<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S10_severance_vs_deletion.md
byte_range: 303322-319439
sha256: a259cd4b4b5e17368461ce9a36b7701537646200bce97ea8cf378df7b584c8bc
generated_by: scripts/chunk_doc.py
-->

## 12Z. Severance-vs-Deletion Distinction — S10 Resolution (2026-04-24)

**Origin:** Security Review S10 — four different mechanisms produce entities that are "gone" (severance per §12M/C1, archive per §12I/R9, drop per §12I/R9, user-erasure per §12X/S8). Each has different semantics, audit trails, recoverability, and narrative meaning. Without a canonical taxonomy, consumers (prompts, admin UIs, projections, notifications, compliance reports) conflate them — wrong recovery tool invoked, replay ambiguous, notifications mismatched, GDPR Art. 30 reports polluted.

### 12Z.1 Threat model

1. **Admin UI confusion** — admin sees "gone" and doesn't know which of the 4 states → wrong recovery tool → worst case: attempts to "undelete" a legally-erased user
2. **Audit fragmentation** — 5+ audit tables each own a piece; no unified "what happened to X" query
3. **Replay ambiguity** — §12Y.9 `ReplayPrompt` returns `partial` for severance AND crypto-shred with no distinction
4. **Cross-interaction unhandled** — user-erasure + later reality closure + later severance compound on same PC; prompts/projections/audit must handle deterministically
5. **Prompt marker drift** — `[SEVERED]` is one marker; without taxonomy, devs invent `[DELETED]` / `[MISSING]` / `[LOST]` ad-hoc → model can't distinguish
6. **Notification mismatch** — R9 closure cascade vs S8 erasure email vs DF14 narrative discovery route differently; without taxonomy, leaks across categories
7. **Recovery gate misuse** — admin assumes universal "undelete"; in reality, crypto-shred is irreversible, severance-relink is different from unarchive, backup-restore is time-bounded
8. **Compliance pollution** — GDPR Art. 30 requires *legal erasure* counts only; mixing business lifecycle + gameplay severance distorts reporting
9. **Cross-reality propagation asymmetry** — user-erasure fans to all realities (meta-worker); severance is per-pair; drop is single-reality; each needs different admin tool

### 12Z.2 Layer 1 — Canonical 5-State Taxonomy

```go
// contracts/entity_status/state.go
type GoneState string

const (
    StateActive      GoneState = "active"
    StateSevered     GoneState = "severed"       // §12M: ancestor closed, cascade severed, potentially relinkable
    StateArchived    GoneState = "archived"      // §12I R9 archived state, restorable via unarchive
    StateDropped     GoneState = "dropped"       // §12I R9 final drop, unrecoverable (DB physically gone)
    StateUserErased  GoneState = "user_erased"   // §12X S8 crypto-shred, unrecoverable for that user
)
```

Single enum, platform-wide. No other "gone" enumeration. Ad-hoc `null` / `missing` / `not_found` checks that could indicate one of these states MUST route through `GetEntityStatus()` (L2).

Narrative mapping:
| State | In-fiction meaning | Player visibility |
|---|---|---|
| `active` | present | normal |
| `severed` | lost to time, ancestor gone | DF14 mystery breadcrumbs |
| `archived` | frozen in place, admin-reversible | admin UI mostly |
| `dropped` | never existed (or forgotten utterly) | reality is gone; no in-fiction surface |
| `user_erased` | the person who cannot be remembered | `[erased]` display name in events referencing them |

### 12Z.3 Layer 2 — Unified `GetEntityStatus()` Query API

```go
// contracts/entity_status/query.go
type EntityType string

const (
    EntityReality EntityType = "reality"
    EntityPC      EntityType = "pc"
    EntityNPC     EntityType = "npc"
    EntityItem    EntityType = "item"
    EntityEvent   EntityType = "event"
)

type EntityStatus struct {
    State            GoneState
    StateChangedAt   time.Time
    ReasonRef        string         // audit-row ID: lifecycle_transition_audit_id / admin_action_audit_id / pii_kek_id / reality_migration_audit_id
    ReasonRefTable   string         // which audit table ReasonRef points to
    Recoverable      bool
    RecoveryMethod   string         // "relink_ancestor" | "unarchive_reality" | "restore_from_backup" | "impossible"
    CompoundStates   []GoneState    // all states currently applying; L5 precedence chooses display State
}

func GetEntityStatus(ctx context.Context, entityType EntityType, entityID uuid.UUID) (EntityStatus, error)
```

