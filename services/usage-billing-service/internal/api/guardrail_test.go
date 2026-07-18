package api

// DB-integration tests for the Phase 6a spend-guardrail handlers
// (reserve / reconcile / release) and the leaked-reservation sweeper.
//
// These require a real Postgres: set USAGE_BILLING_TEST_DB_URL to a throwaway
// database (the suite TRUNCATEs spend_guardrails + token_reservations between
// tests). Skipped when the env var is unset, mirroring the glossary-service
// openTestDB convention.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/usage-billing-service/internal/config"
	"github.com/loreweave/usage-billing-service/internal/migrate"
)

const (
	guardrailTestSecret   = "test_jwt_secret_at_least_32_characters_long"
	guardrailTestDaily    = 10.0
	guardrailTestMonthly  = 100.0
	guardrailTestFreeTier = 50.0 // Phase 6a-β — Subsystem B free-tier allowance
)

// openGuardrailTestDB opens a pool for the guardrail integration tests; skips
// when USAGE_BILLING_TEST_DB_URL is unset. Runs migrations and truncates the
// two guardrail tables so each test starts from a clean slate.
func openGuardrailTestDB(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dbURL := os.Getenv("USAGE_BILLING_TEST_DB_URL")
	if dbURL == "" {
		t.Skip("USAGE_BILLING_TEST_DB_URL not set — skipping DB integration test")
	}
	pool, err := pgxpool.New(context.Background(), dbURL)
	if err != nil {
		t.Fatalf("openGuardrailTestDB: %v", err)
	}
	if err := migrate.Up(context.Background(), pool); err != nil {
		pool.Close()
		t.Fatalf("migrate.Up: %v", err)
	}
	if _, err := pool.Exec(context.Background(),
		`TRUNCATE spend_guardrails, token_reservations, platform_balances`); err != nil {
		pool.Close()
		t.Fatalf("truncate: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func newGuardrailServer(t *testing.T, pool *pgxpool.Pool) *Server {
	t.Helper()
	return NewServer(pool, &config.Config{
		JWTSecret:                  guardrailTestSecret,
		GuardrailDefaultDailyUSD:   guardrailTestDaily,
		GuardrailDefaultMonthlyUSD: guardrailTestMonthly,
		PlatformFreeTierUSD:        guardrailTestFreeTier,
		ReservationTTL:             45 * time.Minute,
	})
}

// platformBalance is a snapshot of one platform_balances row.
type platformBalance struct {
	freeTierAllowance, freeTierUsed float64
	creditsBalance, reserved        float64
}

func readPlatformBalance(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID) platformBalance {
	t.Helper()
	var b platformBalance
	err := pool.QueryRow(context.Background(), `
SELECT free_tier_allowance_usd, free_tier_used_usd, credits_balance_usd, reserved_usd
FROM platform_balances WHERE owner_user_id = $1`, owner).
		Scan(&b.freeTierAllowance, &b.freeTierUsed, &b.creditsBalance, &b.reserved)
	if err != nil {
		t.Fatalf("readPlatformBalance: %v", err)
	}
	return b
}

func platformBalanceExists(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID) bool {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM platform_balances WHERE owner_user_id = $1`, owner).Scan(&n); err != nil {
		t.Fatalf("platformBalanceExists: %v", err)
	}
	return n > 0
}

// callReservePlatform posts a reserve with model_source=platform_model.
func callReservePlatform(t *testing.T, srv *Server, owner, job uuid.UUID, est float64) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{
		"owner_user_id": owner, "job_id": job, "estimated_usd": est,
		"model_source": "platform_model",
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/billing/guardrail/reserve", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	srv.guardrailReserve(rr, req)
	return rr
}

// guardrail is a snapshot of one spend_guardrails row.
type guardrail struct {
	dailyLimit, monthlyLimit   float64
	dailySpent, monthlySpent   float64
	reserved                   float64
	dailyWindow, monthlyWindow time.Time
}

func readGuardrail(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID) guardrail {
	t.Helper()
	var g guardrail
	err := pool.QueryRow(context.Background(), `
SELECT daily_limit_usd, monthly_limit_usd, daily_spent_usd, monthly_spent_usd,
       reserved_usd, daily_window_date, monthly_window_month
FROM spend_guardrails WHERE owner_user_id = $1`, owner).
		Scan(&g.dailyLimit, &g.monthlyLimit, &g.dailySpent, &g.monthlySpent,
			&g.reserved, &g.dailyWindow, &g.monthlyWindow)
	if err != nil {
		t.Fatalf("readGuardrail: %v", err)
	}
	return g
}

func reservationStatus(t *testing.T, pool *pgxpool.Pool, resID uuid.UUID) string {
	t.Helper()
	var status string
	if err := pool.QueryRow(context.Background(),
		`SELECT status FROM token_reservations WHERE reservation_id = $1`, resID).
		Scan(&status); err != nil {
		t.Fatalf("reservationStatus: %v", err)
	}
	return status
}

// callReserve posts to guardrailReserve and returns the recorder.
func callReserve(t *testing.T, srv *Server, owner, job uuid.UUID, est float64) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{
		"owner_user_id": owner, "job_id": job, "estimated_usd": est,
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/billing/guardrail/reserve", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	srv.guardrailReserve(rr, req)
	return rr
}

func reservationIDFrom(t *testing.T, rr *httptest.ResponseRecorder) uuid.UUID {
	t.Helper()
	var out struct {
		ReservationID uuid.UUID `json:"reservation_id"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode reserve response %q: %v", rr.Body.String(), err)
	}
	return out.ReservationID
}

func callReconcile(t *testing.T, srv *Server, resID uuid.UUID, actual float64) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"reservation_id": resID, "actual_usd": actual})
	req := httptest.NewRequest(http.MethodPost, "/internal/billing/guardrail/reconcile", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	srv.guardrailReconcile(rr, req)
	return rr
}

