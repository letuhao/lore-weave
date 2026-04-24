<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R13_admin_discipline.md
byte_range: 134184-139622
sha256: 0daf8b3b47f71108df79d53971b6becbe80fd6c785ff05285e65c9e3cda597d7
generated_by: scripts/chunk_doc.py
-->

## 12L. Admin Tooling Discipline (R13 mitigation)

Most of R13 already addressed by DF9/DF10/DF11/DF13 tooling registrations. What remains is the **discipline layer**: guardrails, audit, compensating-event pattern, destructive-action confirmation.

### 12L.1 Layer 1 — Admin command library (canonical set)

All admin actions are named, reviewed, versioned commands in `services/admin-cli/commands/`. No ad-hoc SQL in production.

```
services/admin-cli/commands/
  reset_npc_mood.go           # documented, tested
  replay_dead_letter.go
  restore_pair_archive.go
  trigger_compaction.go
  force_close_reality.go      # requires double-approval (R9 pattern)
  ...
```

Every command:
- Named identifier (e.g. `admin/reset-npc-mood`)
- Typed parameter signature
- `--dry-run` preview mode (mandatory for destructive commands)
- Audit logs actor + parameters + result
- Docstring: what, when to use, reversibility

**Rule:** new ops need → new command, reviewed in PR. Never SSH into DB.

### 12L.2 Layer 2 — Compensating events (respect event sourcing)

Admin changes **emit events**, never raw UPDATE of projections:

```go
// REJECTED — violates event sourcing
UPDATE npc_projection SET mood='calm' WHERE npc_id = $1;

// REQUIRED — compensating event
AppendEvent(reality_id, "npc", npc_id, nextVersion, "npc.mood_admin_override", {
  new_mood: "calm",
  reason: "player reported stuck NPC — ticket LW-1234",
  actor_id: admin_user_id,
})
// Projection updated via normal flow
// Event auditable; reality rebuild preserves change
```

Admin-originated event types: `*.admin_override`, `*.admin_reset`, `*.admin_restore`. Distinctly typed so audit + replay can surface them.

### 12L.3 Layer 3 — Admin action audit log (centralized)

In meta registry (cross-reality full audit):

```sql
CREATE TABLE admin_action_audit (
  audit_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  command_name    TEXT NOT NULL,
  command_version TEXT NOT NULL,
  actor_id        UUID NOT NULL,
  reality_id      UUID,
  parameters      JSONB NOT NULL,
  result          JSONB,                         -- 'success' | 'dry_run' | 'error'
  error_detail    TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON admin_action_audit (actor_id, created_at);
CREATE INDEX ON admin_action_audit (reality_id, created_at);
```

Retention: 2 years minimum (configurable).

### 12L.4 Layer 4 — Destructive action confirmation

> **Formalized post-S5 2026-04-24:** implicit two-tier (destructive vs not) is now explicit **three-tier impact class** (destructive / griefing / informational) — see [§12U](#12u-admin-command-classification--s5-resolution-2026-04-24). Every command declares `ImpactClass`; authorization derived. `destructive: true` retained as legacy shortcut for `ImpactClass: destructive`; new commands SHOULD use `ImpactClass` directly.

Commands marked `destructive: true` require interactive confirmation:

```
Command: admin/force-close-reality
Target reality: Tavern of Broken Crown (reality_id: abc-123)
  Active players: 15
  Events: 2.3M
  Archive status: not_started

This initiates the close state machine. Type reality name to confirm: _
```

Typed confirmation; no single-click destruction. Truly dangerous commands (bypass cooling, manual DROP) require double-approval (reuse R9 pattern).

### 12L.5 Layer 5 — Admin UI guardrails

All admin UIs (DF9/DF10/DF11/DF13) MUST:
- Show current state + predicted side effects before action
- Require `--dry-run` preview for destructive actions
- **Not expose raw destructive primitives** — no "DROP DATABASE" button, only safe state machine (R9)
- Show relevant audit trail alongside action form
- No free-form SQL editor in production (dev/staging only)

### 12L.6 Layer 6 — Rollback per action

Every command documents reversibility:
- **Reversible** — `--undo` flag available (emits compensating-compensating event)
- **One-way but semantic** — documented irreversible, extra confirmation
- **Structural** (migration, shard split) — not undone via admin CLI; use normal ops flow

Rollback via compensating events: emit opposite-effect event through same pipeline.

### 12L.7 Governance policy

Policy formalized at [`docs/02_governance/ADMIN_ACTION_POLICY.md`](../../02_governance/ADMIN_ACTION_POLICY.md):
- L1–L6 are requirements, not suggestions
- No ad-hoc SQL in production (code review rejects)
- New commands require PR review + dry-run test
- Dangerous command list maintained + double-approval gated
- Audit log retention + compliance requirements

### 12L.8 Config keys (R13)

```
admin.cli.require_dry_run_for_destructive = true
admin.cli.double_approval_commands = "force-close-reality,drop-database,purge-user-data,bypass-cooling,manual-drop-partition"
admin.audit.retention_days = 730     # 2 years minimum
```

### 12L.9 Implementation ordering

- **V1 launch**: L1 (command library skeleton with ~10 initial commands), L2 (compensating-event pattern in all admin ops), L3 (audit log table + writes), L4 (destructive confirmation for initial dangerous ops), governance policy published
- **V1 + 30 days**: L5 (admin UI guardrails as DF9/DF11 mature)
- **V1 + 60 days**: L6 (rollback/undo for reversible commands)
- **V2+**: Command library grows organically; new ops add commands, not SQL

