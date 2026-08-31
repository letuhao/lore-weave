"""divergence_spec + entity_override repository (C23 — dị bản M0).

The COW delta substrate for a DERIVATIVE Work: one `divergence_spec` (taxonomy +
optional pov_anchor + added canon_rule[]) and zero-or-more `entity_override` rows
(per-entity FIELD overrides — M0 scope; relationship/event overrides DEFERRED).

SCOPE RULE (package re-key, spec 25 §Repo/service layer): reads key on `work_id`
(the derivative Work's composition_work.id — a work-wide read) — access is
decided BEFORE the repo, at the gate (E0 grant on the row's `book_id`). Writes
stamp `created_by` (a plain actor stamp — STORED, never filtered on) and derive
`book_id` via the work_id join to composition_work inside the INSERT. These rows
are PERSISTED here; the packer applies the overrides at retrieval in C25 (this
cycle does NOT apply them — COW persist-only).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import DivergenceSpec, EntityOverride
from app.db.repositories import ReferenceViolationError, rows_changed

_SPEC_COLS = "id, created_by, project_id, work_id, taxonomy, pov_anchor, canon_rule, created_at"
_OVERRIDE_COLS = (
    "id, created_by, project_id, work_id, target_entity_id, overridden_fields, "
    "is_archived, created_at"
)

# taxonomy CHECK set (migrate.py:152) — validate in-repo so a bad value is a domain
# error (→ 422 at the route), never a raw CHECK 500. Mirrors the DivergenceTaxonomy
# Literal on the models / route bodies.
_TAXONOMY_VALUES = ("pov_shift", "character_transform", "au")

# Sentinel for update_spec partial-update: distinguishes "field not provided" from
# "field set to NULL" (pov_anchor can legitimately be cleared to NULL).
_UNSET: Any = object()


def _row_to_override(row: asyncpg.Record) -> EntityOverride:
    data = dict(row)
    f = data.get("overridden_fields")
    if isinstance(f, str):
        data["overridden_fields"] = json.loads(f)
    return EntityOverride.model_validate(data)


class DerivativesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_spec(
        self, spec: DivergenceSpec, *, conn: asyncpg.Connection | None = None
    ) -> DivergenceSpec:
        """Insert the divergence_spec for a derivative Work. `spec.created_by` is
        the plain actor stamp; book_id derives via the work_id join."""
        query = f"""
        INSERT INTO divergence_spec
          (created_by, project_id, work_id, book_id, taxonomy, pov_anchor, canon_rule)
        SELECT $1, $2, $3, w.book_id, $4, $5, $6
        FROM composition_work w WHERE w.id = $3
        RETURNING {_SPEC_COLS}
        """
        args = (
            spec.created_by, spec.project_id, spec.work_id, spec.taxonomy,
            spec.pov_anchor, list(spec.canon_rule),
        )
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        if row is None:
            raise ReferenceViolationError(
                f"work {spec.work_id} not found (book scope unresolvable)"
            )
        return DivergenceSpec.model_validate(dict(row))

    async def create_override(
        self, override: EntityOverride, *, conn: asyncpg.Connection | None = None
    ) -> EntityOverride:
        """Insert one entity_override (entity-field delta) for a derivative Work.
        `override.created_by` is the plain actor stamp; book_id derives via the
        work_id join."""
        query = f"""
        INSERT INTO entity_override
          (created_by, project_id, work_id, book_id, target_entity_id, overridden_fields)
        SELECT $1, $2, $3, w.book_id, $4, $5::jsonb
        FROM composition_work w WHERE w.id = $3
        RETURNING {_OVERRIDE_COLS}
        """
        args = (
            override.created_by, override.project_id, override.work_id,
            override.target_entity_id, json.dumps(override.overridden_fields or {}),
        )
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        if row is None:
            raise ReferenceViolationError(
                f"work {override.work_id} not found (book scope unresolvable)"
            )
        return _row_to_override(row)

    async def get_spec_for_work(
        self, work_id: UUID
    ) -> DivergenceSpec | None:
        query = f"""
        SELECT {_SPEC_COLS} FROM divergence_spec
        WHERE work_id = $1
        ORDER BY created_at
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, work_id)
        return DivergenceSpec.model_validate(dict(row)) if row else None

    async def list_overrides_for_work(
        self, work_id: UUID, *, include_archived: bool = False
    ) -> list[EntityOverride]:
        """The Work's overrides. `include_archived=True` also returns SOFT-DELETED ones.

        🔴 THE UNDO YOU CANNOT REACH. `composition_entity_override_edit` ships an op=restore
        that takes an `override_id`, and until this flag existed there was NO surface anywhere
        that listed a deleted override — so the only way to hold that id was to have written it
        down BEFORE deleting. Measured across the family (D-RESTORE-WITH-NO-WAY-TO-SEE-WHAT-IS-
        RESTORABLE): entity_override was the last LIVE restore family with no discovery path.

        OWNER RULING DQ-T87 (a), 2026-08-31: build it.

        DEFAULT FALSE, AND THAT MATTERS AT TWO CALL SITES that must never see an archived row:
        `packer/pack.py` (an archived override must not apply to generated prose) and the
        works router's list endpoint. Both call this positionally, so their behaviour is
        byte-identical; a guard walks every call site and asserts it.
        """
        archived_clause = "" if include_archived else " AND NOT is_archived"
        query = f"""
        SELECT {_OVERRIDE_COLS} FROM entity_override
        WHERE work_id = $1{archived_clause}
        ORDER BY created_at
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, work_id)
        return [_row_to_override(r) for r in rows]

    # ── S-04: post-derive editing (the deltas were frozen at derive-time; these
    # make them mutable). All scoped by (work_id, book_id) for tenancy
    # defense-in-depth — the route also gates the book's E0 grant first.

    async def update_spec(
        self,
        work_id: UUID,
        book_id: UUID,
        *,
        taxonomy: Any = _UNSET,
        pov_anchor: Any = _UNSET,
        canon_rule: Any = _UNSET,
        conn: asyncpg.Connection | None = None,
    ) -> DivergenceSpec | None:
        """Partial-update the (single) divergence_spec for a derivative Work.

        Only provided fields are written (sentinel `_UNSET` distinguishes omitted
        from an explicit NULL on pov_anchor). `taxonomy` is validated against the
        CHECK set in-repo → ValueError (route maps to 422) so a bad value never
        reaches the DB CHECK as a 500. Returns None when no row matches
        (work_id, book_id) — the route maps that to 404. No create (a spec exists
        from derive-time); no delete (= archive the derivative Work)."""
        sets: list[str] = []
        args: list[Any] = []
        if taxonomy is not _UNSET:
            if taxonomy not in _TAXONOMY_VALUES:
                raise ValueError(f"invalid taxonomy {taxonomy!r}")
            args.append(taxonomy)
            sets.append(f"taxonomy = ${len(args)}")
        if pov_anchor is not _UNSET:
            args.append(pov_anchor)
            sets.append(f"pov_anchor = ${len(args)}")
        if canon_rule is not _UNSET:
            args.append(list(canon_rule))
            sets.append(f"canon_rule = ${len(args)}")
        if not sets:
            # No-op patch: return the current row (book-scoped), not silently nothing.
            return await self._get_spec_scoped(work_id, book_id, conn=conn)
        args.append(work_id)
        work_pos = len(args)
        args.append(book_id)
        book_pos = len(args)
        query = f"""
        UPDATE divergence_spec SET {", ".join(sets)}
        WHERE work_id = ${work_pos} AND book_id = ${book_pos}
        RETURNING {_SPEC_COLS}
        """
        row = await self._fetchrow(query, *args, conn=conn)
        return DivergenceSpec.model_validate(dict(row)) if row else None

    async def _get_spec_scoped(
        self, work_id: UUID, book_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> DivergenceSpec | None:
        query = f"""
        SELECT {_SPEC_COLS} FROM divergence_spec
        WHERE work_id = $1 AND book_id = $2
        ORDER BY created_at LIMIT 1
        """
        row = await self._fetchrow(query, work_id, book_id, conn=conn)
        return DivergenceSpec.model_validate(dict(row)) if row else None

    async def get_override(
        self, work_id: UUID, book_id: UUID, override_id: UUID,
        *, conn: asyncpg.Connection | None = None,
    ) -> EntityOverride | None:
        """Read ONE override (book+work scoped) — the prior state a Tier-A undo_hint
        captures before an update/delete. None when it doesn't belong to this work."""
        query = f"""
        SELECT {_OVERRIDE_COLS} FROM entity_override
        WHERE id = $1 AND work_id = $2 AND book_id = $3
        """  # archived rows ARE returned here — restore must be able to read one back
        row = await self._fetchrow(query, override_id, work_id, book_id, conn=conn)
        return _row_to_override(row) if row else None

    async def add_override(
        self,
        work_id: UUID,
        book_id: UUID,
        created_by: UUID,
        target_entity_id: UUID,
        overridden_fields: dict[str, Any] | None,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> EntityOverride:
        """Add ONE entity_override to a derivative Work AFTER derive (the missing
        'override another entity later'). project_id + book_id derive from the work
        row (scoped to the gated book). A duplicate (work_id, target_entity_id)
        raises asyncpg.UniqueViolationError (route → 409); a work outside the book
        raises ReferenceViolationError (route → 404)."""
        query = f"""
        INSERT INTO entity_override
          (created_by, project_id, work_id, book_id, target_entity_id, overridden_fields)
        SELECT $1, w.project_id, w.id, w.book_id, $4, $5::jsonb
        FROM composition_work w WHERE w.id = $2 AND w.book_id = $3
        RETURNING {_OVERRIDE_COLS}
        """
        row = await self._fetchrow(
            query, created_by, work_id, book_id, target_entity_id,
            json.dumps(overridden_fields or {}), conn=conn,
        )
        if row is None:
            raise ReferenceViolationError(
                f"work {work_id} not found in book {book_id} (override scope unresolvable)"
            )
        return _row_to_override(row)

    async def update_override(
        self,
        work_id: UUID,
        book_id: UUID,
        override_id: UUID,
        overridden_fields: dict[str, Any] | None,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> EntityOverride | None:
        """Replace an override's field-set (whole-object replace — the override IS
        the delta). Returns None when (id, work_id, book_id) matches nothing (404)."""
        query = f"""
        UPDATE entity_override SET overridden_fields = $1::jsonb
        WHERE id = $2 AND work_id = $3 AND book_id = $4
        RETURNING {_OVERRIDE_COLS}
        """
        row = await self._fetchrow(
            query, json.dumps(overridden_fields or {}), override_id, work_id, book_id,
            conn=conn,
        )
        return _row_to_override(row) if row else None

    async def delete_override(
        self,
        work_id: UUID,
        book_id: UUID,
        override_id: UUID,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        """SOFT-delete an override. Returns False when nothing matched (404).

        This was a hard DELETE, justified as "a pure delta — no history to preserve; removing it
        reverts that entity to canon". That reasoning is right about the delta's EFFECT and wrong
        about the authored LABOUR: `overridden_fields` is a JSONB blob the author wrote (how this
        dị bản's entity differs), and destroying it means re-authoring it from memory. Every
        sibling atom — canon_rule, outline_node, the derivative Work itself — soft-archives and
        offers restore; this one silently did not (F3, 2026-07-27).

        The read paths filter `NOT is_archived`, so the delta stops grounding generation the
        moment it is archived — the revert-to-canon semantics the old docstring described are
        preserved exactly. Only the irreversibility is gone.
        """
        query = (
            "UPDATE entity_override SET is_archived = true "
            "WHERE id = $1 AND work_id = $2 AND book_id = $3 AND NOT is_archived"
        )
        if conn is not None:
            status = await conn.execute(query, override_id, work_id, book_id)
        else:
            async with self._pool.acquire() as c:
                status = await c.execute(query, override_id, work_id, book_id)
        return rows_changed(status) > 0

    async def restore_override(
        self,
        work_id: UUID,
        book_id: UUID,
        override_id: UUID,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        """The UNDO the delete now promises. False when nothing matched or it was never archived.

        A restore can legitimately FAIL: the partial unique means the author may have written a
        new override for that same entity since. Surfacing that as False (-> 409) is honest —
        silently resurrecting the old delta would clobber the newer one."""
        query = (
            "UPDATE entity_override SET is_archived = false "
            "WHERE id = $1 AND work_id = $2 AND book_id = $3 AND is_archived"
        )
        try:
            if conn is not None:
                status = await conn.execute(query, override_id, work_id, book_id)
            else:
                async with self._pool.acquire() as c:
                    status = await c.execute(query, override_id, work_id, book_id)
        except asyncpg.UniqueViolationError:
            # A newer override for the same entity exists — un-archiving would collide. Return
            # False so the caller reports it honestly rather than 500-ing. (Same live-probe find
            # as SceneLinksRepo.restore.)
            return False
        return rows_changed(status) > 0

    async def _fetchrow(
        self, query: str, *args: Any, conn: asyncpg.Connection | None = None
    ) -> asyncpg.Record | None:
        if conn is not None:
            return await conn.fetchrow(query, *args)
        async with self._pool.acquire() as c:
            return await c.fetchrow(query, *args)
