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


def _project(
    embedding_model="bge-m3", embedding_dimension=1024,
    rerank_model="33333333-3333-3333-3333-333333333333",
) -> Project:
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
    # E0-3: raw-search now resolves the book's project via get_by_book (after a
    # book-grant check) and runs as the project owner.
    projects_repo.get_by_book = AsyncMock(return_value=project)
    book_client = MagicMock()
    book_client.lexical_search = AsyncMock(
        return_value=([_lex_hit()] if lexical is _SENT else lexical)
    )
    book_client.get_chapter_titles = AsyncMock(return_value={})
    # KG-ML M4 — resolver tier 2 (reader-pref). Default None so existing tests
    # fall through to detected-query-language (no matching hits ⇒ no reordering).
    book_client.get_reader_language = AsyncMock(return_value=None)
    embedding_client = MagicMock()

    # Default reranker: passthrough — every doc scored above the floor in input
    # order, so existing tests behave as if rerank is an identity. Rerank tests
    # re-override get_reranker_client with their own mock.
    async def _passthrough(query, documents, **kwargs):
        return [{"index": i, "relevance_score": max(0.9 - i * 0.05, 0.4)}
                for i in range(len(documents))]
    reranker = MagicMock()
    reranker.rerank = AsyncMock(side_effect=_passthrough)
    reranker.get_default_rerank = AsyncMock(return_value=None)

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


# ── KG-ML M4: reader-language resolution chain ───────────────────────


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_no_language_param_resolves_reader_pref(mock_embed, mock_find):
    """Without ?language=, the endpoint resolves the CALLER's stored
    reader-language (M3) for this book."""
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    book_client.get_reader_language = AsyncMock(return_value="vi")
    resp = client.get(_url("hybrid"))
    assert resp.status_code == 200
    book_client.get_reader_language.assert_awaited_once_with(_BOOK, _USER)


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_explicit_language_param_skips_reader_pref(mock_embed, mock_find):
    """An explicit ?language= wins — the stored reader-pref is NOT consulted."""
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    book_client.get_reader_language = AsyncMock(return_value="en")
    resp = client.get(_url("hybrid") + "&language=vi")
    assert resp.status_code == 200
    book_client.get_reader_language.assert_not_awaited()


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_malformed_language_falls_through_to_reader_pref(mock_embed, mock_find):
    """/review-impl LOW — a malformed ?language= is IGNORED and resolution falls
    through to the stored reader-pref, instead of silently disabling the boost."""
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    book_client.get_reader_language = AsyncMock(return_value="vi")
    resp = client.get(_url("hybrid") + "&language=english")  # fails the tag shape
    assert resp.status_code == 200
    book_client.get_reader_language.assert_awaited_once()


@patch("app.routers.public.raw_search.detect_primary_language")
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_short_query_skips_language_detection(mock_embed, mock_find, mock_detect):
    """/review-impl LOW — a too-short query can't reliably detect a language, so
    detection is skipped (no mis-boost). No explicit param, no stored pref."""
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    book_client.get_reader_language = AsyncMock(return_value=None)
    resp = client.get(f"/v1/knowledge/books/{_BOOK}/search?query=Dr&mode=hybrid")
    assert resp.status_code == 200
    mock_detect.assert_not_called()


@patch("app.routers.public.raw_search.detect_primary_language", return_value="en")
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_long_query_uses_language_detection(mock_embed, mock_find, mock_detect):
    """A query long enough to detect reliably DOES fall through to detection."""
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    book_client.get_reader_language = AsyncMock(return_value=None)
    resp = client.get(f"/v1/knowledge/books/{_BOOK}/search?query=Dracula castle journey&mode=hybrid")
    assert resp.status_code == 200
    mock_detect.assert_called_once()


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
    # No user-level default by default; the rerank gate resolves project model first.
    rr.get_default_rerank = AsyncMock(return_value=None)
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
    # D-RERANK-NOT-BYOK: the project's BYOK rerank model_ref + owner are threaded
    # to the reranker (a swap/drop would fail here), not a hardcoded model name.
    _, kwargs = rr.rerank.await_args
    assert kwargs["model_ref"] == "33333333-3333-3333-3333-333333333333"
    assert kwargs["model_source"] == "user_model"
    assert kwargs["user_id"] == str(_USER)
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
def test_rerank_skipped_when_project_has_no_rerank_model(mock_embed, mock_find):
    # D-RERANK-NOT-BYOK: rerank is BYOK + OPTIONAL. A project with no rerank_model
    # ⇒ skip the rerank step (degraded marker), never call the reranker — no
    # hardcoded platform fallback. (Patches target retriever — wiki-llm M2 moved
    # the fusion core to app.search.retriever; raw_search delegates to it.)
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, _ = _make_client(project=_project(rerank_model=None))
    rr = _override_reranker(return_value=[{"index": 0, "relevance_score": 0.9}])
    body = client.get(_url("hybrid")).json()
    rr.rerank.assert_not_awaited()
    assert body["degraded"].get("rerank") == "not_configured"
    assert len(body["results"]) == 2  # both legs retained, unreranked


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


