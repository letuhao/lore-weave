<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S04_meta_integrity.md
byte_range: 221774-236842
sha256: ed13f98f42e9ce7bab5910e7ca007e2c2c9328087397ab62413a458462428c13
generated_by: scripts/chunk_doc.py
-->

## 12T. Meta Integrity & Access Control — S4 Resolution (2026-04-24)

**Origin:** Security Review S4 — meta registry as trust root. C3 HA ensures availability; C5 CAS covers lifecycle status only; R13 admin audit covers command-level admin actions. **Broad meta-write surface remained un-audited.** S4 closes the gap with 7-layer strategy generalizing C5's CAS pattern to ALL meta writes.

### 12T.1 Threat model specifics

Meta-registry compromise enables:

| Attack primitive | Enabled by | Impact |
|---|---|---|
| Routing redirect | Flip `reality_registry.db_host` | All reality traffic → attacker shard |
| Status DoS | Mass `status='frozen'` | Platform-wide outage |
| Identity manipulation | Alter `player_character_index` | Impersonation, cross-user data leak |
| Audit evasion | Delete audit rows | Hide attacker tracks |
| Privilege forgery | Insert fake audit entries | "Authorize" actions |
| Canon poisoning | Inject `canon_change_log` | Book canon corrupted |
| Rate-limit bypass | Reset `user_reality_creation_quota` | DOS via creation spam |

### 12T.2 Layer 1 — Canonical `MetaWrite()` helper (generalizes §12Q)

All meta-table writes MUST go through single canonical helper:

```go
// contracts/meta/metawrite.go
//
// Generalization of §12Q AttemptStateTransition — covers ALL meta writes.
func MetaWrite(ctx Context, w MetaWriteIntent) (*MetaWriteResult, error) {
    // w contains: table, operation, pk, expected_before, new_values,
    //             actor_type, actor_id, reason, request_context

    tx := db.BeginTx()
    defer tx.Rollback()

    // 1. Validate input (schema CHECK constraints handle remainder at DB level)
    if err := w.Validate(); err != nil {
        return nil, err
    }

    // 2. Optional concurrency CAS (for UPDATE with expected_before)
    if w.Operation == UPDATE && w.ExpectedBefore != nil {
        // CAS UPDATE ... WHERE pk = :pk AND <columns match expected_before>
    }

    // 3. Perform the write
    result, err := tx.Exec(w.BuildSQL())
    if err != nil { return nil, err }

    // 4. Audit row in SAME transaction
    _, _ = tx.Exec(`
        INSERT INTO meta_write_audit
          (table_name, operation, row_pk, before_values, after_values,
           actor_type, actor_id, reason, request_context)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    `, ...)

    return result, tx.Commit()
}
```

**§12Q `AttemptStateTransition()` becomes a specialization** — wraps `MetaWrite()` with additional transition-graph validation + mutual exclusion.

```go
// §12Q AttemptStateTransition post-refactor
func AttemptStateTransition(realityID UUID, fromStatus, toStatus string, ...) (*TransitionResult, error) {
    // Transition-graph validation (§12Q.6)
    if !isValidTransition(fromStatus, toStatus) { return nil, ErrInvalidTransition }
    if conflictsWithOtherLifecycleOp(realityID) { return nil, ErrMutualExclusion }

    // Delegate to MetaWrite (gets free CAS + audit)
    return MetaWrite(ctx, MetaWriteIntent{
        Table: "reality_registry",
        Operation: UPDATE,
        PK: map[string]any{"reality_id": realityID},
        ExpectedBefore: map[string]any{"status": fromStatus},
        NewValues: map[string]any{"status": toStatus, ...},
        ...
    })
}
```

**Rule:** NO service writes directly to meta tables. All through `MetaWrite()`. Lint rule forbids direct SQL writes in production code.

### 12T.3 Layer 2 — Schema invariants as CHECK constraints

