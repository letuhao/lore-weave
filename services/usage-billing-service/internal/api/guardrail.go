package api

// Phase 6a Subsystem A — USD spend guardrail handlers (reserve / reconcile /
// release). Pre-flight estimate-based reservation that protects the user's
// wallet. See docs/03_planning/LLM_PIPELINE_PHASE6A_DESIGN.md §3.4.

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

const pgUniqueViolation = "23505"

// reserveLockSQL: FOR-UPDATE-locks the guardrail row, performs the lazy
// calendar reset of both windows, and returns the current figures. All date
// comparisons use the DB clock (now() AT TIME ZONE 'utc') — never an
// app-supplied date (review-impl MED#8).
const reserveLockSQL = `
UPDATE spend_guardrails SET
  daily_spent_usd      = CASE WHEN daily_window_date    < (now() AT TIME ZONE 'utc')::date
                              THEN 0 ELSE daily_spent_usd END,
  daily_window_date    = CASE WHEN daily_window_date    < (now() AT TIME ZONE 'utc')::date
                              THEN (now() AT TIME ZONE 'utc')::date ELSE daily_window_date END,
  monthly_spent_usd    = CASE WHEN monthly_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                              THEN 0 ELSE monthly_spent_usd END,
  monthly_window_month = CASE WHEN monthly_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                              THEN date_trunc('month', now() AT TIME ZONE 'utc')::date ELSE monthly_window_month END,
  updated_at = now()
WHERE owner_user_id = $1
RETURNING daily_limit_usd, monthly_limit_usd, daily_spent_usd, monthly_spent_usd, reserved_usd`

// recordSpendSQL: lazy-resets the windows AND adds $2 (actual USD) to both
// spent figures in one statement; $3 is the hold to drop (0 when the hold was
// already dropped by the sweeper).
const recordSpendSQL = `
UPDATE spend_guardrails SET
  daily_spent_usd      = (CASE WHEN daily_window_date    < (now() AT TIME ZONE 'utc')::date
                               THEN 0 ELSE daily_spent_usd END) + $2,
  daily_window_date    = CASE WHEN daily_window_date    < (now() AT TIME ZONE 'utc')::date
                              THEN (now() AT TIME ZONE 'utc')::date ELSE daily_window_date END,
  monthly_spent_usd    = (CASE WHEN monthly_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                               THEN 0 ELSE monthly_spent_usd END) + $2,
  monthly_window_month = CASE WHEN monthly_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                              THEN date_trunc('month', now() AT TIME ZONE 'utc')::date ELSE monthly_window_month END,
  reserved_usd         = reserved_usd - $3,
  updated_at           = now()
WHERE owner_user_id = $1`

// platformLockSQL: FOR-UPDATE-locks the platform_balances row and lazily
// resets the free-tier calendar-month window (mirrors reserveLockSQL). Used
// only for a platform_model reservation — Subsystem B (Phase 6a-β).
const platformLockSQL = `
UPDATE platform_balances SET
  free_tier_used_usd     = CASE WHEN free_tier_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                                THEN 0 ELSE free_tier_used_usd END,
  free_tier_window_month = CASE WHEN free_tier_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                                THEN date_trunc('month', now() AT TIME ZONE 'utc')::date ELSE free_tier_window_month END,
  updated_at = now()
WHERE owner_user_id = $1
RETURNING free_tier_allowance_usd, free_tier_used_usd, credits_balance_usd, reserved_usd`

// platformRecordSQL: lazily resets the free-tier window, then deducts $2
// (actual USD) — free tier first, the remainder from credits — and drops $3
// (the hold; 0 when the sweeper already dropped it). Subsystem B reconcile.
const platformRecordSQL = `
UPDATE platform_balances SET
  free_tier_used_usd  = LEAST(
                          (CASE WHEN free_tier_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                                THEN 0 ELSE free_tier_used_usd END) + $2,
                          free_tier_allowance_usd),
  credits_balance_usd = credits_balance_usd - GREATEST(
                          (CASE WHEN free_tier_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                                THEN 0 ELSE free_tier_used_usd END) + $2 - free_tier_allowance_usd,
                          0),
  free_tier_window_month = CASE WHEN free_tier_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
                                THEN date_trunc('month', now() AT TIME ZONE 'utc')::date ELSE free_tier_window_month END,
  reserved_usd        = reserved_usd - $3,
  updated_at          = now()
WHERE owner_user_id = $1`

