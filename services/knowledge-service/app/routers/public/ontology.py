"""KG graph-ontology public router (epic 2026-06-20, lane LC).

Fills the L1-preregistered stub with the tiered graph-schema surface:
list/read, resolved-schema read, adopt (copy-down, M1 adopt-gate), sync
(diff/apply), and per-tier child CRUD (additive + deprecate-only, M3).

Contract: contracts/api/knowledge-service/ontology.yaml.

Tenancy (CLAUDE.md › User Boundaries):
  * **System tier** is read-only over this API. Reads serve everyone; writes
    (PATCH/DELETE/CRUD) on a system row → 403; system *create* → 501 placeholder.
  * **User tier** writes are owner-scoped (`scope_id == caller`).
  * **Project tier** writes are Manage-gated via `require_project_grant(MANAGE)`
    (resolve-to-owner): the grant gate authorizes the caller and the write lands
    as the project owner. Adopt/sync-apply/CRUD all go through this gate.
  * The mutations repo additionally refuses any write on a system row, so a
    mis-routed write fails closed at the data layer too.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §8 M1/M3,
§10-A3/A4.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field

from app.auth.grant_deps import GrantLevel, require_project_grant
from app.clients.glossary_ontology_client import (
    GlossaryOntologyClient,
    HttpGlossaryOntologyClient,
)
from app.config import settings
from app.db.ontology_models import GraphSchema
from app.db.pool import get_knowledge_pool
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import (
    ChildNotFoundError,
    DuplicateChildError,
    NeedsGlossaryError,
    OntologyMutationsRepo,
    SchemaNotWritableError,
    SyncConflictError,
)
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.ontology.glossary_gate import (
    adopt_with_autocreate_glossary,
    resolve_adopt_glossary_codes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/kg",
    tags=["kg-ontology"],
    dependencies=[Depends(get_current_user)],
)

_CODE_MAX = 120
_NAME_MAX = 200


# ── DI ──────────────────────────────────────────────────────────────────────
def get_graph_schemas_repo() -> GraphSchemasRepo:
    return GraphSchemasRepo(get_knowledge_pool())


def get_ontology_mutations_repo() -> OntologyMutationsRepo:
    return OntologyMutationsRepo(get_knowledge_pool())


_glossary_ontology_client: GlossaryOntologyClient | None = None


def get_glossary_ontology_client() -> GlossaryOntologyClient:
    """Singleton KG→glossary ontology-read client (long-lived httpx). Tests
    override this dep with `FakeGlossaryOntologyClient` so the adopt-gate runs
    without a live glossary."""
    global _glossary_ontology_client
    if _glossary_ontology_client is None:
        _glossary_ontology_client = HttpGlossaryOntologyClient(
            base_url=settings.glossary_service_url,
            internal_token=settings.internal_service_token,
            timeout_s=getattr(settings, "glossary_client_timeout_s", 10.0),
        )
    return _glossary_ontology_client


# ── request / response models ────────────────────────────────────────────────
class GraphSchemaListResponse(BaseModel):
    items: list[GraphSchema]


class GraphSchemaTree(GraphSchema):
    """Full schema tree: the summary fields (inherited) + children arrays.

    Mirrors the contract `allOf [GraphSchemaSummary, {children}]` — children are
    inlined at the top level, NOT nested under a `schema` key."""

    edge_types: list[dict] = Field(default_factory=list)
    fact_types: list[dict] = Field(default_factory=list)
    vocab_sets: list[dict] = Field(default_factory=list)
    node_kinds: list[dict] = Field(default_factory=list)


class GraphSchemaPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=_NAME_MAX)
    description: str | None = None
    allow_free_edges: bool | None = None


class AdoptRequest(BaseModel):
    source_schema_id: UUID
    acknowledge_optional_gaps: bool = False


class AdoptPreviewRequest(BaseModel):
    source_schema_id: UUID


class EdgeTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    label: str = Field(min_length=1)
    directed: bool = True
    source_node_kinds: list[str] = Field(default_factory=list)
    target_node_kinds: list[str] = Field(default_factory=list)
    temporal: bool = False
    provenance_required: bool = False
    cardinality: str = "multi_active"
    description: str = ""


class FactTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    label: str = Field(min_length=1)
    description: str = ""


class VocabValueCreate(BaseModel):
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    label: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SchemaNodeKindCreate(BaseModel):
    kind_code: str = Field(min_length=1, max_length=_CODE_MAX)
    strength: str = Field(pattern="^(required|optional)$")


class SyncDecision(BaseModel):
    node_type: str
    parent_code: str | None = None
    code: str
    choice: str = Field(pattern="^(keep_mine|take_theirs)$")


class SyncApplyRequest(BaseModel):
    base_source_hash: str
    decisions: list[SyncDecision] = Field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────────
def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


def _forbidden(msg: str = "insufficient access") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)


async def _writable_schema_for_caller(
    schema_id: UUID, caller: UUID, mutations: OntologyMutationsRepo, gc, projects: ProjectsRepo
) -> GraphSchema:
    """Authorize a child/metadata write on `schema_id` and return the row.

    System tier → 403 (read-only). User tier → owner==caller else 404 (no
    existence oracle). Project tier → Manage grant on the project (resolve-to-
    owner). A missing schema → 404.
    """
    schema = await mutations.get_schema(schema_id)
    if schema is None:
        raise _not_found()
    if schema.scope == "system":
        raise _forbidden("system-tier schema is read-only")
    if schema.scope == "user":
        if schema.scope_id != str(caller):
            raise _not_found()  # not the owner — no existence oracle
        return schema
    # project tier — Manage-gate the project (resolve-to-owner).
    await _require_project_manage(schema.scope_id, caller, gc, projects)
    return schema


async def _require_project_manage(project_id: str | None, caller: UUID, gc, projects: ProjectsRepo) -> None:
    """Mirror require_project_grant(MANAGE) for a project_id pulled off a schema
    row (the grant dep keys off the path param; here the project id comes from
    the schema's scope_id)."""
    if project_id is None:
        raise _not_found()
    try:
        pid = UUID(project_id)
    except (ValueError, AttributeError):
        raise _not_found()
    meta = await projects.project_meta(pid)
    if meta is None:
        raise _not_found()
    owner, book_id = meta
    if caller == owner:
        return
    if book_id is None:
        raise _not_found()
    lvl = await gc.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
        raise _not_found()
    if not lvl.at_least(GrantLevel.MANAGE):
        raise _forbidden()


def _tree_to_response(tree: dict) -> GraphSchemaTree:
    schema: GraphSchema = tree["schema"]
    return GraphSchemaTree(
        **schema.model_dump(),
        edge_types=[e.model_dump() for e in tree["edge_types"]],
        fact_types=[f.model_dump() for f in tree["fact_types"]],
        node_kinds=[k.model_dump() for k in tree["node_kinds"]],
        vocab_sets=[
            {
                **s.model_dump(),
                "values": [v.model_dump() for v in tree["vocab_values"].get(s.code, [])],
            }
            for s in tree["vocab_sets"]
        ],
    )


# ── list / read ───────────────────────────────────────────────────────────────
@router.get("/graph-schemas", response_model=GraphSchemaListResponse)
async def list_graph_schemas(
    scope: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    include_deprecated: bool = Query(default=False),
    user_id: UUID = Depends(get_current_user),
    repo: GraphSchemasRepo = Depends(get_graph_schemas_repo),
) -> GraphSchemaListResponse:
    """List schemas visible to the caller: System (read-only) + the caller's
    User templates + (when `project_id` given) the project's adopted schema.

    Visibility is scope-keyed by the repo; the `project_id` filter only EXPOSES
    the caller's own project rows by id — it does not grant cross-project read."""
    items = await repo.list_visible(
        user_id, project_id=project_id, scope=scope, include_deprecated=include_deprecated
    )
    return GraphSchemaListResponse(items=items)


@router.get("/graph-schemas/{schema_id}", response_model=GraphSchemaTree)
async def get_graph_schema(
    schema_id: UUID = Path(),
    project_id: str | None = Query(default=None),
    include_deprecated: bool = Query(default=False),
    user_id: UUID = Depends(get_current_user),
    repo: GraphSchemasRepo = Depends(get_graph_schemas_repo),
) -> GraphSchemaTree:
    """Read one schema with all children. Scope-visible to the caller (system to
    everyone; user to its owner; project to a caller passing its project_id)."""
    tree = await repo.get_tree(
        user_id, schema_id, project_id=project_id, include_deprecated=include_deprecated
    )
    if tree is None:
        raise _not_found()
    return _tree_to_response(tree)


@router.patch("/graph-schemas/{schema_id}", response_model=GraphSchema)
async def patch_graph_schema(
    body: GraphSchemaPatch,
    schema_id: UUID = Path(),
    caller: UUID = Depends(get_current_user),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    gc=Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
) -> GraphSchema:
    """Edit user/project schema metadata. System tier → 403."""
    await _writable_schema_for_caller(schema_id, caller, mutations, gc, projects)
    return await mutations.patch_schema(
        schema_id,
        name=body.name,
        description=body.description,
        allow_free_edges=body.allow_free_edges,
    )


@router.delete("/graph-schemas/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deprecate_graph_schema(
    schema_id: UUID = Path(),
    caller: UUID = Depends(get_current_user),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    gc=Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
) -> None:
    """Soft-deprecate a user/project schema (recycle bin). System tier → 403."""
    await _writable_schema_for_caller(schema_id, caller, mutations, gc, projects)
    await mutations.deprecate_schema(schema_id)


# ── resolved schema ───────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/schema")
async def get_resolved_schema(
    project_id: UUID = Path(),
    owner: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    repo: GraphSchemasRepo = Depends(get_graph_schemas_repo),
):
    """The resolved effective schema for the project (system→user→project merge).
    View-gated on the project (resolve-to-owner)."""
    return await repo.resolve_for_project(str(project_id))


# ── adopt (copy-down, M1 adopt-gate) ──────────────────────────────────────────
@router.post(
    "/projects/{project_id}/adopt",
    response_model=GraphSchema,
    status_code=status.HTTP_201_CREATED,
)
async def adopt_schema(
    body: AdoptRequest,
    response: Response,
    project_id: UUID = Path(),
    owner: UUID = Depends(require_project_grant(GrantLevel.MANAGE)),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    projects: ProjectsRepo = Depends(get_projects_repo),
    glossary: GlossaryOntologyClient = Depends(get_glossary_ontology_client),
) -> GraphSchema:
    """Adopt (copy-down) a system/user template into the project. Manage-gated.

    M1 adopt-gate: resolve the project's glossary node-kind source (book ontology
    when the project has a book, else the owner's glossary standards), and block
    with 422 `needs_glossary` if the source template requires a node-kind the
    glossary doesn't have. Missing `optional` kinds proceed (warning header).
    Idempotent re-check: once the glossary gap is filled, re-adopt succeeds and
    replaces the project's active schema (one-active invariant).
    """
    project_str = str(project_id)
    # KM6-M2 + auto-seed: adopting a schema AUTO-CREATES the glossary node-kinds it
    # requires (copy-down from System), retrying the adopt once — shared with the
    # agent confirm effect so the GUI + MCP kg_adopt behave identically. A 422 now
    # only fires for a genuinely unsatisfiable gap (book-less project, or a required
    # kind with no System row to copy) — not for the common "glossary not seeded yet".
    try:
        result = await adopt_with_autocreate_glossary(
            projects, glossary, mutations,
            owner=owner, project_id=project_str, source_schema_id=body.source_schema_id,
        )
    except NeedsGlossaryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "KG_ADOPT_NEEDS_GLOSSARY",
                "message": (
                    "the schema needs node-kinds that couldn't be auto-created (no "
                    "System kind to copy, or a book-less project) — add them in "
                    "glossary, then re-adopt"
                ),
                "needs_glossary": {"book_id": exc.book_id, "kinds": exc.kinds},
            },
        )
    except SchemaNotWritableError:
        raise _not_found()

    if result.missing_optional and not body.acknowledge_optional_gaps:
        response.headers["X-KG-Optional-Gaps"] = ",".join(result.missing_optional)
    return result.schema


