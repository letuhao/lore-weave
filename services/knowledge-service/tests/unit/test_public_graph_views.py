"""Lane LD — unit tests for the graph-views + temporal-read router.

Two layers, both driver-free:
  * pure builders (`build_graph_slice`, `build_timeline`, `_coerce_ordinal`)
    exercised directly — the view-scope + temporal filter applied to raw
    `{rel, subj, obj}` records;
  * the FastAPI router mounted with overrides (get_current_user, the repo dep,
    the project-grant dep) + a FAKE neo4j session so the graph-read handler's
    Cypher→filter→response wiring is asserted without a live Neo4j.

Live Neo4j graph-read smoke is deferred (D-KG-LD-NEO4J-SMOKE) — TEST_NEO4J_URI
is usually unset on the dev stack.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.public.graph_views as gv
from app.auth.grant_deps import project_meta_dep
from app.db.ontology_models import GraphView
from app.deps import get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.routers.public.graph_views import (
    _coerce_ordinal,
    build_graph_slice,
    build_timeline,
    get_graph_schemas_repo,
    get_graph_views_repo,
    router,
)


# ── pure helpers ───────────────────────────────────────────────────────────
def _view(**kw) -> GraphView:
    now = datetime.now(timezone.utc)
    base = dict(
        view_id=uuid4(), project_id="p", user_id=uuid4(), code="lens",
        name="Lens", description="", edge_type_codes=[], node_kind_codes=[],
        created_at=now, updated_at=now,
    )
    base.update(kw)
    return GraphView(**base)


def _rec(pred, sid, oid, *, vf=None, vt=None, skind="character", okind="character", sv=None):
    return {
        "rel": {"predicate": pred, "valid_from": vf, "valid_to": vt, "schema_version": sv},
        "subj": {"id": sid, "kind": skind, "name": sid, "glossary_entity_id": None},
        "obj": {"id": oid, "kind": okind, "name": oid, "glossary_entity_id": None},
    }


def test_coerce_ordinal():
    assert _coerce_ordinal(5) == 5
    assert _coerce_ordinal(None) is None
    assert _coerce_ordinal(3.0) == 3
    assert _coerce_ordinal(3.5) is None
    assert _coerce_ordinal(True) is None  # bool excluded
    assert _coerce_ordinal(datetime.now(timezone.utc)) is None  # legacy ts → None


def test_build_graph_slice_identity_no_view():
    recs = [_rec("PURSUES", "a", "b"), _rec("ALLY_OF", "b", "c")]
    sl = build_graph_slice(recs, view=None, as_of_chapter=None, deprecated_edge_codes=[], view_code=None)
    assert {e.edge_type for e in sl.edges} == {"PURSUES", "ALLY_OF"}
    assert {n.id for n in sl.nodes} == {"a", "b", "c"}
    assert sl.warnings == []
    assert sl.view is None


def test_build_graph_slice_view_edge_filter():
    recs = [_rec("PURSUES", "a", "b"), _rec("ALLY_OF", "b", "c")]
    view = _view(edge_type_codes=["PURSUES"])
    sl = build_graph_slice(recs, view=view, as_of_chapter=None, deprecated_edge_codes=[], view_code="lens")
    assert [e.edge_type for e in sl.edges] == ["PURSUES"]
    # node 'c' only reachable via the filtered-out ALLY_OF edge → absent
    assert {n.id for n in sl.nodes} == {"a", "b"}


def test_build_graph_slice_node_kind_filter_drops_edge():
    recs = [_rec("PURSUES", "a", "loc", okind="location")]
    view = _view(node_kind_codes=["character"])
    sl = build_graph_slice(recs, view=view, as_of_chapter=None, deprecated_edge_codes=[], view_code="lens")
    # the edge's target is a location, outside the lens → edge dropped
    assert sl.edges == []
    assert sl.nodes == []


def test_build_graph_slice_temporal_as_of():
    recs = [
        _rec("PURSUES", "a", "revenge", vf=1, vt=10),
        _rec("PURSUES", "a", "seek_dao", vf=10, vt=None),
    ]
    # at chapter 5: only the revenge instance is open (1<=5<10)
    sl5 = build_graph_slice(recs, view=None, as_of_chapter=5, deprecated_edge_codes=[], view_code=None)
    assert [e.target_id for e in sl5.edges] == ["revenge"]
    assert sl5.as_of_chapter == 5
    # at latest (None): only the still-open seek_dao instance
    slx = build_graph_slice(recs, view=None, as_of_chapter=None, deprecated_edge_codes=[], view_code=None)
    assert [e.target_id for e in slx.edges] == ["seek_dao"]


def test_build_graph_slice_deprecated_warning():
    recs = [_rec("OLD_EDGE", "a", "b")]
    view = _view(edge_type_codes=["OLD_EDGE"])
    sl = build_graph_slice(recs, view=view, as_of_chapter=None, deprecated_edge_codes=["OLD_EDGE"], view_code="lens")
    assert sl.warnings == ["view references deprecated edge type 'OLD_EDGE'"]


def test_build_timeline_orders_and_maps():
    recs = [
        {"rel": {"valid_from": 1, "valid_to": 10, "schema_version": 2, "source_chapter": "ch1"},
         "obj": {"id": "revenge", "name": "Revenge"}},
        {"rel": {"valid_from": 10, "valid_to": None, "schema_version": 2, "source_chapter": "ch10"},
         "obj": {"id": "seek_dao", "name": "Seek Dao"}},
    ]
    tl = build_timeline("kai", "PURSUES", recs)
    assert tl.entity_id == "kai" and tl.edge_type == "PURSUES"
    assert [i.target_id for i in tl.instances] == ["revenge", "seek_dao"]
    assert tl.instances[0].valid_to == 10
    assert tl.instances[0].evidence_chapter_id == "ch1"
    assert tl.instances[1].valid_to is None


# ── router CRUD with a fake repo ───────────────────────────────────────────
class FakeViewsRepo:
    """In-memory GraphViewsRepo keyed by (user_id, project_id, code) so
    owner-scoping is enforced by construction."""

    def __init__(self):
        self._rows: dict[tuple, GraphView] = {}

    async def list(self, user_id, project_id):
        return [v for (u, p, _c), v in self._rows.items() if u == user_id and p == project_id]

    async def get(self, user_id, project_id, code):
        return self._rows.get((user_id, project_id, code))

    async def create(self, user_id, project_id, *, code, name, description="", edge_type_codes=None, node_kind_codes=None):
        import asyncpg
        key = (user_id, project_id, code)
        if key in self._rows:
            raise asyncpg.UniqueViolationError("dup")
        now = datetime.now(timezone.utc)
        v = GraphView(view_id=uuid4(), project_id=project_id, user_id=user_id, code=code,
                      name=name, description=description, edge_type_codes=list(edge_type_codes or []),
                      node_kind_codes=list(node_kind_codes or []), created_at=now, updated_at=now)
        self._rows[key] = v
        return v

    async def upsert(self, user_id, project_id, *, code, name, description="", edge_type_codes=None, node_kind_codes=None):
        key = (user_id, project_id, code)
        created = key not in self._rows
        now = datetime.now(timezone.utc)
        v = GraphView(view_id=uuid4(), project_id=project_id, user_id=user_id, code=code,
                      name=name, description=description, edge_type_codes=list(edge_type_codes or []),
                      node_kind_codes=list(node_kind_codes or []), created_at=now, updated_at=now)
        self._rows[key] = v
        return v, created

    async def delete(self, user_id, project_id, code):
        return self._rows.pop((user_id, project_id, code), None) is not None


@pytest.fixture
def auth_user():
    return uuid4()


@pytest.fixture
def repo():
    return FakeViewsRepo()


# D-KG-LD-VIEWS-GRANT — the CRUD writes now require a VIEW grant on the project.
# Tests use a real UUID project and override the grant gate so project_meta returns
# (owner==caller, no book) → the gate's caller==owner branch authorizes.
_PROJ = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def crud_client(repo, auth_user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_graph_views_repo] = lambda: repo
    app.dependency_overrides[get_grant_client] = lambda: object()
    app.dependency_overrides[project_meta_dep] = lambda: (auth_user, None)
    return TestClient(app)


def test_create_then_list_view(crud_client):
    r = crud_client.post(f"/v1/kg/projects/{_PROJ}/views", json={"name": "Drive Map", "edge_type_codes": ["PURSUES"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "drive_map"  # slugified
    assert body["edge_type_codes"] == ["PURSUES"]
    lst = crud_client.get(f"/v1/kg/projects/{_PROJ}/views")
    assert [v["code"] for v in lst.json()["items"]] == ["drive_map"]


def test_create_duplicate_code_409(crud_client):
    crud_client.post(f"/v1/kg/projects/{_PROJ}/views", json={"name": "L", "code": "lens"})
    r = crud_client.post(f"/v1/kg/projects/{_PROJ}/views", json={"name": "L2", "code": "lens"})
    assert r.status_code == 409


def test_create_undeducible_code_422(crud_client):
    r = crud_client.post(f"/v1/kg/projects/{_PROJ}/views", json={"name": "!!!"})
    assert r.status_code == 422


def test_upsert_create_then_update(crud_client):
    r1 = crud_client.put(f"/v1/kg/projects/{_PROJ}/views/lens", json={"name": "v1"})
    assert r1.status_code == 201
    r2 = crud_client.put(f"/v1/kg/projects/{_PROJ}/views/lens", json={"name": "v2", "node_kind_codes": ["character"]})
    assert r2.status_code == 200
    assert r2.json()["name"] == "v2"
    assert r2.json()["node_kind_codes"] == ["character"]


def test_delete_view_then_404(crud_client):
    crud_client.put(f"/v1/kg/projects/{_PROJ}/views/lens", json={"name": "v"})
    assert crud_client.delete(f"/v1/kg/projects/{_PROJ}/views/lens").status_code == 204
    assert crud_client.delete(f"/v1/kg/projects/{_PROJ}/views/lens").status_code == 404


def test_create_view_requires_project_grant(repo, auth_user):
    """D-KG-LD-VIEWS-GRANT: a caller with no grant on the project (non-owner,
    book-less project → owner-only) gets 404 at the gate, before the repo."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: uuid4()  # NOT the owner
    app.dependency_overrides[get_graph_views_repo] = lambda: repo
    app.dependency_overrides[get_grant_client] = lambda: object()
    app.dependency_overrides[project_meta_dep] = lambda: (auth_user, None)  # owner=auth_user
    c = TestClient(app)
    r = c.post(f"/v1/kg/projects/{_PROJ}/views", json={"name": "X", "code": "x"})
    assert r.status_code == 404


