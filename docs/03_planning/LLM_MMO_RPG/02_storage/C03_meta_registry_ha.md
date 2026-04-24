<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: C03_meta_registry_ha.md
byte_range: 161828-174364
sha256: eb0736d9b48d9714c2cf35d47d3c62faaa5d9df7e6e87b6586167a5e61c3da97
generated_by: scripts/chunk_doc.py
-->

## 12O. Meta Registry High Availability (C3 resolution)

**Origin:** SA+DE adversarial review 2026-04-24 surfaced C3 — while reality DBs have DB-per-reality isolation (blast radius = 1 reality), the meta registry is a **platform-wide SPOF**. Meta outage breaks: reality routing, event propagation (meta-worker), publisher heartbeats, admin audit (R13), player dashboards, new reality spawn.

### 12O.1 Why meta is different

DB-per-reality gives blast radius containment at reality level. Meta registry is the opposite: it holds cross-cutting platform state that every service reads on every command.

**Tables on meta DB:**
- `reality_registry` — routing table (lookup on every command)
- `player_character_index` — user-facing PC lookup
- `publisher_heartbeats` — realtime pipeline health
- `admin_action_audit` — R13 policy enforcement
- `reality_close_audit`, `reality_migration_audit`, `archive_verification_log` — compliance
- `canon_change_log` — M4 propagation source

Meta outage = platform-wide service degradation, not just one-reality outage.

### 12O.2 Workload profile — read-heavy

At V3 scale:
| Ops | Rate |
|---|---|
| Reality routing lookup (every command) | ~5K reads/sec |
| Dashboard/discovery queries | ~100 reads/sec |
| Heartbeat writes (publishers) | ~0.4 writes/sec |
| Lifecycle transitions | rare (hours) |
| Audit writes (admin activity peak) | 1-10 writes/sec |
| PC index writes | rare |

**Total: ~10K reads/sec, ~15 writes/sec.** Read-heavy → primary + replicas topology is optimal.

### 12O.3 Layer 1 — Streaming replication + auto-failover

**Topology:**
- 1 primary (writes + strong-consistency reads)
- Sync replica(s) — RPO = 0 for committed writes
- Async replica(s) — read scaling

**Scaling:**
| Stage | Topology | AZ tolerance |
|---|---|---|
| V1/V2 | Primary + 1 sync + 1 async | Single AZ failure |
| V3+ | Primary + 2 sync (diff AZs) + 1 async | Two AZ failure |

**Postgres sync replication config:**
```
synchronous_commit = on
synchronous_standby_names = 'ANY 1 (sync_replica_a, sync_replica_b)'
```

