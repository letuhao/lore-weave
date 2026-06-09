"""Saga driver tests — batched per-stage dispatch, completion, cancellation."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.saga.driver import process_campaign, DispatchClients
from app.saga.gating import ChapterState
from app.clients.dispatch_clients import DispatchError
from tests.conftest import FakeRecord

USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOOK = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CID = UUID("11111111-1111-1111-1111-111111111111")
PROJ = UUID("99999999-9999-9999-9999-999999999999")
C1 = "11111111-1111-1111-1111-111111111111"
C2 = "22222222-2222-2222-2222-222222222222"


def _campaign(**over):
    base = {
        "campaign_id": CID,
        "owner_user_id": USER,
        "book_id": BOOK,
        "status": "running",
        "stages": ["knowledge", "translation", "eval"],
        "gating_mode": "cold_start",
        "knowledge_project_id": PROJ,
        "chapter_from": None,
        "chapter_to": None,
        "knowledge_model_source": "user_model",
        "knowledge_model_ref": None,
        "translation_model_source": "user_model",
        "translation_model_ref": None,
        "target_language": "vi",
    }
    base.update(over)
    return FakeRecord(base)


def _ch(cid, k="pending", t="pending", ka=0, ta=0):
    return ChapterState(cid, k, t, ka, ta)


def _clients():
    tr = AsyncMock()
    tr.dispatch_job = AsyncMock(return_value="job-1")
    kn = AsyncMock()
    kn.dispatch_extraction = AsyncMock(return_value="ext-1")
    return DispatchClients(translation=tr, knowledge=kn), tr, kn


@pytest.fixture
def patch_repo(mocker):
    m = {
        "load_chapter_states": mocker.patch(
            "app.saga.driver.repo.load_chapter_states", new_callable=AsyncMock),
        "count_inflight": mocker.patch(
            "app.saga.driver.repo.count_inflight", new_callable=AsyncMock, return_value=0),
        "mark_stage_dispatched": mocker.patch(
            "app.saga.driver.repo.mark_stage_dispatched", new_callable=AsyncMock),
        "mark_stage_failed": mocker.patch(
            "app.saga.driver.repo.mark_stage_failed", new_callable=AsyncMock),
        "set_campaign_status": mocker.patch(
            "app.saga.driver.repo.set_campaign_status", new_callable=AsyncMock),
    }
    return m


async def _process(pool, clients, campaign, *, max_attempts=3, max_inflight=20):
    await process_campaign(
        pool, clients, campaign,
        max_attempts=max_attempts, max_inflight=max_inflight,
    )


async def test_cold_start_dispatches_both_stages(fake_pool, patch_repo):
    # c1 knowledge done → translate c1; c2 pending → extract.
    patch_repo["load_chapter_states"].return_value = [
        _ch(C1, k="done"), _ch(C2, k="pending"),
    ]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign())

    tr.dispatch_job.assert_awaited_once()
    assert tr.dispatch_job.call_args.kwargs["chapter_ids"] == [C1]
    kn.dispatch_extraction.assert_awaited_once()
    # Both claimed rows flipped to dispatched.
    stages = {c.args[3] for c in patch_repo["mark_stage_dispatched"].call_args_list}
    assert stages == {"knowledge", "translation"}


async def test_completion_sets_completed(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="done", t="done")]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign())
    patch_repo["set_campaign_status"].assert_awaited_once()
    assert patch_repo["set_campaign_status"].call_args.args[2] == "completed"
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()


async def test_cancelling_drained_finalizes(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="dispatched")]
    patch_repo["count_inflight"].return_value = 0
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign(status="cancelling"))
    patch_repo["set_campaign_status"].assert_awaited_once()
    assert patch_repo["set_campaign_status"].call_args.args[2] == "cancelled"


async def test_cancelling_with_inflight_waits(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="dispatched")]
    patch_repo["count_inflight"].return_value = 2
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign(status="cancelling"))
    patch_repo["set_campaign_status"].assert_not_called()
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()


async def test_knowledge_without_project_marks_failed(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="pending")]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign(knowledge_project_id=None))
    kn.dispatch_extraction.assert_not_called()
    patch_repo["mark_stage_failed"].assert_awaited()
    assert patch_repo["mark_stage_failed"].call_args.args[3] == "knowledge"


async def test_dispatch_error_marks_failed(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="done")]
    clients, tr, kn = _clients()
    tr.dispatch_job = AsyncMock(side_effect=DispatchError("boom"))
    await _process(fake_pool, clients, _campaign())
    # CLAIM-FIRST invariant (double-spend guard): the row was marked `dispatched`
    # BEFORE the dispatch call that failed, then released to `failed`.
    dispatched_translation = [
        c for c in patch_repo["mark_stage_dispatched"].call_args_list
        if c.args[3] == "translation"
    ]
    assert dispatched_translation, "row must be claimed before dispatch (claim-first)"
    patch_repo["mark_stage_failed"].assert_awaited()
    assert patch_repo["mark_stage_failed"].call_args.args[3] == "translation"


async def test_inflight_ceiling_blocks_new_dispatch(fake_pool, patch_repo):
    # At the per-campaign in-flight ceiling → no new dispatch this tick.
    patch_repo["load_chapter_states"].return_value = [
        _ch(C1, k="pending"), _ch(C2, k="pending"),
    ]
    patch_repo["count_inflight"].return_value = 20  # == max_inflight
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign(), max_inflight=20)
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()


async def test_dispatched_rows_not_redispatched(fake_pool, patch_repo):
    # Everything already in-flight → no new dispatch (double-spend guard).
    patch_repo["load_chapter_states"].return_value = [
        _ch(C1, k="dispatched"), _ch(C2, k="done", t="dispatched"),
    ]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign())
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()
