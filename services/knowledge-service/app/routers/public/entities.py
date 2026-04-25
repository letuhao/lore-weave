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

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from app.db.neo4j import neo4j_session
from app.db.neo4j_helpers import run_read
from app.db.neo4j_repos.canonical import canonicalize_entity_name
from app.db.neo4j_repos.entities import (
    ENTITIES_MAX_LIMIT,
    Entity,
    EntityDetail,
    MergeEntitiesError,
    archive_entity,
    get_entity,
    get_entity_with_relations,
    list_entities_filtered,
    list_user_entities,
    merge_entities,
    unlock_entity_user_edited,
    update_entity_fields,
)
from app.db.repositories import VersionMismatchError
from app.db.repositories.entity_alias_map import EntityAliasMapRepo
from app.deps import get_entity_alias_map_repo
from app.middleware.jwt_auth import get_current_user


# C9 (D-K19d-γa-01) — local If-Match / ETag helpers. Duplicated from
# ``projects.py`` + ``summaries.py`` on purpose: keeping these inline
# avoids a new shared module + import ripple and matches the existing
# codebase convention for router-level concerns that don't warrant a
# cross-cutting dependency.
def _parse_if_match(header_value: str | None) -> int | None:
    """Return the integer version from an If-Match header, or None
    when no header was sent. Raises 422 on malformed syntax."""
    if header_value is None:
        return None
    s = header_value.strip()
    # Accept both strong ("N") and weak (W/"N") ETag forms.
    if s.startswith('W/'):
        s = s[2:].strip()
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        inner = s[1:-1]
        try:
            return int(inner)
        except ValueError:
            pass
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="If-Match header must be a weak ETag with an integer version",
    )


def _etag(version: int) -> str:
    """Weak ETag for a versioned Entity. Weak because the node carries
    more state than just the version counter (updated_at, denormalized
    stats, etc.) — two serializations of the same version are
    *semantically* equivalent but not byte-identical."""
    return f'W/"{version}"'

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
    response: Response,
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

    C9: ETag header handed back so the FE can send `If-Match: W/"N"`
    on the next PATCH.
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
    response.headers["ETag"] = _etag(detail.entity.version)
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
    response: Response,
    entity_id: str = Path(min_length=1, max_length=200),
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
) -> Entity:
    """K19d.5 + C9 — update an entity's display fields with optimistic
    concurrency. Lock future extractions from overwriting user-edited
    aliases.

    Cross-user / missing entity collapses to 404 per KSA §6.4.

    C9 (D-K19d-γa-01): strict If-Match contract mirrors projects +
    summaries (D-K8-03). A PATCH without If-Match is almost certainly
    a stale client and is rejected with 428. A version mismatch
    returns 412 with the CURRENT entity as body + refreshed ETag so
    the FE can reset its baseline without a second GET.
    """
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match header required — GET the entity first to obtain an ETag",
        )

    async with neo4j_session() as session:
        try:
            updated = await update_entity_fields(
                session,
                user_id=str(user_id),
                entity_id=entity_id,
                name=body.name,
                kind=body.kind,
                aliases=body.aliases,
                expected_version=expected_version,
            )
        except VersionMismatchError as exc:
            # exc.current is the Entity this route put in — cast safely.
            current: Entity = exc.current
            return JSONResponse(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                content=current.model_dump(mode="json"),
                headers={"ETag": _etag(current.version)},
            )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found",
        )
    logger.info(
        "K19d.5: user updated entity user_id=%s entity_id=%s "
        "fields=%s version=%d",
        user_id,
        entity_id,
        [
            f for f in ("name", "kind", "aliases")
            if getattr(body, f) is not None
        ],
        updated.version,
    )
    response.headers["ETag"] = _etag(updated.version)
    return updated


# ── C9 — POST /entities/{id}/unlock ─────────────────────────────────


@entities_router.post(
    "/entities/{entity_id}/unlock",
    response_model=Entity,
)
async def unlock_entity(
    response: Response,
    entity_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
) -> Entity:
    """C9 (D-K19d-γa-02) — clear the user_edited lock so extractions
    can contribute aliases again. No If-Match: matches the /archive
    pattern — a one-way idempotent flag flip has no concurrency hazard
    that a baseline-refresh dance would solve.

    Cross-user / missing id collapses to 404 per KSA §6.4.
    """
    async with neo4j_session() as session:
        updated = await unlock_entity_user_edited(
            session,
            user_id=str(user_id),
            entity_id=entity_id,
        )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found",
        )
    logger.info(
        "C9: user unlocked entity user_id=%s entity_id=%s version=%d",
        user_id, entity_id, updated.version,
    )
    response.headers["ETag"] = _etag(updated.version)
    return updated


