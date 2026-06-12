package resilience

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestWithTimeout_AppliesPerDepDeadline(t *testing.T) {
	called := false
	err := WithTimeout(context.Background(), "test-dep", 10*time.Millisecond, func(ctx context.Context) error {
		called = true
		dl, ok := ctx.Deadline()
		if !ok {
			t.Errorf("inner ctx should carry a deadline")
		}
		if time.Until(dl) > 10*time.Millisecond {
			t.Errorf("inner deadline = %v, want <= 10ms", time.Until(dl))
		}
		return nil
	})
	if !called {
		t.Fatal("fn was never invoked")
	}
	if err != nil {
		t.Errorf("err = %v, want nil", err)
	}
}

func TestWithTimeout_RejectsNonPositiveTimeout(t *testing.T) {
	for _, bad := range []time.Duration{0, -1, -time.Second} {
		called := false
		err := WithTimeout(context.Background(), "d", bad, func(ctx context.Context) error {
			called = true
			return nil
		})
		if !errors.Is(err, ErrInvalidTimeout) {
			t.Errorf("timeout=%v err = %v, want ErrInvalidTimeout", bad, err)
		}
		if called {
			t.Errorf("timeout=%v: fn should NOT be invoked", bad)
		}
	}
}

func TestWithTimeout_RejectsNilParent(t *testing.T) {
	// nolint - intentionally passing nil ctx to exercise the defensive path
	err := WithTimeout(nil, "d", time.Second, func(ctx context.Context) error { return nil })
	if !errors.Is(err, ErrInvalidTimeout) {
		t.Errorf("nil parent err = %v, want ErrInvalidTimeout", err)
	}
}

func TestWithTimeout_RespectsTighterParentDeadline(t *testing.T) {
	parent, cancel := context.WithTimeout(context.Background(), 5*time.Millisecond)
	defer cancel()
	// Per-dep timeout is 1s; tighter parent caps at 5ms.
	err := WithTimeout(parent, "d", time.Second, func(ctx context.Context) error {
		dl, _ := ctx.Deadline()
		if time.Until(dl) > 5*time.Millisecond {
			t.Errorf("expected deadline <=5ms; got %v", time.Until(dl))
		}
		return nil
	})
	if err != nil {
		t.Errorf("err = %v, want nil", err)
	}
}

func TestDeadlineRemaining(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	rem, ok := DeadlineRemaining(ctx)
	if !ok {
		t.Fatal("expected deadline present")
	}
	if rem <= 0 || rem > 100*time.Millisecond {
		t.Errorf("remaining = %v, want in (0, 100ms]", rem)
	}

	_, ok = DeadlineRemaining(context.Background())
	if ok {
		t.Errorf("background ctx should have no deadline")
	}
}
