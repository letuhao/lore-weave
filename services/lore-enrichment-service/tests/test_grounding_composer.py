"""Grounding composition tests (de-bias C2 / slice 0c, T1-T3).

Pure / fake-client — no live stack. Covers the composer (merge/dedup/top-K/score
order/provider-degrade), the glossary-canon provider, the knowledge-context
provider, and the <passages> parser.
"""

from __future__ import annotations

import pytest

from app.retrieval.grounding import (
    compose_grounding,
    make_glossary_canon_provider,
    make_knowledge_context_provider,
    parse_context_passages,
)
from app.retrieval.strategy import GroundingRef
from app.strategies.base import StrategyContext

_CTX = StrategyContext(user_id="u", project_id="p")


def _ref(corpus, excerpt, score, i=0):
    return GroundingRef(corpus_id=corpus, chunk_id=f"{corpus}:{i}", chunk_index=i,
                        excerpt=excerpt, score=score)


# ── <passages> parser ───────────────────────────────────────────────────────

def test_parse_context_passages():
    block = (
        '<context>\n  <passages>\n'
        '    <passage source_type="chapter" source_id="c1" score="0.85">\n'
        '      姜子牙渭水垂钓，遇文王。\n    </passage>\n'
        '    <passage source_type="chapter" source_id="c2" score="0.40">\n'
        '      封神台前，姜子牙执打神鞭。\n    </passage>\n'
        '  </passages>\n</context>'
    )
    out = parse_context_passages(block)
    assert len(out) == 2
    assert out[0] == ("姜子牙渭水垂钓，遇文王。", 0.85)
    assert out[1][1] == 0.40


def test_parse_context_passages_unescapes_and_handles_empty():
    assert parse_context_passages("") == []
    assert parse_context_passages("<context><entities/></context>") == []  # no passages block
    esc = '<passages><passage score="0.5">a &amp; b &lt;x&gt;</passage></passages>'
    assert parse_context_passages(esc) == [("a & b <x>", 0.5)]


# ── compose_grounding ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compose_merges_dedups_and_top_k():
    base = [_ref("corpus", "shared passage", 0.30), _ref("corpus", "corpus-only", 0.20)]

    async def canon(name, missing, ctx):
        return [_ref("glossary:canon", "the authored canon desc", 1.0)]

    async def knowledge(name, missing, ctx):
        # one NEW passage + a DUP of the corpus "shared passage" (different score)
        return [_ref("knowledge:context", "kg passage", 0.90),
                _ref("knowledge:context", "shared passage", 0.88)]

    out = await compose_grounding(
        base, [canon, knowledge], canonical_name="姜子牙", missing_labels=["历史"],
        context=_CTX, top_k=3,
    )
    excerpts = [r.excerpt for r in out]
    assert "shared passage" in excerpts                      # dedup kept ONE
    assert excerpts.count("shared passage") == 1
    assert excerpts[0] == "the authored canon desc"          # score 1.0 first
    assert "kg passage" in excerpts                          # 0.90
    assert len(out) == 3                                     # top-K


@pytest.mark.asyncio
async def test_compose_dedup_keeps_higher_score():
    # review #3: a knowledge passage (0.90) duplicating a low-score corpus chunk
    # (0.20) keeps the HIGHER score, not the first/lower one.
    base = [_ref("corpus", "dup passage", 0.20)]

    async def knowledge(name, missing, ctx):
        return [_ref("knowledge:context", "dup passage", 0.90)]

    out = await compose_grounding(
        base, [knowledge], canonical_name="X", missing_labels=[], context=_CTX, top_k=5,
    )
    assert len(out) == 1
    assert out[0].score == 0.90  # higher-score duplicate won


@pytest.mark.asyncio
async def test_compose_provider_error_is_skipped_not_fatal():
    base = [_ref("corpus", "base", 0.5)]

    async def boom(name, missing, ctx):
        raise RuntimeError("knowledge down")

    out = await compose_grounding(
        base, [boom], canonical_name="X", missing_labels=[], context=_CTX, top_k=5,
    )
    assert [r.excerpt for r in out] == ["base"]  # degraded, base survives


@pytest.mark.asyncio
async def test_compose_empty_everything():
    async def empty(name, missing, ctx):
        return []
    out = await compose_grounding([], [empty], canonical_name="X", missing_labels=[],
                                  context=_CTX, top_k=5)
    assert out == []


# ── glossary canon provider ────────────────────────────────────────────────

class _FakeGlossary:
    def __init__(self, entities):
        self._entities = entities
        self.calls = 0

    async def list_entities(self, *, book_id, limit=100):
        self.calls += 1
        return self._entities


@pytest.mark.asyncio
async def test_canon_provider_returns_description_and_caches():
    from types import SimpleNamespace
    g = _FakeGlossary([SimpleNamespace(name="姜子牙", description="封神主帅，渭水垂钓。")])
    prov = make_glossary_canon_provider(g, book_id="b")
    out = await prov("姜子牙", ["历史"], _CTX)
    assert len(out) == 1 and out[0].excerpt == "封神主帅，渭水垂钓。"
    assert out[0].corpus_id == "glossary:canon" and out[0].score == 1.0
    await prov("姜子牙", [], _CTX)
    assert g.calls == 1  # cached after first read

    assert await prov("不存在", [], _CTX) == []  # unknown entity → []


@pytest.mark.asyncio
async def test_canon_provider_noop_without_scope():
    prov = make_glossary_canon_provider(None, book_id=None)
    assert await prov("姜子牙", [], _CTX) == []


# ── knowledge context provider ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_knowledge_provider_parses_passages():
    block = '<passages><passage score="0.7">姜子牙佐周伐纣。</passage></passages>'

    async def build_ctx(message, context):
        assert "姜子牙" in message and "历史" in message  # query = name + dim labels
        return block

    prov = make_knowledge_context_provider(build_ctx)
    out = await prov("姜子牙", ["历史"], _CTX)
    assert len(out) == 1
    assert out[0].corpus_id == "knowledge:context"
    assert out[0].excerpt == "姜子牙佐周伐纣。" and out[0].score == 0.7


@pytest.mark.asyncio
async def test_knowledge_provider_empty_context_degrades():
    async def build_ctx(message, context):
        return ""  # extraction-disabled / no passages
    prov = make_knowledge_context_provider(build_ctx)
    assert await prov("姜子牙", [], _CTX) == []
