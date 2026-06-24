"""KG-ML M5 (C5) — predicate-label resolution unit tests."""
from __future__ import annotations

from app.labels.predicate_labels import (
    humanize_predicate,
    predicate_catalog,
    resolve_predicate_label,
)


def test_humanize_variants():
    assert humanize_predicate("ALLY_OF") == "ally of"
    assert humanize_predicate("ally_of") == "ally of"
    assert humanize_predicate("ally-of") == "ally of"
    assert humanize_predicate("PART__OF") == "part of"
    assert humanize_predicate("") == ""


def test_resolve_curated_vi():
    assert resolve_predicate_label("ALLY_OF", "vi") == "đồng minh của"
    assert resolve_predicate_label("KILLED", "vi") == "đã giết"


def test_resolve_normalizes_code_case_and_separators():
    # an LLM-emitted snake_case predicate still hits the curated map
    assert resolve_predicate_label("ally_of", "vi") == "đồng minh của"
    assert resolve_predicate_label("ally-of", "vi") == "đồng minh của"


def test_resolve_regional_variant_uses_primary_subtag():
    # "vi-VN" → primary "vi" → curated vi label
    assert resolve_predicate_label("ENEMY_OF", "vi-VN") == "kẻ thù của"


def test_resolve_english_uses_humanize():
    # English isn't curated — humanize reproduces the seed label
    assert resolve_predicate_label("ALLY_OF", "en") == "ally of"
    assert resolve_predicate_label("ALLY_OF", None) == "ally of"


def test_resolve_unknown_predicate_falls_back_to_humanize():
    # open-vocab predicate (not in the curated map) degrades to humanize, never raw
    assert resolve_predicate_label("SECRETLY_FUNDS", "vi") == "secretly funds"
    assert resolve_predicate_label("SECRETLY_FUNDS", "en") == "secretly funds"


def test_resolve_uncurated_language_falls_back_to_humanize():
    # a known predicate but a language with no curation → humanized English
    assert resolve_predicate_label("ALLY_OF", "fr") == "ally of"


def test_catalog_vi_has_curated_labels():
    cat = predicate_catalog("vi")
    assert cat["ALLY_OF"] == "đồng minh của"
    assert cat["KILLED"] == "đã giết"
    assert len(cat) >= 20


def test_catalog_en_is_humanized():
    cat = predicate_catalog("en")
    assert cat["ALLY_OF"] == "ally of"
    assert cat["AT_WAR_WITH"] == "at war with"
