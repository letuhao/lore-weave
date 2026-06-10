"""Unit tests for the wiki-gen consumer's startup drain (wiki-llm M6 /review-impl).

The drain is what makes the resume story work: a job orphaned while the consumer
was down (pending) or crashed mid-run (running) is picked up on startup, rather
than holding the per-book lock forever with no re-trigger path.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.jobs import wiki_gen_processor


def _ctx(repo):
    return (
        patch.object(wiki_gen_processor, "WikiGenJobsRepo", return_value=repo),
        patch.object(wiki_gen_processor, "get_knowledge_pool", return_value=MagicMock()),
        patch.object(wiki_gen_processor, "process_wiki_gen_job", new=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_drain_processes_each_resumable_job():
    repo = MagicMock()
    repo.list_resumable = AsyncMock(return_value=[MagicMock(job_id="j1"), MagicMock(job_id="j2")])
    p1, p2, p3 = _ctx(repo)
    with p1, p2, p3 as proc:
        await wiki_gen_processor.drain_resumable_jobs()
    assert proc.await_count == 2
    proc.assert_any_await("j1")
    proc.assert_any_await("j2")


@pytest.mark.asyncio
async def test_drain_no_jobs_is_noop():
    repo = MagicMock()
    repo.list_resumable = AsyncMock(return_value=[])
    p1, p2, p3 = _ctx(repo)
    with p1, p2, p3 as proc:
        await wiki_gen_processor.drain_resumable_jobs()
    proc.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_swallows_query_failure():
    # A drain query failure must NOT block consumer startup.
    repo = MagicMock()
    repo.list_resumable = AsyncMock(side_effect=RuntimeError("db down"))
    p1, p2, p3 = _ctx(repo)
    with p1, p2, p3 as proc:
        await wiki_gen_processor.drain_resumable_jobs()  # must not raise
    proc.assert_not_awaited()
