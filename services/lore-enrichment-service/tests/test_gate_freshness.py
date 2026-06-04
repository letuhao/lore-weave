"""Gate FRESHNESS bound (RAID C16, WARN-2 / DEFERRED-055).

``EvalRunsRepo.get_latest`` has NO recency filter, so before this fix a passing
eval run from arbitrarily long ago kept P2/P3 unlocked FOREVER — a stale green
against a since-changed corpus. ``make_eval_runs_gate_reader`` now treats a
PASSING row older than a configurable ``max_age_seconds`` as LOCKED (fail-closed
on staleness): the eval must be re-run against the current corpus to re-unlock.

These drive the production reader against a fake repo (no DB) so the age logic is
deterministic:
  * fresh pass → unlocked;
  * stale pass (older than the bound) → LOCKED;
  * stale FAIL stays locked (age is irrelevant — it was never unlocked);
  * max_age_seconds <= 0 disables the bound (any passing run stays valid).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.db.repositories.eval_runs import EvalRun
from app.strategies.gate_reader import make_eval_runs_gate_reader

# asyncio_mode=auto — async tests run without an explicit marker.

_USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
_PROJECT = "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39"
_SUITE = "enrichment-v1"
_MAX_AGE = 3600.0  # 1 hour for the test


def _run(*, passed: bool, age_seconds: float) -> EvalRun:
    """A minimal persisted eval run with a controllable created_at age."""
    created = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return EvalRun(
        eval_run_id=uuid4(),
        project_id=UUID(_PROJECT),
        user_id=UUID(_USER),
        run_id="r1",
        suite_version=_SUITE,
        baseline_version=_SUITE,
        n_proposals=4,
        schema_score=100.0,
        canon_score=100.0,
        anachronism_score=100.0,
        provenance_score=100.0,
        usefulness_score=90.0,
        composite=96.0,
        fleiss_kappa=0.7,
        judge_ensemble_acceptable=True,
        passed=passed,
        raw_report={},
        created_at=created,
    )


class _FakeRepo:
    """Quacks like EvalRunsRepo.get_latest — returns the supplied row (or None)."""

    def __init__(self, row: EvalRun | None) -> None:
        self._row = row

    async def get_latest(self, *, user_id, project_id, suite_version):
        return self._row


async def test_fresh_pass_unlocks():
    repo = _FakeRepo(_run(passed=True, age_seconds=60.0))  # 1 min old
    read = make_eval_runs_gate_reader(repo, max_age_seconds=_MAX_AGE)
    gate = await read(_USER, _PROJECT, _SUITE)
    assert gate.has_run is True
    assert gate.p2_p3_unlocked is True


async def test_stale_pass_is_locked():
    """A passing run OLDER than the bound is treated as LOCKED (fail-closed)."""
    repo = _FakeRepo(_run(passed=True, age_seconds=_MAX_AGE + 60.0))  # past the bound
    read = make_eval_runs_gate_reader(repo, max_age_seconds=_MAX_AGE)
    gate = await read(_USER, _PROJECT, _SUITE)
    assert gate.has_run is True
    assert gate.p2_p3_unlocked is False  # stale green → LOCKED
    assert gate.passed is False
    # composite carried for the audit trail even when staleness locks it.
    assert gate.composite == 96.0


async def test_stale_fail_stays_locked():
    """A failing run is locked regardless of age — the age check only gates a
    pass (a fail was never unlocked, so freshness is moot)."""
    repo = _FakeRepo(_run(passed=False, age_seconds=_MAX_AGE + 60.0))
    read = make_eval_runs_gate_reader(repo, max_age_seconds=_MAX_AGE)
    gate = await read(_USER, _PROJECT, _SUITE)
    assert gate.p2_p3_unlocked is False


async def test_no_run_is_locked():
    repo = _FakeRepo(None)
    read = make_eval_runs_gate_reader(repo, max_age_seconds=_MAX_AGE)
    gate = await read(_USER, _PROJECT, _SUITE)
    assert gate.has_run is False
    assert gate.p2_p3_unlocked is False


async def test_disabled_bound_keeps_stale_pass_unlocked():
    """max_age_seconds <= 0 disables the freshness bound — an arbitrarily old
    passing run stays unlocked (the prior behavior, opt-in only)."""
    repo = _FakeRepo(_run(passed=True, age_seconds=10 * 365 * 24 * 3600.0))  # 10y
    read = make_eval_runs_gate_reader(repo, max_age_seconds=0.0)
    gate = await read(_USER, _PROJECT, _SUITE)
    assert gate.p2_p3_unlocked is True
