"""Phase 2b — D-2B-SHELL-UNIT-TESTS: async-shell coverage for the decoupled BLOCK
translate engine (`decoupled_block_translate.resume`).

The pure state machine is locked by `test_decoupled_block_translate.py`; the
resume-race / no-op guards by `test_decoupled_resume_race.py`; the per-batch
observability row by both. What remained live-smoke-only — and is covered here — is
the resume() SHELL itself driving real folds:

  1. failure-fold: a non-`completed` terminal job folds the in-flight batch as an
     empty/failed last-attempt (best-effort), writes a FAILED chunk row, and
     finalizes whatever partial output exists (no crash, no submit).
  2. failure-fold → total-failure guard: when the failed batch leaves 0/N blocks
     translated, finalize FAILs the chapter (clears resume_state) instead of
     persisting all-original as "completed".
  3. end-to-end correction-retry: a `completed` job whose output is INVALID with
     attempts left re-submits the SAME batch (batch_idx does NOT advance → no chunk
     row, no finalize) with a correction hint.

Shell-level fakes (a FOR UPDATE connection + a pool) mirror
`test_decoupled_resume_race.py` so resume()'s lock/precheck path is exercised
exactly as in production.
"""
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.workers import decoupled_block_translate as block


# ── shell fakes (mirror test_decoupled_resume_race.py) ────────────────────────

class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Conn:
    """FOR UPDATE connection: returns one resume_state row, records executes +
    the chunk-row insert (fetchrow RETURNING id for _insert_chunk_row)."""

    def __init__(self, resume_state, provider_job_id):
        self._row = {"resume_state": resume_state, "provider_job_id": provider_job_id}
        self._chunk_row_id = uuid4()
        self.executed: list = []
        self.fetchrow_calls = 0

    async def fetchrow(self, sql, *args):
        self.fetchrow_calls += 1
        # First fetchrow is the resume_state SELECT ... FOR UPDATE.
        if "FOR UPDATE" in sql:
            return self._row
        # Subsequent fetchrow is _insert_chunk_row's INSERT ... RETURNING id.
        return {"id": self._chunk_row_id}

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        return _Tx()


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        return False


class _Pool:
    """Pool exposing acquire() (the resume tx) + execute() (used by the
    outside-lock _clear_resume_state / _fail)."""

    def __init__(self, conn):
        self._conn = conn
        self.executed: list = []

    def acquire(self):
        return _Acquire(self._conn)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def _job(job_id, *, status, content=None, in_tok=0, out_tok=0):
    j = MagicMock()
    j.job_id = job_id
    j.status = status
    if content is None:
        j.result = None
    else:
        j.result = {
            "messages": [{"role": "assistant", "content": content}],
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
        }
    return j


def _two_batch_rs(provider_job_id):
    """resume_state for a 2-batch chapter where batch 0 already translated and
    batch 1 is the in-flight batch (batch_idx=1)."""
    batches = [
        {"block_indices": [i], "combined": f"[BLOCK {i}]\nsrc{i}",
         "input_texts": {str(i): f"src{i}"}, "token_estimate": 10}
        for i in range(2)
    ]
    return {
        "mode": "block",
        "blocks": [{"type": "paragraph", "content": [{"type": "text", "text": f"src{i}"}]}
                   for i in range(2)],
        "batches": batches,
        "glossary_prompt_block": "", "glossary_correction_map": {},
        "source_lang": "zh", "target_code": "vi",
        "translatable_count": 2, "max_retries": 2, "extra_system": "",
        "batch_idx": 1, "attempt": 0, "correction_hint": "", "rolling_summary": "s0",
        "translated_texts": {"0": "t0"}, "failed_blocks": [],
        "total_input": 5, "total_output": 5,
        "awaiting": "translate_batch",
        "msg": {"user_id": str(uuid4()), "job_id": str(uuid4()),
                "chapter_id": str(uuid4()), "model_source": "byok",
                "model_ref": str(uuid4()), "target_language": "vi"},
        "context_window": 8192, "chapter_text": "src0\nsrc1",
    }


def _one_batch_rs(provider_job_id, *, max_retries=2):
    batches = [{"block_indices": [0], "combined": "[BLOCK 0]\nsrc0",
                "input_texts": {"0": "src0"}, "token_estimate": 10}]
    return {
        "mode": "block",
        "blocks": [{"type": "paragraph", "content": [{"type": "text", "text": "src0"}]}],
        "batches": batches,
        "glossary_prompt_block": "", "glossary_correction_map": {},
        "source_lang": "zh", "target_code": "vi",
        "translatable_count": 1, "max_retries": max_retries, "extra_system": "",
        "batch_idx": 0, "attempt": 0, "correction_hint": "", "rolling_summary": "",
        "translated_texts": {}, "failed_blocks": [],
        "total_input": 0, "total_output": 0,
        "awaiting": "translate_batch",
        "msg": {"user_id": str(uuid4()), "job_id": str(uuid4()),
                "chapter_id": str(uuid4()), "model_source": "byok",
                "model_ref": str(uuid4()), "target_language": "vi"},
        "context_window": 8192, "chapter_text": "src0",
    }


