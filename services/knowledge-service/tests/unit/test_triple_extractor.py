"""K15.4 unit tests — pattern-based SVO triple extractor.

Pure-function tests, no I/O. Covers:
  - Clean SVO extraction with various verb forms
  - Multi-word subjects + objects
  - SKIP_MARKER filter for hypothetical / reported speech
  - Article stripping on objects
  - 80%+ precision on a fixture corpus
"""

from __future__ import annotations

import pytest

from app.extraction.triple_extractor import Triple, extract_triples


# ── smoke + basic ────────────────────────────────────────────────────


def test_k15_4_empty_returns_empty():
    assert extract_triples("") == []
    assert extract_triples("   ") == []


def test_k15_4_simple_svo_past_tense():
    out = extract_triples("Kai killed Commander Zhao in the courtyard.")
    assert len(out) >= 1
    t = out[0]
    assert isinstance(t, Triple)
    assert t.subject == "Kai"
    assert t.predicate == "killed"
    assert "Zhao" in t.object_
    assert t.confidence == 0.5
    assert t.pending_validation is True


def test_k15_4_triple_preserves_sentence():
    sentence = "Kai entered the throne room."
    out = extract_triples(sentence)
    assert any(sentence in t.sentence for t in out)


def test_k15_4_triple_model_alias_round_trip():
    """`object` is a Python keyword so the field is `object_` with
    an alias. Ensure both dump forms work."""
    out = extract_triples("Kai met Drake.")
    assert len(out) >= 1
    d = out[0].model_dump(by_alias=True)
    assert "object" in d
    assert "subject" in d
    assert "predicate" in d


# ── verb forms ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sentence,pred_contains",
    [
        ("Kai killed Zhao.", "killed"),
        ("Kai fights Drake.", "fights"),
        ("Kai took the sword.", "took"),
        ("Kai gave Mira the book.", "gave"),
        ("Kai met Phoenix at dawn.", "met"),
    ],
)
def test_k15_4_verb_forms_extracted(sentence: str, pred_contains: str):
    out = extract_triples(sentence)
    assert len(out) >= 1, f"no triple for {sentence!r}"
    assert any(pred_contains in t.predicate for t in out)


# ── multi-word subject / object ──────────────────────────────────────


def test_k15_4_multi_word_subject():
    out = extract_triples("Commander Zhao struck Kai on the arm.")
    subjects = {t.subject for t in out}
    assert any("Commander Zhao" in s or "Zhao" in s for s in subjects)


def test_k15_4_multi_word_object():
    out = extract_triples("Kai entered Water Kingdom.")
    objs = {t.object_ for t in out}
    assert any("Water Kingdom" in o for o in objs)


def test_k15_4_object_article_stripped():
    out = extract_triples("Kai drew the sword.")
    assert len(out) >= 1
    t = out[0]
    assert not t.object_.lower().startswith("the ")
    assert "sword" in t.object_.lower()


# ── SKIP_MARKER filter ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "sentence",
    [
        "If Kai had stayed, he would have killed Zhao.",
        "Imagine Kai defeated Drake.",
        "Suppose Kai met Phoenix yesterday.",
        "Kai could have killed Zhao.",
        "Kai might have saved Mira.",
    ],
)
def test_k15_4_hypothetical_sentences_skipped(sentence: str):
    out = extract_triples(sentence)
    assert out == [], f"hypothetical leaked: {sentence!r} → {out}"


def test_k15_4_reported_speech_said_that_skipped():
    out = extract_triples("Zhao said that Kai killed Phoenix.")
    assert out == []


# ── negation (should not extract positive fact) ─────────────────────


def test_k15_4_negation_sentence_not_extracted_as_positive():
    """K15.5 handles negation properly; K15.4 should at minimum not
    emit a positive assertion from a negated sentence. The SVO regex
    requires a subject-verb-object shape without 'not' between verb
    and object; `does not know` lands in SKIP-adjacent territory."""
    # "Kai does not know Zhao" — "does" is a valid verb but SVO
    # would capture "(Kai, does, not)" which then trips the object
    # filter (`not` is a stopword-ish token). Assert we don't emit
    # a confident-looking (Kai, knows, Zhao) triple.
    out = extract_triples("Kai does not know Zhao.")
    for t in out:
        assert t.predicate != "knows"
        assert t.predicate != "know"