# ── K19d γ-b — POST /entities/{id}/merge-into/{other_id} ────────────


class EntityMergeResponse(BaseModel):
    target: Entity
    aliases_redirected: int = 0  # C17 — count of alias-map rows written


_MERGE_ERROR_HTTP_STATUS: dict[str, int] = {
    "same_entity": status.HTTP_400_BAD_REQUEST,
    "entity_not_found": status.HTTP_404_NOT_FOUND,
    "entity_archived": status.HTTP_409_CONFLICT,
    "glossary_conflict": status.HTTP_409_CONFLICT,
    "alias_collision": status.HTTP_409_CONFLICT,  # C17
}


# C17 — collision pre-check. For each alias on source, verify NO other
# live entity in the same scope+kind already claims that canonical_name.
# If hit, the merge is ambiguous (a third entity already exists with
# that identity); refuse with 409 alias_collision so the user resolves
# the third entity first.
_C17_COLLISION_PRECHECK_CYPHER = """
UNWIND $candidate_canonicals AS ca
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND coalesce(e.project_id, '') = coalesce($project_id, '')
  AND e.kind = $kind
  AND e.canonical_name = ca
  AND e.id <> $source_id
  AND e.id <> $target_id
  AND e.archived_at IS NULL
RETURN e.id AS id, e.name AS name, ca AS conflicting_alias
LIMIT 1
"""


