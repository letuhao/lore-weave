"""Authoring-run FSM + start-gate + v1 driver unit tests (RAID Wave D2, DR-D)
+ the D3 per-unit ledger / Run Report / accept-reject / Revert-All.

Fakes mirror the repo's OCC semantics exactly: transition() is a guarded
compare-and-set (wrong-from → None) and →gated raises UniqueViolationError
when another run is active on the same book (the partial-index scope fence).
The driver is exercised directly (run_driver) with a FAKE drafting seam and a
FAKE revision capture (the book-service revisions-list seam).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import asyncpg
import pytest

from app.db.models import AuthoringRun, AuthoringRunUnit, PlanRun
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
                     budget_usd, tool_allowlist, params=None,
                     background=False) -> AuthoringRun:
        run = AuthoringRun(
            run_id=uuid.uuid4(), owner_user_id=owner_user_id, book_id=book_id,
            plan_run_id=plan_run_id, level=level, scope=[str(c) for c in scope],
            budget_usd=Decimal(str(budget_usd)), tool_allowlist=tool_allowlist,
            params=params or {}, background=background,
        )
        self.rows[run.run_id] = run
        return run

    async def get_for_owner(self, owner_user_id, run_id) -> AuthoringRun | None:
        r = self.rows.get(run_id)
        return r if r is not None and r.owner_user_id == owner_user_id else None

    async def get_by_id(self, run_id) -> AuthoringRun | None:
        return self.rows.get(run_id)

    async def list_for_owner(self, owner_user_id, book_id, *, limit=20):
        return [
            r for r in self.rows.values()
            if r.owner_user_id == owner_user_id and r.book_id == book_id
        ][:limit]

    async def transition(self, owner_user_id, run_id, *, from_statuses, to_status,
                         breaker_state=None, error_message=None,
                         claim_driver_id=None) -> AuthoringRun | None:
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
        if claim_driver_id is not None:  # D4: →running claims in the same UPDATE
            update["driver_id"] = claim_driver_id
            update["driver_heartbeat_at"] = datetime.now(timezone.utc)
        updated = r.model_copy(update=update)
        self.rows[run_id] = updated
        return updated

    # ── D4 durable driver (mirrors the repo's guarded claims exactly) ────

    async def heartbeat_claim(self, owner_user_id, run_id, driver_id) -> AuthoringRun | None:
        r = await self.get_for_owner(owner_user_id, run_id)
        if r is None or r.status != "running" or r.driver_id != driver_id:
            return None
        updated = r.model_copy(update={
            "driver_heartbeat_at": datetime.now(timezone.utc),
        })
        self.rows[run_id] = updated
        return updated

    async def claim_stale_running(self, *, driver_id, stale_secs, limit) -> list[AuthoringRun]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_secs)
        claimed: list[AuthoringRun] = []
        for rid, r in sorted(self.rows.items(), key=lambda kv: kv[0].hex):
            if len(claimed) >= limit:
                break
            if r.status != "running":
                continue
            if r.driver_heartbeat_at is not None and r.driver_heartbeat_at >= cutoff:
                continue  # fresh heartbeat — a live driver owns it
            updated = r.model_copy(update={
                "driver_id": driver_id,
                "driver_heartbeat_at": datetime.now(timezone.utc),
            })
            self.rows[rid] = updated
            claimed.append(updated)
        return claimed

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


class FakeUnitsRepo:
    """Mirrors AuthoringRunUnitsRepo: owner tenancy via the parent run row,
    upsert resets to pending, transitions are guarded compare-and-set."""

    def __init__(self, runs: FakeRunsRepo) -> None:
        self._runs = runs
        self.rows: dict[tuple[uuid.UUID, int], AuthoringRunUnit] = {}

    def _owned(self, owner, run_id) -> bool:
        r = self._runs.rows.get(run_id)
        return r is not None and r.owner_user_id == owner

    async def upsert_pending(self, owner, run_id, unit_index, chapter_id, *,
                             pre_revision_id) -> AuthoringRunUnit | None:
        if not self._owned(owner, run_id):
            return None
        unit = AuthoringRunUnit(
            run_id=run_id, unit_index=unit_index, chapter_id=chapter_id,
            pre_revision_id=pre_revision_id,
        )
        self.rows[(run_id, unit_index)] = unit
        return unit

    async def mark_drafted(self, owner, run_id, unit_index, *, post_revision_id,
                           cost_usd, run_statuses=None) -> AuthoringRunUnit | None:
        return await self.transition_unit(
            owner, run_id, unit_index, from_statuses=("pending",),
            to_status="drafted", post_revision_id=post_revision_id, cost_usd=cost_usd,
            run_statuses=run_statuses,
        )

    async def mark_failed(self, owner, run_id, unit_index, *, error) -> AuthoringRunUnit | None:
        return await self.transition_unit(
            owner, run_id, unit_index, from_statuses=("pending",),
            to_status="failed", error_message=error,
        )

    async def transition_unit(self, owner, run_id, unit_index, *, from_statuses,
                              to_status, post_revision_id=None, cost_usd=None,
                              error_message=None,
                              run_statuses=None) -> AuthoringRunUnit | None:
        if not self._owned(owner, run_id):
            return None
        if run_statuses is not None:  # D4 late-result fence (parent-run guard)
            parent = self._runs.rows.get(run_id)
            if parent is None or parent.status not in run_statuses:
                return None
        u = self.rows.get((run_id, unit_index))
        if u is None or u.status not in from_statuses:
            return None
        update: dict[str, Any] = {"status": to_status}
        if post_revision_id is not None:
            update["post_revision_id"] = post_revision_id
        if cost_usd is not None:
            update["cost_usd"] = cost_usd
        if error_message is not None:
            update["error_message"] = error_message
        updated = u.model_copy(update=update)
        self.rows[(run_id, unit_index)] = updated
        return updated

    async def get_for_owner(self, owner, run_id, unit_index) -> AuthoringRunUnit | None:
        if not self._owned(owner, run_id):
            return None
        return self.rows.get((run_id, unit_index))

    async def list_for_owner(self, owner, run_id) -> list[AuthoringRunUnit]:
        if not self._owned(owner, run_id):
            return []
        return await self.list_for_run(run_id)

    async def list_for_run(self, run_id) -> list[AuthoringRunUnit]:
        return sorted(
            (u for (rid, _), u in self.rows.items() if rid == run_id),
            key=lambda u: u.unit_index,
        )


class FakeRevisionCapture:
    """Issues a fresh revision id per call (so pre != post per unit; call order
    is pre0, post0, pre1, post1, …). `fail_on_call` (1-based) raises there;
    `empty=True` models a chapter with no revisions yet (returns None)."""

    def __init__(self, *, fail_on_call: set[int] | None = None, empty: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.issued: list[uuid.UUID] = []
        self.fail_on_call = fail_on_call or set()
        self.empty = empty

    async def latest_revision_id(self, *, owner_user_id, book_id, chapter_id):
        self.calls.append(dict(
            owner_user_id=owner_user_id, book_id=book_id, chapter_id=chapter_id,
        ))
        if len(self.calls) in self.fail_on_call:
            raise RuntimeError("book-service revisions unavailable")
        if self.empty:
            return None
        rid = uuid.uuid4()
        self.issued.append(rid)
        return rid


class NotifyRecorder:
    """Stands in for the notification-service ingest client (D4). Records the
    calls; `raise_on_call=True` models an ingest outage — the run must be
    unaffected (best-effort contract)."""

    def __init__(self, *, raise_on_call: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_on_call = raise_on_call

    async def notify(self, user_id, *, title, metadata=None, category="system"):
        self.calls.append(dict(
            user_id=user_id, title=title, metadata=metadata, category=category,
        ))
        if self.raise_on_call:
            raise RuntimeError("notification-service down")


@pytest.fixture(autouse=True)
async def _drain_driver_tasks():
    """D4: driver tasks + the process driver-id live module-level (they span
    per-request service instances) — drain them between tests so a leaked task
    can't bleed into another test's inflight count."""
    yield
    from app.services import authoring_run_service as mod

    tasks = list(mod._DRIVER_TASKS.values())
    for t in tasks:
        if not t.done():
            t.cancel()
    for t in tasks:
        with contextlib.suppress(BaseException):
            await t
    mod._DRIVER_TASKS.clear()


def make_svc(seam=None, plan_status="validated", revisions=None, notify=None,
             driver_id=None):
    runs = FakeRunsRepo()
    plans = FakePlanRuns()
    plans.add(OWNER, BOOK, PLAN, plan_status)
    units = FakeUnitsRepo(runs)
    svc = AuthoringRunService(
        runs, plans, seam or FakeSeam(), units, revisions or FakeRevisionCapture(),
        # Always inject a recorder (never the real httpx client) — terminal
        # transitions notify, and unit tests must stay network-free.
        notify=notify or NotifyRecorder(),
        driver_id=driver_id,
    )
    return svc, runs, plans


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
    # →running CLAIMS for the service's driver (D4) — like svc.start, without
    # spawning the background task (tests drive run_driver synchronously).
    await runs.transition(
        OWNER, run.run_id, from_statuses=("gated",), to_status="running",
        claim_driver_id=svc._driver_id,
    )
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


# ── D3: driver writes the per-unit ledger ───────────────────────────────────


class RestoreRecorder:
    """Stands in for the router-bound BookClient.restore_revision closure.
    `fail_on_call` is 1-based; a failing call raises (unit must stay drafted)."""

    def __init__(self, fail_on_call: set[int] | None = None) -> None:
        self.calls: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []
        self.fail_on_call = fail_on_call or set()

    async def __call__(self, book_id, chapter_id, revision_id) -> None:
        self.calls.append((book_id, chapter_id, revision_id))
        if len(self.calls) in self.fail_on_call:
            raise RuntimeError("book-service restore 502")


async def _completed_run(svc, runs, **kw):
    """Gate + run the driver to report_ready over the default 2-unit scope."""
    run = await _running_run(svc, runs, **kw)
    await svc.run_driver(OWNER, run.run_id)
    return await runs.get_for_owner(OWNER, run.run_id)


async def test_driver_writes_drafted_ledger_rows_with_pre_post_and_cost():
    cap = FakeRevisionCapture()
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.02")))
    svc, runs, _ = make_svc(seam=seam, revisions=cap)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted", "drafted"]
    assert [u.chapter_id for u in units] == [CH1, CH2]
    assert all(u.cost_usd == Decimal("0.02") for u in units)
    # capture order: pre0, post0, pre1, post1 — pre pinned BEFORE the seam,
    # post after; the ids must land on the right rows and differ per unit
    assert units[0].pre_revision_id == cap.issued[0]
    assert units[0].post_revision_id == cap.issued[1]
    assert units[1].pre_revision_id == cap.issued[2]
    assert units[1].post_revision_id == cap.issued[3]
    assert units[0].pre_revision_id != units[0].post_revision_id
    # ledger costs sum to the run's spend
    assert sum(u.cost_usd for u in units) == run.spent_usd


async def test_driver_unit_failure_marks_ledger_row_failed():
    seam = FakeSeam(outcomes=[
        DraftOutcome(ok=True, cost_usd=Decimal("0.01")),
        DraftOutcome(ok=False, error="engine 502: GENERATE_FAILED"),
    ])
    svc, runs, _ = make_svc(seam=seam)
    run = await _completed_run(svc, runs)
    assert run.status == "failed"
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted", "failed"]
    assert units[1].error_message == "engine 502: GENERATE_FAILED"
    assert units[1].post_revision_id is None


async def test_driver_pre_capture_failure_fails_unit_without_drafting():
    cap = FakeRevisionCapture(fail_on_call={1})
    seam = FakeSeam()
    svc, runs, _ = make_svc(seam=seam, revisions=cap)
    run = await _completed_run(svc, runs)
    assert run.status == "failed"
    assert "pre-revision capture failed" in run.error_message
    assert seam.calls == []  # the seam never ran — no unpinned drafting
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["failed"]
    assert units[0].pre_revision_id is None


async def test_driver_post_capture_failure_still_drafts_unit():
    cap = FakeRevisionCapture(fail_on_call={2})  # unit 0's POST capture blips
    svc, runs, _ = make_svc(revisions=cap)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"  # best-effort post — the run continued
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted", "drafted"]
    assert units[0].post_revision_id is None
    assert units[0].pre_revision_id is not None
    assert units[1].post_revision_id is not None


async def test_driver_chapter_without_revisions_pins_null_pre():
    cap = FakeRevisionCapture(empty=True)
    svc, runs, _ = make_svc(revisions=cap)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"
    units = await svc._units.list_for_run(run.run_id)
    assert all(u.status == "drafted" for u in units)
    assert all(u.pre_revision_id is None for u in units)


# ── D3: Run Report ──────────────────────────────────────────────────────────


async def test_unit_report_shape_and_downstream_indexes():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs, scope=[CH1, CH2, CH3])
    rows = await svc.unit_report(run)
    assert [r["unit_index"] for r in rows] == [0, 1, 2]
    assert [r["status"] for r in rows] == ["drafted"] * 3
    # sequential threading: every LATER drafted/accepted unit is downstream
    assert rows[0]["downstream_unit_indexes"] == [1, 2]
    assert rows[1]["downstream_unit_indexes"] == [2]
    assert rows[2]["downstream_unit_indexes"] == []
    assert rows[0]["chapter_id"] == str(CH1)
    assert rows[0]["pre_revision_id"] is not None
    assert rows[0]["post_revision_id"] is not None


async def test_unit_report_partial_on_failed_run():
    seam = FakeSeam(outcomes=[
        DraftOutcome(ok=True, cost_usd=Decimal("0.01")),
        DraftOutcome(ok=False, error="boom"),
    ])
    svc, runs, _ = make_svc(seam=seam)
    run = await _completed_run(svc, runs, scope=[CH1, CH2, CH3])
    assert run.status == "failed"
    rows = await svc.unit_report(run)  # edge #12 — partial is reviewable
    assert [r["status"] for r in rows] == ["drafted", "failed", "pending"]
    assert rows[1]["error_message"] == "boom"
    # unit 2 never ran — synthesized from scope, no ledger row
    assert rows[2]["chapter_id"] == str(CH3)
    assert rows[2]["cost_usd"] == "0"
    assert rows[0]["downstream_unit_indexes"] == []  # nothing drafted after 0


async def test_unit_report_synthesizes_pending_after_budget_pause():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.06")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _completed_run(svc, runs, budget="0.05")
    assert run.status == "paused"
    rows = await svc.unit_report(run)
    assert [r["status"] for r in rows] == ["drafted", "pending"]


async def test_unit_report_rejected_in_wrong_status():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    with pytest.raises(TransitionConflictError, match="report requires"):
        await svc.unit_report(run)  # draft
    await svc.gate(OWNER, run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    await runs.transition(OWNER, run.run_id, from_statuses=("gated",), to_status="running")
    running = await runs.get_for_owner(OWNER, run.run_id)
    with pytest.raises(TransitionConflictError):
        await svc.unit_report(running)


async def test_unit_report_readable_after_close():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    closed = await svc.close(OWNER, run.run_id)
    rows = await svc.unit_report(closed)
    assert len(rows) == 2


# ── D3: accept / reject ─────────────────────────────────────────────────────


async def test_accept_unit_drafted_to_accepted():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    unit = await svc.accept_unit(OWNER, run.run_id, 0)
    assert unit.status == "accepted"
    with pytest.raises(TransitionConflictError, match="accept requires"):
        await svc.accept_unit(OWNER, run.run_id, 0)  # already accepted


async def test_accept_unknown_unit_404_and_foreign_owner_404():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    with pytest.raises(LookupError, match="unit not found"):
        await svc.accept_unit(OWNER, run.run_id, 99)
    with pytest.raises(LookupError, match="run not found"):
        await svc.accept_unit(uuid.uuid4(), run.run_id, 0)


async def test_review_blocked_while_running():
    svc, runs, _ = make_svc()
    run = await _running_run(svc, runs)
    with pytest.raises(TransitionConflictError, match="review requires"):
        await svc.accept_unit(OWNER, run.run_id, 0)
    with pytest.raises(TransitionConflictError, match="review requires"):
        await svc.reject_unit(OWNER, run.run_id, 0, restore=RestoreRecorder())


async def test_reject_restores_pre_revision_then_marks_rejected():
    cap = FakeRevisionCapture()
    svc, runs, _ = make_svc(revisions=cap)
    run = await _completed_run(svc, runs)
    restore = RestoreRecorder()
    unit, cascade, reverted = await svc.reject_unit(OWNER, run.run_id, 0, restore=restore)
    assert unit.status == "rejected"
    assert reverted is True
    # restored the chapter to ITS pre-run baseline (unit 0's pre = issued[0])
    assert restore.calls == [(BOOK, CH1, cap.issued[0])]
    # cascade warning: unit 1 is still drafted downstream of the rejected unit 0
    assert cascade == [1]


async def test_reject_restore_failure_leaves_unit_drafted():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    restore = RestoreRecorder(fail_on_call={1})
    with pytest.raises(RuntimeError, match="restore 502"):
        await svc.reject_unit(OWNER, run.run_id, 0, restore=restore)
    unit = await svc._units.get_for_owner(OWNER, run.run_id, 0)
    assert unit.status == "drafted"  # NEVER rejected without the actual revert


async def test_reject_without_pre_revision_skips_restore():
    svc, runs, _ = make_svc(revisions=FakeRevisionCapture(empty=True))
    run = await _completed_run(svc, runs)
    restore = RestoreRecorder()
    unit, cascade, reverted = await svc.reject_unit(OWNER, run.run_id, 1, restore=restore)
    assert unit.status == "rejected"
    assert reverted is False
    assert restore.calls == []       # nothing to restore to
    assert cascade == []             # no drafted/accepted units after index 1


async def test_reject_non_drafted_unit_conflicts():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    await svc.accept_unit(OWNER, run.run_id, 0)
    with pytest.raises(TransitionConflictError, match="reject requires"):
        await svc.reject_unit(OWNER, run.run_id, 0, restore=RestoreRecorder())


# ── D3: Revert-All ──────────────────────────────────────────────────────────


async def test_revert_all_reverse_order_and_closes_run():
    cap = FakeRevisionCapture()
    svc, runs, _ = make_svc(revisions=cap)
    run = await _completed_run(svc, runs, scope=[CH1, CH2, CH3])
    await svc.accept_unit(OWNER, run.run_id, 0)  # accepted units revert too
    restore = RestoreRecorder()
    result = await svc.revert_all(OWNER, run.run_id, restore=restore)
    # downstream-first: unit 2, then 1, then 0 — restores unwind cleanly
    assert [c[1] for c in restore.calls] == [CH3, CH2, CH1]
    assert restore.calls[0][2] == cap.issued[4]  # unit 2's pre (pre2 = 5th issued)
    assert result["reverted_unit_indexes"] == [2, 1, 0]
    assert result["failed_unit_index"] is None
    assert result["closed"] is True
    assert (await runs.get_for_owner(OWNER, run.run_id)).status == "closed"
    units = await svc._units.list_for_run(run.run_id)
    assert all(u.status == "rejected" for u in units)


async def test_revert_all_partial_failure_stops_and_reports():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)  # units 0, 1 drafted
    restore = RestoreRecorder(fail_on_call={2})  # unit 1 reverts, unit 0 fails
    result = await svc.revert_all(OWNER, run.run_id, restore=restore)
    assert result["reverted_unit_indexes"] == [1]
    assert result["failed_unit_index"] == 0
    assert "restore 502" in result["error"]
    assert result["closed"] is False
    # run untouched; unit 0 still drafted (re-runnable), unit 1 rejected
    assert (await runs.get_for_owner(OWNER, run.run_id)).status == "report_ready"
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted", "rejected"]


async def test_revert_all_from_failed_run_skips_failed_units():
    seam = FakeSeam(outcomes=[
        DraftOutcome(ok=True, cost_usd=Decimal("0.01")),
        DraftOutcome(ok=False, error="boom"),
    ])
    svc, runs, _ = make_svc(seam=seam)
    run = await _completed_run(svc, runs)
    assert run.status == "failed"
    restore = RestoreRecorder()
    result = await svc.revert_all(OWNER, run.run_id, restore=restore)
    assert result["reverted_unit_indexes"] == [0]  # only the drafted unit
    assert result["closed"] is True
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["rejected", "failed"]


async def test_revert_all_wrong_status_conflicts():
    svc, runs, _ = make_svc()
    run = await _running_run(svc, runs)
    with pytest.raises(TransitionConflictError, match="revert-all requires"):
        await svc.revert_all(OWNER, run.run_id, restore=RestoreRecorder())


async def test_revert_all_foreign_owner_404():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    with pytest.raises(LookupError):
        await svc.revert_all(uuid.uuid4(), run.run_id, restore=RestoreRecorder())


# ── D4: durable background execution ────────────────────────────────────────
# Restart durability (sweep + guarded claims), the late-result-after-close
# fence, terminal notifications, DRIVER_MAX_INFLIGHT, and the fg/bg flag.


BOOK2 = uuid.uuid4()
PLAN2 = uuid.uuid4()


def _age_heartbeat(runs: FakeRunsRepo, run_id, *, secs: int) -> None:
    """Backdate the run's driver heartbeat (simulates a driver task a restart
    killed: the row stays 'running' but nothing bumps the heartbeat)."""
    r = runs.rows[run_id]
    runs.rows[run_id] = r.model_copy(update={
        "driver_heartbeat_at": datetime.now(timezone.utc) - timedelta(seconds=secs),
    })


async def _drain(run_id) -> None:
    """Await the run's spawned driver task, if any."""
    from app.services import authoring_run_service as mod

    task = mod._DRIVER_TASKS.get(run_id)
    if task is not None:
        await task


