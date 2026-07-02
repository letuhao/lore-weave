"""Autonomous authoring-run FSM + start-gate + minimal sequential driver
(RAID Wave D2 v1 backbone, DR-D / 07S §10).

FSM: draft → gated → running → (paused ⇄ running) → report_ready → closed,
with running → failed on a unit failure (v1 fail-stop; D4 upgrades the driver
to the saga-grade durable one). Every transition is a guarded OCC UPDATE in
the repo (``WHERE status = ANY(from) RETURNING``) so races lose cleanly.

Start-gate (all-or-nothing, server-enforced, 07S §10):
  approved plan (plan_run status validated|compiled) · non-empty scope whose
  chapters all belong to the book · budget_usd > 0 · non-empty tool allowlist
  (edge #5 — declared UP FRONT, snapshotted on the run row) · no active-run
  overlap on the book (uq_authoring_runs_active_book → 409, edge #11).

Driver (v1, in-process asyncio task — the plan_forge worker-off spirit):
  iterate scope sequentially; per unit re-check status (pause/fail stops) and
  budget (over → auto-pause, breaker reason='budget'); invoke the drafting
  seam; accumulate spent from the seam's reported cost (else the per-unit
  estimate constant); unit failure → breaker reason='unit_failed' + failed.
  All units done → report_ready (D3 builds the Run Report over it).

D3 end-gate (Run Report + review, DR-D / 07S §10 edge #3 + #12):
  the driver additionally writes a per-unit LEDGER row (authoring_run_units):
  BEFORE the seam it pins the chapter's pre-run revision baseline
  (pre_revision_id — book-service snapshots the new body on every draft PATCH,
  so "latest revision" == the pre-run draft, the restore point); AFTER the seam
  it records the new latest revision (post_revision_id, best-effort) + the
  unit's cost. Review: accept (drafted→accepted) · reject (drafted→rejected,
  restoring pre_revision_id via book-service FIRST — never mark rejected
  without the actual revert) · Revert-All (reject every drafted/accepted unit
  in REVERSE unit order so the sequentially-threaded restores unwind cleanly;
  full success closes the run). Units are sequentially threaded, so rejecting
  an upstream unit only WARNS about its downstream (v1: cascade_warning, no
  auto-reject — edge #3).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

import asyncpg

from app.config import settings
from app.db.models import AuthoringRun, AuthoringRunUnit
from app.db.repositories.authoring_runs import AuthoringRunsRepo, AuthoringRunUnitsRepo
from app.db.repositories.plan_runs import PlanRunsRepo

logger = logging.getLogger(__name__)

# plan_run statuses that count as "approved" for the start-gate: `validated`
# is what review_checkpoint(approved=True) stamps; `compiled` is the packaged
# plan (plan_run_status_chk vocabulary — there is no literal 'approved').
_APPROVED_PLAN_STATUSES = ("validated", "compiled")

# Keep strong references to in-flight driver tasks (create_task alone is
# GC-collectable) + let tests/ops introspect. Keyed by run_id.
_DRIVER_TASKS: dict[UUID, asyncio.Task] = {}

# Run statuses whose per-unit outcomes may be REVIEWED (accept/reject/revert-all)
# — the run is stopped at a unit boundary, so the ledger is stable. Edge #12:
# failed/paused runs expose PARTIAL reports (completed units stay reviewable).
_REVIEWABLE_STATUSES = ("report_ready", "failed", "paused")
# The report itself is also readable after close (post-Revert-All audit trail).
_REPORTABLE_STATUSES = _REVIEWABLE_STATUSES + ("closed",)

# reject/revert-all restore callback: (book_id, chapter_id, revision_id) →
# raises (e.g. BookClientError) on failure — the unit is then LEFT drafted.
RestoreFn = Callable[[UUID, UUID, UUID], Awaitable[Any]]


class ActiveRunOverlapError(Exception):
    """Another run is already active (gated/running/paused) on this book."""


class TransitionConflictError(Exception):
    """The run is not in the required from-status (raced or wrong state)."""


@dataclass
class DraftOutcome:
    """What the drafting seam reports back per chapter unit."""

    ok: bool
    cost_usd: Decimal = Decimal("0")
    error: str | None = None


class DraftingSeam(Protocol):
    """ONE callable seam per chapter unit: draft chapter C of book B for
    owner U under the run's params (model ref etc.). Implementations must
    never raise — report failure via DraftOutcome (the driver fail-stops)."""

    async def draft_chapter(
        self,
        *,
        owner_user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        plan_run_id: UUID,
        params: dict[str, Any],
    ) -> DraftOutcome: ...


class RevisionCapture(Protocol):
    """Resolve the chapter's CURRENT latest book-service revision id (None when
    the chapter has no revisions yet). May raise (e.g. BookClientError) — the
    driver treats a failed PRE capture as a unit failure (never draft a chapter
    whose rollback spine could not be pinned) and a failed POST capture as
    best-effort (the draft landed; the report just loses its diff anchor)."""

    async def latest_revision_id(
        self, *, owner_user_id: UUID, book_id: UUID, chapter_id: UUID,
    ) -> UUID | None: ...


class BookRevisionCapture:
    """The REAL capture: book-service's public revisions LIST route (already
    wrapped by BookClient.list_revisions), newest-first, limit=1 →
    items[0].revision_id. Book-service snapshots the NEW body into
    chapter_revisions on every draft PATCH, so the latest revision IS the
    current draft content — captured before the seam it is the pre-run restore
    point, captured after it is the run's own draft. The driver runs headless
    (no caller request in flight), so we mint a short-lived service bearer for
    the run OWNER (actions.py precedent — book-service still enforces the real
    grant boundary on the JWT `sub`)."""

    async def latest_revision_id(
        self, *, owner_user_id: UUID, book_id: UUID, chapter_id: UUID,
    ) -> UUID | None:
        from app.clients.book_client import get_book_client
        from app.mcp.service_bearer import mint_service_bearer

        bearer = mint_service_bearer(owner_user_id, settings.jwt_secret)
        body = await get_book_client().list_revisions(
            book_id, chapter_id, bearer, limit=1,
        )
        items = body.get("items") or []
        if not items or not items[0].get("revision_id"):
            return None
        return UUID(str(items[0]["revision_id"]))


class EngineDraftingSeam:
    """The REAL seam: run the composition chapter engine in-process by calling
    the engine router coroutine directly — the exact pattern the S-COMPOSE MCP
    confirm effect uses (actions._execute_generate → engine_router.
    generate_chapter with per-request repo deps + a minted service bearer).
    With the background worker enabled the engine 202s a pending generation_job
    → poll it to terminal; worker-off it runs inline and returns completed.
    Cost is read from the generation_job row (cost_usd; 0 when the inline path
    didn't meter — the driver then falls back to the per-unit estimate)."""

    async def draft_chapter(
        self,
        *,
        owner_user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        plan_run_id: UUID,
        params: dict[str, Any],
    ) -> DraftOutcome:
        # Deferred imports (actions.py precedent): the engine router pulls in
        # the whole packer; keep this module light + cycle-free.
        from fastapi import HTTPException

        from app.clients.book_client import get_book_client
        from app.clients.embedding_client import get_embedding_client
        from app.clients.glossary_client import get_glossary_client
        from app.clients.knowledge_client import get_knowledge_client
        from app.clients.llm_client import get_llm_client
        from app.db.pool import get_pool
        from app.db.repositories.canon_rules import CanonRulesRepo
        from app.db.repositories.derivatives import DerivativesRepo
        from app.db.repositories.generation_jobs import GenerationJobsRepo
        from app.db.repositories.grounding_pins import GroundingPinsRepo
        from app.db.repositories.narrative_thread import NarrativeThreadRepo
        from app.db.repositories.outline import OutlineRepo
        from app.db.repositories.references import ReferencesRepo
        from app.db.repositories.scene_links import SceneLinksRepo
        from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo
        from app.db.repositories.works import WorksRepo
        from app.mcp.service_bearer import mint_service_bearer
        from app.routers import engine as engine_router

        model_ref_raw = params.get("model_ref")
        if not model_ref_raw:
            return DraftOutcome(ok=False, error="params.model_ref (user-model UUID) required")
        try:
            model_ref = UUID(str(model_ref_raw))
        except (ValueError, TypeError):
            return DraftOutcome(ok=False, error="params.model_ref is not a UUID")
        model_source = str(params.get("model_source") or "user_model")

        pool = get_pool()
        works = WorksRepo(pool)
        jobs = GenerationJobsRepo(pool)
        # The engine is keyed on the Work's knowledge project_id (works.get
        # filters project_id) — resolve the book's single marked Work.
        marked = await works.resolve_by_book(owner_user_id, book_id)
        if len(marked) != 1 or marked[0].project_id is None:
            return DraftOutcome(
                ok=False,
                error="no unambiguous knowledge-backed composition Work for this book",
            )
        project_id = marked[0].project_id

        # Generation can run for minutes and the chapter path REUSES the bearer
        # to persist the draft afterwards — mint a generous TTL (actions.py).
        bearer = mint_service_bearer(
            owner_user_id, settings.jwt_secret,
            ttl=settings.authoring_draft_bearer_ttl_secs,
        )
        try:
            body = engine_router.GenerateChapterBody(
                model_source=model_source,  # type: ignore[arg-type]
                model_ref=model_ref,
                operation=str(params.get("operation") or "draft_chapter"),
                guide=str(params.get("guide") or ""),
                persist=True,
            )
        except (ValueError, TypeError) as exc:  # pydantic ValidationError ⊂ ValueError
            return DraftOutcome(ok=False, error=f"invalid seam params: {exc}")

        deps: dict[str, Any] = dict(
            works=works,
            outline=OutlineRepo(pool),
            scene_links=SceneLinksRepo(pool),
            canon=CanonRulesRepo(pool),
            jobs=jobs,
            book=get_book_client(),
            glossary=get_glossary_client(),
            knowledge=get_knowledge_client(),
            llm=get_llm_client(),
            narrative_threads=NarrativeThreadRepo(pool),
            grounding_pins=GroundingPinsRepo(pool),
            style_profiles=StyleProfileRepo(pool),
            voice_profiles=VoiceProfileRepo(pool),
            references=ReferencesRepo(pool),
            embedder=get_embedding_client(),
            derivatives=DerivativesRepo(pool),
        )
        try:
            resp = await engine_router.generate_chapter(
                project_id, chapter_id, body,
                user_id=owner_user_id, bearer=bearer, **deps,
            )
        except HTTPException as exc:
            return DraftOutcome(ok=False, error=f"engine {exc.status_code}: {exc.detail}")
        except Exception as exc:  # noqa: BLE001 — seam must never raise into the driver
            logger.warning("authoring drafting seam failed", exc_info=True)
            return DraftOutcome(ok=False, error=f"engine error: {exc}")

        try:
            payload = json.loads(resp.body)
        except (ValueError, AttributeError, TypeError):
            payload = {}
        job_id_raw = payload.get("job_id")
        status = str(payload.get("status") or "")

        if status == "pending" and job_id_raw:
            # Worker path (202) — poll the generation_job to terminal.
            return await self._poll_job(jobs, owner_user_id, UUID(str(job_id_raw)))
        if status == "completed":
            cost = Decimal("0")
            if job_id_raw:
                job = await jobs.get(owner_user_id, UUID(str(job_id_raw)))
                if job is not None:
                    cost = job.cost_usd or Decimal("0")
            return DraftOutcome(ok=True, cost_usd=cost)
        return DraftOutcome(ok=False, error=f"engine returned status={status or 'unknown'}")

    @staticmethod
    async def _poll_job(jobs: Any, owner_user_id: UUID, job_id: UUID) -> DraftOutcome:
        interval = settings.authoring_job_poll_secs
        deadline = settings.authoring_job_poll_timeout_secs
        waited = 0.0
        while waited < deadline:
            await asyncio.sleep(interval)
            waited += interval
            job = await jobs.get(owner_user_id, job_id)
            if job is None:
                return DraftOutcome(ok=False, error=f"generation job {job_id} vanished")
            if job.status == "completed":
                return DraftOutcome(ok=True, cost_usd=job.cost_usd or Decimal("0"))
            if job.status in ("failed", "cancelled"):
                err = (job.result or {}).get("error", job.status)
                return DraftOutcome(ok=False, error=f"generation job {job.status}: {err}")
        return DraftOutcome(ok=False, error=f"generation job {job_id} timed out")


class AuthoringRunService:
    def __init__(
        self,
        runs: AuthoringRunsRepo,
        plan_runs: PlanRunsRepo,
        seam: DraftingSeam,
        units: AuthoringRunUnitsRepo,
        revisions: RevisionCapture,
    ) -> None:
        self._runs = runs
        self._plan_runs = plan_runs
        self._seam = seam
        self._units = units
        self._revisions = revisions

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def create(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        *,
        plan_run_id: UUID,
        level: int,
        scope: list[str],
        budget_usd: Decimal,
        tool_allowlist: list[str],
        params: dict[str, Any] | None = None,
    ) -> AuthoringRun:
        """Create the run in `draft`. Deliberately permissive — ALL semantic
        validation happens at gate() (the start-gate is the enforcement point);
        only the referenced plan_run must exist+be owned (FK + tenancy)."""
        plan = await self._plan_runs.get_for_owner(owner_user_id, book_id, plan_run_id)
        if plan is None:
            raise LookupError("plan run not found")
        return await self._runs.create(
            owner_user_id, book_id,
            plan_run_id=plan_run_id, level=level, scope=scope,
            budget_usd=budget_usd, tool_allowlist=tool_allowlist,
            params=params or {},
        )

    async def gate(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        *,
        book_chapter_ids: set[str],
    ) -> AuthoringRun:
        """Start-gate: draft → gated, all-or-nothing (07S §10). The router
        resolves `book_chapter_ids` (the book's active chapter-id set, via
        BookClient.list_chapters with the caller's bearer) so this stays
        unit-testable without HTTP."""
        run = await self._runs.get_for_owner(owner_user_id, run_id)
        if run is None:
            raise LookupError("run not found")
        if run.status != "draft":
            raise TransitionConflictError(f"gate requires status=draft, run is {run.status}")

        plan = await self._plan_runs.get_for_owner(
            owner_user_id, run.book_id, run.plan_run_id,
        )
        if plan is None:
            raise ValueError("plan run not found")
        if plan.status not in _APPROVED_PLAN_STATUSES:
            raise ValueError(
                f"plan run must be approved ({'/'.join(_APPROVED_PLAN_STATUSES)}), "
                f"is {plan.status}"
            )
        if not run.scope:
            raise ValueError("scope is empty — declare the ordered chapter list")
        for cid in run.scope:
            try:
                UUID(str(cid))
            except (ValueError, TypeError):
                raise ValueError(f"scope entry {cid!r} is not a chapter UUID")
        foreign = [c for c in run.scope if str(c) not in book_chapter_ids]
        if foreign:
            raise ValueError(f"scope chapters not in this book: {foreign}")
        if run.budget_usd <= 0:
            raise ValueError("budget_usd must be > 0")
        allow = run.tool_allowlist
        if (
            not allow
            or not isinstance(allow, list)
            or not all(isinstance(t, str) and t.strip() for t in allow)
        ):
            raise ValueError(
                "tool_allowlist must be a non-empty list of tool names (edge #5 — "
                "an autonomous run declares its side-effecting tools up front)"
            )

        try:
            gated = await self._runs.transition(
                owner_user_id, run_id,
                from_statuses=("draft",), to_status="gated",
            )
        except asyncpg.UniqueViolationError as exc:  # scope fence (edge #11)
            raise ActiveRunOverlapError(
                "another authoring run is already active on this book"
            ) from exc
        if gated is None:
            raise TransitionConflictError("run left draft while gating (raced)")
        return gated

    async def start(self, owner_user_id: UUID, run_id: UUID) -> AuthoringRun:
        run = await self._require(owner_user_id, run_id)
        started = await self._runs.transition(
            owner_user_id, run_id, from_statuses=("gated",), to_status="running",
        )
        if started is None:
            raise TransitionConflictError(f"start requires status=gated, run is {run.status}")
        self._spawn_driver(owner_user_id, run_id)
        return started

    async def pause(self, owner_user_id: UUID, run_id: UUID) -> AuthoringRun:
        run = await self._require(owner_user_id, run_id)
        paused = await self._runs.transition(
            owner_user_id, run_id, from_statuses=("running",), to_status="paused",
        )
        if paused is None:
            raise TransitionConflictError(f"pause requires status=running, run is {run.status}")
        return paused

    async def resume(self, owner_user_id: UUID, run_id: UUID) -> AuthoringRun:
        run = await self._require(owner_user_id, run_id)
        resumed = await self._runs.transition(
            owner_user_id, run_id, from_statuses=("paused",), to_status="running",
        )
        if resumed is None:
            raise TransitionConflictError(f"resume requires status=paused, run is {run.status}")
        self._spawn_driver(owner_user_id, run_id)
        return resumed

    async def close(self, owner_user_id: UUID, run_id: UUID) -> AuthoringRun:
        """Terminal close. Allowed from every non-running state (a running run
        must be paused first — the driver owns it). Closing a gated/paused run
        releases the book's scope fence (the partial index only covers
        gated/running/paused)."""
        run = await self._require(owner_user_id, run_id)
        closed = await self._runs.transition(
            owner_user_id, run_id,
            from_statuses=("draft", "gated", "paused", "failed", "report_ready"),
            to_status="closed",
        )
        if closed is None:
            raise TransitionConflictError(f"close not allowed from status {run.status}")
        return closed

    async def get(self, owner_user_id: UUID, run_id: UUID) -> AuthoringRun | None:
        return await self._runs.get_for_owner(owner_user_id, run_id)

    async def list(
        self, owner_user_id: UUID, book_id: UUID, *, limit: int = 20,
    ) -> list[AuthoringRun]:
        return await self._runs.list_for_owner(owner_user_id, book_id, limit=limit)

    async def _require(self, owner_user_id: UUID, run_id: UUID) -> AuthoringRun:
        run = await self._runs.get_for_owner(owner_user_id, run_id)
        if run is None:
            raise LookupError("run not found")
        return run

    # ── D3 Run Report + dependency-ordered review ──────────────────────────

    async def get_any(self, run_id: UUID) -> AuthoringRun | None:
        """UNSCOPED — Run Report route only; the router grant-gates VIEW on
        run.book_id before using it (OwnershipError → 404, no oracle)."""
        return await self._runs.get_by_id(run_id)

    async def unit_report(self, run: AuthoringRun) -> list[dict[str, Any]]:
        """Per-unit report rows over the FULL scope (un-attempted units are
        synthesized as 'pending' — edge #12: a failed/paused run's partial
        ledger is still reviewable). Each row lists downstream_unit_indexes:
        the LATER units currently drafted/accepted — the sequential thread's
        dependency note (edge #3: rejecting this unit invalidates those).
        Caller must have auth-gated the run; report readable from
        report_ready/failed/paused (+closed, post-Revert-All audit)."""
        if run.status not in _REPORTABLE_STATUSES:
            raise TransitionConflictError(
                f"report requires status in {_REPORTABLE_STATUSES}, run is {run.status}"
            )
        by_index = {u.unit_index: u for u in await self._units.list_for_run(run.run_id)}
        statuses = {
            i: (by_index[i].status if i in by_index else "pending")
            for i in range(len(run.scope))
        }
        rows: list[dict[str, Any]] = []
        for i, chapter_id in enumerate(run.scope):
            u = by_index.get(i)
            rows.append({
                "unit_index": i,
                "chapter_id": str(u.chapter_id) if u else str(chapter_id),
                "status": statuses[i],
                "pre_revision_id": str(u.pre_revision_id) if u and u.pre_revision_id else None,
                "post_revision_id": str(u.post_revision_id) if u and u.post_revision_id else None,
                "cost_usd": str(u.cost_usd) if u else "0",
                "error_message": u.error_message if u else None,
                "downstream_unit_indexes": [
                    j for j in range(i + 1, len(run.scope))
                    if statuses[j] in ("drafted", "accepted")
                ],
            })
        return rows

    async def accept_unit(
        self, owner_user_id: UUID, run_id: UUID, unit_index: int,
    ) -> AuthoringRunUnit:
        """Owner-only guarded drafted→accepted."""
        run = await self._require(owner_user_id, run_id)
        if run.status not in _REVIEWABLE_STATUSES:
            raise TransitionConflictError(
                f"review requires run status in {_REVIEWABLE_STATUSES}, run is {run.status}"
            )
        unit = await self._units.transition_unit(
            owner_user_id, run_id, unit_index,
            from_statuses=("drafted",), to_status="accepted",
        )
        if unit is None:
            existing = await self._units.get_for_owner(owner_user_id, run_id, unit_index)
            if existing is None:
                raise LookupError("unit not found")
            raise TransitionConflictError(
                f"accept requires unit status=drafted, unit is {existing.status}"
            )
        return unit

    async def reject_unit(
        self, owner_user_id: UUID, run_id: UUID, unit_index: int, *, restore: RestoreFn,
    ) -> tuple[AuthoringRunUnit, list[int], bool]:
        """Owner-only guarded drafted→rejected. When the unit pinned a
        pre_revision_id, the chapter is FIRST rolled back via `restore` (the
        router binds BookClient.restore_revision with the CALLER's bearer); a
        restore failure propagates (→502) with the unit LEFT drafted — never
        mark rejected without the actual revert. pre_revision_id=None (chapter
        had no revisions before the run) → reject without a restore, flagged by
        reverted=False. Returns (unit, downstream drafted/accepted indexes for
        the cascade_warning — edge #3, v1 warns only, no auto-reject)."""
        run = await self._require(owner_user_id, run_id)
        if run.status not in _REVIEWABLE_STATUSES:
            raise TransitionConflictError(
                f"review requires run status in {_REVIEWABLE_STATUSES}, run is {run.status}"
            )
        unit = await self._units.get_for_owner(owner_user_id, run_id, unit_index)
        if unit is None:
            raise LookupError("unit not found")
        if unit.status != "drafted":
            raise TransitionConflictError(
                f"reject requires unit status=drafted, unit is {unit.status}"
            )
        reverted = False
        if unit.pre_revision_id is not None:
            await restore(run.book_id, unit.chapter_id, unit.pre_revision_id)
            reverted = True
        rejected = await self._units.transition_unit(
            owner_user_id, run_id, unit_index,
            from_statuses=("drafted",), to_status="rejected",
        )
        if rejected is None:
            raise TransitionConflictError("unit left drafted while rejecting (raced)")
        cascade = [
            u.unit_index
            for u in await self._units.list_for_owner(owner_user_id, run_id)
            if u.unit_index > unit_index and u.status in ("drafted", "accepted")
        ]
        return rejected, cascade, reverted

    async def revert_all(
        self, owner_user_id: UUID, run_id: UUID, *, restore: RestoreFn,
    ) -> dict[str, Any]:
        """Owner-only: reject EVERY drafted/accepted unit in REVERSE unit order
        (downstream first — the sequentially-threaded restores unwind cleanly).
        First restore failure STOPS the sweep; the result reports which units
        reverted and which failed (run left as-is). Full success → run closed
        (for a paused run that also releases the book's scope fence — the
        partial index covers gated/running/paused)."""
        run = await self._require(owner_user_id, run_id)
        if run.status not in _REVIEWABLE_STATUSES:
            raise TransitionConflictError(
                f"revert-all requires run status in {_REVIEWABLE_STATUSES}, "
                f"run is {run.status}"
            )
        targets = sorted(
            (
                u for u in await self._units.list_for_owner(owner_user_id, run_id)
                if u.status in ("drafted", "accepted")
            ),
            key=lambda u: u.unit_index,
            reverse=True,
        )
        reverted: list[int] = []
        for u in targets:
            if u.pre_revision_id is not None:
                try:
                    await restore(run.book_id, u.chapter_id, u.pre_revision_id)
                except Exception as exc:  # noqa: BLE001 — collect + stop, report partial
                    logger.warning(
                        "revert-all restore failed for run %s unit %d: %s",
                        run_id, u.unit_index, exc,
                    )
                    return {
                        "reverted_unit_indexes": reverted,
                        "failed_unit_index": u.unit_index,
                        "error": str(exc),
                        "run_status": run.status,
                        "closed": False,
                    }
            updated = await self._units.transition_unit(
                owner_user_id, run_id, u.unit_index,
                from_statuses=("drafted", "accepted"), to_status="rejected",
            )
            if updated is not None:
                reverted.append(u.unit_index)
            # None = raced away (already rejected) — the restore was applied or
            # already done; treat as unwound and continue.
        closed = await self._runs.transition(
            owner_user_id, run_id,
            from_statuses=_REVIEWABLE_STATUSES, to_status="closed",
        )
        return {
            "reverted_unit_indexes": reverted,
            "failed_unit_index": None,
            "error": None,
            "run_status": closed.status if closed else run.status,
            "closed": closed is not None,
        }

    # ── driver (v1 minimal sequential — D4 upgrades to the durable saga) ───

    def _spawn_driver(self, owner_user_id: UUID, run_id: UUID) -> None:
        if run_id in _DRIVER_TASKS and not _DRIVER_TASKS[run_id].done():
            return  # already driving (resume raced a live task)
        task = asyncio.create_task(self._drive_safe(owner_user_id, run_id))
        _DRIVER_TASKS[run_id] = task
        task.add_done_callback(lambda _t: _DRIVER_TASKS.pop(run_id, None))

    async def _drive_safe(self, owner_user_id: UUID, run_id: UUID) -> None:
        try:
            await self.run_driver(owner_user_id, run_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a driver crash must land as failed, not vanish
            logger.exception("authoring driver crashed for run %s", run_id)
            await self._runs.transition(
                owner_user_id, run_id,
                from_statuses=("running",), to_status="failed",
                breaker_state={"reason": "driver_crashed"},
                error_message="driver crashed — see service logs",
            )

    async def run_driver(self, owner_user_id: UUID, run_id: UUID) -> None:
        """Sequential per-unit loop. Re-reads the row each unit so an external
        pause/fail/close is honored at the next unit boundary."""
        while True:
            run = await self._runs.get_for_owner(owner_user_id, run_id)
            if run is None or run.status != "running":
                return  # paused/failed/closed externally — stop silently
            scope = run.scope
            if run.current_unit >= len(scope):
                await self._runs.transition(
                    owner_user_id, run_id,
                    from_statuses=("running",), to_status="report_ready",
                )
                return
            if run.spent_usd >= run.budget_usd:
                await self._runs.transition(
                    owner_user_id, run_id,
                    from_statuses=("running",), to_status="paused",
                    breaker_state={
                        "reason": "budget",
                        "spent_usd": str(run.spent_usd),
                        "budget_usd": str(run.budget_usd),
                        "unit": run.current_unit,
                    },
                )
                return
            chapter_id = UUID(str(scope[run.current_unit]))
            # D3 ledger — pin the pre-run revision baseline BEFORE the seam.
            # A failed PRE capture fails the unit: an autonomous run must never
            # draft a chapter whose rollback spine could not be pinned.
            try:
                pre_rev = await self._revisions.latest_revision_id(
                    owner_user_id=owner_user_id,
                    book_id=run.book_id,
                    chapter_id=chapter_id,
                )
            except Exception as exc:  # noqa: BLE001 — capture seam, fail the unit
                error = f"pre-revision capture failed: {exc}"
                await self._units.upsert_pending(
                    owner_user_id, run_id, run.current_unit, chapter_id,
                    pre_revision_id=None,
                )
                await self._fail_unit(owner_user_id, run_id, run.current_unit,
                                      chapter_id, error)
                return
            await self._units.upsert_pending(
                owner_user_id, run_id, run.current_unit, chapter_id,
                pre_revision_id=pre_rev,
            )
            outcome = await self._seam.draft_chapter(
                owner_user_id=owner_user_id,
                book_id=run.book_id,
                chapter_id=chapter_id,
                plan_run_id=run.plan_run_id,
                params=run.params,
            )
            if not outcome.ok:
                await self._fail_unit(owner_user_id, run_id, run.current_unit,
                                      chapter_id, outcome.error or "")
                return
            cost = outcome.cost_usd if outcome.cost_usd and outcome.cost_usd > 0 else (
                Decimal(str(settings.authoring_unit_estimate_usd))
            )
            # POST capture is best-effort: the draft DID land (and its cost is
            # real) — a capture blip only loses the report's diff anchor.
            post_rev: UUID | None = None
            try:
                post_rev = await self._revisions.latest_revision_id(
                    owner_user_id=owner_user_id,
                    book_id=run.book_id,
                    chapter_id=chapter_id,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "post-revision capture failed for run %s unit %d",
                    run_id, run.current_unit, exc_info=True,
                )
            await self._units.mark_drafted(
                owner_user_id, run_id, run.current_unit,
                post_revision_id=post_rev, cost_usd=cost,
            )
            await self._runs.record_unit_progress(
                owner_user_id, run_id,
                add_spent_usd=cost, current_unit=run.current_unit + 1,
            )

    async def _fail_unit(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        unit_index: int,
        chapter_id: UUID,
        error: str,
    ) -> None:
        """Fail-stop: mark the ledger row failed + trip the run breaker."""
        await self._units.mark_failed(owner_user_id, run_id, unit_index, error=error)
        await self._runs.transition(
            owner_user_id, run_id,
            from_statuses=("running",), to_status="failed",
            breaker_state={
                "reason": "unit_failed",
                "unit": unit_index,
                "chapter_id": str(chapter_id),
                "error": error,
            },
            error_message=error,
        )
