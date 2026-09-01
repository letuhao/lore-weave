package api

// stream_billing.go — Phase 6a-δ streaming spend guardrail.
//
// A stream is not a job, but it reuses the 6a reserve/reconcile machinery via
// a synthetic job_id. preflightStream reserves the worst-case cost before the
// SSE prelude; streamGuard.observe maintains a running output tally and
// signals a hard-abort if a runaway crosses the caller's available budget;
// streamGuard.settle reconciles the real spend at stream end.
//
// See docs/03_planning/LLM_PIPELINE_PHASE6A_DELTA_DESIGN.md.

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/observability"
	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/provider"
)

// errStreamBudgetExceeded is returned by the emit closure when the running
// tally trips the hard-abort. It propagates up through adapter.Stream so the
// upstream connection is closed; streamChat recognises it (via the guard's
// aborted flag) and does not emit a second error frame.
var errStreamBudgetExceeded = errors.New("stream aborted: budget exceeded")

// streamGuard carries the spend-guardrail state for one stream.
type streamGuard struct {
	guardrail     *billing.GuardrailClient
	reservationID uuid.UUID
	// jobID is the synthetic per-stream id used as the reservation's
	// request_id AND as RecordUsage's request_id (the /record
	// idempotency key, D-PHASE6A-BETA-STREAM-RECORD). Mirrors the
	// jobs.Worker.settleBilling pattern where the llm_jobs row id
	// serves both roles.
	jobID       uuid.UUID
	ownerUserID uuid.UUID
	modelSource string // "user_model" | "platform_model"
	modelRef    uuid.UUID
	op          string // "chat" | "tts"
	pricing     billing.Pricing
	// providerKind — D-BILL-PROVIDER-KIND. The chat stream is the highest-volume
	// producer of usage_logs rows; without this the /record payload hardcoded "" and
	// the dominant traffic was unattributable.
	providerKind string

	// chat-only running tally.
	inputCostUSD float64 // fixed: estimated input tokens × input price
	inputTokens  int     // P0-2: estimated input token count (the record's input_tokens when no final usage chunk arrives)
	abortUSD     float64 // hard-abort threshold = caller's available budget
	outChars     int     // accumulated output delta chars (token + reasoning)
	outNonASCII  int
	finalUsage   *provider.StreamChunk // last usage chunk seen, if any
	aborted      bool                  // observe tripped the hard-abort
	// D-UPSTREAM-ERROR-WITH-NO-MESSAGE - an error chunk was forwarded to the caller. The
	// streamers report a provider failure by EMITTING one and then returning the normal
	// end-of-stream sentinel, so streamErr is nil and the terminal classifier below scored
	// the failure as `success`. See finalizeOutcome.
	errorEmitted bool
	errorCode    string
	errorMessage string

	// P0-2 (B1/B2 — full request/response logging). requestPayload is the assembled
	// provider request (post-injection, bounded); completion accumulates the visible
	// streamed answer (token deltas only, capped) for the audit response payload;
	// requestStatus is the terminal outcome set by finalizeOutcome at stream end.
	requestPayload map[string]any
	completion     strings.Builder
	requestStatus  string

	// startedAt stamps the stream's open so finalizeOutcome can say how long a
	// silent one stayed silent. See the terminal log line there.
	startedAt time.Time
}

