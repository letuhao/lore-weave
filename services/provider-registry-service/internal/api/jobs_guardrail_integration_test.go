package api

// DB-integration tests for the Phase 6a doSubmitJob spend-guardrail pre-flight:
// model lookup (404), unpriced (402), over-budget (402), max_tokens cap, and
// the happy path. Require TEST_PROVIDER_REGISTRY_DB_URL (see integrationServer)
// and stub usage-billing with an httptest server.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/provider-registry-service/internal/billing"
)

// reserveReply scripts one usage-billing reserve response.
type reserveReply struct {
	status int
	body   map[string]any
}

// billingStub is a fake usage-billing. reserve responses are consumed in
// order (the last repeats); reconcile/release always 200.
type billingStub struct {
	server         *httptest.Server
	reserve        []reserveReply
	reserveCalls   int
	reconcileCalls int
	releaseCalls   int
}

func newBillingStub(t *testing.T, reserve ...reserveReply) *billingStub {
	t.Helper()
	s := &billingStub{reserve: reserve}
	s.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/internal/billing/guardrail/reserve" {
			idx := s.reserveCalls
			if idx >= len(s.reserve) {
				idx = len(s.reserve) - 1
			}
			s.reserveCalls++
			reply := s.reserve[idx]
			w.WriteHeader(reply.status)
			_ = json.NewEncoder(w).Encode(reply.body)
			return
		}
		// reconcile / release
		switch r.URL.Path {
		case "/internal/billing/guardrail/reconcile":
			s.reconcileCalls++
		case "/internal/billing/guardrail/release":
			s.releaseCalls++
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	t.Cleanup(s.server.Close)
	return s
}

// guardrailServer builds an integration Server with its guardrail client
// pointed at the billing stub.
func guardrailServer(t *testing.T, stub *billingStub) (*Server, *pgxpool.Pool) {
	t.Helper()
	srv, pool := integrationServer(t)
	srv.guardrail = billing.NewGuardrailClient(stub.server.URL, "integration-internal-token", nil)
	return srv, pool
}

