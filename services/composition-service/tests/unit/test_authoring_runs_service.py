"""Authoring-run FSM + start-gate + v1 driver unit tests (RAID Wave D2, DR-D).

Fakes mirror the repo's OCC semantics exactly: transition() is a guarded
compare-and-set (wrong-from → None) and →gated raises UniqueViolationError
when another run is active on the same book (the partial-index scope fence).
The driver is exercised directly (run_driver) with a FAKE drafting seam.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import asyncpg
import pytest

from app.db.models import AuthoringRun, PlanRun
from app.services.authoring_run_service import (
    ActiveRunOverlapError,
    AuthoringRunService,
    DraftOutcome,
    TransitionConflictError,
)

OWNER = uuid.uuid4()
BOOK = uuid.uuid4()
PLAN = uuid.uuid4()
CH1, CH2, CH3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
BOOK_CHAPTERS = {str(CH1), str(CH2), str(CH3)}

_ACTIVE = ("gated", "running", "paused")


class FakeRunsRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, AuthoringRun] = {}

    async def create(self, owner_user_id, book_id, *, plan_run_id, level, scope,
                     budget_usd, tool_allowlist, params=None) -> AuthoringRun:
        run = AuthoringRun(
            run_id=uuid.uuid4(), owner_user_id=owner_user_id, book_id=book_id,
            plan_run_id=plan_run_id, level=level, scope=[str(c) for c in scope],
            budget_usd=Decimal(str(budget_usd)), tool_allowlist=tool_allowlist,
            params=params or {},
        )
        self.rows[run.run_id] = run
        return run

    async def get_for_owner(self, owner_user_id, run_id) -> AuthoringRun | None:
        r = self.rows.get(run_id)
        return r if r is not None and r.owner_user_id == owner_user_id else None

    async def list_for_owner(self, owner_user_id, book_id, *, limit=20):
        return [
            r for r in self.rows.values()
            if r.owner_user_id == owner_user_id and r.book_id == book_id
        ][:limit]

    async def transition(self, owner_user_id, run_id, *, from_statuses, to_status,
                         breaker_state=None, error_message=None) -> AuthoringRun | None:
        r = await self.get_for_owner(owner_user_id, run_id)
        if r is None or r.status not in from_statuses:
            return None
        if to_status == "gated":  # the partial unique index fence
            for other in self.rows.values():
                if (other.run_id != run_id and other.book_id == r.book_id
                        and other.status in _ACTIVE):
                    raise asyncpg.UniqueViolationError("uq_authoring_runs_active_book")
        update: dict[str, Any] = {"status": to_status}
        if breaker_state is not None:
            update["breaker_state"] = breaker_state
        if error_message is not None:
            update["error_message"] = error_message
        updated = r.model_copy(update=update)
        self.rows[run_id] = updated
        return updated

    async def record_unit_progress(self, owner_user_id, run_id, *, add_spent_usd,
                                   current_unit) -> AuthoringRun | None:
        r = await self.get_for_owner(owner_user_id, run_id)
        if r is None:
            return None
        updated = r.model_copy(update={
            "spent_usd": r.spent_usd + add_spent_usd, "current_unit": current_unit,
        })
        self.rows[run_id] = updated
        return updated


class FakePlanRuns:
    def __init__(self) -> None:
        self.rows: dict[tuple, PlanRun] = {}

    def add(self, owner, book, plan_id, status) -> None:
        self.rows[(owner, book, plan_id)] = PlanRun(
            id=plan_id, owner_user_id=owner, book_id=book, mode="rules", status=status,
        )

    async def get_for_owner(self, owner, book, plan_id) -> PlanRun | None:
        return self.rows.get((owner, book, plan_id))


class FakeSeam:
    def __init__(self, outcomes=None,
                 default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")),
                 on_call=None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes = list(outcomes or [])
        self.default = default
        self.on_call = on_call

    async def draft_chapter(self, **kw) -> DraftOutcome:
        self.calls.append(kw)
        if self.on_call is not None:
            await self.on_call(len(self.calls), kw)
        return self.outcomes.pop(0) if self.outcomes else self.default


def make_svc(seam=None, plan_status="validated"):
    runs = FakeRunsRepo()
    plans = FakePlanRuns()
    plans.add(OWNER, BOOK, PLAN, plan_status)
    return AuthoringRunService(runs, plans, seam or FakeSeam()), runs, plans


async def make_run(svc, *, scope=None, budget="1.00", allowlist=None, level=3):
    return await svc.create(
        OWNER, BOOK, plan_run_id=PLAN, level=level,
        scope=[str(c) for c in (scope if scope is not None else [CH1, CH2])],
        budget_usd=Decimal(budget),
        tool_allowlist=allowlist if allowlist is not None else ["book_write_draft"],
    )


# ── create + gate happy path ────────────────────────────────────────────────


async def test_create_draft_and_gate_happy():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    assert run.status == "draft"
    gated = await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    assert gated.status == "gated"


async def test_create_unknown_plan_404():
    svc, _, _ = make_svc()
    with pytest.raises(LookupError):
        await svc.create(
            OWNER, BOOK, plan_run_id=uuid.uuid4(), level=3, scope=[str(CH1)],
            budget_usd=Decimal("1"), tool_allowlist=["t"],
        )


async def test_gate_accepts_compiled_plan_too():
    svc, _, _ = make_svc(plan_status="compiled")
    run = await make_run(svc)
    gated = await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    assert gated.status == "gated"


# ── gate rejections (all-or-nothing) ────────────────────────────────────────


async def test_gate_rejects_unapproved_plan():
    svc, _, _ = make_svc(plan_status="proposed")
    run = await make_run(svc)
    with pytest.raises(ValueError, match="approved"):
        await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_empty_scope():
    svc, _, _ = make_svc()
    run = await make_run(svc, scope=[])
    with pytest.raises(ValueError, match="scope is empty"):
        await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_foreign_chapters():
    svc, _, _ = make_svc()
    foreign = uuid.uuid4()
    run = await make_run(svc, scope=[CH1, foreign])
    with pytest.raises(ValueError, match="not in this book"):
        await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_zero_budget():
    svc, _, _ = make_svc()
    run = await make_run(svc, budget="0")
    with pytest.raises(ValueError, match="budget_usd"):
        await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_empty_allowlist():
    svc, _, _ = make_svc()
    run = await make_run(svc, allowlist=[])
    with pytest.raises(ValueError, match="tool_allowlist"):
        await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_blank_allowlist_entries():
    svc, _, _ = make_svc()
    run = await make_run(svc, allowlist=["ok", "  "])
    with pytest.raises(ValueError, match="tool_allowlist"):
        await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_overlap_active_run_409():
    svc, runs, _ = make_svc()
    first = await make_run(svc)
    await svc.gate(OWNER, first.run_id, book_chapter_ids=BOOK_CHAPTERS)
    second = await make_run(svc, scope=[CH3])
    with pytest.raises(ActiveRunOverlapError):
        await svc.gate(OWNER, second.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_on_non_draft_conflicts():
    svc, _, _ = make_svc()
    run = await make_run(svc)
    await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    with pytest.raises(TransitionConflictError):
        await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_foreign_owner_404():
    svc, _, _ = make_svc()
    run = await make_run(svc)
    with pytest.raises(LookupError):
        await svc.gate(uuid.uuid4(), run.run_id, book_chapter_ids=BOOK_CHAPTERS)


# ── race-guarded transitions ────────────────────────────────────────────────


async def test_start_requires_gated():
    svc, _, _ = make_svc()
    run = await make_run(svc)
    with pytest.raises(TransitionConflictError):
        await svc.start(OWNER, run.run_id)  # still draft


async def test_pause_requires_running_and_resume_requires_paused():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    with pytest.raises(TransitionConflictError):
        await svc.pause(OWNER, run.run_id)
    with pytest.raises(TransitionConflictError):
        await svc.resume(OWNER, run.run_id)


async def test_close_not_allowed_from_running():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    await runs.transition(OWNER, run.run_id, from_statuses=("gated",), to_status="running")
    with pytest.raises(TransitionConflictError):
        await svc.close(OWNER, run.run_id)


async def test_close_releases_fence_for_next_run():
    svc, _, _ = make_svc()
    first = await make_run(svc)
    await svc.gate(OWNER, first.run_id, book_chapter_ids=BOOK_CHAPTERS)
    closed = await svc.close(OWNER, first.run_id)
    assert closed.status == "closed"
    second = await make_run(svc)
    gated = await svc.gate(OWNER, second.run_id, book_chapter_ids=BOOK_CHAPTERS)
    assert gated.status == "gated"


async def test_repo_guarded_transition_wrong_from_noops():
    runs = FakeRunsRepo()
    run = await runs.create(
        OWNER, BOOK, plan_run_id=PLAN, level=3, scope=[str(CH1)],
        budget_usd=Decimal("1"), tool_allowlist=["t"],
    )
    out = await runs.transition(
        OWNER, run.run_id, from_statuses=("running",), to_status="paused",
    )
    assert out is None
    assert (await runs.get_for_owner(OWNER, run.run_id)).status == "draft"


# ── driver (fake seam) ──────────────────────────────────────────────────────


async def _running_run(svc, runs, **kw):
    run = await make_run(svc, **kw)
    await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    await runs.transition(OWNER, run.run_id, from_statuses=("gated",), to_status="running")
    return run


async def test_driver_success_path_report_ready():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    await svc.run_driver(OWNER, run.run_id)
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "report_ready"
    assert final.current_unit == 2
    assert final.spent_usd == Decimal("0.02")
    assert len(seam.calls) == 2
    # scope order preserved: chapter 1 first, then chapter 2
    assert seam.calls[0]["chapter_id"] == CH1
    assert seam.calls[1]["chapter_id"] == CH2


async def test_driver_zero_cost_falls_back_to_unit_estimate():
    from app.config import settings

    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    await svc.run_driver(OWNER, run.run_id)
    final = await runs.get_for_owner(OWNER, run.run_id)
    est = Decimal(str(settings.authoring_unit_estimate_usd))
    assert final.spent_usd == est * 2


async def test_driver_budget_exceeded_auto_pauses_with_breaker():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.06")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, budget="0.05")
    await svc.run_driver(OWNER, run.run_id)
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "paused"
    assert final.breaker_state["reason"] == "budget"
    assert final.current_unit == 1          # unit 1 landed, unit 2 never ran
    assert len(seam.calls) == 1


async def test_driver_unit_failure_fail_stops_with_breaker():
    seam = FakeSeam(outcomes=[
        DraftOutcome(ok=True, cost_usd=Decimal("0.01")),
        DraftOutcome(ok=False, error="engine 502: GENERATE_FAILED"),
    ])
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    await svc.run_driver(OWNER, run.run_id)
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "failed"
    assert final.breaker_state["reason"] == "unit_failed"
    assert final.breaker_state["unit"] == 1
    assert final.breaker_state["chapter_id"] == str(CH2)
    assert final.error_message == "engine 502: GENERATE_FAILED"


async def test_driver_pause_mid_run_stops_at_unit_boundary():
    svc_holder: dict[str, Any] = {}

    async def pause_during_first_unit(call_no, kw):
        if call_no == 1:  # author hits pause while unit 1 drafts
            await svc_holder["runs"].transition(
                OWNER, svc_holder["run_id"],
                from_statuses=("running",), to_status="paused",
            )

    seam = FakeSeam(on_call=pause_during_first_unit)
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    svc_holder.update(runs=runs, run_id=run.run_id)
    await svc.run_driver(OWNER, run.run_id)
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "paused"
    assert len(seam.calls) == 1             # unit 2 never started
    assert final.current_unit == 1          # unit 1's progress still recorded
    assert final.spent_usd == Decimal("0.01")


async def test_driver_resume_continues_from_cursor():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    # simulate a prior partial run: unit 1 done, then paused
    await runs.record_unit_progress(
        OWNER, run.run_id, add_spent_usd=Decimal("0.01"), current_unit=1,
    )
    await runs.transition(OWNER, run.run_id, from_statuses=("running",), to_status="paused")
    resumed = await svc.resume(OWNER, run.run_id)
    assert resumed.status == "running"
    # drive synchronously (the spawned task is also live; run_driver is idempotent
    # over the guarded transitions — the loser of any race just no-ops)
    await svc.run_driver(OWNER, run.run_id)
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "report_ready"
    # only chapter 2 was drafted on resume
    assert any(c["chapter_id"] == CH2 for c in seam.calls)
    assert all(c["chapter_id"] != CH1 for c in seam.calls)
    # drain the task resume() spawned (it no-ops — the run is already terminal)
    from app.services import authoring_run_service as mod

    task = mod._DRIVER_TASKS.get(run.run_id)
    if task is not None:
        await task


async def test_start_spawns_driver_to_completion():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await make_run(svc)
    await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    started = await svc.start(OWNER, run.run_id)
    assert started.status == "running"
    from app.services import authoring_run_service as mod

    task = mod._DRIVER_TASKS.get(run.run_id)
    assert task is not None
    await task
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "report_ready"
