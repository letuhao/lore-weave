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

def _paged_handler(total: int, calls: list[str]):
    """A known-entities stub that honours limit/offset like the real Go handler."""
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        q = req.url.params
        limit, offset = int(q.get("limit", 50)), int(q.get("offset", 0))
        rows = [
            {"entity_id": f"e{i}", "name": f"Thực thể {i}", "kind_code": "terminology",
             "aliases": [f"alias-{i}"], "frequency": 0}
            for i in range(offset, min(offset + limit, total))
        ]
        return httpx.Response(200, json=rows)
    return handler


@pytest.mark.asyncio
async def test_list_canon_entries_asks_for_frequency_zero():
    """The default min_frequency=2 gates on CHAPTER-MENTION count, so every entity of
    a book being written from scratch scores 0 and the list returns empty — the exact
    state that made the prompt's canon block useless."""
    calls: list[str] = []
    gc = _glossary_with(_paged_handler(2, calls))
    entries = await gc.list_canon_entries(uuid4())
    assert entries == [("Thực thể 0", ["alias-0"]), ("Thực thể 1", ["alias-1"])]
    assert "min_frequency=0" in calls[0]
    await gc.aclose()


@pytest.mark.asyncio
async def test_list_canon_entries_pages_past_the_server_side_500_cap():
    """W2. The handler caps `limit` at 500, so a single request can never return a
    3,000-entity book — and the old flat fetch bound silently truncated an
    `ORDER BY mention_count DESC`, dropping the newest lore first."""
    calls: list[str] = []
    gc = _glossary_with(_paged_handler(1_150, calls))
    entries = await gc.list_canon_entries(uuid4())
    assert len(entries) == 1_150
    assert len(calls) == 3  # 500 + 500 + 150 (short page ends the walk)
    assert "offset=0" in calls[0] and "offset=500" in calls[1]
    await gc.aclose()


@pytest.mark.asyncio
async def test_list_canon_entries_keeps_partial_rows_when_a_later_page_fails():
    """A mid-walk outage must not throw away the pages already read: partial canon
    grounds the extractor better than none, and the loss is logged, not silent."""
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if len(calls) == 1:
            return httpx.Response(200, json=[
                {"name": f"E{i}", "aliases": []} for i in range(500)
            ])
        return httpx.Response(503, json={"error": "down"})

    gc = _glossary_with(handler)
    entries = await gc.list_canon_entries(uuid4())
    assert len(entries) == 500
    await gc.aclose()


@pytest.mark.asyncio
async def test_list_canon_entries_degrades_to_empty_never_raises():
    """Same posture as the pinned fetch: extraction proceeds un-grounded rather than
    blocking on a glossary outage."""
    gc = _glossary_with(lambda req: httpx.Response(503, json={"error": "down"}))
    assert await gc.list_canon_entries(uuid4()) == []
    await gc.aclose()

    gc2 = _glossary_with(lambda req: httpx.Response(200, json={"not": "a list"}))
    assert await gc2.list_canon_entries(uuid4()) == []
    await gc2.aclose()


@pytest.mark.asyncio
async def test_list_canon_entries_skips_blank_rows():
    gc = _glossary_with(lambda req: httpx.Response(200, json=[
        {"name": "  "}, {"name": "Trận pháp", "aliases": ["Trận"]}, {"nope": 1},
    ]))
    assert await gc.list_canon_entries(uuid4()) == [("Trận pháp", ["Trận"])]
    await gc.aclose()


# ── the runner half, finally testable ───────────────────────────────────────
#
# This file's own docstring used to say the runner wiring was "asserted by the
# live-smoke". That is why it could silently degrade to [] for every un-pinned book
# without anything going red. merge_known_entities is that logic pulled out to where a
# test can reach it.

PROSE = ("Lâm Uyên ngồi giữa Trận pháp. Thiếu chủ không nói gì. "
         "Bên ngoài, Tô Thanh Dao đứng đợi.")


def test_selection_ships_only_the_canon_this_chunk_MENTIONS():
    """The whole point of smart preload: a 3,000-entity glossary must not empty itself
    into every chunk. An unmentioned name costs prompt budget to say nothing."""
    from app.runner import CanonIndex, select_known_entities

    out, dropped = select_known_entities(
        [], CanonIndex.build([
            ("Lâm Uyên", []), ("Trận pháp", []), ("Huyết Vô Thường", []),
            ("Ngự Khí Thuật", []),
        ]),
        PROSE, cap=150,
    )
    assert out == ["Lâm Uyên", "Trận pháp"]
    assert dropped == 0


def test_selection_matches_an_ALIAS_but_ships_the_CANONICAL_name():
    """A chapter says "Thiếu chủ", not "Lâm Uyên". Matching only the canonical name
    would miss the mention in the very chunk that needed the canon — and the model must
    still be steered to the canonical spelling."""
    from app.runner import CanonIndex, select_known_entities

    out, _ = select_known_entities(
        [], CanonIndex.build([("Lâm Trạch", ["Thiếu chủ"])]),
        "Thiếu chủ bước vào.", cap=150,
    )
    assert out == ["Lâm Trạch"]


def test_pinned_ship_even_when_the_chunk_never_names_them():
    """That is exactly what pinning is FOR (C13) — sparse-but-critical entities stay
    anchored in chapters that never mention them."""
    from app.runner import CanonIndex, select_known_entities

    out, _ = select_known_entities(
        ["Huyết Vô Thường"], CanonIndex.build([]), PROSE, cap=150)
    assert out == ["Huyết Vô Thường"]


def test_surface_match_handles_a_CJK_neighbour():
    r"""Boundary guard. Python's `\w` is Unicode-aware, so a ``-style lookaround sees
    the neighbouring CJK letter as a word char and rejects EVERY match. This is the case
    that breaks first if the rule ever drifts from knowledge-service's entity_detector,
    which restricts the lookarounds to ASCII word chars for exactly this reason."""
    from app.runner import CanonIndex, select_known_entities

    out, _ = select_known_entities(
        [], CanonIndex.build([("凯", [])]), "凯笑了", cap=150)
    assert out == ["凯"]


def test_surface_match_still_refuses_a_substring_inside_an_ascii_word():
    from app.runner import CanonIndex, select_known_entities

    out, _ = select_known_entities(
        [], CanonIndex.build([("Kai", [])]), "Kairos arrived", cap=150)
    assert out == []


def test_selection_reports_what_the_cap_cut():
    from app.runner import CanonIndex, select_known_entities

    out, dropped = select_known_entities(
        [], CanonIndex.build([
            ("Lâm Uyên", []), ("Trận pháp", []), ("Tô Thanh Dao", []),
        ]),
        PROSE, cap=2,
    )
    assert len(out) == 2 and dropped == 1


def test_a_zero_cap_ships_nothing_and_says_so():
    from app.runner import CanonIndex, select_known_entities

    out, dropped = select_known_entities(
        ["A"], CanonIndex.build([("B", [])]), PROSE, cap=0)
    assert out == [] and dropped == 2
