import pytest

from kpi_sync.retry import retry_async


@pytest.mark.asyncio
async def test_retry_async_succeeds_first_try():
    calls = []

    async def fn():
        calls.append(1)
        return "ok"

    result = await retry_async(fn)
    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_async_retries_then_succeeds():
    calls = []

    async def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("transient")
        return "ok"

    result = await retry_async(fn, max_attempts=5, base_delay=0.01, max_delay=0.02)
    assert result == "ok"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retry_async_raises_last_exception_after_max_attempts():
    async def fn():
        raise ValueError("still broken")

    with pytest.raises(ValueError, match="still broken"):
        await retry_async(fn, max_attempts=3, base_delay=0.01, max_delay=0.02)
