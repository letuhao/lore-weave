"""D-ML-TRIPLE-SVO-SCRIPT — per-language relation-marker triple extraction.

Proves zh/ja/ko/vi SVO+SOV relation pre-seeds via the closed-lexicon extractor,
that segmenter-noise (verb runs / josa-suffixed runs) can't land in a role slot,
and that English routing is untouched (SVO regex only).
"""

from __future__ import annotations

import pytest

from app.extraction.triple_extractor import extract_triples


def _triples(text, gloss):
    return [(t.subject, t.predicate, t.object_) for t in extract_triples(text, glossary_names=gloss)]


@pytest.mark.parametrize(
    "text,gloss,expected",
    [
        # SVO — Chinese
        ("凯认识林。", ["凯", "林"], ("凯", "knows", "林")),
        ("凯背叛了林大师。", ["凯", "林大师"], ("凯", "betrayed", "林大师")),
        # SVO — Vietnamese
        ("Nguyễn giết Trần.", ["Nguyễn", "Trần"], ("Nguyễn", "killed", "Trần")),
        # SOV — Japanese (object precedes verb; を/は particles)
        ("田中が佐藤を殺した。", ["田中", "佐藤"], ("田中", "killed", "佐藤")),
        ("田中は佐藤を裏切った。", ["田中", "佐藤"], ("田中", "betrayed", "佐藤")),
        # SOV — Korean (josa-suffixed runs must NOT leak into roles)
        ("김철수가 이영희를 구했다.", ["김철수", "이영희"], ("김철수", "saved", "이영희")),
    ],
)
def test_multilingual_relation_triples(text, gloss, expected):
    assert expected in _triples(text, gloss)


def test_korean_verb_run_not_object():
    # Regression: before the dedup + SOV fix, the verb run "구했다" landed as the
    # object. The object must be a real entity.
    triples = _triples("김철수가 이영희를 구했다.", ["김철수", "이영희"])
    assert triples, "expected a triple"
    for _, _, obj in triples:
        assert "구했" not in obj, f"verb run leaked into object slot: {obj}"


def test_no_triple_without_two_entities():
    # Single anchor ⇒ degrade-open (no triple, never a wrong one).
    assert _triples("凯认识某人。", ["凯"]) == []


def test_no_marker_no_triple():
    assert _triples("凯站在门口。", ["凯"]) == []  # "Kai stood at the door" — no relation verb


def test_english_uses_svo_regex_only_byte_identical():
    # English must route through the existing SVO regex, NOT the relation lexicon.
    assert ("Kai", "killed", "Drake") in _triples("Kai killed Drake.", ["Kai", "Drake"])
    # An English relation word is handled by the SVO regex path (predicate is the
    # raw verb), never the zh/ja/ko/vi lexicon.
    assert ("Kai", "met", "Lin") in _triples("Kai met Lin.", ["Kai", "Lin"])
