//! `world-service` — geography substrate service for the LLM MMO RPG.
//!
//! Owns the `world_geometry` aggregate (GEO_001) and the POL/SET/ROUTE
//! activation generators. See the design docs under
//! `docs/03_planning/LLM_MMO_RPG/features/00_geography/` and the build plan
//! `docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md`.
//!
//! **Cycle 5 (L1.C + L1.G.3).** The lib crate now ships the per-reality DB
//! provisioner / deprovisioner / capacity_planner / db_pool modules. The
//! HTTP server scaffold (and the GEO_001 aggregate) still awaits the
//! DP-kernel (cycle 17). Today this binary prints the deps + module list
//! so an operator can confirm the build is functional.

fn main() {
    println!(
        "world-service — Cycle 5 scaffold\n\
         Library modules: provisioner (L1.C.1), deprovisioner (L1.C.2),\n\
                          capacity_planner (L1.C.3), db_pool (L1.G.3)\n\
         Sibling binary:  orphan_scanner (L1.C.4) — run with --help\n\
         HTTP server + GEO_001 aggregate await DP-kernel (cycle 17)."
    );
}
