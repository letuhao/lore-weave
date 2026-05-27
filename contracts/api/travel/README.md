# contracts/api/travel — travel-service API contracts

Frozen OpenAPI contracts for `services/travel-service` (LLM MMO RPG travel mechanics).

**Status: Cycle 0 — contract home established, no specs frozen yet.**

Per [`V1_30D_IMPLEMENTATION_PLAN.md`](../../../docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md) §3.4, the detailed per-feature OpenAPI specs are frozen in each build cycle's CLARIFY phase (contract-first per module, per `CLAUDE.md`), not all up front in Cycle 0:

| Spec | Frozen by | Source design doc |
|---|---|---|
| `travel.v1.yaml` (`Travel:Initiate` / tick / arrive; `actor_travel_state`) | Cycle 4 | TVL_001 |
| `composite.v1.yaml` (`CompositeTravel:*`; `composite_travel_plan` query) | Cycle 5 | TVL_002 |
| `mount.v1.yaml` (`Forge:GrantMount`; mount selection) | Cycle 5 | TVL_003 |
| `encounter.v1.yaml` (`Encounter:Resolve`) | Cycle 6 | TVL_004 |
| `party.v1.yaml` (`Party:Form`/`Join`/`Leave`/`Travel`) | Cycle 6 | TVL_005 |

Empty until those cycles run.
