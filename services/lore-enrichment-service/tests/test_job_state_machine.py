"""C8 — job state machine tests.

Pins the lifecycle DAG: legal transitions succeed and persist; every illegal
transition RAISES (no silent no-op); the persisted state always matches the
in-memory state. States mirror the C2 ``enrichment_job.status`` vocabulary.

Adversary focus (brief): illegal transitions (resume-from-completed,
start-from-cancelled, …) must raise; persisted == in-memory.
"""

from __future__ import annotations

import pytest

from app.jobs.state_machine import (
    IllegalTransitionError,
    JobRecord,
    JobState,
    JobStateMachine,
    PauseReason,
)


class _FakeSink:
    """Records what would be persisted to the C2 ``enrichment_job`` row."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, JobState]] = []
        self.fail_next = False

    async def __call__(self, rec: JobRecord) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated persist failure")
        self.writes.append((rec.job_id, rec.state))

    @property
    def last_state(self) -> JobState | None:
        return self.writes[-1][1] if self.writes else None


def _machine(state: JobState = JobState.PENDING):
    sink = _FakeSink()
    rec = JobRecord(job_id="job-1", state=state)
    return JobStateMachine(rec, persist=sink), sink, rec


# ── the happy path: full estimate→start→complete ─────────────────────────────
@pytest.mark.asyncio
async def test_full_happy_path() -> None:
    sm, sink, rec = _machine()
    await sm.estimate()
    assert sm.state is JobState.ESTIMATING
    await sm.start()
    assert sm.state is JobState.RUNNING
    assert rec.started_at is not None
    await sm.complete()
    assert sm.state is JobState.COMPLETED
    assert sm.is_terminal()
    assert rec.completed_at is not None
    # persisted state mirrors in-memory at every step
    assert [s for _, s in sink.writes] == [
        JobState.ESTIMATING,
        JobState.RUNNING,
        JobState.COMPLETED,
    ]
    assert sink.last_state is sm.state


# ── pause / resume cycle ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_pause_resume_cycle() -> None:
    sm, sink, rec = _machine(JobState.RUNNING)
    await sm.pause(reason=PauseReason.MANUAL)
    assert sm.state is JobState.PAUSED
    assert rec.pause_reason is PauseReason.MANUAL
    assert rec.paused_at is not None
    await sm.resume()
    assert sm.state is JobState.RUNNING
    assert rec.pause_reason is None  # cleared on resume
    # can pause again with a different reason
    await sm.pause(reason=PauseReason.COST_CAP)
    assert rec.pause_reason is PauseReason.COST_CAP
    assert rec.error_message == "paused: cost_cap"


# ── illegal transitions RAISE (no silent no-op) ──────────────────────────────
@pytest.mark.asyncio
async def test_resume_from_completed_raises() -> None:
    sm, sink, _ = _machine(JobState.COMPLETED)
    before = len(sink.writes)
    with pytest.raises(IllegalTransitionError):
        await sm.resume()
    assert sm.state is JobState.COMPLETED  # unchanged
    assert len(sink.writes) == before  # nothing persisted


@pytest.mark.asyncio
async def test_start_from_cancelled_raises() -> None:
    sm, _, _ = _machine(JobState.CANCELLED)
    with pytest.raises(IllegalTransitionError):
        await sm.start()
    assert sm.state is JobState.CANCELLED


@pytest.mark.asyncio
async def test_pause_from_pending_raises() -> None:
    sm, _, _ = _machine(JobState.PENDING)
    with pytest.raises(IllegalTransitionError):
        await sm.pause()
    assert sm.state is JobState.PENDING


@pytest.mark.asyncio
async def test_complete_from_paused_raises() -> None:
    # complete is only legal from running; from paused it must raise
    sm, _, _ = _machine(JobState.PAUSED)
    with pytest.raises(IllegalTransitionError):
        await sm.complete()
    assert sm.state is JobState.PAUSED


@pytest.mark.asyncio
async def test_start_skipping_estimate_raises() -> None:
    # pending → running is NOT legal (must go through estimating)
    sm, _, _ = _machine(JobState.PENDING)
    with pytest.raises(IllegalTransitionError):
        await sm.start()
    assert sm.state is JobState.PENDING


# ── cancel is legal from the non-terminal states ─────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frm",
    [JobState.PENDING, JobState.ESTIMATING, JobState.RUNNING, JobState.PAUSED],
)
async def test_cancel_legal_from_non_terminal(frm: JobState) -> None:
    sm, _, rec = _machine(frm)
    await sm.cancel()
    assert sm.state is JobState.CANCELLED
    assert rec.completed_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frm", [JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED]
)
async def test_no_transition_out_of_terminal(frm: JobState) -> None:
    sm, _, _ = _machine(frm)
    for action in (sm.estimate, sm.start, sm.resume, sm.cancel, sm.complete):
        with pytest.raises(IllegalTransitionError):
            await action()
        assert sm.state is frm


# ── persist failure → in-memory rolls back to match the store ────────────────
@pytest.mark.asyncio
async def test_persist_failure_rolls_back_state() -> None:
    sm, sink, _ = _machine(JobState.PENDING)
    sink.fail_next = True
    with pytest.raises(RuntimeError):
        await sm.estimate()
    # state did NOT advance — in-memory still matches the (un)persisted store
    assert sm.state is JobState.PENDING
    assert sink.writes == []
    # and the machine still works afterward
    await sm.estimate()
    assert sm.state is JobState.ESTIMATING


# ── values line up with the C2 status vocabulary ─────────────────────────────
def test_state_values_match_c2_status_vocabulary() -> None:
    expected = {
        "pending",
        "estimating",
        "running",
        "paused",
        "completed",
        "failed",
        "cancelled",
    }
    assert {s.value for s in JobState} == expected


# ── state machine works without a persistence hook (pure in-memory) ──────────
@pytest.mark.asyncio
async def test_machine_without_persist_hook() -> None:
    rec = JobRecord(job_id="job-x")
    sm = JobStateMachine(rec)  # no persist
    await sm.estimate()
    await sm.start()
    assert sm.state is JobState.RUNNING
    assert rec.history == [
        (JobState.PENDING, JobState.ESTIMATING),
        (JobState.ESTIMATING, JobState.RUNNING),
    ]
