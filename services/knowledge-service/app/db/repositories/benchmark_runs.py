"""T2-close-1b — BenchmarkRunsRepo: read access to
`project_embedding_benchmark_runs` (Cycle 9 table).

Writes happen from the K17.9 harness (`eval/persist.py`). This
repository only reads, and it reads with user-scoped isolation:
every query JOINs `knowledge_projects` on `user_id` so a caller
handing in another user's `project_id` gets None, not a leaked
row. Same existence-leak rule as `ProjectsRepo.get`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

__all__ = ["BenchmarkRun", "BenchmarkRunsRepo"]


@dataclass(frozen=True)
class BenchmarkRun:
    benchmark_run_id: UUID
    project_id: UUID
    embedding_provider_id: UUID | None
    embedding_model: str
    run_id: str
    recall_at_3: float | None
    mrr: float | None
    avg_score_positive: float | None
    stddev: float | None
    negative_control_pass: bool | None
    passed: bool
    raw_report: dict[str, Any]
    created_at: datetime


class BenchmarkRunsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_latest(
        self,
        user_id: UUID,
        project_id: UUID,
        embedding_model: str | None = None,
    ) -> BenchmarkRun | None:
        """Return the most recent benchmark run for the project.

        When `embedding_model` is set, filters to only runs against
        that specific model — this is the shape the extraction-start
        gate uses, since enabling extraction with model X doesn't
        care whether model Y was benchmarked. When None, returns the
        most recent run across any model (useful for a 'has the user
        ever run a benchmark?' check).

        Cross-user isolation: JOINs `knowledge_projects` on
        `user_id`. A caller who hands in another user's project_id
        gets None back — same rule as `ProjectsRepo.get`, same
        no-existence-leak guarantee.

        Uses the covering index `idx_benchmark_runs_project_latest
        (project_id, embedding_model, created_at DESC)` so both
        query shapes hit an index scan with a LIMIT 1.
        """
        async with self._pool.acquire() as conn:
            if embedding_model is None:
                row = await conn.fetchrow(
                    """
                    SELECT b.*
                    FROM project_embedding_benchmark_runs b
                    JOIN knowledge_projects p USING (project_id)
                    WHERE b.project_id = $1 AND p.user_id = $2
                    ORDER BY b.created_at DESC
                    LIMIT 1
                    """,
                    project_id, user_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT b.*
                    FROM project_embedding_benchmark_runs b
                    JOIN knowledge_projects p USING (project_id)
                    WHERE b.project_id = $1
                      AND p.user_id = $2
                      AND b.embedding_model = $3
                    ORDER BY b.created_at DESC
                    LIMIT 1
                    """,
                    project_id, user_id, embedding_model,
                )
        if row is None:
            return None
        return _row_to_run(row)

    async def get_latest_for_model(
        self,
        user_id: UUID,
        embedding_model: str,
    ) -> BenchmarkRun | None:
        """Most recent benchmark run for ``(user, embedding_model)`` across ANY
        of the user's projects — the MODEL-scoped gate lookup
        (D-JOURNEY-KG-BENCHMARK-UX R1). The benchmark answers "is this *model*
        good enough?", which is a per-model property, so a passing run on the
        user's hidden benchmark *sandbox* unlocks every project using the same
        model. Drops the ``b.project_id`` filter of :meth:`get_latest`; keeps the
        ``knowledge_projects`` JOIN on ``user_id`` for cross-user isolation.

        Back-compat: an existing per-project passing run still satisfies this
        (same table, looser filter), so already-built projects keep working.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.*
                FROM project_embedding_benchmark_runs b
                JOIN knowledge_projects p USING (project_id)
                WHERE p.user_id = $1
                  AND b.embedding_model = $2
                ORDER BY b.created_at DESC
                LIMIT 1
                """,
                user_id, embedding_model,
            )
        if row is None:
            return None
        return _row_to_run(row)


def _row_to_run(row: asyncpg.Record) -> BenchmarkRun:
    raw = row["raw_report"]
    if isinstance(raw, str):
        raw = json.loads(raw) if raw else {}
    elif raw is None:
        raw = {}
    return BenchmarkRun(
        benchmark_run_id=row["benchmark_run_id"],
        project_id=row["project_id"],
        embedding_provider_id=row["embedding_provider_id"],
        embedding_model=row["embedding_model"],
        run_id=row["run_id"],
        recall_at_3=row["recall_at_3"],
        mrr=row["mrr"],
        avg_score_positive=row["avg_score_positive"],
        stddev=row["stddev"],
        negative_control_pass=row["negative_control_pass"],
        passed=row["passed"],
        raw_report=raw,
        created_at=row["created_at"],
    )
