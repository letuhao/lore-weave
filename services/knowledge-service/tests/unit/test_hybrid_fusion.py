"""Raw-search Phase 2 — unit tests for the pure RRF fusion + per-chapter cap."""

from __future__ import annotations

from app.search.hybrid_fusion import (
    DEFAULT_LANG_PREF_WEIGHT,
    apply_language_preference,
    apply_relevance_floor,
    cap_per_chapter,
    normalize_lang,
    rrf_fuse,
)


def _h(chapter: str, surface: str, pos: int, score: float = 0.0,
       relevance: float | None = None) -> dict:
    loc = {"blockIndex": pos} if surface == "draft" else {"chunkIndex": pos}
    h = {"chapterId": chapter, "surface": surface, "score": score, "location": loc}
    if relevance is not None:
        h["relevance"] = relevance
    return h


def _lh(chapter: str, score: float, lang: str) -> dict:
    """A fused hit carrying a sourceLang, for language-preference tests."""
    return {"chapterId": chapter, "surface": "canon", "score": score,
            "sourceLang": lang, "location": {"chunkIndex": 0}}


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


# ── E5: relevance survives fusion + score-floor ──────────────────────


def test_rrf_preserves_relevance_field():
    # the native `relevance` must survive RRF (which only rewrites `score`)
    fused = rrf_fuse([[_h("a", "draft", 0, score=1.5, relevance=0.8)]])
    assert fused[0]["relevance"] == 0.8
    assert fused[0]["score"] == round(1.0 / 61, 6)  # score replaced, relevance kept


def test_relevance_floor_drops_low_hits():
    hits = [_h("a", "canon", 0, relevance=0.9), _h("b", "canon", 1, relevance=0.2)]
    kept = apply_relevance_floor(hits, 0.3)
    assert [h["chapterId"] for h in kept] == ["a"]


def test_relevance_floor_missing_field_passes_through():
    # a hit without `relevance` is treated as 1.0 → never silently nuked
    hits = [_h("a", "draft", 0)]  # no relevance key
    assert apply_relevance_floor(hits, 0.5) == hits


def test_relevance_floor_zero_is_noop():
    hits = [_h("a", "canon", 0, relevance=0.01)]
    assert apply_relevance_floor(hits, 0.0) == hits


# ── KG-ML M4: soft language-preference boost ─────────────────────────


def test_normalize_lang_primary_subtag():
    assert normalize_lang("zh-Hant") == "zh"
    assert normalize_lang("en_US") == "en"
    assert normalize_lang("VI") == "vi"
    assert normalize_lang("  ") == ""
    assert normalize_lang(None) == ""
    assert normalize_lang("unknown") == ""
    assert normalize_lang("mixed") == "mixed"


def test_lang_pref_none_is_noop():
    hits = [_lh("a", 0.02, "zh"), _lh("b", 0.01, "vi")]
    out = apply_language_preference(list(hits), None)
    assert [h["chapterId"] for h in out] == ["a", "b"]  # untouched order
    assert "langMatch" not in out[0]  # no annotation when disabled


def test_lang_pref_boosts_matching_above_higher_fused():
    # b (vi, fused 0.01) should leapfrog a (zh, fused 0.02) for a vi reader,
    # because the boost (~0.0164) exceeds the 0.01 fused gap.
    hits = [_lh("a", 0.02, "zh"), _lh("b", 0.01, "vi")]
    out = apply_language_preference(hits, "vi")
    assert out[0]["chapterId"] == "b"
    assert out[0]["langMatch"] is True
    assert out[0]["fusedScore"] == 0.01  # original RRF preserved
    assert out[0]["score"] == round(0.01 + DEFAULT_LANG_PREF_WEIGHT, 6)
    assert out[1]["langMatch"] is False


def test_lang_pref_does_not_filter_offlanguage():
    # soft, not hard: a zh-only result set still surfaces for a vi reader.
    hits = [_lh("a", 0.02, "zh"), _lh("b", 0.01, "zh")]
    out = apply_language_preference(hits, "vi")
    assert {h["chapterId"] for h in out} == {"a", "b"}
    assert all(h["langMatch"] is False for h in out)
    assert [h["chapterId"] for h in out] == ["a", "b"]  # fused order intact


def test_lang_pref_mixed_matches_any():
    hits = [_lh("a", 0.02, "zh"), _lh("b", 0.01, "mixed")]
    out = apply_language_preference(hits, "vi")
    assert out[0]["chapterId"] == "b"  # mixed boosted for a vi reader
    assert out[0]["langMatch"] is True


def test_lang_pref_regional_variant_matches():
    # reader pref "zh-Hant" normalizes to "zh" and matches a "zh" passage.
    hits = [_lh("a", 0.01, "zh"), _lh("b", 0.02, "en")]
    out = apply_language_preference(hits, "zh-Hant")
    assert out[0]["chapterId"] == "a"
    assert out[0]["langMatch"] is True


def test_lang_pref_tiebreak_prefers_match_then_fused():
    # equal post-boost is impossible here; verify the deterministic sort key:
    # match first, then fused score. Two vi hits keep fused order.
    hits = [_lh("a", 0.01, "vi"), _lh("b", 0.02, "vi")]
    out = apply_language_preference(hits, "vi")
    assert [h["chapterId"] for h in out] == ["b", "a"]  # both matched → fused order


def test_hit_key_keeps_distinct_chunks_sharing_a_block_index():
    # P3-C/MED-1: two distinct semantic passages can share a block_index
    # (one oversized paragraph → several chunks). The dedup key must use the
    # UNIQUE chunkIndex, not blockIndex, or fusion drops one of them.
    h1 = {"chapterId": "a", "surface": "canon", "score": 0.0,
          "location": {"chunkIndex": 0, "blockIndex": 3}}
    h2 = {"chapterId": "a", "surface": "canon", "score": 0.0,
          "location": {"chunkIndex": 1, "blockIndex": 3}}
    fused = rrf_fuse([[h1, h2]])
    assert len(fused) == 2  # both kept (keyed on chunkIndex, not block 3)
