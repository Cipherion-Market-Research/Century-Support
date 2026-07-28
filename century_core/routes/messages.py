"""POST /v1/messages -- C1 in, C2 out.

Adapters never call the LLM, format facts, or answer locally (C1 rule);
this is the one place that turns an inbound message into a response.
"""
from fastapi import APIRouter, Depends

from century_core import maintenance, response_guard
from century_core.commands.registry import detect_command, dispatch_command
from century_core.commands.misc import handle_help
from century_core.deps import get_stores
from century_core.models import InboundMessage, ParagraphBlock, ResponseIR, ResponseMeta
from century_core.qa.router import answer_question
from century_core.stores import Stores

router = APIRouter()


@router.post("/v1/messages", response_model=ResponseIR)
async def post_message(message: InboundMessage, stores: Stores = Depends(get_stores)) -> ResponseIR:
    # Global maintenance-mode switch (WP-7c rollback ledger): checked first,
    # before any command dispatch or Q&A/LLM routing. Still passes through
    # response_guard below -- a holding message is not exempt from the same
    # final gate every other response goes through.
    holding_message = await maintenance.get_maintenance_message(stores.kpi.redis)
    if holding_message is not None:
        maintenance_response = ResponseIR(
            blocks=[ParagraphBlock(md=holding_message)],
            meta=ResponseMeta(answer_kind="refusal", facts_used=[], kpis_used=[]),
        )
        return response_guard.enforce_response(maintenance_response)

    detected = detect_command(message)
    if detected is not None:
        name, args = detected
        response = await dispatch_command(name, args, stores)
        if response is None:
            response = await handle_help(args, stores)
        return response_guard.enforce_response(response)

    question = message.text.strip()
    if not question:
        return response_guard.safe_refusal()

    response = await answer_question(question, stores)
    return response  # already passed through response_guard inside answer_question
