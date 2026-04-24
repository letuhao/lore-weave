<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: C05_lifecycle_cas.md
byte_range: 180485-189001
sha256: 4badc7eb28719508586cf45ff18d3e0fbff96269a7fcd2423f47fb00ed3cf019
generated_by: scripts/chunk_doc.py
-->

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

> **Note (S4-D1):** post-S4 2026-04-24, `AttemptStateTransition()` is a **specialization of the general `MetaWrite()` helper** (see [§12T.2](#12t2-layer-1--canonical-metawrite-helper-generalizes-12q)). It adds transition-graph validation + mutual-exclusion checks on top of MetaWrite's audit + validation. All meta writes (not just state transitions) now go through the general helper pattern.

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

