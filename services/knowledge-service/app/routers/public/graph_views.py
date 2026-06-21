"""KG graph-views + temporal-read public router (epic 2026-06-20, lane LD).

Three surfaces (contract: contracts/api/knowledge-service/views.yaml):

  * **Views CRUD** — `/v1/kg/projects/{project_id}/views[/{code}]`. Per-user
    named `{edge_type_codes[], node_kind_codes[]}` lenses over a project graph.
    Owner-scoped: `owner == caller` (the JWT user). A user only ever sees /
    edits their OWN views, even in a shared project (spec §3.3, §10-D4).

  * **Graph read** — `GET /v1/kg/projects/{project_id}/graph?view=&as_of_chapter=`.
    Returns nodes+edges filtered by the view lens AND the temporal as-of-chapter
    predicate (spec §3.6). **View-gated on the project** via
    `require_project_grant(VIEW)` (resolve-to-owner): a book collaborator with
    a View grant on the project's book reads the OWNER's graph. A view that
    references a deprecated edge-type is flagged in `warnings` (spec §10-A4).

  * **Edge timeline** — `GET /v1/kg/entities/{entity_id}/edges/{edge_type}/timeline`.
    The ordered temporal instance chain for one entity + edge type (e.g. a
    drive arc revenge→seek_dao→transcendence). Grant gate: the entity is
    resolved CALLER-scoped (the universal Neo4j read pattern in this service —
    every `:Entity` read binds the caller's `$user_id`); its project is then
    re-confirmed under a VIEW grant. See `_resolve_entity_project_grant`.

Temporal model (spec §3.6): edge `valid_from`/`valid_to` are **chapter
ordinals (int)**; an edge shows at chapter N when `valid_from <= N AND
(valid_to IS NULL OR valid_to > N)`; invariant edges (no `valid_from`) always
show; `as_of_chapter` omitted = latest (all open). The predicate + view-scope
are pure (`app.ontology.view_filter`) and unit-tested; the Cypher only fetches.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field

import asyncpg

from app.auth.grant_deps import GrantLevel, require_project_grant
from app.clients.grant_client import GrantClient
from app.db.neo4j import neo4j_session
from app.db.neo4j_helpers import run_read
from app.db.ontology_models import GraphView
from app.db.pool import get_knowledge_pool
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.graph_views import GraphViewsRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.ontology.view_filter import (
    build_view_scope,
    deprecated_edge_warnings,
    edge_visible_at,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/kg",
    tags=["kg-views"],
    dependencies=[Depends(get_current_user)],
)

# Slugify cap mirrors SchemaCode (1..120) — the view `code` is the same slug
# space as schema codes.
_CODE_MAX = 120
_NAME_MAX = 200


# ── DI ────────────────────────────────────────────────────────────────────
def get_graph_views_repo() -> GraphViewsRepo:
    """GraphViewsRepo on the shared knowledge pool (mirrors get_projects_repo).
    Tests override this dep with an in-memory fake."""
    return GraphViewsRepo(get_knowledge_pool())


def get_graph_schemas_repo() -> GraphSchemasRepo:
    return GraphSchemasRepo(get_knowledge_pool())


# ── request / response models ─────────────────────────────────────────────
class ViewCreate(BaseModel):
    code: str | None = Field(default=None, max_length=_CODE_MAX)
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    description: str = ""
    edge_type_codes: list[str] = Field(default_factory=list)
    node_kind_codes: list[str] = Field(default_factory=list)


class ViewListResponse(BaseModel):
    items: list[GraphView]


class GraphNode(BaseModel):
    id: str
    kind: str
    name: str
    glossary_entity_id: str | None = None


class GraphEdge(BaseModel):
    edge_type: str
    source_id: str
    target_id: str
    valid_from: int | None = None
    valid_to: int | None = None
    schema_version: int | None = None


class GraphSlice(BaseModel):
    as_of_chapter: int | None = None
    view: str | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TimelineInstance(BaseModel):
    target_id: str
    target_label: str | None = None
    valid_from: int | None = None
    valid_to: int | None = None
    evidence_chapter_id: str | None = None
    schema_version: int | None = None


class EdgeTimeline(BaseModel):
    entity_id: str
    edge_type: str
    instances: list[TimelineInstance] = Field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────
def _slugify(name: str) -> str:
    """Derive a stable code slug from a name when `code` is omitted: lower,
    non-alnum runs → single `_`, trimmed. Capped to `_CODE_MAX`. Empty result
    (e.g. all-punctuation name) → 422 at the call site."""
    out: list[str] = []
    prev_us = False
    for ch in name.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        elif not prev_us:
            out.append("_")
            prev_us = True
    slug = "".join(out).strip("_")
    return slug[:_CODE_MAX]


def _coerce_ordinal(value: Any) -> int | None:
    """Coerce a Neo4j temporal-ordinal property to an int (or None).

    `valid_from`/`valid_to` are chapter ordinals stored as ints. A legacy
    edge may still carry a datetime in `valid_until` (the pre-ontology
    timestamp model) — that is NOT an ordinal, so we coerce only int-like
    values and treat anything non-int as None (invariant / open)."""
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass — exclude it
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


# Graph-read Cypher: every active :RELATES_TO edge in the (owner, project)
# partition, with its temporal props + both endpoint nodes. Multi-tenant:
# binds $user_id (K11.4) AND $project_id on every node. valid_until IS NULL
# keeps superseded (user-corrected) edges out; the chapter-ordinal temporal
# filter (valid_from/valid_to) is applied in PYTHON via edge_visible_at so the
# predicate is pure + unit-tested. predicate IS the edge_type code.
_GRAPH_READ_CYPHER = """
MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)
WHERE subj.user_id = $user_id
  AND obj.user_id = $user_id
  AND subj.project_id = $project_id
  AND obj.project_id = $project_id
  AND r.user_id = $user_id
  AND r.valid_until IS NULL
  AND subj.archived_at IS NULL
  AND obj.archived_at IS NULL
