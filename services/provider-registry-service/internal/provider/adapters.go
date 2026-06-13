package provider

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

//go:embed preconfig_openai.json
var openaiPreconfigJSON []byte

//go:embed preconfig_anthropic.json
var anthropicPreconfigJSON []byte

func loadPreconfig(data []byte) []ModelInventory {
	type entry struct {
		ProviderModelName string         `json:"provider_model_name"`
		DisplayName       string         `json:"display_name"`
		Capability        string         `json:"capability"`
		ContextLength     *int           `json:"context_length"`
		IsRecommended     bool           `json:"is_recommended"`
		CapabilityFlags   map[string]any `json:"capability_flags"`
	}
	var entries []entry
	if err := json.Unmarshal(data, &entries); err != nil {
		return nil
	}
	out := make([]ModelInventory, len(entries))
	for i, e := range entries {
		flags := e.CapabilityFlags
		if flags == nil {
			flags = map[string]any{}
		}
		flags["_capability"] = e.Capability
		flags["_display_name"] = e.DisplayName
		flags["_is_recommended"] = e.IsRecommended
		out[i] = ModelInventory{
			ProviderModelName: e.ProviderModelName,
			ContextLength:     e.ContextLength,
			CapabilityFlags:   flags,
		}
	}
	return out
}

type Adapter interface {
	ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error)
	Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error)
	HealthCheck(ctx context.Context, endpointBaseURL, secret string) error

	// Stream — Phase 1a (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Open a
	// streaming chat completion against the provider and emit canonical
	// StreamChunk events via emit. Adapters that don't support streaming
	// return ErrStreamNotSupported; the route handler maps that to 501.
	//
	// emit returning an error means the downstream caller is gone; the
	// adapter MUST stop streaming and return that error.
	Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error

	// SupportsTools reports whether this adapter forwards `tools` /
	// `tool_choice` to the upstream provider. The capability lives on the
	// adapter (not a hand-maintained allowlist) so it cannot drift from
	// ResolveAdapter. The stream handler rejects a chat request carrying
	// tools/tool_choice for an adapter that returns false with HTTP 400
	// LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER before opening the SSE stream.
	SupportsTools() bool

	// Transcribe — Phase 5a. Speech-to-text. Adapter fetches the audio
	// at input.AudioURL (gateway-side HTTP GET, 30s timeout, 25MB cap),
	// posts to the provider's STT endpoint, and returns the transcript.
	// Adapters that don't support STT return ErrOperationNotSupported;
	// caller maps that to HTTP 501 (or sets job status=failed with code
	// LLM_OPERATION_NOT_SUPPORTED).
	Transcribe(ctx context.Context, endpointBaseURL, secret, modelName string, input TranscribeInput) (TranscribeOutput, Usage, error)

	// Speak — Phase 5a. Text-to-speech with streaming output. Adapter
	// posts to the provider's TTS endpoint and emits raw audio bytes in
	// chunks via emit. Final chunk has Final=true with empty Data. emit
	// returning an error means the downstream caller is gone; the
	// adapter MUST stop streaming and return that error. Adapters that
	// don't support TTS return ErrOperationNotSupported.
	Speak(ctx context.Context, endpointBaseURL, secret, modelName string, input SpeakInput, emit AudioEmitFn) error

	// GenerateImage — Phase 5c-α. Text-to-image generation via the
	// OpenAI-compatible /v1/images/generations endpoint. Adapter posts
	// the request and parses the response into GenerateImageOutput.
	// Adapters that don't support image generation return
	// ErrOperationNotSupported.
	GenerateImage(ctx context.Context, endpointBaseURL, secret, modelName string, input GenerateImageInput) (GenerateImageOutput, Usage, error)

	// GenerateVideo — Phase 5d. Text-to-video (and optionally image-
	// to-video) generation. Adapter dispatches to
	// /v1/videos/generations/text-to-video or
	// /v1/videos/generations/image-to-video based on InitImage presence
	// (path matches local-image-generator-service per
	// /review-impl(DESIGN) HIGH#1; NOT the singular /v1/video/generations
	// from the stale integration guide). Returns single-data-item
	// result. Adapters that don't support video gen return
	// ErrOperationNotSupported.
	GenerateVideo(ctx context.Context, endpointBaseURL, secret, modelName string, input GenerateVideoInput) (GenerateVideoOutput, Usage, error)

	// GenerateAudio — Phase 5e-β.2. Batch TTS via /v1/audio/speech
	// (distinct from Speak which streams). Submits N inputs sequentially
	// upstream (v1; parallel via D-PHASE5E-BETA2-AUDIO-GEN-PARALLEL-ADAPTER).
	// MUST preserve input order: output.Items[i] corresponds 1:1 to
	// input.Texts[i] per /review-impl(DESIGN) MED#5. Adapters that don't
	// support TTS return ErrOperationNotSupported.
	GenerateAudio(ctx context.Context, endpointBaseURL, secret, modelName string, input GenerateAudioInput) (GenerateAudioOutput, Usage, error)
}

// ErrStreamNotSupported — returned by adapters that don't yet implement
// Stream(). Route handler maps this to HTTP 501 Not Implemented.
var ErrStreamNotSupported = fmt.Errorf("streaming not supported by this provider adapter")

// ErrOperationNotSupported — Phase 5a. Returned by Transcribe/Speak (and
// future audio/image adapter methods) on providers that don't expose
// that capability. Caller (worker.runSttJob or stream-handler.streamTts)
// maps this to LLM_OPERATION_NOT_SUPPORTED. Distinct from
// ErrStreamNotSupported so the chat-streaming path can preserve its
// existing 501-mapping without leaking audio semantics.
var ErrOperationNotSupported = fmt.Errorf("operation not supported by this provider adapter")

// ErrAudioFetchFailed — Phase 5a. Returned by Transcribe when the
// gateway can't GET the input AudioURL (4xx/5xx, transport error,
// non-HTTPS scheme). Caller maps to LLM_AUDIO_FETCH_FAILED.
var ErrAudioFetchFailed = fmt.Errorf("audio fetch failed")

// ErrAudioTooLarge — Phase 5a. Returned by Transcribe when the audio
// fetched from AudioURL exceeds the 25MB cap (matches OpenAI Whisper
// upload limit). Caller maps to LLM_AUDIO_TOO_LARGE.
var ErrAudioTooLarge = fmt.Errorf("audio too large")

