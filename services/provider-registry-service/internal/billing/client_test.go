package billing

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// guardrailStub is a fake usage-billing server. It records the last request
// and replies with a scripted status + body.
type guardrailStub struct {
	server      *httptest.Server
	lastPath    string
	lastToken   string
	lastBody    map[string]any
	replyStatus int
	replyBody   any
}

func newGuardrailStub(t *testing.T) *guardrailStub {
	t.Helper()
	s := &guardrailStub{replyStatus: http.StatusOK, replyBody: map[string]any{}}
	s.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		s.lastPath = r.URL.Path
		s.lastToken = r.Header.Get("X-Internal-Token")
		raw, _ := io.ReadAll(r.Body)
		s.lastBody = map[string]any{}
		_ = json.Unmarshal(raw, &s.lastBody)
		w.WriteHeader(s.replyStatus)
		_ = json.NewEncoder(w).Encode(s.replyBody)
	}))
	t.Cleanup(s.server.Close)
	return s
}

func TestGuardrailClient_Reserve_OK(t *testing.T) {
	stub := newGuardrailStub(t)
	resID := uuid.New()
	stub.replyStatus = http.StatusOK
	stub.replyBody = map[string]any{
		"reservation_id": resID, "daily_available": 7.5, "monthly_available": 42.0,
	}

	c := NewGuardrailClient(stub.server.URL, "secret-token", nil)
	owner, job := uuid.New(), uuid.New()
	res, err := c.Reserve(context.Background(), owner, job, 2.5, "platform_model")
	if err != nil {
		t.Fatalf("Reserve: %v", err)
	}
	if res.Insufficient {
		t.Fatal("expected a granted reservation, got Insufficient")
	}
	if res.ReservationID != resID {
		t.Fatalf("reservation_id: got %v want %v", res.ReservationID, resID)
	}
	// A 200 must also surface the availability figures (the streaming
	// guardrail's abort threshold).
	if res.DailyAvailable != 7.5 || res.MonthlyAvailable != 42.0 {
		t.Fatalf("200 availability: got daily=%v monthly=%v want 7.5/42.0",
			res.DailyAvailable, res.MonthlyAvailable)
	}
	if stub.lastPath != "/internal/billing/guardrail/reserve" {
		t.Fatalf("unexpected path %q", stub.lastPath)
	}
	if stub.lastToken != "secret-token" {
		t.Fatalf("X-Internal-Token not forwarded: %q", stub.lastToken)
	}
	if stub.lastBody["model_source"] != "platform_model" {
		t.Fatalf("model_source not forwarded: %v", stub.lastBody["model_source"])
	}
	if stub.lastBody["estimated_usd"] != 2.5 {
		t.Fatalf("estimated_usd not sent: %v", stub.lastBody["estimated_usd"])
	}
}

func TestGuardrailClient_Reserve_402_Insufficient(t *testing.T) {
	stub := newGuardrailStub(t)
	stub.replyStatus = http.StatusPaymentRequired
	stub.replyBody = map[string]any{
		"code": "INSUFFICIENT_BUDGET", "daily_available": 1.25,
		"monthly_available": 9.0, "requested": 5.0,
	}
	c := NewGuardrailClient(stub.server.URL, "tok", nil)

	res, err := c.Reserve(context.Background(), uuid.New(), uuid.New(), 5.0, "user_model")
	if err != nil {
		t.Fatalf("Reserve should not error on a 402, got %v", err)
	}
	if !res.Insufficient {
		t.Fatal("expected Insufficient=true on a 402")
	}
	if res.Code != "INSUFFICIENT_BUDGET" {
		t.Fatalf("402 code not decoded: %q", res.Code)
	}
	if res.DailyAvailable != 1.25 || res.MonthlyAvailable != 9.0 || res.Requested != 5.0 {
		t.Fatalf("402 figures not decoded: %+v", res)
	}
	if res.ReservationID != uuid.Nil {
		t.Fatal("a 402 must not yield a reservation_id")
	}
}

func TestGuardrailClient_Reserve_402_PlatformExhausted(t *testing.T) {
	stub := newGuardrailStub(t)
	stub.replyStatus = http.StatusPaymentRequired
	stub.replyBody = map[string]any{
		"code": "PLATFORM_BALANCE_EXHAUSTED", "platform_available": 2.5, "requested": 8.0,
	}
	c := NewGuardrailClient(stub.server.URL, "tok", nil)

	res, err := c.Reserve(context.Background(), uuid.New(), uuid.New(), 8.0, "platform_model")
	if err != nil {
		t.Fatalf("Reserve should not error on a 402: %v", err)
	}
	if !res.Insufficient || res.Code != "PLATFORM_BALANCE_EXHAUSTED" {
		t.Fatalf("Subsystem-B 402 not decoded: %+v", res)
	}
	if res.PlatformAvailable != 2.5 {
		t.Fatalf("platform_available not decoded: got %v want 2.5", res.PlatformAvailable)
	}
}

func TestGuardrailClient_Reserve_500_IsError(t *testing.T) {
	stub := newGuardrailStub(t)
	stub.replyStatus = http.StatusInternalServerError
	stub.replyBody = map[string]any{"error": "boom"}
	c := NewGuardrailClient(stub.server.URL, "tok", nil)

	if _, err := c.Reserve(context.Background(), uuid.New(), uuid.New(), 1.0, "user_model"); err == nil {
		t.Fatal("expected an error on a 500 reserve")
	}
}

