"""Voice stream service — STT → LLM → TTS pipeline as SSE async generator.

Extends the existing stream_response() pattern with audio input/output.
~70% shared logic with stream_service.py (LLM streaming, message history,
provider resolution, DB persistence).

Design ref: VOICE_PIPELINE_V2.md §4.2
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg
import httpx

from app.client.billing_client import BillingClient
from app.client.provider_client import get_provider_client
from app.config import settings
from app.events.voice_events import emit_voice_turn
from app.models import ProviderCredentials
from app.services.sentence_buffer import SentenceBuffer
from app.services.text_normalizer import TextNormalizer
from app.services.stream_service import _is_openai_compatible, _stream_openai_compatible, _stream_litellm
from app.storage.minio_client import upload_file

logger = logging.getLogger(__name__)


# Voice system prompt — injected server-side when input_method='voice'
VOICE_SYSTEM_PROMPT = (
    "You are in a voice conversation. The user is speaking to you and will hear "
    "your response as speech via text-to-speech.\n\n"
    "Rules for voice mode responses:\n"
    "- Respond in natural, conversational speech — as if talking to a friend\n"
    "- Do NOT use markdown formatting (no **, *, #, ```, etc.)\n"
    "- Do NOT output code blocks — describe what code does instead\n"
    "- Do NOT use bullet points or numbered lists — use flowing sentences\n"
    "- Do NOT use tables or JSON — describe data verbally\n"
    "- Keep responses concise (2-4 sentences for simple questions)\n"
    "- Use natural speech patterns: contractions, filler words are OK\n"
    "- If the user asks about code, explain the concept verbally\n"
    "- Pronounce abbreviations: 'API' as 'A P I', 'URL' as 'U R L'"
)


def _sse(event_type: str, data: dict) -> str:
    """Format an SSE event line."""
    return f'data: {json.dumps({"type": event_type, **data})}\n\n'


def _resolve_model(creds: ProviderCredentials) -> tuple[str, str | None, str, bool]:
    """Resolve model string, base_url, api_key, and whether to use OpenAI SDK."""
    api_key = creds.api_key if creds.api_key else "lw-no-key"
    base_url = creds.base_url or None
    use_openai_sdk = _is_openai_compatible(creds.provider_kind)

    if creds.provider_kind == "anthropic":
        model_string = f"anthropic/{creds.provider_model_name}"
    elif creds.provider_kind == "openai" and not base_url:
        model_string = creds.provider_model_name
        base_url = "https://api.openai.com/v1"
    else:
        model_string = creds.provider_model_name
        if creds.provider_kind == "lm_studio" and base_url and not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

    return api_key, base_url, model_string, use_openai_sdk


async def _transcribe_audio(
    audio_bytes: bytes,
    content_type: str,
    user_id: str,
    stt_model_source: str,
    stt_model_ref: str,
    stt_model_name: str = "whisper-1",
) -> tuple[str, int]:
    """Call STT via provider-registry internal proxy. Returns (transcript, duration_ms)."""
    ext = 'webm' if 'webm' in content_type else 'wav' if 'wav' in content_type else 'ogg'
    start = time.monotonic()

    params = {
        "user_id": user_id,
        "model_source": stt_model_source,
        "model_ref": stt_model_ref,
    }
    proxy_url = f"{settings.provider_registry_internal_url}/internal/proxy/v1/audio/transcriptions"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            proxy_url,
            params=params,
            files={"file": (f"audio.{ext}", audio_bytes, content_type)},
            data={"model": stt_model_name},
            headers={"X-Internal-Token": settings.internal_service_token},
        )
        resp.raise_for_status()

    duration_ms = round((time.monotonic() - start) * 1000)
    result = resp.json()
    return result.get("text", ""), duration_ms


async def _generate_tts_chunks(
    text: str,
    user_id: str,
    tts_model_source: str,
    tts_model_ref: str,
    tts_voice: str,
    tts_model_name: str,
    sentence_index: int,
) -> AsyncGenerator[tuple[dict, bytes], None]:
    """Call TTS via provider-registry internal proxy, yield (sse_event, raw_bytes) per chunk."""
    params = {
        "user_id": user_id,
        "model_source": tts_model_source,
        "model_ref": tts_model_ref,
    }
    proxy_url = f"{settings.provider_registry_internal_url}/internal/proxy/v1/audio/speech"

    chunk_index = 0
    async with httpx.AsyncClient(timeout=30) as client:
        async with client.stream(
            "POST",
            proxy_url,
            params=params,
            json={"model": tts_model_name, "input": text, "voice": tts_voice, "response_format": "mp3"},
            headers={
                "X-Internal-Token": settings.internal_service_token,
                "Content-Type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size=4096):
                event = {
                    "sentenceIndex": sentence_index,
                    "chunkIndex": chunk_index,
                    "data": base64.b64encode(chunk).decode(),
                    "final": False,
                }
                yield event, chunk
                chunk_index += 1

    # Signal sentence complete
    yield {
        "sentenceIndex": sentence_index,
        "chunkIndex": chunk_index,
        "data": "",
        "final": True,
    }, b""


async def _upload_audio_segment(
    pool: asyncpg.Pool,
    session_id: str,
    message_id: str,
    user_id: str,
    segment_index: int,
    sentence_text: str,
    audio_data: bytes,
) -> None:
    """Upload audio to S3 and save segment ref to DB. Fire-and-forget."""
    if not audio_data:
        return
    try:
        object_key = f"voice-audio/{session_id}/{message_id}/{segment_index}_{int(time.time())}.mp3"
        await upload_file(object_key, io.BytesIO(audio_data), content_type="audio/mpeg")

        await pool.execute(
            """
            INSERT INTO message_audio_segments
              (message_id, session_id, user_id, segment_index, object_key, sentence_text, duration_s)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (message_id, segment_index) DO UPDATE
              SET object_key = EXCLUDED.object_key, sentence_text = EXCLUDED.sentence_text
            """,
            message_id, session_id, user_id, segment_index, object_key, sentence_text, None,
        )
    except Exception:
        logger.warning("Audio segment upload failed for %s/%d", message_id, segment_index, exc_info=True)


def _sanitize_transcript(text: str) -> str:
    """Basic sanitization of STT transcript before LLM submission."""
    # Length cap
    if len(text) > 1000:
        text = text[:1000]
    return text.strip()


async def voice_stream_response(
    session_id: str,
    audio_bytes: bytes,
    audio_content_type: str,
    user_id: str,
    model_source: str,
    model_ref: str,
    creds: ProviderCredentials,
    pool: asyncpg.Pool,
    billing: BillingClient,
    voice_config: dict,
) -> AsyncGenerator[str, None]:
    """Async generator: STT → LLM stream → SentenceBuffer → Normalize → TTS → SSE.

    Yields AI SDK data stream protocol SSE lines, extended with voice events.
    """
    normalizer = TextNormalizer()
    sentence_buffer = SentenceBuffer(clause_mode=False)  # Full sentences for natural TTS prosody

    stt_model_source = voice_config.get("stt_model_source", "user_model")
    stt_model_ref = voice_config.get("stt_model_ref", "")
    tts_model_source = voice_config.get("tts_model_source", "user_model")
    tts_model_ref = voice_config.get("tts_model_ref", "")
    tts_voice = voice_config.get("tts_voice", "af_heart")

    # Resolve STT/TTS provider credentials to get actual model names
    # These come from the user's registered models — no hardcoded fallbacks
    provider = get_provider_client()
    try:
        stt_creds = await provider.resolve(stt_model_source, stt_model_ref, user_id)
    except Exception:
        logger.exception("STT model resolution failed for %s", stt_model_ref)
        yield _sse("error", {"errorText": "STT model not found. Check Voice Settings."})
        yield "data: [DONE]\n\n"
        return
    stt_model_name = stt_creds.provider_model_name

    tts_model_name = ""
    if tts_model_ref:
        try:
            tts_creds = await provider.resolve(tts_model_source, tts_model_ref, user_id)
            tts_model_name = tts_creds.provider_model_name
        except Exception:
            logger.warning("TTS model resolution failed for %s — audio will be skipped", tts_model_ref)

    # Track voice config for analytics
    vad_silence_frames = voice_config.get("vad_silence_frames", 8)
    vad_min_duration_ms = voice_config.get("vad_min_duration_ms", 500)
    speech_duration_ms = voice_config.get("speech_duration_ms")
    audio_size_kb = round(len(audio_bytes) / 1024)

    # ── Step 1: STT ──────────────────────────────────────────────────
    try:
        transcript, stt_ms = await _transcribe_audio(
            audio_bytes, audio_content_type, user_id,
            stt_model_source, stt_model_ref, stt_model_name,
        )
    except Exception:
        logger.exception("STT failed for session %s", session_id)
        asyncio.create_task(emit_voice_turn(
            user_id=user_id, session_id=session_id, stt_success=False, stt_duration_ms=0,
            speech_duration_ms=speech_duration_ms,
            threshold_silence_frames=vad_silence_frames,
            threshold_min_duration_ms=vad_min_duration_ms,
        ))
        yield _sse("error", {"errorText": "Speech recognition failed. Please try again."})
        yield "data: [DONE]\n\n"
        return

    yield _sse("stt-transcript", {
        "text": transcript,
        "durationMs": stt_ms,
        "audioSizeKB": audio_size_kb,
    })

    # Reject empty/garbage
    if not transcript or len(transcript.strip()) < 2:
        asyncio.create_task(emit_voice_turn(
            user_id=user_id, session_id=session_id, stt_success=False,
            stt_duration_ms=stt_ms, speech_duration_ms=speech_duration_ms,
            threshold_silence_frames=vad_silence_frames,
            threshold_min_duration_ms=vad_min_duration_ms,
        ))
        yield _sse("error", {"errorText": "Could not understand speech. Try again."})
        yield "data: [DONE]\n\n"
        return

    transcript = _sanitize_transcript(transcript)

    # ── Step 2: Save user message ────────────────────────────────────
    async with pool.acquire() as conn:
        seq = await conn.fetchval(
            "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages WHERE session_id=$1 AND branch_id=0",
            session_id,
        )
        user_msg_id = str(uuid4())
        content_parts = json.dumps({
            "input_method": "voice",
            "stt_model": f"{stt_model_source}:{stt_model_ref}",
            "stt_ms": stt_ms,
        })
        await conn.execute(
            """
            INSERT INTO chat_messages
              (message_id, session_id, owner_user_id, role, content, content_parts, sequence_num, branch_id)
            VALUES ($1,$2,$3,'user',$4,$5::jsonb,$6, 0)
            """,
            user_msg_id, session_id, user_id, transcript, content_parts, seq,
        )
        await conn.execute(
            "UPDATE chat_sessions SET message_count = message_count + 1, updated_at = now() WHERE session_id = $1",
            session_id,
        )

    # ── Step 3: LLM stream + TTS pipeline ────────────────────────────
    # Load session settings (same as stream_response)
    session_row = await pool.fetchrow(
        "SELECT system_prompt, generation_params FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    system_prompt = session_row["system_prompt"] if session_row else None
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}

    # Build message history
    rows = await pool.fetch(
        """
        SELECT role, content FROM chat_messages
        WHERE session_id=$1 AND is_error=false AND branch_id=0
        ORDER BY sequence_num DESC LIMIT 50
        """,
        session_id,
    )
    messages: list[dict] = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # Inject system prompts
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    # Voice system prompt (Layer 0) — always for voice
    messages.insert(
        max(len(messages) - 1, 0),
        {"role": "system", "content": VOICE_SYSTEM_PROMPT},
    )

    # Resolve model
    api_key, base_url, model_string, use_openai_sdk = _resolve_model(creds)

    full_content: list[str] = []
    msg_id = str(uuid4())
    stream_start = time.monotonic()
    ttft: float | None = None
    sentence_index = 0
    skipped_count = 0
    # Collect audio segments during streaming — upload AFTER assistant message is saved (FK requirement)
    pending_segments: list[tuple[int, str, bytes]] = []  # (index, text, audio_data)

    try:
        if use_openai_sdk:
            chunk_stream = _stream_openai_compatible(model_string, messages, api_key, base_url, gen_params)
        else:
            chunk_stream = _stream_litellm(model_string, messages, api_key, base_url, gen_params)

        async for chunk_data in chunk_stream:
            content = chunk_data["content"]
            reasoning = chunk_data.get("reasoning_content", "")

            if ttft is None and (content or reasoning):
                ttft = (time.monotonic() - stream_start) * 1000

            # Stream text deltas (same as text chat)
            if reasoning:
                yield _sse("reasoning-delta", {"delta": reasoning})
            if content:
                full_content.append(content)
                yield _sse("text-delta", {"delta": content})

                # Buffer sentences → normalize → TTS
                for sentence in sentence_buffer.push(content):
                    speakable, was_skipped = normalizer.normalize(sentence)
                    if was_skipped:
                        yield _sse("audio-skip", {
                            "sentenceIndex": sentence_index,
                            "reason": "Code shown above, not read aloud",
                            "text": sentence[:60],
                        })
                        skipped_count += 1
                        sentence_index += 1
                        continue

                    # Generate TTS + stream audio chunks
                    audio_chunks: list[bytes] = []
                    try:
                        async for event, raw in _generate_tts_chunks(
                            speakable, user_id, tts_model_source, tts_model_ref, tts_voice, tts_model_name, sentence_index,
                        ):
                            yield _sse("audio-chunk", event)
                            if raw:
                                audio_chunks.append(raw)
                    except Exception:
                        logger.warning("TTS failed for sentence %d", sentence_index, exc_info=True)

                    # Collect audio for upload after message is saved (FK constraint)
                    if audio_chunks:
                        pending_segments.append((sentence_index, speakable, b"".join(audio_chunks)))

                    sentence_index += 1

        # Flush remaining buffer
        remaining = sentence_buffer.flush()
        if remaining:
            speakable, was_skipped = normalizer.normalize(remaining)
            if not was_skipped:
                audio_chunks = []
                try:
                    async for event, raw in _generate_tts_chunks(
                        speakable, user_id, tts_model_source, tts_model_ref, tts_voice, tts_model_name, sentence_index,
                    ):
                        yield _sse("audio-chunk", event)
                        if raw:
                            audio_chunks.append(raw)
                except Exception:
                    logger.warning("TTS failed for final sentence %d", sentence_index, exc_info=True)

                if audio_chunks:
                    pending_segments.append((sentence_index, speakable, b"".join(audio_chunks)))
                sentence_index += 1
            else:
                skipped_count += 1

        # ── Step 4: Save assistant message ───────────────────────────
        response_time_ms = (time.monotonic() - stream_start) * 1000
        final_text = "".join(full_content)

        async with pool.acquire() as conn:
            seq = await conn.fetchval(
                "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages WHERE session_id=$1 AND branch_id=0",
                session_id,
            )
            parts = {
                "response_time_ms": round(response_time_ms),
                "time_to_first_token_ms": round(ttft) if ttft else None,
                "voice_tts_sentences": sentence_index,
                "voice_tts_skipped": skipped_count,
                "voice_tts_voice": tts_voice,
            }
            await conn.execute(
                """
                INSERT INTO chat_messages
                  (message_id, session_id, owner_user_id, role, content, content_parts,
                   sequence_num, model_ref, branch_id)
                VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7, 0)
                """,
                msg_id, session_id, user_id, final_text, json.dumps(parts), seq, model_ref,
            )
            await conn.execute(
                "UPDATE chat_sessions SET message_count=message_count+1, last_message_at=now(), updated_at=now() WHERE session_id=$1",
                session_id,
            )

        # Upload audio segments AFTER message is saved (FK: message_audio_segments → chat_messages)
        if pending_segments:
            upload_tasks = [
                asyncio.create_task(
                    _upload_audio_segment(pool, session_id, msg_id, user_id, idx, text, data)
                )
                for idx, text, data in pending_segments
            ]
            await asyncio.gather(*upload_tasks, return_exceptions=True)

        # Voice data event
        yield _sse("voice-data", {"messageId": msg_id, "segmentCount": sentence_index})

        # Finish event
        yield _sse("finish-message", {
            "finishReason": "stop",
            "usage": {"promptTokens": 0, "completionTokens": 0},
            "timing": {
                "responseTimeMs": round(response_time_ms),
                "timeToFirstTokenMs": round(ttft) if ttft else None,
                "sttMs": stt_ms,
            },
        })

        # Billing (background)
        asyncio.create_task(
            billing.log_usage(
                user_id=user_id,
                model_source=model_source,
                model_ref=model_ref,
                provider_kind=creds.provider_kind,
                input_tokens=0,
                output_tokens=0,
                session_id=session_id,
                message_id=msg_id,
                input_payload={"voice_transcript": transcript},
                output_payload={"content": final_text},
            )
        )

        # Voice analytics event (background)
        asyncio.create_task(emit_voice_turn(
            user_id=user_id, session_id=session_id, stt_success=True,
            stt_duration_ms=stt_ms, speech_duration_ms=speech_duration_ms,
            llm_first_token_ms=round(ttft) if ttft else None,
            threshold_silence_frames=vad_silence_frames,
            threshold_min_duration_ms=vad_min_duration_ms,
        ))

    except Exception as exc:
        logger.exception("Voice stream error for session %s", session_id)
        yield _sse("error", {"errorText": "An error occurred during voice response."})

    yield "data: [DONE]\n\n"


async def generate_tts_for_message(
    session_id: str,
    message_id: str,
    user_id: str,
    tts_model_source: str,
    tts_model_ref: str,
    tts_voice: str,
    pool: asyncpg.Pool,
) -> AsyncGenerator[str, None]:
    """Generate TTS for an existing assistant message. Stores audio in S3.

    Used by Voice Assist mode: text chat already happened, now add TTS after the fact.
    Reuses the same TTS pipeline as voice_stream_response (sentence buffer, normalizer,
    _generate_tts_chunks, _upload_audio_segment).
    """
    # Read message content
    row = await pool.fetchrow(
        "SELECT content, role, content_parts FROM chat_messages WHERE message_id=$1 AND session_id=$2 AND owner_user_id=$3",
        message_id, session_id, user_id,
    )
    if not row:
        yield _sse("error", {"errorText": "Message not found"})
        yield "data: [DONE]\n\n"
        return
    if row["role"] != "assistant":
        yield _sse("error", {"errorText": "TTS only available for assistant messages"})
        yield "data: [DONE]\n\n"
        return

    # Idempotency: skip if TTS already generated for this message
    existing_parts = row["content_parts"] or {}
    if isinstance(existing_parts, str):
        existing_parts = json.loads(existing_parts)
    if existing_parts.get("voice_tts_sentences", 0) > 0:
        yield _sse("finish-tts", {"totalSentences": existing_parts["voice_tts_sentences"], "messageId": message_id, "cached": True})
        yield "data: [DONE]\n\n"
        return

    content = row["content"] or ""
    if len(content.strip()) < 5:
        yield _sse("error", {"errorText": "Message too short for TTS"})
        yield "data: [DONE]\n\n"
        return

    # Resolve TTS model
    provider = get_provider_client()
    try:
        tts_creds = await provider.resolve(tts_model_source, tts_model_ref, user_id)
        tts_model_name = tts_creds.provider_model_name
    except Exception:
        logger.exception("TTS model resolution failed for %s", tts_model_ref)
        yield _sse("error", {"errorText": "TTS model not found. Check Voice Settings."})
        yield "data: [DONE]\n\n"
        return

    # Split into sentences, normalize, generate TTS
    normalizer = TextNormalizer()
    sentence_buffer = SentenceBuffer(clause_mode=False)
    sentence_index = 0
    pending_segments: list[tuple[int, str, bytes]] = []

    try:
        # Feed entire content through sentence buffer
        for sentence in sentence_buffer.push(content):
            speakable, was_skipped = normalizer.normalize(sentence)
            if was_skipped:
                yield _sse("audio-skip", {
                    "sentenceIndex": sentence_index,
                    "reason": "Code shown above, not read aloud",
                    "text": sentence[:60],
                })
                sentence_index += 1
                continue

            audio_chunks: list[bytes] = []
            try:
                async for event, raw in _generate_tts_chunks(
                    speakable, user_id, tts_model_source, tts_model_ref, tts_voice, tts_model_name, sentence_index,
                ):
                    yield _sse("audio-chunk", event)
                    if raw:
                        audio_chunks.append(raw)
            except Exception:
                logger.warning("TTS failed for sentence %d", sentence_index, exc_info=True)

            if audio_chunks:
                pending_segments.append((sentence_index, speakable, b"".join(audio_chunks)))
            sentence_index += 1

        # Flush remaining
        remaining = sentence_buffer.flush()
        if remaining:
            speakable, was_skipped = normalizer.normalize(remaining)
            if not was_skipped:
                audio_chunks = []
                try:
                    async for event, raw in _generate_tts_chunks(
                        speakable, user_id, tts_model_source, tts_model_ref, tts_voice, tts_model_name, sentence_index,
                    ):
                        yield _sse("audio-chunk", event)
                        if raw:
                            audio_chunks.append(raw)
                except Exception:
                    logger.warning("TTS failed for final sentence %d", sentence_index, exc_info=True)

                if audio_chunks:
                    pending_segments.append((sentence_index, speakable, b"".join(audio_chunks)))
                sentence_index += 1

        # Upload audio segments to S3
        if pending_segments:
            upload_tasks = [
                asyncio.create_task(
                    _upload_audio_segment(pool, session_id, message_id, user_id, idx, text, data)
                )
                for idx, text, data in pending_segments
            ]
            await asyncio.gather(*upload_tasks, return_exceptions=True)

        # Update content_parts with TTS info
        await pool.execute(
            """
            UPDATE chat_messages
            SET content_parts = COALESCE(content_parts, '{}'::jsonb) || $1::jsonb
            WHERE message_id = $2
            """,
            json.dumps({"voice_tts_sentences": sentence_index, "voice_tts_voice": tts_voice}),
            message_id,
        )

        yield _sse("finish-tts", {"totalSentences": sentence_index, "messageId": message_id})

    except Exception:
        logger.exception("TTS generation failed for message %s", message_id)
        yield _sse("error", {"errorText": "TTS generation failed"})

    yield "data: [DONE]\n\n"
