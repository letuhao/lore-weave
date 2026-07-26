"""The idempotent-no-op WRITE breaker (2026-07-25, kg_project_create loop).

The repeated-read breaker (test_repeated_read_breaker.py) is READS-ONLY by design: a
repeated write is normally NOT a loop (six `book_create` calls make six books). But a
create-or-get write that reports it made NOTHING — `created: False`, e.g.
`kg_project_create` on a book whose KG project already exists — is the one write that is
provably pointless to repeat: the world did not change and the byte-identical call returns
the same "already exists" every time.

Measured live (docs/eval/e2e-newcomer/2026-07-25-newcomer-run.md): gemma re-called
`kg_project_create` ~5×/turn on an existing project, bounded only by TIER_A_SAME_OP_CAP,
burning a full tool-loop pass each time. These tests drive the REAL loop through
`_stream_with_tools` (not a unit of the counter) — the same discipline the read-breaker
tests use, because a breaker that is green in isolation but never wired into the loop is
worthless (that exact NameError once crashed every chat turn).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.stream_service import IDEMPOTENT_NOOP_WRITE_CAP, TIER_A_SAME_OP_CAP
from tests.test_repeated_read_breaker import _fake_client_repeating, _tool_calls
from tests.test_spend_gate import _kc

TEST_MODEL_REF = "00000000-0000-0000-0000-0000000000aa"


def _write_tool(name: str = "kg_project_create") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "create or get the knowledge project",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
            "_meta": {"tier": "A"},
        },
    }


async def _drive(*, times: int, result: dict, tool_name: str = "kg_project_create"):
    """Drive a model that calls the SAME Tier-A write, same args, `times` times, where
    every execution returns `result` (via the knowledge client mock)."""
    import app.services.stream_service as ss

    tool = _write_tool(tool_name)
    kc = _kc()
    kc.mcp_execute_tool.return_value = {"success": True, "result": result}
    chunks = []
    with patch.object(ss, "Client", _fake_client_repeating(tool_name, times)):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "set up the knowledge graph"}],
            gen_params={"max_tokens": 100}, tools=[tool],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode="write",
        ):
            chunks.append(ch)
    return chunks, kc


class TestIdempotentNoopWriteBreaker:
    @pytest.mark.asyncio
    async def test_a_single_create_is_untouched(self):
        """The common case — one create — must never be taxed."""
        chunks, kc = await _drive(times=1, result={"project_id": "p1", "created": False})
        tc = _tool_calls(chunks)
        assert len(tc) == 1
        assert tc[0]["ok"] is True
        kc.mcp_execute_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_repeated_created_false_write_is_short_circuited(self):
        """THE test. `created: False` = made nothing; the id is already in context. The
        2nd identical call is the loop and must be stopped WELL before TIER_A_SAME_OP_CAP."""
        chunks, kc = await _drive(times=5, result={"project_id": "p1", "created": False})
        tc = _tool_calls(chunks)

        # Only the first call actually executes; every repeat is short-circuited.
        assert kc.mcp_execute_tool.await_count == IDEMPOTENT_NOOP_WRITE_CAP, (
            "the no-op create loop must be broken after the first result"
        )
        assert kc.mcp_execute_tool.await_count < TIER_A_SAME_OP_CAP, (
            "must fire earlier than the generic Tier-A runaway cap"
        )
        assert tc[0]["ok"] is True

        blocked = [t for t in tc if not t["ok"]]
        assert blocked, "the short-circuited calls must be VISIBLE, not silently dropped"
        for r in blocked:
            # no silent no-op: the model is told exactly why + what to do instead
            assert "created=false" in r["error"]
            assert "move on" in r["error"] or "NEXT step" in r["error"]

    @pytest.mark.asyncio
    async def test_a_real_creation_is_never_blocked(self):
        """`created: True` is a genuine write — this breaker must NOT touch it (only the
        made-nothing case is provably pointless to repeat)."""
        chunks, kc = await _drive(times=3, result={"project_id": "p1", "created": True})
        # All 3 execute (3 < TIER_A_SAME_OP_CAP, so H7 doesn't fire either) — the no-op
        # breaker leaves a real, changing write completely alone.
        assert kc.mcp_execute_tool.await_count == 3
        assert all(tc["ok"] for tc in _tool_calls(chunks))

    @pytest.mark.asyncio
    async def test_a_write_with_no_created_field_is_never_blocked(self):
        """A Tier-A tool that doesn't use the `created` convention at all must be
        unaffected — the breaker keys strictly on `created is False`."""
        chunks, kc = await _drive(
            times=3, result={"ok": True, "updated": 1}, tool_name="book_update_details",
        )
        assert kc.mcp_execute_tool.await_count == 3
        assert all(tc["ok"] for tc in _tool_calls(chunks))
