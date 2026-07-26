"""P2 — repository for the `extraction_leaves` + `extraction_leaves_raw` tables.

Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D1 + §D5.

Provides 7 surfaces:
  - fetch_cached(task_id)        -> ExtractionLeaf | None
  - claim_pending(task_id, ...)  -> bool (atomic insert-or-noop)
  - persist(...)                  -> mark a leaf completed with candidates
  - mark_failed(...)              -> mark a leaf failed; increments retried_n
  - delete_by_chapter(chapter_id, ops) -> (deleted_leaves, deleted_raw)  [WS-0.1]
  - delete_by_book(book_id, ops)  -> (deleted_leaves, deleted_raw) two-step Tx (D5 H2 fix)
  - reset_stale_claims()          -> reset status='running' rows older than 30 min to 'pending'
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class ExtractionLeaf:
    id: UUID
    book_id: UUID
    chapter_id: UUID
    scene_id: UUID
    leaf_path: str
    op: str
    task_id: str
    status: str
    candidates_jsonb: Any  # list[dict] when completed; None otherwise
    retried_n: int
    error_message: str | None
    parse_version: int
    extractor_version: str
    model_ref: str
    glossary_anchor_size: int | None


_VALID_OPS = ("entity", "relation", "event", "fact")


class ExtractionLeavesRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ── Read paths ────────────────────────────────────────────────

    async def fetch_cached(self, task_id: str) -> ExtractionLeaf | None:
        """Return a completed leaf if cached; None otherwise.

        Only returns rows with status='completed' AND non-null candidates_jsonb.
        Used by leaf_processor's pre-LLM cache check.
        """
        row = await self._pool.fetchrow(
            """
            SELECT id, book_id, chapter_id, scene_id, leaf_path, op, task_id, status,
                   candidates_jsonb, retried_n, error_message,
                   parse_version, extractor_version, model_ref,
                   glossary_anchor_size
            FROM extraction_leaves
            WHERE task_id = $1 AND status = 'completed'
            LIMIT 1
            """,
            task_id,
        )
        if row is None:
            return None
        return _row_to_leaf(row)

    # ── Write paths ───────────────────────────────────────────────

    async def claim_pending(
        self,
        *,
        book_id: UUID,
        chapter_id: UUID,
        scene_id: UUID,
        leaf_path: str,
        op: str,
        task_id: str,
        parse_version: int,
        extractor_version: str,
        model_ref: str,
    ) -> bool:
        """Atomic claim: insert pending row, or no-op if (book_id, leaf_path, op)
        already exists. Returns True if this caller successfully claimed.

        Concurrent claimers race here; UNIQUE constraint serialises.
        ON CONFLICT DO NOTHING returns RowCount 0 for the loser.

        `chapter_id` is REQUIRED (WS-0.1): it is the key `delete_by_chapter` uses to
        invalidate one chapter's cache without wiping the whole book's. It is NOT the
        same concept as `scene_id` — scene_id is currently a chapter-id placeholder and
        will diverge once per-scene fanout (D-P2-PER-SCENE-FANOUT) lands.
        """
        if op not in _VALID_OPS:
            raise ValueError(f"unknown op: {op!r}")
        result = await self._pool.execute(
            """
            INSERT INTO extraction_leaves
              (book_id, chapter_id, scene_id, leaf_path, op, task_id, status,
               parse_version, extractor_version, model_ref,
               started_at)
            VALUES
              ($1, $2, $3, $4, $5, $6, 'running',
               $7, $8, $9,
               now())
            ON CONFLICT (book_id, leaf_path, op) DO NOTHING
            """,
            book_id, chapter_id, scene_id, leaf_path, op, task_id,
            parse_version, extractor_version, model_ref,
        )
        # asyncpg returns "INSERT 0 1" on success, "INSERT 0 0" on conflict.
        return result.endswith(" 1")

    async def persist(
        self,
        *,
        task_id: str,
        candidates: list[dict],
        glossary_anchor_size: int | None,
        raw_response: dict | None = None,
        raw_token_usage: dict | None = None,
    ) -> None:
        """Mark a claimed leaf 'completed' with candidates. Optionally write
        the raw response to extraction_leaves_raw (only when project opted in
        — caller decides whether to pass raw_response).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE extraction_leaves
                    SET status = 'completed',
                        candidates_jsonb = $2::jsonb,
                        glossary_anchor_size = $3,
                        completed_at = now(),
                        updated_at = now(),
                        error_message = NULL
                    WHERE task_id = $1 AND status = 'running'
                    RETURNING id
                    """,
                    task_id,
                    json.dumps(candidates),
                    glossary_anchor_size,
                )
                if row is None:
                    logger.warning(
                        "extraction_leaves persist: no running row for task_id=%s "
                        "(race with stale-claim recovery or duplicate dispatch)",
                        task_id,
                    )
                    return
                leaf_id = row["id"]
                if raw_response is not None:
                    await conn.execute(
                        """
                        INSERT INTO extraction_leaves_raw
                          (extraction_leaf_id, raw_response_jsonb, raw_token_usage)
                        VALUES ($1, $2::jsonb, $3::jsonb)
                        ON CONFLICT (extraction_leaf_id) DO NOTHING
                        """,
                        leaf_id,
                        json.dumps(raw_response),
                        json.dumps(raw_token_usage or {}),
                    )

    async def mark_failed(
        self,
        *,
        task_id: str,
        error_message: str,
    ) -> int:
        """Mark a leaf as 'failed' and increment retried_n.

        Returns the new retried_n value. Caller decides whether retried_n
        has reached the retry budget and the leaf is permanently failed.
        """
        row = await self._pool.fetchrow(
            """
            UPDATE extraction_leaves
            SET status = 'failed',
                error_message = $2,
                retried_n = retried_n + 1,
                updated_at = now()
            WHERE task_id = $1
            RETURNING retried_n
            """,
            task_id,
            error_message[:1000],  # cap message size
        )
        return row["retried_n"] if row else 0

    async def delete_by_chapter(
        self,
        chapter_id: UUID,
        ops: list[str] | None = None,
    ) -> tuple[int, int]:
        """WS-0.1 invalidation: delete the extraction_leaves rows for ONE chapter
        (+ cascade extraction_leaves_raw) and return accurate counts.

        Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.3 (P0-4).

        This is the scope `chapter.scenes_reparsed` uses. Re-parsing chapter 7 only
        moves chapter 7's scene index, so only chapter 7's cached leaves are stale;
        wiping the other 199 chapters' leaves (the old `delete_by_book` behavior)
        forced a full-book LLM re-extract for zero index change.

        `delete_by_book` remains for the genuinely book-wide case (the explicit
        `/invalidate-cache/{book_id}` route).

        Returns (deleted_leaves, deleted_raw). Same two-step CTE as delete_by_book:
        Postgres CASCADE does not report the child count via the parent's RETURNING.
        """
        target_ops = ops if ops else list(_VALID_OPS)
        for op in target_ops:
            if op not in _VALID_OPS:
                raise ValueError(f"unknown op: {op!r}")
        row = await self._pool.fetchrow(
            """
            WITH
              target AS (
                SELECT id FROM extraction_leaves
                WHERE chapter_id = $1 AND op = ANY($2::text[])
              ),
              del_raw AS (
                DELETE FROM extraction_leaves_raw
                WHERE extraction_leaf_id IN (SELECT id FROM target)
                RETURNING 1
              ),
              del_leaves AS (
                DELETE FROM extraction_leaves
                WHERE id IN (SELECT id FROM target)
                RETURNING 1
              )
            SELECT
              (SELECT count(*) FROM del_raw)::int   AS deleted_raw,
              (SELECT count(*) FROM del_leaves)::int AS deleted_leaves
            """,
            chapter_id,
            target_ops,
        )
        return (row["deleted_leaves"], row["deleted_raw"])

    async def delete_by_book(
        self,
        book_id: UUID,
        ops: list[str] | None = None,
    ) -> tuple[int, int]:
        """D5 invalidation: delete all extraction_leaves rows for a book
        (+ cascade extraction_leaves_raw) and return accurate counts.

        Book-WIDE. For the per-chapter re-parse trigger use `delete_by_chapter`
        (WS-0.1) — this one is reserved for the explicit `/invalidate-cache/{book_id}`
        route and the missing-chapter_id fallback.

        H2 fix: explicit two-step CTE in a single Tx — Postgres CASCADE
        delete does NOT return a count via RETURNING from the parent.

        Returns (deleted_leaves, deleted_raw).
        """
        target_ops = ops if ops else list(_VALID_OPS)
        for op in target_ops:
            if op not in _VALID_OPS:
                raise ValueError(f"unknown op: {op!r}")
        row = await self._pool.fetchrow(
            """
            WITH
              target AS (
                SELECT id FROM extraction_leaves
                WHERE book_id = $1 AND op = ANY($2::text[])
              ),
              del_raw AS (
                DELETE FROM extraction_leaves_raw
                WHERE extraction_leaf_id IN (SELECT id FROM target)
                RETURNING 1
              ),
              del_leaves AS (
                DELETE FROM extraction_leaves
                WHERE id IN (SELECT id FROM target)
                RETURNING 1
              )
            SELECT
              (SELECT count(*) FROM del_raw)::int   AS deleted_raw,
              (SELECT count(*) FROM del_leaves)::int AS deleted_leaves
            """,
            book_id,
            target_ops,
        )
        return (row["deleted_leaves"], row["deleted_raw"])

    async def reset_stale_claims(self) -> int:
        """D9: reset status='running' rows older than 30 minutes back to
        'pending' so new claims can pick them up.

        Idempotent across multi-replica startup (L5 fix): the status='running'
        filter ensures concurrent recovery is safe.

        Returns the count of reset rows.
        """
        result = await self._pool.execute(
            """
            UPDATE extraction_leaves
            SET status = 'pending',
                error_message = COALESCE(error_message, '') ||
                                '\n[stale-claim recovery at ' || now()::text || ']',
                updated_at = now()
            WHERE status = 'running'
              AND started_at < now() - INTERVAL '30 minutes'
            """
        )
        # "UPDATE N"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0


def _row_to_leaf(row: asyncpg.Record) -> ExtractionLeaf:
    return ExtractionLeaf(
        id=row["id"],
        book_id=row["book_id"],
        chapter_id=row["chapter_id"],
        scene_id=row["scene_id"],
        leaf_path=row["leaf_path"],
        op=row["op"],
        task_id=row["task_id"],
        status=row["status"],
        candidates_jsonb=(
            json.loads(row["candidates_jsonb"]) if row["candidates_jsonb"] else None
        ),
        retried_n=row["retried_n"],
        error_message=row["error_message"],
        parse_version=row["parse_version"],
        extractor_version=row["extractor_version"],
        model_ref=row["model_ref"],
        glossary_anchor_size=row["glossary_anchor_size"],
    )
