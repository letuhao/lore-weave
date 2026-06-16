# L7 — Operations + Logging + Monitoring Substrate

> **Parent:** [_index.md](_index.md)
> **Depth target:** B (artifact-level)
> **Status:** DRAFT — first-pass enumeration
> **Added:** 2026-05-29 (gap discovered during CLARIFY review)

---

## §1. Why L7 exists

L1-L6 ship the application substrate but **lack operational substrate**. Without L7, the platform cannot be run in production:

- No structured logging library → debug logs leak PII (violates S08)
- No tracing → cross-service incident diagnosis is guesswork
- No SLO infrastructure → SR1 burn-rate freeze is aspirational
- No runbook library → 3am ops fails (SR3 problem statement)
- No admin-cli library → R13 "no SSH into DB" rule unenforceable
- No on-call rotation → SR2 alerts route to nowhere
- No incident infrastructure → GDPR Art.33 72h breach notification has no flow
- No deploy pipeline → SR5 canary gates have no executor

These are **cross-cutting infrastructure** that touches every L1-L6 service. Bolting on later = major refactor across 20+ services.

---

## §2. Sub-components

### L7.A — Admin CLI library + command catalog

**Owning chunks:** R13 §12L.1 (admin command library), S11-D10 (break-glass), S5 (impact classification), §12T.6 (sensitive read paths)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.A.1 | `services/admin-cli/` Go service | Code | Canonical admin tool (NOT a daemon — CLI binary) |
| L7.A.2 | `services/admin-cli/internal/framework/` | Code | Command framework: named, versioned, dry-run-first, audit-classified |
| L7.A.3 | `services/admin-cli/internal/auth/` | Code | Reads admin JWT (issued by auth-service), validates scope |
| L7.A.4 | `services/admin-cli/internal/break_glass/` | Code | `POST /admin/break-glass` flow (S11-D10): Tier 1 dual-actor + 100+ char reason + incident ticket ref → 24h TTL JWT with `break_glass=true` claim |
| L7.A.5 | `services/admin-cli/commands/` directory | Code | ~30+ canonical commands organized by domain: `reality/`, `pc/`, `npc/`, `migration/`, `audit/`, `erasure/`, `canon/`, `deploy/`, `capacity/`, `chaos/` |
| L7.A.6 | `services/admin-cli/internal/impact_classifier/` | Code | S5 Tier classification (Destructive/Griefing/Informational) |
| L7.A.7 | `services/admin-cli/internal/confirmation/` | Code | Typed confirmation flow (R13 §12L.4): "Type reality name to confirm" |
| L7.A.8 | `services/admin-cli/internal/dry_run/` | Code | Mandatory `--dry-run` mode for destructive commands |
| L7.A.9 | `services/admin-cli/internal/audit_emitter/` | Code | Writes `admin_action_audit` (meta) row via MetaWrite |
| L7.A.10 | `contracts/admin/command_registry.yaml` | Registry | All ~30 commands declared: name, version, params, impact_class, dry_run_required, double_approval_required |
| L7.A.11 | `scripts/admin-command-registry-lint.sh` | CI lint | Block ad-hoc SQL outside command framework |
| L7.A.12 | `tests/integration/admin_cli_test.go` | Test | Each command tested for: auth, dry-run, audit row, typed confirmation, S5 tier enforcement |
| L7.A.13 | `docs/governance/admin-command-catalog.md` | Doc | Human-readable catalog (R13 §12L.5 admin UI guardrails reference) |

**Per-command artifacts (sample — actual list ~30+):**
- `services/admin-cli/commands/reality/force_close.go` — S5 Tier 1 destructive, double-approval
- `services/admin-cli/commands/reality/cancel_close.go` — S5 Griefing, owner-only
- `services/admin-cli/commands/erasure/user_erasure.go` — S08 §12X.6 full runbook
- `services/admin-cli/commands/canon/decanonize.go` — DMCA takedown
- `services/admin-cli/commands/migration/migrate.go` — triggers migration-orchestrator
- `services/admin-cli/commands/capacity/override.go` — (L1.L.3) S5 Tier 2, 24h auto-expire
- `services/admin-cli/commands/deploy/freeze.go` — SR5 deploy freeze
- `services/admin-cli/commands/deploy/canary_advance.go` — SR5 manual advance
- `services/admin-cli/commands/audit/query.go` — sensitive-read instrumented
- `services/admin-cli/commands/chaos/run_drill.go` — SR7 chaos drill
- (... ~20+ more)