async def test_create_background_flag_persisted_and_default_false():
    svc, _, _ = make_svc()
    fg = await make_run(svc)
    assert fg.background is False
    bg = await svc.create(
        OWNER, BOOK, plan_run_id=PLAN, level=3, scope=[str(CH1)],
        budget_usd=Decimal("1"), tool_allowlist=["t"], background=True,
    )
    assert bg.background is True


async def test_sweep_claims_stale_and_skips_fresh_heartbeat():
    from app.config import settings

    svc, runs, plans = make_svc()
    plans.add(OWNER, BOOK2, PLAN2, "validated")
    # Stale: 'running' on BOOK, heartbeat far older than the threshold (its
    # driver died with a restart).
    stale = await _running_run(svc, runs, scope=[CH1, CH2])
    _age_heartbeat(runs, stale.run_id, secs=settings.authoring_heartbeat_stale_secs + 60)
    # Fresh: 'running' on BOOK2 with a just-bumped heartbeat (live driver
    # elsewhere — e.g. another replica).
    fresh = await svc.create(
        OWNER, BOOK2, plan_run_id=PLAN2, level=3, scope=[str(CH3)],
        budget_usd=Decimal("1"), tool_allowlist=["t"],
    )
    await svc.gate(OWNER, fresh.run_id, book_chapter_ids={str(CH3)})
    await runs.transition(
        OWNER, fresh.run_id, from_statuses=("gated",), to_status="running",
        claim_driver_id="other-replica",
    )

    claimed = await svc.sweep_stale_runs()
    assert [r.run_id for r in claimed] == [stale.run_id]
    await _drain(stale.run_id)
    # the stale run resumed and completed; the fresh one was left alone
    assert (await runs.get_for_owner(OWNER, stale.run_id)).status == "report_ready"
    untouched = await runs.get_for_owner(OWNER, fresh.run_id)
    assert untouched.status == "running"
    assert untouched.driver_id == "other-replica"


