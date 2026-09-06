"""X2 — unit tests for the KAL (knowledge-gateway) read client + the
KAL-routed `GlossaryClient.list_entities` cast read. NO network: all HTTP is
mocked via respx (the proven client-test pattern)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import respx

from app.clients.glossary import GlossaryClient, GlossaryServiceError
from app.clients.kal import KalClient, KalServiceError

KAL = "http://knowledge-gateway:3000"
GL = "http://glossary-service:8088"

# Fengshen CJK round-trip canaries.
FENGSHEN_PLACES = ["玉虛宮", "碧遊宮", "金鰲島", "蓬萊", "陳塘關"]


def _kal() -> KalClient:
    return KalClient(base_url=KAL, internal_token="test-internal")


# ── roster: drains next_cursor to completion ───────────────────────────────────


@respx.mock
async def test_roster_drains_all_pages_until_cursor_null():
    book = uuid4()
    route = respx.get(f"{KAL}/v1/kal/books/{book}/roster")
    route.side_effect = [
        httpx.Response(200, json={"items": [{"entity_id": "e1", "name": "玉虛宮"}], "next_cursor": "c1"}),
        httpx.Response(200, json={"items": [{"entity_id": "e2", "name": "金鰲島"}], "next_cursor": "c2"}),
        httpx.Response(200, json={"items": [{"entity_id": "e3", "name": "蓬萊"}], "next_cursor": None}),
    ]
    c = _kal()
    rows = await c.roster(book_id=book)
    await c.aclose()
    assert [r.entity_id for r in rows] == ["e1", "e2", "e3"]
    assert [r.name for r in rows] == ["玉虛宮", "金鰲島", "蓬萊"]
    # 3 pages fetched (drained to completion)
    assert route.call_count == 3
    # the 2nd+ requests carry the prior page's cursor
    assert "cursor=c1" in str(route.calls[1].request.url)
    assert "cursor=c2" in str(route.calls[2].request.url)


@respx.mock
async def test_roster_single_page_no_cursor_stops():
    book = uuid4()
    route = respx.get(f"{KAL}/v1/kal/books/{book}/roster").respond(
        200, json={"items": [{"entity_id": "e1", "name": "陳塘關"}]}
    )
    c = _kal()
    rows = await c.roster(book_id=book)
    await c.aclose()
    assert route.call_count == 1  # absent next_cursor → one page only
    assert len(rows) == 1 and rows[0].name == "陳塘關"


@respx.mock
async def test_roster_forwards_internal_token_and_user_id():
    book, uid = uuid4(), uuid4()
    route = respx.get(f"{KAL}/v1/kal/books/{book}/roster").respond(200, json={"items": []})
    c = _kal()
    await c.roster(book_id=book, user_id=uid)
    await c.aclose()
    req = route.calls.last.request
    assert req.headers["X-Internal-Token"] == "test-internal"
    assert req.headers["X-User-Id"] == str(uid)


@respx.mock
async def test_roster_503_raises_retryable():
    book = uuid4()
    respx.get(f"{KAL}/v1/kal/books/{book}/roster").respond(503)
    c = _kal()
    with pytest.raises(KalServiceError) as exc:
        await c.roster(book_id=book)
    await c.aclose()
    assert exc.value.retryable is True


@respx.mock
async def test_roster_timeout_raises_retryable():
    book = uuid4()
    respx.get(f"{KAL}/v1/kal/books/{book}/roster").mock(
        side_effect=httpx.TimeoutException("boom")
    )
    c = _kal()
    with pytest.raises(KalServiceError) as exc:
        await c.roster(book_id=book)
    await c.aclose()
    assert exc.value.retryable is True


# ── get_facts / get_canonical / search ─────────────────────────────────────────


@respx.mock
async def test_get_facts_parses_items_and_as_of():
    book, ent = uuid4(), uuid4()
    route = respx.get(f"{KAL}/v1/kal/books/{book}/entities/{ent}/facts").respond(
        200,
        json={
            "items": [
                {"fact_id": "f1", "entity_id": str(ent), "fact_kind": "attribute",
                 "attr_or_predicate": "affiliation", "value": "闡教",
                 "valid_from_ordinal": 1, "valid_to_ordinal": None, "cardinality": "single"},
            ],
            "temporal_capability": {"glossary": "ordinal_valid_time", "kg": "temporal_unsupported"},
        },
    )
    c = _kal()
    facts = await c.get_facts(book_id=book, entity_id=ent, as_of=5)
    await c.aclose()
    assert len(facts) == 1
    assert facts[0].value == "闡教" and facts[0].valid_to_ordinal is None
    assert "as_of=5" in str(route.calls.last.request.url)


@respx.mock
async def test_get_canonical_parses_snapshot():
    book, ent = uuid4(), uuid4()
    respx.get(f"{KAL}/v1/kal/books/{book}/entities/{ent}/canonical").respond(
        200,
        json={"entity_id": str(ent), "content": "玉虛宮 lore", "as_of_ordinal": 12,
              "canonical_status": "current"},
    )
    c = _kal()
    snap = await c.get_canonical(book_id=book, entity_id=ent)
    await c.aclose()
    assert snap.content == "玉虛宮 lore" and snap.canonical_status == "current"


@respx.mock
async def test_search_parses_items():
    book = uuid4()
    respx.get(f"{KAL}/v1/kal/books/{book}/search").respond(
        200, json={"items": [{"entity_id": "e1", "name": "蓬萊", "kind": "location"}]}
    )
    c = _kal()
    rows = await c.search(book_id=book, query="蓬萊", k=5)
    await c.aclose()
    assert rows[0].name == "蓬萊" and rows[0].kind == "location"


# ── GlossaryClient.list_entities routes the cast via the KAL roster ────────────


@respx.mock
async def test_list_entities_via_kal_roster_drains_and_merges_fields():
    """With a KAL configured, the COMPLETE cast (id+name) comes from the drained
    KAL roster; kind + authored short_description merge from the field map.

    T38 B3 — that field map now comes from the KAL's `cast` read rather than a direct
    glossary `/internal/.../entities` page. The MERGE behaviour under test is unchanged; only
    the source of the fields moved, which is exactly what a migration should look like from a
    test's point of view."""
    book = uuid4()
    # field map (kind + short_description) — only e1, e2 here.
    respx.get(f"{KAL}/v1/kal/books/{book}/cast").respond(
        200,
        json={"items": [
            {"entity_id": "e1", "name": "玉虛宮", "kind": "location",
             "short_description": "闡教 HQ"},
            {"entity_id": "e2", "name": "金鰲島", "kind": "location",
             "short_description": "截教 base"},
        ], "next_cursor": None},
    )
    # KAL roster drains 2 pages → e1, e2, e3 (e3 created after the legacy page).
    roster = respx.get(f"{KAL}/v1/kal/books/{book}/roster")
    roster.side_effect = [
        httpx.Response(200, json={"items": [
            {"entity_id": "e1", "name": "玉虛宮"}, {"entity_id": "e2", "name": "金鰲島"},
        ], "next_cursor": "c1"}),
        httpx.Response(200, json={"items": [{"entity_id": "e3", "name": "蓬萊"}], "next_cursor": None}),
    ]
    g = GlossaryClient(base_url=GL, internal_token="t", kal_base_url=KAL)
    rows = await g.list_entities(book_id=book)
    await g.aclose()

    assert [r.entity_id for r in rows] == ["e1", "e2", "e3"]
    # fields merged from the glossary projection
    assert rows[0].kind == "location" and rows[0].description == "闡教 HQ"
    assert rows[1].description == "截教 base"
    # e3 is in the roster (complete cast) but not the legacy page → empty fields,
    # NOT dropped (the drain is the authoritative complete cast).
    assert rows[2].name == "蓬萊" and rows[2].kind == "" and rows[2].description == ""


