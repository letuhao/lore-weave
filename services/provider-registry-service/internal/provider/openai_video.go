package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// openai_video.go — Phase 5d OpenAI-compatible implementation of the
// video-gen adapter method.
//
// **Path dispatch** (/review-impl(DESIGN) HIGH#1):
//   - InitImage == ""  → POST /v1/videos/generations/text-to-video
//   - InitImage != ""  → POST /v1/videos/generations/image-to-video
//
// Matches the actual local-image-generator-service routes at
// G:/Works/local-image-generator-service/app/api/videos.py:168,220.
// The integration guide's singular `/v1/video/generations` is
// aspirational and unimplemented in the only real backend we have.
//
// **Sync upstream mode**: no `mode: "async"` in the request body, so
// upstream defaults to sync mode and returns 200 with `{created, data}`
// inline (same shape as image_gen). Async upstream mode would return
// 202 + require us to poll upstream's GET endpoint — double-polling
// (our gateway's /v1/llm/jobs already polls above us). Wall-clock
// safety comes from worker_video.go's VideoGenJobTimeout=30min ctx.
//
// **Field name init_image** (not image): matches local-image-generator-
// service's VideoGenerateRequest field name.

const (
	videoUpstreamPathTxt2Vid = "/v1/videos/generations/text-to-video"
	videoUpstreamPathImg2Vid = "/v1/videos/generations/image-to-video"
)

// GenerateVideo — text-to-video or image-to-video generation.
//
// Pre-checks (adapter-level, belt-and-suspenders for non-handler callers):
//   - Prompt empty → ErrVideoInvalidParams("prompt required")
//   - N < 0 → ErrVideoInvalidParams (clearer phrasing for negative)
//   - N > 1 → ErrVideoInvalidParams (Phase 5d locks to n=1)
//   - ResponseFormat not "" or "url" → ErrVideoInvalidParams
//     (b64_json rejected; design MED#3)
//   - InitImage size > MaxImg2VidInputBytes → ErrVideoInvalidParams
//     (design MED#2)
//
// Response handling:
//   - Non-2xx with content-policy JSON → ErrVideoContentPolicy
//   - Non-2xx otherwise → typed upstream classifier
//   - 2xx → decode {created, data[{url, revised_prompt}]} → return first
//     entry (n=1 lock)
//   - Response body > MaxImageResponseBytes → ErrVideoGenerationFailed
//     (videos rarely fit; expected behavior)
func (a *openaiAdapter) GenerateVideo(
	ctx context.Context,
	endpointBaseURL, secret, modelName string,
	input GenerateVideoInput,
) (GenerateVideoOutput, Usage, error) {
	// /review-impl(DESIGN) MED#5 phrasing — clearer messages per error.
	// /review-impl(BUILD) LOW#6 cross-reference: handler-side validation
	// in jobs_handler.go::validateVideoGenInput mirrors these checks.
	// Belt-and-suspenders: handler catches caller-side validation early
	// (no DB insert, no goroutine spawn); adapter catches non-handler
	// callers (cron, future RabbitMQ submit path, background re-runs).
	// If the two layers ever drift, both adapter tests + handler tests
	// independently cover each case (see TestOpenAIAdapter_GenerateVideo_*
	// and TestInternalSubmitLlmJob_VideoGen_*).
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
	if base == "" {
		base = openaiBaseURL
	}

	// /review-impl(DESIGN) HIGH#1 — path dispatch based on init_image presence.
	// /review-impl(BUILD) LOW#2 — trim whitespace before the dispatch check;
	// otherwise " " or "\n" routes to image-to-video and upstream fails with
	// a confusing parse error. Trim is for the dispatch decision only; the
	// actual base64 sent upstream is the (trimmed) value too.
	trimmedInitImage := strings.TrimSpace(input.InitImage)
	var upstreamPath string
	if trimmedInitImage != "" {
		upstreamPath = videoUpstreamPathImg2Vid
	} else {
		upstreamPath = videoUpstreamPathTxt2Vid
	}

	body := map[string]any{
		"model":  modelName,
		"prompt": input.Prompt,
		"n":      1, // always 1 per Phase 5d lock
	}
	if input.Size != "" {
		body["size"] = input.Size
	}
	if input.Duration > 0 {
		body["duration"] = input.Duration
	}
	if input.ResponseFormat != "" {
		body["response_format"] = input.ResponseFormat
	}
	if input.Style != "" {
		body["style"] = input.Style
	}
	if trimmedInitImage != "" {
		// Field name `init_image` matches local-image-generator-service's
		// VideoGenerateRequest. NOT `image` per the stale guide.
		// Send the trimmed value so leading/trailing whitespace doesn't
		// confuse upstream base64 decode.
		body["init_image"] = trimmedInitImage
	}
	// NOTE: no "mode" field → upstream defaults to sync mode.

	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return GenerateVideoOutput{}, Usage{}, fmt.Errorf("marshal video-gen body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		base+upstreamPath, bytes.NewReader(bodyBytes))
	if err != nil {
		return GenerateVideoOutput{}, Usage{}, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if secret != "" {
		req.Header.Set("Authorization", "Bearer "+secret)
	}

	resp, err := a.client.Do(req)
	if err != nil {
		return GenerateVideoOutput{}, Usage{}, fmt.Errorf("upstream transport: %w", err)
	}
	defer resp.Body.Close()

	// Reuse MaxImageResponseBytes cap; videos that exceed get an
	// honest failure rather than buffered into worker memory.
	respBytes, _ := io.ReadAll(io.LimitReader(resp.Body, MaxImageResponseBytes+1))
	if len(respBytes) > MaxImageResponseBytes {
		return GenerateVideoOutput{}, Usage{}, fmt.Errorf(
			"%w: upstream response exceeds %d bytes",
			ErrVideoGenerationFailed, MaxImageResponseBytes)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		// Content-policy detection via shared helper (openai_content_policy.go).
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

	// Phase 5d locks to n=1 — take the first data entry. Most backends
	// only return 1 anyway; this normalization is defensive.
	out := GenerateVideoOutput{
		Created: parsed.Created,
		Data: []GeneratedVideo{{
			URL:           parsed.Data[0].URL,
			RevisedPrompt: parsed.Data[0].RevisedPrompt,
		}},
	}
	return out, Usage{}, nil
}
