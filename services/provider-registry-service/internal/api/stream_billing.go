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

	// chat-only running tally.
	inputCostUSD float64 // fixed: estimated input tokens × input price
	inputTokens  int     // P0-2: estimated input token count (the record's input_tokens when no final usage chunk arrives)
	abortUSD     float64 // hard-abort threshold = caller's available budget
	outChars     int     // accumulated output delta chars (token + reasoning)
	outNonASCII  int
	finalUsage   *provider.StreamChunk // last usage chunk seen, if any
	aborted      bool                  // observe tripped the hard-abort

	// P0-2 (B1/B2 — full request/response logging). requestPayload is the assembled
	// provider request (post-injection, bounded); completion accumulates the visible
	// streamed answer (token deltas only, capped) for the audit response payload;
	// requestStatus is the terminal outcome set by finalizeOutcome at stream end.
	requestPayload map[string]any
	completion     strings.Builder
	requestStatus  string
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
	pricing billing.Pricing, inputMap map[string]any,
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
		guardrail:     s.guardrail,
		reservationID: res.ReservationID,
		jobID:         jobID,
		ownerUserID:   userID,
		modelSource:   modelSource,
		modelRef:      modelRef,
		op:            op,
		pricing:       pricing,
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
	default:
		g.requestStatus = "success"
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

	var actual *float64
	switch {
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
	return float64(u.InputTokens)/1e6*inPerMTok + float64(out)/1e6*outPerMTok
}

// minFloat returns the smaller of two float64s.
func minFloat(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}
