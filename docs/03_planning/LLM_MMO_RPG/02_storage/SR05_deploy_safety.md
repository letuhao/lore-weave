<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: SR05_deploy_safety.md
byte_range: 447248-464797
sha256: 0cd1cf28221011aa4cb1247c0a45bb19f0bc0c702adc9b4d53430a9586949fa4
generated_by: scripts/chunk_doc.py
-->

## 12AH. Deploy Safety + Rollback — SR5 Resolution (2026-04-24)

**Origin:** SRE Review SR5 — R2 (projection rebuild) + R3 (§12C schema evolution) covered design-time schema safety + upcasters, but **operational deploy** — canary, rollback, feature flags, freeze enforcement, deploy windows, change review — was absent. SR1-D3 feature freeze references enforcement that didn't exist. SR3-D6 dry-run-first discipline needs analogous framework for code/schema/config deploys.

### 12AH.1 Problems closed

1. Flat deploy treatment (no blast-radius tiering)
2. Missing freeze operational implementation
3. Big-bang deploys (no canary)
4. No runtime toggle / feature flag framework
5. Schema migration rollout ad-hoc
6. Config change risk unchecked
7. Rollback decision framework missing
8. "Which deploy caused this?" observability gap
9. Ad-hoc review process
10. Friday-deploy syndrome unaddressed
11. Multi-reality cohort rollout undesigned
12. Emergency vs normal distinction absent

### 12AH.2 Layer 1 — Deploy Classification + Gating

4-class enum with gating requirements:

| Class | Scope | Gating |
|---|---|---|
| `patch` | Single service, no schema, no contract change, no external interface | CI + 1 reviewer |
| `minor` | Single service with migration OR config change OR new endpoint | CI + 2 reviewers + migration plan |
| `major` | Multi-service OR contract-breaking OR schema-breaking OR new feature OR privileged command | Full gate: CI + 2 reviewers + change advisory (L9) + migration/rollback runbook + canary (L3) |
| `emergency` | Security patch / incident response / cost-control hotfix | Fast-track: 1 reviewer + post-deploy review ≤24h |

Classification signals (`deploy-class-check.sh` CI lint):
- `patch`: no files in `contracts/*`, no migration files, no service count change
- `minor`: migration file OR `config/*` change OR new endpoint in `contracts/api/*`
- `major`: multiple services touched OR contract-breaking OR schema-breaking OR security-sensitive
- `emergency`: `emergency` label + `incident_id` OR `security_finding_id` referenced

Class mismatch (e.g., migration file in PR labeled `patch`) = CI fails.

### 12AH.3 Layer 2 — Deploy Freeze Mechanisms

| Freeze type | Trigger | Scope | Override |
|---|---|---|---|
| **SLO burn freeze** (SR1-D3) | Any SLI burn rate ≥90% over 7d | All classes except `emergency` | Tech lead + post-deploy review |
| **Scheduled freeze** | `admin/deploy-freeze` CLI | Configurable scope | Founder approval |
| **Incident-triggered** | Active SEV0/SEV1 involving service | Affected service + dependencies | IC + tech lead |
| **Security-triggered** | Active attack OR supply-chain suspicion | Platform-wide | Security on-call + tech lead |

Freeze UX:
- CI check `deploy-freeze-check.sh` runs on every PR; labels PR with ⛔ + tooltip (which freeze + thaw ETA)
- `emergency` class bypass: `break-glass-deploy` PR label + tech lead CODEOWNERS approval + mandatory post-deploy review
- DF11 dashboard: active freezes, affected scopes, thaw estimates

### 12AH.4 Layer 3 — Canary Rollout Protocol

For `major` class + any service handling user traffic:

| Stage | Scope | Monitor window | SLO threshold |
|---|---|---|---|
| **0 — internal** | LoreWeave dev accounts only | 10 min | Error rate = 0 |
| **1 — 1% realities** | Random 1% (weighted non-premium) | 30 min | Cohort SLI burn < 2× baseline |
| **2 — 10%** | Next 10% cohort | 2 hours | Cohort SLI burn < 2× baseline |
| **3 — 50%** | Next 40% | 4 hours | Cohort SLI burn < 2× baseline |
| **4 — 100%** | Remaining | — | — |

Each stage:
- `lw_canary_sli_cohort{stage, service}` metric tracks per-cohort SLI
- **Auto-abort** on cohort SLI burn > baseline × 2 → automatic rollback + SRE paged
- Manual advance allowed (tech lead approval) for trusted deploys
- Manual early-proceed allowed (skip wait) with risk acknowledgment

