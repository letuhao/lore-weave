# L1.C through L1.L — Infrastructure sub-components

> **Parent:** [L1_db_physical_meta.md](L1_db_physical_meta.md)
> **Depth target:** B (artifact-level) — concise enumeration; full spec lives in linked kernel chunks
> **Why grouped:** these 10 sub-components are deployment + ops infrastructure. Many share docker-compose / Terraform / K8s manifests + a few share Go libraries. Grouping prevents duplication.

---

## §1. L1.C — Per-reality DB Provisioner

**Owning chunks:** R04 §12D.1 (provision/deprovision flows), §12D.6 (sharding), §12D.7 (orphan scanner)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.C.1 | `services/world-service/internal/provisioner/` Rust module | Code | 11-step provision flow per R04 §12D.1 |
| L1.C.2 | `services/world-service/internal/deprovisioner/` Rust module | Code | 6-step deprovision flow |
| L1.C.3 | `services/world-service/internal/capacity_planner/` Rust module | Code | Shard allocator (R04 §12D.6) |
| L1.C.4 | `services/world-service/cmd/orphan_scanner/` Rust binary | Code | Nightly cron (R04 §12D.7) |
| L1.C.5 | `contracts/migrations/per_reality/0001_initial.sql` | SQL | Initial per-reality schema migration (events + outbox + projections skeleton — actual content owned by L2/L3 cycles) |
| L1.C.6 | `infra/terraform/postgres-shard/` | IaC | Per-shard Postgres provisioning (V1: 1 medium; V2+: more) |
| L1.C.7 | `scripts/capacity-thresholds.yaml` | Config | warning 80%, full 95% |
| L1.C.8 | `tests/integration/reality_lifecycle_test.go` | Test | Provision N realities, verify routing, deprovision, verify dropped + orphan_scanner picks up partial state |
| L1.C.9 | `runbooks/provisioner/orphan_resolution.md` | Doc | SRE runbook (DF11 register at SR3-D3) |

**Dependencies:** L1.B (`MetaWrite()` for `reality_registry` insert), L1.G (pgbouncer entry registration), L1.I (Prometheus scrape registration)

**Acceptance criteria (RAID verify gate for L1.C cycle):**
- `cargo test -p world-service provisioner` 100% pass
- Integration test provisions 10 realities, deprovisions all → registry empty + orphan_scanner reports 0
- Capacity planner allocates to least-full shard
- Orphan scanner detects manually-injected orphan, marks for 7d grace, drops after grace

**Open questions:**
- Q-L1C-1: Bootstrap of first shard — does foundation include initial Terraform run, or is shard provisioning out-of-band (V1 manual)? Suggested: foundation includes V1 docker-compose (single shard); IaC for prod is V1+30d.

---

## §2. L1.D — Migration Orchestrator Service

**Owning chunks:** R04 §12D.2

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.D.1 | `services/migration-orchestrator/` Go service | Code | Dedicated service per R04 §12D.2 |
| L1.D.2 | `services/migration-orchestrator/internal/runner/` | Code | Concurrency-10 runner with retry + backoff |
| L1.D.3 | `services/migration-orchestrator/internal/canary/` | Code | Canary on 1 reality for breaking migrations |
| L1.D.4 | `services/migration-orchestrator/cmd/migrate/` | CLI | Trigger migration runs (`admin/migrate <migration_id>`) |
| L1.D.5 | `contracts/migrations/manifest.yaml` | Config | Migration set declaration (id, version, breaking?, dependencies) |
| L1.D.6 | `contracts/service_acl/matrix.yaml` entry | ACL | `migration-orchestrator → reality_registry` write SVID-authorized |
| L1.D.7 | `scripts/migration-idempotency-validator.sh` | CI lint | Detects non-idempotent migration patterns |
| L1.D.8 | `tests/integration/migration_run_test.go` | Test | Apply migration to 10 realities, verify state, verify retry on transient fail, verify dead-letter on persistent fail |
| L1.D.9 | `runbooks/migration/persistent_failure.md` | Doc | SRE runbook |

**Dependencies:** L1.B (MetaWrite for `instance_schema_migrations` + `reality_migration_audit`), L1.C (read from `reality_registry`)

