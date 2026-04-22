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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, model_validator

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import (
    ENTITIES_MAX_LIMIT,
    Entity,
    EntityDetail,
    archive_entity,
    get_entity_with_relations,
    list_entities_filtered,
    list_user_entities,
    update_entity_fields,
)
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge/me",
    tags=["user-entities"],
    dependencies=[Depends(get_current_user)],
)

# K19d — separate router for the browse/detail endpoints. The path
# prefix is `/v1/knowledge` (no `/me`) because these endpoints are
# for the power-user Entities tab that browses across all the user's
# projects, not just their cross-project preferences. Distinct from
# the `/me/entities` endpoint which is K19c's Preferences section.
entities_router = APIRouter(
    prefix="/v1/knowledge",
    tags=["entities"],
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


# ── K19d browse / detail endpoints ───────────────────────────────────


# K19d.2: minimum length on the `search` param. One-character searches
# devolve into a CONTAINS scan over every name + alias in the user's
# entity set — cheap per-row but n*r where r is rows. At 2 chars the
# substring is already distinctive enough that the filter cuts the
# scan down to a handful of matches for any realistic prose corpus.
_SEARCH_MIN_LENGTH = 2


class EntitiesListResponse(BaseModel):
    entities: list[Entity]
    total: int


@entities_router.get("/entities", response_model=EntitiesListResponse)
async def list_entities(
    project_id: UUID | None = Query(
        default=None,
        description=(
            "Filter to a specific project. Omit (or pass no value) to "
            "browse across every project + global-scope entities the "
            "caller owns."
        ),
    ),
    kind: str | None = Query(
        default=None,
        max_length=100,
        description=(
            "Exact-match filter on `Entity.kind` (e.g. `character`, "
            "`location`, `concept`)."
        ),
    ),
    search: str | None = Query(
        default=None,
        min_length=_SEARCH_MIN_LENGTH,
        max_length=200,
        description=(
            "Case-insensitive substring match against name + aliases. "
            "Minimum 2 characters to avoid whole-corpus scans."
        ),
    ),
    limit: int = Query(50, ge=1, le=ENTITIES_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    user_id: UUID = Depends(get_current_user),
) -> EntitiesListResponse:
    """K19d.2 — browse entities with optional filters.

    Multi-tenant safety: `user_id` from JWT is threaded through to
    the Cypher `$user_id` parameter; cross-user rows are filtered
    at the MATCH. The Entities tab never exposes a user_id body
    field — a caller cannot spoof another user's entities.
    """
    async with neo4j_session() as session:
        rows, total = await list_entities_filtered(
            session,
            user_id=str(user_id),
            project_id=str(project_id) if project_id is not None else None,
            kind=kind,
            search=search,
            limit=limit,
            offset=offset,
        )
    return EntitiesListResponse(entities=rows, total=total)


@entities_router.get(
    "/entities/{entity_id}",
    response_model=EntityDetail,
)
async def get_entity_detail(
    # Review-impl L1: hard cap on entity_id length. Canonical ids in
    # `entity_canonical_id` are deterministic hex hashes well under
    # 100 chars; 200 is generous headroom. Without the cap, a caller
    # could push arbitrary-length strings through to the Cypher
    # `$id` param — parameterization blocks injection but not slow
    # comparison scans.
    entity_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
) -> EntityDetail:
    """K19d.4 — entity detail with 1-hop active :RELATES_TO edges.

    Returns 404 for entities that don't exist OR are owned by
    another user — cross-user access collapses to "not found" per
    KSA §6.4 anti-existence-leak rules.

    MVP detail ships base entity + 1-hop relations only. Facts,
    verbatim passages, and full per-source provenance are slated
    for a follow-up cycle — the FE can lazy-load them on demand
    via future `/entities/{id}/{facts|passages|provenance}` routes.
    """
    async with neo4j_session() as session:
        detail = await get_entity_with_relations(
            session,
            user_id=str(user_id),
            entity_id=entity_id,
        )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found",
        )
    return detail


# ── K19d γ-a — PATCH /entities/{id} ──────────────────────────────────


class EntityUpdate(BaseModel):
    """K19d.5 PATCH body. At least one field must be provided — a
    no-op PATCH still bumps `user_edited` / `updated_at` at the repo
    layer, so guarding here keeps the semantics honest."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = Field(default=None, min_length=1, max_length=100)
    aliases: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _at_least_one(self) -> "EntityUpdate":
        if self.name is None and self.kind is None and self.aliases is None:
            raise ValueError(
                "at least one of name / kind / aliases must be provided"
            )
        # Element-level validation on aliases: reject empty or
        # whitespace-only entries, which would poison the CONTAINS
        # search path in list_entities_filtered.
        if self.aliases is not None:
            for alias in self.aliases:
                if not alias or not alias.strip():
                    raise ValueError("aliases entries must be non-empty")
                if len(alias) > 200:
                    raise ValueError("each alias must be ≤200 chars")
        return self


@entities_router.patch(
    "/entities/{entity_id}",
    response_model=Entity,
)
async def patch_entity(
    body: EntityUpdate,
    entity_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
) -> Entity:
    """K19d.5 — update an entity's display fields and lock future
    extractions from overwriting user-edited aliases.

    Cross-user / missing entity collapses to 404 per KSA §6.4.
    """
    async with neo4j_session() as session:
        updated = await update_entity_fields(
            session,
            user_id=str(user_id),
            entity_id=entity_id,
            name=body.name,
            kind=body.kind,
            aliases=body.aliases,
        )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found",
        )
    logger.info(
        "K19d.5: user updated entity user_id=%s entity_id=%s "
        "fields=%s",
        user_id,
        entity_id,
        [
            f for f in ("name", "kind", "aliases")
            if getattr(body, f) is not None
        ],
    )
    return updated
