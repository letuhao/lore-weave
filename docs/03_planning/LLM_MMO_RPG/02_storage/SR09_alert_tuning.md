<!-- CHUNK-META
chunk: SR09_alert_tuning.md
origin: direct-authored 2026-04-24
origin_branch: mmo-rpg/design-resume
note: Not produced by scripts/chunk_doc.py split; authored as new SR-series content extending SR1-SR8.
-->

## 12AL. Alert Tuning + Pager Discipline — SR9 Resolution (2026-04-24)

**Origin:** SRE Review SR9 — SR1 through SR8 accumulated **~35 declared alerts** across SLO burns, dependency failures, chaos-drill aborts, capacity thresholds. SR1-D6 required every alert to derive from an SLO but did not address **which alerts actually wake humans up, how noisy is too noisy, how we tune thresholds without regression, or who audits the pager load**. Without discipline the pager becomes noise; on-call burns out; SEV0 signal gets missed in the flood. SR9 makes alerts **actionable, measured, and tunable** on a regular cadence.

### 12AL.1 Problems closed

1. Alerts declared across 4 SR resolutions with inconsistent action semantics
2. No distinction between "page now" and "review weekly"
3. Alert thresholds set on design intuition, never tuned against real traffic
4. No tracking of false-positive / false-negative rate
5. Manual silence-forever anti-pattern (slow decay into noise)
6. Alert → runbook linkage declared per-alert but not enforced
7. Pager-rotation load undistributed; some on-call weeks crushingly heavy
8. Alert storms flood pagers during large incidents
9. Weekly alert review referenced in SR2-D8 but not operationalized
10. "Missed alert" (real incident, no fire) untracked → no improvement signal
11. V1 launch has ~35 alerts with variable quality; no rebaseline process

### 12AL.2 Layer 1 — Alert Taxonomy (4 severities × 4 action-classes)

Every alert declares **both** a severity AND an action-class:

| Severity | Meaning | Typical source |
|---|---|---|
| **SEV0** | User impact NOW; data integrity; security incident | SLO burn critical · P0 dep down · audit hash mismatch |
| **SEV1** | User impact imminent; degraded mode active | SLO burn high · P1 dep down · canon injection detected |
| **SEV2** | Investigation needed; time-bounded | Retry-exhaustion spike · capacity budget >95% · scale-up failed |
| **WARN** | Review at next cadence | Capacity budget >85% · shard approaching_cap · flag past removal date |

| Action-class | Behavior | Delivery |
|---|---|---|
| **page-now** | Immediate pager; on-call acknowledges within TTA per SR2-D1 | PagerDuty · phone · SMS |
| **page-batched** | Grouped within 5-min windows; rate-limited per on-call | Slack + PagerDuty batched digest |
| **ticket-only** | Creates ticket in queue; reviewed at next daily ops check | Linear / GitHub issue |
| **log-only** | Structured log + metric increment; no human notification | Prometheus + structured log |

**Severity ↔ action-class matrix (defaults; overridable per alert with justification):**

| Severity | Default action-class | Rationale |
|---|---|---|
| SEV0 | page-now | Immediate response required |
| SEV1 | page-now (paid-hours) / page-batched (off-hours) | Degraded not dead; rate-limit prevents pager-flood |
| SEV2 | page-batched (paid-hours) / ticket-only (off-hours) | Investigative; no emergency |
| WARN | ticket-only | Cadence review handles it |

