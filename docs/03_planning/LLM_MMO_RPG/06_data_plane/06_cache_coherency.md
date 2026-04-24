# 06 — Cache Coherency Protocol (DP-X1..DP-X10)

> **Status:** LOCKED (Phase 2). Defines the cache coherency model for each tier, the invalidation message protocol, storm mitigation, failure modes, and consistency guarantees. Resolves [Q4](99_open_questions.md) (invalidation storm), partial [Q10](99_open_questions.md) (in-process second layer).
> **Stable IDs:** DP-X1..DP-X10.

---

## DP-X1 — Coherency model per tier

Each tier has a distinct coherency model. Features pick a tier ([DP-T0..T3](03_tier_taxonomy.md)) which binds them to one of these models — no mixing.

| Tier | Coherency model | Read-your-writes | Cross-session visibility |
|---|---|---|---|
| **T0** | No coherency (in-process only) | Trivial — only the writer has the data | N/A (not shared) |
| **T1** | Snapshot coherency | Writer's in-memory is authoritative until next snapshot | Eventual, bounded by pub/sub broadcast latency (≤100ms) |
| **T2** | Write-through + async invalidate | Within-session: immediate (cache written before ack). Cross-session same-node: ≤1ms (in-process invalidation). Cross-node: ≤100ms (pub/sub). | Eventual; worst-case = projection-catchup lag (≤1s) |
| **T3** | Synchronous invalidate-before-ack | Always consistent. Ack returns only after invalidation is fanned out and acknowledged. | Strong — all readers see the new value before the writer's ack returns. |

**The model is the contract.** Features that need stronger guarantees than their tier provides must move up a tier or accept the limitation. There is no runtime flag to upgrade coherency without upgrading tier.

---

## DP-X2 — Invalidation message protocol

### Channels

One Redis pub/sub channel per reality for invalidations: `dp:inval:{reality_id}`.

Separately, a per-reality audit stream `dp:inval:audit:{reality_id}` (Redis Stream, not pub/sub) captures every invalidation for debugging and CP observability. Fire-and-forget; data-plane ops do not block on stream writes.

### Message shape

Published as a MessagePack-encoded blob for compactness and schema-evolution safety:

```
{
  "v": 1,                         // schema version
  "ts": 1713999999_123,           // unix millis
  "tier": "T3",                   // "T1" | "T2" | "T3"
  "agg": "player_inventory",      // aggregate type name
  "id": "p_<uuid>",               // aggregate id (string form)
  "writer_node": "game-node-42",  // origin (for self-filter)
  "txn_id": "tx_<uuid>"           // optional, set for t3_write_multi
}
```

**Schema evolution:** `v` field gates the decoder. Readers accept `v <= known_max` and ignore unknown optional fields. Breaking changes (rare) require a new `v` and a coordinated rolling deploy.

### Self-filter

Each SDK instance includes its `node_id` in publishes and filters incoming messages where `writer_node == self.node_id` — the writer has already applied the change locally via the write path, no need to re-invalidate.

### Ordering

Redis pub/sub is best-effort, unordered across publishers, ordered per-publisher. DP does not require global ordering — invalidation is idempotent (drop cache entry whether ordered or not). However, **T3's synchronous-invalidate model does require delivery ACK within the 20ms window** (DP-X5), which Redis pub/sub provides via the PUBLISH return count of subscribers reached. If the count is below expected, SDK retries or falls back to fail-safe (invalidate everything for that aggregate type, see DP-X10).

---

## DP-X3 — Cache population strategy

### Lazy on miss

Default for T2 and T3 reads:

1. SDK issues `read_projection<A>(ctx, id)`.
2. Compute cache key (`dp::cache_key!`).
3. Try Redis `GET` — hit returns immediately (≤10ms).
4. Miss → read projection from Postgres (≤50ms) → populate cache with TTL (DP-X7) → return.

### Proactive hotset (cold-start)

