"""/contact -- how to reach Ciphex."""
from century_core.commands._related import related_footer
from century_core.models import (
    FactBlock,
    HeadingBlock,
    LinkItem,
    LinksBlock,
    ParagraphBlock,
    ResponseIR,
    ResponseMeta,
    WarningBlock,
)

_GENERAL_EMAIL_FALLBACK = "hello@ciphex.io"
_PARTNERSHIPS_EMAIL_FALLBACK = "partnerships@ciphex.io"
_CONTACT_PAGE_FALLBACK = "https://ciphex.io/contact-ciphex"
_TELEGRAM_FALLBACK = "https://t.me/ciphexgroup"
_DEFAULT_SLA_SENTENCE = "Response within 72 business hours, Mon–Fri 09:00–18:00 UTC."


async def handle_contact(args: str, stores) -> ResponseIR:
    facts_used = []
    blocks = [HeadingBlock(text="Contact Ciphex")]

    general_email = stores.facts.get("links.general_inquiries_email")
    if general_email is not None and not general_email.is_unknown:
        blocks.append(
            FactBlock(
                label="General inquiries",
                value=str(general_email.value),
                source=general_email.source_url,
                as_of=str(general_email.verified_on),
            )
        )
        facts_used.append("links.general_inquiries_email")
    else:
        blocks.append(ParagraphBlock(md=f"General inquiries: {_GENERAL_EMAIL_FALLBACK}"))

    partnerships_email = stores.facts.get("links.partnerships_email")
    if partnerships_email is not None and not partnerships_email.is_unknown:
        blocks.append(
            FactBlock(
                label="Partnerships",
                value=str(partnerships_email.value),
                source=partnerships_email.source_url,
                as_of=str(partnerships_email.verified_on),
            )
        )
        facts_used.append("links.partnerships_email")
    else:
        blocks.append(ParagraphBlock(md=f"Partnerships: {_PARTNERSHIPS_EMAIL_FALLBACK}"))

    sla = stores.facts.get("links.contact_response_sla")
    if sla is not None and not sla.is_unknown:
        sla_sentence = str(sla.value)
        facts_used.append("links.contact_response_sla")
    else:
        sla_sentence = _DEFAULT_SLA_SENTENCE
    blocks.append(ParagraphBlock(md=sla_sentence))

    contact_page = stores.facts.get("links.contact_page")
    if contact_page is not None and not contact_page.is_unknown:
        contact_page_url = str(contact_page.value)
        facts_used.append("links.contact_page")
    else:
        contact_page_url = _CONTACT_PAGE_FALLBACK

    telegram = stores.facts.get("links.telegram")
    if telegram is not None and not telegram.is_unknown:
        telegram_url = str(telegram.value)
        facts_used.append("links.telegram")
    else:
        telegram_url = _TELEGRAM_FALLBACK

    blocks.append(
        WarningBlock(md="Ciphex will never DM you first or ask for your seed phrase.")
    )
    blocks.append(
        LinksBlock(
            items=[
                LinkItem(label="Contact form", url=contact_page_url),
                LinkItem(label="Telegram", url=telegram_url),
            ]
        )
    )
    blocks.append(related_footer(("help", "all commands")))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