// ErrAudioURLDisallowed — Phase 5a /review-impl MED#2. Returned by
// Transcribe when AudioURL's hostname resolves to a private / loopback /
// link-local IP range. Defends against SSRF probing of internal services
// (AWS IMDS 169.254.169.254, localhost, RFC1918 ranges). Caller maps to
// LLM_AUDIO_URL_DISALLOWED.
var ErrAudioURLDisallowed = fmt.Errorf("audio_url disallowed")

// ErrTranscribeInputInvalid — Phase 5b /review-impl HIGH#2. Returned by
// Transcribe when the (AudioURL, AudioBytes) pair violates the exactly-
// one-set invariant: BOTH set (caller ambiguity) OR NEITHER set (caller
// forgot to supply audio). Caller (worker.runSttJob) maps to LLM_INVALID_REQUEST.
//
// Distinct from ErrAudioFetchFailed (which means "we had a source, but
// fetching/reading it failed") and from ErrOperationNotSupported (which
// means "no adapter implements this op"). This sentinel is specifically
// for the input-shape invariant.
var ErrTranscribeInputInvalid = fmt.Errorf("transcribe input invalid")

// ErrImageGenerationFailed — Phase 5c-α. Returned when upstream rejects
// the prompt or fails in a way the typed upstream classifier doesn't
// bucket as rate-limit/permanent/transient (model loading, unspecified
// backend error, response body exceeds MaxImageResponseBytes). Caller
// maps to LLM_IMAGE_GENERATION_FAILED.
var ErrImageGenerationFailed = fmt.Errorf("image generation failed")

// ErrImageContentPolicy — Phase 5c-α. Returned specifically when
// upstream signals a content-policy rejection (DALL-E
// "your_request_was_rejected" + safety system block; OpenAI 400 with
// `error.code: "content_policy_violation"`). Distinct so callers can
// surface the right UX hint ("rephrase your prompt") vs the generic
// "generation failed" (might be retryable). Caller maps to
// LLM_IMAGE_CONTENT_POLICY_VIOLATION.
var ErrImageContentPolicy = fmt.Errorf("image generation rejected by content policy")

// ErrImageInvalidParams — Phase 5c-α /review-impl(DESIGN) MED#5.
// Returned when adapter-level invariant check rejects a caller-provided
// field (n > MaxImagesPerJob, prompt empty, bad response_format).
// Distinct from the typed upstream errors because the upstream was
// never called. Caller maps to LLM_INVALID_REQUEST.
//
// Belt-and-suspenders with handler-level validation: handler caps via
// validateImageGenInput, adapter caps here so a non-handler caller
// (cron, future RabbitMQ submit, background re-run) can't bypass.
var ErrImageInvalidParams = fmt.Errorf("image generation params invalid")

// MaxImagesPerJob — Phase 5c-α /review-impl(DESIGN) MED#5. Adapter-level
// upper bound on n (images per job). LoreWeave imposes 4 as a deliberate
// spend cap (cheapest BYOK image-gen still costs ≈$0.02/image; 4×
// keeps a single-job-gone-wrong at the cost-of-coffee level).
const MaxImagesPerJob = 4

// ErrVideoGenerationFailed — Phase 5d. Generic upstream-failed sentinel
// (not content-policy, not rate-limited; e.g., model loading, ambiguous
// backend error, response body cap exceeded). Caller maps to
// LLM_VIDEO_GENERATION_FAILED.
var ErrVideoGenerationFailed = fmt.Errorf("video generation failed")

// ErrVideoContentPolicy — Phase 5d. Content-policy rejection (rare for
// most local video backends; reserved for OpenAI/managed services with
// safety filters). Caller maps to LLM_VIDEO_CONTENT_POLICY_VIOLATION.
var ErrVideoContentPolicy = fmt.Errorf("video generation rejected by content policy")

// ErrVideoInvalidParams — Phase 5d /review-impl(DESIGN) MED-anticipated.
// Adapter-level invariant rejection (Prompt empty, N out of range,
// bad ResponseFormat, init_image oversize). Caller maps to
// LLM_INVALID_REQUEST.
//
// Belt-and-suspenders with handler-level validation: handler caps via
// validateVideoGenInput, adapter caps here so non-handler callers
// can't bypass.
var ErrVideoInvalidParams = fmt.Errorf("video generation params invalid")

// MaxImg2VidInputBytes — Phase 5d /review-impl(DESIGN) MED#2.
// Adapter-level cap on the base64-encoded init_image input field.
// 10MB covers 4K PNGs (~10-15MB raw → 13-20MB b64) for typical cases
// while bounding worst-case DB row size + worker goroutine memory.
// Larger init frames typically don't help video gen quality (the
// model resizes anyway).
const MaxImg2VidInputBytes = 10 * 1024 * 1024

// ── audio_gen sentinels (Phase 5e-β.2) ────────────────────────────────

// ErrAudioGenerationFailed — Phase 5e-β.2. Generic upstream-failed
// sentinel for batch TTS (not auth, not rate-limited, not invalid-params;
// e.g., model loading, unspecified backend error, zero-byte response).
// Caller maps to LLM_AUDIO_GENERATION_FAILED.
var ErrAudioGenerationFailed = fmt.Errorf("audio generation failed")

// ErrAudioGenInvalidParams — Phase 5e-β.2 /review-impl(DESIGN) MED#5.
// Adapter-level invariant rejection (empty Texts, batch over cap, per-
// text empty/oversize). Caller maps to LLM_INVALID_REQUEST.
//
// Belt-and-suspenders with handler-level validation: handler caps via
// validateAudioGenInput, adapter caps here so non-handler callers
// (cron, future RabbitMQ submit, background re-run) can't bypass.
var ErrAudioGenInvalidParams = fmt.Errorf("audio_gen params invalid")

// MaxAudioGenInputs — Phase 5e-β.2 /review-impl(DESIGN) MED#1. Adapter-
// level upper bound on batch size. Capped at 10 (was 20 in initial
// design) to bound double-bill exposure on mid-batch failure: TTS is
// char-billed per upstream request; a batch failing on input 9 of 10
// still charged 8 prior calls. Cap at 10× per retry.
const MaxAudioGenInputs = 10

// MaxAudioGenInputCharsLen — Phase 5e-β.2 /review-impl(DESIGN) LOW#8.
// Per-input character cap (matches OpenAI TTS exactly).
const MaxAudioGenInputCharsLen = 4096

