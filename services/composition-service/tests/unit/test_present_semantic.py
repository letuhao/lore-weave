"""mui #4 C-1 — gather_present uses knowledge semantic bios first, falls back
to glossary FTS select-for-context on empty/failure (AC4/AC5). Self-contained
stubs; no network."""

from __future__ import annotations

import uuid

import pytest

from app.packer.lenses import gather_present

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
BOOK = uuid.uuid4()


class StubGlossary:
    def __init__(self, bios):
        self._bios = bios
        self.called = False

    async def select_for_context(self, book_id, user_id, query, **kw):
        self.called = True
        return self._bios


class StubKnowledge:
    def __init__(self, semantic_bios):
        self._semantic = semantic_bios

    async def glossary_semantic(self, user_id, *, project_id, query, **kw):
        return self._semantic

    async def get_entity(self, bearer, entity_id):
        return None


async def _present(glossary, knowledge):
    return await gather_present(
        glossary, knowledge,
        book_id=BOOK, user_id=USER, project_id=PROJECT, bearer="jwt",
        query="封神之人", present_entity_ids=[],
    )


@pytest.mark.asyncio
async def test_semantic_bios_used_and_glossary_not_called():
    g = StubGlossary([{"entity_id": "g-fts", "cached_name": "FTS", "short_description": "should not appear"}])
    k = StubKnowledge([{"entity_id": "s1", "cached_name": "哪吒", "short_description": "lotus prince"}])
    present, _seen = await _present(g, k)
    assert [p["entity_id"] for p in present] == ["s1"]
    assert present[0]["summary"] == "lotus prince"
    assert g.called is False  # semantic-first → no FTS round trip


@pytest.mark.asyncio
async def test_falls_back_to_glossary_fts_when_semantic_empty():
    g = StubGlossary([{"entity_id": "g1", "cached_name": "Kael", "short_description": "a knight"}])
    k = StubKnowledge([])  # no embeddings / degraded → []
    present, _seen = await _present(g, k)
    assert [p["entity_id"] for p in present] == ["g1"]
    assert g.called is True  # fell back to FTS
