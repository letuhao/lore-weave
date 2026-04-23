# Open Decisions — Pending User Confirmation

> **Purpose:** Single place to track all decisions that are pending the user's answer. As the conversation accumulates, questions get parked here so none are lost.
> **Not a decision doc itself.** This file just tracks what needs answering; actual decisions are recorded in their respective design docs.

---

## How to use this file

- **Locked** — user has explicitly confirmed. Moved to "Locked decisions" section at bottom; removed from pending.
- **Default applied, pending confirm** — I proposed a default; user said "default" or was silent; the default is in the relevant doc but user has the right to overturn.
- **Open, no default** — genuinely waiting for user input. No default applied yet.

When the user answers one, I:
1. Update the relevant design doc (02, 03, etc.) to reflect the decision
2. Move the entry from "Pending" to "Locked decisions" below
3. Add a brief rationale/note if the user gave one

---

## Pending decisions

### From multiverse model (03) — remaining

| # | Decision | Default applied | Status |
|---|---|---|---|
| MV5-pri | **Primitives that cannot be deferred** (even though travel feature is deferred) — schema items that must exist now to avoid painful retrofit | See §"MV5 primitives" | Applied (P1, P4, P5 added to schema); user can flag any missed primitive |

All other multiverse decisions are **LOCKED**. See locked decisions table below.

### Beyond multiverse — vision-level decisions (from 00_VISION.md discussion)

| # | Decision | Default applied | Status |
|---|---|---|---|
| V1 | **Product shape priority** — A (solo RP), A+B (solo + co-author), or direct path to D (MMO)? | Staged: V1 solo RP → V2 coop scene → V3 persistent multiverse | Default — pending confirm |
| V2 | **Service split** — `world-service` (Go) + `roleplay-service` (Python) as two separate services, or combined? | Two services as designed | Default — pending confirm |
| V3 | **Business model** — self-hosted BYOK only, platform-hosted only, or both? | Both — but MMO only viable in platform mode | Default — pending confirm |

---

## Questions without defaults (need explicit user input)

These are items where I did not propose a default because either (a) the question is genuinely ambiguous and needs product intent, or (b) the answer has dependencies on decisions above.

### Q-RISK — Risk discussion items
User indicated they have ideas for risks R1–R13 in [02_STORAGE_ARCHITECTURE.md §13](02_STORAGE_ARCHITECTURE.md) and M1–M7 in [01_OPEN_PROBLEMS.md §M](01_OPEN_PROBLEMS.md). These were parked for separate discussion.

