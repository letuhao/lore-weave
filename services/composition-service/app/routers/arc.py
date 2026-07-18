"""Arc-template library router — W10 the user-driven HTTP CRUD + apply-preview surface.

`/v1/composition`:
  GET    /arc-templates                    — list (tier-merged: owned + system + own-public)
  GET    /arc-templates/catalog            — PUBLIC discovery projection (allow-list, B-3)
  GET    /arc-templates/{id}               — read one
  POST   /arc-templates                    — create (user tier; owner server-stamped)
  PATCH  /arc-templates/{id}               — edit / flip visibility (= publish); owner-only
  DELETE /arc-templates/{id}               — soft archive; owner-only, or a SHARED row (EDIT-gated)
  POST   /arc-templates/{id}/restore[?book_id=] — un-archive (S-08); owner-only, or a SHARED row (EDIT-gated)
  POST   /arc-templates/{id}/adopt         — adopt = clone-to-customize = cross-genre retag
  POST   /arc-templates/{id}/apply         — apply-PREVIEW: rescale + roster-bind + drop/merge plan

Mirrors motif.py exactly (tenancy, error shapes, the uniform H13 404, the publish quota
pre-check). The `apply` endpoint is the §12.5 decompose-at-arc-scale PREVIEW: a PURE,
deterministic plan (proportional placement-rescale R2.5 + roster-bind-once + a §12.6
drop/merge report) — it does NOT materialize outline_node rows or invoke the LLM planner
(that deep integration is the W10 live-smoke follow-up, D-W10-APPLY-PLANNER-MATERIALIZE).
The apply-preview is non-agentic CRUD-shaped read (§13.3) → HTTP is fine here.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _dec
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from loreweave_mcp.errors import NOT_ACCESSIBLE_MESSAGE

from app.config import settings
from app.db.models import (
    ArcApplyArgs,
    ArcTemplate,
    ArcTemplateCreateArgs,
    ArcTemplatePatchArgs,
    _ForbidExtra,
    _Key,
)
from app.clients.book_client import BookClient, BookClientError
from app.db.pool import get_pool
from app.db.repositories import VersionMismatchError
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.references import reference_embed_model
from app.db.repositories.structure import StructureConflictError, StructureRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_arc_template_repo,
    get_book_client_dep,
    get_grant_client_dep,
    get_outline_repo,
)
from app.engine.arc_apply import build_apply_plan, extract_template_from_arc
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError
from pydantic import BaseModel, ConfigDict, Field, field_validator

router = APIRouter(prefix="/v1/composition")

# The uniform "no existence oracle" 404 (H13) — identical for missing, foreign-private,
# and not-owned-on-write, so a caller can't distinguish them.
_NOT_FOUND = {
    "code": "ARC_TEMPLATE_NOT_FOUND",
    "message": "arc template not found or not accessible",
}


class ArcAdopt(_ForbidExtra):
    # NO target arg — the adopt target is ALWAYS the caller's own user tier (mirrors
    # MotifAdopt). retag_genres drives the cross-genre clone.
    retag_genres: list[_Key] | None = Field(default=None, max_length=40)


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


def _require_if_match(if_match: str | None) -> int:
    """BE-A2 — `PATCH /arcs/{id}` REQUIRES If-Match. The MCP door already requires
    `expected_version` (server.py `_ArcUpdateArgs`); the REST door made it OPTIONAL, so a
    missing header skipped BOTH the version clause AND the `version = version + 1` bump
    (structure.py) — a blind clobber that also left a concurrent v7 holder able to keep
    writing against replaced content. Absent ⇒ 428 Precondition Required, never a clobber."""
    if if_match is None:
        raise HTTPException(status_code=428, detail={
            "code": "IF_MATCH_REQUIRED",
            "message": "If-Match: <version> is required — refetch the arc and retry.",
        })
    parsed = _parse_if_match(if_match)
    assert parsed is not None  # _parse_if_match only returns None for a None input
    return parsed


async def _publish_quota_guard(repo: ArcTemplateRepo, caller_id: UUID) -> None:
    """B-4 publish ceiling — informative refusal (NOT the uniform not-accessible error;
    a quota condition is not an ownership one). 0 = unlimited."""
    if settings.motif_max_public <= 0:
        return
    n = await repo.count_shared_by_owner(caller_id)
    if n >= settings.motif_max_public:
        raise HTTPException(status_code=409, detail={
            "code": "ARC_TEMPLATE_PUBLISH_LIMIT_REACHED",
            "limit": settings.motif_max_public,
            "message": f"published arc-template limit reached ({settings.motif_max_public}) "
                       "— unpublish one first",
        })


# ── list / catalog / read ─────────────────────────────────────────────────────────


@router.get("/arc-templates")
async def list_arc_templates(
    scope: str = Query(default="all", pattern="^(mine|system|all)$"),
    genre: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=20),
    status: str = Query(default="active", pattern="^(draft|active|archived)$"),
    limit: int = Query(default=50, ge=1, le=100),
    book_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Tier-merged list under the read predicate. `scope=mine` (owner=caller), `system`
    (owner NULL), `all` (owned + system; NOT others' public — that is the catalog). Full
    owner view; `embedding` is never projected.

    D-ARC-TEMPLATE-BOOK-TIER: pass `book_id` to ALSO surface that book's SHARED tier — the
    caller must have VIEW on it (gated here BEFORE the repo sees it; a non-grantee's book_id
    is rejected, never silently honored)."""
    if book_id is not None:
        await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    repo_scope = "user" if scope == "mine" else scope
    rows = await repo.list_for_caller(
        user_id, scope=repo_scope, genre=genre, status=status,
        q=q, language=language, limit=limit, book_id=book_id,
    )
    return {
        "arc_templates": [a.model_dump(mode="json") for a in rows],
        "scope": scope,
        "limit": limit,
    }