// MaxImageResponseBytes — Phase 5c-α /review-impl(DESIGN) LOW#6.
// Adapter-level cap on the upstream image response body. 8MB covers
// 4 × ~1024×1024 PNG b64 (~670KB each) with comfortable margin for
// JSON envelope + revised_prompt fields. Larger responses → LLM_UPSTREAM_ERROR
// with "exceeds N bytes" message. Documented in openapi.yaml
// ImageGenInput.response_format description so callers know the limit.
//
// /review-impl(BUILD) LOW#2 — this cap is on the DECOMPRESSED body
// size. Go's net/http transparently decompresses gzip when the request
// didn't explicitly set Accept-Encoding (the default), so a small
// wire payload could expand past 8MB once decompressed. For image gen
// this rarely matters (PNG/JPG already-compressed → 1:1 ratio); for
// b64_json strings (highly compressible — ~3:1 ratio for base64) it
// could surprise. If a real gzip-friendly upstream surfaces, document
// or raise the cap then.
const MaxImageResponseBytes = 8 * 1024 * 1024

// ── Audio types (Phase 5a + 5b) ────────────────────────────────────────

// TranscribeInput holds STT request parameters. EXACTLY ONE of AudioURL
// or AudioBytes must be set per call — the adapter pre-checks this and
// returns ErrTranscribeInputInvalid if violated. Both set OR neither set
// is an invariant violation, not a "pick one" preference.
type TranscribeInput struct {
	// AudioURL — Phase 5a. Gateway-fetchable HTTPS URL pointing to the
	// audio bytes. Caller is responsible for upload + URL signing.
	// Only http:// and https:// schemes are accepted. Set this OR
	// AudioBytes, never both.
	AudioURL string

	// AudioBytes — Phase 5b. Raw audio bytes already in the adapter's
	// address space. Used by the multipart-POST entrypoint to /v1/llm/jobs
	// so callers don't need to stage audio in a presigned URL. Set this
	// OR AudioURL, never both.
	AudioBytes []byte

	// ContentType — Phase 5b. MIME type of AudioBytes (e.g. "audio/webm",
	// "audio/wav"). Informs the adapter's filename-extension pick when
	// posting to the upstream multipart endpoint. Ignored in URL mode
	// (fetchAudioURL returns the upstream's Content-Type header instead).
	ContentType string

	// Language — ISO 639-1 code or "auto" for upstream auto-detection.
	// "auto" is converted to "omit param" at the provider HTTP layer
	// (OpenAI Whisper auto-detects when language is absent).
	Language string
}

// TranscribeOutput holds STT response data after parsing.
type TranscribeOutput struct {
	Text       string // transcribed text
	Language   string // detected language (empty if upstream didn't return)
	DurationMs int    // audio duration as reported by upstream (0 if absent)
}

// SpeakInput holds TTS request parameters.
type SpeakInput struct {
	Text   string  // input text to synthesize (max 4000 chars per OpenAI)
	Voice  string  // upstream voice name (e.g. "alloy", "echo")
	Speed  float64 // 0.25 .. 4.0; 1.0 default
	Format string  // "mp3" | "wav" | "opus" | "pcm"
}

// AudioChunk is a single emit payload from Speak.
type AudioChunk struct {
	SequenceID int    // monotonic 0-indexed counter within a single Speak call
	Data       []byte // raw audio bytes; nil/empty when Final=true
	Final      bool   // true on the closing emit; followed by handler's `done` event
}

// AudioEmitFn is the per-chunk callback Speak uses to push streamed audio.
// emit returning an error means the downstream caller is gone; Speak MUST
// stop streaming and return that error.
type AudioEmitFn = func(AudioChunk) error

// ── Image-gen types (Phase 5c-α) ──────────────────────────────────────

// GenerateImageInput mirrors the OpenAI Image API request shape 1:1 so
// any OpenAI-compatible backend works without per-backend adapter code.
// "" / 0 values omit the field at the upstream call so we don't override
// upstream defaults — except where the field carries an invariant
// (Prompt MUST be non-empty; N MUST be ≤ MaxImagesPerJob).
type GenerateImageInput struct {
	// Prompt — required, max 32K (validated at handler before reaching
	// adapter). Adapter pre-checks empty as a defense for non-handler callers.
	Prompt string

	// Size — e.g. "1024x1024"; "" → upstream default.
	Size string

	// N — number of images (1..MaxImagesPerJob). 0 → upstream default
	// (treated as 1 by most backends). Adapter rejects N > MaxImagesPerJob.
	N int

	// ResponseFormat — "url" | "b64_json"; "" → omit (upstream chooses).
	// Adapter validates the enum so a non-handler caller can't slip in
	// "jpeg" or similar.
	ResponseFormat string

	// Quality — "standard" | "hd" | "high" | "medium" | "low"; "" → omit.
	Quality string

	// Style — "vivid" | "natural" (DALL-E-3 only); "" → omit.
	Style string

	// Background — "auto" | "transparent" | "opaque" (gpt-image-1 only); "" → omit.
	Background string
}

// GenerateImageOutput holds the parsed response from
// /v1/images/generations.
type GenerateImageOutput struct {
	// Created — unix timestamp (seconds) when the generation finished.
	Created int64

	// Data — 1..MaxImagesPerJob entries (handler caps; adapter respects
	// upstream's response). Each entry has exactly one of URL or B64JSON
	// populated based on the request's ResponseFormat.
	Data []GeneratedImage
}

// GeneratedImage is a single image in the response. RevisedPrompt is
// upstream-populated when the model rewrote the prompt (DALL-E-3 +
// gpt-image-1 do this; local models typically don't).
type GeneratedImage struct {
	URL           string
	B64JSON       string
	RevisedPrompt string
}

// ── Video-gen types (Phase 5d) ────────────────────────────────────────