RETURN properties(r) AS rel,
       properties(subj) AS subj,
       properties(obj) AS obj
ORDER BY r.predicate ASC, subj.id ASC, obj.id ASC
LIMIT $limit
"""


def _node_dict(props: dict[str, Any]) -> GraphNode:
    return GraphNode(
        id=str(props.get("id", "")),
        kind=str(props.get("kind", "")),
        name=str(props.get("name", "")),
        glossary_entity_id=props.get("glossary_entity_id"),
    )


def build_graph_slice(
    records: list[dict[str, Any]],
    *,
    view: GraphView | None,
    as_of_chapter: int | None,
    deprecated_edge_codes: list[str],
    view_code: str | None,
) -> GraphSlice:
    """Pure assembly of a `GraphSlice` from raw `{rel, subj, obj}` records.

    Applies BOTH filters: the view lens (edge-type + node-kind allow-sets;
    empty facet = identity) and the temporal as-of predicate. A node only
    appears if it is the endpoint of at least one surviving edge AND passes
    the node-kind facet. Extracted from the handler so the filter logic is
    unit-testable without a live Neo4j.
    """
    scope = build_view_scope(view)
    edges: list[GraphEdge] = []
    nodes: dict[str, GraphNode] = {}
    for rec in records:
        rel = rec["rel"]
        subj = rec["subj"]
        obj = rec["obj"]
        edge_type = str(rel.get("predicate", ""))
        if not scope.allows_edge_type(edge_type):
            continue
        subj_kind = str(subj.get("kind", ""))
        obj_kind = str(obj.get("kind", ""))
        # Node-kind facet: BOTH endpoints must pass — an edge whose endpoint
        # falls outside the lens is not part of this lens's slice.
        if not (scope.allows_node_kind(subj_kind) and scope.allows_node_kind(obj_kind)):
            continue
        vf = _coerce_ordinal(rel.get("valid_from"))
        vt = _coerce_ordinal(rel.get("valid_to"))
        if not edge_visible_at(vf, vt, as_of_chapter):
            continue
        edges.append(
            GraphEdge(
                edge_type=edge_type,
                source_id=str(subj.get("id", "")),
                target_id=str(obj.get("id", "")),
                valid_from=vf,
                valid_to=vt,
                schema_version=_coerce_ordinal(rel.get("schema_version")),
            )
        )
        sn = _node_dict(subj)
        on = _node_dict(obj)
        nodes.setdefault(sn.id, sn)
        nodes.setdefault(on.id, on)
    warnings = deprecated_edge_warnings(view, deprecated_edge_codes)
    return GraphSlice(
        as_of_chapter=as_of_chapter,
        view=view_code,
        nodes=list(nodes.values()),
        edges=edges,
        warnings=warnings,
    )


# Timeline Cypher: every instance (active OR superseded) of one edge_type from
# one entity, ordered by the temporal opening ordinal. We do NOT filter
# valid_until here — the timeline is the FULL arc, including closed instances
# (that is the point: revenge→seek_dao→transcendence). Predicate is bound as a
# parameter (never interpolated). Multi-tenant via $user_id (K11.4).
_TIMELINE_CYPHER = """
MATCH (subj:Entity {id: $entity_id})-[r:RELATES_TO]->(obj:Entity)
WHERE subj.user_id = $user_id
  AND obj.user_id = $user_id
  AND r.user_id = $user_id
  AND r.predicate = $edge_type
