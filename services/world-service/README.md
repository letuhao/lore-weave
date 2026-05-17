# world-service

Geography substrate service for the LLM MMO RPG design track (`docs/03_planning/LLM_MMO_RPG/`).

**Owns:** the `world_geometry` aggregate (GEO_001) + the POL_001 / SET_001 / ROUTE_001 activation generators (geography pipeline stages 1–8).

**Status: Cycle 0 scaffold** — empty-compiling Rust crate, no behavior. Created by Cycle 0 of [`V1_30D_IMPLEMENTATION_PLAN.md`](../../docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md).

**Blocked:** Cycle 1 (GEO_001 implementation) cannot start until the **DP-kernel** — the aggregate + event-sourcing framework every GEO/TVL aggregate derives from — is built. The kernel and the foundation tier (EF/RES/PL/TDIL/AIT/PROG) do not yet exist as code; see [`V1_30D_CYCLE_LOG.md`](../../docs/03_planning/LLM_MMO_RPG/V1_30D_CYCLE_LOG.md).

Design refs: [`features/00_geography/`](../../docs/03_planning/LLM_MMO_RPG/features/00_geography/). API contract home: [`contracts/api/world/`](../../contracts/api/world/).
