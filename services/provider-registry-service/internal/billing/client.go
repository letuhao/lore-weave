package billing

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/observability"
)

// GuardrailClient is the provider-registry → usage-billing HTTP client for the
// spend-guardrail endpoints (reserve / reconcile / release). It mirrors the
// existing recordInvocation pattern: X-Internal-Token auth, JSON bodies, a
// short timeout (a billing call must never stall job submission for long).
type GuardrailClient struct {
	baseURL       string
	internalToken string
	http          *http.Client
}

// NewGuardrailClient builds a client against usage-billing's base URL. A nil
// http.Client gets a default with a 5s timeout and a Phase 6c traced
// transport (outbound calls carry a W3C traceparent + emit a CLIENT span).
func NewGuardrailClient(baseURL, internalToken string, hc *http.Client) *GuardrailClient {
	if hc == nil {
		hc = &http.Client{
			Timeout:   5 * time.Second,
			Transport: observability.HTTPTransport(nil),
		}
	}
	return &GuardrailClient{
		baseURL:       strings.TrimRight(baseURL, "/"),
		internalToken: internalToken,
		http:          hc,
	}
}

// ReserveResult is the outcome of a reserve call. Exactly one of the two
// states is meaningful: a non-nil err, or (Insufficient ? a 402 budget
// rejection : a granted ReservationID).
type ReserveResult struct {
	ReservationID     uuid.UUID
	Insufficient      bool    // true → usage-billing returned 402
	Code              string  // the 402 `code` — INSUFFICIENT_BUDGET | PLATFORM_BALANCE_EXHAUSTED | MCP_KEY_CAP_EXCEEDED
	DailyAvailable    float64 // populated when Insufficient (Subsystem A)
	MonthlyAvailable  float64 // populated when Insufficient (Subsystem A)
	PlatformAvailable float64 // populated when Code == PLATFORM_BALANCE_EXHAUSTED (Subsystem B)
	KeyAvailable      float64 // populated when Code == MCP_KEY_CAP_EXCEEDED (per-key sub-cap, H-K)
	Requested         float64 // populated when Insufficient
}

// Reserve places a pre-flight hold for estimatedUSD against the owner's
// budget. A 200 yields ReservationID; a 402 yields Insufficient=true with the
// availability figures; any other outcome is an error (the caller fails
// closed — no job should run on an unconfirmed reservation).
//
// modelSource ("user_model" | "platform_model") selects the gates: a
// platform_model reservation also checks + holds Subsystem B (the platform
// resale ledger) in the same transaction (Phase 6a-β).
func (c *GuardrailClient) Reserve(ctx context.Context, ownerUserID, jobID uuid.UUID, estimatedUSD float64, modelSource string, mcpKeyID *uuid.UUID, spendCapUSD *float64) (ReserveResult, error) {
	body := map[string]any{
		"owner_user_id": ownerUserID,
		"job_id":        jobID,
		"estimated_usd": estimatedUSD,
		"model_source":  modelSource,
	}
	// Public MCP P4/Wave-C (H-K) — pass the per-key cap so usage-billing can hold
	// against it (omitted for first-party jobs, which carry neither).
	if mcpKeyID != nil {
		body["mcp_key_id"] = *mcpKeyID
	}
	if spendCapUSD != nil {
		body["spend_cap_usd"] = *spendCapUSD
	}
	status, raw, err := c.post(ctx, "/internal/billing/guardrail/reserve", body)
	if err != nil {
		return ReserveResult{}, err
	}
	switch status {
	case http.StatusOK:
		var out struct {
			ReservationID    uuid.UUID `json:"reservation_id"`
			DailyAvailable   float64   `json:"daily_available"`
			MonthlyAvailable float64   `json:"monthly_available"`
		}
		if err := json.Unmarshal(raw, &out); err != nil {
			return ReserveResult{}, fmt.Errorf("reserve: decode 200 body: %w", err)
		}
		if out.ReservationID == uuid.Nil {
			return ReserveResult{}, fmt.Errorf("reserve: 200 with nil reservation_id")
		}
		// DailyAvailable/MonthlyAvailable carry the caller's remaining
		// budget — the streaming guardrail's mid-stream abort threshold
		// (Phase 6a-δ). The job path ignores them.
		return ReserveResult{
			ReservationID:    out.ReservationID,
			DailyAvailable:   out.DailyAvailable,
			MonthlyAvailable: out.MonthlyAvailable,
		}, nil
	case http.StatusPaymentRequired:
		// The 402 body differs by gate: Subsystem A (INSUFFICIENT_BUDGET)
		// carries daily/monthly_available; Subsystem B
		// (PLATFORM_BALANCE_EXHAUSTED) carries platform_available.
		var out struct {
			Code              string  `json:"code"`
			DailyAvailable    float64 `json:"daily_available"`
			MonthlyAvailable  float64 `json:"monthly_available"`
			PlatformAvailable float64 `json:"platform_available"`
			KeyAvailable      float64 `json:"key_available"`
			Requested         float64 `json:"requested"`
		}
		_ = json.Unmarshal(raw, &out)
		return ReserveResult{
			Insufficient:      true,
			Code:              out.Code,
			DailyAvailable:    out.DailyAvailable,
			MonthlyAvailable:  out.MonthlyAvailable,
			PlatformAvailable: out.PlatformAvailable,
			KeyAvailable:      out.KeyAvailable,
			Requested:         out.Requested,
		}, nil
	default:
		return ReserveResult{}, fmt.Errorf("reserve: unexpected status %d: %s", status, truncate(raw))
	}
}

