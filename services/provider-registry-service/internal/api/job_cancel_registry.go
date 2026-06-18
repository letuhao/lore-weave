package api

import (
	"context"
	"sync"

	"github.com/google/uuid"
)

// jobCancelRegistry maps an in-flight async LLM job to its worker-goroutine
// CancelFunc so DELETE /v1/llm/jobs/{id} can ABORT the running provider call
// (the governor's Acquire and the streamer's read loop both select on
// ctx.Done()), freeing the concurrency slot the instant cancel is issued —
// not just flipping DB state. This is the Phase-0 fix for the documented
// "Phase 6 worker-context cancellation" gap.
//
// Process-local by design: correct for a single provider-registry replica
// (a cancel always reaches the goroutine in this process). Multi-replica HA
// needs a Redis cancel-flag the streamer/governor poll — tracked in the spec
// (docs/specs/2026-06-11-llm-execution-event-driven-rearchitecture.md §5.1 D2).
//
// The zero value is ready to use.
type jobCancelRegistry struct {
	m sync.Map // uuid.UUID -> context.CancelFunc
}

// register records the job's CancelFunc. Call once at spawn.
func (r *jobCancelRegistry) register(jobID uuid.UUID, cancel context.CancelFunc) {
	r.m.Store(jobID, cancel)
}

// remove drops the entry without cancelling. The worker goroutine defers this
// so a naturally-completed job leaves no stale CancelFunc behind.
func (r *jobCancelRegistry) remove(jobID uuid.UUID) {
	r.m.Delete(jobID)
}

// cancel invokes and removes the job's CancelFunc if present, aborting the
// in-flight goroutine's context. Returns true iff a live goroutine was
// signalled (false = already terminal / never registered / unknown id).
// Safe to race with the worker's defer remove+cancel: LoadAndDelete makes the
// invoke happen at most once, and a CancelFunc is idempotent.
func (r *jobCancelRegistry) cancel(jobID uuid.UUID) bool {
	if v, ok := r.m.LoadAndDelete(jobID); ok {
		v.(context.CancelFunc)()
		return true
	}
	return false
}