// callReconcileNoActual posts a reconcile with NO actual_usd field — the
// usage-unknown path that charges the reservation's stored estimate.
func callReconcileNoActual(t *testing.T, srv *Server, resID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"reservation_id": resID})
	req := httptest.NewRequest(http.MethodPost, "/internal/billing/guardrail/reconcile", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	srv.guardrailReconcile(rr, req)
	return rr
}

func callRelease(t *testing.T, srv *Server, resID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"reservation_id": resID})
	req := httptest.NewRequest(http.MethodPost, "/internal/billing/guardrail/release", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	srv.guardrailRelease(rr, req)
	return rr
}

// ── reserve ────────────────────────────────────────────────────────────────

func TestGuardrailReserve_HappyPath_SeedsRowAndHolds(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner, job := uuid.New(), uuid.New()

	rr := callReserve(t, srv, owner, job, 2.5)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if reservationIDFrom(t, rr) == uuid.Nil {
		t.Fatal("expected a non-nil reservation_id")
	}
	// The 200 body must carry the step-5 availability figures (Phase 6a-δ
	// streaming abort threshold). Row just seeded → spent 0, reserved 0.
	var avail struct {
		DailyAvailable   float64 `json:"daily_available"`
		MonthlyAvailable float64 `json:"monthly_available"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &avail); err != nil {
		t.Fatalf("decode reserve 200 body: %v", err)
	}
	if avail.DailyAvailable != guardrailTestDaily || avail.MonthlyAvailable != guardrailTestMonthly {
		t.Fatalf("reserve 200 availability: got daily=%v monthly=%v want %v/%v",
			avail.DailyAvailable, avail.MonthlyAvailable, guardrailTestDaily, guardrailTestMonthly)
	}
	g := readGuardrail(t, pool, owner)
	if g.dailyLimit != guardrailTestDaily || g.monthlyLimit != guardrailTestMonthly {
		t.Fatalf("guardrail not seeded from config: %+v", g)
	}
	if g.reserved != 2.5 {
		t.Fatalf("expected reserved_usd 2.5, got %v", g.reserved)
	}
	if g.dailySpent != 0 || g.monthlySpent != 0 {
		t.Fatalf("expected no spend yet, got daily=%v monthly=%v", g.dailySpent, g.monthlySpent)
	}
}

func TestGuardrailReserve_Idempotent_SameJobBumpsReservedOnce(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner, job := uuid.New(), uuid.New()

	rr1 := callReserve(t, srv, owner, job, 3.0)
	if rr1.Code != http.StatusOK {
		t.Fatalf("first reserve: expected 200, got %d", rr1.Code)
	}
	first := reservationIDFrom(t, rr1)

	// Second reserve for the SAME job — sequential write whose state is read
	// by the dedup branch (feedback_test_sequential_writes).
	rr2 := callReserve(t, srv, owner, job, 3.0)
	if rr2.Code != http.StatusOK {
		t.Fatalf("second reserve: expected 200, got %d", rr2.Code)
	}
	if second := reservationIDFrom(t, rr2); second != first {
		t.Fatalf("idempotency broken: %v != %v", second, first)
	}
	if g := readGuardrail(t, pool, owner); g.reserved != 3.0 {
		t.Fatalf("reserved_usd double-counted: expected 3.0, got %v", g.reserved)
	}
}

func TestGuardrailReserve_OverBudget_402(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	// Daily limit is 10. First hold of 8 leaves 2 available.
	if rr := callReserve(t, srv, owner, uuid.New(), 8.0); rr.Code != http.StatusOK {
		t.Fatalf("setup reserve: expected 200, got %d", rr.Code)
	}
	rr := callReserve(t, srv, owner, uuid.New(), 5.0)
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d (%s)", rr.Code, rr.Body.String())
	}
	var out struct {
		Code           string  `json:"code"`
		DailyAvailable float64 `json:"daily_available"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if out.Code != "INSUFFICIENT_BUDGET" {
		t.Fatalf("expected INSUFFICIENT_BUDGET, got %q", out.Code)
	}
	if out.DailyAvailable != 2.0 {
		t.Fatalf("expected daily_available 2.0, got %v", out.DailyAvailable)
	}
	// The rejected hold must not have leaked into reserved_usd.
	if g := readGuardrail(t, pool, owner); g.reserved != 8.0 {
		t.Fatalf("rejected reserve leaked into reserved_usd: %v", g.reserved)
	}
}

func TestGuardrailReserve_OverMonthlyBudget_TighterWindowWins_402(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	// Seed the row with a small reserve, then exhaust the MONTHLY window
	// while leaving the DAILY window plenty of room — the 402 must be
	// driven by the tighter (monthly) window.
	if rr := callReserve(t, srv, owner, uuid.New(), 1.0); rr.Code != http.StatusOK {
		t.Fatalf("setup reserve: expected 200, got %d", rr.Code)
	}
	if _, err := pool.Exec(context.Background(),
		`UPDATE spend_guardrails SET monthly_spent_usd = monthly_limit_usd - 1 WHERE owner_user_id=$1`,
		owner); err != nil {
		t.Fatalf("exhaust monthly window: %v", err)
	}
	// daily_available ≈ 9 (limit 10 − reserved 1); monthly_available ≈ 0.
	rr := callReserve(t, srv, owner, uuid.New(), 5.0)
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402 on monthly exhaustion, got %d (%s)", rr.Code, rr.Body.String())
	}
	var out struct {
		DailyAvailable   float64 `json:"daily_available"`
		MonthlyAvailable float64 `json:"monthly_available"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if out.MonthlyAvailable >= out.DailyAvailable {
		t.Fatalf("monthly should be the tighter window: daily=%v monthly=%v",
			out.DailyAvailable, out.MonthlyAvailable)
	}
}

func TestGuardrailReserve_ZeroCost_NeverGated(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	// Exhaust the entire daily budget with a held reservation.
	if rr := callReserve(t, srv, owner, uuid.New(), 10.0); rr.Code != http.StatusOK {
		t.Fatalf("setup reserve: expected 200, got %d", rr.Code)
	}
	// A zero-cost (explicitly-free model) job must still be admitted.
	rr := callReserve(t, srv, owner, uuid.New(), 0)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected zero-cost reserve to pass, got %d (%s)", rr.Code, rr.Body.String())
	}
}

// ── per-key spend sub-cap (P4/Wave-C H-K) ──────────────────────────────────

// callReserveWithKey posts a reserve carrying a public mcp_key_id + its sub-cap.
func callReserveWithKey(t *testing.T, srv *Server, owner, job, mcpKey uuid.UUID, est, cap float64) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{
		"owner_user_id": owner, "job_id": job, "estimated_usd": est,
		"mcp_key_id": mcpKey, "spend_cap_usd": cap,
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/billing/guardrail/reserve", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	srv.guardrailReserve(rr, req)
	return rr
}

// A key's HELD reservations count toward its sub-cap — the core H-K race guard:
// two concurrent holds from one key cannot exceed the cap even before either
// reconciles. Estimates stay under the OWNER daily/monthly budget so only the
// per-key cap binds.
func TestGuardrailReserve_PerKeyCap_HeldHoldsCountTowardCap(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner, mcpKey := uuid.New(), uuid.New()
	const cap = 4.0

	// First hold: $2 of a $4 key cap (and well under the $10 owner daily).
	rr1 := callReserveWithKey(t, srv, owner, uuid.New(), mcpKey, 2.0, cap)
	if rr1.Code != http.StatusOK {
		t.Fatalf("first reserve: expected 200, got %d (%s)", rr1.Code, rr1.Body.String())
	}
	// The reservation row must carry the key (so the held-sum + later attribution work).
	var stamped int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM token_reservations WHERE mcp_key_id = $1 AND status = 'held'`,
		mcpKey).Scan(&stamped); err != nil {
		t.Fatalf("count stamped reservations: %v", err)
	}
	if stamped != 1 {
		t.Fatalf("expected the reservation stamped with mcp_key_id, got %d", stamped)
	}

	// Second hold: $3 would push held to $5 > $4 cap → 402 MCP_KEY_CAP_EXCEEDED,
	// even though the owner budget ($10 daily) still has room.
	rr2 := callReserveWithKey(t, srv, owner, uuid.New(), mcpKey, 3.0, cap)
	if rr2.Code != http.StatusPaymentRequired {
		t.Fatalf("second reserve: expected 402, got %d (%s)", rr2.Code, rr2.Body.String())
	}
	var out struct {
		Code         string  `json:"code"`
		KeyAvailable float64 `json:"key_available"`
	}
	if err := json.Unmarshal(rr2.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode 402: %v", err)
	}
	if out.Code != "MCP_KEY_CAP_EXCEEDED" {
		t.Fatalf("expected MCP_KEY_CAP_EXCEEDED, got %q", out.Code)
	}
	if out.KeyAvailable != 2.0 { // cap 4 − held 2
		t.Fatalf("key_available: got %v want 2.0", out.KeyAvailable)
	}

	// Releasing the first hold frees the key budget → the $3 reserve now fits.
	resID1 := reservationIDFrom(t, rr1)
	if rr := callRelease(t, srv, resID1); rr.Code != http.StatusOK {
		t.Fatalf("release: expected 200, got %d", rr.Code)
	}
	rr3 := callReserveWithKey(t, srv, owner, uuid.New(), mcpKey, 3.0, cap)
	if rr3.Code != http.StatusOK {
		t.Fatalf("third reserve after release: expected 200, got %d (%s)", rr3.Code, rr3.Body.String())
	}
}

