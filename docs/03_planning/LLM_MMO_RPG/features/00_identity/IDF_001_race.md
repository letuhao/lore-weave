# IDF_001 — Race Foundation

> **Conversational name:** "Race" (RAC). Tier 5 Actor Substrate Foundation feature owning the per-reality `RaceId` closed-set + per-actor `race_assignment` aggregate. Cross-actor uniformity: same enum + aggregate referenced by future PCS_001 (PC) + future `NPC_NNN_mortality` (NPC) without drift. Foundation discipline mirrors EF_001's ActorId pattern — own the closed-set once, consume from many features.
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** DRAFT 2026-04-26 (Phase 0 CONCEPT promoted to DRAFT after POST-SURVEY-Q1..Q7 user "A" confirmation; Q-decisions RAC-Q1..Q10 locked per concept-note + RAC-Q4 expanded to 6 sizes per POST-SURVEY-Q2)
> **Stable IDs in this file:** `RAC-A*` axioms · `RAC-D*` deferrals · `RAC-Q*` decisions (registered in [`02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) Stable-ID prefix table)
> **Builds on:** [EF_001 §5.1 ActorId / EntityId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) (sibling pattern — RaceAssignment indexes by ActorId); [WA_001 Lex AxiomDecl](../02_world_authoring/WA_001_lex.md) (V1+ `requires_race` axiom-gate hook); [WA_006 Mortality](../02_world_authoring/WA_006_mortality.md) (race-driven default_mortality_kind_override lookup); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md) (display_name type for declarative names).
> **Defers to:** future PCS_001 (PC race assignment via existing aggregate consumption); future `NPC_NNN_mortality` feature (race-affected lifespan / mortality_kind override); V1+ combat (race-affected ability access via Lex axiom tags); V1+ CULT_001 Cultivation Foundation (mutable rank-tier WITHIN Cultivator race; SEPARATE from race per RAC-D11).
> **Event-model alignment:** Race assignment events = EVT-T3 Derived (sub-discriminator `aggregate_type=race_assignment`, delta_kind=`AssignRace`). Bootstrap RaceBorn events = EVT-T4 System sub-type `RaceBorn`. Forge admin edits = EVT-T8 Administrative `Forge:EditRaceAssignment`. No new EVT-T* category needed.

---

## §1 User story (concrete — V1 Wuxia + Modern + Sci-fi presets)

A reality is born from Thần Điêu Đại Hiệp (Wuxia preset). Its RealityManifest declares 5 races: Phàm nhân / Cultivator / Demon / Ghost / Beast.

1. **Lý Minh** (PC) — race=Cultivator (Tu sĩ); lifespan=600yr; size=Medium; allowed_lex_axiom_tags=["qigong", "spirit_sense"]; default_mortality_kind_override=Permadeath.
2. **Tiểu Thúy** (NPC) — race=Phàm nhân; lifespan=80yr; size=Medium; no axiom tags (mortal NPC has no special abilities).
3. **Du sĩ** (NPC) — race=Cultivator; lifespan=600yr; size=Medium; same axiom tags as LM01 (Cultivator class).
4. **Lão Ngũ** (NPC) — race=Phàm nhân; lifespan=80yr; size=Medium.
5. **Hypothetical bandit ghost** (V1+ NPC) — race=Ghost; size=Medium; default_mortality_kind_override=AlreadyDead (Ghost actors never enter Alive state).
6. **Hypothetical demon-beast** (V1+ NPC) — race=Beast; size=Large; allowed_lex_axiom_tags=["natural_weapons"].
7. **Hypothetical Long (Dragon)** (V1+ canonical boss) — race=Demon; size=Gargantuan; allowed_lex_axiom_tags=["dragon_breath", "flight"].

**A second reality is born from a Modern Saigon detective novel.** RealityManifest declares 1 race: Human. Every actor (PC + NPC) has race=Human; lifespan=80yr; size=Medium.

**A third reality is born from a Sci-fi space-opera.** RealityManifest declares 3 races: Human / AlienX / AlienY. Each race has different lifespans, sizes, and axiom tags.

**This feature design specifies:** the closed-set `RaceId` per reality declared in `RealityManifest.races`; the per-actor `race_assignment` aggregate with reason audit; the V1 immutable assignment policy (V1+ reincarnation lifts); the V1+ Lex axiom gate hook (`AxiomDecl.requires_race`); the WA_006 default_mortality_kind_override resolution; the rejection UX with Vietnamese reject copy in `race.*` namespace per `_boundaries/02_extension_contracts.md` §1.4; the cross-service handoff for canonical bootstrap + PC creation flows.

After this lock: every PC and NPC has a deterministic race assignment driving lifespan + size + axiom access; WA_001 Lex (V1+ closure) can gate axioms by race; WA_006 mortality_config resolves per-race death-mode override; UI can display localized race badges via I18nBundle.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **RaceId** | `pub struct RaceId(pub String);` typed newtype wrapping `String` (e.g., `RaceId("race_cultivator_tusi".to_string())`) | Opaque language-neutral; per-reality scope. NOT a Rust enum — closed-set per reality declared in RealityManifest. Cross-reality `RaceId` collision allowed (Wuxia `race_human_phamnhan` ≠ Modern `race_human_modern` semantically; same string OK). **Distinct from RES_001 `LangCode`** (engine UI translation ISO-639-1 string) AND **distinct from future IDF_002 `LanguageId`** (in-fiction language stable-ID) — runtime newtype prevents accidental cross-type assignment per LNG-D8 / LNG-Q11 future deferral. |
| **RaceDecl** | Author-declared per-reality entry (in RealityManifest.races) | Declarative metadata: display_name (I18nBundle) + default_lifespan_years (u16) + size_category (SizeCategory) + default_mortality_kind_override (Option<MortalityKind> per WA_006) + allowed_lex_axiom_tags (Vec<String> for V1+ Lex gate) + canon_ref (Option<GlossaryEntityId>). |
| **race_assignment** | T2 / Reality aggregate; per-(reality, actor_id) row | Generic for PC + NPC. Birth-fixed V1 — single immutable RaceId field + AssignmentReason audit. ActorId source = [EF_001 §5.1](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types). |
| **AssignmentReason** | Closed enum: `CanonicalSeed / PcCreation / NpcSpawn / AdminOverride { reason: String }` | Audit trail for race assignment. V1+ adds `Reincarnation` + `RaceTransformation`. |
| **SizeCategory** | Closed enum 6-variant: `Tiny / Small / Medium / Large / Huge / Gargantuan` (Pathfinder 2e full coverage per POST-SURVEY-Q2 LOCKED) | V1 closed set. Wuxia coverage: Tiny=Linh xà / Linh thử (spirit creatures); Medium=Cultivator / Phàm nhân; Large=Tigers / Wolves / Beast cultivators; Huge=large beast cultivators; Gargantuan=Long (Dragons) / Linh quy (Giant turtles). Consumed by V1+ combat (size-vs-size modifier; 6×6 = 36-entry matrix). |
| **MortalityKind** | Closed enum **owned by WA_006 Mortality**: `Permadeath / RespawnAtLocation / Ghost / AlreadyDead` (V1+ may extend) | IDF_001 imports type from WA_006; does NOT redefine. RaceDecl.default_mortality_kind_override is the override hook — WA_006 mortality_config consumer reads at runtime per-event lookup (per RAC-Q9). Phase 3 cleanup note: AlreadyDead variant special-case applies to Ghost race where `default_lifespan_years` is conventionally set to 1 (minimum schema-valid) but never consumed (Ghost actors bypass age tracking via override=AlreadyDead path). See §11 Wuxia bootstrap sequence Phase 3 note. |

**Cross-feature consumers:**
- WA_001 Lex (V1+ closure) — `AxiomDecl.requires_race: Option<Vec<RaceId>>` axiom-gate at Stage 4 lex_check
- WA_006 Mortality — `default_mortality_kind_override` resolves race-default death mode per actor
- NPC_002 priority (V1+) — race-conflict modifier in opinion drift (RAC-D2)
- PCS_001 (V1+) — PC creation form selects RaceId from reality's allowed set
- NPC_001 — NPC declared with RaceId at canonical seed; NPC_003 (Desires) optionally consumes for race-aware desires
- V1+ CULT_001 — Cultivator race actors only (other races have NO cultivation realm)

---

## §2.5 Event-model mapping (per [`07_event_model`](../../07_event_model/) EVT-T1..T11)

IDF_001 emits / consumes events that all map to existing active EVT-T* categories — no new category needed.

| IDF_001 path | EVT-T* | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Race assigned at canonical seed (RealityBootstrapper) | **EVT-T4 System** | `RaceBorn { reality_id, actor_id, race_id }` | Bootstrap role (RealityBootstrapper) | Emitted alongside EF_001 EntityBorn at canonical seed; one per actor per reality |
| Race assigned at PC creation | **EVT-T3 Derived** | `aggregate_type=race_assignment`, delta_kind=`AssignRace` | Aggregate-Owner role (IDF_001 owner-service, integrated into world-service) | Causal-ref REQUIRED to triggering PC creation event |
| Race assigned at NPC spawn (V1+ Generator-driven NPCs) | **EVT-T3 Derived** | same as above | Aggregate-Owner role | Causal-ref REQUIRED to triggering NpcSpawn event |
| Race admin override (Forge edit) | **EVT-T8 Administrative** | `Forge:EditRaceAssignment { actor_id, before, after, reason }` | Forge role (WA_003) | Uses `forge_audit_log`; AC-RAC-9 covers atomicity |
| V1+ Reincarnation race transition | **EVT-T3 Derived** | `aggregate_type=race_assignment`, delta_kind=`Reincarnate` | Aggregate-Owner role | V1+ scheduler-driven via V1+30d |

**Closed-set proof for IDF_001:** every race-related path produces an active EVT-T* (T3 / T4 / T8). No new EVT-T* row.

---

## §3 Aggregate inventory

**One** primary aggregate. IDF_001 is a small foundation feature.

### 3.1 `race_assignment` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "race_assignment", tier = "T2", scope = "reality")]
pub struct RaceAssignment {
    pub reality_id: RealityId,
    pub actor_id: ActorId,                // EF_001 §5.1 source-of-truth
    pub race_id: RaceId,                  // birth-fixed V1; mutable V1+ via Reincarnation/Transformation
    pub assigned_at_turn: u64,            // for audit
    pub assigned_at_fiction_ts: i64,      // millis from fiction-clock at assignment
    pub assigned_reason: AssignmentReason,
    pub schema_version: u32,
}

pub enum AssignmentReason {
    CanonicalSeed,                          // RealityBootstrapper at world-build
    PcCreation,                             // PC creation form
    NpcSpawn,                               // NPC spawned via Forge / Generator
    AdminOverride { reason: String },       // Admin force-assigned (Forge:EditRaceAssignment audit)
    // V1+ extensions (additive per I14)
    // Reincarnation { from_race: RaceId, lifespan_carryover: bool },
    // RaceTransformation { from_race: RaceId, trigger: TransformationTrigger },
}
```

- **T2 + RealityScoped:** per-actor across reality lifetime
- **One row per `(reality_id, actor_id)`**: every actor MUST have a race row (assertion at bootstrap; re-assertion at NPC spawn)
- **V1 immutable** (race_id field rejects mutation V1; V1+ Reincarnation/Transformation lifts via additive AssignmentReason variants)
- **Synthetic actors**: don't get race_assignment rows V1 (Synthetic = ChorusOrchestrator / BubbleUpAggregator / etc. — mechanical; no race semantic)

### 3.2 `RaceDecl` (RealityManifest declarative entry — not a runtime aggregate)

```rust
pub struct RaceDecl {
    pub race_id: RaceId,
    pub display_name: I18nBundle,                            // RES_001 §2.3
    pub default_lifespan_years: u16,                         // 80 / 600 / etc.
    pub size_category: SizeCategory,
    pub default_mortality_kind_override: Option<MortalityKind>, // WA_006 ref
    pub allowed_lex_axiom_tags: Vec<String>,                 // V1+ Lex gate (e.g., ["qigong", "spirit_sense"])
    pub canon_ref: Option<GlossaryEntityId>,
}

pub enum SizeCategory {
    Tiny,
    Small,
    Medium,
    Large,
    Huge,
    Gargantuan,
}
```

V1: 6 SizeCategory variants per POST-SURVEY-Q2 (Pathfinder 2e full coverage). V1+ extends additively if first content needs (e.g., Diminutive / Colossal).

---

## §4 Tier+scope (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `race_assignment` | T2 | T2 | Reality | ~1 per turn (UI badge + WA_006 mortality lookup + V1+ Lex gate) | Once at actor birth (V1 immutable); V1+ ~0.001/turn (Reincarnation rare) | Per-actor across reality lifetime; eventual consistency on cross-session reads OK; V1 immutable — no T3 urgency. |

---

## §5 DP primitives this feature calls

By name. No raw `sqlx` / `redis` (DP-R3).

### 5.1 Reads

- `dp::read_projection_reality::<RaceAssignment>(ctx, actor_id)` — UI badge / WA_006 lookup / V1+ Lex axiom gate
- `dp::query_scoped_reality::<RaceAssignment>(ctx, predicate=field_eq(race_id, X))` — operator queries (e.g., "all Cultivator actors in this reality")
- `dp::read_reality_manifest(ctx).races` — RealityManifest extension reads RaceDecl list (called at canonical seed validation + PC creation form)

### 5.2 Writes

- `dp::t2_write::<RaceAssignment>(ctx, actor_id, AssignRaceDelta { race_id, reason })` — assign at bootstrap / PC creation / NPC spawn
- `dp::t2_write::<RaceAssignment>(ctx, actor_id, AdminOverrideDelta { race_id, reason })` — Forge admin edit (AC-RAC-9 covers atomicity)
- V1+ `dp::t2_write::<RaceAssignment>(ctx, actor_id, ReincarnateDelta { from_race, to_race })` — Reincarnation flow (V1+30d scheduler)

### 5.3 Subscriptions

- UI subscribes to `race_assignment` invalidations via DP-X cache invalidation broadcast → re-renders race badge
- V1+ Lex axiom gate at Stage 4 reads `race_assignment` via projection (cached; no subscription needed)

### 5.4 Capability + lifecycle

- `produce: [Derived]` + `write: { aggregate_type: race_assignment, tier: T2, scope: reality }` — for IDF_001 owner-service (world-service in V1; logical role)
- `produce: [System]` + sub-type `RaceBorn` — for RealityBootstrapper at canonical seed
- `produce: [Administrative]` + sub-shape `Forge:EditRaceAssignment` — for Forge admin (WA_003 owns audit log)

---

## §6 Capability requirements (JWT claims)

Inherits PL_001 + EF_001 patterns. No new claim category.

| Claim | Granted to | Why |
|---|---|---|
| `produce: [Derived]` + `write: race_assignment @ T2 @ reality` | world-service backend (IDF_001 owner role) | assign at PC creation / NPC spawn |
| `produce: [System]` + sub-type `RaceBorn` | RealityBootstrapper service | canonical seed at world-build |
| `produce: [Administrative]` + sub-shape `Forge:EditRaceAssignment` | Forge admin (WA_003) | admin override audit |
| `read: race_assignment @ T2 @ reality` | every PC session + NPC_002 orchestrator + WA_001 Lex consumer + WA_006 Mortality consumer | UI display + V1+ Lex gate + mortality lookup |

---

## §7 Subscribe pattern

UI receives `race_assignment` updates via DP-X cache invalidation (DP-A4 pub/sub) → re-renders race badge. No durable channel-event subscription needed (race changes are EVT-T3 Derived or EVT-T4 System, propagated through normal channel event stream — UI multiplex stream catches them).

WA_006 mortality_config consumer reads `race_assignment` per-actor at runtime per WA_006-internal mortality flow (no IDF_001-specific subscription).

NPC_001 persona prompt assembly reads at SceneRoster build time (cached for batch duration per NPC_002 §6).

---

## §8 Pattern choices

### 8.1 Closed-set per-reality enum discipline (RAC-Q2 LOCKED)

`RaceId` is opaque string per-reality (NOT a global Rust enum). Different realities have different races; RealityManifest declares the closed-set. Pattern matches PF_001 places + IDF_002 languages + IDF_005 ideologies.

### 8.2 Birth-fixed V1 immutability (RAC-Q1 LOCKED)

Race assignment is **immutable V1** (cannot mutate `race_id` field once assigned). Mutation rejected with `race.assignment_immutable`. AdminOverride variant for forensic-only edits (V1 ships AdminOverride path; not user-facing). V1+ Reincarnation/Transformation lifts via additive AssignmentReason variants.

### 8.3 Cross-actor uniformity (matches IDF folder pattern)

Same `race_assignment` aggregate covers PC + NPC. Synthetic actors (ChorusOrchestrator / BubbleUpAggregator) don't get rows V1 (matches IDF_003 PRS-Q11 + IDF_004 ORG-Q7 discipline).

### 8.4 Per-event runtime lookup for default_mortality_kind_override (RAC-Q9 LOCKED)

WA_006 mortality_config consumer reads race + override at runtime per-event (NOT cached at canonical bootstrap). Race may be Admin-edited; runtime lookup ensures correctness.

### 8.5 V1+ Lex axiom gate hook reservation (RAC-Q5 LOCKED)

`AxiomDecl.requires_race: Option<Vec<RaceId>>` field reserved V1+ at WA_001 closure pass. V1: optional field present but always None (no race-gated axioms shipped V1). V1+ first race-gated axiom (e.g., qigong restricted to Cultivator) demonstrates the gate.

### 8.6 RealityManifest `races` REQUIRED V1 (RAC-Q6 LOCKED)

Every reality MUST declare ≥1 race in `RealityManifest.races`. Modern reality with single Human race still explicit; no implicit defaults. Mirrors PF_001 places REQUIRED pattern.

### 8.7 6-variant SizeCategory (RAC-Q4 LOCKED per POST-SURVEY-Q2)

`SizeCategory` ships 6 variants V1 (Pathfinder 2e full coverage). Future-proofs wuxia content (Gargantuan Dragons / Tiny spirits) + sci-fi (Drones Tiny / Mecha Gargantuan) + Modern (Medium-only).

### 8.8 Single u16 lifespan years (RAC-Q3 LOCKED)

`default_lifespan_years: u16` — single value V1 (no distribution). V1+ may add distribution (mean + stddev) when scheduler ships V1+30d for deterministic per-actor lifespan variance (RAC-D5).

---

## §9 Failure-mode UX

Reject paths split by validator stage owner per [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md).

| Reject reason | Stage | When | Vietnamese reject copy |
|---|---|---|---|
| `race.unknown_race_id` | 0 schema | RaceId not declared in reality's RealityManifest.races | "Tộc loại không tồn tại trong thế giới này." |
| `race.assignment_immutable` | 7 world-rule | V1 attempt to mutate race_assignment.race_id rejected (V1+ Reincarnation lifts) | "Tộc loại đã được xác định và không thể thay đổi." |
| `race.lex_axiom_forbidden` | **Stage 4 lex_check** (V1+) | WA_001 Lex axiom requires_race unmet by actor | (Lex-derived copy from WA_001) — V1+ first race-gated axiom |
| `race.size_category_invalid` | 0 schema | RaceDecl.size_category invalid value (canonical seed validation) | (Schema check; not user-facing) |
| `race.lifespan_invalid` | 0 schema | RaceDecl.default_lifespan_years = 0 (must be ≥ 1) | (Schema check; not user-facing) |

**`race.*` V1 rule_id enumeration** (IDF_001-owned; registered in `_boundaries/02_extension_contracts.md` §1.4):

1. `race.unknown_race_id` — RaceId not in RealityManifest.races
2. `race.assignment_immutable` — V1 mutation reject
3. `race.lex_axiom_forbidden` — V1+ Lex gate (V1 reserved; first axiom V1+)
4. `race.size_category_invalid` — schema validation
5. `race.lifespan_invalid` — schema validation

V1+ reservations: `race.cross_reality_mismatch` (V2+ Heresy migration); `race.transformation_invalid` (V2+); `race.reincarnation_invalid_target` (V1+ Reincarnation flow); `race.cyclic_lineage_v1plus` (V1+ FF_001 family graph integration).

V1 user-facing rejects: `race.unknown_race_id` + `race.assignment_immutable` only. Schema-level rejects (size/lifespan) unreachable in normal operation (canonical seed validates RaceDecl pre-bootstrap).

---

## §10 Cross-service handoff (canonical seed flow)

Concrete example: Wuxia reality bootstrap with 5 races + 4 canonical actors (Lý Minh + Tiểu Thúy + Du sĩ + Lão Ngũ).

```
1. RealityBootstrapper service (Bootstrap role):
     a. Read RealityManifest with races: 5 RaceDecl entries
     b. For each canonical actor:
        - Determine RaceId from canonical actor declaration
        - Emit EVT-T4 System sub-type RaceBorn { reality_id, actor_id, race_id }
          (one per actor; emitted alongside EF_001 EntityBorn)
        - dp::t2_write::<RaceAssignment>(ctx, actor_id, AssignRaceDelta {
            race_id, reason: AssignmentReason::CanonicalSeed
          }) → T1 (Derived)
        - causal_refs = [reality_bootstrap_event_id]
     c. Repeat for 4 canonical actors
   Result: 4 race_assignment rows committed; each with audit reason

2. PC creation flow (V1+ when PC creation form ships):
   PC LM01 selects "Cultivator" race from reality's allowed set (UI form):
     a. Validate RaceId in RealityManifest.races (Stage 0 schema)
     b. dp::t2_write::<RaceAssignment>(ctx, LM01, AssignRaceDelta {
          race_id: "race_cultivator_tusi",
          reason: AssignmentReason::PcCreation
        }) → T2 (Derived)
     c. UI receives → renders race badge "Tu sĩ" (Vietnamese) / "Cultivator" (English)

3. WA_006 Mortality runtime lookup (per Strike event):
   At validator Stage 7 world-rule physics for Strike event:
     a. dp::read_projection_reality::<RaceAssignment>(ctx, target_actor_id)
        → returns RaceAssignment { race_id: "race_cultivator_tusi", ... }
     b. dp::read_reality_manifest(ctx).races[race_id].default_mortality_kind_override
        → Some(MortalityKind::Permadeath)
     c. WA_006 mortality_config resolves: race override (Permadeath) takes precedence over reality default
     d. Strike outcome derives MortalityTransition Alive→Dead (no respawn)

4. V1+ Lex axiom gate (V1+ when first race-gated axiom ships):
   At Stage 4 lex_check for Use kind with item=spell_scroll:
     a. dp::read_projection_reality::<RaceAssignment>(ctx, agent_id) → Cultivator
     b. AxiomDecl.requires_race = Some(["race_cultivator_tusi"])
     c. Cultivator ✓ — axiom permits qigong-related Use; Phàm nhân would reject `race.lex_axiom_forbidden`
```

**Token chain:** RaceBorn (T4 System) → AssignRace (T3 Derived). Multi-actor canonical seed is sequential per DP-A19 monotonic per-channel ordering.

---

## §11 Sequence: Canonical seed (Wuxia 5-race bootstrap)

```
RealityBootstrapper service @ reality-bootstrap event for Wuxia reality:

  Read RealityManifest:
    races: [
      RaceDecl { race_id: "race_human_phamnhan", display_name: I18nBundle{"Mortal" / "vi": "Phàm nhân" / "zh": "凡人"}, lifespan: 80, size: Medium, override: None, axiom_tags: [] },
      RaceDecl { race_id: "race_cultivator_tusi", display_name: I18nBundle{"Cultivator" / "vi": "Tu sĩ" / "zh": "修士"}, lifespan: 600, size: Medium, override: Some(Permadeath), axiom_tags: ["qigong", "spirit_sense"] },
      RaceDecl { race_id: "race_demon_yao", lifespan: 1200, size: Large, override: Some(Permadeath), axiom_tags: ["natural_weapons", "demonic_arts"] },
      RaceDecl { race_id: "race_ghost_qui", lifespan: 1 (placeholder; AlreadyDead override bypasses age tracking), size: Medium, override: Some(AlreadyDead), axiom_tags: ["incorporeal"] },
      RaceDecl { race_id: "race_beast_thuyao", lifespan: 200, size: Large, override: Some(Permadeath), axiom_tags: ["natural_weapons"] },
    ]
  Validate:
    - All RaceDecl entries pass schema (Stage 0)
    - All race_id strings unique within RealityManifest.races
    - All size_category values valid (6-variant enum)
    - All lifespan_years ≥ 1 (lifespan=0 reject; Ghost race uses lifespan=1 placeholder + override=AlreadyDead bypasses age tracking — Phase 3 cleanup note)
  ✓ schema OK

  For canonical actor Lý Minh (race=Cultivator):
    Emit EVT-T4 System: RaceBorn { actor_id: LM01, race_id: "race_cultivator_tusi" }
    dp::t2_write::<RaceAssignment>(ctx, LM01, AssignRaceDelta {
      race_id: "race_cultivator_tusi",
      reason: AssignmentReason::CanonicalSeed,
      assigned_at_turn: 0,
      assigned_at_fiction_ts: <reality_start_fiction_ts>,
    }) → T1 Derived
    causal_refs = [reality_bootstrap_event_id]

  Repeat for Tiểu Thúy / Du sĩ / Lão Ngũ (all races declared in their canonical seed entries).

UI receives RaceBorn + AssignRace events; renders race badges per actor.
```

---

## §12 Sequence: PC creation (V1+ form)

```
PC creation form (V1+ when PCS_001 PC creation flow ships):

UI:
  - Display reality's allowed races: Phàm nhân / Cultivator / Demon / Ghost / Beast
  - PC selects "Cultivator" → race_id="race_cultivator_tusi"
  - Submit form

gateway:
  POST /v1/pc-create { reality_id, actor_id, name, race_id, ... }

world-service:
  a. claim_turn_slot
  b. validator stages 0-9 ✓
     Stage 0 schema: race_id="race_cultivator_tusi" is in RealityManifest.races ✓
     Stage 7 world-rule: PC creation derivation
       ActualOutputs:
         OutputDecl { target: Actor(LM01), aggregate: race_assignment,
                      delta: AssignRace { race_id: "race_cultivator_tusi",
                                           reason: AssignmentReason::PcCreation } }
  c. dp.advance_turn → Submitted T1
  d. IDF_001 owner-service emits Derived:
     dp.t2_write::<RaceAssignment>(ctx, LM01, AssignRaceDelta { ... }) → T2
     causal_refs=[T1]
  e. release_turn_slot

UI:
  - receives T2 → display race badge "Tu sĩ" (Vietnamese)
  - tooltip shows: "Cultivator (Tu sĩ) • lifespan 600yr • Medium • can practice qigong + spirit_sense"
```

---

## §13 Sequence: WA_006 mortality lookup (Strike target → race-based mortality_kind)

```
PC LM01 strikes target_npc with sword (V1+ combat):

world-service @ Stage 7 world-rule physics:
  - read pc_stats_v1_stub.hp(target_npc) → 30
  - compute clamped HpDelta = -30 → target hp would reach 0
  - resolve MortalityTransition variant:
    a. dp::read_projection_reality::<RaceAssignment>(ctx, target_npc)
       → RaceAssignment { race_id: "race_demon_yao", ... }
    b. dp::read_reality_manifest(ctx).races["race_demon_yao"].default_mortality_kind_override
       → Some(MortalityKind::Permadeath)
    c. mortality_config.race_override resolves: Permadeath (race override takes precedence over reality default)
    d. ActualOutputs include MortalityTransition { from: Alive, to: Dead { died_at_turn, died_at_cell } }

PCS_001 owner-service consumes Derived → updates pc_mortality_state to Dead.
NPC owner-service (or future NPC_NNN_mortality) does similar.
UI renders death scene per CSC_001 Layer 4 narration (race-aware: Demon death vs Phàm nhân death = different prose).
```

---

## §14 Sequence: V1+ Lex axiom gate (race-gated qigong)

```
PC LM01 (Cultivator race) attempts Use spell scroll item @ Stage 4 lex_check:

  WA_001 Lex axiom check for Use kind:
    AxiomDecl matched: { axiom_id: "qigong_minor_healing", requires_race: Some(["race_cultivator_tusi"]) }
    a. dp::read_projection_reality::<RaceAssignment>(ctx, LM01)
       → RaceAssignment { race_id: "race_cultivator_tusi", ... }
    b. axiom.requires_race.contains(LM01.race_id) → ✓
    c. axiom permits Use → continue Stage 4
  Stage 4 lex_check passes; Stage 7 derives healing effect.

Same flow with PC=Phàm nhân:
    a. RaceAssignment.race_id = "race_human_phamnhan"
    b. axiom.requires_race.contains(...) → ✗
    c. REJECTS with `race.lex_axiom_forbidden` (Vietnamese: "Tộc Phàm nhân không thể sử dụng đạo thuật này.")
```

---

## §15 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service can pass these scenarios.

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-RAC-1** | Wuxia reality declares 5-race preset; canonical bootstrap assigns races to 4 canonical actors | 4 race_assignment rows committed; each with AssignmentReason=CanonicalSeed; RaceBorn events emitted alongside EF_001 EntityBorn |
| **AC-RAC-2** | LM01 (PC) created via V1+ PC creation form with race=Cultivator | race_assignment row committed with AssignmentReason=PcCreation; UI displays Tu sĩ badge; tooltip shows lifespan=600yr + axiom_tags |
| **AC-RAC-3** | Tiểu Thúy (NPC) declared at canonical seed with race=Phàm nhân | row committed; UI tooltip shows Phàm nhân + lifespan=80yr |
| **AC-RAC-4** | Modern reality declares 1-race preset (Human only); single PC + 3 NPCs all assigned race=Human | 4 race_assignment rows; all race_id="race_human_modern" |
| **AC-RAC-5** | I18nBundle resolves race display_name correctly across locales | display_name.translations["vi"]="Tu sĩ" / default="Cultivator" / translations["zh"]="修士" |
| **AC-RAC-6** | WA_006 mortality lookup for race=Ghost target | resolves MortalityKind=AlreadyDead per race override |
| **AC-RAC-7** | WA_006 mortality lookup for race=Cultivator target with hp→0 | resolves MortalityKind=Permadeath; no respawn |

### 15.2 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-RAC-V1+1** | V1+ Lex axiom requires_race=[Cultivator]; LM01 (Cultivator) Use qigong scroll passes | V1+ when first race-gated axiom ships in WA_001 closure pass |
| **AC-RAC-V1+2** | Phàm nhân attempts qigong Use (race-gated axiom) | V1+ rejected with `race.lex_axiom_forbidden` |
| **AC-RAC-V1+3** | Reincarnation event Reincarnate { from: Cultivator, to: Phàm nhân child } | V1+ when scheduler V1+30d ships |

### 15.3 Failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-RAC-8** | Actor created with unknown RaceId not in RealityManifest.races | rejected at Stage 0 schema with `race.unknown_race_id`; turn_number unchanged |
| **AC-RAC-9** | Forge admin overrides LM01.race from Cultivator to Phàm nhân | EVT-T8 Forge:EditRaceAssignment audit emitted; race_assignment updated with AdminOverride reason; 3-write transaction atomic (race_assignment + Forge:EditRaceAssignment + forge_audit_log) |
| **AC-RAC-10** | V1 attempt to mutate race_assignment.race_id (non-Forge path) | rejected with `race.assignment_immutable` |

### 15.4 Status transition criteria

- **DRAFT → CANDIDATE-LOCK:** design complete + boundary registered (`race_assignment` aggregate row + `race.*` namespace V1 enumeration + `races` RealityManifest extension + `RAC-*` stable-ID prefix). All AC-RAC-1..10 specified with concrete fixtures.
- **CANDIDATE-LOCK → LOCK:** all AC-RAC-1..10 V1-testable scenarios pass integration tests in world-service against Wuxia + Modern reality fixtures. V1+ scenarios (AC-RAC-V1+1..3) deferred per §17.

---

## §16 Boundary registrations (in same commit chain)

DRAFT promotion registers:

1. `_boundaries/01_feature_ownership_matrix.md`:
   - NEW row: `race_assignment` aggregate (T2/Reality, owner=IDF_001 Race Foundation)
   - EVT-T4 System sub-type ownership row: add `RaceBorn` (IDF_001 owns)
   - EVT-T8 Administrative sub-shape row: add `Forge:EditRaceAssignment` (IDF_001 owns)
2. `_boundaries/02_extension_contracts.md`:
   - §1.4 RejectReason namespace: NEW `race.*` row with 5 V1 rule_ids + 4 V1+ reservations
   - §2 RealityManifest: NEW `races: Vec<RaceDecl>` REQUIRED V1 extension entry
   - Stable-ID prefix table: NEW `RAC-*` row (axioms / deferrals / decisions)
3. `_boundaries/99_changelog.md`: append DRAFT entry

---

## §17 Open questions deferred + landing point

| ID | Question | Defer to |
|---|---|---|
| **RAC-D1** | Race traits affecting combat (Cultivator HP modifier; Demon damage modifier; Beast natural weapons) | V1+ combat feature |
| **RAC-D2** | Race-conflict opinion modifier (Cultivator vs Demon = -10 opinion baseline) | V1+ NPC personality enrichment (PL_005c §5.3 cross-cutting opinion calculation) |
| **RAC-D3** | Mixed-race lineage / hybrid races (half-Demon, half-Human) | V1+ FF_001 Family Foundation feature |
| **RAC-D4** | Reincarnation race transition (Cultivator dies → reborn as Human child) | V1+ scheduler V1+30d |
| **RAC-D5** | Lifespan distribution (mean + stddev for variance) | V1+ when scheduler needs deterministic per-actor lifespan |
| **RAC-D6** | Cross-reality race remap policy | V2+ Heresy migration |
| **RAC-D7** | RaceTransformation event sub-type (Human → Demon via deviation) | V2+ |
| **RAC-D8** | Race-driven appearance defaults (height range / typical features) | V1+ cosmetic (NOT IDF folder per IDF-FOLDER-Q4 LOCKED — IDF stays at demographic substrate layer) |
| **RAC-D9** | Race-driven name pattern (Cultivator daoist names vs Phàm nhân village names) | V1+ FF_001 + cultural_tradition_pack enrichment |
| **RAC-D10** | Race lifespan vs mortality interaction (Cultivator 600yr but death-by-Strike treated equally) | V1+ combat + WA_006 cross-design |
| **RAC-D11** (Phase 0 survey) | Cultivation realm (mutable rank-tier within Cultivator race) — NOT IDF_001 expansion; SEPARATE V1+ feature CULT_001 Cultivation Foundation per POST-SURVEY-Q5 | V1+ CULT_001 Cultivation Foundation (separate feature; defer until first non-SPIKE_01 wuxia content needs realm progression). All wuxia game references separate race from realm. |

---

## §18 Cross-references

**Foundation tier (load-bearing):**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) — source-of-truth for actor_id in race_assignment
- [`PF_001 RealityManifest extension pattern`](../00_place/PF_001_place_foundation.md) — `places: Vec<PlaceDecl>` REQUIRED V1 mirror
- [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md) — display_name type for declarative names

**Sibling IDF:**
- [`IDF_002 Language`](IDF_002_language_concept.md) — race optional ref V1+ (LNG-D9)
- [`IDF_003 Personality`](IDF_003_personality_concept.md) — independent V1
- [`IDF_004 Origin`](IDF_004_origin_concept.md) — origin pack may suggest default race (V1+ enrichment)
- [`IDF_005 Ideology`](IDF_005_ideology_concept.md) — race + ideology jointly gate Lex axioms (V1+ companion fields)

**Consumers:**
- Future PCS_001 — PC creation form selects RaceId
- Future `NPC_NNN_mortality` — NPC race-affected lifespan / mortality
- WA_001 Lex (V1+ closure) — `AxiomDecl.requires_race` field
- WA_006 Mortality — `default_mortality_kind_override` lookup
- NPC_002 (V1+) — race-conflict opinion modifier (RAC-D2)
- V1+ CULT_001 — Cultivator race actors only (RAC-D11)

**Event model + boundaries:**
- [`07_event_model/02_invariants.md`](../../07_event_model/02_invariants.md) EVT-A1..A12 — taxonomy + extensibility
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) EVT-T3 Derived + EVT-T4 System (RaceBorn) + EVT-T8 Administrative
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — race_assignment aggregate + sub-type ownership
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — `race.*` V1 rule_id enumeration; §2 — RealityManifest `races` extension
- [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) — Stage 4 lex_check (V1+ axiom gate)

