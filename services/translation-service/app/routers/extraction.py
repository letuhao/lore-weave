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
from pydantic import BaseModel

from ..broker import publish, publish_event
from ..config import settings as app_settings
from ..deps import get_current_user, get_db
from ..workers.extraction_prompt import estimate_extraction_cost
from ..workers.glossary_client import fetch_extraction_profile

router = APIRouter(prefix="/v1/extraction", tags=["extraction-jobs"])


class CreateExtractionJobPayload(BaseModel):
    chapter_ids: list[UUID]
    extraction_profile: dict[str, dict[str, str]]  # kind_code → attr_code → action
    model_source: str = "platform_model"
    model_ref: UUID | None = None
    context_filters: dict | None = None
    max_entities_per_kind: int = 30


class CancelJobResponse(BaseModel):
    job_id: str
    status: str


@router.post("/books/{book_id}/extract-glossary", status_code=202)
async def create_extraction_job(
    book_id: UUID,
    payload: CreateExtractionJobPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    uid = UUID(user_id)

    # Verify book ownership via book-service
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
    if str(projection.get("owner_user_id")) != user_id:
        raise HTTPException(status_code=403, detail={"code": "EXTRACT_FORBIDDEN", "message": "Not your book"})

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

    # Fetch kinds metadata for cost estimation
    profile_data = await fetch_extraction_profile(str(book_id))
    kinds_metadata = profile_data.get("kinds", []) if profile_data else []

    # Compute cost estimate
    # Rough estimate: assumes ~8K chars per chapter. Actual sizes would require fetching
    # from book-service. This is intentionally approximate per design §6.7.1 ("estimate, not quote").
    chapters_meta = [{"text_length": 8000}] * len(payload.chapter_ids)
    cost_estimate = estimate_extraction_cost(
        chapters_meta, payload.extraction_profile, kinds_metadata
    )

    context_filters = payload.context_filters or {}

    # Insert job + chapter result rows
    job_row = await db.fetchrow(
        """
        INSERT INTO extraction_jobs
          (book_id, owner_user_id, status, source_language, model_source, model_ref,
           extraction_profile, context_filters, chapter_ids, total_chapters, cost_estimate)
        VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING *
        """,
        book_id, uid, source_language, model_source, model_ref,
        json.dumps(payload.extraction_profile),
        json.dumps(context_filters),
        payload.chapter_ids,
        len(payload.chapter_ids),
        json.dumps(cost_estimate),
    )
    job_id = job_row["job_id"]

    for chapter_id in payload.chapter_ids:
        await db.execute(
            """INSERT INTO extraction_chapter_results (job_id, chapter_id, book_id, status)
               VALUES ($1, $2, $3, 'pending')""",
            job_id, chapter_id, book_id,
        )

    # Publish job to broker
    await publish("extraction.job", {
        "job_id": str(job_id),
        "user_id": user_id,
        "book_id": str(book_id),
        "chapter_ids": [str(c) for c in payload.chapter_ids],
        "extraction_profile": payload.extraction_profile,
        "kinds_metadata": kinds_metadata,
        "context_filters": context_filters,
        "source_language": source_language,
        "model_source": model_source,
        "model_ref": str(model_ref),
        "max_entities_per_kind": payload.max_entities_per_kind,
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
    db: asyncpg.Pool = Depends(get_db),
):
    """Cancel a running extraction job. Ownership check per design S3."""
    uid = UUID(user_id)
    row = await db.fetchrow(
        "SELECT status, owner_user_id FROM extraction_jobs WHERE job_id=$1", job_id
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "EXTRACT_JOB_NOT_FOUND", "message": "Job not found"})

    if row["owner_user_id"] != uid:
        raise HTTPException(status_code=403, detail={"code": "EXTRACT_FORBIDDEN", "message": "Not your job"})

    if row["status"] not in ("pending", "running"):
        raise HTTPException(status_code=409, detail={"code": "EXTRACT_JOB_NOT_CANCELLABLE", "message": f"Job is {row['status']}"})

    await db.execute(
        "UPDATE extraction_jobs SET status='cancelling' WHERE job_id=$1", job_id
    )

    return CancelJobResponse(job_id=str(job_id), status="cancelling")


@router.get("/jobs/{job_id}")
async def get_extraction_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get extraction job status with chapter results."""
    uid = UUID(user_id)
    row = await db.fetchrow("SELECT * FROM extraction_jobs WHERE job_id=$1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "EXTRACT_JOB_NOT_FOUND", "message": "Job not found"})

    if row["owner_user_id"] != uid:
        raise HTTPException(status_code=403, detail={"code": "EXTRACT_FORBIDDEN", "message": "Not your job"})

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
