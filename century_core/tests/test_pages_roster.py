"""Tests for century_core/qa/pages_roster.py (Sprint 3 team-member roster
route). Most tests use a small SYNTHETIC markdown fixture, matching the
harvested leadership-team.md's structural shape (name / tier chip / role /
3 credential lines, blank-line separated) -- so they don't depend on the
live-harvested page's actual current roster and stay stable across future
re-harvests. A separate section at the bottom locks in the exact
regression queries from the Sprint 3 brief against the REAL harvested
file, since those are about today's real roster (Kevin O'Brien).
"""
from century_core import response_guard
from century_core.qa.pages_roster import (
    answer_person_question,
    get_roster,
    is_person_question,
    parse_leadership_markdown,
)

_SYNTHETIC_MD = """<!--
source_url: https://ciphex.io/leadership-team
fetched: 2026-08-26
page_title: Test Leadership Page
kind: site page copy (harvested via git show, scripts/harvest_pages.py)
-->

# Test Leadership Page

Ciphex Leadership Team

Ciphex is Built on Decades of Real World Capital Markets and Technology Expertise

100+

More than 100 years of combined professional expertise.

Leadership

A proven track record in Finance, Innovation, and Execution.

Ada Lovelace

Ecosystem

Systems Architecture

20 YRS. Analytical Engine Design

10 YRS. Computational Theory

5 YRS. Technical Writing

Grace Hopper

Ecosystem

Compiler Design

25 YRS. Programming Languages

15 YRS. Naval Systems

10 YRS. Standards Development

Alan Turing

Contributor

Cryptography

30 YRS. Computation Theory

20 YRS. Cryptanalysis

10 YRS. Machine Intelligence
"""


def test_parse_leadership_markdown_extracts_all_people_in_order():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    names = [p.full_name for p in roster.people]
    assert names == ["Ada Lovelace", "Grace Hopper", "Alan Turing"]


def test_parse_leadership_markdown_extracts_fields():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    ada = roster.people[0]
    assert ada.first_name == "Ada"
    assert ada.tier == "Ecosystem"
    assert ada.role == "Systems Architecture"
    assert ada.credentials == (
        "20 YRS. Analytical Engine Design",
        "10 YRS. Computational Theory",
        "5 YRS. Technical Writing",
    )


def test_parse_leadership_markdown_extracts_years_summary():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    assert "100" in roster.years_summary
    assert "combined" in roster.years_summary.lower()


def test_parse_leadership_markdown_empty_text_yields_empty_roster():
    roster = parse_leadership_markdown("")
    assert roster.people == ()


def test_is_person_question_matches_full_name():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    assert is_person_question("tell me about Ada Lovelace", roster)


def test_is_person_question_matches_first_name_only():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    assert is_person_question("who is Ada?", roster)


def test_is_person_question_matches_apostrophe_insensitive():
    # Real-world case is "Kevin O'Brien" (straight) vs "Kevin O’Brien"
    # (curly, as harvested) -- exercised here with a synthetic name-alike
    # to keep this test independent of the live roster.
    roster = parse_leadership_markdown(_SYNTHETIC_MD.replace("Ada Lovelace", "Ada O’Toole"))
    assert is_person_question("tell me about Ada O'Toole", roster)


def test_is_person_question_matches_team_phrase_without_a_name():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    assert is_person_question("who is the ciphex leadership team?", roster)
    assert is_person_question("how experienced is the leadership team?", roster)


def test_is_person_question_requires_an_intent_word():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    # "Ada" appears, but no who/about/tell/background/experience/bio word.
    assert not is_person_question("Ada Lovelace CPX token", roster)


def test_is_person_question_false_for_unknown_name():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    assert not is_person_question("tell me more about Steve Martin", roster)


def test_is_person_question_false_against_empty_roster():
    empty_roster = parse_leadership_markdown("")
    assert not is_person_question("who is the ciphex leadership team?", empty_roster)


def test_is_person_question_does_not_swallow_unrelated_questions():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    assert not is_person_question("what is the total supply of CPX", roster)


def test_answer_person_question_single_match_cites_leadership_page():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    response = answer_person_question("who is Grace?", roster)
    assert response.meta.answer_kind == "faq"
    para = next(b for b in response.blocks if b.type == "paragraph")
    assert "Grace Hopper" in para.md
    assert "Compiler Design" in para.md
    links = next(b for b in response.blocks if b.type == "links")
    assert links.items[0].url == "https://ciphex.io/leadership-team"


def test_answer_person_question_ambiguous_first_name_lists_all_matches():
    ambiguous_md = _SYNTHETIC_MD.replace("Alan Turing", "Alan Kay")  # still distinct names
    # Force an actual collision: two "Alan"s.
    ambiguous_md = ambiguous_md + "\n\nAlan Perlis\n\nContributor\n\nProgramming Languages\n\n15 YRS. Language Design\n\n10 YRS. Compiler Theory\n\n5 YRS. Academia\n"
    roster = parse_leadership_markdown(ambiguous_md)
    response = answer_person_question("who is Alan?", roster)
    para = next(b for b in response.blocks if b.type == "paragraph")
    assert "Alan Kay" in para.md
    assert "Alan Perlis" in para.md


def test_answer_person_question_team_phrase_lists_everyone():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    response = answer_person_question("who is the ciphex leadership team?", roster)
    para = next(b for b in response.blocks if b.type == "paragraph")
    assert "Ada Lovelace" in para.md
    assert "Grace Hopper" in para.md
    assert "Alan Turing" in para.md


def test_answer_person_question_passes_response_guard():
    roster = parse_leadership_markdown(_SYNTHETIC_MD)
    response = answer_person_question("who is Ada?", roster)
    guarded = response_guard.enforce_response(response)
    assert guarded.blocks  # not stripped down to a refusal
    assert guarded.meta.answer_kind == "faq"


# ─────────────────── regression queries against the REAL harvested file ───────────────────
# Sprint 3 brief: these exact phrasings must answer with real content
# (today's roster includes Kevin O'Brien), and "Steve Martin" must not
# match -- these lock in that behavior against the live corpus, in
# addition to the synthetic-fixture tests above.


def test_real_roster_who_is_kevin():
    roster = get_roster()
    if not roster.people:
        return  # environment without the harvested corpus checked out
    assert is_person_question("Who is Kevin?", roster)


def test_real_roster_tell_me_more_about_kevin_obrien():
    roster = get_roster()
    if not roster.people:
        return
    assert is_person_question("tell me more about Kevin O'Brien", roster)
    response = answer_person_question("tell me more about Kevin O'Brien", roster)
    para = next(b for b in response.blocks if b.type == "paragraph")
    assert "Kevin" in para.md


def test_real_roster_who_is_the_leadership_team():
    roster = get_roster()
    if not roster.people:
        return
    assert is_person_question("who is the ciphex leadership team?", roster)


def test_real_roster_how_experienced_is_the_leadership_team():
    roster = get_roster()
    if not roster.people:
        return
    assert is_person_question("How experienced is the leadership team?", roster)


def test_real_roster_steve_martin_does_not_match():
    roster = get_roster()
    if not roster.people:
        return
    assert not is_person_question("tell me more about Steve Martin", roster)
