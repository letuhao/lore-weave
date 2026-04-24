# 07 — Failure and Recovery (DP-F1..DP-F10)

> **Status:** LOCKED (Phase 3). Defines the data-plane's behavior during every class of failure — node loss, control-plane outage, Redis failure, split-brain, invalidation loss, replica lag, graceful drain — and the explicit reconciliation protocols that bring it back to consistent state. Closes [Q6](99_open_questions.md) (cold-start fallback), [Q12](99_open_questions.md) (backpressure), and Q5 residuals (migration observability + rollback).
> **Stable IDs:** DP-F1..DP-F10.

---

## Reading this file

This document answers: "when X fails, what does the data plane do, and how does it get back to healthy?" It does **not** redesign how writes or reads work — it describes what happens when the primitives from [04_kernel_api_contract.md](04_kernel_api_contract.md), the control plane from [05_control_plane_spec.md](05_control_plane_spec.md), or the cache layer from [06_cache_coherency.md](06_cache_coherency.md) enter a degraded state.

Every failure mode below has three parts:
1. **Detection** — how the SDK or CP notices the fault
2. **Behavior during the failure** — what ops succeed, which fail, what the user-visible impact is
3. **Recovery** — how healthy state is restored and any missed work is reconciled

---

## DP-F1 — Failure classification matrix

The closed set of failure modes this folder addresses. Anything outside this list is either (a) out of DP scope, or (b) a bug, not a designed failure.

| Failure | Detection signal | Data plane behavior | Recovery |
|---|---|---|---|
| **Game node death** (process crash, k8s pod eviction) | CP health probe miss + load balancer unreachable | Session re-pins to new node; in-flight ops fail; T1 aggregates reload last Redis snapshot (≤30s loss) | DP-F2 |
| **Control plane outage** (active CP down or partitioned) | gRPC dead-peer, stream-close, missed heartbeat | Degraded mode (DP-C9): continue existing ops with cached policy; reject new session binds | DP-F3 |
| **Redis cache failure** (cluster down or partitioned) | Redis client error + keepalive timeout | Reads fall back to Postgres projection (≤50ms); T2 writes continue (outbox is authoritative); T3 writes fail with `CircuitOpen` | DP-F4 |
| **Split-brain** (SDK partitioned from Redis or CP) | No keepalive >30s + gRPC heartbeat loss | Reject writes (consistency preference); serve reads from last-known cache until it goes stale | DP-F5 |
| **Invalidation message loss** (pub/sub drop) | CP audit stream count mismatch | Silent — stale-while-revalidate bounds window to 20s + TTL | DP-F6 |
| **Postgres replica lag** (when replicas used) | Lag metric | Route hot-path reads to primary; non-critical reads tolerate lag | DP-F4 scope |
| **Schema migration failure** (projection rebuild stalls or corrupts) | Progress stalled >30min; integrity checker mismatch | Halt migration; read-path stays on old schema; rollback via DP-F8 procedure | DP-F8 |
| **Backpressure / load shed** (approaching DP-S8 ceilings) | Token bucket near-empty | SDK returns `RateLimited`; feature code surfaces to user as "try again" | DP-F7 |
| **Graceful drain** (planned node removal) | Admin-initiated | New sessions routed elsewhere; existing ops complete before shutdown | DP-F9 |
| **Chaos drill** (injected failure in test) | Test harness flag | All above behaviors exercised in staging | DP-F10 |

**Excluded (out of scope, addressed elsewhere):**

- Total Postgres primary loss — per-reality [02_storage/SR2](../02_storage/SR02_incident_oncall.md) incident response, not DP
- Malicious compromise — infrastructure + security review, not DP ([DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state) threat-model out-of-scope)
- Network partition across regions — V3 DR concern; V1/V2 is single-region
- LLM proposal bus failure — Python outside DP
- Client WebSocket disconnect — feature-layer concern

---

## DP-F2 — Game node death + session handoff

### Detection

Two independent signals:
- **CP health probe** — CP pings each node every 10 s. Three consecutive misses (30 s window) mark the node dead in the CP's node registry.
- **Load balancer reachability** — gateway's LB removes the node on its own failure detection (LB-dependent, typically 5–15 s).

