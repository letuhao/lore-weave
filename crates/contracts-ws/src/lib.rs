// L6.A.5 — contracts-ws crate.
//
// **Purpose.** Downstream services (roleplay-service, world-service) need
// the WS envelope + close-code types so they can speak to the gateway
// over RPC and emit fanout frames that the gateway will pass through
// to the browser unchanged.
//
// **Why a separate crate (not just dp-kernel).** dp-kernel is the
// per-reality replay/projection plane; the WS surface is orthogonal to
// it (a connection can carry events from many realities). Keeping it
// separate stops dp-kernel from growing a WS dep and lets non-replay
// services (e.g. notification-worker, future presence-service) import
// the envelope types in isolation.
//
// **Wire compatibility.** Every type here MUST stay bit-for-bit
// compatible with `contracts/ws/envelope.go` and
// `services/api-gateway-bff/src/ws/session-router.ts`. The Go file is
// canonical (it shipped cycle 21 L4.L); deviating breaks the gateway.
//
// **Locked decisions (Q-L6 family):**
//   - Q-L6-1: WS impl extends NestJS in api-gateway-bff (this crate is
//     server-LIB types only, NOT a stand-alone WS server).
//   - Q-L6-2: 10K cap per replica — enforced gateway-side, not here.
//   - Q-L6-3: foundation owns server + envelope only; no browser lib.

#![deny(missing_docs)]

//! # contracts-ws
//!
//! Rust mirror of `contracts/ws/envelope.go` + `contracts/ws/ticket.go`.
//!
//! Used by downstream services (roleplay-service, world-service,
//! future presence-service) that need to construct outbound WS frames
//! the gateway will fan out, OR introspect inbound frames the gateway
//! forwards over RPC.
//!
//! The gateway itself is NestJS (Q-L6-1) — this crate does NOT contain
//! a WS server; it is a typed surface for downstream Rust code.
//!
//! Cycle 28 L6.A.5 (RAID).

pub mod envelope;
pub mod close_codes;
pub mod server_lib;
pub mod authz;
pub mod control_channel;

pub use envelope::{Envelope, Direction, MessageKind, ENVELOPE_VERSION};
pub use close_codes::CloseCode;
pub use server_lib::{ServerLib, ServerLibError, OutboundFrame};
pub use authz::{AuthzOutcome, AuthzRejectionReason, AuthzRequest};
pub use control_channel::{WsControlMessage, WsControlKind, WS_CONTROL_VERSION};
