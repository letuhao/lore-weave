"""
GEP-BE-10: Extraction job creation + cancellation endpoints.

POST /v1/extraction/books/{book_id}/extract-glossary — create extraction job
POST /v1/extraction/jobs/{job_id}/cancel — cancel running job
GET  /v1/extraction/jobs/{job_id} — get job status

Design reference: GLOSSARY_EXTRACTION_PIPELINE.md §5.2, §5.3
"""
from __future__ import annotations

import json
from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException
from loreweave_jobs import emit_job_event
from pydantic import BaseModel, Field

from ..broker import publish, publish_event
from ..config import settings as app_settings
from ..deps import get_current_user, get_db
from ..grant_client import get_grant_client
from ..grant_deps import (
    GrantLevel,
    authorize_book,
    clamp_effort_to_grant,
    get_grant_client_dep,
    require_book_grant,
)
from ..model_name import resolve_model_name
from ..workers.extraction_model import get_model_context_window
from ..workers.extraction_prompt import estimate_extraction_cost
from ..workers.glossary_client import fetch_extraction_profile

router = APIRouter(prefix="/v1/extraction", tags=["extraction-jobs"])

# Unified Job Control Plane (producer-emit backfill, D-JOBS-GLOSSARY-EXTRACT-UNWIRED).
# Glossary extraction is hosted in translation-service; it surfaces in the unified Jobs
# screen as service="translation", kind="glossary_extraction" (DISTINCT from knowledge's
# "extraction"). The worker emits running/terminal/cancelled; the reconcile UNION in
# internal_dispatch.py is the H1 backstop.
_JOB_SERVICE = "translation"
_JOB_KIND = "glossary_extraction"


class CreateExtractionJobPayload(BaseModel):
    chapter_ids: list[UUID]
    extraction_profile: dict[str, dict[str, str]]  # kind_code → attr_code → action
    model_source: str = "platform_model"
    model_ref: UUID | None = None
    context_filters: dict | None = None
    max_entities_per_kind: int = 30
    # D-RE-WORKER-GRADED-EFFORT: graded reasoning effort (none|low|medium|high). Clamped to the
    # caller's grant ceiling in the core (INV-T11). `thinking_enabled` is the deprecated bool
    # alias (True→medium) kept for back-compat; `reasoning_effort` wins when set.
    reasoning_effort: str = "none"
    thinking_enabled: bool = False
    # Graded reasoning effort (none|low|medium|high). The SSOT once set; the worker
    # honors low/high (not just medium-or-none). `thinking_enabled` stays as the
    # back-compat bool alias (True ⇒ medium) when reasoning_effort is omitted.
    reasoning_effort: str | None = None
    # D-EXTRACTION-BATCH-CONCURRENCY: cap on CONCURRENT LLM calls per chapter (the
    # window×batch fan-out). Omitted/None ⇒ 1 (sequential, the prior behavior). The
    # worker clamps to a hard ceiling; chapters still run sequentially (entity
    # accumulation is per-chapter) — only the batches within a chapter fan out.
    concurrency_level: int | None = Field(default=None, ge=1, le=64)


class CancelJobResponse(BaseModel):
    job_id: str
    status: str


@router.post("/books/{book_id}/extract-glossary", status_code=202)
async def create_extraction_job(
    book_id: UUID,
    payload: CreateExtractionJobPayload,
    user_id: str = Depends(get_current_user),
    # E0-4a edit gate (book grant). Caller-pays: the model below resolves from the
    # CALLER's translation preferences and the worker runs on the caller's key.
    _grant: UUID = Depends(require_book_grant(GrantLevel.EDIT)),
    db: asyncpg.Pool = Depends(get_db),
):
    return await _create_extraction_job_core(db, book_id, UUID(user_id), payload)


