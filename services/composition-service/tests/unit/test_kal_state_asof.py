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


def test_cast_from_state_KEEPS_a_nameless_entity_so_its_name_can_be_looked_up():
    """⚠️ REWRITTEN 2026-08-24 (QC-5 C41). This asserted the opposite, on the reasoning that an
    entity with no `name` fact "did not exist yet at this position" and that dropping it here
    "keeps the two in agreement instead of relying on the renderer to clean up".

    Measured on the acceptance book, the premise is false: **13 of 21 entities carry a `name`
    fact and 8 do not, and the 8 are the PEOPLE.** `state@as_of` does not project a name;
    `roster` does, by contract. Dropping here threw the characters away before anyone could look
    them up, and the block headed "CHARACTER CANON" listed events and objects only — which is
    what QC-5's clause 1a was failing on (7/8 on the untouched control).

    The property that test defended is intact and asserted below: `render_canon` still emits no
    nameless line. What moved is WHERE the decision happens.
    """
    named, unnamed = str(uuid.uuid4()), str(uuid.uuid4())
    cast = cast_from_state([_entity(named, name="Alice"), _entity(unnamed, role="antagonist")])
    assert [c["entity_id"] for c in cast] == [named, unnamed]
    assert not cast[1].get("name"), "kept, but still nameless until someone fills it"

    from app.engine.heal_canon import render_canon
    rendered = render_canon(cast)
    assert "Alice" in rendered
    assert "- :" not in rendered, (
        "the renderer must still emit no nameless line — that property did not move"
    )


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
    from app.engine.canon_bible import canon_cast_at

    chapter = uuid.uuid4()
    e1 = str(uuid.uuid4())
    kal = _StubKal([_entity(e1, name="Alice", role="protagonist")])
    book = _StubBook({str(chapter): 12})

    cast, as_of = await canon_cast_at(kal, book, BOOK, chapter, USER)

    assert kal.state_calls == [12]
    assert kal.roster_calls == 0
    assert cast == [{"name": "Alice", "role": "protagonist", "entity_id": e1}]
    # C2: the position is RETURNED, not only logged — a degrade nobody can observe
    # from the result is a degrade that gets reported as a success.
    assert as_of == 12


async def test_canon_cast_falls_back_to_the_untimed_roster_and_warns(caplog):
    # An unresolvable position degrades to what the caller had before this task — but LOUDLY.
    # An ungrounded-in-time bible is invisible in the output; this WARN is its only detector.
    from app.engine.canon_bible import canon_cast_at

    chapter = uuid.uuid4()
    kal = _StubKal([])
    book = _StubBook({})   # book-service knows no sort_order for this chapter

    with caplog.at_level("WARNING"):
        cast, as_of = await canon_cast_at(kal, book, BOOK, chapter, USER)

    assert kal.state_calls == []
    assert kal.roster_calls == 1
    assert cast == [{"entity_id": "r1", "name": "FromRoster", "kind": None}]
    assert as_of is None   # C2: the caller can SEE it fell back
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
    #
    # ⚠️ The assertion was `== []` until C41 kept nameless rows. The INTENT is unchanged and is
    # what is asserted now: no malformed row may produce a NAMED cast member, so nothing
    # malformed can reach a rendered bible line.
    cast = cast_from_state(payload)
    assert all(not c.get("name") for c in cast)

# ── QC-5 C41: the block headed "CHARACTER CANON" contained no characters ──────────────────


class _RosterKal(_StubKal):
    """A KAL whose roster knows the names `state@as_of` does not project."""

    def __init__(self, entities, roster_rows, roster_raises=False):
        super().__init__(entities)
        self._rows = roster_rows
        self._raises = roster_raises

    async def roster(self, book_id, *, user_id=None, strict=False):
        self.roster_calls += 1
        if self._raises:
            raise RuntimeError("KAL roster unreachable")
        return list(self._rows)


