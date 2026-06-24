"""KG-ML M6 (D12) — unit guards for the CJK full-text passage leg.

Infra-free: the live `cjk` index behavior is proven by the live-smoke; these pin
the repo wiring (query escaped, index name, tenant/canon params, blank → no call)
+ the pure helpers (Lucene escape, CJK detection) so a regression is caught with
no live Neo4j.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.db.neo4j_repos.passages import (
    PASSAGE_CJK_FT_INDEX,
    find_passages_by_fulltext,
    lucene_escape,
)
from app.search.retriever import query_has_cjk


# ── pure helpers ───────────────────────────────────────────────────────────
def test_lucene_escape():
    assert lucene_escape("姜子牙") == "姜子牙"  # CJK runs untouched
    assert lucene_escape("a+b") == r"a\+b"
    assert lucene_escape('foo:bar "x"') == r'foo\:bar \"x\"'
    assert lucene_escape("a && b") == r"a \&\& b"
    assert lucene_escape("   ") == ""
    assert lucene_escape(None) == ""


def test_query_has_cjk():
    assert query_has_cjk("姜子牙") is True  # Chinese
    assert query_has_cjk("ナルト") is True  # Katakana
    assert query_has_cjk("홍길동") is True  # Hangul
    assert query_has_cjk("Dracula") is False
    assert query_has_cjk("") is False
    assert query_has_cjk("café 123") is False  # Latin + digits + accent


# ── find_passages_by_fulltext wiring ───────────────────────────────────────
class _Rows:
    """Async-iterable of {p, raw_score} records."""

    def __init__(self, records):
        self._records = records

    def __aiter__(self):
        async def gen():
            for r in self._records:
                yield r
        return gen()


@pytest.mark.asyncio
async def test_find_passages_by_fulltext_wires_query_and_filters(monkeypatch):
    captured: dict = {}

    async def fake_read(session, cypher, **kwargs):
        captured["cypher"] = cypher
        captured["kwargs"] = kwargs
        return _Rows([
            {"p": {"id": "pg-1", "user_id": "u", "source_type": "chapter",
                   "source_id": "ch-1", "chunk_index": 0, "text": "天剑峰",
                   "source_lang": "zh"}, "raw_score": 4.2},
        ])

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_read", fake_read)

    hits = await find_passages_by_fulltext(
        MagicMock(), user_id="u", project_id="p", query="天剑+峰",
        source_type="chapter", limit=5,
    )
    # the index name + escaped query reach the call …
    assert captured["kwargs"]["index_name"] == PASSAGE_CJK_FT_INDEX
    assert captured["kwargs"]["q"] == r"天剑\+峰"  # '+' escaped, CJK kept
    assert captured["kwargs"]["user_id"] == "u"
    assert captured["kwargs"]["project_id"] == "p"
    assert captured["kwargs"]["source_type"] == "chapter"
    # canon gate defaults closed (drafts excluded) …
    assert captured["kwargs"]["include_drafts"] is False
    # … and the row round-trips into a PassageSearchHit.
    assert len(hits) == 1
    assert hits[0].passage.text == "天剑峰"
    assert hits[0].raw_score == 4.2


@pytest.mark.asyncio
async def test_find_passages_by_fulltext_blank_query_no_call(monkeypatch):
    called = {"n": 0}

    async def fake_read(session, cypher, **kwargs):
        called["n"] += 1
        return _Rows([])

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_read", fake_read)

    # whitespace-only and all-special (escapes to empty after strip) → no query
    assert await find_passages_by_fulltext(MagicMock(), user_id="u", project_id="p", query="   ") == []
    assert called["n"] == 0
