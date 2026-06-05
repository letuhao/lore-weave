"""canon_rule repository — author-declared invariants (§1.2/§5).

SECURITY RULE (M5 isolation): every method takes `user_id` first and filters
`user_id = $1`. DELETE is a soft-archive (is_archived=true) — a rule is never
hard-deleted so the critic-calibration history (which rule fired) survives.
`list_active` returns only enforceable rules (active AND NOT archived) — that
is what the M6 critic re-resolves at critique time (§13 CC2: a deleted/archived
rule must not be enforced).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import CanonRule
from app.db.repositories import VersionMismatchError

_SELECT_COLS = """
  id, user_id, project_id, text, scope, entity_id, from_order, until_order,
  kind, active, version, is_archived, created_at, updated_at
"""

_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"text", "scope", "entity_id", "from_order", "until_order", "kind", "active"}
)
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {"entity_id", "from_order", "until_order", "kind"}
)


def _row_to_rule(row: asyncpg.Record) -> CanonRule:
    return CanonRule.model_validate(dict(row))


class CanonRulesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        user_id: UUID,
        project_id: UUID,
        text: str,
        *,
        scope: str = "world",
        entity_id: UUID | None = None,
        from_order: int | None = None,
        until_order: int | None = None,
        kind: str | None = None,
    ) -> CanonRule:
        query = f"""
        INSERT INTO canon_rule
          (user_id, project_id, text, scope, entity_id, from_order, until_order, kind)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, user_id, project_id, text, scope, entity_id,
                from_order, until_order, kind,
            )
        return _row_to_rule(row)

    async def list_active(self, user_id: UUID, project_id: UUID) -> list[CanonRule]:
        """Enforceable rules only (active AND NOT archived) — the M6 critic's
        source of truth at critique time. Uses idx_canon_rule_project."""
        query = f"""
        SELECT {_SELECT_COLS} FROM canon_rule
        WHERE user_id = $1 AND project_id = $2 AND active AND NOT is_archived
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id)
        return [_row_to_rule(r) for r in rows]

    async def list_all(self, user_id: UUID, project_id: UUID) -> list[CanonRule]:
        """Every non-archived rule (active + inactive) — the management list."""
        query = f"""
        SELECT {_SELECT_COLS} FROM canon_rule
        WHERE user_id = $1 AND project_id = $2 AND NOT is_archived
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id)
        return [_row_to_rule(r) for r in rows]

    async def get(self, user_id: UUID, rule_id: UUID) -> CanonRule | None:
        query = f"SELECT {_SELECT_COLS} FROM canon_rule WHERE user_id = $1 AND id = $2"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, rule_id)
        return _row_to_rule(row) if row else None

    async def update(
        self,
        user_id: UUID,
        rule_id: UUID,
        patch: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> CanonRule | None:
        """Partial update with optional If-Match (same discipline as WorksRepo)."""
        updates: dict[str, Any] = {}
        for field, value in patch.items():
            if field not in _UPDATABLE_COLUMNS:
                raise ValueError(f"field not updatable: {field}")
            if value is None and field not in _NULLABLE_UPDATE_COLUMNS:
                continue
            updates[field] = value

        if not updates:
            return await self.get(user_id, rule_id)

        set_clauses: list[str] = []
        params: list[Any] = [user_id, rule_id]
        for field, value in updates.items():
            params.append(value)
            set_clauses.append(f"{field} = ${len(params)}")
        set_clauses.append("updated_at = now()")

        version_clause = ""
        if expected_version is not None:
            params.append(expected_version)
            version_clause = f" AND version = ${len(params)}"
            set_clauses.append("version = version + 1")

        query = f"""
        UPDATE canon_rule
        SET {", ".join(set_clauses)}
        WHERE user_id = $1 AND id = $2{version_clause}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        if row is not None:
            return _row_to_rule(row)
        if expected_version is None:
            return None
        current = await self.get(user_id, rule_id)
        if current is None:
            return None
        raise VersionMismatchError(current)

    async def archive(self, user_id: UUID, rule_id: UUID) -> CanonRule | None:
        """Soft-archive (DELETE semantics). Returns the row, or None if missing /
        cross-user / already archived."""
        query = f"""
        UPDATE canon_rule
        SET is_archived = true, updated_at = now()
        WHERE user_id = $1 AND id = $2 AND NOT is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, rule_id)
        return _row_to_rule(row) if row else None
