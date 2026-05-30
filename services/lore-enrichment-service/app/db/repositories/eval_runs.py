"""EvalRunsRepo — persist + read the ``enrichment_eval_runs`` table (RAID C15).

Mirrors knowledge-service ``benchmark_runs.py`` / ``eval/persist.py`` (load→run→
persist to a runs table): one immutable row per (project, suite_version, run_id)
scorecard. Writes the weighted sub-scores + composite + judge-ensemble κ + the
GATE decision (passed); reads the LATEST run for a (project, suite_version) so
the gate that guards C16/C17 is driven by real persisted data.

Per-user/per-project scoped (Q3): every read filters on ``user_id`` so a
cross-user caller gets None, not a leaked row.

Idempotency: ``UNIQUE(project_id, suite_version, run_id)`` — re-persisting the
SAME run_id is an ``ON CONFLICT DO NOTHING`` no-op that reloads the existing row
(``deduped=True``), so a re-run never duplicates a baseline row. The CLI defaults
run_id to a timestamp, so a genuine re-run gets a fresh row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

__all__ = ["EvalRun", "EvalRunsRepo"]


@dataclass(frozen=True)
class EvalRun:
    eval_run_id: UUID
    project_id: UUID
    user_id: UUID
    run_id: str
    suite_version: str
    baseline_version: str | None
    n_proposals: int
    schema_score: float
    canon_score: float
    anachronism_score: float
    provenance_score: float
    usefulness_score: float
    composite: float
    fleiss_kappa: float | None
    judge_ensemble_acceptable: bool
    passed: bool
    raw_report: dict[str, Any]
    created_at: datetime
    deduped: bool = False


class EvalRunsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def persist(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        run_id: str,
        suite_version: str,
        baseline_version: str | None,
        n_proposals: int,
        subscores: dict[str, float],
        composite: float,
        fleiss_kappa: float | None,
        judge_ensemble_acceptable: bool,
        passed: bool,
        raw_report: dict[str, Any],
    ) -> EvalRun:
        """Insert one eval-run row. Idempotent on (project, suite_version,
        run_id): a duplicate run_id reloads the existing row (deduped=True), so
        a re-run can never duplicate a baseline row."""
        raw_json = json.dumps(raw_report, ensure_ascii=False)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO enrichment_eval_runs (
                  project_id, user_id, run_id, suite_version, baseline_version,
                  n_proposals, schema_score, canon_score, anachronism_score,
                  provenance_score, usefulness_score, composite, fleiss_kappa,
                  judge_ensemble_acceptable, passed, raw_report
                )
                VALUES (
                  $1, $2, $3, $4, $5,
                  $6, $7, $8, $9,
                  $10, $11, $12, $13,
                  $14, $15, $16::jsonb
                )
                ON CONFLICT (project_id, suite_version, run_id) DO NOTHING
                RETURNING *
                """,
                project_id, user_id, run_id, suite_version, baseline_version,
                n_proposals,
                subscores.get("schema", 0.0), subscores.get("canon", 0.0),
                subscores.get("anachronism", 0.0), subscores.get("provenance", 0.0),
                subscores.get("usefulness", 0.0),
                composite, fleiss_kappa,
                judge_ensemble_acceptable, passed, raw_json,
            )
            if row is None:
                # Conflict — reload the existing row (idempotent re-run).
                row = await conn.fetchrow(
                    """SELECT * FROM enrichment_eval_runs
                       WHERE project_id = $1 AND suite_version = $2 AND run_id = $3""",
                    project_id, suite_version, run_id,
                )
                return _row_to_run(row, deduped=True)
        return _row_to_run(row, deduped=False)

    async def get_latest(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        suite_version: str,
    ) -> EvalRun | None:
        """The most recent eval run for a (project, suite_version). Cross-user
        isolation: filters on user_id — a caller handing in another user's
        project_id gets None. This is the read the GATE uses to decide whether
        C16/C17 may activate."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM enrichment_eval_runs
                WHERE project_id = $1 AND user_id = $2 AND suite_version = $3
                ORDER BY created_at DESC, eval_run_id DESC
                LIMIT 1
                """,
                project_id, user_id, suite_version,
            )
        if row is None:
            return None
        return _row_to_run(row, deduped=False)


def _row_to_run(row: asyncpg.Record, *, deduped: bool) -> EvalRun:
    raw = row["raw_report"]
    if isinstance(raw, str):
        raw = json.loads(raw) if raw else {}
    elif raw is None:
        raw = {}
    return EvalRun(
        eval_run_id=row["eval_run_id"],
        project_id=row["project_id"],
        user_id=row["user_id"],
        run_id=row["run_id"],
        suite_version=row["suite_version"],
        baseline_version=row["baseline_version"],
        n_proposals=row["n_proposals"],
        schema_score=float(row["schema_score"]),
        canon_score=float(row["canon_score"]),
        anachronism_score=float(row["anachronism_score"]),
        provenance_score=float(row["provenance_score"]),
        usefulness_score=float(row["usefulness_score"]),
        composite=float(row["composite"]),
        fleiss_kappa=(float(row["fleiss_kappa"]) if row["fleiss_kappa"] is not None else None),
        judge_ensemble_acceptable=row["judge_ensemble_acceptable"],
        passed=row["passed"],
        raw_report=raw,
        created_at=row["created_at"],
        deduped=deduped,
    )