async def _create_extraction_job_core(
    db: asyncpg.Pool,
    book_id: UUID,
    uid: UUID,
    payload: CreateExtractionJobPayload,
    *,
    mcp_key_id: str | None = None,
    spend_cap_usd: float | None = None,
) -> dict:
    """Resolve the model + extraction profile, estimate cost, atomically create the
    job (+ chapter-result rows + the 'pending' JobEvent), and publish to the worker
    queue. The single source of truth for the HTTP `create_extraction_job` handler
    AND the `translation.start_extraction` confirm effect (the MCP path) — the caller
    owns the grant/identity check (HTTP via the EDIT dep; confirm via re-authorize +
    chapter-binding). Returns the job-handle dict."""
    # The grant gate already authorized + proved the book exists (a missing book
    # resolves to `none` → 404). Fetch the projection only for source_language
    # (original_language); ownership is no longer decided here.
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                f"{app_settings.book_service_internal_url}/internal/books/{book_id}/projection",
                headers={"X-Internal-Token": app_settings.internal_service_token},
            )
        except httpx.RequestError:
            raise HTTPException(status_code=502, detail={"code": "EXTRACT_BOOK_SERVICE_UNAVAILABLE", "message": "Book service unavailable"})

    if r.status_code == 404:
        raise HTTPException(status_code=404, detail={"code": "EXTRACT_BOOK_NOT_FOUND", "message": "Book not found"})
    if not r.is_success:
        raise HTTPException(status_code=502, detail={"code": "EXTRACT_BOOK_SERVICE_ERROR", "message": "Book service error"})

    projection = r.json()
    source_language = projection.get("original_language", "zh") or "zh"

    # Resolve model — use payload model_ref or fall back to user's translation settings
    model_source = payload.model_source
    model_ref = payload.model_ref
    if not model_ref:
        row = await db.fetchrow(
            "SELECT model_source, model_ref FROM user_translation_preferences WHERE user_id=$1",
            uid,
        )
        if row and row["model_ref"]:
            model_source = row["model_source"]
            model_ref = row["model_ref"]
        else:
            raise HTTPException(
                status_code=422,
                detail={"code": "EXTRACT_NO_MODEL", "message": "No model configured. Set a model in Translation Settings first."},
            )

    # Fetch kinds metadata for cost estimation + worker batching (must succeed).
    profile_data = await fetch_extraction_profile(str(book_id))
    if not profile_data or not profile_data.get("kinds"):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "EXTRACT_PROFILE_UNAVAILABLE",
                "message": "Could not load extraction profile from glossary-service.",
            },
        )
    kinds_metadata = profile_data["kinds"]

    # The MCP path (translation_start_extraction) does NOT supply an extraction_profile —
    # the agent can't reasonably author the full kind→attr→action map, and shouldn't (it's
    # book config, not an agent decision). Derive it from the book's auto-selected ontology
    # (every non-skip attr on each auto-selected kind), i.e. the same profile the FE would
    # have built. The HTTP/FE path sends a user-customized profile (kinds/attrs may be
    # deselected) → respect it as-is. Without this, the worker gets {} → 0 batches → 0
    # entities (the MCP extraction path silently no-ops).
    extraction_profile = payload.extraction_profile
    if not extraction_profile:
        # "default" defers to each attribute's authored merge_strategy
        # (D-EXTRACT-ATTR-MERGE-DEFAULTS) — NOT "fill", which froze every already-filled
        # attribute on re-extraction. The seeded heuristic (append/overwrite/fill) then
        # governs so a recurring entity accumulates new knowledge across chapters.
        extraction_profile = {
            k["code"]: {a["code"]: "default" for a in k.get("attributes", [])}
            for k in kinds_metadata
            if k.get("auto_selected", True) and k.get("attributes")
        }

    # Compute cost estimate
    # Rough estimate: assumes ~8K chars per chapter. Actual sizes would require fetching
    # from book-service. This is intentionally approximate per design §6.7.1 ("estimate, not quote").
    # D-CACHE-PLANNER-WIRING: resolve the REAL model context so the planner-backed quote
    # windows oversized chapters against the SAME budget the executor will use (not the SDK's
    # conservative default, which would over-split every chapter). Best-effort → fallback.
    model_context_window = await get_model_context_window(model_source, str(model_ref) if model_ref else None)

    # D-RE-WORKER-GRADED-EFFORT: resolve the graded reasoning effort, CLAMPED to the caller's
    # grant ceiling (INV-T11 — effort is paid compute; a non-owner must not escalate spend past
    # their grant). The MCP/confirm paths already clamp, so re-clamping here is idempotent for
    # them AND secures the direct HTTP path (whose payload effort is unclamped). `reasoning_effort`
    # wins; `thinking_enabled` is the deprecated bool alias (True→medium).
    effort_raw = (payload.reasoning_effort or "").strip().lower() or ("medium" if payload.thinking_enabled else "none")
    _grant_level = await get_grant_client().resolve_grant(book_id, uid)
    reasoning_effort, _ = clamp_effort_to_grant(effort_raw, int(_grant_level))

    chapters_meta = [{"text_length": 8000}] * len(payload.chapter_ids)
    cost_estimate = estimate_extraction_cost(
        chapters_meta, extraction_profile, kinds_metadata,
        model_context_window=model_context_window,
        reasoning_effort=reasoning_effort,
    )

    context_filters = payload.context_filters or {}

    # P4 — resolve the human model NAME (best-effort) for the 'pending' lifecycle event +
    # a whitelisted params dict for the Jobs GUI. None on any failure (GUI is null-safe).
    model_name = await resolve_model_name(model_source, str(model_ref))
    job_params = {
        "model": model_name,
        "model_ref": str(model_ref),
        "source_language": source_language,
        "max_entities_per_kind": payload.max_entities_per_kind,
        "thinking_enabled": payload.thinking_enabled,
        "reasoning_effort": reasoning_effort,
    }

    # D-EXTRACTION-ADMISSION-CONTROL: cap CONCURRENT extraction jobs per user. P5 fair-scheduling
    # is translation-chapter-only — it does NOT bound extraction fan-out, so without this a user
    # could launch unbounded concurrent jobs (each holds HTTP clients + contends the glossary
    # per-book advisory lock → pool pressure). 0 ⇒ disabled. Checked here so BOTH the HTTP and the
    # MCP-confirm paths (which share this core) are bounded.
    _cap = app_settings.extraction_max_concurrent_jobs_per_user
    if _cap > 0:
        active = await db.fetchval(
            "SELECT count(*) FROM extraction_jobs WHERE owner_user_id=$1 "
            "AND status IN ('pending','running')",
            uid,
        )
        if (active or 0) >= _cap:
            raise HTTPException(
                status_code=429,
                detail={"code": "EXTRACT_TOO_MANY_JOBS",
                        "message": f"You already have {active} extraction job(s) running "
                                   f"(max {_cap}). Wait for one to finish or cancel it."},
            )

    # Insert job + chapter result rows + emit the 'pending' lifecycle event in ONE tx
    # (H1: the JobEvent commits atomically with the row). The chapter-results are a SINGLE
    # bulk INSERT (was an O(N) per-chapter await loop — the create-path latency that froze
    # the wizard, D-JOBS-GLOSSARY-EXTRACT bug #2) and the whole create is now atomic (was
    # non-transactional → a mid-loop failure left a half-created job).
    async with db.acquire() as conn:
        async with conn.transaction():
            job_row = await conn.fetchrow(
                """
                INSERT INTO extraction_jobs
                  (book_id, owner_user_id, status, source_language, model_source, model_ref,
                   extraction_profile, context_filters, chapter_ids, total_chapters, cost_estimate,
                   reasoning_effort, mcp_key_id, spend_cap_usd)
                VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                RETURNING *
                """,
                book_id, uid, source_language, model_source, model_ref,
                json.dumps(extraction_profile),
                json.dumps(context_filters),
                payload.chapter_ids,
                len(payload.chapter_ids),
                json.dumps(cost_estimate),
                reasoning_effort,
                mcp_key_id, spend_cap_usd,
            )
            job_id = job_row["job_id"]

            await conn.execute(
                """INSERT INTO extraction_chapter_results (job_id, chapter_id, book_id, status)
                   SELECT $1, c, $2, 'pending' FROM unnest($3::uuid[]) AS c""",
                job_id, book_id, payload.chapter_ids,
            )

            await emit_job_event(
                conn, service=_JOB_SERVICE, job_id=str(job_id),
                owner_user_id=str(uid), kind=_JOB_KIND, status="pending",
                model=model_name, params=job_params,
            )

    # Publish job to broker
    await publish("extraction.job", {
        "job_id": str(job_id),
        "user_id": str(uid),
        "book_id": str(book_id),
        "chapter_ids": [str(c) for c in payload.chapter_ids],
        "extraction_profile": extraction_profile,
        "kinds_metadata": kinds_metadata,
        "context_filters": context_filters,
        "source_language": source_language,
        "model_source": model_source,
        "model_ref": str(model_ref),
        "max_entities_per_kind": payload.max_entities_per_kind,
        "thinking_enabled": payload.thinking_enabled,
        "reasoning_effort": reasoning_effort,
        # D-EXTRACTION-BATCH-CONCURRENCY: per-chapter LLM-call fan-out cap (None ⇒ 1).
        "concurrency": payload.concurrency_level,
        # D-PMCP-WORKER-CARRIER: ride the public-MCP key + cap so the extraction
        # worker re-sets the attribution contextvar before each provider call.
        "mcp_key_id": mcp_key_id,
        "spend_cap_usd": spend_cap_usd,
    })

    return {
        "job_id": str(job_id),
        "status": "pending",
        "job_type": "extract_glossary",
        "total_chapters": len(payload.chapter_ids),
        "cost_estimate": cost_estimate,
    }


