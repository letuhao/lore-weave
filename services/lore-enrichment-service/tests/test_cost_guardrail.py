"""C8 — per-job cost guardrail tests.

Pins the cost-discipline control: projected spend is checked BEFORE each unit;
the job is paused (state machine, reason cost_cap) BEFORE the cap is breached,
never after an overrun. Boundary equality (spend == cap) is explicitly defined
and tested.

Adversary focus (brief): cost-cap off-by-one — pause BEFORE exceeding, not
retroactively; spend==cap behaviour defined; cap breach → job `paused`.
"""

from __future__ import annotations

import pytest

from app.jobs.cost_guardrail import CostCapExceeded, CostGuardrail
from app.jobs.state_machine import JobRecord, JobState, JobStateMachine, PauseReason


def _running_machine():
    rec = JobRecord(job_id="job-cost", state=JobState.RUNNING)
    return JobStateMachine(rec), rec


# ── would_exceed: strictly-greater boundary (== cap is allowed) ──────────────
def test_would_exceed_boundary_equality_allowed() -> None:
    g = CostGuardrail(cap=10.0, spent=7.0)
    assert not g.would_exceed(3.0)  # 7 + 3 == 10 → exactly on cap → allowed
    assert g.would_exceed(3.0001)  # 7 + 3.0001 > 10 → exceeds
    assert not g.would_exceed(0.0)  # zero unit never exceeds


def test_would_exceed_uncapped_is_always_false() -> None:
    g = CostGuardrail(cap=None)
    assert not g.would_exceed(1_000_000.0)


def test_would_exceed_rejects_negative() -> None:
    g = CostGuardrail(cap=10.0)
    with pytest.raises(ValueError):
        g.would_exceed(-1.0)


# ── charge: never pushes spend past the cap ──────────────────────────────────
def test_charge_accumulates_until_cap_then_refuses() -> None:
    g = CostGuardrail(cap=10.0)
    assert g.charge(4.0) is True
    assert g.spent == pytest.approx(4.0)
    assert g.charge(6.0) is True  # 4 + 6 == 10 → exactly on cap → allowed
    assert g.spent == pytest.approx(10.0)
    assert g.remaining == pytest.approx(0.0)
    # next positive unit would exceed → refused, spend unchanged
    assert g.charge(0.01) is False
    assert g.spent == pytest.approx(10.0)  # NOT pushed over the cap


def test_charge_uncapped_always_accepts() -> None:
    g = CostGuardrail(cap=None)
    assert g.charge(123.0) is True
    assert g.spent == pytest.approx(123.0)
    assert g.remaining is None


def test_zero_cap_pauses_any_positive_unit() -> None:
    g = CostGuardrail(cap=0.0)
    assert g.charge(0.0) is True  # zero fits
    assert g.charge(0.001) is False  # any positive overruns a zero cap


def test_negative_cap_rejected() -> None:
    with pytest.raises(ValueError):
        CostGuardrail(cap=-1.0)


# ── charge_or_pause: cap breach → job transitions to paused(cost_cap) ─────────
@pytest.mark.asyncio
async def test_cap_breach_pauses_job_before_overrun() -> None:
    sm, rec = _running_machine()
    g = CostGuardrail(cap=5.0)
    # first unit fits
    await g.charge_or_pause(3.0, sm)
    assert g.spent == pytest.approx(3.0)
    assert rec.state is JobState.RUNNING
    # second unit would push 3 + 3 = 6 > 5 → pause BEFORE incurring, raise
    with pytest.raises(CostCapExceeded) as exc:
        await g.charge_or_pause(3.0, sm)
    # job is PAUSED with the cost_cap reason
    assert rec.state is JobState.PAUSED
    assert rec.pause_reason is PauseReason.COST_CAP
    assert rec.error_message == "paused: cost_cap"
    # spend was NOT incremented past the cap (no retroactive overrun)
    assert g.spent == pytest.approx(3.0)
    assert exc.value.attempted == pytest.approx(3.0)
    assert exc.value.cap == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_charge_or_pause_exactly_on_cap_does_not_pause() -> None:
    sm, rec = _running_machine()
    g = CostGuardrail(cap=5.0)
    await g.charge_or_pause(5.0, sm)  # lands exactly on cap → allowed
    assert g.spent == pytest.approx(5.0)
    assert rec.state is JobState.RUNNING  # NOT paused


@pytest.mark.asyncio
async def test_charge_or_pause_uncapped_never_pauses() -> None:
    sm, rec = _running_machine()
    g = CostGuardrail(cap=None)
    for _ in range(5):
        await g.charge_or_pause(1000.0, sm)
    assert rec.state is JobState.RUNNING
    assert g.spent == pytest.approx(5000.0)


# ── record_actual: unconditional post-call reconcile (C1, DEFERRED-052) ───────
def test_record_actual_trues_up_unconditionally_even_past_cap() -> None:
    """The work already ran; the real spend is recorded even if it dips past the
    cap (one-gap overshoot). The NEXT would_exceed/charge then guards the cap."""
    g = CostGuardrail(cap=10.0)
    assert g.charge(8.0) is True  # pre-charged estimate
    g.record_actual(5.0)  # actual was 13 → overshoots the cap by 3
    assert g.spent == pytest.approx(13.0)
    assert g.would_exceed(0.01) is True  # the next gap is now correctly blocked


def test_record_actual_negative_refunds_headroom() -> None:
    g = CostGuardrail(cap=10.0)
    g.charge(8.0)  # pre-charged estimate of 8
    g.record_actual(-3.0)  # actual was only 5 → refund 3
    assert g.spent == pytest.approx(5.0)
    assert g.remaining == pytest.approx(5.0)


def test_record_actual_floors_at_zero() -> None:
    g = CostGuardrail(cap=10.0)
    g.charge(2.0)
    g.record_actual(-100.0)  # a refund larger than spent floors at 0, never negative
    assert g.spent == pytest.approx(0.0)


def test_record_actual_uncapped_still_tracks_spend() -> None:
    g = CostGuardrail(cap=None)
    g.charge(50.0)
    g.record_actual(25.0)
    assert g.spent == pytest.approx(75.0)


@pytest.mark.asyncio
async def test_pause_persists_through_state_machine() -> None:
    # integration: the pause uses the real state machine + a persistence sink,
    # so the persisted status would be 'paused' (cap breach → paused, the
    # easiest-to-forget acceptance gate per the brief).
    writes: list[JobState] = []

    async def sink(rec: JobRecord) -> None:
        writes.append(rec.state)

    rec = JobRecord(job_id="job-persist", state=JobState.RUNNING)
    sm = JobStateMachine(rec, persist=sink)
    g = CostGuardrail(cap=2.0)
    with pytest.raises(CostCapExceeded):
        await g.charge_or_pause(2.5, sm)  # first unit already over the cap
    assert writes == [JobState.PAUSED]
    assert rec.state is JobState.PAUSED