// seedPricedModel inserts a provider_credentials + user_models pair with the
// given pricing JSONB, and returns the owner + user_model_id.
func seedPricedModel(t *testing.T, pool *pgxpool.Pool, pricingJSON string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	userID := uuid.New()

	var credID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO provider_credentials (owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, status)
VALUES ($1,'openai','guardrail-test','http://127.0.0.1:1','x','active')
RETURNING provider_credential_id`, userID).Scan(&credID); err != nil {
		t.Fatalf("seed provider_credentials: %v", err)
	}
	var modelID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO user_models (owner_user_id, provider_credential_id, provider_kind, provider_model_name, is_active, pricing)
VALUES ($1,$2,'openai','gpt-guardrail-test',true,$3)
RETURNING user_model_id`, userID, credID, pricingJSON).Scan(&modelID); err != nil {
		t.Fatalf("seed user_models: %v", err)
	}
	t.Cleanup(func() {
		bg := context.Background()
		_, _ = pool.Exec(bg, `DELETE FROM llm_jobs WHERE owner_user_id=$1`, userID)
		_, _ = pool.Exec(bg, `DELETE FROM user_models WHERE user_model_id=$1`, modelID)
		_, _ = pool.Exec(bg, `DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credID)
	})
	return userID, modelID
}

// submitJob posts a job through doSubmitJob and returns the recorder.
func submitJob(t *testing.T, srv *Server, userID uuid.UUID, payload map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(payload)
	req := httptest.NewRequest(http.MethodPost, "/v1/llm/jobs", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	srv.doSubmitJob(rr, req, userID)
	return rr
}

func errorCode(t *testing.T, rr *httptest.ResponseRecorder) string {
	t.Helper()
	var e struct {
		Code string `json:"code"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &e)
	return e.Code
}

func jobCount(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM llm_jobs WHERE owner_user_id=$1`, owner).Scan(&n); err != nil {
		t.Fatalf("jobCount: %v", err)
	}
	return n
}

const pricedTextModel = `{"input_per_mtok":1.0,"output_per_mtok":10.0}`

// ── 404: model_ref resolves to nothing ─────────────────────────────────────

func TestDoSubmitJob_UnknownModel_404(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": uuid.New()}})
	srv, pool := guardrailServer(t, stub)
	owner := uuid.New()

	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "chat", "model_source": "user_model",
		"model_ref": uuid.NewString(), // no such model
		"input":     map[string]any{"messages": []any{map[string]any{"role": "user", "content": "hi"}}},
	})
	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d (%s)", rr.Code, rr.Body.String())
	}
	if c := errorCode(t, rr); c != "LLM_MODEL_NOT_FOUND" {
		t.Fatalf("expected LLM_MODEL_NOT_FOUND, got %q", c)
	}
	if stub.reserveCalls != 0 {
		t.Fatal("reserve must not be called for an unknown model")
	}
	if jobCount(t, pool, owner) != 0 {
		t.Fatal("no job row should be created for an unknown model")
	}
}

// ── 402: model exists but is unpriced ──────────────────────────────────────

func TestDoSubmitJob_UnpricedModel_402(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": uuid.New()}})
	srv, pool := guardrailServer(t, stub)
	owner, modelID := seedPricedModel(t, pool, `{}`) // empty pricing → unpriced

	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "embedding", "model_source": "user_model",
		"model_ref": modelID.String(),
		"input":     map[string]any{"text": "embed me"},
	})
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d (%s)", rr.Code, rr.Body.String())
	}
	if c := errorCode(t, rr); c != "LLM_QUOTA_EXCEEDED" {
		t.Fatalf("expected LLM_QUOTA_EXCEEDED, got %q", c)
	}
	if stub.reserveCalls != 0 {
		t.Fatal("reserve must not be called for an unpriced model")
	}
	if jobCount(t, pool, owner) != 0 {
		t.Fatal("no job row should be created for an unpriced model")
	}
}

// ── 402: over budget, non-chat op (no cap) ─────────────────────────────────

func TestDoSubmitJob_OverBudget_NonChat_402(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusPaymentRequired, map[string]any{
		"code": "INSUFFICIENT_BUDGET", "daily_available": 0.0,
		"monthly_available": 0.0, "requested": 5.0,
	}})
	srv, pool := guardrailServer(t, stub)
	owner, modelID := seedPricedModel(t, pool, pricedTextModel)

	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "embedding", "model_source": "user_model",
		"model_ref": modelID.String(),
		"input":     map[string]any{"text": "embed me"},
	})
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d (%s)", rr.Code, rr.Body.String())
	}
	if stub.reserveCalls != 1 {
		t.Fatalf("expected exactly 1 reserve call (no cap retry for embedding), got %d", stub.reserveCalls)
	}
	if jobCount(t, pool, owner) != 0 {
		t.Fatal("an over-budget job must not create a row")
	}
}

// ── happy path: reservation carried onto the job row ───────────────────────

func TestDoSubmitJob_HappyPath_CarriesReservation(t *testing.T) {
	resID := uuid.New()
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": resID}})
	srv, pool := guardrailServer(t, stub)
	owner, modelID := seedPricedModel(t, pool, pricedTextModel)

	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "chat", "model_source": "user_model",
		"model_ref": modelID.String(),
		"input": map[string]any{
			"messages":   []any{map[string]any{"role": "user", "content": "hello"}},
			"max_tokens": float64(100),
		},
	})
	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d (%s)", rr.Code, rr.Body.String())
	}
	var out struct {
		JobID string `json:"job_id"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode 202 body: %v", err)
	}
	jobID, err := uuid.Parse(out.JobID)
	if err != nil {
		t.Fatalf("bad job_id %q: %v", out.JobID, err)
	}
	var stored *uuid.UUID
	if err := pool.QueryRow(context.Background(),
		`SELECT reservation_id FROM llm_jobs WHERE job_id=$1`, jobID).Scan(&stored); err != nil {
		t.Fatalf("read reservation_id: %v", err)
	}
	if stored == nil || *stored != resID {
		t.Fatalf("job row reservation_id: got %v want %v", stored, resID)
	}
}

// ── max_tokens cap: 402-then-200, cap surfaced on job_meta ──────────────────

