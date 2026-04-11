# External AI Service Integration Guide

> **Purpose:** This document tells external developers how to build TTS, STT, Image Generation, or Video Generation services that integrate with LoreWeave's provider-registry system.
>
> **Audience:** AI agents and developers building separate repos for AI services.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [How Provider Registry Works](#2-how-provider-registry-works)
3. [API Standard: OpenAI-Compatible](#3-api-standard-openai-compatible)
4. [Service Contract: Text-to-Speech (TTS)](#4-service-contract-text-to-speech-tts)
5. [Service Contract: Speech-to-Text (STT)](#5-service-contract-speech-to-text-stt)
6. [Service Contract: Image Generation](#6-service-contract-image-generation)
7. [Service Contract: Video Generation](#7-service-contract-video-generation)
8. [Authentication & Credential Flow](#8-authentication--credential-flow)
9. [Capability Flags](#9-capability-flags)
10. [Usage & Billing Integration](#10-usage--billing-integration)
11. [Health Check Contract](#11-health-check-contract)
12. [Model Discovery Contract](#12-model-discovery-contract)
13. [Deployment & Registration](#13-deployment--registration)
14. [Testing Your Service](#14-testing-your-service)
15. [Reference: Existing Adapter Implementations](#15-reference-existing-adapter-implementations)

---

## 1. Architecture Overview

```
┌──────────────┐     ┌───────────────────────┐     ┌─────────────────────┐
│  LoreWeave   │────▶│  provider-registry    │────▶│  YOUR SERVICE       │
│  Frontend    │     │  service              │     │  (separate repo)    │
│              │◀────│                       │◀────│                     │
└──────────────┘     └───────────────────────┘     └─────────────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  usage-      │
                     │  billing     │
                     │  service     │
                     └──────────────┘
```

**Key principle:** LoreWeave's `provider-registry-service` is the central hub. It:
1. Stores user credentials (encrypted) and endpoint URLs
2. Routes AI requests to the correct external service
3. Maps between a standard input format and provider-specific APIs
4. Records usage for billing

**Your service** only needs to expose a standard REST API. LoreWeave handles auth, billing, and routing.

---

## 2. How Provider Registry Works

### User Setup Flow
1. User creates a **Provider Credential** with: `provider_kind`, `endpoint_base_url`, `api_key`
2. User creates a **User Model** linked to the credential with: `provider_model_name`, `capability_flags`
3. When invoking, LoreWeave resolves the credential → decrypts the API key → calls your service

### Invoke Flow (what happens when LoreWeave calls your service)

```
1. Frontend calls:     POST /v1/model-registry/invoke
                       { model_source: "user_model", model_ref: "<user_model_id>", input: {...} }

2. Provider-registry:  Resolves user_model → provider_credential
                       Decrypts API key from secret_ciphertext
                       Resolves adapter by provider_kind

3. Adapter calls:      POST {your_endpoint_base_url}/{path}
                       Authorization: Bearer {decrypted_api_key}
                       Body: provider-specific format

4. Your service:       Processes request, returns response

5. Provider-registry:  Extracts usage (tokens), records billing, returns to frontend
```

### Internal Invoke (service-to-service)

For backend services (e.g., extraction worker, chapter translator), the flow uses:
```
POST /internal/invoke?user_id={owner_user_id}
X-Internal-Token: {service_token}
```

This skips JWT auth and uses the internal service token instead.

---

## 3. API Standard: OpenAI-Compatible

LoreWeave uses **OpenAI-compatible API format** as the default standard. If your service follows the OpenAI API structure, it works out of the box with the existing `openai` adapter — no custom adapter needed.

### Why OpenAI-Compatible?
- Widest ecosystem support
- LM Studio, vLLM, Ollama (partial), and many tools already use it
- The `provider_kind` fallback in LoreWeave routes unknown kinds to the OpenAI adapter

### What "OpenAI-Compatible" Means

Your service should expose these endpoints (implement only the ones relevant to your capability):

| Capability | Endpoint | OpenAI Reference |
|-----------|----------|-----------------|
| Chat/Completion | `POST /v1/chat/completions` | [Chat API](https://platform.openai.com/docs/api-reference/chat) |
| TTS | `POST /v1/audio/speech` | [TTS API](https://platform.openai.com/docs/api-reference/audio/createSpeech) |
| STT | `POST /v1/audio/transcriptions` | [Transcription API](https://platform.openai.com/docs/api-reference/audio/createTranscription) |
| Image Gen | `POST /v1/images/generations` | [Image API](https://platform.openai.com/docs/api-reference/images/create) |
| Models List | `GET /v1/models` | [Models API](https://platform.openai.com/docs/api-reference/models/list) |

---

## 4. Service Contract: Text-to-Speech (TTS)

### Endpoint

```
POST {base_url}/v1/audio/speech
Content-Type: application/json
Authorization: Bearer {api_key}
```

### Request Body

```json
{
  "model": "your-tts-model-name",
  "voice": "alloy",
  "input": "The text to synthesize into speech.",
  "response_format": "mp3",
  "speed": 1.0
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model name as registered in LoreWeave (e.g., `tts-1`, `tts-1-hd`) |
| `voice` | string | Yes | Voice identifier. OpenAI built-in: `alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `onyx`, `nova`, `sage`, `shimmer`, `verse`, `marin`, `cedar`. Your service defines its own voices. |
| `input` | string | Yes | Text to synthesize. **Max 4096 characters.** |
| `instructions` | string | No | Additional voice control instructions (not supported by all models) |
| `response_format` | string | No | `mp3` (default), `opus`, `aac`, `flac`, `wav`, `pcm` |
| `speed` | number | No | Playback speed: **0.25 to 4.0** (default 1.0) |

### Response (Non-Streaming)

Return raw audio bytes with appropriate content type:

```
HTTP/1.1 200 OK
Content-Type: audio/mpeg
Transfer-Encoding: chunked

<binary audio data>
```

### Streaming TTS (Critical for Voice Mode)

Streaming TTS is **essential for low-latency voice conversations**. Instead of waiting for the full audio to generate, the service streams audio chunks as they're produced. This reduces time-to-first-audio from seconds to ~200ms.

#### Option A: Raw Audio Streaming (recommended for simplicity)

The same endpoint returns chunked audio when the client sets `Accept: audio/mpeg` (or the requested format). Audio chunks are sent as they're generated — the client can start playback immediately.

```
POST {base_url}/v1/audio/speech
Content-Type: application/json
Authorization: Bearer {api_key}

{
  "model": "your-tts-model",
  "voice": "alloy",
  "input": "Long text that will be streamed as audio chunks...",
  "response_format": "mp3",
  "speed": 1.0
}
```

Response — chunked transfer:
```
HTTP/1.1 200 OK
Content-Type: audio/mpeg
Transfer-Encoding: chunked

<chunk 1: audio bytes>
<chunk 2: audio bytes>
...
```

**Implementation notes:**
- Use HTTP chunked transfer encoding — most frameworks support this natively
- Each chunk should be a valid audio segment (for MP3: complete frames; for PCM: raw samples)
- The client reads the stream and feeds chunks to an `AudioContext` or `MediaSource` for real-time playback
- **MP3 is ideal for streaming** — each frame is self-contained and decodable independently
- **PCM** (`response_format: "pcm"`) is simplest for streaming — raw 24kHz 16-bit LE mono samples

#### Option B: Server-Sent Events (SSE) with base64 chunks

For clients that prefer event-based streaming (e.g., browser EventSource):

```
POST {base_url}/v1/audio/speech
Content-Type: application/json

{
  "model": "your-tts-model",
  "voice": "alloy",
  "input": "Text to synthesize...",
  "response_format": "pcm",
  "stream_format": "sse"
}
```

Response — SSE stream:
```
HTTP/1.1 200 OK
Content-Type: text/event-stream

data: {"type":"audio","data":"<base64 encoded audio chunk>","index":0}

data: {"type":"audio","data":"<base64 encoded audio chunk>","index":1}

data: {"type":"audio","data":"<base64 encoded audio chunk>","index":2}

data: {"type":"done","duration_ms":3450}

```

| SSE Event Type | Fields | Description |
|---------------|--------|-------------|
| `audio` | `data` (base64), `index` (int) | Audio chunk — decode and append to playback buffer |
| `done` | `duration_ms` (int) | Stream complete — total audio duration |
| `error` | `message` (string) | Error occurred — abort playback |

#### Option C: WebSocket (for bidirectional voice)

For full-duplex voice conversations (speak while AI responds):

```
WS {base_url}/v1/audio/speech/ws
```

Client sends:
```json
{"type": "config", "model": "your-tts-model", "voice": "alloy", "response_format": "pcm", "speed": 1.0}
{"type": "text", "content": "First sentence to speak."}
{"type": "text", "content": "Second sentence."}
{"type": "flush"}
```

Server sends:
```json
{"type": "audio", "data": "<base64 pcm chunk>"}
{"type": "audio", "data": "<base64 pcm chunk>"}
{"type": "done", "duration_ms": 2100}
```

#### Recommended Implementation Priority

1. **Non-streaming** — implement first, simplest, works everywhere
2. **Raw audio streaming (Option A)** — implement second, biggest latency win, minimal code change
3. **SSE streaming (Option B)** — implement if clients prefer event-based APIs
4. **WebSocket (Option C)** — implement last, only if bidirectional voice is needed

#### Example: Streaming TTS in Python/FastAPI

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio

app = FastAPI()

class TTSRequest(BaseModel):
    model: str
    voice: str
    input: str
    response_format: str = "mp3"
    speed: float = 1.0

@app.post("/v1/audio/speech")
async def generate_speech(req: TTSRequest):
    async def audio_stream():
        # Split text into sentences for incremental synthesis
        sentences = split_into_sentences(req.input)
        for sentence in sentences:
            # Generate audio for one sentence (your TTS engine)
            chunk = await your_tts_engine.synthesize_chunk(
                text=sentence,
                voice=req.voice,
                speed=req.speed,
                format=req.response_format,
            )
            yield chunk
    
    content_type = {
        "mp3": "audio/mpeg",
        "pcm": "audio/pcm",
        "wav": "audio/wav",
        "opus": "audio/opus",
    }.get(req.response_format, "audio/mpeg")
    
    return StreamingResponse(
        audio_stream(),
        media_type=content_type,
    )
```

#### Client-Side Playback (Browser)

```javascript
// Fetch streaming audio and play in real-time
const response = await fetch('/v1/audio/speech', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ...' },
  body: JSON.stringify({ model: 'tts-v1', voice: 'alloy', input: text }),
});

const reader = response.body.getReader();
const audioContext = new AudioContext({ sampleRate: 24000 });
let nextStartTime = audioContext.currentTime;

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  // Decode chunk and schedule playback
  const audioBuffer = await audioContext.decodeAudioData(value.buffer);
  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  source.start(nextStartTime);
  nextStartTime += audioBuffer.duration;
}
```

### Available Voices Endpoint (required for TTS services)

LoreWeave's frontend fetches the voice list to populate a voice selector dropdown.
This endpoint is called when the user opens Voice Settings.

```
GET {base_url}/v1/voices
Authorization: Bearer {api_key}
```

Optional query parameters:
- `language` — filter by language code (e.g., `?language=en`)

Response:
```json
{
  "voices": [
    {
      "voice_id": "af_heart",
      "name": "Heart",
      "language": "en",
      "gender": "female",
      "preview_url": "https://your-service.com/previews/af_heart.mp3"
    },
    {
      "voice_id": "am_adam",
      "name": "Adam",
      "language": "en",
      "gender": "male",
      "preview_url": null
    },
    {
      "voice_id": "jf_alpha",
      "name": "Alpha",
      "language": "ja",
      "gender": "female",
      "preview_url": null
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `voice_id` | string | Yes | Unique identifier — this is the value passed to `POST /v1/audio/speech` as `voice` |
| `name` | string | Yes | Human-readable display name |
| `language` | string | Yes | ISO language code (e.g., `en`, `ja`, `zh`, `vi`) |
| `gender` | string | No | `male`, `female`, `neutral` — used for grouping in the UI |
| `preview_url` | string\|null | No | URL to a short audio preview (~3s). If null, "Play Preview" button is hidden. Format: MP3 or WAV. Must be accessible without auth (or use a signed URL). |

**Voice ID in TTS requests:** The `voice` field in `POST /v1/audio/speech` must match a `voice_id` from this endpoint. If an invalid voice is passed, return:

```json
HTTP 400
{"detail": "Unknown voice: xyz. Use GET /v1/voices to list available voices."}
```

**Default voice:** If the `voice` field is omitted or set to `"auto"`, the service should use its default voice (typically the first voice in the list).

### Usage Reporting

LoreWeave calculates usage based on input character count:
- `input_tokens` = number of characters in the `input` field
- `output_tokens` = 0

Your service does NOT need to report usage — LoreWeave measures it.

### Example Implementation (Python/FastAPI)

```python
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io

app = FastAPI()

class TTSRequest(BaseModel):
    model: str
    voice: str
    input: str
    response_format: str = "mp3"
    speed: float = 1.0

@app.post("/v1/audio/speech")
async def generate_speech(
    req: TTSRequest,
    authorization: str = Header(None),
):
    # Validate API key
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized")
    
    # Generate audio (your TTS engine here)
    audio_bytes = your_tts_engine.synthesize(
        text=req.input,
        voice=req.voice,
        speed=req.speed,
        format=req.response_format,
    )
    
    content_type = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "opus": "audio/opus",
        "flac": "audio/flac",
    }.get(req.response_format, "audio/mpeg")
    
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=content_type,
    )
```

---

## 5. Service Contract: Speech-to-Text (STT)

### Endpoint

```
POST {base_url}/v1/audio/transcriptions
Content-Type: multipart/form-data
Authorization: Bearer {api_key}
```

### Request (multipart form)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | Audio file. Supported formats: `flac`, `mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `ogg`, `wav`, `webm` |
| `model` | string | Yes | Model name (e.g., `whisper-1`, `gpt-4o-transcribe`) |
| `language` | string | No | ISO-639-1 language code (e.g., `en`, `ja`, `vi`) — hint for recognition |
| `response_format` | string | No | `json` (default), `text`, `srt`, `verbose_json`, `vtt` |
| `temperature` | number | No | 0 to 1 (default 0) — lower = more deterministic |
| `prompt` | string | No | Optional text to guide model style or provide context |
| `timestamp_granularities` | array | No | `["word"]`, `["segment"]`, or both. Requires `verbose_json` format |

### Response (json format)

```json
{
  "text": "The transcribed text from the audio."
}
```

### Response (verbose_json format)

```json
{
  "text": "The transcribed text from the audio.",
  "language": "en",
  "duration": 3.45,
  "segments": [
    {
      "start": 0.0,
      "end": 1.5,
      "text": "The transcribed text"
    },
    {
      "start": 1.5,
      "end": 3.45,
      "text": "from the audio."
    }
  ]
}
```

### Streaming STT (for real-time voice mode)

For voice conversations, the client sends audio in real-time as the user speaks, and receives partial transcriptions incrementally.

#### WebSocket Streaming (recommended)

```
WS {base_url}/v1/audio/transcriptions/ws
```

Client sends:
```json
{"type": "config", "model": "your-stt-model", "language": "en", "temperature": 0}
```

Then streams raw audio chunks (binary frames, PCM 16kHz 16-bit mono):
```
<binary audio chunk 1>
<binary audio chunk 2>
...
```

Client sends when user stops speaking:
```json
{"type": "flush"}
```

Server sends partial transcriptions as they're ready:
```json
{"type": "partial", "text": "The transcr"}
{"type": "partial", "text": "The transcribed text"}
{"type": "final", "text": "The transcribed text from the audio.", "language": "en", "duration": 3.45}
```

| Event Type | Fields | Description |
|-----------|--------|-------------|
| `partial` | `text` | Interim transcription (may change) |
| `final` | `text`, `language`, `duration` | Finalized transcription for this segment |
| `error` | `message` | Error occurred |

#### Implementation Priority

1. **Non-streaming** (`POST /v1/audio/transcriptions`) — implement first
2. **WebSocket streaming** — implement for real-time voice mode

### Usage Reporting

- `input_tokens` = audio duration in seconds (integer)
- `output_tokens` = number of characters in transcription

### Example Implementation (Python/FastAPI)

```python
from fastapi import FastAPI, File, Form, UploadFile, Header, HTTPException
import tempfile, os

app = FastAPI()

@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(...),
    language: str = Form(None),
    response_format: str = Form("json"),
    temperature: float = Form(0),
    authorization: str = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized")
    
    # Save uploaded audio to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Transcribe (your STT engine here)
        result = your_stt_engine.transcribe(
            audio_path=tmp_path,
            language=language,
            temperature=temperature,
        )
        
        if response_format == "text":
            return result.text
        
        return {
            "text": result.text,
            "language": result.language,
            "duration": result.duration,
            **({"segments": result.segments} if response_format == "verbose_json" else {}),
        }
    finally:
        os.unlink(tmp_path)
```

---

## 6. Service Contract: Image Generation

### Endpoint

```
POST {base_url}/v1/images/generations
Content-Type: application/json
Authorization: Bearer {api_key}
```

### Request Body

```json
{
  "model": "your-image-model",
  "prompt": "A mystical castle on a floating island at sunset",
  "size": "1024x1024",
  "n": 1,
  "response_format": "url",
  "quality": "standard"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model name (e.g., `dall-e-3`, `gpt-image-1`) |
| `prompt` | string | Yes | Text description. **Max length:** 32K (GPT models), 4K (DALL-E-3), 1K (DALL-E-2) |
| `size` | string | No | DALL-E-2: `256x256`, `512x512`, `1024x1024`. DALL-E-3: `1024x1024`, `1792x1024`, `1024x1792`. GPT: `auto`, `1024x1024`, `1536x1024`, `1024x1536` |
| `n` | integer | No | Number of images (default 1). DALL-E-3/GPT: only `n=1` |
| `response_format` | string | No | `url` (default) or `b64_json` |
| `quality` | string | No | `standard` (default), `hd`, `high`, `medium`, `low` — model-dependent |
| `style` | string | No | `vivid` (default) or `natural` — DALL-E-3 only |
| `background` | string | No | `auto`, `transparent`, `opaque` — GPT image models only |

### Response

```json
{
  "created": 1700000000,
  "data": [
    {
      "url": "https://your-service.com/images/generated/abc123.png",
      "revised_prompt": "A mystical castle..."
    }
  ]
}
```

Or with `b64_json`:
```json
{
  "created": 1700000000,
  "data": [
    {
      "b64_json": "iVBORw0KGgo..."
    }
  ]
}
```

**Note:** LoreWeave downloads the image from `url` and stores it in MinIO. The URL must be accessible from the LoreWeave server for a reasonable time (~10 minutes).

### Usage Reporting

- `input_tokens` = prompt character count
- `output_tokens` = 0

---

## 7. Service Contract: Video Generation

### Endpoint

```
POST {base_url}/v1/video/generations
Content-Type: application/json
Authorization: Bearer {api_key}
```

> **Note:** The path is `/v1/video/generations` (singular "video"), matching the LoreWeave video-gen-service implementation.

### Request Body

```json
{
  "model": "your-video-model",
  "prompt": "A dragon flying over a medieval city",
  "size": "1920x1080",
  "duration": 5,
  "n": 1,
  "style": "natural"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model name |
| `prompt` | string | Yes | Text description of the video |
| `size` | string | No | Resolution. Common: `1920x1080`, `1080x1920`, `1080x1080`, `1440x1080` (default `1920x1080`) |
| `duration` | number | No | Duration in seconds (default 5) |
| `n` | integer | No | Number of videos (default 1) |
| `style` | string | No | Style hint (model-dependent) |
| `image` | string | No | Base64 image for image-to-video |

### Response

```json
{
  "created": 1700000000,
  "data": [
    {
      "url": "https://your-service.com/videos/generated/xyz789.mp4"
    }
  ]
}
```

### Async Generation (recommended for video)

Video generation is slow. Support async pattern:

**Submit:**
```
POST /v1/video/generations → 202 Accepted
{ "id": "gen_abc123", "status": "processing" }
```

**Poll:**
```
GET /v1/video/generations/gen_abc123
{ "id": "gen_abc123", "status": "completed", "data": [{ "url": "..." }] }
```

Statuses: `processing` → `completed` | `failed`

---

## 8. Authentication & Credential Flow

### How LoreWeave stores credentials

```
provider_credentials table:
  provider_credential_id: UUID
  owner_user_id: UUID
  provider_kind: TEXT         ← e.g., "my_tts_service"
  endpoint_base_url: TEXT     ← e.g., "https://my-tts.example.com"
  secret_ciphertext: TEXT     ← AES-256-GCM encrypted API key
  api_standard: TEXT          ← "openai_compatible" (default)
  status: TEXT                ← "active"
```

### How your service receives auth

Every request from LoreWeave includes:
```
Authorization: Bearer {decrypted_api_key}
```

Your service should:
1. Extract the Bearer token
2. Validate it (your own auth logic)
3. Return 401 if invalid

**For local/self-hosted services** that don't need auth: accept any token or check for a static key.

### Provider Kind Registration

When users set up your service in LoreWeave, they configure:
- **Provider Kind**: A string identifier (e.g., `my_tts`, `whisper_local`, `stable_diffusion`)
- **Endpoint Base URL**: Where your service runs (e.g., `http://localhost:8000`, `https://api.myservice.com`)
- **API Key**: Secret for authentication

If your `provider_kind` is not one of the built-in types (`openai`, `anthropic`, `ollama`, `lm_studio`), LoreWeave's adapter factory falls back to the **OpenAI-compatible adapter**. This means your service gets OpenAI-format requests automatically — no custom adapter needed.

---

## 9. Capability Flags

When users create a model entry, they set capability flags:

```json
{
  "chat": false,
  "tts": true,
  "stt": false,
  "image_gen": false,
  "video_gen": false,
  "embedding": false,
  "moderation": false
}
```

These flags:
- Control which models appear in capability-filtered dropdowns (e.g., TTS model selector only shows `tts: true`)
- Are stored as JSONB on `user_models.capability_flags`
- Are set by the user, not auto-detected (the user knows what their model supports)

### Recommended: Expose capabilities in model list

```
GET /v1/models
```

Response:
```json
{
  "data": [
    {
      "id": "my-tts-v1",
      "object": "model",
      "owned_by": "my-organization",
      "capabilities": {
        "tts": true,
        "voices": ["alloy", "nova", "echo"]
      }
    }
  ]
}
```

LoreWeave can sync these when the user clicks "Refresh Models" in the provider settings UI.

---

## 10. Usage & Billing Integration

LoreWeave handles billing automatically. Your service does NOT need to implement billing.

### How it works

1. LoreWeave's provider-registry calls your service
2. After receiving the response, it calculates token usage:
   - **Chat**: `input_tokens` from prompt, `output_tokens` from response
   - **TTS**: `input_tokens` = character count, `output_tokens` = 0
   - **STT**: `input_tokens` = audio seconds, `output_tokens` = transcript chars
   - **Image**: `input_tokens` = prompt chars, `output_tokens` = 0
   - **Video**: `input_tokens` = prompt chars, `output_tokens` = 0
3. Records usage in `usage_logs` table
4. Deducts from user's monthly quota or credits

### Optional: Return usage in response

If your response includes usage data, LoreWeave will use it instead of calculating:

```json
{
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 500,
    "total_tokens": 650
  }
}
```

---

## 11. Health Check Contract

### Endpoint

```
GET {base_url}/health
```

or

```
GET {base_url}/v1/models
```

LoreWeave uses the model list endpoint as a health check. If it returns 200, the service is healthy.

### Response

Any 200 response is acceptable. Recommended:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "models": ["my-tts-v1", "my-tts-v2"]
}
```

---

## 12. Model Discovery Contract

### Endpoint

```
GET {base_url}/v1/models
Authorization: Bearer {api_key}
```

### Response (OpenAI format)

```json
{
  "object": "list",
  "data": [
    {
      "id": "my-tts-v1",
      "object": "model",
      "created": 1700000000,
      "owned_by": "my-organization"
    },
    {
      "id": "my-stt-whisper-large",
      "object": "model",
      "created": 1700000000,
      "owned_by": "my-organization"
    }
  ]
}
```

LoreWeave uses this to:
- Populate the model inventory (auto-sync available models)
- Verify the credential works (health check)
- Let users pick from available models

---

## 13. Deployment & Registration

### Step 1: Deploy your service

Your service can run anywhere accessible from LoreWeave's server:
- Local: `http://localhost:8000`
- Docker: `http://my-tts-service:8000` (same Docker network)
- Cloud: `https://api.myservice.com`

### Step 2: User registers in LoreWeave

In LoreWeave UI → Settings → Model Providers:

1. Click **"Add Provider"**
2. Fill in:
   - **Provider Name**: "My TTS Service"
   - **Provider Kind**: `my_tts` (or `openai` if fully compatible)
   - **Endpoint URL**: `http://localhost:8000`
   - **API Key**: Your service's API key
3. Click **"Verify"** — LoreWeave calls `GET /v1/models` to test
4. **Add Model**:
   - **Model Name**: `my-tts-v1`
   - **Capabilities**: Check `tts` ✓
   - **Alias**: "My TTS Voice"

### Step 3: Use in LoreWeave

The model now appears in:
- Voice Mode settings (TTS model dropdown)
- Reader TTS settings
- Any capability-filtered model selector

### Docker Compose Integration (optional)

Add your service to LoreWeave's `docker-compose.yml`:

```yaml
my-tts-service:
  build: ../my-tts-service
  ports:
    - "8500:8000"
  environment:
    API_KEY: ${MY_TTS_API_KEY:-dev_key}
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

---

## 14. Testing Your Service

### Quick test with curl

**TTS:**
```bash
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "Authorization: Bearer dev_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"my-tts-v1","voice":"alloy","input":"Hello world","response_format":"mp3"}' \
  --output test.mp3
```

**STT:**
```bash
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -H "Authorization: Bearer dev_key" \
  -F "file=@test.mp3" \
  -F "model=my-stt-v1" \
  -F "language=en"
```

**Image:**
```bash
curl -X POST http://localhost:8000/v1/images/generations \
  -H "Authorization: Bearer dev_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"my-image-v1","prompt":"A cat wearing a hat","size":"512x512"}'
```

**Models list:**
```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer dev_key"
```

### Test via LoreWeave provider-registry

Once registered, test the full flow:

```bash
# Get a JWT token
TOKEN=$(curl -s http://localhost:3123/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test1234!"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Invoke via provider-registry
curl -X POST http://localhost:3123/v1/model-registry/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_source": "user_model",
    "model_ref": "<your_user_model_id>",
    "input": {
      "model": "my-tts-v1",
      "voice": "alloy",
      "input": "Hello from LoreWeave",
      "response_format": "mp3"
    }
  }'
```

---

## 15. Reference: Existing Adapter Implementations

### Built-in adapters in LoreWeave

| Provider Kind | Adapter | Chat | TTS | STT | Image | Video |
|--------------|---------|------|-----|-----|-------|-------|
| `openai` | OpenAI adapter | ✓ | ✓ | ✓ | ✓ | — |
| `anthropic` | Anthropic adapter | ✓ | — | — | — | — |
| `ollama` | Ollama adapter | ✓ | — | — | — | — |
| `lm_studio` | LM Studio adapter | ✓ | — | — | — | — |
| `*` (any other) | OpenAI fallback | ✓ | ✓ | ✓ | ✓ | — |

### Source code reference

- Adapter interface: `services/provider-registry-service/internal/provider/adapters.go`
- Invoke endpoint: `services/provider-registry-service/internal/api/server.go`
- TTS generation: `services/book-service/internal/api/audio.go`
- Image generation: `services/book-service/internal/api/media.go`
- Video generation: `services/video-gen-service/app/generate.py` (skeleton)

### Key data structures

```go
// Usage returned by adapters
type Usage struct {
    InputTokens  int
    OutputTokens int
}

// Model info from /v1/models
type ModelInventory struct {
    ProviderModelName string
    ContextLength     int
    CapabilityFlags   map[string]interface{}
}

// Adapter interface
type Adapter interface {
    ListModels(ctx context.Context, baseURL, secret string) ([]ModelInventory, error)
    Invoke(ctx context.Context, baseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error)
    HealthCheck(ctx context.Context, baseURL, secret string) error
}
```

---

## Checklist: Building a New AI Service

- [ ] Choose capability: TTS, STT, Image, Video, or multi-capability
- [ ] Implement the OpenAI-compatible endpoint(s) from section 3
- [ ] Implement `GET /v1/models` for model discovery
- [ ] Implement `GET /health` for health check
- [ ] Accept `Authorization: Bearer {key}` header
- [ ] Return standard response format (see sections 4-7)
- [ ] Deploy and make accessible from LoreWeave server
- [ ] Register as a provider in LoreWeave Settings UI
- [ ] Set correct capability flags on the model
- [ ] Test end-to-end via `POST /v1/model-registry/invoke`

---

---

## 16. Known Limitations & Future Work

### Current limitations in LoreWeave

| Area | Limitation | Impact |
|------|-----------|--------|
| **STT backend** | No STT endpoint in LoreWeave yet — frontend uses browser Web Speech API | STT services can be built but need a new backend route to connect |
| **Provider invoke: file upload** | `Invoke()` adapter interface only handles JSON (`map[string]any`), not multipart file upload | STT services that need audio file input must be called directly (like video-gen-service), not through the generic invoke path |
| **Streaming TTS in provider-registry** | The provider-registry invoke endpoint returns JSON, not streaming audio | Streaming TTS must be called directly by the frontend or a dedicated service, bypassing provider-registry |
| **Video API not standardized** | `/v1/video/generations` follows a Sora-compatible guess, not an official OpenAI spec | Video service developers should expect this path may change |

### Planned improvements

- **STT proxy route** in api-gateway-bff for provider-based STT
- **Multipart invoke** path in provider-registry for file-based AI calls
- **Streaming audio proxy** for real-time TTS through the gateway
- **WebSocket relay** in gateway for bidirectional voice (STT + TTS)

### Building ahead of these limitations

If you're building a TTS or STT service now:
1. **Implement the standard endpoints** documented above — they'll work when LoreWeave adds the routes
2. **Also expose a simple health check** at `GET /health` so Docker can monitor it
3. **For streaming**: implement raw chunked audio first (Option A) — it's the simplest and works with a direct URL connection even before the gateway proxy exists

---

*Last updated: 2026-04-11 — LoreWeave session 31. Verified against OpenAI Python SDK (2025-12 spec).*
