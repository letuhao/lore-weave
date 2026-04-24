<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S05_admin_command_classification.md
byte_range: 236842-247185
sha256: b4e91718984372f5ac730af6928d892dd7f6b0185afa454d510c7af30b6fb4ff
generated_by: scripts/chunk_doc.py
-->

## 12U. Admin Command Classification — S5 Resolution (2026-04-24)

**Origin:** Security Review S5 — R13-L4 had implicit two-tier model (dangerous vs not-dangerous). Many "non-destructive" commands can still grief users. Also unblocks S3 deferred admin-tier gating (V1+30d → V1 ready).

### 12U.1 Framing

§12L R13-L4 "Destructive action confirmation" covered truly dangerous operations (DROP, purge). Everything else was treated uniformly as "not dangerous." Gap:

Griefing-capable commands that aren't destructive:
- `admin/reset-npc-mood` on player's favorite NPC → disrupts active play
- `admin/compaction-trigger-npc` → forces LLM summary, may lose narrative detail
- `admin/freeze-reality` (non-emergency) → denies service to players
- `admin/restore-pair-archive` (wrong pair) → NPC gets wrong memory
- `admin/force-npc-leave-session` → breaks ongoing roleplay
- Edit player's canon-worthy L3 event

Each is REVERSIBLE but high-impact on users. Compromised admin account can grief widely without triggering "dangerous" gate.

### 12U.2 Three-tier impact class

**Single dimension** — what the command does. Authorization derived.

#### Tier 1 — Destructive

Irreversible data/service loss. Existing R13-L4 coverage.

Examples: `admin/force-close-reality`, `admin/manual-drop-database`, `admin/purge-user-data`, `admin/bypass-archive-verification`

Requirements:
- **Dual-actor** (double-approval) — different users, 24h cooldown
- Typed confirmation (reality name, etc.)
- Mandatory reason (**100+ chars**)
- Full R13-L4 treatment

#### Tier 2 — Griefing (NEW)

Material user impact, reversible via compensating events.

Examples: `admin/reset-npc-mood`, `admin/compaction-trigger-npc`, `admin/freeze-reality` (non-emergency), `admin/restore-pair-archive`, `admin/force-npc-leave-session`, `admin/edit-player-canon-event`

Requirements:
- **Single-actor** (standard admin auth)
- **Mandatory reason** (50+ chars, audited)
- **Affected-user notification** — "An admin performed X on your Y. Reason: [...]"
- **Enhanced audit** — entry flagged `reviewed = false` in `admin_action_audit`
- **Periodic review** — weekly by admin-ops manager
- Rollback preferred when feasible

#### Tier 3 — Informational (NEW)

Read-only OR self-scoped.

Examples: `admin/query-reality-stats`, `admin/view-npc-memory` (SELECT), `admin/export-session-history`, `admin/help`

Requirements:
- Single-actor (standard admin auth)
- Standard audit (R13-L3 default)
- No user notification
- No periodic review
- Optional reason

### 12U.3 Command metadata extension

Every admin command declares impact class at registration (R13-L1 extended):

```go
RegisterCommand(Command{
    Name: "admin/reset-npc-mood",
    Description: "Reset NPC's mood state to neutral",
    Keywords: []string{"reset", "npc", "mood", "stuck"},
    Category: "npc_state_ops",

    // S5 classification:
    ImpactClass: TierGriefing,           // 'destructive' | 'griefing' | 'informational'
    AffectsUsers: true,
    UserNotificationRequired: true,
    MinReasonChars: 50,
    Reversible: true,
    ReversibleBy: "admin/reset-npc-mood --undo",

    // Existing fields:
    DryRunSupported: true,
    Category: "npc_state_ops",
})
```

**Lint rule:** missing `ImpactClass` declaration fails CI.
**PR review:** reviewers verify classification correctness.

### 12U.4 Schema additions

```sql
-- Extend admin_action_audit with S5 fields
ALTER TABLE admin_action_audit
  ADD COLUMN impact_class TEXT NOT NULL DEFAULT 'informational',
    -- 'destructive' | 'griefing' | 'informational'
  ADD COLUMN reason TEXT,
  ADD COLUMN reason_length INT,
  ADD COLUMN reversible BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN reversed_by_audit_id UUID,      -- if this was a rollback
  ADD COLUMN reviewed BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN reviewed_by UUID,
  ADD COLUMN reviewed_at TIMESTAMPTZ,
  ADD COLUMN review_notes TEXT;

CREATE INDEX admin_action_audit_review_queue
  ON admin_action_audit (impact_class, reviewed, created_at)
  WHERE impact_class = 'griefing' AND reviewed = FALSE;

-- Join table for affected-user notification
CREATE TABLE admin_action_affects_user (
  audit_id        UUID NOT NULL REFERENCES admin_action_audit(audit_id),
  user_id         UUID NOT NULL,
  notified_at     TIMESTAMPTZ,
  acknowledged_at TIMESTAMPTZ,
  PRIMARY KEY (audit_id, user_id)
);
CREATE INDEX ON admin_action_affects_user (user_id, notified_at DESC);
```

### 12U.5 User notification for Griefing tier

When Tier 2 command affects a user's data:

```
📋 Admin activity on your account

Admin performed action: Reset NPC "Elena"'s mood state
Affected: Your active session in reality "Tavern of Broken Crown"
Reason: "Player reported NPC stuck in incorrect emotional state after recent event"
Time: 2026-05-15 14:23 UTC

[View full audit trail]
```

