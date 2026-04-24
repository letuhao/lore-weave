<!-- CHUNK-META
chunk: SR12_observability_cost.md
origin: direct-authored 2026-04-24
origin_branch: mmo-rpg/design-resume
note: Not produced by scripts/chunk_doc.py split; authored as new SR-series content extending SR1-SR11. Final SR concern.
-->

## 12AO. Observability Cost + Cardinality — SR12 Resolution (2026-04-24)

**Origin:** SRE Review SR12 — final SRE concern. SR1-SR11 created ~45 alerts + 22 audit tables + dozens of metrics + structured logs. Each was cost-budgeted in its own SR; none coordinated across the whole surface. At V3 scale (target ~500 GB/day per SR1-D8), observability cost is material. SR12 makes the full observability surface **auditable, capped, and attributable** — the invariant I19 candidate makes "declared in inventory" the forcing function for everything else.

### 12AO.1 Problems closed

1. No single inventory of metrics + audit tables
2. Retention tier matrix declared in S8-D3 but individual tables drift per SR
3. Cardinality rules (SR1-D8) enforced by convention, not admission control
4. Log volume unbudgeted per service
5. Aggregate rollup ad-hoc — `alert_outcomes` has 90d+2y pattern but others don't
6. No meta-observability — can't tell which service's telemetry is expensive
7. Label-explosion bugs leak into production before rollback
8. Observability cost not attributed to tier (free / paid / premium)
9. V1 launch has ~45 alerts + 22 audit tables with mixed cardinality discipline
10. Quarterly retention review undesigned
11. Cost target (<500 GB/day V3) unvalidated against actual series count

### 12AO.2 Layer 1 — Observability Inventory Registry (proposed invariant I19)

Single source of truth at `contracts/observability/inventory.yaml`:

```yaml
# Metric entry
- type: metric
  name: lw_dependency_circuit_state
  owner_service: roleplay-service                   # emitter; multiple services may emit same metric
  also_emitted_by: [chat-service, world-service]
  labels:
    dep: { type: enum, source: "contracts/dependencies/matrix.yaml::name", max_cardinality: 50 }
    service: { type: enum, source: "contracts/service_acl/matrix.yaml::services", max_cardinality: 20 }
  metric_type: gauge
  cardinality_estimate: 50 × 20 = 1000
  retention_tier: default                            # Prometheus scrape retention
  declared_in: SR6-D7
  added: 2026-04-24

# Audit table entry
- type: audit_table
  name: turn_outcomes
  db: meta
  retention_hot_days: 365
  retention_cold_days: null
  pii_classification: low
  growth_rate_estimate: "~50K rows/day at V1; ~5M/day at V3"
  declared_in: SR11-D8
  added: 2026-04-24
```

**Required fields** per type:
- **Metric**: name · owner_service · labels + max_cardinality per label · metric_type · cardinality_estimate · retention_tier · declared_in
- **Audit table**: name · db · retention_hot_days · retention_cold_days · pii_classification · growth_rate_estimate · declared_in

**Proposed invariant I19:** "Every metric and audit table referenced in code is declared in `contracts/observability/inventory.yaml` with owner + cardinality estimate + retention + source SR."

**Status of I19:** **PENDING architect sign-off via POST-REVIEW** — not self-authorized per SR6/SR8/SR10 process lesson. If approved → joins I18 in `00_foundation/02_invariants.md` with enforcement point `scripts/observability-inventory-lint.sh`. If rejected → SR12-D1 stays decision-class without invariant-status.

**CI enforcement** (`observability-inventory-lint.sh`):
- Every `lw_*` metric declaration in Go / TS / Python source scanned; missing entry = lint fail
- Every `CREATE TABLE` migration with `audit` or `events` suffix scanned; missing entry = lint fail
- Label mismatch between declaration + code = lint fail
- Cardinality estimate must match pattern `<int> × <int> = <product>` or `<int>` — prevents silently adding unbounded labels

### 12AO.3 Layer 2 — Cardinality Budget per Service

Service-level cap at `contracts/observability/budgets.yaml`:

```yaml
- service: roleplay-service
  metric_series_budget: 50000                  # max active series this service contributes
  log_bytes_per_day_budget_gb: 10              # structured logs only
  audit_rows_per_day_budget: 200000             # sum across all audit tables written by service
  tier: v1                                       # budgets tiered same as SR8 capacity budgets
```

