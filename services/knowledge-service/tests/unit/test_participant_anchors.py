"""D-KG-TL-PARTICIPANT-ANCHOR — unit tests for Option A (stored participant
entity anchors at extraction + backfill).

DB-free: Neo4j / glossary are faked (AsyncMock / MagicMock). Covers the three
behaviours that don't need a live graph:
  - the read path PREFERS a stored, aligned ``participant_entity_ids`` over
    read-time name resolution (the durable win) and only resolves residual names;
  - a misaligned / absent stored array falls back to read-time resolution;
  - the shared ``resolve_participant_anchors`` picks the anchored match;
  - the project backfill resolves + writes aligned arrays.

The merge_event Cypher (ON CREATE / ON MATCH alignment) needs a live Neo4j and
is covered by the live-smoke (``D-KG-TL-PA-LIVE-SMOKE``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.neo4j_repos.events import Event
from app.labels import timeline_localizer
from app.labels.timeline_localizer import localize_participants


def _evt(*, ident: str = "evt-1", participants: list[str] | None = None) -> Event:
    return Event(
        id=ident,
        user_id="user-1",
        project_id="proj-1",
        title="桥上的决斗",
        canonical_title="桥上的决斗",
        participants=participants or [],
        confidence=0.9,
        source_types=["chapter"],
    )


# ── the stored anchor is INTERNAL — never serialized into the API response ───


def test_participant_entity_ids_excluded_from_wire():
    """``participant_entity_ids`` is a stored anchor for the localizer, not an FE
    field — ``Field(exclude=True)`` must keep it OUT of the serialized response
    even though the custom @model_serializer wraps the dump (API contract
    unchanged, AC-T5 spirit)."""
    e = _evt(participants=["凯"])
    e.participant_entity_ids = ["gid-kai"]
    dumped = e.model_dump()
    assert "participant_entity_ids" not in dumped
    assert e.participant_entity_ids == ["gid-kai"]  # still readable as an attribute


# ── read path PREFERS the stored anchor (no read-time resolution) ────────────


@pytest.mark.asyncio
async def test_participants_prefers_stored_anchor(monkeypatch):
    """A fully-aligned ``participant_entity_ids`` is trusted wholesale: the read
    path does ZERO name resolution, anchored slots localize, ``""`` slots stay
    source + marked (AC-T3)."""
    e = _evt(participants=["凯", "赵", "无名"])
    e.participant_entity_ids = ["gid-kai", "gid-zhao", ""]  # aligned; 无名 unanchored

    called = False

    async def fake_resolve(*, user_id, project_id, names):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(timeline_localizer, "_resolve_names_to_entity_ids", fake_resolve)
    glossary = MagicMock()
    # 凯 has a vi name; 赵 is anchored but the glossary has no vi translation.
    glossary.fetch_entity_display_names = AsyncMock(return_value={"gid-kai": "Khải"})

    await localize_participants(
        [e], user_id="user-1", project_id="proj-1", book_id=uuid4(),
        language="vi", glossary=glossary,
    )

    assert called is False  # aligned anchors → NO read-time resolution
    assert e.participants_localized == ["Khải", "赵", "无名"]
    assert e.participants_translated == [True, False, False]
    # the glossary join got exactly the two anchored ids (not the "" slot).
    _, kwargs = glossary.fetch_entity_display_names.call_args
    assert set(kwargs["entity_ids"]) == {"gid-kai", "gid-zhao"}


@pytest.mark.asyncio
async def test_participants_mixed_resolves_only_residual(monkeypatch):
    """A page with one backfilled event + one legacy event resolves ONLY the
    legacy event's names at read time."""
    e_anchored = _evt(ident="e1", participants=["凯"])
    e_anchored.participant_entity_ids = ["gid-kai"]
    e_legacy = _evt(ident="e2", participants=["赵"])  # no stored anchors

    seen: dict[str, list[str]] = {}

    async def fake_resolve(*, user_id, project_id, names):
        seen["names"] = list(names)
        return {"赵": "gid-zhao"}

    monkeypatch.setattr(timeline_localizer, "_resolve_names_to_entity_ids", fake_resolve)
    glossary = MagicMock()
    glossary.fetch_entity_display_names = AsyncMock(
        return_value={"gid-kai": "Khải", "gid-zhao": "Triệu"}
    )

    await localize_participants(
        [e_anchored, e_legacy], user_id="u", project_id="p", book_id=uuid4(),
        language="vi", glossary=glossary,
    )

    assert seen["names"] == ["赵"]  # only the legacy event's name was re-resolved
    assert e_anchored.participants_localized == ["Khải"]
    assert e_legacy.participants_localized == ["Triệu"]


