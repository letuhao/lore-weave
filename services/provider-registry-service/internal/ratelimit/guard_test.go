package ratelimit

import (
	"context"
	"errors"
	"testing"
)

// ── Governor: unlimited short-circuit ──────────────────────────────────────

// limit ≤ 0 (a credential with NULL max_concurrency) must pass through WITHOUT
// touching Redis — so an unlimited class is never gated and a nil/unconfigured
// rdb can't panic on the hot path.
func TestGovernor_UnlimitedPassesThroughWithoutRedis(t *testing.T) {
	g := &Governor{} // rdb nil on purpose — unlimited must not dereference it
	for _, lim := range []int{0, -1} {
		release, err := g.Acquire(context.Background(), "cred-abc", lim)
		if err != nil {
			t.Fatalf("unlimited (limit=%d) must not error; got %v", lim, err)
		}
		if release == nil {
			t.Fatalf("release must be non-nil")
		}
		release() // must be safe to call
	}
}

// ── Guard with fakes ───────────────────────────────────────────────────────

type fakeBreaker struct {
	allow       bool
	recordedOK  *bool
	recordCalls int
}

func (f *fakeBreaker) Allow(ctx context.Context, kind string) (bool, error) { return f.allow, nil }
func (f *fakeBreaker) Record(ctx context.Context, kind string, success bool) {
	f.recordCalls++
	v := success
	f.recordedOK = &v
}

type fakeGov struct{ acquired, released int }

func (g *fakeGov) Acquire(ctx context.Context, concClass string, limit int) (func(), error) {
	g.acquired++
	return func() { g.released++ }, nil
}

func transient(err error) bool { return err != nil && err.Error() == "429" }

func TestGuard_NilLayersPassThrough(t *testing.T) {
	called := false
	err := Guard(context.Background(), nil, nil, "openai", 8, transient, func() error {
		called = true
		return nil
	})
	if err != nil || !called {
		t.Fatalf("nil governance must pass through; called=%v err=%v", called, err)
	}
}

func TestGuard_OpenBreakerRejectsWithoutCalling(t *testing.T) {
	brk := &fakeBreaker{allow: false}
	gov := &fakeGov{}
	called := false
	err := Guard(context.Background(), gov, brk, "openai", 8, transient, func() error {
		called = true
		return nil
	})
	if !errors.Is(err, ErrCircuitOpen) {
		t.Fatalf("open breaker must return ErrCircuitOpen; got %v", err)
	}
	if called {
		t.Fatal("provider must NOT be called when circuit is open")
	}
	if gov.acquired != 0 {
		t.Fatal("must not acquire a slot when circuit is open")
	}
}

func TestGuard_SuccessRecordsHealthyAndReleases(t *testing.T) {
	brk := &fakeBreaker{allow: true}
	gov := &fakeGov{}
	err := Guard(context.Background(), gov, brk, "openai", 8, transient, func() error { return nil })
	if err != nil {
		t.Fatalf("unexpected err %v", err)
	}
	if gov.acquired != 1 || gov.released != 1 {
		t.Fatalf("slot must be acquired+released; got %d/%d", gov.acquired, gov.released)
	}
	if brk.recordedOK == nil || !*brk.recordedOK {
		t.Fatal("success must record healthy")
	}
}

func TestGuard_TransientFailureCountsAgainstBreaker(t *testing.T) {
	brk := &fakeBreaker{allow: true}
	gov := &fakeGov{}
	err := Guard(context.Background(), gov, brk, "openai", 8, transient, func() error {
		return errors.New("429")
	})
	if err == nil {
		t.Fatal("error must propagate")
	}
	if brk.recordedOK == nil || *brk.recordedOK {
		t.Fatal("transient failure must record a breaker failure (success=false)")
	}
	if gov.released != 1 {
		t.Fatal("slot must be released even on failure")
	}
}

func TestGuard_PermanentErrorLeavesBreakerUntouched(t *testing.T) {
	brk := &fakeBreaker{allow: true}
	gov := &fakeGov{}
	err := Guard(context.Background(), gov, brk, "openai", 8, transient, func() error {
		return errors.New("400") // not transient
	})
	if err == nil {
		t.Fatal("error must propagate")
	}
	if brk.recordCalls != 0 {
		t.Fatal("a permanent (non-transient) error must NOT touch the breaker")
	}
	if gov.released != 1 {
		t.Fatal("slot must be released")
	}
}
