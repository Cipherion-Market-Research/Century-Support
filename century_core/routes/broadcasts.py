"""POST /v1/broadcasts -- accepts a C2-shaped broadcast and durably queues
it for delivery. No channel adapters exist yet (WP-6 is Sprint 3, after
this epic's API freeze), so this endpoint's job today is: validate,
guardrail-check, and enqueue on Redis for whichever adapter picks it up
later -- not claim delivery that can't happen yet.
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from century_core import guardrails
from century_core.config import Config
from century_core.deps import get_stores
from century_core.models import BroadcastAccepted, BroadcastRequest
from century_core.stores import Stores

router = APIRouter()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@router.post("/v1/broadcasts", response_model=BroadcastAccepted, status_code=202)
async def post_broadcast(request: BroadcastRequest, stores: Stores = Depends(get_stores)) -> BroadcastAccepted:
    text = "\n".join(_extract_text_for_block(b) for b in request.blocks)
    result = guardrails.check_text(text)
    if not result.ok:
        raise HTTPException(status_code=422, detail={"guardrail_violations": result.violations})

    broadcast_id = str(uuid.uuid4())
    queued_at = _utcnow_iso()

    envelope = {
        "broadcast_id": broadcast_id,
        "queued_at": queued_at,
        "target": request.target.model_dump(),
        "blocks": [b.model_dump() for b in request.blocks],
    }
    redis_client = stores.kpi.redis
    if redis_client is not None:
        await redis_client.rpush(Config.BROADCAST_QUEUE_KEY, json.dumps(envelope))

    return BroadcastAccepted(broadcast_id=broadcast_id, enqueued=redis_client is not None, queued_at=queued_at)


def _extract_text_for_block(block) -> str:
    if block.type == "heading":
        return block.text
    if block.type in ("paragraph", "warning"):
        return block.md
    if block.type == "fact":
        return f"{block.label} {block.value}"
    if block.type in ("links", "buttons"):
        return "\n".join(item.label for item in block.items)
    return ""
