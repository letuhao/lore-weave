// Package meta — degraded-mode fallback buffer.
//
// L1.J.1 (cycle 7) — companion to L1.E meta HA + L1.J degraded mode.
//
// When the meta primary (and all sync replicas) become unreachable, services
// SHOULD NOT block on writes. Instead they switch to "Limited" service mode
// (contracts/lifecycle/service_mode.go) and write into the FallbackBuffer.
// On recovery, mode_propagation flips Limited→Full and the buffer flushes
// (in FIFO order) through MetaWrite() as if the writes were freshly issued.
//
// Invariants:
//   1. **Bounded.** Buffer is hard-capped at 10000 entries. Past the cap,
//      Append() returns ErrBufferFull and the caller MUST surface the failure
//      to the requesting client (or drop with a metric).
//   2. **FIFO.** Flush emits entries in append order. Same-resource updates
//      preserve their relative order so the resulting state is causally
//      consistent.
//   3. **Idempotent flush.** Each entry carries the same MetaWriteIntent shape
//      the original MetaWrite() would have seen, including ExpectedBefore
//      (CAS guard). If the buffered intent loses the race on flush (another
//      writer succeeded in the gap), it is recorded as a flush-conflict
//      rather than retried.
//   4. **No silent loss.** Drop on full is a separate code path with its own
//      counter; never falls through to a no-op return.
//   5. **Per-process.** The buffer lives in-process; a process restart loses
//      buffered writes by design (caller is expected to be in Limited mode and
//      have surfaced provisional state to the user already).
//
// This is intentionally a small surface — the service-specific buffer/flush
// (services/<name>/internal/buffer_flush/) wraps this with domain knowledge.
package meta

import (
	"context"
	"errors"
	"sync"
)

// DefaultBufferCap is the hard ceiling on a FallbackBuffer. Per Q-L1J-1 (shared
// Redis control channel) + L1.J §8 acceptance ("bounded at 10K").
const DefaultBufferCap = 10000

// ErrBufferFull is returned by Append when the buffer is at DefaultBufferCap.
// Callers MUST handle (surface to client, record metric); never swallow.
var ErrBufferFull = errors.New("meta: fallback buffer full")

// ErrBufferDisabled is returned by Append/Flush when the buffer was created
// with cap=0 (disabled by config — fail-fast mode for canary deploys).
var ErrBufferDisabled = errors.New("meta: fallback buffer disabled")

// BufferedIntent is a single deferred MetaWrite() captured during a meta
// outage. Mirrors MetaWriteIntent + adds enqueue metadata for forensic replay.
type BufferedIntent struct {
	Intent          MetaWriteIntent
	EnqueuedAtNanos int64
	OriginActor     Actor
}

// FlushResult is the per-flush outcome.
type FlushResult struct {
	Attempted     int
	Succeeded     int
	Conflicts     int // CAS conflict on flush (another writer won)
	Errors        int // non-conflict errors (RPC/network/db)
	DroppedOnFull int // not counted in Attempted; captured at Append time
}

// FlushExecutor is the dependency FallbackBuffer.Flush calls per intent.
// Production binds it to MetaWrite(ctx, cfg, intent); tests stub.
type FlushExecutor interface {
	Execute(ctx context.Context, intent MetaWriteIntent) error
}

// FlushExecutorFunc is an adapter so a plain func satisfies FlushExecutor.
type FlushExecutorFunc func(ctx context.Context, intent MetaWriteIntent) error

// Execute implements FlushExecutor.
func (f FlushExecutorFunc) Execute(ctx context.Context, intent MetaWriteIntent) error {
	return f(ctx, intent)
}

// FallbackBuffer is the in-process degraded-mode write buffer. Safe for
// concurrent use. A buffer with cap==0 is "disabled" (every Append returns
// ErrBufferDisabled) — used by canary deploys that prefer fail-fast.
type FallbackBuffer struct {
	mu            sync.Mutex
	cap           int
	entries       []BufferedIntent
	droppedOnFull int
}

