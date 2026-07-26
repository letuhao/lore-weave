"""Authoring-run FSM + start-gate + v1 driver unit tests (RAID Wave D2, DR-D)
+ the D3 per-unit ledger / Run Report / accept-reject / Revert-All
+ the D5 per-unit continuity critic (verdict ledger + critic_severe breaker).

Tenancy (spec 25 Stage-1 re-key): the repos + service are BARE-ID — reads key on
run_id/book_id, writes stamp `created_by` as a plain actor (STORED, never filtered
on). Access is decided BEFORE the repo, at the E0 book-grant gate (the route/MCP/
confirm-dispatch layer, covered by test_authoring_run_tenancy.py). So these fakes
carry no owner-scoping; `OWNER` here is only the `created_by` stamp the run is
created with (spend/bearer identity + the notification target).

Fakes mirror the repo's OCC semantics exactly: transition() is a guarded
compare-and-set (wrong-from → None) and →gated raises UniqueViolationError
when another run is active on the same book (the partial-index scope fence).
The driver is exercised directly (run_driver) with a FAKE drafting seam, a
FAKE revision capture (the book-service revisions-list seam) and a FAKE
critic seam (the engine judge_prose seam).
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from app.db.models import AuthoringRun, AuthoringRunUnit, PlanRun
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.services.authoring_run_service import (
    ActiveRunOverlapError,
    AuthoringRunService,
    CriticVerdict,
    DraftOutcome,
    EngineDraftingSeam,
    TransitionConflictError,
    verdict_from_critique,
)

OWNER = uuid.uuid4()
BOOK = uuid.uuid4()
PLAN = uuid.uuid4()
CH1, CH2, CH3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
BOOK_CHAPTERS = {str(CH1), str(CH2), str(CH3)}

_ACTIVE = ("gated", "running", "paused")


class FakeRunsRepo:
    """Bare-id AuthoringRunsRepo double (spec 25): no owner filter anywhere;
    `created_by` is a stamp set at create. Guarded OCC transitions mirror the
    real ``UPDATE … WHERE status = ANY(from) RETURNING`` semantics."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, AuthoringRun] = {}

    async def create(self, created_by, book_id, *, plan_run_id, level, scope,
                     budget_usd, tool_allowlist, params=None,
                     background=False, pause_after_each_unit=True) -> AuthoringRun:
        run = AuthoringRun(
            run_id=uuid.uuid4(), created_by=created_by, book_id=book_id,
            plan_run_id=plan_run_id, level=level, scope=[str(c) for c in scope],
            budget_usd=Decimal(str(budget_usd)), tool_allowlist=tool_allowlist,
            params=params or {}, background=background,
            pause_after_each_unit=pause_after_each_unit,
        )
        self.rows[run.run_id] = run
        return run

    async def set_pause_policy(self, run_id, pause_after_each_unit) -> AuthoringRun | None:
        r = self.rows.get(run_id)
        if r is None or r.status == "closed":   # mirrors WHERE status != 'closed'
            return None
        updated = r.model_copy(update={"pause_after_each_unit": pause_after_each_unit})
        self.rows[run_id] = updated
        return updated

    async def get_by_id(self, run_id) -> AuthoringRun | None:
        return self.rows.get(run_id)

    async def list_for_book(self, book_id, *, limit=20):
        return [r for r in self.rows.values() if r.book_id == book_id][:limit]

    async def transition(self, run_id, *, from_statuses, to_status,
                         breaker_state=None, error_message=None,
                         claim_driver_id=None) -> AuthoringRun | None:
        r = self.rows.get(run_id)
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

    async def heartbeat_claim(self, run_id, driver_id) -> AuthoringRun | None:
        r = self.rows.get(run_id)
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

    async def record_unit_progress(self, run_id, *, add_spent_usd,
                                   current_unit,
                                   driver_id=None) -> AuthoringRun | None:
        r = self.rows.get(run_id)
        if r is None:
            return None
        # Mirrors the repo's CASE fence: spend always lands; the cursor write
        # is driver-fenced (a superseded driver must not move it).
        cursor_ok = driver_id is None or r.driver_id == driver_id
        updated = r.model_copy(update={
            "spent_usd": r.spent_usd + add_spent_usd,
            "current_unit": current_unit if cursor_ok else r.current_unit,
        })
        self.rows[run_id] = updated
        return updated

    async def release_claim(self, run_id, driver_id) -> bool:
        r = self.rows.get(run_id)
        if r is None or r.status != "running" or r.driver_id != driver_id:
            return False
        self.rows[run_id] = r.model_copy(update={"driver_heartbeat_at": None})
        return True


class FakePlanRuns:
    """Book-scoped PlanRunsRepo double (spec 25): `get_for_book(book_id, plan_id)`;
    `created_by` is a stamp, never a lookup key."""

    def __init__(self) -> None:
        self.rows: dict[tuple, PlanRun] = {}

    def add(self, created_by, book, plan_id, status) -> None:
        self.rows[(book, plan_id)] = PlanRun(
            id=plan_id, created_by=created_by, book_id=book, mode="rules", status=status,
        )

    async def get_for_book(self, book_id, plan_id) -> PlanRun | None:
        return self.rows.get((book_id, plan_id))


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
    """Bare-id AuthoringRunUnitsRepo double (spec 25): the units table carries no
    scope of its own — its scope IS the parent run (gated at the route). Upsert
    resets to pending; transitions are guarded compare-and-set; the parent-run
    existence/status/driver guards mirror the repo's JOIN + late-result fence."""

    def __init__(self, runs: FakeRunsRepo) -> None:
        self._runs = runs
        self.rows: dict[tuple[uuid.UUID, int], AuthoringRunUnit] = {}

    async def upsert_pending(self, run_id, unit_index, chapter_id, *,
                             pre_revision_id) -> AuthoringRunUnit | None:
        if run_id not in self._runs.rows:  # INSERT … SELECT parent-run guard
            return None
        unit = AuthoringRunUnit(
            run_id=run_id, unit_index=unit_index, chapter_id=chapter_id,
            pre_revision_id=pre_revision_id,
        )
        self.rows[(run_id, unit_index)] = unit
        return unit

    async def mark_drafted(self, run_id, unit_index, *, post_revision_id,
                           cost_usd, job_id=None, run_statuses=None,
                           run_driver_id=None) -> AuthoringRunUnit | None:
        return await self.transition_unit(
            run_id, unit_index, from_statuses=("pending",),
            to_status="drafted", post_revision_id=post_revision_id, cost_usd=cost_usd,
            job_id=job_id, run_statuses=run_statuses, run_driver_id=run_driver_id,
        )

    async def mark_failed(self, run_id, unit_index, *, error) -> AuthoringRunUnit | None:
        return await self.transition_unit(
            run_id, unit_index, from_statuses=("pending",),
            to_status="failed", error_message=error,
        )

    async def set_critic_verdict(self, run_id, unit_index, *,
                                 verdict) -> AuthoringRunUnit | None:
        # D5: mirrors the repo — guarded on the unit still being 'drafted' (a
        # raced-away row loses cleanly → None).
        u = self.rows.get((run_id, unit_index))
        if u is None or u.status != "drafted":
            return None
        updated = u.model_copy(update={"critic_verdict": verdict})
        self.rows[(run_id, unit_index)] = updated
        return updated

    async def transition_unit(self, run_id, unit_index, *, from_statuses,
                              to_status, post_revision_id=None, cost_usd=None,
                              error_message=None, job_id=None, run_statuses=None,
                              run_driver_id=None) -> AuthoringRunUnit | None:
        parent = self._runs.rows.get(run_id)
        if parent is None:  # mirrors the FROM authoring_runs r JOIN
            return None
        if run_statuses is not None:  # D4 late-result fence (parent-run guard)
            if parent.status not in run_statuses:
                return None
        if run_driver_id is not None:  # D4 sweep-steal fence (parent driver)
            if parent.driver_id != run_driver_id:
                return None
        u = self.rows.get((run_id, unit_index))
        if u is None or u.status not in from_statuses:
            return None
        update: dict[str, Any] = {"status": to_status}
        if post_revision_id is not None:
            update["post_revision_id"] = post_revision_id
        if cost_usd is not None:
            update["cost_usd"] = cost_usd
        if job_id is not None:
            update["job_id"] = job_id
        if error_message is not None:
            update["error_message"] = error_message
        updated = u.model_copy(update=update)
        self.rows[(run_id, unit_index)] = updated
        return updated

    async def get_for_run(self, run_id, unit_index) -> AuthoringRunUnit | None:
        return self.rows.get((run_id, unit_index))

    async def list_for_run(self, run_id) -> list[AuthoringRunUnit]:
        return sorted(
            (u for (rid, _), u in self.rows.items() if rid == run_id),
            key=lambda u: u.unit_index,
        )


