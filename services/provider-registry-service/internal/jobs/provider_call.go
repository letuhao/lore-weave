package jobs

import (
	"context"

	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

type providerCallScopeKey struct{}
type providerCallScope struct {
	class string
	limit int
}

func withProviderCallScope(ctx context.Context, class string, limit int) context.Context {
	return context.WithValue(ctx, providerCallScopeKey{}, providerCallScope{class: class, limit: limit})
}

func providerCallScopeFrom(ctx context.Context) (providerCallScope, bool) {
	scope, ok := ctx.Value(providerCallScopeKey{}).(providerCallScope)
	return scope, ok
}

func (w *Worker) withProviderCall(ctx context.Context, class string, limit int, call func(context.Context) error) error {
	waitCtx := ctx
	cancelWait := func() {}
	if w.concurrencyAcquireTimeout > 0 {
		waitCtx, cancelWait = context.WithTimeout(ctx, w.concurrencyAcquireTimeout)
	}
	defer cancelWait()
	return ratelimit.Guard(waitCtx, ctx, w.gov, w.brk, class, limit, provider.IsTransientUpstreamError, call)
}

func (w *Worker) withScopedProviderCall(ctx context.Context, call func(context.Context) error) error {
	scope, ok := providerCallScopeFrom(ctx)
	if !ok {
		return ratelimit.ErrGovernorUnavailable
	}
	// callProvider INSIDE the Guard: a model-lease request riding the ctx is
	// acquired per attempt (a retry re-acquires), mirroring the chat path.
	return w.withProviderCall(ctx, scope.class, scope.limit, func(c context.Context) error {
		return w.callProvider(ctx, func() error { return call(c) })
	})
}