**Acceptance criteria:**
- Every command in `command_registry.yaml`
- CI lint blocks new SQL outside framework
- Dry-run mode produces no side effects + outputs predicted impact
- Typed confirmation enforced for destructive commands
- Break-glass JWT issuance audited with 24h auto-expiry

**Open question:**
- Q-L7A-1: command_registry.yaml — single file or per-domain split? Suggested: per-domain split (`registry/reality.yaml`, `registry/erasure.yaml`, ...) + auto-merge by framework loader.
- Q-L7A-2: Admin CLI distribution — single binary OR per-domain binaries? Suggested: single binary with subcommands (`admin reality force-close`) — easier to ship + version.

---

### L7.B — SRE Runbook Library (SR3 27-runbook gate)

**Owning chunks:** SR03 §12AF (canonical schema, directory structure, verification cadence)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.B.1 | `docs/sre/runbooks/` directory | Doc | Root of runbook library |
| L7.B.2 | `docs/sre/runbooks/README.md` | Doc | Library usage guide |
| L7.B.3 | `docs/sre/runbooks/TEMPLATE.md` | Doc | Canonical schema (SR3 §12AF.2 YAML frontmatter + sections) |
| L7.B.4 | `docs/sre/runbooks/INDEX.md` | Auto-gen | Alert→runbook map (generated by L7.B.10 indexer) |
| L7.B.5 | `docs/sre/runbooks/auth/` (3 runbooks) | Doc | token-flow-broken, jwt-expiration-spike, break-glass-initiation |
| L7.B.6 | `docs/sre/runbooks/ws/` (3 runbooks) | Doc | refresh-failures, connection-saturation, mass-disconnect |
| L7.B.7 | `docs/sre/runbooks/meta/` (3 runbooks) | Doc | failover-to-standby, write-audit-hash-mismatch, read-lag-investigation |
| L7.B.8 | `docs/sre/runbooks/publisher/` (2 runbooks) | Doc | lag-spike, dead-letter-queue-review |
| L7.B.9 | `docs/sre/runbooks/projection/` (2 runbooks) | Doc | rebuild-catastrophic, drift-detected |
| L7.B.10 | `docs/sre/runbooks/llm-provider/` (3 runbooks) | Doc | outage-primary, rate-limit-degradation, cost-anomaly |
| L7.B.11 | `docs/sre/runbooks/canon/` (2 runbooks) | Doc | injection-detected, propagation-latency-high |
| L7.B.12 | `docs/sre/runbooks/admin/` (2 runbooks) | Doc | break-glass, command-failure-investigation |
| L7.B.13 | `docs/sre/runbooks/reality/` (3 runbooks) | Doc | provisioning-stuck, archive-verification-failed, lifecycle-corruption |
| L7.B.14 | `docs/sre/runbooks/deploy/` (2 runbooks) | Doc | canary-abort, rollback-execution |
| L7.B.15 | `docs/sre/runbooks/capacity/` (2 runbooks) | Doc | shard-near-full, budget-breach-at-deploy |
| L7.B.16 | `scripts/runbook-index-generator.sh` | Script | Generates INDEX.md from runbook frontmatter |
| L7.B.17 | `scripts/runbook-verification-lint.sh` | CI lint | Block alert without runbook link (SR1-D6); flag runbook past `next_verification_due` |
| L7.B.18 | `scripts/runbook-drift-check.sh` | CI lint | Detect drift: service rename/removal not reflected in runbook `applies_to_services` |
| L7.B.19 | `infra/external-access-docs/` | Doc | Out-of-band docs (S3-hosted, CloudFront-cached) — accessible when AWS console down (SR3 problem 9) |

**Total: 27 runbooks (SR3 V1 launch gate)** + library infrastructure.

**Acceptance criteria:**
- All 27 runbooks present + verified < 90d
- INDEX.md auto-generated correctly
- SR1-D6 lint enforces alert→runbook
- Drift check catches stale runbooks
- External-access docs reachable when CloudWatch/Vault unreachable

**Open question:**
- Q-L7B-1: 27-runbook list — V1 ships all 27 or staggered? Suggested: V1 ships ALL 27 (per SR3 gate); placeholder OK if marked `last_verified: 1970-01-01` + `verification_method: stub`.

---

### L7.C — On-Call Rotation + Escalation Infrastructure

