# RES_001 — Resource Foundation

> **Category:** RES — Resource Foundation (foundation tier; sibling of EF_001 / PF_001 / MAP_001 / CSC_001; 5th and final V1 foundation feature)
> **Catalog reference:** [`catalog/cat_00_RES_resource.md`](../../catalog/cat_00_RES_resource.md) (owns `RES-*` stable-ID namespace)
> **Status:** **CANDIDATE-LOCK 2026-04-27** (DRAFT 2026-04-26 → TDIL closure-pass-extension Q4 day-boundary → turn-boundary applied at TDIL DRAFT bdc8d8e1 → CANDIDATE-LOCK 2026-04-27 closure pass: §14 AC-RES-1..10 walked; RES-Q1..Q6 noted as deferred to consumer feature closures — RES-Q1 to PCS_001 + NPC_001 first-design-pass / RES-Q2 user-facing message confirmed "kho đầy, sản xuất tạm dừng" / RES-Q3 to PL_005 closure pass / RES-Q4 V1 default `consumable_priority` author-declared + fallback declaration-order / RES-Q5 i18n cross-cutting commit / RES-Q6 V1 PC starting Reputation default = 0). Q1-Q12 LOCKED via `00_CONCEPT_NOTES.md` §10 + Q6-Q12 deep-dive. **Foundation tier 6/6 closure feature** — final V1 foundation feature CANDIDATE-LOCK promotion (PROG_001 6th foundation added 2026-04-26 superseded original "5th and final" framing; foundation tier closes EF + PF + MAP + CSC + RES + PROG all CANDIDATE-LOCK). Companion documents: [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + gap analysis) + [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (10-game survey + 12-pattern synthesis + V1/V1+30d/V2/V3 phase mapping).
>
> **CLOSURE-PASS-EXTENSION 2026-04-27 (TDIL_001 DRAFT promotion):** Q4 "DailyBoundary Generator" semantic SUPERSEDED by TDIL-A3 per-turn O(1) Generator semantic (architecture-scale TDIL_001 Time Dilation Foundation). Mechanical revision: 4 Generators (`Scheduled:CellProduction`, `Scheduled:NPCAutoCollect`, `Scheduled:CellMaintenance`, `Scheduled:HungerTick`) shift from `EVT-G2 FictionTimeMarker (day-boundary)` to **per-turn fire** with elapsed-time parameter. Computation invariant: `delta = base_rate × elapsed_time × multiplier` (O(1) regardless of `time_flow_rate` magnitude). Per TDIL-A4 channel-bound vs actor-bound clock-source matrix:
> - **Channel-bound** (read channel `wall_clock` advance): `Scheduled:CellProduction`, `Scheduled:NPCAutoCollect` (V1+30d lazy migration via PROG-D19), `Scheduled:CellMaintenance`
> - **Actor-bound** (read appropriate proper-time clock per BodyOrSoul): `Scheduled:HungerTick` reads `body_clock` (vital exhaustion is body-bound; soul wandering body paused → no hunger advance V1+30d via TDIL-D5)
>
> NO semantic change to user-facing behavior — all V1 acceptance scenarios AC-RES-1..10 preserved. Cross-realm production (Dragon Ball chamber 365× wall = 365 production cycles per outside turn) now correctly handled by elapsed-time multiplication. Affected sections: §10 4-Generator clock-source matrix (channel-bound vs actor-bound discriminator added), Generator binding rows (EVT-G2 day-boundary → per-turn fire). Per RES_001 §10 unified per-turn semantic resolves PROG-D19 cross-feature concern (NPC eager auto-collect → lazy migration V1+30d on unified semantic). See [TDIL_001 §6 Generator clock-source matrix](../17_time_dilation/TDIL_001_time_dilation_foundation.md#6-generator-clock-source-matrix-q6-locked) for full clock-source matrix and [TDIL_001 §6.4 closure-pass coordination](../17_time_dilation/TDIL_001_time_dilation_foundation.md#64-closure-pass-coordination) for cascade rationale.
> **i18n notice:** RES_001 is the FIRST feature to formally adopt the English-stable-IDs + `I18nBundle` display-strings pattern (per user direction 2026-04-26 — game is international; English is the standard for engine identifiers). See §2 for contract. Existing features (PL_002/006, NPC_001/002, PL_005, WA_*) currently use Vietnamese reject copy; cross-cutting i18n audit is deferred (tracked in §17 downstream).
> **V1 testable acceptance:** 10 scenarios AC-RES-1..10 (§14).

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

LoreWeave is a **simulation/strategy game with RPG core** (per user direction 2026-04-26). V1 ships a turn-based RPG vertical slice; V1+30d / V2 / V3 expand into complex resource economy + giao thương + kinh tế module. Without a Resource Foundation, V1 cannot ship:

- Combat (no HP pool to deplete)
- Trade (no currency for NPCs to exchange)
- Cell production (đồng lúa producing rice has nowhere to go)
- Hunger loop (no food consumption tracking)
- NPC economic agency (no inventories for NPCs to own)
- Wuxia/xianxia "danh tiếng" social tracking
- Mortality state machine triggers (HP=0 → death needs HP ownership)

RES_001 establishes the value-substrate that 4 other foundation features reference (EF/PF/MAP/CSC) plus the entire economy module future direction.

### V1 minimum scope (locked per Q1-Q12)

- **5 ResourceKind categories** (Q1): `Vital` / `Consumable` / `Currency` / `Material` / `SocialCurrency`
- **2 aggregates** (Q3): `vital_pool` (T2/Reality, body-bound, actor-only) + `resource_inventory` (T2/Reality, portable, EntityRef-any)
- **3 V1 sinks** (Q2 + Q5 + Q12): food consumption / cell maintenance cost / trade buy-sell spread
- **Hybrid production model** (Q4): cell auto-produces + NPC owner auto-collects + PC owner manual-harvests + no-owner halts
- **Day-boundary Generator tick** (Q4c): all production/consumption fires when fiction-time crosses fiction-day boundary
- **Soft hunger PC+NPC** (Q5): symmetric daily food tick + PL_006 `Hungry` magnitude scaling 1→7=mortality
- **Open economy** (Q2a) with author-declared global pricing + buy/sell spread per kind (Q12b)
- **NPC finite liquidity** (Q12c): trade constrained by NPC actual balance; refilled by Q4f auto-collect
- **Author-configurable currency tiers** (Q10): default single `Copper`; multi-tier (e.g., Vietnamese đồng/lượng bạc/lượng vàng) via RealityManifest
- **Body-bound cell ownership** (Q9c): xuyên không auto-inheritance — cells follow body, not soul
- **English IDs + i18n display strings** (NEW pattern §2)

### V1 NOT shipping (deferred per Q-decisions)

| Feature | Defer to | Why |
|---|---|---|
| Item-unique kind (history, provenance) | V1+30d | Q1c reserved schema |
| PC inventory cap | V1+30d | Q6 schema reserved on `entity_binding` |
| Hydration loop | V1+30d | Q5h |
| Per-cell price variance | V1+30d | Q12a |
| Equipment wear | V1+30d | Q1c follow-up |
| Quality/grade variation | V2 | Q7 needs crafting |
| Crafting recipes | V2 | New module |
| Supply/demand dynamic prices | V2 | New module |
| Trade routes / convoys | V2 | New module |
| Per-town aggregation | V2 | New module |
| NPC-job system | V2 | New module |
| Per-faction treasury | V3 | New module |
| Loans / banking / inflation | V3 | New module |
| Knowledge as resource (CK3 secrets) | V3 | Reserved enum variant |

---

## §2 — i18n Contract (NEW cross-cutting pattern)

### §2.1 Why this pattern

LoreWeave is an international game. English is the engine standard:
- **Stable identifiers** in code, schema, rule_ids, and event sub-types are English (`snake_case` for IDs, `PascalCase` for type names)
- **User-facing strings** (resource names, reject messages, narrative copy) are i18n bundles with English default + per-locale translations
- **Author-declared content** (currency names, custom resource kinds in RealityManifest) is multi-language via I18nBundle

### §2.2 Core types

```rust
/// Multi-language string with English default required.
/// Used for any user-facing display string in RES_001.
pub struct I18nBundle {
    /// English default — REQUIRED. Used as fallback when active locale missing.
    pub default: String,
    /// Per-locale translations. ISO-639-1 lowercase code (e.g., "vi", "zh", "ja", "ko").
    /// "en" key is forbidden here (use `default` field instead — single source of truth for English).
    pub translations: HashMap<LangCode, String>,
}

pub type LangCode = String;  // ISO-639-1 lowercase, e.g., "vi"

impl I18nBundle {
    /// Returns the active-locale string, falling back to `default` (English) if missing.
    pub fn render(&self, locale: &LangCode) -> &str {
        self.translations.get(locale).unwrap_or(&self.default)
    }

    /// Convenience constructor for English-only.
    pub fn en(s: impl Into<String>) -> Self {
        Self { default: s.into(), translations: HashMap::new() }
    }
}
```

### §2.3 RES_001 conformance

All RES_001 user-facing strings use `I18nBundle`:
- `CurrencyDecl.display_name`
- `ResourceKindDecl.display_name`
- `RejectReason.user_message` (LoreWeave-wide RejectReason envelope extension — see §13)
- LLM narrative descriptions (consumed by AssemblePrompt at runtime)

All RES_001 stable IDs are English `snake_case`:
- `rule_id`: `resource.trade.npc_insufficient_funds`, `resource.hunger.starvation_mortality`, etc.
- `aggregate_type`: `vital_pool`, `resource_inventory`
- `EVT-T5` sub-types: `Scheduled:CellProduction`, `Scheduled:HungerTick`, etc.
- Engine-defined enum variants: `VitalKind::Hp`, `VitalKind::Stamina`, `ConsumableKind::Food` (V1 minimum), etc.

### §2.4 Author-content example (Vietnamese xianxia reality)

Author declares 3-tier Vietnamese currency in RealityManifest:

```rust
RealityManifest {
    currencies: vec![
        CurrencyDecl {
            kind_id: CurrencyKindId("copper"),
            display_name: I18nBundle {
                default: "Copper Coin".to_string(),
                translations: hashmap! {
                    "vi".to_string() => "Đồng".to_string(),
                    "zh".to_string() => "銅錢".to_string(),
                },
            },
            base_rate_to_smallest: 1,
            display_priority: 0,
        },
        CurrencyDecl {
            kind_id: CurrencyKindId("silver"),
            display_name: I18nBundle {
                default: "Silver Tael".to_string(),
                translations: hashmap! {
                    "vi".to_string() => "Lượng bạc".to_string(),
                    "zh".to_string() => "兩銀".to_string(),
                },
            },
            base_rate_to_smallest: 100,
            display_priority: 1,
        },
        CurrencyDecl {
            kind_id: CurrencyKindId("gold"),
            display_name: I18nBundle::en("Gold Tael")
                .with_vi("Lượng vàng")
                .with_zh("兩金"),
            base_rate_to_smallest: 10000,
            display_priority: 2,
        },
    ],
    // ... other extensions
}
```

The engine treats `kind_id="copper"` as the stable identifier; LLM narration renders `display_name.render(active_locale)`.

### §2.5 Cross-cutting impact (deferred audit)

Existing features with hardcoded Vietnamese reject copy (PL_006, NPC_001, PL_002, WA_*, etc.) need i18n audit. Tracked in §17 downstream. RES_001 does NOT modify those features in this DRAFT — it establishes the pattern; future cross-cutting commit applies.

---

## §3 — ResourceKind Ontology

### §3.1 ResourceKind enum (forward-compatible per EVT-A11)

```rust
pub enum ResourceKind {
    // ─── V1 active ───
    Vital(VitalKind),                  // body-bound; storage in vital_pool aggregate
    Consumable(ConsumableKindId),      // author-declared kind via RealityManifest
    Currency(CurrencyKindId),          // author-declared currency via RealityManifest (Q10)
    Material(MaterialKindId),          // author-declared material kind
    SocialCurrency(SocialKind),        // V1: only `Reputation`; V2 expands

    // ─── V1+30d reserved (typed-only V1) ───
    Item(ItemKind),                    // unique items with ItemInstanceId

    // ─── V2 reserved ───
    Recipe(RecipeId),                  // crafting recipes as transferable knowledge

    // ─── V3 reserved ───
    Knowledge(KnowledgeKind),          // information/secrets (CK3 pattern)
    Influence(InfluenceKind),          // political/factional leverage
}
```

### §3.2 Engine-fixed enums (closed sets)

```rust
/// Body-bound vital pools. Engine-fixed for type-system enforcement.
pub enum VitalKind {
    Hp,         // V1 active
    Stamina,    // V1 active
    Mana,       // V1+ reserved
}

/// Social currencies. V1 ships only Reputation; V2 expands to wuxia/xianxia + CK3 patterns.
pub enum SocialKind {
    Reputation,    // V1 active — wuxia/xianxia danh tiếng
    Prestige,      // V2 reserved (CK3 prestige)
    Piety,         // V2 reserved (religious standing)
    Influence,     // V2 reserved (faction leverage)
}
```

### §3.3 Author-declared kinds (open per-reality)

`ConsumableKindId`, `CurrencyKindId`, `MaterialKindId` are stable string IDs declared by author in RealityManifest. Pattern matches NPC_001 ActorId — substrate fixes type, author declares instances.

```rust
pub struct ConsumableKindId(pub String);   // e.g., "rice", "bread", "water", "potion_minor_heal"
pub struct CurrencyKindId(pub String);     // e.g., "copper", "silver", "gold"
pub struct MaterialKindId(pub String);     // e.g., "wood", "iron", "stone", "leather"
```

### §3.4 ResourceKindDecl (RealityManifest declaration shape)

```rust
pub struct ResourceKindDecl {
    pub kind: ResourceKind,
    pub display_name: I18nBundle,
    pub description: I18nBundle,
    pub nutritional: bool,             // Q5j — true if counts as "food" for hunger tick
    pub stack_policy: StackPolicy,
    pub transferable: bool,            // false for Vital body-bound; true otherwise
}

pub enum StackPolicy {
    Sum,                               // unbounded count (Currency, Material, Consumable, SocialCurrency)
    SumClamped { max_value: u32 },     // bounded with max (Vital — but storage in vital_pool, not resource_inventory)
    Identity,                          // each instance unique (Item V1+30d)
}
```

### §3.5 V1 minimum kinds (engine defaults if author declares nothing)

If a reality's author leaves `resource_kinds: []` empty in RealityManifest, RES_001 ships these defaults:

| ResourceKind | kind_id | display_name (en) | nutritional | stack_policy |
|---|---|---|---|---|
| `Currency` | `copper` | "Copper Coin" | false | Sum |
| `Consumable` | `food_basic` | "Food" | true | Sum |
| `Consumable` | `water_basic` | "Water" | false | Sum (V1+30d when hydration ships) |
| `Material` | `wood` | "Wood" | false | Sum |
| `Material` | `iron` | "Iron" | false | Sum |
| `Material` | `stone` | "Stone" | false | Sum |
| `SocialCurrency` | (auto) | "Reputation" | false | Sum |
| `Vital::Hp` | (engine) | "HP" | n/a | SumClamped { max_value: 100 } |
| `Vital::Stamina` | (engine) | "Stamina" | n/a | SumClamped { max_value: 100 } |

Author can override any default by declaring same `kind_id`.

---

## §4 — Aggregates (Q3 split LOCKED)

### §4.1 `vital_pool` aggregate

**Scope:** T2/Reality (per DP-A14). One instance per Actor (PC + NPC).
**Owner:** Body-bound — `vital_pool.actor_ref` MUST resolve to an entity_binding with body-presence.
**Transferable:** NO (type-system enforced — no transfer event accepts vital_pool source/target).

```rust
pub struct VitalPool {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,                          // body-bound owner
    pub vitals: Vec<VitalInstance>,
    pub last_modified_at_turn: u64,
    pub schema_version: u32,                          // V1 = 1
}

pub struct VitalInstance {
    pub kind: VitalKind,                              // Hp | Stamina | (Mana V1+)
    pub current_value: u32,
    pub max_value: u32,                               // from VitalProfile per actor-class
    pub last_regen_at_fiction_ts: i64,
    pub depletion_history_window: VecDeque<DepletionRecord>,  // for replay determinism per EVT-A9
}

pub struct VitalProfile {
    pub kind: VitalKind,
    pub max_value: u32,                               // class default
    pub regen_rule: RegenRule,
    pub depletion_rule: DepletionRule,
    pub on_zero_effect: OnZeroEffect,
}

pub enum RegenRule {
    TimeBased { per_fiction_hour: u32 },              // Hp regens 5/hour
    RestBased { per_rest_action: u32 },               // Stamina regens 30/rest
    Manual,                                           // no auto-regen (Mana V1+ design TBD)
}

pub enum DepletionRule {
    ActionDriven,                                     // Hp depleted by Strike kind
    PerActionCost { kind: InteractionKind, amount: u32 },  // Stamina costs per action
    Manual,                                           // explicit only
}

pub enum OnZeroEffect {
    EmitMortalityTrigger,                             // Hp=0 → WA_006
    ApplyStatus(StatusFlag),                          // Stamina=0 → PL_006::Exhausted
    NoOp,
}
```

**Storage:** Reality-scoped index by `actor_ref → VitalPool`. Read-side projection `actor_vital_summary` provides hot-path lookup for AssemblePrompt + combat tick.

### §4.2 `resource_inventory` aggregate

**Scope:** T2/Reality. One instance per owner EntityRef (PC, NPC, Cell, Item-V1+30d).
**Owner:** Any EntityRef.
**Transferable:** YES — entries can move between inventories via PL_005 Interaction (Trade/Give/Strike).

```rust
pub struct ResourceInventory {
    pub reality_id: RealityId,
    pub owner: EntityRef,                             // PC | NPC | Cell | Item (V1+30d)
    pub balances: Vec<ResourceBalance>,
    pub last_modified_at_turn: u64,
    pub schema_version: u32,                          // V1 = 1
    pub inventory_cap: Option<CapacityProfile>,       // Q6b — None V1, Some V1+30d
}

pub struct ResourceBalance {
    pub kind: ResourceKind,                           // discriminator
    pub amount: u64,                                  // count (Sum stack policy)
    pub instance_id: Option<ItemInstanceId>,          // Q1a — None V1, Some V1+30d for Item kind
}

pub struct CapacityProfile {                          // V1+30d only
    pub max_slots: u32,                               // distinct kinds count
    pub max_weight: Option<u32>,                      // V2 weight cap
}
```

### §4.3 Aggregate scoping summary

| Aggregate | Tier | Owner type | Transferable | Body-bound |
|---|---|---|---|---|
| `vital_pool` | T2/Reality | Actor only (PC/NPC) | NO | YES |
| `resource_inventory` | T2/Reality | EntityRef any | YES | NO |

### §4.4 EntityRef discriminator

Per EF_001:
```rust
pub enum EntityRef {
    Actor(ActorId),                                   // PC + NPC
    Cell(ChannelId),                                  // cell-as-entity (per PF_001)
    Item(ItemInstanceId),                             // V1+30d
    Faction(FactionId),                               // V3
}
```

V1 valid `resource_inventory.owner` types: `Actor` and `Cell`. `Item` reserved V1+30d. `Faction` reserved V3.

---

## §5 — Ownership Semantics

### §5.1 Resource ownership (resource_inventory)

Resources are owned by exactly ONE EntityRef at a time (per axiom 1 in CONCEPT_NOTES §1). Single-owner invariant:
- Transfer = atomic decrement-from-source + increment-to-target in single event
- Co-ownership / shared-ownership = V2+ feature (deferred)

### §5.2 Cell ownership (Q9 LOCKED)

Cell ownership lives on `entity_binding` (EF_001 owns), NOT in resource_inventory:

```rust
// EF_001 entity_binding extension (added 2026-04-26 RES_001 DRAFT)
pub struct EntityBinding {
    // ... existing fields ...
    pub cell_owner: Option<EntityRef>,                // V1 — None for orphan cells
}
```

V1 cell ownership transfer paths:
1. **Author Forge edit** (WA_003 `Forge:EditCellOwnership` sub-shape) — admin canonical
2. **Body-substitution / xuyên không** (PCS_001 mechanic — Q9c) — soul-replacement preserves body-bound ownership
3. **NPC death → orphan** (Q9d) — owner=None, production halts (Q2e)

V1+30d transfer paths (deferred):
4. PC-to-PC trade (PL_005 dedicated TradeKind extension)
5. PC-buy from NPC (PL_005 dedicated BuyKind extension)

V2+ paths (deferred):
6. NPC succession (heir inherits)

### §5.3 Body-bound semantics (xuyên không)

Per Q9c LOCKED: cell ownership follows BODY, not soul. When PC's soul transmigrates into another body (xuyên không event):
- Old body's cell ownership chain transfers automatically to new soul
- Soul-only resources (V1+ Knowledge kind) follow soul
- Body-bound resources (Vital pool — Hp, Stamina) transfer with body

PCS_001 owns the xuyên không mechanic + its event sequence. RES_001 documents the resource-side implication: vital_pool follows body; resource_inventory.owner=Actor follows body's actor identity.

### §5.4 EF_001 cascade integration

Per EF_001 §6.1 cascade rules: when entity is destroyed, dependent resources cascade per HolderCascade pattern.

| Triggering event | Resource impact |
|---|---|
| Actor destroyed (death finalized via WA_006) | `resource_inventory.owner=Actor(_)` becomes orphan; PL_005 Loot kind picks up V1+30d |
| Cell destroyed (PF_001 StructuralState=Destroyed) | `resource_inventory.owner=Cell(_)` becomes orphan; treated same as no-owner cell |
| Item destroyed (V1+30d) | Item-bound resources cascade to holder |

Cascade order: per EF_001 §6.1 4-step (entity delta → destroyed signal → consumer cascade → cell-resident cascade). RES_001 is a CONSUMER (receives signals; updates ownership).

---

## §6 — Production Model

### §6.1 ProducerProfile (RealityManifest declaration)

```rust
pub struct ProducerProfile {
    pub place_type: PlaceTypeRef,                     // applies to all cells of this PlaceType
    pub outputs: Vec<ProductionOutput>,
    pub stockpile_cap: u64,                           // Q2c — production halts at cap
}

pub struct ProductionOutput {
    pub kind: ResourceKind,
    pub amount_per_fiction_day: u32,                  // fixed V1, dynamic V1+30d
}
```

Example: a `Tavern` PlaceType might produce 2 copper/day; a `RiceField` PlaceType might produce 5 rice/day; an `IronMine` might produce 1 iron/day.

### §6.2 Production trigger

`Scheduled:CellProduction` Generator (EVT-T5 Generated, EVT-G2 trigger source `FictionTimeMarker` day-boundary):

1. Generator fires on fiction-day boundary (via 07_event_model EVT-G framework)
2. For each cell in reality with non-None owner + ProducerProfile match:
   - For each output in ProducerProfile.outputs:
     - `cell.resource_inventory[kind] += amount_per_fiction_day`
     - Clamp to `stockpile_cap`; surplus dropped (V1) or queued (V1+30d)
3. Emit EVT-T5 sub-type `Scheduled:CellProduction` per cell with batch outputs

Cells with `owner=None` (orphan): SKIP production (Q4h).
Cells with PC owner: produce into cell stockpile (PC must visit + harvest later).
Cells with NPC owner: produce into cell stockpile, then `Scheduled:NPCAutoCollect` Generator transfers to NPC (§6.4).

### §6.3 Day-boundary timing model

Per Q4c: production fires when fiction-time **crosses fiction-day boundary**. NOT continuous accrual; NOT per-turn; specifically per-day.

Timing scenarios:
- Sleep 8h fiction (no day cross) → 0 production (within-day)
- Sleep crosses midnight (fiction-day rolls) → 1 day's production
- Travel 5 fiction-days → 5 days' production batch-emitted (deterministic per EVT-A9)
- Multiple actors/turns within same fiction-day → no double-trigger (Generator dedup by day-marker)

### §6.4 NPC owner auto-collect

`Scheduled:NPCAutoCollect` Generator (EVT-T5 Generated, day-boundary, per-cell):

1. After CellProduction Generator (sequenced via 07_event_model V4 ordering)
2. For each cell with `owner=Actor(npc_id)`:
   - Transfer entire cell stockpile → NPC's resource_inventory
   - Emit `ResourceTransfer { from: Cell(c), to: Actor(npc), kinds: [...] }` event
3. Cell stockpile reset to 0 after transfer

PC-owned cells (`owner=Actor(pc_id)` where actor is a PC) are EXCLUDED from auto-collect — preserves player agency (Q4g). PC must visit + harvest manually via PL_005 Use kind on cell (§7.3 below).

### §6.5 Production rate variability (V1+ landing point)

V1: `amount_per_fiction_day` is fixed.
V1+30d: add `RateModifier` chain (Status / Weather / Skill multipliers) — applied at production-emit time.
V2: dynamic rate via supply/demand market simulation.

Schema reservation: `ProductionOutput` keeps `amount_per_fiction_day` as base; V1+30d adds `modifier_refs: Vec<RateModifierRef>` field (additive per I14).

### §6.6 Author-edit production rate

Author can edit ProducerProfile via WA_003 Forge (existing path):
- `Forge:EditCellProducerProfile` AdminAction sub-shape (added 2026-04-26 — RES_001 registers; WA_003 closure folds in)
- Edit canonical RealityManifest → next fiction-day Generator picks up new rate

---

## §7 — Consumption Model

### §7.1 Consumption sources (V1)

| Source | Mechanism | Sink role |
|---|---|---|
| **Hunger tick** (Q5) | Per-fiction-day each actor consumes 1 food | Sink #1 (food disappears) |
| **Cell maintenance** (Q2c) | Per-fiction-day each cell with owner consumes maintenance cost from owner | Sink #2 (currency/material disappears) |
| **PL_005 Use kind** | Action-driven: PC drinks potion, eats apple | Generic — varies by kind |
| **Trade buy/sell spread** (Q12b) | NPC profit margin on round-trip | Sink #3 (PC loses on round-trip) |
| **Combat damage** (PL_005 Strike) | Vital depletion (Hp via Strike DepletionRule) | Vital pool only |

### §7.2 Hunger tick Generator

`Scheduled:HungerTick` Generator (EVT-T5 Generated, day-boundary):

```pseudo
for each actor in reality:
    food_kinds = ConsumableKinds where nutritional=true
    if actor.resource_inventory contains any nutritional consumable:
        deduct 1 unit of (any nutritional consumable; deterministic priority order)
        if actor has Hungry status: clear it (magnitude = 0)
    else:
        if actor has Hungry status:
            increment Hungry magnitude by 1
        else:
            apply Hungry status with magnitude=1
        if Hungry.magnitude >= 7:
            emit MortalityTransitionTrigger { actor, cause_kind: Starvation }
```

Deterministic food-priority: when actor has multiple food kinds, deduct in author-declared priority order (RealityManifest `consumable_priority: Vec<ConsumableKindId>`). Default priority: declaration order in `resource_kinds`.

### §7.3 Cell maintenance Generator

`Scheduled:CellMaintenance` Generator (EVT-T5 Generated, day-boundary):

```pseudo
for each cell with owner != None:
    profile = cell_maintenance_profiles[cell.place_type]  // RealityManifest
    if profile is None: continue  // no maintenance required
    if owner.resource_inventory has all required kinds in sufficient amount:
        deduct maintenance cost from owner inventory
        cell.production_active = true
    else:
        cell.production_active = false  // production halts (Q2f)
        // V1+30d: cell decays toward Destroyed via PF_001 StructuralState
```

```rust
pub struct MaintenanceCost {
    pub costs: Vec<ResourceCost>,                     // can require multiple kinds
}

pub struct ResourceCost {
    pub kind: ResourceKind,
    pub amount: u64,
}
```

Example: `Tavern` cell maintenance = 2 copper + 1 wood per fiction-day. If owner has both → production active. If owner has 0 wood → production halts.

### §7.4 PC harvest action (Q4b)

PL_005 Use kind targeting cell-as-target (per existing PL_005 ExamineTarget extension pattern):

```pseudo
PC executes: /use harvest <cell_ref>
  Validator chain:
    - PC must be in cell (presence check via PL_001 §3.6)
    - cell.owner == Actor(pc_id) OR cell.owner == None  (orphan cells harvestable)
    - cell.resource_inventory has > 0 entries
  Outcome:
    - drain entire cell.resource_inventory → PC.resource_inventory
    - emit InteractionAccepted { kind: Use, sub_intent: Harvest, ... }
```

V1: PC harvests orphan cells too (free taking — no original owner objects). V1+30d: orphan-claim-via-harvest can reassign cell ownership to PC (Q9 path).

### §7.5 Vital pool depletion (combat)

PL_005 Strike kind cascade emits VitalDelta event consumed by RES_001:

```rust
pub struct VitalDelta {
    pub actor_ref: ActorRef,
    pub kind: VitalKind,
    pub delta: i32,                                   // negative = damage
    pub source: VitalDeltaSource,                     // Strike { attacker } | Status { flag } | Generator { ... }
}
```

RES_001 validator applies delta to `vital_pool.vitals[kind]`. Clamps to [0, max_value]. If new value == 0 + OnZeroEffect == EmitMortalityTrigger → emit `MortalityTransitionTrigger { actor, cause_kind: KilledBy(attacker) }`.

---

## §8 — Transfer / Trade Model

### §8.1 Transfer mechanisms V1

| Mechanism | Kind | Atomic? | Path |
|---|---|---|---|
| **Trade** (consensual exchange) | PL_005 Give kind reciprocal (V1 minimum) — both sides Give in same turn | YES | PL_005 OutputDecl with `aggregate_type=resource_inventory` |
| **Gift** (one-way, no consideration) | PL_005 Give kind | YES | Same |
| **Theft** (forced, no consent) | PL_005 Strike kind cascade | YES | Same |
| **Loot** (post-mortem) | V1+30d (PL_005 Loot kind on corpse) | YES (V1+30d) | Same |
| **Production** (creation) | EVT-T5 Generated (no PL_005 path) | YES | §6 above |
| **Consumption** (destruction) | EVT-T5 Generated OR PL_005 Use kind | YES | §7 above |

### §8.2 Trade pricing (Q12 LOCKED)

```rust
pub struct PriceDecl {
    pub kind: ResourceKind,
    pub base_buy_price: u64,                          // NPC sells to PC at this (in smallest currency unit)
    pub base_sell_price: u64,                         // NPC buys from PC at this
    pub primary_currency: CurrencyKindId,             // which currency this price is in (default: smallest)
}

// Invariant (validator-enforced): base_buy_price >= base_sell_price (NPC profit margin = sink)
```

V1: global pricing. RealityManifest declares `prices: Vec<PriceDecl>`. Same price for all NPCs.
V1+30d: per-cell price variance.
V2: supply/demand dynamic.

### §8.3 NPC finite liquidity (Q12c LOCKED)

NPC has finite resource_inventory balance. Trade validator:

```pseudo
PC offers: pay 5 copper for 1 rice from NPC
  Validate:
    - NPC.resource_inventory[Rice] >= 1   (else reject: resource.trade.npc_insufficient_goods)
    - PC.resource_inventory[Copper] >= 5  (else reject: resource.trade.pc_insufficient_funds)
    - price_check: 5 == price.base_buy_price[Rice]  (else reject: resource.trade.invalid_price V1+30d)

PC offers: sell 1 rice for 3 copper to NPC
  Validate:
    - PC.resource_inventory[Rice] >= 1   (else reject: resource.trade.pc_insufficient_goods)
    - NPC.resource_inventory[Copper] >= 3  (else reject: resource.trade.npc_insufficient_funds)
    - price_check: 3 == price.base_sell_price[Rice]
```

NPC liquidity refilled via Q4f auto-collect from owned cells. PC can deplete NPC; trade halts until NPC's cells produce more.

### §8.4 Currency conversion at trade (Q10b)

V1 simplification: total-in-smallest-unit accounting + display-layer multi-tier.

PC pays 1 silver + 30 copper = 130 copper-equivalent (silver = 100 copper per CurrencyDecl). Internal accounting:
- Deduct 130 copper-equivalent from PC.resource_inventory total
- PC's resource_inventory still tracks per-CurrencyKindId (copper, silver, gold separately)
- Display: LLM narrates "Lý Minh paid 1 silver tael and 30 copper coins" via I18nBundle formatter

V1+30d: enforce per-denomination tracking + change-availability constraint.

### §8.5 Trade event shape

```rust
// PL_005 Interaction sub-payload extension (registered at PL_005 closure pass)
pub struct InteractionTradePayload {
    pub buyer: ActorRef,
    pub seller: ActorRef,
    pub buyer_offers: Vec<ResourceBalance>,           // PC pays this
    pub seller_offers: Vec<ResourceBalance>,          // PC receives this
    pub atomic: bool,                                 // V1 = always true
}
```

---

## §9 — RealityManifest Extensions

### §9.1 Fields added by RES_001 (registered in `_boundaries/02_extension_contracts.md` §2)

```rust
RealityManifest {
    // ─── existing fields per Continuum / NPC_001 / WA_001 / WA_002 / WA_006 / PF_001 / MAP_001 / CSC_001 ───

    // ─── RES_001 extensions (added 2026-04-26) ───

    /// Author-declared resource kinds. Empty = use engine V1 defaults (§3.5).
    pub resource_kinds: Vec<ResourceKindDecl>,

    /// Author-declared currencies (Q10). Empty = single default Copper.
    pub currencies: Vec<CurrencyDecl>,

    /// Author-declared vital profiles per actor-class (Q3e). Engine ships sensible defaults.
    pub vital_profiles: Vec<VitalProfileDecl>,

    /// Cell production rates per PlaceType (Q4d).
    pub producers: Vec<ProducerProfile>,

    /// Trade pricing per kind (Q12a global V1).
    pub prices: Vec<PriceDecl>,

    /// Cell stockpile capacity per PlaceType (Q2c production constraint).
    pub cell_storage_caps: HashMap<PlaceTypeRef, u64>,

    /// Cell maintenance cost per PlaceType (Q2c sink #2).
    pub cell_maintenance_profiles: HashMap<PlaceTypeRef, MaintenanceCost>,

    /// Initial resource distribution (currency + goods seed).
    pub initial_resource_distribution: Vec<InitialDistributionDecl>,

    /// Initial Reputation distribution (SocialCurrency Q1c V1).
    pub social_initial_distribution: HashMap<ActorRef, i64>,
}

pub struct VitalProfileDecl {
    pub actor_class: ActorClassRef,                   // e.g., "peasant", "warrior", "noble"
    pub profiles: Vec<VitalProfile>,
}

pub struct InitialDistributionDecl {
    pub owner: EntityRef,
    pub balances: Vec<ResourceBalance>,
}
```

### §9.2 Default values (engine fallback)

If author provides empty arrays, engine defaults apply per §3.5 + sensible balance:
- Default 1 currency: `copper` with rate 1
- Default vital profiles: PC = Hp/Stamina max 100 each, regen TimeBased 5/hour Hp + RestBased 30/rest Stamina; NPC peasant = max 50/50.
- Default cell maintenance: `None` (no cost) — V1 author-tunable
- Default cell storage cap: 1000 units per cell

### §9.3 Per-reality opt-in

Authors can omit feature-specific fields; defaults apply (per `_boundaries/02_extension_contracts.md` §2 rule 4 — composability).

---

## §10 — Generator Bindings

### §10.1 V1 Generators (4 total)

All registered as `EVT-T5 Generated` sub-types per 07_event_model EVT-A11 sub-type ownership. RES_001 owns the 4 V1 sub-shape definitions.

| Sub-type | Trigger | Description |
|---|---|---|
| `Scheduled:CellProduction` | EVT-G2 `FictionTimeMarker` (day-boundary) | Cells produce per ProducerProfile rate |
| `Scheduled:CellMaintenance` | Same day-boundary | Cells consume maintenance cost from owner |
| `Scheduled:NPCAutoCollect` | Same day-boundary | NPC owner auto-collects cell stockpile |
| `Scheduled:HungerTick` | Same day-boundary | All actors consume 1 food OR Hungry+=1 |

### §10.2 Generator ordering (per EVT-G6 Coordinator)

Within day-boundary trigger, sequence:
1. `Scheduled:CellProduction` — fill cell stockpiles
2. `Scheduled:NPCAutoCollect` — drain to NPC owners
3. `Scheduled:CellMaintenance` — deduct from owners (after auto-collect, owner has fresh balance)
4. `Scheduled:HungerTick` — deduct food from all actors

This ordering ensures owners have current resources before maintenance check + hunger tick.

### §10.3 Determinism (per EVT-A9 RNG)

Each Generator must be deterministic for replay. RNG seeds:
- CellProduction: `blake3(reality_id || day_marker || "production")`
- NPCAutoCollect: `blake3(reality_id || day_marker || "collect")`
- CellMaintenance: deterministic (no RNG)
- HungerTick: deterministic ordering by actor_id (no RNG)

### §10.4 Cycle detection (per EVT-G3)

RES_001 Generators do NOT trigger other Generators in same fiction-day. They emit T5 events; T5 events do NOT cascade to T6/T1/T3 within same day. Cycle-free.

V1+30d if RateModifiers introduce cell→cell cascades (e.g., one cell's production buffs neighbor's rate), Coordinator-level cycle detection applies.

---

## §11 — Validator Chain

### §11.1 RES_001 validators (added to `_boundaries/03_validator_pipeline_slots.md`)

Slot ordering relative to existing validators:

| Slot | Validator | Owner | Order |
|---|---|---|---|
| ... | (existing PL_001 / PL_005 / PL_006 / WA_006 / EF_001 / PF_001 validators) | | |
| `RES-V1` | `ResourceBalanceCheck` | RES_001 | After PL_005 OutputDecl validation, before WA_006 mortality |
| `RES-V2` | `VitalDepletionGuard` | RES_001 | After PL_005 Strike kind validation |
| `RES-V3` | `TradePricingValidator` | RES_001 | After PL_005 Trade payload parse |
| `RES-V4` | `MaintenanceLiquidityCheck` | RES_001 | At Scheduled:CellMaintenance Generator emit |

### §11.2 Validator behaviors

**RES-V1 ResourceBalanceCheck**: For each PL_005 OutputDecl with `aggregate_type=resource_inventory`:
- If decrement: source owner balance >= amount
- If increment: target owner exists
- Reject: `resource.balance.insufficient` or `resource.balance.invalid_owner`

**RES-V2 VitalDepletionGuard**: For Strike kind cascade emitting VitalDelta:
- Apply clamping per OnZeroEffect
- If post-delta value == 0 + OnZeroEffect == EmitMortalityTrigger → emit MortalityTransitionTrigger
- No reject (this validator is event-emitter, not gate)

**RES-V3 TradePricingValidator**: For PL_005 Trade payload:
- Verify offered amounts match RealityManifest.prices (V1 strict-match; V1+30d allows author-declared price ranges)
- Verify NPC liquidity (Q12c)
- Reject: `resource.trade.npc_insufficient_funds` / `resource.trade.npc_insufficient_goods` / `resource.trade.pc_insufficient_funds` / `resource.trade.invalid_price`

**RES-V4 MaintenanceLiquidityCheck**: At CellMaintenance Generator:
- For each cell with owner: check owner inventory has required maintenance kinds
- If yes → deduct + cell.production_active=true
- If no → skip deduction + cell.production_active=false (no reject — Generator handles gracefully)

---

## §12 — Cascade Integration with Other Features

### §12.1 PL_005 Interaction integration

Reuses existing OutputDecl mechanism:
- `aggregate_type="resource_inventory"` → mutates resource_inventory
- `aggregate_type="vital_pool"` → mutates vital_pool (Strike kind only V1; Use V1+30d for healing potions)

PL_005 closure pass folds in:
- Trade kind sub-payload (`InteractionTradePayload`)
- Harvest sub-intent for Use kind (PC → cell drain)
- 7 V1 RES_001 rule_ids registered in PL_005 documentation

### §12.2 PL_006 Status Effects integration

**Promote Hungry from V1+ reserved → V1 active.** Magnitude semantics:
- 1-3 = mild (narrative: "feels hungry")
- 4-6 = severe (narrative: "starving / weakened")
- 7+ = critical → emit MortalityTransitionTrigger

PL_006 owns the status flag + magnitude field. RES_001 owns the Generator that increments/clears it. Boundary clean.

V1: narrative-only effect (no Stamina/Hp penalty from Hungry status). V1+30d: -10% Stamina max while Hungry magnitude >= 4.

### §12.3 WA_006 Mortality integration

RES_001 emits `MortalityTransitionTrigger` events from 2 sources:
- Vital depletion (Hp=0): `cause_kind: KilledBy(attacker_ref)`
- Hunger threshold (Hungry magnitude >= 7): `cause_kind: Starvation`

WA_006 closure pass adds `Starvation` to `cause_kind` enum (additive per I14).

### §12.4 EF_001 Entity Foundation integration

EF_001 closure pass extends `entity_binding`:
- `cell_owner: Option<EntityRef>` (Q9 LOCKED)
- `inventory_cap: Option<CapacityProfile>` (Q6b reservation V1, used V1+30d)

RES_001 reads these fields; EF_001 owns the schema.

### §12.5 PF_001 Place Foundation integration

PF_001 references in RealityManifest:
- `cell_storage_caps[place_type]` per cell type (Q2c)
- `cell_maintenance_profiles[place_type]` per cell type (Q2c)
- `producers[place_type]` matching ProducerProfile (Q4d)

PF_001 doc closure pass cross-references RES_001 for cell-as-economic-entity model.

### §12.6 PCS_001 PC Substrate integration (parallel agent)

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) §4.4 reading list update needed:
- Add RES_001 mandatory reading
- Add §X "Cell ownership inheritance via body-substitution" — V1 mechanic where xuyên không soul-replacement preserves body-bound ownership chain (Q9c LOCKED)
- Add VitalProfile reference: PCS_001 declares per-PC max_value overriding RealityManifest defaults

Update scheduled at PCS_001 first-design-pass (parallel agent picks up).

### §12.7 NPC_001 Cast integration

NPC_001 doc closure pass adds:
- §X "NPC owner auto-collect Generator" — daily cell production transfers to NPC inventory
- §Y "NPC consumption tick" — daily food consumption via HungerTick Generator
- VitalProfile reference: NPC_001 declares per-NPC-class defaults

### §12.8 07_event_model integration

07_event_model registers 4 V1 Generator sub-types (per EVT-A11):
- `EVT-T5::Scheduled:CellProduction`
- `EVT-T5::Scheduled:CellMaintenance`
- `EVT-T5::Scheduled:NPCAutoCollect`
- `EVT-T5::Scheduled:HungerTick`

All trigger via EVT-G2 `FictionTimeMarker` source (day-boundary). Sequencing per EVT-G6 Coordinator.

EVT-T3 Derived sub-types added:
- `aggregate_type=vital_pool` (RES_001 owned)
- `aggregate_type=resource_inventory` (RES_001 owned)

EVT-T8 AdminAction sub-shape added (WA_003 Forge owns):
- `Forge:EditCellProducerProfile`
- `Forge:EditPriceDecl`
- `Forge:EditCellMaintenanceCost`
- `Forge:GrantInitialResources`

WA_003 Forge closure folds these in.

---

## §13 — RejectReason rule_id Catalog

### §13.1 `resource.*` namespace (registered in `_boundaries/02_extension_contracts.md` §1.4)

V1 rule_ids (12 total):

| rule_id | Trigger | Vietnamese display (i18n bundle) |
|---|---|---|
| `resource.balance.insufficient` | Owner balance < required amount for decrement | "Không đủ tài nguyên" |
| `resource.balance.invalid_owner` | OutputDecl target owner doesn't exist | "Chủ sở hữu không hợp lệ" |
| `resource.balance.negative_amount_forbidden` | OutputDecl amount < 0 (Currency/Material) | "Số lượng không hợp lệ" |
| `resource.vital.below_zero` | Validator caught vital depletion below 0 (defensive — clamping should prevent) | "Lỗi hệ thống chí mạng" |
| `resource.vital.body_bound_transfer_forbidden` | Attempt to transfer Vital between actors | "Sinh lực không thể chuyển giao" |
| `resource.trade.npc_insufficient_funds` | NPC has < sell_price worth of currency to buy from PC | "Người này không đủ tiền" |
| `resource.trade.npc_insufficient_goods` | NPC has < requested amount of goods to sell to PC | "Người này không đủ hàng" |
| `resource.trade.pc_insufficient_funds` | PC has < buy_price worth of currency | "Bạn không đủ tiền" |
| `resource.trade.pc_insufficient_goods` | PC has < offered amount to sell | "Bạn không đủ hàng" |
| `resource.trade.invalid_price` | Offered amount doesn't match RealityManifest price (strict V1) | "Giá không phù hợp" |
| `resource.harvest.empty_cell` | PC harvest action on cell with empty stockpile | "Không có gì để thu hoạch" |
| `resource.harvest.not_owner_or_orphan` | PC harvest on cell owned by another actor | "Đây không phải tài sản của bạn" |

### §13.2 V1+30d reservations

- `resource.balance.cap_exceeded` — inventory_cap enforcement
- `resource.trade.bargaining_failed` — LLM-mediated price negotiation rejection
- `resource.item.instance_not_found` — Item kind lookup failure

### §13.3 RejectReason envelope extension

RES_001 introduces `user_message: I18nBundle` field on RejectReason (per §2.3 i18n contract). This is an ENVELOPE-level addition affecting Continuum (PL_001 §3.5).

```rust
pub struct RejectReason {
    pub rule_id: String,                              // English stable ID
    pub user_message: I18nBundle,                     // NEW — multi-language user-facing
    pub detail: serde_json::Value,
}
```

PL_001 Continuum closure pass folds in (additive per I14 — `user_message` is new optional-but-recommended field; existing rule_ids backfill English `default` from existing Vietnamese as deferred audit).

---

## §14 — Acceptance Criteria

10 V1-testable scenarios. Each must pass deterministically per EVT-A9 replay.

### AC-RES-1 — Cell production day-boundary tick
- Setup: Reality with 1 RiceField cell (owner=NPC Lão Vương), ProducerProfile = 5 rice/day, stockpile_cap = 100
- Action: Sleep command 8 fiction-hours (no day cross)
- Expected: Cell stockpile unchanged (0 rice)
- Action: Sleep command 16 fiction-hours (crosses 1 day boundary)
- Expected: 1× CellProduction Generator fires; cell.resource_inventory[Rice] = 5; 1× NPCAutoCollect transfers to Lão Vương; final Lão Vương inventory[Rice] = 5

### AC-RES-2 — Multi-day batch production
- Setup: Same as AC-RES-1
- Action: Travel command 5 fiction-days
- Expected: 5× CellProduction events emitted batch-style; 5× NPCAutoCollect events; final Lão Vương inventory[Rice] = 25
- Determinism: Replay produces identical event sequence with same blake3 RNG seeds

### AC-RES-3 — Cell maintenance failure halts production
- Setup: Tavern cell (owner=NPC), ProducerProfile = 2 copper/day, MaintenanceCost = 1 wood/day. NPC owner has 0 wood.
- Action: Day-boundary tick
- Expected: CellMaintenance Generator runs first; NPC owner has 0 wood → cell.production_active=false; CellProduction skipped for this cell; emit `cell_maintenance_failed` derived event

### AC-RES-4 — PC manual harvest drains cell stockpile
- Setup: RiceField cell (owner=PC), stockpile = 30 rice (accumulated over 6 fiction-days; PC didn't auto-collect per Q4g)
- Action: PC executes `/use harvest <cell_ref>` while present in cell
- Expected: PL_005 Use kind validator passes RES-V1 + EF_001 + PF_001 checks; cell stockpile drains to 0; PC.resource_inventory[Rice] = 30 (assuming PC starts at 0)

### AC-RES-5 — Hunger tick: actor with food, no Hungry status
- Setup: Lý Minh has 5 rice in inventory, no Hungry status
- Action: Day-boundary tick
- Expected: HungerTick Generator deducts 1 rice; Lý Minh inventory[Rice] = 4; no Hungry status applied; status.actor_status[Lý Minh] unchanged

### AC-RES-6 — Hunger tick: actor without food, Hungry magnitude increments
- Setup: Lý Minh has 0 food, no Hungry status
- Action: Day-boundary tick
- Expected: HungerTick deducts nothing; emits ApplyStatus(Hungry, magnitude=1) targeting Lý Minh; PL_006 actor_status reflects

### AC-RES-7 — Starvation mortality threshold
- Setup: Lý Minh has Hungry magnitude=6, no food
- Action: Day-boundary tick
- Expected: HungerTick increments magnitude to 7; emits `MortalityTransitionTrigger { actor: Lý Minh, cause_kind: Starvation }`; WA_006 consumes; Lý Minh enters Mortality state machine

### AC-RES-8 — Trade with sufficient liquidity (PC buys from NPC)
- Setup: NPC Lão Vương has 50 rice + 20 copper. RealityManifest price[Rice] = { buy: 5 copper, sell: 3 copper }. PC has 100 copper.
- Action: PC executes `/trade buy 10 rice from Lão Vương`
- Expected: PL_005 Trade kind validator passes RES-V3; PC pays 50 copper; Lão Vương receives 50 copper; Lão Vương sends 10 rice; PC receives 10 rice
- Final: PC inventory = { copper: 50, rice: 10 }; Lão Vương inventory = { copper: 70, rice: 40 }

### AC-RES-9 — Trade with NPC insufficient funds (PC sells to NPC)
- Setup: NPC Lão Vương has 5 copper, 50 rice. PC has 0 copper, 20 rice. price[Rice].sell_price = 3 copper.
- Action: PC executes `/trade sell 10 rice to Lão Vương`
- Expected: RES-V3 validator computes required = 30 copper; Lão Vương has only 5 copper; reject with `resource.trade.npc_insufficient_funds`; user_message renders Vietnamese fallback if locale=vi

### AC-RES-10 — Multi-currency display formatter
- Setup: Reality declares 3 currencies (copper rate=1, silver rate=100, gold rate=10000). PC has 12345 copper-equivalent total.
- Action: AssemblePrompt renders PC inventory display
- Expected: Formatter outputs "1 gold tael, 23 silver taels, 45 copper coins" (English default) or "1 lượng vàng, 23 lượng bạc, 45 đồng" (vi locale via I18nBundle)

---

## §15 — Deferrals

### §15.1 V1+30d (RES_002 — within 30 days of V1 ship)

| ID | Description | Rationale |
|---|---|---|
| RES-D1 | `Item(ItemKind)` variant V1+30d ship | ItemInstanceId + history + provenance complexity (Q1c) |
| RES-D2 | PC inventory weight cap enforcement | CapacityProfile schema reserved V1 (Q6) |
| RES-D3 | Per-cell price variance | Author declares per-cell PriceDecl override (Q12a) |
| RES-D4 | Equipment wear / condition | Per-instance condition counter (V1+30d Item kind) |
| RES-D5 | Hydration loop | Symmetric with hunger; needs `Thirsty` status in PL_006 |
| RES-D6 | Per-actor-class consumption rate override | Currently universal 1 food/day (Q5i) |
| RES-D7 | RateModifier chain | Status / Weather / Skill multipliers on production |
| RES-D8 | Multi-tier currency per-denomination tracking | V1 uses total-smallest-unit; V1+30d tracks per-denomination |
| RES-D9 | Bargaining LLM-mediated price negotiation | LLM proposes prices outside strict-match |
| RES-D10 | Orphan-claim-via-harvest | PC harvesting orphan cell can claim ownership |

### §15.2 V2 (Economy module — `13_economy/` folder, future)

| ID | Description |
|---|---|
| RES-D11 | Production chains (Recipe aggregate; multi-step crafting) |
| RES-D12 | Supply/demand dynamic prices (Market aggregate per region) |
| RES-D13 | Trade routes + convoys (TradeRoute aggregate) |
| RES-D14 | Per-town resource aggregation |
| RES-D15 | NPC-job system (Occupation per NPC; LLM allocates labor) |
| RES-D16 | Quality grade tiers |
| RES-D17 | Maintenance/upkeep recurring sinks at multiple tiers |
| RES-D18 | Decay/spoilage for organics |

### §15.3 V3 (Strategy module — future)

| ID | Description |
|---|---|
| RES-D19 | Per-faction treasury aggregation |
| RES-D20 | Hierarchical income flow (cell → town → faction; vassal → liege) |
| RES-D21 | Loans + banking + interest |
| RES-D22 | Inflation mechanic (controlled currency sink at faction level) |
| RES-D23 | Tax system (% flow from lower tier to upper tier) |
| RES-D24 | Diplomatic resource exchange |
| RES-D25 | `Knowledge(KnowledgeKind)` variant V3 ship — secrets/intel as resource |
| RES-D26 | `Influence(InfluenceKind)` variant V3 ship — political leverage |
| RES-D27 | Cross-reality trade — conflicts with R5 anti-pattern policy; OUT of scope |

---

## §16 — Open Questions (closure pass items)

> **CANDIDATE-LOCK 2026-04-27 closure pass:** All 6 RES-Q* RESOLVED as deferrals to consumer feature closures (mirror AIT-Q1/Q2 + PROG-Q1..Q5 closure pattern). RES_001 V1 substrate complete; consumer features own seed-time/runtime decisions on each axis.

| ID | Question | Resolution at CANDIDATE-LOCK 2026-04-27 |
|---|---|---|
| RES-Q1 | Default vital_pool VitalProfile — what max_value for PC vs NPC peasant vs NPC noble? | **RESOLVED: deferred to PCS_001 + NPC_001 first-design-pass** — consumer features own per-actor-class default declarations; RES_001 V1 schema-stable for any per-class profile. PCS_001 already CANDIDATE-LOCK 2026-04-27 (`af025ebb`); NPC_001 CANDIDATE-LOCK; both consume `vital_pool` aggregate via standard pattern. |
| RES-Q2 | Cell stockpile overflow handling V1: drop or queue? | **RESOLVED: drop** (production halts at cap per Q4 + Q2c LOCKED); user-facing I18nBundle message `cell_production_halted_storage_full` with default English `"storage full, production paused"` + Vietnamese translation `"kho đầy, sản xuất tạm dừng"` per §2 i18n contract. |
| RES-Q3 | Trade reciprocity: V1 uses Give-kind reciprocal pair OR dedicated Trade kind? | **RESOLVED: deferred to PL_005 closure pass** — PL_005 owns interaction-kind ontology; RES_001 V1 supports both via OutputDecl pattern (schema-additive either way). |
| RES-Q4 | Determinism of "any nutritional consumable" food-priority — author-declared vs deterministic-id-order? | **RESOLVED: V1 default author-declared `consumable_priority`** (RealityManifest extension OPTIONAL); fallback to declaration-order in `resource_kinds` if author empty. Deterministic per replay-determinism invariant. |
| RES-Q5 | i18n cross-cutting audit — when do existing features (PL_006/NPC_001/PL_002/WA_*) migrate? | **RESOLVED: deferred to i18n cross-cutting commit** (engine-wide migration post-RES_001 LOCK); RES_001 V1 introduces I18nBundle pattern locally per §2; existing Vietnamese hardcoded reject copy V1 functional + cosmetic-only migration. |
| RES-Q6 | Should `social_initial_distribution` apply to NPCs only or PC + NPC? | **RESOLVED: PC + NPC both** — `HashMap<ActorRef, i64>` covers both (no schema change); PC starting Reputation default = 0 confirmed. REP_001 CANDIDATE-LOCK 2026-04-27 owns PC reputation runtime gating V1+. |

---

## §17 — Coordination Notes / Downstream Impacts

### §17.1 Co-locked changes in this commit

Per `_boundaries/_LOCK.md` claim (single combined `[boundaries-lock-claim+release]` commit):

- ✅ `RES_001_resource_foundation.md` — this DRAFT
- ✅ `_boundaries/01_feature_ownership_matrix.md` — register `vital_pool` + `resource_inventory`
- ✅ `_boundaries/02_extension_contracts.md` §1.4 — `resource.*` rule_id namespace prefix
- ✅ `_boundaries/02_extension_contracts.md` §2 — 9 RealityManifest extension fields
- ✅ `_boundaries/02_extension_contracts.md` §1 — RejectReason `user_message: I18nBundle` field added (NEW i18n contract §2.3)
- ✅ `_boundaries/03_validator_pipeline_slots.md` — RES-V1..V4 slots
- ✅ `_boundaries/99_changelog.md` — entry
- ✅ `00_resource/_index.md` — DRAFT row
- ✅ `00_resource/00_CONCEPT_NOTES.md` §11 — i18n decision capture
- ✅ `catalog/cat_00_RES_resource.md` — feature catalog (NEW)

### §17.2 Deferred follow-up commits (downstream features)

These features need updates AFTER RES_001 LOCK (separate commits, lock-coordinated):

| Feature | Update | Priority | Lock cycle |
|---|---|---|---|
| **PL_006** | Promote `Hungry` reserved → V1 active; document magnitude semantics 1/4/7 thresholds | HIGH (V1 hunger ships) | next closure pass |
| **WA_006** | Add `Starvation` to `cause_kind` enum | HIGH (Q5k mortality) | next closure pass |
| **PL_005** | Register `interaction.harvest.*` + `interaction.trade.*` rule_ids; document Trade kind sub-payload + Use Harvest sub-intent | HIGH (V1 trade + harvest) | next closure pass |
| **EF_001** | Add `cell_owner: Option<EntityRef>` + `inventory_cap: Option<CapacityProfile>` fields on entity_binding | HIGH (V1 ownership semantics) | next closure pass |
| **PCS_001 brief** | Add §4.4 RES_001 mandatory reading + §X body-substitution ownership inheritance | HIGH (parallel agent dependency) | brief update commit |
| **NPC_001** | Document NPC owner auto-collect Generator + NPC consumption tick + VitalProfile NPC-class declarations | MEDIUM | NPC_001 closure pass extension |
| **PF_001** | Cross-reference cell-as-economic-entity model + RealityManifest extensions | LOW | PF_001 closure pass extension |
| **WA_003 Forge** | Add 4 AdminAction sub-shapes (`Forge:EditCellProducerProfile` / `Forge:EditPriceDecl` / `Forge:EditCellMaintenanceCost` / `Forge:GrantInitialResources`) | MEDIUM | WA closure |
| **PL_001 Continuum** | Add `RejectReason.user_message: I18nBundle` field per §2.3 NEW envelope contract | MEDIUM (i18n cross-cutting begins) | next closure pass |
| **07_event_model** | Register 4 EVT-T5 sub-types + 2 EVT-T3 sub-types `aggregate_type` namespace | HIGH | event-model agent next pass |
| **i18n cross-cutting audit** | Migrate existing Vietnamese hardcoded reject copy to I18nBundle (PL_006 / NPC_001 / NPC_002 / PL_002 / WA_*) | LOW (cosmetic; doesn't block V1 functionality) | dedicated cross-cutting commit |

### §17.3 i18n NEW pattern propagation

RES_001 introduces I18nBundle pattern. Future feature designs should:
- Use English `snake_case` for all stable IDs (rule_ids, aggregate_type, sub-types, enum variants)
- Use `I18nBundle` for all user-facing strings (display_name, user_message, narrative descriptions)
- Use `default` field as English-required fallback
- Translations field as optional per-locale

This is the **engine standard** going forward. Existing Vietnamese reject copy in PL_006 etc. remains functional V1 but should be migrated as cosmetic cleanup.

### §17.4 Foundation tier completion

RES_001 is the **5th and final V1 foundation feature**. Foundation tier now covers:
- WHO (EF_001 Entity Foundation)
- WHERE-semantic (PF_001 Place Foundation)
- WHERE-graph (MAP_001 Map Foundation)
- WHAT-inside-cell (CSC_001 Cell Scene Composition)
- **WHAT-flows-through-entity (RES_001 Resource Foundation)**

V1 design surface for foundation tier is COMPLETE pending:
- PCS_001 PC Substrate (parallel agent commissioned, not yet started)
- DF5 Session/Group Chat (V1-blocking deferred)
- DF7 PC Stats (V1-blocking deferred)
- PO_001 PC Creation flow (V1-blocking; depends on PCS_001)

---

## §18 — Status

- **Created:** 2026-04-26 by main session
- **Phase:** **CANDIDATE-LOCK 2026-04-27** (DRAFT 2026-04-26 → TDIL closure-pass-extension applied at TDIL DRAFT bdc8d8e1 → CANDIDATE-LOCK closure pass this commit)
- **Closure pass evidence:** §14 AC-RES-1..10 walked + RES-Q1..Q6 all RESOLVED as deferrals to consumer feature closures (§16); §17.2 downstream impacts mostly applied via subsequent feature closures (PL_006 Hungry V1 promotion / WA_006 Starvation cause / EF_001 cell_owner field / 07_event_model EVT-T5/T3 sub-types — all completed in subsequent closure-pass commits).
- **Foundation tier 6/6 closure feature** — final V1 foundation feature CANDIDATE-LOCK promotion (PROG_001 added 2026-04-26 as 6th foundation; foundation tier closes EF + PF + MAP + CSC + RES + PROG all CANDIDATE-LOCK).
- **Companion docs:** [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q12 deep-dive locked) + [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (10-game survey + V1/V1+30d/V2/V3 phase mapping)
- **Lock-coordinated commit:** Single `[boundaries-lock-claim+release]` commit (CANDIDATE-LOCK closure pass) — annotation-only spec update + folder closure + lock release + changelog entry.
