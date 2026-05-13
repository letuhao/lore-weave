<!-- CHUNK-META
chunk: SR08_capacity_scaling.md
origin: direct-authored 2026-04-24
origin_branch: mmo-rpg/design-resume
note: Not produced by scripts/chunk_doc.py split; authored as new SR-series content extending SR1-SR7.
-->

## 12AK. Capacity Planning + Auto-Scaling — SR8 Resolution (2026-04-24)

**Origin:** SRE Review SR8 — SR1 set SLO targets, SR6 bounded dependency blast radius with bulkheads, SR7 made reliability mechanisms falsifiable through chaos drills. But **"how much of what, and when do we add more?"** is undesigned. Under-provisioning burns SR1 error budget. Over-provisioning burns S6 cost budget. DB-per-reality fleet (R4-L6) adds a unique scaling dimension: thousands of small DBs on shared shards rather than one huge DB. Without a declared capacity model, SR1 SLO targets are aspirations, not commitments.

### 12AK.1 Problems closed

1. Undeclared capacity targets per service
2. Ad-hoc scaling rules that drift from intent
3. Per-reality ceilings referenced in MV6 but not enforced
4. Fleet shard utilization (R4-L6 2K/10K numbers) without tracking
5. Scale-up storms under load (thundering herd on boot)
6. Scale-down that drops in-flight work (SR6-D10 not coupled)
7. No load-test gate — SLOs are untested promises
8. Budget changes ad-hoc; no cost-impact review
9. LLM concurrent-call capacity confused with compute capacity
10. Scaling signals inconsistent across services
11. No audit trail of scaling decisions
12. Multi-tenant reality noisy-neighbor at fleet level

### 12AK.2 Layer 1 — Service Class Taxonomy (4 classes)

Every service bootstraps with a declared class. Scaling signals + auto-scaler choice + capacity shape all derive from class.

| Class | Shape | Examples | Scaling signal primary | Scaling signal secondary |
|---|---|---|---|---|
| **web** | Stateless request/response; horizontal scale-out | `api-gateway-bff`, `auth-service`, `book-service`, `sharing-service`, `catalog-service` | CPU target 70% | RPS per replica |
| **worker** | Long-running event-driven; queue consumer | `publisher`, `meta-worker`, `event-handler`, `migration-orchestrator`, `translation-service`, `video-gen-service` | Queue depth | Processing lag (oldest unprocessed event age) |
| **data-plane** | Stateful or pool-bound; vertical scale + shard | `provider-registry-service`, `usage-billing-service`, `knowledge-service` | Memory 80% · DB conn pool utilization | Per-request p99 latency |
| **llm-gateway** | External-call-bound; concurrency-limited not compute-limited | `roleplay-service`, `chat-service` | Concurrent-LLM-call count against S6 per-user cap | Turn-completion p95 vs SR1-D2 SLO |

**Special cases:**
- `world-service`: mixed class — web (session-create REST) + worker (session processor per R7). Treated as **composite**: one deployment, two scaling signals. Scale-up triggers on either.
- `admin-cli`: not a service; runs as on-demand CLI. No scaling.

Class declared in `contracts/capacity/budgets.yaml` (L2). CI lint blocks new service without class.

### 12AK.3 Layer 2 — Capacity Budget Matrix (proposed invariant I17)

Single source of truth at `contracts/capacity/budgets.yaml`:

```yaml
- service: roleplay-service
  class: llm-gateway
  v1:
    replicas_min: 2
    replicas_max: 8
    cpu_per_replica: "1000m"
    memory_per_replica: "2Gi"
    db_pool_size: 30                      # aligns SR6-D9 P1 bulkhead default
    concurrent_llm_calls_per_replica: 50  # composite of S6 per-user tier × expected multi-user concurrency
    network_egress_mbps: 50
  v2:
    replicas_min: 4
    replicas_max: 32
    cpu_per_replica: "2000m"
    memory_per_replica: "4Gi"
    db_pool_size: 60
    concurrent_llm_calls_per_replica: 100
    network_egress_mbps: 100
  v3:
    replicas_min: 16
    replicas_max: 256
    cpu_per_replica: "2000m"
    memory_per_replica: "4Gi"
    db_pool_size: 60
    concurrent_llm_calls_per_replica: 100
    network_egress_mbps: 100
  scaling_policy_ref: policies/llm-gateway-default.yaml
  review_cadence: quarterly               # tied to SR2-D8 weekly/monthly/quarterly ops cadence
```

