"""GET /health -- liveness + dependency connectivity, mirroring
kpi_sync/pubs_rag's health endpoint shape."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from century_core.deps import get_stores
from century_core.stores import Stores

router = APIRouter()


@router.get("/health")
async def health(stores: Stores = Depends(get_stores)):
    checks = {"facts_loaded": len(stores.facts) > 0}

    try:
        await stores.kpi.redis.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    if stores.rag_conn is not None:
        try:
            await stores.rag_conn.fetchval("SELECT 1")
            checks["postgres"] = True
        except Exception:
            checks["postgres"] = False
    else:
        checks["postgres"] = None  # not configured — publications features degrade gracefully

    ok = bool(checks["facts_loaded"]) and bool(checks["redis"]) and checks["postgres"] is not False
    return JSONResponse(status_code=200 if ok else 503, content={"ok": ok, "checks": checks})
