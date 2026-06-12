package resilience

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// BreakerState is the 3-state machine per SR06 §12AI.4.
//
//   - StateClosed:    normal operation. Calls pass through; window tracked.
//   - StateOpen:      calls fast-fail with ErrCircuitOpen; no upstream call.
//   - StateHalfOpen:  limited probe calls. One success → Closed. One failure → Open.
//
// The enum is intentionally an int with a stable order so the integer can
// be exported as the `lw_dependency_circuit_state` gauge (0/1/2 per L7 spec).
type BreakerState int

const (
	StateClosed   BreakerState = 0
	StateHalfOpen BreakerState = 1
	StateOpen     BreakerState = 2
)

// String returns the lowercase wire form used by metrics and the
// dependency_events.event_type column.
func (s BreakerState) String() string {
	switch s {
	case StateClosed:
		return "closed"
	case StateHalfOpen:
		return "half_open"
	case StateOpen:
		return "open"
	}
	return fmt.Sprintf("invalid_breaker_state(%d)", int(s))
}

// ErrCircuitOpen is returned by Call when the breaker is in StateOpen and
// the caller's request was fast-failed.
var ErrCircuitOpen = errors.New("resilience: circuit open")

// BreakerConfig is the per-(caller_service, dep) configuration sourced
// from contracts/dependencies/matrix.yaml.
type BreakerConfig struct {
	// ErrorRateThreshold (0.0–1.0). Above this rate within MinRequests
	// trips Closed → Open. SR06 default 0.25 (25%).
	ErrorRateThreshold float64

	// MinRequests is the minimum sample size before error-rate is
	// statistically meaningful. Below this, the breaker stays Closed
	// regardless of error rate. SR06 default 20.
	MinRequests int

	// OpenDuration is how long the breaker stays Open before allowing
	// a single half-open probe. SR06 default 30s.
	OpenDuration time.Duration

	// HalfOpenProbeInterval bounds the probe rate while in HalfOpen.
	// One probe per interval; concurrent callers fast-fail. Default 1s.
	HalfOpenProbeInterval time.Duration

	// Now is overridable for tests. Production callers leave nil → time.Now.
	Now func() time.Time
}

// BreakerMetrics is the read-only counter view exposed to dashboards +
// `lw_dependency_circuit_state{dep, service}` gauge.
type BreakerMetrics struct {
	State                BreakerState
	WindowedTotal        int
	WindowedFailures     int
	WindowedErrorRate    float64
	TransitionsClosed    int
	TransitionsHalfOpen  int
	TransitionsOpen      int
	LastTransitionAt     time.Time
	FastFailedSinceOpen  int
}

// CircuitBreaker is the canonical breaker contract. Implementations MUST
// be safe for concurrent use across goroutines (callers share one breaker
// per (caller_service, dep) pair per SR06 §12AI.4 fault-domain rule).
type CircuitBreaker interface {
	// Call invokes fn under breaker protection. Returns ErrCircuitOpen if
	// the breaker is Open. Returns fn's error verbatim otherwise.
	Call(ctx context.Context, fn func(context.Context) error) error

	// State is the current state; cheap, suitable for tight-loop reads.
	State() BreakerState

	// Metrics is a snapshot of the windowed counters + transition history.
	Metrics() BreakerMetrics
}

// NewBreaker constructs the default in-memory breaker for depName + cfg.
// depName is recorded for dependency_events emission; the caller is
// responsible for emitting the row on each transition (via the constructor
// in dependency_events.go).
func NewBreaker(depName string, cfg BreakerConfig) CircuitBreaker {
	if cfg.MinRequests <= 0 {
		cfg.MinRequests = 20
	}
	if cfg.OpenDuration <= 0 {
		cfg.OpenDuration = 30 * time.Second
	}
	if cfg.HalfOpenProbeInterval <= 0 {
		cfg.HalfOpenProbeInterval = time.Second
	}
	if cfg.ErrorRateThreshold <= 0 {
		cfg.ErrorRateThreshold = 0.25
	}
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	return &breaker{depName: depName, cfg: cfg}
}

type breaker struct {
	depName string
	cfg     BreakerConfig

	mu                  sync.Mutex
	state               BreakerState
	windowedTotal       int
	windowedFailures    int
	lastTransitionAt    time.Time
	openedAt            time.Time
	lastProbeAt         time.Time
	transitionsClosed   int
	transitionsHalfOpen int
	transitionsOpen     int
	fastFailedSinceOpen int
}