// preflightStream runs the streaming spend-guardrail pre-flight: estimate the
// worst-case cost, reserve it, and build the streamGuard. It MUST be called
// before the SSE prelude — on a rejection it writes the HTTP error itself and
// returns ok=false. When the guardrail is not wired (s.guardrail nil — a
// Server built as a bare literal in unit tests) it returns (nil, true): the
// stream proceeds unguarded and the nil-safe observe/settle no-op.
func (s *Server) preflightStream(
	w http.ResponseWriter, r *http.Request,
	userID uuid.UUID, op, modelSource string, modelRef uuid.UUID,
	pricing billing.Pricing, inputMap map[string]any, providerKind string,
) (*streamGuard, bool) {
	if s.guardrail == nil {
		return nil, true
	}

	// A stream is never chunked → nchunks = 1. chat worst-case output =
	// max_tokens (or the config default); tts cost is exact.
	estimate, err := s.estimator.EstimateUSD(op, inputMap, pricing, 1)
	if errors.Is(err, billing.ErrUnpriced) {
		writeError(w, http.StatusPaymentRequired, "LLM_QUOTA_EXCEEDED", "model pricing not configured")
		return nil, false
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "cost estimate failed")
		return nil, false
	}

	// ── Context-window gate (D-CHAT-CONTEXT-OVERFLOW) — DEFAULT-ON ────────────────
	// The JOBS path (jobs_handler preflight) already rejects requests that overflow
	// the model's window, but the STREAM path historically SKIPPED it (chat omits
	// max_tokens, "server decides"). That gap poisons chat SPECIFICALLY: a bloated
	// assembled prompt (every tool schema + grounding + re-sent history over a
	// multi-pass tool loop) OVERFLOWS the window, and llama.cpp/LM Studio SILENTLY
	// TRUNCATES it — so the model reasons over a CLIPPED prompt and degrades (loops,
	// mis-routes tools, "gets dumb"). Pipelines never hit this (they ARE gated) —
	// which matches the observed "loops only in chat, never in one-shot/pipeline"
	// signature. Gate on INPUT + safety; also LOG the input size every turn so the
	// bloat is monitorable (the metric that was missing). Skipped only when the
	// model's context_length is unknown (NULL/legacy/platform rows).
	if s.jobsRepo != nil {
		if ctxLen, ctxFound, ctxErr := s.jobsRepo.ModelContextLength(r.Context(), modelSource, userID, modelRef); ctxErr == nil && ctxFound && ctxLen > 0 {
			inTokens := s.estimator.InputTokens(inputMap, 1)
			safety := ctxLen * 15 / 100 // mirror the jobs-path + Python ContextBudget 15%
			if inTokens+safety > ctxLen {
				slog.Warn("chat context overflow — assembled prompt exceeds model window",
					"input_tokens", inTokens, "safety", safety, "context_length", ctxLen,
					"model_ref", modelRef.String(), "op", op)
				writeError(w, http.StatusBadRequest, "LLM_CONTEXT_OVERFLOW", fmt.Sprintf(
					"the assembled prompt overflows this model's context window: input=%d + safety=%d = %d > context_length=%d — reduce injected context (tools/grounding/history) or use a larger-window model",
					inTokens, safety, inTokens+safety, ctxLen))
				return nil, false
			}
			// Metric — even when it FITS, record the real input size + headroom so a
			// creeping bloat is visible before it overflows.
			slog.Info("chat context preflight", "input_tokens", inTokens,
				"context_length", ctxLen, "headroom", ctxLen-inTokens,
				"pct_used", inTokens*100/ctxLen, "model_ref", modelRef.String())
		}
	}

	jobID, err := uuid.NewV7() // synthetic — a stream has no llm_jobs row
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to allocate stream id")
		return nil, false
	}
	// The synchronous stream path is first-party only (public MCP keys reach
	// priced capability via the async jobs path, where the per-key cap is
	// enforced); pass nil cap here. If a public-key stream path is ever added,
	// thread the carrier through like doSubmitJob.
	res, err := s.guardrail.Reserve(r.Context(), userID, jobID, estimate, modelSource, nil, nil)
	if err != nil {
		// Fail closed — no stream opens on an unconfirmed reservation.
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "billing service unavailable")
		return nil, false
	}
	if res.Insufficient {
		writeBudget402(w, res)
		return nil, false
	}

	g := &streamGuard{
		startedAt:     time.Now(),
		guardrail:     s.guardrail,
		reservationID: res.ReservationID,
		jobID:         jobID,
		ownerUserID:   userID,
		modelSource:   modelSource,
		modelRef:      modelRef,
		op:            op,
		pricing:       pricing,
		providerKind:  providerKind,
		abortUSD:      minFloat(res.DailyAvailable, res.MonthlyAvailable),
	}
	if op == "chat" {
		// EstimateUSD("chat") succeeded → both text price dimensions are
		// present (textCost requires them), so the deref below is safe.
		g.inputTokens = s.estimator.InputTokens(inputMap, 1)
		g.inputCostUSD = float64(g.inputTokens) / 1e6 * (*pricing.InputPerMTok)
	}
	return g, true
}

