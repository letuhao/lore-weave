# L1 — DB Physical + Meta Registry

> **Status:** DRAFT — first-pass enumeration complete (12 sub-components). Going deeper bottom-up.
> **Last updated:** 2026-05-29

---

## §1. Sub-component overview (first pass — confirmed scope)

| ID | Component | Size | Owning kernel chunk(s) | Notes |
|---|---|---|---|---|
| L1.A | Meta Registry DB schema (~20 tables) | L | 00_overview §3-§11, S04, S08, S10, S06, S07, S09, R09, R04-L2, S11, SR02, SR05, R13, M4, S13 | Shared `loreweave_meta` DB |
| L1.B | Meta Access Library Go (`contracts/meta/`) | L | C03 §12O.5, S04 §12T.3, C05 §12Q | imports into every Go service |
| L1.C | Per-reality DB Provisioner | XL | R04 §12D.1, §12D.6, §12D.7 | 11-step provision + 6-step deprovision + capacity planner + orphan scanner |
| L1.D | Migration Orchestrator Service | L | R04 §12D.2 | dedicated Go service, concurrency 10 |
| L1.E | Meta HA Infrastructure | XL | C03 §12O.3, §12O.7, §12O.9 | Patroni + etcd + sync replica + WAL archive + PITR |
| L1.F | Meta Cache Layer (Redis) | M | C03 §12O.6 | 30s TTL + invalidation via xreality.reality.stats |
| L1.G | Pgbouncer setup | M | R04 §12D.4 | transaction pooling + per-shard pgbouncer |
| L1.H | Tiered Backup Strategy | L | R04 §12D.3 | active/frozen/archived tiers + MinIO bucket |
| L1.I | Per-DB Metrics Aggregation | M | R04 §12D.5, C03 §12O.12, I19 | 7 metrics × N DBs |
| L1.J | Degraded Mode Handlers | L | C03 §12O.8, SR6-D5 | service-side bounded buffers + retry schedules |
| L1.K | CI Lints + Validators | M | S04 §12T.6, I8, I12, etc. | meta-write-discipline, pii-classify, transitions-validation, etc. |
| L1.L | V1→V3 Capacity Progression Gates | S | R04 §12D.9-10, I17 | doc only + admin/capacity-override audit |

---

## §2. L1.A — Meta Registry DB schema (deep enumeration)

> **Approach:** enumerate every table in `loreweave_meta` with: schema sketch · indexes
> · retention tier (S08-D3) · which services read/write · related events emitted · owning
> kernel chunk.
>
> **Tables to enumerate (~20+):** TBD — to be filled bottom-up next.

### Table inventory (to be enumerated table-by-table)

