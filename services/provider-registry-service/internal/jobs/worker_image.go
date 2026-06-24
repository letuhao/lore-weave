package jobs

// worker_image.go — Phase 5c-α image-gen job dispatch path.
//
// Routed from Worker.Process() when operation is in imageJobOperations.
// Runs adapter.GenerateImage synchronously (no streaming, no chunking,
// no aggregator) → marshals provider.GenerateImageOutput to ImageGenResult
// shape → finalizes Job with result OR maps adapter error to LLM_* code.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// ImageGenJobTimeout — Phase 5c-α. Wall-clock cap on a single image-gen
// job. Multi-step ComfyUI workflows (Flux 1024×1024 with 28 steps,
// SDXL refiner pass) commonly take 60-120s; 4-image batches can hit
// 5-8 min. 10 min gives headroom without indefinitely pinning the
// worker goroutine.
//
// /review-impl design Q6 — tunable in a future cycle via config field
// if telemetry surfaces a problem.
const ImageGenJobTimeout = 10 * time.Minute

// imageJobOperations — Phase 5c-α. Job operations dispatched through
// processImageGenJob (the image-gen path) instead of the streaming
// chat machinery.
//
// streamableOperations ∩ imageJobOperations = ∅. Same disjoint-set
// invariant Phase 5a established between streamable + audio; image
// is the third dispatch path. Routing in Process() picks one based
// on map membership (audio first, then image, then streamable —
// non-overlap is asserted by TestImageJobOperations_Disjoint).
var imageJobOperations = map[string]struct{}{
	"image_gen": {},
}

// isImageJobOperation reports whether the worker dispatches the operation
// through the image-gen path (adapter.GenerateImage, no chunking, no
// streaming).
func isImageJobOperation(op string) bool {
	_, ok := imageJobOperations[op]
	return ok
}

