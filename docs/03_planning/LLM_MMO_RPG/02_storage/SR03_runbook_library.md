<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: SR03_runbook_library.md
byte_range: 414170-430312
sha256: 0b75e7832c8c8d46189debbee923d9288ddb1b3b77ae4a6bae57fb4d1679c677
generated_by: scripts/chunk_doc.py
-->

## 12AF. Runbook Library — SR3 Resolution (2026-04-24)

**Origin:** SRE Review SR3 — SR1-D6 requires every alert link to a runbook; SR2-D6 references runbooks as core ops artifacts. But the library itself, format, verification, drift detection, and accessibility were undesigned. Without a runbook library, alert→runbook binding is aspirational; 3am ops is wishful.

### 12AF.1 Problems closed

1. Scattered knowledge (§12 design docs, alert descriptions, tribal memory) — not 3am-readable
2. No canonical runbook format
3. SR1-D6 alert→runbook mapping has nothing to link to
4. No ownership / drift detection as architecture evolves
5. No verification cadence (is this runbook still accurate?)
6. Dry-run discipline missing for destructive commands
7. Ambiguous-incident decision trees undefined
8. Post-incident runbook update flow undefined
9. External access documentation during incident (when AWS/Vault may be down)
10. Accessibility during incident (SR2-D10 reiterated)
11. New on-call confusion vs orientation
12. Tool-docs vs runbook distinction unclear

### 12AF.2 Layer 1 — Canonical Runbook Schema

Every runbook is a markdown file with YAML frontmatter:

```yaml
---
runbook_id: ws/refresh-failures
version: 1
owner: sre-team                           # GitHub CODEOWNERS
applies_to_alerts: [lw_ws_refresh_failures_high]
applies_to_incidents: []
applies_to_services: [api-gateway-bff, auth-service]
last_verified: 2026-04-24
last_verified_by: alice
verification_method: reading_review        # reading_review | tabletop | chaos_drill
next_verification_due: 2026-07-24         # default +90d
severity_hints: [sev2, sev1_if_correlates_with_outage]
dry_run_required_for_destructive: true
related_runbooks: [auth/token-flow, ws/connection-debugging]
external_access_needed: [aws_cloudwatch_logs, grafana_ws_dashboard]
born_from_incident_id: null               # set if runbook created from postmortem
---

# WS Refresh Failures

## TL;DR (30 seconds)
[One paragraph: what's happening + first immediate action]

## Symptoms
- Alert fires
- User-visible
- Dashboard indicators

## Likely Causes (ranked by frequency)
1. Cause — verify method — fix
2. ...

## Diagnostic Commands
[Copy-paste ready, dry-run first]

## Mitigation Steps
### Quick mitigation (stop bleeding — SEV1)
[Steps]

### Full resolution
[Detailed steps]

## Rollback
[How to revert if mitigation worsens]

## Escalation
[When + who]

## Related
[Cross-links]
```

### 12AF.3 Layer 2 — Directory Structure + Auto-Index

Root: `docs/sre/runbooks/`

Organization by subsystem:
```
docs/sre/runbooks/
  INDEX.md                                # auto-generated; alert→runbook map
  README.md                               # how to use library
  TEMPLATE.md                             # skeleton for new runbook
  auth/
    token-flow-broken.md
    jwt-expiration-spike.md
    break-glass-initiation.md
  ws/
    refresh-failures.md
    connection-saturation.md
    mass-disconnect.md
  meta/
    failover-to-standby.md
    write-audit-hash-mismatch.md          # §12X.L6 auto-SEV0
    read-lag-investigation.md
  publisher/
    lag-spike.md
    dead-letter-queue-review.md
  projection/
    rebuild-catastrophic.md
    drift-detected.md
  llm-provider/
    outage-primary.md
    rate-limit-degradation.md
    cost-anomaly.md
  canon/
    injection-detected.md                 # S13 auto-SEV1
    propagation-latency-high.md
  admin/
    user-erasure-dispute.md
  fleet/
    reality-db-failover.md
    backup-restore-drill.md               # R4 / §12D
    subtree-split-kickoff.md              # §12N
  queue/
    abuse-cooldown-override.md            # S7
  cost/
    platform-budget-exhaustion.md         # S6
  rpc/
    service-acl-denial-spike.md           # S11
    mtls-certificate-rotation-failure.md
  tenant/
    noisy-neighbor-investigation.md       # SR1-D4
  generic/
    i-don-t-know-what-s-wrong.md
    new-on-call-first-day.md
    escalation-chains.md
```

