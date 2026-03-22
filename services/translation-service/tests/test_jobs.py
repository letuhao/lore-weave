"""Integration tests for job endpoints using mocked DB pool + mocked HTTP."""
import datetime
import json
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest

from tests.conftest import FakeRecord

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
BOOK_ID = str(uuid4())
JOB_ID = str(uuid4())
CHAPTER_ID = str(uuid4())
MODEL_REF = str(uuid4())
_NOW = datetime.datetime.utcnow()

_BOOK_SETTINGS_ROW = FakeRecord({
    "book_id": UUID(BOOK_ID),
    "owner_user_id": UUID(USER_ID),
    "target_language": "vi",
    "model_source": "platform_model",
    "model_ref": UUID(MODEL_REF),
    "system_prompt": "Translate.",
    "user_prompt_tpl": "{chapter_text}",
    "updated_at": _NOW,
})

_JOB_ROW = FakeRecord({
    "job_id": UUID(JOB_ID),
    "book_id": UUID(BOOK_ID),
    "owner_user_id": UUID(USER_ID),
    "status": "pending",
    "target_language": "vi",
    "model_source": "platform_model",
    "model_ref": UUID(MODEL_REF),
    "system_prompt": "Translate.",
    "user_prompt_tpl": "{chapter_text}",
    "chapter_ids": [UUID(CHAPTER_ID)],
    "total_chapters": 1,
    "completed_chapters": 0,
    "failed_chapters": 0,
    "error_message": None,
    "started_at": None,
    "finished_at": None,
    "created_at": _NOW,
})

_CHAPTER_ROW = FakeRecord({
    "id": uuid4(),
    "job_id": UUID(JOB_ID),
    "chapter_id": UUID(CHAPTER_ID),
    "book_id": UUID(BOOK_ID),
    "owner_user_id": UUID(USER_ID),
    "status": "completed",
    "translated_body": "Phần mở đầu...",
    "source_language": "en",
    "target_language": "vi",
    "input_tokens": 120,
    "output_tokens": 98,
    "usage_log_id": None,
    "error_message": None,
    "started_at": _NOW,
    "finished_at": _NOW,
    "created_at": _NOW,
})