// A key's COMMITTED spend (usage_logs this month) counts toward its sub-cap, so a
// key cannot reset its budget by letting jobs finish.
func TestGuardrailReserve_PerKeyCap_CommittedUsageCounts(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner, mcpKey := uuid.New(), uuid.New()
	const cap = 5.0

	// Seed $4 of committed spend this month attributed to the key.
	if _, err := pool.Exec(context.Background(), `
INSERT INTO usage_logs (request_id, owner_user_id, provider_kind, model_source, model_ref,
  total_cost_usd, billing_decision, request_status, mcp_key_id)
VALUES ($1,$2,'openai','user_model',$3,4.0,'recorded','success',$4)`,
		uuid.New(), owner, uuid.New(), mcpKey); err != nil {
		t.Fatalf("seed usage_logs: %v", err)
	}

	// $1.50 would push committed+estimate to $5.50 > $5 cap → 402.
	rr := callReserveWithKey(t, srv, owner, uuid.New(), mcpKey, 1.5, cap)
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402 from committed usage, got %d (%s)", rr.Code, rr.Body.String())
	}
	// $0.50 fits under the remaining $1.
	rr2 := callReserveWithKey(t, srv, owner, uuid.New(), mcpKey, 0.5, cap)
	if rr2.Code != http.StatusOK {
		t.Fatalf("expected $0.50 to fit under the cap, got %d (%s)", rr2.Code, rr2.Body.String())
	}
}

// A first-party reserve (no mcp_key_id) is never per-key capped — the cap path is
// inert for non-public traffic.
func TestGuardrailReserve_NoKey_NotCapped(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()
	// Two $4 reserves (no key) — owner daily is $10, so both pass; no per-key gate.
	if rr := callReserve(t, srv, owner, uuid.New(), 4.0); rr.Code != http.StatusOK {
		t.Fatalf("first no-key reserve: got %d", rr.Code)
	}
	if rr := callReserve(t, srv, owner, uuid.New(), 4.0); rr.Code != http.StatusOK {
		t.Fatalf("second no-key reserve: got %d", rr.Code)
	}
}

