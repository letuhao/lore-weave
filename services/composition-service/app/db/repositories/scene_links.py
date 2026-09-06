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
  id, created_by, project_id, from_node_id, to_node_id, kind, label, is_archived, created_at
"""

# The same columns, table-qualified — `list_by_book` joins outline_node (which also has
# `id`, `project_id`, `created_by`, `created_at`), so the bare list above would be an
# ambiguous-column error.
_SELECT_COLS_SL = """
  sl.id, sl.created_by, sl.project_id, sl.from_node_id, sl.to_node_id,
  sl.kind, sl.label, sl.is_archived, sl.created_at
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
            # ...and both must be LIVE. `archive_node` cascades over the outline subtree and does
            # not touch scene_link, so without this an author could draw a causal edge onto a
            # scene they had already archived — an edge to something the tree no longer shows.
            # The FE picker already filters archived targets, but (as with the kind rule above)
            # a rule that lives only in one client is not a rule: MCP and REST reach this same
            # repo through different front doors.
            kinds = await c.fetchval(
                "SELECT count(*) FROM outline_node "
                "WHERE project_id = $1 AND id = ANY($2::uuid[]) "
                "AND kind = 'scene' AND NOT is_archived",
                project_id, [from_node_id, to_node_id],
            )
            if kinds != 2:
                raise ReferenceViolationError(
                    "scene_link endpoints must both be LIVE SCENE nodes"
                )
            row = await c.fetchrow(
                query, created_by, project_id, from_node_id, to_node_id, kind, label
            )
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row_to_link(row)

    async def list_by_project(
        self, project_id: UUID, *, include_archived: bool = False,
    ) -> list[SceneLink]:
        """Live edges only — and "live" includes the ENDPOINTS.

        `archive_node` cascades over the outline subtree and deliberately does not touch
        scene_link, so archiving a scene used to leave its causal edges behind: still returned,
        pointing at a node the tree no longer shows (the FE resolved the missing title to a
        short id, so the author saw an edge to `deadbeef…`). Filtering on the endpoints here
        rather than cascading the archive keeps the pair SYMMETRIC for free — restore the scene
        and its edges come back, with no `archived_by_cascade` bookkeeping to get wrong, and
        with an edge the author deleted themselves staying deleted.

        `include_archived` — owner ruling 2026-08-31 (DQ-T44 (a)):
        composition_scene_link_edit ships a `restore` op and NOTHING lists what is restorable, so
        the only way to hold the id is to have written it down before deleting. Measured live:
        the model correctly answers "I can't see it in the trash without an ID".

        🔴 THE FLAG ANSWERS THE ENDPOINT QUESTION IT WOULD OTHERWISE RAISE, which is why this is
        one argument and not a design. The row that owns this defect warned that a recycle-bin
        listing must decide whether to show an edge whose endpoint is archived — and the ONLY
        caller that passes True is `composition_list_outline`, where the SAME flag is already
        being passed to `list_tree`. The archived endpoints are therefore in the tree beside the
        edge: the symmetry the docstring above is built on holds in both directions, and the
        `deadbeef…` failure it describes cannot come back through this door.

        Default False, so the two callers that do not pass it — the packer lens and the outline
        router — keep the live-only view they were written against.
        """
        archived_clause = "" if include_archived else """
          AND NOT sl.is_archived
          AND EXISTS (SELECT 1 FROM outline_node f
                      WHERE f.id = sl.from_node_id AND NOT f.is_archived)
          AND EXISTS (SELECT 1 FROM outline_node t
                      WHERE t.id = sl.to_node_id AND NOT t.is_archived)"""
        query = f"""
        SELECT {_SELECT_COLS_SL} FROM scene_link sl
        WHERE sl.project_id = $1{archived_clause}
        ORDER BY sl.created_at, sl.id
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
        WHERE sl.book_id = $1 AND NOT sl.is_archived
          -- Same rule as list_by_project: an edge whose endpoint has been archived is not a
          -- live edge. These are LEFT JOINs (an endpoint row can be missing entirely), so the
          -- NULL case must be excluded explicitly — `NOT f.is_archived` alone is NULL, not
          -- true, for a missing row, which happens to drop it, but relying on that would be
          -- an accident rather than a stated rule.
          AND f.id IS NOT NULL AND NOT f.is_archived
          AND t.id IS NOT NULL AND NOT t.is_archived
        ORDER BY sl.created_at, sl.id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, book_id)
        return [dict(r) for r in rows]

    async def delete(self, project_id: UUID, link_id: UUID) -> bool:
        """SOFT-delete an edge. Returns False on a missing id or an edge outside this project.

        The project bind is mandatory (kinds-bug scope rule): an edge from another Work — gated on
        a different book — cannot be deleted under the resolved Work's book gate.

        Was a hard DELETE with no undo, unlike its sibling atoms (F3, 2026-07-27). A scene link is
        the author's DECLARED setup/payoff connection and carries an authored `label`; losing it
        irreversibly loses structural work that only the author can reconstruct."""
        async with self._pool.acquire() as c:
            status = await c.execute(
                "UPDATE scene_link SET is_archived = true "
                "WHERE project_id = $1 AND id = $2 AND NOT is_archived",
                project_id, link_id,
            )
        return rows_changed(status) > 0

    async def restore(self, project_id: UUID, link_id: UUID) -> bool:
        """The UNDO the delete now promises. False when nothing matched or it was never archived —
        including when the author has since re-declared that same edge (the partial unique), which
        is honest: resurrecting the old one would collide with the newer."""
        try:
            async with self._pool.acquire() as c:
                status = await c.execute(
                    "UPDATE scene_link SET is_archived = false "
                    "WHERE project_id = $1 AND id = $2 AND is_archived",
                    project_id, link_id,
                )
        except asyncpg.UniqueViolationError:
            # The partial unique is doing its job: that same edge has been re-declared since, so
            # un-archiving this one would collide. Found by a LIVE probe — the docstring promised
            # False and the code actually RAISED, which the MCP handler would have surfaced as a
            # 500 instead of the honest "could not be restored" it was written to return.
            return False
        return rows_changed(status) > 0
