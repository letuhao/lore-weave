"""KG extraction-triage public router (epic 2026-06-20, lane LH).

The triage queue: extraction elements that didn't match the resolved schema are
parked in ``kg_triage_items`` (NOT written to Neo4j) and resolved human-gated,
grouped by ``signature`` so one resolution batch-applies. Contract:
contracts/api/knowledge-service/triage.yaml. Spec s3.7 + s11.

TENANCY (LOCKED -- worker-loaded-id-needs-parent-scoping): ``project_id`` is
caller-supplied, so every route grant-checks the project via
``require_project_grant`` (resolve-to-owner) and passes the resolved OWNER to the
repo as ``user_id``. The repo filters ``user_id AND project_id`` on every query,
so user B can never list or resolve user A's triage. List is View-gated;
KG-local + glossary-handoff resolve + dismiss are Edit-gated; schema-mutating
resolve is Manage-gated.

CROSS-SERVICE (M1): ``promote_to_glossary_kind`` / ``demote_to_attribute`` are
glossary writes the USER initiates -- this router NEVER calls glossary. It moves
the items to ``pending_glossary`` and returns ``needs_glossary{book_id,kinds}``
so the FE deep-links the user into glossary; KG re-processes when the kind
appears.
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field

from app.auth.grant_deps import (
    GrantLevel,
    project_meta_dep,
    require_project_grant,
)
from app.clients.grant_client import GrantClient
from app.db.ontology_models import TriageItemType, TriageStatus
from app.db.pool import get_knowledge_pool
from app.db.repositories.triage import (
    GLOSSARY_HANDOFF_ACTIONS,
    SCHEMA_MUTATING_ACTIONS,
    SUGGESTED_ACTIONS,
    TriageRepo,
)
from app.deps import get_grant_client
from app.middleware.jwt_auth import get_current_user
from app.ontology.triage_apply import (
    Neo4jReapplyWriter,
    TriageApplyError,
    apply_resolved,
    requires_reapply,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/kg",
    tags=["kg-triage"],
    dependencies=[Depends(get_current_user)],
)


# ── DI (local factory; mirrors app.deps Repo(get_knowledge_pool()) pattern) ──
def get_triage_repo() -> TriageRepo:
    return TriageRepo(get_knowledge_pool())


# ── valid action enum (mirrors the frozen contract TriageResolve.action) ─────
TriageAction = Literal[
    "map",
    "add_to_vocab",
    "add_to_schema",
    "re_target",
    "widen_target_kinds",
    "drop_edge",
    "close_previous",
    "set_multi_active",
    "promote_to_glossary_kind",
    "demote_to_attribute",
    "dismiss",
]

# Which actions each item_type permits (s11.2). The router rejects an action that
# isn't valid for the group's item_type (422), so a `promote` can't be applied to
# an `unknown_vocab_value` group, etc.
_VALID_ACTIONS_BY_TYPE: dict[TriageItemType, frozenset[str]] = {
    k: frozenset(v) for k, v in SUGGESTED_ACTIONS.items()
}


# ── response envelopes (mirror triage.yaml schemas) ──────────────────────────
class TriageGroupOut(BaseModel):
    signature: str
    item_type: TriageItemType
    count: int
    status: TriageStatus
    sample_payload: dict[str, Any] = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)


class TriageGroupListOut(BaseModel):
    groups: list[TriageGroupOut]
    next_cursor: str | None = None


class TriageResolveIn(BaseModel):
    action: TriageAction
    params: dict[str, Any] = Field(default_factory=dict)
    # Contract field (default true). This endpoint is keyed by `{signature}`, so
    # resolution is INHERENTLY batch over the signature group (s11.3) -- there is
    # no item id at this route to scope a single-item resolve to. The field is
    # accepted for contract-compat; `false` is not a supported narrowing here
    # (single-item dismiss is the dedicated /{triage_id}/dismiss route).
    apply_to_signature: bool = True


class NeedsGlossaryOut(BaseModel):
    book_id: str | None = None
    kinds: list[str] = Field(default_factory=list)


class TriageResolveResultOut(BaseModel):
    status: Literal["resolved", "pending_glossary"]
    affected: int
    schema_version: int | None = None
    needs_glossary: NeedsGlossaryOut | None = None


# S-05 — per-item drill-in (so the FE can dismiss ONE noisy item of a signature
# group via the existing /{triage_id}/dismiss route, instead of only the whole
# signature). Read-only, additive; the resolve/dismiss write paths are unchanged.
class TriageItemOut(BaseModel):
    triage_id: str
    item_type: TriageItemType
    payload: dict[str, Any] = Field(default_factory=dict)


class TriageItemListOut(BaseModel):
    items: list[TriageItemOut]


def _not_found(detail: str = "not found") -> HTTPException:
    # Uniform 404 -- never an existence oracle for a project/signature.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


# ── GET queue grouped by signature (View-gated) ──────────────────────────────
@router.get(
    "/projects/{project_id}/triage",
    response_model=TriageGroupListOut,
)
async def list_triage(
    project_id: UUID,
    status_filter: TriageStatus = Query(default="pending", alias="status"),
    item_type: TriageItemType | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None),
    owner: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    repo: TriageRepo = Depends(get_triage_repo),
) -> TriageGroupListOut:
    """Triage queue, one row per ``signature`` (count + sample). View-gated; the
    repo is scoped to the project OWNER (resolve-to-owner) so a cross-tenant
    caller without a grant 404s in the dep before reaching here."""
    offset = _decode_offset(cursor)
    groups, has_more = await repo.list_grouped(
        user_id=owner,
        project_id=str(project_id),
        status=status_filter,
        item_type=item_type,
        limit=limit,
        offset=offset,
    )
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return TriageGroupListOut(
        groups=[
            TriageGroupOut(
                signature=g.signature,
                item_type=g.item_type,
                count=g.count,
                status=g.status,
                sample_payload=g.sample_payload,
                suggested_actions=g.suggested_actions,
            )
            for g in groups
        ],
        next_cursor=next_cursor,
    )


# ── GET the pending items of one signature (View-gated) ──────────────────────
@router.get(
    "/projects/{project_id}/triage/{signature}/items",
    response_model=TriageItemListOut,
)
async def list_triage_items(
    project_id: UUID,
    signature: str = Path(..., min_length=1, max_length=500),
    owner: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    repo: TriageRepo = Depends(get_triage_repo),
) -> TriageItemListOut:
    """The PENDING items of one signature (S-05 per-item drill-in). View-gated;
    the repo is scoped to the project OWNER (resolve-to-owner), so a cross-tenant
    caller 404s in the dep. Lets the FE dismiss ONE noisy item via the existing
    `/{triage_id}/dismiss` route instead of the whole signature group."""
    items = await repo.list_pending_for_signature(
        user_id=owner, project_id=str(project_id), signature=signature
    )
    return TriageItemListOut(
        items=[
            TriageItemOut(
                triage_id=str(it.triage_id),
                item_type=it.item_type,
                payload=it.payload or {},
            )
            for it in items
        ]
    )


# ── POST resolve a signature (batch; Edit- or Manage-gated by action) ────────
@router.post(
    "/projects/{project_id}/triage/{signature}/resolve",
    response_model=TriageResolveResultOut,
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": TriageResolveResultOut}},
)
async def resolve_triage(
    body: TriageResolveIn,
    response: Response,
    project_id: UUID = Path(...),
    signature: str = Path(..., min_length=1, max_length=500),
    caller: UUID = Depends(get_current_user),
    meta=Depends(project_meta_dep),
    grant: GrantClient = Depends(get_grant_client),
    repo: TriageRepo = Depends(get_triage_repo),
) -> TriageResolveResultOut:
    """Apply ``action`` to every PENDING item of ``signature`` (batch, s11.3).

    GATING (s11.2): KG-local + glossary-handoff actions need Edit; schema-mutating
    actions (add_to_vocab/add_to_schema/widen/set_multi_active) need Manage. The
    gate runs AFTER we know the action so the required tier matches the action;
    the project grant resolves the owner the repo writes as.
    """
    action = body.action
    need = (
        GrantLevel.MANAGE if action in SCHEMA_MUTATING_ACTIONS else GrantLevel.EDIT
    )
    owner = await _resolve_owner_for_action(caller, meta, need, grant)
    project = str(project_id)

    # The signature group's item_type determines the valid actions. Resolve it
    # from a live pending sample (also confirms the group exists for this owner).
    pending = await repo.list_pending_for_signature(
        user_id=owner, project_id=project, signature=signature
    )
    if not pending:
        raise _not_found("no pending triage items for this signature")
    item_type = pending[0].item_type
    if action not in _VALID_ACTIONS_BY_TYPE.get(item_type, frozenset()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"action '{action}' is not valid for item_type '{item_type}'",
        )

    # Glossary hand-off (M1): NO KG->glossary write. Move items to
    # pending_glossary + return a needs_glossary deep-link for the FE.
    if action in GLOSSARY_HANDOFF_ACTIONS:
        kinds = _needs_glossary_kinds(body.params, pending)
        book_id = _book_id_for_handoff(meta, body.params)
        affected = await repo.resolve_signature(
            user_id=owner,
            project_id=project,
            signature=signature,
            action=action,
            params=body.params,
            resolved_by=str(caller),
            new_status="pending_glossary",
        )
        response.status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        return TriageResolveResultOut(
            status="pending_glossary",
            affected=affected,
            needs_glossary=NeedsGlossaryOut(book_id=book_id, kinds=kinds),
        )

    # Schema-mutating actions (Manage): the actual schema write + schema_version
    # bump is LC's ontology_mutations -- compose-point D-KG-LH-LC-SCHEMA-WRITE.
    # LH records the resolution intent + marks items resolved; it does NOT write
    # the schema here. schema_version stays None until LC wires the write.
    new_schema_version: int | None = None
    if action in SCHEMA_MUTATING_ACTIONS:
        logger.info(
            "triage schema-mutating action '%s' on %s/%s: recording intent; "
            "actual schema write deferred to LC (D-KG-LH-LC-SCHEMA-WRITE)",
            action, project, signature,
        )

    # KG-local actions (map/re_target/drop_edge/close_previous): mark the batch
    # resolved, THEN (E1, D-KG-LH-NEO4J-REAPPLY) re-apply the now-valid edge into
    # Neo4j via the central write path (create_relation) for the REAPPLY actions
    # (map/re_target/close_previous). drop_edge/dismiss write nothing. The
    # re-apply runs over the SAME pending list we resolved, fail-soft per item:
    # one bad park (missing endpoint / unreconstructable payload) is logged and
    # skipped, never breaks the batch. The Neo4j write is owner-scoped (the writer
    # is bound to the resolved OWNER), so a cross-tenant write is impossible.
    affected = await repo.resolve_signature(
        user_id=owner,
        project_id=project,
        signature=signature,
        action=action,
        params=body.params,
        resolved_by=str(caller),
        new_status="resolved",
        schema_version=new_schema_version,
    )
    if requires_reapply(action):
        await _reapply_batch(owner, action, body.params, pending)
    return TriageResolveResultOut(
        status="resolved",
        affected=affected,
        schema_version=new_schema_version,
    )


# ── POST dismiss a single item (Edit-gated) ──────────────────────────────────
@router.post(
    "/projects/{project_id}/triage/{triage_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def dismiss_triage(
    project_id: UUID,
    triage_id: UUID,
    caller: UUID = Depends(get_current_user),
    owner: UUID = Depends(require_project_grant(GrantLevel.EDIT)),
    repo: TriageRepo = Depends(get_triage_repo),
) -> Response:
    """Dismiss ONE pending triage item. Edit-gated; scoped to the project owner.
    404 if not found / not visible / already terminal (no existence oracle)."""
    dismissed = await repo.dismiss(
        user_id=owner,
        project_id=str(project_id),
        triage_id=triage_id,
        resolved_by=str(caller),
    )
    if not dismissed:
        raise _not_found("triage item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── E1 re-apply (D-KG-LH-NEO4J-REAPPLY) ──────────────────────────────────────
async def _reapply_batch(
    owner: UUID, action: str, params: dict[str, Any], pending: list
) -> None:
    """Re-apply every just-resolved item of a REAPPLY action into Neo4j via the
    central write path, under the project OWNER. One session for the whole batch.

    Fail-soft on TWO levels:
      * Neo4j unconfigured (Track-1 mode) → log + return (PG state already
        resolved; the live re-apply is a no-op, never a 500).
      * a single item that can't be reconstructed / whose endpoint is missing →
        log + continue (one bad park never breaks the batch)."""
    from app.db.neo4j import Neo4jNotConfiguredError, neo4j_session

    try:
        session_cm = neo4j_session()
    except Neo4jNotConfiguredError:
        logger.warning(
            "triage re-apply skipped — Neo4j not configured (Track-1); PG state "
            "resolved, %d item(s) of action '%s' not written", len(pending), action,
        )
        return

    async with session_cm as session:
        writer = Neo4jReapplyWriter(session, owner_user_id=str(owner))
        for item in pending:
            try:
                await apply_resolved(item, action, params, writer=writer)
            except TriageApplyError as exc:
                logger.warning("triage re-apply skipped one item: %s", exc)
            except Exception:  # noqa: BLE001 — re-apply is best-effort, never block
                logger.exception(
                    "triage re-apply failed for item %s (action '%s')",
                    getattr(item, "triage_id", "?"), action,
                )


# ── helpers ──────────────────────────────────────────────────────────────────
async def _resolve_owner_for_action(
    caller: UUID, meta, need: GrantLevel, grant: GrantClient
) -> UUID:
    """Mirror `require_project_grant` but with a DYNAMIC tier (the resolve route
    chooses Edit vs Manage from the action). Returns the project owner; 404 for
    missing/non-grantee/book-less-non-owner, 403 for grantee-under-tier."""
    if meta is None:
        raise _not_found()
    owner, book_id = meta
    if caller == owner:
        return owner
    if book_id is None:
        raise _not_found()  # book-less project -> owner-only
    lvl = await grant.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
        raise _not_found()  # non-grantee -> 404 (no oracle)
    if not lvl.at_least(need):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="insufficient access"
        )
    return owner


def _needs_glossary_kinds(params: dict[str, Any], pending: list) -> list[str]:
    """Kinds the user must act on in glossary. Prefer an explicit
    ``params.kinds`` (FE-supplied); else derive the proposed kind from the parked
    payloads (``payload.proposed_kind`` / ``payload.kind``)."""
    explicit = params.get("kinds")
    if isinstance(explicit, list) and explicit:
        return [str(k) for k in explicit]
    kinds: list[str] = []
    for it in pending:
        payload = it.payload or {}
        kind = payload.get("proposed_kind") or payload.get("kind")
        if kind and str(kind) not in kinds:
            kinds.append(str(kind))
    return kinds


def _book_id_for_handoff(meta, params: dict[str, Any]) -> str | None:
    """The book to deep-link into glossary for. Prefer the project's book (from
    meta); fall back to an explicit ``params.book_id`` (project no-book ->
    user glossary standards, no book_id)."""
    if meta is not None:
        _owner, book_id = meta
        if book_id is not None:
            return str(book_id)
    explicit = params.get("book_id")
    return str(explicit) if explicit else None


# Offset cursor: opaque base-10 string. Triage groups are small + admin-facing;
# an offset cursor is sufficient (no seek-key drift concerns like project list).
def _encode_offset(offset: int) -> str:
    return str(offset)


def _decode_offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        v = int(cursor)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid cursor"
        )
    if v < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid cursor"
        )
    return v