Resolution order (stops at first non-`active`, collects compound):
1. PII registry (`pii_kek.destroyed_at`) → `user_erased` (for PC-linked entities)
2. Meta registry (`reality_registry.status`) → `archived` / `dropped`
3. Ancestry severance (`reality_ancestry.severed_at` + cascade reachability) → `severed`
4. Entity projections → `active` if none above

Implementation detail:
- Cached 60s per `(entity_type, entity_id)` in Redis
- Cache invalidated on state transitions via MetaWrite events
- Consumers: §12Y.L4 prompt filter, §12Y.9 replay reason, admin UIs, notification system, projections display

All ad-hoc "is this thing gone?" checks forbidden outside this function. CI lint scans for `WHERE ... IS NULL` patterns on identity fields outside this path — flags for review.

### 12Z.4 Layer 3 — Standardized Prompt Marker Enum

Enumerated markers §12Y templates may emit inside prompt content:

| Marker | Meaning | Example usage |
|---|---|---|
| `[SEVERED]` | Narrative ancestry severed; data archived elsewhere | "The prophecy spoke of the `[SEVERED]` kingdom..." |
| `[ARCHIVED]` | Reality frozen (rare in play prompts; admin UI mostly) | n/a typical prompt |
| `[ERASED]` | User-scoped crypto-shred; PC display name replaced | `{[erased]} nods quietly` |
| `[UNRECOVERABLE]` | Dropped reality (admin replay only; reality is gone so no live prompt references it) | admin UI only |
| `[LOST]` | Narrative-layer wrapper (DF14); softer than `[SEVERED]` | "a `[LOST]` name from an older age" |

**Enforcement (§12Y.L6 post-output scanner extension):**
- Scanner whitelist = exactly these 5 marker patterns
- Template output containing any other bracket-marker = fixture test failure
- §12Y template lint: `[WORLD_CANON]` / `[MEMORY]` / `[HISTORY]` sections can only emit these 5 entity-state markers (other `[...]` tags are structural section names, distinct)

`[LOST]` is the soft narrative wrapper for `[SEVERED]` — use when the prompt is player-facing narrative rather than system-layer. Both tag the same state; `[LOST]` is just copy-layer preference.

### 12Z.5 Layer 4 — Cross-Audit Unified Timeline

New admin command, S5 **Informational** tier (standard single-actor auth):

```
admin entity-provenance --entity-type=pc --entity-id=<uuid> [--format=timeline|json]
```

Queries all 6 audit sources + pii_registry + ancestry table; merges by timestamp:

```
2026-01-15 14:22:10  [CREATE]       PC "Elena" created in reality R1
2026-01-20 10:04:12  [REFERENCE]    PC "Elena" first appearance in session S_abc
2026-02-03 09:11:40  [TRANSITION]   reality R1 → pending_close
                                    (actor: admin_bob, reason: "stale reality cleanup LW-1234")
2026-02-10 11:00:00  [SEVERANCE]    R1 severed from descendants [R2, R3] (cascade auto)
                                    EntityStatus: severed (recoverable via admin/relink-ancestor V2+)
2026-06-03 09:11:40  [TRANSITION]   reality R1 → dropped
                                    EntityStatus: dropped (unrecoverable; backup window 30d from 2026-05-04)
```

Queries span:
- `events` (where entity appears)
- `admin_action_audit` (admin commands touching it)
- `lifecycle_transition_audit` (reality state transitions)
- `reality_migration_audit` (§12N migrations)
- `meta_write_audit` (meta changes referencing it)
- `pii_registry` / `pii_kek` (erasure timeline)
- `reality_ancestry` (§12M severance events)

Output is authoritative answer to "what happened to entity X?" — replaces ad-hoc SQL across 6 tables. Admin UI timeline visualization (V1+30d) wraps this CLI.