class FakeRevisionCapture:
    """Issues a fresh revision id per call (so pre != post per unit; call order
    is pre0, post0, pre1, post1, …). `fail_on_call` (1-based) raises there;
    `empty=True` models a chapter with no revisions yet (returns None). Mirrors
    the RevisionCapture contract: `created_by` actor stamp, never a filter."""

    def __init__(self, *, fail_on_call: set[int] | None = None, empty: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.issued: list[uuid.UUID] = []
        self.fail_on_call = fail_on_call or set()
        self.empty = empty

    async def latest_revision_id(self, *, created_by, book_id, chapter_id):
        self.calls.append(dict(
            created_by=created_by, book_id=book_id, chapter_id=chapter_id,
        ))
        if len(self.calls) in self.fail_on_call:
            raise RuntimeError("book-service revisions unavailable")
        if self.empty:
            return None
        rid = uuid.uuid4()
        self.issued.append(rid)
        return rid


class FakeCriticSeam:
    """Mirrors the CriticSeam contract (D5). `verdicts` are consumed in call
    order (then `default`); `raise_on_call` (1-based) raises there — the driver
    must degrade to a warn verdict, never fail the run."""

    def __init__(self, verdicts=None,
                 default=CriticVerdict(severity="ok", summary="all dims clear"),
                 raise_on_call: set[int] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.verdicts = list(verdicts or [])
        self.default = default
        self.raise_on_call = raise_on_call or set()

    async def critique(self, **kw) -> CriticVerdict:
        self.calls.append(kw)
        if len(self.calls) in self.raise_on_call:
            raise RuntimeError("judge model unavailable")
        return self.verdicts.pop(0) if self.verdicts else self.default


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
             driver_id=None, critic=None, late_restore=None, corrections=None):
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
        # D5: always inject a fake critic (never the real EngineCriticSeam —
        # it fetches the draft over HTTP). Default: 'ok' verdicts, zero cost,
        # so pre-D5 driver assertions (spend, statuses) are unaffected.
        critic=critic or FakeCriticSeam(),
        # Late-swallow restore spy (never the real book-service call).
        late_restore=late_restore or RestoreRecorder(),
        corrections=corrections,  # BE-9b: None → no capture (most tests); a recorder for the capture test
    )
    return svc, runs, plans


class FakeCorrections:
    """BE-9b recorder — captures record_for_job calls without a DB."""
    def __init__(self):
        self.calls: list[tuple] = []

    async def record_for_job(self, job_id, *, created_by, kind, changed_blocks=None):
        self.calls.append((job_id, created_by, kind))
        return object()


async def make_run(svc, *, scope=None, budget="1.00", allowlist=None, level=3,
                   params=None, pause_after_each_unit=False):
    # NOTE: defaults to pause_after_each_unit=False (unlike the real service's
    # own safe default of True) so the many pre-existing "drafts every unit
    # back-to-back" driver tests in this file keep exercising that behavior
    # unmodified. Tests of the D-AGENT-MODE pause_after_each_unit feature itself
    # pass pause_after_each_unit=True explicitly. OWNER is the `created_by` stamp.
    return await svc.create(
        OWNER, BOOK, plan_run_id=PLAN, level=level,
        scope=[str(c) for c in (scope if scope is not None else [CH1, CH2])],
        budget_usd=Decimal(budget),
        tool_allowlist=allowlist if allowlist is not None else ["composition_write_prose"],
        params=params, pause_after_each_unit=pause_after_each_unit,
    )


# ── create + gate happy path ────────────────────────────────────────────────


async def test_create_draft_and_gate_happy():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    assert run.status == "draft"
    gated = await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    assert gated.status == "gated"


async def test_create_unknown_plan_404():
    svc, _, _ = make_svc()
    with pytest.raises(LookupError):
        await svc.create(
            OWNER, BOOK, plan_run_id=uuid.uuid4(), level=3, scope=[str(CH1)],
            budget_usd=Decimal("1"), tool_allowlist=["composition_write_prose"],
        )


async def test_gate_accepts_compiled_plan_too():
    svc, _, _ = make_svc(plan_status="compiled")
    run = await make_run(svc)
    gated = await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    assert gated.status == "gated"


# ── gate rejections (all-or-nothing) ────────────────────────────────────────