**Proposed invariant I17 — Capacity Budget Discipline:** every service declares its capacity budget in `contracts/capacity/budgets.yaml`. CI lint blocks deployment of a service not represented in the file. Scaling beyond `replicas_max` requires `admin/capacity-override` (S5 Tier 2, L10).

**Status of I17:** **PENDING architect sign-off via POST-REVIEW** — not self-authorized. If approved, I17 joins I16 in `00_foundation/02_invariants.md`. If rejected, SR8-D2 stays as a decision-class rule without invariant-status.

**V1 vs V2 vs V3 semantics:**
- V1 budget = current platform tier (solo RP + coop scene bootstrap)
- V2 = 2-4 players per reality at scale (DF5 session scaling lands)
- V3 = persistent multiverse at target scale
Budget numbers are **starting estimates** tuned from load-testing (L8) + V1 prototype data (closes the D1 cost OPEN).

### 12AK.4 Layer 3 — Scaling Signals per Class

| Class | Primary | Secondary | Scale-up threshold | Scale-down threshold | Cool-down |
|---|---|---|---|---|---|
| web | CPU | RPS/replica | CPU > 70% for 3 min OR RPS > 80% budget for 2 min | CPU < 30% for 10 min AND RPS < 40% budget | 5 min up, 15 min down |
| worker | queue-depth | lag-age | depth > 200 OR oldest-unprocessed > 2 min | depth < 50 AND oldest-unprocessed < 30s | 3 min up, 15 min down |
| data-plane | memory + pool | p99 latency | memory > 80% OR pool-util > 85% OR p99 > 2× SLO | memory < 50% AND pool-util < 40% | 10 min up, 30 min down (stateful, careful) |
| llm-gateway | concurrent-calls | turn-p95 | concurrent > 80% cap OR p95 > 1.5× SLO | concurrent < 30% AND p95 < 0.8× SLO | 5 min up, 10 min down |

**Composite signals** (e.g., `world-service`): scale up on **either** signal breaching; scale down only when **both** signals below down-threshold. Prevents premature scale-down when one dimension is quiet but another is building.

**Hysteresis:** scale-down thresholds always strictly lower than scale-up (no chattering). Cool-down windows prevent oscillation.

Signal library at `contracts/capacity/signals.go`; per-class signal bundle bootstraps from class declaration.

### 12AK.5 Layer 4 — Per-Reality Capacity Ceilings

Extends MV6 (player-cap = 100 per reality, configurable) with five per-reality ceilings enforced by `world-service`:

| Ceiling | V1 default | Enforcement point | Breach outcome |
|---|---|---|---|
| Active players | **100** (MV6) | `reality_registry.active_player_count` CAS on session-start | Reject new session with `ErrRealityFull`; user UX = queue position + ETA |
| Concurrent WS connections | 150 (1.5× player cap; allows observers) | api-gateway-bff ticket redemption | Reject ticket with `ErrRealityConnectionCap`; retry after 30s |
| Event rate | 1000 events/min per reality | `events_outbox` write rate-limit per `reality_id` | `ErrRealityEventRateExceeded`; backoff + retry at client |
| Session-processor saturation | 20 active session-processors per reality | R7 session-router | Queue new session-start; UX = typing-indicator + ETA |
| Active NPC count in scene | 50 | roleplay-service scene manager | Prune least-active NPC per S2 capability; user-visible "NPC left the scene" |

Ceilings extensible per-reality via `reality_registry.capacity_overrides` (jsonb); tier-upgrade grants higher ceilings (platform tier integration — `103_PLATFORM_MODE_PLAN.md` referenced).