func TestDoSubmitJob_MaxTokensCap_RetriesAndSurfacesCap(t *testing.T) {
	resID := uuid.New()
	stub := newBillingStub(t,
		// First reserve (full max_tokens) — over budget, with a small but
		// positive remaining budget so a cap is possible.
		reserveReply{http.StatusPaymentRequired, map[string]any{
			"code": "INSUFFICIENT_BUDGET", "daily_available": 0.001,
			"monthly_available": 9.0, "requested": 5.0,
		}},
		// Second reserve (capped max_tokens) — granted.
		reserveReply{http.StatusOK, map[string]any{"reservation_id": resID}},
	)
	srv, pool := guardrailServer(t, stub)
	owner, modelID := seedPricedModel(t, pool, pricedTextModel)

	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "chat", "model_source": "user_model",
		"model_ref": modelID.String(),
		"input": map[string]any{
			"messages":   []any{map[string]any{"role": "user", "content": "hello"}},
			"max_tokens": float64(100000),
		},
	})
	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202 after the cap retry, got %d (%s)", rr.Code, rr.Body.String())
	}
	if stub.reserveCalls != 2 {
		t.Fatalf("expected 2 reserve calls (initial + capped retry), got %d", stub.reserveCalls)
	}
	var out struct {
		JobID string `json:"job_id"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	jobID := uuid.MustParse(out.JobID)

	// The cap must be surfaced on job_meta AND applied to the stored input.
	var jobMeta, input []byte
	if err := pool.QueryRow(context.Background(),
		`SELECT job_meta, input FROM llm_jobs WHERE job_id=$1`, jobID).Scan(&jobMeta, &input); err != nil {
		t.Fatalf("read job row: %v", err)
	}
	var meta map[string]any
	if err := json.Unmarshal(jobMeta, &meta); err != nil {
		t.Fatalf("decode job_meta: %v", err)
	}
	capObj, ok := meta["max_tokens_capped"].(map[string]any)
	if !ok {
		t.Fatalf("job_meta.max_tokens_capped missing — cap was silent: %s", jobMeta)
	}
	if capObj["reason"] != "budget" {
		t.Fatalf("cap reason: got %v want budget", capObj["reason"])
	}
	applied := int(capObj["applied"].(float64))
	if applied < 1 || applied >= 100000 {
		t.Fatalf("capped max_tokens out of range: %d", applied)
	}
	var inMap map[string]any
	if err := json.Unmarshal(input, &inMap); err != nil {
		t.Fatalf("decode input: %v", err)
	}
	if got := int(inMap["max_tokens"].(float64)); got != applied {
		t.Fatalf("stored input max_tokens %d != capped %d", got, applied)
	}
}

// setUserModelContextLength backfills user_models.context_length for an
// already-seeded row. Used by the STAGE-4 preflight overflow tests.
func setUserModelContextLength(t *testing.T, pool *pgxpool.Pool, modelID uuid.UUID, ctxLen int) {
	t.Helper()
	if _, err := pool.Exec(context.Background(),
		`UPDATE user_models SET context_length=$2 WHERE user_model_id=$1`,
		modelID, ctxLen); err != nil {
		t.Fatalf("set context_length: %v", err)
	}
}

// ── D-EXTRACTION-CONTEXT-FIX-STAGE-4 context-fit preflight ─────────────────

// TestDoSubmitJob_ContextOverflow_400 — the input + max_tokens + 15% safety
// margin exceed the registered context_length → 400 LLM_CONTEXT_OVERFLOW
// before any reservation is placed. Regression-lock for the KV-cache OOM seen
// on huihui-qwen3.6-abliterated 32K (R+E+F gather → "failed to find a memory
// slot for batch").
func TestDoSubmitJob_ContextOverflow_400(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": uuid.New()}})
	srv, pool := guardrailServer(t, stub)
	owner, modelID := seedPricedModel(t, pool, pricedTextModel)
	setUserModelContextLength(t, pool, modelID, 8192)

	// max_tokens alone (10000) > context_length (8192) → overflow no matter
	// how small the prompt is.
	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "chat", "model_source": "user_model",
		"model_ref": modelID.String(),
		"input": map[string]any{
			"messages":   []any{map[string]any{"role": "user", "content": "hi"}},
			"max_tokens": float64(10000),
		},
	})
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d (%s)", rr.Code, rr.Body.String())
	}
	if c := errorCode(t, rr); c != "LLM_CONTEXT_OVERFLOW" {
		t.Fatalf("expected LLM_CONTEXT_OVERFLOW, got %q", c)
	}
	if stub.reserveCalls != 0 {
		t.Fatal("reserve must not be called when context overflows")
	}
	if jobCount(t, pool, owner) != 0 {
		t.Fatal("no job row should be created for an overflow")
	}
}

// TestDoSubmitJob_ContextFits_Passes — input + max_tokens + safety < context
// → preflight passes through to reservation + 202. Confirms the fit branch
// doesn't false-positive on reasonable requests.
func TestDoSubmitJob_ContextFits_Passes(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": uuid.New()}})
	srv, pool := guardrailServer(t, stub)
	owner, modelID := seedPricedModel(t, pool, pricedTextModel)
	setUserModelContextLength(t, pool, modelID, 32768)

	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "chat", "model_source": "user_model",
		"model_ref": modelID.String(),
		"input": map[string]any{
			"messages":   []any{map[string]any{"role": "user", "content": "hello"}},
			"max_tokens": float64(4096),
		},
	})
	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d (%s)", rr.Code, rr.Body.String())
	}
}

// TestDoSubmitJob_ContextLengthNull_SkipsCheck — NULL context_length (legacy
// rows, providers without a known limit) MUST NOT block the request. The
// preflight returns (0, true) and skips the fit comparison.
func TestDoSubmitJob_ContextLengthNull_SkipsCheck(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{"reservation_id": uuid.New()}})
	srv, pool := guardrailServer(t, stub)
	owner, modelID := seedPricedModel(t, pool, pricedTextModel)
	// context_length defaults to NULL — no setUserModelContextLength call.

	rr := submitJob(t, srv, owner, map[string]any{
		"operation": "chat", "model_source": "user_model",
		"model_ref": modelID.String(),
		"input": map[string]any{
			"messages":   []any{map[string]any{"role": "user", "content": "hi"}},
			"max_tokens": float64(1000000), // would overflow ANY model — but NULL skips
		},
	})
	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202 (NULL ctxlen skips fit check), got %d (%s)", rr.Code, rr.Body.String())
	}
}

// seedPlatformModel inserts a priced platform_models row, returning its id.
func seedPlatformModel(t *testing.T, pool *pgxpool.Pool, pricingJSON string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := pool.QueryRow(context.Background(), `
INSERT INTO platform_models (provider_kind, provider_model_name, display_name, status, pricing)
VALUES ('openai','gpt-platform-test','GPT Platform Test','active',$1)
RETURNING platform_model_id`, pricingJSON).Scan(&id); err != nil {
		t.Fatalf("seed platform_models: %v", err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM platform_models WHERE platform_model_id=$1`, id)
	})
	return id
}

