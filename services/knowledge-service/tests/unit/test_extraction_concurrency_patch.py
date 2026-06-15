"""C7 raise-cap (KN-7) — PATCH /extraction/jobs/{job_id}/concurrency.

Owner-scoped in-flight change of a running/paused job's parallel-LLM
concurrency cap. Bounds (1–64) enforced by the request model; terminal
jobs 409; missing jobs 404.

Mounts the real jobs_router on app.main.app (so the conftest grant-gate
shim transparently resolves the caller as owner) and overrides the
extraction-jobs repo with an AsyncMock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.extraction_jobs import ExtractionJob

_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_JOB_ID = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _job_stub(**overrides) -> ExtractionJob:
    defaults = dict(
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER,
        project_id=_TEST_PROJECT,
        scope="all",
        scope_range=None,
        status="running",
        llm_model="test-model",
        embedding_model="bge-m3",
        max_spend_usd=Decimal("10.00"),
        items_total=100,
        items_processed=42,
        current_cursor=None,
        cost_spent_usd=Decimal("1.50"),
        started_at=datetime(2026, 4, 18, 10, 0, 0, tzinfo=timezone.utc),
        paused_at=None,
        completed_at=None,
        created_at=datetime(2026, 4, 18, 9, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 18, 10, 5, 0, tzinfo=timezone.utc),
        error_message=None,
        concurrency_level=4,
    )
    defaults.update(overrides)
    return ExtractionJob(**defaults)


def _setup(*, set_return=None, get_return=None) -> tuple[TestClient, AsyncMock]:
    from app.main import app
    from app.deps import get_extraction_jobs_repo
    from app.middleware.jwt_auth import get_current_user

    jobs_repo = AsyncMock()
    jobs_repo.set_concurrency_level = AsyncMock(return_value=set_return)
    jobs_repo.get = AsyncMock(return_value=get_return)

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    return TestClient(app, raise_server_exceptions=False), jobs_repo


_URL = f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}/concurrency"


def test_patch_concurrency_updates_running_job():
    updated = _job_stub(concurrency_level=16)
    client, repo = _setup(set_return=updated)
    resp = client.patch(_URL, json={"concurrency_level": 16})
    assert resp.status_code == 200, resp.text
    assert resp.json()["concurrency_level"] == 16
    # Owner-scoped call to the repo.
    repo.set_concurrency_level.assert_awaited_once_with(_TEST_USER, _TEST_JOB_ID, 16)


def test_patch_concurrency_below_min_rejected_422():
    client, repo = _setup()
    resp = client.patch(_URL, json={"concurrency_level": 0})
    assert resp.status_code == 422
    repo.set_concurrency_level.assert_not_awaited()


def test_patch_concurrency_above_max_rejected_422():
    client, repo = _setup()
    resp = client.patch(_URL, json={"concurrency_level": 65})
    assert resp.status_code == 422
    repo.set_concurrency_level.assert_not_awaited()


def test_patch_concurrency_missing_job_returns_404():
    # 0-row update AND get() returns None → 404.
    client, _repo = _setup(set_return=None, get_return=None)
    resp = client.patch(_URL, json={"concurrency_level": 8})
    assert resp.status_code == 404


def test_patch_concurrency_terminal_job_returns_409():
    # 0-row update because the job is terminal; get() finds it → 409.
    client, _repo = _setup(
        set_return=None, get_return=_job_stub(status="complete"),
    )
    resp = client.patch(_URL, json={"concurrency_level": 8})
    assert resp.status_code == 409
    assert "complete" in resp.json()["detail"]


def test_patch_concurrency_boundaries_accepted():
    """Both ends of the inclusive [1, 64] range pass validation."""
    for level in (1, 64):
        client, repo = _setup(set_return=_job_stub(concurrency_level=level))
        resp = client.patch(_URL, json={"concurrency_level": level})
        assert resp.status_code == 200, (level, resp.text)
        repo.set_concurrency_level.assert_awaited_once_with(
            _TEST_USER, _TEST_JOB_ID, level,
        )
