"""C15 — enrichment_eval_runs repository round-trip (real Postgres).

Persist a scorecard → read it back as the latest run → assert the sub-scores,
composite, κ, and the GATE decision (passed) survive the round-trip. Asserts
idempotency: re-persisting the SAME (project, suite_version, run_id) is a no-op
that reloads the existing row (no duplicate baseline row). Skips when no real DB.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.repositories.eval_runs import EvalRunsRepo

pytestmark = pytest.mark.asyncio


async def test_persist_and_read_back_latest(pool):
    repo = EvalRunsRepo(pool)
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    subs = {"schema": 95.0, "canon": 80.0, "anachronism": 100.0,
            "provenance": 100.0, "usefulness": 85.0}
    run = await repo.persist(
        user_id=user_id, project_id=project_id, run_id="run-1",
        suite_version="enrichment-v1", baseline_version="enrichment-v1",
        n_proposals=4, subscores=subs, composite=91.0,
        fleiss_kappa=0.62, judge_ensemble_acceptable=True, passed=True,
        raw_report={"hello": "世界"},
    )
    assert run.passed is True
    assert run.deduped is False
    assert run.usefulness_score == 85.0
    assert run.composite == 91.0
    assert run.fleiss_kappa == 0.62

    latest = await repo.get_latest(
        user_id=user_id, project_id=project_id, suite_version="enrichment-v1"
    )
    assert latest is not None
    assert latest.eval_run_id == run.eval_run_id
    assert latest.schema_score == 95.0
    assert latest.raw_report.get("hello") == "世界"  # CJK survives JSONB round-trip


async def test_persist_idempotent_no_duplicate_baseline(pool):
    repo = EvalRunsRepo(pool)
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    subs = {"schema": 90.0, "canon": 90.0, "anachronism": 90.0,
            "provenance": 90.0, "usefulness": 90.0}
    first = await repo.persist(
        user_id=user_id, project_id=project_id, run_id="baseline",
        suite_version="enrichment-v1", baseline_version=None, n_proposals=4,
        subscores=subs, composite=90.0, fleiss_kappa=0.7,
        judge_ensemble_acceptable=True, passed=True, raw_report={},
    )
    # Re-persist SAME (project, suite, run_id) — must reload, not duplicate.
    second = await repo.persist(
        user_id=user_id, project_id=project_id, run_id="baseline",
        suite_version="enrichment-v1", baseline_version=None, n_proposals=4,
        subscores=subs, composite=90.0, fleiss_kappa=0.7,
        judge_ensemble_acceptable=True, passed=True, raw_report={},
    )
    assert second.deduped is True
    assert second.eval_run_id == first.eval_run_id

    # Exactly one row for the tuple.
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            """SELECT COUNT(*) FROM enrichment_eval_runs
               WHERE project_id = $1 AND suite_version = $2 AND run_id = $3""",
            project_id, "enrichment-v1", "baseline",
        )
    assert n == 1


async def test_get_latest_cross_user_isolation(pool):
    repo = EvalRunsRepo(pool)
    owner = uuid.uuid4()
    other = uuid.uuid4()
    project_id = uuid.uuid4()
    subs = {"schema": 90.0, "canon": 90.0, "anachronism": 90.0,
            "provenance": 90.0, "usefulness": 90.0}
    await repo.persist(
        user_id=owner, project_id=project_id, run_id="r1",
        suite_version="enrichment-v1", baseline_version=None, n_proposals=1,
        subscores=subs, composite=90.0, fleiss_kappa=None,
        judge_ensemble_acceptable=True, passed=True, raw_report={},
    )
    # Another user querying the same project_id gets None (no leak).
    leaked = await repo.get_latest(
        user_id=other, project_id=project_id, suite_version="enrichment-v1"
    )
    assert leaked is None


async def test_get_latest_returns_most_recent(pool):
    repo = EvalRunsRepo(pool)
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    subs = {"schema": 50.0, "canon": 50.0, "anachronism": 50.0,
            "provenance": 50.0, "usefulness": 50.0}
    await repo.persist(
        user_id=user_id, project_id=project_id, run_id="old",
        suite_version="enrichment-v1", baseline_version=None, n_proposals=1,
        subscores=subs, composite=50.0, fleiss_kappa=None,
        judge_ensemble_acceptable=False, passed=False, raw_report={},
    )
    subs2 = {"schema": 95.0, "canon": 95.0, "anachronism": 95.0,
             "provenance": 95.0, "usefulness": 95.0}
    await repo.persist(
        user_id=user_id, project_id=project_id, run_id="new",
        suite_version="enrichment-v1", baseline_version=None, n_proposals=1,
        subscores=subs2, composite=95.0, fleiss_kappa=0.8,
        judge_ensemble_acceptable=True, passed=True, raw_report={},
    )
    latest = await repo.get_latest(
        user_id=user_id, project_id=project_id, suite_version="enrichment-v1"
    )
    assert latest is not None
    assert latest.run_id == "new"
    assert latest.passed is True
