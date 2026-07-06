package jobs

// worker_vision.go — PDF-import vision op (docs/specs/2026-07-06-pdf-book-import.md
// L5) job dispatch path.
//
// Routed from Worker.Process() when operation is in visionJobOperations.
// Runs adapter.CaptionImage synchronously (no streaming, no chunking, no
// aggregator) → marshals provider.CaptionImageOutput to a result map →
// finalizes Job with result OR maps adapter error to LLM_* code. Mirrors
// worker_image.go's layout exactly.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// VisionJobTimeout — wall-clock cap on a single vision-caption job. A
// one-shot multimodal chat completion typically completes in well under
// 60s; 2 minutes gives headroom for a slower local/BYOK backend without
// indefinitely pinning the worker goroutine.
const VisionJobTimeout = 2 * time.Minute

// visionJobOperations — job operations dispatched through
// processVisionJob (the vision-caption path) instead of the streaming
// chat machinery.
//
// Disjoint from streamableOperations/audioJobOperations/imageJobOperations/
// videoJobOperations — see TestVisionJobOperations_Disjoint.
var visionJobOperations = map[string]struct{}{
	"vision": {},
}

// isVisionJobOperation reports whether the worker dispatches the
// operation through the vision-caption path (adapter.CaptionImage, no
// chunking, no streaming).
func isVisionJobOperation(op string) bool {
	_, ok := visionJobOperations[op]
	return ok
}

// processVisionJob dispatches a vision-shaped job. Mirrors the layout of
// processImageGenJob: creds-resolve + adapter-pick + decode input +
// runVisionJob.
func (w *Worker) processVisionJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation, modelSource string,
	modelRef uuid.UUID,
	input json.RawMessage,
	logger *slog.Logger,
) {
	providerKind, providerModelName, endpointBaseURL, secret, err := w.resolve(ctx, ownerUserID, modelRef, modelSource)
	if err != nil {
		logger.Error("resolve creds failed (vision)", "err", err)
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

	w.runVisionJob(ctx, jobID, ownerUserID, operation, providerKind, providerModelName,
		endpointBaseURL, secret, adapter, inputMap, logger)
}

// runVisionJob executes a single CaptionImage call and finalizes the job.
//
// Error mapping (via classifyVisionError):
//   - context.Canceled → cancelled, LLM_CANCELLED
//   - context.DeadlineExceeded → failed, LLM_TIMEOUT
//   - ErrVisionInvalidParams → failed, LLM_INVALID_REQUEST
//   - ErrVisionCaptionFailed → failed, LLM_VISION_CAPTION_FAILED
//   - typed upstream errors → failed, LLM_RATE_LIMITED / LLM_AUTH_FAILED / LLM_UPSTREAM_ERROR
//   - ErrOperationNotSupported → failed, LLM_OPERATION_NOT_SUPPORTED
//   - any other → failed, LLM_UPSTREAM_ERROR
func (w *Worker) runVisionJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation string,
	providerKind, providerModelName, endpointBaseURL, secret string,
	adapter provider.Adapter,
	inputMap map[string]any,
	logger *slog.Logger,
) {
	visCtx, cancel := context.WithTimeout(ctx, VisionJobTimeout)
	defer cancel()

	in := provider.CaptionImageInput{
		ImageB64:  safeStr(inputMap, "image_b64"),
		MimeType:  safeStr(inputMap, "mime_type"),
		Prompt:    safeStr(inputMap, "prompt"),
		MaxTokens: safeIntDefault(inputMap, "max_tokens", 0),
	}
	// Retry the caption on a transient upstream error, same discipline as
	// image_gen/video_gen.
	var out provider.CaptionImageOutput
	err := retryTransient(visCtx, w.maxRetries, logger, func() error {
		o, _, e := adapter.CaptionImage(visCtx, endpointBaseURL, secret, providerModelName, in)
		out = o
		return e
	})
	if err != nil {
		errCode, status := classifyVisionError(visCtx, err)
		logger.Info("vision caption failed", "code", errCode, "status", status, "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, status, nil, errCode, err.Error(), "")
		return
	}

	result := map[string]any{
		"caption":             out.Caption,
		"finish_reason":       out.FinishReason,
		"provider_kind":       providerKind,
		"provider_model_name": providerModelName,
	}
	_ = w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, 0)
	w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", out.FinishReason)
}

// classifyVisionError maps adapter-side errors to (code, status) pairs
// for finalizeAndNotify. Mirrors classifyImageError's structure.
func classifyVisionError(ctx context.Context, err error) (code, status string) {
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
	case errors.Is(err, provider.ErrVisionInvalidParams):
		return "LLM_INVALID_REQUEST", "failed"
	case errors.Is(err, provider.ErrVisionCaptionFailed):
		return "LLM_VISION_CAPTION_FAILED", "failed"
	case errors.Is(err, provider.ErrOperationNotSupported):
		return "LLM_OPERATION_NOT_SUPPORTED", "failed"
	default:
		return "LLM_UPSTREAM_ERROR", "failed"
	}
}