**Owning chunks:** SR02 §12AE.3 (rotation), §12AE.4 (alert routing + fallback chain)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.C.1 | `infra/pagerduty/` Terraform | IaC | PagerDuty (or equivalent) service + escalation policy + schedule |
| L7.C.2 | `infra/pagerduty/rotation_schedule.yaml` | Config | V1 solo / V1+30d 2-person / V2+ team (per SR2 §12AE.3 table) |
| L7.C.3 | `infra/pagerduty/escalation_policy.yaml` | Config | Primary → secondary → tech lead → founder direct (per SR2 §12AE.4) |
| L7.C.4 | `docs/sre/oncall-handoffs/` directory | Doc | Append-only handoff log (SR2 §12AE.3 protocol) |
| L7.C.5 | `docs/sre/oncall-handoffs/TEMPLATE.md` | Doc | Handoff schema: open incidents, SLI burn, expected blips, anomalies |
| L7.C.6 | `infra/alertmanager/routing.yaml` | Config | Maps alert pattern → rotation (per SR2 §12AE.4 alert routing table) |
| L7.C.7 | `services/oncall-bot/` Go service | Code | Slack bot for handoff reminders + ack tracking (V1+30d) |
| L7.C.8 | `tests/integration/escalation_test.go` | Test | Fire alert; primary doesn't ack within TTA → secondary paged; verify escalation chain |
| L7.C.9 | `runbooks/oncall/handoff_missed.md` | Doc | SRE |
| L7.C.10 | `runbooks/oncall/escalation_to_founder.md` | Doc | SRE |

**Acceptance criteria:**
- Alert routes to correct rotation per `applies_to_services` in runbook frontmatter
- Escalation chain timing matches SR2 TTA (5min/15min/30min/2h by severity)
- Handoff log append-only enforced

**Open question:**
- Q-L7C-1: PagerDuty vs OpsGenie vs Squadcast — V1 choice? Suggested: PagerDuty (industry standard, broad integration). Cost ~$25/user/month — accept for V1.
- Q-L7C-2: Solo-dev V1 reality — "weekend 4h non-SEV0" SLA documented in user-facing TOS? Suggested: document in `docs/governance/oncall-sla.md`, NOT in user-facing TOS (V1 is hobby/early). V2+ when paid tier launches → user-facing.

---

### L7.D — Incident Response Infrastructure

**Owning chunks:** SR02 §12AE (severity matrix, IC role, war room), SR04 (postmortem), §12X (GDPR Art.33)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.D.1 | `services/incident-bot/` Go service | Code | Slack bot — declares incident + creates war-room channel + posts severity card |
| L7.D.2 | `services/incident-bot/internal/severity_classifier/` | Code | Auto-escalation rules (SR2 §12AE.2: data integrity → SEV0, canon injection → SEV1, audit hash mismatch → SEV0, personal data breach → SEV0) |
| L7.D.3 | `services/incident-bot/internal/war_room/` | Code | Creates `#incident-<id>` Slack channel + invites IC + fixer + relevant teams |
| L7.D.4 | `services/incident-bot/internal/statuspage/` | Code | Auto-posts to status page (L7.L) for SEV0/SEV1 user-visible |
| L7.D.5 | `services/incident-bot/internal/comms_template/` | Code | Pre-approved customer comms copy (avoids bad copy under pressure — SR2 problem 7) |
| L7.D.6 | `contracts/incidents/severity_matrix.yaml` | Config | 4-severity criteria (SEV0/1/2/3) + TTA + comms obligations |
| L7.D.7 | `services/incident-bot/internal/gdpr_breach_flow/` | Code | Personal data breach → GDPR Art.33 72h notification flow (sends to DPO + records timeline) |
| L7.D.8 | `infra/comms/out_of_band/` | Config | Statuspage hosted external (not on platform infra) — works when prod is the incident (SR2 problem 10) |
| L7.D.9 | `services/postmortem-bot/` Go service | Code | Triggered on incident close; creates `docs/sre/postmortems/<id>.md` from template |
| L7.D.10 | `docs/sre/postmortems/TEMPLATE.md` | Doc | SR04 postmortem template: timeline, root cause (12-enum per SR04-D), action items, follow-up |
| L7.D.11 | `contracts/postmortems/root_cause_enum.yaml` | Config | SR4 12-enum root cause taxonomy |
| L7.D.12 | `services/incident-bot/internal/ic_role/` | Code | IC role workflow tooling (separate from fixer per SR2 §12AE.2) |
| L7.D.13 | `tests/integration/incident_flow_test.go` | Test | Fire auto-SEV0 alert → incident declared → war room created → status page updated → IC assigned → postmortem stub created |
| L7.D.14 | `runbooks/incident/declaration.md` | Doc | SRE |
| L7.D.15 | `runbooks/incident/gdpr_breach.md` | Doc | SRE — 72h flow |
| L7.D.16 | `runbooks/incident/comms_under_pressure.md` | Doc | SRE — comms templates usage |

