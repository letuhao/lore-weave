"""scene_grounding_pins repository — LOOM T3.4 per-scene grounding steering.

One row per addressed grounding item (present-entity / canon-rule / lore-source):
`action='pin'` force-keeps it through the budget trim, `action='exclude'` drops it
from the pack. Read by `pack()` (the single chokepoint shared by the grounding
preview and the engine generation) so preview == what the model receives.

SCOPE RULE (package re-key, spec 25 §Repo/service layer): reads key on
`project_id` — access is decided BEFORE the repo, at the gate (E0 grant on the
row's `book_id`). Writes stamp `created_by` (a plain actor stamp — STORED, never
filtered on; re-stamped on conflict, matching the created_at refresh — the row
is replaced in place) and derive `book_id` from composition_work inside the
INSERT. `set_action` upserts on the UNIQUE (project, scene, item_type, item_id)
key so a pin⇄exclude flip replaces the row in place (never two rows for one
item).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.models import SceneGroundingPin
from app.db.repositories import ReferenceViolationError

_SELECT_COLS = """
  id, created_by, project_id, outline_node_id, item_type, item_id, action, created_at
"""


def _row_to_pin(row: asyncpg.Record) -> SceneGroundingPin:
    return SceneGroundingPin.model_validate(dict(row))


class GroundingPinsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_for_scene(
        self, project_id: UUID, outline_node_id: UUID,
    ) -> list[SceneGroundingPin]:
        """All pin/exclude rows for one scene — the set `pack()` applies. Uses
        idx_scene_grounding_pins_scene."""
        query = f"""
        SELECT {_SELECT_COLS} FROM scene_grounding_pins
        WHERE project_id = $1 AND outline_node_id = $2
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, outline_node_id)
        return [_row_to_pin(r) for r in rows]

    async def set_action(
        self, project_id: UUID, outline_node_id: UUID,
        item_type: str, item_id: str, action: str, *, created_by: UUID,
    ) -> SceneGroundingPin:
        """Pin or exclude an item — upsert on the UNIQUE key so a pin⇄exclude flip
        replaces the existing row in place (created_at + created_by refreshed —
        last-writer actor). The scene's scope/existence is gated at the router
        (SEC2) BEFORE this call."""
        query = f"""
        INSERT INTO scene_grounding_pins
          (created_by, project_id, book_id, outline_node_id, item_type, item_id, action)
        SELECT $1, $2, w.book_id, $3, $4, $5, $6
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        ON CONFLICT (project_id, outline_node_id, item_type, item_id)
        DO UPDATE SET action = EXCLUDED.action, created_by = EXCLUDED.created_by,
                      created_at = now()
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, created_by, project_id, outline_node_id, item_type, item_id, action,
            )
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row_to_pin(row)

    async def clear(
        self, project_id: UUID, outline_node_id: UUID,
        item_type: str, item_id: str,
    ) -> bool:
        """Remove an item's steering (return it to default budget behavior). True
        when a row was deleted, False when there was nothing to clear."""
        query = """
        DELETE FROM scene_grounding_pins
        WHERE project_id = $1 AND outline_node_id = $2
          AND item_type = $3 AND item_id = $4
        """
        async with self._pool.acquire() as c:
            result = await c.execute(query, project_id, outline_node_id, item_type, item_id)
        # asyncpg returns "DELETE <n>"
        return result.rsplit(" ", 1)[-1] != "0"
