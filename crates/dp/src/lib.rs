//! `dp` — the data-plane SDK contract.
//!
//! # What this crate is, and what it is not
//!
//! [`06_data_plane/`] is 25 LOCKED documents that name **three** crates:
//! `dp` (this one), `dp-derive` and `dp-clippy`. Measured 2026-08-07, none of
//! the three existed, while `crates/dp-kernel` — created five weeks *after*
//! that lock, by the RAID track, for event-contract plumbing — carried the
//! prefix and was read as coverage by `12_module_coverage_audit.md`. Every
//! detail is `FLOW-1`..`FLOW-26` in the game-tier RUN-STATE; the short version
//! is that **`dp-kernel` is `02_storage` in Rust, and this is the access
//! surface that was never built on top of it.**
//!
//! This crate is deliberately small and holds **no I/O**. It is the part of the
//! contract that can be true before a connection exists: what a tier promises,
//! what a scope addresses, and the fact that an aggregate has exactly one of
//! each.
//!
//! # Slice 1 of the sealed build order — what it does and does not claim
//!
//! * **Does:** make `DP-A5`'s closed taxonomy **unrepresentable to violate** —
//!   sealed traits, so no crate anywhere can mint a fifth tier or a third scope
//!   — and make `DP-Ch4`'s exclusivity structural **for a concrete impl**,
//!   rather than checked by a derive macro. See [`tier`] and [`scope`] for why
//!   that is a strengthening of the locked text and not a deviation from it.
//! * **Does NOT** make exclusivity structural for a **generic** impl, and that
//!   limit is load-bearing rather than incidental: `impl<T: Tier> DpAggregate
//!   for Wallet<T>` gives one `TYPE_NAME` four tiers, chosen per request. A
//!   cold-start refuter compiled and ran exactly that on 2026-08-07 (`V1-F1`)
//!   after this crate's own docs had called it impossible. The type checker
//!   cannot see it — the contradiction is *across* monomorphisations — so
//!   `scripts/dp-aggregate-gate.py` checks it over the source, for this repo
//!   only. [`aggregate`] states the split in full.
//! * **Does:** put `REC-102c`'s degraded-mode partition in code as
//!   [`Tier::SURVIVES_STORE_OUTAGE`], so a decision made in prose today cannot
//!   quietly become prose-only tomorrow.
//! * **Does NOT** ship read/write primitives (`DP-K4`/`K5`), a `DpClient`,
//!   `SessionContext`, or `cache_key!`. Those are slices 3 and 4, and each
//!   needs something this slice does not have: a control plane, a `channels`
//!   table, and a settled `DpError`.
//! * **Does NOT** ship `dp-derive`. With tier and scope as associated types the
//!   derive is *ergonomics*, not *enforcement* — and a proc-macro crate whose
//!   only caller is its own tests is the orphan shape
//!   `scripts/orphan-model-gate.py` refuses. It arrives with the first real
//!   aggregate.
//! * **Does NOT** create `crates/loreweave-aggregates` (`OOS-2`). Same reason,
//!   said once: **the shared crate exists when two services share a type**, and
//!   today zero do.
//!
//! # `Q13`, which is due
//!
//! `99_open_questions.md` `Q13` — *"how do we test that a feature actually
//! honors its declared tier?"* — has been open since 2026-04-25, deferred in
//! two locked files on the same trigger: *"once SDK implementation starts."*
//! This is that. The answer splits:
//!
//! * **The declaration half is now mostly a compile problem, and the remainder
//!   is a gate.** A tier that is an associated type on a sealed trait cannot be
//!   a fifth thing and cannot vary at runtime; on a **concrete** impl it also
//!   cannot be two things. `tests/ui/` proves each of those fails to compile —
//!   which is this crate's own non-vacuity evidence, because *a guarantee
//!   nobody tried to break is a claim.* The generic escape is the part rustc
//!   permits, and `dp-aggregate-gate` is what refuses it.
//! * **The behavioural half is slice 4's.** Whether a T2 aggregate's write path
//!   *actually* acks on cache+outbox rather than waiting for a fan-out is a
//!   property of the write surface, and there is no write surface yet. Recorded
//!   here rather than left implied.
//!
//! [`06_data_plane/`]: ../../../docs/03_planning/LLM_MMO_RPG/06_data_plane/_index.md

#![forbid(unsafe_code)]
#![deny(missing_debug_implementations)]

pub mod aggregate;
pub mod scope;
pub mod tier;

pub use aggregate::{requires_channel, tier_row, DpAggregate, TierRow};
pub use scope::{ChannelScope, RealityScope, Scope, ScopeKind};
pub use tier::{Coherency, Tier, TierLevel, T0, T1, T2, T3};