**Acceptance criteria:**
- Auto-severity rules fire correctly on test fixtures
- War room creation < 30s after incident declaration
- Status page updates per severity comms obligation
- Postmortem stub created automatically on incident close
- GDPR 72h timer enforced + alerts on approaching deadline

---

### L7.E — Structured Logging Library

**Owning chunks:** S08 §12X.8 (log.PII / log.Sensitive / log.Normal tags; compile-time DEBUG guard)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.E.1 | `pkg/logging/` Go library | Code | Structured logging with field tags |
| L7.E.2 | `pkg/logging/pii.go` | Code | `log.PII(name, value)` — auto-masked `***@***.***` in prod; hashed in dev |
| L7.E.3 | `pkg/logging/sensitive.go` | Code | `log.Sensitive(name, value)` — dropped at INFO; visible at DEBUG only in dev builds |
| L7.E.4 | `pkg/logging/normal.go` | Code | `log.Normal(name, value)` — no redaction |
| L7.E.5 | `crates/logging/` Rust crate | Code | Equivalent for Rust services (tracing crate integration) |
| L7.E.6 | `src/loreweave/logging/` Python module | Code | Equivalent for Python services (structlog integration) |
| L7.E.7 | `pkg/logging/compile_guard.go` (+ Rust + Python) | Code | Compile-time DEBUG guard for prod builds (build tag `prod` disables DEBUG) |
| L7.E.8 | `pkg/logging/trace_correlation.go` | Code | Auto-injects trace_id + correlation_id (from L7.G OpenTelemetry context) |
| L7.E.9 | `scripts/logging-discipline-lint.sh` | CI lint | Detect bare `fmt.Println`, `log.Println`, `print` (Python) outside test/debug code |
| L7.E.10 | `scripts/sensitive-field-lint.sh` | CI lint | Detect "email", "password", "token" in `log.Normal` calls (suggest `log.PII` or `log.Sensitive`) |
| L7.E.11 | `tests/integration/logging_test.rs` | Test | PII fields masked in prod build; sensitive dropped at INFO; normal passes through |

**Acceptance criteria:**
- PII auto-mask verified in prod build (test fixture)
- DEBUG-disabled in prod build (compile-time, not runtime)
- All 3 languages have identical API surface
- CI lint blocks bare log calls

---

### L7.F — Log Aggregation Pipeline

**Owning chunks:** S08 §12X.8 (ingest scrubber, 30d retention)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.F.1 | `infra/vector/vector.toml` | Config | Vector log shipper config (or Fluent Bit alternative) |
| L7.F.2 | `infra/vector/scrubber_patterns.yaml` | Config | Regex scrubber patterns (same set as S08 §12X.5: email, phone, ipv4, ipv6, cc_pan, ssn_us, api_key_like) |
| L7.F.3 | `infra/loki/loki-distributed.yaml` | IaC | Loki backend (cheaper than ELK for our scale) |
| L7.F.4 | `infra/loki/retention.yaml` | Config | 30d retention enforced |
| L7.F.5 | `dashboards/logs-explorer.json` | Grafana | Grafana Loki query UI |
| L7.F.6 | `infra/vector/per_service_routing.yaml` | Config | Routes logs by service to topic |
| L7.F.7 | `scripts/log-density-detector.sh` | Script | Drops lines exceeding configured PII density (S08 belt-and-suspenders) |
| L7.F.8 | `tests/integration/log_pipeline_test.go` | Test | Inject log with PII → verify scrubbed at ingest before storage |
| L7.F.9 | `runbooks/logs/loki_down.md` | Doc | SRE |

**Acceptance criteria:**
- Logs reach Loki within 5s of emission
- Ingest scrubber catches PII at L7.E.2 boundary (defense in depth)
- 30d retention enforced (no logs older than 30d)

**Open question:**
- Q-L7F-1: Loki vs ELK vs Datadog? Suggested: Loki self-hosted V1 (cost), reconsider V3+ if log volume justifies managed.

