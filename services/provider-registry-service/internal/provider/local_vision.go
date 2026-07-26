package provider

import (
	"context"
)

// local_vision.go — PDF-import vision op (docs/specs/2026-07-06-pdf-book-import.md
// L5) Ollama + LM Studio implementations. Both serve chat completions over
// the SAME OpenAI-compatible `/v1/chat/completions` endpoint OpenAI itself
// uses (see ollamaAdapter.Stream's doc comment and lmStudioAdapter.Invoke,
// adapters.go) — a vision-capable local model (llava, qwen2-vl, gemma-3/4
// vision variants, moondream, ...) accepts the identical multimodal
// `image_url` content-block shape. Whether captioning actually succeeds
// depends entirely on the LOADED model supporting vision — same posture
// as every other adapter method here: the adapter doesn't pre-flight the
// model's capability_flags (no such gate exists anywhere else in this
// package either, e.g. GenerateImage/GenerateVideo), it lets the upstream
// reject an unsupported request and the error classifies to
// LLM_UPSTREAM_ERROR like any other bad request.
//
// /review-impl 2026-07-06: replaces the original stub
// (ErrOperationNotSupported) — LM Studio's own model-inventory parsing
// (parseLMStudioNativeModels) already detects+flags `capability_flags.
// vision` for a loaded vision model (e.g. google/gemma-4-26b-a4b-qat), so
// the capability was already discoverable in this codebase; captioning
// just wasn't wired to it.

// CaptionImage — Ollama, via its OpenAI-compatible /v1/chat/completions
// endpoint. Requires a vision-capable model to be loaded/pulled (e.g.
// llava, qwen2-vl, gemma3); a text-only model's upstream rejection
// classifies to LLM_UPSTREAM_ERROR like any other bad request.
func (a *ollamaAdapter) CaptionImage(
	ctx context.Context,
	endpointBaseURL, _, modelName string,
	input CaptionImageInput,
) (CaptionImageOutput, Usage, error) {
	if err := validateCaptionImageInput(input); err != nil {
		return CaptionImageOutput{}, Usage{}, err
	}
	base := endpointBaseURL
	if base == "" {
		base = ollamaDefaultBase
	}
	body := buildOpenAICompatVisionBody(modelName, input)
	return postOpenAICompatVision(ctx, a.client, base, nil, body)
}

// CaptionImage — LM Studio, via its OpenAI-compatible /v1/chat/completions
// endpoint. Requires a vision-capable model to be loaded (e.g.
// google/gemma-4-26b-a4b-qat, llava, qwen2-vl); LM Studio's own
// model-inventory parsing already flags such models with
// capability_flags.vision (parseLMStudioNativeModels, adapters.go).
func (a *lmStudioAdapter) CaptionImage(
	ctx context.Context,
	endpointBaseURL, secret, modelName string,
	input CaptionImageInput,
) (CaptionImageOutput, Usage, error) {
	if err := validateCaptionImageInput(input); err != nil {
		return CaptionImageOutput{}, Usage{}, err
	}
	base := NormalizeLmStudioBase(endpointBaseURL)
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	body := buildOpenAICompatVisionBody(modelName, input)
	return postOpenAICompatVision(ctx, a.client, base, headers, body)
}
