# 99 — Open Questions

> **Status:** OPEN. Items here are deliberately deferred — each has a reason to defer and a target resolution point. Not every item blocks Phase 2.
> **Rule:** Anything locked in Phase 1 that later needs to change goes through a supersedence entry in [../decisions/](../decisions/); the superseded axiom/ID gets a `_withdrawn` suffix. This file tracks things not yet decided, not things being re-decided.

---

## Q1 — Exact Rust SDK API shape ✅ RESOLVED (Phase 2, 2026-04-25)

**What:** The precise Rust trait definitions, method signatures, and module layout for the SDK (`t0_*`, `t1_*`, `t2_*`, `t3_*` + multi-aggregate transactions + subscription APIs).

**Resolution:** Locked in [04_kernel_api_contract.md](04_kernel_api_contract.md) — DP-K1..K12 specify all core types, tier traits, predicate builder, read/write primitives, subscription APIs, macros, capability tokens, and SDK init/bind flow. ~24 primitives total.

**Residual:** `#[derive(Aggregate)]` proc-macro implementation details deferred to Phase 2b (`dp-derive` crate).

---

## Q2 — Python ↔ Rust event bus protocol

**What:** The wire protocol, topic layout, event schema, and backpressure model for the bus that carries Python roleplay-service proposals to the Rust game layer. Locked direction: [DP-A6](02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) (Python emits only, Rust validates and applies). Open: bus technology (Redis Streams vs NATS vs Kafka), schema versioning, replay semantics on game-service crash, ordering guarantees.

**Why deferred:** User flagged roleplay-service as a draft, expected to redesign heavily. Locking a bus protocol to a draft service would constrain that redesign. Every future design in 06_data_plane can proceed without this decision because the SDK is Rust-only — Python is outside DP.

**Resolves in:** A future `10_llm_bus_protocol.md` in this folder or a new subfolder, once roleplay-service has a locked design.

**Dependencies:** roleplay-service design maturity.

---

## Q3 — Redis topology

**What:** Single Redis cluster with sharding by `reality_id` vs one Redis instance per reality vs hybrid (shared for T2 projection cache, per-reality for T1 hot state).

**Why deferred:** Depends on operational cost tradeoffs and the specific number of active realities at launch. All Phase 1 axioms are topology-agnostic because cache keys start with `reality_id` ([DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys)), so any topology works.

**Resolves in:** Phase 3 `07_failure_and_recovery.md` or in an ops-focused doc once V2 ramp data exists.

**Dependencies:** Operational cost estimates (Q7).

**Default for design:** Assume single Redis Cluster with hash-tag sharding `{reality_id}` until decided otherwise. SDK is written to be topology-agnostic.

---

## Q4 — Cache invalidation storm mitigation ✅ RESOLVED (Phase 2, 2026-04-25)

**What:** When a T3 write invalidates a hot aggregate, every SDK instance subscribed to that invalidation will drop its local copy. Next read from each instance re-populates from Postgres — this is a thundering herd.