// observe accounts one streamed chunk against the running tally. It returns
// abort=true when the chat tally crosses the caller's available budget — a
// runaway the gateway must stop mid-flight. A tts stream never aborts (its
// cost was fixed and fully reserved up front). Nil-safe.
func (g *streamGuard) observe(chunk provider.StreamChunk) (abort bool) {
	if g == nil || g.op != "chat" {
		return false
	}
	switch chunk.Kind {
	case provider.StreamChunkToken, provider.StreamChunkReasoning:
		// Reasoning deltas bill as output tokens too.
		c, n := billing.CountScriptChars(chunk.Delta)
		g.outChars += c
		g.outNonASCII += n
		// P0-2 (B1) — accumulate the VISIBLE completion (token deltas) for the audit
		// response payload, capped at usagePayloadCapBytes so a runaway stream can't
		// balloon the record. Reasoning deltas count toward billing but are hidden
		// thinking, so they're not stored in the logged answer.
		if chunk.Kind == provider.StreamChunkToken && g.completion.Len() < usagePayloadCapBytes {
			g.completion.WriteString(chunk.Delta)
		}
		if g.tallyCostUSD() > g.abortUSD {
			g.aborted = true
		}
		return g.aborted
	case provider.StreamChunkUsage:
		uc := chunk // copy — chunk is a loop-scoped value at the call site
		g.finalUsage = &uc
	case provider.StreamChunkError:
		// 🔴 THE WITNESS REPORTED SUCCESS ON THE FAILURE IT WAS BUILT TO DESCRIBE. Every
		// streamer signals a provider failure the same way: emit a StreamChunkError, then
		// `return errStreamDone` — the SAME sentinel a clean end-of-stream returns. So
		// streamChat hands finalizeOutcome a nil error and the stream is recorded `success`
		// in usage_logs and in the terminal log line.
		//
		// MEASURED 2026-09-01 on the first reproducible instance this row has had. A turn
		// that died with `upstream sent "error" with no error message` logged, from this
		// process: status='success' usage=false chars=0 duration_ms=431. Two rows spent
		// weeks narrowing to this hop, and when they finally got a line out of it, the line
		// said the opposite of what happened.
		//
		// Recorded here rather than in each streamer because this is the one place every
		// streamer's chunks pass through — the openai, anthropic and responses paths all
		// return the same sentinel from their own error branch, and a per-streamer fix would
		// have to be repeated three times and remembered for the fourth.
		if !g.errorEmitted {
			g.errorEmitted = true
			g.errorCode, g.errorMessage = chunk.Code, chunk.Message
		}
	}
	return false
}

// didAbort reports whether observe tripped the hard-abort. Nil-safe.
func (g *streamGuard) didAbort() bool {
	return g != nil && g.aborted
}

// captureRequest stores the assembled provider request (post-injection) so settle
// can log it as the audit input payload (P0-2 B1). Nil-safe. Bounded by the caller.
func (g *streamGuard) captureRequest(payload map[string]any) {
	if g != nil {
		g.requestPayload = payload
	}
}

// finalizeOutcome classifies the stream's terminal outcome from the streamChat
// error so settle records the real request_status (P0-2 B2) — success on a clean
// finish, aborted on a budget hard-abort, cancelled on client disconnect, and
// provider_error on any other upstream failure. Nil-safe.
func (g *streamGuard) finalizeOutcome(streamErr error) {
	if g == nil {
		return
	}
	switch {
	case g.aborted:
		g.requestStatus = "aborted"
	case errors.Is(streamErr, context.Canceled) || errors.Is(streamErr, context.DeadlineExceeded):
		g.requestStatus = "cancelled"
	case streamErr != nil:
		g.requestStatus = "provider_error"
	case g.errorEmitted:
		// The stream told its CALLER it had failed and then returned the clean-finish
		// sentinel. A success here is not a mislabel, it is the audit row disagreeing with
		// what the client was actually sent.
		g.requestStatus = "provider_error"
	default:
		g.requestStatus = "success"
	}

	// ── D-TURN-STALLS-AFTER-THE-SURFACE-IS-BUILT / D-UPSTREAM-ERROR-WITH-NO-MESSAGE ──
	//
	//	THE INVARIANT. A stream that logged its START logs how it ENDED.
	//
	// This is the one hop two defect rows spent weeks narrowing to and then could not cross.
	// Both recorded the same wall: provider-registry emits `chat context preflight` and then
	// NOTHING — the identical single line for a turn that completes and for a turn that hangs
	// forever — so "did the call to the provider ever return?" had no witness on either side,
	// and a call that was never made was indistinguishable from one that never came back.
	//
	// THE MECHANISM WAS ALREADY HERE AND MERELY SILENT. The terminal status is computed right
	// above and has been recorded to `usage_logs` all along; it was simply never emitted, and
	// `streamErr` — the only place the provider's actual failure exists in this process — was
	// classified into one word and then dropped on the floor. Nothing new is measured below.
	// Every field was already in hand at the moment the information was being destroyed.
	//
	// `usage` is the field those rows actually needed: it says whether the provider sent a
	// final usage chunk, which distinguishes "the call returned" from "the stream opened and
	// nothing ever came back". `duration_ms` gives a silent stream a length.
	lg := []any{
		"status", g.requestStatus,
		"op", g.op,
		"model_ref", g.modelRef.String(),
		"duration_ms", time.Since(g.startedAt).Milliseconds(),
		"output_chars", g.outChars,
		"usage", g.finalUsage != nil,
	}
	if streamErr != nil {
		// The provider's own words, not a category. A row that reads "provider reported a
		// failure without saying why" was written because this string had nowhere to go.
		lg = append(lg, "err", streamErr.Error())
	}
	if g.errorEmitted {
		// The error the CALLER was sent. On every streamer this travels as a chunk and never
		// as `streamErr`, so without these two fields the failure the client saw appears in
		// this process's log as nothing at all — which is how a turn that died upstream came
		// to be recorded here as a success with no err field to contradict it.
		lg = append(lg, "chunk_err_code", g.errorCode, "chunk_err", g.errorMessage)
	}
	if g.requestStatus == "success" {
		slog.Info("chat stream finished", lg...)
	} else {
		slog.Warn("chat stream finished", lg...)
	}
}

