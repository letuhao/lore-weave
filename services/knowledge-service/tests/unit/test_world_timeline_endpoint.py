"""D-WORLD-TIMELINE-ROLLUP — GET /v1/knowledge/worlds/{world_id}/timeline.

Tests the membership→project-resolution→event-union orchestration: per-project
reads merged + re-sorted on the global axis + capped, with the same
WorldNotFound→404 / BookServiceUnavailable→503 mapping as the subgraph rollup.
The book client, projects repo, list_events_filtered, neo4j_session and the
chapter-title enricher are faked/patched.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.clients.book_client import BookServiceUnavailable, WorldNotFound
from app.db.neo4j_repos.events import Event

_TEST_USER = uuid4()
_WORLD = uuid4()


class _P:
    def __init__(self, pid, uid):
        self.project_id = pid
        self.user_id = uid


class _FakeRepo:
    def __init__(self, world_projs, by_book):
        self._wp = world_projs
        self._bb = by_book

    async def list(self, user_id, *, world_id=None, limit=50, **kw):
        return self._wp

    async def get_by_book(self, book_id):
        return self._bb.get(book_id)


class _FakeBook:
    def __init__(self, items=None, exc=None):
        self._items = items or []
        self._exc = exc

    async def list_world_books(self, world_id, user_id):
        if self._exc:
            raise self._exc
        return self._items


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _ev(eid: str, pid: str, order: int) -> Event:
    return Event(
        id=eid,
        user_id=str(_TEST_USER),
        project_id=pid,
        title=eid,
        canonical_title=eid,
        event_order=order,
    )


def _client(repo, book):
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import get_book_client, get_projects_repo

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: repo
    app.dependency_overrides[get_book_client] = lambda: book
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    from app.main import app

    app.dependency_overrides.clear()


def test_union_merges_member_timelines_sorted_by_event_order():
    wp, p1 = uuid4(), uuid4()
    b1 = uuid4()
    repo = _FakeRepo(world_projs=[_P(wp, _TEST_USER)], by_book={b1: _P(p1, _TEST_USER)})
    book = _FakeBook(items=[{"book_id": str(b1)}])

    # world-level project contributes orders 10,30; member book contributes 20.
    per_project = {
        str(wp): [_ev("e10", str(wp), 10), _ev("e30", str(wp), 30)],
        str(p1): [_ev("e20", str(p1), 20)],
    }

    async def fake_list(session, *, project_id, **kw):
        return (per_project.get(project_id, []), len(per_project.get(project_id, [])))

    try:
        with patch(
            "app.routers.public.timeline.list_events_filtered",
            new=AsyncMock(side_effect=fake_list),
        ), patch(
            "app.routers.public.timeline.neo4j_session", new=lambda: _noop_session(),
        ), patch(
            "app.routers.public.timeline.enrich_events_with_chapter_titles",
            new=AsyncMock(return_value=None),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/timeline")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        # merged + globally sorted by event_order across BOTH partitions.
        assert [e["id"] for e in body["events"]] == ["e10", "e20", "e30"]
        # each event keeps its source project_id (FE legends per book).
        assert {e["project_id"] for e in body["events"]} == {str(wp), str(p1)}
        assert body["total"] == 3
        assert body["truncated"] is False
    finally:
        _teardown()


def test_union_caps_and_flags_truncated():
    wp = uuid4()
    repo = _FakeRepo(world_projs=[_P(wp, _TEST_USER)], by_book={})
    book = _FakeBook(items=[])
    events = [_ev(f"e{i}", str(wp), i) for i in range(5)]

    async def fake_list(session, *, project_id, **kw):
        return (events, len(events))

    try:
        with patch(
            "app.routers.public.timeline.list_events_filtered",
            new=AsyncMock(side_effect=fake_list),
        ), patch(
            "app.routers.public.timeline.neo4j_session", new=lambda: _noop_session(),
        ), patch(
            "app.routers.public.timeline.enrich_events_with_chapter_titles",
            new=AsyncMock(return_value=None),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/timeline?limit=3")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert len(body["events"]) == 3
        assert body["total"] == 5
        assert body["truncated"] is True
    finally:
        _teardown()


def test_world_not_found_maps_to_404():
    repo = _FakeRepo([], {})
    book = _FakeBook(exc=WorldNotFound(str(_WORLD)))
    try:
        with patch(
            "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock,
        ) as mock_list, patch(
            "app.routers.public.timeline.neo4j_session", new=lambda: _noop_session(),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/timeline")
        assert resp.status_code == 404
        assert mock_list.await_count == 0
    finally:
        _teardown()


def test_book_service_unavailable_maps_to_503():
    repo = _FakeRepo([], {})
    book = _FakeBook(exc=BookServiceUnavailable("down"))
    try:
        with patch(
            "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock,
        ), patch(
            "app.routers.public.timeline.neo4j_session", new=lambda: _noop_session(),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/timeline")
        assert resp.status_code == 503
    finally:
        _teardown()