async def test_gate_rejects_unapproved_plan():
    svc, _, _ = make_svc(plan_status="proposed")
    run = await make_run(svc)
    with pytest.raises(ValueError, match="approved"):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_empty_scope():
    svc, _, _ = make_svc()
    run = await make_run(svc, scope=[])
    with pytest.raises(ValueError, match="scope is empty"):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_foreign_chapters():
    svc, _, _ = make_svc()
    foreign = uuid.uuid4()
    run = await make_run(svc, scope=[CH1, foreign])
    with pytest.raises(ValueError, match="not in this book"):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_zero_budget():
    svc, _, _ = make_svc()
    run = await make_run(svc, budget="0")
    with pytest.raises(ValueError, match="budget_usd"):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_empty_allowlist():
    svc, _, _ = make_svc()
    run = await make_run(svc, allowlist=[])
    with pytest.raises(ValueError, match="tool_allowlist"):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_blank_allowlist_entries():
    svc, _, _ = make_svc()
    run = await make_run(svc, allowlist=["ok", "  "])
    with pytest.raises(ValueError, match="tool_allowlist"):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_rejects_non_allowlistable_tool_name():
    """IN-3 backstop (mcp-tool-io.md, /review-impl): gate() is the ONE chokepoint
    both REST and MCP funnel through — re-validates against the same closed set
    the schema-level Literal[] enforces, in case a caller ever bypasses it."""
    svc, _, _ = make_svc()
    run = await make_run(svc, allowlist=["not_a_real_tool"])
    with pytest.raises(ValueError, match="unknown/non-drafting tool"):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_accepts_a_real_allowlistable_tool():
    svc, _, _ = make_svc()
    run = await make_run(svc, allowlist=["composition_write_prose"])
    gated = await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    assert gated.status == "gated"


async def test_gate_overlap_active_run_409():
    svc, runs, _ = make_svc()
    first = await make_run(svc)
    await svc.gate(first.run_id, book_chapter_ids=BOOK_CHAPTERS)
    second = await make_run(svc, scope=[CH3])
    with pytest.raises(ActiveRunOverlapError):
        await svc.gate(second.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_on_non_draft_conflicts():
    svc, _, _ = make_svc()
    run = await make_run(svc)
    await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    with pytest.raises(TransitionConflictError):
        await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)


async def test_gate_unknown_run_404():
    """A missing run raises LookupError (routers map to 404, no existence
    oracle). Owner-scoping is gone from the service (spec 25): a run's access is
    decided at the route BEFORE this call — see test_authoring_run_tenancy.py."""
    svc, _, _ = make_svc()
    with pytest.raises(LookupError):
        await svc.gate(uuid.uuid4(), book_chapter_ids=BOOK_CHAPTERS)


# ── race-guarded transitions ────────────────────────────────────────────────


async def test_start_requires_gated():
    svc, _, _ = make_svc()
    run = await make_run(svc)
    with pytest.raises(TransitionConflictError):
        await svc.start(run.run_id)  # still draft


async def test_pause_requires_running_and_resume_requires_paused():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    with pytest.raises(TransitionConflictError):
        await svc.pause(run.run_id)
    with pytest.raises(TransitionConflictError):
        await svc.resume(run.run_id)


async def test_close_not_allowed_from_running():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    await runs.transition(run.run_id, from_statuses=("gated",), to_status="running")
    with pytest.raises(TransitionConflictError):
        await svc.close(run.run_id)


async def test_close_releases_fence_for_next_run():
    svc, _, _ = make_svc()
    first = await make_run(svc)
    await svc.gate(first.run_id, book_chapter_ids=BOOK_CHAPTERS)
    closed = await svc.close(first.run_id)
    assert closed.status == "closed"
    second = await make_run(svc)
    gated = await svc.gate(second.run_id, book_chapter_ids=BOOK_CHAPTERS)
    assert gated.status == "gated"


async def test_repo_guarded_transition_wrong_from_noops():
    runs = FakeRunsRepo()
    run = await runs.create(
        OWNER, BOOK, plan_run_id=PLAN, level=3, scope=[str(CH1)],
        budget_usd=Decimal("1"), tool_allowlist=["composition_write_prose"],
    )
    out = await runs.transition(
        run.run_id, from_statuses=("running",), to_status="paused",
    )
    assert out is None
    assert (await runs.get_by_id(run.run_id)).status == "draft"


# ── driver (fake seam) ──────────────────────────────────────────────────────


async def _running_run(svc, runs, **kw):
    run = await make_run(svc, **kw)
    await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    # →running CLAIMS for the service's driver (D4) — like svc.start, without
    # spawning the background task (tests drive run_driver synchronously).
    await runs.transition(
        run.run_id, from_statuses=("gated",), to_status="running",
        claim_driver_id=svc._driver_id,
    )
    return run


async def test_driver_success_path_report_ready():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
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
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    est = Decimal(str(settings.authoring_unit_estimate_usd))
    assert final.spent_usd == est * 2


async def test_driver_budget_exceeded_auto_pauses_with_breaker():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.06")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, budget="0.05")
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
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
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
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
                svc_holder["run_id"],
                from_statuses=("running",), to_status="paused",
            )

    seam = FakeSeam(on_call=pause_during_first_unit)
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    svc_holder.update(runs=runs, run_id=run.run_id)
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
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
        run.run_id, add_spent_usd=Decimal("0.01"), current_unit=1,
    )
    await runs.transition(run.run_id, from_statuses=("running",), to_status="paused")
    resumed = await svc.resume(run.run_id)
    assert resumed.status == "running"
    # drive synchronously (the spawned task is also live; run_driver is idempotent
    # over the guarded transitions — the loser of any race just no-ops)
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
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
    await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    started = await svc.start(run.run_id)
    assert started.status == "running"
    from app.services import authoring_run_service as mod

    task = mod._DRIVER_TASKS.get(run.run_id)
    assert task is not None
    await task
    final = await runs.get_by_id(run.run_id)
    assert final.status == "report_ready"


# ── D-AGENT-MODE §20 D4: server-side auto-pause-after-each-unit ────────────


async def test_create_pause_after_each_unit_defaults_true():
    """The service's own Python default (mirrors the DB column default) — the
    REST/MCP callers always pass it explicitly, but a bare svc.create() call
    (e.g. a future internal caller) still gets the SAFE default."""
    svc, _, _ = make_svc()
    run = await svc.create(
        OWNER, BOOK, plan_run_id=PLAN, level=3, scope=[str(CH1)],
        budget_usd=Decimal("1"), tool_allowlist=["composition_write_prose"],
    )
    assert run.pause_after_each_unit is True


async def test_driver_pauses_at_boundary_when_policy_on_and_more_scope_remains():
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, pause_after_each_unit=True)
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    assert final.status == "paused"
    assert final.breaker_state == {"reason": "pause_after_each_unit", "unit": 0}
    assert final.current_unit == 1           # unit 0's progress stands (resume point)
    assert len(seam.calls) == 1               # unit 1 never started
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted"]


