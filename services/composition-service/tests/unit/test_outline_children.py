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


# ── child_count badge field (navigator scene/chapter counts) ─────────────────

def test_outline_node_child_count_maps_and_defaults():
    base = dict(
        id=uuid4(), user_id=USER, project_id=PROJECT, parent_id=None,
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
    def __init__(self, nodes: list[_StubNode]) -> None:
        self.nodes = nodes
        self.calls: list[dict] = []

    async def list_children(self, user_id, project_id, parent_id, *, after=None, limit=100, include_archived=False):
        self.calls.append({"parent_id": parent_id, "after": after, "limit": limit})
        return self.nodes


class _StubWorks:
    async def get(self, user_id, project_id):
        return object()  # non-None → _require_work passes


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_outline_repo, get_works_repo
    from app.middleware.jwt_auth import get_current_user

    holder: dict = {"repo": None}
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: _StubWorks()
    app.dependency_overrides[get_outline_repo] = lambda: holder["repo"]
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
