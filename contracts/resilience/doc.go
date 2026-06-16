// Package resilience holds the canonical resilience primitives for every
// LoreWeave outbound dependency call: timeout, circuit breaker, retry,
// bulkhead. Owned by the platform team.
//
// Cycle 18 (L4.F) ships:
//   - timeout.go            — WithTimeout wrapper (SR06 I16 enforcement point)
//   - breaker.go            — 3-state circuit breaker (closed | half_open | open)
//   - retry.go              — exponential backoff with ±25% jitter, Retry-After aware
//   - bulkhead.go           — per-(service, dep) concurrency + queue isolation
//   - dependency_events.go  — typed audit-row constructors for state transitions
//
// The Rust mirror lives in `crates/dp-kernel::resilience` per Q-L4-1 (Go +
// Rust runtime types, no Python in this cycle). Library invariants:
//
//   - Q-L4-1: Go primary; Rust mirror; Python deferred to cycle-19+.
//   - SR06 I16: every outbound call routes through WithTimeout.
//   - SR06 §12AI.4: one breaker per (caller_service, dep) — never shared.
//   - SR06 §12AI.5: retry policy differentiates idempotent vs non-idempotent.
//   - SR06 §12AI.10: bulkhead overflow returns ErrBulkheadFull, never blocks.
//
// dependency_events row writes are emitted via MetaWrite (I8) by the caller;
// this package only provides the typed constructors.
package resilience
