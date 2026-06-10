"""CM4 — internal per-project backfill endpoint.

POST /internal/projects/{project_id}/backfill-orders

Stamps the dual-order axes (event_order, chronological_order, passage
chapter_index) for an EXISTING project whose events/passages predate CM4
(they were written with NULL orders → the timeline filters were no-ops).
Idempotent; safe to re-run. Operator/admin-triggered per project.

Authentication: X-Internal-Token (service-to-service).
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.book_client import get_book_client
from app.clients.llm_client import get_llm_client
from app.config import settings
from app.db.migrations.backfill_orders import run_orders_backfill
from app.db.migrations.backfill_status import (
    make_llm_classify_fn,
    run_status_backfill,
)
from app.db.neo4j import neo4j_session
from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/projects",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/{project_id}/backfill-orders")
async def backfill_orders(project_id: UUID) -> dict:
    """Backfill event_order / chronological_order / passage chapter_index
    for one project. Resolves the owning user from knowledge_projects."""
    row = await get_knowledge_pool().fetchrow(
        "SELECT user_id FROM knowledge_projects WHERE project_id = $1 LIMIT 1",
        project_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found",
        )
    user_id = row["user_id"]

    if not settings.neo4j_uri:
        # Track 1 (no graph) — nothing to backfill; clean no-op.
        return {
            "project_id": str(project_id),
            "skipped": "neo4j_unavailable",
        }

    async with neo4j_session() as session:
        result = await run_orders_backfill(
            session,
            get_book_client(),
            user_id=str(user_id),
            project_id=str(project_id),
        )

    return {
        "project_id": str(project_id),
        "events_ordered": result.events_ordered,
        "events_skipped_no_sort": result.events_skipped_no_sort,
        "passages_indexed": result.passages_indexed,
        "chrono_ranked": result.chrono_ranked,
    }


class BackfillStatusRequest(BaseModel):
    """A2-S1b-2 — the model used to classify existing event summaries into
    coarse status. Mirrors the extraction model-selection shape."""

    model_source: Literal["user_model", "platform_model"] = "user_model"
    model_ref: str = Field(min_length=1, max_length=200)
    batch_size: int = Field(default=25, ge=1, le=100)


@router.post("/{project_id}/backfill-status")
async def backfill_status(project_id: UUID, body: BackfillStatusRequest) -> dict:
    """A2-S1b-2 — one-time entity-status backfill: classify existing
    positioned events into coarse active/gone records. Idempotent;
    project-scoped; skips null-`event_order` events (MED#2). Resolves the
    owning user from knowledge_projects."""
    row = await get_knowledge_pool().fetchrow(
        "SELECT user_id FROM knowledge_projects WHERE project_id = $1 LIMIT 1",
        project_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found",
        )
    user_id = row["user_id"]

    if not settings.neo4j_uri:
        return {"project_id": str(project_id), "skipped": "neo4j_unavailable"}

    classify_fn = make_llm_classify_fn(
        get_llm_client(),
        user_id=str(user_id),
        model_source=body.model_source,
        model_ref=body.model_ref,
    )
    async with neo4j_session() as session:
        result = await run_status_backfill(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            classify_fn=classify_fn,
            batch_size=body.batch_size,
        )

    return {
        "project_id": str(project_id),
        "events_scanned": result.events_scanned,
        "events_skipped_no_order": result.events_skipped_no_order,
        "statuses_written": result.statuses_written,
        "skipped_unresolved_entity": result.skipped_unresolved_entity,
        "skipped_no_source": result.skipped_no_source,
        "skipped_bad_status": result.skipped_bad_status,
        "skipped_not_participant": result.skipped_not_participant,
    }
