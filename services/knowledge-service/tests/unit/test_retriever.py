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
from app.search.retriever import (
    RetrievalResult,
    _visible_within_window,
    passage_to_hit,
    run_hybrid_search,
)

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


def _passage_hit(chunk_index=0, score=0.9, source_lang="unknown",
                 source_id="ch-canon", chapter_index=9) -> PassageSearchHit:
    p = Passage(
        id=f"pg-{source_lang}-{chunk_index}", user_id=str(_USER), project_id=str(_PROJECT_ID),
        source_type="chapter", source_id=source_id, chunk_index=chunk_index,
        text="canon prose", embedding_model="bge-m3", is_hub=False, chapter_index=chapter_index,
        source_lang=source_lang,
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


@pytest.fixture(autouse=True)
def _stub_cjk_leg():
    """KG-ML M6 — the CJK full-text leg fires for CJK queries (most tests here use
    '姜子牙'). Stub it to [] by default so existing assertions see it as an additive
    empty leg; the M6 fusion test overrides the return value."""
    with patch(
        "app.search.retriever.find_passages_by_fulltext", new_callable=AsyncMock
    ) as m:
        m.return_value = []
        yield m


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
    # No user-level default rerank model by default; tests override to exercise the
    # project-unset → user-default fallback.
    rr.get_default_rerank = AsyncMock(return_value=None)
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


# ── W11-M1 (spec §4.3) — reader spoiler cutoff over the RAG passage axis ─────
def test_visible_within_window_predicate():
    # (lexical hit dicts) visible: at or before the reader's cutoff chapter
    assert _visible_within_window({"sortOrder": 3}, 5) is True
    assert _visible_within_window({"sortOrder": 5}, 5) is True   # inclusive
    # future chapter → hidden (the spoiler)
    assert _visible_within_window({"sortOrder": 6}, 5) is False
    # fail-closed: an unresolvable reading position (-1) admits NOTHING
    assert _visible_within_window({"sortOrder": 0}, -1) is False
    # a hit with no/non-int sortOrder is not admitted on its own claim
    assert _visible_within_window({}, 5) is False
    assert _visible_within_window({"sortOrder": None}, 5) is False


def test_window_raw_passages_drops_unknown_and_future():
    from app.search.retriever import _window_raw_passages
    visible = _passage_hit(chunk_index=0, chapter_index=3)      # read
    future = _passage_hit(chunk_index=1, chapter_index=9)       # not reached
    unknown = _passage_hit(chunk_index=2, chapter_index=None)   # un-ordered canon passage
    # cutoff 5 → keep only the chapter-3 passage; future AND unknown are dropped
    kept = _window_raw_passages([visible, future, unknown], 5)
    assert [h.passage.chapter_index for h in kept] == [3]
    # no cutoff → all pass (author/wiki path)
    assert len(_window_raw_passages([visible, future, unknown], None)) == 3
    # unresolvable position → nothing
    assert _window_raw_passages([visible, future, unknown], -1) == []


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_before_sort_order_drops_future_chapters(embed, find):
    # semantic hit is chapter 9 (a future chapter for a reader at chapter 5);
    # lexical hit is chapter 3 (already read). The cutoff must drop the future one.
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]  # chapter_index=9 → sortOrder 9
    book, emb, rr = _clients(lex_hits=[_lex_hit()])  # sortOrder 3
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        before_sort_order=5,
    )
    surfaces = {h["surface"] for h in out.hits}
    assert surfaces == {"draft"}  # only the chapter-3 (lexical/draft) hit survives
    assert all(h["sortOrder"] <= 5 for h in out.hits)


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_before_sort_order_fail_closed_returns_nothing(embed, find):
    # An unresolvable reading position (-1) must yield NO hits — a reader whose
    # position can't be pinned sees nothing, never the whole book.
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        before_sort_order=-1,
    )
    assert out.hits == []


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_before_sort_order_drops_unknown_chapter_canon_passage(embed, find):
    # THE FAIL-OPEN THE REVIEW CAUGHT: a canon passage whose chapter_index is None
    # (un-ordered at publish — book-service returned {} for sort_orders) must be
    # DROPPED under a reader cutoff, NOT coerced to sortOrder 0 and leaked as if it
    # were chapter 0. Before the fix this passage surfaced for every reader.
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit(chapter_index=None)]  # unknown-position canon
    book, emb, rr = _clients(lex_hits=[])  # no lexical hits; only the None passage
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        before_sort_order=5,
    )
    assert out.hits == []  # the unknown-chapter passage is NOT visible to the reader


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_no_cutoff_is_unchanged_author_behavior(embed, find):
    # Omitting the cutoff (None) is the author/wiki path — both chapters present.
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
    )
    assert {h["surface"] for h in out.hits} == {"draft", "canon"}


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


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_no_project_rerank_falls_back_to_user_default(embed, find):
    # Project has NO per-project rerank model, but the user has a DEFAULT rerank
    # model (provider-registry user_default_models) → rerank runs with it.
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    rr.get_default_rerank = AsyncMock(return_value="44444444-4444-4444-4444-444444444444")
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(rerank_model=None),
        book_client=book, embedding_client=emb, reranker_client=rr,
    )
    rr.get_default_rerank.assert_awaited_once()
    rr.rerank.assert_awaited()  # ran via the user-default model
    # the resolved default model_ref is passed through to the rerank call
    assert rr.rerank.await_args.kwargs["model_ref"] == "44444444-4444-4444-4444-444444444444"
    assert "rerank" not in out.degraded


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_no_rerank_anywhere_marks_not_configured(embed, find):
    # No per-project model AND no user default → skip rerank, mark degraded.
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]
    book, emb, rr = _clients(lex_hits=[_lex_hit()])  # get_default_rerank → None
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(rerank_model=None),
        book_client=book, embedding_client=emb, reranker_client=rr,
    )
    rr.rerank.assert_not_awaited()
    assert out.degraded.get("rerank") == "not_configured"


