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
  aggregate_type    TEXT NOT NULL,             -- 'pc' | 'npc' | 'region' | 'world'
  aggregate_id      UUID NOT NULL,
  aggregate_version BIGINT NOT NULL,           -- monotonic per (reality, aggregate); for optimistic concurrency
  event_type        TEXT NOT NULL,             -- 'pc.say', 'npc.mood_shifted', 'region.item_dropped', ...
  event_version     INT  NOT NULL DEFAULT 1,   -- schema version of this event type
  payload           JSONB NOT NULL,
  metadata          JSONB NOT NULL,            -- actor, causation_id, correlation_id, timestamp, source
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (reality_id, aggregate_type, aggregate_id, aggregate_version)
);

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

-- Per-PC memory — each (npc_id, pc_id) pair is its own aggregate (see §12H).
-- Projection here; embedding lives in separate table (§12H.7).
CREATE TABLE npc_pc_memory_projection (
  npc_id              UUID NOT NULL,
  pc_id               UUID NOT NULL,
  aggregate_id        UUID NOT NULL,              -- uuidv5('npc_pc_memory', npc_id||pc_id)
  summary             TEXT,                        -- rolling LLM-generated (bounded §12H.3)
  facts               JSONB NOT NULL DEFAULT '[]', -- LRU-bounded to npc_memory.max_facts_per_pc
  last_interaction_at TIMESTAMPTZ,
  interaction_count   INT NOT NULL DEFAULT 0,
  last_summary_rewrite_at TIMESTAMPTZ,
  archive_status      TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'faded' | 'summary_only' | 'archived'
  last_event_version  BIGINT NOT NULL,
  PRIMARY KEY (npc_id, pc_id)
);
CREATE INDEX ON npc_pc_memory_projection (archive_status, last_interaction_at);

-- Embedding stored separately (§12H.6) — prevents snapshot bloat
CREATE TABLE npc_pc_memory_embedding (
  npc_id        UUID NOT NULL,
  pc_id         UUID NOT NULL,
  embedding     vector(1536),
  content_hash  TEXT NOT NULL,                   -- for change detection
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (npc_id, pc_id)
);
CREATE INDEX npc_pc_memory_embedding_hnsw
  ON npc_pc_memory_embedding USING hnsw (embedding vector_cosine_ops);
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
CREATE instance:
  1. INSERT INTO world_instance_registry (status='provisioning')
  2. CREATE DATABASE loreweave_world_<instance_id>
  3. Run schema migrations (latest set)
  4. Seed initial regions from book-service
  5. Seed initial NPC proxies from glossary-service (derive-only, no sync)
  6. UPDATE registry SET status='active'

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

## 12A. Event Volume Management (R1 mitigation)

Full event sourcing emits many writes. Multiverse isolation bounds scope per reality but does not reduce total platform volume. The following 6-layer strategy addresses event volume explosion (R1 in §13).

### 12A.1 Layer 1 — Audit split

Events are split into **two categories, two tables**:

**State events** (`events` table): small, permanent, drive projections. Size: 500B–2KB.
- `pc.said`, `pc.took`, `pc.moved`, `npc.said`, `npc.mood_shifted`, `region.item_dropped`
- Kept forever (canon narrative)

**Audit events** (`event_audit` table): large, bounded retention, forensic-only. Size: 5–20KB.
- Full prompt sent to LLM
- Retrieval results (entities + scores)
- LLM raw response
- Canon-lint check details
- Tokens used, model used

```sql
-- Lean core event log
CREATE TABLE events (
  event_id          BIGSERIAL,
  reality_id        UUID NOT NULL,
  aggregate_type    TEXT NOT NULL,
  aggregate_id      UUID NOT NULL,
  aggregate_version BIGINT NOT NULL,
  event_type        TEXT NOT NULL,
  event_version     INT NOT NULL DEFAULT 1,
  payload           JSONB NOT NULL,                -- lean state delta only
  metadata          JSONB NOT NULL,
  audit_ref         UUID,                          -- optional pointer to event_audit row
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (reality_id, aggregate_type, aggregate_id, aggregate_version)
) PARTITION BY RANGE (created_at);

ALTER TABLE events ALTER COLUMN payload SET COMPRESSION lz4;
ALTER TABLE events ALTER COLUMN metadata SET COMPRESSION lz4;

-- Bulk audit — short retention, aggressive cleanup
CREATE TABLE event_audit (
  audit_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id          BIGINT,                        -- FK to events (may be broken after events archived)
  reality_id        UUID NOT NULL,
  prompt_text       TEXT,                          -- assembled prompt sent to LLM
  retrieval_json    JSONB,                         -- what was retrieved and why
  llm_raw_response  TEXT,                          -- raw LLM output
  model_used        TEXT,
  tokens_input      INT,
  tokens_output     INT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);

ALTER TABLE event_audit ALTER COLUMN prompt_text SET COMPRESSION lz4;
ALTER TABLE event_audit ALTER COLUMN retrieval_json SET COMPRESSION lz4;
ALTER TABLE event_audit ALTER COLUMN llm_raw_response SET COMPRESSION lz4;

CREATE INDEX ON event_audit (reality_id, created_at);
CREATE INDEX ON event_audit (event_id);
```

**Rule:** projection rebuild only reads `events`. Debugging joins `event_audit` on demand. Archive schedules for `events` and `event_audit` are independent (§12A.4).

### 12A.2 Layer 2 — Event emission discipline

Not every happening deserves an event row. Strict rules for what gets persisted:

