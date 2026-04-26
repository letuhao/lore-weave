# PROG_001 Progression Foundation — Chaos Backend Reference

> **Status:** RESEARCH 2026-04-26 — companion to [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md). Read-only deep-dive of the user's paused realtime-MMO project at `D:\Works\source\chaos-repositories\chaos-backend-service` (~27 kLOC Rust). Extracts patterns relevant to Q1-Q7 in CONCEPT_NOTES §5 + cross-feature signals for PL_006 / RES_001 / 07_event_model / WA_006 / future DF7.
>
> **Method:** Walked the workspace top-down (Cargo.toml → crates/ → services/ → docs/). Identified which crates are *implemented* (5 of 17) vs. *placeholder stubs* (12 of 17). Read the substantial crates' `types.rs` / `enums.rs` / aggregator implementations + the design docs in `docs/` for the unimplemented crates (combat-core, element-core, status-core, effect-core, condition-core have ~20 markdown design docs each).
>
> **Paradigm caveat:** chaos-backend is **realtime MMO + concrete-per-system** (24 mastery levels HARDCODED in enum, fixed `[f64; 50]` element arrays, "100K+ concurrent players sub-millisecond" target). LoreWeave is **turn-based + author-configurable per-reality + multi-system-per-actor**. Many patterns transfer; many do not. Each section flags both.

---

## §1 — Repo overview

**Workspace:** Rust 2021, single Cargo.toml workspace, 17 crate slots + 14 service slots + extensive `docs/` design corpus.

### Implemented crates (~27 kLOC total Rust)

| Crate | Files | LOC est. | Role |
|---|---|---|---|
| `actor-core` | 128 | ~12k | **The hub.** Stat aggregation engine with `Actor`/`Contribution`/`Snapshot`/`Caps` pipeline, bucket processor (Flat→Mult→PostAdd→Override), plugin/registry/cache/metrics infrastructure. |
| `actor-core-hierarchical` | 23 | ~3k | Performance variant: array-based actor data hub for elemental subsystem. Inherits actor-core via traits, adds `[f64; 50]` arrays for "1-2 ns access". |
| `element-core` | 41 | ~6k | Elemental data + 50-element fixed-array stats + tier/realm/stage enums + aggregator with `Sum/Multiply/Max/Min/Average/First/Last/Custom` strategies + unified registry. |
| `condition-core` | 28 | ~3k | Generic predicate evaluator (function-name + operator + value + parameters). Used by effect-core/status-core/action-core for "should this trigger?" |
| `shared` | 4 | ~250 | Common error type, constants, type aliases. |

### Placeholder crates (Cargo.toml only — no `src/` or 1-file lib stub)

`combat-core`, `leveling-core`, `race-core`, `item-core`, `event-core`, `generator-core`, `job-core`, `world-core` (1-file stub). `effect-core` directory does not even exist as Rust source — design lives only in `docs/effect-core/*.md`. Same for `status-core` source-vs-docs.

### Services (`services/*`, REST/WS façades over the cores)

`api-gateway`, `chaos-backend`, `user-management`, `inventory-service`, `chat-service`, `guild-service`, `world-service`, `matchmaking-service`, `event-service`, `content-management-service`, `notification-service`, `payment-service`, `anti-cheat-service`, `analytics-service`. Most are skeletal too.

### Design docs (`docs/*`, markdown — far more substantive than code in many areas)

- `docs/element-core/` — 30+ markdown files (system architecture, mastery levels, multi-system integration, registry consolidation, performance optimization, advanced derived stats, error handling, hybrid subsystems). **This is the design SSOT for elements.**
- `docs/combat-core/` — 11 numbered files (overview, cultivation integration, damage system, resource manager integration, damage application, flexible action system, modular architecture, world-core binding, shields & protections, resource damage distribution, damage application engine) + `damage-management/` subfolder.
- `docs/condition-core/` — 20+ files including 11 integration designs (with element-core, status-core, actor-core) + debate analysis.
- `docs/effect-core/` — 17 files including Skyrim-Style ID analysis, FormID vs Array performance analysis, hybrid architecture.
- `docs/status-core/` — 17 files including burning-status combat-flow diagram, plugin system, configuration system.
- `docs/leveling-systems/` — **EMPTY directory**. The whole leveling/progression design exists only as `Cargo.toml` description ("Character progression and experience systems for Chaos World MMORPG"). For PROG_001 there is **no concrete formula or curve to copy** from chaos-backend — only adjacent patterns from element-core mastery and actor-core caps.
- `docs/microservices-architecture/`, `docs/system-comparison/`, `docs/integration/`, `docs/wow-latency-comparison.md` — meta/architecture docs.

