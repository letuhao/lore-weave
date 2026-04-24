<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: SR02_incident_oncall.md
byte_range: 395002-414170
sha256: 0a0ebacbea356d309828f625e45bd07001f5a7d0d2a48133a29bc28e55e7550f
generated_by: scripts/chunk_doc.py
-->

## 12AE. Incident Classification + On-Call Rotation — SR2 Resolution (2026-04-24)

**Origin:** SRE Review SR2 — SR1 gave us SLOs + error budgets; SR2 gives us the runway for "when error budget is burning, what does the team actually do at 3am". §12A–§12AD alerts all say "PAGE SRE" without rotation, severity matrix, IC role, or lifecycle state machine defined.

### 12AE.1 Problems closed

1. Severity undefined — all PAGEs treated identically
2. No rotation, no escalation chain
3. Alert routing blind (security alerts land on SRE, not security on-call)
4. Incident lifecycle states absent
5. Incident Commander (IC) role vs fixer role undifferentiated
6. War room + comms procedures ad hoc
7. Customer comms under pressure → bad copy
8. No `incidents` tracker; postmortems reference nothing durable
9. GDPR Art. 33 72h breach notification has no defined flow
10. Incident comms depend on prod stack (circular if prod is the incident)
11. Hobby-project reality (solo dev) not honestly reflected

### 12AE.2 Layer 1 — Severity Matrix

4 severity levels with concrete criteria, time-to-acknowledge (TTA), comms obligations:

| Severity | Criteria | TTA | Comms | IC Required |
|---|---|---|---|---|
| **SEV0** | Platform-wide outage (no logins / no turns) OR confirmed data integrity event (corruption, breach, unauthorized canon mutation, audit hash mismatch per §12X.L6) | **5 min** | War room + status page auto-banner + every-30-min update | **Yes** (separate from fixer) |
| **SEV1** | Major feature down for majority of a tier OR SR1 error budget burn ≥90% (freeze-trigger) OR security finding from S13.L9 OR break-glass (§12AA.L10) invoked | **15 min** | War room + status page + every-60-min update | **Yes** |
| **SEV2** | Material impact, limited scope (single reality crash, LLM provider degraded, meta lag, queue saturation) | **30 min** | Slack thread; status page if user-visible | Optional |
| **SEV3** | Minor impact, bounded workaround (non-critical feature degraded, dashboard metric off) | **2 hours** | Ticket only | No |

**Auto-escalation rules:**
- Data integrity incident → auto-SEV0 regardless of initial classification
- Canon injection detected (§12AC.L9) → auto-SEV1
- Audit hash mismatch (§12X.L6) → auto-SEV0
- Personal data breach (confirmed or suspected) → auto-SEV0 (L9 fast-path)

Severity changes during incident recorded in `incidents.severity_history` jsonb (L7).

### 12AE.3 Layer 2 — On-Call Rotation Structure

| Rotation | Cadence | Scope | V1 (solo) | V1+30d (2-person) | V2+ (team) |
|---|---|---|---|---|---|
| SRE primary | 7d shift | Default alert target | Solo dev | Alternating weekly | Weekly rotation |
| SRE secondary | 3d overlap | Busy periods, handoff | — | Partner on-call | Rotation |
| Security on-call | 14d shift | S1-S13 triggers, break-glass, privacy breach | Solo dev ("security hat") | Dedicated pair | Separate rotation |
| Data on-call | 14d shift | Meta HA, backup, migration | Solo dev | Solo dev | Dedicated DBA |

**Weekend coverage:** primary through weekend; secondary backup if unreachable. **V1 solo reality explicitly documented:** "weekend response time degrades to 4h non-SEV0; SEV0 still 5 min TTA." Honesty > false SLA.

**Timezone:** V1 primary in founder's timezone (UTC+7). Follow-the-sun V2+ when team spans >2 timezones.

**Handoff protocol:** outgoing writes `docs/sre/oncall-handoffs/<yyyy-mm-dd>_<from>_to_<to>.md`:
- Open incidents + status
- Active SLI burn rates
- Known blips expected this week
- Anything unusual observed

