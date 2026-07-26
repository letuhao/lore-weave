"""R2 (D-COACHING-SCORECARD-MOUNT) — the coaching-scorecards read route (FastAPI wiring + token gate
+ owner-scoping + card passthrough). The real end-to-end (a persisted evaluate scorecard → the FE) is
proven in the live-smoke; this proves the HTTP surface + that SD-7's `quarantine` rides through untouched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.config import settings
from tests.conftest import FakeRecord

_AUTH = {"X-Internal-Token": settings.internal_service_token}
UID = str(uuid4())


@pytest.mark.asyncio
async def test_scorecards_read_is_owner_scoped_and_passes_the_card_through(client, mock_pool):
    oid, sid = str(uuid4()), str(uuid4())
    card = {"overall_score": 72, "quarantine": True,
            "dimensions": [{"key": "clarity", "label": "Clarity", "score": 4, "note": "good"}]}
    mock_pool.fetch = AsyncMock(return_value=[
        FakeRecord({"output_id": oid, "session_id": sid, "title": "Interview scorecard",
                    "metadata": json.dumps(card), "created_at": datetime(2026, 7, 15, tzinfo=timezone.utc)}),
    ])
    r = await client.get("/internal/chat/assistant/scorecards", headers=_AUTH, params={"user_id": UID})
    assert r.status_code == 200
    body = r.json()
    assert len(body["scorecards"]) == 1
    item = body["scorecards"][0]
    assert item["output_id"] == oid and item["session_id"] == sid
    # SD-7: the quarantine flag rides through the read untouched (the route neither reads nor clears it).
    assert item["card"]["quarantine"] is True
    assert item["card"]["dimensions"][0]["key"] == "clarity"
    # owner-scoped + scorecard-typed + newest-first
    q = mock_pool.fetch.await_args.args[0]
    assert "owner_user_id = $1" in q and "output_type = 'scorecard'" in q and "ORDER BY created_at DESC" in q
    assert mock_pool.fetch.await_args.args[1] == UID  # the bound owner IS the requested user


@pytest.mark.asyncio
async def test_legacy_card_without_quarantine_coerces_fail_closed_to_true(client, mock_pool):
    # SD-7 defense-in-depth: a pre-C3 card has no `quarantine` field; the read MUST present it as True
    # (shown-never-trended). An explicit False (a future certified card) is preserved.
    legacy = {"overall_score": 85, "dimensions": []}  # no quarantine key
    certified = {"overall_score": 90, "quarantine": False, "dimensions": []}
    mock_pool.fetch = AsyncMock(return_value=[
        FakeRecord({"output_id": str(uuid4()), "session_id": None, "title": "legacy",
                    "metadata": json.dumps(legacy), "created_at": datetime(2026, 6, 24, tzinfo=timezone.utc)}),
        FakeRecord({"output_id": str(uuid4()), "session_id": None, "title": "certified",
                    "metadata": json.dumps(certified), "created_at": datetime(2026, 6, 23, tzinfo=timezone.utc)}),
    ])
    r = await client.get("/internal/chat/assistant/scorecards", headers=_AUTH, params={"user_id": UID})
    cards = r.json()["scorecards"]
    assert cards[0]["card"]["quarantine"] is True   # legacy null → fail-closed true
    assert cards[1]["card"]["quarantine"] is False  # explicit false preserved


@pytest.mark.asyncio
async def test_a_malformed_metadata_row_does_not_500_the_whole_feed(client, mock_pool):
    # cold-review MED — a row whose metadata is JSON null / a list must degrade that one card to a
    # quarantined shell, never take down the entire feed with a TypeError/AttributeError.
    good = {"overall_score": 70, "quarantine": True, "dimensions": []}
    mock_pool.fetch = AsyncMock(return_value=[
        FakeRecord({"output_id": str(uuid4()), "session_id": None, "title": "null-meta",
                    "metadata": "null", "created_at": datetime(2026, 6, 24, tzinfo=timezone.utc)}),
        FakeRecord({"output_id": str(uuid4()), "session_id": None, "title": "list-meta",
                    "metadata": json.dumps(["oops"]), "created_at": datetime(2026, 6, 23, tzinfo=timezone.utc)}),
        FakeRecord({"output_id": str(uuid4()), "session_id": None, "title": "good",
                    "metadata": json.dumps(good), "created_at": datetime(2026, 6, 22, tzinfo=timezone.utc)}),
    ])
    r = await client.get("/internal/chat/assistant/scorecards", headers=_AUTH, params={"user_id": UID})
    assert r.status_code == 200
    cards = r.json()["scorecards"]
    assert len(cards) == 3
    assert all(c["card"]["quarantine"] is True for c in cards)  # every one fail-closed, feed intact


@pytest.mark.asyncio
async def test_scorecards_requires_internal_token(client):
    r = await client.get("/internal/chat/assistant/scorecards", params={"user_id": UID})
    assert r.status_code == 401
    r2 = await client.get("/internal/chat/assistant/scorecards",
                          headers={"X-Internal-Token": "wrong"}, params={"user_id": UID})
    assert r2.status_code == 401