// processImageGenJob dispatches an image-gen-shaped job. Mirrors the
// layout of processAudioJob: creds-resolve + adapter-pick + decode
// input + runImageGenJob.
func (w *Worker) processImageGenJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation, modelSource string,
	modelRef uuid.UUID,
	input json.RawMessage,
	logger *slog.Logger,
) {
	providerKind, providerModelName, endpointBaseURL, secret, err := w.resolve(ctx, ownerUserID, modelRef, modelSource)
	if err != nil {
		logger.Error("resolve creds failed (image)", "err", err)
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

	w.runImageGenJob(ctx, jobID, ownerUserID, operation, providerKind, providerModelName,
		endpointBaseURL, secret, adapter, inputMap, logger)
}

// runImageGenJob executes a single GenerateImage call and finalizes
// the job.
//
// Error mapping (via classifyImageError):
//   - context.Canceled → cancelled, LLM_CANCELLED
//   - context.DeadlineExceeded → failed, LLM_TIMEOUT
//   - ErrImageInvalidParams → failed, LLM_INVALID_REQUEST
//   - ErrImageContentPolicy → failed, LLM_IMAGE_CONTENT_POLICY_VIOLATION
//   - ErrImageGenerationFailed → failed, LLM_IMAGE_GENERATION_FAILED
//   - typed upstream errors → failed, LLM_RATE_LIMITED / LLM_AUTH_FAILED / LLM_UPSTREAM_ERROR
//   - ErrOperationNotSupported → failed, LLM_OPERATION_NOT_SUPPORTED
//   - any other → failed, LLM_UPSTREAM_ERROR
func (w *Worker) runImageGenJob(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation string,
	providerKind, providerModelName, endpointBaseURL, secret string,
	adapter provider.Adapter,
	inputMap map[string]any,
	logger *slog.Logger,
) {
	imgCtx, cancel := context.WithTimeout(ctx, ImageGenJobTimeout)
	defer cancel()

	in := provider.GenerateImageInput{
		Prompt:         safeStr(inputMap, "prompt"),
		Size:           safeStr(inputMap, "size"),
		N:              safeIntDefault(inputMap, "n", 0),
		ResponseFormat: safeStr(inputMap, "response_format"),
		Quality:        safeStr(inputMap, "quality"),
		Style:          safeStr(inputMap, "style"),
		Background:     safeStr(inputMap, "background"),
	}
	// Phase 6b — retry the generation on a transient upstream error.
	var out provider.GenerateImageOutput
	err := retryTransient(imgCtx, w.maxRetries, logger, func() error {
		o, _, e := adapter.GenerateImage(imgCtx, endpointBaseURL, secret, providerModelName, in)
		out = o
		return e
	})
	if err != nil {
		errCode, status := classifyImageError(imgCtx, err)
		logger.Info("image_gen failed", "code", errCode, "status", status, "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, status, nil, errCode, err.Error(), "")
		return
	}

	dataItems := make([]map[string]any, len(out.Data))
	for i, d := range out.Data {
		item := map[string]any{}
		if d.URL != "" {
			item["url"] = d.URL
		}
		if d.B64JSON != "" {
			item["b64_json"] = d.B64JSON
		}
		if d.RevisedPrompt != "" {
			item["revised_prompt"] = d.RevisedPrompt
		}
		dataItems[i] = item
	}
	result := map[string]any{
		"created": out.Created,
		"data":    dataItems,
		// D-PHASE5E — surface the resolved provider identity so the consumer
		// (book-service) can record application-level analytics + the displayed
		// model name without a second lookup. Both already resolved above.
		"provider_kind":       providerKind,
		"provider_model_name": providerModelName,
	}
	_ = w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, 0)
	w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", "")
}

// classifyImageError maps adapter-side errors to (code, status) pairs
// for finalizeAndNotify. Mirrors classifyAudioError's structure.
//
// ctx state is examined first so a transport error caused by ctx.Cancel/
// Deadline surfaces with the right status.
func classifyImageError(ctx context.Context, err error) (code, status string) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		if errors.Is(ctxErr, context.DeadlineExceeded) {
			return "LLM_TIMEOUT", "failed"
		}
		if errors.Is(ctxErr, context.Canceled) {
			return "LLM_CANCELLED", "cancelled"
		}
	}
	// Typed upstream errors take precedence over generic sentinels —
	// they carry structured status code info the generic path loses.
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
	case errors.Is(err, provider.ErrImageInvalidParams):
		// Phase 5c-α /review-impl(DESIGN) MED#5 — adapter pre-check
		// invariant violation. Caller-side bug, not retryable.
		return "LLM_INVALID_REQUEST", "failed"
	case errors.Is(err, provider.ErrImageContentPolicy):
		return "LLM_IMAGE_CONTENT_POLICY_VIOLATION", "failed"
	case errors.Is(err, provider.ErrImageGenerationFailed):
		return "LLM_IMAGE_GENERATION_FAILED", "failed"
	case errors.Is(err, provider.ErrOperationNotSupported):
		return "LLM_OPERATION_NOT_SUPPORTED", "failed"
	default:
		return "LLM_UPSTREAM_ERROR", "failed"
	}
}

// safeStr returns inputMap[key] as a string, or "" if missing or not a string.
func safeStr(m map[string]any, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

// safeFloatDefault returns inputMap[key] as float64, or def if missing/not numeric.
// JSON decoder yields float64 for any numeric JSON value.
//
// Phase 5e-β.2 — used by runAudioGenJob for `speed` field.
func safeFloatDefault(m map[string]any, key string, def float64) float64 {
	if v, ok := m[key].(float64); ok {
		return v
	}
	return def
}

// safeIntDefault returns inputMap[key] as an int (coercing from float64
// for JSON-numbers), or `def` if missing/wrong type.
func safeIntDefault(m map[string]any, key string, def int) int {
	if v, ok := m[key]; ok {
		switch x := v.(type) {
		case int:
			return x
		case int64:
			return int(x)
		case float64:
			return int(x)
		}
	}
	return def
}