RETURN properties(r) AS rel, properties(obj) AS obj
ORDER BY coalesce(r.valid_from, 2147483647) ASC, obj.id ASC
LIMIT $limit
"""


def build_timeline(
    entity_id: str,
    edge_type: str,
    records: list[dict[str, Any]],
) -> EdgeTimeline:
    """Pure assembly of an `EdgeTimeline` from `{rel, obj}` records."""
    instances: list[TimelineInstance] = []
    for rec in records:
        rel = rec["rel"]
        obj = rec["obj"]
        instances.append(
            TimelineInstance(
                target_id=str(obj.get("id", "")),
                target_label=obj.get("name"),
                valid_from=_coerce_ordinal(rel.get("valid_from")),
                valid_to=_coerce_ordinal(rel.get("valid_to")),
                evidence_chapter_id=rel.get("source_chapter"),
                schema_version=_coerce_ordinal(rel.get("schema_version")),
            )
        )
    return EdgeTimeline(entity_id=entity_id, edge_type=edge_type, instances=instances)


async def _records(result: Any) -> list[dict[str, Any]]:
    """Drain a neo4j async result into a list of `{key: dict}` records, so the
    pure builders never touch the live driver cursor."""
    out: list[dict[str, Any]] = []
    async for rec in result:
        out.append({k: dict(rec[k]) for k in rec.keys()})
    return out


async def _deprecated_edge_codes(repo: GraphSchemasRepo, project_id: str) -> list[str]:
    """The edge-type codes the project's resolved schema has deprecated.

    The default `resolve_for_project` drops deprecated edge-types, so to flag a
    view that references one (§10-A4) we read the active project schema's tree
    WITH deprecated rows and diff. Best-effort: any read hiccup yields no
    warnings rather than failing the graph read."""
    try:
        async with repo._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT schema_id FROM kg_graph_schemas
                WHERE scope = 'project' AND scope_id = $1 AND deprecated_at IS NULL
                ORDER BY updated_at DESC, schema_id DESC LIMIT 1
                """,
                project_id,
            )
            if row is None:
                return []
            rows = await conn.fetch(
                """
                SELECT code FROM kg_edge_types
                WHERE schema_id = $1 AND deprecated_at IS NOT NULL
                """,
                row["schema_id"],
            )
        return [r["code"] for r in rows]
    except (asyncpg.PostgresError, OSError):  # pragma: no cover - defensive
        logger.warning("deprecated-edge lookup failed for project %s", project_id, exc_info=True)
        return []