Encode business rules at DB layer — defense against both application bugs and malicious writes:

```sql
-- reality_registry integrity
ALTER TABLE reality_registry ADD CONSTRAINT db_host_valid_pattern
  CHECK (db_host IS NULL OR db_host ~ '^pg-shard-[0-9]+\.(internal|prod|staging)$');

ALTER TABLE reality_registry ADD CONSTRAINT status_valid
  CHECK (status IN ('provisioning', 'seeding', 'active', 'pending_close',
                    'frozen', 'migrating', 'archived', 'archived_verified',
                    'soft_deleted', 'dropped'));

ALTER TABLE reality_registry ADD CONSTRAINT locale_valid
  CHECK (locale ~ '^[a-z]{2}(-[A-Z]{2})?$');

ALTER TABLE reality_registry ADD CONSTRAINT session_caps_bounded
  CHECK (session_max_pcs BETWEEN 1 AND 50
     AND session_max_npcs BETWEEN 0 AND 50
     AND session_max_total BETWEEN 2 AND 100);

-- player_character_index
ALTER TABLE player_character_index ADD CONSTRAINT status_valid
  CHECK (status IN ('active', 'offline', 'hidden', 'npc_converted', 'deceased', 'deleted'));

-- Apply to all meta tables as relevant
```

Attacker with direct DB write access still cannot inject invalid values. Belt + suspenders with L1.

### 12T.4 Layer 3 — Append-only audit tables

Audit tables must resist UPDATE/DELETE by application roles:

```sql
-- Revoke mutation permissions on audit tables from application roles
REVOKE UPDATE, DELETE ON
  admin_action_audit,
  reality_close_audit,
  reality_migration_audit,
  lifecycle_transition_audit,
  meta_write_audit,
  meta_read_audit,
  archive_verification_log
FROM app_service_role, app_admin_role;

-- Only dedicated audit_retention role can DELETE, for scheduled cleanup
CREATE ROLE audit_retention_role;
GRANT DELETE ON <all audit tables> TO audit_retention_role;

-- Retention cron uses this role; its DELETE calls go through MetaWrite,
-- which itself writes an audit row (self-audited retention)
```

**V1**: Postgres REVOKE + retention role + self-audited cleanup.

**V2+**: detached old audit partitions → MinIO Object Lock (WORM) + periodic hash-chain checkpoint for tamper detection.

### 12T.5 Layer 4 — `meta_write_audit` table

```sql
CREATE TABLE meta_write_audit (
  audit_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name       TEXT NOT NULL,
  operation        TEXT NOT NULL,              -- 'INSERT' | 'UPDATE' | 'DELETE'
  row_pk           JSONB NOT NULL,             -- primary key of affected row
  before_values    JSONB,                      -- full row before (NULL for INSERT)
  after_values     JSONB,                      -- full row after (NULL for DELETE)
  actor_type       TEXT NOT NULL,              -- 'admin' | 'system' | 'service' | 'retention_cron'
  actor_id         TEXT NOT NULL,              -- admin user_id, service name, cron id
  reason           TEXT,                       -- caller-provided context
  request_context  JSONB,                      -- trace_id, request_id, source service
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON meta_write_audit (table_name, created_at DESC);
CREATE INDEX ON meta_write_audit (actor_id, created_at DESC);
CREATE INDEX ON meta_write_audit (created_at) WHERE actor_type = 'admin';

-- Partition by month for retention management
-- (partitioning omitted in this SQL snippet; follow §11 pattern)
```

