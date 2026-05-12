# Phase 5a Design — Audio Adapter (STT + TTS)

> **Status**: DRAFT — pending REVIEW signoff
> **Cycle**: C-LLM-PHASE-5A
> **Size**: L (files ≈8 · logic ≈6 · side-effects 1: openapi stream-request schema becomes operation-aware)
> **Plan ref**: [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md §5](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md)
> **Predecessor**: Phase 4d (provider-registry retirement of legacy invoke + chat-completion proxy paths)

---

## 1. Goals (cycle 5a only)

1. Provider-registry gateway gains **first-class STT + TTS** operations on the unified contract:
   - `POST /v1/llm/jobs` `operation=stt` — submit-and-wait pattern
   - `POST /v1/llm/stream` `operation=tts` — SSE-streamed audio chunks
2. Adapter layer extended: `Transcribe` + `Speak` methods, OpenAI implementation only.
3. SDK Python adds `Client.transcribe()` + `Client.stream_tts()`.
4. Transparent proxy `/internal/proxy/v1/audio/*` **stays alive** (chat-service still uses it; 5b retires it).
5. `image_gen` deferred — no caller exists, will surface in a later cycle.

**Non-goals** (explicitly):
- Migrating chat-service voice (that's 5b)
- Multi-provider audio (Anthropic/Ollama have no audio API; LM Studio depends on user-loaded model — return `ErrOperationNotSupported`)
- Image generation
- Audio-side gateway chunking (long-audio split) — defer until needed
- TTS output → S3 upload by gateway (caller owns storage; status quo)

---

## 2. Contract changes

### 2.1 OpenAPI — `StreamRequest` becomes operation-aware

Today (`contracts/api/llm-gateway/v1/openapi.yaml`):
```yaml
StreamRequest:
  type: object
  required: [model_source, model_ref, messages]
  properties:
    model_source: ...
    model_ref: ...
    messages: [...]
    tools: ...
    temperature: ...
    max_tokens: ...
    stream_format: openai|anthropic|vercel-ai-ui-v1
```

Target — discriminated union with optional `operation` field defaulting to `"chat"` (backward-compatible):

```yaml
StreamRequest:
  oneOf:
    - $ref: '#/components/schemas/ChatStreamRequest'
    - $ref: '#/components/schemas/TtsStreamRequest'
  discriminator:
    propertyName: operation
    mapping:
      chat: '#/components/schemas/ChatStreamRequest'
      tts:  '#/components/schemas/TtsStreamRequest'

ChatStreamRequest:
  type: object
  required: [model_source, model_ref, messages]
  properties:
    operation:
      type: string
      enum: [chat]
      default: chat                     # omitted ⇒ "chat" — preserves all existing callers
    model_source: ...
    model_ref: ...
    messages: [...]
    tools: ...
    temperature: ...
    max_tokens: ...
    stream_format: openai|anthropic|vercel-ai-ui-v1

TtsStreamRequest:
  type: object
  required: [operation, model_source, model_ref, input]
  properties:
    operation:
      type: string
      enum: [tts]
    model_source: ...
    model_ref: ...
    input:
      $ref: '#/components/schemas/TtsInput'
    trace_id: { type: string, nullable: true }

TtsInput:
  type: object
  required: [text]
  properties:
    text:   { type: string, minLength: 1, maxLength: 4000 }
    voice:  { type: string, default: alloy }
    speed:  { type: number, minimum: 0.25, maximum: 4.0, default: 1.0 }
    format:
      type: string
      enum: [mp3, wav, opus, pcm]
      default: mp3
```

### 2.2 OpenAPI — new `AudioChunkEvent`

```yaml
AudioChunkEvent:
  type: object
  required: [event, sequence_id, data, final]
  properties:
    event:
      type: string
      enum: [audio-chunk]
    sequence_id:
      type: integer
      minimum: 0
      description: Monotonic 0-indexed counter within a single SSE stream.
    data:
      type: string
      format: byte                        # base64
      description: |
        Base64-encoded raw audio bytes in the format negotiated via TtsInput.format.
        Empty string when final=true (end-of-stream sentinel).
    final:
      type: boolean
      description: True on the closing chunk; followed by a `done` event.
```

`StreamEventEnvelope` union gains `AudioChunkEvent`.

### 2.3 OpenAPI — `SubmitJobRequest.input` for `stt`

Already declared at `openapi.yaml:625`:
```
- `stt`: `{ audio_url: "...", language: "auto" }`
```

Frozen as-is. Add formal schema:

```yaml
SttInput:
  type: object
  required: [audio_url]
  properties:
    audio_url:
      type: string
      format: uri
      description: |
        HTTPS URL the gateway can GET to fetch the audio. Caller is responsible
        for upload + URL signing. For chat-service voice flow, this is a
        pre-signed MinIO URL with ≤60s TTL.
    language:
      type: string
      default: auto
      description: |
        ISO 639-1 code or "auto" for upstream auto-detection.
        OpenAI Whisper accepts both.
```

`Job.result` for completed `stt` job:
```yaml
SttResult:
  type: object
  required: [text]
  properties:
    text:        { type: string }
    language:    { type: string, nullable: true, description: detected language }
    duration_ms: { type: integer, description: audio duration as reported by upstream }
```

### 2.4 No change to existing endpoints

`/v1/llm/jobs`, `/v1/llm/stream`, `/internal/llm/jobs`, `/internal/llm/stream` URLs unchanged. Worker dispatch + SSE handler **branch on operation** internally.

---

## 3. Component design

### 3.1 Gateway `Adapter` interface extension

[`services/provider-registry-service/internal/provider/adapters.go`](services/provider-registry-service/internal/provider/adapters.go)

```go
type Adapter interface {
    ListModels(ctx, baseURL, secret) ([]ModelInventory, error)
    Invoke(ctx, baseURL, secret, modelName, input) (map[string]any, Usage, error)
    HealthCheck(ctx, baseURL, secret) error
    Stream(ctx, baseURL, secret, modelName, input, emit) error

    // Phase 5a additions
    Transcribe(ctx context.Context, baseURL, secret, modelName string, input TranscribeInput) (TranscribeOutput, Usage, error)
    Speak(ctx context.Context, baseURL, secret, modelName string, input SpeakInput, emit AudioEmitFn) error
}

type TranscribeInput struct {
    AudioURL string  // gateway-fetchable URL
    Language string  // "auto" or ISO 639-1
}

type TranscribeOutput struct {
    Text        string
    Language    string  // detected; empty if upstream didn't return
    DurationMs  int     // 0 if upstream didn't return
}

type SpeakInput struct {
    Text   string
    Voice  string   // upstream voice name (alloy/echo/...)
    Speed  float64  // 1.0 default
    Format string   // mp3/wav/opus/pcm
}

type AudioChunk struct {
    SequenceID int
    Data       []byte
    Final      bool
}

type AudioEmitFn = func(AudioChunk) error

var ErrOperationNotSupported = errors.New("operation not supported by this provider adapter")
```

### 3.2 OpenAI adapter (`openaiAdapter`) — implementations

**Transcribe**:
1. `httpClient.Get(input.AudioURL)` to fetch bytes (timeout = 30s; max body = 25MB per OpenAI Whisper limit)
2. Build multipart body: `file=<audio>`, `model=<modelName>`, `language=<input.Language>` (omit when `auto`), `response_format=verbose_json` (so we get `language` + `duration` back)
3. `POST {baseURL}/v1/audio/transcriptions` with `Authorization: Bearer <secret>`
4. Parse JSON: `{text, language, duration}`
5. Return `TranscribeOutput{Text, Language, DurationMs: round(duration*1000)}`, `Usage{}` (Whisper has no token usage)
6. Reuses helper logic from existing [`server.go:1949 verifySTT`](services/provider-registry-service/internal/api/server.go#L1949) (extract WAV-build skipped — verify uses synthetic silence; production fetches real audio)

**Speak**:
1. `POST {baseURL}/v1/audio/speech` JSON: `{model, input: text, voice, speed, response_format: format}` with `Authorization` + `Accept: application/octet-stream`
2. Open streaming response body (`resp.Body`)
3. Read in 4KB chunks, emit `AudioChunk{SequenceID: n, Data: buf[:n], Final: false}`
4. On EOF: emit `AudioChunk{SequenceID: final, Data: nil, Final: true}`
5. emit returning error → close upstream + return error (caller disconnect)

### 3.3 Other adapters (`anthropic`, `ollama`, `lmStudio`)

Both methods return `ErrOperationNotSupported`. No HTTP call.

(Open: LM Studio whisper.cpp loaders exist but inconsistent. Defer until a user requests it. Adding shape stub now keeps the option open.)

### 3.4 Worker dispatch — `audioJobWorker`

[`services/provider-registry-service/internal/jobs/worker.go`](services/provider-registry-service/internal/jobs/worker.go)

Today `streamableOperations` whitelists chat-shape ops; everything else fails with `LLM_OPERATION_NOT_SUPPORTED`. Phase 5a adds:

```go
// Audio-job ops route through a different adapter method (Transcribe / Speak)
// — no SSE, no per-chunk aggregation. Single upstream call → single result.
var audioJobOperations = map[string]struct{}{
    "stt": {},
}

// Phase 5a: tts is streaming-only via /v1/llm/stream — never hits the worker.
// We intentionally do NOT add tts to validJobOperations-via-jobs path.
```

Update `validJobOperations` (in `jobs_handler.go`) to **reject** `tts` from `/v1/llm/jobs` with `LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS` + hint pointing at `/v1/llm/stream`. (Caller-error, not server-error — 400 not 501.)

Worker dispatch in `processJob`:
1. If `op` in `streamableOperations` → existing path (chat-streaming + per-op aggregator)
2. Elif `op == "stt"` → new `runSttJob` path (single Transcribe call → marshal `SttResult` → `status=completed`)
3. Elif `op == "tts"` → mark job failed with `LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS` (defense; submit handler should have rejected first)
4. Else (`embedding`, `image_gen`, `translation`) → status quo (unsupported)

`runSttJob`:
- Resolve provider creds (existing `resolveCredentials`)
- Call `adapter.Transcribe(ctx, baseURL, secret, modelName, in)`
- On `ErrOperationNotSupported` → `status=failed, error.code=LLM_OPERATION_NOT_SUPPORTED`
- On other error → `status=failed, error.code=LLM_UPSTREAM_ERROR` (existing classifier reused)
- On success → `result = {text, language, duration_ms}`, `status=completed`, `progress.chunks_total=1, chunks_done=1`
- Honor cancellation: `ctx.Done()` → `status=cancelled, error.code=LLM_CANCELLED`

### 3.5 SSE handler — `/v1/llm/stream` branches on operation

[`services/provider-registry-service/internal/api/server.go`](services/provider-registry-service/internal/api/server.go) `streamHandler` (or whatever the current name is — to verify in BUILD).

Pseudocode:
```go
func (s *Server) doStream(w, r) {
    body := decodeStreamRequest(r)
    op := body.Operation
    if op == "" { op = "chat" }   // backward-compat default

    switch op {
    case "chat":
        s.streamChat(w, r, body)        // existing path
    case "tts":
        s.streamTts(w, r, body)         // new path — calls adapter.Speak
    default:
        sseWriteError(w, "LLM_INVALID_REQUEST", "unsupported stream operation: "+op)
    }
}

func (s *Server) streamTts(w, r, body) {
    creds := resolveCredentials(...)    // same as chat path
    adapter := pickAdapter(creds.providerKind)
    seq := 0
    emit := func(c AudioChunk) error {
        return sseWriteEvent(w, "audio-chunk", map[string]any{
            "sequence_id": c.SequenceID,
            "data":        base64Encode(c.Data),
            "final":       c.Final,
        })
    }
    err := adapter.Speak(r.Context(), creds.baseURL, creds.secret, creds.modelName, body.Input, emit)
    if errors.Is(err, ErrOperationNotSupported) {
        sseWriteError(w, "LLM_OPERATION_NOT_SUPPORTED", "tts not supported by provider")
        return
    }
    if err != nil {
        sseWriteError(w, "LLM_UPSTREAM_ERROR", err.Error())
        return
    }
    sseWriteEvent(w, "done", map[string]any{})
}
```

`internalLlmStream` mirrors the same dispatch (just different auth + per-call user_id resolution).

### 3.6 SDK Python (`sdks/python/loreweave_llm/`)

**`models.py` additions**:
```python
class AudioChunkEvent(_BaseEvent):
    event_type: Literal["audio-chunk"] = Field("audio-chunk", alias="event")
    sequence_id: int
    data: str         # base64
    final: bool

# Update StreamEvent union to include AudioChunkEvent

class TtsInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str = "alloy"
    speed: float = 1.0
    format: Literal["mp3", "wav", "opus", "pcm"] = "mp3"

class TtsStreamRequest(BaseModel):
    operation: Literal["tts"] = "tts"
    model_source: ModelSource
    model_ref: UUID
    input: TtsInput
    trace_id: str | None = None

    def to_request_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

class SttInput(BaseModel):
    audio_url: str
    language: str = "auto"

class SttResult(BaseModel):
    text: str
    language: str | None = None
    duration_ms: int | None = None
```

**`client.py` additions**:
```python
async def transcribe(
    self,
    audio_url: str,
    *,
    model_source: ModelSource,
    model_ref: str,
    language: str = "auto",
    user_id: str | None = None,
    timeout_s: float | None = None,
) -> SttResult:
    """Submit STT job, wait for terminal state, return decoded result.

    Reuses submit_job + wait_terminal — same backoff, same cancellation,
    same metric instrumentation.
    """
    req = SubmitJobRequest(
        operation="stt",
        model_source=model_source,
        model_ref=model_ref,
        input={"audio_url": audio_url, "language": language},
    )
    submitted = await self.submit_job(req, user_id=user_id)
    job = await self.wait_terminal(submitted.job_id, user_id=user_id, timeout_s=timeout_s)
    if job.status != "completed":
        raise from_code(job.error.code if job.error else "LLM_UPSTREAM_ERROR",
                        job.error.message if job.error else "stt failed")
    return SttResult.model_validate(job.result)

async def stream_tts(
    self,
    text: str,
    *,
    model_source: ModelSource,
    model_ref: str,
    voice: str = "alloy",
    speed: float = 1.0,
    format: Literal["mp3", "wav", "opus", "pcm"] = "mp3",
    user_id: str | None = None,
) -> AsyncIterator[AudioChunkEvent | DoneEvent]:
    """Stream TTS audio chunks. Yields AudioChunkEvent until final=true,
    then a DoneEvent. Caller decodes base64 and feeds the player."""
    req = TtsStreamRequest(
        model_source=model_source,
        model_ref=model_ref,
        input=TtsInput(text=text, voice=voice, speed=speed, format=format),
    )
    # Reuse self.stream() machinery but with the new request body shape
    # — _stream_inner handles the SSE iteration; both Chat and Tts requests
    #   share the URL + auth headers.
    async for ev in self._stream_inner(req.to_request_body(), user_id=user_id):
        if isinstance(ev, AudioChunkEvent):
            yield ev
        elif isinstance(ev, DoneEvent):
            yield ev
            return
        elif isinstance(ev, ErrorEvent):
            raise from_code(ev.code, ev.message)
        # Ignore TokenEvent / UsageEvent (not expected on tts but safe to skip)
```

Existing `stream(StreamRequest)` keeps working — internally we factor `_stream_inner(body_dict, user_id)` so both `stream()` and `stream_tts()` share the SSE-iteration machinery.

### 3.7 Audio-URL access from gateway

Gateway needs HTTP GET access to whatever the caller passes as `audio_url`. Two scenarios:
- **chat-service voice (Phase 5b)**: chat-service uploads audio bytes to MinIO with key `voice-uploads/{user}/{session}/{ts}.webm`, generates a pre-signed GET URL valid 60s, passes URL to `transcribe()`. Gateway fetches via plain httpx.
- **Out-of-cluster callers (future)**: any HTTPS URL works.

Gateway constraints to enforce:
- URL must be `http://` or `https://` (reject `file://`, `s3://`, etc.) — basic SSRF guard
- GET timeout 30s, max body 25MB (matches OpenAI Whisper upload cap)
- On fetch failure → `LLM_AUDIO_FETCH_FAILED`

(SSRF-deeper hardening — e.g., disallowing `127.0.0.1`, `169.254.169.254` — deferred to Phase 6 hardening; for MVP we accept that gateway runs in a VPC where chat-service ↔ MinIO traffic is the expected use.)

---

## 4. Sequence diagrams

### 4.1 STT — submit-and-wait via jobs

```
chat-service          provider-registry              MinIO            OpenAI
     │                       │                         │                 │
     │ upload audio          │                         │                 │
     ├──────────────────────────────────────────────►│                 │
     │ ◄────────────────────────────────────────────  │                 │
     │   {object_key}                                  │                 │
     │ presign GET                                     │                 │
     │ ────────►(local SDK call)                       │                 │
     │ {audio_url}                                     │                 │
     │                                                 │                 │
     │ POST /v1/llm/jobs (op=stt, input=audio_url)    │                 │
     ├──────────────────────►│                         │                 │
     │ ◄────────────────────  │ {job_id, status: pending}                │
     │                       │                                            │
     │                       │ audioJobWorker picks up                    │
     │                       │ GET audio_url                              │
     │                       ├────────────────────────►│                 │
     │                       │ ◄──────────────────────  audio bytes      │
     │                       │ POST /v1/audio/transcriptions             │
     │                       ├─────────────────────────────────────────►│
     │                       │ ◄─────────────────────────────────────── {text, lang, dur}
     │                       │ persist Job.result                        │
     │                       │                                            │
     │ poll GET /v1/llm/jobs/:id (or wait_terminal)    │                 │
     ├──────────────────────►│                         │                 │
     │ ◄────────────────────  │ {status: completed, result: SttResult}    │
```

### 4.2 TTS — SSE stream via /v1/llm/stream

```
chat-service          provider-registry              OpenAI
     │                       │                         │
     │ POST /v1/llm/stream (op=tts, input.text=...)   │
     ├──────────────────────►│                         │
     │ ◄────────────────────  200 SSE                  │
     │                       │ POST /v1/audio/speech   │
     │                       ├────────────────────────►│
     │                       │ ◄────────────────────── 200 streaming bytes
     │ ◄ event: audio-chunk  │ {seq_id: 0, data: ..., final: false}
     │ ◄ event: audio-chunk  │ {seq_id: 1, data: ..., final: false}
     │ ◄ event: audio-chunk  │ {seq_id: N, data: "", final: true}
     │ ◄ event: done         │
```

---

## 5. Test plan

### 5.1 Adapter-level (Go unit tests)

[`services/provider-registry-service/internal/provider/adapters_test.go`](services/provider-registry-service/internal/provider/adapters_test.go)

| Test | Asserts |
|---|---|
| `TestOpenAIAdapter_Transcribe_HappyPath` | mock `httptest.Server` for both URL fetch + `/v1/audio/transcriptions`; assert multipart shape (file + model + language fields), parse `verbose_json` response, return correct `TranscribeOutput` |
| `TestOpenAIAdapter_Transcribe_LanguageAuto_OmitsParam` | language="auto" ⇒ multipart MUST NOT include `language` field |
| `TestOpenAIAdapter_Transcribe_AudioFetchFailure` | URL returns 404 ⇒ wrapped error containing "LLM_AUDIO_FETCH_FAILED" hint |
| `TestOpenAIAdapter_Transcribe_AudioTooLarge` | response body 26MB ⇒ aborts read at 25MB cap |
| `TestOpenAIAdapter_Transcribe_UpstreamHTTP4xx` | 401 ⇒ wrapped error with status code |
| `TestOpenAIAdapter_Speak_HappyPath` | mock streams 12KB body in 3 chunks ⇒ 4 emits (3 data + 1 final), monotonic seq_id |
| `TestOpenAIAdapter_Speak_EmitErrorAborts` | emit returns error on chunk 1 ⇒ adapter stops + returns same error; upstream conn closed |
| `TestAnthropicAdapter_Audio_NotSupported` | both Transcribe + Speak return ErrOperationNotSupported (no HTTP) |
| `TestOllamaAdapter_Audio_NotSupported` | same |
| `TestLmStudioAdapter_Audio_NotSupported` | same (kept consistent for now) |

### 5.2 Worker-level (Go unit tests)

[`services/provider-registry-service/internal/jobs/worker_test.go`](services/provider-registry-service/internal/jobs/worker_test.go)

| Test | Asserts |
|---|---|
| `TestRunSttJob_HappyPath` | fake adapter returns `TranscribeOutput{Text:"hello"}` ⇒ Job.result = `{"text":"hello","language":"","duration_ms":0}`, status=completed |
| `TestRunSttJob_Cancellation` | ctx cancelled mid-Transcribe ⇒ status=cancelled, error.code=LLM_CANCELLED |
| `TestRunSttJob_OperationNotSupported` | adapter returns ErrOperationNotSupported ⇒ status=failed, code=LLM_OPERATION_NOT_SUPPORTED |
| `TestRunSttJob_UpstreamError` | adapter returns generic error ⇒ status=failed, code=LLM_UPSTREAM_ERROR |
| `TestProcessJob_TtsRoute_Rejected` | submitting tts via /v1/llm/jobs ⇒ 400 LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS at submit time |
| `TestStreamableOperations_AudioJobOperations_Disjoint` | regression-lock: stt NOT in streamableOperations; tts NOT in audioJobOperations |
| `TestValidJobOperations_StillIncludesStt` | stt remains in validJobOperations whitelist (just routed differently) |

### 5.3 API handler-level (Go unit tests)

| Test | Asserts |
|---|---|
| `TestSubmitJob_TtsRejectedAtSubmit` | POST /v1/llm/jobs `op=tts` ⇒ 400 LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS, error message hints `/v1/llm/stream` |
| `TestSubmitJob_SttAccepted` | POST /v1/llm/jobs `op=stt` ⇒ 202, job_id returned |
| `TestStreamHandler_TtsRoute` | POST /v1/llm/stream `op=tts` w/ fake adapter Speak emitting 2 chunks ⇒ SSE: 2 audio-chunk + 1 final + 1 done |
| `TestStreamHandler_TtsOperationNotSupported` | adapter returns ErrOperationNotSupported ⇒ SSE error event LLM_OPERATION_NOT_SUPPORTED |
| `TestStreamHandler_OperationDefaultIsChat` | omitted `operation` field ⇒ existing chat path runs (backward-compat) |
| `TestStreamHandler_UnknownOperation_Rejected` | `operation=embedding` on stream ⇒ SSE error LLM_INVALID_REQUEST |

### 5.4 SDK Python (pytest)

[`sdks/python/tests/test_audio.py`](sdks/python/tests/test_audio.py) — NEW

| Test | Asserts |
|---|---|
| `test_transcribe_happy_path` | submit_job mocked → wait_terminal returns completed Job → SttResult parsed |
| `test_transcribe_failure` | wait_terminal returns failed → raises mapped LLMError subclass |
| `test_stream_tts_happy_path` | mock SSE: 2 audio-chunk events + done → iterator yields 3 events in order |
| `test_stream_tts_error_event` | mock SSE error event → raises LLMError subclass |
| `test_audio_chunk_event_decode` | base64 round-trip works |

### 5.5 Regression locks

| Test | Asserts |
|---|---|
| `TestDoProxyAudioPathsNotDeprecated` (existing, in proxy_integration_test.go) | still passes — audio carve-out preserved |
| `TestIsDeprecatedProxyPath_AudioPathsAllowed` (existing) | still passes |

### 5.6 Live smoke (manual, post-merge)

- Pre-condition: user has registered an OpenAI BYOK with whisper-1 + tts-1
- `curl POST /internal/llm/jobs op=stt audio_url=<presigned>` → poll `/internal/llm/jobs/:id` → `result.text` non-empty
- `curl POST /internal/llm/stream op=tts text="hello world"` → receives `audio-chunk` events → concat `data` decoded base64 = playable mp3

---

## 6. Files touched (estimate)

| # | File | Change |
|---|---|---|
| 1 | `contracts/api/llm-gateway/v1/openapi.yaml` | StreamRequest discriminated union + AudioChunkEvent + SttInput/SttResult/TtsInput schemas |
| 2 | `services/provider-registry-service/internal/provider/adapters.go` | Adapter interface + Transcribe/Speak types + ErrOperationNotSupported |
| 3 | `services/provider-registry-service/internal/provider/openai_audio.go` | NEW — OpenAI Transcribe + Speak impls (split out for size) |
| 4 | `services/provider-registry-service/internal/provider/audio_unsupported.go` | NEW — Anthropic/Ollama/LM Studio stubs |
| 5 | `services/provider-registry-service/internal/jobs/worker.go` | audioJobOperations map + runSttJob dispatch |
| 6 | `services/provider-registry-service/internal/api/jobs_handler.go` | Reject tts at submit with LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS |
| 7 | `services/provider-registry-service/internal/api/server.go` | Stream handler branches on operation |
| 8 | `sdks/python/loreweave_llm/models.py` | AudioChunkEvent + Tts/Stt models |
| 9 | `sdks/python/loreweave_llm/client.py` | transcribe + stream_tts methods, factor _stream_inner |
| 10 | `services/provider-registry-service/internal/provider/adapters_test.go` | new tests (≈10) |
| 11 | `services/provider-registry-service/internal/jobs/worker_test.go` | new tests (≈7) |
| 12 | `services/provider-registry-service/internal/api/server_test.go` | new tests (≈6) |
| 13 | `sdks/python/tests/test_audio.py` | NEW — SDK tests (≈5) |
| 14 | `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` | mark 5a shipped post-cycle |

Estimate: **~14 files** (slightly over the L threshold of 6+; but logic surface is concentrated — interface + 2 adapter methods + 1 worker dispatch + SSE branch + SDK additions).

If file count alone bumps to XL, mark explicitly during BUILD and notify; current intent is L-tight.

---

## 7. Open questions surfaced during DESIGN

| # | Q | Resolution |
|---|---|---|
| D1 | Should `runSttJob` cap audio at 25MB or stream-and-truncate? | Cap. 26MB ⇒ fail with `LLM_AUDIO_TOO_LARGE` before hitting upstream. |
| D2 | Should TTS streaming validate voice name against an allowlist? | No — pass through to upstream; OpenAI 400 if invalid. Avoids drift when OpenAI ships new voices. |
| D3 | What if caller passes `format=opus` but upstream returns mp3? | OpenAI honors `response_format` field; trust upstream. If mismatch surfaces in production, add format-detection + error. |
| D4 | Should `AudioChunkEvent.data` use base64 or raw bytes (binary SSE)? | Base64. SSE is text-only by spec; binary breaks proxies. Cost: +33% bandwidth, acceptable. |
| D5 | Idempotency for STT — same audio_url submitted twice = re-run upstream call? | Yes (status quo for chat ops too). Job dedup is a separate Phase 6 concern. |
| D6 | Backward-compat: existing chat callers omit `operation` — do we accept that or require explicit `operation=chat`? | Accept omitted (default to "chat"). Otherwise every existing caller breaks. Locked by `TestStreamHandler_OperationDefaultIsChat`. |

---

## 8. 5b preview (NOT in this cycle — informational)

Once 5a ships:
- chat-service `voice_stream_service.py`:
  - `_transcribe_audio` → uploads to MinIO + presigned URL + `client.transcribe(audio_url)`
  - `_generate_tts_chunks` → `async for ev in client.stream_tts(text=...)` re-emits Vercel AI SDK envelope to FE
- Drop `httpx` import from voice path
- Grep zero callers of `/internal/proxy/v1/audio/*` → remove handler + audio carve-out from `isDeprecatedProxyPath` → 410-Gone unification

---

## 9. Decision needed before BUILD

This DESIGN doc is the artifact for Phase 2. Phase 3 (REVIEW) reviews **this doc**, not code. User approval needed on:

1. ✅ Operation-aware StreamRequest (vs. dedicated `/v1/llm/tts/stream` endpoint)
2. ✅ STT via jobs / TTS via stream split (vs. both via jobs with audio S3 result URL)
3. ✅ OpenAI-only adapter coverage
4. ✅ Defer image_gen
5. ✅ Backward-compat: omitted `operation` defaults to `"chat"`
6. ✅ MinIO presigned URL pattern for STT audio_url

USER APPROVED 2026-04-28. Moving to PLAN.

---

## 10. PLAN — bite-sized BUILD tasks

TDD where applicable (red test → green impl → refactor). Tasks numbered T1-T20; each ≤ 5min target. After each task: run the cited verify command before moving on.

| # | Task | Files | Verify |
|---|---|---|---|
| **T1** | Extend `Adapter` interface: add `Transcribe`/`Speak` signatures + helper types (`TranscribeInput/Output`, `SpeakInput`, `AudioChunk`, `AudioEmitFn`) + `ErrOperationNotSupported` sentinel. Stub all 4 adapters returning `ErrOperationNotSupported`. | `internal/provider/adapters.go` (+5 types, interface 2 methods) + 4 adapter stubs (inline in adapters.go OR new `adapters_audio.go`) | `cd services/provider-registry-service && go build ./...` |
| **T2** | TDD red+green: 1 unit test asserting all 4 adapters return `ErrOperationNotSupported` for both methods. | `internal/provider/adapters_audio_test.go` (NEW) | `go test ./internal/provider/ -run TestAdaptersAudioInitiallyUnsupported` |
| **T3** | OpenAPI: `StreamRequest` → `oneOf [ChatStreamRequest, TtsStreamRequest]` discriminated union; add `TtsInput`, `AudioChunkEvent`, `SttInput`, `SttResult` schemas; update `StreamEventEnvelope` union. | `contracts/api/llm-gateway/v1/openapi.yaml` | yamllint + spec parses (manual) |
| **T4** | TDD red: `TestOpenAIAdapter_Transcribe_HappyPath` — `httptest.Server` for audio_url GET (returns dummy bytes) + `/v1/audio/transcriptions` (returns `verbose_json` shape). Assert multipart fields + parsed output. | `adapters_audio_test.go` | test FAILS (Transcribe still returns ErrOperationNotSupported) |
| **T5** | Green: implement `OpenAIAdapter.Transcribe`. New file `internal/provider/openai_audio.go` (split for size). Fetch audio_url (httpx-equivalent in stdlib `http.Client` with 30s timeout + 25MB cap), build multipart with `file` + `model` + optional `language` + `response_format=verbose_json`, POST with bearer auth, parse JSON. | `openai_audio.go` (NEW, ~80 LOC) | T4 test passes |
| **T6** | Add 4 Transcribe error tests: language=auto omits param, audio fetch 404 → wrapped error, audio body >25MB → `LLM_AUDIO_TOO_LARGE`, upstream 401 → wrapped error with status. | `adapters_audio_test.go` | 4 tests pass |
| **T7** | TDD red: `TestOpenAIAdapter_Speak_HappyPath` — mock streams 12KB body in 3 chunks; assert 3 data emits (4KB each, monotonic seq_id) + 1 final emit. | `adapters_audio_test.go` | test FAILS |
| **T8** | Green: implement `OpenAIAdapter.Speak` — POST `/v1/audio/speech` JSON `{model, input, voice, speed, response_format}`, stream body in 4KB chunks → `emit`, end with `Final: true` chunk. | `openai_audio.go` | T7 passes |
| **T9** | Add 2 Speak error tests: emit returns error → adapter aborts upstream + propagates same error; upstream 401 → wrapped error. | `adapters_audio_test.go` | 2 tests pass |
| **T10** | Worker: add `audioJobOperations` map (`stt` only), `runSttJob` impl (resolve creds, call adapter.Transcribe, persist result/error/cancel state). Update `processJob` dispatch to route stt → runSttJob. Defensive: `tts` arriving at worker (shouldn't happen) → fail with `LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS`. | `internal/jobs/worker.go` | `go build ./...` clean |
| **T11** | Worker tests: 4 runSttJob cases (happy, cancellation, ErrOperationNotSupported→failed, upstream error→failed) + regression-lock test asserting `streamableOperations` ∩ `audioJobOperations` = ∅. | `internal/jobs/worker_test.go` | 5 tests pass |
| **T12** | jobs_handler: in `submitJob` validation, reject `operation=tts` with 400 `LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS` + error message hinting `/v1/llm/stream`. Add 2 tests: tts rejected, stt accepted. | `internal/api/jobs_handler.go` + `jobs_handler_test.go` | tests pass |
| **T13** | server.go stream handler: extract `operation` from request body (default `"chat"`), switch chat (existing) vs tts vs reject. New `streamTts` helper: resolve creds + adapter.Speak with emit closure writing SSE `audio-chunk` events; on `ErrOperationNotSupported` → SSE error event; on success → final + done. | `internal/api/server.go` (+~80 LOC) | `go build ./...` clean |
| **T14** | server.go stream handler tests: 4 cases — TtsRoute happy (2 chunks emitted), TtsOperationNotSupported, OperationDefaultIsChat regression, UnknownOperation rejected. | `internal/api/server_test.go` (or stream-specific test file) | 4 tests pass |
| **T15** | SDK models: add `AudioChunkEvent` + update `StreamEvent` union; add `TtsInput`, `TtsStreamRequest` (with `to_request_body()`), `SttInput`, `SttResult` Pydantic models. | `sdks/python/loreweave_llm/models.py` | `pytest sdks/python/tests/` existing 160+ tests still pass |
| **T16** | SDK client: factor existing `stream()` into `_stream_inner(body_dict, user_id)` helper. Add `stream_tts(text, voice, speed, format, model_source, model_ref, user_id)` method using `_stream_inner`. | `sdks/python/loreweave_llm/client.py` | existing stream() tests still pass |
| **T17** | SDK client: add `transcribe(audio_url, model_source, model_ref, language, user_id, timeout_s)` method wrapping `submit_job` + `wait_terminal` + result decode. | `sdks/python/loreweave_llm/client.py` | import works |
| **T18** | SDK tests: NEW `test_audio.py` — 5 tests (transcribe happy, transcribe failure → mapped error, stream_tts happy, stream_tts error → raised, base64 round-trip) using existing `httpx.MockTransport` pattern. | `sdks/python/tests/test_audio.py` (NEW) | all 5 pass |
| **T19** | Update `LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` Phase 5a row: mark ✅ shipped with brief evidence. | `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` | manual diff review |
| **T20** | **VERIFY phase** — full evidence: `go build ./...` clean (provider-registry-service), `go vet ./internal/...` clean, `go test ./internal/...` all green, `pytest sdks/python/tests/` all green, **regression lock**: `go test -run TestDoProxyAudioPathsNotDeprecated` still passes (audio carve-out preserved for 5b), chat-service `pytest services/chat-service/tests/` regression check (no behavioral change to voice yet). | — | output captured into Phase 6 evidence string |

### Dependency graph

```
T1 ─► T2
 │
 ├─► T3 (parallel — pure spec)
 │
 ├─► T4 ─► T5 ─► T6              (OpenAI Transcribe)
 │
 ├─► T7 ─► T8 ─► T9              (OpenAI Speak)
 │
 ├─► T10 ─► T11                  (Worker dispatch)
 │
 ├─► T12                          (jobs_handler reject)
 │
 └─► T13 ─► T14                   (Stream handler branch)
            │
            ▼
   T15 ─► T16 ─► T17 ─► T18      (SDK)
                            │
                            ▼
                          T19 ─► T20
```

### Skip / deferral protocol

- If during BUILD any task discovers more than its planned scope, STOP, reclassify per Anti-Skip rule, notify user.
- If T5 (OpenAI Transcribe green) reveals provider quirks not in `verifySTT`, do NOT inline-add — defer with `D-PHASE5A-WHISPER-QUIRK-<n>` and a regression test for the working subset.
- LM Studio whisper.cpp shape is **out of scope** for 5a — adapter stub stays. If user provides config later, that's a 5a-followup cycle.

### Phase complete-evidence template (for VERIFY)

```
go build ./...:                         clean
go vet ./internal/...:                  clean
go test ./internal/provider/...:        N pass / 0 fail (was X; +Y new)
go test ./internal/jobs/...:            N pass / 0 fail (was X; +Y new)
go test ./internal/api/...:             N pass / 0 fail (was X; +Y new)
pytest sdks/python/tests/:              N pass / 0 fail (was 160; +5 new)
pytest services/chat-service/tests/:    N pass / 0 fail (regression baseline)
TestDoProxyAudioPathsNotDeprecated:     PASS (regression-lock)
```
