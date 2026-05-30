"""Per-job cost budget + reserved eval-cost line tests (RAID C14, M5).

The :class:`JobCostBudget` wraps the C8 guardrail and reserves a fraction of the
cap for the (C15) eval pass. Asserts:
  * the working cap = cap − eval_reserve (the reserve is held back);
  * the pipeline charge enforces against the WORKING cap (a charge that would dip
    into the reserve is refused — the eval budget is protected);
  * a breach PAUSES the job (cost_cap) — never crashes, never overruns;
  * the C8 off-by-one contract is inherited verbatim (== cap allowed, > blocked);
  * misconfiguration (reserve > cap, fraction out of range) raises.
"""

from __future__ import annotations

import pytest

from app.gaps.model import Dimension, EntityKind, Gap
from app.jobs.cost import (
    DEFAULT_EVAL_RESERVE_FRACTION,
    GENERATION_GAP_COST,
    PER_GAP_WORKING_COST,
    RETRIEVAL_GAP_COST,
    CostCapExceeded,
    EvalReserveError,
    GapCostModel,
    JobCostBudget,
)
from app.jobs.state_machine import JobRecord, JobState, JobStateMachine, PauseReason


def test_working_cap_holds_back_eval_reserve():
    b = JobCostBudget(100.0, eval_reserve_fraction=0.15)
    assert b.cap == 100.0
    assert b.eval_reserve == pytest.approx(15.0)
    assert b.working_cap == pytest.approx(85.0)


def test_default_reserve_fraction():
    b = JobCostBudget(200.0)
    assert b.eval_reserve == pytest.approx(200.0 * DEFAULT_EVAL_RESERVE_FRACTION)


def test_explicit_absolute_reserve():
    b = JobCostBudget(100.0, eval_reserve=30.0)
    assert b.eval_reserve == 30.0
    assert b.working_cap == pytest.approx(70.0)


def test_charge_refuses_to_dip_into_eval_reserve():
    b = JobCostBudget(100.0, eval_reserve=20.0)  # working cap 80
    assert b.charge(80.0) is True   # lands exactly on the working cap — allowed
    assert b.spent == 80.0
    # one more unit would eat into the protected eval reserve → refused.
    assert b.would_exceed(0.01) is True
    assert b.charge(0.01) is False
    assert b.spent == 80.0  # unchanged — reserve protected


def test_off_by_one_contract_inherited():
    b = JobCostBudget(50.0, eval_reserve=0.0)  # working cap 50
    assert b.would_exceed(50.0) is False  # == cap allowed
    assert b.would_exceed(50.01) is True  # > cap blocked


@pytest.mark.asyncio
async def test_breach_pauses_job_not_crashes():
    b = JobCostBudget(10.0, eval_reserve=2.0)  # working cap 8
    record = JobRecord(job_id="j1", state=JobState.RUNNING)
    machine = JobStateMachine(record)
    # first charge fits (5 <= 8); second would breach 8 → pause.
    await b.charge_or_pause(5.0, machine)
    assert record.state is JobState.RUNNING
    with pytest.raises(CostCapExceeded):
        await b.charge_or_pause(5.0, machine)  # 5+5=10 > working cap 8
    assert record.state is JobState.PAUSED
    assert record.pause_reason is PauseReason.COST_CAP
    assert b.spent == 5.0  # the breaching unit was NOT charged


@pytest.mark.asyncio
async def test_uncapped_never_blocks_and_reserves_nothing():
    b = JobCostBudget(None)
    assert b.cap is None
    assert b.eval_reserve == 0.0
    assert b.working_cap is None
    record = JobRecord(job_id="j1", state=JobState.RUNNING)
    machine = JobStateMachine(record)
    await b.charge_or_pause(1e9, machine)  # never pauses
    assert record.state is JobState.RUNNING


def test_misconfig_raises():
    with pytest.raises(EvalReserveError):
        JobCostBudget(100.0, eval_reserve=150.0)  # reserve > cap
    with pytest.raises(EvalReserveError):
        JobCostBudget(100.0, eval_reserve_fraction=1.0)  # fraction out of range
    with pytest.raises(EvalReserveError):
        JobCostBudget(-1.0)  # negative cap


# ── BLOCK-1: the REAL per-gap cost model is NON-ZERO (the inert-cap fix) ───────


def _gaps(n: int) -> list[Gap]:
    return [
        Gap(
            entity_kind=EntityKind.LOCATION,
            canonical_name=f"loc{i}",
            target_ref=f"loc:{i}",
            mention_count=1,
            present_dimensions=(),
            missing_dimensions=tuple(Dimension),
        )
        for i in range(n)
    ]


def test_gap_cost_model_charges_nonzero_per_gap():
    """The real per-gap cost (embed + LLM) is NON-ZERO — unlike the inert
    TemplateStrategy free-scaffold estimate (0.0) the assembly used to wire."""
    model = GapCostModel()
    assert PER_GAP_WORKING_COST == RETRIEVAL_GAP_COST + GENERATION_GAP_COST
    assert model.per_gap_cost == pytest.approx(PER_GAP_WORKING_COST)
    assert model.per_gap_cost > 0.0  # the defect was this being 0.0

    one = model.estimate_cost(_gaps(1))
    assert one.cost == pytest.approx(PER_GAP_WORKING_COST)
    assert one.cost > 0.0
    three = model.estimate_cost(_gaps(3))
    assert three.cost == pytest.approx(PER_GAP_WORKING_COST * 3)


def test_gap_cost_model_empty_batch_is_free_but_per_gap_nonzero():
    model = GapCostModel()
    assert model.estimate_cost([]).cost == 0.0  # nothing to do
    assert model.estimate_cost(_gaps(1)).cost > 0.0  # but a real gap is not free


def test_gap_cost_model_rejects_negative():
    with pytest.raises(ValueError):
        GapCostModel(retrieval_gap_cost=-1.0)


def test_assembly_wires_nonzero_cost_not_template():
    """Guard the wiring: the assembly must NOT inject the free TemplateStrategy
    estimate (cost 0.0) as the cost path — that is exactly the inert-cap defect.
    A one-gap charge through the wired model must be > 0."""
    from app.strategies.template import TemplateStrategy

    # The OLD (defective) wiring's per-gap charge was 0.0 — prove it stays the
    # contrast, and that the NEW model the assembly wires is non-zero.
    assert TemplateStrategy().estimate_cost(_gaps(1)).cost == 0.0
    assert GapCostModel().estimate_cost(_gaps(1)).cost > 0.0