**Retention:** 5 years (exceeds R13's 2-year admin_action_audit because meta writes are higher-stakes for compliance/forensics).

### 12T.6 Layer 5 — `meta_read_audit` for sensitive queries

Not all reads — only enumerated sensitive paths (performance-conscious):

```sql
CREATE TABLE meta_read_audit (
  audit_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_type     TEXT NOT NULL,               -- enumerated: 'player_index_cross_user', 'audit_query', 'admin_bulk_export', ...
  parameters     JSONB,
  actor_id       TEXT NOT NULL,
  result_count   INT,                          -- flag if unexpectedly large
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON meta_read_audit (actor_id, created_at DESC);
CREATE INDEX ON meta_read_audit (query_type, created_at DESC);
```

**Sensitive-read enumeration (V1):**
- `player_character_index` lookup by non-owner user_id
- Any query on audit tables (admin investigation, compliance reads)
- Bulk queries on any meta table (LIMIT > 1000, or no WHERE filter)
- Explicit admin export commands (via admin-cli)

Security team maintains enumeration; quarterly review. Non-listed reads pass through unaudited.

**Retention:** 2 years.

### 12T.7 Layer 6 — Anomaly detection + monitoring

Metrics added to DF9/DF11 admin dashboards + SRE alerting:

```
-- Write rate by table + actor type
lw_meta_write_rate{table_name, actor_type}                   gauge
lw_meta_write_by_actor{actor_id, table_name}                 counter

-- Routing changes (high-sensitivity)
lw_meta_routing_db_host_changes_total                        counter
-- Bulk reads
lw_meta_bulk_read_count{query_type}                          counter
-- Audit integrity
lw_meta_audit_row_count_daily_delta{table_name}              gauge (expected growth)
-- Out-of-scope access (service writes to a table it doesn't normally)
lw_meta_out_of_scope_write{service, table_name}              counter
```

**Alerts (tunable):**
- `db_host` change without matching `migrating` state → **PAGE SRE** (suspected routing attack)
- admin_action_audit row without meta_write_audit companion → **PAGE** (data divergence)
- Bulk read count spike (> 5σ above 7-day baseline) → investigate
- Service writes table outside its L7 scope → investigate
- Audit row count drops (> 1% daily decline) → **PAGE** (tamper suspect)

### 12T.8 Layer 7 — Least-privilege service roles

Each service has its own Postgres role with minimal permissions:

| Service role | SELECT | INSERT | UPDATE |
|---|---|---|---|
| `world_service_role` | reality_registry, player_character_index, session_participants | session_participants, lifecycle_transition_audit, meta_write_audit (via MetaWrite) | reality_registry (status via MetaWrite) |
| `roleplay_service_role` | reality_registry | meta_write_audit (via MetaWrite) | — |
| `publisher_role` | reality_registry, events_outbox (reality DB — per-reality role) | publisher_heartbeats, meta_write_audit | publisher_heartbeats |
| `meta_worker_role` | reality_registry | canon_change_log, l3_override_index, meta_write_audit | reality_registry.last_stats_updated_at, l3_override_index |
| `event_handler_role` | reality_registry, events (reality DB) | event_handler_cursor, l3_override_index, meta_write_audit | event_handler_cursor |
| `migration_orchestrator_role` | reality_registry, instance_schema_migrations | reality_migration_audit, meta_write_audit | reality_registry (migration fields via MetaWrite) |
| `admin_cli_role` (elevated) | ALL | ALL via MetaWrite (dangerous cmds require double-approval per R13) | ALL via MetaWrite |
| `audit_retention_role` | audit tables | meta_write_audit | DELETE on audit tables only (via MetaWrite self-audit) |

Setup:
```sql
-- On DB provisioning, create roles
CREATE ROLE world_service_role WITH LOGIN PASSWORD :wsr_secret;
GRANT CONNECT ON DATABASE meta_registry TO world_service_role;
GRANT SELECT ON reality_registry, player_character_index, session_participants TO world_service_role;
GRANT INSERT ON session_participants, lifecycle_transition_audit, meta_write_audit TO world_service_role;
GRANT UPDATE (status, status_transition_at, ...) ON reality_registry TO world_service_role;
-- etc.
```

**Benefit:** leaked credential limits blast radius to that role's scope. Attacker with `publisher_role` can't touch player_character_index.

### 12T.9 Interactions with existing mechanisms

| Section | Interaction |
|---|---|
| **§12Q C5 CAS** | MetaWrite generalizes it — §12Q wraps MetaWrite with transition-graph validation |
| **§12L R13 admin discipline** | Complementary — admin_action_audit records command-level intent; meta_write_audit records data-level writes. Admin command = 1 admin_action_audit + N meta_write_audit rows |
| **§12O C3 Meta HA** | Complementary — HA ensures availability; S4 ensures integrity + access control |
| **§12R P2 admin command discovery** | Each command declares its meta-table scope → informs L7 role requirements |
| **S1 rate limit** | user_reality_creation_quota writes via MetaWrite — auditable |
| **R13 governance** | ADMIN_ACTION_POLICY extended to cover S4 rules (direct SQL forbidden, MetaWrite required) |

### 12T.10 Configuration

```
meta.writes.helper_enforced = true                      # L1 lint-checked
meta.audit.write.retention_days = 1825                  # 5 years (L4)
meta.audit.read.retention_days = 730                    # 2 years (L5)
meta.audit.read.sensitive_paths_config_path = "/etc/lw/meta-sensitive-read-paths.yml"
meta.audit.append_only_enforced = true                  # L3
meta.monitoring.anomaly_detection_enabled = true
meta.monitoring.routing_change_alert_severity = "page"
meta.monitoring.audit_divergence_alert_severity = "page"
meta.monitoring.bulk_read_baseline_window_days = 7
meta.monitoring.audit_daily_delta_threshold_pct = 1     # alert on > 1% daily drop

meta.roles.service_scoped = true                        # L7 enforced
```

### 12T.11 Implementation ordering

- **V1 launch (mandatory):**
  - L1 MetaWrite helper + §12Q refactored as specialization
  - L2 CHECK constraints on reality_registry, session_participants, player_character_index
  - L3 REVOKE UPDATE/DELETE on all audit tables + audit_retention_role
  - L4 meta_write_audit table + MetaWrite emits audit rows
  - L7 per-service Postgres roles with least-privilege grants
  - Lint rule in CI forbidding direct SQL writes on meta tables
  - Governance policy (ADMIN_ACTION_POLICY) amendment: MetaWrite required
- **V1 + 30 days:**
  - L5 meta_read_audit + sensitive-path enumeration
  - L6 basic anomaly metrics (rate + routing change alerts)
- **V1 + 60 days:**
  - L6 full anomaly detection suite (bulk reads, out-of-scope, audit divergence)
- **V2+:**
  - L3b WORM via MinIO Object Lock for archived audit partitions
  - L3c Hash-chain for tamper detection on audit tables
  - Advanced ML-based anomaly detection

### 12T.12 What this resolves

- ✅ **Meta write audit gap**: all writes auditable via canonical helper + append-only table
- ✅ **Audit tamper resistance**: Postgres REVOKE + self-audited cleanup; V2+ WORM for compliance
- ✅ **Schema-layer integrity**: CHECK constraints reject malformed writes even from malicious sources
- ✅ **Credential blast radius**: L7 per-service roles bound damage from leaked credentials
- ✅ **Detection**: L6 anomaly monitoring surfaces attacks in real-time
- ✅ **Compliance posture**: stronger audit chain for SOC 2 / ISO 27001 / GDPR forensics
- ✅ **C5 generalization**: §12Q becomes special case of MetaWrite — unified audit discipline

**Residuals (acceptable V1):**
- L3b WORM deferred V2+ (Postgres REVOKE sufficient for active ops; WORM for cold archive)
- L3c hash-chain deferred V2+ (append-only + monitoring catches most tamper; hash-chain is belt+suspenders)
- ML-based anomaly detection V2+ (V1 uses threshold alerts)
- Read audit performance overhead mitigated by enumerated sensitive paths only

