<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: 99_known_risks_and_close.md
byte_range: 464797-476561
sha256: 936b53c9590cedd26712a71ba5d4468b497e4459c66c0185955e5166c707e56c
generated_by: scripts/chunk_doc.py
-->

## 13. Known risks (for separate discussion)

> The user indicated they have ideas for these. Listed here so we have them in one place when we resume.

### R1. Event volume explosion — **MITIGATED**
Full event sourcing multiplies writes vs pure CRUD. Projection updates also go through the DB. Naive daily volume (~2 GB/day/reality × 1000 realities = 1 TB/day) would overwhelm Postgres.

**Resolution:** 6-layer strategy designed in [§12A](#12a-event-volume-management-r1-mitigation) — audit split, event discipline, tiered retention, archive pipeline, snapshot-truncate, lz4 compression. Expected outcome: ~1 GB hot per reality per year in Postgres (50× reduction); cold data in cheap MinIO. Platform-wide: 1 TB hot Postgres total, 50 TB cold MinIO for 1000 active realities. Trade-offs documented in §12A.8.

### R2. Projection rebuild time at scale — **MITIGATED**
Projection rebuild across large instances was a concern. After R1 mitigation + multiverse + snapshots, normal rebuild is fast (<1 min per reality with snapshots); only edge cases need special handling.

**Resolution:** 5-layer strategy in [§12B](#12b-projection-rebuild--integrity-r2-mitigation) — snapshot-anchored rebuild (baseline from §6), per-aggregate parallelism, V1 freeze-rebuild / V2 blue-green for schema migration, integrity checker with drift detection, catastrophic recovery procedure. Admin tooling for orchestration deferred to **DF9 — Rebuild & Integrity Ops**.

Expected behavior: catastrophic rebuild 5–10 min per reality (rare); schema migration 0 downtime with blue-green (V2); drift detection eliminates silent corruption.

### R3. Event schema evolution pain — **MITIGATED**
Event sourcing makes events immutable; schema changes require upcasters maintained forever. Without tooling, this compounds exponentially as event types and versions multiply.

**Resolution:** 6-layer strategy in [§12C](#12c-event-schema-evolution-r3-mitigation) — additive-first discipline, schema-as-code + codegen (Go as source of truth, generated TS + Python types), upcaster chain on read, schema validation on write, breaking-change-via-new-event-type escape hatch, archive upgrade deferred V2. Tooling + dev UX deferred to **DF10 — Event Schema Tooling**.

Expected maintenance cost: ~3–5 dev-hours/month at mature scale (linear, not compounding).

### R4. DB-per-instance operational cost — **MITIGATED**
11K DBs at V3 scale requires purpose-built tooling; standard Postgres tools assume 1 DB.

**Resolution:** 7-layer strategy in [§12D](#12d-database-fleet-operations-r4-mitigation) — automated provisioning/deprovisioning, migration orchestrator (dedicated service), tiered backup by reality status, pgbouncer connection pooling, metrics aggregation, shared-Postgres sharding, orphan DB detection. Admin tooling + capacity planning deferred to **DF11 — Database Fleet Management**.

Expected V3 footprint: 2–4 Postgres servers (not 1 per DB), ~40 TB backup storage in dedicated MinIO bucket.

### R5. Cross-instance queries — **MITIGATED (by rejection)**
Initial framing assumed feature demand for cross-reality queries. Re-examination: no product feature actually requires cross-instance live query. The only cross-reality feature is world travel (DF6), which is atomic import/export, not query.

**Resolution:** 3-layer strategy in [§12E](#12e-cross-instance-data-access-r5-mitigation) — meta registry lookups (L1), event-driven propagation via dedicated `meta-worker` service (L2), analytics explicitly deferred (L3). Anti-pattern codified in [docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md](../../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md).

Over-designed analytics tooling (DF12) withdrawn — not registered until demand surfaces.

### R6. Outbox publisher failure — **MITIGATED**
Publisher is critical path for realtime broadcast. Multiple failure modes (crash, lag, poison pill, Redis overflow).

**Resolution:** 7-layer strategy in [§12F](#12f-outbox-publisher-reliability-r6--r12-mitigation) — dedicated `publisher` service at `services/publisher/`, outbox schema extension with retry + DLQ, per-reality lag monitoring with alert tiers, WebSocket catchup protocol backed by new REST endpoint `GET /v1/realities/{id}/events?since=...`, graceful shutdown + leader election. Admin UX folded into expanded DF9 (now "Event + Projection + Publisher Ops").

Zero-message-loss guaranteed: outbox durable, Redis is cache only, DB is SSOT.

### R7. Multi-aggregate transaction deadlocks — **MITIGATED (reframed)**
Initial framing assumed aggregate is concurrency unit. Re-examination: game is turn-based, session is the concurrency unit. Intra-session writes are serial — no deadlock possible. The real R7 is cross-session effect propagation (e.g., spell destroying tavern affects multiple sessions).

**Resolution:** 2-pillar, 7-layer strategy in [§12G](#12g-session-as-concurrency-boundary--cross-session-event-handler-r7-mitigation):
- Pillar A: Session as single-writer command processor (mandatory, not opt-in)
- Pillar B: Cross-session event handler (dedicated `services/event-handler/` service) with scope-tagged events and per-session event queues

New feature registered: **DF13 — Cross-Session Event Handler** (admin + dev UX). §8.2–§8.4 multi-aggregate patterns superseded by session-level serialization.

### R8. Snapshot size drift — **MITIGATED**
Popular NPC with thousands of per-PC memory entries would produce ~75MB snapshots per NPC in naive design (linear growth with interaction count).

**Resolution:** 7-layer strategy in [§12H](#12h-npc-memory-aggregate-split-r8-mitigation-a1-foundation) — split `npc` into core aggregate + per-pair `npc_pc_memory` aggregates (UUIDv5 derived ID), bounded memory per pair (LRU facts + rolling summary), size enforcement with auto-compaction, cold decay (30/90/365 day tiers), lazy loading scoped by R7 session boundary, embedding stored separately in pgvector projection, observability. Platform storage: 15× reduction per hot NPC.

**A1 (NPC memory at scale) dependent on this:** R8 provides infrastructure; A1's semantic layer (retrieval quality, summary LLM prompt, fact extraction) builds on top. A1 moves from `OPEN` to `PARTIAL` with this resolution.

Admin tooling folded into expanded **DF9** (now "Event + Projection + Publisher + NPC Memory Ops").

### R9. Instance close destructive — **MITIGATED**
Naive single-step close = irreversible accidental data loss. Unlike other failures, no retry path.

**Resolution:** 8-layer multi-gate protocol in [§12I](#12i-safe-reality-closure-r9-mitigation) — 6-state machine (`active → pending_close → frozen → archived → archived_verified → soft_deleted → dropped`) with 120+ day minimum from initiation to irreversible drop; mandatory archive verification drill (checksum + sample decode + sample restore + diff); double-approval for final drop in production; 30-day cooling period with owner cancel; 90-day soft-delete retention (DB renamed, not dropped); emergency cancel at any pre-drop state; exhaustive audit log; player notification cascade. Admin tooling folded into expanded **DF11** (now "Database Fleet + Reality Lifecycle Management").

§7.3 single-step close flow deprecated, superseded by §12I.

### R10. No built-in global ordering across instances — **ACCEPTED**
Per-reality `event_id` is monotonic per-DB; no global sequence across realities.

**Resolution:** consciously accepted in [§12J](#12j-global-event-ordering--accepted-trade-off-r10). No product feature requires global ordering. Analytics (deferred) can merge streams by `created_at` timestamp. NTP-synced Postgres clocks give ~100ms timestamp accuracy, sufficient. Cost of mitigation (centralized sequencer, Lamport/vector clocks) exceeds benefit.

### R11. pgvector footprint × N DBs — **MITIGATED**
Many small vector indexes across N reality DBs. Concern: RAM cost at scale.

**Resolution:** 4-layer strategy in [§12K](#12k-pgvector-footprint-management-r11-mitigation) — embedding already separated from snapshots (R8-L6), HNSW tuned (m=16, ef_construction=64), cold reality eviction automatic via Postgres buffer pool, memory monitoring per shard. Per-shard footprint at V3 scale: ~1.5GB / 256GB RAM = <1%. External vector store (Qdrant/Weaviate) documented as escape hatch if workload changes dramatically; not V1.

### R12. Redis stream as publication channel is ephemeral — **MITIGATED (subsumed by R6-L6)**
Redis streams are capped; events fall off when publisher lags past MAXLEN.

**Resolution:** Framed explicitly as "Redis is cache, DB is SSOT" in [§12F.6](#12f6-layer-6--redis-stream-retention--db-fallback-resolves-r12). Consumer logic falls back to DB events table when stream earliest > client's last_seen_event_id. No data loss possible — events durable in Postgres.

New REST endpoint `GET /v1/realities/{id}/events?since=...` serves catchup. Per-reality `MAXLEN` configurable (default 10K, can raise for crowded realities).

### R13. Admin tooling complexity — **MITIGATED**
Across DB-per-reality + event sourcing + multi-state lifecycle + 11 admin surfaces, admin complexity is real. Wrong tool or ad-hoc SQL = corrupt state.

**Resolution:** mechanisms + discipline layer in [§12L](#12l-admin-tooling-discipline-r13-mitigation) — canonical admin command library (no ad-hoc SQL), compensating-event pattern (respect event sourcing), centralized admin_action_audit log, destructive action confirmation with typed reality name, UI guardrails (no raw DROP button, only safe state machine), rollback-per-action via compensating events.

Governance policy formalized at [`docs/02_governance/ADMIN_ACTION_POLICY.md`](../../02_governance/ADMIN_ACTION_POLICY.md) — L1–L6 are requirements, not suggestions.

---

## 14. Decisions still open (TBC)

| # | Question | Placeholder |
|---|---|---|
| 2 | Embedding storage — pgvector in each instance DB, or a separate vector service? | Leaning pgvector for V1 |
| 3 | Redis durability level — no persistence, AOF, or replicate to Postgres? | Leaning no persistence |
| 5 | Event log partition strategy — monthly (proposed), alternatives? | Monthly |
| 6 | Hot ephemeral state durability — Redis only (lossy), or replicated? | Leaning Redis only |

These become blocking when we commit to implementation. For now they can wait.

## 15. Where this leaves us

**Answered by this document:**
- What is physically stored and where
- How writes become events become state
- How instances are isolated
- How realtime broadcast fits in
- What capacity headroom looks like

**Still open (in decreasing order of urgency):**
- **R1–R13** above — the user indicated ideas for these; discuss next
- Commands and event types enumerated in full (only envelope + examples given here)
- NPC memory aggregation strategy in detail (touches [01 A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--open))
- Projection query patterns (read path specifics)
- Migration from V1 sync projections → V3 async projections

## 16. References

- [00_VISION.md](00_VISION.md)
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — storage decisions here constrain A1 (NPC memory), B1 (concurrency), B3 (simulation tick), B5 (rollback), G3 (canon-drift audit)
- `../101_DATA_RE_ENGINEERING_PLAN.md` — knowledge-service's event-pipeline shape
- Event Sourcing canonical refs: Greg Young on Event Sourcing (2010 talk); Fowler's bliki entry; "Implementing Domain-Driven Design" (Vaughn Vernon) Ch. 8
- MMO prior art: EVE Online's stackless single-shard design; WoW's per-realm database model; Guild Wars 2 architecture talks
