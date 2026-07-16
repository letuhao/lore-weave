"""K19c.4 — Public user-scope entity endpoints.

GET  /v1/knowledge/me/entities?scope=global&limit=50
DELETE /v1/knowledge/me/entities/{entity_id}

The GET powers the Global tab's Preferences section (K19c.4) and is
built to generalise to `scope=project` when K19d lands. The DELETE
is a soft archive (``user_archive_entity`` with reason
``user_archived``); it preserves EVIDENCED_BY edges + relations AND
the ``glossary_entity_id`` anchor (D-K19c.4-01) so the entity can
still appear in cross-reference traces and come back anchored on a
later restore, even after being hidden from the preference list.
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status
from fastapi import status as status_codes  # C8: alias — the list_entities route has a `status` query param that shadows the module name
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from app.db.neo4j import neo4j_session
from app.db.neo4j_helpers import run_read
from app.db.neo4j_repos.canonical import canonicalize_entity_name
from app.db.neo4j_repos.entities import (
    AUTHORABLE_KINDS,
    ENTITIES_MAX_LIMIT,
    ENTITY_SORT_KEYS,
    ENTITY_STATUSES,
    SUPPORTED_VECTOR_DIMS,
    Entity,
    EntityDetail,
    MergeEntitiesError,
    user_archive_entity,
    restore_entity,
    find_entities_by_vector,
    find_gap_candidates,
    get_entity,
    get_entity_with_relations,
    link_to_glossary,
    list_entities_filtered,
    list_user_entities,
    merge_entities,
    merge_entity,
    unlock_entity_user_edited,
    update_entity_fields,
)
from app.db.neo4j_repos.entity_status import statuses_detail_at_order
from app.db.neo4j_repos.facts import Fact, list_facts_for_entity
from app.db.neo4j_repos.relations import (
    SUBGRAPH_MAX_HOPS,
    SUBGRAPH_MAX_NODE_CAP,
    Subgraph,
    get_project_subgraph,
    get_world_subgraph,
)
from app.db.repositories import VersionMismatchError
from app.db.repositories.entity_alias_map import EntityAliasMapRepo
from app.db.repositories.projects import ProjectsRepo
from app.clients.book_client import BookClient, BookServiceUnavailable, WorldNotFound
from app.world_rollup import resolve_world_project_ids
from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.clients.glossary_client import GlossaryClient
from app.extraction.entity_resolver import normalize_kind_for_anchor_lookup
from app.extraction.glossary_writeback import WRITEBACK_TAG
from app.deps import (
    get_book_client,
    get_embedding_client,
    get_entity_alias_map_repo,
    get_glossary_client,
    get_projects_repo,
)
from app.spoiler_window import resolve_before_order
from app.events.outbox_emit import (
    ENTITY_CORRECTED,
    emit_correction,
    entity_correction_payload,
    entity_snapshot,
)
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

    Uses `user_archive_entity` with `reason='user_archived'` — the
    variant that PRESERVES `glossary_entity_id` (D-K19c.4-01) so a
    later restore re-shows the entity still anchored. 404 only
    when the entity doesn't exist for this user at all (cross-user
    or typo in the id). **Idempotent** per RFC 9110: a second DELETE
    on the same entity_id still returns 204 because `_USER_ARCHIVE_CYPHER`
    has no `archived_at IS NULL` guard — it just rewrites
    `archived_at = now()` and the same row comes back. The only
    visible side effect of the second call is a bumped `updated_at`
    and a fresh `archive_reason`. Callers (the FE panel) should
    treat 204 + 404 symmetrically as "entity is now hidden".
    """
    async with neo4j_session() as session:
        # Phase B: read the pre-archive snapshot first (for the correction
        # event). archive is idempotent + op=delete → diff_class=spurious-drop
        # regardless of `before` content, so a read-before-write here is
        # low-stakes (unlike the versioned PATCH, which uses same-Cypher
        # capture). `before` is None when the entity doesn't exist.
        before_entity = await get_entity(
            session, user_id=str(user_id), canonical_id=entity_id,
        )
        # D-K19c.4-01 — user "delete" is hide-now-restore-later, so use the
        # variant that PRESERVES `glossary_entity_id`; the glossary entry still
        # exists and a later restore should bring the entity back anchored.
        result = await user_archive_entity(
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
    before = (
        entity_snapshot(before_entity.name, before_entity.kind, before_entity.aliases)
        if before_entity is not None
        else None
    )
    logger.info(
        "K19c.4: user archived entity user_id=%s entity_id=%s",
        user_id, entity_id,
    )
    # Phase B — a user archive (delete) is a "spurious-drop" correction
    # (after=null). Best-effort emit after the Neo4j write (§6.6).
    await emit_correction(
        event_type=ENTITY_CORRECTED,
        aggregate_id=entity_id,
        payload=entity_correction_payload(
            user_id=str(user_id),
            project_id=result.project_id,
            book_id=None,
            target_id=entity_id,
            op="delete",
            before=before,
            after=None,
            actor_id=str(user_id),
        ),
    )


@router.post(
    "/entities/{entity_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def restore_user_entity(
    entity_id: str,
    user_id: UUID = Depends(get_current_user),
) -> None:
    """D-KG-ENTITY-RESTORE (S7) — un-archive a user entity: the inverse of the
    soft-delete above. Without this, archiving is a **one-way trap** — the UI can
    hide an entity but never bring it back (the only prior path was re-extraction).

    Clears `archived_at`/`archive_reason` via `restore_entity` (which PRESERVES the
    `glossary_entity_id` anchor). **Idempotent**: restoring an already-active entity
    is a no-op that still returns 204 (the row comes back with `archived_at` already
    null). 404 only when the entity doesn't exist for this user at all.

    ⚠ `restore_entity` does NOT recompute `anchor_score` (that is K11.5b's job) — a
    restored entity ranks at score 0.0 until the next recompute pass. This is
    documented, not a bug: the row is visible and anchored immediately; only its
    ranking weight lags one pass.
    """
    async with neo4j_session() as session:
        result = await restore_entity(
            session,
            user_id=str(user_id),
            canonical_id=entity_id,
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found",
        )
    logger.info(
        "S7 D-KG-ENTITY-RESTORE: user restored entity user_id=%s entity_id=%s",
        user_id, entity_id,
    )


# ── K19d browse / detail endpoints ───────────────────────────────────


# K19d.2: minimum length on the `search` param. One-character searches
# devolve into a CONTAINS scan over every name + alias in the user's
# entity set — cheap per-row but n*r where r is rows. At 2 chars the
# substring is already distinctive enough that the filter cuts the
# scan down to a handful of matches for any realistic prose corpus.
_SEARCH_MIN_LENGTH = 2


# C8 — closed enums for the new status filter + sort key. Mirror the
# repo's ENTITY_STATUSES / ENTITY_SORT_KEYS tuples; Literal is the only
# form FastAPI introspects for 422 validation.
EntityStatusFilter = Literal["canonical", "discovered", "archived"]
EntitySortBy = Literal["mention_count", "anchor_score"]

# C8 — semantic_query length bound. Matches the drawers-search query
# cap shape: short enough that a single embed call is cheap, long
# enough for a sentence-level natural-language query.
_SEMANTIC_QUERY_MAX_LENGTH = 1000


class EntitiesListResponse(BaseModel):
    entities: list[Entity]
    total: int
    # C8 — null on the plain (FTS / browse) path; set on the
    # `semantic_query` vector path so the FE can show "searched via X"
    # and distinguish "project not indexed" (null model) from a
    # zero-hit live search.
    embedding_model: str | None = None


@entities_router.get("/entities", response_model=EntitiesListResponse)
async def list_entities(
    project_id: UUID | None = Query(
        default=None,
        description=(
            "Filter to a specific project. Omit (or pass no value) to "
            "browse across every project + global-scope entities the "
            "caller owns. REQUIRED when `semantic_query` is set "
            "(vector search is project-scoped)."
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
            "Case-insensitive substring (FTS) match against name + "
            "aliases. Minimum 2 characters to avoid whole-corpus scans. "
            "Mutually exclusive with `semantic_query`."
        ),
    ),
    semantic_query: str | None = Query(
        default=None,
        min_length=_SEARCH_MIN_LENGTH,
        max_length=_SEMANTIC_QUERY_MAX_LENGTH,
        description=(
            "C8: natural-language VECTOR search over entity embeddings. "
            "Embeds the query via the project's provider-registry "
            "embedding model, then runs two-layer (anchor-weighted) "
            "vector retrieval. Requires `project_id`. Distinct from the "
            "plain `search` FTS param — pass one or the other."
        ),
    ),
    status: EntityStatusFilter | None = Query(
        default=None,
        description=(
            "C8: filter to a single DERIVED status — `canonical` "
            "(glossary-anchored), `discovered` (unanchored, active), or "
            "`archived`. Omit for the default active view (canonical + "
            "discovered). `archived` is the only way to surface archived "
            "rows."
        ),
    ),
    sort_by: EntitySortBy = Query(
        default="mention_count",
        description=(
            "C8: ordering key. `mention_count` (default, browse-by-"
            "frequency) or `anchor_score` (anchored-first curation view). "
            "Ignored on the `semantic_query` path (vector relevance + "
            "anchor weighting drive that ordering)."
        ),
    ),
    limit: int = Query(50, ge=1, le=ENTITIES_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    before_chapter_id: UUID | None = Query(
        default=None,
        description=(
            "W11 reader SPOILER WINDOW. When set, the list is restricted to "
            "entities the reader has actually MET — those with at least one "
            "fact established by this chapter. FAIL-CLOSED: an unresolvable "
            "chapter returns an EMPTY list, never the full cast. Omit for the "
            "editor/curation view (whole cast). The reader lore-seeker passes "
            "the chapter being read; without this, listing entity NAMES leaks "
            "the existence of later-introduced characters (adversarial-review "
            "finding — the facts were windowed but the name list was not)."
        ),
    ),
    user_id: UUID = Depends(get_current_user),
    book_client: BookClient = Depends(get_book_client),
) -> EntitiesListResponse:
    """K19d.2 + C8 — browse / search entities.

    Two retrieval modes:
      - **plain** (default): paginated browse with `kind` / `search`
        (FTS) / `status` filters + `sort_by`.
      - **semantic** (`semantic_query` set): two-layer anchor-weighted
        VECTOR search. The query is embedded server-side via the
        project's provider-registry embedding model (no hardcoded model
        name, no per-service embed env — same BYOK resolution as the
        drawers-search path). `status` still filters the vector result
        set; `sort_by` is ignored (vector relevance + anchor_score win).

    Multi-tenant safety: `user_id` from JWT is threaded through to
    the Cypher `$user_id` parameter; cross-user rows are filtered
    at the MATCH. The Entities tab never exposes a user_id body
    field — a caller cannot spoof another user's entities.
    """
    if semantic_query is not None:
        if search is not None:
            raise HTTPException(
                status_code=status_codes.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="pass either `search` (FTS) or `semantic_query` "
                "(vector), not both",
            )
        if before_chapter_id is not None:
            # The W11 spoiler window is not implemented on the vector path (the
            # reader lore-seeker uses plain FTS). REJECT rather than silently
            # return an UNWINDOWED semantic result set — a windowed request that
            # comes back unwindowed would be exactly the leak this closes.
            raise HTTPException(
                status_code=status_codes.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="`before_chapter_id` (spoiler window) is not supported "
                "with `semantic_query`; use plain `search` for the reader view",
            )
        if project_id is None:
            raise HTTPException(
                status_code=status_codes.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="`project_id` is required for `semantic_query` "
                "(vector search is project-scoped)",
            )
        # Lazy dep resolution: the projects-repo + embedding-client are
        # only needed on the (rarer) vector path, and `get_projects_repo`
        # touches the knowledge pool. Resolving them as eager route-level
        # `Depends` would force every plain browse call (and its tests) to
        # stand up the pool. We call the same getters the drawers route
        # uses; unit tests patch THESE module references.
        return await _semantic_search_entities(
            user_id=user_id,
            project_id=project_id,
            query=semantic_query,
            kind=kind,
            status=status,
            limit=limit,
            projects_repo=await get_projects_repo(),
            embedding_client=await get_embedding_client(),
        )

    # W11 spoiler window: resolve the reader's chapter to its fact-ordinal cutoff.
    # resolve_before_order FAILS CLOSED — an omitted/unresolvable chapter → -1, so the
    # windowed query keeps nothing. before_order stays None ONLY when the caller did not
    # ask for a window (editor/curation), which the repo reads as "unfiltered".
    before_order: int | None = None
    if before_chapter_id is not None:
        before_order, _ = await resolve_before_order(book_client, before_chapter_id)

    async with neo4j_session() as session:
        rows, total = await list_entities_filtered(
            session,
            user_id=str(user_id),
            project_id=str(project_id) if project_id is not None else None,
            kind=kind,
            search=search,
            status=status,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
            before_order=before_order,
        )
    return EntitiesListResponse(entities=rows, total=total)


async def _semantic_search_entities(
    *,
    user_id: UUID,
    project_id: UUID,
    query: str,
    kind: str | None,
    status: str | None,
    limit: int,
    projects_repo: ProjectsRepo,
    embedding_client: EmbeddingClient,
) -> EntitiesListResponse:
    """C8 — vector search branch of `list_entities`.

    Mirrors the drawers-search contract:
      - 404 when the project is missing / cross-user (anti-leak).
      - 200 `{entities: [], embedding_model: null}` when the project has
        no embedding model configured (FE: "not indexed yet").
      - 502 `provider_error` on EmbeddingError from the BYOK provider.
      - 502 `embedding_dim_mismatch` when the live vector length
        disagrees with the project's stored `embedding_dimension`.

    The embedding model is resolved from `project.embedding_model`
    (a provider-registry model ref) — NEVER a literal in this code.
    """
    if not query.strip():
        return EntitiesListResponse(entities=[], total=0, embedding_model=None)

    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status_codes.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    if (
        project.embedding_model is None
        or project.embedding_dimension is None
        or project.embedding_dimension not in SUPPORTED_VECTOR_DIMS
    ):
        return EntitiesListResponse(
            entities=[], total=0, embedding_model=project.embedding_model,
        )

    try:
        embed_result = await embedding_client.embed(
            user_id=user_id,
            model_source="user_model",
            model_ref=project.embedding_model,
            texts=[query],
        )
    except EmbeddingError as exc:
        logger.warning(
            "C8: semantic entity search embedding failed project=%s model=%s: %s",
            project_id, project.embedding_model, exc,
        )
        raise HTTPException(
            status_code=status_codes.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "provider_error",
                "message": str(exc),
                "retryable": bool(getattr(exc, "retryable", False)),
            },
        )

    if not embed_result.embeddings or not embed_result.embeddings[0]:
        return EntitiesListResponse(
            entities=[], total=0, embedding_model=project.embedding_model,
        )
    query_vector = embed_result.embeddings[0]

    try:
        async with neo4j_session() as session:
            hits = await find_entities_by_vector(
                session,
                user_id=str(user_id),
                project_id=str(project_id),
                query_vector=query_vector,
                dim=project.embedding_dimension,
                embedding_model=project.embedding_model,
                # Oversample so post-filtering by kind/status doesn't
                # starve the page: ask for limit*N candidates, then
                # trim after the Python-side filters.
                limit=limit * 5,
                include_archived=(status == "archived"),
            )
    except ValueError as exc:
        logger.warning(
            "C8: semantic entity search dim mismatch project=%s stored=%s live=%s",
            project_id, project.embedding_dimension, len(query_vector),
        )
        raise HTTPException(
            status_code=status_codes.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "embedding_dim_mismatch",
                "message": str(exc),
            },
        )

    rows = [h.entity for h in hits]
    # Post-filter by kind + derived status (the vector index is global;
    # these dimensions aren't expressible in the Cypher vector call). Use
    # the model's own `status` computed field rather than re-deriving — one
    # fewer precedence copy to drift (adversary review note).
    if kind is not None:
        rows = [e for e in rows if e.kind == kind]
    if status is not None:
        rows = [e for e in rows if e.status == status]
    # `total` is the count of matches we retrieved (adversary review
    # minor-1): report it BEFORE the page trim so the FE's "X of N" is
    # honest. This is bounded by the oversample (limit*5) — a true
    # corpus-wide count isn't available from the vector index without a
    # second pass, and the semantic path is single-page (offset ignored),
    # so a retrieved-set count is the meaningful figure here.
    total = len(rows)
    rows = rows[:limit]
    return EntitiesListResponse(
        entities=rows, total=total, embedding_model=project.embedding_model,
    )


