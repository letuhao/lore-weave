<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R06_R12_publisher_reliability.md
byte_range: 80681-90615
sha256: d8f36513ecedaba5c187fbdaba950507e7e472f4b9611aef447b56478b2befb3
generated_by: scripts/chunk_doc.py
-->

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