@respx.mock
async def test_list_entities_REFUSES_without_a_kal_rather_than_answering_emptily():
    """T38 B3 — the direct-glossary fallback is GONE, and its absence is a REFUSAL.

    It was already unreachable (`knowledge_gateway_url` has a default and both construction
    sites pass it), and while the path existed the reader gate correctly refused to shrink.
    Returning `[]` for a KAL-less client would read as "this book has no cast" — the same
    shape as the silent truncation the whole drain exists to end.
    """
    book = uuid4()
    g = GlossaryClient(base_url=GL, internal_token="t")   # no kal_base_url
    with pytest.raises(GlossaryServiceError) as exc:
        await g.list_entities(book_id=book)
    await g.aclose()
    assert exc.value.retryable is False
    assert "INV-KAL" in str(exc.value)

@respx.mock
async def test_list_entities_kal_failure_surfaces_as_glossary_error():
    """A KAL read failure must surface as GlossaryServiceError so the caller's
    existing degrade path (verify_degraded / empty grounding) fires — never a
    silent false-green."""
    book = uuid4()
    # T38 B3 — the field map moved to the KAL's `cast`; the roster failure is still the one
    # under test, so `cast` is mocked healthy and `roster` is the thing that 503s.
    respx.get(f"{KAL}/v1/kal/books/{book}/cast").respond(200, json={"items": [], "next_cursor": None})
    respx.get(f"{KAL}/v1/kal/books/{book}/roster").respond(503)
    g = GlossaryClient(base_url=GL, internal_token="t", kal_base_url=KAL)
    with pytest.raises(GlossaryServiceError) as exc:
        await g.list_entities(book_id=book)
    await g.aclose()
    assert exc.value.retryable is True


@respx.mock
async def test_list_entities_via_kal_cjk_round_trips():
    book = uuid4()
    respx.get(f"{KAL}/v1/kal/books/{book}/cast").respond(200, json={"items": [], "next_cursor": None})
    items = [{"entity_id": f"e{i}", "name": n} for i, n in enumerate(FENGSHEN_PLACES)]
    respx.get(f"{KAL}/v1/kal/books/{book}/roster").respond(
        200, json={"items": items, "next_cursor": None}
    )
    g = GlossaryClient(base_url=GL, internal_token="t", kal_base_url=KAL)
    rows = await g.list_entities(book_id=book)
    await g.aclose()
    assert [r.name for r in rows] == FENGSHEN_PLACES
