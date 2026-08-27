"""D-THE-NORMALISER-DROPS-ARTICLES-BUT-NOT-HYPHENS.

THE DEFECT. `_answer_norm` strips articles from both sides of a synonym match and leaves
hyphens alone, so the compound form a careful writer actually uses cannot reach the tool.
Measured against the deployed matcher over the live catalogue, one character apart:

    'Run the golden-rules validation on my plan for this book'
        answerable = {book_steering_list}          plan_validate NOT answerable
    'Run the golden rules validation on my plan for this book'
        answerable = {plan_validate, ...}          plan_validate answerable

`plan_validate` declares the synonym "golden rules". The hyphenated form is the one a careful
writer uses for a compound modifier, and it is the one that failed.

🔴 IT COST A WHOLE K=5 LIVE BATCH, AND THE BATCH LOOKED FINE. Zero errors, 0/5 called, 0/5
surfaced — a clean-looking run that measured nothing, because the tool was never on the wire.
A zero-error batch is not a working batch.

THE INVARIANT: a request that uses a tool's declared synonym must reach that tool, whatever
ordinary punctuation the author wrote it with.

🔴 AND THE WIDENING WAS MEASURED BEFORE IT WAS WRITTEN, because widening THIS function is the
thing that manufactured the ties. Stripping ARTICLES collapsed "write chapter" / "write A
chapter" / "write THE chapter" into one string and destroyed the create/edit distinction their
authors had drawn. Over the 1,194 synonyms of the 199 LIVE tools: 13 colliding normalised
synonyms before, 13 after, ZERO new collisions. And underscores are deliberately excluded — see
`test_an_underscore_is_still_a_boundary_because_a_tool_name_is_an_identifier`.
"""
from __future__ import annotations

import pytest

from app.services.tool_surface import _answer_norm, answerable_tools


def _tool(name: str, synonyms: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": f"{name} does a thing.",
        "parameters": {"type": "object", "properties": {}},
        "_meta": {"tier": "R", "scope": "book", "synonyms": synonyms},
    }}


# ── the instance ───────────────────────────────────────────────────────────────────────────

def test_the_hyphenated_compound_reaches_the_tool_that_declared_it_spaced():
    """🔴 THE ORIGINAL INSTANCE, in the words the scenario actually used."""
    cat = [_tool("plan_validate", ["validate plan", "check spec", "golden rules"]),
           _tool("book_steering_list", ["steering", "book steering"])]
    hyphen = "Run the golden-rules validation on my plan for this book."
    spaced = "Run the golden rules validation on my plan for this book."
    assert "plan_validate" in answerable_tools(spaced, cat), (
        "the spaced form no longer matches — the fixture, not the fix, is wrong"
    )
    assert "plan_validate" in answerable_tools(hyphen, cat), (
        "the hyphenated compound still cannot reach a tool that declares it spaced"
    )


def test_a_synonym_DECLARED_with_a_hyphen_is_reachable_from_the_spaced_form():
    """The other direction, and it is not hypothetical: 10 live synonyms are declared with a
    hyphen — `co-write`, `re-translate changed`, `un-index chapter`, `reverse-engineer arc`."""
    cat = [_tool("composition_generate", ["co-write", "write chapter"])]
    for phrasing in ("Can you co-write this with me?", "Can you co write this with me?"):
        assert "composition_generate" in answerable_tools(phrasing, cat), phrasing


@pytest.mark.parametrize("raw, expected", [
    ("golden-rules", "golden rules"),
    ("co-write", "co write"),
    ("re-translate changed", "re translate changed"),
    ("world-building", "world building"),
    ("GOLDEN-RULES", "golden rules"),
    ("multi--dash", "multi dash"),
])
def test_every_dash_becomes_a_word_break(raw, expected):
    assert _answer_norm(raw) == expected


def test_the_unicode_dashes_are_covered_too():
    """An em dash is how an author separates clauses, and it arrives in real prompts —
    'Write chapter — draft the prose for …' is a measured one. Treating it as a letter would
    glue two words together that the author kept apart."""
    assert _answer_norm("Chapter I — The Ember Codex") == "chapter i ember codex"
    assert _answer_norm("world–building") == "world building"   # en dash
    assert _answer_norm("world—building") == "world building"   # em dash


# ── what must NOT change ───────────────────────────────────────────────────────────────────

def test_an_underscore_is_still_a_boundary_because_a_tool_name_is_an_identifier():
    """🔴 THE CONTROL THAT REFUTED THE OBVIOUS VERSION OF THIS FIX.

    Collapsing `_` as well as `-` is the natural generalisation and it is WRONG.
    `_exact_name_pattern` guards a tool name with `(?<![a-z0-9_])` precisely because a name is
    an identifier — its own docstring records `book_list` matching inside `book_list_chapters`
    before it shipped. Turning `_` into a space makes that boundary a space and the bug
    returns.

    Measured over the live tool names: hyphen-only leaves 0 names matching inside another name;
    hyphen AND underscore produces 3 — `book_list` inside `composition_motif_book_list`, and
    `world_map_update` inside `world_map_update_marker` and `_region`. The last is a tool this
    ledger already records reporting a write it never made, so the broader fix would have
    dragged a destructive sibling onto the wire to solve a punctuation problem."""
    assert _answer_norm("plan_validate") == "plan_validate"
    assert _answer_norm("book_list") == "book_list"

    cat = [_tool("book_list", ["list books"]),
           _tool("composition_motif_book_list", ["list motif books"])]
    got = answerable_tools("Please use the composition_motif_book_list tool.", cat)
    assert got == {"composition_motif_book_list"}, (
        f"naming the longer tool also dragged in its shorter sibling: {sorted(got)}"
    )


def test_the_article_stripping_it_lives_beside_is_unchanged():
    """This function's OTHER job. A regression here would be the v1 incident again: 'update the
    description of my book' failing to match the declared 'update description' on an article."""
    assert _answer_norm("update the description of my book") == "update description book"


def test_a_request_naming_nothing_still_forces_nothing():
    """Chitchat must stay empty — the widening must not make everything match everything."""
    cat = [_tool("plan_validate", ["validate plan", "golden rules"]),
           _tool("composition_generate", ["co-write"])]
    assert answerable_tools("How are you today?", cat) == set()
    assert answerable_tools("", cat) == set()
    assert answerable_tools(None, cat) == set()


def test_the_widening_does_not_collapse_two_distinct_synonyms_into_one():
    """The precision property, asserted on the shape that would prove it broken: two tools whose
    declared synonyms differ ONLY by a hyphen would become indistinguishable. Measured over the
    live catalogue this happens zero times — 13 colliding phrases before and after — and this
    test pins the reasoning so a future widening has to re-measure rather than assume."""
    a, b = _answer_norm("co-write"), _answer_norm("co write")
    assert a == b, "the two forms must unify — that is the whole point"
    # …but a genuinely different phrase must NOT collapse into them.
    assert _answer_norm("cowrite") != a, (
        "removing the hyphen entirely (rather than making it a break) would fuse 'cowrite' with "
        "'co write' — a wider change than was measured, and not what shipped"
    )
