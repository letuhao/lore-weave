# 02 — Extension Contracts for Shared Schemas

> **Status:** seed 2026-04-25.
>
> **Lock-gated:** edit only with the `_LOCK.md` claim active.

---

## Why this file exists

Some schemas are SHARED across many features:
- `TurnEvent` payload — extended by PL_002, NPC_002, WA_006, ...
- `RealityManifest` — extended by PL_001, WA_001, WA_002, WA_006, NPC_001, ...
- Capability JWT claims — extended by WA_003, PLT_001, PLT_002, WA_006, ...
- `EVT-T8 AdminAction` sub-shapes — extended by WA_003, PLT_001, PLT_002, WA_006, ...

Without a contract, these schemas drift:
- Two features add the same field name with different semantics
- A feature removes a field another feature depends on
- Schema versioning becomes ambiguous

This file locks the EXTENSION RULES per shared schema. Each section below is a contract.

---

## §1 — `TurnEvent` envelope

### Owner

[**PL_001 Continuum**](../features/04_play_loop/PL_001_continuum.md) §3.5.

### Current shape (TurnEventSchema = 1, 2026-04-25)

```rust
pub struct TurnEvent {
    // ─── Continuum-owned core (MUST exist) ───
    pub actor: ActorId,
    pub intent: TurnIntent,                       // Speak | Action | MetaCommand | FastForward | Narration
    pub fiction_duration_proposed: FictionDuration,
    pub narrator_text: Option<String>,            // post-validation; None on Rejected
    pub canon_drift_flags: Vec<DriftFlag>,
    pub outcome: TurnOutcome,                     // Accepted | Rejected { reason: RejectReason }
    pub idempotency_key: Uuid,                    // client-issued
    pub causal_refs: Vec<CausalRef>,              // EVT-A6 typed causal-refs

    // ─── Feature-extended (additive per I14) ───
    pub command_kind: Option<CommandKind>,        // PL_002 owns CommandKind enum closed set
    pub command_args: Option<serde_json::Value>,  // PL_002 owns per-command schemas
    pub reaction_intent: Option<ReactionIntent>,  // NPC_002 owns ReactionIntent enum
    pub aside_target: Option<ActorId>,            // NPC_002
    pub action_kind: Option<ActionKind>,          // NPC_002 owns ActionKind enum + GestureKind
    // ... future feature fields
}

pub enum TurnIntent {  // Continuum-owned closed set
    Speak,
    Action,
    MetaCommand,
    FastForward,
    Narration,
}

pub enum TurnOutcome {  // Continuum-owned closed set
    Accepted,
    Rejected { reason: RejectReason },
}

pub struct RejectReason {  // Continuum-owned envelope shape
    pub rule_id: String,                          // namespaced — see §1.4 below
    pub detail: serde_json::Value,                // feature-defined per rule_id namespace
}
```

### Extension rules

1. **Additive only.** Features MAY add new optional `Option<T>` fields. Features MUST NOT modify existing field types or remove fields. Per foundation I14.
2. **Schema version on bump.** When a feature ADDS a field, the feature's design doc declares "TurnEventSchema v1 → v2: added field `foo: Option<Foo>`". The version number is monotonic; envelope owner (Continuum) approves the bump.
3. **Continuum owns core.** Fields in the "Continuum-owned core" block above are part of the envelope; only Continuum may modify them. Other features extend the additive section.
4. **Closed enums (TurnIntent, TurnOutcome) are Continuum's.** Adding a new TurnIntent variant requires a Continuum design-change. Features cannot add intents.
5. **Feature-defined enums (CommandKind, ReactionIntent, ActionKind, ...) are owned by their respective features.** Each enum's closed set is locked in the owning feature's doc; additive evolution per I14.
6. **No co-occurrence rules baked into the envelope.** "If `command_kind=Sleep` then `intent=FastForward`" is a SEMANTIC rule, not a schema rule. Validators enforce semantic rules; envelope just declares fields.

### When a feature wants to add a field

