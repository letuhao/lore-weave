package lifecycle

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// DrainHooks is the ordered set of shutdown callbacks fired by Drain.
// Order is FIXED per SR06 §12AI.11 — callers cannot reorder; missing
// hooks are no-ops (a stateless service can omit FlushOutbox, e.g.).
//
// The order matters: a wedged DB call must not block FlushOutbox; the
// outbox row stays unflushed and the next replica picks it up via
// claim-lock. Drain bounds wall-clock; correctness preserved.
type DrainHooks struct {
	// StopAccepting — flip /health/ready to 503; LB stops routing new
	// requests; WS new connections rejected (close code 4011). MUST be
	// quick (no I/O); we don't pass a ctx because there's nothing to
	// cancel — it's a flag flip.
	StopAccepting func()

	// WaitInFlight — block until active request-handlers complete OR ctx
	// deadline expires. Bounded by drain timeout.
	WaitInFlight func(context.Context) error

	// FlushOutbox — best-effort final drain of the outbox to Redis.
	// Remaining rows persist; next replica via claim-lock.
	FlushOutbox func(context.Context) error

	// CloseBreakers — open all circuit breakers so any in-flight outbound
	// call returns ErrCircuitOpen immediately rather than waiting on
	// their per-dep timeout.
	CloseBreakers func() error

	// CloseResources — orderly DB pool close, Redis disconnect, HTTP
	// idle-close. Last because it MUST run even if earlier steps timed
	// out (otherwise sockets leak).
	CloseResources func() error
}

// DrainResult captures which hooks ran and their outcomes. Mostly useful
// for the post-shutdown audit log + the "drain duration" metric.
type DrainResult struct {
	StoppedAccepting    bool
	WaitedInFlight      bool
	WaitInFlightErr     error
	FlushedOutbox       bool
	FlushOutboxErr      error
	ClosedBreakers      bool
	CloseBreakersErr    error
	ClosedResources     bool
	CloseResourcesErr   error
	Elapsed             time.Duration
	DeadlineExceeded    bool
}

// ErrDrainTimeoutInvalid is returned by Drain on non-positive timeout.
var ErrDrainTimeoutInvalid = errors.New("lifecycle: drain timeout must be > 0")

// Drain executes the five SR06-mandated shutdown hooks IN ORDER and
// returns a DrainResult capturing per-step outcomes. The function
// guarantees:
//
//   - timeout > 0 — else ErrDrainTimeoutInvalid returned synchronously
//     (caller passed a zero timeout = bug; we never silently default).
//   - StopAccepting runs FIRST and is unbounded (it's a flag flip;
//     no ctx because there's nothing meaningful to cancel).
//   - The remaining four hooks share ONE deadline derived from `timeout`.
//     If hook N runs over the deadline, hook N+1 still runs but with a
//     ctx that's already-cancelled — the hook MUST honor that and
//     bail quickly.
//   - CloseResources ALWAYS runs, even if every preceding hook failed.
//     Sockets must not leak; the underlying pool close is non-blocking.
//   - Nil hooks are no-ops (a stateless service omitting FlushOutbox is
//     valid; we don't force every service to implement all five).
//
// Returns nil error on full success. Returns a wrapped error otherwise;
// the caller inspects DrainResult for per-step detail.
func Drain(parent context.Context, timeout time.Duration, hooks DrainHooks) (DrainResult, error) {
	res := DrainResult{}
	if timeout <= 0 {
		return res, fmt.Errorf("%w: got %v", ErrDrainTimeoutInvalid, timeout)
	}
	if parent == nil {
		parent = context.Background()
	}
	start := time.Now()
	defer func() { res.Elapsed = time.Since(start) }()

	// Step 1 — StopAccepting (unbounded; flag flip).
	if hooks.StopAccepting != nil {
		hooks.StopAccepting()
		res.StoppedAccepting = true
	}

	// Steps 2–5 share one deadline derived from `timeout`.
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()

	// Step 2 — WaitInFlight.
	if hooks.WaitInFlight != nil {
		res.WaitedInFlight = true
		if err := hooks.WaitInFlight(ctx); err != nil {
			res.WaitInFlightErr = err
		}
	}

	// Step 3 — FlushOutbox.
	if hooks.FlushOutbox != nil {
		res.FlushedOutbox = true
		if err := hooks.FlushOutbox(ctx); err != nil {
			res.FlushOutboxErr = err
		}
	}

	// Step 4 — CloseBreakers (no ctx; this is internal state mutation).
	if hooks.CloseBreakers != nil {
		res.ClosedBreakers = true
		if err := hooks.CloseBreakers(); err != nil {
			res.CloseBreakersErr = err
		}
	}

	// Step 5 — CloseResources (ALWAYS runs; no ctx — pool close is non-blocking).
	if hooks.CloseResources != nil {
		res.ClosedResources = true
		if err := hooks.CloseResources(); err != nil {
			res.CloseResourcesErr = err
		}
	}

	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		res.DeadlineExceeded = true
	}

	if !res.IsSuccess() {
		return res, fmt.Errorf("lifecycle: drain completed with errors (deadline_exceeded=%v)", res.DeadlineExceeded)
	}
	return res, nil
}

// IsSuccess returns true iff every per-step error is nil AND the deadline
// was not exceeded. A successful drain means every hook completed cleanly
// within `timeout`.
func (r DrainResult) IsSuccess() bool {
	if r.DeadlineExceeded {
		return false
	}
	if r.WaitInFlightErr != nil ||
		r.FlushOutboxErr != nil ||
		r.CloseBreakersErr != nil ||
		r.CloseResourcesErr != nil {
		return false
	}
	return true
}

// DrainTimeoutDefaults — SR06 §12AI.11 per-service-class defaults.
// Callers SHOULD use these unless they have a documented reason otherwise.
const (
	// DrainTimeoutDefault is the V1 default for typical services.
	DrainTimeoutDefault = 30 * time.Second

	// DrainTimeoutStateless — api-gateway-bff, lightweight handlers.
	DrainTimeoutStateless = 10 * time.Second

	// DrainTimeoutLongRunner — migration-orchestrator, publisher.
	DrainTimeoutLongRunner = 120 * time.Second
)