async def _resolve_entity_project_grant(
    entity_id: str,
    caller: UUID,
    gc: GrantClient,
    projects_repo: ProjectsRepo,
) -> tuple[str, UUID]:
    """Grant-gate the timeline route (which carries NO project_id in its path)
    and resolve-to-owner so a book grantee can read the OWNER's entity timeline.

    D-KG-LD-GRANTEE-TIMELINE — the entity is looked up by its globally-unique
    `id` WITHOUT a user filter (`get_entity_by_id_any_owner`; safe because
    `Entity.id` is globally unique, so no cross-tenant collision). That yields
    the entity's OWNER `user_id` + `project_id`. We then apply the SAME gate as
    `grant_deps._resolve_owner`:

      * `caller == owner` → ok (owner self-read);
      * else resolve the OWNER's project-book grant — non-grantee → **404**
        (no existence oracle), under-VIEW → **403**.

    A missing entity (or one with no project/owner) collapses to 404 — uniform
    with every other entity route, no existence leak.

    Returns ``(project_id, owner_user_id)``. The timeline query is bound to the
    **owner** (the graph partition is owner-scoped), never the caller — parity
    with the graph-read route, which carries project_id and resolves-to-owner
    via `require_project_grant`. A grantee of book A therefore reads the owner's
    timeline for an entity in book A, but CANNOT reach an entity whose project
    book they hold no grant on (404).
    """
    from app.db.neo4j_repos.entities import get_entity_by_id_any_owner

    async with neo4j_session() as session:
        ent = await get_entity_by_id_any_owner(session, entity_id)
    if ent is None or not ent.project_id or not ent.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    project_id = ent.project_id
    owner = UUID(ent.user_id)
    # Owner self-read short-circuits (mirrors _resolve_owner caller==owner). The
    # owner is the graph-partition authority for its own entity.
    if caller == owner:
        return project_id, owner
    # Cross-owner: re-confirm a VIEW grant on the OWNER's project book.
    # project_meta wants a UUID; knowledge project ids ARE uuids. A non-uuid
    # project_id (legacy/global) has no resolvable book → owner-only → 404 for a
    # non-owner caller (fail closed, no oracle).
    try:
        pid_uuid = UUID(project_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    meta = await projects_repo.project_meta(pid_uuid)
    if meta is None:
        # Owner's entity references a project with no row → no book to resolve a
        # grant on → owner-only → 404 for a non-owner.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    _meta_owner, book_id = meta
    if book_id is None:
        # Book-less project → owner-only (R1): a non-owner caller cannot reach.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    lvl = await gc.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    if not lvl.at_least(GrantLevel.VIEW):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient access")
    # Bind the timeline to the entity OWNER (the graph partition), not the
    # caller — this is the cross-tenant read the lane closes.
    return project_id, owner


# ── Views CRUD (owner == caller) ──────────────────────────────────────────
@router.get("/projects/{project_id}/views", response_model=ViewListResponse)
async def list_views(
    project_id: UUID = Path(description="knowledge project id (uuid)"),
    user_id: UUID = Depends(get_current_user),
    repo: GraphViewsRepo = Depends(get_graph_views_repo),
) -> ViewListResponse:
    """List the caller's views in a project (owner-scoped — never another
    user's). No project grant check needed: a view is the caller's OWN
    per-user data, scoped by `user_id`; it reveals nothing about the project
    graph itself. `project_id` is UUID-typed (like the CRUD writes) so the
    stored value and the list query canonicalize identically — a non-canonical
    (e.g. uppercase) UUID can't make a created view invisible to list."""
    items = await repo.list(user_id, str(project_id))
    return ViewListResponse(items=items)


@router.post(
    "/projects/{project_id}/views",
    response_model=GraphView,
    status_code=status.HTTP_201_CREATED,
)
async def create_view(
    body: ViewCreate,
    project_id: UUID = Path(description="knowledge project id (uuid)"),
    user_id: UUID = Depends(get_current_user),
    repo: GraphViewsRepo = Depends(get_graph_views_repo),
    # D-KG-LD-VIEWS-GRANT — parity with the LF kg_view_upsert tool: a VIEW grant
    # on the project is required to write a view for it (owner OR a >=VIEW book
    # grantee). The repo still owner-scopes the row to the caller; this gate stops
    # a caller minting views against a project they can't reach. 404/403 via the
    # gate. (list_views stays ungated — it reveals only the caller's own rows.)
    _grant: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
) -> GraphView:
    """Create a view owned by the caller. `code` defaults to a slug of `name`.
    409 on a duplicate `(project_id, user_id, code)`."""
    code = (body.code or "").strip() or _slugify(body.name)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="could not derive a view code from name; provide an explicit code",
        )
    if len(code) > _CODE_MAX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"code exceeds {_CODE_MAX} chars",
        )
    try:
        return await repo.create(
            user_id,
            str(project_id),
            code=code,
            name=body.name,
            description=body.description,
            edge_type_codes=body.edge_type_codes,
            node_kind_codes=body.node_kind_codes,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a view with code '{code}' already exists for you in this project",
        )


@router.put("/projects/{project_id}/views/{code}", response_model=GraphView)
async def upsert_view(
    body: ViewCreate,
    response: Response,
    project_id: UUID = Path(description="knowledge project id (uuid)"),
    code: str = Path(min_length=1, max_length=_CODE_MAX),
    user_id: UUID = Depends(get_current_user),
    repo: GraphViewsRepo = Depends(get_graph_views_repo),
    # D-KG-LD-VIEWS-GRANT — VIEW grant required (see create_view).
    _grant: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
) -> GraphView:
    """Upsert a view by code (owner only). 200 on update, 201 on create. The
    path `code` is authoritative — a `code` in the body is ignored."""
    view, created = await repo.upsert(
        user_id,
        str(project_id),
        code=code,
        name=body.name,
        description=body.description,
        edge_type_codes=body.edge_type_codes,
        node_kind_codes=body.node_kind_codes,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return view


@router.delete(
    "/projects/{project_id}/views/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_view(
    project_id: UUID = Path(description="knowledge project id (uuid)"),
    code: str = Path(min_length=1, max_length=_CODE_MAX),
    user_id: UUID = Depends(get_current_user),
    repo: GraphViewsRepo = Depends(get_graph_views_repo),
    # D-KG-LD-VIEWS-GRANT — VIEW grant required (see create_view).
    _grant: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
) -> None:
    """Hard-delete the caller's view. 404 if the caller owns no such view."""
    deleted = await repo.delete(user_id, str(project_id), code)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="view not found")