---

### L7.G — Distributed Tracing Infrastructure

**Owning chunks:** event metadata `causation_id` / `correlation_id` (00_overview §4.3) — extended cross-service

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.G.1 | `pkg/tracing/` Go library (OpenTelemetry) | Code | OTEL Go SDK wrapper with standard tags |
| L7.G.2 | `crates/tracing/` Rust crate | Code | OTEL Rust SDK wrapper |
| L7.G.3 | `src/loreweave/tracing/` Python module | Code | OTEL Python SDK wrapper |
| L7.G.4 | `frontend-game/src/tracing/` TS module | Code | OTEL JS for frontend (Real User Monitoring) |
| L7.G.5 | `pkg/tracing/propagation.go` (+ Rust + Python) | Code | W3C Trace Context propagation via HTTP headers + WS message metadata |
| L7.G.6 | `infra/tempo/tempo.yaml` | IaC | Tempo backend (Grafana stack alignment with Loki) |
| L7.G.7 | `pkg/tracing/sampler.go` | Code | Adaptive sampling: 100% for SEV0/SEV1 incidents, 1-10% baseline |
| L7.G.8 | `infra/tempo/retention.yaml` | Config | 14d retention (shorter than logs — traces are debugging evidence) |
| L7.G.9 | `dashboards/traces-explorer.json` | Grafana | Tempo + service map |
| L7.G.10 | `tests/integration/tracing_test.rs` | Test | Cross-service request: trace span correctly propagates Rust → Go → Python |
| L7.G.11 | `scripts/tracing-completeness-lint.sh` | CI lint | Block new HTTP/RPC handler missing tracing wrap |

**Acceptance criteria:**
- Span propagates across Rust ↔ Go ↔ Python ↔ TS
- Adaptive sampling increases to 100% during active SEV0/SEV1
- Trace lookup by `correlation_id` < 5s P99 in Tempo

---

### L7.H — Prometheus + Grafana Infrastructure

**Owning chunks:** R04 §12D.5 (per-DB metrics), C03 §12O.12 (meta metrics), Q-L1I-1 + Q-L1I-2 LOCKED

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.H.1 | `infra/prometheus/main.yaml` | IaC | Prometheus HA pair (federation per Q-L1I-1) |
| L7.H.2 | `infra/prometheus/recording-rules/` | Config | Aggregation rules (per-shard, per-status, per-deploy-cohort, per-tier) |
| L7.H.3 | `infra/prometheus/scrape-config-generator.sh` | Script | Dynamic scrape targets per L1.C provisioner |
| L7.H.4 | `infra/thanos/thanos.yaml` | IaC | Thanos sidecar for 1y+ retention (Q-L1I-2: V1+30d activation) |
| L7.H.5 | `infra/grafana/grafana.ini` | Config | Grafana with SSO (auth-service integration) |
| L7.H.6 | `dashboards/_library/` directory | Doc | Dashboard library with standards |
| L7.H.7 | `dashboards/_library/STANDARDS.md` | Doc | Color palette, panel layout conventions, drill-down patterns |
| L7.H.8 | `dashboards/_library/TEMPLATE.json` | JSON | Canonical dashboard template |
| L7.H.9 | `dashboards/platform/` (10+ dashboards) | JSON | Platform-wide: SLO summary, reality fleet, meta HA, publisher health, projection health, canon propagation, LLM cost, security events, supply chain, SLO error budget |
| L7.H.10 | `dashboards/per-service/` (per-service dashboards × 20+ services) | JSON | One per service following template |
| L7.H.11 | `scripts/dashboard-validator.sh` | CI lint | Block dashboards not conforming to template |
| L7.H.12 | `tests/integration/dashboard_render_test.go` | Test | All dashboards render without errors against test Prometheus |

**Acceptance criteria:**
- HA pair survives single Prometheus failure
- Thanos retains 1y+ at acceptable cost (sized in capacity budget)
- All dashboards follow template
- Drill-down from platform → per-service works

---

### L7.I — SLO + Error Budget Infrastructure

