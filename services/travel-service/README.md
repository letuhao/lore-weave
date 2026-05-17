# travel-service

Travel mechanics service for the LLM MMO RPG design track (`docs/03_planning/LLM_MMO_RPG/`).

**Owns five aggregates:** `actor_travel_state` (TVL_001 atomic travel) · `composite_journey` (TVL_002) · `mount` (TVL_003) · `travel_encounter` (TVL_004) · `travel_party` (TVL_005).

**Status: Cycle 0 scaffold** — empty-compiling Rust crate, no behavior. Created by Cycle 0 of [`V1_30D_IMPLEMENTATION_PLAN.md`](../../docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md).

**Blocked:** Cycle 4 (TVL_001 implementation) cannot start until **both** the DP-kernel **and** the foundation actor substrate (EF_001 / RES_001 / PL_001 / TDIL_001 / AIT_001 / PROG_001) are built — none exist as code yet. See [`V1_30D_CYCLE_LOG.md`](../../docs/03_planning/LLM_MMO_RPG/V1_30D_CYCLE_LOG.md).

Design refs: [`features/00_travel/`](../../docs/03_planning/LLM_MMO_RPG/features/00_travel/). API contract home: [`contracts/api/travel/`](../../contracts/api/travel/).
