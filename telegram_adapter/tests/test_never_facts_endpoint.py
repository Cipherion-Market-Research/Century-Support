"""Owner hard rule: this adapter must never call GET /v1/facts/:key on a
user's behalf -- that would let a channel bypass every guardrail Century
Core enforces before a number reaches a user. Statically verified two
ways: (1) grep every source file in the package for the forbidden route,
and (2) confirm the only Century Core path core_client.py builds is
`/v1/messages`.
"""
import pathlib

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent

_SOURCE_FILES = [
    p
    for p in PACKAGE_ROOT.rglob("*.py")
    if "tests" not in p.parts  # this file itself legitimately names the forbidden route
]


def test_no_source_file_constructs_the_facts_endpoint():
    forbidden = "/v1/facts"
    offenders = []
    for path in _SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        if forbidden in text:
            offenders.append(str(path))
    assert offenders == [], f"forbidden route referenced in: {offenders}"


def test_core_client_only_ever_posts_to_v1_messages():
    from telegram_adapter import core_client

    assert core_client._MESSAGES_PATH == "/v1/messages"

    source = pathlib.Path(core_client.__file__).read_text(encoding="utf-8")
    # The only two literal Century Core route fragments anywhere in
    # core_client.py: the module-level constant above, and nothing else.
    assert source.count('"/v1/') == 1
