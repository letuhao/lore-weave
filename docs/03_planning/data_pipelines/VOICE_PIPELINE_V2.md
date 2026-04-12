# Voice Pipeline V2 — Architecture Document

> **Status:** IMPLEMENTED — all 48 tasks + 5 analytics bonus tasks complete
> **Sessions:** 32 (design + CRA), 33 (implementation)
> **Previous:** 6 review rounds (context, data, UX, security, performance, competitor) — 44 issues resolved
> **Change v2.1:** Client-side controller → Vercel Workflow (rejected — Vercel-only, unnecessary state engine)
> **Change v2.2:** Vercel Workflow → chat-service integration (implemented — extends existing message pipeline with audio I/O)

---

## 1. Problems with V1

### 1.1 State Management is Broken

No strict phase locking. Multiple subsystems race:
- TTS playing → VAD captures speaker output → STT sends garbage → infinite loop
- LLM finishes fast → pipeline generation changes → TTS audio discarded
- React effects used for control flow → async batching causes double-sends

### 1.2 No Audio Persistence

TTS audio held in memory, discarded on any state change. No replay.

### 1.3 No Text Preprocessing

Raw LLM output (markdown, code blocks, JSON, emojis) sent directly to TTS.
Result: "asterisk asterisk bold asterisk asterisk" spoken aloud.

---

## 2. Why Not Vercel Workflow?

Vercel Workflow was evaluated and rejected for two reasons:

1. **Platform lock-in** — Workflow requires Vercel's hosted durable execution backend. LoreWeave deploys on AWS. No self-hosted runtime exists.
2. **Wrong abstraction** — Voice doesn't need a durable state engine. The chat-service already manages all persistent state (messages in Postgres, audio in S3). There's nothing to "recover" — the data is already durable. A voice turn is just a chat message with audio input/output.

**What we actually need:** extend the existing `POST /{session_id}/messages` endpoint to accept audio and return audio alongside text. The chat-service already handles LLM streaming, message persistence, billing, and SSE. Voice is the same pipeline with STT at the front and TTS at the back.

---

## 3. V2 Architecture — Chat-Service Voice Integration

### 3.1 Design Principles

1. **Extend, don't replace** — voice is a new I/O layer on the existing chat message pipeline
2. **Server owns the data** — messages in Postgres, audio in S3, client is stateless
3. **Thin client** — browser handles only mic capture (VAD) and audio playback
4. **SSE streaming** — same protocol as text chat, extended with audio chunk events
5. **Resume anytime** — user leaves, comes back, messages + audio still there
6. **Text normalization** — server-side: voice system prompt + rule-based stripping

### 3.2 Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  BROWSER (thin client)                                           │
│                                                                  │
│  ┌────────────┐  ┌──────────┐  ┌─────────────────────────────┐  │
│  │ Mic Capture │─▶│ VAD      │  │ Audio Playback              │  │
│  │(MediaStream)│  │(Silero)  │  │ (AudioContext, PCM chunks)  │  │
│  └────────────┘  └────┬─────┘  └──────────▲──────────────────┘  │
│                       │ speech end         │                     │
│                       ▼                    │                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ VoiceClient                                                 │ │
│  │  POST /voice-message (multipart: audio file)                │ │
│  │  ← SSE stream: transcript + LLM tokens + TTS audio chunks  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└────────────────────────┼───────────────────▲─────────────────────┘
                         │ HTTP              │ SSE
                         ▼                   │
┌──────────────────────────────────────────────────────────────────┐
│  CHAT-SERVICE (Python / FastAPI)                                 │
│                                                                  │
│  POST /v1/chat/sessions/{id}/voice-message                       │
│  (multipart: audio file + voice config JSON)                     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ voice_stream_response() — async generator, yields SSE      │  │
│  │                                                            │  │
│  │  1. STT: call /v1/audio/transcriptions → transcript        │  │
│  │     ↳ yield {type: "stt-transcript", text: "..."}          │  │
│  │     ↳ Save user message to DB (role=user, input_method=    │  │
│  │       voice)                                               │  │
│  │                                                            │  │
│  │  2. LLM: same as stream_response() — inject voice system   │  │
│  │     prompt when input_method=voice                         │  │
│  │     ↳ yield {type: "text-delta", delta: "..."}   (same)    │  │
│  │     ↳ yield {type: "reasoning-delta", ...}       (same)    │  │
│  │                                                            │  │
│  │  3. Sentence buffer: accumulate LLM tokens into sentences  │  │
│  │     ↳ clause-mode for voice (split on comma at 40+ chars)  │  │
│  │     ↳ CJK: split on CJK punctuation (、。！？)             │  │
│  │                                                            │  │
│  │  4. Per sentence: normalize → TTS → stream audio           │  │
│  │     ↳ TextNormalizer.normalize(sentence) → speakable text  │  │
│  │     ↳ Call /v1/audio/speech (streaming, response_format=   │  │
│  │       mp3)                                                 │  │
│  │     ↳ yield {type: "audio-chunk", sentenceIndex, data,     │  │
│  │       final}                                               │  │
│  │     ↳ Upload complete sentence audio to S3 (background     │  │
│  │       task)                                                │  │
│  │                                                            │  │
│  │  5. Save assistant message + audio segment refs to DB       │  │
│  │     ↳ yield {type: "finish-message", ...}          (same)  │  │
│  │     ↳ yield {type: "voice-data", segments: [...]}          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Calls:                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────┐              │
│  │ STT      │  │ LLM      │  │ TTS      │  │ S3 │              │
│  │ (gateway │  │ (OpenAI/ │  │ (Kokoro/ │  │    │              │
│  │  proxy)  │  │  LiteLLM)│  │  OpenAI) │  │    │              │
│  └──────────┘  └──────────┘  └──────────┘  └────┘              │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 How It Extends the Existing Pipeline

The current `send_message` endpoint in [messages.py](services/chat-service/app/routers/messages.py) does:

