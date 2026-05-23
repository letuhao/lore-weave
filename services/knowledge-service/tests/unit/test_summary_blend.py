"""P3 D5 — tests for summary_blend selector."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.context.selectors.summary_blend import (
    LevelSummaryHit,
    select_summary_blend,
)


def _async_iter_records(records: list[dict]):
    """Build an async iterator of dict records mimicking neo4j AsyncResult."""

    class _MockRows:
        def __init__(self, recs):
            self._recs = recs

        def __aiter__(self):
            self._iter = iter(self._recs)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    return _MockRows(records)


async def test_empty_embedding_returns_empty():
    session = MagicMock()
    out = await select_summary_blend(
        session, project_id="p", embedding_model_uuid="e",
        query_embedding=[],
    )
    assert out == []


async def test_blend_queries_all_3_levels_in_parallel():
    """Selector fires 3 Cypher queries (chapter + part + book)."""
    session = MagicMock()
    # Return distinct records per call so we can verify all 3 ran.
    call_seq = []

    async def mock_run(cypher, **kwargs):
        call_seq.append(kwargs["idx_name"])
        return _async_iter_records([])

    session.run = AsyncMock(side_effect=mock_run)
    await select_summary_blend(
        session, project_id="p1", embedding_model_uuid="e1",
        query_embedding=[0.1, 0.2, 0.3],
    )
    assert len(call_seq) == 3
    # Index names include chapter/part/book prefixes.
    assert any("chapter_summary_emb" in n for n in call_seq)
    assert any("part_summary_emb" in n for n in call_seq)
    assert any("book_summary_emb" in n for n in call_seq)


async def test_blend_weights_book_highest_in_ranking():
    """When raw_scores are equal, book-level wins via weighted_score (0.4 > 0.3)."""
    session = MagicMock()

    async def mock_run(cypher, **kwargs):
        idx_name = kwargs["idx_name"]
        if "chapter_summary_emb" in idx_name:
            return _async_iter_records([
                {"path": "book/part-1/chapter-1", "node_id": "c1",
                 "summary_text": "chapter summary", "score": 0.9},
            ])
        if "part_summary_emb" in idx_name:
            return _async_iter_records([
                {"path": "book/part-1", "node_id": "p1",
                 "summary_text": "part summary", "score": 0.9},
            ])
        if "book_summary_emb" in idx_name:
            return _async_iter_records([
                {"path": "book", "node_id": "b1",
                 "summary_text": "book summary", "score": 0.9},
            ])
        return _async_iter_records([])

    session.run = AsyncMock(side_effect=mock_run)
    hits = await select_summary_blend(
        session, project_id="p", embedding_model_uuid="e",
        query_embedding=[0.5, 0.5],
    )
    assert len(hits) == 3
    # Book first (0.9 × 0.4 = 0.36); chapter/part tied at 0.9 × 0.3 = 0.27.
    assert hits[0].level == "book"
    assert hits[0].weighted_score == pytest.approx(0.36)


async def test_blend_skips_rows_with_empty_summary_text():
    """Defensive: rows with NULL/empty summary_text are filtered out."""
    session = MagicMock()

    async def mock_run(cypher, **kwargs):
        if "chapter_summary_emb" in kwargs["idx_name"]:
            return _async_iter_records([
                {"path": "ch-1", "node_id": "c", "summary_text": "", "score": 0.99},
                {"path": "ch-2", "node_id": "c2", "summary_text": "valid text", "score": 0.5},
            ])
        return _async_iter_records([])

    session.run = AsyncMock(side_effect=mock_run)
    hits = await select_summary_blend(
        session, project_id="p", embedding_model_uuid="e",
        query_embedding=[0.1],
    )
    assert len(hits) == 1
    assert hits[0].summary_text == "valid text"


async def test_blend_degrades_gracefully_on_per_level_query_failure():
    """One level's query raising (e.g., index missing) must not fail the whole blend."""
    session = MagicMock()

    async def mock_run(cypher, **kwargs):
        if "chapter_summary_emb" in kwargs["idx_name"]:
            raise RuntimeError("index not found")
        if "book_summary_emb" in kwargs["idx_name"]:
            return _async_iter_records([
                {"path": "book", "node_id": "b", "summary_text": "book summary", "score": 0.8},
            ])
        return _async_iter_records([])

    session.run = AsyncMock(side_effect=mock_run)
    hits = await select_summary_blend(
        session, project_id="p", embedding_model_uuid="e",
        query_embedding=[0.1],
    )
    # Chapter failed → 0 hits from chapter. Book returned 1.
    assert len(hits) == 1
    assert hits[0].level == "book"


async def test_blend_returns_empty_when_no_indexes_exist():
    """Legacy graph (no summaries persisted) → all 3 queries return empty → []."""
    session = MagicMock()
    session.run = AsyncMock(return_value=_async_iter_records([]))
    hits = await select_summary_blend(
        session, project_id="p", embedding_model_uuid="e",
        query_embedding=[0.1],
    )
    assert hits == []


async def test_blend_truncates_to_final_top_n():
    """Each level returns 3; total 9 candidates; final_top_n=4 keeps best 4."""
    session = MagicMock()

    async def mock_run(cypher, **kwargs):
        # All levels return 3 hits each with descending scores.
        idx = kwargs["idx_name"]
        prefix = idx.split("_summary")[0]
        return _async_iter_records([
            {"path": f"{prefix}-1", "node_id": "1", "summary_text": "s1", "score": 0.9},
            {"path": f"{prefix}-2", "node_id": "2", "summary_text": "s2", "score": 0.6},
            {"path": f"{prefix}-3", "node_id": "3", "summary_text": "s3", "score": 0.3},
        ])

    session.run = AsyncMock(side_effect=mock_run)
    hits = await select_summary_blend(
        session, project_id="p", embedding_model_uuid="e",
        query_embedding=[0.1],
        final_top_n=4,
    )
    assert len(hits) == 4
    # All hits sorted by weighted_score descending.
    scores = [h.weighted_score for h in hits]
    assert scores == sorted(scores, reverse=True)
