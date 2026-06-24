// Package canary implements the SR05 §12AH.4 canary rollout state machine:
// the 5 stages (0=internal, 1=1%, 2=10%, 3=50%, 4=100%), their monitor windows
// (10min/30min/2h/4h), and the advance / auto-abort decision based on cohort
// SLI burn vs baseline.
//
// The state machine is PURE: Decide() takes the current state + a clock reading
// + the observed cohort SLI burn and returns the next action. No I/O, no
// globals, no background goroutine — the controller's run-loop (cmd/) calls
// Decide() on a tick and persists the result to deploy_audit through the
// DeployStore interface. This keeps the safety-critical logic unit-testable
// without a live SLI source or a live DB.
package canary

import (
	"fmt"
	"time"
)

// Stage is a canary rollout stage index per §12AH.4.
type Stage int

const (
	StageInternal Stage = 0 // LoreWeave dev accounts only
	Stage1pct     Stage = 1 // random 1% realities (weighted non-premium)
	Stage10pct    Stage = 2 // next 10% cohort
	Stage50pct    Stage = 3 // next 40%
	StageFull     Stage = 4 // remaining 100%
)

// BaselineBurnMultiplier is the auto-abort threshold from §12AH.4: a stage
// aborts when cohort SLI burn exceeds baseline × this multiplier.
const BaselineBurnMultiplier = 2.0

// stageSpec describes one stage's cohort window + monitor window + threshold.
type stageSpec struct {
	Stage          Stage
	MonitorWindow  time.Duration
	CohortPctStart int // inclusive lower cohort bound (0..99)
	CohortPctEnd   int // inclusive upper cohort bound (0..99); StageFull = all
	// ZeroErrorRate marks Stage 0 where the threshold is "error rate == 0"
	// rather than a burn multiplier (§12AH.4 stage-0 column).
	ZeroErrorRate bool
}

// stageTable is the §12AH.4 canary table. Cohort bounds map the 1/10/50/100%
// progression onto the 0..99 deploy_cohort space (cohorts rolled in order):
//
//	stage 0 internal — no realities (dev accounts only); window 10m
//	stage 1 1%       — cohorts [0,0]                    ; window 30m
//	stage 2 10%      — cohorts [1,10]                   ; window 2h
//	stage 3 50%      — cohorts [11,50]                  ; window 4h
//	stage 4 100%     — cohorts [51,99]                  ; no window
var stageTable = []stageSpec{
	{Stage: StageInternal, MonitorWindow: 10 * time.Minute, CohortPctStart: -1, CohortPctEnd: -1, ZeroErrorRate: true},
	{Stage: Stage1pct, MonitorWindow: 30 * time.Minute, CohortPctStart: 0, CohortPctEnd: 0},
	{Stage: Stage10pct, MonitorWindow: 2 * time.Hour, CohortPctStart: 1, CohortPctEnd: 10},
	{Stage: Stage50pct, MonitorWindow: 4 * time.Hour, CohortPctStart: 11, CohortPctEnd: 50},
	{Stage: StageFull, MonitorWindow: 0, CohortPctStart: 51, CohortPctEnd: 99},
}

// SpecFor returns the stage spec for s.
func SpecFor(s Stage) (stageSpec, bool) {
	for _, sp := range stageTable {
		if sp.Stage == s {
			return sp, true
		}
	}
	return stageSpec{}, false
}

// MonitorWindow returns the monitor window for a stage (0 for StageFull).
func MonitorWindow(s Stage) time.Duration {
	if sp, ok := SpecFor(s); ok {
		return sp.MonitorWindow
	}
	return 0
}

// State is the live canary state for one deploy.
type State struct {
	DeployID       string
	Stage          Stage
	StageEnteredAt time.Time
	BaselineBurn   float64 // the pre-deploy baseline cohort SLI burn rate
	Aborted        bool
}

// Action is the outcome of a Decide() call.
type Action int

const (
	// ActionHold — monitor window not elapsed and SLI healthy; do nothing.
	ActionHold Action = iota
	// ActionAdvance — window elapsed + SLI healthy; advance to next stage.
	ActionAdvance
	// ActionAbort — SLI burn breached threshold; abort + rollback + page SRE.
	ActionAbort
	// ActionComplete — already at StageFull; deploy done.
	ActionComplete
)

