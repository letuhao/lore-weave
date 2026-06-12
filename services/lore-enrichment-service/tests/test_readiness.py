"""Readiness probe tests (RAID C18 — clears DEFERRED-042).

The C18 brief + adversary focus demand: prove ``/ready`` returns **503** when the
DB is down by INJECTING A FAILING POOL (not merely mocking the route), confirm it
returns 200 when ``SELECT 1`` succeeds, and confirm ``/health`` stays a constant-ok
liveness probe that does NOT touch the DB (so a DB blip never crash-loops the pod).
"""

from __future__ import annotations

import app.api.observability as obs_mod
import app.db.pool as pool_mod
import app.main as main_mod
from fastapi.testclient import TestClient


class _OkPool:
    """A pool whose SELECT 1 returns 1 (DB reachable)."""

    async def fetchval(self, query):
        assert query == "SELECT 1"
        return 1


class _FailingPool:
    """A pool whose round-trip RAISES — simulates a DB that dropped after startup.

    This is the injected FAILING POOL the brief requires: /ready must hit a real
    pool method that fails (not a route-level mock), so the 503 path proves the
    SELECT 1 is actually attempted against the pool.
    """

    async def fetchval(self, query):
        raise ConnectionError("connection refused: postgres unreachable")


class _WrongResultPool:
    """A pool whose SELECT 1 returns something other than 1 (corrupt/degraded)."""

    async def fetchval(self, query):
        return 0


def _client(monkeypatch) -> TestClient:
    """Build a TestClient with a stubbed lifespan (no real DB dial at startup)."""

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
    return TestClient(main_mod.app)


def test_health_is_constant_ok_liveness(monkeypatch):
    """/health stays constant-ok liveness — no DB dependency, never 503."""
    with _client(monkeypatch) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_health_ok_even_when_db_down(monkeypatch):
    """A failing pool must NOT affect /health (liveness != readiness)."""
    # Point the observability module's get_pool at a failing pool; /health must
    # still be 200 because it does not call get_pool at all.
    monkeypatch.setattr(obs_mod, "get_pool", lambda: _FailingPool())
    with _client(monkeypatch) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_ready_200_when_db_up(monkeypatch):
    """/ready returns 200 when SELECT 1 succeeds against the pool."""
    monkeypatch.setattr(obs_mod, "get_pool", lambda: _OkPool())
    with _client(monkeypatch) as client:
        resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_ready_503_when_db_down_injected_failing_pool(monkeypatch):
    """/ready returns 503 (not 200, not 500) when the pool round-trip FAILS.

    The failing pool is injected at the get_pool seam — the route really calls
    pool.fetchval, which raises, proving SELECT 1 is attempted against the DB.
    """
    monkeypatch.setattr(obs_mod, "get_pool", lambda: _FailingPool())
    with _client(monkeypatch) as client:
        resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_ready_503_when_pool_uninitialised(monkeypatch):
    """/ready returns 503 when the pool is not initialised (get_pool raises)."""

    def _raise():
        raise RuntimeError("DB pool not initialised")

    monkeypatch.setattr(obs_mod, "get_pool", _raise)
    with _client(monkeypatch) as client:
        resp = client.get("/ready")
    assert resp.status_code == 503


def test_ready_503_when_select1_returns_unexpected(monkeypatch):
    """/ready returns 503 if SELECT 1 returns something other than 1."""
    monkeypatch.setattr(obs_mod, "get_pool", lambda: _WrongResultPool())
    with _client(monkeypatch) as client:
        resp = client.get("/ready")
    assert resp.status_code == 503
