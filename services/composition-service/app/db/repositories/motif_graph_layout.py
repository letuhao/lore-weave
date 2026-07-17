"""Wave-4 (D-MOTIF-GRAPH-CANVAS) — the per-viewer motif-graph node positions store.

Positions are a cosmetic, REGENERABLE per-viewer preference (scope key owner_user_id +
book_id): each user arranges their own view, so they never live on the shared motif /
motif_link rows. The write is a SERVER-SIDE MERGE (positions || moves) so two nodes dragged
in quick succession never clobber each other, with an optimistic `version` for the rare
multi-device same-user race (a mismatch → None, which the route maps to a fail-soft 412 +
the current state for the client to reseed). Drop the row → the canvas auto-lays-out.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg


# D-MOTIF-GRAPH-BOOK-SCOPING (Option B — the book's STORY graph): a node is (a) the book's
# SHARED authoring tier, or (b) the caller's OWN motif actually BOUND in THIS book (a
# motif_application row). NOT the caller's whole library, NOT other books, NOT system/public
# (you bind a *clone* of those, and the motif_link_guard forbids cross-tier edges → islands).
# $1 = caller, $2 = book; the EXISTS correlates on the outer `motif.id`. ONE fragment shared by
# nodes_for_book (what shows) and motif_visible_in_book (what a caller may position) so a shown
# node is always position-able and a non-node is always rejected (one-predicate-two-callsites).
_BOOK_NODE_PREDICATE = (
    "((book_shared AND book_id = $2) "
    "OR (owner_user_id = $1 AND EXISTS ("
    "SELECT 1 FROM motif_application ma WHERE ma.book_id = $2 AND ma.motif_id = motif.id)))"
)


class MotifGraphLayoutRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def nodes_for_book(
        self, caller_id: UUID, book_id: UUID, limit: int,
    ) -> list[dict[str, Any]]:
        """The graph NODES for a book (D-MOTIF-GRAPH-BOOK-SCOPING, Option B): the book's shared
        tier + the caller's own motifs BOUND in this book. Bounded by `limit`; own-tier first,
        then by name for a stable layout seed."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"""
                SELECT id, owner_user_id, book_shared, code, kind, name, visibility
                FROM motif
                WHERE status = 'active' AND {_BOOK_NODE_PREDICATE}
                ORDER BY (owner_user_id = $1) DESC, name
                LIMIT $3
                """,
                caller_id, book_id, max(0, limit),
            )
        return [dict(r) for r in rows]

    async def edges_among(self, node_ids: list[UUID]) -> list[dict[str, Any]]:
        """The motif_link edges whose BOTH endpoints are in the node set (an edge to a node not
        shown is omitted — no dangling edge). Empty when fewer than two nodes."""
        if len(node_ids) < 2:
            return []
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                "SELECT id, from_motif_id, to_motif_id, kind, ord FROM motif_link "
                "WHERE from_motif_id = ANY($1::uuid[]) AND to_motif_id = ANY($1::uuid[])",
                node_ids,
            )
        return [dict(r) for r in rows]

    async def motif_visible_in_book(self, caller_id: UUID, book_id: UUID, motif_id: UUID) -> bool:
        """Is `motif_id` a node the caller may position in this book's graph? Uses the SAME
        `_BOOK_NODE_PREDICATE` as `nodes_for_book`, so a shown node is always position-able and a
        non-node (unbound / other book / system) is always rejected (a 404, no oracle)."""
        async with self._pool.acquire() as c:
            found = await c.fetchval(
                f"SELECT 1 FROM motif WHERE id = $3 AND status = 'active' AND {_BOOK_NODE_PREDICATE}",
                caller_id, book_id, motif_id,
            )
        return found is not None

    async def get(self, owner_user_id: UUID, book_id: UUID) -> tuple[dict[str, Any], int]:
        """The caller's stored positions + version for this book, or ({}, 0) when none yet.
        version 0 signals "no row" so the client sends if_version=0 on its first write."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT positions, version FROM motif_graph_layout "
                "WHERE owner_user_id = $1 AND book_id = $2",
                owner_user_id, book_id,
            )
        if row is None:
            return ({}, 0)
        return (_loads(row["positions"]), int(row["version"]))

    async def merge(
        self, owner_user_id: UUID, book_id: UUID,
        moves: dict[str, dict[str, float]], if_version: int,
    ) -> tuple[dict[str, Any], int] | None:
        """Merge `moves` ({motif_id: {x,y}}) into the caller's OWN layout row (upsert), bumping
        `version`. Returns the new (positions, version), or None on an OCC conflict (an existing
        row whose version != if_version). The UPDATE is scoped to owner_user_id — a caller can
        only ever write their OWN positions (no path touches another viewer's row).

        First write (no row) INSERTs at version 1 regardless of if_version (first-writer-wins on a
        cosmetic cache). An existing row updates only when `version = if_version`; a mismatch does
        neither the insert (conflict) nor the update (WHERE false) → 0 rows → None → the 412 path."""
        if not moves:
            return await self.get(owner_user_id, book_id)
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                """
                INSERT INTO motif_graph_layout (owner_user_id, book_id, positions, version)
                VALUES ($1, $2, $3::jsonb, 1)
                ON CONFLICT (owner_user_id, book_id) DO UPDATE
                  SET positions  = motif_graph_layout.positions || EXCLUDED.positions,
                      version    = motif_graph_layout.version + 1,
                      updated_at = now()
                  WHERE motif_graph_layout.version = $4
                RETURNING positions, version
                """,
                owner_user_id, book_id, json.dumps(moves), if_version,
            )
        if row is None:
            return None  # OCC conflict — the route reseeds the client with get()
        return (_loads(row["positions"]), int(row["version"]))


def _loads(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return value or {}
