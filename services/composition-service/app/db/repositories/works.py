"""composition_work repository — the Work marker + work-level settings (§5/§6.2).

SECURITY RULE (M5 isolation): every method takes `user_id` first and every SQL
statement filters `user_id = $1`. A cross-user read returns None / [] (404-not-
403). Reviewers must reject any query that omits the user_id predicate.

`composition_work.project_id` is the PRIMARY KEY and equals the knowledge
project id (cross-DB, no FK). Creating a Work therefore requires an already-
existing knowledge project id — the POST /work flow (M7) creates the knowledge
project first, then the row here.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import CompositionWork
from app.db.repositories import VersionMismatchError

_SELECT_COLS = """
  project_id, user_id, book_id, id, pending_project_backfill,
  source_work_id, branch_point,
  active_template_id, status, settings,
  version, created_at, updated_at
"""

# Fields a PATCH /works/{id} may change. Defense-in-depth against a router
# passing an unexpected column into the dynamic UPDATE.
_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"active_template_id", "status", "settings"}
)
# Columns that accept an explicit NULL (clear). `active_template_id` clears the
# template selection; status/settings are NOT NULL so None is skipped.
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset({"active_template_id"})


def _row_to_work(row: asyncpg.Record) -> CompositionWork:
    data = dict(row)
    s = data.get("settings")
    if isinstance(s, str):
        data["settings"] = json.loads(s)
    return CompositionWork.model_validate(data)


class WorksRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        user_id: UUID,
        project_id: UUID,
        book_id: UUID,
        *,
        active_template_id: UUID | None = None,
        settings: dict[str, Any] | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> CompositionWork:
        """Insert the Work marker row for an existing knowledge project.

        Accepts an optional `conn` so the POST /work flow can create the
        knowledge project + emit the outbox event + write this row in one
        transaction (txn-local outbox, §1).
        """
        query = f"""
        INSERT INTO composition_work (project_id, user_id, book_id, active_template_id, settings)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        RETURNING {_SELECT_COLS}
        """
        args = (project_id, user_id, book_id, active_template_id, json.dumps(settings or {}))
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        return _row_to_work(row)

    async def create_pending(
        self,
        user_id: UUID,
        book_id: UUID,
        *,
        active_template_id: UUID | None = None,
        settings: dict[str, Any] | None = None,
    ) -> CompositionWork:
        """C16 (WG-3): create a LAZY greenfield Work with a NULL project_id +
        `pending_project_backfill=true` when knowledge-service could not mint the
        project (down/5xx). The surrogate `id` PK makes the row addressable; the
        partial-unique (user,book) WHERE pending index caps it at one — so a
        concurrent retry that loses the race re-gets the existing pending row.
        GREENFIELD ONLY: the router refuses this path for a derivative Work (C23
        guard — a derivative keeps project_id NOT NULL)."""
        query = f"""
        INSERT INTO composition_work
          (project_id, user_id, book_id, pending_project_backfill, active_template_id, settings)
        VALUES (NULL, $1, $2, true, $3, $4::jsonb)
        RETURNING {_SELECT_COLS}
        """
        args = (user_id, book_id, active_template_id, json.dumps(settings or {}))
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *args)
        return _row_to_work(row)

    async def create_derivative(
        self,
        user_id: UUID,
        project_id: UUID,
        book_id: UUID,
        source_work_id: UUID,
        *,
        branch_point: int | None = None,
        settings: dict[str, Any] | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> CompositionWork:
        """C23 (dị bản M0): insert a DERIVATIVE Work linked to its source.

        `project_id` MUST be a freshly-minted knowledge project (G2 — the
        derivative's own delta partition; NEVER the source's) and is NOT NULL: the
        `chk_derivative_project_required` DB CHECK rejects a null project on a row
        with `source_work_id` set, the same guard the router enforces before this
        call. Accepts an optional `conn` so the derive flow can write the Work +
        its divergence_spec + entity_override[] in one transaction.
        """
        query = f"""
        INSERT INTO composition_work
          (project_id, user_id, book_id, source_work_id, branch_point, settings)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        RETURNING {_SELECT_COLS}
        """
        args = (project_id, user_id, book_id, source_work_id, branch_point,
                json.dumps(settings or {}))
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        return _row_to_work(row)

    async def get_pending_for_book(
        self, user_id: UUID, book_id: UUID
    ) -> CompositionWork | None:
        """The (at-most-one) lazy greenfield Work awaiting a knowledge project for
        this user+book (C16 backfill seam). None when there is none."""
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE user_id = $1 AND book_id = $2 AND pending_project_backfill
        ORDER BY created_at
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, book_id)
        return _row_to_work(row) if row else None

    async def backfill_project(
        self, user_id: UUID, work_id: UUID, project_id: UUID
    ) -> CompositionWork | None:
        """C16 backfill seam: stamp the now-created knowledge `project_id` onto a
        lazy Work (by surrogate `id`) and clear the pending marker. Idempotent:
        only updates a still-pending row, so a double-backfill no-ops. Returns the
        updated row, or None if the row vanished / was already backfilled."""
        query = f"""
        UPDATE composition_work
        SET project_id = $3, pending_project_backfill = false, updated_at = now()
        WHERE user_id = $1 AND id = $2 AND pending_project_backfill
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, work_id, project_id)
        return _row_to_work(row) if row else None

    async def get(self, user_id: UUID, project_id: UUID) -> CompositionWork | None:
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE user_id = $1 AND project_id = $2
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, project_id)
        return _row_to_work(row) if row else None

    async def resolve_by_book(
        self, user_id: UUID, book_id: UUID
    ) -> list[CompositionWork]:
        """Return every MARKED (real-project) Work for this user+book (§6.2
        prefers-marked).

        The caller (work_resolution.resolve_work) maps the result:
          len == 1 → found · len > 1 → candidates · len == 0 → defer to the
        knowledge book-project lookup. Ordered by created_at so a candidates
        list is stable.

        C16: a LAZY null-project Work (`pending_project_backfill`) is EXCLUDED — it
        is a placeholder, not yet a grounding-backed marked Work, and would have a
        null project_id (un-anchorable). Excluding it makes resolution fall through
        to the knowledge book-project lookup so a retry once knowledge recovers hits
        the create_project → BACKFILL seam (which stamps the project onto this same
        pending row) instead of returning the placeholder as a finished `found` Work.
        """
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE user_id = $1 AND book_id = $2 AND status = 'active'
          AND NOT pending_project_backfill
        ORDER BY created_at, project_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, book_id)
        return [_row_to_work(r) for r in rows]

    async def update(
        self,
        user_id: UUID,
        project_id: UUID,
        patch: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> CompositionWork | None:
        """Partial update with optional If-Match (§5).

        - Unknown fields → ValueError (defense-in-depth).
        - None on a NOT-NULL column is skipped; None on a nullable column clears.
        - Empty effective patch returns the current row unchanged (no version
          bump, no updated_at touch) — GET-like no-op.
        - `expected_version` set: WHERE gates on version, SET bumps it; a 0-row
          result does a follow-up GET to distinguish 404 (None) from 412
          (raises VersionMismatchError with the current row).
        """
        updates: dict[str, Any] = {}
        for field, value in patch.items():
            if field not in _UPDATABLE_COLUMNS:
                raise ValueError(f"field not updatable: {field}")
            if value is None and field not in _NULLABLE_UPDATE_COLUMNS:
                continue
            updates[field] = value

        if not updates:
            return await self.get(user_id, project_id)

        set_clauses: list[str] = []
        params: list[Any] = [user_id, project_id]
        for field, value in updates.items():
            if field == "settings":
                params.append(json.dumps(value))
                set_clauses.append(f"settings = ${len(params)}::jsonb")
            else:
                params.append(value)
                set_clauses.append(f"{field} = ${len(params)}")
        set_clauses.append("updated_at = now()")

        version_clause = ""
        if expected_version is not None:
            params.append(expected_version)
            version_clause = f" AND version = ${len(params)}"
            set_clauses.append("version = version + 1")

        query = f"""
        UPDATE composition_work
        SET {", ".join(set_clauses)}
        WHERE user_id = $1 AND project_id = $2{version_clause}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        if row is not None:
            return _row_to_work(row)
        if expected_version is None:
            return None
        current = await self.get(user_id, project_id)
        if current is None:
            return None
        raise VersionMismatchError(current)