**Acceptance criteria:**
- `go test -tags=integration ./services/migration-orchestrator/...` pass
- Concurrency=10 verified (no thread starvation)
- Retry exhaustion → `reality_migration_audit.failure_reason='persistent'` + alert fires
- Breaking migration on canary reality → fails CI gate if canary failed
- `scripts/migration-idempotency-validator.sh` blocks injected non-idempotent SQL

**Open questions:**
- Q-L1D-1: Migration rollback path — should orchestrator auto-rollback on persistent failure, or only document down migration SQL? Suggested: V1 doc-only (manual rollback by SRE); V2+ auto-rollback for non-data-changing migrations.

---

## §3. L1.E — Meta HA Infrastructure

**Owning chunks:** C03 §12O.3, §12O.7 (app-level retry), §12O.9 (cross-region DR)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.E.1 | `infra/terraform/meta-postgres/primary.tf` | IaC | Primary Postgres + sync replication config |
| L1.E.2 | `infra/terraform/meta-postgres/sync_replica.tf` | IaC | 1 sync replica (V1/V2; 2 at V3+) |
| L1.E.3 | `infra/terraform/meta-postgres/async_replica.tf` | IaC | 1 async replica for reads |
| L1.E.4 | `infra/patroni/patroni.yml` | Config | Patroni etcd-based failover |
| L1.E.5 | `infra/etcd/etcd-cluster.tf` | IaC | 3-node etcd cluster |
| L1.E.6 | `infra/postgres/postgresql.conf` | Config | `synchronous_commit=on`, `synchronous_standby_names='ANY 1 (sync_replica_a)'` |
| L1.E.7 | `infra/wal-archive/` | Config | WAL ship 60s to MinIO `lw-meta-wal-archive` bucket |
| L1.E.8 | `infra/pitr-tooling/` | Tooling | PITR restore tooling (30d retention) |
| L1.E.9 | `runbooks/meta/failover.md` | Doc | SRE runbook (RTO 30s target) |
| L1.E.10 | `runbooks/meta/pitr_restore.md` | Doc | PITR restore procedure |
| L1.E.11 | `chaos/drills/meta_failover.yaml` | Chaos | Periodic failover drill (SR07) |
| L1.E.12 | `tests/integration/meta_failover_test.go` | Test | Kill primary, verify failover within 30s, verify writes resume |

**Dependencies:** None (this IS infrastructure — L1.B + L1.D depend on this)

**Acceptance criteria:**
- Terraform plan applies cleanly to staging
- Manual failover (`patronictl switchover`) completes <30s
- WAL archive verified on MinIO bucket
- PITR restore drill recovers to T-1h state successfully
- Chaos drill (meta_failover) green

**Open questions:**
- Q-L1E-1: Cross-region DR — V1+30d or V3+? C03 §12O.9 says V3+. Confirm.
- Q-L1E-2: etcd hosted-managed (AWS RDS-compatible? Managed etcd?) or self-hosted? Suggested: self-hosted on dedicated EC2/EKS to avoid vendor lock + match Patroni docs.

---

## §4. L1.F — Meta Cache Layer (Redis)

**Owning chunks:** C03 §12O.6

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.F.1 | `contracts/meta/cache.go` (already enumerated in L1.B.2) | Code | Cache library |
| L1.F.2 | `infra/terraform/redis-cache/` | IaC | Redis Sentinel cluster for HA |
| L1.F.3 | `infra/redis/redis.conf` | Config | Persistence: AOF every 1s; maxmemory-policy: allkeys-lru |
| L1.F.4 | `scripts/cache-warmup.sh` | Script | Top-N active reality cache warmup on service boot |
| L1.F.5 | `contracts/cache/keys.yaml` | Registry | Cache key schema registry (TTL, invalidation triggers per key) |
| L1.F.6 | `tests/integration/cache_invalidation_test.go` | Test | Emit `xreality.reality.stats` → verify all instances' caches invalidate |

**Dependencies:** L1.B (cache.go), L2 outbox publisher (emits xreality.* invalidation events)

