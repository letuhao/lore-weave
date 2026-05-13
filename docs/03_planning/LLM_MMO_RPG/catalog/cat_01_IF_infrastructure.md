<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_01_IF_infrastructure.md
byte_range: 2681-40975
sha256: 184f90400c76ce0ccdc13ad74ef92c4364b02a8496e1088a491bb3d03533c009
generated_by: scripts/chunk_doc.py
-->

## IF — Infrastructure

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| IF-1 | Event-sourced storage (events as SSOT, projections as derived state) | ✅ | INFRA | — | [02 §4](02_STORAGE_ARCHITECTURE.md) |
| IF-2 | Snapshot-fork semantics (peer realities, cascading read) | ✅ | INFRA | IF-1 | [03 §6–7](03_MULTIVERSE_MODEL.md) |
| IF-3 | Reality registry + DB-per-reality with subtree grouping | ✅ | INFRA | IF-1 | [02 §7](02_STORAGE_ARCHITECTURE.md), [03 §7](03_MULTIVERSE_MODEL.md) |
| IF-4 | Meta registry (cross-reality player index, instance routing) | ✅ | INFRA | IF-3 | [02 §7.2, §12E.2](02_STORAGE_ARCHITECTURE.md) |
| IF-4a | Meta-worker service (dedicated Go, xreality.* event consumer) | ✅ | INFRA | IF-4, IF-5 | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) (R5-L2) |
| IF-4b | Cross-instance event propagation (`xreality.*` topics) | ✅ | INFRA | IF-5 | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) (R5-L2) |
| IF-4c | Cross-instance data access governance policy | ✅ | INFRA | — | [docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md](../../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md) (R5 anti-pattern) |
| IF-5 | Realtime transport (Redis Streams + WebSocket fanout per region) | 🟡 | INFRA | IF-1 | [02 §9](02_STORAGE_ARCHITECTURE.md); reuse [70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN](../70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN.md) |
| IF-5a | Session as single-writer command processor (mandatory) | ✅ | V1 | — | [02 §12G.2](02_STORAGE_ARCHITECTURE.md) (R7-L1) |
| IF-5b | Event scope tagging (`session` / `region` / `reality` / `world`) | ✅ | V1 | IF-1 | [02 §12G.3](02_STORAGE_ARCHITECTURE.md) (R7-L2) |
| IF-5c | Cross-session event handler service (dedicated Go) | ✅ | V1 | IF-1 | [02 §12G.5](02_STORAGE_ARCHITECTURE.md) (R7-L3) |
| IF-5d | Session event queue (per session, priority pop before user input) | ✅ | V1 | IF-5a | [02 §12G.4](02_STORAGE_ARCHITECTURE.md) (R7-L4) |
| IF-5e | NPC single-session constraint (V1; multi-presence deferred V2+) | ✅ | V1 | NPC-1 | [02 §12G.7](02_STORAGE_ARCHITECTURE.md) (R7-L6) |
| IF-6 | Outbox pattern (crash-safe publish) | ✅ | INFRA | IF-1, IF-5 | [02 §9.2, §12F.1](02_STORAGE_ARCHITECTURE.md) |
| IF-6a | Publisher service (dedicated Go, leader election, partition-by-reality) | ✅ | INFRA | IF-6 | [02 §12F.2](02_STORAGE_ARCHITECTURE.md) (R6-L2) |
| IF-6b | Per-reality outbox lag monitoring + 3-tier alerts | ✅ | INFRA | IF-6a | [02 §12F.3](02_STORAGE_ARCHITECTURE.md) (R6-L3) |
| IF-6c | Client catchup protocol (WS handshake + REST `/v1/realities/{id}/events?since=`) | ✅ | V1 | IF-6a | [02 §12F.4](02_STORAGE_ARCHITECTURE.md) (R6-L4) |
| IF-6d | Dead-letter queue with retry backoff + admin resolution | ✅ | INFRA | IF-6 | [02 §12F.5](02_STORAGE_ARCHITECTURE.md) (R6-L5) |
| IF-6e | Redis stream MAXLEN + DB fallback (Redis is cache, DB is SSOT) | ✅ | INFRA | IF-6 | [02 §12F.6](02_STORAGE_ARCHITECTURE.md) (R6-L6, resolves R12) |
| IF-6f | Graceful shutdown + handoff | ✅ | INFRA | IF-6a | [02 §12F.7](02_STORAGE_ARCHITECTURE.md) (R6-L7) |
| IF-7 | Event schema versioning + upcaster chain | ✅ | INFRA | IF-1 | [02 §10, §12C.3](02_STORAGE_ARCHITECTURE.md) |
| IF-7a | Additive-first discipline (policy) | ✅ | INFRA | IF-7 | [02 §12C.1](02_STORAGE_ARCHITECTURE.md) (R3-L1 locked) |
| IF-7b | Schema-as-code + registry (Go source + codegen) | ✅ | INFRA | IF-7 | [02 §12C.2](02_STORAGE_ARCHITECTURE.md) (R3-L2 locked) |
| IF-7c | Schema validation on write | ✅ | INFRA | IF-7 | [02 §12C.4](02_STORAGE_ARCHITECTURE.md) (R3-L4 locked) |
| IF-7d | Breaking change via new event_type (90d deprecation cooldown) | ✅ | INFRA | IF-7 | [02 §12C.5](02_STORAGE_ARCHITECTURE.md) (R3-L5 locked) |
| IF-7e | Polyglot type generation (Go → TS + Python) | ✅ | INFRA | IF-7b | [02 §12C.7](02_STORAGE_ARCHITECTURE.md) |
| IF-7f | Archive upgrade (upcast at cold-archive) | 📦 | V2 | IF-10 | [02 §12C.6](02_STORAGE_ARCHITECTURE.md) (R3-L6 deferred V2) |
| IF-8 | Snapshots (per-aggregate periodic checkpoints) | ✅ | INFRA | IF-1 | [02 §6](02_STORAGE_ARCHITECTURE.md) |
| IF-9 | Projection rebuild pipeline | ✅ | INFRA | IF-1, IF-8 | [02 §5.5, §12B](02_STORAGE_ARCHITECTURE.md) |
| IF-9a | Per-aggregate parallel rebuild (8-worker default) | ✅ | INFRA | IF-9 | [02 §12B.2](02_STORAGE_ARCHITECTURE.md) (R2-L2 locked) |
| IF-9b | V1 freeze-rebuild for schema migration | ✅ | V1 | IF-9 | [02 §12B.3](02_STORAGE_ARCHITECTURE.md) (R2-L3 locked) |
| IF-9c | V2 blue-green projection tables (dual-write + atomic swap) | ✅ | V2 | IF-9 | [02 §12B.3](02_STORAGE_ARCHITECTURE.md) (R2-L3 locked) |
| IF-9d | Integrity checker (daily sample + monthly full) | ✅ | V1 | IF-9 | [02 §12B.4](02_STORAGE_ARCHITECTURE.md) (R2-L4 locked) |
| IF-9e | Catastrophic rebuild procedure (freeze-rebuild-thaw, rolling 50 concurrent) | ✅ | V1 | IF-9 | [02 §12B.5](02_STORAGE_ARCHITECTURE.md) (R2-L5 locked) |
| IF-10 | Archive to MinIO (hot/warm/cold tiering of events) | ✅ | INFRA | IF-1 | [02 §11, §12A.4](02_STORAGE_ARCHITECTURE.md) |
| IF-10a | Audit split — separate `event_audit` table from `events` | ✅ | INFRA | IF-1 | [02 §12A.1](02_STORAGE_ARCHITECTURE.md) (R1-L1 locked) |
| IF-10b | Event emission discipline — state events vs derivable, only state events persisted | ✅ | INFRA | IF-1 | [02 §12A.2](02_STORAGE_ARCHITECTURE.md) (R1-L2 locked) |
| IF-10c | Tiered retention per event type (nightly cleanup job) | ✅ | INFRA | IF-10 | [02 §12A.3](02_STORAGE_ARCHITECTURE.md) (R1-L3 locked) |
| IF-10d | Snapshot-then-truncate non-canon aggregates | ✅ | V3 | IF-8 | [02 §12A.5](02_STORAGE_ARCHITECTURE.md) (R1-L5 locked) |
| IF-10e | lz4 compression on JSONB columns + ZSTD for MinIO cold | ✅ | INFRA | IF-1 | [02 §12A.6](02_STORAGE_ARCHITECTURE.md) (R1-L6 locked) |
| IF-11 | Auto-freeze + auto-archive of inactive realities | 🟡 | INFRA | IF-3, IF-10 | [03 §12.1](03_MULTIVERSE_MODEL.md) |
| IF-12 | pgvector-per-reality embedding storage | ✅ | INFRA | IF-3 | Locked S2 |
| IF-13 | Schema migrations across N instance DBs (idempotent, staggered) | ✅ | INFRA | IF-3 | [02 §7.5, §12D.2](02_STORAGE_ARCHITECTURE.md) |
| IF-13a | Automated DB provisioning + deprovisioning | ✅ | INFRA | IF-3 | [02 §12D.1](02_STORAGE_ARCHITECTURE.md) (R4-L1) |
| IF-13b | Migration orchestrator (dedicated Go service) | ✅ | INFRA | IF-13 | [02 §12D.2](02_STORAGE_ARCHITECTURE.md) (R4-L2) |
| IF-13c | Tiered backup strategy (active/frozen/archived → different schedules) | ✅ | INFRA | IF-3, IF-10 | [02 §12D.3](02_STORAGE_ARCHITECTURE.md) (R4-L3) |
| IF-13d | pgbouncer connection pooling (per-shard, transaction mode) | ✅ | INFRA | IF-3 | [02 §12D.4](02_STORAGE_ARCHITECTURE.md) (R4-L4) |
| IF-13e | Metrics aggregation with reality_id labels | ✅ | INFRA | IF-3 | [02 §12D.5](02_STORAGE_ARCHITECTURE.md) (R4-L5) |
| IF-13f | Shared Postgres server sharding (many DBs per server) | ✅ | V2 | IF-3 | [02 §12D.6](02_STORAGE_ARCHITECTURE.md) (R4-L6) |
| IF-13g | Orphan DB detection + cleanup | ✅ | INFRA | IF-3 | [02 §12D.7](02_STORAGE_ARCHITECTURE.md) (R4-L7) |
| IF-13h | DB subtree split runbook — freeze-copy-cutover (V1/V2) | ✅ | V1 | IF-3, IF-13 | [02 §12N.4](02_STORAGE_ARCHITECTURE.md) (C2-D1/D2) |
| IF-13i | `migrating` lifecycle state + `reality_migration_audit` | ✅ | V1 | IF-13h | [02 §12N.3](02_STORAGE_ARCHITECTURE.md) (C2-state) |
| IF-13j | Pre/post-migration integrity verification (reuse R2-L4 logic) | ✅ | V1 | IF-9d, IF-13h | [02 §12N.4](02_STORAGE_ARCHITECTURE.md) step 8 |
| IF-13k | Migration rollback (source untouched until success) | ✅ | V1 | IF-13h | [02 §12N.10](02_STORAGE_ARCHITECTURE.md) |
| IF-13l | Logical-replication split (Tier 2, near-zero-downtime) | 📦 | V3+ | IF-13h | [02 §12N.5](02_STORAGE_ARCHITECTURE.md) (C2-D1 Tier 2) |
| IF-13m | Subtree-split coordination (multi-reality parallel migration) | 📦 | V3+ | IF-13l | [02 §12N.6](02_STORAGE_ARCHITECTURE.md) |
| IF-14 | Meta registry HA — Patroni + sync replica + async replica (C3 resolution) | ✅ | V1 | IF-4 | [02 §12O.3](02_STORAGE_ARCHITECTURE.md) (C3-D1/D2) |
| IF-14a | Meta access library (shared Go, primary/replica routing) | ✅ | V1 | IF-14 | [02 §12O.5](02_STORAGE_ARCHITECTURE.md) (C3-arch) |
| IF-14b | Redis cache for reality routing (30s TTL, xreality invalidation) | ✅ | V1 | IF-14, IF-4b | [02 §12O.6](02_STORAGE_ARCHITECTURE.md) (C3-D3) |
| IF-14c | App-level failover retry + backoff | ✅ | V1 | IF-14 | [02 §12O.7](02_STORAGE_ARCHITECTURE.md) |
| IF-14d | Degraded mode (cache-serve + buffered heartbeats/audit) | ✅ | V1 | IF-14b | [02 §12O.8](02_STORAGE_ARCHITECTURE.md) |
| IF-14e | WAL archive + PITR (30d retention) | ✅ | V1 | IF-14 | [02 §12O.9](02_STORAGE_ARCHITECTURE.md) |
| IF-14f | Meta HA monitoring + alerts | ✅ | V1 | IF-14 | [02 §12O.12](02_STORAGE_ARCHITECTURE.md) |
| IF-14g | Cross-region DR (active-passive + automated DNS failover) | 📦 | V3+ | IF-14 | [02 §12O.9](02_STORAGE_ARCHITECTURE.md) (C3-D5) |
| IF-14h | 2nd sync replica for multi-AZ tolerance | 📦 | V3+ | IF-14 | [02 §12O.3](02_STORAGE_ARCHITECTURE.md) |
| IF-14i | Separate audit DB cluster | 📦 | V3+ | IF-14 | [02 §12O.10](02_STORAGE_ARCHITECTURE.md) (C3-D4 evaluate) |
| IF-14j | Per-shard HA for reality DBs | 📦 | V3+ | IF-3 | [02 §12O.11](02_STORAGE_ARCHITECTURE.md) (C3-D6) |
| IF-15 | L3 override reverse index (C4 resolution) | ✅ | V1 | IF-4, IF-4a | [02 §12P](02_STORAGE_ARCHITECTURE.md) (C4-D1..D4) |
| IF-15a | Event-handler side-effect maintenance | ✅ | V1 | IF-15, IF-5c | [02 §12P.3](02_STORAGE_ARCHITECTURE.md) |
| IF-15b | O(1) preview + force-propagate targeting queries | ✅ | V1 | IF-15 | [02 §12P.4](02_STORAGE_ARCHITECTURE.md) |
| IF-15c | Index rebuild command (recovery) | ✅ | V1 | IF-15 | [02 §12P.6](02_STORAGE_ARCHITECTURE.md) |
| IF-16 | Lifecycle transition CAS discipline (C5 resolution) | ✅ | V1 | IF-4 | [02 §12Q](02_STORAGE_ARCHITECTURE.md) (C5-D1..D6) |
| IF-16a | `AttemptStateTransition()` helper in `contracts/meta/` | ✅ | V1 | IF-16 | [02 §12Q.3](02_STORAGE_ARCHITECTURE.md) |
| IF-16b | `lifecycle_transition_audit` table | ✅ | V1 | IF-16 | [02 §12Q.4](02_STORAGE_ARCHITECTURE.md) |
| IF-16c | Transition graph validation + mutual exclusion | ✅ | V1 | IF-16 | [02 §12Q.6-7](02_STORAGE_ARCHITECTURE.md) |
| IF-16d | Lint rule enforcing helper usage | ✅ | V1 | IF-16 | [02 §12Q.8](02_STORAGE_ARCHITECTURE.md) |
| IF-17 | Adversarial review follow-ups (H/M/P consolidated) | ✅ | V1 | various | [02 §12R](02_STORAGE_ARCHITECTURE.md) |
| IF-17a | Session size caps + queue UX (H3 revised — NPC single-session PERMANENT) | ✅ | V1 | IF-16, NPC-1 | [02 §12R.1](02_STORAGE_ARCHITECTURE.md) (H3-NEW-D1..D5) |
| IF-17b | NPC availability schedule (schema reserved, V2+ feature) | 📦 | V2+ | IF-17a | [02 §12R.1.3](02_STORAGE_ARCHITECTURE.md) (H3-NEW-D6) |
| IF-17c | Reality `seeding` state + bootstrap worker | ✅ | V1 | IF-16a, migration-orchestrator | [02 §12R.2](02_STORAGE_ARCHITECTURE.md) (H5-D1..D3) |
| IF-17d | Bootstrap locale translation integration | ✅ | V1 | IF-17c, translation-service | [02 §12R.2.3](02_STORAGE_ARCHITECTURE.md) (M-REV-5-D1) |
| IF-17e | Upcaster for deprecated event types | ✅ | V1 | IF-7 | [02 §12C.5 updated, §12R.3](02_STORAGE_ARCHITECTURE.md) (H4-D1) |
| IF-17f | Adversarial-review observability suite | ✅ | V1 | — | [02 §12R.4](02_STORAGE_ARCHITECTURE.md) (H1/H2/H6/M-REV-6) |
| IF-17g | HNSW pre-warm on reality thaw | ✅ | V1 | IF-18 | [02 §12R.5](02_STORAGE_ARCHITECTURE.md) (M-REV-3-D1) |
| IF-17h | Projection rebuild determinism rule | ✅ | V1 | IF-9 | [02 §12R.7](02_STORAGE_ARCHITECTURE.md) (P4-D1) |
| IF-17i | Admin command keyword metadata + search | ✅ | V1 | IF-20 | [02 §12R.9](02_STORAGE_ARCHITECTURE.md) (P2-D1) |
| IF-18 | Reality creation rate limit (S1) | ✅ | V1 | IF-4 | [02 §12S.1](02_STORAGE_ARCHITECTURE.md) (S1-D1) |
| IF-19 | Session-scoped memory model (replaces §12H per-pair) | ✅ | V1 | IF-1, NPC-1 | [02 §12S.2](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D1..D5) |
| IF-19a | Event visibility + whisper schema (5 values) | ✅ | V1 | IF-1 | [02 §12S.2.1](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D2) |
| IF-19b | session_participants capability table | ✅ | V1 | IF-5a | [02 §12S.2.2](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D3) |
| IF-19c | npc_session_memory aggregate (replaces npc_pc_memory) | ✅ | V1 | IF-19 | [02 §12S.2.3](02_STORAGE_ARCHITECTURE.md) |
| IF-19d | npc_pc_relationship derived projection | ✅ | V1 | IF-19 | [02 §12S.2.4](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D5) |
| IF-19e | Prompt-assembly canonical query (capability-based) | ✅ | V1 | IF-19 | [02 §12S.2.5](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D4) |
| IF-20 | Event cascade_policy (S3) | ✅ | V1 | IF-1, IF-2 | [02 §12S.3.1](02_STORAGE_ARCHITECTURE.md) (S3-NEW-D1..D3) |
| IF-21 | Privacy level full tier system (S3 Option A) | ✅ | V1 | IF-1 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) (S3-NEW-D6..D8) |
| IF-21a | Per-tier retention (sensitive 30d, confidential 7d) | ✅ | V1+30d | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21b | Force-propagate rejection on non-normal privacy | ✅ | V1 | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21c | Cascade auto-constrain on non-normal privacy | ✅ | V1 | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21d | Whisper tiered UX (4 command variants) | ✅ | V1 | IF-21 | [02 §12S.3.4](02_STORAGE_ARCHITECTURE.md) |
| IF-21e | Fork UX warning with inheritance counts | ✅ | V1 | IF-20, IF-21 | [02 §12S.3.5](02_STORAGE_ARCHITECTURE.md) |
| IF-21f | Per-event encryption (MinIO SSE-C for confidential) | 📦 | V2+ | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21g | Admin access tier gating (was V1+30d, now V1) | ✅ | V1 | IF-21, IF-23 | [02 §12S.5, §12U.7](02_STORAGE_ARCHITECTURE.md); unblocked by S5 lock 2026-04-24. Implemented via IF-23g SQL filter. |
| IF-22 | Meta integrity & access control (S4) | ✅ | V1 | IF-4 | [02 §12T](02_STORAGE_ARCHITECTURE.md) (S4-D1..D8) |
| IF-22a | `MetaWrite()` canonical helper (generalizes §12Q) | ✅ | V1 | IF-16a | [02 §12T.2](02_STORAGE_ARCHITECTURE.md) (S4-D1) |
| IF-22b | `meta_write_audit` append-only table | ✅ | V1 | IF-22a | [02 §12T.5](02_STORAGE_ARCHITECTURE.md) (S4-D2) |
| IF-22c | CHECK constraints on meta tables | ✅ | V1 | IF-4 | [02 §12T.3](02_STORAGE_ARCHITECTURE.md) (S4-D3) |
| IF-22d | Append-only audit (REVOKE + retention role) | ✅ | V1 | IF-22 | [02 §12T.4](02_STORAGE_ARCHITECTURE.md) (S4-D4) |
| IF-22e | `meta_read_audit` for sensitive queries | ✅ | V1+30d | IF-22 | [02 §12T.6](02_STORAGE_ARCHITECTURE.md) (S4-D5) |
| IF-22f | Per-service Postgres roles (least privilege) | ✅ | V1 | IF-22 | [02 §12T.8](02_STORAGE_ARCHITECTURE.md) (S4-D6) |
| IF-22g | Meta anomaly detection + PAGE alerts | ✅ | V1+60d | IF-22 | [02 §12T.7](02_STORAGE_ARCHITECTURE.md) (S4-D7) |
| IF-22h | WORM cold-archive for audit tables | 📦 | V2+ | IF-22d, IF-10 | [02 §12T.4](02_STORAGE_ARCHITECTURE.md) (S4-D8) |
| IF-22i | Hash-chain tamper detection on audit | 📦 | V2+ | IF-22d | [02 §12T.4](02_STORAGE_ARCHITECTURE.md) (S4-D8) |
| IF-23 | Admin command impact classification (S5) | ✅ | V1 | IF-20 | [02 §12U](02_STORAGE_ARCHITECTURE.md) (S5-D1..D8) |
| IF-23a | Three-tier ImpactClass (destructive/griefing/informational) | ✅ | V1 | IF-23 | [02 §12U.2](02_STORAGE_ARCHITECTURE.md) (S5-D1) |
| IF-23b | Tier-specific authorization (dual-actor / reason / notification) | ✅ | V1 | IF-23 | [02 §12U.2](02_STORAGE_ARCHITECTURE.md) (S5-D2) |
| IF-23c | ImpactClass metadata + CI lint enforcement | ✅ | V1 | IF-20 | [02 §12U.3](02_STORAGE_ARCHITECTURE.md) (S5-D3) |
| IF-23d | admin_action_affects_user notification table | ✅ | V1 | IF-23 | [02 §12U.4-5](02_STORAGE_ARCHITECTURE.md) (S5-D4) |
| IF-23e | Griefing-tier periodic review dashboard | ✅ | V1+30d | IF-23 | [02 §12U.6](02_STORAGE_ARCHITECTURE.md) (S5-D5) |
| IF-23f | User admin-activity page (`/me/admin-activity`) | ✅ | V1+30d | IF-23d | [02 §12U.5](02_STORAGE_ARCHITECTURE.md) |
| IF-23g | Privacy-level access SQL filter (S3 V1+30d → V1) | ✅ | V1 | IF-21, IF-23 | [02 §12U.7](02_STORAGE_ARCHITECTURE.md) (S5-D6) |
| IF-23h | ML classification-drift + grief-pattern detection | 📦 | V2+ | IF-23 | [02 §12U.10](02_STORAGE_ARCHITECTURE.md) (S5-D8) |
| IF-24 | LLM cost controls (S6) | ✅ | V1 | IF-15 | [02 §12V](02_STORAGE_ARCHITECTURE.md) (S6-D1..D8) |
| IF-24a | Per-user turn rate limit (Redis token bucket, tier-aware) | ✅ | V1 | IF-24 | [02 §12V.2](02_STORAGE_ARCHITECTURE.md) (S6-D1) |
| IF-24b | Per-session cost cap with warn + hard cap | ✅ | V1 | IF-24 | [02 §12V.3](02_STORAGE_ARCHITECTURE.md) (S6-D2) |
| IF-24c | Per-user daily cost budget | ✅ | V1+30d | IF-24 | [02 §12V.4](02_STORAGE_ARCHITECTURE.md) (S6-D3) |
| IF-24d | Real-time cost observability + alerts | ✅ | V1 | IF-24 | [02 §12V.5](02_STORAGE_ARCHITECTURE.md) (S6-D4) |
| IF-24e | Circuit breaker (user + platform levels) | ✅ | V1+30d | IF-24 | [02 §12V.6](02_STORAGE_ARCHITECTURE.md) (S6-D5) |
| IF-24f | `user_cost_ledger` table (per-LLM-call logging) | ✅ | V1 | IF-24 | [02 §12V.7](02_STORAGE_ARCHITECTURE.md) (S6-D6) |
| IF-24g | Model selection tier gating | ✅ | V1 | IF-24 | [02 §12V.8](02_STORAGE_ARCHITECTURE.md) (S6-D7) |
| IF-24h | ML cost anomaly + predictive modeling + tier suggestions | 📦 | V2+ | IF-24 | [02 §12V.10](02_STORAGE_ARCHITECTURE.md) (S6-D8) |
| IF-25 | Queue abuse prevention (S7) | ✅ | V1 | IF-17a | [02 §12W](02_STORAGE_ARCHITECTURE.md) (S7-D1..D7) |
| IF-25a | Per-user queue depth cap (5 simultaneous) | ✅ | V1 | IF-25 | [02 §12W.2](02_STORAGE_ARCHITECTURE.md) (S7-D1) |
| IF-25b | Two-stage queue expiration (10-min + 24h) | ✅ | V1 | IF-25 | [02 §12W.3](02_STORAGE_ARCHITECTURE.md) (S7-D2) |
| IF-25c | `user_queue_metrics` + queue state transitions | ✅ | V1 | IF-25 | [02 §12W.4](02_STORAGE_ARCHITECTURE.md) (S7-D3) |
| IF-25d | Queue priority decay (acceptance-rate-based) | ✅ | V1+30d | IF-25c | [02 §12W.5](02_STORAGE_ARCHITECTURE.md) (S7-D4) |
| IF-25e | Abandonment cool-down (10/24h → 1h ban) | ✅ | V1 | IF-25c | [02 §12W.6](02_STORAGE_ARCHITECTURE.md) (S7-D5) |
| IF-25f | Reality-level queue override schema (DF4 activates) | 📦 | V1 schema / V2+ enforcement | IF-25 | [02 §12W.7](02_STORAGE_ARCHITECTURE.md) (S7-D6) |
| IF-25g | ML abuse pattern + reputation system | 📦 | V2+ | IF-25 | [02 §12W.8](02_STORAGE_ARCHITECTURE.md) |
| IF-26 | Audit log PII + retention (S8) | ✅ | V1 | IF-1, IF-22 | [02 §12X](02_STORAGE_ARCHITECTURE.md) (S8-D1..D8) |
| IF-26a | `pii_registry` + per-user KEK crypto-shred erasure | ✅ | V1 | IF-26 | [02 §12X.2](02_STORAGE_ARCHITECTURE.md) (S8-D1) |
| IF-26b | PII classification migration tags + CI lint | ✅ | V1 | IF-26 | [02 §12X.3](02_STORAGE_ARCHITECTURE.md) (S8-D2) |
| IF-26c | Unified retention tier matrix (supersedes scattered rules) | ✅ | V1 | IF-26 | [02 §12X.4](02_STORAGE_ARCHITECTURE.md) (S8-D3) |
| IF-26d | Free-text PII scrubber (admin reason, transcripts, notes) | ✅ | V1 | IF-26 | [02 §12X.5](02_STORAGE_ARCHITECTURE.md) (S8-D4) |
| IF-26e | `admin/user-erasure` Tier 1 destructive runbook (30d SLA) | ✅ | V1 | IF-26a, IF-23 | [02 §12X.6](02_STORAGE_ARCHITECTURE.md) (S8-D5) |
| IF-26f | Audit hash chain + daily Merkle root (V1+30d) | ✅ | V1+30d | IF-26 | [02 §12X.7](02_STORAGE_ARCHITECTURE.md) (S8-D6) |
| IF-26g | Structured logging library + ingest scrubber (30d retention) | ✅ | V1 | — | [02 §12X.8](02_STORAGE_ARCHITECTURE.md) (S8-D7) |
| IF-26h | `user_consent_ledger` + revocation event fan-out | ✅ | V1 | IF-26 | [02 §12X.9](02_STORAGE_ARCHITECTURE.md) (S8-D8) |
| IF-29 | Prompt assembly governance (S9) | ✅ | V1 | IF-15, IF-14 | [02 §12Y](02_STORAGE_ARCHITECTURE.md) (S9-D1..D10) |
| IF-29a | Centralized `contracts/prompt/` library + CI lint on provider SDK bypass | ✅ | V1 | IF-29 | [02 §12Y.2](02_STORAGE_ARCHITECTURE.md) (S9-D1) |
| IF-29b | Versioned prompt template registry (schema-as-code) | ✅ | V1 | IF-29 | [02 §12Y.3](02_STORAGE_ARCHITECTURE.md) (S9-D2) |
| IF-29c | Strict 8-section prompt structure + `[INPUT]` sandboxing | ✅ | V1 | IF-29 | [02 §12Y.4](02_STORAGE_ARCHITECTURE.md) (S9-D3) |
| IF-29d | Capability + privacy filter pre-assembly gate (S2/S3/S8 enforcement) | ✅ | V1 | IF-29 | [02 §12Y.5](02_STORAGE_ARCHITECTURE.md) (S9-D4) |
| IF-29e | Multi-layer injection defense (delimiter + instruction + scanner + canary + post-output) | ✅ | V1 | IF-29 | [02 §12Y.6](02_STORAGE_ARCHITECTURE.md) (S9-D5) |
| IF-29f | Per-intent token budget hard caps | ✅ | V1 | IF-29 | [02 §12Y.7](02_STORAGE_ARCHITECTURE.md) (S9-D6) |
| IF-29g | PII redactor + per-provider policy (trains_on_inputs / retention / trusted / tier) | ✅ | V1 | IF-29, IF-14 | [02 §12Y.8](02_STORAGE_ARCHITECTURE.md) (S9-D7) |
| IF-29h | `prompt_audit` deterministic replay (hash + context, no body) | ✅ | V1 | IF-29 | [02 §12Y.9](02_STORAGE_ARCHITECTURE.md) (S9-D8) |
| IF-29i | Regression fixture harness (mock V1 / nightly real-model V1+30d) | ✅ | V1 | IF-29b | [02 §12Y.10](02_STORAGE_ARCHITECTURE.md) (S9-D9) |
| IF-29j | 4-layer canon markup in prompt templates (L1/L2/L3/L4 + SEVERED) | ✅ | V1 | IF-29, WA-4 | [02 §12Y.11](02_STORAGE_ARCHITECTURE.md) (S9-D10) |
| IF-30 | Severance-vs-deletion taxonomy (S10) | ✅ | V1 | IF-1, IF-3 | [02 §12Z](02_STORAGE_ARCHITECTURE.md) (S10-D1..D8) |
| IF-30a | 5-state `GoneState` enum (active/severed/archived/dropped/user_erased) | ✅ | V1 | IF-30 | [02 §12Z.2](02_STORAGE_ARCHITECTURE.md) (S10-D1) |
| IF-30b | `GetEntityStatus()` unified query API + 60s cache | ✅ | V1 | IF-30a | [02 §12Z.3](02_STORAGE_ARCHITECTURE.md) (S10-D2) |
| IF-30c | Prompt marker enum (5 markers) + §12Y scanner whitelist | ✅ | V1 | IF-30, IF-29e | [02 §12Z.4](02_STORAGE_ARCHITECTURE.md) (S10-D3) |
| IF-30d | `admin/entity-provenance` cross-audit timeline CLI | ✅ | V1 | IF-30b, IF-22 | [02 §12Z.5](02_STORAGE_ARCHITECTURE.md) (S10-D4) |
| IF-30d-ui | Entity-provenance timeline web viewer | ✅ | V1+30d | IF-30d | [02 §12Z.5](02_STORAGE_ARCHITECTURE.md) (S10-D4) (DF9/DF11 subsurface) |
| IF-30e | State precedence rule + compound states | ✅ | V1 | IF-30a | [02 §12Z.6](02_STORAGE_ARCHITECTURE.md) (S10-D5) |
| IF-30f | Per-state recovery gate matrix (no universal undelete) | ✅ | V1 | IF-30b | [02 §12Z.7](02_STORAGE_ARCHITECTURE.md) (S10-D6) |
| IF-30f-relink | `admin/relink-ancestor` severance reconnection | 📦 | V2+ | IF-30f, DF6 | [02 §12Z.7](02_STORAGE_ARCHITECTURE.md) (S10-D6) |
| IF-30g | Per-state notification templates (auto-routed by `GoneState`) | ✅ | V1 | IF-30a | [02 §12Z.8](02_STORAGE_ARCHITECTURE.md) (S10-D7) |
| IF-30h | Compliance report section separation (GDPR Art. 30 isolation) | ✅ | V1 | IF-30 | [02 §12Z.9](02_STORAGE_ARCHITECTURE.md) (S10-D8) |
| IF-31 | Service-to-service authentication (S11) | ✅ | V1 | — | [02 §12AA](02_STORAGE_ARCHITECTURE.md) (S11-D1..D10) |
| IF-31a | SPIFFE-like per-service SVID + workload attestation | ✅ | V1 | IF-31 | [02 §12AA.2](02_STORAGE_ARCHITECTURE.md) (S11-D1) |
| IF-31b | Full mTLS service-to-service (Envoy sidecar) | ✅ | V1+30d | IF-31a | [02 §12AA.3](02_STORAGE_ARCHITECTURE.md) (S11-D2) |
| IF-31c | Service ACL matrix + CI lint | ✅ | V1 | IF-31 | [02 §12AA.4](02_STORAGE_ARCHITECTURE.md) (S11-D3) |
| IF-31d | Explicit principal-mode per RPC + confused-deputy defense | ✅ | V1 | IF-31 | [02 §12AA.5](02_STORAGE_ARCHITECTURE.md) (S11-D4) |
| IF-31e | Admin JWT distinct claim schema (role + session + tier + approver + 15min TTL) | ✅ | V1 | IF-31, IF-24 (S5) | [02 §12AA.6](02_STORAGE_ARCHITECTURE.md) (S11-D5) |
| IF-31f | Vault-based secret management + SVID-bound paths | ✅ | V1 | IF-31a | [02 §12AA.7](02_STORAGE_ARCHITECTURE.md) (S11-D6) |
| IF-31g | Event signing in outbox (Ed25519 + freshness) | ✅ | V1+30d | IF-31a, IF-10 | [02 §12AA.8](02_STORAGE_ARCHITECTURE.md) (S11-D7) |
| IF-31h | Private subnet + per-service egress allowlist + VPC flow monitoring | ✅ | V1 | IF-31 | [02 §12AA.9](02_STORAGE_ARCHITECTURE.md) (S11-D8) |
| IF-31i | Two-tier RPC audit (structured logs 90d + `service_to_service_audit` 5y) | ✅ | V1 | IF-31 | [02 §12AA.10](02_STORAGE_ARCHITECTURE.md) (S11-D9) |
| IF-31j | Dev/staging/prod parity + break-glass emergency access | ✅ | V1 | IF-31, IF-20 | [02 §12AA.11](02_STORAGE_ARCHITECTURE.md) (S11-D10) |
| IF-32 | WebSocket token security (S12) | ✅ | V1 | IF-10 (publisher), IF-31 | [02 §12AB](02_STORAGE_ARCHITECTURE.md) (S12-D1..D10) |
| IF-32a | WS ticket handshake (60s one-shot, subprotocol header, not URL) | ✅ | V1 | IF-32 | [02 §12AB.2](02_STORAGE_ARCHITECTURE.md) (S12-D1) |
| IF-32b | Per-connection WS session + 15-min refresh | ✅ | V1 | IF-32a | [02 §12AB.3](02_STORAGE_ARCHITECTURE.md) (S12-D2) |
| IF-32c | Per-message S2/S3 authorization + 30s cache | ✅ | V1 | IF-32, IF-S2-cap | [02 §12AB.4](02_STORAGE_ARCHITECTURE.md) (S12-D3) |
| IF-32d | Origin allowlist + ticket origin binding | ✅ | V1 | IF-32 | [02 §12AB.5](02_STORAGE_ARCHITECTURE.md) (S12-D4) |
| IF-32e | Per-connection + per-user WS rate limits | ✅ | V1 | IF-32, IF-24 (S6) | [02 §12AB.6](02_STORAGE_ARCHITECTURE.md) (S12-D5) |
| IF-32f | Client fingerprint binding + replay defense (seq + nonce) | ✅ | V1+30d | IF-32a | [02 §12AB.7](02_STORAGE_ARCHITECTURE.md) (S12-D6) |
| IF-32g | Versioned WS message schema (`contracts/ws/v1.yaml`) | ✅ | V1 | IF-32 | [02 §12AB.8](02_STORAGE_ARCHITECTURE.md) (S12-D7) |
| IF-32h | Lifecycle audit + enumerated close codes (1000, 4001–4010) | ✅ | V1 | IF-32, IF-22 | [02 §12AB.9](02_STORAGE_ARCHITECTURE.md) (S12-D8) |
| IF-32i | Forced disconnect via signed Redis control channel (<1s SLA) | ✅ | V1 | IF-32, IF-31g | [02 §12AB.10](02_STORAGE_ARCHITECTURE.md) (S12-D9) |
| IF-32j | WS observability + DF9/DF11 dashboards | ✅ | V1 | IF-32 | [02 §12AB.11](02_STORAGE_ARCHITECTURE.md) (S12-D10) |
| IF-32-split | Dedicated `ws-gateway` service split | 📦 | V1+30d | IF-32 | [02 §12AB.12](02_STORAGE_ARCHITECTURE.md) (S12-D10 trigger at >10K active conn/instance) |
| IF-33 | DF3 canonization security invariants (S13 pre-spec) | ✅ | V1 | — | [02 §12AC](02_STORAGE_ARCHITECTURE.md) (S13-D1..D10) |
| IF-33a | Author authority + `book_authorship` table + MetaWrite enforcement | ✅ | V1 | IF-33, IF-3 | [02 §12AC.2](02_STORAGE_ARCHITECTURE.md) (S13-D1) |
| IF-33b | Canonize/decanonize as S5 Tier 1 Destructive (symmetric) | ✅ | V1 | IF-33, IF-23 | [02 §12AC.3](02_STORAGE_ARCHITECTURE.md) (S13-D2) |
| IF-33c | Pre-canon validation pipeline (injection + PII + privacy + length + dup + lock-level) | ✅ | V1 | IF-33, IF-26d, IF-29e | [02 §12AC.4](02_STORAGE_ARCHITECTURE.md) (S13-D3) |
| IF-33d | `canon_entries` immutable provenance + content_hash | ✅ | V1 | IF-33 | [02 §12AC.5](02_STORAGE_ARCHITECTURE.md) (S13-D4) |
| IF-33e | `canonization_audit` (5y) + per-author/book/burst rate limits | ✅ | V1 | IF-33 | [02 §12AC.6](02_STORAGE_ARCHITECTURE.md) (S13-D5) |
| IF-33f | Post-erasure attribution preservation (S8 interaction) | ✅ | V1 | IF-33, IF-26 | [02 §12AC.7](02_STORAGE_ARCHITECTURE.md) (S13-D6) |
| IF-33g | Hot-propagation rate controls + observability | ✅ | V1+30d | IF-33, C4 (§12P) | [02 §12AC.8](02_STORAGE_ARCHITECTURE.md) (S13-D7) |
| IF-33h | Decanonization protocol + compensating events | ✅ | V1 | IF-33 | [02 §12AC.9](02_STORAGE_ARCHITECTURE.md) (S13-D8) |
| IF-33i | Canon injection defense: marker wrapping + canon-echo canary + quarterly retrospective scan | ✅ | V1+30d | IF-33, IF-29e | [02 §12AC.10](02_STORAGE_ARCHITECTURE.md) (S13-D9) |
| IF-33j | Cross-reality impact disclosure UX + 7d review SLA + mass-canonization detection | ✅ | V1+30d | IF-33 | [02 §12AC.11](02_STORAGE_ARCHITECTURE.md) (S13-D10) |
| IF-33-df3 | DF3 Canonization Author Review Flow (full feature) | 📦 | V2+ | IF-33 + DF3 | [DF3 entry](OPEN_DECISIONS.md); S13 invariants locked, full design pending |
| IF-34 | SLOs + error budget policy (SR1) | ✅ | V1 | — | [02 §12AD](02_STORAGE_ARCHITECTURE.md) (SR1-D1..D8) |
| IF-34a | User-journey SLI metrics (7 core SLIs) | ✅ | V1 | IF-34 | [02 §12AD.2](02_STORAGE_ARCHITECTURE.md) (SR1-D1) |
| IF-34b | Tiered SLO targets (free/paid/premium) | ✅ | V1 | IF-34a | [02 §12AD.3](02_STORAGE_ARCHITECTURE.md) (SR1-D2) |
| IF-34c | Error budget policy + burn-rate CI gating | ✅ | V1+30d | IF-34b | [02 §12AD.4](02_STORAGE_ARCHITECTURE.md) (SR1-D3) |
| IF-34d | Multi-tenant isolation SLO (noisy-neighbor + meta 99.99%) | ✅ | V1 | IF-34 | [02 §12AD.5](02_STORAGE_ARCHITECTURE.md) (SR1-D4) |
| IF-34e | Reliability review cadence (daily/weekly/monthly/quarterly) | ✅ | V1 | IF-34 | [02 §12AD.6](02_STORAGE_ARCHITECTURE.md) (SR1-D5) |
| IF-34f | Alert-to-SLO derivation + CI lint | ✅ | V1 | IF-34a | [02 §12AD.7](02_STORAGE_ARCHITECTURE.md) (SR1-D6) |
| IF-34g | Internal status page | ✅ | V1+30d | IF-34 | [02 §12AD.8](02_STORAGE_ARCHITECTURE.md) (SR1-D7) |
| IF-34g-public | Public status page + external SLA | 📦 | V2+ | IF-34g | [02 §12AD.8](02_STORAGE_ARCHITECTURE.md) (SR1-D7 post-monetization) |
| IF-34h | SLO observability cost controls (cardinality + retention tiers) | ✅ | V1 | IF-34 | [02 §12AD.9](02_STORAGE_ARCHITECTURE.md) (SR1-D8) |
| IF-35 | Incident classification + on-call rotation (SR2) | ✅ | V1 | IF-34 | [02 §12AE](02_STORAGE_ARCHITECTURE.md) (SR2-D1..D10) |
| IF-35a | Severity matrix SEV0–SEV3 + auto-escalation rules | ✅ | V1 | IF-35 | [02 §12AE.2](02_STORAGE_ARCHITECTURE.md) (SR2-D1) |
| IF-35b | On-call rotation structure (SRE/Security/Data specialty) | ✅ | V1 | IF-35 | [02 §12AE.3](02_STORAGE_ARCHITECTURE.md) (SR2-D2) |
| IF-35c | Alert routing table + fallback chain | ✅ | V1 | IF-35a, IF-34f | [02 §12AE.4](02_STORAGE_ARCHITECTURE.md) (SR2-D3) |
| IF-35d | Incident lifecycle 6-state machine | ✅ | V1 | IF-35 | [02 §12AE.5](02_STORAGE_ARCHITECTURE.md) (SR2-D4) |
| IF-35e | Incident Commander role + handoff protocol | ✅ | V1 | IF-35d | [02 §12AE.6](02_STORAGE_ARCHITECTURE.md) (SR2-D5) |
| IF-35f | Communication protocol + templates (war room/status/updates) | ✅ | V1 | IF-35, IF-34g | [02 §12AE.7](02_STORAGE_ARCHITECTURE.md) (SR2-D6) |
| IF-35g | `incidents` tracker table (5y, meta DB) | ✅ | V1 | IF-35 | [02 §12AE.8](02_STORAGE_ARCHITECTURE.md) (SR2-D7) |
| IF-35h | Review cadences + postmortem triggers | ✅ | V1 | IF-35g | [02 §12AE.9](02_STORAGE_ARCHITECTURE.md) (SR2-D8) |
| IF-35i | Privacy + security fast-paths (GDPR 72h / active attack / canon injection / audit tamper) | ✅ | V1 | IF-35a, IF-26, IF-33 | [02 §12AE.10](02_STORAGE_ARCHITECTURE.md) (SR2-D9) |
| IF-35j | Incident infrastructure independence (external PagerDuty + status page + runbook mirror) | ✅ | V1 | IF-35 | [02 §12AE.11](02_STORAGE_ARCHITECTURE.md) (SR2-D10) |
| IF-36 | Runbook library (SR3) | ✅ | V1 | IF-34f, IF-35 | [02 §12AF](02_STORAGE_ARCHITECTURE.md) (SR3-D1..D10) |
| IF-36a | Canonical runbook schema (YAML frontmatter + Markdown template) | ✅ | V1 | IF-36 | [02 §12AF.2](02_STORAGE_ARCHITECTURE.md) (SR3-D1) |
| IF-36b | Directory structure + auto-generated INDEX.md | ✅ | V1 | IF-36a | [02 §12AF.3](02_STORAGE_ARCHITECTURE.md) (SR3-D2) |
| IF-36c | 27-runbook V1 gate (required before production cutover) | ✅ | V1 | IF-36a | [02 §12AF.4](02_STORAGE_ARCHITECTURE.md) (SR3-D3) |
| IF-36d | 90-day verification cadence + overdue tracking | ✅ | V1 | IF-36 | [02 §12AF.5](02_STORAGE_ARCHITECTURE.md) (SR3-D4) |
| IF-36e | Three drift-detection CI lints (alert-sync + service-annotate + dead-ref) | ✅ | V1 | IF-36 | [02 §12AF.6](02_STORAGE_ARCHITECTURE.md) (SR3-D5) |
| IF-36f | Dry-run-first rule + CI enforcement | ✅ | V1 | IF-36a | [02 §12AF.7](02_STORAGE_ARCHITECTURE.md) (SR3-D6) |
| IF-36g | Generic triage runbooks (i-don-t-know + new-on-call + escalation) | ✅ | V1 | IF-36c | [02 §12AF.8](02_STORAGE_ARCHITECTURE.md) (SR3-D7) |
| IF-36h | External access inventory + break-glass fallback docs | ✅ | V1 | IF-36 | [02 §12AF.9](02_STORAGE_ARCHITECTURE.md) (SR3-D8) |
| IF-36i | Post-incident runbook update flow (action items + born_from_incident_id) | ✅ | V1 | IF-36, IF-35g | [02 §12AF.10](02_STORAGE_ARCHITECTURE.md) (SR3-D9) |
| IF-36j | Runbook accessibility (git + Notion mirror + on-call startup ritual) | ✅ | V1 | IF-36 | [02 §12AF.11](02_STORAGE_ARCHITECTURE.md) (SR3-D10) |
| IF-37 | Postmortem process (SR4) | ✅ | V1 | IF-35, IF-36 | [02 §12AG](02_STORAGE_ARCHITECTURE.md) (SR4-D1..D10) |
| IF-37a | Canonical postmortem template + CI structure lint | ✅ | V1 | IF-37 | [02 §12AG.2](02_STORAGE_ARCHITECTURE.md) (SR4-D1) |
| IF-37b | Blameless mechanisms (no-name rule + review gate + quarterly audit) | ✅ | V1 | IF-37a | [02 §12AG.3](02_STORAGE_ARCHITECTURE.md) (SR4-D2) |
| IF-37c | Authorship-by-severity + V1 solo-dev pattern | ✅ | V1 | IF-37, IF-35e | [02 §12AG.4](02_STORAGE_ARCHITECTURE.md) (SR4-D3) |
| IF-37d | 5-state review workflow + legal review trigger | ✅ | V1 | IF-37c | [02 §12AG.5](02_STORAGE_ARCHITECTURE.md) (SR4-D4) |
| IF-37e | Extended action item schema + lifecycle scanning | ✅ | V1 | IF-37, IF-35g | [02 §12AG.6](02_STORAGE_ARCHITECTURE.md) (SR4-D5) |
| IF-37f | Time-boxed deadlines + slip escalation + publication iteration | ✅ | V1 | IF-37d | [02 §12AG.7](02_STORAGE_ARCHITECTURE.md) (SR4-D6) |
| IF-37g | Root cause classification enum + quarterly pattern detection + auto-preventive-incident | ✅ | V1 | IF-37 | [02 §12AG.8](02_STORAGE_ARCHITECTURE.md) (SR4-D7) |
| IF-37h | Internal Full + Security-Restricted variants (V1) | ✅ | V1 | IF-37 | [02 §12AG.9](02_STORAGE_ARCHITECTURE.md) (SR4-D8) |
| IF-37h-public | Customer-Facing + Regulator-Facing variants | 📦 | V2+ | IF-37h | [02 §12AG.9](02_STORAGE_ARCHITECTURE.md) (SR4-D8 monetization+GDPR) |
| IF-37i | Sharing rituals (weekly/monthly Postmortem Hour/quarterly) + runbook back-lookup | ✅ | V1 | IF-37 | [02 §12AG.10](02_STORAGE_ARCHITECTURE.md) (SR4-D9) |
| IF-37j | Annual meta-review of postmortem process | ✅ | V1 | IF-37 | [02 §12AG.11](02_STORAGE_ARCHITECTURE.md) (SR4-D10) |
| IF-38 | Deploy safety + rollback (SR5) | ✅ | V1 | IF-34, IF-35 | [02 §12AH](02_STORAGE_ARCHITECTURE.md) (SR5-D1..D10) |
| IF-38a | Deploy class enum + CI classification lint | ✅ | V1 | IF-38 | [02 §12AH.2](02_STORAGE_ARCHITECTURE.md) (SR5-D1) |
| IF-38b | 4 deploy freeze mechanisms + break-glass-deploy override | ✅ | V1 | IF-38a, IF-34c | [02 §12AH.3](02_STORAGE_ARCHITECTURE.md) (SR5-D2) |
| IF-38c | 5-stage canary rollout + auto-abort at 2× baseline burn | ✅ | V1 | IF-38a, IF-3 | [02 §12AH.4](02_STORAGE_ARCHITECTURE.md) (SR5-D3) |
| IF-38d | Feature flags table + planned_removal_date + quarterly debt review | ✅ | V1 | IF-38 | [02 §12AH.5](02_STORAGE_ARCHITECTURE.md) (SR5-D4) |
| IF-38e | 6-phase schema migration protocol + `migration-orchestrator` + cohort rollout | ✅ | V1 | IF-38, IF-1 | [02 §12AH.6](02_STORAGE_ARCHITECTURE.md) (SR5-D5) |
| IF-38f | Config change PR requirements (diff + validation + dry-run + rollback) | ✅ | V1 | IF-38 | [02 §12AH.7](02_STORAGE_ARCHITECTURE.md) (SR5-D6) |
| IF-38f-backtest | Alert config backtest CI hook | ✅ | V1+30d | IF-38f, IF-34f | [02 §12AH.7](02_STORAGE_ARCHITECTURE.md) (SR5-D6) |
| IF-38g | Rollback decision framework + runbook + rollback-first bias | ✅ | V1 | IF-38, IF-36 | [02 §12AH.8](02_STORAGE_ARCHITECTURE.md) (SR5-D7) |
| IF-38h | `deploy_audit` table (5y) + alert/incident correlation | ✅ | V1 | IF-38, IF-35g | [02 §12AH.9](02_STORAGE_ARCHITECTURE.md) (SR5-D8) |
| IF-38i | Async change advisory for major + V1 solo-dev pattern | ✅ | V1 | IF-38a | [02 §12AH.10](02_STORAGE_ARCHITECTURE.md) (SR5-D9) |
| IF-38j | Deploy windows + CI enforcement | ✅ | V1 | IF-38a | [02 §12AH.11](02_STORAGE_ARCHITECTURE.md) (SR5-D10) |
| IF-14 | Provider-registry integration (BYOK credential resolution) | ✅ | INFRA | — | Reuse [98_CHAT_SERVICE_DESIGN §5.4](../98_CHAT_SERVICE_DESIGN.md) |
| IF-15 | LiteLLM multi-provider inference (with streaming) | ✅ | INFRA | IF-14 | Reuse [98_CHAT_SERVICE_DESIGN §6](../98_CHAT_SERVICE_DESIGN.md) |
| IF-16 | Per-reality locale primitive | ✅ | INFRA | IF-3 | [03 §8.3](03_MULTIVERSE_MODEL.md) (MV5 primitive P1) |
| IF-17 | Analytics ETL → ClickHouse (cross-reality aggregates) | 📦 | V3 | IF-1 | [02 §3 diagram](02_STORAGE_ARCHITECTURE.md) — optional |
| IF-18 | pgvector HNSW tuning + footprint monitoring | ✅ | V1 | IF-12 | [02 §12K](02_STORAGE_ARCHITECTURE.md) (R11) |
| IF-19 | Global event ordering — accepted trade-off (no mitigation; timestamp merge sufficient) | ✅ | INFRA | — | [02 §12J](02_STORAGE_ARCHITECTURE.md) (R10 ACCEPTED) |
| IF-20 | Admin command library (canonical, named, reviewed, versioned; no ad-hoc SQL) | ✅ | V1 | — | [02 §12L.1](02_STORAGE_ARCHITECTURE.md) (R13-L1) |
| IF-21 | Compensating-event pattern for admin changes | ✅ | V1 | IF-1 | [02 §12L.2](02_STORAGE_ARCHITECTURE.md) (R13-L2) |
| IF-22 | Admin action audit log (centralized, 2-year retention) | ✅ | V1 | IF-4 | [02 §12L.3](02_STORAGE_ARCHITECTURE.md) (R13-L3) |
| IF-23 | Destructive action confirmation + double-approval for dangerous commands | ✅ | V1 | IF-20 | [02 §12L.4](02_STORAGE_ARCHITECTURE.md) (R13-L4) |
| IF-24 | Admin UI guardrails (no raw DROP/UPDATE buttons, no free-form SQL in prod) | ✅ | V1 | — | [02 §12L.5](02_STORAGE_ARCHITECTURE.md) (R13-L5) |
| IF-27 | Admin rollback via compensating events | ✅ | V2 | IF-21 | [02 §12L.6](02_STORAGE_ARCHITECTURE.md) (R13-L6) |
| IF-28 | Admin Action Policy governance doc | ✅ | INFRA | — | [docs/02_governance/ADMIN_ACTION_POLICY.md](../../02_governance/ADMIN_ACTION_POLICY.md) (R13-governance) |
| IF-39 | Dependency registry (`contracts/dependencies/matrix.yaml`) | ✅ | V1 | — | [02_storage/SR06_dependency_failure.md §12AI.2](../02_storage/SR06_dependency_failure.md) (SR6-D1) |
| IF-39a | Circuit breaker library (`contracts/resilience/`; 3-state) | ✅ | V1 | IF-39 | [02_storage/SR06_dependency_failure.md §12AI.4](../02_storage/SR06_dependency_failure.md) (SR6-D3) |
| IF-39b | Dependency health dashboard (DF11 panel) | ✅ | V1 | IF-39, IF-34 | [02_storage/SR06_dependency_failure.md §12AI.8](../02_storage/SR06_dependency_failure.md) (SR6-D7) |
| IF-39c | Graceful shutdown / drain handler (`contracts/lifecycle/Drain`) | ✅ | V1 | — | [02_storage/SR06_dependency_failure.md §12AI.11](../02_storage/SR06_dependency_failure.md) (SR6-D10) |
| IF-39d | Multi-provider LLM failover (extends `provider_registry`) | ✅ | V1 | IF-14, IF-15 | [02_storage/SR06_dependency_failure.md §12AI.7](../02_storage/SR06_dependency_failure.md) (SR6-D6) |
| IF-39e | Degraded-mode framework (`contracts/lifecycle/modes.go`; 5-mode) | ✅ | V1 | IF-39 | [02_storage/SR06_dependency_failure.md §12AI.6](../02_storage/SR06_dependency_failure.md) (SR6-D5) |
| IF-39f | `dependency_events` audit table (1y retention) | ✅ | V1 | IF-39 | [02_storage/SR06_dependency_failure.md §12AI.9](../02_storage/SR06_dependency_failure.md) (SR6-D8) |
| IF-39g | Chaos drill hooks (**activated by SR7**) | ✅ | V1 | IF-39a, IF-39f, IF-40 | [02_storage/SR07_chaos_drills.md §12AJ.12](../02_storage/SR07_chaos_drills.md) (SR7-governance) — was V1+30d placeholder until SR7 resolution |
| IF-39h | Dependency runbook template (SR3 integration) | ✅ | V1 | IF-36, IF-39 | [02_storage/SR06_dependency_failure.md §12AI.2](../02_storage/SR06_dependency_failure.md) (SR6-D1; matrix `runbook:` field) |
| IF-39i | Bulkhead resource pool manager | ✅ | V1 | IF-39, IF-39a | [02_storage/SR06_dependency_failure.md §12AI.10](../02_storage/SR06_dependency_failure.md) (SR6-D9) |
| IF-39j | Timeout discipline CI lint (`timeout-discipline-lint.sh`) | ✅ | V1 | IF-39 | [02_storage/SR06_dependency_failure.md §12AI.3](../02_storage/SR06_dependency_failure.md) (SR6-D2; enforces invariant I16) |
| IF-40 | Chaos experiment registry (`contracts/chaos/experiments.yaml`) | ✅ | V1 | — | [02_storage/SR07_chaos_drills.md §12AJ.2](../02_storage/SR07_chaos_drills.md) (SR7-D1) |
| IF-40a | `chaos-cli` admin tool (list/describe/run/abort/kill-switch/status) | ✅ | V1 | IF-40, IF-20 | [02_storage/SR07_chaos_drills.md §12AJ.8](../02_storage/SR07_chaos_drills.md) (SR7-D7) |
| IF-40b | `chaos_drills` audit table (3y retention) | ✅ | V1 | IF-40 | [02_storage/SR07_chaos_drills.md §12AJ.9](../02_storage/SR07_chaos_drills.md) (SR7-D8) |
| IF-40c | Chaos harness framework (method adapters: http_blackhole / db_slow_query / pod_kill / network_latency / ...) | ✅ | V1 | IF-40, IF-39a | [02_storage/SR07_chaos_drills.md §12AJ.8](../02_storage/SR07_chaos_drills.md) (SR7-D7) |
| IF-40d | Per-experiment abort-criteria checker (10s SLI polling; auto-abort) | ✅ | V1 | IF-40, IF-34 | [02_storage/SR07_chaos_drills.md §12AJ.7](../02_storage/SR07_chaos_drills.md) (SR7-D6) |
| IF-40e | Global chaos kill-switch (S5 Tier 1) | ✅ | V1 | IF-40a | [02_storage/SR07_chaos_drills.md §12AJ.7](../02_storage/SR07_chaos_drills.md) (SR7-D6, SR7-D7) |
| IF-40f | Dry-run mode for chaos experiments | ✅ | V1 | IF-40c | [02_storage/SR07_chaos_drills.md §12AJ.7](../02_storage/SR07_chaos_drills.md) (SR7-D6) |
| IF-40g | Post-drill review template + automated metric snapshot | ✅ | V1 | IF-40b, IF-34 | [02_storage/SR07_chaos_drills.md §12AJ.10](../02_storage/SR07_chaos_drills.md) (SR7-D9) |
| IF-40h | V1 launch gate CI check (`v1-launch-check.sh`) | ✅ | V1 | IF-40b | [02_storage/SR07_chaos_drills.md §12AJ.11](../02_storage/SR07_chaos_drills.md) (SR7-D10) |
| IF-40i | SR3 runbook `last_verified` method = `chaos_drill` | ✅ | V1 | IF-36, IF-40b | [02_storage/SR07_chaos_drills.md §12AJ.10](../02_storage/SR07_chaos_drills.md) (SR7-D9, extends SR3-D4) |
| IF-40j | Chaos-scheduler cron (V1 via admin-cli; dedicated service V2+) | ✅ | V1 | IF-40a | [02_storage/SR07_chaos_drills.md §12AJ.5](../02_storage/SR07_chaos_drills.md) (SR7-D4) |
| IF-41 | Capacity budget registry (`contracts/capacity/budgets.yaml`) | ✅ | V1 | — | [02_storage/SR08_capacity_scaling.md §12AK.3](../02_storage/SR08_capacity_scaling.md) (SR8-D2) |
| IF-41a | Service class taxonomy + bootstrap declaration | ✅ | V1 | IF-41 | [02_storage/SR08_capacity_scaling.md §12AK.2](../02_storage/SR08_capacity_scaling.md) (SR8-D1) |
| IF-41b | Scaling signal library (`contracts/capacity/signals.go`) | ✅ | V1 | IF-41 | [02_storage/SR08_capacity_scaling.md §12AK.4](../02_storage/SR08_capacity_scaling.md) (SR8-D3) |
| IF-41c | Per-reality capacity ceiling enforcer (in `world-service`) | ✅ | V1 | IF-41 | [02_storage/SR08_capacity_scaling.md §12AK.5](../02_storage/SR08_capacity_scaling.md) (SR8-D4) |
| IF-41d | `shard_utilization` tracking table + shard dashboard | ✅ | V1 | IF-41 | [02_storage/SR08_capacity_scaling.md §12AK.6](../02_storage/SR08_capacity_scaling.md) (SR8-D5) |
| IF-41e | Auto-scaling policy templates (HPA / KEDA / vertical) | ✅ | V1 | IF-41, IF-41b | [02_storage/SR08_capacity_scaling.md §12AK.7](../02_storage/SR08_capacity_scaling.md) (SR8-D6) |
| IF-41f | `scaling_events` audit table (1y retention) | ✅ | V1 | IF-41 | [02_storage/SR08_capacity_scaling.md §12AK.11](../02_storage/SR08_capacity_scaling.md) (SR8-D10) |
| IF-41g | Capacity metrics + alerts + DF11 panel | ✅ | V1 | IF-41, IF-34 | [02_storage/SR08_capacity_scaling.md §12AK.8](../02_storage/SR08_capacity_scaling.md) (SR8-D7) |
| IF-41h | Load-test capacity gate (`capacity-gate-check.sh`) | 📦 | V1+30d | IF-41, G2-D4 | [02_storage/SR08_capacity_scaling.md §12AK.9](../02_storage/SR08_capacity_scaling.md) (SR8-D8; V1+30d automation) |
| IF-41i | Pre-warmed replica pool manager | 📦 | V1+30d | IF-41e | [02_storage/SR08_capacity_scaling.md §12AK.7](../02_storage/SR08_capacity_scaling.md) (SR8-D6; V1+30d) |
| IF-41j | `admin/capacity-override` + `admin/scaling-policy-update` + `admin/drain-shard` | ✅ | V1 | IF-41, IF-20 | [02_storage/SR08_capacity_scaling.md §12AK.10, §12AK.6](../02_storage/SR08_capacity_scaling.md) (SR8-D9, SR8-D5) |
| IF-42 | Alert rule registry (`contracts/alerts/rules.yaml`) | ✅ | V1 | — | [02_storage/SR09_alert_tuning.md §12AL.3](../02_storage/SR09_alert_tuning.md) (SR9-D2) |
| IF-42a | `alert-rule-lint.sh` CI lint (fields / dead-ref / severity-match / replay-validation) | ✅ | V1 | IF-42 | [02_storage/SR09_alert_tuning.md §12AL.3](../02_storage/SR09_alert_tuning.md) (SR9-D2) |
| IF-42b | `alert_outcomes` audit (90d hot + 2y cold aggregate) | ✅ | V1 | IF-42 | [02_storage/SR09_alert_tuning.md §12AL.5](../02_storage/SR09_alert_tuning.md) (SR9-D4) |
| IF-42c | `alert_silences` table + `admin/alert-silence` CLI | ✅ | V1 | IF-42, IF-20 | [02_storage/SR09_alert_tuning.md §12AL.6](../02_storage/SR09_alert_tuning.md) (SR9-D5) |
| IF-42d | Pager-load metrics + rotation-rebalance dashboard (DF11) | ✅ | V1 | IF-42b, IF-34 | [02_storage/SR09_alert_tuning.md §12AL.8](../02_storage/SR09_alert_tuning.md) (SR9-D7) |
| IF-42e | Alert storm detection + batched digest delivery | ✅ | V1 | IF-42, IF-32 | [02_storage/SR09_alert_tuning.md §12AL.10](../02_storage/SR09_alert_tuning.md) (SR9-D9) |
| IF-42f | Weekly alert-review template + generator script | ✅ | V1 | IF-42b | [02_storage/SR09_alert_tuning.md §12AL.9](../02_storage/SR09_alert_tuning.md) (SR9-D8) |
| IF-42g | Threshold tuning workflow (4-stage promotion + auto-downgrade/escalate) | ✅ | V1 | IF-42b | [02_storage/SR09_alert_tuning.md §12AL.4](../02_storage/SR09_alert_tuning.md) (SR9-D3) |
| IF-42h | Alert-to-runbook CI lint trio (sync / dead-ref / coverage-check) | ✅ | V1 | IF-42, IF-36 | [02_storage/SR09_alert_tuning.md §12AL.7](../02_storage/SR09_alert_tuning.md) (SR9-D6; extends SR3-D5) |
| IF-42i | False-positive / false-negative classifier + auto-downgrade trigger | 📦 | V1+30d | IF-42b, IF-42g | [02_storage/SR09_alert_tuning.md §12AL.4](../02_storage/SR09_alert_tuning.md) (SR9-D3; needs 30 days of data) |
| IF-42j | `admin/alert-threshold-update` + `admin/pager-rotation-swap` CLI | ✅ | V1 | IF-42, IF-20 | [02_storage/SR09_alert_tuning.md §12AL.12](../02_storage/SR09_alert_tuning.md) (SR9-governance) |
| IF-43 | Supply chain registry (`contracts/supply_chain/`: dep_allowlist + secret-scan-baseline + cve-policy) | ✅ | V1 | — | [02_storage/SR10_supply_chain.md §12AM.6](../02_storage/SR10_supply_chain.md) (SR10-D5) |
| IF-43a | SBOM generator (syft; CycloneDX 1.5) | ✅ | V1 | IF-43 | [02_storage/SR10_supply_chain.md §12AM.2](../02_storage/SR10_supply_chain.md) (SR10-D1) |
| IF-43b | Dep pinning enforcer (`dep-pinning-lint.sh`) | ✅ | V1 | IF-43 | [02_storage/SR10_supply_chain.md §12AM.3](../02_storage/SR10_supply_chain.md) (SR10-D2; enforces I18 if approved) |
| IF-43c | Container image signing + verification (cosign + K8s admission policy) | ✅ | V1 | IF-43, IF-31 | [02_storage/SR10_supply_chain.md §12AM.4](../02_storage/SR10_supply_chain.md) (SR10-D3) |
| IF-43d | CVE scanner + severity gate (trivy; critical/high blocks) | ✅ | V1 | IF-43, IF-42 | [02_storage/SR10_supply_chain.md §12AM.5](../02_storage/SR10_supply_chain.md) (SR10-D4) |
| IF-43e | 3rd-party vetting workflow (checklist + allowlist CI lint + `admin/dep-vet-approve`) | ✅ | V1 | IF-43 | [02_storage/SR10_supply_chain.md §12AM.6](../02_storage/SR10_supply_chain.md) (SR10-D5) |
| IF-43f | SLSA Level 2 provenance (slsa-github-generator + cosign attest) | ✅ | V1 | IF-43c | [02_storage/SR10_supply_chain.md §12AM.7](../02_storage/SR10_supply_chain.md) (SR10-D6) |
| IF-43g | 3-scan-point secret scanning (gitleaks pre-commit + CI + monthly history cron) | ✅ | V1 | IF-43 | [02_storage/SR10_supply_chain.md §12AM.8](../02_storage/SR10_supply_chain.md) (SR10-D7; extends I12) |
| IF-43h | Supply chain runbook library — 6 runbooks | ✅ | V1 | IF-36, IF-43 | [02_storage/SR10_supply_chain.md §12AM.9](../02_storage/SR10_supply_chain.md) (SR10-D8; SR3 27-gate → 39) |
| IF-43i | Build reproducibility check (V1+30d 10% sample; V2+ blocks merge) | 📦 | V1+30d | IF-43 | [02_storage/SR10_supply_chain.md §12AM.10](../02_storage/SR10_supply_chain.md) (SR10-D9) |
| IF-43j | `supply_chain_events` audit + `admin/cve-override` + `admin/supply-chain-freeze` CLI | ✅ | V1 | IF-43, IF-20 | [02_storage/SR10_supply_chain.md §12AM.10, §12AM.12](../02_storage/SR10_supply_chain.md) (SR10-D9, SR10-governance) |
| IF-44 | Turn state machine library (`contracts/turn/state_machine.go`) | ✅ | V1 | — | [02_storage/SR11_turn_ux_reliability.md §12AN.2](../02_storage/SR11_turn_ux_reliability.md) (SR11-D1) |
| IF-44a | `turn.status.update` WS message + per-state indicator UX | ✅ | V1 | IF-44, IF-32 | [02_storage/SR11_turn_ux_reliability.md §12AN.3](../02_storage/SR11_turn_ux_reliability.md) (SR11-D2) |
| IF-44b | `PresenceState` enum + `session_participants` schema extension + debounced WS propagation | ✅ | V1 | IF-44 | [02_storage/SR11_turn_ux_reliability.md §12AN.4](../02_storage/SR11_turn_ux_reliability.md) (SR11-D3) |
| IF-44c | Disconnect-handling 3-policy matrix + per-session/reality config | ✅ | V1 | IF-44, IF-44b | [02_storage/SR11_turn_ux_reliability.md §12AN.5](../02_storage/SR11_turn_ux_reliability.md) (SR11-D4) |
| IF-44d | Optimistic UX framework + divergence rollback + toast notification | ✅ | V1 | IF-44a | [02_storage/SR11_turn_ux_reliability.md §12AN.6](../02_storage/SR11_turn_ux_reliability.md) (SR11-D5) |
| IF-44e | Degraded-mode UX banner system per SR6-D5 | ✅ | V1 | IF-44a, IF-39e | [02_storage/SR11_turn_ux_reliability.md §12AN.7](../02_storage/SR11_turn_ux_reliability.md) (SR11-D6) |
| IF-44f | FIFO + tier-bump queue + 30%-cap fairness Gini metric | ✅ | V1 | IF-44, IF-34 | [02_storage/SR11_turn_ux_reliability.md §12AN.8](../02_storage/SR11_turn_ux_reliability.md) (SR11-D7) |
| IF-44g | `turn_outcomes` audit table (1y retention; 4 indexes) | ✅ | V1 | IF-44 | [02_storage/SR11_turn_ux_reliability.md §12AN.9](../02_storage/SR11_turn_ux_reliability.md) (SR11-D8) |
| IF-44h | Registered error code library (`contracts/errors/user_errors.yaml`) with i18n + CI lint | ✅ | V1 | IF-44, IF-16 | [02_storage/SR11_turn_ux_reliability.md §12AN.10](../02_storage/SR11_turn_ux_reliability.md) (SR11-D9) |
| IF-44i | V1 12-scenario launch gate (`v1-turn-ux-check.sh`) | ✅ | V1 | IF-44, IF-40b | [02_storage/SR11_turn_ux_reliability.md §12AN.11](../02_storage/SR11_turn_ux_reliability.md) (SR11-D10) |
| IF-44j | `admin/session-unfreeze` + `admin/turn-abandon` + `admin/presence-reset` CLI | ✅ | V1 | IF-44, IF-20 | [02_storage/SR11_turn_ux_reliability.md §12AN.12](../02_storage/SR11_turn_ux_reliability.md) (SR11-governance) |
| IF-45 | Observability inventory registry (`contracts/observability/inventory.yaml`) | ✅ | V1 | — | [02_storage/SR12_observability_cost.md §12AO.2](../02_storage/SR12_observability_cost.md) (SR12-D1) |
| IF-45a | `observability-inventory-lint.sh` CI lint (metric + audit-table declaration enforcement) | ✅ | V1 | IF-45 | [02_storage/SR12_observability_cost.md §12AO.2](../02_storage/SR12_observability_cost.md) (SR12-D1; enforces I19 if approved) |
| IF-45b | Per-service cardinality + log + audit budgets (`budgets.yaml`) | ✅ | V1 | IF-45, IF-41 | [02_storage/SR12_observability_cost.md §12AO.3](../02_storage/SR12_observability_cost.md) (SR12-D2) |
| IF-45c | `observability_budget_breaches` audit table (1y retention) | ✅ | V1 | IF-45 | [02_storage/SR12_observability_cost.md §12AO.3](../02_storage/SR12_observability_cost.md) (SR12-D2) |
| IF-45d | Retention tier audit cron + `user_queue_metrics` 1y formalization | ✅ | V1 | IF-45 | [02_storage/SR12_observability_cost.md §12AO.4](../02_storage/SR12_observability_cost.md) (SR12-D3; S8-D3 Operational tier extension) |
| IF-45e | Log sampling configuration + per-service overrides + `admin/log-sampling-update` | ✅ | V1 | IF-45, IF-20 | [02_storage/SR12_observability_cost.md §12AO.5](../02_storage/SR12_observability_cost.md) (SR12-D4) |
| IF-45f | Audit rollup crons (alert_outcomes weekly agg + prompt_audit cold archive; others V1+30d) | 🟡 | V1 + V1+30d | IF-45 | [02_storage/SR12_observability_cost.md §12AO.6](../02_storage/SR12_observability_cost.md) (SR12-D5) |
| IF-45g | Meta-observability metrics + DF11 panel + 4 alerts | ✅ | V1 | IF-45, IF-34 | [02_storage/SR12_observability_cost.md §12AO.7](../02_storage/SR12_observability_cost.md) (SR12-D6) |
| IF-45h | Cardinality admission control in `pkg/metrics/` (V1 warn-and-drop → V1+30d hard-reject → V2+ pre-commit) | ✅ | V1 | IF-45 | [02_storage/SR12_observability_cost.md §12AO.8](../02_storage/SR12_observability_cost.md) (SR12-D7) |
| IF-45i | Weekly rebaseline cadence template + V1 solo-dev pattern | ✅ | V1 | IF-45 | [02_storage/SR12_observability_cost.md §12AO.10](../02_storage/SR12_observability_cost.md) (SR12-D9) |
| IF-45j | `admin/metric-label-audit` + `admin/retention-override` CLI | ✅ | V1 | IF-45, IF-20 | [02_storage/SR12_observability_cost.md §12AO.12](../02_storage/SR12_observability_cost.md) (SR12-governance) |

