"""M0 — skeleton boot + wiring (no live DB needed).

The lifespan's pool/migrate calls are stubbed so TestClient can run the
startup without Postgres; the real /health DB ping is covered by the
`compose up → curl /health` live verify gate. Here we lock that the app
boots and the routers are wired.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    # Stub the lifespan DB wiring so startup doesn't need Postgres.
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_public_ping(client):
    r = client.get("/v1/composition/ping")
    assert r.status_code == 200
    assert r.json() == {"pong": True}


def test_internal_ping_requires_token(client):
    assert client.get("/internal/ping").status_code == 401
    r = client.get("/internal/ping", headers={"X-Internal-Token": "test_token"})
    assert r.status_code == 200
    assert r.json() == {"pong": True}


def test_metrics_exposes_registry(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "composition_service_up" in r.text