def test_grantee_creates_view_stored_under_grantee(repo, auth_user):
    """D-KG-LD-VIEWS-GRANT: a book collaborator with a VIEW grant on a SHARED
    project mints a view stored under THEIR user_id (per-user lens) — the gate
    authorizes (returns the owner) but the repo owner-scopes the row to the
    caller, so a grantee gets their own lens, never the owner's."""
    from app.clients.grant_client import GrantLevel

    owner = auth_user
    grantee = uuid4()
    book_id = uuid4()

    class _FakeGrant:
        async def resolve_grant(self, b, caller):
            return GrantLevel.VIEW

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: grantee
    app.dependency_overrides[get_graph_views_repo] = lambda: repo
    app.dependency_overrides[get_grant_client] = lambda: _FakeGrant()
    app.dependency_overrides[project_meta_dep] = lambda: (owner, book_id)
    c = TestClient(app)
    r = c.post(f"/v1/kg/projects/{_PROJ}/views", json={"name": "Grantee lens", "code": "glens"})
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == str(grantee)  # stored under the grantee
    # owner-scoped: the row is keyed to the grantee, not the owner.
    assert (grantee, _PROJ, "glens") in repo._rows
    assert (owner, _PROJ, "glens") not in repo._rows


def test_views_are_owner_scoped(repo, auth_user):
    """A second user does not see the first user's views (owner scoping)."""
    other = uuid4()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_graph_views_repo] = lambda: repo
    app.dependency_overrides[get_grant_client] = lambda: object()
    # grant gate: owner == auth_user (book-less project → owner-only).
    app.dependency_overrides[project_meta_dep] = lambda: (auth_user, None)
    # user A (the owner) creates a view
    app.dependency_overrides[get_current_user] = lambda: auth_user
    c_a = TestClient(app)
    c_a.post(f"/v1/kg/projects/{_PROJ}/views", json={"name": "A lens", "code": "alens"})
    # user B lists — sees nothing (list is ungated; owner-scoped repo returns [])
    app.dependency_overrides[get_current_user] = lambda: other
    c_b = TestClient(app)
    assert c_b.get(f"/v1/kg/projects/{_PROJ}/views").json()["items"] == []
    # user B deleting A's code → 404 (gate: non-owner on a book-less project)
    assert c_b.delete(f"/v1/kg/projects/{_PROJ}/views/alens").status_code == 404


