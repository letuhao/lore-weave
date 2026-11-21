package ratelimit

import (
	"context"
	"errors"
	"testing"
)

func TestGovernorUnavailableFailsClosedForCappedCalls(t *testing.T) {
	g := NewGovernor(nil, GovernorConfig{})
	if _, err := g.Acquire(context.Background(), context.Background(), "credential", 2); !errors.Is(err, ErrGovernorUnavailable) {
		t.Fatalf("capped Acquire error=%v", err)
	}
	permit, err := g.Acquire(context.Background(), context.Background(), "credential", 0)
	if !errors.Is(err, ErrGovernorUnavailable) || permit != nil {
		t.Fatalf("capped/defaulted calls without Redis must fail closed: permit=%v err=%v", permit, err)
	}
}

type fakeBreaker struct {
	allow       bool
	recordedOK  *bool
	recordCalls int
}

func (f *fakeBreaker) Allow(context.Context, string) (bool, error) { return f.allow, nil }
func (f *fakeBreaker) Record(_ context.Context, _ string, success bool) {
	f.recordCalls++
	v := success
	f.recordedOK = &v
}

type fakeGov struct{ acquired, released int }

func (g *fakeGov) Acquire(_ context.Context, callCtx context.Context, _ string, _ int) (ProviderPermit, error) {
	g.acquired++
	return &fakePermit{ctx: callCtx, released: &g.released}, nil
}

type fakePermit struct {
	ctx      context.Context
	released *int
}

func (p *fakePermit) Context() context.Context { return p.ctx }
func (p *fakePermit) Release()                 { *p.released++ }
func transient(err error) bool                 { return err != nil && err.Error() == "429" }

func TestGuard_NilGovernorRejectsCappedCall(t *testing.T) {
	called := false
	err := Guard(context.Background(), context.Background(), nil, nil, "cred", 3, transient, func(context.Context) error { called = true; return nil })
	if !errors.Is(err, ErrGovernorUnavailable) || called {
		t.Fatalf("err=%v called=%v", err, called)
	}
}
func TestGuard_UncappedPassesThrough(t *testing.T) {
	called := false
	err := Guard(context.Background(), context.Background(), nil, nil, "platform", 0, transient, func(context.Context) error { called = true; return nil })
	if err != nil || !called {
		t.Fatalf("err=%v called=%v", err, called)
	}
}
func TestGuard_OpenBreakerRejects(t *testing.T) {
	brk, gov := &fakeBreaker{allow: false}, &fakeGov{}
	called := false
	err := Guard(context.Background(), context.Background(), gov, brk, "cred", 2, transient, func(context.Context) error { called = true; return nil })
	if !errors.Is(err, ErrCircuitOpen) || called || gov.acquired != 0 {
		t.Fatalf("err=%v called=%v acquired=%d", err, called, gov.acquired)
	}
}
func TestGuard_PassesPermitContextAndReleases(t *testing.T) {
	brk, gov := &fakeBreaker{allow: true}, &fakeGov{}
	var got context.Context
	err := Guard(context.Background(), context.Background(), gov, brk, "cred", 2, transient, func(ctx context.Context) error { got = ctx; return nil })
	if err != nil || got == nil || gov.acquired != 1 || gov.released != 1 || brk.recordedOK == nil || !*brk.recordedOK {
		t.Fatalf("err=%v acquired/released=%d/%d breaker=%v", err, gov.acquired, gov.released, brk.recordedOK)
	}
}
func TestGuard_TransientFailureCountsAndReleases(t *testing.T) {
	brk, gov := &fakeBreaker{allow: true}, &fakeGov{}
	err := Guard(context.Background(), context.Background(), gov, brk, "cred", 2, transient, func(context.Context) error { return errors.New("429") })
	if err == nil || brk.recordedOK == nil || *brk.recordedOK || gov.released != 1 {
		t.Fatalf("err=%v breaker=%v released=%d", err, brk.recordedOK, gov.released)
	}
}
func TestGuard_PermanentErrorDoesNotChangeBreaker(t *testing.T) {
	brk, gov := &fakeBreaker{allow: true}, &fakeGov{}
	err := Guard(context.Background(), context.Background(), gov, brk, "cred", 2, transient, func(context.Context) error { return errors.New("400") })
	if err == nil || brk.recordCalls != 0 || gov.released != 1 {
		t.Fatalf("err=%v calls=%d releases=%d", err, brk.recordCalls, gov.released)
	}
}
