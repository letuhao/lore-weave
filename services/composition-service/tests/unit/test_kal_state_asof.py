"""Unit tests for the KAL `state@as_of` read and the canon bible built from it (plan T7).

The defect this closes: every canon bible composition rendered was built from `roster` — an
untimed enumeration of every entity that ever existed in the book. Healing chapter 12, the
drafting stack was told about a character who dies in chapter 40 as though they were alive,
under their final rank. `state@as_of` answers at the position being written.

Two halves are tested here because they fail differently: the client (transport, the required
position, degradation) and `cast_from_state` (the flattening that makes the bible temporal).
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx

from app.clients.kal_client import KalClient
from app.engine.heal_canon import cast_from_state, render_canon

BASE = "http://knowledge-gateway:3000"
BOOK = uuid.uuid4()
USER = uuid.uuid4()


def _state_url() -> str:
    return f"{BASE}/v1/kal/books/{BOOK}/state"


def _client() -> KalClient:
    return KalClient(BASE, "intok")


def _entity(eid: str, **attrs: str) -> dict:
    return {
        "entity_id": eid,
        "facts": [
            {"attr": k, "value": v, "fact_kind": "attribute", "valid_from_ordinal": 1}
            for k, v in attrs.items()
        ],
    }


# ── the client ───────────────────────────────────────────────────────────────


@respx.mock
async def test_state_sends_the_position_the_internal_token_and_the_tenancy_header():
    e1 = str(uuid.uuid4())
    route = respx.get(_state_url()).mock(
        return_value=httpx.Response(200, json={
            "book_id": str(BOOK), "as_of_ordinal": 12,
            "entities": [_entity(e1, name="Alice", role="protagonist")],
        })
    )
    c = _client()
    try:
        got = await c.state(BOOK, as_of=12, user_id=USER)
    finally:
        await c.aclose()

    assert [e["entity_id"] for e in got] == [e1]
    req = route.calls.last.request
    # The position must actually be ON the wire. A client that dropped it would get the
    # service's 400 in production but pass any assertion made only about the response.
    assert req.url.params["as_of"] == "12"
    assert req.headers["X-Internal-Token"] == "intok"
    assert req.headers["X-User-Id"] == str(USER)


@respx.mock
async def test_state_degrades_to_empty_on_outage_rather_than_raising():
    # A KAL outage leaves a heal run ungrounded (legacy behaviour); it must not 500 the route.
    respx.get(_state_url()).mock(side_effect=httpx.ConnectError("refused"))
    c = _client()
    try:
        assert await c.state(BOOK, as_of=3, user_id=USER) == []
    finally:
        await c.aclose()


@respx.mock
async def test_state_refuses_a_non_list_entities_payload(caplog):
    # Keyed-by-id is the shape a `?? []`-style guard accepts silently; iterating it yields
    # keys, not entities, and the bible would be built from strings.
    #
    # The LOG assertion is the load-bearing half. The per-row `isinstance(e, dict)` filter
    # below already discards those keys, so an empty result proves nothing about this guard —
    # removing it entirely leaves the return value identical. What is lost is the diagnosis:
    # a silently-empty cast reads as "this book has no entities", and the operator has no way
    # to tell that apart from a downstream contract change.
    respx.get(_state_url()).mock(
        return_value=httpx.Response(200, json={"entities": {"e1": {"facts": []}}})
    )
    c = _client()
    try:
        with caplog.at_level("WARNING"):
            assert await c.state(BOOK, as_of=3) == []
    finally:
        await c.aclose()
    assert any("non-list" in r.getMessage() for r in caplog.records), caplog.text


@respx.mock
async def test_state_treats_a_400_as_a_caller_bug_and_still_degrades(caplog):
    # The service owns the required-position rule. A 400 means composition asked wrongly —
    # log it as such (it must not hide in the outage bucket) but never raise into the route.
    respx.get(_state_url()).mock(return_value=httpx.Response(400, json={"code": "GLOSS_BAD_REQUEST"}))
    c = _client()
    try:
        with caplog.at_level("WARNING"):
            assert await c.state(BOOK, as_of=-1) == []
    finally:
        await c.aclose()
    assert any("REFUSED" in r.getMessage() for r in caplog.records), caplog.text


# ── the flattening ───────────────────────────────────────────────────────────


# One non-ASCII fixture value, kept on purpose: the canon bible is rendered for books whose
# source language is Vietnamese (the xianxia address-convention block in heal_canon.py is
# itself written in Vietnamese), and it crosses a JSON boundary on the way here. An ASCII-only
# fixture would not catch an encoding regression in the flattening.
_VI_NAME = "Lâm Vân"  # doc-language-gate: ok -- corpus-shaped test data, see the note above


def test_cast_from_state_carries_the_attributes_the_bible_renders():
    e1 = str(uuid.uuid4())
    cast = cast_from_state([_entity(
        e1, name=_VI_NAME, role="protagonist", description="outer-sect disciple",
        relationships="disciple of Elder To",
    )])
    assert cast == [{
        "name": _VI_NAME, "role": "protagonist", "description": "outer-sect disciple",
        "relationships": "disciple of Elder To", "entity_id": e1,
    }]

    # And the bible actually renders them. This is the assertion that shows the migration
    # changed the OUTPUT, not just the call: a roster-shaped cast ({entity_id, name}) leaves
    # render_canon's role/description branches dead, which is what every bible looked like.
    bible = render_canon(cast)
    assert "protagonist" in bible and "outer-sect disciple" in bible
    assert _VI_NAME in bible          # the non-ASCII name survives the round trip
    assert "protagonist" not in render_canon([{"entity_id": e1, "name": _VI_NAME}])


def test_cast_from_state_drops_an_entity_with_no_name_at_this_position():
    # An entity whose name fact starts later did not exist yet at this position. A nameless
    # bible line grounds nothing, and `render_canon` would skip it anyway — dropping it here
    # keeps the two in agreement instead of relying on the renderer to clean up.
    named, unnamed = str(uuid.uuid4()), str(uuid.uuid4())
    cast = cast_from_state([_entity(named, name="Alice"), _entity(unnamed, role="antagonist")])
    assert [c["entity_id"] for c in cast] == [named]


def test_cast_from_state_ignores_attributes_the_bible_does_not_render():
    # The state read returns the whole per-entity state; the bible is TERSE by design (a
    # verbose one buried the convention rule a verifier needed). Extra attrs must not leak in.
    e1 = str(uuid.uuid4())
    cast = cast_from_state([_entity(e1, name="Alice", life_status="dead", rank="core disciple")])
    assert cast == [{"name": "Alice", "entity_id": e1}]


# ── the wiring: which read the canon path actually chooses ───────────────────


class _StubKal:
    def __init__(self, entities):
        self.entities = entities
        self.state_calls: list[int] = []
        self.roster_calls = 0

    async def state(self, book_id, *, as_of, user_id=None):
        self.state_calls.append(as_of)
        return self.entities

    async def roster(self, book_id, *, user_id=None, strict=False):
        self.roster_calls += 1
        return [{"entity_id": "r1", "name": "FromRoster", "kind": None}]


class _StubBook:
    def __init__(self, orders):
        self.orders = orders

    async def get_chapter_sort_orders(self, chapter_ids):
        return self.orders


async def test_canon_cast_reads_state_at_the_chapters_sort_order():
    # The position must be the CHAPTER's book position, not an index the router happened to
    # have. Asserting the value passed to `state` is the whole point: an off-by-one or a
    # job-relative index answers confidently about a different chapter.
    from app.routers.plan import _canon_cast_at

    chapter = uuid.uuid4()
    e1 = str(uuid.uuid4())
    kal = _StubKal([_entity(e1, name="Alice", role="protagonist")])
    book = _StubBook({str(chapter): 12})

    cast = await _canon_cast_at(kal, book, BOOK, chapter, USER)

    assert kal.state_calls == [12]
    assert kal.roster_calls == 0
    assert cast == [{"name": "Alice", "role": "protagonist", "entity_id": e1}]


async def test_canon_cast_falls_back_to_the_untimed_roster_and_warns(caplog):
    # An unresolvable position degrades to what the caller had before this task — but LOUDLY.
    # An ungrounded-in-time bible is invisible in the output; this WARN is its only detector.
    from app.routers.plan import _canon_cast_at

    chapter = uuid.uuid4()
    kal = _StubKal([])
    book = _StubBook({})   # book-service knows no sort_order for this chapter

    with caplog.at_level("WARNING"):
        cast = await _canon_cast_at(kal, book, BOOK, chapter, USER)

    assert kal.state_calls == []
    assert kal.roster_calls == 1
    assert cast == [{"entity_id": "r1", "name": "FromRoster", "kind": None}]
    assert any("NO resolved story position" in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.parametrize("payload", [
    [{"entity_id": "e1", "facts": "not-a-list"}],
    [{"entity_id": "e1"}],
    ["not-a-mapping"],
    [{"entity_id": "e1", "facts": [{"attr": "name"}]}],       # value missing
    [{"entity_id": "e1", "facts": [{"value": "Alice"}]}],     # attr missing
])
def test_cast_from_state_survives_malformed_rows(payload):
    # The bible is rendered on a request path a human is waiting on; a shape surprise must
    # thin the cast, never raise out of the route.
    assert cast_from_state(payload) == []
