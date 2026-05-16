package jobs

// worker_audio.go — Phase 5a audio-job dispatch path.
//
// Routed from Worker.Process() when operation is in audioJobOperations.
// Runs adapter.Transcribe synchronously (no streaming, no chunking, no
// aggregator) → marshals provider.TranscribeOutput to SttResult shape →
// finalizes Job with result OR maps adapter error to LLM_* code.

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
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

// ProcessAudioInline — Phase 5b. Bytes-mode entrypoint that mirrors
// Process() but takes audio bytes via goroutine closure instead of
// reading them from the DB-persisted input JSON. Called from the
// multipart submit handler (jobs_handler.go) AFTER ParseMultipartForm
// has extracted the file + metadata fields; the handler holds the
// bytes in stack memory + spawns this goroutine with the bytes captured
// in its closure.
//
// /review-impl design §3.2: this binds bytes-mode STT to the in-process
// goroutine pattern. Phase 2c (RabbitMQ worker migration) will need
// MinIO staging — D-PHASE2C-AUDIO-STAGING deferred item.
//
// The synthesized inputMap mirrors what runSttJob expects but the
// audio source is signaled by a non-nil AudioBytes on TranscribeInput
// rather than an "audio_url" field — the adapter's exactly-one check
// ensures no ambiguity.
func (w *Worker) ProcessAudioInline(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	modelSource string,
	modelRef uuid.UUID,
	language string,
	audioBytes []byte,
	contentType string,
) {
	logger := w.logger.With("job_id", jobID.String(), "operation", "stt", "mode", "inline")

	rowsRunning, err := w.repo.MarkRunning(ctx, jobID)
	if err != nil {
		logger.Error("mark running failed", "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, "stt", "failed", nil, "LLM_INTERNAL_ERROR", err.Error(), "")
		return
	}
	if rowsRunning == 0 {
		logger.Info("job not pending; skipping process")
		return
	}

	providerKind, providerModelName, endpointBaseURL, secret, err := w.resolve(ctx, ownerUserID, modelRef, modelSource)
	if err != nil {
		logger.Error("resolve creds failed (audio-inline)", "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, "stt", "failed", nil, "LLM_MODEL_NOT_FOUND", err.Error(), "")
		return
	}

	adapter, err := w.adapter(providerKind)
	if err != nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, "stt", "failed", nil, "LLM_PROVIDER_ROUTE_VIOLATION", err.Error(), "")
		return
	}

	// /review-impl HIGH#1 (5a) — bound wall-clock; bytes mode reuses
	// the same SttJobTimeout cap so a slow upstream Whisper can't pin
	// the goroutine indefinitely (the 25MB byte slice is captured in
	// closure for the duration; cap protects RAM).
	sttCtx, cancel := context.WithTimeout(ctx, SttJobTimeout)
	defer cancel()

	in := provider.TranscribeInput{
		AudioBytes:  audioBytes,
		ContentType: contentType,
		Language:    language,
	}
	// Phase 6b — retry the transcription on a transient upstream error.
	var out provider.TranscribeOutput
	terr := retryTransient(sttCtx, w.maxRetries, logger, func() error {
		o, _, e := adapter.Transcribe(sttCtx, endpointBaseURL, secret, providerModelName, in)
		out = o
		return e
	})
	if terr != nil {
		errCode, status := classifyAudioError(sttCtx, terr)
		logger.Info("stt-inline failed", "code", errCode, "status", status, "err", terr)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, "stt", status, nil, errCode, terr.Error(), "")
		return
	}

	result := map[string]any{
		"text":        out.Text,
		"language":    out.Language,
		"duration_ms": out.DurationMs,
	}
	_ = w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, 0)
	w.finalizeAndNotify(ctx, jobID, ownerUserID, "stt", "completed", result, "", "", "")
}

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
	case "audio_gen":
		// Phase 5e-β.2 — batch TTS dispatch.
		w.runAudioGenJob(ctx, jobID, ownerUserID, operation, providerModelName, endpointBaseURL, secret, adapter, inputMap, logger)
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
	// Phase 6b — retry the transcription on a transient upstream error.
	var out provider.TranscribeOutput
	err := retryTransient(sttCtx, w.maxRetries, logger, func() error {
		o, _, e := adapter.Transcribe(sttCtx, endpointBaseURL, secret, providerModelName, in)
		out = o
		return e
	})
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

// AudioGenJobTimeout — Phase 5e-β.2. Wall-clock cap on a single audio_gen
// (batch TTS) job. 10 inputs × ~15s upstream + slack = 5 min upper bound.
const AudioGenJobTimeout = 5 * time.Minute