# ── 1. failure-fold → finalize partial ────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_failure_fold_finalizes_partial():
    """A non-`completed` terminal for the in-flight batch folds it as an empty
    last-attempt (best-effort), writes a FAILED chunk row, and finalizes the
    partial output (batch 0 survived) — no crash, no new submit."""
    pjid = uuid4()
    rs = _two_batch_rs(pjid)
    conn = _Conn(rs, pjid)
    pool = _Pool(conn)
    llm = MagicMock()
    llm.submit_job = AsyncMock()
    fin = AsyncMock()

    await block.resume(
        pool=pool, llm_client=llm, job=_job(pjid, status="failed"),
        chapter_translation_id=uuid4(), finalize_cb=fin,
    )

    # Folded empty → no retry submit.
    llm.submit_job.assert_not_awaited()
    # The failed batch RESOLVED (batch_idx advanced) → a FAILED chunk row was written.
    upd = [sql for sql, _ in conn.executed if "validation_errors" in sql]
    assert upd, "expected a chunk-row quality UPDATE for the resolved failed batch"
    # Finalized the partial (batch 0 translated) and cleared resume_state.
    fin.assert_awaited_once()
    body_json = fin.await_args.args[0]
    assert "t0" in body_json  # batch 0's translation survived into the body
    assert any("resume_state=NULL" in sql for sql, _ in pool.executed)


# ── 2. failure-fold → total-failure FAIL ──────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_failure_fold_total_failure_fails_chapter():
    """A failed single-batch chapter leaves 0/1 blocks translated → the total-failure
    guard FAILs the chapter (no finalize, resume_state cleared)."""
    pjid = uuid4()
    rs = _one_batch_rs(pjid)
    conn = _Conn(rs, pjid)
    pool = _Pool(conn)
    llm = MagicMock()
    llm.submit_job = AsyncMock()
    fin = AsyncMock()

    await block.resume(
        pool=pool, llm_client=llm, job=_job(pjid, status="failed"),
        chapter_translation_id=uuid4(), finalize_cb=fin,
    )

    llm.submit_job.assert_not_awaited()
    fin.assert_not_awaited()  # total-failure path FAILs instead of finalizing
    # _fail wrote status='failed' and _clear_resume_state nulled the state.
    assert any("status='failed'" in sql for sql, _ in pool.executed)
    assert any("resume_state=NULL" in sql for sql, _ in pool.executed)


# ── 3. end-to-end correction-retry in the shell ───────────────────────────────

@pytest.mark.asyncio
async def test_resume_invalid_with_attempts_left_resubmits_same_batch():
    """A `completed` job whose output is INVALID (no parseable block) with attempts
    left re-submits the SAME batch (batch_idx unchanged → NO chunk row, NO finalize)
    carrying a correction hint."""
    pjid = uuid4()
    next_job = uuid4()
    rs = _one_batch_rs(pjid, max_retries=2)
    conn = _Conn(rs, pjid)
    pool = _Pool(conn)
    llm = MagicMock()
    submit_ret = MagicMock()
    submit_ret.job_id = next_job
    llm.submit_job = AsyncMock(return_value=submit_ret)
    fin = AsyncMock()

    # Completed but unparseable (no [BLOCK 0] marker) → validation invalid.
    await block.resume(
        pool=pool, llm_client=llm, job=_job(pjid, status="completed",
                                            content="garbage with no marker",
                                            in_tok=3, out_tok=4),
        chapter_translation_id=uuid4(), finalize_cb=fin,
    )

    # Retried: re-submitted the SAME batch.
    llm.submit_job.assert_awaited_once()
    fin.assert_not_awaited()  # batch did not resolve → no finalize
    # No chunk row yet (batch_idx didn't advance).
    assert not [sql for sql, _ in conn.executed if "validation_errors" in sql]
    # The persisted resume_state advanced provider_job_id to the retry's job + set
    # a correction hint + bumped attempt — written UNDER the lock (on `conn`).
    persist = [(sql, args) for sql, args in conn.executed if "provider_job_id=$2" in sql]
    assert persist, "expected _persist_inflight to write the retry's provider_job_id"
    persisted_rs = json.loads(persist[-1][1][2])
    assert persisted_rs["attempt"] == 1
    assert persisted_rs["correction_hint"]
    assert persisted_rs["batch_idx"] == 0  # same batch