Incoming ack via reply + Slack confirmation.

### 12AE.4 Layer 3 — Alert Routing + Fallback Chain

Routing table (extends SR1-D6 schema):

| Alert pattern | Primary rotation | Fallback chain |
|---|---|---|
| `lw_ws_*` | SRE primary | SRE secondary → tech lead |
| `lw_auth_*` | Security on-call | SRE primary → tech lead |
| `lw_meta_*`, `lw_projection_*` | Data on-call | SRE primary → tech lead |
| `lw_canon_injection_*` | Security on-call | SRE primary + tech lead **parallel** |
| `lw_cost_*`, `lw_budget_*` | SRE primary | Finance lead (V2+) |
| `lw_rpc_*`, `lw_service_*` | SRE primary | Tech lead |
| `lw_audit_hash_mismatch` (§12X.L6) | Security on-call | Tech lead (auto-SEV0) |
| `lw_incident_*` (meta-alerts on incident process) | SRE primary | Tech lead |
| default | SRE primary | Tech lead |

Fallback chain (PagerDuty or equivalent):
1. Primary paged; TTA window starts
2. Not ack'd in TTA → secondary paged
3. Secondary not ack'd in TTA → tech lead
4. Tech lead not ack'd in 2× TTA → PagerDuty manager / founder's direct phone

Alert yaml schema extends SR1-D6:

```yaml
alert: lw_ws_refresh_failures_high
sli_ref: sli_auth_success
derivation_rule: "..."
runbook: runbooks/ws/refresh-failures.md
# SR2 additions:
severity_map:
  default: sev2
  escalate_to_sev1_if: "burn_rate >= 0.9"
  escalate_to_sev0_if: "correlates_with_data_integrity_alert"
routing:
  primary: sre_oncall
  fallback: [sre_secondary, tech_lead]
```

CI lint (`scripts/slo-alert-lint.sh`) enforces `severity_map` + `routing` on every alert (extended from SR1-D6).

### 12AE.5 Layer 4 — Incident Lifecycle States

```
declared ──→ triaged ──→ mitigated ──→ resolved ──→ postmortem ──→ closed
                │            │             │             │
                │ IC         │ User        │ Root        │ Action
                │ assigned   │ impact      │ cause       │ items
                │ severity   │ stopped     │ fixed       │ ticketed
                │ confirmed  │             │             │
```

| State | Entry trigger | Exit criteria |
|---|---|---|
| `declared` | Alert auto-declares SEV1+ OR manual declaration via `admin/declare-incident` OR customer report | IC assigned; severity confirmed |
| `triaged` | IC assigned (may upgrade/downgrade severity) | Impact + scope established |
| `mitigated` | User impact stopped (failover, rollback, circuit breaker, feature flag) | Users no longer affected; root cause may still unknown |
| `resolved` | Root cause fixed; no expected recurrence | Verified in prod for 2h at SEV0/SEV1 |
| `postmortem` | SEV≥2 per triggers; postmortem in progress | Postmortem published + action items ticketed |
| `closed` | Action items have tickets + owners | Terminal state |

Transition rules:
- SEV0/SEV1 CANNOT skip `postmortem` state
- SEV2 skips `postmortem` unless L8 triggers met
- SEV3 goes `declared → triaged → resolved → closed` (no mitigated distinct from resolved; no postmortem)

Each transition stamped with actor + timestamp in `incidents` table (L7).

### 12AE.6 Layer 5 — Incident Commander (IC)

**IC ≠ fixer.** IC coordinates; fixer investigates + executes.