**Acceptance criteria:**
- Cache hit rate ≥ 95% in steady-state load test (10K reads/sec, 100 unique realities)
- Invalidation event propagates to all instances <2s
- Cache survives Redis Sentinel failover with no data loss (stale data acceptable; cache is not SSOT)

**Open questions:**
- Q-L1F-1: Multi-instance Redis topology — single shared Sentinel cluster vs per-AZ? Suggested: shared Sentinel V1; per-AZ V3+ (multi-AZ resilience).

---

## §5. L1.G — Pgbouncer

**Owning chunks:** R04 §12D.4

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.G.1 | `infra/terraform/pgbouncer/` | IaC | Per-shard pgbouncer (1:1 with Postgres shard host) |
| L1.G.2 | `infra/pgbouncer/pgbouncer.ini` | Config | Transaction pooling mode; 500 real / 5000 virtual |
| L1.G.3 | `services/world-service/internal/db_pool/` Rust | Code | App-side: 1 pool per shard host (not per DB) |
| L1.G.4 | `contracts/meta/pool.go` extension | Code | Same pattern for Go services |
| L1.G.5 | `runbooks/pgbouncer/connection_exhaustion.md` | Doc | SRE runbook |
| L1.G.6 | `tests/integration/pgbouncer_multiplex_test.go` | Test | 1000 virtual connections, 50 backend, verify no blocking |

**Dependencies:** L1.E (Postgres infrastructure exists)

**Acceptance criteria:**
- Pgbouncer survives 5K concurrent virtual connections with 500 backend
- Transaction-mode constraints documented (no session-scoped advisory locks)
- Per-shard pgbouncer deployable independently

**Open questions:**
- Q-L1G-1: Alternative tools (pgcat, Odyssey) — V1 commits to pgbouncer per R04 §12D.4 rationale; re-evaluate trigger = transaction-pool limits hit at V3. Confirm.

---

## §6. L1.H — Tiered Backup Strategy

**Owning chunks:** R04 §12D.3

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.H.1 | `services/backup-scheduler/` Go service | Code | Reads `reality_registry.status` → dispatches backup per tier |
| L1.H.2 | `contracts/backup/policy.yaml` | Config | Per-status backup policy (frequency, retention) |
| L1.H.3 | `infra/minio/lw-db-backups-bucket.tf` | IaC | Dedicated MinIO bucket (separate from `lw-world-archive`) |
| L1.H.4 | `scripts/restore-drill.sh` | Script | Monthly restore-drill automation (writes to `archive_verification_log`) |
| L1.H.5 | `dashboards/backup-verification.json` | Grafana | DF11 dashboard |
| L1.H.6 | `tests/integration/tiered_backup_test.go` | Test | Provision realities in active/frozen/archived statuses; verify each gets correct backup tier |
| L1.H.7 | `runbooks/backup/restore.md` | Doc | SRE runbook |

**Dependencies:** L1.C (reality lifecycle), L1.E (Postgres + WAL), MinIO infra (assumed pre-existing per LoreWeave novel platform — confirm)

**Acceptance criteria:**
- 3-tier policy enforced (active=14d incr + 4w full / frozen=4w full / archived=none)
- Restore drill succeeds; `archive_verification_log` row written
- Capacity sizing: 40 TB at V3 (~documented in I17 capacity budget for backup-scheduler)

**Open questions:**
- Q-L1H-1: Is MinIO already provisioned per existing LoreWeave platform, or does foundation include MinIO setup? Suggested: confirm MinIO is pre-existing for `frontend` BLOB store; foundation adds dedicated `lw-db-backups` bucket only.
- Q-L1H-2: Restore-drill cadence — monthly per shard? Quarterly? Suggested: monthly per shard automatically; quarterly full-system drill manually.

---

## §7. L1.I — Per-DB Metrics Aggregation

