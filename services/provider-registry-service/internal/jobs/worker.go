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

	"github.com/loreweave/provider-registry-service/internal/chunker"
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
// Phase 3c — `chunking` is the optional ChunkConfig decoded from the
// llm_jobs.chunking JSONB column. When non-nil + applicable to the input
// shape, the worker chunks the LAST user message's content via Phase 3a
// chunker, then dispatches per-chunk adapter.Stream calls (sequential
// for now — chatAggregator state isn't goroutine-safe across chunks;
// parallel is Phase 3c-followup or Phase 6 hardening).
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
	chunking *ChunkConfig,
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

	// Phase 3c — chunked dispatch path. Active when:
	//   1. chunking config is non-nil + non-none (decoded upstream)
	//   2. input shape supports chunking (chat with extractable text)
	// Otherwise we fall through to single-call Phase 2b path unchanged.
	chunkPieces := w.maybeChunk(inputMap, chunking, logger)
	if len(chunkPieces) > 1 {
		if err := w.processChunks(ctx, jobID, agg, adapter, endpointBaseURL, secret, providerModelName, inputMap, chunkPieces, emit, logger); err != nil {
			errCode := "LLM_UPSTREAM_ERROR"
			if err == provider.ErrStreamNotSupported {
				errCode = "LLM_STREAM_NOT_SUPPORTED"
			}
			w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, errCode, err.Error(), "")
			return
		}
	} else {
		// Single-call Phase 2b path.
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
		// Single chunk → progress 1/1 for caller polling.
		_ = w.repo.UpdateProgress(ctx, jobID, intPtr(1), 1, 0)
	}

	result, _, _ := agg.Finalize()
	finishReason, _ := result["finish_reason"].(string)

	w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "completed", result, "", "", finishReason)
}

// maybeChunk returns the chunked text pieces for this job's input, or
// a single-element slice when chunking is not requested / not applicable.
// Falling back gracefully (instead of erroring) means a chat job with
// chunking config but a non-chattable input shape still completes via
// the single-call path.
func (w *Worker) maybeChunk(inputMap map[string]any, cfg *ChunkConfig, logger *slog.Logger) []string {
	if cfg == nil {
		return nil
	}
	text, ok := ExtractChattableText(inputMap)
	if !ok {
		logger.Info("chunking requested but input not chattable — falling back to single call")
		return nil
	}
	pieces, err := chunkText(text, *cfg)
	if err != nil {
		logger.Warn("chunker failed — falling back to single call", "err", err)
		return nil
	}
	return pieces
}

// processChunks dispatches one adapter.Stream call per chunk, bracketed
// by agg.StartChunk/EndChunk so the aggregator builds a multi-chunk
// result. Sequential for now; goroutine-safe parallel is a follow-up.
func (w *Worker) processChunks(
	ctx context.Context,
	jobID uuid.UUID,
	agg Aggregator,
	adapter provider.Adapter,
	endpointBaseURL, secret, providerModelName string,
	inputMap map[string]any,
	chunks []string,
	emit EmitFn,
	logger *slog.Logger,
) error {
	total := len(chunks)
	totalPtr := &total
	for i, piece := range chunks {
		perChunkInput, err := SubstituteLastUserMessage(inputMap, piece)
		if err != nil {
			return fmt.Errorf("substitute chunk %d: %w", i, err)
		}
		agg.StartChunk(i)
		streamErr := adapter.Stream(ctx, endpointBaseURL, secret, providerModelName, perChunkInput, emit)
		agg.EndChunk(i)
		if streamErr != nil {
			logger.Error("chunk stream failed", "chunk", i, "err", streamErr)
			return streamErr
		}
		// Progress update so polling shows N/total.
		_ = w.repo.UpdateProgress(ctx, jobID, totalPtr, i+1, 0)
	}
	return nil
}

// EmitFn aliases provider.EmitFn so the worker doesn't redeclare types.
type EmitFn = func(provider.StreamChunk) error

// chunkText is a thin wrapper that calls into the chunker package using
// the worker's ChunkConfig. Kept package-internal so the chunker import
// stays a worker.go private detail.
func chunkText(text string, c ChunkConfig) ([]string, error) {
	return chunker.ChunkText(text, chunker.Request{
		Strategy: chunker.Strategy(c.Strategy),
		Size:     c.Size,
		Overlap:  c.Overlap,
	})
}

func intPtr(v int) *int { return &v }
