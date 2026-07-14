"""Voice stream service — STT → LLM → TTS pipeline as SSE async generator.

Extends the existing stream_response() pattern with audio input/output.
~70% shared logic with stream_service.py (LLM streaming, message history,
provider resolution, DB persistence).

Phase 5b — STT + TTS routed through the unified LLM gateway via the
loreweave_llm SDK. No more direct `/internal/proxy/v1/audio/*` calls;
no more chat-service-side model-name resolution for stt/tts (the gateway
resolves via `model_ref` → user_model row).

Design refs: VOICE_PIPELINE_V2.md §4.2, LLM_PIPELINE_PHASE5B_DESIGN.md §2.6
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from types import SimpleNamespace
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg

from loreweave_llm import AudioChunkEvent, Client, DoneEvent, SttResult

from app.client.auth_client import resolve_local_date
from app.client.billing_client import BillingClient
from app.client.knowledge_client import get_knowledge_client
from app.client.provider_client import get_provider_client
from app.config import settings
from app.events.voice_events import emit_voice_turn
from app.models import ProviderCredentials
from app.services.injection_defense import neutralize_injection
from app.services.sentence_buffer import SentenceBuffer
from app.services.text_normalizer import TextNormalizer
from app.services.stream_service import _stream_via_gateway
from app.services.working_memory import resolve_anchor
from app.storage.minio_client import upload_file
from loreweave_context import build_system_message

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


def _new_llm_client(user_id: str) -> Client:
    """Per-call SDK client (mirrors stream_service.py pattern). httpx pool
    init cost is the trade-off; consistency with sibling-service pattern
    matters more for reviewability. If profiling ever shows the pool init
    as hot, lift to a singleton with rationale.
    """
    return Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
        idle_read_timeout_s=settings.llm_stream_idle_read_timeout_s,
    )


async def _transcribe_audio(
    audio_bytes: bytes,
    content_type: str,
    user_id: str,
    stt_model_source: str,
    stt_model_ref: str,
) -> tuple[str, int]:
    """Phase 5b — call STT via unified LLM gateway (bytes mode). Returns
    (transcript, duration_ms). Gateway resolves the upstream model name
    via `stt_model_ref` → user_model row, so the caller doesn't need
    `stt_model_name` anymore.
    """
    start = time.monotonic()
    client = _new_llm_client(user_id)
    try:
        result: SttResult = await client.transcribe(
            audio_bytes,
            model_source=stt_model_source,
            model_ref=stt_model_ref,
            content_type=content_type,
            language="auto",
        )
    finally:
        await client.aclose()
    duration_ms = round((time.monotonic() - start) * 1000)
    return result.text, duration_ms


async def _generate_tts_chunks(
    text: str,
    user_id: str,
    tts_model_source: str,
    tts_model_ref: str,
    tts_voice: str,
    sentence_index: int,
) -> AsyncGenerator[tuple[dict, bytes], None]:
    """Phase 5b — call TTS via unified LLM gateway (SSE stream). Yields
    (sse_event, raw_bytes) per audio chunk, preserving the existing FE
    envelope shape (sentenceIndex/chunkIndex/data/final) by wrapping
    each gateway AudioChunkEvent. The gateway resolves the upstream model
    name via `tts_model_ref` — caller doesn't supply `tts_model_name`.
    """
    chunk_index = 0
    client = _new_llm_client(user_id)
    try:
        async for ev in client.stream_tts(
            text=text,
            model_source=tts_model_source,
            model_ref=tts_model_ref,
            voice=tts_voice,
            format="mp3",
        ):
            if isinstance(ev, AudioChunkEvent):
                raw = base64.b64decode(ev.data) if ev.data else b""
                # Preserve existing FE envelope (sentenceIndex/chunkIndex/
                # data/final). Gateway is sentence-agnostic; chat-service
                # owns sentence semantics above this layer.
                event = {
                    "sentenceIndex": sentence_index,
                    "chunkIndex": chunk_index,
                    "data": ev.data,  # already base64
                    "final": ev.final,
                }
                yield event, raw
                chunk_index += 1
            elif isinstance(ev, DoneEvent):
                # Gateway signaled end-of-stream. Loop terminates; the
                # final emit with final=True has already been yielded
                # above (from the AudioChunkEvent with final=True per
                # the openai adapter's closing emit).
                break
    finally:
        await client.aclose()


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

    # Phase 5b — STT/TTS upstream model-name resolution moved to the
    # gateway. We just validate the caller-supplied stt_model_ref is
    # non-empty here; deeper validation (does the model exist?) happens
    # gateway-side and surfaces via the SDK as LLMModelNotFound (mapped
    # to the FE-friendly "STT model not found" error).
    if not stt_model_ref:
        yield _sse("error", {"errorText": "STT model not configured. Check Voice Settings."})
        yield "data: [DONE]\n\n"
        return

    # Track voice config for analytics
    vad_silence_frames = voice_config.get("vad_silence_frames", 8)
    vad_min_duration_ms = voice_config.get("vad_min_duration_ms", 500)
    speech_duration_ms = voice_config.get("speech_duration_ms")
    audio_size_kb = round(len(audio_bytes) / 1024)

    # ── Step 1: STT ──────────────────────────────────────────────────
    try:
        transcript, stt_ms = await _transcribe_audio(
            audio_bytes, audio_content_type, user_id,
            stt_model_source, stt_model_ref,
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
    # DBT-11 — resolve the local day before acquiring the conn (auth call on cache miss).
    _local_date = await resolve_local_date(user_id)
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
              (message_id, session_id, owner_user_id, role, content, content_parts, sequence_num, branch_id, local_date)
            VALUES ($1,$2,$3,'user',$4,$5::jsonb,$6, 0, $7)
            """,
            user_msg_id, session_id, user_id, transcript, content_parts, seq,
            _local_date,  # DBT-11 — bucket by the user's LOCAL day (resolved before acquire)
        )
        await conn.execute(
            "UPDATE chat_sessions SET message_count = message_count + 1, updated_at = now() WHERE session_id = $1",
            session_id,
        )

    # ── Step 3: LLM stream + TTS pipeline ────────────────────────────
    # Load session settings (same as stream_response)
    session_row = await pool.fetchrow(
        "SELECT system_prompt, generation_params, project_id, project_ids, working_memory_seed, session_kind FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    system_prompt = session_row["system_prompt"] if session_row else None
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}
    # Resolve the session-stored reasoning pref to WIRE fields (review-impl H):
    # raw "off"/"auto" crashes StreamRequest validation. Voice has no creds in
    # scope (the gateway resolves the model) → creds=None conservative control.
    from app.services.stream_service import _resolve_and_stash_reasoning

    _resolve_and_stash_reasoning(gen_params, None)
    project_id = session_row.get("project_id") if session_row else None
    # Track B B1(2) — multi-KG: same effective-target resolution as the text path.
    from app.services.stream_service import resolve_grounding_target
    _build_project_id, _build_project_ids = resolve_grounding_target(
        session_row, str(project_id) if project_id else None,
    )

    # ── K5: build memory block via knowledge-service ────────────────────────
    # Voice mode benefits from memory just like text mode. Failures
    # degrade silently inside the client.
    knowledge_client = get_knowledge_client()
    kctx = await knowledge_client.build_context(
        user_id=user_id,
        session_id=session_id,
        project_id=_build_project_id,
        project_ids=_build_project_ids,
        message=transcript,
    )

    # ── P0-5 (audit Area 3, SEC-4 / ML-4) — neutralize indirect prompt-injection
    # in the retrieved knowledge block before it is spliced into the voice system
    # prompt (same untrusted-data defense as the text path). Multilingual-safe;
    # clean text unchanged. The user's transcript + session persona are NOT touched.
    kctx.context = neutralize_injection(kctx.context)

    # ── Anchoring (interview-roleplay) — same shared helper as the text path so
    # the 2h voice session (the real use) gets the anchor too (EC-3).
    wm_pinned, wm_tail = resolve_anchor(
        kctx.working_memory,
        session_row.get("working_memory_seed") if session_row else None,
    )
    # P0-5 — sanitize the rendered roleplay anchor (untrusted state) too.
    wm_pinned = neutralize_injection(wm_pinned)
    wm_tail = neutralize_injection(wm_tail)

    # Build message history sized by knowledge_service
    history_limit = max(1, kctx.recent_message_count)
    rows = await pool.fetch(
        """
        SELECT role, content FROM chat_messages
        WHERE session_id=$1 AND is_error=false AND branch_id=0
        ORDER BY sequence_num DESC LIMIT $2
        """,
        session_id, history_limit,
    )
    messages: list[dict] = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # Compose the system prompt: memory → anchor → session prompt (K5-I3: each part
    # stripped so trailing newlines don't stack into triple-newline runs). T3.4 — the
    # shared kernel renderer (plain path, no cache, no skills/steering — voice is a
    # minimal surface), retiring the byte-copy of chat's assembly ladder. VOICE_SYSTEM_PROMPT
    # + wm_tail are inserted separately below (they are their own messages, not this block).
    _voice_system = build_system_message(
        use_cache=False,
        kctx_context=kctx.context,
        kctx_stable="",
        kctx_volatile="",
        wm_pinned=wm_pinned,
        system_prompt=system_prompt,
        tail_blocks=[],
    )
    if _voice_system:
        messages.insert(0, {"role": "system", "content": _voice_system})

    # Voice system prompt (Layer 0) — always for voice
    messages.insert(
        max(len(messages) - 1, 0),
        {"role": "system", "content": VOICE_SYSTEM_PROMPT},
    )

    # Tail anchor (recency) — closest to the latest user turn (EC-3/EC-7).
    if wm_tail:
        messages.insert(max(len(messages) - 1, 0), {"role": "system", "content": wm_tail})

    # Phase 1c-ii: gateway resolves api_key / base_url / model_string
    # internally — no per-service resolution needed.
    full_content: list[str] = []
    msg_id = str(uuid4())
    stream_start = time.monotonic()
    ttft: float | None = None
    # WS-4.2a — the LLM UsageEvent arrives on the trailing chunk from
    # `_stream_via_gateway`; voice used to DISCARD it and bill 0/0. Capture it so
    # both the DB row AND the SSE `finish-message` the FE reads carry real tokens.
    last_usage = None
    tts_chars = 0  # WS-4.2b — TTS is metered by CHARACTERS spoken (not tokens)
    sentence_index = 0
    skipped_count = 0
    # Collect audio segments during streaming — upload AFTER assistant message is saved (FK requirement)
    pending_segments: list[tuple[int, str, bytes]] = []  # (index, text, audio_data)

    try:
        # WS-4.1-tools — voice consumes the SHARED tool-capable generator (_stream_with_tools),
        # not the raw gateway stream, so a voice turn can call memory/recall tools mid-response
        # (the sealed "shared inner generator"). Blast radius is contained: this is a NEW caller,
        # _stream_with_tools is unchanged. permission_mode='ask' — a spoken turn may READ (recall)
        # but never fire a destructive write mid-speech (no client confirm loop exists for voice).
        # A tool set fetch failure degrades to NO tools (voice still answers), never breaks the turn.
        from app.services.stream_service import _stream_with_tools
        try:
            _voice_tools = await knowledge_client.get_tool_definitions(user_id=user_id)
        except Exception:
            logger.warning("voice tool-surface fetch failed; proceeding tool-free", exc_info=True)
            _voice_tools = []
        chunk_stream = _stream_with_tools(
            model_source=model_source,
            model_ref=model_ref,
            user_id=user_id,
            messages=messages,
            gen_params=gen_params,
            tools=_voice_tools,
            knowledge_client=knowledge_client,
            session_id=session_id,
            project_id=_build_project_id,
            permission_mode="ask",
        )

        async for chunk_data in chunk_stream:
            # WS-4.1-tools — robust chunk handling: _stream_with_tools yields tool_call /
            # suspend / agent_surface chunks that carry NO 'content' key (the KeyError the
            # sealed decision flags). A tool_call is surfaced as an SSE event but never spoken;
            # suspend/agent_surface are inapplicable to a voice turn (no client resume) → skipped.
            content = chunk_data.get("content", "")
            reasoning = chunk_data.get("reasoning_content", "")
            # WS-4.2a — the trailing chunk carries usage (content=="" so it skips
            # the TTS path below); keep the last non-null one for billing.
            if chunk_data.get("usage") is not None:
                last_usage = chunk_data["usage"]
            # WS-4.1-tools cold-review H1 — a SUSPEND ends the generator with NO terminal usage
            # chunk (a paid Tier-R read or a frontend tool suspends even in 'ask' mode). Voice has
            # no client resume loop, so: BILL the tokens the suspend payload carries (not 0/0 — the
            # exact WS-4.2a mis-bill, re-created on this path) and surface an explicit error instead
            # of a silent half-turn. Then fall through to save/finish with the REAL usage.
            _susp = chunk_data.get("suspend")
            if _susp:
                last_usage = SimpleNamespace(
                    prompt_tokens=int(_susp.get("input_tokens", 0) or 0),
                    completion_tokens=int(_susp.get("output_tokens", 0) or 0),
                )
                yield _sse("error", {"errorText": "That needs a confirmation I can't do by voice — try it in text chat."})
                break
            _tc = chunk_data.get("tool_call")
            if _tc:
                yield _sse("tool-call", {"tool": _tc.get("name") or _tc.get("tool") or "tool"})
                continue  # a tool_call chunk has no speakable content

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
                            speakable, user_id, tts_model_source, tts_model_ref, tts_voice, sentence_index,
                        ):
                            yield _sse("audio-chunk", event)
                            if raw:
                                audio_chunks.append(raw)
                    except Exception:
                        logger.warning("TTS failed for sentence %d", sentence_index, exc_info=True)

                    # Collect audio for upload after message is saved (FK constraint)
                    if audio_chunks:
                        pending_segments.append((sentence_index, speakable, b"".join(audio_chunks)))
                        tts_chars += len(speakable)  # WS-4.2b — meter TTS by chars spoken

                    sentence_index += 1

        # Flush remaining buffer
        remaining = sentence_buffer.flush()
        if remaining:
            speakable, was_skipped = normalizer.normalize(remaining)
            if not was_skipped:
                audio_chunks = []
                try:
                    async for event, raw in _generate_tts_chunks(
                        speakable, user_id, tts_model_source, tts_model_ref, tts_voice, sentence_index,
                    ):
                        yield _sse("audio-chunk", event)
                        if raw:
                            audio_chunks.append(raw)
                except Exception:
                    logger.warning("TTS failed for final sentence %d", sentence_index, exc_info=True)

                if audio_chunks:
                    pending_segments.append((sentence_index, speakable, b"".join(audio_chunks)))
                    tts_chars += len(speakable)  # WS-4.2b — meter TTS by chars spoken
                sentence_index += 1
            else:
                skipped_count += 1

        # ── Step 4: Save assistant message ───────────────────────────
        response_time_ms = (time.monotonic() - stream_start) * 1000
        final_text = "".join(full_content)
        # WS-4.2a — real LLM token counts (0 only if the provider reported none).
        input_tokens = int(getattr(last_usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(last_usage, "completion_tokens", 0) or 0)

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
                   sequence_num, model_ref, branch_id, local_date)
                VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7, 0, $8)
                """,
                msg_id, session_id, user_id, final_text, json.dumps(parts), seq, model_ref,
                _local_date,  # DBT-11 — same turn as the user msg above (resolved before acquire)
            )
            await conn.execute(
                "UPDATE chat_sessions SET message_count=message_count+1, last_message_at=now(), updated_at=now() WHERE session_id=$1",
                session_id,
            )

        # WS-4.1 — canon auto-capture on voice turns (the gap the WS-4.5 stopgap worked
        # around). Mirrors the text path's post-turn block (stream_service._emit_chat_turn):
        # resolve the session's book from its project, build the SAME CaptureContext, fire
        # maybe_capture_canon + persist the decision. Self-gates — a bookless / off-cadence /
        # too-short turn returns fire=False WITH a reason (so the home strip shows capture
        # visibly OFF, never a silent drop). Replaces the WS-4.5 'voice_path_unsupported'
        # stopgap now that capture actually runs on a voice turn.
        try:
            from app.services.canon_capture import (
                CaptureContext, maybe_capture_canon, persist_capture_status,
            )
            _cap_book_id = None
            if _build_project_id:
                _cap_book_id = await knowledge_client.resolve_book_id(
                    user_id=user_id, project_id=str(_build_project_id),
                )
            _cap_decision = maybe_capture_canon(
                ctx=CaptureContext(
                    book_id=_cap_book_id,
                    project_enables=kctx.canon_capture_enabled,
                    grounding_enabled=True,  # voice always builds a knowledge context
                ),
                user_id=str(user_id),
                assistant_turn_count=seq,
                user_message=transcript,
                assistant_message=final_text,
                model_ref=model_ref if model_source == "user_model" else None,
            )
            await persist_capture_status(pool, session_id, _cap_decision)
        except Exception:
            logger.warning("voice canon capture failed for session %s", session_id, exc_info=True)

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
            "usage": {"promptTokens": input_tokens, "completionTokens": output_tokens},
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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                session_id=session_id,
                message_id=msg_id,
                input_payload={"voice_transcript": transcript},
                output_payload={"content": final_text},
            )
        )

        # WS-4.2b — STT + TTS usage plumbing. These were previously DISCARDED (the day was
        # metered by the LLM half only). Record them under distinct lanes with their real
        # metering unit (STT = audio-seconds, TTS = characters) in the payload; token fields
        # stay 0 so a token-priced cost is NOT faked — precise per-minute/per-char pricing is
        # the billing cost-model follow-on. This makes the STT/TTS usage VISIBLE + auditable.
        # L1 fix — explicit None check (a clip whose ms rounds to 0.0 is falsy and would
        # silently fall to the byte-estimate). M1 fix — provider_kind="" (unknown), NOT
        # creds.provider_kind: `creds` is the CHAT LLM credential; STT/TTS routinely use a
        # different provider (whisper/Kokoro), so stamping the chat provider corrupts any
        # per-provider rollup. model_source/model_ref correctly identify the STT/TTS model.
        if speech_duration_ms:
            _stt_seconds = round(speech_duration_ms / 1000, 2)
        else:
            _stt_seconds = round(audio_size_kb / 16, 2)  # rough proxy (no cost impact; tokens 0)
        asyncio.create_task(billing.log_usage(
            user_id=user_id, model_source=stt_model_source, model_ref=stt_model_ref,
            provider_kind="", input_tokens=0, output_tokens=0,
            session_id=session_id, message_id=msg_id, purpose="voice_stt",
            input_payload={"audio_seconds": _stt_seconds, "audio_kb": audio_size_kb},
            output_payload={"transcript_chars": len(transcript)},
        ))
        if tts_chars > 0 and tts_model_ref:
            asyncio.create_task(billing.log_usage(
                user_id=user_id, model_source=tts_model_source, model_ref=tts_model_ref,
                provider_kind="", input_tokens=0, output_tokens=0,
                session_id=session_id, message_id=msg_id, purpose="voice_tts",
                input_payload={"tts_characters": tts_chars, "tts_voice": tts_voice},
                output_payload={"sentences": sentence_index},
            ))

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

    # Phase 5b — TTS model resolution moved to the gateway. We just
    # require the caller-supplied tts_model_ref is non-empty; "does the
    # model exist?" is decided by the gateway and surfaces via the SDK
    # as LLMModelNotFound (caught in the try-block below for each TTS
    # call).
    if not tts_model_ref:
        yield _sse("error", {"errorText": "TTS model not configured. Check Voice Settings."})
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
                    speakable, user_id, tts_model_source, tts_model_ref, tts_voice, sentence_index,
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
                        speakable, user_id, tts_model_source, tts_model_ref, tts_voice, sentence_index,
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
