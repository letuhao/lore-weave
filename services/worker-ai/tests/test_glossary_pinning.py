"""C13 — glossary pinning (worker-ai half).

Covers:
  1. GlossaryClient.fetch_entities_by_ids — returns the entity NAMES from the
     /internal/books/{book_id}/entities/by-ids select-for-context shape, reusing
     the X-Internal-Token header (no new secret). Empty input / non-200 / decode
     failure degrade to [] (the runner runs un-pinned, never blocks).
  2. _decode_pinned — JSONB normalisation (str | list | None).

These are the units the cycle brief requires: "fetch_entities_by_ids returns
names; known_entities non-empty when a pinned set is present" — the second half
(runner wiring) is asserted by the live-smoke + the decoupled/sync code paths
that now pass `pinned_names` into known_entities.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.clients import GlossaryClient


def _glossary_with(handler) -> GlossaryClient:
    gc = GlossaryClient("http://glossary-service:8211", "tok", 5.0)
    gc._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"X-Internal-Token": "tok"},
    )
    return gc


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_returns_names():
    book_id = uuid4()
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["token"] = req.headers.get("X-Internal-Token")
        captured["body"] = req.content
        # select-for-context row shape: name is `cached_name`.
        return httpx.Response(200, json={"items": [
            {"entity_id": "e1", "cached_name": "PanGu", "kind_code": "deity"},
            {"entity_id": "e2", "cached_name": "Nuwa", "kind_code": "deity"},
        ]})

    gc = _glossary_with(handler)
    names = await gc.fetch_entities_by_ids(book_id, ["e1", "e2"])

    assert names == ["PanGu", "Nuwa"]
    # Hits the SAME internal endpoint the knowledge-service selector uses.
    assert f"/internal/books/{book_id}/entities/by-ids" in captured["url"]
    # Reuses the existing X-Internal-Token — NO new secret.
    assert captured["token"] == "tok"
    assert b"e1" in captured["body"] and b"e2" in captured["body"]


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_empty_input_no_call():
    called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"items": []})

    gc = _glossary_with(handler)
    assert await gc.fetch_entities_by_ids(uuid4(), []) == []
    assert called["n"] == 0  # short-circuits, no HTTP call


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_non_200_degrades_to_empty():
    gc = _glossary_with(lambda req: httpx.Response(503))
    assert await gc.fetch_entities_by_ids(uuid4(), ["e1"]) == []


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_drops_blank_names():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [
            {"entity_id": "e1", "cached_name": "  "},   # blank → dropped
            {"entity_id": "e2", "cached_name": "Kai"},
            {"entity_id": "e3"},                          # missing → dropped
        ]})

    gc = _glossary_with(handler)
    assert await gc.fetch_entities_by_ids(uuid4(), ["e1", "e2", "e3"]) == ["Kai"]


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_network_error_degrades_to_empty():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    gc = _glossary_with(handler)
    assert await gc.fetch_entities_by_ids(uuid4(), ["e1"]) == []


def test_decode_pinned_normalises_jsonb():
    from app.runner import _decode_pinned

    # NULL ⇒ None (no pins).
    assert _decode_pinned(None) is None
    # raw JSON str (asyncpg JSONB codec) ⇒ list[str].
    assert _decode_pinned('["e1", "e2"]') == ["e1", "e2"]
    # already-decoded list ⇒ list[str] (stringified).
    assert _decode_pinned(["e1", "e2"]) == ["e1", "e2"]
    # malformed JSON ⇒ None (job runs un-pinned, never crashes the poll loop).
    assert _decode_pinned("{not json") is None
    # non-list JSON ⇒ None.
    assert _decode_pinned('"e1"') is None


# ── D-EXTRACT-KNOWN-ENTITIES-PINNED-ONLY ────────────────────────────────────
#
# C13 replaced a hardcoded `[]` with the PINNED names — right direction, one step
# short. Pinning is a manual per-entity action and this file's own docstring calls
# nothing-pinned the common case, so the extraction prompt normally still declared
# KNOWN_ENTITIES = [] while its rules lean on that list ("Known entities win ties")
# and Rule 8 biases toward omitting anything that reads as backstory — which is
# exactly where a novel's authored lore appears. Measured against gemma-4-26b on the
# live Mị Đế passage (1.7k-token prompt, so nothing was lost in the middle): 4 of 7
# authored terms with the block empty, 7 of 7 with it populated.

@pytest.mark.asyncio
async def test_list_canon_names_asks_for_frequency_zero():
    """The default min_frequency=2 gates on CHAPTER-MENTION count, so every entity of
    a book being written from scratch scores 0 and the list returns empty — the exact
    state that made the prompt's canon block useless."""
    book_id = uuid4()
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json=[
            {"entity_id": "e1", "name": "Chân Linh", "kind_code": "power_system",
             "aliases": [], "frequency": 0},
            {"entity_id": "e2", "name": "Luyện khí", "kind_code": "terminology",
             "aliases": [], "frequency": 0},
        ])

    gc = _glossary_with(handler)
    names = await gc.list_canon_names(book_id, limit=150)
    assert names == ["Chân Linh", "Luyện khí"]
    assert "min_frequency=0" in captured["url"]
    assert "limit=150" in captured["url"]
    await gc.aclose()


