package ratelimit

import (
	"context"
	"errors"
)

// ErrCircuitOpen — the provider's circuit-breaker is open; the call was rejected
// without touching the provider. The worker maps this to LLM_CIRCUIT_OPEN.
var ErrCircuitOpen = errors.New("provider circuit open")

// CircuitBreaker / ConcurrencyGovernor — the surfaces Guard depends on. *Breaker
// and *Governor satisfy them; tests supply fakes. Callers MUST pass an UNTYPED
// nil to disable a layer (a typed-nil concrete boxed in the interface would be
// non-nil and panic) — the worker holds these as interface fields, left nil
// when REDIS_URL is unset.
type CircuitBreaker interface {
	Allow(ctx context.Context, kind string) (bool, error)
	Record(ctx context.Context, kind string, success bool)
}

type ConcurrencyGovernor interface {
	Acquire(ctx context.Context, concClass string, limit int) (func(), error)
}

// Guard wraps a single provider call with the circuit-breaker + concurrency
// governor for `kind`. `gov` and `brk` may be nil (governance disabled, e.g.
// REDIS_URL unset) → the call passes through unchanged, so existing code paths
// and unit tests stay Redis-free.
//
// `isTransient` classifies an error as a transient/upstream provider-health
// failure (429/5xx). Only those count against the breaker; a permanent error
// (e.g. a 400 bad request) is neither a health failure nor a recovery signal,
// so it leaves the breaker untouched — a user's bad request can never trip it.
func Guard(
	ctx context.Context,
	gov ConcurrencyGovernor,
	brk CircuitBreaker,
	concClass string,
	limit int,
	isTransient func(error) bool,
	call func() error,
) error {
	if brk != nil {
		allowed, _ := brk.Allow(ctx, concClass)
		if !allowed {
			return ErrCircuitOpen
		}
	}
	if gov != nil {
		release, err := gov.Acquire(ctx, concClass, limit)
		if err != nil {
			return err // governor timeout / ctx cancel — treated as transient by caller
		}
		defer release()
	}

	err := call()

	if brk != nil {
		if err == nil {
			brk.Record(ctx, concClass, true) // healthy → reset/close
		} else if isTransient(err) {
			brk.Record(ctx, concClass, false) // provider-health failure → count toward open
		}
		// permanent (non-transient) error → leave the breaker untouched
	}
	return err
}
