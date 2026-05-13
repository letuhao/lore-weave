# WA_003 — Forge (Author Console)

> **⚠ CLOSURE-PASS-EXTENSION 2026-04-27 — DF05_001 Session/Group Chat CANDIDATE-LOCK 71a60346:**
>
> 9 NEW V1 Forge AdminAction sub-shapes registered in `_boundaries/01_feature_ownership_matrix.md` per DF05_001 §14.1: `Forge:CreateSession { channel_id, anchor_pc_id, initial_participants, reason }` + `Forge:CloseSession { session_id, reason }` + `Forge:KickFromSession { session_id, actor_id, force, reason }` (force=true skips 30s grace per Q10-D4) + `Forge:EditActorSessionMemory { actor_id, session_id, edit_kind, before, after, reason }` (pre-close all OK per Q11-D1) + `Forge:RegenSessionDistill { session_id, reason }` (post-close re-LLM per Q11-D2) + `Forge:PurgeActorSessionMemory { actor_id, session_id, reason }` (GDPR per Q11-D3) + `Forge:AnonymizePcInSessions { actor_id, reason }` (GDPR cascade — replaces PC name with "kẻ lạ" in others' memories) + `Forge:BulkRegenSessionDistill { reality_id, session_filter, prompt_template_version, reason }` (bulk reality-scoped per Q11-D4) + `Forge:BulkPurgeStaleSessions { reality_id, before_fiction_time, reason }` (admin cleanup). All 9 use `forge_audit_log` 3-write atomic pattern (aggregate write + EVT-T8 emit + audit entry); audit-grade retention CANNOT delete audit layer per Q11-D5. Player invisible V1 per Q11-D6 (transparency UI deferred V1+30d via DF5-D16). WA_003 ForgeEditAction enum closure folds in 9 new sub-shapes additively per I14. NO change to WA_003 3-tier RBAC matrix or audit pattern; CANDIDATE-LOCK status PRESERVED. LOW magnitude — pure additive AdminAction registration. Reference: [DF05_001 §14 Forge admin operations](../DF/DF05_session_group_chat/DF05_001_session_foundation.md#14--forge-admin-operations-q11-locked).

> **📐 PATTERNS-FOR-FUTURE-EXTRACTION NOTICE (added 2026-04-25 post-WA boundary review; reframed 2026-04-25 closure pass):**
> This feature contains design patterns that are USABLE AS-IS for V1 but may be extracted to a reusable cross-cutting feature in V2+ when other author-console UIs need them. Specifically:
>
> - §6 RBAC matrix × ImpactClass classification
> - §7.4 dual-actor approval flow + pending_edit T1 state
> - §10 cross-service handoff template
>
> These patterns are **V1-ESSENTIAL** for Forge — they enable Lex/Heresy editing — and are NOT boundary violations. The future extraction is an OPTIMIZATION (deduplicate when other features need similar consoles), NOT a fix (the patterns are correctly placed for V1).
>
> **Status interpretation:** WA_003 is CANDIDATE-LOCK with normal V1 stability. The earlier "PROVISIONAL" status (commit `4be727d` over-extension marker) was reframed in this closure pass — the framing was too harsh; the patterns are legitimate WA design used to enable the Lex/Heresy editing console. See [`_boundaries/99_changelog.md`](../../_boundaries/99_changelog.md) for the audit trail.
>
> **Sections that are core WA scope (the editing functionality):**
> - §1 user story (Lex/Heresy editing scenarios)
> - §3.1 `forge_audit_log` aggregate
> - §7 EditAction closed set (Lex/Heresy operations)
> - §11/§12 Lex/Heresy edit sequences
> - §13 admin stage transition sequence
>
> **Sections that USE patterns extractable to future CC_NNN:**
> - §6 RBAC matrix (generic per-feature; usable verbatim by future console UIs)
> - §7.4 dual-actor (generic Tier1 approval flow)
> - §10 cross-service handoff (generic template)
>
> Companion files PLT_001 Charter + PLT_002 Succession (formerly WA_004/005, relocated 2026-04-25) already consume Forge's RBAC pattern as USERS — they didn't redesign, they cited. That's the pattern-reuse model V2+ may formalize.
>
> ---
>
> **Conversational name:** "Forge" (FRG). The author-facing console where world authors view + edit their reality's Lex axioms, declare per-actor Heresy contamination exceptions, and (with admin escalation) trigger WorldStability stage transitions. Pairs with Lex (the law) + Heresy (the violation): Forge is where authors WRITE the law and the exceptions.
>
> **Category:** WA — World Authoring
> **Status:** **CANDIDATE-LOCK 2026-04-25** (DRAFT → PROVISIONAL → CANDIDATE-LOCK across boundary review + closure pass; §14 acceptance criteria added — 10 scenarios). LOCK granted after the 10 §14 acceptance scenarios have passing integration tests.
> **Catalog refs:** **DF4 World Rules** (sub-feature: author UI for axioms + contamination + stability monitoring). Resolves [WA_001 LX-D4](WA_001_lex.md) (author UI to edit LexConfig) and [WA_002 HER-D10](WA_002_heresy.md) (author UI for ContaminationDecl + WorldStability monitoring).
> **Builds on:** [WA_001 Lex](WA_001_lex.md), [WA_002 Heresy](WA_002_heresy.md) (consumes their aggregates; does NOT redesign), [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) (rejection copy localization pattern), [02_storage S05](../../02_storage/) (S5 admin action policy for stage transitions)
> **Defers to:** future PCS_001 for `PcId` (Forge references abstractly), future quest engine for narrative-recovery flows.

---

## §1 User story (concrete)

**Scenario A — Wuxia author tightens a rule mid-reality:**

Author Tâm-Anh owns reality `R-tdd-h-2026-04`. She notices LLM-narrated NPCs sometimes mention firearms (anachronistic for 1256 Song dynasty). She opens Forge in the LoreWeave web UI:

1. Forge fetches her reality's LexConfig and renders the axiom table
2. She finds `Firearms: Allowance::Allowed` (default Permissive)
3. Clicks "Edit" → changes to `Allowance::Forbidden`
4. Adds note: "Anachronistic for 1256 Song setting"
5. Clicks "Save"
6. Forge POSTs a typed edit-request → backend → S5 capability check (author owns this reality? ✓) → t2_write LexConfig → invalidation broadcast → all world-service nodes pick up within 100 ms
7. Forge UI shows: "✓ Saved — future turns will reject Firearms attempts. Past committed events are unchanged (per LX §8.5 non-retroactive policy)."
8. Audit log records `forge_audit_log` row: who, when, what changed, reason

**Scenario B — Author declares a transmigrator exception:**

Same reality, Tâm-Anh introduces a new PC `pc_yangguo` who is canonically a transmigrator with imported `MagicSpells` ability (Heresy). She:

1. Opens Forge → "Contamination declarations" tab
2. Clicks "+ New declaration"
3. Picks PC: `pc_yangguo` (autocomplete from reality's actor roster)
4. Picks imported kind: `MagicSpells` (Forge auto-fills the warning: "This reality currently lists MagicSpells as Forbidden. To allow this PC's exception, the axiom must be Forbidden or AllowedWithBudget. Forge will auto-bump it to AllowedWithBudget if you proceed.")
5. Sets budget: 3 per fiction-day, 100 lifetime
6. Sets EnergySubstrate: `ConvertWorldEnergy { efficiency: 0.10 }`
7. Sets cascade: `RejectAndStrainWorld` (Forge default)
8. Clicks "Save"
9. Forge backend creates the ContaminationDecl + bumps the LexConfig axiom from `Forbidden` to `AllowedWithBudget(default_template)` atomically
10. UI shows: "✓ pc_yangguo can now use MagicSpells, capped at 3/day + 100/lifetime, drawing from world energy."

**Scenario C — Operator/admin advances world stability:**

After 200 strain accumulated in the reality, operator A opens Forge → "World Stability" tab. Sees:
- Current stage: `Strained`
- Strain accumulator: 217
- Recent violations: list (last 20 entries)
- Suggested next stage: `Cracking{1}` (advisory)

Operator A clicks "Advance to Cracking{1}" → Forge requires reason ("uncontrolled MagicSpells use") → triggers S5 dual-actor flow (operator B must approve within 60s) → on approval, backend executes WA_002 §13 sequence (t3_write + advance_turn at reality root + EVT-T8 AdminAction).

Forge UI banner: "⏳ Awaiting operator B approval..." → "✓ Reality advanced to Cracking{1}. Bubble-up propagation in progress."

**This feature design specifies:** the API contract (typed edit-request shapes), RBAC model (author vs admin), UX flow shape (NOT frontend code), audit-log aggregate, and coordination with S5 for admin operations.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **AuthorRole** | `enum AuthorRole { RealityOwner \| Co-Author \| Admin \| ReadOnly }` | RealityOwner = original creator; Co-Author = invited; Admin = LoreWeave operator; ReadOnly = viewers (e.g., book reader without edit rights). |
| **EditAction** | Typed enum of all author-issued edits Forge supports | Closed set: ~12 V1 actions. See §7. |
| **EditOutcome** | `enum EditOutcome { Applied \| AwaitingApproval \| Rejected { reason } }` | `AwaitingApproval` for S5 dual-actor flows. |
| **ForgeAuditEntry** | Immutable record of every edit-request: who, when, action, before+after snapshots, reason | Lives in `forge_audit_log` aggregate. |
| **EditPreview** (V2+) | Simulated impact of an edit BEFORE committing — "X past events would be invalidated" | Deferred §8. |
| **ImpactClass** | `enum ImpactClass { Trivial \| Minor \| Major \| Tier1 }` | Maps to S5 admin classification. Trivial = author can do solo; Tier1 = dual-actor required. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)

Forge edits are AUTHORITATIVE ops issued by privileged actors (authors / admins). They map to:

| Forge action | EVT-T* | Producer | Notes |
|---|---|---|---|
| Edit Lex axiom | **EVT-T8** AdminAction | gateway → world-service | Even author edits are AdminAction-class because they're privileged authoritative writes (per EVT-A4 producer-binding). |
| Create/delete ContaminationDecl | **EVT-T8** AdminAction | gateway → world-service | Same. |
| Trigger WorldStability stage transition | **EVT-T8** AdminAction + side-effect **EVT-T11** WorldTick (or EVT-T8 only V1 per HER-D8) | admin-cli flow per WA_002 §13 | Admin-only; S5 dual-actor required. |
| View / read | (not an event — pure read) | — | DP read_projection only. |

EVT-T8 sub-shape extension: WA_003 introduces `AdminAction::ForgeEdit { editor, action, reality, payload }` sub-shape.

---

## §3 Aggregate inventory

One new aggregate. Most state is referenced from WA_001/002.

### 3.1 `forge_audit_log`

```rust
#[derive(Aggregate)]
#[dp(type_name = "forge_audit_log", tier = "T2", scope = "reality")]
pub struct ForgeAuditEntry {
    pub entry_id: Uuid,                          // primary key
    pub reality_id: RealityId,
    pub editor: AuthorRef,                        // who made the edit
    pub editor_role: AuthorRole,                  // role at time of edit
    pub action: EditAction,                       // typed enum; payload included
    pub at_wall_clock: Timestamp,
    pub at_fiction_time: FictionTimeTuple,        // for canon-context audit
    pub before: serde_json::Value,                // snapshot of pre-edit state (relevant subset)
    pub after: serde_json::Value,                 // snapshot of post-edit state
    pub reason: String,                           // operator-supplied rationale (≤500 chars)
    pub impact_class: ImpactClass,
    pub approval_chain: Vec<AuthorRef>,           // for S5 dual-actor: approving operator(s); empty if solo-actionable
    pub correlation_event_id: Option<u64>,        // EVT-T8 AdminAction event_id this audit entry corresponds to
}
```

- T2 + RealityScoped: append-only audit log per reality.
- One row per accepted edit. Rejected edits NOT logged here (they're in `proposal_rejection_log` per general rejection-path pattern).
- `before` / `after` are JSON snapshots of the relevant subset (entire LexConfig is too big; just the axiom that changed). V2+ may add diff format for compactness.
- Read by Forge UI ("audit log" tab) and by operator review tooling (S5 telemetry).

### 3.2 References (no other new aggregates)

- **`lex_config`** (WA_001) — Forge writes via typed EditAction
- **`actor_contamination_decl`** (WA_002) — Forge creates/edits/deletes
- **`world_stability`** (WA_002) — Forge views; admin-only writes via S5
- **`reality_registry`** (per `02_storage/C03_meta_registry_ha.md`) — Forge reads to verify ownership for RBAC

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `forge_audit_log` | T2 | T2 | Reality | ~1/audit-tab-load | ~1/edit (rare) | Append-only audit; durable; eventual-consistency on read OK. |

(All other touched aggregates inherit tier+scope from WA_001/WA_002.)

No T0/T1/T3 in this feature. Audit append doesn't need T3 atomicity with the actual edit — both are logged separately and reconciled by `correlation_event_id`.

---

## §5 DP primitives this feature calls

### 5.1 Reads (per Forge view-load)

```rust
// Author views her reality's axioms
let lex = dp::read_projection_reality::<LexConfig>(ctx, LexConfigId::singleton(reality_id), ...).await?;

// Author views contamination declarations (paginated)
let decls = dp::query_scoped_reality::<ActorContaminationDecl>(
    ctx,
    Predicate::field_eq(reality_id, target_reality),
    limit=50,
    ...
).await?;

// Author views world stability
let stability = dp::read_projection_reality::<WorldStability>(ctx, WorldStabilityId::singleton(reality_id), ...).await?;

// Author views audit log
let audit = dp::query_scoped_reality::<ForgeAuditEntry>(
    ctx,
    Predicate::field_eq(reality_id, target_reality)
        .and(Predicate::field_range(at_wall_clock, since, until)),
    limit=100,
    ...
).await?;
```

### 5.2 Writes (per accepted edit)

```rust
// Edit Lex axiom (author solo for trivial; dual-actor for major)
dp::t2_write::<LexConfig>(ctx, LexConfigId::singleton(reality_id), LexDelta::EditAxiom { kind, allowance, note }).await?;

// Create / edit / delete ContaminationDecl
dp::t2_write::<ActorContaminationDecl>(ctx, decl_id, DeclDelta::Upsert { ... }).await?;
dp::t2_write::<ActorContaminationDecl>(ctx, decl_id, DeclDelta::Delete).await?;

// Stage transition (admin-only, dual-actor via S5)
dp::t3_write::<WorldStability>(ctx, WorldStabilityId::singleton(reality_id), StabilityDelta::AdvanceStage { ... }).await?;

// Audit log append (always after a successful edit)
dp::t2_write::<ForgeAuditEntry>(ctx, entry_id, AuditDelta::Append { ... }).await?;

// Emit EVT-T8 AdminAction (for the edit itself)
dp::advance_turn(ctx, &ChannelId::reality_root(reality_id), TurnEvent::AdminAction { ... }, causal_refs=[]).await?;
```

---

## §6 RBAC model

### 6.1 Closed-set roles + capabilities

| Role | Can read | Can edit Lex axioms | Can edit ContaminationDecl | Can advance WorldStability stage | Can view audit log |
|---|---|---|---|---|---|
| `ReadOnly` | ✓ (Lex + WorldStability summary only) | ✗ | ✗ | ✗ | ✗ |
| `Co-Author` | ✓ all | Trivial + Minor only | ✓ create/edit (not delete) | ✗ | ✓ (own reality) |
| `RealityOwner` | ✓ all | ✓ all (some Tier-1 require dual-actor with another author OR admin) | ✓ all | ✗ (admin escalation required) | ✓ (own reality) |
| `Admin` | ✓ all realities | ✓ all (dual-actor required for Tier-1) | ✓ all | ✓ (S5 dual-actor) | ✓ all |

### 6.2 ImpactClass classification per EditAction

| EditAction | Default ImpactClass | Notes |
|---|---|---|
| `EditAxiom { kind, from: Permissive, to: Permissive }` | Trivial | Default → Default; no behavioral change |
| `EditAxiom { kind, allowance: Allowed → Forbidden }` | Minor | Forbids future use; past events unchanged |
| `EditAxiom { kind, allowance: Forbidden → Allowed }` | Major | Opens new ability; canonical-stability concern |
| `EditAxiom { kind, allowance: * → AllowedWithBudget }` | Major | Introduces contamination model |
| `EditDefaultDisposition { Permissive → Restrictive }` | Tier1 | Whole-reality semantic flip; dual-actor required |
| `CreateContaminationDecl { ... }` | Major | New per-actor exception |
| `EditContaminationDecl { budget cap reduction }` | Minor | Tightens; cannot retroactively undo past commits |
| `EditContaminationDecl { budget cap increase OR cascade weakening }` | Major | Loosens; canonical-strain concern |
| `DeleteContaminationDecl` | Major | Removes exception; future actor uses get Lex-rejected |
| `AdvanceWorldStability { Stable → Strained }` | Major | Visible to NPCs only |
| `AdvanceWorldStability { → Cracking{1..3} }` | Tier1 | Visible to all actors; dual-actor required |
| `AdvanceWorldStability { → Catastrophic }` | Tier1 | Severe; dual-actor required + 24h cooldown after |
| `AdvanceWorldStability { → Shattered }` | Tier1 | Terminal; dual-actor + executive sign-off (V2+ formalize) |
| `RegressWorldStability { ... }` | Tier1 | Always dual-actor; rare |

### 6.3 Capability JWT shape extension

Forge adds a `forge.role: AuthorRole` claim to the operator's JWT. world-service validates per-edit:

```rust
fn check_forge_capability(jwt: &CapabilityToken, action: &EditAction, target_reality: RealityId) -> Result<(), DpError> {
    let role = jwt.forge_role_for_reality(target_reality)?;  // ReadOnly | Co-Author | RealityOwner | Admin

    let impact = action.classify_impact();
    match (role, impact) {
        (ReadOnly, _)                => Err(CapabilityDenied),
        (Co-Author, Trivial | Minor) => Ok(()),
        (Co-Author, _)               => Err(CapabilityDenied),
        (RealityOwner, Tier1)        => Err(NeedsDualActor),  // forces dual-actor flow
        (RealityOwner, _)            => Ok(()),
        (Admin, Tier1)               => Err(NeedsDualActor),
        (Admin, _)                   => Ok(()),
    }
}
```

`NeedsDualActor` is a soft error: gateway converts it into "AwaitingApproval" UX flow (§7.4) rather than a hard reject.

---

## §7 Edit flows (V1 closed set)

12 V1 EditActions. New actions added via additive schema bump (FRG-S* series, future).

### 7.1 EditAxiom

```rust
pub struct EditAxiom {
    pub kind: AxiomKind,                          // from WA_001 closed set
    pub allowance: Allowance,                     // Allowed | Forbidden | AllowedWithBudget(template)
    pub note: Option<String>,
}
```

**Frontend flow:** axiom table → row "Edit" → modal with kind dropdown (disabled — kind doesn't change), Allowance radio buttons, optional note field, Save.

**Backend flow (Trivial / Minor — solo author OK):**
1. JWT capability check (§6.3)
2. Read current LexConfig
3. Compute diff (before/after snapshots)
4. t2_write LexConfig with the new axiom
5. Append ForgeAuditEntry with `correlation_event_id`
6. Emit EVT-T8 AdminAction at reality root
7. Return `EditOutcome::Applied { lex_event_id, audit_entry_id }`

**Backend flow (Major / Tier1 — dual-actor required):**
1. JWT capability check returns `NeedsDualActor`
2. Backend creates a `pending_edit` row in transient state (T1 RealityScoped) with TTL 5 minutes
3. Returns `EditOutcome::AwaitingApproval { pending_id, expires_at }`
4. Forge UI shows "Awaiting approval from another <RealityOwner|Admin>"
5. Second author/admin opens Forge → "Pending approvals" → reviews diff → clicks "Approve" or "Reject"
6. On approve: backend completes the edit (steps 4-7 from solo flow); audit entry's `approval_chain` carries both authors
7. On reject or TTL expiry: edit discarded; audit entry NOT logged

### 7.2 EditDefaultDisposition

```rust
pub struct EditDefaultDisposition {
    pub disposition: Disposition,                 // Permissive | Restrictive
}
```

Always Tier1 (whole-reality semantic flip). Dual-actor required.

### 7.3 ContaminationDecl operations

Three actions:
```rust
pub struct CreateContaminationDecl(pub ActorContaminationDecl);
pub struct EditContaminationDecl { pub decl_id: ActorContaminationDeclId, pub patch: DeclPatch }
pub struct DeleteContaminationDecl { pub decl_id: ActorContaminationDeclId }
```

**Side-effect of CreateContaminationDecl:** if the target axiom's current Allowance is `Forbidden`, Forge auto-bumps it to `AllowedWithBudget(default_template)` in the SAME edit transaction. Author confirms in UI dialog before saving. Atomicity is via `t3_write_multi` covering both `lex_config` + `actor_contamination_decl` writes.

### 7.4 AdvanceWorldStability (admin-only)

```rust
pub struct AdvanceWorldStability {
    pub to_stage: WorldStabilityStage,
    pub reason: String,                           // ≥30 chars required for Tier1
}
```

Always admin-only (RealityOwner cannot self-trigger). Always dual-actor (Tier1 minimum).

UI surfaces "Suggested next stage" advisory (based on strain accumulator threshold) but the actual transition is operator-decision.

### 7.5 RegressWorldStability (admin-only, rare)

```rust
pub struct RegressWorldStability {
    pub to_stage: WorldStabilityStage,
    pub reason: String,                           // ≥100 chars required
}
```

Tier1, dual-actor, longer reason mandatory. Use case: false-positive stage advance, or narrative recovery (V2+ adds quest-driven recovery; manual regression remains as escape hatch).

### 7.6 Read-only views (no EditAction; just queries)

- `ViewAxioms` — table of all axioms with current Allowance + last-edited timestamp
- `ViewContaminationDecls` — paginated list of all ContaminationDecls with budget usage summary
- `ViewWorldStability` — current stage + strain accumulator + recent stage_history (last 16 transitions)
- `ViewAuditLog` — paginated, filterable by editor / action / time range
- `ViewPendingApprovals` — for Co-Author / RealityOwner / Admin: pending dual-actor edits awaiting their decision

---

## §8 Pattern choices

### 8.1 V1 = no preview/simulation

V1 does NOT preview "what would happen if I made this edit". Reasons:
- Preview requires running the validator pipeline against historical events without committing — non-trivial implementation
- V1 behavior is predictable enough by reading the design docs
- V2+ HER-D11 + new FRG-D1 add preview as a feature

V1 ships with: warning banners on Major/Tier1 edits ("This will affect future turns; past commits unchanged") + visible diff before save.

### 8.2 Audit append separate from edit (not atomic)

Locked: `t2_write LexConfig` and `t2_write ForgeAuditEntry` are SEPARATE writes, NOT in `t3_write_multi`. Reasons:
- Audit log is a logging concern; if it fails, the edit should still succeed
- Reconciliation via `correlation_event_id` (the EVT-T8 event committed via advance_turn at reality root)
- A missing audit row is recoverable by replaying from event log; missing edit is not

V2+ may strengthen to atomic if audit-loss tolerance becomes a problem. Not a V1 priority.

### 8.3 RBAC at JWT, NOT at aggregate

Forge does NOT add per-aggregate visibility rules. Authorization is at JWT-claim level + EditAction-impact-class. Aggregates remain trusting the SDK + capability check. Reason: simplifies the authorization model; aggregate reads/writes already gated by DP-K9.

### 8.4 Frontend is out of scope; this doc locks API + UX flow

WA_003 specifies:
- API endpoint shapes (gateway-level REST + types)
- UX flow descriptions ("modal opens → diff shown → save")
- RBAC matrix
- Audit log shape

WA_003 does NOT specify:
- React component structure
- Tailwind styling
- shadcn/ui component choices
- Animation timing

Frontend implementation is downstream feature work in `frontend/` per CLAUDE.md React-MVC rules.

### 8.5 Pending edits live in T1, not T2 (transient by design)

`pending_edit` (for dual-actor flow) is T1 + ChannelScoped (reality root channel), NOT T2 RealityScoped. Reasons:
- 5-minute TTL; ephemeral
- Loss on crash means "approver re-requests"; acceptable
- Not part of audit log (only ACCEPTED edits land in audit)

### 8.6 No bulk edits in V1

Author cannot "edit 10 axioms at once" in V1. Each edit is a separate request → separate EditAction → separate audit entry. V2+ may add bulk-edit transactions for efficiency. V1 keeps the model simple.

---

## §9 Failure-mode UX

| Failure | When | UX | Recovery |
|---|---|---|---|
| `CapabilityDenied` (RBAC reject) | User attempts an edit beyond their role | Toast: "Bạn không có quyền thực hiện việc này. Liên hệ chủ thực tại hoặc admin." | View role + ask owner |
| `NeedsDualActor` | Tier1 edit by single author | Modal: "Hành động này cần xác nhận từ một <RealityOwner/Admin> khác. Đã gửi yêu cầu — chờ phê duyệt trong 5 phút." | UI shows pending status; second actor approves or rejects |
| `PendingExpired` | Dual-actor approval not received within 5 min | Toast: "Yêu cầu đã hết hạn. Vui lòng gửi lại nếu vẫn cần." | User re-submits |
| `AggregateNotFound` (target axiom doesn't exist for EditAxiom) | Editor specifies a non-existent kind | Toast: "Loại quy tắc không tồn tại." | (impossible if UI uses dropdown of known kinds; defensive only) |
| `RealityMismatch` | JWT's reality_id doesn't match request | Hard 403 + audit-log a SEV2 security event | (frontend bug or malicious request) |
| `Conflict` (concurrent edits) | Two authors edit same axiom simultaneously | Last-write-wins + UI shows "Đã có thay đổi mới hơn từ <author>. Đang tải lại..." | Forge auto-reloads the axiom view; user re-applies their edit on top |
| `ContaminationDeclConflict` (creating decl for axiom that's `Allowed`, no auto-bump needed but mismatch) | UI bug or stale state | Toast: "Trạng thái thực tại đã thay đổi. Vui lòng tải lại." | reload |

V2+ adds: in-page conflict resolution UX (3-way merge for axiom edits).

---

## §10 Cross-service handoff

```text
Author opens Forge UI in browser
    │
    ▼
frontend (React) → api-gateway-bff (NestJS):
    GET /v1/forge/realities/{reality_id}/lex
    GET /v1/forge/realities/{reality_id}/contamination-decls?limit=50
    GET /v1/forge/realities/{reality_id}/world-stability
    │
gateway-bff:
    JWT capability check (forge.role for reality_id)
    forwards to world-service (Rust) via gRPC
    │
world-service:
    dp::read_projection_reality::<LexConfig>(...)
    dp::query_scoped_reality::<ActorContaminationDecl>(...)
    dp::read_projection_reality::<WorldStability>(...)
    return JSON-serialized snapshots
    │
gateway-bff → frontend: JSON response
    │
frontend renders tables + buttons
```

Author edits → POST flow:

```text
frontend → api-gateway-bff:
    POST /v1/forge/realities/{reality_id}/edits
    body: { action: EditAction, reason: String }
    │
gateway-bff:
    JWT check
    forward to world-service
    │
world-service:
    forge_validator: check capability + impact classification
    if NeedsDualActor:
        t1_write pending_edit at reality root channel (TTL 5min)
        return AwaitingApproval { pending_id }
    else:
        t2_write target aggregate (LexConfig | ActorContaminationDecl | ...)
        advance_turn at reality root with EVT-T8 AdminAction { ForgeEdit { ... } }
        t2_write ForgeAuditEntry
        return Applied { event_id, audit_entry_id }
    │
gateway-bff → frontend: response
frontend updates UI + shows toast
```

Admin stage transition (escalates through S5):

```text
admin operator A in Forge → POST /v1/forge/.../advance-stability
    │
gateway-bff → world-service:
    forge_validator: action=AdvanceWorldStability, impact=Tier1
    NeedsDualActor (always for Tier1)
    t1_write pending_edit
    notify operator B (push notification, V1 may be email/in-UI banner only)
    return AwaitingApproval { pending_id, expires_at }

operator B opens Forge → "Pending approvals" → reviews → "Approve"
    │
gateway-bff → world-service:
    completes the WA_002 §13 sequence:
        t3_write WorldStability AdvanceStage
        advance_turn at reality root with WorldTick payload (or AdminAction-only V1 per HER-D8)
        emit EVT-T8 AdminAction with approval_chain=[op_A, op_B]
        t2_write ForgeAuditEntry
    return Applied
```

---

## §11 Sequence: author flips Firearms axiom (Scenario A — Minor edit, solo)

```text
Tâm-Anh's JWT carries:
    forge.roles: { R-tdd-h-2026-04: RealityOwner }
    produce: [AdminAction]                        // for Forge edits
    write: [lex_config @ T2, forge_audit_log @ T2, actor_contamination_decl @ T2]
    can_advance_turn: [reality_root]              // for AdminAction emission

────────────────────────────────────────
frontend POST /v1/forge/realities/R-tdd-h-2026-04/edits
    body: {
      action: EditAxiom { kind: Firearms, allowance: Forbidden, note: "Anachronistic" },
      reason: "Anachronistic for 1256 Song setting"
    }
    │
    ▼
gateway-bff:
    JWT check ✓
    forward to world-service
    │
    ▼
world-service:
    forge_validator:
      role = RealityOwner ✓
      impact = Minor (Allowed → Forbidden)
      RBAC matrix: RealityOwner + Minor = Ok solo
    │
    ▼
    read current LexConfig
    compute snapshot before:  { kind: Firearms, allowance: Allowed, note: None }
    compute snapshot after:   { kind: Firearms, allowance: Forbidden, note: "Anachronistic" }
    │
    ▼
    t2_write LexConfig { LexDelta::EditAxiom { Firearms, Forbidden, Some("Anachronistic") } }
        → causality_token T2
    │
    ▼
    advance_turn at reality root with TurnEvent::AdminAction {
      sub_shape: ForgeEdit {
        editor: Tâm-Anh,
        action: EditAxiom { Firearms, Forbidden },
        before: snapshot_before,
        after: snapshot_after,
      },
      causal_refs: []
    }
        → channel_event_id = E_admin
    │
    ▼
    t2_write ForgeAuditEntry {
      entry_id: <new uuid>,
      reality_id: R-tdd-h-2026-04,
      editor: Tâm-Anh,
      editor_role: RealityOwner,
      action: EditAxiom { Firearms, Forbidden, ... },
      at_wall_clock: now,
      at_fiction_time: <current_fiction>,
      before: snapshot_before,
      after: snapshot_after,
      reason: "Anachronistic for 1256 Song setting",
      impact_class: Minor,
      approval_chain: [],                        // solo
      correlation_event_id: Some(E_admin),
    }
    │
    ▼
gateway-bff → frontend:
    200 OK { outcome: Applied,
             lex_event_id: E_admin,
             audit_entry_id: <uuid>,
             new_lex_version: <hash> }

frontend toast: "✓ Đã lưu — các lượt sau, Firearms sẽ bị từ chối."
frontend reloads axiom table (optimistic update on success)

──────────────────────────────────
Effect on subsequent turns:
    LexConfig invalidation broadcast → all world-service nodes refresh within ~100ms
    Next NPC who tries to "draw a pistol": Lex catches → rule_id "lex.ability_forbidden.firearms"
    Past committed events with NPC firing guns: UNCHANGED (per LX §8.5 non-retroactive)
```

---

## §12 Sequence: author declares contamination for pc_yangguo (Scenario B — Major, dual-actor)

```text
frontend POST /v1/forge/.../edits
    body: {
      action: CreateContaminationDecl {
        actor: ActorId::Pc(pc_yangguo),
        imported_kind: MagicSpells,
        budget: { max_per_fiction_day: 3, max_total_lifetime: 100 },
        energy_substrate: ConvertWorldEnergy { efficiency: 0.10 },
        cascade_on_exceeded: RejectAndStrainWorld,
      },
      reason: "Canonical transmigrator from arc 2"
    }
    │
    ▼
forge_validator:
    role = RealityOwner
    impact = Major (creates exception + auto-bumps axiom Allowance)
    RBAC: RealityOwner + Major = Ok solo (NOT Tier1)
    │
    ▼
world-service detects auto-bump needed:
    current LexConfig.MagicSpells = Forbidden
    creating decl requires AllowedWithBudget
    → atomic operation via t3_write_multi:
        t3_write LexConfig { EditAxiom: MagicSpells → AllowedWithBudget(default_template) }
        t3_write ActorContaminationDecl { create new decl with author's parameters }
    (T3 used here because multi-aggregate atomicity needed)
    │
    ▼
    advance_turn at reality root with AdminAction ForgeEdit { ... auto_bump=true ... }
    t2_write ForgeAuditEntry {
      action: CreateContaminationDecl { ... },
      before: { lex.MagicSpells = Forbidden, decls = [] },
      after:  { lex.MagicSpells = AllowedWithBudget, decls = [<new decl>] },
      impact_class: Major,
      ...
    }
    │
    ▼
gateway-bff → frontend:
    200 OK Applied { ... }

frontend confirmation modal first:
    "Cảnh báo: Tạo exception này sẽ tự động đổi MagicSpells từ Forbidden sang
     AllowedWithBudget. Tiếp tục?"
    [Hủy] [Xác nhận]

(after user confirms)
    POST proceeds; on success:
    toast: "✓ pc_yangguo can now use MagicSpells (3/day, 100/life)."
```

---

## §13 Sequence: admin advances stability (Scenario C — Tier1, dual-actor)

```text
Operator A POST /v1/forge/.../edits
    body: {
      action: AdvanceWorldStability { to_stage: Cracking{1}, reason: "uncontrolled MagicSpells use, 217 strain" },
      reason: "Provide narrative pressure for protagonist arc"
    }
    │
    ▼
forge_validator:
    role = Admin
    impact = Tier1 (always for AdvanceWorldStability beyond Strained)
    RBAC: Admin + Tier1 = NeedsDualActor
    │
    ▼
world-service:
    t1_write pending_edit { id: P1, reality, action, requested_by: op_A, expires_at: now+5min }
    return AwaitingApproval { pending_id: P1, expires_at }

(operator A's UI shows "⏳ Awaiting approval from another Admin")

────── 30 seconds later ──────

Operator B opens Forge → "Pending approvals" tab
    GET /v1/forge/.../pending → returns [P1]
    Op B reviews diff: stage Strained → Cracking{1}
    Op B clicks "Approve"
    │
    POST /v1/forge/.../pending/P1/approve
    │
    ▼
world-service:
    forge_validator: op B has Admin role ✓; valid for this pending edit ✓
    completes WA_002 §13 stage transition sequence:
        t3_write WorldStability AdvanceStage { from: Strained, to: Cracking{1}, ... }
        advance_turn at reality root TurnEvent::WorldTick { stage_transition }
            (or EVT-T8 AdminAction-only per HER-D8 V1)
        emit derivative bubble-up events at all descendant channels
    t2_write ForgeAuditEntry {
      action: AdvanceWorldStability { Cracking{1} },
      approval_chain: [op_A, op_B],
      impact_class: Tier1,
      ...
    }
    delete pending_edit P1
    │
    ▼
gateway-bff → both operators' frontends (push notification):
    "✓ Reality advanced to Cracking{1}. Operator A: thanks. Operator B: confirmed."

UI banner across all reality sessions:
    "⚠ Thực tại đang xuất hiện điềm bất an..." (per WA_002 §9.2)
```

---

## §14 Acceptance criteria (LOCK gate)

The design is implementation-ready when gateway-bff + world-service + admin tooling can pass these scenarios. Each scenario is one row in the integration test suite. LOCK is granted after all 10 pass.

### 14.1 Happy-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-FRG-1 OWNER MINOR EDIT** | RealityOwner Tâm-Anh executes §11 sequence: flips `Firearms: Allowed → Forbidden` (Minor solo). | RBAC check: RealityOwner + Minor = Ok solo; `t2_write LexConfig` commits with new axiom; `advance_turn` at reality root with EVT-T8 AdminAction `ForgeEdit { editor: tam_anh, action: EditAxiom { Firearms, Forbidden, ... } }`; `t2_write ForgeAuditEntry` with full snapshot before/after; UI toast confirms; subsequent turns reject Firearms attempts (per WA_001 §11 pattern). |
| **AC-FRG-2 OWNER MAJOR EDIT WITH AUTO-BUMP** | RealityOwner executes §12 sequence: creates ContaminationDecl for `pc_yangguo MagicSpells` while LexConfig has `MagicSpells: Forbidden`. | Confirmation modal shown to author; on confirm: `t3_write_multi` atomic with [LexConfig::EditAxiom (Forbidden → AllowedWithBudget(default_template)), ActorContaminationDecl::Create]; both writes either succeed or both rollback; EVT-T8 ForgeEdit with `auto_bump=true`; audit entry `before/after` shows the LexConfig delta + new decl. |
| **AC-FRG-3 CO-AUTHOR MINOR EDIT** | Co-Author (granted via PLT_001 Charter) executes a Minor-impact axiom edit. | RBAC check: Co-Author + Minor = Ok solo; same commit flow as AC-FRG-1; audit entry records Co-Author identity + role. |
| **AC-FRG-4 READ-ONLY VIEW LOAD** | All 4 roles (RealityOwner / Co-Author / Admin / ReadOnly) load the Forge UI; each role queries `lex_config` + `actor_contamination_decl` + `world_stability` per their JWT capability. | RealityOwner sees full edit-enabled UI; Co-Author sees axioms + decls (edit-enabled per role) + audit; Admin sees all + cross-reality view; ReadOnly sees axioms + WorldStability summary only (no decls / audit / edit buttons). |

### 14.2 Failure-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-FRG-5 READ-ONLY ATTEMPTS EDIT** | ReadOnly user clicks Edit (UI shouldn't expose the button, but defensive backend check); POST `/v1/forge/realities/{R}/edits` with EditAxiom payload. | gateway-bff JWT capability check rejects: `forge.role[R] = ReadOnly`; returns `CapabilityDenied`; UI toast: "Bạn không có quyền thực hiện việc này..." (per §9). No write committed. |
| **AC-FRG-6 CO-AUTHOR ATTEMPTS TIER1** | Co-Author calls `AdvanceWorldStability` (Tier1). | RBAC matrix §6.1: Co-Author cannot trigger AdvanceWorldStability (admin-only). Reject with `CapabilityDenied`; UI surfaces "Chỉ admin mới có thể thực hiện việc này.". (Tier1 NeedsDualActor flow does NOT engage because the requester isn't even authorized to initiate.) |
| **AC-FRG-7 CONCURRENT EDIT CONFLICT** | Two RealityOwner-class users (e.g., RealityOwner + Admin) submit `EditAxiom` for the same `kind: Firearms` within 50ms. | First write commits; second write succeeds based on stale read but the underlying `LexConfig` row reflects last-write-wins; UI of second author auto-reloads after detecting `lex_config.last_authored_at` is newer than their pre-edit read; UI shows "Đã có thay đổi mới hơn từ <author>. Đang tải lại..."; user can re-apply their edit if still desired. |
| **AC-FRG-8 PENDING TTL EXPIRY** | RealityOwner initiates a Tier1 edit (e.g., AdvanceWorldStability); `pending_edit` T1 row created with TTL 5 min; no second-actor approval arrives within 5 minutes. | Background sweeper (or T1 TTL expiry) drops the pending_edit silently; ForgeAuditEntry NOT logged (only Accepted edits land in audit per §8.2); submitter's UI shows "Yêu cầu đã hết hạn. Vui lòng gửi lại nếu vẫn cần."; submitter can re-initiate from scratch. |

### 14.3 Boundary scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-FRG-9 TIER1 DUAL-ACTOR APPROVAL** | §13 sequence end-to-end: operator A initiates `AdvanceWorldStability { to_stage: Cracking{1} }`; operator B approves within 5 min. | A's POST creates `pending_edit` T1 row; A's UI shows "Awaiting approval"; B's UI surfaces in "Pending approvals" tab; B's approve POST completes the edit: t3_write WorldStability AdvanceStage + advance_turn at reality root with WorldTick (or EVT-T8 AdminAction-only V1 per HER-D8) + ForgeAuditEntry with `approval_chain: [op_A, op_B]`. UI banners reach all reality sessions per WA_002 §9.2. |
| **AC-FRG-10 AUDIT-LOG NON-ATOMIC RECOVERY** | Edit's `t2_write LexConfig` succeeds and EVT-T8 AdminAction emits, but the subsequent `t2_write ForgeAuditEntry` fails (transient DB error). | Per §8.2 design (audit append separate from edit): the LexConfig edit STANDS; missing audit row is logged as a SEV3 ops alert; reconciliation tooling can replay the missing audit from the EVT-T8 AdminAction event log via `correlation_event_id` lookup. (Verifies the design's intentional non-atomicity is observable + recoverable.) |

**Lock criterion:** all 10 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-acceptance criteria + reframing) → `LOCKED` (after tests).

---

## §15 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| FRG-D1 | Edit preview/simulation — show what past events would be invalidated before committing | V2+ (HER-D11 + this) |
| FRG-D2 | Bulk edit transactions (10 axioms at once with audit-as-batch) | V2+ |
| FRG-D3 | Diff visualization (side-by-side) for complex axiom edits | V2+ frontend feature |
| FRG-D4 | Templates / presets — "Apply Wuxia preset" auto-fills 12 standard axioms | V2+ |
| FRG-D5 | Co-Author invitation flow (RealityOwner adds Co-Authors to their reality) | catalog WA-* future feature |
| FRG-D6 | i18n beyond Vietnamese (English UI for international authors) | Phase 5 ops |
| FRG-D7 | Quest-driven WorldStability recovery (narrative recovery flow) | V2+ depends on quest engine |
| FRG-D8 | Visual stability dashboard (timeline chart of strain over fiction-time) | V2+ frontend |
| FRG-D9 | Author UI tutorials / onboarding for first-time reality creators | V2+ ops |
| FRG-D10 | Author-AI assistant — "suggest axioms based on book canon analysis" | V3+ (knowledge-service integration) |
| FRG-D11 | Action history undo — "undo my last 3 edits" | V2+ (depends on diff/preview FRG-D1) |
| FRG-D12 | Notification protocol for dual-actor approval (push? email? in-UI banner only?) | V2+ ops; V1 in-UI banner sufficient |

---

## §16 Cross-references

- [WA_001 Lex](WA_001_lex.md) — provides LexConfig + AxiomKind + Allowance enum that Forge edits
- [WA_002 Heresy](WA_002_heresy.md) — provides ActorContaminationDecl + WorldStability that Forge edits
- [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) — reject copy localization pattern
- [02_storage S05] — admin action policy + S5 dual-actor enforcement
- [02_storage C03] — reality_registry for ownership lookup
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T8 AdminAction (Forge edits) + EVT-T11 WorldTick (stage transitions V2+)
- [07_event_model/02_invariants.md](../../07_event_model/02_invariants.md) — EVT-A4 producer binding (Forge JWT carries `produce: AdminAction`)
- [decisions/deferred_DF01_DF15.md](../../decisions/deferred_DF01_DF15.md) — DF4 World Rules umbrella
- [CLAUDE.md] — frontend MVC rules apply to downstream React implementation; out of WA_003 scope
- (Future) **WA_004** — Co-Author management; **WA_005** — Templates/presets

---

## §17 Implementation readiness checklist

- [x] **§2** Domain concepts (AuthorRole, EditAction, EditOutcome, ForgeAuditEntry, ImpactClass)
- [x] **§2.5** EVT-T* mapping (EVT-T8 AdminAction for edits; EVT-T11/T8 for stage transitions per HER-D8)
- [x] **§3** Aggregate inventory (1 new: `forge_audit_log`; 4 references to WA_001/002)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** RBAC model: 4 roles × ImpactClass matrix; per-EditAction default classification
- [x] **§7** 12 V1 EditActions + 5 read-only views
- [x] **§8** Pattern choices (no V1 preview; audit non-atomic; JWT-level RBAC; frontend out of scope; pending edits T1; no bulk V1)
- [x] **§9** Failure-mode UX (7 failure cases)
- [x] **§10** Cross-service handoff (frontend → gateway → world-service)
- [x] **§11** Sequence: Minor solo edit (Firearms flip)
- [x] **§12** Sequence: Major solo edit with auto-bump (CreateContaminationDecl)
- [x] **§13** Sequence: Tier1 dual-actor edit (AdvanceWorldStability)
- [x] **§14** Acceptance criteria (10 scenarios across happy-path / failure-path / boundary)
- [x] **§15** Deferrals (FRG-D1..D12)

**Deferred:** acceptance criteria (intentionally not in V1 of this doc).

**Resolves WA_001/002 deferrals:** LX-D4 (author UI) ✓, HER-D10 (author UI for ContaminationDecl + WorldStability monitoring) ✓.

**Status:** DRAFT 2026-04-25.

**Drift watchpoint:** §10 admin stage-transition flow inherits HER-D8 (EVT-T11 WorldTick V1+30d) — V1 may emit only EVT-T8 AdminAction.

**Next** (when this doc locks): gateway-bff exposes `/v1/forge/...` REST endpoints; world-service implements `forge_validator` + edit handlers + audit-log writer; frontend implements React tables + edit modals (downstream feature in `frontend/`). Vertical-slice target: Tâm-Anh's hypothetical reality with 3 sequence-tested edits (Minor solo, Major solo with auto-bump, Tier1 dual-actor) all execute end-to-end.
