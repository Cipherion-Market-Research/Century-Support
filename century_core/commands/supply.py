"""/supply -- thin command wrapper around the deterministic supply Q&A
path (century_core.qa.supply.answer_supply_question), which already
distinguishes on-chain totalSupply() from effective/circulating supply --
see that module's docstring for the full reconciliation."""
from century_core.commands._related import related_footer
from century_core.models import ResponseIR
from century_core.qa.supply import answer_supply_question


async def handle_supply(args: str, stores) -> ResponseIR:
    response = await answer_supply_question(stores)
    # answer_supply_question is shared with the plain-text Q&A route (its
    # answer_kind is "faq", not "command") -- the /command related-links
    # footer is appended here, in the /supply wrapper, rather than in that
    # shared module, so it only ever shows up on the /supply command
    # response, never on a plain-text supply/burn question's answer.
    footer = related_footer(("price", "price info"), ("stats", "claim statistics"))
    return response.model_copy(update={"blocks": [*response.blocks, footer]})