// GenerateVideoInput mirrors the OpenAI-compatible video generation
// request shape but with field names matching the actual
// local-image-generator-service backend (NOT the stale integration
// guide). Specifically, the img2vid conditioning field is named
// `init_image` (per local-image-generator-service's VideoGenerateRequest),
// NOT `image` per the guide.
//
// Path dispatch is handled by the adapter based on InitImage presence:
//   - InitImage == ""  → POST /v1/videos/generations/text-to-video
//   - InitImage != ""  → POST /v1/videos/generations/image-to-video
//
// /review-impl(DESIGN) HIGH#1 — the integration guide's singular
// /v1/video/generations is aspirational; the real backend uses plural
// + text-to-video/image-to-video sub-segments.
type GenerateVideoInput struct {
	// Prompt — required, max 32K (validated at handler). Adapter
	// pre-checks empty.
	Prompt string

	// Size — e.g. "1920x1080"; "" → upstream default.
	Size string

	// Duration — seconds (1..60); 0 → omit (upstream default ≈5s).
	Duration int

	// N — Phase 5d locks to n=1. Adapter rejects N>1 or N<0 with
	// ErrVideoInvalidParams.
	N int

	// ResponseFormat — Phase 5d accepts "url" only per
	// /review-impl(DESIGN) MED#3 (b64_json impractical for video — even
	// short clips exceed MaxImageResponseBytes). "" → omit (upstream
	// defaults to url-like behavior).
	ResponseFormat string

	// Style — optional style hint; "" → omit.
	Style string

	// InitImage — Phase 5d. Optional base64-encoded image for
	// image-to-video models (Wan, LTX Video). When non-empty, adapter
	// dispatches to /v1/videos/generations/image-to-video. Capped at
	// MaxImg2VidInputBytes (10MB).
	InitImage string
}

// GenerateVideoOutput holds the parsed response from
// /v1/videos/generations/{text,image}-to-video (sync mode).
type GenerateVideoOutput struct {
	// Created — unix timestamp when generation finished.
	Created int64

	// Data — Phase 5d locks to len(1). Single generated video.
	Data []GeneratedVideo
}

// GeneratedVideo is a single video in the response. RevisedPrompt is
// upstream-populated when the model rewrote the prompt (rare for video
// — most local backends don't do safety-system rewriting).
type GeneratedVideo struct {
	URL           string
	RevisedPrompt string
}

// ── audio_gen types (Phase 5e-β.2) ────────────────────────────────────

// GenerateAudioInput — batch TTS input. Texts MUST be ordered (output
// preserves input position); per-text limits enforced at adapter +
// handler.
type GenerateAudioInput struct {
	// Texts — 1..MaxAudioGenInputs strings, each 1..MaxAudioGenInputCharsLen chars.
	Texts []string

	// Voice — upstream voice name; "" → adapter default ("alloy" for OpenAI).
	Voice string

	// Speed — 0.25..4.0; 0 → adapter default (1.0).
	Speed float64

	// Format — "mp3" (default if empty) | "opus" | "aac" | "flac" | "wav" | "pcm".
	Format string

	// ResponseFormat — "b64_json" (default if empty) | "url".
	// b64_json: bytes in result; url: gateway stages to MinIO + returns public URL.
	ResponseFormat string
}

// GenerateAudioOutput — adapter returns raw bytes per input. Worker
// converts to b64 or stages to MinIO based on input.ResponseFormat
// AFTER the adapter call returns.
type GenerateAudioOutput struct {
	// Items[i] corresponds 1:1 to input.Texts[i] (order-preserving invariant
	// per /review-impl(DESIGN) MED#5).
	Items []GeneratedAudio
}

// GeneratedAudio is one audio file in the batch response.
type GeneratedAudio struct {
	Data        []byte // raw audio bytes; non-empty (adapter rejects 0-byte upstream)
	Format      string // canonical format string ("mp3", "opus", etc.)
	ContentType string // upstream MIME, e.g. "audio/mpeg"
	DurationMs  int    // 0 if upstream didn't report
}

type ModelInventory struct {
	ProviderModelName string         `json:"provider_model_name"`
	ContextLength     *int           `json:"context_length,omitempty"`
	CapabilityFlags   map[string]any `json:"capability_flags"`
}

type Usage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

// ── helpers ───────────────────────────────────────────────────────────────────

func postJSON(ctx context.Context, client *http.Client, url string, headers map[string]string, body any) (map[string]any, error) {
	b, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(b))
	if err != nil {
		return nil, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	res, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http: %w", err)
	}
	defer res.Body.Close()
	raw, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("unmarshal (status %d): %s", res.StatusCode, string(raw))
	}
	if res.StatusCode >= 400 {
		msg := ""
		if e, ok := out["error"]; ok {
			msg = fmt.Sprintf("%v", e)
		}
		return nil, fmt.Errorf("provider error %d: %s", res.StatusCode, msg)
	}
	return out, nil
}

func getJSON(ctx context.Context, client *http.Client, url string, headers map[string]string) (map[string]any, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("new request: %w", err)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	res, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http: %w", err)
	}
	defer res.Body.Close()
	// Limit response size to 10MB to prevent OOM
	raw, err := io.ReadAll(io.LimitReader(res.Body, 10<<20))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	if res.StatusCode >= 400 {
		return nil, fmt.Errorf("provider error %d: %s", res.StatusCode, string(raw[:min(len(raw), 200)]))
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("unmarshal: expected JSON, got %s", string(raw[:min(len(raw), 100)]))
	}
	return out, nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func extractMessages(input map[string]any) []map[string]any {
	if v, ok := input["messages"]; ok {
		if msgs, ok := v.([]map[string]any); ok {
			return msgs
		}
		// handle []any (from JSON decode)
		if raw, ok := v.([]any); ok {
			out := make([]map[string]any, 0, len(raw))
			for _, item := range raw {
				if m, ok := item.(map[string]any); ok {
					out = append(out, m)
				}
			}
			return out
		}
	}
	return []map[string]any{{"role": "user", "content": "Hi"}}
}

// forwardOptionalChatFields copies passthrough fields from the SDK's
// `input` dict into the upstream request body when present. Centralizes
// the per-field "if ok, forward" pattern so every OpenAI-compatible
// adapter (openai, lm_studio, ollama) treats these the same way.
//
// Fields forwarded:
//   - response_format    — JSON-schema enforcement (OpenAI structured
//     output, LM Studio + Ollama via llama.cpp's grammar layer)
//   - chat_template_kwargs — llama.cpp passthrough (e.g.
//     {"thinking": false}, {"enable_thinking": false}) to suppress
//     thinking-mode generation on reasoning-capable local models
//     (Qwen3-thinking, DeepSeek-R1, abliterated variants). Critical
//     for extraction pipelines whose JSON output is otherwise
//     swallowed by reasoning_tokens (D-EXTRACTION-CONTEXT-FIX-STAGE-4).
//   - reasoning_effort   — OpenAI o1/o3-style reasoning budget knob
//   - top_p, top_k, presence_penalty, frequency_penalty, seed —
//     standard sampling controls
//
// Providers that don't recognize a field generally ignore it; OpenAI
// rejects unknown fields with 400, but the SDK doesn't include those
// fields unless explicitly set. We keep the surface narrow + boring.
func forwardOptionalChatFields(input, body map[string]any) {
	passthrough := []string{
		"response_format",
		"chat_template_kwargs",
		"reasoning_effort",
		"top_p",
		"top_k",
		"presence_penalty",
		"frequency_penalty",
		"seed",
	}
	for _, k := range passthrough {
		if v, ok := input[k]; ok {
			body[k] = v
		}
	}
}

