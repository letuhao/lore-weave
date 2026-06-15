"""Internal dispatch endpoint — Auto-Draft Factory S1 (decision A).

`POST /internal/translation/dispatch-job` lets a trusted internal caller
(campaign-service) create a translation job ON BEHALF OF a user, over an
internal-token call carrying the VERIFIED `user_id` in the body — NOT a minted
user-JWT. Ownership is re-verified against the asserted `user_id` (defense in
depth) before reusing the exact same job-create core as the public route.

Mounted under `/internal/*` → reachable service-to-service inside the cluster
only; the gateway proxies `/v1/*`, never `/internal/*`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from ..config import settings as app_settings
from ..deps import get_db
from ..grant_deps import GrantLevel, authorize_book
from ..grant_client import get_grant_client
from ..models import CreateJobPayload
from ..workers.segment_store import ensure_chapter_segments
from ..workers.segment_status import compute_segment_status
from .jobs import _resolve_and_create_job, _cancel_job_core

router = APIRouter(prefix="/internal/translation", tags=["internal"])


async def _verify_book_owner(book_id: UUID, user_id: str) -> None:
    """E0-4a: re-verify the asserted `user_id` has at least EDIT on `book_id`
    (defense in depth — the internal token authenticates the SERVICE; this
    confirms the USER claim). Was an owner-only book-projection check; now a
    book-grant check so a collaborator dispatched by a campaign (4b) is honored.
    Raises 404 (no grant — anti-oracle) / 403 (under edit)."""
    await authorize_book(get_grant_client(), book_id, UUID(user_id), GrantLevel.EDIT)


async def require_internal_token(
    x_internal_token: str | None = Header(default=None),
) -> None:
    if (
        not app_settings.internal_service_token
        or x_internal_token != app_settings.internal_service_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TRANSL_INVALID_INTERNAL_TOKEN", "message": "invalid internal token"},
        )


class InternalDispatchPayload(BaseModel):
    user_id: UUID
    book_id: UUID
    chapter_ids: list[UUID]
    target_language: str | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    # S5b: per-campaign V3 verifier model (null → falls back to the translator,
    # per v3/orchestrator.py _verifier_model). CreateJobPayload already overlays
    # + persists + publishes these; we just forward them.
    verifier_model_source: str | None = None
    verifier_model_ref: UUID | None = None
    # S5b-eval: per-campaign translation eval-judge model. Rides through to the
    # translation.quality event (not used by the worker) so learning's M7d-2
    # fidelity judge uses the campaign's chosen model.
    eval_judge_model_source: str | None = None
    eval_judge_model_ref: UUID | None = None
    # D-FACTORY-V3-PIPELINE: the Auto-Draft Factory IS the V3 quality pipeline
    # (Translator→Verifier→Corrector + the M7a `translation.quality` emit that the
    # eval stage + S5b-eval judge depend on). This endpoint is campaign-only, so it
    # defaults to 'v3' — without it the job runs the book/user default (usually v2),
    # the verifier never runs, no `translation.quality` fires, and the campaign's
    # eval stage + eval_fidelity_score never engage. Overridable if a campaign ever
    # needs v2.
    pipeline_version: str | None = "v3"
    # S2: default-skip idempotency applies here too (the campaign driver relies
    # on it — re-dispatching an already-translated chapter must not re-spend).
    force_retranslate: bool = False
    # S4a: the owning campaign, threaded into the job + every provider job_meta.
    campaign_id: UUID | None = None


class DispatchResponse(BaseModel):
    job_id: UUID


@router.post(
    "/dispatch-job",
    response_model=DispatchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_token)],
)
async def dispatch_job(
    payload: InternalDispatchPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> DispatchResponse:
    if not payload.chapter_ids:
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_NO_CHAPTERS", "message": "chapter_ids is empty"},
        )
    user_id = str(payload.user_id)
    # Re-verify the asserted user actually owns the book (defense in depth — the
    # internal token authenticates the SERVICE, this confirms the USER claim).
    await _verify_book_owner(payload.book_id, user_id)
    # model_source + model_ref are a pair (CreateJobPayload enforces it). When the
    # campaign supplies no model_ref, leave BOTH unset so the job falls back to the
    # user's saved translation settings rather than 422-ing on a half-override.
    model_source = payload.model_source if payload.model_ref else None
    # Same pairing rule for the verifier override: keep both unset on a half-override.
    verifier_model_source = payload.verifier_model_source if payload.verifier_model_ref else None
    eval_judge_model_source = payload.eval_judge_model_source if payload.eval_judge_model_ref else None
    job = await _resolve_and_create_job(
        db,
        payload.book_id,
        CreateJobPayload(
            chapter_ids=payload.chapter_ids,
            target_language=payload.target_language,
            model_source=model_source,
            model_ref=payload.model_ref,
            verifier_model_source=verifier_model_source,
            verifier_model_ref=payload.verifier_model_ref,
            eval_judge_model_source=eval_judge_model_source,
            eval_judge_model_ref=payload.eval_judge_model_ref,
            pipeline_version=payload.pipeline_version,  # D-FACTORY-V3-PIPELINE (default 'v3')
            force_retranslate=payload.force_retranslate,
        ),
        user_id,
        campaign_id=payload.campaign_id,
    )
    return DispatchResponse(job_id=job.job_id)


class RebuildSegmentsPayload(BaseModel):
    book_id: UUID


class RebuildSegmentsResponse(BaseModel):
    chapter_id: str
    segments: int
    changed: bool


@router.post(
    "/chapters/{chapter_id}/segments/rebuild",
    response_model=RebuildSegmentsResponse,
    dependencies=[Depends(require_internal_token)],
)
async def rebuild_chapter_segments(
    chapter_id: UUID,
    payload: RebuildSegmentsPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> RebuildSegmentsResponse:
    """T2-M1: (re)build a chapter's source-side segments from its current blocks.
    Idempotent — unchanged source is a no-op. Internal-token only (the full backfill
    loops this over every chapter at deploy)."""
    res = await ensure_chapter_segments(db, payload.book_id, chapter_id)
    return RebuildSegmentsResponse(**res)


class SegmentStatusItem(BaseModel):
    segment_index: int
    start_block_index: int
    end_block_index: int
    token_estimate: int
    translated: bool
    dirty: bool
    stale: bool = False
    needs: bool = False
    translated_at: str | None = None


class SegmentStatusResponse(BaseModel):
    chapter_id: str
    target_language: str
    segments: list[SegmentStatusItem]
    dirty_count: int
    needs_count: int = 0


@router.get(
    "/chapters/{chapter_id}/segments/status",
    response_model=SegmentStatusResponse,
    dependencies=[Depends(require_internal_token)],
)
async def internal_segment_status(
    chapter_id: UUID,
    target_language: str = Query(...),
    db: asyncpg.Pool = Depends(get_db),
) -> SegmentStatusResponse:
    """T2-M2: per-segment translation status for a chapter+language (internal-token).
    dirty = the segment's source changed since it was last translated, or it was
    never translated for this language. Empty `segments` → the chapter has no
    segments built yet (run the rebuild/backfill)."""
    items = await compute_segment_status(db, chapter_id, target_language)
    return SegmentStatusResponse(
        chapter_id=str(chapter_id),
        target_language=target_language,
        segments=[SegmentStatusItem(**it) for it in items],
        dirty_count=sum(1 for it in items if it["dirty"]),
        needs_count=sum(1 for it in items if it["needs"]),
    )


class ChapterStatusResponse(BaseModel):
    # Normalized truth vocab the campaign reconcile understands (NOT the raw
    # chapter_translations.status). "done" → mark the campaign row done;
    # "failed"/"gone" → reset for re-dispatch; "running" → leave (in-flight).
    status: str  # "done" | "failed" | "running" | "gone"


@router.get(
    "/jobs/{job_id}/chapters/{chapter_id}/status",
    response_model=ChapterStatusResponse,
    dependencies=[Depends(require_internal_token)],
)
async def dispatch_chapter_status(
    job_id: UUID,
    chapter_id: UUID,
    user_id: UUID = Query(...),
    db: asyncpg.Pool = Depends(get_db),
) -> ChapterStatusResponse:
    """D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: ground-truth for the campaign's
    stuck-`dispatched` reconcile. Tells whether a chapter's translation actually
    completed (so a lost `chapter.translated`/`chapter.translation_skipped` event
    can be reconciled to `done` WITHOUT re-dispatching), is still in-flight (leave),
    or didn't produce a fresh translation (reset for re-dispatch).

    The "done" truth MIRRORS the S2 idempotency skip-gate (jobs.py): a chapter is
    done iff a **fresh completed** translation EXISTS for this job's language
    (status='completed' AND not glossary-stale) — keyed on (language, chapter),
    NOT on this job. That is load-bearing: a chapter the gate SKIPPED has no
    per-job row yet still has a fresh version, so a per-job lookup would wrongly
    report 'failed' → reset → re-dispatch → skip → … → falsely fail a chapter that
    is in fact translated. A glossary-STALE completed row is intentionally NOT
    'done' (the gate re-translates it), so it falls through to 'failed' once the
    job is terminal → re-dispatch refreshes it (loop-free: the refreshed row is
    non-stale → 'done' next time).

    Owner-scoped via the asserted `user_id`; a not-found/not-owned job → 404 (the
    caller maps that to a safe re-dispatch)."""
    job = await db.fetchrow(
        "SELECT owner_user_id, status, target_language FROM translation_jobs WHERE job_id=$1",
        job_id,
    )
    if not job or str(job["owner_user_id"]) != str(user_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"},
        )

    lang = job["target_language"]
    if lang is not None:
        fresh = await db.fetchval(
            """
            SELECT 1 FROM chapter_translations
            WHERE target_language = $1 AND chapter_id = $2
              AND status = 'completed' AND is_glossary_stale = false
            LIMIT 1
            """,
            lang, chapter_id,
        )
        if fresh:
            return ChapterStatusResponse(status="done")

    # Not freshly translated. A still-active job may yet produce it (leave); a
    # terminal job that didn't → re-dispatch (the gate prevents re-spend on a
    # chapter that DID complete fresh — that path returned 'done' above).
    if job["status"] in ("pending", "running", "paused"):
        return ChapterStatusResponse(status="running")
    return ChapterStatusResponse(status="failed")


class JobStatusResponse(BaseModel):
    # "active" → still pending/running (chapters legitimately in-flight; leave);
    # "terminal" → completed/failed/cancelled (resolve chapters per-chapter).
    status: str  # "active" | "terminal"


@router.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    dependencies=[Depends(require_internal_token)],
)
async def dispatch_job_status(
    job_id: UUID,
    user_id: UUID = Query(...),
    db: asyncpg.Pool = Depends(get_db),
) -> JobStatusResponse:
    """D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: a campaign dispatches a chapter batch as
    ONE job, so the reconcile checks job aliveness ONCE per job (not per chapter)
    before any per-chapter truth — bounding the truth fan-out for a slow-but-alive
    job to a single call per tick. Owner-scoped; 404 if not found/owned (the caller
    maps that to a safe re-dispatch)."""
    job = await db.fetchrow(
        "SELECT owner_user_id, status FROM translation_jobs WHERE job_id=$1", job_id
    )
    if not job or str(job["owner_user_id"]) != str(user_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"},
        )
    active = job["status"] in ("pending", "running")
    return JobStatusResponse(status="active" if active else "terminal")


class InternalCancelPayload(BaseModel):
    user_id: UUID


@router.post(
    "/jobs/{job_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal_token)],
)
async def dispatch_cancel(
    job_id: UUID,
    payload: InternalCancelPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> None:
    """S3c-2: cancel a translation job on behalf of a campaign (internal-token +
    asserted user_id). Reuses the public cancel core — owner-scoped (404 if not
    owned), 409 if already terminal (the campaign treats both as success)."""
    await _cancel_job_core(db, job_id, str(payload.user_id))


# translation_jobs has no `updated_at`; its mutation timestamps are created_at /
# started_at / finished_at — GREATEST of them is the row's effective last-touch.
_TRANSL_TS = "GREATEST(created_at, COALESCE(started_at, created_at), COALESCE(finished_at, created_at))"


@router.get("/jobs", dependencies=[Depends(require_internal_token)])
async def reconcile_jobs(
    since: datetime = Query(..., description="ISO-8601 — rows updated at/after this"),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Reconcile SOURCE (Unified Job Control Plane H1 backstop): translation jobs whose
    effective last-touch is at/after `since`, in canonical `JobEvent` payload shape, for
    the jobs-service sweep to upsert. Internal-token; ALL owners. `partial` → `completed`
    (the job finished, some chapters done — mirrors the worker's terminal emit)."""
    rows = await db.fetch(
        f"SELECT job_id, owner_user_id, status, error_message, {_TRANSL_TS} AS ts "
        f"FROM translation_jobs WHERE {_TRANSL_TS} >= $1 ORDER BY ts ASC LIMIT 1000",
        since,
    )
    out = []
    for r in rows:
        st = "completed" if r["status"] == "partial" else r["status"]
        out.append({
            "service": "translation", "job_id": str(r["job_id"]),
            "owner_user_id": str(r["owner_user_id"]), "kind": "translation", "status": st,
            "parent_job_id": None, "detail_status": None, "progress": None, "title": None,
            "error": ({"code": "translation_failed", "message": (r["error_message"] or "")[:500]}
                      if st == "failed" else None),
            "occurred_at": r["ts"].isoformat() if r["ts"] else None,
        })
    return {"jobs": out}


