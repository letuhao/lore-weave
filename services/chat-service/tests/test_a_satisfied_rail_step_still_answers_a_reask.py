"""D-RAIL-DONE-SUPPRESSES-THE-REREAD — a finished journey must not take the answer off the wire.

MEASURED LIVE 2026-08-14, four sessions (019ffff4, 01a00003, 01a00004, 01a00005), K=3, on
throwaway books seeded with TWO active canon rules.

  Turn 1  "What canon rules have I declared for this book?"
          -> composition_list_canon_rules RAN. Both rules reported. Correct.

  Turn 2  "Remind me again — what canon rules do I have on this book right now?"
          -> composition_list_canon_rules WITHHELD on every pass (14 of them in one session):

                 stage  = rail_gate
                 reason = "rail step already satisfied (mode=done_suppress)"

             The model then called composition_list_derivatives x5, composition_list_outline x5,
             composition_get_derivative_context x2 — hunting for the tool that answers — and
             finally answered from conversation memory.

This is DQ-T30's mechanism, and it is sharper than the DQ's own wording. The DQ says a completed
rail "correctly stops driving, and the model then answers from conversation memory". The measured
truth is worse: the completed rail actively REMOVES the answering read from the action space, so
answering from memory is the only move the model has left.

THE INVARIANT: a rail step being satisfied means the rail need not DRIVE it again; it must never
mean the author may no longer ASK.

The gate conflates two claims that coincide only for a WRITE. "Done" -> a second write duplicates
data, so drop it. For a READ there is nothing to duplicate: re-reading IS the freshness the author
asked for.

WHY THIS IS SEPARATE FROM THE DQ-T30 GUARD. That guard notices the turn answered without reading
and nudges. It cannot help while the tool is off the wire — measured directly: with the guard
shipped and the tool rail-gated, it fired 3/3, named the tool, and the model still could not call
it, taking the honest-disclosure branch instead. Two defects, one symptom.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")


def _gate_window() -> str:
    """The rail-gate union site — the ONE chokepoint where the gate joins the suppressors."""
    i = SRC.index("_rail_suppress = rail_gate_suppressions(")
    return SRC[i:i + 4600]


def test_a_rail_gated_answering_read_is_reclaimed():
    """THE FALSIFIER. Without this the re-ask cannot reach the tool that answers it."""
    w = _gate_window()
    assert "_reclaimed_reads = {" in w
    assert "_rail_suppress = set(_rail_suppress) - _reclaimed_reads" in w


def test_only_reads_are_reclaimed():
    """A WRITE whose step is done must STAY suppressed — dropping that is how a finished journey
    writes twice, which is the whole reason the gate exists."""
    w = _gate_window()
    assert 'tool_tier(cat_index[n]) == "R"' in w


def test_reclaim_requires_the_tool_to_declare_this_request():
    """Not every done read comes back — only one whose OWN declared vocabulary answers the words
    actually typed. A blanket reclaim would undo the intra-turn repeat killer the gate exists to
    be, and this loop has already shipped one guard that dragged a turn onto unasked-for work."""
    w = _gate_window()
    assert "answerable_tools(request_text, [cat_index[n]])" in w


def test_the_loop_breakers_still_win():
    """ORDERING IS THE SAFETY PROPERTY. `failure_suppress` (gave up after repeated errors) and
    `repeat_read_suppress` (hammering the same read) describe a model misbehaving RIGHT NOW; the
    rail gate describes a journey that finished earlier. The reclaim must happen BEFORE the
    breakers are unioned in, so a reclaimed read that is ALSO being hammered stays suppressed."""
    w = _gate_window()
    r = w.index("_reclaimed_reads = {")
    for breaker in ("failure_suppress", "repeat_read_suppress"):
        u = w.index("_suppress = set(_suppress) | " + breaker)
        assert r < u, (
            "the " + breaker + " union must come AFTER the reclaim, or a genuine loop breaker "
            "could be undone by answerability"
        )


def test_the_reclaim_is_logged():
    """A surface decision that silently reverses another is how the last three days of this loop
    were spent debugging. Name it."""
    assert "rail gate: reclaiming %s" in _gate_window()
