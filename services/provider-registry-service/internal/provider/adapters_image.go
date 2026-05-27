package provider

import "context"

// adapters_image.go — Phase 5c-α stubs for the non-OpenAI adapters.
// None of these providers expose an OpenAI-compatible image generation
// endpoint via their public API, so they uniformly return
// ErrOperationNotSupported:
//
//   - Anthropic: no image-gen API at all (image input via vision models
//     is multimodal chat, not generation).
//   - Ollama: doesn't expose /v1/images/generations through its
//     OpenAI-compat layer; image-gen via Ollama runs through its
//     native /api/generate path with image-specific models, but
//     LoreWeave routes image-gen through the OpenAI-compat shape.
//   - LM Studio: per-model GUI generation only; no API endpoint.
//
// If any provider adds OpenAI-compat image-gen later, swap the stub for
// a real implementation in a follow-up cycle. The Adapter interface
// contract requires the method, so stubs are mandatory for build.

// GenerateImage — Anthropic does not support image generation.
func (a *anthropicAdapter) GenerateImage(
	_ context.Context,
	_, _, _ string,
	_ GenerateImageInput,
) (GenerateImageOutput, Usage, error) {
	return GenerateImageOutput{}, Usage{}, ErrOperationNotSupported
}

// GenerateImage — Ollama OpenAI-compat layer does not expose image generation.
func (a *ollamaAdapter) GenerateImage(
	_ context.Context,
	_, _, _ string,
	_ GenerateImageInput,
) (GenerateImageOutput, Usage, error) {
	return GenerateImageOutput{}, Usage{}, ErrOperationNotSupported
}

// GenerateImage — LM Studio does not support image generation via API.
func (a *lmStudioAdapter) GenerateImage(
	_ context.Context,
	_, _, _ string,
	_ GenerateImageInput,
) (GenerateImageOutput, Usage, error) {
	return GenerateImageOutput{}, Usage{}, ErrOperationNotSupported
}
