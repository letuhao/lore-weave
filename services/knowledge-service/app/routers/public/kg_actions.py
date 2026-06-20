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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError

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
from app.deps import get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.ontology.adopt_effect import (
    AdoptNeedsGlossary,
    AdoptParams,
    AdoptSourceMissing,
    apply_adopt,
    preview_adopt,
)
from app.ontology.confirm import (
    AUTH_ADMIN,
    AUTH_GRANT,
    DESC_ADOPT,
    DESC_SCHEMA_EDIT,
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
from app.routers.public.ontology import get_glossary_ontology_client

logger = logging.getLogger(__name__)

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
    claims: ActionClaims, caller: UUID, gc: GrantClient, projects: ProjectsRepo
) -> UUID:
    """Re-check authority at confirm/preview (C3 + defense in depth). Grant actions:
    the redeemer must be the proposing user AND still hold MANAGE on the token's
    project. The admin branch is structured but 501 (KM5 wires RS256). Returns the
    project owner (the repo write scope). Raises 403/404/422/501."""
    if claims.authority == AUTH_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="admin actions are not enabled yet",
        )
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


# ── confirm (token-gated, single-use write) ───────────────────────────────────
@router.post("/confirm")
async def confirm_action(
    body: ConfirmTokenBody,
    caller: UUID = Depends(get_current_user),
    gc: GrantClient = Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
    schemas: GraphSchemasRepo = Depends(get_graph_schemas_repo),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    tokens: ActionTokenRepo = Depends(get_action_token_repo),
    glossary: GlossaryOntologyClient = Depends(get_glossary_ontology_client),
) -> dict:
    claims = _decode_confirm_token(body)
    owner = await _authorize_action(claims, caller, gc, projects)
    # Single-use: claim the jti now. Fail-closed — a failed effect does NOT release it.
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


# ── preview (non-consuming current-state render) ──────────────────────────────
@router.post("/preview")
async def preview_action(
    body: ConfirmTokenBody,
    caller: UUID = Depends(get_current_user),
    gc: GrantClient = Depends(get_grant_client),
    projects: ProjectsRepo = Depends(get_projects_repo),
    schemas: GraphSchemasRepo = Depends(get_graph_schemas_repo),
    mutations: OntologyMutationsRepo = Depends(get_ontology_mutations_repo),
    glossary: GlossaryOntologyClient = Depends(get_glossary_ontology_client),
) -> dict:
    claims = _decode_confirm_token(body)
    owner = await _authorize_action(claims, caller, gc, projects)
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
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="unknown action")