@router.get("/arc-templates/catalog")
async def catalog_arc_templates(
    genre: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=20),
    sort: str = Query(default="recent", pattern="^(recent|name)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """PUBLIC discovery (B-3 analogue): visibility='public' + active only. Any authed
    user may read it (no grant). The projection is an explicit allow-list — embedding /
    raw source_ref / the heavy layout+roster are structurally excluded."""
    items, total = await repo.list_public(
        genre=genre, q=q, language=language, sort=sort, limit=limit, offset=offset,
    )
    out = []
    for it in items:
        row = {k: _jsonify(v) for k, v in it.items()}
        row["adopt_target"] = "user"
        out.append(row)
    return {"items": out, "total": total, "limit": limit, "offset": offset}


@router.get("/arc-templates/{arc_id}")
async def get_arc_template(
    arc_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    arc = await repo.get_visible(user_id, arc_id)
    if arc is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return arc.model_dump(mode="json")


# ── create / patch / archive ────────────────────────────────────────────────────────


@router.post("/arc-templates", status_code=201)
async def create_arc_template(
    body: ArcTemplateCreateArgs,
    target: str = Query(default="user", pattern="^(user|book_shared)$"),
    book_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Create an arc_template; owner_user_id is server-stamped = caller (the body cannot
    carry it — _ForbidExtra). A public/unlisted create runs the publish quota pre-check.
    A duplicate → 409.

    D-ARC-TEMPLATE-BOOK-TIER: `target='book_shared'` creates into a book's SHARED tier —
    it REQUIRES `book_id` + EDIT on that book (gated here, before the write; owner is
    attribution, the book's collaborators co-own it). The row stays visibility='private'."""
    book_shared = target == "book_shared"
    if book_shared:
        if book_id is None:
            raise HTTPException(status_code=400, detail={
                "code": "BOOK_ID_REQUIRED", "message": "target='book_shared' requires book_id"})
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    else:
        book_id = None  # a user-tier row never carries a book
    if body.visibility in ("public", "unlisted"):
        await _publish_quota_guard(repo, user_id)
    try:
        arc = await repo.create(user_id, body, book_id=book_id, book_shared=book_shared)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "ARC_TEMPLATE_CODE_EXISTS",
            "message": "an arc template with this code + language already exists",
        })
    return arc.model_dump(mode="json")


