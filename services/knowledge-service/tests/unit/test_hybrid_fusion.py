"""Raw-search Phase 2 — unit tests for the pure RRF fusion + per-chapter cap."""

from __future__ import annotations

from app.search.hybrid_fusion import cap_per_chapter, rrf_fuse


def _h(chapter: str, surface: str, pos: int, score: float = 0.0) -> dict:
    loc = {"blockIndex": pos} if surface == "draft" else {"chunkIndex": pos}
    return {"chapterId": chapter, "surface": surface, "score": score, "location": loc}


def test_rrf_combines_legs_distinct_keys():
    lex = [_h("a", "draft", 0), _h("b", "draft", 1)]
    sem = [_h("c", "canon", 0), _h("a", "canon", 0)]  # a/canon distinct from a/draft
    fused = rrf_fuse([lex, sem])
    assert len(fused) == 4
    # sorted descending by RRF score
    scores = [h["score"] for h in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_same_key_in_both_legs_ranks_top():
    # (a, draft, 0) appears rank-0 in BOTH legs → highest fused score.
    legs = [
        [_h("a", "draft", 0), _h("b", "draft", 1)],
        [_h("a", "draft", 0), _h("c", "draft", 1)],
    ]
    fused = rrf_fuse(legs)
    assert fused[0]["chapterId"] == "a"
    assert fused[0]["surface"] == "draft"
    # 3 distinct keys (a appears once, deduped)
    assert len(fused) == 3


def test_rrf_replaces_score_with_fused_value():
    fused = rrf_fuse([[_h("a", "draft", 0, score=99.0)]])
    assert fused[0]["score"] == round(1.0 / 61, 6)  # not the original 99.0


def test_cap_per_chapter_limits_flooding():
    hits = [
        _h("a", "draft", 0), _h("a", "draft", 1), _h("a", "draft", 2),
        _h("a", "draft", 3), _h("b", "draft", 0),
    ]
    capped = cap_per_chapter(hits, cap=2)
    assert sum(1 for h in capped if h["chapterId"] == "a") == 2
    assert any(h["chapterId"] == "b" for h in capped)


def test_rrf_empty_legs():
    assert rrf_fuse([[], []]) == []
