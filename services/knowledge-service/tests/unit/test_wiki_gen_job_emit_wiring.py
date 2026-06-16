"""Unified Job Control Plane (D-JOBS-WIKI-GEN-UNWIRED) — emit_job_event wiring on
WikiGenJobsRepo.

The shared emit lib + payload shape are SDK-tested; these prove the WIRING fires on
each wiki-gen status chokepoint (create → pending, mark_running → running, complete →
completed, fail → failed, pause → paused, resume → pending, cancel → cancelled) on the
SAME conn/tx as the write, maps the wiki 'complete' enum to canonical 'completed',
carries the error on 'failed', and does NOT fire when a status-guarded UPDATE matched
no row (a cancelled/terminal job can't emit a duplicate / spurious running).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.repositories import wiki_gen_jobs as wj
from app.db.repositories.wiki_gen_jobs import WikiGenJobsRepo


def _status(s):
    return getattr(s, "value", s)


class _Conn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, query, *params):
        return self._row

    def transaction(self):
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
    # create() calls _row_to_job(row); the row→model mapping is covered elsewhere, so
    # stub it to avoid faking every column.
    monkeypatch.setattr(
        wj, "_row_to_job",
        lambda r: SimpleNamespace(job_id=r.get("job_id"), status=r.get("status", "pending")),
    )


@pytest.fixture
def _spy(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(wj, "emit_job_event", spy)
    return spy


@pytest.mark.asyncio
async def test_create_emits_pending(_spy):
    repo = WikiGenJobsRepo(_Pool({"job_id": "x"}))
    u, p, b = uuid4(), uuid4(), uuid4()
    await repo.create(user_id=u, project_id=p, book_id=b, model_source="user_model",
                      model_ref="m1", entity_ids=["e1"], max_spend_usd=None, items_total=1)
    _spy.assert_awaited_once()
    kw = _spy.await_args.kwargs
    assert kw["service"] == "knowledge" and kw["kind"] == "wiki_gen"
    assert _status(kw["status"]) == "pending" and kw["owner_user_id"] == str(u)


@pytest.mark.asyncio
async def test_mark_running_emits_running(_spy):
    u = uuid4()
    repo = WikiGenJobsRepo(_Pool({"user_id": u}))
    j = uuid4()
    ok = await repo.mark_running(j, items_total=3)
    assert ok is True
    kw = _spy.await_args.kwargs
    assert _status(kw["status"]) == "running"
    assert kw["job_id"] == str(j) and kw["owner_user_id"] == str(u)


@pytest.mark.asyncio
async def test_mark_running_no_row_no_emit(_spy):
    # the claim matched nothing (cancelled/terminal between pull and claim) → no emit
    repo = WikiGenJobsRepo(_Pool(None))
    ok = await repo.mark_running(uuid4(), items_total=3)
    assert ok is False
    _spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_maps_to_canonical(_spy):
    repo = WikiGenJobsRepo(_Pool({"user_id": uuid4(), "cost_spent_usd": 2.5}))
    await repo.complete(uuid4())
    kw = _spy.await_args.kwargs
    assert _status(kw["status"]) == "completed"  # 'complete' → 'completed'
    assert kw["cost_usd"] == 2.5  # cumulative cost carried on the terminal emit


@pytest.mark.asyncio
async def test_fail_carries_error(_spy):
    repo = WikiGenJobsRepo(_Pool({"user_id": uuid4(), "cost_spent_usd": 0}))
    await repo.fail(uuid4(), error="budget exceeded")
    kw = _spy.await_args.kwargs
    assert _status(kw["status"]) == "failed"
    assert kw["error"]["message"] == "budget exceeded"


@pytest.mark.asyncio
async def test_pause_emits_paused(_spy):
    repo = WikiGenJobsRepo(_Pool({"user_id": uuid4(), "cost_spent_usd": 0}))
    await repo.pause(uuid4(), reason="user")
    assert _status(_spy.await_args.kwargs["status"]) == "paused"


@pytest.mark.asyncio
async def test_resume_emits_pending_when_flipped(_spy):
    repo = WikiGenJobsRepo(_Pool({"user_id": uuid4(), "cost_spent_usd": 0}))
    ok = await repo.resume(uuid4())
    assert ok is True
    assert _status(_spy.await_args.kwargs["status"]) == "pending"


@pytest.mark.asyncio
async def test_resume_no_row_no_emit(_spy):
    # not paused (concurrent cancel/complete) → guarded UPDATE matched nothing
    repo = WikiGenJobsRepo(_Pool(None))
    ok = await repo.resume(uuid4())
    assert ok is False
    _spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_emits_cancelled_when_flipped(_spy):
    repo = WikiGenJobsRepo(_Pool({"user_id": uuid4(), "cost_spent_usd": 0}))
    ok = await repo.cancel(uuid4())
    assert ok is True
    assert _status(_spy.await_args.kwargs["status"]) == "cancelled"


@pytest.mark.asyncio
async def test_cancel_no_row_no_emit(_spy):
    # running/terminal job (not pending|paused) → guarded UPDATE matched nothing
    repo = WikiGenJobsRepo(_Pool(None))
    ok = await repo.cancel(uuid4())
    assert ok is False
    _spy.assert_not_awaited()