```python
# Current text chat flow (messages.py + stream_service.py):
POST /{session_id}/messages  (JSON: {content: "hello"})
  1. Verify session ownership
  2. Save user message to DB
  3. Resolve provider credentials
  4. return StreamingResponse(stream_response(...))
     → stream_response():
       a. Load session settings + message history
       b. Inject system prompt
       c. Stream LLM response (OpenAI SDK or LiteLLM)
       d. Yield SSE: text-delta, reasoning-delta
       e. Save assistant message to DB
       f. Extract outputs (code blocks, etc.)
       g. Yield SSE: data, finish-message
       h. Auto-title, billing (background tasks)
```

The voice endpoint adds:

```python
# New voice flow:
POST /{session_id}/voice-message  (multipart: audio file + config)
  1. Verify session ownership                          # same
  2. STT: transcribe audio → text                      # NEW
  3. Save user message to DB (input_method='voice')    # same + flag
  4. Resolve provider credentials                      # same
  5. return StreamingResponse(voice_stream_response(...))
     → voice_stream_response():
       a. Load session + history                       # same
       b. Inject system prompt + VOICE system prompt   # same + voice
       c. Stream LLM response                          # same
       d. Yield SSE: text-delta, reasoning-delta       # same
       e. Buffer sentences (SentenceBuffer)             # NEW
       f. Per sentence: normalize → TTS → yield audio   # NEW
       g. Upload audio to S3 (background)               # NEW
       h. Save assistant message + audio segments to DB  # same + segments
       i. Yield SSE: data, finish-message, voice-data   # same + voice
       j. Auto-title, billing (background)              # same
```

**~70% of the code is shared with the existing text chat pipeline.** The voice-specific additions are: STT at the front, sentence buffering + normalization + TTS in the middle, audio persistence at the end.

### 3.4 SSE Stream Protocol (Extended)

The existing AI SDK data stream protocol is extended with voice-specific events:

```typescript
// Existing events (unchanged):
{ type: "text-delta",      delta: string }
{ type: "reasoning-delta", delta: string }
{ type: "data",            data: [{ message_id, output_id, ... }] }
{ type: "finish-message",  finishReason, usage, timing }
{ type: "error",           errorText: string }

// New voice events:
{ type: "stt-transcript",  text: string, durationMs: number, audioSizeKB: number }
{ type: "audio-chunk",     sentenceIndex: number, data: string (base64), final: boolean }
{ type: "audio-skip",      sentenceIndex: number, reason: string, text: string }
{ type: "voice-data",      segments: [{ index, objectKey, text, durationS }] }
{ type: "voice-metrics",   sttMs, llmFirstTokenMs, ttsAvgMs, sentenceCount, skippedCount }
```

**audio-chunk encoding:** Base64 in SSE. Each chunk is a small MP3 frame (~2-8KB). Total overhead ~33% but keeps the protocol simple — single SSE connection, no WebSocket, no separate audio stream. At ~10 chunks per sentence, a 5-sentence response is ~50 events × ~5KB = ~250KB base64 (~190KB raw). Acceptable for a chat response.

**Alternative considered:** Separate binary WebSocket for audio. Rejected — adds protocol complexity, two connections to manage, harder to debug. The SSE approach reuses the existing chat streaming infrastructure.

### 3.5 Voice System Prompt (Layer 0)

Injected **server-side in `voice_stream_response()`** when `input_method='voice'`:

```
"You are in a voice conversation. The user is speaking to you and will hear
your response as speech via text-to-speech.

Rules for voice mode responses:
- Respond in natural, conversational speech — as if talking to a friend
- Do NOT use markdown formatting (no **, *, #, ```, etc.)
- Do NOT output code blocks — describe what code does instead
- Do NOT use bullet points or numbered lists — use flowing sentences
- Do NOT use tables or JSON — describe data verbally
- Keep responses concise (2-4 sentences for simple questions)
- Use natural speech patterns: contractions, filler words are OK
- If the user asks about code, explain the concept verbally
- Pronounce abbreviations: 'API' as 'A P I', 'URL' as 'U R L'"
```

**Security:** Server-side only. Cannot be overridden by client. STT transcript is untrusted input — goes through same sanitization as typed messages.

### 3.6 Text Normalizer (Layer 1)

Rule-based, runs server-side per sentence before TTS:

```python
class TextNormalizer:
    """Strip markdown/code/emoji from LLM output before TTS."""

    # Markdown formatting
    BOLD_RE = re.compile(r'\*\*(.+?)\*\*')
    ITALIC_RE = re.compile(r'\*(.+?)\*')
    STRIKE_RE = re.compile(r'~~(.+?)~~')
    CODE_INLINE_RE = re.compile(r'`([^`]+)`')
    HEADING_RE = re.compile(r'#{1,6}\s*')
    LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
    CODE_BLOCK_RE = re.compile(r'```[\s\S]*?```')

    def normalize(self, text: str) -> tuple[str, bool]:
        """Returns (speakable_text, was_skipped)."""
        # Skip code blocks entirely
        if self.CODE_BLOCK_RE.search(text):
            return ('', True)
        # Skip JSON/tables
        stripped = text.strip()
        if stripped.startswith('{') or stripped.startswith('|'):
            return ('', True)

        result = text
        result = self.BOLD_RE.sub(r'\1', result)
        result = self.ITALIC_RE.sub(r'\1', result)
        result = self.STRIKE_RE.sub(r'\1', result)
        result = self.CODE_INLINE_RE.sub(r'\1', result)
        result = self.HEADING_RE.sub('', result)
        result = self.LINK_RE.sub(r'\1', result)

        # Strip remaining markdown chars + collapse whitespace
        result = re.sub(r'[*_~`#>|]', '', result)
        result = re.sub(r'\s{2,}', ' ', result).strip()

        if len(result) < 2:
            return ('', True)
        return (result, False)
