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

// anthropic_vision.go — PDF-import vision op (docs/specs/2026-07-06-
// pdf-book-import.md L5) Anthropic implementation of the image-captioning
// adapter method. Anthropic's Messages API uses a STRUCTURALLY DIFFERENT
// wire shape from OpenAI's `image_url` content block — an `image` block
// with a base64 `source` — so this does not share
// openai_compat_vision.go's builder/parser; those are OpenAI-wire-shape
// specific (OpenAI/Ollama/LM-Studio).
//
// https://docs.anthropic.com/en/docs/build-with-claude/vision
//
// /review-impl 2026-07-06: replaces the original stub
// (ErrOperationNotSupported) — Claude 3+ vision models ARE supported by
// this codebase already (parseAnthropicModels, adapters.go, sets
// capability_flags.vision from the models-list `capabilities.image_input`
// field); convertAnthropicMessages passes a content-block array through
// unchanged, so this only needed its own request builder + response
// parser, not a new message-conversion path.

// CaptionImage — Anthropic Messages API vision captioning. Requires a
// vision-capable model (Claude 3+ all support it); Anthropic recommends
// placing the image block before the text block for best results.
func (a *anthropicAdapter) CaptionImage(
	ctx context.Context,
	endpointBaseURL, secret, modelName string,
	input CaptionImageInput,
) (CaptionImageOutput, Usage, error) {
	if err := validateCaptionImageInput(input); err != nil {
		return CaptionImageOutput{}, Usage{}, err
	}
	mimeType := input.MimeType
	if mimeType == "" {
		mimeType = "image/png"
	}
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = anthropicBaseURL
	}

	// Anthropic requires max_tokens (400s without it) — same fallback
	// default as Invoke/Stream's anthropicAdapter methods, but a caption
	// should be short, so a smaller ceiling than chat's 8192 default is
	// used when the caller didn't specify one.
	maxTokens := 300
	if input.MaxTokens > 0 {
		maxTokens = input.MaxTokens
	}

	body := map[string]any{
		"model":      modelName,
		"max_tokens": maxTokens,
		"messages": []map[string]any{
			{
				"role": "user",
				"content": []map[string]any{
					{
						"type": "image",
						"source": map[string]any{
							"type":       "base64",
							"media_type": mimeType,
							"data":       input.ImageB64,
						},
					},
					{"type": "text", "text": input.Prompt},
				},
			},
		},
	}

	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf("marshal vision body: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/v1/messages", bytes.NewReader(bodyBytes))
	if err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", secret)
	req.Header.Set("anthropic-version", "2023-06-01")

	resp, err := a.client.Do(req)
	if err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf("upstream transport: %w", err)
	}
	defer resp.Body.Close()

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
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
		StopReason string `json:"stop_reason"`
		Usage      struct {
			InputTokens  int `json:"input_tokens"`
			OutputTokens int `json:"output_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(respBytes, &parsed); err != nil {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf(
			"decode vision response: %w (body=%s)", err, truncateBody(string(respBytes), 1024))
	}

	var caption string
	for _, block := range parsed.Content {
		if block.Type == "text" && strings.TrimSpace(block.Text) != "" {
			caption = block.Text
			break
		}
	}
	if caption == "" {
		return CaptionImageOutput{}, Usage{}, fmt.Errorf(
			"%w: upstream returned no caption", ErrVisionCaptionFailed)
	}

	usage := Usage{
		InputTokens:  parsed.Usage.InputTokens,
		OutputTokens: parsed.Usage.OutputTokens,
	}
	return CaptionImageOutput{
		Caption:      caption,
		FinishReason: parsed.StopReason,
	}, usage, nil
}
