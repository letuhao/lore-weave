//! S2 / C2 — from-spec golden fixtures.
//!
//! A golden fixture pins `{event envelope -> expected projection delta}` for one
//! projecting event type. The test harness (`tests/golden.rs`) runs each
//! fixture's envelope through the FULL projection set and asserts the produced
//! `Vec<ProjectionUpdate>` equals the fixture's `expected_updates`.
//!
//! ## Honest framing (see the slice plan + /review-impl)
//!
//! Fixtures are authored from the **design source of truth** — the migration
//! column semantics (`contracts/migrations/per_reality/0006_projections.up.sql`,
//! `0009_canon_projection.up.sql`), the locked Q-decisions (Q-L3B-1 npc.said
//! fan-out, Q-L3-4 verification meta, the canon_layer enum, …), and each arm's
//! doc-comment contract — **NOT** by dumping `apply_event` output. That is the
//! best available independence in a single-author battery.
//!
//! Even so, the residual coupling (same author reads both) means C2-via-fixtures
//! is primarily a **regression-lock + spec-encoding**: it pins the contract and
//! catches future drift, and catches a *current* wrong value only to the extent
//! the fixture was authored independently of the code. True independence for the
//! highest-risk types is the deferred Option-B reference projector
//! (D-C2-REFERENCE-PROJECTOR).

use dp_kernel::{EventEnvelope, ProjectionUpdate};
use serde::Deserialize;

/// One golden fixture: an event and the projection delta it MUST produce.
#[derive(Debug, Deserialize)]
pub struct Fixture {
    /// The input event.
    pub envelope: EventEnvelope,
    /// The expected `Vec<ProjectionUpdate>` from running the envelope through the
    /// full projection set, in order.
    pub expected_updates: Vec<ProjectionUpdate>,
}

/// Parse a fixture from JSON bytes.
pub fn load(bytes: &[u8]) -> Result<Fixture, String> {
    serde_json::from_slice(bytes).map_err(|e| e.to_string())
}