# ── graph-read handler with a fake neo4j session ───────────────────────────
class _FakeResult:
    def __init__(self, records):
        self._records = records

    def __aiter__(self):
        async def gen():
            for r in self._records:
                yield r
        return gen()


class _FakeRecord:
    def __init__(self, d):
        self._d = d

    def keys(self):
        return self._d.keys()

    def __getitem__(self, k):
        return self._d[k]


class _FakeSession:
    def __init__(self, records):
        self._records = records

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def run(self, cypher, **params):
        # K11.4 asserts $user_id is present in the cypher before we get here.
        assert "$user_id" in cypher
        return _FakeResult(self._records)


def test_graph_read_applies_view_and_temporal(monkeypatch, repo, auth_user):
    project_id = uuid4()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_graph_views_repo] = lambda: repo
    app.dependency_overrides[get_graph_schemas_repo] = lambda: object()
    app.dependency_overrides[get_grant_client] = lambda: object()
    # grant gate: project_meta returns (owner==caller, no book) → _resolve_owner
    # short-circuits to owner (the gate's caller==owner branch).
    app.dependency_overrides[project_meta_dep] = lambda: (auth_user, None)

    # fake neo4j: two PURSUES instances + one ALLY_OF
    records = [
        _FakeRecord({k: dict(v) for k, v in _rec("PURSUES", "a", "revenge", vf=1, vt=10).items()}),
        _FakeRecord({k: dict(v) for k, v in _rec("PURSUES", "a", "seek_dao", vf=10, vt=None).items()}),
        _FakeRecord({k: dict(v) for k, v in _rec("ALLY_OF", "a", "b").items()}),
    ]
    monkeypatch.setattr(gv, "neo4j_session", lambda **kw: _FakeSession(records))

    async def _fake_deprecated(repo_, pid):
        return ["OLD_EDGE"]
    monkeypatch.setattr(gv, "_deprecated_edge_codes", _fake_deprecated)

    client = TestClient(app)
    # create a PURSUES-only view owned by the caller (uses the fake repo)
    client.post(f"/v1/kg/projects/{project_id}/views",
                json={"name": "Drives", "code": "drives", "edge_type_codes": ["PURSUES", "OLD_EDGE"]})

    # at chapter 5 with the drives view: only the open revenge instance
    r = client.get(f"/v1/kg/projects/{project_id}/graph?view=drives&as_of_chapter=5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["target_id"] for e in body["edges"]] == ["revenge"]
    assert body["as_of_chapter"] == 5
    assert body["view"] == "drives"
    # the view references a deprecated edge OLD_EDGE → warning
    assert body["warnings"] == ["view references deprecated edge type 'OLD_EDGE'"]


def test_graph_read_unknown_view_404(monkeypatch, repo, auth_user):
    project_id = uuid4()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_graph_views_repo] = lambda: repo
    app.dependency_overrides[get_graph_schemas_repo] = lambda: object()
    app.dependency_overrides[get_grant_client] = lambda: object()
    app.dependency_overrides[project_meta_dep] = lambda: (auth_user, None)
    monkeypatch.setattr(gv, "neo4j_session", lambda **kw: _FakeSession([]))
    client = TestClient(app)
    r = client.get(f"/v1/kg/projects/{project_id}/graph?view=nope")
    assert r.status_code == 404