1. Lock-claim `_LOCK.md` of `_boundaries/`
2. Update §1 of this file: add the new field with owner attribution
3. Update [`01_feature_ownership_matrix.md`](01_feature_ownership_matrix.md) "Schema / envelope ownership" row
4. Bump `TurnEventSchema` if required (Continuum approval — typically auto for additive optional fields)
5. Append `99_changelog.md` row
6. Lock-release
7. The feature's own design doc cites this file's contract

### §1.4 RejectReason rule_id namespace ownership

Each feature owns a prefix in the `rule_id` string namespace:

| Prefix | Owner |
|---|---|
| `lex.*` | WA_001 Lex |
| `heresy.*` | WA_002 Heresy |
| `mortality.*` | WA_006 Mortality (provisional; WA_006 over-extended) |
| `world_rule.*` | cross-cutting (any feature can use; documented in feature's design) |
| `oracle.*` | 05_llm_safety A3 |
| `canon_drift.*` | 05_llm_safety A6 |
| `capability.*` | DP-K9 / 05_llm_safety A6 |
| `parse.*` | PL_002 Grammar |
| `chorus.*` | NPC_002 Chorus |
| `forge.*` | WA_003 Forge |
| `charter.*` | PLT_001 Charter |
| `succession.*` | PLT_002 Succession |
| `interaction.*` | PL_005 Interaction (added 2026-04-26) |
| `status.*` | PL_006 Status Effects (added 2026-04-26) |

Continuum DOES NOT enumerate every variant. Each feature's design doc owns its prefix's rule_ids and the corresponding Vietnamese reject copy.

---

## §2 — `RealityManifest`

### Owner

⚠ **Currently unowned.** Continuum was first to declare its part (PL_001 §16) but the manifest is now extended by 5+ features.

**Proposal:** create a new infrastructure feature `IF_001_reality_manifest.md` (under `features/01_infrastructure/` if/when that folder is created) that owns the manifest envelope. Until then, this file (`02_extension_contracts.md` §2) IS the contract.

### Current shape (RealityManifestSchema = 1, 2026-04-25)

```rust
pub struct RealityManifest {
    // ─── Identity (always required) ───
    pub reality_id: RealityId,
    pub book_canon_ref: BookCanonRef,
    pub schema_version: u32,

    // ─── Continuum-owned (PL_001 §16) ───
    pub starting_fiction_time: FictionTimeTuple,
    pub root_channel_tree: RootChannelDecl,        // continent → country → district → town hierarchy
    pub canonical_actors: Vec<CanonicalActorDecl>,

    // ─── NPC_001 Cast extension to CanonicalActorDecl ───
    // CanonicalActorDecl gains: category, core_beliefs_ref, flexible_state_init,
    //                          knowledge_tags, greeting_obligation, priority_tier_hint

    // ─── WA_001 Lex extension ───
    pub lex_config: Option<LexConfigDecl>,         // None = use Permissive default

    // ─── WA_002 Heresy extension ───
    pub contamination_allowances: Vec<ContaminationAllowanceDecl>,

    // ─── WA_006 Mortality extension (provisional) ───
    pub mortality_config: Option<MortalityConfigDecl>,

    // ─── Future feature extensions ───
}
```

### Extension rules

1. **Additive only** per foundation I14. Same rule as TurnEvent.
2. **Optional fields** for feature-specific declarations (Continuum's three core fields are always required).
3. **Schema version monotonic** — when a field is added, manifest schema bumps; old realities still readable (treat missing fields as `None` / default).
4. **Per-reality opt-in.** A reality MAY omit feature-specific fields; the feature defaults apply (e.g., no `lex_config` → Lex Permissive default; no `mortality_config` → Permadeath default).
5. **Composability.** RealityManifest is composed at book-ingestion time; multiple ingestion-pipeline contributors may add their parts.

### Pending action

Creating `features/01_infrastructure/IF_001_reality_manifest.md` to formally own the envelope is a deferred action. Until that feature ships, this contract IS the truth — features cite "per `_boundaries/02_extension_contracts.md` §2".

---

## §3 — Capability JWT shape

### Owner

DP-K9 owns the base JWT shape (issuer, sub, exp, iat, capabilities, etc.). FORGE-related claims (`forge.role`, `forge.roles`, `forge.roles_version`) are owned by **PLT_001 Charter** §6.3.

### Current shape (subset relevant to Forge)

```json
{
  "iss": "dp-control-plane",
  "sub": "service:world-service",
  "reality_id": "r_<uuid>",
  "session_id": "s_<uuid>",
  "node_id": "<host-id>",
  "capabilities": [
    /* DP-K9 owned per-aggregate read/write capabilities */
  ],
  "produce": ["PlayerTurn", "NPCTurn", "AggregateMutation", "AdminAction"],

  "forge": {
    "roles": { "<reality_id>": "Co-Author | RealityOwner | Admin | ReadOnly" },
    "roles_version": 42
  },

  "exp": 1714000000,
  "iat": 1713999700
}
```

### Extension rules

1. **DP-K9 owns the envelope.** Adding a top-level field requires DP-A* axiom-level change (rare).
2. **`forge.*` namespace** is owned by Charter (PLT_001); other forge-* features (Succession, Mortality) ADD claims under the same namespace via Charter's contract.
3. **`produce: [EVT-T*]` array** is owned by event-model EVT-A4 producer-binding. Feature designs DECLARE which EVT-T* categories their service produces; event-model agent's Phase 2 reconciles the union.

### Borderline with auth-service

The `forge.roles` shape implicitly requires auth-service to know per-user-per-reality role mappings. **Drift watchpoint** (also in CHR-D9 / PLT_001): if auth-service prefers a different model (e.g., per-user platform DB), Charter's design needs alignment. Tracked, not blocking V1.

---

## §4 — `EVT-T8 AdminAction` sub-shapes

### Owner

Top-level event category EVT-T8 owned by **07_event_model agent** (Phase 1 LOCKED). Sub-shapes are FEATURE-DEFINED per the agent's "feature-defined sub-shapes" pattern (mirrors EVT-T1 PlayerTurn sub-shape model).

### Current sub-shapes (2026-04-25)

| Sub-shape | Owner feature |
|---|---|
| `ForgeEdit { editor, action, before, after }` | WA_003 Forge |
| `CharterInvite` | PLT_001 Charter |
| `CharterAccept` | PLT_001 Charter |
| `CharterDecline` | PLT_001 Charter |
| `CharterCancel` | PLT_001 Charter |
| `CharterRevoke` | PLT_001 Charter |
| `CharterResign` | PLT_001 Charter |
| `SuccessionInitiate` | PLT_002 Succession |
| `SuccessionRecipientAccept` | PLT_002 Succession |
| `SuccessionRecipientDecline` | PLT_002 Succession |
| `SuccessionRecipientWithdraw` | PLT_002 Succession |
| `SuccessionAdminApprove` | PLT_002 Succession |
| `SuccessionAdminReject` | PLT_002 Succession |
| `SuccessionOwnerCancel` | PLT_002 Succession |
| `SuccessionFinalize` | PLT_002 Succession |
| `MortalityAdminKill` (provisional) | WA_006 Mortality |

### Extension rules

1. **Feature-defined.** Each feature owns its sub-shape namespace (e.g., Charter owns `Charter*`, Succession owns `Succession*`).
2. **No collision.** Sub-shape discriminators must be globally unique within EVT-T8.
3. **Additive evolution per I14.** Features may add fields to their sub-shapes; cannot modify existing fields without schema bump.

---

## §5 — Future shared schemas

When a new shared schema arises (multiple features need to extend the same struct), open boundary-review:
1. Lock-claim
2. Add a new section to this file
3. Designate envelope owner (typically the FIRST feature that needed it, OR a dedicated infrastructure feature like IF_001)
4. Document extension rules
5. Update `01_feature_ownership_matrix.md`
6. Lock-release

Don't let new shared schemas accumulate without a contract.
