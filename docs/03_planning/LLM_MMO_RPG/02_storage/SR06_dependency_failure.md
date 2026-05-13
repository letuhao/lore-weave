<!-- CHUNK-META
chunk: SR06_dependency_failure.md
origin: direct-authored 2026-04-24
origin_branch: mmo-rpg/design-resume
note: Not produced by scripts/chunk_doc.py split; authored as new SR-series content extending SR1-SR5.
-->

## 12AI. Dependency Failure Handling — SR6 Resolution (2026-04-24)

**Origin:** SRE Review SR6 — the platform has ~15 external dependencies (LLM providers, meta DB, per-reality DBs, Redis Streams, MinIO, Vault, auth IdP, monitoring surfaces). SR1-SR5 covered targets, incidents, runbooks, postmortems, deploy — but "a dependency just failed, what happens?" was undesigned. Without discipline, any one outage cascades: an LLM timeout holds a DB connection which exhausts the pool which backs up the outbox which stalls propagation which breaks WS delivery. The goal of SR6 is **bounded blast radius per dependency failure** + **graceful degradation** + **audit trail for postmortem**.

### 12AI.1 Problems closed

1. Unbounded outbound calls (no timeouts / no deadlines)
2. No visibility into dependency health
3. Retry storms / thundering herd on recovery
4. Cascading failure (one dep drains others)
5. All-or-nothing availability — no degraded mode
6. LLM provider single-point-of-failure per call
7. No audit trail of dep failures (postmortem impossible)
8. Non-idempotent retries causing double-writes
9. Deploy / restart drops in-flight requests
10. Ad-hoc circuit breaker implementations per service
11. Timeouts too long → user sees frozen UI
12. No chaos drill framework (→ SR7)

### 12AI.2 Layer 1 — Dependency Registry + Criticality Tiers

Single source of truth at `contracts/dependencies/matrix.yaml`:

```yaml
- name: llm-anthropic
  owner_service: roleplay-service         # primary caller
  also_used_by: [chat-service, world-service]
  criticality: P1                          # platform-paid RP + chat depend on it
  type: http_external
  sla_target: 99.5%                        # upstream
  timeout_ms: 60000                        # matches SR1-D2 tier default
  circuit_breaker:
    error_rate_threshold: 0.25             # 25% errors over min_requests window
    min_requests: 20
    open_duration_ms: 30000                # 30s before half-open probe
  fallback: [llm-openai, llm-byok-user]
  degraded_modes: [limited, offline]
  runbook: docs/sre/runbooks/llm-provider/llm-anthropic-down.md
```

**Criticality tiers:**

| Tier | Definition | Example deps | Failure impact |
|---|---|---|---|
| **P0** | Platform-critical — failure = full outage; no meaningful degraded mode | meta DB · auth-service · api-gateway-bff egress · Vault | All user-facing traffic halts |
| **P1** | Feature-critical — failure degrades a major feature; other features continue | LLM providers (primary) · Redis Streams · per-reality DB (partial) · provider-registry | One feature flow (RP, chat) offline or degraded |
| **P2** | Background — failure doesn't block active play | MinIO · translation-service · video-gen · knowledge-service Neo4j derived layer · monitoring egress | Background features delayed; retry later |

**Governance:** every new external dependency MUST be added to the matrix + have a runbook (SR3) + PR-reviewed tier classification. CI lint (`scripts/dependency-registry-lint.sh`) blocks new `http.Client` / `sql.Open` / `redis.NewClient` calls outside registered names. Tier classification changes require architect sign-off (same workflow as new invariant per `00_foundation/02_invariants.md`).

### 12AI.3 Layer 2 — Timeout Discipline (invariant I16)

**Rule:** every outbound call declares a timeout. No `context.Background()` for network calls. Sum of timeouts along a request chain must fit the user-visible SLO.

Default timeouts by dependency class:

| Class | Default timeout | Source |
|---|---|---|
| LLM provider — paid-tier intent (session_turn, npc_reply) | 60s | SR1-D2 `sli_turn_completion` paid |
| LLM provider — premium-tier intent | 120s | SR1-D2 premium |
| LLM provider — short intent (canon_check, summary) | 15s | S9-D6 token budget |
| Postgres — per-reality read | 5s | |
| Postgres — per-reality write | 10s | |
| Meta DB (any) | 3s | stricter; shared resource |
| Redis (any) | 500ms | cache; budget-critical |
| MinIO — small object (≤1MB) | 10s | |
| MinIO — large object | 60s | |
| Inter-service RPC default | 5s | S11 alignment |
| Vault secret fetch | 2s | cached; rare |
| Auth external IdP | 5s | |

**Enforcement:** `contracts/resilience/WithTimeout(ctx, dep, fn)` is the canonical wrapper — reads the timeout from the matrix. CI lint (`scripts/timeout-discipline-lint.sh`) flags:
- `http.NewRequest` / `http.Client.Do` without `ctx` carrying a deadline derived from matrix
- `sql.Query` / `redis.Cmd` without context cancel
- `context.Background()` in any code path that eventually makes a network call (allowed only in `func init()` + top-level shutdown)

A 60s LLM timeout downstream of a 5s RPC timeout is a bug — CI lint's call-graph pass detects inverted budgets when instrumentation is available; until then, integration review catches it.

### 12AI.4 Layer 3 — Circuit Breaker Library

Canonical library at `contracts/resilience/`:

```go
type CircuitBreaker interface {
    Call(ctx context.Context, fn func(context.Context) error) error
    State() BreakerState     // closed | half_open | open
    Metrics() BreakerMetrics
}

func NewBreaker(depName string, cfg BreakerConfig) CircuitBreaker
```

**3-state machine:**

| State | Behavior | Transition trigger |
|---|---|---|
| **closed** | Calls pass through; track success/failure windowed | → `open` when `error_rate ≥ threshold` over `min_requests` window |
| **open** | Calls fast-fail with `ErrCircuitOpen`; no upstream call made | → `half_open` after `open_duration_ms` elapsed |
| **half_open** | Limited probe calls (1 every `probe_interval_ms`) | → `closed` if probe succeeds · → `open` if probe fails |

**Audit of transitions:**
Every state change writes a `dependency_events` row (see §12AI.9), plus:
- Emits `dependency.<dep>.circuit_opened` / `...circuit_closed` events via outbox (I13)
- Increments `lw_dependency_circuit_transitions_total{dep, from, to}` metric
- PAGE SRE on per-dep `open` > 5min for P0/P1; log-only for P2

**Library requirement:** any outbound call on a P0 or P1 dependency MUST route through `contracts/resilience/`. CI lint flags raw `http.Do` / `db.Query` calls against P0/P1 deps bypassing the library.

**Breaker sharing (fault-domain rule):** one breaker per `(caller_service, dep)` pair. Two services calling the same dep maintain independent breakers. A wedged breaker in `roleplay-service` does not trip one in `chat-service`.

### 12AI.5 Layer 4 — Retry Policy + Backoff + Jitter

Default policy per call class:

| Class | Max retries | Backoff | Total budget |
|---|---|---|---|
| **Idempotent** (GET, read-only RPC, Redis read) | 3 | Exp `100ms × 2^n` ± 25% jitter | 10s |
| **Compensating-event pattern** (outbox write with idempotency key) | 3 | Same | 10s |
| **Non-idempotent** (POST without idempotency key, LLM call with side-effects) | 0 | — | — |
| **Critical write** (cost ledger, audit, canon entries) | 2 | Exp + cap at 5s | 15s |

**Enforcement:**
- `contracts/resilience/Retry(ctx, policy, fn)` wraps calls; policy looked up from matrix per-dep
- CI lint blocks ad-hoc `for i := 0; i < 3; i++ { ... }` retry loops outside the library

**Retry-After:** respect HTTP `Retry-After` header — if upstream returns a retry delay, use it instead of default backoff (still capped at policy budget).

