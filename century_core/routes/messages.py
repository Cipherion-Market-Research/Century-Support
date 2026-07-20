"""POST /v1/messages -- C1 in, C2 out.

Adapters never call the LLM, format facts, or answer locally (C1 rule);
this is the one place that turns an inbound message into a response.
"""
from fastapi import APIRouter, Depends

from century_core import response_guard
from century_core.commands.registry import detect_command, dispatch_command
from century_core.commands.misc import handle_help
from century_core.deps import get_stores
from century_core.models import InboundMessage, ResponseIR
from century_core.qa.router import answer_question
from century_core.stores import Stores

router = APIRouter()


@router.post("/v1/messages", response_model=ResponseIR)
async def post_message(message: InboundMessage, stores: Stores = Depends(get_stores)) -> ResponseIR:
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