// ── reconcile ──────────────────────────────────────────────────────────────

func TestGuardrailReconcile_RecordsSpendAndDropsHold(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner, job := uuid.New(), uuid.New()

	resID := reservationIDFrom(t, callReserve(t, srv, owner, job, 4.0))
	if rr := callReconcile(t, srv, resID, 3.25); rr.Code != http.StatusOK {
		t.Fatalf("reconcile: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	g := readGuardrail(t, pool, owner)
	if g.dailySpent != 3.25 || g.monthlySpent != 3.25 {
		t.Fatalf("spend not recorded in both windows: daily=%v monthly=%v", g.dailySpent, g.monthlySpent)
	}
	if g.reserved != 0 {
		t.Fatalf("hold not dropped: reserved_usd=%v", g.reserved)
	}
	if s := reservationStatus(t, pool, resID); s != "reconciled" {
		t.Fatalf("expected status reconciled, got %q", s)
	}
}

func TestGuardrailReconcile_Idempotent_NoDoubleCount(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReserve(t, srv, owner, uuid.New(), 4.0))
	if rr := callReconcile(t, srv, resID, 2.0); rr.Code != http.StatusOK {
		t.Fatalf("first reconcile: expected 200, got %d", rr.Code)
	}
	// Second reconcile of the same reservation — must be a true no-op.
	if rr := callReconcile(t, srv, resID, 2.0); rr.Code != http.StatusOK {
		t.Fatalf("second reconcile: expected 200, got %d", rr.Code)
	}
	if g := readGuardrail(t, pool, owner); g.dailySpent != 2.0 {
		t.Fatalf("reconcile double-counted spend: expected 2.0, got %v", g.dailySpent)
	}
}

func TestGuardrailReconcile_OmittedActualUSD_ChargesEstimate(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	// Reserve 4.0, then reconcile WITHOUT an actual_usd — the recorded spend
	// must be the reservation's own estimate, and the hold must be dropped.
	resID := reservationIDFrom(t, callReserve(t, srv, owner, uuid.New(), 4.0))
	if rr := callReconcileNoActual(t, srv, resID); rr.Code != http.StatusOK {
		t.Fatalf("reconcile (no actual): expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	g := readGuardrail(t, pool, owner)
	if g.dailySpent != 4.0 || g.monthlySpent != 4.0 {
		t.Fatalf("estimate not charged: daily=%v monthly=%v", g.dailySpent, g.monthlySpent)
	}
	if g.reserved != 0 {
		t.Fatalf("hold not dropped: reserved_usd=%v", g.reserved)
	}
}

func TestGuardrailReconcile_NotFound_404(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	if rr := callReconcile(t, srv, uuid.New(), 1.0); rr.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d (%s)", rr.Code, rr.Body.String())
	}
}

// ── release ────────────────────────────────────────────────────────────────

func TestGuardrailRelease_DropsHoldNoSpend(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReserve(t, srv, owner, uuid.New(), 5.0))
	if rr := callRelease(t, srv, resID); rr.Code != http.StatusOK {
		t.Fatalf("release: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	g := readGuardrail(t, pool, owner)
	if g.reserved != 0 {
		t.Fatalf("hold not released: reserved_usd=%v", g.reserved)
	}
	if g.dailySpent != 0 || g.monthlySpent != 0 {
		t.Fatalf("release recorded spend: daily=%v monthly=%v", g.dailySpent, g.monthlySpent)
	}
	if s := reservationStatus(t, pool, resID); s != "released" {
		t.Fatalf("expected status released, got %q", s)
	}

	// Second release — idempotent no-op.
	if rr := callRelease(t, srv, resID); rr.Code != http.StatusOK {
		t.Fatalf("second release: expected 200, got %d", rr.Code)
	}
	if g := readGuardrail(t, pool, owner); g.reserved != 0 {
		t.Fatalf("double release drove reserved_usd off zero: %v", g.reserved)
	}
}

// ── lazy calendar reset ────────────────────────────────────────────────────

func TestGuardrailReconcile_LazyWindowReset(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReserve(t, srv, owner, uuid.New(), 1.0))

	// Backdate both windows and seed stale spend, as if the calendar had
	// rolled over while a hold was outstanding.
	if _, err := pool.Exec(context.Background(), `
UPDATE spend_guardrails SET
  daily_spent_usd = 5, daily_window_date = DATE '2000-01-01',
  monthly_spent_usd = 7, monthly_window_month = DATE '2000-01-01'
WHERE owner_user_id = $1`, owner); err != nil {
		t.Fatalf("backdate: %v", err)
	}

	// Reconcile must reset both stale windows to 0 BEFORE adding actual spend.
	if rr := callReconcile(t, srv, resID, 2.0); rr.Code != http.StatusOK {
		t.Fatalf("reconcile: expected 200, got %d", rr.Code)
	}
	g := readGuardrail(t, pool, owner)
	if g.dailySpent != 2.0 {
		t.Fatalf("daily window not reset before spend: expected 2.0, got %v", g.dailySpent)
	}
	if g.monthlySpent != 2.0 {
		t.Fatalf("monthly window not reset before spend: expected 2.0, got %v", g.monthlySpent)
	}
	today := time.Now().UTC().Truncate(24 * time.Hour)
	if !g.dailyWindow.UTC().Truncate(24 * time.Hour).Equal(today) {
		t.Fatalf("daily_window_date not advanced to today: %v", g.dailyWindow)
	}
}

// ── sweeper + swept-then-reconcile (review-impl HIGH#2) ─────────────────────

func TestSweeper_ReleasesExpiredHoldAndLateReconcileStillCharges(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReserve(t, srv, owner, uuid.New(), 6.0))

	// Force the hold past its TTL.
	if _, err := pool.Exec(context.Background(),
		`UPDATE token_reservations SET expires_at = now() - interval '1 hour' WHERE reservation_id = $1`,
		resID); err != nil {
		t.Fatalf("expire hold: %v", err)
	}

	n, err := srv.sweepExpiredReservations(context.Background())
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if n != 1 {
		t.Fatalf("expected 1 swept reservation, got %d", n)
	}
	if s := reservationStatus(t, pool, resID); s != "swept" {
		t.Fatalf("expected status swept, got %q", s)
	}
	if g := readGuardrail(t, pool, owner); g.reserved != 0 {
		t.Fatalf("sweeper did not drop the hold: reserved_usd=%v", g.reserved)
	}

	// HIGH#2: the job actually finished after being swept — its real spend
	// must still be recorded, and reserved_usd must NOT go negative (the
	// sweeper already dropped the hold).
	if rr := callReconcile(t, srv, resID, 4.5); rr.Code != http.StatusOK {
		t.Fatalf("late reconcile: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	g := readGuardrail(t, pool, owner)
	if g.dailySpent != 4.5 {
		t.Fatalf("swept-then-reconcile lost the spend: expected 4.5, got %v", g.dailySpent)
	}
	if g.reserved != 0 {
		t.Fatalf("swept-then-reconcile moved reserved_usd off zero: %v", g.reserved)
	}
	if s := reservationStatus(t, pool, resID); s != "reconciled" {
		t.Fatalf("expected status reconciled after late reconcile, got %q", s)
	}
}

func TestSweeper_LeavesFreshHoldUntouched(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReserve(t, srv, owner, uuid.New(), 1.0))
	n, err := srv.sweepExpiredReservations(context.Background())
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if n != 0 {
		t.Fatalf("expected 0 swept (hold is fresh), got %d", n)
	}
	if s := reservationStatus(t, pool, resID); s != "held" {
		t.Fatalf("fresh hold was swept: status=%q", s)
	}
}

// ── release after sweep (settleReservation swept+release branch) ────────────

func TestGuardrailRelease_OnSweptHold_IsNoOp(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReserve(t, srv, owner, uuid.New(), 2.0))
	if _, err := pool.Exec(context.Background(),
		`UPDATE token_reservations SET expires_at = now() - interval '1 hour' WHERE reservation_id = $1`,
		resID); err != nil {
		t.Fatalf("expire hold: %v", err)
	}
	if _, err := srv.sweepExpiredReservations(context.Background()); err != nil {
		t.Fatalf("sweep: %v", err)
	}

	// Releasing an already-swept hold must not drive reserved_usd negative.
	if rr := callRelease(t, srv, resID); rr.Code != http.StatusOK {
		t.Fatalf("release on swept: expected 200, got %d", rr.Code)
	}
	if g := readGuardrail(t, pool, owner); g.reserved != 0 {
		t.Fatalf("release-on-swept moved reserved_usd: %v", g.reserved)
	}
	if s := reservationStatus(t, pool, resID); s != "swept" {
		t.Fatalf("release-on-swept should leave status swept, got %q", s)
	}
}

// ── validation ─────────────────────────────────────────────────────────────

func TestGuardrailReserve_Validation(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)

	// Missing job_id.
	rr := callReserve(t, srv, uuid.New(), uuid.Nil, 1.0)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for nil job_id, got %d", rr.Code)
	}
	// Negative estimate.
	rr = callReserve(t, srv, uuid.New(), uuid.New(), -1.0)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for negative estimate, got %d", rr.Code)
	}
}

