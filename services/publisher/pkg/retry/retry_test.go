package retry

import (
	"errors"
	"testing"
	"time"
)

func TestDefaultPolicy_Sensible(t *testing.T) {
	p := DefaultPolicy()
	if err := p.Validate(); err != nil {
		t.Fatalf("DefaultPolicy must validate: %v", err)
	}
	if p.MaxAttempts < 5 {
		t.Errorf("MaxAttempts=%d too aggressive; should give at least 5 retries", p.MaxAttempts)
	}
}

func TestClassify_HappyPath_MarksPublished(t *testing.T) {
	if got := Classify(DefaultPolicy(), 0, nil); got != MarkPublished {
		t.Errorf("nil err should mark_published, got %v", got)
	}
}

func TestClassify_TransientErrSchedulesRetry(t *testing.T) {
	if got := Classify(DefaultPolicy(), 0, errors.New("conn reset")); got != Retry {
		t.Errorf("first failure should retry, got %v", got)
	}
}

func TestClassify_DeadLettersAtMaxAttempts(t *testing.T) {
	p := DefaultPolicy()
	// currentAttempts = p.MaxAttempts - 1 means next attempt would be
	// MaxAttempts → DeadLetter.
	if got := Classify(p, p.MaxAttempts-1, errors.New("boom")); got != DeadLetter {
		t.Errorf("attempts reaching MaxAttempts must dead-letter, got %v", got)
	}
	// Beyond MaxAttempts: still DeadLetter.
	if got := Classify(p, p.MaxAttempts+5, errors.New("boom")); got != DeadLetter {
		t.Errorf("attempts beyond MaxAttempts must dead-letter, got %v", got)
	}
}

func TestBackoffFor_GrowsExponentially(t *testing.T) {
	p := Policy{MaxAttempts: 10, BaseBackoff: 100 * time.Millisecond, MaxBackoff: 60 * time.Second}
	tests := []struct {
		attempts int
		want     time.Duration
	}{
		{1, 100 * time.Millisecond},
		{2, 200 * time.Millisecond},
		{3, 400 * time.Millisecond},
		{4, 800 * time.Millisecond},
	}
	for _, tc := range tests {
		got := BackoffFor(p, tc.attempts)
		if got != tc.want {
			t.Errorf("BackoffFor(%d) = %v; want %v", tc.attempts, got, tc.want)
		}
	}
}

func TestBackoffFor_CappedAtMaxBackoff(t *testing.T) {
	p := Policy{MaxAttempts: 20, BaseBackoff: 100 * time.Millisecond, MaxBackoff: 1 * time.Second}
	// attempt 20 would be 100ms × 2^19 = 52428800ms = 14h without a cap.
	got := BackoffFor(p, 20)
	if got != p.MaxBackoff {
		t.Errorf("BackoffFor must cap at MaxBackoff=%v, got %v", p.MaxBackoff, got)
	}
}

func TestBackoffFor_NeverTightLoops(t *testing.T) {
	// Anti-regression: BackoffFor must NEVER return <= 0 for ANY attempt.
	// This prevents the publisher loop from busy-spinning on persistent
	// failure (adversary review focus).
	p := DefaultPolicy()
	for attempts := 1; attempts <= p.MaxAttempts+5; attempts++ {
		if got := BackoffFor(p, attempts); got <= 0 {
			t.Errorf("BackoffFor(%d) = %v MUST be > 0 — tight-loop risk", attempts, got)
		}
	}
}

func TestPolicy_ValidateCatchesBadConfig(t *testing.T) {
	tests := []struct {
		name string
		p    Policy
	}{
		{"max_attempts_zero", Policy{MaxAttempts: 0, BaseBackoff: 1 * time.Second, MaxBackoff: 1 * time.Second}},
		{"base_zero", Policy{MaxAttempts: 5, BaseBackoff: 0, MaxBackoff: 1 * time.Second}},
		{"max_below_base", Policy{MaxAttempts: 5, BaseBackoff: 5 * time.Second, MaxBackoff: 1 * time.Second}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if err := tc.p.Validate(); err == nil {
				t.Errorf("expected ErrInvalidPolicy on %+v", tc.p)
			}
		})
	}
}

func TestDecision_String(t *testing.T) {
	cases := []struct {
		d    Decision
		want string
	}{
		{MarkPublished, "mark_published"},
		{Retry, "retry"},
		{DeadLetter, "dead_letter"},
	}
	for _, tc := range cases {
		if tc.d.String() != tc.want {
			t.Errorf("Decision %d String=%q want %q", tc.d, tc.d.String(), tc.want)
		}
	}
}
