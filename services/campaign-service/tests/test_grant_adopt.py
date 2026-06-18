"""E0-4b — campaign-service grant adoption.

Covers the executable guards owner-run tests can't give:
  * grant_deps.authorize_book tier semantics (none→404, under→403, ≥→caller);
  * router deny matrix (view-grantee 403 on manage/edit routes; non-grantee 404 on
    reads; the SHARED per-book read view — a grantee sees a campaign owned by
    someone else);
  * consumer correlation — the knowledge stage matches book_owner_user_id (the
    event's graph-owner), translation/eval match owner_user_id (the caller).
The dual-identity DISPATCH is covered in test_driver.py.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app import repositories as repo
from app.grant_client import GrantLevel
from app.grant_deps import authorize_book
from tests.conftest import FakeRecord, TEST_USER

BOOK = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
OTHER = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
CAMP = "dddddddd-dddd-dddd-dddd-dddddddddddd"
NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)


# ── grant_deps.authorize_book — tier semantics ───────────────────────────────

def _gc(level: GrantLevel):
    gc = MagicMock()
    gc.resolve_grant = AsyncMock(return_value=level)
    return gc


@pytest.mark.asyncio
async def test_authorize_book_none_is_404():
    with pytest.raises(HTTPException) as ei:
        await authorize_book(_gc(GrantLevel.NONE), BOOK, UUID(TEST_USER), GrantLevel.VIEW)
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_authorize_book_under_tier_is_403():
    with pytest.raises(HTTPException) as ei:
        await authorize_book(_gc(GrantLevel.VIEW), BOOK, UUID(TEST_USER), GrantLevel.MANAGE)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_authorize_book_at_tier_returns_caller():
    caller = await authorize_book(_gc(GrantLevel.MANAGE), BOOK, UUID(TEST_USER), GrantLevel.MANAGE)
    assert caller == UUID(TEST_USER)


# ── router deny matrix (shared per-book view) ─────────────────────────────────

def _row(**over):
    base = {
        "campaign_id": UUID(CAMP), "owner_user_id": OTHER,  # owned by SOMEONE ELSE
        "book_owner_user_id": OTHER, "book_id": BOOK, "name": "Shared", "status": "running",
        "gating_mode": "phase_barrier", "stages": ["knowledge", "translation", "eval"],
        "target_language": "vi", "knowledge_project_id": None, "embedding_model_ref": None,
        "knowledge_model_source": None, "knowledge_model_ref": None,
        "translation_model_source": None, "translation_model_ref": None,
        "verifier_model_source": None, "verifier_model_ref": None,
        "eval_judge_model_source": None, "eval_judge_model_ref": None,
        "chapter_from": None, "chapter_to": None, "budget_usd": None,
        "spent_usd": Decimal("0"), "total_chapters": 1, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "started_at": None, "finished_at": None,
    }
    base.update(over)
    return FakeRecord(base)


def test_get_shared_view_grantee_sees_others_campaign(client, mocker, fake_grant):
    # The campaign is owned by OTHER; a VIEW-grantee on the book sees it (drop-owner
    # read + grant gate). Proves the shared per-book view.
    fake_grant.resolve_grant.return_value = GrantLevel.VIEW
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=_row())
    resp = client.get(f"/v1/campaigns/{CAMP}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["owner_user_id"] == str(OTHER)


def test_get_non_grantee_404(client, mocker, fake_grant):
    fake_grant.resolve_grant.return_value = GrantLevel.NONE
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=_row())
    resp = client.get(f"/v1/campaigns/{CAMP}")
    assert resp.status_code == 404


def test_pause_view_grantee_403(client, mocker, fake_grant):
    # pause needs `edit`; a VIEW-grantee is forbidden.
    fake_grant.resolve_grant.return_value = GrantLevel.VIEW
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=_row())
    resp = client.post(f"/v1/campaigns/{CAMP}/pause")
    assert resp.status_code == 403


def test_pause_edit_grantee_ok(client, mocker, fake_grant):
    fake_grant.resolve_grant.return_value = GrantLevel.EDIT
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 side_effect=[_row(status="running"), _row(status="paused")])
    mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/pause")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"


def test_start_edit_grantee_403(client, mocker, fake_grant):
    # start needs `manage`; an EDIT-grantee (enough for pause) is forbidden.
    fake_grant.resolve_grant.return_value = GrantLevel.EDIT
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=_row())
    resp = client.post(f"/v1/campaigns/{CAMP}/start")
    assert resp.status_code == 403


def test_list_book_scoped_grant_gated(client, mocker, fake_grant):
    # ?book_id= → grant-gated shared per-book list (view). No grant → 404.
    fake_grant.resolve_grant.return_value = GrantLevel.NONE
    resp = client.get(f"/v1/campaigns?book_id={BOOK}")
    assert resp.status_code == 404


def test_list_book_scoped_calls_book_query(client, mocker, fake_grant):
    fake_grant.resolve_grant.return_value = GrantLevel.VIEW
    lst = mocker.patch("app.repositories.list_campaigns", new_callable=AsyncMock, return_value=[])
    resp = client.get(f"/v1/campaigns?book_id={BOOK}")
    assert resp.status_code == 200
    assert lst.call_args.kwargs.get("book_id") == BOOK


# ── consumer correlation — stage→identity column ──────────────────────────────

def test_match_id_col_knowledge_is_book_owner():
    assert repo._match_id_col("knowledge") == "book_owner_user_id"
    assert repo._match_id_col("translation") == "owner_user_id"
    assert repo._match_id_col("eval") == "owner_user_id"


@pytest.mark.asyncio
async def test_mark_stage_done_knowledge_matches_book_owner(fake_pool):
    # A knowledge.chapter_extracted event carries the graph owner's user_id → the
    # SQL must correlate on book_owner_user_id (else a collaborator's campaign,
    # owner_user_id = caller ≠ graph owner, never advances).
    await repo.mark_stage_done_by_chapter(
        fake_pool, owner_user_id=OTHER, book_id=BOOK, chapter_id=UUID(CAMP),
        stage="knowledge", target_language=None,
    )
    sql = fake_pool.execute.call_args.args[0]
    assert "c.book_owner_user_id = $2" in sql


@pytest.mark.asyncio
async def test_mark_stage_done_translation_matches_owner(fake_pool):
    await repo.mark_stage_done_by_chapter(
        fake_pool, owner_user_id=UUID(TEST_USER), book_id=BOOK, chapter_id=UUID(CAMP),
        stage="translation", target_language="vi",
    )
    sql = fake_pool.execute.call_args.args[0]
    assert "c.owner_user_id = $2" in sql
