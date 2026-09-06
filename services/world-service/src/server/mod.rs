//! The service's HTTP surface.
//!
//! Built on `crates/service-http` — serve / health / internal-auth / trace /
//! metrics / RFC 7807 — which named this migration before it happened: *"tilemap
//! /world migrate opportunistically when next touched."*
//!
//! The surface is **internal** (`WS-F4`). Invariant I1 routes all external
//! traffic through `api-gateway-bff`; every versioned route here is gated on
//! `X-Internal-Token`. The probes are ungated on purpose so a docker healthcheck
//! reaches them.
//!
//! Note the sibling: `embedding_queue::live::server` is the embedding **worker's**
//! own probe surface, served by a different binary from a different port. Two
//! HTTP surfaces in one crate is deliberate — a worker's liveness is not the
//! service's.

pub mod config;
pub mod db;
pub mod handlers;
pub mod routes;
pub mod state;

pub use config::Config;
pub use routes::{Gate, ROUTES, RouteSpec, build_router};
pub use state::AppState;
