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
| `model` | string | Yes | Model name as registered in LoreWeave |
| `voice` | string | Yes | Voice identifier (your service defines available voices) |
| `input` | string | Yes | Text to synthesize (may be long — up to 4096 chars per block) |
| `response_format` | string | No | `mp3` (default), `wav`, `opus`, `flac` |
| `speed` | number | No | Playback speed multiplier: 0.25 to 4.0 (default 1.0) |

### Response

Return raw audio bytes with appropriate content type:

```
HTTP/1.1 200 OK
Content-Type: audio/mpeg
Transfer-Encoding: chunked

<binary audio data>
```

### Available Voices Endpoint (recommended)

```
GET {base_url}/v1/voices
```

Response:
```json
{
  "voices": [
    { "voice_id": "alloy", "name": "Alloy", "language": "en", "gender": "neutral", "preview_url": "..." },
    { "voice_id": "nova", "name": "Nova", "language": "en", "gender": "female", "preview_url": "..." }
  ]
}
```

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
| `file` | file | Yes | Audio file (mp3, wav, webm, m4a, etc.) |
| `model` | string | Yes | Model name as registered |
| `language` | string | No | ISO language code (e.g., `en`, `ja`, `vi`) — hint for recognition |
| `response_format` | string | No | `json` (default), `text`, `verbose_json` |
| `temperature` | number | No | 0 to 1 (default 0) — lower = more deterministic |

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
  "response_format": "url"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model name |
| `prompt` | string | Yes | Text description of the image |
| `size` | string | No | `256x256`, `512x512`, `1024x1024` (default), `1024x1792`, `1792x1024` |
| `n` | integer | No | Number of images to generate (default 1) |
| `response_format` | string | No | `url` (default) or `b64_json` |

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
POST {base_url}/v1/videos/generations
Content-Type: application/json
Authorization: Bearer {api_key}
```

### Request Body

```json
{
  "model": "your-video-model",
  "prompt": "A dragon flying over a medieval city",
  "size": "1280x720",
  "duration": 5,
  "fps": 24
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model name |
| `prompt` | string | Yes | Text description |
| `size` | string | No | Resolution (default `1280x720`) |
| `duration` | number | No | Duration in seconds (default 5) |
| `fps` | integer | No | Frames per second (default 24) |
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
POST /v1/videos/generations → 202 Accepted
{ "id": "gen_abc123", "status": "processing" }
```

**Poll:**
```
GET /v1/videos/generations/gen_abc123
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

*Last updated: 2026-04-11 — LoreWeave session 31*
