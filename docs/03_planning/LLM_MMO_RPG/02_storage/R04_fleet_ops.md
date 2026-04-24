<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R04_fleet_ops.md
byte_range: 61548-72787
sha256: 863caca5d7e6143a1c51d0fe7576a435e4803454783308a0655422ae8b2cc55d
generated_by: scripts/chunk_doc.py
-->

## 12D. Database Fleet Operations (R4 mitigation)

With 1000+ active realities + 10K+ frozen at V3 scale, the platform runs ~11K Postgres DBs across 2–6 Postgres servers. Postgres can handle the raw count; the problem is that standard tooling (goose, pg_dump, postgres-exporter, pgadmin) was designed for 1 or a few DBs, not thousands. R4 requires purpose-built automation across 7 areas.

### 12D.1 Layer 1 — Automated provisioning + deprovisioning

Reality lifecycle drives DB lifecycle. All automated, idempotent, retry-safe.

**Provisioning flow (triggered by world-service on reality creation):**
```
1. Capacity planner selects shard (§12D.6)
2. CREATE DATABASE loreweave_world_<reality_id> ON shard
3. Connect to new DB
4. Install required extensions (pgvector, others)
5. Create service roles (app user, readonly user)
6. Apply latest schema migration set
7. INSERT reality_registry row with db_host + db_name
8. Register pgbouncer entry for new DB
9. Register Prometheus scrape target
10. Return reality_id
```

**Deprovisioning flow (triggered by reality close, §7.3):**
```
1. Verify MinIO archive completed + checksum validated
2. UPDATE reality_registry SET status='closed', db_host=NULL, db_name=NULL
3. DROP DATABASE loreweave_world_<reality_id>
4. Deregister pgbouncer entry
5. Remove Prometheus scrape target
6. Clean up replication slots (if any)
```

Any failed step is recoverable: L7 orphan scanner picks up partial state.

### 12D.2 Layer 2 — Migration orchestrator (dedicated service)

Applying schema migrations across 11K DBs requires orchestration. Central service in Go, stateful, resumable:

```
migration-orchestrator service:
  - reads migration set from contracts/migrations/
  - queries meta registry's instance_schema_migrations table
  - finds DBs needing migration M_k
  - applies M_k with concurrency limit (default 10)
  - retries transient failures (default 3 attempts, 30s backoff)
  - alerts on persistent failures (SRE manual intervention)
  - updates instance_schema_migrations on each success
```

**Hard invariants for every migration:**
- **Idempotent**: applying twice = no-op second time
- **Reversible** where possible (down migration SQL documented)
- **Non-breaking** by default (additive, no data loss) — breaking migrations require special approval + canary on 1 reality first

**Config:**
```
ops.migration.concurrency = 10
ops.migration.retry_attempts = 3
ops.migration.retry_backoff_seconds = 30
ops.migration.timeout_per_db_minutes = 5
```

Why dedicated service (not function inside world-service): clear boundary, reusable across service teams, easier to reason about long-running state.

### 12D.3 Layer 3 — Tiered backup strategy

Backups scaled to reality status (active/frozen/archived). Dramatically reduces waste vs one-size-fits-all backup.

| Reality status | Backup strategy | Retention |
|---|---|---|
| `active` | Daily incremental (pg_basebackup + WAL archive) + weekly full | 14 days incremental, 4 weeks full |
| `frozen` | Weekly full only (no writes → no incremental) | 4 weeks full |
| `archived` | None — MinIO Parquet archive IS the backup | Forever in MinIO |
| `closed` | None — verified archive, DB dropped | MinIO archive only |

**Backup storage sizing at V3 scale:**
- Active: 1000 × 14 daily × 1 GB = 14 TB incremental; 1000 × 4 × 1 GB = 4 TB full → ~18 TB
- Frozen: 10K × 4 × 0.5 GB = 20 TB
- Total: ~40 TB — separate cheap storage tier

**Dedicated MinIO bucket**: `lw-db-backups` (separate from `lw-world-archive` — different retention + access patterns).

