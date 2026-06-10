"""Unit tests for the in-process hybrid retriever (wiki-llm M2 / §C10).

`run_hybrid_search` is the fusion core the HTTP endpoint and the wiki generator
share. These tests pin the IN-PROCESS contract: it takes an already-resolved
project, NEVER raises (a degraded/not_indexed leg is a marker), and fuses
exactly like the shipped endpoint. The endpoint's own behavior is covered by
test_raw_search_api.py — this file exercises the callable directly.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models import Project
from app.db.neo4j_repos.passages import Passage, PassageSearchHit
from app.search.retriever import RetrievalResult, run_hybrid_search

_USER = uuid4()
_BOOK = uuid4()
_PROJECT_ID = uuid4()


def _project(
    embedding_model="bge-m3",
    embedding_dimension=1024,
    rerank_model="33333333-3333-3333-3333-333333333333",
) -> Project:
    # rerank_model set by default so the BYOK rerank gate (D-RERANK-NOT-BYOK) runs;
    # pass rerank_model=None to exercise the skip → degraded['rerank']='not_configured'.
    return Project(
        project_id=_PROJECT_ID, user_id=_USER, name="X", description="",
        project_type="book", book_id=_BOOK, instructions="",
        extraction_enabled=False, extraction_status="disabled",
        embedding_model=embedding_model, embedding_dimension=embedding_dimension,
        rerank_model=rerank_model, rerank_model_source="user_model",
        extraction_config={}, last_extracted_at=None,
        estimated_cost_usd=Decimal("0"), actual_cost_usd=Decimal("0"),
        is_archived=False, version=1,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


def _passage_hit(chunk_index=0, score=0.9) -> PassageSearchHit:
    p = Passage(
        id=f"pg-{chunk_index}", user_id=str(_USER), project_id=str(_PROJECT_ID),
        source_type="chapter", source_id="ch-canon", chunk_index=chunk_index,
        text="canon prose", embedding_model="bge-m3", is_hub=False, chapter_index=9,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    return PassageSearchHit(passage=p, raw_score=score, vector=None)


def _lex_hit(block_index=0, score=1.5) -> dict:
    return {
        "chapterId": "ch-draft", "chapterTitle": "Draft Ch", "sortOrder": 3,
        "surface": "draft", "matchType": "lexical", "score": score,
        "relevance": 1.0, "snippet": "draft prose", "highlights": [[0, 3]],
        "location": {"blockIndex": block_index, "headingContext": None,
                     "charStart": 0, "charEnd": 3},
    }


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _clients(lex_hits=None, passage_hits=None, rerank_passthrough=True):
    book = MagicMock()
    book.lexical_search = AsyncMock(return_value=lex_hits)
    book.get_chapter_titles = AsyncMock(return_value={})
    embed = MagicMock()
    rr = MagicMock()
    if rerank_passthrough:
        async def _pass(q, docs, **kwargs):  # BYOK kwargs: user_id/model_source/model_ref
            return [{"index": i, "relevance_score": 0.9} for i in range(len(docs))]
        rr.rerank = AsyncMock(side_effect=_pass)
    else:
        rr.rerank = AsyncMock(return_value=None)
    return book, embed, rr


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_hybrid_fuses_both_legs(embed, find):
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
    )
    assert isinstance(out, RetrievalResult)
    assert out.degraded == {}
    # both a draft (lexical) and a canon (semantic) chapter present
    surfaces = {h["surface"] for h in out.hits}
    assert surfaces == {"draft", "canon"}


@pytest.mark.asyncio
async def test_empty_query_short_circuits():
    book, emb, rr = _clients()
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="   ", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
    )
    assert out.hits == [] and out.degraded == {}
    book.lexical_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_not_indexed_degrades_no_raise():
    # No embedding config on the project ⇒ semantic leg degrades (no 404/raise).
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙",
        project=_project(embedding_model=None, embedding_dimension=None),
        book_client=book, embedding_client=emb, reranker_client=rr,
    )
    assert out.degraded.get("semantic") == "not_indexed"
    assert [h["surface"] for h in out.hits] == ["draft"]  # lexical still returns


@pytest.mark.asyncio
async def test_lexical_unavailable_degrades():
    book, emb, rr = _clients(lex_hits=None)  # book-service returns None
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙",
        project=_project(embedding_model=None, embedding_dimension=None),
        book_client=book, embedding_client=emb, reranker_client=rr,
        mode="lexical",
    )
    assert out.degraded.get("lexical") == "book_service_unavailable"
    assert out.hits == []


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_lexical_mode_skips_rerank(embed, find):
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        mode="lexical",
    )
    rr.rerank.assert_not_awaited()  # lexical is clean → no rerank
    embed.assert_not_awaited()      # semantic leg skipped
    assert [h["surface"] for h in out.hits] == ["draft"]
