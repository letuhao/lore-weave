"""K16.9 — Unit tests for rebuild endpoint (delete + start)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.extraction_jobs import ExtractionJob

_NO_PROJECT = object()
_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_BOOK = uuid4()
_TEST_JOB_ID = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _project_stub():
    from app.db.models import Project
    return Project(
        project_id=_TEST_PROJECT, user_id=_TEST_USER, name="Test",
        description="", project_type="translation", book_id=_TEST_BOOK,
        instructions="", extraction_enabled=True, extraction_status="ready",
        extraction_config={}, estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"), is_archived=False, version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _job_stub(**overrides) -> ExtractionJob:
    defaults = dict(
        job_id=_TEST_JOB_ID, user_id=_TEST_USER, project_id=_TEST_PROJECT,
        scope="all", scope_range=None, status="running",
        llm_model="test-model", embedding_model="bge-m3",
        max_spend_usd=Decimal("10.00"), items_total=100,
        items_processed=0, current_cursor=None,
        cost_spent_usd=Decimal("0"),
        started_at=datetime.now(timezone.utc), paused_at=None,
        completed_at=None, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc), error_message=None,
    )
    defaults.update(overrides)
    return ExtractionJob(**defaults)


def _make_client(*, project=None, active_jobs=None):
    from app.main import app
    from app.deps import (
        get_book_client,
        get_extraction_jobs_repo,
        get_extraction_pending_repo,
        get_glossary_client,
        get_projects_repo,
    )
    from app.middleware.jwt_auth import get_current_user

    if project is _NO_PROJECT:
        repo_return = None
    else:
        repo_return = project if project is not None else _project_stub()

    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=repo_return)
    projects_repo.set_extraction_state = AsyncMock(return_value=repo_return)

    jobs_repo = AsyncMock()
    jobs_repo.list_active = AsyncMock(return_value=active_jobs or [])
    jobs_repo.get = AsyncMock(return_value=_job_stub())

    # Mock pool for the transaction block
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"job_id": _TEST_JOB_ID})
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_transaction():
        yield

    mock_conn.transaction = mock_transaction

    @asynccontextmanager
    async def mock_acquire():
        yield mock_conn

    mock_pool = MagicMock()
    mock_pool.acquire = mock_acquire

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    # The rebuild endpoint also depends on these for the server-side items_total
    # count (#9); override them so DI doesn't reach the (uninitialised) real pool.
    # The count itself is best-effort (swallowed → NULL) so AsyncMocks suffice.
    app.dependency_overrides[get_extraction_pending_repo] = lambda: AsyncMock()
    app.dependency_overrides[get_book_client] = lambda: AsyncMock()
    app.dependency_overrides[get_glossary_client] = lambda: AsyncMock()

    client = TestClient(app, raise_server_exceptions=False)
    client._pool_patch = patch(
        "app.routers.public.extraction.get_knowledge_pool",
        return_value=mock_pool,
    )
    client._pool_patch.start()
    return client, projects_repo


def _stop(client):
    if hasattr(client, "_pool_patch"):
        client._pool_patch.stop()
        del client._pool_patch


def _url():
    return f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/rebuild"


def _body(**overrides):
    return {"llm_model": "test-model", "embedding_model": "bge-m3", **overrides}


# ── Tests ────────────────────────────────────────────────────────────


@patch("app.routers.public.extraction.neo4j_session")
@patch("app.routers.public.extraction.app_settings")
def test_rebuild_success(mock_settings, mock_neo4j):
    mock_settings.neo4j_uri = "bolt://localhost:7687"

    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client, repo = _make_client()
    resp = client.post(_url() + "?confirm=true", json=_body())
    _stop(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["scope"] == "all"
    assert data["status"] == "running"

    # Neo4j delete should have been called for each label
    assert mock_session.run.call_count == 4  # 4 labels


@patch("app.routers.public.extraction.neo4j_session")
@patch("app.routers.public.extraction.app_settings")
def test_rebuild_without_confirm_returns_warning_and_deletes_nothing(mock_settings, mock_neo4j):
    """bug #14 — a rebuild without ?confirm=true must NOT delete; it returns a
    destructive-warning preview carrying the live node counts."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"

    mock_record = {"entity_count": 12000, "fact_count": 50, "event_count": 30, "passage_count": 0}
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=mock_record)
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client, _ = _make_client()
    resp = client.post(_url(), json=_body())  # no confirm
    _stop(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["action_required"] == "confirm"
    assert data["entity_count"] == 12000
    assert "scope" not in data  # not a job — nothing was started
    # Only the stats COUNT query ran — the 4-label destructive delete did NOT.
    assert mock_session.run.call_count == 1


def test_rebuild_project_not_found():
    client, _ = _make_client(project=_NO_PROJECT)
    resp = client.post(_url(), json=_body())
    _stop(client)
    assert resp.status_code == 404


def test_rebuild_active_job_returns_409():
    active = _job_stub(status="running")
    client, _ = _make_client(active_jobs=[active])
    resp = client.post(_url(), json=_body())
    _stop(client)
    assert resp.status_code == 409


@patch("app.routers.public.extraction.app_settings")
def test_rebuild_neo4j_not_configured_returns_503(mock_settings):
    mock_settings.neo4j_uri = ""
    client, _ = _make_client()
    resp = client.post(_url(), json=_body())
    _stop(client)
    assert resp.status_code == 503


def test_rebuild_empty_model_rejected():
    client, _ = _make_client()
    resp = client.post(_url(), json=_body(llm_model=""))
    _stop(client)
    assert resp.status_code == 422


# ── bug #42 — incremental "update" mode (accumulate, no wipe) ─────────


@patch("app.routers.public.extraction.neo4j_session")
@patch("app.routers.public.extraction.app_settings")
def test_rebuild_update_mode_is_nondestructive_and_needs_no_confirm(mock_settings, mock_neo4j):
    """bug #42 — mode=update starts a job WITHOUT a confirm and WITHOUT touching
    Neo4j: no destructive-stats query, no delete. It re-extracts on top of the
    existing graph via the idempotent MERGE writes."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client, _ = _make_client()
    resp = client.post(_url(), json=_body(mode="update"))  # NO ?confirm
    _stop(client)
    assert resp.status_code == 201
    assert resp.json()["status"] == "running"  # a job actually started
    # The destructive path never ran: no stats COUNT and no 4-label delete.
    assert mock_session.run.call_count == 0


@patch("app.routers.public.extraction._count_scope_items", new_callable=AsyncMock)
@patch("app.routers.public.extraction.app_settings")
def test_rebuild_update_mode_passes_scope_and_range(mock_settings, mock_count):
    """bug #42 — mode=update forwards the caller's scope/scope_range to the job
    (the per-chapter incremental case), instead of the replace path's scope=all."""
    from types import SimpleNamespace
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_count.return_value = SimpleNamespace(total=3)

    client, _ = _make_client()
    resp = client.post(
        _url(),
        json=_body(mode="update", scope="chapters", scope_range={"chapter_range": [1, 3]}),
    )
    _stop(client)
    assert resp.status_code == 201
    # the scope/range flowed into the items_total count (and thus the job create)
    args = mock_count.await_args.args
    assert args[0] == "chapters"
    assert args[1] == {"chapter_range": [1, 3]}


@patch("app.routers.public.extraction.app_settings")
def test_rebuild_update_mode_rejects_reversed_chapter_range(mock_settings):
    """bug #42 — an update validates the range shape up front (mirrors StartJob),
    so a reversed [from>to] range 422s rather than creating a no-op job."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    client, _ = _make_client()
    resp = client.post(
        _url(),
        json=_body(mode="update", scope="chapters", scope_range={"chapter_range": [3, 1]}),
    )
    _stop(client)
    assert resp.status_code == 422


def test_rebuild_invalid_mode_rejected():
    """An unknown mode is a 422 (Literal validation), never silently treated as replace."""
    client, _ = _make_client()
    resp = client.post(_url() + "?confirm=true", json=_body(mode="merge"))
    _stop(client)
    assert resp.status_code == 422
