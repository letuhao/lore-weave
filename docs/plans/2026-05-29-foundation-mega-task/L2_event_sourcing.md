# L2 — Event Sourcing + Outbox + Publisher

> **Parent:** [_index.md](_index.md)
> **Depth target:** B (artifact-level)
> **Status:** DRAFT — first-pass enumeration

---

## §1. Scope of L2

Per-reality event sourcing infrastructure + cross-service event propagation.
Lives **per-reality DB** (NOT meta), with publisher in meta-adjacent territory.

**IN scope:**
- L2.A `events` table schema + 6-layer R1 volume mitigation
- L2.B `event_audit` table + audit pipeline (high-volume LLM forensics, short retention)
- L2.C `events_outbox` + `outbox.Write()` helper
- L2.D Publisher service (R06 — drains outbox → Redis Streams)
- L2.E `aggregate_snapshots` table + snapshot policy
- L2.F Event schema registry (R03 schema-as-code)
- L2.G Codegen tool `eventgen` (Go → TS + Python)
- L2.H Upcaster chain library
- L2.I Schema validation on write
- L2.J Tiered archive pipeline (hot Postgres → warm partition → MinIO Parquet/ZSTD)
- L2.K Per-reality cleanup cron (R1-L3 retention enforcement)
- L2.L `xreality.*` topic infrastructure (R05 cross-instance propagation)

**OUT (deferred):**
- Async projections (V3+ per 00_overview §4.6)
- L6 archive upgrade (V2+ per R03 §12C.6)
- Advanced upcaster optimization
- L5 snapshot-then-truncate (V3+ per R01 §12A.5)

---

## §2. Sub-components

### L2.A — `events` table schema + retention pipeline

**Owning chunks:** 00_overview §4.2 (envelope), R01 §12A (volume mitigation L1-L6), 12S (privacy fields), §12G (concurrency)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.A.1 | `contracts/migrations/per_reality/0001_events_table.sql` | SQL | Full schema with PK `(reality_id, aggregate_type, aggregate_id, aggregate_version)`, partitioned by `created_at` range, lz4 compression on `payload`+`metadata`, indexes |
| L2.A.2 | `contracts/migrations/per_reality/0002_events_privacy_constraints.sql` | SQL | §12S CHECK constraints: whisper_target_required, privacy_cascade_consistency |
| L2.A.3 | `contracts/events/envelope.rs` | Rust struct | Event envelope type — Rust-side |
| L2.A.4 | `contracts/events/envelope.go` | Go struct | Event envelope — Go side |
| L2.A.5 | `crates/dp-kernel/src/event.rs` | Rust trait | `Event` trait — generic event interface |
| L2.A.6 | `tests/integration/event_append_concurrency_test.rs` | Test | Optimistic concurrency: parallel writes on same aggregate, only 1 succeeds, others get `ErrConcurrencyConflict` |
| L2.A.7 | `tests/integration/event_partition_test.rs` | Test | Range partition by month works; old partitions detachable |

**Acceptance criteria:**
- Append 10K events to single aggregate; verify monotonic version
- Concurrent appends on same `(reality_id, aggregate_id)` — only one succeeds per version
- lz4 compression reduces JSONB size 40%+ (measured on representative payloads)
- Partition detach works without blocking new appends

---

### L2.B — `event_audit` table + audit pipeline

**Owning chunks:** R01 §12A.1 (audit split)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.B.1 | `contracts/migrations/per_reality/0003_event_audit_table.sql` | SQL | Full schema with partition by month, lz4 on text+jsonb columns |
| L2.B.2 | `contracts/events/audit_helpers.rs` | Rust | Helper to write event + linked audit row in same TX |
| L2.B.3 | `scripts/event-audit-retention-cron.sh` | Cron | Nightly cleanup per R01 §12A.3 (30d audit retention, 90d flagged) |
| L2.B.4 | `tests/integration/event_audit_link_test.rs` | Test | Append event + audit; `events.audit_ref` correctly populated; cron prunes old audit |

**Acceptance criteria:**
- `events.audit_ref` set in same TX as `event_audit` row
- Audit row can be missing (FK is logical, not enforced — events archived independently)
- Nightly cron prunes >30d non-flagged audit; flagged kept 90d

---

### L2.C — `events_outbox` + `outbox.Write()` helper (I13)

