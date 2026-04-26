# ACT_001 — Actor Foundation

> **Conversational name:** "Actor" (ACT). Tier 5 Actor Substrate Foundation feature owning per-actor unified `actor_core` (always present; identity layer L1) + sparse `actor_chorus_metadata` (AI-drive metadata; L3 control state) + bilateral `actor_actor_opinion` (per-(observer, target); L3 relationship) + `actor_session_memory` (per-(actor, session); L3 LLM context). Replaces the `npc` aggregate anomaly (only Tier 5 substrate feature NOT per-actor unified pre-ACT_001). Resolves 3 unification opportunities at behavior layer simultaneously.
>
> **Boundary discipline (3-layer architectural model):**
>
> - **L1 Identity** — `actor_core` (always present post-creation; canonical_traits + flexible_state + knowledge_tags + voice_register + core_beliefs_ref)
> - **L2 Capability/Kind** — encoded in ActorId variant (PC / NPC / Synthetic); stable post-creation
> - **L3 Control source** — DYNAMIC (User / AI / Engine); determines population of sparse extensions
>   - Control = User → PC online → no `actor_chorus_metadata` row
>   - Control = AI → NPC always (V1) OR PC offline V1+ → `actor_chorus_metadata` row populated
>   - Control = Engine → Synthetic → no narrative substrate V1
>
> **Category:** ACT — Actor Foundation (Tier 5 Actor Substrate; unification refactor 2026-04-27)
> **Status:** DRAFT 2026-04-27 (Phase 0 CONCEPT 1c0d2d7 → DRAFT 2/5 this commit; Q1-Q6 LOCKED via main session deep-dive 2 REVISIONS — Q3 REVISION on AI-controls-PC-offline insight + Q6 user-revised to full unify all 3 opportunities)
> **Stable IDs in this file:** `ACT-A*` axioms · `ACT-D*` deferrals · `ACT-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) (sibling pattern; ActorKind discrimination); [02_storage R08](../../02_storage/R08_npc_memory_split.md) (schema split UPDATED in commit 3/5); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md) (display strings); [07_event_model EVT-A10](../../07_event_model/02_invariants.md) (event log = universal SSOT); [WA_003 Forge](../02_world_authoring/WA_003_forge.md) (forge_audit_log).
> **Defers to:** future PCS_001 (PC Substrate; owns pc_user_binding + pc_mortality_state + pc_stats_v1_stub on ACT_001 stable base); V1+ AI-controls-PC-offline activation feature (populates `actor_chorus_metadata` for offline PCs); V1+ multi-PC realities (bilateral PC↔PC opinion); V1+ NPC↔NPC drama (sect rivalry opinion); V2+ WA_002 Heresy (cross-reality migration).
> **Event-model alignment:** Actor events = EVT-T4 System sub-types `ActorBorn` (canonical seed; replaces NPC_001 R8 implicit) + `ActorChorusMetadataBorn` (sparse; NPCs only V1) + EVT-T8 Administrative `Forge:EditActorCore` + `Forge:EditChorusMetadata` + `Forge:EditActorOpinion` + `Forge:EditActorSessionMemory` V1 active + EVT-T3 Derived (`aggregate_type=actor_actor_opinion` Update + `aggregate_type=actor_session_memory` Update — preserved from NPC_001 §13 session-end derivation). No new EVT-T* category.

---

## §1 User story (NPC_001 unification + future-proofing AI-controls-PC-offline V1+)

### V1 SPIKE_01 Wuxia preset (post-unify; behavior identical to current NPC_001)

| Actor | Kind | actor_core row | actor_chorus_metadata row | actor_session_memory rows | actor_actor_opinion rows |
|---|---|---|---|---|---|
| Lý Minh (PC) | PC | ✓ (canonical_traits + flexible_state + knowledge_tags + voice_register + core_beliefs_ref) | ✗ (PC always user-driven V1; no row) | (chat-service stores PC chat history; world-service no row V1) | ✓ V1+ PC view of NPCs (deferred ACT-D2) |
| Du sĩ (NPC) | NPC | ✓ | ✓ (greeting_obligation + priority_tier_hint + desires) | ✓ per-(du_si, session_id) | ✓ Du sĩ → Lý Minh (V1 active) |
| Tiểu Thúy (NPC) | NPC | ✓ | ✓ | ✓ | ✓ |
| Lão Ngũ (NPC) | NPC | ✓ | ✓ | ✓ | ✓ |
| ChorusOrchestrator | Synthetic | ✗ (V1 forbidden) | ✗ | ✗ | ✗ |

### V1+ runtime examples (preserved from NPC_001; renamed actor_*)

- **Du sĩ session-end opinion derivation** → V1 active: `actor_actor_opinion` row updated for (observer=du_si, target=ly_minh) — same logic as NPC_001 §13 (per-session derivation; trust + familiarity + stance_tags); preserves V1 functionality.
- **Du sĩ session_memory rolling summary** → V1 active: `actor_session_memory` row updated per-(du_si, session_id); same R8-L2 limits (≤100 facts; ≤2000 char summary).
- **Lý Minh quotes meta-knowledge in turn 5** (SPIKE_01 obs#5) → triggers npc reactions; opinion drift derived at session-end; preserves canonical reproducibility.

### V1+ AI-controls-PC-offline activation example (deferred ACT-D1)

- PC Lý Minh logs out → control source transitions User → AI
  - V1+ feature emits `ActorControlSourceChange { actor_id: ly_minh, before: User, after: AI }`
  - `actor_chorus_metadata` row CREATED for ly_minh (greeting_obligation + priority_tier_hint + desires populated by author/AI)
  - Chorus orchestrator (NPC_002) treats Lý Minh as AI-driven actor; same priority resolution logic as NPCs
- PC Lý Minh logs back in → control source transitions AI → User
  - V1+ feature emits `ActorControlSourceChange { actor_id: ly_minh, before: AI, after: User }`
  - `actor_chorus_metadata` row REMOVED for ly_minh (or marked inactive; defer detail to V1+ activation)

### V1+ NPC↔NPC drama example (deferred ACT-D3)

- Du sĩ and Lão Ngũ are both members of Đông Hải Đạo Cốc; rival sect Ma Tông NPCs spawn nearby
- Sect rivalry triggers V1+ opinion modifiers on `actor_actor_opinion` (observer=du_si, target=ma_tong_member) → trust=-50; stance_tags=["wary"]
- NPC_002 Chorus Tier 4 priority modifier reads REP_001 + actor_actor_opinion for cross-NPC dynamics

**This feature design specifies:** 4 unified per-actor aggregates replacing R8-locked `npc` + `npc_session_memory` + `npc_pc_relationship_projection`; 6 V1 reject rule_ids in `actor.*` namespace; 3-layer architectural model preserving compile-time PC vs NPC discrimination via ActorId variants while unifying storage; canonical seed flow for NPCs (always populated chorus_metadata) + PC default sparse (no chorus_metadata V1); future-proofing AI-controls-PC-offline V1+ + multi-PC realities V1+ + NPC↔NPC drama V1+ all simultaneously.

After this lock: NPC_001 closure-pass-extension transfers 3 aggregates to ACT_001; NPC_002 Chorus reads via actor_* aggregates; NPC_003 desires field on actor_chorus_metadata; PCS_001 unblocked to build on stable ACT_001 base.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Actor** | unified PC + NPC + Synthetic | EF_001 ActorId variant; ACT_001 owns per-actor substrate |
| **Actor identity** | `actor_core` aggregate | L1 Identity layer; always present post-creation |
| **AI-drive metadata** | `actor_chorus_metadata` aggregate | L3 Control state layer; sparse — populated when control source = AI |
| **Bilateral opinion** | `actor_actor_opinion` aggregate | L3 Relationship layer; per-(observer_actor, target_actor); symmetric pair generation |
| **Session memory** | `actor_session_memory` aggregate | L3 LLM context layer; per-(actor, session); supports AI-driven actor LLM continuity |
| **Control source** | DYNAMIC field (V1 implied by ActorKind; V1+ explicit) | User (PC online) / AI (NPC always; PC offline V1+) / Engine (Synthetic) |
| **Persona assembly** | 4-input combiner read pattern | Reads actor_core + actor_chorus_metadata (if AI-driven) + actor_session_memory + actor_actor_opinion |
| **Sparse storage discipline** | Missing row = "not applicable" semantics | actor_chorus_metadata: missing = not AI-driven; actor_session_memory: missing = no session yet |

### ACT_001 axioms

- **ACT-A1** (Per-actor unified pattern) — All ACT_001 aggregates keyed by ActorId (or composite (ActorId, _) for relationship/session). NO per-NPC-only or per-PC-only ACT_001 aggregates V1. Pattern matches all Tier 5 substrate features (IDF + FF + FAC + REP + PROG + RES + PL_006).
- **ACT-A2** (3-layer architectural model) — L1 Identity (always present), L2 Capability/Kind (stable; encoded in ActorId), L3 Control source (dynamic; sparse aggregate population). Layer assignment determines storage density.
- **ACT-A3** (`actor_core` always present post-creation) — Every non-Synthetic actor has `actor_core` row from creation event onward. Read fallback: missing row = creation event not yet processed (transient; not "default"). Synthetic actors have NO `actor_core` row V1.
- **ACT-A4** (`actor_chorus_metadata` sparse — control-source-driven population) — Row populated ONLY when actor's current control source = AI (NOT just because actor is NPC kind). V1: NPCs always have row (control source = AI always V1); PCs never have row (control source = User always V1). V1+ AI-controls-PC-offline (ACT-D1): PCs populate row when control source transitions User → AI (offline); row removed/inactive when control source transitions AI → User (re-online). Layer assignment is L3 (control state), NOT L2 (kind).
- **ACT-A5** (`actor_actor_opinion` bilateral) — Per-(observer_actor, target_actor) opinion stored. Observer ≠ target enforced (Stage 0 schema reject `actor.opinion_self_target_forbidden`). V1 active patterns: NPC→PC (preserved from npc_pc_relationship_projection); V1+ patterns: PC→NPC + NPC→NPC + PC→PC.
- **ACT-A6** (`actor_session_memory` per-(actor, session)) — Memory facts scoped to specific session; supports LLM context continuity. V1: NPCs populated; V1+ AI-controls-PC-offline: PCs populated when offline (chat-service handoff to world-service via V1+ unification design).
- **ACT-A7** (Synthetic actor forbidden V1) — Universal substrate discipline (matches IDF + FF + FAC + REP + PROG + RES + PL_006). V1+ may relax IF admin-faction synthetic narrative identity needed.
- **ACT-A8** (Cross-reality strict V1) — Reality boundaries enforced V1; V2+ Heresy migration via WA_002 (universal V2+ deferral pattern).

---

## §2.5 Event-model mapping (per [`07_event_model`](../../07_event_model/) EVT-T1..T11)

| Event | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| Actor declared at canonical seed | **EVT-T4 System** | `ActorBorn { actor_id, kind: ActorKind, traits_summary }` | Bootstrap (RealityBootstrapper) | ✓ V1 |
| Chorus metadata declared at canonical seed (NPCs only V1) | **EVT-T4 System** | `ActorChorusMetadataBorn { actor_id }` | Bootstrap | ✓ V1 |
| Actor opinion update (session-end derivation) | **EVT-T3 Derived** | `aggregate_type=actor_actor_opinion`, `delta_kind=Update { observer, target, before, after }` | Aggregate-Owner (world-service; preserved from NPC_001 §13) | ✓ V1 (NPC→PC pattern) |
| Actor session memory update | **EVT-T3 Derived** | `aggregate_type=actor_session_memory`, `delta_kind=Update { actor_id, session_id, fact_added | summary_rewritten }` | Aggregate-Owner (world-service) | ✓ V1 |
| Forge admin edit actor core | **EVT-T8 Administrative** | `Forge:EditActorCore { actor_id, edit_kind, before, after, reason }` | Forge (WA_003) | ✓ V1 |
| Forge admin edit chorus metadata | **EVT-T8 Administrative** | `Forge:EditChorusMetadata { actor_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| Forge admin edit opinion | **EVT-T8 Administrative** | `Forge:EditActorOpinion { observer, target, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| Forge admin edit session memory | **EVT-T8 Administrative** | `Forge:EditActorSessionMemory { actor_id, session_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| Actor control source change (V1+ AI-controls-PC-offline) | **EVT-T3 Derived** | `delta_kind=ActorControlSourceChange { actor_id, before, after }` | (V1+ feature) | ✗ V1+ (ACT-D1) |
| Bilateral PC→NPC opinion (V1+) | **EVT-T3 Derived** | `aggregate_type=actor_actor_opinion`, observer=PC, target=NPC | (V1+ runtime population) | ✗ V1+ (ACT-D2) |
| NPC→NPC opinion (V1+ drama) | **EVT-T3 Derived** | `aggregate_type=actor_actor_opinion`, observer=NPC, target=NPC | (V1+ sect rivalry) | ✗ V1+ (ACT-D3) |

**Event ordering at canonical seed (per PL_001 §16.2):** EntityBorn → PlaceBorn → MapLayoutBorn → SceneLayoutBorn → **ActorBorn** → **ActorChorusMetadataBorn** (NPCs only) → RaceBorn → FamilyBorn → FactionBorn → FactionMembershipBorn → ReputationBorn → (other Tier 5 substrate events). ACT_001 events emit AFTER EF_001/PF_001/MAP/CSC and BEFORE other Tier 5 (since ACT_001 actor_core is the identity foundation other Tier 5 features reference via ActorId).

---

## §3 Aggregate inventory

ACT_001 ships **4 aggregates** V1 (replaces 3 from NPC_001 R8 imports + adds 1 new sparse extension).

### §3.1 `actor_core` (T2 / Reality scope — primary; ALWAYS PRESENT)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_core", tier = "T2", scope = "reality")]
pub struct ActorCore {
    pub actor_id: ActorId,                      // EF_001 §5.1 sibling pattern
    pub glossary_entity_id: GlossaryEntityId,   // canon ref
    pub current_region_id: ChannelId,           // points to a cell channel
    pub current_session_id: Option<SessionId>,  // NPC: ≤1 session at a time per R8-L1; PC: present when online; Synthetic: None
    pub mood: ActorMood,                        // emotional state (-100..+100); generic across kinds (was NpcMood)
    pub core_beliefs: CanonRef,                 // L1 canon reference (book-derived, immutable per realities)
    pub flexible_state: FlexibleState,          // L3 reality-local drift (per-reality emergent)
    // V1+ extensions (additive per I14)
    // pub canon_drift_flags: Vec<CanonDriftFlag>,  // V1+ A6 detector integration (ACT-D7)
}
```

**Key:** `(reality_id, actor_id)`. Unique constraint enforced.

**Storage discipline:**
- T2 + RealityScoped: ~10-20 KB per row, stable (matches R8-L1 NPC sizing)
- One row per `(reality_id, actor_id)` — V1 includes PCs + NPCs; Synthetic excluded
- ALWAYS PRESENT post-creation (ACT-A3); sparse storage discipline does NOT apply (every actor has core row)

**Mutability:**
- V1: Mutable via canonical seed (ActorBorn) + Forge admin (Forge:EditActorCore) + runtime mood/flexible_state drift (preserved from NPC_001 §13 session-end derivation pattern)

**Renamed from NPC_001 §3.1 `npc`:**
- Field `npc_id: NpcId` → `actor_id: ActorId` (sibling pattern allows ActorKind discrimination)
- Field `mood: NpcMood` → `mood: ActorMood` (type renamed; same shape; kind-agnostic; -100..+100)
- Field `current_session_id: Option<SessionId>` SEMANTICS preserved: None = actor not in session (NPC idle/ambient; PC offline)
- All other fields preserved; semantics preserved (current_region_id + glossary_entity_id + core_beliefs + flexible_state)

**Synthetic actors forbidden V1 (ACT-A7):**
- Reject `actor.synthetic_actor_forbidden` Stage 0 schema for actor.kind == ActorKind::Synthetic.

**Cross-reality strict V1 (ACT-A8):**
- Reject `actor.cross_reality_mismatch` Stage 0 schema for cross-reality reads.

### §3.2 `actor_chorus_metadata` (T2 / Reality scope — sparse; AI-drive metadata)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_chorus_metadata", tier = "T2", scope = "reality")]
pub struct ActorChorusMetadata {
    pub actor_id: ActorId,                      // FK to actor_core
    pub greeting_obligation: GreetingObligation,
    pub priority_tier_hint: PriorityTierHint,
    pub desires: Vec<DesireDecl>,               // renamed from NpcDesireDecl (kind-agnostic; NPC_003 ownership transfers)
    // V1+ extensions (additive per I14)
    // pub control_source: ControlSource,       // V1+ explicit (ACT-D1; V1 implied by ActorKind = NPC)
    // pub last_ai_drive_at_turn: Option<u64>,  // V1+ AI-controls-PC-offline tracking (ACT-D1)
}
```

**Key:** `(reality_id, actor_id)`. Sparse storage (Q3 LOCKED).

**Storage discipline:**
- Sparse: V1 NPCs always have row; PCs NEVER have row; Synthetic NEVER have row
- Missing row = "not AI-driven" (V1 implied by ActorKind = PC OR Synthetic)
- V1+ AI-controls-PC-offline activation: PC online → no row; PC offline → row created; PC re-online → row removed/inactive (defer activation detail to V1+ feature)

**Mutability:**
- V1: Mutable via canonical seed (ActorChorusMetadataBorn for NPCs) + Forge admin (Forge:EditChorusMetadata)
- V1+: NPC_002 Chorus may emit runtime updates (priority_tier_hint adjustments; desires drift); deferred to V1+ when concrete use case ships

**NPC_003 Desires field transfer:**
- Was `npc.desires: Vec<NpcDesireDecl>` (npc aggregate field added 2026-04-26)
- Now `actor_chorus_metadata.desires: Vec<DesireDecl>` (renamed type; transferred field)
- NPC_003 closure-pass-extension transfers ownership in commit 3/5

### §3.3 `actor_actor_opinion` (T2 / Reality scope — sparse bilateral)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_actor_opinion", tier = "T2", scope = "reality")]
pub struct ActorActorOpinion {
    pub id: ActorActorOpinionId,                // = uuidv5(observer_actor_id, target_actor_id)
    #[dp(indexed)] pub observer_actor_id: ActorId,
    #[dp(indexed)] pub target_actor_id: ActorId,
    pub trust: i16,                             // -100..+100 (preserved from npc_pc_relationship_projection)
    pub familiarity: u16,                       // 0..u16::MAX (interaction count, capped)
    pub stance_tags: Vec<StanceTag>,            // preserved closed set
    pub last_updated_turn: u64,                 // for staleness telemetry
    // V1+ extensions (additive per I14)
    // pub opinion_drift_curve: Option<OpinionDriftCurve>, // V1+ sect rivalry decay (ACT-D3)
}
```

**Key:** `(reality_id, observer_actor_id, target_actor_id)`. Sparse storage.

**Bilateral semantics (ACT-A5):**
- Per-(observer, target) — symmetric pair NOT enforced (du_si→ly_minh and ly_minh→du_si stored as 2 SEPARATE rows; values may differ)
- V1 active patterns:
  - **NPC→PC** (preserved from npc_pc_relationship_projection; session-end derivation via NPC_001 §13)
- V1+ patterns:
  - **PC→NPC** (V1+ runtime population per ACT-D2)
  - **NPC→NPC** (V1+ sect rivalry drama per ACT-D3)
  - **PC→PC** (V1+ multi-PC realities per ACT-D4)

**Constraints:**
- Observer ≠ target enforced; reject `actor.opinion_self_target_forbidden` Stage 0 schema
- Synthetic actors as observer or target rejected (`actor.synthetic_actor_forbidden`)

**Mutability:**
- V1: Session-end derivation (preserved from NPC_001 §13 pattern; world-service writes per-pair) + Forge admin (Forge:EditActorOpinion)
- V1+: Runtime events for V1+ patterns (PC→NPC, NPC→NPC, PC→PC)

**Renamed from NPC_001 §3.3 `npc_pc_relationship_projection`:**
- Field `npc_id: NpcId` → `observer_actor_id: ActorId`
- Field `pc_id: PcId` → `target_actor_id: ActorId`
- Bilateral key composite enables symmetric pair patterns
- Other fields preserved (trust + familiarity + stance_tags + last_updated_turn)

### §3.4 `actor_session_memory` (T2 / Reality scope — per-session)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_session_memory", tier = "T2", scope = "reality")]
pub struct ActorSessionMemory {
    pub id: ActorSessionMemoryId,               // = uuidv5(actor_id, session_id) per R8-L2
    #[dp(indexed)] pub actor_id: ActorId,
    pub session_id: SessionId,                  // session this memory belongs to
    pub summary: String,                        // ≤2000 chars per R8-L2 (preserved)
    pub facts: Vec<MemoryFact>,                 // ≤100 LRU per R8-L2 (preserved)
    pub embeddings_ref: Option<EmbeddingRef>,   // separated to pgvector dedicated table per R8-L6 (preserved)
}
```

**Key:** `(reality_id, actor_id, session_id)`. Unique constraint enforced.

**Storage discipline:**
- T2 + RealityScoped (NOT channel-scoped: memory follows the actor, not the cell)
- Per R8-L2: bounded to 100 facts + 2000-char summary; LRU eviction; rolling LLM summary rewrite every 50 events
- V1: NPCs populated (preserved from NPC_001); PCs no row V1 (chat-service stores PC chat history)
- V1+ AI-controls-PC-offline: PCs populated when AI-driven offline (ACT-D1); world-service handles offline PC LLM context via this aggregate

**Mutability:**
- V1: Session-end derivation (preserved from NPC_001) + Forge admin (Forge:EditActorSessionMemory)
- V1+: PC offline AI-driven session memory population (ACT-D1)

**Renamed from NPC_001 §3.2 `npc_session_memory`:**
- Field `npc_id: NpcId` → `actor_id: ActorId`
- Other fields preserved (summary + facts + embeddings_ref)

### §3.5 NPC_001-kept aggregate (NOT ACT_001-owned)

- **`npc_node_binding`** (NPC_001 §3.4) — NPC writer-node owner mapping with epoch fence; NPC-specific (PC uses entity_binding from PL_001/EF_001; different mechanism). UNCHANGED V1; KEPT under NPC_001 ownership.

### §3.6 V1+ ACT_001 enrichment aggregates (deferred)

- **`actor_canon_drift_log`** (V1+ ACT-D7) — A6 canon-drift detector integration; per-actor drift history.

### §3.7 Future PCS_001-owned aggregates (separate cycle Q2 LOCKED)

- **`pc_user_binding`** (PCS_001) — user_id + current_session + body_memory (xuyên không SoulLayer + BodyLayer)
- **`pc_mortality_state`** (PCS_001) — handoff from WA_006 (Alive/Dying/Dead/Ghost)
- **`pc_stats_v1_stub`** (PCS_001) — V1 minimal stats; V2+ DF7 replaces

---

## §4 Tier+scope (DP-R2)

| Aggregate | Tier | Scope | Read frequency | Write frequency | Storage notes |
|---|---|---|---|---|---|
| `actor_core` | T2 | Reality | ~5-10 per turn (NPC_002 Tier 2-3 priority + persona assembly + V1+ many features read identity) | ~0.01 V1 (canonical seed only); V1+ runtime mood/flexible_state drift via session-end derivation | ALWAYS PRESENT post-creation; ~10-20 KB per row |
| `actor_chorus_metadata` | T2 | Reality | ~2-5 per turn (NPC_002 Chorus priority + persona assembly; only when AI-driven actor in scene; PC scenes V1 don't read this aggregate) | ~0.001 V1 (canonical seed only); V1+ runtime drift via Forge / orchestrator | Sparse: NPCs only V1; PCs V1+ when AI-driven offline (ACT-D1) |
| `actor_actor_opinion` | T2 | Reality | ~1-3 per turn per active scene (NpcOpinion::for_target reads; NPC_002 Tier 2 priority) | ~1 per session-end per (observer, target) interacted | Sparse: per-(observer, target) when interactions create opinion |
| `actor_session_memory` | T2 | Reality | ~5-10 per session (LLM context assembly per turn for AI-driven actor) | ~1 per turn (rolling fact append; rolling summary every 50 events per R8-L2) | Per-(actor, session); bounded R8-L2 (≤100 facts; ≤2000 char summary) |

---

## §5 DP primitives

ACT_001 reuses standard 06_data_plane primitives:

```rust
// V1 reads — actor_core (always present post-creation)
let core = dp::read_aggregate_reality::<ActorCore>(ctx, reality_id, key=actor_id)
    .await?
    .ok_or(ActorError::ActorNotFound)?;  // missing = creation event not yet processed (transient)

// V1 reads — actor_chorus_metadata (sparse; NPCs only V1)
let chorus_md = dp::read_aggregate_reality::<ActorChorusMetadata>(ctx, reality_id, key=actor_id).await?;
let is_ai_driven = chorus_md.is_some();  // V1: NPCs always Some; PCs always None

// V1 reads — actor_actor_opinion (sparse bilateral)
let opinion = dp::read_aggregate_reality::<ActorActorOpinion>(ctx, reality_id,
                  key=(observer_actor_id, target_actor_id))
    .await?;
let trust = opinion.map(|o| o.trust).unwrap_or(0);  // missing = neutral (no interaction yet)

// V1 reads — actor_session_memory (per-session)
let memory = dp::read_aggregate_reality::<ActorSessionMemory>(ctx, reality_id,
                  key=(actor_id, session_id))
    .await?;

// V1 writes — canonical seed (ActorBorn for all actors except Synthetic)
dp::t2_write(ctx, "ActorBorn",
    aggregate=actor_core,
    payload=ActorCore { ... },
    causal_ref=bootstrap_event)
.await?;

// V1 writes — canonical seed (ActorChorusMetadataBorn for NPCs only V1)
dp::t2_write(ctx, "ActorChorusMetadataBorn",
    aggregate=actor_chorus_metadata,
    payload=ActorChorusMetadata { ... },
    causal_ref=bootstrap_event)
.await?;

// V1 writes — Forge admin
dp::t2_write(ctx, "Forge:EditActorCore",
    aggregate=actor_core,
    payload=updated_row,
    causal_ref=forge_admin_event)
.await?;

// V1 writes — session-end opinion derivation (preserved from NPC_001 §13)
dp::t2_write(ctx, "OpinionUpdate",
    aggregate=actor_actor_opinion,
    payload=updated_opinion,
    causal_ref=session_end_event)
.await?;
```

---

## §6 Persona assembly contract (preserved from NPC_001 §6; renamed actor_*)

The actor's "persona" for an LLM prompt is assembled per-call from 4 reads + a deterministic combiner. NOT stored as a flat aggregate.

```rust
pub struct AssembledPersona {
    pub identity: ActorCore,
    pub ai_drive: Option<ActorChorusMetadata>,    // Some when AI-driven
    pub session_memory: Option<ActorSessionMemory>, // Some when actor has session memory
    pub opinion_with_target: Option<ActorActorOpinion>, // Some when actor has opinion of target
}

pub fn assemble_persona(
    ctx: &Ctx,
    actor_id: ActorId,
    session_id: Option<SessionId>,
    target_id: Option<ActorId>,
) -> Result<AssembledPersona, ActorError> {
    let identity = read_actor_core(ctx, actor_id)?;
    let ai_drive = read_actor_chorus_metadata(ctx, actor_id)?;  // None for PCs V1
    let session_memory = match session_id {
        Some(sid) => read_actor_session_memory(ctx, actor_id, sid)?,
        None => None,
    };
    let opinion_with_target = match target_id {
        Some(tid) => read_actor_actor_opinion(ctx, actor_id, tid)?,
        None => None,
    };
    Ok(AssembledPersona { identity, ai_drive, session_memory, opinion_with_target })
}
```

**Key changes from NPC_001 §6:**
- `assemble_persona(npc_id)` → `assemble_persona(actor_id)` (kind-agnostic; PC + NPC both)
- 4 input reads: actor_core (was npc) + actor_chorus_metadata (NEW; sparse) + actor_session_memory (was npc_session_memory) + actor_actor_opinion (was npc_pc_relationship_projection; bilateral)
- Combiner logic preserved; LLM prompt assembly behavior identical V1

---

## §7 Capability requirements (JWT claims)

| Operation | JWT claim required | Notes |
|---|---|---|
| Read `actor_core` | `reality.read` | Standard reality-scope read |
| Read `actor_chorus_metadata` | `reality.read` | Standard reality-scope read; sparse |
| Read `actor_actor_opinion` | `reality.read` | Standard reality-scope read; bilateral |
| Read `actor_session_memory` | `reality.read` | Standard reality-scope read; per-session |
| Write canonical seed (ActorBorn / ActorChorusMetadataBorn) | `bootstrap.canonical_seed` | RealityBootstrapper role only |
| Write Forge admin (Forge:EditActorCore / Forge:EditChorusMetadata / Forge:EditActorOpinion / Forge:EditActorSessionMemory) | `forge.admin` (WA_003 contract) | Reuses WA_003 Forge JWT contract; no new claim |
| Write session-end opinion derivation | (orchestrator JWT; world-service internal) | Aggregate-Owner role; preserved from NPC_001 §13 |
| Write V1+ runtime opinion events (PC→NPC + NPC→NPC + PC→PC) | (V1+ — TBD when V1+ ships) | Aggregate-Owner role |
| Write V1+ AI-controls-PC-offline transitions | (V1+ feature JWT) | (V1+ ACT-D1) |

---

## §8 Pattern choices

### §8.1 Per-actor unified pattern (Q1 LOCKED)

ACT_001 V1 uses unified per-actor aggregate pattern matching all Tier 5 substrate features. Rejects per-NPC-only or per-PC-only aggregates V1.

**Reasoning:**
- Pattern consistency across Tier 5 substrate (8+ features); NPC_001 was anomaly to fix
- Future-proofs PC + NPC + Synthetic uniformly
- Code path simplification: one read pattern for any actor kind
- Substrate-level reuse: PCS_001 + NPC_001 build on top; no per-kind reimplementation

### §8.2 3-layer architectural model (ACT-A2)

L1 Identity (always) + L2 Capability/Kind (stable) + L3 Control source (dynamic).

**Reasoning:**
- Layer assignment determines storage density (L1 always; L3 sparse)
- Future-proofs AI-controls-PC-offline V1+ (L3 dynamic transition)
- Compile-time kind discrimination preserved (L2 encoded in ActorId variant)
- Composition over sum-type: each layer = separate aggregate; sparse storage at L3 prevents bloat

### §8.3 Sparse `actor_chorus_metadata` per Q3 LOCKED REVISION

Sparse storage: NPCs always populated; PCs never populated V1; PCs V1+ populated when AI-driven offline.

**Reasoning (Q3 REVISION):**
- desires + greeting_obligation + priority_tier_hint are L3 AI-drive metadata, NOT L2 NPC-specific
- Future-proofs AI-controls-PC-offline V1+ feature without aggregate refactor (additive activation)
- Naming: `actor_chorus_metadata` (kind-agnostic; references chorus pattern but doesn't lock to NPC)
- Owner: ACT_001 (substrate level — applies to any AI-driven actor)
- NPC_002 Chorus reads from this aggregate; chorus orchestration extends to AI-driven PCs V1+ via same path

### §8.4 Bilateral `actor_actor_opinion` per Q6 LOCKED REVISION

Bilateral key composite (observer_actor_id, target_actor_id) supporting symmetric pair patterns.

**Reasoning (Q6 user-revised to full unify):**
- V1 NPC→PC pattern preserved (npc_pc_relationship_projection migration)
- V1+ PC→NPC + NPC→NPC + PC→PC patterns enabled by bilateral key
- Once AI-controls-PC-offline V1+ ships: PC AI-driven needs to query "PC's opinion of NPC X" — bilateral supports
- Sect rivalry NPC↔NPC drama V1+ enabled
- Multi-PC realities PC↔PC dynamics enabled
- Symmetry NOT enforced — du_si→ly_minh and ly_minh→du_si stored separately; values may differ (asymmetric opinion is realistic)

### §8.5 V1 functionality identical to NPC_001 (preservation)

V1 behavior IDENTICAL to current NPC_001 + NPC_002 + NPC_003 — unification is structural for future-proofing, NOT functional change.

**Reasoning:**
- Migration safety: existing tests + integration scenarios (SPIKE_01 turn 5) reproduce post-unify
- Cross-feature integration preserved (NPC_002 Chorus priority Tier 2-3 reads; persona assembly 4-input contract)
- Renaming + key changes are mechanical; semantics unchanged
- V1+ enrichment (PC bilateral; AI-controls-PC-offline; session memory PC pathway) ADD on top of V1 base

### §8.6 V1 universal substrate discipline (synthetic excluded; cross-reality strict)

ACT-A7 Synthetic forbidden V1 + ACT-A8 Cross-reality strict V1.

**Reasoning:**
- Universal substrate discipline matches all Tier 5 features (IDF + FF + FAC + REP + RES + PROG + PL_006)
- Synthetic actors don't have narrative properties V1 (no desires + no opinion + no session memory)
- V1+ relax IF concrete use case emerges (admin-faction synthetic narrative identity)
- Cross-reality V2+ Heresy via WA_002 (universal V2+ deferral)

---

## §9 Failure-mode UX

| Reject rule | Stage | User-facing message | When fired |
|---|---|---|---|
| `actor.unknown_actor_id` | 0 schema | "Actor không tồn tại trong hiện thực này" (Actor doesn't exist) | Read/write attempt with unknown actor_id |
| `actor.synthetic_actor_forbidden` | 0 schema | (Schema-level; not user-facing) | Synthetic actor cannot have ACT_001 aggregate row |
| `actor.cross_reality_mismatch` | 0 schema | (Schema-level; not user-facing) | actor.reality_id ≠ aggregate.reality_id |
| `actor.kind_specific_field_mismatch` | 0 schema | (Schema-level; not user-facing) | chorus_metadata for non-AI-driven actor V1 (e.g., PC online attempting populate) |
| `actor.opinion_self_target_forbidden` | 0 schema | "Actor không thể có opinion về chính mình" (Actor can't opine self) | observer == target in actor_actor_opinion |
| `actor.duplicate_session_memory` | 0 schema | (Schema-level; not user-facing) | Multi-row per (actor, session) pair |

V1+ reservation rules:
- `actor.bilateral_opinion_unsupported_v1` — V1+ when NPC→NPC + PC→PC events ship (currently V1 NPC→PC only)
- `actor.ai_control_pc_offline_unsupported_v1` — V1+ AI-controls-PC-offline activation
- `actor.canon_drift_detected` — V1+ A6 detector cross-feature integration (ACT-D7)

**Per RES_001 §2 i18n contract:** All `actor.*` rejects use `RejectReason.user_message: I18nBundle` with English `default` field + Vietnamese translation V1 from day 1.

---

## §10 Cross-service handoff (canonical seed flow)

ACT_001 canonical seed flows through standard RealityBootstrapper pipeline:

1. **knowledge-service** ingests book canon → emits `RealityManifest` with `canonical_actors: Vec<CanonicalActorDecl>` (extends with ACT_001 fields)
2. **world-service RealityBootstrapper** validates manifest:
   - Stage 0 schema validation per actor: actor_id valid; kind in {Pc, Npc, (Synthetic excluded V1)}; cross-reality consistency; chorus_metadata fields populated for NPCs (greeting_obligation + priority_tier_hint + desires)
   - Stage 1: emit `ActorBorn` per actor (PC + NPC; NOT Synthetic)
   - Stage 2: emit `ActorChorusMetadataBorn` per NPC (chorus_metadata fields populated)
3. **ACT_001 owner-service** (world-service module) writes `actor_core` rows + `actor_chorus_metadata` rows (NPCs only V1)
4. Downstream features V1+ consume actor substrate:
   - NPC_002 Chorus Tier 2-3 priority reads `actor_core` + `actor_chorus_metadata`
   - V1+ NPC↔NPC drama reads `actor_actor_opinion` for sect rivalry
   - V1+ AI-controls-PC-offline activates `actor_chorus_metadata` PC population
   - PCS_001 future builds on top of ACT_001 stable base

---

## §11 Sequence: Canonical seed (Wuxia 4 NPCs + 1 PC)

```
RealityManifest {
    canonical_actors: vec![
        // PC Lý Minh — actor_core only V1; no chorus_metadata
        CanonicalActorDecl {
            actor_id: ActorId::Pc(PcId(uuid_lm)),
            kind: ActorKind::Pc,
            canonical_traits: CanonicalTraits { name: "Lý Minh", role: "PC", ... },
            flexible_state_init: FlexibleState::default(),
            knowledge_tags: vec![knowledge_tag("modern_tech"), knowledge_tag("wuxia_lore")],
            voice_register: VoiceRegister::TerseFirstPerson,
            core_beliefs_ref: Some(canon_ref("ly_minh_canon")),
            // chorus_metadata fields = None (PC always user-driven V1)
            chorus_metadata: None,
        },

        // NPC Du sĩ — actor_core + chorus_metadata
        CanonicalActorDecl {
            actor_id: ActorId::Npc(NpcId(uuid_dusi)),
            kind: ActorKind::Npc,
            canonical_traits: CanonicalTraits { name: "Du sĩ", role: "scholar", ... },
            flexible_state_init: FlexibleState::default(),
            knowledge_tags: vec![knowledge_tag("daoist_scripture"), knowledge_tag("wuxia_lore")],
            voice_register: VoiceRegister::Novel3rdPerson,
            core_beliefs_ref: Some(canon_ref("du_si_canon")),
            chorus_metadata: Some(ChorusMetadataDecl {
                greeting_obligation: GreetingObligation::Required,
                priority_tier_hint: PriorityTierHint::High,
                desires: vec![desire("preserve_sect_canon"), desire("teach_disciples")],
            }),
        },

        // Tiểu Thúy + Lão Ngũ NPCs — similar shape
        // ...
    ],
}
```

**Validation flow:**
1. Stage 0 schema validation per actor:
   - actor_id valid → ✓
   - kind ∈ {Pc, Npc} (Synthetic rejected per Q4 LOCKED `actor.synthetic_actor_forbidden`) → ✓
   - chorus_metadata Some for NPCs / None for PCs (V1 control source discipline; V1+ AI-controls-PC-offline relaxes for offline PCs) → ✓
2. RealityBootstrapper emits per actor:
   - 1 EVT-T4 ActorBorn (all 5 actors: 1 PC + 4 NPCs)
   - 4 EVT-T4 ActorChorusMetadataBorn (NPCs only V1)
3. ACT_001 owner-service writes:
   - 5 rows in actor_core (PC + 4 NPCs); each row populates from CanonicalActorDecl.flexible_state_init → ActorCore.flexible_state, mood_init → ActorCore.mood, etc.
   - 4 rows in actor_chorus_metadata (NPCs only); each row populates from CanonicalActorDecl.chorus_metadata.{greeting_obligation, priority_tier_hint, desires}
4. Causal-ref chain: bootstrap_event → ActorBorn → row_insert → ActorChorusMetadataBorn (NPC only) → row_insert

**Read examples post-bootstrap:**
- `read_actor_core(ly_minh)` → PC core (canonical_traits + knowledge_tags + voice_register + ...)
- `read_actor_chorus_metadata(ly_minh)` → None (PC; not AI-driven V1)
- `read_actor_core(du_si)` → NPC core
- `read_actor_chorus_metadata(du_si)` → Some(chorus_metadata) with desires + greeting_obligation + priority_tier_hint
- `read_actor_actor_opinion(du_si, ly_minh)` → None (no interaction yet; lazy-create at first session-end derivation)
- `read_actor_session_memory(du_si, session_1)` → None (no session yet)

---

## §12 Sequence: Session-end opinion derivation (preserved from NPC_001 §13)

```
Session ends (PC /signoff or 30-min idle timeout)
  → world-service iterates each (NPC, PC) pair the session interacted with
  → For each pair: compute trust_delta = sum(fact.importance × valence_sign) over session_facts
  → Merge with existing actor_actor_opinion row
    → If row exists: update trust + familiarity + stance_tags + last_updated_turn
    → If row doesn't exist: lazy-create with computed values
  → Commit via t2_write per NPC_001 §13 sequence
  → Causal_ref to session-end SystemEvent
  → AC-ACT-V1+1 covers V1 NPC→PC pattern (preserved); V1+ patterns deferred (ACT-D2..D4)
```

V1: NPC→PC pattern ONLY (preserved from npc_pc_relationship_projection); V1+ enables PC→NPC + NPC→NPC + PC→PC.

---

## §13 Sequence: Forge admin EditActorCore (V1 active)

```
Author types in Forge UI: "Edit Du sĩ mood to be more cautious; flexible_state.disposition = 'wary'"
  → Forge frontend emits POST /v1/forge/actor/core/edit
       { actor_id: "du_si", edit_kind: "UpdateFlexibleState",
         field_path: "disposition", before: "neutral", after: "wary",
         reason: "post-meta-knowledge moment in turn 5" }
  → world-service Forge handler validates:
     - JWT has forge.admin claim
     - actor_id valid
     - actor not synthetic
  → 3-write atomic transaction:
     1. Read existing actor_core row → before snapshot
     2. Write actor_core row { flexible_state.disposition: "wary", ... }
     3. Emit EVT-T8 Forge:EditActorCore { actor_id, edit_kind, before, after, reason }
     4. Write forge_audit_log entry referencing EVT-T8 event_id
  → AC-ACT-7 covers atomicity (3-write transaction)
```

---

## §14 Sequence: V1+ AI-controls-PC-offline transition (deferred ACT-D1)

```
// V1+ EXAMPLE (NOT V1 — deferred)
PC Lý Minh logs out (session ends; control source transitions User → AI)
  → V1+ feature emits ActorControlSourceChange { actor_id: ly_minh, before: User, after: AI }
  → ACT_001 owner-service receives event
  → Lazy-create actor_chorus_metadata row for ly_minh:
     { greeting_obligation: GreetingObligation::Optional,
       priority_tier_hint: PriorityTierHint::Medium,
       desires: vec![desire("continue_main_quest"), desire("avoid_sect_rivals")] }
  → Chorus orchestrator (NPC_002) treats Lý Minh as AI-driven actor (same priority resolution path)
  → V1+ AI-controls-PC-offline scheduler may activate PC offline scene generation
PC Lý Minh logs back in (control source transitions AI → User)
  → V1+ feature emits ActorControlSourceChange { actor_id: ly_minh, before: AI, after: User }
  → ACT_001 owner-service deletes actor_chorus_metadata row (or marks inactive; defer to V1+ design)
  → Chorus orchestrator removes Lý Minh from AI-driven priority pool
```

V1+ enrichment requires V1+ AI-controls-PC-offline feature design.

---

## §15 Acceptance criteria (LOCK gate)

V1 (10 testable scenarios):

| AC | Scenario | Expected outcome |
|---|---|---|
| **AC-ACT-1** | Wuxia canonical bootstrap declares 5 actors (1 PC + 4 NPCs; NO Synthetic per Q4 LOCKED) | RealityBootstrapper emits 5 EVT-T4 ActorBorn events + 4 EVT-T4 ActorChorusMetadataBorn events (NPCs only); 5 actor_core rows + 4 actor_chorus_metadata rows written; PC Lý Minh has actor_core but NO actor_chorus_metadata row V1 (control source = User; sparse storage discipline) |
| **AC-ACT-2** | actor_core read returns identity for any kind (PC + NPC) | Read path uniform; PC + NPC return same shape (canonical_traits + flexible_state + knowledge_tags + voice_register + core_beliefs_ref + mood) |
| **AC-ACT-3** | actor_chorus_metadata sparse storage validated | PC has NO row V1; NPC has row; missing row read returns None (not "not AI-driven" by hard code; semantics) |
| **AC-ACT-4** | actor_actor_opinion bilateral keys validated | observer ≠ target enforced (`actor.opinion_self_target_forbidden`); bilateral pair (du_si, ly_minh) and (ly_minh, du_si) stored separately |
| **AC-ACT-5** | actor_session_memory per-(actor, session) keying | du_si has 2 session memories (session_1 + session_2) as separate rows; uuidv5 keying matches R8-L2 spec |
| **AC-ACT-6** | NPC_001 closure-pass-extension verified | NPC_001 §3 references actor_core (not npc) + actor_session_memory (not npc_session_memory) + actor_actor_opinion (not npc_pc_relationship_projection); npc_node_binding KEPT |
| **AC-ACT-7** | NPC_002 closure-pass-extension verified | Chorus priority Tier 2-3 reads actor_core (not npc); NpcOpinion::for_pc renamed ActorOpinion::for_target reads actor_actor_opinion |
| **AC-ACT-8** | NPC_003 closure-pass-extension verified | desires field reads from actor_chorus_metadata.desires (not npc.desires); type renamed DesireDecl |
| **AC-ACT-9** | Synthetic actor rejected V1 | Stage 0 schema reject `actor.synthetic_actor_forbidden` for ChorusOrchestrator/BubbleUpAggregator/etc. |
| **AC-ACT-10** | 02_storage R08 update verified | Schema split applied; backward-incompatible documented; ACT_001 ownership note added; main session attribution |

V1+ deferred (4 scenarios):

| AC | Scenario | V1+ enrichment |
|---|---|---|
| **AC-ACT-V1+1** | V1+ AI-controls-PC-offline activates actor_chorus_metadata for PC | ACT-D1 |
| **AC-ACT-V1+2** | V1+ PC↔NPC bilateral opinion (PC view of NPC populated) | ACT-D2 |
| **AC-ACT-V1+3** | V1+ NPC↔NPC opinion (sect rivalry drama) | ACT-D3 |
| **AC-ACT-V1+4** | V1+ PC↔PC opinion (multi-PC realities) | ACT-D4 |

---

## §16 Boundary registrations (in same commit chain)

This DRAFT cycle (commits 2-3/5) adds the following boundary entries:

### `_boundaries/01_feature_ownership_matrix.md` (commit 2/5 + 3/5)

- 4 NEW aggregates owned by ACT_001: actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory
- 3 transferred from NPC_001 R8 imports (REMOVE old npc + npc_session_memory + npc_pc_relationship_projection rows; replace with ACT_001-owned)
- 2 NEW EVT-T4 sub-types: ActorBorn + ActorChorusMetadataBorn
- 4 NEW EVT-T8 sub-shapes: Forge:EditActorCore + Forge:EditChorusMetadata + Forge:EditActorOpinion + Forge:EditActorSessionMemory
- 2 NEW EVT-T3 entries: actor_actor_opinion + actor_session_memory (replaces NPC_001-owned npc_pc_relationship_projection + npc_session_memory entries)
- 1 NEW namespace: `actor.*` (6 V1 + 3 V1+ reservations)
- RealityManifest envelope: canonical_actors ownership transfer (PL_001 + NPC_001 → ACT_001 unified) + chorus_metadata fields additive
- 1 NEW stable-ID prefix: `ACT-*`

### `_boundaries/02_extension_contracts.md` (commit 2/5)

- §1.4 namespace registration: `actor.*` (6 V1 rules + 3 V1+ reservations)
- §2 RealityManifest CanonicalActorDecl extension: chorus_metadata fields (Optional; populated for NPCs)

### `_boundaries/99_changelog.md` (commits 2/5 + 5/5)

- Commit 2/5 entry: ACT_001 DRAFT promotion + boundary register
- Commit 5/5 entry: ACT_001 closure pass + lock release

### `02_storage/R08_npc_memory_split.md` (commit 3/5)

- Schema split: npc → actor_core + actor_chorus_metadata
- Rename: npc_session_memory → actor_session_memory; npc_pc_relationship_projection → actor_actor_opinion (bilateral key)
- Ownership note: ACT_001 owns 3 split aggregates (formerly R8-NPC_001-imported); NPC_001 keeps `npc_node_binding`
- R8 changelog appended

### `catalog/cat_00_ACT_actor_foundation.md` (commit 2/5; created)

- New catalog file with ACT-A1..A8 axioms + ACT-D1..D10 deferrals + 14+ catalog entries

### `features/00_actor/_index.md` (commit 2/5)

- ACT_001 row updated to DRAFT 2026-04-27

### `features/05_npc_systems/NPC_001_cast.md` (commit 3/5; closure-pass-extension)

- §3 aggregate ownership transfers (3 aggregates moved to ACT_001)
- §6 persona assembly updated (4 inputs renamed actor_*)
- §14 acceptance scenarios names updated

### `features/05_npc_systems/NPC_002_chorus.md` (commit 3/5; closure-pass-extension)

- Read paths updated (NpcOpinion::for_pc → ActorOpinion::for_target)
- Tier 2-3 priority reads actor_core
- Chorus orchestration extends to AI-driven PCs V1+ via same path

### `features/05_npc_systems/NPC_003_desires.md` (commit 3/5; closure-pass-extension)

- desires field ownership transfer (npc.desires → actor_chorus_metadata.desires)
- Type rename NpcDesireDecl → DesireDecl

---

## §17 Open questions deferred + landing point

### V1+ deferrals (ACT-D1..ACT-D10)

| ID | Item | Landing point |
|---|---|---|
| **ACT-D1** | V1+ AI-controls-PC-offline feature activation | Activates actor_chorus_metadata for offline PCs; new feature design when concrete |
| **ACT-D2** | V1+ PC↔NPC bilateral opinion runtime population | Activates with AI-controls-PC-offline; PC AI-driven needs query "PC's opinion of NPC" |
| **ACT-D3** | V1+ NPC↔NPC opinion (sect rivalry drama) | Sect drama feature consumes actor_actor_opinion bilateral pattern |
| **ACT-D4** | V1+ PC↔PC opinion (multi-PC realities) | Multiplayer feature activation |
| **ACT-D5** | V1+ NPC xuyên không (currently PC-only V1 via PCS_001 body_memory) | NPC body-substitution feature when concrete |
| **ACT-D6** | V2+ cross-reality migration | Universal V2+ Heresy via WA_002 |
| **ACT-D7** | V1+ canon-drift detector integration | A6 detector + actor_core knowledge_tags + actor_session_memory |
| **ACT-D8** | V1+ NPC_003 desires lifecycle events | Currently author-only via Forge V1; runtime events V1+ |
| **ACT-D9** | V1+ actor_chorus_metadata schema enrichment | Additional AI-drive metadata as V1+ features ship |
| **ACT-D10** | V1+ unified node_binding | Currently NPC-only npc_node_binding; PC offline V1+ may need consolidation |

### Open questions (NONE V1)

All Q1-Q6 LOCKED via main session deep-dive 2026-04-27 (Q3 REVISION + Q6 user-revised to full unify). No outstanding V1 design questions.

---

## §18 Cross-references

### Resolved deferrals from upstream features

- **NPC_001 R8 import anomaly** — `npc` aggregate (per-NPC) was only Tier 5 substrate not unified per-actor → ✅ RESOLVED via actor_core + actor_chorus_metadata split
- **NPC_001 §3.3 npc_pc_relationship_projection one-directional** — only NPC→PC opinion → ✅ RESOLVED via actor_actor_opinion bilateral
- **NPC_001 §3.2 npc_session_memory NPC-scoped** — PC session memory fragmented in chat-service → ✅ RESOLVED via actor_session_memory unified

### Consumes from locked features

- **EF_001 §5.1** ActorId source-of-truth — sibling pattern; ActorKind discrimination
- **02_storage R08** schema spec (UPDATED in commit 3/5)
- **RES_001 §2.3** I18nBundle pattern — display strings; reject user_message
- **WA_003** Forge audit log — EVT-T8 sub-shapes use forge_audit_log pattern (3-write atomic)
- **07_event_model EVT-A10** event log = universal SSOT — ACT_001 events flow in channel stream

### Consumed by future features (V1+)

- **NPC_001 Cast V1** — closure-pass-extension reads actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory; persona assembly §6
- **NPC_002 Chorus V1** — closure-pass-extension; Tier 2-3 priority reads actor_core; ActorOpinion::for_target reads actor_actor_opinion
- **NPC_003 NPC Desires V1** — closure-pass-extension; desires field reads actor_chorus_metadata.desires
- **PCS_001 V1+** — builds on ACT_001 stable base; owns pc_user_binding + pc_mortality_state + pc_stats_v1_stub
- **AI-controls-PC-offline V1+ (ACT-D1)** — activates actor_chorus_metadata PC population
- **Multi-PC realities V1+ (ACT-D4)** — bilateral PC↔PC opinion via actor_actor_opinion
- **Sect rivalry NPC↔NPC drama V1+ (ACT-D3)** — bilateral NPC↔NPC opinion
- **A6 canon-drift detector V1+ (ACT-D7)** — reads actor_core knowledge_tags + actor_session_memory facts
- **REP_001 V1+** — already locked CANDIDATE-LOCK; reads actor_core for actor identity

---

## §19 Implementation readiness checklist

- [ ] **§1** User story locked (Wuxia 5 actors + V1+ runtime examples)
- [ ] **§2** Domain concepts + ACT-A1..A8 axioms locked
- [ ] **§2.5** Event-model mapping locked (2 EVT-T4 + 4 EVT-T8 + 2 EVT-T3 V1; V1+ reserved)
- [ ] **§3** Aggregate inventory: 4 ACT_001 aggregates + 1 NPC_001-kept + 3 PCS_001-future
- [ ] **§4** Tier+scope DP-R2 annotations
- [ ] **§5** DP primitives reuse standard
- [ ] **§6** Persona assembly contract preserved (4-input combiner)
- [ ] **§7** Capability requirements: reuses WA_003 forge.admin JWT
- [ ] **§8** Pattern choices: 6 sub-sections covering Q1-Q6 LOCKED decisions
- [ ] **§9** Failure-mode UX: 6 V1 reject rules + 3 V1+ reservations + Vietnamese I18n
- [ ] **§10** Cross-service handoff via standard RealityBootstrapper pipeline
- [ ] **§11** Sequence: Canonical seed (Wuxia 5 actors)
- [ ] **§12** Sequence: Session-end opinion derivation (preserved from NPC_001 §13)
- [ ] **§13** Sequence: Forge admin EditActorCore (V1 active)
- [ ] **§14** Sequence: V1+ AI-controls-PC-offline (deferred ACT-D1)
- [ ] **§15** Acceptance criteria: 10 V1-testable AC-ACT-1..10 + 4 V1+ deferred
- [ ] **§16** Boundary registrations (in same commit chain — commits 2-5/5)
- [ ] **§17** Open questions deferred: 10 deferrals (ACT-D1..ACT-D10); 0 V1 open Q
- [ ] **§18** Cross-references: 3 RESOLVED upstream (NPC_001 anomalies) + 5 consumed-from + 9 consumed-by-future
- [ ] **§19** This checklist (filling at Phase 3 cleanup commit 4/5)

**Status transition:** DRAFT 2026-04-27 (commit 2/5 this commit) → cascading closure-pass-extensions (commit 3/5) → Phase 3 cleanup (commit 4/5) → **CANDIDATE-LOCK** in commit 5/5 → **LOCK** when AC-ACT-1..10 pass integration tests + V1+ scenarios after V1+ enrichment ships.

**Next** (when CANDIDATE-LOCK granted): world-service can scaffold 4 ACT_001 aggregates + Forge admin handlers; NPC_001 + NPC_002 + NPC_003 closure-pass-extensions applied in commit 3/5; PCS_001 unblocked to build on stable ACT_001 base (separate cycle Q2 LOCKED).
