# PO_001 — Player Onboarding

> **Category:** PO — Player Onboarding (first user-visible feature post-foundation closure)
> **Catalog reference:** [`catalog/cat_03_PO_player_onboarding.md`](../../catalog/cat_03_PO_player_onboarding.md) (owns `PO-*` stable-ID namespace)
> **Status:** DRAFT 2026-04-27 — All 10 critical scope questions LOCKED via 4-batch deep-dive 2026-04-27 zero revisions. Companion documents: [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q10 LOCKED matrix §10) + [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (9-system survey; BG3 + Disco Elysium + AI Dungeon hybrid V1 anchor) + [`wireframes/`](wireframes/) (12 files HTML/CSS/MD; FE-first design committed 19855a5b + 4c4fd6d7) + [`wireframes/ACTOR_SETTINGS_AUDIT.md`](wireframes/ACTOR_SETTINGS_AUDIT.md) (46 V1 actor settings × 14 features inventory).
>
> **i18n compliance:** Conforms to RES_001 §2 cross-cutting i18n contract — all stable IDs English `snake_case` / `PascalCase`; all user-facing strings `I18nBundle`.
> **V1 testable acceptance:** 12 scenarios AC-PO-1..12 (§10).
> **Resolves:** PCS-D1 (V1+ runtime login flow PC creation; full V1) + PCS-D10 (V1+ PO_001 Player Onboarding integration; full V1).

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

Per user direction 2026-04-27 (post foundation tier 6/6 closure + 9 Tier 5 substrate features all at CANDIDATE-LOCK): "ok, tiếp tục với PO_001 — nhưng trước đó nên thiết kế FE trước; thảo luận FE sau đó chúng ta quyết định draft html trước khi đi sâu vào thiết kế tính năng". FE-first approach validated UX direction via wireframes Phase 0 commits (19855a5b + 4c4fd6d7) before backend feature spec.

PO_001 is the **first user-visible feature** post-foundation closure. Without PO_001, V1 cannot ship:
- New users have no path from auth-service login to actual gameplay
- PCS-D1 unresolved (runtime login flow PC creation deferred)
- PCS-D10 unresolved (PO_001 UI integration deferred)
- LoreWeave's "AI-native MMO RPG" positioning incomplete (no AI-driven character creation)
- Wuxia genre xuyên không signature differentiator unrealized in UX layer

PO_001 establishes the gateway from auth-service to first turn. Pure UX layer + thin orchestration over 14 locked features.

### V1 minimum scope (per Q1-Q10 LOCKED in CONCEPT_NOTES §10)

- **3 onboarding modes** (Q1 A LOCKED): `OnboardingMode { Canonical / Custom / XuyenKhong }` enum
- **Mode B 3-level UX progression** (Q2 A LOCKED): Basic Wizard 8 steps + Advanced Settings (~46 V1 fields) + AI Character Assistant
- **AI Character Assistant V1 active** (Q3 A LOCKED): natural-language input → LLM field suggestions via chat-service; reality-aware constraint checking via knowledge-service; iterative tweak; 6 quick actions; constraint-aware (skips V1+ deferred fields)
- **Email + password account creation V1** (Q4 A LOCKED): auth-service email/password registration; JWT issuance; OAuth V1+ (PO-D1)
- **Cap=1 PC per reality V1** (Q5 A LOCKED): per PCS-A9 LOCKED axiom; PO-D2 deferral covers multi-PC activation when PCS-D3 cap relaxed V1+
- **Locked-in reality per session V1** (Q6 A LOCKED): one-time selection at landing; mid-session switch V2+ (PO-D5)
- **All-or-nothing submit V1** (Q7 A LOCKED): final submit at confirm screen creates everything atomically; auto-save per step V1+30d (PO-D3)
- **Desktop-only V1** (Q8 A LOCKED): mobile responsive V1+30d (PO-D4)
- **Immediate spawn cell drop-in** (Q9 A LOCKED): confirm → cascade fires → drop into first turn với SR11 turn UX state machine + LLM scene narration
- **Inline tooltips minimal V1** (Q10 A LOCKED): hover-tooltips on form fields + minimal "Tutorial overlay" on first turn explaining 5-action grammar; richer tutorial overlay V1+30d (PO-D10)
- **1 NEW sparse aggregate**: `actor_user_session` (T2/Reality, sparse per-(actor, session))
- **2 RealityManifest extensions** (both OPTIONAL V1): `onboarding_config: Option<OnboardingConfigDecl>` + `canonical_pcs: Vec<ActorRef>` ref list (subset of canonical_actors[kind=Pc])
- **3 EVT-T8 Administrative sub-shapes V1**: `Forge:CreateOnboardingDraft` + `Forge:UpdateOnboardingDraft` + `Forge:CompleteOnboarding`
- **Cross-aggregate validator C-rule**: PC creation cascade orchestrates 14-feature event chain (Forge:RegisterPc → ActorBorn → EntityBorn → IDF_*Born → FamilyBorn → FactionMembershipBorn → ReputationBorn → ProgressionInit → actor_clocks-init → SR11 first-turn-state)
- **7 V1 reject rules** in `onboarding.*` namespace + 5 V1+ reservations
- **PO-* stable-ID prefix**

### V1 NOT shipping (deferred per Q-decisions)

| Feature | Defer to | Why |
|---|---|---|
| OAuth (Google/Discord) account creation | V1+ (PO-D1) | Q4 — V1 email+password only; OAuth requires auth-service provider integrations |
| Multi-PC roster per reality | V1+ when PCS-D3 cap relaxed (PO-D2) | Q5 — V1 PCS-A9 cap=1 LOCKED |
| Auto-save per step + draft resume | V1+30d (PO-D3) | Q7 — V1 all-or-nothing submit; actor_user_session.onboarding_draft schema additive V1+30d |
| Mobile responsive layout | V1+30d (PO-D4) | Q8 — V1 desktop-only; responsive breakpoints V1+30d |
| Reality switcher mid-session | V2+ (PO-D5) | Q6 — V1 locked-in per session |
| Character export/import (cross-reality migration) | V2+ (PO-D6) | Heresy V2+ scope |
| Community-shared character templates | V2+ (PO-D7) | Social feature; requires sharing infra |
| AI-generated character portraits | V2+ (PO-D8) | Visual AI feature; chat-service V1 text-only |
| Voice-to-text input for AI Assistant | V2+ (PO-D9) | Speech-to-text infra V2+ |
| Richer tutorial overlay (post-creation interactive) | V1+30d (PO-D10) | Q10 — V1 inline tooltips minimal; ~10-15 step tutorial V1+30d when content authored |
| Reality-themed onboarding skin (per-reality custom UI) | V1+30d (PO-D11) | Visual variant; V1 single skin với reality-themed accent only |
| Onboarding telemetry analytics | V1+30d (PO-D12) | A/B testing infrastructure |

---

## §2 — Domain concepts

### §2.1 OnboardingConfigDecl (RealityManifest declaration)

Each reality declares own onboarding config per per-reality discipline (mirrors PROG-A1 + REP_001 + FAC_001 author-discipline).

```rust
pub struct OnboardingConfigDecl {
    pub modes_enabled: Vec<OnboardingMode>,                // Q1 A LOCKED — V1 3-variant subset
    pub canonical_pcs: Vec<ActorRef>,                      // Mode A picker source; references canonical_actors[kind=Pc]
    pub ai_assistant_enabled: bool,                        // Q3 A LOCKED — per-reality opt-in (default true V1)
    pub default_spawn_cell: ChannelId,                     // Q9 A LOCKED — fallback if user skips spawn cell selection
    pub onboarding_skin: Option<I18nBundle>,               // V1+ PO-D11 reality-themed skin variant
    pub tutorial_steps: Vec<TutorialStepDecl>,             // V1+ PO-D10 richer tutorial schema-reserved
}

pub enum OnboardingMode {                                  // Q1 A LOCKED — 3 V1 variants
    Canonical,       // Mode A — pick from canonical_pcs (BG3 Origin Character pattern)
    Custom,          // Mode B — basic wizard + Advanced + AI Assistant (BG3 Custom + Cyberpunk lifepath)
    XuyenKhong,      // Mode C — Disco Elysium amnesia + wuxia transmigration (LoreWeave-unique)
}

pub struct TutorialStepDecl {                              // V1+ schema-reserved per Q10 (PO-D10)
    pub step_id: String,
    pub trigger: TutorialTrigger,                          // V1+ — OnEnter / OnFirstAction / OnDuration
    pub content: I18nBundle,
}

pub enum TutorialTrigger {
    OnEnter,                                               // V1+ — fires when scene/screen first rendered
    OnFirstAction,                                         // V1+ — fires when player makes first action of given kind
    OnDuration { fiction_seconds: u64 },                   // V1+ — fires after fiction-time elapsed
}
```

### §2.2 OnboardingDraft (V1 schema-reserved; runtime activation V1+30d per PO-D3)

```rust
pub struct OnboardingDraft {                               // V1 schema-reserved; V1+30d active per PO-D3
    pub mode: OnboardingMode,
    pub step_completed: u8,                                // 0..N for Mode B basic wizard; 0..5 Mode C
    pub draft_data: serde_json::Value,                     // free-form per mode; V1+30d schema-typed
    pub last_updated_at_turn: u64,
    pub last_updated_at_fiction_ts: i64,
}
```

### §2.3 actor_user_session aggregate (V1 minimal session tracking)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_user_session", tier = "T2", scope = "reality")]
pub struct ActorUserSession {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,                               // PC only V1 per Q5 LOCKED (cap=1 per PCS-A9)
    pub session_id: SessionId,
    pub user_id: UserId,                                   // auth-service ref
    pub onboarding_completed_at_turn: Option<u64>,         // None = onboarding in-progress; Some = completed
    pub onboarding_mode: OnboardingMode,
    pub onboarding_draft: Option<OnboardingDraft>,         // V1+30d active per PO-D3; V1 always None (all-or-nothing)
    pub schema_version: u32,                               // V1 = 1
}
```

### §2.4 PC creation cascade (Mode B Custom PC complete flow)

```pseudo
on Forge:CompleteOnboarding(user_id, mode, draft_data, reality_id):
  // Stage 0 schema validation
  reject_if reality_id ∉ user.accessible_realities → onboarding.reality_unauthorized
  reject_if mode ∉ onboarding_config.modes_enabled → onboarding.mode_unsupported
  reject_if draft_data invalid for mode → onboarding.draft_invalid
  reject_if reality.canonical_actors[kind=Pc].count >= reality.max_pc_count → onboarding.pc_cap_exceeded (V1: cap=1)
  reject_if user already has PC in this reality → onboarding.user_already_has_pc
  
  // Mode-specific validation
  match mode:
    Canonical:
      reject_if draft_data.canonical_pc_ref ∉ onboarding_config.canonical_pcs → onboarding.canonical_pc_unauthorized
      reject_if canonical_pc already user_id_init Some → onboarding.canonical_pc_unavailable
    Custom:
      reject_if draft_data.race_id ∉ reality.canonical_races → onboarding.draft_invalid
      reject_if draft_data.faction_id ∉ reality.canonical_factions → onboarding.draft_invalid
      reject_if draft_data.spawn_cell ∉ reality.places → onboarding.spawn_cell_unauthorized
      // ... per-feature constraint checks ...
    XuyenKhong:
      reject_if draft_data.body_memory.body.host_body_ref ∉ reality.canonical_actors → onboarding.draft_invalid
      reject_if draft_data.body_memory.soul.origin_world_ref Some && reality V1 → onboarding.cross_reality_migration_unsupported_v1 (V2+)
  
  // Atomic 3-write Forge admin pattern (per WA_003)
  WRITE 1: insert canonical_actor (CanonicalActorDecl from draft_data; if Mode A: lookup existing canonical_pc + bind)
  WRITE 2: emit Forge:RegisterPc + Forge:BindPcUser cascade events; insert actor_user_session row
  WRITE 3: append forge_audit_log entry
  
  // Cascade events (synchronous same turn; orchestrates 14-feature chain)
  emit Forge:RegisterPc { pc_id, body_memory_init, user_id_init, spawn_cell }   // PCS_001
  emit Forge:BindPcUser { pc_id, user_id }                                       // PCS_001
  emit ActorBorn { actor_id, kind: Pc, traits_summary }                          // ACT_001
  emit EntityBorn { entity_id, entity_type: Actor(Pc), cell_id: spawn_cell }     // EF_001
  emit RaceBorn { reality_id, actor_id, race_id }                                // IDF_001
  emit LanguageProficiencyBorn for each declared lang                            // IDF_002
  emit PersonalityBorn { actor_id, archetype_id }                                // IDF_003
  emit OriginBorn { actor_id, birthplace + lineage + native_language + ... }    // IDF_004
  emit IdeologyStanceBorn for each declared stance                               // IDF_005
  if family_node populated:
    emit FamilyBorn { actor_id, parent_refs, dynasty_id }                        // FF_001
  if faction declared:
    emit FactionMembershipBorn { actor_id, faction_id, role_id, rank }           // FAC_001
  for each declared rep row:
    emit ReputationBorn { actor_id, faction_id, initial_score }                  // REP_001
  if origin_pack default_titles V1+ (PO-D-#):
    emit TitleGranted (TIT_001) per default title
  emit ProgressionInit for declared progression_kinds                            // PROG_001
  emit ResourceInit for vital_pool + currencies + items                          // RES_001
  emit actor_clocks-init { actor_clock: 0, soul_clock, body_clock }              // TDIL_001
  emit OnboardingCompleted { user_id, actor_id, mode, fiction_ts }               // PO_001
  
  // First turn state initialization
  initialize SR11 turn UX state machine for actor (turn 0 → composing)
  generate LLM scene narration via chat-service
  return turn_id of first turn (state: Composing)
```

### §2.5 AI Character Assistant flow (Mode B + Mode C V1 active)

```pseudo
on AICharacterAssistantRequest(user_input, reality_id, current_draft):
  // Stage 1: Context preparation (synchronous; <100ms)
  let reality_manifest = read RealityManifest(reality_id)
  let constraints = extract_constraints(reality_manifest):
    - races: Vec<RaceDecl> (canonical_races)
    - languages: Vec<LanguageDecl>
    - personalities: 12 V1 archetypes (engine-fixed)
    - origins: Vec<OriginPackDecl>
    - ideologies: Vec<IdeologyDecl>
    - dynasties: Vec<DynastyDecl> (if reality declares)
    - factions: Vec<FactionDecl>
    - title_ids: Vec<TitleId>
    - progression_kinds: Vec<ProgressionKindDecl>
    - resource_kinds: Vec<ResourceKindDecl>
    - places: Vec<PlaceDecl> (cell-tier for spawn_cell options)
    - max_pc_count: u8 (V1: 1)
  
  // Stage 2: LLM call via chat-service (asynchronous; ~2-5 seconds)
  let prompt = build_ai_assistant_prompt(user_input, current_draft, constraints)
  let llm_response = chat_service.complete(prompt, model: GPT-4-class)
  
  // Stage 3: Parse + validate (synchronous; <500ms)
  let suggested_fields = parse_llm_response(llm_response)
  let validated_fields = []
  for field in suggested_fields:
    if field is V1+ deferred → SKIP (constraint awareness)
    if field.value not in reality_manifest valid_values → flag as warning
    if field is cross-feature inconsistent (e.g., faction-ideology binding violates) → flag as warning
    validated_fields.push(field)
  
  // Stage 4: Render to UI
  return AIAssistantSuggestion {
    fields: validated_fields,
    coherence_warnings: [...],
    user_summary: I18nBundle (LLM-generated explanation in user's locale),
  }

// Quick AI actions (6 V1):
// 1. Surprise me — random valid character
// 2. Make this character more {tragic/cunning/heroic}
// 3. Generate backstory hook
// 4. Validate consistency
// 5. Iterate previous suggestion (apply tweaks)
// 6. Open full screen (06_ai_assistant.html)
```

---

## §3 — Aggregates (Q5 + Q7 LOCKED)

### §3.1 `actor_user_session` (T2 / Reality scope; sparse) — PRIMARY

**Scope:** T2/Reality (per DP-A14). Sparse per-(actor, session) — only created at onboarding completion + active session lifecycle.
**Owner:** PO_001 Player Onboarding.
**Tracking model:** Eager — session row created at PC creation; updated on session lifecycle events (login/logout); mostly read-only during play loop.

### §3.2 Why split from PCS_001 pc_user_binding

PCS_001 `pc_user_binding` owns the PC ↔ user binding (PC-side). PO_001 `actor_user_session` owns the user session lifecycle (user-side).

- **PCS_001 pc_user_binding** = stable PC-user mapping (1 PC per user per reality V1 per PCS-A9)
- **PO_001 actor_user_session** = ephemeral session tracking (login/logout/onboarding-completion timestamps)

V1 sparse storage: 1 row per active session per actor; rows persist for audit even after session ends V1+30d.

---

## §4 — RealityManifest extensions

### §4.1 Fields added by PO_001

Registered in `_boundaries/02_extension_contracts.md` §2:

```rust
RealityManifest {
    // ... existing fields ...
    
    // ─── PO_001 extensions (added 2026-04-27 DRAFT) ───
    
    /// Author-declared onboarding config per reality.
    /// OPTIONAL V1 — None = use engine default (Mode B Custom only; AI Assistant enabled; default_spawn_cell = first cell in places).
    /// Wuxia preset typical: { modes_enabled: [Canonical, Custom, XuyenKhong], canonical_pcs: [5 actor refs], ai_assistant_enabled: true }
    /// Modern preset typical: { modes_enabled: [Canonical, Custom], canonical_pcs: [4 actor refs], ai_assistant_enabled: true }
    /// Sandbox/freeplay preset: None (engine defaults)
    pub onboarding_config: Option<OnboardingConfigDecl>,
    
    /// References to canonical actors that can be picked in Mode A (Canonical PC mode).
    /// MUST be subset of canonical_actors with kind=Pc (validated at canonical seed bootstrap).
    /// Empty Vec valid V1 = Mode A unavailable for this reality.
    pub canonical_pcs: Vec<ActorRef>,
}
```

### §4.2 Default values (engine fallback)

If author provides `onboarding_config: None`:
- `modes_enabled` → [Custom] (only Mode B; Canonical + XuyenKhong require explicit declaration)
- `canonical_pcs` → []
- `ai_assistant_enabled` → true
- `default_spawn_cell` → first cell-tier ChannelId in `places` (must exist)
- `onboarding_skin` → None (uses engine wuxia ink-wash + reality-themed accent default)
- `tutorial_steps` → [] (V1: inline tooltips minimal V1; richer tutorial V1+30d)

If `canonical_pcs: []`:
- Mode A picker shows empty state "Reality này chưa có nhân vật có sẵn — pick Mode B Custom hoặc Mode C Xuyên Không"

### §4.3 Per-reality opt-in (composability)

Authors can omit PO fields entirely → engine defaults apply. Per `_boundaries/02_extension_contracts.md` §2 rule 4 — composability.

---

## §5 — Events (per EVT-A11 sub-type ownership)

### §5.1 EVT-T8 Administrative sub-shapes V1

3 V1 sub-shapes:

```rust
// Forge:CreateOnboardingDraft — V1+30d active per PO-D3 (auto-save)
pub struct ForgeCreateOnboardingDraft {                    // V1 schema-reserved; V1+30d active
    pub user_id: UserId,
    pub reality_id: RealityId,
    pub mode: OnboardingMode,
    pub initial_draft_data: serde_json::Value,
}

// Forge:UpdateOnboardingDraft — V1+30d active per PO-D3
pub struct ForgeUpdateOnboardingDraft {                    // V1 schema-reserved; V1+30d active
    pub user_id: UserId,
    pub reality_id: RealityId,
    pub step_completed: u8,
    pub draft_data_delta: serde_json::Value,
}

// Forge:CompleteOnboarding — V1 ACTIVE (orchestrates PC creation cascade)
pub struct ForgeCompleteOnboarding {
    pub user_id: UserId,
    pub reality_id: RealityId,
    pub mode: OnboardingMode,
    pub draft_data: serde_json::Value,                     // V1: provided fully at submit; V1+30d resumes from draft
}
```

### §5.2 EVT-T1 Submitted sub-type — `OnboardingCompleted`

```rust
pub struct OnboardingCompleted {                           // EVT-T1 narrative milestone for LLM
    pub user_id: UserId,
    pub actor_id: ActorId,
    pub mode: OnboardingMode,
    pub completed_at_fiction_ts: i64,
    pub completed_at_turn: u64,
}
```

V1 active. Emitted on every successful PC creation. LLM uses for first-turn scene narration context ("Nhân vật vừa bước vào thế giới này — đây là cảnh đầu tiên...").

### §5.3 EVT-T3 Derived sub-type — `OnboardingDraftUpdated` (V1+30d)

```rust
pub struct OnboardingDraftUpdated {                        // V1 schema-reserved; V1+30d active per PO-D3
    pub user_id: UserId,
    pub reality_id: RealityId,
    pub step_completed: u8,
    pub fiction_ts: i64,
}
```

V1+30d active alongside auto-save activation.

---

## §6 — AI Character Assistant (Q3 A LOCKED)

### §6.1 chat-service integration (V1 active)

PO_001 V1 calls chat-service (Python/FastAPI) via api-gateway-bff for AI Character Assistant LLM calls. chat-service uses LiteLLM as provider abstraction; per CLAUDE.md "all AI calls go through adapter layer" + "no hardcoded model names".

```rust
// Pseudocode for AI Assistant integration
async fn ai_character_assistant_request(
    user_input: I18nBundle,
    reality_id: RealityId,
    current_draft: serde_json::Value,
    locale: LangCode,
) -> Result<AIAssistantSuggestion, AIError> {
    // 1. Build context from RealityManifest
    let reality_manifest = world_service.read_reality_manifest(reality_id).await?;
    let constraints = extract_constraints(&reality_manifest);
    
    // 2. Build LLM prompt
    let prompt = build_prompt(
        user_input,
        current_draft,
        constraints,
        locale,
        ai_persona: "LoreWeave Character Assistant",
    );
    
    // 3. Call chat-service via api-gateway-bff
    let response = chat_service_client.complete(
        provider_id: user.preferred_provider,                  // BYOK pattern V1+
        model: user.preferred_model OR reality.recommended_model,
        prompt,
        max_tokens: 2000,
        temperature: 0.7,
    ).await?;
    
    // 4. Parse + validate
    let suggested_fields = parse_response(response)?;
    let validated_fields = validate_against_constraints(suggested_fields, constraints);
    
    // 5. Return suggestion with coherence warnings
    Ok(AIAssistantSuggestion {
        fields: validated_fields.fields,
        coherence_warnings: validated_fields.warnings,
        user_summary: response.summary,
    })
}
```

### §6.2 Constraint awareness (Q3 A LOCKED — LoreWeave-unique)

AI Assistant skips V1+ deferred fields automatically. Validates against RealityManifest declarations:

| Field | Constraint source | V1 active validation |
|---|---|---|
| `race_id` | `reality.canonical_races` | ✅ V1 — reject if not declared |
| `language_id` | `reality.canonical_languages` | ✅ V1 |
| `personality_archetype_id` | 12 V1 engine-fixed archetypes | ✅ V1 |
| `origin_pack` | `reality.canonical_origin_packs` | ✅ V1 |
| `ideology_id` | `reality.canonical_ideologies` | ✅ V1 |
| `faction_id` | `reality.canonical_factions` | ✅ V1 |
| `role_id` | FactionDecl.roles | ✅ V1 |
| `dynasty_id` | `reality.canonical_dynasties` | ✅ V1 |
| `progression_kind_id` | `reality.progression_kinds` | ✅ V1 |
| `resource_kind` | `reality.resource_kinds` | ✅ V1 |
| `cell_id` (spawn) | `reality.places` (cell-tier only) | ✅ V1 |

V1+ deferred fields (skipped by AI Assistant):
- Title holdings (V1+ TIT-D10 origin pack default_titles)
- Cross-reality body memory (V2+ Heresy)
- Subjective time rate modifiers (V1+30d TDIL-D3)
- Etc.

### §6.3 Cross-feature consistency check

AI Assistant validates 5+ cross-feature consistency rules:

1. **Faction ↔ Ideology binding** — if faction.requires_ideology Some, actor's ideology must satisfy (RESOLVES IDF_005 IDL-D2 via FAC_001)
2. **Faction ↔ Family lineage** — sect-master title binding requires actor in correct dynasty (TIT_001)
3. **Race ↔ Origin pack** — race must be valid for origin pack's birthplace region
4. **Reputation ↔ Faction membership** — declared rep with faction X but actor not in faction X is allowed V1 (sparse storage); flagged as warning
5. **Cultivation realm ↔ Age** — high-tier cultivation usually requires high age (LLM heuristic; not engine-validated)

Coherence warnings shown to user; user can override (override = author's choice).

### §6.4 6 quick AI actions (V1 active)

1. **🎲 Surprise me** — random valid character within reality constraints
2. **🌙 Make this character more `{tragic/cunning/heroic/mysterious}`** — adjust mood/secret_held/disposition axes
3. **⚔ Generate backstory hook** — LLM creates narrative hook (e.g., "Mother's last words on deathbed...")
4. **🔍 Validate consistency** — re-run cross-feature consistency check on current draft
5. **↻ Iterate previous suggestion** — apply user's natural-language tweak to previous AI response
6. **📚 Open AI Assistant full screen** — switch from compact panel to dedicated chat UI (06_ai_assistant.html)

---

## §7 — Cross-aggregate validator (Q9 A LOCKED — immediate cascade on Forge:CompleteOnboarding)

### §7.1 PC creation cascade C-rule

Registered in `_boundaries/03_validator_pipeline_slots.md` Stage 0+ canonical seed cross-aggregate consistency rules (joins existing C1-C25 from prior commits; new rule PO-C1):

**PO-C1 (PC creation cascade orchestration):** Forge:CompleteOnboarding admin event triggers synchronous cascade across 14 features same turn. Owner: PO_001. Trigger source: Forge:CompleteOnboarding EVT-T8.

### §7.2 Cascade pseudocode (full chain)

See §2.4 cascade pseudocode — orchestrates 14 feature events synchronously same turn:

| Step | Feature | Event |
|---|---|---|
| 1 | PCS_001 | Forge:RegisterPc + Forge:BindPcUser |
| 2 | ACT_001 | ActorBorn |
| 3 | EF_001 | EntityBorn at spawn_cell |
| 4 | IDF_001 | RaceBorn |
| 5 | IDF_002 | LanguageProficiencyBorn (per declared) |
| 6 | IDF_003 | PersonalityBorn |
| 7 | IDF_004 | OriginBorn |
| 8 | IDF_005 | IdeologyStanceBorn (per declared) |
| 9 | FF_001 | FamilyBorn (if family_node) |
| 10 | FAC_001 | FactionMembershipBorn (if faction) |
| 11 | REP_001 | ReputationBorn (per declared rep row) |
| 12 | TIT_001 | TitleGranted V1+ (if origin pack default_titles per PO-D-#) |
| 13 | PROG_001 | ProgressionInit (per progression_kind) |
| 14 | RES_001 | ResourceInit (vital_pool + currencies + items) |
| 15 | TDIL_001 | actor_clocks init |
| 16 | PO_001 | OnboardingCompleted (narrative milestone) |
| 17 | SR11 | first turn state machine init |

All within same turn-event commit window.

### §7.3 Determinism per EVT-A9

Cascade is fully deterministic — no RNG V1. Replay determinism preserved.

---

## §8 — V1 reject rules (`onboarding.*` namespace)

### §8.1 V1 rule_ids (registered in `_boundaries/02_extension_contracts.md` §1.4)

7 V1 rule_ids:

| rule_id | Trigger | Vietnamese display (i18n bundle) |
|---|---|---|
| `onboarding.reality_unauthorized` | User tries to create PC in reality they don't have access to | "Bạn không có quyền truy cập thế giới này" |
| `onboarding.mode_unsupported` | User tries mode not in onboarding_config.modes_enabled | "Chế độ tạo nhân vật này không khả dụng cho thế giới này" |
| `onboarding.draft_invalid` | Mode B/C draft data fails schema validation (e.g., race not in canonical_races) | "Dữ liệu nhân vật không hợp lệ" |
| `onboarding.pc_cap_exceeded` | User tries to create PC when reality's max_pc_count reached (V1: cap=1 per PCS-A9) | "Đã đạt giới hạn số nhân vật cho thế giới này" |
| `onboarding.canonical_pc_unavailable` | Mode A picker — canonical PC already bound to another user | "Nhân vật này đã được người chơi khác chọn" |
| `onboarding.spawn_cell_unauthorized` | User picks spawn cell not in reality.places | "Vị trí xuất hiện không hợp lệ" |
| `onboarding.user_already_has_pc` | User tries to create second PC in single-reality V1 | "Bạn đã có nhân vật trong thế giới này" |

### §8.2 V1+ reservations

5 V1+ reservations:
- `onboarding.draft_resume_failed` — V1+30d (PO-D3 auto-save resume)
- `onboarding.oauth_provider_invalid` — V1+ (PO-D1 OAuth)
- `onboarding.ai_assistant_unavailable` — V1+ if chat-service down fallback
- `onboarding.tutorial_step_invalid` — V1+ (PO-D10)
- `onboarding.cross_reality_migration_unsupported_v1` — V2+ (PO-D6 character export/import)

### §8.3 RejectReason envelope conformance

PO_001 conforms to RES_001 §2.3 i18n contract — `RejectReason.user_message: I18nBundle` carries multi-language text. V1 ships I18nBundle from day 1.

---

## §9 — Sequence diagrams

### §9.1 Mode A Canonical PC selection (BG3 Origin Character pattern)

```pseudo
User clicks "Đóng vai nhân vật có sẵn" Mode A:
  fetch canonical_pcs from RealityManifest (subset of canonical_actors[kind=Pc])
  filter where canonical_pc.user_id_init.is_none() (not yet bound to other user)
  render picker UI (5 PCs with portrait + bio + stats + relationships + secrets)

User clicks "Lý Lão Tổ" → "Chọn nhân vật này":
  Forge:CompleteOnboarding {
    user_id, reality_id, mode: Canonical,
    draft_data: { canonical_pc_ref: actor.ly_lao_to }
  }
  
  Stage 0 validation:
    actor.ly_lao_to ∈ onboarding_config.canonical_pcs  ✓
    actor.ly_lao_to.user_id_init.is_none()              ✓
  
  Atomic 3-write:
    1. update pc_user_binding (set user_id_init = current user_id)
    2. emit Forge:BindPcUser
    3. forge_audit_log entry
  
  // Cascade: existing canonical PC has all features pre-populated
  // No cascade needed (ActorBorn + EntityBorn + IDF_*Born + ... already fired at canonical seed)
  // Just bind user_id + initialize first turn state
  
  emit OnboardingCompleted EVT-T1
  initialize SR11 turn UX for actor.ly_lao_to
  generate LLM scene narration via chat-service
  return turn_id of first turn (state: Composing)
```

### §9.2 Mode B Custom PC complete cascade (Basic Wizard 8 steps)

```pseudo
User completes 8-step wizard:
  Step 1: Name "Lý Minh" + đại từ "anh/em (m)"
  Step 2: Race "race.han"
  Step 3: Origin pack "origin_pack.donghai_coastal_village"
  Step 4: Personality "Cunning"
  Step 5: Faction "faction.donghai_dao_coc / role: inner_disciple / master: actor.ly_lao_to"
  Step 6: Appearance text
  Step 7: Spawn cell "cell.donghai_dao_coc.tu_luyen_that"
  Step 8: Review & confirm

User clicks "Bước Vào Thế Giới":
  Forge:CompleteOnboarding {
    user_id, reality_id, mode: Custom,
    draft_data: { name, gender_pronouns, race_id, origin_pack, personality, faction, ... }
  }
  
  Stage 0 validation:
    race_id ∈ reality.canonical_races       ✓
    faction_id ∈ reality.canonical_factions ✓
    role_id ∈ faction.roles                  ✓
    spawn_cell ∈ reality.places              ✓
    user has no existing PC in this reality  ✓
    pc_count < reality.max_pc_count (cap=1)  ✓
  
  Atomic 3-write Forge admin pattern:
    1. insert canonical_actor + actor_user_session row
    2. emit Forge:RegisterPc + Forge:BindPcUser cascade
    3. forge_audit_log entry
  
  // 14-feature cascade chain (same turn)
  emit ActorBorn (ACT_001)
  emit EntityBorn at cell.donghai_dao_coc.tu_luyen_that (EF_001)
  emit RaceBorn (IDF_001)
  emit LanguageProficiencyBorn for [donghai_van_ngon (R/W/S/L 100/80/100/100)] (IDF_002)
  emit PersonalityBorn { archetype: Cunning } (IDF_003)
  emit OriginBorn { birthplace, lineage, native_language, default_ideology_refs } (IDF_004)
  emit IdeologyStanceBorn { ideology: dao_traditional, fervor: Light } (IDF_005)
  emit FamilyBorn { actor_id, parents: [], dynasty_id: None } (FF_001)
  emit FactionMembershipBorn { faction: donghai_dao_coc, role: inner_disciple, master: ly_lao_to } (FAC_001)
  // No reputation rows declared at creation V1; skip ReputationBorn
  // No origin pack default_titles V1; skip TitleGranted (V1+ PO-D-#)
  emit ProgressionInit per origin_pack ClassDefaultDecl: qi_cultivation tier 1 raw=20 / sword_arts 80 / intelligence 18 (PROG_001)
  emit ResourceInit { hp: 100/100, stamina: 100/100, mana: 100/100, currency.copper: 50, items: [trúc kiếm × 1] } (RES_001)
  emit actor_clocks-init { actor_clock: 0, soul_clock: 0, body_clock: 0 } (TDIL_001)
  emit OnboardingCompleted EVT-T1 (PO_001)
  
  initialize SR11 turn UX state machine
  chat-service.generate_scene_narration(actor: ly_minh, scene: cell.donghai_dao_coc.tu_luyen_that, context: first_turn)
  return turn_id (state: Composing)
```

### §9.3 Mode C Xuyên Không Arrival cascade

```pseudo
User completes 5-step Mode C:
  Step 1 Soul: origin_world "earth_modern_2026" + knowledge_tags [internet, wuxia_meta] + native_language "vietnamese"
  Step 2 Body: host_body_ref "actor.deceased_ly_minh_disciple" (just died from cultivation deviation)
  Step 3 LeakagePolicy: SoulPrimary { body_blurts_threshold: 0.3 }
  Step 4 Spawn cell: inherited from body (cultivation chamber)
  Step 5 LLM-generated reveal narration (handled at confirm)

User clicks "Bước Vào Thế Giới":
  Forge:CompleteOnboarding {
    user_id, reality_id, mode: XuyenKhong,
    draft_data: { body_memory_init: PcBodyMemory { soul, body, leakage_policy }, ... }
  }
  
  Stage 0 validation:
    body.host_body_ref ∈ reality.canonical_actors                ✓
    body.host_body_ref.mortality_state ∈ [Dying, Dead]            ✓ (host body recently deceased)
    body.host_body_ref.user_id_init.is_none()                     ✓ (not yet bound)
    soul.origin_world_ref Some && reality.heresy_v1_supported     ✓ (V1: only earth_modern_2026 declared OK)
  
  Cascade similar to Mode B but with body_memory_init populated:
    Forge:RegisterPc { body_memory_init: PcBodyMemory { soul, body, leakage_policy } }
    actor inherits canonical_traits FROM host_body_ref:
      - name (host body's name)
      - role (host body's role)
      - canonical_traits.physical (host body)
    + soul-specific:
      - knowledge_tags (soul + body knowledge_tags merged per LeakagePolicy)
      - flexible_state.secret_held = "Linh hồn từ Trái Đất 2026"
  
  TDIL_001 actor_clocks init với xuyên không clock-split:
    actor_clock = 0 (new identity born now)
    soul_clock = soul.previous_world.fiction_age (carries forward from origin world)
    body_clock = host_body_ref.last_known_body_clock (inherits body age)
  
  emit PcTransmigrationCompleted EVT-T1 (PCS_001 narrative event for LLM)
  emit OnboardingCompleted EVT-T1 (PO_001)
  
  chat-service.generate_xuyen_khong_reveal(soul, body, leakage_policy):
    "Bạn mở mắt. Trên trần là gỗ thô đen. Phổi đau như rách... Đây là... đâu?
     Tay bạn — không phải tay bạn. Trẻ hơn, chai sạn hơn. Trên cánh tay có một
     vết sẹo bạn không nhớ. Và trong đầu — kiếm pháp. Một cái gì đó về
     Đông Hải Đạo Cốc..."
  
  return turn_id (state: Composing) với amnesia framing context
```

---

## §10 — Acceptance Criteria

12 V1-testable scenarios. Each must pass deterministically per EVT-A9 replay.

### AC-PO-1 — Author declares onboarding config; RealityManifest validates

- Setup: RealityManifest với onboarding_config = OnboardingConfigDecl { modes_enabled: [Canonical, Custom, XuyenKhong], canonical_pcs: [actor.ly_lao_to, actor.ly_tu, ...], ai_assistant_enabled: true, default_spawn_cell: cell.donghai_dao_coc.front_courtyard }
- Action: bootstrap reality
- Expected: Stage 0 schema validator passes; canonical_pcs subset of canonical_actors[kind=Pc] verified; actor_user_session aggregate registered

### AC-PO-2 — Engine default config when author omits

- Setup: RealityManifest với onboarding_config = None
- Action: bootstrap
- Expected: engine default applies (modes_enabled = [Custom]; canonical_pcs = []; ai_assistant_enabled = true; default_spawn_cell = first cell-tier ChannelId)

### AC-PO-3 — Mode A canonical PC selection cascade

- Setup: User logged in via auth-service; reality.onboarding_config.canonical_pcs includes actor.ly_lao_to (user_id_init = None)
- Action: User clicks Lý Lão Tổ → "Chọn"
- Expected: Forge:CompleteOnboarding emits; pc_user_binding.user_id_init updated; actor_user_session row inserted; OnboardingCompleted EVT-T1 emitted; SR11 first-turn state machine initialized; LLM scene narration generated

### AC-PO-4 — Mode B Custom PC 8-step wizard cascade

- Setup: User completes 8-step wizard for Lý Minh (race=han, origin=donghai_coastal_village, personality=Cunning, faction=donghai_dao_coc, role=inner_disciple, spawn_cell=tu_luyen_that)
- Action: User clicks "Bước Vào Thế Giới"
- Expected: 14-feature cascade fires same turn (ActorBorn + EntityBorn + RaceBorn + ... + OnboardingCompleted); all 14 events causal-ref to Forge:CompleteOnboarding; first turn state initialized; LLM scene narration generated

### AC-PO-5 — Mode C Xuyên Không Arrival cascade với body_memory_init

- Setup: User picks Mode C; soul=earth_modern_2026 + knowledge_tags + native_language=vietnamese; body=deceased_ly_minh_disciple (mortality_state=Dead); leakage_policy=SoulPrimary
- Action: User confirms
- Expected: Cascade fires với body_memory_init populated; PcTransmigrationCompleted EVT-T1 emitted; TDIL actor_clocks initialized với xuyên không clock-split (actor_clock=0; soul_clock=soul.previous_world; body_clock=host_body); LLM xuyên không reveal narration generated; first turn drops in với amnesia framing

### AC-PO-6 — AI Character Assistant suggests fields với constraint awareness

- Setup: User input "Tôi muốn một thiếu nữ hồ ly tinh, con gái bí mật của Hoàng đế..."
- Action: AI Assistant request to chat-service
- Expected: chat-service returns suggestions for race=fox_spirit_lineage + faction=donghai_dao_coc + father=imperial_emperor + secret_held + ...; AI skips V1+ deferred fields (no title suggestions; no cross-reality body memory); coherence warnings for ambiguous suggestions; user can apply all OR review one-by-one

### AC-PO-7 — Onboarding rejection: reality unauthorized

- Setup: User logged in but no access to reality_id="paid_premium_reality"
- Action: User tries to enter that reality
- Expected: reject `onboarding.reality_unauthorized` với I18nBundle "Bạn không có quyền truy cập thế giới này"

### AC-PO-8 — Onboarding rejection: PC cap exceeded V1

- Setup: User already has PC in reality (cap=1 V1 per PCS-A9)
- Action: User tries to create second PC
- Expected: reject `onboarding.user_already_has_pc` với I18nBundle "Bạn đã có nhân vật trong thế giới này"

### AC-PO-9 — Onboarding rejection: canonical PC unavailable

- Setup: User picks canonical PC actor.ly_lao_to but it's already bound to another user
- Action: Forge:CompleteOnboarding với mode=Canonical
- Expected: reject `onboarding.canonical_pc_unavailable` với I18nBundle "Nhân vật này đã được người chơi khác chọn"

### AC-PO-10 — All-or-nothing submit V1 (no draft persistence)

- Setup: User in middle of Mode B Step 4; refreshes browser
- Action: User returns to landing
- Expected: V1 — draft state lost; user starts over from landing; no actor_user_session row created (no completion happened); V1+30d (PO-D3) ships auto-save

### AC-PO-11 — First turn drop-in immediate

- Setup: User completes any mode
- Action: Forge:CompleteOnboarding succeeds
- Expected: SR11 turn UX state machine initialized (state: Composing); LLM scene narration in scene_narration block; 5 quick action buttons (Speak/Action/MetaCommand/FastForward/Narration) rendered; sidebar shows Persona+Faction+Reputation+Title+Inventory+Cultivation+TDIL clocks; turn_id returned from Forge:CompleteOnboarding response

### AC-PO-12 — AI Assistant graceful degradation when chat-service down

- Setup: chat-service unreachable (timeout 5s)
- Action: User clicks AI Assistant input
- Expected: AI Assistant disabled với banner "AI Character Assistant tạm thời không khả dụng — vui lòng dùng Manual mode"; user can still complete creation via Basic Wizard or Advanced Settings; no reject (reject `onboarding.ai_assistant_unavailable` V1+ if needed)

### V1+ deferred AC

- **AC-PO-V1+1**: V1+ OAuth account creation cascade (PO-D1 — Google + Discord providers)
- **AC-PO-V1+2**: V1+ Multi-PC roster screen (PO-D2 — when PCS-D3 cap relaxed)
- **AC-PO-V1+3**: V1+30d Auto-save per step + draft resume (PO-D3 — actor_user_session.onboarding_draft activation)
- **AC-PO-V1+4**: V1+30d Mobile responsive layout (PO-D4 — breakpoints <768px)

---

## §11 — V1 Minimum Delivery Summary

| Element | V1 spec |
|---|---|
| Aggregates | 1 (`actor_user_session`) |
| RealityManifest extensions | 2 OPTIONAL (onboarding_config + canonical_pcs ref list) |
| OnboardingMode variants | 3 V1 (Canonical / Custom / XuyenKhong) |
| Mode B levels | 3 V1 (Basic Wizard 8 steps + Advanced ~46 fields + AI Assistant) |
| AI Assistant | V1 active via chat-service + knowledge-service constraint awareness |
| Account auth methods V1 | 1 (email + password); OAuth V1+ (PO-D1) |
| Multi-PC cap V1 | 1 per PCS-A9 LOCKED; V1+ relax via PCS-D3 |
| EVT-T8 sub-shapes | 3 (Forge:CreateOnboardingDraft V1+30d / UpdateOnboardingDraft V1+30d / CompleteOnboarding V1 active) |
| EVT-T1 sub-types | 1 (OnboardingCompleted narrative milestone) |
| EVT-T3 sub-types | 1 (OnboardingDraftUpdated V1+30d) |
| Cross-aggregate validators | 1 (PO-C1 PC creation cascade orchestration; 14-feature chain) |
| RejectReason rule_ids | 7 V1 + 5 V1+ reservations |
| Acceptance scenarios | 12 V1 + 4 V1+ deferred |
| Stable-ID prefix | PO-* |
| Cross-feature deferrals resolved | PCS-D1 (full V1) + PCS-D10 (full V1) |

---

## §12 — Deferrals Catalog (PO-D1..PO-D12)

**V1+30d (fast-follow):**
- PO-D3 Auto-save per step + draft resume (actor_user_session.onboarding_draft schema activation)
- PO-D4 Mobile responsive layout (breakpoints <768px; Mode B Advanced layout adaptation)
- PO-D10 Richer tutorial overlay post-creation (~10-15 step interactive tutorial when content authored)
- PO-D11 Reality-themed onboarding skin variant (per-reality custom UI beyond accent color)
- PO-D12 Onboarding telemetry analytics (A/B testing + funnel conversion tracking)

**V1+ (when consumer feature ships):**
- PO-D1 OAuth account creation (Google + Discord; auth-service provider integration)
- PO-D2 Multi-PC roster screen (when PCS-D3 cap=1 → cap=N relaxed)

**V2 (Economy/Strategy module-tier):**
- PO-D6 Character export/import (cross-reality migration via WA_002 Heresy)
- PO-D7 Community-shared character templates (social feature; sharing infra)

**V2+ (Heresy / Mid-session features):**
- PO-D5 Reality switcher mid-session (no-logout reality change)
- PO-D8 AI-generated character portraits (visual AI feature; image-gen service)
- PO-D9 Voice-to-text input for AI Assistant (speech-to-text infra)

---

## §13 — Cross-references

### §13.1 Resolves cross-feature deferrals

- **PCS-D1** (PCS_001): V1+ runtime login flow PC creation → V1 RESOLVES (full active via Forge:CompleteOnboarding orchestrating Forge:RegisterPc + Forge:BindPcUser cascade)
- **PCS-D10** (PCS_001): V1+ PO_001 Player Onboarding integration → V1 RESOLVES (full active via 14-feature cascade orchestration)

### §13.2 Cross-feature integration

- **EF_001 Entity Foundation** — PO_001 reads ActorId source; emits EntityBorn at spawn_cell
- **PF_001 Place Foundation** — reads RealityManifest.places for spawn cell selection; validates spawn_cell ∈ places
- **ACT_001 Actor Foundation** — consumes CanonicalActorDecl shape; populates actor_core canonical_traits + flexible_state_init + mood_init (Mode B)
- **PCS_001 PC Substrate** — RESOLVES PCS-D1 + PCS-D10; orchestrates Forge:RegisterPc + Forge:BindPcUser cascade
- **IDF_001..005** — Mode B wizard steps consume race/language/personality/origin/ideology decls (per-reality declared)
- **FF_001 Family Foundation** — Mode B Advanced allows family relations input; emits FamilyBorn
- **FAC_001 Faction Foundation** — Mode B Step 5 + Advanced — faction membership input; emits FactionMembershipBorn
- **REP_001 Reputation Foundation** — Mode B Advanced — initial reputation rows per faction; emits ReputationBorn
- **TIT_001 Title Foundation** — V1+ origin pack default_titles via TIT-D10
- **PROG_001 Progression Foundation** — Mode B + Advanced — initial progression values per ClassDefaultDecl
- **RES_001 Resource Foundation** — Mode B + Advanced — initial vital pools + currencies + items
- **TDIL_001 Time Dilation Foundation** — actor_clocks initialized at PC creation (xuyên không clock-split if Mode C)
- **AIT_001 AI Tier Foundation** — PCs always None tier (PO_001 doesn't override)
- **WA_006 Mortality** — mortality_state initialized to Alive; Mode C may set Dying/Dead initial state for body host
- **WA_003 Forge** — 3-write atomic Forge admin pattern + forge_audit_log
- **chat-service** (Python/FastAPI) — AI Character Assistant V1 dependency; LLM via LiteLLM
- **knowledge-service** (Python/FastAPI) — RealityManifest constraint awareness for AI Assistant
- **auth-service** (Go/Chi) — email + password account creation V1; JWT issuance
- **api-gateway-bff** (TypeScript/NestJS) — first WS connection + ticket exchange per S12
- **M7 progressive disclosure** — Mode B "Skip → use defaults" CTA enforces tier defaults via origin pack
- **SR11 turn UX reliability** — first turn state machine visible from turn 1
- **UI_COPY_STYLEGUIDE** — tooltip + first-run copy governance
- **EVT_model EVT-A11** — PO_001 owns actor_user_session; only PO_001 emits onboarding.* EVT-T8 sub-shapes per Aggregate-Owner discipline

### §13.3 V1+ downstream features

- **DF05 Session/Group Chat** — actor_user_session.session_id ↔ DF5 session participation (V1 active)
- **PL_001 Continuum** — first turn state machine integrated; SR11 turn UX visible
- **NPC_002 Chorus** — V1+ Tier 4 priority modifier reads onboarding completion timestamp
- **WA_001 Lex** — V1+ AxiomDecl.requires_onboarding_completed hook (gates abilities for new players V1+)

---

## §14 — Status

- **Created:** 2026-04-27 by main session
- **Phase:** DRAFT 2026-04-27 — Q1-Q10 LOCKED via 4-batch deep-dive zero revisions; wireframes Phase 0 preceded (commits 19855a5b + 4c4fd6d7)
- **Status target:** CANDIDATE-LOCK after Phase 3 review cleanup + closure pass + downstream coordination notes
- **Companion docs:**
  - [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q10 LOCKED matrix §10)
  - [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (9-system survey; BG3 + Disco Elysium + AI Dungeon hybrid V1 anchor)
  - [`wireframes/`](wireframes/) — 12 files HTML/CSS/MD; FE-first design committed 19855a5b + 4c4fd6d7
  - [`wireframes/ACTOR_SETTINGS_AUDIT.md`](wireframes/ACTOR_SETTINGS_AUDIT.md) — 46 V1 actor settings × 14 features inventory
  - [`catalog/cat_03_PO_player_onboarding.md`](../../catalog/cat_03_PO_player_onboarding.md) (axioms + entries + deferrals)
  - [`_index.md`](_index.md) (folder index)
- **4-commit cycle:**
  - 0/4 wireframes Phase 0 (commits 19855a5b + 4c4fd6d7) — FE-first wireframes (10 HTML + CSS + audit MD)
  - 1/4 Phase 0 backend kickoff (commit 9245666c) — concept notes + reference survey + index update
  - 2/4 DRAFT (this commit) — PO_001_player_onboarding.md spec + boundary updates + catalog seed; WITH `[boundaries-lock-claim]`
  - 3/4 Phase 3 cleanup (next commit) — self-review fixes + downstream coordination notes
  - 4/4 CANDIDATE-LOCK closure (next commit) — final lock + RESOLVES PCS-D1 + PCS-D10 declarations + `[boundaries-lock-release]`
