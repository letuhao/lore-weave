"""T25p / spec §3.3c — `anchor_score` on a Postgres entity hit, JOINED not copied.

`PgVectorStore` still refuses to store `anchor_score`: it is `mention_count / max(mention_count)`
across a bucket, so it changes when a DIFFERENT entity's count moves and a copy on the vector
row drifts by construction. `test_vector_primary_owns_anchor_score.py` guards that and is
untouched by this file. What T25p adds is the other half — reading it from its AUTHORITY, for
exactly the hits a search returned.

⚠️ **The safeguard is the subject of these tests, not the feature.** `glossary.py` ranks by
`h.score * float(h.attributes["anchor_score"] or 0.0)` with a BRACKET, so:

    key ABSENT   -> KeyError, loud, the ranking stops
    key = None   -> 0.0, a genuinely un-anchored entity, matching the Neo4j arm
    key = 0.0    -> 0.0, indistinguishable from the above BY DESIGN

which means a resolver that fails and returns "no anchors" would turn every weighted score into
zero and hand back raw cosine order — correct-looking, silently wrong. So the tests below are
mostly about what must NOT happen.
"""

from __future__ import annotations

from unittest import mock

import pytest

from app.adapters.pg_vector_store import PgVectorStore

_USER = "u-1"


def _rows(*ids):
    return [{"record_id": i, "score": 0.9, "project_id": "p-1", "archived": False} for i in ids]


def _store_over(rows, **kw):
    """A store whose pool returns `rows`, so the search path runs without a database."""
    conn = mock.AsyncMock()
    conn.fetch = mock.AsyncMock(return_value=rows)
    acq = mock.MagicMock()
    acq.__aenter__ = mock.AsyncMock(return_value=conn)
    acq.__aexit__ = mock.AsyncMock(return_value=False)
    pool = mock.MagicMock()
    pool.acquire = mock.MagicMock(return_value=acq)
    return PgVectorStore(pool=pool, search_effort=False, **kw)


async def _search(store):
    return await store.search(
        user_id=_USER, embedding=[0.1] * 1024, dim=1024, k=5, scope="entity")


@pytest.mark.asyncio
async def test_WITHOUT_a_resolver_the_key_stays_ABSENT():
    """The pre-T25p contract, and the one that must not regress. Absent means the consumer
    RAISES; present-but-None means it ranks by zero. Adding the feature must not quietly
    convert the first into the second for deployments that supply no resolver."""
    hits = await _search(_store_over(_rows("e1", "e2")))
    assert hits, "the fixture returned no hits, so this test would pass vacuously"
    for h in hits:
        assert "anchor_score" not in h.attributes


@pytest.mark.asyncio
async def test_WITH_a_resolver_each_hit_carries_its_own_score():
    """And they must not be transposed: two hits, two different scores, checked per id."""
    async def resolver(user_id, ids):
        assert user_id == _USER
        return {"e1": 0.7727272727272727, "e2": 0.25}

    hits = await _search(_store_over(_rows("e1", "e2"), anchor_scores=resolver))
    got = {h.record_id: h.attributes["anchor_score"] for h in hits}
    assert got == {"e1": 0.7727272727272727, "e2": 0.25}


@pytest.mark.asyncio
async def test_the_resolver_is_asked_for_EXACTLY_the_hits_returned():
    """Bounded by k. A resolver handed the whole table would scan the tenant on every search,
    and the reason this is a per-hit lookup rather than a join is that it stays bounded."""
    seen: list[list[str]] = []

    async def resolver(user_id, ids):
        seen.append(list(ids))
        return {}

    await _search(_store_over(_rows("e1", "e2", "e3"), anchor_scores=resolver))
    assert seen == [["e1", "e2", "e3"]]


@pytest.mark.asyncio
async def test_an_entity_the_AUTHORITY_does_not_know_is_None_not_absent_and_not_zero():
    """`None` is the un-anchored value the Neo4j arm already returns
    (`getattr(h.entity, "anchor_score", None)`), and `glossary.py`'s `or 0.0` is written to
    treat it as a real number. Omitting the key for one hit instead would raise on a perfectly
    ordinary entity."""
    async def resolver(user_id, ids):
        return {"e1": 1.0}                      # e2 is not in the graph at all

    hits = await _search(_store_over(_rows("e1", "e2"), anchor_scores=resolver))
    by_id = {h.record_id: h for h in hits}
    assert by_id["e2"].attributes["anchor_score"] is None
    assert "anchor_score" in by_id["e2"].attributes


@pytest.mark.asyncio
async def test_a_resolver_that_RAISES_propagates_and_is_not_swallowed():
    """⚠️ The one that matters. Catching this and returning `{}` would give every hit
    `anchor_score = None`, `glossary.py` would multiply every score by 0.0, and the block
    would come back in RAW COSINE ORDER — a wrong ranking that looks exactly like a right
    one. A backend outage must be an error, not a re-ranking."""
    async def resolver(user_id, ids):
        raise RuntimeError("graph unreachable")

    with pytest.raises(RuntimeError, match="graph unreachable"):
        await _search(_store_over(_rows("e1"), anchor_scores=resolver))


@pytest.mark.asyncio
async def test_a_PASSAGE_search_never_consults_the_resolver():
    """Passage ranking is single-layer — `anchor_score` is meaningless there, and asking for
    it would cost a round trip per search to decorate hits nothing reads."""
    called = False

    async def resolver(user_id, ids):
        nonlocal called
        called = True
        return {}

    store = _store_over(
        [{"record_id": "p1", "score": 0.5, "text": "t", "source_type": "chapter",
          "source_id": "s", "chunk_index": 0, "is_hub": False, "chapter_index": 1,
          "canon": True, "source_lang": "en", "project_id": "p-1",
          "created_at": None, "block_index": 0}],
        anchor_scores=resolver)
    await store.search(user_id=_USER, embedding=[0.1] * 1024, dim=1024, k=5, scope="passage")
    assert called is False


@pytest.mark.asyncio
async def test_no_hits_means_no_resolver_call():
    """An empty search must not pay for a lookup of nothing."""
    called = False

    async def resolver(user_id, ids):
        nonlocal called
        called = True
        return {}

    assert await _search(_store_over([], anchor_scores=resolver)) == []
    assert called is False
