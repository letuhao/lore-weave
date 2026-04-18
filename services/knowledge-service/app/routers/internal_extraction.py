"""K16.6a — Internal extraction endpoint for worker-ai.

POST /internal/extraction/extract-item

Runs the Pass 2 LLM extraction pipeline on a single item (chapter or
chat turn) and writes results to Neo4j. Called by worker-ai as part of
the extraction job loop.

Authentication: X-Internal-Token (service-to-service).
Trusts the caller's user_id — worker-ai reads it from extraction_jobs.
"""

from __future__ import annotations

import logging
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.glossary_client import get_glossary_client
from app.clients.provider_client import (
    ProviderAuthError,
    ProviderDecodeError,
    ProviderError,
    ProviderInvalidRequest,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUpstreamError,
    get_provider_client,
)
from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.pool import get_knowledge_pool
from app.extraction.anchor_loader import Anchor, load_glossary_anchors
from app.extraction.pass2_orchestrator import (
    extract_pass2_chapter,
    extract_pass2_chat_turn,
)
from app.middleware.internal_auth import require_internal_token

# Errors that the worker should retry (transient upstream issues).
_RETRYABLE_ERRORS = (ProviderTimeout, ProviderRateLimited, ProviderUpstreamError)
# Errors that are permanent — retrying won't help.
_PERMANENT_ERRORS = (ProviderAuthError, ProviderModelNotFound, ProviderInvalidRequest, ProviderDecodeError)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/extraction",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


# ── Request / Response models ────────────────────────────────────────

ItemType = Literal["chapter", "chat_turn"]


class ExtractItemRequest(BaseModel):
    user_id: UUID
    project_id: UUID | None = None
    item_type: ItemType
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=200)
    job_id: UUID

    # Model to use for LLM extraction
    model_source: Literal["user_model", "platform_model"] = "user_model"
    model_ref: str = Field(min_length=1, max_length=200)

    # Text content — exactly one of these should be populated
    chapter_text: str | None = None
    user_message: str | None = None
    assistant_message: str | None = None

    # Previously known entities for context enrichment
    known_entities: list[str] = Field(default_factory=list)


class ExtractItemResponse(BaseModel):
    source_id: str
    entities_merged: int = 0
    relations_created: int = 0
    events_merged: int = 0
    facts_merged: int = 0
    evidence_edges: int = 0
    duration_seconds: float = 0.0


# ── Helpers ──────────────────────────────────────────────────────────


async def _load_anchors_for_extraction(
    *, user_id: UUID, project_id: UUID | None,
) -> list[Anchor]:
    """K13.0 Pass 0: pre-load glossary anchors before Pass 2 runs.

    Returns an empty list (extraction proceeds without anchor bias) if:
      - project_id is None (chat-only, no book)
      - no knowledge_projects row matches (user_id, project_id)
      - project has no book_id linked (Mode 1 project)
      - glossary_client.list_entities fails (circuit open, 5xx, …)
      - any Neo4j hiccup during the upsert loop

    Per-entry failures inside load_glossary_anchors are already
    isolated there; this helper only handles the outer envelope.
    """
    if project_id is None:
        return []
    try:
        async with get_knowledge_pool().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT book_id FROM knowledge_projects "
                "WHERE project_id = $1 AND user_id = $2",
                project_id, user_id,
            )
        book_id = row["book_id"] if row else None
        if book_id is None:
            return []
        async with neo4j_session() as anchor_session:
            return await load_glossary_anchors(
                anchor_session,
                get_glossary_client(),
                user_id=str(user_id),
                project_id=str(project_id),
                book_id=book_id,
            )
    except Exception:
        logger.warning(
            "K13.0: anchor pre-load failed for project=%s — "
            "extraction will run without anchor bias",
            project_id, exc_info=True,
        )
        return []


# ── Endpoint ─────────────────────────────────────────────────────────


@router.post(
    "/extract-item",
    response_model=ExtractItemResponse,
    status_code=status.HTTP_200_OK,
)
async def extract_item(body: ExtractItemRequest) -> ExtractItemResponse:
    """Run Pass 2 extraction on a single item and write to Neo4j.

    Called by worker-ai for each item in an extraction job. The worker
    handles try_spend, advance_cursor, and pause/cancel — this endpoint
    is purely the extraction + write step.
    """
    if not settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j not configured — extraction requires NEO4J_URI",
        )

    started = time.perf_counter()
    provider_client = get_provider_client()

    # K13.0 — pre-load glossary anchors. Degrades to [] on any failure
    # so extraction still runs (without duplicate-reduction benefit).
    anchors = await _load_anchors_for_extraction(
        user_id=body.user_id, project_id=body.project_id,
    )

    try:
        async with neo4j_session() as session:
            if body.item_type == "chapter":
                if not body.chapter_text:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="chapter_text required for item_type=chapter",
                    )
                result = await extract_pass2_chapter(
                    session,
                    user_id=str(body.user_id),
                    project_id=str(body.project_id) if body.project_id else None,
                    source_type=body.source_type,
                    source_id=body.source_id,
                    job_id=str(body.job_id),
                    chapter_text=body.chapter_text,
                    known_entities=body.known_entities,
                    model_source=body.model_source,
                    model_ref=body.model_ref,
                    client=provider_client,
                    anchors=anchors,
                )
            else:  # "chat_turn" — Pydantic Literal rejects other values at 422
                if not body.user_message and not body.assistant_message:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="user_message or assistant_message required for item_type=chat_turn",
                    )
                result = await extract_pass2_chat_turn(
                    session,
                    user_id=str(body.user_id),
                    project_id=str(body.project_id) if body.project_id else None,
                    source_type=body.source_type,
                    source_id=body.source_id,
                    job_id=str(body.job_id),
                    user_message=body.user_message,
                    assistant_message=body.assistant_message,
                    known_entities=body.known_entities,
                    model_source=body.model_source,
                    model_ref=body.model_ref,
                    client=provider_client,
                    anchors=anchors,
                )
    except HTTPException:
        raise  # re-raise validation errors (422)
    except _RETRYABLE_ERRORS as exc:
        logger.warning(
            "K16.6a: retryable extraction error source_id=%s: %s",
            body.source_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"retryable": True, "error": str(exc)},
        )
    except _PERMANENT_ERRORS as exc:
        logger.error(
            "K16.6a: permanent extraction error source_id=%s: %s",
            body.source_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"retryable": False, "error": str(exc)},
        )
    except ProviderError as exc:
        # Catch-all for any future ProviderError subclass
        logger.error(
            "K16.6a: unknown provider error source_id=%s: %s",
            body.source_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"retryable": True, "error": str(exc)},
        )

    elapsed = time.perf_counter() - started
    logger.info(
        "K16.6a: extract-item done source_id=%s type=%s "
        "entities=%d relations=%d events=%d facts=%d in %.1fs",
        body.source_id, body.item_type,
        result.entities_merged, result.relations_created,
        result.events_merged, result.facts_merged, elapsed,
    )

    return ExtractItemResponse(
        source_id=result.source_id,
        entities_merged=result.entities_merged,
        relations_created=result.relations_created,
        events_merged=result.events_merged,
        facts_merged=result.facts_merged,
        evidence_edges=result.evidence_edges,
        duration_seconds=round(elapsed, 2),
    )
