"""Narrative motif library router — W1 the user-driven HTTP CRUD surface.

`/v1/composition`:
  GET    /motifs                          — list (tier-merged: owned + system + own-public)
  GET    /motifs/catalog                  — PUBLIC discovery projection (allow-list, B-3)
  GET    /motifs/{id}                      — read one (owner full / public detail redacted)
  POST   /motifs                          — create (user tier; owner server-stamped)
  PATCH  /motifs/{id}                      — edit / flip visibility (= publish); owner-only
  DELETE /motifs/{id}                      — soft archive; owner-only
  POST   /motifs/{id}/adopt                — adopt = clone-to-customize = cross-genre retag

Tenancy (the kinds-bug fix + R1.1): owner_user_id is SERVER-STAMPED from the JWT
`sub` (never a request field — the *Args models forbid extra keys, S2). A read is
gated by the single F0 predicate (MotifRepo.get_visible: system | public | owner);
a missing/foreign-private motif → a uniform 404 "not found or not accessible" (no
existence oracle, H13). A write (patch/archive) is owner-only at the repo — a
system or another user's row never matches, so the FE "clone to edit" affordance
is the only way to customize a shared motif (you edit your clone, never the shared
original).

Publish (visibility → public/unlisted) and adopt are COUNT-gated against per-user
ceilings (B-4 — mirror D-MCP-BOOK-CREATE-QUOTA; 0 = unlimited). The publish-strip
DB trigger (F0) handles the B-3 source-prose strip for imported-derived rows on
ANY write path; the catalog projection is an explicit allow-list so embedding /
examples / raw source_ref never reach a non-owner.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _dec
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import Field

from app.config import settings
from app.db.models import (
    Motif, MotifCreateArgs, MotifPatchArgs, _ForbidExtra, _Key,
)
from app.db.repositories import VersionMismatchError
from app.db.repositories.motif_repo import MotifRepo
from app.deps import get_motif_repo
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")

# The uniform "no existence oracle" 404 (H13) — identical for missing, foreign-
# private, and not-owned-on-write, so a caller can't distinguish them.
_NOT_FOUND = {"code": "MOTIF_NOT_FOUND", "message": "motif not found or not accessible"}

# Fields a NON-OWNER must never receive on a public motif's DETAIL read (B-3):
# examples (may carry imported source prose — copyright); source_ref is replaced
# by its opaque lineage token (never raw); embedding is already off the projection.
_PUBLIC_DETAIL_REDACT = ("examples",)


class MotifAdopt(_ForbidExtra):
    # NO target arg — the adopt target is ALWAYS the caller's own user tier (book
    # tier dropped, R1.1.1). retag_genres drives the cross-genre clone (R2.2).
    retag_genres: list[_Key] | None = Field(default=None, max_length=40)


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


def _redact_for_viewer(motif: Motif, *, is_owner: bool) -> dict[str, Any]:
    """Owner sees the full view; a non-owner reading a PUBLIC motif's detail gets
    the meso content (roles/beats — legitimately public) but NOT examples, and
    `source_ref` is opaque-ized to its lineage token form (never a raw id). The
    `embedding` vector is already absent from the model projection (server-side).
    `owner_user_id` is dropped for a non-owner so a public motif's author isn't
    leaked by default (§4.2)."""
    data = motif.model_dump(mode="json")
    if is_owner:
        return data
    for field in _PUBLIC_DETAIL_REDACT:
        data[field] = []
    data["owner_user_id"] = None
    # source_ref already lands as the F0 'lineage:<id>' opaque token; if anything
    # else ever leaks through, opaque-ize defensively.
    sr = data.get("source_ref")
    if sr is not None and not str(sr).startswith("lineage:"):
        data["source_ref"] = None
    return data


async def _publish_quota_guard(repo: MotifRepo, caller_id: UUID) -> None:
    """B-4 publish ceiling — informative refusal (NOT the uniform not-accessible
    error; a quota condition is not an ownership one). 0 = unlimited."""
    if settings.motif_max_public <= 0:
        return
    n = await repo.count_shared_by_owner(caller_id)
    if n >= settings.motif_max_public:
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_PUBLISH_LIMIT_REACHED",
            "limit": settings.motif_max_public,
            "message": f"published-motif limit reached ({settings.motif_max_public}) "
                       "— unpublish one first",
        })


async def _adopt_quota_guard(repo: MotifRepo, caller_id: UUID) -> None:
    """B-4 adopt ceiling — informative refusal. 0 = unlimited."""
    if settings.motif_max_adopt <= 0:
        return
    n = await repo.count_adopted_by_owner(caller_id)
    if n >= settings.motif_max_adopt:
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_ADOPT_LIMIT_REACHED",
            "limit": settings.motif_max_adopt,
            "message": f"adopted-motif limit reached ({settings.motif_max_adopt}) "
                       "— archive one first",
        })


# ── list / catalog / read ───────────────────────────────────────────────────


@router.get("/motifs")
async def list_motifs(
    scope: str = Query(default="all", pattern="^(mine|system|all)$"),
    genre: str | None = Query(default=None, max_length=100),
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=20),
    status: str = Query(default="active", pattern="^(draft|active|archived)$"),
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """Tier-merged list under the read predicate. `scope=mine` (owner=caller),
    `system` (owner NULL), `all` (owned + system; NOT others' public — that is the
    catalog). Full owner/author view (the caller owns or is the platform for every
    row). `embedding` is never projected."""
    repo_scope = "user" if scope == "mine" else scope  # repo names the owned scope 'user'
    rows = await repo.list_for_caller(
        user_id, scope=repo_scope, genre=genre, kind=kind, status=status,
        q=q, language=language, limit=limit,
    )
    return {
        "motifs": [m.model_dump(mode="json") for m in rows],
        "scope": scope,
        "limit": limit,
    }


@router.get("/motifs/catalog")
async def catalog_motifs(
    genre: str | None = Query(default=None, max_length=100),
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=20),
    sort: str = Query(default="recent", pattern="^(recent|name)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """PUBLIC discovery (B-3): visibility='public' + active only. Any authed user
    may read it (no grant). The projection is an explicit allow-list — embedding /
    examples / raw source_ref are structurally excluded."""
    items, total = await repo.list_public(
        genre=genre, kind=kind, q=q, language=language,
        sort=sort, limit=limit, offset=offset,
    )
    # serialize the allow-list rows (UUID/datetime/Decimal → json) + adopt hint.
    out = []
    for it in items:
        row = {k: _jsonify(v) for k, v in it.items()}
        row["adopt_target"] = "user"
        out.append(row)
    return {"items": out, "total": total, "limit": limit, "offset": offset}


@router.get("/motifs/{motif_id}")
async def get_motif(
    motif_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    motif = await repo.get_visible(user_id, motif_id)
    if motif is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    is_owner = motif.owner_user_id is not None and motif.owner_user_id == user_id
    return _redact_for_viewer(motif, is_owner=is_owner)


# ── create / patch / archive ─────────────────────────────────────────────────


@router.post("/motifs", status_code=201)
async def create_motif(
    body: MotifCreateArgs,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """Create a user-tier motif; owner_user_id is server-stamped = caller (the
    body cannot carry it — _ForbidExtra). A public/unlisted create runs the
    publish quota pre-check first. A duplicate (owner, code, language) → 409."""
    if body.visibility in ("public", "unlisted"):
        await _publish_quota_guard(repo, user_id)
    try:
        motif = await repo.create(user_id, body)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_CODE_EXISTS",
            "message": "a motif with this code + language already exists",
        })
    return motif.model_dump(mode="json")


@router.patch("/motifs/{motif_id}")
async def patch_motif(
    motif_id: UUID,
    body: MotifPatchArgs,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    """Owner-only edit (the repo filters owner_user_id=caller — a system or
    foreign row never matches → 404, the 'clone to edit' affordance). Optimistic
    concurrency via If-Match → 412. Flipping visibility INTO a shareable state
    runs the publish quota pre-check (un-publishing never hits quota). A summary
    change clears the embed hash so W3 re-embeds (repo-side)."""
    # publish quota only when transitioning INTO a shareable state. We must know
    # the current visibility to avoid charging quota for a public→public no-op or
    # re-charging a row that is already shared.
    if body.visibility in ("public", "unlisted"):
        current = await repo.get_visible(user_id, motif_id)
        already_shared = (
            current is not None
            and current.owner_user_id == user_id
            and current.visibility in ("public", "unlisted")
        )
        if not already_shared:
            await _publish_quota_guard(repo, user_id)
    try:
        motif = await repo.patch(
            user_id, motif_id, body, expected_version=_parse_if_match(if_match),
        )
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={
            "code": "MOTIF_VERSION_CONFLICT",
            "current": exc.current.model_dump(mode="json"),
        })
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_CODE_EXISTS",
            "message": "a motif with this code + language already exists",
        })
    if motif is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return motif.model_dump(mode="json")


@router.delete("/motifs/{motif_id}", status_code=200)
async def archive_motif(
    motif_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """Soft archive (status='archived'), owner-only. NOT a hard delete — the
    motif_application FK is SET NULL so the binding-ledger history survives. A
    foreign/missing/system row is a no-op (router returns archived:true uniformly
    — no oracle; the repo only touches the caller's own row)."""
    await repo.archive(user_id, motif_id)
    return {"id": str(motif_id), "archived": True}


# ── adopt (the clone primitive) ──────────────────────────────────────────────


@router.post("/motifs/{motif_id}/adopt")
async def adopt_motif(
    motif_id: UUID,
    body: MotifAdopt | None = None,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """Adopt = the ONE clone primitive (= adopt = customize = cross-genre retag,
    R1.1.1). Clones a visible (public/system/own) motif into the caller's OWN tier
    as a private 'adopted' row (owner reset to caller, vector copied, source_ref =
    opaque lineage token, version=1). Idempotent: a repeat adopt of the same
    source returns the existing clone (200, no duplicate). Adopt is count-gated
    (B-4). A not-visible source → 404 (no oracle)."""
    await _adopt_quota_guard(repo, user_id)
    retag = body.retag_genres if body is not None else None
    try:
        motif, created = await repo.adopt(user_id, motif_id, retag_genres=retag)
    except LookupError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    except asyncpg.UniqueViolationError:
        # the suffix space was exhausted — surface as a code-conflict, not a 500.
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_CODE_EXISTS",
            "message": "could not allocate a free code for the adopted motif",
        })
    # if the source was a `pattern`, adopt its direct composed_of members + re-point
    # the edges at the caller's own copies (H-3 / MD-2(b)). Only on a FRESH adopt.
    members_adopted = 0
    if created and motif.kind == "pattern":
        members_adopted = await repo.adopt_pattern_members(user_id, motif_id, motif.id)
    body_out = motif.model_dump(mode="json")
    body_out["members_adopted"] = members_adopted
    status_code = 201 if created else 200
    return JSONResponse(status_code=status_code, content=body_out)


def _jsonify(value: Any) -> Any:
    """Catalog allow-list values come straight off asyncpg (UUID/datetime/Decimal/
    list) — coerce the non-JSON-native ones for the response."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, _dec.Decimal):
        return float(value)
    return value