**Owning chunks:** R06 §12F.1, I13 invariant

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.C.1 | `contracts/migrations/per_reality/0004_events_outbox_table.sql` | SQL | Schema per R06: `event_id`, `reality_id`, `published BOOL`, `attempts INT`, `last_error TEXT`, `last_attempt_at`, `dead_lettered_at`, plus 2 partial indexes (pending + dead_letter) |
| L2.C.2 | `crates/dp-kernel/src/outbox.rs` | Rust | `outbox::write(ctx, tx, event)` — must be called inside same TX as event append |
| L2.C.3 | `contracts/events/outbox.go` | Go | Same API for Go services (publisher, meta-worker) |
| L2.C.4 | `scripts/outbox-event-emit-lint.sh` | CI lint | (Already L1.K.12) Block direct `redis.XAdd` outside `services/publisher/` |
| L2.C.5 | `tests/integration/outbox_atomicity_test.rs` | Test | Event append + outbox write in same TX; rollback on partial fail |
| L2.C.6 | `contracts/events/allowlist.yaml` | Config | Which `MetaWrite()`/event types emit outbox events (used by L1.B.6 too) |

**Acceptance criteria:**
- TX rollback on event-append fail → outbox row NOT written
- Outbox row visible to publisher via `WHERE published=FALSE AND dead_lettered_at IS NULL` query
- `FOR UPDATE SKIP LOCKED` works with multi-publisher replicas

---

### L2.D — Publisher service

**Owning chunks:** R06 §12F.2-5 (publisher service, lag monitoring, reconnect, retry/DLQ)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.D.1 | `services/publisher/` Go service | Code | Dedicated service per R06 §12F.2 |
| L2.D.2 | `services/publisher/internal/leader_election/` | Code | Redis SETNX-based leader election (V2+; V1 no-op) |
| L2.D.3 | `services/publisher/internal/poll_loop/` | Code | Polls outbox with `FOR UPDATE SKIP LOCKED`, batches per reality, pushes to Redis Streams |
| L2.D.4 | `services/publisher/internal/retry/` | Code | Exponential backoff + dead-letter at attempts ≥ max |
| L2.D.5 | `services/publisher/internal/heartbeat/` | Code | Writes `publisher_heartbeats` (meta) every 10s |
| L2.D.6 | `services/publisher/cmd/publisher/main.go` | Code | Entry point + Drain integration (SR6-D10) |
| L2.D.7 | `contracts/service_acl/matrix.yaml` entries | ACL | publisher → meta (heartbeat write), publisher → per-reality DB (outbox read), publisher → Redis Streams (xadd) |
| L2.D.8 | `infra/k8s/publisher-deployment.yaml` | IaC | Deployment with multi-replica (V2+) |
| L2.D.9 | `contracts/capacity/budgets.yaml` entry | Config | I17 capacity budget for publisher class |
| L2.D.10 | `tests/integration/publisher_lag_test.rs` | Test | Stop publisher; inject 1000 outbox rows; restart; verify all drained within SLO; verify dead-letter on persistent fail |
| L2.D.11 | `tests/integration/publisher_failover_test.rs` | Test | 2 replicas; kill leader; verify failover within 30s; no duplicate XADD |
| L2.D.12 | `runbooks/publisher/lag.md` | Doc | SRE runbook (R06 §12F.3 thresholds: 10s warn / 60s page / 300s degraded) |

**Acceptance criteria:**
- Outbox lag < 1s P50, < 10s P99 under steady load
- 1000-row dead-letter scenario: all logged with `last_error`, alert fires
- Leader election: no duplicate XADD during failover (verified by Redis stream consumer dedup)

**Open question:**
- Q-L2D-1: V1 deploys 1 publisher replica per shard host. V2 wants multi-replica per shard for HA. Switch trigger? Suggested: V2 = scale beyond 1000 active realities (need parallel-drain capacity).

---

### L2.E — `aggregate_snapshots` table + snapshot mechanism

**Owning chunks:** 00_overview §6, R02 §12B (rebuild)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.E.1 | `contracts/migrations/per_reality/0005_snapshots_table.sql` | SQL | Schema per §6 with PK `(aggregate_type, aggregate_id, aggregate_version)` |
| L2.E.2 | `crates/dp-kernel/src/snapshot.rs` | Rust trait | `Snapshot` trait + `load_aggregate()` algorithm (latest snap + replay since) |
| L2.E.3 | `crates/dp-kernel/src/snapshot_policy.rs` | Rust | Snapshot every 500 events OR 1h in-world-time, keep last 3 |
| L2.E.4 | `services/world-service/internal/snapshot_cron/` Rust | Code | Background cron per aggregate to trigger snapshots |
| L2.E.5 | `tests/integration/aggregate_load_test.rs` | Test | Append 1500 events; load aggregate; verify replay uses snapshot at v1000 + 500 events |
| L2.E.6 | `tests/integration/snapshot_prune_test.rs` | Test | Keep last 3 snapshots; verify older snapshots dropped |