---

## §2 — Actor stats model (`actor-core` + `actor-core-hierarchical`)

### Two parallel layers

**Layer 1 — `actor-core::types::Actor`** (`crates/actor-core/src/types.rs`):

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Actor {
    pub id: String,
    pub name: String,
    pub race: String,
    pub level: i64,                          // ← single global level
    pub core_resources: [f64; 9],            // ← fixed slot array (HP/MP/SP/...)
    pub custom_resources: HashMap<String, f64>,  // ← extension point
    pub subsystems: Vec<String>,             // ← which Subsystems contribute
    pub data: HashMap<String, serde_json::Value>,
    pub version: i64,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}
```

**Layer 2 — `actor-core-hierarchical::core::HierarchicalActor`** (`crates/actor-core-hierarchical/src/core/hierarchical_actor.rs`):

```rust
pub struct HierarchicalActor {
    pub id: String,
    pub name: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub elemental_system: ElementalSystem,                      // ← from element-core
    pub global_stats_cache: HashMap<String, f64>,               // ← cached final values
    pub system_contributions: HashMap<String, Vec<SystemContribution>>,
    pub metadata: HashMap<String, String>,
}
```

### Aggregation pipeline (the load-bearing pattern)

The actor itself **does not store final stats**. Instead, each registered `Subsystem` emits a `SubsystemOutput` containing `Vec<Contribution>` (additive/multiplicative deltas) + `Vec<CapContribution>` (min/max constraints). The `AggregatorImpl` in `crates/actor-core/src/aggregator/mod.rs` walks all subsystems, groups contributions by `stat_name`, and processes per stat in a deterministic bucket order:

```rust
// crates/actor-core/src/bucket_processor/mod.rs
pub fn process_contributions_in_order(
    contributions: Vec<Contribution>,
    initial_value: f64,
    clamp_caps: Option<&Caps>,
) -> ActorCoreResult<f64> {
    // Bucket order is hardcoded: FLAT → MULT → POST_ADD → OVERRIDE
    let bucket_order = [Bucket::Flat, Bucket::Mult, Bucket::PostAdd, Bucket::Override];
    // ...
}
```

Final output is a `Snapshot { primary, derived, caps_used, version, processing_time, ... }` — immutable per-tick aggregation result, with optional cache lookup.

### Hierarchical pattern tradeoff

The "hierarchical" variant exists for hot-path performance (Vietnamese mastery scenario where the hot stat `element_mastery_levels[i]` is accessed millions of times per second). It abandons HashMap flexibility for fixed `[f64; 50]` arrays — `1-2 ns access` claim in the README. Cost: schema is frozen at compile time (50 elements MAX, 50 derived stats per element each their own array).

For LoreWeave (turn-based, hundreds-of-ms-to-minutes per turn): **the hot-path optimization is irrelevant**. The aggregation pipeline pattern (Layer 1 — `Contribution`/`Bucket`/`Snapshot`) is the load-bearing idea worth copying. The hierarchical fixed-array variant is the wrong direction for our author-configurable schema.

### Tradeoffs summary

| Aspect | actor-core (Layer 1) | hierarchical (Layer 2) |
|---|---|---|
| Stat shape | HashMap<String, f64> dynamic | `[f64; 50]` fixed compile-time |
| Schema flexibility | High (subsystems register stats) | Low (50-element ceiling baked in) |
| Access speed | HashMap lookup ~50ns | Array index 1-2ns |
| Aggregation model | Bucket processor with deterministic ordering | Per-element accumulator on the array |
| Multi-system support | Via `Vec<Subsystem>` registry | Only "elemental" is wired up |
| Cap support | First-class via `Caps`/`CapContribution`/`AcrossLayerPolicy` | None visible — caps live in actor-core layer |

---

## §3 — Leveling/progression model

**Critical finding:** `crates/leveling-core` is empty (Cargo.toml only). `docs/leveling-systems/` is empty. There is NO leveling-system source-of-truth in chaos-backend to mine.

What the chaos-backend *does* have for progression-like mechanics is the **mastery system embedded in `element-core`**, which works as a 24-level + 5-realm + 4-stage breakthrough cultivation system for elemental affinity. From `crates/element-core/src/core/elemental_data.rs`:

```rust
/// Elemental mastery level enum - Extended System with 24 levels
pub enum ElementMasteryLevel {
    // Basic Levels  (0–999, 1k–4.9k, 5k–14.9k, 15k–49.9k)
    Beginner, Novice, Apprentice, Regular,
    // Intermediate  (50k–149.9k, 150k–499.9k, 500k–1.49M, 1.5M–4.99M)
    Adept, Expert, AdvancedExpert, Master,
    // Advanced      (5M–14.9M, 15M–49.9M, 50M–149.9M, 150M–499.9M)
    AdvancedMaster, GrandMaster, Completer, Transcender,
    // Legendary     (500M–1.49B, 1.5B–4.99B, 5B–14.9B, 15B–49.9B)
    Sage, Archmage, Legendary, Mythic,
    // Transcendent  (50B–149.9B, 150B–499.9B, 500B–1.49T, 1.5T–4.99T)
    Transcendent, Celestial, Divine, Immortal,
    // Ultimate      (5T–14.9T, 15T–49.9T, 50T–149.9T, 150T+)
    Eternal, Omniscient, Omnipotent, Supreme,
}
```

Three orthogonal classifications stack on the same XP scalar:

```rust
pub enum MasteryLevelTier {       // 6 tiers — coarse grouping (Basic … Ultimate)
    Basic, Intermediate, Advanced, Legendary, Transcendent, Ultimate,
}

