package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// B1 (D-LANE-BUDGET-ENFORCE) — the per-lane spend report: aggregates usage_logs by lane and JOINs the
// per-user budget (making user_lane_budgets READ). Owner-scoped; assistant-vs-interactive visibility.
func TestUsageByLane_AggregatesAndJoinsBudget_DB(t *testing.T) {
	pool := openGuardrailTestDB(t)
	ctx := context.Background()
	srv := newGuardrailServer(t, pool)
	owner, other := uuid.New(), uuid.New()
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM usage_logs WHERE owner_user_id = ANY($1)`, []uuid.UUID{owner, other})
		_, _ = pool.Exec(ctx, `DELETE FROM user_lane_budgets WHERE owner_user_id=$1`, owner)
	})

	seed := func(o uuid.UUID, lane string, cost float64) {
		if _, err := pool.Exec(ctx, `
INSERT INTO usage_logs (request_id, owner_user_id, provider_kind, model_source, model_ref,
  total_cost_usd, billing_decision, request_status, lane)
VALUES ($1,$2,'openai','user_model',$3,$4,'recorded','success',$5)`,
			uuid.New(), o, uuid.New(), cost, lane); err != nil {
			t.Fatalf("seed usage_logs: %v", err)
		}
	}
	// owner: $3 assistant (2 rows) + $2 interactive; a DIFFERENT user's assistant spend must NOT leak.
	seed(owner, "assistant", 1.0)
	seed(owner, "assistant", 2.0)
	seed(owner, "interactive", 2.0)
	seed(other, "assistant", 99.0)
	// a FAILED row carries no real incurred cost and must NOT inflate the lane (cold-review MED).
	if _, err := pool.Exec(ctx, `
INSERT INTO usage_logs (request_id, owner_user_id, provider_kind, model_source, model_ref,
  total_cost_usd, billing_decision, request_status, lane)
VALUES ($1,$2,'openai','user_model',$3,50.0,'rejected','provider_error','assistant')`,
		uuid.New(), owner, uuid.New()); err != nil {
		t.Fatalf("seed failed row: %v", err)
	}
	// budget: assistant capped at $5 (interactive left unlimited).
	if _, err := pool.Exec(ctx,
		`INSERT INTO user_lane_budgets (owner_user_id, lane_code, monthly_limit_usd) VALUES ($1,'assistant',5.0)`,
		owner); err != nil {
		t.Fatalf("seed budget: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/internal/billing/usage/by-lane?owner_user_id="+owner.String(), nil)
	rr := httptest.NewRecorder()
	srv.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("by-lane = %d, body=%s", rr.Code, rr.Body.String())
	}
	var body struct {
		Lanes []struct {
			LaneCode     string   `json:"lane_code"`
			SpentUSD     float64  `json:"spent_usd"`
			BudgetUSD    float64  `json:"budget_usd"`
			RemainingUSD *float64 `json:"remaining_usd"`
			OverBudget   bool     `json:"over_budget"`
		} `json:"lanes"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode: %v (%s)", err, rr.Body.String())
	}
	byLane := map[string]struct {
		spent, budget float64
		remaining     *float64
		over          bool
	}{}
	for _, l := range body.Lanes {
		byLane[l.LaneCode] = struct {
			spent, budget float64
			remaining     *float64
			over          bool
		}{l.SpentUSD, l.BudgetUSD, l.RemainingUSD, l.OverBudget}
	}
	a := byLane["assistant"]
	if a.spent != 3.0 || a.budget != 5.0 || a.remaining == nil || *a.remaining != 2.0 || a.over {
		t.Fatalf("assistant lane wrong: spent=%v budget=%v remaining=%v over=%v (want 3/5/2/false)", a.spent, a.budget, a.remaining, a.over)
	}
	in := byLane["interactive"]
	if in.spent != 2.0 || in.budget != 0 || in.remaining != nil {
		t.Fatalf("interactive lane wrong: spent=%v budget=%v remaining=%v (want 2/0/nil-unlimited)", in.spent, in.budget, in.remaining)
	}

	// over-budget: push assistant past its $5 cap → over_budget true, remaining negative.
	seed(owner, "assistant", 4.0) // now $7 > $5
	rr2 := httptest.NewRecorder()
	srv.Router().ServeHTTP(rr2, httptest.NewRequest(http.MethodGet, "/internal/billing/usage/by-lane?owner_user_id="+owner.String(), nil))
	_ = json.Unmarshal(rr2.Body.Bytes(), &body)
	for _, l := range body.Lanes {
		if l.LaneCode == "assistant" {
			if !l.OverBudget || l.SpentUSD != 7.0 {
				t.Fatalf("assistant over-budget not reported: spent=%v over=%v", l.SpentUSD, l.OverBudget)
			}
		}
	}
}
