"""K15.2 unit tests — entity candidate extractor.

Pure-function tests, no I/O, no Neo4j. Covers the KSA §5.1
two-pass algorithm and the K15.2 acceptance criteria:
  - 90%+ of explicit names extracted in the fixture corpus
  - Common nouns ignored
  - Glossary matches rank highest
  - CJK handled via glossary-only path (English-first scope)
"""

from __future__ import annotations

import pytest

from app.extraction.entity_detector import (
    COMMON_NOUN_STOPWORDS,
    EntityCandidate,
    extract_entity_candidates,
)


# ── smoke + basic English ─────────────────────────────────────────────


def test_k15_2_empty_text_returns_empty_list():
    assert extract_entity_candidates("") == []
    assert extract_entity_candidates("   ") == []


def test_k15_2_simple_english_picks_up_both_names():
    text = "Kai killed Commander Zhao in the courtyard."
    out = extract_entity_candidates(text)
    names = {c.name for c in out}
    assert "Kai" in names
    assert "Commander Zhao" in names or "Zhao" in names


def test_k15_2_result_is_pydantic_model():
    out = extract_entity_candidates("Kai smiled.")
    assert len(out) >= 1
    assert isinstance(out[0], EntityCandidate)
    assert 0.0 <= out[0].confidence <= 1.0
    assert out[0].kind_hint == "character"
    assert "signals" in out[0].model_dump()


# ── common-noun filter ────────────────────────────────────────────────


def test_k15_2_common_nouns_ignored():
    """The detector must not treat pronouns / generic referents as
    entities. `The character walked. The man spoke.` has two
    capitalized sentence-starts that are NOT names."""
    text = "The character walked. The man spoke. It was quiet."
    out = extract_entity_candidates(text)
    assert out == [], f"expected no candidates, got {[c.name for c in out]}"


def test_k15_2_stopword_list_is_lowercase_folded():
    # Sanity check: every stopword entry is casefolded so the
    # _fold(display) lookup matches regardless of input case.
    for word in COMMON_NOUN_STOPWORDS:
        assert word == word.casefold()


def test_k15_2_sentence_start_the_filtered_but_name_kept():
    """`The Kingdom fell. Kai wept.` — `The` should be filtered,
    `Kingdom` (if it slips through capitalized-phrase fusion with
    The) and `Kai` should land. Specifically the capitalized-phrase
    regex greedily captures `The Kingdom` as one phrase — that
    folded form isn't a stopword so it survives. The important
    invariant: `The` alone never survives."""
    text = "The Kingdom fell. Kai wept."
    out = extract_entity_candidates(text)
    names = {c.name for c in out}
    assert "The" not in names
    assert "Kai" in names


# ── glossary-match ranks highest ──────────────────────────────────────


def test_k15_2_glossary_match_outranks_bare_capitalized():
    text = "Drake fought Kai on the bridge."
    out = extract_entity_candidates(text, glossary_names=["Kai"])
    by_name = {c.name.lower(): c for c in out}
    assert "kai" in by_name
    assert "drake" in by_name
    # Kai has glossary signal → higher confidence than Drake (bare cap).
    assert by_name["kai"].confidence > by_name["drake"].confidence
    assert "glossary" in by_name["kai"].signals
    assert "glossary" not in by_name["drake"].signals


def test_k15_2_glossary_case_insensitive_word_bounded():
    """Glossary entry 'Kai' must match 'kai', 'KAI', 'Kai!' but
    NOT 'kairos' (word boundary)."""
    text = "kai ran. KAI jumped. Kai! Kairos watched."
    out = extract_entity_candidates(text, glossary_names=["Kai"])
    names_lower = {c.name.lower() for c in out}
    # Kai variants all merge into one candidate via _fold
    kai_cands = [c for c in out if c.name.lower() == "kai"]
    assert len(kai_cands) == 1
    # Three Kai hits → frequency bonus should be in the signals
    assert "frequency" in kai_cands[0].signals
    # Kairos is bare capitalized (no glossary hit), should still appear
    assert "kairos" in names_lower


def test_k15_2_glossary_match_results_in_high_confidence():
    out = extract_entity_candidates(
        "Kai entered the hall.",
        glossary_names=["Kai"],
    )
    kai = next(c for c in out if c.name.lower() == "kai")
    # base 0.30 + glossary 0.45 + capitalized 0.10 + verb_adjacent 0.15
    # = 1.0 (capped). At minimum: base + glossary = 0.75
    assert kai.confidence >= 0.75


