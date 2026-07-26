"""P2 — unit tests for LeafProcessor (D3 + D9 retry semantics)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.clients.glossary_client import (
    GlossaryAnchorMalformed,
    GlossaryAnchorUnavailable,
)
from app.db.repositories.extraction_leaves import ExtractionLeaf
from app.jobs.leaf_processor import LeafProcessor, LeafTaskInput, RETRY_BUDGET


@dataclass
class _FakeRepo:
    """In-memory test double for ExtractionLeavesRepo."""

    cached: dict[str, ExtractionLeaf]

    def __init__(self):
        self.cached = {}
        self.claim_pending = AsyncMock(return_value=True)
        self.persist = AsyncMock(return_value=None)
        self.mark_failed = AsyncMock(return_value=1)  # retried_n=1 after first failure

    async def fetch_cached(self, task_id: str):
        return self.cached.get(task_id)


def _task(op: str = "entity", task_id: str = "tid-1") -> LeafTaskInput:
    return LeafTaskInput(
        book_id=uuid4(),
        chapter_id=uuid4(),
        scene_id=uuid4(),
        leaf_path="book/part-1/chapter-1/scene-1",
        op=op,
        task_id=task_id,
        normalized_leaf_text="alice ran",
        parse_version=1,
        extractor_version="v1-abcdef01",
        model_ref="m-uuid",
        glossary_anchor=[{"name": "Alice"}],
        parent_job_id=uuid4(),
        save_raw=False,
    )


async def test_cache_hit_returns_immediately_no_llm_call():
    repo = _FakeRepo()
    repo.cached["tid-1"] = ExtractionLeaf(
        id=uuid4(), book_id=uuid4(), chapter_id=uuid4(), scene_id=uuid4(),
        leaf_path="p", op="entity", task_id="tid-1", status="completed",
        candidates_jsonb=[{"name": "Alice"}],
        retried_n=0, error_message=None,
        parse_version=1, extractor_version="v1", model_ref="m",
        glossary_anchor_size=1,
    )
    extractor = AsyncMock(return_value=([{"x": 1}], {"raw": True}, {}))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    out = await proc.process(_task())
    assert out == [{"name": "Alice"}]
    extractor.assert_not_called()
    repo.claim_pending.assert_not_called()
    repo.persist.assert_not_called()


async def test_cache_miss_calls_extractor_then_persists():
    repo = _FakeRepo()
    extractor = AsyncMock(return_value=([{"name": "Bob"}], {"raw": "x"}, {"input": 10}))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    out = await proc.process(_task())
    assert out == [{"name": "Bob"}]
    extractor.assert_awaited_once()
    repo.claim_pending.assert_awaited_once()
    repo.persist.assert_awaited_once()


async def test_save_raw_false_omits_raw_response_from_persist():
    repo = _FakeRepo()
    extractor = AsyncMock(return_value=([{"x": 1}], {"raw": "y"}, {"t": 5}))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    task = _task()
    task.save_raw = False
    await proc.process(task)
    persist_kwargs = repo.persist.call_args.kwargs
    assert persist_kwargs["raw_response"] is None


async def test_save_raw_true_includes_raw_response():
    repo = _FakeRepo()
    extractor = AsyncMock(return_value=([{"x": 1}], {"raw": "y"}, {"t": 5}))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    task = _task()
    task.save_raw = True
    await proc.process(task)
    persist_kwargs = repo.persist.call_args.kwargs
    assert persist_kwargs["raw_response"] == {"raw": "y"}
    assert persist_kwargs["raw_token_usage"] == {"t": 5}


async def test_glossary_unavailable_marks_failed_and_re_raises():
    repo = _FakeRepo()
    extractor = AsyncMock(side_effect=GlossaryAnchorUnavailable("5xx"))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    with pytest.raises(GlossaryAnchorUnavailable):
        await proc.process(_task())
    repo.mark_failed.assert_awaited_once()
    error_msg = repo.mark_failed.call_args.kwargs["error_message"]
    assert "glossary unavailable" in error_msg


async def test_glossary_malformed_marks_failed_and_re_raises_no_retry():
    """GlossaryAnchorMalformed is non-transient — should NOT consume retry budget
    semantics differently (it just raises after marking)."""
    repo = _FakeRepo()
    extractor = AsyncMock(side_effect=GlossaryAnchorMalformed("4xx"))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    with pytest.raises(GlossaryAnchorMalformed):
        await proc.process(_task())
    repo.mark_failed.assert_awaited_once()
    error_msg = repo.mark_failed.call_args.kwargs["error_message"]
    assert "malformed" in error_msg


async def test_generic_llm_exception_marks_failed_and_re_raises():
    repo = _FakeRepo()
    extractor = AsyncMock(side_effect=RuntimeError("LLM timeout"))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    with pytest.raises(RuntimeError):
        await proc.process(_task())
    repo.mark_failed.assert_awaited_once()


async def test_unknown_op_marks_failed_with_clear_message():
    repo = _FakeRepo()
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": AsyncMock()},  # only entity, op='relation' missing
        semaphore=asyncio.Semaphore(1),
    )
    with pytest.raises(ValueError, match="relation"):
        await proc.process(_task(op="relation"))
    repo.mark_failed.assert_awaited_once()


async def test_retry_budget_exhaustion_logs_warning(caplog):
    """When retried_n hits retry_budget, log a warning (rest is caller's
    responsibility to skip)."""
    import logging
    repo = _FakeRepo()
    repo.mark_failed = AsyncMock(return_value=RETRY_BUDGET)  # already at budget
    extractor = AsyncMock(side_effect=RuntimeError("flake"))
    proc = LeafProcessor(
        repo=repo,  # type: ignore[arg-type]
        extractors={"entity": extractor},
        semaphore=asyncio.Semaphore(1),
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            await proc.process(_task())
    assert any("retry budget exhausted" in r.message for r in caplog.records)