// ── OpenAI adapter ────────────────────────────────────────────────────────────

// openaiIsReasoningModel reports whether an OpenAI model accepts the
// `reasoning_effort` knob — the o-series reasoning models (o1, o3, o4, …). The
// gpt-* chat models (gpt-4o, gpt-4.1, …) do NOT and reject it with HTTP 400.
func openaiIsReasoningModel(model string) bool {
	m := strings.ToLower(strings.TrimSpace(model))
	for _, p := range []string{"o1", "o3", "o4", "o5"} {
		if strings.HasPrefix(m, p) {
			return true
		}
	}
	return false
}

// stripDefaultOpenAIUnsupportedFields removes request fields that REAL OpenAI
// cloud rejects with HTTP 400 ("Unrecognized request argument supplied: …"),
// but ONLY when targeting the default OpenAI endpoint (empty base_url). A custom
// base_url is a local OpenAI-compatible server (LM Studio / Ollama / vLLM) that
// uses these to suppress thinking, so it keeps them.
//   - chat_template_kwargs — a llama.cpp/vLLM-only passthrough (TR-4); OpenAI
//     never accepts it.
//   - reasoning_effort — an o-series-only knob; gpt-* chat models reject it.
//     Composition sets reasoning_effort="none" to disable local thinking models,
//     so without this strip every OpenAI non-o-series chat model 400s.
func stripDefaultOpenAIUnsupportedFields(body map[string]any, modelName, endpointBaseURL string) {
	if strings.TrimRight(endpointBaseURL, "/") != "" {
		return // custom base_url → a local OpenAI-compatible server; keep the fields
	}
	delete(body, "chat_template_kwargs")
	if !openaiIsReasoningModel(modelName) {
		delete(body, "reasoning_effort")
	}
}

type openaiAdapter struct {
	client          *http.Client
	staticInventory []ModelInventory
}

const openaiBaseURL = "https://api.openai.com"

func (a *openaiAdapter) ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	out, err := getJSON(ctx, a.client, base+"/v1/models", headers)
	if err != nil {
		// Fallback to static inventory if API call fails
		return a.staticInventory, nil
	}
	// OpenAI-shape: {"data":[{"id":...}]}
	if data, ok := out["data"].([]any); ok && len(data) > 0 {
		return parseOpenAIModels(data), nil
	}
	// C2 (BL-2): Cohere-shape: {"models":[{"name":...,"endpoints":["rerank"|"embed"|"chat"]}]}.
	// Local-rerank backends (rerank_local kind) resolve to this OpenAI-compatible
	// adapter; a Cohere-compatible /v1/models lists rerank models we must discover.
	if models, ok := out["models"].([]any); ok && len(models) > 0 {
		return parseCohereModels(models), nil
	}
	return a.staticInventory, nil
}

// parseCohereModels parses a Cohere-shape /v1/models payload. Cohere advertises a
// model's capabilities via its `endpoints` array (e.g. ["rerank"], ["embed"],
// ["chat"]); we map that to the canonical capability token and tag the boolean
// flag for rerank so the RerankModelPicker filter (capability_flags @> {"rerank":true}
// OR _capability='rerank') finds discovered rerank models. Falls back to a name
// substring when `endpoints` is absent.
func parseCohereModels(models []any) []ModelInventory {
	var out []ModelInventory
	for _, item := range models {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		name, _ := m["name"].(string)
		if name == "" {
			continue
		}
		cap := "chat"
		if eps, ok := m["endpoints"].([]any); ok {
			for _, e := range eps {
				switch s, _ := e.(string); s {
				case "rerank":
					cap = "rerank"
				case "embed":
					if cap != "rerank" {
						cap = "embedding"
					}
				}
			}
		}
		if cap == "chat" && strings.Contains(strings.ToLower(name), "rerank") {
			cap = "rerank"
		}
		flags := map[string]any{
			"_capability":   cap,
			"_display_name": name,
		}
		if cap == "rerank" {
			flags["rerank"] = true
		}
		var ctxLen *int
		if cl, ok := m["context_length"].(float64); ok && cl > 0 {
			v := int(cl)
			ctxLen = &v
		}
		out = append(out, ModelInventory{
			ProviderModelName: name,
			ContextLength:     ctxLen,
			CapabilityFlags:   flags,
		})
	}
	return out
}

func parseOpenAIModels(data []any) []ModelInventory {
	var models []ModelInventory
	for _, item := range data {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		id, _ := m["id"].(string)
		if id == "" {
			continue
		}
		cap := classifyOpenAIModel(id)
		flags := map[string]any{
			"_capability":   cap,
			"_display_name": id,
		}
		// C2: also set the canonical boolean flag for rerank so the picker's
		// `capability_flags @> {"rerank":true}` filter matches (the canonical schema),
		// in addition to the `_capability='rerank'` match. Keeps discovery aligned
		// with C0/C1's RERANK_CAPABILITY token.
		if cap == "rerank" {
			flags["rerank"] = true
		}
		// Detect thinking models
		if strings.HasPrefix(id, "o1") || strings.HasPrefix(id, "o3") || strings.HasPrefix(id, "o4") {
			flags["thinking"] = true
		}
		models = append(models, ModelInventory{
			ProviderModelName: id,
			CapabilityFlags:   flags,
		})
	}
	return models
}

func classifyOpenAIModel(id string) string {
	switch {
	// C2 (BL-2): rerank discovery — a Cohere-shape `/v1/models` (or any OpenAI-
	// compatible local-rerank backend) lists cross-encoder models whose id carries
	// "rerank" (e.g. rerank-v3.5, rerank-english-v3.0, bge-reranker-v2-m3). Tag the
	// canonical `rerank` capability (NOT "reranker") so the RerankModelPicker filter
	// finds them. Checked first because a reranker id never collides with the others.
	case strings.Contains(id, "rerank"):
		return "rerank"
	case strings.Contains(id, "embedding") || strings.Contains(id, "ada-002"):
		return "embedding"
	case strings.Contains(id, "dall-e") || strings.Contains(id, "gpt-image") || strings.Contains(id, "sora") || id == "chatgpt-image-latest":
		return "image_gen"
	case strings.Contains(id, "tts") || strings.Contains(id, "whisper"):
		return "tts"
	case strings.Contains(id, "audio") || strings.Contains(id, "realtime"):
		return "audio"
	case strings.Contains(id, "transcribe"):
		return "stt"
	case strings.Contains(id, "moderation"):
		return "moderation"
	case strings.HasPrefix(id, "davinci") || strings.HasPrefix(id, "babbage"):
		return "completion"
	default:
		return "chat"
	}
}