@router.patch("/arc-templates/{arc_id}")
async def patch_arc_template(
    arc_id: UUID,
    body: ArcTemplatePatchArgs,
    book_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    """Owner-only edit (the repo filters owner_user_id=caller — a system or foreign row
    never matches → 404, the 'clone to edit' affordance). Optimistic concurrency via
    If-Match → 412. Flipping visibility INTO a shareable state runs the publish quota
    pre-check (un-publishing never hits quota).

    D-ARC-TEMPLATE-BOOK-TIER: pass `book_id` to edit a BOOK-SHARED row as a collaborator —
    it REQUIRES EDIT on that book (gated here; the repo then allows a non-owner grantee to
    write the shared row). A book_shared row can never be flipped public (the shape CHECK)."""
    if book_id is not None:
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    if body.visibility in ("public", "unlisted"):
        current = await repo.get_visible(user_id, arc_id, book_id=book_id)
        already_shared = (
            current is not None
            and current.owner_user_id == user_id
            and current.visibility in ("public", "unlisted")
        )
        if not already_shared:
            await _publish_quota_guard(repo, user_id)
    try:
        arc = await repo.patch(
            user_id, arc_id, body, expected_version=_parse_if_match(if_match), book_id=book_id,
        )
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={
            "code": "ARC_TEMPLATE_VERSION_CONFLICT",
            "current": exc.current.model_dump(mode="json"),
        })
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "ARC_TEMPLATE_CODE_EXISTS",
            "message": "an arc template with this code + language already exists",
        })
    if arc is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return arc.model_dump(mode="json")


