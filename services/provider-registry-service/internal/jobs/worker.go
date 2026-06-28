package jobs

// Phase 2b worker. Process(ctx, jobID, ...) drives one job from
// pending → running → terminal. Phase 2b spawns this inline from the
// POST handler (fire-and-forget goroutine); Phase 2c will wrap it in a
// RabbitMQ consumer. Phase 6 hardening adds a crash-recovery crawler.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/observability"
	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/chunker"
	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
	"github.com/loreweave/provider-registry-service/internal/storage"
)

// CredResolver looks up the provider details a job needs before
// invocation. Server already has this logic inline (see doProxy);
// the worker uses a small callback to avoid pulling those into this
// package. (invokeModel / internalInvokeModel removed in Phase 4d.)
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
	// Phase 5e-β.2 — gateway-side audio staging for audio_gen URL mode.
	// May be nil; URL-mode audio_gen jobs return LLM_INVALID_REQUEST in
	// that case. b64_json mode works without an audioCache.
	audioCache *storage.AudioCache
	// Phase 6a — usage-billing spend-guardrail client. May be nil
	// (router-only tests, dev without usage-billing); settleReservation then
	// no-ops and the usage-billing sweeper releases any leaked hold.
	guardrail *billing.GuardrailClient
	// Phase 6b — transient-retry budget (config JOB_MAX_RETRIES). 0 → a
	// failed upstream call is not retried.
	maxRetries int
	// S3a (G5) — per-provider concurrency governor + circuit-breaker. Both
	// nil when REDIS_URL is unset → ratelimit.Guard passes calls through
	// unchanged (governance disabled; existing tests stay Redis-free).
	gov ratelimit.ConcurrencyGovernor
	brk ratelimit.CircuitBreaker
}

func NewWorker(repo *Repo, resolve CredResolver, adapter AdapterFactory, notifier Notifier, logger *slog.Logger, audioCache *storage.AudioCache, guardrail *billing.GuardrailClient, maxRetries int) *Worker {
	if logger == nil {
		logger = slog.Default()
	}
	if notifier == nil {
		notifier = NoopNotifier{}
	}
	return &Worker{repo: repo, resolve: resolve, adapter: adapter, notifier: notifier, logger: logger, audioCache: audioCache, guardrail: guardrail, maxRetries: maxRetries}
}

