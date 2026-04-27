# PROG_001 — Progression Foundation

> **Category:** PROG — Progression Foundation (foundation tier; 6th foundation feature alongside EF_001 / PF_001 / MAP_001 / CSC_001 / RES_001; Tier 5 Actor Substrate post-IDF + FF coexisting tier)
> **Catalog reference:** [`catalog/cat_00_PROG_progression.md`](../../catalog/cat_00_PROG_progression.md) (owns `PROG-*` stable-ID namespace)
> **Status:** DRAFT 2026-04-26 — All 7 critical scope questions LOCKED via 6-batch deep-dive 2026-04-26 (Q1+Q6 / Q2 / Q3 / Q4+Q5 batched / Q4+Q5 REVISED quantum-observation / Q7). Companion documents: [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q7 LOCKED matrix §11) + [`02_CHAOS_BACKEND_REFERENCE.md`](02_CHAOS_BACKEND_REFERENCE.md) (chaos-backend repo analysis — actor-core aggregation pipeline + damage law chain).
>
> **CLOSURE-PASS-EXTENSION 2026-04-27 (TDIL_001 DRAFT promotion):** Q3f "DailyBoundary only V1" Generator semantic SUPERSEDED by TDIL-A3 per-turn O(1) Generator semantic (architecture-scale TDIL_001 Time Dilation Foundation). Mechanical revision: `Scheduled:CultivationTick` Generator binding changes from `EVT-G2 FictionTimeMarker (day-boundary)` to **per-turn fire** with elapsed-time parameter. Computation invariant: `delta = base_rate × elapsed_time × multiplier` (O(1) regardless of `time_flow_rate` magnitude). Per TDIL-A4 actor-bound clock-source matrix, CultivationTick reads `body_clock` (BodyOrSoul::Body progressions) or `soul_clock` (BodyOrSoul::Soul progressions) per ProgressionKindDecl.body_or_soul discriminator — NOT channel `wall_clock`. NO semantic change to user-facing behavior (PCs still cultivate per fiction-time elapsed; Tracked NPCs lazy materialization preserved); all V1 acceptance scenarios AC-PROG-1..12 preserved. Cross-realm tu tiên (Tây Du Ký heaven 0.0027× / Dragon Ball chamber 365×) now correctly handled by elapsed-time multiplication. Affected sections: §6 Training Triggers (Time-source semantic), §7 Hybrid Observation NPC Model (Tracked NPC lazy materialization formula), §12 Generator Bindings (Scheduled:CultivationTick binding row), §14 Cascade Integration (EVT-G2 → per-turn fire). PROG-D19 RES_001 alignment concern resolved via TDIL-A3 unified per-turn semantic. See [TDIL_001 §6 Generator clock-source matrix](../17_time_dilation/TDIL_001_time_dilation_foundation.md#6-generator-clock-source-matrix-q6-locked) for full clock-source matrix and [TDIL_001 §6.4 closure-pass coordination](../17_time_dilation/TDIL_001_time_dilation_foundation.md#64-closure-pass-coordination) for cascade rationale.
> **i18n compliance:** Conforms to RES_001 §2 cross-cutting pattern — all stable IDs English `snake_case` / `PascalCase`; all user-facing strings `I18nBundle`.
> **V1 testable acceptance:** 12 scenarios AC-PROG-1..12 (§16).
> **Supersedes:** DF7 PC Stats placeholder (V1-blocking deferred since 2026-04-23). DF7-V1+ becomes "Combat Damage Formulas Full" sub-feature reading PROG_001 ProgressionInstance values (per chaos-backend law chain — PROG-D24).

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

Per user direction 2026-04-26: LoreWeave is **simulation/strategy game with RPG core**, NO level / NO power-rating concept. Combat outcomes derive from RELEVANT specific attributes/skills, not aggregate "power level". Engine cannot fix one progression schema — modern social ≠ tu tiên cultivation ≠ traditional D&D. Author declares schema per reality; engine instantiates per actor.

Without PROG_001, V1 cannot ship:
- Combat (no stats to feed damage formula)
- Cultivation (tu tiên realities have no progression substrate)
- Skill checks (PL_005 actions can't be gated by competence)
- Character growth (PCs/NPCs static; no agency through training)
- Multi-system progression (one PC with both martial + alchemy skills simultaneously)

PROG_001 establishes the value-substrate for ALL actor progression dimensions across genres.

### V1 minimum scope (per Q1-Q7 LOCKED in CONCEPT_NOTES §11)

- **1 NEW aggregate** (Q6): `actor_progression` (T2/Reality, owner=Actor only V1; Item V1+30d reserved)
- **3 ProgressionType variants** (Q1): `Attribute` / `Skill` / `Stage` (V1+ ResourceBound reserved)
- **Optional `derives_from`** (Q1): Skill ← Attribute training rate scaling (V1 ship; query-value bonus V1+30d)
- **`BodyOrSoul` discriminator** (Q1 NEW): xuyên không cross-reality stat translation hint (Body/Soul/Both; default Body)
- **3 curve types** (Q2): `Linear` / `Log` / `Stage` with breakthrough; flat tier list
- **4 CapRule types** (Q2): `SoftCap` / `HardCap` / `TierBased` / `Unbounded`
- **Per-tier `WithinTierCurve`** override (Q2f) for Stage type
- **2 training trigger sources** (Q3): `Action` (PL_005 cascade) + `Time` (day-boundary Generator)
- **3 TrainingCondition types** (Q3): `LocationMatch` / `StatusRequired` / `StatusForbidden`
- **NEW Generator** (Q3): `Scheduled:CultivationTick` (day-boundary; sequenced 5th after RES_001's 4)
- **Hybrid observation-driven NPC model** (Q4 REVISED): PC eager Generator + Tracked NPC lazy materialization + Untracked NPC = no aggregate (future AI Tier feature owns)
- **`last_observed_at_fiction_ts`** + **`tracking_tier`** fields (Q4 REVISED)
- **NO atrophy V1** (Q5 REVISED — V1+ landing as lazy at materialization, not Generator)
- **Hybrid combat damage** (Q7): LLM proposes damage_amount in PL_005 Strike payload; engine validator computes bounds [min, max] from PROG_001 stats; clamps silently
- **Per-reality `StrikeFormulaDecl`** (Q7) with offense/defense terms + factors + post_damage_hooks
- **4 RealityManifest extensions** (all OPTIONAL V1)
- **2 NEW EVT-T3 sub-shapes** (`ProgressionDelta` + `ActorProgressionMaterialized`) + 1 cascade-trigger (`BreakthroughAdvance`)
- **2 NEW AdminAction sub-shapes** (`Forge:GrantProgression` + `Forge:TriggerBreakthrough`)
- **7 V1 rule_ids** in `progression.*` namespace

### V1 NOT shipping (deferred per Q-decisions)

| Feature | Defer to | Why |
|---|---|---|
| `ResourceBound` ProgressionType (mana-pool style) | V1+30d (PROG-D31 reserved) | Q1b — V1 ships 3 types only |
| DiscreteLevelup curve (D&D point allocation) | V1+30d (PROG-D1) | Q2 — interactive UI requires |
| Failed breakthrough narrative (走火入魔) | V1+30d (PROG-D2) | Q2d — silent V1 |
| `mentor_required` BreakthroughCondition active | V1+30d (PROG-D3) | Q2 + Q3b — depends mentor source |
| `fiction_time_window` BreakthroughCondition active | V1+30d (PROG-D4) | Q2 — full-moon cultivation etc. |
| Skill atrophy/decay | V1+30d (PROG-D5) | Q5 — defer; mechanism is lazy at materialization V1+ |
| Subsystem stacking (chaos-backend Contribution pattern) | V1+30d (PROG-D6) | Q1+Q6 — V1 raw_value only |
| Realm-stage nested hierarchy | V2 (PROG-D7) | Q2 — flat tier list V1; nest only if proven limiting |
| `TrainingSource::Mentor` — multiplier | V1+30d (PROG-D8) | Q3b — depends Subsystem stacking |
| Variable / Random `TrainingAmount` | V1+30d (PROG-D9) | Q3d — Fixed only V1 |
| `ActorClassMatch` / `FictionTimeWindow` / `RelationshipRequired` TrainingConditions | V1+30d (PROG-D10/D11/D12) | Q3e — 3 V1 only |
| `HourlyBoundary` / Custom TickPeriod | V1+30d (PROG-D13) | Q3f — DailyBoundary only V1 |
| `TrainingSource::Quest` | V2 (PROG-D14) | Q3c — QST_001 dependency |
| `InstrumentClass` match | V1+30d (PROG-D15) | Q3 — broader category match V1+ |
| RES_001 NPC eager → lazy migration | V1+30d (PROG-D19) | Q4 REVISED — RES_001 closure pass alignment |
| Intermediate-state interpolation | V1+ (PROG-D20) | Q4 REVISED — V1 conservative single-state |
| NPC-to-NPC cascade during un-observed period | V2 (PROG-D21) | Q4 REVISED — complex determinism |
| Untracked → Tracked tier promotion | future AI Tier feature (PROG-D22) | Q4 REVISED — out of PROG_001 scope |
| Closed-form materialization optimization | V1+30d (PROG-D23) | Q4 REVISED — V1 per-day replay |
| DF7-equivalent full damage law (chaos-backend chain) | V1+ (PROG-D24) | Q7c — V1 hybrid bounds only |
| Critical hits | V1+ (PROG-D25) | Q7d |
| AoE multi-target Strike | V1+ (PROG-D26) | Q7g |
| Damage type variety (physical / magical / spiritual / true) | V1+ (PROG-D27) | Q7c |
| Per-instrument formula override | V1+30d (PROG-D28) | Q7 — simple extension |
| `Forge:EditStrikeFormula` AdminAction | V1+30d (PROG-D29) | Q7 — runtime formula authoring |
| Element-stat multiplicative chain | V1+ (PROG-D30) | Q7c — chaos-backend invariant |
| Cross-actor `TrainingSource::CrossActor` (one action affects 2 actors) | V1+30d (PROG-D33) | CULT_001 stress-test pre-audit 2026-04-27 — supports dual cultivation (mị ma song tu) + demonic absorption (魔修) + master-pet bond + family-bond cultivation. Schema-additive new TrainingSource enum variant. |
| `ProgressionDeltaKind::RawValueDecrement` V1+ active (drain/leech semantic) | V1+30d (PROG-D34) | CULT_001 stress-test pre-audit 2026-04-27 — supports dual cultivation cauldron drain + demonic essence absorption + lifespan-burn forbidden technique. Schema-additive (variant already implied in §8.2 V1+ atrophy decay; PROG-D34 promotes to first-class drain delta_kind). Distinct from PROG-D2 走火入魔 tier regress (different mechanic). |
| `derives_from` cross-feature source (FF_001 / FAC_001 / REL_001 state → rate multiplier) | V2 (PROG-D35) | CULT_001 stress-test pre-audit 2026-04-27 — supports family-count-multiplies-power (đa phúc đa tử) + sect-membership-multiplies-cultivation-rate. Currently DerivationDecl only references PROG_001 self-attributes; V2 extends source kind to cross-feature aggregate state observers. |
| `BreakthroughCondition::KarmaThreshold` variant (heart demon / 心魔 gating) | V1+30d (PROG-D36) | CULT_001 stress-test pre-audit 2026-04-27 — supports heart-demon karma cultivation (good/bad karma thresholds gating breakthroughs). Schema-additive new BreakthroughCondition enum variant. Karma source = WA_001 Lex axiom or future KARMA_001 feature. |
| `RebirthBonusDecl` RealityManifest extension (cumulative per-death bonus) | V2 (PROG-D37) | CULT_001 stress-test pre-audit 2026-04-27 — supports rebirth cultivation (chết trùng sinh mạnh hơn) where each death adds permanent stat/tier bonus to next incarnation. Cross-feature dependency: WA_006 mortality death event + PCS_001 xuyên không soul-layer + new aggregate `actor_rebirth_count`. Author declares `per_death_bonus: HashMap<ProgressionKindId, u64>` per reality. |

---

## §2 — i18n Contract Reference

PROG_001 conforms to **RES_001 §2 i18n contract** (cross-cutting pattern; engine standard since 2026-04-26):

- **Stable identifiers** in code/schema/rule_ids/event sub-types/enum variants are **English `snake_case`** / `PascalCase`
- **User-facing strings** use **`I18nBundle { default: String, translations: HashMap<LangCode, String> }`** with English `default` required
- **Author-declared content** (kind_id strings, custom progression kinds) is multi-language via I18nBundle

PROG_001 conformance checklist:
- ✅ All `rule_id` English: `progression.training.kind_unknown`, `progression.combat.formula_invalid`, etc.
- ✅ All `aggregate_type` English: `actor_progression`
- ✅ All EVT-T3/T5 sub-shapes English: `ProgressionDelta`, `Scheduled:CultivationTick`, `ActorProgressionMaterialized`, `BreakthroughAdvance`
- ✅ All engine enum variants English: `ProgressionType::Attribute`, `BodyOrSoul::Body`, `CurveDecl::Stage`
- ✅ All user-facing strings I18nBundle: `ProgressionKindDecl.display_name`, `ProgressionKindDecl.description`, `TierDecl.name`

Author-content example (Vietnamese xianxia reality with Chinese term display):
```rust
ProgressionKindDecl {
    kind_id: ProgressionKindId("qi_cultivation".into()),     // English stable ID
    display_name: I18nBundle {
        default: "Qi Cultivation".to_string(),                // English required
        translations: hashmap! {
            "vi".to_string() => "Luyện khí".to_string(),
            "zh".to_string() => "炼气".to_string(),
        },
    },
    // ...
}
```

LLM narration at active locale=vi renders "Luyện khí"; locale=zh renders "炼气"; locale=en (or absent) renders "Qi Cultivation" (default).

---

## §3 — Aggregates (Q6 LOCKED)

### §3.1 `actor_progression` (T2 / Reality) — PRIMARY

**Scope:** T2/Reality (per DP-A14). One instance per Actor (PC + NPC V1 active; Item V1+30d reserved per Q6b).
**Owner:** PROG_001 Progression Foundation.
**Tracking model:** PCs eager Generator; Tracked NPCs lazy materialization on observation; Untracked NPCs = no aggregate (future AI Tier feature).

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_progression", tier = "T2", scope = "reality")]
pub struct ActorProgression {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,                              // PC + NPC V1; Item V1+30d
    pub values: Vec<ProgressionInstance>,
    pub last_modified_at_turn: u64,
    pub schema_version: u32,                              // V1 = 1

    /// Q4 REVISED: tracking tier discriminator. None V1 = use default eager-or-lazy heuristic
    /// (PCs eager; NPCs lazy when assigned). Future AI Tier feature populates with explicit Major/Minor/etc.
    pub tracking_tier: Option<NpcTrackingTier>,
}

pub struct ProgressionInstance {
    pub kind_id: ProgressionKindId,                       // matches RealityManifest schema
    pub raw_value: u64,                                   // base accrued; subsystem bonuses ADDED at query V1+30d
    pub current_tier: Option<TierIndex>,                  // None for Attribute/Skill; Some(N) for Stage type
    pub last_trained_at_fiction_ts: i64,                  // for atrophy V1+ (PROG-D5)
    pub last_observed_at_fiction_ts: i64,                 // ⭐ Q4 REVISED quantum-observation reference
    pub training_log_window: VecDeque<TrainingRecord>,    // bounded ring buffer for replay determinism per EVT-A9
}

pub struct TrainingRecord {
    pub fiction_ts: i64,
    pub source: TrainingSource,
    pub amount_applied: u32,
    pub causal_event_id: u64,
}

/// Reserved for future AI Tier feature (NOT defined in PROG_001):
/// pub enum NpcTrackingTier {
///     Major,    // full progression + LLM-driven decisions
///     Minor,    // progression but rule-based actions
///     // Untracked = absence of ActorProgression aggregate (clean default)
/// }
pub type NpcTrackingTier = String;                        // V1 placeholder; future AI Tier defines enum
```

### §3.2 Why split into separate aggregate vs extending PCS_001/NPC_001 cores

Per Q6 LOCKED — Option A (NEW aggregate) won over (B) extend cores + (C) reuse RES_001:

- **(B) extend cores REJECTED**: would modify PCS_001 + NPC_001 with different fields each (PCs eager-tracked; NPCs lazy-tracked); bloats both cores; I14 additive-only stress at scale (5+ progression dimensions); breaks single-shape pattern
- **(C) reuse RES_001 REJECTED**: SEMANTIC MISMATCH — RES_001 axiom #1 is transferability (`resource_inventory` is portable units); progression is non-transferable (skills/cultivation can't move between actors). Forcing into RES_001 would break RES axiom.
- **(A) NEW aggregate WINS**: clean separation; single shape PC+NPC; no locked-aggregate risk; matches RES_001 Q3 split discipline (vital_pool body-bound separately from resource_inventory portable).

### §3.3 Storage scope discipline

Reality-scoped index by `actor_ref → ActorProgression`. PROG_001 V1 read-side projections:
- `actor_progression_summary` for hot-path AssemblePrompt persona context (NPC_001 §6 reads this)
- `actor_progression_combat_view` for hot-path PL_005 Strike kind cascade (Q7 formula reads this)

Both are read-side projections — V1 query-time computation acceptable per Q6d (no Snapshot caching V1; turn-based latency budget).

---

## §4 — ProgressionKind Ontology (Q1 LOCKED)

### §4.1 Architecture: Unified with type discriminator

Per Q1a LOCKED — invariants giống nhau across Attribute/Skill/Stage (non-transferable + growth-driven + capped + actor-scoped + author-declared). Pattern matches PL_006 unified `actor_status`. RES_001 split discipline does NOT apply (different invariant: vital body-bound type-system enforced).

Reference chaos-backend `actor-core` 12k LOC: uses unified Subsystem→Contribution→Snapshot pipeline. Direct lift candidate V1+30d when subsystem stacking ships (PROG-D6).

### §4.2 ProgressionType enum

```rust
pub enum ProgressionType {
    Attribute,    // V1 active — innate, slow-changing, soft cap (e.g., 体质 / STR / 智)
    Skill,        // V1 active — learned, action-driven, soft cap V1 (V1+ tier-locked)
    Stage,        // V1 active — tier-based with breakthrough (e.g., 练气 9 tiers → 筑基 → 金丹 → 元婴 → 化神)
    // V1+30d reserved:
    // ResourceBound, // mana-pool-like with consumption-per-use (PROG-D31)
}
```

### §4.3 BodyOrSoul discriminator (Q1 NEW for xuyên không)

```rust
pub enum BodyOrSoul {
    Body,    // V1 default — martial / body-cultivation / motor skills (e.g., 炼体, 剑术, athletic, swordsmanship)
    Soul,    // academic / social / cognitive (e.g., 智 INT, 谈判 negotiation, language fluency, cultural knowledge)
    Both,    // hybrid — rare, mostly authorial choice (e.g., a wuxia "spirit-body harmony" technique)
}
```

xuyên không event behavior (PCS_001 mechanic per brief §S8 + RES_001 Q9c body-substitution semantics):
- **Body progressions** stay with body — new soul inherits martial skills + cultivation tier from previous occupant
- **Soul progressions** travel with soul — academic knowledge + cognitive skills + language fluency follow soul to new body
- **Both progressions** keep on both — author choice (rare)

V1 author default: `Body`. Soul-bound = explicit author declaration for cognitive/academic/social kinds.

### §4.4 ProgressionKindDecl (RealityManifest declaration shape)

```rust
pub struct ProgressionKindDecl {
    pub kind_id: ProgressionKindId,                       // author-declared stable ID
    pub display_name: I18nBundle,                         // i18n per RES_001 §2
    pub description: I18nBundle,
    pub progression_type: ProgressionType,                // Q1b discriminator
    pub body_or_soul: BodyOrSoul,                         // Q1 NEW xuyên không hint
    pub curve: CurveDecl,                                 // Q2 — Linear / Log / Stage
    pub cap_rule: CapRule,                                // Q2 — SoftCap / HardCap / TierBased / Unbounded
    pub training_rules: Vec<TrainingRuleDecl>,            // Q3 — Action + Time
    pub initial_value: u64,                               // default starting raw_value
    pub initial_tier: Option<TierIndex>,                  // Stage type; None for Attribute/Skill
    pub derives_from: Option<DerivationDecl>,             // Q1c hybrid — skill ← attribute scaling
}

pub struct DerivationDecl {
    pub source_kind_id: ProgressionKindId,                // typically Attribute kind
    pub training_rate_factor: f32,                        // training rate multiplier (e.g., 1.0 + INT*0.05)
    // Q1e — V1 only training_rate; query-value bonus V1+30d (PROG-D9 same scope)
}

pub struct ProgressionKindId(pub String);                 // e.g., "physical_strength" / "negotiation" / "qi_cultivation"
pub struct TrainingRuleId(pub String);                    // diagnostic / Forge reference
pub struct TierIndex(pub u8);                             // 0-based; flat tier list
```

### §4.5 derives_from V1 mechanics

Q1d LOCKED — Skill ← Attribute only (no circular references V1).

When training event fires for a Skill kind with `derives_from`:
1. Look up source attribute's current `raw_value` from actor's ProgressionInstance
2. Compute training rate multiplier: `1.0 + source_value * factor`
3. Apply multiplied amount to skill: `final_amount = base_amount * multiplier`

Example: `negotiation` Skill `derives_from { source: "intelligence", factor: 0.05 }`
- INT=20, base training amount=1
- Multiplier = 1.0 + 20*0.05 = 2.0
- Final amount = 1 * 2.0 = 2 (rounded down for u64)

V1 simplification: derivation only affects training rate (Q1e). V1+30d may extend to query-value bonus (skill checks read INT-bonus directly).

---

## §5 — Curves (Q2 LOCKED)

### §5.1 CurveDecl enum

Per Q2a LOCKED — 3 V1 curve types. Threshold collapsed into Stage 1-tier degenerate (Q2b). DiscreteLevelup deferred V1+30d (PROG-D1).

```rust
pub enum CurveDecl {
    Linear {
        rate_per_train_unit: f32,                         // 1.0 = standard; <1 slow learner; >1 fast
    },
    Log {
        base_rate: f32,                                   // initial gain per unit
        difficulty_factor: f32,                           // higher = sharper diminishing approach to cap
    },
    Stage {
        tiers: Vec<TierDecl>,                             // author-declared ordered; flat list (Q2i no realm-stage nesting)
    },
}
```

### §5.2 TierDecl (Stage type)

```rust
pub struct TierDecl {
    pub tier_index: TierIndex,                            // 0-based; stable per kind
    pub name: I18nBundle,                                 // "练气一层" / "Apprentice" / "Foundation Building"
    pub tier_max: u64,                                    // raw_value cap at this tier
    pub within_tier_curve: WithinTierCurve,               // Q2f per-tier override
    pub breakthrough_condition: BreakthroughCondition,
    pub initial_value_on_advance: u64,                    // Q2g typically 0; rarely carry-over
}

pub enum WithinTierCurve {
    Linear { rate_per_train_unit: f32 },
    Log { base_rate: f32, difficulty_factor: f32 },
}
```

### §5.3 BreakthroughCondition

Per Q2c LOCKED — automatic check at training-tick + author-Forge override. Q2d failed breakthrough silent V1 (走火入魔 narrative V1+30d PROG-D2).

```rust
pub enum BreakthroughCondition {
    AtMax,                                                // raw_value == tier_max alone (auto-advance)
    AtMaxPlus {
        item_consumption: Option<ResourceCost>,           // e.g., 灵丹 1 (RES_001 Consumable)
        location_required: Option<PlaceTypeRef>,          // e.g., CultivationChamber (PF_001 PlaceType)
        mentor_required: Option<MentorRequirement>,       // V1+30d active (PROG-D3); V1 schema-reserved only
        fiction_time_window: Option<FictionTimeWindow>,   // V1+30d active (PROG-D4); V1 schema-reserved only
    },
    AuthorOnly,                                           // author must trigger via Forge:TriggerBreakthrough
}

pub struct ResourceCost {                                 // reuses RES_001 ResourceCost shape
    pub kind: ResourceKind,
    pub amount: u64,
}

pub struct MentorRequirement {                            // V1+30d shape; reserved V1
    pub mentor_actor_class: ActorClassRef,
    pub mentor_min_progression: HashMap<ProgressionKindId, u64>,
}

pub struct FictionTimeWindow {                            // V1+30d shape; reserved V1
    pub days_of_year: Vec<u16>,
    pub hours_of_day: Vec<u8>,
}
```

### §5.4 CapRule enum

Per Q2e LOCKED — 4 V1 types. Validity matrix Q2j enforced at RealityManifest bootstrap.

```rust
pub enum CapRule {
    SoftCap {
        cap: u64,                                         // training stops accruing past cap with diminishing returns
    },
    HardCap {
        cap: u64,                                         // training rejected past cap; raw_value strictly ≤ cap
    },
    TierBased,                                            // cap = current_tier.tier_max; advances on breakthrough
    Unbounded,                                            // no cap (rare; V3 Knowledge kind)
}
```

### §5.5 CapRule × CurveDecl validity matrix (Q2j)

| CurveDecl | Valid CapRule(s) |
|---|---|
| `Linear` | `SoftCap` / `HardCap` / `Unbounded` (NOT `TierBased`) |
| `Log` | `SoftCap` / `HardCap` (Log inherently bounded; not `Unbounded`) |
| `Stage` | **`TierBased` only** (cap derives from tiers) |

Validator at RealityManifest bootstrap rejects invalid combinations with `progression.training.rule_invalid` (e.g., `Stage` curve with `HardCap` rule rejected).

### §5.6 Worked example — tu tiên xianxia 24-tier hierarchy

```rust
ProgressionKindDecl {
    kind_id: ProgressionKindId("qi_cultivation".into()),
    display_name: I18nBundle::en("Qi Cultivation").with_zh("炼气").with_vi("Luyện khí"),
    description: I18nBundle::en("Refining qi within the body's meridians; the foundational cultivation system"),
    progression_type: ProgressionType::Stage,
    body_or_soul: BodyOrSoul::Body,
    curve: CurveDecl::Stage {
        tiers: vec![
            // 练气 (9 tiers — qi refining)
            TierDecl {
                tier_index: TierIndex(0),
                name: I18nBundle::en("Qi Refining 1").with_zh("练气一层"),
                tier_max: 100,
                within_tier_curve: WithinTierCurve::Linear { rate_per_train_unit: 1.0 },
                breakthrough_condition: BreakthroughCondition::AtMax,
                initial_value_on_advance: 0,
            },
            // ... TierDecl entries 1..8 for 练气二层 through 九层 ...
            
            // 筑基 (foundation building)
            TierDecl {
                tier_index: TierIndex(9),
                name: I18nBundle::en("Foundation Building").with_zh("筑基"),
                tier_max: 500,
                within_tier_curve: WithinTierCurve::Log { base_rate: 1.5, difficulty_factor: 1.2 },
                breakthrough_condition: BreakthroughCondition::AtMaxPlus {
                    item_consumption: Some(ResourceCost {
                        kind: ResourceKind::Consumable(ConsumableKindId("foundation_pill".into())),
                        amount: 1,
                    }),
                    location_required: Some(PlaceTypeRef("cultivation_chamber".into())),
                    mentor_required: None,
                    fiction_time_window: None,
                },
                initial_value_on_advance: 0,
            },
            
            // ... 金丹 (golden core), 元婴 (nascent soul), 化神 (spirit transformation) ...
        ],
    },
    cap_rule: CapRule::TierBased,
    training_rules: vec![ /* §6 */ ],
    initial_value: 0,
    initial_tier: Some(TierIndex(0)),
    derives_from: None,
}
```

---

## §6 — Training Triggers (Q3 LOCKED)

### §6.1 TrainingRuleDecl

Per Q3 LOCKED — 2 V1 sources (Action + Time); Item collapses into Action `target_match` (Q3g — saves engine surface).

```rust
pub struct TrainingRuleDecl {
    pub rule_id: TrainingRuleId,
    pub source: TrainingSource,
    pub amount: TrainingAmount,
    pub conditions: Vec<TrainingCondition>,               // ALL must match (AND-semantic)
}

pub enum TrainingSource {
    Action {
        interaction_kind: InteractionKind,                // PL_005 Speak / Strike / Give / Examine / Use
        target_match: Option<TargetMatch>,
        instrument_match: Option<InstrumentMatch>,
    },
    Time {
        period: TickPeriod,                               // V1: DailyBoundary only
    },
    // V1+30d reserved:
    // Mentor { mentor_relationship: RelationshipKind, multiplier: f32 },  // PROG-D8
    // Quest { quest_id: QuestId },                                          // PROG-D14
}

pub enum TickPeriod {
    DailyBoundary,                                        // V1 active (matches RES_001 Generators)
    // HourlyBoundary,  Custom { fiction_seconds: u64 },  // V1+30d (PROG-D13)
}

pub enum TargetMatch {
    Any,
    EntityKind(EntityType),                               // Pc / Npc / Item / EnvObject
    ResourceKindMatch(ResourceKind),                      // for Item training (Use Consumable(elixir_kind))
    PlaceTypeMatch(PlaceTypeRef),
    Specific(EntityId),                                   // narrow match
}

pub enum InstrumentMatch {
    Any,
    Specific(ResourceKind),                               // training Sword skill requires Sword item as tool
    // InstrumentClass V1+30d (PROG-D15)
}

pub enum TrainingAmount {
    Fixed { amount: u32 },                                // V1 active
    // Variable / Random V1+30d (PROG-D9)
}

pub enum TrainingCondition {
    LocationMatch(PlaceTypeRef),                          // V1
    StatusRequired(StatusFlag),                           // V1
    StatusForbidden(StatusFlag),                          // V1 — Drunk reduces 经商
    // ActorClassMatch / FictionTimeWindow / RelationshipRequired V1+30d
}
```

### §6.2 Action-driven training cascade (Q3i)

PL_005 cascade post-validation runs after PL_005 OutputDecl validators pass + before turn commits:

```pseudo
PL_005 cascade post-validation (HOT-PATH):
  let interaction_kind = current_turn.interaction_kind;
  let actor_ref = current_turn.actor;
  
  // Indexed lookup: training_rules_by_interaction_kind[interaction_kind] → Vec<(kind_id, rule)>
  // Index built at RealityManifest bootstrap; O(1) lookup at hot-path
  for (kind_id, rule) in training_rules_by_interaction_kind[interaction_kind]:
    // Optional gating per rule
    if rule.target_match.matches(current_turn.target):
      if rule.instrument_match.matches(current_turn.instrument):
        if all rule.conditions match (location + status):
          // Apply training amount with derives_from rate multiplier
          let effective_amount = rule.amount.value() * actor.derives_from_multiplier(kind_id);
          actor_progression[kind_id].raw_value += effective_amount;
          actor_progression[kind_id].last_trained_at_fiction_ts = current_fiction_ts;
          
          emit ProgressionDelta {
            actor_ref, kind_id,
            delta_kind: ProgressionDeltaKind::RawValueIncrement { amount: effective_amount },
            source_event_id: current_turn.event_id,
          };
          
          // Auto-breakthrough check (Q2c)
          check_breakthrough_advance(actor_ref, kind_id);
        // Q3j silent skip if conditions unmet — no reject
```

Hot-path optimization: index `training_rules_by_interaction_kind: HashMap<InteractionKind, Vec<(ProgressionKindId, TrainingRuleDecl)>>` built at RealityManifest bootstrap. O(1) lookup per turn-event.

### §6.3 Time-driven training (Q3 + §6.4 Generator)

Time training fires via `Scheduled:CultivationTick` Generator (§7 below). Same logic as action-driven but iterates Time-source rules + applies daily.

### §6.4 Worked example — tu tiên cultivation training rules

```rust
ProgressionKindDecl {
    kind_id: ProgressionKindId("qi_cultivation".into()),
    // ... §5.6 fields ...
    training_rules: vec![
        // Auto-cultivation in cultivation chamber daily
        TrainingRuleDecl {
            rule_id: TrainingRuleId("qi_passive_cultivation".into()),
            source: TrainingSource::Time { period: TickPeriod::DailyBoundary },
            amount: TrainingAmount::Fixed { amount: 1 },
            conditions: vec![
                TrainingCondition::LocationMatch(PlaceTypeRef("cultivation_chamber".into())),
            ],
        },
        // Spirit pill consumption burst
        TrainingRuleDecl {
            rule_id: TrainingRuleId("qi_pill_burst".into()),
            source: TrainingSource::Action {
                interaction_kind: InteractionKind::Use,
                target_match: Some(TargetMatch::ResourceKindMatch(
                    ResourceKind::Consumable(ConsumableKindId("spirit_pill".into()))
                )),
                instrument_match: None,
            },
            amount: TrainingAmount::Fixed { amount: 50 },
            conditions: vec![],
        },
    ],
    // ...
}
```

### §6.5 Worked example — modern social skill

```rust
ProgressionKindDecl {
    kind_id: ProgressionKindId("negotiation".into()),
    display_name: I18nBundle::en("Negotiation").with_vi("Đàm phán"),
    description: I18nBundle::en("Skill in persuading others through dialogue"),
    progression_type: ProgressionType::Skill,
    body_or_soul: BodyOrSoul::Soul,                       // social = soul-bound
    curve: CurveDecl::Log { base_rate: 1.0, difficulty_factor: 1.5 },
    cap_rule: CapRule::SoftCap { cap: 1000 },
    derives_from: Some(DerivationDecl {                   // INT scales rate
        source_kind_id: ProgressionKindId("intelligence".into()),
        training_rate_factor: 0.05,                       // each INT pt = 5% rate boost
    }),
    training_rules: vec![
        TrainingRuleDecl {
            rule_id: TrainingRuleId("negotiate_during_speak".into()),
            source: TrainingSource::Action {
                interaction_kind: InteractionKind::Speak,
                target_match: Some(TargetMatch::EntityKind(EntityType::Npc)),
                instrument_match: None,
            },
            amount: TrainingAmount::Fixed { amount: 1 },
            conditions: vec![
                TrainingCondition::StatusForbidden(StatusFlag::Drunk),  // can't negotiate drunk
            ],
        },
    ],
    initial_value: 0,
    initial_tier: None,
    // ...
}
```

---

## §7 — Hybrid Observation NPC Model (Q4 REVISED LOCKED)

### §7.1 3-tier NPC architecture (future AI Tier feature scope)

User direction 2026-04-26: at scale (billions of NPCs vision), eager Generator iteration doesn't work. Quantum-observation principle applies — NPC state stale-until-observed (Schrödinger pattern; reference Stellaris pops / CK3 background characters / Skyrim distance culling).

| Tier | Storage V1 | Update model | V1 owner |
|---|---|---|---|
| **PC** | `ActorProgression` aggregate (full) | **Eager** — daily Generator iterates | PROG_001 V1 |
| **Tracked NPC (Major)** | `ActorProgression` aggregate (full) | **Lazy** — materialize on observation | PROG_001 V1 ships hooks; future AI Tier feature owns tier-tracking semantics |
| **Untracked NPC (Background)** | NO aggregate | LLM/RNG-generated per session; discarded | **future AI Tier feature** (out of PROG_001 scope V1; PROG_001 silently skips) |

PROG_001 V1 ships PC eager + Tracked NPC lazy hooks. Untracked NPC = absence of aggregate (clean default).

### §7.2 Future AI Tier feature reservation

`features/16_ai_tier/` placeholder pending user kickoff post-PROG_001 DRAFT.

AI Tier feature responsibilities (sketch only — not in PROG_001 scope):
- Define `NpcTrackingTier` enum (Major / Minor / Generated / etc.)
- Tier promotion mechanics (Untracked NPC → Tracked when significance threshold reached)
- Untracked NPC procedural generation (LLM-driven persona + stat synthesis on-demand)
- Discard policies (session-end / cell-leave / N-day no-observation)
- Integration with PROG_001's `tracking_tier` field
- Integration with NPC_001 ActorId
- Integration with billion-NPC scaling vision

PROG_001 V1 ships READY for AI Tier integration:
- `tracking_tier: Option<NpcTrackingTier>` field reserved (None V1 default)
- `last_observed_at_fiction_ts` field active V1
- Materialization computation function (testable V1)
- Untracked NPC = absence of aggregate (clean default semantic)

### §7.3 Generator iteration behavior (V1)

```pseudo
Scheduled:CultivationTick (day-boundary; sequenced 5th per EVT-G6 Coordinator):
  for each actor in reality where ActorProgression exists AND actor_type == PC:
    // PC eager — Generator iterates daily
    apply training rules + auto-breakthrough check
    emit ProgressionDelta events
  
  // Tracked NPCs SKIPPED at Generator (lazy)
  // Untracked NPCs absent from store (no aggregate)
```

### §7.4 Observation event triggers

When PC observes Tracked NPC, materialization fires. Observation events V1:
1. **PC enters cell containing NPC** (via PL_001 §3.6 entity_binding location change → MemberJoined cascade → PC observes all NPCs in cell)
2. **PL_005 Interaction targets NPC** (Speak / Strike / Give / Examine / Use targeting NPC)
3. **LLM-driven NPC action initiated** (NPCTurn produced by NPC_002 Chorus orchestrator)
4. **Forge edit references NPC** (WA_003 Forge AdminAction with NPC subject)
5. **Cascade event references NPC** (e.g., quest mentions NPC by name V2+)

V1: triggers 1-4 active. Trigger 5 V2+ (depends QST_001).

### §7.5 Materialization computation

```pseudo
fn materialize_actor_progression(npc: ActorRef, current_fiction_ts: i64):
  let progression = actor_progression_index[npc];
  if progression is None: return;  // untracked; no progression
  
  let mut emitted_deltas: Vec<ProgressionDelta> = vec![];
  
  for instance in progression.values:
    let elapsed_days = current_fiction_ts.day_count() - instance.last_observed_at.day_count();
    if elapsed_days <= 0: continue;  // already up-to-date
    
    let kind = reality.progression_kinds[instance.kind_id];
    
    // Conservative V1 (Q4f): replay each day applying Time-source training rules with last-known state
    for day in 0..elapsed_days:
      let simulated_ts = instance.last_observed_at + (day + 1) * fiction_day;
      
      for rule in kind.training_rules where rule.source matches Time:
        if all rule.conditions match (using NPC's last-known location + status):
          let effective_amount = rule.amount.value() * derives_from_multiplier(npc, instance.kind_id);
          instance.raw_value += effective_amount;
          
          // Auto-breakthrough check (Q2c)
          if let Some(breakthrough_event) = check_breakthrough(instance, kind):
            emitted_deltas.push(breakthrough_event);
    
    // Aggregate accrual into single delta event for batch
    if instance.raw_value changed:
      emitted_deltas.push(ProgressionDelta {
        actor_ref: npc, kind_id: instance.kind_id,
        delta_kind: ProgressionDeltaKind::RawValueIncrement { amount: ... },
        source_event_id: materialization_event_id,
      });
    
    instance.last_observed_at_fiction_ts = current_fiction_ts;
  
  // Wrap batch in ActorProgressionMaterialized event for audit trail
  emit ActorProgressionMaterialized {
    actor_ref: npc,
    materialized_at_fiction_ts: current_fiction_ts,
    deltas: emitted_deltas,
  };
```

V1 simplification: NPC stays in last-known state for entire elapsed period. V1+30d adds intermediate-state interpolation (PROG-D20).

### §7.6 RES_001 alignment concern (PROG-D19 V1+30d)

**RES_001 NPC owner auto-collect Generator** (`Scheduled:NPCAutoCollect` daily for ALL NPCs) is architecturally inconsistent with quantum-observation principle for the same reason original Q4 was wrong.

V1 keeps RES_001 eager (already CANDIDATE-LOCK; not modifying in PROG_001 DRAFT scope). V1+30d closure pass migrates RES_001 NPC economy to lazy materialization (matches PROG_001 pattern). Tracked as **PROG-D19** + downstream RES_001 closure-pass concern.

---

## §8 — Atrophy V1 (Q5 REVISED LOCKED)

### §8.1 V1 NO atrophy

Per Q5a LOCKED — NO atrophy V1. Defer V1+30d (PROG-D5).

### §8.2 V1+ atrophy mechanism shape (lazy at materialization)

Per Q5b LOCKED — V1+ atrophy applies at materialization time (not Generator). Reuses materialization pattern from §7.5.

V1+30d schema additive (per I14):
```rust
pub struct ProgressionKindDecl {
    // ... V1 fields ...
    pub atrophy_rule: Option<AtrophyRule>,                // V1+30d additive (PROG-D5)
}

pub struct AtrophyRule {                                  // V1+30d shape
    pub threshold_days: u32,                              // no decay until N days no-practice
    pub daily_decay: u32,                                 // per-day decrement after threshold
    pub floor: u64,                                       // minimum raw_value (atrophy can't go below)
}
```

V1+30d behavior:
```pseudo
fn apply_atrophy_at_materialization(instance: ProgressionInstance, current_fiction_ts: i64):
  if let Some(atrophy_rule) = instance.kind.atrophy_rule:
    let days_since_last_trained = current_fiction_ts.day_count() - instance.last_trained_at.day_count();
    if days_since_last_trained > atrophy_rule.threshold_days:
      let decay_amount = (days_since_last_trained - atrophy_rule.threshold_days) * atrophy_rule.daily_decay;
      instance.raw_value = max(atrophy_rule.floor, instance.raw_value.saturating_sub(decay_amount));
      emit ProgressionDelta with delta_kind: RawValueDecrement (V1+ enum variant)
```

For PCs (eager daily Generator): same logic but runs at daily Generator.

### §8.3 Distinguished from TierRegress (PROG-D2)

| Mechanism | Trigger | V1+30d ID | Distinction |
|---|---|---|---|
| **Atrophy** | No-practice decay (gradual) | PROG-D5 | Reduces `raw_value` based on `last_trained_at` |
| **TierRegress** | Failed breakthrough (走火入魔) | PROG-D2 | Demotes `current_tier` due to deviation event |

Both V1+30d but separate mechanisms. Atrophy uses `last_trained_at_fiction_ts`; TierRegress uses BreakthroughCondition failure event.

---

## §9 — Combat Damage Formula V1 (Q7 LOCKED)

### §9.1 Hybrid V1 architecture

Per Q7a LOCKED — LLM proposes `damage_amount` in PL_005 Strike payload; engine validator computes bounds [min, max] from PROG_001 stats; clamps silently.

Full chaos-backend law chain (`base → element_multiplier → resistance(after_penetration) → status_application`) deferred V1+ DF7-equivalent (PROG-D24/D30).

### §9.2 RealityManifest extension (Q7b)

```rust
pub struct RealityManifest {
    // ... existing PROG fields ...
    
    /// Strike formula. None V1 = default formula (LLM proposes 1..=defender_hp/2 with no stat reading).
    pub strike_formula: Option<StrikeFormulaDecl>,
}

pub struct StrikeFormulaDecl {
    pub offense_terms: Vec<StatTerm>,                     // sum these → attacker offense
    pub defense_terms: Vec<StatTerm>,                     // sum these → defender defense
    pub min_damage_factor: f32,                           // min_dmg = (offense - defense) * min_factor
    pub max_damage_factor: f32,                           // max_dmg = (offense - defense) * max_factor
    pub damage_floor: u32,                                // absolute minimum (weak attacker still scratches)
    pub post_damage_hooks: Vec<PostDamageHook>,           // Q7f status application rules
}

pub struct StatTerm {
    pub kind_id: ProgressionKindId,                       // reads ProgressionInstance.raw_value
    pub weight: f32,                                      // multiplier (strength=1.0; swordsmanship=0.5)
    pub instrument_match: Option<ResourceKind>,           // optional — apply only if matching instrument used
}

pub struct PostDamageHook {
    pub damage_threshold: u32,                            // trigger if final_damage >= threshold
    pub apply_status: StatusFlag,                         // PL_006 status to apply
    pub magnitude: u8,                                    // PL_006 magnitude
}
```

### §9.3 Cascade pseudocode (V1)

```pseudo
on Strike action(attacker, defender, instrument):
  // Q4 REVISED: if defender is Tracked NPC, observation triggers materialization first
  materialize_actor_progression(defender, current_fiction_ts);
  
  let formula = reality.strike_formula.unwrap_or(default_strike_formula());
  
  let attacker_offense = formula.offense_terms.iter()
    .filter(|term| term.instrument_match.is_none() || matches(term.instrument_match, instrument))
    .map(|term| attacker.progression[term.kind_id].raw_value as f32 * term.weight)
    .sum();
  
  let defender_defense = formula.defense_terms.iter()
    .map(|term| defender.progression[term.kind_id].raw_value as f32 * term.weight)
    .sum();
  
  let raw_potential = (attacker_offense - defender_defense).max(0.0);
  let min_dmg = max(formula.damage_floor, (raw_potential * formula.min_damage_factor) as u32);
  let max_dmg = (raw_potential * formula.max_damage_factor) as u32;
  
  // Q7e: silent clamp (preserves narrative flow; no reject)
  let final_damage = llm_proposed_damage.clamp(min_dmg, max_dmg);
  
  // Apply VitalDelta to defender's vital_pool.HP (RES_001)
  emit VitalDelta { actor_ref: defender, kind: VitalKind::Hp, delta: -final_damage };
  
  // Q7f post-damage hooks (status application via PL_006)
  for hook in formula.post_damage_hooks where final_damage >= hook.damage_threshold:
    emit ApplyStatus { actor_ref: defender, flag: hook.apply_status, magnitude: hook.magnitude };
  
  // Q3 attacker training cascade (existing PL_005 hot-path):
  for rule in attacker.kinds.training_rules where rule matches Strike action:
    apply training amount to attacker
```

### §9.4 Default formula (no author declaration)

```rust
fn default_strike_formula() -> StrikeFormulaDecl {
    StrikeFormulaDecl {
        offense_terms: vec![],                            // no stat reading
        defense_terms: vec![],                            // no stat reading
        min_damage_factor: 0.0,
        max_damage_factor: 0.0,
        damage_floor: 1,                                  // at least 1 damage
        post_damage_hooks: vec![],
    }
}
// Engine adds outer cap when no formula stat reads:
//   min_dmg=1; max_dmg=defender.vital_pool[Hp].current_value / 2
//   (prevent insta-kill while preserving narrative flow)
```

→ Realities without progression schema OR without strike_formula still playable PvE-light. LLM proposes within safe bounds.

### §9.5 Worked examples (3 genres)

**Modern fistfight** — see §11 RealityManifest example.

**Tu tiên qi-blast** (筑基 cultivator qi=400) vs (练气 opponent body=80):
```
attacker_offense = 400*1.5 + (instrument="spirit_sword" → +spirit_blade*1.0) = 600 (+ instrument bonus)
defender_defense = 80*1.2 = 96
raw_potential = 504
bounds = [252, 605]
LLM proposes 350 → clamped to [252, 605] → 350 ✓
350 > 100 threshold → Wounded magnitude 5 applied
```

**D&D sword swing** — author declares STR + swordsmanship offense; armor_value defense; wider damage_factor variance for "dice roll" feel.

---

## §10 — Body/Soul + Xuyên Không Integration (Q1 NEW)

### §10.1 BodyOrSoul rule application

Per RES_001 §5.3 + PCS_001 brief §S8 — xuyên không (soul transmigration into another body) preserves body-bound progressions on the body (passed to new soul) and soul-bound progressions on the soul (passed to new body).

PROG_001 §10 adds the rule for progression specifically:

```pseudo
on PcXuyenKhongCompleted event (PCS_001 mechanic):
  let old_body_actor_id = event.body_actor_id;
  let new_pc_id = event.new_pc_id;
  let soul_origin_actor = event.soul_origin_actor_id;  // may be from different reality
  
  // For each progression kind in new_pc's reality:
  for instance in old_body_actor_progression.values:
    let kind = reality.progression_kinds[instance.kind_id];
    match kind.body_or_soul:
      BodyOrSoul::Body => {
        // Body progression follows body — new PC inherits this skill/cultivation
        new_pc_progression.values.push(instance);  // copy as-is
      },
      BodyOrSoul::Soul => {
        // Soul progression follows soul — old body's value is "lost" to new PC
        // Soul's own value (from origin reality) carries over (handled by PCS_001 §S8)
        // Skip body's soul-progression — don't transfer
      },
      BodyOrSoul::Both => {
        // Hybrid — author choice; V1 conservative: body's value carries over (same as Body)
        new_pc_progression.values.push(instance);
      },
  
  // Soul-bound progressions from soul_origin_actor's reality:
  // (Cross-reality transfer requires R5-compliant pattern; out of PROG_001 V1 scope —
  //  PCS_001 §S8 handles soul state extraction; PROG_001 just declares rule for body-side)
```

V1 simplification: soul-bound cross-reality transfer is PCS_001 / future AI Tier responsibility. PROG_001 V1 only declares the BodyOrSoul rule.

### §10.2 Worked example

PC Lý Minh (origin=2026 Saigon scholar, INT=18, qi_cultivation=N/A) xuyên không into Trần Phong's body (1256 Hàng Châu peasant, STR=15, swordsmanship=5).

After xuyên không:
- Lý Minh's NEW progression:
  - **Body inherited from Trần Phong**: STR=15 (Body kind), swordsmanship=5 (Body kind)
  - **Soul brought from Lý Minh**: INT=18 (Soul kind)
  - qi_cultivation: N/A (not in 2026 Saigon reality; cannot transfer)
- Trần Phong's old progression: archived/destroyed (PCS_001 mortality state)

LLM narrates: "Lý Minh waking in Trần Phong's body finds his hand instinctively gripping the sword (body's swordsmanship intact), but his mind retains modern scholarly knowledge."

---

## §11 — RealityManifest Extensions

### §11.1 Fields added by PROG_001

Registered in `_boundaries/02_extension_contracts.md` §2:

```rust
RealityManifest {
    // ... existing fields per Continuum / NPC_001 / WA_001 / WA_002 / WA_006 / PF_001 / MAP_001 / CSC_001 / RES_001 / NPC_003 / IDF_001..005 / FF_001 ...
    
    // ─── PROG_001 extensions (added 2026-04-26 DRAFT) ───
    
    /// Author-declared progression kinds (Q1+Q2+Q3+Q7).
    /// Empty default = NO progression in reality (sandbox/freeplay realities valid V1).
    /// (Different from RES_001 which ships engine defaults — PROG schema inherently genre-specific;
    /// modern game ≠ tu tiên ≠ D&D — no universal default.)
    pub progression_kinds: Vec<ProgressionKindDecl>,
    
    /// Per-actor-class default initial values (overrides ProgressionKindDecl.initial_value per class).
    /// E.g., "warrior" actor-class STR=15 default; "scholar" INT=15 default.
    pub progression_class_defaults: HashMap<ActorClassRef, Vec<ClassDefaultDecl>>,
    
    /// Per-actor override (rare V1; common in V1+ for protagonist NPCs).
    pub progression_actor_overrides: HashMap<ActorRef, Vec<ActorOverrideDecl>>,
    
    /// Strike damage formula. None V1 = default formula (LLM proposes 1..=defender_hp/2; no stat reading).
    pub strike_formula: Option<StrikeFormulaDecl>,
}

pub struct ClassDefaultDecl {
    pub kind_id: ProgressionKindId,
    pub initial_value: u64,
    pub initial_tier: Option<TierIndex>,
}

pub struct ActorOverrideDecl {
    pub kind_id: ProgressionKindId,
    pub override_value: u64,
    pub override_tier: Option<TierIndex>,
}
```

### §11.2 Default values (engine fallback)

If author provides empty arrays:
- `progression_kinds: []` → reality has NO progression. LLM falls back to NPC_001 flexible_state for character description.
- `strike_formula: None` → default formula (LLM proposes 1..=defender_hp/2; no stat reading).

### §11.3 Per-reality opt-in (composability)

Authors can omit PROG fields entirely (sandbox/freeplay realities); progression is opt-in per reality. Per `_boundaries/02_extension_contracts.md` §2 rule 4 — composability.

---

## §12 — Generator Bindings + Coordinator Sequencing

### §12.1 V1 Generators

PROG_001 owns 1 V1 Generator:

| Sub-type | Trigger | Description |
|---|---|---|
| `Scheduled:CultivationTick` | EVT-G2 `FictionTimeMarker` (day-boundary) | PCs only V1: apply Time-source training rules + auto-breakthrough check; emit ProgressionDelta events |

All registered as `EVT-T5 Generated` sub-type per 07_event_model EVT-A11 sub-type ownership.

### §12.2 Coordinator sequencing per EVT-G6

Day-boundary trigger fires the following Generators in order:

1. `Scheduled:CellProduction` (RES_001) — fill cell stockpiles
2. `Scheduled:NPCAutoCollect` (RES_001) — drain to NPC owners
3. `Scheduled:CellMaintenance` (RES_001) — deduct from owners
4. `Scheduled:HungerTick` (RES_001) — food consumption + Hungry magnitude
5. **`Scheduled:CultivationTick` (PROG_001) — last** — reads end-of-day state (post-status-applied; PCs eager only per Q4 REVISED; Tracked NPCs lazy-skip)

CultivationTick last vì:
- Actor có thể đói (Hungry magnitude ≥ 4) → TrainingCondition::StatusForbidden(Hungry-severe) blocks cultivation V1+ (V1 does not gate on Hungry magnitude — but pattern enables)
- Status chain consistent: cultivation reads STATE-AT-END-OF-DAY

### §12.3 Determinism (per EVT-A9 RNG)

Each Generator must be deterministic for replay. RNG seeds:
- `Scheduled:CultivationTick`: `blake3(reality_id || day_marker || "cultivation")` — deterministic for replay

V1 Generator uses no RNG (pure deterministic accrual). Seed reserved for V1+30d when probabilistic mechanisms (Random TrainingAmount PROG-D9) added.

### §12.4 Cycle detection (per EVT-G3)

PROG_001 Generator does NOT trigger other Generators in same fiction-day. Emits T3/T5 events; T3/T5 events do NOT cascade to T6/T1 within same day. Cycle-free V1.

### §12.5 NEW EVT-T3 sub-shapes

PROG_001 owns 2 NEW EVT-T3 Derived sub-shapes:

```rust
// Per-event progression delta
pub struct ProgressionDelta {
    pub actor_ref: ActorRef,
    pub kind_id: ProgressionKindId,
    pub delta_kind: ProgressionDeltaKind,
    pub source_event_id: u64,                             // causal-ref per EVT-A6
}

pub enum ProgressionDeltaKind {
    RawValueIncrement { amount: u32 },                    // V1 — training accrual
    TierAdvance { from: TierIndex, to: TierIndex },       // V1 — breakthrough event
    TierRegress { from: TierIndex, to: TierIndex },       // V1+30d — 走火入魔 deviation (PROG-D2)
    DirectSet { new_value: u64 },                         // V1 — author Forge override
}

// Lazy-materialization batch wrapper (Q4 REVISED)
pub struct ActorProgressionMaterialized {
    pub actor_ref: ActorRef,
    pub materialized_at_fiction_ts: i64,
    pub deltas: Vec<ProgressionDelta>,                    // batch of accruals during elapsed period
}
```

### §12.6 NEW cascade-trigger sub-shape

```rust
pub struct BreakthroughAdvance {
    pub actor_ref: ActorRef,
    pub kind_id: ProgressionKindId,
    pub from_tier: TierIndex,
    pub to_tier: TierIndex,
    pub triggered_at_fiction_ts: i64,
}
```

Cascade-trigger pattern (mirrors PF_001 PlaceDestroyed): downstream consumers subscribe explicitly. V1 consumers:
- NPC_001 Cast — opinion drift on breakthrough (V1+ optional)
- NPC_002 Chorus — priority adjustment (V1+ optional)
- (V2 quest engine — gate quest objectives on breakthrough)

V1 emits BreakthroughAdvance; consumers may opt-in V1+.

---

## §13 — Validator Chain

### §13.1 PROG_001 validator slots

Slot ordering relative to existing validators (registered in `_boundaries/03_validator_pipeline_slots.md`):

| Slot | Validator | Owner | Order |
|---|---|---|---|
| ... | (existing PL_001 / PL_005 / PL_006 / WA_006 / EF_001 / PF_001 / RES_001 validators) | | |
| `PROG-V1` | `ProgressionDeltaValidator` | PROG_001 | After PL_005 OutputDecl validation, after RES_001 RES-V1 |
| `PROG-V2` | `BreakthroughConditionCheck` | PROG_001 | At training-tick + Forge:TriggerBreakthrough events |
| `PROG-V3` | `StrikeFormulaBoundsCheck` | PROG_001 | After PL_005 Strike kind payload parse, before VitalDelta emit |
| `PROG-V4` | `ProgressionSchemaValidator` | PROG_001 | At RealityManifest bootstrap (CapRule × CurveDecl validity matrix Q2j) |

### §13.2 Validator behaviors

**PROG-V1 ProgressionDeltaValidator**: For each ProgressionDelta event:
- Verify kind_id exists in reality.progression_kinds
- Verify delta_kind variant valid for kind's CurveDecl (TierAdvance only valid for Stage type)
- Verify amount within reasonable bounds (raw_value + amount ≤ kind.cap_rule cap if HardCap)
- Reject: `progression.training.kind_unknown` / `progression.cap.exceeded`

**PROG-V2 BreakthroughConditionCheck**: At training-tick OR Forge:TriggerBreakthrough:
- Check raw_value at tier_max
- Check breakthrough_condition (item_consumption / location_required / mentor V1+ / time_window V1+)
- If all satisfied → advance tier + reset raw_value + emit ProgressionDelta::TierAdvance + emit BreakthroughAdvance cascade
- If failed (Forge-triggered) → reject `progression.breakthrough.condition_unmet`

**PROG-V3 StrikeFormulaBoundsCheck**: At PL_005 Strike kind cascade:
- Read formula from RealityManifest (or default)
- Compute bounds [min_dmg, max_dmg]
- Clamp llm_proposed_damage silently (Q7e — no reject V1)
- Emit VitalDelta with clamped value

**PROG-V4 ProgressionSchemaValidator**: At RealityManifest bootstrap:
- Validate Q2j CapRule × CurveDecl matrix (Stage requires TierBased; Linear/Log can't use TierBased)
- Validate derives_from references valid kind_id (and source kind is Attribute type)
- Validate StatTerm in StrikeFormulaDecl references valid kind_id
- Reject: `progression.training.rule_invalid` / `progression.combat.formula_invalid` / `progression.combat.stat_term_unknown`

---

## §14 — Cascade Integration with Other Features

### §14.1 EF_001 Entity Foundation

PROG_001 references `EntityRef` (Actor variant V1; Item variant V1+30d reserved). EF_001 cascade rules apply:
- Actor destroyed (death) → ActorProgression aggregate becomes orphan (V1: archived; V1+ merges with V1+ "death loot" or "soul transfer" mechanics)
- Item destroyed (V1+30d Item kind) → Item-bound progression cascades

### §14.2 RES_001 Resource Foundation

PROG_001 reads RES_001 Vital values for combat formula (defender HP for max_dmg cap when no formula). PROG_001 emits VitalDelta to RES_001 vital_pool (HP decrement from combat damage). Boundary: PROG_001 doesn't OWN vital_pool; consumes via VitalDelta event.

PROG_001 reads RES_001 Consumable kind for `BreakthroughCondition::AtMaxPlus.item_consumption` (foundation pill consumption at breakthrough). RES_001 auto-handles consumption via PL_005 Use semantics (existing path).

**Alignment concern (PROG-D19)**: RES_001 NPC owner auto-collect Generator inconsistent với quantum-observation; V1+30d closure pass migrates RES_001 NPC economy to lazy materialization.

### §14.3 PCS_001 PC Substrate (parallel agent commission)

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md):
- §4.4 reading list: ADD PROG_001 mandatory reading
- §S5 stats stub: SUPERSEDED by PROG_001 progression_kinds (PCS_001 brief update at PROG_001 CANDIDATE-LOCK)
- §S8 xuyên không body-substitution mechanic: applies BodyOrSoul rule (PROG_001 §10) for progression-side semantics

When PCS_001 lands DRAFT:
- PCS declares per-PC initial progression values (matching reality.progression_kinds schema)
- PCS xuyên không event triggers PROG_001 §10 body-soul progression transfer

### §14.4 NPC_001 Cast

NPC_001 closure pass folds in:
- §6 persona assembly: read ProgressionInstance values (with materialization-on-observation per Q4 REVISED) for `[ACTOR_CONTEXT]` block — LLM aware of NPC swordsmanship/cultivation tier for dialogue + reactions
- §X NPC progression behavior: Tracked NPCs lazy on observation (per Q4 REVISED §7)
- VitalProfile reference: NPC_001 declares per-NPC-class defaults (separate from PROG_001 progression schema)

### §14.5 NPC_003 Desires (LIGHT)

Independent — desires are narrative, not numeric progression. No PROG_001 reference required.

### §14.6 IDF_001..005 Identity Foundation (Tier 5 Actor Substrate)

IDF folder closed 2026-04-26 with 5 features (Race / Language / Personality / Origin / Ideology). PROG_001 may reference IDF aggregates as `derives_from` source (V1+30d):
- Race traits (race_assignment) may modulate progression rate (V1+30d Subsystem stacking PROG-D6)
- Language proficiency (actor_language_proficiency) IS progression-like (per IDF_002 design); coordinate at V1+30d closure
- Personality archetype (actor_personality) may modulate training rate (V1+30d)
- Origin pack (actor_origin) may declare initial progression values (V1+30d via progression_class_defaults extension)
- Ideology stance (actor_ideology_stance) may modulate breakthrough conditions (V2)

V1 PROG_001 doesn't actively consume IDF aggregates — independence allows both to ship V1.

### §14.7 FF_001 Family Foundation

FF_001 family_node lineage tracking is independent of progression. V2+: family inheritance mechanics (PROG-D32 reserved — bloodline progression bonuses) bridge FF_001 + PROG_001.

### §14.8 PL_005 Interaction

PL_005 cascade post-validation reads training_rules indexed by InteractionKind (Q3i hot-path). PL_005 closure pass adds reference to PROG_001 cascade behavior.

PL_005 Strike kind cascade emits VitalDelta + ApplyStatus per PROG_001 §9.3 (Q7).

### §14.9 PL_006 Status Effects

PROG_001 references StatusFlag enum (read-only) in:
- TrainingCondition::StatusRequired/StatusForbidden (Q3e)
- PostDamageHook.apply_status (Q7f)

PROG_001 emits ApplyStatus events to PL_006 actor_status (existing path; no PL_006 modification).

### §14.10 WA_006 Mortality

PROG_001 indirectly contributes to mortality via Q7 combat damage cascade:
- Strike → VitalDelta → Hp=0 → MortalityTransitionTrigger emit (RES_001 path) → WA_006 consumes
- PROG_001 doesn't directly emit MortalityTrigger; just supplies damage formula

### §14.11 WA_001 Lex

Lex declares which progression systems are valid per reality. Lex schema validation at RealityManifest bootstrap:
- "no qi-cultivation in modern reality" → reject ProgressionKindDecl with `progression.training.kind_unknown` if Lex rejects qi_cultivation
- Per-reality progression_kinds Vec must pass Lex validation

PROG_001 runs validator AFTER Lex schema validation.

### §14.12 WA_003 Forge

PROG_001 introduces 2 NEW AdminAction sub-shapes (per WA_003 ForgeEditAction enum extension; locked at WA_003 closure pass downstream):

```rust
pub enum ForgeEditAction {
    // ... existing variants ...
    
    /// Author override progression value (DirectSet variant). NEW 2026-04-26 PROG_001 DRAFT.
    GrantProgression {
        actor_ref: ActorRef,
        kind_id: ProgressionKindId,
        new_value: u64,
        new_tier: Option<TierIndex>,                      // for Stage type
    },
    
    /// Author trigger breakthrough (skip auto-check). NEW 2026-04-26 PROG_001 DRAFT.
    TriggerBreakthrough {
        actor_ref: ActorRef,
        kind_id: ProgressionKindId,
    },
}
```

WA_003 closure pass folds these in. Audit trail via `forge_audit_log` (WA_003-owned).

### §14.13 07_event_model

07_event_model registers PROG_001 sub-types per EVT-A11:

EVT-T3 Derived:
- `aggregate_type=actor_progression` — accrual / breakthrough / direct-set deltas
- NEW sub-shape: `ActorProgressionMaterialized` (lazy-materialization batch wrapper)
- NEW cascade-trigger sub-shape: `BreakthroughAdvance`

EVT-T5 Generated:
- `Scheduled:CultivationTick` (day-boundary trigger via EVT-G2)

EVT-T8 Administrative:
- `Forge:GrantProgression` sub-shape
- `Forge:TriggerBreakthrough` sub-shape

EVT-G6 Coordinator: PROG_001 CultivationTick sequenced 5th in day-boundary chain.

### §14.14 Future AI Tier feature (`16_ai_tier/`)

PROG_001 reserves `tracking_tier: Option<NpcTrackingTier>` field; AI Tier feature owns enum + tier promotion logic + Untracked NPC procedural generation. Boundary: PROG_001 ships HOOKS; AI Tier feature ships SEMANTICS.

### §14.15 Future CULT_001 Cultivation Foundation (V1+ priority per IDF roadmap)

Boundary clarity for CULT_001 (mentioned as V1+ priority in IDF folder closure changelog):
- **PROG_001 owns cultivation SUBSTRATE** — Stage type with breakthrough mechanic, training rules, RealityManifest declarations cover tu tiên cultivation generically
- **CULT_001 V1+ may add** wuxia-specific extensions: cultivation method registry (luyện khí method 1 vs method 2), 灵根 talent typing, dual-cultivation mechanics, sect-specific cultivation paths
- CULT_001 is a SUB-FEATURE of PROG_001 (V1+ extension); not a competing foundation

V1 PROG_001 ships sufficient for tu tiên realities WITHOUT CULT_001. CULT_001 V1+ enriches without redesigning.

---

## §15 — RejectReason rule_id Catalog

### §15.1 `progression.*` namespace V1 (registered in `_boundaries/02_extension_contracts.md` §1.4)

V1 rule_ids (7 total):

| rule_id | Trigger | Vietnamese display (i18n bundle) |
|---|---|---|
| `progression.training.kind_unknown` | invalid kind_id reference in TrainingRuleDecl or ProgressionDelta | "Loại tiến trình không xác định" |
| `progression.training.rule_invalid` | malformed TrainingRuleDecl at RealityManifest bootstrap (e.g., empty rule_id; invalid CapRule × CurveDecl) | "Quy tắc luyện không hợp lệ" |
| `progression.breakthrough.condition_unmet` | Forge-triggered breakthrough failed condition check | "Đột phá không đủ điều kiện" |
| `progression.breakthrough.invalid_tier` | invalid tier_index for actor's current state | "Tầng cảnh giới không hợp lệ" |
| `progression.cap.exceeded` | value would exceed HardCap (Linear/Log curves) | "Đã đạt giới hạn" |
| `progression.combat.formula_invalid` | RealityManifest bootstrap rejects malformed StrikeFormulaDecl | "Công thức chiến đấu không hợp lệ" |
| `progression.combat.stat_term_unknown` | StrikeFormulaDecl references non-existent kind_id | "Thuộc tính tham chiếu không xác định" |

### §15.2 V1+ reservations

- `progression.atrophy.no_practice` — V1+30d (PROG-D5)
- `progression.deviation.cultivation_failed` — V1+30d (PROG-D2 走火入魔)
- `progression.training.prereq_unmet` — V1+30d (Q3j action-rejection mode)
- `progression.combat.proposed_out_of_range` — V1+30d (Q7e reject mode)
- `progression.combat.element_resistance_invalid` — V1+ (DF7 PROG-D24)
- `progression.combat.critical_threshold_invalid` — V1+ (PROG-D25 critical hit)

### §15.3 RejectReason envelope conformance

PROG_001 conforms to RES_001 §2.3 i18n contract — `RejectReason.user_message: I18nBundle` carries multi-language text. Existing Vietnamese reject copy migrates to I18nBundle as part of cross-cutting i18n audit (deferred LOW priority per RES_001 §17.4).

---

## §16 — Acceptance Criteria

12 V1-testable scenarios. Each must pass deterministically per EVT-A9 replay.

### AC-PROG-1 — Author declares progression schema; RealityManifest validates
- Setup: RealityManifest with progression_kinds containing 1 Attribute (STR Linear SoftCap), 1 Skill (Negotiation Log SoftCap with derives_from INT), 1 Stage (qi_cultivation 24-tier)
- Action: bootstrap reality
- Expected: PROG-V4 schema validator passes; CapRule × CurveDecl matrix (Q2j) all valid; ActorProgression aggregates created for all canonical_actors

### AC-PROG-2 — PC daily Generator training accrual
- Setup: PC Lý Minh has qi_cultivation kind with Time training rule (LocationMatch=cultivation_chamber, amount=1); Lý Minh in cultivation_chamber
- Action: travel command 5 fiction-days
- Expected: 5× CultivationTick Generator fires; emits 5× ProgressionDelta::RawValueIncrement events; raw_value increments to 5

### AC-PROG-3 — Stage breakthrough auto-advance at tier_max
- Setup: PC Lý Minh qi_cultivation tier 0 (练气一层) raw_value=99 (tier_max=100); Lý Minh in cultivation_chamber
- Action: travel command 1 fiction-day (Generator fires)
- Expected: training amount=1 → raw_value=100; auto-breakthrough check passes (BreakthroughCondition::AtMax for tier 0); current_tier advances to 1; raw_value reset to 0; emit ProgressionDelta::TierAdvance + BreakthroughAdvance cascade-trigger event

### AC-PROG-4 — Stage breakthrough requires item + location (筑基)
- Setup: PC qi_cultivation tier 8 (练气九层) raw_value=900 (tier_max); BreakthroughCondition::AtMaxPlus { item: foundation_pill 1, location: cultivation_chamber }; PC has foundation_pill in inventory; PC in cultivation_chamber
- Action: PC executes `/use foundation_pill` (V1 use kind triggers breakthrough check)
- Expected: PROG-V2 validator checks all conditions met; advance to tier 9 (筑基); foundation_pill consumed; emit TierAdvance + BreakthroughAdvance

### AC-PROG-5 — Action training cascade with derives_from
- Setup: PC has Negotiation Skill with derives_from INT (factor=0.05); INT=20; PC speaks to NPC Lão Vương
- Action: PL_005 Speak action targets NPC
- Expected: PL_005 cascade post-validation finds Negotiation training rule; multiplier = 1.0 + 20*0.05 = 2.0; effective amount = 1 * 2.0 = 2; raw_value increments by 2

### AC-PROG-6 — TrainingCondition StatusForbidden blocks training
- Setup: PC has Drunk status; PC speaks to NPC; Negotiation training rule has StatusForbidden(Drunk)
- Action: PL_005 Speak action
- Expected: training rule conditions don't all match (Drunk forbidden); silent skip (Q3j); no ProgressionDelta emitted; no reject

### AC-PROG-7 — Tracked NPC lazy materialization on observation
- Setup: NPC Lý Lão has qi_cultivation tier 9 raw_value=400 last_observed_at=day-100; NPC has Time training rule (LocationMatch=cultivation_chamber); NPC's last-known location is cultivation_chamber
- Action: PC enters cell with Lý Lão at day-130 (30 days elapsed)
- Expected: materialize_actor_progression triggers; replay 30 days of cultivation; raw_value increments to 430 (within tier_max=500); emit ActorProgressionMaterialized event with 30 batched deltas; last_observed_at updates to day-130

### AC-PROG-8 — Untracked NPC = no aggregate (silent skip)
- Setup: Random villager NPC has NO ActorProgression aggregate (untracked); future AI Tier feature would generate persona on-demand
- Action: PC speaks to villager; PL_005 Speak cascade fires
- Expected: PROG_001 cascade silently skips villager (no aggregate found); no ProgressionDelta event for villager; no reject; PL_005 turn proceeds normally

### AC-PROG-9 — Combat damage formula clamps LLM proposal
- Setup: PC Lý Minh STR=15, swordsmanship=10, sword equipped; bandit CON=12, dodge=5; reality strike_formula: offense=STR*1.0+swordsmanship*0.5; defense=CON*0.8+dodge*0.3; min_factor=0.3; max_factor=0.7; damage_floor=1
- Action: PC strikes bandit with sword; LLM proposes damage_amount=12
- Expected: offense=20; defense=11.1; raw_potential=8.9; min_dmg=3; max_dmg=6; LLM proposal 12 clamped silently to 6; VitalDelta -6 applied to bandit Hp; if PostDamageHook for damage_threshold=20 → no Wounded (6<20)

### AC-PROG-10 — PostDamageHook applies status
- Setup: Same as AC-PROG-9; reality strike_formula has PostDamageHook { threshold=20, apply: Wounded, magnitude: 2 }; PC's offense yields max_dmg=25; LLM proposes 22
- Action: Strike action
- Expected: final_damage=22; threshold=20 met; emit ApplyStatus(Wounded, mag=2) on bandit

### AC-PROG-11 — Default formula (no author declaration)
- Setup: Reality without strike_formula declared; bandit Hp=50
- Action: PC strikes bandit; LLM proposes damage_amount=999
- Expected: default formula applies; engine outer cap = bandit_hp/2 = 25; LLM proposal 999 clamped silently to 25; VitalDelta -25 applied

### AC-PROG-12 — Forge:GrantProgression author override
- Setup: Author wants to grant PC qi_cultivation tier 5 (skipping training)
- Action: Author invokes `Forge:GrantProgression { actor_ref: pc_ly_minh, kind_id: qi_cultivation, new_value: 0, new_tier: Some(5) }`
- Expected: forge_audit_log records edit; PC's ProgressionInstance updated to tier=5, raw_value=0; emit ProgressionDelta::DirectSet event; subsequent AssemblePrompt shows new tier

---

## §17 — V1 Minimum Delivery Summary

PROG_001 V1 ships:

| Component | Count |
|---|---|
| New aggregate | 1 (`actor_progression`) |
| ProgressionType variants | 3 V1 (Attribute / Skill / Stage); 1 V1+30d reserved |
| BodyOrSoul variants | 3 (Body / Soul / Both) |
| CurveDecl variants | 3 V1 (Linear / Log / Stage); DiscreteLevelup V1+30d |
| CapRule variants | 4 V1 (SoftCap / HardCap / TierBased / Unbounded) |
| TrainingSource variants | 2 V1 (Action / Time); Mentor V1+30d / Quest V2 |
| TrainingAmount variants | 1 V1 (Fixed); Variable / Random V1+30d |
| TrainingCondition variants | 3 V1 (LocationMatch / StatusRequired / StatusForbidden); 3 V1+30d reserved |
| BreakthroughCondition variants | 3 V1 (AtMax / AtMaxPlus / AuthorOnly) |
| RealityManifest extensions | 4 OPTIONAL fields |
| Generators | 1 (`Scheduled:CultivationTick`) |
| EVT-T3 sub-shapes | 2 + 1 cascade-trigger (ProgressionDelta + ActorProgressionMaterialized + BreakthroughAdvance) |
| AdminAction sub-shapes | 2 (Forge:GrantProgression + Forge:TriggerBreakthrough) |
| Validator slots | 4 (PROG-V1..V4) |
| Rule_ids `progression.*` | 7 V1 + 6 V1+ reservations |
| Acceptance scenarios | 12 (AC-PROG-1..12) |
| Deferrals catalog | 30+ (PROG-D1..D30 + alignment concerns) |

Author can express V1:
- ✅ **Modern social** — STR/INT attributes + negotiation/business/oratory/piano skills
- ✅ **Tu tiên** — qi_cultivation Stage 24-tier + 灵丹 elixirs + cultivation chamber + body/qi cultivation systems
- ✅ **Traditional D&D** — STR/INT/AGI attributes + class-based skills + level-up via Forge:GrantProgression (V1 manual; V1+30d add discrete-levelup)
- ✅ **Survival** — body cultivation via action-driven training (Use sword → swordsmanship; Speak → negotiation)
- ✅ **Sandbox/freeplay** — empty progression_kinds; reality has NO progression; NPC_001 flexible_state drives narrative

---

## §18 — Deferrals Catalog (PROG-D1..D37)

Already enumerated in CONCEPT_NOTES §11.2 / §11.4 / §11.8 / §11.11. PROG-D33..D37 added 2026-04-27 closure-pass-extension via CULT_001 stress-test pre-audit. Summary:

**V1+30d (RES-D-equivalent fast-follow):**
- PROG-D1 DiscreteLevelup curve
- PROG-D2 Failed breakthrough narrative (走火入魔)
- PROG-D3 mentor_required active
- PROG-D4 fiction_time_window active
- PROG-D5 Skill atrophy (lazy at materialization)
- PROG-D8 TrainingSource::Mentor multiplier
- PROG-D9 TrainingAmount Variable / Random
- PROG-D10 TrainingCondition::ActorClassMatch
- PROG-D11 TrainingCondition::FictionTimeWindow
- PROG-D12 TrainingCondition::RelationshipRequired
- PROG-D13 TickPeriod::HourlyBoundary / Custom
- PROG-D15 InstrumentMatch::InstrumentClass
- PROG-D19 RES_001 NPC eager → lazy migration alignment
- PROG-D23 Closed-form materialization optimization
- PROG-D28 Per-instrument formula override
- PROG-D29 Forge:EditStrikeFormula AdminAction
- **PROG-D33** Cross-actor `TrainingSource::CrossActor` (dual cult / demonic absorb / master-pet bond / family-bond) — *added 2026-04-27 CULT_001 stress-test*
- **PROG-D34** `ProgressionDeltaKind::RawValueDecrement` active (drain/leech / lifespan-burn) — *added 2026-04-27 CULT_001 stress-test*
- **PROG-D36** `BreakthroughCondition::KarmaThreshold` (heart demon / 心魔 gating) — *added 2026-04-27 CULT_001 stress-test*

**V2 (Economy/Strategy module-tier):**
- PROG-D6 Subsystem stacking (chaos-backend Contribution pattern)
- PROG-D14 TrainingSource::Quest (QST_001 dependency)
- PROG-D20 Intermediate-state materialization interpolation
- PROG-D21 NPC-to-NPC cascade during un-observed
- PROG-D24 DF7-equivalent full damage law chain
- PROG-D25 Critical hits
- PROG-D26 AoE multi-target Strike
- PROG-D27 Damage type variety
- PROG-D30 Element-stat multiplicative chain
- **PROG-D35** `derives_from` cross-feature source (FF_001 / FAC_001 / REL_001 state → rate multiplier) — *added 2026-04-27 CULT_001 stress-test*
- **PROG-D37** `RebirthBonusDecl` RealityManifest extension (cumulative per-death bonus) — *added 2026-04-27 CULT_001 stress-test*

**V3 (Strategy module / Future AI Tier feature):**
- PROG-D7 Realm-stage nested hierarchy
- PROG-D22 Untracked → Tracked tier promotion (future AI Tier)
- PROG-D31 ResourceBound ProgressionType (mana-pool)
- PROG-D32 Bloodline progression bonuses (FF_001 + PROG_001 V2+ bridge)

### §18.1 PROG-D33..D37 cross-cultivation extensibility audit (2026-04-27 closure-pass-extension)

Discovered via CULT_001 stress-test pre-audit against 11 exotic cultivation systems from xianxia/xuanhuan/wuxia genre (dual-cultivation, demonic absorption, family/clan cultivation, rebirth cultivation, lifespan-burn, heart-demon karma, alchemy/talisman/array, pet-beast bond, sword-spirit, body-refining parallel-axis, neigong-waigong wuxia). **Verdict**: PROG_001 design is future-proof — 5 of 11 NATIVELY supported V1; 6 require V1+ schema-additive extensions (D33-D37 + existing D2/D10/D12/D24/etc.). NO PROG_001 redesign required; all gaps additive per I14 invariant.

| Gap | Affected systems (cultivation novels reference) | Deferral ID |
|---|---|---|
| Cross-actor delta (one action's effect on 2 actors) | Dual cultivation (Mị ma song tu) / Demonic absorption (Mo Dao Zu Shi 魔修) / Master-pet bond (Đấu Phá Pokemon-like) / Family-bond cultivation (đa phúc đa tử) | PROG-D33 |
| Negative delta / drain semantic (victim loses progression) | Cauldron mechanics (human cauldron) / Demonic absorption / Lifespan-burn forbidden technique (Cultivation Too Hard / Lifespan Burning System) | PROG-D34 |
| Cross-feature derives_from (state from FF_001/FAC_001/REL_001 multiplies cultivation rate) | Family-count-multiplies-power (đa phúc đa tử) / Sect-membership-rate-bonus (kiếm hiệp neigong) / Marriage-state cultivation | PROG-D35 |
| KarmaThreshold breakthrough condition | Heart demon (心魔) / Karma cultivation (功德 / 业力) / Buddhist-Devil parallel paths | PROG-D36 |
| Rebirth cumulative bonus (each death = permanent next-life bonus) | Rebirth cultivation (chết trùng sinh mạnh hơn — Rebirth of the God Emperor / Villainous Rebirth / Path of Lazy Immortal) | PROG-D37 |

**3 systems remain NATIVELY supported V1** (no deferral needed):
- Body cultivation parallel-axis (Cầu Ma Wang Lin Ancient Body / Hoàn Mỹ) → multiple ProgressionKindDecls + BodyOrSoul=Body each
- Alchemy/Talisman/Array orthogonal axes → multiple ProgressionKindDecls
- Lifespan-burn (one-actor self-sacrifice) → Action interaction_kind="burn_lifespan" + cross-aggregate hook to actor_core.lifespan_remaining

**1 system already has reservation V1+30d** (PROG-D2 Failed breakthrough narrative 走火入魔 covers tribulation/deviation for demonic cultivation).

**1 system already has reservation V1+30d** (Q6b PROG_001 §3.1 Item ActorRef reserved) → covers sword-spirit / artifact growth (御剑 cultivation).

**1 system covered by FAC_001 + PROG-D10** (Wuxia neigong/waigong sect martial arts) → ActorClassMatch condition deferred.

---

## §19 — Open Questions (Closure Pass Items)

| ID | Question | Resolution path |
|---|---|---|
| PROG-Q1 | Default vital-pool max_value for PC vs NPC progression initial values | PCS_001 + NPC_001 first-design-pass declares per-actor-class; PROG_001 closure pass folds in citation |
| PROG-Q2 | PC progression observation triggers — does PC always count as "observed" or only when player actively plays? | V1 default: PC always observed (eager Generator). V1+30d may add "PC offline N days = lazy mode". |
| PROG-Q3 | Cross-reality progression migration during xuyên không — author declares mapping or auto BodyOrSoul rule? | V1: BodyOrSoul rule auto-applies (PROG_001 §10). V1+30d may add author-declared mapping table per reality pair. |
| PROG-Q4 | i18n cross-cutting audit timing (existing Vietnamese reject copy migration) | Separate cross-cutting commit post PROG_001 LOCK; tracked in coordination notes |
| PROG-Q5 | NPC tracking_tier promotion threshold semantics | Future AI Tier feature owns; PROG_001 ships placeholder |
| PROG-Q6 | Replay determinism for materialization (RNG seed for batch event) | V1 deterministic blake3 from `(reality_id, npc_actor_id, current_fiction_ts, "materialization")` |

---

## §20 — Coordination Notes / Downstream Impacts

### §20.1 Co-locked changes in this commit

Per `_boundaries/_LOCK.md` claim (single combined `[boundaries-lock-claim+release]` commit):

- ✅ `PROG_001_progression_foundation.md` — this DRAFT
- ✅ `_boundaries/01_feature_ownership_matrix.md` — register `actor_progression` aggregate + RealityManifest extension + EVT-T3/T5 sub-types + AdminAction sub-shapes + PROG-* stable-ID prefix
- ✅ `_boundaries/02_extension_contracts.md` §1.4 — `progression.*` rule_id namespace prefix (7 V1 rule_ids)
- ✅ `_boundaries/02_extension_contracts.md` §2 — 4 RealityManifest extension fields
- ✅ `_boundaries/99_changelog.md` — entry
- ✅ `00_progression/_index.md` — DRAFT row
- ✅ `00_progression/00_CONCEPT_NOTES.md` §10 — Status DRAFT promoted
- ✅ `catalog/cat_00_PROG_progression.md` — feature catalog (NEW)

### §20.2 Deferred follow-up commits (downstream features)

These features need updates AFTER PROG_001 LOCK (separate commits, lock-coordinated):

| Feature | Update | Priority | Lock cycle |
|---|---|---|---|
| **WA_003** | Add 2 AdminAction sub-shapes (`Forge:GrantProgression` + `Forge:TriggerBreakthrough`) to ForgeEditAction enum | HIGH | next WA closure |
| **PCS_001 brief** | Update §4.4 reading list (add PROG_001) + §S5 stats stub SUPERSEDED by PROG_001 + §S8 BodyOrSoul rule reference | HIGH | brief update commit |
| **NPC_001** | Closure pass §6 persona assembly extends to read ProgressionInstance values with materialization-on-observation; document Tracked NPC lazy behavior | MEDIUM | NPC_001 closure pass |
| **PL_005** | Add reference §9.1 to PROG_001 cascade behavior; index training_rules by InteractionKind | HIGH | PL_005 closure |
| **PL_006** | Note Hungry magnitude ≥ 4 may forbid cultivation training V1+ (TrainingCondition::StatusForbidden) | LOW | PL_006 closure |
| **WA_006** | Note progression reset on death V1+ (cause_kind affects post-death progression) | LOW | WA_006 closure |
| **07_event_model** | Register 2 EVT-T3 sub-shapes (ProgressionDelta + ActorProgressionMaterialized) + 1 cascade-trigger (BreakthroughAdvance) + 1 EVT-T5 sub-type (Scheduled:CultivationTick) + 2 EVT-T8 sub-shapes (Forge:GrantProgression / Forge:TriggerBreakthrough) | HIGH | event-model agent next pass |
| **DF7 placeholder** | Mark SUPERSEDED in `decisions/deferred_DF01_DF15.md`; DF7-V1+ becomes "Combat Damage Formulas Full" sub-feature | MEDIUM | DF7 retirement commit |
| **RES_001** | NPC eager → lazy migration (PROG-D19 alignment) | V1+30d | RES_001 closure pass V1+30d |

### §20.3 Future feature reservation

**Future AI Tier feature** (`features/16_ai_tier/`):
- 3-tier NPC architecture (PC/Tracked/Untracked)
- NpcTrackingTier enum + tier promotion
- Untracked NPC procedural generation
- Discard policies
- Defer creation until user explicit kickoff post PROG_001 DRAFT

**Future CULT_001 Cultivation Foundation** (V1+ priority per IDF folder closure roadmap):
- Wuxia-specific cultivation method registry
- 灵根 talent typing
- Sect-specific cultivation paths
- V1+ extension; PROG_001 V1 sufficient for tu tiên without CULT_001

### §20.4 ORG-* prefix alignment concern

Note: `15_organization/` was V3 reserved with ORG-* namespace; IDF_004 Origin Foundation also took ORG-* (Tier 5 Actor Substrate). Conflict noted — `15_organization/` may need namespace rename (e.g., FAC-* for Factions per FF_001 closure changelog). Not PROG_001 scope; flagged for cross-feature coordination at next IDF closure pass review.

---

## §21 — Status

- **Created:** 2026-04-26 by main session
- **Phase:** DRAFT 2026-04-26
- **Status target:** CANDIDATE-LOCK after Phase 3 review cleanup + closure pass + 9 §20.2 downstream applied
- **Companion docs:**
  - [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q7 LOCKED matrix §11)
  - [`02_CHAOS_BACKEND_REFERENCE.md`](02_CHAOS_BACKEND_REFERENCE.md) (chaos-backend repo analysis)
- **Lock-coordinated commit:** This commit + 7 sibling boundary file updates under single `[boundaries-lock-claim+release]` prefix
