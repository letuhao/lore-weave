<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: SR01_slos_error_budget.md
byte_range: 382318-395002
sha256: f4c34c98c88c7446d08f734f053e7d760b3cdc2a9fe628ab0bce6f57d38577e2
generated_by: scripts/chunk_doc.py
-->

## 12AD. SLOs + Error Budget Policy — SR1 Resolution (2026-04-24)

**Origin:** SRE Review SR1 — §12A–§12AC accumulated ~50+ metrics and alerts, but no formal reliability targets, no error budget policy, no user-journey SLIs. Raw thresholds scattered ("PAGE if X > 30s") have no derivation anchor. Without SLOs, reliability is implicit; without budgets, there's no mechanism to trade feature velocity for reliability when needed.

### 12AD.1 Why SLOs here

Reliability without targets = hope. Targets without budgets = unenforceable. Budgets without burn-rate rules = aspirational.

Problems this closes:
1. Many alert thresholds are magic numbers with no derivation rule
2. No formal agreement on what the platform promises to users
3. No mechanism to say "we pause features, fix reliability first"
4. Raw latency metrics ≠ what players experience end-to-end
5. Tier differentiation (free/paid/premium) unreflected in reliability commitments
6. Multi-reality isolation (noisy neighbor) has no formal protection target
7. External SLA posture undefined (becomes V2+ monetization blocker)

### 12AD.2 Layer 1 — User-Journey SLIs

SLIs measure what users experience, not system internals. Seven core SLIs:

| SLI | Definition | Source |
|---|---|---|
| `sli_session_availability` | Fraction of session-start attempts succeeding within 5s | `successful_session_starts / total_session_start_attempts` (5-min windows) |
| `sli_turn_completion` | Fraction of submitted turns producing LLM response within budget (60s paid / 120s premium) | `turns_completed_within_budget / turns_submitted` |
| `sli_event_delivery` | Fraction of events delivered via WS within 2s of emission | `ws_events_delivered_within_2s / ws_events_emitted` |
| `sli_realtime_freshness` | P99 staleness of projection reads | histogram `read_ts - last_applied_event_ts` |
| `sli_auth_success` | Fraction of auth ops (login, refresh, WS ticket) < 500ms successfully | `auth_success_within_500ms / auth_attempts` |
| `sli_admin_action_success` | Fraction of admin commands succeeding within 30s | `admin_command_success_within_30s / admin_command_attempts` |
| `sli_cross_reality_propagation` | Fraction of cross-reality fan-outs reaching descendants within 60s (S8 erasure, §12AC canon, §12M ancestry) | `fanouts_within_60s / fanouts_initiated` |

Metric naming: existing `lw_*` pattern with `_sli` suffix when SLI-level (vs raw counters). Each SLI sourced from canonical metric emitters already defined in prior sections (§12F, §12Y.9, §12AA.10, §12AB.11, etc.).

### 12AD.3 Layer 2 — SLO Targets (per tier)

Initial targets (revise post-V1 with real data; L8 governance):

| SLI | Free/BYOK | Paid | Premium | Window |
|---|---|---|---|---|
| Session availability | 99.0% | 99.5% | 99.9% | 30-day rolling |
| Turn completion | 95.0% | 99.0% | 99.0% | 30-day rolling |
| Event delivery | 99.0% | 99.5% | 99.9% | 30-day rolling |
| Realtime freshness (P99 < 3s) | 99.0% | 99.5% | 99.9% | 30-day rolling |
| Auth success | 99.9% | 99.9% | 99.9% | 7-day rolling |
| Admin action success | 99.5% | — | — | 30-day rolling (platform) |
| Cross-reality propagation | 99.0% | — | — | 30-day rolling (platform) |

Tier rationale:
- **Free/BYOK**: lower SLO acceptable — self-service, user owns provider keys
- **Paid**: "good enough for serious play" — reasonable expectation for monthly subscription
- **Premium**: "best we can offer" — paired with premium-model access (§12V.L7)
- **Admin + cross-reality**: platform-level, no per-user tier distinction
- **Auth always strict**: foundational; users expect always-on login