func (b *breaker) State() BreakerState {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.state
}

func (b *breaker) Metrics() BreakerMetrics {
	b.mu.Lock()
	defer b.mu.Unlock()
	rate := 0.0
	if b.windowedTotal > 0 {
		rate = float64(b.windowedFailures) / float64(b.windowedTotal)
	}
	return BreakerMetrics{
		State:               b.state,
		WindowedTotal:       b.windowedTotal,
		WindowedFailures:    b.windowedFailures,
		WindowedErrorRate:   rate,
		TransitionsClosed:   b.transitionsClosed,
		TransitionsHalfOpen: b.transitionsHalfOpen,
		TransitionsOpen:     b.transitionsOpen,
		LastTransitionAt:    b.lastTransitionAt,
		FastFailedSinceOpen: b.fastFailedSinceOpen,
	}
}

// Call routes through the state machine. Probe-call gating + transition
// recording happen under the breaker mutex; the upstream fn is invoked
// OUTSIDE the lock so a slow upstream doesn't serialize all callers.
func (b *breaker) Call(ctx context.Context, fn func(context.Context) error) error {
	gate := b.gate()
	if gate.fastFail {
		return ErrCircuitOpen
	}
	err := fn(ctx)
	b.record(err, gate.isProbe)
	return err
}

type gateDecision struct {
	fastFail bool
	isProbe  bool
}

// gate inspects the current state and decides whether to admit the call.
// In StateOpen, the call is admitted ONLY if the OpenDuration has elapsed
// AND no other probe is currently in flight; that admission transitions
// the state to HalfOpen for the duration of the probe.
func (b *breaker) gate() gateDecision {
	b.mu.Lock()
	defer b.mu.Unlock()
	now := b.cfg.Now()
	switch b.state {
	case StateClosed:
		return gateDecision{}
	case StateOpen:
		if now.Sub(b.openedAt) < b.cfg.OpenDuration {
			b.fastFailedSinceOpen++
			return gateDecision{fastFail: true}
		}
		// Probe window opened. Transition to HalfOpen; this admitted
		// call IS the probe.
		b.transitionTo(StateHalfOpen, now)
		b.lastProbeAt = now
		return gateDecision{isProbe: true}
	case StateHalfOpen:
		// One probe per interval. Concurrent callers fast-fail (rather
		// than queue) so a wedged probe doesn't queue traffic.
		if now.Sub(b.lastProbeAt) < b.cfg.HalfOpenProbeInterval {
			b.fastFailedSinceOpen++
			return gateDecision{fastFail: true}
		}
		b.lastProbeAt = now
		return gateDecision{isProbe: true}
	}
	return gateDecision{}
}

// record processes the fn result and applies any state transition.
//   - Closed:   on enough samples + threshold breach → Open
//   - HalfOpen: probe-success → Closed; probe-failure → Open
//   - Open:     no recording (call was fast-failed)
func (b *breaker) record(callErr error, isProbe bool) {
	b.mu.Lock()
	defer b.mu.Unlock()
	now := b.cfg.Now()
	if isProbe {
		if callErr == nil {
			b.transitionTo(StateClosed, now)
		} else {
			b.transitionTo(StateOpen, now)
			b.openedAt = now
		}
		return
	}
	if b.state == StateOpen {
		// Shouldn't reach here — gate fast-failed. Defensive no-op.
		return
	}
	b.windowedTotal++
	if callErr != nil {
		b.windowedFailures++
	}
	if b.windowedTotal >= b.cfg.MinRequests {
		rate := float64(b.windowedFailures) / float64(b.windowedTotal)
		if rate >= b.cfg.ErrorRateThreshold {
			b.transitionTo(StateOpen, now)
			b.openedAt = now
		}
	}
}

// transitionTo is the only mutator of b.state. It MUST be called with
// b.mu held. Resets the windowed counters on every transition so the
// next window starts fresh.
func (b *breaker) transitionTo(next BreakerState, now time.Time) {
	if b.state == next {
		return
	}
	b.state = next
	b.lastTransitionAt = now
	b.windowedTotal = 0
	b.windowedFailures = 0
	switch next {
	case StateClosed:
		b.transitionsClosed++
		b.fastFailedSinceOpen = 0
	case StateHalfOpen:
		b.transitionsHalfOpen++
	case StateOpen:
		b.transitionsOpen++
		b.fastFailedSinceOpen = 0
	}
}
