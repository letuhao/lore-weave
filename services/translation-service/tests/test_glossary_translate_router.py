"""Router tests for glossary batch translation jobs."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from tests.conftest import FakeRecord
from app.grant_client import GrantLevel

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOOK_ID = str(uuid4())
MODEL_REF = str(uuid4())


@pytest.fixture
def client_gt(client):
    with (
        patch("app.routers.glossary_translate.publish", new_callable=AsyncMock) as pub,
        patch(
            "app.routers.glossary_translate.fetch_translation_candidates",
            new_callable=AsyncMock,
            return_value={"total": 2, "items": [{"attributes": [{"code": "name"}]}]},
        ),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {"original_language": "zh"}
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client
        yield client, pub


def test_glossary_translate_create_403_view(client_gt, fake_pool, grant_stub):
    client, _ = client_gt
    grant_stub.level = GrantLevel.VIEW
    resp = client.post(
        f"/v1/glossary-translate/books/{BOOK_ID}/translate",
        json={"target_language": "vi"},
    )
    assert resp.status_code == 403


def test_glossary_translate_create_202(client_gt, fake_pool, grant_stub):
    client, pub = client_gt
    grant_stub.level = GrantLevel.EDIT
    job_id = uuid4()
    fake_pool.fetchrow.return_value = FakeRecord({"job_id": job_id})
    resp = client.post(
        f"/v1/glossary-translate/books/{BOOK_ID}/translate",
        json={"target_language": "vi", "model_ref": MODEL_REF},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_type"] == "translate_glossary"
    assert body["total_entities"] == 2
    pub.assert_awaited_once()


def test_glossary_translate_create_422_same_language(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.EDIT
    with (
        patch("app.routers.glossary_translate.publish", new_callable=AsyncMock) as pub,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {"original_language": "vi"}
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client
        resp = client.post(
            f"/v1/glossary-translate/books/{BOOK_ID}/translate",
            json={"target_language": "vi", "model_ref": MODEL_REF},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "GT_SAME_LANGUAGE"
    pub.assert_not_awaited()


def test_glossary_translate_get_job(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.VIEW
    job_id = uuid4()
    fake_pool.fetchrow.return_value = FakeRecord({
        "job_id": job_id,
        "book_id": UUID(BOOK_ID),
        "status": "running",
        "source_language": "zh",
        "target_language": "vi",
        "overwrite_mode": "missing_only",
        "total_entities": 5,
        "completed_entities": 2,
        "failed_entities": 0,
        "attrs_translated": 4,
        "attrs_skipped": 1,
        "total_input_tokens": 100,
        "total_output_tokens": 50,
        "cost_estimate": '{"llm_calls": 5}',
        "error_message": None,
        "started_at": None,
        "finished_at": None,
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    })
    resp = client.get(f"/v1/glossary-translate/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["job_type"] == "translate_glossary"
