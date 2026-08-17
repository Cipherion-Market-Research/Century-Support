"""/supply -- thin command wrapper around the deterministic supply Q&A
path (century_core.qa.supply.answer_supply_question), which already
distinguishes on-chain totalSupply() from effective/circulating supply --
see that module's docstring for the full reconciliation."""
from century_core.models import ResponseIR
from century_core.qa.supply import answer_supply_question


async def handle_supply(args: str, stores) -> ResponseIR:
    return await answer_supply_question(stores)
