package chaos

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// ErrChaosInjected is returned by Hook.Apply when the hook decided to
// FAIL the call. Callers SHOULD wrap this with their own typed error so
// the chaos-injected failure is visible in the audit trail.
//
// Anti-foot-gun rule: production callers MUST treat ErrChaosInjected as a
// real failure (do not auto-retry, do not silently swallow). The whole
// point of a chaos drill is to exercise the failure-handling path.
var ErrChaosInjected = errors.New("chaos: injected failure")

// HookID is the stable string identifier for an instrumentation point.
// Naming convention: "<service>.<package>.<func>.<phase>" (e.g.,
// "publisher.outbox.drain.before_redis_xadd").
//
// HookIDs are matched exactly — no glob, no regex. Keeping match exact
// makes the audit-row "what fired" question trivially answerable.
type HookID string

// Hook is the SDK abstraction over a single chaos-injection point.
// Implementations MUST be safe for concurrent use; the registry hands the
// same pointer to many goroutines.
//
// Apply MUST honor ctx cancellation (i.e., not block past ctx.Done()).
// Returning a non-nil error signals "injected failure"; returning nil
// signals "no chaos fires this call" (the caller continues normally).
type Hook interface {
	// ID returns the HookID this Hook is bound to.
	ID() HookID

	// Apply is invoked at the instrumentation point. Returning an error
	// signals the caller should treat the call as failed (wrap with
	// ErrChaosInjected). Returning nil signals "no chaos this call".
	Apply(ctx context.Context) error

	// IsExhausted returns true when the hook has fired its budget and
	// will return nil for all subsequent calls. Used by the V1+30d
	// chaos-engine to auto-deregister exhausted hooks.
	IsExhausted() bool
}

// NoopHook is the default Hook every service binds before chaos-engine
// activates. Apply always returns nil; IsExhausted returns true so the
// registry can prune.
type NoopHook struct {
	HookID HookID
}

// ID implements Hook.
func (n *NoopHook) ID() HookID { return n.HookID }

// Apply implements Hook. Always returns nil.
func (n *NoopHook) Apply(_ context.Context) error { return nil }

// IsExhausted always true — Noop is "permanently exhausted" by design.
func (n *NoopHook) IsExhausted() bool { return true }

// ─────────────────────────────────────────────────────────────────────
// FailOnce — fires ErrChaosInjected on the first call, returns nil after.
// ─────────────────────────────────────────────────────────────────────

// FailOnce is the canonical "trip once" Hook. The first Apply returns
// ErrChaosInjected; every subsequent Apply returns nil. Used to exercise
// circuit-breaker open/half-open transitions in tests + V1+30d drills.
type FailOnce struct {
	HookID HookID
	// Reason is included in the error message for audit clarity.
	Reason string

	tripped atomic.Bool
}

// ID implements Hook.
func (f *FailOnce) ID() HookID { return f.HookID }

// Apply trips on first call. CompareAndSwap means concurrent calls trip
// exactly one of them.
func (f *FailOnce) Apply(_ context.Context) error {
	if f.tripped.CompareAndSwap(false, true) {
		return fmt.Errorf("%w: %s [hook=%s]", ErrChaosInjected, f.Reason, f.HookID)
	}
	return nil
}

// IsExhausted returns true after the first trip.
func (f *FailOnce) IsExhausted() bool { return f.tripped.Load() }

// ─────────────────────────────────────────────────────────────────────
// DelayOnce — sleeps for D on the first call, then short-circuits.
// ─────────────────────────────────────────────────────────────────────

// DelayOnce inserts a one-shot wall-clock delay at an instrumentation
// point. Useful for exercising timeout boundaries without manufacturing
// real backend slowness. Honors ctx cancellation.
type DelayOnce struct {
	HookID HookID
	Delay  time.Duration

	fired atomic.Bool
}

// ID implements Hook.
func (d *DelayOnce) ID() HookID { return d.HookID }

// Apply sleeps Delay on first call, honoring ctx cancellation. Returns
// ctx.Err() if cancellation fires; nil otherwise (delay is not a
// "failure", just a "slow").
func (d *DelayOnce) Apply(ctx context.Context) error {
	if !d.fired.CompareAndSwap(false, true) {
		return nil
	}
	if d.Delay <= 0 {
		return nil
	}
	select {
	case <-time.After(d.Delay):
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// IsExhausted returns true after first fire.
func (d *DelayOnce) IsExhausted() bool { return d.fired.Load() }

// ─────────────────────────────────────────────────────────────────────
// HookRegistry — service-local store of (HookID → Hook).
// ─────────────────────────────────────────────────────────────────────

// HookRegistry is the per-service Hook store. DEFAULT is empty (no chaos
// fires). The V1+30d chaos-engine populates it via a sidecar RPC.
//
// Concurrency: Register / Get / Deregister are safe for concurrent use.
// The registry NEVER blocks on the hot path (Get returns immediately
// even if Register holds the mutex briefly).
type HookRegistry struct {
	mu    sync.RWMutex
	hooks map[HookID]Hook
}

// NewHookRegistry returns an empty registry. Safe to share across
// goroutines.
func NewHookRegistry() *HookRegistry {
	return &HookRegistry{hooks: make(map[HookID]Hook)}
}

// Register adds or replaces a hook. Returns the previously-registered
// hook if one was bound (caller may want to log the replacement).
func (r *HookRegistry) Register(h Hook) Hook {
	if h == nil {
		return nil
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	prev := r.hooks[h.ID()]
	r.hooks[h.ID()] = h
	return prev
}

// Get returns the hook bound to id, or nil if none. Hot-path safe — uses
// a read lock so many callers can dispatch concurrently.
func (r *HookRegistry) Get(id HookID) Hook {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.hooks[id]
}

// Deregister removes the hook bound to id. Returns the removed hook (or
// nil if none was bound).
func (r *HookRegistry) Deregister(id HookID) Hook {
	r.mu.Lock()
	defer r.mu.Unlock()
	prev := r.hooks[id]
	delete(r.hooks, id)
	return prev
}

// Len returns the number of bound hooks. For test assertions.
func (r *HookRegistry) Len() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.hooks)
}

// Apply is the call-site convenience helper. If a hook is bound for id,
// Apply runs it and returns the result. If no hook is bound, returns
// nil immediately (zero-cost path for unhooked services). This is the
// helper instrumentation code SHOULD use, not Get + Apply directly,
// because it preserves the "no chaos = no overhead" invariant.
func (r *HookRegistry) Apply(ctx context.Context, id HookID) error {
	h := r.Get(id)
	if h == nil {
		return nil
	}
	return h.Apply(ctx)
}
