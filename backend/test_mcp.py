import asyncio
import socket
from threading import Thread
from time import monotonic, sleep

import uvicorn
from mcp import Client

import app
from routes import pitch as pitch_routes


def test_mcp_answers_from_the_bundled_demo_over_streamable_http() -> None:
    active_store = pitch_routes.store
    original = (
        active_store.path,
        active_store.text,
        list(active_store.sections),
        dict(active_store.metadata),
        active_store.source,
    )
    active_store.replace("Private investor name is Example Ventures.", "private.txt")

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app.app, log_level="error", lifespan="on"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()

    try:
        deadline = monotonic() + 10
        while monotonic() < deadline and not server.started:
            sleep(0.05)
        assert server.started, "Pitchroom MCP server did not start"

        async def ask_pitchroom() -> tuple[list[str], object, object]:
            async with Client(f"http://127.0.0.1:{port}/mcp/") as client:
                tools = await client.list_tools()
                grounded = await client.call_tool(
                    "ask_pitch", {"question": "What problem does Pitchroom AI solve?"}
                )
                unsupported = await client.call_tool(
                    "ask_pitch", {"question": "What is its Series B valuation?"}
                )
                return [tool.name for tool in tools.tools], grounded, unsupported

        tool_names, grounded, unsupported = asyncio.run(ask_pitchroom())

        assert tool_names == ["ask_pitch"]
        assert grounded.structured_content["grounded"] is True
        assert grounded.structured_content["source_refs"]
        assert "static pitch decks" in grounded.structured_content["answer"].lower()
        assert unsupported.structured_content["grounded"] is False
        assert unsupported.structured_content["source_refs"] == []
        assert "could not find" in unsupported.structured_content["answer"].lower()
        assert "Example Ventures" not in str(grounded.structured_content)
        assert "Example Ventures" not in str(unsupported.structured_content)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        (
            active_store.path,
            active_store.text,
            active_store.sections,
            active_store.metadata,
            active_store.source,
        ) = original