# ── Graph read (View-gated on the project) ────────────────────────────────
@router.get("/projects/{project_id}/graph", response_model=GraphSlice)
async def read_graph(
    project_id: UUID = Path(description="knowledge project id (uuid)"),
    view: str | None = Query(default=None, description="view code; omit for the whole schema"),
    as_of_chapter: int | None = Query(default=None, ge=0, description="chapter ordinal; omit for latest"),
    limit: int = Query(default=500, ge=1, le=2000),
    owner: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    caller: UUID = Depends(get_current_user),
    views_repo: GraphViewsRepo = Depends(get_graph_views_repo),
    schemas_repo: GraphSchemasRepo = Depends(get_graph_schemas_repo),
) -> GraphSlice:
    """Read the project graph filtered by `view` + `as_of_chapter`.

    **Grant gate:** `require_project_grant(VIEW)` resolves the project's
    (owner, book) and authorizes the caller (owner OR a >=VIEW book grantee),
    returning the project OWNER. The Neo4j query then runs as that owner — the
    graph partition is owner-scoped, so a grantee correctly reads the owner's
    graph (mirrors `projects.py` GET). A missing project / non-grantee → 404.

    The view (if supplied) is resolved as the CALLER's own lens (views are
    per-user; a grantee uses THEIR view over the owner's graph). An unknown
    view code → 404. Deprecated edge-types the view references are flagged in
    `warnings` (§10-A4).
    """
    project_str = str(project_id)
    selected_view: GraphView | None = None
    if view is not None:
        selected_view = await views_repo.get(caller, project_str, view)
        if selected_view is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="view not found")

    async with neo4j_session() as session:
        result = await run_read(
            session,
            _GRAPH_READ_CYPHER,
            user_id=str(owner),
            project_id=project_str,
            limit=limit,
        )
        records = await _records(result)

    deprecated = await _deprecated_edge_codes(schemas_repo, project_str)
    return build_graph_slice(
        records,
        view=selected_view,
        as_of_chapter=as_of_chapter,
        deprecated_edge_codes=deprecated,
        view_code=view,
    )


# ── Edge timeline (View-gated on the entity's project) ────────────────────
@router.get(
    "/entities/{entity_id}/edges/{edge_type}/timeline",
    response_model=EdgeTimeline,
)
async def read_edge_timeline(
    entity_id: str = Path(min_length=1, max_length=200),
    edge_type: str = Path(min_length=1, max_length=120),
    limit: int = Query(default=500, ge=1, le=2000),
    caller: UUID = Depends(get_current_user),
    gc: GrantClient = Depends(get_grant_client),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> EdgeTimeline:
    """The temporal instance chain for one entity + edge type (e.g. a drive
    arc). View-gated on the entity's project (see
    `_resolve_entity_project_grant`), which resolves-to-owner so a VIEW-grantee
    of the owner's book reads the OWNER's timeline (D-KG-LD-GRANTEE-TIMELINE).
    Returns the FULL arc — active AND superseded instances — ordered by opening
    chapter ordinal."""
    _project_id, owner = await _resolve_entity_project_grant(
        entity_id, caller, gc, projects_repo
    )
    # Bind to the resolved OWNER, not the caller — the graph partition is
    # owner-scoped, so a grantee correctly reads the owner's arc (mirrors the
    # graph-read route). Binding the caller here would re-introduce the 404 the
    # lane fixes (caller != owner ⇒ no rows).
    async with neo4j_session() as session:
        result = await run_read(
            session,
            _TIMELINE_CYPHER,
            user_id=str(owner),
            entity_id=entity_id,
            edge_type=edge_type,
            limit=limit,
        )
        records = await _records(result)
    return build_timeline(entity_id, edge_type, records)
