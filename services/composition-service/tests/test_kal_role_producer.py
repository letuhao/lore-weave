"""T37 — composition-service as a KAL command producer: the role write.

WHY THIS EXISTS
---------------
T36 defined roles as `entity_facts` rows with `fact_kind='relation'` and a story interval,
and measured the graph on 2026-08-11:

    attribute 41435 · name 5189 · alias 1868 · relation 0

`entity_facts_kind_chk` has always admitted `'relation'` and the KAL's `appendFact` has
always written any kind. **Nothing ever emitted one.** A schema that permits a row and a
writer that never emits one are indistinguishable from the database — which is exactly the
shape of every other "built but never wired" defect this plan has found (the vector provider
nothing constructed; `vector_hit_to_raw_hit` with zero callers; `VectorHit.vector` no caller
could request).

So these rules are about the PRODUCER, not the transport: that the payload is the shape the
contract declares, that a role cannot be written without a story position, and that the write
does not silently degrade.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.clients.kal_client import KalClient

BOOK = uuid4()
SUBJECT = uuid4()
EPISODE = uuid4()
USER = uuid4()


def _client(handler) -> KalClient:
    c = KalClient("http://kal.test", internal_token="t")
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                base_url="http://kal.test")
    return c


@pytest.mark.asyncio
async def test_the_role_write_sends_the_shape_the_CONTRACT_declares():
    """Asserted field-by-field against `AppendFactRequest`'s required list, because the two
    sides of this call are in different languages and nothing else relates them: the schema
    lives in `contracts/api/knowledge-gateway/kal.v1.yaml`, the caller in Python, the handler
    in TypeScript forwarding to Go. A missing or renamed key is a 4xx at runtime and green
    everywhere in between — the `cached_aliases`/`kind_code` class, one layer up.
    """
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = __import__("json").loads(request.content)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json={"fact_id": str(uuid4())})

    out = await _client(handler).append_role_fact(
        BOOK, subject_entity_id=SUBJECT, predicate="betrayed",
        object_value="Lâm Uyên", valid_from_ordinal=10_000_000,
        source_episode_id=EPISODE, user_id=USER,
    )

    assert seen["url"] == f"http://kal.test/v1/kal/books/{BOOK}/facts"
    body = seen["body"]
    # Exactly AppendFactRequest's `required` list.
    for key in ("entity_id", "fact_kind", "attr_or_predicate", "value",
                "valid_from_ordinal", "source_episode_id"):
        assert key in body, f"the contract requires {key!r} and the producer omitted it"
    assert body["fact_kind"] == "relation", (
        "the producer wrote a fact that is not a relation — T36's whole subject is the "
        "relation kind, of which the graph held ZERO")
    assert body["entity_id"] == str(SUBJECT)
    assert body["attr_or_predicate"] == "betrayed"
    assert body["value"] == "Lâm Uyên"
    assert body["valid_from_ordinal"] == 10_000_000
    assert seen["headers"].get("x-user-id") == str(USER), "tenancy header not sent"
    assert out["fact_id"]


@pytest.mark.asyncio
async def test_a_role_CANNOT_be_written_without_a_story_position():
    """`valid_from_ordinal` is a required keyword, not an optional one, and that is the
    lesson T36 Half 3 paid for: the KG's authoring path took no position at all, so every
    author-declared relation came out positionless — and an as-of read excludes positionless
    edges by design. **The roles that mattered most were the ones the canon check could never
    see.** A producer that could omit the position would reintroduce exactly that class.
    """
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover — never called
        return httpx.Response(200, json={})

    with pytest.raises(TypeError, match="valid_from_ordinal"):
        await _client(handler).append_role_fact(
            BOOK, subject_entity_id=SUBJECT, predicate="betrayed",
            object_value="Lâm Uyên", source_episode_id=EPISODE,
        )


@pytest.mark.asyncio
async def test_the_write_RAISES_rather_than_degrading_like_the_reads_do():
    """The opposite convention from `roster`, deliberately. A degraded READ gives the packer
    a thin cast and a visibly worse prompt; a dropped WRITE gives the canon guard a book in
    which the betrayal never happened, and the guard then passes a scene it should have
    questioned. A read may degrade; a write may not."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "unknown entity"})

    with pytest.raises(httpx.HTTPStatusError):
        await _client(handler).append_role_fact(
            BOOK, subject_entity_id=SUBJECT, predicate="betrayed",
            object_value="Lâm Uyên", valid_from_ordinal=10_000_000,
            source_episode_id=EPISODE,
        )


@pytest.mark.asyncio
async def test_writeback_key_is_sent_only_when_given():
    """Absent, not null. The KAL treats `writeback_key` as the Path-A idempotency gate; a
    key of `None` on the wire is a value the schema does not declare, and the same
    absent-vs-empty distinction `CastEntry.attributes` was made explicit for."""
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={})

    c = _client(handler)
    await c.append_role_fact(
        BOOK, subject_entity_id=SUBJECT, predicate="allied_with", object_value="X",
        valid_from_ordinal=1, source_episode_id=EPISODE)
    await c.append_role_fact(
        BOOK, subject_entity_id=SUBJECT, predicate="allied_with", object_value="X",
        valid_from_ordinal=1, source_episode_id=EPISODE, writeback_key="wb-1")

    assert "writeback_key" not in bodies[0]
    assert bodies[1]["writeback_key"] == "wb-1"


@pytest.mark.asyncio
async def test_source_episode_id_is_OMITTED_when_absent_never_invented():
    """🔴 **The rule the live smoke earned, and it cost a 500 to learn.**

    `entity_facts.source_episode_id` carries a FOREIGN KEY to `episodes`. The first cut of
    this producer took the field as REQUIRED — the contract declares it so — and the studio
    endpoint passed whatever it was handed. Driving the real path end to end returned:

        insert or update on table "entity_facts" violates foreign key constraint
        "entity_facts_source_episode_id_fkey"
        Key (source_episode_id)=(e8dfe19d-…) is not present in table "episodes"

    surfacing as a 502 at the KAL and a 500 at the author. **A plan-authored role has no
    episode** (Q2: *"plan-authored, not extracted"*), so inventing an id to satisfy a required
    field writes a provenance claim that is both false and unsatisfiable.

    NULL is the shape the core already expects: `appendFact`'s ON CONFLICT reads
    `coalesce(source_episode_id, '000…')`, which is only meaningful if NULL is normal — and a
    direct insert with NULL creates the `relation` row cleanly.

    Omitted, not `null`: the same absent-vs-empty distinction `CastEntry.attributes` and
    `writeback_key` are explicit about. A key the schema does not declare is a key the
    validator on the other side may reject.
    """
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={})

    c = _client(handler)
    await c.append_role_fact(
        BOOK, subject_entity_id=SUBJECT, predicate="betrayed", object_value="Lâm Uyên",
        valid_from_ordinal=12_000_000)
    await c.append_role_fact(
        BOOK, subject_entity_id=SUBJECT, predicate="betrayed", object_value="Lâm Uyên",
        valid_from_ordinal=12_000_000, source_episode_id=EPISODE)

    assert "source_episode_id" not in bodies[0], (
        "an author-declared role sent a source_episode_id it does not have — the column is "
        "an FK to `episodes`, so an invented id is a 500, not a provenance gap")
    assert bodies[1]["source_episode_id"] == str(EPISODE), (
        "an extracted role must still be able to cite its episode")
