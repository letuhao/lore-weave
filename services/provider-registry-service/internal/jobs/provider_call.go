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
	return w.withProviderCall(ctx, scope.class, scope.limit, call)
}
