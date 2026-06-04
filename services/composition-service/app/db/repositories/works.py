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
  project_id, user_id, book_id, active_template_id, status, settings,
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
        """Return every MARKED Work for this user+book (§6.2 prefers-marked).

        The caller (work_resolution.resolve_work) maps the result:
          len == 1 → found · len > 1 → candidates · len == 0 → defer to the
        knowledge book-project lookup. Ordered by created_at so a candidates
        list is stable.
        """
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE user_id = $1 AND book_id = $2 AND status = 'active'
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
