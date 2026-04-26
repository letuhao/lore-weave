<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_06_PCS_pc_systems.md
byte_range: 53160-54550
sha256: 11469db62fbb63f65698658eb550a5bd56940b565d1981854969dc950658510e
generated_by: scripts/chunk_doc.py
-->

## PCS — PC Systems

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PCS-1 | PC state projection (location, status, stats, inventory) | ✅ | V1 | IF-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md), [04 §8](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-2 | PC inventory + item origin reality | ✅ | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) (MV5 primitive P5) |
| PCS-3 | PC ↔ NPC relationship tracking | 🟡 | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) |
| PCS-4 | PC stats model (simple state-based, no RPG mechanics) | 🟡 | V1 | PCS-1 | [04 §5.3](04_PLAYER_CHARACTER_DESIGN.md), PC-C3 locked, **DF7** concrete schema |
| PCS-5 | PC offline mode (visible + vulnerable) | 🟡 | V1 | PCS-1 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md), PC-B2 locked |
| PCS-6 | PC `/hide` command + hidden status | 🟡 | V1 | PCS-5 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-7 | PC-as-NPC conversion after prolonged hiding | 📦 | V2 | PCS-6, NPC-8 | **DF1 — Daily Life** |
| PCS-8 | PC death (event emission, per-reality outcome) | 🟡 | V1 | PCS-1, WA-5 | [04 §4.1](04_PLAYER_CHARACTER_DESIGN.md), PC-B1 locked; outcomes in **DF4** |
| PCS-9 | PC reclaim from NPC mode | 📦 | V2 | PCS-7 | **DF1** |
| PCS-10 | PC persona generation (LLM persona for NPC mode) | 📦 | V2 | PCS-7 | **DF8 — NPC persona from PC history** |

---

## PCS_001 PC Substrate (DRAFT 2026-04-27 — Tier 5 Actor Substrate post-ACT_001 unification)

> Foundation-level catalog appendage. PCS_001 owns `PCS-*` stable-ID namespace (already registered in `_boundaries/01_feature_ownership_matrix.md` line 148; this section formalizes axioms + deferrals).
>
> | Sub-prefix | What |
> |---|---|
> | `PCS-A*` | Axioms (locked invariants) |
> | `PCS-D*` | Per-feature deferrals (V1+ / V2 phases) |
> | `PCS-Q*` | Open questions (closure pass items) |

### Core architectural axioms

**PCS-A1 (PC-only L3 substrate post-ACT_001):** PCS_001 aggregates apply to PCs only V1 (kind=Pc per ActorId::Pc variant). NPCs and Synthetic forbidden V1. Pattern: sparse aggregates within ACT_001 unified substrate. Identity (L1) unified at ACT_001 actor_core; PCS_001 owns L3 PC-specific concerns: user-control + body-memory + lifecycle (mortality).

**PCS-A2 (Identity unified at L1 via ACT_001):** PCS_001 does NOT own actor identity (canonical_traits, flexible_state, knowledge_tags, voice_register, core_beliefs_ref, mood). All identity at ACT_001 actor_core; PCS_001 reads + extends. Brief §S2 (PC persona model) + §S6 (PC-NPC relationship read) ABSORBED by ACT_001.

**PCS-A3 (PcId Uuid + DP-A12 constructor):** Per Q1 LOCKED 2026-04-27; mirror NpcId pattern + module-private constructor enforces forge-controlled PC creation only.

**PCS-A4 (Single pc_user_binding aggregate V1):** Per Q2 LOCKED; user_id + current_session + body_memory in 1 cohesive aggregate. V1+ split if NPC body-substitution PCS-D5 ships.

**PCS-A5 (Body-soul split via PcBodyMemory):** Full schema per Q5 REFINEMENT — SoulLayer + BodyLayer + LeakagePolicy 4-variant. native_skills + motor_skills V1 empty Vec reserved (V1+ A6 detector populates).

**PCS-A6 (4-state mortality V1 schema):** Per Q7 LOCKED; Alive/Dying/Dead/Ghost. V1 active death transitions per mortality_config.mode; V1+ Respawn + Resurrection + GhostDispersed deferred PCS-D2.

**PCS-A7 (Synthetic actor PC forbidden V1):** Universal substrate discipline; reject `pc.synthetic_actor_forbidden`.

**PCS-A8 (Cross-reality strict V1):** Per Q8 LOCKED; V2+ Heresy migration via WA_002. xuyên không origin_world_ref is GlossaryEntityId (canonical reference; not active reality).

