# L3 — Snapshot + Projection Runtime

> **Parent:** [_index.md](_index.md)
> **Depth target:** B (artifact-level)
> **Status:** DRAFT — first-pass enumeration

---

## §1. Scope of L3

Per-reality DB projection materialization + read-path snapshot fold + integrity guarantees.

**Relationship to L2:**
- L2.E ships `aggregate_snapshots` table + snapshot WRITE policy (when to snapshot)
- L3.C ships snapshot READ runtime (load + replay-since-snapshot)
- L2.A `events` table is the SSOT; L3 projections are derived
- L3 owns the actual `apply_event(state, event) → state'` fold logic per aggregate type

**IN scope:**
- L3.A 10 projection tables (pc/pc_inventory/pc_relationship/npc/npc_session_memory/npc_pc_relationship/npc_session_memory_embedding/region/world_kv/session_participants)
- L3.B `Projection` trait + per-aggregate `apply_event()` runtime (Rust)
- L3.C Snapshot READ runtime (`load_aggregate`)
- L3.D Per-aggregate parallel rebuilder (R02 §12B.2)
- L3.E Daily sampling integrity checker (R02 §12B.4)
- L3.F Monthly full integrity check (R02 §12B.4)
- L3.G V1 freeze-rebuild migration strategy (R02 §12B.3)
- L3.H Catastrophic rebuild procedure (R02 §12B.5)
- L3.I pgvector setup (npc_session_memory_embedding HNSW)
- L3.J Projection lag metrics + alerts
- L3.K Drift detection metadata + verification cron

**OUT (deferred):**
- V2 blue-green projection migration (R02 §12B.3 — V2+ scope)
- DF9 admin tooling for rebuild ops
- Async projections (V3+, deferred per L2 §1)
- Cross-reality projection (not allowed per I7 — handled by meta-worker writing to per-reality projections)

---

## §2. Sub-components

### L3.A — Projection tables (10 tables)

**Owning chunks:** 00_overview §5 (projections), §12S.2 (session-scoped NPC memory), §12G (concurrency for session_participants)

**Tables (per-reality DB):**

| ID | Table | Purpose | Owning chunk | Key columns |
|---|---|---|---|---|
| L3.A.1 | `pc_projection` | PC primary state | §5.1 | `pc_id PK`, `user_id`, `name`, `current_region_id`, `status`, `stats JSONB`, `last_event_version`, `last_verified_at`, `last_verified_event_version` (R02 §12B.4) |
| L3.A.2 | `pc_inventory_projection` | Per-PC items + MV5 P5 origin reality | §5.1 | `(pc_id, item_code) PK`, `quantity`, `metadata`, `origin_reality_id` (V1 nullable, MV5 future) |
| L3.A.3 | `pc_relationship_projection` | PC↔PC, PC↔NPC scores | §5.1 | `(pc_id, other_entity_type, other_entity_id) PK`, `score INT`, `labels TEXT[]` |
| L3.A.4 | `npc_projection` | NPC primary state (mood, beliefs, flexible state) | §5.2 | `npc_id PK`, `glossary_entity_id` (read-only ref), `current_region_id`, `mood`, `core_beliefs JSONB` (author-locked), `flexible_state JSONB` (LLM-drifted), `last_event_version` |
| L3.A.5 | `npc_session_memory_projection` | Per-session NPC memory (S2 capability-scoped) | §12S.2.3 | `(npc_id, session_id) PK`, `reality_id`, `aggregate_id` (uuidv5), `summary TEXT`, `facts JSONB`, `session_started_at`, `session_ended_at`, `interaction_count`, `archive_status` (`active|faded|summary_only|archived`) |
| L3.A.6 | `npc_pc_relationship_projection` | NPC↔PC relationship (durable) | §12S.2.4 | `(npc_id, other_entity_id) PK`, `other_entity_type`, `reality_id`, `trust_level INT (-100..+100)`, `familiarity_count`, `last_session_id`, `relationship_labels TEXT[]` |
| L3.A.7 | `npc_session_memory_embedding` | pgvector embedding for retrieval | §12S.2 | `(npc_id, session_id) PK`, `embedding vector(1536)`, `content_hash`, HNSW index `vector_cosine_ops` |
| L3.A.8 | `region_projection` | Region state + items on floor + exits + ambient | §5.3 | `region_id PK`, `code`, `display_name`, `description`, `parent_region_id`, `exits JSONB`, `floor_items JSONB`, `ambient_state JSONB`, `last_event_version` |
| L3.A.9 | `world_kv_projection` | Free-form world key-value (quest flags, global events) | §5.4 | `key TEXT PK`, `value JSONB`, `last_event_version`, `updated_at` |
| L3.A.10 | `session_participants` | Capability-scoped membership (S2 foundation) | §12S.2 | `(session_id, participant_type, participant_id) PK`, `reality_id`, `joined_at`, `left_at` (NULL = active) |