@router.delete("/arc-templates/{arc_id}", status_code=200)
async def archive_arc_template(
    arc_id: UUID,
    book_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Soft archive (status='archived'), owner-only. A foreign/missing/system row is a
    no-op (router returns archived:true uniformly — no oracle). D-ARC-TEMPLATE-BOOK-TIER:
    pass `book_id` (EDIT-gated) to archive a book-SHARED row as a collaborator."""
    if book_id is not None:
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    await repo.archive(user_id, arc_id, book_id=book_id)
    return {"id": str(arc_id), "archived": True}


@router.post("/arc-templates/{arc_id}/restore", status_code=200)
async def restore_arc_template(
    arc_id: UUID,
    book_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Un-archive (S-08) — the reverse of DELETE /arc-templates/{id}. Owner-only by default; pass
    `book_id` (EDIT-gated) to restore a book-SHARED row (D-ARC-TEMPLATE-BOOK-TIER). Returns the restored
    row (so the library refreshes). 404 if no archived arc-template with that id is restorable by you."""
    if book_id is not None:
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    arc = await repo.restore(user_id, arc_id, book_id=book_id)
    if arc is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return arc.model_dump(mode="json")


# ── adopt (the clone primitive) ──────────────────────────────────────────────────────


@router.post("/arc-templates/{arc_id}/adopt")
async def adopt_arc_template(
    arc_id: UUID,
    body: ArcAdopt | None = None,
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Adopt = the clone primitive (= adopt = customize = cross-genre retag). Clones a
    visible (public/system/own) arc_template into the caller's OWN tier as a private row
    (owner reset to caller, vector copied, source_ref = opaque lineage token, version=1).
    A not-visible source → 404 (no oracle). A code collision in the caller's tier → 409
    (the caller owns the rename policy)."""
    retag = body.retag_genres if body is not None else None
    try:
        arc = await repo.clone(user_id, arc_id, target_owner=user_id, retag_genres=retag)
    except LookupError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "ARC_TEMPLATE_CODE_EXISTS",
            "message": "an arc template with this code + language already exists "
                       "— rename or retag before adopting",
        })
    return JSONResponse(status_code=201, content=arc.model_dump(mode="json"))


# ── apply (the §12.5 decompose-at-arc-scale PREVIEW — pure, deterministic) ────────────


@router.post("/arc-templates/{arc_id}/apply")
async def apply_arc_template(
    arc_id: UUID,
    body: ArcApplyArgs,
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Apply-PREVIEW (§12.5): given a visible arc_template + a target chapter count + a
    roster binding, return the deterministic apply PLAN — R2.5 proportional placement-
    rescale of every layout placement into [1..target], the arc_roster bound ONCE and
    propagated to every placement, the per-chapter interleave, and a §12.6 drop/merge
    report (a motif lost to a scale-mismatch is NEVER silent). PURE: no outline_node
    materialization, no LLM, nothing persisted (the deep planner integration is the W10
    live-smoke follow-up, D-W10-APPLY-PLANNER-MATERIALIZE). A not-visible source → 404."""
    arc = await repo.get_visible(user_id, arc_id)
    if arc is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    plan = build_apply_plan(arc, body)
    return plan.model_dump(mode="json")


def _jsonify(value: Any) -> Any:
    """Catalog allow-list values come straight off asyncpg (UUID/datetime/Decimal/list)
    — coerce the non-JSON-native ones for the response."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, _dec.Decimal):
        return float(value)
    return value


# ══════════════════════════════════════════════════════════════════════════════
# 23 B (CF-9) — structure_node (the durable SPEC layer) REST mirrors.
#
# MCP-first governs AGENT logic; a human GUI cannot call MCP tools, and every
# Studio panel writes REST (OutlineTree's reorder/patch If-Match OCC is the
# precedent — 24 PH20/OQ-3). So every composition_arc_* tool gets a REST route
# over the SAME StructureRepo method (one repo method, two front doors: the Hub's
# drag-drop transport here, the agent's MCP tool in app/mcp/server.py). Access is
# the E0 book grant, gated BEFORE the repo (25 PM-8): book-scoped routes gate the
# path book_id; by-id routes resolve the node's book from the ROW and gate on ITS
# book_id (`worker-loaded-id-needs-parent-scoping`). `created_by` is a plain actor
# stamp (never a scope key). Reads mirror too.
#
# `structure_node` is PER-BOOK (BA8), so these routes are keyed by book_id/node_id,
# NOT project_id — distinct from the /works/{project_id}/* outline routes.
# ══════════════════════════════════════════════════════════════════════════════


_ArcStatusREST = Literal["empty", "outline", "drafting", "done"]


# ── D-ARC-TRACKS-ROSTER-SCHEMA (spec 32a §A) — typed cascade entries ────────────
# `tracks`/`roster` were `list[dict[str, Any]]` free blobs at both doors. `_merge_by`
# (structure.py) shadows by `key`; a MISSING key ⇒ un-overridable garbage, an EMPTY key ⇒
# every empty-keyed entry across the ancestor chain collides on "" and the leaf eats the
# root's. The ONLY hard rule is therefore the key: non-empty + unique within the node.
# `extra="allow"` (not forbid): the packer reads other fields leniently, and forbidding a
# richer agent write — or dropping its extra fields on a round-trip — would be a regression,
# not a fix. The vocabulary of `constraints[]` stays deliberately OPEN (shape only).
class ArcTrack(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str = Field(min_length=1)
    label: str = ""


class ArcRosterSlot(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str = Field(min_length=1)
    actant: str | None = None
    label: str | None = None
    constraints: list[str] = Field(default_factory=list)


def _reject_within_node_dupes(v: list[ArcTrack] | list[ArcRosterSlot] | None):
    """AI-3 — a duplicate key WITHIN one node's own list is the corruption (across-chain
    shadowing by key is intended). Named so the panel/agent can fix it, never silent."""
    if not v:
        return v
    seen: set[str] = set()
    for it in v:
        if it.key in seen:
            raise ValueError(
                f"ARC_ENTRY_KEY_DUPLICATE: '{it.key}' — track/roster keys must be unique within an arc"
            )
        seen.add(it.key)
    return v


class _ArcContent(BaseModel):
    """The cascade content fields shared by create + patch, with the key invariant."""
    tracks: list[ArcTrack] | None = None
    roster: list[ArcRosterSlot] | None = None
    roster_bindings: dict[str, Any] | None = None

    _v_tracks = field_validator("tracks")(_reject_within_node_dupes)
    _v_roster = field_validator("roster")(_reject_within_node_dupes)


# Dict-form validators for the MCP door (server.py `_ArcCreateArgs`/`_ArcUpdateArgs` keep the
# args as `list[dict]` so the repo call site is unchanged): validate each entry against the
# same ArcTrack/ArcRosterSlot invariant (raises on a missing/empty/duplicate key), keep dicts.
# ONE definition of the key rule across both doors (the 3-schema-source discipline).
def validate_track_dicts(v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not v:
        return v
    _reject_within_node_dupes([ArcTrack.model_validate(d) for d in v])
    return v


def validate_roster_dicts(v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not v:
        return v
    _reject_within_node_dupes([ArcRosterSlot.model_validate(d) for d in v])
    return v


class ArcCreate(_ArcContent):
    kind: Literal["saga", "arc"] = "arc"
    parent_arc_id: UUID | None = None
    title: str = ""
    summary: str = ""
    goal: str = ""
    status: _ArcStatusREST = "outline"
    arc_template_id: UUID | None = None
    template_version: int | None = None


class ArcPatch(_ArcContent):
    title: str | None = None
    summary: str | None = None
    goal: str | None = None
    status: _ArcStatusREST | None = None
    arc_template_id: UUID | None = None
    template_version: int | None = None


class ArcMove(BaseModel):
    new_parent_arc_id: UUID | None = None   # None = a root
    after_id: UUID | None = None            # place AFTER this sibling; None = first


class ArcAssignChapters(BaseModel):
    # BE-A3: `null` UNASSIGNS the chapters (returns them to the ?unassigned=true pool). The
    # children route already READS that pool, so add-only assign left a state no writer could
    # produce — this closes the inverse gap (GG-2).
    structure_node_id: UUID | None = None
    chapter_node_ids: list[UUID]


def _structures() -> StructureRepo:
    return StructureRepo(get_pool())


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0 book-grant chokepoint → HTTP (mirrors outline._gate_book). none→404 (the
    uniform H13 message, no existence oracle), under-tier→403."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


async def _gate_arc(
    structures: StructureRepo, grant: GrantClient, caller: UUID, node_id: UUID,
    need: GrantLevel,
):
    """By-id routes: resolve the arc's book from the ROW (bare-id read), then gate
    the caller's grant on ITS book_id. A missing node returns the SAME uniform 404
    as a denied grant (no oracle). Returns the resolved node."""
    node = await structures.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _gate_book(grant, node.book_id, caller, need)
    return node


def _arc_conflict_http(exc: StructureConflictError) -> HTTPException:
    """Map a structure_node depth/cycle/cross-book trigger violation to a clean 400
    (mirrors the outline reorder BAD_REFERENCE precedent — never a 500)."""
    return HTTPException(status_code=400, detail={
        "code": "STRUCTURE_CONSTRAINT",
        "message": (
            "a saga cannot have a parent, nesting is capped at saga→arc→sub-arc "
            "(depth 2), no cycles, and a parent must be in the same book"
        ),
        "detail": str(exc)[:300],
    })


# ── reads ──────────────────────────────────────────────────────────────────────


@router.get("/books/{book_id}/arcs")
async def list_arcs(
    book_id: UUID,
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """The book's SPEC tree in one call (BA11 — the Chapter Browser's arc group
    headers without the N+1). Each node also carries the 24 PH9/OQ-2 DERIVED block
    (`span`, `is_contiguous`, `chapter_count`) the Plan Hub's arc shell (read surface
    #1) needs — computed in ONE aggregate query alongside the tree, additive so the
    Chapter Browser (which ignores them) is unaffected. VIEW on the book."""
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    structures = _structures()
    nodes = await structures.list_tree(book_id, include_archived=include_archived)
    derived = await structures.derived_blocks(book_id)
    empty = {"span": None, "is_contiguous": True, "chapter_count": 0, "first_story_order": None}
    out_nodes = []
    for n in nodes:
        d = n.model_dump(mode="json")
        d.update(derived.get(n.id, empty))
        out_nodes.append(d)
    return {"nodes": out_nodes, "book_id": str(book_id)}


@router.get("/books/{book_id}/parts")
async def list_parts(
    book_id: UUID,
    include_trashed: bool = False,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """C-merge C3 read-cutover — the Manuscript rail's part groupings, served from structure_node
    kind='part' (the C2 mirror of book-service parts) so the FE stops reading the parts TABLE and C4
    can drop it. Parts-compatible shape ({items:[...]}); sort_order is decoded from the mirror rank
    (the C2 reconcile encodes it fixed-width, so int(rank) is the original order). include_trashed adds
    archived 'part' nodes (a trashed book-service part → its mirror is archived) for the restore UI.
    VIEW on the book."""
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    nodes = await _structures().list_tree(book_id, kinds=("part",), include_archived=include_trashed)
    items = [
        {
            "part_id": str(n.id),
            "book_id": str(book_id),
            "title": n.title or None,
            "path": "",
            "sort_order": int(n.rank) if (n.rank or "").isdigit() else 0,
            "lifecycle_state": "trashed" if n.is_archived else "active",
        }
        for n in nodes
    ]
    return {"items": items}


@router.get("/arcs/{node_id}")
async def get_arc(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """One arc/saga, ENRICHED with the resolved cascade + derived span + open-
    promise rollup (the arc-inspector payload — BA7/BA6/BA15). VIEW on the book."""
    structures = _structures()
    node = await _gate_arc(structures, grant, user_id, node_id, GrantLevel.VIEW)
    threads_repo = NarrativeThreadRepo(get_pool())
    out = node.model_dump(mode="json")
    out["resolved"] = {
        "tracks": await structures.resolve_tracks(node.id),
        "roster": await structures.resolve_roster(node.id),
        "roster_bindings": await structures.resolve_roster_bindings(node.id),
    }
    # BE-A1: serve the SAME dense-ranked derived block the list route serves (span in reading
    # ORDINALS), NOT span()'s raw STRIDED min/max — that raw axis is the packer's input
    # (lenses.py) and MUST stay untouched, so we read derived_blocks here instead of touching
    # span(). An archived node is absent from derived_blocks ⇒ a NULL block: "not computed" is
    # deliberately distinct from a live 0-chapter arc's chapter_count: 0 (§3.4).
    _block = (await structures.derived_blocks(node.book_id)).get(node.id)
    out["span"] = _block["span"] if _block else None
    out["chapter_count"] = _block["chapter_count"] if _block else None
    out["is_contiguous"] = _block["is_contiguous"] if _block else None
    out["open_promises"] = [
        t.model_dump(mode="json")
        for t in await structures.open_promises(node.id, narrative_threads_repo=threads_repo)
    ]
    return out


# ── writes ─────────────────────────────────────────────────────────────────────


@router.post("/books/{book_id}/arcs", status_code=201)
async def create_arc(
    book_id: UUID,
    body: ArcCreate,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        node = await _structures().create_node(
            book_id,
            created_by=user_id,
            kind=body.kind,
            title=body.title, summary=body.summary, goal=body.goal, status=body.status,
            parent_id=body.parent_arc_id,
            tracks=body.tracks, roster=body.roster, roster_bindings=body.roster_bindings,
            arc_template_id=body.arc_template_id, template_version=body.template_version,
        )
    except StructureConflictError as exc:
        raise _arc_conflict_http(exc)
    return node.model_dump(mode="json")


@router.patch("/arcs/{node_id}")
async def patch_arc(
    node_id: UUID,
    body: ArcPatch,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    structures = _structures()
    node = await _gate_arc(structures, grant, user_id, node_id, GrantLevel.EDIT)
    # Auth (the gate) runs BEFORE the precondition check, so a non-grantee gets the uniform
    # 404 — never a 428 that would confirm the row exists (no existence oracle).
    expected_version = _require_if_match(if_match)
    patch = body.model_dump(exclude_unset=True)
    try:
        updated = await structures.update(
            node.id, patch, expected_version=expected_version,
        )
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={
            "code": "STRUCTURE_VERSION_CONFLICT",
            "current": exc.current.model_dump(mode="json"),
        })
    except StructureConflictError as exc:
        raise _arc_conflict_http(exc)
    if updated is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    return updated.model_dump(mode="json")


@router.delete("/arcs/{node_id}", status_code=200)
async def delete_arc(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    structures = _structures()
    node = await _gate_arc(structures, grant, user_id, node_id, GrantLevel.EDIT)
    await structures.archive(node.id)
    return {"id": str(node.id), "archived": True}


@router.post("/arcs/{node_id}/restore", status_code=200)
async def restore_arc(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    structures = _structures()
    node = await _gate_arc(structures, grant, user_id, node_id, GrantLevel.EDIT)
    await structures.restore(node.id)
    return {"id": str(node.id), "archived": False}


@router.post("/arcs/{node_id}/move", status_code=200)
async def move_arc(
    node_id: UUID,
    body: ArcMove,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    structures = _structures()
    node = await _gate_arc(structures, grant, user_id, node_id, GrantLevel.EDIT)
    try:
        moved = await structures.move(
            node.id, new_parent_id=body.new_parent_arc_id, after_id=body.after_id,
        )
    except StructureConflictError as exc:
        raise _arc_conflict_http(exc)
    if moved is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    return moved.model_dump(mode="json")


@router.post("/books/{book_id}/arcs/assign-chapters", status_code=200)
async def assign_arc_chapters(
    book_id: UUID,
    body: ArcAssignChapters,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Attach chapter-kind outline nodes to an arc (book-scoped both sides). EDIT."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    count = await _structures().assign_chapters(
        book_id, body.structure_node_id, body.chapter_node_ids,
    )
    return {
        "assigned": count,
        "structure_node_id": str(body.structure_node_id) if body.structure_node_id else None,
    }


# ── BE-7a (spec 34) — the REST twin of composition_arc_extract_template. "Save this arc as a
#    template" is a Tier-A WRITE, so it gets a REST route (NOT a bridge allowlist entry — the
#    allowlist's contract is "nothing here writes"). Mirrors the MCP handler verbatim, incl. the
#    UniqueViolationError → 409 map (the engine deliberately does not swallow it). ──────────────
class ArcExtractTemplate(BaseModel):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    language: str = "en"
    # 'public' is excluded at create — publishing is the separate library visibility flip.
    visibility: Literal["private", "unlisted"] = "private"


@router.post("/arcs/{node_id}/extract-template", status_code=201)
async def extract_arc_template(
    node_id: UUID,
    body: ArcExtractTemplate,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Save an authored arc (a structure_node) as a reusable arc TEMPLATE in the caller's own
    library. Reading the arc to extract from it ⇒ VIEW on its book (derived from the ROW); the
    new template is owner-stamped to the caller. 409 on a duplicate (owner, code, language)."""
    structures = _structures()
    node = await _gate_arc(structures, grant, user_id, node_id, GrantLevel.VIEW)
    try:
        result = await extract_template_from_arc(
            get_pool(), arc_node=node, owner_user_id=user_id,
            code=body.code, name=body.name, language=body.language, visibility=body.visibility,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "ARC_TEMPLATE_CODE_EXISTS",
            "message": "an arc template with this code + language already exists in your library",
        })
    return result


