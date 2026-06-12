"""Wave 2a — resume race-guard (D-2B-TRANSL-RESUME-RACE) + the updated_at bump.

The resume() race guard (FOR UPDATE + a provider_job_id precheck) lets the sweeper and
the event consumer drive the SAME terminal concurrently without double-folding /
double-submitting the next batch. Here we lock the two new invariants:

  (1) a resume whose job is no longer the row's in-flight provider_job_id (a concurrent
      resume already folded + advanced it) is a no-op — no submit, no finalize, no write;
      likewise a vanished / already-cleared row.
  (2) _persist_inflight bumps updated_at (the sweeper's idle-detection depends on it).

The fold/finalize happy path is covered by the pure-SM tests + live-smoke.
"""
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.workers import decoupled_block_translate as block
from app.workers import decoupled_translate as text


class _Tx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Conn:
    def __init__(self, fetchrow_result):
        self._fr = fetchrow_result
        self.executed: list = []

    async def fetchrow(self, _sql, *_args):
        return self._fr

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        return _Tx(self)


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


def _job(job_id):
    j = MagicMock()
    j.job_id = job_id
    j.status = "completed"
    return j


@pytest.mark.parametrize("engine", [block, text])
@pytest.mark.asyncio
async def test_resume_skips_when_job_superseded(engine):
    """provider_job_id advanced past this job ⇒ a concurrent resume already handled this
    terminal ⇒ no double submit / finalize / write."""
    conn = _Conn({"resume_state": {"msg": {}}, "provider_job_id": uuid4()})  # advanced
    llm = MagicMock()
    llm.submit_job = AsyncMock()
    fin = AsyncMock()
    await engine.resume(
        pool=_Pool(conn), llm_client=llm, job=_job(uuid4()),
        chapter_translation_id=uuid4(), finalize_cb=fin,
    )
    llm.submit_job.assert_not_awaited()
    fin.assert_not_awaited()
    assert conn.executed == []


@pytest.mark.parametrize("engine", [block, text])
@pytest.mark.asyncio
async def test_resume_skips_when_row_gone_or_cleared(engine):
    """Vanished row or already-NULL resume_state ⇒ no-op (a concurrent finalize won)."""
    for fr in (None, {"resume_state": None, "provider_job_id": uuid4()}):
        conn = _Conn(fr)
        llm = MagicMock()
        llm.submit_job = AsyncMock()
        fin = AsyncMock()
        await engine.resume(
            pool=_Pool(conn), llm_client=llm, job=_job(uuid4()),
            chapter_translation_id=uuid4(), finalize_cb=fin,
        )
        llm.submit_job.assert_not_awaited()
        fin.assert_not_awaited()


@pytest.mark.parametrize("engine", [block, text])
@pytest.mark.asyncio
async def test_persist_inflight_bumps_updated_at(engine):
    ex = AsyncMock()
    await engine._persist_inflight(ex, uuid4(), uuid4(), {"x": 1})
    sql = ex.execute.call_args.args[0]
    assert "updated_at=now()" in sql
    # sanity: still a chapter_translations UPDATE keyed by id
    assert "UPDATE chapter_translations" in sql and "WHERE id=$1" in sql
