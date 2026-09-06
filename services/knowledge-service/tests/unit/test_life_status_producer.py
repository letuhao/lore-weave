"""D-T32-ALIVE-NO-FACTS — the life-status producer.

`glossary_entities.alive` was the liveness signal and carried nothing: 7361 true /
0 false, never once set (it is a manual author toggle, not a derived column). The
graph DID know who had died — `:EntityStatus` rows with real story positions — and
`entity_facts` could hold that since T32 widened its CHECK to admit `'status'`.
Nothing ever wrote one: corpus-wide `attribute` 41536 · `name` 5202 · `alias` 1869
· **status 0**.

The gap was cross-pipeline: detection in knowledge, emission behind glossary's HTTP
boundary. These pin the projection between them.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.graph_repos.events import EVENT_ORDER_CHAPTER_STRIDE
from app.extraction.pass2_writer import Pass2WriteResult, StatusTransition


def test_a_transition_is_addressed_in_GLOSSARY_terms():
    """Not the Neo4j node id. `entity_facts.entity_id` is an FK to
    `glossary_entities`, so the graph's own id cannot address a fact row."""
    t = StatusTransition(glossary_entity_id="g-1", status="gone", chapter_ordinal=5)
    assert t.glossary_entity_id == "g-1" and t.status == "gone"


def test_the_ordinal_is_a_CHAPTER_ordinal_not_an_event_order():
    """THE conversion that must not drift. The graph's status axis is `event_order`
    (chapter × STRIDE + idx); `entity_facts.valid_from_ordinal` is a chapter ordinal
    (3, 4, 5 …). Both are plain ints, so passing the wrong one positions the fact a
    million chapters into the book and NOTHING complains."""
    event_order = 5 * EVENT_ORDER_CHAPTER_STRIDE + 17     # ch.5, 18th event
    assert event_order // EVENT_ORDER_CHAPTER_STRIDE == 5
    t = StatusTransition(glossary_entity_id="g", status="gone",
                         chapter_ordinal=event_order // EVENT_ORDER_CHAPTER_STRIDE)
    assert t.chapter_ordinal == 5, "a fact at 5_000_017 would be off by ~1M chapters"


def test_the_result_reports_transitions_and_defaults_to_none():
    """REPORTED, not written. The writer owns a Neo4j session and nothing else; the
    POST belongs to the layer that holds the glossary client, or a network call ends
    up inside a graph transaction that cannot roll back with it."""
    assert Pass2WriteResult(source_id="s").status_transitions == []


@pytest.mark.asyncio
async def test_the_client_reports_failure_rather_than_raising():
    """Best-effort by contract: the transition is already durable as an
    `:EntityStatus`, so a failed append is a gap to re-run, never a reason to 500 a
    persist that succeeded."""
    import httpx
    from app.clients.glossary_client import GlossaryClient

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"error": "boom"})

    client = GlossaryClient(
        base_url="http://glossary", internal_token="t", timeout_s=5.0, retries=0)
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://glossary")
    ok = await client.append_fact(
        uuid4(), entity_id=str(uuid4()), fact_kind="status",
        attr_or_predicate="life_status", value="gone", valid_from_ordinal=5)
    assert ok is False and len(calls) == 1


@pytest.mark.asyncio
async def test_the_append_sends_the_contracted_shape():
    import json as _json

    import httpx
    from app.clients.glossary_client import GlossaryClient

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(_json.loads(request.content))
        seen["_url"] = str(request.url)
        return httpx.Response(200, json={"fact_id": "f-1"})

    book, ent = uuid4(), uuid4()
    client = GlossaryClient(
        base_url="http://glossary", internal_token="t", timeout_s=5.0, retries=0)
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://glossary")
    ok = await client.append_fact(
        book, entity_id=str(ent), fact_kind="status",
        attr_or_predicate="life_status", value="gone", valid_from_ordinal=5)

    assert ok is True
    assert f"/internal/books/{book}/facts/append" in seen["_url"]
    assert seen["fact_kind"] == "status"
    assert seen["attr_or_predicate"] == "life_status"
    assert seen["value"] == "gone"
    assert seen["valid_from_ordinal"] == 5
    assert seen["cardinality"] == "single"
