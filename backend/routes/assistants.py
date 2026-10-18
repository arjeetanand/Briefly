from __future__ import annotations

import hashlib
import hmac
import html
import http.client
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import sqlite3
import ssl
import time
import uuid
import urllib.error
import urllib.request
import zipfile
from collections import deque
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from config import setting
from routes.pitch import (
    BACKEND_DIR,
    DOCUMENT_EXTENSIONS,
    DOCUMENT_TYPES,
    DocumentStore,
    QuestionRequest,
    SourceSection,
    _answer_question_from_store,
    _extract_document,
    _normalise_text,
    _text_sections,
    _token_set,
    _token_stem,
    _read_limited_document_upload,
    _document_upload_limit,
)

router = APIRouter()
DATABASE_PATH = Path(setting("PITCHROOM_DATABASE_PATH", "backend/data/pitchroom.sqlite3"))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = BACKEND_DIR.parent / DATABASE_PATH
SESSION_COOKIE = "pitchroom_session"
MAX_SITE_PAGES = 100
MAX_SITE_BYTES = 25 * 1024 * 1024
MAX_PAGE_BYTES = 512 * 1024
MAX_SITE_SECONDS = 45
MAX_ASSISTANT_SOURCES = 100
MAX_ASSISTANT_BYTES = 50 * 1024 * 1024
MAX_ASSISTANT_ANSWERS_PER_MINUTE = 60
USER_AGENT = "PitchroomBot/1.0 (+public-page knowledge import)"


