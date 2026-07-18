"""Wave-4 (D-MOTIF-GRAPH-CANVAS) — the book motif-graph routes (GET graph, PATCH layout).

TestClient + dependency_overrides; the graph repo is monkeypatched (its DB work is proven in
test_motif_graph_layout + the B7 live smoke). Focus: the response SHAPE, the OCC 412 reseed, and
the foreign-motif 404 (no oracle) — the NEW logic these routes add.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.grant_client import GrantLevel

USER = uuid4()
BOOK = uuid4()


class _Grant:
    def __init__(self, level):
        self._level = level

    async def resolve_grant(self, book_id, user_id):
        return self._level

    async def resolve_access(self, book_id, user_id):
        return self._level


@pytest.fixture
def client(monkeypatch):
    from app.main import app
    from app.deps import get_grant_client_dep
    from app.middleware.jwt_auth import get_current_user
    import app.routers.motif as motif_router

    def mk(level: GrantLevel, repo: AsyncMock | None = None):
        repo = repo or AsyncMock()
        monkeypatch.setattr(motif_router, "get_pool", lambda: None)
        monkeypatch.setattr(motif_router, "MotifGraphLayoutRepo", lambda _pool: repo)
        app.dependency_overrides[get_current_user] = lambda: USER
        app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(level)
        return TestClient(app), repo

    yield mk
    app.dependency_overrides.clear()


def test_get_graph_returns_nodes_edges_and_the_callers_layout(client):
    repo = AsyncMock()
    n1, n2 = uuid4(), uuid4()
    repo.nodes_for_book.return_value = [
        {"id": n1, "owner_user_id": USER, "book_shared": False, "code": "a", "kind": "scheme", "name": "A", "visibility": "private"},
        {"id": n2, "owner_user_id": USER, "book_shared": False, "code": "b", "kind": "sequence", "name": "B", "visibility": "private"},
    ]
    repo.edges_among.return_value = [{"id": uuid4(), "from_motif_id": n1, "to_motif_id": n2, "kind": "precedes", "ord": 1}]
    repo.get.return_value = ({str(n1): {"x": 1, "y": 2}}, 3)
    c, _ = client(GrantLevel.VIEW, repo)
    r = c.get(f"/v1/composition/books/{BOOK}/motif-graph")
    assert r.status_code == 200
    d = r.json()
    assert [n["code"] for n in d["nodes"]] == ["a", "b"]
    assert d["nodes"][0]["mine"] is True
    assert len(d["edges"]) == 1 and d["edges"][0]["kind"] == "precedes"
    assert d["layout"]["version"] == 3 and d["layout"]["positions"][str(n1)] == {"x": 1, "y": 2}
    assert d["truncated"] is False


def test_get_graph_flags_truncation_past_the_cap(client, monkeypatch):
    import app.routers.motif as motif_router
    monkeypatch.setattr(motif_router, "_MOTIF_GRAPH_NODE_CAP", 2)
    repo = AsyncMock()
    ids = [uuid4() for _ in range(3)]  # cap+1 → truncated
    repo.nodes_for_book.return_value = [
        {"id": i, "owner_user_id": USER, "book_shared": False, "code": f"c{n}", "kind": "scheme", "name": f"N{n}", "visibility": "private"}
        for n, i in enumerate(ids)
    ]
    repo.edges_among.return_value = []
    repo.get.return_value = ({}, 0)
    c, _ = client(GrantLevel.VIEW, repo)
    d = c.get(f"/v1/composition/books/{BOOK}/motif-graph").json()
    assert d["truncated"] is True and len(d["nodes"]) == 2  # capped, and it says so


def test_patch_layout_merges_and_returns_new_version(client):
    repo = AsyncMock()
    repo.motif_visible_in_book.return_value = True
    m = uuid4()
    repo.merge.return_value = ({str(m): {"x": 5, "y": 6}}, 4)
    c, _ = client(GrantLevel.VIEW, repo)
    r = c.patch(f"/v1/composition/books/{BOOK}/motif-graph/layout",
                json={"moves": [{"motif_id": str(m), "x": 5, "y": 6}], "if_version": 3})
    assert r.status_code == 200
    d = r.json()
    assert d["version"] == 4 and d["positions"][str(m)] == {"x": 5, "y": 6}
    repo.merge.assert_awaited_once()


def test_patch_layout_occ_conflict_412_reseeds_current(client):
    repo = AsyncMock()
    repo.motif_visible_in_book.return_value = True
    repo.merge.return_value = None  # OCC conflict
    repo.get.return_value = ({"m": {"x": 0, "y": 0}}, 9)
    c, _ = client(GrantLevel.VIEW, repo)
    r = c.patch(f"/v1/composition/books/{BOOK}/motif-graph/layout",
                json={"moves": [{"motif_id": str(uuid4()), "x": 1, "y": 1}], "if_version": 2})
    assert r.status_code == 412
    detail = r.json()["detail"]
    assert detail["code"] == "MOTIF_GRAPH_LAYOUT_STALE"
    assert detail["current"]["version"] == 9  # the client reseeds from this


def test_patch_layout_foreign_motif_404_and_never_writes(client):
    """A motif the caller can't see in this book → uniform 404 (no oracle); merge never runs."""
    repo = AsyncMock()
    repo.motif_visible_in_book.return_value = False
    c, _ = client(GrantLevel.VIEW, repo)
    r = c.patch(f"/v1/composition/books/{BOOK}/motif-graph/layout",
                json={"moves": [{"motif_id": str(uuid4()), "x": 1, "y": 1}], "if_version": 0})
    assert r.status_code == 404
    repo.merge.assert_not_called()