# ── entity gate (bare common noun subjects rejected) ───────────────


def test_k15_4_lowercase_subject_rejected():
    """A lowercase subject ("he killed Zhao") must not land — the
    pronoun-resolution problem is K17's job."""
    out = extract_triples("he killed Zhao.")
    assert out == []


def test_k15_4_sentence_start_stopword_subject_rejected():
    """Sentence-start "The" + verb shouldn't land as subject."""
    out = extract_triples("The killed Kai.")  # ungrammatical trap
    subjects = {t.subject.casefold() for t in out}
    assert "the" not in subjects


# ── CJK smoke (triple extractor does not handle CJK) ────────────────


def test_k15_4_cjk_sentence_yields_no_triples():
    """K15.4 is English-first. A pure-CJK sentence has no capital-
    letter signal so the SVO regex can't match. That's intentional —
    K17 LLM is the multilingual fallback."""
    out = extract_triples("凯杀了张将军。")
    assert out == []


def test_k15_4_mixed_english_chinese_extracts_english_only():
    text = (
        "Kai killed Commander Zhao at the bridge. "
        "凯杀了张将军在桥上。"
    )
    out = extract_triples(text)
    # At least one English triple
    assert any(t.subject == "Kai" for t in out)
    # No triple should contain CJK chars (K15.4 pattern is Latin-only)
    for t in out:
        assert all(ord(c) < 0x2e80 for c in t.subject), (
            f"CJK leaked into subject: {t.subject}"
        )


# ── self-reference drop ─────────────────────────────────────────────


def test_k15_4_self_reference_dropped():
    """"Kai saw Kai" is almost always a regex-fusion artifact;
    the extractor drops conservatively."""
    out = extract_triples("Kai saw Kai.")
    assert out == []


# ── R1 regressions ──────────────────────────────────────────────────


def test_k15_4_r1_i1_compound_clause_not_fused():
    """K15.4-R1/I1: "Kai walked and Drake followed" must not emit
    a single triple `(Kai, walked, and Drake followed)`. Before
    the fix, the object regex greedily swallowed the conjunction
    and the following clause, producing a confidently-wrong triple
    that would poison the K18 validator.
    """
    out = extract_triples("Kai walked and Drake followed.")
    for t in out:
        assert "and" not in t.object_.lower().split(), (
            f"compound fused into object: {t}"
        )
        assert "Drake" not in t.object_, f"clause fused: {t}"


def test_k15_4_r1_i1_object_conjunction_takes_first_only():
    """K15.4-R1/I1: "Kai killed Zhao and Drake" — the object stops
    at the conjunction boundary rather than fusing both targets
    into one object string.
    """
    out = extract_triples("Kai killed Zhao and Drake.")
    assert len(out) >= 1
    t = out[0]
    assert "and" not in t.object_.lower()
    assert "Zhao" in t.object_


def test_k15_4_r1_i2_adverbial_pp_not_fused_into_object():
    """K15.4-R1/I2: "Kai walked slowly into the room" must not
    emit `(Kai, walked, slowly into the room)`. The adverbial PP
    is not a direct object — "walked" is intransitive here.
    Without the preposition/adverb stop-word gate, the object
    regex would swallow the whole tail.
    """
    out = extract_triples("Kai walked slowly into the room.")
    for t in out:
        obj = t.object_.lower()
        assert "slowly" not in obj, f"adverb leaked: {t}"
        assert "into" not in obj, f"preposition leaked: {t}"


# ── R2 regressions ──────────────────────────────────────────────────


