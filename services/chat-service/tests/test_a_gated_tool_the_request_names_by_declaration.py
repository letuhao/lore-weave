"""DQ-T31 — the world-setup gate opens on VOCABULARY, not on what the request asks for.

THE DEFECT, in two directions on one function.

  SHUT WHEN IT SHOULD OPEN. `glossary_book_sync_apply` declares the synonyms "apply the
  standard updates" and "take the upstream changes". Asked *"Take the upstream changes — apply
  the standard updates to this book"* — two of them VERBATIM — it is, against the live
  catalogue, the ONLY answerable tool with no competitor. It surfaced 0/2 and was called 0/2,
  because `_is_world_setup_intent` is a substring match over a hand-written marker list and
  none of those words is a marker.

  OPEN WHEN IT SHOULD NOT. `codex` IS a marker, so *"draft the prose for 'Chapter I — The Ember
  Codex'"* opens the gate on a pure prose turn. The gate fires on 11 of 186 corpus prompts and
  at least one of those is that.

WHY A LONGER MARKER LIST IS NOT THE FIX, in the row's own words: "Widening the markers to fix
the SHUT-side failures would enlarge this side too."

AND WHY R1 COULD NOT RESCUE IT. R1 answerability promises a tool whose declared vocabulary
answers the request a place on the wire "whatever the budget, the domain selection or the rail
decided". For a gated tool it cannot deliver, through no fault of its own: the ONE-OFF build is
handed the UNFILTERED catalog and R1 does force the tool in there, but the PER-PASS build is
handed the catalog AFTER the gate and REPLACES that list on the first pass. The rescue lands in
a list that is immediately discarded. The only place it can be fixed is before the removal.

THE INVARIANT (owner decision, 2026-08-27): a gated tool whose OWN declared synonyms answer the
request is exempt from the gate — and only that tool. Per-TOOL, never per-turn, the same scoping
the `rail_step_tools` exemption already uses on the same principle: guidance and capability move
as one signal.
"""
from __future__ import annotations

import pytest

from app.services import instrument
from app.services.tool_discovery import (
    INTENT_GATED_SETUP_TOOLS,
    SETUP_INTENT_SKILL,
    filter_intent_gated_setup_tools,
    tool_name,
)


@pytest.fixture(autouse=True)
def _no_instrument_residue():
    """🔴 THIS FILE BROKE FOUR UNRELATED `test_cp0_instrument` CASES BEFORE IT HAD THIS, AND THE
    REPO HAD ALREADY PAID FOR THE LESSON ONCE.

    `filter_intent_gated_setup_tools` RECORDS what it withheld, and `record_surface_withheld`
    opens a sink when none is armed — so every call here leaves rows in the ambient ContextVar.
    `arm_turn_surface` then ADOPTS that sink rather than replacing it, deliberately, because a
    narrowing that predates its sink is lost rather than late. In production the adopt is safe:
    each request runs in its own task and therefore its own context copy. Under pytest, sync
    tests share one context, so this file's rows reached a later file's assertions.

    Green in isolation, red in the full run — which `arm_turn_surface`'s own comment names as
    "the signature of state leaking between turns rather than of a broken assertion". The
    isolation is the ContextVar's own save/restore, copied from
    test_a_withheld_setup_tool_is_not_reported_as_absent.py, which hit the SAME four tests.
    """
    token = instrument.surface_withheld.set(None)
    try:
        yield
    finally:
        instrument.surface_withheld.reset(token)

#: The instance. Its real declared synonyms, copied from the registration.
SYNC_APPLY = "glossary_book_sync_apply"


def _tool(name: str, synonyms: list[str], desc: str = "") -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc or f"{name} does a thing.",
        "parameters": {"type": "object", "properties": {}},
        "_meta": {"tier": "W", "scope": "book", "synonyms": synonyms},
    }}


def _catalog() -> list[dict]:
    """A catalogue holding the gated tools plus ordinary company."""
    gated = sorted(INTENT_GATED_SETUP_TOOLS)
    cat = [
        _tool(SYNC_APPLY, ["apply the standard updates", "take the upstream changes",
                           "sync the standards"]),
    ]
    cat += [_tool(n, [f"{n.replace('_', ' ')}"]) for n in gated if n != SYNC_APPLY]
    cat += [
        _tool("book_chapter_save_draft", ["write the chapter", "save the draft"]),
        _tool("composition_generate", ["write chapter", "cowrite"]),
    ]
    return cat


def _names(catalog: list[dict]) -> set[str]:
    return {tool_name(td) for td in catalog}


# ── the shut side: the request names the tool in the tool's own words ───────────────────────

@pytest.mark.parametrize("prompt", [
    "Take the upstream changes — apply the standard updates to this book.",
    "Apply the standard updates to this book.",
    "Take the upstream changes.",
])
def test_a_request_in_the_tools_own_declared_words_reaches_that_tool(prompt):
    """🔴 THE ORIGINAL INSTANCE. Two of these are the measured prompt and its halves; before
    this arm every one of them left the tool unseedable, unfindable AND unloadable."""
    kept = _names(filter_intent_gated_setup_tools(_catalog(), [], None, request_text=prompt))
    assert SYNC_APPLY in kept, (
        f"the request uses {SYNC_APPLY}'s own declared synonyms and the tool is still gated"
    )


