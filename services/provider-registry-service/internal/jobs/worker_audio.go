package jobs

// worker_audio.go — Phase 5a audio-job dispatch path.
//
// Routed from Worker.Process() when operation is in audioJobOperations.
// Runs adapter.Transcribe synchronously (no streaming, no chunking, no
// aggregator) → marshals provider.TranscribeOutput to SttResult shape →
// finalizes Job with result OR maps adapter error to LLM_* code.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// SttJobTimeout — Phase 5a /review-impl HIGH#1. Hard wall-clock cap on
// a single stt job: audio fetch + Whisper upstream combined. 5 min covers
// worst-case Whisper on max-size (25MB) audio. Without this cap the
// worker goroutine spawned with bgCtx=context.Background() would block
// forever on a slow audio_url (the invokeClient has no http.Timeout
// by design — chat streaming needs unbounded — so per-op caps live here).
const SttJobTimeout = 5 * time.Minute

// processAudioJob dispatches an audio-shaped job (currently only stt).
// Mirrors the layout of Process()'s creds-resolve + adapter-pick + decode
// pattern but feeds adapter.Transcribe instead of adapter.Stream.
func (w *Worker) processAudioJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation, modelSource string,
	modelRef uuid.UUID,
	input json.RawMessage,
	logger *slog.Logger,
) {
	providerKind, providerModelName, endpointBaseURL, secret, err := w.resolve(ctx, ownerUserID, modelRef, modelSource)
	if err != nil {
		logger.Error("resolve creds failed (audio)", "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, "LLM_MODEL_NOT_FOUND", err.Error(), "")
		return
	}

	adapter, err := w.adapter(providerKind)
	if err != nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, "LLM_PROVIDER_ROUTE_VIOLATION", err.Error(), "")
		return
	}

	var inputMap map[string]any
	if err := json.Unmarshal(input, &inputMap); err != nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, "LLM_INVALID_REQUEST", err.Error(), "")
		return
	}

	switch operation {
	case "stt":
		w.runSttJob(ctx, jobID, ownerUserID, operation, providerModelName, endpointBaseURL, secret, adapter, inputMap, logger)
	default:
		// Defensive — audioJobOperations is the gate; reaching here means
		// a new entry was added without a runner. Fail loud so it gets
		// caught in PR review or live tests.
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
			"LLM_OPERATION_NOT_SUPPORTED",
			"audio operation routed but no runner wired",
			"")
	}
}

// runSttJob executes a single Transcribe call and finalizes the job.
//
// Error mapping:
//   - context.Canceled → status=cancelled, code=LLM_CANCELLED
//   - ErrAudioFetchFailed → status=failed, code=LLM_AUDIO_FETCH_FAILED
//   - ErrAudioTooLarge → status=failed, code=LLM_AUDIO_TOO_LARGE
//   - ErrOperationNotSupported → status=failed, code=LLM_OPERATION_NOT_SUPPORTED
//   - any other error → status=failed, code=LLM_UPSTREAM_ERROR
//
// Cancellation note: ctx.Err() is checked AFTER Transcribe returns, since
// the gateway-side audio fetch and the upstream POST both honor ctx
// cancellation natively (http.Client). A cancelled job returns either
// the wrapped context error or an HTTP transport error wrapping it.
func (w *Worker) runSttJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation string,
	providerModelName, endpointBaseURL, secret string,
	adapter provider.Adapter,
	inputMap map[string]any,
	logger *slog.Logger,
) {
	// /review-impl HIGH#1 — bound the audio job's wall-clock so a slow
	// audio_url server can't pin this goroutine indefinitely. invokeClient
	// has no http.Timeout (chat streaming requires unbounded); per-op
	// caps must live at the dispatch boundary.
	sttCtx, cancel := context.WithTimeout(ctx, SttJobTimeout)
	defer cancel()

	audioURL, _ := inputMap["audio_url"].(string)
	language, _ := inputMap["language"].(string)

	in := provider.TranscribeInput{AudioURL: audioURL, Language: language}
	out, _, err := adapter.Transcribe(sttCtx, endpointBaseURL, secret, providerModelName, in)
	if err != nil {
		errCode, status := classifyAudioError(sttCtx, err)
		logger.Info("stt failed", "code", errCode, "status", status, "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, status, nil, errCode, err.Error(), "")
		return
	}

	result := map[string]any{
		"text":        out.Text,
		"language":    out.Language,
		"duration_ms": out.DurationMs,
	}
	_ = w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, 0)
	w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", "")
}

// classifyAudioError maps adapter-side errors to (code, status) pairs for
// finalizeAndNotify. ctx is examined first so a transport error caused
// by ctx.Cancel/Deadline surfaces with the right status.
//
// /review-impl HIGH#1 + MED#3 — extended classification:
//   - context.Canceled (outer cancel via DELETE handler) → cancelled
//   - context.DeadlineExceeded (our 5-min SttJobTimeout) → failed/LLM_TIMEOUT
//   - ErrUpstreamRateLimited → failed/LLM_RATE_LIMITED (caller can backoff)
//   - ErrUpstreamPermanent 401/403 → failed/LLM_AUTH_FAILED
//   - ErrUpstreamPermanent 4xx other → failed/LLM_UPSTREAM_ERROR
//   - ErrUpstreamTransient (5xx) → failed/LLM_UPSTREAM_ERROR
//   - ErrAudioURLDisallowed (SSRF guard) → failed/LLM_AUDIO_URL_DISALLOWED
//   - ErrAudioFetchFailed → failed/LLM_AUDIO_FETCH_FAILED
//   - ErrAudioTooLarge → failed/LLM_AUDIO_TOO_LARGE
//   - ErrOperationNotSupported → failed/LLM_OPERATION_NOT_SUPPORTED
//   - other → failed/LLM_UPSTREAM_ERROR
func classifyAudioError(ctx context.Context, err error) (code, status string) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		if errors.Is(ctxErr, context.DeadlineExceeded) {
			return "LLM_TIMEOUT", "failed"
		}
		if errors.Is(ctxErr, context.Canceled) {
			return "LLM_CANCELLED", "cancelled"
		}
	}
	// Typed upstream errors take precedence over generic sentinels — they
	// carry structured status code info that the generic path loses.
	var rl *provider.ErrUpstreamRateLimited
	if errors.As(err, &rl) {
		return "LLM_RATE_LIMITED", "failed"
	}
	var perm *provider.ErrUpstreamPermanent
	if errors.As(err, &perm) {
		if perm.StatusCode == 401 || perm.StatusCode == 403 {
			return "LLM_AUTH_FAILED", "failed"
		}
		return "LLM_UPSTREAM_ERROR", "failed"
	}
	var trans *provider.ErrUpstreamTransient
	if errors.As(err, &trans) {
		return "LLM_UPSTREAM_ERROR", "failed"
	}
	switch {
	case errors.Is(err, provider.ErrAudioURLDisallowed):
		return "LLM_AUDIO_URL_DISALLOWED", "failed"
	case errors.Is(err, provider.ErrAudioFetchFailed):
		return "LLM_AUDIO_FETCH_FAILED", "failed"
	case errors.Is(err, provider.ErrAudioTooLarge):
		return "LLM_AUDIO_TOO_LARGE", "failed"
	case errors.Is(err, provider.ErrOperationNotSupported):
		return "LLM_OPERATION_NOT_SUPPORTED", "failed"
	default:
		return "LLM_UPSTREAM_ERROR", "failed"
	}
}
