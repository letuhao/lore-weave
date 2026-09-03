"""D-LAZY-TAIL-UNUSED — the model must be told the advertised set is a SUBSET.

MEASURED 2026-08-14 across 30 live runs of five ordinary authoring requests: `tool_list` was
called ONCE and `tool_load` NEVER — with both advertised on every single run. The lazy tail the
whole surfacing design leans on was not a fallback in practice; whatever the deterministic
pre-filter put on the wire was the entire reachable catalogue for that turn.

Nothing told the model otherwise. The advertised set was presented as simply "the tools", so a
model that could not find one did the reasonable thing with what it had — and that is the failure
this loop keeps finding in both directions: answer from the context block (a review queue of ONE
reported as three), or reach for the nearest write that IS on the wire (three chapters created by
a read question).

🔴 THE SCENT WAS DEPLOYED AND REFUTED. Same fixture, K=3: the model stopped answering from
nothing and called a tool — `glossary_search`, which returns EVERY entity — and reported three
again. It satisfied "call something" by calling the wrong thing, because the right thing was not
on the wire. Three prose interventions now, zero tool_list calls in 39 runs.

It is NOT applied to the note. These tests pin its CONTENT so the negative result stays legible,
and `test_it_is_not_applied` pins the decision so it cannot drift back in without a new
measurement.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import _DISCOVERY_SCENT, _ORIENTATION_SCENT  # noqa: E402


def test_it_says_the_surface_is_partial():
    s = _DISCOVERY_SCENT.lower()
    assert "subset" in s, "the model must know the advertised set is not everything"


def test_it_names_the_way_out():
    assert "tool_list" in _DISCOVERY_SCENT
    assert "tool_load" in _DISCOVERY_SCENT


def test_it_forbids_answering_a_data_question_with_no_tool_call():
    """The load-bearing clause. Discovery is the mechanism; this is the rule that makes not
    discovering visible — a count or a list given without a tool call is the shape of every
    incident in the ledger."""
    s = _DISCOVERY_SCENT.lower()
    assert "never answer a question about the user's own data" in s
    assert "when no tool returned it" in s


def test_it_is_short_enough_to_carry_every_turn():
    """It rides on every book turn, so its cost is paid every turn. ~70 tokens is the budget this
    was justified at; a paragraph that grows without measurement is how a prefix bloats."""
    assert len(_DISCOVERY_SCENT.split()) < 110


def test_it_does_not_duplicate_the_orientation_scent():
    """Two scents on the same note must not say the same thing twice — the orientation scent names
    three composition READS, this one names the discovery path."""
    assert "tool_list" not in _ORIENTATION_SCENT


def test_it_is_not_applied():
    """The measurement refused it. Prose does not move this model off the advertised surface, and
    a ~70-token rider on every book turn with no measured benefit is a cost, not a fix. If someone
    re-applies it, they owe a run that shows tool_list firing."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"
    text = src.read_text(encoding="utf-8")
    assert "book_context_note += _DISCOVERY_SCENT" not in text
