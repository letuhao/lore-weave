<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: 00_overview_and_schema.md
byte_range: 0-34183
sha256: fdb0076bd23a059318a7c680ff15929c14b2936c4d89d728143d08b382395970
generated_by: scripts/chunk_doc.py
-->

# 02 — Storage Architecture

> **Status:** Exploratory design — locks two decisions, leaves others open. Risks listed for separate discussion.
> **Scope:** Physical persistence of world state for the LLM MMO RPG. Does not cover canonical data (book / glossary / knowledge — those are owned by existing services).
> **Created:** 2026-04-23
> **Superseded in framing by:** [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) — the conceptual model that sits above this engineering baseline. The word "instance" used throughout this document corresponds to **"reality"** in the multiverse model. There is no privileged "root reality"; every reality is a peer universe. See [03 §1–3](03_MULTIVERSE_MODEL.md) for the conceptual framing and [03 §8](03_MULTIVERSE_MODEL.md) for schema adjustments (notably: every events/projection row gains a `reality_id` column).

---

## 1. Decisions locked

| # | Decision | Chosen |
|---|---|---|
| 1 | Event sourcing mode | **Full event sourcing** — events are SSOT, state rows are materialized projections rebuildable from the event log |
| 4 | Reality isolation | **1 DB per reality subtree** — each reality (or subtree after a DB split) gets its own Postgres database; a thin "meta registry" DB tracks them all |
| — | Fork semantics | **Snapshot fork** (locked separately in 03) — peer realities, no live inheritance between them |
| — | Model name | **Multiverse** (peer realities, no root) |

