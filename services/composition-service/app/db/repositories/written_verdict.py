"""SC11 amendment Phase 1 — the WRITTEN VERDICT mirror.

`outline_node.written_scene_id` answers "is there prose behind this spec node?" as a COLUMN, not a
computation. It is a **regenerable cache of the inverse of `scenes.source_scene_id`**, and every
operation in this module is a RECONCILE against book-service's truth — never an incremental patch
from an event payload.

WHY RECONCILE, NOT PATCH. The relay is at-least-once and un-ordered. If `chapter.scenes_linked`
carried the mappings and we applied them, a stale redelivery would happily overwrite newer state.
A re-read cannot: whatever book-service says NOW is what the mirror becomes. That makes every
function here idempotent, order-insensitive and self-healing — the reason the event deliberately
carries only `{book_id, chapter_id}`.

THE CLEAR IS AS IMPORTANT AS THE SET, and it is the half that is easy to forget. A scene can be
DELETED (a re-parse drops it; a chapter is trashed), and the node it backed becomes unwritten. A
mirror that only ever SETS would keep claiming prose that no longer exists — which is worse than
never having had the column, because a stale "written" is a confident lie.

⚠ This does NOT re-invert SC2/DA-3 (see the DDL comment in migrate.py): `scenes.source_scene_id`
remains the sole authored anchor, owned by the index owner. book-service always wins.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class WrittenVerdictRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def reconcile_chapter(
        self, book_id: UUID, chapter_id: UUID, links: list[tuple[UUID, UUID]],
    ) -> dict[str, int]:
        """Make the mirror match book-service's truth FOR ONE CHAPTER.

        `links` is [(outline_node_id, scene_id)] — every scene of this chapter that carries a
        `source_scene_id`, straight from book-service. Anything not in it is, by definition, not
        written *by this chapter's prose*.

        Returns {"linked": n, "cleared": n} — the actual row counts, so a caller can tell a real
        reconcile from a no-op instead of assuming one happened (a silent success is a bug).
        """
        node_ids = [n for n, _ in links]
        scene_ids = [s for _, s in links]
        async with self._pool.acquire() as c, c.transaction():
            # SET/MOVE. `IS DISTINCT FROM` makes a no-op reconcile cost ZERO writes and leaves
            # `written_at` alone — so the timestamp means "when the prose appeared", not "when the
            # sweeper last ran". RETURNING gives the real count: a caller can tell a reconcile that
            # DID something from one that did nothing, instead of assuming.
            linked = await c.fetchval(
                """
                WITH t(node_id, scene_id) AS (
                  SELECT * FROM unnest($2::uuid[], $3::uuid[])
                ), upd AS (
                  UPDATE outline_node n
                     SET written_scene_id = t.scene_id, written_at = now(),
                         written_chapter_id = $4
                    FROM t
                   WHERE n.id = t.node_id AND n.book_id = $1
                     AND (n.written_scene_id IS DISTINCT FROM t.scene_id
                          OR n.written_chapter_id IS DISTINCT FROM $4)
                  RETURNING 1
                )
                SELECT count(*) FROM upd
                """,
                book_id, node_ids, scene_ids, chapter_id,
            ) or 0

            # CLEAR — the half that is easy to forget, AND the half I first got wrong.
            #
            # Keyed on `written_chapter_id` (which chapter's PROSE backs the node), NOT on
            # `chapter_id` (which chapter the node BELONGS to). They are different columns and they
            # come apart for real:
            #   * nothing constrains a scene's `source_scene_id` to a node of its own chapter, so
            #     copy-pasted prose makes chapter A's scene back a node whose spec chapter is B.
            #     Clearing by `chapter_id` made the two chapters FIGHT — set, clear, set — and the
            #     mirror never converged.
            #   * `chapter_id` is NULL on a PLANNED node (most of them). A chapter-scoped CLEAR
            #     could never reach one, and the sweeper skips NULLs too, so a stale link there was
            #     PERMANENT.
            # "The nodes this chapter's prose used to back, and no longer does" is correct in both.
            cleared = await c.fetchval(
                """
                WITH upd AS (
                  UPDATE outline_node
                     SET written_scene_id = NULL, written_at = NULL, written_chapter_id = NULL
                   WHERE book_id = $1
                     AND written_chapter_id = $2          -- the chapter whose PROSE backed it…
                     AND written_scene_id IS NOT NULL
                     AND NOT (id = ANY($3::uuid[]))       -- …and no longer does
                  RETURNING 1
                )
                SELECT count(*) FROM upd
                """,
                book_id, chapter_id, node_ids,
            ) or 0

        return {"linked": int(linked), "cleared": int(cleared)}

    async def clear_chapter(self, book_id: UUID, chapter_id: UUID) -> int:
        """Every spec node of this chapter is now unwritten — its prose is GONE
        (`chapter.trashed` / `chapter.deleted`). Spec §5.2b: the link also breaks when the SCENE
        vanishes, without `source_scene_id` ever being touched. A mirror that ignored this would
        keep claiming prose the author has deleted.

        This IS `reconcile_chapter` with an empty truth-set — the same code path, so it cannot
        drift from it."""
        return (await self.reconcile_chapter(book_id, chapter_id, []))["cleared"]

    async def clear_orphans(self, book_id: UUID) -> int:
        """Clear nodes claiming prose that no chapter owns — `written_scene_id` set with
        `written_chapter_id` NULL.

        Such a row is UNREACHABLE by any chapter-scoped CLEAR (which keys on written_chapter_id), so
        it would be permanently, silently stale — the exact class of bug that made me key the CLEAR
        on the wrong column in the first place. It should be impossible (every SET writes both
        columns together, in one statement), and that is precisely why the sweeper must still be
        able to heal it: a cache you cannot regenerate from truth is not a cache, it is a second
        source of truth.

        ONLY safe from the book-wide reconcile, which has just authoritatively re-stamped
        `written_chapter_id` on every genuinely-written node from book-service's answer. Anything
        still orphaned after that is garbage.
        """
        async with self._pool.acquire() as c:
            return await c.fetchval(
                """
                WITH upd AS (
                  UPDATE outline_node
                     SET written_scene_id = NULL, written_at = NULL, written_chapter_id = NULL
                   WHERE book_id = $1
                     AND written_scene_id IS NOT NULL
                     AND written_chapter_id IS NULL
                  RETURNING 1
                )
                SELECT count(*) FROM upd
                """,
                book_id,
            ) or 0

    async def written_map(self, book_id: UUID) -> dict[str, str]:
        """{outline_node_id: written_scene_id} for a book — what the Plan Hub renders. The partial
        index (`WHERE written_scene_id IS NOT NULL`) makes this cheap on a mostly-unwritten book."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT id, written_scene_id FROM outline_node
                 WHERE book_id = $1 AND written_scene_id IS NOT NULL AND NOT is_archived
                """,
                book_id,
            )
        return {str(r["id"]): str(r["written_scene_id"]) for r in rows}

    async def books_with_spec(self, *, after: UUID | None = None, limit: int = 200) -> list[UUID]:
        """The backfill/sweeper cursor: books that HAVE spec nodes, keyset-paged by book_id.

        Keyset (not OFFSET) so the walk is RESUMABLE — a crash mid-backfill resumes from the last
        book it finished, and a book inserted during the walk cannot shift the page under it."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT DISTINCT book_id FROM outline_node
                 WHERE kind IN ('chapter','scene') AND NOT is_archived
                   AND ($1::uuid IS NULL OR book_id > $1)
                 ORDER BY book_id
                 LIMIT $2
                """,
                after, limit,
            )
        return [r["book_id"] for r in rows]


def links_from_scenes(scenes: list[dict[str, Any]]) -> dict[UUID, list[tuple[UUID, UUID]]]:
    """Group book-service's scene rows into {chapter_id: [(node_id, scene_id)]}.

    Only scenes that actually carry a `source_scene_id` produce a link. A scene with none is not
    "unwritten" — it is prose with no spec node, which is the PH21 unplanned tray's business, not
    this mirror's.
    """
    out: dict[UUID, list[tuple[UUID, UUID]]] = {}
    for s in scenes:
        ch = s.get("chapter_id")
        if not ch:
            continue
        ch_id = ch if isinstance(ch, UUID) else UUID(str(ch))
        out.setdefault(ch_id, [])
        ssid, sid = s.get("source_scene_id"), s.get("id")
        if not ssid or not sid:
            continue
        out[ch_id].append((
            ssid if isinstance(ssid, UUID) else UUID(str(ssid)),
            sid if isinstance(sid, UUID) else UUID(str(sid)),
        ))
    return out
