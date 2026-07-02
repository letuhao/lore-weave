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
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from app.config import settings
from app.db.models import AuthoringRun
from app.db.repositories.authoring_runs import AuthoringRunsRepo
from app.db.repositories.plan_runs import PlanRunsRepo

logger = logging.getLogger(__name__)

# plan_run statuses that count as "approved" for the start-gate: `validated`
# is what review_checkpoint(approved=True) stamps; `compiled` is the packaged
# plan (plan_run_status_chk vocabulary — there is no literal 'approved').
_APPROVED_PLAN_STATUSES = ("validated", "compiled")

# Keep strong references to in-flight driver tasks (create_task alone is
# GC-collectable) + let tests/ops introspect. Keyed by run_id.
_DRIVER_TASKS: dict[UUID, asyncio.Task] = {}


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
    ) -> None:
        self._runs = runs
        self._plan_runs = plan_runs
        self._seam = seam

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
            outcome = await self._seam.draft_chapter(
                owner_user_id=owner_user_id,
                book_id=run.book_id,
                chapter_id=chapter_id,
                plan_run_id=run.plan_run_id,
                params=run.params,
            )
            if not outcome.ok:
                await self._runs.transition(
                    owner_user_id, run_id,
                    from_statuses=("running",), to_status="failed",
                    breaker_state={
                        "reason": "unit_failed",
                        "unit": run.current_unit,
                        "chapter_id": str(chapter_id),
                        "error": outcome.error or "",
                    },
                    error_message=outcome.error,
                )
                return
            cost = outcome.cost_usd if outcome.cost_usd and outcome.cost_usd > 0 else (
                Decimal(str(settings.authoring_unit_estimate_usd))
            )
            await self._runs.record_unit_progress(
                owner_user_id, run_id,
                add_spent_usd=cost, current_unit=run.current_unit + 1,
            )
