"""canon_rule repository — author-declared invariants (§1.2/§5).

SCOPE RULE (package re-key, spec 25 §Repo/service layer): reads key on
`project_id` (the Work partition key) — access is decided BEFORE the repo, at
the gate (E0 grant on the row's `book_id`). Writes stamp `created_by` (a plain
actor stamp — STORED, never filtered on) and derive `book_id` from
composition_work inside the INSERT so a row can never land with a NULL book
scope. DELETE is a soft-archive (is_archived=true) — a rule is never
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
from app.db.repositories import ReferenceViolationError, VersionMismatchError

_SELECT_COLS = """
  id, created_by, project_id, text, scope, entity_id, from_order, until_order,
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
        project_id: UUID,
        text: str,
        *,
        created_by: UUID,
        scope: str = "world",
        entity_id: UUID | None = None,
        from_order: int | None = None,
        until_order: int | None = None,
        kind: str | None = None,
    ) -> CanonRule:
        query = f"""
        INSERT INTO canon_rule
          (created_by, project_id, book_id, text, scope, entity_id, from_order, until_order, kind)
        SELECT $1, $2, w.book_id, $3, $4, $5, $6, $7, $8
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, created_by, project_id, text, scope, entity_id,
                from_order, until_order, kind,
            )
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row_to_rule(row)

    async def list_active(self, project_id: UUID) -> list[CanonRule]:
        """Enforceable rules only (active AND NOT archived) — the M6 critic's
        source of truth at critique time. Uses idx_canon_rule_project."""
        query = f"""
        SELECT {_SELECT_COLS} FROM canon_rule
        WHERE project_id = $1 AND active AND NOT is_archived
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row_to_rule(r) for r in rows]

    async def list_all(self, project_id: UUID) -> list[CanonRule]:
        """Every non-archived rule (active + inactive) — the management list."""
        query = f"""
        SELECT {_SELECT_COLS} FROM canon_rule
        WHERE project_id = $1 AND NOT is_archived
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row_to_rule(r) for r in rows]

    async def get(self, project_id: UUID, rule_id: UUID) -> CanonRule | None:
        query = f"SELECT {_SELECT_COLS} FROM canon_rule WHERE project_id = $1 AND id = $2"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, rule_id)
        return _row_to_rule(row) if row else None

    async def update(
        self,
        project_id: UUID,
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
            return await self.get(project_id, rule_id)

        set_clauses: list[str] = []
        params: list[Any] = [project_id, rule_id]
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
        WHERE project_id = $1 AND id = $2{version_clause}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        if row is not None:
            return _row_to_rule(row)
        if expected_version is None:
            return None
        current = await self.get(project_id, rule_id)
        if current is None:
            return None
        raise VersionMismatchError(current)

    async def archive(self, project_id: UUID, rule_id: UUID) -> CanonRule | None:
        """Soft-archive (DELETE semantics). Returns the row, or None if missing /
        another project's / already archived."""
        query = f"""
        UPDATE canon_rule
        SET is_archived = true, updated_at = now()
        WHERE project_id = $1 AND id = $2 AND NOT is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, rule_id)
        return _row_to_rule(row) if row else None

    async def restore(self, project_id: UUID, rule_id: UUID) -> CanonRule | None:
        """BE-11 — archive()'s exact inverse (the undo behind the delete toast). Returns
        the row, or None if missing / another project's / NOT archived.

        🔴 It must NOT bump `version` and must NOT touch `active`. Restore un-archives ONLY:
        a rule that was `active=false` when it was deleted comes back INACTIVE. Bumping the
        version would silently invalidate a client's If-Match; flipping `active` would
        silently re-arm a rule the author had deliberately disabled — both are silent
        corruption, which is why they have their own test.

        `canon_rule` has no parent/child tree ⇒ NO cascade (unlike outline.restore_node's
        two recursive walks). No If-Match/OCC: an archived row has no concurrent editor.
        """
        query = f"""
        UPDATE canon_rule
        SET is_archived = false, updated_at = now()
        WHERE project_id = $1 AND id = $2 AND is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, rule_id)
        return _row_to_rule(row) if row else None