# ── BE-7b (spec 34) — the REST twin of composition_arc_suggest. A READ, but it rides the REST
#    path like everything else the FE reaches (plan-30 §6.1), so it is a route, not a bridge entry. ──
# B-3 PRIVACY (mirrors mcp/server.py `_arc_public_projection`): a NON-owned candidate's raw
# source_ref / embedding / owner are STRIPPED — the shareable thing is the abstract structure, never
# another user's imported-source reference. Drop-set pinned by a test so the two projections can't drift.
_ARC_PUBLIC_DROP = frozenset({
    "embedding", "embedding_model", "embedding_dim", "source_ref", "owner_user_id", "source_version",
})


def _arc_public_projection(arc: Any) -> dict[str, Any]:
    return {k: v for k, v in arc.model_dump(mode="json").items() if k not in _ARC_PUBLIC_DROP}


class ArcSuggest(BaseModel):
    project_id: UUID
    premise: str | None = None
    genre: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
    detail: Literal["summary", "full"] = "full"


@router.post("/arc-templates/suggest")
async def suggest_arc_templates(
    body: ArcSuggest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Rank the caller-visible arc templates that fit a Work's premise/genre. VIEW on the Work's
    book (derived from the row). A non-owned candidate is projected through the B-3 allow-list."""
    work = await WorksRepo(get_pool()).get(body.project_id)
    if work is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    # Two-space retrieval (2026-07-17 tenancy re-design): the caller's OWN BYOK embed model
    # (from the Work settings) ranks their STRICTLY-PRIVATE arcs in their own space; None ⇒
    # those arcs fall back to non-semantic ranking (the platform never embeds private content).
    candidates = await MotifRetriever(get_pool()).retrieve_arcs(
        user_id, book_id=work.book_id, project_id=body.project_id,
        premise=body.premise, genre=body.genre, limit=body.limit,
        user_model=reference_embed_model(getattr(work, "settings", None)),
    )

    def _project(arc: Any) -> dict[str, Any]:
        is_owner = getattr(arc, "owner_user_id", None) == user_id
        if body.detail == "summary":
            # a lightweight ref (score + match_reason are kept at the wrapper) — Context Budget Law §6b
            return {
                "id": str(arc.id), "code": arc.code, "name": arc.name,
                "chapter_span": getattr(arc, "chapter_span", None),
                "genre_tags": list(getattr(arc, "genre_tags", []) or []),
                "mine": is_owner,
            }
        return arc.model_dump(mode="json") if is_owner else _arc_public_projection(arc)

    return {
        "candidates": [
            {"arc_template": _project(c.arc_template), "score": c.score, "match_reason": c.match_reason}
            for c in candidates
        ],
        "detail": body.detail,
        "count": len(candidates),
    }


# ── S-10 O6c — the REST twin of composition_decompile_arcs. "Group my chapters into arcs" is a
#    DETERMINISTIC ($0, no LLM, idempotent — reuses existing decompiled arcs by position) structural
#    write, so it gets an EDIT-gated REST route like the other arc twins (BE-7a/BE-7b). The agent path
#    stays confirm-token-gated (an agent's proposal needs human approval); a human clicking the button
#    IS the approval, so the direct twin is plain EDIT-gated — same shared engine either way. ──────────
class DecompileArcs(BaseModel):
    chapters_per_arc: int = Field(default=10, ge=1, le=100)


@router.post("/books/{book_id}/arcs/decompile", status_code=200)
async def decompile_book_arcs(
    book_id: UUID,
    body: DecompileArcs,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Group a book's chapters into arcs deterministically. EDIT on the book. Idempotent — re-running
    reuses existing decompiled arcs by position (safe to click twice). Returns the engine's
    `{arcs, chapters_assigned, arc_ids, reason?}` so the caller sees exactly what landed."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    from app.engine.arc_decompile import decompile_arcs
    return await decompile_arcs(
        get_pool(), book_id, created_by=user_id, chapters_per_arc=body.chapters_per_arc,
    )


# ── S-10 O3 — the read-only problems panel (the studio Issues tab). REST twin of the
#    composition_diagnostics MCP tool; BOTH call the shared build_book_diagnostics so the human panel
#    and the agent can never drift. Never spends (no LLM, no conformance run — it POINTS at the Tier-W
#    refresh). VIEW on the book. ─────────────────────────────────────────────────────────────────────
@router.get("/books/{book_id}/diagnostics")
async def book_diagnostics(
    book_id: UUID,
    limit: int = 25,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Everything wrong with this book, ranked error → warn → info (conformance, canon contradictions,
    broken canon rules, open-thread debt, prose-deleted spec nodes, unplanned chapters). Counts exact,
    rows capped. VIEW on the book; a non-grantee 404s at the gate (anti-oracle)."""
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    from app.services.agent_native import build_book_diagnostics, resolve_scope
    pool = get_pool()
    _work, pid = await resolve_scope(WorksRepo(pool), book_id)
    cap = max(1, min(int(limit), 100))
    diag = await build_book_diagnostics(pool, book_id=book_id, project_id=pid, user_id=user_id, cap=cap)
    return {"book_id": str(book_id), **diag.ranked(cap=cap)}


class ChapterReorder(BaseModel):
    """24 PH20 Row-3 — move a chapter in the book's READING order."""

    chapter_id: UUID          # book-service chapter_id (not the outline node id)
    after_chapter_id: UUID | None = None   # null ⇒ make it the first chapter


@router.post("/books/{book_id}/chapters/reorder", status_code=200)
async def reorder_book_chapters(
    book_id: UUID,
    body: ChapterReorder,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    book: BookClient = Depends(get_book_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Reorder a chapter in the manuscript, then rebuild composition's reading-axis mirror.

    Row-3 ("drag a chapter along its lane") is NOT a composition-local move: the Hub's x-axis is the
    book's reading order, which **book-service owns**. So this is the one gesture that crosses the
    seam, and it is exposed as ONE route so the client cannot leave the two halves inconsistent:

      1. book-service `POST /chapters/reorder` — the transactional renumber (it alone can permute the
         partial-unique slot index);
      2. `outline.resync_reading_order` — re-derive every chapter/scene `story_order` from the new
         truth AND remap the canon-rule anchors that ride the same axis.

    Both are individually idempotent, so a retry after a partial failure converges. If step 2 fails
    the manuscript IS reordered and only the mirror is stale — we say so explicitly (502
    MIRROR_RESYNC_FAILED) rather than reporting a clean success over a half-applied move
    (`silent-success-is-a-bug`); re-issuing the same request repairs it.

    EDIT on the book, enforced here AND again by book-service on the inner call.
    """
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        await book.reorder_chapters(
            book_id, body.chapter_id, body.after_chapter_id, bearer,
        )
    except BookClientError as exc:
        # Surface book-service's own 400/404/409 verbatim — it owns the rules (a chapter that is
        # not in the book, an after_id from another book, a non-active lifecycle).
        status = exc.status if exc.status in (400, 403, 404, 409) else 502
        raise HTTPException(status_code=status, detail={
            "code": exc.code or "BOOK_SERVICE_UNAVAILABLE", "detail": str(exc),
        }) from exc

    try:
        chapters = await book.list_chapters(book_id, bearer)
        sorts = {
            UUID(str(c["chapter_id"])): int(c["sort_order"])
            for c in chapters
            if c.get("chapter_id") is not None and c.get("sort_order") is not None
        }
        moved = await outline.resync_reading_order(book_id, sorts)
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail={
            "code": "MIRROR_RESYNC_FAILED",
            "detail": ("the chapter WAS reordered, but composition's reading-axis mirror could not "
                       "be rebuilt; re-issue this request to repair it"),
            "cause": str(exc),
        }) from exc
    return {"book_id": str(book_id), "resynced": moved}