// NewFallbackBuffer constructs a bounded buffer. cap <= 0 disables the buffer
// (Append returns ErrBufferDisabled).
func NewFallbackBuffer(cap int) *FallbackBuffer {
	if cap < 0 {
		cap = 0
	}
	return &FallbackBuffer{cap: cap, entries: make([]BufferedIntent, 0, cap)}
}

// Append enqueues a write intent. Returns ErrBufferFull if at cap (and
// increments the dropped counter). Returns ErrBufferDisabled if cap==0.
func (b *FallbackBuffer) Append(now int64, actor Actor, intent MetaWriteIntent) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.cap == 0 {
		b.droppedOnFull++
		return ErrBufferDisabled
	}
	if len(b.entries) >= b.cap {
		b.droppedOnFull++
		return ErrBufferFull
	}
	b.entries = append(b.entries, BufferedIntent{
		Intent:          intent,
		EnqueuedAtNanos: now,
		OriginActor:     actor,
	})
	return nil
}

// Len returns the current buffered-intent count (for metrics + tests).
func (b *FallbackBuffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.entries)
}

// Cap returns the configured buffer cap.
func (b *FallbackBuffer) Cap() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.cap
}

// DroppedOnFull returns the cumulative count of writes rejected due to a full
// (or disabled) buffer.
func (b *FallbackBuffer) DroppedOnFull() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.droppedOnFull
}

// Snapshot returns a copy of the current buffer (for forensic inspection).
// Mutating the result has no effect on the buffer.
func (b *FallbackBuffer) Snapshot() []BufferedIntent {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := make([]BufferedIntent, len(b.entries))
	copy(out, b.entries)
	return out
}

// Flush drains the buffer in FIFO order through the executor. Per
// invariant 3 (idempotent flush) the executor is expected to surface CAS
// conflicts as ErrConcurrentStateTransition; FallbackBuffer counts those
// separately so the SRE dashboard distinguishes "another writer won" from
// "system failure".
//
// On any error other than ErrConcurrentStateTransition, Flush STOPS and
// re-enqueues the unprocessed tail so partial-flush state is preserved.
// CAS-conflict entries are NOT re-enqueued (the conflict resolves toward
// the winning writer; replaying would re-conflict forever).
//
// Flush is safe to call concurrently with Append (Append-after-Flush-start
// is processed in the NEXT Flush call).
func (b *FallbackBuffer) Flush(ctx context.Context, exec FlushExecutor) FlushResult {
	b.mu.Lock()
	if b.cap == 0 {
		b.mu.Unlock()
		return FlushResult{DroppedOnFull: b.droppedOnFull}
	}
	if len(b.entries) == 0 {
		b.mu.Unlock()
		return FlushResult{DroppedOnFull: b.droppedOnFull}
	}
	// Snapshot + clear in one critical section so Append-during-Flush goes to
	// a fresh buffer rather than being silently re-flushed.
	drain := b.entries
	b.entries = make([]BufferedIntent, 0, b.cap)
	droppedSnap := b.droppedOnFull
	b.mu.Unlock()

	res := FlushResult{DroppedOnFull: droppedSnap, Attempted: len(drain)}
	for i, e := range drain {
		if err := exec.Execute(ctx, e.Intent); err != nil {
			if errors.Is(err, ErrConcurrentStateTransition) {
				res.Conflicts++
				continue
			}
			// Hard error: re-enqueue the unprocessed tail (i..end) so a
			// subsequent Flush can retry. Honors invariant: no silent loss.
			res.Errors++
			b.mu.Lock()
			// Prepend the unprocessed tail in front of any new appends.
			tail := drain[i:]
			merged := make([]BufferedIntent, 0, len(tail)+len(b.entries))
			merged = append(merged, tail...)
			merged = append(merged, b.entries...)
			// Re-cap: drop excess at the tail (oldest unflushed first wins).
			if len(merged) > b.cap {
				dropped := len(merged) - b.cap
				merged = merged[:b.cap]
				b.droppedOnFull += dropped
			}
			b.entries = merged
			b.mu.Unlock()
			return res
		}
		res.Succeeded++
	}
	return res
}
