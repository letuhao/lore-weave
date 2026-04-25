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

**06_data_plane design phase for Phase 1-3 scope is complete.** However — see Phase 4 section below.

---

# Phase 4 — Channel-model follow-ups (2026-04-25)

> **Context:** Phase 1-3 locked the kernel contract against a model we understood as "turn-based event-linear reality". On 2026-04-25 the user clarified the actual game model adds a **hierarchical channel** concept:
>
> - Each reality is an instance of a book; time inside is a sequence of events, not wall-clock.
> - Players grouped into nested channels: **cell session → tavern → town → district → country → continent**. A player is in exactly one cell at a time but is a "resident" of every ancestor channel.
> - Event rate decays ~10× per level up. Probabilistic **bubble-up** aggregates lower-level events and may trigger higher-level events.
> - "Everyone sees the same page" is scoped to channel level: cell members share cell events + ancestor events.
>
> A multi-perspective adversarial review under the new model found that Phase 1-3 contracts remain valid but must be extended. **7/7 of the REAL-* issues from the previous review still stand** (6 reframed to per-channel scope). **9 NEW-* issues** surface from the channel model itself.
>
> This section records the backlog. Items will be resolved one at a time in Phase 4 mini-sessions. Phase 1-3 axioms, tiers, rulebook, SLO anchors, kernel API, control plane spec, coherency protocol, and failure modes remain **LOCKED** as a baseline — changes must go through standard supersession procedure in [../decisions/](../decisions/).

## Phase 4 severity summary

- **🔴 Blockers (2 remaining, 2 resolved):** Q15 page/turn per-channel · Q27 event bubble-up primitive · ~~Q16 durable subscribe~~ ✅ resolved 2026-04-25 · ~~Q26 channel as first-class concept~~ ✅ resolved 2026-04-25
- **🟡 Significant gaps (9 remaining, 3 resolved):** Q18, Q19, Q20, Q21, Q22, Q28, Q31, Q32 + ~~Q17, Q30, Q34~~ ✅ resolved 2026-04-25
- **🟢 Nits / operational (4):** Q23–Q25, Q29, Q33

**Resolved (5):** Q16, Q17, Q26, Q30, Q34 ✅

---

## Q15 — Per-channel page/turn boundary primitive (REAL-1 reframed)

**What:** Each channel (cell, tavern, town, ...) has its own turn/page boundary — a canonical sync event that "advances" the channel and all members must see before the next channel-scoped event. DP contract currently has no first-class primitive for this; features would have to encode it via convention (ad-hoc T3 write of a `page_flip` aggregate).

**Why blocker:** Page-flip / turn-boundary is the central sync mechanism of the game. If not a first-class DP concept, every feature invents its own; consistency across features breaks.

