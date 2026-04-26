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
	notifier Notifier
	logger   *slog.Logger
}

func NewWorker(repo *Repo, resolve CredResolver, adapter AdapterFactory, notifier Notifier, logger *slog.Logger) *Worker {
	if logger == nil {
		logger = slog.Default()
	}
	if notifier == nil {
		notifier = NoopNotifier{}
	}
	return &Worker{repo: repo, resolve: resolve, adapter: adapter, notifier: notifier, logger: logger}
}

// finalizeAndNotify is the only path through which the worker ends a
// job. It runs Repo.Finalize and, if the row actually transitioned
// (rowsAffected > 0), publishes a TerminalEvent. The rowsAffected gate
// prevents a duplicate event when a cancel beat us at the DB layer
// (cancel handler emits its own event independently).
func (w *Worker) finalizeAndNotify(
	ctx context.Context,
	jobID, ownerUserID uuid.UUID,
	operation, status string,
	result any,
	errorCode, errorMessage, finishReason string,
) {
	rows, err := w.repo.Finalize(ctx, jobID, status, result, errorCode, errorMessage, finishReason)
	if err != nil {
		w.logger.Error("finalize failed", "job_id", jobID.String(), "err", err)
		return
	}
	if rows == 0 {
		// Race lost — cancel won. Cancel handler already published.
		return
	}
	var resultJSON json.RawMessage
	if result != nil {
		resultJSON, _ = json.Marshal(result)
	}
	if err := w.notifier.PublishTerminal(ctx, TerminalEvent{
		JobID:        jobID,
		OwnerUserID:  ownerUserID,
		Operation:    operation,
		Status:       status,
		Result:       resultJSON,
		ErrorCode:    errorCode,
		ErrorMessage: errorMessage,
		FinishReason: finishReason,
	}); err != nil {
		// Best-effort — DB row is the source of truth. Caller can
		// still poll. Log + move on.
		w.logger.Warn("notifier publish failed", "job_id", jobID.String(), "err", err)
	}
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
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, "LLM_INTERNAL_ERROR", err.Error(), "")
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
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
			"LLM_OPERATION_NOT_SUPPORTED",
			fmt.Sprintf("operation %q not yet implemented in async-job mode", operation),
			"")
		return
	}

	providerKind, providerModelName, endpointBaseURL, secret, err := w.resolve(ctx, ownerUserID, modelRef, modelSource)
	if err != nil {
		logger.Error("resolve creds failed", "err", err)
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, "LLM_MODEL_NOT_FOUND", err.Error(), "")
		return
	}

	adapter, err := w.adapter(providerKind)
	if err != nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, "LLM_PROVIDER_ROUTE_VIOLATION", err.Error(), "")
		return
	}

	// Decode input to the map form Adapter.Stream expects.
	var inputMap map[string]any
	if err := json.Unmarshal(input, &inputMap); err != nil {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, "LLM_INVALID_REQUEST", err.Error(), "")
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
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, errCode, streamErr.Error(), "")
		return
	}

	result, _, outputTokens := agg.Finalize()
	finishReason, _ := result["finish_reason"].(string)

	// Persist progress separately so the row carries token counts even
	// if a Phase 2c subscriber peeks before terminal.
	if err := w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, outputTokens); err != nil {
		logger.Warn("progress update failed", "err", err)
		// Not fatal — proceed to finalize anyway.
	}
	w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", finishReason)
}

func intPtr(v int) *int { return &v }