| Table | Owning chunk | Retention tier | Read by | Written by | Events |
|---|---|---|---|---|---|
| `reality_registry` | R04 / 00_overview | Operational | all services | world-service via MetaWrite | `reality.created`, `reality.status.*` |
| `pii_kek` | S08 / S10 | PII Sensitive | services with PII access | auth-service via MetaWrite | crypto-shred on user erasure |
| `pii_registry` | S08 §12X | Operational | services with PII | services via MetaWrite | `pii.classified`, retention sweeper |
| `user_consent_ledger` | S08 §12X | Operational | services reading user data | auth-service, world-service via MetaWrite | `user.consent.*` |
| `prompt_audit` | S09 §12Y | 90d hot / 2y cold | none (compliance only) | contracts/prompt internal | (none — audit-only) |
| `user_cost_ledger` | S06 §12V | 2y + pseudonymize | billing service | usage-billing-service via MetaWrite | `billing.charge.*` |
| `user_queue_metrics` | S07 §12W | Operational | rate-limiter | services emitting queue activity | (none — counter) |
| `admin_action_audit` | R13 §12L | 5y | none (compliance only) | admin-cli via MetaWrite | (none — audit-only) |
| `service_to_service_audit` | S11 §12AA | 5y | none (compliance only) | all services via MetaWrite | (none — audit-only) |
| `meta_write_audit` | S04 §12T.3 | 1y | none (introspection) | MetaWrite internal | (none — append-only) |
| `meta_read_audit` | S04 | 1y | none (introspection) | (deferred — read-side audit) | (none) |
| `incidents` | SR02 §12AE | 7y compliance | sre-dashboard | sre-cli via MetaWrite + AttemptStateTransition | `incident.*` |
| `feature_flags` | SR05 §12AH | Operational | all services | admin-cli via MetaWrite | `feature_flag.*` |
| `deploy_audit` | SR05 §12AH | 1y | sre-dashboard | deploy pipeline via MetaWrite | `deploy.*` |
| `publisher_heartbeats` | R06 §12F | Ephemeral (24h rolling) | sre + meta-worker | publisher service via MetaWrite | (none — heartbeat) |
| `player_character_index` | 04_player_character §A | Operational | world-service, gateway | world-service via MetaWrite | `pc.index.*` |
| `reality_close_audit` | R09 §12I | 7y compliance | none (compliance only) | world-service via MetaWrite + AttemptStateTransition | `reality.close.*` |
| `reality_migration_audit` | R04 / SR05 | 1y | migration-orchestrator | migration-orchestrator via MetaWrite | `migration.*` |
| `archive_verification_log` | R09 §12I | 7y compliance | world-service (close flow) | world-service via MetaWrite | `archive.verified` |
| `canon_change_log` | M4 + S13 | 2y | meta-worker | glossary-service via MetaWrite | `canon.change.*` → fan to `xreality.canon.*` |
| `canon_entries` | S13 §12AC | 2y | glossary-service, world-service, prompt assembler | glossary-service via MetaWrite | `canon.promoted`, `canon.propagated` |
| `canonization_audit` | S13 | 5y | none (compliance) | glossary-service via MetaWrite | (audit-only) |
| `instance_schema_migrations` | R04-L2 | Operational | migration-orchestrator | migration-orchestrator via MetaWrite | (none) |
| `shard_utilization` | SR08 §12AK | Operational | sre-dashboard, capacity planner | shard health agent via MetaWrite | `shard.scaling.*` |
| `scaling_events` | SR08 §12AK | 1y | sre-dashboard | shard health agent via MetaWrite | (audit-only) |
| `dependency_events` | SR06 §12AI | 1y | sre-dashboard | services via MetaWrite | (none — audit-only) |
| `chaos_drills` | SR07 §12AJ | 1y | sre-dashboard | chaos-engine via MetaWrite | `chaos.drill.*` |
| `supply_chain_events` | SR10 §12AM | 1y | sre-dashboard | CI pipeline via MetaWrite | `supply_chain.*` |
| `alert_outcomes` | SR09 §12AL | 1y | sre-dashboard | alert engine via MetaWrite | (audit-only) |
| `alert_silences` | SR09 §12AL | Operational | alert engine | sre-cli via MetaWrite | (audit-only) |
| `turn_outcomes` | SR11 §12AN | 30d hot / 1y cold | sre + roleplay-service | roleplay-service via MetaWrite | (audit-only) |
| `observability_budget_breaches` | SR12 §12AO | 1y | sre-dashboard | metric library via MetaWrite | `obs.budget.*` |
| `book_authorship` | S13 §12AC | Operational | glossary, world-service | book-service via MetaWrite | `book.authorship.*` |

**Total: ~30+ tables.** (Higher than initial estimate of 20.)

### Per-table deep-dive (TBD — bottom-up table-by-table)

For each table above, the deep-dive will enumerate:
- Full column list with types + nullability
- Primary key + indexes
- Foreign keys + ON DELETE behavior
- CHECK constraints (business invariants encoded)
- Role grants (per S04-D6, 8 roles minimum)
- Retention class (S08-D3) + erasure method
- Outbox events emitted (if any)
- Read paths (cache vs primary vs replica)
- Migration ordering constraint (some tables must exist before others)

---

## §3. L1.B — Meta Access Library Go (`contracts/meta/`)

> **Status:** sub-component listed. Deep-dive pending — comes after L1.A tables complete.

