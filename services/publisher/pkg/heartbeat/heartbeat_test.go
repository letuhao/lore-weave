package heartbeat

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/lifecycle"
)

type fakeWriter struct {
	calls       []time.Time
	failOnCalls map[int]bool // 1-based call indexes to fail
	current     int
}

func (w *fakeWriter) WriteHeartbeat(_ context.Context, _, _ string, now time.Time) error {
	w.current++
	w.calls = append(w.calls, now)
	if w.failOnCalls != nil && w.failOnCalls[w.current] {
		return errors.New("simulated meta write failure")
	}
	return nil
}

type frozenClock struct{ t time.Time }

func (c *frozenClock) Now() time.Time { return c.t }

func TestNew_ValidatesArgs(t *testing.T) {
	c := &frozenClock{t: time.Unix(0, 0)}
	w := &fakeWriter{}
	tests := []struct {
		name        string
		publisherID string
		shardHost   string
		writer      Writer
		clock       Clock
	}{
		{"empty_publisher", "", "h1", w, c},
		{"empty_shard", "p1", "", w, c},
		{"nil_writer", "p1", "h1", nil, c},
		{"nil_clock", "p1", "h1", w, nil},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := New(tc.publisherID, tc.shardHost, tc.writer, tc.clock); err == nil {
				t.Error("expected error")
			}
		})
	}
}

func TestTick_HappyPath_KeepsModeFull(t *testing.T) {
	c := &frozenClock{t: time.Unix(1700000000, 0)}
	w := &fakeWriter{}
	l, err := New("p1", "h1", w, c)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		if err := l.Tick(context.Background()); err != nil {
			t.Fatalf("tick %d: %v", i, err)
		}
	}
	if l.Mode() != lifecycle.ModeFull {
		t.Errorf("happy path should keep ModeFull, got %v", l.Mode())
	}
	if l.FailureCount() != 0 {
		t.Errorf("happy path FailureCount should be 0, got %d", l.FailureCount())
	}
	if len(w.calls) != 5 {
		t.Errorf("expected 5 writes, got %d", len(w.calls))
	}
}

func TestTick_DegradesAfterConsecutiveFailures(t *testing.T) {
	c := &frozenClock{t: time.Unix(1700000000, 0)}
	w := &fakeWriter{failOnCalls: map[int]bool{1: true, 2: true, 3: true}}
	l, err := New("p1", "h1", w, c)
	if err != nil {
		t.Fatal(err)
	}
	for i := 1; i <= 3; i++ {
		if err := l.Tick(context.Background()); err == nil {
			t.Fatalf("tick %d: expected error", i)
		}
	}
	if l.Mode() != lifecycle.ModeLimited {
		t.Errorf("3 consecutive failures should flip mode → ModeLimited, got %v", l.Mode())
	}
	if l.FailureCount() != 3 {
		t.Errorf("expected FailureCount=3, got %d", l.FailureCount())
	}
}

func TestTick_RecoversOnSuccess(t *testing.T) {
	c := &frozenClock{t: time.Unix(1700000000, 0)}
	w := &fakeWriter{failOnCalls: map[int]bool{1: true, 2: true, 3: true}}
	l, err := New("p1", "h1", w, c)
	if err != nil {
		t.Fatal(err)
	}
	// Three failures → degraded.
	for i := 1; i <= 3; i++ {
		_ = l.Tick(context.Background())
	}
	if l.Mode() != lifecycle.ModeLimited {
		t.Fatalf("setup: expected ModeLimited, got %v", l.Mode())
	}
	// Fourth tick succeeds.
	if err := l.Tick(context.Background()); err != nil {
		t.Fatalf("recovery tick: %v", err)
	}
	if l.Mode() != lifecycle.ModeFull {
		t.Errorf("recovery should reset mode → ModeFull, got %v", l.Mode())
	}
	if l.FailureCount() != 0 {
		t.Errorf("recovery should reset FailureCount, got %d", l.FailureCount())
	}
}

func TestSetDegradedThreshold_AllowsSingleTickLatch(t *testing.T) {
	c := &frozenClock{t: time.Unix(1700000000, 0)}
	w := &fakeWriter{failOnCalls: map[int]bool{1: true}}
	l, _ := New("p1", "h1", w, c)
	l.SetDegradedThreshold(1)
	_ = l.Tick(context.Background())
	if l.Mode() != lifecycle.ModeLimited {
		t.Errorf("threshold=1 should latch on single failure, got %v", l.Mode())
	}
}

func TestRealClock_ReturnsRecentTime(t *testing.T) {
	got := RealClock{}.Now()
	if time.Since(got) > 5*time.Second {
		t.Errorf("RealClock.Now() returned suspicious %v", got)
	}
}
