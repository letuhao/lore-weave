"""scene_link repository — non-derivable scene edges (setup_payoff / custom).

SECURITY RULE (M5 isolation): every method takes `user_id` first and filters
`user_id = $1`. Edges have no archive column and no children, so DELETE is a
hard delete (the only hard delete in M2). The unique (from,to,kind) constraint
makes create idempotent-ish — a duplicate raises UniqueViolation, surfaced to
the router as a 409.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.models import SceneLink
from app.db.repositories import rows_changed

_SELECT_COLS = """
  id, user_id, project_id, from_node_id, to_node_id, kind, label, created_at
"""


def _row_to_link(row: asyncpg.Record) -> SceneLink:
    return SceneLink.model_validate(dict(row))


class SceneLinksRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        user_id: UUID,
        project_id: UUID,
        from_node_id: UUID,
        to_node_id: UUID,
        *,
        kind: str = "setup_payoff",
        label: str = "",
    ) -> SceneLink:
        query = f"""
        INSERT INTO scene_link (user_id, project_id, from_node_id, to_node_id, kind, label)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, user_id, project_id, from_node_id, to_node_id, kind, label
            )
        return _row_to_link(row)

    async def list_by_project(self, user_id: UUID, project_id: UUID) -> list[SceneLink]:
        query = f"""
        SELECT {_SELECT_COLS} FROM scene_link
        WHERE user_id = $1 AND project_id = $2
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id)
        return [_row_to_link(r) for r in rows]

    async def delete(self, user_id: UUID, link_id: UUID) -> bool:
        """Hard-delete an edge. Returns False on a cross-user / missing id."""
        async with self._pool.acquire() as c:
            status = await c.execute(
                "DELETE FROM scene_link WHERE user_id = $1 AND id = $2",
                user_id, link_id,
            )
        return rows_changed(status) > 0