// Reconcile records the spend for a completed job. A non-nil actualUSD is the
// measured cost; nil omits the field so usage-billing charges the
// reservation's own stored estimate (media / usage-unknown jobs). Best-effort:
// the caller logs the error; the usage-billing sweeper is the backstop.
func (c *GuardrailClient) Reconcile(ctx context.Context, reservationID uuid.UUID, actualUSD *float64) error {
	payload := map[string]any{"reservation_id": reservationID}
	if actualUSD != nil {
		payload["actual_usd"] = *actualUSD
	}
	status, raw, err := c.post(ctx, "/internal/billing/guardrail/reconcile", payload)
	if err != nil {
		return err
	}
	if status != http.StatusOK {
		return fmt.Errorf("reconcile: unexpected status %d: %s", status, truncate(raw))
	}
	return nil
}

// Release frees a held reservation with no spend (failed/cancelled job).
// Best-effort, same as Reconcile.
func (c *GuardrailClient) Release(ctx context.Context, reservationID uuid.UUID) error {
	status, raw, err := c.post(ctx, "/internal/billing/guardrail/release", map[string]any{
		"reservation_id": reservationID,
	})
	if err != nil {
		return err
	}
	if status != http.StatusOK {
		return fmt.Errorf("release: unexpected status %d: %s", status, truncate(raw))
	}
	return nil
}

// UsageRecord is one model-level usage entry for the /record audit ledger.
type UsageRecord struct {
	RequestID    uuid.UUID
	OwnerUserID  uuid.UUID
	ModelSource  string
	ModelRef     uuid.UUID
	Operation    string // → /record `purpose`
	InputTokens  int
	OutputTokens int
	// TotalCostUSD is the authoritative per-model cost (input×in_rate +
	// output×out_rate from the model's Pricing), computed by the caller (the same
	// `actual` it reconciles the reservation with). nil → usage-billing falls back
	// to its flat per-token placeholder (back-compat / pricing-unresolved). Without
	// this the audit ledger mis-bills: a flat rate under-counts cloud models (gpt-4o
	// output is 4× input) AND wrongly charges local ($0) models.
	TotalCostUSD *float64
}

// RecordUsage posts a model-level usage entry to usage-billing's
// /internal/model-billing/record (Phase 6a-β — wires the gateway as the
// model-level biller). request_id = the job_id, so a retry is idempotent on
// the usage-billing side. Best-effort: the caller logs the error.
//
// provider_kind is left empty — the worker does not resolve it (the
// D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS gap the callers also accept);
// usage-billing's stale provider_kind CHECK is dropped in the 6a-β migration
// so an empty value is now accepted.
func (c *GuardrailClient) RecordUsage(ctx context.Context, rec UsageRecord) error {
	payload := map[string]any{
		"request_id":     rec.RequestID,
		"owner_user_id":  rec.OwnerUserID,
		"provider_kind":  "",
		"model_source":   rec.ModelSource,
		"model_ref":      rec.ModelRef,
		"input_tokens":   rec.InputTokens,
		"output_tokens":  rec.OutputTokens,
		"request_status": "success",
		"purpose":        rec.Operation,
	}
	// Send the authoritative per-model cost when the caller resolved it; absent →
	// usage-billing uses its flat fallback (back-compat).
	if rec.TotalCostUSD != nil {
		payload["total_cost_usd"] = *rec.TotalCostUSD
	}
	status, raw, err := c.post(ctx, "/internal/model-billing/record", payload)
	if err != nil {
		return err
	}
	if status != http.StatusOK && status != http.StatusCreated {
		return fmt.Errorf("record usage: unexpected status %d: %s", status, truncate(raw))
	}
	return nil
}

// post issues a JSON POST to the guardrail endpoint and returns the status
// code + raw body.
func (c *GuardrailClient) post(ctx context.Context, path string, payload map[string]any) (int, []byte, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return 0, nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if c.internalToken != "" {
		req.Header.Set("X-Internal-Token", c.internalToken)
	}
	res, err := c.http.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer res.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(res.Body, 1<<20))
	if err != nil {
		return 0, nil, err
	}
	return res.StatusCode, raw, nil
}

// truncate trims a response body for inclusion in an error message.
func truncate(b []byte) string {
	const max = 256
	if len(b) > max {
		return string(b[:max]) + "…"
	}
	return string(b)
}
