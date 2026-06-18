package llmgw

import "time"

// ModelSource mirrors the openapi enum.
type ModelSource string

const (
	ModelSourceUser     ModelSource = "user_model"
	ModelSourcePlatform ModelSource = "platform_model"
)

// AuthMode toggles between caller-provided JWT (FE / gateway-bff path)
// and internal X-Internal-Token + user_id query param (svc→svc path).
type AuthMode string

const (
	AuthJWT      AuthMode = "jwt"
	AuthInternal AuthMode = "internal"
)

// JobStatus matches the openapi schema.
type JobStatus string

const (
	JobPending   JobStatus = "pending"
	JobRunning   JobStatus = "running"
	JobCompleted JobStatus = "completed"
	JobFailed    JobStatus = "failed"
	JobCancelled JobStatus = "cancelled"
)

// ── Image generation ─────────────────────────────────────────────────

// GenerateImageRequest is the input to Client.GenerateImage.
//
// Optional fields use pointer types so callers can distinguish "explicit
// empty/zero value" from "omitted" — the wire payload uses Python-SDK-
// matching semantics: pointer-nil ⇒ key absent from body; pointer-to-
// value ⇒ key present even if the dereferenced value is zero.
type GenerateImageRequest struct {
	// Required.
	Prompt      string      // non-empty
	ModelSource ModelSource // user_model | platform_model
	ModelRef    string      // UUID-shaped string

	// Optional — nil pointer ⇒ omit from wire payload.
	Size           *string // e.g. "1024x1024", "1792x1024"; nil ⇒ gateway default
	N              *int    // image count; nil ⇒ gateway default
	ResponseFormat *string // "url" | "b64_json"; nil ⇒ gateway default ("url")
	Quality        *string // model-dependent
	Style          *string // "vivid" | "natural" (DALL-E-3)
	Background     *string // "auto" | "transparent" | "opaque" (gpt-image-1)

	// Per-call overrides.
	UserID          string        // overrides Client.UserID; required when AuthInternal & ctor UserID is empty
	PollInterval    time.Duration // initial poll delay; zero ⇒ 500ms
	MaxPollInterval time.Duration // max poll delay; zero ⇒ 10s
}

// ImageGenDataItem is one entry in ImageGenResult.Data.
//
// Exactly one of URL or B64JSON is populated based on the request's
// ResponseFormat. RevisedPrompt is upstream-populated when the model
// rewrote the prompt (DALL-E-3, gpt-image-1).
type ImageGenDataItem struct {
	URL           string `json:"url,omitempty"`
	B64JSON       string `json:"b64_json,omitempty"`
	RevisedPrompt string `json:"revised_prompt,omitempty"`
}

// ImageGenResult mirrors openapi `ImageGenResult`. Caller is responsible
// for downloading URLs immediately — gateway does NOT persist them, and
// upstream URL lifetimes vary (OpenAI ~1h; local services caller-config).
type ImageGenResult struct {
	Created int64              `json:"created"`
	Data    []ImageGenDataItem `json:"data"`
	// ProviderKind + ProviderModelName (Phase 5e, D-PHASE5E) carry the gateway-
	// resolved provider identity for the served generation. Additive/optional:
	// empty when the gateway predates the field. Consumers (book-service) use
	// them for usage analytics + the displayed model name.
	ProviderKind      string `json:"provider_kind,omitempty"`
	ProviderModelName string `json:"provider_model_name,omitempty"`
}

// ── Audio generation (Phase 5e-β.2) ──────────────────────────────────

// GenerateAudioRequest is the input to Client.GenerateAudio.
//
// /review-impl(DESIGN) HIGH#5 — optional fields use pointer types so
// callers can distinguish "explicit equal-to-default value" from
// "omitted" — preserves caller intent across SDK→gateway→upstream.
type GenerateAudioRequest struct {
	// Required.
	Texts       []string    // 1..MaxAudioGenInputs strings, each 1..4096 chars
	ModelSource ModelSource // user_model | platform_model
	ModelRef    string      // UUID-shaped string

	// Optional — nil pointer ⇒ omit from wire payload.
	Voice          *string  // nil ⇒ upstream default ("alloy" for OpenAI)
	Speed          *float64 // nil ⇒ upstream default (1.0); range 0.25..4.0
	Format         *string  // nil ⇒ upstream default ("mp3"); mp3/opus/aac/flac/wav/pcm
	ResponseFormat *string  // nil ⇒ gateway default ("b64_json"); b64_json|url

	// Per-call overrides.
	UserID          string        // overrides Client.UserID; required when AuthInternal & ctor UserID is empty
	PollInterval    time.Duration // initial poll delay; zero ⇒ 500ms
	MaxPollInterval time.Duration // max poll delay; zero ⇒ 10s
}

// AudioGenDataItem is one entry in AudioGenResult.Data.
//
// Exactly one of URL or B64JSON is populated based on the request's
// ResponseFormat. DurationMs is upstream-dependent (typically 0 for
// OpenAI TTS). ContentType is always populated.
type AudioGenDataItem struct {
	URL         string `json:"url,omitempty"`
	B64JSON     string `json:"b64_json,omitempty"`
	DurationMs  int    `json:"duration_ms,omitempty"`
	ContentType string `json:"content_type"`
}

// AudioGenResult mirrors openapi `AudioGenResult`. Order-preserving:
// Data[i] corresponds to request.Texts[i] 1:1.
type AudioGenResult struct {
	Created int64              `json:"created"`
	Data    []AudioGenDataItem `json:"data"`
}

// MaxAudioGenInputs — batch cap matching gateway's adapter-level limit.
// /review-impl(DESIGN) MED#1 — capped at 10 to bound double-bill exposure.
const MaxAudioGenInputs = 10

// MaxAudioGenInputCharsLen — per-input cap matching OpenAI TTS exactly.
const MaxAudioGenInputCharsLen = 4096

// ── Internal wire models (private) ───────────────────────────────────

// submitJobResponse decodes the 202 Accepted envelope from POST /v1/llm/jobs.
type submitJobResponse struct {
	JobID       string `json:"job_id"`
	Status      string `json:"status"`
	SubmittedAt string `json:"submitted_at"`
}

// job decodes GET /v1/llm/jobs/{id}. result is operation-specific JSON;
// caller-side type validation happens in GenerateImage / future
// GenerateAudio / GenerateVideo methods.
type job struct {
	JobID       string         `json:"job_id"`
	Operation   string         `json:"operation"`
	Status      JobStatus      `json:"status"`
	Result      map[string]any `json:"result,omitempty"`
	Error       *jobError      `json:"error,omitempty"`
	SubmittedAt string         `json:"submitted_at"`
	StartedAt   string         `json:"started_at,omitempty"`
	CompletedAt string         `json:"completed_at,omitempty"`
}

func (j *job) isTerminal() bool {
	return j.Status == JobCompleted || j.Status == JobFailed || j.Status == JobCancelled
}

type jobError struct {
	Code        string  `json:"code"`
	Message     string  `json:"message"`
	RetryAfterS float64 `json:"retry_after_s,omitempty"`
}

// pollOptions controls waitTerminal's behavior.
type pollOptions struct {
	pollInterval         time.Duration
	maxPollInterval      time.Duration
	transientRetryBudget int // per-poll HTTP failure tolerance; fixed at 0 for generate_image
}