**Enforcement:**
- Actual series count derived from `inventory.yaml` cardinality_estimate sums; at PR time a service exceeding budget = lint fail
- Runtime: metric library emits `lw_observability_series_count{service}` gauge; SR9 alert if actual series > 90% of budget for 10 min
- Log volume: structured-logger samples per `sampling.yaml` (L4); `lw_observability_log_bytes_total{service}` counter; budget breach = SEV2 alert
- Audit growth: daily cron aggregates `INSERT` counts per audit table per service; budget breach = ticket + next capacity review

**Per-tier budgets** mirror SR8 V1/V2/V3 capacity-budget matrix. V1 numbers are starting estimates tuned from prototype data.

**`observability_budget_breaches` audit table:**

```sql
CREATE TABLE observability_budget_breaches (
  breach_id         UUID PRIMARY KEY,
  service           TEXT NOT NULL,
  resource          TEXT NOT NULL,              -- 'metric_series' | 'log_bytes' | 'audit_rows'
  budget            BIGINT NOT NULL,
  actual            BIGINT NOT NULL,
  breach_ratio      NUMERIC(10,3),               -- actual / budget
  detected_at       TIMESTAMPTZ NOT NULL,
  resolved_at       TIMESTAMPTZ,
  root_cause        TEXT,                        -- populated in weekly review
  remediation       TEXT
);
CREATE INDEX ON observability_budget_breaches (service, detected_at DESC);
CREATE INDEX ON observability_budget_breaches (resource, detected_at DESC) WHERE resolved_at IS NULL;
```

Retention **1 year**; aligns other 1y operational audit tables per SR6-D8 / SR8-D10 / SR11-D8.

### 12AO.4 Layer 3 — Retention Tier Audit

Cross-reference all **22 audit tables** (per SR1-SR11 accumulation) against S8-D3 retention tier matrix:

| Audit table | Declared retention | S8 tier | Reconciliation |
|---|---|---|---|
| `meta_write_audit` (S4) | 5y | Audit | ✅ aligned |
| `meta_read_audit` (S4) | 2y | Long-cold | ✅ aligned |
| `admin_action_audit` (S5/R13) | 5y | Audit | ✅ aligned |
| `service_to_service_audit` (S11) | 5y | Audit | ✅ aligned |
| `prompt_audit` (S9) | 90d hot + 2y cold | Hot + Long-cold | ✅ aligned |
| `user_cost_ledger` (S6, pseudonymize at 2y) | 7y + pseudonymize-at-2y | Billing + S8 override | ✅ aligned |
| `user_queue_metrics` (S7) | **TBD** | — | 🟡 flag — spec 1y aligned with operational |
| `user_consent_ledger` (S8) | active+2y | Consent | ✅ aligned |
| `pii_registry` (S8) | until crypto-shredded | Forever-until-erased | ✅ aligned |
| `canon_entries` + `canonization_audit` (S13) | forever / 5y | Forever + Audit | ✅ aligned |
| `book_authorship` (S13) | forever | Forever | ✅ aligned |
| `incidents` (SR2) | 5y | Audit | ✅ aligned |
| `feature_flags` (SR5) | lifecycle | — | ✅ ongoing state, not time-retained |
| `deploy_audit` (SR5) | 5y | Audit | ✅ aligned |
| `dependency_events` (SR6) | 1y | Operational | ✅ aligned |
| `chaos_drills` (SR7) | 3y | Mid-term | ✅ aligned |
| `shard_utilization` (SR8) | lifecycle | — | ✅ ongoing state |
| `scaling_events` (SR8) | 1y | Operational | ✅ aligned |
| `alert_outcomes` (SR9) | 90d hot + 2y cold aggregate | Hot + Long-cold | ✅ aligned |
| `alert_silences` (SR9) | lifecycle | — | ✅ ongoing state |
| `supply_chain_events` (SR10) | 3y | Mid-term | ✅ aligned |
| `turn_outcomes` (SR11) | 1y | Operational | ✅ aligned |
| `observability_budget_breaches` (this chunk) | 1y | Operational | ✅ aligned |

**Findings from this audit:**
- `user_queue_metrics` (SR7) retention was unspecified — formalized here as **1 year** (operational tier). SR7-D3 retroactively reconciled.
- No other drift detected.