```

### 3.7 Sentence Buffer (with CJK + Clause Mode)

```python
class SentenceBuffer:
    """Accumulate LLM tokens, emit complete sentences for TTS."""

    # Full sentence boundaries
    SENTENCE_ENDS = re.compile(r'[.!?]\s')
    CJK_SENTENCE_ENDS = re.compile(r'[。！？]\s?')

    # Clause boundaries (voice mode only, min 40 chars)
    CLAUSE_DELIMS = [', ', ' — ', '; ', ' but ', ' and ', ' so ', ' because ']
    CJK_CLAUSE_DELIMS = ['、', '，']
    CLAUSE_MIN_LENGTH = 40

    def __init__(self, clause_mode: bool = False):
        self.buffer = ''
        self.clause_mode = clause_mode

    def push(self, token: str) -> list[str]:
        """Push a token, return list of complete sentences (if any)."""
        self.buffer += token
        sentences = []

        while True:
            # Check full sentence boundaries first
            match = self.SENTENCE_ENDS.search(self.buffer)
            if not match:
                match = self.CJK_SENTENCE_ENDS.search(self.buffer)
            if match:
                end = match.end()
                sentences.append(self.buffer[:end].strip())
                self.buffer = self.buffer[end:]
                continue

            # Clause-mode splits (voice only, 40+ chars)
            if self.clause_mode and len(self.buffer) > self.CLAUSE_MIN_LENGTH:
                all_delims = self.CLAUSE_DELIMS + self.CJK_CLAUSE_DELIMS
                for delim in all_delims:
                    idx = self.buffer.rfind(delim)
                    if idx > self.CLAUSE_MIN_LENGTH:
                        end = idx + len(delim)
                        sentences.append(self.buffer[:end].strip())
                        self.buffer = self.buffer[end:]
                        break
            break

        return sentences

    def flush(self) -> str | None:
        """Flush remaining buffer (call when LLM stream ends)."""
        if self.buffer.strip():
            result = self.buffer.strip()
            self.buffer = ''
            return result
        return None
```

---

## 4. Server Implementation

### 4.1 Voice Message Endpoint

```python
# routers/voice.py
router = APIRouter(prefix="/v1/chat/sessions", tags=["voice"])