**Override protocol:** any deviation from the default matrix (e.g., a SEV1 that's always page-now regardless of hour) requires `override_justification` field in rule + tech-lead review.

### 12AL.3 Layer 2 — Alert Rule Schema-as-Code

Single source of truth at `contracts/alerts/rules.yaml`:

```yaml
- alert_id: lw_sli_turn_completion_burn_critical
  sli_ref: sli_turn_completion                  # SR1-D1
  derivation_rule: "burn_rate_7d > 10"          # from SR1-D3 error-budget policy
  threshold_value: 10
  threshold_unit: "×baseline"
  duration: 5m                                   # fire after 5 min sustained
  severity: SEV0
  action_class: page-now
  runbook: docs/sre/runbooks/llm-provider/llm-turn-completion-burn.md   # SR3
  owner_service: roleplay-service               # routes via SR2-D3 alert-routing matrix
  tier_scope: [paid, premium]                   # which user tiers; free-tier excluded
  quiet_hours: null                              # no quiet hours — SEV0 always pages
  override_justification: null                   # default matrix match
  baselined_since: 2026-05-15                    # L3 tuning process (14-day baseline)
  last_reviewed: 2026-04-24
```

**Required fields:** `alert_id` · `sli_ref` · `derivation_rule` · `threshold_value` · `duration` · `severity` · `action_class` · `runbook` · `owner_service`. CI lint `scripts/alert-rule-lint.sh` blocks PRs with missing fields, dead `runbook` path, unknown `sli_ref`, or severity↔action-class mismatch without `override_justification`.

**Rule validation CI hook** (extends SR1-D6): every rule's `derivation_rule` expression is parsed + replayed against last 7d metrics during CI — answers "would this alert have fired correctly?" Pre-prod deploy of new alerts fails if replay shows >50 fires (clear false-positive) or <0 (thought-it-was-actionable-but-never-triggers; reclassify as WARN or remove).

### 12AL.4 Layer 3 — Threshold Tuning Process (2-week baseline)

New or changed alerts follow a staged promotion:

| Stage | Duration | Action-class | Outcome review |
|---|---|---|---|
| **0 — design** | PR merged | log-only | CI validation rule replay clean |
| **1 — baseline** | 14 days in prod | log-only → ticket-only at day 7 | Fire frequency + FP rate collected; expected range tuned |
| **2 — staged** | 14 days | page-batched | On-call acknowledges each fire; notes in `alert_outcomes` (L4) |
| **3 — promoted** | indefinite | per severity↔action-class default | Full production signal |

**Noisy-alert auto-downgrade (protection rule):** any alert at `page-now` with FP rate > 40% over last 30 days auto-downgraded to `page-batched` + flagged for threshold retune. Auto-downgrade writes an `alert_outcomes` row `event_type=auto_downgraded` and notifies owner-service + SRE Slack. Re-promotion requires tech-lead approval + baseline re-run.

**Missed-alert escalation:** any real incident (`incidents` table entry per SR2-D7) with no contributing alert fire in the 30 min preceding creates an `alert_outcomes` row `event_type=missed` — surfaces in weekly review (L8) and routinely becomes a "new alert to add" action item.

### 12AL.5 Layer 4 — Alert Outcomes Audit

```sql
CREATE TABLE alert_outcomes (
  outcome_id            UUID PRIMARY KEY,
  alert_id              TEXT NOT NULL,                   -- from rules.yaml
  fired_at              TIMESTAMPTZ NOT NULL,
  severity              TEXT NOT NULL,                   -- severity at time of fire (may differ from current)
  action_class          TEXT NOT NULL,
  event_type            TEXT NOT NULL,                   -- 'fired' | 'acknowledged' | 'dismissed_false_positive'
                                                         -- | 'auto_downgraded' | 'auto_escalated' | 'missed'
                                                         -- | 'silenced_by_admin' | 'correlated_incident'
  acknowledged_at       TIMESTAMPTZ,                     -- if acknowledged (page-now or page-batched)
  acknowledged_by       UUID,                            -- user_ref_id
  related_incident_id   UUID,                            -- if correlated with real incident (SR2-D7)
  dismiss_reason        TEXT,                            -- for dismissed_false_positive
  silence_id            UUID,                            -- if silenced (L6)
  notes                 TEXT                             -- max 500 chars; scrubbed per §12X.4
);

CREATE INDEX ON alert_outcomes (alert_id, fired_at DESC);
CREATE INDEX ON alert_outcomes (event_type, fired_at DESC);
CREATE INDEX ON alert_outcomes (acknowledged_by, fired_at DESC);
CREATE INDEX ON alert_outcomes (related_incident_id) WHERE related_incident_id IS NOT NULL;
```

**Retention:** **90 days hot + 2 years cold aggregate** (aligns SR1-D8 observability cost controls). Cold aggregate = weekly roll-up per alert_id: {fire_count, FP_count, median_ack_time, incident_correlation_count}; raw rows discarded after 90d.
**PII classification:** `low` (opaque user_ref_id per S8-D1; notes scrubbed).
**Write path:** via `MetaWrite()` (I8); append-only; no updates except `acknowledged_at` / `acknowledged_by` / `dismiss_reason` / `notes` (narrow-column allowlist encoded in MetaWrite validator).

**Correlation:**
- `related_incident_id` populated when alert fires within 30 min of an incident declaration on the same service
- `missed` event_type = incident with no alert fire in preceding 30 min — identifies monitoring gaps
- `auto_downgraded` / `auto_escalated` = L3 tuning-process artifacts

### 12AL.6 Layer 5 — Silence + Snooze Protocol

```sql
CREATE TABLE alert_silences (
  silence_id        UUID PRIMARY KEY,
  alert_id_pattern  TEXT NOT NULL,                       -- exact or glob, e.g. 'lw_dependency_*'
  reason            TEXT NOT NULL,                       -- min 50 chars; scrubbed
  initiated_by      UUID NOT NULL,
  initiated_at      TIMESTAMPTZ NOT NULL,
  expires_at        TIMESTAMPTZ NOT NULL,                -- mandatory; max 30 days
  scope             JSONB,                                -- {service, reality_ids, cohort, tier}
  cleared_at        TIMESTAMPTZ,
  cleared_by        UUID,
  related_incident_id UUID,                              -- if during incident
  related_maintenance_id UUID                             -- if during announced maintenance
);

CREATE INDEX ON alert_silences (expires_at) WHERE cleared_at IS NULL;
CREATE INDEX ON alert_silences (alert_id_pattern);
```

**Governance:**
- `admin/alert-silence` = **S5 Tier 2 Griefing** (user-visible — on-call coverage reduced; reason + duration + notify SRE Slack required)
- **Max duration 30 days**; no manual-permanent-silence
- Auto-clear at `expires_at`; extension = new silence (creates fresh audit trail)
- Silence-during-incident (`related_incident_id` set) bypasses the 30-day cap (incident resolution may take longer) but auto-clears when incident `resolved`
- Silence-during-maintenance (`related_maintenance_id` set; linked to `status-page-admin` maintenance window) auto-clears at maintenance end
- Weekly alert review (L8) flags all silences >7 days

**Anti-patterns blocked:**
- `alert_id_pattern = '*'` (silence everything) = requires dual-actor + 24h cooldown (S5 Tier 1 equivalent)
- Silence without reason = CI validator rejects (reason < 50 chars)
- Silence created after alert fires within 5 min = flagged in review (looks like "shut up alert" rather than "planned maintenance")

### 12AL.7 Layer 6 — Alert-to-Runbook Contract

**Rule:** every SEV0, SEV1, SEV2 alert MUST point at an existing runbook. WARN alerts SHOULD but may defer.

**CI enforcement** (extends SR3-D5 "three CI drift-detection lints"):
1. `alert-runbook-sync.sh` — PR modifying `rules.yaml` must update the referenced runbook's `applies_to_alerts` frontmatter (SR3-D1) · fails PR merge
2. `alert-runbook-dead-ref.sh` — daily cron scans `rules.yaml` for `runbook:` paths that don't exist; opens tracking issue in SRE queue
3. `alert-coverage-check.sh` — SR3-D3 V1-gate runbook list cross-referenced with alert rules; every V1-critical alert has a runbook (extends SR3 27-runbook gate → 33 with SR7's 5 chaos runbooks + SR8's `admin/drain-shard.md` → V1 runbook count settles at 33)

**Exception** for WARN-tier alerts: `runbook: PLACEHOLDER` allowed for 60 days from baseline-start with mandatory follow-up ticket; auto-escalates to ticket owner if PLACEHOLDER remains at 60 days.

**Derivation-rule ↔ runbook contract:** runbook's `Symptoms` section (SR3-D1) references the alert `derivation_rule` expression. If rule changes, runbook update is mandatory in the same PR (CI lint 1 above catches this).

### 12AL.8 Layer 7 — Pager Rotation Load Discipline

Extends SR2-D2 (tiered rotation) with **measured pager load** per on-call.

**Per-rotation metrics** (weekly aggregation):
- `pages_received` — total page-now + page-batched events (SR2-D1 TTA applies)
- `median_ack_time_s` — time from page to acknowledge
- `incidents_declared` — from pages → real incidents (SR2-D4)
- `false_positive_rate` — from L4 `dismissed_false_positive` / `pages_received`
- `handoff_quality_score` — tech-lead-assigned 1-5 rating per SR2-D2 handoff doc + retro

**Rotation rebalance triggers:**

| Condition | Action |
|---|---|
| `pages_received` > 10/week for 2 consecutive weeks | Tech-lead + SRE review rotation; likely root-cause = noisy alert (L3 tuning) or overloaded service |
| `median_ack_time` > 2× SR2-D1 TTA for 2 consecutive weeks | Investigate: rotation burnout or pager accessibility issue |
| `false_positive_rate` > 30% for 2 consecutive weeks | Alert review sprint (L8) — goal: reduce to <15% |
| `handoff_quality_score` < 3 across 2 rotations | Handoff template / process review per SR2-D2 |

**Solo-dev reality (V1):** one human plays all roles. Metrics still collected (baseline for team-growth). "Rotation rebalance" = adjust cadence of drills/reviews to reduce solo load. V2+ when team expands, metrics inform shift sizing.

**Escalation chain load audit (extends SR2-D3 fallback chain):** fallback-path fires (primary didn't ack → secondary) logged to `alert_outcomes`; if fallback fires > 5% of total pages, primary rotation may need support.

### 12AL.9 Layer 8 — Weekly Alert Review

Operationalized SR2-D8 weekly cadence into concrete alert-review artifact.

**Template:** `docs/sre/alert-reviews/YYYY-WW.md`:

```markdown
# Alert Review — Week WW of YYYY

## Top-10 alerts by volume
| alert_id | fires | acknowledged | dismissed (FP%) |

## Top-3 false-positive
| alert_id | FP rate | proposed action |

## Recently silenced (last 7 days)
| silence_id | alert_pattern | reason | expires |

## Recently added (last 14 days)
| alert_id | baseline stage | findings |

## Missed alerts (incidents with no fire)
| incident_id | service | duration | proposed new alert |

## Rotation metrics
| on-call period | pages | median ack | FP rate | handoff score |

## Action items for next week
- [ ] tune threshold X
- [ ] add alert for missed scenario Y
- [ ] retire alert Z (FP > 60% over 30 days)
```

**Review participants:** SRE + primary on-call (off-rotation week participation optional). V1 solo-dev = same human, same 48h-sit pattern as SR4 postmortems.

**Outputs feed:**
- SR1 SLO review (L3 tuning data → SLO realism)
- SR3 runbook updates (new failure modes → runbook entries)
- SR6 matrix updates (threshold/timeout re-tuning from real failure data)
- Action items tracked in `docs/sre/alert-reviews/` with `owner` + `due_date` + status per SR4-D5 pattern

### 12AL.10 Layer 9 — Alert Storm Protection

When incident generates > N correlated alerts, pager flood drowns signal.

**Storm detection:** `lw_alert_fires_total{action_class="page-now"}` rate > 10/5min triggers storm mode.

**Storm protocol:**

1. Active storm detection → `lw_alert_storm_active` gauge = 1
2. Subsequent page-now alerts within 5min window **batched** to on-call WS channel (not pager)
3. Batched digest posted every 2 min: "Storm active (N alerts on S services since T)"
4. On-call already-paged; storm protocol ensures signal stays visible without additional phone-buzz
5. Storm clears when rate < 10/5min for 10 consecutive minutes
6. Post-storm summary auto-posted to `#inc-<incident>` channel (per SR2-D6)

**Storm-mode exceptions** (always page even during storm):
- NEW alert not fired in preceding 30 min (might be different root cause)
- Different service from storm origin (different fault domain)
- SEV0 absolutely always pages (storm protection ineligible)

**Storm audit:** `alert_storms` rows in `alert_outcomes` (`event_type=storm_activated` / `storm_cleared`) for postmortem timeline reconstruction.

### 12AL.11 Layer 10 — V1 Minimal Bar + Rebaseline

**V1 launch gate:**

1. **All existing SR1/SR6/SR7/SR8 SEV0/SEV1 alerts migrated** to `contracts/alerts/rules.yaml` with required fields populated (6 from SR1 + 6 from SR6 + 0 direct from SR7 + 7 from SR8 = **19 alerts minimum**).
2. **Each has**: runbook link (exists, non-PLACEHOLDER for SEV0/SEV1) · derivation_rule validated against 7d replay · owner_service declared · baselined_since set.
3. **`alert-rule-lint.sh` CI passing** on every V1-critical alert.
4. **V1 baselined alerts cleared Stage 3 (promoted)** — no V1-launch-critical alert still at Stage 1/2.
5. **2 weeks of `alert_outcomes` data** collected per alert before launch (forcing function for baseline-tuned thresholds).

**V1 rebaseline workflow:**
- Pre-launch `scripts/v1-alert-rebaseline.sh` generates a rebaseline report: per-alert fire rate from 14-day replay, proposed threshold adjustment, FP estimate
- Tech-lead reviews + applies adjustments
- CI gate `v1-alerts-rebaselined` passes only when `baselined_since` + `last_reviewed` are recent (< 7 days pre-launch)

**V1+30d evolution:**
- Layer 4's automatic downgrade / escalation kicks in based on accumulated data
- Layer 9 storm-mode tuning from V1 incident experience
- Alert-rule-lint extension: cost model integration (every alert has an estimated page-load → total on-call load capped)

### 12AL.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| SR1-D6 | Alert derivation from SLO rule: SR9-D2 adds action-class + schema-as-code |
| SR1-D8 | Retention + cardinality rules govern `alert_outcomes` storage model |
| SR2-D1 | Severity matrix referenced verbatim (SEV0/1/2/3) |
| SR2-D2 | Pager rotation discipline extended with measured pager load (L7) |
| SR2-D3 | Alert routing matrix referenced via `owner_service` field |
| SR2-D8 | Weekly review cadence operationalized into `docs/sre/alert-reviews/` artifact |
| SR3-D1 | Runbook frontmatter `applies_to_alerts` cross-linked; PR edits enforce bidirectional update |
| SR3-D3 | V1 runbook gate reconciled: 27 base + 5 chaos + 1 drain-shard = **33 runbooks at V1 launch** |
| SR3-D5 | Three CI drift-detection lints extended with alert-runbook variants |
| SR4-D5 | Alert review action-item tracking uses SR4 schema (owner/due/status) |
| SR4-D7 | `monitoring_gap` root-cause correlates with `missed` alerts from L4 |
| SR5-D2 | Deploy freeze auto-silences alerts on the frozen scope (silence tagged `related_maintenance_id`) |
| SR6-D7 | 6 dependency alerts migrated into `rules.yaml` schema |
| SR7-D6 | Abort-criteria breach = synthesized alert event; counted in `alert_outcomes` |
| SR8-D7 | 7 capacity alerts migrated into `rules.yaml` |
| S12 (WS) | Storm-mode batched digest delivered via existing on-call WS control channel |
| ADMIN_ACTION_POLICY §R4 | 3 new commands: `admin/alert-silence` Tier 2 · `admin/alert-threshold-update` Tier 2 · `admin/pager-rotation-swap` Tier 3 |
| I17 (capacity budget) | Every alert's `owner_service` MUST exist in `budgets.yaml` (service registration invariant extends transitively) |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| 2-week baseline per new alert delays SEV0 reachability | Prevents "shot-in-the-dark threshold" noise; staged promotion is the tuning process |
| FP rate 40% auto-downgrade is aggressive | Protects on-call from known-noisy alerts; re-promotion gate preserves rigor |
| `alert_outcomes` 90d retention is short | Cold aggregate preserves per-alert weekly roll-up indefinitely; raw rows storage-cost-bounded |
| 30-day max silence forces re-justification | Prevents slow-decay-into-noise anti-pattern |
| Storm-mode batching may delay pager by 2 min | Primary page already fired; batch is signal preservation, not detection delay |
| Weekly review cadence adds SRE load | Operationalizes existing SR2-D8 expectation; V1 solo pattern accommodates |
| Pager-load metrics require cohesive rotation tracking | Piggybacks SR2-D2 rotation data; no new system |

**What this resolves:**

- ✅ Inconsistent alert semantics — L1 severity × action-class matrix
- ✅ No tunable thresholds — L3 staged promotion process
- ✅ FP/FN blind spot — L4 `alert_outcomes` audit + missed-alert detection
- ✅ Silence-forever anti-pattern — L5 mandatory expiry + review
- ✅ Runbook linkage unenforced — L6 three CI lints extending SR3-D5
- ✅ Unmeasured pager load — L7 per-rotation metrics + rebalance triggers
- ✅ Weekly review operationalized — L8 template + action-item tracking
- ✅ Alert storm pager flood — L9 dedup + batched digest + SEV0-always-pages exception
- ✅ V1 launch with ad-hoc alerts — L10 rebaseline gate + lint
- ✅ Alert-to-runbook drift — L6 bidirectional CI enforcement

**V1 / V1+30d / V2+ split:**

- **V1:**
  - L1 severity × action-class taxonomy
  - L2 `contracts/alerts/rules.yaml` + CI lint
  - L3 staged promotion (0/1/2/3)
  - L4 `alert_outcomes` audit (90d hot + 2y cold aggregate)
  - L5 silence/snooze with 30-day cap
  - L6 alert-runbook CI lints (3)
  - L7 pager-load metrics (solo-dev baseline)
  - L8 weekly review artifact template
  - L9 storm protection
  - L10 V1 rebaseline gate — 19 migrated alerts, ≥2 weeks baseline data each
- **V1+30d:**
  - L3 auto-downgrade / auto-escalate active (needs 30 days of outcome data)
  - L4 cold-aggregate rollup active
  - L7 rotation rebalance triggers active (needs 30+ days of rotation data)
  - Alert-rule cost model (page-load budget per on-call)
- **V2+:**
  - ML-assisted threshold tuning (anomaly baseline)
  - Predictive alert (pre-breach fire)
  - Cross-alert correlation detection (reduces storm need)
  - Per-customer SLA alerting (post-monetization)

**Residuals (deferred):**
- ML anomaly-detection alerts — V2+
- Customer-facing SLA alerts — V2+ monetization dependency
- Multi-region alert correlation — V3+
- Alert cost-to-benefit model — V1+60d after pager-load data stabilizes

**Decisions locked (10):**
- **SR9-D1** 4-severity × 4-action-class taxonomy; severity ↔ action-class default matrix with `override_justification` escape hatch
- **SR9-D2** Alert rule schema-as-code at `contracts/alerts/rules.yaml` — required fields: alert_id · sli_ref · derivation_rule · threshold · duration · severity · action_class · runbook · owner_service · tier_scope · baselined_since · last_reviewed
- **SR9-D3** 4-stage promotion process (design / baseline / staged / promoted); 14-day baseline; noisy-alert auto-downgrade at 40% FP over 30 days; missed-alert escalation
- **SR9-D4** `alert_outcomes` audit table — 90d hot + 2y cold aggregate (aligns SR1-D8); 8-enum event_type; MetaWrite-enforced with narrow-column update allowlist
- **SR9-D5** Silence/snooze protocol — `admin/alert-silence` S5 Tier 2 with mandatory 50+ char reason + max 30-day duration + auto-expire; incident-tagged silences bypass 30-day cap but auto-clear on resolve; anti-pattern blocks (`*` pattern = Tier 1 equivalent; reason-less = lint reject; silence-after-fire = flagged in review)
- **SR9-D6** Alert-to-runbook CI contract — 3 lints (alert-runbook-sync / dead-ref / coverage-check); SEV0-2 mandatory runbook; WARN allows PLACEHOLDER 60 days; derivation-rule ↔ runbook bidirectional update enforced
- **SR9-D7** Pager rotation load metrics (extends SR2-D2) — pages_received / median_ack / incidents_declared / FP_rate / handoff_score weekly; 4 rebalance triggers (>10/week · >2× TTA · >30% FP · <3 handoff score for 2 weeks)
- **SR9-D8** Weekly alert review artifact at `docs/sre/alert-reviews/YYYY-WW.md` — template with top-10 volume / top-3 FP / silenced / recently-added / missed / rotation metrics / action items; feeds SR1 SLO review + SR3 runbook updates + SR6 matrix updates
- **SR9-D9** Alert storm protection — `lw_alert_storm_active` when page-now rate >10/5min; batched digest to WS channel every 2 min; storm-mode exceptions (new alert / different service / SEV0 always pages); storm audit via `alert_outcomes`
- **SR9-D10** V1 minimal bar — 19 SR1/SR6/SR7/SR8 alerts migrated + Stage-3 promoted + 2-weeks baseline data; `v1-alerts-rebaselined` CI gate; SR3 V1 runbook total reconciled to **33** (27 base + 5 chaos + 1 drain-shard)

**Features added (11):**
- **IF-42** Alert rule registry (`contracts/alerts/rules.yaml`)
- **IF-42a** `alert-rule-lint.sh` CI lint (required-field / dead-ref / severity↔action-class / replay-validation)
- **IF-42b** `alert_outcomes` audit table (90d hot + 2y cold aggregate)
- **IF-42c** `alert_silences` table + `admin/alert-silence` CLI
- **IF-42d** Pager-load metrics + rotation-rebalance dashboard (DF11)
- **IF-42e** Alert storm detection + batched digest delivery
- **IF-42f** Weekly alert-review template + generator script
- **IF-42g** Threshold tuning workflow (4-stage promotion + auto-downgrade/escalate)
- **IF-42h** Alert-to-runbook CI lint trio (extends SR3-D5)
- **IF-42i** False-positive / false-negative classifier (V1+30d with auto-downgrade trigger)
- **IF-42j** `admin/alert-threshold-update` + `admin/pager-rotation-swap` CLI commands

**No new invariant** — alert discipline is process, not architectural. I17 (SR8) remains the most recent invariant; next candidate would arise organically if a pattern emerges across SR10-SR12.

**Remaining SRE concerns (SR10–SR12) queued:** supply chain security · turn-based game reliability UX · observability cost + cardinality.
