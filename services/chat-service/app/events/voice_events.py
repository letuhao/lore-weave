"""Voice analytics event publisher — emits voice.turn events to Redis Stream."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_STREAM_KEY = "loreweave:events:voice"

_redis: Any = None


def _get_redis() -> Any:
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def emit_voice_turn(
    user_id: str,
    session_id: str,
    stt_success: bool,
    stt_duration_ms: int,
    speech_duration_ms: int | None = None,
    audio_size_kb: int | None = None,
    llm_first_token_ms: int | None = None,
    tts_sentence_count: int = 0,
    tts_skipped_count: int = 0,
    threshold_silence_frames: int = 8,
    threshold_min_duration_ms: int = 500,
) -> None:
    """Emit a voice.turn event to Redis Stream for statistics-service consumption."""
    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "stt_success": stt_success,
        "stt_duration_ms": stt_duration_ms,
        "speech_duration_ms": speech_duration_ms,
        "audio_size_kb": audio_size_kb,
        "llm_first_token_ms": llm_first_token_ms,
        "tts_sentence_count": tts_sentence_count,
        "tts_skipped_count": tts_skipped_count,
        "threshold_silence_frames": threshold_silence_frames,
        "threshold_min_duration_ms": threshold_min_duration_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        r = _get_redis()
        await r.xadd(_STREAM_KEY, {
            "event_type": "voice.turn",
            "payload": json.dumps(payload),
        })
    except Exception:
        logger.warning("Failed to emit voice.turn event", exc_info=True)
        # Non-blocking — analytics failure should not break voice pipeline
