"""Chat & AI settings — voice resolution (spec §4.4, D-CHATAI-M5-VOICE-UNIFY).

Maps the unified per-user voice blob (`user_chat_ai_prefs.voice`) onto the flat
`voice_config` keys the voice stream service consumes, and merges it with the
per-request config so the user's SAVED voice (the new canonical home) wins over
the FE's echoed default — killing the "af_heart resets every request" behavior.

Voice blob shape (per-surface, spec §4.4):
    voice = {
      stt:   {source, model_ref},
      vad:   {silence_frames, min_duration_ms},
      speed,
      chat:    {tts_source, tts_model_ref, tts_voice_id},   # talk-to-chat
      reading: {tts_source, tts_model_ref, tts_voice_id},   # read-aloud (reader)
    }
A voice_id always travels coupled to its tts_model_ref (a voice is only valid for
its model). This maps the `chat` surface (the voice-message loop).
"""

from __future__ import annotations

from app.services.settings_resolution import canon_voice_source


def voice_blob_to_config(voice: dict) -> dict:
    """Flatten the stored voice blob's `chat` surface + shared fields to the
    `voice_config` keys `voice_stream_service` reads. Only SET values appear (so
    the caller can overlay them onto a request config)."""
    out: dict = {}
    chat = voice.get("chat") or {}
    if chat.get("tts_voice_id"):
        out["tts_voice"] = chat["tts_voice_id"]
    if chat.get("tts_model_ref"):
        out["tts_model_ref"] = chat["tts_model_ref"]
    if chat.get("tts_source"):
        # coerce legacy 'ai_model' → canonical 'user_model' so already-stored rows
        # resolve at the consumer (D-CHATAI-VOICE-TWO-STORES).
        out["tts_model_source"] = canon_voice_source(chat["tts_source"])
    stt = voice.get("stt") or {}
    if stt.get("model_ref"):
        out["stt_model_ref"] = stt["model_ref"]
    if stt.get("source"):
        out["stt_model_source"] = canon_voice_source(stt["source"])
    vad = voice.get("vad") or {}
    if vad.get("silence_frames") is not None:
        out["vad_silence_frames"] = vad["silence_frames"]
    if vad.get("min_duration_ms") is not None:
        out["vad_min_duration_ms"] = vad["min_duration_ms"]
    return out


def merge_voice_config(request_config: dict, voice_blob: dict) -> dict:
    """Return `request_config` with the user's stored voice overlaid so the SAVED
    voice wins where set (the new canonical home is authoritative; the request is
    the FE echo of the legacy store). A field the store doesn't set falls through
    to the request, then to the voice-stream service's System default."""
    stored = voice_blob_to_config(voice_blob or {})
    return {**(request_config or {}), **stored}
