"""Track 4 P2 — cross-encoder rerank helper (_cross_encoder_rerank).

Proves the reorder + score-replace, and that EVERY degrade path returns None so
the L3 selector keeps its MMR order (never fabricates or crashes on a bad rerank).
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.context.selectors.passages import L3Passage, _cross_encoder_rerank


def _p(text: str, score: float = 0.5) -> L3Passage:
    return L3Passage(
        text=text, source_type="chapter", source_id="s",
        chunk_index=0, score=score, is_hub=False, chapter_index=1,
    )


def _client(rerank_return):
    c = AsyncMock()
    c.rerank = AsyncMock(return_value=rerank_return)
    return c


async def _run(client, passages):
    return await _cross_encoder_rerank(
        client, query="q", passages=passages,
        model_ref="m", user_id=uuid4(), model_source="user_model",
    )


@pytest.mark.asyncio
async def test_reorders_by_relevance_and_replaces_score():
    passages = [_p("a", 0.1), _p("b", 0.2), _p("c", 0.3)]
    client = _client([
        {"index": 2, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.7},
        {"index": 1, "relevance_score": 0.5},
    ])
    out = await _run(client, passages)
    assert [p.text for p in out] == ["c", "a", "b"]
    assert [p.score for p in out] == [0.9, 0.7, 0.5]
    # input list not mutated (replace builds new objects)
    assert [p.score for p in passages] == [0.1, 0.2, 0.3]
    client.rerank.assert_awaited_once()


@pytest.mark.asyncio
async def test_none_result_degrades_to_mmr():
    assert await _run(_client(None), [_p("a"), _p("b")]) is None


@pytest.mark.asyncio
async def test_empty_result_degrades():
    assert await _run(_client([]), [_p("a"), _p("b")]) is None


@pytest.mark.asyncio
async def test_out_of_range_index_degrades():
    assert await _run(_client([{"index": 9, "relevance_score": 0.9}]), [_p("a"), _p("b")]) is None


@pytest.mark.asyncio
async def test_duplicate_index_degrades():
    client = _client([
        {"index": 0, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.8},
    ])
    assert await _run(client, [_p("a"), _p("b")]) is None


@pytest.mark.asyncio
async def test_non_int_index_degrades():
    assert await _run(_client([{"index": "0", "relevance_score": 0.9}]), [_p("a"), _p("b")]) is None


@pytest.mark.asyncio
async def test_partial_result_keeps_only_ranked():
    # reranker judged only one relevant → we keep only that one (never fabricate).
    out = await _run(_client([{"index": 1, "relevance_score": 0.9}]), [_p("a"), _p("b"), _p("c")])
    assert [p.text for p in out] == ["b"]


@pytest.mark.asyncio
async def test_missing_score_keeps_passage_score_unchanged():
    out = await _run(_client([{"index": 1}, {"index": 0}]), [_p("a", 0.4), _p("b", 0.5)])
    assert [p.text for p in out] == ["b", "a"]
    assert [p.score for p in out] == [0.5, 0.4]  # scores untouched (no relevance_score)
