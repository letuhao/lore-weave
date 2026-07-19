"""DBT-CHAT-PERSIST — the terminal-path assistant persistence.

The assistant reply used to be written ONLY on a clean finish, so a mid-stream
error, a user interrupt (client disconnect), or an abandoned/expired
frontend-tool suspend lost the whole streamed reply (the reported bug: a session
whose `propose_edit` card expired kept only the user message).

These cover the two helpers that close that gap:
  * ``_persist_terminal_assistant`` — writes a partial/incomplete reply with a
    finish_reason (idempotent on message_id; skips a truly-empty turn).
  * ``_materialize_abandoned_suspend`` — turns an abandoned suspended run into a
    visible 'interrupted' message.
Plus the read-path surfacing of the new ``finish_reason`` column.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.stream_service import (
    _persist_terminal_assistant,
    _materialize_abandoned_suspend,
    _mark_suspend_abandoned,
)


# ── a minimal fake asyncpg pool that records what got written ────────────────
class _FakeConn:
    def __init__(self, seq: int, inserted: bool):
        self._seq = seq
        self._inserted = inserted
        self.executed: list[tuple] = []
        self.inserted_row: dict | None = None

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Tx()

    async def fetchval(self, sql, *args):
        return self._seq

    async def fetchrow(self, sql, *args):
        # Capture the INSERT column values positionally (matches the helper's
        # VALUES order): 1=msg_id 2=session 3=user 4=content 5=parts 6=seq
        # 7=model_ref 8=parent 9=tool_calls 10=is_error 11=error_detail 12=finish
        self.inserted_row = {
            "message_id": args[0],
            "content": args[3],
            "is_error": args[9],
            "error_detail": args[10],
            "finish_reason": args[11],
        }
        return {"inserted": self._inserted}

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


class _FakePool:
    def __init__(self, seq: int = 5, inserted: bool = True):
        self.conn = _FakeConn(seq, inserted)
        # pool-level fetchrow/execute (used by _mark_suspend_abandoned): the row
        # the SELECT returns, and a record of the UPDATE that ran.
        self.existing_row: dict | None = None
        self.pool_executed: list[tuple] = []

    def acquire(self):
        conn = self.conn

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Acq()

    async def fetchrow(self, sql, *args):
        return self.existing_row

    async def execute(self, sql, *args):
        self.pool_executed.append((sql, args))


def _common():
    return dict(
        msg_id=str(uuid4()),
        session_id=str(uuid4()),
        user_id=str(uuid4()),
        parent_message_id=str(uuid4()),
        model_ref=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_error_persists_partial_with_is_error_and_finish_reason():
    pool = _FakePool()
    ok = await _persist_terminal_assistant(
        pool, **_common(),
        content="partial answer before the boom",
        reasoning="",
        tool_calls_history=None,
        finish_reason="error",
        is_error=True,
        error_detail="boom",
    )
    assert ok is True
    row = pool.conn.inserted_row
    assert row["content"] == "partial answer before the boom"
    assert row["is_error"] is True
    assert row["finish_reason"] == "error"
    assert row["error_detail"] == "boom"
    # a real INSERT (xmax=0) bumps the session message_count exactly once
    assert any("message_count = message_count + 1" in sql for sql, _ in pool.conn.executed)


@pytest.mark.asyncio
async def test_interrupt_persists_partial_not_flagged_error():
    pool = _FakePool()
    ok = await _persist_terminal_assistant(
        pool, **_common(),
        content="streamed so far",
        reasoning="",
        tool_calls_history=None,
        finish_reason="interrupted",
        is_error=False,
        error_detail=None,
    )
    assert ok is True
    assert pool.conn.inserted_row["finish_reason"] == "interrupted"
    assert pool.conn.inserted_row["is_error"] is False


@pytest.mark.asyncio
async def test_empty_turn_is_not_persisted():
    """Nothing streamed (no content, no reasoning, no tool calls) → the user
    message stands alone; a blank assistant bubble would be noise."""
    pool = _FakePool()
    ok = await _persist_terminal_assistant(
        pool, **_common(),
        content="",
        reasoning="",
        tool_calls_history=None,
        finish_reason="interrupted",
        is_error=False,
        error_detail=None,
    )
    assert ok is False
    assert pool.conn.inserted_row is None  # never reached the INSERT


@pytest.mark.asyncio
async def test_idempotent_update_does_not_double_count():
    """ON CONFLICT took the UPDATE branch (xmax != 0) → the row is refreshed but
    message_count must NOT be incremented again."""
    pool = _FakePool(inserted=False)
    ok = await _persist_terminal_assistant(
        pool, **_common(),
        content="x",
        reasoning="",
        tool_calls_history=None,
        finish_reason="interrupted",
        is_error=False,
        error_detail=None,
    )
    assert ok is True
    assert not any("message_count" in sql for sql, _ in pool.conn.executed)


@pytest.mark.asyncio
async def test_materialize_uses_prose_when_present():
    pool = _FakePool()
    susp = SimpleNamespace(
        message_id=str(uuid4()),
        session_id=str(uuid4()),
        owner_user_id=str(uuid4()),
        parent_message_id=None,
        model_ref=str(uuid4()),
        working=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Here is my reasoning."},
            {"role": "assistant", "content": ""},  # a tool-call-only turn
        ],
        pending_tool_call={"name": "propose_edit", "args": {}},
    )
    ok = await _materialize_abandoned_suspend(pool, susp)
    assert ok is True
    assert pool.conn.inserted_row["content"] == "Here is my reasoning."
    assert pool.conn.inserted_row["finish_reason"] == "interrupted"


@pytest.mark.asyncio
async def test_materialize_falls_back_to_rationale_when_no_prose():
    """The reported case: a pure tool-call turn (empty assistant content). The
    bubble must still say SOMETHING — fall back to the pending tool's rationale."""
    pool = _FakePool()
    susp = SimpleNamespace(
        message_id=str(uuid4()),
        session_id=str(uuid4()),
        owner_user_id=str(uuid4()),
        parent_message_id=None,
        model_ref=str(uuid4()),
        working=[{"role": "assistant", "content": ""}],
        pending_tool_call={
            "name": "propose_edit",
            "args": {"rationale": "Update the description per the plot."},
        },
    )
    ok = await _materialize_abandoned_suspend(pool, susp)
    assert ok is True
    assert pool.conn.inserted_row["content"] == "Update the description per the plot."
    assert pool.conn.inserted_row["finish_reason"] == "interrupted"