@pytest.mark.asyncio
async def test_list_canon_names_degrades_to_empty_never_raises():
    """Same posture as the pinned fetch: extraction proceeds un-grounded rather than
    blocking on a glossary outage."""
    gc = _glossary_with(lambda req: httpx.Response(503, json={"error": "down"}))
    assert await gc.list_canon_names(uuid4(), limit=150) == []
    await gc.aclose()

    gc2 = _glossary_with(lambda req: httpx.Response(200, json={"not": "a list"}))
    assert await gc2.list_canon_names(uuid4(), limit=150) == []
    await gc2.aclose()


@pytest.mark.asyncio
async def test_list_canon_names_skips_blank_rows_and_respects_a_zero_cap():
    gc = _glossary_with(lambda req: httpx.Response(200, json=[
        {"name": "  "}, {"name": "Trận pháp"}, {"nope": 1},
    ]))
    assert await gc.list_canon_names(uuid4(), limit=10) == ["Trận pháp"]
    await gc.aclose()

    # limit<=0 must not even call out — a cap of 0 means "no canon in the prompt".
    called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json=[{"name": "X"}])

    gc2 = _glossary_with(handler)
    assert await gc2.list_canon_names(uuid4(), limit=0) == []
    assert called["n"] == 0
    await gc2.aclose()


# ── the runner half, finally testable ───────────────────────────────────────
#
# This file's own docstring used to say the runner wiring was "asserted by the
# live-smoke". That is why it could silently degrade to [] for every un-pinned book
# without anything going red. merge_known_entities is that logic pulled out to where a
# test can reach it.

def test_merge_puts_pinned_first_then_canon_and_dedups():
    from app.runner import merge_known_entities

    out, dropped = merge_known_entities(
        ["Lâm Uyên"], ["chân linh", "Lâm Uyên", "Luyện khí"], cap=10,
    )
    assert out == ["Lâm Uyên", "chân linh", "Luyện khí"]   # pinned first, no duplicate
    assert dropped == 0


def test_merge_keeps_the_PINNED_names_when_the_cap_bites():
    """A user pinned those precisely so they survive a truncation."""
    from app.runner import merge_known_entities

    out, dropped = merge_known_entities(["A", "B"], ["C", "D", "E"], cap=3)
    assert out == ["A", "B", "C"]
    assert dropped == 2          # reported, never silently cut


def test_merge_dedups_case_insensitively():
    from app.runner import merge_known_entities

    out, _ = merge_known_entities(["Thần Hồn"], ["thần hồn", "Pháp khí"], cap=10)
    assert out == ["Thần Hồn", "Pháp khí"]


def test_merge_with_a_zero_cap_yields_nothing_and_says_how_much_it_dropped():
    from app.runner import merge_known_entities

    out, dropped = merge_known_entities(["A"], ["B", "C"], cap=0)
    assert out == [] and dropped == 3


def test_merge_with_no_pins_still_grounds_the_prompt():
    """THE regression: nothing pinned is the common case, and it used to mean the
    extractor was told the book has no canon at all."""
    from app.runner import merge_known_entities

    out, dropped = merge_known_entities([], ["Chân Linh", "Luyện khí"], cap=150)
    assert out == ["Chân Linh", "Luyện khí"] and dropped == 0
