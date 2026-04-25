# 20 — Operational Residuals (DP-Ch46..DP-Ch50)

> **Status:** LOCKED (Phase 4, 2026-04-25). Pragmatic operational defaults + configurability documentation for ops handoff. Resolves [99_open_questions.md Q23 + Q24 + Q25 + Q29 + Q33](99_open_questions.md). **No new axiom** — this file is operational residuals implementing existing invariants and SLOs.
> **Stable IDs:** DP-Ch46..DP-Ch50.

---

## Reading this file

Five operational concerns batched into a single ops-handoff file. Each is small enough that a separate file would be overhead; together they form the operator's reference for V1/V2 deployment. Phase 4 design phase + design-residual cleanup is functionally complete after this file lands; only [Q20](99_open_questions.md) (LLM latency) remains and is V1-data-deferred.

- DP-Ch46: Histogram bucket layouts (Q23)
- DP-Ch47: Telemetry cardinality control (Q24)
- DP-Ch48: Capability signing key rotation policy (Q25)
- DP-Ch49: Subscription fan-out batching (Q29)
- DP-Ch50: Retention per channel level (Q33)

All values below are **recommended defaults**. Operators can override per-deployment via CP admin / config without contractual breakage.

---

## DP-Ch46 — Histogram bucket layouts

### Default Prometheus buckets are wrong-shape for DP

Default Prometheus exposition has linear buckets (`5, 10, 25, 50, 75, 100, 250, 500, 1000ms`). DP's SLO targets are sub-100ms with p99 measurements; default buckets lose resolution where it matters.

### Recommended exponential bucket layouts (per metric)

```
# T0 read latency (target p99 <1 ms — in-process memory)
buckets = [0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.05]  # 100µs..50ms

# T1 read/write latency (target p99 <10 ms — Redis cache + pub/sub)
buckets = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.5]  # 500µs..500ms

# T2 read latency (target: cache hit <10ms p99, miss <50ms p99)
buckets = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]  # 1ms..1s

# T2/T3 write latency (target T2 <5ms ack, T3 <50ms ack)
buckets = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]  # 1ms..2s

# Cross-node fanout latency (target ≤20 ms p99 per DP-X5)
buckets = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5]  # 1ms..500ms

# Causality wait latency (target ≤5s default per DP-Ch39)
buckets = [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]  # 10ms..30s

# Cold-start latency (target ≤10 s per DP-S2)
buckets = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]  # 100ms..1min
```

### Cache hit rate

Cache hit rate is a **counter ratio**, not a histogram. Track via two counters:

```
dp.cache.hits_total{tier, op}
dp.cache.requests_total{tier, op}
```

