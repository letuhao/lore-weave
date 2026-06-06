"""A2-S2 — internal canon-read endpoint for the composition canon guard.

POST /internal/projects/{project_id}/fact-for-check

Returns the canon snapshot (status + entities + relations + events≤P) for an
entity-id set at a reading position. Consumed by composition-service's A2-S3
SCORE-style symbolic guard + LLM-judge. Read-only.

Authentication: X-Internal-Token (service-to-service; composition already holds
the knowledge internal token for build_context).
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.fact_for_check import FactForCheck, get_fact_for_check
from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/projects",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


class FactForCheckRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=1, max_length=200)
    at_order: int = Field(ge=0)
    relation_limit: int = Field(default=50, ge=1, le=500)
    event_limit: int = Field(default=50, ge=1, le=500)


@router.post("/{project_id}/fact-for-check", response_model=FactForCheck)
async def fact_for_check(project_id: UUID, body: FactForCheckRequest) -> FactForCheck:
    """A2-S2 — canon snapshot for the A2-S3 guard. Resolves the owning user
    from knowledge_projects; returns empty (not 404) when the graph is absent."""
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
        # Track 1 (no graph) — empty snapshot, the guard degrades to advisory.
        return FactForCheck(at_order=body.at_order)

    async with neo4j_session() as session:
        result = await get_fact_for_check(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            entity_ids=body.entity_ids,
            at_order=body.at_order,
            relation_limit=body.relation_limit,
            event_limit=body.event_limit,
        )
    return result
