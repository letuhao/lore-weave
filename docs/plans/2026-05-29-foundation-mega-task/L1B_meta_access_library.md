# L1.B — Meta Access Library (Go `contracts/meta/`)

> **Parent:** [L1_db_physical_meta.md](L1_db_physical_meta.md)
> **Depth target:** B (artifact-level)
> **Status:** DRAFT — first-pass artifact enumeration

---

## §1. What it is

`contracts/meta/` is the **canonical Go library** that EVERY service imports to access `loreweave_meta`. There is no `meta-service` standalone — meta access is library-level per C03 §12O.5 (rationale: hot path, avoid extra network hop).

**Hard rule (I8):** NO service writes directly to meta tables. All writes go through `MetaWrite()` or `AttemptStateTransition()`. CI lint blocks direct `INSERT/UPDATE/DELETE` SQL on meta tables outside `contracts/meta/`.

**Hard rule (S04 §12T.6):** sensitive reads (enumerated in `meta-sensitive-read-paths.yml`) go through the library's audit-instrumented read path. Bypass = CI lint fail.

---

## §2. Sub-components (artifacts)

| ID | File | Purpose | Owning chunk | Size |
|---|---|---|---|---|
| L1.B.1 | `routing.go` | Primary-vs-replica query router | C03 §12O.4 | M |
| L1.B.2 | `cache.go` | Redis cache layer (30s TTL `meta:reality:{id}`) | C03 §12O.6 | M |
| L1.B.3 | `fallback.go` | Degraded-mode logic (bounded buffer + 503) | C03 §12O.8 | M |
| L1.B.4 | `pool.go` | Connection pool per primary/replicas | C03 §12O.13 (config) | S |
| L1.B.5 | `health.go` | Health + readiness probes | C03 §12O.12 | S |
| L1.B.6 | `metawrite.go` | `MetaWrite()` canonical helper | S04 §12T.2 | L |
| L1.B.7 | `lifecycle.go` | `AttemptStateTransition()` (specialization of MetaWrite) | C05 §12Q.3 | M |
| L1.B.8 | `transitions.yaml` | Per-resource transition graph (reality, incident, deploy, …) | C05 §12Q.6 + SR02/SR05 transitions | M |
| L1.B.9 | `transitions_validator.go` | Validates transitions.yaml graphs at startup | C05 §12Q.6 + SR02 lifecycle | S |
| L1.B.10 | `actor.go` | `Actor` type + SVID integration | S11 §12AA + S04 actor_type enum | S |
| L1.B.11 | `audit_writer.go` | Wraps every MetaWrite to also write `meta_write_audit` row in same TX | S04 §12T.5 | S |
| L1.B.12 | `read_audit.go` | Wraps enumerated sensitive-read paths with `meta_read_audit` | S04 §12T.6 | M |
| L1.B.13 | `entity_status.go` | `GetEntityStatus()` resolution path (pii_kek → reality_registry → reality_ancestry → projections) | S10 §12Z | M |
| L1.B.14 | `consent.go` | `ConsentSnapshot` cache (5min TTL) — checks `user_consent_ledger` | S08 §12X.9 | S |
| L1.B.15 | `pii_scrubber.go` | Free-text PII scrubber lib (`contracts/pii/scrubber.go` — but used by audit_writer for `reason` fields) | S08 §12X.5 | M |
| L1.B.16 | `metrics.go` | Library-emitted metrics (`lw_meta_*` per C03 §12O.12) | C03 §12O.12 | S |
| L1.B.17 | `errors.go` | Canonical error types (`ErrConcurrentStateTransition`, `ErrInvalidTransition`, `ErrMutualExclusion`, `ErrDegradedMode`, …) | C05 + C03 + S04 | S |

**Total: 17 Go files** at ~50-300 LOC each (mostly S/M).

---

## §3. `MetaWrite()` API surface (L1.B.6 deep)

```go
package meta

type MetaWriteOp string
const (
    OpInsert MetaWriteOp = "INSERT"
    OpUpdate MetaWriteOp = "UPDATE"
    OpDelete MetaWriteOp = "DELETE"
)

type ActorType string
const (
    ActorAdmin           ActorType = "admin"
    ActorSystem          ActorType = "system"
    ActorService         ActorType = "service"
    ActorRetentionCron   ActorType = "retention_cron"
)

type MetaWriteIntent struct {
    Table            string
    Operation        MetaWriteOp
    PK               map[string]any
    ExpectedBefore   map[string]any   // for CAS UPDATE only
    NewValues        map[string]any
    Actor            Actor             // type, id, svid
    Reason           string            // required for destructive ops
    RequestContext   RequestContext    // trace_id, request_id, source service
}

type MetaWriteResult struct {
    AuditID       uuid.UUID
    RowsAffected  int
    NewValues     map[string]any  // post-write state echo
}

func MetaWrite(ctx context.Context, w MetaWriteIntent) (*MetaWriteResult, error)
```

