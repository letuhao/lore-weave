// Package runner is the concurrency-bounded migration dispatcher.
//
// Per L1.D §2 acceptance criteria:
//   - Concurrency-cap = 10 active runners (no thread starvation).
//   - Retry with exponential backoff: 3 attempts (initial + 2 retries),
//     base delay 100ms, capped at 30s.
//   - Persistent failure (all attempts exhausted) → records
//     reality_migration_audit.event_type='migration_failed' with
//     failure_detail containing the attempt log; alert fires via the
//     `reality_migration_audit_failures_partial` partial index.
//
// Design notes:
//   - The runner is purely an in-process scheduler; the actual SQL
//     application is delegated to the injected Applier interface so the
//     tests can inject a deterministic fake.
//   - All audit + state writes go through the injected MetaWriter
//     (which the live wiring binds to MetaWrite() — Q-L1B-3).
//   - Backoff timer is injected via the Sleeper interface so the test
//     suite doesn't actually wait 100ms × 2 × N retries.
package runner

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// DefaultConcurrency is the cap on active migration runners. Matches
// L1.D §2 acceptance criteria ("Concurrency=10 verified — no thread
// starvation").
const DefaultConcurrency = 10

// DefaultMaxAttempts = initial attempt + 2 retries = 3 total attempts
// before dead-letter.
const DefaultMaxAttempts = 3

// DefaultBaseBackoff is the initial backoff after the first failure.
const DefaultBaseBackoff = 100 * time.Millisecond

// DefaultMaxBackoff caps exponential backoff growth.
const DefaultMaxBackoff = 30 * time.Second

// Applier executes the SQL for a single (reality, migration) pair.
// Tests inject a deterministic fake that records calls.
type Applier interface {
	// Apply runs the migration's UP SQL against the per-reality DB.
	// Returns (false, transient-error) for retryable failures;
	// (false, permanent-error) for non-retryable.
	// Returns (true, nil) on success.
	//
	// The applier is responsible for its own idempotency — re-running
	// after a transient failure on the same (reality, migration) must
	// be safe.
	Apply(ctx context.Context, realityID, migrationID string) (succeeded bool, err error)
}

// Auditor records audit events (one per attempt — start, succeeded,
// failed). The live wiring binds this to contracts/meta.MetaWrite()
// against reality_migration_audit so each event lands a row with the
// audit + (for milestones) outbox event in the same TX.
type Auditor interface {
	RecordEvent(ctx context.Context, event AuditEvent) error
}

// StateWriter persists the FINAL state of a (reality, migration) pair
// in instance_schema_migrations. The live wiring binds this to
// MetaWrite() so audit + outbox land in the same TX.
type StateWriter interface {
	MarkApplied(ctx context.Context, realityID, migrationID string) error
	MarkFailed(ctx context.Context, realityID, migrationID, reason string) error
}

// Sleeper exists so tests can use a virtual clock.
type Sleeper interface {
	Sleep(ctx context.Context, d time.Duration)
}

// realSleeper is the production Sleeper backed by time.Sleep.
type realSleeper struct{}

func (realSleeper) Sleep(ctx context.Context, d time.Duration) {
	select {
	case <-ctx.Done():
	case <-time.After(d):
	}
}

// NewRealSleeper returns the default time.Sleep-backed sleeper.
func NewRealSleeper() Sleeper { return realSleeper{} }

// AuditEvent is one row destined for reality_migration_audit.
type AuditEvent struct {
	RealityID     string
	MigrationID   string
	RunID         string
	EventType     string // migration_started | migration_succeeded | migration_failed | migration_aborted
	AttemptNumber int
	FailureDetail map[string]any
}

// ErrTransient marks a retryable failure. Use errors.Is(err, ErrTransient).
var ErrTransient = errors.New("transient migration failure")

// Job is one (reality, migration) pair to apply.
type Job struct {
	RealityID   string
	MigrationID string
	RunID       string
}

// Result is the outcome of one Job.
type Result struct {
	Job         Job
	Succeeded   bool
	Attempts    int
	FinalError  error
	FinalReason string // populated only on failure
}

// Config configures Runner.
type Config struct {
	Concurrency int
	MaxAttempts int
	BaseBackoff time.Duration
	MaxBackoff  time.Duration

	Applier     Applier
	Auditor     Auditor
	StateWriter StateWriter
	Sleeper     Sleeper
}

// validate sets defaults + checks required collaborators.
func (c *Config) validate() error {
	if c == nil {
		return fmt.Errorf("runner: nil config")
	}
	if c.Applier == nil {
		return fmt.Errorf("runner: Applier nil")
	}
	if c.Auditor == nil {
		return fmt.Errorf("runner: Auditor nil")
	}
	if c.StateWriter == nil {
		return fmt.Errorf("runner: StateWriter nil")
	}
	if c.Concurrency <= 0 {
		c.Concurrency = DefaultConcurrency
	}
	if c.MaxAttempts <= 0 {
		c.MaxAttempts = DefaultMaxAttempts
	}
	if c.BaseBackoff <= 0 {
		c.BaseBackoff = DefaultBaseBackoff
	}
	if c.MaxBackoff <= 0 {
		c.MaxBackoff = DefaultMaxBackoff
	}
	if c.Sleeper == nil {
		c.Sleeper = realSleeper{}
	}
	return nil
}