# ── quoted-name detection across quote families ──────────────────────


@pytest.mark.parametrize(
    "text",
    [
        'The sign read "Master Li" in bold letters.',
        "The sign read 'Master Li' in bold letters.",
        "The sign read \u201cMaster Li\u201d in bold letters.",
        "The sign read \u300cMaster Li\u300d in bold letters.",
    ],
)
def test_k15_2_quoted_name_detected_across_quote_families(text: str):
    out = extract_entity_candidates(text)
    names = {c.name for c in out}
    assert "Master Li" in names, f"failed for text: {text!r}"


def test_k15_2_quoted_signal_contributes_to_confidence():
    out = extract_entity_candidates('He whispered "Shadow" softly.')
    shadow = next((c for c in out if c.name == "Shadow"), None)
    assert shadow is not None
    assert "quoted" in shadow.signals


# ── frequency bonus ──────────────────────────────────────────────────


def test_k15_2_r1_single_mention_glossary_name_has_no_frequency_bonus():
    """K15.2-R1: a single textual mention of a glossary-matched
    Latin-script name must NOT collect a frequency bonus. Without
    the gate, Pass A1 (glossary) and Pass A3 (capitalized) would
    both bump the counter on the same literal 'Kai', registering
    count=2 on a single mention and inflating the signal by +0.05.
    """
    out = extract_entity_candidates("Kai smiled.", glossary_names=["Kai"])
    kai = next(c for c in out if c.name == "Kai")
    assert "frequency" not in kai.signals, (
        f"single mention should not have frequency bonus, got {kai.signals}"
    )


def test_k15_2_frequency_bonus_bumps_confidence():
    single = extract_entity_candidates("Kai walked.")
    triple = extract_entity_candidates("Kai walked. Kai ran. Kai slept.")
    k_single = next(c for c in single if c.name == "Kai")
    k_triple = next(c for c in triple if c.name == "Kai")
    assert k_triple.confidence > k_single.confidence
    assert "frequency" in k_triple.signals


def test_k15_2_frequency_bonus_is_capped():
    text = " ".join(["Kai walked."] * 20)
    out = extract_entity_candidates(text)
    kai = next(c for c in out if c.name == "Kai")
    # Cap is 0.20 — total should never exceed 1.0 (pydantic validator)
    assert kai.confidence <= 1.0
    assert kai.signals.get("frequency", 0) <= 0.20 + 1e-9


# ── CJK via glossary-only path ───────────────────────────────────────


def test_k15_2_cjk_detected_only_via_glossary():
    """K15.2 English-first scope: CJK text has no capitalized-phrase
    signal because there's no case. The glossary path is the only
    way a CJK name surfaces until K15.3 ships per-language patterns."""
    text = "凯笑了。凯抽出剑。"

    # Without glossary: no candidates
    assert extract_entity_candidates(text) == []

    # With glossary: detected + frequency bonus for two mentions
    out = extract_entity_candidates(text, glossary_names=["凯"])
    assert len(out) == 1
    assert out[0].name == "凯"
    assert "glossary" in out[0].signals
    assert "frequency" in out[0].signals


def test_k15_2_mixed_script_text_with_glossary():
    text = "Kai met 凯 at dawn."
    out = extract_entity_candidates(text, glossary_names=["凯", "Kai"])
    names = {c.name for c in out}
    assert "Kai" in names
    assert "凯" in names


# ── sorting ─────────────────────────────────────────────────────────


def test_k15_2_results_sorted_confidence_desc():
    text = "Drake met Kai. Kai said hello. Kai smiled again."
    out = extract_entity_candidates(text, glossary_names=["Kai"])
    confidences = [c.confidence for c in out]
    assert confidences == sorted(confidences, reverse=True)


# ── acceptance corpus: 90%+ coverage ─────────────────────────────────


