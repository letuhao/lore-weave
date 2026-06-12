"""structure_template repository — read the story-structure library (§5 GET /templates).

Built-in templates have `owner_user_id IS NULL` (seeded in migrate.py); a user
may have custom ones. The list a user sees = built-ins + their own. Read-only in
V0 (custom-template authoring is a later surface).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from app.db.models import StructureTemplate

_SELECT_COLS = "id, owner_user_id, name, kind, beats, created_at"


def _row_to_template(row: asyncpg.Record) -> StructureTemplate:
    data = dict(row)
    beats = data.get("beats")
    if isinstance(beats, str):
        data["beats"] = json.loads(beats)
    return StructureTemplate.model_validate(data)


class StructureTemplatesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_for_user(self, user_id: UUID) -> list[StructureTemplate]:
        """Built-in (owner NULL) + the user's own templates. Built-ins first."""
        query = f"""
        SELECT {_SELECT_COLS} FROM structure_template
        WHERE owner_user_id IS NULL OR owner_user_id = $1
        ORDER BY owner_user_id NULLS FIRST, name
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id)
        return [_row_to_template(r) for r in rows]

    async def get(self, user_id: UUID, template_id: UUID) -> StructureTemplate | None:
        """One template the user may use: a built-in (owner NULL) OR their own.
        Returns None for a missing id or another user's custom template (no
        cross-user leak — the A3 decompose endpoint maps that to 404)."""
        query = f"""
        SELECT {_SELECT_COLS} FROM structure_template
        WHERE id = $1 AND (owner_user_id IS NULL OR owner_user_id = $2)
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, template_id, user_id)
        return _row_to_template(row) if row is not None else None
