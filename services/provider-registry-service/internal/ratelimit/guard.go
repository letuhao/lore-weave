package ratelimit

import (
	"context"
	"errors"
)

var ErrCircuitOpen = errors.New("provider circuit open")

type CircuitBreaker interface {
	Allow(ctx context.Context, kind string) (bool, error)
	Record(ctx context.Context, kind string, success bool)
}

type ConcurrencyGovernor interface {
	Acquire(waitCtx, callCtx context.Context, concClass string, limit int) (ProviderPermit, error)
}

func Guard(
	waitCtx context.Context,
	callCtx context.Context,
	gov ConcurrencyGovernor,
	brk CircuitBreaker,
	concClass string,
	limit int,
	isTransient func(error) bool,
	call func(context.Context) error,
) error {
	if callCtx == nil {
		callCtx = waitCtx
	}
	if brk != nil {
		allowed, _ := brk.Allow(waitCtx, concClass)
		if !allowed {
			return ErrCircuitOpen
		}
	}
	if limit > 0 && gov == nil {
		return ErrGovernorUnavailable
	}
	var permit ProviderPermit
	var err error
	if gov == nil {
		permit = newNoopPermit(callCtx)
	} else {
		permit, err = gov.Acquire(waitCtx, callCtx, concClass, limit)
		if err != nil {
			return err
		}
	}
	defer permit.Release()

	callErr := call(permit.Context())
	if errors.Is(context.Cause(permit.Context()), ErrLeaseLost) {
		callErr = errors.Join(callErr, ErrLeaseLost)
	}
	if brk != nil {
		if callErr == nil {
			brk.Record(waitCtx, concClass, true)
		} else if isTransient(callErr) || errors.Is(callErr, ErrLeaseLost) || errors.Is(callErr, ErrGovernorUnavailable) {
			brk.Record(waitCtx, concClass, false)
		}
	}
	return callErr
}
