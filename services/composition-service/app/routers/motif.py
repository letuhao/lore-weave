"""Narrative motif library router — W1 the user-driven HTTP CRUD surface.

`/v1/composition`:
  GET    /motifs                          — list (tier-merged: owned + system + own-public)
  GET    /motifs/catalog                  — PUBLIC discovery projection (allow-list, B-3)
  GET    /motifs/book/{book_id}            — the book's library: own + the SHARED tier (VIEW-gated)
  GET    /motifs/{id}                      — read one (owner full / public detail redacted)
  POST   /motifs                          — create (user tier; owner server-stamped)
  PATCH  /motifs/{id}[?book_id=]           — edit; owner-only, or a SHARED row (EDIT-gated)
  DELETE /motifs/{id}[?book_id=]           — soft archive; owner-only, or a SHARED row (EDIT-gated)
  POST   /motifs/{id}/adopt                — adopt into user | book (label) | book_shared (EDIT-gated)

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
    Motif, MotifCreateArgs, MotifLinkKind, MotifPatchArgs, _ForbidExtra, _Key,
)
from app.db.repositories import VersionMismatchError
from app.db.repositories.motif_repo import MotifRepo
from app.deps import get_grant_client_dep, get_motif_repo
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0-4c book-grant chokepoint → HTTP (mirrors works._gate_book). none→404 (no oracle),
    under→403. The book grant is the access control for a book-scoped motif op (adopt-to-book,
    the shared-tier read/write) — the HTTP route must be NO softer than the MCP path."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")

# The uniform "no existence oracle" 404 (H13) — identical for missing, foreign-
# private, and not-owned-on-write, so a caller can't distinguish them.
_NOT_FOUND = {"code": "MOTIF_NOT_FOUND", "message": "motif not found or not accessible"}

# Fields a NON-OWNER must never receive on a public motif's DETAIL read (B-3):
# examples (may carry imported source prose — copyright); source_ref is replaced
# by its opaque lineage token (never raw); embedding is already off the projection.
_PUBLIC_DETAIL_REDACT = ("examples",)


class MotifAdopt(_ForbidExtra):
    # target='user'        — the caller's own private library (default; no book context).
    # target='book'        — model A: a PRIVATE per-user label on the clone (D-MOTIF-ADOPT-PER-BOOK).
    # target='book_shared' — model B: the book's SHARED tier (D-MOTIF-ADOPT-BOOK-COLLAB-TIER).
    # 'book'/'book_shared' REQUIRE book_id + EDIT on that book (gated before the clone — the HTTP
    # route is no softer than the MCP path; D-MOTIF-HTTP-ADOPT-BOOK). retag_genres drives the
    # cross-genre clone (R2.2).
    target: str = Field(default="user", pattern="^(user|book|book_shared)$")
    book_id: UUID | None = None
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
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """Tier-merged list under the read predicate. `scope=mine` (owner=caller),
    `system` (owner NULL), `all` (owned + system; NOT others' public — that is the
    catalog). Full owner/author view (the caller owns or is the platform for every
    row). `embedding` is never projected. `offset` paginates a >limit library (§2#9 scale)."""
    repo_scope = "user" if scope == "mine" else scope  # repo names the owned scope 'user'
    rows = await repo.list_for_caller(
        user_id, scope=repo_scope, genre=genre, kind=kind, status=status,
        q=q, language=language, limit=limit, offset=offset,
    )
    return {
        "motifs": [m.model_dump(mode="json") for m in rows],
        "scope": scope,
        "limit": limit,
        "offset": offset,
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


def _book_view(motif: Motif, *, caller_id: UUID) -> dict[str, Any]:
    """Book-library projection (D-MOTIF-ADOPT-BOOK-COLLAB-TIER): own rows full; a SHARED row
    owned by another collaborator gets the B-3 redaction (no examples / opaque source_ref / no
    owner) but keeps book_id + book_shared so the FE can badge it + route an edit to the shared
    path. Mirrors the MCP _motif_book_view."""
    is_owner = motif.owner_user_id is not None and motif.owner_user_id == caller_id
    data = _redact_for_viewer(motif, is_owner=is_owner)
    data["book_id"] = str(motif.book_id) if motif.book_id else None
    data["book_shared"] = bool(motif.book_shared)
    return data


@router.get("/motifs/book/{book_id}")
async def list_book_motifs(
    book_id: UUID,
    genre: str | None = Query(default=None, max_length=100),
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=20),
    status: str = Query(default="active", pattern="^(draft|active|archived)$"),
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """The book's motif library (D-MOTIF-ADOPT-BOOK-COLLAB-TIER): the caller's own motifs
    (globals + this book's private labels) PLUS the book's SHARED tier (book_shared rows from
    any collaborator). VIEW on the book required (the grant is the access control). Shared rows
    are badged book_shared=true."""
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    rows = await repo.list_in_book(
        user_id, book_id, genre=genre, kind=kind, status=status,
        q=q, language=language, limit=limit,
    )
    return {
        "motifs": [_book_view(m, caller_id=user_id) for m in rows],
        "book_id": str(book_id),
        "count": len(rows),
    }


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
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
    book_id: UUID | None = Query(default=None),
) -> dict[str, Any]:
    """Edit a motif. Default (no book_id) = OWNER-only edit (the repo filters
    owner_user_id=caller — a system or foreign row never matches → 404, the 'clone to
    edit' affordance). Pass `book_id` to edit a SHARED book-tier motif
    (D-MOTIF-ADOPT-BOOK-COLLAB-TIER): any EDIT-grantee of that book may edit it
    (EDIT-gated here, then the repo matches book_shared AND book_id). Optimistic
    concurrency via If-Match → 412. Flipping visibility INTO a shareable state runs the
    publish quota pre-check (un-publishing never hits quota); a shared row stays private (a
    visibility flip on the shared path is refused up front with a 400, not a DB 500)."""
    if book_id is not None:
        # SHARED-tier edit: the book grant is the gate (not ownership). A shared row is private by
        # the motif_book_shared_shape CHECK — reject a visibility flip up front (a clean 400, not a
        # DB CheckViolation 500). Publishing is the owner's separate flip on their OWN copy.
        if body.visibility is not None and body.visibility != "private":
            raise HTTPException(status_code=400, detail={
                "code": "MOTIF_SHARED_STAYS_PRIVATE",
                "message": "a shared book-tier motif stays private; publish from your own copy instead",
            })
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
        try:
            motif = await repo.patch_shared(
                user_id, motif_id, book_id, body, expected_version=_parse_if_match(if_match),
            )
        except VersionMismatchError as exc:
            raise HTTPException(status_code=412, detail={
                "code": "MOTIF_VERSION_CONFLICT",
                "current": exc.current.model_dump(mode="json"),
            })
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail={
                "code": "MOTIF_CODE_EXISTS",
                "message": "a motif with this code + language already exists in this book",
            })
        if motif is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        return motif.model_dump(mode="json")
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
    grant: GrantClient = Depends(get_grant_client_dep),
    book_id: UUID | None = Query(default=None),
) -> dict[str, Any]:
    """Soft archive (status='archived'). Default (no book_id) = owner-only. Pass
    `book_id` to archive a SHARED book-tier motif (D-MOTIF-ADOPT-BOOK-COLLAB-TIER) — any
    EDIT-grantee may (EDIT-gated here, then the repo matches book_shared AND book_id). NOT
    a hard delete — the motif_application FK is SET NULL so the binding-ledger history
    survives. A foreign/missing/system row is a no-op (archived:true uniformly — no oracle;
    the repo only touches an in-scope row)."""
    if book_id is not None:
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
        await repo.archive_shared(user_id, motif_id, book_id)
        return {"id": str(motif_id), "archived": True}
    await repo.archive(user_id, motif_id)
    return {"id": str(motif_id), "archived": True}


