"""Context Budget Law §11a — the per-turn context-TRACE route (the Inspector feed).

`GET /v1/chat/sessions/{id}/context-trace` returns the window of recent assistant
turns, each carrying the FULL persisted contextBudget frame (raw_tokens, trace[],
status_flags, allocation breakdown, …) PLUS the parent user message (LEFT JOIN), so
the Inspector renders the turn list + the per-turn waterfall from one call. Owner-
gated + session-scoped like its context-history/context-budget siblings.

This is the BE-endpoint proof-ref for the §11a endpoint/owner-gate/pagination items
(the fast unit half; `scripts/context-inspector-trace-gate.py` is the live GATE).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.conftest import TEST_SESSION_ID, FakeRecord

_BREAKDOWN = {
    "system_prompt": 120,
    "skills": 40,
    "history": 500,
    "frontend_tool_schemas": 80,
}


def _frame(**over) -> dict:
    payload = {
        "used_tokens": 3528,
        "context_length": 131072,
        "effective_limit": 128000,
        "pct": 0.02,
        "until_compact_pct": 0.9,
        "baseline_tokens": 1600,
        "breakdown": _BREAKDOWN,
        "raw_tokens": 5128,
        "reduction_pct": 0.31,
        "status_flags": ["gated", "wire"],
        "retrieval_mode": "prepend",
        "intent": "status-op",
        "entity_presence": {"grounding_needed": False, "matched": [], "reason": "x"},
        "trace": [
            {"phase": "compiler", "tier": "T0", "category": "results",
             "action": "wire hygiene", "delta": -1600, "is_error": False},
        ],
    }
    payload.update(over)
    return payload


def _row(seq: int, *, breakdown: bool = True, user_message: str | None = "hi") -> FakeRecord:
    frame = _frame() if breakdown else {"used_tokens": 10, "pct": 0.0}
    return FakeRecord({
        "sequence_num": seq,
        "created_at": datetime.now(timezone.utc),
        "input_tokens": 1000 + seq,
        "output_tokens": 20 + seq,
        "context_breakdown": json.dumps(frame),
        "user_message": user_message,
    })


class TestContextTraceRoute:
    @pytest.mark.asyncio
    async def test_returns_turns_with_full_frame_and_user_message(self, client, mock_pool):
        mock_pool.fetchval.return_value = True  # owner gate: session owned
        mock_pool.fetch.return_value = [_row(2, user_message="who is Lam Uyen"), _row(4)]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/context-trace")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [it["sequence_num"] for it in items] == [2, 4]
        first = items[0]
        # the parent user message rides along (the LEFT JOIN)
        assert first["user_message"] == "who is Lam Uyen"
        # the FULL Inspector frame is present per turn (single-turn detail is inline)
        f = first["frame"]
        assert f["raw_tokens"] == 5128
        assert f["status_flags"] == ["gated", "wire"]
        assert f["trace"][0]["tier"] == "T0"
        assert f["breakdown"]["skills"] == 40

    @pytest.mark.asyncio
    async def test_owner_gate_404_and_no_row_query(self, client, mock_pool):
        mock_pool.fetchval.return_value = None  # not owned / not found
        resp = await client.get(f"/v1/chat/sessions/{uuid4()}/context-trace")
        assert resp.status_code == 404
        mock_pool.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_turns_without_a_measured_breakdown(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = [_row(1), _row(2, breakdown=False)]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/context-trace")
        assert resp.status_code == 200
        assert [it["sequence_num"] for it in resp.json()["items"]] == [1]

    @pytest.mark.asyncio
    async def test_limit_forwarded_and_capped(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = []
        ok = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/context-trace?limit=25")
        assert ok.status_code == 200
        assert 25 in mock_pool.fetch.call_args.args
        over = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/context-trace?limit=9999")
        assert over.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_zero_or_negative_rejected(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = []
        assert (await client.get(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/context-trace?limit=0")).status_code == 422
        assert (await client.get(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/context-trace?limit=-3")).status_code == 422
        mock_pool.fetch.assert_not_called()
