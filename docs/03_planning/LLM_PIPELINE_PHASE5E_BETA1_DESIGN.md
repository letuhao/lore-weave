# Phase 5e-β.1 — Go SDK + book-service media.go migration onto unified gateway

> **Status:** DESIGN (post-/review-impl; 6 HIGH + 5 MED + 6 LOW + 3 COSMETIC findings folded inline)
> **Cycle:** Phase 5e-β.1 (cycle 2 of session 56)
> **Predecessor:** [Phase 5e-α](LLM_PIPELINE_PHASE5E_ALPHA_DESIGN.md) — video-gen-service (Python) migration shipped at commit `d276d0a7`
> **Successor:** Phase 5e-β.2 — gateway audio_gen adapter + Python SDK `generate_audio()` + extend Go SDK + migrate `book-service/internal/api/audio.go`

## 1. Goals

1. Ship a **Go SDK** at `sdks/go/llmgw/` (package `llmgw`) that exposes the unified gateway's job-submit-and-poll API to Go callers, modeling its surface on the Python SDK's `generate_image()` (Phase 5c-α).
2. Migrate **`book-service::generateChapterMedia`** ([media.go:351](../../services/book-service/internal/api/media.go#L351)) from the legacy direct-httpx pattern (`/internal/credentials` → direct provider `/v1/images/generations`) to use the new Go SDK's `Client.GenerateImage()` via the unified gateway.
3. Add **first-ever SDK-mock-level tests** for `generateChapterMedia` covering the typed-error → HTTP-status routing. **Full integration tests (DB + MinIO + httptest)** are explicitly DEFERRED — book-service has no existing handler test harness; building one is out-of-scope for 5e-β.1.
4. Keep `services/book-service/internal/api/audio.go` UNCHANGED — audio uses `/internal/credentials` + direct `/v1/audio/speech` and the gateway does not yet have an `audio_gen` adapter. Audio migration is deferred to Phase 5e-β.2.

## 2. Why this cycle exists

- **Path B step 4** of the LLM-pipeline unification: 5c-α + 5d shipped gateway adapters (image_gen, video_gen); 5e-α migrated video-gen-service (Python caller); this migrates book-service (FIRST Go caller).
- After 5e-β.2 (audio) + 5f (video-gen-service BFF deletion), the unified-gateway invariant is fully realized for ALL external LLM/audio/image/video calls in the platform.
- Without a Go SDK, every future Go caller (post-Phase-5f: notification-service if it ever generates content, future workflow agents) would repeat the same HTTP plumbing book-service has today — sunk cost.

## 3. Plan-line correction

[`LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md`](LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md) line 34 currently classifies book-service as having "No LLM calls". This is **stale** — the plan was written before `media.go::generateChapterMedia` and `audio.go::generateAudio` were added to the service. The plan row will be corrected as part of this cycle.

## 4. Migration surface

### 4.1 In-scope (this cycle)

| File | Action | Why |
|---|---|---|
| `sdks/go/llmgw/` | NEW package | First-ever Go SDK; greenfield |
| `services/book-service/internal/api/media.go` | MOD `generateChapterMedia` | Replace credential-resolve + direct-POST with SDK |
| `services/book-service/internal/api/server.go` | MOD | Add `llmgw *llmgw.Client` field; construct inside `NewServer` (panic-on-misconfig, mirrors `s.minio` precedent) |
| `services/book-service/internal/config/config.go` | MOD | Add `LLMGatewayInternalURL` (required env) |
| `services/book-service/go.mod` | MOD | Add SDK via `replace` directive |
| `services/book-service/Dockerfile` | MOD | **(HIGH#2)** Bump COPY paths for repo-root build context; same shape as Phase 5e-α |
| `infra/docker-compose.yml` | MOD | book-service `build.context: ..` + `build.dockerfile: services/book-service/Dockerfile` + add `LLM_GATEWAY_INTERNAL_URL` env |
| `services/book-service/internal/api/media_test.go` | NEW | Typed-error-routing tests via SDK mock (no DB; no MinIO) |
| Grep-locks | NEW (folded into `media_test.go` per CO#3) | Negative-path: legacy URLs absent |

### 4.2 Explicitly out-of-scope

- `audio.go::generateAudio` — still uses `/internal/credentials` + direct `/v1/audio/speech` upstream. Stays unchanged. Deferred to Phase 5e-β.2.
- `services/book-service/internal/config/config.go::ProviderRegistryURL` field — **kept** because audio.go still needs it. Removal deferred to 5e-β.2.
- **Full integration tests** (DB-backed handler tests for `generateChapterMedia`) — book-service has NO existing handler test harness; building Postgres + MinIO + JWT-issuer + ownership-row fixtures is its own project. Deferred to a Track-2 follow-up `D-PHASE5E-BETA1-INTEGRATION-TEST-HARNESS`.

## 5. Go SDK (`sdks/go/llmgw/`)

### 5.1 Naming (resolved — HIGH-adjacent decisions Q5.1.A + LOW#2 closed)

- **Filesystem path:** `sdks/go/llmgw/` (matches Python SDK's `sdks/python/loreweave_llm/` only in being under `sdks/`; the leaf name is Go-idiomatic)
- **Module path:** `github.com/loreweave/llmgw`
- **Package identifier:** `llmgw` (no underscores, no dashes; passes `staticcheck ST1003`)
- **Import idiom:** `import "github.com/loreweave/llmgw"` → usage `llmgw.NewClient(...)`, `llmgw.GenerateImage(...)`, `llmgw.ErrImageContentPolicy`

Rationale: cross-language symmetry with Python SDK is less important than Go-team-readability for the lifetime of the SDK. `llmgw` is short, descriptive (LLM Gateway), and matches Go conventions like `pgx`, `chi`, `uuid`. The Python SDK identifier `loreweave_llm` is forced by Python's flat-import namespace; Go's module-path system makes the package name independent.

### 5.2 Package layout

```
sdks/go/llmgw/
├── go.mod              # module github.com/loreweave/llmgw
├── doc.go              # package overview comment
├── client.go           # Client struct + NewClient + lifecycle + GenerateImage
├── transport.go        # submitJob / getJob / cancelJob / waitTerminal / raiseHTTPError
├── models.go           # request/response types + enums (string consts)
├── errors.go           # *Error + sentinel codes + newErrorFromCode helper
├── client_test.go      # GenerateImage end-to-end via httptest.NewServer
├── transport_test.go   # submitJob / getJob / waitTerminal / cancelJob individually
├── errors_test.go      # code→sentinel mapping + errors.Is contract + inner-population regression-lock
└── README.md           # quick-start with image_gen example
```

### 5.3 Public API

```go
package llmgw

// Options for NewClient. Mirrors Python SDK's Client.__init__ kwargs.
type Options struct {
    BaseURL       string             // e.g. "http://provider-registry-service:8085"
    AuthMode      AuthMode           // AuthJWT or AuthInternal
    BearerToken   string             // required when AuthMode=AuthJWT
    InternalToken string             // required when AuthMode=AuthInternal
    UserID        string             // optional; required per-call when AuthMode=AuthInternal and ctor UserID is empty
    Transport     http.RoundTripper  // (HIGH#5) optional; default http.DefaultTransport. SDK NEVER exposes *http.Client; whole-request Timeout traps polling
}

type AuthMode string

const (
    AuthJWT      AuthMode = "jwt"
    AuthInternal AuthMode = "internal"
)

type Client struct {
    // ... unexported fields, including http *http.Client (no Timeout)
}

func NewClient(opts Options) (*Client, error)

// GenerateImage submits an image_gen job, polls until terminal, returns the
// decoded result. Polling has exponential backoff (0.5s → 10s, ×1.5).
// transientRetryBudget is fixed at 0 — image generation is expensive
// ($GPU minutes); a silent re-run on transient failure could double-charge BYOK.
//
// Cancellation is via ctx. Polling sleeps select on ctx.Done().
//
// All wall-clock cancellation is the caller's responsibility via ctx.
// The SDK's internal *http.Client has NO Timeout set; per-request
// timeouts must be applied at the ctx level by the caller.
func (c *Client) GenerateImage(ctx context.Context, req GenerateImageRequest) (*ImageGenResult, error)

// (5e-β.2 will add GenerateAudio with the same shape.)
```

**HIGH#5 fix — `Transport` only, not `*http.Client`:** Accepting a full `*http.Client` lets the user set `Timeout` which then caps **each polling request** (a trap because they likely expect "overall timeout"). By accepting only `http.RoundTripper`, the SDK builds `&http.Client{Transport: t}` internally with no Timeout. Cancellation is exclusively via `context.Context`.

```go
// models.go — request / response types
type ModelSource string

const (
    ModelSourceUser     ModelSource = "user_model"
    ModelSourcePlatform ModelSource = "platform_model"
)

type GenerateImageRequest struct {
    Prompt          string         // required, non-empty
    ModelSource     ModelSource    // required
    ModelRef        string         // required, UUID-shaped (validated at SDK boundary)
    Size            *string        // pointer ⇒ nil means "omit; let gateway/upstream default decide"
    N               *int           // pointer ⇒ nil means "omit"
    ResponseFormat  *string        // "url" | "b64_json"; nil ⇒ omit (gateway default "url")
    Quality         *string
    Style           *string        // "vivid" | "natural" (DALL-E-3 only)
    Background      *string        // "auto" | "transparent" | "opaque" (gpt-image-1 only)
    UserID          string         // per-call override; empty ⇒ use ctor default
    PollInterval    time.Duration  // initial poll delay; zero ⇒ 500ms default
    MaxPollInterval time.Duration  // max poll delay; zero ⇒ 10s default
}

type ImageGenDataItem struct {
    URL           string `json:"url,omitempty"`
    B64JSON       string `json:"b64_json,omitempty"`
    RevisedPrompt string `json:"revised_prompt,omitempty"`
}

type ImageGenResult struct {
    Created int64              `json:"created"`
    Data    []ImageGenDataItem `json:"data"`
}
```

### 5.4 Wire-body building (MED#1 — explicit)

The Go SDK builds the JSON request body as `map[string]any` to preserve "explicitly-set vs omitted" distinction. Mirrors Python SDK `client.py:653-670`:

```go
// inside GenerateImage, after UUID + non-empty-prompt validation:
input := map[string]any{"prompt": req.Prompt}
if req.Size != nil {
    input["size"] = *req.Size  // includes "" (empty string) if caller explicitly set it
}
if req.N != nil {
    input["n"] = *req.N
}
if req.ResponseFormat != nil {
    input["response_format"] = *req.ResponseFormat
}
if req.Quality != nil {
    input["quality"] = *req.Quality
}
if req.Style != nil {
    input["style"] = *req.Style
}
if req.Background != nil {
    input["background"] = *req.Background
}

body := map[string]any{
    "operation":    "image_gen",
    "model_source": string(req.ModelSource),
    "model_ref":    req.ModelRef,
    "input":        input,
}
```

Memory `feedback_sdk_default_arg_dropped_from_wire` warns against `if arg != default: include` checks (silently drops explicit-equal-to-default). The pointer-nil-check pattern preserves caller intent — an explicit empty string still wires through.

### 5.5 Error model (HIGH#1 — central helper + regression-lock)

```go
// errors.go
package llmgw

import (
    "errors"
    "fmt"
)

// Error is the error type returned by all SDK methods. The Code field
// matches the gateway's openapi ErrorBody.code namespace. Use errors.Is
// to match by sentinel, or errors.As to retrieve fields (StatusCode,
// RetryAfterS).
type Error struct {
    Code        string  // e.g. "LLM_IMAGE_CONTENT_POLICY_VIOLATION"
    Message     string
    StatusCode  int     // HTTP status if known (0 otherwise)
    RetryAfterS float64 // only set for rate-limit; 0 otherwise
    inner       error   // sentinel for errors.Is matching
}

func (e *Error) Error() string {
    if e.StatusCode > 0 {
        return fmt.Sprintf("%s (http=%d): %s", e.Code, e.StatusCode, e.Message)
    }
    return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

func (e *Error) Unwrap() error { return e.inner }

// Sentinel errors — match via errors.Is(err, ErrXxx).
var (
    ErrAuthFailed            = errors.New("LLM_AUTH_FAILED")
    ErrInvalidRequest        = errors.New("LLM_INVALID_REQUEST")
    ErrQuotaExceeded         = errors.New("LLM_QUOTA_EXCEEDED")
    ErrModelNotFound         = errors.New("LLM_MODEL_NOT_FOUND")
    ErrRateLimited           = errors.New("LLM_RATE_LIMITED")
    ErrUpstream              = errors.New("LLM_UPSTREAM_ERROR")
    ErrImageContentPolicy    = errors.New("LLM_IMAGE_CONTENT_POLICY_VIOLATION")
    ErrImageGenerationFailed = errors.New("LLM_IMAGE_GENERATION_FAILED")
    ErrJobNotFound           = errors.New("LLM_JOB_NOT_FOUND")
    ErrJobTerminal           = errors.New("LLM_JOB_TERMINAL")
    ErrHTTPTransport         = errors.New("LLM_HTTP_ERROR")
    ErrDecode                = errors.New("LLM_DECODE_ERROR")
)

// codeSentinels maps gateway error codes to their sentinel error.
// Unknown codes fall through to a nil inner (Error still constructable,
// errors.Is just returns false for any specific sentinel).
var codeSentinels = map[string]error{
    "LLM_AUTH_FAILED":                    ErrAuthFailed,
    "LLM_INVALID_REQUEST":                ErrInvalidRequest,
    "LLM_QUOTA_EXCEEDED":                 ErrQuotaExceeded,
    "LLM_MODEL_NOT_FOUND":                ErrModelNotFound,
    "LLM_RATE_LIMITED":                   ErrRateLimited,
    "LLM_UPSTREAM_ERROR":                 ErrUpstream,
    "LLM_IMAGE_CONTENT_POLICY_VIOLATION": ErrImageContentPolicy,
    "LLM_IMAGE_GENERATION_FAILED":        ErrImageGenerationFailed,
    "LLM_JOB_NOT_FOUND":                  ErrJobNotFound,
    "LLM_JOB_TERMINAL":                   ErrJobTerminal,
    "LLM_HTTP_ERROR":                     ErrHTTPTransport,
    "LLM_DECODE_ERROR":                   ErrDecode,
}

// newErrorFromCode constructs a *Error with the right sentinel populated
// for errors.Is matching. ALL Error construction in the SDK MUST go
// through this helper — manual struct construction risks forgetting to
// set `inner` and silently breaking `errors.Is(err, ErrXxx)` for
// callers. (Per /review-impl(DESIGN) HIGH#1.)
func newErrorFromCode(code, message string, statusCode int) *Error {
    return &Error{
        Code:       code,
        Message:    message,
        StatusCode: statusCode,
        inner:      codeSentinels[code], // nil if unknown — OK
    }
}

// newErrorFromCodeWithRetry — same as newErrorFromCode but with retry-after.
func newErrorFromCodeWithRetry(code, message string, statusCode int, retryAfterS float64) *Error {
    return &Error{
        Code:        code,
        Message:     message,
        StatusCode:  statusCode,
        RetryAfterS: retryAfterS,
        inner:       codeSentinels[code],
    }
}
```

**Regression-lock test (per HIGH#1):**

```go
// errors_test.go
func TestNewErrorFromCode_AllKnownCodesMatchSentinels(t *testing.T) {
    for code, sentinel := range codeSentinels {
        err := newErrorFromCode(code, "test msg", 500)
        if !errors.Is(err, sentinel) {
            t.Errorf("errors.Is failed for code %s: inner sentinel not populated", code)
        }
    }
}

func TestNewErrorFromCode_UnknownCode_DoesNotPanic(t *testing.T) {
    err := newErrorFromCode("LLM_FUTURE_UNKNOWN_CODE", "msg", 500)
    // No specific sentinel matches, but Error() still works and
    // errors.Is against ANY sentinel returns false (not panics).
    if err.Code != "LLM_FUTURE_UNKNOWN_CODE" {
        t.Errorf("Code lost")
    }
    if errors.Is(err, ErrAuthFailed) {
        t.Errorf("unexpected sentinel match on unknown code")
    }
}
```

### 5.6 Transport (`transport.go`)

Four operations: `submitJob`, `getJob`, `cancelJob`, plus `waitTerminal` which loops over `getJob`.

```go
// submitJob POSTs the submit-job envelope and returns the 202 response.
// On 4xx/5xx, decodes ErrorBody and returns a typed *Error via newErrorFromCode.
func (c *Client) submitJob(ctx context.Context, body map[string]any, userIDOverride string) (*submitJobResponse, error)

// getJob GETs the current Job. 404 returns *Error with code LLM_JOB_NOT_FOUND.
func (c *Client) getJob(ctx context.Context, jobID string, userIDOverride string) (*job, error)

// cancelJob DELETEs the job. 204 and 409 (idempotent) return nil; 404 returns ErrJobNotFound.
func (c *Client) cancelJob(ctx context.Context, jobID string, userIDOverride string) error

// waitTerminal polls getJob with exponential backoff until status ∈
// {completed, failed, cancelled}, or ctx is cancelled.
//
// transientRetryBudget controls per-poll HTTP failure tolerance. Per
// Python SDK precedent (Phase 5c-α MED#1), this is fixed at 0 for
// generate_image — silent retry could double-charge BYOK.
//
// Honors ctx.Done() during sleeps via select.
func (c *Client) waitTerminal(ctx context.Context, jobID string, userIDOverride string, opts pollOptions) (*job, error)
```

**HTTP error mapping** (in transport.go's `raiseHTTPError`):
- Decode response body as `{code, message, retry_after_s}` JSON
- If decode fails: use generic `LLM_ERROR` code with status-bucket fallback
- Use `newErrorFromCode` (or `newErrorFromCodeWithRetry` for 429) — **never construct `*Error` manually**

### 5.7 Client lifecycle

The Go `*http.Client` is goroutine-safe and connection-pool-internal. Unlike Python's `httpx.AsyncClient`, there is **no explicit `aclose()`** needed. Per-call cancellation is via `context.Context`. Construct ONE Client at server startup, share across all handlers (goroutine-safe).

`Transport` injection (HIGH#5): caller may pass a custom `http.RoundTripper` but NOT a full `*http.Client`. This prevents the `Timeout` trap — the SDK's internal `*http.Client` has no Timeout; all wall-clock control is via `ctx`.

### 5.8 UUID validation

```go
import "github.com/google/uuid"

if _, err := uuid.Parse(req.ModelRef); err != nil {
    return nil, newErrorFromCode(
        "LLM_INVALID_REQUEST",
        fmt.Sprintf("model_ref must be UUID-shaped, got %q", req.ModelRef),
        0, // SDK-side validation; no HTTP status
    )
}
```

`book-service` already vendors `github.com/google/uuid v1.6.0` — SDK adds same dep.

## 6. `book-service::generateChapterMedia` migration shape

### 6.1 Before (current — [media.go:351-559](../../services/book-service/internal/api/media.go#L351-L559))

```go
func (s *Server) generateChapterMedia(w http.ResponseWriter, r *http.Request) {
    // ...
    // 1. Resolve provider credentials (~30 LOC)
    credURL := fmt.Sprintf("%s/internal/credentials/%s/%s?user_id=%s", ...)
    // ... HTTP request, decode, error handling
    var creds struct {
        ProviderKind      string `json:"provider_kind"`
        ProviderModelName string `json:"provider_model_name"`
        BaseURL           string `json:"base_url"`
        APIKey            string `json:"api_key"`
    }

    // 2. Direct provider POST to /v1/images/generations (~30 LOC)
    genReq, _ := http.NewRequestWithContext(ctx, "POST", baseURL+"/v1/images/generations", ...)
    // ... decode response

    // 3-6: download, MinIO upload, version record, billing (~70 LOC, unchanged)
}
```

### 6.2 After (proposed — incorporates MED#2, MED#3, MED#4 fixes)

```go
func (s *Server) generateChapterMedia(w http.ResponseWriter, r *http.Request) {
    if s.minio == nil {
        writeError(w, http.StatusServiceUnavailable, "MEDIA_UNAVAILABLE", "media storage not configured")
        return
    }
    if s.llmgw == nil {
        writeError(w, http.StatusServiceUnavailable, "GENERATION_UNAVAILABLE", "AI generation not configured")
        return
    }
    // ... ownership / lifecycle / body decode (unchanged from current implementation)

    ctx := r.Context()

    // 1+2: SDK call (replaces ~60 LOC credential resolve + direct POST)
    size := body.Size
    result, err := s.llmgw.GenerateImage(ctx, llmgw.GenerateImageRequest{
        Prompt:      body.Prompt,
        ModelSource: llmgw.ModelSource(body.ModelSource),
        ModelRef:    body.ModelRef,
        Size:        &size,
        UserID:      ownerID,
    })
    if err != nil {
        // MED#3 — use errors.As (not type-assert) to retrieve Error fields.
        // MED#2 — specific errors FIRST; ErrImageGenerationFailed and ErrUpstream
        // get SEPARATE cases (today same writeError; tomorrow may diverge).
        var llmErr *llmgw.Error
        _ = errors.As(err, &llmErr) // safe even if err is wrapped

        switch {
        case errors.Is(err, llmgw.ErrImageContentPolicy):
            msg := "Content policy violation"
            if llmErr != nil {
                msg = "Content policy: " + llmErr.Message
            }
            writeError(w, http.StatusBadRequest, "CONTENT_POLICY", msg)
        case errors.Is(err, llmgw.ErrQuotaExceeded):
            writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "AI provider quota exceeded")
        case errors.Is(err, llmgw.ErrModelNotFound):
            writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "AI model not found")
        case errors.Is(err, llmgw.ErrInvalidRequest):
            writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", err.Error())
        case errors.Is(err, llmgw.ErrRateLimited):
            // MED#4 — surface Retry-After header so FE can wait correctly
            if llmErr != nil && llmErr.RetryAfterS > 0 {
                w.Header().Set("Retry-After", strconv.Itoa(int(llmErr.RetryAfterS)))
            }
            writeError(w, http.StatusTooManyRequests, "RATE_LIMITED", "AI provider rate-limit")
        case errors.Is(err, llmgw.ErrImageGenerationFailed):
            writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI image generation failed (retryable)")
        case errors.Is(err, llmgw.ErrUpstream):
            writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI provider upstream error")
        case errors.Is(err, llmgw.ErrJobTerminal):
            // status=cancelled — shouldn't normally happen for sync request flow
            writeError(w, http.StatusGatewayTimeout, "GENERATION_CANCELLED", "AI generation cancelled")
        default:
            // Catch-all: unknown gateway code, transport error, decode error.
            writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI image generation failed")
        }
        return
    }
    if len(result.Data) == 0 || result.Data[0].URL == "" {
        writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "empty AI provider response")
        return
    }

    // 3. Download the generated image (unchanged)
    dlReq, _ := http.NewRequestWithContext(ctx, "GET", result.Data[0].URL, nil)
    client := &http.Client{Timeout: 120 * time.Second}
    imgResp, err := client.Do(dlReq)
    // ... unchanged

    // 4-5: ensure bucket + MinIO upload + DB version record (unchanged)
    // (Note: `ai_model` column now stores body.ModelRef (UUID) instead of
    //  creds.ProviderModelName. See §6.4 — Q6.A resolved as Option (a)).

    // 6. Best-effort usage billing.
    // provider_kind is NOT exposed by the unified SDK (gateway records its own
    // model usage; this billing call records APPLICATION-LEVEL purpose).
    // Per Phase 5e-α QC MED#1 precedent: pass empty string; usage-billing
    // accepts via JSON-null → Go-empty-string decode. Tracked as deferred.
    if s.cfg.UsageBillingServiceURL != "" {
        // ... unchanged billing call, with provider_kind="" instead of creds.ProviderKind
    }

    writeJSON(w, http.StatusCreated, map[string]any{
        "url":          mediaURL,
        "object_key":   objectKey,
        "version":      nextVersion,
        "version_id":   versionID,
        "ai_model":     body.ModelRef, // was creds.ProviderModelName — see §6.4
        "size":         uploadInfo.Size,
        "content_type": contentType,
    })
}
```

### 6.3 LOC reduction

| Section | Before | After | Δ |
|---|---|---|---|
| 1. Credential resolve | ~30 | 0 | −30 |
| 2. Direct provider POST | ~30 | ~7 (SDK call) | −23 |
| Error handling | ~10 | ~40 (typed switch) | +30 |
| Total handler | ~210 | ~110 | −100 (~48%) |

Adjusted ~48% reduction vs initial ~55% estimate after accounting for the larger typed-error switch.

### 6.4 `ai_model` field decision (Q6.A — closed: Option (a))

**Resolution:** Store `body.ModelRef` (UUID) in `block_media_versions.ai_model`. The legacy `creds.ProviderModelName` (human name like "dall-e-3") is no longer available because the SDK abstracts credentials. Frontend already resolves UUID → name via provider-list endpoints; the column-level rename is consumer-facing only.

**Deferred follow-up:** `D-PHASE5E-BETA1-IMAGE-PROVIDER-MODEL-NAME-IN-RESULT` tracks extending `ImageGenResult` to expose `provider_model_name` so the SDK can pass-through the human name to callers in a future cycle.

## 7. Server wiring (HIGH#3 — closed: keep current signature, build SDK inside `NewServer`)

```go
// services/book-service/internal/api/server.go
type Server struct {
    pool   *pgxpool.Pool
    cfg    *config.Config
    secret []byte
    minio  *minio.Client
    llmgw  *llmgw.Client  // NEW; nil only if NewClient errored (current pattern with s.minio)
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
    s := &Server{pool: pool, cfg: cfg, secret: []byte(cfg.JWTSecret)}
    if cfg.MinioEndpoint != "" && cfg.MinioSecretKey != "" {
        mc, err := minio.New(cfg.MinioEndpoint, ...)
        if err == nil { s.minio = mc }
    }
    // NEW (5e-β.1) — same nil-on-misconfig pattern as s.minio
    if cfg.LLMGatewayInternalURL != "" && cfg.InternalServiceToken != "" {
        lc, err := llmgw.NewClient(llmgw.Options{
            BaseURL:       cfg.LLMGatewayInternalURL,
            AuthMode:      llmgw.AuthInternal,
            InternalToken: cfg.InternalServiceToken,
            // UserID empty at ctor — multi-tenant; per-call override required
        })
        if err == nil { s.llmgw = lc }
    }
    return s
}
```

**Signature kept as `NewServer(pool, cfg) *Server`** — matches existing pattern. The handler checks `if s.llmgw == nil` for fail-safe (like `s.minio == nil` check today). Fail-fast at config-load comes from `config.Load()` returning error when `LLM_GATEWAY_INTERNAL_URL` is empty (§8).

## 8. Config + env changes

```go
// services/book-service/internal/config/config.go
type Config struct {
    // ... existing fields
    ProviderRegistryURL    string  // KEEPS — audio.go still uses
    LLMGatewayInternalURL  string  // NEW — book-service's image_gen path
}

func Load() (*Config, error) {
    c := &Config{
        // ... existing
        LLMGatewayInternalURL: os.Getenv("LLM_GATEWAY_INTERNAL_URL"),
    }
    // ... existing validation
    if c.LLMGatewayInternalURL == "" {
        return nil, fmt.Errorf("LLM_GATEWAY_INTERNAL_URL is required")
    }
    return c, nil
}
```

`docker-compose.yml` — add to `book-service`:

```yaml
LLM_GATEWAY_INTERNAL_URL: http://provider-registry-service:8085
```

(Same host as `PROVIDER_REGISTRY_SERVICE_URL` since the gateway IS provider-registry-service; the rename matches knowledge-service / worker-ai / translation-service naming convention.)

## 9. `go.mod` consumption + Dockerfile (HIGH#2)

### 9.1 book-service go.mod

```
require github.com/loreweave/llmgw v0.1.0

replace github.com/loreweave/llmgw => ../../sdks/go/llmgw
```

### 9.2 Dockerfile bump (HIGH#2)

Current (`services/book-service/Dockerfile`):
```dockerfile
FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/book-service ./cmd/book-service
```

After (matches Phase 5e-α video-gen-service approach — repo-root context):
```dockerfile
FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
# repo-root build context: COPY SDK first, then service code
COPY sdks/go/llmgw /sdks/go/llmgw
COPY services/book-service/go.mod services/book-service/go.sum services/book-service/
WORKDIR /src/services/book-service
# Adjust replace path — relative from /src/services/book-service to /sdks/go/llmgw
# is ../../sdks/go/llmgw which matches the in-repo path.
RUN go mod download
WORKDIR /src
COPY services/book-service services/book-service
WORKDIR /src/services/book-service
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/book-service ./cmd/book-service
```

### 9.3 docker-compose.yml book-service entry change

```yaml
book-service:
  build:
    context: ..              # was: ../services/book-service
    dockerfile: services/book-service/Dockerfile
  # ... rest unchanged
```

## 10. Test plan (HIGH#4 — scope-reduced)

### 10.1 Go SDK tests (`sdks/go/llmgw/`) — NEW

`client_test.go`:

| Test | What it proves |
|---|---|
| `TestGenerateImage_HappyPath` | SDK submits, polls, decodes a completed job's result correctly via httptest.NewServer |
| `TestGenerateImage_NonDefaultSize_ReachesWire` | **(HIGH#6)** Caller passes `Size: ptr("1792x1024")` (NOT "1024x1024" which is gateway default); test asserts wire body's `input.size == "1792x1024"`. Catches a hardcoded-default-bypass regression. |
| `TestGenerateImage_OmittedSize_NotInWire` | **(HIGH#6 companion)** Caller passes `Size: nil`; test asserts wire body's `input` does NOT contain "size" key |
| `TestGenerateImage_ExplicitN_ReachesWire` | Pointer-int explicit value forwarded; tests `feedback_sdk_default_arg_dropped_from_wire` learning |
| `TestGenerateImage_EmptyPrompt_ReturnsInvalidRequest` | SDK-side validation returns LLM_INVALID_REQUEST before hitting the wire |
| `TestGenerateImage_NonUUIDModelRef_ReturnsInvalidRequest` | UUID-shape validation at SDK boundary |
| `TestGenerateImage_ContextCancellation` | Cancelling ctx mid-poll returns `ctx.Err()` (not a hang); no goroutine leak |
| `TestGenerateImage_JobFailedWithContentPolicy_ReturnsTypedError` | `errors.Is(err, ErrImageContentPolicy)` true |
| `TestGenerateImage_JobFailedWithQuotaExceeded_ReturnsTypedError` | `errors.Is(err, ErrQuotaExceeded)` true |
| `TestGenerateImage_JobCancelled_ReturnsJobTerminalError` | status=cancelled surfaces as ErrJobTerminal |
| `TestGenerateImage_PollExponentialBackoff` | Verify poll interval grows 0.5→0.75→1.125→…→10s capped |

`transport_test.go`:

| Test | What it proves |
|---|---|
| `TestSubmitJob_OK` | 202 response decoded |
| `TestSubmitJob_400_InvalidRequest_PopulatesInner` | 400 with body code → `errors.Is(err, ErrInvalidRequest)` true (HIGH#1) |
| `TestSubmitJob_TransportError_ReturnsHTTPError` | net dial failure → `errors.Is(err, ErrHTTPTransport)` true |
| `TestGetJob_NotFound` | 404 → `errors.Is(err, ErrJobNotFound)` true |
| `TestWaitTerminal_TransientHTTPFailure_Budget0_RaisesImmediately` | budget=0 means first transport failure propagates |
| `TestWaitTerminal_TerminalStatuses` | each of {completed, failed, cancelled} ends the loop |
| `TestRaiseHTTPError_429_PopulatesRetryAfter` | 429 with body `retry_after_s` populates `*Error.RetryAfterS` (MED#4) |

`errors_test.go`:

| Test | What it proves |
|---|---|
| `TestNewErrorFromCode_AllKnownCodesMatchSentinels` | **(HIGH#1 regression-lock)** Every entry in codeSentinels can be reached via `errors.Is(err, sentinel)` after `newErrorFromCode(code, ...)` |
| `TestNewErrorFromCode_UnknownCode_DoesNotPanic` | Future codes don't crash; just don't match any sentinel |
| `TestError_ErrorString_IncludesCodeAndStatus` | Stringer format stable |
| `TestErrorUnwrap_ReturnsInner` | `errors.Unwrap` works for `errors.Is` chain-walk |

### 10.2 book-service tests — NEW, narrow scope

`services/book-service/internal/api/media_test.go`:

The full DB+MinIO+httptest integration harness is **out of scope** (HIGH#4 deferred). Instead, this cycle adds SDK-mock-level tests that prove the typed-error routing works:

**Approach:** Define a small consumer interface in book-service (`type imageGenerator interface { GenerateImage(ctx, req) (*ImageGenResult, error) }`), make `s.llmgw` typed against it so tests can inject a mock. The interface lives in book-service (consumer-defined). Concrete `*llmgw.Client` satisfies it automatically.

| Test | What it proves |
|---|---|
| `TestGenerateChapterMedia_SDKReturnsContentPolicy_Returns400` | Mock returns ErrImageContentPolicy → HTTP 400 with CONTENT_POLICY code |
| `TestGenerateChapterMedia_SDKReturnsQuotaExceeded_Returns402` | Mock returns ErrQuotaExceeded → HTTP 402 |
| `TestGenerateChapterMedia_SDKReturnsRateLimitedWithRetry_SetsHeader` | Mock returns ErrRateLimited with RetryAfterS=30; response has Retry-After: 30 |
| `TestGenerateChapterMedia_SDKReturnsImageGenerationFailed_Returns502` | MED#2 — separate case from Upstream; same status, different message |
| `TestGenerateChapterMedia_EmptyResultData_Returns502` | Empty `result.Data` surfaces as 502 |
| `TestGenerateChapterMedia_UnknownLLMError_FallsToDefault502` | Default-case catch-all works |

These tests don't need DB/MinIO because the SDK mock returns the error EARLY, before the download/MinIO/billing branches. The happy-path-with-DB integration test is in the deferred follow-up.

### 10.3 Grep-locks (CO#3 — folded into media_test.go as sub-test)

```go
// services/book-service/internal/api/media_test.go (top-level test function)
func TestNoLegacyLLMResolutionInMediaGo(t *testing.T) {
    body, err := os.ReadFile("media.go")
    if err != nil { t.Fatal(err) }
    src := string(body)
    forbidden := []string{
        "/internal/credentials/",
        "/v1/images/generations",
        "creds.ProviderKind",
        "creds.ProviderModelName",
        "creds.BaseURL",
        "creds.APIKey",
    }
    for _, f := range forbidden {
        if strings.Contains(src, f) {
            t.Errorf("media.go must NOT contain %q after 5e-β.1 migration", f)
        }
    }
    required := []string{
        `"github.com/loreweave/llmgw"`,
        "s.llmgw.GenerateImage(",
        "llmgw.ErrImageContentPolicy",
    }
    for _, r := range required {
        if !strings.Contains(src, r) {
            t.Errorf("media.go must contain %q after 5e-β.1 migration", r)
        }
    }
}

func TestAudioGoStillUsesLegacyPath(t *testing.T) {
    // ANTI-BAIT: confirm 5e-β.1 did NOT accidentally migrate audio.go.
    // audio.go migration is reserved for Phase 5e-β.2.
    body, err := os.ReadFile("audio.go")
    if err != nil { t.Fatal(err) }
    src := string(body)
    if !strings.Contains(src, "/internal/credentials/") {
        t.Error("audio.go appears to have been migrated; that was reserved for 5e-β.2")
    }
}
```

### 10.4 Existing tests

Run `go test ./...` from `services/book-service/` — confirm no regressions in `metrics_test.go`, `server_test.go`. Run `go vet ./...` clean.

## 11. Risks + mitigations

| Risk | Mitigation |
|---|---|
| **R1: Go SDK is greenfield — first published Go module in monorepo.** | Module path uses `github.com/loreweave/llmgw`; consumed via `replace` directive so no actual github publish needed yet. |
| **R2: Provider model name lost from response.** | Documented in §6.4 + deferred `D-PHASE5E-BETA1-IMAGE-PROVIDER-MODEL-NAME-IN-RESULT`. |
| **R3: Frontend may show "model_ref UUID" instead of human name.** | Frontend already has per-user model list with names; this removes a redundant inline source-of-truth. |
| **R4: audio.go still uses legacy /internal/credentials path.** | Intentional + tested by anti-bait grep-lock (audio.go MUST still contain legacy URL). Documented §4.2. |
| **R5: Polling loop holds an open HTTP connection during waits.** | No — each `getJob` is its own request; keep-alive pool reuses connections. |
| **R6: Context cancellation during poll could leak goroutines.** | `select { case <-ctx.Done(): return ctx.Err(); case <-time.After(interval): }`. No leaks. Tested by `TestGenerateImage_ContextCancellation`. |
| **R7: errors.Is matching only works if `inner` is populated.** | HIGH#1 fix — all `*Error` construction routes through `newErrorFromCode`; regression-lock test enforces. |
| **R8: First-ever Go SDK — easy to set patterns badly.** | All decisions resolved in DESIGN; structure mirrors Python SDK file-for-file. |
| **R9: book-service handler tests need DB/MinIO harness which doesn't exist.** | Scope-reduced (HIGH#4) — only SDK-mock-level tests this cycle; full harness deferred. |
| **R10: `creds.ProviderModelName` was used for the `ai_model` DB column.** | After migration, store `body.ModelRef` instead. Schema column is `text`, accepts UUID; FE resolves via provider list. |
| **R11: User passes `*http.Client` with Timeout — silent kill of long polls.** | HIGH#5 fix — SDK accepts only `http.RoundTripper`, not `*http.Client`. SDK builds internal `*http.Client{Transport: t}` with no Timeout. |
| **R12: Wire-body construction drops explicit-empty-string values.** | MED#1 fix — explicit `map[string]any` pattern, mirrors Python `client.py:653-670`. Pointer-nil ⇒ omit; pointer-to-empty-string ⇒ explicit empty. |
| **R13: errors.As vs type-assert.** | MED#3 fix — caller pattern always uses `errors.As`. Documented in §6.2 + README. |
| **R14: RetryAfterS hidden behind errors.Is.** | MED#4 fix — caller surfaces via Retry-After response header when present. |
| **R15: High-concurrency callers may saturate http.Transport.MaxIdleConnsPerHost (default 2).** | LOW#5 — documented in §13 deferred; not a 5e-β.1 blocker. |

## 12. Acceptance criteria

1. `cd sdks/go/llmgw && go test ./...` — all SDK tests pass.
2. `cd services/book-service && go build ./... && go vet ./... && go test ./...` — book-service builds, lints clean, tests pass.
3. `grep -n "/internal/credentials/" services/book-service/internal/api/media.go` — no matches (audio.go retains it; verified by anti-bait test).
4. `grep -n "/v1/images/generations" services/book-service/internal/api/media.go` — no matches.
5. `grep -n "GenerateImage" services/book-service/internal/api/media.go` — exactly one match (the SDK call).
6. POST `/v1/books/:id/chapters/:id/media-generate` returns the same response shape (`url`, `object_key`, `version`, `version_id`, `ai_model`, `size`, `content_type`) — backwards-compatible with frontend (except `ai_model` is UUID now, see §6.4).
7. `docker compose -f infra/docker-compose.yml build book-service` succeeds with the new repo-root build context.

## 13. Deferred items (added by this cycle)

| ID | Description | Target |
|---|---|---|
| `D-PHASE5E-BETA1-IMAGE-PROVIDER-MODEL-NAME-IN-RESULT` | Extend ImageGenResult to expose `provider_model_name` so callers don't lose the human-readable upstream model name | Track 2 / future cycle |
| `D-PHASE5E-BETA1-AI-MODEL-DB-MIGRATION` | (Maybe) backfill `block_media_versions.ai_model` to UUID format if the mixed-format becomes annoying | Won't-fix unless FE complains |
| `D-PHASE5E-BETA1-LIVE-SMOKE` | Manual: POST `/v1/books/.../media-generate` against gpt-image-1 / DALL-E-3 / local-image-generator-service:8700 after merge; verify happy path | After 5e-β.1 lands |
| `D-PHASE5E-BETA1-INTEGRATION-TEST-HARNESS` | Build Postgres + MinIO + JWT-issuer fixtures for book-service handler integration tests (incl. `generateChapterMedia` happy path) | Track 2 / Phase 5e-β.2 |
| `D-PHASE5E-BETA1-GO-SDK-LOGGING` | Add `Logger interface { Debug(msg string, kv ...any) }` field on Options or accept `*slog.Logger` for diagnostic events | Track 2 |
| `D-PHASE5E-BETA1-GO-SDK-TRANSPORT-TUNING` | Document or auto-tune `Transport.MaxIdleConnsPerHost` for high-concurrency callers | Track 2; revisit if load testing shows pain |
| `D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS` | (Carry-over from 5e-α) Backfill provider_kind at billing time if dashboards break on empty-string category | Phase 5e-β.2 or later |

## 14. Resolved decisions (closed in this DESIGN cycle)

| ID | Decision | Closure |
|---|---|---|
| Q5.1.A | Package identifier | `llmgw` (Go-idiomatic short; no underscore). Module path `github.com/loreweave/llmgw`; filesystem `sdks/go/llmgw/`. |
| Q6.A | `ai_model` column post-migration | Store `body.ModelRef` (UUID). FE resolves via provider-list endpoints; `D-PHASE5E-BETA1-IMAGE-PROVIDER-MODEL-NAME-IN-RESULT` tracks SDK enhancement. |
| /review-impl HIGH#1 | errors.Is sentinel population | Central helper `newErrorFromCode(code, msg, status)` populates `inner` from `codeSentinels` map. ALL construction routes through it. Regression-lock test enforces. |
| /review-impl HIGH#2 | Dockerfile + docker-compose context bump | Promoted to §4.1 in-scope; §9.2 + §9.3 give explicit diff. |
| /review-impl HIGH#3 | `NewServer` signature change | NO change — build SDK inside existing `NewServer(pool, cfg) *Server`, nil-on-misconfig matches `s.minio` precedent. |
| /review-impl HIGH#4 | Test harness scope | Reduced to SDK-mock-level tests in book-service; full DB-backed integration deferred. |
| /review-impl HIGH#5 | `*http.Client.Timeout` trap | SDK accepts `http.RoundTripper` only; internal `*http.Client` has no Timeout. |
| /review-impl HIGH#6 | NonDefaultSize false-negative | Test uses "1792x1024" (NOT gateway default "1024x1024"); asserts wire body, not result. |
| /review-impl MED#1 | Wire-body construction | Explicit `map[string]any` snippet in §5.4. |
| /review-impl MED#2 | Caller switch case ordering | ImageGenerationFailed split from Upstream into separate cases. |
| /review-impl MED#3 | type-assert vs errors.As | Always `errors.As`. |
| /review-impl MED#4 | RetryAfterS surface | Caller sets `Retry-After` response header from `*Error.RetryAfterS`. |
| /review-impl MED#5 | Module path / package naming | Closed via Q5.1.A (`llmgw`). |

---

**Status of this design:** READY-FOR-BUILD. All HIGH/MED findings folded inline. LOW items #1, #3, #4, #5 documented for awareness or deferred. COSMETIC items applied (`s.llmgw` field name stable; grep-locks folded into media_test.go).
