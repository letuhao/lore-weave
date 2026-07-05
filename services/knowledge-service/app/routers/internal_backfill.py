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
from app.db.migrations.backfill_participant_anchors import (
    run_participant_anchor_backfill,
)
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


@router.post("/{project_id}/backfill-participant-anchors")
async def backfill_participant_anchors(project_id: UUID) -> dict:
    """D-KG-TL-PARTICIPANT-ANCHOR — resolve + stamp ``participant_entity_ids`` on
    a project's existing events so the timeline localizer joins participant names
    by stored glossary id instead of re-resolving at read time. Idempotent;
    project-scoped. Resolves the owning user from knowledge_projects."""
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
        return {"project_id": str(project_id), "skipped": "neo4j_unavailable"}

    async with neo4j_session() as session:
        result = await run_participant_anchor_backfill(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
        )

    return {
        "project_id": str(project_id),
        "events_scanned": result.events_scanned,
        "events_anchored": result.events_anchored,
        "anchors_resolved": result.anchors_resolved,
    }


@router.post("/{project_id}/backfill-passages")
async def backfill_passages(project_id: UUID) -> dict:
    """D-KG-PASSAGES-NOT-INGESTED — (re)ingest L3 ``:Passage`` nodes for a project's
    already-published chapters, so semantic memory/story search has chapter-body data.

    Publish-time ingestion (CM3c, ``chapter.published``) is SKIPPED when the project
    has no embedding config at publish time — e.g. the KG project was created/linked
    to the book AFTER its chapters were published — leaving the semantic index empty
    while lexical search still works. This backfills passages from each chapter's
    pinned published revision. Idempotent (re-ingest deletes + re-upserts per chapter);
    project-scoped; admin/operator-triggered. Resolves user + embedding config +
    book from ``knowledge_projects``."""
    row = await get_knowledge_pool().fetchrow(
        "SELECT user_id, book_id, embedding_model, embedding_dimension "
        "FROM knowledge_projects WHERE project_id = $1 LIMIT 1",
        project_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found",
        )
    if not settings.neo4j_uri:
        return {"project_id": str(project_id), "skipped": "neo4j_unavailable"}
    if row["book_id"] is None:
        return {"project_id": str(project_id), "skipped": "no_linked_book"}
    if not row["embedding_model"] or not row["embedding_dimension"]:
        return {"project_id": str(project_id), "skipped": "no_embedding_config"}

    # Heavy deps — inline import (mirrors the CM3c publish handler).
    from app.clients.embedding_client import get_embedding_client
    from app.extraction.passage_ingester import ingest_chapter_passages

    book_client = get_book_client()
    chapters = await book_client.list_chapters(
        row["book_id"], editorial_status="published",
    )
    if chapters is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="book-service unavailable listing chapters",
        )

    embedding_client = get_embedding_client()
    ingested = passages = failed = 0
    for ch in chapters:
        rev = ch.get("published_revision_id")
        cid = ch.get("chapter_id")
        if not rev or not cid:
            continue  # a published row missing its pinned revision — skip, count nothing
        try:
            async with neo4j_session() as session:
                res = await ingest_chapter_passages(
                    session, book_client, embedding_client,
                    user_id=row["user_id"], project_id=project_id,
                    book_id=row["book_id"], chapter_id=UUID(cid),
                    chapter_index=ch.get("sort_order"),
                    embedding_model=row["embedding_model"],
                    embedding_dim=row["embedding_dimension"],
                    revision_id=UUID(rev),
                    # A transient revision-fetch miss must not wipe existing canon.
                    delete_stale_on_missing=False,
                )
            ingested += 1
            passages += res.chunks_created
        except Exception:
            failed += 1
            logger.warning(
                "backfill-passages: chapter=%s project=%s failed — continuing",
                cid, project_id, exc_info=True,
            )

    return {
        "project_id": str(project_id),
        "chapters_ingested": ingested,
        "passages_created": passages,
        "chapters_failed": failed,
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