**Spike + research:**
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Wuxia reality canonical content (5 races used in turn 5 + turn 8)
- [`_research_character_systems_market_survey.md`](_research_character_systems_market_survey.md) §4.1 + §6.1 + §9.1 — Race patterns survey

---

## §19 Implementation readiness checklist

This doc satisfies items per DP-R2 + 22_feature_design_quickstart.md:

- [x] §2 Domain concepts + RaceId / RaceDecl / race_assignment / AssignmentReason / SizeCategory (6-variant)
- [x] §2.5 Event-model mapping (T3 Derived + T4 System RaceBorn + T8 Forge:EditRaceAssignment; no new EVT-T*)
- [x] §3 Aggregate inventory (1 new: `race_assignment` T2/Reality)
- [x] §4 Tier+scope (per DP-R2)
- [x] §5 DP primitives by name
- [x] §6 Capability JWT requirements
- [x] §7 Subscribe pattern (UI invalidation + WA_006 / NPC_002 / Lex consumer reads)
- [x] §8 Pattern choices (closed-set / immutable V1 / cross-actor uniformity / runtime mortality lookup / Lex hook V1+ / RealityManifest REQUIRED / 6-size SizeCategory / single u16 lifespan)
- [x] §9 Failure UX (race.* V1 namespace 5 rules + 4 V1+ reservations)
- [x] §10 Cross-service handoff (4 flows: bootstrap + PC creation + mortality lookup + V1+ Lex gate)
- [x] §11-§14 Sequences (canonical seed / PC creation / mortality lookup / V1+ Lex axiom gate)
- [x] §15 Acceptance criteria (10 V1-testable + 3 V1+ deferred)
- [x] §16 Boundary registrations (in same commit)
- [x] §17 Deferrals RAC-D1..D11 (11 items; D11 from POST-SURVEY-Q5)
- [x] §18 Cross-references
- [x] §19 Readiness (this section)

