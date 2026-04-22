"""K19c.4 — Public user-scope entity endpoints.

GET  /v1/knowledge/me/entities?scope=global&limit=50
DELETE /v1/knowledge/me/entities/{entity_id}

The GET powers the Global tab's Preferences section (K19c.4) and is
built to generalise to `scope=project` when K19d lands. The DELETE
is a soft archive (reuses ``archive_entity`` with reason
``user_archived``); it preserves EVIDENCED_BY edges + relations so
the entity can still appear in cross-reference traces even after
being hidden from the preference list.
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import (
    ENTITIES_MAX_LIMIT,
    Entity,
    archive_entity,
    list_user_entities,
)
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge/me",
    tags=["user-entities"],
    dependencies=[Depends(get_current_user)],
)


class UserEntitiesResponse(BaseModel):
    entities: list[Entity]


@router.get("/entities", response_model=UserEntitiesResponse)
async def list_user_entities_endpoint(
    scope: Literal["global"] = Query(
        "global",
        description=(
            "Entity scope. Only 'global' is supported in K19c — 'project' "
            "lands alongside the K19d Entities tab."
        ),
    ),
    limit: int = Query(50, ge=1, le=ENTITIES_MAX_LIMIT),
    user_id: UUID = Depends(get_current_user),
) -> UserEntitiesResponse:
    """K19c.4 — list the caller's active global-scope entities.

    "Global-scope" = entities with no `project_id`, extracted by
    Track 2 from chat turns that weren't tied to a specific project.
    Archived entities are excluded; rollback path is re-extraction
    on the next chat turn rather than UI restore (matches existing
    `archive_entity` semantics).
    """
    async with neo4j_session() as session:
        rows = await list_user_entities(
            session,
            user_id=str(user_id),
            scope=scope,
            limit=limit,
        )
    return UserEntitiesResponse(entities=rows)


@router.delete(
    "/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_user_entity(
    entity_id: str,
    user_id: UUID = Depends(get_current_user),
) -> None:
    """K19c.4 — soft-archive a user entity (UI "delete" = hide it).

    Reuses `archive_entity` with `reason='user_archived'`. 404 only
    when the entity doesn't exist for this user at all (cross-user
    or typo in the id). **Idempotent** per RFC 9110: a second DELETE
    on the same entity_id still returns 204 because `_ARCHIVE_CYPHER`
    has no `archived_at IS NULL` guard — it just rewrites
    `archived_at = now()` and the same row comes back. The only
    visible side effect of the second call is a bumped `updated_at`
    and a fresh `archive_reason`. Callers (the FE panel) should
    treat 204 + 404 symmetrically as "entity is now hidden".
    """
    async with neo4j_session() as session:
        result = await archive_entity(
            session,
            user_id=str(user_id),
            canonical_id=entity_id,
            reason="user_archived",
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found",
        )
    logger.info(
        "K19c.4: user archived entity user_id=%s entity_id=%s",
        user_id, entity_id,
    )
