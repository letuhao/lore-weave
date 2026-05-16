# Phase 5e-β.2 — `audio_gen` adapter + MinIO staging + Python/Go SDK + book-service audio.go migration

> **Status:** DESIGN (post-/review-impl — 4 HIGH + 11 MED + 13 LOW + 3 COSMETIC folded inline)
> **Cycle:** Phase 5e-β.2 (cycle 3 of session 56)
> **Predecessor:** [Phase 5e-β.1](LLM_PIPELINE_PHASE5E_BETA1_DESIGN.md) — Go SDK greenfield + book-service media.go migration shipped at `9c607146`
> **Successor:** Phase 5f — `services/video-gen-service/` deletion + api-gateway-bff `/v1/video-gen/*` retirement + FE migration

## 1. Goals

1. Add `audio_gen` operation to the unified gateway as a **batch, job-mode** companion to the existing streaming `tts` operation:
   - `POST /v1/llm/jobs operation=audio_gen` → `adapter.GenerateAudio` → `AudioGenResult` with N data entries (one per input text)
   - Distinct from streaming `tts` (used by chat-service voice for real-time playback); batch is for store-to-disk audio (book chapter narration)
2. Implement **BOTH** response modes per CLARIFY decision:
   - `b64_json` (default): base64-encoded audio inline in result
   - `url` (NEW pattern): gateway stages binary in MinIO + returns a **public** URL constructed against `MINIO_EXTERNAL_URL` (mirrors book-service's existing `loreweave-media` bucket pattern). /review-impl(DESIGN) HIGH#1 — presigned URLs with host-rewrite break SigV4 signatures; we use a public-read bucket with UUID-keyed objects (unguessable, same security tradeoff book-service already accepts for chapter media).
3. Add MinIO infrastructure to provider-registry-service (NEW dependency) with `loreweave-audio-cache` bucket, **public-read bucket policy** + server-side lifecycle policy for auto-cleanup
4. Extend Python SDK with `Client.generate_audio()` operation-based method
5. Extend Go SDK (`sdks/go/llmgw/`) with `GenerateAudio` method + types + sentinels
6. Migrate `services/book-service/internal/api/audio.go::generateAudio` from direct `/internal/credentials/` + `/v1/audio/speech` httpx pattern to use Go SDK's `GenerateAudio()`. Per-block-loop preserved at caller side; gateway batches internally per submit.
7. Drop `PROVIDER_REGISTRY_SERVICE_URL` from book-service config (no longer needed after audio.go migrates — Phase 5e-β.1 kept it specifically for audio.go)

## 2. Why this cycle exists

- **Path B step 5** of the LLM-pipeline unification: 5a-d shipped gateway adapters for chat/stt/tts-stream/image_gen/video_gen; 5e-α + 5e-β.1 migrated video-gen-service (Python) + book-service media.go (Go). This is the LAST caller migration before 5f's BFF retirement.
- After this: book-service has ZERO direct provider httpx calls; `PROVIDER_REGISTRY_SERVICE_URL` config field becomes unused; the unified-gateway invariant covers all platform LLM/audio/image/video operations.
- **Gateway audio is currently split between `Speak` (streaming TTS via `/v1/llm/stream`) and `Transcribe` (STT via `/v1/llm/jobs`).** Adding `audio_gen` (batch TTS via `/v1/llm/jobs`) completes the matrix.

## 3. Operation matrix (post-cycle)

| Operation | Endpoint | Mode | Caller |
|-----------|----------|------|--------|
| `chat` / `completion` | `/v1/llm/stream` | SSE stream | chat-service text |
| `tts` | `/v1/llm/stream` | SSE stream (audio-chunk events) | chat-service voice (real-time) |
| `stt` | `/v1/llm/jobs` | Job poll | chat-service voice (transcription) |
| `image_gen` | `/v1/llm/jobs` | Job poll | book-service media + video-gen-service |
| `video_gen` | `/v1/llm/jobs` | Job poll | video-gen-service |
| **`audio_gen` (NEW)** | **`/v1/llm/jobs`** | **Job poll, batch** | **book-service audio (NEW caller)** |

The two TTS paths (`tts` streaming + `audio_gen` batch) coexist — same upstream (OpenAI `/v1/audio/speech`) but different caller-side latency profiles.

## 4. Migration surface

### 4.1 In-scope (this cycle)

| File | Action | Why |
|---|---|---|
| `sdks/go/llmgw/` (extend) | MOD | +GenerateAudio + AudioGenRequest/AudioGenResult types + 2 new sentinels |
| `sdks/python/loreweave_llm/` (extend) | MOD | +generate_audio() + AudioGenResult/AudioGenDataItem + 2 new exception classes |
| `services/provider-registry-service/internal/storage/` | NEW package | MinIO wrapper for audio-cache bucket + presigned URL gen |
| `services/provider-registry-service/internal/provider/{adapters.go, openai_audio.go, adapters_audio.go}` | MOD | +GenerateAudio Adapter method + types + sentinels + batch implementation |
| `services/provider-registry-service/internal/jobs/{worker.go, worker_audio.go}` | MOD | +processAudioGenJob + audio_gen dispatch + AudioGenJobTimeout |
| `services/provider-registry-service/internal/api/{jobs_handler.go, jobs_router_test.go}` | MOD | +validateAudioGenInput + handler tests |
| `services/provider-registry-service/internal/migrate/migrate.go` | MOD | audio_gen in CHECK constraint + ALTER block (Phase 4a-β pattern) |
| `services/provider-registry-service/internal/config/config.go` | MOD | +MINIO_* + AUDIO_CACHE_BUCKET + AUDIO_CACHE_TTL_HOURS |
| `services/provider-registry-service/cmd/provider-registry-service/main.go` | MOD | Bootstrap MinIO client + create bucket + set lifecycle policy |
| `services/notification-service/internal/consumer/{consumer.go, consumer_test.go}` | MOD | opLabel "Audio gen" |
| `contracts/api/llm-gateway/v1/openapi.yaml` | MOD | +AudioGenInput + AudioGenResult + AudioGenDataItem + audio_gen JobOperation enum |
| `services/book-service/internal/api/audio.go` | MOD | Migrate generateAudio to use Go SDK |
| `services/book-service/internal/api/server.go` | MOD | Add audioGenerator consumer interface |
| `services/book-service/internal/api/media_test.go` | MOD | Update audio.go anti-bait (no longer retains legacy URL after migration) |
| `services/book-service/internal/config/config.go` | MOD | Drop ProviderRegistryURL field |
| `services/book-service/internal/config/config_test.go` | MOD | Drop PROVIDER_REGISTRY_SERVICE_URL setup |
| `services/book-service/internal/api/audio_test.go` | NEW | Helper-level tests for audio.go's error routing + grep-locks |
| `infra/docker-compose.yml` | MOD | Add MINIO_* envs to provider-registry-service + drop PROVIDER_REGISTRY_SERVICE_URL from book-service |
| `docs/03_planning/LLM_PIPELINE_PHASE5E_BETA2_DESIGN.md` | NEW (this doc) | |
| `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` | MOD | 5e-β.2 row ✅ + 5f preview |
| Session docs | MOD | SESSION_PATCH + SESSION_HANDOFF |
| Adapter / worker / SDK test files | MOD/NEW | Per-component tests |

**Total estimate: ~40 files (15 NEW + 25 MOD).**

### 4.2 Explicitly out-of-scope

- **Streaming `tts` operation changes** — chat-service voice keeps using `Client.stream_tts()` (Phase 5a/5b). The new `audio_gen` is parallel, not replacement.
- **Parallel processing in adapter** — sequential per-input upstream calls in v1. Tracked as `D-PHASE5E-BETA2-AUDIO-GEN-PARALLEL-ADAPTER`. For book chapters with 20+ blocks, parallel = real win, but design first.
- **Partial-success result envelope** — if one input in a batch fails, the whole job fails. Tracked as `D-PHASE5E-BETA2-AUDIO-GEN-PARTIAL-SUCCESS`. Pattern parallel to image_gen which is all-or-nothing today.
- **Gateway-proxy URL** (vs MinIO direct) — v1 returns presigned MinIO URLs; assumes caller has MinIO network access. Tracked as `D-PHASE5E-BETA2-AUDIO-CACHE-GATEWAY-PROXY` if non-MinIO-accessible callers emerge.
- **Audio cache observability** — no metrics on bucket size, hit rate, TTL expiry. Tracked.
- **TTS content-policy detection** — OpenAI's TTS rarely emits content-policy violations (unlike image gen). Track as `D-PHASE5E-BETA2-TTS-CONTENT-POLICY` if it surfaces.

## 5. Gateway: `audio_gen` operation

### 5.1 Wire shape (openapi)

```yaml
JobOperation:
  enum: [chat, completion, embedding, stt, tts, image_gen, video_gen, audio_gen, ...]

AudioGenInput:
  type: object
  required: [texts]
  properties:
    texts:
      type: array
      items:
        type: string
        minLength: 1
        maxLength: 4000  # OpenAI TTS per-input limit
      minItems: 1
      maxItems: 20     # MaxAudioGenInputs cap
    voice:
      type: string
      default: alloy
      description: One of: alloy, echo, fable, onyx, nova, shimmer (OpenAI). Backend-specific.
    speed:
      type: number
      minimum: 0.25
      maximum: 4.0
      default: 1.0
    format:
      type: string
      enum: [mp3, opus, aac, flac, wav, pcm]
      default: mp3
    response_format:
      type: string
      enum: [b64_json, url]
      default: b64_json
      description: |
        b64_json: audio bytes inline in result.data[i].b64_json.
        url: gateway stages to MinIO, returns presigned URL (1h TTL).

AudioGenDataItem:
  type: object
  properties:
    url:
      type: string
      description: Presigned MinIO URL. Populated when response_format=url. 1h TTL — fetch immediately.
    b64_json:
      type: string
      description: Base64-encoded audio bytes. Populated when response_format=b64_json.
    duration_ms:
      type: integer
      nullable: true
      description: Audio duration in milliseconds. Upstream-dependent; often null for OpenAI TTS.
    content_type:
      type: string
      description: MIME type, e.g. "audio/mpeg", "audio/opus".

AudioGenResult:
  type: object
  required: [created, data]
  properties:
    created:
      type: integer
    data:
      type: array
      items:
        $ref: '#/components/schemas/AudioGenDataItem'
      minItems: 1
      maxItems: 20
```

### 5.2 Adapter interface

```go
// adapters.go
type Adapter interface {
    // ... existing methods
    GenerateAudio(ctx context.Context, endpointBaseURL, secret string, modelName string, input GenerateAudioInput) (*GenerateAudioOutput, error)
}

type GenerateAudioInput struct {
    Texts          []string
    Voice          string // default "alloy" if empty
    Speed          float64 // default 1.0 if zero
    Format         string // default "mp3" if empty
    ResponseFormat string // "b64_json" | "url"
}

type GenerateAudioOutput struct {
    Items []GeneratedAudio
}

type GeneratedAudio struct {
    Data        []byte
    Format      string
    ContentType string  // e.g. "audio/mpeg"
    DurationMs  int     // 0 when upstream doesn't return
}

// New sentinels
var (
    ErrAudioGenerationFailed = errors.New("audio_gen failed")
    ErrAudioGenInvalidParams = errors.New("audio_gen invalid params")
)

// New consts
const (
    // /review-impl(DESIGN) MED#1 — cap at 10 (was 20) to bound double-bill
    // exposure when mid-batch failure forces retry. TTS is char-billed per
    // request; a batch that fails on input 9 of 10 still charges 8 prior
    // successful upstream calls. Caps risk at 10× per retry vs 20×.
    MaxAudioGenInputs        = 10
    MaxAudioGenInputCharsLen = 4096  // matches OpenAI TTS exactly (was 4000 safety margin) per LOW#8
    AudioGenJobTimeout       = 5 * time.Minute  // 10 inputs × ~15s upstream + slack = 5min upper bound
)
```

### 5.3 OpenAI adapter implementation (sequential v1; order-preserving)

```go
// openai_audio.go
//
// /review-impl(DESIGN) MED#5 — Adapter contract REQUIRES preserving
// input order: output.Items[i] corresponds 1:1 to input.Texts[i]. v1
// sequential loop satisfies trivially. Future parallel impl (deferred
// D-PHASE5E-BETA2-AUDIO-GEN-PARALLEL-ADAPTER) MUST use INDEXED writes
// (items[i] = ...), NOT append from goroutines, or audio for block 5
// could end up in result.Data[2] silently corrupting caller's mapping.
func (a *openaiAdapter) GenerateAudio(ctx context.Context, endpointBaseURL, secret, modelName string, input GenerateAudioInput) (*GenerateAudioOutput, error) {
    if len(input.Texts) == 0 {
        return nil, ErrAudioGenInvalidParams
    }
    if len(input.Texts) > MaxAudioGenInputs {
        return nil, ErrAudioGenInvalidParams
    }
    for _, t := range input.Texts {
        if strings.TrimSpace(t) == "" || len(t) > MaxAudioGenInputCharsLen {
            return nil, ErrAudioGenInvalidParams
        }
    }

    // Pre-allocated, indexed writes — preserve order invariant under
    // future parallel refactor.
    items := make([]GeneratedAudio, len(input.Texts))
    for i, text := range input.Texts {
        audio, err := a.speakOne(ctx, endpointBaseURL, secret, modelName, text, input.Voice, input.Speed, input.Format)
        if err != nil {
            return nil, err  // all-or-nothing v1
        }
        // /review-impl(DESIGN) MED#11 — defensive empty-bytes check at adapter return.
        if len(audio.Data) == 0 {
            return nil, ErrAudioGenerationFailed
        }
        items[i] = audio
    }
    return &GenerateAudioOutput{Items: items}, nil
}

// speakOne — single-text POST to /v1/audio/speech, reads whole body.
// /review-impl(DESIGN) LOW#1 — defaults applied at adapter (mirrors Speak):
//   - Voice "" → "alloy"
//   - Speed 0 → 1.0
//   - Format "" → "mp3"
// Use ClassifyUpstreamHTTP for typed errors. Same Auth/Content-Type as Speak.
func (a *openaiAdapter) speakOne(ctx context.Context, base, secret, model, text, voice string, speed float64, format string) (GeneratedAudio, error) {
    if voice == "" { voice = "alloy" }
    if speed <= 0 { speed = 1.0 }
    if format == "" { format = "mp3" }
    // POST {model, input, voice, speed, response_format} to base+/v1/audio/speech
    // io.ReadAll(io.LimitReader(resp.Body, MaxAudioBytes)) — same cap as Speak streaming.
    // Return GeneratedAudio{Data, Format, ContentType, DurationMs:0}.
}
```

### 5.4 Worker plumbing path (/review-impl(DESIGN) HIGH#2)

The new `audio_gen` worker needs access to `*storage.AudioCache`. Current `Worker` struct has no MinIO field. Wiring:

1. **`internal/jobs/worker.go`** — add field:
   ```go
   type Worker struct {
       repo       *Repo
       resolve    CredResolver
       adapter    AdapterFactory
       notifier   Notifier
       logger     *slog.Logger
       audioCache *storage.AudioCache  // NEW (may be nil if MinIO config missing)
   }
   func NewWorker(repo *Repo, resolve CredResolver, adapter AdapterFactory, notifier Notifier, logger *slog.Logger, audioCache *storage.AudioCache) *Worker { ... }
   ```
2. **`internal/api/server.go::NewServer`** — accept `audioCache *storage.AudioCache` parameter; pass to `jobs.NewWorker`.
3. **`cmd/provider-registry-service/main.go`** — bootstrap `storage.NewAudioCache(ctx, cfg)` (nil if MinIO unconfigured; gateway boots without URL-mode support but b64_json still works); pass into `api.NewServer`.
4. **All existing tests calling `jobs.NewWorker`** — add `nil` as the 6th arg (audioCache absent in unit tests).
5. **Worker handles nil audioCache gracefully**: in `processAudioGenJob`, if `w.audioCache == nil` and `response_format=url`, fail the job with `LLM_INVALID_REQUEST` (clear message: "url mode requires audio-cache configured at gateway").

### 5.4.1 Worker dispatch + URL/b64 result building

```go
// worker_audio.go
const AudioGenJobTimeout = 5 * time.Minute

func (w *Worker) processAudioGenJob(ctx context.Context, jobID uuid.UUID, modelRef uuid.UUID, modelSource string, userID uuid.UUID, input map[string]any) {
    // Extract input from map
    // Get adapter via w.invokeClient
    // Call adapter.GenerateAudio
    // Build result based on input.response_format:
    //   - "b64_json": items[i].Data → base64.StdEncoding.EncodeToString → AudioGenDataItem.B64JSON
    //   - "url": call w.audioCache.Stage(ctx, jobID, idx, items[i].Data, items[i].ContentType) → AudioGenDataItem.URL
    // Update job to completed with result
}

// /review-impl(DESIGN) MED#4 — full parity with classifyImageError. Don't
// drop AUTH/OPERATION_NOT_SUPPORTED/RATE_LIMITED branches — book-service's
// writeAudioGenError (mirroring writeImageGenError from 5e-β.1) needs the
// typed codes for HTTP status routing.
func classifyAudioGenError(ctx context.Context, err error) (code string, status string) {
    if errors.Is(err, ErrAudioGenInvalidParams) {
        return "LLM_INVALID_REQUEST", "failed"
    }
    if errors.Is(err, ErrOperationNotSupported) {
        return "LLM_OPERATION_NOT_SUPPORTED", "failed"
    }
    // Typed upstream errors via errors.As — mirrors classifyImageError.
    var rateErr *ErrUpstreamRateLimited
    if errors.As(err, &rateErr) {
        return "LLM_RATE_LIMITED", "failed"
    }
    var permErr *ErrUpstreamPermanent
    if errors.As(err, &permErr) {
        // 401/403 → LLM_AUTH_FAILED (book-service maps to 402 NO_PROVIDER)
        if permErr.StatusCode == 401 || permErr.StatusCode == 403 {
            return "LLM_AUTH_FAILED", "failed"
        }
        return "LLM_UPSTREAM_ERROR", "failed"
    }
    var transErr *ErrUpstreamTransient
    if errors.As(err, &transErr) {
        return "LLM_UPSTREAM_ERROR", "failed"
    }
    if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
        return "LLM_TIMEOUT", "failed"
    }
    if errors.Is(ctx.Err(), context.Canceled) || errors.Is(err, context.Canceled) {
        return "LLM_CANCELLED", "cancelled"
    }
    if errors.Is(err, ErrAudioGenerationFailed) {
        return "LLM_AUDIO_GENERATION_FAILED", "failed"
    }
    return "LLM_UPSTREAM_ERROR", "failed"
}
```

### 5.5 MinIO audio-staging (NEW)

> **Major design correction (/review-impl(DESIGN) HIGH#1):** Original design used presigned URLs with host rewrite via `MINIO_EXTERNAL_URL` — this **breaks SigV4 signatures** (signature is computed against host header at sign time; rewriting host invalidates it). Fixed by using a **public-read bucket** with UUID-keyed objects (same security tradeoff book-service already accepts for `loreweave-media` chapter media), then constructing static URLs against `MINIO_EXTERNAL_URL`. Mirrors book-service's `setBucketPublicRead` + `mediaURL` pattern — known-working in this codebase.

```go
// internal/storage/audio_cache.go
package storage

import (
    "bytes"
    "context"
    "fmt"
    "log/slog"
    "strings"

    "github.com/google/uuid"
    "github.com/minio/minio-go/v7"
    "github.com/minio/minio-go/v7/pkg/credentials"
    "github.com/minio/minio-go/v7/pkg/lifecycle"
)

// AudioCache is the gateway-side MinIO staging for audio_gen URL mode.
// Bucket is PUBLIC-READ — same security model as book-service's
// loreweave-media. Object keys are job-id-scoped UUIDs (unguessable).
type AudioCache struct {
    client      *minio.Client
    bucket      string
    externalURL string // public URL prefix, e.g. http://localhost:9123
}

type Config struct {
    Endpoint    string // minio:9000 (in-cluster)
    AccessKey   string
    SecretKey   string
    UseSSL      bool
    Bucket      string // loreweave-audio-cache
    ExternalURL string // http://localhost:9123 (dev) or https://media.loreweave.com (prod)
}

func NewAudioCache(ctx context.Context, cfg Config, logger *slog.Logger) (*AudioCache, error) {
    if cfg.ExternalURL == "" {
        return nil, fmt.Errorf("audio cache requires MINIO_EXTERNAL_URL")
    }
    mc, err := minio.New(cfg.Endpoint, &minio.Options{
        Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
        Secure: cfg.UseSSL,
    })
    if err != nil {
        return nil, fmt.Errorf("minio new: %w", err)
    }

    // Create bucket if missing.
    exists, err := mc.BucketExists(ctx, cfg.Bucket)
    if err != nil {
        return nil, fmt.Errorf("bucket exists check: %w", err)
    }
    if !exists {
        if err := mc.MakeBucket(ctx, cfg.Bucket, minio.MakeBucketOptions{}); err != nil {
            // Race: another instance may have created it.
            if exists2, _ := mc.BucketExists(ctx, cfg.Bucket); !exists2 {
                return nil, fmt.Errorf("make bucket: %w", err)
            }
        }
    }

    // Set public-read bucket policy (anonymous GET — mirrors book-service's
    // setBucketPublicRead at media.go:587).
    publicPolicy := `{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": ["arn:aws:s3:::` + cfg.Bucket + `/*"]
        }]
    }`
    if err := mc.SetBucketPolicy(ctx, cfg.Bucket, publicPolicy); err != nil {
        // /review-impl(DESIGN) MED#2 — log loudly; don't swallow silently.
        // Boot continues since URL-mode still works (just without policy
        // enforcement; operator can fix post-deploy).
        logger.Warn("audio_cache: SetBucketPolicy failed — URL-mode public access may not work", "err", err)
    }

    // /review-impl(DESIGN) MED#3 — rename local var to avoid shadowing
    // package `lifecycle`. Was `lifecycle := lifecycle.NewConfiguration()`.
    lcCfg := lifecycle.NewConfiguration()
    lcCfg.Rules = []lifecycle.Rule{
        {
            ID:         "expire-staged-audio",
            Status:     "Enabled",
            Expiration: lifecycle.Expiration{Days: 1}, // MinIO minimum
        },
    }
    if err := mc.SetBucketLifecycle(ctx, cfg.Bucket, lcCfg); err != nil {
        // /review-impl(DESIGN) MED#2 — log + continue. Lifecycle failure
        // is non-fatal (bucket grows; operator can fix later).
        logger.Warn("audio_cache: SetBucketLifecycle failed — bucket may grow unbounded", "err", err)
    }

    return &AudioCache{
        client:      mc,
        bucket:      cfg.Bucket,
        externalURL: strings.TrimRight(cfg.ExternalURL, "/"),
    }, nil
}

// Stage uploads audio bytes + returns a public URL.
//
// /review-impl(DESIGN) LOW#5 — prefer `format` (caller-specified) for ext;
// `contentType` may be empty if upstream omitted the Content-Type header.
func (a *AudioCache) Stage(ctx context.Context, jobID uuid.UUID, idx int, format string, data []byte, contentType string) (string, error) {
    if len(data) == 0 {
        return "", fmt.Errorf("audio_cache: refusing to stage 0-byte object")
    }
    ext := "." + format // "mp3", "opus", "aac", etc.
    objectKey := fmt.Sprintf("jobs/%s/%d%s", jobID, idx, ext)
    _, err := a.client.PutObject(ctx, a.bucket, objectKey,
        bytes.NewReader(data), int64(len(data)),
        minio.PutObjectOptions{ContentType: contentType})
    if err != nil {
        return "", fmt.Errorf("audio_cache put: %w", err)
    }
    // Static public URL — same pattern as book-service mediaURL().
    return fmt.Sprintf("%s/%s/%s", a.externalURL, a.bucket, objectKey), nil
}
```

**Notes:**
- **Bucket is public-read** (mirrors `loreweave-media`). Object keys contain UUIDs — unguessable; security model is "URL is the bearer token" (same as Apple's iCloud share links).
- **1-day MinIO lifecycle** — minimum supported by MinIO. Staged objects auto-expire. No Go cleanup loop. Tracked as `D-PHASE5E-BETA2-AUDIO-CACHE-FAST-TTL` if minute-level TTL ever needed.
- **No presigned URLs** — eliminates SigV4 host-rewrite trap. URLs are static; caller uses `MINIO_EXTERNAL_URL` host (same one book-service uses for its media URLs).

### 5.6 Handler validation

```go
// jobs_handler.go
//
// /review-impl(DESIGN) COSMETIC#3 — match existing validateImageGenInput
// signature: chunking is a TOP-LEVEL field on SubmitJobRequest (json.RawMessage),
// NOT inside input map. The handler dispatches to operation-specific
// validators by passing both `input` and `chunking` raw.
func validateAudioGenInput(input map[string]any, chunking json.RawMessage) error {
    texts, ok := input["texts"].([]any)
    if !ok || len(texts) == 0 {
        return fmt.Errorf("texts is required and must be non-empty array")
    }
    if len(texts) > MaxAudioGenInputs {
        return fmt.Errorf("texts exceeds max %d", MaxAudioGenInputs)
    }
    for i, t := range texts {
        s, ok := t.(string)
        if !ok {
            return fmt.Errorf("texts[%d] must be string", i)
        }
        if strings.TrimSpace(s) == "" {
            return fmt.Errorf("texts[%d] must not be empty/whitespace", i)
        }
        if len(s) > MaxAudioGenInputCharsLen {
            return fmt.Errorf("texts[%d] exceeds %d chars (OpenAI TTS limit)", i, MaxAudioGenInputCharsLen)
        }
    }
    if rf, ok := input["response_format"].(string); ok {
        if rf != "b64_json" && rf != "url" {
            return fmt.Errorf("response_format must be 'b64_json' or 'url'")
        }
    }
    // /review-impl(DESIGN) MED#6 — format enum is OpenAI-canonical; adapter
    // passes through for backend-specific extensions. Reject only obvious
    // junk; backend rejects unsupported formats with clear errors.
    if format, ok := input["format"].(string); ok && format != "" {
        valid := map[string]bool{"mp3": true, "opus": true, "aac": true, "flac": true, "wav": true, "pcm": true}
        if !valid[format] {
            return fmt.Errorf("format must be one of mp3,opus,aac,flac,wav,pcm")
        }
    }
    // Chunking not supported (matches validateImageGenInput pattern).
    if len(chunking) > 0 && string(chunking) != "null" {
        return fmt.Errorf("chunking config not supported for audio_gen")
    }
    return nil
}
```

### 5.7 DB migration (/review-impl(DESIGN) HIGH#3 + MED#9)

The existing constraint name is **`llm_jobs_operation_check`** (NO version suffix). Earlier cycles (4a-β, 5d) DROP + re-CREATE the constraint with the same name. Use the same pattern:

```go
// migrate.go — new Phase 5e-β.2 ALTER block (after Phase 5d block at line 165)
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
    'chat','completion','embedding','stt','tts','image_gen','video_gen','audio_gen',
    'entity_extraction','relation_extraction','event_extraction','fact_extraction','translation'
));
```

**Also (HIGH#3 + MED#9): update CREATE TABLE inline CHECK** at lines 97–103 to include `audio_gen` so cold-start DBs accept the operation. Without this, fresh DBs are broken until the ALTER block runs (and the ALTER block only happens on first boot AFTER schema creation — cold-start during initial boot would reject `audio_gen` inserts until the loop completes).

Mirrors Phase 5d's pattern exactly.

## 6. Python SDK extension

```python
# client.py
#
# /review-impl(DESIGN) HIGH#5 — Optional fields use `None` sentinel; wire
# inclusion via `if X is not None` (NOT `if X != default`). Per memory
# `feedback_sdk_default_arg_dropped_from_wire` — explicit-equal-to-default
# values must reach the wire so caller intent is preserved across SDK→
# gateway. Phase 5c-α image_gen had MED#1 because `if n != 1` silently
# dropped explicit n=1; don't repeat.
async def generate_audio(
    self,
    texts: list[str],
    *,
    model_source: ModelSource,
    model_ref: str,
    voice: str | None = None,
    speed: float | None = None,
    format: AudioFormat | None = None,
    response_format: Literal["b64_json", "url"] | None = None,
    user_id: str | None = None,
    poll_interval_s: float = 0.5,
    max_poll_interval_s: float = 10.0,
) -> AudioGenResult:
    """Submit batch audio_gen job, wait for terminal, return result.

    Phase 5e-β.2 — operation-based TTS. Distinct from `stream_tts()` (Phase 5a)
    which is streaming/realtime; this is batch/job-mode for stored audio
    (book chapter narration). Both use the same upstream (/v1/audio/speech)
    but different gateway operations.

    Polling defaults: 0.5s initial, 10s max, 1.5× backoff. transient_retry
    budget fixed at 0. /review-impl(DESIGN) MED#10 — TTS is char-billed;
    mid-batch retries could double-charge up to N × 4096 chars per call.
    Lock at 0 to bound exposure (amplified vs generate_image's single-input
    risk).

    Args:
        texts: 1..10 strings, each 1..4096 chars (OpenAI TTS limit;
            /review-impl(DESIGN) MED#1 — batch capped at 10 to bound
            double-bill exposure on mid-batch failure).
        model_source: 'user_model' or 'platform_model'.
        model_ref: UUID-shaped model reference.
        voice: None ⇒ gateway/upstream default 'alloy'. Backend-specific.
        speed: None ⇒ gateway/upstream default 1.0. Range 0.25..4.0.
        format: None ⇒ gateway/upstream default 'mp3'.
        response_format: None ⇒ gateway/upstream default 'b64_json'.
            'b64_json' inline; 'url' returns public MinIO URL (1d TTL).
        user_id: per-call override.

    Raises:
        LLMInvalidRequest: validation failures (empty texts, oversize, etc.)
        LLMAudioGenerationFailed: upstream TTS failed.
        LLMQuotaExceeded / LLMRateLimited / etc.

    Returns:
        AudioGenResult with `len(texts)` data entries.
    """
    # ... mirrors generate_image structure
```

```python
# errors.py
class LLMAudioGenerationFailed(LLMError):
    code = "LLM_AUDIO_GENERATION_FAILED"

# models.py
class AudioGenDataItem(BaseModel):
    url: str | None = None
    b64_json: str | None = None
    duration_ms: int | None = None
    content_type: str

class AudioGenResult(BaseModel):
    created: int
    data: list[AudioGenDataItem]
```

## 7. Go SDK extension

```go
// sdks/go/llmgw/models.go (add)
//
// /review-impl(DESIGN) HIGH#5 — Optional fields use *string/*float64
// pointer pattern (matches Python's `T | None`). Wire-inclusion via
// `if req.X != nil` preserves explicit-equal-to-default semantics
// (Phase 5e-β.1 design MED#1 — mirrors generate_image).
type GenerateAudioRequest struct {
    // Required.
    Texts       []string
    ModelSource ModelSource
    ModelRef    string

    // Optional — nil pointer ⇒ omit from wire payload.
    Voice          *string  // nil ⇒ upstream default ("alloy")
    Speed          *float64 // nil ⇒ upstream default (1.0)
    Format         *string  // nil ⇒ upstream default ("mp3")
    ResponseFormat *string  // nil ⇒ gateway default ("b64_json")

    // Per-call overrides.
    UserID          string
    PollInterval    time.Duration
    MaxPollInterval time.Duration
}

type AudioGenDataItem struct {
    URL         string `json:"url,omitempty"`
    B64JSON     string `json:"b64_json,omitempty"`
    DurationMs  int    `json:"duration_ms,omitempty"`
    ContentType string `json:"content_type"`
}

type AudioGenResult struct {
    Created int64              `json:"created"`
    Data    []AudioGenDataItem `json:"data"`
}

// sdks/go/llmgw/errors.go (add)
var (
    ErrAudioGenerationFailed = errors.New("LLM_AUDIO_GENERATION_FAILED")
)
// + codeSentinels entry

// sdks/go/llmgw/client.go (add method)
func (c *Client) GenerateAudio(ctx context.Context, req GenerateAudioRequest) (*AudioGenResult, error) {
    // Pre-flight validations (SDK boundary):
    //   - ModelRef UUID-shaped
    //   - len(Texts) > 0 (catches nil AND empty slice per LOW#4)
    //   - len(Texts) <= MaxAudioGenInputs (10 per MED#1)
    //   - each text non-empty after TrimSpace AND <= 4096 chars (LOW#8)
    // Wire body via map[string]any:
    //   input["texts"] = req.Texts (always)
    //   if req.Voice != nil { input["voice"] = *req.Voice }
    //   if req.Speed != nil { input["speed"] = *req.Speed }
    //   if req.Format != nil { input["format"] = *req.Format }
    //   if req.ResponseFormat != nil { input["response_format"] = *req.ResponseFormat }
    // Submit → wait → decode AudioGenResult.
    // On JobFailed: surface typed error via newErrorFromCodeWithRetry.
}
```

## 7.1 book-service consumer-defined interfaces (/review-impl(DESIGN) HIGH#4)

`server.go` already has `imageGenerator interface { GenerateImage(...) }` + `s.llmgw imageGenerator` from Phase 5e-β.1. **Decision:** add a SECOND, SEPARATE interface `audioGenerator` + a SECOND field `s.audioGenClient audioGenerator`. Both fields wire to the SAME concrete `*llmgw.Client` in NewServer (Go satisfies interfaces implicitly). Reasons:

- **Don't rename `s.llmgw`** — Phase 5e-β.1's grep-lock `s.llmgw.GenerateImage(` in `media_test.go::TestNoLegacyLLMResolutionInMediaGo` line 332 must keep passing without modification.
- **Two narrow interfaces** > one widened interface — tests mock the narrow surface they need (image_gen mocks don't need to stub audio_gen).
- Both interfaces in `server.go`; both fields assigned in NewServer to `lc` (same concrete client).

```go
// services/book-service/internal/api/server.go
type imageGenerator interface {
    GenerateImage(ctx context.Context, req llmgw.GenerateImageRequest) (*llmgw.ImageGenResult, error)
}

type audioGenerator interface {
    GenerateAudio(ctx context.Context, req llmgw.GenerateAudioRequest) (*llmgw.AudioGenResult, error)
}

type Server struct {
    // ... existing fields
    llmgw          imageGenerator  // existing; keep field name
    audioGenClient audioGenerator  // NEW
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
    // ... existing wiring
    if cfg.LLMGatewayInternalURL != "" && cfg.InternalServiceToken != "" {
        lc, err := llmgw.NewClient(...)
        if err != nil {
            slog.Error("book-service: llmgw.NewClient failed", "err", err)
        } else {
            s.llmgw = lc           // satisfies imageGenerator
            s.audioGenClient = lc  // satisfies audioGenerator (same concrete *llmgw.Client)
        }
    }
    return s
}
```

## 8. book-service `audio.go` migration

### 8.1 Before (current)

```go
func (s *Server) generateAudio(w http.ResponseWriter, r *http.Request) {
    // ... ownership/lifecycle checks ...
    // 1. Resolve credentials via /internal/credentials/ (~30 LOC)
    // 2. Loop over body.Blocks:
    //    POST /v1/audio/speech per block
    //    Upload mp3 to MinIO
    //    Insert chapter_audio_segments
    //    Aggregate segments + errors
    // 3. Bill by totalChars
}
```

### 8.2 After

```go
func (s *Server) generateAudio(w http.ResponseWriter, r *http.Request) {
    if s.minio == nil { /* 503 */ }
    if s.audioGenClient == nil { /* 503 — same nil-check pattern as s.llmgw */ }

    // ... ownership/lifecycle/body decode unchanged ...

    // Filter non-empty blocks BEFORE sending; track original indices.
    type indexedText struct {
        idx  int
        text string
    }
    var inputs []indexedText
    for _, b := range body.Blocks {
        if strings.TrimSpace(b.Text) != "" {
            inputs = append(inputs, indexedText{idx: b.Index, text: b.Text})
        }
    }
    if len(inputs) == 0 {
        writeJSON(w, http.StatusOK, map[string]any{"segments": []segResult{}, "errors": []segError{}})
        return
    }

    texts := make([]string, len(inputs))
    for i, it := range inputs {
        texts[i] = it.text
    }

    // Single SDK call (batched across N blocks)
    ctx := r.Context()
    voice := body.Voice
    format := "mp3"               // FE always expects mp3
    responseFormat := "b64_json"  // download + upload pattern; URL mode would add a fetch
    result, err := s.audioGenClient.GenerateAudio(ctx, llmgw.GenerateAudioRequest{
        Texts:          texts,
        ModelSource:    llmgw.ModelSource(body.ModelSource),
        ModelRef:       body.ModelRef,
        Voice:          &voice,
        Format:         &format,
        ResponseFormat: &responseFormat,
        UserID:         ownerID.String(),
    })
    if err != nil {
        writeAudioGenError(w, err)  // extracted helper, parallel to writeImageGenError
        return
    }

    // Per-result: decode base64 → upload to MinIO → insert DB row.
    // Original-index preserved via inputs[i].idx.
    var segments []segResult
    for i, item := range result.Data {
        audioBytes, err := base64.StdEncoding.DecodeString(item.B64JSON)
        if err != nil {
            slog.Error("generateAudio b64 decode", "block_index", inputs[i].idx, "error", err)
            continue
        }
        objectKey := fmt.Sprintf("audio/%s/tts/%s_%s_%d_%s.mp3",
            chapterID, body.Language, body.Voice, inputs[i].idx, uuid.New().String())
        _, err = s.minio.PutObject(ctx, mediaBucket, objectKey, bytes.NewReader(audioBytes), int64(len(audioBytes)),
            minio.PutObjectOptions{ContentType: "audio/mpeg"})
        if err != nil { /* per-block error track */ }
        // Insert DB row + append to segments
    }

    // 5. Best-effort usage billing — preserved unchanged from legacy
    // generateAudio (only the source of totalChars shifts: was summed
    // mid-loop, now summed from `inputs` post-filter pre-submit).
    if s.cfg.UsageBillingServiceURL != "" && len(segments) > 0 {
        totalChars := 0
        for _, it := range inputs {
            totalChars += len(it.text)
        }
        modelRefUUID, _ := uuid.Parse(body.ModelRef)
        usagePayload, _ := json.Marshal(map[string]any{
            "request_id":     uuid.New(),
            "owner_user_id":  ownerID,
            "provider_kind":  "",  // per 5e-α QC MED#1 precedent (SDK doesn't expose)
            "model_source":   body.ModelSource,
            "model_ref":      modelRefUUID,
            "input_tokens":   totalChars,
            "output_tokens":  0,
            "request_status": "success",
            "purpose":        "tts_generation",
        })
        // POST to billingURL, best-effort (slog.Warn on failure).
    }
}
```

### 8.3 Why b64_json mode (not URL mode) for book-service

- **Uniform FE handling** — book-service's existing audio storage uses the `loreweave-media` bucket (same as user-uploaded audio). b64 path preserves that uniformity: the FE always plays from `loreweave-media` URLs regardless of TTS-vs-upload origin.
- Book-service ALREADY downloads + uploads each block; b64 doesn't ADD a fetch step vs URL (it just moves the bytes via DB instead of a second MinIO).
- For per-block audio (~50KB), inline base64 in the job result is reasonable; aggregate result per chapter is ~10×100KB = 1MB JSON in `llm_jobs.result` JSONB (well under Postgres's 1GB row limit; tracked as `D-PHASE5E-BETA2-RESULT-SIZE-METRIC`).
- URL mode remains available for future callers who want direct-presign playback (skip caller-side re-upload) — tracked as `D-PHASE5E-BETA2-AUDIO-SKIP-LOCAL-UPLOAD`.

### 8.4 LOC reduction

| Section | Before | After | Δ |
|---|---|---|---|
| 1. Credential resolve | ~30 | 0 | −30 |
| 2. Per-block TTS POST | ~25 per block × N | 1 SDK call | −25×N+10 |
| Error handling | ~10 | ~30 (typed switch) | +20 |
| Total handler | ~340 | ~210 | −130 (~38%) |

### 8.5 Drop `ProviderRegistryURL` from config

After audio.go migrates, no code in book-service references `/internal/credentials/`. The `ProviderRegistryURL` config field becomes unused. Drop:
- `config.go`: drop field + drop required-env validation
- `config_test.go`: drop `PROVIDER_REGISTRY_SERVICE_URL` setup
- `docker-compose.yml`: drop `PROVIDER_REGISTRY_SERVICE_URL` env line
- `media_test.go::TestAudioGoStillUsesLegacyPath`: **delete entirely** — audio.go is now migrated. The companion `TestNoLegacyLLMResolutionInMediaGo` STAYS (still pins media.go).
- **NEW** `audio_test.go::TestNoLegacyLLMResolutionInAudioGo`: positive grep-lock mirroring media's structure — audio.go MUST contain `llmgw.GenerateAudio`, MUST NOT contain `/internal/credentials/`, `/v1/audio/speech`, `creds.APIKey`, `creds.ProviderModelName`. /review-impl(DESIGN) MED#7 — replaces anti-bait with positive lock.

## 9. Tests

### 9.1 Gateway

| File | Tests added |
|---|---|
| `internal/provider/adapters_audio_test.go` | +8 for GenerateAudio: empty-texts rejected, oversize-text rejected, batch-cap rejected, happy path (single + multi), all-or-nothing on mid-batch failure, content-type passes through, format=mp3/opus dispatch, stub-trio (Anthropic/Ollama/LM Studio return ErrOperationNotSupported) |
| `internal/jobs/worker_audio_test.go` | +10 for audio_gen worker: dispatch routes to processAudioGenJob, classifyAudioGenError matrix (8 cases), audio_gen in audioJobOperations whitelist, audio_gen in 5-place sync |
| `internal/api/jobs_router_test.go` | +6 for handler: ValidationPasses, RejectsEmptyTexts, RejectsOversizeText, RejectsBatchOverCap, RejectsBadResponseFormat, RejectsChunkingConfig |
| `internal/storage/audio_cache_test.go` | NEW. 4 tests: Stage uploads + returns valid presigned URL, ContentType propagates, bucket auto-create on first use, lifecycle policy set on init |

### 9.2 Python SDK

| File | Tests added |
|---|---|
| `sdks/python/tests/test_audio_gen.py` | NEW. 10 tests: happy path b64_json + happy path url + empty texts rejected (LLMInvalidRequest pre-wire) + oversize text rejected + batch cap rejected + voice forwarded to wire + format forwarded + response_format forwarded + LLMAudioGenerationFailed mapping + from_code regression-lock |

### 9.3 Go SDK

| File | Tests added |
|---|---|
| `sdks/go/llmgw/client_test.go` | +8 for GenerateAudio: happy path b64_json, happy path url, empty Texts rejected pre-wire, non-UUID ModelRef rejected, voice reaches wire (non-default voice — mirrors HIGH#6 pattern), format reaches wire, response_format=url returns URLs, ErrAudioGenerationFailed mapping |
| `sdks/go/llmgw/errors_test.go` | +1: codeSentinels entry for LLM_AUDIO_GENERATION_FAILED roundtrips via newErrorFromCode |

### 9.4 book-service

| File | Tests added |
|---|---|
| `internal/api/audio_test.go` | NEW. 8 tests: writeAudioGenError typed-error routing (mirrors writeImageGenError pattern from 5e-β.1) + grep-locks (audio.go has no /internal/credentials/, no /v1/audio/speech, no creds.ProviderModelName, no creds.APIKey, has llmgw import, has audioGenClient.GenerateAudio call) |
| `internal/api/media_test.go` | MOD: drop TestAudioGoStillUsesLegacyPath anti-bait (audio migrated). Replace with positive lock that audio.go IS migrated. |

## 10. Risks + mitigations

| Risk | Mitigation |
|---|---|
| **R1: MinIO infra is NEW to provider-registry-service.** | Mirror book-service's MinIO bootstrap (already works in this codebase); use existing minio-go v7 library. |
| **R2: Server-side bucket lifecycle minimum is 1 day; presigned URL TTL is 1 hour. 23h dead-storage window.** | Document. Tracked as D-PHASE5E-BETA2-AUDIO-CACHE-FAST-TTL. Acceptable for v1. |
| **R3: Sequential adapter batch is slow for 20+ blocks.** | Sequential v1; parallel tracked as D-PHASE5E-BETA2-AUDIO-GEN-PARALLEL-ADAPTER. |
| **R4: All-or-nothing batch failure model — one bad input kills the whole job.** | Documented in design + tracked as D-PHASE5E-BETA2-AUDIO-GEN-PARTIAL-SUCCESS. Book-service caller filters whitespace-only texts BEFORE submit; primary failure mode is upstream throttling which affects all texts anyway. |
| **R5: Audio result size — b64_json mode with 20 inputs × ~100KB each = 2MB result JSON in DB `llm_jobs.result`.** | Existing job-result size; openapi already allows 8MB image_gen result. Bills well. Tracked as D-PHASE5E-BETA2-RESULT-SIZE-METRIC. |
| **R6: Presigned URL host may not be reachable from caller in prod (different docker network).** | `MINIO_EXTERNAL_URL` config rewrites the host. Caller assumed in same MinIO-accessible network. Tracked. |
| **R7: Migration concurrency — old audio.go path still works mid-deploy.** | Both legacy and new code paths use the same MinIO bucket + DB rows. Rolling deploy safe: old workers finish their TTS calls + new workers use SDK. No schema migration breaks. |
| **R8: book-service's audio.go retains the per-block loop wrapping a batch SDK call.** | Filter empty blocks BEFORE submit to avoid wasted upstream calls. Map result.data[i] back to original block index via the `indexedText` struct. |
| **R9: response_format=url mode adds gateway-side MinIO complexity for ONE caller that uses b64.** | URL mode is built but unused by book-service this cycle. Sets pattern for future callers; tested but not actually exercised by production today. Accept. |
| **R10: SDK validation must catch empty Texts BEFORE the wire; otherwise gateway 400 has poor caller diagnostics.** | SDK validates Texts length, per-text char limit, MaxAudioGenInputs cap. Mirrors generate_image's UUID/prompt validation. |
| **R11: New required envs (MINIO_*) on provider-registry-service might break existing deployments.** | Config validation requires them. docker-compose.yml has dev defaults; prod deploys must set. Document. |
| **R12: TTS doesn't have content-policy violation paths today.** | If OpenAI ever returns a content-policy error for TTS, classifyAudioGenError currently returns LLM_AUDIO_GENERATION_FAILED. Acceptable — add LLMAudioContentPolicy later if needed. |

## 11. Acceptance criteria

1. `cd services/provider-registry-service && go build ./... && go vet ./... && go test ./...` — ALL GREEN
2. `cd sdks/python && python -m pytest tests/` — all pass + 10 new audio_gen tests
3. `cd services/chat-service && python -m pytest tests/` — 180/180 unchanged (regression baseline)
4. `cd sdks/go/llmgw && go test ./...` — all pass (was 44; +9 new for GenerateAudio + 1 codeSentinel lock)
5. `cd services/book-service && go build ./... && go vet ./... && go test ./...` — ALL GREEN; new audio_test.go passes
6. `grep -n "/internal/credentials/" services/book-service/internal/api/audio.go` — no matches
7. `grep -n "/v1/audio/speech" services/book-service/internal/api/audio.go` — no matches
8. `grep -n "s.cfg.ProviderRegistryURL" services/book-service/` — no matches
9. POST `/v1/books/:id/chapters/:id/audio` returns same response shape (`segments[].block_index/media_url/media_key/duration_ms` + `errors[]`) — backwards-compatible with FE
10. `docker compose -f infra/docker-compose.yml build provider-registry-service && docker compose -f infra/docker-compose.yml build book-service` succeeds
11. After `docker compose up`: `loreweave-audio-cache` bucket auto-created in MinIO with public-read policy; `book-service` does NOT have PROVIDER_REGISTRY_SERVICE_URL env
12. /review-impl(DESIGN) LOW#13 — provider-registry-service `go.mod` pins `github.com/minio/minio-go/v7 v7.0.100` (matches book-service version exactly)

## 12. Deferred items added by this cycle

| ID | Description | Target |
|---|---|---|
| `D-PHASE5E-BETA2-AUDIO-GEN-PARALLEL-ADAPTER` | Replace sequential per-input upstream calls with bounded-parallel goroutines | Track 2 / perf cycle |
| `D-PHASE5E-BETA2-AUDIO-GEN-PARTIAL-SUCCESS` | Allow some inputs to succeed when others fail (per-index errors array in result) | Track 2 |
| `D-PHASE5E-BETA2-AUDIO-CACHE-GATEWAY-PROXY` | Optional gateway-proxy URL alternative to direct MinIO presigned (for callers without MinIO network access) | Track 2 if non-MinIO callers emerge |
| `D-PHASE5E-BETA2-AUDIO-CACHE-FAST-TTL` | Replace MinIO lifecycle (1-day min) with Go cleanup goroutine if storage growth is pain | Track 2 if observed |
| `D-PHASE5E-BETA2-RESULT-SIZE-METRIC` | DB growth from large b64_json results | Track 2 |
| `D-PHASE5E-BETA2-TTS-CONTENT-POLICY` | Add LLMAudioContentPolicy class if OpenAI ever returns content-policy for TTS | Track 2 |
| `D-PHASE5E-BETA2-LIVE-SMOKE` | Manual post-merge against OpenAI BYOK + actual book chapter audio generation | After merge |

## 13. Open questions — resolved by /review-impl(DESIGN)

1. **OpenAI TTS char limit** — locked at 4096 (matches OpenAI exactly; was 4000 safety margin per LOW#8). MaxAudioGenInputCharsLen=4096.
2. **Format support varies by upstream** — handler enforces canonical OpenAI enum; adapter passes through; upstream errors if unsupported (MED#6).
3. **Speed range 0.25..4.0** — matches OpenAI; SDK validates pre-wire.
4. **Voice passthrough** — SDK doesn't enum-validate; backend-specific.
5. **Job-result size** — 10 inputs × ~100KB = 1MB result JSON in DB. Safe. `D-PHASE5E-BETA2-RESULT-SIZE-METRIC` tracks.
6. **URL mode signing** — RESOLVED: no presigned URLs; public-read bucket + static URLs (HIGH#1 fix).
7. **Concurrency** — sequential book chapters per caller; no race.
8. **Cancellation propagation** — end-to-end via ctx (book-service ↔ SDK ↔ gateway worker).
9. **DB CHECK constraint** — uses existing `llm_jobs_operation_check` (no version suffix) per HIGH#3.
10. **Worker plumbing** — explicit signature changes documented in §5.4 per HIGH#2.

## 14. Resolved decisions (closed in this DESIGN cycle)

| ID | Decision | Closure |
|---|---|---|
| /review-impl HIGH#1 | URL mode signature mechanic | Public-read bucket + static URLs (mirrors book-service `loreweave-media` pattern); NO presigned URLs. |
| /review-impl HIGH#2 | Worker plumbing for audioCache | Explicit Worker field + NewWorker arg + main.go bootstrap + api.NewServer signature, documented §5.4. |
| /review-impl HIGH#3 | DB constraint versioning | Use existing constraint name `llm_jobs_operation_check` (no suffix); update CREATE TABLE inline + add Phase 5e-β.2 ALTER block. |
| /review-impl HIGH#4 | book-service interface design | Two narrow interfaces (`imageGenerator` + `audioGenerator`), two fields (`s.llmgw` kept; `s.audioGenClient` new), both point to same `*llmgw.Client`. |
| /review-impl HIGH#5 | SDK wire-encoding for optionals | Pointer pattern (`*string`/`*float64`); wire-include via `if X != nil`; preserves explicit-equal-to-default per `feedback_sdk_default_arg_dropped_from_wire`. |
| /review-impl MED#1 | Batch size cap | MaxAudioGenInputs=10 (was 20) to bound double-bill exposure. |
| /review-impl MED#2 | Lifecycle error swallow | Log warning + continue boot. |
| /review-impl MED#3 | Variable shadowing | Rename `lifecycle` local var → `lcCfg`. |
| /review-impl MED#4 | classifyAudioGenError parity | Full typed-error matrix (rate/perm/transient/auth/ctx) mirroring classifyImageError. |
| /review-impl MED#5 | Input order invariant | Adapter contract requires `output.Items[i]` ↔ `input.Texts[i]` 1:1; pre-allocated indexed writes. |
| /review-impl MED#6 | Format strictness | Handler-level canonical enum; per-backend variations rejected by adapter passthrough. |
| /review-impl MED#7 | Anti-bait deletion + positive lock | Delete TestAudioGoStillUsesLegacyPath; new audio_test.go has positive grep-lock. |
| /review-impl MED#8 | b64 vs URL rationale | Documented "uniform FE handling" reason. |
| /review-impl MED#9 | CREATE TABLE inline sync | Explicit in §5.7. |
| /review-impl MED#10 | transient_retry_budget=0 rationale | Char-billed × batch size amplification documented. |
| /review-impl MED#11 | Empty-bytes upload | Defensive check returns ErrAudioGenerationFailed. |
| /review-impl LOW#1 | speakOne defaults | Applied at adapter explicitly. |
| /review-impl LOW#3 | AUDIO_CACHE_TTL_HOURS env | Dropped (lifecycle is 1-day MinIO-server-side; no presign TTL needed). |
| /review-impl LOW#4 | nil vs empty slice test | Both cases covered in test list. |
| /review-impl LOW#5 | Extension source | Use caller-specified `format`, not upstream `contentType`. |
| /review-impl LOW#7 | Billing block preservation | Shown explicitly in §8.2. |
| /review-impl LOW#8 | Char limit | 4096 (matches OpenAI). |
| /review-impl LOW#13 | minio-go version pin | v7.0.100 (matches book-service). |
| /review-impl COSMETIC#3 | chunking check pattern | `len(chunking) > 0 && string(chunking) != "null"` on top-level param, not input map. |

---

**Status of this design:** READY-FOR-BUILD. All HIGH/MED findings folded inline.