**Acceptance criteria:**
- Load-aggregate latency < 50ms P99 for aggregate at version 10K (with snapshot at 9500)
- Pruning keeps exactly 3 snapshots (configurable)
- Replay correctness: load aggregate from snapshot + replay = load from event 0 (byte-equal projection state)

---

### L2.F — Event schema registry (R03 schema-as-code)

**Owning chunks:** R03 §12C.2 (schema-as-code), §12C.7 (polyglot), I14 (additive-first)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.F.1 | `contracts/events/` monorepo root location | Convention | All Go-annotated event structs live here |
| L2.F.2 | `contracts/events/pc.go`, `npc.go`, `region.go`, `world.go`, etc. | Go | Authoritative event structs with `@event`/`@version`/`@upcast` annotations |
| L2.F.3 | `contracts/events/registry.go` (generated) | Generated | Dispatch table `(event_type, event_version) → struct + upcaster chain` |
| L2.F.4 | `contracts/events/generated/ts/` | Generated | TypeScript interfaces for frontend + api-gateway-bff |
| L2.F.5 | `contracts/events/generated/python/` | Generated | Pydantic models for chat-service, knowledge-service, roleplay-service Python parts |
| L2.F.6 | `contracts/events/generated/rust/` | Generated | Rust types for world-service, travel-service, roleplay-service Rust parts |
| L2.F.7 | `contracts/events/_registry.yaml` | Config | Active + deprecated per event_type (R03 §12C.5 cooldown tracking) |
| L2.F.8 | `tests/integration/registry_load_test.go` | Test | Service startup loads registry from `_registry.yaml`; missing event type → fail-fast |

**Acceptance criteria:**
- Registry generates correctly from annotations
- Service startup fails-fast on registry parse error
- Deprecated event types emit write-time warning per R03 §12C.5

---

### L2.G — Codegen tool `eventgen`

**Owning chunks:** R03 §12C.2, §12C.7

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.G.1 | `tools/eventgen/` Go binary | Tool | Parses `@event`/`@version`/`@upcast` annotations |
| L2.G.2 | `tools/eventgen/codegen/go/` | Templates | Go registry generation |
| L2.G.3 | `tools/eventgen/codegen/ts/` | Templates | TypeScript interface generation |
| L2.G.4 | `tools/eventgen/codegen/python/` | Templates | Pydantic model generation |
| L2.G.5 | `tools/eventgen/codegen/rust/` | Templates | Rust struct generation (via build.rs or pre-build) |
| L2.G.6 | `scripts/eventgen-validate.sh` | CI | CI gate: regenerate + diff; fail if generated files out of sync |
| L2.G.7 | `Makefile` `eventgen:` target | Make | Local dev convenience |

**Acceptance criteria:**
- `eventgen generate` produces all 4 language outputs
- `eventgen validate` succeeds on green codebase
- CI fails on hand-edited generated file
- Missing `@description` annotation → CI fail per R03 §12C.7

---

### L2.H — Upcaster chain library

**Owning chunks:** R03 §12C.3

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.H.1 | `crates/dp-kernel/src/upcaster.rs` | Rust | Upcaster trait + chain composition |
| L2.H.2 | `contracts/events/upcasters/` Rust | Rust | `@upcast` annotated functions (one per pair `(type, vN→vN+1)`) |
| L2.H.3 | `contracts/events/upcasters_go/` Go | Go | Go-side upcasters for Go consumers |
| L2.H.4 | `tools/eventgen` chain composer | Tool | Auto-stitches v1→v2→v3 from individual `@upcast` declarations |
| L2.H.5 | `tests/integration/upcaster_chain_test.rs` | Test | Load v1 event from old archive, verify upcasts to latest; multi-step chain (v1→v2→v3) correct |

**Acceptance criteria:**
- Upcaster chain bytes-perfect: `upcast(v1, target=v3) == upcast(upcast(v1, target=v2), target=v3)`
- Missing intermediate upcaster (v2→v3) → registry load fail per R03 §12C.2

---

### L2.I — Schema validation on write

**Owning chunks:** R03 §12C.4

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.I.1 | `crates/dp-kernel/src/event_validator.rs` | Rust | Validates payload against registered schema before append |
| L2.I.2 | `contracts/events/validators_go/` | Go | Go-side validators |
| L2.I.3 | `tests/integration/event_validation_test.rs` | Test | Inject malformed payload → `ErrUnknownEventSchema` or `ErrSchemaViolation` |