// ── Phase 6a-β — Subsystem B (platform resale ledger) ──────────────────────

func TestGuardrailReserve_Platform_HoldsBothLedgers(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	if rr := callReservePlatform(t, srv, owner, uuid.New(), 4.0); rr.Code != http.StatusOK {
		t.Fatalf("platform reserve: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	// A platform_model job holds in BOTH ledgers.
	if g := readGuardrail(t, pool, owner); g.reserved != 4.0 {
		t.Fatalf("spend_guardrails.reserved: got %v want 4.0", g.reserved)
	}
	b := readPlatformBalance(t, pool, owner)
	if b.reserved != 4.0 {
		t.Fatalf("platform_balances.reserved: got %v want 4.0", b.reserved)
	}
	if b.freeTierAllowance != guardrailTestFreeTier {
		t.Fatalf("platform_balances seeded wrong: got allowance %v", b.freeTierAllowance)
	}
}

func TestGuardrailReserve_UserModel_SkipsPlatformBalances(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	if rr := callReserve(t, srv, owner, uuid.New(), 3.0); rr.Code != http.StatusOK {
		t.Fatalf("user_model reserve: expected 200, got %d", rr.Code)
	}
	if platformBalanceExists(t, pool, owner) {
		t.Fatal("a user_model reserve must not create a platform_balances row")
	}
}

func TestGuardrailReserve_Platform_OverFreeTier_402(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	// Seed both rows with a small hold, then shrink the free tier so that
	// Subsystem B — not A — is the binding gate.
	if rr := callReservePlatform(t, srv, owner, uuid.New(), 1.0); rr.Code != http.StatusOK {
		t.Fatalf("setup reserve: %d", rr.Code)
	}
	if _, err := pool.Exec(context.Background(),
		`UPDATE platform_balances SET free_tier_allowance_usd = 5, credits_balance_usd = 0 WHERE owner_user_id=$1`,
		owner); err != nil {
		t.Fatalf("shrink free tier: %v", err)
	}
	// A-available ≈ 9 (daily 10 − reserved 1); B-available = 5 − 0 − 1 = 4.
	rr := callReservePlatform(t, srv, owner, uuid.New(), 8.0)
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d (%s)", rr.Code, rr.Body.String())
	}
	var out struct {
		Code string `json:"code"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if out.Code != "PLATFORM_BALANCE_EXHAUSTED" {
		t.Fatalf("expected PLATFORM_BALANCE_EXHAUSTED, got %q", out.Code)
	}
}

func TestGuardrailReserve_Platform_CreditsCoverBeyondFreeTier(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	if rr := callReservePlatform(t, srv, owner, uuid.New(), 1.0); rr.Code != http.StatusOK {
		t.Fatalf("setup reserve: %d", rr.Code)
	}
	// Free tier fully used; credits cover the next job.
	if _, err := pool.Exec(context.Background(), `
UPDATE platform_balances SET free_tier_used_usd = free_tier_allowance_usd, credits_balance_usd = 20
WHERE owner_user_id=$1`, owner); err != nil {
		t.Fatalf("exhaust free tier: %v", err)
	}
	// B-available = 50 − 50 − 1 + 20 = 19 ≥ 8.
	if rr := callReservePlatform(t, srv, owner, uuid.New(), 8.0); rr.Code != http.StatusOK {
		t.Fatalf("credits should cover beyond the free tier: got %d (%s)", rr.Code, rr.Body.String())
	}
}

func TestGuardrailReserve_Platform_SubsystemAStillEnforced_402(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	// Estimate 12 > the daily limit 10, but well within the $50 free tier.
	// The Subsystem A gate must still 402 a platform_model job.
	rr := callReservePlatform(t, srv, owner, uuid.New(), 12.0)
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d (%s)", rr.Code, rr.Body.String())
	}
	var out struct {
		Code string `json:"code"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if out.Code != "INSUFFICIENT_BUDGET" {
		t.Fatalf("expected INSUFFICIENT_BUDGET (Subsystem A), got %q", out.Code)
	}
}

func TestGuardrailReconcile_Platform_WithinFreeTier(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReservePlatform(t, srv, owner, uuid.New(), 5.0))
	if rr := callReconcile(t, srv, resID, 4.0); rr.Code != http.StatusOK {
		t.Fatalf("reconcile: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	b := readPlatformBalance(t, pool, owner)
	if b.freeTierUsed != 4.0 {
		t.Fatalf("free_tier_used: got %v want 4.0", b.freeTierUsed)
	}
	if b.creditsBalance != 0 {
		t.Fatalf("credits should be untouched within the free tier, got %v", b.creditsBalance)
	}
	if b.reserved != 0 {
		t.Fatalf("platform hold not dropped: reserved=%v", b.reserved)
	}
}

func TestGuardrailReconcile_Platform_SpillsToCredits(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReservePlatform(t, srv, owner, uuid.New(), 5.0))
	// Free tier all but $2 used; $10 of credits available.
	if _, err := pool.Exec(context.Background(), `
UPDATE platform_balances SET free_tier_used_usd = 48, credits_balance_usd = 10
WHERE owner_user_id=$1`, owner); err != nil {
		t.Fatalf("near-exhaust free tier: %v", err)
	}
	// Reconcile $5: $2 fills the free tier (→ 50), $3 spills to credits (→ 7).
	if rr := callReconcile(t, srv, resID, 5.0); rr.Code != http.StatusOK {
		t.Fatalf("reconcile: expected 200, got %d", rr.Code)
	}
	b := readPlatformBalance(t, pool, owner)
	if b.freeTierUsed != b.freeTierAllowance {
		t.Fatalf("free tier should be capped at allowance: used=%v allowance=%v", b.freeTierUsed, b.freeTierAllowance)
	}
	if b.creditsBalance != 7.0 {
		t.Fatalf("credits: got %v want 7.0 (10 − 3 spill)", b.creditsBalance)
	}
}

func TestGuardrailRelease_Platform_DropsHoldNoSpend(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReservePlatform(t, srv, owner, uuid.New(), 6.0))
	if rr := callRelease(t, srv, resID); rr.Code != http.StatusOK {
		t.Fatalf("release: expected 200, got %d", rr.Code)
	}
	b := readPlatformBalance(t, pool, owner)
	if b.reserved != 0 {
		t.Fatalf("platform hold not released: reserved=%v", b.reserved)
	}
	if b.freeTierUsed != 0 {
		t.Fatalf("release must record no spend, free_tier_used=%v", b.freeTierUsed)
	}
}

func TestSweeper_Platform_DropsHold_LateReconcileStillCharges(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	resID := reservationIDFrom(t, callReservePlatform(t, srv, owner, uuid.New(), 6.0))
	if _, err := pool.Exec(context.Background(),
		`UPDATE token_reservations SET expires_at = now() - interval '1 hour' WHERE reservation_id=$1`,
		resID); err != nil {
		t.Fatalf("expire hold: %v", err)
	}
	if _, err := srv.sweepExpiredReservations(context.Background()); err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if b := readPlatformBalance(t, pool, owner); b.reserved != 0 {
		t.Fatalf("sweeper did not drop the platform hold: reserved=%v", b.reserved)
	}
	// A swept platform job that later completes still records its spend.
	if rr := callReconcile(t, srv, resID, 3.5); rr.Code != http.StatusOK {
		t.Fatalf("late reconcile: expected 200, got %d", rr.Code)
	}
	b := readPlatformBalance(t, pool, owner)
	if b.freeTierUsed != 3.5 {
		t.Fatalf("swept-then-reconcile lost platform spend: free_tier_used=%v", b.freeTierUsed)
	}
	if b.reserved != 0 {
		t.Fatalf("swept-then-reconcile moved platform reserved off zero: %v", b.reserved)
	}
}

// TestGuardrailPlatform_FreeTierLazyReset locks the Subsystem B free-tier
// calendar-month reset on BOTH paths: platformRecordSQL (reconcile) and
// platformLockSQL (reserve). A stale free_tier_window_month must zero
// free_tier_used before the window is used (design §3.1 / §3.4).
func TestGuardrailPlatform_FreeTierLazyReset(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()
	ctx := context.Background()

	windowMonth := func() string {
		var d time.Time
		if err := pool.QueryRow(ctx,
			`SELECT free_tier_window_month FROM platform_balances WHERE owner_user_id=$1`, owner).
			Scan(&d); err != nil {
			t.Fatalf("read window: %v", err)
		}
		return d.Format("2006-01-02")
	}

	// ── platformRecordSQL reset (reconcile) ──
	resID := reservationIDFrom(t, callReservePlatform(t, srv, owner, uuid.New(), 5.0))
	if _, err := pool.Exec(ctx, `
UPDATE platform_balances SET free_tier_used_usd = 48, free_tier_window_month = DATE '2000-01-01'
WHERE owner_user_id=$1`, owner); err != nil {
		t.Fatalf("backdate: %v", err)
	}
	if rr := callReconcile(t, srv, resID, 3.0); rr.Code != http.StatusOK {
		t.Fatalf("reconcile: expected 200, got %d", rr.Code)
	}
	b := readPlatformBalance(t, pool, owner)
	if b.freeTierUsed != 3.0 {
		t.Fatalf("reconcile must reset the stale window to 0 before adding: free_tier_used=%v want 3.0", b.freeTierUsed)
	}
	if windowMonth() == "2000-01-01" {
		t.Fatal("reconcile did not advance free_tier_window_month")
	}

	// ── platformLockSQL reset (reserve) ──
	// Backdate again with the free tier near-exhausted: without the reset
	// the next reserve would 402 (bAvail = 50 − 48 = 2 < 8); with it,
	// free_tier_used zeroes and bAvail = 50 ≥ 8.
	if _, err := pool.Exec(ctx, `
UPDATE platform_balances SET free_tier_used_usd = 48, free_tier_window_month = DATE '2000-01-01'
WHERE owner_user_id=$1`, owner); err != nil {
		t.Fatalf("re-backdate: %v", err)
	}
	if rr := callReservePlatform(t, srv, owner, uuid.New(), 8.0); rr.Code != http.StatusOK {
		t.Fatalf("reserve after a stale window must reset the free tier and admit the job: got %d (%s)",
			rr.Code, rr.Body.String())
	}
	if b := readPlatformBalance(t, pool, owner); b.freeTierUsed != 0 {
		t.Fatalf("reserve did not reset the stale free_tier_used: got %v", b.freeTierUsed)
	}
}

// TestRecordInvocation_Idempotent_NoDoubleWrite locks the Phase 6a-β /record
// idempotency: a retry with the SAME request_id must not write a second audit row.
// (D-S4C-ACCOUNTBALANCES-DROP: the token ledger is retired — /record no longer
// deducts a quota, so the real idempotency artifact is the usage_logs row count,
// guarded by the request_id UNIQUE; the old account_balances quota check is gone.)
func TestRecordInvocation_Idempotent_NoDoubleWrite(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()
	reqID := uuid.New()
	modelRef := uuid.New()

	callRecord := func() *httptest.ResponseRecorder {
		body, _ := json.Marshal(map[string]any{
			"request_id": reqID, "owner_user_id": owner, "model_ref": modelRef,
			"provider_kind": "openai", "model_source": "user_model",
			"input_tokens": 100, "output_tokens": 50,
		})
		req := httptest.NewRequest(http.MethodPost, "/internal/model-billing/record", bytes.NewReader(body))
		rr := httptest.NewRecorder()
		srv.recordInvocation(rr, req)
		return rr
	}
	countLogs := func() int {
		var n int
		if err := pool.QueryRow(context.Background(),
			`SELECT count(*) FROM usage_logs WHERE request_id=$1`, reqID).
			Scan(&n); err != nil {
			t.Fatalf("count usage_logs: %v", err)
		}
		return n
	}

	if rr := callRecord(); rr.Code != http.StatusCreated {
		t.Fatalf("first record: expected 201, got %d (%s)", rr.Code, rr.Body.String())
	}
	if afterFirst := countLogs(); afterFirst != 1 {
		t.Fatalf("first record: expected 1 usage_logs row, got %d", afterFirst)
	}

	// Retry with the SAME request_id — must be idempotent (re-read, no second row).
	if rr := callRecord(); rr.Code != http.StatusCreated {
		t.Fatalf("retry record: expected 201, got %d (%s)", rr.Code, rr.Body.String())
	}
	if afterRetry := countLogs(); afterRetry != 1 {
		t.Fatalf("duplicate request_id double-wrote usage_logs: expected 1 row, got %d", afterRetry)
	}
}

// ── Phase 6a-γ — user-facing guardrail GET/PATCH + platform-balance GET ─────

func callGuardrailGet(t *testing.T, srv *Server, userID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/model-billing/guardrail", nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, guardrailTestSecret, userID, "user"))
	rr := httptest.NewRecorder()
	srv.getGuardrail(rr, req)
	return rr
}

func callGuardrailPatch(t *testing.T, srv *Server, userID uuid.UUID, body map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPatch, "/v1/model-billing/guardrail", bytes.NewReader(raw))
	req.Header.Set("Authorization", "Bearer "+signedToken(t, guardrailTestSecret, userID, "user"))
	rr := httptest.NewRecorder()
	srv.patchGuardrail(rr, req)
	return rr
}

