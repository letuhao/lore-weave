package api

// DB-integration tests for the Phase 6a-δ streaming spend-guardrail pre-flight
// in doLlmStream: model lookup (404), unpriced (402), over-budget (402), and
// the happy path (reserve before the SSE prelude, reconcile at stream end).
// Require TEST_PROVIDER_REGISTRY_DB_URL; usage-billing is stubbed.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedStreamModel seeds a priced user_model whose provider_credentials row
// carries a REAL encrypted secret — doLlmStream decrypts it synchronously
// during credential resolution (unlike the job path), so a bogus ciphertext
// would 500 before the guardrail pre-flight ever runs.
func seedStreamModel(t *testing.T, srv *Server, pool *pgxpool.Pool, pricingJSON string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	userID := uuid.New()

	cipher, _, err := srv.encryptSecret("test-stream-key")
	if err != nil {
		t.Fatalf("encryptSecret: %v", err)
	}
	var credID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO provider_credentials (owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, status)
VALUES ($1,'openai','stream-guardrail-test','http://127.0.0.1:1',$2,'active')
RETURNING provider_credential_id`, userID, cipher).Scan(&credID); err != nil {
		t.Fatalf("seed provider_credentials: %v", err)
	}
	var modelID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO user_models (owner_user_id, provider_credential_id, provider_kind, provider_model_name, is_active, pricing)
VALUES ($1,$2,'openai','gpt-stream-test',true,$3)
RETURNING user_model_id`, userID, credID, pricingJSON).Scan(&modelID); err != nil {
		t.Fatalf("seed user_models: %v", err)
	}
	t.Cleanup(func() {
		bg := context.Background()
		_, _ = pool.Exec(bg, `DELETE FROM user_models WHERE user_model_id=$1`, modelID)
		_, _ = pool.Exec(bg, `DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credID)
	})
	return userID, modelID
}

// callStream posts a chat streamRequest through doLlmStream.
func callStream(t *testing.T, srv *Server, userID uuid.UUID, modelRef string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{
		"operation":    "chat",
		"model_source": "user_model",
		"model_ref":    modelRef,
		"messages":     []any{map[string]any{"role": "user", "content": "hello"}},
		"max_tokens":   64,
	})
	req := httptest.NewRequest(http.MethodPost, "/v1/llm/stream", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	srv.doLlmStream(rr, req, userID)
	return rr
}

func TestDoLlmStream_UnknownModel_404(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": uuid.New()}})
	srv, _ := guardrailServer(t, stub)

	rr := callStream(t, srv, uuid.New(), uuid.NewString())
	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d (%s)", rr.Code, rr.Body.String())
	}
	if stub.reserveCalls != 0 {
		t.Fatal("reserve must not be called for an unknown model")
	}
}

func TestDoLlmStream_UnpricedModel_402(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": uuid.New()}})
	srv, pool := guardrailServer(t, stub)
	userID, modelID := seedStreamModel(t, srv, pool, `{}`) // empty pricing → unpriced

	rr := callStream(t, srv, userID, modelID.String())
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d (%s)", rr.Code, rr.Body.String())
	}
	if c := errorCode(t, rr); c != "LLM_QUOTA_EXCEEDED" {
		t.Fatalf("expected LLM_QUOTA_EXCEEDED, got %q", c)
	}
	if stub.reserveCalls != 0 {
		t.Fatal("reserve must not be called for an unpriced model")
	}
}

func TestDoLlmStream_OverBudget_402_BeforePrelude(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusPaymentRequired, map[string]any{
		"code": "INSUFFICIENT_BUDGET", "daily_available": 0.0,
		"monthly_available": 0.0, "requested": 5.0,
	}})
	srv, pool := guardrailServer(t, stub)
	userID, modelID := seedStreamModel(t, srv, pool, pricedTextModel)

	rr := callStream(t, srv, userID, modelID.String())
	// 402 (not 200) proves the rejection landed BEFORE the SSE prelude —
	// once WriteHeader(200) ships the recorder code can no longer be 402.
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402 before the SSE prelude, got %d (%s)", rr.Code, rr.Body.String())
	}
	if stub.reserveCalls != 1 {
		t.Fatalf("expected exactly 1 reserve call, got %d", stub.reserveCalls)
	}
	if stub.reconcileCalls != 0 {
		t.Fatal("a rejected stream must not reconcile")
	}
}

func TestDoLlmStream_HappyPath_ReservesAndSettles(t *testing.T) {
	resID := uuid.New()
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{
		"reservation_id": resID, "daily_available": 10.0, "monthly_available": 50.0,
	}})
	srv, pool := guardrailServer(t, stub)
	userID, modelID := seedStreamModel(t, srv, pool, pricedTextModel)

	rr := callStream(t, srv, userID, modelID.String())
	// The pre-flight passed → the SSE prelude shipped → 200. The upstream
	// (a dead 127.0.0.1:1 endpoint) then fails and an error frame is
	// emitted, but the guardrail wrapped the whole thing.
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 (SSE opened), got %d (%s)", rr.Code, rr.Body.String())
	}
	if stub.reserveCalls != 1 {
		t.Fatalf("expected 1 reserve call, got %d", stub.reserveCalls)
	}
	// settle is deferred in doLlmStream → it has run by the time the call
	// returns. A reserved stream always reconciles (never releases).
	if stub.reconcileCalls != 1 {
		t.Fatalf("expected 1 reconcile call at stream end, got %d", stub.reconcileCalls)
	}
}
