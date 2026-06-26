"""T2.1 — unit tests for the Cast & Codex routes (status / facts / timeline
spoiler-window). Neo4j + book-service are mocked; the spoiler resolver is patched
so these assert the ROUTER wiring (window threading, fail-closed propagation,
param validation). Integration coverage lives in tests/integration/db/.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.neo4j_repos.entities import Entity
from app.db.neo4j_repos.facts import Fact

_TEST_USER = uuid4()
_PROJECT_ID = uuid4()
_CHAPTER_ID = uuid4()
_ENTITY_ID = "ent-kael-1"


def _entity_stub(eid: str, name: str = "Kael", kind: str = "character") -> Entity:
    return Entity(
        id=eid, user_id=str(_TEST_USER), project_id=str(_PROJECT_ID),
        name=name, canonical_name=name.lower(), kind=kind, aliases=[name],
        canonical_version=1, source_types=["book_content"], confidence=0.9,
        mention_count=4, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _fact_stub(content: str, ftype: str = "decision", from_order: int | None = 0) -> Fact:
    return Fact(
        id=f"fact-{content[:8]}", user_id=str(_TEST_USER), project_id=str(_PROJECT_ID),
        type=ftype, content=content, canonical_content=content.lower(),
        confidence=0.9, from_order=from_order,
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _make_client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import (
        get_book_client,
        get_entity_alias_map_repo,
        get_event_text_translations_repo,
        get_glossary_client,
        get_projects_repo,
        get_translation_client,
    )

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_book_client] = lambda: AsyncMock()
    app.dependency_overrides[get_entity_alias_map_repo] = lambda: AsyncMock()
    # KG-TL — timeline router now resolves these eagerly (canonical path doesn't
    # call them; they just need to construct without the live pool).
    app.dependency_overrides[get_projects_repo] = lambda: AsyncMock()
    app.dependency_overrides[get_glossary_client] = lambda: AsyncMock()
    app.dependency_overrides[get_translation_client] = lambda: AsyncMock()
    app.dependency_overrides[get_event_text_translations_repo] = lambda: AsyncMock()
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    from app.main import app
    app.dependency_overrides.clear()


# ── GET /entities/statuses ────────────────────────────────────────────


@patch("app.routers.public.entities.statuses_detail_at_order", new_callable=AsyncMock)
@patch("app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock)
@patch("app.routers.public.entities.resolve_before_order", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_statuses_happy_threads_window(mock_resolve, mock_list, mock_status):
    mock_resolve.return_value = (999, True)
    mock_list.return_value = ([_entity_stub("e1"), _entity_stub("e2", "Mira")], 2)
    mock_status.return_value = {
        "e1": {"status": "gone", "from_order": 5},
        "e2": {"status": "active", "from_order": None},
    }
    client = _make_client()
    try:
        resp = client.get(
            f"/v1/knowledge/entities/statuses?project_id={_PROJECT_ID}"
            f"&before_chapter_id={_CHAPTER_ID}"
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["window_available"] is True
        assert body["statuses"]["e1"] == {"status": "gone", "from_order": 5}
        assert body["statuses"]["e2"]["status"] == "active"
        # batched over the project's entity ids, windowed at the resolved ceiling.
        assert mock_status.await_args.kwargs["entity_ids"] == ["e1", "e2"]
        assert mock_status.await_args.kwargs["at_order"] == 999
    finally:
        _teardown()


@patch("app.routers.public.entities.statuses_detail_at_order", new_callable=AsyncMock)
@patch("app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock)
@patch("app.routers.public.entities.resolve_before_order", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_statuses_window_unavailable_propagates(mock_resolve, mock_list, mock_status):
    # fail-closed: no chapter → -1 window, all-active, window_available False.
    mock_resolve.return_value = (-1, False)
    mock_list.return_value = ([_entity_stub("e1")], 1)
    mock_status.return_value = {"e1": {"status": "active", "from_order": None}}
    client = _make_client()
    try:
        resp = client.get(f"/v1/knowledge/entities/statuses?project_id={_PROJECT_ID}")
        assert resp.status_code == 200, resp.json()
        assert resp.json()["window_available"] is False
        assert mock_status.await_args.kwargs["at_order"] == -1
    finally:
        _teardown()


def test_statuses_requires_project_id():
    client = _make_client()
    try:
        assert client.get("/v1/knowledge/entities/statuses").status_code == 422
    finally:
        _teardown()


# ── GET /entities/{id}/facts ──────────────────────────────────────────


@patch("app.routers.public.entities.list_facts_for_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.resolve_before_order", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_facts_happy_threads_window(mock_resolve, mock_facts):
    mock_resolve.return_value = (50, True)
    mock_facts.return_value = [_fact_stub("broke the oath"), _fact_stub("prefers tea", "preference")]
    client = _make_client()
    try:
        resp = client.get(
            f"/v1/knowledge/entities/{_ENTITY_ID}/facts?before_chapter_id={_CHAPTER_ID}"
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["window_available"] is True
        assert [f["content"] for f in body["facts"]] == ["broke the oath", "prefers tea"]
        assert mock_facts.await_args.kwargs["entity_id"] == _ENTITY_ID
        assert mock_facts.await_args.kwargs["before_order"] == 50
    finally:
        _teardown()


@patch("app.routers.public.entities.list_facts_for_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.resolve_before_order", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_facts_window_unavailable_empty(mock_resolve, mock_facts):
    mock_resolve.return_value = (-1, False)
    mock_facts.return_value = []
    client = _make_client()
    try:
        resp = client.get(f"/v1/knowledge/entities/{_ENTITY_ID}/facts")
        assert resp.status_code == 200, resp.json()
        assert resp.json() == {"facts": [], "window_available": False}
        assert mock_facts.await_args.kwargs["before_order"] == -1
    finally:
        _teardown()


@patch("app.routers.public.entities.list_facts_for_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.resolve_before_order", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_facts_rejects_oversized_id(mock_resolve, mock_facts):
    client = _make_client()
    try:
        resp = client.get("/v1/knowledge/entities/" + ("x" * 201) + "/facts")
        assert resp.status_code == 422
        mock_facts.assert_not_awaited()
    finally:
        _teardown()


# ── GET /timeline?before_chapter_id= ──────────────────────────────────


@patch("app.routers.public.timeline.enrich_events_with_chapter_titles", new_callable=AsyncMock)
@patch("app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock)
@patch("app.routers.public.timeline.resolve_before_order", new_callable=AsyncMock)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_resolves_before_chapter_id(mock_resolve, mock_list, _mock_enrich):
    mock_resolve.return_value = (777, True)
    mock_list.return_value = ([], 0)
    client = _make_client()
    try:
        resp = client.get(f"/v1/knowledge/timeline?before_chapter_id={_CHAPTER_ID}")
        assert resp.status_code == 200, resp.json()
        assert mock_list.await_args.kwargs["before_order"] == 777
    finally:
        _teardown()


@patch("app.routers.public.timeline.enrich_events_with_chapter_titles", new_callable=AsyncMock)
@patch("app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock)
@patch("app.routers.public.timeline.resolve_before_order", new_callable=AsyncMock)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_explicit_before_order_wins(mock_resolve, mock_list, _mock_enrich):
    mock_list.return_value = ([], 0)
    client = _make_client()
    try:
        resp = client.get(
            f"/v1/knowledge/timeline?before_order=10&before_chapter_id={_CHAPTER_ID}"
        )
        assert resp.status_code == 200, resp.json()
        assert mock_list.await_args.kwargs["before_order"] == 10
        mock_resolve.assert_not_awaited()  # explicit value wins, resolver untouched
    finally:
        _teardown()
