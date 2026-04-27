"""Tests for the synchronous translate-text endpoint.

Phase 4c-γ: rewritten to mock the loreweave_llm SDK via FakeLLMClient
+ FastAPI dependency_overrides instead of patching httpx directly.
The legacy test_uses_user_timeout_preference is dropped because the
SDK has its own polling timeout (no httpx.AsyncClient(timeout=...)
to assert).
"""
from typing import Any
import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from loreweave_llm.errors import LLMError, LLMQuotaExceeded
from loreweave_llm.models import Job, JobError

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


class FakeLLMClient:
    """Stand-in for app.llm_client.LLMClient. Captures submit_and_wait
    kwargs + replays a scripted Job (or raises a queued exception)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.queued: list[Any] = []

    def queue_translation(
        self,
        *,
        content: str = "",
        status: str = "completed",
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_code: str | None = None,
        error_message: str = "",
    ) -> None:
        if status == "completed":
            result = {
                "messages": [{"role": "assistant", "content": content}],
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            }
        else:
            result = None
        error = JobError(code=error_code, message=error_message) if error_code else None
        self.queued.append(Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="translation",
            status=status,  # type: ignore[arg-type]
            result=result,
            error=error,
            submitted_at="2026-04-27T00:00:00Z",
        ))

    def queue_exception(self, exc: Exception) -> None:
        self.queued.append(exc)

    async def submit_and_wait(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.queued:
            raise AssertionError("FakeLLMClient: no queued response")
        item = self.queued.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_llm():
    """Per-test FakeLLMClient + FastAPI dependency override."""
    from app.main import app
    from app.llm_client import get_llm_client

    fake = FakeLLMClient()

    def _override():
        return fake

    app.dependency_overrides[get_llm_client] = _override
    yield fake
    # Cleanup happens via the autouse client fixture's clear()


class TestTranslateText:
    def test_no_model_configured_returns_422(self, client, fake_pool):
        fake_pool.fetchrow.return_value = None  # no preferences
        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello world"},
        )
        assert resp.status_code == 422

    def test_successful_translation(self, client, fake_pool, fake_llm):
        fake_pool.fetchrow.return_value = _prefs_row()
        fake_llm.queue_translation(
            content="Xin chao the gioi",
            input_tokens=10, output_tokens=8,
        )

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
        # Phase 4c-γ wire-shape pin (review-impl style)
        assert len(fake_llm.calls) == 1
        call = fake_llm.calls[0]
        assert call["operation"] == "translation"
        assert call["model_source"] == "user_model"
        assert str(call["model_ref"]) == str(TEST_MODEL_REF)
        assert call["chunking"] is None
        assert "endpoint" in call["job_meta"]

    def test_override_target_language(self, client, fake_pool, fake_llm):
        fake_pool.fetchrow.return_value = _prefs_row()
        fake_llm.queue_translation(content="Bonjour le monde")

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello world", "target_language": "fr"},
        )
        assert resp.status_code == 200
        assert resp.json()["target_language"] == "fr"

    def test_quota_exceeded_returns_402(self, client, fake_pool, fake_llm):
        """Phase 4c-γ — LLMQuotaExceeded (402 billing) maps to 402."""
        fake_pool.fetchrow.return_value = _prefs_row()
        fake_llm.queue_exception(LLMQuotaExceeded("402 billing rejected"))

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 402

    def test_provider_error_returns_502(self, client, fake_pool, fake_llm):
        """Phase 4c-γ — generic LLMError (transport/upstream) maps to 502."""
        fake_pool.fetchrow.return_value = _prefs_row()
        fake_llm.queue_exception(LLMError("connection refused"))

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 502

    def test_failed_job_returns_502(self, client, fake_pool, fake_llm):
        """Phase 4c-γ — Job.status='failed' (not exception) → 502."""
        fake_pool.fetchrow.return_value = _prefs_row()
        fake_llm.queue_translation(
            status="failed",
            error_code="LLM_UPSTREAM_ERROR",
            error_message="provider 502",
        )

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 502

    def test_failed_job_quota_exceeded_returns_402(self, client, fake_pool, fake_llm):
        """Phase 4c-γ — Job.status='failed' with LLM_QUOTA_EXCEEDED → 402."""
        fake_pool.fetchrow.return_value = _prefs_row()
        fake_llm.queue_translation(
            status="failed",
            error_code="LLM_QUOTA_EXCEEDED",
            error_message="quota exhausted",
        )

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 402

    def test_empty_content_returns_502(self, client, fake_pool, fake_llm):
        """Phase 4c-γ — completed job with empty content → 502 malformed."""
        fake_pool.fetchrow.return_value = _prefs_row()
        fake_llm.queue_translation(content="")

        resp = client.post(
            "/v1/translation/translate-text",
            json={"text": "Hello"},
        )
        assert resp.status_code == 502
        assert "Malformed" in resp.json()["detail"]

    def test_missing_text_returns_422(self, client, fake_pool):
        resp = client.post(
            "/v1/translation/translate-text",
            json={},
        )
        assert resp.status_code == 422