**Owning chunks:** R04 §12D.5, C03 §12O.12 (meta-specific metrics), I19 (observability inventory)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.I.1 | `infra/prometheus/scrape-config.yaml` | Config | Dynamic scrape targets (per-reality DB) — updated by provisioner (L1.C) |
| L1.I.2 | `infra/prometheus/recording-rules.yaml` | Config | Aggregation rules (per-shard, per-status) |
| L1.I.3 | `infra/prometheus/alerts/per-reality.yaml` | Config | Per-reality alerts (warning / page thresholds) |
| L1.I.4 | `infra/prometheus/alerts/meta.yaml` | Config | C03 §12O.12 lw_meta_* alerts |
| L1.I.5 | `infra/postgres-exporter/postgres-exporter.yaml` | Config | Postgres exporter with cardinality controls (only `reality_id`, `shard_host` labels) |
| L1.I.6 | `contracts/observability/inventory.yaml` initial entries | Registry | All L1 metrics declared (I19) |
| L1.I.7 | `dashboards/per-reality-health.json` | Grafana | Per-reality DB inspector |
| L1.I.8 | `dashboards/shard-health.json` | Grafana | Per-shard overview |
| L1.I.9 | `tests/integration/metrics_cardinality_test.go` | Test | Inject 100 realities; verify Prometheus series count ≤ 7 metrics × N realities (no cardinality explosion) |

**Dependencies:** L1.C (provisioner registers scrape targets), I19 (obs inventory schema lives in L6 — circular; resolve by including I19 schema in L1.I cycle)

**Acceptance criteria:**
- Cardinality budget enforced (`scripts/observability-inventory-lint.sh` from L1.K passes)
- Alert routing per SR02 alert routing table works (verify with chaos drill)
- Recording rules aggregate per-shard correctly

**Open questions:**
- Q-L1I-1: Prometheus topology — single instance or HA pair? Suggested: HA pair via Prometheus federation for V1+ (avoids alert blind spots during scrape window).
- Q-L1I-2: Long-term metric retention — Cortex/Thanos? Suggested: V1 = 30d Prometheus native; V1+30d = Thanos sidecar for 1y+ retention.

---

## §8. L1.J — Degraded Mode Handlers

**Owning chunks:** C03 §12O.8, SR06-D5 (Service mode enum)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.J.1 | `contracts/meta/fallback.go` (already L1.B.3) | Code | Meta-side degraded buffer + flush |
| L1.J.2 | `contracts/lifecycle/service_mode.go` | Code | `ServiceMode` enum (Full/Limited/Essentials/ReadOnly/Offline) per SR6-D5 |
| L1.J.3 | `contracts/lifecycle/mode_propagation.go` | Code | Redis control channel `lw:dependency:control` consumer/emitter |
| L1.J.4 | `services/*/internal/buffer_flush/` per service | Code | Service-specific buffer flush hooks |
| L1.J.5 | `chaos/drills/meta_outage.yaml` | Chaos | Periodic chaos drill |
| L1.J.6 | `tests/integration/degraded_mode_test.go` | Test | Kill meta primary, verify buffer fills + correctly bounded + flushes on recovery |
| L1.J.7 | `runbooks/degraded_mode/recovery.md` | Doc | SRE runbook |

**Dependencies:** L1.B (fallback.go), L1.E (meta HA infra exists to fail-over from)

**Acceptance criteria:**
- Buffer fills correctly + bounded at 10K
- Mode propagation reaches all services within 5s
- Chaos drill (meta_outage) → all services enter Limited mode → recovery → flush succeeds → Mode=Full restored
- Admin commands gated on fresh ack (R9 close confirmations) are correctly blocked

**Open questions:**
- Q-L1J-1: Redis control channel — separate Redis from cache Redis? Suggested: same Redis (lower infra footprint); document risk if Redis itself dies.

---

## §9. L1.K — CI Lints + Validators

**Owning chunks:** S04 §12T.6 (meta-write discipline), S08 §12X.3 (pii classify), C05 §12Q (transitions validation), SR06 I16 (timeout), SR08 I17 (capacity budget), SR10 I18 (dep pinning), SR12 I19 (obs inventory)

**Artifacts (CI lint scripts):**