func decodeGuardrail(t *testing.T, rr *httptest.ResponseRecorder) map[string]float64 {
	t.Helper()
	var m map[string]float64
	if err := json.Unmarshal(rr.Body.Bytes(), &m); err != nil {
		t.Fatalf("decode guardrail body %q: %v", rr.Body.String(), err)
	}
	return m
}

func TestGetGuardrail_NoRow_ReturnsConfigDefaults(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)

	rr := callGuardrailGet(t, srv, uuid.New())
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	g := decodeGuardrail(t, rr)
	if g["daily_limit_usd"] != guardrailTestDaily || g["monthly_limit_usd"] != guardrailTestMonthly {
		t.Fatalf("no-row GET should return config defaults: %+v", g)
	}
	if g["daily_spent_usd"] != 0 || g["reserved_usd"] != 0 {
		t.Fatalf("no-row GET should report zero spend/reserved: %+v", g)
	}
}

func TestGetGuardrail_ReflectsAReservation(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	if rr := callReserve(t, srv, owner, uuid.New(), 3.0); rr.Code != http.StatusOK {
		t.Fatalf("setup reserve: %d", rr.Code)
	}
	g := decodeGuardrail(t, callGuardrailGet(t, srv, owner))
	if g["reserved_usd"] != 3.0 {
		t.Fatalf("GET should reflect the held reservation: reserved=%v", g["reserved_usd"])
	}
	if g["daily_available_usd"] != guardrailTestDaily-3.0 {
		t.Fatalf("daily_available should net out the hold: %v", g["daily_available_usd"])
	}
}