**Owning chunks:** SR01 §12AD (7 SLIs, error budget policy, burn-rate 4-tier response)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.I.1 | `contracts/slo/sli_definitions.yaml` | Registry | 7 SLIs per SR1 §12AD.2: sli_session_availability, sli_turn_completion, sli_event_delivery, sli_realtime_freshness, sli_auth_success, sli_admin_action_success, sli_cross_reality_propagation |
| L7.I.2 | `contracts/slo/slo_targets.yaml` | Registry | SLO targets per tier (free/paid/premium) per SR1 §12AD.3 |
| L7.I.3 | `infra/prometheus/recording-rules/sli.yaml` | Config | Recording rules computing each SLI from raw metrics |
| L7.I.4 | `services/slo-budget-calculator/` Go service | Code | Computes burn rate per SLI per window (7d / 30d) |
| L7.I.5 | `dashboards/slo-burn-rate.json` | Grafana | Per-SLI burn rate visualization |
| L7.I.6 | `infra/prometheus/alerts/slo-burn.yaml` | Config | 4-tier burn-rate alerts per SR1 §12AD.4 |
| L7.I.7 | `scripts/feature-freeze-enforcer.sh` | CI lint | Detects burn ≥ 75% → adds `reliability-review-required` label to PRs; ≥ 90% → blocks PR without `approve-reliability-override` |
| L7.I.8 | `services/slo-budget-calculator/internal/multi_tenant_isolation/` | Code | SR1 §12AD.5 noisy-neighbor detection (3σ anomaly) |
| L7.I.9 | `docs/sre/slo-reviews/` directory | Doc | Weekly engineering review log (freeze/unfreeze decisions) |
| L7.I.10 | `docs/sre/slo-reviews/TEMPLATE.md` | Doc | Per-week review template |
| L7.I.11 | `runbooks/slo/burn-rate-spike.md` | Doc | SRE per-SLI runbook |
| L7.I.12 | `runbooks/slo/multi-tenant-isolation-violation.md` | Doc | SRE noisy-neighbor runbook |
| L7.I.13 | `tests/integration/burn_rate_test.go` | Test | Inject SLI violations; verify burn calculated correctly; verify freeze trigger fires |

**Acceptance criteria:**
- All 7 SLIs computed correctly from raw metrics
- Burn rate alerts fire at correct thresholds
- Feature freeze auto-enforced at ≥ 90% burn
- Multi-tenant isolation SLO monitored

---

### L7.J — Alertmanager Infrastructure

**Owning chunks:** SR09 §12AL (rules.yaml, severity × action-class taxonomy), SR2 §12AE.4 (routing table), L4.P

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.J.1 | `infra/alertmanager/main.yaml` | Config | Routing per SR2 §12AE.4 |
| L7.J.2 | `infra/alertmanager/channels.yaml` | Config | Slack, email, PagerDuty webhooks |
| L7.J.3 | `infra/alertmanager/inhibition_rules.yaml` | Config | Suppress lower-severity alerts during SEV0/SEV1 |
| L7.J.4 | `infra/alertmanager/silence_admission_policy.yaml` | Config | Who can silence what; auto-expiry per silence category |
| L7.J.5 | `services/alert-recorder/` Go service | Code | Writes `alert_outcomes` + `alert_silences` (meta) via MetaWrite |
| L7.J.6 | `contracts/alerts/rules.yaml` extension | Config | (L4.P.1) All alert rules with severity_map + escalation per SR2 |
| L7.J.7 | `scripts/alert-rule-validator.sh` | CI lint | Every alert has runbook reference (SR1-D6) |
| L7.J.8 | `tests/integration/alert_routing_test.go` | Test | Fire alert; verify routing per SR2 table; verify inhibition during SEV0 |
| L7.J.9 | `runbooks/alerts/silence_misuse.md` | Doc | SRE |

**Acceptance criteria:**
- Alert routes match SR2 routing table
- Inhibition prevents alert storm during major incident
- Silence audit complete (who silenced what + auto-expiry)

---

### L7.K — Deploy Pipeline + CI/CD Orchestration