pub enum ElementMasteryRealm {    // 5 realms — XP thresholded (0/1k/3k/6k/10k+)
    ElementalAwareness, ElementalControl, ElementalHarmony,
    ElementalTranscendence, ElementalAscension,
}

pub enum ElementMasteryStage {    // 4 stages within a realm (Early/Mid/Late/Peak)
    Early, Mid, Late, Peak,
}
```

Each gives a multiplier (`get_level_bonus()`, `get_tier_multiplier()`, `get_realm_multiplier()`, `get_stage_multiplier()`). E.g., `Supreme.get_level_bonus()` returns `65.0`, `Ultimate.get_tier_multiplier()` returns `10.0`. These multipliers feed into the derived-stats calculation downstream — a level-up effectively rescales every derived stat for that element.

### What's hardcoded vs configurable

- **Hardcoded:** the 24-level enum names, the XP thresholds, the multiplier values per level/realm/tier/stage, the Vietnamese display names. All baked into `match` statements in `from_experience(exp: i64)`.
- **Configurable:** which derived stats apply per element (declared in YAML elsewhere), which elements an actor has, base properties per element.
- **No training logic:** `from_experience()` is a pure conversion — there is no code path for "action X grants Y XP". XP is just stored on the actor; the increment source is presumed to be elsewhere.

### Curves used (reverse-engineered from thresholds)

XP-to-next-level ratio is approximately **3.0× per level** (1k→4k→15k→50k→150k). Same multiplier across all 24 levels — this is **uniform exponential**, NOT diminishing-returns or stage-breakthrough — but the *labels* simulate a tier-stage cultivation system. The 5-realm enum then groups levels and applies an additional realm multiplier (1× → 2× → 5× → 10× → 25×) creating an effective compound exponential.

### Patterns to extract for PROG_001

1. **Tier/Realm/Stage enum stack** — one XP scalar, multiple orthogonal labels (qualitative bands). Useful for tu tiên (Q2 curve type "tier-stage breakthrough").
2. **Per-band multiplier as derived-stat input** — level→bonus→derived. Useful for "level X provides Y damage multiplier".
3. **24 levels is too many for a hardcoded enum.** For LoreWeave's per-reality dynamic schema, levels/tiers/stages must be data-driven (YAML declared by author), not Rust enums.

---

## §4 — Combat formula model

`crates/combat-core` is empty (Cargo.toml only). The design is in `docs/combat-core/02_Damage_System_Design.md` (180+ lines) + 10 sibling files.

### Damage composition law (canonical order, from doc §⚠️)

```rust
// 1. Base damage from action
let base_damage = calculate_base_damage(action);
// 2. Apply element multiplier (attacker_element vs target_element)
let element_multiplier = get_element_multiplier(attacker_element, target_element);
let element_damage = base_damage * element_multiplier;
// 3. Apply resistance (after penetration)
let resistance = calculate_resistance_after_penetration(target, element_type);
let final_damage = element_damage * (1.0 - resistance);
// 4. Apply DoT/CC after damage calculation
if should_apply_status { apply_status_effects(attacker, target, element_type); }
```

### "Omni additive-only" rule (load-bearing invariant)

The doc *explicitly* warns:

```rust
let total_power = omni_power + element_power;  // ✅ Correct
let total_power = omni_power * element_power;  // ❌ Wrong - causes snowball
```

"Omni" stats are universal-across-all-elements bonuses (e.g., +10% damage to any element). They MUST add to per-element stats, never multiply, otherwise a player stacking +omni AND +element gets quadratic instead of linear scaling. This is a design trap chaos-backend learned the hard way.

### Hit resolution order (from doc §"Parry/Block Placement")

```
HitCheck → Parry → Block → Penetration/Defense → Reflection → Shields → Resources
```

Each step is a probability gate or stat reduction; only after all of these does the damage reduce a resource (HP). Parry and Block are *passive pre-mitigation* (consume a resource budget themselves rather than HP).

### Status hit dependency

```rust
if !hit_success && status_config.requires_hit {
    return; // No status if miss
}
// status_prob = f(attacker_stats, defender_stats); roll vs threshold; apply
```

I.e., status effects are gated on the underlying hit/damage event succeeding.

### Per-element derived stats fed into damage calc

From `ElementalSystemData` (`crates/element-core/src/core/elemental_data.rs:501-598`), each element has 50+ derived stats keyed in fixed arrays — `power_point`, `defense_point`, `crit_rate`, `crit_damage`, `accurate_rate`, `dodge_rate`, `element_penetration`, `element_absorption`, `element_amplification`, `element_reduction`, `reflection_rate`, `parry_rate`, `block_rate`, `skill_execution_speed`, `skill_cooldown_reduction`, etc. Plus `element_interaction_bonuses: [[f64; 50]; 50]` — 2D matrix of element-vs-element multipliers (Fire vs Water = 0.7, Water vs Fire = 1.3).

### Pattern applicable to LoreWeave

- Damage formula is **multi-stage with explicit ordering** — author can extend without knowing the next stage's math. Useful template for Q7 ("V1 damage formula").
- "Omni additive, element multiplicative" is a **clean separation rule** — generic stats stack additively, specialized stats stack multiplicatively. Worth lifting verbatim.
- The 50×50 element interaction matrix is over-engineered for LoreWeave V1; an author-declared "element_pair → multiplier" lookup is enough.

---

## §5 — Effect / Status / Condition trinity

Three cores, confusingly similar names. Boundaries (from reading `docs/effect-core/00_Effect_Core_Overview.md`, `docs/status-core/00_Status_Core_Design_Notes.md`, `crates/condition-core/src/types.rs`):

| Core | Role | Lifecycle | Example |
|---|---|---|---|
| **condition-core** | **Predicate evaluator.** `if X then Y` building block. Stateless. Pure function. | None — evaluated on demand. | "actor has element_mastery > 1000", "target is in fire zone" |
| **effect-core** | **Effect-as-data registry + dispatcher.** Skyrim-inspired Magic Effects pattern: every effect (spell, talent, perk, item-passive, status-tick) is a registered `EffectId` with its own metadata. Hub for all `apply X to actor`. | Object pool (frequent effects) + lazy creation (rare effects). 85% pool hit rate target. | The "burning" effect blueprint, the "+10% fire damage" perk blueprint. |
| **status-core** | **Active status-effect manager on actors.** Holds per-actor `Vec<ActiveStatusEffect>`, manages stacking, duration, immunity, magnitude, periodic ticks. | Stateful per actor — created when applied, destroyed when expired/dispelled. | Actor X currently has burning(stacks=3, remaining=4s) + slow(stacks=1, remaining=2s). |

### Composition flow

```
Trigger (action / item-use / damage / time-tick)
   → effect-core resolves EffectId → EffectBlueprint
   → condition-core evaluates "should apply?" predicate
   → status-core instantiates ActiveStatusEffect on target
   → status-core ticks (every game-tick) consume + re-emit damage events
   → status-core expires / dispels → cleanup
