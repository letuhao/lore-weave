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
	"log/slog"
	"net/http"

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
	op            string // "chat" | "tts"
	pricing       billing.Pricing

	// chat-only running tally.
	inputCostUSD float64 // fixed: estimated input tokens × input price
	abortUSD     float64 // hard-abort threshold = caller's available budget
	outChars     int     // accumulated output delta chars (token + reasoning)
	outNonASCII  int
	finalUsage   *provider.StreamChunk // last usage chunk seen, if any
	aborted      bool                  // observe tripped the hard-abort
}

// preflightStream runs the streaming spend-guardrail pre-flight: estimate the
// worst-case cost, reserve it, and build the streamGuard. It MUST be called
// before the SSE prelude — on a rejection it writes the HTTP error itself and
// returns ok=false. When the guardrail is not wired (s.guardrail nil — a
// Server built as a bare literal in unit tests) it returns (nil, true): the
// stream proceeds unguarded and the nil-safe observe/settle no-op.
func (s *Server) preflightStream(
	w http.ResponseWriter, r *http.Request,
	userID uuid.UUID, op, modelSource string, pricing billing.Pricing, inputMap map[string]any,
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

	jobID, err := uuid.NewV7() // synthetic — a stream has no llm_jobs row
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to allocate stream id")
		return nil, false
	}
	res, err := s.guardrail.Reserve(r.Context(), userID, jobID, estimate, modelSource)
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
		op:            op,
		pricing:       pricing,
		abortUSD:      minFloat(res.DailyAvailable, res.MonthlyAvailable),
	}
	if op == "chat" {
		// EstimateUSD("chat") succeeded → both text price dimensions are
		// present (textCost requires them), so the deref below is safe.
		g.inputCostUSD = float64(s.estimator.InputTokens(inputMap, 1)) / 1e6 * (*pricing.InputPerMTok)
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
