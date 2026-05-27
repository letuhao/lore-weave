package provider

import "context"

// adapters_video.go — Phase 5d stubs for the non-OpenAI adapters. None
// of these providers expose an OpenAI-compatible video generation
// endpoint via their public API, so they uniformly return
// ErrOperationNotSupported:
//
//   - Anthropic: no video generation API
//   - Ollama: doesn't expose video gen through its OpenAI-compat layer
//   - LM Studio: per-model GUI generation only; no video API
//
// If any provider adds OpenAI-compat video gen later, swap the stub
// for a real implementation in a follow-up cycle.

func (a *anthropicAdapter) GenerateVideo(
	_ context.Context,
	_, _, _ string,
	_ GenerateVideoInput,
) (GenerateVideoOutput, Usage, error) {
	return GenerateVideoOutput{}, Usage{}, ErrOperationNotSupported
}

func (a *ollamaAdapter) GenerateVideo(
	_ context.Context,
	_, _, _ string,
	_ GenerateVideoInput,
) (GenerateVideoOutput, Usage, error) {
	return GenerateVideoOutput{}, Usage{}, ErrOperationNotSupported
}

func (a *lmStudioAdapter) GenerateVideo(
	_ context.Context,
	_, _, _ string,
	_ GenerateVideoInput,
) (GenerateVideoOutput, Usage, error) {
	return GenerateVideoOutput{}, Usage{}, ErrOperationNotSupported
}
