"""Unit tests for wiki citation provenance (wiki-llm M4)."""
from __future__ import annotations

import pytest

from app.wiki.cite import compose_provenance_cites, used_cite_ids
from app.wiki.ir import Source
from app.wiki.parse import parse_article


def _sources():
    return [
        Source(cite_id="G1", kind="glossary", snippet="canon desc"),
        Source(cite_id="P1", kind="passage", chapter_id="c1", block_index=2,
               chapter_sort_order=3, score=0.9, snippet="passage one"),
        Source(cite_id="P2", kind="passage", chapter_id="c2", block_index=5,
               chapter_sort_order=7, score=0.5, snippet="uncited passage"),
    ]


def _ir(markdown):
    return parse_article(markdown, entity_id="e", display_name="x", sources=_sources())


def test_used_cite_ids():
    ir = _ir("Lead [G1]. More detail [P1].")
    assert used_cite_ids(ir) == {"G1", "P1"}


@pytest.mark.asyncio
async def test_compose_excludes_uncited():
    ir = _ir("Lead [G1]. More detail [P1].")  # P2 never cited
    cites = await compose_provenance_cites(ir)
    ids = {c.source_id for c in cites}
    assert "c2" not in ids        # P2 (uncited) dropped
    assert "c1" in ids and "G1" in ids


@pytest.mark.asyncio
async def test_compose_ranks_authored_canon_first():
    ir = _ir("Lead [G1]. More detail [P1].")
    cites = await compose_provenance_cites(ir)
    # glossary canon (score None) ranks ahead of the scored passage
    assert cites[0].source_type == "glossary_entity"
    assert cites[0].score is None


@pytest.mark.asyncio
async def test_compose_maps_passage_anchor():
    ir = _ir("Detail [P1].")
    cites = await compose_provenance_cites(ir)
    c = next(c for c in cites if c.source_type == "chapter")
    assert c.chapter_id == "c1"
    assert c.chapter_index == 3        # chapter_sort_order
    assert c.block_or_line == "2"      # block_index
    assert c.score == 0.9


@pytest.mark.asyncio
async def test_compose_empty_when_nothing_cited():
    ir = _ir("Plain prose with no citations at all here.")
    assert await compose_provenance_cites(ir) == []
