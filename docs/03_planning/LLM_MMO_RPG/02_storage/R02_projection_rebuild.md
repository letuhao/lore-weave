<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R02_projection_rebuild.md
byte_range: 45573-51819
sha256: f9f6ccc67063ba74f9214be8d02aaeae92d33f38a12288d295fc5b1a45dbce72
generated_by: scripts/chunk_doc.py
-->

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