**Owning chunks:** SR05 §12AH (deploy classification, freeze, canary, feature flags), SR1-D3 (burn-rate freeze)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.K.1 | `.github/workflows/deploy.yml` | CI | Main deploy workflow |
| L7.K.2 | `.github/workflows/lint.yml` | CI | All 15 L1.K lints + L7 lints |
| L7.K.3 | `.github/workflows/canary.yml` | CI | Triggered after main deploy; advances canary stages per SR5 §12AH.4 |
| L7.K.4 | `services/canary-controller/` Go service | Code | Reads `deploy_audit`; advances/aborts based on cohort SLI burn |
| L7.K.5 | `services/canary-controller/internal/cohort_router/` | Code | Routes by `reality_registry.deploy_cohort` (L1.A reality_registry extension) |
| L7.K.6 | `scripts/deploy-class-check.sh` | CI lint | Patch/minor/major/emergency classification per SR5 §12AH.2 |
| L7.K.7 | `scripts/deploy-freeze-check.sh` | CI lint | Block PR during active freeze (SLO burn, scheduled, incident, security) |
| L7.K.8 | `services/admin-cli/commands/deploy/break_glass.go` | Code | Break-glass-deploy PR label workflow per SR5 §12AH.3 |
| L7.K.9 | `dashboards/deploy-progress.json` | Grafana | Canary stage progress |
| L7.K.10 | `tests/integration/canary_advance_test.go` | Test | Inject cohort SLI; verify auto-advance at threshold; verify auto-abort on SLI burn |
| L7.K.11 | `tests/integration/deploy_freeze_test.go` | Test | Force burn ≥ 90% → verify PR blocked unless override |
| L7.K.12 | `runbooks/deploy/canary_abort.md` | Doc | SRE |
| L7.K.13 | `runbooks/deploy/freeze_override.md` | Doc | SRE |

**Acceptance criteria:**
- Deploy class auto-detected from PR diff
- Canary advances per stage timing (10min/30min/2h/4h)
- Auto-abort + rollback on cohort SLI burn > 2× baseline
- Freeze blocks PR per 4 freeze types

**Open question:**
- Q-L7K-1: V1 = GitHub Actions only? Or also ArgoCD GitOps? Suggested: GitHub Actions V1 (matches existing LoreWeave novel platform); ArgoCD V2+ if multi-cluster.

---

### L7.L — Status Page + Customer Comms

**Owning chunks:** SR02 §12AE.2 (status page comms obligation), SR02 problem 10 (out-of-band)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L7.L.1 | `infra/statuspage/` IaC | IaC | Hosted Statuspage.io (or Atlassian Statuspage) — external to platform |
| L7.L.2 | `infra/statuspage/components.yaml` | Config | Component list matching service catalog (gateway, auth, world, roleplay, …) |
| L7.L.3 | `services/statuspage-updater/` Go service | Code | Listens to incident events → auto-updates status page |
| L7.L.4 | `infra/statuspage/templates/` | Config | Comms templates (i18n via i18next — V1 EN+VI minimum) |
| L7.L.5 | `infra/statuspage/banner-config.yaml` | Config | Auto-banner SEV0/SEV1 per SR2 §12AE.2 |
| L7.L.6 | `tests/integration/statuspage_test.go` | Test | Declare SEV0 → status page auto-banner appears within 30s |
| L7.L.7 | `runbooks/statuspage/manual_update.md` | Doc | SRE |

**Acceptance criteria:**
- Status page hosted externally (not on platform infra)
- Auto-update within 30s of incident declaration
- i18n EN+VI minimum

**Open question:**
- Q-L7L-1: Statuspage.io vs self-hosted (Cachet)? Suggested: Statuspage.io V1 (~$29/month, professional UX, EN+VI supported); self-hosted V2+ if cost concern.

---

## §3. L7 cross-component dependency graph

```
L7.E (logging lib) ─→ L7.F (log pipeline consumes)
L7.G (tracing lib) ─→ L7.H (Grafana Tempo backend)
L7.E + L7.G ←─ ALL services (every service imports)

L7.H (Prometheus + Grafana) ←─ ALL services (every service emits metrics)
L7.I (SLO infra) ←─ L7.H (reads metrics)
L7.J (Alertmanager) ←─ L7.H + L7.I + L4.P (rules.yaml)

L7.A (admin-cli) ←─ L1.B (uses MetaWrite for audit) + L4.M (SVID auth)
L7.A admin commands ←─ EVERY domain has admin commands

L7.B (runbook library) ←─ ALL services + L7.J (alert→runbook link)
L7.C (on-call) ←─ L7.J (routing) + L7.D (incident comms)
L7.D (incident infra) ←─ L7.J + L7.L (status page) + L1.A.6.1 (incidents table)

L7.K (deploy pipeline) ←─ L1.A.6.3 (deploy_audit) + L7.I (SLO burn check) + L1.K (all lints)
L7.L (status page) ←─ L7.D + L7.C

Foundational ordering: L7.E + L7.G (libs) → L7.H (Prom+Grafana) → L7.I (SLOs) + L7.J (Alertmanager) → L7.B (runbook library) → L7.A (admin-cli) → L7.C (on-call) → L7.D (incident infra) → L7.K (deploy pipeline) → L7.L (status page) + L7.F (log pipeline)
```

