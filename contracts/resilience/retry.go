package resilience

import (
	"context"
	"errors"
	"fmt"
	"math/rand"
	"time"
)

// RetryClass differentiates idempotent from non-idempotent calls per
// SR06 §12AI.5. Non-idempotent calls MUST NOT retry without an idempotency
// key (otherwise double-write risk under "request reached server but
// response was lost" failure mode).
type RetryClass int

const (
	// RetryClassIdempotent — GET, read-only RPC, Redis read. SR06 default 3
	// retries, exp backoff 100ms × 2^n ± 25% jitter, 10s total budget.
	RetryClassIdempotent RetryClass = 1

	// RetryClassNonIdempotent — POST without idempotency key, LLM call with
	// side-effects. SR06 default 0 retries (one attempt; fail fast).
	RetryClassNonIdempotent RetryClass = 2

	// RetryClassCriticalWrite — cost ledger, audit, canon entries. SR06
	// default 2 retries, exp + 5s cap, 15s total budget. Caller MUST supply
	// an idempotency key (enforced by callsite, not this library).
	RetryClassCriticalWrite RetryClass = 3
)

// RetryPolicy is the per-call retry configuration. Construct via the
// DefaultRetryPolicy helper or build manually. All durations are positive
// or RetryWithBackoff returns ErrInvalidRetryPolicy synchronously.
type RetryPolicy struct {
	Class         RetryClass
	MaxAttempts   int           // INCLUDES the first attempt. 1 = no retry.
	BaseBackoff   time.Duration // n-th retry waits BaseBackoff * 2^(n-1) ± jitter
	MaxBackoff    time.Duration // hard cap on per-iteration wait
	TotalBudget   time.Duration // wall-clock cap across all attempts
	JitterPercent float64       // ±this fraction of computed backoff. 0.25 = ±25%.

	// IsRetryable decides whether a failure should trigger another attempt.
	// nil → all non-nil errors are retryable (idempotent default). Callers
	// supplying explicit retry-only-on-5xx logic override here.
	IsRetryable func(error) bool

	// RetryAfter inspects the error for an upstream Retry-After hint. If
	// non-zero, the returned duration is used instead of computed backoff
	// (still capped at MaxBackoff + TotalBudget). nil → ignore.
	RetryAfter func(error) (time.Duration, bool)

	// Sleep is overridable for tests (avoids 30-second sleeps in unit
	// tests). Production callers leave nil → time.Sleep.
	Sleep func(time.Duration)

	// Now is overridable for tests; production = time.Now.
	Now func() time.Time

	// rng is overridable for tests; production = packaged rand source.
	rng func() float64
}

// ErrInvalidRetryPolicy is returned by RetryWithBackoff when the policy
// fields are inconsistent (negative durations, MaxAttempts < 1, etc.).
var ErrInvalidRetryPolicy = errors.New("resilience: invalid retry policy")

// ErrRetryBudgetExhausted wraps the LAST error after exhausting the retry
// budget (max attempts OR total wall-clock budget). errors.Unwrap recovers
// the underlying error so callers can `errors.Is(err, ErrCircuitOpen)`.
var ErrRetryBudgetExhausted = errors.New("resilience: retry budget exhausted")

// DefaultRetryPolicy returns the SR06 §12AI.5 default for the given class.
// Returns ErrInvalidRetryPolicy for unknown classes.
func DefaultRetryPolicy(class RetryClass) (RetryPolicy, error) {
	switch class {
	case RetryClassIdempotent:
		return RetryPolicy{
			Class:         class,
			MaxAttempts:   4, // 1 initial + 3 retries
			BaseBackoff:   100 * time.Millisecond,
			MaxBackoff:    5 * time.Second,
			TotalBudget:   10 * time.Second,
			JitterPercent: 0.25,
		}, nil
	case RetryClassNonIdempotent:
		return RetryPolicy{
			Class:         class,
			MaxAttempts:   1, // no retry
			BaseBackoff:   0,
			MaxBackoff:    0,
			TotalBudget:   0,
			JitterPercent: 0,
		}, nil
	case RetryClassCriticalWrite:
		return RetryPolicy{
			Class:         class,
			MaxAttempts:   3, // 1 initial + 2 retries
			BaseBackoff:   100 * time.Millisecond,
			MaxBackoff:    5 * time.Second,
			TotalBudget:   15 * time.Second,
			JitterPercent: 0.25,
		}, nil
	}
	return RetryPolicy{}, fmt.Errorf("%w: unknown class %d", ErrInvalidRetryPolicy, class)
}