**Index generation:** `scripts/gen-runbook-index.sh` scans all frontmatter, generates:
- Alphabetical index
- Alert → runbook map (for fast 3am lookup)
- Service → runbooks map
- Overdue-verification list (next_verification_due < today)
- Recently-updated list

CI hook runs on every PR touching `docs/sre/runbooks/`; `INDEX.md` always committed current.

**Storage:** git primary; read-only mirror in Notion/Confluence per SR2-D10.

### 12AF.4 Layer 3 — Required Minimum Runbook Set (V1)

**27 runbooks** must exist before V1 production cutover:

| Subsystem | Count | Runbooks |
|---|---|---|
| auth | 3 | token-flow-broken, jwt-expiration-spike, break-glass-initiation |
| ws | 3 | refresh-failures, connection-saturation, mass-disconnect |
| meta | 3 | failover-to-standby, write-audit-hash-mismatch, read-lag-investigation |
| publisher | 2 | lag-spike, dead-letter-queue-review |
| projection | 2 | rebuild-catastrophic, drift-detected |
| llm-provider | 3 | outage-primary, rate-limit-degradation, cost-anomaly |
| canon | 2 | injection-detected, propagation-latency-high |
| admin | 1 | user-erasure-dispute |
| fleet | 3 | reality-db-failover, backup-restore-drill, subtree-split-kickoff |
| queue | 1 | abuse-cooldown-override |
| cost | 1 | platform-budget-exhaustion |
| rpc | 2 | service-acl-denial-spike, mtls-certificate-rotation-failure |
| tenant | 1 | noisy-neighbor-investigation |
| generic | 3 | i-don-t-know-what-s-wrong, new-on-call-first-day, escalation-chains |

**V1 gate**: every SEV0-capable alert must have a runbook OR explicit escalation fallback annotation (`applies_to_alerts: [alert_x]` in `generic/escalation-chains.md`). CI lint checks completeness.

### 12AF.5 Layer 4 — Verification Protocol

Each runbook has `last_verified` + `next_verification_due` (default +90d).

Verification methods (declared in frontmatter):

| Method | Depth | Typical use |
|---|---|---|
| `reading_review` | Owner + one other read + validate accuracy against current code/architecture | Baseline; most runbooks |
| `tabletop` | Team walks through scenario verbally; timed | Top-10 runbooks quarterly |
| `chaos_drill` | Actually trigger condition in staging, follow runbook end-to-end | SR7 chaos engineering integration |

Overdue detection:
- `scripts/overdue-runbook-check.sh` (weekly cron) posts list to Slack #sre channel
- Items overdue > 30d flagged in monthly metrics review (SR2-D8)
- Overdue runbook cannot be referenced by a new alert in CI check (fail PR)

### 12AF.6 Layer 5 — Drift Detection (3 mechanisms)

**1. Alert-change lint** — PRs modifying `alerts/*.yaml` must update `applies_to_alerts` in affected runbook frontmatter. CI: `alert-runbook-sync-check.sh`.

**2. Service-change lint** — PRs modifying `contracts/service_acl/matrix.yaml` OR `contracts/api/*` scan all runbooks for references to changed services/endpoints; CI annotates affected runbooks in PR description with "⚠️ Runbook review needed" — does not block merge but signals for post-merge followup.

**3. Dead-reference scanner** — `scripts/runbook-deadref.sh`:
- Nonexistent service references (cross-check `contracts/service_acl/matrix.yaml`)
- Nonexistent table references (cross-check migration files)
- Nonexistent metric references (cross-check Prometheus registry)
- Broken markdown links

Runs on every PR touching `docs/sre/runbooks/`; failure blocks merge.

### 12AF.7 Layer 6 — Dry-Run First + Canned Commands

Every destructive command in a runbook MUST:
1. Show dry-run variant FIRST
2. Show expected output sample
3. Require explicit confirmation step before execution
4. Reference admin command's S5 tier (from ADMIN_ACTION_POLICY)

