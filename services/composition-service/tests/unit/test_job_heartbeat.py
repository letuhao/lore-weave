"""A running worker job keeps `updated_at` fresh, so the sweeper does not start it twice.

`sweep_once` re-drives any active job whose `updated_at` is older than 900s, and `run_job` does
not skip a `running` row. A plan-forge job that regenerates (up to three 12k-token attempts per
step) can legitimately run past that — and was then started a SECOND time while the first was
still going (plan 2026-09-18, T3).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.worker import job_consumer


class _Repo:
    def __init__(self, pool) -> None:
        self.touched: list = []
        self.statuses: list[str] = []
        _Repo.last = self

    async def get(self, job_id):
        return SimpleNamespace(id=job_id, status="running", operation="plan_forge_propose",
                               input={}, created_by=uuid4())

    async def update_status(self, job_id, status, **kw):
        self.statuses.append(status)

    async def touch_running(self, job_id):
        self.touched.append(job_id)


async def _noop(*a, **k):
    return None


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(job_consumer, "_monotonic", lambda: now["t"])
    monkeypatch.setattr(job_consumer, "GenerationJobsRepo", _Repo)
    monkeypatch.setattr(job_consumer, "_finalize_plan_forge_job", _noop)
    monkeypatch.setattr(job_consumer, "_finalize_plan_pass_job", _noop)
    return now


@pytest.mark.asyncio
async def test_a_LONG_wait_touches_updated_at_well_inside_the_sweep_window(clock):
    """Simulate 20 minutes of LLM waiting, polled every 5s: the job must beat, repeatedly."""

    async def op(pool, llm, job, *, cancel_check):
        for _ in range(240):          # 240 polls x 5s = 1200s > the 900s sweep timeout
            clock["t"] += 5
            assert await cancel_check() is False
        return {"ok": True}

    job_consumer._run_operation, orig = op, job_consumer._run_operation  # type: ignore[assignment]
    try:
        out = await job_consumer.run_job(None, None, job_id=str(uuid4()), user_id="u")
    finally:
        job_consumer._run_operation = orig  # type: ignore[assignment]
    assert out == "completed"
    beats = len(_Repo.last.touched)
    assert beats >= 1200 // 900 + 1, f"only {beats} heartbeat(s) in 1200s — the sweeper would re-drive"
    # rate-limited: a 5s poll loop must not become a write per poll
    assert beats <= 1200 // int(job_consumer._HEARTBEAT_SECS) + 1, beats
    assert job_consumer._HEARTBEAT_SECS < 900 / 3


@pytest.mark.asyncio
async def test_a_failing_heartbeat_never_fails_the_job(clock):
    class _Flaky(_Repo):
        async def touch_running(self, job_id):
            raise RuntimeError("db blip")

    job_consumer.GenerationJobsRepo = _Flaky  # type: ignore[misc]

    async def op(pool, llm, job, *, cancel_check):
        clock["t"] += 3600
        assert await cancel_check() is False
        return {"ok": True}

    job_consumer._run_operation, orig = op, job_consumer._run_operation  # type: ignore[assignment]
    try:
        out = await job_consumer.run_job(None, None, job_id=str(uuid4()), user_id="u")
    finally:
        job_consumer._run_operation = orig  # type: ignore[assignment]
    assert out == "completed"


def test_the_heartbeat_only_touches_a_RUNNING_row():
    """A beat must never revive a job that finished or was cancelled meanwhile."""
    import inspect

    from app.db.repositories.generation_jobs import GenerationJobsRepo

    src = inspect.getsource(GenerationJobsRepo.touch_running)
    assert "status = 'running'" in src and "updated_at = now()" in src
