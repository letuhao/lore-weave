"""24 H5/H1 — the arc routes the Plan Hub drives: the E0 grant gate on each, and the
PH9/OQ-2 derived block the arc shell (read surface #1) must carry.

Why these exist (both are enforcement gaps a review caught, not new behaviour):

  * GRANT GATE — `POST /arcs/{id}/move` and `POST /books/{id}/arcs/assign-chapters` became
    live user write surface in H5. Both DO gate (`_gate_arc` → `_gate_book`, EDIT), but no
    test issued a request to either: deleting the `await _gate_book(...)` line left the whole
    suite green. Tenancy is LOCKED — a rule with no test that goes red is drift waiting to
    happen. The by-id move gates on the ROW's book (`gate-must-derive-scope-from-the-loaded-row`),
    and a missing node returns the SAME uniform 404 as a denied grant (no oracle).

  * DERIVED BLOCK — the Hub renders NO lanes without `span`/`is_contiguous`/`chapter_count` on
    each shell node. This attach already regressed once (the repo had the data; the router
    didn't attach it — the Hub came up empty against the real backend while every unit test
    passed, because the FE mocks returned the enriched shape). The repo function is covered
    only under an env-gated DB skip, so the ATTACH itself needs a runnable guard.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import StructureNode
from app.grant_client import GrantLevel

USER, BOOK, ARC, SAGA = uuid4(), uuid4(), uuid4(), uuid4()


class _Grant:
    def __init__(self, level):
        self._level = level

    async def resolve_grant(self, book_id, user_id):
        return self._level

    async def resolve_access(self, book_id, user_id):
        return self._level, "active"


def _node(node_id, *, kind="arc", parent_id=None, rank="0m", title="Arc") -> StructureNode:
    return StructureNode(
        id=node_id, book_id=BOOK, parent_id=parent_id, kind=kind,
        depth=0 if parent_id is None else 1, rank=rank, title=title,
    )


@pytest.fixture
def client(monkeypatch):
    """TestClient factory: `mk(level, structures=...)` → (client, structures_mock).

    `_structures()` is a plain module function (not a Depends), so it is monkeypatched
    rather than dependency-overridden.
    """
    from app.main import app
    from app.deps import get_grant_client_dep
    from app.middleware.jwt_auth import get_bearer_token, get_current_user
    import app.routers.arc as arc_router

    def mk(level: GrantLevel, structures: AsyncMock | None = None):
        repo = structures or AsyncMock()
        monkeypatch.setattr(arc_router, "_structures", lambda: repo)
        app.dependency_overrides[get_current_user] = lambda: USER
        app.dependency_overrides[get_bearer_token] = lambda: "jwt"
        app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(level)
        return TestClient(app), repo

    yield mk
    app.dependency_overrides.clear()


# ── the grant gate on the H5 write routes ──────────────────────────────────────


def test_assign_chapters_view_grantee_403_and_never_writes(client):
    c, repo = client(GrantLevel.VIEW)
    r = c.post(
        f"/v1/composition/books/{BOOK}/arcs/assign-chapters",
        json={"structure_node_id": str(ARC), "chapter_node_ids": [str(uuid4())]},
    )
    assert r.status_code == 403
    repo.assign_chapters.assert_not_called()


def test_assign_chapters_non_grantee_404_and_never_writes(client):
    c, repo = client(GrantLevel.NONE)
    r = c.post(
        f"/v1/composition/books/{BOOK}/arcs/assign-chapters",
        json={"structure_node_id": str(ARC), "chapter_node_ids": [str(uuid4())]},
    )
    assert r.status_code == 404
    repo.assign_chapters.assert_not_called()


def test_arc_move_view_grantee_403_and_never_writes(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.VIEW, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/move", json={"new_parent_arc_id": None, "after_id": None})
    assert r.status_code == 403
    repo.move.assert_not_called()


def test_arc_move_non_grantee_404_and_never_writes(client):
    # The row EXISTS and its book resolves — but the caller holds no grant on that book.
    # 404 (not 403) so a non-grantee cannot use the status code as an existence oracle.
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.NONE, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/move", json={"new_parent_arc_id": None, "after_id": None})
    assert r.status_code == 404
    repo.move.assert_not_called()


def test_arc_move_missing_node_is_the_same_404_as_a_denied_grant(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    c, repo = client(GrantLevel.OWNER, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/move", json={"new_parent_arc_id": None, "after_id": None})
    assert r.status_code == 404
    repo.move.assert_not_called()


def test_arc_list_non_grantee_404(client):
    c, repo = client(GrantLevel.NONE)
    r = c.get(f"/v1/composition/books/{BOOK}/arcs")
    assert r.status_code == 404
    repo.list_tree.assert_not_called()


# ── BE-A2: PATCH /arcs/{id} REQUIRES If-Match (no blind clobber) ────────────────


def test_patch_arc_without_if_match_is_428_and_never_writes(client):
    # The MCP door requires expected_version; the REST door used to make If-Match OPTIONAL,
    # so a missing header skipped the version clause AND the version bump — a legal blind
    # clobber on the object that steers generation. BE-A2: absent ⇒ 428, update untouched.
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.EDIT, structures=repo)
    r = c.patch(f"/v1/composition/arcs/{ARC}", json={"title": "New title"})
    assert r.status_code == 428
    assert r.json()["detail"]["code"] == "IF_MATCH_REQUIRED"
    repo.update.assert_not_called()


def test_patch_arc_with_if_match_passes_expected_version(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    repo.update = AsyncMock(return_value=_node(ARC, title="New title"))
    c, repo = client(GrantLevel.EDIT, structures=repo)
    r = c.patch(
        f"/v1/composition/arcs/{ARC}", json={"title": "New title"}, headers={"If-Match": "7"},
    )
    assert r.status_code == 200
    assert repo.update.call_args.kwargs["expected_version"] == 7


def test_patch_arc_missing_if_match_gates_before_precondition(client):
    # Auth before precondition: a non-grantee with no If-Match still gets the uniform 404
    # (no existence oracle), never a 428 that would confirm the row exists.
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.NONE, structures=repo)
    r = c.patch(f"/v1/composition/arcs/{ARC}", json={"title": "New title"})
    assert r.status_code == 404
    repo.update.assert_not_called()


# ── read surface #1: the derived block MUST ride on every shell node ───────────


def test_arc_list_attaches_the_derived_block_to_every_node(client):
    repo = AsyncMock()
    repo.list_tree = AsyncMock(return_value=[_node(SAGA, kind="saga", title="Saga"), _node(ARC, parent_id=SAGA)])
    repo.derived_blocks = AsyncMock(return_value={
        SAGA: {"span": {"from_order": 1, "to_order": 7}, "is_contiguous": False, "chapter_count": 5},
        ARC: {"span": {"from_order": 1, "to_order": 3}, "is_contiguous": True, "chapter_count": 3},
    })
    c, _ = client(GrantLevel.VIEW, structures=repo)

    r = c.get(f"/v1/composition/books/{BOOK}/arcs")
    assert r.status_code == 200
    nodes = {n["id"]: n for n in r.json()["nodes"]}

    assert nodes[str(SAGA)]["span"] == {"from_order": 1, "to_order": 7}
    assert nodes[str(SAGA)]["is_contiguous"] is False
    assert nodes[str(SAGA)]["chapter_count"] == 5
    assert nodes[str(ARC)]["chapter_count"] == 3
    # The raw node fields are untouched — the block is ADDITIVE (the Chapter Browser shares
    # this route and reads only the raw fields).
    assert nodes[str(ARC)]["kind"] == "arc"
    assert nodes[str(ARC)]["parent_id"] == str(SAGA)


def test_arc_list_node_with_no_chapters_gets_the_empty_block_not_a_missing_key(client):
    # An arc absent from the derived map holds no chapters. It must still carry the block —
    # a MISSING key would make the FE read `undefined` and fall back to a wrong default
    # (`fe-status-default-fallback-signals-backend-field-omission`).
    repo = AsyncMock()
    repo.list_tree = AsyncMock(return_value=[_node(ARC)])
    repo.derived_blocks = AsyncMock(return_value={})
    c, _ = client(GrantLevel.VIEW, structures=repo)

    node = c.get(f"/v1/composition/books/{BOOK}/arcs").json()["nodes"][0]
    assert node["span"] is None
    assert node["is_contiguous"] is True
    assert node["chapter_count"] == 0
