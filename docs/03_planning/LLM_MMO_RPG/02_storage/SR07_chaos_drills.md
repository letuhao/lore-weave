<!-- CHUNK-META
chunk: SR07_chaos_drills.md
origin: direct-authored 2026-04-24
origin_branch: mmo-rpg/design-resume
note: Not produced by scripts/chunk_doc.py split; authored as new SR-series content extending SR1-SR6.
-->

## 12AJ. Chaos Drill Cadence — SR7 Resolution (2026-04-24)

**Origin:** SRE Review SR7 — SR1-SR6 defined **what** reliable operation looks like (SLOs, incident flow, runbooks, postmortems, deploy safety, dependency handling) but not **proof that those mechanisms actually work**. Circuit breakers that have never opened · runbooks that have never been executed · degraded modes that have never activated under load — all are theoretical until exercised. SR7 makes reliability mechanisms **falsifiable** through hypothesis-driven chaos experiments run on a regular cadence, with a V1 minimal bar that gates launch.

### 12AJ.1 Problems closed

1. Untested circuit breakers (SR6) — first open in prod is first validation
2. Unexecuted runbooks (SR3) — first real incident is first drill
3. Unknown SLO realism — SLIs (SR1) are declarations, not validated measurements
4. Undeclared failure-mode assumptions — "we think Redis failure degrades cleanly"
5. No recovery-time data — MTTR estimates without evidence
6. Drill ad-hoc-ness — no registry, no cadence, no audit trail
7. Game-day hesitancy — fear of production drilling with no safety rail
8. Team unfamiliarity with incident protocol (SR2)
9. Deploy safety (SR5) rollback path unexercised
10. Gone-state recovery (S10) never actually tested end-to-end

### 12AJ.2 Layer 1 — Chaos Experiment Registry

Single source of truth at `contracts/chaos/experiments.yaml`:

```yaml
- id: chaos-llm-anthropic-blackhole
  category: dep_failure                    # see §12AJ.4 categories
  hypothesis: |
    If all anthropic provider calls blackhole (100% timeout) for 5 minutes,
    the circuit breaker opens within 30s, roleplay-service enters `limited`
    mode with fallback to openai, and sli_turn_completion stays within 2× baseline.
  target:
    dep: llm-anthropic                     # references contracts/dependencies/matrix.yaml
    service: roleplay-service
  method: http_blackhole                   # canonical method vocabulary
  duration_ms: 300000                      # 5 min
  blast_radius:
    scope: cohort                          # global | cohort | reality | session | pod
    cohort_percent: 10                     # only in cohort scope
  abort_criteria:
    - sli: sli_turn_completion
      breach: burn_rate > 3
    - sli: sli_session_availability
      breach: burn_rate > 2
    - external: active_sev0_incident
      check: incidents.active_count > 0 AND severity='SEV0'
  runbook: docs/sre/runbooks/chaos/llm-anthropic-blackhole.md
  cadence: monthly                         # see §12AJ.5
  environments: [staging, prod]
  v1_required: true                        # part of V1 minimal bar
```

**Mandatory fields:** id · category · hypothesis (must state falsifiable prediction) · target · method · duration · blast_radius · abort_criteria · runbook · cadence · environments. Missing any = CI lint fails (`chaos-registry-lint.sh`).

**Governance:** adding an experiment requires:
- Runbook in `docs/sre/runbooks/chaos/` exists (SR3 pattern)
- SR6 matrix entry exists for the target dep (if dep_failure category)
- SLI impact estimate (what breach means for users)
- Rollback verification ("when the experiment ends, how do we know the system recovered?")

New experiments require architect sign-off (same workflow as new invariant / new dependency).

### 12AJ.3 Layer 2 — Hypothesis-Driven Format

Every experiment states a falsifiable prediction in the form:

> **Given** the system is in [initial state]
> **When** we inject [failure mode] for [duration]
> **Then** [metric] stays within [bounds] AND [recovery property] holds within [time]

Examples:

| Hypothesis | Passes if | Fails if |
|---|---|---|
| LLM-anthropic blackhole 5min | breaker opens <30s · failover activates · sli_turn_completion burn <2× | users see >5% failed turns · failover doesn't route · breaker doesn't close post-recovery |
| Per-reality DB outage 2min | affected reality enters `read_only` mode · other realities unaffected · writes rejected cleanly | cross-reality SLI degrades · writes succeed silently · mode doesn't clear |
| Deploy rollback mid-canary stage 2 | canary auto-aborts · cohort reverts to prior version · zero user-visible errors | aborted cohort hangs mid-state · errors leak to downstream stages |

