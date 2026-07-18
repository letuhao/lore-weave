"""composition_daily_progress repository — LOOM T4.2 writing-progress stats.

Server-SSOT writing progress for a Work. The client reports the ACTIVE chapter's
current TOTAL word count on save, keyed to the user's LOCAL date — a SNAPSHOT, not
a delta. Per-day authored words are DERIVED here by differencing successive
snapshots of a chapter (so the same count reported twice the same day is
idempotent, and multi-device writing on the same chapter converges on the latest
snapshot). This is the PO-chosen snapshot/server-differenced model (2026-06-24).

SECURITY (M5 isolation): every method takes `user_id` first and filters on it —
progress is the user's OWN studio stat (composition_work is per-user), so a
cross-user read returns the empty aggregate, never another user's words.

`report` upserts on the PK (user, project, chapter, date) so a re-save the same
local date overwrites that day's snapshot (last-write-wins).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

import asyncpg


@dataclass
class ProgressAggregate:
    """The differenced read used to build the GET /progress response.

    `day_words` is ascending (snapshot_date, words_authored_that_day) across all
    history on-or-before the anchor date — the FIRST snapshot of each chapter is a
    BASELINE that contributes 0 (so enabling tracking on an existing book does not
    count its pre-existing content as "written today"; only subsequent deltas count).
    `book_total` is the sum of each chapter's latest snapshot on-or-before the anchor.
    """

    day_words: list[tuple[date, int]] = field(default_factory=list)
    book_total: int = 0


class DailyProgressRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def report(
        self,
        user_id: UUID,
        project_id: UUID,
        chapter_id: UUID,
        words: int,
        snapshot_date: date,
    ) -> None:
        """Upsert the chapter's word-count snapshot for one local date. Idempotent
        on the PK — a re-report the same (chapter, date) overwrites the snapshot."""
        query = """
        INSERT INTO composition_daily_progress
          (user_id, project_id, chapter_id, snapshot_date, words)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, project_id, chapter_id, snapshot_date)
        DO UPDATE SET words = EXCLUDED.words, updated_at = now()
        """
        async with self._pool.acquire() as c:
            await c.execute(query, user_id, project_id, chapter_id, snapshot_date, words)

    async def ensure_baseline(
        self, user_id: UUID, project_id: UUID, chapter_id: UUID, words: int,
    ) -> None:
        """Record the chapter's PRE-EXISTING word count the FIRST time it is opened
        after tracking starts — the reference point its first daily snapshot diffs
        against (so pre-existing content isn't counted as written today). Insert-once:
        ON CONFLICT DO NOTHING so re-opening a chapter (now larger) NEVER resets the
        baseline and erases recorded progress."""
        query = """
        INSERT INTO composition_progress_baseline (user_id, project_id, chapter_id, words)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, project_id, chapter_id) DO NOTHING
        """
        async with self._pool.acquire() as c:
            await c.execute(query, user_id, project_id, chapter_id, words)

    async def get_goal(self, user_id: UUID, project_id: UUID) -> int | None:
        """BE-P2 — the caller's OWN daily word goal for this Work (None if unset).
        Per-user: a legitimate viewer only ever sees their own goal, never another
        collaborator's (the tenancy fix for the shared work.settings.daily_goal)."""
        async with self._pool.acquire() as c:
            g = await c.fetchval(
                "SELECT daily_goal FROM composition_progress_goal "
                "WHERE user_id = $1 AND project_id = $2",
                user_id, project_id,
            )
        return int(g) if g is not None and g > 0 else None

    async def set_goal(self, user_id: UUID, project_id: UUID, goal: int) -> None:
        """Upsert the caller's OWN daily goal. `goal <= 0` clears it (deletes the row)
        so 'no goal' is the absence of a row, not a stored 0 the reader must special-case."""
        async with self._pool.acquire() as c:
            if goal <= 0:
                await c.execute(
                    "DELETE FROM composition_progress_goal WHERE user_id = $1 AND project_id = $2",
                    user_id, project_id,
                )
            else:
                await c.execute(
                    "INSERT INTO composition_progress_goal (user_id, project_id, daily_goal) "
                    "VALUES ($1, $2, $3) "
                    "ON CONFLICT (user_id, project_id) "
                    "DO UPDATE SET daily_goal = EXCLUDED.daily_goal, updated_at = now()",
                    user_id, project_id, goal,
                )

    async def read_aggregate(
        self, user_id: UUID, project_id: UUID, on_or_before: date,
    ) -> ProgressAggregate:
        """Compute the per-day authored-word series (snapshot differencing) and the
        current book total, both bounded to snapshots on-or-before `on_or_before`
        (the client's local "today" — so a clock skew can't leak future-dated rows).
        Streak + sparkline windowing are shaped from `day_words` in the router.

        A chapter's FIRST daily snapshot diffs against its baseline (the pre-existing
        count captured on open) via COALESCE(LAG, baseline.words): an existing chapter
        counts only the NEW words; a new chapter (baseline ~0) counts fully. A missing
        baseline falls through to NULL → 0 (safe: never spikes pre-existing content)."""
        day_words_q = """
        WITH s AS (
          SELECT d.snapshot_date, d.words,
                 COALESCE(
                   LAG(d.words) OVER (PARTITION BY d.chapter_id ORDER BY d.snapshot_date),
                   b.words
                 ) AS prev_words
          FROM composition_daily_progress d
          LEFT JOIN composition_progress_baseline b
            ON b.user_id = d.user_id AND b.project_id = d.project_id
               AND b.chapter_id = d.chapter_id
          WHERE d.user_id = $1 AND d.project_id = $2 AND d.snapshot_date <= $3
        )
        SELECT snapshot_date,
               SUM(CASE WHEN prev_words IS NULL THEN 0
                        ELSE GREATEST(words - prev_words, 0) END)::int AS words
        FROM s
        GROUP BY snapshot_date
        ORDER BY snapshot_date
        """
        # book total = each chapter's latest known count: its newest daily snapshot,
        # or its baseline when it has been opened but not yet written this window.
        book_total_q = """
        SELECT
          COALESCE((
            SELECT SUM(words)::int FROM (
              SELECT DISTINCT ON (chapter_id) words
              FROM composition_daily_progress
              WHERE user_id = $1 AND project_id = $2 AND snapshot_date <= $3
              ORDER BY chapter_id, snapshot_date DESC
            ) latest
          ), 0)
          +
          COALESCE((
            SELECT SUM(b.words)::int FROM composition_progress_baseline b
            WHERE b.user_id = $1 AND b.project_id = $2
              AND NOT EXISTS (
                SELECT 1 FROM composition_daily_progress d
                WHERE d.user_id = b.user_id AND d.project_id = b.project_id
                  AND d.chapter_id = b.chapter_id AND d.snapshot_date <= $3
              )
          ), 0)
          AS total
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(day_words_q, user_id, project_id, on_or_before)
            total = await c.fetchval(book_total_q, user_id, project_id, on_or_before)
        return ProgressAggregate(
            day_words=[(r["snapshot_date"], r["words"]) for r in rows],
            book_total=int(total or 0),
        )
