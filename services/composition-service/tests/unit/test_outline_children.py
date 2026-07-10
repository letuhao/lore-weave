"""#02 manuscript navigator — outline lazy-children endpoint (cursor paging).

Covers the pure keyset-cursor helpers and the endpoint's page/trim/next_cursor logic
via a TestClient with a fake OutlineRepo (no DB) — mirrors test_routers.py's override
pattern. The live SQL (rank COLLATE "C" keyset) is exercised by the Phase 4 E2E.
"""
from __future__ import annotations

import base64
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db.models import OutlineNode
from app.routers.outline import _decode_child_cursor, _encode_child_cursor

USER = UUID("00000000-0000-0000-0000-0000000000aa")
PROJECT = UUID("00000000-0000-0000-0000-0000000000bb")
BOOK = UUID("00000000-0000-0000-0000-0000000000cc")


# ── child_count badge field (navigator scene/chapter counts) ─────────────────

def test_outline_node_child_count_maps_and_defaults():
    base = dict(
        id=uuid4(), created_by=USER, project_id=PROJECT, book_id=BOOK, parent_id=None,
        kind="chapter", rank="a0",
    )
    # a row FROM list_children carries child_count → it maps onto the model.
    assert OutlineNode.model_validate({**base, "child_count": 7}).child_count == 7
    # a row from any other query (no child_count column) is None — "not computed", not 0.
    assert OutlineNode.model_validate(base).child_count is None


# ── pure cursor helpers ──────────────────────────────────────────────────────

def test_child_cursor_round_trip():
    nid = uuid4()
    rank, got = _decode_child_cursor(_encode_child_cursor("a0", nid))
    assert rank == "a0" and got == nid
    # a rank containing '|' still round-trips — id is recovered via rpartition.
    r2, g2 = _decode_child_cursor(_encode_child_cursor("a|b|c", nid))
    assert r2 == "a|b|c" and g2 == nid


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty
        "!!not-base64!!",  # bad base64
        base64.urlsafe_b64encode(b"nopipe").decode(),  # no separator
        base64.urlsafe_b64encode(b"r|not-a-uuid").decode(),  # bad uuid
    ],
)
def test_child_cursor_rejects_malformed(bad):
    with pytest.raises(HTTPException) as ei:
        _decode_child_cursor(bad)
    assert ei.value.status_code == 400


# ── endpoint paging (fake repo) ──────────────────────────────────────────────

class _StubNode:
    def __init__(self, rank: str, nid: UUID, child_count: int = 0) -> None:
        self.rank = rank
        self.id = nid
        self.child_count = child_count

    def model_dump(self, mode: str = "json") -> dict:
        return {"id": str(self.id), "rank": self.rank, "child_count": self.child_count}


class _FakeOutline:
    def __init__(self, nodes: list[_StubNode], search_items: list[dict] | None = None) -> None:
        self.nodes = nodes
        self.search_items = search_items or []
        self.calls: list[dict] = []
        self.search_calls: list[dict] = []
        self.chapter_node: UUID | None = None

    async def list_children(self, project_id, parent_id, *, after=None, limit=100, include_archived=False):
        self.calls.append({"parent_id": parent_id, "after": after, "limit": limit})
        return self.nodes

    async def search_nodes(self, project_id, q, *, limit=30):
        self.search_calls.append({"q": q, "limit": limit})
        return self.search_items

    async def outline_stats(self, project_id):
        return {"arcs": 1, "chapters": 12, "scenes": 35}

    async def scenes_for_chapter(self, project_id, chapter_id):
        self.calls.append({"scenes_for_chapter": chapter_id, "project_id": project_id})
        return self.nodes

    async def chapter_node_id(self, project_id, chapter_id):
        return self.chapter_node


class _StubWorks:
    async def get(self, project_id):
        # non-None with a book_id → _require_work resolves + gates on the book.
        from types import SimpleNamespace
        return SimpleNamespace(book_id=BOOK)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_grant_client_dep, get_outline_repo, get_works_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # E0 book-grant authority stubbed at OWNER; the navigator endpoints
    # _require_work (resolve the Work's book, then gate VIEW) before reading.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    holder: dict = {"repo": None}
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: _StubWorks()
    app.dependency_overrides[get_outline_repo] = lambda: holder["repo"]
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, holder
    app.dependency_overrides.clear()


def test_first_page_emits_next_cursor(client):
    c, holder = client
    nodes = [_StubNode(f"a{i}", uuid4()) for i in range(4)]  # limit=3 → repo returns limit+1
    holder["repo"] = _FakeOutline(nodes)
    r = c.get(f"/v1/composition/works/{PROJECT}/outline/children?limit=3")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3  # extra row trimmed
    assert body["next_cursor"] is not None
    rank, nid = _decode_child_cursor(body["next_cursor"])  # cursor of the last KEPT node
    assert rank == nodes[2].rank and nid == nodes[2].id
    call = holder["repo"].calls[0]
    assert call["parent_id"] is None  # omitted → top-level arcs
    assert call["limit"] == 3


