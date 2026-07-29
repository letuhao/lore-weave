//! # sim-core — the simulation kernel (S1a slice)
//!
//! Implements `docs/03_planning/LLM_MMO_RPG/14_sim_core_spec.md` §4 (core
//! types) + §5 (step semantics) for a **single island**. Multi-island
//! messaging is S2; generational-invalidation cascade, panic containment and
//! the full chaos harness are S1b (PO thin-slice decision, 2026-07-26).
//!
//! ## Contract highlights (the load-bearing ones)
//! - **SC-A1 (order-independent safety):** any permutation of the ingress
//!   stream yields only valid outcomes — outcomes may differ, validity may
//!   not. Asserted by the permutation property test in `crates/sim`.
//! - **Preconditions re-validate at step time, never at admission** (spec §5).
//!   Admission stamps `Seq` and nothing else.
//! - **`apply` is only reachable through `check`** — structurally: the
//!   [`Island`] owns `D::State` and exposes no `&mut` path to it.
//! - **No ambient time, no I/O, no `f32` in state** (TDIL-A9 discipline).
//!   Time is injected as [`Tick`]; randomness only via the seeded [`DetRng`].
//! - **Rules are an argument, not ambient state** (RLS-A12): [`Domain`] carries
//!   `type Rules`, and `check`/`apply` receive `&Rules`.

#![forbid(unsafe_code)]

pub mod checkpoint;
pub mod domain;
pub mod ingress;
pub mod metrics;
pub mod island;
pub mod rng;
mod ruleset;
pub mod seen;
pub mod types;

pub use checkpoint::{Dissolution, IslandCheckpoint};
pub use domain::Domain;
pub use ingress::{Ingress, Lane};
pub use metrics::IslandMetrics;
pub use island::{Island, StepStatus};
pub use rng::DetRng;
pub use seen::{SeenSet, SeenWindow};
pub use types::{
    Admitted,
    Class, DiscardReason, DissolutionReason, EntityId, EpochSwitchRefused, Fallback, Gen, InputId,
    IslandId,
    IslandMessage, Outcome, Precondition, PreconditionKind, Producer, QueuedInput, RulesetDigest, RulesetEpoch, RulesetMismatch,
    Seq, Tick, Violation,
};
