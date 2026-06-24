// Package turn — L4.K shared-kernel turn-lifecycle contract (SR11 §12AN).
//
// # Why this exists
//
// Turn UX reliability (SR11) is a cross-service concern: a "turn" begins with
// user input at the gateway, runs through chat-service + knowledge-service +
// world-service, and completes (or fails) via a TurnState machine. If each
// service defines its own state vocabulary, alerting / observability /
// retries become inconsistent. We ship ONE TurnState enum + TurnContext
// envelope here that EVERY participating service consumes.
//
// # The 8-state vocabulary (SR11)
//
//   1. Pending      — turn accepted, queued
//   2. Validating   — preflight (auth, quota, capacity admission)
//   3. Routing      — selecting downstream service / model
//   4. Executing    — LLM call / projection write in flight
//   5. Streaming    — partial response visible to user
//   6. Completed    — terminal success
//   7. Failed       — terminal failure (see ErrorEnvelope for class)
//   8. Cancelled    — user-initiated abort (or upstream timeout)
//
// # Q-IDs honored
//
//   - Q-L4-1 — Rust mirror in crates/dp-kernel/src/turn.rs
//   - Cycle-18 lifecycle integration — turn_end MUST flush before drain
//     completes (FlushOutbox step). See turn_lifecycle_hook.go.
//
// # turn_outcomes audit table
//
// Every terminal transition (Completed / Failed / Cancelled) writes one row
// into the meta-side `turn_outcomes` table. The writer is decoupled from the
// state machine so a service can batch terminal events under load.
//
// # What this package ships in cycle 20
//
//   - TurnState 8-variant enum + validation
//   - TurnContext envelope (versioned)
//   - TurnContext mutation guard (call-graph safety — NOT Send if mutable)
//   - TurnOutcomeWriter interface
//   - Turn lifecycle hooks (start/end) that plug into contracts/lifecycle.Drain
package turn
