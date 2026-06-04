"""Materialize an eval baseline row from a saved judge dump (track phase Q1).

Scores a dump with ``loreweave_eval`` and persists it as a ``source='baseline'``
eval_run, so the promotion gate (Q8) and the Dev Log (Q7) have a real
metric-of-record row to diff candidates against. Idempotent (re-runnable — keyed
on ``baseline:<label>``).

Usage (from services/learning-service, with a reachable LEARNING_DB_URL):
    LEARNING_DB_URL=postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_learning \
    python -m scripts.materialize_eval_baseline <dump_root> <owner_user_uuid> [label]

Env (optional, forwarded to loreweave_eval.panel_from_env):
    KNOWLEDGE_EXTRACTOR_MODEL / KNOWLEDGE_FILTER_MODEL  judges to exclude
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

import asyncpg

from loreweave_eval import panel_from_env, score_dump

from app.db.eval_repo import ensure_score_configs
from app.db.eval_sink import DbSink
from app.db.migrate import run_migrations


async def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    dump_root = Path(sys.argv[1]).resolve()
    if not dump_root.is_dir():
        print(f"ERROR: dump not found: {dump_root}", file=sys.stderr)
        return 2
    owner = UUID(sys.argv[2])
    label = sys.argv[3] if len(sys.argv) >= 4 else dump_root.name
    dsn = os.environ.get("LEARNING_DB_URL")
    if not dsn:
        print("ERROR: LEARNING_DB_URL required", file=sys.stderr)
        return 2

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        await run_migrations(pool)          # idempotent — creates the quality tables
        await ensure_score_configs(pool)
        result = score_dump(dump_root, panel_from_env(), variant_label=label)
        sink = DbSink(
            pool,
            user_id=owner,
            source="baseline",
            dataset_version=label,
            idempotency_key=f"baseline:{label}",
        )
        eval_run_id = await sink.write_eval_result(result)
        print(
            f"baseline eval_run {eval_run_id}: "
            f"disjoint_f1={result.disjoint_median_f1} "
            f"ci=[{result.disjoint_ci_low}, {result.disjoint_ci_high}] "
            f"judges={result.n_judges_total} disjoint={result.n_disjoint_judges}"
        )
        row = await pool.fetchrow(
            "SELECT source, disjoint_median_f1, full_panel_median_f1, n_disjoint_judges "
            "FROM eval_runs WHERE eval_run_id = $1",
            eval_run_id,
        )
        print("readback:", dict(row))
        n_scores = await pool.fetchval(
            "SELECT count(*) FROM quality_scores WHERE source_eval_run_id = $1",
            eval_run_id,
        )
        n_results = await pool.fetchval(
            "SELECT count(*) FROM eval_results WHERE eval_run_id = $1",
            eval_run_id,
        )
        print(f"children: eval_results={n_results} quality_scores={n_scores}")
    finally:
        await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
