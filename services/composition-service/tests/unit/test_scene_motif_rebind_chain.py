"""D-MOTIF-SCENE-REBIND-CHAIN — the per-scene role-rebind + legal-succession chain routes.

The FE binding card already wires two affordances the backend never served:
- ``RoleBindingRow`` → ``useMotifBinding.rebindRole`` → ``PATCH …/motif/role`` (rebind ONE
  role of a bound motif to a cast entity, or null = unresolve).
- ``ChainItHint`` → ``useMotifBinding.chainIt`` → ``POST …/motif/chain`` (pre-seed the NEXT
  node with a legal-succession motif resolved BY CODE).

These cover the route orchestration with faked pool/apps/glossary + stub repos: the
node-kind/tenancy 404s, the role-membership + in-cast guards, the by-code resolution, and
the `bound_via='chain'` provenance. The jsonb_set / SQL itself is the repo's concern.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

U, P, B, N, M = (uuid.uuid4() for _ in range(5))
EID = uuid.uuid4()


# ── fakes ──────────────────────────────────────────────────────────────────────

class _ACM:
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
    """Configurable: `bound` is the app returned by by_nodes (None = nothing bound)."""
    def __init__(self, bound=None):
        self._bound = bound
        self.set_calls: list = []
    async def by_nodes(self, p, nodes):
        return [self._bound] if self._bound is not None else []
    async def set_role_binding(self, p, node, role_key, entity_id, *, conn=None):
        self.set_calls.append((role_key, entity_id))
        return 1


class FakeKal:
    """KAL roster stub — returns the fully-drained cast `[{entity_id, name}]`."""
    def __init__(self, items):
        self._items = [{"entity_id": str(i["entity_id"]), "name": i["name"]}
                       for i in items if i.get("name") and i.get("entity_id")]
    async def roster(self, book_id, **kw):
        return list(self._items)


def _bound_app(role_bindings):
    return SimpleNamespace(motif_id=M, role_bindings=role_bindings)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    monkeypatch.setattr("app.routers.plan.get_pool", lambda: FakePool())

    from app.main import app
    from app.deps import get_grant_client_dep, get_kal_client_dep, get_outline_repo, get_works_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    # E0 book-grant authority stubbed at OWNER; the role/chain routes _require_work
    # (resolve the Work's book, then gate) before acting.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    work = SimpleNamespace(project_id=P, created_by=U, book_id=B, settings={})
    state = SimpleNamespace(node=None, kal=FakeKal([]))

    class _Works:
        async def get(self, p):
            return work
    class _Outline:
        async def get_node(self, node_id, *, conn=None):
            return state.node

    app.dependency_overrides[get_current_user] = lambda: U
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_works_repo] = lambda: _Works()
    app.dependency_overrides[get_outline_repo] = lambda: _Outline()
    app.dependency_overrides[get_kal_client_dep] = lambda: state.kal
    with TestClient(app) as c:
        yield c, state
    app.dependency_overrides.clear()


# ── PATCH …/motif/role (rebindRole) ──────────────────────────────────────────────

def test_rebind_role_updates_the_one_role(client, monkeypatch):
    c, state = client
    state.node = SimpleNamespace(project_id=P, kind="scene")
    state.kal = FakeKal([{"entity_id": str(EID), "name": "Lin"}])
    apps = FakeApps(bound=_bound_app({"seeker": None}))
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: apps)

    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif/role",
                json={"role_key": "seeker", "entity_id": str(EID)})
    assert r.status_code == 200
    body = r.json()
    assert body["rebound"] is True and body["role_key"] == "seeker"
    assert body["entity_id"] == str(EID)
    # exactly the targeted role was written.
    assert apps.set_calls == [("seeker", EID)]


def test_rebind_role_null_unresolves(client, monkeypatch):
    c, state = client
    state.node = SimpleNamespace(project_id=P, kind="scene")
    apps = FakeApps(bound=_bound_app({"seeker": str(EID)}))
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: apps)

    # entity_id omitted → null → unresolve; NO cast lookup needed.
    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif/role",
                json={"role_key": "seeker"})
    assert r.status_code == 200 and r.json()["entity_id"] is None
    assert apps.set_calls == [("seeker", None)]


def test_rebind_missing_node_is_404(client, monkeypatch):
    c, state = client
    state.node = None
    apps = FakeApps(bound=_bound_app({"seeker": None}))
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: apps)
    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif/role",
                json={"role_key": "seeker", "entity_id": str(EID)})
    assert r.status_code == 404 and apps.set_calls == []


def test_rebind_unbound_node_is_404(client, monkeypatch):
    c, state = client
    state.node = SimpleNamespace(project_id=P, kind="scene")
    apps = FakeApps(bound=None)  # nothing bound → no role to rebind
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: apps)
    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif/role",
                json={"role_key": "seeker", "entity_id": str(EID)})
    assert r.status_code == 404 and apps.set_calls == []


def test_rebind_unknown_role_key_is_404(client, monkeypatch):
    c, state = client
    state.node = SimpleNamespace(project_id=P, kind="scene")
    apps = FakeApps(bound=_bound_app({"seeker": None}))  # only 'seeker' exists
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: apps)
    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif/role",
                json={"role_key": "ghost", "entity_id": str(EID)})
    assert r.status_code == 404 and apps.set_calls == []  # no arbitrary jsonb-key write


def test_rebind_foreign_entity_not_in_cast_is_404(client, monkeypatch):
    c, state = client
    state.node = SimpleNamespace(project_id=P, kind="scene")
    state.kal = FakeKal([{"entity_id": str(uuid.uuid4()), "name": "Someone else"}])
    apps = FakeApps(bound=_bound_app({"seeker": None}))
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: apps)
    # EID is NOT in the book cast → rebind rejected (tenant-scoped), no write.
    r = c.patch(f"/v1/composition/works/{P}/outline/{N}/motif/role",
                json={"role_key": "seeker", "entity_id": str(EID)})
    assert r.status_code == 404 and apps.set_calls == []


# ── POST …/motif/chain (chainIt) ─────────────────────────────────────────────────

def _patch_motifrepo_codes(monkeypatch, by_code):
    class _Repo:
        def __init__(self, pool):
            pass
        async def get_by_codes(self, caller_id, codes):
            return {code: by_code[code] for code in codes if code in by_code}
    monkeypatch.setattr("app.routers.plan.MotifRepo", _Repo)


def test_chain_resolves_code_and_binds_via_chain(client, monkeypatch):
    c, state = client
    state.node = SimpleNamespace(project_id=P, kind="scene")
    motif = SimpleNamespace(id=M, code="revenge.face_slap", name="Face Slap")
    _patch_motifrepo_codes(monkeypatch, {"revenge.face_slap": motif})
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: object())

    captured = {}
    async def fake_bind(**kw):
        captured.update(kw)
        return {"node_id": str(kw["node_id"]), "motif_id": str(kw["motif_id"]), "bound": True}
    monkeypatch.setattr("app.routers.plan._bind_scene_motif", fake_bind)

    r = c.post(f"/v1/composition/works/{P}/outline/{N}/motif/chain",
               json={"to_motif_code": "revenge.face_slap"})
    assert r.status_code == 200
    body = r.json()
    assert body["chained"] is True and body["motif_code"] == "revenge.face_slap"
    assert body["bound"] is True
    # the resolved motif id + the chain provenance flowed into the ledger bind.
    assert captured["motif_id"] == M and captured["bound_via"] == "chain"
    assert captured["node_id"] == N


def test_chain_unresolvable_code_is_404(client, monkeypatch):
    c, state = client
    state.node = SimpleNamespace(project_id=P, kind="scene")
    _patch_motifrepo_codes(monkeypatch, {})  # no visible motif with that code
    called = {"bind": False}
    async def fake_bind(**kw):
        called["bind"] = True
        return {}
    monkeypatch.setattr("app.routers.plan._bind_scene_motif", fake_bind)

    r = c.post(f"/v1/composition/works/{P}/outline/{N}/motif/chain",
               json={"to_motif_code": "nope.missing"})
    assert r.status_code == 404 and called["bind"] is False


def test_chain_missing_node_is_404(client, monkeypatch):
    c, state = client
    state.node = None
    r = c.post(f"/v1/composition/works/{P}/outline/{N}/motif/chain",
               json={"to_motif_code": "revenge.face_slap"})
    assert r.status_code == 404


# ── _bind_scene_motif bound_via provenance (chain stamps annotations) ─────────────

async def test_bind_scene_motif_stamps_bound_via_chain(monkeypatch):
    from app.routers.plan import _bind_scene_motif

    class FakeApps2:
        def __init__(self):
            self.inserted: list = []
        async def delete_for_nodes(self, p, nodes, *, conn=None):
            return 0
        async def insert_many(self, p, b, rows, *, created_by=None, conn=None):
            self.inserted.extend(rows)
            return rows

    motif = SimpleNamespace(id=M, version=2, name="Face Slap", roles=[],
                            info_asymmetry=None, source="authored")
    class _Repo:
        def __init__(self, pool):
            pass
        async def get_visible(self, user_id, motif_id):
            return motif
    monkeypatch.setattr("app.db.repositories.motif_repo.MotifRepo", _Repo)

    apps = FakeApps2()
    await _bind_scene_motif(
        pool=FakePool(), apps=apps, kal=FakeKal([]),
        user_id=U, project_id=P, book_id=B, node_id=N, motif_id=M, bound_via="chain")
    assert apps.inserted[0]["annotations"]["bound_via"] == "chain"