| ID | Script | Owning invariant / chunk | Block-on |
|---|---|---|---|
| L1.K.1 | `meta-write-discipline-lint.sh` | I8 / S04 §12T.6 | Direct INSERT/UPDATE on meta tables outside `contracts/meta/` |
| L1.K.2 | `pii-classify-lint.sh` | S08 §12X.3 | Migration without `@pii_sensitivity` / `@retention_class` / `@erasure_method` / `@legal_basis` tags |
| L1.K.3 | `transitions-validation-lint.sh` | C05 §12Q.6 | Invalid `transitions.yaml` graph (unreachable states, no terminal) |
| L1.K.4 | `shard-allocation-validation.sh` | R04 §12D.6 | Shard allocator violating capacity thresholds |
| L1.K.5 | `migration-idempotency-validator.sh` | R04 §12D.2 | Non-idempotent migration patterns |
| L1.K.6 | `observability-inventory-lint.sh` | SR12 I19 | `lw_*` metric emit without `inventory.yaml` entry |
| L1.K.7 | `capacity-budget-lint.sh` | SR08 I17 | Service missing from `budgets.yaml` |
| L1.K.8 | `dep-pinning-lint.sh` | SR10 I18 | Unhashed dep declaration in go.sum / package-lock.json / uv.lock / Dockerfile FROM |
| L1.K.9 | `timeout-discipline-lint.sh` | SR06 I16 | Outbound call without timeout declaration |
| L1.K.10 | `language-rule-lint.sh` | I3 amended | Service file in wrong language (e.g., world-service must be Rust per amended I3) |
| L1.K.11 | `role-grant-validator.sh` | S04-D6 / §12T.7 | Per-service Postgres grants violating L7 least-privilege table |
| L1.K.12 | `outbox-event-emit-lint.sh` | I13 | Direct `redis.XAdd` outside `services/publisher/` |
| L1.K.13 | `service-acl-matrix-lint.sh` | I11 / S11 §12AA | New RPC without ACL matrix entry |
| L1.K.14 | `prompt-assembly-discipline-lint.sh` | I2 / I10 / S09 §12Y | Direct `litellm/anthropic/openai` SDK call outside `contracts/prompt/` + `services/provider-registry-service/` |
| L1.K.15 | `meta-sensitive-read-bypass-lint.sh` | S04 §12T.6 | Sensitive-table read outside `contracts/meta/read_audit.go` instrumentation |

**Artifacts (Other):**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.K.16 | `.github/workflows/lint-foundation.yml` | CI | Wires all 15 lints into PR check |
| L1.K.17 | `Makefile` `lint:` target | Make | Local dev convenience |
| L1.K.18 | `docs/governance/lint-catalog.md` | Doc | Lint registry for code review checklist |

**Dependencies:** All L1.A-J artifacts (each lint enforces a specific invariant established by those)

**Acceptance criteria:**
- All 15 lints pass on green codebase
- Each lint has a test fixture that injects a violation; lint fails as expected
- CI pipeline runs all lints in parallel; total wall-clock ≤ 3min

**Open questions:**
- Q-L1K-1: Lint tool choices — semgrep / shellcheck / Go static analysis? Suggested: mix — semgrep for cross-language patterns; pure shell + grep where simple; Go static analysis (`go vet` extensions) for Go-specific.
- Q-L1K-2: When does `language-rule-lint.sh` enforce I3 amendment? Suggested: in same commit as I3 amendment (final CLARIFY artifact).

---

## §10. L1.L — V1→V3 Capacity Progression Gates

**Owning chunks:** R04 §12D.9-10, I17 / SR08 §12AK, S5-D5 (admin/capacity-override)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L1.L.1 | `docs/governance/capacity-progression.md` | Doc | Documented V1/V2/V3 progression + transition triggers |
| L1.L.2 | `contracts/capacity/budgets.yaml` | Config | Per-service capacity budgets — initial entries for all foundation services + 12 existing services |
| L1.L.3 | `services/admin-cli/commands/capacity_override.go` | Code | `admin/capacity-override` command (S5 Tier 2, 24h auto-expire) |
| L1.L.4 | `dashboards/capacity-planner.json` | Grafana | Per-shard fullness + projection |
| L1.L.5 | `infra/k8s/hpa/` per service | IaC | HPA configs for web/llm-gateway class |
| L1.L.6 | `infra/k8s/keda/` per worker | IaC | KEDA configs for worker class |
| L1.L.7 | `tests/integration/capacity_override_test.go` | Test | Admin override grants 24h, auto-expires, audit row written |

