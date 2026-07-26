"""K13.0 — unit tests for the Pass 0 glossary anchor pre-loader."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.db.neo4j_repos.entities import Entity
from app.extraction.anchor_loader import (
    Anchor,
    ProjectionResult,
    load_glossary_anchors,
    project_glossary_entities_to_nodes,
)

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
    gc.list_all_entities = AsyncMock(return_value=None)

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
    gc.list_all_entities = AsyncMock(return_value=([
        {"entity_id": gid1, "name": "Arthur", "kind_code": "person", "aliases": ["Art"]},
        {"entity_id": gid2, "name": "Excalibur", "kind_code": "object", "aliases": []},
    ], False))

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
    gc.list_all_entities = AsyncMock(return_value=([
        {"entity_id": gid_bad, "name": "Bad", "kind_code": "person", "aliases": []},
        {"entity_id": gid_ok, "name": "Good", "kind_code": "person", "aliases": []},
    ], False))

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
    gc.list_all_entities = AsyncMock(return_value=([], False))

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
    gc.list_all_entities = AsyncMock(return_value=([
        {"entity_id": "", "name": "NoID", "kind_code": "person"},
        {"entity_id": str(uuid4()), "name": "", "kind_code": "person"},
        {"kind_code": "person"},
        {"entity_id": gid_ok, "name": "Valid", "kind_code": "person"},
    ], False))

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


# ── WS-4B: project_glossary_entities_to_nodes ──────────────────────────


@pytest.mark.asyncio
async def test_projection_counts_created_vs_existing(monkeypatch):
    """The whole-glossary path lists active entities and reports create-vs-exist
    counts from the counted upsert."""
    gid1, gid2, gid3 = str(uuid4()), str(uuid4()), str(uuid4())
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(return_value=([
        {"entity_id": gid1, "name": "Arthur", "kind_code": "person", "aliases": ["Art"]},
        {"entity_id": gid2, "name": "Merlin", "kind_code": "person", "aliases": []},
        {"entity_id": gid3, "name": "Camelot", "kind_code": "place", "aliases": []},
    ], False))
    # first is new, next two already exist
    created_flags = {gid1: True, gid2: False, gid3: False}

    async def fake_upsert(session, **kw):
        gid = kw["glossary_entity_id"]
        return _make_entity(kw["name"], kw["kind"], gid), created_flags[gid]

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor_counted", fake_upsert,
    )

    res = await project_glossary_entities_to_nodes(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )
    assert isinstance(res, ProjectionResult)
    assert (res.created, res.existing, res.seen, res.skipped) == (1, 2, 3, 0)
    gc.list_all_entities.assert_awaited_once()


@pytest.mark.asyncio
async def test_projection_reads_whole_glossary_with_prose_less_params(monkeypatch):
    """REGRESSION (/review-impl) — the whole-glossary read MUST override the
    known-entities handler defaults, or a PROSE-LESS book (WS-4B's whole point,
    scenario S04) projects nothing:
      min_frequency default 2 → needs >=2 chapter links (a prose-less book has 0)
      alive default true      → silently drops narratively-dead entities
      limit default 50        → silently truncates (now handled by paging)
    """
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(return_value=([], False))

    async def fake_upsert(session, **kw):
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"]), True

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor_counted", fake_upsert,
    )
    await project_glossary_entities_to_nodes(
        session=MagicMock(), glossary_client=gc,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
    )
    kwargs = gc.list_all_entities.await_args.kwargs
    assert kwargs["min_frequency"] == 0, "must not require chapter links"
    assert kwargs["include_dead"] is True, "dead characters are still graph nodes"


@pytest.mark.asyncio
async def test_projection_reports_truncation_never_silently(monkeypatch):
    """REGRESSION — a truncated glossary read must be REPORTED, not silently dropped."""
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(return_value=(
        [{"entity_id": str(uuid4()), "name": f"E{i}", "kind_code": "person"}
         for i in range(3)],
        True,  # truncated
    ))

    async def fake_upsert(session, **kw):
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"]), True

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor_counted", fake_upsert,
    )
    res = await project_glossary_entities_to_nodes(
        session=MagicMock(), glossary_client=gc,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
    )
    assert res.truncated is True
    assert res.seen == 3


@pytest.mark.asyncio
async def test_anchor_preload_pages_and_does_not_filter_status(monkeypatch):
    """REGRESSION (D-ANCHOR-PRELOAD-50-CAP + D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM):
    extraction Pass-0 must page the WHOLE glossary (it silently anchored only 50),
    and must NOT send status='active' — both entity-creation paths insert
    status='draft', so an active-only filter would anchor almost nothing."""
    gid = str(uuid4())
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(return_value=(
        [{"entity_id": gid, "name": "Arthur", "kind_code": "person"}], False,
    ))

    async def fake_upsert(session, **kw):
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"])

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor", fake_upsert,
    )
    out = await load_glossary_anchors(
        session=MagicMock(), glossary_client=gc,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
    )
    assert len(out) == 1
    gc.list_all_entities.assert_awaited_once()
    assert gc.list_all_entities.await_args.kwargs["status_filter"] is None


@pytest.mark.asyncio
async def test_projection_subset_uses_fetch_by_ids(monkeypatch):
    """When entity_ids are given, fetch exactly those (not the whole glossary)."""
    gid1, gid2 = str(uuid4()), str(uuid4())
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(side_effect=AssertionError("must not list all"))
    gc.fetch_entities_by_ids = AsyncMock(return_value=[
        SimpleNamespace(entity_id=gid1, cached_name="Arthur",
                        kind_code="person", cached_aliases=["Art"]),
        SimpleNamespace(entity_id=gid2, cached_name="Merlin",
                        kind_code="person", cached_aliases=[]),
    ])

    async def fake_upsert(session, **kw):
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"]), True

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor_counted", fake_upsert,
    )

    res = await project_glossary_entities_to_nodes(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
        entity_ids=[gid1, gid2],
    )
    assert (res.created, res.existing, res.seen) == (2, 0, 2)
    gc.fetch_entities_by_ids.assert_awaited_once()


@pytest.mark.asyncio
async def test_projection_glossary_failure_is_zero_result(monkeypatch):
    """A glossary read failure (list_entities → None) → all-zero result, no upsert."""
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(return_value=None)

    async def fake_upsert(*a, **kw):
        raise AssertionError("must not upsert when the glossary read failed")

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor_counted", fake_upsert,
    )

    res = await project_glossary_entities_to_nodes(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )
    assert (res.created, res.existing, res.seen, res.skipped) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_projection_counts_glossary_fk_conflict_separately(monkeypatch):
    """LIVE-SMOKE REGRESSION — Entity.glossary_entity_id has a GLOBAL uniqueness
    constraint, so an entity already anchored by this book's OTHER knowledge project
    raises ConstraintError. It must be counted as `conflicted` (and explained to the
    caller), not folded into a smaller nodes_created that reads like success."""
    from neo4j.exceptions import ConstraintError

    gid_ok, gid_taken = str(uuid4()), str(uuid4())
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(return_value=([
        {"entity_id": gid_taken, "name": "Taken", "kind_code": "person"},
        {"entity_id": gid_ok, "name": "Fresh", "kind_code": "person"},
    ], False))

    async def fake_upsert(session, **kw):
        if kw["glossary_entity_id"] == gid_taken:
            raise ConstraintError("already exists with property glossary_entity_id")
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"]), True

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor_counted", fake_upsert,
    )
    res = await project_glossary_entities_to_nodes(
        session=MagicMock(), glossary_client=gc,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
    )
    assert (res.created, res.conflicted, res.skipped, res.seen) == (1, 1, 0, 2)


@pytest.mark.asyncio
async def test_projection_skips_bad_row_on_upsert_error(monkeypatch):
    """One upsert error is counted as skipped; the batch keeps going."""
    gid_ok, gid_bad = str(uuid4()), str(uuid4())
    gc = MagicMock()
    gc.list_all_entities = AsyncMock(return_value=([
        {"entity_id": gid_bad, "name": "Bad", "kind_code": "person"},
        {"entity_id": gid_ok, "name": "Good", "kind_code": "person"},
    ], False))

    async def fake_upsert(session, **kw):
        if kw["glossary_entity_id"] == gid_bad:
            raise RuntimeError("neo4j hiccup")
        return _make_entity(kw["name"], kw["kind"], kw["glossary_entity_id"]), True

    monkeypatch.setattr(
        "app.extraction.anchor_loader.upsert_glossary_anchor_counted", fake_upsert,
    )

    res = await project_glossary_entities_to_nodes(
        session=MagicMock(),
        glossary_client=gc,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        book_id=BOOK_ID,
    )
    assert (res.created, res.existing, res.seen, res.skipped) == (1, 0, 2, 1)
