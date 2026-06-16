// Package controller wires the canary state machine to its external
// dependencies: the deploy_audit store (read current stage + history; write
// advance / abort), the cohort-scoped SLI source, the rollout executor (the
// thing that actually shifts traffic — GitHub Actions / deploy tooling), and
// the pager.
//
// Every external dependency is an interface so the safety-critical Tick logic
// is unit-tested with fakes and there is NO live CI / DB / SLI source needed.
// This is the L7.K.4 service brain; cmd/canary-controller drives it on a timer.
package controller

import (
	"context"
	"fmt"
	"time"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
)

// DeployRecord is the projection of a deploy_audit row the controller drives.
type DeployRecord struct {
	DeployID     string
	Class        string // patch|minor|major|emergency
	Stage        canary.Stage
	StageEntered time.Time
	BaselineBurn float64
	RolledBack   bool
}

// DeployStore reads + updates deploy_audit. The prod impl goes through
// contracts/meta MetaWrite() (deploy_audit canary_history is UPDATE-allowed for
// app_canary_role per migration 023). Tests use an in-memory fake.
type DeployStore interface {
	// ActiveCanary returns the single in-progress major deploy, or ok=false.
	ActiveCanary(ctx context.Context) (rec DeployRecord, ok bool, err error)
	// AdvanceStage persists a stage advance + appends a canary_history entry.
	AdvanceStage(ctx context.Context, deployID string, to canary.Stage, at time.Time, reason string) error
	// MarkRolledBack sets rolled_back=true + rollback_reason + completed_at.
	MarkRolledBack(ctx context.Context, deployID string, reason string, at time.Time) error
	// MarkComplete sets completed_at on a finished (100%) rollout.
	MarkComplete(ctx context.Context, deployID string, at time.Time) error
}

// SLISource returns the cohort-scoped SLI burn (and stage-0 error rate) for a
// deploy at its current stage. The prod impl queries Prometheus
// (lw_canary_sli_cohort{stage,service}); tests inject readings.
type SLISource interface {
	// Observe returns the burn rate + error rate for the deploy's live cohorts.
	Observe(ctx context.Context, deployID string, stage canary.Stage) (canary.Observation, error)
}

// RolloutExecutor performs the actual traffic shift / rollback. The prod impl
// triggers the canary.yml GitHub Actions workflow (repository_dispatch) or the
// deploy tooling; tests record calls. Kept behind an interface so the
// controller never embeds CI specifics.
type RolloutExecutor interface {
	// Promote shifts traffic so the given stage's cohorts run the new code.
	Promote(ctx context.Context, deployID string, to canary.Stage) error
	// Rollback reverts ALL cohorts to the prior version.
	Rollback(ctx context.Context, deployID string, reason string) error
}

// Pager pages SRE on an auto-abort (§12AH.4 "automatic rollback + SRE paged").
type Pager interface {
	PageSRE(ctx context.Context, deployID, reason string) error
}

// Clock returns "now"; injectable for tests.
type Clock func() time.Time

// Controller orchestrates one canary tick.
type Controller struct {
	store DeployStore
	sli   SLISource
	exec  RolloutExecutor
	pager Pager
	now   Clock
}

// New builds a Controller. Fails closed on any nil dependency.
func New(store DeployStore, sli SLISource, exec RolloutExecutor, pager Pager, now Clock) (*Controller, error) {
	if store == nil || sli == nil || exec == nil || pager == nil {
		return nil, fmt.Errorf("controller: all dependencies required (store/sli/exec/pager)")
	}
	if now == nil {
		now = time.Now
	}
	return &Controller{store: store, sli: sli, exec: exec, pager: pager, now: now}, nil
}

// TickResult reports what the tick did (for logs + metrics + tests).
type TickResult struct {
	DeployID string
	Action   canary.Action
	Reason   string
	Stage    canary.Stage // resulting stage (after advance) or current
}

// Tick runs one control-loop iteration: find the active canary, observe its
// SLI, decide, and execute. A no-op (no active canary) returns ok=false.
//
// On ActionAbort it rolls back FIRST, then marks the audit row + pages SRE.
// Rollback execution failure is surfaced (the audit row records the attempt)
// so the run-loop retries / escalates rather than silently dropping a bad
// deploy on the floor.
func (c *Controller) Tick(ctx context.Context) (TickResult, bool, error) {
	rec, ok, err := c.store.ActiveCanary(ctx)
	if err != nil {
		return TickResult{}, false, fmt.Errorf("controller: read active canary: %w", err)
	}
	if !ok {
		return TickResult{}, false, nil
	}

	obs, err := c.sli.Observe(ctx, rec.DeployID, rec.Stage)
	if err != nil {
		return TickResult{}, true, fmt.Errorf("controller: observe SLI for %s: %w", rec.DeployID, err)
	}

	st := canary.State{
		DeployID:       rec.DeployID,
		Stage:          rec.Stage,
		StageEnteredAt: rec.StageEntered,
		BaselineBurn:   rec.BaselineBurn,
		Aborted:        rec.RolledBack,
	}
	d := canary.Decide(st, obs)
	res := TickResult{DeployID: rec.DeployID, Action: d.Action, Reason: d.Reason, Stage: rec.Stage}

	switch d.Action {
	case canary.ActionHold:
		return res, true, nil

	case canary.ActionAdvance:
		if err := c.exec.Promote(ctx, rec.DeployID, d.NextStage); err != nil {
			return res, true, fmt.Errorf("controller: promote %s→stage %d: %w", rec.DeployID, d.NextStage, err)
		}
		now := c.now()
		if err := c.store.AdvanceStage(ctx, rec.DeployID, d.NextStage, now, d.Reason); err != nil {
			return res, true, fmt.Errorf("controller: persist advance: %w", err)
		}
		res.Stage = d.NextStage
		return res, true, nil

	case canary.ActionAbort:
		now := c.now()
		// Rollback first — restoring service is the priority.
		rbErr := c.exec.Rollback(ctx, rec.DeployID, d.Reason)
		if mkErr := c.store.MarkRolledBack(ctx, rec.DeployID, d.Reason, now); mkErr != nil && rbErr == nil {
			rbErr = mkErr
		}
		// Page SRE regardless of rollback outcome (§12AH.4).
		if pErr := c.pager.PageSRE(ctx, rec.DeployID, d.Reason); pErr != nil && rbErr == nil {
			rbErr = pErr
		}
		if rbErr != nil {
			return res, true, fmt.Errorf("controller: abort handling for %s: %w", rec.DeployID, rbErr)
		}
		return res, true, nil

	case canary.ActionComplete:
		if err := c.store.MarkComplete(ctx, rec.DeployID, c.now()); err != nil {
			return res, true, fmt.Errorf("controller: mark complete: %w", err)
		}
		return res, true, nil

	default:
		return res, true, fmt.Errorf("controller: unhandled action %s", d.Action)
	}
}
