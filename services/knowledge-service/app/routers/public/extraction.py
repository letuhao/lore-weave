"""K16.2 — Extraction lifecycle endpoints under /v1/knowledge/projects/{id}/extraction.

K16.2 ships the cost estimation endpoint. K16.3–K16.10 will add
start/pause/resume/cancel/delete/rebuild endpoints to the same router.

Authentication: JWT via router-level + per-route dependency (same
pattern as projects.py — see the double-dependency note there).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient
from app.clients.glossary_client import GlossaryClient
from app.db.repositories.extraction_pending import ExtractionPendingRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_book_client,
    get_extraction_pending_repo,
    get_glossary_client,
    get_projects_repo,
)
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge/projects",
    tags=["extraction"],
    dependencies=[Depends(get_current_user)],
)

# ── Token-per-item estimates (KSA §5.5) ─────────────────────────────
# Prompt + response tokens for a single extraction pass. These are
# conservative upper-bound estimates for cost preview. The actual
# job uses atomic try_spend with real token counts.
_TOKENS_PER_CHAPTER = 2000
_TOKENS_PER_CHAT_TURN = 800
_TOKENS_PER_GLOSSARY_ENTITY = 300

# Rough per-token cost for preview. This is a placeholder until
# provider-registry exposes model pricing (D-K16.2-01).
_DEFAULT_COST_PER_TOKEN = Decimal("0.000002")  # ~$2/M tokens

# Seconds per item estimate for duration preview.
_SECONDS_PER_ITEM = 2


# ── Request / response models ───────────────────────────────────────

JobScope = Literal["chapters", "chat", "glossary_sync", "all"]


class EstimateRequest(BaseModel):
    scope: JobScope
    scope_range: dict | None = None
    llm_model: str = Field(min_length=1, max_length=200)


class EstimateItemCounts(BaseModel):
    chapters: int = 0
    chat_turns: int = 0
    glossary_entities: int = 0


class EstimateResponse(BaseModel):
    items_total: int
    items: EstimateItemCounts
    estimated_tokens: int
    estimated_cost_usd_low: Decimal
    estimated_cost_usd_high: Decimal
    estimated_duration_seconds: int


# ── Endpoint ─────────────────────────────────────────────────────────


@router.post(
    "/{project_id}/extraction/estimate",
    response_model=EstimateResponse,
    status_code=status.HTTP_200_OK,
)
async def estimate_extraction_cost(
    project_id: UUID,
    body: EstimateRequest,
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    pending_repo: ExtractionPendingRepo = Depends(get_extraction_pending_repo),
    book_client: BookClient = Depends(get_book_client),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
) -> EstimateResponse:
    """Preview cost and item counts for a proposed extraction job.

    Does NOT create a job or spend any budget. The frontend shows this
    in the "Build Knowledge Graph" confirmation dialog (KSA §5.5).
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    chapters = 0
    chat_turns = 0
    glossary_entities = 0

    scope = body.scope

    # TODO(K16.2): scope_range is accepted but not yet forwarded to
    # data sources. Book-service's internal chapters endpoint does not
    # support range filtering yet. Tracked as D-K16.2-02 in
    # SESSION_PATCH. The field is kept on the request model so the
    # frontend can start sending it without a contract change when
    # filtering lands.

    # Chapter count — via book-service internal API
    if scope in ("chapters", "all") and project.book_id is not None:
        count = await book_client.count_chapters(project.book_id)
        chapters = count if count is not None else 0

    # Pending chat turns — from extraction_pending queue
    if scope in ("chat", "all"):
        chat_turns = await pending_repo.count_pending(user_id, project_id)

    # Glossary entity count — via glossary-service internal API
    if scope in ("glossary_sync", "all") and project.book_id is not None:
        count = await glossary_client.count_entities(project.book_id)
        glossary_entities = count if count is not None else 0

    items_total = chapters + chat_turns + glossary_entities
    estimated_tokens = (
        chapters * _TOKENS_PER_CHAPTER
        + chat_turns * _TOKENS_PER_CHAT_TURN
        + glossary_entities * _TOKENS_PER_GLOSSARY_ENTITY
    )

    base_cost = Decimal(estimated_tokens) * _DEFAULT_COST_PER_TOKEN
    cost_low = (base_cost * Decimal("0.7")).quantize(Decimal("0.01"))
    cost_high = (base_cost * Decimal("1.3")).quantize(Decimal("0.01"))

    duration = items_total * _SECONDS_PER_ITEM

    return EstimateResponse(
        items_total=items_total,
        items=EstimateItemCounts(
            chapters=chapters,
            chat_turns=chat_turns,
            glossary_entities=glossary_entities,
        ),
        estimated_tokens=estimated_tokens,
        estimated_cost_usd_low=cost_low,
        estimated_cost_usd_high=cost_high,
        estimated_duration_seconds=duration,
    )
