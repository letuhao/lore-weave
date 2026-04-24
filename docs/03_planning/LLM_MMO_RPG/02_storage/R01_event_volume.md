<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R01_event_volume.md
byte_range: 34183-45573
sha256: 668e136f1fbf07086fffcb9d9da32642772f432e20695be3a2741e99c1bbb046
generated_by: scripts/chunk_doc.py
-->

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

