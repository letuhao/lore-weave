"""K16.1 — unit tests for the extraction-job state machine.

Pure-python, no DB fixtures. Exercises every valid transition, every
invalid transition, the terminal-state rail, and the pause_reason
contract.
"""

from __future__ import annotations

import pytest

from app.jobs.state_machine import (
    StateTransitionError,
    TERMINAL_STATES,
    is_terminal,
    validate_transition,
)


# ── valid transitions ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "current,new",
    [
        ("pending", "running"),
        ("pending", "cancelled"),
        ("running", "complete"),
        ("running", "failed"),
        ("running", "cancelled"),
        ("paused", "running"),
        ("paused", "cancelled"),
        ("paused", "failed"),
    ],
)
def test_k16_1_valid_transition_no_reason(current, new):
    validate_transition(current, new, trace_id="t-1")


@pytest.mark.parametrize("reason", ["user", "budget", "error"])
def test_k16_1_running_to_paused_requires_reason(reason):
    validate_transition(
        "running", "paused", pause_reason=reason, trace_id="t-1"
    )


# ── invalid transitions ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "current,new",
    [
        ("pending", "paused"),
        ("pending", "complete"),
        ("pending", "failed"),
        ("running", "pending"),
        ("paused", "pending"),
        ("paused", "complete"),
        ("running", "running"),
        ("paused", "paused"),
    ],
)
def test_k16_1_invalid_transition_rejected(current, new):
    with pytest.raises(StateTransitionError, match="invalid transition"):
        validate_transition(current, new, trace_id="t-1")


# ── terminal-state rail ──────────────────────────────────────────────


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES))
@pytest.mark.parametrize("target", ["running", "paused", "pending"])
def test_k16_1_terminal_state_cannot_exit(terminal, target):
    with pytest.raises(StateTransitionError, match="terminal state"):
        validate_transition(terminal, target, trace_id="t-1")


def test_k16_1_is_terminal_matches_set():
    assert is_terminal("complete") is True
    assert is_terminal("failed") is True
    assert is_terminal("cancelled") is True
    assert is_terminal("running") is False
    assert is_terminal("pending") is False
    assert is_terminal("paused") is False


# ── pause_reason contract ────────────────────────────────────────────


def test_k16_1_paused_without_reason_raises():
    with pytest.raises(StateTransitionError, match="requires a pause_reason"):
        validate_transition("running", "paused", trace_id="t-1")


@pytest.mark.parametrize(
    "current,new",
    [("pending", "running"), ("running", "complete"), ("paused", "running")],
)
def test_k16_1_non_paused_with_reason_raises(current, new):
    with pytest.raises(StateTransitionError, match="only valid"):
        validate_transition(
            current, new, pause_reason="user", trace_id="t-1"
        )


# ── logging ──────────────────────────────────────────────────────────


def test_k16_1_logs_transition_with_trace_id(caplog):
    import logging as _logging
    with caplog.at_level(_logging.INFO, logger="app.jobs.state_machine"):
        validate_transition("running", "complete", trace_id="trace-abc")
    assert any("running → complete" in r.message for r in caplog.records)
    assert any("trace-abc" in r.message for r in caplog.records)
    assert any("validated" in r.message for r in caplog.records)


def test_k16_1_logs_pause_reason(caplog):
    import logging as _logging
    with caplog.at_level(_logging.INFO, logger="app.jobs.state_machine"):
        validate_transition(
            "running", "paused", pause_reason="budget", trace_id="t-1"
        )
    assert any("reason=budget" in r.message for r in caplog.records)


# ── unknown status defensive check ───────────────────────────────────


def test_k16_1_unknown_current_status():
    with pytest.raises(StateTransitionError, match="unknown current status"):
        validate_transition("weird_state", "running", trace_id="t-1")  # type: ignore[arg-type]


# ── R1/I1: drift guard against the repo's JobStatus literal ─────────


def test_k16_1_jobstatus_matches_repo_literal():
    """If K10.4's repo enum gains or drops a state, this test
    fails loudly so the state machine matrix can be updated in
    the same PR instead of silently diverging."""
    from typing import get_args

    from app.db.repositories.extraction_jobs import (
        JobStatus as RepoJobStatus,
    )
    from app.jobs.state_machine import JobStatus as SmJobStatus

    assert set(get_args(SmJobStatus)) == set(get_args(RepoJobStatus))
