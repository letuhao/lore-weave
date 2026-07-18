"""C-merge C2 — the manuscript-parts → structure_node mirror reconcile.

book-service emits `manuscript_part.changed {book_id}` on any part mutation; composition's consumer
RE-READS the book's active parts (book_client.list_parts_mirror) and calls this to reconcile the
kind='part' structure_node rows. Idempotent + order-insensitive: whatever book-service says NOW is what
the mirror becomes (the chapter.scenes_linked discipline), so replay/redelivery in any order converges.

DESIGN INVARIANT: structure_node.id == part.id (1:1 same-UUID mirror). So the upsert is keyed by the
part's own id, chapters.structure_node_id (set book-side) already equals part_id, and C4 is a rename.

TEMPORARY: deleted at C4 when parts is retired and structure_node is the sole SSOT.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


def _rank_for(sort_order: int) -> str:
    """A lexically-sortable rank derived from the part's sort_order. structure_node.rank is free-form
    TEXT ordered `COLLATE "C"`; a fixed-width zero-pad sorts identically to the integer order. Only
    'part' siblings are compared against each other at read time (C3 filters kind='part')."""
    return f"{max(sort_order, 0):08d}"


async def reconcile_book_parts(pool: asyncpg.Pool, book_id: UUID, parts: list[dict[str, Any]]) -> dict[str, int]:
    """Make the book's kind='part' structure_node rows match `parts` (from book-service). Upserts each
    present part (by id == part.id), archives any kind='part' node no longer present. One transaction.
    Returns {upserted, archived}."""
    ids = [UUID(str(p["id"])) for p in parts]
    async with pool.acquire() as conn:
        async with conn.transaction():
            upserted = 0
            for p in parts:
                pid = UUID(str(p["id"]))
                # ON CONFLICT guarded on kind='part' so a (astronomically unlikely) id collision with a
                # real arc/saga can never be silently overwritten into a part.
                await conn.execute(
                    """
                    INSERT INTO structure_node (id, book_id, kind, rank, title, parent_id)
                    VALUES ($1, $2, 'part', $3, $4, NULL)
                    ON CONFLICT (id) DO UPDATE
                       SET title = EXCLUDED.title,
                           rank = EXCLUDED.rank,
                           is_archived = false,
                           updated_at = now()
                     WHERE structure_node.kind = 'part'
                    """,
                    pid, book_id, _rank_for(int(p.get("sort_order", 0))), str(p.get("title", "")),
                )
                upserted += 1
            # Archive parts that vanished from book-service (trashed/deleted) — the mirror must not keep
            # claiming a grouping the author removed.
            archived_ids = await conn.fetch(
                """
                UPDATE structure_node SET is_archived = true, updated_at = now()
                 WHERE book_id = $1 AND kind = 'part' AND is_archived = false
                   AND NOT (id = ANY($2::uuid[]))
                RETURNING id
                """,
                book_id, ids,
            )
    result = {"upserted": upserted, "archived": len(archived_ids)}
    logger.info("parts-mirror: book %s reconciled (upserted=%d archived=%d)",
                book_id, result["upserted"], result["archived"])
    return result