func TestGuardrailClient_Reserve_200_NilReservationID_IsError(t *testing.T) {
	stub := newGuardrailStub(t)
	stub.replyStatus = http.StatusOK
	stub.replyBody = map[string]any{} // no reservation_id
	c := NewGuardrailClient(stub.server.URL, "tok", nil)

	if _, err := c.Reserve(context.Background(), uuid.New(), uuid.New(), 1.0, "user_model"); err == nil {
		t.Fatal("expected an error when a 200 carries no reservation_id")
	}
}

func TestGuardrailClient_Reconcile_WithActual(t *testing.T) {
	stub := newGuardrailStub(t)
	c := NewGuardrailClient(stub.server.URL, "tok", nil)
	resID := uuid.New()

	actual := 3.5
	if err := c.Reconcile(context.Background(), resID, &actual); err != nil {
		t.Fatalf("Reconcile: %v", err)
	}
	if stub.lastPath != "/internal/billing/guardrail/reconcile" {
		t.Fatalf("unexpected path %q", stub.lastPath)
	}
	if stub.lastBody["actual_usd"] != 3.5 {
		t.Fatalf("actual_usd not sent: %v", stub.lastBody["actual_usd"])
	}

	stub.replyStatus = http.StatusInternalServerError
	if err := c.Reconcile(context.Background(), resID, &actual); err == nil {
		t.Fatal("expected an error when reconcile returns non-200")
	}
}

func TestGuardrailClient_Reconcile_NilActual_OmitsField(t *testing.T) {
	stub := newGuardrailStub(t)
	c := NewGuardrailClient(stub.server.URL, "tok", nil)

	// A nil actualUSD must leave actual_usd OUT of the body entirely so
	// usage-billing falls back to the reservation's stored estimate.
	if err := c.Reconcile(context.Background(), uuid.New(), nil); err != nil {
		t.Fatalf("Reconcile: %v", err)
	}
	if _, present := stub.lastBody["actual_usd"]; present {
		t.Fatalf("actual_usd must be omitted when nil, got %v", stub.lastBody["actual_usd"])
	}
}

func TestGuardrailClient_Release(t *testing.T) {
	stub := newGuardrailStub(t)
	c := NewGuardrailClient(stub.server.URL, "tok", nil)
	resID := uuid.New()

	if err := c.Release(context.Background(), resID); err != nil {
		t.Fatalf("Release: %v", err)
	}
	if stub.lastPath != "/internal/billing/guardrail/release" {
		t.Fatalf("unexpected path %q", stub.lastPath)
	}
	if stub.lastBody["reservation_id"] != resID.String() {
		t.Fatalf("reservation_id not sent: %v", stub.lastBody["reservation_id"])
	}

	stub.replyStatus = http.StatusBadGateway
	if err := c.Release(context.Background(), resID); err == nil {
		t.Fatal("expected an error when release returns non-200")
	}
}

func TestGuardrailClient_RecordUsage(t *testing.T) {
	stub := newGuardrailStub(t)
	c := NewGuardrailClient(stub.server.URL, "tok", nil)
	jobID, owner, modelRef := uuid.New(), uuid.New(), uuid.New()

	err := c.RecordUsage(context.Background(), UsageRecord{
		RequestID:    jobID,
		OwnerUserID:  owner,
		ModelSource:  "platform_model",
		ModelRef:     modelRef,
		Operation:    "chat",
		InputTokens:  100,
		OutputTokens: 50,
	})
	if err != nil {
		t.Fatalf("RecordUsage: %v", err)
	}
	if stub.lastPath != "/internal/model-billing/record" {
		t.Fatalf("unexpected path %q", stub.lastPath)
	}
	// request_id = the job_id (the /record idempotency key).
	if stub.lastBody["request_id"] != jobID.String() {
		t.Fatalf("request_id: got %v want %v", stub.lastBody["request_id"], jobID)
	}
	// Operation maps to /record's `purpose`.
	if stub.lastBody["purpose"] != "chat" {
		t.Fatalf("purpose: got %v want chat", stub.lastBody["purpose"])
	}
	if stub.lastBody["input_tokens"] != float64(100) || stub.lastBody["output_tokens"] != float64(50) {
		t.Fatalf("token counts not forwarded: %v / %v",
			stub.lastBody["input_tokens"], stub.lastBody["output_tokens"])
	}
	if stub.lastBody["model_source"] != "platform_model" {
		t.Fatalf("model_source: got %v", stub.lastBody["model_source"])
	}
	// TotalCostUSD nil → total_cost_usd ABSENT (usage-billing flat-fallbacks).
	if _, present := stub.lastBody["total_cost_usd"]; present {
		t.Fatalf("total_cost_usd must be absent when TotalCostUSD is nil: %v", stub.lastBody["total_cost_usd"])
	}
}

func TestGuardrailClient_RecordUsage_SendsCost(t *testing.T) {
	stub := newGuardrailStub(t)
	c := NewGuardrailClient(stub.server.URL, "tok", nil)
	cost := 0.3515
	err := c.RecordUsage(context.Background(), UsageRecord{
		RequestID: uuid.New(), OwnerUserID: uuid.New(), ModelSource: "user_model",
		ModelRef: uuid.New(), Operation: "chat", InputTokens: 58777, OutputTokens: 20457,
		TotalCostUSD: &cost,
	})
	if err != nil {
		t.Fatalf("RecordUsage: %v", err)
	}
	// The authoritative per-model cost is forwarded so usage-billing bills it
	// verbatim instead of its flat per-token placeholder.
	if stub.lastBody["total_cost_usd"] != 0.3515 {
		t.Fatalf("total_cost_usd: got %v want 0.3515", stub.lastBody["total_cost_usd"])
	}
}
