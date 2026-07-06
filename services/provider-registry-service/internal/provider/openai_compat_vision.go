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

// openai_compat_vision.go — PDF-import vision op (docs/specs/2026-07-06-
// pdf-book-import.md L5) shared request/response plumbing for every
// adapter whose vision-capable models are served over the SAME
// OpenAI-compatible `/v1/chat/completions` multimodal wire shape:
// OpenAI itself, Ollama (its OpenAI-compat endpoint — see
// ollamaAdapter.Stream's doc comment, adapters.go), and LM Studio (fully
// OpenAI-compatible by design). Anthropic uses a structurally different
// wire shape (Messages API image content blocks) and has its own
// implementation in anthropic_vision.go.
//
// /review-impl 2026-07-06 finding: the original implementation stubbed
// Ollama/LM-Studio as ErrOperationNotSupported on the mistaken assumption
// that local-backend vision support was uncertain. It isn't — LM Studio's
// own model-inventory parsing (parseLMStudioNativeModels, adapters.go)
// already detects and flags `capability_flags.vision` for a loaded
// vision-capable model (e.g. google/gemma-4-26b-a4b-qat), and both
// adapters already serve chat over the identical OpenAI-compatible
// endpoint used here for OpenAI itself. The capability existed in the
// codebase's own model metadata; captioning just hadn't been wired to it.

// validateCaptionImageInput — shared adapter-level invariant pre-checks,
// belt-and-suspenders with handler-level validateVisionInput. Every
// CaptionImage implementation calls this first.
func validateCaptionImageInput(input CaptionImageInput) error {
	if strings.TrimSpace(input.Prompt) == "" {
		return fmt.Errorf("%w: prompt required", ErrVisionInvalidParams)
	}
	if input.ImageB64 == "" {
		return fmt.Errorf("%w: image required", ErrVisionInvalidParams)
	}
	if len(input.ImageB64) > MaxVisionInputImageBytes {
		return fmt.Errorf("%w: image exceeds %d-byte cap (got %d)",
			ErrVisionInvalidParams, MaxVisionInputImageBytes, len(input.ImageB64))
	}
	return nil
}

// buildOpenAICompatVisionBody builds the multimodal chat-completions body
// shared by OpenAI/Ollama/LM-Studio — a single user message with a
// {type:"text"} block followed by a {type:"image_url"} data-URI block.
func buildOpenAICompatVisionBody(modelName string, input CaptionImageInput) map[string]any {
	mimeType := input.MimeType
	if mimeType == "" {
		mimeType = "image/png"
	}
	dataURL := fmt.Sprintf("data:%s;base64,%s", mimeType, input.ImageB64)
	body := map[string]any{
		"model": modelName,
		"messages": []map[string]any{
			{
				"role": "user",
				"content": []map[string]any{
					{"type": "text", "text": input.Prompt},
					{"type": "image_url", "image_url": map[string]any{"url": dataURL}},
				},
			},
		},
	}
	if input.MaxTokens > 0 {
		body["max_tokens"] = input.MaxTokens
	}
	return body
}

// postOpenAICompatVision POSTs an already-built body to {base}/v1/chat/
// completions and parses an OpenAI-compatible chat-completions response
// into (CaptionImageOutput, Usage). Shared POST/cap/classify/parse logic
// for OpenAI/Ollama/LM-Studio — only the base URL and headers differ per
// adapter.
func postOpenAICompatVision(
	ctx context.Context, client *http.Client, base string, headers map[string]string, body map[string]any,
) (CaptionImageOutput, Usage, error) {
	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf("marshal vision body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		strings.TrimRight(base, "/")+"/v1/chat/completions", bytes.NewReader(bodyBytes))
	if err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := client.Do(req)
	if err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf("upstream transport: %w", err)
	}
	defer resp.Body.Close()

	// MaxImageResponseBytes is reused here (8MB) — a caption response is
	// tiny text, but bounding the read still guards against a
	// misbehaving/malicious upstream sending an oversized body.
	respBytes, _ := io.ReadAll(io.LimitReader(resp.Body, MaxImageResponseBytes+1))
	if len(respBytes) > MaxImageResponseBytes {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf(
			"%w: upstream response exceeds %d bytes",
			ErrVisionCaptionFailed, MaxImageResponseBytes)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		retryAfter := parseRetryAfter(resp.Header.Get("Retry-After"))
		return CaptionImageOutput{}, Usage{},
			ClassifyUpstreamHTTP(resp.StatusCode, string(respBytes), retryAfter)
	}

	var parsed struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
		} `json:"choices"`
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(respBytes, &parsed); err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf(
			"decode vision response: %w (body=%s)", err, truncateBody(string(respBytes), 1024))
	}
	if len(parsed.Choices) == 0 || strings.TrimSpace(parsed.Choices[0].Message.Content) == "" {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf(
			"%w: upstream returned no caption", ErrVisionCaptionFailed)
	}

	usage := Usage{
		InputTokens:  parsed.Usage.PromptTokens,
		OutputTokens: parsed.Usage.CompletionTokens,
	}
	return CaptionImageOutput{
		Caption:      parsed.Choices[0].Message.Content,
		FinishReason: parsed.Choices[0].FinishReason,
	}, usage, nil
}
