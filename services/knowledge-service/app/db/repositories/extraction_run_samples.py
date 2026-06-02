"""Q4b-feed — repository for `extraction_run_samples`.

The run-attributable feed for the online LLM judge. worker-ai writes one row
per SUCCEEDED chapter run (opted-in projects only — `save_raw_extraction`);
learning-service's eval-runner reads by `run_id` to feed `run_online_judge`.

Plan: docs/plans/2026-06-01-q4b-feed-extraction-run-samples.md §3.

TRANSIENT buffer: `prune_older_than` runs on knowledge-service startup so novel
text doesn't accumulate beyond the judging window (default 7 days).
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
class ExtractionRunSample:
    run_id: UUID
    user_id: UUID
    project_id: UUID | None
    book_id: UUID | None
    config_hash: str | None
    items: dict[str, Any]  # {entity:[...], relation:[...], event:[...]}
    source_text: str


class ExtractionRunSamplesRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def insert_sample(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
        project_id: UUID | None,
        book_id: UUID | None,
        config_hash: str | None,
        items: dict[str, Any],
        source_text: str,
    ) -> bool:
        """Insert one run sample. Idempotent on `run_id` (fresh per chapter, so
        a conflict only happens on a re-emit race — first write wins).

        Returns True if a row was inserted, False on conflict.
        """
        result = await self._pool.execute(
            """
            INSERT INTO extraction_run_samples
              (run_id, user_id, project_id, book_id, config_hash,
               items_jsonb, source_text)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            ON CONFLICT (run_id) DO NOTHING
            """,
            run_id, user_id, project_id, book_id, config_hash,
            json.dumps(items), source_text,
        )
        return result.endswith(" 1")

    async def fetch_sample(self, run_id: UUID) -> ExtractionRunSample | None:
        """Return the sample for `run_id`, or None if absent (non-opted run,
        pruned, or never sampled)."""
        row = await self._pool.fetchrow(
            """
            SELECT run_id, user_id, project_id, book_id, config_hash,
                   items_jsonb, source_text
            FROM extraction_run_samples
            WHERE run_id = $1
            """,
            run_id,
        )
        if row is None:
            return None
        items = row["items_jsonb"]
        if isinstance(items, str):
            items = json.loads(items)
        return ExtractionRunSample(
            run_id=row["run_id"],
            user_id=row["user_id"],
            project_id=row["project_id"],
            book_id=row["book_id"],
            config_hash=row["config_hash"],
            items=items or {},
            source_text=row["source_text"],
        )

    async def prune_older_than(self, days: int) -> int:
        """Delete samples older than `days`. Returns the count deleted.

        Called on startup — the sample is a transient judging buffer; rows
        older than the judging window are dead weight (novel text at rest)."""
        result = await self._pool.execute(
            """
            DELETE FROM extraction_run_samples
            WHERE created_at < now() - make_interval(days => $1)
            """,
            days,
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0


__all__ = ["ExtractionRunSamplesRepo", "ExtractionRunSample"]