Primary waits for at least 1 sync replica ACK before confirming commit. Write latency +5-10ms (acceptable for meta's low write rate).

**Failover orchestrator: Patroni** (etcd-based consensus, industry standard)
- Auto-detects primary failure via etcd lease
- Promotes healthiest sync replica
- Updates VIP/DNS
- RTO target: ~30 seconds

### 12O.4 Layer 2 — Read replica offloading

Additional async replicas serve read-only queries:
- Dashboard/discovery queries (eventual consistency OK, ~100ms lag)
- Audit log searches (rare, admin-only, compliance reads)
- Player PC index lookups (stale-OK for dashboard)

**Primary stays focused on:**
- All writes (sync committed to replica)
- Critical hot reads (heartbeat freshness check, lifecycle transition CAS)

### 12O.5 Layer 3 — Meta access library (not standalone service)

**Decision:** meta access is a **shared Go library** imported by all services, NOT a standalone microservice. Rationale:
- Every service needs meta access on hot path (reality routing per command)
- Extra network hop would add latency + new failure mode
- Logic is simple CRUD + routing — doesn't justify service boundary

```
contracts/meta/
  routing.go       -- primary-vs-replica query router
  cache.go         -- Redis cache layer (L4)
  fallback.go      -- degraded-mode logic (L5)
  pool.go          -- connection pool per primary/replicas
  health.go        -- health + readiness probes
```

Each service (world-service, roleplay-service, publisher, meta-worker, event-handler, migration-orchestrator) imports this library.

**If V3 needs centralized meta coordination** (e.g., cross-service rate limits on writes) → extract to `meta-service` standalone service. Not V1/V2.

### 12O.6 Layer 4 — Redis cache layer (hot reads)

Reality routing is stable (realities rarely change shards). Cache aggressively:

```
Cache key: meta:reality:{reality_id} → {db_host, db_name, status, locale, ...}
TTL: 30 seconds (configurable)
```

**Hit rate estimate:** 95%+ in steady state. 10K reads/sec × 95% cached = primary serves only 500 reads/sec. Primary stays idle most of the time.

**Cache invalidation:**
- Writes that change reality state invalidate cache key
- Via `xreality.reality.stats` topic (R5 infrastructure) — all service caches receive invalidation events
- No per-node cache; shared Redis keeps all services consistent

**Cache warmup on startup:** service loads top-N active realities into cache on boot (configurable: e.g., top 1000 by last-active).

**Bypass flag:** reads needing fresh data use `?fresh=true` → skip cache, hit replica/primary.

### 12O.7 Layer 5 — App-level routing + retry during failover

30-second failover window handled at app layer:

```go
for attempt := 1; attempt <= maxAttempts; attempt++ {
  conn, err := metaClient.GetPrimary()
  if isTransient(err) {
    // 100ms, 500ms, 2s, 5s, 10s
    sleepBackoff(attempt)
    refreshConnectionPool()
    continue
  }
  return conn.Exec(...)
}
// After max retries: return 503 Retry-After OR enter degraded mode (§12O.8)
```

DNS/VIP managed by Patroni — app just reconnects, gets new primary automatically.

### 12O.8 Layer 6 — Degraded mode for full-meta outage

If primary + all sync replicas unavailable (catastrophic, rare):

**Reality routing:**
- Redis cache continues serving warm realities
- Cache miss → 503 with `Retry-After`
- Users see "temporary unavailability for <specific reality>"

**Heartbeats:**
- Publisher/meta-worker/event-handler buffer heartbeats locally (bounded buffer, default 10K entries)
- Flush to meta on recovery
- Other services see stale heartbeat timestamps → alert fires but services continue

**Admin audit (R13):**
- Buffer locally (bounded, default 10K entries)
- Flush on recovery
- Buffer overflow → admin ops rate-limited at service level (safety)
- **Admin commands that need fresh audit acknowledgment** (e.g., R9 close confirmations) → block until meta recovers

**New reality spawn:**
- Blocked fully (requires meta write)
- Users see "reality creation temporarily unavailable"

**Platform-wide alert:** page-level severity for SRE.

**Config:**
```
meta.degraded_mode.audit_buffer_size = 10000
meta.degraded_mode.write_queue_retries = 5
meta.degraded_mode.retry_backoff_schedule = "100ms,500ms,2s,5s,10s"
meta.degraded_mode.alert_after_seconds = 10
```

### 12O.9 Layer 7 — Disaster recovery (cross-region)

Beyond HA — protects against single-region failure:

**V1/V2 (single-region HA enough):**
- WAL archive to MinIO (continuous, 60s ship interval)
- PITR capability (30-day retention)
- RPO: 60 seconds
- Cross-region deferred

**V3+ (cross-region active-passive):**
- WAL + base backup replicated cross-region via MinIO replication
- Standby cluster in target region, warm
- Automated DNS failover on detected region-outage
- RTO: 15-30 minutes
- RPO: 5 minutes

### 12O.10 Separate audit DB — deferred to V3+ evaluation

Audit tables (`admin_action_audit`, close/migration audit, verification log) have different profile:
- Higher write rate (1-10/sec peak) than rest of meta
- Near-zero read rate (compliance/forensic only)
- Long retention (2+ years, grows large)
- Compliance-critical

**V1/V2:** consolidated with meta (simplest). Meta write capacity has headroom.

**V3 consideration:**
- If audit write rate > 100/sec, split to dedicated audit DB cluster
- If compliance mandates isolation
- Separate HA setup for audit

**Not committed for V1/V2.** Revisit at V3+ based on measured write rate.

### 12O.11 Reality DB HA — separately, not in V1/V2

Meta gets full HA (platform-wide blast radius).

**Reality DB HA is different:**
- Reality DB outage = 1 reality unavailable (bounded blast radius)
- HA for 1000+ reality DBs = massive infrastructure cost
- **V1/V2:** single reality DB per reality, accept short outage from shard failure
- **V3+:** per-shard HA (shard = Postgres server hosting N reality DBs). Shard failover promotes standby. RTO ~30s per shard. Better than per-reality HA.

Per-shard HA is cheaper than per-reality HA AND provides the same outcome (shard failover restores all N realities simultaneously).

### 12O.12 Monitoring + alerts

```
lw_meta_primary_up{az}                               gauge
lw_meta_replica_up{replica_id, az}                   gauge
lw_meta_replication_lag_seconds{replica_id}          gauge
lw_meta_failover_count_total                         counter
lw_meta_write_latency_seconds                         histogram
lw_meta_read_latency_seconds{target=primary|replica}  histogram
lw_meta_cache_hit_rate                                gauge
lw_meta_cache_size_bytes                              gauge
lw_meta_degraded_mode_active                          gauge (0/1)
lw_meta_degraded_buffer_size{service, buffer_type}    gauge
```

**Alerts:**
- Replication lag > 5s → warn
- Replication lag > 30s → page
- Primary down → page immediately
- Cache hit rate < 80% → investigate
- Degraded mode active > 60s → page
- Failover triggered → notification to all SRE
- Audit buffer > 80% full → investigate (possible meta outage)

### 12O.13 Configuration

```
meta.replication.mode = "streaming_sync_at_least_one"
meta.replication.sync_replicas_required = 1          # V1/V2: 1; V3: 2
meta.replication.async_replicas = 1
meta.replication.failover_orchestrator = "patroni"
meta.replication.rpo_target_seconds = 0              # sync replica
meta.replication.rto_target_seconds = 30

meta.cache.enabled = true
meta.cache.ttl_seconds = 30
meta.cache.warm_on_startup = true
meta.cache.warm_top_n = 1000                         # V3: auto-tune
meta.cache.redis_pool_size = 20

meta.wal_archive.enabled = true
meta.wal_archive.bucket = "lw-meta-wal-archive"
meta.wal_archive.ship_interval_seconds = 60
meta.pitr.retention_days = 30

meta.cross_region.enabled = false                    # V1/V2: no; V3+: yes
meta.cross_region.target_region = ""                 # activation V3+

meta.degraded_mode.audit_buffer_size = 10000
meta.degraded_mode.write_queue_retries = 5
meta.degraded_mode.retry_backoff_schedule = "100ms,500ms,2s,5s,10s"
meta.degraded_mode.alert_after_seconds = 10

meta.audit_db.separated = false                      # V1/V2: no; V3 evaluate
```

### 12O.14 Accepted trade-offs

| Cost | Justification |
|---|---|
| Sync replication +5-10ms write latency | Meta write rate low (~15/sec); RPO=0 worth it |
| +1 Postgres server V1 (primary + sync replica) | Platform-wide SPOF avoidance non-negotiable |
| +2 Postgres V3 (2 sync + 1 async) | Multi-AZ resilience |
| 30s RTO during failover | Degraded mode (L5/L6) + cache absorbs it |
| Redis cache eventual consistency (30s TTL) | Reality routing changes rarely; stale reads safe |
| Degraded mode complexity | Isolated to rare outages |
| Cross-region deferred V3+ | Single-region HA enough until scale demands |
| Audit DB consolidation V1/V2 | Simplicity; split at V3+ if needed |
| Reality DB HA deferred V3+ | Bounded blast radius; per-shard HA at V3 covers this cheaper |

### 12O.15 Implementation ordering

- **V1 launch**: Patroni + 1 sync replica + 1 async replica. Meta access library with primary/replica routing (L1-L3). Redis cache for reality routing (L4). App-level retry on failover (L7).
- **V1 + 30 days**: WAL archive + PITR setup (L9 partial, single-region).
- **V1 + 60 days**: Degraded mode handling (L8) — tested via chaos drill.
- **V2**: Cache warmup auto-tuning, replication monitoring dashboard.
- **V3+**: 2nd sync replica (multi-AZ), cross-region DR (L9 full), per-shard HA for reality DBs, evaluate audit DB split.

### 12O.16 What this resolves

- ✅ Platform-wide SPOF eliminated (sync replica + auto-failover)
- ✅ Read scaling via async replicas + Redis cache
- ✅ Failover window tolerated (app-level retry + degraded mode)
- ✅ DR path to cross-region scaled to V3+
- ✅ Clean separation: meta HA vs reality DB HA (different strategies)
- ✅ Audit consolidation explicit with V3 evaluation trigger

Remaining open items (V3+ scale):
- Cross-region automated DNS failover tooling
- Audit DB split criteria if/when activated
- Per-shard HA for reality DBs (separate section when V3 approaches)