On confirmed death, CP transitions affected sessions to `migrating` state.

### Behavior during

- **In-flight ops on the dead node:** all fail. Client receives WebSocket disconnect or request error. T1 writes that reached the node but not yet snapshotted to Redis are lost (≤30 s window per [DP-T1](03_tier_taxonomy.md#dp-t1--volatile)). T2 writes that committed to outbox are **not** lost (outbox is on Postgres, survives node death) — but the ack may not have reached the client.
- **Other nodes:** unaffected. Continue normal operation.
- **Sessions on the dead node:** marked `migrating`; new ops for these sessions are rejected with `DpError::WrongWriterNode` until re-pinning completes.

### Recovery

1. **CP identifies replacement node** — uses load-balancer hash or explicit assignment; avoids nodes already above DP-S8 per-node capacity.
2. **New node binds session** — `bind_session(reality_id, session_id)` issued from new node. CP issues fresh JWT (new `node_id` in claims).
3. **T1 aggregate reload** — new node's SDK reads the last T1 Redis snapshot for each aggregate owned by the session. Cold-start budget from [DP-X3](06_cache_coherency.md#dp-x3--cache-population-strategy) applies.
4. **Client reconnect** — gateway routes the next WebSocket request to the new node (via updated sticky-cookie or LB rule). Client sees brief disconnect + reconnect; session feels continuous.
5. **Ack reconciliation** — T2 writes whose ack was lost in transit are idempotent on retry by the client (feature responsibility: retry + dedupe via client-side request id). The outbox entry has already been written; retry is a no-op at DP level.

**Total session handoff latency p99:** ≤ 5 s from node death to session usable on new node (excluding reality cold-start if that's also required).

---

## DP-F3 — Control plane outage + recovery

### Detection

SDK-side:
- gRPC stream close on any of `StreamTierPolicyUpdates`, `StreamRealityTransitions`, `StreamInvalidationAudit`
- gRPC call timeout on a sync RPC (3 × RTT baseline, default ~300 ms)
- Explicit health probe every 10 s — 3 consecutive fails marks CP unreachable

SDK emits metric `dp.control_plane.reachable = 0` and structured log with the observed error. Passive CP node (see [DP-C2](05_control_plane_spec.md#dp-c2--deployment-model)) may already be promoting; SDK retries connect to the failover address before declaring outage.

### Behavior during (degraded mode)

Per [DP-C9](05_control_plane_spec.md#dp-c9--degraded-mode):

- **Existing sessions continue** — cached tier policy + unexpired JWTs support ongoing reads and writes.
- **Capability refresh is paused** — SDK does not retry refresh against a known-down CP; waits for reconnect signal.
- **New session binds rejected** — gateway queues player connects or surfaces "warming up" to the user.
- **`t3_write_multi` rejected** — cross-aggregate atomic writes require CP coordination for txn correlation. Single T3 writes still work.
- **Schema migrations are paused** — any migration in progress halts at a safe step; no new migrations can start.
- **Invalidation broadcast still works** — SDK publishes to Redis directly; CP only audits. Audit-based reconciliation (DP-F6) is paused during CP outage.

### Recovery

1. **Passive CP promotes or failed CP restarts.** etcd leader election completes within 10 s of active loss; passive becomes active.
2. **SDK reconnect** — each SDK detects CP reachable, issues a `Health` RPC, then `GetTierPolicy` to refresh its snapshot (diff-based — only updates since last-seen version are returned).
3. **Capability refresh resumes** — expired JWTs trigger `refresh_capability` in the background; services accumulated during outage catch up.
4. **Audit reconciliation** — CP replays missed audit entries from Redis stream `dp:inval:audit:{reality_id}`; any discrepancy with subscriber counts triggers fail-safe broadcast (DP-F6).
5. **Paused migrations resume** — migration coordinator reads last-known-state from CP storage and continues.

**Degraded-mode duration ceiling:** 15 min before system quality degrades significantly (stale tier policy + growing count of expired capabilities). V1/V2 SLO per [DP-C9](05_control_plane_spec.md#dp-c9--degraded-mode). V3 targets ≤5 min typical with HA improvements.

---

## DP-F4 — Cache layer failure

### Redis unreachable / cluster failure

**Detection:** SDK's Redis client emits connection errors; keepalive fails >5 s; metric `dp.cache.available = 0`.

**Behavior:**

| Operation | During Redis failure |
|---|---|
| T2/T3 read (cache hit path) | Skip cache; go direct to Postgres projection (≤50 ms instead of ≤10 ms) |
| T2 write | Cache write is best-effort; outbox (Postgres) is authoritative. Writes continue. |
| T3 write | Requires invalidation broadcast via Redis. **Fails** with `DpError::CircuitOpen { service: "redis" }`. Feature must queue or surface error. |
| T1 write | In-memory update continues; snapshot to Redis fails silently (retried on recovery); broadcast fails (subscribers see stale). |
| `subscribe_invalidation` | Stream stops delivering; subscribers notice via stream close event and switch to conservative-stale mode (treat all cached entries as potentially stale beyond their TTL). |

**Recovery:**

1. Redis cluster returns; SDK reconnects and resumes ops.
2. SDK reads the last 60 s of `dp:inval:audit:{reality_id}` stream to catch missed invalidations and drops matching cache entries.
3. T1 aggregates whose in-memory state diverged from (non-existent) Redis snapshot during outage are snapshotted once on recovery.
4. T3 write circuit closes as cache ops succeed; feature code retries queued writes.

### Postgres replica lag (when replicas used)

**Detection:** replica lag metric exceeds threshold (e.g., 1 s).

**Behavior:** SDK's read path auto-routes hot-path T3 reads to the primary (where T3 writes are sync-committed); T2 read cache misses continue to hit replicas (slight staleness tolerated at T2 semantics anyway).

**Recovery:** passive — resumes when lag returns below threshold. No explicit action.

---

## DP-F5 — Split-brain detection + reconciliation

### Scenarios

- **SDK ↔ Redis partition** — SDK cannot reach Redis but Redis is alive for other SDKs. Unilateral from the affected SDK's perspective.
- **SDK ↔ CP partition** — similar, one SDK isolated.
- **Redis cluster partition** — two halves of Redis cluster operate independently (rare with Redis Cluster, but possible).

### Preference: Consistency over Availability

Per DP-F1 and [DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split), the data plane prefers consistency when faced with uncertainty. Partitioned SDKs:

- **Stop accepting T3 writes** (sync invalidation cannot be guaranteed across the partition).
- **Continue T2 writes to outbox** — outbox is local to the session's Postgres, not partitioned; T2 ack is on outbox + local cache. Invalidation broadcast may not reach far side until partition heals.
- **Continue T1 writes in-memory** — broadcast is best-effort anyway for T1.
- **Continue reads** with stale flag logged; SWR grace window applies.

### Detection

- Redis client: keepalive absent >30 s → partition suspected.
- CP connection: three consecutive health probe misses → CP unreachable.
- Sticky-routing mismatch: SDK receives a `t1_write` intended for a session it no longer owns → cross-network issue suspected.

### Reconciliation on partition heal

1. SDK reconnects Redis + CP.
2. SDK reads last 60 s audit stream for missed invalidations.
3. SDK's local cache drops entries matching audited invalidations.
4. T3 writes that were rejected during partition are NOT retried by DP — feature code receives the error and decides (retry, queue, surface).
5. CP verifies the SDK's last-known tier-policy version vs current; pushes delta via `StreamTierPolicyUpdates`.

**Split-brain blast radius:** bounded by partition duration × T3 write rate. At V3 peak T3 rate 50 writes/s/reality × typical partition duration 30 s = ~1500 T3 writes rejected per partitioned reality per incident. Feature code's retry policy determines user impact.

---

## DP-F6 — Invalidation audit + reconciliation

### Normal-path audit

Every SDK publish to `dp:inval:{reality_id}` is mirrored to a Redis Stream `dp:inval:audit:{reality_id}`. CP consumes the stream and records:

- Published count per writer_node + time bucket
- Expected subscriber count (from active session registry)
- Actual subscriber-report count (subscribers periodically report `received` counts back to CP every 60 s)

Discrepancy = **suspected invalidation loss.**

### Detection thresholds

- **Per-reality per-minute:** if `expected - received > 5`, alert + trigger fail-safe broadcast for affected aggregate types.
- **Per-SDK-instance:** if a subscriber's received count drops >20% over 5 min while publish rate is steady, suspect subscriber-side drop; investigate that instance.

### Fail-safe broadcast

When loss is suspected, CP publishes to `dp:inval:{reality_id}:failsafe` with payload `{ aggregate_types: [...] }`. All subscribers drop ALL cache entries for those aggregate types. Coarse (over-invalidates many entries for one lost message) but correct.

Failsafe rate-limited: at most 1/minute per reality per aggregate type. Prevents spiral where aggressive failsafes cause read load spikes that cause more failsafes.

### Reconciliation after CP outage

On CP recovery (DP-F3), CP replays the audit stream from the outage window:
1. Compute expected publishes from CP's side (reconstructed from paused but still-logged CP events and from SDK reports).
2. Compare with the stream.
3. For gaps >5 min or >100 messages, trigger fail-safe per affected aggregate types.

---

## DP-F7 — Backpressure token bucket

Closes [Q12](99_open_questions.md). Three independently-sized buckets govern rate limits. Any bucket empty → `DpError::RateLimited { retry_after }`.

### Bucket 1 — Per-reality per-tier

Enforces [DP-S5](08_scale_and_slos.md#dp-s5--throughput-targets-at-v3-peak) ceilings.

| Tier | Refill rate (per reality) | Bucket size | Enforces |
|---|---:|---:|---|
| T1 writes | 5 000/s | 20 000 | Sustained + 4s burst |
| T2 writes | 500/s | 2 000 | Sustained + 4s burst |
| T3 writes | 50/s | 200 | Sustained + 4s burst |
| T2/T3 reads | 10 000/s | 30 000 | Sustained + 3s burst |

Implemented in the SDK (per-reality state shared via Redis atomic counter with TTL sliding window). Alternative: per-SDK-instance bucket calibrated to `global_ceiling / expected_instance_count` — simpler but less tight.

### Bucket 2 — Per-service (caller fairness)

Prevents one rogue or buggy service (e.g. a looping feature with a retry storm) from monopolizing capacity. Each service has a bucket size = `reality_ceiling / N_services`.

Sizing defaults:
- 4 services active per reality → each gets 25% of reality bucket
- Dynamic rebalancing: if service X consistently uses <10% of its share while service Y is throttled, CP may rebalance on 5-min intervals

### Bucket 3 — Per-session (abuse prevention)

Prevents a single bot-controlled player from spamming writes.

- T2/T3 writes: 10/s per session
- T1 writes: 100/s per session (positions, emotes)
- T2/T3 reads: 200/s per session

Exceeded → `RateLimited` bubbles to the feature, which typically surfaces "slow down" to the client.

### `retry_after` semantics

`DpError::RateLimited { retry_after }` includes a `Duration`. Feature code may:
- Propagate to user ("try again in N seconds")
- Queue the op locally and retry exactly once after `retry_after`
- Drop the op silently (for non-critical events like analytics)

Feature must NOT retry immediately in a loop — clippy lint `dp::forbid_swallowed_backpressure` (DP-R6) prevents this.

### Dynamic adjustment

CP may adjust refill rates per-aggregate-type based on observed write patterns. Changes push via `StreamTierPolicyUpdates` to all SDKs within 60 s. Used sparingly (e.g., disaster response, not normal tuning).

---

## DP-F8 — Cold-start fallback + schema migration rollback

### Cold-start fallback when CP unreachable

Closes Q6 residual. When a reality is frozen and CP is down:

1. Gateway receives a player connect for the frozen reality.
2. Gateway cannot call `WakeReality(reality_id)` on CP.
3. **Fallback path:** gateway queues the connect with a ≤30 s hold. If CP recovers within the window, continue normal flow.
4. After 30 s, gateway surfaces `503 Service Temporarily Unavailable` with `Retry-After: 60` to the client. Reality stays frozen. Other realities (already warm) continue.

**No "CP-bypass warm":** attempting to warm a reality without CP risks double-wake (two nodes both thinking they own it), which violates the session-node single-writer rule (DP-A11). Safer to stay frozen.

### Schema migration rollback

When a migration encounters data integrity failures during rebuild (01/R02's integrity checker signals >0.1% row mismatch), rollback procedure:

1. **Halt new writes in new schema** — CP flips tier_policy to dual-read/dual-write mode, with new schema marked degraded. SDK continues reading both shapes but pauses writing in new shape.
2. **Quarantine the partial new-schema projection table** — renamed with timestamp suffix, kept for forensic review.
3. **Resume reads from old schema projection** — already in dual-read mode, no change needed.
4. **Alert + postmortem** — per [02_storage/SR4](../02_storage/SR04_postmortem_process.md) + this folder's chaos drill results.

**Rollback time budget:** ≤5 min from integrity-checker alert to writes resuming on old schema (flip tier_policy + drain new-schema in-flight).

**Rollback blast radius:** data written in new schema during the failing window is preserved in the quarantined table; manual recovery may replay it after root-cause fix. No user-visible data loss, but user-visible latency bump during the flip.

---

## DP-F9 — Graceful drain + quiescence

### Planned node removal (rolling deploy, capacity reduction)

1. **Admin marks node "draining"** via CP's admin CLI.
2. **CP stops assigning new sessions** to the draining node.
3. **Existing sessions complete** naturally (player disconnects, session archives at idle-timeout per [02_storage/S1](../02_storage/S01_03_session_scoped_memory.md)) or are actively migrated (DP-F2 flow, but pre-announced rather than reactive).
4. **T1 snapshot flush** — all T1 aggregates on the draining node are snapshotted to Redis before the node accepts shutdown.
5. **Outbox drain** — any pending outbox entries on the node are flushed (outbox is on Postgres; only transient state needs draining).
6. **Node acknowledges drain complete** to CP → CP removes from registry → admin shuts down.

**Drain deadline:** 10 min default. Sessions still active are force-migrated (same DP-F2 path, less gentle).

### Rolling deploy coordination

CP drives deploy via `deploy_cohort` table (see [DP-C4](05_control_plane_spec.md#dp-c4--tier-policy-registry)). Nodes drain + upgrade + rejoin in sequence, with health-check gates between cohorts. Aborts deploy on unhealthy cohort.

**Max 25% of game-node capacity draining at once** (V3; V1/V2 tolerate single-node drain given smaller fleet).

### Quiescence for reality freeze

Different from node drain — freezing a reality ([02_storage/R9](../02_storage/R09_safe_reality_closure.md)):

1. CP announces `reality.status = freezing` to all SDKs.
2. SDKs reject new session binds for that reality (existing sessions continue).
3. Sessions archive at idle-timeout (hours to a day).
4. Once session count = 0, CP transitions `freezing → frozen`; per-reality Postgres + Redis namespaces can be cold-stored per R9 lifecycle.

No data-plane-level action needed beyond bind-rejection; 02_storage's lifecycle machine owns the rest.

---

## DP-F10 — Chaos drill + failure injection cadence

Automated failure injection in staging against a V2-equivalent load profile. Each drill validates a specific DP-F row.

### Cadence

| Drill | Cadence | Validates |
|---|---|---|
| CP failover (kill active, verify passive promotes) | Weekly | DP-C10, DP-F3 degraded-mode + recovery |
| Game-node kill (kill one, verify session re-pin) | Weekly | DP-A11, DP-F2 |
| Redis cluster node loss | Bi-weekly | DP-F4 cache failure path |
| Invalidation drop injection (drop N% of pub/sub msgs) | Bi-weekly | DP-F6 reconciliation + failsafe |
| Full reality freeze + thaw | Monthly | DP-C7 cold-start + DP-F9 quiescence |
| Schema migration rollback exercise | Quarterly | DP-F8 rollback procedure |
| Network partition (SDK ↔ CP) injection | Monthly | DP-F5 split-brain |
| Backpressure saturation (burst to 3× DP-S5) | Monthly | DP-F7 token bucket correctness |
| Cross-region DR drill (V3 only) | Quarterly | Cross-region failover (future) |

### Gate on production release

A DP release cannot ship to production if any mandatory drill has failed in the preceding 30 days. CI-gated via `last_successful_drill` check in CP's deploy_cohort manifest.

### Drill ownership

- Weekly/bi-weekly drills: automated, alerted if failed; runbook in [02_storage/SR3](../02_storage/SR03_runbook_library.md).
- Monthly/quarterly drills: on-call engineer participates; postmortem if any step exceeds runbook budget.

Plugs into the existing SRE drill infrastructure ([02_storage/SR7](../02_storage/) — reference; may be Phase 3+ of the SRE review).

---

## Summary

| ID | What it locks |
|---|---|
| DP-F1 | Failure classification: 10 modes in scope; out-of-scope failures listed |
| DP-F2 | Node death: CP 30s detection + session re-pin + T1 snapshot reload; p99 handoff ≤5s |
| DP-F3 | CP outage: degraded mode preserves ongoing ops; new binds rejected; ≤15min ceiling |
| DP-F4 | Redis failure: reads fall back to projection; T3 writes → CircuitOpen; audit replay on recovery |
| DP-F5 | Split-brain: CP > AP preference; reject T3 writes on uncertainty; 60s audit replay on heal |
| DP-F6 | Invalidation audit: per-minute expected-vs-received diff; fail-safe aggregate-type broadcast |
| DP-F7 | Backpressure: 3 token buckets (per-reality-tier, per-service, per-session) + `retry_after` |
| DP-F8 | Cold-start fallback: queue ≤30s then 503; schema migration rollback ≤5min with dual-read |
| DP-F9 | Graceful drain: 10min deadline; force-migrate; reality freeze delegates to 02_storage R9 |
| DP-F10 | Chaos cadence: weekly CP + node, bi-weekly Redis + inval drop, monthly freeze + partition, quarterly migration rollback |

---

## Cross-references

- [DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split) — CP/DP split; CP not on hot path, even during recovery
- [DP-A11](02_invariants.md#dp-a11--session-node-owns-t1-writes) — session-sticky writer; node death triggers re-pin
- [DP-C2](05_control_plane_spec.md#dp-c2--deployment-model) / [DP-C9](05_control_plane_spec.md#dp-c9--degraded-mode) / [DP-C10](05_control_plane_spec.md#dp-c10--ha-failover-admin-interface) — CP HA + degraded mode
- [DP-X4](06_cache_coherency.md#dp-x4--invalidation-storm-mitigation) / [DP-X10](06_cache_coherency.md#dp-x10--failure-modes--fail-safe) — coherency-layer failure modes
- [DP-S7](08_scale_and_slos.md#dp-s7--availability-targets) / [DP-S8](08_scale_and_slos.md#dp-s8--resource-ceilings-per-reality) — availability targets and capacity ceilings
- [02_storage/R9](../02_storage/R09_safe_reality_closure.md) — reality lifecycle that DP-F9 plugs into
- [02_storage/R2](../02_storage/R02_projection_rebuild.md) — projection rebuild that DP-F8 rollback coordinates with
- [02_storage/SR2](../02_storage/SR02_incident_oncall.md) / [SR3](../02_storage/SR03_runbook_library.md) / [SR4](../02_storage/SR04_postmortem_process.md) — incident response + runbook + postmortem DP plugs into
- [11_access_pattern_rules.md DP-R6](11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry) — features must propagate backpressure from DP-F7

---

## Deferred

- **V3 cross-region DR** — out of Phase 3 scope; aligns with V3 operational maturity.
- **Chaos drill automation tooling** — operational concern, separate infra work in an ops folder once V2 is approaching.
- **Per-service dynamic backpressure sharing algorithm** — DP-F7 defaults to fixed equal shares; dynamic rebalancing is a V2-data-informed tuning.
- **Q13 test strategy** — tier contract enforcement testing — not resolved here; belongs in a test-plan doc once SDK implementation starts.