Per-reality canary selection via new field:
```sql
ALTER TABLE reality_registry
  ADD COLUMN deploy_cohort INT NOT NULL;                     -- hash(reality_id) % 100
CREATE INDEX ON reality_registry (deploy_cohort);
```

Cohort assigned at creation; stable for reality's lifetime. Canary rolls cohorts in order (0→99).

### 12AH.5 Layer 4 — Feature Flags (runtime toggle)

```sql
CREATE TABLE feature_flags (
  flag_name             TEXT PRIMARY KEY,
  description           TEXT NOT NULL,
  default_enabled       BOOLEAN NOT NULL DEFAULT false,
  target_scope          TEXT NOT NULL,       -- 'global' | 'reality' | 'user' | 'cohort' | 'tier'
  enabled_realities     UUID[],
  enabled_users         UUID[],
  enabled_cohorts       INT[],
  enabled_tiers         TEXT[],              -- 'free' | 'paid' | 'premium'
  owner                 UUID NOT NULL,
  created_at            TIMESTAMPTZ NOT NULL,
  planned_removal_date  DATE NOT NULL,       -- MANDATORY; flag-debt control
  current_status        TEXT NOT NULL        -- 'experimental' | 'rolling_out' | 'full' | 'deprecated'
);
```

**Governance:**
- New flag MUST declare `planned_removal_date` (CI lint enforces on migration adding new flag row)
- **Quarterly flag-debt review**: flags past `planned_removal_date` = cleanup required OR extension justification (reviewed in SR2-D8 cadence)
- Flag toggle commands = S5 Tier 2 Griefing (user-visible change):
  - `flag/enable` · `flag/disable` · `flag/set-scope`
- Flag reads cached 60s per service; TTL forces fresh reads regularly
- Flag-debt metric: `lw_flag_debt_count{status='past_removal_date'}` gauge

**Flag vs deploy rollback:**
- **Prefer flags** for new features (instant rollback via toggle)
- **Prefer code rollback** for bug fixes (flag adds complexity without benefit)

### 12AH.6 Layer 5 — Schema Migration Operational Protocol

R3 (§12C) upcaster chain + schema-as-code cover **design-time** safety. SR5-L5 adds **rollout**.

**6-phase protocol** per migration:

| Phase | Action | Rollback |
|---|---|---|
| 1. Pre-flight | Test migration in dev + staging + 1% prod sample | Abort; fix + retry |
| 2. Additive first | Add columns/tables as nullable; no-op for existing readers | Drop additions (safe, no data loss) |
| 3. Deploy code | New code reads old + new; writes old | Code rollback (additive columns stay) |
| 4. Backfill | Long-running data migration; pausable + resumable | Halt backfill; existing data usable |
| 5. Cutover | Switch writers to new schema; readers already handle both | Abort cutover; revert to dual-read |
| 6. Remove old | Drop deprecated columns; nullable → required | — (preceded by deprecation window) |

Each migration PR includes `migration_plan.md`:
- Phase-by-phase timeline
- Per-phase rollback procedure
- Monitoring criteria per phase
- Cohort rollout schedule

**Multi-reality rollout** (per canary L3):
- `migration-orchestrator` service applies migrations per cohort
- `reality_migration_audit` table (§12N) records per-reality per-phase status
- Any reality fails migration → halt entire cohort + alert + investigation

**Breaking changes** (§12C.5 new-event-type pattern):
- Launch new event type alongside old
- Code reads both during transition (≥30 days)
- Deprecation schedule locked at launch
- Removal is separate deploy after window

### 12AH.7 Layer 6 — Config Change Safety

Config changes (env vars, service ACL, alert thresholds, feature flag defaults) = same risk as code.

PR requirements:
- Visible diff (not opaque binary)
- Config validation test (JSON schema / Go struct / YAML lint)
- Dry-run where possible (`config-apply --dry-run`)
- Rollback plan (usually revert PR)
- Owner + reviewer (2 for prod config)

Config rollout:
- **Single-service**: config reload via vault watch / ECS task refresh
- **Platform-wide**: staged per L3 canary cohorts
- **Alert config**: backtest against historical data — CI hook replays alert rule against last 7 days of metrics; answers "would this alert have fired correctly?"

Config audit:
- Every config change writes to `deploy_audit` with `deploy_type='config'`

### 12AH.8 Layer 7 — Rollback Decision Framework

Per-change-type rollback table:

| Change type | Rollback method | Safety | Notes |
|---|---|---|---|
| Code (no schema) | Redeploy prior image tag | ✅ Fast, safe | Preferred |
| Feature flag | Disable flag | ✅ Instant, no redeploy | Best for new features |
| Schema additive | Deploy prior code; additions stay | ✅ Safe | Additions inert if unused |
| Schema breaking — mid-cutover | Abort cutover; return to dual-read | ⚠️ Complex | Requires procedure knowing how to reverse |
| Schema breaking — post-cutover | Fix-forward usually better | ⚠️ Case-by-case | Data in new schema migratable back but risky |
| Config | Revert config PR + reload | ✅ Fast | Prefer forward-fix if reload slow |
| Data migration (backfill) | Halt; revert code | ⚠️ Partial state | Design backfill to be idempotent + resumable |

Runbook `admin/deploy-rollback.md` in SR3 library codifies the table + decision framework.

**Rollback vs fix-forward decision:**
- **Rollback if**: user impact active + clear mitigation + rollback is safe (known-safe prior version)
- **Rollback if**: root cause hypothesis unclear + need to isolate (rollback = bisect)
- **Fix-forward if**: impact bounded + rollback introduces new risk (e.g., rolling past schema migration)
- **Fix-forward if**: rollback cost > current impact (rare; document carefully)

**Rollback-first bias**: "Fix-forward requires explicit justification" rule written in runbook.

### 12AH.9 Layer 8 — Deploy Audit + Observability Correlation

```sql
CREATE TABLE deploy_audit (
  deploy_id             UUID PRIMARY KEY,
  deploy_class          TEXT NOT NULL,            -- 'patch' | 'minor' | 'major' | 'emergency'
  service               TEXT NOT NULL,
  from_version          TEXT,
  to_version            TEXT NOT NULL,
  deploy_type           TEXT NOT NULL,            -- 'code' | 'schema' | 'config' | 'flag'
  cohorts_affected      INT[],                     -- canary progression
  current_stage         INT,                       -- L3 stage
  initiated_at          TIMESTAMPTZ NOT NULL,
  completed_at          TIMESTAMPTZ,
  status                TEXT NOT NULL,            -- 'in_progress' | 'success' | 'aborted' | 'rolled_back'
  initiated_by          UUID NOT NULL,
  approved_by           UUID[],                    -- 2+ for major
  change_ref            TEXT,                      -- PR URL
  rollback_plan_ref     TEXT,                      -- migration_plan.md path
  auto_rollback_reason  TEXT,
  related_incident_id   UUID                       -- if deploy caused / resolved incident
);

CREATE INDEX ON deploy_audit (service, initiated_at DESC);
CREATE INDEX ON deploy_audit (status) WHERE status = 'in_progress';
CREATE INDEX ON deploy_audit (deploy_class, initiated_at DESC);
```

Retention: **5 years** (aligns §12T.5).

**Correlation mechanisms:**
- Alerts + incidents auto-annotated with `recent_deploys` array: any `deploy_audit` within 1h of alert fire, same service
- `incidents.related_audit_refs` jsonb (SR2-D7) includes deploy_audit_ids
- "Recent deploys" panel in DF11 dashboard
- SLO dashboard shows deploy markers on SLI timelines (correlation at a glance)
- SR4-D7 `deploy_induced` root cause category tied to deploy_audit_id

### 12AH.10 Layer 9 — Change Advisory (async)

For `major` class deploys:

**Process:**
1. Deploy intent + scope posted in `#change-advisory` Slack ≥24h before (or async equivalent)
2. Review participants: tech lead + SRE + affected-service owner(s)
3. Risk assessment posted: blast radius + rollback ease + SLI impact estimate + canary plan
4. Reviewers respond: ✅ green light / 🟡 request-changes / ❌ block
5. **Tech lead green light mandatory**; 2+ total green lights required
6. Post-deploy retro in next weekly SR2 review

Templates at `docs/sre/change-advisory-templates/`:
- `change-advisory-intent.md` (24h notice)
- `change-advisory-retro.md` (post-deploy)

**V1 solo-dev pattern** (same philosophy as SR4):
- Self-review + 48h-sit + post-to-empty-channel
- Forces articulation + future-self-reader clarity
- External mentor review if accessible

**Emergency class:** skips advisory but requires:
- Post-deploy review within 24h
- Incident / security finding reference in PR
- Entry in `deploy_audit` with `deploy_class='emergency'`

### 12AH.11 Layer 10 — Deploy Windows + Guardrails

Standard deploy windows (V1 founder timezone UTC+7):

| Window | Allowed classes |
|---|---|
| Mon–Thu 10:00–16:00 local | patch · minor · major |
| Friday 10:00–14:00 | patch · emergency |
| Friday 14:00+ · weekends · holidays | emergency only |
| Night (local 22:00–08:00) | emergency only |

