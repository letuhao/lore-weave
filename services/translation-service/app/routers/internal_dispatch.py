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
from loreweave_jobs import emit_job_event
from pydantic import BaseModel

from ..config import settings as app_settings
from ..deps import get_db
from ..grant_deps import GrantLevel, authorize_book
from ..grant_client import get_grant_client
from ..models import CreateJobPayload
from ..workers.extraction_cache import purge_stale_raw_outputs
from ..workers.extraction_outcomes import reconcile_from_rows
from ..workers.segment_store import ensure_chapter_segments
from ..workers.segment_status import compute_segment_status
from .jobs import _resolve_and_create_job, _cancel_job_core, _pause_job_core, _resume_job_core

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
    limit: int = Query(1000, ge=1, le=5000, description="page cap — the sweeper's _PAGE_LIMIT"),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Reconcile SOURCE (Unified Job Control Plane H1 backstop): translation-service jobs
    whose effective last-touch is at/after `since` (oldest-first, capped at `limit`), in
    canonical `JobEvent` payload shape, for the jobs-service sweep to upsert. Internal-token;
    ALL owners. UNIONs every translation-service job table (one `kind` each) so each is
    covered by the same single reconcile source: `translation_jobs` (kind `translation`) +
    `extraction_jobs` (glossary-extract, kind `glossary_extraction`,
    D-JOBS-GLOSSARY-EXTRACT-UNWIRED) + `glossary_translation_jobs` (glossary batch translate,
    kind `glossary_translation`, D-JOBS-GLOSSARY-TRANSLATE-UNWIRED). Status normalization to
    canonical: `partial` / `completed_with_errors` → `completed` (the job finished with some
    per-unit failures — mirrors the workers' terminal emit). The effective-ts expression is
    shared (all three tables have created_at/started_at/finished_at). NOTE: the per-source
    watermark is shared across the unioned kinds, so a burst in one table can delay the
    others' reconcile — acceptable for a backstop (the live emit is primary)."""
    rows = await db.fetch(
        "SELECT job_id, owner_user_id, status, error_message, kind, ts FROM ("
        f"  SELECT job_id, owner_user_id, status, error_message, 'translation' AS kind, "
        f"         {_TRANSL_TS} AS ts FROM translation_jobs"
        "   UNION ALL "
        f"  SELECT job_id, owner_user_id, status, error_message, 'glossary_extraction' AS kind, "
        f"         {_TRANSL_TS} AS ts FROM extraction_jobs"
        "   UNION ALL "
        f"  SELECT job_id, owner_user_id, status, error_message, 'glossary_translation' AS kind, "
        f"         {_TRANSL_TS} AS ts FROM glossary_translation_jobs"
        ") s WHERE ts >= $1 ORDER BY ts ASC LIMIT $2",
        since, limit,
    )
    out = []
    for r in rows:
        st = "completed" if r["status"] in ("partial", "completed_with_errors") else r["status"]
        out.append({
            "service": "translation", "job_id": str(r["job_id"]),
            "owner_user_id": str(r["owner_user_id"]), "kind": r["kind"], "status": st,
            "parent_job_id": None, "detail_status": None, "progress": None, "title": None,
            "error": ({"code": f"{r['kind']}_failed", "message": (r["error_message"] or "")[:500]}
                      if st == "failed" else None),
            "occurred_at": r["ts"].isoformat() if r["ts"] else None,
        })
    return {"jobs": out}


@router.get("/extraction-jobs/{job_id}/reconcile", dependencies=[Depends(require_internal_token)])
async def reconcile_extraction_job(
    job_id: UUID,
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """OBS/M2 reconciliation sweep (INV-O12): re-derive an extraction job's stats from the
    `extraction_batch_outcomes` SSOT rows and compare to the cached counters on
    `extraction_jobs`. The outcome rows are the truth; the job-row counters are a cache a
    mid-update crash can skew. Report-only by design — it surfaces drift (so a sweeper / ops
    dashboard can detect a divergence) without auto-correcting the convergence-critical
    completed/failed counters, which are chapter-grained and must not be clobbered by a
    batch-grained re-derivation mid-flight. Internal-token; any owner."""
    job = await db.fetchrow(
        "SELECT status, completed_chapters, failed_chapters, total_chapters "
        "FROM extraction_jobs WHERE job_id=$1", job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "EXTRACT_JOB_NOT_FOUND", "message": "Job not found"})
    rows = await db.fetch(
        "SELECT chapter_id, status FROM extraction_batch_outcomes WHERE job_id=$1", job_id)
    ssot = reconcile_from_rows([(r["chapter_id"], r["status"]) for r in rows])
    # A chapter is "finished" in the SSOT when it has any outcome rows; compare that count to
    # the job row's completed_chapters (clean + with-errors both count as finished).
    derived_finished = ssot["chapters_completed"] + ssot["chapters_with_errors"]
    return {
        "job_id": str(job_id),
        "ssot": ssot,
        "job_row": {
            "status": job["status"],
            "completed_chapters": job["completed_chapters"],
            "failed_chapters": job["failed_chapters"],
            "total_chapters": job["total_chapters"],
        },
        "drift": derived_finished != (job["completed_chapters"] or 0),
    }


class CacheRetentionPayload(BaseModel):
    # All optional — unfiltered = the GLOBAL retention sweep (the scheduled job); the
    # scope fields narrow it to one tenant/book/chapter for a targeted compaction.
    keep: int = 3
    owner_user_id: UUID | None = None
    book_id: UUID | None = None
    chapter_id: UUID | None = None


@router.post("/extraction-cache/retention", dependencies=[Depends(require_internal_token)])
async def extraction_cache_retention(
    payload: CacheRetentionPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """CACHE/M6 retention (architecture §8.1): purge stale `extraction_raw_outputs`
    generations, keeping the latest `keep` content-hash versions per (owner, book,
    chapter). This is the maintenance seam a scheduler/cron hits — internal-token only
    (it is a platform housekeeping op, not a user action; no grant gate, every owner's
    cache is in scope when unfiltered). The optional scope fields target one tenant/book/
    chapter. Best-effort: a purge failure returns deleted=0, never raises (retention must
    not break a cron run)."""
    deleted = await purge_stale_raw_outputs(
        db,
        keep=payload.keep,
        owner_user_id=str(payload.owner_user_id) if payload.owner_user_id else None,
        book_id=str(payload.book_id) if payload.book_id else None,
        chapter_id=str(payload.chapter_id) if payload.chapter_id else None,
    )
    return {"deleted": deleted, "keep": payload.keep}


class JobControlPayload(BaseModel):
    # The asserted OWNER (jobs-service forwards the verified JWT sub). Re-verified
    # against the row by the owner-scoped cancel cores — M4.
    owner_user_id: UUID
    # The job KIND (D-JOBS-SECONDARY-KIND-CONTROL) — translation-service hosts THREE job
    # tables, so control_job dispatches by kind: translation (default) / glossary_extraction
    # (extraction_jobs) / glossary_translation (glossary_translation_jobs). None ⇒ translation
    # (back-compat for an older jobs-service that doesn't send kind).
    kind: str | None = None


@router.post("/job-control/{job_id}/{action}", dependencies=[Depends(require_internal_token)])
async def control_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Unified Job Control Plane P3 — the `job_id`-keyed control surface the central
    jobs-service forwards user actions to. A translation job is multi-chapter and now
    supports stop-dispatch **pause/resume** (B2, D-JOBS-P3-TRANSLATION-PAUSE) alongside
    cancel + retry, so translation IS in jobs-service `_MULTI_UNIT_KINDS` (the caps-gate
    offers pause when running / resume when paused). pause = stop dispatching new chapter
    units (the worker drops them at its start gate; in-flight chapters drain); resume =
    re-drive the un-done chapters from the stored job row.

    A DISTINCT prefix from the campaign cancel (`/internal/translation/jobs/{job_id}/
    cancel`, which takes a `user_id` body) so the control-plane contract (an
    `owner_user_id` body) doesn't collide on the route. The pause/resume/cancel cores are
    owner-scoped — M4 re-check (404 if not owned), 409 on an illegal transition.

    Dispatches by `kind` (D-JOBS-SECONDARY-KIND-CONTROL): translation-service also hosts the
    glossary-extract (`extraction_jobs`) + glossary-translate (`glossary_translation_jobs`)
    producers; both are CANCEL-ONLY (their native endpoints only cancel)."""
    secondary = _SECONDARY_CANCEL.get(payload.kind or "")
    if secondary is not None:
        if action != "cancel":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "TRANSL_UNSUPPORTED_ACTION",
                        "message": f"{payload.kind} jobs support only 'cancel', not '{action}'"},
            )
        table, kind = secondary
        return await _cancel_secondary_core(db, job_id, payload.owner_user_id, table, kind)
    if action == "retry":
        return await _retry_job_core(db, job_id, payload.owner_user_id)
    if action == "pause":
        return await _pause_job_core(db, job_id, payload.owner_user_id)
    if action == "resume":
        return await _resume_job_core(db, job_id, payload.owner_user_id)
    if action != "cancel":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TRANSL_UNSUPPORTED_ACTION",
                    "message": f"translation jobs support 'cancel'/'pause'/'resume'/'retry', not '{action}'"},
        )
    await _cancel_job_core(db, job_id, str(payload.owner_user_id))
    return {"job_id": str(job_id), "status": "cancelled"}


# kind → (job table, canonical emit kind). The table is a FIXED literal (never user input),
# so the f-string interpolation below is injection-safe.
_SECONDARY_CANCEL: dict[str, tuple[str, str]] = {
    "glossary_extraction": ("extraction_jobs", "glossary_extraction"),
    "glossary_translation": ("glossary_translation_jobs", "glossary_translation"),
}


async def _cancel_secondary_core(
    db: asyncpg.Pool, job_id: UUID, owner_user_id: UUID, table: str, kind: str,
) -> dict:
    """Owner-scoped cancel for a translation-hosted SECONDARY producer (glossary-extract /
    glossary-translate). Mirrors the native cancel endpoints: 404 if not found/owned (M4),
    409 unless pending|running, else UPDATE→cancelling + emit the transition in one tx (H1).
    The worker settles it to 'cancelled' + emits the terminal."""
    async with db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f"SELECT owner_user_id, status FROM {table} WHERE job_id=$1", job_id)
            if row is None or str(row["owner_user_id"]) != str(owner_user_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})
            if row["status"] not in ("pending", "running"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "TRANSL_JOB_NOT_CANCELLABLE", "message": f"Job is {row['status']}"})
            await conn.execute(
                f"UPDATE {table} SET status='cancelling' WHERE job_id=$1", job_id)
            await emit_job_event(
                conn, service="translation", job_id=str(job_id),
                owner_user_id=str(owner_user_id), kind=kind, status="cancelling")
    return {"job_id": str(job_id), "status": "cancelling"}


async def _retry_job_core(db: asyncpg.Pool, job_id: UUID, owner_user_id: UUID) -> dict:
    """D-JOBS-P4-RETRY — re-submit a FAILED translation job as a FRESH job (new job_id),
    reusing the failed row's model/language/pipeline/QA params. Owner-scoped (M4 re-check:
    404 if not owned). 409 unless the job is `failed` (retry is only offered there). The
    retried job is created STANDALONE (campaign_id=None) — a user retry is detached from any
    original campaign saga, which orchestrates its own jobs. `force_retranslate=True` re-runs
    the stored chapter set regardless of the skip-gate. Prompts + any unset params resolve
    from the user's CURRENT settings (the model/language/pipeline choices are preserved)."""
    row = await db.fetchrow(
        "SELECT * FROM translation_jobs WHERE job_id=$1 AND owner_user_id=$2",
        job_id, owner_user_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRANSL_NOT_FOUND", "message": "job not found"},
        )
    if row["status"] != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TRANSL_NOT_RETRYABLE",
                    "message": f"only a failed job can be retried (status='{row['status']}')"},
        )
    # review-impl MED — a campaign-dispatched job is MANAGED BY ITS CAMPAIGN (the saga
    # re-dispatches failed stages + owns the spend accounting). A standalone user retry
    # would detach from the campaign AND risk double-spend if the campaign also re-runs it.
    # Refuse here (the cap-gate can't see campaign_id — it's not on the projection — so the
    # button may still show for a campaign job; gating it there needs the projection to carry
    # campaign membership, tracked D-JOBS-P4-RETRY-CAMPAIGN-GATE).
    if row["campaign_id"] is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TRANSL_CAMPAIGN_MANAGED",
                    "message": "this translation job is managed by its campaign — retry the campaign, not the job"},
        )
    payload = CreateJobPayload(
        chapter_ids=list(row["chapter_ids"]),
        target_language=row["target_language"],
        model_source=row["model_source"],
        model_ref=row["model_ref"],
        pipeline_version=row["pipeline_version"],
        qa_depth=row["qa_depth"],
        max_qa_rounds=row["max_qa_rounds"],
        verifier_model_source=row["verifier_model_source"],
        verifier_model_ref=row["verifier_model_ref"],
        eval_judge_model_source=row["eval_judge_model_source"],
        eval_judge_model_ref=row["eval_judge_model_ref"],
        cold_start_mode=row["cold_start_mode"],
        block_index_filter=row["block_index_filter"],
        seed_version_id=row["seed_version_id"],
        force_retranslate=True,
    )
    new_job = await _resolve_and_create_job(
        db, row["book_id"], payload, str(owner_user_id), campaign_id=None,
    )
    return {"job_id": str(new_job.job_id), "status": new_job.status,
            "retried_from": str(job_id)}