# ── D-RAWSEARCH-CANON-WIRING ────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_surface_canon_default_excludes_drafts_both_legs(embed, find):
    """Default surface=canon → semantic include_drafts=False AND lexical surface=canon
    (the latter was previously unset → book-service defaulted to draft, a leak)."""
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
    )
    assert find.await_args.kwargs["include_drafts"] is False
    assert book.lexical_search.await_args.kwargs["surface"] == "canon"


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_surface_all_includes_drafts_both_legs(embed, find):
    """surface=all → semantic include_drafts=True AND lexical surface=all."""
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit()]
    book, emb, rr = _clients(lex_hits=[_lex_hit()])
    await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        surface="all",
    )
    assert find.await_args.kwargs["include_drafts"] is True
    assert book.lexical_search.await_args.kwargs["surface"] == "all"


# ── KG-ML M4: language-aware retrieval ──────────────────────────────────────


def test_passage_to_hit_carries_source_lang():
    p = Passage(
        id="p", user_id=str(_USER), source_type="chapter", source_id="ch1",
        chunk_index=0, text="t", source_lang="vi",
    )
    assert passage_to_hit(PassageSearchHit(passage=p, raw_score=0.9))["sourceLang"] == "vi"


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_pref_lang_orders_matching_first_rerank_off(embed, find):
    """A vi reader's pref lifts the vi passage above the zh one (rerank OFF)."""
    embed.return_value = [0.1] * 1024
    find.return_value = [
        _passage_hit(source_lang="zh", source_id="ch-zh"),
        _passage_hit(source_lang="vi", source_id="ch-vi"),
    ]
    book, emb, rr = _clients(lex_hits=None)
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="Dracula", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        mode="semantic", rerank=False, pref_lang="vi",
    )
    assert out.hits[0]["sourceLang"] == "vi"
    assert out.hits[0]["langMatch"] is True
    rr.rerank.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_pref_lang_survives_rerank(embed, find):
    """/review-impl HIGH regression — the language preference is the FINAL pass,
    so it survives the cross-encoder rerank (which re-sorts the whole pool by its
    own relevance and would otherwise discard a pre-rerank boost). Rerank is ON
    (project has a model + passthrough reranker); a vi reader still gets vi #0."""
    embed.return_value = [0.1] * 1024
    # rerank passthrough scores in input order (0.9, 0.85, …) → without the final
    # language pass, the zh passage (returned first) would stay #0.
    find.return_value = [
        _passage_hit(source_lang="zh", source_id="ch-zh"),
        _passage_hit(source_lang="vi", source_id="ch-vi"),
    ]
    book, emb, rr = _clients(lex_hits=None)  # rerank passthrough (default)
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="Dracula", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        mode="semantic", rerank=True, pref_lang="vi",
    )
    rr.rerank.assert_awaited()  # rerank really ran
    assert out.hits[0]["sourceLang"] == "vi"
    assert out.hits[0]["langMatch"] is True
    # soft, not a filter: the zh passage still present, just after
    assert {h["sourceLang"] for h in out.hits} == {"vi", "zh"}


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_pref_lang_wins_per_chapter_cap_under_rerank(embed, find):
    """The language pass runs BEFORE the per-chapter cap, so for a chapter with
    both a vi and an en passage (same chapterId), the vi one wins the single
    chapter=granularity slot for a vi reader — even with rerank on."""
    embed.return_value = [0.1] * 1024
    find.return_value = [  # SAME source_id → one chapter, two languages
        _passage_hit(chunk_index=0, source_lang="en", source_id="ch-1"),
        _passage_hit(chunk_index=1, source_lang="vi", source_id="ch-1"),
    ]
    book, emb, rr = _clients(lex_hits=None)
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="Dracula", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        mode="semantic", granularity="chapter", rerank=True, pref_lang="vi",
    )
    assert len(out.hits) == 1  # cap=1 per chapter
    assert out.hits[0]["sourceLang"] == "vi"


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_no_pref_lang_leaves_order_unboosted(embed, find):
    """pref_lang=None (wiki path / no reader pref) → no langMatch annotation."""
    embed.return_value = [0.1] * 1024
    find.return_value = [
        _passage_hit(score=0.95, source_lang="zh", source_id="ch-zh"),
        _passage_hit(score=0.80, source_lang="vi", source_id="ch-vi"),
    ]
    book, emb, rr = _clients(lex_hits=None)
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="Dracula", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr,
        mode="semantic", rerank=False,  # pref_lang defaults None
    )
    assert all("langMatch" not in h for h in out.hits)
    assert out.hits[0]["sourceLang"] == "zh"  # higher cosine wins, unboosted


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_cjk_query_runs_cjk_lexical_leg(embed, find, _stub_cjk_leg):
    """KG-ML M6 — a CJK query fuses the cjk full-text leg; its passage shows up
    even when lexical (trigram) + semantic legs are empty."""
    embed.return_value = [0.1] * 1024
    find.return_value = []  # semantic empty
    _stub_cjk_leg.return_value = [_passage_hit(source_lang="zh", source_id="ch-zh")]
    book, emb, rr = _clients(lex_hits=[])  # trigram empty
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="姜子牙", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr, rerank=False,
    )
    _stub_cjk_leg.assert_awaited_once()
    zh_hits = [h for h in out.hits if h["sourceLang"] == "zh"]
    assert zh_hits
    # KG-ML M6 (D-KG-ML-M6-MATCHTYPE cleared) — cjk-leg hits label "lexical",
    # not the passage default "semantic".
    assert all(h["matchType"] == "lexical" for h in zh_hits)