**Guardrails:**
- Deploy outside standard window → PR requires `off-hours-deploy` label + tech lead approval
- `emergency` class allowed anytime + post-deploy review within 24h
- Scheduled deploys (maintenance windows) announced via `status-page-admin` ≥48h before

CI check `deploy-window-check.sh`:
- Reads current UTC+7 time + PR class + labels
- Blocks merge if outside allowed window without proper label
- PR comment shows "next allowed deploy time" if blocked

**V2+ evolution:** deploy windows widen as team grows + timezones span; follow-the-sun V3+.

### 12AH.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| SR1-D3 | Error budget ≥90% freeze enforced by deploy-freeze-check.sh CI lint |
| SR2-D4 | Incident `mitigated` state often achieved via deploy rollback |
| SR2-D7 | `incidents.related_audit_refs` includes deploy_audit_ids |
| SR3-D6 | Deploy commands follow dry-run-first discipline (runbook L7 codifies) |
| SR4-D7 | Root cause categories `deploy_induced` + `change_management_failure` count deploy-origin incidents |
| §12C (R3) | Upcaster chain underpins L5 migration protocol |
| §12B (R2) | Projection rebuild coordinates with schema cutover phase |
| §12N | `reality_migration_audit` is per-reality phase tracker |
| §12U (S5) | Flag ops + deploy rollback = Tier 2 Griefing; freeze override = Tier 1 |
| §12AA.10 (S11) | `service_to_service_audit` captures deploy-initiated RPCs |
| ADMIN_ACTION_POLICY | New commands: `admin/deploy-freeze` Tier 2 · `flag/enable` Tier 2 · `flag/disable` Tier 2 · `admin/deploy-rollback` Tier 2 · `admin/deploy-override-freeze` Tier 1 |
| DF11 dashboard | Deploy panel + freeze panel + canary stage tracking |
| CLAUDE.md | Gateway invariant + contract-first + provider-gateway invariant all deploy-implicated |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| Deploy class + CI enforcement | Prevents blast-radius misclassification; ~30s CI overhead per PR |
| 5-stage canary = slower | Blast radius bounded; acceptable for many-reality fleet |
| Flag-debt accumulation risk | Mandatory `planned_removal_date` + quarterly review mitigates |
| 6-phase migration = multi-deploy | Safer than big-bang; more deploys but smaller blast each |
| Deploy windows restrict velocity | Safety > speed; emergency class provides escape |
| Change advisory adds latency | 24h for major; review depth worth it; V1 solo absorbs |
| `deploy_audit` adds another table | Audit-grade; aligns with other ops audits |
| `reality_registry.deploy_cohort` column | Schema addition; stable for reality lifetime; low cost |

**What this resolves:**

- ✅ Flat deploy treatment — L1 class enum + gating
- ✅ Freeze operational — L2 4 mechanisms + override
- ✅ Big-bang deploys — L3 canary protocol + auto-abort
- ✅ No runtime toggle — L4 flags + governance
- ✅ Schema rollout ad-hoc — L5 6-phase protocol + cohort rollout
- ✅ Config change risk — L6 PR requirements + alert backtest
- ✅ Rollback confusion — L7 per-type framework + runbook + rollback-first bias
- ✅ "Which deploy?" observability — L8 deploy_audit + SLO correlation
- ✅ Ad-hoc review — L9 change advisory (async) + V1 solo pattern
- ✅ Friday-deploys — L10 windows + CI enforcement

**V1 / V1+30d / V2+ split:**

- **V1**:
  - L1 classification + CI enforcement
  - L2 freeze mechanisms (SLO burn integration; manual `admin/deploy-freeze`)
  - L3 canary protocol (may start at stage 2 or 3 initially before reality count justifies 0/1)
  - L4 feature flags + governance + flag-first-for-new-features
  - L5 6-phase migration + `migration-orchestrator` + cohort rollout
  - L6 config PR requirements
  - L7 rollback runbook + decision framework
  - L8 `deploy_audit` table
  - L9 change advisory for major (V1 solo pattern)
  - L10 deploy windows
- **V1+30d**:
  - L3 full stage 0/1 canary automation once reality count grows
  - L6 alert-config backtest CI hook
  - L9 multi-person advisory when team expands
- **V2+**:
  - Blue-green deploy for schema migration (§12B.3)
  - ML anomaly detection in canary SLI
  - Automated rollback (human-in-loop → automated)
  - Follow-the-sun deploy windows

**Residuals (deferred):**
- V2+ blue-green deploy per §12B.3
- V2+ ML anomaly in canary SLI monitoring
- V2+ automated rollback (trust in auto-decide)
- V3+ follow-the-sun windows
- Deploy artifact provenance + SBOM → SR10 supply chain
- Progressive config rollout with canary cohorts (V2+)

