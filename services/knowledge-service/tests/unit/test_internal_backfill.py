"""CM4 — unit tests for the per-project orders-backfill internal endpoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.migrations.backfill_orders import OrdersBackfillResult
from app.main import app

_INTERNAL_TOKEN_HEADER = {"X-Internal-Token": "default_test_token"}


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _fake_pool(row):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=row)
    return pool


def test_backfill_orders_404_when_project_missing(monkeypatch):
    monkeypatch.setattr(
        "app.routers.internal_backfill.get_knowledge_pool",
        lambda: _fake_pool(None),
    )
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/internal/projects/{uuid4()}/backfill-orders",
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 404


def test_backfill_orders_runs_and_returns_stats(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        "app.routers.internal_backfill.get_knowledge_pool",
        lambda: _fake_pool({"user_id": user_id}),
    )

    ms = MagicMock()
    ms.neo4j_uri = "bolt://fake"
    monkeypatch.setattr("app.routers.internal_backfill.settings", ms)

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    monkeypatch.setattr(
        "app.routers.internal_backfill.neo4j_session", fake_session,
    )
    monkeypatch.setattr(
        "app.routers.internal_backfill.get_book_client", lambda: MagicMock(),
    )

    result = OrdersBackfillResult()
    result.events_ordered = 12
    result.events_skipped_no_sort = 1
    result.passages_indexed = 30
    result.chrono_ranked = 8
    run_mock = AsyncMock(return_value=result)
    monkeypatch.setattr(
        "app.routers.internal_backfill.run_orders_backfill", run_mock,
    )

    client = TestClient(app, raise_server_exceptions=False)
    project_id = uuid4()
    resp = client.post(
        f"/internal/projects/{project_id}/backfill-orders",
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["events_ordered"] == 12
    assert body["events_skipped_no_sort"] == 1
    assert body["passages_indexed"] == 30
    assert body["chrono_ranked"] == 8
    # the backfill ran for the project's resolved owner.
    run_mock.assert_awaited_once()
    assert run_mock.await_args.kwargs["user_id"] == str(user_id)
    assert run_mock.await_args.kwargs["project_id"] == str(project_id)


def test_backfill_orders_track1_noop_when_no_neo4j(monkeypatch):
    monkeypatch.setattr(
        "app.routers.internal_backfill.get_knowledge_pool",
        lambda: _fake_pool({"user_id": uuid4()}),
    )
    ms = MagicMock()
    ms.neo4j_uri = ""  # Track 1 — no graph
    monkeypatch.setattr("app.routers.internal_backfill.settings", ms)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/internal/projects/{uuid4()}/backfill-orders",
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    assert resp.json()["skipped"] == "neo4j_unavailable"
