# Admin Action Policy

> **Status:** Policy — enforced at code review and architecture review
> **Applies to:** All admin tooling across LoreWeave (CLI, admin UIs, ops scripts, DF9/DF10/DF11/DF13 surfaces)
> **Source:** Derived from [§12L in 02_storage/R13_admin_discipline.md](../03_planning/LLM_MMO_RPG/02_storage/R13_admin_discipline.md)
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
- `admin/purge-user-data` (GDPR hard delete — legacy; superseded by `admin/user-erasure`)
- `admin/user-erasure` (GDPR/CCPA right-to-erasure via crypto-shred; Tier 1 destructive; 30-day full-erasure SLA — see [02_storage/S08_audit_pii_retention.md](../03_planning/LLM_MMO_RPG/02_storage/S08_audit_pii_retention.md) §12X.6)
- `admin/unarchive-reality` (S5 Griefing Tier 2; within soft-delete window; user notification per R8 — see [02_storage/S10_severance_vs_deletion.md](../03_planning/LLM_MMO_RPG/02_storage/S10_severance_vs_deletion.md) §12Z.7)
- `admin/restore-from-backup` (S5 Destructive Tier 1, dual-actor; time-bounded by R4 retention 7/14/30d; post-backup events permanently lost — see [02_storage/S10_severance_vs_deletion.md](../03_planning/LLM_MMO_RPG/02_storage/S10_severance_vs_deletion.md) §12Z.7)
- `admin/relink-ancestor` (V2+; severance reconnection; Tier 1 destructive, dual-actor; ancestor DB must exist — see [02_storage/S10_severance_vs_deletion.md](../03_planning/LLM_MMO_RPG/02_storage/S10_severance_vs_deletion.md) §12Z.7)
- `admin/break-glass` (incident-response emergency admin access; Tier 1 dual-actor + 100+ char reason + incident ticket; 24h TTL admin JWT with `break_glass=true` claim; every RPC double-audited + SLACK/PAGE on-call; mandatory post-use credential rotation + 7d postmortem — see [02_storage/S11_service_to_service_auth.md](../03_planning/LLM_MMO_RPG/02_storage/S11_service_to_service_auth.md) §12AA.11)
- `author/canonize-fact` (L3→L2 canon promotion affecting all descendant realities; Tier 1 Destructive, dual-actor author + second reviewer, 100+ char reason, 24h author cooldown, platform-editor mandatory for book's first 90d — see [02_storage/S13_canonization_pre_spec.md](../03_planning/LLM_MMO_RPG/02_storage/S13_canonization_pre_spec.md) §12AC.3)
- `author/decanonize-fact` (L2→L3 demotion; symmetric Tier 1 Destructive; enumerated reasons; content preserved in audit — see [02_storage/S13_canonization_pre_spec.md](../03_planning/LLM_MMO_RPG/02_storage/S13_canonization_pre_spec.md) §12AC.9)
- `admin/canonize-fact` (platform-initiated emergency canonization; Tier 1 Destructive dual-actor)
- `admin/decanonize-fact` (platform-initiated; DMCA takedown / security issue / platform governance; Tier 1 Destructive dual-actor)
- `admin/update-incident-severity` (S5 Tier 2 Griefing — affects user-visible comms via status page; reason + notification required — see [02_storage/SR02_incident_oncall.md](../03_planning/LLM_MMO_RPG/02_storage/SR02_incident_oncall.md) §12AE.11)
- `status-page-admin` (S5 Tier 2 Griefing — manual maintenance/incident notices to public status page — see [02_storage/SR01_slos_error_budget.md](../03_planning/LLM_MMO_RPG/02_storage/SR01_slos_error_budget.md) §12AD.8)
- `admin/deploy-freeze` (S5 Tier 2 Griefing — blocks deploys in specified scope; affects deploy velocity — see [02_storage/SR05_deploy_safety.md](../03_planning/LLM_MMO_RPG/02_storage/SR05_deploy_safety.md) §12AH.3)
- `admin/deploy-override-freeze` (S5 Tier 1 Destructive — dual-actor; bypasses SLO-burn / incident / security freeze for emergency deploy)
- `admin/deploy-rollback` (S5 Tier 2 Griefing — reverts code/config; user-visible behavior change)
- `flag/enable` / `flag/disable` / `flag/set-scope` (S5 Tier 2 Griefing — runtime feature flag toggles; user-visible behavior change — see [02_storage/SR05_deploy_safety.md](../03_planning/LLM_MMO_RPG/02_storage/SR05_deploy_safety.md) §12AH.5)
- `admin/degraded-mode-force` (S5 Tier 1 Destructive — forces platform or service into a degraded mode bypassing automatic circuit-breaker-driven activation; user-visible; dual-actor + 100+ char reason + 24h cooldown — see [02_storage/SR06_dependency_failure.md](../03_planning/LLM_MMO_RPG/02_storage/SR06_dependency_failure.md) §12AI.6)
- `admin/circuit-breaker-reset` (S5 Tier 2 Griefing — force-closes a circuit breaker bypassing cooldown; can re-expose users to upstream failure; reason + SRE notification required — see [02_storage/SR06_dependency_failure.md](../03_planning/LLM_MMO_RPG/02_storage/SR06_dependency_failure.md) §12AI.4)
- `admin/failover-budget-override` (S5 Tier 2 Griefing — raises per-user S6 budget cap during LLM failover; bounded multiplier; billing/cost impact — see [02_storage/SR06_dependency_failure.md](../03_planning/LLM_MMO_RPG/02_storage/SR06_dependency_failure.md) §12AI.7)
- `admin/bypass-archive-verification`
- `admin/manual-partition-drop`
- Others added as needed

### Tier 3 Informational commands (rapid response, low gating)

The following commands are **not** in the dangerous list but ARE Tier 3 Informational per S5-D1 (standard single-actor auth + standard audit); documented here for operational awareness:

- `admin/declare-incident` (creates `incidents` row with severity; standard auth — rapid response matters more than gating per SR2-D1)
- `admin/close-incident` (Tier 3; terminal state transition)

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

### R7 — Command Impact Classification (added 2026-04-24, S5)

Every admin command MUST declare `ImpactClass` at registration. Three tiers:

- **`destructive`** — irreversible data/service loss (DROP DATABASE, purge-user-data, bypass-archive-verification). **Requires dual-actor** (different users, 24h cooldown) + typed confirmation + 100+ char reason.
- **`griefing`** — material user impact, reversible via compensating events (reset-npc-mood, freeze-reality, force-npc-leave-session, compaction-trigger). **Requires 50+ char reason** + affected-user notification + periodic review + enhanced audit.
- **`informational`** — read-only or self-scoped (query-stats, view-memory, help, export-session). Standard single-actor auth + standard audit.

Classification miscategorization is PR rejection. Security team audits quarterly for correctness.

Missing `ImpactClass` declaration fails CI lint.

Source design: [§12U in 02_storage/S05_admin_command_classification.md](../03_planning/LLM_MMO_RPG/02_storage/S05_admin_command_classification.md).

### R8 — User Notification for Griefing Tier (added 2026-04-24, S5)

Tier 2 (Griefing) commands that touch user data MUST notify affected users via the standard platform notification channel (same as R9 closure notifications). Notification includes:
- Admin action performed (redacted admin ID OK)
- Affected resource (NPC, session, PC, etc.)
- Reason provided by admin
- Timestamp

Users access `/me/admin-activity` for full personal audit trail.

Suppression of notification requires an ADR documenting why (e.g., maintenance ops during scheduled window with advance notice).

### R9 — Periodic Review of Griefing Actions (added 2026-04-24, S5)

Griefing-tier entries MUST be reviewed weekly by admin-ops manager:
- Mark `reviewed = true` with `review_notes`
- Flag abnormal patterns for investigation
- Unreviewed entries > 2 weeks old trigger alert

Review queue surfaced in DF9/DF11 admin dashboards.

### R10 — Privacy Level Access Control (added 2026-04-24, S3 + S5)

Reads of events with `privacy_level != 'normal'` enforce minimum impact class:
- `sensitive` events require Griefing or Destructive command (Tier 2+)
- `confidential` events require Destructive command (Tier 1, dual-actor)

Enforced via SQL filter at query construction — commands of insufficient tier cannot see higher-privacy events even if DB access is present.

Source design: [§12S.3.2 Privacy tier in 02_storage/S01_03_session_scoped_memory.md](../03_planning/LLM_MMO_RPG/02_storage/S01_03_session_scoped_memory.md) + [§12U.7 Interaction in 02_storage/S05_admin_command_classification.md](../03_planning/LLM_MMO_RPG/02_storage/S05_admin_command_classification.md).

## 4. Code review enforcement

PR reviewers MUST reject:
- New admin command lacking dry-run, audit, or docstring
- Direct `UPDATE ... SET` on projection tables outside compensating-event flow
- Admin UI exposing raw destructive SQL primitives
- Free-form SQL editor in production-facing admin UI
- Missing destructive confirmation on destructive commands
- New "dangerous command" without double-approval integration
- New/altered table migration missing PII classification tags (`@pii_sensitivity` / `@retention_class` / `@erasure_method` / `@legal_basis`) — see [02_storage/S08_audit_pii_retention.md](../03_planning/LLM_MMO_RPG/02_storage/S08_audit_pii_retention.md) §12X.3
- Direct LLM provider SDK call outside `contracts/prompt/` library (bypasses prompt assembly governance) — see [02_storage/S09_prompt_assembly.md](../03_planning/LLM_MMO_RPG/02_storage/S09_prompt_assembly.md) §12Y.2
- User-authored data populating non-`[INPUT]` section of a prompt template — see [02_storage/S09_prompt_assembly.md](../03_planning/LLM_MMO_RPG/02_storage/S09_prompt_assembly.md) §12Y.4
- Prompt template version change without corresponding fixture update — see [02_storage/S09_prompt_assembly.md](../03_planning/LLM_MMO_RPG/02_storage/S09_prompt_assembly.md) §12Y.10
- New inter-service RPC call not registered in [`contracts/service_acl/matrix.yaml`](../../contracts/service_acl/matrix.yaml) (bypasses S11 ACL enforcement) — see [02_storage/S11_service_to_service_auth.md](../03_planning/LLM_MMO_RPG/02_storage/S11_service_to_service_auth.md) §12AA.4
- Hardcoded service credentials in env vars, source code, or config files (must fetch from vault via SVID per S11-D6) — see [02_storage/S11_service_to_service_auth.md](../03_planning/LLM_MMO_RPG/02_storage/S11_service_to_service_auth.md) §12AA.7
- RPC contract missing `x-principal-mode` declaration (`requires_user` / `system_only` / `either`) — confused-deputy risk — see [02_storage/S11_service_to_service_auth.md](../03_planning/LLM_MMO_RPG/02_storage/S11_service_to_service_auth.md) §12AA.5

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
- [02_storage/R09_safe_reality_closure.md](../03_planning/LLM_MMO_RPG/02_storage/R09_safe_reality_closure.md) — §12I R9 closure protocol; admin commands for close respect the state machine.
- [02_storage/R13_admin_discipline.md](../03_planning/LLM_MMO_RPG/02_storage/R13_admin_discipline.md) — §12L, this policy's source section.

## 7. Audit mechanisms

| Mechanism | Owner | Cadence |
|---|---|---|
| `admin_action_audit` table | Every admin command writes automatically | Real-time |
| Quarterly audit review | Tech Lead + Security | Every 3 months |
| Annual policy review | Tech Lead + all admin surface owners | Annual |
| Incident postmortem reference | Incident response | Per incident |

## 8. References

- [02_storage/R13_admin_discipline.md](../03_planning/LLM_MMO_RPG/02_storage/R13_admin_discipline.md) — §12L full R13 mitigation mechanisms
- [decisions/locked_decisions.md](../03_planning/LLM_MMO_RPG/decisions/locked_decisions.md) — R13-* decision log
- [docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md](CROSS_INSTANCE_DATA_ACCESS_POLICY.md) — sibling policy
- DF9, DF10, DF11, DF13 registered features — admin UX implementations subject to this policy
