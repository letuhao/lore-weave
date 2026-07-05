"""CM4 — unit tests for the per-project orders-backfill internal endpoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
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


def test_backfill_passages_ingests_published_chapters(monkeypatch):
    """D-KG-PASSAGES-NOT-INGESTED — ingests each published chapter's passages; a
    published row missing its pinned revision is skipped, not counted or failed."""
    user_id, book_id = uuid4(), uuid4()
    monkeypatch.setattr(
        "app.routers.internal_backfill.get_knowledge_pool",
        lambda: _fake_pool({"user_id": user_id, "book_id": book_id,
                            "embedding_model": "bge-m3", "embedding_dimension": 1024}),
    )
    ms = MagicMock()
    ms.neo4j_uri = "bolt://fake"
    monkeypatch.setattr("app.routers.internal_backfill.settings", ms)

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    monkeypatch.setattr("app.routers.internal_backfill.neo4j_session", fake_session)

    bc = MagicMock()
    bc.list_chapters = AsyncMock(return_value=[
        {"chapter_id": str(uuid4()), "published_revision_id": str(uuid4()), "sort_order": 1},
        {"chapter_id": str(uuid4()), "published_revision_id": str(uuid4()), "sort_order": 2},
        {"chapter_id": str(uuid4()), "published_revision_id": None, "sort_order": 3},  # skip
    ])
    monkeypatch.setattr("app.routers.internal_backfill.get_book_client", lambda: bc)
    monkeypatch.setattr(
        "app.clients.embedding_client.get_embedding_client", lambda: MagicMock(),
    )
    ing = AsyncMock(return_value=SimpleNamespace(chunks_created=10))
    monkeypatch.setattr(
        "app.extraction.passage_ingester.ingest_chapter_passages", ing,
    )

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/internal/projects/{uuid4()}/backfill-passages",
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["chapters_ingested"] == 2  # the null-revision row is skipped
    assert body["passages_created"] == 20
    assert body["chapters_failed"] == 0
    assert ing.await_count == 2


def test_backfill_passages_skips_when_no_embedding_config(monkeypatch):
    monkeypatch.setattr(
        "app.routers.internal_backfill.get_knowledge_pool",
        lambda: _fake_pool({"user_id": uuid4(), "book_id": uuid4(),
                            "embedding_model": None, "embedding_dimension": None}),
    )
    ms = MagicMock()
    ms.neo4j_uri = "bolt://fake"
    monkeypatch.setattr("app.routers.internal_backfill.settings", ms)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/internal/projects/{uuid4()}/backfill-passages",
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    assert resp.json()["skipped"] == "no_embedding_config"


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
