import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from config import load_environment, setting

load_environment()

from routes.pitch import router, store
from routes.assistants import router as assistants_router
from mcp_server import server as pitch_mcp_server


mcp_http_app = pitch_mcp_server.streamable_http_app(
    streamable_http_path="/",
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "localhost:*",
            "127.0.0.1:*",
            "[::1]:*",
            "pitchvoice-ai.onrender.com",
        ],
        allowed_origins=[
            "http://localhost:*",
            "http://127.0.0.1:*",
            "http://[::1]:*",
            "https://pitchvoice-ai.onrender.com",
            "https://chatgpt.com",
            "https://chat.openai.com",
        ],
    ),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with pitch_mcp_server.session_manager.run():
        yield


app = FastAPI(title="Pitchroom AI API", version="1.0.0", lifespan=lifespan)
allowed_origins = [
    origin.strip()
    for origin in setting("FRONTEND_ORIGINS").split(",")
    if origin.strip()
]
@app.middleware("http")
async def require_room_token(request: Request, call_next):
    workspace_api = request.url.path.startswith(("/api/auth/", "/api/assistants", "/api/shared/"))
    if request.method != "OPTIONS" and not workspace_api and (request.url.path == "/api" or request.url.path.startswith("/api/")):
        # The Render launcher fails closed; an empty setting is for loopback development.
        required_token = setting("PITCHROOM_ACCESS_TOKEN")
        if required_token:
            scheme, _, provided_token = request.headers.get("authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(provided_token, required_token):
                return JSONResponse(
                    {"detail": "Enter the access token configured for this Pitchroom room."},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
    return await call_next(request)


# Keep CORS outside the access gate so browser clients can read 401 challenges.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router)
app.include_router(assistants_router)
app.mount("/mcp", mcp_http_app, name="pitchroom-mcp")

# The public demo uses one origin: FastAPI serves both the API and the browser
# voice room.  That keeps microphone uploads on the same HTTPS origin in a
# deployment instead of exposing a private localhost API to presentation
# attendees' browsers.
FRONTEND_STATIC_DIR = Path(__file__).resolve().parents[1] / "frontend" / "static"
if FRONTEND_STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_STATIC_DIR), name="frontend-static")

    @app.get("/", include_in_schema=False)
    def serve_frontend() -> FileResponse:
        return FileResponse(FRONTEND_STATIC_DIR / "index.html")

    @app.get("/studio", include_in_schema=False)
    def serve_studio() -> FileResponse:
        return FileResponse(FRONTEND_STATIC_DIR / "studio.html")

    @app.get("/s/{share_token}", include_in_schema=False)
    def serve_shared_assistant(share_token: str) -> FileResponse:
        return FileResponse(FRONTEND_STATIC_DIR / "studio.html")

__all__ = ["app", "store"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