**Ceiling vs MV6:** MV6 is the product-level cap (balance / social design). SR8 ceilings are the platform-level caps (capacity protection). Platform cap ≥ product cap always.

### 12AK.6 Layer 5 — Fleet Shard Utilization

Extends R4-L6 (many-DBs-per-server) with tracking + rebalance primitives:

```sql
CREATE TABLE shard_utilization (
  shard_host            TEXT PRIMARY KEY,            -- e.g., 'pg-shard-03.loreweave.internal'
  shard_tier            TEXT NOT NULL,               -- 'small' | 'medium' | 'large'
  max_realities         INT NOT NULL,                -- per R4-L6: 500/2000/10000 by tier
  current_realities     INT NOT NULL,
  active_realities      INT NOT NULL,                -- subset of current; status in (active, pending_close)
  avg_event_rate_1m     DOUBLE PRECISION,            -- events/min across active
  total_storage_bytes   BIGINT,
  cpu_util_pct          DOUBLE PRECISION,
  memory_util_pct       DOUBLE PRECISION,
  last_updated_at       TIMESTAMPTZ NOT NULL,
  status                TEXT NOT NULL                -- 'healthy' | 'approaching_cap' | 'draining' | 'offline'
);
CREATE INDEX ON shard_utilization (shard_tier, current_realities);
CREATE INDEX ON shard_utilization (status) WHERE status != 'healthy';
```

**Utilization thresholds:**

| Metric | Healthy | Approaching-cap | Drain-required |
|---|---|---|---|
| `current_realities / max_realities` | < 70% | 70-90% | > 90% |
| `cpu_util_pct` | < 60% | 60-80% | > 80% |
| `memory_util_pct` | < 70% | 70-85% | > 85% |

**New-reality placement** (`world-service` provisioner): pick lowest-utilization healthy shard matching `shard_tier` requirement (premium realities → large tier; free/paid → medium/small). Cap at 85% per-shard to leave headroom for existing-reality growth.

**Rebalance (`admin/drain-shard`)** = S5 Tier 1 Destructive:
- Blocks new-reality placement on target shard
- Migrates existing realities via `migration-orchestrator` (C2 DB subtree split reuses protocol)
- User-visible downtime per reality = `migrating` lifecycle state
- Takes hours to days depending on reality count; runbook in SR3

### 12AK.7 Layer 6 — Auto-Scaling Mechanisms

| Class | V1 mechanism | V1+30d | V2+ |
|---|---|---|---|
| web | Kubernetes HPA (CPU + RPS) | Predictive pre-scale before scheduled events | AI-driven demand forecast |
| worker | KEDA (queue-depth scaler) | Backlog-aware target replica count | Multi-queue unified scaler |
| data-plane | **Vertical** (manual, review-gated) | Read-replica auto-provisioning | Write-sharding evaluation |
| llm-gateway | HPA (custom metric: concurrent-calls) | BYOK-aware per-tenant scaling | Per-model cost-optimized routing |

**Policy templates** at `contracts/capacity/policies/`:
- `web-default.yaml` — CPU 70% target, min=2, max=8× min, scale-up cool-down 5min, scale-down 15min
- `worker-default.yaml` — queue-depth 200 threshold, min=1, max=6× min
- `data-plane-default.yaml` — **no HPA; vertical only**; alerts trigger human review (SR2)
- `llm-gateway-default.yaml` — concurrent-calls 80% cap, min=2, max=16× min, cool-down 5min

Services inherit by referencing `scaling_policy_ref` in their budget entry. Overrides allowed with `justification` field (e.g., `world-service` composite needs tuned thresholds).

**Pre-warming (V1+30d):** services with bursty demand get `min_warm_replicas` above `replicas_min` during predictable-load windows (e.g., peak-hour curve from V1 telemetry). Prevents cold-start on scale-up. Tunable per service; default off in V1.

### 12AK.8 Layer 7 — Capacity Observability

Metrics (canonical labels per SR1-D8):