**Migration:** `contracts/migrations/per_reality/0006_projections.sql` (single migration adding all 10 tables — they're tightly coupled by foreign keys + co-rebuilt)

**Verification metadata (R02 §12B.4 adds to ALL projection tables):**
```sql
ALTER TABLE <projection> ADD COLUMN last_verified_at TIMESTAMPTZ;
ALTER TABLE <projection> ADD COLUMN last_verified_event_version BIGINT;
```

---

### L3.B — `Projection` trait + per-aggregate `apply_event()` runtime

**Owning chunks:** 00_overview §4.4 (command flow), §5 (projections), 04_player_character (PC state model)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.B.1 | `crates/dp-kernel/src/projection.rs` | Rust trait | `Projection` trait — `apply_event(state, event) → state'` |
| L3.B.2 | `crates/dp-kernel-macros/src/derive_projection.rs` | Proc-macro | `#[derive(Projection)]` macro (companion to `#[derive(Aggregate)]`) |
| L3.B.3 | `crates/projections/pc/` Rust | Code | PC + pc_inventory + pc_relationship projection logic |
| L3.B.4 | `crates/projections/npc/` Rust | Code | NPC + npc_session_memory + npc_pc_relationship + embedding projection logic |
| L3.B.5 | `crates/projections/region/` Rust | Code | region projection logic |
| L3.B.6 | `crates/projections/world_kv/` Rust | Code | world_kv projection logic |
| L3.B.7 | `crates/projections/session/` Rust | Code | session_participants projection logic (S2 capability binding) |
| L3.B.8 | `tests/integration/projection_apply_test.rs` | Test | For each event type, apply produces expected projection delta |
| L3.B.9 | `tests/integration/projection_idempotency_test.rs` | Test | `apply(state, event)` is idempotent if `event_version ≤ state.last_event_version` (skip path) |

**Acceptance criteria:**
- `apply_event` is pure function: no side effects, deterministic per `(state, event)` input
- Idempotency check via `last_event_version` works (skip already-applied events)
- All event types in registry have at least one projection that handles them (CI gate)

**Open question:**
- Q-L3B-1: Should `Projection` trait support multiple projections per event (e.g., `pc.said` updates BOTH `pc_projection.last_event_version` AND triggers `npc_session_memory_projection.interaction_count++`)? Suggested: yes; trait returns `Vec<ProjectionUpdate>`.

---

### L3.C — Snapshot READ runtime (`load_aggregate`)

**Owning chunks:** 00_overview §6 (snapshot policy), §6 (load-aggregate algorithm)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.C.1 | `crates/dp-kernel/src/snapshot_runtime.rs` | Rust | `load_aggregate(type, id) → State` algorithm |
| L3.C.2 | `crates/dp-kernel/src/snapshot_cache.rs` | Rust | In-memory LRU cache of recent snapshots (per-process) |
| L3.C.3 | `tests/integration/load_aggregate_test.rs` | Test | Bytes-equal: `load_from_snapshot+replay == load_from_event_0` |
| L3.C.4 | `tests/integration/snapshot_cache_test.rs` | Test | Cache hit on repeat load; eviction on memory pressure |

**Acceptance criteria:**
- Load aggregate latency < 50ms P99 at version 10K
- Snapshot cache hit rate ≥ 80% in steady-state workload
- Cache eviction respects memory bound (configurable)

---

### L3.D — Per-aggregate parallel rebuilder (R02 §12B.2)

**Owning chunks:** R02 §12B.2

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.D.1 | `services/world-service/internal/rebuilder/` Rust | Code | Work-stealing queue, configurable worker pool |
| L3.D.2 | `contracts/rebuild/config.yaml` | Config | `storage.rebuild.parallel_workers = 8` |
| L3.D.3 | `services/world-service/cmd/rebuild_reality/` Rust | Binary | Admin command (called via admin-cli) |
| L3.D.4 | `tests/integration/parallel_rebuild_test.rs` | Test | 500 aggregates × 200 events; rebuild < 1s; verify byte-equal projections |

**Acceptance criteria:**
- 8 workers achieve ≥6× speedup over 1 worker on 500-aggregate fixture
- Graceful cancellation on timeout (configurable)
- No memory blowup (bounded worker pool + bounded queue)

---

### L3.E — Daily sampling integrity checker (R02 §12B.4)

**Owning chunks:** R02 §12B.4

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.E.1 | `services/integrity-checker/` Go service | Code | Per-reality daily cron |
| L3.E.2 | `services/integrity-checker/internal/sampler/` | Code | Picks 20 random aggregates (configurable) |
| L3.E.3 | `services/integrity-checker/internal/comparator/` | Code | Replays events from snapshot, diffs against live projection |
| L3.E.4 | `contracts/integrity/config.yaml` | Config | `sample_size = 20`, `daily_enabled = true` |
| L3.E.5 | `tests/integration/integrity_drift_test.go` | Test | Inject manual projection drift; verify checker detects and marks for rebuild |
| L3.E.6 | `runbooks/integrity/drift_alert.md` | Doc | SRE response procedure |

**Acceptance criteria:**
- Drift detected within 24h (daily run)
- False positive rate < 1%
- Drift marks aggregate for targeted rebuild (writes to a `drift_queue` per-reality table)

**Open question:**
- Q-L3E-1: integrity-checker per-reality cron — separate service or part of world-service? Suggested: separate (different ops cadence, can scale independently).

---

### L3.F — Monthly full integrity check (R02 §12B.4)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.F.1 | `services/integrity-checker/internal/full_check/` | Code | Shadow projection rebuild + full diff |
| L3.F.2 | `contracts/integrity/config.yaml` extension | Config | `full_check_interval_days = 30` |
| L3.F.3 | `infra/k8s/integrity-checker-cronjob.yaml` | IaC | Scheduled during low-traffic window |
| L3.F.4 | `tests/integration/full_integrity_test.go` | Test | Synthetic drift on 100 aggregates; full check detects all |
| L3.F.5 | `runbooks/integrity/full_check_failure.md` | Doc | SRE |

**Acceptance criteria:**
- Full check completes < 1h for 10K-aggregate reality
- All drifted aggregates flagged
- Runs only during low-traffic window (configurable)

---

### L3.G — V1 freeze-rebuild schema migration strategy

**Owning chunks:** R02 §12B.3 V1 strategy

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.G.1 | `services/admin-cli/commands/rebuild_projection.go` | Code | Admin command — set status='rebuilding', migrate, rebuild, set status='active' |
| L3.G.2 | `contracts/meta/transitions.yaml` reality state additions | Config | Add `rebuilding` state + transitions (`active → rebuilding`, `rebuilding → active`) |
| L3.G.3 | `services/world-service/middleware/maintenance_gate.rs` | Code | Reject writes if reality.status='rebuilding'; surface 503 + maintenance screen to clients |
| L3.G.4 | `tests/integration/schema_migration_test.go` | Test | Freeze reality, add column, rebuild, thaw; verify projection has new column populated correctly |

**Acceptance criteria:**
- Reality unavailable bounded (seconds to minutes per R02 §12B.3 V1)
- Writes correctly rejected during rebuild
- Lifecycle transitions audited (`lifecycle_transition_audit` row written)

---

### L3.H — Catastrophic rebuild procedure (R02 §12B.5)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.H.1 | `services/admin-cli/commands/catastrophic_rebuild.go` | Code | Admin command — `--scope=reality`/`--scope=all-realities`/`--scope=aggregate-list` |
| L3.H.2 | `services/admin-cli/internal/rolling_rebuild/` | Code | Rolling across N realities, max 50 concurrent |
| L3.H.3 | `contracts/rebuild/catastrophic_config.yaml` | Config | `rolling_concurrency = 50`, `freeze_timeout_minutes = 30` |
| L3.H.4 | `tests/integration/catastrophic_rebuild_test.go` | Test | Corrupt projection on 10 realities; rolling rebuild restores all within timeout |
| L3.H.5 | `runbooks/disaster/projection_loss.md` | Doc | Full incident runbook |

**Acceptance criteria:**
- Per-reality rebuild < 10min with snapshots, < 30min without
- Rolling concurrency = 50 verified (no more than 50 realities frozen simultaneously)
- Audit row written for each rebuild attempt

---

### L3.I — pgvector setup (npc_session_memory_embedding HNSW)

**Owning chunks:** §12S.2 (session-scoped memory), R11 §12K (pgvector footprint)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.I.1 | `contracts/migrations/per_reality/0007_pgvector_setup.sql` | SQL | `CREATE EXTENSION vector;` (in provisioner R04 §12D.1 step 4) |
| L3.I.2 | `contracts/migrations/per_reality/0006_projections.sql` extension | SQL | HNSW index `npc_session_memory_embedding USING hnsw (embedding vector_cosine_ops)` |
| L3.I.3 | `crates/projections/npc/embedding_writer.rs` | Rust | Computes embedding via LLM provider (BYOK), writes to projection table |
| L3.I.4 | `services/world-service/internal/embedding_queue/` | Code | Async queue (per-session debounce) to avoid embedding storm on every interaction |
| L3.I.5 | `tests/integration/embedding_retrieval_test.rs` | Test | Cosine similarity search returns expected ranking |
| L3.I.6 | `infra/postgres/extensions.conf` | Config | `shared_preload_libraries='vector'` (Postgres restart required after add) |

**Acceptance criteria:**
- pgvector extension installed on every per-reality DB at provisioning time
- HNSW index queryable < 10ms P99 for 100K-vector dataset
- Embedding writer respects R11 footprint budget (no embedding storm)

**Open question:**
- Q-L3I-1: Embedding model dimension — 1536 (OpenAI text-embedding-ada-002) hard-coded per §12S.2 schema. If user BYOK uses 768 (smaller model) or 3072 (larger), how to handle? Suggested: lock to 1536 in V1; flexible via separate table per dimension in V2+.

---

### L3.J — Projection lag metrics + alerts

**Owning chunks:** R02 §12B.4 metadata, I19 obs inventory

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.J.1 | `crates/dp-kernel/src/projection_metrics.rs` | Rust | Emits `lw_projection_lag_seconds{reality_id, table}` + `lw_projection_drift_count{reality_id, table}` |
| L3.J.2 | `infra/prometheus/alerts/projection.yaml` | Config | Lag > 60s page; drift > 0 page |
| L3.J.3 | `contracts/observability/inventory.yaml` entries | Registry | All L3 metrics declared (I19) |
| L3.J.4 | `dashboards/projection-health.json` | Grafana | Per-reality projection health view |

**Acceptance criteria:**
- All `lw_projection_*` metrics in `inventory.yaml`
- Alerts fire per threshold
- Dashboard shows per-reality + per-table lag

---

### L3.K — Drift detection metadata + verification cron

**Owning chunks:** R02 §12B.4

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L3.K.1 | `contracts/migrations/per_reality/0008_verification_metadata.sql` | SQL | Adds `last_verified_at` + `last_verified_event_version` to all projection tables (L3.A.1-10) |
| L3.K.2 | `services/integrity-checker/internal/verifier/` | Code | Updates `last_verified_*` after successful verification (used by both daily L3.E and monthly L3.F) |
| L3.K.3 | `tests/integration/verification_metadata_test.go` | Test | After integrity check, `last_verified_event_version = current event version` |

**Acceptance criteria:**
- Verification metadata correctly updated after both daily + monthly check
- Stale verification (last_verified_at > 7d) → alert

---

## §3. L3 cross-component dependency graph

```
L3.A (projection tables) ──┬─→ L3.B (Projection runtime — apply_event)
                           ├─→ L3.D (parallel rebuilder)
                           ├─→ L3.E + L3.F (integrity checks)
                           ├─→ L3.G + L3.H (rebuild strategies)
                           └─→ L3.K (verification metadata)

L3.B ←─ L2.A (events) + L2.F (event registry)
L3.B ←─ L2.E (aggregate_snapshots) + L3.C (snapshot read runtime)

L3.D ←─ L3.B + L3.C
L3.E + L3.F ←─ L3.D (re-runs rebuild on flagged drift)
L3.G + L3.H ←─ L3.D + L1.B (AttemptStateTransition for reality status)

L3.I (pgvector) ←─ L1.C (provisioner installs extension) + L3.A.7

L3.J (metrics) ←─ ALL L3 components
L3.K ←─ L3.A (metadata columns) + L3.E + L3.F

Approximate ordering: L3.B (runtime) → L3.A (tables) → L3.C + L3.D (snapshot/rebuild) → L3.E + L3.F + L3.K (integrity) → L3.G + L3.H (migration/disaster) → L3.I (pgvector) → L3.J (metrics)
```

---

## §4. Acceptance criteria for whole L3 (RAID verify gate)

- All 10 projection tables created
- `apply_event` correctness: `replay_all_events(reality) == derive_projection(state_0, all_events)`
- Load-aggregate latency < 50ms P99 at version 10K
- Parallel rebuild speedup ≥ 6× with 8 workers
- Integrity checker daily catches injected drift within 24h
- Catastrophic rebuild < 10min per reality (with snapshots)
- pgvector HNSW search < 10ms P99
- All L3 metrics in observability inventory

---

## §5. Open questions surfaced during L3 enumeration

| # | Question | Suggested resolution | Status |
|---|---|---|---|
| Q-L3-1 | Embedding worker placement — in world-service vs dedicated `embedding-worker`? | V1: in world-service async queue; V1+30d: extract if embedding volume justifies | Suggested |
| Q-L3-2 | Async projection (V3+ per 00_overview §4.6) — confirm OUT of foundation? | YES OUT | Confirmed by L2 §1 |
| Q-L3B-1 | Projection trait — multiple projections per event support? | YES — `Vec<ProjectionUpdate>` return type | Suggested |
| Q-L3E-1 | integrity-checker — separate service or in world-service? | Separate (different ops cadence) | Suggested |
| Q-L3I-1 | Embedding dimension 1536 hard-coded — what if BYOK uses different model? | V1 lock 1536; V2+ flexible per-table per-dimension | Suggested |
| Q-L3-3 | Catastrophic rebuild orchestrator — admin-cli sub-command or new service? | admin-cli sub-command (`rolling_rebuild` internal lib) | Suggested |
| Q-L3-4 | Verification metadata columns on EVERY projection table — accept slight schema bloat? | YES; minimal overhead, required for integrity guarantees | Suggested |
| Q-L3-5 | V2 blue-green migration deferred — should foundation ship scaffolding? | NO; pure V2+ work (R02 §12B.3) | Confirmed by R02 §12B.8 |

---

## §6. Cycle decomposition hint for L3

| Cycle | Scope | Why grouped |
|---|---|---|
| L3-cycle-1 | L3.B + L3.C (Projection trait + snapshot read runtime) | Pure kernel runtime; no DB tables yet; foundation for everything else |
| L3-cycle-2 | L3.A + L3.K (10 projection tables + verification metadata) | Schema migration; depends on L3.B trait exists |
| L3-cycle-3 | L3.D + L3.G + L3.H (Rebuild — parallel + freeze + catastrophic) | All rebuild paths together; share rebuilder code |
| L3-cycle-4 | L3.E + L3.F + L3.J (Integrity checker + metrics) | Daily + monthly + drift alerts; runs on top of L3.D rebuilder |
| L3-cycle-5 | L3.I (pgvector + embedding queue) | Separable; depends on L3.A.7 table exists |

**Total L3 estimate: ~5 RAID XL cycles.**

---

## §7. Status

```
[x] L3 — 11 sub-components enumerated at B-level (A-K)
[x] L3 — cross-component deps mapped
[x] L3 — 8 open questions surfaced (6 suggested defaults, 2 confirmed)
[x] L3 — cycle decomposition hint (~5 cycles)
[ ] L3 — open questions resolved (batch at end of all layers)
[ ] Continue to L4 (SDK / Kernel API)
```