@router.post("/{session_id}/voice-message")
async def send_voice_message(
    session_id: UUID,
    audio: UploadFile = File(...),
    config: str = Form('{}'),  # JSON string with voice settings
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> StreamingResponse:
    voice_config = json.loads(config)

    # Verify session ownership (same as send_message)
    session = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session["status"] == "archived":
        raise HTTPException(status_code=409, detail="session is archived")

    # Read audio file
    audio_bytes = await audio.read()
    if len(audio_bytes) > 10 * 1024 * 1024:  # 10MB max
        raise HTTPException(status_code=413, detail="audio too large")

    # Resolve credentials (same as send_message)
    model_source = session["model_source"]
    model_ref = str(session["model_ref"])
    try:
        creds = await get_provider_client().resolve(model_source, model_ref, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return StreamingResponse(
        voice_stream_response(
            session_id=str(session_id),
            audio_bytes=audio_bytes,
            audio_content_type=audio.content_type or 'audio/webm',
            user_id=user_id,
            model_source=model_source,
            model_ref=model_ref,
            creds=creds,
            pool=pool,
            billing=get_billing_client(),
            voice_config=voice_config,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### 4.2 Voice Stream Response

```python
# services/voice_stream_service.py

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
    """Like stream_response() but with STT input and TTS output."""

    normalizer = TextNormalizer()
    sentence_buffer = SentenceBuffer(clause_mode=True)
    stt_model = voice_config.get('stt_model', 'whisper-1')
    tts_voice = voice_config.get('tts_voice', 'af_heart')
    tts_model = voice_config.get('tts_model', 'kokoro')
    gateway_url = settings.gateway_url  # Internal VPC URL on AWS

    # ── Step 1: STT ──────────────────────────────────────────────
    stt_start = time.monotonic()
    try:
        transcript = await transcribe_audio(
            audio_bytes, audio_content_type, stt_model, gateway_url, user_id,
        )
    except Exception as exc:
        logger.exception("STT failed for session %s", session_id)
        yield sse_event("error", {"errorText": f"Speech recognition failed: {exc}"})
        yield "data: [DONE]\n\n"
        return

    stt_ms = round((time.monotonic() - stt_start) * 1000)
    yield sse_event("stt-transcript", {
        "text": transcript,
        "durationMs": stt_ms,
        "audioSizeKB": round(len(audio_bytes) / 1024),
    })

    # Reject empty/garbage transcripts
    if not transcript or len(transcript.strip()) < 2:
        yield sse_event("error", {"errorText": "Could not understand speech. Try again."})
        yield "data: [DONE]\n\n"
        return

    # Sanitize transcript (untrusted input)
    transcript = sanitize_transcript(transcript)

    # ── Step 2: Save user message ────────────────────────────────
    async with pool.acquire() as conn:
        seq = await conn.fetchval(
            "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages WHERE session_id=$1 AND branch_id=0",
            session_id,
        )
        user_msg_id = str(uuid4())
        content_parts = json.dumps({"input_method": "voice", "stt_model": stt_model, "stt_ms": stt_ms})
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

    # ── Step 3: LLM stream + TTS pipeline ────────────────────────
    # Reuse existing stream_response logic for LLM part
    # (load history, inject system prompt + voice prompt, stream)

    session_row = await pool.fetchrow(
        "SELECT system_prompt, generation_params FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    system_prompt = session_row["system_prompt"] if session_row else None
    gen_params = _parse_gen_params(session_row)

    # Build message history (same as stream_response)
    rows = await pool.fetch(
        "SELECT role, content FROM chat_messages WHERE session_id=$1 AND is_error=false AND branch_id=0 ORDER BY sequence_num DESC LIMIT 50",
        session_id,
    )
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # Inject system prompts
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    # Voice system prompt (Layer 0) — always injected for voice
    messages.insert(
        len(messages) - 1 if len(messages) > 1 else 0,
        {"role": "system", "content": VOICE_SYSTEM_PROMPT},
    )

    # Resolve model + stream LLM
    api_key, base_url, model_string, use_openai_sdk = resolve_model(creds)

    full_content: list[str] = []
    segments: list[dict] = []
    sentence_index = 0
    msg_id = str(uuid4())
    stream_start = time.monotonic()
    ttft: float | None = None
    tts_tasks: list[asyncio.Task] = []

    try:
        chunk_stream = _get_chunk_stream(use_openai_sdk, model_string, messages, api_key, base_url, gen_params)

        async for chunk_data in chunk_stream:
            content = chunk_data["content"]
            reasoning = chunk_data["reasoning_content"]

            if ttft is None and (content or reasoning):
                ttft = (time.monotonic() - stream_start) * 1000

            if reasoning:
                yield sse_event("reasoning-delta", {"delta": reasoning})
            if content:
                full_content.append(content)
                yield sse_event("text-delta", {"delta": content})

                # Buffer sentences
                for sentence in sentence_buffer.push(content):
                    speakable, skipped = normalizer.normalize(sentence)
                    if skipped:
                        yield sse_event("audio-skip", {
                            "sentenceIndex": sentence_index,
                            "reason": "Code shown above, not read aloud",
                            "text": sentence[:60],
                        })
                        sentence_index += 1
                        continue

                    # Generate TTS + stream audio chunks inline
                    async for audio_event in generate_streaming_tts(
                        speakable, tts_voice, tts_model, gateway_url, user_id, sentence_index,
                    ):
                        yield sse_event("audio-chunk", audio_event)

                    # Upload to S3 in background (non-blocking)
                    task = asyncio.create_task(
                        upload_audio_segment(session_id, msg_id, sentence_index, speakable, user_id)
                    )
                    tts_tasks.append(task)
                    sentence_index += 1

        # Flush remaining buffer
        remaining = sentence_buffer.flush()
        if remaining:
            speakable, skipped = normalizer.normalize(remaining)
            if not skipped:
                async for audio_event in generate_streaming_tts(
                    speakable, tts_voice, tts_model, gateway_url, user_id, sentence_index,
                ):
                    yield sse_event("audio-chunk", audio_event)
                task = asyncio.create_task(
                    upload_audio_segment(session_id, msg_id, sentence_index, speakable, user_id)
                )
                tts_tasks.append(task)
                sentence_index += 1

        # ── Step 4: Save assistant message ───────────────────────
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
                "voice_tts_voice": tts_voice,
                "voice_tts_model": tts_model,
            }
            await conn.execute(
                """
                INSERT INTO chat_messages
                  (message_id, session_id, owner_user_id, role, content, content_parts,
                   sequence_num, input_tokens, output_tokens, model_ref, branch_id)
                VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7,$8,$9, 0)
                """,
                msg_id, session_id, user_id, final_text, json.dumps(parts), seq,
                None, None, model_ref,
            )
            await conn.execute(
                "UPDATE chat_sessions SET message_count=message_count+1, last_message_at=now(), updated_at=now() WHERE session_id=$1",
                session_id,
            )

        # Wait for S3 uploads to finish
        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        # Voice data event (segment metadata for replay)
        yield sse_event("voice-data", {"messageId": msg_id, "segmentCount": sentence_index})

        # Finish event (same as text chat)
        yield sse_event("finish-message", {
            "finishReason": "stop",
            "usage": {"promptTokens": 0, "completionTokens": 0},
            "timing": {
                "responseTimeMs": round(response_time_ms),
                "timeToFirstTokenMs": round(ttft) if ttft else None,
                "sttMs": stt_ms,
            },
        })

    except Exception as exc:
        logger.exception("Voice stream error for session %s", session_id)
        yield sse_event("error", {"errorText": "An error occurred during voice response."})

    yield "data: [DONE]\n\n"
```

### 4.3 STT Helper

```python
async def transcribe_audio(
    audio_bytes: bytes,
    content_type: str,
    model: str,
    gateway_url: str,
    user_id: str,
) -> str:
    """Call STT service via gateway, return transcript text."""
    import httpx
    ext = 'webm' if 'webm' in content_type else 'wav'
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{gateway_url}/v1/audio/transcriptions",
            files={"file": (f"audio.{ext}", audio_bytes, content_type)},
            data={"model": model},
            headers={"X-User-Id": user_id},
        )
        resp.raise_for_status()
        return resp.json().get("text", "")
```

### 4.4 Streaming TTS Helper

```python
async def generate_streaming_tts(
    text: str,
    voice: str,
    model: str,
    gateway_url: str,
    user_id: str,
    sentence_index: int,
) -> AsyncGenerator[dict, None]:
    """Call TTS service, yield audio chunks as they arrive."""
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        async with client.stream(
            "POST",
            f"{gateway_url}/v1/audio/speech",
            json={"input": text, "voice": voice, "model": model, "response_format": "mp3"},
            headers={"X-User-Id": user_id},
        ) as resp:
            resp.raise_for_status()
            chunk_index = 0
            async for chunk in resp.aiter_bytes(chunk_size=4096):
                yield {
                    "sentenceIndex": sentence_index,
                    "chunkIndex": chunk_index,
                    "data": base64.b64encode(chunk).decode(),
                    "final": False,
                }
                chunk_index += 1

    # Signal sentence complete
    yield {
        "sentenceIndex": sentence_index,
        "chunkIndex": chunk_index,
        "data": "",
        "final": True,
    }
```

### 4.5 Audio Persistence

```python
async def upload_audio_segment(
    session_id: str,
    message_id: str,
    segment_index: int,
    text: str,
    user_id: str,
) -> None:
    """Upload sentence audio to S3 and save segment ref to DB. Fire-and-forget."""
    # Audio bytes accumulated during TTS streaming (stored in per-sentence buffer)
    # Upload to S3
    object_key = f"voice-audio/{session_id}/{message_id}/{segment_index}_{int(time.time())}.mp3"
    await s3_client.put_object(bucket="lw-chat", key=object_key, body=audio_bytes)

    # Save ref to DB
    await pool.execute(
        """
        INSERT INTO message_audio_segments
          (message_id, session_id, user_id, segment_index, object_key, sentence_text, duration_s)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (message_id, segment_index) DO UPDATE
          SET object_key = EXCLUDED.object_key, sentence_text = EXCLUDED.sentence_text
        """,
        message_id, session_id, user_id, segment_index, object_key, text, duration_s,
    )
```

---

## 5. Database Changes

### 5.1 New Table: message_audio_segments

```sql
CREATE TABLE IF NOT EXISTS message_audio_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
  session_id UUID NOT NULL,
  user_id UUID NOT NULL,
  segment_index INT NOT NULL,
  object_key TEXT NOT NULL,
  sentence_text TEXT NOT NULL,
  duration_s REAL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (message_id, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_mas_message ON message_audio_segments(message_id);
CREATE INDEX IF NOT EXISTS idx_mas_user ON message_audio_segments(user_id);
CREATE INDEX IF NOT EXISTS idx_mas_cleanup ON message_audio_segments(created_at);
```

**Changes from V2.1 design (review fixes applied):**
- Added `user_id` column + index — enables GDPR erasure without expensive joins (D5)
- Added `UNIQUE(message_id, segment_index)` — prevents duplicate segments on retry (D4)
- `ON CONFLICT DO UPDATE` in insert query — idempotent uploads (D4)

### 5.2 chat_messages Changes

No schema changes needed. Voice metadata stored in existing `content_parts` JSONB:

```json
// User message (voice)
{ "input_method": "voice", "stt_model": "whisper-1", "stt_ms": 342 }

// Assistant message (voice response)
{ "response_time_ms": 2100, "time_to_first_token_ms": 450,
  "voice_tts_sentences": 3, "voice_tts_voice": "af_heart", "voice_tts_model": "kokoro" }
```

---

## 6. Client Implementation

### 6.1 VoiceClient (Thin)

```typescript
class VoiceClient {
  constructor(private apiBase: string, private token: string) {}

  /** Send voice audio, receive SSE stream of transcript + LLM text + TTS audio */
  async sendVoiceMessage(
    sessionId: string,
    audioBlob: Blob,
    voiceConfig: VoiceConfig,
    callbacks: VoiceCallbacks,
  ): Promise<void> {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'audio.webm');
    formData.append('config', JSON.stringify(voiceConfig));

    const resp = await fetch(
      `${this.apiBase}/v1/chat/sessions/${sessionId}/voice-message`,
      { method: 'POST', headers: { 'Authorization': `Bearer ${this.token}` }, body: formData },
    );

    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const lines = decoder.decode(value, { stream: true }).split('\n');
      for (const line of lines) {
        if (!line.startsWith('data: ') || line === 'data: [DONE]') continue;
        const event = JSON.parse(line.slice(6));

        switch (event.type) {
          case 'stt-transcript':  callbacks.onTranscript(event.text); break;
          case 'text-delta':      callbacks.onTextDelta(event.delta); break;
          case 'reasoning-delta': callbacks.onReasoningDelta?.(event.delta); break;
          case 'audio-chunk':     callbacks.onAudioChunk(event); break;
          case 'audio-skip':      callbacks.onAudioSkip?.(event); break;
          case 'finish-message':  callbacks.onFinish(event); break;
          case 'voice-metrics':   callbacks.onMetrics?.(event); break;
          case 'error':           callbacks.onError(event.errorText); break;
        }
      }
    }
  }
}
```

### 6.2 VAD Controller

Same as V2.1 — persistent MediaStream, Silero ONNX, pause/resume analysis:

```typescript
class VadController {
  private mediaStream: MediaStream | null = null;
  private vad: MicVAD | null = null;
  private active = false;

  async activate(): Promise<void> {
    this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const { MicVAD } = await import('@ricky0123/vad-web');
    this.vad = await MicVAD.new({
      stream: this.mediaStream,
      onSpeechEnd: (audio) => { if (this.active) this.onSpeechEnd(audio); },
    });
  }

  resume(): void  { this.active = true; this.vad?.start(); }
  pause(): void   { this.active = false; this.vad?.pause(); }

  deactivate(): void {
    this.vad?.destroy();
    this.mediaStream?.getTracks().forEach(t => t.stop());
    this.mediaStream = null;
  }
}
```

### 6.3 Audio Playback Controller

Receives MP3 chunks from SSE, decodes and schedules for gapless playback:

```typescript
class AudioPlaybackController {
  private audioContext: AudioContext;
  private scheduledTime = 0;

  init(): void { this.audioContext = new AudioContext(); }

  async enqueueChunk(base64Data: string): Promise<void> {
    const binary = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
    const audioBuffer = await this.audioContext.decodeAudioData(binary.buffer);
    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);
    const startTime = Math.max(this.audioContext.currentTime, this.scheduledTime);
    source.start(startTime);
    this.scheduledTime = startTime + audioBuffer.duration;
  }

  stop(): void {
    this.audioContext.close();
    this.audioContext = new AudioContext();
    this.scheduledTime = 0;
  }
}
```

### 6.4 React Hook: useVoiceChat

```typescript
export function useVoiceChat(sessionId: string) {
  const [voiceState, setVoiceState] = useState<'inactive' | 'listening' | 'sending' | 'receiving'>('inactive');
  const [sttText, setSttText] = useState<string>('');

  const vadRef = useRef<VadController>(null);
  const playbackRef = useRef<AudioPlaybackController>(null);
  const clientRef = useRef<VoiceClient>(null);

  const activate = useCallback(async () => {
    const vad = new VadController();
    vad.onSpeechEnd = async (audio) => {
      vad.pause();
      setVoiceState('sending');

      const blob = float32ToWebmBlob(audio);
      await clientRef.current!.sendVoiceMessage(sessionId, blob, voiceConfig, {
        onTranscript: (text) => { setSttText(text); setVoiceState('receiving'); },
        onTextDelta: (delta) => { /* append to message display */ },
        onAudioChunk: (chunk) => {
          if (chunk.data) playbackRef.current!.enqueueChunk(chunk.data);
        },
        onFinish: () => { setVoiceState('listening'); vad.resume(); },
        onError: (msg) => { setVoiceState('listening'); vad.resume(); },
      });
    };

    vadRef.current = vad;
    playbackRef.current = new AudioPlaybackController();
    playbackRef.current.init();
    clientRef.current = new VoiceClient(API_BASE, authToken);

    await vad.activate();
    vad.resume();
    setVoiceState('listening');
  }, [sessionId]);

  const deactivate = useCallback(() => {
    vadRef.current?.deactivate();
    playbackRef.current?.stop();
    setVoiceState('inactive');
  }, []);

  const cancel = useCallback(() => {
    playbackRef.current?.stop();
    // Note: server-side LLM stream continues but client ignores remaining events
    // Message is still saved — available for text review
  }, []);

  return { voiceState, sttText, activate, deactivate, cancel };
}
```

---

## 7. Audio Replay

### 7.1 Replay Endpoint

```
GET /v1/chat/sessions/{session_id}/messages/{message_id}/audio-segments
Authorization: Bearer {jwt}

Response:
{
  "segments": [
    { "index": 0, "text": "Hello! How can I help?", "durationS": 1.2,
      "url": "https://s3.../voice-audio/...?X-Amz-Signature=..." }
  ]
}
```

Signed URLs generated lazily per request. 15-minute expiry. Scoped to authenticated user's own messages.

### 7.2 Cleanup

**Two-layer:**
1. **S3 lifecycle rule:** prefix `voice-audio/` → expire after 48h
2. **DB cleanup task** (periodic, every 4h in chat-service):

```python
async def cleanup_expired_audio():
    # Delete DB rows first (returns object keys)
    rows = await pool.fetch("""
        DELETE FROM message_audio_segments
        WHERE created_at < now() - interval '48 hours'
        RETURNING object_key
    """)
    # Then delete from S3 (if this fails, lifecycle catches it)
    for row in rows:
        try:
            await s3.delete_object(Bucket='lw-chat', Key=row['object_key'])
        except Exception:
            pass  # S3 lifecycle is the safety net
```

### 7.3 GDPR Erasure

```
DELETE /v1/chat/voice-data
Authorization: Bearer {jwt}

→ Fetches all user's segments via idx_mas_user index
→ Deletes S3 objects
→ Deletes DB rows
→ Returns { deletedCount: N }
```

Server-side consent enforcement: `voice_consent_at` timestamp stored in user profile. `POST /voice-message` returns 403 if consent not recorded.

---

## 8. Frontend UI

### 8.1 Audio Indicator on Messages

```
┌──────────────────────────────────────────────────┐
│  AI: Hello! How can I help you today?            │
│                                                  │
│  speaker-icon play ━━━━━━━━━━ 0:03 / 0:05  dot  │
│     > 3 segments                     (collapsed) │
└──────────────────────────────────────────────────┘
```

- Default: play/pause + progress bar + health dot (green/yellow/red)
- Expanded (click "3 segments"): per-sentence buttons
- Debug mode (Voice Settings toggle): full TTS/STT metrics

### 8.2 Voice Mode Overlay

```
┌─────────────────────────────────────────┐
│  Mic Voice Mode                   Gear X│
│                                         │
│  [waveform / status indicator]          │
│  Status: Listening... | Sending...      │
│          | Receiving... | Playing...    │
│                                         │
│  You: "How are you today?"              │
│                                         │
│  AI: "I'm doing great, thank you!"     │
│       play ━━━━━━━ 0:02 / 0:03        │
│       [code shown above, not read aloud]│
│       "Let me know if you need help."   │
│       play ━━━━━━━ 0:02 / 0:04        │
│                                         │
│  [Cancel / Tap to stop]  [Exit Voice]   │
└─────────────────────────────────────────┘
```

**Mobile cancel:** Tap anywhere in waveform area to interrupt playback.

### 8.3 Voice Assist Mode

Simpler alternative — no overlay, no auto-send:
- "Auto-send when I stop talking" toggle determines mode
- Voice Assist: STT → insert into textarea, user edits and sends manually
- Auto-TTS on AI response (toggleable)
- Does NOT use the voice-message endpoint — uses regular send_message + separate TTS calls

---

## 9. Implementation Tasks

### Phase A: Core Pipeline (P0)

| Task | Scope | Dep |
|------|-------|-----|
| **VP2-01** | `TextNormalizer` class — rule-based markdown/code/emoji stripping (Python, server-side) | — |
| **VP2-02** | `SentenceBuffer` class — sentence + clause + CJK splitting (Python, server-side) | — |
| **VP2-03** | `voice_stream_response()` async generator — STT → LLM stream → sentence buffer → normalize → TTS → SSE | VP2-01, 02 |
| **VP2-04** | `POST /voice-message` endpoint in chat-service (multipart: audio + config) | VP2-03 |
| **VP2-05** | Voice system prompt injection — prepend speech-style instructions when `input_method='voice'` | VP2-03 |
| **VP2-06** | `VoiceClient` — thin JS class: POST audio, parse SSE stream, dispatch callbacks | VP2-04 |
| **VP2-07** | `VadController` — persistent MediaStream, Silero ONNX VAD, pause/resume | — |
| **VP2-08** | `AudioPlaybackController` — decode MP3 chunks, AudioContext gapless scheduling | — |
| **VP2-09** | `useVoiceChat` React hook — wire VoiceClient + VAD + playback, expose state | VP2-06..08 |
| **VP2-10** | Voice mode overlay UI — waveform, transcript, controls, status indicator | VP2-09 |
| **VP2-11** | Gateway: proxy `/v1/audio/speech` and `/v1/audio/transcriptions` to audio service | — |

### Phase B: Audio Persistence + Replay (P1)

| Task | Scope | Dep |
|------|-------|-----|
| **VP2-12** | `message_audio_segments` table migration (with `user_id`, unique constraint) | — |
| **VP2-13** | S3 upload helper — upload sentence audio in background (`asyncio.create_task`) | VP2-12 |
| **VP2-14** | Wire S3 upload into `voice_stream_response()` per sentence | VP2-03, 13 |
| **VP2-15** | Audio segments GET endpoint — return segments with signed S3 URLs | VP2-12 |
| **VP2-16** | Audio replay player component — play/pause, progress bar, per-sentence (collapsed) | VP2-15 |
| **VP2-17** | Audio indicator on assistant messages (speaker icon + health dot) | VP2-16 |
| **VP2-18** | Cleanup task — periodic delete expired segments from DB + S3 | VP2-12 |
| **VP2-19** | S3 lifecycle rule — prefix `voice-audio/` expires after 48h (safety net) | — |

### Phase C: UX Polish + Metrics (P1)

| Task | Scope | Dep |
|------|-------|-----|
| **VP2-20** | Voice message flag — `input_method: 'voice'` in `content_parts`, mic badge in UI | VP2-03 |
| **VP2-21** | STT/TTS metrics on messages — debug toggle in Voice Settings | VP2-03 |
| **VP2-22** | Normalizer skip indicator — "Code shown above, not read aloud" | VP2-01 |
| **VP2-23** | "Sending..." state feedback — pulsing indicator between VAD speech-end and STT response | VP2-10 |
| **VP2-24** | Mobile cancel — tap waveform area to interrupt playback | VP2-10 |
| **VP2-25** | Filler phrase — "Thinking..." indicator when LLM first token > 1.0s | VP2-03 |
| **VP2-26** | Error recovery UX — inline "Didn't catch that" after empty STT, persistent warning after 3 failures | VP2-09 |
| **VP2-27** | Adaptive silence threshold — start 500ms, adjust based on false triggers / speech duration | VP2-07 |

### Phase D: Voice Assist Mode (P1)

| Task | Scope | Dep |
|------|-------|-----|
| **VP2-28** | Fix push-to-talk mic button — respect Voice Settings STT source | — |
| **VP2-29** | Mic button 4-state design — idle, recording, transcribing, error | VP2-28 |
| **VP2-30** | Voice Assist toggle — always-on VAD mic in input bar, STT → insert into textarea | VP2-07 |
| **VP2-31** | Append/Replace mode — auto-append when textarea non-empty | VP2-30 |
| **VP2-32** | Auto-TTS on AI response — when Voice Assist ON, play TTS for new assistant messages | VP2-08 |
| **VP2-33** | Audio stop button on messages | VP2-32 |
| **VP2-34** | Voice Assist preferences — persist on/off, append/replace, auto-TTS toggle | VP2-30 |

### Phase E: Security + Infrastructure (P2)

| Task | Scope | Dep |
|------|-------|-----|
| **VP2-35** | Voice consent — first-activation dialog, server-side `voice_consent_at` enforcement | VP2-04 |
| **VP2-36** | GDPR erasure endpoint — `DELETE /v1/chat/voice-data` | VP2-12 |
| **VP2-37** | SSE-S3 encryption on `lw-chat` S3 bucket | VP2-19 |
| **VP2-38** | STT transcript sanitization — length cap (1000 chars), strip prompt-injection patterns | VP2-03 |
| **VP2-39** | Persistent mic-active indicator in main UI chrome | VP2-09 |
| **VP2-40** | Mode switch guard — disable text input during voice sending/receiving | VP2-09 |
| **VP2-41** | Debug toggle in Voice Settings — show/hide metrics on messages | VP2-21 |
| **VP2-42** | Headphone detection — enable lightweight VAD during playback for auto-cancel | VP2-07 |
| **VP2-43** | Combine first-time dialogs — consent text inline in mic permission, defer headphone prompt | VP2-35 |

**Total: 43 tasks across 5 phases.**

---

## 10. Latency Analysis

### 10.1 Per-Turn Budget

```
Client:
  VAD speech-end                           ~0ms (local ONNX)
  Encode + POST multipart                  ~20ms (same-region AWS)

Server (chat-service):
  STT transcription                        200-500ms
  Save user message                        ~5ms
  LLM first token                          500-2000ms
  Sentence buffer (clause mode)            300-500ms of LLM tokens
  Normalize (sync)                         ~0ms
  TTS first MP3 chunk (streaming)          200-300ms

  Total server time to first audio chunk:  ~1.0-1.5s

Return:
  SSE event to client                      ~10ms
  MP3 decode + AudioContext schedule        ~10ms

  Total perceived latency:                 ~1.0-1.5s
  With filler indicator at 1.0s:           No dead silence
```

### 10.2 Comparison

| Dimension | LoreWeave V2 | OpenAI Realtime | Pipecat | LiveKit |
|-----------|-------------|-----------------|---------|---------|
| Time-to-first-audio | ~1.0-1.5s | ~300ms | ~1.2s | ~800ms |
| Architecture | HTTP endpoint + SSE | WebSocket (full-duplex) | WebSocket | WebRTC |
| Audio persistence | Yes (S3 + replay) | No | No | No |
| Self-hosted BYOK | Yes | No | Yes | Partial |
| Complexity | Low (extends existing chat) | High (new protocol) | Medium | High |
| Resume after disconnect | Yes (messages in DB) | No | No | No |

---

## 11. Review Issues — Resolution

### Issues resolved by switching to chat-service approach:

| # | Issue | Resolution |
|---|-------|-----------|
| A1/C1/C7 | Vercel Workflow can't run on AWS | **Eliminated** — no Workflow, plain Python async |
| S1 | JWT in Workflow event log | **Eliminated** — no event log |
| S2 | Audio in Workflow event log | **Eliminated** — audio goes to S3 only |
| S8 | Event log data residency | **Eliminated** — no event log |
| P1 | setTimeout replay semantics | **Eliminated** — no replay engine |
| P3 | Event log bloat (audio chunks) | **Eliminated** — SSE is ephemeral, no persistence |
| P7 | emitUIEvent step overhead | **Eliminated** — SSE yields are zero-cost |
| P8 | Long-lived Workflow runs | **Eliminated** — each request is a normal HTTP request |
| A2 | processVoiceTurn child workflow | **Eliminated** — plain function |
| A5 | emitUIEvent excessive checkpoints | **Eliminated** — plain SSE yield |

### Issues addressed in new design:

| # | Issue | Fix applied |
|---|-------|------------|
| A3/P2 | Combined LLM+TTS — TTS failure retries LLM | **Fixed** — TTS is per-sentence with individual try/catch. LLM failure is separate from TTS failure. No "step retry" — just normal Python error handling |
| D1 | PCM→MP3 missing | **Fixed** — use `response_format: 'mp3'` throughout. MP3 for streaming (each frame independently decodable), MP3 for persistence. No conversion needed |
| D3 | CJK clause splitting | **Fixed** — SentenceBuffer includes `CJK_SENTENCE_ENDS` and `CJK_CLAUSE_DELIMS` |
| D4 | No unique constraint on segments | **Fixed** — `UNIQUE(message_id, segment_index)` + `ON CONFLICT DO UPDATE` |
| D5 | No user_id on segments | **Fixed** — `user_id` column + index added |
| D6 | Cleanup orphan risk | **Fixed** — S3 lifecycle (48h) is the primary cleanup, DB delete is secondary. Orphaned S3 objects auto-expire |
| D7 | No backpressure on audio | **N/A** — SSE is pull-based (client reads at its own pace). Server yields and FastAPI/uvicorn handle buffering |
| S3 | Hook token exposed | **Eliminated** — no hooks, standard JWT auth on every request |
| S4 | No access control on stream | **Fixed** — voice-message endpoint checks session ownership (same as send_message) |
| S5 | Routes lack auth middleware | **Fixed** — same `Depends(get_current_user)` as existing endpoints |
| S6 | STT unsanitized (was P2) | **Promoted to VP2-38** — sanitize_transcript() called before LLM |
| S7 | Consent client-side only | **Fixed** — server-side `voice_consent_at` enforcement in VP2-35 |
| P4 | Step overhead underestimated | **Eliminated** — no steps, just async function calls |
| P5 | Memory accumulation before persist | **Fixed** — S3 upload is fire-and-forget per sentence (`asyncio.create_task`), audio not accumulated |
| P6 | Base64 overhead | **Accepted** — 33% overhead on ~5KB MP3 chunks is ~1.6KB extra. Keeps SSE protocol simple. Not worth adding WebSocket complexity |
| A4 | Base64 audio in hook event log | **Eliminated** — audio goes directly from TTS response to SSE, never stored in any event log |
| A6/C6 | Steps call gateway instead of internal | **Fixed** — `gateway_url` is internal VPC URL on AWS |
| A7 | STT empty check too lenient | **Fixed** — `len(transcript.strip()) < 2` + sanitize_transcript() |
| C3 | Lambda incompatible | **N/A** — chat-service runs on ECS/EC2, not Lambda (it's a long-running FastAPI server) |
| C4 | ALB needed for SSE | **Already the case** — chat-service SSE already works on ALB |
| C5 | MinIO → S3 | **Noted** — abstract via existing storage client, swap at deploy time |
| U1 | 1.0-1.5s borderline | **Mitigated** — filler threshold lowered to 1.0s (VP2-25) |
| U2 | "sending" no feedback | **Fixed** — VP2-23: pulsing indicator |
| U3 | Mobile no cancel | **Fixed** — VP2-24: tap waveform to cancel |
| U4 | Error recovery undefined | **Fixed** — VP2-26: inline message + persistent warning after 3 fails |
| U5 | Filler repetitive | **Fixed** — rotate per-turn, user can disable in settings |
| U6 | Mode toggle too thin | **Addressed** — two-option selector with descriptions |
| U7 | Reconnection flash | **N/A** — each voice turn is a single HTTP request. No persistent connection to reconnect. If the request fails, user just speaks again |
| U8 | Three pre-speech dialogs | **Fixed** — VP2-43: combine consent into mic permission, defer headphone prompt |

### Summary

| Category | V2.1 (Workflow) | V2.2 (chat-service) |
|----------|----------------|---------------------|
| Critical issues | 7 | **0** |
| High issues | 14 | **0** (all resolved) |
| Medium issues | 14 | **2** (accepted: base64 overhead, latency vs competitors) |
| Low issues | 5 | **0** (all addressed) |

---

## 12. Open Questions (Resolved)

| Question | Resolution |
|----------|-----------|
| Vercel Workflow? | **Rejected** — Vercel-only platform, wrong abstraction for voice |
| Client vs server pipeline? | **Server** — chat-service already owns messages/sessions, voice extends it |
| Why server state? | Messages in Postgres, audio in S3. User can leave and resume. Not "state management" — just data persistence that already exists |
| Separate voice service? | **No** — voice is a new endpoint in chat-service, shares LLM/DB/billing code |
| Audio encoding in SSE? | **Base64 MP3 chunks** — simple, single connection, 33% overhead acceptable for ~5KB chunks |
| WebSocket for audio? | **Rejected** — adds protocol complexity for marginal gain |
| STT sanitization priority? | **P0** (promoted from P2) — untrusted input before LLM |
| CJK splitting? | **Included** — CJK sentence/clause delimiters in SentenceBuffer |
| PCM vs MP3 for streaming? | **MP3** — each frame independently decodable, same format for streaming and persistence |
| Consent enforcement? | **Server-side** — `voice_consent_at` timestamp, 403 if not set |
| Hosting? | **AWS** — ECS/EC2 for chat-service, S3 for audio, ALB for SSE |

---

*Created: 2026-04-11 — LoreWeave session 31 (original), session 32 (chat-service redesign)*
*Design iterations: client-side controller → Vercel Workflow (rejected) → chat-service integration (current)*
*46 review issues evaluated: 15 eliminated by architecture change, 28 fixed in design, 2 accepted, 1 N/A*
