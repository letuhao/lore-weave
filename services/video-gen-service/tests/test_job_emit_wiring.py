"""Unified Job Control Plane P1 — emit_job_event wiring on VideoGenJobsRepo.

The shared emit lib + JobEvent payload shape are SDK-tested centrally; these prove the
WIRING fires at video-gen's job-status chokepoints (create + CAS complete + CAS fail) on
the SAME conn the write uses (so the event commits atomically with the status change — H1),
maps the right fields, and does NOT fire when the CAS lost (no row matched) — so a
redelivered/duplicate terminal never re-emits (money/billing-adjacent).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db import repository as repo_mod
from app.db.repository import VideoGenJobsRepo

USER = uuid4()
JOB = uuid4()
PJID = uuid4()


def _record(**over):
    """A dict that quacks like an asyncpg.Record for the columns we read."""
    base = dict(
        id=JOB, user_id=USER, provider_job_id=PJID, status="pending",
        request_json={}, video_url=None, size_bytes=None, content_type=None,
        error_json=None, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return base


class _FakeConn:
    """Stand-in asyncpg conn: fetchrow returns a scripted row (or None for a
    lost CAS); `transaction()` is a no-op async context manager."""

    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Tx()


class _FakePool:
    """Stand-in asyncpg pool: `acquire()` yields the scripted conn."""

    def __init__(self, row):
        self._conn = _FakeConn(row)

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acq()


@pytest.mark.asyncio
async def test_create_emits_pending(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo_mod, "emit_job_event", spy)
    repo = VideoGenJobsRepo(_FakePool(_record(status="pending")))
    job = await repo.create(user_id=USER, provider_job_id=PJID, request_json={"prompt": "x"})
    assert job.id == JOB
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "video_gen"
    assert kw["kind"] == "video_gen"
    assert kw["status"] == "pending"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_complete_emits_completed_on_cas_won(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo_mod, "emit_job_event", spy)
    repo = VideoGenJobsRepo(_FakePool(_record(status="completed")))
    won = await repo.complete(JOB, video_url="http://minio/v.mp4", size_bytes=2048, content_type="video/mp4")
    assert won is True
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "video_gen"
    assert kw["status"] == "completed"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_complete_no_emit_on_cas_lost(monkeypatch):
    """A redelivered/duplicate completion that loses the CAS (no row) must NOT
    emit a duplicate terminal event."""
    spy = AsyncMock()
    monkeypatch.setattr(repo_mod, "emit_job_event", spy)
    repo = VideoGenJobsRepo(_FakePool(None))  # CAS lost → UPDATE RETURNING empty
    won = await repo.complete(JOB, video_url="http://minio/v.mp4", size_bytes=2048, content_type="video/mp4")
    assert won is False
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_emits_with_error_on_cas_won(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo_mod, "emit_job_event", spy)
    repo = VideoGenJobsRepo(_FakePool(_record(status="failed")))
    won = await repo.fail(JOB, status="failed", error={"code": "upstream_error", "message": "boom"})
    assert won is True
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["status"] == "failed"
    assert kw["error"] == {"code": "upstream_error", "message": "boom"}


@pytest.mark.asyncio
async def test_fail_cancelled_emits_status(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo_mod, "emit_job_event", spy)
    repo = VideoGenJobsRepo(_FakePool(_record(status="cancelled")))
    won = await repo.fail(JOB, status="cancelled", error=None)
    assert won is True
    kw = spy.await_args.kwargs
    assert kw["status"] == "cancelled"
    assert kw["error"] is None


@pytest.mark.asyncio
async def test_fail_no_emit_on_cas_lost(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo_mod, "emit_job_event", spy)
    repo = VideoGenJobsRepo(_FakePool(None))  # CAS lost
    won = await repo.fail(JOB, status="failed", error={"code": "x", "message": "y"})
    assert won is False
    spy.assert_not_awaited()