# ── adopt (the clone primitive) ──────────────────────────────────────────────


@router.post("/motifs/{motif_id}/adopt")
async def adopt_motif(
    motif_id: UUID,
    body: MotifAdopt | None = None,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Adopt = the ONE clone primitive (= adopt = customize = cross-genre retag,
    R1.1.1). Clones a visible (public/system/own) motif into a target tier as a
    private 'adopted' row (vector copied, source_ref = opaque lineage token,
    version=1). target='user' (default) → the caller's own library; target='book' →
    a private per-book label; target='book_shared' → the book's SHARED tier
    (D-MOTIF-HTTP-ADOPT-BOOK / -BOOK-COLLAB-TIER). A book target REQUIRES book_id +
    EDIT on that book (gated here, no softer than MCP). Idempotent: a repeat adopt of
    the same source into the same tier returns the existing clone. Count-gated (B-4).
    A not-visible source → 404 (no oracle)."""
    target = body.target if body is not None else "user"
    book_id = body.book_id if body is not None else None
    book_shared = target == "book_shared"
    if target in ("book", "book_shared"):
        if book_id is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "MOTIF_BOOK_REQUIRED",
                        "message": f"book_id is required when target='{target}'"},
            )
        # EDIT-gate the book BEFORE the clone — the grant is the tenancy boundary for a
        # book-scoped adopt (D-MOTIF-HTTP-ADOPT-BOOK). none→404, under-tier→403.
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    await _adopt_quota_guard(repo, user_id)
    retag = body.retag_genres if body is not None else None
    try:
        motif, created = await repo.adopt(
            user_id, motif_id, retag_genres=retag,
            book_id=book_id, book_shared=book_shared,
        )
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
    # NOT for a book_shared root: the members would be cloned into the adopter's PRIVATE
    # tier (invisible to other grantees) under a shared root — a half-shared pattern. Shared
    # member expansion is deferred (D-MOTIF-LINK-SHARED-TIER); the shared root stands alone.
    members_adopted = 0
    if created and motif.kind == "pattern" and not book_shared:
        members_adopted = await repo.adopt_pattern_members(user_id, motif_id, motif.id)
    body_out = motif.model_dump(mode="json")
    body_out["members_adopted"] = members_adopted
    status_code = 201 if created else 200
    return JSONResponse(status_code=status_code, content=body_out)


# ── the motif graph (BE-M3) — composed_of · precedes · variant_of ────────────
# These REST routes wrap the SAME MotifRepo.{list,create,delete}_link methods that back
# the `composition_motif_link_*` MCP tools (server.py) — the graph was agent-only (no REST,
# no GUI) until now. The DB `motif_link_guard` trigger is the spec: a self-link / cycle /
# cross-tier edge is a 409 the FE renders inline, NOT a swallowed toast (plan 33 §3.1).


class MotifLinkCreateBody(_ForbidExtra):
    to_motif_id: UUID
    kind: MotifLinkKind
    ord: int | None = None
    # book_id: set to link two SHARED motifs of that book (needs EDIT on the book; both
    # endpoints must be book_shared in it). Omit for your own user-tier graph.
    book_id: UUID | None = None


@router.get("/motifs/{motif_id}/links")
async def list_motif_links(
    motif_id: UUID,
    direction: str = Query(default="both"),
    kinds: list[str] | None = Query(default=None),
    book_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """List one motif's relationship edges — `composed_of` members, `precedes`
    successors, `variant_of` siblings — each joined to the neighbor's id/code/name.
    `direction`: 'out' (this→neighbor), 'in', or 'both' (default). A not-visible anchor
    returns an empty list (IDOR-safe — empty is indistinguishable from 'no edges', no
    existence oracle). Pass `book_id` to read a SHARED book motif's graph (VIEW-gated)."""
    if direction not in ("out", "in", "both"):
        raise HTTPException(status_code=422, detail={
            "code": "MOTIF_LINK_DIRECTION",
            "message": "direction must be 'out', 'in', or 'both'",
        })
    if book_id is not None:
        await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    links = await repo.list_links(
        user_id, motif_id, direction=direction, kinds=kinds, book_id=book_id,
    )
    return {"motif_id": str(motif_id), "links": links, "count": len(links)}


@router.post("/motifs/{motif_id}/links", status_code=201)
async def create_motif_link(
    motif_id: UUID,
    body: MotifLinkCreateBody,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Create an edge FROM this motif TO another. Default: BOTH endpoints must be motifs
    you OWN (a user may not touch the system/foreign graph). Pass `book_id` to link two
    SHARED motifs of that book (EDIT-gated). A self-link / cycle / cross-tier edge (the
    `motif_link_guard` trigger) → 409; a duplicate edge → 409; an endpoint out of the
    required scope → 404 (no oracle)."""
    if body.book_id is not None:
        await _gate_book(grant, body.book_id, user_id, GrantLevel.EDIT)
    try:
        link = await repo.create_link(
            user_id, motif_id, body.to_motif_id, body.kind,
            ord=body.ord, book_id=body.book_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_LINK_EXISTS", "message": "that edge already exists",
        })
    except asyncpg.CheckViolationError:
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_LINK_INVALID",
            "message": ("a motif cannot precede itself, and a cycle would make the "
                        "succession chain unresolvable"),
        })
    return link.model_dump(mode="json")


@router.delete("/motif-links/{link_id}", status_code=200)
async def delete_motif_link(
    link_id: UUID,
    book_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Delete one edge (hard delete — edges have no children). Default: the edge must be
    on one of YOUR motifs. Pass `book_id` to delete an edge in that book's SHARED graph
    (EDIT-gated). A foreign / system / missing / wrong-book edge → 404 (no oracle)."""
    if book_id is not None:
        await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    deleted = await repo.delete_link(user_id, link_id, book_id=book_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"deleted": True, "link_id": str(link_id)}


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
