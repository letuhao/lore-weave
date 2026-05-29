//! `dp-kernel` — LoreWeave data-platform kernel (RAID cycle 8 / L2.H + L2.I).
//!
//! ## Scope
//!
//! - [`upcaster`] — L2.H upcaster chain library. Lets a service declare
//!   per-event transformations `vN -> vN+1` and compose chains automatically.
//!   Designed to be IDEMPOTENT + REPLAY-SAFE: upcasting an already-vN event
//!   to vN is a no-op, and the chain refuses to downcast (`v3 -> v2`).
//!
//! - [`event_validator`] — L2.I schema validation on write. Validates an
//!   incoming event payload against the registered schema BEFORE the event
//!   is appended to the log (per R03 §12C.4 — never let malformed events
//!   poison the stream).
//!
//! - [`errors`] — typed error enum shared by both modules.
//!
//! The Go side of these libraries lives in `contracts/events/upcasters_go/`
//! and `contracts/events/validators_go/` — both follow the same trait shape
//! so logic is portable.
//!
//! ## Why a new crate (vs adding to `meta-rs`)?
//!
//! `meta-rs` (cycle 2) is the routing/read library for the META database. It
//! must stay tiny + free of YAML / event-schema dependencies because the
//! kernel hot-path links it. L2 event-sourcing primitives are a different
//! concern (data-platform vs meta-routing) and have their own deferral path
//! (`crates/dp-kernel/` keeps growing as L2 lands more pieces — outbox,
//! snapshot policy, projection trait — in cycles 9-11).
//!
//! ## Stability contract
//!
//! Symbols exported at the root (`pub use`) are V1-stable. Sub-module paths
//! may be reshaped within `dp-kernel` between cycles 8-11 as L2 fills out.

pub mod errors;
pub mod event_validator;
pub mod outbox;
pub mod upcaster;

pub use errors::EventError;
pub use event_validator::{EventValidator, SchemaDescriptor, ValidatorRegistry};
pub use outbox::{insert_sql as outbox_insert_sql, write as outbox_write, OutboxError, OutboxRow, OutboxWriter};
pub use upcaster::{Upcaster, UpcasterChain, UpcasterRegistry};
