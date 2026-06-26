"""T4.1 — unit tests for GET /v1/knowledge/projects/{id}/flywheel.

Pins the router glue: latest-COMPLETED-job selection, the has_delta=False
empty state, the 404 on unknown project, and field/new_items mapping. The
created_job_id counting is exercised in the live-smoke + test_flywheel.py.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.db.neo4j_repos.flywheel import FlywheelDelta, FlywheelItem

_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _job(status: str, *, completed=True):
    return SimpleNamespace(
        job_id=uuid4(),
        status=status,
        completed_at=datetime.now(timezone.utc) if completed else None,
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _client(*, project=object(), jobs=None):
    from app.main import app
    from app.deps import get_extraction_jobs_repo, get_projects_repo
    from app.middleware.jwt_auth import get_current_user

    jobs_repo = AsyncMock()
    jobs_repo.list_for_project = AsyncMock(return_value=jobs or [])
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=project)

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    return TestClient(app, raise_server_exceptions=False)


def test_unknown_project_404():
    client = _client(project=None)
    resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/flywheel")
    assert resp.status_code == 404


def test_no_completed_job_returns_has_delta_false():
    # only a running job → nothing completed yet
    client = _client(jobs=[_job("running", completed=False)])
    resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/flywheel")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["has_delta"] is False
    assert body["entities_added"] == 0 and body["new_items"] == []


@patch("app.routers.public.extraction.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.extraction.get_flywheel_delta", new_callable=AsyncMock)
def test_maps_latest_completed_job_delta(mock_delta):
    mock_delta.return_value = FlywheelDelta(
        entities_added=4,
        relations_added=2,
        events_added=1,
        new_items=[
            FlywheelItem(kind="entity", id="e1", name="Kael"),
            FlywheelItem(kind="event", id="v1", name="The Duel"),
            FlywheelItem(kind="relation", id="r1", name="Kael → ALLY_OF → Mira"),
        ],
    )
    # newest-first list: a newer running job must NOT shadow the completed one.
    completed = _job("complete")
    client = _client(jobs=[_job("running", completed=False), completed])
    resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/flywheel")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["has_delta"] is True
    assert body["job_id"] == str(completed.job_id)
    assert (body["entities_added"], body["relations_added"], body["events_added"]) == (4, 2, 1)
    assert [i["kind"] for i in body["new_items"]] == ["entity", "event", "relation"]
    # the helper was scoped to the COMPLETED job's id + the caller
    assert mock_delta.await_args.kwargs["job_id"] == str(completed.job_id)
    assert mock_delta.await_args.kwargs["user_id"] == str(_TEST_USER)