async def test_claim_race_two_claimants_one_wins():
    svc, runs, _ = make_svc()
    run = await _running_run(svc, runs)
    _age_heartbeat(runs, run.run_id, secs=10_000)
    # Two sweepers race the same stale run: the first guarded claim sets
    # driver_id + a fresh heartbeat, so the second finds nothing stale.
    a = await runs.claim_stale_running(driver_id="driver-A", stale_secs=3600, limit=10)
    b = await runs.claim_stale_running(driver_id="driver-B", stale_secs=3600, limit=10)
    assert [r.run_id for r in a] == [run.run_id]
    assert b == []
    assert (await runs.get_for_owner(OWNER, run.run_id)).driver_id == "driver-A"


async def test_per_unit_claim_stops_paused_run_before_seam():
    seam = FakeSeam()
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    await runs.transition(OWNER, run.run_id, from_statuses=("running",), to_status="paused")
    await svc.run_driver(OWNER, run.run_id)
    assert seam.calls == []  # the guarded per-unit claim failed BEFORE the seam


async def test_per_unit_claim_stops_stolen_run_at_unit_boundary():
    """A sweep steal (another driver claimed after a stale heartbeat) stops the
    old driver at the next unit boundary — no second seam call."""
    holder: dict[str, Any] = {}

    async def steal_during_first_unit(call_no, kw):
        if call_no == 1:
            runs = holder["runs"]
            _age_heartbeat(runs, holder["run_id"], secs=10_000)
            await runs.claim_stale_running(
                driver_id="thief-driver", stale_secs=3600, limit=10,
            )

    seam = FakeSeam(on_call=steal_during_first_unit)
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    holder.update(runs=runs, run_id=run.run_id)
    await svc.run_driver(OWNER, run.run_id)
    assert len(seam.calls) == 1  # unit 2 never started under the old driver
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "running"           # the thief now owns the run
    assert final.driver_id == "thief-driver"
    assert final.current_unit == 1             # unit 1's progress recorded