@router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_extraction_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    """Cancel a running extraction job. E0-4a edit gate (job→book grant)."""
    row = await db.fetchrow(
        "SELECT status, book_id, owner_user_id FROM extraction_jobs WHERE job_id=$1", job_id
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "EXTRACT_JOB_NOT_FOUND", "message": "Job not found"})
    # Non-grantee → 404 (uniform with missing job, anti-oracle).
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.EDIT)

    if row["status"] not in ("pending", "running"):
        raise HTTPException(status_code=409, detail={"code": "EXTRACT_JOB_NOT_CANCELLABLE", "message": f"Job is {row['status']}"})

    # UPDATE → 'cancelling' + emit the transition in one tx (H1). The worker settles it to
    # 'cancelled' (claim-time or mid-loop) and emits the terminal. Owner from the row.
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE extraction_jobs SET status='cancelling' WHERE job_id=$1", job_id
            )
            await emit_job_event(
                conn, service=_JOB_SERVICE, job_id=str(job_id),
                owner_user_id=str(row["owner_user_id"]), kind=_JOB_KIND, status="cancelling",
            )

    return CancelJobResponse(job_id=str(job_id), status="cancelling")


@router.get("/jobs/{job_id}")
async def get_extraction_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get extraction job status with chapter results. E0-4a view gate (job→book)."""
    row = await db.fetchrow("SELECT * FROM extraction_jobs WHERE job_id=$1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "EXTRACT_JOB_NOT_FOUND", "message": "Job not found"})
    # Non-grantee → 404 (uniform with missing job, anti-oracle).
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.VIEW)

    chapter_rows = await db.fetch(
        "SELECT * FROM extraction_chapter_results WHERE job_id=$1 ORDER BY created_at",
        job_id,
    )

    import json as _json
    return {
        "job_id": str(row["job_id"]),
        "book_id": str(row["book_id"]),
        "status": row["status"],
        "job_type": "extract_glossary",
        "source_language": row["source_language"],
        "total_chapters": row["total_chapters"],
        "completed_chapters": row["completed_chapters"],
        "failed_chapters": row["failed_chapters"],
        "entities_created": row["entities_created"],
        "entities_updated": row["entities_updated"],
        "entities_skipped": row["entities_skipped"],
        "total_input_tokens": row["total_input_tokens"],
        "total_output_tokens": row["total_output_tokens"],
        "cost_estimate": json.loads(row["cost_estimate"]) if row["cost_estimate"] else None,
        "error_message": row["error_message"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "created_at": row["created_at"].isoformat(),
        "chapters": [
            {
                "chapter_id": str(cr["chapter_id"]),
                "status": cr["status"],
                "entities_found": cr["entities_found"],
                "input_tokens": cr["input_tokens"],
                "output_tokens": cr["output_tokens"],
                "error_message": cr["error_message"],
            }
            for cr in chapter_rows
        ],
    }