func TestPatchGuardrail_SetsLimits(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	rr := callGuardrailPatch(t, srv, owner, map[string]any{"daily_limit_usd": 25.0})
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	g := decodeGuardrail(t, rr)
	if g["daily_limit_usd"] != 25.0 {
		t.Fatalf("daily_limit not set: %v", g["daily_limit_usd"])
	}
	if g["monthly_limit_usd"] != guardrailTestMonthly {
		t.Fatalf("monthly_limit should be untouched: %v", g["monthly_limit_usd"])
	}
	if g2 := decodeGuardrail(t, callGuardrailGet(t, srv, owner)); g2["daily_limit_usd"] != 25.0 {
		t.Fatalf("PATCH did not persist: GET shows %v", g2["daily_limit_usd"])
	}
}

func TestPatchGuardrail_Validation(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)

	if rr := callGuardrailPatch(t, srv, uuid.New(), map[string]any{}); rr.Code != http.StatusBadRequest {
		t.Fatalf("empty body should 400, got %d", rr.Code)
	}
	if rr := callGuardrailPatch(t, srv, uuid.New(), map[string]any{"daily_limit_usd": 0}); rr.Code != http.StatusBadRequest {
		t.Fatalf("zero limit should 400, got %d", rr.Code)
	}
	if rr := callGuardrailPatch(t, srv, uuid.New(), map[string]any{"monthly_limit_usd": -5}); rr.Code != http.StatusBadRequest {
		t.Fatalf("negative limit should 400, got %d", rr.Code)
	}
}