@pytest.mark.asyncio
async def test_participants_misaligned_array_falls_back(monkeypatch):
    """A length-mismatched stored array (legacy ON MATCH grew a short array) is
    distrusted → the whole event falls back to read-time resolution."""
    e = _evt(participants=["凯", "赵"])
    e.participant_entity_ids = ["gid-kai"]  # len 1 != 2 → not trusted

    seen: dict[str, list[str]] = {}

    async def fake_resolve(*, user_id, project_id, names):
        seen["names"] = sorted(names)
        return {"凯": "gid-kai", "赵": "gid-zhao"}

    monkeypatch.setattr(timeline_localizer, "_resolve_names_to_entity_ids", fake_resolve)
    glossary = MagicMock()
    glossary.fetch_entity_display_names = AsyncMock(
        return_value={"gid-kai": "Khải", "gid-zhao": "Triệu"}
    )

    await localize_participants(
        [e], user_id="u", project_id="p", book_id=uuid4(),
        language="vi", glossary=glossary,
    )

    assert seen["names"] == ["凯", "赵"]  # both re-resolved (short array distrusted)
    assert e.participants_localized == ["Khải", "Triệu"]


# ── shared resolver: name → glossary entity_id (anchored-first) ──────────────


@pytest.mark.asyncio
async def test_resolve_participant_anchors_picks_anchored(monkeypatch):
    from app.db.neo4j_repos import entities as ent_mod

    def ent(gid):
        m = MagicMock()
        m.glossary_entity_id = gid
        return m

    async def fake_find(session, *, user_id, project_id, name, include_archived=False):
        return {
            "凯": [ent("gid-kai")],
            "赵": [ent(None), ent("gid-zhao")],  # first match unanchored → skip to next
            "无名": [ent(None)],  # no anchored match → omitted
        }.get(name, [])

    monkeypatch.setattr(ent_mod, "find_entities_by_name", fake_find)

    out = await ent_mod.resolve_participant_anchors(
        MagicMock(), user_id="u", project_id="p", names=["凯", "赵", "无名", "凯"],
    )
    assert out == {"凯": "gid-kai", "赵": "gid-zhao"}  # 无名 omitted; dup 凯 collapsed


# ── project backfill: resolve + write aligned arrays ─────────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r

        return gen()


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.set_calls: list[dict] = []

    async def run(self, cypher, **params):
        if "RETURN e.id AS id" in cypher:
            return _FakeResult(self._rows)
        self.set_calls.append(params)  # a SET write
        return _FakeResult([])


@pytest.mark.asyncio
async def test_participant_anchor_backfill_resolves_and_sets(monkeypatch):
    from app.db.migrations import backfill_participant_anchors as bpa

    rows = [
        {"id": "e1", "participants": ["凯", "无名"]},
        {"id": "e2", "participants": ["赵"]},
    ]

    async def fake_resolve(session, *, user_id, project_id, names):
        return {"凯": "gid-kai", "赵": "gid-zhao"}  # 无名 unanchored

    monkeypatch.setattr(bpa, "resolve_participant_anchors", fake_resolve)

    sess = _FakeSession(rows)
    res = await bpa.run_participant_anchor_backfill(sess, user_id="u", project_id="p")

    assert res.events_scanned == 2
    assert res.events_anchored == 2  # both got ≥1 anchor
    assert res.anchors_resolved == 2  # 凯 + 赵 (无名 is "")
    by_id = {c["id"]: c["participant_entity_ids"] for c in sess.set_calls}
    # arrays are ALIGNED to each event's stored participants; "" for unanchored.
    assert by_id["e1"] == ["gid-kai", ""]
    assert by_id["e2"] == ["gid-zhao"]
