"""Phase G · G1 — the rail DRIVE decision (`_maybe_redrive_rail`).

The pure enforcement primitives (caps, escape hatch, honest give-up) live in test_rail_progress.py.
This covers the redrive selector that the stream loop calls between model iterations: given a FRESH
book-state probe, it returns the next drivable step — and it must SKIP a step the enforcement has
already given up on (`nudged_out`), so a defiant model degrades to an honest stop, never a loop.

The full hold/release effect (a REQUIRED unmet step holding a live turn, an explicit "skip"
releasing it) is proven live in G5's in-container S06 run — the stream generator is not unit-driven.
"""
from __future__ import annotations

from collections import Counter

import pytest

import app.services.book_state_probe as probe_mod
from app.services.rail_progress import BookState
from app.services.stream_service import _maybe_redrive_rail

PLANNING = [
    {"id": "propose", "tool": "plan_propose_spec", "done_when": "plan > 0"},
    {"id": "compile", "tool": "plan_compile", "done_when": "structure_fresh > 0"},
]


def _fixed_probe(state: BookState):
    async def _p(book_id, caller_user_id):
        return state
    return _p


async def test_redrive_picks_the_compile_step_when_propose_is_done(monkeypatch):
    # Propose landed (plan=1) but nothing compiled (structure_fresh=0) — the drivable next step is
    # the compile, exactly the S06 gap the rail must now push through.
    monkeypatch.setattr(probe_mod, "probe_book_state", _fixed_probe(BookState(plan=1, structure_fresh=0)))
    got = await _maybe_redrive_rail(
        [("planning", PLANNING)], "book", "user",
        turn_start_counts={}, turn_succeeded=Counter({"plan_propose_spec": 1}),
        async_tools=frozenset(), nudged_out=set(),
    )
    assert got is not None
    slug, step = got
    assert slug == "planning" and step.step_id == "compile" and step.tool == "plan_compile"


async def test_redrive_skips_a_step_that_enforcement_gave_up_on(monkeypatch):
    # Same state, but the compile step is in nudged_out (the bounded auto-release already fired) —
    # the redrive must NOT return it again, so the turn ends honestly instead of looping forever.
    monkeypatch.setattr(probe_mod, "probe_book_state", _fixed_probe(BookState(plan=1, structure_fresh=0)))
    got = await _maybe_redrive_rail(
        [("planning", PLANNING)], "book", "user",
        turn_start_counts={}, turn_succeeded=Counter({"plan_propose_spec": 1}),
        async_tools=frozenset(), nudged_out={"compile"},
    )
    assert got is None


async def test_redrive_returns_none_when_the_rail_is_complete(monkeypatch):
    # Both effects satisfied → nothing to drive.
    monkeypatch.setattr(probe_mod, "probe_book_state", _fixed_probe(BookState(plan=1, structure_fresh=2)))
    got = await _maybe_redrive_rail(
        [("planning", PLANNING)], "book", "user",
        turn_start_counts={}, turn_succeeded=Counter({"plan_propose_spec": 1, "plan_compile": 1}),
        async_tools=frozenset(), nudged_out=set(),
    )
    assert got is None
