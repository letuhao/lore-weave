package jobs

// Phase 6b — job-level transient-retry primitive. One helper, used by the
// streaming, chunked, and media-gen worker paths. See
// docs/03_planning/LLM_PIPELINE_PHASE6B_DESIGN.md.

import (
	"context"
	"log/slog"
	"time"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

const (
	retryBaseS = 1.0  // first-retry backoff, seconds
	retryCapS  = 30.0 // backoff ceiling, seconds
	// retryMaxShiftAttempt guards 1<<attempt against overflow — far past
	// the point retryCapS dominates anyway.
	retryMaxShiftAttempt = 16
)

// retrySleep is the cancellable backoff sleep. A package var so tests can
// swap it for an instant no-op (and still observe ctx cancellation).
var retrySleep = func(ctx context.Context, d time.Duration) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(d):
		return nil
	}
}

// retryBackoff returns the wait before retry `attempt` (0-based): the
// exponential retryBaseS·2^attempt, capped at retryCapS — UNLESS the error
// carries a server Retry-After, which takes precedence.
//
// A server-supplied Retry-After is clamped to retryCapS: the streamable
// worker path runs retryTransient on a context with NO per-job timeout
// (only the media paths wrap one), so an unclamped hint — a misbehaving
// upstream sending `Retry-After: 86400`, or a value large enough to
// overflow the int64-ns conversion to a negative duration — would park the
// worker goroutine for hours with the job stuck `running`. 30s is ample
// backoff for a job retry (/review-impl Phase 6b #1).
func retryBackoff(attempt int, err error) time.Duration {
	if ra := provider.RetryAfter(err); ra > 0 {
		if ra > retryCapS {
			ra = retryCapS
		}
		return time.Duration(ra * float64(time.Second))
	}
	waitS := retryCapS
	if attempt < retryMaxShiftAttempt {
		waitS = retryBaseS * float64(int64(1)<<uint(attempt))
		if waitS > retryCapS {
			waitS = retryCapS
		}
	}
	return time.Duration(waitS * float64(time.Second))
}

// retryTransient runs op, retrying up to maxRetries times on a transient
// upstream error (provider.IsTransientUpstreamError) with exponential
// backoff. A non-transient error returns immediately — no retry. The backoff
// sleep is cancellable via ctx. Returns nil on success, or the last error.
func retryTransient(ctx context.Context, maxRetries int, logger *slog.Logger, op func() error) error {
	for attempt := 0; ; attempt++ {
		err := op()
		if err == nil {
			return nil
		}
		if !provider.IsTransientUpstreamError(err) {
			return err
		}
		if attempt >= maxRetries {
			if logger != nil {
				logger.Warn("transient retry budget exhausted", "err", err, "attempts", attempt+1)
			}
			return err
		}
		wait := retryBackoff(attempt, err)
		if logger != nil {
			logger.Info("transient upstream error — retrying",
				"err", err, "wait", wait, "attempt", attempt+1, "max_retries", maxRetries)
		}
		if serr := retrySleep(ctx, wait); serr != nil {
			return serr
		}
	}
}
