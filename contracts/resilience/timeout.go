package resilience

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// ErrInvalidTimeout is returned by WithTimeout when the configured timeout
// is non-positive. A zero or negative timeout is ALWAYS a programmer bug —
// silently treating it as "no timeout" defeats SR06 I16.
var ErrInvalidTimeout = errors.New("resilience: invalid timeout (must be > 0)")

// WithTimeout runs fn with a deadline derived from the parent ctx and the
// per-dep `timeout` value sourced from `contracts/dependencies/matrix.yaml`.
// It is the canonical SR06 I16 enforcement point — every outbound network
// or DB call MUST go through this wrapper (or a wrapper that wraps this).
//
// Semantics:
//
//   - timeout MUST be > 0. A non-positive timeout returns ErrInvalidTimeout
//     synchronously; fn is never invoked. This is intentional: silently
//     defaulting to "no deadline" cascades into pool exhaustion (the exact
//     failure mode SR06 was designed to prevent).
//   - If the parent ctx already carries a tighter deadline, WithTimeout
//     respects the tighter bound — the per-dep timeout is a CAP, never an
//     extension. A request-chain budget of 5s and a per-dep timeout of 60s
//     yields a 5s actual deadline, NOT 60s.
//   - On fn-returns-before-deadline, the cancel func is invoked
//     immediately (defer cancel()) to free the timer.
//   - The returned error is fn's error verbatim. WithTimeout NEVER wraps
//     fn's error to keep `errors.Is(err, ctx.Err())` cheap for callers.
func WithTimeout(parent context.Context, depName string, timeout time.Duration, fn func(context.Context) error) error {
	if timeout <= 0 {
		return fmt.Errorf("%w: dep=%q timeout=%v", ErrInvalidTimeout, depName, timeout)
	}
	if parent == nil {
		// Defensive: a nil parent ctx slipped through. context.WithTimeout
		// panics on nil; surface a typed error instead so the caller can
		// add a metric without crashing.
		return fmt.Errorf("%w: dep=%q parent ctx is nil", ErrInvalidTimeout, depName)
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()
	return fn(ctx)
}

// DeadlineRemaining returns the remaining budget on ctx. Useful when a
// caller wants to fast-fail BEFORE making an outbound call that obviously
// won't fit (e.g., remaining=10ms, RTT 30ms → skip).
//
// Returns (remaining, true) if ctx carries a deadline; (0, false) otherwise.
func DeadlineRemaining(ctx context.Context) (time.Duration, bool) {
	dl, ok := ctx.Deadline()
	if !ok {
		return 0, false
	}
	return time.Until(dl), true
}