**Quarterly retention review cadence** (SR2-D8): cross-reference `inventory.yaml` against S8 tier matrix; flag drift; rebaseline each V+30d.

### 12AO.5 Layer 4 — Log Sampling Strategy

Structured-logger config at `contracts/observability/sampling.yaml`:

```yaml
default_rates:
  error: 1.0                         # 100% — always capture errors
  warn: 0.50                         # 50% — capture most warnings
  info: 0.10                         # 10% — sampled for volume control
  debug: 0.01                        # 1% — trace-level; production-disabled by default

per_service_overrides:
  - service: auth-service
    error: 1.0
    warn: 1.0                        # auth warnings include failed logins; capture all
    info: 0.20
    debug: 0.0                       # disable in prod for PII safety
  - service: admin-cli
    error: 1.0
    warn: 1.0
    info: 1.0                        # admin actions audited separately too; info = low volume
    debug: 0.50
```

**Per-call-chain trace sampling:** if any log in a trace is sampled at rate R, all logs in that trace also captured (trace-preservation). Via OpenTelemetry trace_id continuity.

**PII safety:** structured logger's field-tag system (§12X.L7 Logger) enforces PII=low rule per S8-D2. Sampling rate doesn't relax PII scrubbing — every sampled log still goes through `pkg/logging/` scrubber.

**`admin/log-sampling-update`** = S5 Tier 2 Griefing — changes runtime sampling rate; reason + 7-day auto-expire required.

### 12AO.6 Layer 5 — Audit Rollup Cadences

For high-volume operational audit tables with long aggregate retention, explicit rollup protocol:

| Table | Hot (raw rows) | Warm (hourly agg) | Cold (daily agg) | Rollup cron |
|---|---|---|---|---|
| `alert_outcomes` (SR9) | 90d | — | 2y weekly agg per alert_id | nightly |
| `turn_outcomes` (SR11) | 365d raw | — | 5y daily agg per (session_type, tier) | V1+30d |
| `dependency_events` (SR6) | 365d raw | — | 5y weekly agg per (dep, event_type) | V1+30d |
| `scaling_events` (SR8) | 365d raw | — | 5y weekly agg per service | V1+30d |
| `chaos_drills` (SR7) | 3y raw | — | — | — (low volume) |
| `supply_chain_events` (SR10) | 3y raw | — | — | — (low volume) |
| `prompt_audit` (S9) | 90d | — | 2y context-hash + metadata | nightly per S9-D9 |

**Rollup mechanics:**
- Cron job in `admin-cli` (V1) or dedicated aggregator service (V2+)
- Writes cold-aggregate rows to parallel table (e.g., `alert_outcomes_weekly_agg`)
- Deletes raw rows past retention-hot threshold
- Lossy-but-purposeful: raw rows are for recent-incident forensics; aggregates are for trend analysis

**V1 minimal aggregations:** `alert_outcomes` weekly agg (per SR9-D4) + `prompt_audit` cold archive (per S9-D9). Other tables defer aggregation to V1+30d with baseline data informing schema.

### 12AO.7 Layer 6 — Meta-Observability

The observability-of-observability surface. Meta-metrics at `contracts/observability/meta.yaml`:

| Meta-metric | Labels | Purpose |
|---|---|---|
| `lw_observability_series_count{service}` | service | Prometheus actual series per emitter service |
| `lw_observability_log_bytes_total{service}` | service | Structured log volume per service |
| `lw_observability_log_events_total{service, level}` | service, level ∈ {error, warn, info, debug} | Per-severity event count |
| `lw_observability_audit_writes_total{service, table}` | service, table | Audit-table insert rate per service |
| `lw_observability_cardinality_violations_total{service, metric}` | service, metric (top-K) | Admission-control rejections (L7) |
| `lw_observability_retention_overrides_active` | (no labels) | Count of active `admin/retention-override` uses |

**Dashboard (DF11 observability panel):**
- Per-service budget-vs-actual heatmap (mirror of SR8 capacity dashboard)
- Log-volume timeline per service (7-day trend)
- Audit-table growth rate per table + budget line
- Cardinality-violation top offenders (V1+30d data-driven)
- Retention-override activity log

