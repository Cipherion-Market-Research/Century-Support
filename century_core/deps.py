"""FastAPI dependency providers. Production wiring lives in app.state (set
up in app.py); tests override get_stores via app.dependency_overrides to
inject a Stores built entirely from stubs — no real Redis/Postgres/OpenAI
needed."""
from fastapi import Request

from century_core.stores import Stores


def get_stores(request: Request) -> Stores:
    return request.app.state.stores
