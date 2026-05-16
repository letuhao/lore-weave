# Phase 5b Design — chat-service Voice Migration + Audio Proxy Retirement

> **Status**: SHIPPED — BUILD complete. `/review-impl` round 1 caught 3 HIGH + 7 MED + 5 LOW + 1 COSMETIC; ALL 16 folded inline (Fixes #1-#16) BEFORE coding started. BUILD surfaced 2 additional issues (httpx multipart accepts only str/bytes; SDK _raise_http_error didn't consult from_code) — both fixed inline.
> **Cycle**: C-LLM-PHASE-5B
> **Size**: XL (files ≈18 · logic ≈10 · side-effects: 1 contract extension on `/v1/llm/jobs` + 1 deprecation flip on transparent-proxy audio paths + 3 new SDK audio error classes)
> **Plan ref**: [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md §5](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md)
> **Predecessor**: Phase 5a (audio adapter ships STT-via-URL + TTS-via-stream)
> **CLARIFY answers locked**: bytes mode **parallel** with URL mode (zero callers exist for URL mode, but it stays for symmetry); multipart transport on `/v1/llm/jobs`; existing FE envelope shape preserved (sentence-level wrapping stays in chat-service above the gateway); 3 proxy_integration_test.go placeholder-using tests **rewritten** to synthetic path (Fix #7, #8), 4 multipart-specific tests deleted, audio-not-deprecated test flipped (transparent proxy code stays, regression-locks preserved).

---

## 1. Goals

1. **chat-service voice path** stops calling `/internal/proxy/v1/audio/*`. STT + TTS go through the unified LLM gateway via the SDK.
2. **Gateway** gains a second STT submission shape — bytes via `multipart/form-data` on `POST /v1/llm/jobs` — so chat-service doesn't need to upload audio to MinIO + presign a URL just to call STT.
3. **SDK** gains a `transcribe_bytes()` method (or polymorphic `transcribe()`) that accepts `(audio_bytes, content_type)` and uses multipart upload.
4. **Transparent proxy** deny-list extends to `v1/audio/transcriptions` + `v1/audio/speech` — chat-service is the only caller and it just got migrated; with that, **every legacy LLM/audio path on the proxy is retired**.

### Non-goals

- Migrating the FE wire envelope shape (Q3 reversed in CLARIFY — gateway's `AudioChunkEvent` has no sentence concept; chat-service still produces sentence-level boundaries above the gateway layer).
- Removing the gateway's URL-mode STT path (`audio_url` + SSRF guard + `fetchAudioURL`). Stays in parallel.
- MinIO/S3 staging inside the gateway. Internal bytes handoff uses an in-process goroutine closure (see §3.2). Phase 2c (RabbitMQ worker) will revisit.
- Image generation (`image_gen`). Still no caller; defer to Phase 5c.
- LM Studio whisper.cpp adapter (`D-PHASE5A-LMSTUDIO-WHISPER`).

---

## 2. Contract changes

### 2.1 OpenAPI — `POST /v1/llm/jobs` becomes content-type-polymorphic

Today (`contracts/api/llm-gateway/v1/openapi.yaml`):
```yaml
paths:
  /v1/llm/jobs:
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/SubmitJobRequest' }
```

Target — keep the existing JSON request body and add a multipart variant restricted to `operation=stt`:

```yaml
paths:
  /v1/llm/jobs:
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/SubmitJobRequest' }   # all ops
          multipart/form-data:
            schema: { $ref: '#/components/schemas/SubmitSttBytesRequest' }   # stt only
```

New schema:

```yaml
SubmitSttBytesRequest:
  type: object
  required: [operation, model_source, model_ref, audio]
  description: |
    Multipart variant for STT submission with the audio bytes carried
    inline. The gateway streams the file into a per-process buffer
    (no DB persistence), dispatches the worker, and replies 202 with
    the same envelope as the JSON variant.

    Only `operation=stt` accepts this content-type. Other operations
    on `multipart/form-data` return 400 `LLM_INVALID_REQUEST`.

    `chunking` config is NOT accepted on multipart submits — STT runs
    as a single upstream call regardless of audio length. If a
    `chunking` form field is present, the handler returns 400
    `LLM_INVALID_REQUEST: "chunking not accepted on stt multipart submits"`.

    File field name MUST be exactly `"audio"`. Anything else returns
    400 `LLM_INVALID_REQUEST: "expected file field 'audio'; got [<list>]"`
    so caller typos surface immediately (Fix #13).
  properties:
    operation:
      type: string
      enum: [stt]
      description: Must be "stt".
    model_source: { $ref: '#/components/schemas/ModelSource' }
    model_ref:    { type: string, format: uuid }
    language:     { type: string, default: auto }
    trace_id:     { type: string, nullable: true }
    audio:
      type: string
      format: binary
      description: |
        Audio bytes (any format Whisper accepts: webm, mp3, wav, ogg,
        m4a, flac). 25MB hard cap matches OpenAI Whisper upload limit.
        Bytes >25MB are rejected with 413 + `LLM_AUDIO_TOO_LARGE`.
```

`SttInput` schema (JSON variant) **stays unchanged** — `audio_url` remains the JSON-mode entrypoint. The two modes are mutually exclusive by Content-Type.

**Content-Type dispatch — RFC-conformant parsing (Fix #4):**

Handler uses `mime.ParseMediaType(r.Header.Get("Content-Type"))` (stdlib lowercases + strips params) and dispatches on `mediaType`:

| mediaType | Path |
|---|---|
| `"application/json"` | existing JSON path (Phase 5a) — all operations |
| `"multipart/form-data"` | new bytes path (Phase 5b) — **stt only**; other ops → 400 `LLM_INVALID_REQUEST` |
| anything else | 415 `LLM_INVALID_REQUEST: "unsupported Content-Type"` |

This handles RFC 2045 case-insensitivity (`MULTIPART/FORM-DATA`) and parameter-ordering variation (`multipart/form-data; charset=utf-8; boundary=...`) that naive `strings.HasPrefix` would miss.

**25MB cap mechanism — explicit (Fix #1):**

```go
const stt MaxAudioBytes = 25 * 1024 * 1024  // matches provider.MaxAudioBytes from 5a
const sttMultipartOverhead = 32 * 1024      // multipart envelope, headers, boundaries
r.Body = http.MaxBytesReader(w, r.Body, sttMaxAudioBytes + sttMultipartOverhead)

if err := r.ParseMultipartForm(sttMaxAudioBytes); err != nil {
    var maxBytesErr *http.MaxBytesError
    if errors.As(err, &maxBytesErr) {
        writeError(w, http.StatusRequestEntityTooLarge, "LLM_AUDIO_TOO_LARGE",
            "audio exceeds 25MB cap")
        return
    }
    writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
        "multipart parse failed: " + err.Error())
    return
}
```

Note: `ParseMultipartForm(maxMemory)` is the in-memory threshold, NOT a cap — `http.MaxBytesReader` is what actually enforces the size limit. Stdlib will spill to `os.TempDir()` for the in-memory cap value, which is undesirable for the audio path — we want bytes in RAM for the goroutine closure handoff (§3.2). To force in-memory, set `maxMemory = sttMaxAudioBytes` so the entire 25MB stays in `r.MultipartForm.File["audio"][0]`'s `*multipart.FileHeader` and we read it via `Open() → io.ReadAll` capped at `sttMaxAudioBytes`. Belt-and-suspenders: adapter-level `MaxAudioBytes` check in `openai_audio.go::Transcribe` (Phase 5a, unchanged) catches any 26MB byte slice that somehow gets past the handler.

**Acceptance tests required (T8 expanded):**
- 25MB exactly → 202 accepted
- 25MB + 1 byte → 413 `LLM_AUDIO_TOO_LARGE`
- 26MB → 413 `LLM_AUDIO_TOO_LARGE`
- `Content-Type: MULTIPART/FORM-DATA; boundary=b` → 202 accepted (case-insensitivity)
- `chunking` form field present → 400 `LLM_INVALID_REQUEST: "chunking not accepted..."`
- Audio uploaded under field name `"file"` → 400 `"expected file field 'audio'; got [file, ...]"`

### 2.2 Adapter interface — `TranscribeInput` gains bytes fields

`services/provider-registry-service/internal/provider/adapters.go`:

```go
type TranscribeInput struct {
    // URL mode (Phase 5a) — gateway-fetchable HTTPS URL. SSRF-guarded.
    AudioURL string

    // Bytes mode (Phase 5b) — audio bytes already in adapter's address
    // space. Set by jobs_handler when the request arrived as multipart.
    // When non-nil, AudioURL is ignored.
    AudioBytes  []byte
    ContentType string  // e.g. "audio/webm", "audio/wav"; informs filename ext

    Language string
}
```

Exclusion rule (enforced in adapter at the top of `Transcribe`) — **exactly one** of `AudioURL` / `AudioBytes` must be set. Both set OR both empty is an invariant violation, returned as the new `ErrTranscribeInputInvalid` sentinel (mapped by `classifyAudioError` → `LLM_INVALID_REQUEST`). Adapter pre-check fires BEFORE the bytes-vs-URL switch so neither branch silently wins (Fix #2):

```go
// New sentinel in adapters.go
var ErrTranscribeInputInvalid = fmt.Errorf("transcribe input invalid")

// In openai_audio.go::Transcribe — exactly-one check FIRST
hasURL := input.AudioURL != ""
hasBytes := input.AudioBytes != nil
if hasURL == hasBytes {
    // Both set OR both empty — invariant violation
    if hasURL {
        return TranscribeOutput{}, Usage{}, fmt.Errorf("%w: both AudioURL and AudioBytes set; pick one", ErrTranscribeInputInvalid)
    }
    return TranscribeOutput{}, Usage{}, fmt.Errorf("%w: no audio source", ErrTranscribeInputInvalid)
}

// Now dispatch — exactly one is set, no preference logic
var audioBytes []byte
var contentType string
if hasBytes {
    if len(input.AudioBytes) > MaxAudioBytes {
        return TranscribeOutput{}, Usage{}, fmt.Errorf("%w: %d bytes", ErrAudioTooLarge, len(input.AudioBytes))
    }
    audioBytes = input.AudioBytes
    contentType = input.ContentType
} else {
    var err error
    audioBytes, contentType, err = fetchAudioURL(ctx, a.client, input.AudioURL)
    if err != nil { return TranscribeOutput{}, Usage{}, err }
}
// rest of Transcribe is unchanged — multipart build / POST / parse
```

**Acceptance tests required (T4 expanded):**
- `(URL="", Bytes=nil)` → `ErrTranscribeInputInvalid` ("no audio source")
- `(URL="https://...", Bytes=[1,2,3])` → `ErrTranscribeInputInvalid` ("both ... set; pick one")
- `(URL="https://...", Bytes=nil)` → URL path (existing 5a behavior)
- `(URL="", Bytes=[1,2,3])` → bytes path
- `(URL="", Bytes=[26MB])` → `ErrAudioTooLarge`

### 2.3 Worker — pass bytes through goroutine closure, never persist to DB

Audio bytes from a multipart submit MUST NOT hit the `llm_jobs.input` JSONB column (25MB row + 33% base64 bloat = 33MB rows; bad caches; bad replication; visible in admin tooling). Instead:

1. `jobs_handler.doSubmitJob` parses multipart on Content-Type match.
2. The metadata fields (`operation`, `model_source`, `model_ref`, `language`, `trace_id`) build a synthetic JSON `input` payload: `{"audio_inline": true, "content_type": "audio/webm", "language": "auto"}`. **No `audio_bytes_b64` field.**
3. The file field bytes are captured into a `[]byte` in the handler's stack.
4. `jobs.Insert` persists the synthetic input (no bytes) and returns `jobID`.
5. `go func() { worker.ProcessAudio(bgCtx, jobID, userID, audioBytes, contentType, ...) }()` — bytes live in goroutine closure for the duration of the job.
6. Worker passes bytes through to `adapter.Transcribe(... TranscribeInput{AudioBytes: bytes, ContentType: ct})`.

This adds **one new public worker entry** `Worker.ProcessAudioInline(ctx, jobID, ownerUserID, modelSource, modelRef, language string, audioBytes []byte, contentType string)`. The existing `Worker.Process` signature is unchanged. ProcessAudioInline calls `processAudioJob` with an `inputMap` synthesized in-handler — no DB roundtrip for bytes.

**Limitation**: this binds the bytes mode to the in-process worker goroutine pattern. Phase 2c (RabbitMQ migration) will need MinIO staging — `D-PHASE2C-AUDIO-STAGING` deferred item.

### 2.4 SDK Python — `transcribe()` polymorphism

`sdks/python/loreweave_llm/client.py`:

```python
async def transcribe(
    self,
    audio: str | bytes | bytearray | memoryview,   # URL string OR bytes-like buffer
    *,
    model_source: ModelSource,
    model_ref: str,
    language: str = "auto",
    content_type: str | None = None,   # required when audio is bytes-like
    user_id: str | None = None,
    poll_interval_s: float = 0.25,
    max_poll_interval_s: float = 5.0,
) -> SttResult:
```

Dispatch (Fix #5 — accept any Python buffer protocol):
- `isinstance(audio, str)` → existing JSON-body path (URL mode, Phase 5a).
- `isinstance(audio, (bytes, bytearray, memoryview))` → multipart upload path (bytes mode, Phase 5b). `content_type` REQUIRED; raises `LLMInvalidRequest("content_type required for bytes-like audio")` if missing. httpx natively accepts all three in `files={...}` (no zero-copy lost for `memoryview`).
- anything else → `LLMInvalidRequest("audio must be str (URL) or bytes-like")`.

The multipart path:
1. Build `httpx.AsyncClient` `files={"audio": ("audio.bin", audio, content_type)}` + `data={"operation": "stt", "model_source": ..., "model_ref": ..., "language": ...}`.
2. POST to `/v1/llm/jobs` (or `/internal/llm/jobs` per auth_mode) — receives 202 with `job_id`.
3. Reuse existing `wait_terminal(transient_retry_budget=0)` loop (Phase 5a).
4. Decode `SttResult` on `status=completed`.

### 2.4.1 New SDK error classes (Fix #3)

Phase 5a's audio-specific gateway codes were emitted but unmapped — SDK callers got generic `LLMError` for every audio failure. Phase 5b adds three named exception classes so callers can branch:

```python
# sdks/python/loreweave_llm/errors.py — additions

class LLMAudioTooLarge(LLMError):
    """Caller-side audio exceeds the gateway's 25MB cap.
    Maps from gateway code: LLM_AUDIO_TOO_LARGE.
    """

class LLMAudioFetchFailed(LLMError):
    """URL-mode: gateway couldn't GET the audio_url (4xx/5xx, DNS, transport).
    Maps from gateway code: LLM_AUDIO_FETCH_FAILED.
    """

class LLMAudioURLDisallowed(LLMError):
    """URL-mode: audio_url host resolves to a disallowed IP range (SSRF guard).
    Maps from gateway code: LLM_AUDIO_URL_DISALLOWED.
    """
```

`from_code()` mapping table extended:
| code | exception |
|---|---|
| `LLM_AUDIO_TOO_LARGE` | `LLMAudioTooLarge` |
| `LLM_AUDIO_FETCH_FAILED` | `LLMAudioFetchFailed` |
| `LLM_AUDIO_URL_DISALLOWED` | `LLMAudioURLDisallowed` |

Exports added to `loreweave_llm.__init__`. Existing Phase 5a tests against `from_code` for these three codes are EXPECTED to currently return generic `LLMError` — a regression-lock test in 5b pins the new specific classes (`test_audio_errors_have_specific_classes`).

### 2.5 Transparent proxy deny-list

`services/provider-registry-service/internal/api/server.go::isDeprecatedProxyPath` — add 2 entries:
```go
deprecated := []string{
    "v1/chat/completions",
    "v1/completions",
    "v1/embeddings",
    "v1/audio/transcriptions",   // Phase 5b — migrated to /v1/llm/jobs
    "v1/audio/speech",           // Phase 5b — migrated to /v1/llm/stream operation=tts
}
```

Update the function docstring + error-message hint to point at the new SDK methods.

### 2.6 chat-service voice path

`services/chat-service/app/services/voice_stream_service.py`:

**Client instantiation pattern — match sibling stream_service.py (Fix #9):**

The existing sibling [stream_service.py:68](services/chat-service/app/services/stream_service.py#L68) creates a fresh `Client(base_url=..., auth_mode='internal', internal_token=..., user_id=user_id)` per call. Voice path aligns with this — per-call instantiation, not a singleton. Connection-pool churn (one httpx pool init per voice turn) is a known cost; deviating to a singleton would be a NEW pattern requiring its own justification + reviewer attention. If pool churn ever profiles as a hot path, lift to a singleton THEN, with rationale.

**STT replacement** (`_transcribe_audio`):
```python
from loreweave_llm import Client, SttResult, LLMAudioTooLarge

client = Client(
    base_url=settings.provider_registry_internal_url,
    auth_mode="internal",
    internal_token=settings.internal_service_token,
    user_id=user_id,
)
try:
    result: SttResult = await client.transcribe(
        audio_bytes,                     # raw bytes — bytes-mode (Phase 5b)
        model_source=stt_model_source,
        model_ref=stt_model_ref,
        language=stt_language or "auto",
        content_type=content_type,
    )
finally:
    await client.aclose()
return result.text, result.duration_ms
```

`_transcribe_audio` signature drops `stt_model_name` (no longer needed — gateway resolves via `model_ref` → user_model row).

**Dead-code removal (Fix #11):** lines 215, 220-223 of [voice_stream_service.py](services/chat-service/app/services/voice_stream_service.py#L215) currently resolve `stt_creds.provider_model_name` and `tts_creds.provider_model_name` for the legacy proxy path. After migration these are dead — DELETE the `provider.resolve()` calls and the `stt_model_name` / `tts_model_name` locals. Caller surface for `_transcribe_audio` and `_generate_tts_chunks` drops both args. Save a regression by adding a grep-lock test: `tests/test_voice_no_dead_resolution.py` asserts `provider.resolve` is NOT called in the voice path.

**TTS replacement** (`_generate_tts_chunks`):
```python
from loreweave_llm import Client, AudioChunkEvent, DoneEvent

client = Client(
    base_url=settings.provider_registry_internal_url,
    auth_mode="internal",
    internal_token=settings.internal_service_token,
    user_id=user_id,
)
try:
    chunk_index = 0
    async for ev in client.stream_tts(
        text=text,
        model_source=tts_model_source,
        model_ref=tts_model_ref,
        voice=tts_voice,
    ):
        if isinstance(ev, AudioChunkEvent):
            import base64
            raw = base64.b64decode(ev.data)
            # Preserve existing FE envelope (Q3 — keep sentenceIndex shape)
            fe_event = {
                "sentenceIndex": sentence_index,
                "chunkIndex": chunk_index,
                "data": ev.data,                # already base64
                "final": ev.final,
            }
            yield fe_event, raw
            chunk_index += 1
        # DoneEvent → loop exits
finally:
    await client.aclose()
```

Drop the `httpx` import from this module's voice path (still imported elsewhere in chat-service for non-voice flows).

### 2.7 Tests touched

| File | Change |
|------|--------|
| `services/provider-registry-service/internal/provider/adapters_audio_test.go` | +3 tests for bytes-mode Transcribe (happy / oversize / content-type→ext) |
| `services/provider-registry-service/internal/jobs/worker_audio_test.go` | +2 tests for `ProcessAudioInline` (happy / cancellation) |
| `services/provider-registry-service/internal/api/jobs_router_test.go` | +3 tests for multipart submit (happy / oversize 413 / wrong-op-on-multipart 400) |
| `services/provider-registry-service/internal/api/proxy_deprecation_test.go` | flip 3 audio cases `false → true` |
| `services/provider-registry-service/internal/api/proxy_integration_test.go` | DELETE 9 tests using `v1/audio/speech` as placeholder; flip `TestDoProxyAudioPathsNotDeprecated` to a row in `TestDoProxyDeprecatedPathsReturn410`; net delta ≈−250 lines |
| `services/provider-registry-service/internal/api/proxy_router_test.go` | swap `v1/audio/speech` ref to a non-deprecated path (or delete if it was just exercising route match) |
| `sdks/python/tests/test_audio.py` | +4 tests for bytes-mode transcribe (happy / missing content_type / oversize / dispatches URL vs bytes correctly) |
| `services/chat-service/tests/test_voice_router.py` | swap httpx mocks → SDK mocks (`patch("loreweave_llm.Client")`) |

---

## 3. Architecture & data flow

### 3.1 Sequence — voice send (chat-service → gateway → OpenAI Whisper)

> **Path note (Fix #16):** the diagram shows logical hops. chat-service routes via SDK `auth_mode="internal"` → `/internal/llm/jobs` (X-Internal-Token + `user_id` query param). The handler-side change in T7 covers BOTH `/v1/llm/jobs` (JWT) AND `/internal/llm/jobs` (internal token) because they share `doSubmitJob` ([jobs_handler.go:71](services/provider-registry-service/internal/api/jobs_handler.go#L71)).

```
FE                chat-service              gateway                 OpenAI
 │                     │                       │                       │
 │ POST /voice-message │                       │                       │
 │ (audio.webm)        │                       │                       │
 │────────────────────▶│                       │                       │
 │                     │ POST /internal/llm/jobs                       │
 │                     │ multipart/form-data   │                       │
 │                     │   operation=stt       │                       │
 │                     │   audio=<bytes>       │                       │
 │                     │──────────────────────▶│                       │
 │                     │                       │ insert llm_jobs row   │
 │                     │                       │ (NO bytes in input)   │
 │                     │ 202 {job_id}          │                       │
 │                     │◀──────────────────────│                       │
 │                     │                       │                       │
 │                     │ poll GET /jobs/{id}   │  goroutine spawns:    │
 │                     │──────────────────────▶│  ProcessAudioInline   │
 │                     │                       │  (bytes via closure)  │
 │                     │                       │                       │
 │                     │                       │   POST /v1/audio/     │
 │                     │                       │   transcriptions      │
 │                     │                       │   (multipart)         │
 │                     │                       │──────────────────────▶│
 │                     │                       │   {text, language,    │
 │                     │                       │    duration}          │
 │                     │                       │◀──────────────────────│
 │                     │ {status:completed,    │  finalize job         │
 │                     │  result:{...}}        │                       │
 │                     │◀──────────────────────│                       │
 │                     │                       │                       │
 │                     │ POST /internal/llm/stream  operation=tts      │
 │                     │ {text, voice, ...}    │                       │
 │                     │──────────────────────▶│                       │
 │                     │                       │ POST /v1/audio/speech │
 │                     │                       │──────────────────────▶│
 │                     │   SSE audio-chunk     │   binary stream       │
 │                     │   (gateway shape)     │◀──────────────────────│
 │                     │◀══════════════════════│                       │
 │  SSE audio-chunk    │                       │                       │
 │  (FE envelope —     │                       │                       │
 │   sentenceIndex)    │                       │                       │
 │◀════════════════════│                       │                       │
```

Key invariants:
- Audio bytes traverse exactly TWO hops: client→chat-service→gateway. Gateway streams them once into multipart, posts to upstream, drops.
- DB row for the STT job has 80 bytes of metadata, not 33MB of base64.
- Chat-service's sentence-level wrapping (sentenceIndex/chunkIndex/final) is applied on top of each `AudioChunkEvent` from the gateway — gateway is sentence-agnostic.

### 3.2 In-process bytes handoff — why no global store

Considered three options for moving audio bytes from handler to worker:

| Option | Pros | Cons | Decision |
|---|---|---|---|
| A. Goroutine closure capture | No new state, cleanup via GC, bytes-lifetime = job-lifetime | Limited to single-process worker | ✅ Picked |
| B. Base64 in `llm_jobs.input` JSONB | Works under RabbitMQ migration | 33% bloat (25→33MB rows), visible in admin tooling, TOAST overhead | ❌ |
| C. MinIO staging | Works under RabbitMQ, decoupled | New infra dep on provider-registry-service, +4 env vars, +2 new tests | ❌ (overkill for current single-process worker) |

Goroutine closure (option A) is chosen because:
- Bytes live in the goroutine's stack; freed automatically when goroutine returns.
- No new shared mutable state (no `sync.Map` registry, no TTL sweeper).
- Phase 2c migration to RabbitMQ workers can revisit with MinIO staging — defer item `D-PHASE2C-AUDIO-STAGING`.

### 3.3 Backward-compat — URL mode stays in parallel

5a's URL-mode STT path (audio_url + SSRF guard + `fetchAudioURL`) survives unchanged. The Adapter interface gains the bytes branch via `switch input.AudioBytes != nil`. A `(URL set, Bytes set)` AND `(neither set)` both return `LLM_AUDIO_FETCH_FAILED` with diagnostic message.

Rationale (per CLARIFY Q1 final): keeping URL mode preserves Phase 5a's shipped contract & tests; the 33-test 5a baseline is undisturbed; the new bytes path is purely additive.

---

## 4. Migration & deletion details

### 4.1 What gets REWRITTEN vs. DELETED from proxy_integration_test.go

The proxy code (model-name rewrite, 4MiB body cap, auth-header forwarding) stays alive in `server.go::doProxy` as defense-in-depth + 410 enforcement. Deleting the regression-locks for that code wholesale loses real coverage (Fix #7, #8). Strategy:

**KEPT (rewrite to use synthetic placeholder path):**
The synthetic placeholder is `v1/responses` — an OpenAI roadmap path NOT in the deny-list, will never collide with current routes. Add a `// Phase 5b — placeholder path; not real, not deprecated` comment.

1. `TestDoProxyRewritesJSONModelField` — KEPT, swap `v1/audio/speech` → `v1/responses`. Pins K17.2a model-name rewrite behavior (Fix #7).
2. `TestDoProxyForwardsAuthorizationHeader` — KEPT, swap path. Pins decrypted-API-key injection.
3. `TestDoProxyBodyTooLargeRejected` — KEPT, swap path. Pins the 4MiB body cap (Fix #8).

**DELETED (audio-specific, no synthetic equivalent makes sense):**

4. The 4-test block around `proxy_integration_test.go:261-298` (multipart-specific audio tests) — these were exercising the multipart-pass-through-unchanged path that 5b retires.
5. `TestDoProxyAudioPathsNotDeprecated` (`:608-640`) — flip purpose: replaced by 2 new rows in `TestDoProxyDeprecatedPathsReturn410`'s `cases` table.

**ADDED:**
- `TestDoProxyDeprecatedPathsReturn410` extended with `{audio-transcriptions, v1/audio/transcriptions}` and `{audio-speech, v1/audio/speech}` rows.

**Net test delta:** −4 deleted + 3 rewritten (no count change) + 2 new rows = net −2 tests vs. the earlier "delete 9" plan, which preserves the regression-locks that matter.

**proxy_router_test.go (Fix #10):** [proxy_router_test.go:111](services/provider-registry-service/internal/api/proxy_router_test.go#L111) — before T17, read the containing test function and classify:
- If the test exercises ROUTE-MATCHING / JWT-AUTH MECHANICS with `v1/audio/speech` as an arbitrary target → swap to `v1/responses`.
- If the test specifically asserts "audio paths reach `doProxy`" → delete and add to `TestDoProxyDeprecatedPathsReturn410`.

The design defers the call to BUILD-time (T17 task description must include this disambiguation step).

**Why "tests don't pretend to exercise live traffic any more" is wrong:** the proxy code is alive; deleting the only callers of that code via tests means future-Claude can't see the contract. Synthetic-placeholder strategy preserves the contract without lying about caller traffic.

### 4.2 What `D-PHASE5A-*` items get closed by this cycle

| Item | Status after 5b |
|---|---|
| `D-PHASE5A-LIVE-SMOKE` | Closed — chat-service voice path now LIVE-smokes the gateway STT+TTS end-to-end via real user voice |
| `D-PHASE5A-STREAM-INTEGRATION-TESTS` | Still deferred — these are about deeper `/v1/llm/stream` integration coverage; 5b adds happy-path live-smoke but not the deep-DB tests |
| `D-PHASE5A-LMSTUDIO-WHISPER` | Still deferred — LM Studio adapter unchanged |
| `D-PHASE5A-SDK-TTS-EVENT-FILTER` | Still deferred — accepted-and-documented behavior |
| `D-PHASE5A-SDK-TRANSCRIBE-RETRY-BUDGET` | Still deferred |
| `D-PHASE5A-OPENAPI-EVENT-FIELD` | Still deferred — pre-existing pattern |

New deferred items expected from 5b:
- `D-PHASE2C-AUDIO-STAGING` — when RabbitMQ worker migration happens, replace goroutine closure with MinIO staging
- `D-PHASE5B-CANCEL-NO-OP-AUDIO-RAM` — DELETE /v1/llm/jobs/{id} doesn't cancel the worker goroutine; up to 25MB × `SttJobTimeout(5min)` of RAM pinned per cancelled-but-still-running STT job. Phase 6 worker-context hardening fixes (Fix #6 deferred).
- Possibly `D-PHASE5B-SSRF-GUARD-DEAD-CODE` if no caller ever uses URL-mode STT — track for a future cycle to consider deleting

---

## 5. Build plan (PLAN phase)

Decompose into bite-sized tasks. Per CLAUDE.md L+/XL rules, ordering is contract-first → adapter → worker → handler → SDK → consumer (chat-service) → proxy retirement → tests-throughout.

| # | Task | Files | Size |
|---|------|-------|------|
| T1 | OpenAPI: add `SubmitSttBytesRequest` schema + `multipart/form-data` request body variant; document `chunking` rejection + `audio` field-name spec | `contracts/api/llm-gateway/v1/openapi.yaml` | XS |
| T2 | Adapter types: `TranscribeInput` +AudioBytes/+ContentType; **new sentinel `ErrTranscribeInputInvalid`**; document exclusion rule | `services/provider-registry-service/internal/provider/adapters.go` | XS |
| T3 | `openai_audio.go::Transcribe` — **exactly-one pre-check (Fix #2)** + bytes branch (skip fetchAudioURL) + 25MB check; URL branch unchanged | `services/provider-registry-service/internal/provider/openai_audio.go` | S |
| T4 | Adapter tests: 5 cases (URL+Bytes both set → invariant, both empty → invariant, bytes happy, oversize-rejected, content-type→ext); **+1 classifyAudioError test for new sentinel → LLM_INVALID_REQUEST** | `services/provider-registry-service/internal/provider/adapters_audio_test.go` | S |
| T5 | Worker: `ProcessAudioInline(audioBytes, contentType, ...)` entrypoint that synthesizes inputMap + calls runSttJob with `TranscribeInput.AudioBytes` set; **classifyAudioError extended with new sentinel branch** | `services/provider-registry-service/internal/jobs/worker_audio.go` (+ small change to worker.go if needed) | S |
| T6 | Worker tests: ProcessAudioInline happy + cancellation + invariant-violation classification | `services/provider-registry-service/internal/jobs/worker_audio_test.go` | S |
| T7 | Handler: `mime.ParseMediaType` dispatch (Fix #4); `http.MaxBytesReader` cap + `*http.MaxBytesError` catch (Fix #1); reject `chunking` form field (Fix #12); explicit field-name error (Fix #13); spawn goroutine with bytes-in-closure; reject non-stt operation on multipart with 400 | `services/provider-registry-service/internal/api/jobs_handler.go` | M |
| T8 | Handler tests: **6 cases** (multipart happy, 25MB-exact accept, 25MB+1 → 413, 26MB → 413, MULTIPART/FORM-DATA case-insensitive → 202, chunking-field-present → 400, file-field=`file` → 400 with field-name hint, wrong-op-on-multipart → 400) | `services/provider-registry-service/internal/api/jobs_router_test.go` | M |
| T9 | SDK: polymorphic `transcribe(audio: str\|bytes\|bytearray\|memoryview, ..., content_type=None)` — isinstance covers memoryview (Fix #5) | `sdks/python/loreweave_llm/client.py` | S |
| T10 | **SDK errors: add `LLMAudioTooLarge`/`LLMAudioFetchFailed`/`LLMAudioURLDisallowed` classes + register in `from_code()` mapping** (Fix #3) | `sdks/python/loreweave_llm/errors.py` + `sdks/python/loreweave_llm/__init__.py` | S |
| T11 | SDK tests: **7 cases** (bytes happy, bytearray happy, memoryview happy, bytes-without-content_type → LLMInvalidRequest, oversize → LLMAudioTooLarge, dispatch correctness str-vs-bytes, **regression-lock `test_audio_errors_have_specific_classes`**) | `sdks/python/tests/test_audio.py` | S |
| T12 | chat-service `voice_stream_service.py`: replace `_transcribe_audio` with SDK bytes call (per-call Client per Fix #9); replace `_generate_tts_chunks` with SDK stream_tts + envelope re-wrap; **DELETE dead `stt_creds.provider_model_name` + `tts_creds.provider_model_name` resolutions** (Fix #11) | `services/chat-service/app/services/voice_stream_service.py` | M |
| T13 | chat-service tests: swap httpx mocks → SDK Client mocks; **+1 grep-lock test `test_voice_no_dead_resolution.py` asserting `provider.resolve` not called in voice path** (Fix #11); ensure 177 baseline holds | `services/chat-service/tests/test_voice_router.py` + new `test_voice_no_dead_resolution.py` | S |
| T14 | provider-registry server.go: add 2 audio paths to `isDeprecatedProxyPath` deny-list; update docstring | `services/provider-registry-service/internal/api/server.go` | XS |
| T15 | proxy_deprecation_test.go: flip 3 audio cases false→true | `services/provider-registry-service/internal/api/proxy_deprecation_test.go` | XS |
| T16 | proxy_integration_test.go: **REWRITE 3 placeholder-using tests to `v1/responses` synthetic path** (Fix #7, #8); DELETE 4 multipart-specific tests + 1 audio-not-deprecated test; ADD audio rows to TestDoProxyDeprecatedPathsReturn410 | `services/provider-registry-service/internal/api/proxy_integration_test.go` | M |
| T17 | proxy_router_test.go: **read line 111's containing test, classify (route-mechanic vs. audio-specific), rewrite or delete per Fix #10** | `services/provider-registry-service/internal/api/proxy_router_test.go` | XS |
| T18 | Doc UPDATES: `LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` row marked ✅ shipped; design doc status flipped to SHIPPED. **SESSION_PATCH update ships IN THE SAME COMMIT AS CODE per CLAUDE.md Phase 10/11** (Fix #15) — not a separate task. | `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` | XS |

Total: ≈16 code files + 3 doc files (was 15+3 → +1 for SDK errors.py + new chat-service test file). Build order: T1→T4 (gateway adapter foundation), T5→T8 (gateway worker+handler), T9→T11 (SDK + errors), T12→T13 (chat-service + dead-code removal lock), T14→T17 (proxy retirement), T18 (docs — SESSION_PATCH inline in commit).

---

## 6. Open questions / risks

| # | Question | Answer / mitigation |
|---|---|---|
| Q1 | Should `audio_url` mode be removed once chat-service migrates? | Keep in parallel for 5b (CLARIFY answer). Track as `D-PHASE5B-SSRF-GUARD-DEAD-CODE` for a future delete-if-still-no-caller cycle. |
| Q2 | What if Whisper rejects the multipart file due to filename-extension mismatch? | `audioFilenameFromContentType()` (Phase 5a) handles that — it picks the right `.webm/.mp3/...` filename based on Content-Type. Bytes mode reuses it. |
| Q3 | What if chat-service sends >25MB audio? | THREE enforcement points: (a) FE limits before upload; (b) handler `http.MaxBytesReader` rejects with 413 + `LLM_AUDIO_TOO_LARGE` (Fix #1); (c) adapter belt-and-suspenders check. |
| Q4 | TTS — chat-service still does sentence-level chunking + N TTS calls. Is this still optimal vs. one big TTS call? | YES. Sentence-level lets us interleave `audio-skip` events for code blocks ([useAutoTTS.ts:148](frontend/src/features/chat/hooks/useAutoTTS.ts#L148)). Single-shot TTS would lose this. |
| Q5 | What about `D-PHASE5A-LIVE-SMOKE`? | Closes ONLY IF the QC-phase live smoke runs AND passes against a registered OpenAI whisper-1 + tts-1 (per §7 acceptance criteria). If the smoke is skipped or fails, the deferred item REMAINS OPEN (Fix #14). |
| Q6 | What happens to a 25MB audio in the worker goroutine if the user calls DELETE /v1/llm/jobs/{id}? | Worker uses `bgCtx := context.Background()` — cancel handler flips DB state but can't reach the goroutine's ctx. Bytes stay in the goroutine closure for up to `SttJobTimeout = 5min`. Under sustained-cancel usage (10 cancels in a row) ≈250MB RAM pinned for 5min. **Accepted-and-documented** as `D-PHASE5B-CANCEL-NO-OP-AUDIO-RAM`. Phase 6 worker-context hardening will thread a cancel-registry; deferring is the pragmatic choice for 5b (Fix #6). |

---

## 7. Acceptance criteria (QC phase)

- [ ] `go build ./...` clean at gateway
- [ ] `go vet ./...` clean
- [ ] `go test -count=1 ./services/provider-registry-service/...` ALL GREEN (delta: +8 new tests, −12 deleted proxy tests → net −4)
- [ ] `pytest sdks/python/tests/` 167+4 = 171 passed
- [ ] `pytest services/chat-service/tests/ -q` baseline 177 PASS, 0 failures
- [ ] `grep -rn "/internal/proxy/v1/audio" services/` returns ONLY test-file references — no application code path uses it
- [ ] `grep -rn "httpx" services/chat-service/app/services/voice_stream_service.py` — should not return import lines (httpx no longer used in voice path)
- [ ] LIVE smoke: chat-service voice round-trip with a registered OpenAI whisper-1 + tts-1 produces real audio playback in the FE — confirm in browser
- [ ] `/review-impl` on the design doc returns no HIGH-severity findings
- [ ] `/review-impl` on the post-BUILD code returns no HIGH findings; MEDs fixed inline before commit

---

## 8. Phase 5c preview

After 5b ships:
- `image_gen` adapter — when first caller appears. Story: video-gen-service or knowledge-service's wiki-illustration pipeline.
- `D-PHASE2C-AUDIO-STAGING` — handled as part of Phase 2c (RabbitMQ worker migration).
- `D-PHASE5B-SSRF-GUARD-DEAD-CODE` — clean up URL-mode STT if no caller ever materializes.
