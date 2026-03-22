"""Unit tests for /v1/translation/chapters/.../versions endpoints (LW-72)."""
import datetime
from uuid import UUID, uuid4

import pytest

from tests.conftest import FakeRecord

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHAPTER_ID = str(uuid4())
BOOK_ID = str(uuid4())
JOB_ID = str(uuid4())
VERSION_ID = str(uuid4())

_NOW = datetime.datetime.utcnow()
_CT_ID = uuid4()


def _list_row(**overrides):
    base = {
        "id": _CT_ID,
        "job_id": UUID(JOB_ID),
        "chapter_id": UUID(CHAPTER_ID),
        "book_id": UUID(BOOK_ID),
        "owner_user_id": UUID(USER_ID),
        "status": "completed",
        "translated_body": "Phần mở đầu...",
        "source_language": "en",
        "target_language": "vi",
        "version_num": 1,
        "input_tokens": 100,
        "output_tokens": 80,
        "usage_log_id": None,
        "error_message": None,
        "started_at": _NOW,
        "finished_at": _NOW,
        "created_at": _NOW,
        "is_active": True,
        "active_ct_id": _CT_ID,
        "model_source": "platform_model",
        "model_ref": uuid4(),
    }
    base.update(overrides)
    return FakeRecord(base)


def _get_row(**overrides):
    base = {
        "id": _CT_ID,
        "job_id": UUID(JOB_ID),
        "chapter_id": UUID(CHAPTER_ID),
        "book_id": UUID(BOOK_ID),
        "owner_user_id": UUID(USER_ID),
        "status": "completed",
        "translated_body": "Phần mở đầu...",
        "source_language": "en",
        "target_language": "vi",
        "version_num": 1,
        "input_tokens": 100,
        "output_tokens": 80,
        "usage_log_id": None,
        "error_message": None,
        "started_at": _NOW,
        "finished_at": _NOW,
        "created_at": _NOW,
    }
    base.update(overrides)
    return FakeRecord(base)


def _active_row(**overrides):
    base = {
        "owner_user_id": UUID(USER_ID),
        "target_language": "vi",
        "status": "completed",
    }
    base.update(overrides)
    return FakeRecord(base)


# ── GET /v1/translation/chapters/{chapter_id}/versions ────────────────────────

def test_list_versions_empty_when_no_translations(client, fake_pool):
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chapter_id"] == CHAPTER_ID
    assert data["languages"] == []


def test_list_versions_groups_rows_by_language(client, fake_pool):
    row_vi = _list_row()
    row_zh = _list_row(
        id=uuid4(),
        target_language="zh",
        active_ct_id=None,
        is_active=False,
        version_num=1,
    )
    fake_pool.fetch.return_value = [row_vi, row_zh]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    langs = {g["target_language"] for g in resp.json()["languages"]}
    assert langs == {"vi", "zh"}


def test_list_versions_marks_is_active_true_for_active_version(client, fake_pool):
    fake_pool.fetch.return_value = [_list_row(is_active=True, active_ct_id=_CT_ID)]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    group = resp.json()["languages"][0]
    assert group["target_language"] == "vi"
    assert group["versions"][0]["is_active"] is True


def test_list_versions_marks_is_active_false_when_no_active_set(client, fake_pool):
    fake_pool.fetch.return_value = [_list_row(is_active=False, active_ct_id=None)]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    group = resp.json()["languages"][0]
    assert group["active_id"] is None
    assert group["versions"][0]["is_active"] is False


def test_list_versions_includes_version_num(client, fake_pool):
    fake_pool.fetch.return_value = [_list_row(version_num=3)]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    group = resp.json()["languages"][0]
    assert group["versions"][0]["version_num"] == 3


def test_list_versions_multiple_versions_same_language(client, fake_pool):
    v2_id = uuid4()
    row_v2 = _list_row(id=v2_id, version_num=2, is_active=False)
    row_v1 = _list_row(id=_CT_ID, version_num=1, is_active=True)
    fake_pool.fetch.return_value = [row_v2, row_v1]
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions")
    assert resp.status_code == 200
    langs = resp.json()["languages"]
    # All under single language group
    assert len(langs) == 1
    assert len(langs[0]["versions"]) == 2


# ── GET /v1/translation/chapters/{chapter_id}/versions/{version_id} ───────────

def test_get_version_returns_full_translation(client, fake_pool):
    fake_pool.fetchrow.return_value = _get_row()
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["translated_body"] == "Phần mở đầu..."
    assert data["target_language"] == "vi"
    assert data["input_tokens"] == 100
    assert data["output_tokens"] == 80


def test_get_version_returns_404_when_not_found(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_FOUND"


def test_get_version_returns_403_when_not_owned(client, fake_pool):
    fake_pool.fetchrow.return_value = _get_row(owner_user_id=UUID(OTHER_USER_ID))
    resp = client.get(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "TRANSL_FORBIDDEN"


# ── PUT /v1/translation/chapters/{chapter_id}/versions/{version_id}/active ────

def test_set_active_version_returns_200_and_upserts(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row()
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_id"] == VERSION_ID
    assert data["target_language"] == "vi"
    assert data["chapter_id"] == CHAPTER_ID
    # DB execute must be called to upsert active table
    fake_pool.execute.assert_called_once()


def test_set_active_version_returns_404_when_not_found(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_FOUND"


def test_set_active_version_returns_403_when_not_owned(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row(owner_user_id=UUID(OTHER_USER_ID))
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "TRANSL_FORBIDDEN"


def test_set_active_version_returns_422_when_status_failed(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row(status="failed")
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_COMPLETED"


def test_set_active_version_returns_422_when_status_pending(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row(status="pending")
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_COMPLETED"


def test_set_active_version_returns_422_when_status_running(client, fake_pool):
    fake_pool.fetchrow.return_value = _active_row(status="running")
    resp = client.put(f"/v1/translation/chapters/{CHAPTER_ID}/versions/{VERSION_ID}/active")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TRANSL_NOT_COMPLETED"
