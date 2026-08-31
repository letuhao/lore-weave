"""mui #4 K-1 — unit tests for select_glossary_semantic (no Neo4j/embed/HTTP).

Mocks the embed client, patches find_entities_by_vector INSIDE the adapter (T17 —
the selector reaches entity vectors through `VectorStore` now, so patching the real
repo call one layer down drives the actual VectorSearchHit -> VectorHit mapping instead
of bypassing it), mocks the glossary
client's by-ids fetch. Asserts ranking, anchor-only filtering, and the
best-effort fallback-to-[] on each failure mode.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.context.query_embedding as qe_mod
from app.clients.glossary_client import GlossaryEntityForContext
from app.context.selectors import glossary as gsel
from app.db.graph_repos.entities import Entity, VectorSearchHit

USER = uuid4()
PROJECT = uuid4()
BOOK = uuid4()


@pytest.fixture(autouse=True)
def _clear_query_embedding_cache():
    # MED-2 shared cache is module-global — isolate tests so a cache hit from
    # one test doesn't skip the embed path another test is asserting on.
    qe_mod._query_embedding_cache.clear()
    yield
    qe_mod._query_embedding_cache.clear()


def _hit(gid: str | None, name: str, score: float, anchor: float = 1.0) -> VectorSearchHit:
    ent = Entity(
        id=f"canon-{name}",
        user_id=str(USER),
        project_id=str(PROJECT),
        name=name,
        canonical_name=name,
        kind="character",
        glossary_entity_id=gid,
        # T17 — a REAL anchor, because the ranking product is now computed by the caller from
        # `raw_score` and `attributes["anchor_score"]` rather than read off a `weighted_score`
        # the fixture invented. With `anchor_score` left at its 0.0 default every weighted
        # score was 0.0 and the ordering assertion collapsed to insertion order — i.e. the old
        # fixture's `weighted_score=score` was asserting on a number no backend produces.
        anchor_score=anchor,
    )
    return VectorSearchHit(entity=ent, raw_score=score, weighted_score=score * anchor)


def _embed_ok(vector=(0.1, 0.2, 0.3)):
    client = MagicMock()
    client.embed = AsyncMock(return_value=SimpleNamespace(embeddings=[list(vector)]))
    return client


def _glossary_with(rows: list[GlossaryEntityForContext]):
    client = MagicMock()
    client.fetch_entities_by_ids = AsyncMock(return_value=rows)
    return client


def _row(eid: str, name: str) -> GlossaryEntityForContext:
    return GlossaryEntityForContext(entity_id=eid, cached_name=name, kind_code="character")


async def _run(monkeypatch, *, hits, rows, embed=None, model="emb-uuid", dim=1024, query="封神之人"):
    monkeypatch.setattr("app.adapters.neo4j_vector_store.find_entities_by_vector", AsyncMock(return_value=hits))
    return await gsel.select_glossary_semantic(
        session=MagicMock(),
        embedding_client=embed or _embed_ok(),
        glossary_client=_glossary_with(rows),
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model=model, embedding_dimension=dim,
        query=query, max_entities=20,
    )


@pytest.mark.asyncio
async def test_ranks_by_weighted_score_and_enriches(monkeypatch):
    hits = [_hit("g1", "姜子牙", 0.7), _hit("g2", "哪吒", 0.9)]  # out of order
    rows = [_row("g1", "姜子牙"), _row("g2", "哪吒")]
    out = await _run(monkeypatch, hits=hits, rows=rows)
    # ordered by weighted_score desc → g2 (0.9) then g1 (0.7)
    assert [e.entity_id for e in out] == ["g2", "g1"]
    assert out[0].tier == "semantic"
    assert out[0].rank_score == 0.9


@pytest.mark.asyncio
async def test_drops_unanchored_hits(monkeypatch):
    # AC6 — a hit with glossary_entity_id=None must not leak into context.
    hits = [_hit(None, "discovered-only", 0.95), _hit("g1", "姜子牙", 0.5)]
    rows = [_row("g1", "姜子牙")]
    out = await _run(monkeypatch, hits=hits, rows=rows)
    assert [e.entity_id for e in out] == ["g1"]


@pytest.mark.asyncio
async def test_no_embedding_model_returns_empty(monkeypatch):
    embed = _embed_ok()
    out = await _run(monkeypatch, hits=[], rows=[], embed=embed, model=None)
    assert out == []
    embed.embed.assert_not_awaited()  # short-circuits before embedding


@pytest.mark.asyncio
async def test_blank_query_returns_empty(monkeypatch):
    embed = _embed_ok()
    out = await _run(monkeypatch, hits=[], rows=[], embed=embed, query="   ")
    assert out == []
    embed.embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_embed_failure_falls_back_to_empty(monkeypatch):
    embed = MagicMock()
    embed.embed = AsyncMock(side_effect=RuntimeError("provider down"))
    out = await _run(monkeypatch, hits=[_hit("g1", "x", 0.9)], rows=[_row("g1", "x")], embed=embed)
    assert out == []


@pytest.mark.asyncio
async def test_respects_max_tokens(monkeypatch):
    # MED-1 — semantic results are trimmed to the token budget (parity with
    # FTS select-for-context). Three ~40-token entities; budget 50 keeps 1.
    big = "描述" * 20  # 40 CJK chars ≈ 40 tokens
    hits = [_hit("g1", "甲", 0.9), _hit("g2", "乙", 0.8), _hit("g3", "丙", 0.7)]
    rows = [
        GlossaryEntityForContext(entity_id=f"g{i}", cached_name="甲", kind_code="character", short_description=big)
        for i in (1, 2, 3)
    ]
    monkeypatch.setattr("app.adapters.neo4j_vector_store.find_entities_by_vector", AsyncMock(return_value=hits))
    out = await gsel.select_glossary_semantic(
        session=MagicMock(), embedding_client=_embed_ok(), glossary_client=_glossary_with(rows),
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model="m", embedding_dimension=1024, query="q",
        max_entities=20, max_tokens=50,
    )
    assert [e.entity_id for e in out] == ["g1"]  # only the top-ranked fits


@pytest.mark.asyncio
async def test_no_anchored_hits_returns_empty_without_fetch(monkeypatch):
    gc = _glossary_with([])
    monkeypatch.setattr("app.adapters.neo4j_vector_store.find_entities_by_vector", AsyncMock(return_value=[_hit(None, "x", 0.9)]))
    out = await gsel.select_glossary_semantic(
        session=MagicMock(), embedding_client=_embed_ok(), glossary_client=gc,
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model="m", embedding_dimension=1024, query="q",
    )
    assert out == []
    gc.fetch_entities_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_ANCHOR_reorders_the_ranking_not_just_scales_it(monkeypatch):
    """🔴 **Dropping the anchor multiplication redded NOTHING before this rule.** Every other
    fixture here used `anchor=1.0`, so `score * anchor == score` and the two-layer product was
    indistinguishable from raw cosine — the whole point of two-layer retrieval, untested.

    So the two orderings are made to DISAGREE:

        A  raw .9  anchor .2  ->  weighted .18
        B  raw .5  anchor 1.0 ->  weighted .50

    Raw cosine ranks A first; the weighted product ranks B first. A selector that silently
    stopped applying the anchor would return a plausible list in the wrong order, which is
    exactly the failure `PgVectorStore` omits the key to prevent (D-T25B-PG-ANCHOR-SCORE).
    """
    hits = [_hit("gA", "姜子牙", 0.9, anchor=0.2), _hit("gB", "哪吒", 0.5, anchor=1.0)]
    rows = [_row("gA", "姜子牙"), _row("gB", "哪吒")]
    out = await _run(monkeypatch, hits=hits, rows=rows)
    assert [e.entity_id for e in out] == ["gB", "gA"], (
        "ranked by RAW cosine, not by raw × anchor — two-layer retrieval collapsed to one "
        f"layer. got {[e.entity_id for e in out]}, weighted gives ['gB', 'gA']")
    assert out[0].rank_score == pytest.approx(0.5)
    assert out[1].rank_score == pytest.approx(0.18)


@pytest.mark.asyncio
async def test_a_backend_that_OMITS_anchor_score_raises_rather_than_ranking_by_cosine(monkeypatch):
    """The other half, and the reason the lookup is a bracket rather than `.get`.

    `PgVectorStore` leaves `anchor_score` out of an entity hit entirely — the score is
    bucket-relative and any copy on the vector row drifts. A consumer that defaulted the
    missing key would return cosine order and look perfectly healthy. This pins that the
    selector RAISES instead, which is the loud failure the omission was designed to produce.
    """
    from app.ports.vector_store import VectorHit

    async def _no_anchor(*a, **kw):
        return [VectorHit(record_id="e1", score=0.9, scope="entity",
                          attributes={"glossary_entity_id": "gA"})]

    monkeypatch.setattr(gsel, "get_vector_store", AsyncMock(
        return_value=SimpleNamespace(search=_no_anchor)))
    with pytest.raises(KeyError, match="anchor_score"):
        await gsel.select_glossary_semantic(
            session=MagicMock(), embedding_client=_embed_ok(),
            glossary_client=_glossary_with([_row("gA", "姜子牙")]),
            user_id=USER, project_id=PROJECT, book_id=BOOK,
            embedding_model="emb-uuid", embedding_dimension=1024,
            query="封神之人", max_entities=20,
        )
