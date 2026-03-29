"""Tests for the synchronous translate-text endpoint."""
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

from tests.conftest import FakeRecord

TEST_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TEST_MODEL_REF = str(uuid4())


def _prefs_row(**overrides):
    base = {
        "user_id": TEST_USER_ID,
        "target_language": "vi",
        "model_source": "user_model",
        "model_ref": TEST_MODEL_REF,
        "system_prompt": "Translate {source_language} to {target_language}.",
        "user_prompt_tpl": "Translate:\n\n{chapter_text}",
        "compact_model_source": None,
        "compact_model_ref": None,
        "compact_system_prompt": "",
        "compact_user_prompt_tpl": "",
        "chunk_size_tokens": 2000,
        "invoke_timeout_secs": 300,
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    base.update(overrides)
    return FakeRecord(base)


def _mock_httpx(mock_httpx_cls, response):
    """Set up mock httpx.AsyncClient to return a given response from post()."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=response)
    mock_httpx_cls.return_value = mock_client
    return mock_client


class TestTranslateText:
    def test_no_model_configured_returns_422(self, client, fake_pool):
        fake_pool.fetchrow.return_value = None  # no preferences
        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello world"},
        )
        assert resp.status_code == 422

    @patch("app.routers.translate.httpx.AsyncClient")
    def test_successful_translation(self, mock_httpx_cls, client, fake_pool):
        fake_pool.fetchrow.return_value = _prefs_row()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "output": {"content": "Xin chao the gioi"},
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        _mock_httpx(mock_httpx_cls, mock_response)

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello world"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["translated_text"] == "Xin chao the gioi"
        assert body["target_language"] == "vi"
        assert body["input_tokens"] == 10
        assert body["output_tokens"] == 8

    @patch("app.routers.translate.httpx.AsyncClient")
    def test_override_target_language(self, mock_httpx_cls, client, fake_pool):
        fake_pool.fetchrow.return_value = _prefs_row()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "output": {"content": "Bonjour le monde"},
            "usage": {},
        }
        _mock_httpx(mock_httpx_cls, mock_response)

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello world", "target_language": "fr"},
        )
        assert resp.status_code == 200
        assert resp.json()["target_language"] == "fr"

    @patch("app.routers.translate.httpx.AsyncClient")
    def test_provider_402_returns_402(self, mock_httpx_cls, client, fake_pool):
        fake_pool.fetchrow.return_value = _prefs_row()

        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.is_success = False
        _mock_httpx(mock_httpx_cls, mock_response)

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 402

    @patch("app.routers.translate.httpx.AsyncClient")
    def test_provider_500_returns_502(self, mock_httpx_cls, client, fake_pool):
        fake_pool.fetchrow.return_value = _prefs_row()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False
        _mock_httpx(mock_httpx_cls, mock_response)

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 502

    @patch("app.routers.translate.httpx.AsyncClient")
    def test_malformed_provider_response_returns_502(self, mock_httpx_cls, client, fake_pool):
        fake_pool.fetchrow.return_value = _prefs_row()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"unexpected": "shape"}
        _mock_httpx(mock_httpx_cls, mock_response)

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 502
        assert "Malformed" in resp.json()["detail"]

    @patch("app.routers.translate.httpx.AsyncClient")
    def test_uses_user_timeout_preference(self, mock_httpx_cls, client, fake_pool):
        fake_pool.fetchrow.return_value = _prefs_row(invoke_timeout_secs=60)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "output": {"content": "translated"},
            "usage": {},
        }
        _mock_httpx(mock_httpx_cls, mock_response)

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 200
        # Verify httpx.AsyncClient was constructed with the user's timeout
        mock_httpx_cls.assert_called_once_with(timeout=60)

    def test_missing_text_returns_422(self, client, fake_pool):
        resp = client.post(
            "/v1/translation/translate-text",
            json={},
        )
        assert resp.status_code == 422
