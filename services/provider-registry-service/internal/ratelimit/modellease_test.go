package ratelimit

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

// #286 / plan 2026-09-19 T11 — the lease's rules, run through its real Lua script (miniredis
// executes Lua in-process, so this is the script production runs, not a re-implementation).

func newLease(t *testing.T, cfg ModelLeaseConfig) (*ModelLease, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	if cfg.PollInterval == 0 {
		cfg.PollInterval = 10 * time.Millisecond
	}
	return NewModelLease(rdb, cfg), mr
}

const ep = "http://host.docker.internal:1234"

func TestModelLease_SameModelCallsShareTheEndpoint(t *testing.T) {
	l, _ := newLease(t, ModelLeaseConfig{WaitTimeout: 200 * time.Millisecond})
	rel1, err := l.Acquire(context.Background(), ep, "gemma-12b")
	if err != nil {
		t.Fatal(err)
	}
	defer rel1()
	rel2, err := l.Acquire(context.Background(), ep, "gemma-12b")
	if err != nil {
		t.Fatalf("a second call for the SAME model must not wait: %v", err)
	}
	rel2()
}

func TestModelLease_ADifferentModelWaitsUntilTheHolderFinishes(t *testing.T) {
	l, _ := newLease(t, ModelLeaseConfig{WaitTimeout: 2 * time.Second})
	rel12, err := l.Acquire(context.Background(), ep, "gemma-12b")
	if err != nil {
		t.Fatal(err)
	}
	got := make(chan time.Time, 1)
	go func() {
		rel26, err := l.Acquire(context.Background(), ep, "gemma-26b")
		if err == nil {
			got <- time.Now()
			rel26()
		}
	}()
	select {
	case <-got:
		t.Fatal("a call for a DIFFERENT model ran while another model held the endpoint — the collision #286 is about")
	case <-time.After(150 * time.Millisecond):
	}
	released := time.Now()
	rel12()
	select {
	case at := <-got:
		if at.Before(released) {
			t.Fatal("granted before the holder released")
		}
	case <-time.After(time.Second):
		t.Fatal("the waiting model was never granted after the holder released")
	}
}

func TestModelLease_OtherEndpointsDoNotWait(t *testing.T) {
	l, _ := newLease(t, ModelLeaseConfig{WaitTimeout: 100 * time.Millisecond})
	rel, _ := l.Acquire(context.Background(), ep, "gemma-12b")
	defer rel()
	rel2, err := l.Acquire(context.Background(), "http://other-box:1234", "gemma-26b")
	if err != nil {
		t.Fatalf("another endpoint is another GPU: %v", err)
	}
	rel2()
}

func TestModelLease_AgingStopsTheHeldModelFromStarvingAWaiter(t *testing.T) {
	l, _ := newLease(t, ModelLeaseConfig{WaitTimeout: 2 * time.Second, AgingBound: 80 * time.Millisecond})
	relA, _ := l.Acquire(context.Background(), ep, "A")
	var waiterGranted sync.WaitGroup
	waiterGranted.Add(1)
	go func() {
		rel, err := l.Acquire(context.Background(), ep, "B")
		if err == nil {
			waiterGranted.Done()
			rel()
		}
	}()
	time.Sleep(150 * time.Millisecond) // B has now waited past the aging bound
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Millisecond)
	defer cancel()
	if rel, err := l.Acquire(ctx, ep, "A"); err == nil {
		rel()
		t.Fatal("a new call for the held model jumped a waiter that had passed the aging bound")
	}
	relA()
	done := make(chan struct{})
	go func() { waiterGranted.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("the aged waiter was never granted")
	}
}

func TestModelLease_ACrashedHolderFreesItself(t *testing.T) {
	l, mr := newLease(t, ModelLeaseConfig{Lease: 100 * time.Millisecond, WaitTimeout: 2 * time.Second})
	_, _ = l.Acquire(context.Background(), ep, "A") // never released: the caller "crashed"
	mr.FastForward(200 * time.Millisecond)            // redis-side TTLs are not used; scores are wall ms
	time.Sleep(150 * time.Millisecond)
	rel, err := l.Acquire(context.Background(), ep, "B")
	if err != nil {
		t.Fatalf("an expired holder must not wedge the endpoint: %v", err)
	}
	rel()
}

func TestModelLease_TimesOutAsRetryable(t *testing.T) {
	l, _ := newLease(t, ModelLeaseConfig{WaitTimeout: 60 * time.Millisecond})
	rel, _ := l.Acquire(context.Background(), ep, "A")
	defer rel()
	_, err := l.Acquire(context.Background(), ep, "B")
	if !errors.Is(err, ErrModelLeaseTimeout) {
		t.Fatalf("want ErrModelLeaseTimeout, got %v", err)
	}
}

func TestModelLease_FailsOpenWhenRedisIsDown(t *testing.T) {
	l, mr := newLease(t, ModelLeaseConfig{WaitTimeout: 50 * time.Millisecond})
	mr.Close()
	rel, err := l.Acquire(context.Background(), ep, "A")
	if err != nil {
		t.Fatalf("the lease must never become the outage: %v", err)
	}
	rel()
}

func TestNormalizeEndpoint(t *testing.T) {
	cases := map[string]string{
		"http://Host.Docker.Internal:1234/":   "http://host.docker.internal:1234",
		"http://host.docker.internal:1234/v1": "http://host.docker.internal:1234",
		"https://api.example.com":             "https://api.example.com:443",
		"http://127.0.0.1:1234":               "http://127.0.0.1:1234",
	}
	for in, want := range cases {
		if got := NormalizeEndpoint(in); got != want {
			t.Errorf("NormalizeEndpoint(%q) = %q, want %q", in, got, want)
		}
	}
	if NormalizeEndpoint("http://host.docker.internal:1234") == NormalizeEndpoint("http://127.0.0.1:1234") {
		t.Error("aliases must stay distinct: merging is only for the same URL")
	}
}
