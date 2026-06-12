package resilience

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

// mockClock advances by explicit Tick(); production time.Now is never called
// from these tests so we can deterministically cross OpenDuration thresholds.
type mockClock struct {
	mu  sync.Mutex
	now time.Time
}

func newMockClock() *mockClock {
	return &mockClock{now: time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)}
}

func (m *mockClock) Now() time.Time {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.now
}

func (m *mockClock) Tick(d time.Duration) {
	m.mu.Lock()
	m.now = m.now.Add(d)
	m.mu.Unlock()
}

var errDepFailed = errors.New("dep failed")

func TestBreaker_DefaultsApplied(t *testing.T) {
	b := NewBreaker("test", BreakerConfig{}).(*breaker)
	if b.cfg.MinRequests != 20 {
		t.Errorf("MinRequests = %d, want 20", b.cfg.MinRequests)
	}
	if b.cfg.OpenDuration != 30*time.Second {
		t.Errorf("OpenDuration = %v, want 30s", b.cfg.OpenDuration)
	}
	if b.cfg.ErrorRateThreshold != 0.25 {
		t.Errorf("ErrorRateThreshold = %v, want 0.25", b.cfg.ErrorRateThreshold)
	}
}

func TestBreaker_ClosedStaysClosedBelowMinRequests(t *testing.T) {
	clock := newMockClock()
	b := NewBreaker("d", BreakerConfig{
		ErrorRateThreshold: 0.5,
		MinRequests:        10,
		OpenDuration:       100 * time.Millisecond,
		Now:                clock.Now,
	})
	// All failures, but only 5 calls — below MinRequests; should stay Closed.
	for i := 0; i < 5; i++ {
		_ = b.Call(context.Background(), func(ctx context.Context) error { return errDepFailed })
	}
	if got := b.State(); got != StateClosed {
		t.Errorf("State = %v, want Closed (below MinRequests)", got)
	}
}

func TestBreaker_TripsClosedToOpenOnErrorRate(t *testing.T) {
	clock := newMockClock()
	b := NewBreaker("d", BreakerConfig{
		ErrorRateThreshold: 0.5,
		MinRequests:        4,
		OpenDuration:       time.Hour,
		Now:                clock.Now,
	})
	// 4 calls, 3 failures — 75% > 50% threshold.
	for i := 0; i < 3; i++ {
		_ = b.Call(context.Background(), func(ctx context.Context) error { return errDepFailed })
	}
	_ = b.Call(context.Background(), func(ctx context.Context) error { return nil })
	if got := b.State(); got != StateOpen {
		t.Errorf("State = %v, want Open after 75%% error rate", got)
	}
}

func TestBreaker_OpenFastFails(t *testing.T) {
	clock := newMockClock()
	b := NewBreaker("d", BreakerConfig{
		ErrorRateThreshold: 0.5,
		MinRequests:        2,
		OpenDuration:       time.Hour,
		Now:                clock.Now,
	})
	for i := 0; i < 2; i++ {
		_ = b.Call(context.Background(), func(ctx context.Context) error { return errDepFailed })
	}
	if b.State() != StateOpen {
		t.Fatalf("precondition: State = %v, want Open", b.State())
	}
	invoked := false
	err := b.Call(context.Background(), func(ctx context.Context) error {
		invoked = true
		return nil
	})
	if !errors.Is(err, ErrCircuitOpen) {
		t.Errorf("err = %v, want ErrCircuitOpen", err)
	}
	if invoked {
		t.Errorf("fn should NOT be invoked when breaker open")
	}
	if got := b.Metrics().FastFailedSinceOpen; got != 1 {
		t.Errorf("FastFailedSinceOpen = %d, want 1", got)
	}
}

func TestBreaker_OpenToHalfOpenAfterDuration_ProbeSuccessClosed(t *testing.T) {
	clock := newMockClock()
	b := NewBreaker("d", BreakerConfig{
		ErrorRateThreshold:    0.5,
		MinRequests:           2,
		OpenDuration:          100 * time.Millisecond,
		HalfOpenProbeInterval: 10 * time.Millisecond,
		Now:                   clock.Now,
	})
	// Trip to Open.
	for i := 0; i < 2; i++ {
		_ = b.Call(context.Background(), func(ctx context.Context) error { return errDepFailed })
	}
	if b.State() != StateOpen {
		t.Fatalf("precondition: not Open")
	}
	// Advance clock past OpenDuration — next call probes.
	clock.Tick(200 * time.Millisecond)
	err := b.Call(context.Background(), func(ctx context.Context) error { return nil })
	if err != nil {
		t.Errorf("probe err = %v, want nil", err)
	}
	if got := b.State(); got != StateClosed {
		t.Errorf("State after successful probe = %v, want Closed", got)
	}
}

func TestBreaker_HalfOpenProbeFailReopens(t *testing.T) {
	clock := newMockClock()
	b := NewBreaker("d", BreakerConfig{
		ErrorRateThreshold:    0.5,
		MinRequests:           2,
		OpenDuration:          100 * time.Millisecond,
		HalfOpenProbeInterval: 10 * time.Millisecond,
		Now:                   clock.Now,
	})
	for i := 0; i < 2; i++ {
		_ = b.Call(context.Background(), func(ctx context.Context) error { return errDepFailed })
	}
	clock.Tick(200 * time.Millisecond)
	err := b.Call(context.Background(), func(ctx context.Context) error { return errDepFailed })
	if !errors.Is(err, errDepFailed) {
		t.Errorf("err = %v, want errDepFailed", err)
	}
	if got := b.State(); got != StateOpen {
		t.Errorf("State after failed probe = %v, want Open", got)
	}
	m := b.Metrics()
	if m.TransitionsOpen < 2 {
		t.Errorf("expected at least 2 Open transitions (initial trip + probe fail); got %d", m.TransitionsOpen)
	}
}

func TestBreaker_HalfOpenLimitsConcurrentProbes(t *testing.T) {
	clock := newMockClock()
	b := NewBreaker("d", BreakerConfig{
		ErrorRateThreshold:    0.5,
		MinRequests:           2,
		OpenDuration:          100 * time.Millisecond,
		HalfOpenProbeInterval: time.Hour, // effectively one probe per test
		Now:                   clock.Now,
	})
	for i := 0; i < 2; i++ {
		_ = b.Call(context.Background(), func(ctx context.Context) error { return errDepFailed })
	}
	clock.Tick(200 * time.Millisecond)
	// First call admitted as the probe (slow). Second concurrent call MUST fast-fail.
	done := make(chan struct{})
	go func() {
		_ = b.Call(context.Background(), func(ctx context.Context) error {
			<-done
			return nil
		})
	}()
	// Give the goroutine time to enter Call + transition to HalfOpen.
	time.Sleep(10 * time.Millisecond)
	err := b.Call(context.Background(), func(ctx context.Context) error {
		t.Error("second concurrent probe should NOT execute fn")
		return nil
	})
	if !errors.Is(err, ErrCircuitOpen) {
		t.Errorf("concurrent probe err = %v, want ErrCircuitOpen", err)
	}
	close(done)
}

func TestBreakerState_String(t *testing.T) {
	if StateClosed.String() != "closed" {
		t.Errorf("Closed.String = %q", StateClosed.String())
	}
	if StateHalfOpen.String() != "half_open" {
		t.Errorf("HalfOpen.String = %q", StateHalfOpen.String())
	}
	if StateOpen.String() != "open" {
		t.Errorf("Open.String = %q", StateOpen.String())
	}
}