async def test_driver_pause_after_each_unit_resume_drafts_next_then_completes():
    """Resuming a pause_after_each_unit stop drafts exactly the next unit, then
    (being the LAST unit) proceeds straight to report_ready without pausing
    again."""
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, pause_after_each_unit=True)
    await svc.run_driver(run.run_id)
    assert (await runs.get_by_id(run.run_id)).status == "paused"
    resumed = await svc.resume(run.run_id)
    assert resumed.status == "running"
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    assert final.status == "report_ready"     # no second pause — it was the last unit
    assert len(seam.calls) == 2
    assert [c["chapter_id"] for c in seam.calls] == [CH1, CH2]
    from app.services import authoring_run_service as mod

    task = mod._DRIVER_TASKS.get(run.run_id)
    if task is not None:
        await task


async def test_driver_pause_after_each_unit_does_not_pause_on_last_unit():
    """A single-unit scope never pauses on pause_after_each_unit — it proceeds
    straight to the existing end-of-scope report_ready path."""
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, scope=[CH1], pause_after_each_unit=True)
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    assert final.status == "report_ready"
    assert len(seam.calls) == 1


async def test_driver_pause_after_each_unit_false_drafts_back_to_back():
    """Explicit-false regression: the whole scope drafts unattended (mirrors
    the pre-D-AGENT-MODE ground truth), matching test_driver_success_path."""
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, pause_after_each_unit=False)
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    assert final.status == "report_ready"
    assert len(seam.calls) == 2


async def test_driver_pause_after_each_unit_notifies():
    notify = NotifyRecorder()
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam, notify=notify)
    run = await _running_run(svc, runs, pause_after_each_unit=True)
    await svc.run_driver(run.run_id)
    assert (await runs.get_by_id(run.run_id)).status == "paused"
    assert len(notify.calls) == 1
    call = notify.calls[0]
    assert "paused (pause_after_each_unit)" in call["title"]
    assert call["metadata"]["status"] == "paused"


async def test_driver_pause_after_each_unit_does_not_override_budget_stop():
    """The budget check runs FIRST at the TOP of the loop, before any unit is
    drafted — if budget is already exhausted going into a unit (e.g. resuming
    after a prior unit's spend), that stop wins (breaker reason 'budget') and
    the seam never runs, regardless of pause_after_each_unit. (The reverse
    order — pause_after_each_unit firing for a unit whose OWN cost pushes past
    budget — is exercised by test_driver_pauses_at_boundary_when_policy_on…:
    the pause_after_each_unit check runs immediately after that unit's own
    critique, before the loop ever revisits the budget check.)"""
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs, budget="0.05", pause_after_each_unit=True)
    # Simulate unit 0 already drafted+spent in a prior segment (resume point).
    await runs.record_unit_progress(
        run.run_id, add_spent_usd=Decimal("0.05"), current_unit=1,
    )
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    assert final.status == "paused"
    assert final.breaker_state["reason"] == "budget"
    assert seam.calls == []           # unit 1 never even started


async def test_set_pause_policy_updates_flag():
    svc, runs, _ = make_svc()
    run = await make_run(svc, pause_after_each_unit=True)
    updated = await svc.set_pause_policy(run.run_id, False)
    assert updated.pause_after_each_unit is False
    again = await svc.set_pause_policy(run.run_id, True)
    assert again.pause_after_each_unit is True


async def test_set_pause_policy_blocked_when_closed():
    svc, runs, _ = make_svc()
    run = await make_run(svc)
    closed = await svc.close(run.run_id)
    assert closed.status == "closed"
    with pytest.raises(TransitionConflictError):
        await svc.set_pause_policy(run.run_id, True)


async def test_set_pause_policy_unknown_run_404():
    """A missing run raises LookupError (owner-scoping removed by spec 25 — the
    route decides access before the service; see test_authoring_run_tenancy.py)."""
    svc, runs, _ = make_svc()
    with pytest.raises(LookupError):
        await svc.set_pause_policy(uuid.uuid4(), True)


async def test_set_pause_policy_allowed_while_running():
    """A run-header toggle mid-run (D4a) — allowed at any non-closed status,
    not gated to the reviewable statuses."""
    svc, runs, _ = make_svc()
    run = await _running_run(svc, runs)
    updated = await svc.set_pause_policy(run.run_id, True)
    assert updated.pause_after_each_unit is True
    assert updated.status == "running"


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
    await svc.run_driver(run.run_id)
    return await runs.get_by_id(run.run_id)


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
    await svc.gate(run.run_id, book_chapter_ids=BOOK_CHAPTERS)
    await runs.transition(run.run_id, from_statuses=("gated",), to_status="running")
    running = await runs.get_by_id(run.run_id)
    with pytest.raises(TransitionConflictError):
        await svc.unit_report(running)


async def test_unit_report_readable_after_close():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    closed = await svc.close(run.run_id)
    rows = await svc.unit_report(closed)
    assert len(rows) == 2


# ── D3: accept / reject ─────────────────────────────────────────────────────


async def test_accept_unit_drafted_to_accepted():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    unit = await svc.accept_unit(run.run_id, 0)
    assert unit.status == "accepted"
    with pytest.raises(TransitionConflictError, match="accept requires"):
        await svc.accept_unit(run.run_id, 0)  # already accepted


async def test_accept_unknown_unit_and_unknown_run_404():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    with pytest.raises(LookupError, match="unit not found"):
        await svc.accept_unit(run.run_id, 99)
    # missing run → run not found (routers 404; access is gated at the route now)
    with pytest.raises(LookupError, match="run not found"):
        await svc.accept_unit(uuid.uuid4(), 0)


async def test_review_blocked_while_running():
    svc, runs, _ = make_svc()
    run = await _running_run(svc, runs)
    with pytest.raises(TransitionConflictError, match="review requires"):
        await svc.accept_unit(run.run_id, 0)
    with pytest.raises(TransitionConflictError, match="review requires"):
        await svc.reject_unit(run.run_id, 0, restore=RestoreRecorder())


async def test_reject_restores_pre_revision_then_marks_rejected():
    cap = FakeRevisionCapture()
    svc, runs, _ = make_svc(revisions=cap)
    run = await _completed_run(svc, runs)
    restore = RestoreRecorder()
    unit, cascade, reverted = await svc.reject_unit(run.run_id, 0, restore=restore)
    assert unit.status == "rejected"
    assert reverted is True
    # restored the chapter to ITS pre-run baseline (unit 0's pre = issued[0])
    assert restore.calls == [(BOOK, CH1, cap.issued[0])]
    # cascade warning: unit 1 is still drafted downstream of the rejected unit 0
    assert cascade == [1]


async def test_reject_captures_reject_correction_be9b():
    """BE-9b — a reject on a unit whose draft carried a job_id records a kind='reject'
    generation_correction on that job (the human-gate taste signal, previously discarded)."""
    JOB = uuid.uuid4()
    corrections = FakeCorrections()
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01"), job_id=JOB))
    svc, runs, _ = make_svc(seam=seam, corrections=corrections)
    run = await _completed_run(svc, runs)
    await svc.reject_unit(run.run_id, 0, restore=RestoreRecorder())
    assert corrections.calls == [(JOB, OWNER, "reject")]


