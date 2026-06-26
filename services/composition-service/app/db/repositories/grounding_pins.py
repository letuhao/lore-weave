"""scene_grounding_pins repository — LOOM T3.4 per-scene grounding steering.

One row per addressed grounding item (present-entity / canon-rule / lore-source):
`action='pin'` force-keeps it through the budget trim, `action='exclude'` drops it
from the pack. Read by `pack()` (the single chokepoint shared by the grounding
preview and the engine generation) so preview == what the model receives.

SECURITY (M5 isolation): every method takes `user_id` first and filters on it.
`set_action` upserts on the UNIQUE (project, scene, item_type, item_id) key so a
pin⇄exclude flip replaces the row in place (never two rows for one item).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.models import SceneGroundingPin

_SELECT_COLS = """
  id, user_id, project_id, outline_node_id, item_type, item_id, action, created_at
"""


def _row_to_pin(row: asyncpg.Record) -> SceneGroundingPin:
    return SceneGroundingPin.model_validate(dict(row))


class GroundingPinsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_for_scene(
        self, user_id: UUID, project_id: UUID, outline_node_id: UUID,
    ) -> list[SceneGroundingPin]:
        """All pin/exclude rows for one scene — the set `pack()` applies. Uses
        idx_scene_grounding_pins_scene."""
        query = f"""
        SELECT {_SELECT_COLS} FROM scene_grounding_pins
        WHERE user_id = $1 AND project_id = $2 AND outline_node_id = $3
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id, outline_node_id)
        return [_row_to_pin(r) for r in rows]

    async def set_action(
        self, user_id: UUID, project_id: UUID, outline_node_id: UUID,
        item_type: str, item_id: str, action: str,
    ) -> SceneGroundingPin:
        """Pin or exclude an item — upsert on the UNIQUE key so a pin⇄exclude flip
        replaces the existing row in place (created_at refreshed). The scene's
        ownership/existence is gated at the router (SEC2) BEFORE this call."""
        query = f"""
        INSERT INTO scene_grounding_pins
          (user_id, project_id, outline_node_id, item_type, item_id, action)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (project_id, outline_node_id, item_type, item_id)
        DO UPDATE SET action = EXCLUDED.action, created_at = now()
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, user_id, project_id, outline_node_id, item_type, item_id, action,
            )
        return _row_to_pin(row)

    async def clear(
        self, user_id: UUID, project_id: UUID, outline_node_id: UUID,
        item_type: str, item_id: str,
    ) -> bool:
        """Remove an item's steering (return it to default budget behavior). True
        when a row was deleted, False when there was nothing to clear."""
        query = """
        DELETE FROM scene_grounding_pins
        WHERE user_id = $1 AND project_id = $2 AND outline_node_id = $3
          AND item_type = $4 AND item_id = $5
        """
        async with self._pool.acquire() as c:
            result = await c.execute(query, user_id, project_id, outline_node_id, item_type, item_id)
        # asyncpg returns "DELETE <n>"
        return result.rsplit(" ", 1)[-1] != "0"