async def test_late_result_after_close_lands_failed_not_drafted():
    """The known race: the run is paused+closed (e.g. before a Revert-All)
    while the seam is mid-flight — the late drafted result must be swallowed
    (unit failed 'run closed mid-flight'), never a fresh drafted row."""
    holder: dict[str, Any] = {}

    async def close_mid_flight(call_no, kw):
        await holder["runs"].transition(
            OWNER, holder["run_id"], from_statuses=("running",), to_status="paused",
        )
        await holder["svc"].close(OWNER, holder["run_id"])

    seam = FakeSeam(
        on_call=close_mid_flight,
        default=DraftOutcome(ok=True, cost_usd=Decimal("0.03")),
    )
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    holder.update(svc=svc, runs=runs, run_id=run.run_id)
    await svc.run_driver(OWNER, run.run_id)
    assert len(seam.calls) == 1
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["failed"]  # NOT drafted
    assert units[0].error_message == "run closed mid-flight"
    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "closed"                 # the close stands
    assert final.spent_usd == Decimal("0.03")       # the real spend still lands


async def test_late_result_while_paused_still_drafts():
    """Pause (without close) mid-seam is NOT a swallow: paused is a resumable
    stop, the drafted row is the resume point."""
    holder: dict[str, Any] = {}

    async def pause_mid_flight(call_no, kw):
        if call_no == 1:
            await holder["runs"].transition(
                OWNER, holder["run_id"], from_statuses=("running",), to_status="paused",
            )

    seam = FakeSeam(on_call=pause_mid_flight)
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    holder.update(runs=runs, run_id=run.run_id)
    await svc.run_driver(OWNER, run.run_id)
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted"]