async def test_reject_with_null_job_id_records_nothing_be9b():
    """BE-9a: a pre-BE-9a unit (job_id NULL) records NO correction — never backfill a guess that
    would attribute the author's rejection to someone else's generation."""
    corrections = FakeCorrections()
    svc, runs, _ = make_svc(corrections=corrections)  # default seam → DraftOutcome.job_id is None
    run = await _completed_run(svc, runs)
    await svc.reject_unit(run.run_id, 0, restore=RestoreRecorder())
    assert corrections.calls == []


async def test_reject_restore_failure_leaves_unit_drafted():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    restore = RestoreRecorder(fail_on_call={1})
    with pytest.raises(RuntimeError, match="restore 502"):
        await svc.reject_unit(run.run_id, 0, restore=restore)
    unit = await svc._units.get_for_run(run.run_id, 0)
    assert unit.status == "drafted"  # NEVER rejected without the actual revert


async def test_reject_without_pre_revision_skips_restore():
    svc, runs, _ = make_svc(revisions=FakeRevisionCapture(empty=True))
    run = await _completed_run(svc, runs)
    restore = RestoreRecorder()
    unit, cascade, reverted = await svc.reject_unit(run.run_id, 1, restore=restore)
    assert unit.status == "rejected"
    assert reverted is False
    assert restore.calls == []       # nothing to restore to
    assert cascade == []             # no drafted/accepted units after index 1


async def test_reject_non_drafted_unit_conflicts():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)
    await svc.accept_unit(run.run_id, 0)
    with pytest.raises(TransitionConflictError, match="reject requires"):
        await svc.reject_unit(run.run_id, 0, restore=RestoreRecorder())


# ── D3: Revert-All ──────────────────────────────────────────────────────────


async def test_revert_all_reverse_order_and_closes_run():
    cap = FakeRevisionCapture()
    svc, runs, _ = make_svc(revisions=cap)
    run = await _completed_run(svc, runs, scope=[CH1, CH2, CH3])
    await svc.accept_unit(run.run_id, 0)  # accepted units revert too
    restore = RestoreRecorder()
    result = await svc.revert_all(run.run_id, restore=restore)
    # downstream-first: unit 2, then 1, then 0 — restores unwind cleanly
    assert [c[1] for c in restore.calls] == [CH3, CH2, CH1]
    assert restore.calls[0][2] == cap.issued[4]  # unit 2's pre (pre2 = 5th issued)
    assert result["reverted_unit_indexes"] == [2, 1, 0]
    assert result["failed_unit_index"] is None
    assert result["closed"] is True
    assert (await runs.get_by_id(run.run_id)).status == "closed"
    units = await svc._units.list_for_run(run.run_id)
    assert all(u.status == "rejected" for u in units)


async def test_revert_all_partial_failure_stops_and_reports():
    svc, runs, _ = make_svc()
    run = await _completed_run(svc, runs)  # units 0, 1 drafted
    restore = RestoreRecorder(fail_on_call={2})  # unit 1 reverts, unit 0 fails
    result = await svc.revert_all(run.run_id, restore=restore)
    assert result["reverted_unit_indexes"] == [1]
    assert result["failed_unit_index"] == 0
    assert "restore 502" in result["error"]
    assert result["closed"] is False
    # run untouched; unit 0 still drafted (re-runnable), unit 1 rejected
    assert (await runs.get_by_id(run.run_id)).status == "report_ready"
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
    result = await svc.revert_all(run.run_id, restore=restore)
    assert result["reverted_unit_indexes"] == [0]  # only the drafted unit
    assert result["closed"] is True
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["rejected", "failed"]


async def test_revert_all_wrong_status_conflicts():
    svc, runs, _ = make_svc()
    run = await _running_run(svc, runs)
    with pytest.raises(TransitionConflictError, match="revert-all requires"):
        await svc.revert_all(run.run_id, restore=RestoreRecorder())


async def test_revert_all_unknown_run_404():
    """A missing run raises LookupError (owner-scoping removed by spec 25 — the
    route decides access before the service; see test_authoring_run_tenancy.py)."""
    svc, runs, _ = make_svc()
    with pytest.raises(LookupError):
        await svc.revert_all(uuid.uuid4(), restore=RestoreRecorder())


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
        budget_usd=Decimal("1"), tool_allowlist=["composition_write_prose"], background=True,
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
        budget_usd=Decimal("1"), tool_allowlist=["composition_write_prose"],
    )
    await svc.gate(fresh.run_id, book_chapter_ids={str(CH3)})
    await runs.transition(
        fresh.run_id, from_statuses=("gated",), to_status="running",
        claim_driver_id="other-replica",
    )

    claimed = await svc.sweep_stale_runs()
    assert [r.run_id for r in claimed] == [stale.run_id]
    await _drain(stale.run_id)
    # the stale run resumed and completed; the fresh one was left alone
    assert (await runs.get_by_id(stale.run_id)).status == "report_ready"
    untouched = await runs.get_by_id(fresh.run_id)
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
    assert (await runs.get_by_id(run.run_id)).driver_id == "driver-A"


async def test_per_unit_claim_stops_paused_run_before_seam():
    seam = FakeSeam()
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    await runs.transition(run.run_id, from_statuses=("running",), to_status="paused")
    await svc.run_driver(run.run_id)
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
    await svc.run_driver(run.run_id)
    assert len(seam.calls) == 1  # unit 2 never started under the old driver
    final = await runs.get_by_id(run.run_id)
    assert final.status == "running"           # the thief now owns the run
    assert final.driver_id == "thief-driver"
    # Driver-fenced late writes: the superseded driver's result must not move
    # the cursor (the thief re-runs unit 0) nor mint a drafted row — but its
    # spend IS real and lands.
    assert final.current_unit == 0
    assert final.spent_usd == Decimal("0.01")
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["pending"]  # left to the new driver


