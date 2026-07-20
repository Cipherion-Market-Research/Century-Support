import asyncio

import aiohttp
import pytest

from kpi_sync.http import FetchError, fetch_json
from kpi_sync.tests.conftest import FakeResponse, FakeSession, RaiseResponse


@pytest.mark.asyncio
async def test_fetch_json_success_first_try():
    session = FakeSession([FakeResponse(200, json_body={"ok": True})])
    result = await fetch_json(session, "http://example/ok")
    assert result == {"ok": True}
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_fetch_json_retries_on_500_then_succeeds():
    session = FakeSession(
        [FakeResponse(500), FakeResponse(200, json_body={"ok": True})]
    )
    result = await fetch_json(session, "http://example/flaky", base_delay=0.01, max_delay=0.02)
    assert result == {"ok": True}
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_fetch_json_retries_on_429_honors_retry_after():
    session = FakeSession(
        [
            FakeResponse(429, headers={"Retry-After": "0.01"}),
            FakeResponse(200, json_body={"ok": True}),
        ]
    )
    result = await fetch_json(session, "http://example/limited")
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_fetch_json_non_retryable_4xx_raises_immediately():
    session = FakeSession([FakeResponse(404, text_body="not found")])
    with pytest.raises(FetchError):
        await fetch_json(session, "http://example/missing", max_attempts=5)
    # Must not retry a plain 404 -- only one call should have happened.
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_fetch_json_gives_up_after_max_attempts():
    session = FakeSession([FakeResponse(503)])
    with pytest.raises(FetchError):
        await fetch_json(session, "http://example/down", max_attempts=3, base_delay=0.01, max_delay=0.02)
    assert len(session.calls) == 3


@pytest.mark.asyncio
async def test_fetch_json_retries_on_connection_error():
    session = FakeSession(
        [
            RaiseResponse(aiohttp.ClientConnectionError("boom")),
            FakeResponse(200, json_body={"ok": True}),
        ]
    )
    result = await fetch_json(session, "http://example/reconnect", base_delay=0.01, max_delay=0.02)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_fetch_json_respects_rate_limiter(monkeypatch):
    from kpi_sync.ratelimiter import AsyncRateLimiter

    limiter = AsyncRateLimiter(max_calls=100, period_s=1.0)
    calls = []
    original_acquire = limiter.acquire

    async def spy_acquire():
        calls.append(1)
        await original_acquire()

    monkeypatch.setattr(limiter, "acquire", spy_acquire)
    session = FakeSession([FakeResponse(200, json_body={"ok": True})])
    await fetch_json(session, "http://example/ok", rate_limiter=limiter)
    assert len(calls) == 1
