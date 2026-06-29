"""Arc-template library router — W10 the user-driven HTTP CRUD + apply-preview surface.

`/v1/composition`:
  GET    /arc-templates                    — list (tier-merged: owned + system + own-public)
  GET    /arc-templates/catalog            — PUBLIC discovery projection (allow-list, B-3)
  GET    /arc-templates/{id}               — read one
  POST   /arc-templates                    — create (user tier; owner server-stamped)
  PATCH  /arc-templates/{id}               — edit / flip visibility (= publish); owner-only
  DELETE /arc-templates/{id}               — soft archive; owner-only
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
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.models import (
    ArcApplyArgs,
    ArcTemplate,
    ArcTemplateCreateArgs,
    ArcTemplatePatchArgs,
    _ForbidExtra,
    _Key,
)
from app.db.repositories import VersionMismatchError
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.deps import get_arc_template_repo
from app.engine.arc_apply import build_apply_plan
from app.middleware.jwt_auth import get_current_user
from pydantic import Field

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
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Tier-merged list under the read predicate. `scope=mine` (owner=caller), `system`
    (owner NULL), `all` (owned + system; NOT others' public — that is the catalog). Full
    owner view; `embedding` is never projected."""
    repo_scope = "user" if scope == "mine" else scope
    rows = await repo.list_for_caller(
        user_id, scope=repo_scope, genre=genre, status=status,
        q=q, language=language, limit=limit,
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
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Create a user-tier arc_template; owner_user_id is server-stamped = caller (the
    body cannot carry it — _ForbidExtra). A public/unlisted create runs the publish
    quota pre-check first. A duplicate (owner, code, language) → 409."""
    if body.visibility in ("public", "unlisted"):
        await _publish_quota_guard(repo, user_id)
    try:
        arc = await repo.create(user_id, body)
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
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    """Owner-only edit (the repo filters owner_user_id=caller — a system or foreign row
    never matches → 404, the 'clone to edit' affordance). Optimistic concurrency via
    If-Match → 412. Flipping visibility INTO a shareable state runs the publish quota
    pre-check (un-publishing never hits quota)."""
    if body.visibility in ("public", "unlisted"):
        current = await repo.get_visible(user_id, arc_id)
        already_shared = (
            current is not None
            and current.owner_user_id == user_id
            and current.visibility in ("public", "unlisted")
        )
        if not already_shared:
            await _publish_quota_guard(repo, user_id)
    try:
        arc = await repo.patch(
            user_id, arc_id, body, expected_version=_parse_if_match(if_match),
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
    user_id: UUID = Depends(get_current_user),
    repo: ArcTemplateRepo = Depends(get_arc_template_repo),
) -> dict[str, Any]:
    """Soft archive (status='archived'), owner-only. A foreign/missing/system row is a
    no-op (router returns archived:true uniformly — no oracle; the repo only touches the
    caller's own row)."""
    await repo.archive(user_id, arc_id)
    return {"id": str(arc_id), "archived": True}


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
