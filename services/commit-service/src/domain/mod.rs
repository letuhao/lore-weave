//! `CombatDomain` — the production combat domain's SEED (not `sim`'s
//! TestDomain, which stays a chaos harness). Minimal but total semantics for
//! the POC-2 vertical slice: strike / defend / move(stance) / flee, mirroring
//! `contracts/agent/vocabularies/combat_v1.json` one-to-one.
//!
//! Rules discipline: every `apply` is TOTAL and defensive — a cross-island
//! message or substitute arrives with no preconditions (sim-core contract),
//! so an absent/fled/downed target is a recorded miss, never a panic.

mod actor;
mod binding;
mod law;
mod payload;
mod round;
mod state;
mod substrate;

pub use actor::Actor;
pub use binding::{BindingError, HubBinding, RealityRules};
pub use law::CombatDomain;
pub use payload::{CombatEvent, CombatPayload, RefusalReason, Stance};
pub use state::{CombatResource, CombatState, NoResource};
