"""kg_views read+write repository (epic 2026-06-20, lane LD).

A **view** is a per-user named lens — `{edge_type_codes[], node_kind_codes[]}`
— over the SAME project graph. Views are READ-only filters (extraction never
runs view-scoped, spec §10-C3); this repo only owns their CRUD lifecycle.

Tenancy (CLAUDE.md "User Boundaries & Tenancy" + spec §3.3): a view is
**per-user inside a (possibly shared) project** — `UNIQUE (project_id,
user_id, code)`. Every method takes `user_id` as its FIRST argument and every
query filters by it (the house security-rule pattern, mirroring the other
repos), so a caller can only ever see/mutate their OWN views — never another
user's, even within a shared project. The router enforces `owner == caller`;
this repo is the structural belt to that suspender.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §3.3.
Contract: contracts/api/knowledge-service/views.yaml.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.ontology_models import GraphView

_VIEW_COLS = """
  view_id, project_id, user_id, code, name, description,
  edge_type_codes, node_kind_codes, created_at, updated_at
"""


def _row_to_view(row: asyncpg.Record) -> GraphView:
    return GraphView.model_validate(dict(row))


class GraphViewsRepo:
    """Owner-scoped CRUD over `kg_views`."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list(self, user_id: UUID, project_id: str) -> list[GraphView]:
        """All of the caller's views in a project, ordered by code.

        Owner-scoped: only `user_id`'s rows — a co-collaborator's views in
        the same shared project are NEVER returned.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_VIEW_COLS} FROM kg_views
                WHERE user_id = $1 AND project_id = $2
                ORDER BY code
                """,
                user_id,
                project_id,
            )
        return [_row_to_view(r) for r in rows]

    async def get(
        self, user_id: UUID, project_id: str, code: str
    ) -> GraphView | None:
        """One view by `(project_id, user_id, code)`. None when the caller
        owns no such view (cross-user / missing collapse to the same None —
        no existence oracle)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_VIEW_COLS} FROM kg_views
                WHERE user_id = $1 AND project_id = $2 AND code = $3
                """,
                user_id,
                project_id,
                code,
            )
        return _row_to_view(row) if row else None

    async def create(
        self,
        user_id: UUID,
        project_id: str,
        *,
        code: str,
        name: str,
        description: str = "",
        edge_type_codes: list[str] | None = None,
        node_kind_codes: list[str] | None = None,
    ) -> GraphView:
        """INSERT a new view owned by `user_id`. Raises
        `asyncpg.UniqueViolationError` if `(project_id, user_id, code)`
        already exists (the router maps that to 409)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO kg_views
                  (project_id, user_id, code, name, description,
                   edge_type_codes, node_kind_codes)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING {_VIEW_COLS}
                """,
                project_id,
                user_id,
                code,
                name,
                description,
                list(edge_type_codes or []),
                list(node_kind_codes or []),
            )
        return _row_to_view(row)

    async def upsert(
        self,
        user_id: UUID,
        project_id: str,
        *,
        code: str,
        name: str,
        description: str = "",
        edge_type_codes: list[str] | None = None,
        node_kind_codes: list[str] | None = None,
    ) -> tuple[GraphView, bool]:
        """Upsert a view by `(project_id, user_id, code)` (PUT semantics).

        Returns `(view, created)` — `created` is True on INSERT, False when
        an existing row was UPDATEd. The `ON CONFLICT` target is the
        owner-scoped unique key, so the upsert can NEVER touch another
        user's view (it would not conflict on that user's key, and the
        WHERE on the implicit conflict row is the same composite key).
        `created_at` is preserved on update; `updated_at` is bumped.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO kg_views
                  (project_id, user_id, code, name, description,
                   edge_type_codes, node_kind_codes)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (project_id, user_id, code) DO UPDATE SET
                  name = EXCLUDED.name,
                  description = EXCLUDED.description,
                  edge_type_codes = EXCLUDED.edge_type_codes,
                  node_kind_codes = EXCLUDED.node_kind_codes,
                  updated_at = now()
                RETURNING {_VIEW_COLS}, (xmax = 0) AS _created
                """,
                project_id,
                user_id,
                code,
                name,
                description,
                list(edge_type_codes or []),
                list(node_kind_codes or []),
            )
        data = dict(row)
        created = bool(data.pop("_created"))
        return GraphView.model_validate(data), created

    async def delete(self, user_id: UUID, project_id: str, code: str) -> bool:
        """Hard-delete a view (views carry no data). Returns True if a row
        was deleted, False if the caller owns no such view (cross-user /
        missing → False, mapped to 404 by the router)."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM kg_views
                WHERE user_id = $1 AND project_id = $2 AND code = $3
                """,
                user_id,
                project_id,
                code,
            )
        # asyncpg returns "DELETE <n>" — n>0 means a row was removed.
        return result.rsplit(" ", 1)[-1] != "0"