def _susp():
    return SimpleNamespace(
        message_id=str(uuid4()),
        session_id=str(uuid4()),
        owner_user_id=str(uuid4()),
        parent_message_id=None,
        model_ref=str(uuid4()),
        working=[{"role": "assistant", "content": ""}],
        pending_tool_call={"name": "propose_edit", "args": {"rationale": "r"}},
    )


@pytest.mark.asyncio
async def test_abandon_flips_awaiting_provisional_to_interrupted():
    """The suspend checkpoint wrote a rich 'awaiting_input' provisional; abandoning
    the run just flips its badge to 'interrupted' — content is preserved, NOT
    re-materialized (which would clobber the prose + tools + card)."""
    pool = _FakePool()
    pool.existing_row = {"finish_reason": "awaiting_input"}
    await _mark_suspend_abandoned(pool, _susp())
    # an UPDATE ... finish_reason='interrupted' ran; no re-insert (conn untouched)
    assert any("finish_reason = 'interrupted'" in sql for sql, _ in pool.pool_executed)
    assert pool.conn.inserted_row is None


@pytest.mark.asyncio
async def test_abandon_materializes_when_no_provisional():
    """If the best-effort suspend checkpoint never wrote a row, fall back to
    reconstructing from `working`."""
    pool = _FakePool()
    pool.existing_row = None  # no provisional
    await _mark_suspend_abandoned(pool, _susp())
    assert pool.conn.inserted_row is not None
    assert pool.conn.inserted_row["finish_reason"] == "interrupted"


@pytest.mark.asyncio
async def test_abandon_leaves_resolved_row_untouched():
    """A run that already resolved to 'stop'/'error' must NOT be downgraded."""
    pool = _FakePool()
    pool.existing_row = {"finish_reason": "stop"}
    await _mark_suspend_abandoned(pool, _susp())
    assert pool.pool_executed == []      # no UPDATE
    assert pool.conn.inserted_row is None  # no materialize