# ── timeline handler with a fake neo4j session + stubbed grant ─────────────
def test_edge_timeline(monkeypatch, auth_user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_grant_client] = lambda: object()
    app.dependency_overrides[get_projects_repo] = lambda: object()

    # stub the grant-gate (its own resolution is covered by the repo + grant
    # tests); here we assert the Cypher→build_timeline wiring.
    async def _ok_grant(entity_id, caller, gc, projects_repo):
        return "proj-x"
    monkeypatch.setattr(gv, "_resolve_entity_project_grant", _ok_grant)

    records = [
        _FakeRecord({
            "rel": {"valid_from": 1, "valid_to": 10, "schema_version": 1, "source_chapter": "ch1"},
            "obj": {"id": "revenge", "name": "Revenge"},
        }),
        _FakeRecord({
            "rel": {"valid_from": 10, "valid_to": None, "schema_version": 1, "source_chapter": "ch10"},
            "obj": {"id": "seek_dao", "name": "Seek Dao"},
        }),
    ]
    monkeypatch.setattr(gv, "neo4j_session", lambda **kw: _FakeSession(records))

    client = TestClient(app)
    r = client.get("/v1/kg/entities/kai/edges/PURSUES/timeline")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entity_id"] == "kai" and body["edge_type"] == "PURSUES"
    assert [i["target_id"] for i in body["instances"]] == ["revenge", "seek_dao"]
    assert body["instances"][0]["evidence_chapter_id"] == "ch1"