# ── adopt loss preview (read-only, D-KG-LC-REVADOPT-LOSS) ──────────────────────
@router.post("/projects/{project_id}/adopt/preview")
async def adopt_preview(
    body: AdoptPreviewRequest,
    project_id: UUID = Path(),
    owner: UUID = Depends(require_project_grant(GrantLevel.MANAGE)),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    repo: GraphSchemasRepo = Depends(get_graph_schemas_repo),
):
    """Preview "what you'll lose" before re-adopting a template. Read-only,
    Manage-gated (same grant as adopt — resolve-to-owner). Re-adopt deprecates
    the project's active schema and replaces it with a fresh copy of the source,
    silently dropping any customizations the source lacks; this surfaces them
    first so the UI can warn + gate the destructive action.

    Returns `{has_current, would_lose:[{node_type, code, change, ...}]}`. When the
    project never adopted (`has_current=False`) there is nothing to lose."""
    current_schema_id = await _active_project_schema_id(repo, str(project_id))
    try:
        return await mutations.compute_adopt_preview(
            owner_user_id=owner,
            project_id=str(project_id),
            current_schema_id=current_schema_id,
            incoming_source_id=body.source_schema_id,
        )
    except SchemaNotWritableError:
        raise _not_found()


# ── sync (tree diff / apply) ──────────────────────────────────────────────────
@router.get("/projects/{project_id}/sync/available")
async def sync_available(
    project_id: UUID = Path(),
    owner: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    repo: GraphSchemasRepo = Depends(get_graph_schemas_repo),
):
    """Tree-granular diff of the project's active schema vs its upstream source.
    View-gated. Empty `changes` when up to date or the project never adopted."""
    schema_id = await _active_project_schema_id(repo, str(project_id))
    if schema_id is None:
        return {
            "source_ref": None,
            "source_hash_current": None,
            "project_source_hash": None,
            "has_updates": False,
            "changes": [],
        }
    return await mutations.sync_diff(schema_id)


