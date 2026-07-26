"""K19b.8 — Unit tests for the job-logs public endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.extraction_jobs import ExtractionJob
from app.db.repositories.job_logs import JobLog


_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_JOB_ID = uuid4()
_NO_JOB = object()  # sentinel for "jobs_repo.get returns None" (cross-user / missing)


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _job_stub() -> ExtractionJob:
    return ExtractionJob(
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER,
        project_id=_TEST_PROJECT,
        scope="chapters",
        scope_range=None,
        status="running",
        llm_model="m",
        embedding_model="e",
        max_spend_usd=Decimal("5"),
        items_total=10,
        items_processed=0,
        current_cursor=None,
        cost_spent_usd=Decimal("0"),
        started_at=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
        paused_at=None,
        completed_at=None,
        created_at=datetime(2026, 4, 22, 11, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
        error_message=None,
    )


def _log_stub(log_id: int, message: str = "x") -> JobLog:
    return JobLog(
        log_id=log_id,
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER,
        level="info",
        message=message,
        context={},
        created_at=datetime(2026, 4, 22, 12, 1, tzinfo=timezone.utc),
    )


def _make_client(*, job=None, logs=None):
    from app.main import app
    from app.deps import get_extraction_jobs_repo, get_job_logs_repo
    from app.middleware.jwt_auth import get_current_user

    if job is _NO_JOB:
        job_return = None
    else:
        job_return = job if job is not None else _job_stub()
    jobs_repo = AsyncMock()
    jobs_repo.get = AsyncMock(return_value=job_return)

    logs_repo = AsyncMock()
    logs_repo.list = AsyncMock(return_value=logs or [])

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    app.dependency_overrides[get_job_logs_repo] = lambda: logs_repo

    return TestClient(app, raise_server_exceptions=False), logs_repo


def test_list_logs_returns_page_with_null_cursor_when_not_full():
    logs = [_log_stub(1, "a"), _log_stub(2, "b")]
    client, _repo = _make_client(logs=logs)
    resp = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/logs?limit=50",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["logs"]) == 2
    assert body["logs"][0]["message"] == "a"
    assert body["next_cursor"] is None  # page not full


def test_list_logs_sets_next_cursor_when_page_is_full():
    # limit=3, returns 3 rows → cursor = max log_id.
    logs = [_log_stub(10), _log_stub(11), _log_stub(12)]
    client, _repo = _make_client(logs=logs)
    resp = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/logs?limit=3",
    )
    assert resp.status_code == 200
    assert resp.json()["next_cursor"] == 12


def test_list_logs_forwards_since_log_id_and_limit():
    client, repo = _make_client(logs=[])
    resp = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/logs"
        "?since_log_id=42&limit=25",
    )
    assert resp.status_code == 200
    repo.list.assert_awaited_once_with(
        _TEST_USER, _TEST_JOB_ID, since_log_id=42, limit=25,
    )


def test_list_logs_job_not_found_returns_404():
    client, _repo = _make_client(job=_NO_JOB)
    resp = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/logs",
    )
    assert resp.status_code == 404


def test_list_logs_invalid_limit_rejected():
    client, _repo = _make_client()
    # le=200 on Query validator
    resp_big = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/logs?limit=500",
    )
    assert resp_big.status_code == 422
    # ge=1
    resp_zero = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/logs?limit=0",
    )
    assert resp_zero.status_code == 422


def test_list_logs_negative_cursor_rejected():
    client, _repo = _make_client()
    resp = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/logs?since_log_id=-1",
    )
    assert resp.status_code == 422


# ── Studio Quality tab (`quality-canon`) / D-KG-CANON-FLAG-REVIEW-UI ──

def _flag_stub(log_id: int, name: str) -> JobLog:
    return JobLog(
        log_id=log_id, job_id=_TEST_JOB_ID, user_id=_TEST_USER, level="warning",
        message=f"Canon check: '{name}' referenced as active despite being marked gone",
        context={"event": "pass2_canon_flag", "name": name, "entity_id": "e1"},
        created_at=datetime(2026, 4, 22, 12, 1, tzinfo=timezone.utc),
    )


def _make_canon_flags_client(*, project=None, flags=None):
    from app.main import app
    from app.deps import get_job_logs_repo, get_projects_repo
    from app.middleware.jwt_auth import get_current_user

    project_return = None if project is _NO_JOB else (project or object())
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=project_return)

    logs_repo = AsyncMock()
    logs_repo.list_canon_flags_for_project = AsyncMock(return_value=flags or [])

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_job_logs_repo] = lambda: logs_repo

    return TestClient(app, raise_server_exceptions=False), logs_repo


def test_canon_flags_returns_flags():
    flags = [_flag_stub(1, "Old Man Wu"), _flag_stub(2, "Su Han")]
    client, _repo = _make_canon_flags_client(flags=flags)
    resp = client.get(f"/v1/knowledge/extraction/projects/{_TEST_PROJECT}/canon-flags")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["flags"]) == 2
    assert body["flags"][0]["context"]["name"] == "Old Man Wu"


def test_canon_flags_project_not_found_returns_404():
    client, _repo = _make_canon_flags_client(project=_NO_JOB)
    resp = client.get(f"/v1/knowledge/extraction/projects/{_TEST_PROJECT}/canon-flags")
    assert resp.status_code == 404


def test_canon_flags_forwards_limit():
    client, repo = _make_canon_flags_client(flags=[])
    resp = client.get(f"/v1/knowledge/extraction/projects/{_TEST_PROJECT}/canon-flags?limit=25")
    assert resp.status_code == 200
    repo.list_canon_flags_for_project.assert_awaited_once_with(_TEST_USER, _TEST_PROJECT, limit=25)


def test_canon_flags_invalid_limit_rejected():
    client, _repo = _make_canon_flags_client()
    assert client.get(
        f"/v1/knowledge/extraction/projects/{_TEST_PROJECT}/canon-flags?limit=500",
    ).status_code == 422
    assert client.get(
        f"/v1/knowledge/extraction/projects/{_TEST_PROJECT}/canon-flags?limit=0",
    ).status_code == 422