// Runner dispatches jobs with bounded concurrency + retry.
type Runner struct {
	cfg *Config
}

// New constructs a Runner.
func New(cfg *Config) (*Runner, error) {
	if err := cfg.validate(); err != nil {
		return nil, err
	}
	return &Runner{cfg: cfg}, nil
}

// Concurrency returns the effective concurrency cap (after defaulting).
func (r *Runner) Concurrency() int { return r.cfg.Concurrency }

// MaxAttempts returns the effective per-job attempt limit.
func (r *Runner) MaxAttempts() int { return r.cfg.MaxAttempts }

// Run executes all jobs respecting the concurrency cap. Returns one
// Result per job (ordering NOT guaranteed). All jobs are attempted
// even if some fail.
//
// Concurrency mechanism: classic semaphore-channel of size Concurrency.
// We assert (in tests) that at most N goroutines call Applier.Apply
// concurrently — the Applier is what we inject a counter into.
func (r *Runner) Run(ctx context.Context, jobs []Job) []Result {
	results := make([]Result, len(jobs))
	if len(jobs) == 0 {
		return results
	}

	sem := make(chan struct{}, r.cfg.Concurrency)
	var wg sync.WaitGroup

	for i, j := range jobs {
		wg.Add(1)
		go func(idx int, job Job) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results[idx] = r.runOne(ctx, job)
		}(i, j)
	}
	wg.Wait()
	return results
}

// runOne is the per-job attempt loop with exponential backoff.
func (r *Runner) runOne(ctx context.Context, job Job) Result {
	// Always emit a migration_started audit row at the start of the run.
	_ = r.cfg.Auditor.RecordEvent(ctx, AuditEvent{
		RealityID:     job.RealityID,
		MigrationID:   job.MigrationID,
		RunID:         job.RunID,
		EventType:     "migration_started",
		AttemptNumber: 1,
	})

	res := Result{Job: job}
	var lastErr error
	for attempt := 1; attempt <= r.cfg.MaxAttempts; attempt++ {
		res.Attempts = attempt
		succ, err := r.cfg.Applier.Apply(ctx, job.RealityID, job.MigrationID)
		if err == nil && succ {
			_ = r.cfg.Auditor.RecordEvent(ctx, AuditEvent{
				RealityID:     job.RealityID,
				MigrationID:   job.MigrationID,
				RunID:         job.RunID,
				EventType:     "migration_succeeded",
				AttemptNumber: attempt,
			})
			_ = r.cfg.StateWriter.MarkApplied(ctx, job.RealityID, job.MigrationID)
			res.Succeeded = true
			return res
		}
		lastErr = err
		// Permanent (non-transient) failure: skip remaining attempts.
		if err != nil && !errors.Is(err, ErrTransient) {
			break
		}
		// Sleep with exponential backoff (skipped on the LAST attempt
		// since we won't retry).
		if attempt < r.cfg.MaxAttempts {
			delay := r.backoff(attempt)
			r.cfg.Sleeper.Sleep(ctx, delay)
		}
	}
	// Persistent failure path — Q-L1D-1 V1: NO auto-rollback. Just record
	// the dead-letter state. SRE runs runbooks/migration/persistent_failure.md.
	reason := "persistent"
	if lastErr != nil && !errors.Is(lastErr, ErrTransient) {
		reason = "permanent_error"
	}
	res.FinalError = lastErr
	res.FinalReason = reason
	_ = r.cfg.Auditor.RecordEvent(ctx, AuditEvent{
		RealityID:     job.RealityID,
		MigrationID:   job.MigrationID,
		RunID:         job.RunID,
		EventType:     "migration_failed",
		AttemptNumber: res.Attempts,
		FailureDetail: map[string]any{
			"reason":     reason,
			"last_error": errorString(lastErr),
		},
	})
	_ = r.cfg.StateWriter.MarkFailed(ctx, job.RealityID, job.MigrationID, reason)
	return res
}

// backoff returns the delay for attempt N. Capped at MaxBackoff.
func (r *Runner) backoff(attempt int) time.Duration {
	d := r.cfg.BaseBackoff << (attempt - 1)
	if d > r.cfg.MaxBackoff {
		d = r.cfg.MaxBackoff
	}
	return d
}

func errorString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

// PeakConcurrency is a test helper exposed to package-internal tests so
// they can pin the concurrency-cap behavior. Test-only; the Applier
// implementation in tests increments + records peak via atomic.
type PeakConcurrency struct {
	current int64
	peak    int64
}

// Enter is called by a test Applier when Apply starts; must be paired
// with Exit() via defer.
func (p *PeakConcurrency) Enter() {
	n := atomic.AddInt64(&p.current, 1)
	for {
		old := atomic.LoadInt64(&p.peak)
		if n <= old || atomic.CompareAndSwapInt64(&p.peak, old, n) {
			break
		}
	}
}

// Exit pairs with Enter.
func (p *PeakConcurrency) Exit() { atomic.AddInt64(&p.current, -1) }

// Peak returns the largest observed concurrent count.
func (p *PeakConcurrency) Peak() int { return int(atomic.LoadInt64(&p.peak)) }
