// Package canary implements the breaking-migration safety gate.
//
// Per L1.D §2 acceptance criteria:
//   "Breaking migration on canary reality → fails CI gate if canary failed"
//
// For migrations with `breaking: true` in contracts/migrations/manifest.yaml,
// the orchestrator MUST:
//   1. Pick ONE canary reality (lowest-numbered active reality by default,
//      configurable via CanarySelector).
//   2. Apply the migration to that reality via the runner.
//   3. WAIT for verification — caller must call Verify() to mark the canary
//      as cleared (post-apply tests passed). Until then, fan-out is blocked.
//   4. Only after verification, dispatch the remaining jobs.
//   5. If the canary fails OR verification times out → ABORT fan-out and
//      record migration_aborted in reality_migration_audit for every
//      not-yet-attempted reality.
//
// Non-breaking migrations bypass the canary entirely (they fan out
// directly through the runner under the same concurrency cap).
//
// Q-L1D-1 V1: no auto-rollback. A failed canary halts; SRE follows
// runbooks/migration/persistent_failure.md.
package canary

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"time"
)

// Dispatcher is the minimal runner contract canary needs. Matches
// runner.Runner.Run shape so the live wiring is trivial.
type Dispatcher interface {
	Run(ctx context.Context, jobs []Job) []Result
}

// Job mirrors runner.Job (re-declared to avoid the import cycle between
// canary and runner; the migrate cmd binds them together).
type Job struct {
	RealityID   string
	MigrationID string
	RunID       string
}

// Result mirrors runner.Result (subset — canary only inspects Succeeded).
type Result struct {
	Job        Job
	Succeeded  bool
	Attempts   int
	FinalError error
}

// AbortAuditor lets canary record migration_aborted events for the
// remaining realities after a canary failure.
type AbortAuditor interface {
	RecordAbort(ctx context.Context, realityID, migrationID, runID, reason string) error
}

// CanarySelector picks which reality goes first. Default: lowest sorted
// reality_id. Tests inject a deterministic selector.
type CanarySelector interface {
	Pick(realities []string) (string, error)
}

// LexicographicSelector picks the lexicographically smallest reality_id.
// Deterministic, no infra dependency — works for unit + integration tests.
type LexicographicSelector struct{}

// Pick returns the smallest by sort.Strings.
func (LexicographicSelector) Pick(realities []string) (string, error) {
	if len(realities) == 0 {
		return "", fmt.Errorf("canary: empty reality list")
	}
	sorted := append([]string(nil), realities...)
	sort.Strings(sorted)
	return sorted[0], nil
}

// VerificationGate is the synchronous wait for "canary succeeded AND
// post-apply verification passed". The orchestrator's caller must
// invoke Pass() (or Fail()) after running its verification suite.
// Default timeout = 5min; configurable.
type VerificationGate struct {
	ch chan verdict
}

type verdict struct {
	ok     bool
	reason string
}

// NewVerificationGate returns a fresh gate.
func NewVerificationGate() *VerificationGate {
	return &VerificationGate{ch: make(chan verdict, 1)}
}

// Pass signals the gate the canary verification succeeded.
func (g *VerificationGate) Pass() {
	select {
	case g.ch <- verdict{ok: true}:
	default:
	}
}

// Fail signals the gate the verification failed (caller-supplied reason).
func (g *VerificationGate) Fail(reason string) {
	select {
	case g.ch <- verdict{ok: false, reason: reason}:
	default:
	}
}

// wait blocks until Pass/Fail/ctx-done/timeout.
func (g *VerificationGate) wait(ctx context.Context, timeout time.Duration) (bool, string) {
	t := time.NewTimer(timeout)
	defer t.Stop()
	select {
	case v := <-g.ch:
		return v.ok, v.reason
	case <-t.C:
		return false, "verification_timeout"
	case <-ctx.Done():
		return false, "context_cancelled"
	}
}

// Config configures the canary orchestrator.
type Config struct {
	Dispatcher        Dispatcher
	Selector          CanarySelector
	Aborter           AbortAuditor
	VerificationGate  *VerificationGate
	VerificationDelay time.Duration // max wait for verification verdict
}