Sub-deliverables (from C03 §12O.5 + S04 + C05):
- `routing.go` — primary-vs-replica query router (C03 §12O.4)
- `cache.go` — Redis cache layer (C03 §12O.6)
- `fallback.go` — degraded-mode logic (C03 §12O.8)
- `pool.go` — connection pool per primary/replicas
- `health.go` — health + readiness probes (C03 §12O.12)
- `MetaWrite()` (S04 §12T.3)
- `AttemptStateTransition()` (C05 §12Q)
- `transitions.yaml` + validator (per-resource transition graph)
- `Actor` type + SVID integration (S11)

---

## §4. L1.C — Per-reality DB Provisioner

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from R04 §12D.1, §12D.6, §12D.7):
- Provisioning flow — 11 steps (capacity-pick shard → CREATE DATABASE → extensions →
  roles → schema → registry row → pgbouncer entry → Prometheus scrape → return)
- Deprovisioning flow — 6 steps (verify archive → registry null → DROP DATABASE →
  pgbouncer deregister → Prometheus deregister → replication slot cleanup)
- Capacity planner (R04 §12D.6) — shard allocation by current_db_count + storage + cpu
- Orphan scanner nightly job (R04 §12D.7) — reconciles pg_database vs reality_registry,
  7-day grace + auto-DROP
- Configs (concurrency, retry, timeouts) — see R04 §12D.2 config block
- Capacity thresholds (warning 80% / full 95%)

---

## §5. L1.D — Migration Orchestrator Service

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from R04 §12D.2):
- Dedicated Go service (`services/migration-orchestrator/`)
- Reads `contracts/migrations/`
- Queries `instance_schema_migrations`
- Applies M_k with concurrency 10
- Retry transient (3 attempts, 30s backoff)
- Idempotency + reversibility + non-breaking enforcement
- Breaking-migration canary on 1 reality before fleet
- Alert on persistent failure → SRE
- Update `instance_schema_migrations` on each success

---

## §6. L1.E — Meta HA Infrastructure

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from C03 §12O.3, §12O.7, §12O.9):
- Patroni setup with etcd consensus
- Sync replica config (`synchronous_commit=on`, `synchronous_standby_names=…`)
- Async replica for read scaling
- Auto-failover ~30s RTO
- VIP/DNS management
- WAL archive (60s ship interval to MinIO bucket `lw-meta-wal-archive`)
- PITR retention 30d
- V1: 1 sync + 1 async / V2: same / V3+: 2 sync (multi-AZ) + 1 async + cross-region DR

---

## §7. L1.F — Meta Cache Layer (Redis)

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from C03 §12O.6):
- Cache key: `meta:reality:{reality_id}` → {db_host, db_name, status, locale, ...}
- TTL 30s configurable
- Invalidation via `xreality.reality.stats` events (R5 infrastructure)
- Cache warmup on service startup (top-N active, default 1000)
- `?fresh=true` bypass flag
- Per-service Redis pool (size 20)
- Cache hit-rate metric `lw_meta_cache_hit_rate`

---

## §8. L1.G — Pgbouncer setup

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from R04 §12D.4):
- Per-shard pgbouncer process
- Transaction pooling mode (NOT session)
- Backend connections: 500 real, virtual 5000 to apps
- App-side: 1 pool per shard host (not per DB) — pgbouncer multiplexes
- Limits accepted: no session-scoped advisory locks, prepared-statement handling

---

## §9. L1.H — Tiered Backup Strategy

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from R04 §12D.3):
- Active: daily incremental + weekly full (14d/4w retention)
- Frozen: weekly full only (4w retention)
- Archived: MinIO Parquet archive (no Postgres backup)
- Closed: archive only
- Dedicated bucket `lw-db-backups` (separate from `lw-world-archive`)
- Per-shard parallel scheduler
- Restore drill tooling + verification dashboard

---

## §10. L1.I — Per-DB Metrics Aggregation

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from R04 §12D.5, C03 §12O.12, I19):
- Per-DB metrics with `reality_id` + `shard_host` labels:
  - `lw_reality_db_size_bytes`
  - `lw_reality_db_connections`
  - `lw_reality_db_tps`
  - `lw_reality_db_slow_query_count`
  - `lw_reality_db_replication_lag_seconds`
  - `lw_reality_db_event_count`
  - `lw_reality_db_last_backup_ts`