---

## §4. Acceptance criteria for whole L7 (RAID verify gate)

- Logging: PII auto-masked in prod build
- Tracing: span propagates across all 4 languages
- Prometheus: HA pair + Thanos long-term retention
- SLO: all 7 SLIs computed + burn-rate freeze enforced
- Alertmanager: routing per SR2 table + inhibition during incident
- Admin CLI: ~30 commands cataloged + framework enforced
- Runbook library: 27 runbooks present + SR1-D6 lint passes
- On-call: rotation + escalation chain tested
- Incident: auto-severity + war-room + status page + GDPR 72h timer
- Deploy: canary auto-advance/abort + freeze enforcement
- Status page: external + auto-update + i18n

---

## §5. Open questions surfaced during L7 enumeration

| # | Question | Suggested resolution | Status |
|---|---|---|---|
| Q-L7A-1 | command_registry.yaml — single or per-domain split? | Per-domain split + framework auto-merge | Suggested |
| Q-L7A-2 | Admin CLI distribution | Single binary with subcommands | Suggested |
| Q-L7B-1 | 27-runbook list — V1 ships all or staggered? | V1 ships ALL 27; stub OK for placeholders | Suggested |
| Q-L7C-1 | PagerDuty vs alternatives? | PagerDuty (industry standard) | Suggested |
| Q-L7C-2 | Solo-dev weekend SLA — user-facing TOS? | Internal `docs/governance/oncall-sla.md` V1; user-facing V2+ | Suggested |
| Q-L7F-1 | Loki vs ELK vs Datadog? | Loki self-hosted V1; reconsider V3+ | Suggested |
| Q-L7K-1 | GitHub Actions only V1, or ArgoCD too? | GitHub Actions V1; ArgoCD V2+ | Suggested |
| Q-L7L-1 | Statuspage.io vs self-hosted? | Statuspage.io V1; self-hosted V2+ if cost concern | Suggested |
| Q-L7-1 | Incident-bot + statuspage-updater + slo-budget-calculator — bundle into one ops-bot? | Suggested: separate services (clear ops boundaries per service map convention) | Suggested |
| Q-L7-2 | Comms template pre-approval workflow | Pre-approved templates stored in `infra/comms/templates/`; new templates require legal review (V2+ formal) | Suggested |
| Q-L7-3 | Service mesh (Istio/Linkerd) for tracing/auth? | NOT V1 (adds complexity); revisit V3+ when service count > 30 | Suggested |
| Q-L7-4 | Frontend (RUM) metrics — foundation owns or frontend-game team? | frontend-game team owns RUM; foundation owns backend tracing | Suggested |

---

## §6. Cycle decomposition hint for L7

| Cycle | Scope | Why grouped |
|---|---|---|
| L7-cycle-1 | L7.E (logging libs) + L7.G (tracing libs) | Foundational cross-cutting libs; every service imports |
| L7-cycle-2 | L7.H (Prometheus + Grafana + Thanos) + L7.F (Loki + Vector) | Observability infra; depends on L7.E+G for emitters |
| L7-cycle-3 | L7.I (SLO infra) + L7.J (Alertmanager) | SLO + alerts together; depend on L7.H |
| L7-cycle-4 | L7.B (runbook library — all 27 runbooks) + L7.C (on-call rotation) | Library + rotation paired; depend on alerts existing |
| L7-cycle-5 | L7.A (admin-cli framework + ~30 commands) | Largest single cycle; touches every domain |
| L7-cycle-6 | L7.D (incident infra) + L7.L (status page) | Incident-to-customer-comms flow |
| L7-cycle-7 | L7.K (deploy pipeline + canary controller) | Deploy automation; depends on SLO + canary cohort field |

**Total L7 estimate: ~7 RAID XL cycles.**

---

## §7. Status

```
[x] L7 — 12 sub-components enumerated at B-level (A-L)
[x] L7 — cross-component deps mapped
[x] L7 — 12 open questions surfaced
[x] L7 — cycle decomposition hint (~7 cycles)
[ ] L7 — open questions resolved (batch lock pending)
[ ] CLARIFY MASTER + scope updated to include L7
[ ] Final cycle decomposition (with L7 = ~38 cycles total)
[ ] RAID workflow specification
[ ] Final commits
```
