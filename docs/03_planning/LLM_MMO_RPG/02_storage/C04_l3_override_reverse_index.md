<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: C04_l3_override_reverse_index.md
byte_range: 174364-180485
sha256: 4fba4fe2698a0c98f8b44f13b7414a3a15f581a2c9c16b8f5ca108d5c7536a7c
generated_by: scripts/chunk_doc.py
-->

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

