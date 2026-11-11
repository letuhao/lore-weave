package ratelimit

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type fakeFailureGovernor struct{}

func (fakeFailureGovernor) Acquire(context.Context, context.Context, string, int) (ProviderPermit, error) {
	return nil, ErrGovernorUnavailable
}

func TestLocalGovernorCapsCallsAndReclaimsIdleSlots(t *testing.T) {
	g := NewLocalGovernor()
	const n, limit = 12, 3
	var active, maxActive atomic.Int32
	var wg sync.WaitGroup
	start := make(chan struct{})
	for range n {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			p, err := g.Acquire(context.Background(), context.Background(), "cred", limit)
			if err != nil {
				t.Errorf("Acquire: %v", err)
				return
			}
			cur := active.Add(1)
			for old := maxActive.Load(); cur > old && !maxActive.CompareAndSwap(old, cur); old = maxActive.Load() {
			}
			time.Sleep(time.Millisecond)
			active.Add(-1)
			p.Release()
		}()
	}
	close(start)
	wg.Wait()
	if maxActive.Load() > limit {
		t.Fatalf("max active=%d cap=%d", maxActive.Load(), limit)
	}
	if active.Load() != 0 {
		t.Fatalf("active left=%d", active.Load())
	}
	if len(g.slots) != 0 {
		t.Fatalf("idle slot map retained %d entries", len(g.slots))
	}
}

func TestLocalGovernorWaitCancellationReclaimsEntry(t *testing.T) {
	g := NewLocalGovernor()
	p, err := g.Acquire(context.Background(), context.Background(), "cred", 1)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := g.Acquire(ctx, context.Background(), "cred", 1); !errors.Is(err, context.Canceled) {
		t.Fatalf("err=%v", err)
	}
	p.Release()
	if len(g.slots) != 0 {
		t.Fatalf("idle slot retained: %d", len(g.slots))
	}
}

func TestCompositeGovernorFailsClosedAndReleasesLocalOnRedisError(t *testing.T) {
	local := NewLocalGovernor()
	g := NewCompositeGovernor(fakeFailureGovernor{}, local)
	if _, err := g.Acquire(context.Background(), context.Background(), "cred", 2); !errors.Is(err, ErrGovernorUnavailable) {
		t.Fatalf("err=%v", err)
	}
	if len(local.slots) != 0 {
		t.Fatalf("local slot leaked: %d", len(local.slots))
	}
}
