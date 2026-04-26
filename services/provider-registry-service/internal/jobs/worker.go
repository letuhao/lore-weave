package jobs

// Phase 2b worker. Process(ctx, jobID, ...) drives one job from
// pending → running → terminal. Phase 2b spawns this inline from the
// POST handler (fire-and-forget goroutine); Phase 2c will wrap it in a
// RabbitMQ consumer. Phase 6 hardening adds a crash-recovery crawler.

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// CredResolver looks up the provider details a job needs before
// invocation. Server already has this logic inline (see
// invokeModel/internalInvokeModel/doProxy); the worker uses a small
// callback to avoid pulling those into this package.
type CredResolver func(
	ctx context.Context,
	ownerUserID, modelRef uuid.UUID,
	modelSource string,
) (
	providerKind string,
	providerModelName string,
	endpointBaseURL string,
	secret string,
	err error,
)

// AdapterFactory returns a streaming adapter for a given provider kind.
// Mirrors provider.ResolveAdapter signature without forcing the worker
// to know about the http client wiring.
type AdapterFactory func(providerKind string) (provider.Adapter, error)

// Worker holds the dependencies a job needs. Constructed once at server
// lifespan startup; reused for every Process() call.
type Worker struct {
	repo     *Repo
	resolve  CredResolver
	adapter  AdapterFactory
	logger   *slog.Logger
}

func NewWorker(repo *Repo, resolve CredResolver, adapter AdapterFactory, logger *slog.Logger) *Worker {
	if logger == nil {
		logger = slog.Default()
	}
	return &Worker{repo: repo, resolve: resolve, adapter: adapter, logger: logger}
}

// Process runs a single job to completion. Caller passes in the inserted
// job_id + the original input (so we don't re-read JSONB from DB).
//
// Crash semantics: if the goroutine running Process panics or the
// process exits, the row stays in 'running' indefinitely. Phase 6 adds
// a recovery crawler that times out long-stale rows.
func (w *Worker) Process(
	ctx context.Context,
	jobID uuid.UUID,
	ownerUserID uuid.UUID,
	operation, modelSource string,
	modelRef uuid.UUID,
	input json.RawMessage,
) {
	logger := w.logger.With("job_id", jobID.String(), "operation", operation)

	rowsRunning, err := w.repo.MarkRunning(ctx, jobID)
	if err != nil {
		logger.Error("mark running failed", "err", err)
		_ = w.repo.Finalize(ctx, jobID, "failed", nil, "LLM_INTERNAL_ERROR", err.Error(), "")
		return
	}
	if rowsRunning == 0 {
		// Already cancelled OR another worker beat us. Nothing to do.
		logger.Info("job not pending; skipping process")
		return
	}

	// Phase 2b cuts: only chat/completion are wired through the streaming
	// adapter. Other operations get a clean LLM_OPERATION_NOT_SUPPORTED.
	if operation != "chat" && operation != "completion" {
		_ = w.repo.Finalize(ctx, jobID, "failed", nil,
			"LLM_OPERATION_NOT_SUPPORTED",
			fmt.Sprintf("operation %q not yet implemented in async-job mode", operation),
			"")
		return
	}

	providerKind, providerModelName, endpointBaseURL, secret, err := w.resolve(ctx, ownerUserID, modelRef, modelSource)
	if err != nil {
		logger.Error("resolve creds failed", "err", err)
		_ = w.repo.Finalize(ctx, jobID, "failed", nil, "LLM_MODEL_NOT_FOUND", err.Error(), "")
		return
	}

	adapter, err := w.adapter(providerKind)
	if err != nil {
		_ = w.repo.Finalize(ctx, jobID, "failed", nil, "LLM_PROVIDER_ROUTE_VIOLATION", err.Error(), "")
		return
	}

	// Decode input to the map form Adapter.Stream expects.
	var inputMap map[string]any
	if err := json.Unmarshal(input, &inputMap); err != nil {
		_ = w.repo.Finalize(ctx, jobID, "failed", nil, "LLM_INVALID_REQUEST", err.Error(), "")
		return
	}

	agg := NewAggregator(operation)
	emit := func(chunk provider.StreamChunk) error {
		agg.Accept(chunk)
		return nil
	}

	streamErr := adapter.Stream(ctx, endpointBaseURL, secret, providerModelName, inputMap, emit)
	if streamErr != nil {
		logger.Error("stream failed", "err", streamErr)
		errCode := "LLM_UPSTREAM_ERROR"
		if streamErr == provider.ErrStreamNotSupported {
			errCode = "LLM_STREAM_NOT_SUPPORTED"
		}
		_ = w.repo.Finalize(ctx, jobID, "failed", nil, errCode, streamErr.Error(), "")
		return
	}

	result, _, outputTokens := agg.Finalize()
	finishReason, _ := result["finish_reason"].(string)

	// Persist progress + result. We update progress separately so a
	// future Phase 2c callback emit can race-safely read tokens_used
	// from the row before terminal.
	if err := w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, outputTokens); err != nil {
		logger.Warn("progress update failed", "err", err)
		// Not fatal — proceed to finalize anyway.
	}
	if err := w.repo.Finalize(ctx, jobID, "completed", result, "", "", finishReason); err != nil {
		logger.Error("finalize failed", "err", err)
	}
}

func intPtr(v int) *int { return &v }
