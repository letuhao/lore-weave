# 08 — Scale Targets and SLOs

> **Status:** LOCKED. Anchor numbers for V1/V2/V3 and per-tier latency/throughput targets. Every Phase 2/3 design derives from these numbers.
> **Stable IDs:** DP-S1..DP-S8.

---

## DP-S1 — Stage anchor numbers

The data plane is sized for V3 but V1 and V2 are subsets of the same architecture — the SDK, control plane, and tier model are the same. Numbers below are the ceilings each stage designs for.

| Stage | Concurrent players / reality | Total concurrent players | Realities active concurrently | Scope of DP exercised |
|---|---:|---:|---:|---|
| **V1 — Solo RP** | 1 | ~10s (across users) | ~10s | T2/T3 only; T0/T1 not exercised |
| **V2 — Coop scene** | 2–4 | ~100s | ~100s | All tiers exercised lightly |
| **V3 — MMO-lite** | **200–500** | **~10 000** | ~1000 | All tiers under peak load |

**Design target:** V3. Everything below is V3 ceiling unless otherwise stated.

V3 = 10k total players distributed across ~1000 active realities, 200–500 players per heavily-populated reality, most realities with <50 players. Heavy realities are the scaling test.

---

## DP-S2 — Latency budget (client-perceived)

| Operation | Budget (p99) | Stage applies |
|---|---:|---|
| Player action → own-client ack | **50 ms** | V2+ |
| Player action → other players see (broadcast) | **200 ms** | V2+ |
| Cross-reality read | No guarantee — bounded-staleness, seconds-scale | V3 |
| Cold-start of a reality (frozen → active, first player) | ≤10 seconds | V3 |

Own-client ack budget includes network RTT from client to gateway + gateway to game service + SDK ack. Out of 50ms p99, ~10ms is network (LAN/region-local), ~40ms is the game service + SDK.

Broadcast budget: 50ms (writer ack) + 100ms (pub/sub fan-out) + 50ms (subscriber delivery) = 200ms p99.

---

## DP-S3 — Per-tier write latency targets (SDK-internal, p99)

Measured from SDK call entry to SDK call return. Excludes client network RTT. These are the budgets each tier must fit within so that DP-S2 is achievable end-to-end.

| Tier | p99 write latency | Notes |
|---|---:|---|
| DP-T0 | <1 ms | In-process memory write. Dominated by Rust call overhead. |
| DP-T1 | <10 ms | In-process + Redis pub/sub publish. Snapshot flush async. |
| DP-T2 | <5 ms ack, ≤1 s to projection | Ack on cache+outbox; projection catches up async. |
| DP-T3 | <50 ms ack | Sync event log + projection + invalidation broadcast. |

T3 is the expensive tier by design. Features that hit T3 every tick are a design error — tier choice must minimize T3 frequency.

---

## DP-S4 — Per-tier read latency targets (SDK-internal, p99)

| Tier | p99 read latency | Source |
|---|---:|---|
| DP-T0 | <1 ms | In-process memory. |
| DP-T1 | <10 ms | Redis GET. |
| DP-T2 | <10 ms cache hit / <50 ms cache miss | Redis GET → fallback projection read. |
| DP-T3 | <10 ms cache hit / <50 ms cache miss | Same path as T2 reads (cache is shared). After a T3 write, cache is consistent before ack. |

Cache hit rate target: **≥95% at steady state** for T2 and T3 reads. Below 90% is a defect — investigate cache topology, TTL tuning, or invalidation storms.

---

## DP-S5 — Throughput targets at V3 peak

Per-reality peak (worst-case heavily-populated reality at 500 CCU during combat burst):

| Tier | Target sustained | Target burst (5 s) |
|---:|---:|---:|
| T0 writes | Unbounded (in-process) | Unbounded |
| T1 writes | 5 000 / s | 20 000 / s |
| T2 writes | 500 / s | 2 000 / s |
| T3 writes | 50 / s | 200 / s |
| T2/T3 reads | 10 000 / s | 30 000 / s |

**Aggregate across all realities:** T3 ≤50 000/s, T2 ≤500 000/s, reads ≤10 000 000/s. These numbers constrain Redis sizing, Postgres event-log write capacity, and the pub/sub fan-out design.

