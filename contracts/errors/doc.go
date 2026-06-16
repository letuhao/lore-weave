// Package errors — L4.K canonical error taxonomy (SR11 errors module).
//
// # Why a shared taxonomy
//
// Cross-service error reporting needs ONE vocabulary or every consumer
// (turn-outcome writer, alerting, SLO calc) hand-rolls its own. The SR11
// errors module defines 4 classes:
//
//   - UserError       — caller's fault (auth, validation, quota exceeded);
//                       NEVER retryable; never paged.
//   - SystemError     — server-side bug or unexpected state; paged at
//                       threshold; sometimes retryable.
//   - Transient       — known-temporary failure (upstream blip, network);
//                       retry with backoff.
//   - Permanent       — terminal failure (entity dropped, reality archived);
//                       caller surfaces gracefully, never retries.
//
// # Exhaustive — no "Other" catch-all
//
// V1 ships with 28 canonical error CODES grouped by class. New codes
// require an additive enum row + a unit-test assertion in
// `canonical_test.go::TestAllCodesAreExhaustive`. Refusing an "Other" or
// "Unknown" catch-all forces every team to classify their failures into the
// right bucket — which keeps SLO + retry semantics correct.
//
// # Q-IDs honored
//
//   - Q-L4-1 — Rust mirror in crates/dp-kernel/src/turn_errors.rs
//   - SR11 §12AN — turn-outcomes table consumes ErrorEnvelope fields
//
// # What this package ships in cycle 20
//
//   - ErrorClass 4-variant enum
//   - ErrorCode exhaustive enum (28 V1 codes; see canonical.go constant list)
//   - ErrorEnvelope serializable struct (carried in TurnOutcomeRow,
//     api-gateway-bff WS message envelope, etc.)
//   - Helper constructors per class
package errors
