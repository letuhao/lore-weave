"""Unit tests for voice resolution (M5 — D-CHATAI-M5-VOICE-UNIFY).

The saved account voice (user_chat_ai_prefs.voice) must WIN over the request's
echoed default, killing the 'af_heart resets every request' behavior; an unset
field falls through to the request, then the System default."""
from __future__ import annotations

from app.services.voice_settings import merge_voice_config, voice_blob_to_config


def test_blob_maps_chat_surface_and_shared_fields():
    voice = {
        "chat": {"tts_source": "user_model", "tts_model_ref": "m1", "tts_voice_id": "bella"},
        "stt": {"source": "ai_model", "model_ref": "s1"},
        "vad": {"silence_frames": 12, "min_duration_ms": 300},
    }
    cfg = voice_blob_to_config(voice)
    assert cfg == {
        "tts_voice": "bella", "tts_model_ref": "m1", "tts_model_source": "user_model",
        # legacy stored 'ai_model' is coerced to canonical 'user_model' on read
        # (D-CHATAI-VOICE-TWO-STORES).
        "stt_model_ref": "s1", "stt_model_source": "user_model",
        "vad_silence_frames": 12, "vad_min_duration_ms": 300,
    }


def test_empty_blob_yields_empty_config():
    assert voice_blob_to_config({}) == {}
    assert voice_blob_to_config({"chat": {"tts_voice_id": ""}}) == {}  # empty ignored


def test_saved_voice_wins_over_request_default():
    # the FE echoes af_heart; the saved account voice must override it.
    req = {"tts_voice": "af_heart", "stt_model_ref": "s1", "tts_model_ref": "m0"}
    voice = {"chat": {"tts_voice_id": "nova", "tts_model_ref": "m1"}}
    merged = merge_voice_config(req, voice)
    assert merged["tts_voice"] == "nova"       # saved wins
    assert merged["tts_model_ref"] == "m1"     # saved wins
    assert merged["stt_model_ref"] == "s1"     # request kept where store unset


def test_request_kept_when_store_unset():
    merged = merge_voice_config({"tts_voice": "af_heart"}, {})
    assert merged["tts_voice"] == "af_heart"   # nothing saved → request default stands


def test_none_inputs_safe():
    assert merge_voice_config(None, None) == {}


# ── D-CHATAI-VOICE-TWO-STORES — the two-stores vocab reconcile (WS-4.0) ──────
def test_read_coerces_legacy_ai_model_on_both_surfaces():
    voice = {
        "chat": {"tts_source": "ai_model", "tts_model_ref": "m1"},
        "stt": {"source": "ai_model", "model_ref": "s1"},
    }
    cfg = voice_blob_to_config(voice)
    assert cfg["tts_model_source"] == "user_model"
    assert cfg["stt_model_source"] == "user_model"


def test_read_passes_browser_and_user_model_through():
    cfg = voice_blob_to_config({"chat": {"tts_source": "user_model"}, "stt": {"source": "browser"}})
    assert cfg["tts_model_source"] == "user_model"
    assert cfg["stt_model_source"] == "browser"