def test_k15_2_acceptance_90_percent_coverage_on_fixture():
    """K15.2 acceptance: >=90% of explicit names extracted from a
    representative test paragraph. Fixture lists 10 named entities;
    at least 9 must appear in the output."""
    text = (
        "Kai entered the throne room of Water Kingdom. "
        "Commander Zhao bowed. "
        "Princess Mira watched from the balcony. "
        "Drake and Phoenix stood guard at the door. "
        "The steward, Old Man Li, announced the arrival. "
        '"General Bao has returned," said Mira. '
        "Outside, Hailong City buzzed with rumors. "
        "Lord Okafor arrived in a carriage."
    )
    expected = {
        "Kai",
        "Water Kingdom",
        "Commander Zhao",
        "Princess Mira",
        "Drake",
        "Phoenix",
        "Old Man Li",
        "General Bao",
        "Hailong City",
        "Lord Okafor",
    }
    out = extract_entity_candidates(text)
    found_names = {c.name for c in out}

    # Partial-match tolerance: if the detector returns "Zhao" instead
    # of "Commander Zhao", count that as a hit. The acceptance bar
    # is "90% of explicit names surface somehow" — the display form
    # is K17's job to refine.
    hits = 0
    for name in expected:
        if name in found_names:
            hits += 1
            continue
        # Check any token of the expected phrase is present
        tokens = name.split()
        if any(t in found_names for t in tokens):
            hits += 1
    coverage = hits / len(expected)
    assert coverage >= 0.9, (
        f"coverage {coverage:.0%} below 90% — "
        f"expected={expected} found={found_names}"
    )


# ── R2 regressions ───────────────────────────────────────────────────


def test_k15_2_r2_i1_cjk_quoted_name_accrues_frequency_bonus():
    """K15.2-R2/I1: a CJK name quoted multiple times (no glossary,
    no capitalized-pass coverage) must still accrue a frequency
    bonus. Before the span-dedup rewrite, the quoted pass never
    bumped `count`, leaving CJK-quoted names permanently at
    count=0 regardless of mention frequency.
    """
    text = "\u300c凯\u300d跑了。\u300c凯\u300d停下。\u300c凯\u300d笑了。"
    out = extract_entity_candidates(text)
    assert len(out) == 1
    kai = out[0]
    assert kai.name == "凯"
    assert "quoted" in kai.signals
    assert "frequency" in kai.signals, (
        f"CJK quoted name with 3 mentions should have frequency signal, "
        f"got {kai.signals}"
    )


def test_k15_2_r2_i1_latin_quoted_and_capitalized_dedups_span():
    """K15.2-R2/I1: when a Latin quoted name is ALSO captured by
    the capitalized-phrase regex at the same span, the two passes
    must not double-bump the counter. A single mention should
    produce count=1, no frequency bonus.
    """
    text = 'Alice whispered "Shadow" once.'
    # "Shadow" is matched by: (a) the quoted pass on the
    # inner-group span, (b) the capitalized-phrase pass on the
    # same characters. Both call bump_count_for_span with the
    # same (start, end) → only one counter bump.
    out = extract_entity_candidates(text)
    shadow = next(c for c in out if c.name == "Shadow")
    assert "quoted" in shadow.signals
    assert "capitalized" in shadow.signals
    assert "frequency" not in shadow.signals, (
        f"single-mention Latin quoted+capitalized should not "
        f"collect frequency bonus, got {shadow.signals}"
    )


def test_k15_2_r2_i2_output_deterministic_across_calls():
    """K15.2-R2/I2: same input must produce identical output
    across calls. Before the sorted glossary-list fix, set
    iteration order was hash-randomized, so when two glossary
    candidates tied on confidence their order would differ
    across runs. Lock determinism in.
    """
    text = (
        "Kai fought Drake at dawn. "
        "Drake struck first. Kai blocked."
    )
    glossary = ["Kai", "Drake", "Phoenix", "Water Kingdom"]

    out1 = extract_entity_candidates(text, glossary_names=glossary)
    out2 = extract_entity_candidates(text, glossary_names=glossary)
    out3 = extract_entity_candidates(text, glossary_names=list(reversed(glossary)))

    # Same input → identical output
    assert out1 == out2
    # Order of glossary_names input must not affect output
    assert out1 == out3


# ── stopwords: the acceptance "ignores common nouns" ─────────────────


def test_k15_2_generic_referents_never_surface():
    text = (
        "The character crossed the street. "
        "The man nodded. "
        "The hero drew his sword."
    )
    out = extract_entity_candidates(text)
    names_lower = {c.name.lower() for c in out}
    for bad in (
        "the character",
        "the man",
        "the hero",
    ):
        assert bad not in names_lower
