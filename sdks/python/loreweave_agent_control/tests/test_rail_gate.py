"""Action-space GATING (2026-07-26) — `rail_gate_suppressions`.

Binds the rail's computed progress into the advertised tool set: a finished step's tool is
dropped from the wire so a weak model cannot repeat it (the glossary_propose_entities ×8 /
kg_project_create ×57 loops). These tests pin every mode + the edge cases that make the gate
safe: a `repeat` step is never gated, a tool still owed by a not-done step survives, a
this-turn success advances the gate intra-turn, and a tool reused across two steps consumes
successes in order.
"""
from __future__ import annotations

from collections import Counter

from loreweave_agent_control import (
    GATE_DONE_SUPPRESS,
    GATE_OFF,
    GATE_STEP_LOCK,
    RailProgress,
    StepProgress,
    rail_gate_suppressions,
)
from loreweave_agent_control.rail import BookState


def _step(
    i: int, tool: str, done: bool, *, repeat: bool = False, session: bool | None = None,
) -> StepProgress:
    """`done` is the BOOK's verdict; `session` is "this chat performed it".

    `session` defaults to `done` so the step_lock/resume tests keep reading naturally. The
    done_suppress tests below set it EXPLICITLY, because the whole point of the split is that
    the two can disagree — and when they do, only the session verdict may take a tool away.
    """
    return StepProgress(
        index=i, step_id=f"s{i}", tool=tool, done=done, reason="", repeat=repeat,
        session_done=done if session is None else session,
    )


def _prog(steps: list[StepProgress], next_index: int | None) -> RailProgress:
    return RailProgress(slug="demo", steps=steps, next_index=next_index, state=BookState())


# ── off ───────────────────────────────────────────────────────────────────────

def test_off_never_suppresses():
    prog = _prog([_step(1, "a", True), _step(2, "b", False)], 2)
    assert rail_gate_suppressions([prog], set(), GATE_OFF) == set()


def test_empty_progress_is_a_noop():
    assert rail_gate_suppressions(None, set(), GATE_DONE_SUPPRESS) == set()
    assert rail_gate_suppressions([], {"a"}, GATE_STEP_LOCK) == set()


# ── done_suppress ──────────────────────────────────────────────────────────────

def test_done_suppress_drops_a_finished_step_tool():
    prog = _prog([_step(1, "a", True, session=True), _step(2, "b", False)], 2)
    assert rail_gate_suppressions([prog], set(), GATE_DONE_SUPPRESS) == {"a"}


def test_done_suppress_keeps_a_repeat_step_even_when_done():
    # a legitimately-batched step (repeat) must stay callable after one success
    prog = _prog([_step(1, "a", True, repeat=True, session=True), _step(2, "b", False)], 2)
    assert rail_gate_suppressions([prog], set(), GATE_DONE_SUPPRESS) == set()


def test_done_suppress_keeps_a_tool_still_owed_by_a_not_done_step():
    # tool "a" is done in step 1 but reused (not yet done) in step 3 → must NOT be dropped
    prog = _prog(
        [_step(1, "a", True, session=True), _step(2, "b", True, session=True),
         _step(3, "a", False)], 3
    )
    supp = rail_gate_suppressions([prog], set(), GATE_DONE_SUPPRESS)
    assert "a" not in supp
    assert supp == {"b"}


def test_done_suppress_advances_intra_turn_on_a_this_turn_success():
    # turn-start: step 1 not done. A success THIS turn (turn_succeeded) must gate it now —
    # this is the intra-turn repeat killer (glossary ×8 within one turn).
    prog = _prog([_step(1, "a", False), _step(2, "b", False)], 1)
    assert rail_gate_suppressions([prog], Counter({"a": 1}), GATE_DONE_SUPPRESS) == {"a"}


def test_done_suppress_two_steps_same_tool_need_two_successes():
    # tool "a" is used by step 1 AND step 2; one success advances only step 1, so "a" is still
    # owed by step 2 → not dropped yet.
    prog = _prog([_step(1, "a", False), _step(2, "a", False), _step(3, "b", False)], 1)
    assert rail_gate_suppressions([prog], Counter({"a": 1}), GATE_DONE_SUPPRESS) == set()
    # two successes advance both → "a" fully done, dropped
    assert rail_gate_suppressions([prog], Counter({"a": 2}), GATE_DONE_SUPPRESS) == {"a"}