async def test_a_nameless_entity_gets_its_name_from_the_ROSTER():
    """🔴 Measured on the acceptance book: 13 of 21 entities carry a `name` FACT and 8 do not,
    and the 8 are the people.

    `state@as_of` projects `{entity_id, facts}` only, so `cast_from_state` sees a name only when
    one happens to be stored as a fact. `render_canon` then drops every nameless row — correctly,
    since "a nameless bible line grounds nothing" — and the bible listed the talent competition,
    the spirit stones and the tea pavilion while omitting every character. A critic asked whether
    prose contradicts a rule about a character, handed a character canon without that character,
    flags prose that conforms: QC-5 clause 1a, failing at 7/8 on the untouched control.
    """
    from app.engine.canon_bible import canon_cast_at

    chapter = uuid.uuid4()
    eid = str(uuid.uuid4())
    kal = _RosterKal([_entity(eid, role="betrayer")],          # facts, but NO name
                     [{"entity_id": eid, "name": "Lam Trach"}])
    cast, _ = await canon_cast_at(kal, _StubBook({str(chapter): 11}), BOOK, chapter, USER)

    assert kal.roster_calls == 1
    assert cast[0]["name"] == "Lam Trach", (
        "the name was never missing from the system — `roster` projects id+name by contract, "
        "which is the whole reason this fallback exists"
    )


async def test_a_cast_that_already_has_names_does_NOT_call_the_roster():
    """The control arm, and it guards a cost as well as a behaviour: the roster is a keyset
    drain over the whole book, and paying for it on every critique of a fully-named cast would
    be a real regression. It also proves the fill is a FALLBACK rather than an override."""
    from app.engine.canon_bible import canon_cast_at

    chapter = uuid.uuid4()
    eid = str(uuid.uuid4())
    kal = _RosterKal([_entity(eid, name="FromState", role="x")],
                     [{"entity_id": eid, "name": "FromRoster"}])
    cast, _ = await canon_cast_at(kal, _StubBook({str(chapter): 11}), BOOK, chapter, USER)

    assert kal.roster_calls == 0
    assert cast[0]["name"] == "FromState", "state's own name must win; the roster only FILLS"


async def test_a_roster_OUTAGE_leaves_the_cast_as_state_gave_it():
    """Advisory all the way down: a thinner bible is acceptable, a failed critique is not."""
    from app.engine.canon_bible import canon_cast_at

    chapter = uuid.uuid4()
    eid = str(uuid.uuid4())
    kal = _RosterKal([_entity(eid, role="betrayer")], [], roster_raises=True)
    cast, as_of = await canon_cast_at(kal, _StubBook({str(chapter): 11}), BOOK, chapter, USER)

    assert as_of == 11
    assert cast and not cast[0].get("name")

async def test_the_roster_FILLS_a_missing_name_and_never_OVERRIDES_a_present_one():
    """The control arm that actually fires. Its predecessor gave every entity a name, so the
    fast path returned before the fill loop and the assertion held no matter what the loop did —
    a bite proved it (mutating the guard to `if True:` left the suite green). A MIXED cast is
    what makes the roster run and the precedence observable."""
    from app.engine.canon_bible import canon_cast_at

    chapter = uuid.uuid4()
    have, missing = str(uuid.uuid4()), str(uuid.uuid4())
    kal = _RosterKal(
        [_entity(have, name="FromState", role="x"), _entity(missing, role="betrayer")],
        [{"entity_id": have, "name": "RosterShouldNotWin"},
         {"entity_id": missing, "name": "Lam Trach"}],
    )
    cast, _ = await canon_cast_at(kal, _StubBook({str(chapter): 11}), BOOK, chapter, USER)

    assert kal.roster_calls == 1, "a missing name must trigger exactly one roster drain"
    by_id = {c["entity_id"]: c for c in cast}
    assert by_id[have]["name"] == "FromState", "state's own name WINS; the roster only fills"
    assert by_id[missing]["name"] == "Lam Trach"