async def test_notification_fired_on_report_ready():
    notify = NotifyRecorder()
    svc, runs, _ = make_svc(notify=notify)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"
    assert len(notify.calls) == 1
    call = notify.calls[0]
    assert call["user_id"] == OWNER
    assert call["category"] == "system"
    meta = call["metadata"]
    assert meta["operation"] == "autonomous_authoring"
    assert meta["run_id"] == str(run.run_id)
    assert meta["book_id"] == str(BOOK)
    assert meta["status"] == "report_ready"
    assert meta["units_drafted"] == 2
    assert meta["spent_usd"] == str(run.spent_usd)


async def test_notification_fired_on_failed():
    notify = NotifyRecorder()
    seam = FakeSeam(outcomes=[
        DraftOutcome(ok=True, cost_usd=Decimal("0.01")),
        DraftOutcome(ok=False, error="engine 502"),
    ])
    svc, runs, _ = make_svc(seam=seam, notify=notify)
    run = await _completed_run(svc, runs)
    assert run.status == "failed"
    assert len(notify.calls) == 1
    meta = notify.calls[0]["metadata"]
    assert meta["status"] == "failed"
    assert meta["units_drafted"] == 1  # unit 0 drafted before the stop


async def test_notification_failure_swallowed_run_unaffected():
    notify = NotifyRecorder(raise_on_call=True)
    svc, runs, _ = make_svc(notify=notify)
    run = await _completed_run(svc, runs)   # must not raise
    assert run.status == "report_ready"     # terminal state stands
    assert len(notify.calls) == 1           # the notify WAS attempted