| Metric | Labels | Purpose |
|---|---|---|
| `lw_capacity_budget_utilization{service, dimension}` | dimension ∈ {cpu, memory, db_pool, concurrent_llm, network} | gauge 0..1; 1.0 = at budget |
| `lw_capacity_budget_vs_actual{service, dimension}` | | ratio; >1 = over budget |
| `lw_scaling_replicas_current{service}` | | gauge |
| `lw_scaling_signal{service, signal}` | | gauge; value per class's primary/secondary signal |
| `lw_shard_utilization{shard_host, metric}` | metric ∈ {realities, cpu, memory, storage} | gauge 0..1 |
| `lw_reality_ceiling_hit_total{reality_id_bucket, ceiling}` | reality_id top-K per SR1-D8; ceiling ∈ {players, ws_conn, event_rate, session_proc, npc_count} | counter |
| `lw_scaling_events_total{service, direction, trigger}` | direction ∈ {up, down}; trigger ∈ {signal, manual, cooldown_end} | counter; mirrors `scaling_events` table |

**Alerts:**

| Condition | Severity | Action |
|---|---|---|
| Budget utilization > 85% for 5 min (dim=CPU/memory/db_pool) | WARN (Slack) | Capacity review on next weekly cadence |
| Budget utilization > 95% for 2 min | SEV2 (PAGE) | On-call investigates; may approve `admin/capacity-override` |
| Shard `approaching_cap` for > 1h | WARN | Provisioner biases away; plan rebalance |
| Shard `drain_required` | SEV1 (PAGE) | Immediate rebalance per SR3 runbook |
| Reality ceiling-hit rate > 10/min (same reality) | WARN | Product review: tune MV6 caps or add capacity? |
| Scale-up failed (replica launch error) | SEV2 | On-call; may need cluster capacity or quota bump |
| Scale-down dropped in-flight work (SR6-D10 Drain failed mid-scale-down) | SEV2 | Investigate drain timeout vs workload |

**Dashboard (DF11 capacity panel):**
- Per-service budget-vs-actual stack (green/yellow/red bands)
- Fleet shard map (heatmap: shard × utilization)
- Scaling timeline (last 24h scale-up/down events)
- Reality ceiling-hit summary (top 10 realities by ceiling-hit rate)
- LLM concurrent-call saturation per tier (free/paid/premium)

### 12AK.9 Layer 8 — Load Testing Gate

`loadtest-service` (G2-D4) runs against the capacity budget at 4 gate points:

| Gate | When | Target | Pass criteria |
|---|---|---|---|
| **Baseline** | V1 launch candidate | `replicas_min` at baseline RPS | SLOs met; no SLI breach |
| **Target** | V1 launch candidate | `replicas_min` at budgeted RPS per dimension | SLOs met; budget utilization 60-80% |
| **Breakpoint** | V1 launch candidate + quarterly | Scale up until SLO breaches | Identified breakpoint + auto-scaler kicks in before SLO breach |
| **Degradation** | V1 launch candidate + quarterly | Beyond breakpoint | System enters degraded mode (SR6-D5); no cascading failure (SR6-D4 retry discipline holds) |

Load tests use G2-D4 script mix (casual / combat / fact / jailbreak). New-service gate: must pass Baseline + Target before prod enabling.

**Integration with SR7:** load drills from SR7 category `load` are a subset of SR8 load testing — chaos drills inject load + dep failure simultaneously; SR8 load tests inject load in clean conditions.

**V1+30d automation:** `scripts/capacity-gate-check.sh` CI hook runs per-service Baseline + Target on every `replicas_max` or `cpu_per_replica` increase in `budgets.yaml`.

### 12AK.10 Layer 9 — Capacity Governance

**Budget-change review process:**
- Budget up-scale (`replicas_max` or per-replica resource up) = **minor** deploy class per SR5-D1
- Cost-impact estimate required in PR (integrates `user_cost_ledger` per S6-D6 for LLM dimensions)
- Tech lead approval for > 2× existing `replicas_max`
- Quarterly review cadence (SR2-D8 meta-review rhythm) for all services

**Review artifacts:**
- `docs/sre/capacity-reviews/<yyyy>-Q<N>_service-<name>.md` (per-service quarterly review)
- Pattern: utilization trends · approaching-cap incidents · cost vs S6 projection · recommendation (hold / scale / split)

