# 99 — Open Questions

> **Status:** OPEN. Items here are deliberately deferred — each has a reason to defer and a target resolution point. Not every item blocks Phase 2.
> **Rule:** Anything locked in Phase 1 that later needs to change goes through a supersedence entry in [../decisions/](../decisions/); the superseded axiom/ID gets a `_withdrawn` suffix. This file tracks things not yet decided, not things being re-decided.

---

## Q1 — Exact Rust SDK API shape

**What:** The precise Rust trait definitions, method signatures, and module layout for the SDK (`t0_*`, `t1_*`, `t2_*`, `t3_*` + multi-aggregate transactions + subscription APIs).

**Why deferred:** Phase 2 owns this. Phase 1 locks the contract (tiers, axioms, SLOs) at the conceptual level so that Phase 2 has firm inputs. Writing Rust type signatures before the conceptual model is locked invites rework.

**Resolves in:** `04_kernel_api_contract.md` (Phase 2).

**Dependencies:** None — Phase 1 foundation is sufficient.

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

## Q4 — Cache invalidation storm mitigation

**What:** When a T3 write invalidates a hot aggregate, every SDK instance subscribed to that invalidation will drop its local copy. Next read from each instance re-populates from Postgres — this is a thundering herd. Needs a mitigation (singleflight deduplication, stale-while-revalidate, or scheduled re-population).

**Why deferred:** Specific mitigation depends on the cache coherency protocol, which is Phase 2. Phase 1 flags the concern; Phase 2 resolves it.

**Resolves in:** `06_cache_coherency.md` (Phase 2).

---

## Q5 — Control plane schema migration protocol

**What:** How does the control plane coordinate schema changes (adding a field to an aggregate, changing a tier assignment) across N running SDK instances without a maintenance window? Options: rolling SDK restart with old+new read-compat (Expand/Migrate/Contract), online migration with dual-write, full drain per reality.

**Why deferred:** Phase 2 / Phase 3 territory. Needs CP spec first.

**Resolves in:** `05_control_plane_spec.md` or `07_failure_and_recovery.md`.

**Cross-ref:** [02_storage/R03_schema_evolution.md](../02_storage/R03_schema_evolution.md) solved schema evolution for the durable tier with upcasters. DP cache schema evolution is a separate question — cache may be invalidated wholesale rather than migrated.

---

## Q6 — Cold-start latency for a reality

**What:** When a reality transitions from frozen (no active players) to active (first player joins), the cache is cold. First reads hit Postgres projection. Target is ≤10 seconds for full readiness ([DP-S2](08_scale_and_slos.md)). Open: should the control plane pre-warm cache on transition, or accept the first-minute tax and let cache populate naturally?

**Why deferred:** Phase 3 `07_failure_and_recovery.md` owns cold-start semantics.

