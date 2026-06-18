//! S10 — kernel simulation DST (H1 / VOPR-lite).
//!
//! Runs the REAL dp-kernel event-sourcing surface under a deterministic,
//! seed-reproducible simulator and asserts the spine invariants hold across a
//! sweep of fault schedules. See `docs/specs/2026-06-14-S10-kernel-sim-dst.md`.
//!
//! Modules:
//! - [`exec`]  — the Path-B deterministic executor + `sim_yield`.
//! - [`store`] — `SimEventStore` (fault-injectable `EventStore` impl).
//! - [`skeleton`] — Inc-1 self-non-vacuity gate (the harness proves itself).
//!
//! Oracles (Inc-2..4) are added as `convergence`, `atomicity`, `cas` modules.

/// Seed-sweep width for the clean oracles. Defaults to each oracle's own value;
/// `SIM_SEEDS` overrides (per-PR CI runs the default = shallow; nightly sets it
/// high = deep). Review LOW-2.
pub fn seed_sweep(default: u64) -> u64 {
    std::env::var("SIM_SEEDS")
        .ok()
        .and_then(|s| s.parse().ok())
        .filter(|n| *n > 0)
        .unwrap_or(default)
}

pub mod atomicity;
pub mod cas;
pub mod convergence;
pub mod exec;
pub mod skeleton;
pub mod store;
pub mod table;
pub mod tilemap;
