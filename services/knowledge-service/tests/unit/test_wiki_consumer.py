"""Unit tests for the wiki-gen consumer's startup drain (wiki-llm M6 /review-impl).

The drain is what makes the resume story work: a job orphaned while the consumer
was down (pending) or crashed mid-run (running) is picked up on startup, rather
than holding the per-book lock forever with no re-trigger path.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.jobs import wiki_gen_processor
from app.jobs.wiki_gen_enqueue import WIKI_GEN_STREAM


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


# ── consumer-group delivery (D-WIKI-M6-CONSUMER-GROUP) ────────────────────────


@pytest.mark.asyncio
async def test_consume_batch_processes_then_acks():
    client = MagicMock()
    client.xreadgroup = AsyncMock(return_value=[(WIKI_GEN_STREAM, [("5-0", {"job_id": "j7"})])])
    client.xack = AsyncMock()
    with patch.object(wiki_gen_processor, "process_wiki_gen_job", new=AsyncMock()) as proc:
        await wiki_gen_processor._consume_batch(client, "g", "c")
    proc.assert_awaited_once_with("j7")
    # ack happens AFTER processing, on the exact message id, for the group.
    client.xack.assert_awaited_once_with(WIKI_GEN_STREAM, "g", "5-0")


@pytest.mark.asyncio
async def test_consume_batch_empty_is_noop():
    client = MagicMock()
    client.xreadgroup = AsyncMock(return_value=[])
    client.xack = AsyncMock()
    with patch.object(wiki_gen_processor, "process_wiki_gen_job", new=AsyncMock()) as proc:
        await wiki_gen_processor._consume_batch(client, "g", "c")
    proc.assert_not_awaited()
    client.xack.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_batch_acks_malformed_without_processing():
    # A message with no job_id is still ACKed (don't redeliver a poison wake-up).
    client = MagicMock()
    client.xreadgroup = AsyncMock(return_value=[(WIKI_GEN_STREAM, [("6-0", {})])])
    client.xack = AsyncMock()
    with patch.object(wiki_gen_processor, "process_wiki_gen_job", new=AsyncMock()) as proc:
        await wiki_gen_processor._consume_batch(client, "g", "c")
    proc.assert_not_awaited()
    client.xack.assert_awaited_once_with(WIKI_GEN_STREAM, "g", "6-0")


@pytest.mark.asyncio
async def test_consumer_creates_group_busygroup_safe_and_closes():
    client = MagicMock()
    client.xgroup_create = AsyncMock(
        side_effect=wiki_gen_processor.aioredis.ResponseError("BUSYGROUP Consumer Group name already exists")
    )
    client.xreadgroup = AsyncMock(side_effect=asyncio.CancelledError())  # break the loop at once
    client.aclose = AsyncMock()
    with patch.object(wiki_gen_processor, "drain_resumable_jobs", new=AsyncMock()), \
         patch.object(wiki_gen_processor.aioredis, "from_url", return_value=client):
        with pytest.raises(asyncio.CancelledError):
            await wiki_gen_processor.run_wiki_gen_consumer()
    # group create attempted with MKSTREAM; BUSYGROUP swallowed (no raise); client closed.
    client.xgroup_create.assert_awaited_once_with(
        WIKI_GEN_STREAM, wiki_gen_processor.WIKI_GEN_GROUP, id="$", mkstream=True
    )
    client.aclose.assert_awaited_once()