func (a *openaiAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	payload := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	// Policy: include max_tokens only when caller passes a positive
	// value. Caller-omitted / 0 → let the model decide (no upstream
	// cap). OpenAI accepts requests without max_tokens.
	if v, ok := input["max_tokens"]; ok {
		if mt := int(toFloat(v)); mt > 0 {
			payload["max_tokens"] = mt
		}
	}
	if v, ok := input["temperature"]; ok {
		payload["temperature"] = v
	}
	out, err := postJSON(ctx, a.client, base+"/v1/chat/completions",
		map[string]string{"Authorization": "Bearer " + secret},
		payload,
	)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	if u, ok := out["usage"].(map[string]any); ok {
		usage.InputTokens = int(toFloat(u["prompt_tokens"]))
		usage.OutputTokens = int(toFloat(u["completion_tokens"]))
	}
	return out, usage, nil
}

func (a *openaiAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "gpt-4o-mini",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

func (a *openaiAdapter) Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	body := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	// Policy: max_tokens=0 means omit (let the model decide). Phase 3c
	// enforced at SDK + gateway-handler; this is the final guard for
	// callers posting directly to /internal/proxy or future SDKs.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		body["max_tokens"] = v
	}
	if v, ok := input["tools"]; ok {
		body["tools"] = v
	}
	if v, ok := input["tool_choice"]; ok {
		body["tool_choice"] = v
	}
	forwardOptionalChatFields(input, body)
	// chat_template_kwargs (e.g. {enable_thinking:false}) is a llama.cpp/vLLM
	// passthrough used by LM Studio / Ollama / local OpenAI-compatible servers
	// to suppress reasoning-model thinking. Real OpenAI cloud rejects unknown
	// fields with 400, so strip it when this is the DEFAULT OpenAI endpoint
	// (no custom base_url). Custom base_url (a local OpenAI-compatible server)
	// keeps it — that's how translation/extraction disable thinking. (TR-4)
	stripDefaultOpenAIUnsupportedFields(body, modelName, endpointBaseURL)
	resp, err := openCompletionStream(ctx, a.client, base+"/v1/chat/completions", headers, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return streamOpenAICompat(ctx, resp.Body, emit)
}

// SupportsTools — the OpenAI chat-completions API supports tools + tool_choice.
func (a *openaiAdapter) SupportsTools() bool { return true }

// ── Anthropic adapter ─────────────────────────────────────────────────────────

type anthropicAdapter struct {
	client          *http.Client
	staticInventory []ModelInventory
}

const anthropicBaseURL = "https://api.anthropic.com"

func (a *anthropicAdapter) ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = anthropicBaseURL
	}
	headers := map[string]string{
		"x-api-key":         secret,
		"anthropic-version": "2023-06-01",
	}
	out, err := getJSON(ctx, a.client, base+"/v1/models", headers)
	if err != nil {
		return a.staticInventory, nil
	}
	data, ok := out["data"].([]any)
	if !ok || len(data) == 0 {
		return a.staticInventory, nil
	}
	return parseAnthropicModels(data), nil
}

func parseAnthropicModels(data []any) []ModelInventory {
	var models []ModelInventory
	for _, item := range data {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		id, _ := m["id"].(string)
		displayName, _ := m["display_name"].(string)
		if id == "" {
			continue
		}
		if displayName == "" {
			displayName = id
		}
		flags := map[string]any{
			"_capability":   "chat",
			"_display_name": displayName,
		}
		// Parse context length
		var ctxLen *int
		if v, ok := m["max_input_tokens"].(float64); ok && v > 0 {
			n := int(v)
			ctxLen = &n
		}
		// Parse rich capabilities
		if caps, ok := m["capabilities"].(map[string]any); ok {
			if isSupported(caps, "thinking") {
				flags["thinking"] = true
			}
			if isSupported(caps, "image_input") {
				flags["vision"] = true
			}
			if isSupported(caps, "pdf_input") {
				flags["pdf"] = true
			}
			if isSupported(caps, "code_execution") {
				flags["code_execution"] = true
			}
			if isSupported(caps, "structured_outputs") {
				flags["structured_outputs"] = true
			}
		}
		models = append(models, ModelInventory{
			ProviderModelName: id,
			ContextLength:     ctxLen,
			CapabilityFlags:   flags,
		})
	}
	return models
}

func isSupported(caps map[string]any, key string) bool {
	if v, ok := caps[key].(map[string]any); ok {
		if sup, ok := v["supported"].(bool); ok {
			return sup
		}
	}
	return false
}

func (a *anthropicAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = anthropicBaseURL
	}
	// Anthropic requires max_tokens (returns 400 if missing). Keep
	// the 8192 default for caller-omitted/0; honor positive caller
	// value when supplied.
	maxTokens := 8192
	if v, ok := input["max_tokens"]; ok {
		if mt := int(toFloat(v)); mt > 0 {
			maxTokens = mt
		}
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   convertAnthropicMessages(input),
		"max_tokens": maxTokens,
	}
	if v, ok := input["temperature"]; ok {
		payload["temperature"] = v
	}
	// D12 — request-side tool support. Convert the OpenAI-shaped tools /
	// tool_choice to Anthropic's shape. Omit both when tool_choice is
	// "none" or no tools were supplied (zero behavior change for
	// tool-free Anthropic requests).
	applyAnthropicTools(payload, input)
	out, err := postJSON(ctx, a.client, base+"/v1/messages",
		map[string]string{
			"x-api-key":         secret,
			"anthropic-version": "2023-06-01",
		},
		payload,
	)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	if u, ok := out["usage"].(map[string]any); ok {
		usage.InputTokens = int(toFloat(u["input_tokens"]))
		usage.OutputTokens = int(toFloat(u["output_tokens"]))
	}
	return out, usage, nil
}

