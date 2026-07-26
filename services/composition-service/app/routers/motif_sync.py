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
3-WAY MERGE (D-MOTIF-SYNC-3WAY-BASE cleared): a true 3-way needs THREE texts —
base (the upstream AT adopt time), ours (the caller's local edits), theirs
(upstream CURRENT). The base is the `motif.adopted_base` JSONB snapshot that
`clone()` captures of the source's mergeable fields at adopt time (NOT reconstructed
from a version pin — the table keeps no per-version history). So each field reports
base/ours/theirs + `ours_changed`/`theirs_changed`/`conflict` (both sides moved to
DIFFERENT values), `diff_mode="three_way"`. After a sync the base is RE-BASELINED to
the reconciled upstream (atomically, in the same patch UPDATE) so the next diff is
clean. A row cloned BEFORE this feature has no snapshot → the diff degrades to a
labelled 2-way (ours vs theirs-current, `base_available=False`) — honest, never a
fabricated base.
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
) -> tuple[Motif, asyncpg.Record, dict[str, Any] | None]:
    """Shared resolve for both surfaces: load the caller's LOCAL motif (read
    predicate → H13 404 on miss/foreign), confirm it carries a lineage (→ 409
    not-adopted), then re-resolve the UPSTREAM CURRENT row under the SAME predicate
    (→ 410 gone if it vanished/was archived since adopt). Also loads the local's
    `adopted_base` snapshot (the true 3-way merge base, D-MOTIF-SYNC-3WAY-BASE; None for
    a pre-3-way clone → the diff degrades to 2-way for that row). Returns (local,
    upstream, base)."""
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

    pool = get_pool()
    upstream = await pool.fetchrow(
        f"SELECT {_UPSTREAM_COLS} FROM motif "
        f"WHERE id = $2 AND {_VISIBLE_PREDICATE} AND status <> 'archived'",
        caller_id, src_id,
    )
    if upstream is None:
        raise HTTPException(status_code=410, detail={
            "code": "MOTIF_UPSTREAM_GONE",
            "message": "the upstream motif is no longer available",
        })
    # the merge base = the local row's adopted_base snapshot (owner-scoped read).
    base_row = await pool.fetchrow(
        "SELECT adopted_base FROM motif WHERE id = $1 AND owner_user_id = $2",
        motif_id, caller_id,
    )
    base = (_coerce_jsonb(base_row["adopted_base"])
            if base_row is not None and base_row["adopted_base"] is not None else None)
    return local, upstream, base


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


def _field_diff(
    local: Motif, upstream: asyncpg.Record, base: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Per-field diff. With a `base` (adopted_base snapshot) it is a TRUE 3-way:
    `ours_changed`/`theirs_changed` vs the base + `conflict` (both sides moved to
    DIFFERENT values). Without a base (a pre-3-way clone) it degrades to 2-way (ours vs
    theirs, no base key). `changed` (ours != theirs) is always present."""
    fields: dict[str, dict[str, Any]] = {}
    for f in _MERGEABLE_FIELDS:
        ours = getattr(local, f)
        theirs = _coerce_jsonb(upstream[f])
        entry: dict[str, Any] = {"ours": ours, "theirs": theirs, "changed": ours != theirs}
        if base is not None:
            b = base.get(f)
            ours_changed = ours != b
            theirs_changed = theirs != b
            entry["base"] = b
            entry["ours_changed"] = ours_changed
            entry["theirs_changed"] = theirs_changed
            # conflict: BOTH sides diverged from the base, to different values. A field
            # only theirs-changed is a clean fast-forward; only ours-changed is a local edit.
            entry["conflict"] = ours_changed and theirs_changed and (ours != theirs)
        fields[f] = entry
    return fields


@router.get("/motifs/{motif_id}/upstream-diff")
async def upstream_diff(
    motif_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: MotifRepo = Depends(get_motif_repo),
) -> dict[str, Any]:
    """The "update available" signal + per-field diff for an adopted motif.

    TRUE 3-way (`diff_mode="three_way"`, `base_available=True`) when the row carries an
    `adopted_base` snapshot (D-MOTIF-SYNC-3WAY-BASE) — each field reports base/ours/theirs
    + ours_changed/theirs_changed/conflict. A pre-3-way clone (no snapshot) degrades to
    2-way. `update_available` is True when the upstream CURRENT version moved past the
    locally pinned `source_version`."""
    local, upstream, base = await _resolve_local_and_upstream(user_id, motif_id, repo)
    pinned = local.source_version
    upstream_version = int(upstream["version"])
    update_available = pinned is None or upstream_version > pinned
    return {
        "diff_mode": "three_way" if base is not None else "two_way",
        "base_available": base is not None,
        "pinned_source_version": pinned,
        "upstream_version": upstream_version,
        "update_available": update_available,
        "fields": _field_diff(local, upstream, base),
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
    local, upstream, _base = await _resolve_local_and_upstream(user_id, motif_id, repo)

    upstream_version = int(upstream["version"])
    # RE-BASELINE: after a sync the merge base advances to the upstream we reconciled
    # against — its current mergeable fields. Next diff is then base=this-upstream vs
    # ours(possibly-edited) vs future-upstream. Re-baselined for ALL fields (even kept-ours),
    # since the user has now SEEN this upstream and chosen.
    import json as _json

    new_base = _json.dumps({f: _coerce_jsonb(upstream[f]) for f in _MERGEABLE_FIELDS})

    # Publish ceiling only matters if THIS row is currently shareable (sync never
    # changes visibility, so we check the local row's existing state).
    if local.visibility in ("public", "unlisted"):
        await _publish_quota_guard(repo, user_id)

    # The merge is ONE atomic owner-scoped write (D-MOTIF-SYNC-REPIN-ATOMICITY): the
    # accepted CONTENT fields + the source_version re-pin + the adopted_base re-baseline
    # ride the SAME optimistic-lock patch() UPDATE — so no crash window can leave a
    # bumped version with a stale pin/base. When accept=[] (no content change) the re-pin
    # + re-baseline are a standalone owner-scoped UPDATE (atomic on its own).
    updated = local
    if body.accept:
        patch_kwargs = {f: _coerce_jsonb(upstream[f]) for f in body.accept}
        args = MotifPatchArgs(**patch_kwargs)
        try:
            patched = await repo.patch(
                user_id, motif_id, args, expected_version=local.version,
                repin_source_version=upstream_version, repin_adopted_base=new_base,
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
        # accept=[] — re-pin + re-baseline only (one atomic owner-scoped UPDATE; no version
        # bump, it's lineage bookkeeping not a content edit).
        from app.db.pool import get_pool

        repinned = await get_pool().fetchrow(
            "UPDATE motif SET source_version = $3, adopted_base = $4::jsonb, updated_at = now() "
            "WHERE owner_user_id = $1 AND id = $2 RETURNING source_version",
            user_id, motif_id, upstream_version, new_base,
        )
        if repinned is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)

    return {
        "synced": True,
        "diff_mode": "three_way" if _base is not None else "two_way",
        "accepted": list(body.accept),
        "repinned_source_version": upstream_version,
        "rebaselined": True,
        "motif": updated.model_dump(mode="json"),
    }