**Acceptance criteria:**
- Malformed event rejected at write time (not at projection rebuild)
- Schema validation latency overhead < 0.5ms per event
- `storage.events.schema_validation.enabled=true` enforced in ALL envs (no dev bypass)

---

### L2.J — Tiered archive pipeline (R1-L4)

**Owning chunks:** R01 §12A.4

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.J.1 | `services/archive-worker/` Go service | Code | Per-reality cron: detach partition → Parquet → MinIO → DROP |
| L2.J.2 | `services/archive-worker/internal/parquet/` | Code | Postgres → Parquet conversion with ZSTD compression |
| L2.J.3 | `infra/minio/lw-world-archive-bucket.tf` | IaC | MinIO bucket (separate from `lw-db-backups`, `lw-meta-wal-archive`) |
| L2.J.4 | `scripts/archive-worker-cron.yaml` | Config | Schedule: monthly partition detach per reality |
| L2.J.5 | `tests/integration/archive_roundtrip_test.go` | Test | Detach partition → upload Parquet → re-read → verify byte-equal to original events |
| L2.J.6 | `runbooks/archive/restore.md` | Doc | Restore-on-demand procedure |

**Acceptance criteria:**
- Archive compression ratio ≥ 5x vs Postgres JSONB
- Restore drill recovers archived events byte-equal
- Archive worker idempotent (re-run safely)

**Open question:**
- Q-L2J-1: Archive worker placement — V1 part of world-service vs dedicated service? Suggested: dedicated `archive-worker` (matches publisher pattern; clear ops boundary).

---

### L2.K — Per-reality cleanup cron (R1-L3 retention)

**Owning chunks:** R01 §12A.3

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.K.1 | `services/retention-worker/` Go service | Code | Per-reality cron with config-driven retention rules |
| L2.K.2 | `contracts/retention/event_classes.yaml` | Config | Per event_type retention class (canon_events / volatile_npc / audit / broadcast) + hot/warm/cold thresholds |
| L2.K.3 | `services/retention-worker/internal/classifier/` | Code | Classifies events by type, applies retention rule |
| L2.K.4 | `tests/integration/retention_test.go` | Test | Inject events of various types; run retention; verify expected events deleted, canon preserved |
| L2.K.5 | `runbooks/retention/audit_recovery.md` | Doc | "What if I accidentally deleted canon" recovery (cold archive restore) |

**Acceptance criteria:**
- Canon events NEVER deleted (CI gate test fixture)
- Non-canon prune per config
- Idempotent (re-run safely)

**Open question:**
- Q-L2K-1: retention-worker and archive-worker — separate services or one binary with two modes? Suggested: separate (different ops cadence, different alert SLOs).

---

### L2.L — `xreality.*` topic infrastructure (R05)

**Owning chunks:** R05 §12E (cross-instance)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L2.L.1 | `contracts/events/xreality/` | Schema | xreality.* event type definitions (subset of normal events, marked `cross_reality: true`) |
| L2.L.2 | `services/publisher/internal/xreality_fanout/` | Code | Publisher detects `cross_reality: true` events → emits to `xreality.<type>` Redis Stream |
| L2.L.3 | `services/meta-worker/` Go service | Code | Sole consumer of `xreality.*` topics (per I7) |
| L2.L.4 | `services/meta-worker/internal/dispatch/` | Code | Routes xreality event to appropriate handler (canon propagation, user-erased, reality stats) |
| L2.L.5 | `contracts/service_acl/matrix.yaml` entries | ACL | meta-worker → meta DB (writes), meta-worker → Redis Streams (xreadgroup) |
| L2.L.6 | `tests/integration/xreality_propagation_test.go` | Test | Emit `xreality.canon.promoted` from reality A; verify meta-worker writes to reality B's canon projection |
| L2.L.7 | `runbooks/meta-worker/lag.md` | Doc | SRE runbook |
| L2.L.8 | `contracts/capacity/budgets.yaml` entry | Config | meta-worker class budget |

**Acceptance criteria:**
- xreality event propagates from emit reality to N consumer realities within 2s P99
- meta-worker is sole xreality writer (verified by ACL CI test)
- No cross-reality DB query path (CROSS_INSTANCE_DATA_ACCESS_POLICY lint pass)

---

## §3. L2 cross-component dependency graph

