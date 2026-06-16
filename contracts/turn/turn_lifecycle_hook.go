package turn

import (
	"context"
	"sync"
	"sync/atomic"
)

// turn_lifecycle_hook.go — integration with cycle-18 contracts/lifecycle.Drain.
//
// At service Drain, the lifecycle subsystem runs hooks in this order:
//   StopAccepting → WaitInFlight → FlushOutbox → CloseBreakers → CloseResources
//
// Turn-aware services register a TurnInFlightTracker as the WaitInFlight hook
// so we don't drain mid-turn (would orphan a half-streamed response).
//
// This file ships the tracker + a Drain-compatible hook signature; the
// concrete contracts/lifecycle wiring stays in the consumer service so we
// avoid a cross-module dependency in V1.

// TurnInFlightTracker counts active (non-terminal) turns. Safe for concurrent
// use. Hot-path increments are atomic so we don't take a mutex on every turn.
type TurnInFlightTracker struct {
	inflight atomic.Int64
	// done is signalled when inflight drops to zero AND closed has fired.
	done    chan struct{}
	doOnce  sync.Once
	closeMu sync.Mutex
	closed  bool
}

// NewTurnInFlightTracker constructs a tracker.
func NewTurnInFlightTracker() *TurnInFlightTracker {
	return &TurnInFlightTracker{done: make(chan struct{})}
}

// Start records a new in-flight turn. Returns a deferred-cleanup function that
// MUST be called exactly once (typical pattern: `defer tracker.Start()()`).
func (t *TurnInFlightTracker) Start() func() {
	t.inflight.Add(1)
	return func() { t.End() }
}

// End decrements the in-flight counter. Calling End on a zero counter is a
// programmer error and panics — surface the bug early instead of leaking.
func (t *TurnInFlightTracker) End() {
	v := t.inflight.Add(-1)
	if v < 0 {
		panic("turn: End called more times than Start")
	}
	t.closeMu.Lock()
	defer t.closeMu.Unlock()
	if t.closed && v == 0 {
		t.doOnce.Do(func() { close(t.done) })
	}
}

// InFlight returns the current count.
func (t *TurnInFlightTracker) InFlight() int64 {
	return t.inflight.Load()
}

// WaitForDrain blocks until all in-flight turns finish OR ctx is cancelled.
// Call StopAccepting first so no new turns Start while we wait.
func (t *TurnInFlightTracker) WaitForDrain(ctx context.Context) error {
	t.closeMu.Lock()
	t.closed = true
	if t.inflight.Load() == 0 {
		t.doOnce.Do(func() { close(t.done) })
	}
	t.closeMu.Unlock()

	select {
	case <-t.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}
