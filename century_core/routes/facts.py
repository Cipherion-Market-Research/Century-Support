"""GET /v1/facts/:key -- C4: a key that is absent or `unknown` -> "I don't
know" plus the official link, returned as a 404 with that shape rather
than silently omitting fields."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from century_core.config import Config
from century_core.deps import get_stores
from century_core.models import FactResponse, UnknownFactResponse
from century_core.stores import Stores

router = APIRouter()


@router.get("/v1/facts/{key:path}")
async def get_fact(key: str, stores: Stores = Depends(get_stores)):
    fact = stores.facts.get(key)
    if fact is None or fact.is_unknown:
        body = UnknownFactResponse(
            key=key,
            message="I don't have a verified answer for this yet.",
            official_link=Config.OFFICIAL_SITE_URL,
        )
        return JSONResponse(status_code=404, content=body.model_dump())

    return FactResponse(
        key=key,
        value=fact.value,
        verified_on=str(fact.verified_on),
        source_url=fact.source_url,
        notes=fact.notes,
    )