**Thundering herd prevention:**
- Mandatory ±25% jitter on all retries
- `half_open` probe rate-limited to 1 caller per probe interval (prevents rush-in on recovery)
- Global rate-limit per dep per 1-minute window via shared Redis counter; excess callers get `ErrRateLimitedShared` (fast-fail, no queue)

### 12AI.6 Layer 5 — Degraded Mode Taxonomy

Per-service mode enum at `contracts/lifecycle/modes.go`:

```go
type ServiceMode string

const (
    ModeFull       ServiceMode = "full"        // all features available
    ModeLimited    ServiceMode = "limited"     // some features disabled per dep availability
    ModeEssentials ServiceMode = "essentials"  // core read-paths only; no writes to degraded deps
    ModeReadOnly   ServiceMode = "read_only"   // no state changes; serving from cache / last-known
    ModeOffline    ServiceMode = "offline"     // reject new work; preserve in-flight
)
```

**Per-dep → mode mapping** (declared in matrix `degraded_modes`):

| Dep down | Mode activation | User-visible |
|---|---|---|
| LLM primary only | `limited` — fallback to secondary LLM (§12AI.7) | Slower / different style; banner "using fallback model" |
| All LLMs down (per user) | `limited` for RP/chat — reject new turns; preserve session state | "AI unavailable; please try again in a moment" |
| Redis Streams down | `limited` — outbox buffers in DB; WS updates delayed | "Live updates delayed" toast |
| MinIO down | `limited` — async uploads queued in outbox; sync reads fail-fast | Files show "will complete when storage returns" |
| Per-reality DB down | `read_only` for that reality only; writes rejected | Reality-scoped banner; other realities unaffected |
| Meta DB down | `essentials` platform-wide; writes halted; reality-local reads continue | Major banner; admin commands blocked |
| Auth external IdP | `limited` — existing sessions continue; new logins queued with retry | Login retry UX; existing play unaffected |

**Mode activation:**
- **Automatic:** circuit breaker opens on a tier-mapped dep → mode transitions to configured target
- **Manual:** `admin/degraded-mode-force <mode>` (S5 Tier 1 Destructive — user-visible; dual-actor + 100+ char reason + 24h cooldown)
- **Clearing:** all implicated circuit breakers closed for ≥2 min → auto-restore to `full` (anti-flap single-sample protection)

