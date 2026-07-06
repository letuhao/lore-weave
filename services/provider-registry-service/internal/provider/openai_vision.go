package provider

import (
	"context"
	"strings"
)

// openai_vision.go — PDF-import vision op (docs/specs/2026-07-06-pdf-book-import.md
// L5) OpenAI implementation of the image-captioning adapter method.
// Ollama/LM-Studio implementations live in local_vision.go (same
// OpenAI-compatible wire shape, shared via openai_compat_vision.go);
// Anthropic's structurally different Messages-API shape lives in
// anthropic_vision.go.
//
// Wire shape: a one-shot (non-streaming) multimodal chat completion —
//
//	POST /v1/chat/completions
//	{"model": ..., "messages": [{"role":"user","content":[
//	    {"type":"text","text":prompt},
//	    {"type":"image_url","image_url":{"url":"data:{mime};base64,{b64}"}}
//	]}]}
//
// https://platform.openai.com/docs/guides/vision
//
// This is a DEDICATED adapter method (not smuggled through the generic
// Invoke/Stream chat paths) so the operation is independently gated,
// tested, and cost-estimated — mirroring how GenerateImage/GenerateVideo/
// GenerateAudio each get their own method rather than reusing chat.

// CaptionImage — OpenAI-compatible vision captioning.
func (a *openaiAdapter) CaptionImage(
	ctx context.Context,
	endpointBaseURL, secret, modelName string,
	input CaptionImageInput,
) (CaptionImageOutput, Usage, error) {
	if err := validateCaptionImageInput(input); err != nil {
		return CaptionImageOutput{}, Usage{}, err
	}
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	body := buildOpenAICompatVisionBody(modelName, input)
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	return postOpenAICompatVision(ctx, a.client, base, headers, body)
}
