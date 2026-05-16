# contracts/api/world — world-service API contracts

Frozen OpenAPI contracts for `services/world-service` (LLM MMO RPG geography substrate).

**Status: Cycle 0 — contract home established, no specs frozen yet.**

Per [`V1_30D_IMPLEMENTATION_PLAN.md`](../../../docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md) §3.4, the detailed per-feature OpenAPI specs are frozen in each build cycle's CLARIFY phase (contract-first per module, per `CLAUDE.md`), not all up front in Cycle 0:

| Spec | Frozen by | Source design doc |
|---|---|---|
| `geometry.v1.yaml` (`world_geometry` read/query + GeographyDelta) | Cycle 1 | GEO_001 / GEO_001b |
| `political.v1.yaml` (POL deltas + capability claims) | Cycle 2 | GEO_002 POL_001 |
| `settlement.v1.yaml` (SET deltas) | Cycle 2 | GEO_003 SET_001 |
| `route.v1.yaml` (ROUTE deltas) | Cycle 3 | GEO_004 ROUTE_001 |

Empty until those cycles run.
