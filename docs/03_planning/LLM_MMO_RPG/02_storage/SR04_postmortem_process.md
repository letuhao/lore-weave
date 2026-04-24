<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: SR04_postmortem_process.md
byte_range: 430312-447248
sha256: 09b6a8c18734128cf323c1bbb33490385ebf63a678af3721a006387ec88b6e0e
generated_by: scripts/chunk_doc.py
-->

## 12AG. Postmortem Process — SR4 Resolution (2026-04-24)

**Origin:** SRE Review SR4 — SR2-D8 declared postmortem triggers; S11.L10 + S13 + §12X.L6 mandate postmortems for specific triggers; SR3-D9 references postmortem→runbook workflow. But the postmortem process itself — template, authorship, review, action items, pattern detection — was undesigned.

### 12AG.1 Problems closed

1. No canonical template
2. "Blameless" as slogan without enforcement mechanism
3. Authorship ambiguity
4. Review workflow undefined
5. Action item tracking incomplete (schema + lifecycle missing)
6. Time-boxing absent → indefinite drift
7. Root cause vs contributing factors conflated
8. Pattern detection across postmortems absent
9. Public/private conflation (security, legal, customer)
10. Postmortem theater (written but not read)
11. Meta-review of process itself missing

### 12AG.2 Layer 1 — Canonical Postmortem Template

Location: `docs/sre/postmortems/TEMPLATE.md`

Mandatory sections (CI lint enforces):
- **Metadata** — incident_id, severity, timestamps, TTA, MTTR, author, co-authors, review status, root cause category
- **Executive Summary** — single paragraph, stakeholder-level
- **Impact** — users/realities/SLIs affected, financial impact, data integrity status
- **Timeline** — UTC timestamps, facts-only, no interpretation
- **Detection** — how detected, timeliness, monitoring gaps
- **Root Cause Analysis** — three sub-sections: immediate cause / root cause / contributing factors
- **What Went Well** — learning from success
- **What Went Wrong** — systemic failure modes (NO names)
- **Action Items** — tracked in `incidents.action_items` jsonb, referenced here for readability
- **Appendix** — audit refs, runbooks used, runbooks-that-should-have-existed, related postmortems, communication log

CI lint: `postmortem-structure-check.sh` validates mandatory sections present + metadata complete.

### 12AG.3 Layer 2 — Blameless Culture Mechanisms (enforceable)

"Blameless" becomes enforceable only with concrete rules:

**No-name rule** in Root Cause Analysis + What Went Wrong:
- Individuals never named
- Use system/process/role language

**Reframing examples** (in TEMPLATE.md):
- ❌ "Alice deployed a bad config"
- ✅ "The deployment system merged a config change without config-validation tests; the change was caught post-deploy by error rate alerts"

- ❌ "Bob missed the alert"
- ✅ "The alert was routed to on-call via PagerDuty but escalation-to-secondary didn't fire within TTA; the fallback chain (SR2-D3) had a misconfiguration"

**Review gate checklist** (L4 state transition requires):
- [ ] Blameless language check passed
- [ ] No individual names in Root Cause / What Went Wrong
- [ ] System/process framing throughout

**Quarterly blameless audit:** tech lead + senior eng review 10% sample of published postmortems for blameless violations; findings in quarterly review; repeat violations trigger process retraining.

**"Humans Involved" appendix section** (optional): roles (IC, Fixer, Secondary, etc.), NOT names — preserves transparency about who held which role without blame.

### 12AG.4 Layer 3 — Authorship + Ownership

| Severity | Primary author | Co-authors expected |
|---|---|---|
| SEV0 | IC | Fixer + tech lead (3-author) |
| SEV1 | IC | Fixer (2-author) |
| SEV2 | Fixer (self-IC) OR IC if assigned | Optional |
| SEV3 | Voluntary | — |

**Backup authorship:** IC unavailable during drafting window → tech lead assigns backup within 2 days; `incidents.postmortem_author` updated via MetaWrite.

**V1 solo-dev reality:** same human writes alone. Guideline documented:
- Self-review at 48h (sit on draft; re-read with fresh eyes)
- External mentor review if available
- Use time-boxed deadline to force output; imperfect-published > perfect-in-draft-forever

### 12AG.5 Layer 4 — Review Workflow (5-state)

```
draft ──→ review ──→ approved ──→ published ──→ closed
```