class JobControlPayload(BaseModel):
    # The asserted OWNER (jobs-service forwards the verified JWT sub). Re-verified
    # against the row by the owner-scoped _cancel_job_core — M4.
    owner_user_id: UUID


@router.post("/job-control/{job_id}/{action}", dependencies=[Depends(require_internal_token)])
async def control_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Unified Job Control Plane P3 — the `job_id`-keyed control surface the central
    jobs-service forwards user actions to. A translation job is multi-chapter, but
    its workers honor only CANCEL today (each chapter skips a `cancelled` job); real
    pause/resume = stop-dispatch + drain is a separate money-path feature
    (D-JOBS-P3-TRANSLATION-PAUSE) → this is **cancel-only**, and translation is
    therefore NOT in jobs-service `_MULTI_UNIT_KINDS` (the caps-gate won't offer
    pause/resume, so they never reach here; we 400 defensively).

    A DISTINCT prefix from the campaign cancel (`/internal/translation/jobs/{job_id}/
    cancel`, which takes a `user_id` body) so the control-plane contract (an
    `owner_user_id` body) doesn't collide on the route. Reuses the owner-scoped
    `_cancel_job_core` — M4 re-check (404 if not owned), 409 if already terminal."""
    if action != "cancel":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TRANSL_UNSUPPORTED_ACTION",
                    "message": f"translation jobs support only 'cancel', not '{action}'"},
        )
    await _cancel_job_core(db, job_id, str(payload.owner_user_id))
    return {"job_id": str(job_id), "status": "cancelled"}
