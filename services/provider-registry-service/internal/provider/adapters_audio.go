package provider

import "context"

// adapters_audio.go — Phase 5a stubs for the Transcribe + Speak
// methods. Each adapter that doesn't yet have a real implementation
// returns ErrOperationNotSupported. As real audio support lands, the
// stubs are replaced with provider-specific implementations (e.g.
// OpenAI Transcribe + Speak land in openai_audio.go).
//
// Anthropic / Ollama / LM Studio: no audio API in this cycle. LM Studio
// can in principle host whisper.cpp + Kokoro-TTS, but the upstream HTTP
// shape varies by user-loaded model — defer until a user requests it.

// ── OpenAI ─────────────────────────────────────────────────────────────
// Transcribe + Speak both live in openai_audio.go (Phase 5a T5/T8).

// ── Anthropic ─────────────────────────────────────────────────────────

func (a *anthropicAdapter) Transcribe(_ context.Context, _, _, _ string, _ TranscribeInput) (TranscribeOutput, Usage, error) {
	return TranscribeOutput{}, Usage{}, ErrOperationNotSupported
}

func (a *anthropicAdapter) Speak(_ context.Context, _, _, _ string, _ SpeakInput, _ AudioEmitFn) error {
	return ErrOperationNotSupported
}

// Phase 5e-β.2 — GenerateAudio stub.
func (a *anthropicAdapter) GenerateAudio(_ context.Context, _, _, _ string, _ GenerateAudioInput) (GenerateAudioOutput, Usage, error) {
	return GenerateAudioOutput{}, Usage{}, ErrOperationNotSupported
}

// ── Ollama ────────────────────────────────────────────────────────────

func (a *ollamaAdapter) Transcribe(_ context.Context, _, _, _ string, _ TranscribeInput) (TranscribeOutput, Usage, error) {
	return TranscribeOutput{}, Usage{}, ErrOperationNotSupported
}

func (a *ollamaAdapter) Speak(_ context.Context, _, _, _ string, _ SpeakInput, _ AudioEmitFn) error {
	return ErrOperationNotSupported
}

func (a *ollamaAdapter) GenerateAudio(_ context.Context, _, _, _ string, _ GenerateAudioInput) (GenerateAudioOutput, Usage, error) {
	return GenerateAudioOutput{}, Usage{}, ErrOperationNotSupported
}

// ── LM Studio ─────────────────────────────────────────────────────────

func (a *lmStudioAdapter) Transcribe(_ context.Context, _, _, _ string, _ TranscribeInput) (TranscribeOutput, Usage, error) {
	return TranscribeOutput{}, Usage{}, ErrOperationNotSupported
}

func (a *lmStudioAdapter) Speak(_ context.Context, _, _, _ string, _ SpeakInput, _ AudioEmitFn) error {
	return ErrOperationNotSupported
}

func (a *lmStudioAdapter) GenerateAudio(_ context.Context, _, _, _ string, _ GenerateAudioInput) (GenerateAudioOutput, Usage, error) {
	return GenerateAudioOutput{}, Usage{}, ErrOperationNotSupported
}