// WithGovernance attaches the S3a governor + circuit-breaker (fluent so the
// existing NewWorker call sites and their tests are untouched). Pass untyped-nil
// interfaces to disable a layer — never a typed-nil concrete (see ratelimit.Guard).
func (w *Worker) WithGovernance(gov ratelimit.ConcurrencyGovernor, brk ratelimit.CircuitBreaker) *Worker {
	w.gov = gov
	w.brk = brk
	return w
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
	// Resolve billing identity ONCE (reservation + model) for both the usage
	// outbox (written in the finalize tx) and the reservation settle (after the
	// notification). w.guardrail nil → billing not wired (dev/test).
	var resID *uuid.UUID
	var modelSource string
	var modelRef uuid.UUID
	var billingFound bool
	if w.guardrail != nil {
		var berr error
		resID, modelSource, modelRef, billingFound, berr = w.repo.BillingInfo(ctx, jobID)
		if berr != nil {
			w.logger.Warn("billing info lookup failed", "job_id", jobID.String(), "err", berr)
		}
	}

	// S4b (decision C) + #32 — build the usage-outbox payload. A COMPLETED job with
	// resolvable token usage carries real tokens + the per-model cost (computed ONCE,
	// reused for the reservation reconcile below). #32: failed/cancelled (and a
	// completed job whose tokens didn't resolve) now ALSO emit a row — cost 0 / nil,
	// tokens 0 — so usage-billing audits EVERY call; RequestStatus distinguishes them
	// and the repo attaches the truncated request/response payloads for tracing. Still
	// gated on billingFound (billing wired); a nil cost reconciles at estimate.
	var usage *UsageOutbox
	var cost *float64
	if billingFound {
		requestStatus := "success"
		if status != "completed" {
			requestStatus = status // "failed" | "cancelled"
		}
		var tokIn, tokOut int
		if status == "completed" {
			if ti, to, ok := usageTokens(result); ok {
				tokIn, tokOut = ti, to
				cost = w.actualUSD(ctx, ownerUserID, modelSource, modelRef, result)
			}
		}
		usage = &UsageOutbox{
			ModelSource:   modelSource,
			ModelRef:      modelRef,
			Operation:     operation,
			InputTokens:   tokIn,
			OutputTokens:  tokOut,
			CostUSD:       cost,
			RequestStatus: requestStatus,
		}
	}

	// Finalize + write the usage_outbox row in ONE tx (rows>0 ⇒ transition took
	// effect; a cancel-raced finalize returns 0 and writes nothing — same gate as
	// before). This REPLACES the fire-and-forget RecordUsage HTTP on the jobs path.
	// LLM re-arch Phase 1 — durable, per-job terminal event written in the same
	// finalize tx (relay → loreweave:events:llm_job_terminal). Fires on EVERY
	// terminal status (cost only meaningful for completed). Kind is best-effort
	// (empty here; the Commit-3 queue populates provider kind for routing).
	term := &TerminalOutbox{
		Operation:    operation,
		CostUSD:      cost,
		ErrorCode:    errorCode,
		ErrorMessage: errorMessage,
	}
	rows, err := w.repo.FinalizeWithUsageOutbox(ctx, jobID, ownerUserID, status, result, errorCode, errorMessage, finishReason, usage, term)
	if err != nil {
		// D-CANCEL-FINALIZE-LOG-NOISE — a cancel-race aborts this finalize via the
		// request ctx (context.Canceled). That's harmless: the cancel handler
		// already finalized/emitted/freed the slot. Log it at Debug, not Error, so
		// a normal user-stop doesn't spam the error log. Genuine finalize failures
		// (DB error, etc.) still surface at Error.
		if errors.Is(err, context.Canceled) {
			w.logger.Debug("finalize aborted by cancel-race", "job_id", jobID.String(), "err", err)
		} else {
			w.logger.Error("finalize failed", "job_id", jobID.String(), "err", err)
		}
		return
	}
	if rows == 0 {
		// Race lost — cancel won. Cancel handler already published + released.
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
	// Phase 6a — settle the spend reservation (reconcile or release). Runs only
	// on a real transition (rows > 0). Ordered AFTER the notification
	// (/review-impl LOW#7) so a slow/hung usage-billing call can't delay the
	// terminal event. Reuses the cost computed above (no second pricing read).
	w.settleReservation(ctx, jobID, status, resID, cost)
}

// settleReservation reconciles (completed) or releases (failed) the Phase-6a
// spend reservation, using the identity already resolved by finalizeAndNotify.
// The model-level usage RECORD moved to the usage_outbox (S4b decision C) — the
// jobs path no longer calls RecordUsage. `cost` is the measured spend (nil ⇒
// usage-billing charges the reservation's stored estimate: media / unpriced).
func (w *Worker) settleReservation(ctx context.Context, jobID uuid.UUID, status string, resID *uuid.UUID, cost *float64) {
	if w.guardrail == nil || resID == nil {
		return // billing not wired, or the job carried no reservation
	}
	if status != "completed" {
		// failed — free the hold, no spend. (Cancellation is settled by the
		// cancel handler, not the worker.)
		if relErr := w.guardrail.Release(ctx, *resID); relErr != nil {
			w.logger.Warn("guardrail release failed", "job_id", jobID.String(), "err", relErr)
		}
		return
	}
	if recErr := w.guardrail.Reconcile(ctx, *resID, cost); recErr != nil {
		w.logger.Warn("guardrail reconcile failed", "job_id", jobID.String(), "err", recErr)
	}
}

// usageTokens extracts the input/output token counts from a completed job's
// result `usage` block. ok=false when absent (every media operation).
func usageTokens(result any) (inTok, outTok int, ok bool) {
	rm, isMap := result.(map[string]any)
	if !isMap {
		return 0, 0, false
	}
	usage, isMap := rm["usage"].(map[string]any)
	if !isMap {
		return 0, 0, false
	}
	i, iok := numField(usage, "input_tokens")
	o, ook := numField(usage, "output_tokens")
	if !iok || !ook {
		return 0, 0, false
	}
	return i, o, true
}

// actualUSD computes the measured spend of a completed job from its result
// `usage` block × the model's pricing. Returns nil — "fall back to the stored
// estimate" — whenever the usage tokens or a required price dimension is
// unavailable (notably every media operation, which carries no token usage).
func (w *Worker) actualUSD(ctx context.Context, ownerUserID uuid.UUID, modelSource string, modelRef uuid.UUID, result any) *float64 {
	tokIn, tokOut, ok := usageTokens(result)
	if !ok {
		return nil
	}
	pricing, found, err := w.repo.ModelPricing(ctx, modelSource, ownerUserID, modelRef)
	if err != nil || !found || pricing.InputPerMTok == nil || pricing.OutputPerMTok == nil {
		return nil
	}
	usd := float64(tokIn)/1e6*(*pricing.InputPerMTok) + float64(tokOut)/1e6*(*pricing.OutputPerMTok)
	return &usd
}

// numField extracts a non-negative integer from a JSON-decoded usage map.
// The aggregator stores Go ints; a value that round-tripped through JSON is
// a float64 — both are accepted. ok=false for an absent/negative/other value.
func numField(m map[string]any, key string) (int, bool) {
	var n int
	switch v := m[key].(type) {
	case int:
		n = v
	case int64:
		n = int(v)
	case float64:
		n = int(v)
	default:
		return 0, false
	}
	if n < 0 {
		return 0, false
	}
	return n, true
}

// ProcessJob is the queue-consumer entry point (LLM re-arch Phase 1 Commit 3):
// it loads a job's dispatch fields by id and runs Process. The submit handler
// persisted everything; the queue message carries only the id (small → cheap
// redelivery). Idempotent + redelivery-safe: Process's MarkRunning gate
// (rows==0 ⇒ already cancelled/terminal/claimed) makes a redelivered or
// already-finished job a no-op, so at-least-once delivery is safe. A vanished
// row (ErrNoRows) is logged + dropped (the caller acks). NOTE: a job that
// crashed mid-Process is left `running` and is SKIPPED here (not re-run) — that
// stuck-`running` case is the truth-sweeper's job (spec §5.6), not redelivery's.
func (w *Worker) ProcessJob(ctx context.Context, jobID uuid.UUID) {
	d, err := w.repo.LoadForProcess(ctx, jobID)
	if err != nil {
		// Gone or unreadable — nothing to run. Don't finalize (we have no
		// owner/operation to attribute); the consumer acks + drops.
		w.logger.Warn("queue: load job failed — dropping", "job_id", jobID.String(), "err", err)
		return
	}
	if d.Status != "pending" {
		// Redelivery of an already-claimed/terminal job — no-op (Process's
		// MarkRunning would also catch this, but skip the work up front).
		w.logger.Info("queue: job not pending — skipping", "job_id", jobID.String(), "status", d.Status)
		return
	}
	chunkCfg, decErr := DecodeChunkConfig(d.Chunking)
	if decErr != nil {
		w.finalizeAndNotify(ctx, jobID, d.OwnerUserID, d.Operation, "failed", nil,
			"LLM_INVALID_REQUEST", "invalid chunking config: "+decErr.Error(), "")
		return
	}
	w.Process(ctx, jobID, d.OwnerUserID, d.Operation, d.ModelSource, d.ModelRef, d.Input, chunkCfg)
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
	// Phase 6c — the job span. ctx arrived via observability.DetachedContext
	// (jobs_handler), carrying the submit request's trace_id but not its
	// cancellation; this span re-roots the detached worker under that trace.
	ctx, span := observability.Tracer("jobs").Start(ctx, "llm.job.process",
		trace.WithAttributes(
			attribute.String("llm.operation", operation),
			attribute.String("job.id", jobID.String()),
		))
	defer span.End()

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

	// Phase 5a — audio job dispatch (stt). Routes BEFORE the chat-streaming
	// whitelist because audio ops use adapter.Transcribe (not Stream),
	// have no chunker, and no aggregator. tts is intentionally NOT in
	// audioJobOperations: it streams via /v1/llm/stream only; if it
	// somehow reaches here (jobs_handler should have rejected it at
	// submit), defensive-fail with NOT_SUPPORTED_VIA_JOBS.
	if operation == "tts" {
		w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil,
			"LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS",
			"tts is supported only via /v1/llm/stream",
			"")
		return
	}
	if isAudioJobOperation(operation) {
		w.processAudioJob(ctx, jobID, ownerUserID, operation, modelSource, modelRef, input, logger)
		return
	}

	// Phase 5c-α — image-gen dispatch. Routes BEFORE chat-streaming
	// whitelist because image_gen uses adapter.GenerateImage (not Stream),
	// has no chunker, and no aggregator. Mirrors audio dispatch above.
	if isImageJobOperation(operation) {
		w.processImageGenJob(ctx, jobID, ownerUserID, operation, modelSource, modelRef, input, logger)
		return
	}

	// Phase 5d — video-gen dispatch. Routes BEFORE chat-streaming
	// whitelist because video_gen uses adapter.GenerateVideo (not Stream),
	// has no chunker, and no aggregator. Mirrors image dispatch above
	// with VideoGenJobTimeout=30min ctx (3× longer than image).
	if isVideoJobOperation(operation) {
		w.processVideoGenJob(ctx, jobID, ownerUserID, operation, modelSource, modelRef, input, logger)
		return
	}

	// Phase 4a-α Step 0 — op-whitelist. The chat-streaming machinery +
	// per-op aggregator (cycle 20 jsonListAggregator) is the same wire
	// shape for chat/completion AND for the *_extraction operations:
	// adapter.Stream emits StreamChunks; aggregator routes them to the
	// right result map. The only difference is the aggregator factory
	// (see NewAggregator below). Embedding uses a different upstream HTTP
	// shape — it stays gated until its dedicated cycle wires an adapter.
	// (image_gen now has dispatch above; translation is chat-shaped and is
	// whitelisted in streamableOperations.)
	if !isStreamableOperation(operation) {
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

	// D-PROVIDER-CONCURRENCY-CONFIG — the concurrency class (credential id) +
	// its cap (NULL → 0 = unlimited). Fail-open: if the lookup errors, fall back
	// to the provider kind as the class + unlimited, so a transient DB hiccup
	// never wedges a job. (repo is non-nil here — MarkRunning ran above.)
	concClass, concLimit := providerKind, 0
	if k, lim, ok, cerr := w.repo.ResolveConcurrency(ctx, modelSource, ownerUserID, modelRef); cerr != nil {
		logger.Warn("resolve concurrency failed — defaulting to unlimited", "err", cerr)
	} else if ok {
		concClass, concLimit = k, lim
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
		if err := w.processChunks(ctx, jobID, agg, adapter, concClass, concLimit, endpointBaseURL, secret, providerModelName, inputMap, chunkPieces, emit, logger); err != nil {
			errCode := classifyStreamErrorCode(err)
			w.finalizeAndNotify(ctx, jobID, ownerUserID, operation, "failed", nil, errCode, err.Error(), "")
			return
		}
	} else {
		// Single-call Phase 2b path with Phase 4a-α Step 0b transient retry.
		streamErr := w.streamWithRetry(ctx, agg, adapter, concClass, concLimit, endpointBaseURL, secret, providerModelName, inputMap, emit, logger)
		if streamErr != nil {
			logger.Error("stream failed", "err", streamErr)
			errCode := classifyStreamErrorCode(streamErr)
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
//
// Phase 6b — each chunk retries on its OWN budget (Worker.maxRetries), no
// longer a single budget shared across all chunks. One chunk's transient
// failure no longer starves the rest. A pathological N-chunk job is still
// bounded (N·maxRetries worst case, capped backoff; if every chunk fails the
// upstream is down and the job fails anyway).
func (w *Worker) processChunks(
	ctx context.Context,
	jobID uuid.UUID,
	agg Aggregator,
	adapter provider.Adapter,
	concClass string,
	concLimit int,
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
		streamErr := retryTransient(ctx, w.maxRetries, logger, func() error {
			// StartChunk resets the per-chunk buffer — so a retry after a
			// partial stream discards that attempt's partial (Phase 6b).
			agg.StartChunk(i)
			// S3a: governor + circuit-breaker wrap the provider call. Inside
			// retryTransient so each retry re-checks the breaker + re-acquires
			// a slot, and a transient failure counts toward opening.
			return ratelimit.Guard(ctx, w.gov, w.brk, concClass, concLimit, provider.IsTransientUpstreamError, func() error {
				return adapter.Stream(ctx, endpointBaseURL, secret, providerModelName, perChunkInput, emit)
			})
		})
		if streamErr != nil {
			// EndChunk is NOT called on failure: the job fails and the
			// aggregator result is discarded, so committing this chunk's
			// partial buffer would only be a latent trap if processChunks
			// ever returned a partial result (/review-impl Phase 6b #4).
			logger.Error("chunk stream failed", "chunk", i, "err", streamErr)
			return streamErr
		}
		agg.EndChunk(i)
		// Progress update so polling shows N/total. Best-effort; the
		// nil-repo guard keeps processChunks unit-testable without a DB.
		if w.repo != nil {
			_ = w.repo.UpdateProgress(ctx, jobID, totalPtr, i+1, 0)
		}
	}
	return nil
}

// streamWithRetry runs the single-call (unchunked) stream with transient
// retry — Phase 6b. Exponential backoff via retryTransient; the budget is
// Worker.maxRetries. Non-transient errors propagate immediately.
//
// agg.StartChunk(0) is called inside the retry op so a retry after a
// partial stream discards that attempt's accumulated tokens — the same
// reset discipline as processChunks. Without it, a transient failure
// mid-stream followed by a successful retry would double-accumulate the
// re-emitted deltas into the aggregator (/review-impl Phase 6b #2).
// StartChunk(0)/EndChunk(0) on a single chunk is behaviour-equivalent to
// the unframed Phase 2b path for both aggregator types.
func (w *Worker) streamWithRetry(
	ctx context.Context,
	agg Aggregator,
	adapter provider.Adapter,
	concClass string,
	concLimit int,
	endpointBaseURL, secret, providerModelName string,
	input map[string]any,
	emit EmitFn,
	logger *slog.Logger,
) error {
	err := retryTransient(ctx, w.maxRetries, logger, func() error {
		agg.StartChunk(0)
		// S3a: governor + circuit-breaker wrap the provider call (see processChunks).
		return ratelimit.Guard(ctx, w.gov, w.brk, concClass, concLimit, provider.IsTransientUpstreamError, func() error {
			return adapter.Stream(ctx, endpointBaseURL, secret, providerModelName, input, emit)
		})
	})
	if err != nil {
		// EndChunk skipped on failure — the failed job's result is
		// discarded (consistent with processChunks, /review-impl 6b #4).
		return err
	}
	agg.EndChunk(0)
	return nil
}

// classifyStreamErrorCode picks the canonical LLM_* error code for a
// stream failure so finalizeAndNotify can emit a stable error envelope.
func classifyStreamErrorCode(err error) string {
	if errors.Is(err, ratelimit.ErrCircuitOpen) {
		return "LLM_CIRCUIT_OPEN" // S3a: provider circuit open — failed fast, provider untouched
	}
	if err == provider.ErrStreamNotSupported {
		return "LLM_STREAM_NOT_SUPPORTED"
	}
	var rl *provider.ErrUpstreamRateLimited
	if errors.As(err, &rl) {
		return "LLM_RATE_LIMITED"
	}
	return "LLM_UPSTREAM_ERROR"
}

// EmitFn aliases provider.EmitFn so the worker doesn't redeclare types.
type EmitFn = func(provider.StreamChunk) error

// streamableOperations is the whitelist of Job operations that the worker
// dispatches through adapter.Stream. They share the same wire shape (chat
// messages → SSE token deltas) but get different per-op aggregators via
// NewAggregator(operation). Operations not in this set fail fast with
// LLM_OPERATION_NOT_SUPPORTED — kept that way until their dedicated
// adapters land (embedding/image_gen have different upstream HTTP shapes).
//
// stt is NOT here — it routes through audioJobOperations + adapter.Transcribe.
// tts is NOT here — it streams only via /v1/llm/stream.
var streamableOperations = map[string]struct{}{
	"chat":                {},
	"completion":          {},
	"entity_extraction":   {},
	"relation_extraction": {},
	"event_extraction":    {},
	"fact_extraction":     {}, // Phase 4a-β
	"summarize_level":     {}, // P3 hierarchical reduce — chat-shaped, default aggregator
	// translation-service submits operation="translation" via the SDK. It is
	// chat-shaped (prompt → text completion; the block translator does its own
	// marker-based parsing of result.content), so it uses the default
	// chatAggregator. Was previously gated here → LLM_OPERATION_NOT_SUPPORTED,
	// which silently broke every chapter translation (caught by the TR-4 live
	// acceptance run, 2026-05-31).
	"translation": {},
}

// audioJobOperations — Phase 5a. Job operations dispatched through
// adapter.Transcribe (not adapter.Stream). Audio jobs run as a single
// upstream call → single result; no chunker, no aggregator.
//
// Invariant (regression-locked by TestStreamableAudio_Disjoint):
// streamableOperations ∩ audioJobOperations = ∅. Routing in Process()
// checks audio first, then streamable, ensuring no operation is in both
// dispatch paths.
var audioJobOperations = map[string]struct{}{
	"stt":       {},
	"audio_gen": {}, // Phase 5e-β.2 — batch TTS via /v1/llm/jobs
}

// isStreamableOperation reports whether the worker can dispatch the given
// operation through the chat-streaming machinery + per-op aggregator.
func isStreamableOperation(op string) bool {
	_, ok := streamableOperations[op]
	return ok
}

// isAudioJobOperation reports whether the worker dispatches the operation
// through the audio-job path (adapter.Transcribe → SttResult). Phase 5a.
func isAudioJobOperation(op string) bool {
	_, ok := audioJobOperations[op]
	return ok
}

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
