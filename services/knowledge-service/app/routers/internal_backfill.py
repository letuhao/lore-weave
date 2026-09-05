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
from app.db.graph import graph_session
from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/projects",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


#: The statuses the one-active-job partial index covers, kept as ONE tuple so this guard and
#: the index cannot drift apart. Spelled the same way `extraction_jobs.list_active` does.
_ACTIVE_JOB_STATUSES = ("pending", "running", "paused")


async def _refuse_if_extraction_active(project_id: UUID) -> None:
    """409 while an extraction job holds this project.

    🔴 **WHY (L3, 2026-08-30).** `event_order` has exactly TWO writers:
    `pass2_writer` (under an extraction job) and `run_orders_backfill` (this endpoint).
    Two *extractions* cannot race — `idx_extraction_jobs_one_active_per_project` is a UNIQUE
    partial index over `(project_id) WHERE status IN (pending, running, paused)`, so the
    second INSERT fails and the endpoint answers 409. Verified live, not read: the index is
    present on `loreweave_knowledge`.

    **This endpoint was outside that invariant entirely.** It checked that the project exists
    and that a graph is configured, then renumbered `event_order` across the whole project.
    And the two writers do not merely overlap, they DISAGREE: the backfill assigns
    `base + idx` over `sorted(event_ids)` — dense from 0 — while the writer continues from the
    band's current maximum. Run together they produce two numberings of one chapter, and the
    reading axis is whatever interleaving won.

    Nothing here is hypothetical about the damage: `event_order` is the spoiler cutoff, the
    timeline, `list_events_in_order`, and the causal pass's forward-only filter. A duplicate
    there is not a crash; it is a stable sort silently falling back to row order.

    The guard is a READ, so it is subject to the same TOCTOU as any check-then-act — a job
    could start in the window. That is a much narrower race than an unguarded backfill, and
    the index remains the thing that makes the extraction side unambiguous; this closes the
    case where a backfill is fired at a project that is visibly busy.
    """
    row = await get_knowledge_pool().fetchrow(
        "SELECT job_id FROM extraction_jobs WHERE project_id = $1 "
        "AND status = ANY($2::text[]) LIMIT 1",
        project_id, list(_ACTIVE_JOB_STATUSES),
    )
    if row is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"extraction job {row['job_id']} is active on this project; a backfill "
                f"would renumber event_order underneath it"
            ),
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
    # AFTER the 404: a caller naming a project that does not exist should hear that, not
    # a 409 about a job it could not have started.
    await _refuse_if_extraction_active(project_id)
    user_id = row["user_id"]

    if not settings.neo4j_uri:
        # Track 1 (no graph) — nothing to backfill; clean no-op.
        return {
            "project_id": str(project_id),
            "skipped": "neo4j_unavailable",
        }

    async with graph_session() as session:
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

    async with graph_session() as session:
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
    from app.extraction.passage_backfill import backfill_project_passages

    result = await backfill_project_passages(
        project_id=project_id, user_id=row["user_id"], book_id=row["book_id"],
        embedding_model=row["embedding_model"], embedding_dim=row["embedding_dimension"],
        book_client=get_book_client(), embedding_client=get_embedding_client(),
    )
    if result.get("error") == "book_service_unavailable":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="book-service unavailable listing chapters",
        )
    return {"project_id": str(project_id), **result}


@router.post("/{project_id}/backfill-glossary-passages")
async def backfill_glossary_passages(project_id: UUID) -> dict:
    """Index every glossary entity of the project's book as a `:Passage`.

    `source_type='glossary'` was a declared member of KNOWN_SOURCE_TYPES with NO
    producer, so authored lore was never semantically retrievable — the composition
    lore lens could only ever find chapter passages, i.e. prose already written. A book
    whose glossary was built BEFORE chapter 1 therefore had an empty lore lens.

    This backfills what the event path now maintains going forward. Idempotent: each
    entity's passage carries a content hash, so re-running re-embeds only what changed.

    Returns a per-outcome tally rather than a bare "ok" — `no_embedding_model: 14` is
    the answer the caller needs to act on, and reporting it as success is precisely the
    silent no-op this endpoint exists to end.
    """
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

    from app.clients.glossary_client import get_glossary_client
    from app.events.handlers import index_glossary_entity_passage

    # Enumerate via entity-ids, NOT known-entities: the latter is the extraction anchor
    # list (frequency-filtered, and it reads the display name from the attribute coded
    # `name`, which `terminology` does not have). Live-measured, it silently skipped 2 of
    # 14 entities while reporting a complete-looking count.
    listed = await get_glossary_client().list_entity_ids(row["book_id"])
    if listed is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="glossary-service unavailable",
        )
    entities, truncated = listed

    outcomes: dict[str, int] = {}
    for ent in entities:
        raw_id = ent.get("entity_id")
        if not raw_id:
            continue
        try:
            entity_uuid = UUID(str(raw_id))
        except ValueError:
            continue
        outcome = await index_glossary_entity_passage(
            book_id=row["book_id"], user_id=row["user_id"],
            project_id=project_id, glossary_entity_id=entity_uuid,
            embedding_model=row["embedding_model"],
            embedding_dim=row["embedding_dimension"],
        )
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    logger.info(
        "glossary passage backfill project=%s entities=%d outcomes=%s",
        project_id, len(entities), outcomes,
    )
    return {
        "project_id": str(project_id),
        "entities_seen": len(entities),
        "outcomes": outcomes,
        # Never a silent cap — the caller must know the walk stopped early.
        "truncated": truncated,
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
    async with graph_session() as session:
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
