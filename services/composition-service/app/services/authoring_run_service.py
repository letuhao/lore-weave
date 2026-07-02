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
  v1 honesty: the allowlist is declared+snapshotted but not yet CONSULTED —
  the v1 drafting seam invokes no agent tools, so there is nothing to gate.
  When agentic tools ride the run, the driver MUST check each side-effecting
  call against the snapshot and trip the breaker on a miss (edge #5's second
  half; tracked D-RAID-ALLOWLIST-ENFORCE).

Driver (v1, in-process asyncio task — the plan_forge worker-off spirit):
  iterate scope sequentially; per unit re-check status (pause/fail stops) and
  budget (over → auto-pause, breaker reason='budget'); invoke the drafting
  seam; accumulate spent from the seam's reported cost (else the per-unit
  estimate constant); unit failure → breaker reason='unit_failed' + failed.
  All units done → report_ready (D3 builds the Run Report over it).

D4 durable background execution (campaign-service saga-driver pattern):
  * Restart durability — the run row carries driver_id + driver_heartbeat_at
    (bumped once per unit). A service restart kills the in-process task and
    leaves the run 'running' with a stale heartbeat; the startup + periodic
    SWEEP (`sweep_stale_runs`, campaign claim_active_campaigns spirit) does a
    guarded claim (UPDATE … WHERE status='running' AND heartbeat stale
    RETURNING, setting driver_id + heartbeat) and resumes from current_unit —
    the ledger's upsert_pending resets the cursor unit's row on re-run.
  * Per-unit guarded claim — each loop iteration re-claims via ONE guarded
    UPDATE (status='running' AND driver_id=mine; the heartbeat bump doubles as
    the claim), so an external pause/close or a sweep steal stops the driver
    BEFORE the next seam call.
  * Late-result fence — the post-seam drafted write is guarded on the run
    still being running-or-paused AND still driven by THIS driver. A run
    closed/failed mid-flight swallows the late result: the unit lands failed
    ('run closed mid-flight') and the engine-persisted draft is best-effort
    RESTORED to the pinned pre_revision_id (the engine PATCHed content before
    the fence could swallow the row — a Revert-All must not leave it behind).
    A run sweep-STOLEN mid-flight leaves the unit row entirely to the new
    driver (spend still recorded; the cursor write is driver-fenced so the
    superseded driver can never rewind it).
  * Stop notification — on terminal transition (report_ready | failed) AND on
    breaker pauses (budget | critic_severe) a best-effort notification goes
    out via notification-service HTTP ingest (operation=
    "autonomous_authoring"); notify failure NEVER affects the run. 07S's
    "interrupt on severe" only interrupts if it reaches the human.
  * DRIVER_MAX_INFLIGHT — at most authoring_driver_max_inflight concurrent
    driver tasks per process; start/resume beyond the cap leaves the run
    running-unclaimed for the sweep to pick up once a slot frees.
  * fg/bg toggle — `background` is accepted at create and surfaced in GET/list
    (v1: a pure FE display/filter flag; sweep durability applies to BOTH).