**Behavior:**
1. Validate `MetaWriteIntent` (table is in allowlist, op valid, PK present)
2. Begin TX
3. If CAS UPDATE: `UPDATE ... WHERE pk = :pk AND <expected_before>` — 0 rows = `ErrConcurrentStateTransition`
4. Execute the write
5. Write `meta_write_audit` row in same TX (via `audit_writer.go`)
6. Commit
7. Emit outbox event if table is in event-emit allowlist (per `events_allowlist.yaml`)

**CI lint enforcement (L1.K):** `scripts/meta-write-discipline-lint.sh` greps for `db.Exec("INSERT INTO loreweave_meta..."`, `db.Exec("UPDATE loreweave_meta..."`, etc. outside `contracts/meta/`. Fail → block merge.

---

## §4. `AttemptStateTransition()` API surface (L1.B.7 deep)

```go
package meta

type TransitionRequest struct {
    ResourceType  string   // "reality" | "incident" | "deploy" | …
    ResourceID    string
    FromState     string
    ToState       string
    Reason        string
    Actor         Actor
    Payload       map[string]any  // additional fields to update (e.g., close_initiated_by)
}

type TransitionResult struct {
    AuditID       uuid.UUID
    NewState      string
    TransitionAt  time.Time
}

func AttemptStateTransition(ctx context.Context, req TransitionRequest) (*TransitionResult, error)
```

**Behavior:**
1. Look up resource's transition graph from `transitions.yaml` (loaded at startup, validated)
2. Reject if `(FromState, ToState)` not in graph → `ErrInvalidTransition`
3. Reject if resource is in mutually-exclusive lifecycle op → `ErrMutualExclusion`
4. Delegate to `MetaWrite()` with `Operation=UPDATE, ExpectedBefore={status: FromState}` — gets CAS + audit for free
5. Write `lifecycle_transition_audit` row in same TX (via `audit_writer.go` extension)

**`transitions.yaml` schema sketch:**
```yaml
resources:
  reality:
    table: reality_registry
    state_column: status
    states:
      - active
      - pending_close
      - frozen
      - migrating
      - archived
      - archived_verified
      - soft_deleted
      - dropped
    transitions:
      - from: active
        to: [pending_close, migrating, rebasing]
      - from: pending_close
        to: [active, frozen]
      # ... per C05 §12Q.6 full graph
    mutual_exclusions:
      - if_status: migrating
        forbidden_transitions: [pending_close]
  incident:
    table: incidents
    state_column: status
    states: [declared, triaged, mitigated, resolved, postmortem, closed]
    transitions: # ... per SR02 §12AE
  deploy:
    table: deploy_audit
    state_column: status
    states: [staged, canary_1pct, canary_10pct, canary_50pct, completed, rolled_back]
    transitions: # ... per SR05 §12AH
```

**Validator (L1.B.9):**
- Run at service startup: parse YAML, check for cycles, check all states reachable from initial state, check no unreachable terminal states except explicit final states
- Fail-fast: panic on load if invalid (no degraded operation with broken state machine)

---

## §5. Read paths (L1.B.1, L1.B.2, L1.B.12)

**Three read modes:**

| Mode | API | Cache? | Audit? | Hot path? |
|---|---|---|---|---|
| `GetRealityRouting(realityID)` | `routing.go` | Yes (Redis 30s) | No | YES (every command) |
| `GetEntityStatus(entityType, entityID)` | `entity_status.go` | Yes (Redis 60s) | No | YES (every prompt) |
| `ReadSensitive(query_type, params)` | `read_audit.go` | No | YES (`meta_read_audit`) | NO (admin/forensics) |

**Sensitive read enumeration** (from `meta-sensitive-read-paths.yml`):
- `player_index_cross_user` — `SELECT … FROM player_character_index WHERE user_ref_id != $caller_user`
- `audit_query` — any `SELECT FROM *_audit`
- `admin_bulk_export` — explicit admin-cli command
- `bulk_meta_query` — any query with `LIMIT > 1000` or missing `WHERE` on meta table

**Bypass detection** (L1.K lint): grep for sensitive-table reads outside `read_audit.go` instrumentation.

---

## §6. Cache invalidation (L1.B.2 deep)

**Cache keys + invalidation triggers:**

| Cache key | TTL | Invalidated by |
|---|---|---|
| `meta:reality:{reality_id}` | 30s | `xreality.reality.stats` event (R5 infrastructure) |
| `meta:user_consent:{user_ref_id}` | 5min | `user.consent.granted`, `user.consent.revoked` events |
| `meta:entity_status:{type}:{id}` | 60s | `*.status.*` events |
| `meta:feature_flags` | 60s | `feature_flag.toggled` event |

**Bypass flag:** `?fresh=true` query param → skip cache, hit replica/primary directly.

**Startup warmup:** load top-N active realities into cache on service boot (configurable: e.g., top 1000 by `last_active_at`). C03 §12O.6.

---

## §7. Degraded mode (L1.B.3 deep)