// guardrailReserve — POST /internal/billing/guardrail/reserve.
//
// A platform_model job reserves against BOTH Subsystem A (spend_guardrails —
// the user's cap) AND Subsystem B (platform_balances — LoreWeave's free tier
// + credits). A user_model job reserves against Subsystem A only.
func (s *Server) guardrailReserve(w http.ResponseWriter, r *http.Request) {
	var in struct {
		OwnerUserID  uuid.UUID  `json:"owner_user_id"`
		JobID        uuid.UUID  `json:"job_id"`
		EstimatedUSD float64    `json:"estimated_usd"`
		ModelSource  string     `json:"model_source"`
		McpKeyID     *uuid.UUID `json:"mcp_key_id,omitempty"`     // P4/Wave-C (H-K) — public key, per-key cap
		SpendCapUSD  *float64   `json:"spend_cap_usd,omitempty"`  // P4/Wave-C (H-K) — the key's sub-cap
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "invalid payload")
		return
	}
	if in.OwnerUserID == uuid.Nil || in.JobID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "owner_user_id and job_id required")
		return
	}
	if in.EstimatedUSD < 0 {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "estimated_usd must be >= 0")
		return
	}
	// model_source defaults to user_model when absent (back-compat for any
	// caller not yet sending it); only platform_model engages Subsystem B.
	if in.ModelSource == "" {
		in.ModelSource = "user_model"
	}
	if in.ModelSource != "user_model" && in.ModelSource != "platform_model" {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "invalid model_source")
		return
	}
	isPlatform := in.ModelSource == "platform_model"
	ctx := r.Context()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to start tx")
		return
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// Seed the guardrail row from config defaults on first contact.
	if _, err := tx.Exec(ctx, `
INSERT INTO spend_guardrails(owner_user_id, daily_limit_usd, monthly_limit_usd)
VALUES ($1,$2,$3) ON CONFLICT (owner_user_id) DO NOTHING`,
		in.OwnerUserID, s.cfg.GuardrailDefaultDailyUSD, s.cfg.GuardrailDefaultMonthlyUSD); err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to seed guardrail")
		return
	}
	// Phase 6a-β — seed the platform_balances row from the config free tier
	// on first contact (platform_model jobs only).
	if isPlatform {
		if _, err := tx.Exec(ctx, `
INSERT INTO platform_balances(owner_user_id, free_tier_allowance_usd)
VALUES ($1,$2) ON CONFLICT (owner_user_id) DO NOTHING`,
			in.OwnerUserID, s.cfg.PlatformFreeTierUSD); err != nil {
			writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to seed platform balance")
			return
		}
	}

	// Idempotency FIRST: a held reservation for this job already exists →
	// return it, do NOT insert and do NOT bump reserved_usd (review-impl HIGH#3).
	var existing uuid.UUID
	err = tx.QueryRow(ctx, `
SELECT reservation_id FROM token_reservations WHERE job_id = $1 AND status = 'held'`,
		in.JobID).Scan(&existing)
	if err == nil {
		if err := tx.Commit(ctx); err != nil {
			writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to commit")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"reservation_id": existing})
		return
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "idempotency check failed")
		return
	}

	// FOR UPDATE lock + lazy calendar reset.
	var dailyLimit, monthlyLimit, dailySpent, monthlySpent, reserved float64
	if err := tx.QueryRow(ctx, reserveLockSQL, in.OwnerUserID).
		Scan(&dailyLimit, &monthlyLimit, &dailySpent, &monthlySpent, &reserved); err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to load guardrail")
		return
	}

	dailyAvail := dailyLimit - dailySpent - reserved
	monthlyAvail := monthlyLimit - monthlySpent - reserved
	minAvail := dailyAvail
	if monthlyAvail < minAvail {
		minAvail = monthlyAvail
	}
	// A zero-cost job (explicitly-free model) is never gated.
	if in.EstimatedUSD > 0 && in.EstimatedUSD > minAvail {
		_ = tx.Rollback(ctx)
		writeJSON(w, http.StatusPaymentRequired, map[string]any{
			"code":              "INSUFFICIENT_BUDGET",
			"daily_available":   dailyAvail,
			"monthly_available": monthlyAvail,
			"requested":         in.EstimatedUSD,
		})
		return
	}

	// Phase 6a-β — Subsystem B gate (platform_model only). The
	// platform_balances row is FOR-UPDATE-locked AFTER spend_guardrails;
	// every path (reserve / reconcile / sweep) locks A then B in that order,
	// so there is no deadlock.
	if isPlatform {
		var ftAllowance, ftUsed, credits, platReserved float64
		if err := tx.QueryRow(ctx, platformLockSQL, in.OwnerUserID).
			Scan(&ftAllowance, &ftUsed, &credits, &platReserved); err != nil {
			writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to load platform balance")
			return
		}
		// The pool the caller may still draw on: free tier left + credits,
		// minus other held platform reservations.
		bAvail := ftAllowance - ftUsed - platReserved + credits
		if in.EstimatedUSD > 0 && in.EstimatedUSD > bAvail {
			_ = tx.Rollback(ctx)
			writeJSON(w, http.StatusPaymentRequired, map[string]any{
				"code":               "PLATFORM_BALANCE_EXHAUSTED",
				"platform_available": bAvail,
				"requested":          in.EstimatedUSD,
			})
			return
		}
	}

	// Public MCP P4/Wave-C (H-K) — per-key spend sub-cap. Enforced INSIDE the
	// owner-row FOR UPDATE lock taken above, which serializes EVERY reserve for
	// this owner — and thus every concurrent reserve for this owner's key — so the
	// read-then-check below is race-safe without any new lock. The key's running
	// spend = COMMITTED (usage_logs this calendar month) + HELD (this key's other
	// in-flight reservations); reject when this estimate would push it over the
	// cap. Secondary to the owner guardrail above (which gates first); a zero-cost
	// job is never gated. Only public-key calls carry mcp_key_id + cap.
	if in.McpKeyID != nil && in.SpendCapUSD != nil && in.EstimatedUSD > 0 {
		var committed, held float64
		if err := tx.QueryRow(ctx, `
SELECT COALESCE(SUM(total_cost_usd), 0) FROM usage_logs
WHERE mcp_key_id = $1 AND created_at >= date_trunc('month', now() AT TIME ZONE 'utc')`,
			*in.McpKeyID).Scan(&committed); err != nil {
			writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to sum key spend")
			return
		}
		if err := tx.QueryRow(ctx, `
SELECT COALESCE(SUM(estimated_usd), 0) FROM token_reservations
WHERE mcp_key_id = $1 AND status = 'held'`,
			*in.McpKeyID).Scan(&held); err != nil {
			writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to sum key holds")
			return
		}
		keyAvail := *in.SpendCapUSD - committed - held
		if in.EstimatedUSD > keyAvail {
			_ = tx.Rollback(ctx)
			writeJSON(w, http.StatusPaymentRequired, map[string]any{
				"code":          "MCP_KEY_CAP_EXCEEDED",
				"key_available": keyAvail,
				"requested":     in.EstimatedUSD,
			})
			return
		}
	}

	// Insert the hold + bump reserved_usd as one atomic unit.
	var resID uuid.UUID
	err = tx.QueryRow(ctx, `
INSERT INTO token_reservations(owner_user_id, job_id, estimated_usd, status, expires_at, model_source, mcp_key_id)
VALUES ($1,$2,$3,'held',$4,$5,$6) RETURNING reservation_id`,
		in.OwnerUserID, in.JobID, in.EstimatedUSD, time.Now().Add(s.cfg.ReservationTTL), in.ModelSource, in.McpKeyID).Scan(&resID)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == pgUniqueViolation {
			// A concurrent reserve for the same job won the race. Roll back
			// (the failed INSERT poisoned this tx) and return the winner.
			_ = tx.Rollback(ctx)
			var dup uuid.UUID
			if qerr := s.pool.QueryRow(ctx, `
SELECT reservation_id FROM token_reservations WHERE job_id=$1 AND status='held'`,
				in.JobID).Scan(&dup); qerr != nil {
				writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "race resolution failed")
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"reservation_id": dup})
			return
		}
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to insert reservation")
		return
	}
	if _, err := tx.Exec(ctx, `
UPDATE spend_guardrails SET reserved_usd = reserved_usd + $2, updated_at = now()
WHERE owner_user_id = $1`, in.OwnerUserID, in.EstimatedUSD); err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to update reserved")
		return
	}
	// Phase 6a-β — bump the Subsystem B hold for a platform_model job.
	if isPlatform {
		if _, err := tx.Exec(ctx, `
UPDATE platform_balances SET reserved_usd = reserved_usd + $2, updated_at = now()
WHERE owner_user_id = $1`, in.OwnerUserID, in.EstimatedUSD); err != nil {
			writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to update platform reserved")
			return
		}
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to commit")
		return
	}
	// daily_available / monthly_available are the step-5 figures (limit −
	// spent − reserved, BEFORE this reservation's bump) — how much this
	// caller may still spend in total. The streaming guardrail (Phase 6a-δ)
	// uses them as the mid-stream hard-abort threshold; the job path ignores
	// them.
	writeJSON(w, http.StatusOK, map[string]any{
		"reservation_id":    resID,
		"daily_available":   dailyAvail,
		"monthly_available": monthlyAvail,
	})
}