func (a *anthropicAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "claude-3-5-sonnet-20241022",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

// Stream — Phase 1c-anthropic. Closes D-PHASE-1C-ANTHROPIC. Anthropic's
// /v1/messages SSE format differs from OpenAI's /v1/chat/completions
// (separate event names, content_block_delta with text_delta vs
// thinking_delta, message_delta carries usage+stop_reason); the
// per-event mapping lives in anthropic_streamer.go.
func (a *anthropicAdapter) Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = anthropicBaseURL
	}
	// Anthropic API REQUIRES max_tokens (returns 400 if missing). The
	// max_tokens-policy fix at the SDK + gateway-handler layer strips
	// 0/missing values upstream of us; if we still don't see one here,
	// fall back to 8192 default to avoid a hard 400 from Anthropic.
	maxTokens := 8192
	if v, ok := input["max_tokens"]; ok {
		if mt := int(toFloat(v)); mt > 0 {
			maxTokens = mt
		}
	}
	body := map[string]any{
		"model":      modelName,
		"messages":   convertAnthropicMessages(input),
		"max_tokens": maxTokens,
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	if v, ok := input["system"]; ok {
		body["system"] = v
	}
	// D12 — request-side tool support. Convert the OpenAI-shaped tools /
	// tool_choice to Anthropic's shape. Omit both when tool_choice is
	// "none" or no tools were supplied (zero behavior change for
	// tool-free Anthropic requests).
	applyAnthropicTools(body, input)
	resp, err := openAnthropicStream(ctx, a.client, base, secret, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return streamAnthropicSSE(ctx, resp.Body, emit)
}

// SupportsTools — true (Phase K21-B / D12). anthropicAdapter.Stream and
// .Invoke convert the OpenAI-shaped `tools` / `tool_choice` / tool-result
// `messages` into Anthropic's /v1/messages shape (see anthropic_tools.go),
// and the streamer parse-side already maps tool_use blocks → ToolCallEvent.
// With both sides wired, the handler may forward tools/tool_choice to this
// adapter; no first-class provider rejects tools any more.
func (a *anthropicAdapter) SupportsTools() bool { return true }

// ── Ollama adapter ────────────────────────────────────────────────────────────

type ollamaAdapter struct {
	client *http.Client
}

const ollamaDefaultBase = "http://localhost:11434"

func (a *ollamaAdapter) ListModels(ctx context.Context, endpointBaseURL, _ string) ([]ModelInventory, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = ollamaDefaultBase
	}
	// Ollama exposes GET /api/tags to list local models
	out, err := getJSON(ctx, a.client, base+"/api/tags", nil)
	if err != nil {
		return nil, fmt.Errorf("list models: %w", err)
	}
	// Response: {"models": [{"name": "llama3:latest", "size": N, "parameter_size": "8B", ...}]}
	var models []ModelInventory
	if mList, ok := out["models"].([]any); ok {
		for _, item := range mList {
			m, ok := item.(map[string]any)
			if !ok {
				continue
			}
			name, _ := m["name"].(string)
			if name == "" {
				continue
			}
			cap := "chat"
			if strings.Contains(name, "embed") {
				cap = "embedding"
			}
			inv := ModelInventory{
				ProviderModelName: name,
				CapabilityFlags:   map[string]any{"_capability": cap, "_display_name": name},
			}
			models = append(models, inv)
		}
	}
	return models, nil
}

func (a *ollamaAdapter) Invoke(ctx context.Context, endpointBaseURL, _ string, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = ollamaDefaultBase
	}
	payload := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
		"stream":   false,
	}
	options := map[string]any{}
	if v, ok := input["temperature"]; ok {
		options["temperature"] = v
	}
	// Policy: include num_predict (Ollama's max_tokens equivalent)
	// only on positive caller value. Caller-omitted / 0 → Ollama
	// streams to natural stop.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		options["num_predict"] = v
	}
	if len(options) > 0 {
		payload["options"] = options
	}
	out, err := postJSON(ctx, a.client, base+"/api/chat", nil, payload)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	usage.InputTokens = int(toFloat(out["prompt_eval_count"]))
	usage.OutputTokens = int(toFloat(out["eval_count"]))
	return out, usage, nil
}

func (a *ollamaAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

// Stream — Ollama supports streaming via its OpenAI-compatible
// /v1/chat/completions endpoint (separate from the /api/chat NDJSON path
// used by Invoke). This implementation uses the OpenAI-compat path so it
// shares the SSE parser with openai/lm_studio.
func (a *ollamaAdapter) Stream(ctx context.Context, endpointBaseURL, _ string, modelName string, input map[string]any, emit EmitFn) error {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = ollamaDefaultBase
	}
	body := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	// Policy: max_tokens=0 means omit (let the model decide). Phase 3c
	// enforced at SDK + gateway-handler; this is the final guard for
	// callers posting directly to /internal/proxy or future SDKs.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		body["max_tokens"] = v
	}
	// Ollama's OpenAI-compat endpoint forwards tools / tool_choice.
	if v, ok := input["tools"]; ok {
		body["tools"] = v
	}
	if v, ok := input["tool_choice"]; ok {
		body["tool_choice"] = v
	}
	forwardOptionalChatFields(input, body)
	resp, err := openCompletionStream(ctx, a.client, base+"/v1/chat/completions", nil, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return streamOpenAICompat(ctx, resp.Body, emit)
}

// SupportsTools — Ollama's OpenAI-compat endpoint supports tools + tool_choice.
func (a *ollamaAdapter) SupportsTools() bool { return true }

// ── LM Studio adapter (OpenAI-compatible) ────────────────────────────────────

type lmStudioAdapter struct {
	client *http.Client
}

const lmStudioDefaultBase = "http://localhost:1234"

// NormalizeLmStudioBase strips the trailing slash AND a trailing "/v1" segment.
// Users frequently paste full OpenAI-style URLs like http://localhost:1234/v1
// into the ProvidersTab UI, but the adapter appends "/v1/chat/completions" or
// "/api/v1/models" itself. Without normalization the request becomes
// /v1/v1/chat/completions which 404s and LM Studio returns {"error": ...} body
// that downstream extract_content() can't parse. Empty input → default base.
//
// Exported so the transparent proxy in api/server.go (doProxy) can apply the
// same normalization — the proxy builds URLs as `baseURL + "/" + targetPath`
// where targetPath already starts with "v1/...", so the same /v1/v1/ duplication
// happens via that code path too.
func NormalizeLmStudioBase(endpointBaseURL string) string {
	base := strings.TrimRight(endpointBaseURL, "/")
	base = strings.TrimSuffix(base, "/v1")
	if base == "" {
		return lmStudioDefaultBase
	}
	return base
}

