"""D-MOTIF-FE-SWAP-NODE-GRANULARITY — per-SCENE motif bind/swap/clear.

The chapter swap (`apply_motif_swap`) regenerates a chapter's scenes from a motif's
beats and REQUIRES a chapter node. Shape A's per-scene binding surface needs a
lightweight scene-level write instead: `_bind_scene_motif` records one
`motif_application` for a single scene node, atomically replacing any prior binding,
with NO scene regeneration. The PATCH/DELETE routes dispatch on `node.kind`.

These cover the orchestration with faked pool/apps/glossary + a stub MotifRepo (the
SQL itself is covered by the motif_application repo tests; role resolution by
bind_motif's tests) and the route's node-kind dispatch + tenancy 404.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.routers.plan import _bind_scene_motif

U, P, B, N, M = (uuid.uuid4() for _ in range(5))


# ── fakes for the helper ──────────────────────────────────────────────────────

class _ACM:
    """An async context manager yielding `val` (for pool.acquire() / conn.transaction())."""
    def __init__(self, val=None):
        self._val = val
    async def __aenter__(self):
        return self._val
    async def __aexit__(self, *a):
        return False


class FakeConn:
    def transaction(self):
        return _ACM()


class FakePool:
    def __init__(self):
        self._c = FakeConn()
    def acquire(self):
        return _ACM(self._c)


class FakeApps:
    def __init__(self):
        self.deleted: list = []
        self.inserted: list = []
    async def delete_for_nodes(self, p, nodes, *, conn=None):
        self.deleted.append(list(nodes))
        return len(nodes)
    async def insert_many(self, p, b, rows, *, created_by=None, conn=None):
        self.inserted.extend(rows)
        return rows


class FakeKal:
    """KAL roster stub — returns the fully-drained cast `[{entity_id, name}]`."""
    def __init__(self, items):
        self._items = [{"entity_id": str(i["entity_id"]), "name": i["name"]}
                       for i in items if i.get("name") and i.get("entity_id")]
    async def roster(self, book_id, **kw):
        return list(self._items)


def _fake_motif(mid, *, roles=None, name="Auction-House Treasure", version=3):
    return SimpleNamespace(id=mid, version=version, name=name,
                           roles=roles or [], info_asymmetry=None, source="authored")


def _patch_motifrepo(monkeypatch, motif):
    class _Repo:
        def __init__(self, pool):
            pass
        async def get_visible(self, user_id, motif_id):
            return motif
    monkeypatch.setattr("app.db.repositories.motif_repo.MotifRepo", _Repo)


# ── _bind_scene_motif orchestration ───────────────────────────────────────────

async def test_clear_deletes_the_nodes_binding():
    apps = FakeApps()
    out = await _bind_scene_motif(
        pool=FakePool(), apps=apps, kal=FakeKal([]),
        user_id=U, project_id=P, book_id=B, node_id=N, motif_id=None)
    assert out["cleared"] is True and out["node_id"] == str(N)
    assert apps.deleted == [[N]] and apps.inserted == []


async def test_bind_writes_one_application_replacing_prior(monkeypatch):
    eid = uuid.uuid4()
    motif = _fake_motif(M, roles=[{"key": "bidder", "label": "the bidder",
                                   "constraints": ["short on resources"]}])
    _patch_motifrepo(monkeypatch, motif)
    apps = FakeApps()
    out = await _bind_scene_motif(
        pool=FakePool(), apps=apps,
        kal=FakeKal([{"entity_id": str(eid), "name": "the bidder"}]),
        user_id=U, project_id=P, book_id=B, node_id=N, motif_id=M)
    assert out["bound"] is True and out["motif_id"] == str(M)
    assert out["motif_name"] == "Auction-House Treasure"
    # replace-then-insert: prior binding dropped BEFORE the new row → exactly one row.
    assert apps.deleted == [[N]]
    assert len(apps.inserted) == 1
    row = apps.inserted[0]
    assert row["motif_id"] == str(M) and row["motif_version"] == 3
    assert row["outline_node_id"] == str(N)
    assert row["annotations"]["bound_via"] == "manual_scene"
    # motif-level (a manual scene bind is not a plan-time beat match).
    assert "beat_key" not in row["annotations"]
    # role resolved by NAME HINT to the cast entity.
    assert row["role_bindings"]["bidder"] == str(eid)


async def test_motif_not_visible_is_404_and_writes_nothing(monkeypatch):
    _patch_motifrepo(monkeypatch, None)  # get_visible → None (foreign/archived motif)
    apps = FakeApps()
    with pytest.raises(HTTPException) as ei:
        await _bind_scene_motif(
            pool=FakePool(), apps=apps, kal=FakeKal([]),
            user_id=U, project_id=P, book_id=B, node_id=N, motif_id=M)
    assert ei.value.status_code == 404
    assert apps.inserted == [] and apps.deleted == []  # H13: no write on a rejected motif


# ── route node-kind dispatch + tenancy ────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())        # lifespan
    monkeypatch.setattr("app.routers.plan.get_pool", lambda: FakePool())  # route Tx

    from app.main import app
    from app.deps import (get_book_client_dep, get_grant_client_dep, get_kal_client_dep,
                          get_outline_repo, get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    # E0 book-grant authority stubbed at OWNER; the motif route _require_work
    # (resolve the Work's book, then gate) before dispatching on node.kind.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    work = SimpleNamespace(project_id=P, created_by=U, book_id=B, settings={})
    outline = SimpleNamespace(node=None)

    class _Works:
        async def get(self, p):
            return work
    class _Outline:
        async def get_node(self, node_id, *, conn=None):
            return outline.node

    app.dependency_overrides[get_current_user] = lambda: U
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_works_repo] = lambda: _Works()
    app.dependency_overrides[get_book_client_dep] = lambda: object()
    app.dependency_overrides[get_kal_client_dep] = lambda: object()
    app.dependency_overrides[get_outline_repo] = lambda: _Outline()
    with TestClient(app) as c:
        yield c, outline
    app.dependency_overrides.clear()


def test_patch_scene_node_routes_to_scene_bind(client, monkeypatch):
    c, outline = client
    outline.node = SimpleNamespace(project_id=P, kind="scene")

    async def fake_scene_bind(**kw):
        return {"routed": "scene", "node_id": str(kw["node_id"])}
    monkeypatch.setattr("app.routers.plan._bind_scene_motif", fake_scene_bind)

    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif", json={"motif_id": str(M)})
    assert r.status_code == 200
    assert r.json()["routed"] == "scene"


def test_patch_chapter_node_routes_to_chapter_swap(client, monkeypatch):
    c, outline = client
    outline.node = SimpleNamespace(project_id=P, kind="chapter")
    called = {}

    async def fake_swap(*a, **kw):
        called["chapter"] = True
        return SimpleNamespace(chapter_node_id=str(N), archived_scene_ids=[], new_scene_ids=[],
                               orphaned_thread_ids=[], new_motif_id=None, undo_token=None)
    monkeypatch.setattr("app.routers.plan.apply_motif_swap", fake_swap)

    # motif_id=None (clear) → skips the motif lookup, goes straight to apply_motif_swap.
    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif", json={"motif_id": None})
    assert r.status_code == 200 and called.get("chapter") is True
    assert r.json()["chapter_node_id"] == str(N)


def test_patch_missing_or_cross_project_node_is_404(client):
    c, outline = client
    outline.node = None  # not found / not owned
    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif", json={"motif_id": str(M)})
    assert r.status_code == 404


def test_delete_scene_node_clears_via_ledger(client, monkeypatch):
    c, outline = client
    outline.node = SimpleNamespace(project_id=P, kind="scene")
    apps = FakeApps()
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: apps)

    r = c.delete(f"/v1/composition/works/{P}/outline/{N}/motif")
    assert r.status_code == 200 and r.json()["cleared"] is True
    assert apps.deleted == [[N]]
