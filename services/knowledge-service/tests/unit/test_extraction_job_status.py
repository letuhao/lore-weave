"""K16.5 — Unit tests for job status + project job list endpoints."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock
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
        project_id=_TEST_PROJECT,
        user_id=_TEST_USER,
        name="Test",
        description="",
        project_type="translation",
        book_id=_TEST_BOOK,
        instructions="",
        extraction_enabled=True,
        extraction_status="building",
        extraction_config={},
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


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
    )
    defaults.update(overrides)
    return ExtractionJob(**defaults)


def _stub_book_client(chapter_titles: dict | None = None):
    """C6 /review-impl L3 — BookClient override for router tests. By
    default returns {} (matches "book-service unreachable" degrade
    path the enricher handles cleanly). Tests that exercise the
    happy-path enrichment pass a dict mapping UUID → title."""
    stub = AsyncMock()
    stub.get_chapter_titles = AsyncMock(return_value=chapter_titles or {})
    return stub


def _setup_overrides(*, job=None, jobs_list=None, project=None, book_client=None):
    from app.main import app
    from app.deps import get_book_client, get_extraction_jobs_repo, get_projects_repo
    from app.middleware.jwt_auth import get_current_user

    jobs_repo = AsyncMock()
    jobs_repo.get = AsyncMock(return_value=job)
    jobs_repo.list_for_project = AsyncMock(return_value=jobs_list or [])

    if project is _NO_PROJECT:
        proj_return = None
    else:
        proj_return = project if project is not None else _project_stub()
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=proj_return)

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    # /review-impl L3 — default override so the enricher short-circuits
    # instead of attempting a real HTTP call to book-service during
    # unit tests. Happy-path enrichment tests pass a real stub.
    app.dependency_overrides[get_book_client] = (
        lambda: book_client if book_client is not None else _stub_book_client()
    )

    return TestClient(app, raise_server_exceptions=False)


def _setup_list_all_overrides(*, all_jobs=None, book_client=None):
    """K19b.1 helper — wires list_all_for_user and returns both the
    client and the mock so the test can inspect call kwargs."""
    from app.main import app
    from app.deps import get_book_client, get_extraction_jobs_repo
    from app.middleware.jwt_auth import get_current_user

    jobs_repo = AsyncMock()
    jobs_repo.list_all_for_user = AsyncMock(return_value=all_jobs or [])

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    # /review-impl L3 — same book_client override discipline.
    app.dependency_overrides[get_book_client] = (
        lambda: book_client if book_client is not None else _stub_book_client()
    )

    return TestClient(app, raise_server_exceptions=False), jobs_repo


# ── GET /v1/knowledge/extraction/jobs/{job_id} ──────────────────────


def test_get_job_returns_200_with_etag():
    job = _job_stub()
    client = _setup_overrides(job=job)
    resp = client.get(f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == str(_TEST_JOB_ID)
    assert data["items_processed"] == 42
    assert "ETag" in resp.headers
    assert resp.headers["ETag"].startswith('W/"')


def test_get_job_not_found_returns_404():
    client = _setup_overrides(job=None)
    resp = client.get(f"/v1/knowledge/extraction/jobs/{uuid4()}")
    assert resp.status_code == 404


def test_get_job_304_when_etag_matches():
    job = _job_stub()
    client = _setup_overrides(job=job)
    # First request to get the ETag
    resp1 = client.get(f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}")
    etag = resp1.headers["ETag"]
    # Second request with If-None-Match
    resp2 = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}",
        headers={"If-None-Match": etag},
    )
    assert resp2.status_code == 304


def test_get_job_200_when_etag_stale():
    job = _job_stub()
    client = _setup_overrides(job=job)
    resp = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}",
        headers={"If-None-Match": 'W/"0"'},
    )
    assert resp.status_code == 200


# ── GET /v1/knowledge/projects/{id}/extraction/jobs ─────────────────


def test_list_jobs_returns_200():
    jobs = [_job_stub(status="complete"), _job_stub(status="running")]
    client = _setup_overrides(jobs_list=jobs)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/jobs",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_jobs_empty_project_returns_empty():
    client = _setup_overrides(jobs_list=[])
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/jobs",
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_jobs_project_not_found_returns_404():
    client = _setup_overrides(project=_NO_PROJECT)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/jobs",
    )
    assert resp.status_code == 404


# ── K19b.1: GET /v1/knowledge/extraction/jobs ─────────────────────────


def test_list_all_jobs_active_returns_200():
    jobs = [_job_stub(status="running"), _job_stub(status="pending")]
    client, repo = _setup_list_all_overrides(all_jobs=jobs)
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=active")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    repo.list_all_for_user.assert_awaited_once_with(
        _TEST_USER, status_group="active", limit=50
    )


def test_list_all_jobs_history_returns_200_with_custom_limit():
    jobs = [_job_stub(status="complete")]
    client, repo = _setup_list_all_overrides(all_jobs=jobs)
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=history&limit=25")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    repo.list_all_for_user.assert_awaited_once_with(
        _TEST_USER, status_group="history", limit=25
    )


def test_list_all_jobs_missing_status_group_returns_422():
    client, _repo = _setup_list_all_overrides()
    resp = client.get("/v1/knowledge/extraction/jobs")
    assert resp.status_code == 422


def test_list_all_jobs_invalid_status_group_returns_422():
    client, _repo = _setup_list_all_overrides()
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=bogus")
    assert resp.status_code == 422


def test_list_all_jobs_limit_out_of_range_returns_422():
    client, _repo = _setup_list_all_overrides()
    # le=200 on the Query validator
    resp_too_big = client.get(
        "/v1/knowledge/extraction/jobs?status_group=active&limit=500"
    )
    assert resp_too_big.status_code == 422
    # ge=1 on the Query validator
    resp_too_small = client.get(
        "/v1/knowledge/extraction/jobs?status_group=active&limit=0"
    )
    assert resp_too_small.status_code == 422


def test_list_all_jobs_empty_returns_empty_array():
    client, _repo = _setup_list_all_overrides(all_jobs=[])
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=history")
    assert resp.status_code == 200
    assert resp.json() == []


# ── C6 /review-impl L3 — router-level enricher integration ────────


def test_get_job_response_contains_enriched_current_chapter_title():
    """Lock the cross-service contract end-to-end: job with
    chapter-scope cursor → router calls enricher → enricher calls
    BookClient → response payload has ``current_chapter_title``
    populated. A regression dropping the enricher call in the
    router would leave the field null despite the mock providing
    a title."""
    chapter_uuid = uuid4()
    job = _job_stub(
        current_cursor={"scope": "chapters", "last_chapter_id": str(chapter_uuid)},
    )
    book_client = _stub_book_client(
        chapter_titles={chapter_uuid: "Chapter 12 — The Bridge Duel"},
    )
    client = _setup_overrides(job=job, book_client=book_client)
    resp = client.get(f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_chapter_title"] == "Chapter 12 — The Bridge Duel"
    # Enricher was called exactly once with the job's chapter_id.
    book_client.get_chapter_titles.assert_awaited_once()
    call_ids = book_client.get_chapter_titles.await_args.args[0]
    assert call_ids == [chapter_uuid]


def test_list_all_jobs_response_has_enriched_current_chapter_title():
    """Same contract lock for the cross-project list endpoint.
    Multiple jobs → enricher batches chapter_ids → each job's
    payload carries its resolved title. A regression dropping the
    enricher would leave current_chapter_title=null silently."""
    cid_a = uuid4()
    cid_b = uuid4()
    jobs = [
        _job_stub(
            job_id=uuid4(),
            current_cursor={"last_chapter_id": str(cid_a)},
        ),
        _job_stub(
            job_id=uuid4(),
            current_cursor={"last_chapter_id": str(cid_b)},
        ),
    ]
    book_client = _stub_book_client(
        chapter_titles={
            cid_a: "Chapter 1 — Opening",
            cid_b: "Chapter 5 — Rising Action",
        },
    )
    client, _repo = _setup_list_all_overrides(
        all_jobs=jobs, book_client=book_client,
    )
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=active")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["current_chapter_title"] == "Chapter 1 — Opening"
    assert body[1]["current_chapter_title"] == "Chapter 5 — Rising Action"


def test_etag_includes_current_chapter_title_so_title_change_bumps():
    """/review-impl M1 fix lock — two jobs with identical
    ``updated_at`` but different ``current_chapter_title`` must
    produce DIFFERENT etags. Before the fix, etag was derived from
    updated_at alone and a chapter rename on book-side would serve
    304 with stale title until staleTime expired."""
    chapter_uuid = uuid4()
    job_a = _job_stub(
        current_cursor={"last_chapter_id": str(chapter_uuid)},
    )
    job_b = _job_stub(
        current_cursor={"last_chapter_id": str(chapter_uuid)},
    )

    client_a = _setup_overrides(
        job=job_a,
        book_client=_stub_book_client(
            chapter_titles={chapter_uuid: "Chapter 12 — The Bridge Duel"},
        ),
    )
    resp_a = client_a.get(f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}")
    etag_a = resp_a.headers["ETag"]

    client_b = _setup_overrides(
        job=job_b,
        book_client=_stub_book_client(
            chapter_titles={chapter_uuid: "Chapter 12 — The Renamed Duel"},
        ),
    )
    resp_b = client_b.get(f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}")
    etag_b = resp_b.headers["ETag"]

    # Same updated_at + different title → different etag. If this
    # fails, FE would cache stale title forever.
    assert etag_a != etag_b
    # Both are still W/"..." weak etags.
    assert etag_a.startswith('W/"')
    assert etag_b.startswith('W/"')
