//! `world-service` — geography substrate service for the LLM MMO RPG.
//!
//! Owns the `world_geometry` aggregate (GEO_001) and the POL/SET/ROUTE
//! activation generators. See the design docs under
//! `docs/03_planning/LLM_MMO_RPG/features/00_geography/` and the build plan
//! `docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md`.
//!
//! **Cycle 0 scaffold.** This crate compiles empty and has no behavior. Cycle 1
//! cannot proceed until the DP-kernel (aggregate + event-sourcing framework)
//! exists — see `V1_30D_CYCLE_LOG.md`.

fn main() {
    println!(
        "world-service — Cycle 0 scaffold (no behavior). \
         Cycle 1 (GEO_001) is blocked on the unbuilt DP-kernel."
    );
}