def test_the_exemption_is_per_TOOL_and_never_per_turn():
    """🔴 IF THIS INVERTS, THE ARM BECOMES THE MARKER LIST IT REPLACED. Matching one gated
    tool must not un-gate the other four — that is exactly the over-reach N5a-FULL exists to
    stop, and exactly what widening the markers would have done."""
    kept = _names(filter_intent_gated_setup_tools(
        _catalog(), [], None,
        request_text="Take the upstream changes — apply the standard updates to this book."))
    assert SYNC_APPLY in kept
    others = (INTENT_GATED_SETUP_TOOLS - {SYNC_APPLY}) & _names(_catalog())
    assert others, "the fixture no longer holds any OTHER gated tool, so this proves nothing"
    assert not (others & kept), (
        f"matching one gated tool un-gated the rest: {sorted(others & kept)}"
    )


# ── the open side: what must still be refused ──────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "Write chapter — use the cowrite engine to draft the prose for 'Chapter I — The Ember Codex'.",
    "Rename the chapter called The Ember Codex in my outline to something shorter.",
    "Write the next chapter.",
    "How are you today?",
    "",
])
def test_a_turn_that_does_not_name_a_gated_tool_still_cannot_reach_one(prompt):
    """The over-reach guard, including the two prose prompts that the MARKER list opens on.

    Note what this does and does not claim: the declaration arm does not open on them. The
    marker list still does — `codex` remains a marker and `_is_world_setup_intent` is
    unchanged — which is a SEPARATE defect (D-A-CHAPTER-TITLE-OPENS-THE-WORLD-SETUP-GATE) and
    is deliberately not fixed here. What is proven is that the new arm adds no false
    positives of its own."""
    kept = _names(filter_intent_gated_setup_tools(_catalog(), [], None, request_text=prompt))
    assert not (INTENT_GATED_SETUP_TOOLS & kept), (
        f"a request naming no gated tool reached {sorted(INTENT_GATED_SETUP_TOOLS & kept)}"
    )


def test_a_near_miss_in_someone_elses_vocabulary_does_not_open_it():
    """'write the chapter' is book_chapter_save_draft's declared synonym, not a gated tool's.
    The arm reads the GATED tool's declaration and nothing else."""
    kept = _names(filter_intent_gated_setup_tools(
        _catalog(), [], None, request_text="Write the chapter and save the draft."))
    assert not (INTENT_GATED_SETUP_TOOLS & kept)


# ── nothing that already worked may change ─────────────────────────────────────────────────

def test_no_request_text_is_byte_identical_to_before():
    """The default. Every caller that does not pass `request_text` must get the old behaviour
    exactly — not approximately."""
    cat = _catalog()
    for arg in (None, ""):
        kept = _names(filter_intent_gated_setup_tools(cat, [], None, request_text=arg))
        assert not (INTENT_GATED_SETUP_TOOLS & kept)
    assert _names(filter_intent_gated_setup_tools(cat, [], None)) == _names(
        filter_intent_gated_setup_tools(cat, [], None, request_text=None))


def test_a_setup_intent_turn_still_returns_the_catalog_unchanged():
    """The skill-injected path short-circuits ABOVE the new arm and must keep doing so."""
    cat = _catalog()
    out = filter_intent_gated_setup_tools(cat, [SETUP_INTENT_SKILL], None,
                                          request_text="anything at all")
    assert out is cat, "the setup-intent short circuit no longer returns the catalog identically"


def test_the_rail_exemption_still_works_and_composes():
    """`rail_step_tools` is the precedent this arm was built on; it must not be displaced."""
    victim = sorted(INTENT_GATED_SETUP_TOOLS & _names(_catalog()) - {SYNC_APPLY})[0]
    kept = _names(filter_intent_gated_setup_tools(
        _catalog(), [], {victim},
        request_text="Take the upstream changes — apply the standard updates to this book."))
    assert victim in kept, "the rail exemption stopped working"
    assert SYNC_APPLY in kept, "the declaration arm and the rail exemption do not compose"


def test_a_gated_tool_absent_from_the_catalog_cannot_be_conjured():
    """The arm EXEMPTS from a removal; it never adds. A tool the catalogue does not hold must
    not appear because the request happened to name it."""
    cat = [td for td in _catalog() if tool_name(td) != SYNC_APPLY]
    kept = _names(filter_intent_gated_setup_tools(
        cat, [], None,
        request_text="Take the upstream changes — apply the standard updates to this book."))
    assert SYNC_APPLY not in kept


# ── the withheld record must tell the truth ────────────────────────────────────────────────

def test_an_exempted_tool_is_not_reported_as_withheld():
    """`record_surface_withheld` is what P1's accounting reads. A tool that WAS offered must
    not also be recorded as narrowed away, or the surface record contradicts the surface."""
    from app.services import instrument

    sink: list = []
    token = instrument.surface_withheld.set(sink)
    try:
        filter_intent_gated_setup_tools(
            _catalog(), [], None,
            request_text="Take the upstream changes — apply the standard updates to this book.")
    finally:
        instrument.surface_withheld.reset(token)
    withheld = {r.get("tool") for r in sink if isinstance(r, dict)}
    assert SYNC_APPLY not in withheld, (
        "the tool was exempted and still recorded as withheld at intent_gate"
    )
    assert withheld, "nothing was recorded as withheld — the other gated tools should still be"
