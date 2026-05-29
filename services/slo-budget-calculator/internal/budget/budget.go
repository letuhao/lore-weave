// Package budget computes the error budget + burn rate for a (sli, tier)
// pair from a stream of Prometheus SLI ratio samples.
//
// SR1 §12AD.4 contract:
//
//	error_budget    = (1 - SLO_target) × events_in_window
//	budget_consumed = events_failed_in_window
//	burn_rate       = budget_consumed / fraction_of_window_elapsed
//
// The 4-tier policy (< 0.50, 0.50–0.75, 0.75–0.90, ≥ 0.90) maps to PR
// labels in slo_targets.yaml::burn_rate_response.
//
// All functions in this package are PURE — no IO, no globals, no
// clock — so tests can drive them with synthesized Prom data and assert
// exact values. The HTTP server in cmd/slo-budget-calculator wires real
// Prom queries to these calculators.
package budget

import (
	"errors"
	"fmt"
	"sort"
	"time"
)

// Sample is one observation of the SLI ratio at a point in time.
//
// Ratio is the success-fraction (e.g., successful_sessions / total_sessions)
// in the [0, 1] range. NumEvents is the denominator (total events in the
// 5-min bucket) — used to weight the budget computation so an empty bucket
// can't pollute the burn rate.
type Sample struct {
	At        time.Time
	Ratio     float64
	NumEvents float64
}

// ErrInvalidTarget is returned when the SLO target is out of (0, 1].
var ErrInvalidTarget = errors.New("budget: SLO target must be in (0, 1]")

// ErrEmptyWindow is returned when no samples land in the requested window.
var ErrEmptyWindow = errors.New("budget: no samples in window")

// Window is the rolling SLO window — 7d for auth, 30d for everything else.
type Window struct {
	Duration time.Duration
}

// Compute returns the burn rate + remaining budget given:
//   - target  — SLO ratio (e.g., 0.999 for 99.9%)
//   - samples — every 5-min ratio observation in the window
//   - now     — the wall clock; samples older than now-window.Duration are dropped
//
// Determinism: same inputs → same outputs. No clock reads beyond `now`.
//
// Return: burn_rate is the dimensionless ratio
//
//	(budget_consumed / fraction_of_window_elapsed)
//
// per SR1 §12AD.4. budget_consumed_pct is the fraction of the period's
// allowable failures already used.
func Compute(target float64, samples []Sample, w Window, now time.Time) (Result, error) {
	if target <= 0 || target > 1 {
		return Result{}, ErrInvalidTarget
	}
	if w.Duration <= 0 {
		return Result{}, errors.New("budget: window duration must be > 0")
	}
	windowStart := now.Add(-w.Duration)

	// Filter to in-window samples. Sort by time so the elapsed-fraction
	// calculation is deterministic for partially-warm windows.
	inWin := make([]Sample, 0, len(samples))
	for _, s := range samples {
		if !s.At.Before(windowStart) && !s.At.After(now) {
			inWin = append(inWin, s)
		}
	}
	if len(inWin) == 0 {
		return Result{}, ErrEmptyWindow
	}
	sort.Slice(inWin, func(i, j int) bool { return inWin[i].At.Before(inWin[j].At) })

	// Event-weighted totals. Each bucket contributes:
	//   total_events_i   = NumEvents_i
	//   failed_events_i  = (1 - Ratio_i) × NumEvents_i
	var totalEvents, failedEvents float64
	for _, s := range inWin {
		if s.NumEvents < 0 {
			return Result{}, fmt.Errorf("budget: sample at %s has negative num_events", s.At)
		}
		if s.Ratio < 0 || s.Ratio > 1 {
			return Result{}, fmt.Errorf(
				"budget: sample at %s has ratio %v out of [0,1]",
				s.At, s.Ratio,
			)
		}
		totalEvents += s.NumEvents
		failedEvents += (1 - s.Ratio) * s.NumEvents
	}

	// Error budget = (1 - target) × total_events
	errorBudget := (1 - target) * totalEvents
	if errorBudget <= 0 {
		// Defensive: even at target=1 (no failures allowed) we keep a
		// minimum so burn-rate math doesn't divide by zero. Caller can
		// detect by checking remaining_budget == total_events.
		return Result{
			TargetRatio:       target,
			ErrorBudgetEvents: 0,
			ConsumedEvents:    failedEvents,
			RemainingEvents:   -failedEvents,
			BudgetConsumedPct: 0,
			BurnRate:          0,
			SampleCount:       len(inWin),
		}, nil
	}

	budgetConsumedPct := failedEvents / errorBudget
	// Elapsed fraction of the window. inWin[0].At is the oldest sample;
	// fraction_elapsed = (now - inWin[0]) / window. For a freshly-booted
	// system at t=0 of the window the fraction is tiny → spike-amplifies
	// the burn rate so the alert fires early.
	elapsed := now.Sub(inWin[0].At)
	if elapsed <= 0 {
		elapsed = 1 * time.Second // floor — never divide by zero
	}
	fractionElapsed := float64(elapsed) / float64(w.Duration)
	if fractionElapsed > 1 {
		fractionElapsed = 1
	}
	if fractionElapsed <= 0 {
		fractionElapsed = 1e-9
	}
	burnRate := budgetConsumedPct / fractionElapsed

	return Result{
		TargetRatio:       target,
		ErrorBudgetEvents: errorBudget,
		ConsumedEvents:    failedEvents,
		RemainingEvents:   errorBudget - failedEvents,
		BudgetConsumedPct: budgetConsumedPct,
		BurnRate:          burnRate,
		SampleCount:       len(inWin),
	}, nil
}

// Result is the full burn-rate computation output for a (sli, tier) pair.
type Result struct {
	// TargetRatio echoes the SLO target (for caller convenience).
	TargetRatio float64

	// ErrorBudgetEvents is the maximum events that may fail in this window.
	ErrorBudgetEvents float64

	// ConsumedEvents is the count already failed.
	ConsumedEvents float64

	// RemainingEvents = ErrorBudgetEvents - ConsumedEvents. May go negative
	// if SLO has already been breached.
	RemainingEvents float64

	// BudgetConsumedPct is ConsumedEvents / ErrorBudgetEvents.
	BudgetConsumedPct float64

	// BurnRate is the dimensionless ratio used by the 4-tier policy.
	// >= 0.90 → feature freeze; 0.75-0.90 → review label; 0.50-0.75 → warn.
	BurnRate float64

	// SampleCount is the number of in-window samples that contributed.
	// Tests use this to assert windowing logic.
	SampleCount int
}

// PolicyTier maps the BurnRate to one of the 4-tier responses.
// Returns the highest matching threshold (so 0.95 → "freeze", not "warn").
func (r Result) PolicyTier() string {
	switch {
	case r.BurnRate >= 1.00:
		return "slo-breach-postmortem"
	case r.BurnRate >= 0.90:
		return "approve-reliability-override"
	case r.BurnRate >= 0.75:
		return "reliability-review-required"
	case r.BurnRate >= 0.50:
		return "warn"
	default:
		return "normal"
	}
}
