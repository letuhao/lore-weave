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
	guardrailTestSecret  = "test_jwt_secret_at_least_32_characters_long"
	guardrailTestDaily   = 10.0
	guardrailTestMonthly = 100.0
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
		`TRUNCATE spend_guardrails, token_reservations`); err != nil {
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
		ReservationTTL:             45 * time.Minute,
	})
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