@pytest.mark.asyncio
@patch("app.search.retriever.find_passages_by_vector", new_callable=AsyncMock)
@patch("app.search.retriever.neo4j_session", new=lambda: _noop_session())
@patch("app.search.retriever.embed_query_cached", new_callable=AsyncMock)
async def test_latin_query_skips_cjk_leg(embed, find, _stub_cjk_leg):
    """A Latin-script query never invokes the cjk leg — pre-M6 behavior is
    byte-identical for non-CJK retrieval (the leg is pure overhead otherwise)."""
    embed.return_value = [0.1] * 1024
    find.return_value = [_passage_hit(source_lang="en", source_id="ch-en")]
    book, emb, rr = _clients(lex_hits=[])
    out = await run_hybrid_search(
        user_id=_USER, book_id=_BOOK, query="Dracula", project=_project(),
        book_client=book, embedding_client=emb, reranker_client=rr, rerank=False,
    )
    _stub_cjk_leg.assert_not_called()
    assert "cjk_lexical" not in out.degraded


def test_passage_to_hit_surface_reflects_canon_flag():
    """passage_to_hit labels surface from the node's canon flag, not a hardcode."""
    canon_p = Passage(
        id="c", user_id=str(_USER), source_type="chapter", source_id="ch1",
        chunk_index=0, text="t", canon=True,
    )
    draft_p = Passage(
        id="d", user_id=str(_USER), source_type="chapter", source_id="ch2",
        chunk_index=0, text="t", canon=False,
    )
    assert passage_to_hit(PassageSearchHit(passage=canon_p, raw_score=0.9))["surface"] == "canon"
    assert passage_to_hit(PassageSearchHit(passage=draft_p, raw_score=0.9))["surface"] == "draft"
