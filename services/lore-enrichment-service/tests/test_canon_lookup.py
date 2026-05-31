"""C3 / F-C12-1 — wire the REAL contradiction canon-lookup (spec 2026-06-01).

The contradiction check was inert (`_canon_lookup` hardcoded `[]`). These tests
pin the real lookup: it reads the entity's AUTHORED glossary canon (description),
returns it as a CanonFact (with coarse CJK terms), caches the book's entities for
the run, and DEGRADES honestly (returns []) when there is no book_id / no canon /
a read error — so a down or empty glossary never produces a false-green.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.clients.glossary import GlossaryEntity
from app.verify.canon_lookup import extract_canon_terms, make_glossary_canon_lookup


# ── coarse CJK term extraction ────────────────────────────────────────────────

def test_extract_terms_pulls_specific_nouns_not_the_name():
    # "蓬萊位于东海。" → drops the particle 位于, yields the specific canon token 东海;
    # the entity name is excluded (negating an entity's own name is not a signal).
    terms = extract_canon_terms("蓬萊位于东海。", entity_name="蓬萊")
    assert "东海" in terms
    assert "蓬萊" not in terms


def test_extract_terms_empty_is_empty():
    assert extract_canon_terms("", entity_name="蓬萊") == ()
    assert extract_canon_terms("   ", entity_name="蓬萊") == ()


def test_extract_terms_latin_keeps_proper_nouns_drops_common_words():
    # review-impl MED#1: only PROPER-NOUN-like (Capitalized) tokens become terms,
    # so common words can't drive a false-positive contradiction auto-reject.
    terms = extract_canon_terms(
        "Englishman traveling to Transylvania to meet Count Dracula on business",
        entity_name="Jonathan Harker",
    )
    assert "Transylvania" in terms and "Dracula" in terms  # specific proper nouns
    # common lowercase words must NOT be terms (the false-positive surface):
    for common in ("traveling", "meet", "business", "to", "on"):
        assert common not in terms
    assert "Harker" not in terms  # the entity's own name word


# ── cached glossary canon lookup ──────────────────────────────────────────────

class _FakeGlossary:
    def __init__(self, entities):
        self._entities = entities
        self.calls = 0

    async def list_entities(self, *, book_id, limit=200):
        self.calls += 1
        return self._entities


@pytest.mark.asyncio
async def test_lookup_returns_canon_fact_from_description():
    g = _FakeGlossary([GlossaryEntity(entity_id="e1", name="蓬萊", kind="location",
                                      description="蓬萊位于东海。")])
    lookup = make_glossary_canon_lookup(g, book_id=uuid4())  # type: ignore[arg-type]
    facts = await lookup("蓬萊", "历史")
    assert len(facts) == 1
    assert facts[0].assertion == "蓬萊位于东海。"
    assert "东海" in facts[0].terms


@pytest.mark.asyncio
async def test_lookup_caches_entities_across_calls():
    g = _FakeGlossary([GlossaryEntity(entity_id="e1", name="蓬萊", description="蓬萊位于东海。")])
    lookup = make_glossary_canon_lookup(g, book_id=uuid4())  # type: ignore[arg-type]
    await lookup("蓬萊", "历史")
    await lookup("蓬萊", "地理")  # same entity, different dimension
    assert g.calls == 1  # the book's entities were fetched ONCE, then cached


@pytest.mark.asyncio
async def test_lookup_empty_description_returns_empty():
    g = _FakeGlossary([GlossaryEntity(entity_id="e1", name="蓬萊", description="")])
    lookup = make_glossary_canon_lookup(g, book_id=uuid4())  # type: ignore[arg-type]
    assert await lookup("蓬萊", "历史") == []  # no authored canon → can't contradict


@pytest.mark.asyncio
async def test_lookup_unknown_entity_returns_empty():
    g = _FakeGlossary([GlossaryEntity(entity_id="e1", name="玉虛宮", description="x")])
    lookup = make_glossary_canon_lookup(g, book_id=uuid4())  # type: ignore[arg-type]
    assert await lookup("蓬萊", "历史") == []  # not in the book


@pytest.mark.asyncio
async def test_lookup_no_book_id_returns_empty():
    g = _FakeGlossary([GlossaryEntity(entity_id="e1", name="蓬萊", description="蓬萊位于东海。")])
    lookup = make_glossary_canon_lookup(g, book_id=None)  # type: ignore[arg-type]
    assert await lookup("蓬萊", "历史") == []  # no scope → honest degrade
    assert g.calls == 0


@pytest.mark.asyncio
async def test_lookup_read_error_raises_for_degrade():
    class _Boom:
        async def list_entities(self, *, book_id, limit=200):
            raise RuntimeError("glossary down")

    lookup = make_glossary_canon_lookup(_Boom(), book_id=uuid4())  # type: ignore[arg-type]
    # a read error PROPAGATES so the verifier's _lookup_canon records verify_degraded
    # (a swallowed error would look like "no canon" → false-green). See canon_verify.
    with pytest.raises(RuntimeError):
        await lookup("蓬萊", "历史")