func (c *Config) validate() error {
	if c == nil {
		return errors.New("canary: nil config")
	}
	if c.Dispatcher == nil {
		return errors.New("canary: Dispatcher nil")
	}
	if c.Aborter == nil {
		return errors.New("canary: Aborter nil")
	}
	if c.Selector == nil {
		c.Selector = LexicographicSelector{}
	}
	if c.VerificationGate == nil {
		c.VerificationGate = NewVerificationGate()
	}
	if c.VerificationDelay <= 0 {
		c.VerificationDelay = 5 * time.Minute
	}
	return nil
}

// CanaryOutcome describes what happened.
type CanaryOutcome struct {
	CanaryReality string
	CanaryResult  Result
	Verified      bool
	FanoutResults []Result
	Aborted       bool
	AbortReason   string
}

// Orchestrator drives a breaking-migration safely through canary +
// verification + fan-out.
type Orchestrator struct {
	cfg *Config
}

// New constructs an Orchestrator.
func New(cfg *Config) (*Orchestrator, error) {
	if err := cfg.validate(); err != nil {
		return nil, err
	}
	return &Orchestrator{cfg: cfg}, nil
}

// Run executes a BREAKING migration. realities = all realities to migrate
// (including the canary). migrationID is the manifest entry's id.
func (o *Orchestrator) Run(ctx context.Context, realities []string, migrationID string) (*CanaryOutcome, error) {
	if len(realities) == 0 {
		return nil, errors.New("canary: empty realities list")
	}

	canary, err := o.cfg.Selector.Pick(realities)
	if err != nil {
		return nil, fmt.Errorf("canary: selector pick: %w", err)
	}

	outcome := &CanaryOutcome{CanaryReality: canary}

	// Phase 1 — apply migration to canary reality.
	canaryJob := Job{RealityID: canary, MigrationID: migrationID, RunID: "canary-" + migrationID}
	canaryResults := o.cfg.Dispatcher.Run(ctx, []Job{canaryJob})
	if len(canaryResults) != 1 {
		return nil, fmt.Errorf("canary: dispatcher returned %d results, expected 1", len(canaryResults))
	}
	outcome.CanaryResult = canaryResults[0]

	if !outcome.CanaryResult.Succeeded {
		outcome.Aborted = true
		outcome.AbortReason = "canary_apply_failed"
		o.recordAbortFor(ctx, exclude(realities, canary), migrationID, outcome.AbortReason)
		return outcome, nil
	}

	// Phase 2 — WAIT (hard gate) for verification. This MUST block until
	// the verification suite signals Pass or Fail (or timeout). If the
	// orchestrator returned without waiting, we'd be exactly the "async
	// fire-and-forget" anti-pattern called out in the brief.
	ok, reason := o.cfg.VerificationGate.wait(ctx, o.cfg.VerificationDelay)
	if !ok {
		outcome.Aborted = true
		outcome.AbortReason = "canary_verification_" + reason
		o.recordAbortFor(ctx, exclude(realities, canary), migrationID, outcome.AbortReason)
		return outcome, nil
	}
	outcome.Verified = true

	// Phase 3 — fan out to the rest.
	remaining := exclude(realities, canary)
	if len(remaining) == 0 {
		// only-1-reality cohort; canary IS the entire fan-out.
		return outcome, nil
	}
	jobs := make([]Job, 0, len(remaining))
	for _, r := range remaining {
		jobs = append(jobs, Job{RealityID: r, MigrationID: migrationID, RunID: "fanout-" + migrationID + "-" + r})
	}
	outcome.FanoutResults = o.cfg.Dispatcher.Run(ctx, jobs)
	return outcome, nil
}

func (o *Orchestrator) recordAbortFor(ctx context.Context, realities []string, migrationID, reason string) {
	for _, r := range realities {
		_ = o.cfg.Aborter.RecordAbort(ctx, r, migrationID, "abort-"+migrationID+"-"+r, reason)
	}
}

func exclude(all []string, dropped string) []string {
	out := make([]string, 0, len(all))
	for _, r := range all {
		if r != dropped {
			out = append(out, r)
		}
	}
	return out
}
