"""WP-7c: ciphex-website is a private repo -- raw-content fetches need a
GITHUB_TOKEN bearer header in production, and must fail with a clear,
actionable error (not a bare 404) when it's missing."""
import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from pubs_rag.config import Config
from pubs_rag.webhook import fetch_raw_file

EXPECTED_TOKEN = "ghp_test_token_xyz"


async def _make_repo_server() -> TestServer:
    async def serve_file(request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {EXPECTED_TOKEN}":
            return web.Response(status=404)
        return web.Response(body=b"file contents")

    app = web.Application()
    app.router.add_get("/{owner}/{repo}/{ref}/{path:.*}", serve_file)
    server = TestServer(app)
    await server.start_server()
    return server


@pytest.mark.asyncio
async def test_auth_header_attached_when_token_configured(monkeypatch):
    server = await _make_repo_server()
    monkeypatch.setattr(Config, "GITHUB_API_BASE_URL", f"http://127.0.0.1:{server.port}")
    monkeypatch.setattr(Config, "GITHUB_TOKEN", EXPECTED_TOKEN)
    try:
        async with aiohttp.ClientSession() as session:
            body = await fetch_raw_file(session, "owner", "repo", "main", "src/index.html")
        assert body == b"file contents"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_clean_actionable_error_without_token(monkeypatch):
    server = await _make_repo_server()
    monkeypatch.setattr(Config, "GITHUB_API_BASE_URL", f"http://127.0.0.1:{server.port}")
    monkeypatch.setattr(Config, "GITHUB_TOKEN", "")
    try:
        async with aiohttp.ClientSession() as session:
            with pytest.raises(RuntimeError) as exc_info:
                await fetch_raw_file(session, "owner", "repo", "main", "src/index.html")
        message = str(exc_info.value)
        assert "private repo" in message
        assert "PUBS_RAG_GITHUB_TOKEN" in message
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_wrong_token_gives_actionable_error_not_missing_token_hint(monkeypatch):
    server = await _make_repo_server()
    monkeypatch.setattr(Config, "GITHUB_API_BASE_URL", f"http://127.0.0.1:{server.port}")
    monkeypatch.setattr(Config, "GITHUB_TOKEN", "wrong-token")
    try:
        async with aiohttp.ClientSession() as session:
            with pytest.raises(RuntimeError) as exc_info:
                await fetch_raw_file(session, "owner", "repo", "main", "src/index.html")
        message = str(exc_info.value)
        assert "read access" in message
        # The token value itself must never appear in an error/log message.
        assert "wrong-token" not in message
    finally:
        await server.close()