### 12Z.6 Layer 5 — State Precedence Rule

When multiple states apply compound:

```
dropped > user_erased > severed > archived > active
```

- `EntityStatus.State` = strongest applying state (display winner)
- `EntityStatus.CompoundStates` = full list of applying states (for audit / admin context)

Justification:
- `dropped` wins: reality physically gone; nothing meaningful to say about sub-entities
- `user_erased > severed`: personal erasure is a stronger reader signal than narrative loss (the person exists-but-unknowable wins over fictional loss)
- `severed > archived`: severance implies narrative permanence in-fiction; archived is operationally recoverable
- `archived > active`: obvious

Edge case example:
- PC_A was in reality R1, got user-erased mid-life, then R1's ancestor got severed, then R1 got archived, then R1 got dropped
- At the drop moment: `State = dropped`, `CompoundStates = [dropped, user_erased, severed, archived]`
- Prompt marker before drop: `[ERASED]` (user_erased wins over severed); after drop, no prompts reference R1 at all (reality gone).

### 12Z.7 Layer 6 — Per-State Recovery Gate Matrix

Admin commands explicitly scoped per state. No universal "undelete" super-command.

| From state | Recovery command | S5 Tier | Preconditions |
|---|---|---|---|
| `severed` | `admin/relink-ancestor` (**V2+**) | Destructive Tier 1 | Ancestor DB must exist (not dropped); both reality IDs provided; dual-actor; 100+ char reason |
| `archived` | `admin/unarchive-reality` | Griefing Tier 2 | Within soft-delete window per §12I; 50+ char reason; user notification per R8 |
| `dropped` | `admin/restore-from-backup` (R4) | Destructive Tier 1 | Within R4 backup retention (7/14/30d by status); dual-actor; post-backup events permanently lost (explicitly documented to admin + user) |
| `user_erased` | ✗ none | — | Cryptographically impossible post-KEK destruction |
| `active` | n/a | — | — |

Admin UI flow:
1. Admin opens entity → `GetEntityStatus()` populates card
2. UI reads `RecoveryMethod` → renders tier-appropriate button + confirmation modal
3. `RecoveryMethod = "impossible"` → UI renders explanatory banner + points to user-communication template (for erasure) or data-retention-policy (for dropped-past-backup)

No free-form "undelete" anywhere. PRs adding one fail code review.

### 12Z.8 Layer 7 — Per-State Notification Templates

Notification library `pkg/notifications/` registers templates keyed by `GoneState`; routing auto-selects:

| State | Template ID | Channel | Trigger |
|---|---|---|---|
| `severed` | `notify.severance.mystery_hint` | DF14 in-game lore breadcrumb drop | On severance cascade (not email; narrative-layer) |
| `archived` | `notify.archive.frozen` | R9 notification cascade (§12I.L7) | On transition to `archived` |
| `dropped` | `notify.drop.warning_15d` + `notify.drop.final` | §12I.L7 email | 15 days before drop + at drop |
| `user_erased` | `notify.erasure.confirmed_72h` + `notify.erasure.certificate_30d` | §12X.L5 email | On crypto-shred + 30d full-erasure |

Enforcement:
- Code review rejects free-text per-incident notifications for any of these states; must use registered template
- Templates include: actor ID (redacted per §12X.L4 scrubber), reason scrubbed, timestamp, state-specific fields
- R8 griefing-tier user notification (§12U.L5) integrates via `archived` / `unarchive` — same channel, distinct template ID

### 12Z.9 Layer 8 — Compliance Report Section Separation

Quarterly compliance + annual policy review (R13 §7) reports MUST separate three categories. Template at `services/admin-cli/reports/compliance_quarterly.tmpl` hard-codes section boundaries:

```
§1 Legal erasure (GDPR Art. 17, CCPA)
   Source: admin_action_audit WHERE command = 'admin/user-erasure'
   Counts: user_ref_id erasure completions, average completion time, pending queue

§2 Business lifecycle (operational, not legal)
   Source: lifecycle_transition_audit WHERE to_state IN ('archived', 'dropped')
   Counts: realities archived, dropped, restored

§3 Gameplay severance (in-fiction, not legal or operational failure)
   Source: reality_ancestry WHERE severed_at IS NOT NULL
   Counts: severance cascade events, descendants severed, DF14 breadcrumb emissions
```

