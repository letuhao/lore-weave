"""K17.9 — persist a `BenchmarkReport` to `project_embedding_benchmark_runs`.

Writes one row per (project_id, embedding_model, run_id) tuple.
Re-running the same tuple raises `asyncpg.UniqueViolationError` —
the CLI defaults `run_id` to a timestamp so collisions require the
caller to explicitly re-use an ID, which is almost always a bug.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg

from .run_benchmark import BenchmarkReport

__all__ = ["persist_benchmark_report"]

logger = logging.getLogger(__name__)


async def persist_benchmark_report(
    pool: asyncpg.Pool,
    *,
    project_id: UUID,
    embedding_provider_id: UUID | None,
    embedding_model: str,
    run_id: str,
    report: BenchmarkReport,
) -> UUID:
    """Insert the benchmark row. Returns the new `benchmark_run_id`."""
    # Explicit json.dumps avoids depending on a JSONB codec being
    # registered on the connection — asyncpg routes TEXT-cast JSON to
    # JSONB cleanly with the ::jsonb cast below.
    raw_report_json = json.dumps(report.to_json())
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO project_embedding_benchmark_runs (
              project_id, embedding_provider_id, embedding_model, run_id,
              recall_at_3, mrr, avg_score_positive, stddev,
              negative_control_pass, passed, raw_report
            )
            VALUES (
              $1, $2, $3, $4,
              $5, $6, $7, $8,
              $9, $10, $11::jsonb
            )
            RETURNING benchmark_run_id
            """,
            project_id,
            embedding_provider_id,
            embedding_model,
            run_id,
            report.recall_at_3,
            report.mrr,
            report.avg_score_positive,
            # The `stddev` column stores the strictest of (recall,
            # MRR) — matches how `passes_thresholds` gates on the
            # worse of the two for determinism.
            max(report.stddev_recall, report.stddev_mrr),
            report.negative_control_max_score
                <= report.thresholds["negative_control_max_score"],
            report.passes_thresholds(),
            raw_report_json,
        )
    assert row is not None  # INSERT ... RETURNING always returns a row
    logger.info(
        "K17.9 persist: run_id=%s model=%s passed=%s",
        run_id, embedding_model, report.passes_thresholds(),
    )
    return row["benchmark_run_id"]
