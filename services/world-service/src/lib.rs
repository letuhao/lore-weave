//! `world-service` — geography substrate service for the LLM MMO RPG.
//!
//! ## Cycle 5 (L1.C + L1.G.3) surface
//!
//! Cycle 5 of the foundation mega-task lands the per-reality DB lifecycle
//! infrastructure described in `docs/plans/2026-05-29-foundation-mega-task/
//! L1C_to_L_infrastructure.md` §1 (L1.C) + §5 (L1.G):
//!
//! | Module              | Layer plan ID | Purpose                                                                    |
//! |---------------------|---------------|----------------------------------------------------------------------------|
//! | [`provisioner`]     | L1.C.1        | 11-step `provision_reality()` flow per R04 §12D.1                          |
//! | [`deprovisioner`]   | L1.C.2        | 6-step `deprovision_reality()` flow (idempotent)                           |
//! | [`capacity_planner`]| L1.C.3        | Shard allocator — picks the least-full shard within capacity thresholds    |
//! | [`db_pool`]         | L1.G.3        | App-side pool wrapper — 1 pool per shard host (NOT per DB) for pgbouncer   |
//! | binary `orphan_scanner` | L1.C.4    | Nightly cron — 7-day grace, then drop                                      |
//!
//! The GEO_001 aggregate behavior is still blocked on the DP-kernel (cycle 17).
//! What you see here is the **infrastructure** plumbing — provisioner/db_pool
//! call into the meta library (`crates/meta-rs`) for `RealityRouting` reads
//! and (in a later cycle) MetaWrite via RPC to the meta-worker.
//!
//! ## Why Rust here
//!
//! Per CLAUDE.md "Language rule: Go for domain services, Python for AI/LLM
//! services, **Rust for game-engine / hot-path domain**". The provisioner is
//! the entry point for per-reality lifecycle commands originating from the
//! kernel side, so it lives in Rust alongside the upcoming world-service
//! command handlers. Go services that need to write to `reality_registry`
//! use the existing `contracts/meta` library; this Rust surface complements
//! it, not replaces it.

#![forbid(unsafe_code)]
#![warn(missing_docs, rust_2018_idioms)]

pub mod capacity_planner;
pub mod db_pool;
pub mod deprovisioner;
pub mod errors;
pub mod provisioner;

pub use capacity_planner::{CapacityPlanner, CapacityThresholds, ShardCapacity, ShardId};
pub use db_pool::{DbPoolKey, DbPoolRegistry, ShardHost};
pub use deprovisioner::{DeprovisionReport, DeprovisionRequest, Deprovisioner};
pub use errors::ProvisionerError;
pub use provisioner::{ProvisionReport, ProvisionRequest, Provisioner};
