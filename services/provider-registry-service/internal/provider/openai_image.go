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

// openai_image.go — Phase 5c-α OpenAI implementation of the image-gen
// adapter method. Stub versions for non-OpenAI adapters live in
// adapters_image.go.
//
// Wire-shape reference:
//   POST /v1/images/generations
//   https://platform.openai.com/docs/api-reference/images/create
//
// Same OpenAI-compatible shape is consumed by the sibling
// local-image-generator-service (ComfyUI backend) at port 8700 — see
// G:\Works\local-image-generator-service\docs\EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md.

// GenerateImage — OpenAI image generation. Phase 5c-α implementation.
//
// Flow:
//  1. Adapter-level invariant pre-checks (Prompt non-empty;
//     N ≤ MaxImagesPerJob; ResponseFormat in {"", "url", "b64_json"}).
//     Belt-and-suspenders matching Phase 5b's MaxAudioBytes pattern.
//  2. Build JSON body, omitting unset fields so upstream defaults
//     apply (DALL-E-3 ignores `n>1`, gpt-image-1 ignores `style`, etc.).
//  3. POST to {base}/v1/images/generations with Bearer auth.
//  4. On non-2xx: JSON-first content-policy detection (Fix #3) →
//     ErrImageContentPolicy; otherwise ClassifyUpstreamHTTP → typed
//     transient/permanent/rate-limited.
//  5. On 2xx: parse {created, data[]} → GenerateImageOutput.
//
// Response body capped at MaxImageResponseBytes (Fix #6) — larger
// upstream responses are rejected with ErrImageGenerationFailed before
// JSON parsing so a malicious upstream can't OOM the worker via
// arbitrarily large b64 payloads.
func (a *openaiAdapter) GenerateImage(
	ctx context.Context,
	endpointBaseURL, secret, modelName string,
	input GenerateImageInput,
) (GenerateImageOutput, Usage, error) {
	// /review-impl(DESIGN) MED#5 — adapter-level invariant pre-checks.
	// Handler also enforces; adapter is the last line of defense for
	// non-handler callers (cron, future RabbitMQ submit path, background
	// re-runs).
	if input.Prompt == "" {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf(
			"%w: prompt required", ErrImageInvalidParams)
	}
	if input.N > MaxImagesPerJob {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf(
			"%w: n=%d exceeds cap %d", ErrImageInvalidParams, input.N, MaxImagesPerJob)
	}
	if input.N < 0 {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf(
			"%w: n=%d must be >= 0", ErrImageInvalidParams, input.N)
	}
	if input.ResponseFormat != "" && input.ResponseFormat != "url" && input.ResponseFormat != "b64_json" {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf(
			"%w: response_format=%q (allowed: url, b64_json)",
			ErrImageInvalidParams, input.ResponseFormat)
	}

	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}

	body := map[string]any{
		"model":  modelName,
		"prompt": input.Prompt,
	}
	if input.Size != "" {
		body["size"] = input.Size
	}
	if input.N > 0 {
		body["n"] = input.N
	}
	if input.ResponseFormat != "" {
		body["response_format"] = input.ResponseFormat
	}
	if input.Quality != "" {
		body["quality"] = input.Quality
	}
	if input.Style != "" {
		body["style"] = input.Style
	}
	if input.Background != "" {
		body["background"] = input.Background
	}

	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf("marshal image-gen body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		base+"/v1/images/generations", bytes.NewReader(bodyBytes))
	if err != nil {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if secret != "" {
		req.Header.Set("Authorization", "Bearer "+secret)
	}

	resp, err := a.client.Do(req)
	if err != nil {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf("upstream transport: %w", err)
	}
	defer resp.Body.Close()

	// /review-impl(DESIGN) LOW#6 — named cap. Read up to cap+1 to detect
	// overflow; ReadAll under a LimitReader stops at the cap and we
	// don't get a partial body for typed-error classification (so we
	// signal overflow as ErrImageGenerationFailed).
	respBytes, _ := io.ReadAll(io.LimitReader(resp.Body, MaxImageResponseBytes+1))
	if len(respBytes) > MaxImageResponseBytes {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf(
			"%w: upstream response exceeds %d bytes",
			ErrImageGenerationFailed, MaxImageResponseBytes)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		// /review-impl(DESIGN) MED#3 — content-policy JSON-first;
		// avoids false-positive from prompt echo in error message.
		if isContentPolicyRejection(resp.StatusCode, respBytes) {
			return GenerateImageOutput{}, Usage{}, fmt.Errorf(
				"%w: %s", ErrImageContentPolicy,
				truncateBody(string(respBytes), 4096))
		}
		retryAfter := parseRetryAfter(resp.Header.Get("Retry-After"))
		return GenerateImageOutput{}, Usage{},
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
		return GenerateImageOutput{}, Usage{}, fmt.Errorf(
			"decode image-gen response: %w (body=%s)", err, truncateBody(string(respBytes), 1024))
	}
	if len(parsed.Data) == 0 {
		return GenerateImageOutput{}, Usage{}, fmt.Errorf(
			"%w: upstream returned no images", ErrImageGenerationFailed)
	}

	out := GenerateImageOutput{
		Created: parsed.Created,
		Data:    make([]GeneratedImage, len(parsed.Data)),
	}
	for i, d := range parsed.Data {
		out.Data[i] = GeneratedImage{
			URL:           d.URL,
			B64JSON:       d.B64JSON,
			RevisedPrompt: d.RevisedPrompt,
		}
	}
	return out, Usage{}, nil
}

// isContentPolicyRejection is shared between openai_image.go and
// openai_video.go — defined in openai_content_policy.go (Phase 5d
// refactor per /review-impl(DESIGN) Fix #4).