Delivery:
- Notification center (same channel as R9 notifications)
- Optional email (per user preference)
- User's personal audit at `/me/admin-activity`

### 12U.6 Periodic review

Griefing-tier entries reviewed weekly:

```sql
SELECT * FROM admin_action_audit
WHERE impact_class = 'griefing' AND reviewed = false
ORDER BY created_at;
```

Admin-ops manager reviews batch:
- Mark `reviewed = true` + add `review_notes`
- Flag for investigation if abnormal pattern
- Trigger alert if accumulated unreviewed > 2 weeks

DF9/DF11 admin dashboards surface the queue.

### 12U.7 Interaction with S3 privacy access

S3 privacy_level admin access now formalized via S5 impact class:

| privacy_level | Required impact class to read | Enforcement |
|---|---|---|
| `normal` | Any tier (informational, griefing, destructive) | Standard audit |
| `sensitive` | Griefing or Destructive (Tier 2+) | SQL filter rejects Tier 3 command reads |
| `confidential` | Destructive (dual-actor) | SQL filter rejects Tier 2/3 command reads |

Implementation — commands tag their impact class; SQL queries filter:
```sql
-- At query construction, helper adds:
AND (
  privacy_level = 'normal'
  OR (privacy_level = 'sensitive' AND :impact_class IN ('griefing', 'destructive'))
  OR (privacy_level = 'confidential' AND :impact_class = 'destructive')
)
```

**This unblocks S3 V1+30d deferred item** — S3 admin-tier gating was waiting on S5 classification. Now ready for V1.

### 12U.8 Governance — ADMIN_ACTION_POLICY amendment

New section R7 added to [docs/02_governance/ADMIN_ACTION_POLICY.md](../../02_governance/ADMIN_ACTION_POLICY.md):

> **R7 — Command Impact Classification**
>
> Every admin command MUST declare `ImpactClass` at registration:
> - `destructive` — irreversible data/service loss; requires dual-actor + 24h cooldown + 100+ char reason
> - `griefing` — material user impact, reversible; requires 50+ char reason + affected-user notification + periodic review
> - `informational` — read-only or self-scoped; standard audit only
>
> Classification miscategorization is PR rejection. Security team audits quarterly for correctness.
>
> **R8 — User Notification for Griefing Tier**
>
> Tier 2 commands affecting user data MUST notify affected users via standard notification channel. Suppression requires ADR.
>
> **R9 — Periodic Review**
>
> Griefing-tier entries reviewed weekly by admin-ops manager. Unreviewed > 2 weeks triggers alert.
>
> **R10 — Privacy Level Access**
>
> Reads of `privacy_level = 'sensitive'` events require Tier 2+ (Griefing or Destructive) command impact class. Reads of `privacy_level = 'confidential'` require Tier 1 (Destructive, dual-actor). Enforced via SQL filter.

### 12U.9 Config

```
admin.command.impact_class_required = true                # lint-enforced
admin.tier_griefing.min_reason_chars = 50
admin.tier_griefing.user_notification_required = true
admin.tier_griefing.periodic_review_interval_days = 7
admin.tier_griefing.review_alert_after_weeks = 2

admin.tier_destructive.min_reason_chars = 100
admin.tier_destructive.double_approval_cooldown_hours = 24

# S3 privacy access mapping (activated by S5)
privacy.admin_access.sensitive.requires_impact_class_min = "griefing"
privacy.admin_access.confidential.requires_impact_class_min = "destructive"
```

### 12U.10 Implementation ordering

- **V1 launch (mandatory):**
  - `ImpactClass` field on Command metadata
  - Classify initial ~10-15 admin commands (at R13-L1 launch)
  - `admin_action_audit` schema extension
  - `admin_action_affects_user` join table
  - Griefing-tier user notification (reuses R9 notification channel)
  - CI lint enforces `ImpactClass` declared
  - S3 privacy access mapping activated (unblocks V1+30d → V1)
  - ADMIN_ACTION_POLICY governance R7-R10 added
- **V1 + 30 days:**
  - Periodic review dashboard in DF9/DF11
  - User-facing admin activity page `/me/admin-activity`
- **V2+:**
  - Automated pattern detection (same admin repeatedly targeting one user)
  - ML classification-drift detection

### 12U.11 Accepted trade-offs

| Cost | Justification |
|---|---|
| Classification effort per command | One-time + PR-review catch; prevents large class of abuse |
| User notification noise | Bounded — Tier 2 ops are rare; users can configure delivery channel |
| Weekly review burden | Standard admin-ops practice; queue-based not interrupt |
| Reason text friction | 30s extra per command; forces deliberation; auditable |
| S3 SQL filter overhead | ~0.1ms per query; negligible; ensures privacy enforcement at DB level |

### 12U.12 What this resolves

- ✅ **Griefing gap**: "non-destructive" commands that harm users now classified + audited + user-notified
- ✅ **S3 deferred admin-tier gating**: V1+30d item moved to V1 ready
- ✅ **User transparency**: users see when admins touched their data (`/me/admin-activity`)
- ✅ **Accountability**: periodic review + mandatory reasons + classification
- ✅ **R13-L4 formalized**: implicit two-tier → explicit three-tier
- ✅ **Governance consistency**: ADMIN_ACTION_POLICY R7-R10 added

**Residuals (V2+):**
- Automated classification-drift detection (command misused over time)
- ML grief-pattern detection (same admin, same user repeatedly)

