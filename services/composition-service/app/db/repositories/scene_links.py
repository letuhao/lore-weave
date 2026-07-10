"""scene_link repository — non-derivable scene edges (setup_payoff / custom).

SCOPE RULE (package re-key, spec 25 §Repo/service layer): reads key on
`project_id` — access is decided BEFORE the repo, at the gate (E0 grant on the
row's `book_id`). Writes stamp `created_by` (a plain actor stamp — STORED,
never filtered on) and derive `book_id` from composition_work inside the
INSERT. Edges have no archive column and no children, so DELETE is a hard
delete (the only hard delete in M2) — and it is always project-bound, so an
edge from another Work (gated on a different book) can never be deleted under
this Work's gate. The unique (from,to,kind) constraint makes create
idempotent-ish — a duplicate raises UniqueViolation, surfaced to the router as
a 409.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.models import SceneLink
from app.db.repositories import ReferenceViolationError, rows_changed

_SELECT_COLS = """
  id, created_by, project_id, from_node_id, to_node_id, kind, label, created_at
"""


def _row_to_link(row: asyncpg.Record) -> SceneLink:
    return SceneLink.model_validate(dict(row))


class SceneLinksRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        project_id: UUID,
        from_node_id: UUID,
        to_node_id: UUID,
        *,
        created_by: UUID,
        kind: str = "setup_payoff",
        label: str = "",
    ) -> SceneLink:
        query = f"""
        INSERT INTO scene_link (created_by, project_id, book_id, from_node_id, to_node_id, kind, label)
        SELECT $1, $2, w.book_id, $3, $4, $5, $6
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            # Defense-in-depth (D-COMP-M2-XREF-OWNERSHIP): both endpoints must be
            # nodes in THIS project — the in-DB FK only proves they exist, not
            # that they're in scope. Distinct from/to is enforced by the table
            # CHECK; here we guard the project scope.
            owned = await c.fetchval(
                "SELECT count(*) FROM outline_node "
                "WHERE project_id = $1 AND id = ANY($2::uuid[])",
                project_id, [from_node_id, to_node_id],
            )
            if owned != 2:
                raise ReferenceViolationError(
                    "scene_link endpoints must both be nodes in this project"
                )
            row = await c.fetchrow(
                query, created_by, project_id, from_node_id, to_node_id, kind, label
            )
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row_to_link(row)

    async def list_by_project(self, project_id: UUID) -> list[SceneLink]:
        query = f"""
        SELECT {_SELECT_COLS} FROM scene_link
        WHERE project_id = $1
        ORDER BY created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row_to_link(r) for r in rows]

    async def delete(self, project_id: UUID, link_id: UUID) -> bool:
        """Hard-delete an edge. Returns False on a missing id or an edge outside
        this project. The project bind is mandatory (kinds-bug scope rule): an
        edge from another Work — gated on a different book — cannot be deleted
        under the resolved Work's book gate."""
        async with self._pool.acquire() as c:
            status = await c.execute(
                "DELETE FROM scene_link WHERE project_id = $1 AND id = $2",
                project_id, link_id,
            )
        return rows_changed(status) > 0
