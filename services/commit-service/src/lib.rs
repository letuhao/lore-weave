//! # commit-service (POC-2 seed)
//!
//! The Rust **writer-node role** from
//! `docs/03_planning/LLM_MMO_RPG/15_commit_service.md`: hosts `sim-core`
//! natively (CS-A5), gates admission, and owns the AGT-A3 **LlmDriver**.
//! POC-2 slice = the LLM decision vertical: context → sanctioned LLM chain →
//! validated proposal → island resolution, with cost/latency/validity
//! measured. The EVT-V pipeline, proposal bus, and epoch-token durability are
//! S3 proper (tracked in `docs/plans/2026-07-27-poc2-llm-vertical-slice.md`).
//!
//! ## SHIP RULE (docs 14 §10.4 — the panic trap)
//! Build ONLY with `--profile release-commit` (`panic = "unwind"`). The
//! workspace's plain release profile sets `panic = "abort"`, which would kill
//! SC-A8 containment: one panicking island would take the whole node. The
//! `panic_canary` test guards the runtime behavior.

pub mod admission;
pub mod bus;
pub mod domain;
pub mod llm_driver;
pub mod recovery;
pub mod vocabulary;
pub mod wire;

pub use domain::{Actor, CombatDomain, CombatEvent, CombatPayload, CombatRules, CombatState, Stance};
pub use llm_driver::{decide, hp_band, Candidate, DecisionContext, Dispatch};
pub use vocabulary::{Reject, Vocabulary};
pub use wire::{OutcomeDetail, OutcomeKind, TurnOutcome};

/// The combat_v1 vocabulary, embedded from `contracts/agent/` at COMPILE time
/// so the binary cannot drift from the contract it was built against (the
/// file is the single source; a schema edit forces a rebuild).
pub const COMBAT_V1_JSON: &str =
    include_str!("../../../contracts/agent/vocabularies/combat_v1.json");