**Config:**
```
ops.backup.active.incremental_hours = 24
ops.backup.active.full_days = 7
ops.backup.frozen.full_days = 7
ops.backup.retention_incremental_days = 14
ops.backup.retention_full_weeks = 4
ops.backup.target_bucket = "lw-db-backups"
```

Automated backup scheduler reads `reality_registry.status` and dispatches accordingly. Per-shard parallel.

### 12D.4 Layer 4 — Connection pooling via pgbouncer

Without pooling: N services × M DBs × K connections per pool = connection explosion. Postgres max_connections ~500, exhausted quickly.

**Architecture:**
```
[world-service, roleplay-service, etc.]
              │
              ▼
   pgbouncer (per Postgres shard)
              │
              ▼
     Postgres shard (holds N DBs)
```

**pgbouncer config:**
- **Transaction pooling mode** (safer than session pooling, acceptable given our workload has no session-level state)
- Reuses backend connections across DBs on same shard
- 500 real backend connections per shard, 5000 virtual to apps

**App-side:**
```go
func getDBFor(realityID UUID) *sql.DB {
    shard := registry.Lookup(realityID).ShardHost
    return poolerConnTo(shard, realityID)
    // Connects to pgbouncer with dbname = loreweave_world_<realityID>
}
```

Connection pool in app: 1 pool per shard host (not per DB). pgbouncer multiplexes.

**Why pgbouncer (not pgcat or Odyssey):** battle-tested, well-documented, broad community. Re-evaluate at V3 scale if transaction-pool limits hit.

**Limits accepted:**
- No session-scoped Postgres features (advisory locks, temp tables across statements)
- Prepared statements handled specially
- Our workload fits this mode

### 12D.5 Layer 5 — Metrics aggregation

Per-DB metrics with `reality_id` label. Prometheus aggregates at scrape layer.

**Metrics collected per DB:**
- `lw_reality_db_size_bytes{reality_id, shard_host}`
- `lw_reality_db_connections{reality_id, shard_host}`
- `lw_reality_db_tps{reality_id}`
- `lw_reality_db_slow_query_count{reality_id}`
- `lw_reality_db_replication_lag_seconds{reality_id}`
- `lw_reality_db_event_count{reality_id}`
- `lw_reality_db_last_backup_ts{reality_id}`

At 11K DBs × 7 metrics = ~77K time series. Prometheus handles this easily (million+ series is normal). Label cardinality controlled: only `reality_id`, `shard_host` — not per-query or per-user labels.

**Alert routing:**
- Platform-wide alerts (many DBs impacted): → SRE
- Per-reality alerts (single DB sick): → reality owner metadata or DF11 queue
- Thresholds tuned to avoid noise

### 12D.6 Layer 6 — Shared Postgres server sharding

Many DBs per server — not 1:1. Shards allocated based on capacity.

**Server tiers:**
| Tier | CPU/RAM | Max active DBs | Max frozen DBs |
|---|---|---|---|
| Small (dev) | 4 core / 16 GB | 100 | 500 |
| Medium (prod) | 16 core / 64 GB | 500 | 2,000 |
| Large (prod) | 32 core / 256 GB | 2,000 | 10,000 |

**V3 baseline estimate:** 2 large Postgres servers (primary + replica) or 4 medium (higher redundancy). Fits 1000 active + 10K frozen comfortably.

**Allocation rule:**
- New reality → shard with most free capacity (by `current_db_count` + `current_storage_bytes`)
- R1 DB subtree split threshold triggers new shard allocation if parent shard nears capacity
- Meta registry tracks: `shard_host`, `current_db_count`, `total_storage_bytes`, `cpu_load_pct`

**Capacity thresholds:**
```
ops.shard.capacity_warning_pct = 80
ops.shard.capacity_full_pct = 95
```

At 80% → alert SRE to provision new shard. At 95% → new realities rejected from this shard (hard stop).

