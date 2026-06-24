package resilience

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// ErrBulkheadFull is returned when both the active slots AND the wait
// queue are saturated. The caller fast-fails — never blocks indefinitely.
var ErrBulkheadFull = errors.New("resilience: bulkhead full")

// ErrInvalidBulkheadConfig is returned by NewBulkhead when MaxConcurrent
// or QueueDepth is non-positive. Either is a programmer bug — a zero
// concurrency budget means the dep cannot be called at all.
var ErrInvalidBulkheadConfig = errors.New("resilience: invalid bulkhead config")

// BulkheadConfig is the per-(service, dep) isolation config sourced from
// matrix.yaml. SR06 §12AI.10 default tiers:
//
//	P0: MaxConcurrent=50  QueueDepth=20  QueueTimeout=100ms
//	P1: MaxConcurrent=30  QueueDepth=15  QueueTimeout=200ms
//	P2: MaxConcurrent=10  QueueDepth=5   QueueTimeout=500ms
type BulkheadConfig struct {
	DepName       string
	MaxConcurrent int
	QueueDepth    int
	QueueTimeout  time.Duration
}

// Bulkhead provides per-dep concurrency isolation. Implementations are
// safe for concurrent use across goroutines.
type Bulkhead interface {
	// Call invokes fn while holding a slot. If no slot is immediately
	// available, the caller waits up to QueueTimeout. On expiry → ErrBulkheadFull.
	Call(ctx context.Context, fn func(context.Context) error) error

	// Active returns the current in-flight count. Useful for the
	// `lw_dependency_bulkhead_inflight{dep}` gauge.
	Active() int

	// Rejected returns the cumulative ErrBulkheadFull count since
	// construction. Useful for `lw_dependency_errors_total{error_class="bulkhead_full"}`.
	Rejected() int
}

// NewBulkhead validates the config + constructs the in-memory bulkhead.
// Returns ErrInvalidBulkheadConfig on bad input — the caller is expected
// to fail service bootstrap rather than continue with an unbounded dep.
func NewBulkhead(cfg BulkheadConfig) (Bulkhead, error) {
	if cfg.MaxConcurrent <= 0 {
		return nil, fmt.Errorf("%w: dep=%q MaxConcurrent=%d", ErrInvalidBulkheadConfig, cfg.DepName, cfg.MaxConcurrent)
	}
	if cfg.QueueDepth < 0 {
		return nil, fmt.Errorf("%w: dep=%q QueueDepth=%d", ErrInvalidBulkheadConfig, cfg.DepName, cfg.QueueDepth)
	}
	if cfg.QueueTimeout < 0 {
		return nil, fmt.Errorf("%w: dep=%q QueueTimeout=%v", ErrInvalidBulkheadConfig, cfg.DepName, cfg.QueueTimeout)
	}
	return &bulkhead{
		cfg:    cfg,
		slots:  make(chan struct{}, cfg.MaxConcurrent),
		queued: make(chan struct{}, cfg.QueueDepth),
	}, nil
}

type bulkhead struct {
	cfg    BulkheadConfig
	slots  chan struct{} // buffered; capacity = MaxConcurrent
	queued chan struct{} // buffered; capacity = QueueDepth

	mu       sync.Mutex
	active   int
	rejected int
}

func (b *bulkhead) Active() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.active
}

func (b *bulkhead) Rejected() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.rejected
}

func (b *bulkhead) Call(ctx context.Context, fn func(context.Context) error) error {
	// Two-channel pattern:
	//   1. Try to acquire a slot immediately (fast path: not at capacity)
	//   2. Otherwise enter the queue with a deadline
	//
	// The queue itself is bounded — if QueueDepth slots are also full,
	// the request is rejected synchronously (no second wait).
	select {
	case b.slots <- struct{}{}:
		return b.run(ctx, fn)
	default:
	}
	// Fast path failed — enqueue. If queue is full, reject immediately.
	select {
	case b.queued <- struct{}{}:
	default:
		b.recordRejection()
		return ErrBulkheadFull
	}
	// In the queue. Wait for either a slot or timeout/ctx-cancel.
	timer := time.NewTimer(b.cfg.QueueTimeout)
	defer timer.Stop()
	select {
	case b.slots <- struct{}{}:
		<-b.queued
		return b.run(ctx, fn)
	case <-timer.C:
		<-b.queued
		b.recordRejection()
		return ErrBulkheadFull
	case <-ctx.Done():
		<-b.queued
		return ctx.Err()
	}
}

// run holds the slot for the duration of fn, then releases it on return.
// active/rejected counters are bumped under the mutex.
func (b *bulkhead) run(ctx context.Context, fn func(context.Context) error) error {
	b.mu.Lock()
	b.active++
	b.mu.Unlock()
	defer func() {
		<-b.slots
		b.mu.Lock()
		b.active--
		b.mu.Unlock()
	}()
	return fn(ctx)
}

func (b *bulkhead) recordRejection() {
	b.mu.Lock()
	b.rejected++
	b.mu.Unlock()
}