```
L2.A (events table) ─┬─→ L2.C (outbox) — same TX
                     ├─→ L2.E (snapshots) — projection rebuild source
                     └─→ L2.I (validation) — every append validates

L2.C (outbox) ─→ L2.D (publisher) — drains outbox
L2.D (publisher) ─→ L2.L (xreality fanout) — emits cross-reality topics

L2.F (registry) ─┬─→ L2.G (codegen) — generates from annotations
                 ├─→ L2.H (upcasters) — chain composition
                 └─→ L2.I (validation) — schema lookup

L2.B (event_audit) ─→ L2.A — paired tables in TX

L2.J (archive) ←─ L2.A — detached partitions go to MinIO
L2.K (retention) ←─ L2.A + L2.B — cleanup cron

L2.L (xreality) ←─ L2.D — publisher emits xreality.* topics

Approximate ordering: L2.F + L2.G + L2.H + L2.I (schema infra) → L2.A + L2.B + L2.E (per-reality tables) → L2.C + L2.D (outbox + publisher) → L2.J + L2.K (cleanup) → L2.L (xreality)
```

---

## §4. Acceptance criteria for whole L2 (RAID verify gate)

- All per-reality DB migrations apply cleanly (events, event_audit, snapshots, outbox)
- Event append round-trip: write → outbox row → publisher → Redis Stream → consumer reads
- Snapshot load-aggregate latency < 50ms P99 at version 10K
- Outbox lag < 1s P50 under load
- xreality propagation < 2s P99
- Schema validation rejects malformed events at write
- Upcaster chain replay correct
- Retention cron preserves canon, prunes non-canon
- Archive roundtrip byte-equal

---

## §5. Open questions surfaced during L2 enumeration

| # | Question | Suggested resolution | Status |
|---|---|---|---|
| Q-L2-1 | Sync vs async projection — V1 sync per 00_overview §4.6; foundation locks this? | YES, lock V1 sync. Async V3+. (Already in §1 OUT scope) | Pending lock |
| Q-L2-2 | `events` partition strategy — monthly or weekly? | Monthly (matches archive cadence R01 §12A.4) | Suggested |
| Q-L2-3 | `event_audit` correlation to `events` — FK or just `audit_ref` UUID pointer? | UUID pointer (FK breaks after events archived) | Confirmed by R01 §12A.1 |
| Q-L2D-1 | Publisher multi-replica trigger | V2 = scale beyond 1000 active realities | Suggested |
| Q-L2J-1 | Archive worker placement (in world-service or dedicated)? | Dedicated `archive-worker` service | Suggested |
| Q-L2K-1 | retention-worker and archive-worker — same or separate binary? | Separate (different ops cadence) | Suggested |
| Q-L2-4 | xreality.* topic naming convention — `xreality.<verb>` or `xreality.<aggregate>.<verb>`? | `xreality.<entity>.<verb>` per service map line 60 (already convention) | Confirmed by service map |
| Q-L2-5 | publisher leader election in V1 — N=1 replica means no election needed; should code still implement? | Implement V1 (no-op cost; ready for V2+ scale) | Suggested per R06 §12F.2 |

---

## §6. Cycle decomposition hint for L2

Combining schema infra (G+H+I+F), per-reality data (A+B+E), event flow (C+D+L), cleanup (J+K):

| Cycle | Scope | Why grouped |
|---|---|---|
| L2-cycle-1 | L2.F + L2.G + L2.H + L2.I (Schema infra) | All independent of per-reality DB; foundation for all other L2 work. Codegen → registry → upcasters → validation. |
| L2-cycle-2 | L2.A + L2.B + L2.E (Per-reality tables) | Migration + Rust trait definitions; depends on schema infra exists. Snapshot mechanism. |
| L2-cycle-3 | L2.C + L2.D + L2.L (Outbox + Publisher + xreality) | Event flow end-to-end. Depends on tables exist. Cross-service integration ready. |
| L2-cycle-4 | L2.J + L2.K (Archive + Retention workers) | Cleanup infrastructure; independent of L2-3 but needs L2.A+B existing. Lower priority — can defer if cycle budget tight. |

**Total L2 estimate: ~4 RAID XL cycles.**

---

## §7. Status

```
[x] L2 — 12 sub-components enumerated at B-level
[x] L2 — cross-component deps mapped
[x] L2 — 8 open questions surfaced (5 suggested defaults, 2 confirmed by chunks, 1 pending lock)
[x] L2 — cycle decomposition hint (~4 cycles)
[ ] L2 — open questions resolved (batch at end of all layers)
[ ] Continue to L3 (Snapshot + Projection runtime)
```