D5 per-unit continuity critic (DR-D / 07S §10 — "interrupt on severe; else
Run Report"):
  after a unit lands drafted, and when the run's params.critic_enabled is on
  (DEFAULT TRUE — an autonomous run needs the net; an explicit falsy value
  disables), the driver invokes the CriticSeam under the same guarded-claim
  discipline as the drafting seam (heartbeat bump first — a paused/closed/
  stolen run skips the critique and stops at the boundary). The verdict
  ({severity: ok|warn|severe, summary, cost_usd[, detail]}) lands on the unit
  row (critic_verdict jsonb, surfaced by the D3 Run Report); the critique's
  cost adds to spent_usd via record_unit_progress (so it feeds the budget
  breaker). severity='severe' trips the breaker: the run PAUSES (breaker
  reason critic_severe — NOT failed; the human reviews the report and
  resumes/reverts, 07S "interrupt on severe"). A critic FAILURE is never
  fatal: any seam exception degrades to a {severity:'warn', summary:'critic
  unavailable…'} verdict and the run continues — the report shows the gap.

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
from typing import Any, Awaitable, Callable, Literal, Protocol
from uuid import UUID, uuid4

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
# GC-collectable) + let tests/ops introspect. Keyed by run_id. Module-level on
# purpose: services are constructed per-request (deps.py) but the driver-task
# registry and the process identity below must span them.
_DRIVER_TASKS: dict[UUID, asyncio.Task] = {}

# D4: this PROCESS's driver identity (campaign SagaDriver's uuid4().hex —
# unique per process). The per-unit heartbeat claim checks driver_id = mine, so
# after a restart the new process cannot be confused with the dead one's claim;
# a stale-heartbeat run is then re-claimable by the sweep.
_PROCESS_DRIVER_ID: str = uuid4().hex

# D4 late-result fence: the post-seam drafted write is valid only while the run
# is still stopped-at-worst-paused; a closed/failed run swallows the result.
_LATE_RESULT_RUN_STATUSES = ("running", "paused")


class Notifier(Protocol):
    """Best-effort completion notifier (notification-service HTTP ingest).
    Implementations SHOULD swallow their own failures; the service wraps every
    call defensively regardless — notify must never affect a run."""

    async def notify(
        self,
        user_id: UUID,
        *,
        title: str,
        metadata: dict[str, Any] | None = None,
        category: str = "system",
    ) -> Any: ...

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


# ── D5 continuity critic ─────────────────────────────────────────────────────

CriticSeverity = Literal["ok", "warn", "severe"]
_CRITIC_SEVERITIES = ("ok", "warn", "severe")
# The 4 judge_prose dimensions (engine/critic.py _DIMENSIONS — re-declared here
# so the severity mapper stays importable without pulling the engine module in).
_CRITIC_DIMS = ("coherence", "voice_match", "pacing", "canon_consistency")


@dataclass
class CriticVerdict:
    """What the critic seam reports back per drafted unit."""

    severity: str  # 'ok' | 'warn' | 'severe' (CriticSeverity)
    summary: str
    cost_usd: Decimal = Decimal("0")
    detail: dict[str, Any] | None = None  # the raw critique (report drill-down)

    def as_row(self) -> dict[str, Any]:
        """The jsonb shape stored on authoring_run_units.critic_verdict."""
        row: dict[str, Any] = {
            # defensive: an off-contract severity from an implementation is
            # demoted to 'warn' (never let a typo'd severity trip the breaker
            # or read as a clean 'ok').
            "severity": self.severity if self.severity in _CRITIC_SEVERITIES else "warn",
            "summary": self.summary,
            "cost_usd": str(self.cost_usd),
        }
        if self.detail is not None:
            row["detail"] = self.detail
        return row


class CriticSeam(Protocol):
    """ONE callable per drafted chapter unit (mirrors DraftingSeam): judge the
    continuity/craft of chapter C of book B for owner U under the run's params.
    Implementations must never raise — report failure via a 'warn' verdict
    ('critic unavailable'); the driver additionally guards (a critic failure is
    NEVER fatal to the run — 07S: the report just shows the gap)."""

    async def critique(
        self,
        *,
        owner_user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        plan_run_id: UUID,
        params: dict[str, Any],
    ) -> CriticVerdict: ...


def verdict_from_critique(critique: dict[str, Any]) -> tuple[str, str]:
    """Map a judge_prose critique (4 dims 0-5 + violations[], engine/critic.py
    contract) to (severity, summary). Pure — unit-tested directly.

    severe  — any AFFIRMED canon violation, or any judged dim <=
              authoring_critic_severe_score (a 0/1 on coherence or canon is a
              continuity break, not a style nit);
    warn    — degraded critique (`error` marker), no usable scores, or any
              judged dim <= authoring_critic_warn_score;
    ok      — everything judged above the warn threshold."""
    err = critique.get("error")
    if err:
        return "warn", f"critic unavailable ({err})"
    judged = {
        d: critique.get(d)
        for d in _CRITIC_DIMS
        if isinstance(critique.get(d), int) and not isinstance(critique.get(d), bool)
    }
    score_part = " ".join(f"{d}={s}" for d, s in judged.items())
    violations = [
        v for v in (critique.get("violations") or [])
        if isinstance(v, dict) and v.get("violated", True)
    ]
    if violations:
        rules = ", ".join(str(v.get("rule_id")) for v in violations[:5])
        return "severe", (
            f"{len(violations)} canon violation(s) [{rules}]"
            + (f"; {score_part}" if score_part else "")
        )
    if not judged:
        return "warn", "critic returned no usable scores"
    low = min(judged.values())
    if low <= settings.authoring_critic_severe_score:
        return "severe", f"continuity score critically low; {score_part}"
    if low <= settings.authoring_critic_warn_score:
        return "warn", f"continuity concerns; {score_part}"
    return "ok", score_part


class EngineCriticSeam:
    """The REAL critic seam: the M6/Q1 quality machinery's chapter-level 4-dim
    judge (engine/critic.judge_prose — coherence / voice_match / pacing /
    canon_consistency + per-rule canon violations; the same judge the Quality
    Report endpoint runs, routers/plan.py quality_report_endpoint) invoked
    IN-PROCESS the way EngineDraftingSeam invokes the chapter engine: deferred
    imports, a minted service bearer for the run OWNER (book-service still
    enforces the real grant boundary on the JWT `sub`), the chapter's CURRENT
    draft fetched via BookClient.get_draft → tiptap_doc_to_text.

    Model: params.critic_model_ref when set — anti-self-reinforcement (§4,
    engine/critic.py header: the critic model SHOULD differ from the drafter) —
    else the run's params.model_ref (same-model critique is weaker but better
    than no net; the caller opts into a distinct judge via critic_model_ref).

    Honest v1 gaps (stubbed, by design not omission):
    * canon grounding — the Quality Report endpoint renders a canon block from
      the kal cast roster + genre convention (bearer-side helpers private to
      that router); this headless seam passes empty active_rules/present_facts,
      so `canon_consistency` judges from the passage alone. Wiring the roster
      canon is a follow-up (needs those helpers extracted).
    * cost — the LLM SDK Job carries no cost field (the exact reason the
      drafting seam falls back to authoring_unit_estimate_usd), so a COMPLETED
      critique reports authoring_critic_estimate_usd and a degraded one 0.

    Never raises — every failure degrades to a 'warn' verdict (07S: critic
    failure is never fatal; the Run Report shows the gap)."""

    async def critique(
        self,
        *,
        owner_user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        plan_run_id: UUID,
        params: dict[str, Any],
    ) -> CriticVerdict:
        try:
            return await self._critique(
                owner_user_id=owner_user_id, book_id=book_id,
                chapter_id=chapter_id, params=params,
            )
        except Exception as exc:  # noqa: BLE001 — seam contract: never raise
            logger.warning(
                "authoring critic seam failed for chapter %s", chapter_id,
                exc_info=True,
            )
            return CriticVerdict(severity="warn", summary=f"critic unavailable ({exc})")

    async def _critique(
        self,
        *,
        owner_user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        params: dict[str, Any],
    ) -> CriticVerdict:
        # Deferred imports (EngineDraftingSeam precedent) — keep module light.
        from app.clients.book_client import get_book_client
        from app.clients.llm_client import get_llm_client
        from app.db.pool import get_pool
        from app.db.repositories.works import WorksRepo
        from app.engine.critic import judge_prose
        from app.engine.prose_doc import tiptap_doc_to_text
        from app.mcp.service_bearer import mint_service_bearer
        from app.packer.profile import BookProfile, from_settings

        model_ref = params.get("critic_model_ref") or params.get("model_ref")
        if not model_ref:
            return CriticVerdict(
                severity="warn",
                summary="critic unavailable (params.model_ref required)",
            )
        model_source = str(
            params.get("critic_model_source") or params.get("model_source")
            or "user_model"
        )

        bearer = mint_service_bearer(owner_user_id, settings.jwt_secret)
        draft = await get_book_client().get_draft(book_id, chapter_id, bearer)
        text = tiptap_doc_to_text(
            draft.get("body") or draft.get("doc") or draft.get("content")
        )
        if not text.strip():
            return CriticVerdict(
                severity="warn",
                summary="critic skipped (chapter draft has no prose)",
            )

        # Best-effort source_language (de-bias §2.6: judge in the book's
        # language) from the book's marked Work — 'auto' when unresolvable.
        profile = BookProfile()
        try:
            marked = await WorksRepo(get_pool()).resolve_by_book(owner_user_id, book_id)
            if len(marked) == 1:
                profile = from_settings(marked[0].settings)
        except Exception:  # noqa: BLE001 — language resolve is best-effort
            logger.debug("critic source-language resolve failed (using auto)",
                         exc_info=True)

        critique = await judge_prose(
            get_llm_client(), user_id=str(owner_user_id),
            model_source=model_source, model_ref=str(model_ref),
            passage=text, active_rules=[], present_facts=[], profile=profile,
        )
        severity, summary = verdict_from_critique(critique)
        # judge_prose degrades internally (error marker) — spend unknown there,
        # bill 0; a completed critique bills the estimate (no SDK cost field).
        cost = (
            Decimal("0") if critique.get("error")
            else Decimal(str(settings.authoring_critic_estimate_usd))
        )
        return CriticVerdict(
            severity=severity, summary=summary, cost_usd=cost, detail=critique,
        )


class AuthoringRunService:
    def __init__(
        self,
        runs: AuthoringRunsRepo,
        plan_runs: PlanRunsRepo,
        seam: DraftingSeam,
        units: AuthoringRunUnitsRepo,
        revisions: RevisionCapture,
        *,
        notify: Notifier | None = None,
        driver_id: str | None = None,
        critic: CriticSeam | None = None,
        late_restore: RestoreFn | None = None,
    ) -> None:
        self._runs = runs
        self._plan_runs = plan_runs
        self._seam = seam
        self._units = units
        self._revisions = revisions
        # D4 late-swallow content restore (None → the real book-service restore
        # with a minted service bearer; tests inject a spy): when a seam result
        # lands after close/fail, the engine ALREADY persisted the draft into
        # book-service — swallowing the row is not enough, the content must be
        # rolled back to the unit's pinned pre_revision_id (best-effort).
        self._late_restore_impl = late_restore
        # D5: the per-unit continuity critic (None → the real in-process
        # engine seam; tests inject a fake, like the drafting seam).
        self._critic: CriticSeam = critic if critic is not None else EngineCriticSeam()
        # D4: terminal-notification producer (None → the real NotificationClient,
        # lazily — keeps unit tests httpx-free) + this driver's identity (tests
        # override to simulate a second process; defaults to the process id so
        # per-request service instances share one identity).
        self._notify_impl = notify
        self._driver_id = driver_id or _PROCESS_DRIVER_ID

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
        background: bool = False,
    ) -> AuthoringRun:
        """Create the run in `draft`. Deliberately permissive — ALL semantic
        validation happens at gate() (the start-gate is the enforcement point);
        only the referenced plan_run must exist+be owned (FK + tenancy).
        `background` (D4): a pure FE display/filter flag surfaced in GET/list —
        sweep-resume durability applies to BOTH fg and bg runs; the real fg/bg
        UX is FE-side later."""
        plan = await self._plan_runs.get_for_owner(owner_user_id, book_id, plan_run_id)
        if plan is None:
            raise LookupError("plan run not found")
        return await self._runs.create(
            owner_user_id, book_id,
            plan_run_id=plan_run_id, level=level, scope=scope,
            budget_usd=budget_usd, tool_allowlist=tool_allowlist,
            params=params or {}, background=background,
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
        # D4: the →running transition CLAIMS the run for this driver (driver_id
        # + heartbeat) in the same guarded UPDATE — no running-but-unclaimed gap.
        started = await self._runs.transition(
            owner_user_id, run_id, from_statuses=("gated",), to_status="running",
            claim_driver_id=self._driver_id,
        )
        if started is None:
            raise TransitionConflictError(f"start requires status=gated, run is {run.status}")
        if not self._spawn_driver(owner_user_id, run_id):
            # Deferred at the inflight cap: NULL the just-claimed heartbeat so
            # the NEXT sweep can pick the run up — a fresh heartbeat would make
            # it invisible to sweepers for the whole stale window.
            await self._runs.release_claim(run_id, self._driver_id)
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
            claim_driver_id=self._driver_id,
        )
        if resumed is None:
            raise TransitionConflictError(f"resume requires status=paused, run is {run.status}")
        if not self._spawn_driver(owner_user_id, run_id):
            await self._runs.release_claim(run_id, self._driver_id)  # see start()
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
                # D5: {severity, summary, cost_usd[, detail]} — None when the
                # unit was never critiqued (disabled / failed / boundary skip).
                "critic_verdict": u.critic_verdict if u else None,
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

    # ── driver (D4 durable: sweep-resumable, per-unit guarded claim) ────────

    @staticmethod
    def _live_driver_count() -> int:
        return sum(1 for t in _DRIVER_TASKS.values() if not t.done())

    def _spawn_driver(self, owner_user_id: UUID, run_id: UUID) -> bool:
        """Spawn the per-run driver task, respecting DRIVER_MAX_INFLIGHT.
        Returns False when the cap is hit — the run stays `running` unclaimed
        (its heartbeat goes stale) and the periodic sweep resumes it once a
        slot frees; durability, not loss."""
        if run_id in _DRIVER_TASKS and not _DRIVER_TASKS[run_id].done():
            return True  # already driving (resume raced a live task)
        if self._live_driver_count() >= settings.authoring_driver_max_inflight:
            logger.info(
                "authoring driver for run %s deferred: %d/%d driver slots busy "
                "(sweep resumes it when a slot frees)",
                run_id, self._live_driver_count(),
                settings.authoring_driver_max_inflight,
            )
            return False
        task = asyncio.create_task(self._drive_safe(owner_user_id, run_id))
        _DRIVER_TASKS[run_id] = task
        task.add_done_callback(lambda _t: _DRIVER_TASKS.pop(run_id, None))
        return True

    async def sweep_stale_runs(self) -> list[AuthoringRun]:
        """D4 restart-durability sweep (campaign claim_active_campaigns spirit;
        run at startup + every authoring_sweep_secs). Guarded-claims up to the
        free driver-slot count of `running` runs whose heartbeat is stale (no
        live driver anywhere — a restart killed the task, or a start was
        deferred at the inflight cap) and resumes each from current_unit. Both
        foreground AND background runs are swept (durability applies to both;
        `background` is a display flag). Returns the claimed runs."""
        capacity = settings.authoring_driver_max_inflight - self._live_driver_count()
        if capacity <= 0:
            return []
        claimed = await self._runs.claim_stale_running(
            driver_id=self._driver_id,
            stale_secs=settings.authoring_heartbeat_stale_secs,
            limit=capacity,
        )
        for run in claimed:
            logger.info(
                "authoring sweep: re-claimed stale run %s (unit %d/%d) — resuming",
                run.run_id, run.current_unit, len(run.scope),
            )
            if not self._spawn_driver(run.owner_user_id, run.run_id):
                # Lost a capacity race since the claim — hand the run back
                # (NULL heartbeat) so the next sweep retries immediately.
                await self._runs.release_claim(run.run_id, self._driver_id)
        return claimed

    async def _drive_safe(self, owner_user_id: UUID, run_id: UUID) -> None:
        try:
            await self.run_driver(owner_user_id, run_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a driver crash must land as failed, not vanish
            logger.exception("authoring driver crashed for run %s", run_id)
            failed = await self._runs.transition(
                owner_user_id, run_id,
                from_statuses=("running",), to_status="failed",
                breaker_state={"reason": "driver_crashed"},
                error_message="driver crashed — see service logs",
            )
            if failed is not None:
                await self._notify_terminal(failed)

    async def run_driver(self, owner_user_id: UUID, run_id: UUID) -> None:
        """Sequential per-unit loop. Each iteration re-CLAIMS the row (D4:
        guarded heartbeat bump — status='running' AND driver_id=mine) so an
        external pause/fail/close, or a sweep steal after a stale heartbeat,
        stops the driver at the unit boundary BEFORE the next seam call."""
        while True:
            run = await self._runs.heartbeat_claim(
                owner_user_id, run_id, self._driver_id,
            )
            if run is None:
                return  # paused/failed/closed externally, or claimed away — stop
            scope = run.scope
            if run.current_unit >= len(scope):
                ready = await self._runs.transition(
                    owner_user_id, run_id,
                    from_statuses=("running",), to_status="report_ready",
                )
                if ready is not None:  # terminal for the driver → notify (D4)
                    await self._notify_terminal(ready)
                return
            if run.spent_usd >= run.budget_usd:
                paused = await self._runs.transition(
                    owner_user_id, run_id,
                    from_statuses=("running",), to_status="paused",
                    breaker_state={
                        "reason": "budget",
                        "spent_usd": str(run.spent_usd),
                        "budget_usd": str(run.budget_usd),
                        "unit": run.current_unit,
                    },
                )
                if paused is not None:
                    # A breaker pause on a headless run NEEDS a human — the
                    # interrupt must reach them (07S), same channel as terminal.
                    await self._notify_terminal(paused)
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
            # D4 late-result fence: the drafted write is guarded on the run
            # still being running-or-paused AND still driven by THIS driver.
            # A run closed/failed mid-flight (e.g. pause→close→Revert-All raced
            # the seam) must SWALLOW the late result — mark the unit failed and
            # roll the engine-persisted content back, never drafted. A run
            # sweep-STOLEN mid-flight must leave the unit row entirely to the
            # new driver (its re-run owns it).
            drafted = await self._units.mark_drafted(
                owner_user_id, run_id, run.current_unit,
                post_revision_id=post_rev, cost_usd=cost,
                run_statuses=_LATE_RESULT_RUN_STATUSES,
                run_driver_id=self._driver_id,
            )
            # Spend is REAL either way (the seam did run) — record it before
            # anything else so accounting never loses a late unit's cost. The
            # cursor half is driver-fenced (a superseded driver must not rewind
            # the new driver's cursor); the spend half always lands.
            await self._runs.record_unit_progress(
                owner_user_id, run_id,
                add_spent_usd=cost, current_unit=run.current_unit + 1,
                driver_id=self._driver_id,
            )
            if drafted is None:
                fresh = await self._runs.get_for_owner(owner_user_id, run_id)
                stolen = (
                    fresh is not None
                    and fresh.status in _LATE_RESULT_RUN_STATUSES
                    and fresh.driver_id != self._driver_id
                )
                if stolen:
                    # The new driver owns the unit row (its upsert re-pinned the
                    # baseline) — touching it here would clobber its attempt.
                    logger.warning(
                        "authoring run %s unit %d: seam result superseded by a "
                        "sweep steal — spend recorded, unit left to the new driver",
                        run_id, run.current_unit,
                    )
                    return
                # Closed/failed mid-flight: the engine already PATCHed the draft
                # into book-service — best-effort restore of the pinned pre-run
                # revision, then land the unit as failed with an honest message.
                error = "run closed mid-flight"
                if pre_rev is not None:
                    try:
                        await self._late_restore(
                            owner_user_id, run.book_id, chapter_id, pre_rev,
                        )
                        error += "; draft reverted to pre-run revision"
                    except Exception as exc:  # noqa: BLE001 — best-effort
                        logger.warning(
                            "authoring run %s unit %d: late-swallow restore "
                            "failed — chapter draft left mutated",
                            run_id, run.current_unit, exc_info=True,
                        )
                        error += f"; pre-run restore FAILED ({exc}) — draft left in place"
                await self._units.mark_failed(
                    owner_user_id, run_id, run.current_unit, error=error,
                )
                logger.warning(
                    "authoring run %s unit %d: late seam result after close/fail "
                    "— unit marked failed, draft not accounted",
                    run_id, run.current_unit,
                )
                return
            # D5 continuity critic — post-draft, per-unit, same guarded-claim
            # discipline as the seam. False → stop at the unit boundary
            # (paused/closed/stolen while drafting, or a severe verdict paused
            # the run). params.critic_enabled defaults TRUE; explicit falsy
            # disables (an autonomous run keeps the net unless told otherwise).
            if run.params.get("critic_enabled", True):
                if not await self._critique_unit(owner_user_id, run_id, run,
                                                 chapter_id):
                    return

    async def _critique_unit(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        run: AuthoringRun,
        chapter_id: UUID,
    ) -> bool:
        """Critique the just-drafted unit `run.current_unit` (D5). Returns
        False when the driver must STOP at this unit boundary:
        * the guarded heartbeat claim failed (run paused/failed/closed
          externally, or a sweep stole it while the seam ran) — the critique
          is SKIPPED (verdict stays NULL; the report shows the gap), or
        * the verdict is 'severe' — the breaker pauses the run
          (reason critic_severe; 07S: interrupt on severe — pause, NOT fail,
          the human reviews the report and resumes/reverts).
        A critic exception is never fatal: it lands as a 'warn' verdict
        ('critic unavailable') and the run continues."""
        claim = await self._runs.heartbeat_claim(
            owner_user_id, run_id, self._driver_id,
        )
        if claim is None:
            return False  # stopped/stolen at the boundary — skip the critique
        try:
            verdict = await self._critic.critique(
                owner_user_id=owner_user_id, book_id=run.book_id,
                chapter_id=chapter_id, plan_run_id=run.plan_run_id,
                params=run.params,
            )
        except Exception:  # noqa: BLE001 — critic failure is NEVER fatal (07S)
            logger.warning(
                "authoring critic failed for run %s unit %d (non-fatal)",
                run_id, run.current_unit, exc_info=True,
            )
            verdict = CriticVerdict(severity="warn", summary="critic unavailable")
        row = verdict.as_row()  # sanitizes an off-contract severity to 'warn'
        stored = await self._units.set_critic_verdict(
            owner_user_id, run_id, run.current_unit, verdict=row,
        )
        if stored is None:  # unit raced away from drafted — verdict dropped
            logger.warning(
                "authoring run %s unit %d: critic verdict not stored "
                "(unit no longer drafted)", run_id, run.current_unit,
            )
        # Critique spend is real — add it to the run's spend so it feeds the
        # budget breaker (cursor already sits at current_unit + 1; re-passing
        # it is idempotent, record_unit_progress is status-agnostic).
        if verdict.cost_usd and verdict.cost_usd > 0:
            await self._runs.record_unit_progress(
                owner_user_id, run_id,
                add_spent_usd=verdict.cost_usd, current_unit=run.current_unit + 1,
                driver_id=self._driver_id,
            )
        if row["severity"] == "severe":
            paused = await self._runs.transition(
                owner_user_id, run_id,
                from_statuses=("running",), to_status="paused",
                breaker_state={
                    "reason": "critic_severe",
                    "unit_index": run.current_unit,
                    "chapter_id": str(chapter_id),
                    "summary": verdict.summary,
                },
            )
            if paused is not None:
                # 07S "interrupt on severe": the interrupt must actually reach
                # the human — a silent pause on a background run never would.
                await self._notify_terminal(paused)
            return False
        return True

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
        failed = await self._runs.transition(
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
        if failed is not None:  # terminal transition won → notify (D4)
            await self._notify_terminal(failed)

    async def _late_restore(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        revision_id: UUID,
    ) -> None:
        """Roll a late-swallowed unit's chapter back to its pinned pre-run
        revision. Headless (no caller request in flight) — the real path mints
        a service bearer for the run OWNER exactly like BookRevisionCapture
        (book-service still enforces the grant boundary on the JWT `sub`).
        Tests inject a 3-arg RestoreFn spy via the ctor's `late_restore`."""
        if self._late_restore_impl is not None:
            await self._late_restore_impl(book_id, chapter_id, revision_id)
            return
        from app.clients.book_client import get_book_client
        from app.mcp.service_bearer import mint_service_bearer

        bearer = mint_service_bearer(owner_user_id, settings.jwt_secret)
        await get_book_client().restore_revision(
            book_id, chapter_id, revision_id, bearer,
        )

    # ── D4 completion notification (best-effort, never affects the run) ─────

    async def _notify_terminal(self, run: AuthoringRun) -> None:
        """Best-effort notification on a driver stop the human must hear about:
        terminal transitions (report_ready | failed) AND breaker pauses
        (budget | critic_severe — 07S "interrupt on severe" only interrupts if
        it reaches the human). notification-service HTTP ingest, mirroring
        translation-service's chapter_worker producer. Every failure (including
        a broken injected notifier) is swallowed: notify must never affect the
        run's outcome."""
        try:
            units = await self._units.list_for_run(run.run_id)
            units_drafted = sum(
                1 for u in units if u.status in ("drafted", "accepted")
            )
            if run.status == "report_ready":
                title = (
                    f"Autonomous authoring run complete — "
                    f"{units_drafted} chapter(s) drafted"
                )
            elif run.status == "paused":
                reason = (run.breaker_state or {}).get("reason", "breaker")
                title = (
                    f"Autonomous authoring run paused ({reason}) — "
                    f"{units_drafted} chapter(s) drafted; review needed"
                )
            else:
                title = (
                    f"Autonomous authoring run failed — "
                    f"{units_drafted} chapter(s) drafted before the stop"
                )
            notify = self._notify_impl
            if notify is None:  # lazy real client (keeps unit tests httpx-free)
                from app.clients.notification_client import NotificationClient

                notify = NotificationClient()
            await notify.notify(
                run.owner_user_id,
                title=title,
                metadata={
                    "operation": "autonomous_authoring",
                    "run_id": str(run.run_id),
                    "book_id": str(run.book_id),
                    "status": run.status,
                    "units_drafted": units_drafted,
                    "spent_usd": str(run.spent_usd),
                },
            )
        except Exception:  # noqa: BLE001 — best-effort by contract
            logger.warning(
                "authoring run %s terminal notification failed (ignored)",
                run.run_id, exc_info=True,
            )
