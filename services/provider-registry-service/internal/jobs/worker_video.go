package jobs

// worker_video.go — Phase 5d video-gen job dispatch path.
//
// Routed from Worker.Process() when operation is in videoJobOperations.
// Runs adapter.GenerateVideo synchronously (no streaming, no chunking,
// no aggregator) → marshals provider.GenerateVideoOutput to
// VideoGenResult shape → finalizes Job.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// VideoGenJobTimeout — Phase 5d. Wall-clock cap on a single video-gen
// job. Multi-step ComfyUI workflows for 5-second 1080p clips (Wan,
// LTX Video, SDXL-derived video models) commonly take 5-15 min; longer
// durations can hit 20+ min. 30 min gives headroom without indefinitely
// pinning the worker goroutine. 3× longer than ImageGenJobTimeout
// (10 min) and 6× longer than SttJobTimeout (5 min).
//
// /review-impl design Q2 — raise to 45-60 min if telemetry surfaces
// frequent LLM_TIMEOUT for legitimate workloads.
const VideoGenJobTimeout = 30 * time.Minute

// videoJobOperations — Phase 5d. Job operations dispatched through
// processVideoGenJob (the video-gen path). Disjoint from streamable,
// audio, and image operations — asserted by TestVideoJobOperations_Disjoint.
var videoJobOperations = map[string]struct{}{
	"video_gen": {},
}

func isVideoJobOperation(op string) bool {
	_, ok := videoJobOperations[op]
	return ok
}

// processVideoGenJob dispatches a video-gen-shaped job. Mirrors the
// layout of processImageGenJob: creds-resolve + adapter-pick + input
// decode + runVideoGenJob.
func (w *Worker) processVideoGenJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation, modelSource string,
	modelRef uuid.UUID,
	input json.RawMessage,
	logger *slog.Logger,
) {
	providerKind, providerModelName, endpointBaseURL, secret, err := w.resolve(ctx, ownerUserID, modelRef, modelSource)
	if err != nil {
		logger.Error("resolve creds failed (video)", "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
			"LLM_MODEL_NOT_FOUND", err.Error(), "")
		return
	}

	adapter, err := w.adapter(providerKind)
	if err != nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
			"LLM_PROVIDER_ROUTE_VIOLATION", err.Error(), "")
		return
	}

	var inputMap map[string]any
	if err := json.Unmarshal(input, &inputMap); err != nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
			"LLM_INVALID_REQUEST", err.Error(), "")
		return
	}

	w.runVideoGenJob(ctx, jobID, ownerUserID, operation, providerModelName,
		endpointBaseURL, secret, adapter, inputMap, logger)
}

// runVideoGenJob executes a single GenerateVideo call and finalizes
// the job.
//
// Error mapping (via classifyVideoError):
//   - context.Canceled → cancelled, LLM_CANCELLED
//   - context.DeadlineExceeded → failed, LLM_TIMEOUT
//   - ErrVideoInvalidParams → failed, LLM_INVALID_REQUEST
//   - ErrVideoContentPolicy → failed, LLM_VIDEO_CONTENT_POLICY_VIOLATION
//   - ErrVideoGenerationFailed → failed, LLM_VIDEO_GENERATION_FAILED
//   - typed upstream errors → failed, LLM_RATE_LIMITED / LLM_AUTH_FAILED / LLM_UPSTREAM_ERROR
//   - ErrOperationNotSupported → failed, LLM_OPERATION_NOT_SUPPORTED
//   - other → failed, LLM_UPSTREAM_ERROR
func (w *Worker) runVideoGenJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation string,
	providerModelName, endpointBaseURL, secret string,
	adapter provider.Adapter,
	inputMap map[string]any,
	logger *slog.Logger,
) {
	vidCtx, cancel := context.WithTimeout(ctx, VideoGenJobTimeout)
	defer cancel()

	in := provider.GenerateVideoInput{
		Prompt:         safeStr(inputMap, "prompt"),
		Size:           safeStr(inputMap, "size"),
		Duration:       safeIntDefault(inputMap, "duration", 0),
		N:              safeIntDefault(inputMap, "n", 0),
		ResponseFormat: safeStr(inputMap, "response_format"),
		Style:          safeStr(inputMap, "style"),
		InitImage:      safeStr(inputMap, "init_image"),
	}
	// Phase 6b — retry the generation on a transient upstream error.
	var out provider.GenerateVideoOutput
	err := retryTransient(vidCtx, w.maxRetries, logger, func() error {
		o, _, e := adapter.GenerateVideo(vidCtx, endpointBaseURL, secret, providerModelName, in)
		out = o
		return e
	})
	if err != nil {
		errCode, status := classifyVideoError(vidCtx, err)
		logger.Info("video_gen failed", "code", errCode, "status", status, "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, status, nil, errCode, err.Error(), "")
		return
	}

	dataItems := make([]map[string]any, len(out.Data))
	for i, d := range out.Data {
		item := map[string]any{}
		if d.URL != "" {
			item["url"] = d.URL
		}
		if d.RevisedPrompt != "" {
			item["revised_prompt"] = d.RevisedPrompt
		}
		dataItems[i] = item
	}
	result := map[string]any{
		"created": out.Created,
		"data":    dataItems,
	}
	_ = w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, 0)
	w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", "")
}

// classifyVideoError maps adapter-side errors to (code, status) pairs.
// Mirrors classifyImageError's structure — ctx state first, then typed
// upstream errors, then sentinels.
func classifyVideoError(ctx context.Context, err error) (code, status string) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		if errors.Is(ctxErr, context.DeadlineExceeded) {
			return "LLM_TIMEOUT", "failed"
		}
		if errors.Is(ctxErr, context.Canceled) {
			return "LLM_CANCELLED", "cancelled"
		}
	}
	// Typed upstream errors take precedence over generic sentinels.
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
	case errors.Is(err, provider.ErrVideoInvalidParams):
		return "LLM_INVALID_REQUEST", "failed"
	case errors.Is(err, provider.ErrVideoContentPolicy):
		return "LLM_VIDEO_CONTENT_POLICY_VIOLATION", "failed"
	case errors.Is(err, provider.ErrVideoGenerationFailed):
		return "LLM_VIDEO_GENERATION_FAILED", "failed"
	case errors.Is(err, provider.ErrOperationNotSupported):
		return "LLM_OPERATION_NOT_SUPPORTED", "failed"
	default:
		return "LLM_UPSTREAM_ERROR", "failed"
	}
}