// guardrailReconcile — POST /internal/billing/guardrail/reconcile.
// Records actual spend; idempotent; records spend even for a swept reservation
// (review-impl HIGH#2 — a swept-then-completed job still spent real money).
//
// actual_usd is OPTIONAL: when omitted (null), the spend recorded is the
// reservation's own stored estimated_usd. The gateway worker sends a real
// figure for text jobs whose token usage is known, and omits it for media /
// usage-unknown jobs so the (exact, per-unit) estimate stands.
func (s *Server) guardrailReconcile(w http.ResponseWriter, r *http.Request) {
	var in struct {
		ReservationID uuid.UUID `json:"reservation_id"`
		ActualUSD     *float64  `json:"actual_usd"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "invalid payload")
		return
	}
	if in.ReservationID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "reservation_id required")
		return
	}
	if in.ActualUSD != nil && *in.ActualUSD < 0 {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "actual_usd must be >= 0")
		return
	}
	if err := s.settleReservation(r.Context(), in.ReservationID, true, in.ActualUSD); err != nil {
		if errors.Is(err, errReservationNotFound) {
			writeError(w, http.StatusNotFound, "GUARDRAIL_NOT_FOUND", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// guardrailRelease — POST /internal/billing/guardrail/release.
// Frees a held reservation with no spend (failed/cancelled job). Idempotent.
func (s *Server) guardrailRelease(w http.ResponseWriter, r *http.Request) {
	var in struct {
		ReservationID uuid.UUID `json:"reservation_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "invalid payload")
		return
	}
	if in.ReservationID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "reservation_id required")
		return
	}
	if err := s.settleReservation(r.Context(), in.ReservationID, false, nil); err != nil {
		if errors.Is(err, errReservationNotFound) {
			writeError(w, http.StatusNotFound, "GUARDRAIL_NOT_FOUND", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

var errReservationNotFound = errors.New("reservation not found")

// settleReservation is the shared reconcile/release transaction.
//
//	reconcile=true  → record spend into both spent windows.
//	reconcile=false → release, record no spend.
//
// actualUSD applies only when reconcile=true: a non-nil pointer is the real
// spend; nil means "use the reservation's own estimated_usd" (the caller did
// not measure actual cost — see guardrailReconcile).
//
// Branches on the reservation's stored status:
//   - held       → settle: (reconcile) add spend + drop hold; (release) drop hold.
//   - swept      → reconcile records spend WITHOUT touching reserved_usd (the
//     sweeper already dropped the hold); release is a no-op.
//   - reconciled → true no-op (idempotent).
//   - released   → no-op.
func (s *Server) settleReservation(ctx context.Context, resID uuid.UUID, reconcile bool, actualUSD *float64) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return errors.New("failed to start tx")
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var ownerID uuid.UUID
	var estimated float64
	var status, modelSource string
	err = tx.QueryRow(ctx, `
SELECT owner_user_id, estimated_usd, status, model_source FROM token_reservations
WHERE reservation_id = $1 FOR UPDATE`, resID).Scan(&ownerID, &estimated, &status, &modelSource)
	if errors.Is(err, pgx.ErrNoRows) {
		return errReservationNotFound
	}
	if err != nil {
		return errors.New("failed to load reservation")
	}

	switch {
	case status == "reconciled" || status == "released":
		return tx.Commit(ctx) // idempotent no-op
	case !reconcile && status == "swept":
		return tx.Commit(ctx) // release on an already-swept hold: nothing to do
	}

	// Lock the guardrail row for the duration of the settlement.
	if _, err := tx.Exec(ctx, `SELECT 1 FROM spend_guardrails WHERE owner_user_id=$1 FOR UPDATE`, ownerID); err != nil {
		return errors.New("failed to lock guardrail")
	}

	if reconcile {
		// A nil actualUSD means the caller did not measure real cost — fall
		// back to the reservation's own estimate as the spend.
		spend := estimated
		if actualUSD != nil {
			spend = *actualUSD
		}
		// 'swept' already had its hold dropped by the sweeper → drop $0 more.
		holdToDrop := estimated
		if status == "swept" {
			holdToDrop = 0
		}
		if _, err := tx.Exec(ctx, recordSpendSQL, ownerID, spend, holdToDrop); err != nil {
			return errors.New("failed to record spend")
		}
		// Phase 6a-β — Subsystem B reconcile: deduct the same spend from
		// the free tier (then credits) and drop the B hold. Lock B after A.
		if modelSource == "platform_model" {
			if _, err := tx.Exec(ctx, `SELECT 1 FROM platform_balances WHERE owner_user_id=$1 FOR UPDATE`, ownerID); err != nil {
				return errors.New("failed to lock platform balance")
			}
			if _, err := tx.Exec(ctx, platformRecordSQL, ownerID, spend, holdToDrop); err != nil {
				return errors.New("failed to record platform spend")
			}
		}
		if _, err := tx.Exec(ctx, `
UPDATE token_reservations SET status='reconciled', updated_at=now() WHERE reservation_id=$1`,
			resID); err != nil {
			return errors.New("failed to update reservation")
		}
	} else {
		// Release a held hold: drop it, no spend.
		if _, err := tx.Exec(ctx, `
UPDATE spend_guardrails SET reserved_usd = reserved_usd - $2, updated_at = now()
WHERE owner_user_id = $1`, ownerID, estimated); err != nil {
			return errors.New("failed to release hold")
		}
		// Phase 6a-β — Subsystem B release: drop the B hold, no spend.
		if modelSource == "platform_model" {
			if _, err := tx.Exec(ctx, `SELECT 1 FROM platform_balances WHERE owner_user_id=$1 FOR UPDATE`, ownerID); err != nil {
				return errors.New("failed to lock platform balance")
			}
			if _, err := tx.Exec(ctx, `
UPDATE platform_balances SET reserved_usd = reserved_usd - $2, updated_at = now()
WHERE owner_user_id = $1`, ownerID, estimated); err != nil {
				return errors.New("failed to release platform hold")
			}
		}
		if _, err := tx.Exec(ctx, `
UPDATE token_reservations SET status='released', updated_at=now() WHERE reservation_id=$1`,
			resID); err != nil {
			return errors.New("failed to update reservation")
		}
	}
	return tx.Commit(ctx)
}

// ── Phase 6a-γ — user-facing guardrail read/config + platform balance ──────

// guardrailReadSQL — window-aware read of a spend_guardrails row. A stale
// window displays spent as 0 (a GET must not mutate; the next reserve resets
// it for real).
const guardrailReadSQL = `
SELECT daily_limit_usd, monthly_limit_usd,
  CASE WHEN daily_window_date    < (now() AT TIME ZONE 'utc')::date
       THEN 0 ELSE daily_spent_usd END,
  CASE WHEN monthly_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
       THEN 0 ELSE monthly_spent_usd END,
  reserved_usd
FROM spend_guardrails WHERE owner_user_id = $1`

// platformReadSQL — window-aware read of a platform_balances row.
const platformReadSQL = `
SELECT free_tier_allowance_usd,
  CASE WHEN free_tier_window_month < date_trunc('month', now() AT TIME ZONE 'utc')::date
       THEN 0 ELSE free_tier_used_usd END,
  credits_balance_usd, reserved_usd
FROM platform_balances WHERE owner_user_id = $1`

// writeGuardrailJSON emits the guardrail body (shared by GET + PATCH).
func writeGuardrailJSON(w http.ResponseWriter, dLimit, mLimit, dSpent, mSpent, reserved float64) {
	writeJSON(w, http.StatusOK, map[string]any{
		"daily_limit_usd":       dLimit,
		"monthly_limit_usd":     mLimit,
		"daily_spent_usd":       dSpent,
		"monthly_spent_usd":     mSpent,
		"reserved_usd":          reserved,
		"daily_available_usd":   dLimit - dSpent - reserved,
		"monthly_available_usd": mLimit - mSpent - reserved,
	})
}

// getGuardrail — GET /v1/model-billing/guardrail. The authed user's
// Subsystem-A limits + (window-aware) spend. No row yet → config defaults.
func (s *Server) getGuardrail(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var dLimit, mLimit, dSpent, mSpent, reserved float64
	err := s.pool.QueryRow(r.Context(), guardrailReadSQL, userID).
		Scan(&dLimit, &mLimit, &dSpent, &mSpent, &reserved)
	if errors.Is(err, pgx.ErrNoRows) {
		dLimit, mLimit = s.cfg.GuardrailDefaultDailyUSD, s.cfg.GuardrailDefaultMonthlyUSD
		dSpent, mSpent, reserved = 0, 0, 0
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_GUARDRAIL_FAILED", "failed to read guardrail")
		return
	}
	writeGuardrailJSON(w, dLimit, mLimit, dSpent, mSpent, reserved)
}

// getGuardrailStatusInternal — GET /internal/billing/guardrail/status?owner_user_id=<uuid>.
//
// WS-2.8 (spec 10) — an internal-token READ of a user's spend guardrail so a BACKGROUND worker (the
// diary distiller) can DEGRADE gracefully BEFORE spending: if the user's daily cap is exhausted, the
// worker skips with a "memory paused — daily cap reached" status instead of letting each LLM call fail
// hard mid-run at the provider-gateway (which reserves against this same guardrail — the hard backstop).
// owner_user_id is an explicit query arg (the caller already authenticated the owner), like
// getMcpKeyUsage. A window-stale row reads spent as 0 (guardrailReadSQL), so this never mutates.
func (s *Server) getGuardrailStatusInternal(w http.ResponseWriter, r *http.Request) {
	owner, err := uuid.Parse(r.URL.Query().Get("owner_user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "owner_user_id must be a UUID")
		return
	}
	var dLimit, mLimit, dSpent, mSpent, reserved float64
	err = s.pool.QueryRow(r.Context(), guardrailReadSQL, owner).
		Scan(&dLimit, &mLimit, &dSpent, &mSpent, &reserved)
	if errors.Is(err, pgx.ErrNoRows) {
		// No row yet → the config defaults, nothing spent.
		dLimit, mLimit = s.cfg.GuardrailDefaultDailyUSD, s.cfg.GuardrailDefaultMonthlyUSD
		dSpent, mSpent, reserved = 0, 0, 0
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_FAILED", "failed to read guardrail")
		return
	}
	writeGuardrailJSON(w, dLimit, mLimit, dSpent, mSpent, reserved)
}

// patchGuardrail — PATCH /v1/model-billing/guardrail. Sets the authed user's
// daily and/or monthly USD limit. Either field may be omitted; a supplied
// limit must be > 0. Lowering a limit below current spend is allowed — it
// bounds NEW work, never aborts in-flight work (billing ADR).
func (s *Server) patchGuardrail(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var in struct {
		DailyLimitUSD   *float64 `json:"daily_limit_usd"`
		MonthlyLimitUSD *float64 `json:"monthly_limit_usd"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	if in.DailyLimitUSD == nil && in.MonthlyLimitUSD == nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR",
			"at least one of daily_limit_usd / monthly_limit_usd is required")
		return
	}
	if (in.DailyLimitUSD != nil && *in.DailyLimitUSD <= 0) ||
		(in.MonthlyLimitUSD != nil && *in.MonthlyLimitUSD <= 0) {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "limits must be > 0")
		return
	}
	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_GUARDRAIL_FAILED", "failed to start tx")
		return
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err := tx.Exec(ctx, `
INSERT INTO spend_guardrails(owner_user_id, daily_limit_usd, monthly_limit_usd)
VALUES ($1,$2,$3) ON CONFLICT (owner_user_id) DO NOTHING`,
		userID, s.cfg.GuardrailDefaultDailyUSD, s.cfg.GuardrailDefaultMonthlyUSD); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_GUARDRAIL_FAILED", "failed to seed guardrail")
		return
	}
	// COALESCE: a nil pointer marshals to SQL NULL → the column keeps its
	// value, so only the supplied limit(s) change.
	if _, err := tx.Exec(ctx, `
UPDATE spend_guardrails SET
  daily_limit_usd   = COALESCE($2, daily_limit_usd),
  monthly_limit_usd = COALESCE($3, monthly_limit_usd),
  updated_at = now()
WHERE owner_user_id = $1`, userID, in.DailyLimitUSD, in.MonthlyLimitUSD); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_GUARDRAIL_FAILED", "failed to update limits")
		return
	}
	var dLimit, mLimit, dSpent, mSpent, reserved float64
	if err := tx.QueryRow(ctx, guardrailReadSQL, userID).
		Scan(&dLimit, &mLimit, &dSpent, &mSpent, &reserved); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_GUARDRAIL_FAILED", "failed to re-read guardrail")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_GUARDRAIL_FAILED", "failed to commit")
		return
	}
	writeGuardrailJSON(w, dLimit, mLimit, dSpent, mSpent, reserved)
}

// getPlatformBalance — GET /v1/model-billing/platform-balance. The authed
// user's Subsystem-B free tier + credits. No row yet → config free tier.
func (s *Server) getPlatformBalance(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var allowance, used, credits, reserved float64
	err := s.pool.QueryRow(r.Context(), platformReadSQL, userID).
		Scan(&allowance, &used, &credits, &reserved)
	if errors.Is(err, pgx.ErrNoRows) {
		allowance = s.cfg.PlatformFreeTierUSD
		used, credits, reserved = 0, 0, 0
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_GUARDRAIL_FAILED", "failed to read platform balance")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"free_tier_allowance_usd": allowance,
		"free_tier_used_usd":      used,
		"free_tier_remaining_usd": allowance - used,
		"credits_balance_usd":     credits,
		"reserved_usd":            reserved,
	})
}