Example:

```markdown
### Step 3: Failover meta registry to standby

First, dry-run:
```bash
admin-cli meta failover \
  --from-primary=prod-meta-a \
  --to-standby=prod-meta-b \
  --dry-run
```

Expected output:
```
Would failover primary → standby
Estimated unavailability: ~3 seconds
Would update reality_registry.meta_host for 847 realities
Would invalidate EntityStatus cache
```

If output correct, execute without --dry-run. Requires S5 Tier 1 dual-actor.
```

CI lint `runbook-destructive-check.sh`:
- Scans for destructive command patterns: `admin-cli.*(drop|delete|purge|force|break-glass|canonize|decanonize|reset|failover)`
- Each occurrence must be preceded by `--dry-run` example within same code fence
- Exception: command explicitly lacking dry-run mode → frontmatter `dry_run_not_available: true` + justification comment required
- Violations block PR

### 12AF.8 Layer 7 — Generic / Diagnostic Runbooks

Three required catch-all runbooks for ambiguous situations:

**`generic/i-don-t-know-what-s-wrong.md`** — triage decision tree:
```
1. Check SLO dashboard — which SLI is degraded?
2. Check `incidents` table — any open SEV0/SEV1?
3. Check recent deploys (last 1h)
4. Check external dependency status (LLM providers, AWS, Vault)
5. Check error rate per service
6. If still unclear → escalate per escalation-chains.md
```

**`generic/new-on-call-first-day.md`** — orientation:
- Platform architecture diagram reference
- Access acquisition: PagerDuty, Grafana, AWS console, Slack, incident war rooms
- Who to ask for orientation (tech lead, outgoing on-call)
- "If paged in first week, page secondary + tech lead immediately" rule
- Essential reading list: SR1 SLOs, SR2 severity matrix, top-5 most-fired alerts' runbooks

**`generic/escalation-chains.md`** — fallback chains per SR2-D3:
- This-week rotation (references PagerDuty, not hardcoded)
- Fallback chain timing (TTA thresholds)
- Out-of-band contacts: founder phone, external legal counsel, AWS support case URL, vendor escalation contacts

### 12AF.9 Layer 8 — External Access Inventory

Runbooks declare access requirements in frontmatter:
```yaml
external_access_needed:
  - aws_cloudwatch_logs
  - grafana_ws_dashboard
  - pagerduty_admin
  - vault_read_secret_db_prod
```

Central inventory: `docs/sre/access-inventory.md`:

| Access token | Grants | Acquisition | Fallback if system down |
|---|---|---|---|
| `aws_cloudwatch_logs` | Read CloudWatch | SSO via Okta | Break-glass per §12AA.L10 |
| `grafana_ws_dashboard` | Read WS metrics | SSO | Local Prometheus scrape instructions |
| `pagerduty_admin` | Modify incidents / rotations | PagerDuty SSO | Founder phone + external PagerDuty support |
| `vault_read_secret_db_prod` | Read DB creds | SVID-based (§12AA.L6) | Physical safe V2+; break-glass now |

**Access resilience protocol:**
- Break-glass (§12AA.L10) is escape hatch when auth-service is itself the incident
- `admin/break-glass-initiation.md` runbook documents exact flow
- V2+ physical safe at workspace for root credentials (founder + second key-holder)

### 12AF.10 Layer 9 — Post-Incident Runbook Update

SR2 postmortem process (future SR4) MUST include runbook-specific questions:
1. Was an existing runbook used? Which?
2. Was it accurate? What went wrong?
3. Should a new runbook exist for this scenario?
4. What runbook reference was missing / wrong?

Action items from these questions land in `incidents.action_items` jsonb per SR2-D7.

**Runbook origin tracking:** frontmatter field `born_from_incident_id: <uuid>` (optional) links runbook to the incident that created it. Real-incident-born runbooks are highest-signal; library grows organically.

**Review during weekly SR2-D8:** open action items on runbook updates tracked; stale items (>30d) flagged.

### 12AF.11 Layer 10 — Accessibility Constraints

Per SR2-D10 (infrastructure independence):