```

### Condition-core type signature (the predicate primitive)

```rust
// crates/condition-core/src/types.rs
pub struct ConditionConfig {
    pub condition_id: String,
    pub function_name: String,            // ← e.g., "actor_has_element"
    pub operator: ConditionOperator,      // ← Equal, GreaterThan, Contains, In, …
    pub value: ConditionValue,            // ← Boolean | Integer | Float | String | List
    pub parameters: Vec<ConditionParameter>,
}
pub enum ConditionOperator {
    Equal, NotEqual, GreaterThan, LessThan, GreaterThanOrEqual,
    LessThanOrEqual, Contains, NotContains, In, NotIn,
}
```

This is essentially a **rules-engine atom** — function name resolves to a Rust closure registered in a function-registry, operator + value form the comparison, parameters are bound at evaluation time. LoreWeave's PL_006 (status) and the future progression-trigger system can both lean on this idea.

### Pattern applicable to LoreWeave

- The **3-way split is good** — predicate (stateless) vs blueprint registry (data) vs active instance (per-actor stateful).
- Maps to LoreWeave: condition-core ↔ existing condition predicates in PL_005/PL_006; effect-core ↔ new "modifier blueprint registry" (could anchor PROG_001 training-rule definitions); status-core ↔ existing PL_006 status feature.
- Skyrim's Magic Effects pattern (effect-core) is well-trodden ground for "every modifier is data" — strong validation for our 07_event_model EVT-G framework's "actions emit events; events resolve to modifiers".

---

## §6 — Multi-axis progression (race + element + class stacking)

`crates/race-core` and `crates/job-core` are empty stubs (`job-core/src/lib.rs` is 20 lines of placeholder). Design intent inferred from `crates/actor-core/src/types.rs::Actor.race: String` field + the subsystem registry pattern.

### Implicit pattern — each axis is a Subsystem

The actor-core architecture treats race/element/class/cultivation/etc. **identically**. Each is registered as a `Subsystem` in the `PluginRegistry`; each emits a `SubsystemOutput` per aggregation tick:

```rust
// crates/actor-core/src/types.rs
pub struct SubsystemOutput {
    pub system_id: String,
    pub primary: Vec<Contribution>,           // ← per-stat additive/multiplicative
    pub derived: Vec<Contribution>,
    pub caps: Vec<CapContribution>,           // ← per-stat min/max overrides
    pub processing_time: u64,
    pub context: Option<HashMap<String, serde_json::Value>>,
    pub meta: SubsystemMeta,                  // ← system_id, priority, version, deps
    pub created_at: DateTime<Utc>,
}
```

So race-Elf gives `[Contribution { stat: "agility", bucket: Flat, value: +2 }, …]`. Element-Fire gives `[Contribution { stat: "fire_power", bucket: Mult, value: 1.1 }, …]`. Class-Mage gives `[Contribution { stat: "mana_max", bucket: Flat, value: +50 }, …]`. They all flow into the same bucket processor and stack via the **FLAT → MULT → POST_ADD → OVERRIDE** order, with each subsystem's `priority` breaking ties.

### Cap layering across subsystems

`AcrossLayerPolicy` (`crates/actor-core/src/enums.rs`) handles "race says max=100, class says max=120, element says max=80 — what's the effective cap?":

```rust
pub enum AcrossLayerPolicy {
    Intersect,            // most restrictive (min(maxes), max(mins)) → 80
    Union,                // least restrictive (max(maxes), min(mins)) → 120
    PrioritizedOverride,  // higher-priority layer wins → whichever has highest priority
}
```

Each cap contribution carries its own `layer: String` so the resolver can group caps per-layer first, then apply the across-layer policy. This is a **clean answer to the "multi-source cap" problem** and directly relevant to LoreWeave Q6 (storage model) and Q5 (skill atrophy — atrophy is just a cap-shrinking subsystem).

### Pattern applicable to LoreWeave (tu tiên multi-cultivation-line)

A tu tiên PC with 4 cultivation lines (luyện khí + luyện thể + luyện đan + chế phù) maps cleanly onto 4 Subsystems each emitting their own contributions. Each line has its own progression curve, training trigger, stage caps. They stack via the same bucket processor. **No new aggregation primitive is needed beyond the actor-core Subsystem pattern** — the "multi-system stacking" solution is to lift the Subsystem model verbatim.

---

## §7 — Patterns applicable to PROG_001 V1

For each Q1-Q7 in CONCEPT_NOTES §5:

### Q1 — Attribute vs Skill ontology (unified / split / hybrid)

chaos-backend is **fully unified**: everything is a "stat name" that subsystems contribute to. There's no syntactic distinction between an attribute (`strength`) and a skill (`negotiation`) — both are HashMap keys. The `core_resources: [f64; 9]` array is the only "blessed" subset (HP/MP/SP/etc.), and even that is just convention.

**Recommendation for LoreWeave:** Adopt **unified bag** at the engine layer (one `actor_attributes: Map<String, AttributeValue>` aggregate), but allow author schema declaration to *categorize* into "attribute" vs "skill" for UI/UX purposes. Engine doesn't care; UI does. This matches chaos-backend's pattern and accommodates all three E1/E2/E3 examples.

### Q2 — Curve types V1 (linear / log / tier-stage / threshold / discrete)

chaos-backend implements **tier-stage breakthrough** via the `ElementMasteryLevel` enum stack (level + tier + realm + stage). XP-to-next is uniform exponential under the hood, but the labels and per-band multipliers create the breakthrough feel.

**Recommendation for LoreWeave V1:** ship **two curves** — (a) linear-with-soft-cap (modern social, D&D ability score) and (b) tier-stage-breakthrough (tu tiên realm/stage). Both must be data-driven (author declares thresholds in YAML), unlike chaos-backend's hardcoded enum. The exponential-uniform-with-labels trick is worth borrowing for tier-stage.

### Q3 — Training trigger sources

chaos-backend has **no training trigger code at all** — XP is just an `i64` field, the increment source is unimplemented. The framework `from_experience()` lookup exists, but nothing pushes XP into it.

**Recommendation:** This is a green-field decision for LoreWeave. The PL_005 Use kind cascade already provides "action → triggers → effects" plumbing; PROG_001 should reuse that, not invent a new pipe. Sources to support V1: (a) action-driven (PL_005), (b) time-cultivation (turn-tick subscription), (c) item-elixir (RES_001 consumable hook). Mentor + quest defer to V1+.

### Q4 — NPC progression V1 (train M&B / static CK3 / hybrid)

No data point in chaos-backend (no NPC code). 

**Recommendation:** Static-with-explicit-event-bumps is V1 sweet spot. Engine supports both via the same Subsystem pattern; whether NPC X has the "training" subsystem registered is a per-NPC config flag.

### Q5 — Skill atrophy V1

chaos-backend has none. But the cap system (`CapContribution` with `Additive` / `HardMax` / `SoftMax` modes) **is the natural primitive** — atrophy is a slow-running subsystem that emits negative `Additive` cap contributions over time.

**Recommendation:** Defer atrophy to V1+ but design caps with atrophy in mind. The `AcrossLayerPolicy::Intersect` mode + `Additive` cap mode means we can ship atrophy later without schema migration.

### Q6 — Storage model (new aggregate / extend cores / reuse RES)

chaos-backend's answer is **a new aggregate** (`Actor` with `core_resources: [f64; 9]` + `custom_resources: HashMap<String, f64>` + subsystem-list) entirely separate from inventory/items. Strong separation: actor-stats and items are distinct concerns, items affect stats only via subsystem registration.

**Recommendation:** New `actor_attributes` aggregate, NOT extending RES_001. Items contribute via PL_005 Use cascade. Cells/realm-config provide schema. This aligns with chaos-backend's pattern.

### Q7 — Combat damage formula V1 vs V1+ DF7-equivalent

Steal the **damage composition law** verbatim:

```
base_damage → element_multiplier → resistance(after_penetration) → status_application
```

with the **omni-additive / element-multiplicative** invariant. V1 ship a 3-stage formula; V1+ extend with parry/block/reflection/shields per chaos-backend's full pipeline. The formula is data-extensible — author can register new stages without breaking V1 callers.

---

## §8 — Patterns applicable to OTHER LoreWeave features

### PL_006 (Status effects)

The **effect-core / status-core / condition-core trinity** maps onto our existing PL_006 design. Specifically:
- LoreWeave PL_006 status_blueprint registry ↔ chaos-backend effect-core
- LoreWeave PL_006 active_status on actor ↔ chaos-backend status-core
- LoreWeave PL_005/PL_006 condition predicates ↔ chaos-backend condition-core

**Validation:** the 3-way split is industry-standard. Skyrim's Magic Effects + Condition System is the prior art. PL_006 should NOT collapse blueprint-vs-active into one entity (chaos-backend tried initially per `docs/effect-core/HYBRID_ARCHITECTURE_UPDATE.md` and reverted).

### RES_001 (Resource inventory)

chaos-backend's `Actor.core_resources: [f64; 9]` is a **resource-on-actor pattern**: HP, MP, SP, etc. live on the actor not in inventory. RES_001 already separates "owned items" (inventory) from "actor vital pools" (stats), and chaos-backend confirms this split. Item-instances vs item-templates: chaos-backend's `inventory-service` handlers use "item_id" lookup → instance metadata, matching RES_001 instance/template split.

**Divergence:** chaos-backend has no per-cell-treasury or per-faction-pool patterns — RES_001 V2+ goes beyond.

### 07_event_model + EVT-G framework

The **`Contribution` model** (every stat change is a typed event with source/priority/timestamp) is a strong validation of EVT-G's "actions emit events; events compose into snapshots". Worth adopting the field shape:

```rust
pub struct Contribution {
    pub stat_name: String, pub bucket: Bucket, pub value: f64,
    pub source: String, pub priority: Option<i64>,
    pub dimension: String, pub system: String, pub tags: Option<Vec<String>>,
    pub created_at: DateTime<Utc>,
}
```

Especially `source` + `priority` + `tags` + `system` — these are the EVT-G provenance fields exactly.

### WA_006 (Wiki articles, future)

No direct chaos-backend pattern. The element-core's docs corpus (30+ markdown files per core) is itself a wiki structure — author-facing docs separate from runtime code. WA_006 should expect docs-as-data to scale similarly.

### Future DF7 (deeper damage formula)

chaos-backend's full hit pipeline (`HitCheck → Parry → Block → Penetration/Defense → Reflection → Shields → Resources`) is the canonical DF7 reference. Each stage is a registered handler with input/output contract. LoreWeave can adopt the stage framework even if V1 ships fewer stages.

---

## §9 — What NOT to copy

### Realtime hot-path optimizations

- `actor-core-hierarchical`'s `[f64; 50]` fixed arrays for "1-2 ns access" — irrelevant under our 100ms-to-minutes-per-turn budget; harmful because it freezes schema at compile time. **Reject.**
- The 50×50 `element_interaction_bonuses` 2D matrix — over-engineered. **Reject** in favor of author-declared element-pair lookup table.
- DashMap-everywhere for concurrent stat mutation — turn-based engine has zero concurrent mutation per actor. **Reject.**
- Object-pool effect blueprints with 85% hit rate target — premature optimization; HashMap lookup is fine. **Reject** the pool, **keep** the blueprint registry concept.

### Concrete-per-system enums

- `ElementMasteryLevel` 24-variant Rust enum with hardcoded XP thresholds and bonus multipliers. **Reject** — LoreWeave's per-reality dynamic schema means levels/tiers/stages must be YAML-declared by the author. Reuse the *concept* (3-way orthogonal labels: level + tier + stage) but data-drive it.
- `Actor.race: String` with single global level — **Reject** the single global level (CONCEPT_NOTES §1 user constraint: no level), keep the single-string race tag as a schema-key.
- Vietnamese display names baked into Rust source — **Reject**, all UX strings must live in translation tables.

### Anti-cheat/scale infrastructure

- `services/anti-cheat-service`, `services/matchmaking-service`, the 100K-CCU sub-millisecond claims — irrelevant for LoreWeave's single-author, asynchronous, novel-platform context. **Reject.**

### "Power level" / aggregate combat-rating

chaos-backend implies (via `Actor.level` + element mastery levels) an aggregate progression metric. LoreWeave user constraint C1: NO central level / NO 战力 calculation. **Reject explicitly** — LoreWeave combat resolution must read RELEVANT specific stats per situation, never sum-of-stats.

### Cultivation-system Vietnamese terminology

chaos-backend hardcodes Vietnamese names (Beginner = "Người Mới Bắt Đầu", etc.). LoreWeave is multilingual + per-reality — reality/cell author declares names in their language for their reality. **Reject** all bake-in.

---

## §10 — Quotable Rust types (PROG_001 DRAFT may reference these)

### Q10.1 — The aggregation primitive (load-bearing)

```rust
// crates/actor-core/src/types.rs
pub struct Contribution {
    pub stat_name: String,
    pub bucket: Bucket,             // Flat | Mult | PostAdd | Override
    pub value: f64,
    pub source: String,             // which subsystem emitted
    pub priority: Option<i64>,      // tie-breaker
    pub dimension: String,
    pub system: String,
    pub tags: Option<Vec<String>>,
    pub created_at: DateTime<Utc>,
}
```

### Q10.2 — The cap primitive (atrophy + per-stage cap)

```rust
// crates/actor-core/src/types.rs
pub struct CapContribution {
    pub stat_name: String,
    pub cap_mode: CapMode,          // Baseline | Additive | HardMax | HardMin | Override | SoftMax
    pub min_value: Option<f64>,
    pub max_value: Option<f64>,
    pub source: String,
    pub layer: String,
    pub priority: i64,
    /* + compatibility fields */
}
```

### Q10.3 — Cap layering policy (multi-source caps)

```rust
// crates/actor-core/src/enums.rs
pub enum AcrossLayerPolicy {
    Intersect,             // ∩  — most restrictive
    Union,                 // ∪  — least restrictive
    PrioritizedOverride,   //    — higher-priority layer wins
}
```

### Q10.4 — Bucket processing order (canonical order)

```rust
// crates/actor-core/src/bucket_processor/mod.rs
let bucket_order = [Bucket::Flat, Bucket::Mult, Bucket::PostAdd, Bucket::Override];
// FLAT: sum additively
// MULT: multiply sequentially (× over base)
// POSTADD: add post-multiplication  (e.g., flat damage bonus that ignores % multipliers)
// OVERRIDE: replace value with last contribution's value (boss invulnerability mode)
```

### Q10.5 — Snapshot (immutable per-tick result)

```rust
// crates/actor-core/src/types.rs
pub struct Snapshot {
    pub actor_id: String,
    pub primary: HashMap<String, f64>,
    pub derived: HashMap<String, f64>,
    pub caps_used: HashMap<String, Caps>,
    pub version: i64,
    pub processing_time: Option<u64>,
    pub subsystems_processed: Vec<String>,   // ← provenance
    pub cache_hit: bool,
    pub metadata: HashMap<String, serde_json::Value>,
    pub created_at: DateTime<Utc>,
}
```

### Q10.6 — Tier/Realm/Stage triple (cultivation pattern)

```rust
// crates/element-core/src/core/elemental_data.rs (sketch — drop the hardcoded enum)
pub struct MasteryDescriptor {
    pub xp: i64,
    pub level: LevelKey,    // author-declared; replaces 24-variant enum
    pub tier: TierKey,      // author-declared; coarse grouping
    pub realm: RealmKey,    // author-declared; cultivation-specific
    pub stage: StageKey,    // author-declared; within-realm position
}
// Each Key is a String resolved against the per-reality schema registry.
// The bonus/multiplier table is YAML-declared per-reality, not Rust-match.
```

### Q10.7 — Subsystem output (multi-axis stacking unit)

```rust
// crates/actor-core/src/types.rs
pub struct SubsystemOutput {
    pub system_id: String,
    pub primary: Vec<Contribution>,
    pub derived: Vec<Contribution>,
    pub caps: Vec<CapContribution>,
    pub processing_time: u64,
    pub context: Option<HashMap<String, serde_json::Value>>,
    pub meta: SubsystemMeta,
    pub created_at: DateTime<Utc>,
}

