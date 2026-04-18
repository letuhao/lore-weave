"""K16.15 — Extraction lifecycle integration test.

Chains all extraction endpoints in sequence using FastAPI TestClient
with mocked backends. Verifies the full state machine flow:

  estimate → start → poll → pause → resume → cancel → delete → rebuild

Each step validates the response and the state transitions that
the subsequent step depends on. Individual endpoint logic is
unit-tested elsewhere; this test verifies they compose correctly.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.book_client import BookClient
from app.clients.glossary_client import GlossaryClient
from app.db.repositories.extraction_jobs import ExtractionJob

_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_BOOK = uuid4()
_JOB_ID = uuid4()


def _project_stub(**overrides):
    from app.db.models import Project
    defaults = dict(
        project_id=_TEST_PROJECT, user_id=_TEST_USER, name="Test",
        description="", project_type="translation", book_id=_TEST_BOOK,
        instructions="", extraction_enabled=False, extraction_status="disabled",
        extraction_config={}, estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"), is_archived=False, version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Project(**defaults)


def _job_stub(**overrides) -> ExtractionJob:
    defaults = dict(
        job_id=_JOB_ID, user_id=_TEST_USER, project_id=_TEST_PROJECT,
        scope="all", scope_range=None, status="running",
        llm_model="test-model", embedding_model="bge-m3",
        max_spend_usd=Decimal("10.00"), items_total=45,
        items_processed=10, current_cursor=None,
        cost_spent_usd=Decimal("1.50"),
        started_at=datetime.now(timezone.utc), paused_at=None,
        completed_at=None, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc), error_message=None,
    )
    defaults.update(overrides)
    return ExtractionJob(**defaults)


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


class _MockState:
    """Mutable state shared across the test — tracks the "current" job
    status so endpoints return consistent data as the test progresses.

    For transition endpoints (pause/resume/cancel), set `next_status`
    BEFORE the call. `update_status` returns a job with `next_status`,
    while `list_active` returns the current status for validation.
    """

    def __init__(self):
        self.job_status = "running"
        self.next_status: str | None = None
        self.project_status = "building"
        self.active = True

    def job(self) -> ExtractionJob:
        return _job_stub(status=self.job_status)

    def updated_job(self) -> ExtractionJob:
        return _job_stub(status=self.next_status or self.job_status)

    def project(self):
        return _project_stub(
            extraction_enabled=self.active,
            extraction_status=self.project_status,
        )


def _setup(state: _MockState) -> TestClient:
    """Wire up all DI overrides + pool/neo4j patches for the full lifecycle."""
    from app.main import app
    from app.deps import (
        get_book_client,
        get_extraction_jobs_repo,
        get_extraction_pending_repo,
        get_glossary_client,
        get_projects_repo,
    )
    from app.middleware.jwt_auth import get_current_user

    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(side_effect=lambda *a, **kw: state.project())
    projects_repo.set_extraction_state = AsyncMock(
        side_effect=lambda *a, **kw: state.project(),
    )

    jobs_repo = AsyncMock()
    jobs_repo.list_active = AsyncMock(
        side_effect=lambda *a, **kw: [state.job()] if state.active else [],
    )
    jobs_repo.list_for_project = AsyncMock(
        side_effect=lambda *a, **kw: [state.job()],
    )
    jobs_repo.get = AsyncMock(side_effect=lambda *a, **kw: state.job())
    jobs_repo.update_status = AsyncMock(side_effect=lambda *a, **kw: state.updated_job())

    pending_repo = AsyncMock()
    pending_repo.count_pending = AsyncMock(return_value=100)

    book_client = AsyncMock(spec=BookClient)
    book_client.count_chapters = AsyncMock(return_value=45)

    glossary_client = AsyncMock(spec=GlossaryClient)
    glossary_client.count_entities = AsyncMock(return_value=200)

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    app.dependency_overrides[get_extraction_pending_repo] = lambda: pending_repo
    app.dependency_overrides[get_book_client] = lambda: book_client
    app.dependency_overrides[get_glossary_client] = lambda: glossary_client

    return TestClient(app, raise_server_exceptions=False)


def _mock_pool():
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"job_id": _JOB_ID})
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_transaction():
        yield

    mock_conn.transaction = mock_transaction

    @asynccontextmanager
    async def mock_acquire():
        yield mock_conn

    pool = MagicMock()
    pool.acquire = mock_acquire
    return pool


def _mock_neo4j():
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"deleted": 5})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    return mock_session


# ── The integration test ─────────────────────────────────────────────


def test_full_extraction_lifecycle():
    """Chain: estimate → start → poll → pause → resume → cancel → delete → rebuild."""
    state = _MockState()
    client = _setup(state)

    # ── 1. Estimate ──────────────────────────────────────────────
    state.active = False  # no active job yet
    resp = client.post(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/estimate",
        json={"scope": "all", "llm_model": "test-model"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"]["chapters"] == 45
    assert data["items"]["chat_turns"] == 100
    assert data["items_total"] == 45 + 100 + 200

    # ── 2. Start ─────────────────────────────────────────────────
    with patch("app.routers.public.extraction.get_knowledge_pool",
               return_value=_mock_pool()):
        resp = client.post(
            f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/start",
            json={
                "scope": "all",
                "llm_model": "test-model",
                "embedding_model": "bge-m3",
                "max_spend_usd": "10.00",
            },
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "running"

    # Mark active for subsequent checks
    state.active = True
    state.job_status = "running"
    state.project_status = "building"

    # ── 3. Poll job status ───────────────────────────────────────
    resp = client.get(f"/v1/knowledge/extraction/jobs/{_JOB_ID}")
    assert resp.status_code == 200
    assert "ETag" in resp.headers
    data = resp.json()
    assert data["status"] == "running"

    # ── 4. Pause (running → paused) ─────────────────────────────
    state.next_status = "paused"
    resp = client.post(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/pause",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"
    state.job_status = "paused"
    state.next_status = None

    # ── 5. Resume (paused → running) ─────────────────────────────
    state.next_status = "running"
    resp = client.post(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/resume",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    state.job_status = "running"
    state.next_status = None

    # ── 6. Cancel (running → cancelled) ──────────────────────────
    state.next_status = "cancelled"
    resp = client.post(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/cancel",
    )
    assert resp.status_code == 200, resp.text

    state.active = False
    state.job_status = "cancelled"
    state.project_status = "disabled"
    state.next_status = None

    # ── 7. List job history ──────────────────────────────────────
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/jobs",
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # ── 8. Delete graph ──────────────────────────────────────────
    mock_neo = _mock_neo4j()
    with patch("app.routers.public.extraction.app_settings") as ms:
        ms.neo4j_uri = "bolt://localhost:7687"
        with patch("app.routers.public.extraction.neo4j_session") as mn:
            mn.return_value.__aenter__ = AsyncMock(return_value=mock_neo)
            mn.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = client.delete(
                f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/graph",
            )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["nodes_deleted"] >= 0
    assert data["extraction_status"] == "disabled"

    # ── 9. Rebuild ───────────────────────────────────────────────
    state.active = False
    mock_neo2 = _mock_neo4j()
    with patch("app.routers.public.extraction.app_settings") as ms:
        ms.neo4j_uri = "bolt://localhost:7687"
        with patch("app.routers.public.extraction.neo4j_session") as mn:
            mn.return_value.__aenter__ = AsyncMock(return_value=mock_neo2)
            mn.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.routers.public.extraction.get_knowledge_pool",
                        return_value=_mock_pool()):
                state.job_status = "running"
                resp = client.post(
                    f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/rebuild",
                    json={
                        "llm_model": "test-model",
                        "embedding_model": "bge-m3",
                    },
                )
    assert resp.status_code == 201, resp.text
    assert resp.json()["scope"] == "all"
