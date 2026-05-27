"""P3 D5 — tests for is_abstract_query heuristic."""

from __future__ import annotations

import pytest

from app.context.intent.abstract_query import (
    ABSTRACT_KEYWORDS,
    is_abstract_query,
)


def test_empty_query_returns_false():
    assert is_abstract_query("") is False
    assert is_abstract_query("   ") is False


def test_explicit_theme_keyword_triggers_abstract():
    assert is_abstract_query("What are the themes of this book?") is True


def test_explicit_summary_keyword_triggers_abstract():
    assert is_abstract_query("Give me a summary of chapter 5.") is True


def test_explicit_arc_keyword_triggers_abstract():
    assert is_abstract_query("Walk me through the plot arc.") is True


def test_multi_word_keyword_main_idea_triggers_abstract():
    assert is_abstract_query("What is the main idea here?") is True


def test_short_specific_query_with_entity_returns_false():
    """Short query with a glossary entity is specific."""
    assert is_abstract_query(
        "What did Holmes say?",
        glossary_entities=["Holmes", "Watson"],
    ) is False


def test_short_query_without_keywords_or_entities_returns_false():
    """Short queries default to specific (preserves existing Mode-3 behavior)."""
    assert is_abstract_query("Where is the meeting?") is False


def test_long_query_no_glossary_entities_returns_abstract():
    """Long query (>20 tokens) + no glossary entities → abstract."""
    msg = " ".join(["word"] * 25)
    assert is_abstract_query(msg) is True
    assert is_abstract_query(msg, glossary_entities=[]) is True


def test_long_query_with_matching_glossary_entity_returns_specific():
    """Long query that mentions a known entity is specific, not abstract."""
    msg = "Tell me everything that happened to Holmes during the events of the third chapter of the second volume."
    assert is_abstract_query(msg, glossary_entities=["Holmes"]) is False


def test_long_query_with_non_matching_glossary_entities_returns_abstract():
    msg = " ".join(["word"] * 25)
    assert is_abstract_query(msg, glossary_entities=["Alice", "Bob"]) is True


def test_glossary_entity_match_is_case_insensitive():
    assert is_abstract_query(
        "Tell me about HOLMES and his methods of investigation across many chapters.",
        glossary_entities=["Holmes"],
    ) is False


def test_multi_word_entity_substring_match():
    """Entities like 'Sherlock Holmes' (multi-word) match via substring."""
    msg = "Long question about Sherlock Holmes spanning many tokens for the test."
    assert is_abstract_query(
        msg, glossary_entities=["Sherlock Holmes"],
    ) is False


def test_glossary_none_degrades_to_no_entity_for_long_query():
    """L1: glossary-service unavailable (None) → long query is abstract."""
    msg = " ".join(["word"] * 30)
    assert is_abstract_query(msg, glossary_entities=None) is True


def test_abstract_keywords_constant_includes_expected():
    """Sanity check: constants stay in sync with regex."""
    for kw in ("theme", "summary", "arc", "plot", "synopsis", "gist", "recap"):
        assert kw in ABSTRACT_KEYWORDS


def test_keyword_match_is_word_boundary_not_substring():
    """'summarize' matches; 'subsume' must NOT match."""
    assert is_abstract_query("Subsume the question into a different one.") is False
    assert is_abstract_query("Summarize the question.") is True


def test_empty_entity_string_in_list_is_ignored():
    """Defensive: glossary might return empty-string entities; skip them."""
    msg = " ".join(["word"] * 25)
    assert is_abstract_query(msg, glossary_entities=["", None]) is True  # type: ignore[list-item]