// settle reconciles the stream's spend reservation at stream end. Runs
// unconditionally (deferred) — normal completion, hard-abort, upstream error,
// and client disconnect all reach here. Best-effort: a usage-billing failure
// is logged, never propagated; the sweeper is the backstop. Nil-safe.
func (g *streamGuard) settle(ctx context.Context) {
	if g == nil || g.guardrail == nil {
		return
	}
	// Phase 6c — settle runs detached (ctx from observability.DetachedContext
	// at the deferred call site); this span re-roots it under the stream's
	// trace so the reconcile is not an orphan.
	ctx, span := observability.Tracer("stream").Start(ctx, "llm.stream.settle")
	defer span.End()

	// D-BILL-NO-USAGE-ON-PREFLIGHT-ERROR — a chat provider_error that produced NEITHER a
	// usage chunk NOR any output delta is a PRE-PROCESSING rejection (real OpenAI's 400
	// "reasoning.effort unsupported_parameter", a context-overflow 400, a 401): the provider
	// consumed no prefill and billed us NOTHING, so reconciling/recording the ESTIMATED
	// input tokens (g.inputTokens, stamped up-front in preflight) fabricates cost the user
	// never incurred — and the user-facing spend summary (server.go usage rollup) sums it
	// unfiltered. Zero it. Scope is deliberately tight: a MID-STREAM provider_error
	// (outChars>0) or one that carried a usage chunk (finalUsage!=nil) DID spend real
	// tokens; an aborted stream (real output) and a client-cancelled stream (provider
	// likely prefilled) keep their existing billing. Only "errored before producing
	// anything" is refunded.
	noProviderWork := g.op == "chat" && g.requestStatus == "provider_error" &&
		g.finalUsage == nil && g.outChars == 0

	var actual *float64
	switch {
	case noProviderWork:
		// Provider did no work → reconcile the reservation to $0 (releases the hold).
		zero := 0.0
		actual = &zero
	case g.op == "tts":
		// tts cost is exact (text known up front) → reconcile at the
		// reservation's stored estimate.
		actual = nil
	case g.finalUsage != nil:
		// Authoritative provider token counts.
		a := g.usageCostUSD(*g.finalUsage)
		actual = &a
	default:
		// No usage chunk (client disconnect, abort, or the provider
		// omitted it) → the delta-estimated running tally.
		a := g.tallyCostUSD()
		actual = &a
	}
	if err := g.guardrail.Reconcile(ctx, g.reservationID, actual); err != nil {
		slog.Warn("stream guardrail reconcile failed",
			"reservation_id", g.reservationID.String(), "err", err)
	}

	// P0-2 (B1/B2). Mirror jobs.Worker.settleBilling step (2): after the reservation
	// is reconciled, write a model-level `usage_logs` audit row via
	// /internal/model-billing/record so streaming chat appears in the same per-model
	// spend ledger — AND carries the assembled request + accumulated completion so the
	// highest-volume path is no longer audit-invisible.
	//
	// B2 fix: record on EVERY terminal status (success, provider_error, aborted,
	// cancelled), not just a clean-finish-with-usage. An aborted/disconnected stream
	// still spent real tokens + produced partial output; recording zero rows for it is
	// the audit hole. When the provider sent a final usage chunk we use its
	// authoritative token counts; otherwise we fall back to the delta-estimated tally
	// (the same numbers reconcile already used). tts is exempt — its cost is per-char,
	// not per-token, and it has no completion text to log.
	//
	// Best-effort: a failure is logged, never propagated; the sweeper is the backstop.
	// RequestID = jobID so a retry is idempotent on the usage-billing side.
	if g.op == "chat" {
		status := g.requestStatus
		if status == "" {
			status = "success"
		}
		inTok, outTok := g.inputTokens, billing.EstimateTokens(g.outChars, g.outNonASCII)
		if g.finalUsage != nil {
			reasoning := 0
			if g.finalUsage.ReasoningTokens != nil {
				reasoning = *g.finalUsage.ReasoningTokens
			}
			inTok = g.finalUsage.InputTokens
			outTok = g.finalUsage.OutputTokens + reasoning
		}
		if noProviderWork {
			// Matches the $0 reconcile above: the provider did no work, so the audit row
			// records 0 tokens (TotalCostUSD=actual is already 0). The row is still
			// WRITTEN — a rejected turn stays visible in the ledger as an error, it just
			// carries no fabricated spend.
			inTok, outTok = 0, 0
		}
		// LOW-1: bound the completion the same way the input payload is bounded
		// (stream_handler buildChatStreamInput → boundedPayload) so a very long
		// generation is logged by reference, not shipped inline. Symmetric with the
		// sync path (recordSyncUsage bounds both sides).
		var outPayload map[string]any
		if c := g.completion.String(); c != "" {
			outPayload = boundedPayload(map[string]any{"content": c})
		}
		if err := g.guardrail.RecordUsage(ctx, billing.UsageRecord{
			RequestID:     g.jobID,
			OwnerUserID:   g.ownerUserID,
			ProviderKind:  g.providerKind,
			ModelSource:   g.modelSource,
			ModelRef:      g.modelRef,
			Operation:     g.op,
			InputTokens:   inTok,
			OutputTokens:  outTok,
			RequestStatus: status,
			InputPayload:  g.requestPayload,
			OutputPayload: outPayload,
			TotalCostUSD:  actual, // authoritative per-model cost (matches reconcile)
		}); err != nil {
			slog.Warn("stream usage record failed",
				"request_id", g.jobID.String(), "err", err)
		}
	}
}

