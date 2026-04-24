<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R09_safe_reality_closure.md
byte_range: 116616-130041
sha256: 879feef837febe2e99c05b0ebd5e544f22935d189be4b6f886e733b58549161a
generated_by: scripts/chunk_doc.py
-->

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

