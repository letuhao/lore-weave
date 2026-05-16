# Phase 5d Design — video_gen Adapter + SDK + Contract

> **Status**: SHIPPED — BUILD complete. `/review-impl` round 1 caught 1 HIGH + 2 MED + 4 LOW + 1 COSMETIC; ALL 8 folded inline BEFORE BUILD. No BUILD-time surprises this cycle (Phase 5c-α + 5b lessons applied).
> **Cycle**: C-LLM-PHASE-5D
> **Size**: XL (files ≈18 · logic ≈9 · side-effects: 1 new operation activation + 1 DB CHECK constraint ALTER + 1 const MaxImg2VidInputBytes; field naming differs from sibling-repo integration guide due to actual-backend-vs-guide drift caught in /review-impl)
> **Plan ref**: [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md §5](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md)
> **Predecessor**: Phase 5c-α (image_gen adapter shipped) at HEAD `12fe6273`
> **CLARIFY answers locked**: (1) n=1 only — reject n != 1 at handler + adapter; (2) both `response_format=url` AND `response_format=b64_json` (b64 will upstream-error for realistic videos, but kept for parity with image_gen); (3) include optional `image` field for image-to-video models (Wan, LTX Video on local-image-generator-service); (4) share `isContentPolicyRejection` helper via refactor (move from openai_image.go to a shared file, both image and video reference it).
> **Strategic context (Path B step 2)**: 5c-α activated image_gen. This cycle ships video_gen. Together they unblock 5e (book-service + video-gen-service caller migration) and 5f (video-gen-service BFF deletion). After 5f, every external LLM/audio/image/video flows through `POST /v1/llm/jobs` — unified gateway invariant fully realized.

---

## 1. Goals

1. **Provider-registry gateway** gains a first-class `video_gen` operation on the unified contract:
   - `POST /v1/llm/jobs` `operation=video_gen` → `adapter.GenerateVideo` → `VideoGenResult` (single data entry).
