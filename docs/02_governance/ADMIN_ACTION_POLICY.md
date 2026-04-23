# Admin Action Policy

> **Status:** Policy — enforced at code review and architecture review
> **Applies to:** All admin tooling across LoreWeave (CLI, admin UIs, ops scripts, DF9/DF10/DF11/DF13 surfaces)
> **Source:** Derived from [docs/03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md §12L](../03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md)
> **Created:** 2026-04-23
> **Owner:** Tech Lead

---

## 1. Policy

Admin actions against production systems MUST follow the six requirements below. Ad-hoc SQL, raw UPDATE of projection tables, and one-click destructive commands are not permitted in production.

## 2. Why

At scale LoreWeave runs:
- Thousands of Postgres DBs (DB-per-reality)
- Full event sourcing (state is derived from events)
- Multi-state reality lifecycle (closure irreversible after ~120 days)
- Many admin surfaces (DF9 per-reality ops, DF10 schema tooling, DF11 fleet management, DF13 event handler)

Without discipline:
- Ad-hoc SQL corrupts event-sourced projections
- Direct DB UPDATEs bypass audit + replay guarantees
- Accidental destructive commands produce irreversible data loss
- Diverse admin surfaces create inconsistent operator experience
- No audit trail → no accountability

This policy defines the minimum bar.

## 3. Six requirements

### R1 — Canonical command library

Admin actions MUST be implemented as **named, reviewed, versioned commands** in `services/admin-cli/commands/` (or equivalent for each admin surface). Examples: `admin/reset-npc-mood`, `admin/replay-dead-letter`, `admin/force-close-reality`.

Each command MUST have:
- Named identifier
- Typed parameter signature
- `--dry-run` preview mode (mandatory for destructive commands)
- Docstring: what it does, when to use, reversibility
- Test coverage

Ad-hoc SQL execution in production is prohibited. New ops requirements → new command, reviewed in PR.

### R2 — Compensating events (respect event sourcing)

Admin changes MUST emit events through the standard event pipeline, not direct `UPDATE` of projection tables.

**Rejected:**
```sql
UPDATE npc_projection SET mood = 'calm' WHERE npc_id = $1;
```

**Required:**
```go
AppendEvent(reality_id, "npc", npc_id, nextVersion, "npc.mood_admin_override", {
    new_mood: "calm",
    reason: "player reported stuck NPC — ticket LW-1234",
    actor_id: admin_user_id,
})
```

Admin-originated event types carry `admin_` prefix or `_admin_override`/`_admin_reset` suffix to distinguish from organic events.

**Rationale:** event sourcing requires events as source of truth. Projections rebuild from events. Direct projection mutation invalidates rebuild guarantees and leaves no audit trail.

### R3 — Centralized admin action audit

Every admin command invocation MUST be logged in the centralized `admin_action_audit` table in the meta registry. Fields: command name + version, actor, reality_id, parameters, result, error detail, timestamp.

Retention: **minimum 2 years** (configurable, longer in regulated contexts).

Audit log is append-only; no admin command may modify it.

### R4 — Destructive action confirmation

Commands marked `destructive: true` in their definition MUST require interactive confirmation:
- Show current state + predicted side effects
- Require typed confirmation (e.g., reality name, not just checkbox)
- Display relevant audit trail for context

Truly dangerous commands (bypass safety gates, manual DROP, bulk purges) MUST require **double-approval** (reuse R9 reality-close double-approval pattern): initiator + different approver, 24h cooldown.

**Dangerous command list** (maintained in policy, updated as tooling evolves):
- `admin/force-close-reality` (bypasses cooling period)
- `admin/manual-drop-database` (bypasses soft-delete)
- `admin/purge-user-data` (GDPR hard delete)
- `admin/bypass-archive-verification`
- `admin/manual-partition-drop`
- Others added as needed

### R5 — Admin UI guardrails

All admin UIs MUST:
- Show current state before action (no blind destruction)
- Require `--dry-run` preview for destructive actions
- **Not expose raw destructive primitives** — no "DROP DATABASE" button, "TRUNCATE" button, or equivalent. Only expose operations via the safe state machines defined in the design docs (R9 closure protocol, R8 memory compaction, etc.).
- Show relevant audit trail alongside action form
- Block free-form SQL execution in production (dev/staging only; UI should refuse to connect free-form SQL tools to production DBs)

### R6 — Rollback per action

Every command MUST document its reversibility:
- **Reversible** — provide `--undo` flag; undo emits a compensating-compensating event through the same pipeline
- **One-way semantic** — documented as irreversible in command docstring; requires extra confirmation at invocation
- **Structural** (schema migration, shard split, partition detach) — not undone via admin CLI; use normal ops flow (R2 migration orchestrator, R9 closure protocol)

Rollback NEVER uses direct DB mutation. Always compensating events.

## 4. Code review enforcement

PR reviewers MUST reject:
- New admin command lacking dry-run, audit, or docstring
- Direct `UPDATE ... SET` on projection tables outside compensating-event flow
- Admin UI exposing raw destructive SQL primitives
- Free-form SQL editor in production-facing admin UI
- Missing destructive confirmation on destructive commands
- New "dangerous command" without double-approval integration

Architects MUST reject ADRs proposing ad-hoc DB connections, direct projection mutation, or bypassing the command library pattern.

## 5. Exception handling

An exception to this policy requires a written ADR documenting:
- Specific use case (why the six requirements don't fit)
- Proposed alternative pattern
- Mitigations for audit + safety concerns
- Expected review date (default 6 months)

Exceptions are RARE. Current active exceptions: none.

## 6. Relationship to other governance

- [`CROSS_INSTANCE_DATA_ACCESS_POLICY.md`](CROSS_INSTANCE_DATA_ACCESS_POLICY.md) — rejects cross-instance live queries; admin commands covered by R4 (ad-hoc federated query rate-limited) flow through that policy's §3.4.
- [02_STORAGE_ARCHITECTURE.md §12I](../03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md) — R9 closure protocol; admin commands for close respect the state machine.
- [02_STORAGE_ARCHITECTURE.md §12L](../03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md) — this policy's source section.

## 7. Audit mechanisms

| Mechanism | Owner | Cadence |
|---|---|---|
| `admin_action_audit` table | Every admin command writes automatically | Real-time |
| Quarterly audit review | Tech Lead + Security | Every 3 months |
| Annual policy review | Tech Lead + all admin surface owners | Annual |
| Incident postmortem reference | Incident response | Per incident |

## 8. References

- [docs/03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md §12L](../03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md) — full R13 mitigation mechanisms
- [docs/03_planning/LLM_MMO_RPG/OPEN_DECISIONS.md](../03_planning/LLM_MMO_RPG/OPEN_DECISIONS.md) — R13-* decision log
- [docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md](CROSS_INSTANCE_DATA_ACCESS_POLICY.md) — sibling policy
- DF9, DF10, DF11, DF13 registered features — admin UX implementations subject to this policy