The remaining decisions (#2 embedding storage, #3 Redis durability, #5 event log partitioning, #6 hot state durability) are parked as `TBC`. All pending items live in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

## 2. Why these two together

- **Full event sourcing** = every state change is an immutable event. Projections (state rows) are derived. Rebuildable. Replayable. Audit for free.
- **1 DB per reality** = blast radius of a corrupt projection is one reality. Rebuild one reality without touching the rest. No cross-reality joins ever. Combined with snapshot fork: child realities physically co-host with parent until subtree reaches split threshold, then spin off to their own DB.

They reinforce each other: event sourcing without isolation creates a single event stream that becomes a global bottleneck and a scary rebuild target. Isolation without event sourcing means each reality is just a small CRUD database — less interesting. Together: each reality is a self-contained event-sourced universe, and the multiverse is a collection of these universes linked only by fork-point references.

## 3. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                   world-service (Go)   roleplay-service (Python)    │
└─────────────────┬───────────────────────────────────┬───────────────┘
                  │ write command                     │ LLM orchestration
                  ▼                                   │
    ┌─────────────────────────────┐                   │
    │   Command handler           │                   │
    │   - validate                │                   │
    │   - load aggregate          │                   │
    │   - emit event(s)           │                   │
    │   - append to event log     │                   │
    │   - update projection       │                   │
    │   - publish to stream       │                   │
    └──────┬────────────┬─────────┘                   │
           │            │                             │
           │  same tx   │                             │
           ▼            ▼                             ▼
    ┌────────────┐  ┌────────────┐       ┌───────────────────────┐
    │ events     │  │ projections│       │  Redis Streams        │
    │ (append)   │  │ (materialized view)│  per-instance topics  │
    │            │  │ - pc, npc, │       │  - broadcast fanout   │
    │ snapshots  │  │   region,  │       │  - WS consumers       │
    │            │  │   kv, inv, │       │  - projection workers │
    │            │  │   memory   │       │    (if async mode)    │
    └────────────┘  └────────────┘       └───────────────────────┘
          ▲               ▲
          │               │  same database
          └───────┬───────┘
                  │
          ┌───────┴──────────────────┐
          │  Postgres DB per-instance│   (loreweave_world_<instance_id>)
          └──────────────────────────┘

          ┌──────────────────────────┐
          │  Postgres meta registry  │   (loreweave_world_registry)
          │  - instances             │
          │  - connection routing    │
          │  - schema version per DB │
          │  - user→instance PCs     │
          └──────────────────────────┘

          ┌──────────────────────────┐
          │  Object storage (MinIO)  │
          │  - archived event parts  │
          │  - periodic snapshots    │
          └──────────────────────────┘
```

## 4. Event sourcing model

### 4.1 Aggregates

An **aggregate** is a unit of consistency — all events for one aggregate are totally ordered, and commands against it are serialized. Every state change in the world belongs to exactly one aggregate.

| Aggregate type | Purpose | Typical event rate |
|---|---|---|
| `pc` | Player character — position, inventory, stats, relationships | Medium (active only when player online) |
| `npc` | NPC proxy — mood, location, per-PC memory | High (every interaction with any player) |
| `region` | Region state — items on floor, ambient events, weather | Low–Medium |
| `world` | Instance-global state — clock, global quests, world events | Low |

A "conversation turn" typically emits events against multiple aggregates — e.g., `pc.say`, `npc.hear`, `region.log` — but each event is scoped to one aggregate.

### 4.2 Event envelope

Every event has the same envelope regardless of type:

```sql
CREATE TABLE events (
  event_id          BIGSERIAL,
  reality_id        UUID NOT NULL,             -- per-reality scoping (multiverse model, 03)
  aggregate_type    TEXT NOT NULL,             -- 'pc' | 'npc' | 'npc_session_memory' | 'npc_pc_memory' (legacy) | 'region' | 'world'
  aggregate_id      UUID NOT NULL,
  aggregate_version BIGINT NOT NULL,           -- monotonic per (reality, aggregate); for optimistic concurrency
  event_type        TEXT NOT NULL,             -- 'pc.say', 'npc.mood_shifted', 'region.item_dropped', ...
  event_version     INT  NOT NULL DEFAULT 1,   -- schema version of this event type
  payload           JSONB NOT NULL,
  metadata          JSONB NOT NULL,            -- actor, causation_id, correlation_id, timestamp, source

  -- §12S security additions (2026-04-24):
  session_id          UUID,                     -- NULL for non-session events (region/reality-scope)
  visibility          TEXT NOT NULL DEFAULT 'public_in_session',
    -- 'public_in_session' | 'whisper' | 'npc_internal' | 'region_broadcast' | 'reality_broadcast'
  whisper_target_type TEXT,                     -- 'pc' | 'npc' | NULL (only if visibility='whisper')
  whisper_target_id   UUID,                     -- target PC or NPC id (only if visibility='whisper')
  cascade_policy      TEXT NOT NULL DEFAULT 'inherit',
    -- 'inherit' | 'not_inherit' | 'expire_at_fork' (V2+)
  privacy_level       TEXT NOT NULL DEFAULT 'normal',
    -- 'normal' | 'sensitive' | 'confidential'
  privacy_metadata    JSONB,                    -- future extension hook

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (reality_id, aggregate_type, aggregate_id, aggregate_version)
);

-- §12S integrity constraints
ALTER TABLE events ADD CONSTRAINT events_whisper_has_target
  CHECK (visibility != 'whisper' OR (whisper_target_type IS NOT NULL AND whisper_target_id IS NOT NULL));
ALTER TABLE events ADD CONSTRAINT events_privacy_cascade_consistency
  CHECK (privacy_level = 'normal' OR cascade_policy = 'not_inherit');

-- Global append ordering within the DB (for stream tailing, projection replay, analytics)
CREATE UNIQUE INDEX events_event_id_idx ON events (event_id);

-- Hot reads per (reality, aggregate)
CREATE INDEX events_reality_aggregate_idx ON events (reality_id, aggregate_type, aggregate_id, aggregate_version);

-- Time-range archive
CREATE INDEX events_created_at_idx ON events (created_at);

-- Cascading ancestor reads (bounded by fork_point_event_id in reality_registry)
CREATE INDEX events_reality_event_idx ON events (reality_id, event_id);
```

**Why `(reality_id, aggregate_type, aggregate_id, aggregate_version)` is the PK:**
- Enforces monotonic versioning per (reality, aggregate) (duplicate version = constraint violation = concurrency conflict)
- Natural ordering for replay of one aggregate in one reality
- Reality scoping ensures snapshot-fork isolation — events from sibling realities never collide
- Cascading reads filter by `reality_id IN (ancestor chain)` + `event_id <= fork_point` per ancestor (see [03 §7](03_MULTIVERSE_MODEL.md))

**`event_version`:** schema version of the event *type*, not the aggregate. Allows evolving `pc.say` v1 → v2 without rewriting history. Upcasters convert old events to latest schema on read.

### 4.3 Metadata contract

The `metadata` JSONB holds cross-cutting concerns every event carries:

```json
{
  "actor": {
    "type": "user" | "system" | "npc",
    "id": "uuid"
  },
  "causation_id": "event_id of the event that caused this one",
  "correlation_id": "a saga/turn-level grouping",
  "source": "world-service" | "roleplay-service" | "admin-tool",
  "occurred_at": "2026-04-23T10:15:30.123Z",
  "instance_clock_tick": 12345
}
```

`correlation_id` is how we group "one player turn" — which typically spans 3-5 events across multiple aggregates.

### 4.4 Command flow (write path)

```
1. Command arrives ("player X says 'hello' to NPC Y in region Z")
2. Validate command against projection (cheap read — is X in Z? is Y in Z?)
3. BEGIN TRANSACTION
     a. SELECT aggregate_version FROM aggregate_version_index
        WHERE aggregate_type = 'pc' AND aggregate_id = X FOR UPDATE
     b. INSERT event pc.say (version = prev + 1)
     c. INSERT event npc.hear (version = prev_npc + 1)
     d. INSERT event region.log (version = prev_region + 1)
     e. Update projections in same transaction (see §5)
     f. LISTEN/NOTIFY to realtime stream
   COMMIT
4. Stream consumer broadcasts to WebSocket subscribers
```

**Concurrency:** if step (a) shows `version` ≠ expected, the command retries. Classic optimistic concurrency. In practice almost all PC/region aggregates have low contention; only hot NPCs get contention, addressed in §9.

### 4.5 Why full event sourcing pays off here

For a *normal* CRUD app, full event sourcing is usually overkill. For this MMO it is load-bearing:

- **Replay = regenerate narrative.** We can replay a session from any point — "show me what happened in the tavern between 10:00 and 10:05 from Player A's POV" is a projection query over events, not custom code.
- **Canon-drift audit.** Every NPC utterance is an event with the full prompt + retrieved context in its payload. When an NPC says something wrong, we have the forensic trail without adding logging.
- **Time-travel debugging.** Crash mid-turn? Replay events up to just before the crash on a clone DB. Reproduce.
- **Rollback per instance.** Corrupt an instance by pushing a bad quest? Rewind to a snapshot + replay events up to a chosen point. Other instances untouched.
- **Future migration safety.** When the schema changes, projections rebuild from events. No "migration script that sort of works."

### 4.6 Sync vs async projection — start sync

Projections can be updated (a) in the same transaction as the event append, or (b) asynchronously by a worker tailing the event stream.

**V1 decision: synchronous, in-transaction.** The event append and the projection update commit together. Reads are strongly consistent. No projection lag window.

The cost: every write does 2x work (append event + update projection). For LoreWeave's turn rate (low hundreds/sec at scale), this is well under Postgres's throughput budget.

**Later (V3, if needed): async projections.** When write volume forces throughput above ~2K events/sec sustained per instance, split projection update into a separate worker that consumes from the event stream. Accept eventual consistency on reads, gain write throughput.

Deferring async keeps V1 simple and removes an entire class of bugs (stale reads, out-of-order projection updates).

## 5. Projections

Each aggregate type has one or more **projection tables** — denormalized, query-optimized views of current state. These are the tables the app actually reads from for rendering.

### 5.1 PC projection

```sql
CREATE TABLE pc_projection (
  pc_id             UUID PRIMARY KEY,
  user_id           UUID NOT NULL,
  name              TEXT NOT NULL,
  current_region_id UUID NOT NULL,
  status            TEXT NOT NULL,
  stats             JSONB NOT NULL DEFAULT '{}',
  last_event_version BIGINT NOT NULL,           -- tracks projection lag (only meaningful in async mode)
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON pc_projection (current_region_id);
CREATE INDEX ON pc_projection (user_id);

CREATE TABLE pc_inventory_projection (
  pc_id              UUID NOT NULL REFERENCES pc_projection,
  item_code          TEXT NOT NULL,
  quantity           INT NOT NULL,
  metadata           JSONB,
  origin_reality_id  UUID,              -- P5 (MV5 primitive): reality where item was minted.
                                        -- Nullable in V1 — unused until world-travel feature.
                                        -- Defaults to current reality on insert.
  PRIMARY KEY (pc_id, item_code)
);

CREATE TABLE pc_relationship_projection (
  pc_id              UUID NOT NULL REFERENCES pc_projection,
  other_entity_type  TEXT NOT NULL,             -- 'npc' | 'pc'
  other_entity_id    UUID NOT NULL,
  score              INT NOT NULL DEFAULT 0,
  labels             TEXT[] NOT NULL DEFAULT '{}',  -- 'friend', 'rival', 'debt'
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (pc_id, other_entity_type, other_entity_id)
);
```

### 5.2 NPC projection

```sql
CREATE TABLE npc_projection (
  npc_id             UUID PRIMARY KEY,
  glossary_entity_id UUID NOT NULL,             -- canonical source, read-only ref to glossary-service
  current_region_id  UUID,
  mood               TEXT NOT NULL DEFAULT 'neutral',
  core_beliefs       JSONB NOT NULL DEFAULT '{}',   -- author-locked, never drifts
  flexible_state     JSONB NOT NULL DEFAULT '{}',   -- LLM-drifted, instance-local
  last_event_version BIGINT NOT NULL,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON npc_projection (current_region_id);
CREATE INDEX ON npc_projection (glossary_entity_id);

-- ⚠ SUPERSEDED by §12S.2 (session-scoped model, 2026-04-24).
-- The two tables below are NOT in current design. Kept in doc for audit trail only.
-- Current design: npc_session_memory_projection + npc_pc_relationship_projection + npc_session_memory_embedding (see §12S.2.3, §12S.2.4).

-- ~~CREATE TABLE npc_pc_memory_projection (...) — REPLACED~~
-- ~~CREATE TABLE npc_pc_memory_embedding (...) — REPLACED~~

-- Current projections per §12S.2:
CREATE TABLE npc_session_memory_projection (
  npc_id                UUID NOT NULL,
  session_id            UUID NOT NULL,
  reality_id            UUID NOT NULL,
  aggregate_id          UUID NOT NULL,            -- uuidv5('npc_session_memory', npc_id || session_id)
  summary               TEXT,                      -- LLM-compacted session summary
  facts                 JSONB NOT NULL DEFAULT '[]',  -- structured facts from THIS session only
  session_started_at    TIMESTAMPTZ,
  session_ended_at      TIMESTAMPTZ,
  interaction_count     INT NOT NULL DEFAULT 0,
  last_event_version    BIGINT NOT NULL,
  archive_status        TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'faded' | 'summary_only' | 'archived'
  PRIMARY KEY (npc_id, session_id)
);
CREATE INDEX ON npc_session_memory_projection (archive_status, session_ended_at);

CREATE TABLE npc_pc_relationship_projection (
  npc_id                UUID NOT NULL,
  other_entity_id       UUID NOT NULL,
  other_entity_type     TEXT NOT NULL,            -- 'pc' | 'npc'
  reality_id            UUID NOT NULL,
  trust_level           INT NOT NULL DEFAULT 0,    -- -100 to +100
  familiarity_count     INT NOT NULL DEFAULT 0,   -- sessions shared
  last_session_id       UUID,
  last_interaction_at   TIMESTAMPTZ,
  relationship_labels   TEXT[] NOT NULL DEFAULT '{}',
  last_event_version    BIGINT NOT NULL,
  PRIMARY KEY (npc_id, other_entity_id)
);
CREATE INDEX ON npc_pc_relationship_projection (npc_id, familiarity_count DESC);

CREATE TABLE npc_session_memory_embedding (
  npc_id        UUID NOT NULL,
  session_id    UUID NOT NULL,
  embedding     vector(1536),
  content_hash  TEXT NOT NULL,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (npc_id, session_id)
);
CREATE INDEX npc_session_memory_embedding_hnsw
  ON npc_session_memory_embedding USING hnsw (embedding vector_cosine_ops);

-- Session participation tracking (foundation for capability-based access)
CREATE TABLE session_participants (
  session_id         UUID NOT NULL,
  reality_id         UUID NOT NULL,
  participant_type   TEXT NOT NULL,            -- 'pc' | 'npc'
  participant_id     UUID NOT NULL,
  joined_at          TIMESTAMPTZ NOT NULL,
  left_at            TIMESTAMPTZ,               -- NULL = still in session
  PRIMARY KEY (session_id, participant_type, participant_id)
);
CREATE INDEX session_participants_by_entity
  ON session_participants (participant_type, participant_id, session_id);
```

### 5.3 Region projection

```sql
CREATE TABLE region_projection (
  region_id         UUID PRIMARY KEY,
  code              TEXT NOT NULL,
  display_name      TEXT NOT NULL,
  description       TEXT,
  parent_region_id  UUID,
  exits             JSONB NOT NULL DEFAULT '[]',
  floor_items       JSONB NOT NULL DEFAULT '[]',   -- items visible in the room
  ambient_state     JSONB NOT NULL DEFAULT '{}',   -- weather, time-of-day, etc
  last_event_version BIGINT NOT NULL
);
```

### 5.4 World KV projection

```sql
CREATE TABLE world_kv_projection (
  key               TEXT PRIMARY KEY,
  value             JSONB NOT NULL,
  last_event_version BIGINT NOT NULL,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 5.5 Projection rebuild

Every projection has a deterministic `rebuild()` function: given the event stream, produce the projection from scratch.

```
rebuild_pc_projection(pc_id):
  TRUNCATE rows for pc_id
  FOR each event WHERE aggregate_type = 'pc' AND aggregate_id = pc_id ORDER BY aggregate_version:
    apply_event(event)
```

Rebuild triggers:
- Schema change to a projection (add column, change derivation logic)
- Projection corruption detected (checksum mismatch with expected event version)
- Manual admin command

For instance-scale rebuilds, expected time budget:
- 1M events in an instance, 10k events/sec rebuild rate → ~100 seconds
- Snapshots (§6) reduce rebuild time for hot aggregates

## 6. Snapshots

Full replay of every aggregate on every read is obviously untenable. Snapshots are **materialized checkpoints of aggregate state**, keyed by version.

```sql
CREATE TABLE aggregate_snapshots (
  aggregate_type     TEXT NOT NULL,
  aggregate_id       UUID NOT NULL,
  aggregate_version  BIGINT NOT NULL,
  state              JSONB NOT NULL,            -- full aggregate state
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (aggregate_type, aggregate_id, aggregate_version)
);
CREATE INDEX ON aggregate_snapshots (aggregate_type, aggregate_id, created_at DESC);
```

**Snapshot policy (V1):**
- Every aggregate: snapshot every **500 events** or **1 hour of in-world time**, whichever first
- Keep last 3 snapshots per aggregate (for rollback flexibility)
- Older snapshots pruned

**Why snapshots are not the SSOT:** the event log is. Snapshots are optimization; they can be dropped and rebuilt without data loss.

**Load-aggregate algorithm:**
```
load(aggregate_type, aggregate_id):
  snap = latest snapshot for (type, id)
  events = events for (type, id) WHERE version > snap.version
  return fold(snap.state, events)
```

## 7. Instance DB model

### 7.1 DB-per-instance layout

Each `world_instance` gets a dedicated Postgres database:

```
Database: loreweave_world_<instance_id>
Owner: service role with CRUD on all tables
Schemas:
  public → events, snapshots, projection tables
  (No cross-database references)
```

All tables described in §4–6 live inside that database. The instance database is self-contained: given its connection string, you have the entire instance's state.

### 7.2 Meta registry DB

One shared database tracks all instances:

```sql
-- Database: loreweave_world_registry

CREATE TABLE world_instance_registry (
  instance_id       UUID PRIMARY KEY,
  book_id           UUID NOT NULL,
  name              TEXT NOT NULL,
  status            TEXT NOT NULL,              -- 'provisioning' | 'active' | 'frozen' | 'closed'
  db_host           TEXT NOT NULL,              -- 'pg-shard-1.internal'
  db_name           TEXT NOT NULL,              -- 'loreweave_world_<instance_id>'
  schema_version    TEXT NOT NULL,              -- tracks which migration set applied
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_heartbeat_at TIMESTAMPTZ
);

-- Players across instances (fast lookup: "what PCs do I have?")
CREATE TABLE player_character_index (
  pc_id        UUID PRIMARY KEY,
  user_id      UUID NOT NULL,
  instance_id  UUID NOT NULL REFERENCES world_instance_registry,
  name         TEXT NOT NULL,
  last_seen_at TIMESTAMPTZ,
  status       TEXT NOT NULL
);
CREATE INDEX ON player_character_index (user_id);
CREATE INDEX ON player_character_index (instance_id);

-- Schema migration tracking across instance DBs
CREATE TABLE instance_schema_migrations (
  instance_id       UUID NOT NULL,
  migration_id      TEXT NOT NULL,
  applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (instance_id, migration_id)
);
```

### 7.3 Instance lifecycle

```
CREATE instance (UPDATED per H5/M-REV-5 — see [§12R.2](#12r2-reality-bootstrap-process--seeding-state--worker-h5--m-rev-5)):
  1. INSERT INTO world_instance_registry (status='provisioning')
  2. CREATE DATABASE loreweave_world_<instance_id>
  3. Run schema migrations (latest set)
  4. UPDATE registry SET status='seeding' (via §12Q CAS)
  5. Background worker (migration-orchestrator) seeds:
     - Initial regions from book-service (checkpoint every 100)
     - Initial NPC proxies from glossary-service
     - Translated content if reality.locale != book.source_locale (M-REV-5)
     - Snapshot initial state
  6. UPDATE registry SET status='active' (via §12Q CAS)
     Idempotent + resumable; retries on failure; admin intervention if stuck

FREEZE instance (no new writes, reads OK — for maintenance):
  1. UPDATE registry SET status='frozen'
  2. Command handlers reject writes for this instance

CLOSE instance — DEPRECATED as single step. See [§12I](#12i-safe-reality-closure-r9-mitigation)
  which supersedes this flow with a multi-stage 120+ day protocol:
  active → pending_close (30d cooling) → frozen → archived → archived_verified
    → soft_deleted (90d hold + double-approval) → dropped

  The naive 1-step close below is REJECTED:
    ~~1. Dump all events + final snapshots to MinIO~~
    ~~2. DROP DATABASE loreweave_world_<instance_id>~~
    ~~3. UPDATE registry SET status='closed', db_host=NULL, db_name=NULL~~
    ~~4. player_character_index rows retained for history~~

  See §12I for the safe flow.
```

### 7.4 App-level routing

```
request arrives with instance_id
  → lookup connection info in registry (cached)
  → get connection from per-instance pool
  → execute
```

Connection pool strategy: pool per instance, LRU eviction after 10 minutes of inactivity. Idle instances release their pool, reconnect on-demand.

### 7.5 Schema migrations across all instance DBs

Migrations are tricky with N databases. The workflow:

```
Apply migration M to all active instances:
  for each active instance:
    if M not in instance_schema_migrations:
      connect to instance DB
      execute migration SQL
      INSERT INTO instance_schema_migrations (instance_id, migration_id)

Resume-safe: any interrupted migration can be re-run (migrations must be idempotent).
Stagger: migrations run with concurrency limit (e.g., 10 at a time) to avoid overload.
```

Framework: any Postgres migration tool (goose, migrate, sqlx-migrate) driven by an orchestrator script. **Migrations must be backward-compatible** for at least one release — event schema changes are particularly sensitive.

### 7.6 Provisioning cost

Postgres can host thousands of databases per instance (~10K is a tested limit on a single Postgres server). For meaningful scale:
- V1 (1–100 instances): 1 Postgres server holds all instance DBs + registry
- V2 (100–1000 instances): shard by `instance_id` hash across 2–8 Postgres servers
- V3 (1000+ instances): 1 instance DB per Postgres may be needed for largest active instances; sharded clusters for long-tail

Registry tracks which physical server hosts each instance DB, so routing is straightforward.

## 8. Concurrency patterns

> **Superseded framing:** The multi-aggregate lock patterns in §8.2–§8.4 were designed assuming aggregate is the concurrency unit. After revised R7 analysis (see [§12G](#12g-session-as-concurrency-boundary--cross-session-event-handler-r7-mitigation)), **session is the actual concurrency unit** — intra-session writes are serial by design, eliminating deadlock concerns for most cases. §8.1 optimistic concurrency remains valid as defense-in-depth for cross-session collisions. §8.3 hot-NPC Redis busy lock remains valid as UX-level gate. §8.2 multi-aggregate lock order and §8.4 per-reality single-writer are **effectively obsolete** for production code paths — single-writer-per-session (§12G.2) supersedes both.

### 8.1 Optimistic concurrency on aggregate version

Standard event sourcing pattern. Each command specifies expected version; conflict = retry.

```go
// Pseudocode
func appendEvent(cmd Command) error {
  for retries := 0; retries < 3; retries++ {
    currentVersion := loadAggregateVersion(cmd.AggregateType, cmd.AggregateID)
    err := tx.Exec(`
      INSERT INTO events (...version...) VALUES (..., $currentVersion+1, ...)
    `)
    if err == ConcurrencyConflict {
      continue
    }
    return err
  }
  return ErrTooManyRetries
}
```

Postgres's unique constraint on `(aggregate_type, aggregate_id, aggregate_version)` gives us the conflict detection for free.

### 8.2 Multi-aggregate commands (the common case)

A turn touches pc + npc + region. Three aggregate version bumps, one transaction:

```sql
BEGIN;
  -- Lock PC version
  SELECT aggregate_version FROM events
    WHERE aggregate_type='pc' AND aggregate_id=$pc
    ORDER BY aggregate_version DESC LIMIT 1 FOR UPDATE;
  -- Same for npc, region
  ...
  -- Insert 3 events
  INSERT INTO events (...);
  INSERT INTO events (...);
  INSERT INTO events (...);
  -- Update 3 projections
  UPDATE pc_projection ...;
  UPDATE npc_projection ...;
  UPDATE region_projection ...;
COMMIT;
```

Lock order: `pc → npc → region` consistently to avoid deadlocks. Deadlock-retry at the app layer anyway.

### 8.3 Hot NPC contention

Popular NPCs (the tavern keeper everyone talks to) get write contention. Mitigations:

- **NPC "in conversation" lock (Redis):** `SETNX npc:{id}:busy pc_{id} EX 30`. If lock held, reject with "Elena is busy, wait or say to the room." This is a UX gate, not a DB gate.
- **Command serialization per NPC:** optional — route all commands for a hot NPC to a single worker queue. Throughput of that NPC = 1 worker's rate. Fine given LLM is 3–8s anyway.

### 8.4 Per-instance command serialization (if needed)

For V1 simplicity, a single command processor per instance is viable: all commands for one instance go through one goroutine, eliminating in-instance concurrency issues entirely. This is very cheap at LoreWeave turn rates.

Trade-off: single-writer per instance means the instance is limited to one machine. Fine until V3.

## 9. Realtime integration

### 9.1 Event publication

After COMMIT, publish to a per-instance Redis stream:

```
XADD instance:{instance_id}:events * event_id ... event_type ... payload ...
```

Consumers:
- **WebSocket fanout** — subscribers in a region consume events tagged with that region
- **Async projection workers** (future V3) — consume to update projections
- **Analytics ETL** — batch-consumes into ClickHouse

### 9.2 Publication + commit atomicity

Naive `COMMIT; XADD` has a gap: commit succeeds, app crashes before publishing, event is durable but not broadcast. Two mitigations:

- **Outbox pattern:** commit event + row in `events_outbox`. A publisher tails the outbox and pushes to Redis, deleting rows after confirmed push. Adds a table but makes publication crash-safe.
- **LISTEN/NOTIFY:** Postgres built-in. After COMMIT, `NOTIFY events_channel, event_id`. A listener pushes to Redis. Dies if the listener crashes and misses notifications in its down window.

**V1 choice:** outbox. Slightly more work, zero missed broadcasts.

```sql
CREATE TABLE events_outbox (
  event_id  BIGINT PRIMARY KEY REFERENCES events(event_id),
  published BOOLEAN NOT NULL DEFAULT FALSE,
  attempts  INT NOT NULL DEFAULT 0
);
CREATE INDEX ON events_outbox (published, event_id) WHERE published = FALSE;
```

Publisher reads unpublished rows, pushes, marks published.

## 10. Event schema versioning & upcasting

Event types evolve. The pattern:

```
pc.say v1: {"content": "..."}
pc.say v2: {"content": "...", "speech_act": "question"}   -- added field
```

**Rule:** never mutate old events. Instead, **upcast on read.**

```go
func upcast(e Event) Event {
  if e.EventType == "pc.say" && e.EventVersion == 1 {
    e.Payload["speech_act"] = inferFromContent(e.Payload["content"])
    e.EventVersion = 2
  }
  return e
}
```

Upcasters chain (v1 → v2 → v3 → current). Run on every event load. Projection rebuild always sees the latest schema.

**Hard rule:** never delete or rewrite events in the log. Changing history breaks replay guarantees.

## 11. Archive strategy

Events accumulate forever. Archive policy:

- **Hot (in Postgres):** last 90 days of events, all snapshots
- **Warm (Postgres, partitioned-detached):** events 90–365 days old, accessible but slower
- **Cold (MinIO):** events older than 365 days, compressed + per-month files, restore-on-demand
- **Closed instances:** complete archive to MinIO on close, DB dropped

```sql
-- Events table partitioned by month
CREATE TABLE events (...) PARTITION BY RANGE (created_at);
CREATE TABLE events_2026_04 PARTITION OF events FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
```

Monthly detach + archive job:
```
DETACH PARTITION events_2026_01 CONCURRENTLY;
pg_dump → s3://lw-archive/instances/<id>/events_2026_01.sql.gz
DROP TABLE events_2026_01;
```

Restore is rare but possible: dump back into Postgres with `ATTACH PARTITION`, available for replay/audit.

## 12. Capacity model

Baseline per active instance, assuming 500 concurrent players in one instance (a healthy MMO zone):

| Quantity | Estimate |
|---|---|
| Turns/sec | 500 users × 1 turn / 20s = 25 turns/sec |
| Events/turn | ~4 (pc, npc, region, outbox) |
| Events/sec | ~100 |
| Event row size | ~1 KB (payload + metadata) |
| Event volume / hour | ~360K rows, ~360 MB |
| Event volume / day | ~8.6M rows, ~8.6 GB |
| Projection update ops / sec | ~100 (one per event, in-transaction) |
| Postgres write TPS | ~200 (events + projection updates) |
| Postgres headroom | Commodity Postgres handles 5K–10K TPS; using 2–4% |

Bottleneck is **not DB**. It is LLM cost and latency. See [01_OPEN_PROBLEMS.md D1](01_OPEN_PROBLEMS.md#d1-llm-cost-per-user-hour--open).

Scale by replicating instance DBs across Postgres servers (§7.6). Any single instance bounded by one DB's throughput, which tolerates ~100× the projected V1 load.

