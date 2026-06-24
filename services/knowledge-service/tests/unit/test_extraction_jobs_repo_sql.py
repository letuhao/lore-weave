"""KN-7 — no-DB coverage of ExtractionJobsRepo.set_concurrency_level's SQL.

The PATCH /concurrency router tests (test_extraction_concurrency_patch.py) use
an AsyncMock repo, so the in-flight active-jobs guard
(``WHERE … status IN ('running','paused')``) is never exercised at the SQL
level — a refactor dropping that predicate would still pass the router suite.
This drives the REAL repo against a recording connection and asserts the exact
query string + param order/shape, locking the status filter into the always-run
unit suite.

The cap-raise race itself was REFUTED — the status filter lives inside the
single UPDATE … WHERE, so the gate is atomic — but a 0-row result (the job went
terminal between read and write) maps to the not-updated path the router turns
into 409, so we also assert the None-on-no-rows mapping.
"""
from uuid import uuid4

import pytest

from app.db.repositories.extraction_jobs import ExtractionJobsRepo


class _RecordingConn:
    def __init__(self) -> None:
        self.query: str | None = None
        self.params: tuple = ()

    async def fetchrow(self, query, *params):
        self.query = query
        self.params = params
        return None  # no row — exercise the terminal/0-row mapping


class _RecordingPool:
    def __init__(self) -> None:
        self.conn = _RecordingConn()

    def acquire(self):
        conn = self.conn

        class _Cm:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Cm()


def _norm(q: str) -> str:
    return " ".join(q.split())


@pytest.mark.asyncio
async def test_set_concurrency_emits_active_status_filter_and_param_order():
    pool = _RecordingPool()
    repo = ExtractionJobsRepo(pool)
    user, job = uuid4(), uuid4()

    await repo.set_concurrency_level(user, job, 16)

    q = _norm(pool.conn.query)
    # The active-jobs guard — the predicate the router suite's AsyncMock
    # never exercised. A refactor dropping it would let a terminal job's
    # cap be bumped (and never surface the 409).
    assert "status IN ('running', 'paused')" in q
    # Owner + job scoping is unconditional.
    assert "WHERE user_id = $1 AND job_id = $2" in q
    # SET writes concurrency_level = $3 (the new cap) + updated_at.
    assert "SET concurrency_level = $3" in q
    assert "updated_at = now()" in q
    # Param order/shape: (user_id, job_id, concurrency_level).
    assert pool.conn.params == (user, job, 16)


@pytest.mark.asyncio
async def test_set_concurrency_zero_rows_maps_to_none():
    """A 0-row UPDATE (the job went terminal — status no longer in the
    active set) returns None, which the router disambiguates into the
    409 conflict path via a follow-up get()."""
    pool = _RecordingPool()
    repo = ExtractionJobsRepo(pool)

    result = await repo.set_concurrency_level(uuid4(), uuid4(), 8)

    assert result is None
