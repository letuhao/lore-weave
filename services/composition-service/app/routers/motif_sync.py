"""W11 — motif publish/adopt SYNC surface (upstream-diff + apply-merge).

`/v1/composition`:
  GET  /motifs/{id}/upstream-diff  — "update available" + per-field diff for an
                                     adopted/cloned motif (carries a `lineage:`
                                     source_ref + a pinned `source_version`)
  POST /motifs/{id}/sync           — apply the chosen merge: accept selected
                                     upstream fields onto the local row, bump the
                                     local `version`, re-pin `source_version` to
                                     the upstream CURRENT version.

──────────────────────────────────────────────────────────────────────────────
HONESTY — why this is a TWO-WAY diff, not a true 3-way (the central design fact):

A true 3-way merge needs THREE texts: base (upstream AT the pinned
`source_version`), ours (the caller's local edits), theirs (upstream CURRENT).
But the `motif` table (app/db/migrate.py §motif) keeps ONLY the current row —
`version` is a single in-place INT counter bumped by patch(); there is NO
`motif_revision`/history table, so the *text* of the upstream at the pinned
version is GONE. We therefore CANNOT reconstruct a real base and DO NOT fabricate
one. The diff degrades to a deterministic **2-way** (ours vs theirs-CURRENT),
labelled `diff_mode="two_way"` + `base_available=False` in every response so the
FE renders an honest "ours vs upstream" picker, never a false 3-way auto-merge.

A genuine 3-way needs a schema change (a `motif_revision` history table or a
JSONB snapshot pinned at adopt time) — tracked as **D-MOTIF-SYNC-3WAY-BASE**
(defer gate #2 large/structural: schema migration). Wave2-RECONCILE §3 anticipates
exactly this degrade ("base = pinned `source_version`" is only a version *pin*, the
text is not retained).
──────────────────────────────────────────────────────────────────────────────

TENANCY (the kinds-bug fix + R1.1 / H13): the LOCAL motif is read via
MotifRepo.get_visible (system | public | owner) and re-checked owner-only on the
apply path (the repo's patch() filters owner_user_id=caller). The UPSTREAM row is
re-resolved under the SAME read predicate (you may only diff against an upstream
you can still see). A missing/foreign-private id → a uniform 404 "not found or not
accessible" (no existence oracle). Sync writes only the caller's own row.

COST: diff + merge are pure CRUD over the caller's own data — $0, no LLM/embed
call — so this is plain HTTP (§13.3), NOT a Tier-W confirm-token action. The
tenancy quota guard (publish ceiling) is the only gate, and it only fires when the
synced row is at a shareable visibility.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.config import settings
from app.db.models import Motif, MotifPatchArgs, _ForbidExtra, _Key
from app.db.repositories import VersionMismatchError
from app.db.repositories.motif_repo import MotifRepo
from app.deps import get_motif_repo
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")

# The uniform "no existence oracle" 404 (H13) — identical to motif.py so the two
# surfaces are indistinguishable to a probing caller.
_NOT_FOUND = {"code": "MOTIF_NOT_FOUND", "message": "motif not found or not accessible"}

# The fields a sync may carry from upstream → local. EXACTLY the user-editable
# content fields MotifPatchArgs accepts (summary, beats, roles, conditions, genre).
# owner/visibility/source_* are NOT here — sync never re-tiers or re-owns a row.
_MERGEABLE_FIELDS = ("summary", "genre_tags", "beats", "roles", "preconditions", "effects")

# The upstream columns the diff/merge reads (the mergeable set + the version pin +
# the tenancy predicate inputs). NEVER the full row / embedding / examples.
_UPSTREAM_COLS = (
    "id, owner_user_id, visibility, version, summary, genre_tags, "
    "beats, roles, preconditions, effects"
)
# The F0 read predicate, inlined for the direct upstream query ($1 = caller_id).
_VISIBLE_PREDICATE = "(owner_user_id IS NULL OR visibility = 'public' OR owner_user_id = $1)"


class MotifSyncBody(_ForbidExtra):
    """The apply-merge body. `accept` is the subset of mergeable fields to take
    FROM upstream (theirs); everything else keeps the local value (ours). An empty
    list = "keep all my edits but acknowledge the update" (re-pin only). A field
    outside _MERGEABLE_FIELDS is rejected by the validator → 422 (no smuggling a
    write to owner/visibility through the sync path)."""

    accept: list[_Key] = Field(default_factory=list, max_length=len(_MERGEABLE_FIELDS))

    def _validate_fields(self) -> None:
        bad = [f for f in self.accept if f not in _MERGEABLE_FIELDS]
        if bad:
            raise HTTPException(status_code=422, detail={
                "code": "MOTIF_SYNC_BAD_FIELD",
                "message": f"not a mergeable field: {bad}",
                "allowed": list(_MERGEABLE_FIELDS),
            })


def _lineage_src_id(source_ref: str | None) -> UUID | None:
    """The F0 lineage token is `lineage:<uuid>` (clone()/adopt() stamp it). Parse
    the upstream id out; anything else (None, opaque, malformed) → None (not adopted
    / no resolvable upstream)."""
    if not source_ref or not source_ref.startswith("lineage:"):
        return None
    try:
        return UUID(source_ref.split("lineage:", 1)[1])
    except (ValueError, IndexError):
        return None


async def _resolve_local_and_upstream(
    caller_id: UUID, motif_id: UUID, repo: MotifRepo,
) -> tuple[Motif, asyncpg.Record]:
    """Shared resolve for both surfaces: load the caller's LOCAL motif (read
    predicate → H13 404 on miss/foreign), confirm it carries a lineage (→ 409
    not-adopted), then re-resolve the UPSTREAM CURRENT row under the SAME predicate
    (→ 410 gone if it vanished/was archived since adopt). Returns (local, upstream)."""
    local = await repo.get_visible(caller_id, motif_id)
    if local is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    src_id = _lineage_src_id(local.source_ref)
    if src_id is None:
        raise HTTPException(status_code=409, detail={
            "code": "MOTIF_NOT_ADOPTED",
            "message": "this motif has no upstream lineage to sync against",
        })

    from app.db.pool import get_pool

    upstream = await get_pool().fetchrow(
        f"SELECT {_UPSTREAM_COLS} FROM motif "
        f"WHERE id = $2 AND {_VISIBLE_PREDICATE} AND status <> 'archived'",
        caller_id, src_id,
    )
    if upstream is None:
        raise HTTPException(status_code=410, detail={
            "code": "MOTIF_UPSTREAM_GONE",
            "message": "the upstream motif is no longer available",
        })
    return local, upstream


def _coerce_jsonb(value: Any) -> Any:
    """A JSONB column off asyncpg may be a json string or already a list — the diff
    compares structurally, so normalize the str form to its parsed value."""
    if isinstance(value, str):
        import json
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _field_diff(local: Motif, upstream: asyncpg.Record) -> dict[str, dict[str, Any]]:
    """Per-field 2-way diff (ours vs theirs-CURRENT). NO `base` key — we have no
    historical base (see module docstring). `changed` is a structural inequality."""
    fields: dict[str, dict[str, Any]] = {}
    for f in _MERGEABLE_FIELDS:
        ours = getattr(local, f)
        theirs = _coerce_jsonb(upstream[f])
        fields[f] = {"ours": ours, "theirs": theirs, "changed": ours != theirs}
    return fields


@router.get("/motifs/{motif_id}/upstream-diff")
async def upstream_diff(
    motif_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """The "update available" signal + per-field diff for an adopted motif.

    DEGRADED to 2-way (ours vs theirs-current) — `diff_mode="two_way"`,
    `base_available=False` — because no upstream history is retained (the table
    keeps only the current row; see module docstring + D-MOTIF-SYNC-3WAY-BASE).
    `update_available` is True when the upstream CURRENT version moved past the
    locally pinned `source_version`."""
    local, upstream = await _resolve_local_and_upstream(user_id, motif_id, repo)
    pinned = local.source_version
    upstream_version = int(upstream["version"])
    update_available = pinned is None or upstream_version > pinned
    return {
        "diff_mode": "two_way",
        "base_available": False,
        "pinned_source_version": pinned,
        "upstream_version": upstream_version,
        "update_available": update_available,
        "fields": _field_diff(local, upstream),
    }


async def _publish_quota_guard(repo: MotifRepo, caller_id: UUID) -> None:
    """B-4 publish ceiling — only consulted when the synced row is at a shareable
    visibility (mirrors motif.py). 0 = unlimited. A private sync never hits it."""
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


@router.post("/motifs/{motif_id}/sync")
async def sync_motif(
    motif_id: UUID,
    body: MotifSyncBody,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """Apply the chosen merge on confirm: take the `accept`-ed fields from upstream
    onto the local row, bump the local `version`, and re-pin `source_version` to the
    upstream CURRENT version (so the next diff is clean). Owner-only via the repo's
    optimistic-lock patch (a foreign/system row never matches → H13 404; a stale
    local row → 412, no silent overwrite). $0 — plain HTTP, no Tier-W token."""
    body._validate_fields()
    local, upstream = await _resolve_local_and_upstream(user_id, motif_id, repo)

    upstream_version = int(upstream["version"])

    # Publish ceiling only matters if THIS row is currently shareable (sync never
    # changes visibility, so we check the local row's existing state).
    if local.visibility in ("public", "unlisted"):
        await _publish_quota_guard(repo, user_id)

    # The merge is ONE atomic owner-scoped write (D-MOTIF-SYNC-REPIN-ATOMICITY): the
    # accepted CONTENT fields AND the source_version re-pin ride the SAME optimistic-lock
    # patch() UPDATE (repin_source_version=) — so no crash window can leave a bumped
    # version with a stale pin. When accept=[] (no content change) the re-pin is a
    # standalone owner-scoped UPDATE (atomic on its own) so "reviewed, kept mine" still
    # clears the update signal.
    updated = local
    if body.accept:
        patch_kwargs = {f: _coerce_jsonb(upstream[f]) for f in body.accept}
        args = MotifPatchArgs(**patch_kwargs)
        try:
            patched = await repo.patch(
                user_id, motif_id, args, expected_version=local.version,
                repin_source_version=upstream_version,
            )
        except VersionMismatchError as exc:
            raise HTTPException(status_code=412, detail={
                "code": "MOTIF_VERSION_CONFLICT",
                "current": exc.current.model_dump(mode="json"),
            }) from exc
        except asyncpg.UniqueViolationError as exc:
            # sync never changes code/language, so this is unexpected — surface clean.
            raise HTTPException(status_code=409, detail={
                "code": "MOTIF_CODE_EXISTS",
                "message": "a motif with this code + language already exists",
            }) from exc
        if patched is None:
            # owner-only patch returned None → not the caller's row (H13 uniform).
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        updated = patched
    else:
        # accept=[] — re-pin only (one atomic owner-scoped UPDATE; no version bump, it's
        # lineage bookkeeping not a content edit).
        from app.db.pool import get_pool

        repinned = await get_pool().fetchrow(
            "UPDATE motif SET source_version = $3, updated_at = now() "
            "WHERE owner_user_id = $1 AND id = $2 RETURNING source_version",
            user_id, motif_id, upstream_version,
        )
        if repinned is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)

    return {
        "synced": True,
        "diff_mode": "two_way",
        "accepted": list(body.accept),
        "repinned_source_version": upstream_version,
        "motif": updated.model_dump(mode="json"),
    }