**Mode propagation:** broadcast via Redis control channel `lw:dependency:control` (same mechanism as S12's `lw:ws:control`; signed with SVID per §12AA.L7). `api-gateway-bff` surfaces mode in response headers (`X-LW-Mode`) + WS control messages.

### 12AI.7 Layer 6 — Multi-Provider LLM Failover

Extends `provider_registry` schema (integrated with S9 provider metadata):

```sql
ALTER TABLE provider_registry
  ADD COLUMN failover_priority INT NOT NULL DEFAULT 100,  -- lower = higher priority
  ADD COLUMN failover_scope    TEXT NOT NULL,              -- 'per_user' | 'platform'
  ADD COLUMN is_platform_paid  BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX ON provider_registry (failover_priority) WHERE failover_scope = 'platform';
```

**Failover chain per LLM call:**

1. Resolve priority list per user: platform-paid primary → BYOK entries (if consented per S8 `byok_telemetry` scope) → platform-paid emergency fallback
2. Try priority 1 with its own timeout; on `ErrCircuitOpen` OR timeout → priority 2
3. Each try adheres to its OWN timeout (not additive — if chain budget 120s, try 1 at 60s + try 2 at 50s + try 3 at 10s; skip remaining if budget exhausted)
4. Emit `llm.failover.used{from, to, reason}` event per fallback; counted against S6 user budget at the destination provider's cost

**Cost impact (S6 interaction):**
- Platform-paid fallback calls still count against per-user budget at destination-provider cost
- User budget exhausted during failover → reject with `ErrBudgetExceeded` rather than exceed budget
- S6-D2 per-session cap still enforced across failover chain
- Admin `admin/failover-budget-override` (S5 Tier 2 Griefing) for emergency (capped multiplier; reason + user notify per S5-L2)

**User-visible:** on failover, append `[fallback:gpt-4o-mini]` breadcrumb to session metadata under `[SESSION_STATE]` section only (S9 prompt governance — NOT in user-content regions; NOT in `[INPUT]`).

### 12AI.8 Layer 7 — Dependency Health Observability

Metrics (canonical labels per SR1-D8 cardinality rules):

| Metric | Labels | Purpose |
|---|---|---|
| `lw_dependency_health{dep, state}` | dep ∈ matrix names; state ∈ {healthy, degraded, down} | gauge; dashboard tiles |
| `lw_dependency_circuit_state{dep, service}` | | gauge; 0=closed / 1=half_open / 2=open |
| `lw_dependency_errors_total{dep, service, error_class}` | error_class ∈ {timeout, upstream_5xx, upstream_4xx, circuit_open, retry_exhausted, bulkhead_full} | counter |
| `lw_dependency_latency_seconds{dep, service}` | | histogram; P50/P95/P99 tracked |
| `lw_degraded_mode_active{service, mode}` | | gauge; 1 if active |
| `lw_dependency_events_total{dep, event_type}` | | counter; mirrors `dependency_events` table |

**Alerts:**

| Condition | Severity | Channel |
|---|---|---|
| P0 dep circuit `open` > 1 min | SEV0 (PAGE) | on-call primary + security if auth-related |
| P1 dep circuit `open` > 5 min | SEV1 (PAGE) | on-call primary |
| P2 dep circuit `open` > 30 min | SEV2 (warn) | SRE Slack |
| Dep retry-exhaustion rate > 5/min | SEV2 | SRE Slack |
| Degraded mode active > 10 min (any tier) | SEV1 (PAGE) | on-call primary |
| Timeout-without-retry rate > 1/sec for P0/P1 dep | SEV2 | investigation trigger |

**Dashboard** (DF11 dependency panel V1):
- All deps with criticality tier + current state + last event time
- Breaker state heatmap (service × dep matrix; color by state)
- Degraded-mode activity timeline (last 24h)
- Per-dep latency P50/P95/P99 trend
- Top-5 errors by `(dep, error_class)` pair

### 12AI.9 Layer 8 — Dependency Events Audit

```sql
CREATE TABLE dependency_events (
  event_id              UUID PRIMARY KEY,
  dep_name              TEXT NOT NULL,                       -- from matrix
  service               TEXT NOT NULL,                       -- which caller
  event_type            TEXT NOT NULL,                       -- 'circuit_open' | 'circuit_half_open' | 'circuit_closed'
                                                             -- | 'timeout_burst' | 'retry_exhausted' | 'degraded_mode_activated'
                                                             -- | 'degraded_mode_cleared' | 'failover_used' | 'manual_override'
                                                             -- | 'bulkhead_full_burst'
  reason                TEXT,                                -- 'error_rate=0.42 over 100req' / 'auto from circuit_open' / etc.
  metrics_snapshot      JSONB,                               -- {error_rate, p99_ms, req_rate, circuit_state, ...}
  occurred_at           TIMESTAMPTZ NOT NULL,
  cleared_at            TIMESTAMPTZ,                         -- for mode activations / circuit transitions
  related_incident_id   UUID,                                -- SR2-D7 link
  actor                 UUID                                 -- user_ref_id if manual override; NULL if automatic
);

CREATE INDEX ON dependency_events (dep_name, occurred_at DESC);
CREATE INDEX ON dependency_events (event_type, occurred_at DESC) WHERE cleared_at IS NULL;
CREATE INDEX ON dependency_events (service, dep_name, occurred_at DESC);
```

**Retention:** **1 year** (high-volume metric-derived events; shorter than 5y audit tier but long enough for trend + postmortem).
**PII classification:** `none` (metrics + dep names only; no user content).
**Write path:** via `MetaWrite()` (I8); append-only; REVOKE UPDATE/DELETE on `audit_retention_role` only.

**Use cases:**
- **Postmortem correlation (SR4):** "circuit opened at T-3min, mode activated at T-2min, incident declared at T" — populate timeline
- **Reliability review (SR1-D5):** weekly "top deps by time-in-degraded" chart
- **Runbook evidence (SR3):** recent failures referenced from runbook
- **Chaos drill validation (SR7):** compare injected-failure to recorded events — drill success criterion

### 12AI.10 Layer 9 — Bulkhead Isolation

**Principle:** one slow dep does not exhaust resources shared with other deps.

**Per-service bulkheads** (declared at service bootstrap from matrix):

```go
// contracts/resilience/bulkhead.go
type Bulkhead struct {
    DepName       string
    MaxConcurrent int            // per-service concurrent calls to this dep
    QueueDepth    int            // pending calls allowed before rejection
    QueueTimeout  time.Duration  // how long to wait before rejection
}
```

**Defaults by tier:**

| Tier | MaxConcurrent | QueueDepth | QueueTimeout |
|---|---|---|---|
| P0 | 50 | 20 | 100ms |
| P1 | 30 | 15 | 200ms |
| P2 | 10 | 5 | 500ms |

On queue-full: `ErrBulkheadFull` returned; counted in `lw_dependency_errors_total{error_class="bulkhead_full"}`.

**Resource isolation specifics:**
- **DB pools:** separate pgx pool per `(service, dep)` pair; per-reality DBs share a pool per shard-host
- **HTTP clients:** separate `http.Client` per dep; separate dialer; custom transport per dep (no cross-contamination)
- **Goroutine pools (Go services):** `errgroup` with bounded `SetLimit` per dep
- **Redis connections:** separate pool for `publisher` outbox drain vs `api-gateway-bff` rate-limit vs `session-router` control channel

CI lint (`scripts/bulkhead-lint.sh`) flags:
- Creation of unbounded goroutines calling registered dep names
- Shared HTTP clients across dep names
- `go func() { ... }` without `errgroup` or semaphore for registered deps

### 12AI.11 Layer 10 — Graceful Shutdown + Drain

Canonical shutdown hook at `contracts/lifecycle/Drain`:

```go
func Drain(ctx context.Context, timeout time.Duration, hooks DrainHooks) error

type DrainHooks struct {
    StopAccepting  func()               // flip /health/ready to 503; LB drops service
    WaitInFlight   func(ctx) error      // wait for active handlers; honors ctx deadline
    FlushOutbox    func(ctx) error      // attempt final publisher drain to Redis
    CloseBreakers  func() error         // open all breakers (fail-fast remaining outbound)
    CloseResources func() error         // DB pools, Redis, HTTP, bulkheads
}
```

**SIGTERM handler flow (in order):**

1. **Stop accepting** — `/health/ready` returns 503; LB stops routing new requests; WS new connections rejected (close code 4011 "draining")
2. **Wait in-flight** — up to `timeout` for active handlers to complete; ctx carries deadline
3. **Flush outbox** — publisher attempts final drain; remaining rows persist (next replica picks up via claim-lock)
4. **Open breakers** — outbound calls fast-fail with `ErrCircuitOpen`; handlers that can't complete return cleanly with error
5. **Close resources** — orderly DB pool close; Redis disconnect; HTTP idle-close

**Per-service tuning:**
- V1 default: 30s drain timeout
- Long-running handlers (`migration-orchestrator`, `publisher`): 120s (explicit per-service override)
- Stateless (`api-gateway-bff`): 10s sufficient

**WebSocket drain:** existing connections receive close code **4011 (draining)** with `Retry-After: 5` hint; client reconnects to a different replica.

**Emergency shutdown (SIGKILL):** bypasses drain; rely on outbox + event-sourced recovery. SEV0 postmortem trigger per SR4 if correlated with user impact.

**Integration with SR5 deploy:** canary rollout (SR5-L3) respects drain — no new cohort advance until old replicas fully drained + their `/health/ready` returns 503 for the full window.

### 12AI.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| I1 (gateway) | api-gateway-bff surfaces degraded-mode banners + WS close codes |
| I2 (provider-gateway) | Multi-LLM failover (L6) routes through the gateway; no direct SDK |
| I8 (MetaWrite) | `dependency_events` rows written via MetaWrite (append-only audit) |
| I11 (SVID auth) | Internal-RPC deps (e.g., auth-service) still require SVID; breaker wraps authenticated calls |
| I13 (outbox) | Redis-down degraded mode: outbox buffers in DB; publisher resumes on Redis recovery |
| I16 (timeout discipline, NEW this resolution) | SR6-D2 is the canonical source of timeouts (matrix.yaml) |
| SR1-D2 | SLO thresholds inform dep timeouts (60s/120s tier-matched) |
| SR1-D3 | Error-budget burn can auto-activate degraded mode (V1+30d — L5 integration) |
| SR2-D7 | `incidents.related_audit_refs` includes dependency_events |
| SR3 | Per-dep runbook mandatory; matrix `runbook:` field points at it |
| SR4-D7 | Root cause `external_dependency` category includes dep_event_id link |
| SR5-D2 | Deploy freeze extends to "active SEV0 dep outage" (security-triggered pattern) |
| SR7 (future) | Chaos drill harness injects dep failures; validates SR6 mechanisms |
| S6 (LLM cost) | Failover budget interaction; fallback calls count against per-user budget at destination cost |
| S9 (prompt) | Degraded-mode fallback breadcrumb lives in `[SESSION_STATE]` section only |
| S11-D5 | `admin/degraded-mode-force` = Tier 1 Destructive (user-visible + irreversible in-flight impact) |
| S12 (WS) | New close codes: 4011 "draining" · 4012 "dependency_degraded" added to enumerated set |
| ADMIN_ACTION_POLICY §R4 | 3 new commands: `admin/degraded-mode-force` Tier 1 · `admin/circuit-breaker-reset` Tier 2 · `admin/failover-budget-override` Tier 2 |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| Centralized `matrix.yaml` is one more registry | Prevents drift; single audit point for dep inventory |
| Circuit breakers add latency | ~1ms overhead per call; prevents retry storms worth 1000× under failure |
| Bulkheads require per-dep resource allocation | Prevents noisy-neighbor; capacity planning done once in matrix |
| Timeouts force call-chain budgeting | Required for meaningful SLO; bug fixing easier with explicit budgets |
| Multi-LLM failover complicates cost modeling | S6 integration handles it; cost visibility preserved |
| 30s drain slows deploys | Per-pod; replicas drain in parallel; canary stages don't add serially |
| `dependency_events` adds 1y retention table | High-volume but bounded; needed for postmortem correlation |
| Per-dep HTTP client duplicates TLS sessions | Small memory cost; fault-domain isolation worth it |

**What this resolves:**

- ✅ Unbounded calls — L2 timeout discipline (invariant I16)
- ✅ Health visibility — L7 metrics + dashboard + alerts
- ✅ Retry storms — L4 exp backoff + jitter + half-open probe rate-limit
- ✅ Cascading failure — L9 bulkheads with per-dep resource isolation
- ✅ All-or-nothing availability — L5 degraded mode taxonomy (5 modes)
- ✅ LLM single-point-of-failure — L6 multi-provider failover chain
- ✅ No audit trail — L8 `dependency_events` table
- ✅ Double-write risk — L4 retry policy differentiates idempotent vs non-idempotent
- ✅ In-flight loss on deploy — L11 graceful drain standardized
- ✅ Ad-hoc breakers — L3 canonical library in `contracts/resilience/`
- ✅ Frozen UI — L2 tiered timeouts matched to SLO
- 🔄 Chaos drill framework — deferred to SR7 (integration hooks ready in L8)

**V1 / V1+30d / V2+ split:**

- **V1:**
  - L1 matrix + CI lint enforcement
  - L2 timeouts + discipline lint (new invariant I16)
  - L3 circuit breaker library (count-based error rate, 3-state)
  - L4 retry policy + backoff + jitter
  - L5 degraded modes (5-mode taxonomy) + automatic on-circuit-open activation
  - L6 LLM failover (basic: priority-ordered; per-user chain)
  - L7 metrics + dashboard panels + core alerts
  - L8 `dependency_events` table + MetaWrite integration
  - L9 bulkheads (per-dep conn pools + HTTP clients; errgroup bounds)
  - L10 graceful drain (30s default, per-service override)
- **V1+30d:**
  - L3 adaptive circuit breakers (latency-based signals in addition to error-rate)
  - L5 auto-degraded-mode activation based on SLO burn (SR1-D3 integration)
  - L7 alert tuning from V1 observation data
  - L10 chaos drill hooks ready for SR7 consumption
- **V2+:**
  - ML anomaly detection on dep latency
  - Blue-green provider swap (beyond priority failover)
  - Per-region geo-failover (V3+)
  - Backpressure mechanism for producers (queue-length-aware admission)
  - Upstream-SLA tracking (trigger vendor escalation)
  - Cross-dep correlation model (dep A affects dep B causal graph → SR12)

**Residuals (deferred):**
- Multi-region geo-failover → V3+
- Vendor SLA cost negotiation → business-level, not engineering
- Automatic incident declaration from dep events → SR7 chaos + SR2 escalation
- Cross-dep correlation → SR12 observability cost (related concern)
- Emergency shutdown (SIGKILL) audit beyond event replay → covered by event sourcing; no additional mechanism

**Decisions locked (10):**
- **SR6-D1** Dependency registry + 3-tier criticality classification (P0/P1/P2)
- **SR6-D2** Timeout discipline (invariant I16) with tiered defaults per dep class
- **SR6-D3** Canonical circuit-breaker library at `contracts/resilience/`; 3-state machine; CI-enforced for P0/P1
- **SR6-D4** Retry policy differentiates idempotent (3 × exp-backoff + jitter) vs non-idempotent (0 unless compensating pattern)
- **SR6-D5** 5-mode degraded-mode taxonomy (full / limited / essentials / read_only / offline) with per-dep mapping
- **SR6-D6** Multi-provider LLM failover with per-user priority chain; cost impact propagated to S6
- **SR6-D7** Dependency observability standard (6 metrics + 6 alert conditions + DF11 panel)
- **SR6-D8** `dependency_events` audit table (1y retention, MetaWrite-enforced append-only)
- **SR6-D9** Bulkhead per-`(service, dep)` with tiered defaults; enforced at bootstrap
- **SR6-D10** `Drain()` canonical shutdown helper; 30s default; WS close code 4011

**Features added (11):**
- **IF-39** Dependency registry (`contracts/dependencies/matrix.yaml`)
- **IF-39a** Circuit breaker library (`contracts/resilience/`)
- **IF-39b** Dependency health dashboard (DF11 panel)
- **IF-39c** Graceful shutdown / drain handler (`contracts/lifecycle/Drain`)
- **IF-39d** Multi-provider LLM failover (extends `provider_registry`)
- **IF-39e** Degraded-mode framework (`contracts/lifecycle/modes.go`)
- **IF-39f** `dependency_events` audit table
- **IF-39g** Chaos drill hooks (SR7 placeholder — V1+30d activation)
- **IF-39h** Dependency runbook template (SR3 integration)
- **IF-39i** Bulkhead resource pool manager
- **IF-39j** Timeout discipline CI lint (`scripts/timeout-discipline-lint.sh`)

**New invariant I16** added to `00_foundation/02_invariants.md`: "every outbound call declares a timeout".

**Remaining SRE concerns (SR7–SR12) queued:** chaos drill cadence · capacity planning & auto-scaling · alert tuning & pager discipline · supply chain security · turn-based game reliability UX · observability cost & cardinality.
