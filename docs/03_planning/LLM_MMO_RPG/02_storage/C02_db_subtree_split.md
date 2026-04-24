<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: C02_db_subtree_split.md
byte_range: 147656-161828
sha256: d12481217573e5a5be672c92ddca3018c0ad27890e2c88b92a7230a43296949b
generated_by: scripts/chunk_doc.py
-->

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

