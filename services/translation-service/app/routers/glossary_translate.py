"""Glossary batch translation job API."""
from __future__ import annotations

import json
from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..broker import publish
from ..config import settings as app_settings
from ..deps import get_current_user, get_db
from ..grant_deps import GrantLevel, authorize_book, get_grant_client_dep, require_book_grant
from ..workers.glossary_client import fetch_translation_candidates
from ..workers.glossary_translate_prompt import estimate_glossary_translate_cost

router = APIRouter(prefix="/v1/glossary-translate", tags=["glossary-translate-jobs"])


class CreateGlossaryTranslatePayload(BaseModel):
    target_language: str
    model_source: str = "platform_model"
    model_ref: UUID | None = None
    overwrite_mode: str = Field(default="missing_only", pattern="^(missing_only|refresh_machine)$")
    entity_ids: list[UUID] | None = None
    kind_codes: list[str] = Field(default_factory=list)
    entity_status: str = "all"
    thinking_enabled: bool = False


class CancelJobResponse(BaseModel):
    job_id: str
    status: str


@router.post("/books/{book_id}/translate", status_code=202)
async def create_glossary_translate_job(
    book_id: UUID,
    payload: CreateGlossaryTranslatePayload,
    user_id: str = Depends(get_current_user),
    _grant: UUID = Depends(require_book_grant(GrantLevel.EDIT)),
    db: asyncpg.Pool = Depends(get_db),
):
    uid = UUID(user_id)

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                f"{app_settings.book_service_internal_url}/internal/books/{book_id}/projection",
                headers={"X-Internal-Token": app_settings.internal_service_token},
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=502,
                detail={"code": "GT_BOOK_SERVICE_UNAVAILABLE", "message": "Book service unavailable"},
            )

    if r.status_code == 404:
        raise HTTPException(status_code=404, detail={"code": "GT_BOOK_NOT_FOUND", "message": "Book not found"})
    if not r.is_success:
        raise HTTPException(status_code=502, detail={"code": "GT_BOOK_SERVICE_ERROR", "message": "Book service error"})

    projection = r.json()
    source_language = projection.get("original_language", "zh") or "zh"

    if payload.target_language.strip() == source_language.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "GT_SAME_LANGUAGE",
                "message": "Target language must differ from the book source language.",
            },
        )

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
                detail={"code": "GT_NO_MODEL", "message": "No model configured. Set a model in Translation Settings first."},
            )

    entity_id_strs = [str(e) for e in payload.entity_ids] if payload.entity_ids else None
    candidates = await fetch_translation_candidates(
        str(book_id),
        payload.target_language,
        overwrite_mode=payload.overwrite_mode,
        limit=1,
        offset=0,
        entity_ids=entity_id_strs,
    )
    entity_count = candidates.get("total", 0) if candidates else 0
    attr_count = 0
    if candidates:
        preview = await fetch_translation_candidates(
            str(book_id),
            payload.target_language,
            overwrite_mode=payload.overwrite_mode,
            limit=min(entity_count, 50) or 1,
            offset=0,
            entity_ids=entity_id_strs,
        )
        if preview:
            attr_count = sum(len(e.get("attributes") or []) for e in preview.get("items") or [])

    cost_estimate = estimate_glossary_translate_cost(entity_count, max(attr_count, entity_count))

    metadata = {
        "entity_ids": [str(e) for e in payload.entity_ids] if payload.entity_ids else None,
        "kind_codes": payload.kind_codes,
        "entity_status": payload.entity_status,
        "thinking_enabled": payload.thinking_enabled,
    }

    job_row = await db.fetchrow(
        """
        INSERT INTO glossary_translation_jobs
          (book_id, owner_user_id, status, source_language, target_language,
           model_source, model_ref, overwrite_mode, metadata, total_entities, cost_estimate)
        VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING job_id
        """,
        book_id, uid, source_language, payload.target_language,
        model_source, model_ref, payload.overwrite_mode,
        json.dumps(metadata), entity_count, json.dumps(cost_estimate),
    )
    job_id = job_row["job_id"]

    await publish("glossary_translate.job", {
        "job_id": str(job_id),
        "user_id": user_id,
        "book_id": str(book_id),
        "target_language": payload.target_language,
        "source_language": source_language,
        "model_source": model_source,
        "model_ref": str(model_ref),
        "overwrite_mode": payload.overwrite_mode,
        "thinking_enabled": payload.thinking_enabled,
        "metadata": metadata,
    })

    return {
        "job_id": str(job_id),
        "status": "pending",
        "job_type": "translate_glossary",
        "total_entities": entity_count,
        "cost_estimate": cost_estimate,
    }


@router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_glossary_translate_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT status, book_id FROM glossary_translation_jobs WHERE job_id=$1", job_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "GT_JOB_NOT_FOUND", "message": "Job not found"})
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.EDIT)

    if row["status"] not in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail={"code": "GT_JOB_NOT_CANCELLABLE", "message": f"Job is {row['status']}"},
        )

    await db.execute(
        "UPDATE glossary_translation_jobs SET status='cancelling' WHERE job_id=$1", job_id,
    )
    return CancelJobResponse(job_id=str(job_id), status="cancelling")


@router.get("/jobs/{job_id}")
async def get_glossary_translate_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow("SELECT * FROM glossary_translation_jobs WHERE job_id=$1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "GT_JOB_NOT_FOUND", "message": "Job not found"})
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.VIEW)

    return {
        "job_id": str(row["job_id"]),
        "book_id": str(row["book_id"]),
        "status": row["status"],
        "job_type": "translate_glossary",
        "source_language": row["source_language"],
        "target_language": row["target_language"],
        "overwrite_mode": row["overwrite_mode"],
        "total_entities": row["total_entities"],
        "completed_entities": row["completed_entities"],
        "failed_entities": row["failed_entities"],
        "attrs_translated": row["attrs_translated"],
        "attrs_skipped": row["attrs_skipped"],
        "total_input_tokens": row["total_input_tokens"],
        "total_output_tokens": row["total_output_tokens"],
        "cost_estimate": json.loads(row["cost_estimate"]) if row["cost_estimate"] else None,
        "error_message": row["error_message"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "created_at": row["created_at"].isoformat(),
    }