# ── T2.1 — Cast & Codex: spoiler-windowed status + facts ──────────────


class EntityStatusEntry(BaseModel):
    status: str  # 'active' | 'gone'
    from_order: int | None = None


class EntityStatusesResponse(BaseModel):
    # keyed by Entity.id; every requested id appears (default 'active').
    statuses: dict[str, EntityStatusEntry]
    # False when the chapter spoiler-window couldn't be resolved (fail-closed:
    # all 'active', no history) so the FE can show "reading position unknown".
    window_available: bool


# MUST be declared BEFORE `/entities/{entity_id}` or FastAPI captures
# `statuses` as an entity_id.
@entities_router.get("/entities/statuses", response_model=EntityStatusesResponse)
async def list_entity_statuses(
    project_id: UUID = Query(description="The knowledge project (book) whose cast to status."),
    before_chapter_id: UUID | None = Query(
        default=None,
        description=(
            "Spoiler-window the status THROUGH this book chapter (resolved "
            "server-side). Omitted / unresolvable → fail-closed (all 'active')."
        ),
    ),
    kind: str | None = Query(default=None, max_length=100),
    user_id: UUID = Depends(get_current_user),
    book_client: BookClient = Depends(get_book_client),
) -> EntityStatusesResponse:
    """T2.1 — batch `:EntityStatus` (`active|gone`) for a project's cast, windowed
    to `before_chapter_id`. Project-scoped (not a client id list) to avoid URL-length
    blowups on large casts. Multi-tenant: `user_id` from JWT scopes both reads."""
    before_order, available = await resolve_before_order(book_client, before_chapter_id)
    async with neo4j_session() as session:
        rows, _total = await list_entities_filtered(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            kind=kind,
            search=None,
            limit=ENTITIES_MAX_LIMIT,
            offset=0,
        )
        detail = await statuses_detail_at_order(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            entity_ids=[e.id for e in rows],
            at_order=before_order,
        )
    return EntityStatusesResponse(
        statuses={eid: EntityStatusEntry(**v) for eid, v in detail.items()},
        window_available=available,
    )


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