**Alerts** (registered via SR9-D2 `contracts/alerts/rules.yaml`):
- `lw_observability_series_count / budget > 0.9` for 10 min → SEV2 (PAGE) — investigate new label/metric leaking
- `lw_observability_log_bytes_total` rate > 1.5× budget for 1 hour → SEV2 (PAGE)
- `lw_observability_cardinality_violations_total` rate > 10/min → SEV2 — new code path bypassing admission
- Quarterly: retention-drift audit fails → WARN (ticket) — reconciliation needed

### 12AO.8 Layer 7 — Cardinality Admission Control

Metric library (`pkg/metrics/`) enforces at emission:

```go
// Pseudocode
func (m *Counter) Inc(labels ...Label) error {
    // Look up declaration from observability/inventory.yaml
    decl := inventory.Lookup(m.name)

    // Reject labels not in declared set
    for _, lbl := range labels {
        if !decl.AllowsLabel(lbl.Name) {
            metrics.CardinalityViolation.Inc(m.name, "unknown_label")
            // Policy: V1 warn-and-drop; V1+30d reject (hard error)
            return ErrCardinalityViolation
        }
        if decl.LabelValuesExceeded(lbl.Name, lbl.Value) {
            metrics.CardinalityViolation.Inc(m.name, "value_explosion")
            return ErrCardinalityExplosion
        }
    }

    m.emit(labels...)
    return nil
}
```