**T1 burst dominates broadcast load.** 20k T1 writes/s per reality × 1000 realities worst case = 20M pub/sub messages/s globally. In practice V3 has ≤10 heavily-populated realities simultaneously so realistic peak is ~200k/s — manageable by a Redis cluster with sharded pub/sub, but locks a design constraint: T1 pub/sub fan-out must be sharded by reality. (See [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys).)

---

## DP-S6 — Cache sizing

Working-set size per reality at V3 peak:

| Component | Per reality | Notes |
|---|---|---|
| Active player aggregates (T1) | ~500 × ~2 KB = ~1 MB | Position, emote, presence |
| Chat recent history (T2) | ~50 MB | Last ~500 messages × ~100 KB avg with embeddings |
| NPC session memory (T2) | ~20 MB | Per active session, ~50 sessions × ~400 KB |
| Projection hot set (T2/T3) | ~100 MB | Player inventory, active quest state, region state |
| **Total per heavily-populated reality** | **~170 MB** | Realistic upper bound |

**1000 realities × ~170 MB = 170 GB cache.** In practice most realities are light, so realistic total is ~50 GB. A Redis cluster with 3× 32 GB nodes + replicas fits this with headroom. Exact topology deferred to [99_open_questions.md](99_open_questions.md) Q3.

---

## DP-S7 — Availability targets

| Component | Target | Notes |
|---|---|---|
| Data plane SDK (embedded in game service) | Same as game service (typically 99.9%) | Fate-shared with the service process |
| Redis cache cluster | 99.95% | Redis Cluster with replicas; failover ≤30 s |
| Control plane service | 99.9% | HA deployment, ≥2 nodes; failover ≤60 s |
| Durable tier (Postgres per reality) | Per [02_storage/SR01](../02_storage/SR01_slos_error_budget.md) | Unchanged by DP |

**Failure of the control plane does NOT make the data plane unavailable.** Game services continue to read/write through cached tier policy during a CP outage. CP is required for schema migration and cache-namespace rotation, not for hot-path ops. See [DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split).

**Failure of Redis cache** degrades reads to direct projection reads (still <50 ms) and T1 writes to best-effort (broadcast may be lost until recovery). T2/T3 writes continue — outbox and event log are not cache-dependent.

---

## DP-S8 — Resource ceilings per reality

Per heavily-populated reality (500 CCU):

| Resource | Ceiling | Trigger |
|---|---:|---|
| Event log write rate | 500 / s sustained, 2000 / s burst | Per R1 in [02_storage/R01](../02_storage/R01_event_volume.md); DP's T2+T3 fit inside this. |
| Projection DB size growth | ~10 GB / year per active reality | Per R1 storage footprint estimate. |
| Cache memory | 200 MB | DP-S6 + 20% headroom. |
| Pub/sub outbound fan-out | 20 000 msg / s burst | Dominated by T1 broadcasts during combat. |
| SDK CPU overhead on host game service | ≤10% | Budget for cache serialize/deserialize + pub/sub + tier dispatch. |

**Breach of any ceiling triggers backpressure** — the SDK refuses new T1/T2 writes with a `RATE_LIMITED` error, surfaces telemetry, and routes the feature to fall back (e.g., reduce broadcast rate, batch writes). Exact backpressure mechanism deferred to Phase 3 `07_failure_and_recovery.md`.

---

## SLO summary table

| ID | What | Target | Stage |
|---|---|---|---|
| DP-S1 | V3 player scale | 500 CCU/reality, 10k total | V3 |
| DP-S2a | Own-client ack | 50 ms p99 | V2+ |
| DP-S2b | Broadcast | 200 ms p99 | V2+ |
| DP-S2c | Cross-reality read | bounded-staleness seconds | V3 |
| DP-S3 | T3 write ack | 50 ms p99 | V2+ |
| DP-S4 | Cache hit rate | ≥95% | V2+ |
| DP-S5 | T3 write throughput | 50/s per reality, 50k/s global | V3 |
| DP-S6 | Cache per reality | ~170 MB peak, ~50 GB total | V3 |
| DP-S7 | CP availability | 99.9% | V3 |
| DP-S8 | SDK CPU overhead | ≤10% of host service | V3 |

Any Phase 2/3 design that cannot fit these targets must either propose a revised SLO (with supersedence entry in [../decisions/](../decisions/)) or change the design.