On reality `frozen → active` transition, the CP signals game service to pre-populate cache for aggregates in the **reality hotset** — a learned set of "most-read at V3 peak" aggregate types per reality.

Hotset membership:
- Derived from metrics aggregated over the reality's last 24h of active time before freezing
- Stored by CP as `reality_hotset(reality_id, aggregate_type, priority)`
- V1/V2 uses a static default hotset (player + session + region aggregates); learning is V3

Pre-warm happens in parallel with first-session bind, not blocking the first player's connection.

### Write-triggered population

T2 and T3 writes update the cache **before** returning from the SDK write call (write-through), so subsequent reads on the same node hit the cache.

T1 writes update in-memory state (not Redis) and publish a broadcast; the broadcast subscriber side may populate its own view if it holds one.

---

## DP-X4 — Invalidation storm mitigation

The problem: a T3 write invalidates a hot aggregate; N SDK instances all drop the cache entry simultaneously; next read from each hits Postgres; thundering herd of N reads against one projection row.

### Three-layer mitigation

**Layer 1 — Singleflight deduplication (per SDK instance)**

Each SDK instance has an in-process `singleflight` map keyed by cache-key. If multiple concurrent reads miss and both would hit Postgres, they coalesce: the first read issues the Postgres query, subsequent concurrent requests wait on the first's future. Prevents N→1 within a single node.

**Layer 2 — Stale-while-revalidate (SWR, 20s grace)**

On invalidation, cache entry is marked **stale** but not deleted. Reads during the stale window:
- Return the stale value immediately (≤10ms — avoids blocking on Postgres)
- Trigger an **async** revalidation: one singleflight Postgres read per node to refresh the entry

After the 20-second grace window, stale entries are deleted. Reads past that point fall back to lazy-on-miss (DP-X3).

**SWR + singleflight combination** means at most 1 Postgres read per node per invalidated key during the 20-second window, regardless of read QPS. N-node worst case = N reads, not N × QPS.

**Layer 3 — Jittered repopulation for hot keys**

For aggregates in the reality hotset (DP-X3), CP explicitly triggers a **jittered re-population** on invalidation: each SDK instance receives the invalidation + a random delay (0–2s) before it revalidates. Spreads the N-node Postgres reads across 2 seconds rather than bunching at t=0.

### Not-solved cases

Cold cache + genuine N-node thundering herd on first read after a reality warms up: mitigated by hotset pre-warm (DP-X3) + singleflight, but not fully eliminated. V2 benchmark target: observe <2× sustained-QPS spike at reality-warm transitions. Exceed → add CP-orchestrated pre-warm sequencing.

---

## DP-X5 — Cross-node propagation latency

Latency budget from a T3 write ack back to all subscribers having dropped the invalidated entry:

| Hop | Budget (p99) | Detail |
|---|---:|---|
| Writer commit → Redis PUBLISH | ≤5 ms | Local Redis |
| Redis PUBLISH → subscriber node receives | ≤10 ms | LAN / region-local |
| Subscriber receive → local cache invalidate | ≤5 ms | In-process |
| **Total fanout (DP-T3 budget)** | **≤20 ms** | Matches [DP-T3 definition](03_tier_taxonomy.md#dp-t3--durable-sync) |

T3 write ack returns only after the SDK has confirmed the PUBLISH reached the expected subscriber count (Redis returns subscriber count on PUBLISH). If count is short, SDK waits briefly (up to 20ms), then falls back to fail-safe (DP-X10).

T2 writes publish the same message but **do not wait** — ack returns as soon as local cache is updated and outbox is written.

---

## DP-X6 — In-process second cache layer (opt-in)

[DP-A4](02_invariants.md#dp-a4--redis-is-the-cache-technology) permits an optional in-process cache on top of Redis. DP-X6 defines when to enable and how.

### When to enable

Off by default. Enable per-aggregate-type via CP admin when:

- Redis round-trip is dominant in the aggregate's read latency budget (typically for T1 broadcast fan-out observed on hot player-position reads)
- Aggregate is small (≤1KB serialized) and read many times per second per subscriber

### Rules (when on)

- **TTL:** 1 second maximum (short — the in-proc layer is for bursty same-aggregate reads within a single frame, not steady-state).
- **Invalidation:** subscribes to the same Redis pub/sub channel as the Redis-level cache; drops in-proc entry on any invalidation.
- **Capacity:** bounded LRU per aggregate type (e.g., 10k entries × ~1KB = 10MB — sized per service).
- **Consistency:** always weaker than the Redis-level cache. Features that need stronger consistency opt out.

### Telemetry

Separate counter `dp.cache.inproc.hit_rate` distinct from `dp.cache.redis.hit_rate`. Dashboard alarm if inproc cache's staleness exceeds the Redis-level cache's by more than the configured TTL — indicates invalidation loss or misconfiguration.

---

## DP-X7 — Cache TTL defaults per tier

| Tier | Default TTL | Rationale |
|---|---:|---|
| T0 | N/A | Not cached — in-proc only |
| T1 | 60 s | Matches snapshot cadence × 6; idle aggregates drop from Redis naturally |
| T2 | 5 min | Covers typical session activity window; projection readback on miss is OK |
| T3 | 10 min | Longer TTL acceptable — T3 writes invalidate proactively, TTL is a backstop |

**Override:** CP `tier_policy` allows per-aggregate TTL overrides. Default suffices for ≥90% of aggregate types.

**No infinite TTL.** Every cache entry has an expiry; an invalidation loss plus an infinite TTL = permanent stale read. Cap is 1 hour even for overrides.

---

## DP-X8 — Eviction policy

Redis configured `maxmemory-policy allkeys-lru` for the DP cache instance. LRU evicts cold entries first.

### Per-reality memory isolation

[DP-S6](08_scale_and_slos.md#dp-s6--cache-sizing) sizes ~170 MB per heavily-populated reality, ~50 GB total working set. Default Redis is shared — one hot reality can evict a cold reality's working set under pressure.

**V1/V2:** single shared Redis; accept the noisy-neighbor risk (small realities, low memory pressure expected).

**V3 hardening option (deferred):** Redis Cluster with hash-tag sharding on `{reality_id}` — each reality lives on a specific shard. Memory pressure confined. Sharding decision is [Q3](99_open_questions.md).

### Sensitive-tier eviction priority

T3 cache entries are the most expensive to repopulate (synchronous projection read + invalidation fanout). To give T3 entries a small TTL-based priority, SDK writes T3 entries with a slightly longer TTL refresh on read hit — effectively bumping them up the LRU chain. Tunable per deployment.

---

## DP-X9 — Consistency guarantees summary

Quick reference for feature designers.

| Scenario | T0 | T1 | T2 | T3 |
|---|---|---|---|---|
| Writer reads its own write | Immediate | Immediate (in-memory) | Immediate (cache) | Immediate (cache) |
| Other session, same node, reads after writer's ack | N/A | ≤ broadcast latency (~100ms) | ≤ in-proc inval (1ms) | Immediate (cache is coherent before ack) |
| Other session, other node, reads after writer's ack | N/A | ≤ broadcast latency (~100ms) | ≤ pub/sub fanout (~100ms) | Immediate (ack waits for fanout) |
| After cache TTL expires + no update | N/A | Snapshot reload | Projection read (≤50ms) | Projection read (≤50ms) |
| After invalidation loss | N/A | Next snapshot (≤30s) | Next TTL (≤5min) | Next TTL (≤10min) |
| Cross-reality read | Denied | Denied | Denied (coordinator) | Denied (coordinator) |

"Denied" = SDK returns `DpError::CapabilityDenied`, cross-reality requires explicit coordinator API ([Q11](99_open_questions.md), out of scope for Phase 2).

---

## DP-X10 — Failure modes + fail-safe

### Cache node failure

- SDK detects via Redis client's error; sets `dp.cache.available = 0`.
- **Reads** degrade to direct projection reads (all miss the cache). Throughput drops, latency rises from ~10ms to ~50ms p99.
- **T2 writes** continue — cache update is best-effort; outbox (durable) is authoritative. On cache recovery, next read populates from projection.
- **T3 writes** block on invalidation fanout — which can't happen without Redis. SDK returns `DpError::CircuitOpen { service: "redis" }` for T3 writes until Redis recovers.

### Invalidation loss (pub/sub message dropped)

- Single message loss is silent. Stale-while-revalidate bounds the window (20s grace + TTL).
- Detection: CP's audit stream `dp:inval:audit:{reality_id}` tracks expected invalidations per writer. Mismatch between audit count and subscriber-report count (subscribers periodically report received counts to CP) signals suspected loss.
- Recovery: CP issues a **fail-safe broadcast** on the channel `dp:inval:{reality_id}:failsafe` with `{aggregate_type}` — subscribers drop ALL entries for that aggregate type. Coarse but correct.

### Split-brain (SDK instance partitioned from Redis)

- SDK detects stale Redis subscription (no keepalive for 30s) → forces full local cache drop → reverts to lazy-on-miss until reconnected.
- On reconnect, SDK consumes the last 60s of audit stream to catch up missed invalidations, then resumes normal operation.

### Redis replica lag

- If Redis is replicated (V3 topology decision), reads from a lagging replica can miss very recent writes.
- **Policy:** SDK reads from primary for T3 hot-path reads (same Redis cluster, not replica); replicas are for T2 fallback and observability.

---

## Summary

| ID | What it locks |
|---|---|
| DP-X1 | Per-tier coherency model: no / snapshot / write-through-async / sync-invalidate |
| DP-X2 | Redis pub/sub channel `dp:inval:{reality_id}` + MessagePack payload + self-filter |
| DP-X3 | Lazy-on-miss + proactive hotset + write-through |
| DP-X4 | Singleflight + SWR 20s + jittered repopulation for hotset — invalidation storm solved |
| DP-X5 | Cross-node fanout budget ≤20ms (matches T3 ack budget) |
| DP-X6 | Optional in-proc second cache, off by default, 1s TTL, LRU-bounded |
| DP-X7 | Default TTL per tier: T1=60s, T2=5min, T3=10min; 1h cap on overrides |
| DP-X8 | Redis LRU eviction; V3 Redis Cluster hash-tag sharding deferred to Q3 |
| DP-X9 | Consistency guarantee matrix per scenario |
| DP-X10 | Failure modes: cache down, invalidation loss, split-brain, replica lag — with fail-safe broadcast |

---

## Cross-references

- [DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split) — CP is never on the invalidation hot path
- [DP-A4](02_invariants.md#dp-a4--redis-is-the-cache-technology) — Redis for cache + pub/sub
- [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys) — per-reality key prefix enables channel isolation
- [03_tier_taxonomy.md](03_tier_taxonomy.md) — per-tier consistency semantics
- [04_kernel_api_contract.md DP-K6](04_kernel_api_contract.md#dp-k6--subscription-primitives) — `subscribe_invalidation` API
- [05_control_plane_spec.md DP-C6](05_control_plane_spec.md#dp-c6--invalidation-broadcast-orchestration) — CP orchestration side
- [08_scale_and_slos.md DP-S8](08_scale_and_slos.md#dp-s8--resource-ceilings-per-reality) — pub/sub fan-out budget

---

## Deferred

- **Q3 Redis topology** — single cluster vs sharded-per-reality; impacts DP-X8 noisy-neighbor story. Decision when V2 ramp data exists.
- **Q7 Redis operational cost** — ops/infra concern, not coherency protocol concern.
- **Hotset learning algorithm** (DP-X3 proactive hotset) — V3; V1/V2 uses static default.
- **Cross-region replication** — out of scope for Phase 2; aligns with V3 HA plan.