**Dependencies:** Control plane spec (Q5's home), telemetry to measure actual cold-start latency on V2 prototype.

---

## Q7 — Redis operational cost at V3

**What:** Actual memory and throughput cost of Redis at 10k CCU / 1000 realities / 50 GB working set. Whether managed Redis (ElastiCache, Redis Cloud) vs self-hosted on ECS is the right call. [DP-S6](08_scale_and_slos.md) sizes the working set but does not pick the vendor.

**Why deferred:** Operational decision, not design decision. Only relevant when V3 is imminent.

**Resolves in:** Ops/infra doc or operator runbook, not this folder.

---

## Q8 — SDK telemetry surface

**What:** What metrics the SDK emits (per-tier latency histograms, cache hit rate, invalidation rate, backpressure events). How those metrics flow to the observability stack. Required for SLO measurement ([DP-S4](08_scale_and_slos.md)).

**Why deferred:** Phase 2 SDK design owns this.

**Resolves in:** `04_kernel_api_contract.md` (Phase 2) or a sibling `04b_telemetry.md`.

---

## Q9 — Authorization model inside the SDK

**What:** Beyond "the SDK is the only door," does the SDK itself enforce per-service write authorization (e.g., combat-service cannot write currency, only trade-service can)? Locked or open policy per aggregate type / tier combo?

**Why deferred:** Scope of access control inside the SDK is a design call for Phase 2. Default expectation is "yes, the SDK has a per-service capability model" but not yet specified.

**Resolves in:** `05_control_plane_spec.md` (control plane issues capabilities) + `04_kernel_api_contract.md` (SDK enforces them).

---

## Q10 — In-process second cache layer

**What:** [DP-A4](02_invariants.md#dp-a4--redis-is-the-cache-technology) permits an optional in-process cache layer on top of Redis. Whether to enable it by default, what TTL, invalidation latency budget, and what eviction policy.

**Why deferred:** Optimization, not correctness. V2 can run without it; enable if Redis-round-trip latency is dominant on T1 broadcast fan-out.

**Resolves in:** Phase 2 `06_cache_coherency.md` or later performance-tuning doc.

---

## Q11 — Multi-reality transactional operations

**What:** If a feature needs atomicity across two realities (canon propagation between parent and fork, per [03_multiverse/06_M_C_resolutions.md](../03_multiverse/06_M_C_resolutions.md)), how does DP express this? The existing cross-instance policy (R5) forbids direct cross-reality writes; canon propagation goes through a coordinator. Open: does DP expose a `t3_write_cross_reality` API, or is this strictly out of scope for the SDK (coordinator-only)?

**Why deferred:** Depends on canon propagation design in 03_multiverse. Default assumption: **out of scope for SDK**. Cross-reality coordination is a dedicated service, not an SDK primitive.

**Resolves in:** Cross-reference once 03_multiverse canon propagation spec matures, or explicit deferral if the answer stays "out of scope."

---

## Q12 — Backpressure semantics

**What:** When a reality breaches DP-S8 ceilings (event log write rate, cache memory, pub/sub fan-out), what does the SDK return? Synchronous `RATE_LIMITED` error per write? Token bucket with wait? Drop-with-metric for T1? Per-tier behavior likely differs.

**Why deferred:** Phase 3 failure/recovery owns this. Phase 1 only asserts that backpressure exists ([DP-S8](08_scale_and_slos.md)).

**Resolves in:** `07_failure_and_recovery.md` (Phase 3).

---

## Q13 — Test strategy for tier contract enforcement

**What:** How do we test that a feature actually honors its declared tier? E.g., if a feature declares T2 but occasionally writes T3 under error conditions, how is this caught? Static analysis of SDK call sites? Integration test harness? Runtime assertion in staging?

**Why deferred:** Test strategy depends on SDK API (Phase 2) and the broader test infrastructure. Phase 1 only asserts that tier choice is locked at design time ([DP-A9](02_invariants.md#dp-a9--feature-tier-assignment-is-part-of-feature-design-not-runtime)) and that the Rulebook review gate requires a tier table ([DP-R2](11_access_pattern_rules.md#dp-r2--tier-declaration-per-aggregate)).

**Resolves in:** Test plan doc once SDK API is concrete.

---

## Q14 — Concrete Rust definitions for newtype, macro, and error enum

**What:** Exact Rust code for:
- `RealityId` newtype definition + module privacy configuration (`pub(crate)` vs `pub(super)` vs dedicated auth-module) — implementation of [DP-R1](11_access_pattern_rules.md#dp-r1--reality-scoping) and [DP-A12](02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype).
- `dp::cache_key!` macro shape + proc-macro vs macro-rules choice + compile-error patterns for malformed input — implementation of [DP-R4](11_access_pattern_rules.md#dp-r4--cache-keys-via-dp-macro-never-hand-built).
- `DpError` enum variants (at minimum: `RealityMismatch`, `RateLimited`, `CircuitOpen`, `WrongWriterNode`, `TierViolation`) and their `thiserror` derivation.
- `SessionContext` structure, bind protocol, capability token format, expiry/refresh lifecycle.
- Clippy custom-lint skeleton for rules DP-R3, DP-R4, DP-R6, DP-R8.

**Why deferred:** Concrete code belongs in Phase 2 `04_kernel_api_contract.md`. Phase 1 locks the semantics; Phase 2 writes the types.

**Resolves in:** Phase 2 `04_kernel_api_contract.md`.

**Dependencies:** None — Phase 1 foundation is complete. Phase 2 is unblocked once user approves Phase 1.

---

## Summary — what blocks what

| Open Q | Blocks Phase 2? | Blocks Phase 3? | Blocks feature design? |
|---|:---:|:---:|:---:|
| Q1 SDK API shape | — | yes | yes (features need API to design against) |
| Q2 Python bus | no | no | no (Python is outside DP) |
| Q3 Redis topology | no | minor | no |
| Q4 Invalidation storm | yes | yes | no (features can assume "handled") |
| Q5 Schema migration | yes (CP spec) | yes | no |
| Q6 Cold start | no | yes | no |
| Q7 Redis ops cost | no | no | no |
| Q8 SDK telemetry | yes (minor) | no | no |
| Q9 SDK authZ | yes | no | yes (features need to know what they can write) |
| Q10 In-proc cache | no | no | no |
| Q11 Cross-reality txn | no | minor | minor (multiverse features) |
| Q12 Backpressure | no | yes | minor (features should know failure modes) |
| Q13 Tier testing | no | no | no (but needed for QC gate later) |
| Q14 Rust types + macros | yes | yes | yes (features call these directly) |

**Phase 2 must resolve:** Q1, Q4 (via cache coherency design), Q5 (CP side), Q8, Q9, Q14.
**Phase 3 must resolve:** Q5 (migration protocol), Q6, Q12.
**Out of scope for this folder:** Q2, Q7.