class EntityFactsResponse(BaseModel):
    facts: list[Fact]
    window_available: bool


@entities_router.get(
    "/entities/{entity_id}/facts",
    response_model=EntityFactsResponse,
)
async def list_entity_facts(
    entity_id: str = Path(min_length=1, max_length=200),
    before_chapter_id: UUID | None = Query(
        default=None,
        description=(
            "Spoiler-window the facts THROUGH this book chapter (by the fact's "
            "established-at order). Omitted / unresolvable → fail-closed (no facts)."
        ),
    ),
    user_id: UUID = Depends(get_current_user),
    book_client: BookClient = Depends(get_book_client),
) -> EntityFactsResponse:
    """T2.1 — the known-facts list (`decision|preference|milestone|negation`) ABOUT
    one entity, spoiler-windowed by `before_chapter_id`. A cross-user / unknown
    entity simply yields no facts (no existence leak). L2-loader filters apply
    (confidence ≥ 0.8, not pending) so quarantine candidates don't surface."""
    before_order, available = await resolve_before_order(book_client, before_chapter_id)
    async with neo4j_session() as session:
        facts = await list_facts_for_entity(
            session,
            user_id=str(user_id),
            entity_id=entity_id,
            before_order=before_order,
        )
    return EntityFactsResponse(facts=facts, window_available=available)