**Shard rebalancing / subtree split:** see [§12N](#12n-database-subtree-split-runbook-c2-resolution) for the concrete runbook. V1/V2 uses freeze-copy-cutover (5-45 min freeze per reality); V3+ uses logical replication (~30s freeze). Manual trigger in V1/V2; threshold-driven automation V3+.

### 12D.7 Layer 7 — Orphan DB detection + cleanup

Prevents silent state divergence between registry and physical DBs.

**Nightly reconciliation per shard:**
```python
shard_dbs = SELECT datname FROM pg_database WHERE datname LIKE 'loreweave_world_%'
registry_dbs = SELECT db_name FROM reality_registry WHERE db_host = $shard_host

orphans = shard_dbs - registry_dbs     # DBs on shard but not in registry
missing = registry_dbs - shard_dbs     # Registry says exists but shard doesn't have

for orphan in orphans:
    alert("Orphan DB detected: possible provisioning leak")
    mark_for_review(orphan, grace_until=now + 7 days)
    if review_not_completed_after_grace:
        archive_if_possible(orphan)
        DROP DATABASE orphan

for miss in missing:
    alert("Missing DB — registry says exists but shard doesn't")
    manual_investigation_required()
```

**Config:**
```
ops.orphan_detection.enabled = true
ops.orphan_detection.interval_hours = 24
ops.orphan_detection.hold_days_before_drop = 7
```

### 12D.8 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 provisioning automation | Bug in provisioning script = every new reality broken. Must test thoroughly. |
| L2 migration orchestrator | New stateful service to maintain. CI must validate migration idempotency. |
| L3 tiered backup | 40 TB backup storage at V3 scale (cheap tier but real cost). |
| L4 pgbouncer | Extra hop (~0.5ms added latency). Session-scoped features unavailable. |
| L5 metrics aggregation | Prometheus cardinality must be capped — no per-query labels. |
| L6 sharding | Manual capacity planning in V1/V2 (automated V3). Rebalancing is hard. |
| L7 orphan detection | False positives require manual triage. 7-day grace period. |

Main cost is **L2 migration orchestrator** (new service) and **L6 sharding** (capacity planning discipline). Both unavoidable at scale.

### 12D.9 Capacity progression

**V1** (≤10 realities): 1 small Postgres server, 1 pgbouncer, manual ops OK. Implement L1 + L4 + L7 as insurance.

**V2** (≤100 realities): 1 medium Postgres, 1 pgbouncer. L1, L2, L3, L4, L5, L7 all needed.

**V3** (1000+ realities): 2–4 Postgres servers, pgbouncer per shard, full automation. L6 mandatory.

### 12D.10 Implementation ordering

- **V1 launch**: L1 (provisioning), L4 (pgbouncer even with 1 shard — forward-compat), L7 (orphan detection — cheap insurance)
- **V1 + 30 days**: L2 (migration orchestrator — needed before first production schema change)
- **V1 + 60 days**: L3 (tiered backup — needed before first reality freezes)
- **V2**: L5 (metrics dashboards mature), L6 (real sharding when >1 Postgres server)
- **V3+**: DF11 (fleet management UI + capacity planning automation)

### 12D.11 Tooling surface (deferred to DF11)

Operations dashboards needed:
- Shard health dashboard (capacity, TPS, slow queries per shard)
- Per-reality DB inspector (size, growth, last backup, slow queries)
- Migration status board (which migrations applied to which DBs, progress, failures, retry controls)
- Backup verification dashboard (last successful backup per reality, retention status, restore drill results)
- Orphan DB + missing DB alerts with resolution workflow
- Capacity planner (predicted shard fullness + recommendation + auto-alert)
- Shard rebalance planner (V3+)

Deferred to **DF11 — Database Fleet Management**. Mechanisms (L1–L7) locked here in §12D; dashboards + admin UI + capacity automation is DF11's scope. Distinct from DF9 (rebuild/integrity) — DF9 is per-reality correctness, DF11 is platform-wide fleet.

