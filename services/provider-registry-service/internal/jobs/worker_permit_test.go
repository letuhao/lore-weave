package jobs

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

type perCallPermit struct {
	ctx     context.Context
	release func()
}

func (p *perCallPermit) Context() context.Context { return p.ctx }
func (p *perCallPermit) Release()                 { p.release() }

type perCallGovernor struct{ acquired, released atomic.Int32 }

func (g *perCallGovernor) Acquire(_ context.Context, callCtx context.Context, _ string, _ int) (ratelimit.ProviderPermit, error) {
	g.acquired.Add(1)
	return &perCallPermit{ctx: callCtx, release: func() { g.released.Add(1) }}, nil
}

func TestSpecializedWorkerAttemptsAreGuardedAndRetryReacquires(t *testing.T) {
	w := &Worker{gov: &perCallGovernor{}, maxRetries: 1}
	gov := w.gov.(*perCallGovernor)
	attempt := int32(0)
	err := retryTransient(context.Background(), w.maxRetries, nil, func() error {
		return w.withScopedProviderCall(withProviderCallScope(context.Background(), "cred-a", 2), func(context.Context) error {
			if atomic.AddInt32(&attempt, 1) == 1 {
				return &provider.ErrUpstreamTransient{StatusCode: 503}
			}
			return nil
		})
	})
	if err != nil {
		t.Fatalf("retry failed: %v", err)
	}
	if gov.acquired.Load() != 2 || gov.released.Load() != 2 {
		t.Fatalf("permit counts acquired/released=%d/%d", gov.acquired.Load(), gov.released.Load())
	}
}

func TestSpecializedWorkerWithoutGovernorFailsClosed(t *testing.T) {
	w := &Worker{}
	called := false
	err := w.withScopedProviderCall(withProviderCallScope(context.Background(), "cred-a", 2), func(context.Context) error { called = true; return nil })
	if !errors.Is(err, ratelimit.ErrGovernorUnavailable) || called {
		t.Fatalf("err=%v providerCalled=%v", err, called)
	}
}