# ── C10 (C10-gap-report) — GET /projects/{id}/gaps ───────────────────
#
# ENTITY gaps: high-mention DISCOVERED (unanchored) entities with no
# glossary entry — "we found these in your book(s) but you haven't added
# them to the glossary yet." A THIN pass-through over the existing
# ``find_gap_candidates()`` repo function (KSA §3.4.E); the router adds
# NO new gap engine / scoring — `min_mentions` + `limit` flow straight
# through.
#
# LOCKED — KEEP SEPARATE from lore-enrichment's attribute-dimension gap
# feature (an entity missing a `history` field). That is a different
# query in a different service. This endpoint is ENTITY gaps only.
# (Two-distinct-gap-concepts lock.)


class GapReportResponse(BaseModel):
    """The gap-report payload. `gaps` are discovered (unanchored) entities
    above the `min_mentions` floor; `min_mentions` is echoed so the FE can
    label the active threshold."""

    gaps: list[Entity]
    total: int
    min_mentions: int


@entities_router.get(
    "/projects/{project_id}/gaps",
    response_model=GapReportResponse,
)
async def get_project_gaps(
    project_id: UUID = Path(
        description="The knowledge project (book) whose entity gaps to report.",
    ),
    min_mentions: int = Query(
        50,
        ge=0,
        description=(
            "Mention-count floor — only surface discovered entities mentioned "
            "at least this many times (filters one-off extraction noise). "
            "KSA §3.4.E starts at 50; the gap-report UI exposes this as a knob."
        ),
    ),
    limit: int = Query(
        100,
        ge=1,
        le=ENTITIES_MAX_LIMIT,
        description="Max number of gap candidates to return.",
    ),
    user_id: UUID = Depends(get_current_user),
) -> GapReportResponse:
    """C10 — entity Gap Report. Thin wrapper over ``find_gap_candidates()``:
    discovered (unanchored) entities with no glossary link, mentioned at
    least ``min_mentions`` times, ranked by the repo (mention_count DESC).

    Distinct from lore-enrichment's attribute-dimension gap feature.
    Multi-tenant: ``user_id`` from JWT scopes the Cypher MATCH; the route
    never accepts a user_id field, so a caller can't read another user's
    gaps.
    """
    async with neo4j_session() as session:
        gaps = await find_gap_candidates(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            min_mentions=min_mentions,
            limit=limit,
        )
    return GapReportResponse(gaps=gaps, total=len(gaps), min_mentions=min_mentions)


