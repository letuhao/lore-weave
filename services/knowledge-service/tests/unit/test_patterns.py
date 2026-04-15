"""K15.3 unit tests — per-language pattern sets + dispatch.

Covers:
  - PatternSet compilation for all supported languages
  - get_patterns fallback for unsupported codes
  - detect_primary_language determinism + normalization
  - split_by_language for mixed-content routing
  - Per-language marker matching (smoke)
"""

from __future__ import annotations

import pytest

from app.extraction.patterns import (
    PatternSet,
    SUPPORTED_LANGUAGES,
    detect_primary_language,
    get_patterns,
    split_by_language,
)


# ── PatternSet compilation ────────────────────────────────────────────


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_k15_3_pattern_set_shape(lang: str):
    ps = get_patterns(lang)
    assert isinstance(ps, PatternSet)
    assert ps.language == lang
    # Every category must have at least one compiled pattern
    for field in ("decision", "preference", "milestone", "negation", "skip"):
        patterns = getattr(ps, field)
        assert len(patterns) >= 1, f"{lang}.{field} is empty"
        # Confirm they're compiled, not raw strings
        assert hasattr(patterns[0], "search"), f"{lang}.{field} not compiled"


def test_k15_3_pattern_sets_are_frozen():
    ps = get_patterns("en")
    with pytest.raises(Exception):
        ps.language = "vi"  # type: ignore[misc]


def test_k15_3_get_patterns_unsupported_falls_back_to_english():
    ps = get_patterns("fr")
    assert ps.language == "en"
    ps2 = get_patterns("")
    assert ps2.language == "en"


# ── Language detection ───────────────────────────────────────────────


def test_k15_3_detect_empty_returns_english():
    assert detect_primary_language("") == "en"
    assert detect_primary_language("   ") == "en"


def test_k15_3_detect_english():
    text = "Kai walked into the throne room and bowed to the king."
    assert detect_primary_language(text) == "en"


def test_k15_3_detect_vietnamese():
    text = "Tôi quyết định dùng phương pháp này. Tôi rất thích nó."
    assert detect_primary_language(text) == "vi"


def test_k15_3_detect_chinese_normalizes_to_zh():
    # langdetect returns zh-cn / zh-tw; we normalize to "zh"
    text = "我们决定使用这个方法，因为它更简单。我喜欢这种方式。"
    assert detect_primary_language(text) == "zh"


def test_k15_3_detect_korean():
    text = "나는 이 방법을 사용하기로 결정했다. 정말 좋아한다."
    assert detect_primary_language(text) == "ko"


def test_k15_3_detect_deterministic_across_calls():
    # DetectorFactory.seed = 0 — identical input → identical output
    text = "Kai walked into the throne room."
    results = {detect_primary_language(text) for _ in range(10)}
    assert len(results) == 1


# ── Mixed-content splitting ──────────────────────────────────────────


def test_k15_3_split_empty():
    assert split_by_language("") == []


def test_k15_3_split_single_language():
    # Longer sentences give langdetect enough signal to commit to "en";
    # very short ones may classify as "mixed" which is fine but not
    # what we're testing here.
    text = (
        "Kai walked into the grand throne room slowly. "
        "He bowed deeply before the ancient king. "
        "The old king smiled kindly at the young warrior."
    )
    out = split_by_language(text)
    assert len(out) == 3
    for _, lang in out:
        assert lang == "en"


def test_k15_3_split_mixed_latin_and_cjk():
    text = "Kai entered the hall. 我们决定使用这个方法，因为它更简单。He bowed."
    out = split_by_language(text)
    langs = {lang for _, lang in out}
    # Should contain at least english and chinese
    assert "en" in langs
    assert "zh" in langs