// runAudioGenJob — Phase 5e-β.2. Executes a single GenerateAudio call,
// converts batch result to b64_json or URL mode based on input.response_format,
// and finalizes the job.
//
// Error mapping (via classifyAudioGenError):
//   - context.Canceled → cancelled, LLM_CANCELLED
//   - context.DeadlineExceeded → failed, LLM_TIMEOUT
//   - ErrAudioGenInvalidParams → failed, LLM_INVALID_REQUEST
//   - ErrAudioGenerationFailed → failed, LLM_AUDIO_GENERATION_FAILED
//   - typed upstream errors → failed, LLM_RATE_LIMITED / LLM_AUTH_FAILED / LLM_UPSTREAM_ERROR
//   - ErrOperationNotSupported → failed, LLM_OPERATION_NOT_SUPPORTED
//   - other → failed, LLM_UPSTREAM_ERROR
//
// URL mode with nil w.audioCache → failed/LLM_INVALID_REQUEST.
func (w *Worker) runAudioGenJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation string,
	providerModelName, endpointBaseURL, secret string,
	adapter provider.Adapter,
	inputMap map[string]any,
	logger *slog.Logger,
) {
	agCtx, cancel := context.WithTimeout(ctx, AudioGenJobTimeout)
	defer cancel()

	// Extract texts array from input map (json.Unmarshal yielded []any of strings).
	// /review-impl(BUILD) H#1 — if any non-string element appears, fail
	// LLM_INVALID_REQUEST with clear diagnostics instead of silently
	// stripping (which would corrupt the index mapping at the caller).
	rawTexts, _ := inputMap["texts"].([]any)
	texts := make([]string, 0, len(rawTexts))
	for i, t := range rawTexts {
		s, ok := t.(string)
		if !ok {
			w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
				"LLM_INVALID_REQUEST",
				fmt.Sprintf("audio_gen texts[%d] must be string (got %T)", i, t),
				"")
			return
		}
		texts = append(texts, s)
	}
	responseFormat := safeStr(inputMap, "response_format")
	if responseFormat == "" {
		responseFormat = "b64_json"
	}

	// URL mode requires w.audioCache wired.
	if responseFormat == "url" && w.audioCache == nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
			"LLM_INVALID_REQUEST",
			"audio_gen url mode requires gateway audio-cache configured (set MINIO_* envs)",
			"")
		return
	}

	in := provider.GenerateAudioInput{
		Texts:          texts,
		Voice:          safeStr(inputMap, "voice"),
		Speed:          safeFloatDefault(inputMap, "speed", 0),
		Format:         safeStr(inputMap, "format"),
		ResponseFormat: responseFormat,
	}

	// Phase 6b — retry the generation on a transient upstream error.
	var out provider.GenerateAudioOutput
	err := retryTransient(agCtx, w.maxRetries, logger, func() error {
		o, _, e := adapter.GenerateAudio(agCtx, endpointBaseURL, secret, providerModelName, in)
		out = o
		return e
	})
	if err != nil {
		errCode, status := classifyAudioGenError(agCtx, err)
		logger.Info("audio_gen failed", "code", errCode, "status", status, "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, status, nil, errCode, err.Error(), "")
		return
	}

	// Build result.data based on response_format.
	dataItems := make([]map[string]any, len(out.Items))
	for i, item := range out.Items {
		entry := map[string]any{
			"content_type": item.ContentType,
		}
		if item.DurationMs > 0 {
			entry["duration_ms"] = item.DurationMs
		}
		if responseFormat == "url" {
			url, stageErr := w.audioCache.Stage(agCtx, jobID, i, item.Format, item.Data, item.ContentType)
			if stageErr != nil {
				// /review-impl(BUILD) H#4 — distinguish gateway-side
				// storage failure from upstream AI failure. Upstream
				// SUCCEEDED (we've burned BYOK char-billing); the issue
				// is gateway storage. Use LLM_GATEWAY_STORAGE_ERROR so
				// callers don't auto-retry (which would double-charge).
				logger.Error("audio_gen stage failed (upstream succeeded; gateway storage error)", "idx", i, "err", stageErr)
				w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
					"LLM_GATEWAY_STORAGE_ERROR",
					"upstream TTS succeeded but gateway storage failed: "+stageErr.Error(),
					"")
				return
			}
			entry["url"] = url
		} else {
			entry["b64_json"] = base64.StdEncoding.EncodeToString(item.Data)
		}
		dataItems[i] = entry
	}
	result := map[string]any{
		"created": time.Now().Unix(),
		"data":    dataItems,
	}
	_ = w.repo.UpdateProgress(ctx, jobID, intPtr(len(out.Items)), len(out.Items), 0)
	w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", "")
}

// classifyAudioGenError maps adapter-side errors to (code, status) pairs
// for audio_gen. Mirrors classifyVideoError / classifyImageError structure.
//
// /review-impl(DESIGN) MED#4 — full typed-error matrix; no gaps.
func classifyAudioGenError(ctx context.Context, err error) (code, status string) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		if errors.Is(ctxErr, context.DeadlineExceeded) {
			return "LLM_TIMEOUT", "failed"
		}
		if errors.Is(ctxErr, context.Canceled) {
			return "LLM_CANCELLED", "cancelled"
		}
	}
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
	case errors.Is(err, provider.ErrAudioGenInvalidParams):
		return "LLM_INVALID_REQUEST", "failed"
	case errors.Is(err, provider.ErrAudioGenerationFailed):
		return "LLM_AUDIO_GENERATION_FAILED", "failed"
	case errors.Is(err, provider.ErrOperationNotSupported):
		return "LLM_OPERATION_NOT_SUPPORTED", "failed"
	default:
		return "LLM_UPSTREAM_ERROR", "failed"
	}
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
//   - ErrTranscribeInputInvalid (Phase 5b) → failed/LLM_INVALID_REQUEST
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
	case errors.Is(err, provider.ErrTranscribeInputInvalid):
		// Phase 5b — adapter pre-check caught a caller-side invariant
		// violation (both URL+Bytes set, or neither). Surface as
		// LLM_INVALID_REQUEST so callers don't retry as a transient.
		return "LLM_INVALID_REQUEST", "failed"
	case errors.Is(err, provider.ErrOperationNotSupported):
		return "LLM_OPERATION_NOT_SUPPORTED", "failed"
	default:
		return "LLM_UPSTREAM_ERROR", "failed"
	}
}