# ── C18 (G5) — GET /projects/{id}/subgraph ───────────────────────────
#
# The project-wide read-only subgraph for the C19 graph canvas. Today
# only a per-entity 1-hop read exists (`GET /entities/{id}`); the canvas
# needs a project-level n-hop, node-capped view. This generalises the
# 1-hop pattern into ``get_project_subgraph`` (relations repo) — a
# two-stage Cypher (deterministic top-N seed nodes IN the query, then
# only the edges between them) so a hub entity can never explode the
# result. Returns RAW `{nodes, edges}` — NO server-side layout (the
# canvas hand-rolls force/radial in C19). Read-only; partition-scoped
# (the Cypher binds BOTH user_id AND project_id — no cross-project /
# cross-user bleed).


@entities_router.get(
    "/projects/{project_id}/subgraph",
    response_model=Subgraph,
)
async def get_project_subgraph_endpoint(
    project_id: UUID = Path(
        description="The knowledge project (book) whose subgraph to render.",
    ),
    hops: int = Query(
        1,
        ge=1,
        le=SUBGRAPH_MAX_HOPS,
        description=(
            "Traversal depth for ego-expansion (only applies when `center` "
            f"is set). 1–{SUBGRAPH_MAX_HOPS}. Ignored for the project-wide "
            "view (no center)."
        ),
    ),
    limit: int = Query(
        200,
        ge=1,
        le=SUBGRAPH_MAX_NODE_CAP,
        description=(
            "Hard node cap. The endpoint returns at most this many nodes, "
            "selected deterministically (anchor_score DESC, mention_count "
            "DESC, id ASC) so the same query is stable across calls (powers "
            "the canvas expand / load-more). Edges are only those between "
            f"returned nodes. Max {SUBGRAPH_MAX_NODE_CAP}."
        ),
    ),
    center: str | None = Query(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Optional entity id to ego-expand from — returns the `hops`-"
            "bounded neighbourhood of this entity instead of the project-"
            "wide top-N. Powers the canvas click-to-expand. A center that "
            "doesn't exist / is cross-partition yields an empty subgraph."
        ),
    ),
    user_id: UUID = Depends(get_current_user),
) -> Subgraph:
    """C18 (G5) — read-only project subgraph for the C19 canvas.

    Returns `{nodes, edges}` for the `(user_id, project_id)` partition.
    Multi-tenant + multi-project safety: `user_id` from JWT + the route
    `project_id` are BOTH bound in the Cypher; the route never accepts a
    user_id field, so a caller can't read another user's — or another
    project's — graph. The node cap is enforced IN the query
    (deterministic ORDER + LIMIT on the seed-node collection), never
    post-filtered, so a hub entity can't OOM Neo4j.

    Read-only: returns raw nodes + edges, no server-side layout. Editing
    reuses the existing entity/relation dialogs (C19).
    """
    async with neo4j_session() as session:
        subgraph = await get_project_subgraph(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            hops=hops,
            limit=limit,
            center=center,
        )
    return subgraph