@router.post("/projects/{project_id}/sync/apply")
async def sync_apply(
    body: SyncApplyRequest,
    project_id: UUID = Path(),
    owner: UUID = Depends(require_project_grant(GrantLevel.MANAGE)),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    repo: GraphSchemasRepo = Depends(get_graph_schemas_repo),
):
    """Apply per-node keep_mine/take_theirs. Manage-gated. Forward-only (M3).
    409 on `base_source_hash` drift (upstream moved since /available was read)."""
    schema_id = await _active_project_schema_id(repo, str(project_id))
    if schema_id is None:
        raise _not_found()
    try:
        return await mutations.sync_apply(
            schema_id,
            base_source_hash=body.base_source_hash,
            decisions=[d.model_dump() for d in body.decisions],
        )
    except SyncConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="upstream source moved since the diff was read; re-fetch /sync/available",
        )
    except SchemaNotWritableError:
        raise _not_found()


async def _active_project_schema_id(repo: GraphSchemasRepo, project_id: str) -> UUID | None:
    """The current active (non-deprecated) project-scoped schema id, if any."""
    async with repo._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT schema_id FROM kg_graph_schemas
            WHERE scope = 'project' AND scope_id = $1 AND deprecated_at IS NULL
            ORDER BY updated_at DESC, schema_id DESC LIMIT 1
            """,
            project_id,
        )
    return row["schema_id"] if row else None


# ── child CRUD (additive + deprecate-only, M3) ───────────────────────────────
@router.post(
    "/graph-schemas/{schema_id}/edge-types",
    status_code=status.HTTP_201_CREATED,
)
async def add_edge_type(
    body: EdgeTypeCreate,
    schema_id: UUID = Path(),
    caller: UUID = Depends(get_current_user),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    gc=Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
):
    await _writable_schema_for_caller(schema_id, caller, mutations, gc, projects)
    try:
        return await mutations.add_edge_type(
            schema_id,
            code=body.code,
            label=body.label,
            directed=body.directed,
            source_node_kinds=body.source_node_kinds,
            target_node_kinds=body.target_node_kinds,
            temporal=body.temporal,
            provenance_required=body.provenance_required,
            cardinality=body.cardinality,
            description=body.description,
        )
    except DuplicateChildError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="edge type code exists")


@router.delete(
    "/graph-schemas/{schema_id}/edge-types/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deprecate_edge_type(
    schema_id: UUID = Path(),
    code: str = Path(min_length=1, max_length=_CODE_MAX),
    caller: UUID = Depends(get_current_user),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    gc=Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
) -> None:
    await _writable_schema_for_caller(schema_id, caller, mutations, gc, projects)
    try:
        await mutations.deprecate_edge_type(schema_id, code)
    except ChildNotFoundError:
        raise _not_found()


@router.post(
    "/graph-schemas/{schema_id}/fact-types",
    status_code=status.HTTP_201_CREATED,
)
async def add_fact_type(
    body: FactTypeCreate,
    schema_id: UUID = Path(),
    caller: UUID = Depends(get_current_user),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    gc=Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
):
    await _writable_schema_for_caller(schema_id, caller, mutations, gc, projects)
    try:
        return await mutations.add_fact_type(
            schema_id, code=body.code, label=body.label, description=body.description
        )
    except DuplicateChildError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="fact type code exists")


@router.post(
    "/graph-schemas/{schema_id}/vocab-sets/{set_code}/values",
    status_code=status.HTTP_201_CREATED,
)
async def add_vocab_value(
    body: VocabValueCreate,
    schema_id: UUID = Path(),
    set_code: str = Path(min_length=1, max_length=_CODE_MAX),
    caller: UUID = Depends(get_current_user),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    gc=Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
):
    await _writable_schema_for_caller(schema_id, caller, mutations, gc, projects)
    try:
        return await mutations.add_vocab_value(
            schema_id, set_code=set_code, code=body.code, label=body.label, metadata=body.metadata
        )
    except ChildNotFoundError:
        raise _not_found()
    except DuplicateChildError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="vocab value code exists")


@router.post(
    "/graph-schemas/{schema_id}/node-kinds",
    status_code=status.HTTP_201_CREATED,
)
async def add_node_kind(
    body: SchemaNodeKindCreate,
    schema_id: UUID = Path(),
    caller: UUID = Depends(get_current_user),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    gc=Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
):
    await _writable_schema_for_caller(schema_id, caller, mutations, gc, projects)
    try:
        return await mutations.add_node_kind(
            schema_id, kind_code=body.kind_code, strength=body.strength
        )
    except DuplicateChildError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="node kind exists")


# ── system-tier create (admin-only, requireAdmin placeholder) ─────────────────
@router.post("/system/graph-schemas")
async def create_system_schema() -> Response:
    """System-tier template create — admin-only. v1 returns 501 behind a
    `requireAdmin` placeholder until the admin-identity epic lands (contract
    freezes the route shape now)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="system-tier write is admin-only; not implemented in v1 (requireAdmin placeholder)",
    )
