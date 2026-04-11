"""Tests for the voice message router."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import TEST_SESSION_ID, TEST_USER_ID, make_session_record


class TestSendVoiceMessage:
    @pytest.mark.asyncio
    async def test_returns_200_with_sse_stream(self, client, mock_pool):
        """Valid audio + config returns 200 SSE stream."""
        mock_pool.fetchrow.return_value = make_session_record()

        from app.models import ProviderCredentials
        mock_creds = ProviderCredentials(
            provider_kind="openai",
            provider_model_name="whisper-1",
            base_url="http://test",
            api_key="sk-test",
            context_length=None,
        )

        async def fake_voice_stream(**kwargs):
            yield 'data: {"type": "stt-transcript", "text": "hello"}\n\n'
            yield 'data: {"type": "text-delta", "delta": "Hi there"}\n\n'
            yield 'data: {"type": "finish-message", "finishReason": "stop"}\n\n'
            yield "data: [DONE]\n\n"

        with (
            patch("app.routers.voice.get_provider_client") as mock_provider,
            patch("app.routers.voice.voice_stream_response", side_effect=fake_voice_stream),
        ):
            mock_provider.return_value.resolve = AsyncMock(return_value=mock_creds)

            resp = await client.post(
                f"/v1/chat/sessions/{TEST_SESSION_ID}/voice-message",
                files={"audio": ("audio.webm", b"\x00" * 100, "audio/webm")},
                data={"config": '{"tts_voice": "af_heart"}'},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        assert "stt-transcript" in body
        assert "text-delta" in body
        assert "[DONE]" in body

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/voice-message",
            files={"audio": ("audio.webm", b"\x00" * 100, "audio/webm")},
            data={"config": "{}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archived_session_returns_409(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record(status="archived")

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/voice-message",
            files={"audio": ("audio.webm", b"\x00" * 100, "audio/webm")},
            data={"config": "{}"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_empty_audio_returns_400(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/voice-message",
            files={"audio": ("audio.webm", b"", "audio/webm")},
            data={"config": "{}"},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_config_json_returns_400(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/voice-message",
            files={"audio": ("audio.webm", b"\x00" * 100, "audio/webm")},
            data={"config": "not-json{"},
        )
        assert resp.status_code == 400
        assert "invalid config" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_wrong_content_type_returns_400(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/voice-message",
            files={"audio": ("photo.jpg", b"\xff\xd8" * 50, "image/jpeg")},
            data={"config": "{}"},
        )
        assert resp.status_code == 400
        assert "unsupported content type" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_oversized_audio_returns_413(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/voice-message",
            files={"audio": ("audio.webm", b"\x00" * (11 * 1024 * 1024), "audio/webm")},
            data={"config": "{}"},
        )
        assert resp.status_code == 413
