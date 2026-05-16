"""Phase 5b /review-impl LOW#11 regression-lock — chat-service voice path
must NOT call provider_client.resolve() for STT or TTS model resolution.

After Phase 5b, the gateway owns model-name lookup via `model_ref` →
user_model row. The legacy `provider.resolve()` call in
voice_stream_service.py was dead code post-migration; this test asserts
it stays dead so a future "I'll add the lookup back for caching" change
gets caught.

Grep-lock pattern (not import-lock) because the chat-service test
fixtures mock the SDK, so a runtime check wouldn't surface the dead
call — only static analysis catches it.
"""
from __future__ import annotations

from pathlib import Path

VOICE_STREAM_SERVICE = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "services"
    / "voice_stream_service.py"
)


def test_voice_stream_service_does_not_call_provider_resolve():
    """`provider.resolve(...)` must not appear in voice_stream_service.py.

    If you're adding model-name caching, do it in the SDK or the gateway,
    not here — chat-service no longer needs upstream model names.
    """
    src = VOICE_STREAM_SERVICE.read_text(encoding="utf-8")
    # The literal "provider.resolve" substring is what we're banning.
    # get_provider_client() can still be imported for OTHER non-voice
    # paths (it isn't currently used in this module, but importing it
    # is fine — calling .resolve() on it is the smell).
    assert "provider.resolve" not in src, (
        "voice_stream_service.py contains a provider.resolve(...) call. "
        "Phase 5b moved STT/TTS model-name resolution to the gateway; "
        "chat-service should NOT look up provider_model_name itself. "
        "If you need it for something else, justify in the PR description "
        "and update this regression-lock with the exception."
    )


def test_voice_stream_service_does_not_import_httpx():
    """Phase 5b — direct httpx usage in the voice path was replaced by
    the SDK. Reintroducing httpx here would bypass the SDK's auth/retry
    semantics and risk drift.

    NOTE: other chat-service modules (billing_client, knowledge_client,
    voice.py router) legitimately use httpx — this lock is scoped
    to voice_stream_service.py only.
    """
    src = VOICE_STREAM_SERVICE.read_text(encoding="utf-8")
    # Allow comment mentions but ban actual imports.
    lines = [
        line for line in src.splitlines()
        if line.startswith("import httpx") or line.startswith("from httpx")
    ]
    assert not lines, (
        f"voice_stream_service.py imports httpx directly: {lines}. "
        "Phase 5b — use the loreweave_llm SDK (Client.transcribe / "
        "Client.stream_tts) instead. Drift would bypass SDK auth/retry."
    )


def test_voice_stream_service_uses_sdk_client():
    """Sanity check on the migration target — confirm the SDK Client is
    imported. Pairs with the bans above to make the positive
    pattern explicit.
    """
    src = VOICE_STREAM_SERVICE.read_text(encoding="utf-8")
    assert "from loreweave_llm import" in src, (
        "voice_stream_service.py should import from loreweave_llm SDK"
    )
    assert "Client" in src, "SDK Client must be imported"
