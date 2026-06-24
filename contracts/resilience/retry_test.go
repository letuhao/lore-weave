package resilience

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"
)

var errTransient = errors.New("transient")

func newDeterministicPolicy(maxAttempts int) RetryPolicy {
	p := RetryPolicy{
		Class:         RetryClassIdempotent,
		MaxAttempts:   maxAttempts,
		BaseBackoff:   time.Millisecond,
		MaxBackoff:    10 * time.Millisecond,
		TotalBudget:   time.Second,
		JitterPercent: 0, // deterministic
		Sleep:         func(d time.Duration) {},
		Now:           time.Now,
	}
	return p
}

func TestDefaultRetryPolicy(t *testing.T) {
	cases := []struct {
		class    RetryClass
		attempts int
	}{
		{RetryClassIdempotent, 4},
		{RetryClassNonIdempotent, 1},
		{RetryClassCriticalWrite, 3},
	}
	for _, c := range cases {
		p, err := DefaultRetryPolicy(c.class)
		if err != nil {
			t.Errorf("class=%v err=%v", c.class, err)
			continue
		}
		if p.MaxAttempts != c.attempts {
			t.Errorf("class=%v MaxAttempts=%d, want %d", c.class, p.MaxAttempts, c.attempts)
		}
	}
	_, err := DefaultRetryPolicy(RetryClass(999))
	if !errors.Is(err, ErrInvalidRetryPolicy) {
		t.Errorf("unknown class err = %v, want ErrInvalidRetryPolicy", err)
	}
}

func TestRetry_SucceedsOnFirstAttempt(t *testing.T) {
	p := newDeterministicPolicy(3)
	var calls int32
	err := RetryWithBackoff(context.Background(), p, func(ctx context.Context) error {
		atomic.AddInt32(&calls, 1)
		return nil
	})
	if err != nil {
		t.Errorf("err = %v, want nil", err)
	}
	if calls != 1 {
		t.Errorf("calls = %d, want 1", calls)
	}
}

func TestRetry_RetriesThenSucceeds(t *testing.T) {
	p := newDeterministicPolicy(3)
	var calls int32
	err := RetryWithBackoff(context.Background(), p, func(ctx context.Context) error {
		n := atomic.AddInt32(&calls, 1)
		if n < 2 {
			return errTransient
		}
		return nil
	})
	if err != nil {
		t.Errorf("err = %v, want nil", err)
	}
	if calls != 2 {
		t.Errorf("calls = %d, want 2", calls)
	}
}

func TestRetry_BudgetExhausted(t *testing.T) {
	p := newDeterministicPolicy(3)
	var calls int32
	err := RetryWithBackoff(context.Background(), p, func(ctx context.Context) error {
		atomic.AddInt32(&calls, 1)
		return errTransient
	})
	if !errors.Is(err, ErrRetryBudgetExhausted) {
		t.Errorf("err = %v, want ErrRetryBudgetExhausted wrapper", err)
	}
	if !errors.Is(err, errTransient) {
		t.Errorf("err = %v should ALSO be errTransient (wrapped)", err)
	}
	if calls != 3 {
		t.Errorf("calls = %d, want 3 (MaxAttempts)", calls)
	}
}

func TestRetry_NonRetryableShortCircuits(t *testing.T) {
	p := newDeterministicPolicy(5)
	notRetryable := errors.New("permanent")
	p.IsRetryable = func(err error) bool { return !errors.Is(err, notRetryable) }
	var calls int32
	err := RetryWithBackoff(context.Background(), p, func(ctx context.Context) error {
		atomic.AddInt32(&calls, 1)
		return notRetryable
	})
	if !errors.Is(err, notRetryable) {
		t.Errorf("err = %v, want notRetryable verbatim", err)
	}
	if errors.Is(err, ErrRetryBudgetExhausted) {
		t.Errorf("non-retryable should NOT wrap in ErrRetryBudgetExhausted")
	}
	if calls != 1 {
		t.Errorf("calls = %d, want 1", calls)
	}
}

func TestRetry_RetryAfterHint(t *testing.T) {
	p := newDeterministicPolicy(2)
	hintUsed := false
	p.RetryAfter = func(err error) (time.Duration, bool) {
		hintUsed = true
		return 5 * time.Millisecond, true
	}
	_ = RetryWithBackoff(context.Background(), p, func(ctx context.Context) error { return errTransient })
	if !hintUsed {
		t.Errorf("RetryAfter hint should have been consulted")
	}
}

func TestRetry_ContextCancelStops(t *testing.T) {
	p := newDeterministicPolicy(10)
	// Make sleeps actually wait so the cancel beats them.
	p.Sleep = time.Sleep
	p.BaseBackoff = 50 * time.Millisecond
	ctx, cancel := context.WithCancel(context.Background())
	var calls int32
	go func() {
		time.Sleep(5 * time.Millisecond)
		cancel()
	}()
	err := RetryWithBackoff(ctx, p, func(ctx context.Context) error {
		atomic.AddInt32(&calls, 1)
		return errTransient
	})
	if !errors.Is(err, context.Canceled) {
		t.Errorf("err = %v, want context.Canceled", err)
	}
}

func TestRetry_InvalidPolicy(t *testing.T) {
	cases := []RetryPolicy{
		{MaxAttempts: 0},  // < 1
		{MaxAttempts: -1}, // negative
		// Retry-eligible but BaseBackoff missing.
		{MaxAttempts: 3, BaseBackoff: 0, JitterPercent: 0.25},
		// JitterPercent out-of-range.
		{MaxAttempts: 3, BaseBackoff: time.Millisecond, JitterPercent: 2.0},
	}
	for _, p := range cases {
		err := RetryWithBackoff(context.Background(), p, func(ctx context.Context) error { return nil })
		if !errors.Is(err, ErrInvalidRetryPolicy) {
			t.Errorf("policy=%+v err = %v, want ErrInvalidRetryPolicy", p, err)
		}
	}
}