async def test_late_result_after_close_lands_failed_and_restores_content():
    """The known race: the run is paused+closed (e.g. before a Revert-All)
    while the seam is mid-flight — the late drafted result must be swallowed
    (unit failed, never a fresh drafted row) AND the engine-persisted chapter
    content rolled back to the pinned pre-run revision (the engine PATCHed the
    draft before the fence could swallow the row)."""
    holder: dict[str, Any] = {}

    async def close_mid_flight(call_no, kw):
        await holder["runs"].transition(
            holder["run_id"], from_statuses=("running",), to_status="paused",
        )
        await holder["svc"].close(holder["run_id"])

    seam = FakeSeam(
        on_call=close_mid_flight,
        default=DraftOutcome(ok=True, cost_usd=Decimal("0.03")),
    )
    cap = FakeRevisionCapture()
    late_restore = RestoreRecorder()
    svc, runs, _ = make_svc(seam=seam, revisions=cap, late_restore=late_restore)
    run = await _running_run(svc, runs)
    holder.update(svc=svc, runs=runs, run_id=run.run_id)
    await svc.run_driver(run.run_id)
    assert len(seam.calls) == 1
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["failed"]  # NOT drafted
    assert units[0].error_message == (
        "run closed mid-flight; draft reverted to pre-run revision"
    )
    # the restore targeted the unit's pinned pre-run baseline
    assert late_restore.calls == [(BOOK, CH1, cap.issued[0])]
    final = await runs.get_by_id(run.run_id)
    assert final.status == "closed"                 # the close stands
    assert final.spent_usd == Decimal("0.03")       # the real spend still lands


async def test_late_result_restore_failure_swallowed_and_reported():
    """A failing late-swallow restore must never raise out of the driver — the
    unit's error message reports the chapter draft was left mutated."""
    holder: dict[str, Any] = {}

    async def close_mid_flight(call_no, kw):
        await holder["runs"].transition(
            holder["run_id"], from_statuses=("running",), to_status="paused",
        )
        await holder["svc"].close(holder["run_id"])

    seam = FakeSeam(on_call=close_mid_flight)
    svc, runs, _ = make_svc(
        seam=seam, late_restore=RestoreRecorder(fail_on_call={1}),
    )
    run = await _running_run(svc, runs)
    holder.update(svc=svc, runs=runs, run_id=run.run_id)
    await svc.run_driver(run.run_id)  # must not raise
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["failed"]
    assert "restore FAILED" in units[0].error_message
    assert "draft left in place" in units[0].error_message


async def test_late_result_while_paused_still_drafts():
    """Pause (without close) mid-seam is NOT a swallow: paused is a resumable
    stop, the drafted row is the resume point."""
    holder: dict[str, Any] = {}

    async def pause_mid_flight(call_no, kw):
        if call_no == 1:
            await holder["runs"].transition(
                holder["run_id"], from_statuses=("running",), to_status="paused",
            )

    seam = FakeSeam(on_call=pause_mid_flight)
    svc, runs, _ = make_svc(seam=seam)
    run = await _running_run(svc, runs)
    holder.update(runs=runs, run_id=run.run_id)
    await svc.run_driver(run.run_id)
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
    assert meta["link"] == f"/books/{BOOK}/agent-mode/runs/{run.run_id}"


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
    assert meta["link"] == f"/books/{BOOK}/agent-mode/runs/{run.run_id}"


async def test_notification_failure_swallowed_run_unaffected():
    notify = NotifyRecorder(raise_on_call=True)
    svc, runs, _ = make_svc(notify=notify)
    run = await _completed_run(svc, runs)   # must not raise
    assert run.status == "report_ready"     # terminal state stands
    assert len(notify.calls) == 1           # the notify WAS attempted


async def test_notification_fired_on_budget_pause():
    """A breaker pause on a headless run needs a human — the interrupt must
    reach them (07S), same best-effort channel as the terminal notify."""
    notify = NotifyRecorder()
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.06")))
    svc, runs, _ = make_svc(seam=seam, notify=notify)
    run = await _running_run(svc, runs, budget="0.05")
    await svc.run_driver(run.run_id)
    assert (await runs.get_by_id(run.run_id)).status == "paused"
    assert len(notify.calls) == 1
    call = notify.calls[0]
    assert "paused (budget)" in call["title"]
    assert call["metadata"]["status"] == "paused"
    assert call["metadata"]["operation"] == "autonomous_authoring"


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
    await svc.gate(run_a.run_id, book_chapter_ids=BOOK_CHAPTERS)
    await svc.start(run_a.run_id)
    assert run_a.run_id in mod._DRIVER_TASKS
    await asyncio.sleep(0)  # let the driver reach the blocking seam

    # Run B starts (transition succeeds) but the spawn is DEFERRED at the cap.
    run_b = await svc.create(
        OWNER, BOOK2, plan_run_id=PLAN2, level=3, scope=[str(CH3)],
        budget_usd=Decimal("1"), tool_allowlist=["composition_write_prose"],
    )
    await svc.gate(run_b.run_id, book_chapter_ids={str(CH3)})
    started_b = await svc.start(run_b.run_id)
    assert started_b.status == "running"
    assert run_b.run_id not in mod._DRIVER_TASKS  # no task — slot busy
    # The deferred start RELEASED its claim (heartbeat NULLed) so the next
    # sweep with capacity can pick B up immediately — no stale-window stall.
    assert (await runs.get_by_id(run_b.run_id)).driver_heartbeat_at is None

    # Sweep respects the cap: B is sweep-visible but there is no capacity.
    assert await svc.sweep_stale_runs() == []

    # A finishes → slot frees → the next sweep resumes B from its cursor.
    gate_evt.set()
    await _drain(run_a.run_id)
    assert (await runs.get_by_id(run_a.run_id)).status == "report_ready"
    claimed = await svc.sweep_stale_runs()
    assert [r.run_id for r in claimed] == [run_b.run_id]
    await _drain(run_b.run_id)
    assert (await runs.get_by_id(run_b.run_id)).status == "report_ready"


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
    await svc._units.upsert_pending(run.run_id, 0, CH1, pre_revision_id=uuid.uuid4())
    await svc._units.mark_drafted(
        run.run_id, 0, post_revision_id=uuid.uuid4(), cost_usd=Decimal("0.01"),
    )
    await runs.record_unit_progress(
        run.run_id, add_spent_usd=Decimal("0.01"), current_unit=1,
    )
    _age_heartbeat(runs, run.run_id, secs=settings.authoring_heartbeat_stale_secs + 60)

    claimed = await svc.sweep_stale_runs()
    assert [r.run_id for r in claimed] == [run.run_id]
    await _drain(run.run_id)

    final = await runs.get_by_id(run.run_id)
    assert final.status == "report_ready"
    assert final.current_unit == 3
    # only the remaining units were drafted on resume — unit 0 untouched
    assert [c["chapter_id"] for c in seam.calls] == [CH2, CH3]
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted", "drafted", "drafted"]


# ── D5: per-unit continuity critic ──────────────────────────────────────────
# Critic runs post-draft (default ON), verdict lands on the unit row, cost
# accumulates into spent_usd, severe pauses with the breaker, warn/ok and
# critic FAILURE continue, disabled/stolen skip.


