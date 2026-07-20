"""Test doubles: a minimal in-memory async Redis + a scriptable fake
aiohttp session. Kept dependency-free (no fakeredis/aioresponses) since
this service's own requirements.txt is deliberately minimal."""
import time
from typing import Any, Dict, List, Optional, Union

import pytest


class FakeRedis:
    """Implements exactly the subset of redis.asyncio's interface KpiStore
    uses: get() and set(key, value, ex=...)."""

    def __init__(self):
        self._data: Dict[str, str] = {}
        self._expires_at: Dict[str, float] = {}

    def _expired(self, key: str) -> bool:
        exp = self._expires_at.get(key)
        return exp is not None and time.monotonic() >= exp

    async def get(self, key: str) -> Optional[str]:
        if key not in self._data or self._expired(key):
            self._data.pop(key, None)
            self._expires_at.pop(key, None)
            return None
        return self._data[key]

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self._data[key] = value
        if ex is not None:
            self._expires_at[key] = time.monotonic() + ex
        else:
            self._expires_at.pop(key, None)


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        json_body: Any = None,
        text_body: str = "",
        headers: Optional[dict] = None,
    ):
        self.status = status
        self._json_body = json_body
        self._text_body = text_body
        self.headers = headers or {}

    async def json(self, content_type=None):
        return self._json_body

    async def text(self):
        return self._text_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class RaiseResponse:
    """A scripted step that raises an exception instead of returning a response."""

    def __init__(self, exc: BaseException):
        self.exc = exc


class FakeSession:
    """Fake aiohttp.ClientSession.get(): pops one scripted response/exception
    per call, in order. The last entry repeats if the script is exhausted."""

    def __init__(self, script: List[Union[FakeResponse, RaiseResponse]]):
        self.script = list(script)
        self.calls: List[str] = []

    def get(self, url: str, timeout=None, headers=None):
        self.calls.append(url)
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, RaiseResponse):
            raise step.exc
        return step


@pytest.fixture
def fake_redis():
    return FakeRedis()