// TestDoSubmitJob_PlatformModel_HappyPath exercises doSubmitJob's pre-flight
// for a platform_model job — pricing resolved from platform_models, reserve
// placed with model_source=platform_model (Subsystem B engaged in usage-billing).
func TestDoSubmitJob_PlatformModel_HappyPath(t *testing.T) {
	stub := newBillingStub(t, reserveReply{http.StatusOK, map[string]any{
		"reservation_id": uuid.New(), "daily_available": 10.0, "monthly_available": 50.0,
	}})
	srv, pool := guardrailServer(t, stub)
	modelID := seedPlatformModel(t, pool, pricedTextModel)
	owner := uuid.New()

	body, _ := json.Marshal(map[string]any{
		"operation": "chat", "model_source": "platform_model",
		"model_ref": modelID.String(),
		"input":     map[string]any{"messages": []any{map[string]any{"role": "user", "content": "hi"}}},
	})
	req := httptest.NewRequest(http.MethodPost, "/v1/llm/jobs", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	srv.doSubmitJob(rr, req, owner)

	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d (%s)", rr.Code, rr.Body.String())
	}
	if stub.reserveCalls != 1 {
		t.Fatalf("expected 1 reserve call, got %d", stub.reserveCalls)
	}
	_, _ = pool.Exec(context.Background(), `DELETE FROM llm_jobs WHERE owner_user_id=$1`, owner)
}