async def test_critic_invoked_post_draft_verdict_lands_and_cost_accumulates():
    critic = FakeCriticSeam(
        default=CriticVerdict(severity="ok", summary="clean",
                              cost_usd=Decimal("0.005")),
    )
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam, critic=critic)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"
    # invoked once per drafted unit, with the unit's chapter + the run's params
    assert [c["chapter_id"] for c in critic.calls] == [CH1, CH2]
    assert all(c["book_id"] == BOOK and c["plan_run_id"] == PLAN
               for c in critic.calls)
    units = await svc._units.list_for_run(run.run_id)
    assert [u.critic_verdict for u in units] == [
        {"severity": "ok", "summary": "clean", "cost_usd": "0.005"},
    ] * 2
    # spend: 2 drafts (0.01) + 2 critiques (0.005) — critic cost is real spend
    assert run.spent_usd == Decimal("0.03")


async def test_critic_severe_pauses_run_with_breaker_and_stops_downstream():
    critic = FakeCriticSeam(verdicts=[
        CriticVerdict(severity="severe",
                      summary="1 canon violation(s) [r1]; coherence=1",
                      cost_usd=Decimal("0.005")),
    ])
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    notify = NotifyRecorder()
    svc, runs, _ = make_svc(seam=seam, critic=critic, notify=notify)
    run = await _completed_run(svc, runs)
    # interrupt on severe = PAUSE (07S), never fail — resumable after review
    assert run.status == "paused"
    assert run.breaker_state == {
        "reason": "critic_severe", "unit_index": 0, "chapter_id": str(CH1),
        "summary": "1 canon violation(s) [r1]; coherence=1",
    }
    assert len(seam.calls) == 1          # unit 2 never drafted
    assert len(critic.calls) == 1
    assert run.current_unit == 1         # unit 0's progress stands (resume point)
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted"]   # the draft itself stands
    assert units[0].critic_verdict["severity"] == "severe"
    # 07S "interrupt on severe" — the interrupt must actually reach the human
    assert len(notify.calls) == 1
    assert "paused (critic_severe)" in notify.calls[0]["title"]
    assert notify.calls[0]["metadata"]["status"] == "paused"


async def test_critic_warn_and_ok_continue_run():
    critic = FakeCriticSeam(verdicts=[
        CriticVerdict(severity="warn", summary="continuity concerns; pacing=2"),
        CriticVerdict(severity="ok", summary="all dims clear"),
    ])
    svc, runs, _ = make_svc(critic=critic)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"
    units = await svc._units.list_for_run(run.run_id)
    assert [u.critic_verdict["severity"] for u in units] == ["warn", "ok"]


async def test_critic_exception_degrades_to_warn_and_run_continues():
    critic = FakeCriticSeam(raise_on_call={1})
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam, critic=critic)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"      # critic failure is NEVER fatal
    units = await svc._units.list_for_run(run.run_id)
    assert units[0].critic_verdict == {
        "severity": "warn", "summary": "critic unavailable", "cost_usd": "0",
    }
    assert units[1].critic_verdict["severity"] == "ok"  # unit 2 judged normally
    assert run.spent_usd == Decimal("0.02")   # no critic cost billed for a raise


async def test_critic_off_contract_severity_demoted_to_warn():
    critic = FakeCriticSeam(default=CriticVerdict(severity="catastrophic",
                                                  summary="typo'd severity"))
    svc, runs, _ = make_svc(critic=critic)
    run = await _completed_run(svc, runs)
    assert run.status == "report_ready"       # never trips the breaker
    units = await svc._units.list_for_run(run.run_id)
    assert all(u.critic_verdict["severity"] == "warn" for u in units)


async def test_critic_disabled_skips_entirely():
    critic = FakeCriticSeam()
    svc, runs, _ = make_svc(critic=critic)
    run = await _running_run(svc, runs, params={"critic_enabled": False})
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    assert final.status == "report_ready"
    assert critic.calls == []                  # explicit false disables
    units = await svc._units.list_for_run(run.run_id)
    assert all(u.critic_verdict is None for u in units)


async def test_critic_cost_feeds_budget_breaker():
    # draft 0.01 + critique 0.005 = 0.015 >= budget 0.012 → the pre-unit-2
    # budget check pauses: critic spend is real spend.
    critic = FakeCriticSeam(
        default=CriticVerdict(severity="ok", summary="clean",
                              cost_usd=Decimal("0.005")),
    )
    seam = FakeSeam(default=DraftOutcome(ok=True, cost_usd=Decimal("0.01")))
    svc, runs, _ = make_svc(seam=seam, critic=critic)
    run = await _running_run(svc, runs, budget="0.012")
    await svc.run_driver(run.run_id)
    final = await runs.get_by_id(run.run_id)
    assert final.status == "paused"
    assert final.breaker_state["reason"] == "budget"
    assert len(seam.calls) == 1
    assert final.spent_usd == Decimal("0.015")


async def test_critic_skipped_when_run_stolen_mid_unit():
    """A sweep steal while the seam drafts: the driver-fenced late write leaves
    the unit row to the thief (pending) and the old driver stops BEFORE the
    critique — the thief's re-run of the cursor unit drafts + critiques it."""
    holder: dict[str, Any] = {}

    async def steal_during_first_unit(call_no, kw):
        if call_no == 1:
            runs = holder["runs"]
            _age_heartbeat(runs, holder["run_id"], secs=10_000)
            await runs.claim_stale_running(
                driver_id="thief-driver", stale_secs=3600, limit=10,
            )

    critic = FakeCriticSeam()
    seam = FakeSeam(on_call=steal_during_first_unit)
    svc, runs, _ = make_svc(seam=seam, critic=critic)
    run = await _running_run(svc, runs)
    holder.update(runs=runs, run_id=run.run_id)
    await svc.run_driver(run.run_id)
    assert critic.calls == []                  # never critiqued under a lost claim
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["pending"]  # left to the new driver
    assert units[0].critic_verdict is None     # the report shows the gap


async def test_critic_skipped_when_paused_mid_unit():
    holder: dict[str, Any] = {}

    async def pause_mid_flight(call_no, kw):
        if call_no == 1:
            await holder["runs"].transition(
                holder["run_id"], from_statuses=("running",),
                to_status="paused",
            )

    critic = FakeCriticSeam()
    seam = FakeSeam(on_call=pause_mid_flight)
    svc, runs, _ = make_svc(seam=seam, critic=critic)
    run = await _running_run(svc, runs)
    holder.update(runs=runs, run_id=run.run_id)
    await svc.run_driver(run.run_id)
    assert critic.calls == []                  # paused at the boundary — skipped
    units = await svc._units.list_for_run(run.run_id)
    assert [u.status for u in units] == ["drafted"]  # the drafted row stands
    assert units[0].critic_verdict is None