**GDPR Art. 30 processing records (§12X.L2 `contracts/pii/tables_classification.yaml`) reference ONLY §1 Legal erasure.** Business lifecycle and gameplay severance are operational data, not legal basis changes.

Comingling sections in a report = PR reject. Auditors and regulators receive only §1 for compliance inquiries; §2/§3 stay in internal ops dashboards unless specifically requested.

### 12Z.10 Interactions + V1 split + what this resolves

**Interactions**:

| With | Interaction |
|---|---|
| §12M (C1) | Canonical source of `severed` state; severance mechanism unchanged; S10 adds taxonomy layer on top |
| §12I (R9) | Provides `archived` / `dropped` state transitions; lifecycle_transition_audit is primary audit source |
| §12X (S8) | Provides `user_erased` state via crypto-shred; pii_kek.destroyed_at is audit anchor |
| §12Y (S9) | L4 filter uses `GetEntityStatus()`; post-output scanner whitelists S10-D3 markers; `ReplayPrompt` returns state-specific reason |
| §12U (S5) | Recovery commands each get own tier; admin tier gating respects state precedence |
| §12L (R13) / ADMIN_ACTION_POLICY | Amendment adds `admin/relink-ancestor` (V2+), `admin/unarchive-reality`, `admin/restore-from-backup` to §R4 dangerous command list |
| §12T (S4) | EntityStatus cache invalidation triggered by MetaWrite events |
| DF9 / DF11 | Admin UIs consume `EntityStatus` for routing; timeline viewer wraps `admin/entity-provenance` CLI |
| DF14 | `[SEVERED]` / `[LOST]` markers are DF14's gameplay surface; `notify.severance.mystery_hint` is its notification channel |

**V1 / V1+30d / V2+ split**:
- **V1**: L1 taxonomy, L2 query API, L3 marker enum + scanner whitelist, L4 `admin/entity-provenance` CLI, L5 precedence rule, L6 (archived/dropped/user_erased paths), L7 notifications, L8 compliance reports
- **V1+30d**: L4 web UI timeline visualization (DF9/DF11 subsurface)
- **V2+**: L6 `admin/relink-ancestor`, ML anomaly detection on "gone" transitions, cross-reality erasure correlation (fraud/abuse pattern detection on same-human-multiple-user_ref_ids)

**Accepted trade-offs**:

| Cost | Justification |
|---|---|
| Single-point-of-truth enum ties all consumers to one definition | Alternative (scattered "gone" checks) is exactly how S2/S3 regressions happen; centralization is the point |
| Precedence rule tie-breaking is opinionated | Any rule is better than no rule; documented precedence survives code review; edge cases captured in CompoundStates |
| `[LOST]` as soft wrapper over `[SEVERED]` = 2 markers for 1 state | Copy-layer flexibility for DF14 narrative work; both whitelisted; cheap |
| `admin/relink-ancestor` V2+ | V1 accepts severance as narrative-permanent; V2+ unlocks reunification gameplay if demand surfaces |

**What this resolves**:

- ✅ **Admin UI routing** — `EntityStatus.RecoveryMethod` drives command selection
- ✅ **Audit fragmentation** — `admin/entity-provenance` unifies 6+ sources
- ✅ **Replay ambiguity** — §12Y.9 returns specific state-reason
- ✅ **Cross-interaction layering** — L5 precedence + CompoundStates deterministic
- ✅ **Prompt marker drift** — 5-marker whitelist enforced
- ✅ **Notification mismatch** — per-state templates, auto-routed
- ✅ **Recovery gate misuse** — no universal undelete; per-state tier gating
- ✅ **Compliance pollution** — hard-coded section separation; Art. 30 references only legal erasure

**Residuals (accepted)**:
- Severance relink (V2+) blocks players from reuniting ancestor/descendant narratives until V2+ admin tool ships — DF14 mystery framing fills the gap
- Cross-reality erasure correlation (same human, multiple `user_ref_id`s) deferred V2+; V1 fraud prevention relies on payment/device signals only

