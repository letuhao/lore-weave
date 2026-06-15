"""Unified Job Control Plane P1 — emit_job_event wiring in worker-ai's extraction
terminal transitions (_complete_job / _fail_job).

The shared emit lib + payload shape are SDK-tested; these prove the WIRING fires on the
SAME conn as the status UPDATE, only when the conditional UPDATE actually transitioned a
row (RETURNING row → no duplicate terminal emit on a redelivered/already-terminal job),
maps the DB 'complete' enum to the canonical 'completed', and carries the error on fail.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app import runner


def _status_str(s):
    return getattr(s, "value", s)


def _pool(row):
    """Pool whose acquired conn.fetchrow returns ``row`` (a dict = transition won,
    None = already-terminal/no-row), with acquire()/transaction() async-context."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=row)
    txn = MagicMock()
    txn.__aenter__ = AsyncMock(return_value=None)
    txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn)
    acq = MagicMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acq)
    return pool


@pytest.mark.asyncio
async def test_complete_job_emits_completed(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(runner, "emit_job_event_safe", spy)
    u, j = uuid4(), uuid4()
    await runner._complete_job(_pool({"job_id": str(j)}), u, j)
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "knowledge" and kw["kind"] == "extraction"
    assert _status_str(kw["status"]) == "completed"  # DB 'complete' → canonical
    assert kw["job_id"] == str(j) and kw["owner_user_id"] == str(u)


@pytest.mark.asyncio
async def test_complete_job_no_row_no_emit(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(runner, "emit_job_event_safe", spy)
    await runner._complete_job(_pool(None), uuid4(), uuid4())
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_job_emits_failed_with_error(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(runner, "emit_job_event_safe", spy)
    await runner._fail_job(_pool({"job_id": "x"}), uuid4(), uuid4(), "boom")
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert _status_str(kw["status"]) == "failed"
    assert kw["error"]["message"] == "boom"


@pytest.mark.asyncio
async def test_fail_job_no_row_no_emit(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(runner, "emit_job_event_safe", spy)
    await runner._fail_job(_pool(None), uuid4(), uuid4(), "boom")
    spy.assert_not_awaited()
