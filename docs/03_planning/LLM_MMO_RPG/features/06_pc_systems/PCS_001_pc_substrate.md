# PCS_001 — PC Substrate

> **⚠ CLOSURE-PASS-EXTENSION 2026-04-27 — DF05_001 Session/Group Chat CANDIDATE-LOCK 71a60346:**
>
> `pc_user_binding.current_session: Option<SessionId>` field consumes DF05_001 SessionId — populated when PC is in Active session per DF5-A5 (one Active session per actor); cleared on session-leave or session-close cascade. PCS_001 PC body_memory (PCS-D7 reservation: SoulPrimary xuyên không scenario) feeds DF05_001 LLM persona prompt-assembly during session turns via MemoryProvider trait per §16 SDK contract — `body_memory.{soul,body}.knowledge_tags` informs which knowledge base PC accesses (SoulPrimary 2026 Saigon student vs body 1256 Hangzhou peasant per SPIKE_01 turn 5 literacy slip pattern). Per-PC active-session lookup pattern: `query_session_participation(actor_id=pc, presence ∈ {Connected, Disconnected}, left_fiction_time IS NULL)` — used at PC `/chat` invite to verify DF5-A5 invariant + at cell-leave cascade per PL_001 §13 closure-pass-extension. DF5-A4 PC anchor invariant requires `actor_core.kind == ActorKind::Pc` (DF5-C1 cross-aggregate validator — verifies via PCS_001 + ACT_001 join). NO change to PCS_001 aggregates; CANDIDATE-LOCK status PRESERVED. MEDIUM magnitude — consumer trait import + cross-aggregate validator coordination. Reference: [DF05_001 §3.2 session_participation](../DF/DF05_session_group_chat/DF05_001_session_foundation.md#32-session_participation-t2--reality-sparse-per-session-actor--per-participant) + [DF05_001 §16 SDK Architecture](../DF/DF05_session_group_chat/DF05_001_session_foundation.md#16--sdk-architecture-locked-2026-04-27).

> **Conversational name:** "PC Substrate" (PCS). Tier 5 Actor Substrate Foundation feature owning per-PC `pc_user_binding` aggregate (sparse PC-only — user_id + current_session + body_memory) + per-PC `pc_mortality_state` aggregate (sparse PC-only — Alive/Dying/Dead/Ghost; handoff from WA_006). Builds on stable ACT_001 base (actor_core for L1 identity unified across PC + NPC; actor_chorus_metadata sparse for AI-drive metadata; actor_actor_opinion bilateral; actor_session_memory unified). PC-only L3 user-control + body-memory layer post-ACT_001 unification.
>
> **Boundary discipline:**
>
> - **L1 Identity** (ACT_001 actor_core; always present) — ABSORBED post-unify; PCS_001 doesn't own
> - **L2 Capability/Kind** (ActorId variant) — PCS_001 owns PcId newtype; ActorKind::Pc discriminator EF_001-owned
> - **L3 Control source / Mortality / Body-memory** — PCS_001 owns PC-specific aggregates here
>
> **Category:** PCS — PC Systems (Tier 5 Actor Substrate post-ACT_001 priority per Q2 LOCKED 2026-04-27)
> **Status:** CANDIDATE-LOCK 2026-04-27 (4-commit cycle complete: Phase 0 3c76f33 → Q1-Q10 LOCKED 1/4 5c34b93 → DRAFT 2/4 67b53cd → Phase 3 3/4 7e3218e → closure 4/4 this commit; Q1-Q10 LOCKED via 6-batch deep-dive 2026-04-27 with 1 REFINEMENT on Q5 + 1 RENAME PcXuyenKhongCompleted → PcTransmigrationCompleted per user direction)
> **Stable IDs in this file:** `PCS-A*` axioms · `PCS-D*` deferrals · `PCS-Q*` decisions
> **Builds on:** [ACT_001 §3.1 actor_core](../00_actor/ACT_001_actor_foundation.md#31-actor_core-t2--reality-scope--primary-always-present) (L1 identity unified); [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) (sibling pattern; ActorKind::Pc); [WA_006 Mortality](../02_world_authoring/WA_006_mortality.md) (mortality_config per-reality singleton; pc_mortality_state aggregate handoff from §6 closure pass); [TDIL_001 §10 clock-split](../17_time_dilation/TDIL_001_time_dilation_foundation.md) (xuyên không 3-clock split contract); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md) (display strings); [07_event_model EVT-A10](../../07_event_model/02_invariants.md) (event log = universal SSOT); [WA_003 Forge](../02_world_authoring/WA_003_forge.md) (forge_audit_log).
> **Defers to:** future PO_001 Player Onboarding (V1+ runtime login flow per Q3 LOCKED PCS-D1); V1+ AI-controls-PC-offline (ACT-D1 — activates actor_chorus_metadata for PCs when offline); V1+ Respawn flow (PCS-D2 per Q7 LOCKED — Dying state V1 frozen until V1+ ships exit); V1+ Reincarnation pattern (PCS-D8); V1+ Possession pattern (PCS-D9); V1+ A6 canon-drift detector integration (PCS-D7 — reads body_memory.{soul,body}.knowledge_tags for SPIKE_01 turn 5 literacy slip); V2+ Heresy WA_002 (cross-reality migration per Q8 LOCKED).
> **Event-model alignment:** PC events = EVT-T4 System sub-type `PcRegistered` (canonical seed PC creation; PCS_001-owned per Q3 LOCKED) + EVT-T8 Administrative `Forge:RegisterPc` + `Forge:BindPcUser` + `Forge:EditPcUserBinding` + `Forge:EditBodyMemory` + `Forge:EditPcMortalityState` (5 V1 active per Q3+Q5+Q7 LOCKED) + EVT-T3 Derived (`aggregate_type=pc_mortality_state` with delta_kinds DyingTransition + DeathTransition + GhostTransition V1 active; RespawnTransition + ResurrectionTransition + GhostDispersedTransition V1+ deferred PCS-D2 per Q7 LOCKED) + EVT-T1 Submitted `PcTransmigrationCompleted` (renamed from PcXuyenKhongCompleted; schema active V1; runtime emission V1+ deferred PCS-D-N per Q10 LOCKED). No new EVT-T* category.

---

## §1 User story (Wuxia Lý Minh xuyên không + native PC + V1+ multi-PC charter)

### V1 SPIKE_01 Wuxia preset (RealityManifest.canonical_actors with kind=Pc)

| Actor | Kind | Spawn cell | body_memory_init | user_id_init |
|---|---|---|---|---|
| Lý Minh (PC) | PC | hangzhou_tieu_diem_inn_cell | Some(SoulPrimary; soul=2026 Saigon student / body=1256 Hangzhou peasant Trần Phong) | None at canonical seed; bound via Forge admin V1 OR runtime login V1+ |

V1 cap=1 PC per reality (per Q9 LOCKED Stage 0 schema validator); V1+ multi-PC charter coauthors (PCS-D3).

### V1 canonical PC declaration shape

```rust
CanonicalActorDecl {
    actor_id: ActorId::Pc(PcId(uuid_lm)),
    kind: ActorKind::Pc,
    glossary_entity_id: glossary_entity_id("ly_minh_actor_canon"),
    spawn_cell: channel_id("hangzhou_tieu_diem_inn_cell"),
    canonical_traits: CanonicalTraits { name: "Lý Minh", role: "PC scholar", ... },
    flexible_state_init: FlexibleState::empty(),
    knowledge_tags: vec![/* aggregated from soul + body */],
    voice_register: VoiceRegister::TerseFirstPerson,
    core_beliefs_ref: Some(glossary_entity_id("ly_minh_belief_set")),
    mood_init: ActorMood::NEUTRAL,
    chorus_metadata: None,                              // PC always user-driven V1
    // PCS_001 P2-LOCKED ADDITIVE fields:
    body_memory_init: Some(PcBodyMemory {
        soul: SoulLayer {
            origin_world_ref: Some(glossary_entity_id("modern_saigon_2026_world")),
            knowledge_tags: vec![knowledge_tag("modern_stem"), knowledge_tag("classical_chinese_reading")],
            native_skills: vec![],                       // V1 empty Vec reserved per Q5 REFINEMENT
            native_language: lang_id("vietnamese_modern"),
        },
        body: BodyLayer {
            host_body_ref: Some(glossary_entity_id("tran_phong_peasant_canonical")),
            knowledge_tags: vec![knowledge_tag("regional_hangzhou_dialect"), knowledge_tag("manual_labor")],
            motor_skills: vec![],                        // V1 empty Vec reserved
            native_language: lang_id("hangzhou_chinese_dialect"),
        },
        leakage_policy: LeakagePolicy::SoulPrimary { body_blurts_threshold: 0.05 },
    }),
    user_id_init: None,                                  // bind via runtime login V1+ OR Forge:BindPcUser V1
}
```

### V1+ runtime examples

- **PC user binding (V1 Forge admin path):** `Forge:BindPcUser { pc_id: ly_minh, user_id: claude_test_user_id }` → pc_user_binding.user_id populated; PC ready for play
- **PC death scenario (V1 Permadeath default):** Lý Minh dies at turn N → `mortality_config = Permadeath` → state Alive → Dead
- **PC death scenario (V1 Ghost mode):** mortality_config = Ghost → state Alive → Ghost (oan hồn wandering)
- **PC respawn (V1+ deferred PCS-D2):** mortality_config = RespawnAtLocation → V1 frozen at Dying; V1+ Respawn flow ships Dying → Alive transition
- **Runtime xuyên không (V1+ deferred PCS-D-N):** mid-play soul transmigration emits PcTransmigrationCompleted → TDIL_001 actor_clocks splits (soul_clock + body_clock + actor_clock=0 reset)

### V1+ AI-controls-PC-offline integration (ACT-D1; cross-feature)

When user logs out → control source User → AI:
- ACT_001 actor_chorus_metadata row CREATED for PC (sparse extension activates per ACT-A4)
- chorus orchestrator (NPC_002) treats offline PC as AI-driven; same priority resolution path
- pc_user_binding.current_session = None
- V1+ feature owns activation logic; PCS_001 V1 just exposes pc_user_binding.current_session for state queries

**This feature design specifies:** 2 PC-specific aggregates (pc_user_binding sparse + pc_mortality_state sparse) + PcId newtype + PcBodyMemory schema (SoulLayer + BodyLayer + LeakagePolicy 4-variant) + 7 V1 reject rule_ids in `pc.*` namespace + canonical seed flow integrating with ACT_001 ActorBorn + EF_001 EntityBorn + WA_006 mortality_config + TDIL_001 actor_clocks; V1 active death transitions (Alive→{Dead, Dying, Ghost} per mortality_config); V1+ Respawn + Resurrection + runtime PcTransmigrationCompleted deferred per locked Q-decisions.

After this lock: world-service can scaffold pc_user_binding + pc_mortality_state aggregates; WA_006 closure-pass-extension marks pc_mortality_state handoff RESOLVED; TDIL_001 closure-pass-extension confirms PcTransmigrationCompleted clock-split contract; V1+ PO_001 + AI-controls-PC-offline + Respawn flow consume PCS_001 stable base.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **PcId** | newtype Uuid wrapper | Mirror NpcId pattern + DP-A12 module-private constructor per Q1 LOCKED |
| **PC user binding** | `pc_user_binding` aggregate | user_id (auth-service ref) + current_session (active session ID) + body_memory (xuyên không) |
| **PC body-memory (xuyên không)** | `PcBodyMemory` schema (nested in pc_user_binding) | SoulLayer + BodyLayer + LeakagePolicy 4-variant per Q5+Q6 LOCKED |
| **PC mortality** | `pc_mortality_state` aggregate | 4-state machine per Q7 LOCKED (Alive/Dying/Dead/Ghost) |
| **PC creation pathway** | Canonical seed + Forge admin V1; runtime login V1+ | Per Q3 LOCKED |
| **PC stats** | (deferred V1+) | Q4 LOCKED — PROG_001 + RES_001 + PL_006 cover stats |
| **3-layer architectural model** (post-ACT_001) | L1 identity (ACT_001 owns); L2 kind (ActorId variant); L3 PC-specific (PCS_001 owns) | Per ACT-A2 LOCKED |
| **Multi-PC reality cap V1** | Stage 0 schema validator; row count cap=1 | Per Q9 LOCKED; V1+ relax via RealityManifest.max_pc_count Optional |
| **xuyên không transmigration** | PcBodyMemory schema + PcTransmigrationCompleted EVT-T1 (renamed from PcXuyenKhongCompleted; English type name; Vietnamese term preserved as narrative annotation) | THE NOVEL DESIGN per Q5+Q6+Q10 LOCKED |

### PCS_001 axioms

- **PCS-A1 (PC-only L3 substrate post-ACT_001):** PCS_001 aggregates apply to PCs only V1 (kind=Pc per ActorId::Pc variant). NPCs and Synthetic forbidden V1. Pattern: sparse aggregates within ACT_001 unified substrate.
- **PCS-A2 (Identity unified at L1 via ACT_001):** PCS_001 does NOT own actor identity (canonical_traits, flexible_state, knowledge_tags, voice_register, core_beliefs_ref, mood). All identity at ACT_001 actor_core; PCS_001 reads + extends.
- **PCS-A3 (PcId Uuid + DP-A12 constructor):** Per Q1 LOCKED; module-private constructor enforces forge-controlled PC creation only.
- **PCS-A4 (Single pc_user_binding aggregate V1):** Per Q2 LOCKED; user_id + current_session + body_memory in 1 cohesive aggregate. V1+ split if NPC body-substitution PCS-D5 ships.
- **PCS-A5 (Body-soul split via PcBodyMemory):** Full schema per Q5 REFINEMENT — SoulLayer + BodyLayer + LeakagePolicy 4-variant. native_skills + motor_skills V1 empty Vec reserved (V1+ A6 detector populates).
- **PCS-A6 (4-state mortality V1 schema):** Per Q7 LOCKED; Alive/Dying/Dead/Ghost. V1 active death transitions per mortality_config.mode; V1+ Respawn + Resurrection + GhostDispersed deferred PCS-D2.
- **PCS-A7 (Synthetic actor PC forbidden V1):** Universal substrate discipline; reject `pc.synthetic_actor_forbidden`.
- **PCS-A8 (Cross-reality strict V1):** Per Q8 LOCKED; V2+ Heresy migration via WA_002. xuyên không origin_world_ref is GlossaryEntityId (canonical reference; not active reality).
- **PCS-A9 (Multi-PC cap=1 V1):** Per Q9 LOCKED Stage 0 schema validator counts pc_user_binding rows per reality; V1+ relax via RealityManifest.max_pc_count Optional (PCS-D3).
- **PCS-A10 (Single event clock-split contract):** Per Q10 LOCKED; PcTransmigrationCompleted (PCS_001-owned EVT-T1) consumed by TDIL_001 actor_clocks per TDIL §10 contract; aggregate-owner discipline EVT-A11 preserved.

---

## §2.5 Event-model mapping (per [`07_event_model`](../../07_event_model/) EVT-T1..T11)

| Event | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| PC registered at canonical seed | **EVT-T4 System** | `PcRegistered { pc_id, body_memory, user_id }` (NEW; PCS_001-owned) | Bootstrap (RealityBootstrapper) | ✓ V1 |
| Forge admin RegisterPc | **EVT-T8 Administrative** | `Forge:RegisterPc { pc_id, body_memory_init, user_id_init?, spawn_cell }` | Forge (WA_003) | ✓ V1 |
| Forge admin BindPcUser | **EVT-T8 Administrative** | `Forge:BindPcUser { pc_id, user_id, before, after, reason }` | Forge | ✓ V1 |
| Forge admin EditPcUserBinding | **EVT-T8 Administrative** | `Forge:EditPcUserBinding { pc_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| Forge admin EditBodyMemory | **EVT-T8 Administrative** | `Forge:EditBodyMemory { pc_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| Forge admin EditPcMortalityState | **EVT-T8 Administrative** | `Forge:EditPcMortalityState { pc_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| PC Dying transition | **EVT-T3 Derived** | `aggregate_type=pc_mortality_state`, `delta_kind=DyingTransition { pc_id, will_respawn_at_fiction_time, spawn_cell, trigger }` | Aggregate-Owner (PCS_001 owner-service) | ✓ V1 |
| PC Death transition | **EVT-T3 Derived** | `delta_kind=DeathTransition { pc_id, died_at_turn, died_at_cell, trigger }` | Aggregate-Owner | ✓ V1 |
| PC Ghost transition | **EVT-T3 Derived** | `delta_kind=GhostTransition { pc_id, died_at_turn, died_at_cell, trigger }` | Aggregate-Owner | ✓ V1 |
| PC Respawn transition (V1+) | **EVT-T3 Derived** | `delta_kind=RespawnTransition { pc_id, respawn_cell }` | Aggregate-Owner | ✗ V1+ (PCS-D2 per Q7) |
| PC Resurrection (V1+ rare wuxia) | **EVT-T3 Derived** | `delta_kind=ResurrectionTransition { pc_id, ... }` | Aggregate-Owner | ✗ V1+ (PCS-D-N) |
| PC Ghost dispersed (V1+) | **EVT-T3 Derived** | `delta_kind=GhostDispersedTransition { pc_id }` | Aggregate-Owner | ✗ V1+ (PCS-D-N) |
| Runtime PC transmigration | **EVT-T1 Submitted** | `PcTransmigrationCompleted { old_actor_id, new_pc_id, body_actor_id, soul_origin_ref, body_memory_init, soul_clock_at_split, body_clock_at_split, split_at_turn, split_reason }` | World-service (xuyên không transition) | ⚠ Schema active V1 / Emission V1+ (PCS-D-N) |

**Event ordering at canonical seed (per PL_001 §16.2):** EntityBorn (EF_001) → PlaceBorn → MapLayoutBorn → SceneLayoutBorn → ActorBorn (ACT_001) → ActorChorusMetadataBorn (NPCs only) → **PcRegistered** (PCs only; PCS_001-owned) → RaceBorn → FamilyBorn → FactionBorn → FactionMembershipBorn → ReputationBorn → other Tier 5 events. PcRegistered emits AFTER ActorBorn (ACT_001 must populate actor_core first); PcRegistered carries body_memory + user_id; pc_user_binding row created.

---

## §3 Aggregate inventory

PCS_001 ships **2 aggregates** V1 (per Q4 LOCKED — `pc_stats_v1_stub` deferred V1+).

### §3.1 `pc_user_binding` (T2 / Reality scope — sparse PC-only)

```rust
#[derive(Aggregate)]
#[dp(type_name = "pc_user_binding", tier = "T2", scope = "reality")]
pub struct PcUserBinding {
    pub pc_id: PcId,                                   // FK to actor_core via ActorId::Pc(PcId)
    pub user_id: Option<UserId>,                       // None at canonical seed; Some after Forge:BindPcUser or runtime login V1+
    pub current_session: Option<SessionId>,            // Some when online; None when offline (V1+ AI-controls-PC-offline activates)
    pub body_memory: PcBodyMemory,                     // xuyên không SoulLayer + BodyLayer + LeakagePolicy
    pub last_login_at_turn: Option<u64>,               // staleness telemetry
    pub last_xuyenkhong_at_turn: Option<u64>,          // last xuyên không transition (rare; None for native PCs)
    // V1+ extensions (additive per I14)
    // pub previous_actor_ids: Vec<ActorId>,           // V1+ track prior actor_ids across xuyên không lineage (PCS-D-N)
}

/// Native PC default body_memory (no xuyên không; soul + body aligned).
/// Used when CanonicalActorDecl.body_memory_init = None for kind=Pc (fallback per Q5 LOCKED).
impl PcBodyMemory {
    pub fn native_default(native_language: LanguageId, knowledge_tags: Vec<KnowledgeTag>) -> Self {
        Self {
            soul: SoulLayer {
                origin_world_ref: None,                        // native; no xuyên không
                knowledge_tags: knowledge_tags.clone(),        // soul + body aligned
                native_skills: vec![],                          // V1 empty Vec reserved
                native_language: native_language.clone(),
            },
            body: BodyLayer {
                host_body_ref: None,                            // body created at canonical seed (no former occupant)
                knowledge_tags,                                 // matches soul
                motor_skills: vec![],                           // V1 empty Vec reserved
                native_language,
            },
            leakage_policy: LeakagePolicy::NoLeakage,           // V1 default for native PC
        }
    }
}
```

**Key:** `(reality_id, pc_id)`. Sparse storage: 0 rows (sandbox reality with no PC) or 1 row V1 cap (per Q9 LOCKED).

**Storage discipline:**
- T2 + RealityScoped: ~2-5 KB per row (depends on body_memory.knowledge_tags size)
- V1 cap=1 PC per reality (Stage 0 schema validator counts rows; reject `pc.multi_pc_per_reality_forbidden_v1` if count > 1)
- V1+ relax cap via RealityManifest.max_pc_count Optional (PCS-D3 single-line validator change)

**Mutability:**
- V1: Mutable via canonical seed (PcRegistered) + Forge admin (Forge:RegisterPc + Forge:BindPcUser + Forge:EditPcUserBinding + Forge:EditBodyMemory) + runtime login/logout (V1+ AI-controls-PC-offline updates current_session)
- V1+: PcTransmigrationCompleted runtime emission updates body_memory + last_xuyenkhong_at_turn (PCS-D-N per Q10 LOCKED)

**Synthetic actors forbidden V1 (PCS-A7):**
- Reject `pc.synthetic_actor_forbidden` Stage 0 schema for any actor where ActorId variant ≠ Pc.

**Cross-reality strict V1 (PCS-A8):**
- Reject `pc.cross_reality_mismatch` Stage 0 schema for cross-reality reads.

### §3.2 `pc_mortality_state` (T2 / Reality scope — sparse PC-only; handoff from WA_006)

```rust
#[derive(Aggregate)]
#[dp(type_name = "pc_mortality_state", tier = "T2", scope = "reality")]
pub struct PcMortalityState {
    pub pc_id: PcId,
    pub state: MortalityStateValue,
    pub last_transition_at_turn: u64,
    pub history: Vec<MortalityTransition>,             // bounded V1 (≤20 transitions; V1+ relax)
}

pub enum MortalityStateValue {
    /// Default state; PC alive and active.
    Alive,

    /// Transitional state — PC died but respawn pending (mortality_config = RespawnAtLocation).
    /// V1: schema entry active when mortality_config = RespawnAtLocation; exit (Dying → Alive) V1+ via PCS-D2 Respawn flow.
    /// V1: if Respawn flow not active, Dying state is FROZEN (no auto-exit); reject `pc.respawn_unsupported_v1` at canonical seed if mortality_config.mode = RespawnAtLocation declared without V1+ Respawn flow active.
    Dying {
        died_at_turn: u64,
        died_at_cell: ChannelId,
        will_respawn_at_fiction_time: FictionTimeTuple,    // V1+ Respawn flow consumes
        spawn_cell: ChannelId,                              // V1+ Respawn flow uses
    },

    /// Permanent death; no recovery V1 (mortality_config = Permadeath).
    /// V1+ may add Resurrection rare wuxia transition (PCS-D-N).
    Dead {
        died_at_turn: u64,
        died_at_cell: ChannelId,
    },

    /// Ghost form; PC continues as oan hồn / wandering spirit (mortality_config = Ghost mode).
    /// Wuxia narrative: "ghost wandering after unjust death".
    /// V1: state entry active when mortality_config = Ghost mode; V1+ Ghost → Alive Resurrection deferred (PCS-D-N).
    Ghost {
        died_at_turn: u64,
        died_at_cell: ChannelId,
    },
}

pub struct MortalityTransition {
    pub from: MortalityStateKind,                      // Alive | Dying | Dead | Ghost
    pub to: MortalityStateKind,
    pub at_turn: u64,
    pub trigger: TransitionTrigger,
    pub causal_event_id: Option<EventId>,              // EVT-T8 mortality event reference
}

pub enum MortalityStateKind {                           // discriminator without state-specific fields
    Alive, Dying, Dead, Ghost,
}

pub enum TransitionTrigger {
    DamageOverflow,                                    // HP=0 from PROG_001 strike formula
    PoisonStarvation,                                  // PL_006 actor_status hunger=critical → MortalityTransitionTrigger Starvation per RES_001 §17
    ForgeAdmin { reason: String },                     // Forge:EditPcMortalityState
    RespawnComplete,                                   // V1+ Dying → Alive (PCS-D2)
    Resurrection,                                      // V1+ Ghost → Alive (rare wuxia; PCS-D-N)
    GhostDispersed,                                    // V1+ Ghost → Dead (PCS-D-N)
}
```

**Key:** `(reality_id, pc_id)`. Sparse storage: 0 or 1 row per reality V1 (matches pc_user_binding cap).

**V1 active transitions (state machine per Q7 LOCKED):**

| From | To | V1 active? | Trigger |
|---|---|---|---|
| `Alive` | `Dead` | ✅ V1 | Death event when `mortality_config.mode = Permadeath` |
| `Alive` | `Dying` | ✅ V1 (schema entry; flow exit V1+) | Death event when `mortality_config.mode = RespawnAtLocation` |
| `Alive` | `Ghost` | ✅ V1 | Death event when `mortality_config.mode = Ghost` |
| `Dying` | `Alive` | ❌ V1+ via PCS-D2 Respawn flow | RespawnComplete (timer expires + spawn_cell available) |
| `Dying` | `Dead` | ❌ V1+ via PCS-D2 | Respawn flow timeout / failure |
| `Ghost` | `Alive` | ❌ V1+ via PCS-D-N Resurrection | Wuxia rare resurrection event |
| `Ghost` | `Dead` | ❌ V1+ via PCS-D-N GhostDispersed | Ghost dispersed enrichment |
| `Dead` | (any) | ❌ Forbidden V1 | Reject `pc.mortality_invalid_transition` |

**Mutability:**
- V1: Mutable via mortality events (DyingTransition / DeathTransition / GhostTransition EVT-T3) + Forge admin (Forge:EditPcMortalityState)
- V1+: RespawnTransition + ResurrectionTransition + GhostDispersedTransition deferred PCS-D2 + PCS-D-N

### §3.3 V1+ deferred aggregates (PCS-D4)

- `pc_stats_v1_stub` — DEFERRED V1+ per Q4 LOCKED. PROG_001 actor_progression + RES_001 vital_pool + PL_006 actor_status cover stats. V1+ may activate cache layer if combat hot-path performance demands.

### §3.4 PcBodyMemory schema (nested in pc_user_binding; per Q5 REFINEMENT)

```rust
/// Per-PC body-soul memory model. PC-only V1 (NPC body-substitution V1+ deferred PCS-D5/ACT-D5).
/// Drives A6 canon-drift detection V1+ (body cannot know what soul knows; soul leaks through body).
pub struct PcBodyMemory {
    pub soul: SoulLayer,
    pub body: BodyLayer,
    pub leakage_policy: LeakagePolicy,
}

pub struct SoulLayer {
    /// xuyên không origin world reference (GlossaryEntityId; canonical reference, not active reality per Q8 LOCKED).
    /// None = native (no xuyên không). SPIKE_01 Lý Minh: Some(glossary_entity_id("modern_saigon_2026_world")).
    pub origin_world_ref: Option<GlossaryEntityId>,

    /// Soul's knowledge tags (closed-set per ACT_001 KnowledgeTag).
    /// SPIKE_01 Lý Minh soul: ["modern_stem", "classical_chinese_reading"].
    pub knowledge_tags: Vec<KnowledgeTag>,

    /// Soul-bound skills (cognitive — academic, languages, mind-arts).
    /// V1 empty Vec reserved per Q5 REFINEMENT; V1+ A6 canon-drift detector populates from PROG_001 actor_progression.
    pub native_skills: Vec<ProgressionKindId>,

    /// Soul's native language (IDF_002 reference).
    /// SPIKE_01 Lý Minh soul: lang_id("vietnamese_modern").
    pub native_language: LanguageId,
}

pub struct BodyLayer {
    /// Body's canonical reference (former occupant; original soul of this body).
    /// None = body created fresh (rare; V1+ Reincarnation pattern).
    /// SPIKE_01 Lý Minh body: Some(glossary_entity_id("tran_phong_peasant_canonical")).
    pub host_body_ref: Option<GlossaryEntityId>,

    /// Body's retained knowledge tags (from former occupant; closed-set).
    /// SPIKE_01 Lý Minh body: ["regional_hangzhou_dialect", "manual_labor"]; NOTE missing "literacy".
    /// A6 detector V1+ flags body-knowledge mismatch when actor acts on soul-only knowledge.
    pub knowledge_tags: Vec<KnowledgeTag>,

    /// Body-bound skills (motor — combat reflexes, crafts, manual skills).
    /// V1 empty Vec reserved per Q5 REFINEMENT; V1+ A6 detector populates.
    pub motor_skills: Vec<ProgressionKindId>,

    /// Body's native language (IDF_002 reference).
    /// SPIKE_01 Lý Minh body: lang_id("hangzhou_chinese_dialect").
    pub native_language: LanguageId,
}

/// Soul-body knowledge leakage policy. Drives A6 canon-drift detector V1+.
pub enum LeakagePolicy {
    /// V1 default for native PC (soul + body aligned; no xuyên không).
    /// soul.knowledge_tags == body.knowledge_tags (or strict subset alignment).
    NoLeakage,

    /// Soul controls; body sometimes blurts soul-knowledge.
    /// SPIKE_01 Lý Minh = SoulPrimary { body_blurts_threshold: 0.05 }.
    /// body_blurts_threshold = probability per relevant action that body leaks soul-knowledge.
    SoulPrimary {
        body_blurts_threshold: f32,                    // [0.0, 1.0] per-turn probability
    },

    /// Body controls; soul instinct slips through but mostly suppressed.
    /// Wuxia variant: native body with awakening dormant soul.
    /// soul_slips_threshold = probability soul-knowledge slips into action.
    BodyPrimary {
        soul_slips_threshold: f32,                     // [0.0, 1.0] per-turn probability
    },

    /// Both layers contribute equally; soul + body knowledge merge over time.
    /// Rare wuxia variant: two souls sharing consciousness.
    Balanced,
}
```

---

## §4 Tier+scope (DP-R2)

| Aggregate | Tier | Scope | Read frequency | Write frequency | Storage notes |
|---|---|---|---|---|---|
| `pc_user_binding` | T2 | Reality | ~5-10 per session (PC turn submission + persona assembly + login state checks) | ~0.01 per turn V1 (canonical seed only); ~5 writes/day V1+ session changes | Sparse: 0 or 1 row V1; ~2-5 KB per row |
| `pc_mortality_state` | T2 | Reality | ~1-5 per turn (mortality state checks at PL_005 + WA_006 cross-feature) | ~0 V1 typical (rare death events); ~1 per death event | Sparse: 0 or 1 row V1; ~1 KB per row + history Vec |

---

## §5 DP primitives

PCS_001 reuses standard 06_data_plane primitives:

```rust
// V1 reads — pc_user_binding (sparse PC-only)
let binding = dp::read_aggregate_reality::<PcUserBinding>(ctx, reality_id, key=pc_id)
    .await?
    .ok_or(PcError::PcNotFound)?;
let is_online = binding.current_session.is_some();
let is_xuyenkhong = binding.body_memory.soul.origin_world_ref.is_some();

// V1 reads — pc_mortality_state (sparse PC-only)
let mortality = dp::read_aggregate_reality::<PcMortalityState>(ctx, reality_id, key=pc_id)
    .await?
    .map(|m| m.state)
    .unwrap_or(MortalityStateValue::Alive);  // missing row = Alive default (PC freshly created)

// V1 writes — canonical seed (PcRegistered for PCs)
dp::t2_write(ctx, "PcRegistered",
    aggregate=pc_user_binding,
    payload=PcUserBinding { ... },
    causal_ref=bootstrap_event)
.await?;

// V1 writes — Forge admin
dp::t2_write(ctx, "Forge:BindPcUser",
    aggregate=pc_user_binding,
    payload=updated_binding,
    causal_ref=forge_admin_event)
.await?;

// V1 writes — mortality transition
dp::t2_write(ctx, "DyingTransition",
    aggregate=pc_mortality_state,
    payload=updated_mortality,
    causal_ref=death_event)
.await?;
```

---

## §6 Capability requirements (JWT claims)

| Operation | JWT claim required | Notes |
|---|---|---|
| Read `pc_user_binding` | `reality.read` | Standard reality-scope read |
| Read `pc_mortality_state` | `reality.read` | Standard reality-scope read |
| Write canonical seed (PcRegistered) | `bootstrap.canonical_seed` | RealityBootstrapper role only |
| Write Forge admin (5 sub-shapes) | `forge.admin` (WA_003 contract) | Reuses WA_003 Forge JWT contract; no new claim |
| Write mortality transition events | (orchestrator JWT; world-service internal) | Aggregate-Owner role; triggered by death events from PROG_001 strike + RES_001 starvation + PL_005 interaction |
| Write V1+ Respawn / Resurrection / runtime PcTransmigrationCompleted | (V1+ TBD) | Aggregate-Owner role; depends on V1+ activation |

---

## §7 Subscribe pattern

| Aggregate | Subscribe to | Use case |
|---|---|---|
| `pc_user_binding` | `aggregate_type=actor_core` (ACT_001) | When ACT_001 actor_core PC row updated, PCS_001 may need to propagate (rare V1 — actor_core is L1 identity; pc_user_binding is L3) |
| `pc_user_binding` | EVT-T1 `PcTransmigrationCompleted` (V1+) | Updates body_memory + last_xuyenkhong_at_turn at runtime xuyên không transition (cross-feature with TDIL_001 actor_clocks per Q10 LOCKED) |
| ACT_001 `actor_chorus_metadata` | `aggregate_type=pc_user_binding` (current_session field changes) | V1+ AI-controls-PC-offline (ACT-D1) — when pc_user_binding.current_session transitions Some → None (logout), ACT_001 owner-service creates actor_chorus_metadata row for PC; reverse on login |
| `pc_mortality_state` | EVT-T3 PROG_001 strike damage | When HP=0 detected, transition to Dying/Dead/Ghost per mortality_config |
| `pc_mortality_state` | EVT-T3 RES_001 vital_pool changes | Hp=0 → MortalityTransitionTrigger; Stamina=0 → Exhausted (PL_006) but not death |
| `pc_mortality_state` | EVT-T5 RES_001 hunger tick | Hunger=critical → starvation MortalityTransitionTrigger |
| TDIL_001 `actor_clocks` | EVT-T1 `PcTransmigrationCompleted` (V1+) | Clock-split per TDIL §10 (PCS_001 emits; TDIL_001 consumes per Q10 LOCKED) |

---

## §8 Pattern choices

### §8.1 PC-only L3 substrate post-ACT_001 (PCS-A1)

PCS_001 V1 owns ONLY PC-specific behavior; identity (L1) lives in ACT_001 actor_core unified across PC + NPC.

**Reasoning:**
- ACT_001 unification refactor (commit a1ce3c8) absorbed PC persona model (canonical_traits + flexible_state + knowledge_tags + voice_register)
- PCS_001 NOT responsible for IDENTITY anymore; reads ACT_001 actor_core
- PCS_001 owns L3 PC-specific concerns: user-control + body-memory + lifecycle (mortality)
- Smaller scope (~700-900 lines vs ~1000 ACT_001) since identity lifted to L1

### §8.2 PcId Uuid newtype (Q1 LOCKED)

Mirror NpcId pattern + DP-A12 module-private constructor for forge-controlled creation.

**Reasoning:**
- Pattern consistency with EntityKind types (NpcId, future ItemInstanceId, EnvObjectInstanceId per EF_001)
- Module-private constructor (DP-A12) enforces forge-controlled creation paths only
- UUID uniqueness guaranteed across realities (matches NpcId)
- Author-readable alias V1+ enrichment (defer when pain emerges)

### §8.3 Single pc_user_binding aggregate (Q2 LOCKED)

Cohesive single aggregate (user_id + current_session + body_memory + timestamps) per Q2 LOCKED.

**Reasoning:**
- V1 simplicity wins; xuyên không rare V1 (no contention pain)
- Pattern consistency with ACT_001 actor_chorus_metadata bundling 3 L3 fields
- Sparse storage (0 or 1 row V1 per cap=1 Q9); storage cost minimal
- V1+ split if NPC body-substitution PCS-D5 ships and needs shared schema

### §8.4 Canonical seed + Forge admin V1; runtime login V1+ (Q3 LOCKED)

V1 supports 2 paths: (1) canonical seed declares PC actor_id; (2) Forge admin binds user_id later. V1+ adds runtime login flow via PO_001.

**Reasoning:**
- (A) too narrow — sandbox realities blocked V1
- (B) blocks on PO_001 design; not yet started
- (D) admin-only — no clear path to multi-user V1+
- (C) wins — canonical seed for narrative realities; Forge admin V1 immediate; V1+ PO_001 player self-onboarding

### §8.5 Defer pc_stats_v1_stub V1+ (Q4 LOCKED)

PROG_001 actor_progression + RES_001 vital_pool + PL_006 actor_status cover stats; PCS_001 V1 = 2 aggregates instead of 3.

**Reasoning:**
- PROG_001 superseded DF7 placeholder per PROG_001 DRAFT (commit a76a4e4)
- PC always Tier 0 (AIT_001) — eager simulation; all stat reads O(1)
- 3 aggregates already cover stats; redundant aggregate adds storage cost
- V1+ cache layer if combat hot-path performance demands (PCS-D4)

### §8.6 Full PcBodyMemory schema with reserved skill fields (Q5 REFINEMENT)

Full schema V1; native_skills/motor_skills V1 empty Vec reserved (V1+ A6 detector populates from PROG_001 actor_progression).

**Reasoning:**
- SPIKE_01 turn 5 literacy slip REQUIRES knowledge_tags overlap analysis
- A6 V1+ canon-drift detector reads body_memory.{soul, body}.knowledge_tags
- Skill-level breakdown V1+ enables more sophisticated leak/slip detection
- Schema complete V1 → V1+ activation additive without migration

### §8.7 Full 4-variant LeakagePolicy V1 (Q6 LOCKED)

NoLeakage / SoulPrimary { body_blurts_threshold } / BodyPrimary { soul_slips_threshold } / Balanced.

**Reasoning:**
- Wuxia narrative requires all 4 patterns (per reference survey §2)
- V1+ enum extension is binary-breaking; ship full V1
- Storage cost minimal (5 bytes max per LeakagePolicy)

### §8.8 Full 4-state mortality with phased transition activation (Q7 LOCKED)

V1 schema 4-state (Alive/Dying/Dead/Ghost); V1 active death transitions Alive→{Dead, Dying, Ghost}; V1+ Respawn + Resurrection + GhostDispersed deferred PCS-D2.

**Reasoning:**
- Wuxia oan hồn Ghost narrative core wuxia trope
- WoW respawn pattern for Dying state; transitional state with parameters
- V1 Dying state FROZEN if Respawn flow not active; reject `pc.respawn_unsupported_v1` at canonical seed
- Schema reservation V1 = no migration V1+ when flows ship

### §8.9 V1 strict single-reality (Q8 LOCKED) + V1 cap=1 PC (Q9 LOCKED)

Universal substrate discipline (cross-reality V2+ Heresy) + V1 single-PC per reality (V1+ multi-PC charter coauthors).

**Reasoning:**
- Universal V2+ Heresy discipline (IDF + FF + FAC + REP + ACT all locked)
- xuyên không origin_world_ref is GlossaryEntityId (canonical reference; not active reality)
- V1 SPIKE_01 = single PC; multi-PC V1+ via charter coauthors (PLT_001 future feature)
- FAC_001 Q2 REVISION pattern (Stage 0 schema validator + V1+ relax = single-line change)

### §8.10 Single event clock-split contract (Q10 LOCKED)

PcTransmigrationCompleted (renamed from PcXuyenKhongCompleted; English type name) → TDIL_001 actor_clocks subscribes per TDIL §10 contract.

**Reasoning:**
- Aggregate-Owner discipline EVT-A11 — TDIL_001 owns actor_clocks; only TDIL_001 writes
- Single event simpler causal chain
- Renamed per user direction 2026-04-27 (Vietnamese term preserved as parenthetical narrative annotation; English type name)
- Schema active V1; runtime emission V1+ deferred (canonical seed declares pre-split state V1)

---

## §9 Failure-mode UX

| Reject rule | Stage | User-facing message | When fired |
|---|---|---|---|
| `pc.unknown_pc_id` | 0 schema | "PC không tồn tại trong hiện thực này" (PC doesn't exist) | Read/write attempt with unknown pc_id |
| `pc.synthetic_actor_forbidden` | 0 schema | (Schema-level; not user-facing) | Synthetic actor cannot have PCS_001 aggregate row |
| `pc.cross_reality_mismatch` | 0 schema | (Schema-level; not user-facing) | actor.reality_id ≠ pc_user_binding.reality_id |
| `pc.invalid_transmigration_combination` | 0 schema | "Tổ hợp xuyên không không hợp lệ" (Invalid transmigration combination) | soul/body inconsistency at PcTransmigrationCompleted (e.g., soul knowledge_tags overlap body knowledge_tags inconsistently) |
| `pc.user_id_already_bound` | 0 schema | "User đã được liên kết với PC khác" (User already bound to another PC) | One user_id can't bind to multi PCs V1 |
| `pc.mortality_invalid_transition` | 0 schema | (Schema-level; not user-facing) | e.g., Dead → Alive without RespawnComplete trigger; transitions outside V1 active set |
| `pc.multi_pc_per_reality_forbidden_v1` | 0 schema | "Hiện thực V1 chỉ hỗ trợ 1 PC; multi-PC charter coauthors V1+ via PCS-D3" | pc_user_binding row count > 1 per Q9 LOCKED |

V1+ reservation rules:
- `pc.runtime_login_unsupported_v1` — V1+ when PC creation form ships per Q3 LOCKED (PCS-D1)
- `pc.respawn_unsupported_v1` — V1+ when respawn flow ships per Q7 LOCKED (PCS-D2); V1 Stage 0 schema canonical seed validation rejects mortality_config.mode = RespawnAtLocation if V1+ flow not active
- `pc.body_substitution_unsupported_v1` — V1+ when full xuyên không runtime ships beyond canonical seed (PCS-D-N per Q10)

**Per RES_001 §2 i18n contract:** All `pc.*` rejects use `RejectReason.user_message: I18nBundle` with English `default` field + Vietnamese translation V1 from day 1.

---

## §10 Cross-service handoff (canonical seed flow)

PCS_001 canonical seed flows through standard RealityBootstrapper pipeline integrating with ACT_001 + EF_001 + WA_006 + TDIL_001:

1. **knowledge-service** ingests book canon → emits `RealityManifest` with `canonical_actors: Vec<CanonicalActorDecl>` (ACT_001-owned post-unify; PCS_001 P2-LOCKED additive fields body_memory_init + user_id_init)
2. **world-service RealityBootstrapper** validates manifest:
   - Stage 0 schema validation per PC actor:
     - actor_id valid + `kind = Pc`
     - spawn_cell ∈ RealityManifest.places (per ACT-A2 + PCS-A8)
     - glossary_entity_id ∈ knowledge-service canon
     - body_memory_init Some(...) for PC kind (REQUIRED V1 per Q5 LOCKED)
     - user_id_init Optional (V1 typically None at canonical seed; bound via Forge admin)
     - mortality_config.mode validation: if RespawnAtLocation declared but V1+ Respawn flow not active → reject `pc.respawn_unsupported_v1`
     - V1 cap=1 enforcement: count pc_user_binding rows; reject `pc.multi_pc_per_reality_forbidden_v1` if > 1
   - Stage 1: emit ACT_001 ActorBorn (kind=Pc) + EF_001 EntityBorn { entity_type: Actor(Pc), cell_id: spawn_cell }
   - Stage 2: emit PCS_001 PcRegistered { pc_id, body_memory: from canonical decl, user_id: None }
3. **PCS_001 owner-service** writes:
   - `pc_user_binding` row { pc_id, user_id: None, current_session: None, body_memory, last_login_at_turn: None, last_xuyenkhong_at_turn: None }
   - `pc_mortality_state` row { pc_id, state: Alive, last_transition_at_turn: 0, history: [] }
4. **TDIL_001 actor_clocks** initialized: { actor_id: pc_id, actor_clock: 0, soul_clock: from body_memory canonical, body_clock: from body_memory canonical } (per TDIL §10 + Q10 LOCKED)
5. **WA_006 mortality_config** read at runtime when death events fire; pc_mortality_state state machine transitions per mortality_config.mode

### Field-mapping table: CanonicalActorDecl → PcUserBinding + ActorCore

| Target field | CanonicalActorDecl source field | Notes |
|---|---|---|
| `actor_core.actor_id` | `actor_id` | ACT_001-owned; PCs use ActorId::Pc(PcId) variant |
| `actor_core.glossary_entity_id` | `glossary_entity_id` | ACT_001-owned per ACT-P2 |
| `actor_core.current_region_id` | `spawn_cell` | ACT_001-owned per ACT-P2 |
| `actor_core.flexible_state` | `flexible_state_init` | ACT_001-owned |
| `actor_core.mood` | `mood_init` | ACT_001-owned |
| `pc_user_binding.pc_id` | `actor_id.into()` | extracted from ActorId::Pc variant |
| `pc_user_binding.user_id` | `user_id_init` | None at canonical seed typically; V1 Forge:BindPcUser binds |
| `pc_user_binding.current_session` | (none) | None at bootstrap; runtime login V1+ populates |
| `pc_user_binding.body_memory` | `body_memory_init.unwrap_or(default_native)` | Required Some V1 for PC; native PC fallback if None |
| `pc_user_binding.last_login_at_turn` | (none) | None at bootstrap |
| `pc_user_binding.last_xuyenkhong_at_turn` | (none) | None at bootstrap (canonical seed declares pre-split; no transition event) |
| `pc_mortality_state.state` | (default Alive) | All PCs start Alive at canonical seed |

---

## §11 Sequence: Canonical seed (Wuxia Lý Minh xuyên không pre-split)

```
RealityManifest {
    canonical_actors: vec![
        CanonicalActorDecl {
            actor_id: ActorId::Pc(PcId(uuid_lm)),
            kind: ActorKind::Pc,
            glossary_entity_id: glossary_entity_id("ly_minh_actor_canon"),
            spawn_cell: channel_id("hangzhou_tieu_diem_inn_cell"),
            canonical_traits: CanonicalTraits {
                name: "Lý Minh",
                role: "PC scholar (xuyên không transmigrator)",
                ...
            },
            flexible_state_init: FlexibleState::empty(),
            knowledge_tags: vec![/* aggregated soul + body */],
            voice_register: VoiceRegister::TerseFirstPerson,
            core_beliefs_ref: Some(glossary_entity_id("ly_minh_belief_set")),
            mood_init: ActorMood::NEUTRAL,
            chorus_metadata: None,                              // PC user-driven V1
            // PCS_001 P2-LOCKED ADDITIVE fields (REQUIRED V1):
            body_memory_init: Some(PcBodyMemory {
                soul: SoulLayer {
                    origin_world_ref: Some(glossary_entity_id("modern_saigon_2026_world")),
                    knowledge_tags: vec![
                        knowledge_tag("modern_stem"),
                        knowledge_tag("classical_chinese_reading"),
                    ],
                    native_skills: vec![],                       // V1 empty Vec
                    native_language: lang_id("vietnamese_modern"),
                },
                body: BodyLayer {
                    host_body_ref: Some(glossary_entity_id("tran_phong_peasant_canonical")),
                    knowledge_tags: vec![
                        knowledge_tag("regional_hangzhou_dialect"),
                        knowledge_tag("manual_labor"),
                        // NO "literacy" tag → A6 detector flags when body reads
                    ],
                    motor_skills: vec![],                        // V1 empty Vec
                    native_language: lang_id("hangzhou_chinese_dialect"),
                },
                leakage_policy: LeakagePolicy::SoulPrimary {
                    body_blurts_threshold: 0.05,                 // 5% probability per relevant action
                },
            }),
            user_id_init: None,                                  // bind via Forge admin V1
        },
    ],
    // ... other canonical actors (NPCs Du sĩ, Tiểu Thúy, Lão Ngũ — declared via ACT_001 path; no body_memory_init / user_id_init)
}
```

**Validation flow:**
1. Stage 0 schema validation per PC actor:
   - actor_id valid + kind=Pc → ✓
   - spawn_cell ∈ RealityManifest.places → ✓ (PF_001 declared)
   - glossary_entity_id ∈ knowledge-service canon → ✓
   - body_memory_init Some for PC kind → ✓ (REQUIRED V1 per Q5; if None, fallback to PcBodyMemory::native_default for native PC pattern)
   - user_id_init None acceptable V1 → ✓ (bound via Forge:BindPcUser V1 OR runtime login V1+)
   - V1 cap=1 enforcement: count canonical_actors with kind=Pc → must be ≤1 (per PCS-A9 + Q9 LOCKED); reject `pc.multi_pc_per_reality_forbidden_v1` if > 1
   - mortality_config validation: if mortality_config.mode = RespawnAtLocation declared but V1+ Respawn flow PCS-D2 not active → reject `pc.respawn_unsupported_v1` (V1 reality must use Permadeath or Ghost mode)
2. RealityBootstrapper emits per PC actor:
   - 1 EVT-T4 EF_001 EntityBorn { entity_id: pc_id, entity_type: Actor(Pc), cell_id: spawn_cell }
   - 1 EVT-T4 ACT_001 ActorBorn { actor_id: pc_id, kind: Pc, traits_summary: ... }
   - 1 EVT-T4 PCS_001 PcRegistered { pc_id, body_memory: from canonical decl, user_id: None }
   - 1 EVT-T4 TDIL_001 ActorClocksRegistered (with initial soul_clock + body_clock from body_memory canonical seed; per TDIL §10)
   - (other Tier 5 events: RaceBorn, FamilyBorn, FactionBorn, FactionMembershipBorn, ReputationBorn — independent)
3. PCS_001 owner-service writes:
   - `pc_user_binding` row { pc_id, user_id: None, current_session: None, body_memory: from canonical, last_login: None, last_xuyenkhong: None }
   - `pc_mortality_state` row { pc_id, state: Alive, last_transition_at_turn: 0, history: [] }
4. Causal-ref chain: bootstrap_event → EntityBorn → ActorBorn → PcRegistered → pc_user_binding row_insert → pc_mortality_state row_insert → ActorClocksRegistered

**Post-bootstrap reads:**
- `read_pc_user_binding(ly_minh_pc_id)` → row with user_id: None (waiting for binding)
- `read_pc_mortality_state(ly_minh_pc_id)` → state: Alive
- `read_actor_core(ly_minh_pc_id)` → ACT_001 actor_core row (canonical_traits + flexible_state + knowledge_tags + voice_register + mood)
- `read_actor_clocks(ly_minh_pc_id)` → TDIL_001 row (3-clock initialized; soul_clock + body_clock from body_memory canonical)

---

## §12 Sequence: Forge admin BindPcUser (V1 active)

```
Author types in Forge UI: "Bind user 'claude_test' to PC Lý Minh"
  → Forge frontend emits POST /v1/forge/pc/bind
       { pc_id: ly_minh_pc_id, user_id: claude_test_user_id, reason: "test session binding" }
  → world-service Forge handler validates:
     - JWT has forge.admin claim
     - pc_id valid (exists in pc_user_binding)
     - user_id valid (exists in auth-service)
     - V1 cap=1 enforcement: user_id not already bound to another PC; reject pc.user_id_already_bound if
     - actor not synthetic
  → 3-write atomic transaction:
     1. Read existing pc_user_binding row → before snapshot (user_id: None)
     2. Write pc_user_binding row { user_id: Some(claude_test_user_id), ... }
     3. Emit EVT-T8 Forge:BindPcUser { pc_id, user_id, before, after, reason }
     4. Write forge_audit_log entry referencing EVT-T8 event_id
  → AC-PCS-7 covers atomicity (3-write transaction)
```

---

## §13 Sequence: Forge admin EditBodyMemory (V1 active; xuyên không author override)

```
Author types in Forge UI: "Update Lý Minh body_memory: increase body_blurts_threshold to 0.1"
  → Forge frontend emits POST /v1/forge/pc/body_memory/edit
       { pc_id: ly_minh_pc_id, edit_kind: "UpdateLeakagePolicy",
         before: SoulPrimary { body_blurts_threshold: 0.05 },
         after: SoulPrimary { body_blurts_threshold: 0.1 },
         reason: "narrative escalation" }
  → world-service Forge handler validates:
     - JWT has forge.admin claim + pc_id valid
     - edit_kind matches body_memory schema (no schema-violating edits)
  → 3-write atomic transaction (same pattern as §12)
  → AC-PCS-8 covers body_memory edit atomicity
```

---

## §14 Sequence: PC mortality transition (V1 active; Permadeath path)

```
PROG_001 strike formula determines Lý Minh HP=0 at turn N
  → PROG_001 emits EVT-T3 hp_zero event
  → PCS_001 owner-service subscribes; reads WA_006 mortality_config
  → mortality_config.mode = Permadeath → trigger DeathTransition

  → Validate transition:
     - From state Alive → To state Dead (V1 active per Q7)
     - Trigger: DamageOverflow

  → 3-write atomic transaction:
     1. Read existing pc_mortality_state row → before { state: Alive }
     2. Write pc_mortality_state row {
          state: Dead { died_at_turn: N, died_at_cell: actor_core.current_region_id },
          last_transition_at_turn: N,
          history: [..., MortalityTransition { from: Alive, to: Dead, at_turn: N, trigger: DamageOverflow, causal_event_id: Some(hp_zero_event_id) }],
        }
     3. Emit EVT-T3 DeathTransition { pc_id, died_at_turn: N, died_at_cell, trigger: DamageOverflow }

  → Downstream cascade:
     - WA_006 closure-pass-extension reads pc_mortality_state for narrative authoring
     - V1+ A6 detector may flag "PC dead but acted in subsequent turn" inconsistency
     - V1+ Respawn flow does NOT activate (Permadeath mode); state stuck at Dead
```

**Alternative paths V1:**
- mortality_config.mode = Ghost → state Alive → Ghost (oan hồn wandering; PC continues as ghost)
- mortality_config.mode = RespawnAtLocation → REJECTED at canonical seed V1 (`pc.respawn_unsupported_v1`); reality must use Permadeath or Ghost V1

---

## §15 Sequence: V1+ runtime PcTransmigrationCompleted (deferred PCS-D-N; schema active V1)

```
// V1+ EXAMPLE (NOT V1 — deferred per Q10)
Mid-play scenario: ancient cultivator dies; soul transmigrates to modern body via narrative event
  → V1+ feature emits PcTransmigrationCompleted EVT-T1:
     {
       old_actor_id: ActorId::Npc(NpcId(uuid_ancient_cultivator)),
       new_pc_id: PcId(uuid_new_pc),
       body_actor_id: ActorId::Npc(NpcId(uuid_modern_npc_body)),
       soul_origin_ref: Some(glossary_entity_id("ancient_wuxia_world")),
       body_memory_init: PcBodyMemory { ... },                    // post-split state
       soul_clock_at_split: <ancient cultivator's accumulated soul time>,
       body_clock_at_split: <modern body's accumulated time>,
       split_at_turn: <turn N>,
       split_reason: TransmigrationReason::SuddenDeath,
     }
  → TDIL_001 actor_clocks subscribes (per Q10 LOCKED + TDIL §10 contract):
     - Writes new actor_clocks row for new_pc_id: { actor_clock: 0 (reset), soul_clock: from event, body_clock: from event }
     - Marks old_actor_id actor_clocks row terminated (worldline preserved per TDIL-A8)
  → RES_001 vital_pool subscribes (per RES §5.3):
     - new_pc_id inherits body_actor_id's vital_pool current values
  → RES_001 entity_binding cell_owner subscribes (per RES Q9c):
     - Cells previously owned by body_actor_id auto-inherit to new_pc_id
  → PCS_001 owner-service writes:
     - new pc_user_binding row { pc_id: new_pc_id, body_memory: from event, user_id: None (V1+ may inherit), last_xuyenkhong_at_turn: split_at_turn }
     - new pc_mortality_state row { state: Alive }
  → ACT_001 actor_core row created for new_pc_id
  → AC-PCS-V1+1 covers full xuyên không runtime flow (deferred V1+)
```

**"Schema active V1 / Emission V1+" semantic clarification:**
- V1: PCS_001 spec DEFINES PcTransmigrationCompleted EVT-T1 sub-type schema (engine knows the shape; subscribers like TDIL_001 know how to consume)
- V1: NO RUNTIME emission of PcTransmigrationCompleted V1 (canonical seed declares pre-split state; no transition event needed)
- V1+: Runtime emission unlocked when PCS-D-N enrichment ships (mid-play xuyên không scenarios; A6 detector active; full event flow + cross-feature cascade)
- Pre-V1+ activation: realities with xuyên không actors must declare in canonical seed; mid-play xuyên không transitions REJECTED V1

V1: schema for PcTransmigrationCompleted DEFINED + canonical seed declares pre-split state; runtime emission V1+ requires:
- V1+ A6 canon-drift detector (PCS-D7) for body-soul knowledge mismatch detection
- V1+ multi-PC reality cap relax (PCS-D3) if new_pc adds to existing reality
- V1+ TDIL-A8 worldline monotonicity preserved (Forge past-clock edits FORBIDDEN)

---

## §16 Acceptance criteria (LOCK gate)

V1 (10 testable scenarios):

| AC | Scenario | Expected outcome |
|---|---|---|
| **AC-PCS-1** | Wuxia canonical bootstrap declares Lý Minh PC with body_memory_init Some(SoulPrimary{...}) → actor_core + pc_user_binding + pc_mortality_state + actor_clocks rows written | RealityBootstrapper emits 4 EVT-T4 events; 4 rows written; cross-aggregate consistency at canonical seed |
| **AC-PCS-2** | Lý Minh xuyên không SoulLayer.knowledge_tags=["modern_stem", "classical_chinese_reading"] + BodyLayer.knowledge_tags=["regional_hangzhou_dialect", "manual_labor"] → schema validates; A6 V1+ detector reads correctly | body_memory schema fields populated; knowledge_tag overlap analysis ready for A6 V1+ |
| **AC-PCS-3** | SPIKE_01 turn 5 literacy slip schema verification (V1 schema test; full detection V1+) | Schema fields populated correctly: SoulLayer.knowledge_tags includes "classical_chinese_reading"; BodyLayer.knowledge_tags MISSING "literacy"; LeakagePolicy::SoulPrimary { body_blurts_threshold: 0.05 } configured. A6 detector V1+ activation reads schema (PCS-D7); V1 only validates schema integrity, not detection logic. |
| **AC-PCS-4** | Multi-PC reality rejected V1 (`pc.multi_pc_per_reality_forbidden_v1`) | Stage 0 schema validator counts pc_user_binding rows; rejects > 1 |
| **AC-PCS-5** | Synthetic actor PC rejected (`pc.synthetic_actor_forbidden`) | Stage 0 schema validator |
| **AC-PCS-6** | Cross-reality PC migration rejected (`pc.cross_reality_mismatch`) | Stage 0 schema validator |
| **AC-PCS-7** | Forge admin BindPcUser 3-write atomic | pc_user_binding row + EVT-T8 + forge_audit_log committed atomically; rollback if any fails |
| **AC-PCS-8** | Forge admin EditBodyMemory 3-write atomic | pc_user_binding.body_memory updated; EVT-T8 + forge_audit_log committed |
| **AC-PCS-9** | Mortality transition Alive → Dead (Permadeath) | mortality_config.mode = Permadeath; HP=0 → DeathTransition emitted; pc_mortality_state row updated; history records DamageOverflow trigger |
| **AC-PCS-10** | PcId newtype module-private constructor enforced (DP-A12 pattern) | External code cannot construct PcId directly; only via forge-controlled paths |

V1+ deferred (4 scenarios):

| AC | Scenario | V1+ enrichment |
|---|---|---|
| **AC-PCS-V1+1** | V1+ runtime PcTransmigrationCompleted full flow | PCS-D-N per Q10 LOCKED |
| **AC-PCS-V1+2** | V1+ Respawn transition (Dying → Alive at fiction_time + spawn_cell) | PCS-D2 per Q7 LOCKED |
| **AC-PCS-V1+3** | V1+ AI-controls-PC-offline activates actor_chorus_metadata for PC | ACT-D1 cross-feature |
| **AC-PCS-V1+4** | V1+ multi-PC reality (charter coauthors) | PCS-D3 single-line validator change |

---

## §17 Boundary registrations (in same commit chain)

This DRAFT commit (2/4) adds:

### `_boundaries/01_feature_ownership_matrix.md`

- 2 NEW aggregate rows: pc_user_binding + pc_mortality_state (PCS_001 owner)
- 1 NEW EVT-T4 sub-type: PcRegistered (PCS_001 owner)
- 5 NEW EVT-T8 sub-shapes: Forge:RegisterPc + Forge:BindPcUser + Forge:EditPcUserBinding + Forge:EditBodyMemory + Forge:EditPcMortalityState
- 1 NEW EVT-T3 entries: pc_mortality_state delta_kinds (DyingTransition + DeathTransition + GhostTransition V1; RespawnTransition + ResurrectionTransition + GhostDispersedTransition V1+)
- 1 NEW EVT-T1 sub-type: PcTransmigrationCompleted (schema active V1; emission V1+)
- 1 NEW namespace: `pc.*` (7 V1 + 3 V1+ reservations)
- RealityManifest envelope: CanonicalActorDecl additive fields (body_memory_init + user_id_init; both Optional V1)
- 1 NEW stable-ID prefix: `PCS-*` (already partially registered; finalized)

### `_boundaries/02_extension_contracts.md`

- §1.4 namespace registration: `pc.*` (7 V1 rules + 3 V1+ reservations)
- §2 RealityManifest CanonicalActorDecl additive fields (body_memory_init + user_id_init); cross-references PCS_001 §3.4 PcBodyMemory schema

### `_boundaries/99_changelog.md`

- Commit 2/4 entry: PCS_001 DRAFT promotion + boundary register
- Commit 4/4 entry: PCS_001 closure pass + lock release (deferred)

### `catalog/cat_06_PCS_pc_systems.md`

- PCS-A1..A10 axioms documented
- PCS-D1..D10 deferrals enumerated
- 14+ catalog entries with feature references

### `features/06_pc_systems/_index.md`

- PCS_001 row updated to DRAFT 2026-04-27 (was Q-LOCKED 5c34b93)

### Cross-feature coordination

- WA_006 closure-pass-extension note: pc_mortality_state aggregate handoff RESOLVED (commit 4/4 will add formal note)
- TDIL_001 closure-pass-extension note: PcTransmigrationCompleted clock-split contract per Q10 LOCKED (commit 4/4)

---

## §18 Open questions deferred + landing point

### V1+ deferrals (PCS-D1..PCS-D10)

| ID | Item | Landing point |
|---|---|---|
| **PCS-D1** | V1+ runtime login flow PC creation | PO_001 Player Onboarding feature when concrete |
| **PCS-D2** | V1+ Respawn transition flow (Dying → Alive) | When mortality_config respawn semantics ship |
| **PCS-D3** | V1+ multi-PC reality cap relax | charter coauthors (PLT_001) — single-line validator change |
| **PCS-D4** | V1+ pc_stats_v1_stub cache layer | If combat hot-path performance demands |
| **PCS-D5** | V1+ NPC body-substitution (xuyên không for NPCs) | Cross-ref ACT-D5; shared body_memory schema |
| **PCS-D6** | V2+ cross-reality PC migration via WA_002 Heresy | V2+ |
| **PCS-D7** | V1+ A6 canon-drift detector body_memory integration | 05_llm_safety A6 V1+ |
| **PCS-D8** | V1+ Reincarnation pattern (body resets each death; soul preserves) | When narrative use case concrete |
| **PCS-D9** | V1+ Possession pattern (temporary occupation by another soul) | When narrative use case concrete |
| **PCS-D10** | V1+ PO_001 Player Onboarding integration | UI flow consumes PCS_001 primitives |

### Open questions (NONE V1)

All Q1-Q10 LOCKED via 6-batch deep-dive 2026-04-27 (1 REFINEMENT on Q5 + 1 RENAME of PcXuyenKhongCompleted → PcTransmigrationCompleted). No outstanding V1 design questions.

---

## §19 Cross-references

### Resolved deferrals from upstream features

- **WA_006 §6 closure pass** — `pc_mortality_state` aggregate ownership EXPLICITLY HANDED OFF to PCS_001 → ✅ RESOLVED via §3.2 pc_mortality_state aggregate
- **PCS_001 brief §S2 (PC persona)** — ABSORBED by ACT_001 actor_core post-unification → ✅ Resolved upstream
- **PCS_001 brief §S6 (PC-NPC relationship read)** — ABSORBED by ACT_001 actor_actor_opinion bilateral → ✅ Resolved upstream
- **DF7 PC Stats placeholder** — SUPERSEDED by PROG_001 actor_progression + RES_001 vital_pool + PL_006 actor_status → ✅ Resolved upstream

### Consumes from locked features

- **EF_001 §5.1** ActorId source-of-truth — sibling pattern; ActorKind::Pc discriminator; PcId newtype owned by PCS_001
- **ACT_001 §3.1** actor_core (L1 identity) — PCs read identity from actor_core (post-unification)
- **ACT_001 §3.2** actor_chorus_metadata (V1+ AI-controls-PC-offline) — sparse extension; PCs populate when offline V1+
- **ACT_001 §3.3** actor_actor_opinion (V1+ PC↔NPC bilateral) — PC view of NPCs V1+ runtime
- **ACT_001 §3.4** actor_session_memory (V1+ PC offline AI context) — PC populated V1+
- **WA_006** mortality_config (per-reality singleton) — PCS_001 reads at runtime for mortality state machine
- **TDIL_001 §10** clock-split contract — PCS_001 emits PcTransmigrationCompleted; TDIL_001 actor_clocks consumes
- **RES_001 §2.3** I18nBundle — display strings + reject user_message
- **RES_001 §5.3** body-bound resource inheritance — V1+ runtime xuyên không cell_owner inheritance (PCS-D-N)
- **WA_003** Forge audit log — EVT-T8 sub-shapes use forge_audit_log pattern (3-write atomic)

### Consumed by future features

- **PO_001 V1+** Player Onboarding — PC creation form UI consumes PCS_001 primitives (Forge:RegisterPc + Forge:BindPcUser)
- **AI-controls-PC-offline V1+** — activates actor_chorus_metadata for PCs when offline (cross-ref ACT-D1)
- **A6 V1+** canon-drift detector — reads body_memory.{soul, body}.knowledge_tags (PCS-D7)
- **PROG_001** combat damage formula — PC takes damage; HP=0 triggers PCS_001 mortality transition

---

## §20 Implementation readiness checklist

- [ ] **§1** User story locked (Wuxia Lý Minh xuyên không + native PC + V1+ runtime examples)
- [ ] **§2** Domain concepts + PCS-A1..A10 axioms locked
- [ ] **§2.5** Event-model mapping locked (1 EVT-T4 + 5 EVT-T8 + 1 EVT-T3 + 1 EVT-T1; V1 active vs V1+ deferred)
- [ ] **§3** Aggregate inventory: 2 PCS_001 aggregates (pc_user_binding + pc_mortality_state); pc_stats_v1_stub deferred V1+
- [ ] **§4** Tier+scope DP-R2 annotations
- [ ] **§5** DP primitives reuse standard
- [ ] **§6** Capability requirements: reuses WA_003 forge.admin JWT
- [ ] **§7** Subscribe pattern (mortality cascade from PROG_001 strike + RES_001 starvation + V1+ TDIL_001 transmigration)
- [ ] **§8** Pattern choices: 10 sub-sections covering Q1-Q10 LOCKED decisions
- [ ] **§9** Failure-mode UX: 7 V1 reject rules + 3 V1+ reservations + Vietnamese I18n
- [ ] **§10** Cross-service handoff via standard RealityBootstrapper pipeline + ACT_001 + EF_001 + WA_006 + TDIL_001 integration
- [ ] **§11** Sequence: Canonical seed (Wuxia Lý Minh xuyên không pre-split state)
- [ ] **§12** Sequence: Forge admin BindPcUser (V1 active)
- [ ] **§13** Sequence: Forge admin EditBodyMemory (V1 active)
- [ ] **§14** Sequence: PC mortality transition (V1 active; Permadeath path)
- [ ] **§15** Sequence: V1+ runtime PcTransmigrationCompleted (schema active V1; emission deferred)
- [ ] **§16** Acceptance criteria: 10 V1-testable AC-PCS-1..10 + 4 V1+ deferred
- [ ] **§17** Boundary registrations (in same commit chain — commit 2/4)
- [ ] **§18** Open questions deferred: 10 deferrals (PCS-D1..PCS-D10); 0 V1 open Q
- [ ] **§19** Cross-references: 4 RESOLVED upstream + 10 consumed-from + 4 consumed-by-future
- [ ] **§20** This checklist (filling at Phase 3 cleanup commit 3/4)

**Status transition:** DRAFT 2026-04-27 (commit 2/4 67b53cd) → Phase 3 cleanup applied (commit 3/4 7e3218e) → **CANDIDATE-LOCK 2026-04-27** (commit 4/4 this commit) → **LOCK** when AC-PCS-1..10 pass integration tests + V1+ scenarios after V1+ enrichments ship.

**Next** (when CANDIDATE-LOCK granted): world-service can scaffold pc_user_binding + pc_mortality_state aggregates + Forge admin handlers; WA_006 closure-pass-extension marks pc_mortality_state handoff RESOLVED; TDIL_001 closure-pass-extension confirms PcTransmigrationCompleted clock-split contract; V1+ PO_001 + AI-controls-PC-offline + Respawn flow consumers wire up.