- Cardinality control (no per-query labels — only reality_id + shard_host)
- Alert routing (platform-wide → SRE; per-reality → owner or DF11 queue)
- Observability inventory entries (I19) — all `lw_*` metrics registered in
  `contracts/observability/inventory.yaml`
- Meta-specific metrics from C03 §12O.12 (lw_meta_*)

---

## §11. L1.J — Degraded Mode Handlers

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from C03 §12O.8, SR6-D5):
- Service-side bounded buffers (default 10K entries):
  - Publisher heartbeat buffer
  - meta-worker heartbeat buffer
  - admin audit buffer
- Retry schedules `100ms,500ms,2s,5s,10s`
- Admin command blocking rules (R9 close confirmations block on meta outage)
- Buffer-overflow rate-limiter at service level
- Service mode enum (Full, Limited, Essentials, ReadOnly, Offline) — SR6-D5
- Mode propagation via Redis control channel `lw:dependency:control`
- `Drain()` lifecycle hook integration (SR6-D10)
- Chaos drill integration (SR07 §12AJ)

---

## §12. L1.K — CI Lints + Validators

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables:
- `scripts/meta-write-discipline-lint.sh` — flags direct INSERT/UPDATE to meta tables
- `scripts/pii-classify-lint.sh` — flags PII columns missing `@pii_sensitivity` tag
- `scripts/transitions-validation-lint.sh` — validates `transitions.yaml` graphs
- `scripts/shard-allocation-validation.sh`
- `scripts/migration-idempotency-validation.sh`
- `scripts/observability-inventory-lint.sh` (I19) — every `lw_*` metric declared
- `scripts/capacity-budget-lint.sh` (I17) — every service in `budgets.yaml`
- `scripts/dep-pinning-lint.sh` (I18) — every dep has cryptographic hash
- `scripts/timeout-discipline-lint.sh` (I16) — every outbound call declares timeout
- `scripts/language-rule-lint.sh` — re-derive per amended I3
- `scripts/role-grant-validator.sh` — verify per-service Postgres grants match S04-D6

---

## §13. L1.L — V1→V3 Capacity Progression Gates

> **Status:** sub-component listed. Deep-dive pending.

Sub-deliverables (from R04 §12D.9-10, I17, S5-D5):
- Documented V1/V2/V3 capacity progression (foundation builds V1 ceiling + V2 readiness)
- `admin/capacity-override` command (S5 tier 2, 24h auto-expire) + S5 audit
- `contracts/capacity/budgets.yaml` — per-service replicas/cpu/memory/db_pool/llm-calls

---

## §14. Open questions surfaced during enumeration

1. **canon_entries location** — service map line 71 says it's in `loreweave_meta`; S13-D4
   says "lives in glossary-service". Conflict. Foundation needs to lock this. Suggested:
   meta DB owns `canon_entries` (cross-service read), `glossary-service` owns the
   `glossary` DB which has its own author-side staging tables. Glossary-service writes
   to `canon_entries` via `MetaWrite()`.

2. **Migration orchestrator language** — service map says Go; OK because orchestrator
   doesn't `#[derive(Aggregate)]`.

3. **Patroni dependency** — adds etcd as a hard dep. Should etcd be foundation-managed
   or rely on existing infra? Foundation infra checklist need to clarify.

4. **Backup verification** — R04 §12D.3 mentions "restore drill" but doesn't lock
   cadence. Suggested: monthly restore drill per shard, automated, results in
   `archive_verification_log`. Foundation owns the automation.

5. **L1.I observability inventory format** — I19 says `inventory.yaml` is the registry;
   foundation must ship the YAML schema + lint script. Format draft needed (open).

---

## §15. Status

```
[x] L1 sub-components enumerated (12 components, 30+ tables)
[ ] L1.A per-table deep-dive (next, bottom-up)
[ ] L1.B-L per-sub-component deep-dive
[ ] L1 open questions resolved
[ ] L1 cycle decomposition (after deep-dive complete)
```
