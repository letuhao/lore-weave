// Package upcastersgo is the Go mirror of `crates/dp-kernel/src/upcaster.rs`
// (L2.H upcaster chain library).
//
// Go services (auth-service, glossary-service, world-service-go-side,
// publisher, …) register one-step upcasters at init; the registry composes
// them into chains automatically. Same invariants as the Rust side:
//
//   - Forward-only (downcast forbidden — would lose info)
//   - Idempotent at the no-op step (from==to)
//   - Total-chain or fail-loud on missing intermediate
//   - Replay-safe (pure functions; no IO)
//
// Wire compatibility: payloads are `map[string]any` matching the Rust
// `serde_json::Value` shape. The L2.G eventgen tool can emit a per-event
// dispatch table from `@upcast` annotations in cycle 9+ — cycle 8 wires the
// shipped upcaster (npc.said v1→v2) by hand in `npc_said_v1_to_v2.go`.
package upcastersgo