def test_a_step_DONE_IN_THE_BOOK_but_not_in_THIS_CHAT_keeps_its_tool():
    """The Mị Đế bug, as a unit.

    The book has a plan (`done_when: "plan > 0"` holds — a run proposed 2026-07-29), so the
    step is durably done. This conversation has not proposed anything. Suppressing here is
    what left the author unable to plan a second arc: `plan_propose_spec` was off the wire in
    every later session, while `plan_compile`/`plan_run_pass` stayed on it, so the model
    invented a `run_id` to reach the tools it COULD see.

    A rail step is a thing this chat does. The book's own state may inform the model — the
    progress block already tells it "ALREADY DONE — do NOT repeat" — but it may not disarm it.
    """
    prog = _prog(
        [_step(1, "plan_propose_spec", True, session=False),
         _step(2, "b", False, session=False)],
        None,
    )
    assert rail_gate_suppressions([prog], set(), GATE_DONE_SUPPRESS) == set()


def test_the_same_step_IS_gated_once_THIS_CHAT_performs_it():
    """The control for the test above — the anti-loop guarantee must survive the fix.

    Same durable state; the difference is that this session's call log now carries the tool.
    Without this pair, "never suppress on book state" could be satisfied by never suppressing
    at all, and the ×8 repeat loops the gate was built for would come straight back.
    """
    prog = _prog(
        [_step(1, "plan_propose_spec", True, session=True), _step(2, "b", False, session=False)],
        None,
    )
    assert rail_gate_suppressions([prog], set(), GATE_DONE_SUPPRESS) == {"plan_propose_spec"}


def test_an_artifact_bearing_step_is_still_gated_intra_turn():
    """The regression the split could plausibly introduce, pinned.

    `compute_rail_progress` decides `done` for a step with `done_when` from the ARTIFACT and
    never consults the call log on that branch. So if `session_done` were derived as a
    fallback of that branch rather than computed independently, a step that lands its artifact
    would read session-undone forever and the model could call it all turn. It is computed
    independently; this asserts the consequence at the gate.
    """
    prog = _prog([_step(1, "a", True, session=False), _step(2, "b", False, session=False)], 1)
    assert rail_gate_suppressions([prog], Counter({"a": 1}), GATE_DONE_SUPPRESS) == {"a"}


# ── step_lock ──────────────────────────────────────────────────────────────────

def test_step_lock_advertises_only_the_current_step_tool():
    prog = _prog([_step(1, "a", True), _step(2, "b", False), _step(3, "c", False)], 2)
    # current is step 2 (b); a (done) and c (future) are both dropped
    assert rail_gate_suppressions([prog], set(), GATE_STEP_LOCK) == {"a", "c"}


def test_step_lock_advances_on_a_this_turn_success():
    prog = _prog([_step(1, "a", False), _step(2, "b", False), _step(3, "c", False)], 1)
    # a succeeded this turn → current advances to b; a and c dropped, b allowed
    assert rail_gate_suppressions([prog], Counter({"a": 1}), GATE_STEP_LOCK) == {"a", "c"}


def test_step_lock_all_done_drops_everything():
    prog = _prog([_step(1, "a", True), _step(2, "b", True)], None)
    assert rail_gate_suppressions([prog], set(), GATE_STEP_LOCK) == {"a", "b"}


# ── multiple rails union ────────────────────────────────────────────────────────

def test_multiple_rails_union_their_suppressions():
    p1 = _prog([_step(1, "a", True, session=True), _step(2, "b", False)], 2)
    p2 = _prog([_step(1, "c", True, session=True), _step(2, "d", False)], 2)
    assert rail_gate_suppressions([p1, p2], set(), GATE_DONE_SUPPRESS) == {"a", "c"}


def test_step_lock_keeps_each_rails_current_tool():
    p1 = _prog([_step(1, "a", False), _step(2, "b", False)], 1)
    p2 = _prog([_step(1, "c", False), _step(2, "d", False)], 1)
    # each rail's current tool (a, c) survives; the futures (b, d) drop
    assert rail_gate_suppressions([p1, p2], set(), GATE_STEP_LOCK) == {"b", "d"}


def test_unknown_mode_is_inert():
    prog = _prog([_step(1, "a", True, session=True), _step(2, "b", False)], 2)
    assert rail_gate_suppressions([prog], set(), "bogus") == set()
