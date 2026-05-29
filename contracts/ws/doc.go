// Package ws — L4.L WebSocket SERVER-SIDE skeleton.
//
// # Scope (cycle 21 L4.L)
//
// This package ships the **foundation-owned** WS contract types: ticket
// shape, message envelope (control vs data + 11 enumerated close codes
// per S12 §12AB.9), server-side WSSession (15-min TTL, seq + nonce
// tracking), and the ServiceMode write-rejection helper that wires WS
// admission into the cycle 18 lifecycle.
//
// # Q-L6-3 (LOCKED 2026-05-29): browser TS lib NOT owned by foundation
//
// The frontend-game team owns the browser-side WebSocket library. The
// foundation ships only:
//
//   - Server-side ticket issuance/validation contract
//   - Server-side message envelope (Go + Rust)
//   - Server-side WSSession state (per-connection)
//   - Enumerated close codes (the wire-format ground truth)
//   - ServiceMode integration gate (cycle 18 lifecycle)
//
// The api-gateway-bff NestJS WS server consumes this package via cycle
// 27+ (L6) wiring; the foundation does NOT extend NestJS this cycle
// (L6 scope per layer plan).
//
// # Carry-forward from prior cycles
//
//   - Cycle 8 schema registry + eventgen: envelope types here ship in
//     the same shape eventgen could produce; future cycles may switch
//     to eventgen-generated envelopes (Q-L6-3 + eventgen synergy).
//   - Cycle 18 lifecycle ServiceMode: see [ServiceModeGate] — WS
//     server rejects writes when ServiceMode == ReadOnly or Offline.
//
// # Q-IDs honored (LOCKED 2026-05-29)
//
//   - Q-L6-3: server-side only; no browser lib in this package.
//   - Q-L6-1: api-gateway-bff WS extension is L6 scope (not this cycle);
//     this package supplies the contract types that L6 will consume.
//   - Q-L6-2: 10K connections per replica is a deployment/HPA decision,
//     not a contract; mentioned in Doc only.
//   - Q-L4-1: Rust mirror lives at crates/dp-kernel/src/ws.rs.
//
// # What is NOT in cycle 21
//
//   - Concrete Redis-backed ticket store (caller wires; only the
//     interface TicketStore lands here).
//   - Concrete WS handler / framing (gateway-NestJS / gateway-Go owns).
//   - L3 authz cache (S12 §12AB.4) — landing with L6 ws-gateway.
//   - Per-connection rate limits (S12 §12AB.6) — landing with L6.
//   - Browser fingerprint computation (S12 §12AB.7) — server-side
//     verifier interface present; client-side bytes computed by browser
//     lib (Q-L6-3).
package ws