Turn-completion at 95% for free accepts BYOK provider variance (user's own rate limits, outages).

### 12AD.4 Layer 3 — Error Budget Policy

Error budget = `(1 - SLO_target) × events_in_window`.

Example: Paid turn completion 99% over 30d means 1% of turns may exceed 60s budget. If turn volume is 10M/month, budget = 100K "slow turn events".

**Budget burn rate** = (budget spent so far) / (fraction of window elapsed).

4-tier response policy:

| 7-day burn rate | Response |
|---|---|
| < 50% | Normal operation; feature work continues |
| 50–75% | Feature PRs marked `reliability-review-required`; a11y + perf tests mandatory |
| 75–90% | Feature work paused; reliability fixes prioritized; weekly review discussion |
| ≥ 90% | **Feature freeze**; SRE + tech lead jointly unfreeze after root-cause fix |
| Budget exhausted | SLO breach; postmortem + public status page update (V2+); paid-user credits (V2+ SLA) |

Enforcement:
- Dashboard: burn-rate-per-SLI (week-over-week)
- CI check: if any SLI burn ≥ 75%, feature PRs require `approve-reliability-override` label + tech-lead approval (GitHub CODEOWNERS)
- Governance: weekly engineering review reads SLO dashboard; freeze/unfreeze decisions logged in `docs/sre/slo-reviews/`

Budget resets at measurement window end; partial freezes auto-end when burn drops below threshold for 24h (no permanent lockout).

### 12AD.5 Layer 4 — Multi-Tenant Isolation SLO

Per-reality noisy-neighbor protection — reality A's failure must not degrade reality B:

| SLI | Target |
|---|---|
| Cross-reality SLI correlation | When reality A has SLI breach, reality B's same SLI stays within ±10% of baseline |
| Meta registry availability | **99.99%** over 30d (shared dependency; stricter target) |
| Per-reality resource quota | No single reality > 10% of shared resource (Postgres conn pool, Redis memory, LLM budget outside premium) |

Enforcement levers (already exist in prior sections; SR1 formalizes as isolation SLO):
- §12D.4 pgbouncer per-reality conn limits
- §12F.6 Redis stream MAXLEN per-reality message volume
- §12V.3 per-session cost cap → per-reality LLM spend
- §12W per-user queue cap → cross-reality queue abuse prevention

Noisy-neighbor detection:
- Per-reality resource usage metrics with `{reality_id}` label (bounded cardinality per §12AD.L8 cost controls)
- 3σ anomaly detection → SRE investigate (not auto-PAGE; could be legitimate popular reality)
- Pattern: if reality A exceeds 10% resource quota AND B's SLI degrades → correlated investigation

### 12AD.6 Layer 5 — Reliability Review Cadence

| Cadence | Artifact | Outcome |
|---|---|---|
| Daily | SLO dashboard check (on-call 5-min review) | Triage spikes; call out anomalies |
| Weekly | Engineering review: SLO dashboard + burn rates + runbook updates | Freeze/unfreeze decisions; feature-vs-reliability prioritization |
| Monthly | Per-SLI deep dive (rotating: 1 SLI per month) | Baseline refresh; threshold tuning; runbook improvements |
| Quarterly | Full SLO review — targets still right? User expectations matched? | Adjust targets with documented rationale |
| Annual | External SLA review (post-monetization) | Update customer-facing SLA |

All reviews logged in `docs/sre/slo-reviews/<yyyy-mm-dd>_<slo-or-general>.md`. Append-only history; target-change rationale preserved.

### 12AD.7 Layer 6 — Alert Threshold Derivation from SLO

Every alert MUST derive from an SLO. Raw magic numbers = CI fail.

Alert definition schema:
```yaml
# alerts/ws_refresh_failures.yaml
alert: lw_ws_refresh_failures_high
expr: rate(lw_ws_refresh_failures_total[5m]) > <derived_threshold>
severity: page
sli_ref: sli_auth_success
derivation_rule: "threshold = 2× SLO error budget allowed rate over 5 min"
runbook: runbooks/ws/refresh-failures.md
owner: sre-team
```

CI lint (`scripts/slo-alert-lint.sh`) checks every alert file:
- `sli_ref` must reference a declared SLI
- `derivation_rule` must be present
- `runbook` must point to existing file
- Severity must match SLI tier (high-priority SLI → page; low → warn)

Threshold changes require SLO review approval in same PR (governance lives with review, not code review).

### 12AD.8 Layer 7 — Public Status Page

Post-monetization surface at `status.loreweave.dev`:

Content:
- Per-SLI current state (traffic-light: green/amber/red per tier)
- Active incidents (auto-updated from SR2 incident mgmt integration)
- Scheduled maintenance windows (SR5 change-mgmt integration)
- SLO history (rolling 90d time-series)

Update flow:
- **Automated**: SLI breach > 5 min → auto-publish "degraded" banner
- **Manual**: operator authors maintenance notice via status-page-admin CLI (S5 Tier 2 Griefing — user-visible impact)
- **Post-incident**: within 14d, postmortem link published

V1: internal-only (feature flag gates public visibility).
V2+: public page aligned with monetization launch + external SLA commitments.

### 12AD.9 Layer 8 — Observability Cost Controls (SLO side)

SLO monitoring itself has cost; can't be cardinality-unlimited. Pre-requisite for SR12, budgeted here:

Label cardinality caps:
- `user_ref_id` label ONLY on rare user-facing SLI violation counters (not on every request metric)
- `reality_id` label on per-reality SLIs with aggregation at >1K realities (top-K + `_other` bucket)
- `session_id` label forbidden on long-retention metrics (cardinality explodes)
- Default high-cardinality labels use `exemplars` (Prometheus exemplar pattern) rather than labels

Retention tiers:
- Raw metrics: 15 days
- 5-min aggregates (for 30-day SLO windows): 90 days
- 1-hour aggregates (for quarterly review): 2 years
- SLO review artifacts in `docs/sre/`: forever (git)

Storage target: < 500 GB metrics/day at V3 platform scale.

### 12AD.10 Interactions + V1 split + what this resolves

**Interactions**:

| With | Interaction |
|---|---|
| §12A–§12AC | Each section's metrics get `sli_ref` annotations retrofit V1+30d; threshold derivation enforced |
| §12V (S6) cost controls | Per-session cost cap = per-reality resource quota enforcement (L4) |
| §12AA (S11) | `service_to_service_audit` timestamps source admin-action-success SLI |
| §12AB (S12) | WS metrics source event-delivery + auth SLIs |
| §12Y (S9) | `prompt_audit` timestamps source turn-completion SLI |
| §12L (R13) / ADMIN_ACTION_POLICY | Status page updates = admin cmd, Tier 2 Griefing |
| DF9 / DF11 | SLO dashboard is DF11 subsurface; per-reality SLI panel in DF9 |
| SR2 (incident classification) | Error budget burn ≥ 90% = auto-incident declared |
| SR5 (deploy safety) | Burn-rate CI check gates feature PRs |
| SR9 (alert tuning) | Alert derivation contract established here; SR9 fills runbook side |

**Accepted trade-offs**:

| Cost | Justification |
|---|---|
| Initial targets are guesses, not grounded in V1 data | Explicit "starting point" framing + quarterly review mitigates; better than no targets |
| Tiered SLO differentiation adds dashboard complexity | Matches monetization differentiation; free users still get reasonable baseline |
| Error budget policy adds feature-velocity friction | That's the point; reliability loses by default when un-traded |
| Label cardinality caps limit some drill-down | Storage cost bounded; alternative (per-user metrics) bankrupts observability |
| CI check on PRs under high burn rate slows merges | Intended: "fix reliability, then ship" |

**What this resolves**:

- ✅ **No formal reliability targets** — L2 SLO table
- ✅ **Alert magic numbers** — L6 derivation rule + CI lint
- ✅ **Feature-vs-reliability tradeoff undefined** — L3 error budget policy
- ✅ **Raw metrics ≠ user experience** — L1 user-journey SLIs
- ✅ **Tier differentiation** — L2 per-tier targets
- ✅ **Noisy neighbor** — L4 multi-tenant isolation SLO
- ✅ **No review cadence** — L5 daily/weekly/monthly/quarterly/annual
- ✅ **External SLA unclear** — L7 V2+ public page post-monetization

**V1 / V1+30d / V2+ split**:
- **V1**: L1 SLIs in metrics pipeline; L2 initial targets documented (dashboard only, not enforced); L3 error budget policy documented + dashboard; L4 isolation monitoring wired; L6 derivation rule enforced on NEW alerts (not backfill yet); L8 cardinality caps in CI
- **V1+30d**: L3 burn-rate CI check gating feature PRs; L5 weekly review cadence operational; L6 derivation_rule backfilled on all existing alerts; L7 internal-only status page
- **V2+**: L7 public status page at monetization launch; L5 annual SLA review; advanced SLIs (client-side RUM, synthetic monitoring)

**Residuals (deferred)**:
- V2+ RUM (client-side real user monitoring) for perceived latency SLIs
- V2+ synthetic monitoring (continuously-simulated user journeys via scripted bots)
- V3+ multi-region SLO (cross-region RTT budgets)
- Post-monetization customer SLA credit process