**Pass/fail recorded in `chaos_drills` audit table (§12AJ.9).** A failed hypothesis doesn't mean "experiment failed" — it means "mechanism needs fixing"; that's the point. Pass/fail is treated as data, not blame.

### 12AJ.4 Layer 3 — Experiment Categories (7)

| Category | Validates | Example experiments |
|---|---|---|
| **dep_failure** | SR6 circuit breakers · degraded modes · multi-provider failover | LLM blackhole · Redis down · meta DB slow · MinIO 500s |
| **network** | SR6 timeouts · bulkheads | latency injection 2s · packet loss 10% · DNS lookup fail |
| **state_corruption** | R9 lifecycle invariants · C5 CAS · projection rebuild (R2) | simulate projection desync · orphan event · lifecycle jump attempt |
| **load** | R7 session concurrency · SR1 SLIs · S7 queue | surge 10× traffic · hot session (100 turns/min) · queue-flood |
| **security** | S9 injection defense · S11 SVID auth · S12 WS security | prompt injection strings · rogue SVID attempt · WS fingerprint mismatch |
| **deploy** | SR5 canary · rollback · freeze · drain (SR6-D10) | abort mid-stage-2 · rollback during migration · force drain-timeout |
| **recovery** | R9 safe closure · C1 severance · S10 gone-state · R4 backup restore | restore-from-backup drill · relink-ancestor (V2+) · user-erasure full cycle |

Categories are not orthogonal — an LLM blackhole is both `dep_failure` and implicitly tests `network` timeouts. Category is the **primary lens**, not an exclusive classification.

### 12AJ.5 Layer 4 — Cadence Tiers

| Tier | Frequency | Scope | Example |
|---|---|---|---|
| **always-on** | continuous (low blast) | staging only (V1); dev + staging (V2+) | random 1-pod kill every 4h in staging |
| **weekly** | 1× / week | staging primary; select prod-safe | single-dep failover drill rotated through matrix |
| **monthly** | 1× / month | staging + prod cohort | cross-service dep-failure drill with degraded-mode activation |
| **quarterly game-day** | 1× / quarter | prod coordinated | full-incident simulation: SEV1 declared, IC runs SR2 protocol end-to-end |
| **yearly** | 1× / year | prod + regulatory | disaster-recovery: restore-from-backup, full fleet failover (V2+); regulator tabletop |

**V1 reality check** (solo-dev): cadence scales with team size. V1 solo = weekly (single staged drill) + monthly (small prod drill) + quarterly (self-run tabletop). Always-on automated chaos defers to V1+30d.

