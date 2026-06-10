"""Stuck-`dispatched` self-heal (D-CAMPAIGN-BESTEFFORT-EMIT-REDIS).

reconcile_stuck asks downstream ground-truth whether a stage that has sat in
`dispatched` past the timeout actually finished (→ mark done, no re-dispatch),
failed/vanished (→ reset for re-dispatch), or is still in-flight (→ leave).
"""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.clients.dispatch_clients import DispatchError
from app.saga.reconcile import reconcile_stuck
from tests.conftest import FakeRecord

USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOOK = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PROJ = UUID("99999999-9999-9999-9999-999999999999")
JOB = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
C1 = UUID("11111111-1111-1111-1111-111111111111")


def _campaign(**over):
    base = {
        "campaign_id": CID, "owner_user_id": USER, "book_id": BOOK,
        "knowledge_project_id": PROJ, "target_language": "vi",
    }
    base.update(over)
    return FakeRecord(base)


def _stuck(chapter_id=C1, knowledge="pending", translation="pending", job_id=None):
    return FakeRecord({
        "chapter_id": chapter_id,
        "knowledge_status": knowledge,
        "translation_status": translation,
        "translation_job_id": job_id,
    })


def _clients():
    tr = AsyncMock()
    kn = AsyncMock()
    return type("C", (), {"translation": tr, "knowledge": kn})(), tr, kn


@pytest.fixture
def patch_repo(mocker):
    return {
        "find": mocker.patch("app.saga.reconcile.repo.find_stuck_dispatched",
                             new_callable=AsyncMock, return_value=[]),
        "done": mocker.patch("app.saga.reconcile.repo.mark_stage_done_by_chapter",
                             new_callable=AsyncMock, return_value=1),
        "reset": mocker.patch("app.saga.reconcile.repo.reset_stuck_stage",
                              new_callable=AsyncMock, return_value=1),
    }


async def test_no_stuck_rows_makes_no_downstream_calls(fake_pool, patch_repo):
    clients, tr, kn = _clients()
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    kn.extraction_status.assert_not_called()
    tr.chapter_status.assert_not_called()
    patch_repo["done"].assert_not_called()
    patch_repo["reset"].assert_not_called()


# ── knowledge (project-scoped truth, queried once) ──────────────────────────

async def test_knowledge_active_is_left_untouched(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(knowledge="dispatched")]
    clients, tr, kn = _clients()
    kn.extraction_status = AsyncMock(return_value={"active": True, "last_outcome": None})
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    patch_repo["done"].assert_not_called()
    patch_repo["reset"].assert_not_called()


async def test_knowledge_complete_marks_done(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(knowledge="dispatched")]
    clients, tr, kn = _clients()
    kn.extraction_status = AsyncMock(return_value={"active": False, "last_outcome": "complete"})
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    patch_repo["done"].assert_awaited_once()
    assert patch_repo["done"].call_args.kwargs["stage"] == "knowledge"
    # knowledge is language-agnostic — no language guard
    assert patch_repo["done"].call_args.kwargs["target_language"] is None
    patch_repo["reset"].assert_not_called()


async def test_knowledge_failed_resets(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(knowledge="dispatched")]
    clients, tr, kn = _clients()
    kn.extraction_status = AsyncMock(return_value={"active": False, "last_outcome": "failed"})
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    patch_repo["reset"].assert_awaited_once()
    assert patch_repo["reset"].call_args.args[3] == "knowledge"
    patch_repo["done"].assert_not_called()


async def test_knowledge_no_project_resets_without_query(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(knowledge="dispatched")]
    clients, tr, kn = _clients()
    await reconcile_stuck(fake_pool, clients, _campaign(knowledge_project_id=None), timeout_s=900)
    kn.extraction_status.assert_not_called()
    patch_repo["reset"].assert_awaited_once()


async def test_knowledge_truth_error_leaves_rows(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(knowledge="dispatched")]
    clients, tr, kn = _clients()
    kn.extraction_status = AsyncMock(side_effect=DispatchError("knowledge down"))
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    patch_repo["done"].assert_not_called()
    patch_repo["reset"].assert_not_called()