@entities_router.post(
    "/entities/{entity_id}/merge-into/{other_id}",
    response_model=EntityMergeResponse,
)
async def merge_entity_into(
    entity_id: str = Path(min_length=1, max_length=200),
    other_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
    alias_map_repo: EntityAliasMapRepo = Depends(get_entity_alias_map_repo),
) -> EntityMergeResponse:
    """K19d.6 + C17 — merge `entity_id` (source) into `other_id` (target).

    Re-homes every RELATES_TO and EVIDENCED_BY edge from source to
    target, combines aliases + source_types + mention_count +
    evidence_count, then DETACH DELETEs source. Target is returned
    with `user_edited=true` so extraction doesn't silently undo
    the merge by re-adding removed alias variants.

    C17 (D-K19d-γb-03 closer): on success, every alias on source
    (plus source's canonical_name) is registered in
    ``entity_alias_map`` so future re-extraction of those names
    redirects to target instead of resurrecting source. If user
    previously merged X→source, those redirects are repointed onto
    target. Pre-merge collision check refuses the merge if any
    source alias already names a third live entity (ambiguity).

    Error envelope — structured `detail.error_code` lets the FE
    switch on the failure class:
      - 400 ``same_entity``        — source_id == other_id
      - 404 ``entity_not_found``   — either missing / cross-user
      - 409 ``entity_archived``    — either archived
      - 409 ``glossary_conflict``  — anchored to different glossary
                                      entries
      - 409 ``alias_collision``    — a source alias names a third
                                      live entity; resolve that
                                      entity first (C17)
    """
    user_id_str = str(user_id)

    # C17 review-impl HIGH-1 — handle the trivial self-merge BEFORE
    # the collision precheck. Otherwise a user typing
    # /X/merge-into/X against an entity sharing canonical_name with
    # any sibling would surface 409 alias_collision instead of the
    # correct 400 same_entity (the collision filter excludes only
    # source AND target ids, which collapse to the same exclusion
    # under self-merge — siblings still match).
    if entity_id == other_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "same_entity",
                "message": "source and target must be distinct entities",
            },
        )

    async with neo4j_session() as session:
        # C17 step 1 — capture source pre-merge so we can write
        # alias-map rows after surgery (the source node is gone by
        # then). get_entity already enforces user-id ownership; if
        # source is missing/cross-user the merge_entities call below
        # raises entity_not_found.
        source = await get_entity(
            session, user_id=user_id_str, canonical_id=entity_id,
        )

        # C17 step 2 — collision pre-check (only if source loaded).
        if source is not None:
            project_scope = source.project_id or "global"
            candidate_canonicals = sorted({
                ca for ca in (
                    canonicalize_entity_name(a) for a in source.aliases
                ) if ca
            })
            # Add source's canonical_name to the precheck if not
            # already in aliases-derived set (defensive).
            if source.canonical_name and source.canonical_name not in candidate_canonicals:
                candidate_canonicals.append(source.canonical_name)
            if candidate_canonicals:
                collision_result = await run_read(
                    session,
                    _C17_COLLISION_PRECHECK_CYPHER,
                    user_id=user_id_str,
                    project_id=source.project_id,
                    kind=source.kind,
                    candidate_canonicals=candidate_canonicals,
                    source_id=entity_id,
                    target_id=other_id,
                )
                collision_row = await collision_result.single()
                if collision_row is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error_code": "alias_collision",
                            "message": (
                                "Source alias collides with another live "
                                f"entity '{collision_row['name']}' "
                                f"(id={collision_row['id']}). Merge or "
                                "rename that entity first."
                            ),
                            "colliding_entity_id": collision_row["id"],
                            "colliding_entity_name": collision_row["name"],
                            "conflicting_alias": collision_row["conflicting_alias"],
                        },
                    )

        # C17 step 3 — run existing surgery.
        try:
            target = await merge_entities(
                session,
                user_id=user_id_str,
                source_id=entity_id,
                target_id=other_id,
            )
        except MergeEntitiesError as exc:
            http_status = _MERGE_ERROR_HTTP_STATUS.get(
                exc.error_code, status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(
                status_code=http_status,
                detail={
                    "error_code": exc.error_code,
                    "message": str(exc),
                },
            )

    # C17 step 4 — alias-map writes + chain re-point. Outside the
    # neo4j_session block because Postgres I/O is independent. The
    # Neo4j surgery is already committed; alias-map writes are
    # best-effort per ADR §5.4. Review-impl HIGH-2: wrap in try so
    # a transient Postgres failure doesn't surface as 500 (which
    # would mislead the user into a retry that 404s because source
    # is already gone). Failures log a WARNING; ops can recover via
    # scripts/backfill_entity_alias_map.py.
    aliases_redirected = 0
    if source is not None:
        project_scope = source.project_id or "global"
        # Union of source's aliases + source.canonical_name. Skip
        # aliases that canonicalize to the empty string (defensive —
        # extraction shouldn't produce these but a stray honorific-
        # only alias would).
        canonicals_to_register = set()
        for alias in source.aliases:
            ca = canonicalize_entity_name(alias)
            if ca:
                canonicals_to_register.add(ca)
        if source.canonical_name:
            canonicals_to_register.add(source.canonical_name)

        for ca in canonicals_to_register:
            try:
                await alias_map_repo.record_merge(
                    user_id=user_id,
                    project_scope=project_scope,
                    kind=source.kind,
                    canonical_alias=ca,
                    target_entity_id=other_id,
                    source_entity_id=entity_id,
                )
                aliases_redirected += 1
            except Exception:
                logger.warning(
                    "C17 record_merge failed (best-effort): "
                    "user=%s alias=%s target=%s — backfill recovers",
                    user_id, ca, other_id,
                    exc_info=True,
                )

        # C17 step 5 — chain re-point. If user previously merged X
        # into source, those rows still point at source.id (now
        # deleted). Repoint onto target so multi-step merge chains
        # (REVIEW-DESIGN catch) keep redirecting consistently.
        try:
            repointed = await alias_map_repo.repoint_target(
                user_id=user_id,
                old_target_entity_id=entity_id,
                new_target_entity_id=other_id,
            )
            if repointed:
                logger.info(
                    "C17: re-pointed %d existing redirects from %s → %s",
                    repointed, entity_id, other_id,
                )
        except Exception:
            logger.warning(
                "C17 repoint_target failed (best-effort): "
                "user=%s old=%s new=%s — backfill recovers",
                user_id, entity_id, other_id,
                exc_info=True,
            )

    logger.info(
        "K19d.6 + C17: user merged entity user_id=%s source=%s target=%s "
        "aliases_redirected=%d",
        user_id, entity_id, other_id, aliases_redirected,
    )
    return EntityMergeResponse(target=target, aliases_redirected=aliases_redirected)
