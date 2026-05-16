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
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/chunker"
	"github.com/loreweave/provider-registry-service/internal/provider"
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
	// (router-only tests, dev without usage-billing); settleBilling then
	// no-ops and the usage-billing sweeper releases any leaked hold.
	guardrail *billing.GuardrailClient
}

func NewWorker(repo *Repo, resolve CredResolver, adapter AdapterFactory, notifier Notifier, logger *slog.Logger, audioCache *storage.AudioCache, guardrail *billing.GuardrailClient) *Worker {
	if logger == nil {
		logger = slog.Default()
	}
	if notifier == nil {
		notifier = NoopNotifier{}
	}
	return &Worker{repo: repo, resolve: resolve, adapter: adapter, notifier: notifier, logger: logger, audioCache: audioCache, guardrail: guardrail}
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
		// The cancel handler also releases the spend reservation.
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
	// Phase 6a — settle the spend reservation (reconcile or release). Runs
	// only on a real transition (rows > 0), so a job whose finalize lost to
	// a cancel is settled by the cancel handler, not double-counted here.
	// Ordered AFTER the notification (/review-impl LOW#7) so a slow/hung
	// usage-billing call cannot delay the terminal event.
	w.settleBilling(ctx, jobID, ownerUserID, operation, status, result)
}

// settleBilling settles a terminal job's billing — Phase 6a + 6a-β. Two
// independent best-effort steps: (1) reconcile/release the spend reservation
// (Subsystem A + B); (2) on a completed job, record model-level usage to the
// /record audit ledger (the gateway as biller). A usage-billing failure is
// logged, never propagated.
func (w *Worker) settleBilling(ctx context.Context, jobID, ownerUserID uuid.UUID, operation, status string, result any) {
	if w.guardrail == nil {
		return // billing not wired
	}
	resID, modelSource, modelRef, found, err := w.repo.BillingInfo(ctx, jobID)
	if err != nil {
		w.logger.Warn("billing info lookup failed", "job_id", jobID.String(), "err", err)
		return
	}
	if !found {
		return // no job row — nothing to settle or record
	}

	// (1) Spend reservation — only when the job carries one.
	if resID != nil {
		if status != "completed" {
			// failed — free the hold, record no spend. (Cancellation is
			// settled by the cancel handler, not the worker.)
			if relErr := w.guardrail.Release(ctx, *resID); relErr != nil {
				w.logger.Warn("guardrail release failed", "job_id", jobID.String(), "err", relErr)
			}
		} else {
			// completed — reconcile. A non-nil actual is the measured
			// spend; nil tells usage-billing to charge the reservation's
			// own estimate (media jobs, or usage/pricing unresolved).
			actual := w.actualUSD(ctx, ownerUserID, modelSource, modelRef, result)
			if recErr := w.guardrail.Reconcile(ctx, *resID, actual); recErr != nil {
				w.logger.Warn("guardrail reconcile failed", "job_id", jobID.String(), "err", recErr)
			}
		}
	}

	// (2) Phase 6a-β — model-level usage record (gateway as biller). Only on
	// a completed job with resolvable token usage; request_id = job_id so a
	// settle retry is idempotent on the usage-billing side.
	if status == "completed" {
		if tokIn, tokOut, ok := usageTokens(result); ok {
			if recErr := w.guardrail.RecordUsage(ctx, billing.UsageRecord{
				RequestID:    jobID,
				OwnerUserID:  ownerUserID,
				ModelSource:  modelSource,
				ModelRef:     modelRef,
				Operation:    operation,
				InputTokens:  tokIn,
				OutputTokens: tokOut,
			}); recErr != nil {
				w.logger.Warn("usage record failed", "job_id", jobID.String(), "err", recErr)
			}
		}
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
	// (see NewAggregator below). Embedding/translation use different
	// upstream HTTP shapes — those stay gated until their dedicated
	// cycles wire adapters. (image_gen now has dispatch above.)
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
		// Single-call Phase 2b path with Phase 4a-α Step 0b transient retry.
		streamErr := w.streamWithRetry(ctx, adapter, endpointBaseURL, secret, providerModelName, inputMap, emit, logger)
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
// Phase 4a-α Step 0b + /review-impl MED#5 — transient retry budget is
// JOB-LEVEL (shared across all chunks), NOT per-chunk. A 9-chunk job
// gets ONE retry total, not 9. This bounds upstream-call amplification
// under sustained transient errors and matches the SDK's caller-side
// budget=1 contract.
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
	budget := 1 // shared across all chunks
	for i, piece := range chunks {
		perChunkInput, err := SubstituteLastUserMessage(inputMap, piece)
		if err != nil {
			return fmt.Errorf("substitute chunk %d: %w", i, err)
		}
		agg.StartChunk(i)
		streamErr := w.streamWithBudget(ctx, adapter, endpointBaseURL, secret, providerModelName, perChunkInput, emit, &budget, logger)
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

// streamWithRetry — single-call (unchunked) path. Owns its own budget=1
// because there are no other chunks to share with. Wraps streamWithBudget.
func (w *Worker) streamWithRetry(
	ctx context.Context,
	adapter provider.Adapter,
	endpointBaseURL, secret, providerModelName string,
	input map[string]any,
	emit EmitFn,
	logger *slog.Logger,
) error {
	budget := 1
	return w.streamWithBudget(ctx, adapter, endpointBaseURL, secret, providerModelName, input, emit, &budget, logger)
}

// streamWithBudget calls adapter.Stream with retry on transient upstream
// errors (rate-limit / 5xx / network timeout) consuming from a SHARED
// budget pointer. The pointer enables job-level (cross-chunk) budget per
// /review-impl MED#5: a 9-chunk job gets ONE retry total, not 9.
//
// Honors `Retry-After` from rate-limit responses; falls back to a fixed
// 1s backoff otherwise. Non-transient errors (4xx other than 429,
// ErrStreamNotSupported, etc.) propagate immediately without retry.
//
// When *budget reaches 0 a transient error propagates as failure — caller
// (worker.processChunks or worker.Process single-call path) finalizes
// the job with the appropriate error code. Budget is NOT replenished
// across chunks so a slow drain still terminates.
//
// Replaces knowledge-service's K17.3 caller-side retry loop — Phase 4a
// migration drops K17.3 so this gateway-side retry MUST cover the same
// quality contract. Phase 6b will replace with exponential backoff +
// per-user budget.
func (w *Worker) streamWithBudget(
	ctx context.Context,
	adapter provider.Adapter,
	endpointBaseURL, secret, providerModelName string,
	input map[string]any,
	emit EmitFn,
	budget *int,
	logger *slog.Logger,
) error {
	const fixedBackoffS = 1.0
	for {
		err := adapter.Stream(ctx, endpointBaseURL, secret, providerModelName, input, emit)
		if err == nil {
			return nil
		}
		if !provider.IsTransientUpstreamError(err) {
			return err
		}
		if *budget <= 0 {
			logger.Warn("transient retry budget exhausted (job-level)", "err", err)
			return err
		}
		*budget--
		wait := provider.RetryAfter(err)
		if wait <= 0 {
			wait = fixedBackoffS
		}
		logger.Info("transient upstream error — retrying", "err", err, "wait_s", wait, "remaining_budget", *budget)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Duration(wait * float64(time.Second))):
		}
	}
}

// classifyStreamErrorCode picks the canonical LLM_* error code for a
// stream failure so finalizeAndNotify can emit a stable error envelope.
func classifyStreamErrorCode(err error) string {
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
// adapters land (embedding/translation/image_gen).
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
