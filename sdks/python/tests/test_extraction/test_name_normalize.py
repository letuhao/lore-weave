"""D-KG-TL-SIMPLIFIED-TRADITIONAL-DUP Phase 1 — multi-language name normalization.

Pure, deterministic. Verifies the fold collapses *equivalence* (encoding/script
variants of one name) but NOT *similarity* (distinct names), across languages.
"""

from __future__ import annotations

import pytest

from loreweave_extraction.name_normalize import (
    fold_han_simplified,
    has_han,
    nfkc_casefold,
    normalize_entity_name,
)


# ── language-agnostic: NFKC + casefold ───────────────────────────────────────


def test_ascii_english_unchanged_except_case():
    # Pure-ASCII names normalize exactly like .lower() → no accidental re-key of
    # the existing English entity corpus when this is wired in.
    assert normalize_entity_name("Jonathan Harker") == "jonathan harker"
    assert normalize_entity_name("DRACULA") == "dracula"


def test_fullwidth_folds_to_ascii():
    # NFKC: full-width Latin → half-width (same identity, different width).
    assert normalize_entity_name("Ｋａｉ") == "kai"
    assert normalize_entity_name("ＡＢＣ") == "abc"


def test_composed_and_decomposed_accents_fold_together():
    composed = "Café"                      # é = U+00E9
    decomposed = "Café"              # e + combining acute
    assert normalize_entity_name(composed) == normalize_entity_name(decomposed)


def test_casefold_stronger_than_lower():
    # Unicode casefold: ß → ss (str.lower leaves ß) — German names dedupe.
    assert normalize_entity_name("Straße") == "strasse"


def test_accents_are_preserved_not_stripped():
    # Diacritics carry identity — must NOT fold (would over-merge distinct names).
    assert normalize_entity_name("má") != normalize_entity_name("ma")
    assert normalize_entity_name("Müller") != normalize_entity_name("Muller")
    # Vietnamese names keep their tone marks.
    assert "ầ" in normalize_entity_name("Trầm") or normalize_entity_name("Trầm") != "tram"


# ── CJK simplified/traditional fold ──────────────────────────────────────────


def test_traditional_folds_to_simplified():
    # The smoke case: 張若塵 (traditional) ≡ 张若尘 (simplified) → one canonical form.
    assert normalize_entity_name("張若塵") == normalize_entity_name("张若尘")
    assert normalize_entity_name("張若塵") == "张若尘"
    # 池瑤 → 池瑶 (池 identical in both scripts, 瑤→瑶).
    assert normalize_entity_name("池瑤") == "池瑶"


def test_simplified_input_is_stable():
    # Already-simplified input is unchanged (idempotent fold).
    assert normalize_entity_name("八王子") == "八王子"
    assert normalize_entity_name("万古神帝") == "万古神帝"


def test_fold_han_simplified_passes_through_non_han():
    assert fold_han_simplified("Harker 哈克") == "Harker 哈克"  # Latin untouched
    assert fold_han_simplified("plain ascii") == "plain ascii"


def test_has_han_gate():
    assert has_han("張若塵") is True
    assert has_han("八王子 Prince") is True
    assert has_han("Jonathan") is False
    assert has_han("") is False


def test_japanese_kana_unaffected_by_han_fold():
    # Kana are not in the T2S table → pass through (distinct phonemes, never folded).
    assert fold_han_simplified("ハルカ") == "ハルカ"
    assert fold_han_simplified("はるか") == "はるか"


# ── primitives + guards ──────────────────────────────────────────────────────


def test_nfkc_casefold_idempotent():
    once = nfkc_casefold("Ｋａｉ")
    assert nfkc_casefold(once) == once


def test_non_str_raises():
    with pytest.raises(TypeError):
        normalize_entity_name(123)  # type: ignore[arg-type]
