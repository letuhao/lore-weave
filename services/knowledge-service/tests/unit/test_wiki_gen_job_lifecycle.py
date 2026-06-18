"""wiki-llm M7b — unit tests for the job status + resume/cancel endpoints
(closes D-WIKI-M6-RESUME).

The repo SQL guards (``WHERE status IN (...)``) are proven by the cross-service
live-smoke; here we pin the endpoint contract the glossary proxy + FE depend on:
ownership (404 hides another book/user's job id), the resume→409-unless-paused +
re-enqueue, the cancel→409-unless-cancellable, and the status projection.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.repositories.wiki_gen_jobs import WikiGenJob
from app.routers import internal_wiki as iw


def _job(*, book_id, user_id, status="paused", entity_ids=None, items_done=None) -> WikiGenJob:
    return WikiGenJob(
        job_id=uuid4(), user_id=user_id, project_id=uuid4(), book_id=book_id,
        status=status, model_source="user_model", model_ref="m1",
        entity_ids=entity_ids or ["e1", "e2", "e3"], items_done=items_done or ["e1"],
        max_spend_usd=Decimal("1.00"), items_total=3, items_processed=1,
        cost_spent_usd=Decimal("0.25"),
    )


def _repo(*, get_latest=None, get=None, resume=True, cancel=True):
    r = MagicMock()
    r.get_latest_for_book = AsyncMock(return_value=get_latest)
    r.get = AsyncMock(return_value=get)
    r.resume = AsyncMock(return_value=resume)
    r.cancel = AsyncMock(return_value=cancel)
    return r


def _patch_repo(repo):
    """Patch the repo constructor + pool so the handler's
    ``WikiGenJobsRepo(get_knowledge_pool())`` yields our mock."""
    return patch.multiple(
        iw,
        WikiGenJobsRepo=MagicMock(return_value=repo),
        get_knowledge_pool=MagicMock(return_value=MagicMock()),
    )


# ── GET job status ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_status_projects_counts():
    book, user = uuid4(), uuid4()
    job = _job(book_id=book, user_id=user, status="running")
    with _patch_repo(_repo(get_latest=job)):
        out = await iw.get_wiki_gen_job(book, user)
    assert out.status == "running"
    assert out.entity_count == 3
    assert out.items_done_count == 1
    assert out.items_processed == 1
    assert out.cost_spent_usd == Decimal("0.25")


@pytest.mark.asyncio
async def test_get_job_status_projects_results_and_live_pass():
    # W4a — the screen-③ table data + live sub-step pointer flow through the poll.
    book, user = uuid4(), uuid4()
    job = _job(book_id=book, user_id=user, status="running")
    job.results = {
        "e1": {"outcome": "written", "citations": 2, "flags": 0, "name": "Mina"},
        "e2": {"outcome": "processing", "citations": 0, "flags": 0, "name": "Count"},
    }
    job.current_entity_id = "e2"
    job.current_pass = "verify"
    with _patch_repo(_repo(get_latest=job)):
        out = await iw.get_wiki_gen_job(book, user)
    assert out.results["e1"]["outcome"] == "written"
    assert out.results["e1"]["citations"] == 2
    assert out.current_entity_id == "e2"
    assert out.current_pass == "verify"


# ── W6b-2b: current source text (the diff "after") ───────────────────────────


@pytest.mark.asyncio
async def test_source_text_returns_only_requested_current_texts():
    repo = MagicMock()
    repo.list = AsyncMock(return_value=[MagicMock(project_id=uuid4())])
    with patch.multiple(
        iw,
        gather_entity_context=AsyncMock(return_value=MagicMock()),
        source_texts=MagicMock(return_value={
            "entity:e1": "name\ndesc", "kg:e1": "facts", "block:c1": "passage"}),
        get_glossary_client=MagicMock(), get_book_client=MagicMock(),
        get_embedding_client=MagicMock(), get_reranker_client=MagicMock(),
    ):
        req = iw.WikiSourceTextRequest(
            user_id=uuid4(), entity_id="e1",
            sources=[iw.WikiSourceRef(source_type="entity", source_id="e1")])
        out = await iw.wiki_source_text(uuid4(), req, projects_repo=repo)
    assert out.texts == {"entity:e1": "name\ndesc"}  # only the requested source


@pytest.mark.asyncio
async def test_source_text_empty_when_not_indexed():
    repo = MagicMock()
    repo.list = AsyncMock(return_value=[])  # no project → not indexed
    req = iw.WikiSourceTextRequest(
        user_id=uuid4(), entity_id="e1",
        sources=[iw.WikiSourceRef(source_type="entity", source_id="e1")])
    out = await iw.wiki_source_text(uuid4(), req, projects_repo=repo)
    assert out.texts == {}


@pytest.mark.asyncio
async def test_get_job_status_404_when_no_job():
    with _patch_repo(_repo(get_latest=None)):
        with pytest.raises(HTTPException) as exc:
            await iw.get_wiki_gen_job(uuid4(), uuid4())
    assert exc.value.status_code == 404


# ── resume ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resume_paused_job_flips_and_enqueues():
    book, user = uuid4(), uuid4()
    job = _job(book_id=book, user_id=user, status="paused")
    repo = _repo(get=job, resume=True)
    with _patch_repo(repo), \
            patch.object(iw, "enqueue_wiki_gen", new=AsyncMock()) as enq, \
            patch.object(iw, "_redis", return_value=MagicMock()):
        out = await iw.resume_wiki_gen_job(
            book, job.job_id, iw.WikiGenJobActionRequest(user_id=user))
    assert out["status"] == "pending"
    repo.resume.assert_awaited_once_with(job.job_id)
    enq.assert_awaited_once()  # re-enqueued so the consumer re-drives it


@pytest.mark.asyncio
async def test_resume_409_when_not_paused():
    book, user = uuid4(), uuid4()
    job = _job(book_id=book, user_id=user, status="running")
    repo = _repo(get=job, resume=False)  # repo.resume guards on status='paused'
    with _patch_repo(repo), \
            patch.object(iw, "enqueue_wiki_gen", new=AsyncMock()) as enq, \
            patch.object(iw, "_redis", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc:
            await iw.resume_wiki_gen_job(
                book, job.job_id, iw.WikiGenJobActionRequest(user_id=user))
    assert exc.value.status_code == 409
    enq.assert_not_awaited()  # no enqueue when the flip didn't happen


@pytest.mark.asyncio
async def test_resume_404_for_other_users_job():
    book = uuid4()
    job = _job(book_id=book, user_id=uuid4(), status="paused")  # owned by someone else
    repo = _repo(get=job, resume=True)
    with _patch_repo(repo), \
            patch.object(iw, "enqueue_wiki_gen", new=AsyncMock()) as enq, \
            patch.object(iw, "_redis", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc:
            await iw.resume_wiki_gen_job(
                book, job.job_id, iw.WikiGenJobActionRequest(user_id=uuid4()))
    assert exc.value.status_code == 404
    repo.resume.assert_not_awaited()  # ownership checked before any mutation
    enq.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_404_when_book_mismatch():
    user = uuid4()
    job = _job(book_id=uuid4(), user_id=user, status="paused")
    repo = _repo(get=job, resume=True)
    with _patch_repo(repo), \
            patch.object(iw, "enqueue_wiki_gen", new=AsyncMock()), \
            patch.object(iw, "_redis", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc:
            await iw.resume_wiki_gen_job(
                uuid4(), job.job_id, iw.WikiGenJobActionRequest(user_id=user))
    assert exc.value.status_code == 404


# ── cancel ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_pending_job_releases_lock():
    book, user = uuid4(), uuid4()
    job = _job(book_id=book, user_id=user, status="pending")
    repo = _repo(get=job, cancel=True)
    with _patch_repo(repo):
        out = await iw.cancel_wiki_gen_job(
            book, job.job_id, iw.WikiGenJobActionRequest(user_id=user))
    assert out["status"] == "cancelled"
    repo.cancel.assert_awaited_once_with(job.job_id)


@pytest.mark.asyncio
async def test_cancel_running_job_now_cancellable():
    # D-WIKI-M7B — a RUNNING wiki-gen job is now cancellable (repo.cancel guards on
    # pending|paused|running; the orchestrator's between-entity poll stops it).
    book, user = uuid4(), uuid4()
    job = _job(book_id=book, user_id=user, status="running")
    repo = _repo(get=job, cancel=True)
    with _patch_repo(repo):
        out = await iw.cancel_wiki_gen_job(
            book, job.job_id, iw.WikiGenJobActionRequest(user_id=user))
    assert out["status"] == "cancelled"
    repo.cancel.assert_awaited_once_with(job.job_id)


@pytest.mark.asyncio
async def test_cancel_409_when_terminal():
    # An already-terminal job → repo.cancel returns False (guard misses) → 409.
    book, user = uuid4(), uuid4()
    job = _job(book_id=book, user_id=user, status="complete")
    repo = _repo(get=job, cancel=False)
    with _patch_repo(repo):
        with pytest.raises(HTTPException) as exc:
            await iw.cancel_wiki_gen_job(
                book, job.job_id, iw.WikiGenJobActionRequest(user_id=user))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_cancel_404_for_other_users_job():
    book = uuid4()
    job = _job(book_id=book, user_id=uuid4(), status="paused")
    repo = _repo(get=job, cancel=True)
    with _patch_repo(repo):
        with pytest.raises(HTTPException) as exc:
            await iw.cancel_wiki_gen_job(
                book, job.job_id, iw.WikiGenJobActionRequest(user_id=uuid4()))
    assert exc.value.status_code == 404
    repo.cancel.assert_not_awaited()