IC responsibilities:
- Own incident comms (status page, Slack updates, stakeholder notifications)
- Maintain timeline (events, decisions, attempts)
- Assign subordinate roles (ops lead, comms lead, scribe) if complex
- Call status updates at cadence per severity
- Declare mitigation + resolution transitions (fixer can't self-declare "done")
- Hand off if shift exceeds 4h

| Severity | IC required | Notes |
|---|---|---|
| SEV0 | Yes | IC + fixer + comms lead (minimum 3 roles) |
| SEV1 | Yes | IC + fixer (minimum 2 roles) |
| SEV2 | Optional | Fixer can self-IC if narrow scope |
| SEV3 | No | n/a |

**Handoff protocol (>4h incidents):**
- Outgoing IC writes handoff doc: timeline, current hypothesis, active investigators, next decision points, open questions
- Incoming IC reads + asks clarifying questions
- Slack `#inc-<id>` channel notified: `IC handoff: A → B at <ts>`
- `incidents.incident_commander` updated via MetaWrite

**V1 solo-dev reality documented:** same person plays IC + fixer. Guideline: *"Slow down to document timeline even if you're alone — your future self and postmortem depend on it."*

### 12AE.7 Layer 6 — Communication Protocol

| Artifact | SEV0 | SEV1 | SEV2 | SEV3 |
|---|---|---|---|---|
| Slack war room `#inc-<id>` | Auto-created on declare | Auto-created | On-demand | No |
| Zoom/Meet bridge | Auto-linked in channel topic | Auto-linked | On-demand | No |
| Status page update | Auto-banner | Auto-banner | If user-visible | No |
| Update cadence | Every 30 min | Every 60 min | Adhoc | On resolve |
| Stakeholder notify (tech lead + founder) | Immediate | Immediate | Within 1h | Weekly review |

**Update templates** — avoid free-text drafting under pressure. Stored at `docs/sre/incident-comms-templates/`:

- `declared.tmpl` — initial announcement
- `update.tmpl` — periodic updates during investigation
- `mitigated.tmpl` — impact bounded
- `resolved.tmpl` — root cause fixed
- `postmortem-published.tmpl` — postmortem link + action items
- `closed.tmpl` — final closure
- `status-page-banner.tmpl`
- `status-page-incident.tmpl`
- `status-page-resolved.tmpl`

Example `update.tmpl`:

```
INCIDENT UPDATE — {{incident_id}} — {{severity}}
Time: {{now_utc}} ({{minutes_since_declare}} min after declaration)
Status: {{state_transition}}
Impact: {{impact_summary}}
Current hypothesis: {{hypothesis}}
Next checkpoint: {{next_checkpoint_utc}}
IC: {{ic}} · Fixer: {{fixer}}
```

### 12AE.8 Layer 7 — `incidents` Tracker Table

```sql
CREATE TABLE incidents (
  incident_id             UUID PRIMARY KEY,
  declared_at             TIMESTAMPTZ NOT NULL,
  declared_by             UUID NOT NULL,              -- user_ref_id or NULL for 'system_alert'
  trigger_source          TEXT NOT NULL,              -- 'alert'|'manual'|'customer_report'|'security_finding'|'scheduled_maintenance'
  alert_name              TEXT,                       -- if trigger_source='alert'
  severity                TEXT NOT NULL,              -- 'sev0'|'sev1'|'sev2'|'sev3'
  severity_history        JSONB,                      -- [{ts, from, to, reason}]
  title                   TEXT NOT NULL,
  summary                 TEXT,                       -- scrubbed per §12X.5
  status                  TEXT NOT NULL,              -- lifecycle state per L4
  incident_commander      UUID,
  fixer_primary           UUID,
  triaged_at              TIMESTAMPTZ,
  mitigated_at            TIMESTAMPTZ,
  resolved_at             TIMESTAMPTZ,
  postmortem_published_at TIMESTAMPTZ,
  postmortem_doc_path     TEXT,                       -- docs/sre/postmortems/<id>.md
  closed_at               TIMESTAMPTZ,
  slack_channel           TEXT,
  war_room_bridge         TEXT,
  affected_sli            TEXT[],                     -- SR1 SLIs involved
  affected_reality_count  INT,
  affected_user_count     INT,
  related_audit_refs      JSONB,                      -- links to admin_action_audit, service_to_service_audit, etc.
  action_items            JSONB                       -- [{ticket_id, owner, due_date, status}] post-postmortem
);

CREATE INDEX ON incidents (severity, declared_at DESC);
CREATE INDEX ON incidents (status) WHERE status NOT IN ('closed', 'resolved');
CREATE INDEX ON incidents (declared_at DESC);
CREATE INDEX ON incidents (incident_commander) WHERE status NOT IN ('closed');
```

Location: meta DB. Retention: **5 years** (aligns §12T.5). Writes via MetaWrite (§12T.2) — incident records are audit-grade; tampering detected by audit hash chain (§12X.L6).

**PII classification:** `medium` — contains user_ref_id references, scrubbed summary; no raw user content.

### 12AE.9 Layer 8 — Review Cadences + Postmortem Triggers

| Cadence | Artifact | Outcome |
|---|---|---|
| Daily | Open SEV0/SEV1 status check by on-call | Force closure or continued daily cadence |
| Weekly | Review all active + closed-this-week incidents | Spot patterns; update runbooks |
| Monthly | Metrics review (count per sev, MTTA, MTTR, top causes, rotation load) | Rotation tuning, capacity signals |
| Quarterly | Full structural review (rotation, severity calibration, alert routing) | Adjust routing table + severity criteria |

**Postmortem triggers** (linked to SR4 when defined):
- SEV0: mandatory postmortem within **7 days**
- SEV1: mandatory postmortem within **7 days**
- SEV2: mandatory if MTTR > 1h OR root cause unknown — within **14 days**
- SEV3: optional; lessons captured in weekly review

All review docs in `docs/sre/incident-reviews/`; append-only.

### 12AE.10 Layer 9 — Privacy + Security Incident Fast-Paths

**Personal data breach (confirmed or suspected):**
- GDPR Art. 33: **72-hour notification** to DPA
- Auto-escalate to SEV0
- Security on-call primary
- Legal loop within **1h** (separate Slack channel `#inc-<id>-legal`, restricted membership)
- Breach notification decision within **48h** (buffer before 72h deadline)
- Status page delayed until legal green-light (prevents premature disclosure)
- Postmortem publication coordinated with legal

**Active attack in progress:**
- Break-glass (§12AA.L10) pre-authorized for Security on-call
- Exploitation-in-progress bypasses dual-actor delay (post-use rotation mandate still applies)
- SEV0; Security on-call IC; SRE primary assists
- Credentials touched during break-glass auto-rotate post-incident per §12AA.L10

**Canon injection detected (§12AC.L9):**
- Auto-SEV1
- Security on-call primary
- If injection in production canon affecting active sessions: auto-propose decanonization (still requires §12AC.L8 dual-actor approval, but proposal auto-filed in review queue)
- Affected realities receive §12AB.9 control channel event to active sessions
- SR4 postmortem obligation (canon is cross-reality — high-impact)

**Audit hash chain mismatch (§12X.L6):**
- Auto-SEV0 (tampering attempt)
- Security on-call; forensics team looped (V2+; V1 founder + advisor contact)
- Full audit trail snapshot immediately
- Do not touch source until forensics clear
- Break-glass available for investigation per §12AA.L10

### 12AE.11 Layer 10 — Communication Infrastructure Independence

Incident response infrastructure MUST NOT depend on LoreWeave production:

| Layer | Our service | Incident infra |
|---|---|---|
| Hosting | AWS ECS/RDS (our prod) | **External**: PagerDuty or equivalent (separate vendor); status page on separate stack (e.g., Cloudflare Pages) |
| Notifications | WS + SMTP in our prod | **External**: PagerDuty SMS/call + Slack; no dogfooding |
| Documentation | Could be behind our auth | Public-readable `docs/sre/` in git; runbooks accessible without production access |
| Runbooks | Git repo (accessible outside) | Plus read-only mirror in Notion/Confluence as backup |
| Status page | N/A | **External**: separately hosted per SR1-D7 |
| Incident tracker UI | DF11 dashboard reads `incidents` table | UI may be down during incident; `admin-cli entity-provenance` works from any env with vault + SVID |

**Forbidden:** "LoreWeave-native incident channel" built on our own WS. If our WS is the incident, we can't communicate.

**Runbook access resilience:** every runbook in both git (primary) + mirrored doc store (backup). On-call always has local clone + mirror access.

### 12AE.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| SR1 | Error budget burn ≥ 90% = auto-SEV1 declaration; `affected_sli` array references SR1 SLIs |
| SR4 (postmortem — future) | Lifecycle state `postmortem` triggers SR4 process; action items tracked in `incidents.action_items` |
| §12AA.L10 (break-glass) | Pre-authorized for Security on-call during active-attack SEV0; post-use rotation stays mandatory |
| §12X.L6 (audit hash chain) | Mismatch → auto-SEV0 security fast-path |
| §12AC.L9 (canon injection) | Detection → auto-SEV1 + auto-decanonization proposal in review queue |
| §12U (S5 admin tiers) | Status page manual updates = Tier 2 Griefing; `admin/declare-incident` = Tier 3 Informational (rapid response, low gating) |
| SR1-D7 status page | Shared infrastructure; incident-declared banners auto-publish |
| ADMIN_ACTION_POLICY | New `admin/declare-incident` command (Tier 3); `admin/update-incident-severity` Tier 2 |
| DF9 / DF11 | Incident dashboard in DF11; per-reality incident history in DF9 |
| §12T MetaWrite | `incidents` table writes audit-grade, append-only enforcement |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| Framework complexity for solo dev | Scales to team; retrofit later is painful; solo reality documented explicitly |
| External PagerDuty vendor dependency | Can't dogfood (circular); vendor lock-in acceptable for incident infra |
| Multiple specialty rotations V1 | Collapses to one person wearing multiple hats; explicit hats surface the mental mode switch |
| `incidents` in meta DB | Audit-grade belongs with other forensic data |
| Severity matrix subjectivity | Any matrix > none; quarterly review calibrates |
| 5-min SEV0 TTA aggressive for solo | Matches production outage urgency; weekend caveat documented; solo-dev realistic fallback = "founder's phone, direct" |

**What this resolves:**

- ✅ Severity undefined — L1 matrix with TTA + comms
- ✅ No rotation — L2 tiered structure scaling with team
- ✅ Unrouted alerts — L3 routing table + fallback
- ✅ No lifecycle — L4 6-state machine
- ✅ IC absent — L5 separate-from-fixer + handoff protocol
- ✅ Ad-hoc comms — L6 templates + cadence per severity
- ✅ No incident tracking — L7 `incidents` table
- ✅ Review cadence gap — L8 daily/weekly/monthly/quarterly
- ✅ GDPR 72h missing flow — L9 fast-path with legal loop
- ✅ Circular comms dependency — L10 external infrastructure mandate
- ✅ Canon injection response — L9 auto-SEV1 + auto-decanonization proposal
- ✅ Active attack break-glass pre-auth — L9

**V1 / V1+30d / V2+ split:**

- **V1 (solo-dev reality)**:
  - L1 severity matrix applied; V1 documents "you are primary + secondary + IC"
  - L2 "SRE + Security + Data hats" worn sequentially
  - L3 routing in config but all routes reach one human
  - L4 lifecycle tracked in `incidents` table
  - L5 IC = same human; still maintain timeline
  - L6 templates + status page (internal-only per SR1-D7)
  - L7 `incidents` table
  - L8 weekly review solo; monthly metrics
  - L9 privacy fast-path documented; legal contact = founder + external legal counsel on retainer
  - L10 PagerDuty + Cloudflare Pages status; external docs mirror V1+30d
- **V1+30d (2-person team)**:
  - Real rotation begins
  - Postmortem workflow hardened (SR4)
  - Mirror docs + runbook access drill
- **V2+ (full team)**:
  - Full rotation structure operational
  - On-call comp-time policy
  - Follow-the-sun if timezones span

**Residuals (deferred):**
- V2+ on-call compensation policy
- V2+ follow-the-sun rotation
- V3+ automated remediation (self-healing classes)
- Incident game-day / chaos drills → SR7
- External ticket tracker integration (Jira/Linear) — tool-dependent