func (a Action) String() string {
	switch a {
	case ActionHold:
		return "hold"
	case ActionAdvance:
		return "advance"
	case ActionAbort:
		return "abort"
	case ActionComplete:
		return "complete"
	default:
		return "unknown"
	}
}

// Observation is one SLI reading for the current canary cohort.
type Observation struct {
	// CohortBurn is the observed cohort SLI burn rate (same units as baseline).
	CohortBurn float64
	// ErrorRate is the stage-0 internal error rate (must be 0 to advance).
	ErrorRate float64
	// Now is the clock reading for this decision (injected; never time.Now()).
	Now time.Time
}

// Decision bundles the action with the reason (for audit + paging copy).
type Decision struct {
	Action Action
	Reason string
	// NextStage is set when Action == ActionAdvance.
	NextStage Stage
}

// Decide evaluates the canary state machine for the current state + observation.
//
// Auto-abort precedence: an SLI-burn breach aborts REGARDLESS of whether the
// monitor window has elapsed (a stage that goes bad in minute 1 must not wait
// out its window). §12AH.4 "auto-abort on cohort SLI burn > baseline × 2".
func Decide(st State, obs Observation) Decision {
	if st.Aborted {
		return Decision{Action: ActionAbort, Reason: "deploy already aborted"}
	}
	if st.Stage >= StageFull {
		return Decision{Action: ActionComplete, Reason: "canary at 100% — rollout complete"}
	}

	sp, ok := SpecFor(st.Stage)
	if !ok {
		// Unknown stage — fail safe by aborting rather than silently advancing.
		return Decision{Action: ActionAbort, Reason: fmt.Sprintf("unknown canary stage %d — failing safe", st.Stage)}
	}

	// 1. Abort check (precedes window — applies the moment SLI goes bad).
	if sp.ZeroErrorRate {
		if obs.ErrorRate > 0 {
			return Decision{Action: ActionAbort, Reason: fmt.Sprintf("stage 0 internal error rate %.4f > 0 — aborting", obs.ErrorRate)}
		}
	} else {
		threshold := st.BaselineBurn * BaselineBurnMultiplier
		if obs.CohortBurn > threshold {
			return Decision{
				Action: ActionAbort,
				Reason: fmt.Sprintf("cohort SLI burn %.4f > baseline %.4f × %.1f = %.4f — auto-abort + rollback",
					obs.CohortBurn, st.BaselineBurn, BaselineBurnMultiplier, threshold),
			}
		}
	}

	// 2. Window check — hold until the monitor window has fully elapsed.
	elapsed := obs.Now.Sub(st.StageEnteredAt)
	if elapsed < sp.MonitorWindow {
		return Decision{
			Action: ActionHold,
			Reason: fmt.Sprintf("stage %d healthy; %s of %s monitor window elapsed", st.Stage, elapsed.Round(time.Second), sp.MonitorWindow),
		}
	}

	// 3. Advance — window elapsed + SLI healthy.
	next := st.Stage + 1
	return Decision{
		Action:    ActionAdvance,
		NextStage: next,
		Reason:    fmt.Sprintf("stage %d passed (window %s elapsed, SLI healthy) — advancing to stage %d", st.Stage, sp.MonitorWindow, next),
	}
}

// CohortInStage reports whether a reality with the given deploy_cohort (0..99)
// is included at the given stage. Cohorts roll in order 0→99; a stage includes
// its own band plus all lower stages' bands (a deploy at stage 3 has stages
// 1+2+3 cohorts live). Stage 0 (internal) includes no realities.
func CohortInStage(cohort int, stage Stage) bool {
	if cohort < 0 || cohort > 99 {
		return false
	}
	for _, sp := range stageTable {
		if sp.Stage > stage {
			continue
		}
		if sp.CohortPctStart < 0 { // internal stage: no realities
			continue
		}
		if cohort >= sp.CohortPctStart && cohort <= sp.CohortPctEnd {
			return true
		}
	}
	return false
}
