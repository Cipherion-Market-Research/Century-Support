"""Telegram channel adapter for Century Core (WP-6a).

Standalone deployable service: translates Telegram webhook updates into the
frozen C1 message envelope, POSTs to Century Core's `/v1/messages`, and
renders the C2 response IR back into Telegram MarkdownV2. See
docs/CONTRACTS.md for the frozen contracts this package implements against.

This package never calls the LLM, never formats facts locally, and never
calls the per-key facts lookup endpoint on a user's behalf -- rendering
only (see core_client.py and its accompanying test for the enforced
guarantee).
"""
