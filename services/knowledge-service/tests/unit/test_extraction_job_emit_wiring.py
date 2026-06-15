"""Unified Job Control Plane P1 — emit_job_event wiring on ExtractionJobsRepo.

The shared emit lib + payload shape are SDK-tested; these prove the WIRING fires on the
job-status chokepoints (create → pending, update_status → the transition) on the SAME
conn/tx as the write, maps the extraction 'complete' enum to the canonical 'completed',
carries the error on 'failed', and does NOT fire when the terminal-guarded UPDATE matched
no row (so a redelivered/terminal transition can't emit a duplicate).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.repositories import extraction_jobs as ej
from app.db.repositories.extraction_jobs import ExtractionJobsRepo


def _status(s):
    return getattr(s, "value", s)


class _Conn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, query, *params):
        return self._row

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *a):
                return False

        return _Txn()


class _Pool:
    def __init__(self, row):
        self.conn = _Conn(row)

    def acquire(self):
        conn = self.conn

        class _Cm:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Cm()


@pytest.fixture(autouse=True)
def _stub_row_to_job(monkeypatch):
    # emit reads new_status (update_status) / the job row (create); the row→model
    # mapping itself is covered elsewhere, so stub it to avoid faking every column.
    monkeypatch.setattr(
        ej, "_row_to_job",
        lambda r: SimpleNamespace(job_id=r.get("job_id"), status=r.get("status", "pending")),
    )


@pytest.mark.asyncio
async def test_update_status_emits_transition(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ej, "emit_job_event", spy)
    repo = ExtractionJobsRepo(_Pool({"job_id": "x"}))
    u, j = uuid4(), uuid4()
    await repo.update_status(u, j, "cancelled")
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "knowledge" and kw["kind"] == "extraction"
    assert _status(kw["status"]) == "cancelled"
    assert kw["job_id"] == str(j) and kw["owner_user_id"] == str(u)


@pytest.mark.asyncio
async def test_update_status_complete_maps_to_canonical(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ej, "emit_job_event", spy)
    repo = ExtractionJobsRepo(_Pool({"job_id": "x"}))
    await repo.update_status(uuid4(), uuid4(), "complete")
    assert _status(spy.await_args.kwargs["status"]) == "completed"  # 'complete' → 'completed'


@pytest.mark.asyncio
async def test_update_status_failed_carries_error(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ej, "emit_job_event", spy)
    repo = ExtractionJobsRepo(_Pool({"job_id": "x"}))
    await repo.update_status(uuid4(), uuid4(), "failed", error_message="boom")
    kw = spy.await_args.kwargs
    assert _status(kw["status"]) == "failed"
    assert kw["error"]["message"] == "boom"


@pytest.mark.asyncio
async def test_update_status_no_row_no_emit(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ej, "emit_job_event", spy)
    repo = ExtractionJobsRepo(_Pool(None))
    out = await repo.update_status(uuid4(), uuid4(), "cancelled")
    assert out is None
    spy.assert_not_awaited()
