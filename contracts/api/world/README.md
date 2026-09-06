# contracts/api/world — world-service API contracts

Frozen OpenAPI contracts for `services/world-service` (LLM MMO RPG geography substrate).

**Status: one spec frozen — the service's first HTTP surface.** The geography specs below are still unfrozen; the Cycle-0 note that read *"no specs frozen yet"* was true until 2026-08-13.

| Spec | Frozen by | Source design doc | State |
|---|---|---|---|
| [`provisioning.v1.yaml`](provisioning.v1.yaml) — internal probes + `POST /internal/v1/realities` | 2026-08-13 (`WS1`) | [`2026-08-13-world-service-server-RUN-STATE.md`](../../../docs/plans/2026-08-13-world-service-server-RUN-STATE.md) | **frozen + enforced** |
| `geometry.v1.yaml` (`world_geometry` read/query + GeographyDelta) | Cycle 1 | GEO_001 / GEO_001b | planned |
| `political.v1.yaml` (POL deltas + capability claims) | Cycle 2 | GEO_002 POL_001 | planned |
| `settlement.v1.yaml` (SET deltas) | Cycle 2 | GEO_003 SET_001 | planned |
| `route.v1.yaml` (ROUTE deltas) | Cycle 3 | GEO_004 ROUTE_001 | planned |

Per [`V1_30D_IMPLEMENTATION_PLAN.md`](../../../docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md) §3.4, the detailed per-feature OpenAPI specs are frozen in each build cycle's CLARIFY phase (contract-first per module, per `CLAUDE.md`), not all up front in Cycle 0. `provisioning.v1.yaml` was not in that plan — provisioning is an operational surface rather than a geography feature, so it earned a row rather than being served without one.

## Enforcement

`contracts/.spectral.yaml` is **not wired** (DEFERRED 078), so freezing a YAML here buys no machine check by itself. `services/world-service/tests/route_conformance.rs` supplies the missing half: it walks the real route table, parses every `*.v1.yaml` in this directory, and fails on an undocumented route or a documented-but-unrouted path. Add a route → document it here, in the same commit, or the build reds.
