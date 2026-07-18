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

# The same columns, table-qualified — `list_by_book` joins outline_node (which also has
# `id`, `project_id`, `created_by`, `created_at`), so the bare list above would be an
# ambiguous-column error.
_SELECT_COLS_SL = """
  sl.id, sl.created_by, sl.project_id, sl.from_node_id, sl.to_node_id,
  sl.kind, sl.label, sl.created_at
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
            # A scene_link is the non-derivable SCENE→SCENE edge (F-H7). A chapter-level "link"
            # is already expressible as reading order, so it is not a thing. The FE refuses it,
            # but the invariant belongs HERE: an MCP/REST caller reaches the same repo through a
            # different front door, and a rule that lives only in one client is not a rule.
            kinds = await c.fetchval(
                "SELECT count(*) FROM outline_node "
                "WHERE project_id = $1 AND id = ANY($2::uuid[]) AND kind = 'scene'",
                project_id, [from_node_id, to_node_id],
            )
            if kinds != 2:
                raise ReferenceViolationError(
                    "scene_link endpoints must both be SCENE nodes"
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

    async def list_by_book(self, book_id: UUID) -> list[dict]:
        """24 PH13/H1.4 — every scene-link edge of a BOOK in one call (mirrors
        list_by_project but keyed on `book_id`, the Hub's tenancy scope — BPS-8).
        scene_link edges are sparse by design ("ONLY non-derivable edges"), so a
        whole-book fetch is cheap (F-H7). Served by idx_scene_link_book. Access is
        decided BEFORE the repo, at the E0 VIEW gate on `book_id`.

        Each endpoint carries its ANCESTRY — the parent chapter node and the arc:

            {from,to}_chapter_node_id · {from,to}_arc_id

        PH13 requires an edge whose endpoint is collapsed to render as a STUB into the
        collapsed node, "never silently dropped". The canvas cannot do that from the raw
        row: a collapsed arc never loads its chapter window, so its scenes are not loaded
        either, and the client has NO WAY to learn which lane an unloaded endpoint lives
        in. React Flow then gets an edge naming a node that does not exist and drops it
        without a word — exactly the silent truncation PH13 forbids. The ancestry is one
        cheap join here; on the client it is unknowable.

        `structure_node_id` lives only on chapters (the `outline_structure_kind` CHECK), so
        a scene's arc rides its parent chapter's — the COALESCE pattern `plan_overlay`'s
        thread query already uses. An endpoint that is itself a chapter carries its own.
        Returns plain dicts (not `SceneLink`) because the ancestry is a JOIN-derived
        projection, not columns of the row.
        """
        query = f"""
        SELECT {_SELECT_COLS_SL},
               f.parent_id AS from_chapter_node_id,
               t.parent_id AS to_chapter_node_id,
               COALESCE(f.structure_node_id, fc.structure_node_id) AS from_arc_id,
               COALESCE(t.structure_node_id, tc.structure_node_id) AS to_arc_id
        FROM scene_link sl
        LEFT JOIN outline_node f  ON f.id = sl.from_node_id
        LEFT JOIN outline_node fc ON fc.id = f.parent_id
        LEFT JOIN outline_node t  ON t.id = sl.to_node_id
        LEFT JOIN outline_node tc ON tc.id = t.parent_id
        WHERE sl.book_id = $1
        ORDER BY sl.created_at, sl.id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, book_id)
        return [dict(r) for r in rows]

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
