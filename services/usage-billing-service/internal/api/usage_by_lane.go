package api

import (
	"net/http"
	"time"

	"github.com/google/uuid"
)

// getUsageByLane — GET /internal/billing/usage/by-lane?owner_user_id=&month=YYYY-MM
//
// B1 (D-LANE-BUDGET-ENFORCE) — the per-lane spend report. usage_logs.lane is populated + indexed (C6)
// but nothing AGGREGATES by lane, and user_lane_budgets was written-but-never-READ. This closes both:
// it sums each lane's COMMITTED spend for the month and JOINs the per-user per-lane budget, so a
// consumer can see assistant-vs-interactive spend and how close each lane is to its cap. Owner-scoped.
// (The pre-flight per-lane cap ENFORCEMENT at the reserve chokepoint is tracked separately — it needs
// the job `purpose` threaded through provider-registry, which isn't available at reserve today.)
func (s *Server) getUsageByLane(w http.ResponseWriter, r *http.Request) {
	owner, err := uuid.Parse(r.URL.Query().Get("owner_user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "owner_user_id required")
		return
	}
	// month = the first day of the reporting month (UTC). Default: the current month.
	monthStart := time.Now().UTC().Truncate(24 * time.Hour)
	monthStart = time.Date(monthStart.Year(), monthStart.Month(), 1, 0, 0, 0, 0, time.UTC)
	if m := r.URL.Query().Get("month"); m != "" {
		parsed, perr := time.Parse("2006-01", m)
		if perr != nil {
			writeError(w, http.StatusBadRequest, "GUARDRAIL_INVALID", "month must be YYYY-MM")
			return
		}
		monthStart = time.Date(parsed.Year(), parsed.Month(), 1, 0, 0, 0, 0, time.UTC)
	}
	// Bind BOTH month bounds as exact instants (cold-review LOW): `$2 + interval '1 month'` would be
	// evaluated in the DB session timezone and shift the upper edge off a non-UTC session.
	monthEnd := monthStart.AddDate(0, 1, 0)

	rows, err := s.pool.Query(r.Context(), `
SELECT sl.lane_code, sl.label,
       COALESCE(u.spent, 0)              AS spent_usd,
       COALESCE(b.monthly_limit_usd, 0)  AS budget_usd
FROM spend_lanes sl
LEFT JOIN (
  SELECT lane, SUM(total_cost_usd) AS spent
  FROM usage_logs
  WHERE owner_user_id = $1
    AND request_status = 'success'          -- cold-review MED: only ACTUAL incurred spend (mirrors the
                                            -- per-key rollup); a provider_error/rejected row carries no
                                            -- real cost and must not inflate a lane or trip over_budget.
    AND created_at >= $2 AND created_at < $3
  GROUP BY lane
) u ON u.lane = sl.lane_code
LEFT JOIN user_lane_budgets b ON b.owner_user_id = $1 AND b.lane_code = sl.lane_code
ORDER BY sl.sort_order, sl.lane_code`, owner, monthStart, monthEnd)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "failed to read lane usage")
		return
	}
	defer rows.Close()

	type laneReport struct {
		LaneCode     string   `json:"lane_code"`
		Label        string   `json:"label"`
		SpentUSD     float64  `json:"spent_usd"`
		BudgetUSD    float64  `json:"budget_usd"`      // 0 ⇒ unlimited for this lane
		RemainingUSD *float64 `json:"remaining_usd"`   // nil when unlimited
		OverBudget   bool     `json:"over_budget"`
	}
	out := []laneReport{}
	for rows.Next() {
		var lr laneReport
		if err := rows.Scan(&lr.LaneCode, &lr.Label, &lr.SpentUSD, &lr.BudgetUSD); err != nil {
			writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "scan failed")
			return
		}
		if lr.BudgetUSD > 0 {
			rem := lr.BudgetUSD - lr.SpentUSD
			lr.RemainingUSD = &rem
			lr.OverBudget = lr.SpentUSD > lr.BudgetUSD
		}
		out = append(out, lr)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GUARDRAIL_TX_FAILED", "row iteration failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"owner_user_id": owner.String(),
		"month":         monthStart.Format("2006-01"),
		"lanes":         out,
	})
}