def _mock_book_service_response(owner_user_id: str = USER_ID, status_code: int = 200):
    """Returns an httpx.Response mock for book-service /internal/books/.../projection."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = (status_code < 400)
    resp.json.return_value = {"owner_user_id": owner_user_id, "lifecycle_state": "active"}
    return resp


# ── POST /v1/translation/books/{book_id}/jobs ─────────────────────────────────

def test_create_job_rejects_empty_chapter_ids(client, fake_pool):
    resp = client.post(f"/v1/translation/books/{BOOK_ID}/jobs", json={"chapter_ids": []})
    assert resp.status_code == 422


def test_create_job_rejects_missing_chapter_ids(client, fake_pool):
    resp = client.post(f"/v1/translation/books/{BOOK_ID}/jobs", json={})
    assert resp.status_code == 422


def test_create_job_returns_403_when_not_book_owner(client, fake_pool):
    with patch("app.routers.jobs.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get.return_value = _mock_book_service_response(owner_user_id=OTHER_USER_ID)

        resp = client.post(
            f"/v1/translation/books/{BOOK_ID}/jobs",
            json={"chapter_ids": [CHAPTER_ID]},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "TRANSL_FORBIDDEN"


def test_create_job_returns_422_no_model_configured(client, fake_pool):
    # Book settings exist but model_ref is None
    no_model_row = FakeRecord({**_BOOK_SETTINGS_ROW, "model_ref": None})
    fake_pool.fetchrow.return_value = no_model_row

    with patch("app.routers.jobs.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get.return_value = _mock_book_service_response()

        resp = client.post(
            f"/v1/translation/books/{BOOK_ID}/jobs",
            json={"chapter_ids": [CHAPTER_ID]},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NO_MODEL_CONFIGURED"


def test_create_job_returns_201_and_creates_rows(client, fake_pool):
    fake_pool.fetchrow.side_effect = [
        _BOOK_SETTINGS_ROW,   # _resolve_effective_settings (book settings)
        _JOB_ROW,             # INSERT translation_jobs RETURNING *
    ]

    with patch("app.routers.jobs.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get.return_value = _mock_book_service_response()

        resp = client.post(
            f"/v1/translation/books/{BOOK_ID}/jobs",
            json={"chapter_ids": [CHAPTER_ID]},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["total_chapters"] == 1
    assert data["book_id"] == BOOK_ID


def test_create_job_publishes_to_broker_not_background_tasks(client, fake_pool):
    """Plan §6.1: job creation must publish to RabbitMQ, NOT use BackgroundTasks."""
    fake_pool.fetchrow.side_effect = [_BOOK_SETTINGS_ROW, _JOB_ROW]

    with patch("app.routers.jobs.httpx.AsyncClient") as mock_client_cls, \
         patch("app.routers.jobs.publish", new_callable=AsyncMock) as mock_publish, \
         patch("app.routers.jobs.publish_event", new_callable=AsyncMock) as mock_publish_event:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get.return_value = _mock_book_service_response()

        resp = client.post(
            f"/v1/translation/books/{BOOK_ID}/jobs",
            json={"chapter_ids": [CHAPTER_ID]},
        )

    assert resp.status_code == 201
    # Broker publish must have been called with the correct routing key
    mock_publish.assert_called_once()
    routing_key = mock_publish.call_args.args[0]
    assert routing_key == "translation.job"
    # Event publish must also have been called
    mock_publish_event.assert_called_once()
    event_body = mock_publish_event.call_args.args[1]
    assert event_body["event"] == "job.created"


# ── GET /v1/translation/books/{book_id}/jobs ─────────────────────────────────

def test_list_jobs_returns_array(client, fake_pool):
    fake_pool.fetch.return_value = [_JOB_ROW]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["job_id"] == JOB_ID


def test_list_jobs_respects_limit_param(client, fake_pool):
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/jobs?limit=2")
    assert resp.status_code == 200
    call_args = fake_pool.fetch.call_args
    assert 2 in call_args.args or 2 in call_args.kwargs.values()


# ── GET /v1/translation/jobs/{job_id} ────────────────────────────────────────

def test_get_job_returns_detail_with_chapter_translations(client, fake_pool):
    fake_pool.fetchrow.return_value = _JOB_ROW
    fake_pool.fetch.return_value = [_CHAPTER_ROW]
    resp = client.get(f"/v1/translation/jobs/{JOB_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == JOB_ID
    assert len(data["chapter_translations"]) == 1
    assert data["chapter_translations"][0]["status"] == "completed"


def test_get_job_returns_404_when_not_owned(client, fake_pool):
    other_row = FakeRecord({**_JOB_ROW, "owner_user_id": UUID(OTHER_USER_ID)})
    fake_pool.fetchrow.return_value = other_row
    resp = client.get(f"/v1/translation/jobs/{JOB_ID}")
    assert resp.status_code == 404


def test_get_job_returns_404_when_not_found(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.get(f"/v1/translation/jobs/{JOB_ID}")
    assert resp.status_code == 404


# ── GET /v1/translation/jobs/{job_id}/chapters/{chapter_id} ──────────────────

def test_get_chapter_translation_returns_result(client, fake_pool):
    fake_pool.fetchrow.side_effect = [
        FakeRecord({"owner_user_id": UUID(USER_ID)}),  # ownership check
        _CHAPTER_ROW,                                   # chapter row
    ]
    resp = client.get(f"/v1/translation/jobs/{JOB_ID}/chapters/{CHAPTER_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["translated_body"] == "Phần mở đầu..."
    assert data["input_tokens"] == 120
    assert data["output_tokens"] == 98


def test_get_chapter_translation_returns_403_when_not_owned(client, fake_pool):
    fake_pool.fetchrow.return_value = FakeRecord({"owner_user_id": UUID(OTHER_USER_ID)})
    resp = client.get(f"/v1/translation/jobs/{JOB_ID}/chapters/{CHAPTER_ID}")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "TRANSL_FORBIDDEN"


def test_get_chapter_translation_returns_404_when_chapter_missing(client, fake_pool):
    fake_pool.fetchrow.side_effect = [
        FakeRecord({"owner_user_id": UUID(USER_ID)}),
        None,  # no chapter row
    ]
    resp = client.get(f"/v1/translation/jobs/{JOB_ID}/chapters/{CHAPTER_ID}")
    assert resp.status_code == 404


# ── POST /v1/translation/jobs/{job_id}/cancel ────────────────────────────────

def test_cancel_job_sets_cancelled_status(client, fake_pool):
    fake_pool.fetchrow.return_value = FakeRecord({
        "owner_user_id": UUID(USER_ID),
        "status": "running",
    })
    resp = client.post(f"/v1/translation/jobs/{JOB_ID}/cancel")
    assert resp.status_code == 204
    fake_pool.execute.assert_called_once()
    sql = fake_pool.execute.call_args.args[0]
    assert "cancelled" in sql


def test_cancel_job_returns_409_when_already_completed(client, fake_pool):
    fake_pool.fetchrow.return_value = FakeRecord({
        "owner_user_id": UUID(USER_ID),
        "status": "completed",
    })
    resp = client.post(f"/v1/translation/jobs/{JOB_ID}/cancel")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "TRANSL_CANNOT_CANCEL"


def test_cancel_job_returns_404_when_not_owned(client, fake_pool):
    fake_pool.fetchrow.return_value = FakeRecord({
        "owner_user_id": UUID(OTHER_USER_ID),
        "status": "running",
    })
    resp = client.post(f"/v1/translation/jobs/{JOB_ID}/cancel")
    assert resp.status_code == 404


def test_cancel_pending_job_succeeds(client, fake_pool):
    fake_pool.fetchrow.return_value = FakeRecord({
        "owner_user_id": UUID(USER_ID),
        "status": "pending",
    })
    resp = client.post(f"/v1/translation/jobs/{JOB_ID}/cancel")
    assert resp.status_code == 204