**PCS-A9 (Multi-PC cap=1 V1):** Per Q9 LOCKED Stage 0 schema validator counts pc_user_binding rows per reality; V1+ relax via RealityManifest.max_pc_count Optional (PCS-D3).

**PCS-A10 (Single event clock-split contract):** Per Q10 LOCKED; PcTransmigrationCompleted (PCS_001-owned EVT-T1) consumed by TDIL_001 actor_clocks per TDIL §10 contract; aggregate-owner discipline EVT-A11 preserved. Renamed from PcXuyenKhongCompleted per user direction 2026-04-27 (English type name; Vietnamese term "xuyên không" preserved as parenthetical narrative annotation).

### PCS_001 catalog entries (PCS-11..PCS-20)

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PCS-11 | `pc_user_binding` aggregate (T2/Reality, sparse PC-only; V1 cap=1 per reality per Q9 LOCKED) | ✅ | V1 | EF-1 (ActorId::Pc), ACT-1 (actor_core), DP-A14 | [PCS_001 §3.1](../features/06_pc_systems/PCS_001_pc_substrate.md#31-pc_user_binding-t2--reality-scope--sparse-pc-only) |
| PCS-12 | `pc_mortality_state` aggregate (T2/Reality, sparse PC-only; 4-state machine; handoff from WA_006) | ✅ | V1 | PCS-11, WA-6 (mortality_config) | [PCS_001 §3.2](../features/06_pc_systems/PCS_001_pc_substrate.md#32-pc_mortality_state-t2--reality-scope--sparse-pc-only-handoff-from-wa_006) |
| PCS-13 | `PcId` newtype (Uuid + DP-A12 module-private constructor mirror NpcId pattern per Q1 LOCKED) | ✅ | V1 | EF-1 (ActorId variant) | [PCS_001 §2](../features/06_pc_systems/PCS_001_pc_substrate.md#2-domain-concepts) |
| PCS-14 | `PcBodyMemory` schema (SoulLayer + BodyLayer + LeakagePolicy 4-variant per Q5 REFINEMENT + Q6 LOCKED) | ✅ | V1 | PCS-11, IDF-2 (LanguageId), PROG-* (ProgressionKindId reserved) | [PCS_001 §3.4](../features/06_pc_systems/PCS_001_pc_substrate.md#34-pcbodymemory-schema-nested-in-pc_user_binding-per-q5-refinement) |
| PCS-15 | `MortalityStateValue` 4-state enum (Alive/Dying/Dead/Ghost) + `TransitionTrigger` 6-variant + `MortalityTransition` history per Q7 LOCKED | ✅ | V1 | PCS-12 | [PCS_001 §3.2](../features/06_pc_systems/PCS_001_pc_substrate.md#32-pc_mortality_state-t2--reality-scope--sparse-pc-only-handoff-from-wa_006) |
| PCS-16 | EVT-T4 System sub-type `PcRegistered` (canonical seed PC creation; PCS_001-owned per Q3 LOCKED) | ✅ | V1 | EVT-A11, PCS-11 | [PCS_001 §2.5](../features/06_pc_systems/PCS_001_pc_substrate.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| PCS-17 | EVT-T8 AdminAction sub-shapes (5 V1: Forge:RegisterPc + Forge:BindPcUser + Forge:EditPcUserBinding + Forge:EditBodyMemory + Forge:EditPcMortalityState) | ✅ | V1 | PCS-11, PCS-12, WA-3 (forge_audit_log) | [PCS_001 §2.5](../features/06_pc_systems/PCS_001_pc_substrate.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| PCS-18 | EVT-T3 Derived sub-types — pc_mortality_state delta_kinds (DyingTransition + DeathTransition + GhostTransition V1 active; RespawnTransition + ResurrectionTransition + GhostDispersedTransition V1+ reserved) | ✅ V1 active + V1+ reserved | V1 | EVT-A11, PCS-12 | [PCS_001 §2.5](../features/06_pc_systems/PCS_001_pc_substrate.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| PCS-19 | EVT-T1 Submitted sub-type `PcTransmigrationCompleted` (renamed from PcXuyenKhongCompleted per user direction 2026-04-27; English type name; schema active V1; runtime emission V1+ deferred PCS-D-N per Q10 LOCKED) | ⚠ Schema V1 / Emission V1+ | V1 schema | EVT-A11, PCS-11, TDIL-* (actor_clocks subscriber) | [PCS_001 §2.5](../features/06_pc_systems/PCS_001_pc_substrate.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| PCS-20 | RealityManifest CanonicalActorDecl additive fields (body_memory_init Option<PcBodyMemory> + user_id_init Option<UserId>); REQUIRED V1 for kind=Pc per Q3+Q5 LOCKED; `pc.*` namespace 7 V1 reject rules + 3 V1+ reservations | ✅ | V1 | PCS-11, PCS-14, RES-23 (i18n) | [PCS_001 §17](../features/06_pc_systems/PCS_001_pc_substrate.md#17-boundary-registrations-in-same-commit-chain) + [`_boundaries/02_extension_contracts.md` §1.4 + §2](../_boundaries/02_extension_contracts.md) |

### Per-feature deferrals (PCS-D*)

| Deferral | Description | Phase |
|---|---|---|
| PCS-D1 | V1+ runtime login flow PC creation | PO_001 Player Onboarding feature when concrete |
| PCS-D2 | V1+ Respawn transition flow (Dying → Alive) | When mortality_config respawn semantics ship |
| PCS-D3 | V1+ multi-PC reality cap relax via RealityManifest.max_pc_count Optional | charter coauthors (PLT_001) — single-line validator change |
| PCS-D4 | V1+ pc_stats_v1_stub cache layer | If combat hot-path performance demands |
| PCS-D5 | V1+ NPC body-substitution (xuyên không for NPCs) | Cross-ref ACT-D5; shared body_memory schema |
| PCS-D6 | V2+ cross-reality PC migration via WA_002 Heresy | V2+ |
| PCS-D7 | V1+ A6 canon-drift detector body_memory integration | 05_llm_safety A6 V1+ |
| PCS-D8 | V1+ Reincarnation pattern (body resets each death; soul preserves) | When narrative use case concrete |
| PCS-D9 | V1+ Possession pattern (temporary occupation by another soul) | When narrative use case concrete |
| PCS-D10 | V1+ PO_001 Player Onboarding integration | UI flow consumes PCS_001 primitives |

### Open questions (PCS-Q*)

NONE V1. All Q1-Q10 LOCKED via 6-batch deep-dive 2026-04-27 (1 REFINEMENT on Q5 + 1 RENAME of PcXuyenKhongCompleted → PcTransmigrationCompleted).

### Cross-feature integration map

| Feature | Direction | Integration |
|---|---|---|
| EF_001 Entity Foundation | PCS_001 reads | ActorId::Pc(PcId) sibling pattern |
| ACT_001 Actor Foundation | PCS_001 reads (L1 identity) | PCs read actor_core for canonical_traits/flexible_state/etc.; PCS_001 V1 = pure L3 substrate |
| WA_006 Mortality | PCS_001 RESOLVES handoff | `pc_mortality_state` aggregate ownership transferred per WA_006 §6 closure pass commit f436e60 |
| TDIL_001 Time Dilation | PCS_001 emits / TDIL_001 consumes | PcTransmigrationCompleted EVT-T1 → TDIL_001 actor_clocks per TDIL §10 clock-split contract per Q10 LOCKED |
| RES_001 Resource | PCS_001 cross-feature | V1+ runtime xuyên không cell_owner inheritance per RES §5.3 (PCS-D-N) |
| PROG_001 Progression | PCS_001 reads | actor_progression covers PC stats; HP=0 → DamageOverflow → mortality transition |
| PL_006 Status | PCS_001 cross-feature | actor_status flags (Drunk/Exhausted/Wounded/Frightened) covered V1 |
| WA_003 Forge | PCS_001 reuses | forge_audit_log pattern (3-write atomic for 5 EVT-T8 sub-shapes) |
| PO_001 Player Onboarding | PCS_001 consumed by V1+ | Runtime login flow consumes Forge:RegisterPc + Forge:BindPcUser primitives (PCS-D1) |
| AI-controls-PC-offline V1+ | PCS_001 consumed by V1+ | Activates ACT_001 actor_chorus_metadata for PC; cross-ref ACT-D1 |
| A6 canon-drift detector V1+ | PCS_001 consumed by V1+ | Reads body_memory.{soul, body}.knowledge_tags for SPIKE_01 turn 5 literacy slip detection (PCS-D7) |
| Future PROG_001 strike formula | PCS_001 mortality consumer | HP=0 from strike → DyingTransition/DeathTransition/GhostTransition per mortality_config.mode |
| Future RES_001 vital_pool starvation | PCS_001 mortality consumer | hunger=critical → MortalityTransitionTrigger Starvation per RES_001 §17 → PCS_001 mortality state |
