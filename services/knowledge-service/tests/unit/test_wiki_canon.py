"""Unit tests for the wiki canon-lookup (wiki-llm M4)."""
from __future__ import annotations

import pytest

from app.wiki.canon import extract_canon_terms, make_canon_lookup
from app.wiki.context import EntityBrief


def test_extract_terms_excludes_entity_name_latin():
    terms = extract_canon_terms("Dracula lived in Transylvania", entity_name="Dracula")
    assert "Dracula" not in terms
    assert "Transylvania" in terms


def test_extract_terms_drops_lowercase_common_words():
    # Only Capitalized proper-noun-like tokens are kept (common words would
    # over-fire the contradiction heuristic).
    terms = extract_canon_terms("a traveling merchant who sells goods", entity_name="X")
    assert terms == ()


def test_extract_terms_cjk_proper_nouns():
    # jieba proper-noun extraction (lazy-loaded). The entity's own name is excluded.
    terms = extract_canon_terms("姜子牙辅佐周武王讨伐商纣王", entity_name="姜子牙")
    assert "姜子牙" not in terms
    assert isinstance(terms, tuple)


def test_extract_terms_empty():
    assert extract_canon_terms("", entity_name="x") == ()
    assert extract_canon_terms("   ", entity_name="x") == ()


@pytest.mark.asyncio
async def test_make_canon_lookup_returns_canon_fact():
    brief = EntityBrief(entity_id="e", name="姜子牙", short_description="周朝丞相，辅佐周武王")
    facts = await make_canon_lookup(brief)("姜子牙", "body")
    assert len(facts) == 1
    assert facts[0].entity_name == "姜子牙"
    assert facts[0].assertion == "周朝丞相，辅佐周武王"


@pytest.mark.asyncio
async def test_make_canon_lookup_no_canon_returns_empty():
    # Empty short_description → no canon known → [] (genuine, not degraded).
    facts = await make_canon_lookup(EntityBrief(entity_id="e", name="x"))("x", "body")
    assert facts == []
