"""KM6 — generalized class-C confirm + preview endpoints (spec §13.5).

One JWT-gated confirm path serves every high-impact knowledge action via an action
descriptor; a separate non-consuming preview path re-renders the human-facing card
from CURRENT state (§5.1 #5). Both are reachable ONLY with the user's browser JWT —
the MCP/mint path can never call them (the un-bypassability argument: the MCP tool
mints + returns a token; only the human's browser redeems it here).

Order at confirm (§13.5): verify token → re-check authority (BEFORE consuming, so a
stranger holding a victim's token can't burn it) → claim jti (single-use) →
re-validate the action against current state → run the effect. Fail-closed: once the
jti is claimed, a failed effect does NOT release it — the human re-proposes.

The project a token targets comes from the TOKEN (`claims.project_id`), not the path,
so authority is resolved manually against that project (reusing the canonical
resolve-to-owner gate) rather than via a path-bound `require_project_grant`.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ValidationError

from app.auth.admin_jwt import (
    SCOPE_ADMIN_WRITE,
    AdminKey,
    AdminTokenInvalid,
    verify_admin_token,
)
from app.auth.admin_key import get_admin_key as _shared_get_admin_key
from app.auth.grant_deps import _resolve_owner  # canonical anti-oracle 404/403 gate
from app.clients.glossary_ontology_client import GlossaryOntologyClient
from app.clients.grant_client import GrantClient, GrantLevel
from app.config import settings
from app.db.pool import get_knowledge_pool
from app.db.repositories.action_tokens import ActionTokenRepo
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import (
    ChildNotFoundError,
    DuplicateChildError,
    OntologyMutationsRepo,
    SchemaNotWritableError,
)
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.system_templates import (
    DuplicateSystemTemplate,
    SystemTemplateNotFound,
    SystemTemplatesRepo,
)
from app.db.repositories.triage import TriageRepo
from app.deps import (
    get_benchmark_runs_repo,
    get_book_client,
    get_extraction_jobs_repo,
    get_extraction_wake,
    get_glossary_client,
    get_grant_client,
    get_projects_repo,
)
from app.middleware.jwt_auth import get_current_user
from app.ontology.adopt_effect import (
    AdoptNeedsGlossary,
    AdoptParams,
    AdoptSourceMissing,
    apply_adopt,
    preview_adopt,
)
from app.ontology.build_graph_effect import (
    BuildGraphParams,
    apply_build_graph,
    preview_build_graph,
)
from app.ontology.build_wiki_effect import (
    BuildWikiActiveJob,
    BuildWikiNoEntities,
    BuildWikiParams,
    apply_build_wiki,
    preview_build_wiki,
)
from app.ontology.confirm import (
    AUTH_ADMIN,
    AUTH_GRANT,
    DESC_ADOPT,
    DESC_BUILD_GRAPH,
    DESC_BUILD_WIKI,
    DESC_SCHEMA_EDIT,
    DESC_SYNC,
    DESC_SYSTEM_CREATE,
    DESC_SYSTEM_DELETE,
    DESC_SYSTEM_PATCH,
    DESC_TRIAGE_PROPOSED_EDGE,
    DESC_TRIAGE_SCHEMA_WRITE,
    ActionClaims,
    ActionTokenExpired,
    ActionTokenInvalid,
    verify_action_token,
)
from app.ontology.schema_edit_effect import (
    SchemaEditDrift,
    SchemaEditParams,
    apply_schema_edit,
    preview_schema_edit,
)
from app.ontology.triage_proposed_edge_effect import (
    ProposedEdgeDrift,
    ProposedEdgeNotFound,
    ProposedEdgeParams,
    ProposedEdgeWriteFailed,
    apply_proposed_edge,
    preview_proposed_edge,
)
from app.ontology.triage_schema_write_effect import (
    TriageSchemaWriteDrift,
    TriageSchemaWriteParams,
    TriageSchemaWriteUnsupported,
    apply_triage_schema_write,
    preview_triage_schema_write,
)
from app.ontology.sync_effect import (
    SyncApplyParams,
    SyncDrift,
    SyncNoSchema,
    apply_sync,
    preview_sync,
)
from app.ontology.system_effect import (
    SystemEffectDrift,
    SystemTemplateParams,
    VERB_BY_DESCRIPTOR,
    apply_system_template,
    preview_system_template,
)
from app.routers.public.ontology import get_glossary_ontology_client

logger = logging.getLogger(__name__)

_SYSTEM_DESCRIPTORS = frozenset({DESC_SYSTEM_CREATE, DESC_SYSTEM_PATCH, DESC_SYSTEM_DELETE})

router = APIRouter(
    prefix="/v1/kg/actions",
    tags=["kg-actions"],
    dependencies=[Depends(get_current_user)],
)


# ── DI ──────────────────────────────────────────────────────────────────────
def get_action_token_repo() -> ActionTokenRepo:
    return ActionTokenRepo(get_knowledge_pool())


def get_graph_schemas_repo() -> GraphSchemasRepo:
    return GraphSchemasRepo(get_knowledge_pool())


def get_ontology_mutations_repo() -> OntologyMutationsRepo:
    return OntologyMutationsRepo(get_knowledge_pool())


def get_system_templates_repo() -> SystemTemplatesRepo:
    return SystemTemplatesRepo(get_knowledge_pool())


def get_triage_repo() -> TriageRepo:
    return TriageRepo(get_knowledge_pool())


def get_admin_key() -> AdminKey | None:
    """The configured RS256 admin key (shared process cache), or None when
    System-tier admin is disabled. Overridable in tests."""
    return _shared_get_admin_key()


class ConfirmTokenBody(BaseModel):
    confirm_token: str


# ── shared decode + authorize ────────────────────────────────────────────────
def _decode_confirm_token(body: ConfirmTokenBody) -> ActionClaims:
    """Verify {confirm_token}; raise the 4xx itself on missing/expired/invalid."""
    if not body.confirm_token or not body.confirm_token.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confirm_token is required")
    try:
        return verify_action_token(settings.jwt_secret, body.confirm_token, time.time())
    except ActionTokenExpired:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="confirmation expired — propose again",
        )
    except ActionTokenInvalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid confirmation",
        )


async def _authorize_action(
    claims: ActionClaims,
    caller: UUID,
    gc: GrantClient,
    projects: ProjectsRepo,
    *,
    admin_token: str | None = None,
    admin_key: AdminKey | None = None,
) -> UUID | None:
    """Re-check authority at confirm/preview (C3 + defense in depth).

    Grant actions: the redeemer must be the proposing user AND still hold MANAGE
    on the token's project → returns the project owner (the repo write scope).

    Admin actions (KM5-M2): re-verify the RS256 admin JWT (re-presented as
    X-Admin-Token), require `admin:write`, and BIND the redeemer to the proposer
    by asserting the live token's `sub` == the confirm-token's `asub` (both
    non-empty). System tier has no project owner → returns None.

    Raises 401/403/404/422/503."""
    # Authority↔descriptor pairing (defense in depth): a System descriptor MUST
    # carry admin authority, a grant descriptor MUST carry grant authority. A
    # mismatch is only possible from a buggy/forged mint (both fields are inside
    # the HMAC) — fail closed BEFORE any effect, so an admin token can never drive
    # a project-grant effect and a grant token can never drive a System write.
    is_system = claims.descriptor in _SYSTEM_DESCRIPTORS
    if is_system and claims.authority != AUTH_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="system action requires admin authority",
        )
    if not is_system and claims.authority == AUTH_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="admin authority not valid for this action",
        )

    if claims.authority == AUTH_ADMIN:
        return await _authorize_admin(claims, admin_token, admin_key)
    if claims.authority != AUTH_GRANT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="unknown authority"
        )
    # Bound to the proposer — a different signed-in user cannot redeem it even with
    # the string. Checked BEFORE consuming so a stranger can't burn it.
    if str(caller) != claims.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="confirmation not valid for this user",
        )
    try:
        project_uuid = UUID(claims.project_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid project in token"
        )
    meta = await projects.project_meta(project_uuid)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    owner, book_id = meta
    # Reuse the canonical gate: caller must be owner OR hold >= MANAGE on the book.
    return await _resolve_owner(caller, owner, book_id, GrantLevel.MANAGE, gc)


async def _authorize_admin(
    claims: ActionClaims, admin_token: str | None, admin_key: AdminKey | None
) -> None:
    """Admin-authority re-check (INV-T2/T3). The RS256 admin JWT is re-presented
    at confirm/preview (X-Admin-Token) — never trusted from `X-User-Id`. Returns
    None (System tier has no project owner). Raises 503/401/403."""
    if admin_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="system-tier administration is not configured",
        )
    if not admin_token or not admin_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="admin token required"
        )
    try:
        admin_claims = verify_admin_token(admin_token, admin_key)
    except AdminTokenInvalid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
        )
    if not admin_claims.has_scope(SCOPE_ADMIN_WRITE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="missing required admin scope"
        )
    # Bind the redeemer to the proposer: the live RS256 subject must equal the
    # confirm-token's `asub`, BOTH non-empty. (KM5-M1 /review-impl MED — a codec
    # that doesn't require `sub` must be guarded at the binding site, else two
    # empty strings would match.) Checked BEFORE the jti is consumed.
    if (
        not claims.admin_sub.strip()
        or not admin_claims.sub.strip()
        or admin_claims.sub != claims.admin_sub
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin confirmation not valid for this admin",
        )
    return None


# ── confirm (token-gated, single-use write) ───────────────────────────────────
@router.post("/confirm")
async def confirm_action(
    body: ConfirmTokenBody,
    caller: UUID = Depends(get_current_user),
    gc: GrantClient = Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
    schemas: GraphSchemasRepo = Depends(get_graph_schemas_repo),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    system_repo: SystemTemplatesRepo = Depends(get_system_templates_repo),
    triage: TriageRepo = Depends(get_triage_repo),
    tokens: ActionTokenRepo = Depends(get_action_token_repo),
    glossary: GlossaryOntologyClient = Depends(get_glossary_ontology_client),
    admin_key: AdminKey | None = Depends(get_admin_key),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> dict:
    claims = _decode_confirm_token(body)
    owner = await _authorize_action(
        claims, caller, gc, projects, admin_token=x_admin_token, admin_key=admin_key
    )
    # Single-use: claim the jti now. Fail-closed — a failed effect does NOT release it.
    # (Authority — incl. the RS256 admin re-verify + asub bind — is checked ABOVE,
    # before the claim, so a stranger can't burn a victim's token.)
    claimed = await tokens.consume(
        jti=claims.jti,
        descriptor=claims.descriptor,
        exp=datetime.fromtimestamp(claims.exp, tz=timezone.utc),
    )
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="already confirmed — propose again",
        )

    if claims.descriptor == DESC_SCHEMA_EDIT:
        return await _confirm_schema_edit(claims, schemas, mutations)
    if claims.descriptor == DESC_ADOPT:
        return await _confirm_adopt(claims, owner, mutations, projects, glossary)
    if claims.descriptor == DESC_SYNC:
        return await _confirm_sync(claims, schemas, mutations)
    if claims.descriptor == DESC_TRIAGE_PROPOSED_EDGE:
        return await _confirm_proposed_edge(claims, owner, triage)
    if claims.descriptor == DESC_TRIAGE_SCHEMA_WRITE:
        return await _confirm_triage_schema_write(claims, owner, schemas, mutations, triage)
    if claims.descriptor == DESC_BUILD_GRAPH:
        return await _confirm_build_graph(claims, owner, projects)
    if claims.descriptor == DESC_BUILD_WIKI:
        return await _confirm_build_wiki(claims, owner, projects)
    if claims.descriptor in _SYSTEM_DESCRIPTORS:
        return await _confirm_system(claims, system_repo)
    # Unreachable: verify_action_token already rejects non-live descriptors.
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="unknown action")


async def _confirm_schema_edit(
    claims: ActionClaims, schemas: GraphSchemasRepo, mutations: OntologyMutationsRepo
) -> dict:
    try:
        params = SchemaEditParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    try:
        return await apply_schema_edit(schemas, mutations, claims.project_id, params)
    except SchemaEditDrift as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except DuplicateChildError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a {params.level} '{params.code}' already exists in this schema",
        )
    except ChildNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"the {params.level} '{params.code}' no longer exists — propose again",
        )
    except SchemaNotWritableError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="the project schema is no longer writable — propose again",
        )


async def _confirm_adopt(
    claims: ActionClaims, owner: UUID, mutations: OntologyMutationsRepo,
    projects: ProjectsRepo, glossary: GlossaryOntologyClient,
) -> dict:
    try:
        params = AdoptParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    try:
        return await apply_adopt(
            mutations, projects, glossary,
            owner=owner, project_id=claims.project_id, params=params,
        )
    except AdoptNeedsGlossary as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "KG_ADOPT_NEEDS_GLOSSARY",
                "message": "the project's glossary is missing required node-kinds — "
                           "add them in glossary first, then propose again",
                "needs_glossary": {"book_id": exc.book_id, "kinds": exc.kinds},
            },
        )
    except AdoptSourceMissing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="the source template no longer exists — propose again",
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )


async def _confirm_sync(
    claims: ActionClaims, schemas: GraphSchemasRepo, mutations: OntologyMutationsRepo
) -> dict:
    try:
        params = SyncApplyParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    try:
        return await apply_sync(schemas, mutations, claims.project_id, params)
    except SyncDrift as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except SyncNoSchema as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


async def _confirm_proposed_edge(
    claims: ActionClaims, owner: UUID | None, triage: TriageRepo
) -> dict:
    """E2 — place a parked `proposed_edge` into Neo4j (class-C, grant authority).
    `owner` is the resolved project owner from `_authorize_action` (grant path is
    never None here; the authority↔descriptor pairing already rejected admin)."""
    try:
        params = ProposedEdgeParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    try:
        return await apply_proposed_edge(
            triage, owner=owner, project_id=claims.project_id, params=params
        )
    except ProposedEdgeNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ProposedEdgeDrift as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except ProposedEdgeWriteFailed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


async def _confirm_triage_schema_write(
    claims: ActionClaims,
    owner: UUID | None,
    schemas: GraphSchemasRepo,
    mutations: OntologyMutationsRepo,
    triage: TriageRepo,
) -> dict:
    """E3 — apply a schema-mutating triage resolution via ontology_mutations
    (class-C, Manage-gated) and write the new schema_version onto the items.
    `owner` is the resolved project owner (grant path; never None here) — passed
    so the version stamp scopes to (owner, project, signature)."""
    try:
        params = TriageSchemaWriteParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    try:
        return await apply_triage_schema_write(
            schemas, mutations, triage, claims.project_id, params, owner=owner
        )
    except TriageSchemaWriteDrift as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except TriageSchemaWriteUnsupported as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except DuplicateChildError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="that schema element already exists — propose again",
        )
    except ChildNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="the targeted schema element no longer exists — propose again",
        )
    except SchemaNotWritableError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="the project schema is no longer writable — propose again",
        )


async def _confirm_build_graph(
    claims: ActionClaims, owner: UUID | None, projects: ProjectsRepo
) -> dict:
    """Cost-gated job trigger — start the extraction job via the shared core (grant
    authority; `owner` is the resolved project owner, never None here). The core's
    HTTPExceptions (K17.9 benchmark 409, active-job 409, scope 422) propagate as-is —
    fail-closed (the consumed jti is not released; the human re-proposes after fixing).

    The extraction deps (jobs/benchmark repos, book client, wake) are built HERE rather
    than injected into the shared confirm route — adding them to the route signature would
    force every confirm (incl. admin/system) to resolve the redis-backed wake + book
    client, breaking unrelated paths. They are process singletons / pool-backed repos."""
    try:
        params = BuildGraphParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    return await apply_build_graph(
        project_id=claims.project_id, owner=owner, params=params,
        projects_repo=projects,
        jobs_repo=await get_extraction_jobs_repo(),
        benchmark_repo=await get_benchmark_runs_repo(),
        book_client=await get_book_client(),
        extraction_wake=await get_extraction_wake(),
    )


async def _confirm_build_wiki(
    claims: ActionClaims, owner: UUID | None, projects: ProjectsRepo
) -> dict:
    """Cost-gated wiki generation — resolve the entity set + create/enqueue the job
    (grant authority; `owner` resolved, never None). Deps built here (glossary client +
    redis), not route-injected (see _confirm_build_graph)."""
    from app.routers.internal_wiki import _redis  # process-singleton redis for the XADD

    try:
        params = BuildWikiParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    project = await projects.get(owner, UUID(claims.project_id))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    try:
        return await apply_build_wiki(
            project=project, owner=owner, params=params,
            glossary_client=await get_glossary_client(), redis=_redis(),
        )
    except BuildWikiNoEntities:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="no entities to generate wiki articles for — extract the glossary first",
        )
    except BuildWikiActiveJob as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "active_job_exists", "job_id": exc.existing_job_id},
        )


async def _confirm_system(claims: ActionClaims, system_repo: SystemTemplatesRepo) -> dict:
    """Admin System-tier template effect. Authority (RS256 + asub bind) was already
    re-checked in `_authorize_admin` and the jti consumed; here we re-validate the
    target against current state and apply."""
    params = _system_params(claims)
    try:
        return await apply_system_template(system_repo, params)
    except SystemEffectDrift as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except SystemTemplateNotFound:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="the system template no longer exists — propose again",
        )
    except DuplicateSystemTemplate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a system template '{params.code}' already exists",
        )


def _system_params(claims: ActionClaims) -> SystemTemplateParams:
    """Parse the system params + assert the descriptor's verb matches params.verb
    (both inside the HMAC; a mismatch means a malformed mint → fail closed)."""
    try:
        params = SystemTemplateParams(**claims.params)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
        )
    if VERB_BY_DESCRIPTOR.get(claims.descriptor) != params.verb:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="descriptor/verb mismatch"
        )
    return params


# ── preview (non-consuming current-state render) ──────────────────────────────
@router.post("/preview")
async def preview_action(
    body: ConfirmTokenBody,
    caller: UUID = Depends(get_current_user),
    gc: GrantClient = Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
    schemas: GraphSchemasRepo = Depends(get_graph_schemas_repo),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    system_repo: SystemTemplatesRepo = Depends(get_system_templates_repo),
    triage: TriageRepo = Depends(get_triage_repo),
    glossary: GlossaryOntologyClient = Depends(get_glossary_ontology_client),
    admin_key: AdminKey | None = Depends(get_admin_key),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> dict:
    claims = _decode_confirm_token(body)
    owner = await _authorize_action(
        claims, caller, gc, projects, admin_token=x_admin_token, admin_key=admin_key
    )
    if claims.descriptor in _SYSTEM_DESCRIPTORS:
        return await preview_system_template(system_repo, _system_params(claims))
    if claims.descriptor == DESC_BUILD_GRAPH:
        try:
            params = BuildGraphParams(**claims.params)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
            )
        project = await projects.get(owner, UUID(claims.project_id))
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        # Deps built here (not route-injected) — see _confirm_build_graph.
        return await preview_build_graph(
            project=project, params=params, book_client=await get_book_client(),
            benchmark_repo=await get_benchmark_runs_repo(), owner=owner,
        )
    if claims.descriptor == DESC_BUILD_WIKI:
        try:
            params = BuildWikiParams(**claims.params)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
            )
        project = await projects.get(owner, UUID(claims.project_id))
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        return await preview_build_wiki(
            project=project, params=params, glossary_client=await get_glossary_client(),
        )
    if claims.descriptor == DESC_SCHEMA_EDIT:
        try:
            params = SchemaEditParams(**claims.params)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
            )
        return await preview_schema_edit(schemas, claims.project_id, params)
    if claims.descriptor == DESC_ADOPT:
        try:
            params = AdoptParams(**claims.params)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
            )
        return await preview_adopt(
            schemas, mutations, projects, glossary,
            owner=owner, project_id=claims.project_id, params=params,
        )
    if claims.descriptor == DESC_SYNC:
        try:
            params = SyncApplyParams(**claims.params)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
            )
        return await preview_sync(schemas, mutations, claims.project_id, params)
    if claims.descriptor == DESC_TRIAGE_PROPOSED_EDGE:
        try:
            params = ProposedEdgeParams(**claims.params)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
            )
        return await preview_proposed_edge(
            triage, owner=owner, project_id=claims.project_id, params=params
        )
    if claims.descriptor == DESC_TRIAGE_SCHEMA_WRITE:
        try:
            params = TriageSchemaWriteParams(**claims.params)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="bad proposal payload"
            )
        return await preview_triage_schema_write(schemas, claims.project_id, params)
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="unknown action")