**Cost attribution (S6 integration):**
- Per-tier capacity cost calculated as `(CPU + memory + network) × replicas × tier` + `concurrent_llm_calls × average cost`
- Tier breakdown (free / paid / premium) via reality-tier assignment (existing in `reality_registry`)
- D2 pricing formula uses this as the real cost denominator (closes D1 OPEN when V1 prototype data arrives)

**Emergency override:** `admin/capacity-override` (S5 Tier 2 Griefing — cost impact; reason + notification required) allows scale beyond `replicas_max` for bounded duration (max 24h; extension requires dual-actor). Auto-expire; post-expire report to on-call.

### 12AK.11 Layer 10 — Scale-Down Hygiene

Scaling down drops work if mishandled. SR6-D10 `Drain()` is the coupling point.

**Scale-down protocol:**

1. **Terminating replica identified** (HPA / KEDA picks lowest-utilization instance).
2. **`/health/ready` returns 503** — LB stops routing.
3. **SR6-D10 `Drain()` invoked** — 30s default timeout (120s for long-runners).
4. **Outbox flushed** — publisher final drain; remaining rows persist for next replica claim-lock.
5. **Circuit breakers opened** — outbound calls fast-fail; remaining handlers exit cleanly.
6. **WS connections closed** with close code 4011 (reuses SR6-D10 close code; client reconnects to remaining replicas).
7. **Replica terminated** after drain completes OR timeout.

**Pre-warm mechanism (V1+30d):**
- Services declaring `min_warm_replicas` in budget keep N instances above `replicas_min` during predictable-load windows
- Pre-warm replicas bootstrap fully (cache-fill, DB-pool pre-establish) before accepting traffic
- Reduces cold-start on rapid scale-up; prevents SLI-breach during scale-up ramp
- Cost trade-off tracked in capacity review (L9)

**Thundering-herd prevention on scale-up:**
- New replicas bootstrap with jittered delay (5-30s) before `/health/ready` = true
- `publisher` and `meta-worker` use claim-lock backoff (existing R6-L1 pattern)
- LLM gateway: respects dep `matrix.yaml` rate limits — no bulk LLM calls at boot

**Scale-down event audit:**

```sql
CREATE TABLE scaling_events (
  event_id              UUID PRIMARY KEY,
  service               TEXT NOT NULL,
  direction             TEXT NOT NULL,               -- 'up' | 'down'
  from_replicas         INT NOT NULL,
  to_replicas           INT NOT NULL,
  trigger               TEXT NOT NULL,               -- 'signal_cpu' | 'signal_queue' | 'signal_latency'
                                                     -- | 'signal_concurrent_llm' | 'manual_override'
                                                     -- | 'scheduled_prewarmed' | 'emergency_override'
  signal_value          DOUBLE PRECISION,            -- actual value that triggered
  signal_threshold      DOUBLE PRECISION,            -- threshold crossed
  initiated_at          TIMESTAMPTZ NOT NULL,
  completed_at          TIMESTAMPTZ,
  outcome               TEXT NOT NULL,               -- 'success' | 'partial' | 'failed' | 'drain_timeout'
  drain_duration_ms     BIGINT,                      -- for scale-down; time spent in SR6-D10 Drain
  inflight_lost_count   INT,                         -- for scale-down; non-zero = drain-timeout incident
  actor                 UUID,                        -- for manual_override / emergency_override
  related_incident_id   UUID                         -- if scaling decision was incident-driven
);
CREATE INDEX ON scaling_events (service, initiated_at DESC);
CREATE INDEX ON scaling_events (outcome, initiated_at DESC) WHERE outcome != 'success';
CREATE INDEX ON scaling_events (trigger, initiated_at DESC);
```

**Retention:** **1 year** (aligns `dependency_events` per SR6-D8 — high-volume operational audit).
**PII classification:** `none`.
**Write path:** via `MetaWrite()` (I8); append-only with narrow-column completion updates.