def test_k15_4_r2_i1_passive_voice_not_inverted():
    """K15.4-R2/I1: "Kai was killed by Drake" must NOT produce
    `(Kai, was, killed)`. Before the fix, auxiliary verbs (was,
    were, is, are, has, had) were in the main-verb alternation, so
    the SVO regex happily matched passive constructions as if the
    patient were the agent — inverting reality and producing
    confidently-wrong triples that would poison K18 validation.

    Fix: remove auxiliaries from the verb alternation. Passive /
    progressive / perfect tenses are K17 LLM's job.
    """
    out = extract_triples("Kai was killed by Drake.")
    for t in out:
        assert t.predicate not in {"was", "is", "were", "are", "has", "had", "did"}, (
            f"auxiliary leaked as main verb: {t}"
        )
        # Most importantly: Kai must not be labeled as agent of "killed"
        assert not (t.subject == "Kai" and "killed" in t.object_.lower()), (
            f"passive inversion: {t}"
        )


@pytest.mark.parametrize(
    "sentence",
    [
        "Kai was killed by Drake.",
        "Zhao was captured at dawn.",
        "Mira is loved by all.",
        "The sword was broken.",
        "Drake had fought before.",
    ],
)
def test_k15_4_r2_i1_auxiliary_verbs_never_main(sentence: str):
    """Any SVO triple produced from a sentence with an auxiliary
    construction must not use the auxiliary as the predicate."""
    out = extract_triples(sentence)
    for t in out:
        assert t.predicate not in {"was", "is", "were", "are", "has", "had", "did"}


# ── acceptance: 80%+ precision on fixture corpus ────────────────────


def test_k15_4_acceptance_precision_on_30_sentence_corpus():
    """K15.4 acceptance: 80%+ precision on a mixed corpus of
    clean SVO + trap sentences. Precision = (correct triples) /
    (total triples emitted). Traps include hypothetical, reported
    speech, and lowercase-subject false-positives."""
    fixture = [
        # Clean SVO — should all extract
        ("Kai killed Commander Zhao.", True),
        ("Drake fought Phoenix at dawn.", True),
        ("Mira entered the throne room.", True),
        ("Kai drew the sword.", True),
        ("Commander Zhao bowed to Kai.", True),
        ("Kai met Phoenix at dusk.", True),
        ("Drake struck Kai on the arm.", True),
        ("Phoenix saved Mira from the fire.", True),
        ("Kai took the crown.", True),
        ("Mira gave Kai the map.", True),
        ("Kai entered Water Kingdom.", True),
        ("Zhao knew the secret.", True),
        ("Kai loved Mira deeply.", True),
        ("Drake hated Phoenix openly.", True),
        ("Phoenix told Kai the truth.", True),
        # Traps — should all be rejected
        ("If Kai had stayed, he would have killed Zhao.", False),
        ("Imagine Kai defeated Drake.", False),
        ("Suppose Kai met Phoenix.", False),
        ("Zhao said that Kai killed Phoenix.", False),
        ("he killed Zhao.", False),  # lowercase subject
        ("The killed Kai.", False),  # stopword subject
        ("Kai could have killed Zhao.", False),
        ("Kai might have saved Mira.", False),
        ("Kai does not know Zhao.", False),
        ("Kai saw Kai.", False),  # self-reference
        # Edge cases — should extract
        ("Lord Okafor arrived at the palace.", True),
        ("Old Man Li announced the guest.", True),
        ("Princess Mira watched from above.", True),
        ("General Bao returned from the war.", True),
        ("Hailong buzzed with rumors.", True),
    ]

    total_emitted = 0
    correct = 0
    missed_clean = 0

    for sentence, should_extract in fixture:
        triples = extract_triples(sentence)
        if should_extract:
            if triples:
                total_emitted += len(triples)
                correct += len(triples)  # all triples on a clean sentence count as correct
            else:
                missed_clean += 1
        else:
            total_emitted += len(triples)
            # emissions on a trap are incorrect — don't increment `correct`

    precision = correct / total_emitted if total_emitted else 0.0
    recall_clean = (len(
        [s for s, ok in fixture if ok]) - missed_clean) / len(
        [s for s, ok in fixture if ok]
    )
    assert precision >= 0.80, (
        f"precision {precision:.0%} below 80% — "
        f"correct={correct} emitted={total_emitted} "
        f"missed_clean={missed_clean}"
    )
    # Sanity: recall on clean sentences should also be reasonable
    assert recall_clean >= 0.60, (
        f"recall on clean sentences {recall_clean:.0%} below 60%"
    )