Dashboard derives `hit_rate = hits / requests`. Alert if hit_rate < 0.95 (target per [DP-S4](08_scale_and_slos.md#dp-s4--per-tier-read-latency-targets-sdk-internal-p99)) sustained over 5 min.

### Override mechanism

CP admin CLI can adjust bucket layout per metric per deployment via `set-histogram-buckets <metric> <bucket_list>`. Bucket changes apply at SDK restart (next deploy cohort). Hot-reload not supported.

### Why exponential, not linear

Latency distributions are heavy-tailed log-normal. Exponential buckets give equal resolution per decade. Linear buckets at 5/10/25/50/75/100ms have only 2 buckets in the 10-100ms range — useless for p99 measurement at 50ms target.

---

## DP-Ch47 — Telemetry cardinality control

### The problem

Naïve labeling: `dp.{op}.latency{reality_id, channel_id, aggregate_type, tier, op, result}` →
- 10k realities × ~50 channels active × ~50 aggregate types × 4 tiers × ~5 ops × ~3 results
- = millions of unique series per metric
- Prometheus blows up; query time skyrockets; storage cost balloons.

### Mitigation pattern

**Default labels (low cardinality):**

```
service     # ~10 distinct (world-service, combat-service, etc.)
tier        # 4 values (T0..T3)
op          # ~5 (read, write, query, subscribe, invalidate)
result      # ~3 (ok, error_capacity, error_other)
```

Cardinality: 10 × 4 × 5 × 3 = 600 series per metric. Bounded.

**High-cardinality labels NOT in metrics:**

- `reality_id`, `channel_id`, `aggregate_type`, `session_id`, `actor_id` — these go in **structured logs** (queryable via log-aggregator) and **traces** (1% sampled), not Prometheus labels.

**SDK-side aggregation:**

SDK accumulates per-(reality_id, channel_id, aggregate_type) counters in process; flushes to Prometheus by aggregating across the high-cardinality dimensions. Per-channel breakdown queryable from logs/traces when needed for incident response.

### When fine-grained breakdown is needed

Operators flag a specific (reality_id) for debug:

```
admin> debug-trace-on reality=R-12345 duration=10m
```

CP signals SDKs in that reality to emit richer labels for 10 min. Bounded breakdown without permanent cardinality cost.

### Recommended exporters

- **Prometheus**: counters + histograms with bounded labels above
- **OpenTelemetry traces**: 1% sampled, full labels including reality_id / channel_id / aggregate_type
- **Structured logs**: every error + capacity event logs full context (reality, channel, aggregate, session)

### Override mechanism

`dp_emit_full_labels = true` env var on a specific service forces all-labels emission for that instance. Ops uses this on canary instances during investigation. Default `false`.

---

## DP-Ch48 — Capability signing key rotation policy

### V1/V2 (current per [DP-C8](05_control_plane_spec.md#dp-c8--capability-issuance--rotation))

- **Quarterly rotation** (90-day window)
- Old keys retained "verify-only" for 2× max capability lifetime (10 min) after rotation
- Storage: KMS-backed (not raw Postgres) — rotation key set fetched at CP startup
- Audit: every sign/verify event logged to `dp:writer_audit:{reality_id}` (existing per [DP-Ch13](13_channel_ordering_and_writer.md#dp-ch13--writer-handoff--epoch-fencing-protocol))

### V3 upgrade

When platform-mode launches at V3 with multi-tenant deployment + commercial SLA:

- **Monthly rotation** (30-day window) — narrower blast radius for stolen keys
- **Passport-style revocation broadcast**: CP publishes revoked-key-id list every 5 min on a dedicated Redis pub/sub channel:

```
Channel: dp:cap_revoked:{reality_id}
Payload: { revoked_key_ids: [String], at: Timestamp }
```

SDKs cache the revoked list (TTL 5 min) and reject JWTs signed with revoked keys before normal expiry. Allows immediate revocation on security incident without waiting for natural rotation.

- **KMS-backed**: signing key never lives in Postgres at V3; CP requests sign-op via KMS API per JWT issuance.
- **Auditable rotation events**: each rotation produces an audit entry with `actor=admin / scheduled`, `from_key_id`, `to_key_id`, `at`.

### Migration path V2 → V3

1. Add revocation channel + SDK-side revoked-list consumer (deploy SDKs first; V2 still ignores revoked list because V2 keys live full 90d)
2. Switch CP to monthly rotation cadence
3. Move signing keys to KMS
4. Drop the verify-only legacy storage

No data-plane downtime — capability issuance protocol unchanged at the wire level (still JWT signed by an asymmetric key).

### Override mechanism

`cap_rotation_days` config on CP — operator can set 30 / 60 / 90. Default per stage above. Faster rotation has operational cost (more KMS sign ops, more cache invalidation churn) but smaller blast radius.

---

## DP-Ch49 — Subscription fan-out batching

### Naïve fan-out cost

- Per active player: subscribed to 6 channel levels (cell + tavern + town + district + country + continent — varies per book)
- 500 CCU × 6 = 3000 active subscriptions per reality
- 10k CCU global × 6 = 60k Redis Stream subscribers globally

Redis Streams handle this fine, but Redis subscriber state + consumer-group bookkeeping scales linearly with subscriber count. Memory overhead + reconnect cost grows.

### Batching pattern

**One Redis Stream subscriber per (game-node, channel) pair** — not per (player, channel) pair.

```
SDK on game-node N maintains:
  subscriptions: Map<ChannelId, ChannelSubscription>

ChannelSubscription:
  redis_consumer: RedisStreamConsumer   # one Redis subscriber for this channel from this node
  local_listeners: Vec<SessionConnection>   # in-process sessions interested in this channel
```

When channel C has events:
1. Redis pushes one event to game-node N's subscriber
2. SDK on N dispatches to all `local_listeners` for C — in-process fan-out, ~µs per delivery

Reduces Redis subscriber count from O(players × levels) to O(nodes × active_channels):
- 5 game nodes × 1000 active channels = 5k subscribers globally instead of 60k

### Memory bounds

```
Per node, per channel: ~1KB (Redis client state)
Per node total: 1000 active channels × 1KB = ~1MB. Negligible.

Per session interested in channel: ~32 bytes (subscription pointer)
Per node, all sessions: 500 sessions × 6 levels × 32B = ~100KB. Negligible.
```

### Implementation hooks

`subscribe_channel_events_durable<S>` (existing per [DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api)) is invoked by feature code per (session, channel). SDK transparently coalesces — checks if a Redis subscriber for `(this_node, channel)` already exists; if yes, just registers the new local_listener; if no, opens the Redis subscriber + registers.

When all local_listeners for `(this_node, channel)` disconnect, SDK closes the Redis subscriber after a 30-s grace window (in case a new session re-subscribes quickly).

### Override mechanism

`subscription_grace_seconds` per channel level — operator can extend grace for high-churn levels (default 30s for cells, 300s for tavern+).

---

## DP-Ch50 — Retention per channel level

### Default retention by level

```
cell        30 days       # high churn, mostly chat / play history
tavern      1 year        # matches reality default per 02_storage R1
town+       1 year        # same as reality default
```

Rationale:
- Cells churn fast; their events are mostly transient social chat. 30 days covers "looking back at last month's RP" without years-of-archive cost.
- Higher channels are world-state events; 1 year preserves canon-relevant history.

### Per-channel override

`channels.metadata.retention_days: u32` overrides level default for a specific channel.

```json
// Example: "Important Tavern" with extended retention
{
  "level_name": "tavern",
  "metadata": { "retention_days": 1825 }   // 5 years
}
```

Default (if metadata absent) applies the level-name default above.

### Cleanup mechanism

Existing per-reality cleanup batch (per [02_storage R1](../02_storage/R01_event_volume.md)) extended:

```sql
-- Nightly batch query per reality:
DELETE FROM event_log
WHERE reality_id = $1
  AND channel_id IS NOT NULL
  AND committed_at < (
      now() - (
          COALESCE(
              (SELECT (metadata->>'retention_days')::int FROM channels WHERE id = event_log.channel_id),
              CASE
                  WHEN ch.level_name = 'cell' THEN 30
                  ELSE 365
              END
          ) * interval '1 day'
      )
  );
```

Reality-scoped events (where `channel_id IS NULL`) keep the existing reality-wide retention (per 02_storage R1 — 1 year default).

### Aggregator snapshot retention

Per [DP-Ch26](16_bubble_up_aggregator.md#dp-ch26--state-model-event-sourced--periodic-snapshots), aggregator snapshots are kept for 90 days post-unregister. For dissolved channels, snapshot GC follows the channel's own retention — if a tavern with 5-year retention dissolves, its aggregator snapshots also kept 5 years.

### Override mechanism

CP admin CLI: `set-channel-retention <channel_id> <days>` updates `channels.metadata.retention_days`. Effective at next nightly batch.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch46 | Exponential histogram bucket layouts per metric (sub-ms to 30s ranges); cache hit rate as counter ratio (not histogram); override via CP admin CLI |
| DP-Ch47 | Default Prometheus labels = low-cardinality only (service, tier, op, result); high-cardinality (reality_id / channel_id / aggregate_type) goes to logs + traces; SDK-side aggregation; debug-trace flag for bounded full-label investigation |
| DP-Ch48 | V1/V2 quarterly rotation per DP-C8; V3 monthly rotation + passport-style revocation broadcast on `dp:cap_revoked:{reality_id}` channel; KMS-backed at V3; migration path V2 → V3 specified |
| DP-Ch49 | Subscription batching: one Redis subscriber per (node, channel), not per (player, channel); reduces global subscriber count ~12×; in-process fan-out to local sessions; 30-s grace on last-listener close |
| DP-Ch50 | Per-channel-level default retention (cell 30d, tavern+ 1y); per-channel override via metadata.retention_days; nightly cleanup batch extended; aggregator snapshots follow channel retention on dissolve |

---

## Cross-references

- [DP-S4](08_scale_and_slos.md#dp-s4--per-tier-read-latency-targets-sdk-internal-p99) — latency targets DP-Ch46 buckets are sized for
- [DP-K8](04c_subscribe_and_macros.md#dp-k8--dpinstrumented-telemetry-macro) — instrumentation macro that DP-Ch47 cardinality rules guide
- [DP-C8](05_control_plane_spec.md#dp-c8--capability-issuance--rotation) — current quarterly rotation policy DP-Ch48 extends
- [DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api) — subscribe primitive that DP-Ch49 batches behind the scenes
- [02_storage R1](../02_storage/R01_event_volume.md) — event-log retention DP-Ch50 extends with per-channel-level overrides

---

## Phase 4 — final state after this file

| Status | Count | Items |
|---|---:|---|
| ✅ Resolved | **19** | Q15, Q16, Q17, Q18, Q19, Q21, Q22, Q23, Q24, Q25, Q26, Q27, Q28, Q29, Q30, Q31, Q32, Q33, Q34 |
| 🟡 Deferred (V1 data) | 1 | Q20 LLM latency |
| 🟢 Resolved | 0 | (all 4 nits absorbed into this file: Q23/Q24/Q25/Q33) |

**19 of 20 Phase 4 questions resolved.** Remaining Q20 (LLM latency) requires V1 prototype data and has no design action available now.

**Phase 4 design + ops-residual cleanup is functionally complete.** 06_data_plane is locked baseline for feature design. SDK implementation (Phase 2b proc-macros, clippy lints, dp/dp-derive crates) is the next phase of work, pursued when V1 game services begin coding.