func TestGetPlatformBalance_NoRow_ReturnsConfigFreeTier(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)

	req := httptest.NewRequest(http.MethodGet, "/v1/model-billing/platform-balance", nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, guardrailTestSecret, uuid.New(), "user"))
	rr := httptest.NewRecorder()
	srv.getPlatformBalance(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var m map[string]float64
	_ = json.Unmarshal(rr.Body.Bytes(), &m)
	if m["free_tier_allowance_usd"] != guardrailTestFreeTier {
		t.Fatalf("no-row GET should return the config free tier: %+v", m)
	}
	if m["free_tier_remaining_usd"] != guardrailTestFreeTier {
		t.Fatalf("free_tier_remaining should equal allowance when nothing used: %+v", m)
	}
}

func TestGetPlatformBalance_ReflectsAReservation(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	if rr := callReservePlatform(t, srv, owner, uuid.New(), 4.0); rr.Code != http.StatusOK {
		t.Fatalf("setup platform reserve: %d", rr.Code)
	}
	req := httptest.NewRequest(http.MethodGet, "/v1/model-billing/platform-balance", nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, guardrailTestSecret, owner, "user"))
	rr := httptest.NewRecorder()
	srv.getPlatformBalance(rr, req)
	var m map[string]float64
	_ = json.Unmarshal(rr.Body.Bytes(), &m)
	if m["reserved_usd"] != 4.0 {
		t.Fatalf("platform-balance GET should reflect the held reservation: %+v", m)
	}
}

// ── WS-2.8 — internal guardrail status read (the distiller's degrade pre-check) ──

func callGuardrailStatus(t *testing.T, srv *Server, ownerArg string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/internal/billing/guardrail/status?owner_user_id="+ownerArg, nil)
	rr := httptest.NewRecorder()
	srv.getGuardrailStatusInternal(rr, req)
	return rr
}

func TestGuardrailStatusInternal_ReflectsSpendAndExhaustion(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	// No row yet → config defaults, nothing spent, full daily available.
	rr := callGuardrailStatus(t, srv, owner.String())
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var s struct {
		DailyLimit     float64 `json:"daily_limit_usd"`
		DailyAvailable float64 `json:"daily_available_usd"`
		DailySpent     float64 `json:"daily_spent_usd"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &s); err != nil {
		t.Fatalf("decode status: %v", err)
	}
	if s.DailyLimit != guardrailTestDaily || s.DailyAvailable != guardrailTestDaily || s.DailySpent != 0 {
		t.Fatalf("fresh status: got limit=%v avail=%v spent=%v", s.DailyLimit, s.DailyAvailable, s.DailySpent)
	}

	// Reserve the WHOLE daily cap → the distiller's degrade condition (daily_available_usd <= 0) holds.
	if callReserve(t, srv, owner, uuid.New(), guardrailTestDaily).Code != http.StatusOK {
		t.Fatal("reserve of the full daily cap should succeed")
	}
	rr2 := callGuardrailStatus(t, srv, owner.String())
	_ = json.Unmarshal(rr2.Body.Bytes(), &s)
	if s.DailyAvailable > 0 {
		t.Fatalf("after reserving the full cap, daily_available should be <= 0, got %v", s.DailyAvailable)
	}
}

func TestGuardrailStatusInternal_BadOwner_400(t *testing.T) {
	srv := newGuardrailServer(t, nil)
	if rr := callGuardrailStatus(t, srv, "not-a-uuid"); rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for a non-UUID owner, got %d", rr.Code)
	}
}
