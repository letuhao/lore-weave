"""mui #3 G3-SDK — GroundingCite + merge/compose + adapters."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from loreweave_grounding import (
    GroundingCite,
    compose_cites,
    from_glossary_evidence,
    from_grounding_ref,
    from_l3_passage,
    merge_cites,
)


def _c(text, score, source_id="s"):
    return GroundingCite(source_type="chapter", source_id=source_id, text=text, score=score)


def test_merge_dedupes_by_text_keeping_higher_score():
    a = _c("  Jiang  Ziya  ", 0.4, "a")   # same text (normalized) as b, lower score
    b = _c("jiang ziya", 0.9, "b")
    out = merge_cites([a, b], top_k=10)
    assert len(out) == 1
    assert out[0].source_id == "b"  # higher score kept


def test_merge_sorts_score_desc_authored_canon_first():
    scored_lo = _c("x", 0.2, "lo")
    scored_hi = _c("y", 0.8, "hi")
    canon = _c("z", None, "canon")  # None = authored canon → ranks first
    out = merge_cites([scored_lo, scored_hi, canon], top_k=10)
    assert [c.source_id for c in out] == ["canon", "hi", "lo"]


def test_merge_top_k_and_stable_ties():
    # two equal-score cites keep insertion order (stable), top_k truncates
    out = merge_cites(
        [_c("a", 0.5, "a"), _c("b", 0.5, "b"), _c("c", 0.5, "c")], top_k=2
    )
    assert [c.source_id for c in out] == ["a", "b"]


def test_merge_drops_empty_text():
    out = merge_cites([_c("   ", 0.9, "blank"), _c("real", 0.1, "real")], top_k=10)
    assert [c.source_id for c in out] == ["real"]


@pytest.mark.asyncio
async def test_compose_best_effort_skips_failing_provider():
    base = [_c("base", 0.5, "base")]

    async def good():
        return [_c("extra", 0.9, "extra")]

    async def bad():
        raise RuntimeError("provider down")

    out = await compose_cites(base, [good, bad], top_k=10)
    ids = {c.source_id for c in out}
    assert ids == {"base", "extra"}  # bad provider skipped, not fatal


def test_adapter_glossary_evidence_is_authored_canon():
    row = {
        "evidence_id": "e1", "attr_value_id": "av1", "original_text": "canon text",
        "chapter_id": "ch1", "chapter_index": 3, "block_or_line": "line 5",
    }
    cite = from_glossary_evidence(row)
    assert cite.source_type == "glossary_entity"
    assert cite.text == "canon text"
    assert cite.score is None  # authored canon has no relevance rank
    assert cite.block_or_line == "line 5"


def test_adapter_l3_passage_keeps_score():
    p = SimpleNamespace(text="passage", source_type="chapter", source_id="ch9",
                        chunk_index=2, score=0.77, chapter_index=4)
    cite = from_l3_passage(p)
    assert cite.score == 0.77
    assert cite.chapter_index == 4
    assert cite.source_id == "ch9"


def test_adapter_grounding_ref_maps_synthetic_corpus():
    canon_ref = SimpleNamespace(corpus_id="glossary:canon", chunk_id="canon:X",
                                chunk_index=0, excerpt="desc", score=1.0)
    kctx_ref = SimpleNamespace(corpus_id="knowledge:context", chunk_id="kctx:1",
                               chunk_index=1, excerpt="passage", score=0.6)
    real_ref = SimpleNamespace(corpus_id="0192abc", chunk_id="c1",
                               chunk_index=0, excerpt="src", score=0.5)
    assert from_grounding_ref(canon_ref).source_type == "glossary_entity"
    # MED-1: knowledge-context maps to a neutral "knowledge" type, NOT "chapter"
    # (it has no real chapter source_id to resolve).
    assert from_grounding_ref(kctx_ref).source_type == "knowledge"
    assert from_grounding_ref(real_ref).source_type == "corpus"
    assert from_grounding_ref(canon_ref).text == "desc"