def test_k15_3_r1_split_cjk_sentences_without_whitespace():
    """K15.3-R1: CJK prose uses no inter-sentence whitespace, so
    `(?<=[。！？])\\s+` would merge every Chinese/Japanese sentence
    into one chunk and hide the minority language from dispatch.
    The splitter must break on CJK terminators unconditionally.
    """
    text = "我们决定使用这个方法，因为它更简单。他不知道发生了什么。"
    out = split_by_language(text)
    assert len(out) >= 2, f"CJK terminator under-split: {out}"


def test_k15_3_r1_split_mixed_script_isolates_languages():
    """K15.3-R1: a mixed Latin+CJK paragraph must route each
    sub-sentence to its own language. Before the fix, the CJK
    middle would merge into the trailing Latin sentence and get
    misclassified as English.
    """
    text = (
        "Kai entered the grand throne room slowly. "
        "他不知道发生了什么事情，也不明白为什么所有人都在看着他。"
        "Zhao smiled politely at the visitor."
    )
    out = split_by_language(text)
    # The fix under test is the SPLIT: the CJK middle sentence must
    # be a standalone chunk, not merged with the trailing English.
    # langdetect's CJK classification (zh vs ko via Hanja overlap) is
    # a library quirk outside our control — assert on the split shape,
    # not the exact language label.
    assert len(out) == 3, f"expected 3 chunks, got {out}"
    cjk_chunk = out[1][0]
    assert "他不知道" in cjk_chunk
    assert "Zhao" not in cjk_chunk, "CJK merged with trailing Latin"


def test_k15_3_r2_split_drops_pure_punctuation_chunks():
    """K15.3-R2/I1: pure-punctuation chunks ("...", "!!!???") must
    not surface as result entries. Before the fix, they routed
    through langdetect, raised LangDetectException, fell back to
    "en", and propagated downstream as fake sentences with no
    extractable content.
    """
    out = split_by_language("Hello world. ... Kai walked slowly.")
    chunks = [s for s, _ in out]
    assert "..." not in chunks
    assert all(any(ch.isalpha() for ch in s) for s in chunks), (
        f"letterless chunk survived: {chunks}"
    )

    # Text that is ONLY punctuation collapses to empty result.
    assert split_by_language("...!!!???") == []


def test_k15_3_split_drops_whitespace_chunks():
    text = "Kai walked.     \n\n   Zhao bowed."
    out = split_by_language(text)
    for sentence, _ in out:
        assert sentence.strip() == sentence
        assert sentence != ""


# ── Per-language marker matching (smoke) ─────────────────────────────


def test_k15_3_english_decision_marker_matches():
    ps = get_patterns("en")
    assert any(p.search("let's use the new plan") for p in ps.decision)
    assert any(p.search("We Decided to go back") for p in ps.decision)


def test_k15_3_english_skip_marker_matches_hypothetical():
    ps = get_patterns("en")
    assert any(p.search("If Kai had stayed, he would have won.") for p in ps.skip)


def test_k15_3_vietnamese_preference_matches():
    ps = get_patterns("vi")
    assert any(p.search("tôi thích cách này hơn") for p in ps.preference)


def test_k15_3_chinese_negation_matches():
    ps = get_patterns("zh")
    assert any(p.search("他不知道发生了什么") for p in ps.negation)


def test_k15_3_japanese_milestone_matches():
    ps = get_patterns("ja")
    assert any(p.search("ついに完成した") for p in ps.milestone)


def test_k15_3_korean_decision_matches():
    ps = get_patterns("ko")
    assert any(p.search("이 방법을 쓰기로 했다") for p in ps.decision)


# ── Cross-language isolation ─────────────────────────────────────────


def test_k15_3_english_patterns_do_not_match_chinese():
    """The English `\\bwe decided\\b` must not fire on Chinese text —
    `\\b` uses Unicode word boundaries and could spuriously match
    Latin substrings embedded in CJK. Smoke check."""
    ps = get_patterns("en")
    text = "我们决定使用这个方法。"
    for p in ps.decision:
        assert not p.search(text), f"{p.pattern} matched Chinese text"