**Resolution:** [DP-X4](06_cache_coherency.md#dp-x4--invalidation-storm-mitigation) specifies a three-layer mitigation: singleflight deduplication per SDK instance + stale-while-revalidate with 20-second grace window + jittered repopulation for hotset-flagged aggregates. Worst case = N reads per invalidated key per 20s window, regardless of read QPS.

**Residual:** Cold-cache genuine thundering herd at reality-warm transition partially mitigated by hotset pre-warm; V2 benchmark target <2× sustained QPS spike.

---

## Q5 — Control plane schema migration protocol ✅ RESOLVED (Phase 3, 2026-04-25)

**What:** How does the control plane coordinate schema changes across N running SDK instances without a maintenance window?

**Resolution:**
- **Phase 2 ([DP-C5](05_control_plane_spec.md#dp-c5--schema-migration-coordination)):** Expand / Migrate / Contract protocol at the CP level.
- **Phase 3 ([DP-F8](07_failure_and_recovery.md#dp-f8--cold-start-fallback--schema-migration-rollback)):** rollback procedure on integrity-check failure — dual-read pause, quarantine new-schema projection, resume on old schema, ≤5 min rollback budget. Quarantined new-schema data preserved for forensic recovery.
- Catastrophic migrations (breaking change, no dual-read feasible) require reality-freeze via [02_storage R9](../02_storage/R09_safe_reality_closure.md).

**Cross-ref:** [02_storage/R03](../02_storage/R03_schema_evolution.md) durable-tier schema evolution + [R02](../02_storage/R02_projection_rebuild.md) rebuild machinery.

---

## Q6 — Cold-start latency for a reality ✅ RESOLVED (Phase 3, 2026-04-25)

**What:** When a reality transitions from frozen to active, the cache is cold. Target ≤10s per [DP-S2](08_scale_and_slos.md). Pre-warm vs lazy-populate tradeoff, and behavior when CP is unavailable.

**Resolution:**
- **Phase 2 ([DP-C7](05_control_plane_spec.md#dp-c7--cold-start-coordination)):** CP orchestrates `frozen → warming → active` with reality hotset pre-warm in parallel with first-session bind.
- **Phase 3 ([DP-F8](07_failure_and_recovery.md#dp-f8--cold-start-fallback--schema-migration-rollback)):** CP-unavailable fallback — gateway queues connect ≤30s then returns 503 `Retry-After: 60`; reality stays frozen rather than risk double-wake violating single-writer (DP-A11).

**Residual (not an OPEN Q, operational work):** V2 telemetry to validate the ≤10s target in prototype; hotset learning algorithm for V3 stays a future operational tuning.

---

## Q7 — Redis operational cost at V3

**What:** Actual memory and throughput cost of Redis at 10k CCU / 1000 realities / 50 GB working set. Whether managed Redis (ElastiCache, Redis Cloud) vs self-hosted on ECS is the right call. [DP-S6](08_scale_and_slos.md) sizes the working set but does not pick the vendor.

**Why deferred:** Operational decision, not design decision. Only relevant when V3 is imminent.

**Resolves in:** Ops/infra doc or operator runbook, not this folder.

---

## Q8 — SDK telemetry surface 🟡 PARTIAL (Phase 2, 2026-04-25)

**What:** What metrics the SDK emits (per-tier latency histograms, cache hit rate, invalidation rate, backpressure events).

**Partial resolution:** [DP-K8](04_kernel_api_contract.md#dp-k8--dpinstrumented-telemetry-macro) locks the `dp::instrumented!` macro which emits `dp.{op}.{tier}.{aggregate}` latency histograms, counters, and `tracing` spans. Per-scenario metric names listed in DP-X6 (in-proc cache) and DP-C9 (CP reachability). Clippy lint `dp::missing_instrumentation` enforces coverage.

**Residual:** Dashboard layout, alerting thresholds, and observability-stack integration (Prometheus / OTEL / Grafana dashboards) are operational concerns, not this folder's scope. Alert thresholds and SLO burn-rate rules land in an operator-facing doc.

---

## Q9 — Authorization model inside the SDK ✅ RESOLVED (Phase 2, 2026-04-25)

**What:** Does the SDK enforce per-service authorization (e.g., combat-service cannot write currency)?

**Resolution:** Yes, via JWT capability tokens.
- [DP-K9](04_kernel_api_contract.md#dp-k9--capability-tokens) defines token format (JWT with short 5-minute expiry), refresh protocol, and per-aggregate + per-tier capability claims.
- [DP-C8](05_control_plane_spec.md#dp-c8--capability-issuance--rotation) defines CP-side issuance, signing key rotation (quarterly), and revocation model.
- [DP-C4](05_control_plane_spec.md#dp-c4--tier-policy-registry) tier_capability table is the source of truth for which service can do what.
- SDK rejects ops with `DpError::CapabilityDenied { aggregate, tier }` on mismatch.

---

## Q10 — In-process second cache layer 🟡 PARTIAL (Phase 2, 2026-04-25)

**What:** Permit optional in-process cache on top of Redis.

**Partial resolution:** [DP-X6](06_cache_coherency.md#dp-x6--in-process-second-cache-layer-opt-in) locks the policy: off by default; opt-in per aggregate type via CP admin; 1s TTL cap; same-channel invalidation subscription; LRU-bounded.

**Residual:** Which specific aggregate types to enable it for at V2 is data-driven — not decided in Phase 2. Dashboard alarm on staleness discrepancy is an operator doc concern.

---

## Q11 — Multi-reality transactional operations

**What:** If a feature needs atomicity across two realities (canon propagation between parent and fork, per [03_multiverse/06_M_C_resolutions.md](../03_multiverse/06_M_C_resolutions.md)), how does DP express this? The existing cross-instance policy (R5) forbids direct cross-reality writes; canon propagation goes through a coordinator. Open: does DP expose a `t3_write_cross_reality` API, or is this strictly out of scope for the SDK (coordinator-only)?

**Why deferred:** Depends on canon propagation design in 03_multiverse. Default assumption: **out of scope for SDK**. Cross-reality coordination is a dedicated service, not an SDK primitive.

**Resolves in:** Cross-reference once 03_multiverse canon propagation spec matures, or explicit deferral if the answer stays "out of scope."

---

## Q12 — Backpressure semantics ✅ RESOLVED (Phase 3, 2026-04-25)

**What:** Precise behavior when reality breaches [DP-S8](08_scale_and_slos.md) ceilings.

**Resolution:** [DP-F7](07_failure_and_recovery.md#dp-f7--backpressure-token-bucket) locks three independently-sized token buckets:
- **Per-reality-per-tier** — matches DP-S5 sustained + 4s burst (T1=5k/s, T2=500/s, T3=50/s, reads=10k/s)
- **Per-service** — fairness; prevents rogue feature monopolizing (default equal shares, dynamic rebalance 5-min intervals)
- **Per-session** — abuse prevention (T1=100/s, T2/T3 write=10/s, read=200/s)

Any bucket empty → `DpError::RateLimited { retry_after: Duration }`. Feature code MUST propagate per [DP-R6](11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry); silent retry loops caught by clippy lint.

**Residual (V2 tuning, not OPEN):** exact per-service dynamic rebalancing algorithm; V1/V2 ships with equal shares.

---

## Q13 — Test strategy for tier contract enforcement

**What:** How do we test that a feature actually honors its declared tier? E.g., if a feature declares T2 but occasionally writes T3 under error conditions, how is this caught? Static analysis of SDK call sites? Integration test harness? Runtime assertion in staging?

**Why deferred:** Test strategy depends on SDK API (Phase 2) and the broader test infrastructure. Phase 1 only asserts that tier choice is locked at design time ([DP-A9](02_invariants.md#dp-a9--feature-tier-assignment-is-part-of-feature-design-not-runtime)) and that the Rulebook review gate requires a tier table ([DP-R2](11_access_pattern_rules.md#dp-r2--tier-declaration-per-aggregate)).

**Resolves in:** Test plan doc once SDK API is concrete.

---

## Q14 — Concrete Rust definitions for newtype, macro, and error enum ✅ RESOLVED (Phase 2, 2026-04-25)

**What:** Exact Rust contract shapes for newtype, macro, error enum, session bind.

**Resolution:** [04_kernel_api_contract.md](04_kernel_api_contract.md) contains contract sketches for all of:
- `RealityId` + `SessionId` + `NodeId` newtypes ([DP-K1](04_kernel_api_contract.md#dp-k1--core-types))
- `SessionContext` ([DP-K2](04_kernel_api_contract.md#dp-k2--sessioncontext))
- `DpError` with 12 variants incl. `RealityMismatch`, `RateLimited`, `CircuitOpen`, `WrongWriterNode`, `TierViolation`, `CapabilityExpired`, `CapabilityDenied`, `AggregateNotFound`, `SchemaVersionMismatch`, `ControlPlaneUnavailable`, `BackendIo` ([DP-K3](04_kernel_api_contract.md#dp-k3--dperror-enum))
- `dp::cache_key!` + `dp::instrumented!` macros ([DP-K7](04_kernel_api_contract.md#dp-k7--dpcache_key-macro), [DP-K8](04_kernel_api_contract.md#dp-k8--dpinstrumented-telemetry-macro))
- Capability tokens ([DP-K9](04_kernel_api_contract.md#dp-k9--capability-tokens))
- Clippy lint skeletons for R-3, R-4, R-6, R-8 ([DP-K11](04_kernel_api_contract.md#dp-k11--clippy-lint-skeletons))

**Residual:** `#[derive(Aggregate)]` proc-macro crate (`dp-derive`) is its own implementation task — Phase 2b.

---

## Summary — what blocks what

| Open Q | Status after Phase 3 | Resolved in | Blocks feature design? |
|---|---|---|:---:|
| Q1 SDK API shape | ✅ resolved | Phase 2 (DP-K*) | no |
| Q2 Python bus | open | out of DP scope | no |
| Q3 Redis topology | open | ops doc / V2 data | no |
| Q4 Invalidation storm | ✅ resolved | Phase 2 (DP-X4) | no |
| Q5 Schema migration | ✅ resolved | Phase 2 (DP-C5) + Phase 3 (DP-F8 rollback) | no |
| Q6 Cold start | ✅ resolved | Phase 2 (DP-C7) + Phase 3 (DP-F8 fallback) | no |
| Q7 Redis ops cost | open | ops doc | no |
| Q8 SDK telemetry | 🟡 partial | Phase 2 (macro); dashboards = ops | no |
| Q9 SDK authZ | ✅ resolved | Phase 2 (DP-K9, DP-C8) | no |
| Q10 In-proc cache | 🟡 partial | Phase 2 (policy); per-aggregate enable = ops | no |
| Q11 Cross-reality txn | open | out-of-SDK scope | minor |
| Q12 Backpressure | ✅ resolved | Phase 3 (DP-F7) | no |
| Q13 Tier testing | open | Phase 2b test plan | no (QC gate later) |
| Q14 Rust types + macros | ✅ resolved | Phase 2 (DP-K1..K12) | no |

**Design-phase resolved (7):** Q1 · Q4 · Q5 · Q6 · Q9 · Q12 · Q14
**Design-phase partial (2):** Q8 (macro locked, dashboards = ops) · Q10 (policy locked, per-aggregate enable = ops)
**Operational doc (not this folder, 3):** Q3 · Q7 · Q8 dashboards · Q10 per-aggregate enable list
**Out of scope for this folder (2):** Q2 (Python bus) · Q11 (cross-reality txn)
**Future implementation doc (1):** Q13 (test plan, when SDK implementation starts)

**06_data_plane design phase is functionally complete.** Remaining work is implementation (Phase 2b proc-macro crate + clippy lints + SDK + CP service), ops integration (dashboards, per-aggregate tuning), and future scope items that explicitly belong elsewhere.