# ── D-RAWSEARCH-CANON-WIRING: surface param + owner-only drafts ───────────


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_owner_surface_all_passes_through_to_both_legs(mock_embed, mock_find):
    # caller (_USER) == project.user_id (owner) → surface=all honoured.
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    resp = client.get(_url("hybrid") + "&surface=all")
    assert resp.status_code == 200, resp.json()
    assert book_client.lexical_search.await_args.kwargs["surface"] == "all"
    assert mock_find.await_args.kwargs["include_drafts"] is True


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_collaborator_surface_all_downgraded_to_canon(mock_embed, mock_find):
    # A collaborator searches the OWNER's project (resolve-to-owner) so
    # caller != project.user_id → surface=all is silently downgraded to canon:
    # unpublished drafts are the owner's private workspace.
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit()]
    client, _, book_client = _make_client()
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: uuid4()  # not the owner
    resp = client.get(_url("hybrid") + "&surface=all")
    assert resp.status_code == 200, resp.json()
    assert book_client.lexical_search.await_args.kwargs["surface"] == "canon"
    assert mock_find.await_args.kwargs["include_drafts"] is False


def test_bad_surface_rejected():
    client, _, _ = _make_client()
    assert client.get(_url("hybrid") + "&surface=secret").status_code == 422


# ── D-RAWSEARCH-CANON-WIRING: index-drafts endpoint ──────────────────────


def _drafts_url():
    return f"/v1/knowledge/books/{_BOOK}/index-drafts"


def test_index_drafts_owner_indexes_draft_chapters():
    from app.extraction.passage_ingester import IngestResult
    client, _, book_client = _make_client()  # default _OwnerGrant ⇒ OWNER
    cid = uuid4()
    book_client.list_chapters = AsyncMock(return_value=[
        {"chapter_id": str(cid), "sort_order": 4, "editorial_status": "draft"},
    ])
    ingest = AsyncMock(return_value=IngestResult(chunks_created=3, chunks_skipped=0))
    with patch("app.routers.public.raw_search.settings.neo4j_uri", "bolt://x"), \
         patch("app.db.neo4j.neo4j_session", new=lambda: _noop_session()), \
         patch("app.extraction.passage_ingester.ingest_chapter_passages", ingest):
        resp = client.post(_drafts_url())
    assert resp.status_code == 200, resp.json()
    assert resp.json() == {"indexed": 1, "skipped": 0, "chapters": 1}
    # enumerated drafts only, ingested as live-draft (revision_id=None) + canon=False.
    assert book_client.list_chapters.await_args.kwargs["editorial_status"] == "draft"
    assert ingest.await_args.kwargs["canon"] is False
    assert ingest.await_args.kwargs["revision_id"] is None
    assert ingest.await_args.kwargs["chapter_index"] == 4


def test_index_drafts_zero_chunks_counts_as_skipped():
    from app.extraction.passage_ingester import IngestResult
    client, _, book_client = _make_client()
    book_client.list_chapters = AsyncMock(return_value=[
        {"chapter_id": str(uuid4()), "sort_order": 1},
    ])
    ingest = AsyncMock(return_value=IngestResult(chunks_created=0, chunks_skipped=0))
    with patch("app.routers.public.raw_search.settings.neo4j_uri", "bolt://x"), \
         patch("app.db.neo4j.neo4j_session", new=lambda: _noop_session()), \
         patch("app.extraction.passage_ingester.ingest_chapter_passages", ingest):
        resp = client.post(_drafts_url())
    assert resp.json() == {"indexed": 0, "skipped": 1, "chapters": 1}