| Constraint | Implementation |
|---|---|
| Readable without prod auth | Git repo via GitHub clone (no LoreWeave auth needed) |
| Always local | On-call shift-start rule: `git pull` runbook repo |
| Mirror for git outage | Daily cron exports to Notion/Confluence read-only view |
| Fast lookup | `INDEX.md` auto-generated with alert → runbook map |
| Emergency paper copies | V2+ when team has physical workspace: printed top-10 runbooks |
| Universal format | Plain markdown; no proprietary viewer required |
| No JavaScript required | Runbooks readable via any text editor / terminal |

**On-call startup ritual** (in `new-on-call-first-day.md` + weekly during handoff):
1. `git pull` runbook repo (always start of shift)
2. Read SR2-D8 weekly review thread for current week
3. Review `incidents` table for open SEV0/SEV1
4. Confirm working access: PagerDuty, Grafana, Vault
5. Ready.

### 12AF.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| SR1-D6 | Every alert links to runbook; runbook library is the link target |
| SR2-D4 | Incident lifecycle `triaged` state: IC + fixer read relevant runbook |
| SR2-D6 | Comms templates + runbook invocation are companion |
| SR2-D8 | Weekly review includes overdue-runbook list |
| SR2-D10 | Runbook accessibility requirements |
| SR4 (future) | Postmortem → runbook update flow via action_items |
| SR7 (future) | Chaos drills empirically verify runbooks |
| §12A–§12AE | Each section's alerts → runbooks in library |
| ADMIN_ACTION_POLICY | Runbooks reference admin command S5 tiers + dry-run requirements |
| §12AA.L10 (break-glass) | `admin/break-glass-initiation.md` is the definitive runbook |
| §12X.L6 (audit hash chain) | `meta/write-audit-hash-mismatch.md` is SEV0 runbook |
| §12AC.L9 (canon injection) | `canon/injection-detected.md` is SEV1 runbook |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| 27 runbooks before V1 cutover = significant writing | Alert library can't function per SR1-D6 without runbook targets; V1 ops readiness demands it |
| 90-day verification overhead | Drift is real; stale runbooks at 3am are worse than no runbook |
| Strict dry-run rule slows some runbooks | Safety > speed; destructive commands in prod are blast-radius decisions |
| Auto-generated INDEX.md churns with every PR | Bounded diff; bot-friendly; low code-review noise |
| Notion mirror = duplicated storage | Availability during git outage non-negotiable |
| Plain markdown (no fancy tooling) | Universal format; works on any device during 3am emergency |

**What this resolves:**

- ✅ **Scattered knowledge** — L1 schema + L2 directory
- ✅ **No alert→runbook mapping** — L2 auto-index + L5 drift detection
- ✅ **No verification cadence** — L4 90d + methods
- ✅ **Silent drift** — L5 three lints
- ✅ **Destructive command accidents** — L6 dry-run-first + CI lint
- ✅ **Ambiguous incidents** — L7 generic triage runbooks
- ✅ **Post-incident learning lost** — L9 action-item flow
- ✅ **External access confusion** — L8 inventory + break-glass fallback
- ✅ **New on-call lost** — L7 `new-on-call-first-day.md`
- ✅ **Production-dependent accessibility** — L10

**V1 / V1+30d / V2+ split:**

- **V1 (required before production cutover)**:
  - L1 schema finalized; L2 directory + auto-index; L3 all 27 runbooks written
  - L4 baseline `reading_review` for each; L5 all three CI drift lints; L6 dry-run CI lint
  - L7 generic runbooks; L8 access inventory
  - L10 accessibility + on-call startup ritual
- **V1+30d**:
  - L4 tabletop exercises scheduled for top-10 runbooks
  - L9 runbook-update workflow refined after first incidents
- **V2+**:
  - L4 chaos drill integration via SR7
  - Printed emergency copies at team workspace
  - Runbook ownership distributed as team grows
  - Runbook version-diffing UI; effectiveness metrics (MTTR by runbook used vs not)
  - AI-assisted runbook authoring from postmortems

**Residuals (deferred)**:
- V2+ runbook version-diffing UI
- V2+ runbook effectiveness metrics (MTTR correlation)
- V2+ AI-assisted runbook drafting from postmortem input
- V3+ adaptive runbooks (suggest next step based on telemetry)