async def test_unit_report_includes_critic_verdict():
    critic = FakeCriticSeam(verdicts=[
        CriticVerdict(severity="warn", summary="pacing dips",
                      detail={"pacing": 2}),
    ])
    svc, runs, _ = make_svc(critic=critic)
    run = await _completed_run(svc, runs)
    rows = await svc.unit_report(run)
    assert rows[0]["critic_verdict"] == {
        "severity": "warn", "summary": "pacing dips", "cost_usd": "0",
        "detail": {"pacing": 2},
    }
    assert rows[1]["critic_verdict"]["severity"] == "ok"


# ── D5: severity mapping (pure — the judge_prose critique → verdict rules) ──


def _critique(**over):
    base = {"coherence": 4, "voice_match": 4, "pacing": 4,
            "canon_consistency": 4, "violations": []}
    base.update(over)
    return base


def test_verdict_all_dims_clear_is_ok():
    severity, summary = verdict_from_critique(_critique())
    assert severity == "ok"
    assert "coherence=4" in summary


def test_verdict_affirmed_violation_is_severe():
    severity, summary = verdict_from_critique(_critique(violations=[
        {"rule_id": "r1", "violated": True, "span": "…", "why": "…"},
    ]))
    assert severity == "severe"
    assert "r1" in summary


def test_verdict_refuted_violation_does_not_escalate():
    severity, _ = verdict_from_critique(_critique(violations=[
        {"rule_id": "r1", "violated": False},
    ]))
    assert severity == "ok"


def test_verdict_critically_low_dim_is_severe():
    severity, summary = verdict_from_critique(_critique(coherence=1))
    assert severity == "severe"
    assert "coherence=1" in summary


def test_verdict_low_dim_is_warn():
    severity, _ = verdict_from_critique(_critique(pacing=2))
    assert severity == "warn"


def test_verdict_error_marker_is_warn_unavailable():
    severity, summary = verdict_from_critique(
        {"coherence": None, "voice_match": None, "pacing": None,
         "canon_consistency": None, "violations": [], "error": "critic_failed"},
    )
    assert severity == "warn"
    assert "critic unavailable" in summary


def test_verdict_no_usable_scores_is_warn():
    severity, summary = verdict_from_critique(
        {"coherence": None, "voice_match": None, "pacing": None,
         "canon_consistency": None, "violations": []},
    )
    assert severity == "warn"
    assert "no usable scores" in summary


def test_verdict_bool_scores_excluded_not_judged():
    # bool is an int subclass — must not read as a 0/1 score (severe)
    severity, _ = verdict_from_critique(_critique(coherence=True))
    assert severity == "ok"  # judged on the remaining 3 real dims


# ── (2) arity regression: the EngineDraftingSeam ↔ GenerationJobsRepo seam ──
# The 25 re-key made GenerationJobsRepo.get BARE-ID (get(job_id), ONE arg). The
# seam had been calling jobs.get(project_id, job_id) → TypeError on EVERY real
# draft, invisible because every driver unit test injects a FakeSeam (the real
# EngineDraftingSeam was never exercised). These drive the REAL seam's job-poll
# path against a fake repo whose `get` takes exactly one arg — a reintroduced
# two-arg call TypeErrors here — plus the run-partition guard, plus a signature-
# parity assertion (mocked-client-hides-server-side-default drift).


class FakeGenerationJobsRepo:
    """Mirrors GenerationJobsRepo.get EXACTLY: bare-id, ONE positional arg (the
    25 re-key). A reintroduced jobs.get(project_id, job_id) TypeErrors here."""

    def __init__(self, jobs: dict | None = None) -> None:
        self._jobs = jobs or {}
        self.get_calls: list[uuid.UUID] = []

    async def get(self, job_id):  # EXACTLY one positional arg — the whole point
        self.get_calls.append(job_id)
        return self._jobs.get(job_id)


def _job(project_id, *, status="completed", cost_usd=Decimal("0.07"), result=None):
    return SimpleNamespace(
        project_id=project_id, status=status, cost_usd=cost_usd, result=result,
    )


async def test_engine_seam_poll_reads_completed_job_cost_bare_id(monkeypatch):
    """Drives the REAL EngineDraftingSeam._poll_job against a 1-arg fake repo:
    a completed job in this run's partition returns its cost. If the seam ever
    reverts to jobs.get(project_id, job_id) this TypeErrors (defect 2)."""
    from app.config import settings

    monkeypatch.setattr(settings, "authoring_job_poll_secs", 0)
    monkeypatch.setattr(settings, "authoring_job_poll_timeout_secs", 5)
    project_id = uuid.uuid4()
    job_id = uuid.uuid4()
    jobs = FakeGenerationJobsRepo({job_id: _job(project_id, cost_usd=Decimal("0.07"))})

    outcome = await EngineDraftingSeam._poll_job(jobs, project_id, job_id)

    assert outcome.ok is True
    assert outcome.cost_usd == Decimal("0.07")
    assert jobs.get_calls == [job_id]  # called bare-id with the job id ONLY


async def test_engine_seam_poll_partition_guard_treats_foreign_job_as_absent(monkeypatch):
    """Run-partition guard: a job whose project_id differs from the run's Work is
    treated as ABSENT (never polled-to-success, never billed against this run)."""
    from app.config import settings

    monkeypatch.setattr(settings, "authoring_job_poll_secs", 0)
    monkeypatch.setattr(settings, "authoring_job_poll_timeout_secs", 5)
    project_id = uuid.uuid4()
    other_project = uuid.uuid4()
    job_id = uuid.uuid4()
    # The job exists but belongs to ANOTHER project (partition) than the run's.
    jobs = FakeGenerationJobsRepo({job_id: _job(other_project)})

    outcome = await EngineDraftingSeam._poll_job(jobs, project_id, job_id)

    assert outcome.ok is False
    assert "vanished" in outcome.error


async def test_engine_seam_poll_failed_job_reports_error(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "authoring_job_poll_secs", 0)
    monkeypatch.setattr(settings, "authoring_job_poll_timeout_secs", 5)
    project_id = uuid.uuid4()
    job_id = uuid.uuid4()
    jobs = FakeGenerationJobsRepo({
        job_id: _job(project_id, status="failed", result={"error": "GENERATE_FAILED"}),
    })

    outcome = await EngineDraftingSeam._poll_job(jobs, project_id, job_id)

    assert outcome.ok is False
    assert "GENERATE_FAILED" in outcome.error


def test_fake_generation_jobs_repo_get_mirrors_real_signature():
    """Signature-parity backstop (mocked-client-hides-server-side-default): the
    fake's `get` must have the SAME parameter list as the real repo's — so a
    two-arg drift on either side is caught, not silently absorbed by the double."""
    real = list(inspect.signature(GenerationJobsRepo.get).parameters)
    fake = list(inspect.signature(FakeGenerationJobsRepo.get).parameters)
    assert real == fake == ["self", "job_id"]
