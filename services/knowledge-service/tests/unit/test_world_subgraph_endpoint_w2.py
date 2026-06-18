"""G4 (W2) — GET /v1/knowledge/worlds/{world_id}/subgraph endpoint wiring.

Tests the membership → project-resolution → union orchestration + the
WorldNotFound→404 / BookServiceUnavailable→503 mapping, with the book client,
projects repo, get_world_subgraph and neo4j_session all faked/patched. The live
cross-service round-trip is the W2 live-smoke.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.clients.book_client import BookServiceUnavailable, WorldNotFound
from app.db.neo4j_repos.relations import SUBGRAPH_MAX_NODE_CAP, Subgraph, SubgraphNode

_TEST_USER = uuid4()
_OTHER_USER = uuid4()
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


def test_rollup_resolves_world_and_member_projects_and_unions():
    wp, p1, p2 = uuid4(), uuid4(), uuid4()
    b1, b2 = uuid4(), uuid4()
    repo = _FakeRepo(
        world_projs=[_P(wp, _TEST_USER)],
        by_book={b1: _P(p1, _TEST_USER), b2: _P(p2, _TEST_USER)},
    )
    book = _FakeBook(items=[{"book_id": str(b1)}, {"book_id": str(b2)}])
    sg = Subgraph(nodes=[SubgraphNode(id="n", name="n", kind="person")], edges=[])
    try:
        with patch(
            "app.routers.public.entities.get_world_subgraph",
            new_callable=AsyncMock, return_value=sg,
        ) as mock_union, patch(
            "app.routers.public.entities.neo4j_session", new=lambda: _noop_session(),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/subgraph")
        assert resp.status_code == 200, resp.json()
        kwargs = mock_union.await_args.kwargs
        # world-level project FIRST, then each member book's project, deduped
        assert kwargs["project_ids"] == [str(wp), str(p1), str(p2)]
        assert kwargs["user_id"] == str(_TEST_USER)
    finally:
        _teardown()


def test_shared_member_book_project_excluded():
    """A member book owned by another user (shared into the world) resolves to a
    project whose user_id != the caller — we can't read that partition, so it's
    skipped rather than passed to the union (where it would just be empty)."""
    wp, p1, p2 = uuid4(), uuid4(), uuid4()
    b1, b2 = uuid4(), uuid4()
    repo = _FakeRepo(
        world_projs=[_P(wp, _TEST_USER)],
        by_book={b1: _P(p1, _TEST_USER), b2: _P(p2, _OTHER_USER)},  # b2 shared
    )
    book = _FakeBook(items=[{"book_id": str(b1)}, {"book_id": str(b2)}])
    try:
        with patch(
            "app.routers.public.entities.get_world_subgraph",
            new_callable=AsyncMock, return_value=Subgraph(),
        ) as mock_union, patch(
            "app.routers.public.entities.neo4j_session", new=lambda: _noop_session(),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/subgraph")
        assert resp.status_code == 200, resp.json()
        assert mock_union.await_args.kwargs["project_ids"] == [str(wp), str(p1)]
    finally:
        _teardown()


def test_world_not_found_maps_to_404():
    repo = _FakeRepo([], {})
    book = _FakeBook(exc=WorldNotFound(str(_WORLD)))
    try:
        with patch(
            "app.routers.public.entities.get_world_subgraph", new_callable=AsyncMock,
        ) as mock_union, patch(
            "app.routers.public.entities.neo4j_session", new=lambda: _noop_session(),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/subgraph")
        assert resp.status_code == 404
        assert mock_union.await_count == 0  # never reached the union
    finally:
        _teardown()


def test_book_service_unavailable_maps_to_503():
    repo = _FakeRepo([], {})
    book = _FakeBook(exc=BookServiceUnavailable("down"))
    try:
        with patch(
            "app.routers.public.entities.get_world_subgraph", new_callable=AsyncMock,
        ), patch(
            "app.routers.public.entities.neo4j_session", new=lambda: _noop_session(),
        ):
            resp = _client(repo, book).get(f"/v1/knowledge/worlds/{_WORLD}/subgraph")
        assert resp.status_code == 503
    finally:
        _teardown()


def test_limit_above_cap_rejected_422():
    repo = _FakeRepo([], {})
    book = _FakeBook(items=[])
    try:
        with patch(
            "app.routers.public.entities.get_world_subgraph", new_callable=AsyncMock,
        ) as mock_union:
            resp = _client(repo, book).get(
                f"/v1/knowledge/worlds/{_WORLD}/subgraph?limit={SUBGRAPH_MAX_NODE_CAP + 1}"
            )
        assert resp.status_code == 422
        assert mock_union.await_count == 0
    finally:
        _teardown()
