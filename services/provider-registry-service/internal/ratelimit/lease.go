package ratelimit

import (
	"context"
	"errors"
	"sync"
)

var (
	ErrGovernorUnavailable = errors.New("provider concurrency governor unavailable")
	ErrLeaseLost           = errors.New("provider concurrency lease lost")
)

type AcquireError struct{ cause error }

func (e *AcquireError) Error() string {
	return ErrGovernorUnavailable.Error() + ": " + e.cause.Error()
}

func (e *AcquireError) Unwrap() error { return e.cause }
func (e *AcquireError) Is(target error) bool {
	return target == ErrGovernorUnavailable
}

// ProviderPermit carries the context the provider call must honor and releases
// all acquired concurrency slots when the call ends.
type ProviderPermit interface {
	Context() context.Context
	Release()
}

type permit struct {
	ctx       context.Context
	cancel    context.CancelCauseFunc
	releaseFn func()
	once      sync.Once
}

func newPermit(ctx context.Context, cancel context.CancelCauseFunc, release func()) ProviderPermit {
	return &permit{ctx: ctx, cancel: cancel, releaseFn: release}
}

func newNoopPermit(parent context.Context) ProviderPermit {
	ctx, cancel := context.WithCancelCause(parent)
	return newPermit(ctx, cancel, nil)
}

func (p *permit) Context() context.Context { return p.ctx }

func (p *permit) Release() {
	p.once.Do(func() {
		p.cancel(context.Canceled)
		if p.releaseFn != nil {
			p.releaseFn()
		}
	})
}