| # | Risk | Source | Note |
|---|---|---|---|
| R1 | Event volume explosion | 02 §13 | User flagged this as largest risk; multiverse model is the proposed mitigation, awaiting user feedback |
| R2 | Projection rebuild time at scale | 02 §13 | |
| R3 | Event schema evolution pain | 02 §13 | |
| R4 | DB-per-instance operational cost | 02 §13 | |
| R5 | Cross-instance queries | 02 §13 | |
| R6 | Outbox publisher failure | 02 §13 | |
| R7 | Multi-aggregate transaction deadlocks | 02 §13 | |
| R8 | Snapshot size drift | 02 §13 | |
| R9 | Instance close = destructive | 02 §13 | |
| R10 | No built-in global ordering across instances | 02 §13 | |
| R11 | pgvector per-instance footprint | 02 §13 | Depends on S2 |
| R12 | Redis stream ephemerality | 02 §13 | Depends on S3 |
| R13 | Admin tooling complexity | 02 §13 | |
| ~~M1~~ | ~~Reality discovery problem~~ | 01 §M | **LOCKED 2026-04-23** — M1-D1..D7 below; [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery) |
| ~~M3~~ | ~~Canonization contamination~~ | 01 §M | **LOCKED 2026-04-23** — M3-D1..D8 below; [03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution). DF3 implementation + E3 legal still independent. |
| ~~M4~~ | ~~Inconsistent L1/L2 updates across reality lifetimes~~ | 01 §M | **LOCKED 2026-04-23** — M4-D1..D6 below; [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution). Reuses R5-L2 xreality infrastructure. |
| ~~M7~~ | ~~Concept complexity for users~~ | 01 §M | **LOCKED 2026-04-23** — M7-D1..D5 below; [03 §9.6](03_MULTIVERSE_MODEL.md#96-progressive-disclosure--m7-resolution) |

### Q-A1 — NPC memory at scale
Critical-path `OPEN` problem. Multiverse bounds the scope (per-reality) but storage strategy still unsolved. Needs:
- Concrete memory schema decision (structured facts vs summary vs hybrid)
- Retrieval strategy (keyword vs semantic vs hybrid)
- Rewrite/compaction cadence
- Research review (MemGPT, Generative Agents, mem0, Zep)

### Q-A4 — Retrieval quality evaluation
Cannot be answered in design; needs measured evaluation on real LoreWeave books. Blocks implementation commitment.

### Q-D1 — LLM cost measurement
Requires V1 prototype to measure actual cost/user-hour. Blocks business-model commitment.

### Q-E3 — IP ownership legal review
Requires external legal input. Not something a design doc can resolve.

---

## Locked decisions (history)

As user confirms items, they move here with the answer and any rationale.

| # | Decision | Answered on | Answer | Rationale / Notes |
|---|---|---|---|---|
| L1 | Event sourcing mode (storage) | 2026-04-23 | Full event sourcing | Events are SSOT; projections rebuildable; replay / rollback / audit are load-bearing for MMO |
| L4 | Reality isolation (storage) | 2026-04-23 | 1 DB per reality (with subtree grouping until split threshold) | Blast radius containment; natural sharding |
| LMV-Fork | Fork semantics | 2026-04-23 | Snapshot fork | Live fork creates non-reproducible timelines and cascade invalidation nightmares; no justifying benefit |
| LMV-Name | Model name | 2026-04-23 | "Multiverse" | Peer realities with shared origin, no privileged root — matches parallel-universe philosophy (SCP-style) |
| S2 | Embedding storage | 2026-04-23 | pgvector inside each reality DB | Simpler ops; transactional with projections; ≤100M vectors per DB is fine |
| S3 | Redis durability | 2026-04-23 | No persistence (pure cache) | Ephemeral only; rebuild from Postgres on crash |
| S5 | Event log partitioning | 2026-04-23 | Monthly partitions | Simple; archive-friendly |
| S6 | Hot ephemeral state durability | 2026-04-23 | Redis-only, lossy OK | Crash = forget transient state; user reconnect rebuilds |
| MV1 | L1 axiomatic definition | 2026-04-23 | Manual author flag + category heuristics | Author controls critical attributes; categories (species, magic-system) default to L1 |
| MV2 | Canonization allowed | 2026-04-23 | Yes, author-gated explicit action | Not automatic, not player-voted |
| MV3 | Canonicality badge in UI | 2026-04-23 | Yes, discovery hint only | No gameplay enforcement |
| MV6 | Player cap per reality | 2026-04-23 | Fixed cap = 100 (**configurable**) | Stored in config, not hardcoded. Simpler than dynamic soft/hard caps. |
| MV8 | DB subtree split threshold | 2026-04-23 | 50M events OR 500 concurrent players (**configurable**) | Stored in config, not hardcoded. Tune via ops observability. |
| MV4-a | Auto-fork seed mode | 2026-04-23 | **Fresh from book** (not snapshot from parent) | User's insight: snapshot fork amplifies storage via projection population on child. Fresh seed = clean sharding, zero amplification. Auto-fork is pure sharding, not narrative. |
| MV4-a-load | Auto-fork load balancing (drain parent?) | 2026-04-23 | **No drain** | Player stays in whatever reality they joined. Cross-reality movement is handled by future world-travel feature. |
| MV4-b | User-initiated fork | 2026-04-23 | **Enabled in V1, no quota, full user choice** | User is "world creator." Can fork from any reality at any point. Quota/cost calculation deferred to future feature. |
| MV7 | Seed mode at reality creation | 2026-04-23 | **Auto-fork = fresh; user-fork = user chooses (fresh or snapshot); first reality of book = fresh** | Resolved by MV4-a + MV4-b. |
| MV9 | Fork depth strategy | 2026-04-23 | **Auto-rebase at N=5** (configurable) | When depth would exceed 5, auto-rebase: flatten ancestor chain into a fresh-seeded reality with inherited snapshot. |
| MV10 | Auto-freeze inactive reality | 2026-04-23 | **30 days no activity** (configurable) | Stored in config. |
| MV11 | Auto-archive frozen reality | 2026-04-23 | **90 days frozen** (configurable) | Stored in config. |
| MV5 | Cross-reality travel | 2026-04-23 | **Deferred to world-travel feature** | Full feature spec is a separate doc. V1–V2 assume no travel. BUT: some primitives cannot be deferred — see §"MV5 primitives" below. |
| PC-A1 | PC creation mode | 2026-04-23 | Full custom + templates | [04 §3.1](04_PLAYER_CHARACTER_DESIGN.md) |
| PC-A2 | Play as existing glossary character | 2026-04-23 | Supported | [04 §3.2](04_PLAYER_CHARACTER_DESIGN.md) |
| PC-A3 | Canon validation at PC creation | 2026-04-23 | None — paradox allowed | Runtime enforcement via World Rule feature (DF4) |
| PC-B1 | PC death behavior | 2026-04-23 | Per-reality rule; death is just an event | V1 default: permadeath; configurable by World Rules (DF4) |
| PC-B2 | Offline PC in world | 2026-04-23 | Visible, vulnerable; user should `/hide`; LLM does not act | Details in Daily Life feature (DF1) |
| PC-B3 | Prolonged hidden PC | 2026-04-23 | Auto-converts to NPC; leaves hiding; LLM takes over | Details in DF1 |
| PC-C1 | Max PCs per user | 2026-04-23 | 5 (configurable); extra via purchase | `roleplay.pc.max_per_user = 5`; purchase in DF2 |
| PC-C2 | PC personality | 2026-04-23 | User IS PC while active; LLM persona only when NPC-converted | No LLM persona layer for active PC |
| PC-C3 | PC stats model | 2026-04-23 | Simple state-based (no RPG mechanics) | Concrete schema in DF7 |
| PC-D1 | Party / group system | 2026-04-23 | No parties — Session replaces all group mechanics | Details in DF5 |
| PC-D2 | PvP | 2026-04-23 | Enabled within a session | Consent model in DF4/DF5 |
| PC-D3 | Interaction scope | 2026-04-23 | Session only — no global chat | Details in DF5 |
| PC-E1 | PC actions affect L2 canon | 2026-04-23 | Yes, via canonization — **deferred** | DF3 |
| PC-E2 | Author notified of canon-worthy acts | 2026-04-23 | Yes — **deferred** | DF3 |
| PC-E3 | Paradox acceptance | 2026-04-23 | Allowed per reality, governed by World Rules — **deferred** | DF4 |
| R1-L1 | Audit split (events vs event_audit tables) | 2026-04-23 | **Accepted** — 2 tables, state events permanent, audit bounded retention | [02 §12A.1](02_STORAGE_ARCHITECTURE.md) |
| R1-L2 | Event emission discipline | 2026-04-23 | **Accepted** — persist only state-change + core canon events; derived/ephemeral events not logged (or audit only) | [02 §12A.2](02_STORAGE_ARCHITECTURE.md) |
| R1-L3 | Tiered retention per event type | 2026-04-23 | **Accepted** with defaults: canon forever, mood 30d, audit 30d, broadcast 24h — all configurable | [02 §12A.3](02_STORAGE_ARCHITECTURE.md) |
| R1-L4 | Tiered archive pipeline (Hot/Warm/Cold) | 2026-04-23 | **Accepted** — Postgres hot ≤90d, warm partition 90–365d, MinIO cold Parquet+ZSTD >365d | [02 §12A.4](02_STORAGE_ARCHITECTURE.md) |
| R1-L5 | Snapshot-then-truncate non-canon aggregates | 2026-04-23 | **Accepted** — after 180d idle + existing snapshot, delete non-canon events pre-snapshot; canon events never deleted | [02 §12A.5](02_STORAGE_ARCHITECTURE.md) |
| R1-L6 | lz4 compression (Postgres 14+) | 2026-04-23 | **Accepted** — lz4 on JSONB columns + ZSTD for MinIO cold | [02 §12A.6](02_STORAGE_ARCHITECTURE.md) |
| R1-archive-bucket | MinIO bucket for event archive | 2026-04-23 | **New bucket**: `lw-world-archive`, per-reality path structure | [02 §12A.4](02_STORAGE_ARCHITECTURE.md) |
| R1-impl-order | V1 implementation ordering | 2026-04-23 | **Accepted** — V1: L1+L2+L6 mandatory; V1+30d: L3; V2: L4; V3: L5 | [02 §12A.9](02_STORAGE_ARCHITECTURE.md) |
| R2-L1 | Snapshot-anchored rebuild | 2026-04-23 | **Accepted** (already locked in §6) | [02 §6, §12B.1](02_STORAGE_ARCHITECTURE.md) |
| R2-L2 | Per-aggregate parallel rebuild | 2026-04-23 | **Accepted** — default 8 workers, configurable | [02 §12B.2](02_STORAGE_ARCHITECTURE.md) |
| R2-L3 | Schema migration strategy | 2026-04-23 | **V1: freeze-rebuild-thaw; V2: blue-green dual-write** | [02 §12B.3](02_STORAGE_ARCHITECTURE.md) |
| R2-L4 | Projection integrity checker | 2026-04-23 | **Accepted** — daily random-sample (20 aggregates) + monthly full check | [02 §12B.4](02_STORAGE_ARCHITECTURE.md) |
| R2-L5 | Catastrophic rebuild procedure | 2026-04-23 | **Accepted** — freeze → rebuild → verify → thaw; ~5–10 min per reality; rolling 50 concurrent | [02 §12B.5](02_STORAGE_ARCHITECTURE.md) |
| R2-impl-order | V1 implementation ordering | 2026-04-23 | V1: L2 + L5 design; V1+60d: L4; V2: L3 blue-green; V3+: DF9 | [02 §12B.8](02_STORAGE_ARCHITECTURE.md) |
| R2-admin-tooling | Admin UX for rebuild/integrity ops | 2026-04-23 | **Deferred** — new DF9 | DF9 |
| R3-L1 | Additive-first discipline | 2026-04-23 | **Accepted** — prefer new optional field or new event_type over mutating existing | [02 §12C.1](02_STORAGE_ARCHITECTURE.md) |
| R3-L2 | Schema-as-code + codegen | 2026-04-23 | **Accepted** — Go structs authoritative, codegen → TypeScript + Python; Git-versioned, no registry service | [02 §12C.2](02_STORAGE_ARCHITECTURE.md) |
| R3-L3 | Upcaster chain on read | 2026-04-23 | **Accepted** — automated via registry; events never mutated on disk | [02 §12C.3](02_STORAGE_ARCHITECTURE.md) |
| R3-L4 | Schema validation on write | 2026-04-23 | **Accepted** — strict in all environments | [02 §12C.4](02_STORAGE_ARCHITECTURE.md) |
| R3-L5 | Breaking change = new event_type | 2026-04-23 | **Accepted** — 90-day deprecation cooldown, configurable | [02 §12C.5](02_STORAGE_ARCHITECTURE.md) |
| R3-L6 | Archive upgrade (upcast at cold-archive time) | 2026-04-23 | **Deferred to V2** — V1 archives events in original version | [02 §12C.6](02_STORAGE_ARCHITECTURE.md) |
| R3-polyglot | Polyglot type generation | 2026-04-23 | **Accepted** — Go → codegen → TS + Python; shared `contracts/events/` location | [02 §12C.7](02_STORAGE_ARCHITECTURE.md) |
| R3-tooling | Dev tooling surface | 2026-04-23 | **Deferred** — new DF10 | DF10 |
| R3-impl-order | V1 implementation ordering | 2026-04-23 | V1 mandatory: L1+L2+L3+L4; L5 as ongoing policy; L6 defer V2; DF10 matures V1+30d → V3 | [02 §12C.10](02_STORAGE_ARCHITECTURE.md) |
| R4-L1 | Automated DB provisioning + deprovisioning | 2026-04-23 | **Accepted** — scripted, idempotent, tied to reality lifecycle | [02 §12D.1](02_STORAGE_ARCHITECTURE.md) |
| R4-L2 | Migration orchestrator (dedicated service) | 2026-04-23 | **Accepted** — dedicated Go service, concurrency 10, idempotent migrations required | [02 §12D.2](02_STORAGE_ARCHITECTURE.md) |
| R4-L3 | Tiered backup strategy | 2026-04-23 | **Accepted** — daily inc + weekly full (active), weekly full (frozen), MinIO archive replaces backup (archived) | [02 §12D.3](02_STORAGE_ARCHITECTURE.md) |
| R4-L3-bucket | Backup storage location | 2026-04-23 | **Dedicated bucket** `lw-db-backups` (separate from `lw-world-archive`) | [02 §12D.3](02_STORAGE_ARCHITECTURE.md) |
| R4-L4 | Connection pooling | 2026-04-23 | **pgbouncer** (transaction mode), per-shard; re-evaluate pgcat at V3 if limits hit | [02 §12D.4](02_STORAGE_ARCHITECTURE.md) |
| R4-L5 | Metrics aggregation | 2026-04-23 | **Accepted** — Prometheus with `reality_id` + `shard_host` labels only (cap cardinality) | [02 §12D.5](02_STORAGE_ARCHITECTURE.md) |
| R4-L6 | Postgres server sharding | 2026-04-23 | **Accepted** — many DBs per server (up to ~2K/medium or ~10K/large); registry tracks shard allocation | [02 §12D.6](02_STORAGE_ARCHITECTURE.md) |
| R4-L7 | Orphan DB detection | 2026-04-23 | **Accepted** — nightly reconciliation, 7-day grace before auto-drop | [02 §12D.7](02_STORAGE_ARCHITECTURE.md) |
| R4-admin-tooling | Admin UX for fleet ops | 2026-04-23 | **Deferred** — new DF11 (distinct from DF9) | DF11 |
| R4-impl-order | V1 implementation ordering | 2026-04-23 | V1: L1+L4+L7; V1+30d: L2; V1+60d: L3; V2: L5+L6; V3+: DF11 | [02 §12D.10](02_STORAGE_ARCHITECTURE.md) |
| R5-reframe | R5 reframed | 2026-04-23 | **Cross-instance live query rejected as API pattern** — no product feature actually requires it; only world travel (DF6) is cross-reality, and it's import/export | [02 §12E.1](02_STORAGE_ARCHITECTURE.md) |
| R5-L1 | Meta registry lookups | 2026-04-23 | **Accepted minimal** — existing tables + `trending_score` + `last_stats_updated_at` on `reality_registry`; no speculative new indexes | [02 §12E.2](02_STORAGE_ARCHITECTURE.md) |
| R5-L2 | Event-driven propagation | 2026-04-23 | **Accepted** — 3 xreality.* topics via Redis Streams (reuse IF-5) | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) |
| R5-L2-service | Meta-worker service | 2026-04-23 | **Dedicated Go service** (narrow scope) at `services/meta-worker/` | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) |
| R5-L3 | Analytics infrastructure | 2026-04-23 | **Deferred indefinitely** — no ClickHouse/OLAP locked; re-evaluate when specific feature demands | [02 §12E.4](02_STORAGE_ARCHITECTURE.md) |
| R5-anti-pattern | Anti-pattern governance | 2026-04-23 | Codified as governance policy at `docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md` | [02 §12E.6](02_STORAGE_ARCHITECTURE.md) |
| R5-DF12 | Cross-Reality Analytics & Search tooling (previously candidate) | 2026-04-23 | **WITHDRAWN** — not registered; no justifying feature | — |
| R5-impl-order | V1 implementation ordering | 2026-04-23 | V1: L1 + L2 + governance doc; V1+60d: L2 canon propagation activates on first author edit; V3+ re-evaluate L3 if demand | [02 §12E.8](02_STORAGE_ARCHITECTURE.md) |
| R6-L1 | Outbox pattern + retry/DLQ schema | 2026-04-23 | **Accepted** — events_outbox extended with attempts, last_error, last_attempt_at, dead_lettered_at columns | [02 §12F.1](02_STORAGE_ARCHITECTURE.md) |
| R6-L2 | Publisher service (dedicated Go) | 2026-04-23 | **Accepted** — `services/publisher/`, polling with FOR UPDATE SKIP LOCKED, leader election via Redis SETNX | [02 §12F.2](02_STORAGE_ARCHITECTURE.md) |
| R6-L3 | Lag monitoring + alerting | 2026-04-23 | **Accepted** — per-reality metrics, 3-tier alert thresholds (warn/page/critical), publisher heartbeat table in meta registry | [02 §12F.3](02_STORAGE_ARCHITECTURE.md) |
| R6-L4 | Client reconnect + catchup | 2026-04-23 | **Accepted** — WebSocket handshake + new REST endpoint `GET /v1/realities/{id}/events?since={event_id}&limit=500`; client-side dedup | [02 §12F.4](02_STORAGE_ARCHITECTURE.md) |
| R6-L5 | Poison pill / dead letter | 2026-04-23 | **Accepted** — max 5 retries, exponential backoff "1s,5s,30s,2m,10m", admin resolution via DF9 | [02 §12F.5](02_STORAGE_ARCHITECTURE.md) |
| R6-L6 | Redis stream cache + DB fallback | 2026-04-23 | **Accepted** — MAXLEN 10000 default (configurable per-reality via `reality_registry.stream_maxlen`), DB events table SSOT | [02 §12F.6](02_STORAGE_ARCHITECTURE.md) |
| R6-L7 | Graceful shutdown | 2026-04-23 | **Accepted** — 30s timeout, status='draining', complete in-flight, release Redis leader lock | [02 §12F.7](02_STORAGE_ARCHITECTURE.md) |
| R6-scaling | Horizontal scaling | 2026-04-23 | V1: 1 publisher/shard; V2: 2 active-passive with partition-by-reality hash; V3+: 4+ with auto-rebalance | [02 §12F.8](02_STORAGE_ARCHITECTURE.md) |
| R6-admin-tooling | Admin UX for publisher ops | 2026-04-23 | **Folded into DF9** — DF9 scope expanded to "Event + Projection + Publisher Ops" | [02 §12F.12](02_STORAGE_ARCHITECTURE.md) |
| R6-impl-order | V1 implementation ordering | 2026-04-23 | V1 all layers (L1–L7); V1+30d: alert routing + DF9 dashboard starts; V2: multi-replica; V3+: auto-rebalance | [02 §12F.11](02_STORAGE_ARCHITECTURE.md) |
| R12 | Redis stream ephemerality | 2026-04-23 | **Subsumed by R6-L6** — Redis is cache, DB is SSOT, no data loss possible | [02 §12F.6](02_STORAGE_ARCHITECTURE.md) |
| R7-reframe | R7 reframed | 2026-04-23 | **Session is concurrency unit** (not aggregate). Game is turn-based → intra-session is serial by design → no deadlock within session. Real R7 is cross-session effect propagation. | [02 §12G.1](02_STORAGE_ARCHITECTURE.md) |
| R7-L1 | Session as single-writer command processor | 2026-04-23 | **Mandatory architecture** — 1 processor per session, serial FIFO, LLM outside tx. Supersedes §8.2–§8.4 multi-aggregate patterns. | [02 §12G.2](02_STORAGE_ARCHITECTURE.md) |
| R7-L2 | Event scope tagging | 2026-04-23 | **Accepted** — every event has `scope` column: `session` (default), `region`, `reality`, `world` | [02 §12G.3](02_STORAGE_ARCHITECTURE.md) |
| R7-L3 | Cross-session event handler service | 2026-04-23 | **Dedicated Go service** at `services/event-handler/`, separate from publisher — different concern, different scale | [02 §12G.5](02_STORAGE_ARCHITECTURE.md) |
| R7-L4 | Session event queue (per session, per reality DB) | 2026-04-23 | **Accepted** — `session_event_queue` table, priority pop ahead of user input | [02 §12G.4](02_STORAGE_ARCHITECTURE.md) |
| R7-L5 | Propagation semantics | 2026-04-23 | **Async-only V1** — originator doesn't block; affected sessions process on next tick. Sync deferred V2+ if needed. | [02 §12G.6](02_STORAGE_ARCHITECTURE.md) |
| R7-L6 | NPC single-session constraint (V1) | 2026-04-23 | **NPC can be in 1 session at a time** — avoids hardest concurrency; UI gates join attempts. Multi-presence deferred V2+. | [02 §12G.7](02_STORAGE_ARCHITECTURE.md) |
| R7-queue-priority | Queue processing priority | 2026-04-23 | **Queue events before user input** — environmental effects feel immediate | [02 §12G.6](02_STORAGE_ARCHITECTURE.md) |
| R7-admin-tooling | Admin UX for event handler | 2026-04-23 | **New DF13** — Cross-Session Event Handler (distinct from DF9, DF11) | DF13 |
| R7-impl-order | V1 implementation ordering | 2026-04-23 | V1: L1–L7 all. V1+30d: DF13 UX. V2: sync propagation + NPC multi-presence if demanded. | [02 §12G.12](02_STORAGE_ARCHITECTURE.md) |
| R8-L1 | NPC aggregate split | 2026-04-23 | **Two aggregate types**: `npc` (core state only) + `npc_pc_memory` (one per (npc_id, pc_id) pair). UUIDv5(`npc_pc_memory`, npc_id‖pc_id) as deterministic aggregate ID. Both event-sourced. | [02 §12H.2](02_STORAGE_ARCHITECTURE.md) |
| R8-L2 | Bounded memory per pair | 2026-04-23 | **Max 100 facts** per pair (LRU eviction). Summary rewritten every 50 events via LLM compaction. Summary cap 2000 chars. | [02 §12H.3](02_STORAGE_ARCHITECTURE.md) |
| R8-L3 | Snapshot size enforcement | 2026-04-23 | **1MB warn / 5MB critical**. Critical triggers auto-compaction. | [02 §12H.4](02_STORAGE_ARCHITECTURE.md) |
| R8-L4 | Cold memory decay schedule | 2026-04-23 | **30d drop facts / 90d drop embedding / 365d archive to MinIO**. Restore on PC return. All configurable. | [02 §12H.5](02_STORAGE_ARCHITECTURE.md) |
| R8-L5 | Lazy loading per turn | 2026-04-23 | **Load only session's PCs** (R7-L6 constraint). Bounded by session cap, not total interaction history. | [02 §12H.6](02_STORAGE_ARCHITECTURE.md) |
| R8-L6 | Embedding storage separation | 2026-04-23 | **Separate `npc_pc_memory_embedding` table** (pgvector HNSW index). Embedding NOT in aggregate snapshot. Aggregate carries `content_hash`/`update_token` reference only. | [02 §12H.7](02_STORAGE_ARCHITECTURE.md) |
| R8-L7 | Observability | 2026-04-23 | Per-aggregate metrics with cardinality capped per-reality | [02 §12H.8](02_STORAGE_ARCHITECTURE.md) |
| R8-admin-tooling | Admin UX for NPC memory ops | 2026-04-23 | **Folded into DF9** — DF9 scope expanded to "Event + Projection + Publisher + NPC Memory Ops" | [02 §12H.14](02_STORAGE_ARCHITECTURE.md) |
| R8→A1 | A1 status change | 2026-04-23 | **A1 moves from `OPEN` → `PARTIAL`** — R8 provides infrastructure; A1 semantic layer (retrieval/summary/extraction quality) remains, pending V1 prototype data | [01 §A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--partial) |
| R8-impl-order | V1 implementation ordering | 2026-04-23 | V1: L1+L2+L5+L6+L7 (foundational). V1+60d: L3+L4 (when real data emerges). V2+: threshold tuning. | [02 §12H.13](02_STORAGE_ARCHITECTURE.md) |
| R9-L1 | Multi-stage close state machine | 2026-04-23 | **6 states**: active → pending_close → frozen → archived → archived_verified → soft_deleted → dropped. Minimum ~120 days from initiation to irreversible. | [02 §12I.1](02_STORAGE_ARCHITECTURE.md) |
| R9-L2 | Archive verification gate (hard) | 2026-04-23 | **Mandatory 5-step drill**: checksum + manifest + sample decode + sample restore + diff. Transition blocked until verified. 100-sample default (configurable). | [02 §12I.3](02_STORAGE_ARCHITECTURE.md) |
| R9-L3 | Double confirmation | 2026-04-23 | **Typed reality name** at initiate (single actor). **Second approver required** at soft_deleted → dropped in production. 24h approver cooldown. | [02 §12I.4](02_STORAGE_ARCHITECTURE.md) |
| R9-L4 | Cooling period | 2026-04-23 | **30 days in pending_close** (configurable), cancellable by owner | [02 §12I.5](02_STORAGE_ARCHITECTURE.md) |
| R9-L5 | Player notification cascade | 2026-04-23 | **30/7/1 day schedule** (configurable), in-app + email. DF6 export link when available. | [02 §12I.6](02_STORAGE_ARCHITECTURE.md) |
| R9-L6 | Soft-delete via rename | 2026-04-23 | **ALTER DATABASE RENAME** instead of DROP. 90-day hold (configurable). Un-rename possible via emergency restore. | [02 §12I.7](02_STORAGE_ARCHITECTURE.md) |
| R9-L7 | Emergency cancel escape hatch | 2026-04-23 | **Cancel at any pre-drop state**. pending_close/frozen: owner. archived/archived_verified/soft_deleted: admin (+ second approver for soft_deleted). | [02 §12I.8](02_STORAGE_ARCHITECTURE.md) |
| R9-L8 | Audit log (everything) | 2026-04-23 | **`reality_close_audit` table** records every transition/cancel/verify/approve/restore | [02 §12I.9](02_STORAGE_ARCHITECTURE.md) |
| R9-admin-tooling | Admin UX for closure ops | 2026-04-23 | **Folded into DF11** — DF11 scope expanded to "Database Fleet + Reality Lifecycle Management" | [02 §12I.14](02_STORAGE_ARCHITECTURE.md) |
| R9-impl-order | V1 implementation ordering | 2026-04-23 | V1 mandatory: L1+L4+L6+L7+L8. V1+30d: L2 verification. V1+60d: L3 double-approval + L5 notifications. V2+: DF11 UI mature. | [02 §12I.12](02_STORAGE_ARCHITECTURE.md) |
| R10 | Global event ordering across instances | 2026-04-23 | **ACCEPTED** — no product feature requires it. Per-reality ordering + `created_at` timestamp merge sufficient. NTP discipline. No mitigation code. | [02 §12J](02_STORAGE_ARCHITECTURE.md) |
| R11-L1 | Embedding in separate table | 2026-04-23 | Already locked (R8-L6) | [02 §12K.2](02_STORAGE_ARCHITECTURE.md) |
| R11-L2 | HNSW index tuning | 2026-04-23 | **m=16, ef_construction=64, ef_search=40** (configurable) | [02 §12K.3](02_STORAGE_ARCHITECTURE.md) |
| R11-L3 | Cold reality eviction | 2026-04-23 | **Automatic via Postgres buffer pool** — no manual eviction code | [02 §12K.4](02_STORAGE_ARCHITECTURE.md) |
| R11-L4 | Memory monitoring | 2026-04-23 | **Per-shard pgvector memory metric**; alert at >10% RAM | [02 §12K.5](02_STORAGE_ARCHITECTURE.md) |
| R11-escape | External vector store escape hatch | 2026-04-23 | **Documented inline** (not V1); Qdrant/Weaviate as future option. Promote to ADR if/when activated. | [02 §12K.6](02_STORAGE_ARCHITECTURE.md) |
| R13-L1 | Admin command library | 2026-04-23 | **Canonical commands at `services/admin-cli/commands/`** — no ad-hoc SQL in prod, each command named + versioned + dry-run | [02 §12L.1](02_STORAGE_ARCHITECTURE.md) |
| R13-L2 | Compensating events (respect event sourcing) | 2026-04-23 | **Admin changes emit `*.admin_override`/`*.admin_reset` events**, never raw UPDATE | [02 §12L.2](02_STORAGE_ARCHITECTURE.md) |
| R13-L3 | Admin action audit log (centralized) | 2026-04-23 | **`admin_action_audit` table in meta registry**, 2-year retention configurable | [02 §12L.3](02_STORAGE_ARCHITECTURE.md) |
| R13-L4 | Destructive action confirmation | 2026-04-23 | **Typed reality name confirmation** for destructive; double-approval for truly dangerous (reuse R9 pattern) | [02 §12L.4](02_STORAGE_ARCHITECTURE.md) |
| R13-L5 | Admin UI guardrails | 2026-04-23 | **No raw DROP/UPDATE buttons**; no free-form SQL in prod; dry-run required for destructive | [02 §12L.5](02_STORAGE_ARCHITECTURE.md) |
| R13-L6 | Rollback via compensating events | 2026-04-23 | **Reversible commands** document `--undo`; one-way explicitly documented; structural via normal ops flow | [02 §12L.6](02_STORAGE_ARCHITECTURE.md) |
| R13-governance | ADMIN_ACTION_POLICY governance doc | 2026-04-23 | **New doc at `docs/02_governance/ADMIN_ACTION_POLICY.md`** codifies L1–L6 as requirements | [02 §12L.7](02_STORAGE_ARCHITECTURE.md) |
| R13-impl-order | V1 implementation ordering | 2026-04-23 | V1: L1 (~10 commands) + L2 + L3 + L4 + governance doc. V1+30d: L5 UI guardrails. V1+60d: L6 rollback. | [02 §12L.9](02_STORAGE_ARCHITECTURE.md) |
| M1-D1 | Entry flow design | 2026-04-23 | **Smart funnel** — resume-PC → friend-match → canon_attempt top-ranked → "be the first". Never dump raw list on first click. | [03 §9.1.1](03_MULTIVERSE_MODEL.md#911-entry-flow--smart-funnel-m1-d1) |
| M1-D2 | Composite ranking signals + weights | 2026-04-23 | **7 signals, config-driven** (`multiverse.discovery.weight.*`). V1 defaults: friend=100, density=40, locale=30, canon_attempt=20, divergent=10, pure_what_if=5, recency=15, near-cap penalty=-20. Tune from metrics. | [03 §9.1.2](03_MULTIVERSE_MODEL.md#912-composite-ranking-m1-d2) |
| M1-D3 | Friend-follow source + PC presence | 2026-04-23 | **Reuse auth-service follow graph**. New PC field `presence_visibility TEXT NOT NULL DEFAULT 'friends'` (values: `friends \| mutuals \| nobody`). | [03 §9.1.3](03_MULTIVERSE_MODEL.md#913-friend-follow-layer-m1-d3) |
| M1-D4 | Canonicality hint governance | 2026-04-23 | **V1 self-declared by creator**, no audit. V2+: source-book author can override hint on derived realities (platform-mode). Reaffirms MV3: UI hint only, no gameplay effect. | [03 §9.1.4](03_MULTIVERSE_MODEL.md#914-canonicality-hint-governance-m1-d4) |
| M1-D5 | Browse UI pattern | 2026-04-23 | **Flat paginated list** (20/page). Filters: language, canonicality, has_friends, population_range, recent_activity. Hibernated/frozen hidden behind toggle. | [03 §9.1.5](03_MULTIVERSE_MODEL.md#915-browse-ui-m1-d5) |
| M1-D6 | Create-new gating | 2026-04-23 | **Advanced tab only** (not peer to Browse). Confirmation modal if ≥1 existing reality <50% cap. No hard block — preserves MV4-b (user remains world creator). | [03 §9.1.6](03_MULTIVERSE_MODEL.md#916-create-new-gating-m1-d6) |
| M1-D7 | Metrics for weight feedback | 2026-04-23 | **5 metrics logged**: default_landing_accept_rate, friend_match_rate, lonely_reality_ratio, reality_creation_rate_per_user, browse_filter_usage. Threshold: lonely_reality_ratio > 30% over 1 month → tighten density/gating. | [03 §9.1.7](03_MULTIVERSE_MODEL.md#917-metrics-feedback-loop-m1-d7) |
| M1→status | M1 status change | 2026-04-23 | **M1 moves `OPEN` → `PARTIAL`** (01) and `MITIGATED` (03 §11). Framework locked; weight values, preview format, cold-start interaction with C3, preview caching — all pending V1 data. | [01 §M1](01_OPEN_PROBLEMS.md#m1-reality-discovery-problem--partial) · [03 §9.1.8](03_MULTIVERSE_MODEL.md#918-residual-open-requires-v1-data) |
| M7-D1 | User-facing terminology map | 2026-04-23 | **12-row translation table** — reality→timeline, book→world, NPC→character, PC→"your character", L1→"world law", L2→"starting facts", L3→"story event", fork→"explore another version", event sourcing→"the world remembers", aggregate/projection never surfaced, canonicality_hint→"follows the book"/"alternate take"/"what-if". Power-user labels only in author tooling/admin/dev docs. | [03 §9.6.1](03_MULTIVERSE_MODEL.md#961-user-facing-terminology-map-m7-d1) |
| M7-D2 | Three-tier complexity model | 2026-04-23 | **Reader / Player / Author** tiers. Reader default auto-routed, no fork UI. Player sees browse + filters + badges. Author sees full multiverse controls. Soft upgrade triggers (not gates): Reader→Player at `tier.reader.sessions_to_prompt` (default 3) or explicit "Explore"; Player→Author on first book creation or settings toggle. User can always click "Advanced" to override tier default. | [03 §9.6.2](03_MULTIVERSE_MODEL.md#962-three-tier-complexity-model-m7-d2) |
| M7-D3 | Onboarding tutorial flow | 2026-04-23 | **4 steps** — (1) book detail = "Step inside" CTA, (2) first click = overlay "you're stepping into Alice's world, several timelines exist", (3) post-session = postcard summary, (4) tier-upgrade prompt at N sessions. Skippable, re-runnable via help menu. i18n via i18next; V1 ships EN + VI. | [03 §9.6.3](03_MULTIVERSE_MODEL.md#963-onboarding-tutorial-m7-d3) |
| M7-D4 | Copy style guide governance | 2026-04-23 | **New doc at `docs/02_governance/UI_COPY_STYLEGUIDE.md`** codifies M7-D1 map + phrasing patterns + PR review gate ("copy reviewed against styleguide" checkbox on user-facing UI PRs). | [docs/02_governance/UI_COPY_STYLEGUIDE.md](../../02_governance/UI_COPY_STYLEGUIDE.md) |
| M7-D5 | Contextual tooltips | 2026-04-23 | **7 tooltips locked** on: canon_attempt / divergent / pure_what_if badges, "Create new timeline" CTA, friend avatar, hibernated badge, "forked from R_α at event X" label. i18n, <100 char default. | [03 §9.6.5](03_MULTIVERSE_MODEL.md#965-contextual-helpers-m7-d5) |
| M7→status | M7 status change | 2026-04-23 | **M7 moves `OPEN` → `PARTIAL`** (01) and `MITIGATED` (03 §11). Framework locked; tutorial A/B copy, tier-upgrade thresholds, per-locale tooltip wording — all pending V1 data. | [01 §M7](01_OPEN_PROBLEMS.md#m7-concept-complexity-for-users--partial) · [03 §9.6.6](03_MULTIVERSE_MODEL.md#966-residual-open-requires-v1-data) |
| M3-D1 | Canonization trigger authority | 2026-04-23 | **Author-only** — no player request queue, no voting, no public canonization metrics, no auto-surfacing of candidates. Author opts-in per book to see "canonization-eligible" sidebar. | [03 §9.7.1](03_MULTIVERSE_MODEL.md#971-author-only-trigger-m3-d1) |
| M3-D2 | Diff view required before confirm | 2026-04-23 | **5 sections mandatory**: current state / proposed change / prose preview in book context / cascade impact (realities that see vs override per M4) / source attribution. 5s delay + typed `CANONIZE {attribute_name}` confirmation. No single-button canonize. | [03 §9.7.2](03_MULTIVERSE_MODEL.md#972-diff-view-mandatory-m3-d2) |
| M3-D3 | Event eligibility + player consent gates | 2026-04-23 | **Event flag** `canonization_eligible` default false; World Rule (DF4) can enable per-category (death / major_decision / world_state_change / relationship_milestone). Flavor / mood / combat never eligible. **PC consent** opt-in checkbox at PC creation (default ON, sticky, per-PC toggle). Any opt-out contributor → INELIGIBLE. | [03 §9.7.3](03_MULTIVERSE_MODEL.md#973-eligibility--consent-gates-m3-d3) |
| M3-D4 | L2 → L1 harder gate | 2026-04-23 | **R9 pattern reused**: 7-day cooling + typed book-name confirm + double approval in platform mode. **No direct L3 → L1** — must pass through L2 and wait ≥30 days. Permanent audit entry on every L1 promotion. | [03 §9.7.4](03_MULTIVERSE_MODEL.md#974-l2--l1-promotion--harder-gate-m3-d4) |
| M3-D5 | 90-day undo window | 2026-04-23 | Canonized entry carries `canonized_from` metadata. Within 90 days: single-click silent revert. After 90 days: compensating-write required (new L2 event preserves original canonization in history). L1 reversions use R9-style double-approval. All audit-logged. | [03 §9.7.5](03_MULTIVERSE_MODEL.md#975-reversibility--90-day-undo-window-m3-d5) |
| M3-D6 | Attribution + IP metadata | 2026-04-23 | Canonized event carries: contributing PC IDs + user IDs, narrator turn count, source reality + event chain, canonization timestamp, book author ID. Surfaces in glossary entity history + author-controlled export formatting. **Does NOT close E3** — legal ToS remains independent. | [03 §9.7.6](03_MULTIVERSE_MODEL.md#976-attribution--ip-metadata-m3-d6) |
| M3-D7 | Distinguishability in book content | 2026-04-23 | Subtle label + icon delta (quill=original, compass=canonized); toggleable in reading view; export options (strip / inline footnote / appendix credits). Author edits to canonized content tracked as derivative. | [03 §9.7.7](03_MULTIVERSE_MODEL.md#977-distinguishability-in-book-content-m3-d7) |
| M3-D8 | Scope fence M3 / DF3 / E3 | 2026-04-23 | **M3** = TECHNICAL + UX safeguards framework (locked here). **DF3** = full implementation. **E3** = legal launch-gate (platform mode only; self-hosted exempt). Design can lock now; platform launch gated on E3. | [03 §9.7.8](03_MULTIVERSE_MODEL.md#978-scope-fence-with-e3--df3-m3-d8) |
| M3→status | M3 status change | 2026-04-23 | **M3 moves `OPEN` → `PARTIAL`** (01) and `MITIGATED` (03 §11). Framework locked; "significant event" categorization + >90d compensating-write + export UI + edge cases remain DF3 details. E3 IP legal still a separate independent launch gate. | [01 §M3](01_OPEN_PROBLEMS.md#m3-canonization-contamination--partial) · [03 §9.7.9](03_MULTIVERSE_MODEL.md#979-residual-open-requires-df3-detail-or-external-input) |
| M4-D1 | Cascade-impact preview before L1/L2 edit | 2026-04-23 | **Modal required** before commit: shows `N realities will see this / M realities overridden (won't see)` + breakdown by status (active/frozen/archived) + per-reality drill-down (override event_id, timestamp, current L3 value). | [03 §9.8.1](03_MULTIVERSE_MODEL.md#981-preview-before-l1l2-edit-m4-d1) |
| M4-D2 | Default propagation = passive read-through | 2026-04-23 | **No forced rewrite** by default. Cascade rule (§3 + §6) handles: non-overriding realities see new L1/L2 on next read; overriding realities keep their L3 (correct by multiverse design). Safe non-destructive default. | [03 §9.8.2](03_MULTIVERSE_MODEL.md#982-default--passive-read-through-m4-d2) |
| M4-D3 | Optional force-propagate with 3-gate consent | 2026-04-23 | **Destructive, opt-in only**. Writes compensating L3 event in each overriding reality. Requires: (a) explicit opt-in at edit time, (b) reality-owner consent per reality, (c) R13 `admin_override` audit event. Scope-limited: author classifies as `canon_correction` / `typo_fix` / `continuity_error`. Reality-owner veto retained. Affected players notified. | [03 §9.8.3](03_MULTIVERSE_MODEL.md#983-optional-force-propagate-m4-d3) |
| M4-D4 | L1 axiomatic edit warnings | 2026-04-23 | **Pre-commit warning**: `N realities have L3 events conflicting with this new L1 axiom` + list conflicting events per reality. Author must acknowledge. Post-commit: runtime canon-guardrail flags/rejects future conflicting L3 writes; existing conflicts remain historical but canonically void. | [03 §9.8.4](03_MULTIVERSE_MODEL.md#984-l1-axiomatic--louder-warnings-m4-d4) |
| M4-D5 | xreality event channel reuse | 2026-04-23 | Reuse **R5-L2 infrastructure** (no new plumbing). `xreality.canon.updated` event on author edit; payload `{book_id, attribute_path, old_value, new_value, canon_layer, propagation_mode}`; meta-worker updates `reality_registry.last_canon_sync_at`; force-propagate orchestrated via R7 event-handler patterns. | [03 §9.8.5](03_MULTIVERSE_MODEL.md#985-xreality-event-channel-reuse-m4-d5) |
| M4-D6 | Glossary entity change timeline | 2026-04-23 | **Author history view** per attribute: "Author changed {attr} X→Y at {ts}" + "Applied to N / M overridden" + per-reality drill-down (override event_id, current L3, last_canon_sync_at). Reuses M3-D6 attribution pattern. | [03 §9.8.6](03_MULTIVERSE_MODEL.md#986-glossary-entity-change-timeline-m4-d6) |
| M4→status | M4 status change | 2026-04-23 | **M4 moves `OPEN` → `PARTIAL`** (01) and `MITIGATED` (03 §11). Author-safety UX framework locked; compensating L3 schema + notification copy + ownerless-reality consent + L1 guardrail prompt remain DF3/governance details. | [01 §M4](01_OPEN_PROBLEMS.md#m4-inconsistent-l1l2-updates-across-reality-lifetimes--partial) · [03 §9.8.7](03_MULTIVERSE_MODEL.md#987-residual-open-requires-df3--governance-detail) |
| M2→status | M2 status confirm | 2026-04-23 | **M2 confirmed `PARTIAL` with `MITIGATED` in 03 §11**. All mitigation layers already locked (MV10/MV11/R9-L6/MV4-b/M1-D5). Stays `PARTIAL` in 01 for platform-mode tier quota (deferred to `103_PLATFORM_MODE_PLAN.md`). | [01 §M2](01_OPEN_PROBLEMS.md#m2-storage-cost-of-inactive-realities--partial) · [03 §11.M2](03_MULTIVERSE_MODEL.md#m2-storage-cost-of-many-inactive-realities--mitigated) |
| M5→status | M5 status confirm | 2026-04-23 | **M5 confirmed `PARTIAL` with `MITIGATED` in 03 §11**. All mitigation layers already locked (MV9 auto-rebase at N=5 + projection flattening + R4-L5 ops metrics). Stays `PARTIAL` in 01 for threshold tuning (needs V1 data). | [01 §M5](01_OPEN_PROBLEMS.md#m5-fork-depth-explosion--partial) · [03 §11.M5](03_MULTIVERSE_MODEL.md#m5-fork-explosion-depth--mitigated) |
| A5-D1 | 3-intent classifier routing | 2026-04-23 | **Player input classified into command / fact question / free narrative** before any LLM call. Cheap classifier (regex for commands + NLI/rules for fact questions). Misclassification cost bounded: commands retry, fact-miss → LLM fallback + audit. | [05 §2](05_LLM_SAFETY_LAYER.md#2-three-intent-classifier-a5-d1) |
| A5-D2 | Command syntax + deterministic dispatch | 2026-04-23 | `/verb target [args]` MUD pattern. `world-service` validates + writes L3 event + updates projection (per R7 single-writer) BEFORE LLM narrates. State written first, narration second — narration failure never leaves partial state. | [05 §3.1–3.2](05_LLM_SAFETY_LAYER.md#3-command-dispatch-a5) |
| A5-D3 | LLM tool-call allowlist | 2026-04-23 | **Hard rule**: LLM tool-calls allowed ONLY for non-mutating flavor actions (whisper, gesture, reveal_emotion, look_at, recall_memory). State-changing actions (take, drop, attack, heal, move, kill, give, any inventory/HP/world-state mutation) MUST come from client `/verb` commands, NEVER from LLM output. Enforced at world-service dispatch layer. | [05 §3.3](05_LLM_SAFETY_LAYER.md#33-llm-tool-calls--allowed-vs-forbidden-a5-d3) |
| A5-D4 | Tool-call failure policy | 2026-04-23 | On allowed flavor tool-call failure: revert any partial effect + audit `npc.tool_call_failed` + narrator fallback prose ("Elena seems distracted" / "Elena trails off"). No retry. Never expose failure reason to player. | [05 §3.4](05_LLM_SAFETY_LAYER.md#34-tool-call-failure-policy-a5-d4) |
| A3-D1 | World Oracle API | 2026-04-23 | `oracle.query(reality_id, pc_id, key, context_cutoff) → (answer, confidence, source_events)` — deterministic: same input → same answer always. Hosted by `world-service`. | [05 §4.1](05_LLM_SAFETY_LAYER.md#41-api-a3-d1) |
| A3-D2 | Pre-computed fact categories | 2026-04-23 | Oracle pre-computes 5 categories: `entity_location`, `entity_relation`, `L1_axiom`, `book_content`, `world_state_kv`. Cached at reality creation, invalidated on L3 events touching key, pre-warmed on invalidation for hot keys. | [05 §4.2](05_LLM_SAFETY_LAYER.md#42-pre-computed-fact-categories-a3-d2) |
| A3-D3 | Fact-question routing + miss fallback | 2026-04-23 | Intent classifier (A5-D1) routes fact questions to Oracle. **Miss path**: audit-log `oracle.classifier_miss` + LLM fallback with canon retrieval. Miss rate feeds V1 tuning of classifier + Oracle key coverage. Canon-drift detector (G3) monitors miss-path answers for divergence. | [05 §4.3](05_LLM_SAFETY_LAYER.md#43-fact-question-routing-a3-d3) |
| A3-D4 | `context_cutoff` for PC timeline visibility | 2026-04-23 | Oracle filters facts by the PC's timeline cutoff. Prevents spoilers (PC can't learn events post-cutoff) AND prevents cross-PC leaks (other PCs' private memory not in this PC's Oracle scope). **Structural, not prompt-level** — even perfect jailbreak cannot extract what Oracle didn't return. | [05 §4.4](05_LLM_SAFETY_LAYER.md#44-timeline-cutoff--per-pc-visibility-a3-d4) |
| A6-D1 | Layer 1 input sanitization | 2026-04-23 | Normalize whitespace, strip zero-width chars (U+200B..U+200D, U+FEFF), detect known jailbreak patterns → quote inside `<user_input>` delimiter + audit-log `npc.suspicious_input` with flagged pattern. **Do not reject** — let downstream layers handle. | [05 §5.1](05_LLM_SAFETY_LAYER.md#51-layer-1--input-sanitization-a6-d1) |
| A6-D2 | Layer 2 hard server-side delimiters | 2026-04-23 | Prompt template is server-side, compiled with fixed tokens `<system>` / `<user_input from="..." sanitized="true">` / `<npc_response>`. Delimiters never user-controlled; escape-on-detection for nested delimiters. | [05 §5.2](05_LLM_SAFETY_LAYER.md#52-layer-2--hard-delimiters-in-prompt-a6-d2) |
| A6-D3 | Layer 3 canon-scoped retrieval (primary structural defense) | 2026-04-23 | **THE critical layer**. Retrieval filtering BEFORE LLM: retrieval query filters by `(pc_id, timeline_cutoff, reality_id)` at DB. Forbidden facts (other PCs' private memory, other sessions, other realities, spoilers) NEVER enter LLM context. Jailbreak cannot leak what isn't there. | [05 §5.3](05_LLM_SAFETY_LAYER.md#53-layer-3--canon-scoped-retrieval-a6-d3--critical) |
| A6-D4 | Layer 4 output filter | 2026-04-23 | Post-LLM classifier (cheap model / rules). 4 checks: persona-break (soft fail → 1 retry with stricter prompt, then fallback "Elena pauses, distracted"), **cross-PC leak (hard fail → block + audit `npc.output_blocked` + admin alert)**, spoiler (hard fail), NSFW/abuse (per platform policy). | [05 §5.4](05_LLM_SAFETY_LAYER.md#54-layer-4--output-filter-a6-d4) |
| A6-D5 | Layer 5 per-PC retrieval isolation at DB | 2026-04-23 | Per-PC memory access requires `(npc_id, pc_id)` match enforced at DB/service layer. V1: service-layer filter in knowledge-service retrieval API (reject query missing explicit `pc_id`). V2+: add Postgres RLS as defense-in-depth. Integration test mandatory: query without `pc_id` must error; query with wrong `pc_id` must return zero rows. | [05 §5.5](05_LLM_SAFETY_LAYER.md#55-layer-5--per-pc-retrieval-isolation-at-db-layer-a6-d5) |
| A3/A5/A6→status | LLM Safety Layer status change | 2026-04-23 | **A3 moves `OPEN` → `PARTIAL`**; A5 + A6 remain `PARTIAL` with framework formalized via [05_LLM_SAFETY_LAYER.md](05_LLM_SAFETY_LAYER.md). Residual: classifier accuracy, tool-call per-model benchmark, output filter calibration, novel jailbreak classes (ongoing ops). A category batch fully closed: A1–A6 all PARTIAL. | [01 §A3/A5/A6](01_OPEN_PROBLEMS.md#a-llm-reasoning--grounding) · [05 §8](05_LLM_SAFETY_LAYER.md#8-what-this-resolves-from-01_open_problems) |

---

## MV5 primitives — what must be locked now to avoid painful retrofit

Cross-reality travel is deferred, but these schema/protocol primitives cannot be added later without migration pain across all reality DBs. Must exist from V1 even if unused:

| # | Primitive | Why can't defer | Status |
|---|---|---|---|
| P1 | **Reality has `locale` field** (`en`, `vi`, `zh`, ...) | Travel between realities of different languages will need locale-aware display. Adding a locale to existing realities later = complex backfill. | **Must add to `reality_registry`** |
| P2 | **All PC/NPC/Item IDs are globally unique UUIDs** | Travel requires disambiguating entities across realities. UUID gives this for free. | Already planned ✓ |
| P3 | **Meta `player_character_index` tracks `(user_id, pc_id, reality_id)`** | One user, multiple PCs across realities. Future travel needs to surface "your PCs across all realities." | Already planned ✓ |
| P4 | **Event metadata has optional `travel_origin_reality_id` + `travel_origin_event_id`** | If a future event is "PC arrived from travel," the origin must be audit-traceable. Reserving the metadata keys now is zero-cost; adding later requires every consumer to handle both old and new formats. | **Must add to event metadata schema (optional fields, ignored in V1)** |
| P5 | **Items have `origin_reality_id` (nullable)** | Future travel carrying an item needs to know where the item was minted. Nullable = non-breaking. Adding later = migration through all projection + events of all realities. | **Must add to inventory projections** |
| P6 | **World clock is per-reality** | Each reality has its own in-world time. Travel crosses "time zones." Already planned but reinforce: do NOT share a global world clock. | Already planned ✓ |
| P7 | **NPC memory is reality-scoped (not global per glossary entity)** | NPC Elena's memory of PC Alice differs per reality (Elena-R1 and Elena-R2 are "same character, different experiences"). Already reality-scoped via DB-per-reality. | Already planned ✓ |
| P8 | **Canon lock level per attribute** | Travel may carry attributes that are L1 (globally fixed) or L2 (reality-local). Future code needs to know which travels, which doesn't. | Already planned via `canon_lock_level` ✓ |

**Not strictly required but highly recommended:**

| # | Primitive | Note |
|---|---|---|
| P9 | Currency / token abstraction | If future travel enables cross-reality trade, separating "in-world currency" from "platform currency" helps. Not critical for V1. |
| P10 | Entity "portability" flags | Per entity type (PC, item, knowledge), mark whether it is "travelable" in principle. Schema-free in V1 — add as JSONB field later. Skip for now. |

These 8 locked primitives (P1–P8) ensure that when world-travel feature is designed later, the schema doesn't need painful ALTERs across every reality DB.

---

---

## Deferred big features (DF1–DF13, DF12 withdrawn)

Features identified during design discussions that are not yet designed but are **known to be needed**. Each requires its own design doc when touched. Listed here so they don't get lost.

| ID | Feature | Surfaced in | Covers decisions |
|---|---|---|---|
| **DF1** | Daily Life / "Sinh hoạt" — offline PC/NPC behavior, daily routines, NPC-conversion mechanics, reclaim UX | [04_PC §4](04_PLAYER_CHARACTER_DESIGN.md) | PC-B2, PC-B3, partial C-PC2, links to [01 B3](01_OPEN_PROBLEMS.md#b3-world-simulation-tick--open) |
| **DF2** | Monetization / PC slot purchase | [04_PC §5.1](04_PLAYER_CHARACTER_DESIGN.md) | PC-C1 extension |
| **DF3** | Canonization / Author Review Flow — L3→L2 promotion, diff UI, IP attribution | [03 §3, 04 §7](04_PLAYER_CHARACTER_DESIGN.md) | MV2 details, PC-E1, PC-E2, links to [01 E3](01_OPEN_PROBLEMS.md#e3-ip-ownership--open) and [§M3](01_OPEN_PROBLEMS.md#m-multiverse-model-specific-risks) |
| **DF4** | World Rule feature — per-reality rule engine (death, paradox tolerance, PvP, canon strictness) | [04 §7](04_PLAYER_CHARACTER_DESIGN.md) | PC-B1 details, PC-D2 consent, PC-E3, A-PC3 runtime enforcement |
| **DF5** | Session / Group Chat feature — multi-character scene, turn arbitration, PvP, message routing | [04 §6](04_PLAYER_CHARACTER_DESIGN.md) | PC-D1, PC-D2, PC-D3; sibling to [98_CHAT_SERVICE_DESIGN.md](../98_CHAT_SERVICE_DESIGN.md) |
| **DF6** | World Travel — cross-reality PC travel, state transfer policy, entity identity | [OPEN_DECISIONS §MV5 primitives](OPEN_DECISIONS.md) | MV5, partial A-PC3 |
| **DF7** | PC Stats & Capabilities (small) | [04 §5.3](04_PLAYER_CHARACTER_DESIGN.md) | PC-C3 concrete schema |
| **DF8** | NPC persona generation from PC history | [04 §4, §5.2](04_PLAYER_CHARACTER_DESIGN.md) | PC-B3 NPC-conversion, PC-C2 persona semantics; may merge into DF1 |
| **DF9** | Event + Projection + Publisher + NPC Memory Ops — admin UX for: rebuild dashboard, manual triggers, drift reports, schema migration planner, rolling orchestrator, publisher health per shard/partition, dead-letter queue review (replay/skip/manual-publish), partition assignment editor, NPC memory size dashboard, manual compaction trigger, archive/restore controls, memory content inspector | [02 §12B.7, §12F.12, §12H.14](02_STORAGE_ARCHITECTURE.md) | Admin UX over §12B (rebuild/integrity) + §12F (publisher reliability) + §12H (NPC memory ops) mechanisms; algorithms locked in those sections |
| **DF10** | Event Schema Tooling — registry viewer, upcaster test harness, codegen CLI (`eventgen`), deprecation dashboard, cross-service schema sync verifier, docs auto-generation | [02 §12C.11](02_STORAGE_ARCHITECTURE.md) | Dev UX + CI integration around R3 mechanisms; mechanisms locked in §12C |
| **DF11** | Database Fleet + Reality Lifecycle Management — shard health dashboard, per-reality DB inspector, migration status board, backup verification dashboard, orphan resolution workflow, capacity planner, shard rebalance planner, **closure queue + state timeline + verification viewer + double-approval workflow + emergency cancel controls** | [02 §12D.11, §12I.14](02_STORAGE_ARCHITECTURE.md) | Ops UI wrapping R4 + R9 mechanisms; platform-wide fleet + per-reality lifecycle (distinct from DF9 per-reality correctness) |
| ~~DF12~~ | ~~Cross-Reality Analytics & Search~~ | — | **WITHDRAWN** (see R5-DF12 in decisions log); no justifying product feature. Slot left as tombstone for audit trail. |
| **DF13** | Cross-Session Event Handler — event handler health dashboard, cursor lag per reality, session event queue inspector, scope distribution analytics, manual propagation trigger, queue replay | [02 §12G.13](02_STORAGE_ARCHITECTURE.md) | Admin + dev UX for §12G mechanisms; different from DF9 (publisher) — DF9 broadcasts to clients, DF13 routes between sessions |

These features are NOT gates for current design docs (02, 03, 04). They are gated by their own future design. Each should get its own numbered doc when work begins.

---

## How to answer

When you're ready to answer items, you can:
- Say "lock #S2 = pgvector" (or whichever)
- Say "default is fine for #MV4, #MV6, #MV8"
- Say "let's discuss #A1" (I'll open the deep dive on that one)
- Say "design DFX now" (I'll start a new design doc for that big feature)

Mix is fine. Batches are fine. One at a time is fine.
