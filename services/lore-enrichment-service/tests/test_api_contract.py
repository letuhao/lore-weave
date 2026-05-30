"""RAID C3 — contract-freeze route tests.

Asserts the stub API matches the frozen OpenAPI surface:
  1. Every path in contracts/api/lore-enrichment/v1/openapi.yaml is MOUNTED on
     the FastAPI app (no spec path missing a route).
  2. Every mounted /v1/lore-enrichment route is IN the spec (no orphan routes).
  3. The H0 author `promote` endpoint exists and is reachable.
  4. Happy-path requests to every stub route return 200/201/202 or 501 — NEVER
     404 (route missing) or 500 (handler crash).

The app is built without a live DB: /health and all stub routes are pure shape,
so the lifespan DB calls are stubbed (mirrors tests/test_health.py).
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

# A fixed UUID for any {…_id} path param so requests reach the handler.
_UUID = "00000000-0000-0000-0000-000000000001"
_ALLOWED_STATUS = {200, 201, 202, 501}


def _load_spec() -> dict:
    with SPEC_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture()
def client(monkeypatch):
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
    with TestClient(main_mod.app) as c:
        yield c


def _spec_to_concrete(spec_path: str) -> str:
    """Turn an OpenAPI templated path into a concrete request URL."""
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
    assert "/v1/lore-enrichment/proposals/{proposal_id}/promote" in spec["paths"], (
        "H0 promote endpoint missing from the spec"
    )


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
    """H0: the author promote endpoint exists and is reachable (200/501)."""
    resp = client.post(
        f"/v1/lore-enrichment/proposals/{_UUID}/promote",
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code in _ALLOWED_STATUS, resp.status_code
    # As a not-yet-built canonization action it must be 501, not a fake 200.
    assert resp.status_code == 501


def test_all_stub_routes_return_200_or_501(client):
    """Every spec path+method returns 200/201/202 or 501 — never 404/500."""
    spec = _load_spec()
    failures = []
    for spec_path, methods in spec["paths"].items():
        url = _spec_to_concrete(spec_path)
        # query params required by the spec (project_id on list routes).
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


def test_list_routes_return_spec_valid_empty_shape(client):
    """GET list endpoints return a spec-valid {items, total} body (not {})."""
    list_urls = [
        f"/v1/lore-enrichment/jobs?project_id={_UUID}",
        f"/v1/lore-enrichment/proposals?project_id={_UUID}",
        f"/v1/lore-enrichment/sources?project_id={_UUID}",
        "/v1/lore-enrichment/templates",
    ]
    for url in list_urls:
        resp = client.get(url, headers={"Authorization": "Bearer x"})
        assert resp.status_code == 200, (url, resp.status_code)
        body = resp.json()
        assert body.get("items") == [], (url, body)
        assert body.get("total") == 0, (url, body)


def test_promote_carries_principal_seam():
    """Adversary focus: promote must not be anonymous — its signature carries a
    Principal dependency (the authorization seam), even as a stub."""
    import inspect

    from app.api import proposals as prop_mod

    # `from __future__ import annotations` makes annotations strings, so match by
    # name rather than by type identity.
    sig = inspect.signature(prop_mod.promote_proposal)
    principal_params = [
        p
        for p in sig.parameters.values()
        if "Principal" in str(p.annotation)
    ]
    assert principal_params, "promote handler must carry a Principal dependency"