When meta primary + all sync replicas unavailable (catastrophic):

```go
type DegradedModeBuffer struct {
    AuditQueue    *boundedQueue  // 10K entries max
    HeartbeatQueue *boundedQueue // 10K entries
    DropPolicy    DropPolicy     // "oldest" | "newest" | "alert_at_threshold"
}

func (b *DegradedModeBuffer) Enqueue(item BufferedItem) error
func (b *DegradedModeBuffer) Flush(ctx context.Context) error  // on recovery
```

**Behavior per service:**
- `publisher`, `meta-worker`, `event-handler`: buffer heartbeats locally
- `admin-cli`: buffer audit rows; reject Tier 1 destructive commands (need fresh ack)
- All services: surface `X-LW-Mode: degraded` header on outbound responses

**Recovery flush:** on connectivity restore, drain buffer in order; on partial flush failure, retry per `meta.degraded_mode.retry_backoff_schedule = "100ms,500ms,2s,5s,10s"`.

**Buffer overflow:** alert + service-level rate-limit on the action class that's filling it.

---

## §8. Dependencies (what foundation must ship alongside L1.B)

| Dependency | Status | Notes |
|---|---|---|
| `contracts/pii/scrubber.go` | Must ship in same cycle | `audit_writer.go` calls it for `reason` field scrubbing |
| `contracts/resilience/{WithTimeout,Breaker,Retry,Bulkhead}` | Must ship before L1.B | All meta calls wrap through these per I16 |
| `contracts/lifecycle/Drain` | Must ship before L1.B | Used by `fallback.go` on service shutdown |
| KMS adapter | Must ship before L1.B (for `pii_kek`) | NOT in L1.B itself, but L1.B reads pii_kek for `GetEntityStatus()` |
| `events_allowlist.yaml` | Must ship in same cycle | Defines which `MetaWrite()` ops emit outbox events |
| Patroni + etcd infrastructure | Out of scope of library; L1.E ships infra | L1.B `pool.go` assumes Patroni-managed VIP |

---

## §9. Test requirements (acceptance criteria for L1.B cycle)

| Test | Tool | Pass criteria |
|---|---|---|
| Unit tests | `go test ./contracts/meta/...` | 90%+ coverage; all transition graphs validated |
| Integration tests | `docker-compose up postgres redis` + `go test -tags=integration` | MetaWrite → meta_write_audit row present; CAS UPDATE returns 0 rows on stale expected_before; AttemptStateTransition rejects invalid transitions |
| Race detector | `go test -race ./contracts/meta/...` | Zero races on concurrent MetaWrite + cache invalidation |
| Failover test | `pkill postgres` during write loop | Service surfaces `X-LW-Mode: degraded`; buffer fills; flush succeeds on recovery |
| Cache invalidation test | Emit `xreality.reality.stats` event | All instances' caches invalidate within 2s |
| Lint enforcement | `scripts/meta-write-discipline-lint.sh` | Fails on injected violation in test fixture |
| Transition graph validation | `transitions_validator.go` at boot | Fails fast on malformed `transitions.yaml` |
| Replay-determinism | replay events against `lifecycle_transition_audit` | Sequence of transitions reconstructible from audit |

---

## §10. Open questions surfaced during L1.B enumeration

| # | Question | Suggested resolution | Status |
|---|---|---|---|
| Q-L1B-1 | `events_allowlist.yaml` — which `MetaWrite()` ops emit outbox events? Authoritative list? | Auto-derive from service map's "Emits events" column + cross-check with `outbox_event_emit_lint` | Need user lock |
| Q-L1B-2 | `meta-sensitive-read-paths.yml` ownership — security team or platform? | Platform (foundation) owns initial set; security team has CODEOWNERS approval on changes | Suggested default |
| Q-L1B-3 | Should `MetaWrite()` support multi-table TX (e.g., insert reality_registry + reality_close_audit in one TX)? | YES — common pattern; helper `MetaWriteBatch(ctx, []MetaWriteIntent) error` | Need user lock |
| Q-L1B-4 | Library exports for non-Go services (Python knowledge/chat, Rust kernel) — proxy via RPC or per-language port? | Per-language port for hot-path callers; RPC via meta-worker for cold-path | Need user lock |
| Q-L1B-5 | Library testing infra (Patroni docker-compose?) — V1 dev infra or external dep? | Foundation builds `docker-compose.meta-ha.yml` with Patroni + etcd + 1 sync + 1 async (V1 layout) | Suggested default |

---

## §11. Status

```
[x] L1.B — 17 sub-component artifacts enumerated
[x] L1.B — MetaWrite API surface specified
[x] L1.B — AttemptStateTransition + transitions.yaml specified
[x] L1.B — Read paths (3 modes) specified
[x] L1.B — Cache invalidation specified
[x] L1.B — Degraded mode specified
[x] L1.B — Dependencies + test requirements + open questions
[ ] L1.B — 5 open questions resolved
[ ] Continue to L1.C (Per-reality DB Provisioner)
```