**Dependencies:** L1.K.7 (`capacity-budget-lint.sh`), L1.A.6.4 (`shard_utilization` table), L1.A.6.5 (`scaling_events` table)

**Acceptance criteria:**
- `budgets.yaml` covers all services
- `capacity-budget-lint.sh` fails on missing service
- Override command audits via S5 Tier 2 flow
- Override expires after 24h (verified by clock-mock test)

**Open questions:**
- Q-L1L-1: HPA + KEDA infra — K8s assumed? AWS ECS alternative? Suggested: K8s for foundation infra (matches CLAUDE.md hosting model "AWS ECS/EC2, RDS, S3, ElastiCache"). Verify ECS vs EKS choice.

---

## §11. L1 cross-component dependency graph

```
L1.E (Postgres + Patroni infra) ──┬─→ L1.B (Meta library)
                                  └─→ L1.G (Pgbouncer)
                                  
L1.B ─→ L1.C (Provisioner uses MetaWrite)
     ─→ L1.D (Orchestrator uses MetaWrite)
     ─→ L1.H (Backup scheduler reads reality_registry)
     ─→ L1.J (Degraded mode buffer in lib)

L1.C ─→ L1.I (Provisioner registers Prometheus scrape)
     ─→ L1.G (Provisioner registers pgbouncer entry)

L1.F (Cache) ←─ L1.B
              ←─ L2 publisher (emits cache-invalidation events) [L2 dependency]

L1.K (Lints) ─ depends on ALL above (enforces invariants from each)
L1.L (Capacity) ─ depends on L1.K.7, L1.A.6.4-5

Roughly: L1.E → L1.B + L1.G → L1.C + L1.D + L1.H → L1.I + L1.F + L1.J → L1.K + L1.L
```

---

## §12. Cycle-decomposition hint for full L1 (do not lock yet)

Combining L1.A (3-4 cycles from L1A_meta_tables.md §9) + L1.B-L:

| Cycle | Scope | Why grouped |
|---|---|---|
| L1-cycle-1 | L1.E (Meta HA infra, Patroni, etcd, WAL) | Foundation must boot before everything; pure IaC + ops; independent test |
| L1-cycle-2 | L1.A-1 + L1.B (Routing/lifecycle tables + meta library) | Library and the routing-critical tables go together — first writeable meta surface |
| L1-cycle-3 | L1.A-2 + L1.A-3 (PII + Audit tables) | PII + audit are coupled by crypto-shred + append-only enforcement |
| L1-cycle-4 | L1.C + L1.G + L1.F (Provisioner + pgbouncer + cache) | Per-reality DB-lifecycle ops; provisioner uses pgbouncer; cache invalidation tested |
| L1-cycle-5 | L1.D + L1.I (Migration orchestrator + per-DB metrics) | Orchestrator emits metrics; coupled QA |
| L1-cycle-6 | L1.A-4 + L1.H + L1.L (Billing/SRE tables + Backup + Capacity gates) | Lower-priority foundational tables + backup tier + capacity progression |
| L1-cycle-7 | L1.J + L1.K (Degraded mode + 15 CI lints) | Cross-cutting; depends on all prior cycles; final L1 quality gate |

**Total L1 estimate: ~7 RAID XL cycles.**

---

## §13. Status

```
[x] L1.C — enumerated (9 artifacts)
[x] L1.D — enumerated (9 artifacts)
[x] L1.E — enumerated (12 artifacts)
[x] L1.F — enumerated (6 artifacts)
[x] L1.G — enumerated (6 artifacts)
[x] L1.H — enumerated (7 artifacts)
[x] L1.I — enumerated (9 artifacts)
[x] L1.J — enumerated (7 artifacts)
[x] L1.K — enumerated (15 lints + 3 other)
[x] L1.L — enumerated (7 artifacts)
[x] Cross-component dependency graph
[x] L1 cycle decomposition hint
[ ] Open questions across L1.C-L resolved (~12 items)
[ ] Continue to L2 (Event sourcing)
```
