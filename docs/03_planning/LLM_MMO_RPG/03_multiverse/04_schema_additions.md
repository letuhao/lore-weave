<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 04_schema_additions.md
byte_range: 16089-20776
sha256: 78fe1b20a6f0a36aa66c8360029c9550a6b7bf398108a45ae8f285063820cf71
generated_by: scripts/chunk_doc.py
-->

## 8. Schema additions vs 02

[02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) described the engineering baseline. Multiverse model requires these schema adjustments:

### 8.1 Events: add `reality_id` + reserve travel origin fields

```sql
ALTER TABLE events
  ADD COLUMN reality_id UUID NOT NULL;

-- PK changes from (aggregate_type, aggregate_id, aggregate_version)
--                to (reality_id, aggregate_type, aggregate_id, aggregate_version)
-- Monotonic version is per (reality, aggregate), not global.

CREATE INDEX events_reality_idx ON events (reality_id, created_at);
CREATE INDEX events_reality_aggregate_idx
  ON events (reality_id, aggregate_type, aggregate_id, aggregate_version);
```

**Event metadata reserves P4 travel-origin fields** (MV5 primitive). The `metadata` JSONB in [02 §4.3](02_STORAGE_ARCHITECTURE.md) is extended with optional keys, ignored in V1 but reserved for future world-travel:

```json
{
  "actor": { "type": "user", "id": "..." },
  "causation_id": "...",
  "correlation_id": "...",
  "source": "world-service",
  "occurred_at": "...",
  "instance_clock_tick": 12345,

  // Reserved for future world-travel feature — nullable, unused in V1
  "travel_origin_reality_id": null,
  "travel_origin_event_id": null
}
```

Consumers must tolerate absent keys. Reserving the key names now prevents every consumer from needing a schema-version check when travel lands.

### 8.2 Projections: add `reality_id`

Every projection table gains `reality_id` as part of its primary key:

```sql
ALTER TABLE pc_projection DROP CONSTRAINT pc_projection_pkey;
ALTER TABLE pc_projection ADD COLUMN reality_id UUID NOT NULL;
ALTER TABLE pc_projection ADD PRIMARY KEY (pc_id, reality_id);

-- Same for npc_projection, region_projection, world_kv_projection, etc.
```

### 8.3 Reality registry

```sql
CREATE TABLE reality_registry (
  reality_id              UUID PRIMARY KEY,
  book_id                 UUID NOT NULL,
  name                    TEXT NOT NULL,
  locale                  TEXT NOT NULL,           -- P1: e.g. 'en', 'vi', 'zh' — must exist from V1 for future world-travel
  seeded_from             TEXT NOT NULL,           -- 'book' | 'reality' | 'rebase_snapshot'
  parent_reality_id       UUID REFERENCES reality_registry,
  fork_point_event_id     BIGINT,                  -- NULL if seeded_from='book' or 'rebase_snapshot'
  rebase_source_reality_id UUID,                   -- audit trail when seeded_from='rebase_snapshot'
  fork_type               TEXT,                    -- 'auto_capacity' | 'user_initiated' | 'author_genesis' | 'auto_rebase'
  status                  TEXT NOT NULL,           -- 'created' | 'active' | 'frozen' | 'archived' | 'closed'
  divergence_type         TEXT,                    -- 'capacity_split' | 'narrative_branch' | 'private_session' | 'fresh_seed'
  player_cap              INT NOT NULL DEFAULT 100,
  current_player_count    INT NOT NULL DEFAULT 0,
  canonicality_hint       TEXT,                    -- 'canon_attempt' | 'divergent' | 'pure_what_if' — UI hint only
  db_host                 TEXT NOT NULL,
  db_name                 TEXT NOT NULL,
  schema_version          TEXT NOT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_heartbeat_at       TIMESTAMPTZ,
  last_activity_at        TIMESTAMPTZ,              -- drives freeze/archive lifecycle
  frozen_at               TIMESTAMPTZ,              -- when status transitioned to 'frozen'

  CHECK (
    (seeded_from = 'book' AND parent_reality_id IS NULL AND fork_point_event_id IS NULL) OR
    (seeded_from = 'reality' AND parent_reality_id IS NOT NULL AND fork_point_event_id IS NOT NULL) OR
    (seeded_from = 'rebase_snapshot' AND parent_reality_id IS NULL AND rebase_source_reality_id IS NOT NULL)
  )
);

CREATE INDEX ON reality_registry (book_id, status);
CREATE INDEX ON reality_registry (parent_reality_id);
CREATE INDEX ON reality_registry (status, last_activity_at);  -- freeze/archive scanner
```

Notes:
- No `depth` column — depth is meaningless in peer model.
- `locale` is required at creation; cannot be NULL. Set to book's default locale or user's choice.
- `rebase_snapshot` seeding is a third mode, used by auto-rebase at depth limit (§12.3).

### 8.4 Canon lock level on glossary/knowledge

```sql
-- In glossary-service (or wherever canonical facts are stored)
ALTER TABLE entity_attributes ADD COLUMN canon_lock_level SMALLINT NOT NULL DEFAULT 2;
-- 1 = L1 axiomatic (never drifts in any reality; enforced globally)
-- 2 = L2 seeded canon (default, reality can override via L3 events)
```

