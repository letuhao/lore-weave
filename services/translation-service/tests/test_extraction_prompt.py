"""Tests for the extraction prompt builder + output parser."""
from app.workers.extraction_prompt import parse_and_validate_with_stats

# ── the `term` display attribute (glossary/KG entity-linkage repair, 2026-08-01) ──
#
# `terminology` is the only kind whose display attribute is `term`, and it is REQUIRED
# there. The parser accepted only `name`, and the glossary writeback hardcoded `:name` on
# the other side, so the kind lost its name either way: answer the schema correctly and the
# parser dropped the entity; answer `name` and glossary discarded the value. Measured
# before the fix: 215 of 224 `terminology` entities had an empty cached_name — and since
# the evidence row and the translation both hang off the name's attr_value_id, they were
# lost too. A nameless entity cannot be a link target, which is why this is a linkage bug.

_TERM_PROFILE = {"terminology": {"term": "default", "category": "default",
                                 "definition": "default"}}


def test_terminology_entity_named_by_term_is_kept():
    out, _ = parse_and_validate_with_stats(
        '[{"kind":"terminology","term":"先天數","category":"magic",'
        '"definition":"a divination art","evidence":"quote"}]',
        ["terminology"], _TERM_PROFILE)
    assert len(out) == 1, "an entity that answered the schema was dropped"
    assert out[0]["name"] == "先天數"


def test_term_is_not_also_written_back_as_an_attribute():
    """It is consumed as the NAME. Leaving it in attributes makes glossary write the same
    attr_def twice — once as the name, once as an attribute — on one ON CONFLICT row."""
    out, _ = parse_and_validate_with_stats(
        '[{"kind":"terminology","term":"先天數","definition":"d"}]',
        ["terminology"], _TERM_PROFILE)
    assert "term" not in out[0]["attributes"]
    assert out[0]["attributes"]["definition"] == "d"


def test_name_still_wins_when_a_model_sends_both():
    out, _ = parse_and_validate_with_stats(
        '[{"kind":"terminology","name":"A","term":"B","definition":"d"}]',
        ["terminology"], _TERM_PROFILE)
    assert out[0]["name"] == "A"


def test_an_entity_with_NEITHER_name_nor_term_is_still_dropped():
    """The tolerance must not become "accept anything" — an unnamed entity is unusable
    exactly as before, and this is the bite test for the widened condition."""
    out, _ = parse_and_validate_with_stats(
        '[{"kind":"terminology","definition":"no name anywhere"}]',
        ["terminology"], _TERM_PROFILE)
    assert out == []


def test_other_kinds_are_unaffected_by_the_widening():
    """`term` must not become a name source for kinds that have a real `name`."""
    prof = {"character": {"name": "default", "role": "default"}}
    out, _ = parse_and_validate_with_stats(
        '[{"kind":"character","name":"姜子牙","role":"strategist"}]', ["character"], prof)
    assert out[0]["name"] == "姜子牙" and out[0]["attributes"]["role"] == "strategist"