**Cadence scheduler:** `chaos-scheduler` runs as a cron (initially via `admin-cli`, V2+ dedicated job). Picks next experiment from registry respecting cadence + `last_run_at` + rotation policy (don't run the same experiment twice in a row).

### 12AJ.6 Layer 5 — Environment Scoping

| Env | Chaos policy | Approval |
|---|---|---|
| **dev** | Free-for-all; developers encouraged to break things locally | none |
| **staging** | First run of any new experiment; chaos is expected; SLOs slightly relaxed | single engineer |
| **prod — always-on** | Curated low-blast list only; pre-approved in registry | none (registry is the approval) |
| **prod — cohort (≤10%)** | Weekly/monthly experiments; SLI-gated abort | 2 engineers (primary + observer) |
| **prod — full-fleet or recovery** | Quarterly game-days; advance notice | tech lead + SRE on-call + founder FYI |

**"New experiment" gate:** a new experiment MUST run in staging for 2 cycles before first prod run. Shortcut only for security / incident-response drills (approved ad-hoc by security on-call).

**Blast radius reference** (from §12AJ.2 `blast_radius.scope`):
- `pod` — single process instance
- `session` — one user session (R7 concurrency boundary)
- `reality` — one reality's DB + fleet of sessions
- `cohort` — reality-registry.deploy_cohort percentage (reuses SR5 mechanism)
- `global` — platform-wide (reserved for recovery drills + yearly game-days)

### 12AJ.7 Layer 6 — Safety Mechanisms

Belt-and-suspenders to prevent a drill becoming an incident:

1. **Per-experiment abort criteria** declared in registry (§12AJ.2 `abort_criteria`). Checker polls every 10s; breach = immediate auto-abort + audit entry.
2. **Max-blast-radius enforcement** — harness refuses to exceed declared `blast_radius.cohort_percent`; violates = hard error in CI + blocked at runtime.
3. **No-chaos-during-incident** — any active SEV0/SEV1 incident (from `incidents` table per SR2-D7) blocks new experiments. Running experiments auto-abort when incident declared.
4. **No-chaos-during-deploy** — any active major deploy (SR5-D1 class) blocks new prod experiments; running experiments auto-abort when deploy starts.
5. **Global kill switch** — `chaos/kill-switch` command (S5 Tier 1 Destructive — user-visible impact; dual-actor + 100+ char reason) aborts ALL active experiments across envs. Post-incident the kill switch stays on until tech-lead re-enables.
6. **Dry-run flag** — `chaos-cli run --dry-run` executes everything EXCEPT the actual failure injection; validates abort-criteria wiring + audit path without user impact. Required first run in any env.
7. **Maintenance-mode coupling** — if `status-page-admin` has announced maintenance, prod chaos is allowed ONLY for experiments explicitly tagged `maintenance_safe: true`.

### 12AJ.8 Layer 7 — Execution Tooling

Canonical `chaos-cli` at `services/admin-cli/commands/chaos/`:

```
chaos-cli list                              # list registered experiments
chaos-cli describe <exp-id>                 # show registry entry + last runs
chaos-cli run <exp-id> --env=staging --dry-run   # validate wiring
chaos-cli run <exp-id> --env=staging              # actual run
chaos-cli run <exp-id> --env=prod --approver=<svid>  # prod requires co-approver
chaos-cli abort <drill-id>                  # stop a running drill
chaos-cli kill-switch --reason="..."        # stop ALL + disable harness
chaos-cli status                            # show active drills + recent history
```

**Command classification (S5 integration):**
- `chaos/start` — S5 **Tier 2 Griefing** (user-visible impact; reason + notification required)
- `chaos/abort` — S5 **Tier 3 Informational** (recovery action, no additional risk)
- `chaos/kill-switch` — S5 **Tier 1 Destructive** (platform-wide halt of safety-testing; dual-actor + 100+ char reason + 24h cooldown on re-enable)

**Harness requirements** (architecture; detailed impl deferred to SR7 implementation commit):
- Stateless: drill request arrives, harness injects failure + schedules auto-clear
- Per-method adapter: `http_blackhole` (HTTP proxy intercept), `db_slow_query` (pg statement-timeout manipulation), `pod_kill` (Kubernetes delete), `network_latency` (tc netem), etc.
- Audit write before injection, audit update on completion/abort
- No persistent state outside `chaos_drills` table

**SR6 integration:** execution goes through `contracts/resilience/` timeouts + circuit breakers like any other call — chaos drills are first-class dependency-class citizens, not a backdoor.

### 12AJ.9 Layer 8 — `chaos_drills` Audit Table

```sql
CREATE TABLE chaos_drills (
  drill_id              UUID PRIMARY KEY,
  experiment_id         TEXT NOT NULL,            -- from registry yaml
  category              TEXT NOT NULL,            -- redundant-but-denormalized
  environment           TEXT NOT NULL,            -- 'dev' | 'staging' | 'prod'
  blast_radius          JSONB NOT NULL,           -- {scope, cohort_percent, affected_realities, affected_sessions}
  hypothesis            TEXT NOT NULL,            -- snapshot at run time (registry may change later)
  initiated_at          TIMESTAMPTZ NOT NULL,
  completed_at          TIMESTAMPTZ,
  outcome               TEXT NOT NULL,            -- 'running' | 'passed' | 'failed' | 'aborted_safety'
                                                  -- | 'aborted_manual' | 'aborted_incident'
  observed_metrics      JSONB,                    -- SLI snapshots: pre / during / post
  recovery_time_ms      BIGINT,                   -- from clear to all-SLIs-normal
  initiated_by          UUID NOT NULL,            -- user_ref_id
  approved_by           UUID[],                   -- co-approver (prod)
  aborted_by            UUID,                     -- NULL if not aborted
  related_incident_id   UUID,                     -- if drill became / correlated with real incident
  related_postmortem_id UUID,                     -- if drill triggered postmortem
  runbook_update_refs   TEXT[],                   -- SR3 runbook PRs created from findings
  notes                 TEXT                      -- free-form post-drill observations (max 2000 chars; scrubbed per §12X.4)
);

CREATE INDEX ON chaos_drills (experiment_id, initiated_at DESC);
CREATE INDEX ON chaos_drills (outcome, initiated_at DESC);
CREATE INDEX ON chaos_drills (environment, initiated_at DESC);
CREATE INDEX ON chaos_drills (initiated_at DESC) WHERE outcome = 'running';
```

**Retention:** **3 years** (between dependency_events 1y and audit-tier 5y — drills are important history but drop off in utility after implementation matures).
**PII classification:** `low` (notes field scrubbed; actor user_ref_id opaque per S8-D1).
**Write path:** `MetaWrite()` (I8); append-only; REVOKE UPDATE/DELETE except for `completed_at` + `outcome` + `observed_metrics` + `recovery_time_ms` + `aborted_by` + `notes` (drill completion update; narrow allowed-column set encoded in MetaWrite validator).

**Correlation:**
- `related_incident_id` populated when drill became real (safety breach + auto-abort doesn't always clear upstream impact cleanly)
- `related_postmortem_id` populated when drill findings trigger SR4 postmortem (a new bug class discovered)
- `runbook_update_refs` populated post-drill review — points at SR3 runbook PRs containing improvements

### 12AJ.10 Layer 9 — Post-Drill Review

Every drill → review within 48 hours. Review template at `docs/sre/chaos-review-templates/`:

- **Hypothesis outcome** — passed / failed / inconclusive
- **Observed vs predicted** — SLI trajectories (graphs attached)
- **Surprises** — anything unexpected (positive or negative)
- **Action items** — runbook updates · matrix updates · new experiments · bug fixes
- **Followup drill** — does this need to run again with a variant hypothesis?

**Feeds into:**

| Drill outcome | SR3 action | SR4 action | SR6 action |
|---|---|---|---|
| Hypothesis passed, no surprises | Mark runbook `last_verified` via chaos_drill method (SR3-D4) | — | — |
| Hypothesis failed, mechanism bug | **Open SR3 runbook PR** to capture new failure mode | If user-impact > 0, declare post-incident SEV2 + postmortem (SR4-D1) | Update matrix.yaml if timeout/threshold wrong |
| Aborted-safety | Investigate why abort criteria fired early | Postmortem if abort itself caused user-visible impact | Re-tune abort criteria for experiment |
| Surprise discovered (unrelated to hypothesis) | New runbook for newly-discovered issue | Postmortem if ongoing production problem | Dep matrix update if new dep behavior uncovered |

**V1+30d evolution:** automated "drill → runbook PR" workflow — failed drills auto-open a PR against the target runbook with the observed symptoms/mitigations filled in from telemetry.

### 12AJ.11 Layer 10 — V1 Minimal Bar

**Before V1 launches, these 5 drills MUST have passed at least once in staging + once in prod cohort:**

| # | Drill | Validates | V1 owner |
|---|---|---|---|
| 1 | `chaos-llm-primary-blackhole` | SR6-D6 multi-provider failover + SR6-D5 degraded mode | roleplay-service |
| 2 | `chaos-redis-down` | SR6-D3 circuit breaker + R6-L6 Redis-as-cache invariant + SR6-D5 `limited` mode for WS delivery | publisher + api-gateway-bff |
| 3 | `chaos-reality-db-outage` | R9 `read_only` transition + SR6-D5 reality-scoped mode + cross-reality isolation (I7) | world-service |
| 4 | `chaos-deploy-rollback-mid-canary` | SR5-D3 canary auto-abort + SR5-D7 rollback decision framework | migration-orchestrator |
| 5 | `chaos-graceful-drain-timeout` | SR6-D10 `Drain()` behavior at timeout boundary; outbox recovery on next replica | any service (rotate) |

Each drill has a canonical runbook (SR3-D3 27-runbook V1 gate extends by 5 to **32 runbooks**). CI gate `v1-launch-check.sh` queries `chaos_drills` for a passing row per V1-required experiment in each required environment; block launch if any missing.

**V1+30d adds drills 6-12** covering recovery (backup restore), security (injection attempt), load (surge), and state-corruption (projection desync). V2+ adds cross-reality propagation drill (xreality.* topics), severance-recovery drill (C1-OW), and IP-erasure full-cycle drill (S8 crypto-shred).

### 12AJ.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| SR1-D2 | SLI thresholds = experiment abort criteria pass/fail boundary |
| SR1-D3 | Error-budget burn rate monitored during drills; auto-abort on 3× threshold |
| SR2-D1 | Drill outcomes `aborted_incident` link to incident severity matrix |
| SR2-D8 | Failed-drill trigger postmortem per SR4-D1 rules |
| SR3-D3 | V1 27-runbook gate extended to 32 (adds 5 chaos runbooks) |
| SR3-D4 | `last_verified` method `chaos_drill` added to verification methods |
| SR3-D9 | Drill findings feed runbook updates via standardized PR flow |
| SR4-D1 | Failed-drill + user-impact → postmortem mandatory; root-cause `monitoring_gap` / `runbook_gap` common |
| SR5-D2 | Active major-deploy blocks prod chaos (mutual exclusion) |
| SR5-D3 | `chaos-deploy-rollback-mid-canary` drill validates canary abort path |
| SR6-D1 | Chaos registry references dependency matrix for `dep_failure` category |
| SR6-D3 | Breaker state transitions during drill counted + audited via `dependency_events` |
| SR6-D5 | Degraded-mode activation is a primary drill success criterion |
| SR6-D10 | Drain drill validates SIGTERM handler + WS close 4011 path |
| S11-D5 | `chaos/kill-switch` = Tier 1 (same discipline as other destructive platform-level commands) |
| S12 | WS close 4013 "drill_in_progress" added to enumerated set (informational; mirror of 4012) |
| ADMIN_ACTION_POLICY §R4 | 3 new commands: `chaos/start` Tier 2 · `chaos/abort` Tier 3 · `chaos/kill-switch` Tier 1 |
| IF-39g | "Chaos drill hooks" V1+30d placeholder in SR6 is **activated** by this resolution; upgraded to V1 as part of minimal-bar drills |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| V1 launch gated by 5 drills | Each validates a different reliability mechanism; skipping any = shipping unvalidated mechanism |
| Chaos registry is yet-another-YAML | Aligns with dependencies / runbooks / flags registries — same discipline |
| Hypothesis-driven format = more writing | Forces mechanism articulation; dead-weight experiments rejected at PR |
| Safety mechanisms = conservative cadence | Prevents drill-caused incident; V1+30d relaxes once evidence accumulates |
| `chaos_drills` 3y retention adds storage | ~few MB/year; negligible vs value |
| V1 solo-dev cadence is weekly/monthly only | Realistic; always-on automated chaos deferred; solo timer commits to it |

**What this resolves:**

- ✅ Untested circuit breakers — L11 V1-bar drill 1 + 2 exercises SR6 breakers in prod cohort
- ✅ Unexecuted runbooks — L9 post-drill review updates SR3-D4 `last_verified` field
- ✅ Unknown SLO realism — L3 hypothesis format makes SLI breach the pass/fail signal
- ✅ Undeclared failure assumptions — L2 hypothesis "we believe X" makes assumptions explicit + falsifiable
- ✅ No recovery-time data — L9 `recovery_time_ms` captured every drill
- ✅ Ad-hoc drilling — L1 registry + L4 cadence + L6 safety enforces discipline
- ✅ Game-day hesitancy — L5 staging-first + L7 dry-run + L8 kill-switch give safety rails
- ✅ Team unfamiliarity with SR2 — L11 quarterly game-day runs full SEV1 protocol
- ✅ Deploy rollback unexercised — L11 V1-bar drill 4
- ✅ Recovery paths unvalidated — L11 V1-bar drill 3 + 5; broader set V1+30d

**V1 / V1+30d / V2+ split:**

- **V1:**
  - L1 experiment registry + CI lint
  - L2 hypothesis format + required fields
  - L3 7 categories with examples
  - L4 cadence tiers (V1 solo: weekly staging · monthly prod cohort · quarterly self-tabletop)
  - L5 environment scoping + new-experiment gate (2 staging cycles before prod)
  - L6 safety mechanisms (abort criteria · blast-radius · no-chaos-during-incident · kill switch · dry-run)
  - L7 `chaos-cli` with 5 V1-required experiments
  - L8 `chaos_drills` audit table (3y retention)
  - L9 post-drill review template + feeding SR3/SR4/SR6
  - L10 5-drill V1 launch gate
- **V1+30d:**
  - Always-on automated chaos in staging (random pod kills, network flaps)
  - Drills 6-12: recovery (backup restore) · security (injection) · load (surge) · state (projection desync)
  - Automated drill-failure → runbook PR workflow
- **V2+:**
  - Full-fleet yearly recovery exercise
  - ML-assisted hypothesis generation from incident history
  - Cross-reality drills (xreality.* topics)
  - Chaos-as-a-service for external tenant environments (platform mode)
  - Regulator tabletop drills (GDPR Art. 33 72h simulation)

**Residuals (deferred):**
- Continuous production chaos (always-on) — V1+30d once baseline confidence established
- Chaos mesh / third-party chaos-platform integration — evaluate V2+ vs in-house cost
- Canary-chaos coupling (chaos injected during canary stages) — V2+; high blast-radius concern
- Multi-region chaos → V3+

**Decisions locked (10):**
- **SR7-D1** Chaos experiment registry at `contracts/chaos/experiments.yaml` + required-field CI lint + architect sign-off for new experiments
- **SR7-D2** Hypothesis-driven format — Given/When/Then falsifiable prediction; pass/fail is data not blame
- **SR7-D3** 7 experiment categories (dep_failure / network / state_corruption / load / security / deploy / recovery)
- **SR7-D4** 5 cadence tiers (always-on / weekly / monthly / quarterly game-day / yearly); V1 solo-dev pattern weekly-staging + monthly-prod-cohort
- **SR7-D5** Environment scoping + new-experiment gate (2 staging cycles before first prod run); approval matrix (prod cohort = 2 engineers, prod full-fleet = tech lead + SRE on-call)
- **SR7-D6** 7 safety mechanisms (per-exp abort criteria · max blast radius · no-chaos-during-incident · no-chaos-during-deploy · global kill-switch · dry-run flag · maintenance-mode coupling)
- **SR7-D7** `chaos-cli` tooling in `services/admin-cli/commands/chaos/`; 3 admin commands with S5 classification (start=Tier 2 · abort=Tier 3 · kill-switch=Tier 1)
- **SR7-D8** `chaos_drills` audit table (3y retention; PII=low; MetaWrite-enforced append-only; narrow-column update allowlist)
- **SR7-D9** Post-drill review within 48h; template-driven; drill outcomes feed SR3 runbook updates + SR4 postmortems + SR6 matrix updates via deterministic mapping table
- **SR7-D10** 5-drill V1 launch gate (LLM failover · Redis outage · per-reality DB outage · deploy rollback · graceful drain); CI-enforced via `v1-launch-check.sh`

**Features added (11):**
- **IF-40** Chaos experiment registry (`contracts/chaos/experiments.yaml`)
- **IF-40a** `chaos-cli` admin tool (5 subcommands)
- **IF-40b** `chaos_drills` audit table (3y retention)
- **IF-40c** Chaos harness framework (method adapters: http_blackhole / db_slow_query / pod_kill / network_latency / ...)
- **IF-40d** Per-experiment abort-criteria checker (10s polling; SLI-gated auto-abort)
- **IF-40e** Global chaos kill-switch (S5 Tier 1)
- **IF-40f** Dry-run mode for new experiments
- **IF-40g** Post-drill review template + automated metric snapshot
- **IF-40h** V1 launch gate CI check (`v1-launch-check.sh`)
- **IF-40i** SR3 runbook `last_verified` method = `chaos_drill` (extends SR3-D4)
- **IF-40j** Chaos-scheduler cron (V1 via admin-cli; V2+ dedicated service)

**IF-39g activation:** SR6's forward-reference "chaos drill hooks (V1+30d placeholder)" is now activated — upgraded to V1 via this resolution; SR7's 5-drill minimal bar constitutes the V1 activation.

**Remaining SRE concerns (SR8–SR12) queued:** capacity planning + auto-scaling · alert tuning + pager discipline · supply chain security · turn-based game reliability UX · observability cost + cardinality.