| State | Entry | Exit criteria |
|---|---|---|
| `draft` | Author starts writing | All mandatory sections complete + self blameless check |
| `review` | Submitted for review | 2+ reviewers sign off + blameless check passes + technical accuracy verified |
| `approved` | All reviewer sign-offs | Review comments addressed + legal review if trigger met |
| `published` | Written to `docs/sre/postmortems/<yyyy>/<incident_id>_<slug>.md` + linked from `incidents.postmortem_doc_path` | Shared to team channel; announced in weekly review |
| `closed` | All action items ticketed + owners assigned + at least `in_progress` | Terminal |

**Review SLA:**
- SEV0/SEV1: reviewer turnaround 3 days; published within **14d** of resolution
- SEV2: reviewer turnaround 7 days; published within **21d**

**Transition audit:** `incidents.postmortem_review_state_history` jsonb (NEW column):
```json
[
  {"from": "draft", "to": "review", "ts": "...", "actor": "user_ref_id", "notes": "..."},
  ...
]
```

**Legal review trigger** (`approved` state):
- SEV0 + any data integrity / breach / security-tagged incident → legal review mandatory
- Legal review in separate Slack channel `#postmortem-<id>-legal` (restricted membership)

**V1 solo-dev review fallback:** "2+ reviewers" reads as "self-review + 48h-sit-then-re-read + external mentor review if accessible". Documented as V1 pattern, not exception.

### 12AG.6 Layer 5 — Action Item Schema + Lifecycle

Extends `incidents.action_items` jsonb (SR2-D7):

```json
[
  {
    "id": "uuid",
    "title": "Add runbook for auth-service config drift detection",
    "description": "Long-form description...",
    "owner": "user_ref_id",
    "priority": "high|medium|low",
    "category": "runbook|code|config|process|training|tooling|monitoring|documentation",
    "ticket_ref": "LINEAR-1234",
    "due_date": "2026-05-01",
    "status": "open|in_progress|completed|wontfix|superseded",
    "created_at": "2026-04-24T14:00:00Z",
    "completed_at": null,
    "completed_by": null,
    "superseded_by": null,
    "notes": "..."
  }
]
```

**Lifecycle scanning (weekly SR2-D8 review):**

| State | Check | Action |
|---|---|---|
| `open` approaching due_date (≤7d) | Owner reminder via Slack DM | — |
| `open` overdue >14d | Flagged in weekly review | Owner must justify or reassign |
| Any non-terminal state, stale >90d (no status update) | Re-triage | Still needed? Reassign? Close as `wontfix`? |
| Any non-terminal state >180d (ghost) | Auto-close as `superseded` with note | Preserves audit; removes from active list |

**Monthly metrics:**
- Completion rate per severity
- Category distribution (runbook / code / config / ...)
- Average time-to-completion per priority
- Decay rate (items becoming stale)

**Ticket integration (V2+):** Linear/Jira sync — `incidents.action_items[].status` mirrors ticket state via webhook or daily cron. V1 manual update acceptable.

### 12AG.7 Layer 6 — Time-Boxed Deadlines

| Severity | First draft deadline | Published deadline | Slip escalation |
|---|---|---|---|
| SEV0 | 7 days | 14 days | 80% (11.2d): notify IC + tech lead. 100% (14d): escalate to founder |
| SEV1 | 7 days | 14 days | Same as SEV0 |
| SEV2 | 14 days | 21 days | 80% (16.8d): remind author. 100% (21d): flag in weekly review |
| SEV3 | Optional | Optional | If in-progress: apply SEV2 rules |

**Enforcement:**
- `scripts/postmortem-deadline-check.sh` daily cron queries `incidents` table for in-flight postmortems
- Emits warnings for slipping ones (80% threshold = Slack reminder; 100% = PagerDuty page to tech lead)
- DF11 dashboard "Postmortem Pipeline" view shows all in-flight + days-to-deadline + status

**Publication iteration policy:** "Publish 70% complete + iterate than 0% perfect." `metadata.publication_iteration` field tracks updates (v1, v2, v3) after publication.

**Slip metrics:** reviewed monthly; persistent slippage → process improvement action in quarterly review.

### 12AG.8 Layer 7 — Root Cause Classification (pattern detection)

New column: `incidents.root_cause_category` (TEXT, enum value; populated at postmortem `published` state).

Enum values:

| Category | Meaning |
|---|---|
| `system_allowed_human_action` | Human did X; system made X easy/obvious (blameless-reframed) |
| `deploy_induced` | New deploy directly caused incident |
| `config_drift` | Dev/staging/prod config mismatch |
| `capacity_exhaustion` | Load exceeded provision (DB conn, LLM budget, WS conn, queue depth) |
| `external_dependency` | LLM provider / AWS / Vault / external service degradation |
| `data_corruption` | Event / projection / canon data inconsistency |
| `security_event` | Linked to S1-S13 trigger |
| `monitoring_gap` | Alert missing / late / misrouted |
| `runbook_gap` | No runbook for scenario; ad-hoc response |
| `cascading_failure` | One root cause triggered chain across services |
| `change_management_failure` | Process gate (review, rollback, canary) missed/bypassed |
| `unknown_still_investigating` | Provisional; revised when investigation completes |

**Quarterly pattern analysis** (`docs/sre/incident-reviews/<yyyy>-Q<N>_patterns.md`):
- Top 3 categories → systemic investment priorities
- Category drift quarter-over-quarter
- **Pattern alert: "same category appears 5× in quarter" → auto-declares SEV2 preventive incident** to investigate systemic risk proactively

Preventive incidents:
- Severity: SEV2
- Classification: same as the recurring pattern
- Goal: identify + fix the systemic root cause before more incidents
- Owner: tech lead (not on-call)

### 12AG.9 Layer 8 — Postmortem Variants (public/private)

| Variant | Audience | Content | V1 status | Storage |
|---|---|---|---|---|
| **Internal Full** | All staff + read-only contractors | Complete per L1 template | ✅ V1 | `docs/sre/postmortems/<yyyy>/` |
| **Security-Restricted** | Security team + tech lead + legal | Full + attack vectors, compromised creds, forensic detail | ✅ V1 | `docs/sre/postmortems/<yyyy>/security-restricted/` (CODEOWNERS limited; git LFS or private repo V2+) |
| **Customer-Facing Summary** | Public via status page blog | Sanitized: what happened, who affected, what we did, what we're changing. **NO** names / internal tooling / credentials | 📦 V2+ (monetization) | Public blog / status page |
| **Regulator-Facing** | Legal + DPA | GDPR Art. 33 facts-only breach notification | 📦 V2+ | Internal legal archive |

**Sanitization process** (V2+ Customer-Facing):
- IC (or designated author) writes sanitized version from approved Internal Full
- Legal review
- Publishes via status-page-admin CLI (S5 Tier 2)

**Regulator-facing (V2+ GDPR):** separate template meeting regulatory schema; 72h deadline per SR2-D9 fast-path.

### 12AG.10 Layer 9 — Sharing + Learning

**Weekly (SR2-D8 integration):**
- Published-this-week postmortems listed in review
- SEV0/SEV1: 20-minute discussion per postmortem
- SEV2: summary-only unless novel

**Monthly "Postmortem Hour" (V1+30d):**
- Team reads 1-2 postmortems together (rotating author explains)
- Focused learning: "what would we do differently?"
- 60-min meeting; notes in `docs/sre/postmortem-hour-<yyyy-mm-dd>.md`

**Quarterly cross-review:**
- L7 pattern analysis
- Theme retrospective
- Process adjustments

**Archive + searchability:**
- All postmortems at `docs/sre/postmortems/<yyyy>/` — git-indexed
- Tagged by category, runbooks, audit refs
- `scripts/find-postmortems.sh --category=X --since=Y` CLI

**Runbook back-lookup:** each runbook's auto-generated metadata includes `used_in_incidents: [incident_id1, ...]` (populated from published postmortems that reference it). Enables "show me every incident this runbook was used in" queries.

### 12AG.11 Layer 10 — Annual Meta-Review

Annual postmortem of postmortem process itself. Questions:

1. Were postmortems written on time? (SLA compliance rate)
2. Are action items being completed? (per-category completion rates)
3. Is template effective? (too long? missing sections? clutter?)
4. Are blameless checks catching violations? (quarterly audit findings)
5. Is pattern detection working? (did L7 catch systemic issues that would have otherwise recurred?)
6. Is postmortem-hour generating learnings? (attendance, follow-through)
7. What fraction of incidents produced postmortems vs skipped?
8. Are customer-facing / regulator-facing variants (V2+) being produced when required?

Output: `docs/sre/postmortem-process-annual-review-<yyyy>.md` with process improvements proposed + tracked to completion.

### 12AG.12 Interactions + V1 split + what this resolves

