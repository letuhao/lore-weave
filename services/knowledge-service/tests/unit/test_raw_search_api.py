"""Raw-search Phase 2 — unit tests for the hybrid orchestrator endpoint.

Mocks ProjectsRepo.list (book→project), BookClient.lexical_search,
embed_query_cached, find_passages_by_vector. Covers: hybrid fuse,
mode skips, no-project 404, leg degradation, query validation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import Project
from app.db.neo4j_repos.passages import Passage, PassageSearchHit

_USER = uuid4()
_BOOK = uuid4()
_PROJECT_ID = uuid4()


def _project(embedding_model="bge-m3", embedding_dimension=1024) -> Project:
    return Project(
        project_id=_PROJECT_ID, user_id=_USER, name="X", description="",
        project_type="book", book_id=_BOOK, instructions="",
        extraction_enabled=False, extraction_status="disabled",
        embedding_model=embedding_model, embedding_dimension=embedding_dimension,
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
        "relevance": 1.0,  # E5: exact-match lexical relevance
        "snippet": "draft prose", "highlights": [[0, 3]],
        "location": {"blockIndex": block_index, "headingContext": None,
                     "charStart": 0, "charEnd": 3},
    }


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


_SENT = object()


def _make_client(project=_SENT, lexical=_SENT):
    if project is _SENT:
        project = _project()
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import (
        get_book_client,
        get_embedding_client,
        get_projects_repo,
        get_reranker_client,
    )

    projects_repo = MagicMock()
    projects_repo.list = AsyncMock(
        return_value=[project] if project is not None else []
    )
    book_client = MagicMock()
    book_client.lexical_search = AsyncMock(
        return_value=([_lex_hit()] if lexical is _SENT else lexical)
    )
    book_client.get_chapter_titles = AsyncMock(return_value={})
    embedding_client = MagicMock()

    # Default reranker: passthrough — every doc scored above the floor in input
    # order, so existing tests behave as if rerank is an identity. Rerank tests
    # re-override get_reranker_client with their own mock.
    async def _passthrough(query, documents):
        return [{"index": i, "relevance_score": max(0.9 - i * 0.05, 0.4)}
                for i in range(len(documents))]
    reranker = MagicMock()
    reranker.rerank = AsyncMock(side_effect=_passthrough)

    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_book_client] = lambda: book_client
    app.dependency_overrides[get_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_reranker_client] = lambda: reranker
    return TestClient(app, raise_server_exceptions=False), projects_repo, book_client


def _url(mode="hybrid", query="duel"):
    return f"/v1/knowledge/books/{_BOOK}/search?query={query}&mode={mode}"


# ── happy path ───────────────────────────────────────────────────────


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_hybrid_fuses_both_legs(mock_embed, mock_find):
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, book_client = _make_client()
    resp = client.get(_url("hybrid"))
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    surfaces = {h["surface"] for h in body["results"]}
    assert surfaces == {"draft", "canon"}  # lexical + semantic
    assert len(body["results"]) == 2
    assert body["degraded"] == {}
    book_client.lexical_search.assert_awaited()
    mock_embed.assert_awaited()


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_mode_semantic_skips_lexical(mock_embed, mock_find):
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    resp = client.get(_url("semantic"))
    assert resp.status_code == 200
    book_client.lexical_search.assert_not_awaited()
    assert all(h["surface"] == "canon" for h in resp.json()["results"])


@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_mode_lexical_skips_semantic(mock_embed):
    client, _, book_client = _make_client()
    resp = client.get(_url("lexical"))
    assert resp.status_code == 200
    mock_embed.assert_not_awaited()
    book_client.lexical_search.assert_awaited()
    assert all(h["surface"] == "draft" for h in resp.json()["results"])


# ── degradation / errors ─────────────────────────────────────────────


def test_no_project_returns_404_not_indexed():
    client, _, _ = _make_client(project=None)
    resp = client.get(_url("hybrid"))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "not_indexed"


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_book_service_down_degrades_to_semantic(mock_embed, mock_find):
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, _ = _make_client(lexical=None)  # book-service returns None
    resp = client.get(_url("hybrid"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"].get("lexical") == "book_service_unavailable"
    assert {h["surface"] for h in body["results"]} == {"canon"}


@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_embed_unavailable_degrades_to_lexical(mock_embed):
    mock_embed.return_value = None  # provider blip
    client, _, _ = _make_client()
    resp = client.get(_url("hybrid"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"].get("semantic") == "embed_unavailable"
    assert {h["surface"] for h in body["results"]} == {"draft"}


def test_no_embedding_model_degrades_to_lexical():
    client, _, _ = _make_client(
        project=_project(embedding_model=None, embedding_dimension=None),
    )
    resp = client.get(_url("hybrid"))
    assert resp.status_code == 200
    assert resp.json()["degraded"].get("semantic") == "not_indexed"
    assert {h["surface"] for h in resp.json()["results"]} == {"draft"}


def test_query_required():
    client, _, _ = _make_client()
    assert client.get(f"/v1/knowledge/books/{_BOOK}/search?query=").status_code == 422


def test_bad_mode_rejected():
    client, _, _ = _make_client()
    assert client.get(_url("fuzzy")).status_code == 422


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_dim_mismatch_degrades_to_lexical(mock_embed, mock_find):
    mock_embed.return_value = [0.1] * 1536  # user changed model out-of-band
    mock_find.side_effect = ValueError("query_vector length 1536 does not match dim 1024")
    client, _, _ = _make_client()
    resp = client.get(_url("hybrid"))
    assert resp.status_code == 200
    assert resp.json()["degraded"].get("semantic") == "embedding_dim_mismatch"
    assert {h["surface"] for h in resp.json()["results"]} == {"draft"}


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_semantic_hit_titles_enriched(mock_embed, mock_find):
    cid = uuid4()
    p = Passage(
        id="pg-t", user_id=str(_USER), project_id=str(_PROJECT_ID),
        source_type="chapter", source_id=str(cid), chunk_index=0, text="canon prose",
        embedding_model="bge-m3", is_hub=False, chapter_index=3,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [PassageSearchHit(passage=p, raw_score=0.9, vector=None)]
    client, _, book_client = _make_client()
    book_client.get_chapter_titles = AsyncMock(return_value={cid: "第3回 — Bridge Duel"})
    resp = client.get(_url("semantic"))
    assert resp.status_code == 200, resp.json()
    hit = resp.json()["results"][0]
    assert hit["surface"] == "canon"
    assert hit["chapterTitle"] == "第3回 — Bridge Duel"
    book_client.get_chapter_titles.assert_awaited()


# ── E5: granularity + relevance + score-floor ────────────────────────


def test_granularity_defaults_to_chapter_and_forwards():
    client, _, book_client = _make_client()
    assert client.get(_url("lexical")).status_code == 200
    _, kwargs = book_client.lexical_search.call_args
    assert kwargs.get("granularity") == "chapter"  # navigate default


def test_granularity_block_forwarded():
    client, _, book_client = _make_client()
    assert client.get(_url("lexical") + "&granularity=block").status_code == 200
    _, kwargs = book_client.lexical_search.call_args
    assert kwargs.get("granularity") == "block"


def test_bad_granularity_rejected():
    client, _, _ = _make_client()
    assert client.get(_url("lexical") + "&granularity=page").status_code == 422


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_explicit_min_relevance_floors_low_hit(mock_embed, mock_find):
    # the floor is OFF by default (compressed cosine → lossy); an explicit
    # min_relevance opt-in drops a low-cosine hit (0.2 < 0.5).
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.2)]
    client, _, _ = _make_client()
    # rerank=false isolates the E5 cosine floor (rerank would overwrite relevance)
    resp = client.get(_url("semantic") + "&min_relevance=0.5&rerank=false")
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_floor_off_by_default_keeps_low_hit(mock_embed, mock_find):
    # default min_relevance=0.0 → low-cosine hit survives (no global threshold)
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.2)]
    client, _, _ = _make_client()
    resp = client.get(_url("semantic") + "&rerank=false")  # isolate E5 cosine path
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_chapter_mode_caps_across_surfaces(mock_embed, mock_find):
    # MED-2: chapter granularity caps on chapterId ALONE — a chapter with BOTH
    # a lexical(draft) and a semantic(canon) hit collapses to ONE row (navigate
    # shape). Pin the behaviour so a future fusion change can't silently alter it.
    mock_embed.return_value = [0.1] * 1024
    # semantic passage on the SAME chapterId as the default lexical hit ("ch-draft")
    p = Passage(
        id="pg-x", user_id=str(_USER), project_id=str(_PROJECT_ID),
        source_type="chapter", source_id="ch-draft", chunk_index=0, text="canon",
        embedding_model="bge-m3", is_hub=False, chapter_index=3,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    mock_find.return_value = [PassageSearchHit(passage=p, raw_score=0.95, vector=None)]
    client, _, _ = _make_client()  # lexical leg returns _lex_hit (chapterId ch-draft)
    body = client.get(_url("hybrid")).json()  # default granularity=chapter
    rows = [h for h in body["results"] if h["chapterId"] == "ch-draft"]
    assert len(rows) == 1  # one row for the chapter despite two surfaces


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_block_mode_keeps_both_surfaces(mock_embed, mock_find):
    # block granularity lifts the cap → both surfaces of the same chapter surface.
    mock_embed.return_value = [0.1] * 1024
    p = Passage(
        id="pg-y", user_id=str(_USER), project_id=str(_PROJECT_ID),
        source_type="chapter", source_id="ch-draft", chunk_index=0, text="canon",
        embedding_model="bge-m3", is_hub=False, chapter_index=3,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    mock_find.return_value = [PassageSearchHit(passage=p, raw_score=0.95, vector=None)]
    client, _, _ = _make_client()
    body = client.get(_url("hybrid") + "&granularity=block").json()
    rows = [h for h in body["results"] if h["chapterId"] == "ch-draft"]
    assert len(rows) == 2  # draft + canon both kept


# ── E5B: cross-encoder rerank ────────────────────────────────────────


def _override_reranker(return_value=None, side_effect=None):
    from app.main import app
    from app.deps import get_reranker_client
    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=return_value, side_effect=side_effect)
    app.dependency_overrides[get_reranker_client] = lambda: rr
    return rr


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_rerank_floors_and_reorders(mock_embed, mock_find):
    # 2 fused hits; reranker scores idx0=0.2 (< 0.30 floor → dropped),
    # idx1=0.8 (kept). Result = 1 hit, relevance = the cross-encoder score.
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, _ = _make_client()  # lexical _lex_hit + semantic passage → 2 hits
    rr = _override_reranker(return_value=[
        {"index": 0, "relevance_score": 0.2}, {"index": 1, "relevance_score": 0.8},
    ])
    body = client.get(_url("hybrid")).json()
    rr.rerank.assert_awaited()
    assert len(body["results"]) == 1
    assert body["results"][0]["relevance"] == 0.8


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_rerank_unavailable_degrades(mock_embed, mock_find):
    # reranker None → keep fusion order + degraded marker (never 500).
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, _ = _make_client()
    _override_reranker(return_value=None)
    body = client.get(_url("hybrid")).json()
    assert body["degraded"].get("rerank") == "unavailable"
    assert len(body["results"]) == 2  # both legs retained, unreranked


def test_lexical_mode_skips_rerank():
    client, _, _ = _make_client()
    rr = _override_reranker(return_value=[])
    resp = client.get(_url("lexical"))
    assert resp.status_code == 200
    rr.rerank.assert_not_awaited()  # lexical is already clean → no rerank


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_rerank_false_skips(mock_embed, mock_find):
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, _ = _make_client()
    rr = _override_reranker(return_value=[])
    resp = client.get(_url("hybrid") + "&rerank=false")
    assert resp.status_code == 200
    rr.rerank.assert_not_awaited()


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_results_carry_relevance(mock_embed, mock_find):
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, _ = _make_client()
    body = client.get(_url("hybrid")).json()
    assert body["results"]
    assert all("relevance" in h for h in body["results"])