async def test_notification_not_fired_on_pause():
    notify = NotifyRecorder()
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.06")))
    svc, runs, _ = make_svc(seam=seam, notify=notify)
    run = await _running_run(svc, runs, budget="0.05")
    await svc.run_driver(OWNER, run.run_id)
    assert (await runs.get_for_owner(OWNER, run.run_id)).status == "paused"
    assert notify.calls == []  # budget-pause is not a terminal


async def test_max_inflight_start_defers_and_sweep_respects_cap(monkeypatch):
    from app.config import settings
    from app.services import authoring_run_service as mod

    monkeypatch.setattr(settings, "authoring_driver_max_inflight", 1)
    gate_evt = asyncio.Event()

    async def block_until_released(call_no, kw):
        await gate_evt.wait()

    seam = FakeSeam(on_call=block_until_released)
    svc, runs, plans = make_svc(seam=seam)
    plans.add(OWNER, BOOK2, PLAN2, "validated")

    # Run A occupies the single driver slot (its seam blocks).
    run_a = await make_run(svc, scope=[CH1])
    await svc.gate(OWNER, run_a.run_id, book_chapter_ids=BOOK_CHAPTERS)
    await svc.start(OWNER, run_a.run_id)
    assert run_a.run_id in mod._DRIVER_TASKS
    await asyncio.sleep(0)  # let the driver reach the blocking seam

    # Run B starts (transition succeeds) but the spawn is DEFERRED at the cap.
    run_b = await svc.create(
        OWNER, BOOK2, plan_run_id=PLAN2, level=3, scope=[str(CH3)],
        budget_usd=Decimal("1"), tool_allowlist=["t"],
    )
    await svc.gate(OWNER, run_b.run_id, book_chapter_ids={str(CH3)})
    started_b = await svc.start(OWNER, run_b.run_id)
    assert started_b.status == "running"
    assert run_b.run_id not in mod._DRIVER_TASKS  # no task — slot busy

    # Sweep respects the cap: B's heartbeat is stale but there is no capacity.
    _age_heartbeat(runs, run_b.run_id, secs=10_000)
    assert await svc.sweep_stale_runs() == []

    # A finishes → slot frees → the next sweep resumes B from its cursor.
    gate_evt.set()
    await _drain(run_a.run_id)
    assert (await runs.get_for_owner(OWNER, run_a.run_id)).status == "report_ready"
    claimed = await svc.sweep_stale_runs()
    assert [r.run_id for r in claimed] == [run_b.run_id]
    await _drain(run_b.run_id)
    assert (await runs.get_for_owner(OWNER, run_b.run_id)).status == "report_ready"