// tallyCostUSD is the running cost from the delta-estimated output so far.
func (g *streamGuard) tallyCostUSD() float64 {
	outPerTok := 0.0
	if g.pricing.OutputPerMTok != nil {
		outPerTok = *g.pricing.OutputPerMTok / 1e6
	}
	outTokens := billing.EstimateTokens(g.outChars, g.outNonASCII)
	return g.inputCostUSD + float64(outTokens)*outPerTok
}

// usageCostUSD prices an authoritative usage chunk. Reasoning tokens bill at
// the output rate.
func (g *streamGuard) usageCostUSD(u provider.StreamChunk) float64 {
	inPerMTok, outPerMTok := 0.0, 0.0
	if g.pricing.InputPerMTok != nil {
		inPerMTok = *g.pricing.InputPerMTok
	}
	if g.pricing.OutputPerMTok != nil {
		outPerMTok = *g.pricing.OutputPerMTok
	}
	out := u.OutputTokens
	if u.ReasoningTokens != nil {
		out += *u.ReasoningTokens
	}
	// Prompt-cache-aware INPUT pricing (2026 standard; the LiteLLM #19681 bug class:
	// billing cached tokens at the full rate over-charges up to ~11× on a mostly-cached
	// prompt). InputTokens is the FULL billed volume; the provider-normalized split lets us
	// price each part correctly:
	//   cache READ  (served from cache) → discounted (default 0.5×; GPT-5.x/Anthropic ~0.1×
	//               via the configured CachedInputPerMTok),
	//   cache WRITE (Anthropic cache_creation) → 1.25× premium,
	//   UNCACHED    → full input rate.
	// Providers reporting no cache activity (LM Studio) have read=creation=0, so this
	// reduces EXACTLY to InputTokens×inPerMTok — zero behavior change on the local path.
	read, creation := 0, 0
	if u.CacheReadTokens != nil {
		read = *u.CacheReadTokens
	}
	if u.CacheCreationTokens != nil {
		creation = *u.CacheCreationTokens
	}
	uncached := max(0, u.InputTokens-read-creation)
	cachedPerMTok := inPerMTok * 0.5 // conservative default (OpenAI floor; never over-discounts)
	if g.pricing.CachedInputPerMTok != nil {
		cachedPerMTok = *g.pricing.CachedInputPerMTok
	}
	inputCost := (float64(uncached)*inPerMTok +
		float64(read)*cachedPerMTok +
		float64(creation)*inPerMTok*1.25) / 1e6
	return inputCost + float64(out)/1e6*outPerMTok
}

// minFloat returns the smaller of two float64s.
func minFloat(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}
