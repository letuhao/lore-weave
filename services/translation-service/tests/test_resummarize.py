"""Unit tests for the #26/#7 end-of-job canonical resynthesis pass (resummarize.py).

No DB / no real provider — the glossary client + the LLM submit are mocked so the tests
exercise the orchestration: multi-mention LLM merge, single-mention shortcut, best-effort
error handling, and the empty-dirty no-op.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import resummarize


def _fake_job(content: str, status: str = "completed"):
    return SimpleNamespace(status=status, result={"messages": [{"role": "assistant", "content": content}]})


def _item(**over):
    base = {
        "entity_id": "e1",
        "entity_name": "归纳者",
        "attr_code": "appearance",
        "attr_label": "Appearance",
        "raw_values": ["a tall warrior", "a skilled, tall swordsman"],
        "source_language": "zh",
        "raw_fingerprint": "fp123",
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_resummarize_synthesizes_multi_mention():
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_fake_job("一位高大、技艺高超的剑士"))
    post = AsyncMock(return_value={"ok": True})
    with patch("app.workers.resummarize.fetch_canonical_dirty", new=AsyncMock(return_value=[_item()])), \
         patch("app.workers.resummarize.post_canonical", new=post):
        summary = await resummarize.run_resummarize_pass(
            book_id="b1", owner_user_id="u1", model_source="platform_model",
            model_ref="m1", source_language="zh", llm_client=llm,
        )
    assert summary == {"dirty": 1, "synthesized": 1, "failed": 0}
    llm.submit_and_wait.assert_awaited_once()
    # The synthesized text + the fetched fingerprint are written back.
    _, kwargs = post.call_args
    args = post.call_args.args
    assert args[0] == "b1" and args[1] == "e1" and args[2] == "appearance"
    assert args[3] == "一位高大、技艺高超的剑士"
    assert kwargs["raw_fingerprint"] == "fp123"
    # The billing label rides usage_purpose.
    assert llm.submit_and_wait.call_args.kwargs["job_meta"]["usage_purpose"] == "glossary_resummarize"


@pytest.mark.asyncio
async def test_resummarize_single_mention_skips_llm():
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_fake_job("should not be called"))
    post = AsyncMock(return_value={"ok": True})
    with patch("app.workers.resummarize.fetch_canonical_dirty",
               new=AsyncMock(return_value=[_item(raw_values=["the only mention"])])), \
         patch("app.workers.resummarize.post_canonical", new=post):
        summary = await resummarize.run_resummarize_pass(
            book_id="b1", owner_user_id="u1", model_source="platform_model",
            model_ref="m1", source_language="zh", llm_client=llm,
        )
    assert summary == {"dirty": 1, "synthesized": 1, "failed": 0}
    llm.submit_and_wait.assert_not_awaited()  # single mention → no LLM call
    assert post.call_args.args[3] == "the only mention"  # promoted verbatim


@pytest.mark.asyncio
async def test_resummarize_llm_failure_is_best_effort():
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(side_effect=RuntimeError("provider down"))
    post = AsyncMock(return_value={"ok": True})
    with patch("app.workers.resummarize.fetch_canonical_dirty", new=AsyncMock(return_value=[_item()])), \
         patch("app.workers.resummarize.post_canonical", new=post):
        summary = await resummarize.run_resummarize_pass(
            book_id="b1", owner_user_id="u1", model_source="platform_model",
            model_ref="m1", source_language="zh", llm_client=llm,
        )
    assert summary == {"dirty": 1, "synthesized": 0, "failed": 1}
    post.assert_not_awaited()  # nothing to write on an LLM failure


@pytest.mark.asyncio
async def test_resummarize_llm_non_completed_counts_failed():
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_fake_job("", status="failed"))
    post = AsyncMock(return_value={"ok": True})
    with patch("app.workers.resummarize.fetch_canonical_dirty", new=AsyncMock(return_value=[_item()])), \
         patch("app.workers.resummarize.post_canonical", new=post):
        summary = await resummarize.run_resummarize_pass(
            book_id="b1", owner_user_id="u1", model_source="platform_model",
            model_ref="m1", source_language="zh", llm_client=llm,
        )
    assert summary == {"dirty": 1, "synthesized": 0, "failed": 1}
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_resummarize_post_failure_counts_failed():
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_fake_job("merged"))
    post = AsyncMock(return_value=None)  # glossary write failed
    with patch("app.workers.resummarize.fetch_canonical_dirty", new=AsyncMock(return_value=[_item()])), \
         patch("app.workers.resummarize.post_canonical", new=post):
        summary = await resummarize.run_resummarize_pass(
            book_id="b1", owner_user_id="u1", model_source="platform_model",
            model_ref="m1", source_language="zh", llm_client=llm,
        )
    assert summary == {"dirty": 1, "synthesized": 0, "failed": 1}


@pytest.mark.asyncio
async def test_resummarize_empty_dirty_is_noop():
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock()
    with patch("app.workers.resummarize.fetch_canonical_dirty", new=AsyncMock(return_value=[])), \
         patch("app.workers.resummarize.post_canonical", new=AsyncMock()) as post:
        summary = await resummarize.run_resummarize_pass(
            book_id="b1", owner_user_id="u1", model_source="platform_model",
            model_ref="m1", source_language="zh", llm_client=llm,
        )
    assert summary == {"dirty": 0, "synthesized": 0, "failed": 0}
    llm.submit_and_wait.assert_not_awaited()
    post.assert_not_awaited()