async def test_sweep_resume_from_cursor_e2e():
    """Restart durability e2e: a run 'orphaned' mid-scope (driver task gone,
    heartbeat stale, unit 0 already drafted) is swept, resumed from
    current_unit, and completes — without re-drafting unit 0."""
    from app.config import settings

    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, scope=[CH1, CH2, CH3])
    # Simulate the pre-restart driver's progress: unit 0 drafted + cursor at 1,
    # then the process died (stale heartbeat, no task).
    await svc._units.upsert_pending(OWNER, run.run_id, 0, CH1, pre_revision_id=uuid.uuid4())
    await svc._units.mark_drafted(
        OWNER, run.run_id, 0, post_revision_id=uuid.uuid4(), cost_usd=Decimal("0.01"),
    )
    await runs.record_unit_progress(
        OWNER, run.run_id, add_spent_usd=Decimal("0.01"), current_unit=1,
    )
    _age_heartbeat(runs, run.run_id, secs=settings.authoring_heartbeat_stale_secs + 60)

    claimed = await svc.sweep_stale_runs()
    assert [r.run_id for r in claimed] == [run.run_id]
    await _drain(run.run_id)

    final = await runs.get_for_owner(OWNER, run.run_id)
    assert final.status == "report_ready"
    assert final.current_unit == 3
    # only the remaining units were drafted on resume — unit 0 untouched
    assert [c["chapter_id"] for c in seam.calls] == [CH2, CH3]
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted", "drafted", "drafted"]