| Happening | Persist as event? | Audit row? |
|---|---|---|
| `pc.say` (player's input) | ✅ YES | ✅ YES (prompt context for future LLM audit) |
| `npc.hear` (NPC received someone's speech) | ❌ NO — derivable from `pc.say` + who's in region | — |
| `prompt.assembled` (LLM prompt composed) | ❌ NO as event | ✅ YES in audit (as part of next `npc.said` audit row) |
| `retrieval.completed` | ❌ NO as event | ✅ YES in audit |
| `llm.response` (raw) | ❌ NO as event | ✅ YES in audit |
| `npc.said` (processed NPC speech) | ✅ YES | ✅ YES (ties to the audit blob) |
| `npc.mood_shifted` | ✅ YES | ❌ NO |
| `pc.took` / `pc.dropped` / state changes | ✅ YES | ❌ NO |
| `region.broadcast_fanout` | ❌ NO — ephemeral fan-out over Redis | — |
| `canon_lint.result` | ❌ NO as state event | ✅ YES in audit (if warning triggered) |

Reduces events/turn from 7–8 → **2–3 core events**. Volume cut ~60% before other layers apply.

### 12A.3 Layer 3 — Tiered retention per event type

Not all events deserve the same lifetime. Policy per event_type, enforced by nightly cleanup job:

| Event class | Hot (Postgres) | Warm (detached partition) | Cold (MinIO) | Delete after |
|---|---|---|---|---|
| **Canon events** (`pc.said`, `npc.said`, `pc.took`, `npc.moved`, state-change) | 90 days | 90–365 days | 365+ days | Never |
| **Volatile NPC state** (`npc.mood_shifted` when tick-level) | 30 days | — | — | 30 days |
| **Canon-lint warnings** (audit) | 30 days | — | 30–90 days | 90 days |
| **Other audit rows** | 30 days | — | — | 30 days |
| **Broadcast fan-out** (if ever persisted) | 24 hours | — | — | 24 hours |

Nightly job per reality:
```
DELETE FROM events
WHERE reality_id = $this AND event_type IN ('npc.mood_shifted')
  AND created_at < NOW() - INTERVAL '30 days';

DELETE FROM event_audit
WHERE reality_id = $this AND created_at < NOW() - INTERVAL '30 days'
  AND event_id NOT IN (SELECT event_id FROM canon_flagged_events);
```

Config-driven retention values:

```
storage.retention.canon_events.hot_days = 90
storage.retention.canon_events.warm_days = 365
storage.retention.npc_mood_events.hot_days = 30
storage.retention.audit.hot_days = 30
storage.retention.audit.flagged_cold_days = 90
storage.retention.broadcast.hot_hours = 24
```

### 12A.4 Layer 4 — Tiered archive pipeline

Extends §11 with the multi-tier pipeline:

```
┌── HOT ──────────────────────────────────────┐
│  Postgres in-instance DB                    │
│  Last 90 days events + all snapshots        │
│  Full query + projection rebuild            │
│  Compressed (lz4) at column level           │
└───────────────┬─────────────────────────────┘
                │ nightly partition detach (every 7 days)
                ▼
┌── WARM ─────────────────────────────────────┐
│  Detached partitions, still in Postgres     │
│  90–365 days                                │
│  Attachable for forensic query              │
└───────────────┬─────────────────────────────┘
                │ yearly cold-move (or compaction threshold)
                ▼
┌── COLD ─────────────────────────────────────┐
│  MinIO bucket: lw-world-archive             │
│  Per-reality path: /<instance_id>/YYYY_MM/  │
│  Parquet format with ZSTD compression       │
│  5–10× compression vs JSONB                 │
│  Restore-on-demand (legal, audit, replay)   │
└─────────────────────────────────────────────┘
```

Archive job:
```
1. DETACH PARTITION events_2026_01 CONCURRENTLY;
2. COPY partition TO parquet_file WITH (COMPRESSION 'zstd');
3. Upload parquet to MinIO: s3://lw-world-archive/<reality_id>/2026_01/events.parquet
4. Verify checksum
5. DROP TABLE events_2026_01;
```

Same pipeline applies to `event_audit` but on its own schedule (shorter warm retention: audit rows rarely queried after 90 days).

### 12A.5 Layer 5 — Snapshot-then-truncate for non-canon aggregates

For aggregates that have a snapshot ≥ version V and zero recent access in last 180 days, old events ≤ V can be **permanently deleted** (after cold archive) **unless** they are canon events.

Canon events (`pc.said`, `npc.said`, `pc.took`, state-change) are NEVER deleted even after snapshot — they preserve narrative history for future canonization (DF3) and audit.

Non-canon events (ephemeral state ticks, transient flags) are eligible for post-snapshot truncation.

Algorithm per reality per month:
```
FOR each aggregate (type, id):
  snap = latest snapshot
  IF snap exists AND last_event_time_for_aggregate < NOW() - 180 days:
    DELETE FROM events
    WHERE reality_id = $this
      AND aggregate_id = agg_id
      AND aggregate_version <= snap.version
      AND event_type NOT IN (canon_event_types);
```

Result: hot storage stays bounded; canon preserved; non-canon clutter removed.

### 12A.6 Layer 6 — Compression

Postgres-level lz4 compression on JSONB columns (requires Postgres 14+):

```sql
-- Apply to all large-text columns
ALTER TABLE events ALTER COLUMN payload SET COMPRESSION lz4;
ALTER TABLE events ALTER COLUMN metadata SET COMPRESSION lz4;
ALTER TABLE event_audit ALTER COLUMN prompt_text SET COMPRESSION lz4;
ALTER TABLE event_audit ALTER COLUMN retrieval_json SET COMPRESSION lz4;
ALTER TABLE event_audit ALTER COLUMN llm_raw_response SET COMPRESSION lz4;
ALTER TABLE aggregate_snapshots ALTER COLUMN state SET COMPRESSION lz4;
```

lz4 vs default pglz:
- 2× better compression ratio
- Same read speed (often faster)
- Small write-CPU overhead (~3%)

For cold archive (MinIO), use ZSTD (higher ratio, slower — acceptable for rarely-read cold).

### 12A.7 Expected volume numbers

Per reality (100-player cap, 30 concurrent average):

| Stage | Daily volume | Annual (hot) |
|---|---|---|
| Baseline naive (pre-mitigation) | 2 GB/day | 730 GB |
| + L1 audit split (events table only) | 400 MB/day | 146 GB |
| + L2 event discipline (reduce events/turn) | 200 MB/day | 73 GB |
| + L3 tiered retention (prune non-canon >30d) | 150 MB/day effective | 55 GB |
| + L4 archive >90d to MinIO | ~1.5 GB Postgres hot-window total | — |
| + L6 lz4 compression on above | ~1 GB Postgres hot | — |

**Per-reality hot Postgres**: ~1 GB after 1 year. Warm partition: ~10 GB. MinIO cold: ~50 GB.

**Platform-wide (1000 active realities):**
- Hot Postgres: 1 TB total, well within single cluster
- MinIO cold: 50 TB — cheap object storage
- Without mitigation: 365 TB/year all in Postgres = infeasible

### 12A.8 Accepted trade-offs

| Layer | Cost accepted |
|---|---|
| L1 audit split | Two tables to reason about; forensic debugging requires join or pointer chase |
| L2 event discipline | No replay of derived events (broadcast, retrieval); lose some debug fidelity |
| L3 tiered retention | Non-canon events disappear after retention — no "replay from day 1" for those types |
| L4 archive | Cold restore requires re-import from MinIO (rare but real) |
| L5 truncate | Lose replay-from-scratch for old non-canon aggregates; only replay-from-snapshot available |
| L6 lz4 compression | ~3% write CPU overhead; requires Postgres 14+ |

These trade-offs are **acceptable** given the volume problem they solve. Canon fidelity is preserved end-to-end — canon events are never pruned, never deleted. Only transient/derivative data becomes lossy.

### 12A.9 Implementation ordering

- **V1 launch**: L1 (audit split) + L2 (discipline) + L6 (lz4). Mandatory for viable hot-path storage.
- **V1 + 30 days**: L3 (tiered retention cron). Needed once volume starts growing.
- **V2**: L4 (archive pipeline to MinIO) activates when first partitions detach.
- **V3**: L5 (snapshot-then-truncate) becomes relevant when mature realities accumulate.

## 12B. Projection Rebuild & Integrity (R2 mitigation)

Event sourcing requires the ability to rebuild projections from events. This is rare but load-bearing: schema changes, corruption recovery, and catastrophic restore all depend on it. Multiverse isolation + snapshots from §6 already solve most normal cases; the layers below address edge cases.

### 12B.1 Layer 1 — Snapshot-anchored rebuild (baseline)

Already locked in §6. Rebuild of one aggregate = load latest snapshot + fold events since. With snapshot every 500 events or 1 hour, typical aggregate rebuild replays ~50 events (<0.1s per aggregate).

### 12B.2 Layer 2 — Per-aggregate parallel rebuild

Within a reality, aggregates are independent → rebuild in parallel. Default 8 workers (configurable).

```
storage.rebuild.parallel_workers = 8
```

Rebuild of full reality: ~500 aggregates × 50 events / (20K/sec × 8 workers) ≈ 0.2s with snapshots; ~100K events / (20K/sec × 8) ≈ 0.6s for full replay after catastrophic recovery.

Implementation: work-stealing queue per rebuild job, bounded worker pool, graceful cancel on timeout.

### 12B.3 Layer 3 — Schema migration strategy

**V1 strategy: freeze-rebuild-thaw per reality.**

When a projection schema changes (new column, changed derivation):
1. Stop writes for the reality: `status = 'rebuilding'`
2. Run migration SQL (add column, etc.)
3. Rebuild projections from events (§12B.2)
4. Resume writes: `status = 'active'`

Downtime per reality: seconds to minutes. V1 has few realities → tolerable.

**V2 strategy: blue-green projection tables.**

Deferred to V2. When scale requires zero-downtime schema migration:
1. Deploy new projection schema as `<table>_v2` alongside live table
2. Dual-write: writes go to BOTH tables during migration window
3. Background job populates `<table>_v2` from events
4. Verify: diff live vs v2 projection for sampled aggregates
5. Atomic swap: reads switch to v2 via view or rename
6. Drop old table after safety window

Overhead: 2× projection storage during window; dual-write latency small.

**V2 config:**
```
storage.rebuild.blue_green.dual_write_timeout_hours = 24
```

### 12B.4 Layer 4 — Integrity checker (drift detection)

Silent corruption is the worst failure mode. Solution: periodic verification.

**Daily sampling check** (per reality, cheap):
- Pick random sample (default 20) of aggregates
- For each: reload state from events (cascade + snapshot fold)
- Compare with current projection row
- On mismatch: log alert, mark aggregate for targeted rebuild

**Monthly full check** (per reality, expensive, scheduled during low-traffic window):
- Rebuild shadow projection in-memory or in temp table
- Full diff vs live projection
- Alert on any mismatch, auto-trigger rebuild of affected aggregates

Projection tables gain verification metadata:

```sql
ALTER TABLE pc_projection
  ADD COLUMN last_verified_at TIMESTAMPTZ,
  ADD COLUMN last_verified_event_version BIGINT;

-- Same for npc_projection, region_projection, etc.
```

Configuration:
```
storage.rebuild.integrity_check.sample_size = 20
storage.rebuild.integrity_check.daily_enabled = true
storage.rebuild.integrity_check.full_check_interval_days = 30
```

### 12B.5 Layer 5 — Catastrophic rebuild procedure

For disaster recovery (projection tables lost, DB corruption, failed migration):

```
1. UPDATE reality_registry SET status = 'rebuilding' WHERE reality_id = $X
   → All writes for this reality rejected with 503 "under maintenance"
   → Players in this reality see maintenance screen

2. TRUNCATE all projection tables (pc_projection, npc_projection, ...)

3. For each aggregate:
   a. Load latest snapshot (if exists)
   b. Replay events past snapshot version
   c. Or replay from event 0 if no snapshot

4. Run integrity check (§12B.4 full mode)

5. UPDATE reality_registry SET status = 'active' WHERE reality_id = $X
   → Writes resume, players reconnect
```

Expected duration:
- With snapshots: 5–10 minutes per reality
- Without any snapshots (worst case): up to 30 minutes for mature reality

**Rolling across N realities:** orchestrator limits concurrency (default 50 parallel) → 1000 realities / 50 × 10 min ≈ 3–4 hours total, but ≤ 500 players affected at any moment.

Configuration:
```
storage.rebuild.catastrophic.freeze_timeout_minutes = 30
storage.rebuild.catastrophic.rolling_concurrency = 50
```

### 12B.6 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 snapshots | Already accepted. ~10% extra storage for 3 snapshots per aggregate. |
| L2 parallel rebuild | CPU spike during rebuild. Worker count configurable per reality. |
| L3 freeze-rebuild (V1) | Reality unavailable during schema migration (seconds to minutes) |
| L3 blue-green (V2) | 2× projection storage during migration window; dual-write overhead |
| L4 integrity checker | ~1% CPU from daily sampling; full check is background |
| L5 catastrophic rebuild | Reality frozen 5–10 minutes (rare event) |

Main trade-off is V1 freeze-rebuild acceptability. With few realities and careful migration staging, players rarely notice. V2 blue-green removes this once scale demands it.

### 12B.7 Admin tooling (deferred to DF9)

Operations around rebuild need admin surface area:
- Rebuild status dashboard (which realities rebuilding, progress %, ETA)
- Manual rebuild trigger (per-reality, per-aggregate)
- Drift report (aggregates flagged by L4 checker)
- Schema migration planner (stage blue-green across N realities, throttle, rollback)
- Audit trail of rebuild history

This is substantial UI + orchestration work. Deferred to **DF9 — Rebuild & Integrity Ops** (see [OPEN_DECISIONS.md](OPEN_DECISIONS.md) deferred features). Algorithms/mechanisms locked here in §12B; admin UX + orchestration is DF9's scope.

### 12B.8 Implementation ordering

- **V1 launch**: L1 (already) + L2 (parallel rebuild) + L5 (catastrophic procedure, design only — hope never used)
- **V1 + 60 days**: L4 (integrity checker — daily sampling + monthly full)
- **V2**: L3 blue-green for schema migration at scale
- **V3+**: DF9 admin tooling matures

## 12C. Event Schema Evolution (R3 mitigation)

Unlike R1 (volume) and R2 (rebuild), R3 is a **discipline problem**, not a one-shot fix. Without tooling, schema evolution cost compounds; with tooling, it stays linear. The strategy below locks discipline + tooling together.

### 12C.1 Layer 1 — Additive-first discipline

Default stance: **do not modify existing event types**. Prefer, in order:

1. Add a new **optional** field (MINOR bump, backward compatible, trivial upcaster)
2. Introduce a **new event type** for semantically different behavior (see L5)

Only when neither works is the existing event_version bumped with a non-trivial upcaster.

**Rule:** when naming trade-offs vs schema stability come up, choose stability.

### 12C.2 Layer 2 — Schema-as-code + registry

Every event type and version is a typed struct in code. Upcasters are code. A registry generator extracts metadata into a lookup table.

**Example (Go):**

```go
// events/pc.go

// @event pc.said
// @version 1
type PCSaid_V1 struct {
    Content string `json:"content"`
}

// @event pc.said
// @version 2
// @description Added optional speech_act classification
type PCSaid_V2 struct {
    Content   string `json:"content"`
    SpeechAct string `json:"speech_act,omitempty"`
}

// @upcast pc.said 1 -> 2
func UpcastPCSaid_1_to_2(raw json.RawMessage) (PCSaid_V2, error) {
    var v1 PCSaid_V1
    if err := json.Unmarshal(raw, &v1); err != nil {
        return PCSaid_V2{}, err
    }
    return PCSaid_V2{Content: v1.Content}, nil
}

type PCSaid = PCSaid_V2  // CURRENT alias
```

**Registry generator** (CI tool, language-agnostic):
- Parses annotations across all files
- Generates `events/registry.go` with dispatch table `(event_type, event_version) → struct + upcaster chain`
- Generates TypeScript + Python bindings from same annotations (see L7 polyglot strategy below)
- CI fails if: upcaster missing between versions, schema change without version bump, undocumented event_type

**Decision — single source of truth:**
- **Go structs are authoritative** (event producer services are mostly Go: world-service, auth-service, book-service)
- Codegen tool produces TypeScript types (for frontend + api-gateway-bff) and Python types (for roleplay-service, knowledge-service, chat-service)
- One repo location for event schemas: `contracts/events/` at monorepo root
- Changes require PR review across affected services

**Storage for registry:**
- Git-versioned files + codegen output (no separate registry microservice)
- Registry is read-at-startup by services, cached in memory
- Registry changes require service restart (not dynamic reload in V1)

### 12C.3 Layer 3 — Upcaster chain on read

Already framed in §10. Refined:

```
Read path:
  1. SELECT raw events from DB
  2. For each: look up (event_type, event_version) in registry
  3. If event_version < latest_version:
     apply upcaster chain v_n → v_n+1 → ... → latest
  4. Return upcast events to projection fold
```

Chain is automated — registry builds it from individual `@upcast` annotations. Developer never manually composes `v1 → v4` — they just write `v1 → v2`, `v2 → v3`, `v3 → v4` and registry stitches them.

Events stored on disk are **never modified**. Immutability preserved.

### 12C.4 Layer 4 — Schema validation on write

Every event append goes through schema validation:

```go
func AppendEvent(ctx context.Context, evt Event) error {
    schema := registry.Get(evt.EventType, evt.EventVersion)
    if schema == nil {
        return ErrUnknownEventSchema
    }
    if err := schema.Validate(evt.Payload); err != nil {
        return fmt.Errorf("schema violation for %s v%d: %w",
            evt.EventType, evt.EventVersion, err)
    }
    return appendToEventsTable(ctx, evt)
}
```

Config:
```
storage.events.schema_validation.enabled = true   # strict in ALL environments
```

Prevents malformed events from entering the log — bugs fail at write time, not at projection-rebuild time two weeks later.

### 12C.5 Layer 5 — Breaking change = new event type

When a true semantic change is needed (existing event's meaning changes), **do not bump event_version**. Instead:

1. Mark old event type `deprecated: true` in registry — emits warning on write
2. Stop writing old events from new code
3. Introduce new event type (e.g., `pc.moved_v2` → though prefer semantically named `pc.teleported`)
4. Projection consumes both old and new types for a transition period
5. After **90 days** (configurable) + confirmed no old events in hot storage: drop old type handler from projection

**Cooldown config:**
```
storage.events.deprecated_type_cooldown_days = 90
```

**Rationale:** better to have `pc.said_v2` as a new type than an upcaster that reinterprets `pc.said v3` as "same thing but different meaning." Explicit > implicit.

### 12C.6 Layer 6 — Archive upgrade (deferred V2)

When events are archived to MinIO cold storage (R1-L4), an ideal approach is to **upcast to latest version** before writing cold. This keeps the upcaster chain bounded going forward.

**V1 decision: NOT implemented.** Archive writes events in their original version. Upcaster chain handles them at restore time.

**V2 plan:** introduce archive upgrade job:
```
Monthly archive:
  for each event in partition being detached:
    upcast(event, to: latest_version_at_archive_time)
  write to Parquet with schema=latest
  checksum + upload to MinIO
  delete from Postgres
```

Benefits at scale: shorter upcaster chains, simpler restore. Risk: if upcaster has a bug, cold archive permanently corrupted — mitigated by V1-time test harness being mature before V2 activation.

### 12C.7 Polyglot type generation

LoreWeave services span Go, Python, and TypeScript. Event schemas must stay in sync across all three.

**Strategy:**
- Go is source of truth (annotated structs in `contracts/events/`)
- Codegen tool (`eventgen`) produces:
  - `contracts/events/generated/ts/` — TypeScript interfaces for frontend + api-gateway-bff
  - `contracts/events/generated/python/` — Pydantic models for Python services
- Codegen runs in CI; generated files committed so consumers don't need Go toolchain
- Services import generated types; never hand-write event types

**CI gates:**
- Go struct changes without regenerated TS/Python → CI fail
- Generated files modified directly without source change → CI fail
- New event type without `@description` annotation → CI fail

### 12C.8 Expected maintenance cost

With tooling + discipline:

| Change kind | Dev effort | Risk |
|---|---|---|
| Add new event type | 1–2 hours | Low |
| Add optional field (MINOR) | 30 min | Low |
| Rename field / semantic change | 2–4 hours | Medium |
| Breaking change (new event_type via L5) | 4–8 hours | Medium |
| Remove deprecated event type after cooldown | 1 hour | Low |

Projected cost at mature scale (40 event types × 2 versions avg after 3 years):
- 80 version/type changes × 1–2 hours = **80–160 dev-hours over 3 years** ≈ 3–5 dev-hours/month
- Linear scaling, not compounding

### 12C.9 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 additive discipline | Occasional suboptimal field naming (accepted for stability) |
| L2 schema-as-code + codegen | ~2 weeks upfront tooling; ongoing CI maintenance |
| L3 upcaster chain on read | +0.5–1 ms read latency per event per version gap |
| L4 schema validation on write | +0.5 ms write latency per event |
| L5 new event_type for breaking change | Event type proliferation; projection logic forks |
| L6 archive upgrade (V2+) | Archive job complexity; correctness-critical |
| Polyglot codegen | Every event change touches 3 languages (auto-generated but still PR diff) |

Main cost is L2 upfront tooling. Without it, R3 compounds; with it, R3 stays linear. Worth the investment.

### 12C.10 Implementation ordering

- **V1 launch**: L1 (discipline), L2 (schema-as-code + codegen), L3 (upcaster chain), L4 (validation on write). Mandatory — can't start event sourcing without these.
- **V1 + ongoing**: L5 (new event_type for breaking changes) as policy
- **V2**: L6 archive upgrade when cold archive volume justifies
- **V1+30d → V3**: DF10 (see 12C.11) matures

### 12C.11 Tooling surface (deferred to DF10)

The mechanisms above require tooling. Admin + dev tooling around schema evolution is substantial:

- Schema registry viewer (browse all event types, versions, upcasters)
- Upcaster test harness (load sample events, validate chains)
- Codegen CLI (`eventgen generate` / `eventgen validate`)
- Deprecation dashboard (which types are deprecated, what hot-storage counts remain)
- Cross-service schema sync verifier
- Documentation auto-generation from annotations

Deferred to **DF10 — Event Schema Tooling**. Mechanisms (L1–L5) locked here in §12C; dev UX + CI integration is DF10's scope.

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

## 12E. Cross-Instance Data Access (R5 mitigation)

Cross-reality queries across N reality DBs are rejected as an API pattern. This section locks the alternative: a tight 3-layer model for every legitimate cross-instance need, plus an explicit anti-pattern rule.

### 12E.1 Core insight — no product feature requires live cross-instance query

Review of every candidate "cross-reality query" reveals:

| Candidate use case | Classification |
|---|---|
| User "my PCs" dashboard | Meta-level lookup (`player_character_index`) |
| Reality discovery / browser | Meta-level lookup (`reality_registry`) |
| All realities of a book | Meta-level lookup |
| Reality population stats | Meta-level field |
| Canon update propagation | Event-driven push, not query |
| User deletion cascade | Event-driven push |
| Top NPCs / leaderboards | **Not a product feature** (rejected by ethos SOC-6/7) |
| Analytics (retention, cohort) | Admin/business, **defer indefinitely** |
| Moderation ("all content by user") | Admin, slow ad-hoc acceptable |
| Admin "find realities matching X" | Admin, rare |
| Cross-book entity search | **Not a confirmed feature** |
| World travel | **Import/export** (DF6), not query |

**The only cross-reality feature** is world travel (DF6), handled as atomic import/export between two specific reality DBs + meta registry update. Not a query.

No product feature in V1–V4 roadmap requires live cross-instance query. Design accordingly.

### 12E.2 Layer 1 — Meta registry lookups (minimal)

Existing meta registry tables cover current needs:

- `reality_registry` — book_id, locale, status, current_player_count, canonicality_hint, etc.
- `player_character_index` — user_id → pc_id → reality_id → name → last_seen → status

**Extension policy:** add fields lazily when a feature demands them, not speculatively.

**Near-term additions (locked):**
```sql
ALTER TABLE reality_registry
  ADD COLUMN trending_score FLOAT DEFAULT 0,       -- V2+: discovery sort by popularity
  ADD COLUMN last_stats_updated_at TIMESTAMPTZ;    -- heartbeat for reality→meta sync
```

**Rejected (not building):**
- `user_reality_activity_index` — no justifying use case (PC count is user-scope, not reality-scope)
- `reality_popularity_index` — a single field on `reality_registry` suffices
- Separate entity search index — no confirmed feature

Discipline: every new meta field requires a mapped feature. No premature indexes.

### 12E.3 Layer 2 — Event-driven propagation (dedicated service)

Push, not pull. Narrow scope — only the cross-instance state that actually needs to cross boundaries.

**Topics (locked):**

| Topic | Producer | Consumer | Purpose |
|---|---|---|---|
| `xreality.book.canon.updated` | book-service, glossary-service | Each reality subscribed to book_id | L1/L2 canon sync ([M4](01_OPEN_PROBLEMS.md#m4-inconsistent-l1l2-updates-across-reality-lifetimes--open) resolved) |
| `xreality.user.deleted` | auth-service | All realities where user has PC | GDPR purge; convert PC to orphan NPC |
| `xreality.reality.stats` | Each reality | meta-worker | Update registry fields (`current_player_count`, etc.) |

**Dedicated service: `meta-worker` (Go, small, narrow-scope).** Reasons:
- Clear boundary (consumes xreality.* topics, writes to meta registry)
- Reusable across future propagation needs
- Easier to reason about restart/retry state

**Transport:** Redis Streams (reuse IF-5). Separate namespace `xreality.*` to distinguish from intra-reality streams.

**Consumer protocol:**
- At-least-once delivery (dedupe via correlation_id)
- Retry with exponential backoff (3 attempts default)
- Poison-pill queue for persistent failures → manual review

**Config:**
```
xreality.topics.book_canon_updated = "xreality.book.canon.updated"
xreality.topics.user_deleted = "xreality.user.deleted"
xreality.topics.reality_stats = "xreality.reality.stats"
xreality.meta_worker.concurrency = 10
xreality.meta_worker.retry_attempts = 3
xreality.index_update_lag_warn_seconds = 60
```

**Service registration:** `services/meta-worker/` — Go service skeleton, follows existing service patterns (auth middleware, Prometheus metrics, health check).

### 12E.4 Layer 3 — Admin/analytics (deferred indefinitely)

**Not V1. Not V2 locked. Explicitly deferred until a specific feature demands.**

When that day comes (if ever):
- Evaluate data volume (do we need OLAP, or is Postgres batch enough?)
- Evaluate latency tolerance (realtime vs minutes vs hours)
- Evaluate query shape (point lookup vs aggregate vs search)

Candidate tools at that future decision: ClickHouse, Elasticsearch, BigQuery, Snowflake, or plain Postgres replica. None locked now.

**DF12 (Cross-Reality Analytics & Search) — NOT registered.** If demand emerges, new DF to be created at that time with specific scope.

### 12E.5 Ad-hoc admin queries (tool, not feature)

For rare admin operations (incident response, legal discovery, deep debugging), app-level fan-out is acceptable:

```go
func adminFindRealities(criteria Criteria) []Reality {
    // Rate-limited, timeout-bounded, audit-logged
    shards := listActiveShards()
    results := []Reality{}
    for _, shard := range shards {
        for _, realityID := range shardRealitiesIn(shard) {
            if criteria.CheapMetaFilter(realityID) {
                dbResult := queryReality(realityID, criteria)
                results = append(results, dbResult...)
            }
        }
    }
    return results
}
```

**Rules:**
- Rate limit: max 1 such query per minute per admin
- Timeout: 30 seconds total
- Audit log: every invocation
- Never in user-facing request path

**Config:**
```
admin.federated_query.rate_limit_per_min = 1
admin.federated_query.timeout_seconds = 30
```

### 12E.6 Anti-pattern — reject cross-instance live query as API design

Formal governance rule. When a feature seems to need "query across realities," the contributor MUST redesign as one of:

1. **Meta-level lookup** — promote the needed field to `reality_registry` or `player_character_index` (with justification)
2. **Event-driven propagation** — emit event from producer, local cache in consumers
3. **Import/export** — atomic hand-off between specific realities (like world travel DF6)
4. **Ad-hoc admin query** — rate-limited, slow, audit-logged

**Never acceptable:**
- `postgres_fdw` to federate reality DBs
- App-level fan-out in user-facing code path
- Ad-hoc direct connections to multiple reality DBs in realtime path

This is codified as governance policy: see [`docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md`](../../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md).

**Code review enforcement:**
- PR touching realtime code must not import multiple reality DB drivers
- Any new `multi_db_query` function must reference this policy in its doc string
- Deviations require explicit ADR

### 12E.7 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 meta lookups | Field proliferation risk — mitigated by "feature-justified" discipline |
| L2 event propagation | Meta-worker service to maintain (narrow but real) |
| L3 analytics defer | Future demand may require infrastructure addition then |
| Anti-pattern discipline | Code review must catch violations |

The biggest cost is L2 meta-worker — but narrow scope keeps it manageable.

### 12E.8 Implementation ordering

- **V1 launch**: L1 (existing registry + field additions as features land), L2 (meta-worker service with 3 topics), governance doc published
- **V1 + 60 days**: L2 canon propagation activates on first author canon edit
- **V2**: Add `trending_score` if reality discovery sort demands
- **V3+**: Re-evaluate L3 only if specific admin/business feature surfaces

## 12F. Outbox Publisher Reliability (R6 + R12 mitigation)

The outbox pattern (IF-6) is the critical path for realtime broadcast. Publisher service reliability determines whether players see "live" world state or stale state. R12 (Redis stream ephemerality) is fully resolved by this section's cache-vs-SSOT framing.

### 12F.1 Layer 1 — Outbox pattern (already locked)

Events committed atomically with `events_outbox` row in same transaction. Publisher tails outbox, pushes to Redis, marks published. Baseline from IF-6.

Schema extension to support retry + dead letter:

```sql
ALTER TABLE events_outbox
  ADD COLUMN attempts INT NOT NULL DEFAULT 0,
  ADD COLUMN last_error TEXT,
  ADD COLUMN last_attempt_at TIMESTAMPTZ,
  ADD COLUMN dead_lettered_at TIMESTAMPTZ;

CREATE INDEX events_outbox_pending_idx
  ON events_outbox (event_id)
  WHERE published = FALSE AND dead_lettered_at IS NULL;

CREATE INDEX events_outbox_dead_letter_idx
  ON events_outbox (dead_lettered_at)
  WHERE dead_lettered_at IS NOT NULL;
```

### 12F.2 Layer 2 — Publisher service (dedicated)

**Service:** `publisher` at `services/publisher/`. Dedicated Go service — isolated lifecycle, clear ops boundary, matches `meta-worker` pattern.

**Architecture:**
```
publisher process:
  1. Acquire partition assignment (leader election via Redis SETNX)
  2. Poll loop:
     SELECT event_id, reality_id, ... FROM events_outbox
     WHERE reality_id = ANY($assigned_ranges)
       AND published = FALSE
       AND dead_lettered_at IS NULL
     ORDER BY event_id
     LIMIT $batch_size
     FOR UPDATE SKIP LOCKED;
  3. Group by reality_id
  4. Batch push to Redis Stream: XADD reality:<id>:events MAXLEN ~ 10000 ...
  5. On success: UPDATE outbox SET published=true, last_attempt_at=now()
  6. On failure: UPDATE outbox SET attempts=attempts+1, last_error=..., last_attempt_at=now()
     Compute retry delay via exponential backoff
  7. On attempts >= max_retries: UPDATE dead_lettered_at=now() + alert
```

**Leader election** (V2+ with multiple replicas; V1 no-op cost):
- `SETNX publisher:leader:{shard_host} {replica_id} EX 30`
- Leader heartbeats lock every 10s
- Losers idle until leader dies

**FOR UPDATE SKIP LOCKED** allows multiple replicas to safely poll without stepping on each other (at V3 when partition count exceeds replicas).

### 12F.3 Layer 3 — Lag monitoring + alerting

Per-reality lag metrics:
```
lw_outbox_unpublished_count{reality_id}                   gauge
lw_outbox_oldest_unpublished_age_seconds{reality_id}      gauge
lw_publisher_batch_rate{shard_host}                       counter
lw_publisher_error_count{reality_id, reason}              counter
lw_publisher_lag_seconds{reality_id}                      gauge (derived)
lw_publisher_dead_letter_count{reality_id}                gauge
```

**Alert thresholds (configurable):**
```
outbox.lag_warn_seconds = 10      # warn if oldest unpublished > 10s
outbox.lag_page_seconds = 60      # page SRE if > 60s
outbox.lag_critical_seconds = 300 # auto-enable degraded mode if > 5 min
```

**Heartbeat table in meta registry:**
```sql
CREATE TABLE publisher_heartbeats (
  publisher_id      TEXT PRIMARY KEY,         -- replica_id
  shard_host        TEXT NOT NULL,
  assigned_ranges   JSONB,                    -- partition assignment
  last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status            TEXT NOT NULL             -- 'active' | 'draining' | 'dead'
);
CREATE INDEX ON publisher_heartbeats (shard_host, last_heartbeat_at);
```

Missing heartbeat (>30s) = publisher dead → alert + leader election triggers next replica.

### 12F.4 Layer 4 — Client reconnect + catchup protocol

Realtime broadcast = **best-effort cache**. Authoritative state lives in Postgres events table. WebSocket protocol tolerates gaps.

**New REST endpoint for catchup:**
```
GET /v1/realities/{reality_id}/events?since={event_id}&limit=500
  → 200 { events: [...], next_since: event_id_or_null }
```

Authenticated, rate-limited, reads directly from `events` table in reality DB.

**WebSocket handshake:**
```
Client → Server: CONNECT {
  reality_id: "uuid",
  last_seen_event_id: 12345,
  subscribed_regions: ["region_uuid_1", ...]
}

Server → Client: WELCOME {
  current_stream_head_event_id: 14000,
  lag_status: "ok" | "degraded" | "critical",
  catchup_needed: true | false
}

If catchup_needed:
  Client fetches via GET /v1/realities/{id}/events?since=12345 in batches
  Client applies events in order to local state
  Then client sends READY, server starts live streaming

Else:
  Server streams live events from Redis immediately
```

**Dedup on client:**
- Client keeps `Set<event_id>` (bounded ~10K, LRU eviction)
- Drops re-delivered events

**Degraded mode:**
- If `lag_status='degraded'` → client shows "⚠ Realtime delayed" badge
- Client polls catchup endpoint every 30s until `lag_status='ok'`

### 12F.5 Layer 5 — Poison pill handling

Retry policy:
```
publisher.max_retries_per_row = 5
publisher.retry_backoff_schedule = "1s,5s,30s,2m,10m"
```

After 5 attempts failing: row marked `dead_lettered_at = now()`. Publisher skips dead-letter rows (index condition ensures efficient query).

**Alert on dead letter** (once per row, not repeated): SRE / admin reviews via DF9 dashboard.

**Admin resolution options:**
1. **Replay** after code fix — clear `dead_lettered_at`, reset `attempts=0`, `last_error=null`
2. **Skip** permanently — leave dead-lettered, mark `published=true` with audit note
3. **Manual publish** — push event to Redis out-of-band, mark `published=true`

### 12F.6 Layer 6 — Redis stream retention + DB fallback (resolves R12)

Redis Streams have capped length — this is **expected + designed for**, not a bug.

```
publisher.redis_stream_maxlen = 10000           # last ~2 minutes at 100 evt/s per reality
publisher.redis_stream_maxlen_approximate = true  # faster MAXLEN with fuzzy bound
```

**Per-reality MAXLEN override:** stored in `reality_registry.stream_maxlen` (nullable, falls back to default). Active crowded realities can have 50K, frozen realities can have 1K.

**Consumer logic (WebSocket server):**
```
1. Check Redis stream XRANGE for events > last_seen_event_id
2. If stream earliest > last_seen_event_id → FALLBACK to DB query
3. DB events table is SSOT, always available
```

**R12 fully subsumed by this layer.** Redis is cache by design. If cache misses, DB answers. No data loss possible.

### 12F.7 Layer 7 — Graceful shutdown + handoff

Publisher responds to SIGTERM:
```
1. Mark status='draining' in publisher_heartbeats
2. Stop picking new batches
3. Complete in-flight batches (bounded by shutdown_timeout_seconds = 30)
4. Release Redis leader lock (DEL publisher:leader:{shard_host})
5. Exit cleanly
```

Next replica:
```
1. Detects lock released OR TTL expired
2. Wins next SETNX attempt
3. Reads partition assignment from meta registry
4. Starts polling within seconds
```

Zero-message-loss handoff (events durable in outbox until published).

### 12F.8 Horizontal scaling strategy

| Scale | Publisher topology |
|---|---|
| V1 (≤10 realities) | 1 publisher process per shard, 1 leader. No real partitioning. |
| V2 (≤100 realities) | 2 publishers per shard (active-passive). Partition-by-reality via consistent hash. |
| V3 (1000+ realities) | 4+ publishers per shard. Automated rebalance. |

Partition assignment stored in `publisher_heartbeats.assigned_ranges` (JSONB):
```json
{"reality_id_hash_ranges": [[0, 16384], [32768, 49152]]}
```

V1/V2: manual assignment via admin. V3+: auto-rebalance algorithm in DF9.

### 12F.9 Accepted trade-offs

| Layer | Cost |
|---|---|
| L2 publisher service | Dedicated service to operate; health checks required |
| L3 lag monitoring | Prometheus cardinality: 1 metric × N realities. Cap at 1000 active → 1K series, fine. |
| L4 client catchup | WebSocket protocol more complex; client dedup required |
| L5 poison pill DLQ | Manual admin intervention; alerts must be tuned |
| L6 Redis cache + DB fallback | Consumer has two paths; slow path when stream short. Acceptable trade. |
| L7 leader election | Small Redis overhead; prevents split-brain |

At-least-once delivery → consumer dedup mandatory (already required by L4).

### 12F.10 Config keys (R6)

```
publisher.batch_size = 100
publisher.poll_interval_ms = 100
publisher.max_retries_per_row = 5
publisher.retry_backoff_schedule = "1s,5s,30s,2m,10m"
publisher.redis_stream_maxlen = 10000
publisher.redis_stream_maxlen_approximate = true
publisher.shutdown_timeout_seconds = 30
publisher.heartbeat_interval_seconds = 10
publisher.leader_lock_ttl_seconds = 30

outbox.lag_warn_seconds = 10
outbox.lag_page_seconds = 60
outbox.lag_critical_seconds = 300
```

### 12F.11 Implementation ordering

- **V1 launch**: L1 (existing) + L2 (publisher service, single replica) + L3 (metrics + alerts) + L4 (WS handshake + catchup REST endpoint) + L5 (DLQ schema + alert) + L6 (Redis MAXLEN + DB fallback) + L7 (graceful shutdown)
- **V1 + 30 days**: L3 alert routing mature; DF9 publisher dashboard starts
- **V2**: L8 multi-replica publisher with leader election; partition-by-reality
- **V3+**: Auto-rebalance; DF9 publisher admin UI full

### 12F.12 Tooling surface (folded into DF9)

Admin UX for publisher ops:
- Publisher health dashboard (per shard, per partition, lag real-time)
- Dead-letter queue review + replay/skip/manual-publish actions
- Partition assignment editor (V2+)
- Rebalance trigger (V3+)

**Folded into DF9 (Rebuild & Integrity Ops)**. DF9 scope grows to **"Event + Projection + Publisher Operations"** — covers everything in the per-reality correctness + runtime event pipeline. Avoids DF proliferation.

## 12G. Session as Concurrency Boundary + Cross-Session Event Handler (R7 mitigation)

R7 initially framed as "multi-aggregate transaction deadlocks." Re-examination: **game is turn-based, session is the concurrency unit**. Intra-session writes are sequential by design — no deadlocks possible. The real R7 is cross-session effect propagation when an event's scope exceeds the originating session (e.g., spell destroys tavern → affects all 5 sessions in the tavern).

This reframes R7 from a locking problem into an event-routing problem. Supersedes the multi-aggregate concurrency framing in §8.

### 12G.1 Core insight — session is the concurrency unit

Every event lives in exactly one session while player-active. Within a session, turns are strictly sequential:

```
Session turn sequence (example):
  T=0: Alice speaks
  T=1: Elena (LLM) responds
  T=2: Bob speaks
  T=3: Bartender (LLM) responds
  ...
```

At any moment, **exactly one command is being processed** per session. No concurrent writes → no deadlocks → no lock contention.

Multiple sessions can run in parallel within a reality — but they touch different aggregates (different PCs, different NPCs if disjoint, or same NPC only if NPC is in multiple sessions simultaneously — see §12G.7).

**Superseded concerns from §8:**
- §8.2 multi-aggregate lock order discipline → unnecessary within session (serial by design)
- §8.3 hot NPC contention → solved at session level (NPC in 1 session at a time via busy-lock, see §8.3 unchanged)
- §8.4 per-reality single writer → replaced by per-session single writer (finer grain, higher throughput)

Optimistic concurrency (§8.1) still valid as defense-in-depth for cross-session collisions.

### 12G.2 Pillar A — Session as single-writer command processor

**Mandatory architecture.** Every session has exactly one command processor (goroutine or dedicated worker) that processes commands in strict FIFO order:

```go
// Pseudocode — session command loop
func sessionProcessor(sessionID UUID) {
    for cmd := range sessionCommandQueue(sessionID) {
        // 1. Load state (short read, no locks persist after)
        state := loadSessionState(sessionID)

        // 2. LLM + retrieval OUTSIDE tx (can be seconds)
        response := llmProcess(state, cmd)

        // 3. Write tx — short, serial per session
        tx := db.Begin()
        appendEvents(tx, response)          // scoped to session by default
        updateProjections(tx)
        insertOutbox(tx)
        tx.Commit()
    }
}
```

**Properties:**
- No DB-level locks needed within session — serial commits don't contend
- LLM call happens between commits (async), but each session has ≤1 LLM call in flight
- Throughput per session = 1 / (LLM latency + commit latency) ≈ 1 turn / 5s
- Sessions in parallel scale horizontally — N sessions = N processors

**Schema cleanup:**
```sql
-- Remove opt-in single-writer mode — now mandatory at session level
ALTER TABLE reality_registry
  DROP COLUMN command_processor_mode;  -- no longer configurable
```

### 12G.3 Pillar B — Cross-session event propagation (DF13)

Events emitted within a session may have **wider scope**. Handler routes them to other affected sessions.

**Scope tagging on events:**
```sql
ALTER TABLE events
  ADD COLUMN scope TEXT NOT NULL DEFAULT 'session';
-- 'session' | 'region' | 'reality' | 'world'
```

**Scope semantics:**

| Scope | Propagation | Example |
|---|---|---|
| `session` | None — default, intra-session only | PC speaks to NPC in same session |
| `region` | Fan out to all sessions in same region | Spell destroys tavern, weather shifts |
| `reality` | Fan out to all active sessions in reality | World clock tick, reality-wide event |
| `world` | Routed via `xreality.*` (§12E) | Canon update from book, cross-reality |

### 12G.4 Session event queue

Each session has an inbox for cross-session events:

```sql
CREATE TABLE session_event_queue (
  queue_id            BIGSERIAL,
  session_id          UUID NOT NULL,
  source_event_id     BIGINT NOT NULL,
  source_session_id   UUID,                      -- NULL if from system/world tick
  scope               TEXT NOT NULL,
  payload             JSONB NOT NULL,
  status              TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'applied' | 'skipped' | 'failed'
  enqueued_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  applied_at          TIMESTAMPTZ,
  PRIMARY KEY (session_id, queue_id)
);
CREATE INDEX session_event_queue_pending_idx
  ON session_event_queue (session_id, enqueued_at)
  WHERE status = 'pending';
```

Lives in each reality DB (scoped to reality).

### 12G.5 Event-handler service (`services/event-handler/`)

Dedicated Go service. Separate from `publisher` (different concern, different scale).

**Architecture:**
```
event-handler process:
  - Tracks cursor per reality (last processed event_id)
  - Polls events table: WHERE event_id > cursor AND scope != 'session'
  - For each:
     a. Determine affected sessions based on scope:
        - 'region' → query active sessions WHERE region_id = event.region_id
        - 'reality' → query all active sessions in reality
        - 'world' → defer to xreality.* handler (§12E, out of scope for this service)
     b. Insert session_event_queue rows for each affected session
     c. Advance cursor
```

**Cursor table** (per reality DB):
```sql
CREATE TABLE event_handler_cursor (
  cursor_name           TEXT PRIMARY KEY,        -- 'primary' (could have replayers)
  last_routed_event_id  BIGINT NOT NULL DEFAULT 0,
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Consumer — session processor updated:**
```go
func sessionProcessor(sessionID UUID) {
    for {
        // Priority 1: pending queue items (cross-session events)
        if qItem := popQueueItem(sessionID); qItem != nil {
            processQueueItem(sessionID, qItem)  // LLM reacts, commits
            continue
        }

        // Priority 2: user turn input
        if cmd := waitForUserInput(sessionID, timeout); cmd != nil {
            processUserTurn(sessionID, cmd)
            continue
        }
    }
}
```

Queue items processed **before** user input — environmental effects feel immediate.

### 12G.6 Propagation semantics

**Async (default, V1):**
- Originating session commits, moves on
- Affected sessions pick up at their next processor tick
- Latency: seconds (bounded by active session's next idle moment)
- No coordination between sessions

**Sync (deferred, V2+ if specific feature demands):**
- Originator blocks until affected sessions acknowledge
- Adds cross-session coordination complexity
- Only for rare consistency-critical effects

**Ordering guarantees:**
- Within a target session: queue items processed FIFO by `enqueued_at`
- Cross-session: no ordering — session A and session B may see related events in different orders at different times
- Single-writer per session + FIFO queue ensures within-session consistency

**Conflict handling:**
- If session B has a pending user turn AND an incoming queue item, queue item runs first
- If session B's own events contradict incoming event (e.g., both sessions try to destroy the tavern) → both events apply in order; LLM narrates second one appropriately ("the rubble collapses further...")
- No rollback of player actions based on cross-session events

**Idempotency:**
- Queue item has `source_event_id` — if event-handler retries insertion, unique constraint ensures deduplication
- Session processor marks `status='applied'` in same tx as event commit → crash recovery safe

### 12G.7 NPC in multiple sessions simultaneously

Edge case: a key NPC (quest giver) is in sessions 1 and 2 simultaneously. How?

**V1 answer:** NPCs CANNOT be in multiple sessions simultaneously. Each NPC has a `current_session_id` field; attempting to join a second session fails or forces context switch (NPC leaves session 1, joins session 2).

```sql
ALTER TABLE npc_projection
  ADD COLUMN current_session_id UUID;
-- NULL = not in any session (available)
```

If player in session B wants to talk to NPC already in session A: UI says "Elena is currently with [Alice's group] — wait for them to finish."

This avoids the hardest concurrency: same NPC responding to 2 conversations at once.

**V2+ alternative:** "multi-presence NPC" — NPC concurrent in multiple sessions, but memory + state synced via event handler. Complex, deferred.

### 12G.8 Worked example — spell destroys tavern

```
T=0: Session 1 (Alice's table): Alice casts destroy-tavern spell
T=1: Session 1 processor:
       LLM resolves → emits events:
         pc.cast_spell (scope='session')
         spell.triggered (scope='session')
         region.destroyed (scope='region', region_id=tavern)   ← wider scope
       Commit to session 1 + outbox + events table

T=2: event-handler tails events, sees scope='region':
       Queries active sessions where region_id=tavern → finds sessions 2, 3, 4, 5
       Inserts session_event_queue rows for each:
         { scope='region', payload={type:'tavern_destroyed', source_session:1, ...} }

T=3-7: Sessions 2, 3, 4, 5 at next processor tick each:
       Pop queue item
       LLM narrates: "The walls collapse around you!"
       Emit events in own session (scope='session')
       Commit

Final state:
  - Session 1: destroyed_by_alice event recorded
  - Sessions 2-5: each has own reaction events
  - Region state: tavern marked destroyed
  - Players in all 5 sessions see consistent destruction
```

No locks. No deadlocks. No retries. Async propagation ~seconds.

### 12G.9 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 single-writer per session | Throughput per session bounded by LLM latency — matches turn-based design |
| L2 scope tagging | Every event has scope column; design discipline for producers |
| L3 event-handler service | New dedicated service to operate; cursor lag monitoring |
| L4 session event queue | Extra table per reality DB; small, short-lived rows |
| L5 priority (queue before user input) | User may see environmental event before their own turn commits — design feature, not bug |
| L6 NPC single-session constraint (V1) | UX gate when NPC busy; simpler than multi-presence |
| L7 observability | Standard metric overhead |

**Removed from original R7:** lock-order helper, optimistic-retry loops, pre-check reads, multi-aggregate deadlock handling. All unnecessary with session-as-concurrency-unit.

### 12G.10 Key interactions

- **R7 ↔ DF5 (Session feature)**: DF5 owns session lifecycle (create, join, leave); §12G owns concurrency semantics. DF5 design MUST implement single-writer pattern from §12G.2.
- **R7 ↔ DF13 (Event Handler)**: DF13 is the admin + operational UX over event-handler service. Mechanisms locked here, admin UI deferred.
- **R7 ↔ R6 (publisher)**: publisher broadcasts events to connected clients (UX); event-handler routes to other sessions (game state). Both tail events table but track independent cursors. No overlap.
- **R7 ↔ A1 (NPC memory)**: NPC memory updates happen within the session NPC is currently in. No cross-session memory contention.

### 12G.11 Config keys

```
event_handler.poll_interval_ms = 100
event_handler.batch_size = 100
event_handler.cursor_lag_warn_seconds = 30
event_handler.cursor_lag_page_seconds = 120
session.queue_priority = "queue_before_user_input"  # V1 default
session.npc_busy_policy = "single_session"          # V1: NPC in 1 session at a time
session.event_queue_retention_days = 30              # keep applied queue items for audit
```

### 12G.12 Implementation ordering

- **V1 launch**: L1 (session single-writer — part of DF5 Session feature), L2 (scope column + event tagging discipline), L3 (event-handler service MVP), L4 (session_event_queue table + consumer logic), L5 (priority rules), L6 (NPC single-session constraint), L7 (metrics)
- **V1 + 30 days**: DF13 admin UX mature (queue inspection, propagation lag dashboard)
- **V2**: evaluate sync propagation if specific feature demands; evaluate NPC multi-presence
- **V3+**: Advanced scope semantics (e.g., delayed scope, conditional propagation)

### 12G.13 Tooling surface (DF13)

Dedicated admin + dev tooling for cross-session effects:
- Event handler health dashboard (cursor lag per reality)
- Session event queue inspector (pending, applied, failed per session)
- Scope distribution analytics (how often region/reality events fire)
- Manual event propagation trigger (admin tool for debugging / fixup)
- Queue replay after bug fix (re-enqueue failed items after root cause resolved)

Deferred to **DF13 — Cross-Session Event Handler**. Mechanisms (L1–L7) locked here in §12G; admin UX + dev tooling scope of DF13.

## 12H. NPC Memory Aggregate Split (R8 mitigation, A1 foundation)

NPC state grows linearly with interaction count. A popular NPC (tavern keeper) after 1 year with 10K PCs would have ~75MB state per snapshot in a naive design. Resolution: split NPC into core aggregate + per-pair memory aggregates. This is also the storage foundation for A1 (NPC memory at scale) — A1's semantic layer builds on this infrastructure.

### 12H.1 Core insight — linear growth must be broken

Naive NPC aggregate embedding per-PC memory:
- Elena after 1 year × 10K interacted PCs = 10K × 7.5KB = **~75MB per snapshot**
- 3 retained snapshots: **~225MB just for Elena**
- Loading NPC for turn = read 75MB + deserialize. Unworkable.

Split NPC into two aggregate types, both event-sourced:

| Aggregate type | Scope | Snapshot size |
|---|---|---|
| `npc` | Core state per NPC | ~10-20KB (stable) |
| `npc_pc_memory` | One per (npc_id, pc_id) pair | ~2-10KB per pair (bounded) |

Total per NPC at 10K interacted PCs after cold decay (L4): ~6MB steady, loaded lazily (L5) as ~2-10KB per active pair.

### 12H.2 Layer 1 — Aggregate split (core mechanism)

**`npc` aggregate** — core state only:
```
Aggregate ID: npc_id (UUID)
State snapshot: {
  glossary_entity_id,
  current_region_id,
  current_session_id,         // R7-L6: NPC in ≤1 session at a time
  mood,
  core_beliefs: {...},        // L1 canon reference
  flexible_state: {...}       // L3 reality-local drift
}
Size: ~10-20KB, stable regardless of player count
```

**`npc_pc_memory` aggregate** — one per (npc_id, pc_id) pair:
```
Aggregate ID: uuidv5('npc_pc_memory', concat(npc_id, pc_id))  // deterministic
State snapshot: {
  summary: TEXT,              // rolling LLM-generated (L2)
  facts: [...],               // bounded list (L2)
  last_interaction_at,
  interaction_count,
  embedding_ref               // pointer/hash only, vector in separate table (L6)
}
Size: ~2-10KB per pair, bounded
```

Aggregate types enum:
```
'pc' | 'npc' | 'npc_pc_memory' | 'region' | 'world'
```

**Event emission pattern** — when Elena (NPC) talks to Alice (PC), in a single transaction:
```sql
BEGIN;

-- Event on Elena (npc aggregate)
INSERT INTO events (reality_id, aggregate_type, aggregate_id, aggregate_version, event_type, payload, ...)
VALUES ($reality, 'npc', $elena_id, $elena_v+1, 'npc.said', {...}, ...);

-- Event on Elena-Alice memory (npc_pc_memory aggregate)
INSERT INTO events (...)
VALUES ($reality, 'npc_pc_memory', $elena_alice_pair_id, $pair_v+1, 'npc_pc_memory.interaction_logged', {...}, ...);

-- Projection updates + outbox
COMMIT;
```

Both version-bumped atomically, independent snapshot cadence.

### 12H.3 Layer 2 — Bounded memory per pair

Hard caps prevent unbounded pair growth:

```
npc_memory.max_facts_per_pc = 100            # LRU eviction over this
npc_memory.summary_rewrite_every_events = 50  # LLM compaction trigger
npc_memory.summary_max_length_chars = 2000
```

**Fact structure:**
```json
{
  "fact_id": "uuid",
  "content": "Alice defended Elena's son",
  "source_event_id": 12345,
  "importance_score": 0.8,
  "created_at": "...",
  "last_accessed_at": "..."
}
```

**LRU eviction:** when pair hits 100 facts, evict `ORDER BY last_accessed_at ASC` until ≤100.

**Summary rewrite flow:**
```
Trigger: pair receives 50 interaction events since last summary rewrite

  1. Load pair state: summary + recent facts + recent interactions
  2. LLM prompt: "Update this NPC's understanding of this PC..."
  3. Emit event: npc_pc_memory.summary_rewritten { new_summary, obsolete_facts_pruned }
  4. Prune facts that are now subsumed by summary (importance < threshold)
  5. Next 50 events → next rewrite
```

This keeps summary fresh + facts bounded.

### 12H.4 Layer 3 — Snapshot size enforcement + auto-compaction

Hard thresholds:
```
npc_memory.snapshot_size_warn_mb = 1
npc_memory.snapshot_size_critical_mb = 5
```

**On snapshot creation:** measure serialized JSONB size.
- **> warn:** log + metric + review flag
- **> critical:** trigger emergency compaction immediately (aggressive summary rewrite, drop oldest facts)

Prevents any single aggregate from becoming a hot spot.

### 12H.5 Layer 4 — Cold memory decay

Pairs with no recent interaction get progressively pruned:

| Time since last interaction | Action |
|---|---|
| 0–30 days | Full retention (summary + facts + embedding) |
| 30–90 days | Keep summary + embedding; drop facts array |
| 90–365 days | Keep summary only (short); drop embedding |
| 365+ days | Archive entire pair aggregate to MinIO; restore on PC return |

**Archive/restore:**
- Archive: dump aggregate events + snapshots to MinIO (reuses R1-L4 pipeline, per-aggregate granularity)
- Restore: on first new interaction, pull events from MinIO, rebuild projection
- Latency: 1-2 seconds for restore (acceptable for rare long-absence returns)

**Config:**
```
npc_memory.cold_decay_fact_drop_days = 30
npc_memory.cold_decay_embedding_drop_days = 90
npc_memory.archive_days = 365
```

### 12H.6 Layer 5 — Lazy loading (session-scoped)

Turn processor loads minimal state per turn:

```go
func processNPCTurn(sessionID, npcID UUID, currentSpeakerPCID UUID) {
    // Load NPC core — always needed
    npcCore := loadAggregate("npc", npcID)

    // Load memory ONLY for the PC currently speaking + others in session
    sessionPCs := getSessionPCs(sessionID)  // typically 1-10 PCs
    memories := make(map[UUID]NPCPCMemory)
    for _, pcID := range sessionPCs {
        pairID := npcPCMemoryID(npcID, pcID)
        memories[pcID] = loadAggregate("npc_pc_memory", pairID)
    }

    // Do NOT load memories of PCs not in this session
    // R7-L6 constraint: NPC in 1 session at a time → only session's PCs matter

    response := llm(npcCore, memories, sessionContext, currentSpeakerPCID)
    ...
}
```

With R7-L6 (NPC in one session at a time) + session cap (typically 5-10 PCs): max load per turn = 1 npc + ≤10 npc_pc_memory aggregates. **Bounded regardless of NPC's total interaction history.**

### 12H.7 Layer 6 — Embedding storage separation (pgvector)

Embeddings (~6KB each) are the biggest component of memory state. Keep them **outside aggregate snapshots** in a dedicated projection table:

```sql
CREATE TABLE npc_pc_memory_embedding (
  npc_id        UUID NOT NULL,
  pc_id         UUID NOT NULL,
  embedding     vector(1536),           -- pgvector
  content_hash  TEXT NOT NULL,          -- hash of what was embedded (for change detection)
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (npc_id, pc_id)
);
CREATE INDEX npc_pc_memory_embedding_hnsw
  ON npc_pc_memory_embedding USING hnsw (embedding vector_cosine_ops);
```

Aggregate events include `embedding_content_hash` and `embedding_update_token` references, not the vector itself. Actual vector in this projection table.

**Win:** snapshot size ~2KB per pair (vs ~15KB with embedded vector). 7× reduction on hot path.

**Trade:** extra lookup per turn for embedding. Fast (indexed, hot cache). Acceptable cost.

**Rebuild:** projection lost → re-run embedding generation from latest memory content (event-sourced: `npc_pc_memory.summary_rewritten` events trigger embedding refresh).

### 12H.8 Layer 7 — Observability

```
lw_npc_aggregate_count_per_reality                    gauge
lw_npc_pc_memory_aggregate_count_per_reality          gauge
lw_npc_pc_memory_snapshot_size_bytes                  histogram
lw_npc_pc_memory_fact_count                           histogram
lw_npc_pc_memory_seconds_since_interaction            histogram
lw_npc_pc_memory_archive_count_per_reality            counter
lw_npc_pc_memory_restore_count_per_reality            counter
lw_npc_memory_compaction_triggered_count              counter
```

**Alerts:**
- Snapshot size >1MB warn → review triggers
- Snapshot size >5MB critical → auto-compact fires
- High archive rate → possibly too aggressive
- High restore rate → many returning players after long absence

### 12H.9 Connection to A1 (NPC memory at scale)

[01_OPEN_PROBLEMS A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--open) was critical-path `OPEN`. With R8 resolution (this section), A1 moves to `PARTIAL`:

**What R8 provides (infrastructure):**
- Bounded state per (NPC, PC) pair
- Lazy loading (only session's PCs)
- Cold decay + archive for inactive pairs
- Separate embedding storage (pgvector)
- Size enforcement + auto-compaction

**What A1 still needs (semantic layer):**
- Retrieval quality: which facts to surface during prompt assembly?
- Summary quality: LLM prompt for compaction
- Fact extraction: what from an interaction becomes a "fact"?
- Evaluation: measurable success on real book data

R8 is the plumbing; A1 is the art. A1 design is deferred pending real data from V1 prototype.

### 12H.10 Capacity model

**Per NPC at maturity** (10K PCs interacted, with L4 decay applied):
- Active pairs (<30 days): ~100 × 2KB snapshot × 3 retained = 600KB
- Warming pairs (30-90d): ~500 × 1KB × 3 = 1.5MB
- Summary-only pairs (90-365d): ~2000 × 0.5KB × 3 = 3MB
- Archived pairs (>365d): 0 in Postgres (in MinIO)

**Total per hot NPC: ~5MB** (vs ~75MB naive). 15× reduction.

**Platform at V3** (1000 realities × 50 NPCs × ~20 active pairs avg):
- npc_pc_memory aggregate count: ~1M
- Avg snapshot size: ~2KB
- Platform storage: ~6GB npc_pc_memory across all realities
- Eminently manageable

### 12H.11 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 aggregate split | More aggregate rows (1 NPC → 1 npc + N npc_pc_memory); simpler loading |
| L2 bounded facts | Long-term detail loss (accepted; summary retains high-level memory) |
| L3 size enforcement | Auto-compaction may be aggressive; tunable |
| L4 cold decay | Returning player sees "less precise" memory after long absence; trade for storage |
| L5 lazy loading | Requires session scope discipline (already locked in R7-L6) |
| L6 embedding separation | Extra read per turn; major win on snapshot size |
| L7 observability | Metric cardinality per-pair (capped by reality) |

Main win: **linear scaling broken** — per-NPC cost bounded, grows with session participation not total history.

### 12H.12 Config keys (R8)

```
npc_memory.max_facts_per_pc = 100
npc_memory.summary_rewrite_every_events = 50
npc_memory.summary_max_length_chars = 2000
npc_memory.snapshot_size_warn_mb = 1
npc_memory.snapshot_size_critical_mb = 5
npc_memory.cold_decay_fact_drop_days = 30
npc_memory.cold_decay_embedding_drop_days = 90
npc_memory.archive_days = 365
```

### 12H.13 Implementation ordering

- **V1 launch**: L1 (aggregate split — foundational, must start correctly), L2 (bounded memory caps), L5 (lazy loading — already aligned with R7-L6), L6 (embedding separation), L7 (metrics)
- **V1 + 60 days**: L3 (size enforcement active when real data emerges), L4 (cold decay schedule)
- **V2**: Tune thresholds based on observed patterns
- **V3+**: Archive/restore flow matures for long-tail returning players

### 12H.14 Tooling surface (folded into DF9)

Admin + dev tooling for NPC memory:
- Memory size dashboard (top-N aggregates by size, trends)
- Manual compaction trigger (for specific pair)
- Archive/restore controls (per pair, bulk by NPC or by age)
- Memory content inspector (facts, summary, embedding heatmap)
- Decay schedule overview
- Compaction event log

**Folded into DF9** (Event + Projection + Publisher Ops). DF9 scope grows to **"Event + Projection + Publisher + NPC Memory Ops"** — all per-reality data-correctness ops in one admin surface. Avoids DF proliferation.

## 12I. Safe Reality Closure (R9 mitigation)

Closing a reality = DROP DATABASE = irreversible. One mistake destroys active world. Unlike other failure modes where retry recovers, here there is no retry. Replace the naive 1-step close flow in §7.3 with a multi-gate, multi-state, multi-day protocol that makes accidental data loss structurally impossible.

### 12I.1 Multi-stage close state machine

Replace single-step close with 6-state progression. **Minimum time from `active` to irreversible `dropped` is ~120 days.** Long enough to catch any mistake or undiscovered archive corruption.

```
┌────────┐ owner closes   ┌───────────────┐  30d cooling    ┌────────┐
│ active ├───────────────►│ pending_close │────automatic───►│ frozen │
└────────┘                └───────┬───────┘                 └────┬───┘
     ▲                            │ cancel (owner)               │ archive job
     │ reactivate (admin)         │                              │ (1-N hours)
     │                            ▼                              ▼
     │                     ┌────────┐              ┌────────────────┐
     └─────────────────────┤ active │              │   archived     │
                           └────────┘              │ (MinIO done,   │
                                                   │ not verified)  │
                                                   └───────┬────────┘
                                                           │ verify (L2)
                                                           ▼
                                                ┌────────────────────┐
                                                │ archived_verified  │
                                                └──────┬─────────────┘
                                                       │ rename DB
                                                       ▼
                                            ┌─────────────────┐
                                            │ soft_deleted    │
                                            │ (DB renamed,    │
                                            │  90d hold)      │
                                            └────────┬────────┘
                                                     │ double-approval + 90d elapsed
                                                     ▼
                                             ┌────────────┐
                                             │  dropped   │  FINAL
                                             └────────────┘  (DROP DATABASE executed)
```

**State durations:**
- `pending_close`: 30 days (cooling, cancellable by owner)
- `frozen`: hours to days (archive job). **⚠ Descendant severance fires at entry to this state — see [§12M](#12m-reality-ancestry-severance--orphan-worlds-c1-resolution).** Any live descendant reality that depends on this reality's events via cascade gets auto-snapshotted + marked `ancestry_status='severed'` before archive proceeds.
- `archived`: hours (verification)
- `archived_verified` → `soft_deleted`: prompt (DB rename)
- `soft_deleted`: 90 days (hold, double-approval window)
- Total minimum: ~120 days before `DROP DATABASE` executes

### 12I.2 Layer 1 — State machine schema

```sql
ALTER TABLE reality_registry
  ADD COLUMN status_transition_at TIMESTAMPTZ,
  ADD COLUMN close_initiated_by UUID,
  ADD COLUMN close_initiated_at TIMESTAMPTZ,
  ADD COLUMN close_reason TEXT,
  ADD COLUMN archive_verified_at TIMESTAMPTZ,
  ADD COLUMN archive_verification_id UUID,
  ADD COLUMN soft_delete_name TEXT,
  ADD COLUMN drop_scheduled_at TIMESTAMPTZ,
  ADD COLUMN drop_approved_by UUID,
  ADD COLUMN drop_approved_at TIMESTAMPTZ;

-- Status values now include:
-- 'active' | 'pending_close' | 'frozen' | 'archived' | 'archived_verified' | 'soft_deleted' | 'dropped' | 'closed' (legacy)
```

### 12I.3 Layer 2 — Archive verification gate (hard gate)

Before transition `archived → archived_verified`: prove archive is restorable via 5-step verification:

```
1. Checksum: all Parquet/dump files per-partition + manifest
2. Manifest completeness: verify all expected event_ids present in archive
3. Sample decode: pick 100 random events across archive, decode, check schema validity
4. Sample restore: restore 5 random aggregates (pc, npc, region) from archive to temp DB
5. Diff restored aggregates against current projection — must match exactly
```

Verification result recorded:
```sql
CREATE TABLE archive_verification_log (
  verification_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reality_id        UUID NOT NULL,
  verifier_id       TEXT NOT NULL,                -- service or admin that ran
  checks_passed     JSONB NOT NULL,
  status            TEXT NOT NULL,                -- 'passed' | 'failed' | 'inconclusive'
  failure_reason    TEXT,
  sample_size       INT,
  temp_db_host      TEXT,                         -- where sample restore ran
  verified_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Hard invariant**: no transition to `archived_verified` without `archive_verified_at IS NOT NULL` AND `archive_verification_log.status = 'passed'` AND `verified_at > close_initiated_at`. Enforced by check constraint.

Config:
```
reality.close.archive_verification_required = true
reality.close.archive_verification_sample_size = 100
```

### 12I.4 Layer 3 — Double confirmation (human gates)

**Initial close** (`active → pending_close`):
- Owner types reality name exactly (typed confirmation)
- Owner provides `close_reason` (min 20 chars)
- Single actor OK here (cooling + cancel catch mistakes)

**Drop confirmation** (`soft_deleted → dropped`):
- **Second approver required** (`drop_approved_by != close_initiated_by`) in production
- Second approver reviews: full audit trail, verification record, player communication log, 90d elapsed
- Approver types reality name to confirm
- Production enforcement via config

Config:
```
reality.close.require_double_approval_prod = true
reality.close.approver_cooldown_hours = 24       # different user & 24h minimum after initiator
```

### 12I.5 Layer 4 — Cooling period (reversibility window)

`pending_close` state: 30 days default. During this window:
- Writes REJECTED (reality is effectively frozen)
- Reads OK (player can finish reading/exploring, export via DF6)
- UI prominently shows "scheduled for closure on <date>"
- Owner can click "cancel close" → back to `active`

After 30 days + no cancel: auto-transition to `frozen`.

Config:
```
reality.close.cooling_period_days = 30
```

### 12I.6 Layer 5 — Player notification cascade

Outbound notifications on schedule:

| Trigger | Recipients | Channel |
|---|---|---|
| `active → pending_close` | All users with PCs in reality | In-app notification + email |
| T-7 days to freeze | Same | In-app reminder |
| T-1 day to freeze | Same | In-app reminder + email |
| `pending_close → frozen` | Same | Final notice |
| `archived → soft_deleted` | Same | "Data preserved for 90 days, recoverable by request" |

If DF6 (world travel) is available, notifications include link to export PCs.

Config:
```
reality.close.player_notification_schedule_days = "30,7,1"
```

### 12I.7 Layer 6 — Soft-delete via rename (not drop)

Instead of `DROP DATABASE` at `archived_verified → soft_deleted`:

```sql
ALTER DATABASE loreweave_world_<reality_id>
  RENAME TO _closed_<reality_id>_<YYYYMMDD>;
```

DB still exists, renamed + marked. Services remove connection pool entries. Metrics scrape target removed.

After 90 days + double-approval:
```sql
DROP DATABASE _closed_<reality_id>_<YYYYMMDD>;
```

**Benefit:** 90-day window where if corruption discovered or regret surfaces, admin can rename back + restore operations. True safety net.

Config:
```
reality.close.soft_delete_retention_days = 90
```

### 12I.8 Layer 7 — Emergency cancel (escape hatch)

At any pre-`dropped` state, cancel possible:

| From state | Cancel | Actor | Result |
|---|---|---|---|
| `pending_close` | "Cancel close" | Owner | → `active` (writes resume) |
| `frozen` | "Reactivate" | Owner or admin | → `active` (if archive not started) |
| `archived` / `archived_verified` | "Restore to frozen" | Admin (single) | → `frozen` (archive preserved) |
| `soft_deleted` | "Emergency restore" | Admin + second approver | → `archived_verified` (rename DB back) |
| `dropped` | Nothing | — | Only path: restore from MinIO archive into new reality_id |

UI: explicit "CANCEL CLOSE" button visible in all pre-drop states.

Config:
```
reality.close.emergency_cancel_enabled = true
```

### 12I.9 Layer 8 — Audit log (everything)

Every transition, cancel, verification, approval recorded:

```sql
CREATE TABLE reality_close_audit (
  audit_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reality_id        UUID NOT NULL,
  from_state        TEXT NOT NULL,
  to_state          TEXT NOT NULL,
  actor_id          UUID NOT NULL,
  action            TEXT NOT NULL,                -- 'transition' | 'cancel' | 'verify' | 'approve' | 'restore'
  payload           JSONB NOT NULL,               -- reason, approver_id, verification_id, etc.
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON reality_close_audit (reality_id, created_at);
```

DF11 admin dashboard reads this for per-reality timeline view.

### 12I.10 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 multi-stage state machine | More states + transitions; more code paths |
| L2 archive verification | Hours of compute per close (5-step drill); temp DB storage |
| L3 double confirmation | Closure process requires two humans + 24h cooldown |
| L4 cooling period | 30 days of DB + storage kept with no active use |
| L5 notification | Email/in-app infrastructure required |
| L6 soft-delete | 90 days of DB + disk kept per closure |
| L7 emergency cancel | More state transitions to handle in code |
| L8 audit log | Small table; 1 row per transition |

Total storage per closed reality: ~120 days of its size kept before drop. For dying realities this is acceptable — they were going away anyway.

### 12I.11 Config keys (R9)

```
reality.close.cooling_period_days = 30
reality.close.soft_delete_retention_days = 90
reality.close.archive_verification_required = true
reality.close.archive_verification_sample_size = 100
reality.close.require_double_approval_prod = true
reality.close.approver_cooldown_hours = 24
reality.close.player_notification_schedule_days = "30,7,1"
reality.close.emergency_cancel_enabled = true
```

### 12I.12 Implementation ordering

- **V1 launch**: L1 (state machine schema + transitions), L4 (cooling period), L6 (soft-delete rename via ALTER DATABASE), L7 (emergency cancel UI), L8 (audit log table + writes). Mandatory baseline — no shipping without these.
- **V1 + 30 days**: L2 (archive verification — before first real close)
- **V1 + 60 days**: L3 (double approval workflow), L5 (player notifications when notification infra ready)
- **V2+**: DF11 UI matures with close dashboard, verification viewer, emergency controls

### 12I.13 Interaction with other resolutions

- **R9 ↔ R1 archive** ([§12A.4](#12a4-layer-4--tiered-archive-pipeline)): R9 gates reality close on archive verification. Archive reliability (R1-L4) is foundational to R9 safety.
- **R9 ↔ R4 fleet** ([§12D.1](#12d1-layer-1--automated-provisioning--deprovisioning)): closure state transitions supersede the naive deprovisioning flow in §7.3 / §12D.1.
- **R9 ↔ R5 player index**: `player_character_index` rows retained after `dropped` state — user history preserved even when reality gone.
- **R9 ↔ DF6 world travel**: DF6 is the escape hatch for players who want to preserve PCs from closing realities (migrate to another reality).
- **R9 ↔ R2 rebuild** ([§12B.4](#12b4-layer-4--integrity-checker-drift-detection)): verification samples re-use rebuild logic to validate archives.

### 12I.14 Tooling surface (folded into DF11)

Admin UX for reality closure:
- Closure queue (per-state, countdowns, pending approvals)
- Verification results viewer (success/failure, sample details)
- Double-approval workflow (initiator sees pending, approver sees queue)
- Emergency cancel controls (per-state appropriate actions)
- Audit log viewer per reality (timeline of state transitions)
- Restore drill dashboard (manual re-verify, sample restore test)

**Folded into DF11** (Database Fleet Management). DF11 scope grows to **"Database Fleet + Reality Lifecycle Management"**. Natural fit with shard health + per-reality inspector.

## 12J. Global Event Ordering — Accepted Trade-off (R10)

Per-reality `event_id` is monotonic per-DB only; no global sequence across realities.

### 12J.1 Why this is accepted (not mitigated)

With R5 cross-instance live query REJECTED and analytics deferred indefinitely, **no product feature requires global event ordering**:

| Use case | Needs global order? |
|---|---|
| Realtime UX per session | No — intra-reality ordering sufficient |
| Canon propagation | No — causal ordering via `xreality.*` events |
| Replay one reality | No — reality-local order suffices |
| Admin "all events by user X" | Timestamp merge acceptable (rare) |
| Analytics aggregates | ETL merges by `created_at` — ordering fuzz OK |
| Legal discovery | Timestamp merge OK — not ordered-join |

Cost of mitigation (centralized sequencer, Lamport clocks, vector clocks) is high; product benefit is zero.

### 12J.2 Discipline required — timestamp hygiene

Must-haves (already required by other resolutions):
- All events have `created_at TIMESTAMPTZ NOT NULL` from Postgres server clock
- Postgres servers run NTP-synced (standard ops practice)
- Timestamps accurate to ~100ms across shards
- Sufficient for analytics-grade ordering when needed

No new code. No config keys. No tooling. Consciously accepted.

## 12K. pgvector Footprint Management (R11 mitigation)

pgvector per-reality (locked S2) produces many small vector indexes. Quantify at V3 scale; design for monitoring not mitigation.

### 12K.1 Capacity quantified

Per active reality (after R8-L6 embedding-in-separate-table):
- ~20 active NPCs × ~20 active pairs = 400 vectors/reality
- Vector size: 1536 float32 × 4 = 6KB raw
- Total raw: 2.4MB per reality
- HNSW index overhead ~30%: ~3MB
- **Per-reality total: ~6MB (data + index)**

V3 platform (1000 active on 4 servers @ 250 each):
- Per Postgres server: 250 × 6MB = **1.5GB pgvector in RAM**
- Large server (256GB RAM): 1.5GB = **<1% utilization**
- Concern: low

Frozen realities (10K): ~3MB each (after R8-L4 embedding drop for >90d), but cold — not loaded in buffer pool unless queried. No steady RAM cost.

**Conclusion:** pgvector footprint is a monitoring problem, not a design problem.

### 12K.2 Layer 1 — Embedding in separate table (done, R8-L6)

Already locked. Embeddings not in aggregate snapshots → query-time loading only.

### 12K.3 Layer 2 — HNSW index tuning

```sql
CREATE INDEX npc_pc_memory_embedding_hnsw
  ON npc_pc_memory_embedding USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

Parameters:
- `m = 16`: connections per layer, balanced recall vs memory
- `ef_construction = 64`: fast build, acceptable quality
- Query-time `ef_search` tunable per query (default 40)

For 400-vector indexes these defaults are overkill-safe.

### 12K.4 Layer 3 — Cold reality eviction (automatic)

Postgres handles this naturally. Frozen realities not queried → buffer pool doesn't keep pages hot. Cold-start penalty on first query ~50ms, acceptable.

No manual eviction code needed.

### 12K.5 Layer 4 — Memory monitoring

```
lw_pgvector_index_memory_bytes{shard_host, reality_id}   gauge
lw_pgvector_index_build_duration_seconds                  histogram
lw_pgvector_query_duration_seconds{reality_id}            histogram
lw_pgvector_recall_at_k                                   gauge (sampling-based)
```

**Alerts:**
- Per-shard pgvector memory > 10% of RAM → investigate
- Query p99 > 50ms → check index health
- Recall drift → reindex candidate

### 12K.6 Escape hatch — external vector store

Documented for future escalation if pgvector insufficient:
- Qdrant / Weaviate / Pinecone as out-of-band store
- Per-reality namespace
- Sync via event-handler consumer for `npc_pc_memory.summary_rewritten`

**Not V1.** Inline note documenting the path; promoted to ADR only if activated.

### 12K.7 Config keys (R11)

```
pgvector.hnsw.m = 16
pgvector.hnsw.ef_construction = 64
pgvector.hnsw.ef_search = 40
pgvector.memory_alert_pct_of_ram = 10
```

## 12L. Admin Tooling Discipline (R13 mitigation)

Most of R13 already addressed by DF9/DF10/DF11/DF13 tooling registrations. What remains is the **discipline layer**: guardrails, audit, compensating-event pattern, destructive-action confirmation.

### 12L.1 Layer 1 — Admin command library (canonical set)

All admin actions are named, reviewed, versioned commands in `services/admin-cli/commands/`. No ad-hoc SQL in production.

```
services/admin-cli/commands/
  reset_npc_mood.go           # documented, tested
  replay_dead_letter.go
  restore_pair_archive.go
  trigger_compaction.go
  force_close_reality.go      # requires double-approval (R9 pattern)
  ...
```

Every command:
- Named identifier (e.g. `admin/reset-npc-mood`)
- Typed parameter signature
- `--dry-run` preview mode (mandatory for destructive commands)
- Audit logs actor + parameters + result
- Docstring: what, when to use, reversibility

**Rule:** new ops need → new command, reviewed in PR. Never SSH into DB.

### 12L.2 Layer 2 — Compensating events (respect event sourcing)

Admin changes **emit events**, never raw UPDATE of projections:

```go
// REJECTED — violates event sourcing
UPDATE npc_projection SET mood='calm' WHERE npc_id = $1;

// REQUIRED — compensating event
AppendEvent(reality_id, "npc", npc_id, nextVersion, "npc.mood_admin_override", {
  new_mood: "calm",
  reason: "player reported stuck NPC — ticket LW-1234",
  actor_id: admin_user_id,
})
// Projection updated via normal flow
// Event auditable; reality rebuild preserves change
```

Admin-originated event types: `*.admin_override`, `*.admin_reset`, `*.admin_restore`. Distinctly typed so audit + replay can surface them.

### 12L.3 Layer 3 — Admin action audit log (centralized)

In meta registry (cross-reality full audit):

```sql
CREATE TABLE admin_action_audit (
  audit_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  command_name    TEXT NOT NULL,
  command_version TEXT NOT NULL,
  actor_id        UUID NOT NULL,
  reality_id      UUID,
  parameters      JSONB NOT NULL,
  result          JSONB,                         -- 'success' | 'dry_run' | 'error'
  error_detail    TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON admin_action_audit (actor_id, created_at);
CREATE INDEX ON admin_action_audit (reality_id, created_at);
```

Retention: 2 years minimum (configurable).

### 12L.4 Layer 4 — Destructive action confirmation

Commands marked `destructive: true` require interactive confirmation:

```
Command: admin/force-close-reality
Target reality: Tavern of Broken Crown (reality_id: abc-123)
  Active players: 15
  Events: 2.3M
  Archive status: not_started

This initiates the close state machine. Type reality name to confirm: _
```

Typed confirmation; no single-click destruction. Truly dangerous commands (bypass cooling, manual DROP) require double-approval (reuse R9 pattern).

### 12L.5 Layer 5 — Admin UI guardrails

All admin UIs (DF9/DF10/DF11/DF13) MUST:
- Show current state + predicted side effects before action
- Require `--dry-run` preview for destructive actions
- **Not expose raw destructive primitives** — no "DROP DATABASE" button, only safe state machine (R9)
- Show relevant audit trail alongside action form
- No free-form SQL editor in production (dev/staging only)

### 12L.6 Layer 6 — Rollback per action

Every command documents reversibility:
- **Reversible** — `--undo` flag available (emits compensating-compensating event)
- **One-way but semantic** — documented irreversible, extra confirmation
- **Structural** (migration, shard split) — not undone via admin CLI; use normal ops flow

Rollback via compensating events: emit opposite-effect event through same pipeline.

### 12L.7 Governance policy

Policy formalized at [`docs/02_governance/ADMIN_ACTION_POLICY.md`](../../02_governance/ADMIN_ACTION_POLICY.md):
- L1–L6 are requirements, not suggestions
- No ad-hoc SQL in production (code review rejects)
- New commands require PR review + dry-run test
- Dangerous command list maintained + double-approval gated
- Audit log retention + compliance requirements

### 12L.8 Config keys (R13)

```
admin.cli.require_dry_run_for_destructive = true
admin.cli.double_approval_commands = "force-close-reality,drop-database,purge-user-data,bypass-cooling,manual-drop-partition"
admin.audit.retention_days = 730     # 2 years minimum
```

### 12L.9 Implementation ordering

- **V1 launch**: L1 (command library skeleton with ~10 initial commands), L2 (compensating-event pattern in all admin ops), L3 (audit log table + writes), L4 (destructive confirmation for initial dangerous ops), governance policy published
- **V1 + 30 days**: L5 (admin UI guardrails as DF9/DF11 mature)
- **V1 + 60 days**: L6 (rollback/undo for reversible commands)
- **V2+**: Command library grows organically; new ops add commands, not SQL

## 12M. Reality Ancestry Severance — Orphan Worlds (C1 resolution)

**Origin:** SA+DE adversarial review 2026-04-24 surfaced C1 — cascade read broken when ancestor reality is archived/dropped. User proposed reframing as **gameplay feature**: "orphan worlds" — realities whose ancestry has faded from memory. Elegant resolution: turn tech constraint into in-world mystery.

### 12M.1 The problem C1 identified

Snapshot-fork cascade (§6, §7) lets descendants inherit events from ancestors up to fork point. When an ancestor reality closes per R9 (§12I) and its DB is dropped:
- Descendants' projection tables stay intact
- BUT cascade read into ancestor events fails
- Projection rebuild fails
- Cold aggregate load fails

The R9 120-day close floor doesn't help — descendants may live far longer than their ancestors.

### 12M.2 The solution — auto-severance at freeze

When an ancestor reality transitions `pending_close → frozen` in R9 state machine, **automatically sever all live descendants** before allowing ancestor to proceed to `archived`:

```
For each live descendant D where cascade_ancestors(D) contains frozen_reality_id:
  1. Force snapshot all D's aggregates at current version
     (ensures full state captured before ancestor vanishes)
  2. Store snapshots as D's "ancestry_severance_baseline"
  3. Update D's registry: ancestry_status='severed', severed_ancestor_reality_id,
       ancestry_severance_baseline_event_id
  4. Append to D's ancestry_fragment_trail (lore record)
  5. Emit event: reality.ancestry_severed (scope='reality', propagates to all D's sessions)
  6. Only after ALL descendants severed → ancestor proceeds to archived
```

Technically identical to MV9 auto-rebase but preserves descendant's reality_id + adds narrative framing.

### 12M.3 Schema

```sql
ALTER TABLE reality_registry
  ADD COLUMN ancestry_status TEXT NOT NULL DEFAULT 'intact',
    -- 'intact' | 'severed' | 'genesis' (no ancestor by design)
  ADD COLUMN ancestry_severed_at TIMESTAMPTZ,
  ADD COLUMN severed_ancestor_reality_id UUID,
  ADD COLUMN ancestry_severance_baseline_event_id BIGINT,
  ADD COLUMN ancestry_fragment_trail JSONB;
    -- Append-only. Array of severed ancestor references for lore display.
    -- e.g., [
    --   {"reality_id": "...", "severed_at": "2028-03-15",
    --    "narrative_name": "The First Age", "baseline_event_id": 1234567}
    -- ]
```

New event type: `reality.ancestry_severed`
```json
{
  "scope": "reality",
  "payload": {
    "severed_ancestor_id": "uuid",
    "severance_reason": "ancestor_closed",   // 'ancestor_closed' | 'user_requested'
    "baseline_event_id": 1234567,
    "narrative_text": "The Old Age has passed beyond memory..."
  }
}
```

### 12M.4 Cascade read — stops at severance

```python
def load_aggregate_state(aggregate_id, reality_id):
    r = lookup_reality(reality_id)

    if r.ancestry_status == 'severed':
        # Load baseline snapshot captured at severance
        base = load_baseline_snapshot(r.reality_id, r.ancestry_severance_baseline_event_id)
        # Apply only own events after severance point
        own_events = select_events(reality_id=r.reality_id,
                                    aggregate_id=aggregate_id,
                                    event_id__gt=r.ancestry_severance_baseline_event_id)
        return fold(base, own_events)
    else:
        # Standard cascade, stopping at first severed ancestor
        chain = walk_ancestors(r, stop_at_severance=True)
        events = collect_events_along_chain(chain, aggregate_id)
        return fold(events)
```

Severance is terminal — cascade never walks past a severed marker.

### 12M.5 Player notification cascade (extends R9-L5)

When ancestor enters `pending_close` (R9 state), notification fans out to descendant owners:

| Timing | Message |
|---|---|
| T-30d (ancestor enters pending_close) | "Reality <A> is scheduled for closure on YYYY-MM-DD. Your reality <D> will have its ancestry severed — events before that date will become unreadable. Current state is preserved. [Export event log] [View lore summary]" |
| T-7d | Reminder |
| T-1d | Final reminder |
| T=0 (ancestor reaches `frozen`, severance fires) | In-world narrative event in D: "The Old Age has passed beyond memory..." |

Owners cannot prevent (ancestor owner's right). They can export/document anything they want to preserve externally.

### 12M.6 Narrative framing — in-world event

The `reality.ancestry_severed` event is **user-visible** via DF5 session stream. Example narrator copy (configurable, localized):

- Short: "The Old Age has passed beyond memory."
- Poetic: "A profound quiet settles over the world. Ancient memories, once whispered among the oldest, fade into myth. What came before... is no longer known."
- Technical mode (admin/debug): "Reality <R_id> severed from ancestor <A_id> at event <E_id>."

Session LLM can elaborate: NPCs may react ("something feels different... like a dream I can't recall"), historian NPCs lose references, artifacts become mysterious.

### 12M.7 Discovery UI — ancestry fragment trail

Reality's "lore page" shows severance history:

```
The history of this world:
  🌀 The First Age    — severed 2028-03-15
  🌀 The Forgotten Era — severed 2030-01-10
  ⏳ The Current Age  — ongoing since 2030-01-10
```

Each entry has `narrative_name` (author-authored or LLM-generated). Clicking shows baseline snapshot fact summary but not event-level history (which is gone).

Reality browser filter: "Show worlds with severed ancestry" for players who want that narrative tone.

### 12M.8 Reversibility

- **During ancestor R9 cooling period** (`pending_close`, T≤30d): ancestor cancel → severance never fires. Safe.
- **After severance fired** (`frozen` state reached, descendants severed): **one-way operation.** Even if ancestor is restored via R9 emergency cancel, descendants remain severed.
  - Rationale: narrative event already broadcast to players. Reversing creates continuity mess. Cheaper to accept severance is final.
- Document as irreversible in DF9/DF11 admin UI.

### 12M.9 Interaction with MV9 auto-rebase

Both mechanisms produce similar technical state (flatten + detach). Difference:
- **MV9 auto-rebase**: triggers at fork depth > 5; creates new reality_id; no narrative framing; silent
- **12M severance**: triggers at ancestor close; preserves reality_id; narrative event + UX; gameplay layer

MV9 is a pure ops mechanism; §12M is a product mechanism. Both coexist. If a reality hits MV9 rebase first, its ancestry_fragment_trail gets `severance_reason='auto_rebase'` entry.

### 12M.10 Config

```
reality.severance.auto_trigger_on_ancestor_freeze = true
reality.severance.notification_advance_days = 30
reality.severance.narrative_event_enabled = true
reality.severance.baseline_snapshot_required = true   # hard invariant
reality.severance.narrative_text_mode = "poetic"      # 'short' | 'poetic' | 'technical'
```

### 12M.11 Implementation ordering

- **V1 launch**: L1 trigger mechanism + L2 schema + L3 baseline snapshot on severance + L4 cascade-read-with-severance logic + L7 minimal ancestry_fragment_trail
- **V1 + 30 days**: L5 player notification + L6 narrative event + UX
- **V2+**: Discovery UI (L7), filter in reality browser, lore page polish
- **V3+**: **DF14 Vanish Reality Mystery System** — pre-severance breadcrumb generation (see DF14)

### 12M.12 What this resolves

- **C1 cascade read into dropped ancestor**: MITIGATED. Cascade stops at severance.
- **R9 ancestor close blocked by descendants**: RESOLVED. Severance unblocks.
- **Cascade depth unbounded over time**: BOUNDED. Every severance truncates.
- **Simplifies M5 fork-depth concerns** (§12 previous): natural upper bound via severance lifecycle.

Gameplay bonus: "ancient worlds" become narratively richer. Mysteries naturally emerge (see DF14).

## 12N. Database Subtree Split Runbook (C2 resolution)

**Origin:** SA+DE adversarial review 2026-04-24 surfaced C2 — §12D.6 specifies split thresholds (50M events OR 500 concurrent players per subtree) but §12D.10 waves over the actual "how do you move a live reality DB from shard A to shard B" ops procedure. This section locks the concrete playbook.

### 12N.1 When does split actually fire?

| Scale | Split frequency | Impact |
|---|---|---|
| V1 (≤10 realities) | Never — threshold impossible to hit | Playbook is documented insurance |
| V2 (≤100 realities) | Very rare | Admin-scheduled maintenance window OK |
| V3 (1000+ realities) | Regular occurrence for popular realities | Near-zero-downtime required |

Strategy: **document V1/V2 playbook now (may never execute); design V3 automation when scale demands.**

### 12N.2 Two-tier approach

**Tier 1 — V1/V2:** Maintenance-window freeze-copy-cutover. Slow (5-45 min freeze) but safe, uses only Postgres-native tools.

**Tier 2 — V3+:** Logical replication + near-zero-downtime cutover (~30s freeze). Added when V1/V2 freeze becomes UX-unacceptable at scale.

### 12N.3 New `migrating` lifecycle state

```
active ──admin-initiates-split──► migrating ──success──► active (on target shard)
                                       │
                                       └──rollback──► active (on source shard, unchanged)
```

`migrating` is **distinct from R9 `frozen`** (close flow). Mutual exclusion enforced via state machine.

Schema:
```sql
-- Add 'migrating' to status enum
ALTER TABLE reality_registry
  ADD COLUMN migration_source_shard TEXT,
  ADD COLUMN migration_target_shard TEXT,
  ADD COLUMN migration_started_at TIMESTAMPTZ,
  ADD COLUMN migration_method TEXT;
    -- 'freeze_copy_cutover' | 'logical_replication'

CREATE TABLE reality_migration_audit (
  audit_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reality_id            UUID NOT NULL,
  from_shard            TEXT NOT NULL,
  to_shard              TEXT NOT NULL,
  method                TEXT NOT NULL,
  initiated_by          UUID NOT NULL,
  started_at            TIMESTAMPTZ NOT NULL,
  completed_at          TIMESTAMPTZ,
  status                TEXT NOT NULL,
    -- 'in_progress' | 'succeeded' | 'rolled_back' | 'failed'
  freeze_duration_seconds INT,
  rollback_reason       TEXT,
  payload               JSONB
);
CREATE INDEX ON reality_migration_audit (reality_id, started_at DESC);
```

### 12N.4 Tier 1 playbook — freeze-copy-cutover (V1/V2)

**Step-by-step runbook:**

```
Split reality R from shard_A to shard_B:

1. ADMIN INITIATES
   admin-cli shard-split --reality=R --target=shard_B --reason="..."
   Triggers R13-L4 destructive confirmation + shard capacity pre-check.

2. PRE-CHECK GATE
   ✓ Target shard has capacity (R4-L6 thresholds respected)
   ✓ Source shard healthy (no active ops / maintenance)
   ✓ Reality status='active' (not in R9 close, not in MV9 rebase, not in §12M severance, not in another migration)
   ✓ Target extensions available (pgvector, lz4, uuid-ossp)
   ✓ Target has matching schema version (instance_schema_migrations current)
   Abort on any failure.

3. PLAYER NOTIFICATION CASCADE (reuse R9-L5 pattern)
   T-30 min: in-app + email: "Reality will undergo brief maintenance (~5-15 min) at HH:MM"
   T-5 min: final reminder in active sessions
   T-0: freeze begins

4. ENTER migrating STATE (atomic)
   UPDATE reality_registry SET
     status = 'migrating',
     migration_source_shard = shard_A,
     migration_target_shard = shard_B,
     migration_started_at = now(),
     migration_method = 'freeze_copy_cutover'
   WHERE reality_id = R AND status = 'active';
   -- 0 rows affected → concurrent modification, abort

5. DRAIN IN-FLIGHT (timeout: 5 min hard)
   Wait until events_outbox.unpublished_count = 0
   Wait until publisher cursor caught up to head
   Wait until event-handler cursor caught up
   Wait until meta-worker cursor caught up
   If timeout → rollback (step 14)

6. SNAPSHOT SOURCE
   pg_dump -Fc (custom format, compressed) source DB → staging location
   Verify dump integrity (pg_restore --list)

7. RESTORE TO TARGET
   CREATE DATABASE loreweave_world_<reality_id>_new ON shard_B
   pg_restore into target DB
   Rebuild indexes (HNSW, standard btree)
   Pre-warm buffer pool (SELECT from hot tables)

8. TARGET INTEGRITY VERIFICATION (reuse R2-L4)
   ✓ Row counts per table match source exactly
   ✓ Sample 100 random aggregates: rebuild from events, diff vs projection → must match
   ✓ HNSW index queryable (SELECT with ANN query)
   ✓ Extensions all installed
   ✓ Schema migrations marker matches
   Abort + rollback on any failure.

9. ATOMIC REGISTRY CUTOVER (single transaction)
   BEGIN;
     UPDATE reality_registry SET
       db_host = shard_B,
       db_name = loreweave_world_<reality_id>_new,
       status = 'active',
       status_transition_at = now(),
       migration_source_shard = NULL,
       migration_target_shard = NULL,
       migration_started_at = NULL,
       migration_method = NULL
     WHERE reality_id = R AND status = 'migrating';
     -- 0 rows affected → concurrent modification, abort

     -- Update any cross-reality indexes (e.g., player_character_index already scoped)
     INSERT INTO reality_migration_audit (...) VALUES (...);
   COMMIT;

10. UPDATE ROUTING TABLES
    - pgbouncer: deregister source db entry, register target
    - Prometheus: update scrape target
    - Backup scheduler: re-register on target
    - Meta-worker cursors: update to target (cursor position already in dump)

11. RESUME CLIENT CONNECTIONS
    WebSocket server emits RECONNECT signal to clients of reality R
    Clients auto-reconnect via R6-L4 catchup protocol (transparent to user)

12. SAFETY HOLD ON SOURCE
    ALTER DATABASE source RENAME TO _split_<reality_id>_<YYYYMMDD>
    Remains on shard_A for 7 days (config: shard.split.source_retention_days)
    Allows emergency rollback if post-cutover corruption discovered

13. LOG + NOTIFY
    admin_action_audit (R13-L3): "shard-split succeeded for reality R"
    reality_migration_audit: status='succeeded', freeze_duration_seconds=X
    Player notification: "Maintenance complete. World restored."

14. ROLLBACK PATH (any step 5-9 failure)
    admin-cli shard-split-abort --reality=R
    UPDATE reality_registry SET status='active' WHERE reality_id=R AND status='migrating'
      -- Reality back on SOURCE (source unchanged throughout)
    DROP target DB (cleanup)
    reality_migration_audit: status='rolled_back', rollback_reason='...'
    Admin investigates, fixes, retries

15. FINAL DROP (T+7 days)
    Verify no post-cutover issues reported
    DROP DATABASE _split_<reality_id>_<YYYYMMDD> ON shard_A
    reality_migration_audit: final_drop_at=now()
```

**Freeze duration estimates:**

| Reality size | Events | Freeze time |
|---|---|---|
| Small | <1M events (~1GB) | ~5 minutes |
| Medium | ~10M events (~10GB) | ~15 minutes |
| Large | ~50M events (~50GB) | ~45 minutes |

### 12N.5 Tier 2 playbook — logical replication (V3+)

Planned extension. Reduces freeze from 5-45 min to ~30 seconds.

```
Split via logical replication:

1-3. Same pre-check + player notification (shorter: T-5 min warning, not T-30 min)

4. PREPARE TARGET
   CREATE DATABASE on shard_B
   Apply schema migrations (must match source version)
   Enable extensions (pgvector, etc.)

5. SET UP LOGICAL REPLICATION
   On source: CREATE PUBLICATION for all reality tables
   On target: CREATE SUBSCRIPTION from source
   Initial data sync begins

6. INITIAL SYNC + CATCHUP (may take hours for large DB)
   Monitor pg_stat_replication lag on source
   Target catches up; DDL changes prohibited during this window

7. PRE-CUTOVER TASKS (while still catching up)
   Rebuild HNSW indexes on target (BUILD in background)
   Verify sample aggregates (sample_size configurable)
   Pre-warm target buffer pool

8. WHEN LAG < 5s, BRIEF FREEZE (~30s total)
   Reject new writes on reality R
   Wait for final replication drain (lag = 0)
   Bump sequences on target (BIGSERIAL event_id — no auto-sync)
   Atomic registry cutover (step 9 from Tier 1)
   Unfreeze → writes go to target

9. REPLICATION TEARDOWN
   On target: DROP SUBSCRIPTION
   On source: DROP PUBLICATION
   Source DB renamed (same as Tier 1 step 12)

10. SAFETY HOLD + eventual DROP (same as Tier 1)
```

**Postgres logical replication caveats:**
- DDL not replicated → migrations must be on both servers pre-switchover
- Sequences not auto-synced → explicit bump post-cutover
- Some extensions partial (pgvector data replicates; HNSW index must rebuild on target)
- Per-table PUBLICATION entries required

**HNSW rebuild during step 7** (pre-cutover) minimizes freeze duration.

### 12N.6 Subtree split (multi-reality coordination)

R4-L6 threshold can trigger on subtree (reality + its children), not just single reality.

**V1/V2:** Sequential splits (one reality at a time, coordinated via admin-cli subtree mode). Each reality independently follows step 1-15. Slow but simple.

**V3+:** Parallel via logical replication. Single admin command `admin-cli subtree-split --root=R_root --target=shard_B` sets up N parallel replications. Coordinated cutover: all realities in subtree freeze simultaneously (brief), cutover atomically, unfreeze.

Locking: subtree-level advisory lock prevents concurrent ops across the chain.

### 12N.7 Interactions with other mechanisms

| Mechanism | Interaction |
|---|---|
| **R9 close flow** | Can't close during migration; mutual exclusion via status check |
| **R8 NPC memory aggregates** | All tables dumped together; atomic transfer |
| **R6 outbox + publisher** | Cursor state preserved in dump; publisher re-binds to target post-cutover |
| **R7 session queues** | `session_event_queue` dumped; sessions pause during freeze, resume after |
| **§12M severance** | Can't migrate during severance; mutual exclusion |
| **MV9 auto-rebase** | Can't migrate during rebase; mutual exclusion |
| **DF11 admin ops** | Migration status surfaces in fleet dashboard |
| **R5 meta registry cutover** | Single transaction for registry update (critical section) |
| **R13 admin audit** | All migration actions logged via compensating-event pattern |

### 12N.8 Configuration

```
shard.split.maintenance_window_required = true   # V1/V2: yes; V3+ with logical_replication: false
shard.split.notification_advance_minutes = 30    # T-30m warning (Tier 1); T-5m (Tier 2)
shard.split.freeze_timeout_minutes = 120         # hard stop before rollback
shard.split.source_retention_days = 7            # hold before source drop
shard.split.integrity_sample_size = 100          # aggregates verified post-restore
shard.split.method_default = "freeze_copy_cutover"   # V3+: "logical_replication"
shard.split.concurrent_per_platform_max = 2      # rate limit (ops review capacity)
shard.split.tier1_staging_path = "/var/loreweave/split-staging"   # for pg_dump
```

### 12N.9 Accepted trade-offs

| Cost | Justification |
|---|---|
| V1/V2 freeze duration (5-45 min) | Rare at scale; admin-scheduled; players notified 30 min in advance |
| 7-day source retention (storage) | Safety net if post-cutover corruption found |
| Reality unavailable during freeze | UX acceptable for rare event; R6-L4 catchup protocol restores transparent reconnect |
| Migration audit log growth | Negligible (1 row per migration) |
| V3 logical-replication complexity | Only activated when V1/V2 freeze becomes UX-unacceptable at scale |
| Rate limit (2 concurrent per platform) | Ops safety — avoids overwhelming SRE |

### 12N.10 Rollback safety

At any failure in steps 5-9 of Tier 1:
- Source DB **untouched throughout** (we only read from source)
- Target DB can be dropped cleanly (nothing references it yet)
- Registry reverts to `status='active'` on source (reality keeps running)
- No data loss possible

Post-cutover corruption (rare, detected in 7-day hold):
- Source DB still exists (renamed)
- Admin can emergency-rename source back to active name
- Registry update to point back to source
- Target dropped
- 7-day window is the safety margin

### 12N.11 Tooling (folded into DF11)

Admin UX for migration:
- Migration queue (pending, in-progress, completed per platform)
- Per-migration timeline view (which step, elapsed, ETA, freeze duration)
- Abort button (triggers rollback via step 14)
- Post-migration verification status dashboard
- Historical audit log viewer (`reality_migration_audit`)
- Shard capacity advisor (suggest which realities to migrate based on R4-L6 metrics)
- Subtree split planner (V3+)

**DF11 scope expands to "Database Fleet + Reality Lifecycle + Migration Management"**. Natural fit with shard health + per-reality inspector + R9 closure controls.

### 12N.12 Implementation ordering

- **V1 launch**: playbook documented + `admin-cli shard-split` command + `migrating` state in lifecycle + `reality_migration_audit` table. Trigger remains manual.
- **V1 + 90 days**: threshold monitoring (R4-L6 metrics alert when approaching)
- **V2**: DF11 UI for migration workflow (still admin-initiated, no auto-trigger)
- **V3+**: Tier 2 logical-replication mode; threshold-driven automation (within rate limits)

### 12N.13 What this resolves

- ✅ C2 concrete playbook — no more "waved over"
- ✅ Rollback path explicit + safe
- ✅ Integration with R6/R7/R8/R9/§12M/MV9 documented
- ✅ Scaling path to V3 outlined
- ✅ Admin tooling scope defined (DF11 expansion)
- ✅ State machine updated (`migrating` state)
- ✅ Subtree split coordination specified

Remaining open (V3-scale, not blocking V1/V2):
- Logical-replication implementation details (Postgres version requirements, tooling)
- Automated threshold-driven trigger logic
- Cross-subtree split coordination at scale

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

## 12P. L3 Override Reverse Index (C4 resolution)

**Origin:** SA+DE adversarial review 2026-04-24. M4 propagation (§9.8) works conceptually with passive read-through as default, BUT:
- §9.8.1 preview ("M realities overridden this attribute") requires counting overrides
- §9.8.3 force-propagate needs targeting query
- Naive implementation: walk cascade of every reality, check L3 events for attribute. O(realities × cascade_depth × events_per_attr).

At V3 (1000 realities × attribute pool × 20 overrides/reality avg), naive approach turns author edits into seconds-long UI blockers. Reverse index fixes this with O(1) lookup.

### 12P.1 The index

```sql
-- In meta registry (not in individual reality DBs — this is platform-wide routing)
CREATE TABLE l3_override_index (
  book_id              UUID NOT NULL,
  attribute_id         TEXT NOT NULL,          -- entity_id + ':' + attr_name, or canonical path
  reality_id           UUID NOT NULL,
  first_override_at    TIMESTAMPTZ NOT NULL,
  latest_override_event_id BIGINT,              -- points into reality's event stream
  PRIMARY KEY (book_id, attribute_id, reality_id)
);

CREATE INDEX l3_override_by_attribute
  ON l3_override_index (book_id, attribute_id);

CREATE INDEX l3_override_by_reality
  ON l3_override_index (reality_id);
```

### 12P.2 Size estimate (sanity check)

V3 scale:
- 1000 active realities × avg 20 overrides per reality = 20K rows per book
- Multiple books per platform (say 100 books on platform) = 2M rows total
- At ~100 bytes per row (with index overhead) = ~200MB

**Fits comfortably in meta Postgres.** Grows linearly with active overrides, not with total attributes.

### 12P.3 Maintenance — event-handler side effect

When reality R writes an L3 event that overrides attribute A (from book B):

```
event-handler processes L3 override event:
  1. Commit the L3 event to R's DB (normal R7 flow)
  2. Upsert into meta.l3_override_index:
     INSERT INTO l3_override_index
       (book_id, attribute_id, reality_id, first_override_at, latest_override_event_id)
     VALUES (B, A, R, first_at_or_existing, new_event_id)
     ON CONFLICT (book_id, attribute_id, reality_id) DO UPDATE
       SET latest_override_event_id = EXCLUDED.latest_override_event_id;
```

**Tombstone on reality close/drop:** R9 close flow (`archived → soft_deleted`) removes that reality's rows from the index. Ancestor severance (§12M) does NOT remove overrides (child inherits them from baseline snapshot).

**Compensating-event reverse:** if reality later writes an event that un-overrides (reverts to L2 default), emit `*.override_removed` event → delete from index row for (B, A, R).

### 12P.4 Query patterns served

**§9.8.1 preview count** (author about to edit attribute A in book B):
```sql
SELECT
  COUNT(*) FILTER (WHERE reality_id IN (active_realities)) AS overridden_active,
  COUNT(*) FILTER (WHERE reality_id IN (frozen_realities)) AS overridden_frozen,
  ...
FROM l3_override_index
WHERE book_id = $B AND attribute_id = $A;
```
O(1) with index. Instant UI.

**§9.8.3 force-propagate targeting** (author commits force edit):
```sql
-- Realities in book MINUS realities with override for this attribute
SELECT reality_id FROM reality_registry WHERE book_id = $B AND status = 'active'
EXCEPT
SELECT reality_id FROM l3_override_index WHERE book_id = $B AND attribute_id = $A;
```
Fast. Gives exact propagation target set.

**Per-reality drill-down** (§9.8.1):
```sql
SELECT reality_id, first_override_at, latest_override_event_id
FROM l3_override_index
WHERE book_id = $B AND attribute_id = $A;
```

### 12P.5 Consistency guarantees

Index is **eventually consistent** with reality DBs' L3 events (lag = meta-worker processing time, typically <5s).

Acceptable because:
- M4 passive read-through (default) doesn't depend on index (each reality reads canon via cascade independently)
- Preview shows approximate count — small lag doesn't mislead author
- Force-propagate is slow-path anyway (consent gates, compensating writes) — small lag tolerable

**If perfect consistency required** (rare): author preview can fall back to live per-reality query (slow but authoritative). Opt-in "sync refresh" button in preview UI.

### 12P.6 Failure modes + recovery

**Index corruption:** can be **rebuilt from events table** — walk all L3 events across all realities, re-populate index. Expensive (hours for V3 scale) but doable. Background job with progress metric.

**Meta outage during write:** index update lives in meta (not in reality DB). On meta outage, buffer L3 events in event-handler local queue, apply to index on recovery. Reuses degraded-mode buffer pattern from C3/§12O.8.

**Split-brain:** if multiple event-handler instances both update index for same (book, attr, reality), PRIMARY KEY + ON CONFLICT DO UPDATE is idempotent. Last-write-wins on `latest_override_event_id`.

### 12P.7 Config

```
l3_override_index.enabled = true
l3_override_index.rebuild_batch_size = 10000    # for admin rebuild command
l3_override_index.stale_warn_seconds = 30       # meta-worker lag alert
```

### 12P.8 Admin tooling (folded into DF9)

- Index health dashboard (size, recent writes, rebuild status)
- Admin-cli command `rebuild-l3-override-index --book=X` for repair
- Metric `lw_l3_override_index_size_rows` + `lw_l3_override_index_lag_seconds`

### 12P.9 Implementation ordering

- **V1 launch**: index table + event-handler side-effect maintenance + §9.8.1 preview using index
- **V1 + 30 days**: rebuild command + health dashboard
- **V2**: observability maturity + stale-query auto-refresh UI

### 12P.10 What this resolves

- ✅ §9.8.1 preview is O(1) not O(N) — instant UI
- ✅ §9.8.3 force-propagate targeting exact + fast
- ✅ Author edits scale to V3 without UI lag
- ✅ Recovery path via rebuild exists

Residual: compensating-event "un-override" semantics need DF3 design (when exactly does an L3 event count as removing an override vs modifying it). Deferred to DF3.

## 12Q. Lifecycle Transition Discipline (C5 resolution)

**Origin:** SA+DE adversarial review 2026-04-24. Reality lifecycle has ~6 state machines (R9 close, §12M severance, §12N migration, MV9 rebase, plus admin emergency actions). Multiple triggers (owner, admin, cron, automation) can race on same reality. Without explicit CAS (compare-and-swap) discipline, state may corrupt.

### 12Q.1 The risk

Example scenario:
1. Owner clicks "cancel close" at T=29d23h59m (reality in `pending_close`)
2. Cron fires 30d transition at T=30d
3. Both issue UPDATE on `reality_registry.status`
4. Whichever commits second silently overwrites the first

Rare but catastrophic: reality drops while owner expected it to be active.

### 12Q.2 Mandatory CAS pattern

**Every state transition MUST be a conditional UPDATE** with expected current status. 0 rows affected = concurrent modification → abort + optionally retry.

**Correct pattern:**
```sql
UPDATE reality_registry SET
  status = 'frozen',
  status_transition_at = now(),
  close_initiated_by = $admin_id
WHERE reality_id = $R
  AND status = 'pending_close'              -- ← CAS: expected current status
  AND status_transition_at = $expected_prev -- ← optional: fencing token for stricter check
;
-- If affected rows = 0: abort. Another transition already happened.
```

**Rejected pattern** (unconditional update):
```sql
UPDATE reality_registry SET status = 'frozen' WHERE reality_id = $R;
-- No way to detect concurrent modification. Silent corruption possible.
```

### 12Q.3 Helper function — `attempt_state_transition()`

All state transitions go through a single canonical helper in `contracts/meta/`:

```go
// Pseudocode
func AttemptStateTransition(
    realityID uuid.UUID,
    fromStatus, toStatus string,
    payload map[string]any,
) (*TransitionResult, error) {
    tx, _ := db.BeginTx(...)
    defer tx.Rollback()

    result, err := tx.Exec(`
        UPDATE reality_registry SET
          status = $2,
          status_transition_at = now(),
          -- additional fields from payload
          close_initiated_by = COALESCE($3, close_initiated_by),
          migration_source_shard = COALESCE($4, migration_source_shard),
          ...
        WHERE reality_id = $1 AND status = $5
    `, realityID, toStatus, payload[...], ..., fromStatus)

    rowsAffected, _ := result.RowsAffected()
    if rowsAffected == 0 {
        return nil, ErrConcurrentStateTransition
    }

    // Always log audit row in same transaction
    _, _ = tx.Exec(`
        INSERT INTO lifecycle_transition_audit
          (reality_id, from_status, to_status, actor_id, payload, succeeded)
        VALUES ($1, $2, $3, $4, $5, true)
    `, realityID, fromStatus, toStatus, actor, payload)

    return &TransitionResult{...}, tx.Commit()
}
```

**Rule:** NO code directly UPDATEs `reality_registry.status`. Every transition uses this helper. Code review enforces.

### 12Q.4 Transition audit log

Captures every attempted transition (success or concurrency conflict):

```sql
CREATE TABLE lifecycle_transition_audit (
  audit_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reality_id     UUID NOT NULL,
  from_status    TEXT NOT NULL,
  to_status      TEXT NOT NULL,
  actor_id       UUID NOT NULL,
  actor_type     TEXT NOT NULL,         -- 'owner' | 'admin' | 'system' | 'cron'
  succeeded      BOOLEAN NOT NULL,
  failure_reason TEXT,                  -- 'concurrent_modification' | 'invalid_transition' | ...
  payload        JSONB,
  attempted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON lifecycle_transition_audit (reality_id, attempted_at DESC);
CREATE INDEX ON lifecycle_transition_audit (succeeded, attempted_at) WHERE succeeded = FALSE;
```

Failed transitions are **valuable signal**:
- Frequent `concurrent_modification` on same reality → hot race condition to investigate
- Invalid transitions → code bug

### 12Q.5 Retry policy for concurrent conflicts

For cron-type triggers (idempotent, can retry):
```go
for attempt := 1; attempt <= 3; attempt++ {
    result, err := AttemptStateTransition(...)
    if errors.Is(err, ErrConcurrentStateTransition) {
        // Someone else made a transition; re-check current state
        currentStatus := GetRealityStatus(realityID)
        if currentStatus == desired_target {
            return // another actor already did what we wanted
        }
        // Otherwise: bail out, log, alert
        log.Warn("cron transition lost race", ...)
        return
    }
    break
}
```

For owner/admin-initiated transitions: **no retry** (they'd see the failure + current state, can decide again).

### 12Q.6 Explicit state transition graph

Valid transitions enforced at helper function level. Invalid transitions rejected regardless of CAS:

```
Valid transitions (enforced):
  active         → pending_close, migrating, rebasing
  pending_close  → active (cancel), frozen (cron auto)
  frozen         → archived (archive job), active (emergency cancel)
  archived       → archived_verified (verify OK), frozen (verify fail)
  archived_verified → soft_deleted (rename)
  soft_deleted   → dropped (double-approval + 90d), archived_verified (emergency restore)
  migrating      → active (cutover success OR rollback)
  rebasing       → active (new reality takes over)

Invalid examples (rejected by helper):
  active         → dropped     (must go through whole close flow)
  soft_deleted   → active      (must go through archived_verified)
  pending_close  → dropped     (skip states)
```

Helper maintains a transition map; rejects anything not in the map.

### 12Q.7 Concurrent lifecycle ops — mutual exclusion

Reality cannot be in multiple lifecycle ops simultaneously. Enforced via status check:

- Can't close (`pending_close`) while migrating (`migrating`)
- Can't migrate while severing (severance is transient, but status='migrating' check prevents race)
- Can't rebase while closing
- Admin emergency actions go through helper → mutual exclusion by CAS

### 12Q.8 Governance

New governance policy referenced from ADMIN_ACTION_POLICY.md:

> **Lifecycle Transition Rule:** All state transitions on reality_registry.status MUST use `AttemptStateTransition()` helper from `contracts/meta/`. Direct UPDATE of status column is forbidden in production code. Code review MUST reject PRs that violate this rule. Lint rule (grep-based) detects direct UPDATE patterns in CI.

Cross-linked from ADMIN_ACTION_POLICY §3.R2 (compensating events pattern) since state transitions that write additional compensating events follow same discipline.

### 12Q.9 Monitoring

```
lw_lifecycle_transition_count{from, to, succeeded}       counter
lw_lifecycle_transition_conflict_count{reality_id}       counter
lw_lifecycle_transition_invalid_count{from, to}          counter
```

**Alerts:**
- High conflict rate on a single reality → investigate (multiple admins? buggy cron?)
- Any invalid transition attempt → page (code bug)

### 12Q.10 Config

No runtime config needed — discipline is code-enforced via helper + lint.

### 12Q.11 Implementation ordering

- **V1 launch**: `AttemptStateTransition()` helper + `lifecycle_transition_audit` table + all existing R9/§12M/§12N flows migrated to use helper + lint rule in CI
- **V1 + 30 days**: audit dashboard in DF11 (conflict heatmap)
- **V2+**: governance policy addendum if additional state machines emerge

### 12Q.12 What this resolves

- ✅ Race conditions on reality status eliminated by CAS
- ✅ Invalid transitions rejected structurally
- ✅ Full audit trail of every attempted transition (including failures)
- ✅ Mutual exclusion between concurrent lifecycle ops explicit
- ✅ Governance + lint enforces discipline

Residual:
- Helper covers reality_registry.status only. Other stateful objects (pc_projection.status, session status, etc.) may need similar discipline. Apply same pattern as they emerge.

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