pub struct SubsystemMeta {
    pub system_id: String,
    pub priority: i64,
    pub version: String,
    pub dependencies: Vec<String>,
    pub system: String,
    pub data: HashMap<String, serde_json::Value>,
    pub created_at: DateTime<Utc>,
}
```

### Q10.8 — Condition-core predicate atom

```rust
// crates/condition-core/src/types.rs
pub struct ConditionConfig {
    pub condition_id: String,
    pub function_name: String,                      // resolved against fn registry
    pub operator: ConditionOperator,                // Eq, Gt, Lt, In, Contains, …
    pub value: ConditionValue,                      // Bool|Int|Float|String|List
    pub parameters: Vec<ConditionParameter>,
}
```

### Q10.9 — Damage composition (combat formula skeleton)

```rust
// from docs/combat-core/02_Damage_System_Design.md
fn compute_final_damage(action: &Action, attacker: &Actor, target: &Actor) -> f64 {
    let base = calculate_base_damage(action);
    let elem_mult = element_multiplier(attacker.element, target.element);
    let after_elem = base * elem_mult;
    let resistance = resistance_after_penetration(target, action.element_type);
    let final_damage = after_elem * (1.0 - resistance);
    if action.applies_status && hit_check_passed { /* status_core::apply */ }
    final_damage
}
```

### Q10.10 — Aggregation strategy (per-stat config)

```rust
// crates/element-core/src/aggregation/element_aggregator.rs
pub enum AggregationStrategy {
    Sum, Multiply, Max, Min, Average, First, Last,
    Custom(Box<dyn Fn(Vec<f64>) -> f64 + Send + Sync>),
}
```

(The `Custom` variant is interesting for LoreWeave — author-supplied closure for unusual stats. V1 may not need it; V1+ probably does.)

---

> **Bottom line for PROG_001 DRAFT:** The actor-core aggregation pipeline (Contribution × Bucket × Caps × Snapshot, with Subsystem priority + AcrossLayerPolicy) is the **single most important pattern to lift**. Everything else (24-level enum, 50×50 matrices, hot-path arrays, hardcoded Vietnamese, single global level) is realtime/concrete-per-system baggage to leave behind. Combine with the Skyrim-derived effect/condition/status trinity (validated by chaos-backend's docs corpus) and you have a clean substrate for Q1-Q7 V1 design.
