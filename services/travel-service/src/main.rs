//! `travel-service` — travel mechanics service for the LLM MMO RPG.
//!
//! Owns five aggregates — `actor_travel_state` (TVL_001), `composite_journey`
//! (TVL_002), `mount` (TVL_003), `travel_encounter` (TVL_004), `travel_party`
//! (TVL_005). See `docs/03_planning/LLM_MMO_RPG/features/00_travel/` and the
//! build plan `docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md`.
//!
//! **Cycle 0 scaffold.** This crate compiles empty and has no behavior. Cycle 4
//! cannot proceed until the DP-kernel AND the foundation actor substrate
//! (EF_001 / RES_001 / PL_001 / TDIL_001 / AIT_001 / PROG_001) exist — see
//! `V1_30D_CYCLE_LOG.md`.

fn main() {
    println!(
        "travel-service — Cycle 0 scaffold (no behavior). \
         Cycle 4 (TVL_001) is blocked on the unbuilt DP-kernel + foundation substrate."
    );
}