**Phase 3 cleanup applied 2026-04-26 (in IDF_001 commit 2/15 cycle):**
- S1.1 §2 RaceId clarified as typed newtype `pub struct RaceId(pub String)` (matches PlaceId / ChannelId pattern from foundation tier); cross-type collision avoidance noted vs LangCode + LanguageId
- S1.2 §2 MortalityKind clarified as **WA_006-owned** (IDF_001 imports; does not redefine); Ghost AlreadyDead override semantics documented (§11 Phase 3 note)
- S2.1 §11 Wuxia bootstrap sequence Ghost lifespan changed from `0 (immortal)` → `1 (placeholder; AlreadyDead bypasses)` to comply with `lifespan_years ≥ 1` schema rule
- S2.2 §11 Validate step rewording — Ghost lifespan=1 placeholder + override=AlreadyDead path documented (no schema rule violation)
- S3.1 §2 cross-feature distinction for RaceId vs LangCode (RES_001) vs LanguageId (IDF_002) — runtime newtype prevents accidental cross-type assignment

**Status transition:** DRAFT 2026-04-26 (Phase 3 applied) → **CANDIDATE-LOCK** in next commit (3/15) → **LOCK** when AC-RAC-1..10 pass integration tests + V1+ scenarios pass after WA_001 closure pass + V1+30d scheduler ships.

**Next** (when CANDIDATE-LOCK granted): world-service can scaffold race assignment for canonical seed + PC creation; WA_006 mortality_config consumer wired up; V1+ Lex axiom gate hook reserved at WA_001 closure pass.