**Candidate resolution path:** Add **DP-K13** `advance_channel_turn(ctx, channel_id, boundary_event)` primitive + **DP-R9** rule "writes to a channel require subscribe-completion of the last turn_boundary". Supersede [DP-K5](04_kernel_api_contract.md#dp-k5--write-primitives-tier-typed)-scoped scopes to include channel dimension.

**Blocks:** All feature design (they need turn semantics).

---

## Q16 — Durable per-channel event-stream subscribe with resume token (REAL-2 reframed) ✅ RESOLVED (Phase 4, 2026-04-25)

**What:** Phase 1-3 subscribe APIs were fire-and-forget pub/sub; reconnect after disconnect lost gap events. In event-linear game, this is semantic data loss.

**Resolution:** New file [14_durable_subscribe.md](14_durable_subscribe.md) DP-Ch16..Ch20:
- **DP-Ch16** `subscribe_channel_events_durable<S: ChannelEvent>(ctx, channel, from_event_id)` returns `DurableEventStream<S>`; visibility check via session capability + ancestor chain.
- **DP-Ch17** Hybrid backing — Redis Streams `dp:events:{reality}:{channel}` for live tail (7-day retention) + Postgres `event_log` direct query for historical catchup; populated by channel writer in same tx as commit.
- **DP-Ch18** Resume token = `channel_event_id`, client-side cursor; gap-free monotonic delivery; explicit `ResumeTokenExpired` rather than silent gap; catchup → live transition via parallel DB-page + Stream merge with `channel_event_id` deduplication.
- **DP-Ch19** `subscribe_session_channels` convenience auto-multiplexes ancestor chain; per-channel ordering preserved, cross-channel arbitrary; `resubscribe_for_new_context` helper on `move_session_to_channel`.
- **DP-Ch20** TCP-level backpressure + 60s stall threshold; idle heartbeat every 30s; explicit reconnect (no auto-reconnect by SDK); `StreamEndReason` taxonomy (retryable vs not).

[DP-A4](02_invariants.md#dp-a4--redis-is-the-cache--pubsub--streams-technology) extended with Streams role; existing `subscribe_invalidation` (cache coherency) and `subscribe_broadcast` (T1 fan-out) remain as pub/sub fire-and-forget — durable subscribe is a third primitive.

**Unblocks Q15 turn boundary** (turn boundary = `ChannelEvent` impl on this stream) and **Q27 bubble-up** (aggregator subscribes to descendant streams via this primitive).

---

## Q17 — Per-channel total event ordering invariant (REAL-3 reframed) ✅ RESOLVED (Phase 4, 2026-04-25)

**What:** Game intent — everyone in a channel sees events in the same order.

**Resolution:** [DP-A15](02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25) locks per-channel total ordering as an axiom. `channel_event_id: u64` monotonic per channel, gapless, enforced via DB UNIQUE constraint `(reality_id, channel_id, channel_event_id)`. Reality-scoped events retain per-aggregate / per-session ordering per [02_storage R7](../02_storage/R07_concurrency_cross_session.md). Concrete mechanism in [13_channel_ordering_and_writer.md DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism).

---

## Q18 — T1 tier reframed for channel presence (REAL-4 reframed)

**What:** [DP-T1](03_tier_taxonomy.md#dp-t1--volatile) Volatile was designed around 30Hz position updates in an MMO. Turn-based has no use case for that. In channel model, T1 has a natural home: **channel presence state** ("who is currently in this tavern", "who is typing in this cell"). Lower QPS than MMO-T1.

**Why significant (not blocker):** Current T1 eligibility rule says "write rate ≥ 1 per second sustained per aggregate" — channel presence doesn't meet that. Features will be pushed toward T2 unnecessarily; or the T1 eligibility rule needs updating.

**Candidate resolution path:** Reframe [DP-T1](03_tier_taxonomy.md#dp-t1--volatile) examples and eligibility — option (c) from the review: keep 4 tiers but redefine T1 as "channel presence, typing, hover — low QPS transient state".

---

## Q19 — Per-channel pause / reality-pause semantics (REAL-5 reframed)

**What:** When an NPC LLM is "thinking" in a cell, is the cell paused (no writes accepted)? Do other cells in the same tavern continue? Does a tavern-level pause (narration pause) freeze all child cells?

**Why significant:** LLM turn coordination + channel freeze are central game mechanics. DP contract has no primitive; features will invent inconsistent approaches.

**Candidate resolution path:** **DP-K15** `channel_pause(ctx, channel_id, reason, expected_resume_at)` + `channel_resume` + `SessionContext.paused_channels` flag set. Writes to paused channel return `DpError::ChannelPaused`.

---

## Q20 — LLM turn latency is the real hot-path bottleneck (REAL-6 unchanged)

**What:** LLM calls 1–10 s dominate any DP latency. [DP-S*](08_scale_and_slos.md) numbers (50 ms T3 ack, 500 CCU per reality throughput targets) are over-specced relative to what the game actually needs. Real perf concern is LLM throughput per reality and queue depth per player.

**Why significant:** May indicate DP-S numbers should be rescaled downward (less over-engineering) — but premature to rescale without V1 data.

**Candidate resolution path:** Defer quantitative rescale to V1 prototype data. In parallel, design **LLM turn slot** primitive: reservation + cancellation + priority queue per channel. Out of DP SDK scope; feature-level (roleplay-service), but DP may need to expose channel-pause + event cancellation hooks.

---

## Q21 — T2 read-your-writes across service boundary within session (D3 from prior review)

**What:** Service A does `t2_write`, acks on cache + outbox. Service A calls Service B within the same session. B does `read_projection` — projection hasn't caught up (async ≤1 s). B sees stale. Read-your-writes is broken across service boundaries within the same session.

**Candidate resolution path:** Intra-session causality token. `T2Ack` returns a token; subsequent `read_projection` with `wait_for_token` waits until projection reflects it. Added to [DP-K4](04_kernel_api_contract.md#dp-k4--read-primitives) / [DP-K5](04_kernel_api_contract.md#dp-k5--write-primitives-tier-typed).

---

## Q22 — WrongWriterNode retry + routing protocol (D4 from prior review)

**What:** SDK returns `DpError::WrongWriterNode` when a request reaches the wrong node (LB glitch, sticky cookie expired, session re-pinned). What is the retry protocol? How does the gateway learn the correct node?

**Candidate resolution path:** SDK response includes `correct_node` hint (from CP lookup cache); gateway uses hint to re-route. Or feature-level retry with bounded attempts. Spec in Phase 4.

---

## Q23 — Histogram bucket granularity (O1 from prior review)

**What:** `dp.{op}.latency_ms{...}` default Prometheus buckets (5, 10, 25, 50, 75, 100, ...) have poor resolution in the 0–10 ms range where hot-path p99 targets live. Need exponential buckets around the SLO targets.

**Candidate resolution path:** Operational doc — specify bucket layout per metric. Not a design-doc change.

---

## Q24 — Telemetry cardinality blow-up (O2 from prior review)

**What:** 10 k realities × 50 aggregate types × 3 ops × several tags → millions of unique Prometheus series. Under channel model, add `channel_id` tag → orders of magnitude worse.

**Candidate resolution path:** SDK-side roll-up; don't emit per-reality per-aggregate series; aggregate in-process and emit rate-per-service. Or sampling. Ops doc + DP-K8 update.

---

## Q25 — Capability signing key rotation window (S1 from prior review)

**What:** Quarterly rotation leaves a 90-day window where a stolen signing key is valid. For a hobby project this is a tradeoff; for a platform product at V3 this window is large.

**Candidate resolution path:** Monthly rotation + passport-style revocation signal broadcast on hot path. Or accept 90-day as project-appropriate. Decision deferred to platform-mode launch (separate track).

---

## Q26 — Channel hierarchy as first-class DP concept (NEW-1) ✅ RESOLVED (Phase 4, 2026-04-25)

**What:** DP needed `channel_id` as a nested scope within reality; cache key, `SessionContext`, capability claims, event-log schema all needed the channel dimension.

**Resolution:**
- **[DP-A13](02_invariants.md#dp-a13--channel-hierarchy-as-first-class-scope-phase-4-2026-04-25)** Channel hierarchy as first-class scope — tree structure per reality, free-form `level_name` tag, DP agnostic to semantics.
- **[DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25)** Aggregate scope = design-time marker trait choice (`RealityScoped` vs `ChannelScoped`).
- **[12_channel_primitives.md](12_channel_primitives.md)** DP-Ch1..Ch10 — `ChannelId` newtype, per-reality-DB registry schema, CP cache + Redis Stream delta, scope marker traits, cache-key format with `r`/`c` marker, SessionContext extension, ancestor lookup, CRUD primitives, `move_session_to_channel`, tree-change invalidation.
- **[DP-K1/K2/K4/K7/K10/K12 updated](04_kernel_api_contract.md)** with `ChannelId`, scope markers, scope-typed reads, scope-dispatched `cache_key!`, `move_session_to_channel` + `create_channel` + `dissolve_channel` primitives.
- **[DP-C1/C3 updated](05_control_plane_spec.md)** — channel tree cache added to CP responsibilities; 3 new gRPC methods (`GetChannelTree`, `StreamChannelTreeUpdates`, `ResolveAncestorChain`).

**Unblocked Phase 4 items:** Q17, Q30, Q34 (per-channel ordering + writer binding — next cluster), Q15, Q16, Q27 (blockers), Q18, Q19, Q28, Q31, Q32 (semantics).

---

## Q27 — Event bubble-up primitive (NEW-2, blocker)

**What:** Aggregator reads events at channel level L, probabilistically emits event at level L+1 (with random threshold). Who runs the aggregator? Per-channel actor? CP-owned? Feature-level? Random seed must be deterministic for event-log replay consistency.

**Why blocker:** Bubble-up is a central canonical mechanic. Without a DP primitive, features can't express it consistently.

**Candidate resolution path:** **DP-K16** `register_bubble_up_aggregator(ctx, source_channel_id, target_channel_id, config) -> AggregatorHandle` + **DP-K17** `deterministic_rng_for_channel(ctx, channel_id, event_id) -> Rng` (seed = event_id for replay). Aggregator = SDK-owned actor running on the writer node of the target channel.

---

## Q28 — Channel membership ops (NEW-3)

**What:** Player joins cell / leaves tavern / NPC migrates between cells. Frequency: medium. Membership change tier? Validation ownership (feature vs DP)? Privacy (who can see "player X entered tavern Y")?

**Candidate resolution path:** Membership ops are T3 writes (canonical: "player X entered tavern Y at channel_event_id N"). DP exposes `join_channel(ctx, channel_id)` / `leave_channel(ctx, channel_id)` primitives. Validation rules (capacity, prerequisites) are feature-level.

---

## Q29 — Fan-out width at higher channels (NEW-4)

**What:** Country event → all 500 players in country see it. Wide but infrequent fan-out. Memory cost of per-player subscription to 6 channel levels × multiple realities (for spectators).

**Candidate resolution path:** Subscription batching by node — one subscriber per channel per game-node, fan-out to local session clients. Reduces Redis subscribers from O(players) to O(nodes). Ops-doc scope mostly.

---

## Q30 — Per-channel total ordering mechanism (NEW-5) ✅ RESOLVED (Phase 4, 2026-04-25)

**What:** Concrete implementation of Q17's invariant.

**Resolution:** [13_channel_ordering_and_writer.md DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism). Single writer maintains in-memory counter per channel, seeded from `MAX(channel_event_id)` query at writer takeover, gaplessness via DB UNIQUE constraint. Reality-scoped events keep `channel_id = NULL` and use existing R7 ordering. Recovery on writer crash via re-query MAX. Schema extension to `event_log` documented in DP-Ch11.

---

## Q31 — Channel lifecycle (NEW-6)

**What:** Cell sessions are created when a conversation starts, dissolved when members leave. Tavern/town/country: persist for reality lifetime? Can a channel freeze and reactivate independently of its reality's freeze?

**Candidate resolution path:** Channel lifecycle state machine: `active → dormant → dissolved`. Plug into [02_storage R9](../02_storage/R09_safe_reality_closure.md) lifecycle. Events in dissolved channels archived but searchable.

---

## Q32 — Privacy bubble-up (NEW-7)

**What:** A private cell (secret meeting) emits events. Aggregator reads them for bubble-up. Does bubble-up leak the private cell's existence into tavern events?

**Candidate resolution path:** Channels have visibility flag; aggregator respects visibility — skips private-channel events OR emits tavern event with redacted source. Feature-level design refinement; DP primitive exposes the visibility flag.

---

## Q33 — Retention per channel level (NEW-8)

**What:** Cell events: high volume, short retention feasible (30 days). Country events: low volume, long retention (canon-level importance). Current [02_storage R1](../02_storage/R01_event_volume.md) retention is per-reality, flat.

**Candidate resolution path:** Per-channel-level retention config in CP tier_policy. Ops + 02_storage coordination.

---

## Q34 — Channel writer node binding (NEW-9) ✅ RESOLVED (Phase 4, 2026-04-25)

**What:** Single-writer-per-channel discipline + assignment + handoff protocol.

**Resolution:** [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) axiom locks single-writer per active channel. Detailed in [13_channel_ordering_and_writer.md DP-Ch12..Ch14](13_channel_ordering_and_writer.md#dp-ch12--writer-assignment-rules):
- **Cell channels:** writer = creator's session node; CP coordinates handoff on creator-leave; handoff p99 ≤200ms.
- **Non-cell channels (tavern+):** writer = CP-assigned at creation, persistent for lifetime; reassigned on node death (≤35s).
- **Cross-node writes:** SDK transparently routes via gRPC `RouteChannelWrite` (DP-Ch14); ~5ms LAN hop cost. Feature code unchanged.
- **Epoch fencing:** monotonic per channel, stored in `channel_writer_state` table; rejects writes from stale writers (DP-Ch13).
- **Composes with [DP-A11](02_invariants.md#dp-a11--session-node-owns-t1-writes):** T1 writer = session node; ChannelScoped T2/T3 writer = channel-bound node. No conflict.

---

## Phase 4 resolution plan

Work through the list in dependency order:

1. **First:** Q26 (channel first-class) + Q17/Q30 (per-channel ordering + writer binding) — these unblock everything else.
2. **Then:** Q16 (durable subscribe), Q15 (turn boundary), Q27 (bubble-up primitive) — blockers that depend on channel being defined.
3. **Then:** Q19 (pause), Q28 (membership), Q31 (lifecycle), Q18 (T1 reframe) — channel semantics refinements.
4. **Then:** Q21 (T2 RYW), Q22 (WrongWriterNode UX), Q29 (fan-out), Q32 (privacy), Q34 if not already resolved — remaining gaps.
5. **Ops doc:** Q23, Q24, Q25, Q33 — not design-doc work.
6. **Defer:** Q20 (LLM turn latency) — V1 prototype data needed.

Each Phase 4 mini-session picks one Q (or a tight cluster), resolves it, locks new axioms / rules / primitives, adds a new file or extends existing ones. Status tracked here.