**Bundled policies:**
- **V1**: warn-and-drop (log violation, drop the emission, don't break the calling code)
- **V1+30d**: hard-reject (return error; emission library refuses to proceed; forces bug fix)
- **V2+**: pre-commit admission hook (deny PRs adding new labels not in inventory)

**Coverage scope:**
- All `lw_*` Prometheus metrics
- Scoped emission helpers in Go/TS/Python all route through the same `pkg/metrics/` library (enforced by SR6-D3 pattern)
- Third-party library metrics (e.g., Go runtime metrics) have distinct namespace `go_*` / `process_*`; not subject to admission control but still counted toward service series budget

### 12AO.9 Layer 8 — Per-Tenant Cost Attribution

**V1 scope:** observability cost **NOT** attributed per user/tier (complexity too high for launch). Cost is tracked per-service only (L6 meta-metrics).

**V2+ evolution** (post-monetization): extend `user_cost_ledger` (S6-D6) pattern:
- Per-user observability-events-triggered counter
- Attribute service-level cost prorata to users based on active sessions
- Premium tier users generate ~2x observability volume (more intense LLM calls, more turns); cost model reflects

**Cost attribution for platform-paid vs BYOK:**
- Platform-paid users: observability cost → platform overhead (no user pass-through)
- BYOK users: same (observability runs on platform-paid infra regardless of LLM provider)

**Implication for D1 (LLM cost/user-hour OPEN):** observability cost is a separate line item; D2 pricing formula needs observability overhead factor (V2+ when D1 closes).

### 12AO.10 Layer 9 — V1 Rebaseline Cadence

**V1 launch → V1+4 weeks:** weekly observability-cost review. More frequent than quarterly SR2-D8 cadence because initial production data tunes budgets.

**Per-week review artifact** (`docs/sre/observability-reviews/<yyyy>-W<N>.md`):
- Meta-metric snapshots (series / log / audit growth per service)
- Top-5 budget utilizers
- Cardinality violations per service
- Retention drift (if any)
- Proposed budget adjustments
- Action items per SR4-D5 schema

**Participants:** SRE primary on-call + 1 service owner per reviewed service. V1 solo-dev = same-human + 48h-sit (SR4 pattern).

**After V1+4 weeks:** cadence relaxes to monthly, then quarterly per SR2-D8 default.

**Rebaseline triggers** outside cadence:
- Service adds new metric/audit → PR-time budget check + inventory update
- Service scales to new tier (V1→V2) → budget rebaselines per tier
- Retention tier change on any table → cross-file update (inventory + budgets)

### 12AO.11 Layer 10 — V1 Minimal Bar

**V1 launch gate:**

1. **All 22 audit tables** declared in `contracts/observability/inventory.yaml` with fields populated
2. **All ~45 alerts** (migrated via SR9-D10) cross-referenced in inventory with cardinality estimates
3. **All ~30 metrics** across SR1/SR6/SR7/SR8/SR9/SR10/SR11 declared with labels + max_cardinality per label
4. **Per-service budgets** in `contracts/observability/budgets.yaml` for all 19 services (12 existing + 7 MMO-RPG V1)
5. **Retention tier audit** (L3) clean — all 22 tables reconciled; `user_queue_metrics` 1y finalized
6. **Log sampling config** at `contracts/observability/sampling.yaml` with defaults + per-service overrides for auth-service + admin-cli
7. **Cardinality admission control** (L7) active in warn-and-drop mode across Go / TS / Python emission libraries
8. **Meta-metrics** (L6) emitting; DF11 observability panel operational
9. **V1 rebaseline cadence** (L9) — first weekly review scheduled for V1+7 days
10. **Invariant I19** (if approved) — inventory is canonical; missing-declaration lint blocks merge
11. **`admin/metric-label-audit` + `admin/retention-override` + `admin/log-sampling-update`** commands registered per S5
12. **`observability_budget_breaches` table** operational with MetaWrite integration

**V1+30d evolution:**
- L7 admission control: warn-and-drop → hard-reject (after baseline data confirms allowlists are correct)
- L6 rollup crons for `turn_outcomes` / `dependency_events` / `scaling_events`
- L10 rebaseline cadence relaxes to monthly
- Cost attribution model stub (L8) populated with per-service line items

**V2+ evolution:**
- Per-tenant attribution (L8) for post-monetization
- Predictive budget breach (ML anomaly detection)
- Automated inventory generation from source code (reduce PR burden)
- Pre-commit admission hook (PR-time hard reject)

### 12AO.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| I8 (MetaWrite) | `observability_budget_breaches` writes via MetaWrite |
| I14 (additive-first schema) | Inventory schema evolves additively; new fields nullable |
| SR1-D8 | Cardinality rules operationalized via L7 admission control |
| SR2-D8 | Quarterly retention audit cadence extends SR2 ops rhythm |
| SR3 | Observability runbook added — how to investigate budget breaches |
| SR4-D7 | Root cause `monitoring_gap` — inventory gaps surface via L2 budget overflows |
| SR5-D1 | Budget changes = `minor` deploy class |
| SR6-D7 | 6 SR6 metrics migrated to inventory |
| SR7 | Chaos drill meta: does a drill cause budget breach? Surface via L6 |
| SR8-D7 | 7 SR8 metrics migrated to inventory; capacity budget + observability budget share review cadence |
| SR9-D2 | ~45 alerts registered in `rules.yaml`; inventory cross-references for cardinality audit |
| SR10 | Supply chain: observability emission libraries pinned per I18 |
| SR11-D8 | `turn_outcomes` retention reconciled (already 1y aligned) |
| S8-D3 | Retention tier matrix is canonical; L3 audit enforces reconciliation |
| S9-D9 | `prompt_audit` cold archive format coordinated |
| S6-D6 | `user_cost_ledger` reference for V2+ per-tenant attribution pattern |
| I19 (capacity budget; proposed this resolution) | I19 adds inventory invariant — same shape as I16/I17/I18 |
| ADMIN_ACTION_POLICY §R4 | 3 new commands: `admin/metric-label-audit` Tier 3 · `admin/retention-override` Tier 2 · `admin/log-sampling-update` Tier 2 |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| Inventory YAML duplicates code declarations | Lint catches drift; single source of truth for cardinality budget math |
| L7 admission adds ~10-50μs per metric emission | Negligible; prevents O(∞) label explosion |
| Warn-and-drop V1 mode fails silently | Better than breaking prod with hard-reject before baselines are known |
| Quarterly retention audit is manual | Small surface area; automation when pattern emerges |
| V1 observability cost is gross-attributed per-service | Per-tenant V2+ complexity not V1-necessary |
| 22 audit tables seems like a lot | Accumulated across 11 SRs; consolidation = regression risk |
| Observability invariant I19 adds a layer | Same pattern as I16/I17/I18; proven useful |

**What this resolves:**

- ✅ No single inventory — L1 + (if approved) I19
- ✅ Retention drift — L3 audit + reconciliation (1 finding: `user_queue_metrics` formalized)
- ✅ Cardinality convention-only — L7 admission control
- ✅ Log volume unbudgeted — L2 per-service budgets
- ✅ Ad-hoc rollup — L5 per-table protocol
- ✅ No meta-observability — L6 `lw_observability_*` metrics + panel
- ✅ Label-explosion risk — L7 admission V1 warn-and-drop → V1+30d hard-reject
- ✅ No cost attribution — L8 V1 gross per-service (per-tenant V2+)
- ✅ V1 launch discipline — L10 12-item gate
- ✅ Quarterly review undefined — L9 + L3 cadence operationalized

**V1 / V1+30d / V2+ split:**

- **V1:**
  - L1 `contracts/observability/inventory.yaml` + CI lint (+ I19 if approved)
  - L2 per-service cardinality + log budget + `observability_budget_breaches`
  - L3 retention tier audit (22 tables) + reconciliation
  - L4 log sampling config
  - L5 `alert_outcomes` weekly agg + `prompt_audit` cold archive
  - L6 meta-metrics + DF11 panel
  - L7 warn-and-drop cardinality admission
  - L9 weekly rebaseline cadence first 4 weeks
  - L10 12-item launch gate
- **V1+30d:**
  - L5 rollup crons for turn/dependency/scaling events
  - L7 admission → hard-reject
  - L9 cadence → monthly
- **V2+:**
  - L8 per-tenant cost attribution
  - ML anomaly detection for budget breach
  - Pre-commit admission hook
  - Automated inventory generation from source

**Residuals (deferred):**
- Predictive budget breach detection → V2+
- Cross-region observability (V3+)
- External compliance observability (audit log export to external systems) → V2+ compliance work

**Decisions locked (10 + 1 pending):**
- **SR12-D1** Observability inventory registry at `contracts/observability/inventory.yaml` with required fields (metric: labels+max_cardinality+metric_type · audit: retention+pii+growth_rate) + CI enforcement
- **SR12-D2** Per-service cardinality + log + audit budgets at `contracts/observability/budgets.yaml`; `observability_budget_breaches` table (1y retention); series-count alert at 90% of budget
- **SR12-D3** Retention tier audit + reconciliation against S8-D3; quarterly cadence; V1 reconciliation finding: `user_queue_metrics` (SR7) formalized at 1-year retention
- **SR12-D4** Log sampling strategy (error 100% · warn 50% · info 10% · debug 1% default) with per-service overrides; trace-preservation; PII scrubbing non-negotiable
- **SR12-D5** Aggregate rollup cadences per-table protocol; V1 minimum: `alert_outcomes` weekly agg + `prompt_audit` cold archive; other tables defer to V1+30d
- **SR12-D6** Meta-observability (`lw_observability_*`) + DF11 panel + 4 specific alerts
- **SR12-D7** Cardinality admission control in metric library; V1 warn-and-drop → V1+30d hard-reject → V2+ pre-commit
- **SR12-D8** Per-service gross attribution V1; per-tenant V2+ extending S6-D6 pattern
- **SR12-D9** V1 rebaseline cadence — weekly first 4 weeks → monthly → quarterly per SR2-D8
- **SR12-D10** V1 minimal bar — 12-item launch gate (inventory / budgets / retention-clean / sampling / cardinality-admission-warn / meta-metrics / rebaseline-scheduled / admin commands / table operational)
- **SR12-D11** **PENDING architect approval** — proposed invariant I19 "every metric + audit table declared in `contracts/observability/inventory.yaml`". If approved → joins I18 in foundation invariants with enforcement `observability-inventory-lint.sh`. If rejected → SR12-D1 stays decision-class.

**Features added (11):**
- **IF-45** Observability inventory registry (`contracts/observability/inventory.yaml`)
- **IF-45a** `observability-inventory-lint.sh` CI lint (metric + audit-table declaration enforcement)
- **IF-45b** Per-service cardinality + log + audit budgets (`budgets.yaml`)
- **IF-45c** `observability_budget_breaches` audit table (1y retention)
- **IF-45d** Retention tier audit cron + `user_queue_metrics` formalization
- **IF-45e** Log sampling configuration + per-service override + `admin/log-sampling-update`
- **IF-45f** Audit rollup crons (`alert_outcomes` weekly agg + `prompt_audit` cold archive; others V1+30d)
- **IF-45g** Meta-observability metrics + DF11 panel + 4 alerts
- **IF-45h** Cardinality admission control in `pkg/metrics/` (warn-and-drop V1 → hard-reject V1+30d)
- **IF-45i** Weekly rebaseline cadence template + V1 solo-dev pattern
- **IF-45j** `admin/metric-label-audit` + `admin/retention-override` CLI commands

**SRE Review complete (12/12)** — SR12 is the final concern. All prior SRs' observability outputs audited, capped, attributed, and gated. V1 observability discipline established.
