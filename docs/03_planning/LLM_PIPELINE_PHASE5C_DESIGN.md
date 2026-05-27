# Phase 5c-α Design — image_gen Adapter + SDK + Contract

> **Status**: SHIPPED — BUILD complete. `/review-impl` round 1 caught 0 HIGH + 5 MED + 6 LOW + 1 COSMETIC; ALL 12 folded inline BEFORE BUILD. No BUILD-time surprises this cycle (5b's httpx-multipart + from_code routing gotchas were already factored in).
> **Cycle**: C-LLM-PHASE-5C-ALPHA
> **Size**: XL (files ≈13 · logic ≈8 · side-effects: 1 new operation activation on `/v1/llm/jobs` — JobOperation enum/CHECK/SDK Literal already present from Phase 2b reservation)
> **Plan ref**: [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md §5](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md)
> **Predecessor**: Phase 5b (chat-service voice migration; audio paths retired) at HEAD `58fd1acd`
> **CLARIFY answers locked**: (1) async submit→poll via `POST /v1/llm/jobs` `operation=image_gen` (matches Phase 5a STT); (2) caller-side URL→MinIO download (matches chat-service voice — gateway forwards URL/bytes, caller owns storage); (3) multi-image `n=1..4` supported; (4) both `response_format=url` AND `response_format=b64_json` supported (OpenAI spec 1:1).
> **Strategic context (Path B)**: this is the first step of a multi-cycle program to retire `services/video-gen-service/` (currently a thin BFF wrapper around external generation) by promoting image_gen + video_gen to first-class unified-gateway operations. 5c-α ships the adapter/SDK; 5d ships video_gen; 5e migrates callers; 5f deletes the BFF.

---

## 1. Goals

1. **Provider-registry gateway** gains a first-class `image_gen` operation on the unified contract:
   - `POST /v1/llm/jobs` `operation=image_gen` → `adapter.GenerateImage` → `ImageGenResult`
2. **OpenAI adapter** implements `GenerateImage` against the OpenAI-compatible `POST /v1/images/generations` upstream — works against OpenAI proper, the [sibling `local-image-generator-service`](https://example.local/G-Works-local-image-generator-service) (ComfyUI backend at `:8700`), and any other OpenAI-compatible image-gen service users register as a BYOK provider.
3. **Anthropic / Ollama / LM Studio adapters** stub `GenerateImage` to return `ErrOperationNotSupported` (none expose OpenAI-compat image gen; image flows through OpenAI-shaped endpoints only).
4. **Python SDK** gains `Client.generate_image(prompt, ..., model_source, model_ref)` — submit-and-wait wrapper matching `transcribe()` (Phase 5a) ergonomics.
5. **Multi-image** support: `n=1..4` cap at handler validation; result `data` array carries 1–4 entries.
6. **Both response formats**: `url` (default — gateway returns upstream URL unchanged) and `b64_json` (gateway passes the bytes inline). Caller picks via `ImageGenInput.response_format`.

### Non-goals

- **Caller migration** (book-service [media.go:449](services/book-service/internal/api/media.go#L449), video-gen-service [generate.py:158](services/video-gen-service/app/routers/generate.py)). Both currently call upstream directly via http.Client — migration to SDK is Phase 5e (after 5d's video_gen lands).
- **Gateway-side URL→MinIO download**. Caller owns its storage bucket (matches chat-service voice precedent).
- **video_gen operation**. Same shape but different upstream path (`/v1/video/generations`); ship 5d separately.
- **Streaming (progressive image preview)**. The OpenAI spec is request-response; no provider implements streaming image gen via this contract.
- **Image edit / image variations** (`/v1/images/edits`, `/v1/images/variations`). Different OpenAI endpoints; defer to 5c-β if a caller needs them.
- **Image input** (image-to-image, inpainting reference image). `ImageGenInput.image` field is part of the OpenAI gpt-image-1 + ComfyUI workflow spec but not exercised by any LoreWeave caller today; punt unless 5e migration surfaces it.
- **video-gen-service deletion / `/v1/video-gen/*` route retirement.** Phase 5f.

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
    - image_gen         # already present since Phase 2b enum reservation
    - entity_extraction
    - relation_extraction
    - event_extraction
    - fact_extraction
    - translation
```

**Sync-invariant state at start of 5c-α (Fix #1 — these are NOT new in this cycle):**

| Slot | Has `image_gen`? | File |
|---|---|---|
| openapi `JobOperation` enum | ✅ since Phase 2b | [openapi.yaml](contracts/api/llm-gateway/v1/openapi.yaml) |
| migrate.go `llm_jobs.operation` CHECK constraint | ✅ since Phase 2b | [migrate.go:97-102 + ALTER:154-158](services/provider-registry-service/internal/migrate/migrate.go#L97) |
| jobs_handler.go `validJobOperations` map | ✅ since Phase 2b | [jobs_handler.go:33-34](services/provider-registry-service/internal/api/jobs_handler.go) |
| SDK `JobOperation` Literal | ✅ since Phase 4a-α | [models.py:119-125](sdks/python/loreweave_llm/models.py#L119) |
| notification-service op label map | ✅ already mapped to "Image gen" | [consumer.go:95 + consumer_test.go:104](services/notification-service/internal/consumer/consumer.go) |

**What IS new this cycle:**
- 3 schema definitions: `ImageGenInput` + `ImageGenResult` + `ImageGenDataItem`
- Worker `imageJobOperations` map entry + `processImageGenJob` dispatch
- OpenAI adapter `GenerateImage` implementation + stubs
- SDK `Client.generate_image()` + `ImageGenResult`/`ImageGenDataItem` pydantic models + 2 new error classes

No SQL migration, no enum addition, no SDK Literal addition.

New schemas:

```yaml
ImageGenInput:
  type: object
  required: [prompt]
  description: |
    Phase 5c-α. Input payload for SubmitJobRequest with operation=image_gen.
    The gateway forwards to the upstream provider's OpenAI-compatible
    /v1/images/generations endpoint. Field names + semantics mirror the
    OpenAI Image API 1:1 so any OpenAI-compatible backend (DALL-E,
    gpt-image-1, local ComfyUI services like local-image-generator-service)
    works without per-backend adapter code.
  properties:
    prompt:
      type: string
      minLength: 1
      maxLength: 32000
      description: |
        Text description of the desired image. Hard cap 32K at the gateway
        (DALL-E 3 accepts 4K; gpt-image-1 32K; local ComfyUI models often
        cap at CLIP encoder limit ≈300–500 tokens — upstream validates).
    size:
      type: string
      default: "1024x1024"
      description: |
        Image dimensions. Common: "256x256", "512x512", "1024x1024",
        "1792x1024", "1024x1792", "1536x1024", "1024x1536". Upstream
        validates supported sizes per model.
    n:
      type: integer
      minimum: 1
      maximum: 4
      default: 1
      description: |
        Number of images to generate (1..4). Gateway rejects n>4 at
        handler boundary. DALL-E-3 + gpt-image-1 only accept n=1;
        DALL-E-2 + local backends often accept n>1.
    response_format:
      type: string
      enum: [url, b64_json]
      default: url
      description: |
        How to return image bytes. `url` returns an upstream-hosted URL
        the caller must fetch (typical: ~10 min lifetime). `b64_json`
        returns the bytes inline (≈33% bandwidth bloat; convenient when
        caller doesn't want a separate fetch).
    quality:
      type: string
      enum: [standard, hd, high, medium, low]
      default: standard
      description: |
        Quality tier. Model-dependent: DALL-E-3 accepts standard/hd;
        gpt-image-1 accepts high/medium/low. Upstream validates.
    style:
      type: string
      enum: [vivid, natural]
      nullable: true
      description: DALL-E-3 only. `null` to omit.
    background:
      type: string
      enum: [auto, transparent, opaque]
      nullable: true
      description: gpt-image-1 only. `null` to omit.

ImageGenResult:
  type: object
  required: [created, data]
  description: |
    Phase 5c-α. Result payload populated in Job.result when
    operation=image_gen and status=completed.
  properties:
    created:
      type: integer
      description: Unix timestamp (seconds) when the generation finished.
    data:
      type: array
      minItems: 1
      maxItems: 4
      items:
        $ref: '#/components/schemas/ImageGenDataItem'

ImageGenDataItem:
  type: object
  description: |
    Single generated image. Exactly one of `url` or `b64_json` is
    populated based on the request's `response_format`. `revised_prompt`
    is present if the upstream model rewrote the prompt (DALL-E-3 +
    gpt-image-1 do this; local models typically don't).
  properties:
    url:
      type: string
      format: uri
      nullable: true
      description: |
        Upstream-hosted image URL. Caller is responsible for fetching
        and storing — gateway does NOT download. URL lifetime is
        upstream-dependent (OpenAI: ~1 hour; local services: caller
        configures).
    b64_json:
      type: string
      nullable: true
      description: Base64-encoded raw image bytes.
    revised_prompt:
      type: string
      nullable: true
      description: |
        If upstream rewrote the prompt (DALL-E-3 safety-rewrite +
        gpt-image-1 caption-rewrite), the rewritten text. `null`
        otherwise.
```

`SubmitJobRequest.input` description gets a new bullet pointing at `ImageGenInput`.

### 2.2 Adapter interface — new `GenerateImage` method

`services/provider-registry-service/internal/provider/adapters.go`:

```go
type Adapter interface {
    ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error)
    Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error)
    HealthCheck(ctx context.Context, endpointBaseURL, secret string) error
    Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error
    Transcribe(ctx context.Context, endpointBaseURL, secret, modelName string, input TranscribeInput) (TranscribeOutput, Usage, error)
    Speak(ctx context.Context, endpointBaseURL, secret, modelName string, input SpeakInput, emit AudioEmitFn) error

    // GenerateImage — Phase 5c-α. Text-to-image generation. POST to
    // upstream /v1/images/generations with OpenAI-compatible body;
    // parse response into GenerateImageOutput. Adapters that don't
    // support image generation return ErrOperationNotSupported.
    GenerateImage(ctx context.Context, endpointBaseURL, secret, modelName string, input GenerateImageInput) (GenerateImageOutput, Usage, error)
}
```

New types + sentinels:

```go
// GenerateImageInput holds image-gen request parameters. Field shape
// mirrors OpenAI Image API; "" / nil-pointers omit the param at the
// upstream call so we don't override upstream defaults with zero values.
type GenerateImageInput struct {
    Prompt         string  // required, max 32K (validated at handler before reaching adapter)
    Size           string  // e.g. "1024x1024"; "" → upstream default
    N              int     // 1..4 (validated at handler); 0 → 1
    ResponseFormat string  // "url" | "b64_json"; "" → "url"
    Quality        string  // "standard" | "hd" | "high" | "medium" | "low"; "" → omit
    Style          string  // "vivid" | "natural" (DALL-E-3 only); "" → omit
    Background     string  // "auto" | "transparent" | "opaque" (gpt-image-1 only); "" → omit
}

type GenerateImageOutput struct {
    Created int64
    Data    []GeneratedImage
}

type GeneratedImage struct {
    URL           string // populated when input.ResponseFormat=="url"
    B64JSON       string // populated when input.ResponseFormat=="b64_json"
    RevisedPrompt string // populated by upstream if the model rewrote the prompt
}

// ErrImageGenerationFailed — Phase 5c-α. Returned when upstream rejects
// the prompt (content-policy, model loading, unspecified backend error)
// in a way the typed upstream classifier doesn't bucket as
// rate-limit/permanent/transient. Caller maps to LLM_IMAGE_GENERATION_FAILED.
var ErrImageGenerationFailed = fmt.Errorf("image generation failed")

// ErrImageContentPolicy — Phase 5c-α. Returned specifically when
// upstream signals a content-policy rejection (DALL-E "your_request_was_rejected"
// + safety system block; OpenAI 400 with code "content_policy_violation").
// Distinct so callers can surface the right UX hint ("rephrase your
// prompt") vs the generic "generation failed" (might be retryable).
// Caller maps to LLM_IMAGE_CONTENT_POLICY_VIOLATION.
var ErrImageContentPolicy = fmt.Errorf("image generation rejected by content policy")

// ErrImageInvalidParams — Phase 5c-α /review-impl(DESIGN) MED#5. Returned
// when adapter-level invariant check rejects a caller-provided field
// (n > MaxImagesPerJob, prompt empty, etc.). Distinct from the typed
// upstream errors because the upstream was never called. Caller maps
// to LLM_INVALID_REQUEST.
var ErrImageInvalidParams = fmt.Errorf("image generation params invalid")

// MaxImagesPerJob — Phase 5c-α /review-impl(DESIGN) MED#5. Adapter-level
// upper bound on `n`. Belt-and-suspenders matching Phase 5b's MaxAudioBytes
// pattern: handler caps via validateImageGenInput, adapter caps here so
// a non-handler caller (cron, future RabbitMQ submit path, internal
// background re-run) can't bypass the validation gate. Aligns with
// the OpenAI Image API DALL-E-2 max-n=10 ceiling halved for cost-safety
// at the gateway (LoreWeave imposes 4 as a deliberate spend cap).
const MaxImagesPerJob = 4

// MaxImageResponseBytes — Phase 5c-α /review-impl(DESIGN) LOW#6. Cap on
// the upstream image response body the adapter buffers in memory.
// 8MB covers: 4 × ~1024×1024 PNG b64 (~670KB each) ≈ 2.6MB + JSON
// overhead, with comfortable margin. Larger responses → LLM_UPSTREAM_ERROR
// (we don't have a more specific code; consumers see "upstream returned
// > 8MB" message). Documented in openapi.yaml ImageGenInput.response_format
// description so callers know the limit.
const MaxImageResponseBytes = 8 * 1024 * 1024
```

### 2.3 Worker dispatch — `processImageGenJob` parallel to `processAudioJob`

`services/provider-registry-service/internal/jobs/worker_image.go` (NEW):

Mirrors `worker_audio.go` structure 1:1:

```go
// imageJobOperations is the gate for routing into processImageGenJob.
var imageJobOperations = map[string]struct{}{"image_gen": {}}

func isImageJobOperation(op string) bool { _, ok := imageJobOperations[op]; return ok }

const ImageGenJobTimeout = 10 * time.Minute  // ComfyUI backends + large models can run multi-minute

func (w *Worker) processImageGenJob(
    ctx context.Context,
    jobID, ownerUserID uuid.UUID,
    operation, modelSource string,
    modelRef uuid.UUID,
    input json.RawMessage,
    logger *slog.Logger,
) {
    // creds resolve → adapter pick → input decode → runImageGenJob
    // (same shape as processAudioJob)
}

func (w *Worker) runImageGenJob(...) {
    imgCtx, cancel := context.WithTimeout(ctx, ImageGenJobTimeout)
    defer cancel()

    in := provider.GenerateImageInput{
        Prompt:         inputMap["prompt"].(string),
        Size:           safeStr(inputMap, "size"),
        N:              safeIntDefault(inputMap, "n", 1),
        ResponseFormat: safeStrDefault(inputMap, "response_format", "url"),
        Quality:        safeStr(inputMap, "quality"),
        Style:          safeStr(inputMap, "style"),
        Background:     safeStr(inputMap, "background"),
    }
    out, _, err := adapter.GenerateImage(imgCtx, endpointBaseURL, secret, providerModelName, in)
    if err != nil {
        errCode, status := classifyImageError(imgCtx, err)
        w.finalizeAndNotify(...)
        return
    }
    result := map[string]any{
        "created": out.Created,
        "data":    marshalGeneratedImages(out.Data),
    }
    w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", "")
}

func classifyImageError(ctx context.Context, err error) (code, status string) {
    // ctx.Err() takes precedence (cancelled/timeout) — mirrors classifyAudioError
    // typed upstream errors (rate-limited / permanent 401-403 / transient 5xx)
    //   reuse the existing classifier helpers (ClassifyUpstreamHTTP returns these)
    // ErrImageInvalidParams → LLM_INVALID_REQUEST/failed  (Fix #5)
    // ErrImageContentPolicy → LLM_IMAGE_CONTENT_POLICY_VIOLATION/failed
    // ErrImageGenerationFailed → LLM_IMAGE_GENERATION_FAILED/failed
    // ErrOperationNotSupported → LLM_OPERATION_NOT_SUPPORTED/failed
    // default → LLM_UPSTREAM_ERROR/failed
}
```

Hook into `worker.go::Process` AFTER the audio dispatch (mirrors the existing audio routing):

```go
if isAudioJobOperation(operation) {
    w.processAudioJob(...)
    return
}
if isImageJobOperation(operation) {
    w.processImageGenJob(...)
    return
}
// ... existing chat/extraction/translation streamable-op path
```

### 2.4 OpenAI adapter — `openai_image.go` (NEW)

Single-file implementation. Flow:
1. Validate `Prompt != ""` (defense — handler already validates)
2. Build JSON body with non-empty/non-zero fields only (omit `style="vivid"` if upstream doesn't accept it; omit `n=0`)
3. POST to `{base}/v1/images/generations` with `Authorization: Bearer {secret}`
4. On non-2xx: classify via `ClassifyUpstreamHTTP` (existing 5a helper); inspect body for `code=="content_policy_violation"` → return `ErrImageContentPolicy`
5. On 2xx: decode `{created: int, data: [{url?, b64_json?, revised_prompt?}]}` → `GenerateImageOutput`

```go
func (a *openaiAdapter) GenerateImage(
    ctx context.Context, endpointBaseURL, secret, modelName string,
    input GenerateImageInput,
) (GenerateImageOutput, Usage, error) {
    // Phase 5b-pattern invariants: pre-checks BEFORE upstream call. The
    // handler also enforces; adapter is belt-and-suspenders for non-handler
    // callers (see ErrImageInvalidParams docstring).
    if input.Prompt == "" {
        return GenerateImageOutput{}, Usage{}, fmt.Errorf("%w: prompt required", ErrImageInvalidParams)
    }
    if input.N > MaxImagesPerJob {
        return GenerateImageOutput{}, Usage{}, fmt.Errorf(
            "%w: n=%d exceeds cap %d", ErrImageInvalidParams, input.N, MaxImagesPerJob)
    }
    if input.ResponseFormat != "" && input.ResponseFormat != "url" && input.ResponseFormat != "b64_json" {
        return GenerateImageOutput{}, Usage{}, fmt.Errorf(
            "%w: response_format=%q (allowed: url, b64_json)", ErrImageInvalidParams, input.ResponseFormat)
    }

    base := strings.TrimRight(endpointBaseURL, "/")
    if base == "" { base = openaiBaseURL }

    body := map[string]any{
        "model":  modelName,
        "prompt": input.Prompt,
    }
    if input.Size != "" { body["size"] = input.Size }
    if input.N > 0 { body["n"] = input.N }
    if input.ResponseFormat != "" { body["response_format"] = input.ResponseFormat }
    if input.Quality != "" { body["quality"] = input.Quality }
    if input.Style != "" { body["style"] = input.Style }
    if input.Background != "" { body["background"] = input.Background }

    bodyBytes, _ := json.Marshal(body)
    req, _ := http.NewRequestWithContext(ctx, http.MethodPost, base+"/v1/images/generations", bytes.NewReader(bodyBytes))
    req.Header.Set("Content-Type", "application/json")
    if secret != "" { req.Header.Set("Authorization", "Bearer "+secret) }

    resp, err := a.client.Do(req)
    if err != nil { return GenerateImageOutput{}, Usage{}, fmt.Errorf("upstream transport: %w", err) }
    defer resp.Body.Close()

    // Phase 5c-α /review-impl(DESIGN) LOW#6 — named cap (was a magic
    // 8MB literal). Multi-image b64 can be large; refuse to buffer
    // beyond the documented limit.
    respBytes, _ := io.ReadAll(io.LimitReader(resp.Body, MaxImageResponseBytes+1))
    if len(respBytes) > MaxImageResponseBytes {
        return GenerateImageOutput{}, Usage{}, fmt.Errorf(
            "%w: upstream response exceeds %d bytes", ErrImageGenerationFailed, MaxImageResponseBytes)
    }

    if resp.StatusCode < 200 || resp.StatusCode >= 300 {
        // Inspect body for content-policy code FIRST (returns the precise sentinel)
        if isContentPolicyRejection(resp.StatusCode, respBytes) {
            return GenerateImageOutput{}, Usage{}, fmt.Errorf("%w: %s", ErrImageContentPolicy, truncateBody(string(respBytes), 4096))
        }
        retryAfter := parseRetryAfter(resp.Header.Get("Retry-After"))
        return GenerateImageOutput{}, Usage{}, ClassifyUpstreamHTTP(resp.StatusCode, string(respBytes), retryAfter)
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
        return GenerateImageOutput{}, Usage{}, fmt.Errorf("decode image response: %w (body=%s)", err, truncateBody(string(respBytes), 1024))
    }
    if len(parsed.Data) == 0 {
        return GenerateImageOutput{}, Usage{}, fmt.Errorf("%w: upstream returned no images", ErrImageGenerationFailed)
    }
    out := GenerateImageOutput{Created: parsed.Created, Data: make([]GeneratedImage, len(parsed.Data))}
    for i, d := range parsed.Data {
        out.Data[i] = GeneratedImage{URL: d.URL, B64JSON: d.B64JSON, RevisedPrompt: d.RevisedPrompt}
    }
    return out, Usage{}, nil
}

// isContentPolicyRejection detects DALL-E + gpt-image-1 content-policy
// errors. OpenAI returns body `{"error": {"code": "content_policy_violation", ...}}`
// (status 400 typical; sometimes 403 or 200-with-error-field).
//
// /review-impl(DESIGN) MED#3 — JSON structure check FIRST (locks to the
// openai-compat error shape `error.code`), substring match as a fallback
// for backends that don't return JSON. Avoids a false-positive where
// the user's prompt is echoed back inside the error message (e.g.,
// "your prompt 'analyzing content_policy_violation in poetry' was
// rejected for X") — JSON path catches the structural signal first.
func isContentPolicyRejection(status int, body []byte) bool {
    // JSON-first: parse error.code and check directly.
    var parsed struct {
        Error struct {
            Code string `json:"code"`
            Type string `json:"type"`
        } `json:"error"`
    }
    if err := json.Unmarshal(body, &parsed); err == nil {
        if parsed.Error.Code == "content_policy_violation" ||
            parsed.Error.Code == "moderation_blocked" ||
            parsed.Error.Type == "image_generation_user_error" {
            return true
        }
        // JSON parsed successfully but no policy marker — NOT a policy
        // rejection. Don't fall through to substring (the parsed JSON
        // is authoritative).
        return false
    }
    // JSON parse failed → non-JSON body (HTML error page, plain text).
    // Substring fallback only when status is 400/403 (high signal).
    if status != 400 && status != 403 {
        return false
    }
    return bytes.Contains(body, []byte("content_policy_violation")) ||
        bytes.Contains(body, []byte("safety_system"))
}
```

### 2.5 Other adapters — stubs

`services/provider-registry-service/internal/provider/adapters_image.go` (NEW):

```go
func (a *anthropicAdapter) GenerateImage(ctx context.Context, _, _, _ string, _ GenerateImageInput) (GenerateImageOutput, Usage, error) {
    return GenerateImageOutput{}, Usage{}, ErrOperationNotSupported
}
func (a *ollamaAdapter) GenerateImage(ctx context.Context, _, _, _ string, _ GenerateImageInput) (GenerateImageOutput, Usage, error) {
    return GenerateImageOutput{}, Usage{}, ErrOperationNotSupported
}
func (a *lmStudioAdapter) GenerateImage(ctx context.Context, _, _, _ string, _ GenerateImageInput) (GenerateImageOutput, Usage, error) {
    return GenerateImageOutput{}, Usage{}, ErrOperationNotSupported
}
```

(Anthropic has no image-gen API; Ollama doesn't expose one through OpenAI-compat; LM Studio's image support is per-model GUI-only and not exposed via API.)

### 2.6 Handler — handler-level validation for image_gen

`services/provider-registry-service/internal/api/jobs_handler.go`:

Reuse the JSON path (no new multipart entrypoint — image_gen input is small JSON, not bytes-heavy). Add handler-level validation for the image-specific fields before insert so caller gets fast feedback:

```go
// AFTER the standard validation block (operation/model_source/model_ref/input)
if in.Operation == "image_gen" {
    if err := validateImageGenInput(in.Input); err != nil {
        writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", err.Error())
        return
    }
}

// New function in the same file:
func validateImageGenInput(raw json.RawMessage) error {
    var v struct {
        Prompt         string `json:"prompt"`
        N              int    `json:"n"`
        ResponseFormat string `json:"response_format"`
    }
    if err := json.Unmarshal(raw, &v); err != nil {
        return fmt.Errorf("image_gen input parse: %w", err)
    }
    if strings.TrimSpace(v.Prompt) == "" {
        return fmt.Errorf("image_gen requires non-empty prompt")
    }
    if len(v.Prompt) > 32000 {
        return fmt.Errorf("image_gen prompt exceeds 32000-char cap (got %d)", len(v.Prompt))
    }
    if v.N != 0 && (v.N < 1 || v.N > 4) {
        return fmt.Errorf("image_gen n must be 1..4 (got %d)", v.N)
    }
    if v.ResponseFormat != "" && v.ResponseFormat != "url" && v.ResponseFormat != "b64_json" {
        return fmt.Errorf("image_gen response_format must be url or b64_json (got %q)", v.ResponseFormat)
    }
    return nil
}
```

### 2.7 SDK Python — `Client.generate_image()`

`sdks/python/loreweave_llm/client.py`:

```python
async def generate_image(
    self,
    prompt: str,
    *,
    model_source: ModelSource,
    model_ref: str,
    size: str | None = None,
    n: int = 1,
    response_format: Literal["url", "b64_json"] = "url",
    quality: str | None = None,
    style: Literal["vivid", "natural"] | None = None,
    background: Literal["auto", "transparent", "opaque"] | None = None,
    user_id: str | None = None,
    poll_interval_s: float = 0.5,
    max_poll_interval_s: float = 10.0,
) -> ImageGenResult:
    """Phase 5c-α — submit image-gen job, wait for terminal, return decoded result.

    Reuses submit_job + wait_terminal (same backoff, same cancellation,
    same transient-retry semantics as transcribe()). transient_retry_budget
    is fixed at 0 — image gen is expensive (real $ + GPU minutes); a silent
    re-run on transient failure could double-charge BYOK.

    Raises:
      - LLMInvalidRequest on malformed model_ref or empty prompt
      - LLMImageContentPolicy when upstream rejects the prompt by safety
        rules (caller's UX should suggest rephrasing)
      - LLMError subclass keyed by job.error.code on other failures
      - LLMJobTerminal on status=cancelled

    `user_id` per-call override (mirrors submit_job).
    """
    # UUID validation, build SubmitJobRequest, submit, wait_terminal,
    # decode result into ImageGenResult.
```

New SDK models:

```python
# sdks/python/loreweave_llm/models.py
class ImageGenDataItem(BaseModel):
    url: str | None = None
    b64_json: str | None = None
    revised_prompt: str | None = None

class ImageGenResult(BaseModel):
    created: int
    data: list[ImageGenDataItem] = Field(min_length=1, max_length=4)
```

New SDK error:

```python
# sdks/python/loreweave_llm/errors.py
class LLMImageContentPolicy(LLMError):
    """Upstream rejected the prompt by content-policy / safety rules.
    Distinct from generic LLMUpstreamError so caller's UX can surface
    a "rephrase your prompt" hint rather than a "try again" retry.
    Maps from gateway code: LLM_IMAGE_CONTENT_POLICY_VIOLATION.
    """
    code = "LLM_IMAGE_CONTENT_POLICY_VIOLATION"

class LLMImageGenerationFailed(LLMError):
    """Upstream image generation failed for a non-content-policy reason
    (model loading, backend timeout, ambiguous failure). Caller MAY retry
    once; persistent failures suggest a backend issue.
    Maps from gateway code: LLM_IMAGE_GENERATION_FAILED.
    """
    code = "LLM_IMAGE_GENERATION_FAILED"
```

Register in `_CODE_TO_EXC` + export from `__init__.py`.

---

## 3. Architecture & data flow

### 3.1 Sequence — image_gen submit (chat-service is not the caller; this is the future caller pattern)

```
Caller                    gateway                  Upstream (e.g., OpenAI / local-image-generator-service:8700)
  │                          │                          │
  │ POST /v1/llm/jobs        │                          │
  │ {operation:image_gen,    │                          │
  │  model_source,model_ref, │                          │
  │  input:{prompt, size,    │                          │
  │         n, response_     │                          │
  │         format}}         │                          │
  │─────────────────────────▶│                          │
  │                          │ validate input           │
  │                          │ insert llm_jobs row      │
  │ 202 {job_id}             │                          │
  │◀─────────────────────────│                          │
  │                          │                          │
  │                          │ goroutine:               │
  │                          │   resolve creds          │
  │                          │   adapter.GenerateImage  │
  │                          │   POST /v1/images/       │
  │                          │   generations            │
  │                          │─────────────────────────▶│
  │ poll GET /jobs/{id}      │                          │
  │─────────────────────────▶│ status=running           │
  │                          │   {created, data: [...]} │
  │                          │◀─────────────────────────│
  │                          │ finalize completed       │
  │                          │ + result populated       │
  │                          │                          │
  │ poll GET /jobs/{id}      │                          │
  │─────────────────────────▶│                          │
  │ {status:completed,       │                          │
  │  result:{created, data:  │                          │
  │  [{url, ...}]}}          │                          │
  │◀─────────────────────────│                          │
  │                          │                          │
  │ Caller fetches data[0].url, downloads, stores       │
  │ in its own MinIO bucket (5e — book-service, etc.)   │
```

Caller-side download note: image URLs typically have short lifetimes (OpenAI: 1 hour). Caller MUST download immediately after polling completed; persistent storage of the upstream URL is unsafe. Local providers may have different lifetimes; caller should never assume.

### 3.2 No streaming, no chunking

Unlike chat/extraction (chunked) and TTS (streamed audio frames), image_gen is a single request-response. The job lifecycle has a single state transition (pending → running → completed/failed). No `chunking` config; the handler rejects `chunking != null` for image_gen with `LLM_INVALID_REQUEST: "chunking not supported for image_gen"`.

### 3.3 Backward-compat

`JobOperation.image_gen` was already in the enum (Phase 2b reservation). Before this cycle: worker dispatch returned `LLM_OPERATION_NOT_SUPPORTED` for the op. After: routes to `processImageGenJob`. No existing caller is affected.

---

## 4. Tests

### 4.1 Adapter tests (`adapters_image_test.go` — NEW)

5 cases:
- `TestOpenAIAdapter_GenerateImage_HappyPath` — POST + body shape + decode `data[0].url`
- `TestOpenAIAdapter_GenerateImage_MultiImage_N2` — n=2, decode 2 data items
- `TestOpenAIAdapter_GenerateImage_Base64Response` — response_format=b64_json
- `TestOpenAIAdapter_GenerateImage_ContentPolicyRejection` — upstream 400 with content_policy_violation → ErrImageContentPolicy
- `TestOpenAIAdapter_GenerateImage_RevisedPrompt` — DALL-E-3 returns revised_prompt; decoded into GeneratedImage

3 stub-lock tests (`adapters_image_stub_test.go` — or fold into existing `adapters_audio_test.go` table):
- Anthropic/Ollama/LM Studio GenerateImage → ErrOperationNotSupported

### 4.2 Worker tests (`worker_image_test.go` — NEW)

Parallel to `worker_audio_test.go`:
- `TestIsImageJobOperation_Whitelist` — pin the gate
- `TestClassifyImageError_ContentPolicy` — `ErrImageContentPolicy` → `LLM_IMAGE_CONTENT_POLICY_VIOLATION/failed`
- `TestClassifyImageError_GenerationFailed` — `ErrImageGenerationFailed` → `LLM_IMAGE_GENERATION_FAILED/failed`
- `TestClassifyImageError_InvalidParams` — `ErrImageInvalidParams` → `LLM_INVALID_REQUEST/failed` (Fix #5)
- `TestClassifyImageError_Cancelled` / `TestClassifyImageError_DeadlineExceeded` — ctx state precedence
- `TestClassifyImageError_RateLimitedTyped` / `_AuthFailedFrom401` / `_Permanent400IsUpstreamError` / `_Transient5xx` — typed upstream classification (reuse Phase 5a helpers)
- `TestImageJobOperations_AlsoInValidJobOperations` — image_gen is in `validJobOperations` map + migrate.go CHECK + openapi enum (5-place sync invariant grep, mirrors `TestAudioJobOperations_AlsoInValidJobOperations` from Phase 5a; all 4 non-SDK slots are already populated per §2.1 — this test pins they stay populated, not that we add them)
- `TestImageJobOperations_Disjoint` (Fix #2) — `imageJobOperations ∩ streamableOperations = ∅` AND `imageJobOperations ∩ audioJobOperations = ∅`. Mirrors Phase 5a's `TestStreamableAudio_Disjoint`. Catches dispatch-ambiguity regressions where someone adds `image_gen` to the wrong map.
- `TestIsStreamableOperation_RejectsNonStreamable[image_gen]` (Fix #7) — existing test in [worker_test.go:41-58](services/provider-registry-service/internal/jobs/worker_test.go#L41) already covers this; this cycle UPDATES the comment block (line 44 "These ops exist in openapi.JobOperation but don't go through the chat-streaming machinery — they need their own adapters") to reflect 5c-α reality ("ops with non-chat-streaming dispatch — audio + image route via their own whitelist maps in worker.go ordering"). No new test.

### 4.3 Handler tests (`jobs_router_test.go` — NEW cases)

Mirror Phase 5b's multipart test additions:
- `TestInternalSubmitLlmJob_ImageGen_HappyPathAccepted` — well-formed image_gen submission progresses past validation to 503 (router-only server)
- `TestInternalSubmitLlmJob_ImageGen_RejectsEmptyPrompt` — `prompt: ""` → 400 LLM_INVALID_REQUEST
- `TestInternalSubmitLlmJob_ImageGen_RejectsOversizePrompt` — `len(prompt) > 32000` → 400
- `TestInternalSubmitLlmJob_ImageGen_RejectsNOutOfRange` — `n: 5` → 400 ("n must be 1..4")
- `TestInternalSubmitLlmJob_ImageGen_RejectsBadResponseFormat` — `response_format: "jpeg"` → 400
- `TestInternalSubmitLlmJob_ImageGen_RejectsChunkingField` — image_gen with chunking config → 400 ("chunking not supported for image_gen")

### 4.4 SDK tests (`test_image_gen.py` — NEW)

5 cases:
- `test_generate_image_happy_path` — submit → poll completed → ImageGenResult parsed (url mode)
- `test_generate_image_b64_response` — response_format=b64_json → b64_json populated
- `test_generate_image_multi_n` — n=2 → 2 data items
- `test_generate_image_content_policy_raises_llmimagecontentpolicy` — gateway returns failed/LLM_IMAGE_CONTENT_POLICY_VIOLATION → LLMImageContentPolicy raised
- `test_generate_image_rejects_malformed_model_ref_before_wire` — UUID-shape validation

1 regression-lock (parallel to Phase 5b's audio-errors test):
- `test_image_errors_have_specific_classes_regression_lock` — `from_code("LLM_IMAGE_CONTENT_POLICY_VIOLATION", ...) is LLMImageContentPolicy`; same for `LLM_IMAGE_GENERATION_FAILED`.

---

## 5. Build plan (PLAN phase)

| # | Task | Files | Size |
|---|------|-------|------|
| T1 | OpenAPI: `image_gen` already in JobOperation enum (Fix #1 — no enum edit); add `ImageGenInput` + `ImageGenResult` + `ImageGenDataItem` schemas; SubmitJobRequest.input description bullet; document MaxImageResponseBytes 8MB cap in ImageGenInput.response_format description (Fix #6) | `contracts/api/llm-gateway/v1/openapi.yaml` | XS |
| T2 | Adapter types: `GenerateImageInput` + `GenerateImageOutput` + `GeneratedImage`; sentinels `ErrImageGenerationFailed` + `ErrImageContentPolicy` + **`ErrImageInvalidParams`** (Fix #5); constants **`MaxImagesPerJob=4`** (Fix #5) + **`MaxImageResponseBytes=8*1024*1024`** (Fix #6); Adapter interface +GenerateImage | `services/provider-registry-service/internal/provider/adapters.go` | S |
| T3 | OpenAI adapter: `openai_image.go` NEW with GenerateImage implementation including adapter-level pre-checks (Prompt empty + N>MaxImagesPerJob + bad response_format → ErrImageInvalidParams per Fix #5) + JSON-first `isContentPolicyRejection` helper (Fix #3) + MaxImageResponseBytes cap (Fix #6) | `services/provider-registry-service/internal/provider/openai_image.go` (NEW) | M |
| T4 | Adapter stubs: `adapters_image.go` NEW with Anthropic/Ollama/LM Studio stubs | `services/provider-registry-service/internal/provider/adapters_image.go` (NEW) | XS |
| T5 | Adapter tests: 6 OpenAI cases (happy + multi-image n=2 + b64 + content-policy via JSON `error.code` + revised_prompt + oversize→ErrImageGenerationFailed) + **3 invariant cases (N>4 + N<0 + bad-response_format → ErrImageInvalidParams** per Fix #5) + 3 stub locks; **content-policy JSON-first vs substring fallback test** (Fix #3 — verifies the prompt-echo-in-body false-positive is mitigated) | `services/provider-registry-service/internal/provider/adapters_image_test.go` (NEW) | M |
| T6 | Worker: `worker_image.go` NEW with `processImageGenJob` + `runImageGenJob` + `classifyImageError` (incl. ErrImageInvalidParams → LLM_INVALID_REQUEST per Fix #5) + `imageJobOperations` whitelist + `ImageGenJobTimeout=10min` const | `services/provider-registry-service/internal/jobs/worker_image.go` (NEW) | S |
| T7 | Worker dispatch hook in `worker.go::Process` — route to processImageGenJob when isImageJobOperation(op); UPDATE the inline comment at worker.go:158-165 ("Embedding/translation/image_gen") + worker_test.go:42-44 comment to reflect image_gen now has dedicated dispatch (Fix #7) | `services/provider-registry-service/internal/jobs/worker.go` + `services/provider-registry-service/internal/jobs/worker_test.go` | XS |
| T8 | Worker tests: classify image errors (5 cases: content_policy / generation_failed / invalid_params / cancelled / deadline) + classify typed-upstream-error reuse (4 cases) + **`TestImageJobOperations_AlsoInValidJobOperations`** (5-place sync grep) + **`TestImageJobOperations_Disjoint`** (Fix #2 — disjoint vs streamable + audio) | `services/provider-registry-service/internal/jobs/worker_image_test.go` (NEW) | S |
| T9 | Handler: `validateImageGenInput` + dispatch on operation=image_gen + chunking-not-supported-for-image_gen rejection + n cap 1..4 (handler-side; adapter also caps per Fix #5) + response_format url\|b64_json validation | `services/provider-registry-service/internal/api/jobs_handler.go` | S |
| T10 | Handler tests: 6 cases (happy + empty-prompt + oversize-prompt + n-out-of-range + bad-response_format + chunking-rejected) | `services/provider-registry-service/internal/api/jobs_router_test.go` | S |
| T11 | SDK: `Client.generate_image()` method; `ImageGenResult` + `ImageGenDataItem` pydantic models (NEW — no prior partial model exists, per Fix #11); `LLMImageContentPolicy` + `LLMImageGenerationFailed` error classes + `_CODE_TO_EXC` mapping + __init__ exports | `sdks/python/loreweave_llm/client.py` + `models.py` + `errors.py` + `__init__.py` | M |
| T12 | SDK tests: 5 happy/edge + 1 regression-lock for new error classes (parallel to Phase 5b's `test_audio_errors_have_specific_classes_regression_lock`) | `sdks/python/tests/test_image_gen.py` (NEW) | S |
| T13 | Doc updates: `LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` Phase 5c-α row ✅; design doc status flip; SESSION_PATCH inline at commit time. **NOTE**: cross-repo sync to `G:\Works\local-image-generator-service\docs\EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md:651` (caller-side download vs guide's "LoreWeave downloads") is OUT OF SCOPE — tracked as `D-PHASE5C-INTEGRATION-GUIDE-SYNC` (Fix #4). | `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` + this design doc | XS |

Total: ~13 files (including 4 NEW: `openai_image.go`, `adapters_image.go`, `worker_image.go`, plus 2 NEW test files `adapters_image_test.go` + `worker_image_test.go` + `test_image_gen.py`). Build order: T1→T5 (gateway adapter foundation), T6→T8 (worker), T9→T10 (handler), T11→T12 (SDK), T13 (docs).

---

## 6. Open questions / risks

| # | Question | Answer / mitigation |
|---|---|---|
| Q1 | Image bytes can be large (4 × 1024×1024 PNG b64 = ≈2.6MB). Are we storing those in `llm_jobs.result` JSONB? | YES — for `response_format=b64_json`, the entire bytes payload lives in the DB row. Postgres TOAST handles up to 1GB row size, but ≈3MB per row × N concurrent jobs is real bloat. **Mitigation**: document that `b64_json` is for small / few-image use; advise callers to use `url` for large multi-image flows. Adapter-level cap is `MaxImageResponseBytes=8MB` (Fix #6); openapi schema description mentions the limit. Add a metric `llm_image_gen_result_size_bytes` to surface DB growth — deferred as `D-PHASE5C-RESULT-SIZE-METRIC`. |
| Q2 | URL lifetime varies by upstream (OpenAI ~1hr; local-image-generator-service caller-configured). Should the gateway include URL expiry in the result? | NO this cycle. OpenAI doesn't return expiry; we'd have to per-provider-kind it. Defer to a follow-up when a caller surfaces a real bug due to stale URLs. |
| Q3 | DALL-E-3 model rewriting prompts — should we surface that as a separate UX hint? | Already included in result schema via `revised_prompt`. Caller's responsibility to display "your prompt was revised to: X" if desired. |
| Q4 | What if upstream `local-image-generator-service` is unreachable (compose down, network partition)? | adapter.GenerateImage returns transport error → `ClassifyUpstreamHTTP` → typed transient → `classifyImageError` → `LLM_UPSTREAM_ERROR/failed`. Caller can retry. No new error class needed. |
| Q5 | Content-policy detection heuristic — what if a non-OpenAI backend uses a different error shape? | The `isContentPolicyRejection` body substring check matches `content_policy_violation` / `safety_system`. local-image-generator-service uses OpenAI-compat error bodies. Other backends (if they reject prompts) fall through to `LLM_UPSTREAM_ERROR` — acceptable degradation. Mark for future hardening if a non-OpenAI backend surfaces a different shape. |
| Q6 | The 10-minute `ImageGenJobTimeout` — is that too generous? | Multi-step ComfyUI workflows on local-image-generator-service can take 5+ min for high-res Flux. 10 min gives headroom without indefinitely pinning. Tunable later via config field if telemetry surfaces a problem. |
| Q7 | Should we wire image-gen to api-gateway-bff `/v1/video-gen/*` for FE access in this cycle? | NO. That's Phase 5e (FE migration). 5c-α ships the gateway internals only; integration tests use `/internal/llm/jobs` directly. |
| Q8 | The canonical integration guide at `G:\Works\local-image-generator-service\docs\EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md:651` says "LoreWeave downloads the image from `url` and stores it in MinIO" — our design contradicts (caller-side download). Drift between guide and design. | **Accept-and-document** as deferred item `D-PHASE5C-INTEGRATION-GUIDE-SYNC` (Fix #4). Cross-repo PR is out of 5c-α scope; flag for the next-time-we-touch-that-repo opportunity. LoreWeave-side guide (if/when it diverges) is updated in T13 of this cycle. |
| Q9 | `GenerateImageInput.Quality`/`Style`/`Background` use empty-string-omit (not nullable pointers) — caller can't explicitly send `quality=""` to override an upstream default. | (Fix #8) Not a real problem for any current openai-compat backend (they treat omit and empty equivalently). If a future backend distinguishes, switch to `*string` then. Deferred as `D-PHASE5C-NULLABLE-IMAGE-FIELDS`. |
| Q10 | Async-only locks the contract; some FE callers may want sync request-response. | (Fix #9) Async submit→poll fits all known callers (book-service does sync today via direct http, but the polling pattern is fine for its block-editor flow). If a real sync use case surfaces, add `POST /v1/llm/jobs/sync` as a separate facade. Deferred as `D-PHASE5C-SYNC-IMAGE-GEN`. |
| Q11 | Adapter pre-check ordering collapses multi-error reports to first-fail (caller gets 3 round-trips to fix 3 bad fields). | (/review-impl(BUILD) LOW#3) Accept-and-document. Standard first-fail behavior; only matters if a user surfaces real pain. Deferred as `D-PHASE5C-MULTI-ERROR-COLLECT`. |
| Q12 | 5-place sync test greps source files, not live DB state. A future cycle could remove the CHECK constraint at runtime and the test would still pass. | (/review-impl(BUILD) LOW#5) Same limitation applies to Phase 5a's audio test + Phase 4a-β's streamable test. Accept-and-document; fix the pattern across all three sibling tests in a future cycle. Deferred as `D-PHASE5C-LIVE-DB-CONSTRAINT-CHECK`. |

---

## 7. Acceptance criteria (QC phase)

- [ ] `go build ./...` clean
- [ ] `go vet ./...` clean
- [ ] `go test -count=1 ./...` ALL GREEN; delta +~13 tests (5 adapter + 1 worker-whitelist + ≈4 worker-classify + 6 handler)
- [ ] `pytest sdks/python/tests/` 174 + 6 = 180 passed (5 new + 1 regression-lock)
- [ ] OpenAPI schema validates (`spec.expanded` lint or equivalent)
- [ ] `/review-impl` on design doc returns no HIGH-severity findings
- [ ] `/review-impl` on post-BUILD code returns no HIGH findings; MEDs fixed inline before commit
- [ ] LIVE smoke (deferred to 5c-α-followup if not run in QC). Tracking item: `D-PHASE5C-LIVE-SMOKE` (Fix #10).

**Concrete live-smoke procedure (Fix #10):**

```bash
# 1. Start local-image-generator-service (sibling repo, NVIDIA Container Toolkit required)
cd G:/Works/local-image-generator-service
docker compose up -d
curl http://127.0.0.1:8700/health
# → {"status":"ok"}

# 2. Register the provider credential in LoreWeave (via FE Voice/Models Settings or directly):
#    provider_kind=openai (or local_image_gen if a dedicated kind exists)
#    endpoint_base_url=http://host.docker.internal:8700  (from provider-registry's POV)
#    api_key=<FIRST entry from G:/.../local-image-generator-service/.env API_KEYS>
#    Register user_model with provider_model_name=noobai-xl-v1.1
#
# NOTE (/review-impl(BUILD) LOW#4): `host.docker.internal` auto-resolves
# on Docker Desktop (Mac/Win) only. On native Linux Docker, add this to
# infra/docker-compose.yml under provider-registry-service:
#     extra_hosts:
#       - "host.docker.internal:host-gateway"
# Or use the actual host IP. LoreWeave's compose targets Docker Desktop
# by default, so this is a contributor-on-Linux-only concern.

# 3. Submit image_gen via internal endpoint (replace UUIDs):
curl -X POST "http://localhost:8085/internal/llm/jobs?user_id=<USER_UUID>" \
  -H "X-Internal-Token: $INTERNAL_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "image_gen",
    "model_source": "user_model",
    "model_ref": "<USER_MODEL_UUID>",
    "input": {
      "prompt": "cinematic landscape at golden hour, volumetric light",
      "size": "1024x1024",
      "n": 1,
      "response_format": "url"
    }
  }'
# Returns 202 {"job_id": "...", "status": "pending"}

# 4. Poll the job:
JOB_ID=<from above>
curl -X GET "http://localhost:8085/internal/llm/jobs/$JOB_ID?user_id=<USER_UUID>" \
  -H "X-Internal-Token: $INTERNAL_SERVICE_TOKEN"
# Repeat until status=completed. Result.data[0].url should be fetchable:
curl -I <data[0].url>
# → HTTP/1.1 200 OK, Content-Type: image/png
```

**Success signals:**
- 202 returned immediately on submit
- `provider-registry-service` logs show `processImageGenJob` invocation
- Job moves pending → running → completed
- `data[0].url` returns a real PNG (≥10KB body)

**Failure signals to debug:**
- 400 `LLM_INVALID_REQUEST` → validation gap (recheck `validateImageGenInput`)
- 404 `LLM_MODEL_NOT_FOUND` → user_model lookup or provider_kind mismatch
- 502 `LLM_UPSTREAM_ERROR` → local-image-generator-service unreachable (network) or returning non-200 (check its logs)
- 400 `LLM_IMAGE_CONTENT_POLICY_VIOLATION` → policy heuristic fired (likely OK for harmless prompts on local backend — local-image-generator-service may not implement policy at all, so this status would be unexpected)

---

## 8. Phase 5d/5e/5f preview (Path B sequencing)

- **5d** — `video_gen` adapter + SDK + openapi. Same shape as 5c-α but POSTs to `/v1/video/generations`. Async pattern identical. Likely L (smaller because content-policy detection / multi-image are not concerns for video).
- **5e** — caller migration. book-service [media.go:449](services/book-service/internal/api/media.go#L449) (Go — needs Go SDK or thin shim); video-gen-service [generate.py:158](services/video-gen-service/app/routers/generate.py) (Python — uses Python SDK). Likely XL.
- **5f** — video-gen-service deletion. Remove `services/video-gen-service/` + compose entry + api-gateway-bff `/v1/video-gen/*` routes. FE switches to calling unified gateway via SDK or BFF facade. Likely M (mostly delete + small FE PR).

By 5f close, the unified gateway invariant covers chat (4a) + extraction (4a-β) + translation (4c) + audio STT/TTS (5a) + image_gen (5c-α) + video_gen (5d). All external generation flows through `POST /v1/llm/jobs` (or `/v1/llm/stream` for streaming).
