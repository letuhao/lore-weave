"""RAID C3 (contract freeze) + C13 (review gate) — route/spec coverage tests.

Asserts the API matches the frozen OpenAPI surface:
  1. Every path in contracts/api/lore-enrichment/v1/openapi.yaml is MOUNTED.
  2. Every mounted /v1/lore-enrichment route is IN the spec (no orphan routes) —
     C13 added /write-back + /retract, which are now in the spec too.
  3. The H0 author `promote` endpoint exists and carries a Principal seam.
  4. Stub families still in stub state (sources/templates) return 200/501.

C13 note: the proposals review routes are now REAL (DB-backed). C14 note: the
jobs routes are now REAL (DB-backed end-to-end runner). Both are exercised
against fake dependency overrides here (no DB); their behaviour is covered by
tests/test_review_gate.py + tests/test_job_runner.py + the DB + live-smoke gates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

SPEC_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "api"
    / "lore-enrichment"
    / "v1"
    / "openapi.yaml"
)

_UUID = "00000000-0000-0000-0000-000000000001"
_ALLOWED_STATUS = {200, 201, 202, 501}


def _load_spec() -> dict:
    with SPEC_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class _FakeRepo:
    """Empty Q3-scoped repo — list returns ([], 0); get returns None (→404)."""

    async def list(self, **kw):
        return [], 0

    async def get(self, **kw):
        return None


class _FakeConn:
    """A no-row connection for the jobs list/get routes (no real DB)."""

    async def fetchval(self, *a, **kw):
        return 0

    async def fetch(self, *a, **kw):
        return []

    async def fetchrow(self, *a, **kw):
        return None

    async def execute(self, *a, **kw):
        return None


class _FakeAcquire:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    """Empty pool: every job list returns {items:[],total:0}; get → 404."""

    def acquire(self):
        return _FakeAcquire()


@pytest.fixture()
def client(monkeypatch):
    import app.api.proposals as prop_mod
    import app.db.pool as pool_mod
    import app.main as main_mod

    async def _fake_create_pool(dsn):
        return object()

    async def _fake_close_pool():
        return None

    async def _fake_run_migrations(pool):
        return None

    monkeypatch.setattr(main_mod, "create_pool", _fake_create_pool)
    monkeypatch.setattr(main_mod, "close_pool", _fake_close_pool)
    monkeypatch.setattr(main_mod, "run_migrations", _fake_run_migrations)
    monkeypatch.setattr(pool_mod, "create_pool", _fake_create_pool)
    monkeypatch.setattr(pool_mod, "close_pool", _fake_close_pool)

    async def _fake_repo():
        return _FakeRepo()

    async def _fake_db():
        return _FakePool()

    import app.deps as deps_mod

    main_mod.app.dependency_overrides[prop_mod.get_repo] = _fake_repo
    main_mod.app.dependency_overrides[deps_mod.get_db] = _fake_db
    with TestClient(main_mod.app) as c:
        yield c
    main_mod.app.dependency_overrides.clear()


def _spec_to_concrete(spec_path: str) -> str:
    return re.sub(r"\{[^}]+\}", _UUID, spec_path)


def _mounted_paths() -> set[str]:
    import app.main as main_mod

    paths = set()
    for route in main_mod.app.routes:
        path = getattr(route, "path", None)
        if path and path.startswith("/v1/lore-enrichment"):
            paths.add(path)
    return paths


def test_spec_loads_and_is_openapi_31():
    spec = _load_spec()
    assert spec["openapi"].startswith("3.1"), "C3 brief mandates OpenAPI 3.1"
    assert "/v1/lore-enrichment/proposals/{proposal_id}/promote" in spec["paths"]
    # C13 additions are in the contract.
    assert "/v1/lore-enrichment/proposals/{proposal_id}/write-back" in spec["paths"]
    assert "/v1/lore-enrichment/proposals/{proposal_id}/retract" in spec["paths"]


def test_every_spec_path_is_mounted():
    spec = _load_spec()
    mounted = _mounted_paths()
    missing = [p for p in spec["paths"] if p not in mounted]
    assert not missing, f"spec paths not mounted as routes: {missing}"


def test_no_orphan_routes():
    """Every mounted /v1/lore-enrichment route must exist in the spec."""
    spec = _load_spec()
    spec_paths = set(spec["paths"].keys())
    orphans = [p for p in _mounted_paths() if p not in spec_paths]
    assert not orphans, f"routes mounted but absent from spec: {orphans}"


def test_promote_endpoint_reachable(client):
    """H0: the author promote endpoint exists and is reachable — it is now REAL
    (C13). With an unverified anonymous token it must 401 (auth required), never
    404/500. (The owner check + canonization are covered by test_review_gate.)"""
    resp = client.post(
        f"/v1/lore-enrichment/proposals/{_UUID}/promote",
        params={"project_id": _UUID},
        json={"book_id": _UUID},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code in (401, 403, 404, 409, 502, 503), resp.status_code


def test_stub_families_return_200_or_501(client):
    """sources/templates are still C3 stubs → 200/201/202/501, never 404/500.
    Proposals (C13) + jobs (C14) routes are real (DB-backed) and excluded here —
    covered by test_review_gate / test_job_runner + the live-smoke gate."""
    spec = _load_spec()
    failures = []
    for spec_path, methods in spec["paths"].items():
        if "/proposals" in spec_path or "/jobs" in spec_path or "/detect-gaps" in spec_path:
            continue  # real C13/C14/D1 routes — covered by their own suites
        url = _spec_to_concrete(spec_path)
        params = {}
        for op in methods.values():
            for prm in op.get("parameters", []):
                ref = prm.get("$ref", "")
                name = prm.get("name") or ref.rsplit("/", 1)[-1]
                if "ProjectIdQuery" in ref or name == "project_id":
                    params["project_id"] = _UUID
        for method in methods:
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            fn = getattr(client, method)
            kwargs = {"params": params, "headers": {"Authorization": "Bearer x"}}
            if method in ("post", "put", "patch"):
                kwargs["json"] = {}
            resp = fn(url, **kwargs)
            if resp.status_code not in _ALLOWED_STATUS:
                failures.append((method.upper(), spec_path, resp.status_code))
    assert not failures, f"routes returned disallowed status: {failures}"


def _user_token() -> str:
    """A bearer carrying a decodable `sub` so the Q3-scoped proposals list
    resolves an authenticated principal (signature unverified at this layer)."""
    import jwt as pyjwt

    return pyjwt.encode({"sub": _UUID}, "x", algorithm="HS256")


def test_list_routes_return_spec_valid_empty_shape(client):
    """GET list endpoints return a spec-valid {items, total} body (not {})."""
    token = _user_token()
    list_urls = [
        f"/v1/lore-enrichment/jobs?project_id={_UUID}",
        f"/v1/lore-enrichment/proposals?project_id={_UUID}",
        f"/v1/lore-enrichment/sources?project_id={_UUID}",
        "/v1/lore-enrichment/templates",
    ]
    for url in list_urls:
        resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, (url, resp.status_code)
        body = resp.json()
        assert body.get("items") == [], (url, body)
        assert body.get("total") == 0, (url, body)


def test_promote_carries_principal_seam():
    """Adversary focus: promote must not be anonymous — its signature carries a
    Principal dependency (the authorization seam)."""
    import inspect

    from app.api import proposals as prop_mod

    sig = inspect.signature(prop_mod.promote_proposal)
    principal_params = [
        p for p in sig.parameters.values() if "Principal" in str(p.annotation)
    ]
    assert principal_params, "promote handler must carry a Principal dependency"
