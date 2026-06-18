// Package retry implements the publisher's backoff + dead-letter policy.
//
// Per L2.D.4 + R06 §12F.5:
//   - On XADD failure: increment attempts, set last_error, set
//     last_attempt_at = NOW(). Defer next attempt by an exponential backoff
//     (capped at maxBackoff).
//   - Once attempts >= maxAttempts: set dead_lettered_at = NOW() and SKIP
//     in the pending scan. Dead-letter triage is the SRE's
//     `runbooks/publisher/lag.md` workflow.
package retry

import (
	"errors"
	"time"
)

// Policy is the configuration knobs every retry decision reads from. Held
// as a separate struct so tests can construct fast/predictable policies.
type Policy struct {
	// MaxAttempts is the inclusive upper bound on outbox attempts before
	// dead-lettering. Default 10 — tunable via env / config in cycle 11+.
	MaxAttempts int
	// BaseBackoff is the first sleep delta after attempt #1 failure.
	BaseBackoff time.Duration
	// MaxBackoff caps exponential growth; once reached, every subsequent
	// retry sleeps the same maxBackoff (prevents starving the loop on
	// pathological-failure events).
	MaxBackoff time.Duration
}

// DefaultPolicy returns the V1 production defaults. 10 attempts × backoff
// 100ms → 51.2s cap covers the typical Redis-Streams reconnect window
// without burning the publisher loop on a stuck shard.
func DefaultPolicy() Policy {
	return Policy{
		MaxAttempts: 10,
		BaseBackoff: 100 * time.Millisecond,
		MaxBackoff:  60 * time.Second,
	}
}

// Decision is what the poll loop's outcome handler does with a row after
// an XADD attempt.
type Decision int

const (
	// MarkPublished — XADD succeeded; UPDATE published=TRUE.
	MarkPublished Decision = iota
	// Retry — transient failure; UPDATE attempts++, last_error, schedule
	// next retry at NOW() + BackoffFor(attempts).
	Retry
	// DeadLetter — attempts >= MaxAttempts; UPDATE dead_lettered_at = NOW().
	DeadLetter
)

func (d Decision) String() string {
	switch d {
	case MarkPublished:
		return "mark_published"
	case Retry:
		return "retry"
	case DeadLetter:
		return "dead_letter"
	}
	return "unknown"
}

// Classify maps (currentAttempts, xaddErr) → next Decision. currentAttempts
// is the row's attempts column BEFORE this attempt; we increment before
// comparing against MaxAttempts.
func Classify(p Policy, currentAttempts int, xaddErr error) Decision {
	if xaddErr == nil {
		return MarkPublished
	}
	next := currentAttempts + 1
	if next >= p.MaxAttempts {
		return DeadLetter
	}
	return Retry
}

// BackoffFor returns the sleep delta the loop should apply BEFORE retrying
// this row. Exponential growth: base × 2^(attempts-1), capped at MaxBackoff.
// attempts is the row's NEW attempts value (post-increment).
//
// Attempt 1 → base
// Attempt 2 → base × 2
// Attempt 3 → base × 4
// …
// Capped at MaxBackoff.
func BackoffFor(p Policy, attempts int) time.Duration {
	if attempts < 1 {
		attempts = 1
	}
	d := p.BaseBackoff
	for i := 1; i < attempts; i++ {
		d *= 2
		if d >= p.MaxBackoff {
			return p.MaxBackoff
		}
	}
	if d > p.MaxBackoff {
		return p.MaxBackoff
	}
	return d
}

// ErrInvalidPolicy is returned by Policy.Validate when an obviously wrong
// config slips through (caller bug).
var ErrInvalidPolicy = errors.New("retry: invalid policy")

// Validate enforces the minimum-viable invariants. Returns ErrInvalidPolicy
// wrapping a descriptive message on failure.
func (p Policy) Validate() error {
	if p.MaxAttempts < 1 {
		return errors.Join(ErrInvalidPolicy, errors.New("MaxAttempts < 1"))
	}
	if p.BaseBackoff <= 0 {
		return errors.Join(ErrInvalidPolicy, errors.New("BaseBackoff <= 0"))
	}
	if p.MaxBackoff < p.BaseBackoff {
		return errors.Join(ErrInvalidPolicy, errors.New("MaxBackoff < BaseBackoff"))
	}
	return nil
}