### 12AK.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| I4 (DB-per-service) | Capacity budget dimensions include per-service DB pool size |
| I5 (DB-per-reality) | Fleet shard utilization tracks per-reality DB shape |
| I6 (session concurrency) | Session-processor saturation is a per-reality ceiling (L4) |
| I8 (MetaWrite) | `shard_utilization` + `scaling_events` writes via MetaWrite |
| I11 (SVID) | Scaling actions by autoscaler require SVID; no anonymous scaling |
| I16 (timeout) | Timeouts size per-class scaling signals (can't scale on p99 if no timeouts) |
| **I17** (capacity budget) | **Proposed — this resolution; pending architect approval** |
| MV6 | Product-level player cap; SR8 adds platform-level ceilings ≥ MV6 |
| SR1-D2 | SLO targets = load-test breakpoint boundary; budget sized to meet SLO |
| SR1-D3 | Budget-utilization > 85% is burn-adjacent; integrates error-budget policy |
| SR5-D1 | Budget changes = `minor` deploy class (dimension up) or `major` (structural) |
| SR5-D3 | Canary rollout respects capacity budget per cohort |
| SR6-D5 | Degraded modes activated when capacity exhausted before auto-scale catches up |
| SR6-D9 | Bulkhead defaults feed into `db_pool_size` budget dimension |
| SR6-D10 | Drain protocol is the scale-down coupling (L10) |
| SR7-D3 | Chaos drill `load` category validates capacity model against breakpoint |
| S6-D6 | LLM capacity budget feeds cost projections; emergency override has billing impact |
| R4-L6 | Shard sizing (small/medium/large = 500/2K/10K realities) grounds fleet capacity |
| R7 | Session concurrency bound is per-reality ceiling L4 |
| C2 | Shard drain for rebalance reuses DB subtree split protocol |
| ADMIN_ACTION_POLICY §R4 | 3 new commands: `admin/capacity-override` Tier 2 · `admin/scaling-policy-update` Tier 2 · `admin/drain-shard` Tier 1 |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| Capacity budget matrix is yet-another-YAML | Same pattern as deps/chaos registries; consistent discipline |
| Load-test gate adds CI time | ~5-15 min per service for Baseline + Target; required for SLO commitments to be real |
| Pre-warm waste in V1+30d | Optional per service; cost tracked in review; trade-off is cold-start SLO breach vs continuous spend |
| Shard rebalance is slow (hours-days) | Reuses C2 migration protocol; user-visible `migrating` state is known mechanic |
| Emergency override 24h expiry | Forcing function; extension requires re-approval; prevents "override permanent" drift |
| Quarterly review cadence | Budget drift is slow; quarterly matches SR2-D8 ops review rhythm |
| LLM concurrent-calls as capacity dimension | Compute scaling doesn't help if upstream rate-limited; treating concurrency explicitly prevents over-scale |

**What this resolves:**

- ✅ Undeclared capacity targets — L3 matrix + (if approved) invariant I17
- ✅ Ad-hoc scaling rules — L6 policy templates + L7 observability
- ✅ Per-reality ceilings unenforced — L4 five ceilings with CAS/rate-limit enforcement
- ✅ Shard tracking gap — L5 `shard_utilization` table + placement policy
- ✅ Scale-up storms — L10 thundering-herd prevention (jittered bootstrap)
- ✅ Scale-down dropped work — L10 SR6-D10 Drain coupling
- ✅ Untested SLO promises — L8 load-test gate at Baseline/Target/Breakpoint/Degradation
- ✅ Ad-hoc budget changes — L9 review process + cost attribution + S6 integration
- ✅ LLM vs compute capacity confusion — L2 class taxonomy separates llm-gateway
- ✅ Inconsistent scaling signals — L3 per-class signal library at `contracts/capacity/signals.go`
- ✅ No scaling audit trail — L10 `scaling_events` table (1y)
- ✅ Noisy-neighbor at fleet level — L5 shard placement + L6 multi-tenant isolation SLO (SR1-D4)

**V1 / V1+30d / V2+ split:**

- **V1:**
  - L1 class taxonomy + bootstrap-class declaration
  - L2 `contracts/capacity/budgets.yaml` + CI lint + I17 (if approved)
  - L3 per-class scaling signals
  - L4 per-reality ceilings (5 enforced)
  - L5 `shard_utilization` table + placement policy
  - L6 HPA / KEDA / vertical policy templates
  - L7 core capacity metrics + alerts + DF11 panel
  - L8 load-test gate (Baseline + Target for V1-critical services)
  - L9 governance + quarterly review + cost attribution
  - L10 scale-down hygiene + `scaling_events` audit
- **V1+30d:**
  - L6 pre-warm mechanism for bursty services
  - L8 automated `capacity-gate-check.sh` CI hook
  - L8 Breakpoint + Degradation load tests
  - L5 automated shard rebalance heuristics
- **V2+:**
  - Predictive scaling (demand forecasting)
  - Per-model LLM cost-optimized routing (L6 llm-gateway evolution)
  - Write-sharding for data-plane services
  - Regional capacity (V3+ geo-scale)

**Residuals (deferred):**
- Geo-distributed capacity → V3+
- Multi-cloud capacity → out of scope V1/V2 (AWS only per CLAUDE.md hosting model)
- Kubernetes operator for capacity (vs plain HPA/KEDA) → evaluate V2+
- Spot-instance cost optimization → V2+ experiment

**Decisions locked (10, + SR8-D11 pending):**
- **SR8-D1** 4-class service taxonomy (web / worker / data-plane / llm-gateway) + composite pattern for mixed services
- **SR8-D2** Capacity budget matrix at `contracts/capacity/budgets.yaml` with V1/V2/V3 tiers per service × 5 dimensions (CPU / memory / DB pool / concurrent LLM / network)
- **SR8-D3** Per-class scaling signals + thresholds + hysteresis + cool-down windows
- **SR8-D4** 5 per-reality ceilings (players / WS conn / event rate / session-processor / NPC count) with MV6-inheriting defaults
- **SR8-D5** `shard_utilization` table + 3-state shard lifecycle (healthy / approaching_cap / drain_required) + placement policy
- **SR8-D6** Auto-scaling mechanism per class (HPA for web/llm-gateway · KEDA for worker · vertical-only for data-plane)
- **SR8-D7** Capacity observability (7 metrics + 7 alerts + DF11 capacity panel)
- **SR8-D8** Load-test gate at 4 points (Baseline / Target / Breakpoint / Degradation) integrated with G2-D4 loadtest-service
- **SR8-D9** Capacity governance (budget-change review process + quarterly cadence + cost attribution via S6)
- **SR8-D10** Scale-down hygiene via SR6-D10 Drain + `scaling_events` audit (1y retention) + thundering-herd prevention
- **SR8-D11** **PENDING architect approval** — proposed invariant I17 "every service declares a capacity budget". If approved → joins I16 in `00_foundation/02_invariants.md`. If rejected → SR8-D2 remains decision-class without invariant-status.

**Features added (11):**
- **IF-41** Capacity budget registry (`contracts/capacity/budgets.yaml`)
- **IF-41a** Service class taxonomy + bootstrap declaration
- **IF-41b** Scaling signal library (`contracts/capacity/signals.go`)
- **IF-41c** Per-reality capacity ceiling enforcer (in `world-service`)
- **IF-41d** `shard_utilization` tracking table + shard dashboard
- **IF-41e** Auto-scaling policy templates (HPA / KEDA / vertical)
- **IF-41f** `scaling_events` audit table (1y retention)
- **IF-41g** Capacity metrics + alerts + DF11 panel
- **IF-41h** Load-test capacity gate (`capacity-gate-check.sh` V1+30d)
- **IF-41i** Pre-warmed replica pool manager (V1+30d)
- **IF-41j** `admin/capacity-override` + `admin/scaling-policy-update` + `admin/drain-shard` CLI commands

**Remaining SRE concerns (SR9–SR12) queued:** alert tuning + pager discipline · supply chain security · turn-based game reliability UX · observability cost + cardinality.