@entities_router.get(
    "/worlds/{world_id}/subgraph",
    response_model=Subgraph,
)
async def get_world_subgraph_endpoint(
    world_id: UUID = Path(
        description="The world whose member books' canon graphs to roll up.",
    ),
    limit: int = Query(
        200,
        ge=1,
        le=SUBGRAPH_MAX_NODE_CAP,
        description=(
            "Hard node cap applied to the UNION across the world's projects. "
            "Nodes are selected by the same global order as the per-project "
            f"view (anchor_score DESC, mention_count DESC, id ASC). Max "
            f"{SUBGRAPH_MAX_NODE_CAP}."
        ),
    ),
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
    book: BookClient = Depends(get_book_client),
) -> Subgraph:
    """G4 (W2) — the world rollup graph: a UNION of each member book's canon
    subgraph plus the world-level (bible) project.

    Membership is resolved server-side via book-service's internal
    ``/internal/worlds/{id}/books`` (owner-scoped by ``user_id`` → a world the
    caller doesn't own is a uniform 404). We never trust a client-supplied book
    or project list. Each member book's canonical project is resolved via
    ``get_by_book`` (which excludes ``is_derivative`` — dị bản branches stay out
    of the canon rollup and surface in the C28 living-world tree instead).

    The union is N isolated per-(user_id, project_id) reads stitched in app code
    — no cross-partition Cypher, no cross-user/cross-project bleed (a project the
    user doesn't own contributes nothing). The result is a forest of per-book
    components, tagged by ``source_project_id`` so the FE legends each book.
    """
    try:
        project_ids = await resolve_world_project_ids(
            world_id=world_id, user_id=user_id, repo=repo, book=book
        )
    except WorldNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="world not found"
        )
    except BookServiceUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="world membership unavailable",
        )

    async with neo4j_session() as session:
        return await get_world_subgraph(
            session,
            user_id=str(user_id),
            project_ids=project_ids,
            limit=limit,
        )


# ── C13 — GET /projects/{id}/glossary-entity-stats ───────────────────
#
# THIN pass-through to glossary-service's new `/internal/books/{id}/entities/
# stats` (the FE cannot reach glossary `/internal` directly — same reason the
# C9 promote flow proxies through here). Powers the build-wizard Step-2 auto-pin
# suggestion banner: per-entity mention-span + coverage so the FE can suggest
# pinning the sparse-but-long-reaching entities. Read-only; user-scoped via JWT;
# resolves the project's book_id server-side (the FE never sees glossary ids
# until this returns them). No new gap/scoring engine — pure proxy.


class GlossaryEntityStat(BaseModel):
    entity_id: str
    name: str
    kind: str
    mention_count: int
    first_chapter_index: int | None = None
    last_chapter_index: int | None = None
    coverage_pct: float


class GlossaryEntityStatsResponse(BaseModel):
    items: list[GlossaryEntityStat]
    chapter_count: int


@entities_router.get(
    "/projects/{project_id}/glossary-entity-stats",
    response_model=GlossaryEntityStatsResponse,
)
async def get_glossary_entity_stats(
    project_id: UUID = Path(
        description="The knowledge project whose glossary entity stats to report.",
    ),
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
) -> GlossaryEntityStatsResponse:
    """C13 — proxy the glossary mention-span/coverage stats for the build
    wizard's auto-pin banner. 404 if the project doesn't exist for this user;
    422 ``no_book`` if the project has no linked book; on a glossary outage,
    returns an empty list (the FE degrades to manual pinning, never blocks)."""
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status_codes.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    if project.book_id is None:
        raise HTTPException(
            status_code=status_codes.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error_code": "no_book",
                "message": "the project has no linked book; pinning needs a book",
            },
        )
    raw = await glossary_client.get_entity_stats(project.book_id)
    if raw is None:
        return GlossaryEntityStatsResponse(items=[], chapter_count=0)
    return GlossaryEntityStatsResponse(
        items=[GlossaryEntityStat.model_validate(it) for it in raw.get("items", [])],
        chapter_count=int(raw.get("chapter_count", 0)),
    )


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


# ── T2.5 World Map — manual entity authoring ──────────────────────────

# S7-1 — the human create path gates ``kind`` to ``AUTHORABLE_KINDS`` (the
# ONE home, defined in neo4j_repos/entities.py). The old local set used the
# ``faction`` misnomer and omitted ``organization``/``item`` — a create form
# built to the 7-value browse filter silently 422'd 4 of them. The set is now
# shared with the agent gate (KgCreateNodeArgs) so create == agent (INV-parity).
class CreateEntityRequest(BaseModel):
    """T2.5 — create a user-authored entity (e.g. a World Map place). Idempotent:
    re-creating the same (name, kind) in a project returns the existing node
    (``merge_entity`` dedups on a canonical_id hash), so a later extraction of
    the same place converges on this node rather than duplicating it."""

    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _validate(self) -> "CreateEntityRequest":
        if not self.name.strip():
            raise ValueError("name must not be blank")
        if self.kind not in AUTHORABLE_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(AUTHORABLE_KINDS)}"
            )
        return self