**Schema additions to `incidents` table (SR2-D7):**

```sql
ALTER TABLE incidents
  ADD COLUMN root_cause_category         TEXT,           -- L7 enum
  ADD COLUMN postmortem_review_state     TEXT,           -- 'draft'|'review'|'approved'|'published'|'closed'
  ADD COLUMN postmortem_review_state_history JSONB,      -- L4 transitions
  ADD COLUMN postmortem_variant          TEXT,           -- 'internal_full'|'security_restricted'|'customer_facing'|'regulator_facing'
  ADD COLUMN postmortem_legal_review_required BOOLEAN DEFAULT false,
  ADD COLUMN postmortem_legal_review_approved_at TIMESTAMPTZ,
  ADD COLUMN postmortem_publication_iteration INT DEFAULT 1;

CREATE INDEX ON incidents (root_cause_category, declared_at DESC);
CREATE INDEX ON incidents (postmortem_review_state) WHERE postmortem_review_state NOT IN ('closed');
```

**Interactions:**

| With | Interaction |
|---|---|
| SR2-D7 `incidents` table | Schema extended with postmortem-specific columns |
| SR2-D8 review cadences | Postmortem deadline tracking + weekly review integration |
| SR3-D9 | "Runbooks that should have existed" → SR3 library growth; `born_from_incident_id` back-links |
| SR3-D4 | "Runbooks used" → informs verification priority |
| S11.L10 break-glass | Mandatory 7d postmortem per L6 deadlines |
| S13 canon injection | Auto-SEV1 postmortem required |
| §12X.L6 audit hash mismatch | Auto-SEV0 postmortem required |
| §12U (S5) | Legal review trigger on Tier 1 data incidents |
| ADMIN_ACTION_POLICY | Postmortem review workflow via CODEOWNERS |
| DF11 dashboard | Postmortem Pipeline view |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| Template discipline + CI lint | Prevents drive-by postmortems; ~1h overhead per postmortem |
| Time-boxing | Forces output; publication-iteration absorbs imperfection |
| 2+ reviewers aspirational for solo | V1 solo-dev pattern documented explicitly |
| Pattern alert at "5×/quarter" | May trigger preventive incidents that feel premature; better than silent drift |
| Security-restricted separate storage | Required for forensic sensitivity; CODEOWNERS adequate V1 |
| Legal review on SEV0 data incidents | Adds latency; required for GDPR compliance |

**What this resolves:**

- ✅ No canonical template — L1 + CI lint
- ✅ Blameless slogan — L2 mechanisms + review gate + quarterly audit
- ✅ Authorship ambiguity — L3 severity-based rules
- ✅ No review workflow — L4 5-state lifecycle
- ✅ Action item decay — L5 lifecycle scanning + stale/ghost detection
- ✅ Indefinite drift — L6 time-boxing + slip escalation
- ✅ Pattern detection absent — L7 category enum + quarterly analysis + auto-preventive-incident
- ✅ Public vs private conflation — L8 4 variants
- ✅ Postmortem theater — L9 weekly + monthly + quarterly consumption rituals
- ✅ Process effectiveness unknown — L10 annual meta-review

**V1 / V1+30d / V2+ split:**

- **V1**:
  - L1 template + CI lint
  - L2 blameless mechanisms + review gate
  - L3 authorship rules + V1 solo-dev pattern
  - L4 5-state workflow (self-review + 48h-sit fallback for solo)
  - L5 action item schema + weekly scan + stale/ghost detection
  - L6 deadline enforcement + daily cron
  - L7 category enum + quarterly analysis + preventive-incident trigger
  - L8 Internal Full + Security-Restricted variants
  - L9 weekly review integration + archive
  - L10 annual meta-review scheduled
- **V1+30d**: L9 monthly Postmortem Hour starts; V1 solo-dev pattern refined after first few incidents
- **V2+**:
  - L8 Customer-Facing Summary at monetization
  - L8 Regulator-Facing for GDPR Art. 33
  - L5 ticket-system webhook integration (Linear/Jira)
  - AI-assisted draft generation from `incidents` data

**Residuals (deferred):**
- V2+ customer-facing summary publishing pipeline
- V2+ regulator notification templates (GDPR/CCPA)
- V2+ ticket-system webhook integration
- V3+ AI-assisted postmortem drafting
- V3+ postmortem effectiveness metrics (correlation: quality vs repeat-incident rate)

