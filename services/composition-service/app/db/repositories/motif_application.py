"""motif_application repository — the binding ledger (W2-owned; the binder is the
SOLE writer, 00-RECONCILE §2).

A row records "this motif (at this pinned version) was bound to this outline scene
node, with these role→entity bindings + annotations (beat_key, reversal, …)". W5's
conformance trace JOINs this table per scene `outline_node_id` (read-only). The
table + its scope/cycle guards are F0-frozen (migrate.py); this repo only
reads/writes rows under the (project, book) package scope keys — access is decided
BEFORE the repo, at the gate (E0 grant on the row's `book_id`); `created_by` is a
plain actor stamp (STORED, never filtered on). The motif/template FKs keep their
2-tier registry tenancy (untouched by the package re-key).

Anti-repetition (W2 §7.6): `count_by_motif_for_book` is the per-book aggregate the
planner reads at select time (the idx_motif_application_book_motif hot index) so a
motif already applied >= settings.motif_max_reapply times is deprioritized.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import MotifApplication

_SELECT_COLS = (
    "id, created_by, project_id, book_id, motif_id, motif_version, outline_node_id, "
    "structure_node_id, role_bindings, annotations, created_at"
)
_JSONB_FIELDS = ("role_bindings", "annotations")


def _row(r: asyncpg.Record) -> MotifApplication:
    data = dict(r)
    for f in _JSONB_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return MotifApplication.model_validate(data)


class MotifApplicationRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert_many(
        self, project_id: UUID, book_id: UUID,
        rows: list[dict[str, Any]], *, created_by: UUID,
        conn: asyncpg.Connection | None = None,
    ) -> list[MotifApplication]:
        """Insert binding-ledger rows (one per bound scene). Each `row` carries
        motif_id, motif_version, outline_node_id, role_bindings, annotations. Runs on
        an OPEN connection when `conn` is given (atomic with the tree/swap Tx). The
        H-5 scope-guard trigger rejects a node not in `project_id` (CheckViolation).
        book_id is the per-book aggregate key (NOT NULL, already threaded here —
        this table predates the package re-key's derive-in-SQL variants)."""
        if not rows:
            return []

        async def _do(c: asyncpg.Connection) -> list[asyncpg.Record]:
            out: list[asyncpg.Record] = []
            for row in rows:
                _sn = row.get("structure_node_id")
                rec = await c.fetchrow(
                    f"""
                    INSERT INTO motif_application
                      (created_by, project_id, book_id, motif_id, motif_version,
                       outline_node_id, structure_node_id, role_bindings, annotations)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb)
                    RETURNING {_SELECT_COLS}
                    """,
                    created_by, project_id, book_id,
                    UUID(row["motif_id"]) if isinstance(row.get("motif_id"), str) else row.get("motif_id"),
                    row.get("motif_version"),
                    UUID(row["outline_node_id"]) if isinstance(row.get("outline_node_id"), str)
                    else row.get("outline_node_id"),
                    UUID(_sn) if isinstance(_sn, str) else _sn,   # BA5: first-class arc link
                    json.dumps(row.get("role_bindings") or {}),
                    json.dumps(row.get("annotations") or {}),
                )
                out.append(rec)
            return out

        if conn is not None:
            recs = await _do(conn)
        else:
            async with self._pool.acquire() as c:
                async with c.transaction():
                    recs = await _do(c)
        return [_row(r) for r in recs]

    async def by_nodes(
        self, project_id: UUID, node_ids: list[UUID],
    ) -> list[MotifApplication]:
        """The bound motif per node (W5's conformance trace read). MUST filter
        project_id (the kinds-bug tenancy rule — a node-id-only query is a
        cross-scope read). Returns the rows for the given scene nodes."""
        if not node_ids:
            return []
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"""
                SELECT {_SELECT_COLS} FROM motif_application
                WHERE project_id = $1 AND outline_node_id = ANY($2)
                ORDER BY created_at
                """,
                project_id, node_ids,
            )
        return [_row(r) for r in rows]

    async def count_by_motif_for_book(
        self, book_id: UUID, *, conn: asyncpg.Connection | None = None,
    ) -> dict[str, int]:
        """{motif_id(str): distinct-bound-chapter count} for the book — the
        anti-repetition aggregate (W2 §7.6). Counts DISTINCT motif applications by
        motif so the same trope reused across the book trips the cap. Scoped to the
        book (per-book scope, R1.1.4) — a book-wide read, gated on the book's E0
        grant before the repo."""
        query = """
            SELECT motif_id, count(*) AS n FROM motif_application
            WHERE book_id = $1 AND motif_id IS NOT NULL
            GROUP BY motif_id
        """

        async def _do(c: asyncpg.Connection) -> list[asyncpg.Record]:
            return await c.fetch(query, book_id)

        if conn is not None:
            recs = await _do(conn)
        else:
            async with self._pool.acquire() as c:
                recs = await _do(c)
        return {str(r["motif_id"]): int(r["n"]) for r in recs}

    async def set_role_binding(
        self, project_id: UUID, node_id: UUID,
        role_key: str, entity_id: UUID | None, *, conn: asyncpg.Connection,
    ) -> int:
        """Rebind ONE role on the node's bound application (D-MOTIF-SCENE-REBIND-CHAIN).

        Targets the single ``role_bindings[role_key]`` key in place (``jsonb_set``) so a
        role rebind never disturbs the other resolved roles, the motif lineage, or
        ``created_at``. ``entity_id=None`` writes a JSON ``null`` — the role stays visible
        but unresolved (matching the FE ``RoleBinding.entity_id=null``). Scoped to
        project+node (the kinds-bug tenancy rule). ``create_missing=false`` so a
        role the binding never had is a no-op (the router guards key membership; this is
        belt-and-suspenders). Returns the rows updated (0 = nothing bound on the node)."""
        val = json.dumps(str(entity_id)) if entity_id is not None else "null"
        res = await conn.execute(
            """
            UPDATE motif_application
            SET role_bindings = jsonb_set(
                  COALESCE(role_bindings, '{}'::jsonb), ARRAY[$3], $4::jsonb, false)
            WHERE project_id = $1 AND outline_node_id = $2
            """,
            project_id, node_id, role_key, val,
        )
        try:
            return int(res.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def delete_for_nodes(
        self, project_id: UUID, node_ids: list[UUID],
        *, conn: asyncpg.Connection,
    ) -> int:
        """Remove the ledger rows for a set of scene nodes (used on a swap — the
        superseded binding's rows are dropped after the scenes are archived; the
        prose generation_job rows are NOT touched, only the binding ledger). Runs on
        the open swap Tx. Scoped to project. Returns the deleted count."""
        if not node_ids:
            return 0
        res = await conn.execute(
            """
            DELETE FROM motif_application
            WHERE project_id = $1 AND outline_node_id = ANY($2)
            """,
            project_id, node_ids,
        )
        # asyncpg returns 'DELETE <n>'
        try:
            return int(res.split()[-1])
        except (ValueError, IndexError):
            return 0
