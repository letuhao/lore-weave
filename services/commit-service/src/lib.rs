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
/// Q0b B3c — the lease-holding writer transcribing an epoch switch into its own
/// channel. The ONLY place `ruleset.epoch_activated` is constructed.
pub mod epoch_commit;
/// Q0b B3b — the binding signal on `lw.meta.events`, and the rule that the
/// stream is a nudge while `reality_ruleset_binding` is the truth.
pub mod epoch_signal;
/// The host's wall clock. The kernel never sees it — a deterministic island
/// that read a clock would not replay.
pub mod hostclock;
pub mod llm_driver;
pub mod manager;
/// Q1 B2b — `RLS-A3` bindings in the meta DB. Here rather than in
/// `ruleset-loader` so the game-logic tier keeps its three dependencies.
pub mod pg_binding;
pub mod producer;
pub mod recovery;
/// How a node gets the rules it runs (RLS-A3 at startup). Split from
/// `bin/spine.rs` when `--meta-url` pushed that file past its IMP-D3 ceiling.
pub mod ruleset_boot;
pub mod vocabulary;
pub mod wire;

pub use domain::{
    Actor, CombatDomain, CombatEvent, CombatPayload, CombatResource, CombatState, Stance,
};
// S2 — the laws moved to `crates/game-rules` (IMP-A5). Re-exported under their
// original paths so every `commit_service::combat::…` / `::stats::…` import
// keeps working: ONE definition, two paths, which is the same call `StatSlot`
// already made when the slot vocabulary moved to `ruleset-core`. The host may
// depend on the laws; the laws may not depend on the host.
pub use game_rules::{combat, stats};
// F1 — the domain's rules slice IS the resolved ruleset now. Re-exported here
// so a host wiring an island does not need a direct `ruleset-core` dependency
// just to name the type it passes to `Island::new`.
pub use ruleset_core::{CombatRules, ResolvedRuleset, Ruleset, StatRules};
pub use llm_driver::{decide, hp_band, Candidate, DecisionContext, Dispatch};
pub use vocabulary::{Reject, Vocabulary};
pub use wire::{OutcomeDetail, OutcomeKind, TurnOutcome};

/// The combat_v1 vocabulary, embedded from `contracts/agent/` at COMPILE time
/// so the binary cannot drift from the contract it was built against (the
/// file is the single source; a schema edit forces a rebuild).
pub const COMBAT_V1_JSON: &str =
    include_str!("../../../contracts/agent/vocabularies/combat_v1.json");