// RetryWithBackoff invokes fn under the given retry policy. The returned
// error is either:
//
//   - nil — fn succeeded on some attempt;
//   - fn's last error verbatim — fn failed but IsRetryable returned false
//     (caller can inspect with errors.Is/As without wrapping noise);
//   - %w-wrapped ErrRetryBudgetExhausted — attempts or wall-clock budget
//     exhausted; errors.Unwrap returns the last attempt's error.
//
// ctx.Done() short-circuits at the next sleep boundary; in-flight fn is
// NOT cancelled by this wrapper (fn is responsible for honoring its own
// ctx). The returned error in that case is the in-flight error or ctx.Err.
func RetryWithBackoff(ctx context.Context, p RetryPolicy, fn func(context.Context) error) error {
	if err := p.validate(); err != nil {
		return err
	}
	p.fillDefaults()
	start := p.Now()
	var lastErr error
	for attempt := 1; attempt <= p.MaxAttempts; attempt++ {
		if err := ctx.Err(); err != nil {
			return err
		}
		err := fn(ctx)
		if err == nil {
			return nil
		}
		lastErr = err
		// Non-retryable → return immediately without wrapping.
		if p.IsRetryable != nil && !p.IsRetryable(err) {
			return err
		}
		// Last attempt — no more sleeps.
		if attempt == p.MaxAttempts {
			break
		}
		wait := p.computeBackoff(attempt, err)
		// Budget exhaustion check BEFORE the sleep so we don't overshoot.
		if p.TotalBudget > 0 && p.Now().Add(wait).Sub(start) > p.TotalBudget {
			break
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-after(p.Sleep, wait):
		}
	}
	if lastErr == nil {
		// MaxAttempts == 0 (caller bug; validate() catches but defensive).
		return ErrRetryBudgetExhausted
	}
	return fmt.Errorf("%w: last=%w", ErrRetryBudgetExhausted, lastErr)
}

// after returns a channel that fires after d. We use the configurable
// Sleep so tests can fast-forward time without actually waiting.
func after(sleep func(time.Duration), d time.Duration) <-chan struct{} {
	ch := make(chan struct{}, 1)
	go func() {
		sleep(d)
		ch <- struct{}{}
	}()
	return ch
}

func (p RetryPolicy) validate() error {
	if p.MaxAttempts < 1 {
		return fmt.Errorf("%w: MaxAttempts=%d must be >= 1", ErrInvalidRetryPolicy, p.MaxAttempts)
	}
	if p.MaxAttempts > 1 {
		if p.BaseBackoff <= 0 {
			return fmt.Errorf("%w: BaseBackoff must be > 0 when MaxAttempts > 1", ErrInvalidRetryPolicy)
		}
		if p.JitterPercent < 0 || p.JitterPercent > 1 {
			return fmt.Errorf("%w: JitterPercent must be in [0, 1]; got %v", ErrInvalidRetryPolicy, p.JitterPercent)
		}
	}
	return nil
}

func (p *RetryPolicy) fillDefaults() {
	if p.Sleep == nil {
		p.Sleep = time.Sleep
	}
	if p.Now == nil {
		p.Now = time.Now
	}
	if p.rng == nil {
		// math/rand: not cryptographic, but jitter doesn't need CSPRNG.
		// We seed with a fresh source per policy use; the source is not
		// shared across goroutines.
		src := rand.New(rand.NewSource(p.Now().UnixNano()))
		p.rng = src.Float64
	}
}

// computeBackoff returns the wait duration before attempt N (1-indexed
// AFTER the failed attempt; the FIRST retry sleeps BaseBackoff ± jitter).
// Honors Retry-After hint if RetryAfter is set and returns (d, true).
func (p RetryPolicy) computeBackoff(attempt int, lastErr error) time.Duration {
	if p.RetryAfter != nil {
		if d, ok := p.RetryAfter(lastErr); ok && d > 0 {
			return clamp(d, p.MaxBackoff)
		}
	}
	// attempt is 1-indexed FOR THE FAILED CALL. The first sleep happens
	// AFTER attempt=1 and BEFORE attempt=2, so the exponent is (attempt-1).
	base := p.BaseBackoff << (attempt - 1)
	// Jitter: ±JitterPercent. JitterPercent=0.25 → multiply by [0.75, 1.25].
	jitter := 1.0 + (p.rng()*2-1)*p.JitterPercent
	wait := time.Duration(float64(base) * jitter)
	return clamp(wait, p.MaxBackoff)
}

func clamp(d, cap time.Duration) time.Duration {
	if cap > 0 && d > cap {
		return cap
	}
	if d < 0 {
		return 0
	}
	return d
}
