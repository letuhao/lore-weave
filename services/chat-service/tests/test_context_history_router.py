"""Chat Quality Wave W1-residual — the per-turn context-history route.

`GET /v1/chat/sessions/{id}/context-history` returns the ordered SERIES of
per-category token costs across the session's assistant turns (from the
W1-persisted chat_messages.context_breakdown JSONB), so the FE can chart how
each category evolved. Owner-gated like the sibling session-scoped routes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.conftest import TEST_SESSION_ID, FakeRecord


def _frame(breakdown: dict, **over) -> dict:
    """A persisted contextBudget frame (the shape of context_breakdown JSONB)."""
    payload = {
        "used_tokens": 1234,
        "context_length": 8192,
        "effective_limit": 8192,
        "pct": 0.15,
        "until_compact_pct": 0.65,
        "baseline_tokens": 400,
        "breakdown": breakdown,
    }
    payload.update(over)
    return payload


def _history_row(seq: int, breakdown: dict | None, **over) -> FakeRecord:
    """A chat_messages row as selected by the context-history query (asyncpg
    returns JSONB as a string → we store the frame json-encoded)."""
    now = datetime.now(timezone.utc)
    base = {
        "sequence_num": seq,
        "created_at": now,
        "input_tokens": 1000 + seq,
        "output_tokens": 50 + seq,
        "context_breakdown": json.dumps(_frame(breakdown)) if breakdown is not None else None,
    }
    base.update(over)
    return FakeRecord(base)


_BREAKDOWN = {
    "system_prompt": 120,
    "memory_knowledge": {"total": 300, "sections": {"facts": 200, "passages": 100}},
    "working_memory": 0,
    "steering": 0,
    "skills": 40,
    "plan_nudge": 0,
    "book_note": 0,
    "attached_context": 0,
    "history": 500,
    "tool_results": 0,
    "frontend_tool_schemas": 80,
    "mcp_tool_schemas": 60,
}


class TestContextHistory:
    @pytest.mark.asyncio
    async def test_returns_ordered_series(self, client, mock_pool):
        mock_pool.fetchval.return_value = True  # session exists / owned
        mock_pool.fetch.return_value = [
            _history_row(1, _BREAKDOWN),
            _history_row(3, _BREAKDOWN),
        ]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/context-history")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert [it["sequence_num"] for it in items] == [1, 3]
        first = items[0]
        assert first["input_tokens"] == 1001
        assert first["output_tokens"] == 51
        assert first["breakdown"]["system_prompt"] == 120
        # memory_knowledge nests {total, sections} — passed through verbatim.
        assert first["breakdown"]["memory_knowledge"]["total"] == 300
        assert first["breakdown"]["memory_knowledge"]["sections"]["facts"] == 200

    @pytest.mark.asyncio
    async def test_owner_gate_404_for_foreign_session(self, client, mock_pool):
        mock_pool.fetchval.return_value = None  # not owned / not found
        resp = await client.get(f"/v1/chat/sessions/{uuid4()}/context-history")
        assert resp.status_code == 404
        # The row query must NOT run once the owner gate rejects.
        mock_pool.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_when_no_breakdowns(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = []
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/context-history")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_skips_rows_without_a_breakdown(self, client, mock_pool):
        """A persisted frame that carries no `breakdown` map (e.g. a resume-path
        turn that didn't re-measure the parts) is skipped from the series."""
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = [
            _history_row(1, _BREAKDOWN),
            FakeRecord({
                "sequence_num": 2,
                "created_at": datetime.now(timezone.utc),
                "input_tokens": 900,
                "output_tokens": 40,
                # a frame WITHOUT a breakdown key (resume path)
                "context_breakdown": json.dumps({
                    "used_tokens": 900, "context_length": 8192,
                    "effective_limit": 8192, "pct": 0.11,
                    "until_compact_pct": 0.69,
                }),
            }),
        ]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/context-history")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [it["sequence_num"] for it in items] == [1]

    @pytest.mark.asyncio
    async def test_limit_forwarded_and_capped(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = []
        resp = await client.get(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/context-history?limit=25"
        )
        assert resp.status_code == 200
        assert 25 in mock_pool.fetch.call_args.args
        # over the cap → 422
        resp2 = await client.get(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/context-history?limit=9999"
        )
        assert resp2.status_code == 422