def test_child_count_flows_to_response(client):
    c, holder = client
    nodes = [_StubNode("a0", uuid4(), child_count=3), _StubNode("a1", uuid4(), child_count=0)]
    holder["repo"] = _FakeOutline(nodes)
    body = c.get(f"/v1/composition/works/{PROJECT}/outline/children?limit=10").json()
    assert [it["child_count"] for it in body["items"]] == [3, 0]


def test_last_page_has_no_next_cursor(client):
    c, holder = client
    holder["repo"] = _FakeOutline([_StubNode(f"a{i}", uuid4()) for i in range(2)])  # ≤ limit
    body = c.get(f"/v1/composition/works/{PROJECT}/outline/children?limit=3").json()
    assert len(body["items"]) == 2 and body["next_cursor"] is None


def test_bad_cursor_is_400(client):
    c, holder = client
    holder["repo"] = _FakeOutline([])
    assert c.get(f"/v1/composition/works/{PROJECT}/outline/children?cursor=%21%21bad").status_code == 400


# ── #12 cycle-1: chapter scenes (the manuscript-unit document's scenes[] source) ──

def test_chapter_scenes_wraps_scenes_for_chapter(client):
    c, holder = client
    chapter_id = uuid4()
    chapter_node = uuid4()
    repo = _FakeOutline([_StubNode("a0", uuid4()), _StubNode("a1", uuid4())])
    repo.chapter_node = chapter_node
    holder["repo"] = repo
    r = c.get(f"/v1/composition/works/{PROJECT}/chapters/{chapter_id}/scenes")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    # M-G: the outline chapter node rides along (the rail's Create target)
    assert body["chapter_node_id"] == str(chapter_node)
    # tenancy (25 re-key): the repo query is keyed by project + chapter (the Work
    # partition); access is decided at the E0 book gate, not in the repo.
    call = holder["repo"].calls[0]
    assert call["scenes_for_chapter"] == chapter_id
    assert call["project_id"] == PROJECT


def test_chapter_scenes_null_chapter_node_when_never_outlined(client):
    c, holder = client
    holder["repo"] = _FakeOutline([])
    r = c.get(f"/v1/composition/works/{PROJECT}/chapters/{uuid4()}/scenes")
    assert r.status_code == 200
    assert r.json()["chapter_node_id"] is None


def test_parent_id_and_cursor_passed_through(client):
    c, holder = client
    holder["repo"] = _FakeOutline([])
    pid, nid = uuid4(), uuid4()
    cur = _encode_child_cursor("m5", nid)
    r = c.get(f"/v1/composition/works/{PROJECT}/outline/children?parent_id={pid}&cursor={cur}")
    assert r.status_code == 200
    call = holder["repo"].calls[0]
    assert call["parent_id"] == pid
    assert call["after"] == ("m5", nid)


# ── outline search (jump box / #06a) ─────────────────────────────────────────

def test_search_returns_items_and_passes_trimmed_query(client):
    c, holder = client
    hit = {"id": str(uuid4()), "kind": "scene", "title": "Bị phản bội",
           "chapter_id": str(uuid4()), "status": "done", "story_order": 1,
           "path": ["Arc I", "Ch 0001"]}
    holder["repo"] = _FakeOutline([], search_items=[hit])
    r = c.get(f"/v1/composition/works/{PROJECT}/outline/search?q=%20phản%20&limit=10")
    assert r.status_code == 200
    assert r.json()["items"] == [hit]
    call = holder["repo"].search_calls[0]
    assert call["q"] == "phản"   # trimmed
    assert call["limit"] == 10


def test_search_empty_query_short_circuits(client):
    c, holder = client
    holder["repo"] = _FakeOutline([], search_items=[{"id": "x"}])
    r = c.get(f"/v1/composition/works/{PROJECT}/outline/search?q=%20%20")
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert holder["repo"].search_calls == []  # never hit the repo for an empty query


def test_search_limit_is_clamped(client):
    c, holder = client
    holder["repo"] = _FakeOutline([], search_items=[])
    c.get(f"/v1/composition/works/{PROJECT}/outline/search?q=a&limit=999")
    assert holder["repo"].search_calls[0]["limit"] == 50  # clamped to max


def test_stats_returns_kind_totals(client):
    c, holder = client
    holder["repo"] = _FakeOutline([])
    r = c.get(f"/v1/composition/works/{PROJECT}/outline/stats")
    assert r.status_code == 200
    assert r.json() == {"arcs": 1, "chapters": 12, "scenes": 35}