@entities_router.post(
    "/entities",
    response_model=Entity,
    status_code=status.HTTP_201_CREATED,
)
async def create_entity_endpoint(
    body: CreateEntityRequest,
    user_id: UUID = Depends(get_current_user),
) -> Entity:
    """T2.5 — create a user-authored entity (World Map "+ add place").

    Multi-tenant: the node is written under the JWT ``user_id`` (threaded into
    ``merge_entity``'s Cypher), so a caller can only ever create entities in
    their own scope — ``project_id`` is just a tag on the user's own node, never
    a cross-tenant handle. Idempotent: the same (name, kind) in the same project
    returns the same node (no duplicate places). ``source_type='manual'`` +
    confidence 1.0 mark it user-asserted.
    """
    async with neo4j_session() as session:
        entity = await merge_entity(
            session,
            user_id=str(user_id),
            project_id=str(body.project_id),
            name=body.name.strip(),
            kind=body.kind,
            source_type="manual",
            confidence=1.0,
            provenance="human_authored",
        )
    logger.info(
        "T2.5: user created entity user_id=%s project_id=%s kind=%s id=%s",
        user_id, body.project_id, body.kind, entity.id,
    )
    return entity


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
            updated, before = await update_entity_fields(
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
    # Phase B — capture the correction (best-effort, AFTER the Neo4j write
    # committed; cross-store §6.6 → never fails the PATCH). diff_class
    # (kind-change vs boundary) is derived downstream from before/after.
    await emit_correction(
        event_type=ENTITY_CORRECTED,
        aggregate_id=entity_id,
        payload=entity_correction_payload(
            user_id=str(user_id),
            project_id=updated.project_id,
            book_id=None,
            target_id=entity_id,
            op="update",
            # Route `before` through entity_snapshot for ONE canonical shape
            # (adversary subB F2 — match the after/archive snapshots).
            before=(
                entity_snapshot(before.get("name"), before.get("kind"), before.get("aliases"))
                if before
                else None
            ),
            after=entity_snapshot(updated.name, updated.kind, updated.aliases),
            actor_id=str(user_id),
        ),
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


# ── C9 — POST /entities/{id}/promote ────────────────────────────────


def _draft_glossary_id(propose_resp: dict | None) -> str | None:
    """Extract the anchorable glossary entity_id from an ``extract-entities``
    response. Returns None when the batch produced no usable id.

    The single-entity promote yields exactly one proposal whose ``status``
    is one of ``created`` / ``updated`` / ``skipped``:

      - ``created``  — a fresh ai-suggested DRAFT (the common promote case).
      - ``updated``  — the name already named an existing glossary entry and
                       this write touched it; anchor to that entry.
      - ``skipped``  — either (a) the name resolves to an EXISTING glossary
                       entity but no new attribute was written (a no-op
                       merge — already curated; still anchorable, the row
                       carries its ``entity_id``), or (b) a tombstoned
                       ``ai-rejected`` name (``skip_reason='tombstoned'`` —
                       the user explicitly rejected it; NOT anchorable).

    So we accept any non-empty ``entity_id`` EXCEPT a tombstoned skip. This
    makes promote anchor a discovered entity to an already-existing glossary
    entry (the "glossary entry authored that matches a discovered entity"
    path) instead of hard-failing on the merge-no-op case.
    """
    if not propose_resp:
        return None
    items = propose_resp.get("entities") or []
    if not items:
        return None
    first = items[0]
    if first.get("skip_reason") == "tombstoned":
        return None
    gid = first.get("entity_id")
    return gid or None


@entities_router.post(
    "/entities/{entity_id}/promote",
    response_model=Entity,
)
async def promote_entity(
    entity_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
) -> Entity:
    """C9 (C9-promote-flow LOCKED) — promote a DISCOVERED entity into the
    glossary curation flywheel.

    Two server-side steps, in order (the FE cannot reach glossary's
    ``/internal/extract-entities`` and partial-failure handling is safest
    in one request):

      1. create a glossary **DRAFT** (``status='draft'``, tag
         ``ai-suggested``) from the entity's name/kind/aliases via
         ``GlossaryClient.propose_entities`` — NEVER an active entity; the
         human reviews + promotes it in glossary's existing AI-suggestions
         inbox (integrate, don't duplicate).
      2. anchor the knowledge entity to that draft
         (``glossary_entity_id`` + ``anchor_score=1.0``) via
         ``link_to_glossary`` → its derived status flips to ``canonical``.

    Guards:
      - 404 — entity missing / cross-user (KSA §6.4 anti-existence-leak).
      - 409 ``already_anchored`` — entity already has a ``glossary_entity_id``;
        re-promoting would double-draft.
      - 422 ``no_book`` — the project has no ``book_id``; nowhere to write the
        glossary draft.
      - 502 ``glossary_draft_failed`` — the draft-create returned nothing
        anchorable (glossary down/4xx, or the name was tombstoned); the
        entity is NOT anchored.
      - 502 ``anchor_failed`` — the draft was created but the anchor write
        missed (stale id / race). The draft persists; a retry is safe —
        ``propose_entities`` dedups by name and ``link_to_glossary`` is
        idempotent (no orphaned/duplicate draft).
    """
    user_id_str = str(user_id)

    async with neo4j_session() as session:
        entity = await get_entity(
            session, user_id=user_id_str, canonical_id=entity_id,
        )
        if entity is None:
            raise HTTPException(
                status_code=status_codes.HTTP_404_NOT_FOUND,
                detail="entity not found",
            )
        # Only a discovered entity is promotable — already-anchored ⇒ 409
        # (no double-draft on a re-click). Archived entities carry no
        # glossary_entity_id, so this also blocks promoting an archived one
        # only if it was previously anchored (it never is — archive nulls
        # the FK), which is the correct conservative behavior.
        if entity.glossary_entity_id is not None:
            raise HTTPException(
                status_code=status_codes.HTTP_409_CONFLICT,
                detail={
                    "error_code": "already_anchored",
                    "message": "entity is already anchored to a glossary entry",
                },
            )

        # Resolve the project's book_id — the glossary draft must be written
        # under a book.
        project = None
        if entity.project_id:
            try:
                project = await projects_repo.get(user_id, UUID(entity.project_id))
            except ValueError:
                project = None
        book_id = getattr(project, "book_id", None) if project else None
        if book_id is None:
            raise HTTPException(
                status_code=status_codes.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error_code": "no_book",
                    "message": (
                        "project has no linked book — cannot create a glossary "
                        "draft"
                    ),
                },
            )

        # Step 1 — create the ai-suggested DRAFT in glossary. Mirror the
        # KG→glossary writeback payload shape (kind normalized to a glossary
        # kind_code; alias variants minus the canonical name). Compare on the
        # CANONICAL form (case/accent/whitespace-folded) so a display-cased
        # variant of the name itself doesn't leak in as a redundant alias —
        # `entity.canonical_name` is already folded, `aliases` carry display
        # casing (adversary MINOR).
        aliases = [
            a
            for a in entity.aliases
            if a and canonicalize_entity_name(a) != entity.canonical_name
        ]
        attributes: dict = {"aliases": aliases} if aliases else {}
        propose_resp = await glossary_client.propose_entities(
            book_id,
            entities=[
                {
                    "kind_code": normalize_kind_for_anchor_lookup(entity.kind),
                    "name": entity.canonical_name,
                    "attributes": attributes,
                }
            ],
            default_tags=[WRITEBACK_TAG],
            park_unknown_kinds=False,
        )
        glossary_entity_id = _draft_glossary_id(propose_resp)
        if glossary_entity_id is None:
            raise HTTPException(
                status_code=status_codes.HTTP_502_BAD_GATEWAY,
                detail={
                    "error_code": "glossary_draft_failed",
                    "message": (
                        "could not create a glossary draft for this entity "
                        "(glossary unavailable or the name was previously "
                        "rejected)"
                    ),
                },
            )

        # Step 2 — anchor the knowledge entity to the new draft.
        anchored = await link_to_glossary(
            session,
            user_id=user_id_str,
            canonical_id=entity.id,
            glossary_entity_id=glossary_entity_id,
            name=entity.name,
            kind=entity.kind,
            aliases=entity.aliases,
        )

    if anchored is None:
        # The draft was created but the anchor write missed (stale id /
        # race). The draft persists; the FE may retry safely — propose
        # dedups by name (no second draft) and link_to_glossary is
        # idempotent.
        raise HTTPException(
            status_code=status_codes.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "anchor_failed",
                "message": (
                    "glossary draft was created but anchoring the entity "
                    "failed — retry is safe (no duplicate draft will be made)"
                ),
                "glossary_entity_id": glossary_entity_id,
            },
        )

    logger.info(
        "C9: promoted entity user_id=%s entity_id=%s → glossary_entity_id=%s",
        user_id, entity_id, glossary_entity_id,
    )
    return anchored


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
    # Phase B C3 — emit a merge correction (best-effort, §6.6). target_id is the
    # surviving TARGET; before = the (now-deleted) SOURCE snapshot captured
    # pre-merge; after = the merged target. diff_class derives `merge` from op.
    await emit_correction(
        event_type=ENTITY_CORRECTED,
        aggregate_id=other_id,
        payload=entity_correction_payload(
            user_id=str(user_id),
            project_id=target.project_id,
            book_id=None,
            target_id=other_id,
            op="merge",
            before=(
                entity_snapshot(source.name, source.kind, source.aliases)
                if source is not None
                else None
            ),
            after=entity_snapshot(target.name, target.kind, target.aliases),
            actor_id=str(user_id),
        ),
    )
    return EntityMergeResponse(target=target, aliases_redirected=aliases_redirected)