func (a *lmStudioAdapter) ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error) {
	base := NormalizeLmStudioBase(endpointBaseURL)
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	// Try LM Studio native API first (richer data: context_length, type, capabilities)
	// GET /api/v1/models → {"models": [{key, type, display_name, max_context_length, ...}]}
	out, err := getJSON(ctx, a.client, base+"/api/v1/models", headers)
	if err == nil {
		if mList, ok := out["models"].([]any); ok && len(mList) > 0 {
			return parseLMStudioNativeModels(mList), nil
		}
	}
	// Fallback to OpenAI-compatible GET /v1/models → {"data": [{id, ...}]}
	out, err = getJSON(ctx, a.client, base+"/v1/models", headers)
	if err != nil {
		return nil, fmt.Errorf("list models: %w", err)
	}
	var models []ModelInventory
	if data, ok := out["data"].([]any); ok {
		for _, item := range data {
			m, ok := item.(map[string]any)
			if !ok {
				continue
			}
			id, _ := m["id"].(string)
			if id == "" {
				continue
			}
			models = append(models, ModelInventory{
				ProviderModelName: id,
				CapabilityFlags:   map[string]any{"_capability": "chat", "_display_name": id},
			})
		}
	}
	return models, nil
}

func parseLMStudioNativeModels(mList []any) []ModelInventory {
	var models []ModelInventory
	for _, item := range mList {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		key, _ := m["key"].(string)
		if key == "" {
			continue
		}
		modelType, _ := m["type"].(string)
		displayName, _ := m["display_name"].(string)
		if displayName == "" {
			displayName = key
		}
		var ctxLen *int
		if mcl, ok := m["max_context_length"].(float64); ok && mcl > 0 {
			v := int(mcl)
			ctxLen = &v
		}
		cap := "chat"
		if modelType == "embedding" || modelType == "text-embedding" {
			cap = "embedding"
		} else if strings.Contains(modelType, "rerank") || strings.Contains(key, "rerank") {
			// C2 (BL-2): canonical `rerank` token (was the divergent `reranker`), so a
			// rerank model discovered via LM Studio inventory matches the picker filter.
			cap = "rerank"
		}
		flags := map[string]any{
			"_capability":   cap,
			"_display_name": displayName,
		}
		if cap == "rerank" {
			// canonical boolean flag → capability_flags @> {"rerank":true} also matches
			flags["rerank"] = true
		}
		// Parse capabilities from LM Studio native format
		if caps, ok := m["capabilities"].(map[string]any); ok {
			if v, ok := caps["vision"].(bool); ok && v {
				flags["vision"] = true
			}
			if v, ok := caps["trained_for_tool_use"].(bool); ok && v {
				flags["tool_use"] = true
			}
		}
		if params, ok := m["params_string"].(string); ok && params != "" {
			flags["_params"] = params
		}
		models = append(models, ModelInventory{
			ProviderModelName: key,
			ContextLength:     ctxLen,
			CapabilityFlags:   flags,
		})
	}
	return models
}

func (a *lmStudioAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := NormalizeLmStudioBase(endpointBaseURL)
	payload := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	// Policy: include max_tokens only on positive caller value. Caller-
	// omitted / 0 → let the model decide. LM Studio accepts requests
	// without max_tokens (defaults to model's natural stop).
	if v, ok := input["max_tokens"]; ok {
		if mt := int(toFloat(v)); mt > 0 {
			payload["max_tokens"] = mt
		}
	}
	if v, ok := input["temperature"]; ok {
		payload["temperature"] = v
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	out, err := postJSON(ctx, a.client, base+"/v1/chat/completions", headers, payload)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	if u, ok := out["usage"].(map[string]any); ok {
		usage.InputTokens = int(toFloat(u["prompt_tokens"]))
		usage.OutputTokens = int(toFloat(u["completion_tokens"]))
	}
	return out, usage, nil
}

func (a *lmStudioAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

// Stream — LM Studio is OpenAI-compatible on /v1/chat/completions, so this
// delegates to the shared streamOpenAICompat parser. Uses NormalizeLmStudioBase
// to strip a possible trailing /v1 (mirrors Invoke).
func (a *lmStudioAdapter) Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error {
	base := NormalizeLmStudioBase(endpointBaseURL)
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	body := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	// Policy: max_tokens=0 means omit (let the model decide). Phase 3c
	// enforced at SDK + gateway-handler; this is the final guard for
	// callers posting directly to /internal/proxy or future SDKs.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		body["max_tokens"] = v
	}
	// LM Studio's OpenAI-compat endpoint forwards tools / tool_choice —
	// the Phase 0b PoC path for the L3 zone classifier.
	if v, ok := input["tools"]; ok {
		body["tools"] = v
	}
	if v, ok := input["tool_choice"]; ok {
		body["tool_choice"] = v
	}
	forwardOptionalChatFields(input, body)
	resp, err := openCompletionStream(ctx, a.client, base+"/v1/chat/completions", headers, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return streamOpenAICompat(ctx, resp.Body, emit)
}

// SupportsTools — LM Studio's OpenAI-compat endpoint supports tools + tool_choice.
func (a *lmStudioAdapter) SupportsTools() bool { return true }

// ── factory ───────────────────────────────────────────────────────────────────

func ResolveAdapter(providerKind string, client *http.Client) (Adapter, error) {
	switch providerKind {
	case "openai":
		return &openaiAdapter{
			client:          client,
			staticInventory: loadPreconfig(openaiPreconfigJSON),
		}, nil
	case "anthropic":
		return &anthropicAdapter{
			client:          client,
			staticInventory: loadPreconfig(anthropicPreconfigJSON),
		}, nil
	case "ollama":
		return &ollamaAdapter{client: client}, nil
	case "lm_studio":
		return &lmStudioAdapter{client: client}, nil
	default:
		// Custom providers: use OpenAI-compatible adapter with empty inventory
		// (user adds models manually or inventory syncs via /v1/models endpoint)
		return &openaiAdapter{
			client:          client,
			staticInventory: []ModelInventory{},
		}, nil
	}
}

func toFloat(v any) float64 {
	if v == nil {
		return 0
	}
	switch x := v.(type) {
	case float64:
		return x
	case int:
		return float64(x)
	case int64:
		return float64(x)
	}
	return 0
}