def test_index_drafts_collaborator_forbidden():
    client, _, _ = _make_client()
    from app.main import app
    from app.deps import get_grant_client
    from app.clients.grant_client import GrantLevel

    class _Edit:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.EDIT

    app.dependency_overrides[get_grant_client] = lambda: _Edit()
    resp = client.post(_drafts_url())
    assert resp.status_code == 403
    assert resp.json()["detail"] == "owner_only"


def test_index_drafts_non_grantee_404():
    client, _, _ = _make_client()
    from app.main import app
    from app.deps import get_grant_client
    from app.clients.grant_client import GrantLevel

    class _None:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.NONE

    app.dependency_overrides[get_grant_client] = lambda: _None()
    resp = client.post(_drafts_url())
    assert resp.status_code == 404
    assert resp.json()["detail"] == "not_indexed"


def test_index_drafts_unindexed_project_409():
    client, _, _ = _make_client(
        project=_project(embedding_model=None, embedding_dimension=None),
    )
    with patch("app.routers.public.raw_search.settings.neo4j_uri", "bolt://x"):
        resp = client.post(_drafts_url())
    assert resp.status_code == 409
    assert resp.json()["detail"] == "project_not_indexed"


def test_index_drafts_book_service_unavailable_502():
    client, _, book_client = _make_client()
    book_client.list_chapters = AsyncMock(return_value=None)
    with patch("app.routers.public.raw_search.settings.neo4j_uri", "bolt://x"):
        resp = client.post(_drafts_url())
    assert resp.status_code == 502


# ── W11-M1 (spec §4.3) — reader spoiler cutoff wiring at the endpoint seam ────
# The two halves are unit-tested apart (resolve_before_sort_order in
# test_spoiler_window; the per-leg filter in test_retriever). These pin the SEAM:
# the endpoint reads before_chapter_id, resolves it, and threads it through.
_CUTOFF_CH = uuid4()


def _url_cutoff(chapter_id, mode="hybrid", query="duel"):
    return f"/v1/knowledge/books/{_BOOK}/search?query={query}&mode={mode}&before_chapter_id={chapter_id}"


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_before_chapter_id_drops_future_chapters(mock_embed, mock_find):
    # Reader's furthest chapter resolves to sort_order 5. The semantic hit is
    # chapter 9 (future → dropped); the lexical hit is chapter 3 (kept).
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]  # chapter_index=9
    client, _, book_client = _make_client()  # lexical _lex_hit sortOrder=3
    book_client.get_chapter_sort_orders = AsyncMock(return_value={_CUTOFF_CH: 5})
    resp = client.get(_url_cutoff(_CUTOFF_CH))
    assert resp.status_code == 200, resp.json()
    surfaces = {h["surface"] for h in resp.json()["results"]}
    assert surfaces == {"draft"}  # the chapter-9 canon (semantic) hit is gone
    book_client.get_chapter_sort_orders.assert_awaited_once_with([_CUTOFF_CH])


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_before_chapter_id_unresolvable_fails_closed(mock_embed, mock_find):
    # book-service can't resolve the reader's chapter ({}) → endpoint-level
    # fail-closed: ZERO hits, never the whole corpus.
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, book_client = _make_client()
    book_client.get_chapter_sort_orders = AsyncMock(return_value={})  # unresolvable
    resp = client.get(_url_cutoff(_CUTOFF_CH))
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
def test_before_chapter_id_omitted_is_author_path(mock_embed, mock_find):
    # No cutoff → author behavior: both surfaces present, and the resolver is
    # never even called (no needless book-service round-trip).
    mock_embed.return_value = [0.1] * 1024
    mock_find.return_value = [_passage_hit(0, 0.9)]
    client, _, book_client = _make_client()
    book_client.get_chapter_sort_orders = AsyncMock(return_value={_CUTOFF_CH: 5})
    resp = client.get(_url("hybrid"))  # no before_chapter_id
    assert resp.status_code == 200
    assert {h["surface"] for h in resp.json()["results"]} == {"draft", "canon"}
    book_client.get_chapter_sort_orders.assert_not_awaited()