2. **OpenAI adapter** implements `GenerateVideo` against the actual `local-image-generator-service` backend routes:
   - `POST {base}/v1/videos/generations/text-to-video` when no init_image → sync mode (default)
   - `POST {base}/v1/videos/generations/image-to-video` when init_image is set → sync mode (default)
   - Both return `{created, data: [{url}]}` in sync mode (same shape as image_gen).
   - **NOTE (/review-impl(DESIGN) HIGH#1)**: this departs from the (aspirational) integration guide at [G:/Works/local-image-generator-service/docs/EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md:682-687](G:/Works/local-image-generator-service/docs/EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md) which describes singular `/v1/video/generations`. The actual sibling-repo code at [G:/Works/local-image-generator-service/app/api/videos.py:168,220](G:/Works/local-image-generator-service/app/api/videos.py) uses plural `/v1/videos/` + `text-to-video`/`image-to-video` sub-segments. The existing `services/video-gen-service/app/routers/generate.py:158` follows the guide and is consequently broken against the only real backend; Phase 5e migrates it off this legacy path. Integration-guide drift tracked as `D-PHASE5D-INTEGRATION-GUIDE-VIDEO-PATH`.
3. **Anthropic / Ollama / LM Studio adapters** stub `GenerateVideo` to return `ErrOperationNotSupported` (none expose video gen).
4. **5-place sync invariant** for `video_gen`:
   - openapi `JobOperation` enum (NEW entry — unlike image_gen, video_gen was NOT reserved at Phase 2b)
   - migrate.go CHECK constraint (DROP + RECREATE migration per Phase 4a-β precedent)
   - SDK `JobOperation` Literal (NEW entry)
   - handler `validJobOperations` map (NEW entry)
   - notification-service op-label map (NEW entry)
5. **Python SDK** gains `Client.generate_video(prompt, ..., model_source, model_ref, duration, size, image=None)`.
6. **Shared content-policy helper** — `isContentPolicyRejection` moves from `openai_image.go` to a new shared file (`openai_content_policy.go`) so image + video both reference one source of truth.

### Non-goals

- **Caller migration** (video-gen-service [generate.py:158](services/video-gen-service/app/routers/generate.py)). 5e work.
- **video-gen-service deletion** + api-gateway-bff `/v1/video-gen/*` route retirement. 5f work.
- **Multi-video (n>1)**. CLARIFY chose n=1; defer to a follow-up if a real caller surfaces. Handler + adapter both reject `n != 1` with `LLM_INVALID_REQUEST`.
- **Video edits / variations**. Different OpenAI endpoints; defer to a hypothetical 5d-β.
- **Streaming / progressive video preview**. Not in any OpenAI-compat spec.

---

## 2. Contract changes

### 2.1 OpenAPI — `JobOperation` enum + new schemas

`contracts/api/llm-gateway/v1/openapi.yaml`:

```yaml
JobOperation:
  type: string
  enum:
    - chat
    - completion
    - embedding
    - stt
    - tts
    - image_gen
    - video_gen          # NEW — Phase 5d
    - entity_extraction
    - relation_extraction
    - event_extraction
    - fact_extraction
    - translation
```

**Sync-invariant state at start of 5d (Fix-#1-style table, mirroring 5c-α §2.1):**

| Slot | Has `video_gen`? | Action this cycle |
|---|---|---|
| openapi `JobOperation` enum | ❌ | ADD enum entry |
| migrate.go `llm_jobs.operation` CHECK constraint | ❌ | ALTER DROP+RECREATE (per Phase 4a-β `fact_extraction` precedent) |
| jobs_handler.go `validJobOperations` map | ❌ | ADD map entry |
| SDK `JobOperation` Literal | ❌ | ADD Literal entry |
| notification-service op label map | ❌ | ADD label entry |

This is the wider work that 5c-α dodged via Phase 2b reservation. All 5 entries are 1-line additions; the DB migration is an additive `ALTER TABLE llm_jobs DROP/ADD CONSTRAINT` block following the existing Phase 4a-β pattern in [migrate.go:150-158](services/provider-registry-service/internal/migrate/migrate.go#L150).

New schemas:

```yaml
VideoGenInput:
  type: object
  required: [prompt]
  description: |
    Phase 5d. Input payload for `SubmitJobRequest` with
    `operation: video_gen`. The gateway forwards to the upstream
    provider's OpenAI-compatible `POST /v1/video/generations` endpoint
    (singular "video" per the canonical contract).
  properties:
    prompt:
      type: string
      minLength: 1
      maxLength: 32000
      description: |
        Text description of the desired video. Cap matches ImageGenInput.
        Upstream models cap shorter (CLIP encoder ≈300-500 tokens for
        local backends; gpt-image-1-style: 32K).
    size:
      type: string
      default: "1920x1080"
      description: |
        Video dimensions. Common: "1920x1080", "1080x1920", "1080x1080",
        "1440x1080". Upstream validates supported sizes per model.
    duration:
      type: integer
      minimum: 1
      maximum: 60
      default: 5
      description: |
        Video duration in seconds. Upstream backends typically accept
        2..15s for SDXL/Flux-derived video models; some support up to
        60s. Gateway caps at 1..60; upstream-specific shorter caps
        surface as LLM_UPSTREAM_ERROR.
    n:
      type: integer
      enum: [1]
      default: 1
      description: |
        Number of videos. **n=1 only this cycle** per CLARIFY answer.
        Gateway rejects n != 1 at handler + adapter. Multi-video deferred
        to a follow-up if a real caller surfaces (video gen is GPU-minute
        expensive; few backends support n>1 anyway).
    response_format:
      type: string
      enum: [url]
      default: url
      description: |
        How to return video bytes. **url-only** per /review-impl(DESIGN)
        MED#3 — b64_json is impractical for video (even short 1080p MP4
        ≈2-5MB → b64 ≈7MB+ would exceed the 8MB `MaxImageResponseBytes`
        adapter cap). Handler rejects `b64_json` for video_gen with
        clear "use url mode" hint. Asymmetric with image_gen (which
        accepts both) — intentional; documented in handler error.
    style:
      type: string
      nullable: true
      description: |
        Optional style hint (model-dependent — Wan/LTX Video have their
        own style vocabularies). `null` to omit.
    init_image:
      type: string
      nullable: true
      description: |
        Optional base64-encoded image for image-to-video models
        (Wan, LTX Video on local-image-generator-service). When set,
        adapter dispatches to `/v1/videos/generations/image-to-video`
        instead of `text-to-video`. Format: raw base64 of PNG/JPG bytes
        (no data URI prefix). Upstream-dependent: backends without
        img2vid support reject with LLM_UPSTREAM_ERROR. `null` to omit
        (text-to-video mode).

        **Size cap** (/review-impl(DESIGN) MED#2): caller-side base64
        string capped at `MaxImg2VidInputBytes = 10MB` (covers 4K PNG
        equivalent ≈10-15MB raw → 13-20MB b64, but most realistic init
        frames are 1-2MB raw → 1.5-2.7MB b64). Handler rejects oversize
        with `LLM_INVALID_REQUEST: "init_image exceeds 10485760-byte cap"`.
        Adapter belt-and-suspenders rejects with `ErrVideoInvalidParams`.
        Field name `init_image` matches local-image-generator-service's
        actual API ([videos.py via init_image_multipart.py]); not `image`
        per the stale integration guide.

VideoGenResult:
  type: object
  required: [created, data]
  description: |
    Phase 5d. Result payload populated in `Job.result` when
    `operation: video_gen` and `status: completed`.
  properties:
    created:
      type: integer
      description: Unix timestamp (seconds) when generation finished.
    data:
      type: array
      minItems: 1
      maxItems: 1
      items:
        $ref: '#/components/schemas/VideoGenDataItem'

VideoGenDataItem:
  type: object
  description: |
    Single generated video. Exactly one of `url` or `b64_json` is
    populated based on the request's `response_format`. `revised_prompt`
    is present if the upstream model rewrote the prompt (rare for video;
    most backends don't have safety-system prompt rewriting).
  properties:
    url:
      type: string
      format: uri
      nullable: true
      description: |
        Upstream-hosted video URL. Caller is responsible for fetching
        and storing — gateway does NOT download. URL lifetime is
        upstream-dependent. Caller MUST fetch immediately after
        polling completed.
    b64_json:
      type: string
      nullable: true
      description: |
        Base64-encoded raw video bytes. Practical only for very short
        clips (≤1s at low res). Gateway adapter caps the response body
        at MaxImageResponseBytes (8MB decompressed); realistic videos
        will exceed this.
    revised_prompt:
      type: string
      nullable: true
      description: Upstream-rewritten prompt, if any. Null otherwise.
```

### 2.2 Adapter interface — new `GenerateVideo` method

`services/provider-registry-service/internal/provider/adapters.go`:

```go
type Adapter interface {
    // ... existing methods ...

    // GenerateVideo — Phase 5d. Text-to-video (and optionally
    // image-to-video) generation via OpenAI-compatible
    // /v1/video/generations endpoint. Adapter posts the request and
    // parses the response into GenerateVideoOutput. Adapters that
    // don't support video generation return ErrOperationNotSupported.
    GenerateVideo(ctx context.Context, endpointBaseURL, secret, modelName string, input GenerateVideoInput) (GenerateVideoOutput, Usage, error)
}
```

New types + sentinels:

```go
type GenerateVideoInput struct {
    // Prompt — required, max 32K. Adapter pre-checks empty.
    Prompt string

    // Size — e.g. "1920x1080"; "" → upstream default.
    Size string

    // Duration — seconds (1..60). 0 → omit (upstream default ≈5s typical).
    Duration int

    // N — Phase 5d locks to 1 only. Adapter rejects N != 1 with ErrVideoInvalidParams.
    N int

    // ResponseFormat — "url" | "b64_json"; "" → omit.
    ResponseFormat string

    // Style — optional style hint; "" → omit.
    Style string

    // InitImage — Phase 5d /review-impl(DESIGN) HIGH#1. Optional base64-encoded
    // image for image-to-video models. When non-empty, adapter dispatches
    // to /v1/videos/generations/image-to-video; otherwise /v1/videos/
    // generations/text-to-video. Field name matches local-image-generator-
    // service's VideoGenerateRequest.init_image (not "image" per the stale
    // integration guide). Capped at MaxImg2VidInputBytes (10MB) at handler;
    // adapter belt-and-suspenders rejects oversize.
    InitImage string
}

// MaxImg2VidInputBytes — Phase 5d /review-impl(DESIGN) MED#2. Cap on the
// base64-encoded init_image input field. 10MB covers 4K PNGs (~10-15MB
// raw → 13-20MB b64) for the typical case while bounding worst-case DB
// row size + worker goroutine memory. Larger init frames typically
// don't help video gen quality (the model resizes anyway).
const MaxImg2VidInputBytes = 10 * 1024 * 1024

type GenerateVideoOutput struct {
    Created int64
    Data    []GeneratedVideo  // always len 1 (n=1 lock)
}

type GeneratedVideo struct {
    URL           string
    B64JSON       string
    RevisedPrompt string
}

// ErrVideoGenerationFailed — Phase 5d. Generic upstream-failed sentinel
// (not content-policy, not rate-limited; e.g., model loading, ambiguous
// backend error). Caller maps to LLM_VIDEO_GENERATION_FAILED.
var ErrVideoGenerationFailed = fmt.Errorf("video generation failed")

// ErrVideoContentPolicy — Phase 5d. Content-policy rejection (rare for
// most local video backends; reserved for OpenAI/managed services with
// safety filters). Caller maps to LLM_VIDEO_CONTENT_POLICY_VIOLATION.
var ErrVideoContentPolicy = fmt.Errorf("video generation rejected by content policy")

// ErrVideoInvalidParams — Phase 5d /review-impl-anticipated MED. Adapter-
// level invariant rejection (Prompt empty, N != 1). Caller maps to
// LLM_INVALID_REQUEST.
var ErrVideoInvalidParams = fmt.Errorf("video generation params invalid")
```

No new `Max*` consts — video reuses `MaxImageResponseBytes` (8MB cap) for response body. Per `b64_json` design note, realistic videos will exceed this — but the cap fires uniformly with image and provides defense-in-depth.

### 2.3 Shared content-policy helper

**File move**: `isContentPolicyRejection` and its JSON-first body-check logic moves from `services/provider-registry-service/internal/provider/openai_image.go` to a NEW file `services/provider-registry-service/internal/provider/openai_content_policy.go`. Both `openai_image.go::GenerateImage` and `openai_video.go::GenerateVideo` call into it.

No behavior change. The existing image tests assert behavior; no test rewrites needed — just the import surface. Add a 1-line `var _ = isContentPolicyRejection` if Go complains about unused, but the new file makes it package-level so it's referenced from both call sites.

### 2.4 OpenAI adapter — `openai_video.go` (NEW)

Mirrors `openai_image.go` with path dispatch + img2vid handling:
- **Path dispatch**: POST `/v1/videos/generations/text-to-video` when `InitImage == ""`, else `/v1/videos/generations/image-to-video`. Per /review-impl(DESIGN) HIGH#1, this matches the actual local-image-generator-service routes; the singular `/v1/video/generations` in the integration guide is aspirational and unimplemented.
- **Pre-checks (more than image_gen)**:
  - Prompt empty → `ErrVideoInvalidParams("prompt required")`
  - N < 0 → `ErrVideoInvalidParams("n must be >= 0")` (LOW#5 — clearer phrasing for negative)
  - N > 1 → `ErrVideoInvalidParams("n=X exceeds cap; only n=1 supported")`
  - bad ResponseFormat → `ErrVideoInvalidParams`
  - InitImage > MaxImg2VidInputBytes → `ErrVideoInvalidParams("init_image exceeds Y bytes")` (MED#2)
- **Body assembly**: `model`/`prompt`/`size`/`duration`/`n=1`/`style` + `init_image` (NOT `image` — local-image-generator-service field name). Sync upstream mode (no `mode: "async"` in body; let it default to sync).
- **Response decode**: same `{created, data[{url}]}` shape as image_gen; single data item enforced.
- **Content-policy check** via shared `isContentPolicyRejection` helper (moved to `openai_content_policy.go` in T4).

```go
func (a *openaiAdapter) GenerateVideo(
    ctx context.Context,
    endpointBaseURL, secret, modelName string,
    input GenerateVideoInput,
) (GenerateVideoOutput, Usage, error) {
    // /review-impl(DESIGN) MED#5 phrasing — clearer messages per error type.
    if input.Prompt == "" {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "%w: prompt required", ErrVideoInvalidParams)
    }
    if input.N < 0 {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "%w: n must be >= 0 (got %d)", ErrVideoInvalidParams, input.N)
    }
    if input.N > 1 {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "%w: n=%d exceeds cap; only n=1 supported", ErrVideoInvalidParams, input.N)
    }
    if input.ResponseFormat != "" && input.ResponseFormat != "url" {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "%w: response_format=%q (only \"url\" supported for video; b64_json impractical)",
            ErrVideoInvalidParams, input.ResponseFormat)
    }
    // /review-impl(DESIGN) MED#2 — adapter-level init_image size cap.
    if len(input.InitImage) > MaxImg2VidInputBytes {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "%w: init_image exceeds %d bytes (got %d)",
            ErrVideoInvalidParams, MaxImg2VidInputBytes, len(input.InitImage))
    }

    base := strings.TrimRight(endpointBaseURL, "/")
    if base == "" { base = openaiBaseURL }

    // /review-impl(DESIGN) HIGH#1 — path dispatch based on init_image presence.
    // Matches local-image-generator-service's actual routes; the integration
    // guide's `/v1/video/generations` (singular) is aspirational.
    var upstreamPath string
    if input.InitImage != "" {
        upstreamPath = "/v1/videos/generations/image-to-video"
    } else {
        upstreamPath = "/v1/videos/generations/text-to-video"
    }

    body := map[string]any{
        "model":  modelName,
        "prompt": input.Prompt,
    }
    if input.Size != "" { body["size"] = input.Size }
    if input.Duration > 0 { body["duration"] = input.Duration }
    body["n"] = 1  // always 1 per Phase 5d lock
    // response_format defaults to url; only send when explicitly url (omitted otherwise lets upstream pick)
    if input.ResponseFormat != "" { body["response_format"] = input.ResponseFormat }
    if input.Style != "" { body["style"] = input.Style }
    if input.InitImage != "" { body["init_image"] = input.InitImage }  // field name per local-image-generator-service
    // NOTE: no "mode" field → upstream defaults to sync mode → 200 with
    // {created, data} inline. Async mode would return 202 + require us to
    // poll /v1/videos/generations/{job_id}; gateway already polls its own
    // /v1/llm/jobs above us, so double-polling is wasteful.

    bodyBytes, _ := json.Marshal(body)
    req, _ := http.NewRequestWithContext(ctx, http.MethodPost,
        base+upstreamPath, bytes.NewReader(bodyBytes))
    req.Header.Set("Content-Type", "application/json")
    if secret != "" { req.Header.Set("Authorization", "Bearer "+secret) }

    resp, err := a.client.Do(req)
    if err != nil { return GenerateVideoOutput{}, Usage{}, fmt.Errorf("upstream transport: %w", err) }
    defer resp.Body.Close()

    respBytes, _ := io.ReadAll(io.LimitReader(resp.Body, MaxImageResponseBytes+1))
    if len(respBytes) > MaxImageResponseBytes {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "%w: upstream response exceeds %d bytes",
            ErrVideoGenerationFailed, MaxImageResponseBytes)
    }

    if resp.StatusCode < 200 || resp.StatusCode >= 300 {
        if isContentPolicyRejection(resp.StatusCode, respBytes) {
            return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
                "%w: %s", ErrVideoContentPolicy,
                truncateBody(string(respBytes), 4096))
        }
        retryAfter := parseRetryAfter(resp.Header.Get("Retry-After"))
        return GenerateVideoOutput{}, Usage{},
            ClassifyUpstreamHTTP(resp.StatusCode, string(respBytes), retryAfter)
    }

    var parsed struct {
        Created int64 `json:"created"`
        Data    []struct {
            URL           string `json:"url"`
            B64JSON       string `json:"b64_json"`
            RevisedPrompt string `json:"revised_prompt"`
        } `json:"data"`
    }
    if err := json.Unmarshal(respBytes, &parsed); err != nil {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "decode video-gen response: %w (body=%s)", err, truncateBody(string(respBytes), 1024))
    }
    if len(parsed.Data) == 0 {
        return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
            "%w: upstream returned no videos", ErrVideoGenerationFailed)
    }

    // Phase 5d locks to n=1 — adapter normalizes by taking the first
    // entry, but a sanity check would also work. Most backends only
    // return 1 anyway.
    out := GenerateVideoOutput{
        Created: parsed.Created,
        Data:    make([]GeneratedVideo, 1),
    }
    out.Data[0] = GeneratedVideo{
        URL:           parsed.Data[0].URL,
        B64JSON:       parsed.Data[0].B64JSON,
        RevisedPrompt: parsed.Data[0].RevisedPrompt,
    }
    return out, Usage{}, nil
}
```

### 2.5 Other adapters — stubs (`adapters_video.go` NEW)

Mirrors `adapters_image.go`:

```go
func (a *anthropicAdapter) GenerateVideo(...) (GenerateVideoOutput, Usage, error) {
    return GenerateVideoOutput{}, Usage{}, ErrOperationNotSupported
}
func (a *ollamaAdapter) GenerateVideo(...) (GenerateVideoOutput, Usage, error) {
    return GenerateVideoOutput{}, Usage{}, ErrOperationNotSupported
}
func (a *lmStudioAdapter) GenerateVideo(...) (GenerateVideoOutput, Usage, error) {
    return GenerateVideoOutput{}, Usage{}, ErrOperationNotSupported
}
```

### 2.6 Worker dispatch — `processVideoGenJob` + `worker_video.go` (NEW)

Parallel to `worker_image.go`. Key constant:

```go
// VideoGenJobTimeout — Phase 5d. Wall-clock cap on a single video-gen job.
// Multi-step ComfyUI workflows for 5-second 1080p clips (Wan, LTX Video,
// SDXL-derived video models) commonly take 5-15 min; longer durations
// can hit 20+ min. 30 min gives headroom without indefinitely pinning
// the worker goroutine. 3× longer than ImageGenJobTimeout (10 min) and
// 6× longer than SttJobTimeout (5 min).
const VideoGenJobTimeout = 30 * time.Minute
```

```go
var videoJobOperations = map[string]struct{}{
    "video_gen": {},
}

func isVideoJobOperation(op string) bool {
    _, ok := videoJobOperations[op]
    return ok
}

func (w *Worker) processVideoGenJob(...) { /* mirrors processImageGenJob */ }
func (w *Worker) runVideoGenJob(...) { /* mirrors runImageGenJob, single-data-item */ }

func classifyVideoError(ctx context.Context, err error) (code, status string) {
    // Mirror classifyImageError with:
    // - ErrVideoInvalidParams → LLM_INVALID_REQUEST/failed
    // - ErrVideoContentPolicy → LLM_VIDEO_CONTENT_POLICY_VIOLATION/failed
    // - ErrVideoGenerationFailed → LLM_VIDEO_GENERATION_FAILED/failed
    // - typed upstream errors → same as image
    // - default → LLM_UPSTREAM_ERROR/failed
}
```

Worker dispatch hook in `worker.go::Process` AFTER image dispatch (mirrors audio → image → video → streamable ordering):

```go
if isAudioJobOperation(operation) { /* ... */ return }
if isImageJobOperation(operation) { /* ... */ return }
if isVideoJobOperation(operation) {
    w.processVideoGenJob(...)
    return
}
// ... streamable whitelist fall-through
```

### 2.7 Handler — `validateVideoGenInput`

`services/provider-registry-service/internal/api/jobs_handler.go`:

```go
if in.Operation == "video_gen" {
    if err := validateVideoGenInput(in.Input, in.Chunking); err != nil {
        writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", err.Error())
        return
    }
}

func validateVideoGenInput(raw json.RawMessage, chunking json.RawMessage) error {
    if len(chunking) > 0 && string(chunking) != "null" {
        return fmt.Errorf("chunking not supported for video_gen")
    }
    var v struct {
        Prompt         string `json:"prompt"`
        Duration       int    `json:"duration"`
        N              int    `json:"n"`
        ResponseFormat string `json:"response_format"`
        InitImage      string `json:"init_image"`
    }
    if err := json.Unmarshal(raw, &v); err != nil {
        return fmt.Errorf("video_gen input parse: %w", err)
    }
    if strings.TrimSpace(v.Prompt) == "" {
        return fmt.Errorf("video_gen requires non-empty prompt")
    }
    if len(v.Prompt) > 32000 {
        return fmt.Errorf("video_gen prompt exceeds 32000-char cap (got %d)", len(v.Prompt))
    }
    if v.Duration != 0 && (v.Duration < 1 || v.Duration > 60) {
        return fmt.Errorf("video_gen duration must be 1..60s (got %d)", v.Duration)
    }
    if v.N != 0 && v.N != 1 {
        return fmt.Errorf("video_gen n must be 1 (got %d)", v.N)
    }
    // /review-impl(DESIGN) MED#3 — reject b64_json at handler with clear
    // hint. Asymmetric with image_gen (which accepts both); video b64
    // exceeds 8MB cap in practice so accepting it would be a UX footgun.
    if v.ResponseFormat != "" && v.ResponseFormat != "url" {
        return fmt.Errorf("video_gen response_format must be \"url\" (b64_json impractical for video; got %q)", v.ResponseFormat)
    }
    // /review-impl(DESIGN) MED#2 — init_image size cap to bound DB row + memory.
    if len(v.InitImage) > provider.MaxImg2VidInputBytes {
        return fmt.Errorf("video_gen init_image exceeds %d-byte cap (got %d)", provider.MaxImg2VidInputBytes, len(v.InitImage))
    }
    return nil
}
```

### 2.8 SDK Python — `Client.generate_video()`

`sdks/python/loreweave_llm/client.py`:

```python
async def generate_video(
    self,
    prompt: str,
    *,
    model_source: ModelSource,
    model_ref: str,
    size: str | None = None,
    duration: int | None = None,
    response_format: Literal["url"] = "url",  # url-only per MED#3
    style: str | None = None,
    init_image: str | None = None,  # base64 for img2vid (renamed from `image` per HIGH#1)
    user_id: str | None = None,
    poll_interval_s: float = 1.0,
    max_poll_interval_s: float = 30.0,
) -> VideoGenResult:
    """Phase 5d — submit video-gen job, wait for terminal, return decoded result.

    Polling defaults slower than image (1s initial, 30s max) because
    video gen runs longer (ComfyUI Wan/LTX Video typically 5-15 min;
    longer durations push 20+ min).

    Note: n is intentionally NOT a parameter — Phase 5d locks to n=1.
    Multi-video support deferred to a follow-up if a real caller surfaces.

    Note: SDK signature follows Phase 5c-α /review-impl(BUILD) MED#1
    learning — all optional fields use `None` sentinel with `is not None`
    wire-inclusion checks, so explicit caller values are never silently
    dropped.

    Raises:
      - LLMInvalidRequest on malformed model_ref or empty prompt
      - LLMVideoContentPolicy on content-policy rejection
      - LLMVideoGenerationFailed on generic backend failure
      - LLMError subclass keyed by job.error.code on other failures
      - LLMJobTerminal on status=cancelled
    """
    # UUID validation, prompt validation, build input_payload with
    # `if x is not None: include`, submit_job, wait_terminal,
    # decode VideoGenResult.
```

New SDK models:

```python
# sdks/python/loreweave_llm/models.py
class VideoGenDataItem(BaseModel):
    url: str | None = None
    b64_json: str | None = None
    revised_prompt: str | None = None

class VideoGenResult(BaseModel):
    created: int
    data: list[VideoGenDataItem] = Field(min_length=1, max_length=1)
```

New SDK errors:

```python
# sdks/python/loreweave_llm/errors.py
class LLMVideoContentPolicy(LLMError):
    code = "LLM_VIDEO_CONTENT_POLICY_VIOLATION"

class LLMVideoGenerationFailed(LLMError):
    code = "LLM_VIDEO_GENERATION_FAILED"
```

Register in `_CODE_TO_EXC` + export from `__init__.py`.

SDK `JobOperation` Literal in `models.py`:

```python
JobOperation = Literal[
    "chat", "completion", "embedding",
    "stt", "tts",
    "image_gen", "video_gen",   # video_gen NEW
    "entity_extraction", "relation_extraction",
    "event_extraction", "fact_extraction",
    "translation",
]
```

### 2.9 Migration — `migrate.go` ALTER

`services/provider-registry-service/internal/migrate/migrate.go` — append a Phase 5d ALTER block following the Phase 4a-β `fact_extraction` precedent:

```sql
-- Phase 5d: drop + recreate operation CHECK to add video_gen.
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
  'chat','completion','embedding','stt','tts','image_gen','video_gen',
  'entity_extraction','relation_extraction','event_extraction',
  'fact_extraction','translation'
));
```

The CREATE TABLE in the same file also gets `video_gen` added inline so cold schemas don't run the ALTER on an already-extended constraint.

### 2.10 Notification-service op label

`services/notification-service/internal/consumer/consumer.go::opLabel` adds:

```go
"video_gen": "Video gen",
```

And the corresponding test fixture in `consumer_test.go`.

---

## 3. Architecture & data flow

### 3.1 Sequence — video_gen submit + poll

Identical shape to image_gen 5c-α. Two practical differences:
- Polling takes longer (caller code should anticipate 5-30 min wait, not 30s-2min like image)
- Result `data` array always has exactly 1 entry

```
Caller                    gateway                  Upstream (e.g., local-image-generator-service:8700)
  │ POST /internal/llm/jobs │                          │
  │ {operation:video_gen,   │                          │
  │  input:{prompt, size,   │                          │
  │         duration, ...}} │                          │
  │─────────────────────────▶│                          │
  │ 202 {job_id}             │                          │
  │◀─────────────────────────│                          │
  │                          │ goroutine:               │
  │                          │   adapter.GenerateVideo  │
  │                          │   POST /v1/video/        │
  │                          │   generations            │
  │                          │─────────────────────────▶│
  │ poll GET /jobs/{id}      │   (5-30 min)             │
  │─────────────────────────▶│                          │
  │ status:running           │                          │
  │ ...                      │                          │
  │ poll GET /jobs/{id}      │   {created, data:        │
  │─────────────────────────▶│    [{url}]}              │
  │                          │◀─────────────────────────│
  │ {status:completed,       │ finalize completed       │
  │  result:{...}}           │                          │
  │◀─────────────────────────│                          │
```

### 3.2 No streaming, no chunking

Same as image_gen: single request-response. Single state transition. No `chunking` config; handler rejects.

### 3.3 Backward-compat / forward-compat with video-gen-service

This cycle does NOT migrate the existing `services/video-gen-service/` BFF caller. That's 5e work. After 5d ships:
- `services/video-gen-service/app/routers/generate.py:158` still calls `/v1/video/generations` directly via http.Client (legacy path)
- `POST /v1/llm/jobs operation=video_gen` works for new callers (book-service after 5e migrates from image_gen → video_gen too if it adds video features)
- Both paths coexist until 5f deletes video-gen-service

---

## 4. Tests

### 4.1 Adapter tests (`adapters_video_test.go` — NEW)

12 cases:
- `TestOpenAIAdapter_GenerateVideo_HappyPath_TextToVideo` — POST hits `/v1/videos/generations/text-to-video`; body has `n=1` + no `init_image` + sync mode (no `mode` field); url decode
- `TestOpenAIAdapter_GenerateVideo_HappyPath_Img2Vid_PathDispatch` — `InitImage="..."` → POST hits `/v1/videos/generations/image-to-video` (NOT text-to-video); body has `init_image` field present
- `TestOpenAIAdapter_GenerateVideo_RejectsEmptyPrompt` — ErrVideoInvalidParams
- `TestOpenAIAdapter_GenerateVideo_RejectsNegativeN` — n=-1 → "n must be >= 0" message
- `TestOpenAIAdapter_GenerateVideo_RejectsNGreaterThan1` — n=2 → "exceeds cap" message
- `TestOpenAIAdapter_GenerateVideo_RejectsBadResponseFormat` — "b64_json" or "mp4" → ErrVideoInvalidParams (adapter only accepts url)
- `TestOpenAIAdapter_GenerateVideo_RejectsOversizeInitImage` — InitImage > MaxImg2VidInputBytes → ErrVideoInvalidParams (/review-impl(DESIGN) MED#2)
- `TestOpenAIAdapter_GenerateVideo_ContentPolicy_JSONErrorCode` — shared helper still works after refactor (T4)
- `TestOpenAIAdapter_GenerateVideo_OversizeResponseRejected` — 8MB+ → ErrVideoGenerationFailed
- `TestOpenAIAdapter_GenerateVideo_RateLimit429` — typed-upstream propagation
- `TestOpenAIAdapter_GenerateVideo_AuthFailed401` — typed-upstream permanent
- `TestNonOpenAIAdapters_GenerateVideo_Unsupported` — 3 stub locks (anthropic + ollama + lmStudio)

### 4.2 Worker tests (`worker_video_test.go` — NEW)

Mirrors `worker_image_test.go`:
- `TestIsVideoJobOperation_Whitelist`
- `TestVideoJobOperations_Disjoint` — vs streamable, audio, image (3-way pairwise)
- `TestVideoJobOperations_AlsoInValidJobOperations` — 5-place sync grep
- `TestClassifyVideoError_*` — 10 classify matrix cases (mirror image's)

### 4.3 Handler tests (`jobs_router_test.go` — NEW cases)

8 video_gen cases:
- `TestInternalSubmitLlmJob_VideoGen_ValidationPasses`
- `TestInternalSubmitLlmJob_VideoGen_ValidationPasses_WithInitImage` — img2vid mode reaches 503 (validation passed)
- `TestInternalSubmitLlmJob_VideoGen_RejectsEmptyPrompt`
- `TestInternalSubmitLlmJob_VideoGen_RejectsOversizePrompt`
- `TestInternalSubmitLlmJob_VideoGen_RejectsDurationOutOfRange` (0 OK; 61+ rejected)
- `TestInternalSubmitLlmJob_VideoGen_RejectsNNot1` (n=2 → 400)
- `TestInternalSubmitLlmJob_VideoGen_RejectsB64JsonFormat` — `response_format=b64_json` → 400 with "use url" hint (/review-impl(DESIGN) MED#3)
- `TestInternalSubmitLlmJob_VideoGen_RejectsOversizeInitImage` — InitImage > 10MB → 400 (/review-impl(DESIGN) MED#2)
- `TestInternalSubmitLlmJob_VideoGen_RejectsChunkingConfig`

### 4.4 SDK tests (`test_video_gen.py` — NEW)

8 cases (parallel to test_image_gen.py with video specifics):
- `test_generate_video_happy_path_url_mode` — submit + poll + decode + `init_image` NOT in wire (txt2vid)
- `test_generate_video_img2vid_includes_init_image_field` — `init_image=` param flows to wire body as `init_image` (NOT `image`); regression-lock for HIGH#1 field-name fix
- `test_generate_video_rejects_malformed_model_ref_before_wire`
- `test_generate_video_rejects_empty_prompt_before_wire`
- `test_generate_video_rejects_b64_format_before_wire` — SDK Literal narrows response_format to "url" only; pydantic validation rejects "b64_json" at client construction
- `test_generate_video_content_policy_raises_llmvideocontentpolicy`
- `test_generate_video_generation_failed_raises_llmvideogenerationfailed`
- `test_video_errors_have_specific_classes_regression_lock` — same regression pattern as image_gen

### 4.5 Content-policy refactor

The relocation of `isContentPolicyRejection` to `openai_content_policy.go` doesn't need new tests — the existing image tests (4 cases: JSONErrorCode + PromptEchoNotMisclassified + NonJSONSubstringFallback) continue to cover the helper. The video test `TestOpenAIAdapter_GenerateVideo_ContentPolicy_JSONErrorCode` adds verification that video adapter also reaches the helper correctly.

---

## 5. Build plan (PLAN phase)

| # | Task | Files | Size |
|---|------|-------|------|
| T1 | OpenAPI: add `video_gen` to JobOperation enum + `VideoGenInput` (with `init_image` field — NOT `image` per HIGH#1; `response_format` enum is `[url]` only per MED#3) + `VideoGenResult` + `VideoGenDataItem` schemas | `contracts/api/llm-gateway/v1/openapi.yaml` | XS |
| T2 | DB migration: ALTER llm_jobs_operation_check to add `video_gen`; update CREATE TABLE block inline for cold schemas | `services/provider-registry-service/internal/migrate/migrate.go` | XS |
| T3 | Adapter types: `GenerateVideoInput`/Output/`GeneratedVideo` (InitImage field — NOT Image); +3 sentinels (`ErrVideoGenerationFailed`/`ErrVideoContentPolicy`/`ErrVideoInvalidParams`); +`MaxImg2VidInputBytes=10MB` const (MED#2); Adapter interface +GenerateVideo | `services/provider-registry-service/internal/provider/adapters.go` | S |
| T4 | **Refactor**: move `isContentPolicyRejection` from `openai_image.go` to NEW `openai_content_policy.go` (shared by image + video). Update import surface in openai_image.go (no code change, just relocation) | `services/provider-registry-service/internal/provider/openai_content_policy.go` (NEW) + `openai_image.go` | XS |
| T5 | OpenAI adapter: `openai_video.go` NEW with GenerateVideo implementation — **path dispatch** `/v1/videos/generations/text-to-video` vs `/v1/videos/generations/image-to-video` based on InitImage (HIGH#1); adapter-level invariants (empty Prompt + N<0 + N>1 + bad ResponseFormat + InitImage size cap per MED#2); body field `init_image` not `image`; shared content-policy check; single-data-item normalization; sync upstream mode (no `mode: "async"` body field) | `services/provider-registry-service/internal/provider/openai_video.go` (NEW) | M |
| T6 | Adapter stubs: `adapters_video.go` NEW with Anthropic/Ollama/LM Studio stubs | `services/provider-registry-service/internal/provider/adapters_video.go` (NEW) | XS |
| T7 | Adapter tests: 10 cases incl. img2vid + content-policy via shared helper + invariants + typed upstream + 3 stub locks | `services/provider-registry-service/internal/provider/adapters_video_test.go` (NEW) | M |
| T8 | Worker: `worker_video.go` NEW with `processVideoGenJob` + `runVideoGenJob` + `classifyVideoError` + `videoJobOperations` whitelist + `VideoGenJobTimeout=30min` | `services/provider-registry-service/internal/jobs/worker_video.go` (NEW) | S |
| T9 | Worker dispatch hook in `worker.go::Process` — route to processVideoGenJob when isVideoJobOperation(op); update inline comment to reflect 3 dispatch paths (audio/image/video) before chat-streaming | `services/provider-registry-service/internal/jobs/worker.go` + `worker_test.go` | XS |
| T10 | Worker tests: classify matrix (10 cases) + whitelist + disjoint (3-way pairwise) + 5-place sync grep | `services/provider-registry-service/internal/jobs/worker_video_test.go` (NEW) | S |
| T11 | Handler: `validateVideoGenInput` (rejects b64_json per MED#3; size-caps init_image per MED#2; rejects chunking) + dispatch on operation=video_gen + add `video_gen` to `validJobOperations` map | `services/provider-registry-service/internal/api/jobs_handler.go` | S |
| T12 | Handler tests: 8 cases (happy txt2vid + happy img2vid + empty/oversize prompt + duration out of range + n != 1 + b64_json rejected + oversize init_image rejected + chunking rejected) | `services/provider-registry-service/internal/api/jobs_router_test.go` | S |
| T13 | Notification op-label: add `video_gen → "Video gen"` to opLabel map + test fixture | `services/notification-service/internal/consumer/consumer.go` + `consumer_test.go` | XS |
| T14 | SDK: `Client.generate_video()` method (parameters use `None` sentinel per Phase 5c-α MED#1 learning); `response_format: Literal["url"] = "url"` only per MED#3; `init_image: str \| None = None` (NOT `image` per HIGH#1); `VideoGenResult` + `VideoGenDataItem` pydantic models; add `video_gen` to `JobOperation` Literal | `sdks/python/loreweave_llm/client.py` + `models.py` | M |
| T15 | SDK errors: `LLMVideoContentPolicy` + `LLMVideoGenerationFailed` classes + `_CODE_TO_EXC` mapping + __init__ exports | `sdks/python/loreweave_llm/errors.py` + `__init__.py` | S |
| T16 | SDK tests: 8 cases incl. img2vid wire shape + regression-lock for new error classes | `sdks/python/tests/test_video_gen.py` (NEW) | S |
| T17 | Doc updates: `LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` Phase 5d row ✅; design doc status flip; SESSION_PATCH inline at commit time | `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` + this design doc | XS |

Total: ~18 files (5 NEW go files + 1 NEW SDK test file + 1 NEW design doc; 11+ MOD). Build order: T1-T2 contracts + migration; T3-T7 gateway adapter; T8-T10 worker; T11-T12 handler; T13 notification; T14-T16 SDK; T17 docs.

---

## 6. Open questions / risks

| # | Question | Answer / mitigation |
|---|---|---|
| Q1 | Can b64_json videos realistically fit in 8MB? | Probably NOT for any realistic clip (1-second 1080p MP4 ≈ 1-2MB raw; b64 = 1.5-3MB; longer clips quickly exceed 8MB). Handler accepts the field for parity with image_gen, but most callers will get LLM_UPSTREAM_ERROR on b64 mode. Acceptable — the contract is consistent; callers learn to use `url` mode. |
| Q2 | The 30-min `VideoGenJobTimeout` — is that enough? | Sufficient for the common case (≤15-second clips on Wan/LTX Video typically 10-20 min). Marathon cases (60-second clips, complex img2vid prompts) might exceed. If telemetry surfaces frequent LLM_TIMEOUT, raise the const. Defer to a follow-up if observed. |
| Q3 | What if upstream returns >1 video despite our n=1 lock? | Adapter normalizes by taking `parsed.Data[0]` only. This silently drops upstream extras (rare/unusual). A defensive check could reject; pragmatic choice is to take-first since the caller asked for 1. |
| Q4 | `image` field is base64 — should we validate it's valid base64 / a real image before forwarding? | NO. Adapter is pass-through; upstream validates. Validating server-side would require decoding + sniffing, adding GPU-side concerns. If a real "garbage in" issue surfaces, add a length cap or basic format sniff. Defer as `D-PHASE5D-IMG2VID-INPUT-VALIDATION`. |
| Q5 | Polling interval for SDK — 1s/30s is slower than image (0.5s/10s). Risk of perceived latency on quick wins? | If a backend completes in 30s, caller waits up to 30s for the next poll. Real wins are rare; most backends take minutes. Acceptable trade-off — less load on the gateway poll endpoint. |
| Q6 | What about a video-gen caller that needs progress percentage (e.g., FE wants a progress bar)? | Out of scope. The job table has `chunks_done/chunks_total` but those don't map to video frames. Future work: emit progress events via the notification-service stream. Defer as `D-PHASE5D-PROGRESS-EVENTS`. |
| Q7 | Should we deprecate the existing `/v1/video-gen/*` route in api-gateway-bff in this cycle? | NO. That's Phase 5f. 5d only adds the gateway internals; caller migration is 5e; deprecation is 5f. |
| Q8 | Integration guide says `/v1/video/generations` (singular); actual backend uses `/v1/videos/generations/text-to-video`. Existing video-gen-service follows the guide. | (/review-impl(DESIGN) HIGH#1) 5d follows the actual backend paths. Tracked as `D-PHASE5D-INTEGRATION-GUIDE-VIDEO-PATH` for a cross-repo PR to update the guide. video-gen-service's broken legacy path is irrelevant after Phase 5e migrates it through the new gateway operation. |
| Q9 | b64_json mode for video — contract-symmetric with image_gen but practically unusable. | (/review-impl(DESIGN) MED#3) Handler rejects b64_json for video_gen with clear "use url mode" hint. Contract asymmetric (image accepts both; video accepts url only) but documented in openapi enum + handler error. |
| Q10 | init_image input field has no size cap → DB bloat from 50MB base64 strings. | (/review-impl(DESIGN) MED#2) Added `MaxImg2VidInputBytes = 10MB` const; handler + adapter both enforce. |
| Q11 | Dual maintenance risk between unified gateway path (5d) and legacy video-gen-service path until 5f. | (/review-impl(DESIGN) LOW#6) Accept-and-document. Flag explicitly in Phase 5e/5f planning so contract drift doesn't accumulate. Reminder added to §9 sequencing table. |

---

## 7. Acceptance criteria (QC phase)

- [ ] `go build ./...` clean
- [ ] `go vet ./...` clean
- [ ] `go test -count=1 ./...` ALL GREEN; delta +~20 tests (10 adapter + 5 worker classify + 1 disjoint + 1 whitelist + 1 5-place sync + 7 handler)
- [ ] `pytest sdks/python/tests/` 185 + 8 = 193 passed
- [ ] `pytest services/chat-service/tests/` 180 unchanged
- [ ] OpenAPI schema validates
- [ ] `/review-impl` on design doc returns no HIGH-severity findings
- [ ] `/review-impl` on post-BUILD code returns no HIGH findings; MEDs fixed inline before commit
- [ ] LIVE smoke (deferred to 5d-followup if not run in QC). Tracking item: `D-PHASE5D-LIVE-SMOKE`.

**Concrete live-smoke procedure** (parallel to 5c-α §7):

```bash
# 1. Start local-image-generator-service (sibling repo)
cd G:/Works/local-image-generator-service
docker compose up -d
curl http://127.0.0.1:8700/health
# → {"status":"ok"}

# 2. Register provider credential pointing at local-image-generator-service
#    (same setup as 5c-α live smoke)

# 3. Submit video_gen via internal endpoint:
curl -X POST "http://localhost:8085/internal/llm/jobs?user_id=<USER_UUID>" \
  -H "X-Internal-Token: $INTERNAL_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "video_gen",
    "model_source": "user_model",
    "model_ref": "<USER_MODEL_UUID>",
    "input": {
      "prompt": "a serene mountain lake at dawn, cinematic camera pan",
      "size": "1080x1080",
      "duration": 5,
      "n": 1,
      "response_format": "url"
    }
  }'
# Returns 202 {"job_id": "...", "status": "pending"}

# 4. Poll the job (expect 5-15 min for first response):
JOB_ID=<from above>
watch -n 10 'curl -X GET "http://localhost:8085/internal/llm/jobs/$JOB_ID?user_id=<USER_UUID>" \
  -H "X-Internal-Token: $INTERNAL_SERVICE_TOKEN" | jq .status'

# 5. When status=completed, verify data[0].url:
curl -I <data[0].url>
# → HTTP/1.1 200 OK, Content-Type: video/mp4

# 6. Optional: try img2vid by adding "image": "<base64-of-png>" to the input
```

**Success signals**:
- 202 on submit
- `provider-registry-service` logs show `processVideoGenJob` invocation
- Upstream call hits `http://127.0.0.1:8700/v1/videos/generations/text-to-video` (or `/image-to-video` if init_image was set) — verifiable in local-image-generator-service logs
- Job moves pending → running → completed within 30 min
- `data[0].url` returns a real MP4 (≥100KB body)

**Path divergence note (/review-impl(DESIGN) HIGH#1):** The actual upstream path is `/v1/videos/generations/text-to-video` (plural + sub-segment) per [G:/Works/local-image-generator-service/app/api/videos.py:168](G:/Works/local-image-generator-service/app/api/videos.py). The integration guide's `/v1/video/generations` (singular) is aspirational and unimplemented in the backend. Phase 5e will migrate the legacy video-gen-service which today calls the singular path and is presumably broken. Tracked as `D-PHASE5D-INTEGRATION-GUIDE-VIDEO-PATH`.

---

## 8. Phase 5e/5f preview

- **5e (XL)** — caller migration. Two callers:
  - book-service [media.go:449](services/book-service/internal/api/media.go) — Go; image_gen only today (could add video_gen later). Phase 5e migrates the image_gen call to `POST /v1/llm/jobs operation=image_gen`. Go SDK question to be settled (full SDK vs. thin shim).
  - video-gen-service [generate.py:158](services/video-gen-service/app/routers/generate.py) — Python; calls `/v1/video/generations` directly. Migrates to `Client.generate_video()` via existing Python SDK.
- **5f (M)** — `services/video-gen-service/` deletion. Remove the BFF + compose entry + api-gateway-bff `/v1/video-gen/*` routes. FE switches to calling unified gateway via SDK or BFF facade.

By 5f close: every external LLM/audio/image/video flows through `POST /v1/llm/jobs` (or `/v1/llm/stream` for streaming). Unified gateway invariant fully realized.

---

## 9. Path B sequencing summary (architectural)

| Phase | What | Status |
|---|---|---|
| **5c-α** | image_gen adapter + SDK + openapi | ✅ shipped (HEAD 12fe6273) |
| **5d** | video_gen adapter + SDK + openapi + 5-slot registration | ← this cycle |
| **5e** | Caller migration: book-service (Go) + video-gen-service (Python). **Reminder (/review-impl(DESIGN) LOW#6)**: video-gen-service's legacy path is presumably broken against local-image-generator-service today (hits singular `/v1/video/generations` 404); 5e migration also fixes that. Dual-maintenance window between 5d ship + 5e ship should be kept short. | TBD; needs Go SDK decision |
| **5f** | video-gen-service deletion + api-gateway-bff `/v1/video-gen/*` retirement | TBD |

After 5f: unified gateway invariant fully realized for chat, extraction, translation, audio, image, video. All external generation flows through one place; one credential resolution path; one billing path; one adapter interface.
