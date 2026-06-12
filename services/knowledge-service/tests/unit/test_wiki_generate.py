"""Unit tests for wiki single-pass generate + gate (wiki-llm M3 / §C4).

The LLMClient is faked (a scripted sequence of completed/failed jobs); the rest
(prompt build, parse, gate) runs for real. Pins: happy path, corrective retry,
persistent-ungrounded skip, empty-body skip, and LLM-failure — generate_article
NEVER raises.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients.book_profile_client import BookProfile
from app.wiki.context import ContextSource, EntityBrief, GenerationContext
from app.wiki.generate import generate_article
from app.wiki.ir import Source


def _context(degraded=None) -> GenerationContext:
    brief = EntityBrief(entity_id="e1", name="姜子牙", kind="character",
                        aliases=["飞熊"], short_description="封神主角")
    items = [
        ContextSource(source=Source(cite_id="G1", kind="glossary", snippet="x"),
                      text="封神演义的主角"),
        ContextSource(source=Source(cite_id="P1", kind="passage", chapter_id="c",
                                    block_index=2, chapter_sort_order=3, snippet="y"),
                      text="奉命下山辅佐周武王伐纣"),
    ]
    return GenerationContext(brief=brief, items=items, degraded=degraded or {})


def _job(status: str, content: str | None):
    job = MagicMock()
    job.status = status
    job.result = {"messages": [{"content": content}]} if content is not None else {}
    return job


def _llm(*outcomes):
    """outcomes: each a Job, or an Exception to raise on that attempt."""
    llm = MagicMock()
    seq = iter(outcomes)

    async def _saw(**_kwargs):
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        return item

    llm.submit_and_wait = AsyncMock(side_effect=_saw)
    return llm


_GROUNDED = "姜子牙是封神演义的主角，奉命下山辅佐周武王伐纣 [P1]。"
_UNGROUNDED = "姜子牙是一个非常重要的封神人物，做了很多大事。"


async def _gen(llm):
    return await generate_article(
        context=_context(), profile=BookProfile(language="zh"), llm=llm,
        user_id="u1", model_source="user_model", model_ref="m1",
    )


@pytest.mark.asyncio
async def test_happy_path_one_call():
    res = await _gen(_llm(_job("completed", _GROUNDED)))
    assert res.status == "ok"
    assert res.attempts == 1
    assert res.ir is not None and res.gate.passed
    assert res.ir.grounded_claim_count >= 1


@pytest.mark.asyncio
async def test_corrective_retry_then_success():
    llm = _llm(_job("completed", _UNGROUNDED), _job("completed", _GROUNDED))
    res = await _gen(llm)
    assert res.status == "ok"
    assert res.attempts == 2
    # 2nd call carried the corrective note in the system prompt
    second_msgs = llm.submit_and_wait.await_args_list[1].kwargs["input"]["messages"]
    assert "PREVIOUS ATTEMPT" in second_msgs[0]["content"]


@pytest.mark.asyncio
async def test_persistent_ungrounded_skips():
    res = await _gen(_llm(_job("completed", _UNGROUNDED), _job("completed", _UNGROUNDED)))
    assert res.status == "skipped_no_grounding"
    assert res.attempts == 2
    assert res.ir is not None  # last IR kept for diagnostics
    assert res.gate.passed is False


@pytest.mark.asyncio
async def test_empty_body_skips():
    res = await _gen(_llm(_job("completed", "   "), _job("completed", "")))
    assert res.status == "empty"
    assert res.attempts == 2
    assert res.ir is None


@pytest.mark.asyncio
async def test_llm_exception_does_not_raise():
    res = await _gen(_llm(RuntimeError("boom"), RuntimeError("boom")))
    assert res.status == "llm_failed"
    assert res.ir is None


@pytest.mark.asyncio
async def test_non_completed_job_is_llm_failed():
    res = await _gen(_llm(_job("failed", None), _job("failed", None)))
    assert res.status == "llm_failed"


@pytest.mark.asyncio
async def test_degraded_markers_carry_through():
    # A not_indexed context (0 passages elsewhere) must be distinguishable
    # downstream — the degraded markers propagate into the result.
    res = await generate_article(
        context=_context(degraded={"semantic": "not_indexed"}),
        profile=BookProfile(language="zh"), llm=_llm(_job("completed", _GROUNDED)),
        user_id="u1", model_source="user_model", model_ref="m1",
    )
    assert res.status == "ok"
    assert res.degraded == {"semantic": "not_indexed"}
