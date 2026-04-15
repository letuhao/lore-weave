"""K15.5 unit tests — pattern-based negation fact extractor.

Pure-function tests, no I/O. Covers:
  - English negation markers (does not know, is unaware, etc.)
  - Multi-language negation via K15.3 dispatch
  - Subject anchoring via K15.2 entity candidates
  - Object fallback when no following entity
  - Subject-missing sentences silently skipped
"""

from __future__ import annotations

import pytest

from app.extraction.negation import NegationFact, extract_negations


# ── smoke + basic ────────────────────────────────────────────────────


def test_k15_5_empty_returns_empty():
    assert extract_negations("") == []
    assert extract_negations("   ") == []


def test_k15_5_sentence_without_negation_returns_empty():
    assert extract_negations("Kai walked into the room.") == []


def test_k15_5_simple_does_not_know():
    out = extract_negations("Kai does not know Zhao.")
    assert len(out) >= 1
    n = out[0]
    assert isinstance(n, NegationFact)
    assert n.subject == "Kai"
    assert n.object_ == "Zhao"
    assert "does not know" in n.marker.lower() or "not know" in n.marker.lower()
    assert n.fact_type == "negation"
    assert n.confidence == 0.5
    assert n.pending_validation is True


def test_k15_5_is_unaware_marker():
    out = extract_negations("Kai is unaware of the plot.")
    assert len(out) >= 1
    n = out[0]
    assert n.subject == "Kai"
    assert "unaware" in n.marker.lower()


def test_k15_5_never_met_marker():
    out = extract_negations("Kai never met Drake before today.")
    assert len(out) >= 1
    n = out[0]
    assert n.subject == "Kai"
    assert n.object_ == "Drake" or (n.object_ and "Drake" in n.object_)


# ── subject anchoring ───────────────────────────────────────────────


def test_k15_5_subject_missing_skipped():
    """A negation marker with no anchorable entity before it must
    not emit a fact — a bare "is unaware" with no subject has no
    usable semantic content."""
    out = extract_negations("is unaware of the danger.")
    assert out == []


def test_k15_5_multi_word_subject():
    out = extract_negations("Commander Zhao does not know Kai's plan.")
    assert len(out) >= 1
    assert any("Zhao" in n.subject for n in out)


def test_k15_5_nearest_preceding_entity_is_subject():
    """When multiple entities precede the marker, the nearest
    (latest) one anchors as subject."""
    out = extract_negations("Kai met Drake. Drake does not know Phoenix.")
    # Multi-sentence: the second sentence should anchor Drake
    second = [n for n in out if "Phoenix" in (n.object_ or "")]
    assert second
    assert second[0].subject == "Drake"


# ── object fallback ─────────────────────────────────────────────────


def test_k15_5_object_falls_back_to_trailing_np_when_no_entity():
    """No entity candidate after the marker → use a short NP
    fallback. `answer` is a common noun, not an entity."""
    out = extract_negations("Kai does not know the answer.")
    assert len(out) >= 1
    n = out[0]
    assert n.subject == "Kai"
    assert n.object_ is not None
    assert "answer" in n.object_.lower()


def test_k15_5_r1_trailing_np_rejects_preposition_leak():
    """K15.5-R1/I1 regression: trailing-NP fallback must not
    swallow a following preposition. `"the answer of the riddle"`
    previously yielded `"answer of the"` — a PP fused into what
    should be a bare NP."""
    out = extract_negations("Kai does not know the answer of the riddle.")
    assert len(out) >= 1
    n = out[0]
    assert n.subject == "Kai"
    assert n.object_ is not None
    assert "of" not in n.object_.split()
    assert "answer" in n.object_.lower()


def test_k15_5_r1_trailing_np_rejects_pure_pp():
    """K15.5-R1/I1 regression: `"is unaware of the plot"` previously
    yielded `object="of the plot"`. The fallback must return None or
    a non-PP when the tail begins with a preposition."""
    out = extract_negations("Drake is unaware of the plot.")
    assert len(out) >= 1
    n = next((x for x in out if x.subject == "Drake"), None)
    assert n is not None
    # Tail starts with "of" — fallback NP should reject the PP.
    assert n.object_ is None or not n.object_.lower().startswith("of")


def test_k15_5_object_none_when_trailing_empty():
    """Marker at end-of-sentence with no tail → object is None."""
    out = extract_negations("Kai is unaware.")
    assert len(out) >= 1
    # object_ may be None or a trailing punctuation-stripped empty
    n = out[0]
    assert n.subject == "Kai"
    assert n.object_ in (None, "")


# ── model shape ─────────────────────────────────────────────────────


def test_k15_5_model_alias_round_trip():
    out = extract_negations("Kai does not know Zhao.")
    assert len(out) >= 1
    d = out[0].model_dump(by_alias=True)
    assert "object" in d
    assert "subject" in d
    assert "marker" in d
    assert d["fact_type"] == "negation"


# ── SKIP_MARKERS do not interfere ───────────────────────────────────


def test_k15_5_hypothetical_not_filtered_here():
    """K15.5 does NOT apply SKIP_MARKERS — negation inside a
    hypothetical ("if Kai did not know") is still a candidate
    negation. The caller is responsible for upstream SKIP filtering
    if it wants to drop these. K15.5's job is just to find the
    negation pattern.

    This differs from K15.4 triple extractor which DOES apply
    SKIP_MARKERS, because an SVO in a hypothetical is a false
    positive, while a negation in a hypothetical is still a
    negation (just with a condition attached).
    """
    out = extract_negations("When Drake does not know Zhao, he asks Kai.")
    # Should still surface the negation — caller decides what to do
    assert any("Drake" in n.subject for n in out)


# ── multiple negations in one sentence ─────────────────────────────


def test_k15_5_multiple_markers_yield_multiple_facts():
    out = extract_negations(
        "Kai does not know Zhao. Drake does not know Phoenix."
    )
    subjects = {n.subject for n in out}
    assert "Kai" in subjects
    assert "Drake" in subjects


# ── CJK smoke ───────────────────────────────────────────────────────


def test_k15_5_cjk_negation_with_glossary():
    """CJK: subject anchoring needs glossary (K15.2 English-first
    capitalized-phrase regex can't see Chinese names)."""
    # Use a long-enough Chinese string for langdetect to commit,
    # plus glossary to anchor the subject.
    text = "凯不知道张的秘密。凯从未见过凤凰。"
    out = extract_negations(text, glossary_names=["凯", "张", "凤凰"])
    subjects = {n.subject for n in out}
    assert "凯" in subjects


# ── acceptance: common English patterns caught ─────────────────────


@pytest.mark.parametrize(
    "sentence,expected_subject",
    [
        ("Kai does not know Zhao.", "Kai"),
        ("Kai doesn't know Zhao.", "Kai"),
        ("Drake is unaware of the plot.", "Drake"),
        ("Mira never met Phoenix.", "Mira"),
        ("Phoenix has no idea about the treasure.", "Phoenix"),
        ("Kai cannot reach the summit.", "Kai"),
    ],
)
def test_k15_5_acceptance_common_negation_patterns(
    sentence: str, expected_subject: str
):
    out = extract_negations(sentence)
    assert len(out) >= 1, f"no negation surfaced for {sentence!r}"
    assert any(n.subject == expected_subject for n in out), (
        f"expected subject {expected_subject!r} in {[n.subject for n in out]}"
    )