class _Connection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=10, factory=_Connection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_attempts (
            email TEXT NOT NULL, address TEXT NOT NULL, attempted_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assistants (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY, assistant_id TEXT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
            name TEXT NOT NULL, kind TEXT NOT NULL, url TEXT, content_hash TEXT NOT NULL,
            sections TEXT NOT NULL, metadata TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, UNIQUE(assistant_id, url)
        );
        CREATE TABLE IF NOT EXISTS shares (
            assistant_id TEXT PRIMARY KEY REFERENCES assistants(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, snapshot TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS answers (
            id TEXT PRIMARY KEY, assistant_id TEXT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
            grounded INTEGER NOT NULL, latency_ms INTEGER NOT NULL, created_at TEXT NOT NULL,
            retrieval_method TEXT NOT NULL DEFAULT 'lexical', embedding_tokens INTEGER NOT NULL DEFAULT 0,
            session_id TEXT NOT NULL DEFAULT '', estimated_cost_usd REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS retrieval_embeddings (
            content_hash TEXT NOT NULL, model TEXT NOT NULL, vector TEXT NOT NULL,
            PRIMARY KEY(content_hash,model)
        );
        CREATE TABLE IF NOT EXISTS feedback (
            answer_id TEXT PRIMARY KEY REFERENCES answers(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    answer_columns = {row["name"] for row in db.execute("PRAGMA table_info(answers)")}
    if "retrieval_method" not in answer_columns:
        db.execute("ALTER TABLE answers ADD COLUMN retrieval_method TEXT NOT NULL DEFAULT 'lexical'")
    if "embedding_tokens" not in answer_columns:
        db.execute("ALTER TABLE answers ADD COLUMN embedding_tokens INTEGER NOT NULL DEFAULT 0")
    if "session_id" not in answer_columns:
        db.execute("ALTER TABLE answers ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
    if "estimated_cost_usd" not in answer_columns:
        db.execute("ALTER TABLE answers ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0")
    db.execute("UPDATE answers SET session_id=id WHERE session_id='' ")
    return db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retrieval_provider() -> str:
    return "openai" if setting("RETRIEVAL_PROVIDER", "lexical").lower() == "openai" and setting("OPENAI_API_KEY", "") else "lexical"


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{salt.hex()}:{digest.hex()}"


def _valid_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise HTTPException(422, "Enter a valid email address.")
    return value


def _issue_session(db: sqlite3.Connection, user_id: str, response: Response, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=14)
    db.execute(
        "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
        (hashlib.sha256(token.encode()).hexdigest(), user_id, expires.isoformat()),
    )
    host = request.url.hostname or ""
    response.set_cookie(
        SESSION_COOKIE, token, max_age=14 * 86400, httponly=True,
        secure=host not in {"localhost", "127.0.0.1", "::1", "testserver"}, samesite="lax", path="/",
    )


def _user_id(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise HTTPException(401, "Sign in to manage this assistant.")
    with _connect() as db:
        row = db.execute(
            "SELECT user_id,expires_at FROM sessions WHERE token_hash=?",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchone()
        if not row or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            if row:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
            raise HTTPException(401, "Your session expired. Sign in again.")
        return row["user_id"]


def _auth_budget(db: sqlite3.Connection, email: str, request: Request) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    db.execute("DELETE FROM auth_attempts WHERE attempted_at<?", (cutoff,))
    address = request.client.host if request.client else "unknown"
    attempts = db.execute("SELECT COUNT(*) FROM auth_attempts WHERE email=? AND address=? AND attempted_at>=?",
                          (email, address, cutoff)).fetchone()[0]
    if attempts >= 10:
        raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes and try again.")


def _assistant(db: sqlite3.Connection, assistant_id: str, user_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM assistants WHERE id=? AND owner_id=?", (assistant_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Assistant not found.")
    return row


def _answer_budget(db: sqlite3.Connection, assistant_id: str) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    count = db.execute("SELECT COUNT(*) FROM answers WHERE assistant_id=? AND created_at>=?", (assistant_id, cutoff)).fetchone()[0]
    if count >= MAX_ASSISTANT_ANSWERS_PER_MINUTE:
        raise HTTPException(429, "This assistant has reached its 60-question-per-minute pilot limit. Try again shortly.")


def _source_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "name": row["name"], "kind": row["kind"], "url": row["url"],
        "approved": bool(row["approved"]), "metadata": json.loads(row["metadata"]),
        "sections": json.loads(row["sections"]), "created_at": row["created_at"],
    }


def _assistant_payload(db: sqlite3.Connection, row: sqlite3.Row, include_sources: bool = False) -> dict:
    result = {"id": row["id"], "name": row["name"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
    share = db.execute("SELECT revoked,updated_at FROM shares WHERE assistant_id=?", (row["id"],)).fetchone()
    result["published"] = bool(share and not share["revoked"])
    result["published_stale"] = bool(share and not share["revoked"] and share["updated_at"] < row["updated_at"])
    result["source_count"] = db.execute(
        "SELECT COUNT(*) FROM sources WHERE assistant_id=?", (row["id"],)
    ).fetchone()[0]
    if include_sources:
        result["sources"] = [
            _source_payload(source)
            for source in db.execute("SELECT * FROM sources WHERE assistant_id=? ORDER BY created_at", (row["id"],))
        ]
    return result


def _source_store(db: sqlite3.Connection, assistant_id: str, *, approved_only: bool = True) -> DocumentStore:
    where = " AND approved=1" if approved_only else ""
    rows = db.execute(
        f"SELECT * FROM sources WHERE assistant_id=?{where} ORDER BY created_at", (assistant_id,)
    ).fetchall()
    sections = [
        SourceSection(section["text"], section["citation"], section.get("kind", "text"), section.get("url"))
        for row in rows for section in json.loads(row["sections"])
    ]
    document = DocumentStore(Path("assistant sources"))
    document.sections = sections
    document.text = _normalise_text("\n\n".join(section.text for section in sections))
    document.metadata = {"format": "mixed", "sections": len(sections), "warnings": []}
    return document


def _snapshot_store(snapshot: dict) -> DocumentStore:
    sections = [
        SourceSection(section["text"], section["citation"], section.get("kind", "text"), section.get("url"))
        for source in snapshot.get("sources", []) for section in source.get("sections", [])
    ]
    document = DocumentStore(Path("published sources"))
    document.sections = sections
    document.text = _normalise_text("\n\n".join(section.text for section in sections))
    return document


def _embed(texts: list[str]) -> tuple[list[list[float]], int]:
    model = setting("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    url = setting("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/embeddings"
    request = urllib.request.Request(
        url, data=json.dumps({"model": model, "input": texts}).encode(),
        headers={"Authorization": f"Bearer {setting('OPENAI_API_KEY')}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise RuntimeError("The embedding service response was too large.")
            body = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError("The embedding service is unavailable.") from exc
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list) or len(data) != len(texts) or any(not isinstance(item, dict) for item in data):
        raise RuntimeError("The embedding service returned an unexpected response.")
    indices = [item.get("index") for item in data]
    if any(not isinstance(index, int) for index in indices) or set(indices) != set(range(len(texts))):
        raise RuntimeError("The embedding service returned invalid result indices.")
    data.sort(key=lambda item: item["index"])
    vectors = [item.get("embedding") for item in data]
    if any(not isinstance(vector, list) or not vector or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector) for vector in vectors):
        raise RuntimeError("The embedding service returned an invalid vector.")
    usage = body.get("usage", {})
    try:
        tokens = int(usage.get("total_tokens", 0)) if isinstance(usage, dict) else 0
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The embedding service returned invalid token usage.") from exc
    if tokens < 0:
        raise RuntimeError("The embedding service returned invalid token usage.")
    return vectors, tokens


def _semantic_scores(db: sqlite3.Connection, question: str, sections: list[SourceSection]) -> tuple[dict[int, float], int]:
    if setting("RETRIEVAL_PROVIDER", "lexical").lower() != "openai" or not setting("OPENAI_API_KEY", ""):
        return {}, 0
    model = setting("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    inputs = [section.text[:6000] for section in sections]
    hashes = [hashlib.sha256(text.encode()).hexdigest() for text in inputs]
    cached = {}
    unique_hashes = list(dict.fromkeys(hashes))
    for start in range(0, len(unique_hashes), 500):
        batch = unique_hashes[start:start + 500]
        cached.update({row["content_hash"]: json.loads(row["vector"]) for row in db.execute(
            f"SELECT content_hash,vector FROM retrieval_embeddings WHERE model=? AND content_hash IN ({','.join('?' for _ in batch)})",
            (model, *batch),
        )})
    missing_hashes = list(dict.fromkeys(digest for digest in hashes if digest not in cached))
    missing_texts = [inputs[hashes.index(digest)] for digest in missing_hashes]
    tokens_used = 0
    new_vectors: dict[str, list[float]] = {}
    for start in range(0, len(missing_texts), 32):
        vectors, tokens = _embed(missing_texts[start:start + 32])
        tokens_used += tokens
        new_vectors.update(zip(missing_hashes[start:start + 32], vectors))
    query_vectors, query_tokens = _embed([question[:6000]])
    tokens_used += query_tokens
    for digest, vector in new_vectors.items():
        db.execute("INSERT OR IGNORE INTO retrieval_embeddings(content_hash,model,vector) VALUES(?,?,?)",
                   (digest, model, json.dumps(vector)))
    query = query_vectors[0]
    scores: dict[int, float] = {}
    for index, digest in enumerate(hashes):
        vector = cached.get(digest) or new_vectors.get(digest)
        if not vector or len(vector) != len(query):
            continue
        denom = math.sqrt(sum(value * value for value in vector) * sum(value * value for value in query))
        scores[index] = sum(left * right for left, right in zip(vector, query)) / denom if denom else 0
    return scores, tokens_used


def _safe_public_url(value: str, expected_host: str | None = None) -> tuple[str, str, int, str]:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise HTTPException(422, "Enter a valid public website URL.") from exc
    if (parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password
            or port not in {80, 443} or (parsed.scheme == "https" and port != 443)
            or (parsed.scheme == "http" and port != 80)):
        raise HTTPException(422, "Only public HTTP or HTTPS pages on standard ports are supported.")
    if expected_host is not None and host != expected_host:
        raise HTTPException(422, "Website redirects must stay on the submitted domain.")
    try:
        addresses = {item[4][0].split("%", 1)[0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise HTTPException(422, "This website resolves to a private or reserved network address.")
    except (socket.gaierror, ValueError) as exc:
        raise HTTPException(422, "This website could not be resolved as a public host.") from exc
    path = parsed.path or "/"
    query = urlencode([(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                       if key.lower() not in {"fbclid", "gclid", "ref"} and not key.lower().startswith("utm_")])
    normalized = urlunsplit((parsed.scheme, host, path, query, ""))
    return normalized, host, port, parsed.scheme


def _safe_get(url: str, expected_host: str, limit: int, timeout: float = 8) -> tuple[int, dict[str, str], bytes, str]:
    deadline = time.monotonic() + timeout
    for _ in range(6):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The website import deadline was reached.")
        url, host, port, scheme = _safe_public_url(url, expected_host)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ip = next((item[4][0].split("%", 1)[0] for item in addresses if ipaddress.ip_address(item[4][0].split("%", 1)[0]).is_global), None)
        if not ip:
            raise ValueError("No public address was available.")
        raw_socket = socket.create_connection((ip, port), timeout=min(8, remaining))
        connection = None
        try:
            if scheme == "https":
                raw_socket = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("The website import deadline was reached.")
            connection = http.client.HTTPConnection(host, port, timeout=min(8, remaining))
            connection.sock = raw_socket
            path = urlsplit(url).path or "/"
            if urlsplit(url).query:
                path += "?" + urlsplit(url).query
            connection.request("GET", path, headers={"Host": urlsplit(url).netloc, "User-Agent": USER_AGENT, "Accept": "text/html,text/plain,application/xml"})
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            body = response.read(limit + 1)
            status = response.status
            location = headers.get("location", "")
        finally:
            if connection:
                connection.close()
            else:
                raw_socket.close()
        if status not in {301, 302, 303, 307, 308}:
            return status, headers, body, url
        if not location:
            return status, headers, body, url
        next_url = urljoin(url, location)
        if (urlsplit(next_url).hostname or "").lower().rstrip(".") != expected_host:
            raise HTTPException(422, "Website redirects must stay on the submitted domain.")
        if scheme == "https" and urlsplit(next_url).scheme != "https":
            raise HTTPException(422, "Secure websites cannot redirect to an insecure page.")
        url = next_url
    raise ValueError("The page redirected too many times.")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.links: list[str] = []
        self.title = ""
        self._capture = False
        self._ignored = 0
        self._title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self._ignored += 1
        if tag == "title":
            self._title = True
        if self._ignored:
            return
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"] or "")
        if tag in {"p", "li", "h1", "h2", "h3", "br", "tr"}:
            self.blocks.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._title = False
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self._ignored = max(0, self._ignored - 1)
        if tag in {"p", "li", "h1", "h2", "h3", "tr"}:
            self.blocks.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._title:
            self.title += data
        if not self._ignored:
            self.blocks.append(data)


def _html_sections(payload: bytes, page_url: str) -> tuple[str, list[SourceSection], list[str]]:
    parser = _PageParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    title = _normalise_text(parser.title) or urlsplit(page_url).path.strip("/").split("/")[-1] or urlsplit(page_url).hostname or "Website page"
    text = _normalise_text("".join(parser.blocks))[:50_000]
    if not text:
        return title, [], parser.links
    sections = [SourceSection(section.text, f"{title} · {index + 1}", section.kind, page_url)
                for index, section in enumerate(_text_sections(text))]
    return title, sections, parser.links


def _crawl_site(start_url: str) -> dict:
    start_url, host, _, _ = _safe_public_url(start_url)
    started = time.monotonic()
    deadline = started + MAX_SITE_SECONDS

    def fetch(url: str, limit: int) -> tuple[int, dict[str, str], bytes, str]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The website import deadline was reached.")
        return _safe_get(url, host, limit, timeout=remaining)

    robots_url = urlunsplit((urlsplit(start_url).scheme, host, "/robots.txt", "", ""))
    try:
        robots_status, _, robots_body, _ = fetch(robots_url, 256_000)
    except (OSError, ValueError, HTTPException):
        robots_status, robots_body = 503, b""
    from urllib.robotparser import RobotFileParser
    robot = RobotFileParser(robots_url)
    if robots_status in {200, 404, 410}:
        robot.parse(robots_body.decode("utf-8", errors="replace").splitlines() if robots_status == 200 else [])
    else:
        robot.parse(["User-agent: *", "Disallow: /"])

    queue = deque([start_url])
    visited: set[str] = set()
    content_hashes: set[str] = set()
    sources: list[dict] = []
    failed: list[str] = []
    skipped_pages: list[str] = []
    skipped = 0
    total_bytes = 0
    sitemap_urls = list(robot.site_maps() or [])[:5]
    sitemap_urls.append(urlunsplit((urlsplit(start_url).scheme, host, "/sitemap.xml", "", "")))
    for sitemap in dict.fromkeys(sitemap_urls):
        if len(visited) >= MAX_SITE_PAGES or time.monotonic() - started > MAX_SITE_SECONDS:
            break
        try:
            code, headers, body, final_url = fetch(sitemap, 2_000_000)
            if code == 200 and ("xml" in headers.get("content-type", "") or body.lstrip().startswith(b"<?xml")):
                text = body.decode("utf-8", errors="replace")
                sitemap_entries = re.findall(r"<loc>\s*(.*?)\s*</loc>", text, re.I | re.S)
                queue.extend(urljoin(final_url, html.unescape(match)) for match in sitemap_entries[:max(0, MAX_SITE_PAGES - len(queue))])
        except (OSError, ValueError, HTTPException):
            continue

    while queue and len(visited) < MAX_SITE_PAGES and time.monotonic() - started < MAX_SITE_SECONDS and total_bytes < MAX_SITE_BYTES:
        candidate = queue.popleft()
        try:
            page_url, _, _, _ = _safe_public_url(candidate, host)
        except HTTPException:
            skipped += 1
            skipped_pages.append(str(candidate)[:300])
            continue
        if page_url in visited:
            continue
        visited.add(page_url)
        if not robot.can_fetch(USER_AGENT, page_url):
            skipped += 1
            skipped_pages.append(page_url)
            continue
        try:
            status, headers, body, final_url = fetch(page_url, MAX_PAGE_BYTES)
            if status != 200 or "text/html" not in headers.get("content-type", ""):
                skipped += 1
                skipped_pages.append(page_url)
                continue
            if len(body) > MAX_PAGE_BYTES:
                skipped += 1
                skipped_pages.append(page_url)
                continue
            total_bytes += len(body)
            title, sections, links = _html_sections(body, final_url)
            for link in links:
                if len(visited) + len(queue) >= MAX_SITE_PAGES:
                    break
                target = urljoin(final_url, link.strip())
                parsed = urlsplit(target)
                if (parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower().rstrip(".") == host
                        and not parsed.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".mp4", ".xml"))):
                    queue.append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")))
            if not sections:
                skipped += 1
                skipped_pages.append(page_url)
                failed.append(f"{page_url}: no extractable text; this page may need JavaScript rendering")
                continue
            digest = hashlib.sha256("\n".join(section.text for section in sections).encode()).hexdigest()
            if digest in content_hashes:
                skipped += 1
                skipped_pages.append(page_url)
                continue
            content_hashes.add(digest)
            sources.append({"name": title[:160], "kind": "website", "url": final_url, "sections": sections,
                            "metadata": {"format": "html", "sections": len(sections), "warnings": [], "imported_at": _now()}})
        except (OSError, ValueError, TimeoutError, ssl.SSLError, http.client.HTTPException, HTTPException) as exc:
            failed.append(f"{page_url}: {str(exc)[:200]}")
    return {"sources": sources, "failed": failed[:100], "skipped": skipped, "skipped_pages": skipped_pages[:100],
            "truncated": bool(queue or len(visited) >= MAX_SITE_PAGES or total_bytes >= MAX_SITE_BYTES or time.monotonic() >= deadline),
            "pages_visited": len(visited)}


def _store_source(db: sqlite3.Connection, assistant_id: str, item: dict) -> str:
    sections = [
        {"text": part.text, "citation": part.citation, "kind": part.kind, **({"url": part.url} if part.url else {})}
        if isinstance(part, SourceSection) else part for part in item["sections"]
    ]
    content = "\n\n".join(section["text"] for section in sections)
    digest = hashlib.sha256(content.encode()).hexdigest()
    existing = None
    if item.get("url"):
        existing = db.execute("SELECT id,content_hash FROM sources WHERE assistant_id=? AND url=?", (assistant_id, item["url"])).fetchone()
    else:
        existing = db.execute("SELECT id,content_hash FROM sources WHERE assistant_id=? AND url IS NULL AND kind=? AND name=?",
                              (assistant_id, item["kind"], item["name"])).fetchone()
        if not existing:
            duplicate = db.execute("SELECT id,content_hash FROM sources WHERE assistant_id=? AND url IS NULL AND content_hash=?", (assistant_id, digest)).fetchone()
            if duplicate:
                return "unchanged"
    if existing and existing["content_hash"] == digest:
        return "unchanged"
    usage = db.execute("SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(sections AS BLOB))),0) FROM sources WHERE assistant_id=?", (assistant_id,)).fetchone()
    existing_size = db.execute("SELECT LENGTH(CAST(sections AS BLOB)) FROM sources WHERE id=?", (existing["id"],)).fetchone()[0] if existing else 0
    new_size = len(json.dumps(sections, ensure_ascii=False).encode("utf-8"))
    if usage[0] >= MAX_ASSISTANT_SOURCES and not existing:
        raise HTTPException(413, f"Each assistant can have at most {MAX_ASSISTANT_SOURCES} sources.")
    if usage[1] - (existing_size or 0) + new_size > MAX_ASSISTANT_BYTES:
        raise HTTPException(413, "This assistant has reached its 50 MB source limit. Remove a source before adding more.")
    source_metadata = dict(item.get("metadata", {}))
    source_metadata["imported_at"] = _now()
    metadata = json.dumps(source_metadata, ensure_ascii=False)
    if existing:
        now = _now()
        db.execute("UPDATE sources SET name=?,kind=?,content_hash=?,sections=?,metadata=?,approved=0,created_at=? WHERE id=?",
                   (item["name"], item["kind"], digest, json.dumps(sections, ensure_ascii=False), metadata, now, existing["id"]))
        db.execute("UPDATE assistants SET updated_at=? WHERE id=?", (now, assistant_id))
        return "updated"
    now = _now()
    db.execute("INSERT INTO sources(id,assistant_id,name,kind,url,content_hash,sections,metadata,approved,created_at) VALUES(?,?,?,?,?,?,?,?,0,?)",
               (str(uuid.uuid4()), assistant_id, item["name"], item["kind"], item.get("url"), digest,
                json.dumps(sections, ensure_ascii=False), metadata, now))
    db.execute("UPDATE assistants SET updated_at=? WHERE id=?", (now, assistant_id))
    return "added"


class AccountRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=200)
    invite_code: str = Field(default="", max_length=300)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class AssistantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WebsiteRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class ApprovalRequest(BaseModel):
    approved: bool


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=300)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)
    session_id: str = Field(default="", max_length=64)


class FeedbackRequest(BaseModel):
    answer_id: str
    rating: int = Field(ge=-1, le=1)


@router.post("/api/auth/register")
def register(request: AccountRequest, response: Response, http_request: Request) -> dict:
    invite = setting("PITCHROOM_ACCESS_TOKEN", "")
    if invite and not hmac.compare_digest(request.invite_code, invite):
        raise HTTPException(403, "The pilot invite code is not valid.")
    email = _email(request.email)
    user_id = str(uuid.uuid4())
    try:
        with _connect() as db:
            db.execute("INSERT INTO users(id,email,password,created_at) VALUES(?,?,?,?)",
                       (user_id, email, _password_hash(request.password), _now()))
            _issue_session(db, user_id, response, http_request)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "An account with this email already exists.") from exc
    return {"email": email}


@router.post("/api/auth/login")
def login(request: LoginRequest, response: Response, http_request: Request) -> dict:
    email = _email(request.email)
    with _connect() as db:
        _auth_budget(db, email, http_request)
        row = db.execute("SELECT id,password FROM users WHERE email=?", (email,)).fetchone()
        if not row or not _valid_password(request.password, row["password"]):
            db.execute("INSERT INTO auth_attempts(email,address,attempted_at) VALUES(?,?,?)",
                       (email, http_request.client.host if http_request.client else "unknown", _now()))
            db.commit()
            raise HTTPException(401, "Email or password is incorrect.")
        db.execute("DELETE FROM auth_attempts WHERE email=? AND address=?",
                   (email, http_request.client.host if http_request.client else "unknown"))
        _issue_session(db, row["id"], response, http_request)
    return {"email": email}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        with _connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"ok": True}


@router.get("/api/auth/me")
def current_user(request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        user = db.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
    return {"email": user["email"], "retrieval_provider": _retrieval_provider()}


@router.get("/api/assistants")
def list_assistants(request: Request) -> list[dict]:
    user_id = _user_id(request)
    with _connect() as db:
        rows = db.execute("SELECT * FROM assistants WHERE owner_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()
        return [_assistant_payload(db, row) for row in rows]


@router.post("/api/assistants")
def create_assistant(payload: AssistantRequest, request: Request) -> dict:
    user_id = _user_id(request)
    assistant_id, now = str(uuid.uuid4()), _now()
    with _connect() as db:
        if db.execute("SELECT COUNT(*) FROM assistants WHERE owner_id=?", (user_id,)).fetchone()[0] >= 20:
            raise HTTPException(429, "This pilot account can have up to 20 assistants.")
        db.execute("INSERT INTO assistants(id,owner_id,name,created_at,updated_at) VALUES(?,?,?,?,?)",
                   (assistant_id, user_id, payload.name.strip(), now, now))
        row = db.execute("SELECT * FROM assistants WHERE id=?", (assistant_id,)).fetchone()
        return _assistant_payload(db, row, include_sources=True)


@router.get("/api/assistants/{assistant_id}")
def get_assistant(assistant_id: str, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        return _assistant_payload(db, _assistant(db, assistant_id, user_id), include_sources=True)


@router.patch("/api/assistants/{assistant_id}")
def rename_assistant(assistant_id: str, payload: RenameRequest, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        db.execute("UPDATE assistants SET name=?,updated_at=? WHERE id=?", (payload.name.strip(), _now(), assistant_id))
        return _assistant_payload(db, _assistant(db, assistant_id, user_id), include_sources=True)


@router.delete("/api/assistants/{assistant_id}")
def delete_assistant(assistant_id: str, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        db.execute("DELETE FROM assistants WHERE id=?", (assistant_id,))
    return {"ok": True}


@router.post("/api/assistants/{assistant_id}/sources/files")
async def upload_source(assistant_id: str, request: Request, file: UploadFile = File(...)) -> dict:
    user_id = _user_id(request)
    content_type = (file.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    filename = Path(file.filename or "uploaded document").name
    if Path(filename).suffix.lower() not in DOCUMENT_EXTENSIONS and content_type not in DOCUMENT_TYPES:
        raise HTTPException(415, "Upload a PPTX, PDF, DOCX, text, or Markdown file.")
    raw = await _read_limited_document_upload(file, _document_upload_limit())
    try:
        sections, metadata = _extract_document(raw, filename, content_type)
        if not sections and not metadata.get("warnings"):
            raise ValueError("No readable text was found in this file.")
    except (ValueError, zipfile.BadZipFile) as exc:
        raise HTTPException(400, str(exc)) from exc
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        result = _store_source(db, assistant_id, {"name": filename, "kind": "file", "sections": sections, "metadata": metadata})
    return {"status": result, "source": filename, "approved": False, "metadata": metadata}


@router.post("/api/assistants/{assistant_id}/sources/websites")
def import_website(assistant_id: str, payload: WebsiteRequest, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
    result = _crawl_site(payload.url)
    added = unchanged = updated = 0
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        for source in result["sources"]:
            status = _store_source(db, assistant_id, source)
            added += status == "added"
            unchanged += status == "unchanged"
            updated += status == "updated"
    return {**{key: value for key, value in result.items() if key != "sources"},
            "added": added, "unchanged": unchanged, "updated": updated,
            "message": "New or changed pages need your approval before they can answer questions."}


@router.patch("/api/assistants/{assistant_id}/sources/{source_id}")
def approve_source(assistant_id: str, source_id: str, payload: ApprovalRequest, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        source = db.execute("SELECT sections FROM sources WHERE id=? AND assistant_id=?", (source_id, assistant_id)).fetchone()
        if not source:
            raise HTTPException(404, "Source not found.")
        if payload.approved and not json.loads(source["sections"]):
            raise HTTPException(409, "This source has no searchable text. Keep it unapproved or remove it.")
        cursor = db.execute("UPDATE sources SET approved=? WHERE id=? AND assistant_id=?",
                            (int(payload.approved), source_id, assistant_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Source not found.")
        db.execute("UPDATE assistants SET updated_at=? WHERE id=?", (_now(), assistant_id))
        return _source_payload(db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone())


@router.delete("/api/assistants/{assistant_id}/sources/{source_id}")
def delete_source(assistant_id: str, source_id: str, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        cursor = db.execute("DELETE FROM sources WHERE id=? AND assistant_id=?", (source_id, assistant_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Source not found.")
        db.execute("UPDATE assistants SET updated_at=? WHERE id=?", (_now(), assistant_id))
        return {"ok": True}


def _answer(assistant: DocumentStore, payload: AskRequest, db: sqlite3.Connection) -> dict:
    if not assistant.text:
        raise HTTPException(409, "Approve at least one source before asking questions.")
    question = payload.question.strip()
    history = payload.history[-6:]
    # Only pronoun-led follow-ups inherit the prior question, keeping unrelated turns separate.
    previous_question = next((item.content for item in reversed(history) if item.role == "user"), "")
    follow_up = bool(previous_question and re.search(r"\b(it|they|them|this|that|these|those)\b|^(and|also|what about|how about)\b", question.lower()))
    retrieval_question = f"{previous_question[:max(0, 1999 - len(question))]} {question}" if previous_question and follow_up else question
    started = time.monotonic()
    retrieval_mode = "lexical"
    embedding_tokens = 0
    try:
        semantic_scores, embedding_tokens = _semantic_scores(db, retrieval_question, assistant.sections)
        if semantic_scores:
            retrieval_mode = "openai-semantic"
    except RuntimeError:
        semantic_scores = {}
        retrieval_mode = "keyword-fallback"
    result = _answer_question_from_store(
        QuestionRequest(question=retrieval_question), assistant,
        allow_generation=False, semantic_scores=semantic_scores or None,
    )
    if follow_up and result["grounded"]:
        follow_up_terms = _token_set(question)
        evidence_terms = {word for section in result["source_refs"] for word in _token_set(section["text"])}
        evidence_stems = {_token_stem(word) for word in evidence_terms}
        if any(word not in evidence_terms and _token_stem(word) not in evidence_stems for word in follow_up_terms):
            result["grounded"] = False
            result["sources"] = []
            result["source_refs"] = []
    result["question"] = question
    if not result["grounded"]:
        result["answer"] = "I could not find that in the approved sources."
    result["answer_id"] = str(uuid.uuid4())
    result["latency_ms"] = round((time.monotonic() - started) * 1000)
    result["retrieval_mode"] = retrieval_mode
    result["embedding_tokens"] = embedding_tokens
    try:
        token_price = float(setting("OPENAI_EMBEDDING_USD_PER_MILLION_TOKENS", "0.02"))
        if not math.isfinite(token_price):
            raise ValueError("The rate must be a finite number.")
    except ValueError:
        token_price = 0
    result["estimated_cost_usd"] = max(0, token_price) * embedding_tokens / 1_000_000
    return result


@router.post("/api/assistants/{assistant_id}/answer")
def answer_owner(assistant_id: str, payload: AskRequest, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        _answer_budget(db, assistant_id)
        store = _source_store(db, assistant_id)
        result = _answer(store, payload, db)
        db.execute("INSERT INTO answers(id,assistant_id,grounded,latency_ms,created_at,retrieval_method,embedding_tokens,session_id,estimated_cost_usd) VALUES(?,?,?,?,?,?,?,?,?)",
                   (result["answer_id"], assistant_id, int(result["grounded"]), result["latency_ms"], _now(), result["retrieval_mode"], result["embedding_tokens"], payload.session_id[:64] or result["answer_id"], result["estimated_cost_usd"]))
    return result


@router.post("/api/assistants/{assistant_id}/feedback")
def answer_feedback(assistant_id: str, payload: FeedbackRequest, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        answer = db.execute("SELECT id FROM answers WHERE id=? AND assistant_id=?", (payload.answer_id, assistant_id)).fetchone()
        if not answer:
            raise HTTPException(404, "Answer not found.")
        db.execute("INSERT INTO feedback(answer_id,rating,created_at) VALUES(?,?,?) ON CONFLICT(answer_id) DO UPDATE SET rating=excluded.rating,created_at=excluded.created_at",
                   (payload.answer_id, payload.rating, _now()))
    return {"ok": True}


@router.get("/api/assistants/{assistant_id}/metrics")
def assistant_metrics(assistant_id: str, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        return {
            "questions": db.execute("SELECT COUNT(*) FROM answers WHERE assistant_id=?", (assistant_id,)).fetchone()[0],
            "unanswered": db.execute("SELECT COUNT(*) FROM answers WHERE assistant_id=? AND grounded=0", (assistant_id,)).fetchone()[0],
            "avg_latency_ms": db.execute("SELECT COALESCE(AVG(latency_ms),0) FROM answers WHERE assistant_id=?", (assistant_id,)).fetchone()[0],
            "helpful": db.execute("SELECT COUNT(*) FROM feedback f JOIN answers a ON a.id=f.answer_id WHERE a.assistant_id=? AND f.rating=1", (assistant_id,)).fetchone()[0],
            "not_helpful": db.execute("SELECT COUNT(*) FROM feedback f JOIN answers a ON a.id=f.answer_id WHERE a.assistant_id=? AND f.rating=-1", (assistant_id,)).fetchone()[0],
            "embedding_tokens": db.execute("SELECT COALESCE(SUM(embedding_tokens),0) FROM answers WHERE assistant_id=?", (assistant_id,)).fetchone()[0],
            "sessions": db.execute("SELECT COUNT(DISTINCT session_id) FROM answers WHERE assistant_id=?", (assistant_id,)).fetchone()[0],
            "avg_embedding_cost_per_session_usd": db.execute("SELECT COALESCE(SUM(estimated_cost_usd)/NULLIF(COUNT(DISTINCT session_id),0),0) FROM answers WHERE assistant_id=?", (assistant_id,)).fetchone()[0],
            "semantic_answers": db.execute("SELECT COUNT(*) FROM answers WHERE assistant_id=? AND retrieval_method='openai-semantic'", (assistant_id,)).fetchone()[0],
            "retrieval_fallbacks": db.execute("SELECT COUNT(*) FROM answers WHERE assistant_id=? AND retrieval_method='keyword-fallback'", (assistant_id,)).fetchone()[0],
        }


@router.post("/api/assistants/{assistant_id}/publish")
def publish_assistant(assistant_id: str, request: Request) -> dict:
    user_id = _user_id(request)
    token = secrets.token_urlsafe(32)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        sources = [_source_payload(row) for row in db.execute(
            "SELECT * FROM sources WHERE assistant_id=? AND approved=1 ORDER BY created_at", (assistant_id,))]
        if not sources:
            raise HTTPException(409, "Approve at least one source before publishing.")
        snapshot = json.dumps({"assistant_id": assistant_id, "name": _assistant(db, assistant_id, user_id)["name"], "sources": sources}, ensure_ascii=False)
        db.execute("INSERT INTO shares(assistant_id,token_hash,snapshot,revoked,updated_at) VALUES(?,?,?,0,?) "
                   "ON CONFLICT(assistant_id) DO UPDATE SET token_hash=excluded.token_hash,snapshot=excluded.snapshot,revoked=0,updated_at=excluded.updated_at",
                   (assistant_id, hashlib.sha256(token.encode()).hexdigest(), snapshot, _now()))
    return {"url": f"/s/{token}", "published": True}


@router.delete("/api/assistants/{assistant_id}/publish")
def unpublish_assistant(assistant_id: str, request: Request) -> dict:
    user_id = _user_id(request)
    with _connect() as db:
        _assistant(db, assistant_id, user_id)
        db.execute("UPDATE shares SET revoked=1,updated_at=? WHERE assistant_id=?", (_now(), assistant_id))
    return {"published": False}


def _published(token: str) -> tuple[sqlite3.Row, dict]:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as db:
        row = db.execute("SELECT * FROM shares WHERE token_hash=? AND revoked=0", (token_hash,)).fetchone()
    if not row:
        raise HTTPException(404, "This assistant link is no longer available.")
    return row, json.loads(row["snapshot"])


@router.get("/api/shared/{share_token}")
def shared_assistant(share_token: str) -> dict:
    _, snapshot = _published(share_token)
    return {"name": snapshot["name"], "retrieval_provider": _retrieval_provider(), "sources": [
        {"id": item["id"], "name": item["name"], "kind": item["kind"], "url": item["url"], "metadata": item["metadata"]}
        for item in snapshot["sources"]
    ]}


@router.post("/api/shared/{share_token}/answer")
def shared_answer(share_token: str, payload: AskRequest) -> dict:
    _, snapshot = _published(share_token)
    with _connect() as db:
        _answer_budget(db, snapshot["assistant_id"])
        result = _answer(_snapshot_store(snapshot), payload, db)
        db.execute("INSERT INTO answers(id,assistant_id,grounded,latency_ms,created_at,retrieval_method,embedding_tokens,session_id,estimated_cost_usd) VALUES(?,?,?,?,?,?,?,?,?)",
                   (result["answer_id"], snapshot["assistant_id"], int(result["grounded"]), result["latency_ms"], _now(), result["retrieval_mode"], result["embedding_tokens"], payload.session_id[:64] or result["answer_id"], result["estimated_cost_usd"]))
    return result


@router.post("/api/shared/{share_token}/feedback")
def shared_feedback(share_token: str, payload: FeedbackRequest) -> dict:
    _, snapshot = _published(share_token)
    with _connect() as db:
        answer = db.execute("SELECT id FROM answers WHERE id=? AND assistant_id=?", (payload.answer_id, snapshot["assistant_id"])).fetchone()
        if not answer:
            raise HTTPException(404, "Answer not found.")
        db.execute("INSERT INTO feedback(answer_id,rating,created_at) VALUES(?,?,?) ON CONFLICT(answer_id) DO UPDATE SET rating=excluded.rating,created_at=excluded.created_at",
                   (payload.answer_id, payload.rating, _now()))
    return {"ok": True}
