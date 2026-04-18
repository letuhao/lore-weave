"""K13.0 — unit tests for the Pass 0 glossary anchor pre-loader."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.db.neo4j_repos.entities import Entity
from app.extraction.anchor_loader import Anchor, load_glossary_anchors

USER_ID = str(uuid4())
PROJECT_ID = str(uuid4())
BOOK_ID = uuid4()


def _make_entity(name: str, kind: str, gid: str) -> Entity:
    """Build a minimal Entity mimicking what upsert_glossary_anchor returns."""
    return Entity(
        id=f"canon-{name.lower()}",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name=name,
        canonical_name=name.lower(),
        kind=kind,
        aliases=[name, f"{name}-alt"],
        glossary_entity_id=gid,
        anchor_score=1.0,
    )


@pytest.mark.asyncio
async def test_returns_empty_when_glossary_client_fails(monkeypatch):
    """Circuit-open or HTTP 500 from glossary → return [] and keep job running."""
    gc = MagicMock()
    gc.list_entities = AsyncMock(return_value=None)

    calls = []

    async def fake_upsert(*a, **kw):
        calls.append(kw)
        raise AssertionError("upsert must not be called when list_entities fails")

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor", fake_upsert,
    )

    out = await load_glossary_anchors(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )
    assert out == []
    assert calls == []


@pytest.mark.asyncio
async def test_upserts_each_entry_and_returns_anchor_index(monkeypatch):
    """Happy path: two glossary entries → two upsert calls → two Anchors."""
    gid1, gid2 = str(uuid4()), str(uuid4())
    gc = MagicMock()
    gc.list_entities = AsyncMock(return_value=[
        {"entity_id": gid1, "name": "Arthur", "kind_code": "person", "aliases": ["Art"]},
        {"entity_id": gid2, "name": "Excalibur", "kind_code": "object", "aliases": []},
    ])

    captured_kwargs = []

    async def fake_upsert(session, **kw):
        captured_kwargs.append(kw)
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"])

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor", fake_upsert,
    )

    out = await load_glossary_anchors(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )

    assert len(captured_kwargs) == 2
    assert captured_kwargs[0]["glossary_entity_id"] == gid1
    assert captured_kwargs[0]["name"] == "Arthur"
    assert captured_kwargs[0]["kind"] == "person"
    assert captured_kwargs[0]["aliases"] == ["Art"]
    assert captured_kwargs[0]["user_id"] == USER_ID
    assert captured_kwargs[0]["project_id"] == PROJECT_ID

    assert len(out) == 2
    assert all(isinstance(a, Anchor) for a in out)
    assert out[0].name == "Arthur"
    assert out[0].glossary_entity_id == gid1
    assert out[1].name == "Excalibur"


@pytest.mark.asyncio
async def test_skips_entry_on_upsert_exception(monkeypatch):
    """One bad row must not poison the pre-load — others still succeed."""
    gid_ok, gid_bad = str(uuid4()), str(uuid4())
    gc = MagicMock()
    gc.list_entities = AsyncMock(return_value=[
        {"entity_id": gid_bad, "name": "Bad", "kind_code": "person", "aliases": []},
        {"entity_id": gid_ok, "name": "Good", "kind_code": "person", "aliases": []},
    ])

    async def fake_upsert(session, **kw):
        if kw["glossary_entity_id"] == gid_bad:
            raise RuntimeError("neo4j hiccup")
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"])

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor", fake_upsert,
    )

    out = await load_glossary_anchors(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )

    assert len(out) == 1
    assert out[0].glossary_entity_id == gid_ok


@pytest.mark.asyncio
async def test_empty_glossary_returns_empty_list(monkeypatch):
    """Fresh book with no curated entries → normal empty result."""
    gc = MagicMock()
    gc.list_entities = AsyncMock(return_value=[])

    called = False

    async def fake_upsert(*a, **kw):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor", fake_upsert,
    )

    out = await load_glossary_anchors(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )

    assert out == []
    assert called is False


@pytest.mark.asyncio
async def test_skips_entries_missing_required_fields(monkeypatch):
    """Entries without entity_id or name can't anchor; skip them quietly."""
    gid_ok = str(uuid4())
    gc = MagicMock()
    gc.list_entities = AsyncMock(return_value=[
        {"entity_id": "", "name": "NoID", "kind_code": "person"},
        {"entity_id": str(uuid4()), "name": "", "kind_code": "person"},
        {"kind_code": "person"},
        {"entity_id": gid_ok, "name": "Valid", "kind_code": "person"},
    ])

    captured = []

    async def fake_upsert(session, **kw):
        captured.append(kw["glossary_entity_id"])
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"])

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor", fake_upsert,
    )

    out = await load_glossary_anchors(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )

    assert captured == [gid_ok]
    assert len(out) == 1
    assert out[0].name == "Valid"