async def test_knowledge_truth_queried_once_for_many_stuck(fake_pool, patch_repo):
    # project-scoped truth: one query covers every knowledge-stuck chapter.
    c2 = UUID("22222222-2222-2222-2222-222222222222")
    patch_repo["find"].return_value = [
        _stuck(chapter_id=C1, knowledge="dispatched"),
        _stuck(chapter_id=c2, knowledge="dispatched"),
    ]
    clients, tr, kn = _clients()
    kn.extraction_status = AsyncMock(return_value={"active": False, "last_outcome": "complete"})
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    kn.extraction_status.assert_awaited_once()
    assert patch_repo["done"].await_count == 2


# ── translation (job-grouped: aliveness once, then per-chapter truth) ───────

async def test_translation_terminal_done_marks_done(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(translation="dispatched", job_id=JOB)]
    clients, tr, kn = _clients()
    tr.job_status = AsyncMock(return_value="terminal")
    tr.chapter_status = AsyncMock(return_value="done")
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    patch_repo["done"].assert_awaited_once()
    assert patch_repo["done"].call_args.kwargs["stage"] == "translation"
    # language guard threaded (a vi-only event must not mark a different-language row)
    assert patch_repo["done"].call_args.kwargs["target_language"] == "vi"


@pytest.mark.parametrize("truth", ["failed", "gone", "running"])
async def test_translation_terminal_not_done_resets(fake_pool, patch_repo, truth):
    # A terminal job won't progress, so any non-done chapter truth → re-dispatch.
    patch_repo["find"].return_value = [_stuck(translation="dispatched", job_id=JOB)]
    clients, tr, kn = _clients()
    tr.job_status = AsyncMock(return_value="terminal")
    tr.chapter_status = AsyncMock(return_value=truth)
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    patch_repo["reset"].assert_awaited_once()
    assert patch_repo["reset"].call_args.args[3] == "translation"
    patch_repo["done"].assert_not_called()


async def test_translation_active_job_leaves_without_per_chapter_call(fake_pool, patch_repo):
    # FAN-OUT FIX (MED /review-impl): an alive job is probed ONCE at job level — no
    # per-chapter truth call, no row mutation.
    patch_repo["find"].return_value = [
        _stuck(chapter_id=C1, translation="dispatched", job_id=JOB),
        _stuck(chapter_id=UUID("22222222-2222-2222-2222-222222222222"),
               translation="dispatched", job_id=JOB),
    ]
    clients, tr, kn = _clients()
    tr.job_status = AsyncMock(return_value="active")
    tr.chapter_status = AsyncMock()
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    tr.job_status.assert_awaited_once()       # ONE call for the whole batch
    tr.chapter_status.assert_not_called()     # no per-chapter fan-out
    patch_repo["done"].assert_not_called()
    patch_repo["reset"].assert_not_called()


async def test_translation_job_gone_resets_all_without_per_chapter(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(translation="dispatched", job_id=JOB)]
    clients, tr, kn = _clients()
    tr.job_status = AsyncMock(return_value="gone")
    tr.chapter_status = AsyncMock()
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    tr.chapter_status.assert_not_called()
    patch_repo["reset"].assert_awaited_once()


async def test_translation_no_job_id_resets_without_query(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(translation="dispatched", job_id=None)]
    clients, tr, kn = _clients()
    tr.job_status = AsyncMock()
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    tr.job_status.assert_not_called()
    patch_repo["reset"].assert_awaited_once()
    assert patch_repo["reset"].call_args.args[3] == "translation"


async def test_translation_job_status_error_leaves_rows(fake_pool, patch_repo):
    patch_repo["find"].return_value = [_stuck(translation="dispatched", job_id=JOB)]
    clients, tr, kn = _clients()
    tr.job_status = AsyncMock(side_effect=DispatchError("translation down"))
    await reconcile_stuck(fake_pool, clients, _campaign(), timeout_s=900)
    patch_repo["done"].assert_not_called()
    patch_repo["reset"].assert_not_called()
