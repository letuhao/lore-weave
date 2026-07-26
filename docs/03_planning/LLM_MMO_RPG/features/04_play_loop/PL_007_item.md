# PL_007 — Item Foundation

> **Conversational name:** "Item Foundation" (ITM). The **body** behind `EntityId::Item` — the
> definition/instance split, the equipment slot model, the use-effect vocabulary, and the four
> item-management actions. [`EF_001`](../00_entity/EF_001_entity_foundation.md) owns the *contract*
> (`ItemId`, `entity_binding`, lifecycle, affordances); PL_007 owns the *body* that implements it.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** **DRAFT 2026-07-26** — closes audit finding
> [`AUD-F5`](../../12_module_coverage_audit.md#3-findings) (*"Item / equipment module absent —
> STRUCTURAL, V1-blocking"*). The file name was named-and-never-written by EF_001 §Defers-to and by
> EF_001 §1 "Gap 1 — PL_005 nợ Item"; this is that file.
> **Catalog refs:** [`cat_04_PL_play_loop.md`](../../catalog/cat_04_PL_play_loop.md) — PL-26..PL-33;
> owns the `ITM-*` namespace (`ITM-A*` axioms · `ITM-D*` deferrals · `ITM-Q*` open questions ·
> `ITM-V*` validators · `ITM-C*` cross-aggregate consistency rules).
> **Companions (three-file feature, same shape as PL_005 / PL_005b / PL_005c):**
> this file = the **substrate** (§1–§8) · [`PL_007c_integration.md`](PL_007c_integration.md) = the
> **contracts & integration** half (**§9–§19**, continuing this file's numbering — validators, event
> model, manifest, cross-feature integration, sequences, acceptance criteria, deferrals, review ledger)
> · [`PL_007b_inventory.md`](PL_007b_inventory.md) = the **inventory** half (unified view, capacity,
> bounded LLM digest, ground items; ITM-A8/A9). Read this file first.
> **Builds on:** EF_001 §3.1/§4/§6/§7 (binding, `EntityKind` trait, lifecycle, affordances) ·
> RES_001 §3/§4.2/§8.2 (ResourceKind ontology, `resource_inventory`, pricing, `I18nBundle`) ·
> PL_005/PL_005b (4-role pattern; Use/Give/Strike contracts) · PL_006 (`StatusFlag`) ·
> COMB_001 §3/§4 + COMB_002 §5 (`UseItem` action, damage law-chain, Chebyshev range) ·
> AGT-A2 (bounded tool vocabulary) · DP-A6/A12/A14 · EVT Option C taxonomy ·
> **[`DF07_001 Actor Stat Block`](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md)** (landed
> 2026-07-26, same day, in parallel) — DF7 owns the closed `StatSlot` set, the `StatModifier`
> contract, and the resolution law; **PL_007 ships the `EquipmentStats` body DF7-D1 deferred to it**
> (§6.3).
> **Defers to:** a future Loot module (AUD-F9) for the corpse/reward *interaction* (§8.5 gives it the
> substrate) · a future EnvObject feature for real `Unlock` state (§7.3 / ITM-D4) ·
> `14_crafting` V2 for item creation from recipes.

---

## §1 Why this exists

Four gaps, each already named by a locked or DRAFT doc, all of which terminate at "no Item body":

**Gap 1 — PL_005 owes Item (EF_001 §1).** Four of the five V1 `InteractionKind`s take an Item as
`tool` or `target`: Strike (weapon), Give (the gift), Examine (an object), Use (the instrument).
PL_005b's per-kind contracts carry a placeholder in every one of them — "*V1 placeholder check;
V1+ enforces via Item aggregate*" (§3.7, §4.7, §6.7). **V1 interaction cannot ship** while the
enforcement side is a comment.

**Gap 2 — the inventory is half-defined (AUD-F5 / "Inventory 🟡 partial").** RES_001 reserved
`ResourceKind::Item(ItemKind)` with `ResourceBalance.instance_id: Option<ItemInstanceId>` (§3.1,
§4.2) *and* EF_001 reserved `entity_binding.inventory_cap` (§3.1) — two half-schemas pointing at each
other, with `ItemInstanceId` itself undefined. Meanwhile EF_001 AC-EF-10 states the *other*
representation: "*PC's inventory is a read-view over `entity_binding WHERE location.HeldBy = pc_id`,
not a stored aggregate*". Both cannot be the inventory. §3 ITM-A2 picks one and §12.2 withdraws the
other.

**Gap 3 — combat's numbers have no source of variance.** COMB_001 §4's damage law-chain opens
`base = max(1, atk.strike_power − def.armor)`, and COMB_002 §5 gates melee on adjacency, ranged on
`range`. Weapons and armour are *how those inputs differ between two actors*. Without items, every
combatant of a given class is numerically identical and the law-chain is decorative.

**Gap 4 — two EF_001 deferrals were deferred *to this file*.** EF-D3 (`InContainer` enforcement) and
EF-D4 (`Embedded` slot taxonomy) both name "future Item feature" / "future EnvObject feature" as
their target phase. §3 ITM-A6 resolves EF-D3 with a decision; EF-D4 stays with EnvObject.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **ItemDef** | Author-declared template in `RealityManifest.item_defs` | System-tier, read-only at runtime, admin-editable via Forge. The blueprint: class, affordances, equip decl, use effect, price, lex tags. |
| **ItemDefId** | `pub struct ItemDefId(pub String)` | English `snake_case` stable ID per RES_001 §2 i18n contract (e.g. `iron_sword`, `minor_heal_elixir`). |
| **item_instance** | T2/Reality aggregate (§4.1) | The runtime thing: which def, how many charges left, where it came from. **Location is NOT here** — it lives in `entity_binding` (EF_001 owns). |
| **ItemInstanceId** | `pub type ItemInstanceId = ItemId;` | **Alias, not a new type.** Resolves the EF_001/RES_001 spelling drift — see ITM-C1 (§9.4). `EntityId::Item(ItemId)` stays the canonical spelling. |
| **ItemClass** | Closed enum — 8 V1 (§5.2) | `Weapon \| Armor \| Trinket \| Consumable \| Tool \| Key \| Document \| Valuable`. Drives default affordances + the digest grouping (PL_007b §5). |
| **actor_equipment** | T2/Reality sparse aggregate (§4.2) | Per-actor slot → instance map. **Not** a location: an equipped item is still `HeldBy(actor)` (ITM-A5). |
| **EquipSlotId** | `pub struct EquipSlotId(pub String)` | Author-declarable with a 6-slot engine default (§6.1). |
| **StatModifier** | **DF07-owned type** — `{ slot: StatSlot, op: ModifierOp, value: i32, source: ModifierSource }` | What an item *contributes*. PL_007 **produces** these with `source = ModifierSource::Equipment(entity_id)`; it does not define the type and does not resolve it (§6.3). |
| **InstrumentTag** | `pub struct InstrumentTag(pub String)` | Author-declared weapon/tool category (`"blade"`, `"spear"`, `"bow"`). The operand that makes PROG_001 `instrument_match` and DF07 `StatTerm.instrument_match` evaluable against a wielded item — and **resolves PROG-D15** (§6.4 / ITM-C7). |
| **UseEffectDecl** | Closed enum — 7 V1 variants (§7.1) | The bounded vocabulary of what `Use` can do. Each variant maps to an existing owner's aggregate; PL_007 invents no new effect substrate. |
| **CombatItemProfile** | `{ reach, two_handed, strike_kinds }` | The COMB seam: a weapon's reach feeds COMB_002 range, its `strike_kinds` gates PL_005b `StrikeKind`. |
| **Provenance** | `{ origin: ItemOrigin, created_at_turn, created_by: Option<ActorId> }` | The minimum "history" RES-D1 deferred the whole Item variant over. V1 = 3 fields, not a ledger. |

---

## §3 Axioms

> **ITM-A1 — Definition / instance split, with the definition on the System tier.** Every item is a
> (`ItemDef`, `item_instance`) pair. The def is author-declared in `RealityManifest` and **no regular
> actor may mutate it** — runtime writes touch instances only; def edits are `Forge:EditItemDef`
> (admin, audited). This is the platform tenancy rule (CLAUDE.md §User Boundaries: System-tier rows
> are admin-write, user-clone-not-edit) applied to items, and it is what stops "one player renames a
> sword for everyone."

> **ITM-A2 — An instanced item is an Entity, not a resource row. (THE REPRESENTATION RULE.)** An
> item that has identity gets an `entity_binding` row (EF_001 §3.1) and gets location, lifecycle,
> affordances, and the holder-cascade for free. Fungible value stays in RES_001 `resource_inventory`
> as a `ResourceBalance`. **Exactly one representation per thing, chosen by the author at declaration
> time; never both.** Enforced, not asserted: an `ItemDefId` colliding with any `resource_kinds`
> `kind_id` is rejected at canonical seed (ITM-V10 / ITM-C2).

> **ITM-A3 — Items carry modifiers, never stats.** An `ItemDef` never stores a stat value. It declares
> `Vec<StatModifier>` against the **closed DF07-owned `StatSlot` enum** (10 V1 slots). **PL_007 owns
> which items produce which modifiers and when they apply; DF07 owns the slot vocabulary, the layer
> order, and the resolution law.** Neither side may inline the other's half. Concretely: PL_007
> implements DF07's `EquipmentStats` trait and nothing more (§6.3).

> **ITM-A4 — LLM-zero-item-math** (extends COMB-A1 LLM-zero-math and TG-A1 LLM-zero-space). The LLM
> selects *which* item from the bounded held set (AGT-A2) and *what* to point it at. It never emits a
> heal amount, a damage number, a durability value, a price, or any `ItemDef` field. `Item:*` and
> `UseItem` payloads carry an `ItemInstanceId` + an optional target and nothing numeric. A payload
> carrying an out-of-set instance or an engine-owned number is rejected, not clamped.

> **ITM-A5 — Equipment is a slot assignment, not a location.** An equipped item's
> `entity_binding.location` stays `HeldBy(actor)`; "equipped" is a row in `actor_equipment`. This
> preserves EF_001 §3.1's "an entity is in EXACTLY one place at a time" and adds **no fifth
> `LocationKind`** — the enum stays closed (EF_001 §5 "closed V1"). Consequence: unequipping is a
> pure `actor_equipment` write with no binding delta, and a dropped item must be unequipped first
> (ITM-V12).

> **ITM-A6 — V1 inventory is flat (resolves EF-D3).** `EntityLocation::InContainer` stays
> **schema-reserved, enforcement V1+30d** (ITM-D3). V1 holder graphs are therefore depth ≤ 1
> (Item `HeldBy` Actor, or Item `InCell`), which is *why* EF_001's `entity.cyclic_holder_graph` is
> structurally unreachable in V1 rather than merely untested.

> **ITM-A7 — Item-management is engine-authoritative and narration-optional.** Pick up / drop /
> equip / unequip are **not** new `InteractionKind`s — PL_005's five-kind set is closed and its
> closed-set proof stands. They are four PL_007-owned `EVT-T1 Submitted` sub-types (`Item:*`, §8.2)
> that resolve deterministically with no LLM in the path. Same precedent as TG-A3, where movement
> became a turn *phase* rather than competing with the action verbs.

---

## §4 Aggregates

Two aggregates, both T2/Reality, both sparse.

### 4.1 `item_instance` (T2 / Reality) — PRIMARY

```rust
#[derive(Aggregate)]
#[dp(type_name = "item_instance", tier = "T2", scope = "reality")]
pub struct ItemInstance {
    pub instance_id: ItemInstanceId,        // == EntityId::Item(_) payload; ITM-C1
    pub def_id: ItemDefId,                  // → RealityManifest.item_defs; ITM-V1
    pub charges: Option<u32>,               // Some for limited-use defs (elixir doses, scroll reads).
                                            // None = unlimited/not-applicable. 0 → Destroyed (§8.4).
    pub provenance: Provenance,             // §4.3 — the V1 minimum of RES-D1's "history/provenance"
    pub durability: Option<Durability>,     // V1: ALWAYS None (RES-D4). Schema reservation only.
    pub bound_to: Option<ActorId>,          // V1: ALWAYS None (soulbound, ITM-D5). Reservation only.
    pub custom_name: Option<I18nBundle>,    // V1: ALWAYS None (player-named items, ITM-D6).
    pub last_modified_at_turn: u64,
    pub schema_version: u32,                // V1 = 1
}

/// V1+30d wear model (RES-D4). Reserved so the field ordering never churns.
pub struct Durability { pub current: u32, pub max: u32 }
```

**Rules:**
- One row per `instance_id`; **an `item_instance` row and its `entity_binding` row are created in the
  same write transaction** and neither may exist alone (ITM-C3). The binding carries location +
  lifecycle; the instance carries identity + def + charges. Split for the same reason EF_001 split
  `entity_lifecycle_log`: different write frequencies, different snapshot cost.
- `def_id` is immutable after birth. "Turning a sword into a better sword" is a V2 crafting operation
  that destroys and creates, not a def swap — this keeps `Provenance` honest.
- `charges` is engine-written only (ITM-A4). No submitted payload may carry it.
- **Location is deliberately absent.** Any reader wanting "where is this item" reads
  `entity_binding`. Duplicating it here is the drift EF_001 was created to prevent.

### 4.2 `actor_equipment` (T2 / Reality, sparse) — per-actor slot map

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_equipment", tier = "T2", scope = "reality")]
pub struct ActorEquipment {
    pub actor_ref: ActorId,                 // PC + NPC (ActorId per EF_001 §5.1)
    pub slots: Vec<SlotAssignment>,         // ≤ profile slot count; sparse — absent row = nothing equipped
    pub last_modified_at_turn: u64,
    pub schema_version: u32,                // V1 = 1
}

pub struct SlotAssignment {
    pub slot: EquipSlotId,
    pub instance: ItemInstanceId,
    pub equipped_at_turn: u64,
    /// True when this slot is consumed by a multi-slot item whose PRIMARY slot is elsewhere
    /// (two-handed weapon: main_hand primary, off_hand blocked). Blocked slots hold the same
    /// `instance` so unequip is a single-key operation.
    pub blocked_by_primary: bool,
}
```

**Rules:**
- `UNIQUE(actor_ref, slot)` — one item per slot; and `UNIQUE(actor_ref, instance)` — an instance
  cannot fill two independent slots (multi-slot items use `blocked_by_primary`).
- **ITM-C4 (lifecycle lockstep, corrected at review 2026-07-26):** every equipped `instance` MUST
  satisfy `entity_binding.location == HeldBy(actor_ref)` **and**
  `instance.lifecycle_state == holder.lifecycle_state`. The rule is **lockstep with the holder, not
  "always `Existing`"** — the first draft said `== Existing` and that directly contradicted
  [EF_001 §6.1](../00_entity/EF_001_entity_foundation.md#61-cascade-rules), whose
  `Existing → Suspended` cascade transitions *all* held entities to `Suspended` when their holder
  cold-decays (NPC_001 `NpcCold`). Under the wrong rule, every cold-decayed NPC would have violated
  ITM-C4 — and the "fix" an implementer would reach for (clearing the slots) is worse: the NPC would
  wake up disarmed. Correct behaviour: **the slot survives suspension untouched**; `Suspended →
  Existing` restores holder and gear together, in EF_001's one atomic batch.
- The slot is cleared only on the transitions that actually sever holding: holder `→ Destroyed` or
  `→ Removed` (§8.4), the item itself `→ Destroyed`/`Removed` (§8.4), and any location change away
  from `HeldBy(actor_ref)`.
- Sparse: an actor with nothing equipped has **no row** (mirrors ACT_001 `actor_chorus_metadata`).
  `equipment_version` for an absent row is **0**, so DF07's `StatEpoch` has a defined input for an
  unequipped actor rather than a lookup failure.
- **Untracked actors never have a row (ITM-C10).** See §9.4 — this is a scaling invariant, not an
  optimisation.

### 4.3 `Provenance`

```rust
pub struct Provenance {
    pub origin: ItemOrigin,
    pub created_at_turn: u64,
    pub created_by: Option<ActorId>,        // None for CanonicalSeed / Generated
}

pub enum ItemOrigin {
    CanonicalSeed,      // RealityManifest.initial_item_distribution
    ForgeSpawn,         // Forge:SpawnItem (admin)
    WorldPlacement,     // TMP_006 treasure / CSC fixture materialization
    Loot,               // V1 ACTIVE (promoted 2026-07-26 by COMB_004 closure item 2 — the reward
                        // module AUD-F9 called for landed the same day and is its consumer;
                        // see COMB_004 §6 spoils generation)
    Crafted,            // V2 — 14_crafting
    Trade,              // reserved: acquisition path, not creation — V1 unused
}
```

`origin` is written once at birth and never mutated. It is the honest, bounded answer to the
"provenance complexity" that RES-D1 used to justify deferring items entirely: three fields, no
transfer ledger. Full chain-of-custody is ITM-D7.

---

## §5 `ItemDef` — the author-declared template

### 5.1 Shape

```rust
pub struct ItemDefDecl {
    pub def_id: ItemDefId,
    pub display_name: I18nBundle,           // RES_001 §2.2
    pub description: I18nBundle,            // also the Examine text source (§7.2)
    pub class: ItemClass,
    pub affordance_overrides: Option<AffordanceSet>,  // None = ItemClass default (§5.3)
    pub equip: Option<EquipDecl>,           // Some ⇒ equippable (§6.2)
    pub use_effect: Option<UseEffectDecl>,  // Some ⇒ PL_005 Use is valid on it (§7.1)
    pub max_charges: Option<u32>,           // seeds instance.charges at birth
    pub consume_on_exhaust: bool,           // charges hit 0 → Destroyed (§8.4); false ⇒ inert husk
    pub price: Option<PriceDecl>,           // RES_001 §8.2 — None ⇒ not tradeable at NPC vendors
    pub weight: Option<u32>,                // V2 weight cap (RES-D2 / PL_007b §4.3). V1 informational.
    pub lex_tags: Vec<LexTag>,              // WA_001 Stage-4 input (§12.7) — the CRITICAL gate
                                            // PL_005b §8.2 declared for Use and never had an input for
    pub instrument_tags: Vec<InstrumentTag>,// PROG_001 + DF07 instrument_match operand (§6.4 / ITM-C7)
    pub destructible: bool,                 // Strike-on-Item eligibility (V1+ per PL_005b §3.3)
}
```

### 5.2 `ItemClass` — closed enum, 8 V1

| Variant | Typical | Default affordances (§5.3) | Equip? |
|---|---|---|---|
| `Weapon` | sword, spear, bow | examined · used · given · received | yes |
| `Armor` | robe, mail, boots | examined · given · received | yes |
| `Trinket` | jade pendant, ring | examined · used · given · received | yes |
| `Consumable` | elixir, pill (**identity-bearing** — see PL_007b §2) | examined · used · given · received | no |
| `Tool` | rope, flint, lockpick | examined · used · given · received | no |
| `Key` | door key, sect token | examined · used · given · received | no |
| `Document` | letter, manual, map | examined · used · given · received | no |
| `Valuable` | heirloom, art, relic-of-no-power | examined · given · received | no |

**V1+ reserved** (additive per I14): `Container` (ITM-A6/ITM-D3) · `Ammunition` (ITM-D8) ·
`Relic` (active-power artefacts, needs abilities — AUD-F10). **Not** reserved here: `Mount` and
`Vehicle` — mounts are owned by
[TVL_003](../00_travel/TVL_003_mount_vehicle_travel.md) (which deliberately models a `mount` as
*neither* an EF_001 entity nor a RES_001 resource, for the same instance-count reason ITM-Q3 raises),
and `EntityId::Vehicle` is
EF-D1's variant, not an `ItemClass`.

### 5.3 Affordance binding to EF_001

EF_001 §4's implementation matrix declares the Item type default as
`be_examined + be_used + be_given + be_received`. PL_007 **implements `EntityKind for ItemInstance`**
and refines that per class:

> **How the per-class default actually reaches the validator (reworked at cold-start review
> 2026-07-26).** The first draft wrote
> `fn type_default_affordances(&self) -> AffordanceSet { class_default(self.def_id.class()) }`, which
> **cannot be implemented**, for two independent reasons:
>
> 1. `ItemDefId` is a `String` newtype (§2) — it has no `.class()`. The class lives on the
>    `ItemDefDecl` in the manifest, and `item_instance` (§4.1) stores only `def_id`.
> 2. More fundamentally, **EF_001's contract is one default per `EntityType`, not per class.** EF_001
>    §4 says the validator "looks up `entity_type → type_default_affordances` from a registry", and the
>    trait method deliberately takes **`&self` only** — EF_001 §4 states that explicitly, so the trait
>    stays object-safe for `&dyn EntityKind` dispatch. A `&self`-only method on a body holding just a
>    `def_id` has no route to the manifest, so "8 per-class defaults" does not fit the slot EF_001
>    offers at all.
>
> **Resolution — use the mechanism EF_001 already has, and stop fighting the trait.** The per-class set
> is materialised **at instance birth** into the existing `entity_binding.affordance_overrides` field:

```rust
impl EntityKind for ItemInstance {
    fn entity_id(&self) -> EntityId { EntityId::Item(self.instance_id) }
    fn entity_type(&self) -> EntityType { EntityType::Item }

    /// EF_001's per-EntityType default — the honest one, identical for every item, exactly as
    /// EF_001 §4's matrix declares it. Per-class refinement does NOT happen here (see above).
    fn type_default_affordances(&self) -> AffordanceSet {
        BeExamined | BeUsed | BeGiven | BeReceived
    }

    fn display_name(&self, locale: &str) -> String { /* custom_name ?? def.display_name */ }
}

/// Computed ONCE at ItemInstanceBorn, written to entity_binding.affordance_overrides.
/// Pure function of the def — no runtime lookup on the read path (ITM-C12).
fn effective_affordances_at_birth(def: &ItemDefDecl) -> AffordanceSet {
    def.affordance_overrides.unwrap_or_else(|| class_default(def.class))
}
```

Consequences, all of them improvements:

- **The read path stays a single `entity_binding` read.** Stage 3.5.a already reads the binding; it
  needs no manifest join and no `item_defs` lookup per validated target.
- **`class_default → def override → instance override` still holds**, but it is resolved at *birth*
  rather than per read. The tier-merge shape (System → per-def → per-instance) is unchanged; only the
  evaluation time moves.
- `Armor` and `Valuable` **lack `BeUsed`** — so "use the robe" rejects with EF_001
  `entity.affordance_missing` at Stage 3.5.a with no PL_007 code in the path, which was the point.
- Per-*instance* exceptions (EF_001's "Talking Sword") are a later write to the same field.
- **New consequence that must be handled:** because the set is materialised at birth, a
  `Forge:EditItemDef` that changes `class` or `affordance_overrides` does **not** retroactively update
  live instances. That is now an explicit rule rather than an accident — see **ITM-C9** (§9.4), which
  the cold-start review extended to cover exactly this.

---

## §6 Equipment model

### 6.1 Slot profile — engine default, author-overridable

```rust
pub struct EquipSlotProfileDecl {
    pub profile_id: EquipSlotProfileId,
    pub slots: Vec<EquipSlotDecl>,
}
pub struct EquipSlotDecl { pub slot: EquipSlotId, pub display_name: I18nBundle }
```

Engine default when the author declares nothing (mirrors RES_001 §3.5's default-kinds pattern) — **6
V1 slots**: `main_hand` · `off_hand` · `head` · `body` · `feet` · `accessory`.

V1 is **one profile per reality**. Per-race body plans (a serpent-race with no `feet`) are the obvious
extension and are ITM-D2 — the seam is IDF_001 `RaceDecl`, and `profile_id` exists now so activating
it adds a reference, not a schema change.

> **Slot count is capped at 12 V1 (added at review 2026-07-26).** The profile is author-declared, and
> the first draft put no bound on it — which silently broke PL_007b's digest guarantee: `InventoryDigest`
> renders **every** equipped item in full (§5 there), so a reality declaring 30 slots would emit 30
> equipped lines and blow the ≤29-line bound that ITM-A9 asserts, tripping ITM-V17 on a *legitimate*
> author config rather than on a defect. Two things fixed together: the cap here, and PL_007b's bound
> restated as a **formula over the profile size** instead of a constant. Rejects
> `item.slot_profile_too_large` at Stage 0. 12 is generous against the 6-slot default and small enough
> that a full loadout stays readable in a prompt.

### 6.2 `EquipDecl`

```rust
pub struct EquipDecl {
    pub slot: EquipSlotId,                      // primary slot
    pub also_blocks: Vec<EquipSlotId>,          // two-handed sword: [off_hand]
    pub modifiers: Vec<StatModifier>,           // DF07-owned type; applies WHILE EQUIPPED only (§6.5)
    pub requirements: Vec<EquipRequirement>,    // V1: progression-gated only
    pub combat: Option<CombatItemProfile>,      // Some for Weapon/Armor/Shield-like
}

pub enum EquipRequirement {
    /// PROG_001 gate. NOTE the field name: `min_raw_value`, NOT "min_level".
    MinProgression { kind_id: ProgressionKindId, min_raw_value: u64 },
    /// Optional tier gate for realities that declare tiers (PROG_001 tier_max / TierAdvance).
    MinProgressionTier { kind_id: ProgressionKindId, min_tier: u32 },
    // V1+ reserved: RaceAllowed(Vec<RaceId>) · FactionMember(FactionId) · TitleHeld(TitleId)
}

pub struct CombatItemProfile {
    pub reach: u8,                      // 1 = melee (COMB_002 §5 adjacency); >1 = ranged tiles
    pub two_handed: bool,               // consistency-checked against also_blocks (ITM-C5)
    pub strike_kinds: Vec<StrikeKind>,  // PL_005b §3.1 — which StrikeKinds this weapon permits
}
```

`strike_kinds` closes a real hole: PL_005b §3.1 lets any Strike declare `Slash`, but nothing said a
club cannot slash. Now `Strike { tool: Item(club), strike_kind: Slash }` rejects with
`item.strike_kind_unsupported`.

> **`min_level` → `min_raw_value` (corrected at cold-start review 2026-07-26).** The first draft wrote
> `ProgressionLevel { min_level: u32 }`. **PROG_001 has no level concept and explicitly forbids one** —
> its §1 carries a user-directed locked decision: *"NO level / NO power-rating concept. Combat outcomes
> derive from RELEVANT specific attributes/skills, not aggregate 'power level'."* What PROG_001 actually
> exposes is `ProgressionInstance.raw_value: u64` plus an optional tier (`tier_max` / `TierAdvance`).
> Shipping a field called `min_level` would have re-introduced the exact aggregate-power framing the
> progression substrate was designed to avoid, and ITM-V5 would have read a field that does not exist.
> Hence the two variants above, both named in PROG_001's own vocabulary.

### 6.3 The DF07 seam (ITM-A3) — PL_007 is the body DF7-D1 deferred

[`DF07_001`](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md) landed the same day as this doc and
defined the contract precisely, ending with: *"the equipment layer contributes ∅ until **PL_007 Item**
ships an `EquipmentStats` impl — no DF7 change needed then."* This section is that impl. **Nothing in
DF07 changes.**

`StatModifier`, `StatSlot`, `ModifierOp`, and `ModifierSource` are **DF07-owned types** (DF07 §3, §5.3)
and are reproduced here read-only:

```rust
// DF07 §5.3 — owned there, produced here.
pub struct StatModifier {
    pub slot: StatSlot,                 // closed engine enum, 10 V1 (DF07 §3) — NOT a free-form string
    pub op: ModifierOp,                 // Flat | Percent (percent in milli: whole % × 10)
    pub value: i32,
    pub source: ModifierSource,          // PL_007 always emits Equipment(EntityId)
}
```

**The one thing PL_007 implements** (DF07 §6.2 declares this trait and calls it):

```rust
impl EquipmentStats for World {
    /// Every modifier from every EQUIPPED item, with source = Equipment(item entity id).
    /// Held-but-unequipped items contribute nothing (§6.5).
    fn equipped_modifiers(&self, actor: ActorId) -> Vec<StatModifier> {
        actor_equipment(actor).slots.iter()
            .filter(|a| !a.blocked_by_primary)          // multi-slot items counted ONCE — see below
            .flat_map(|a| item_def(a.instance).equip.modifiers.iter()
                .map(|m| StatModifier { source: ModifierSource::Equipment(
                        EntityId::Item(a.instance)), ..*m }))
            .collect()                                   // DF7-A3 sorts; PL_007 need not
    }

    /// Feeds DF07's StatEpoch (§8.2) so a cached block invalidates on any equipment change.
    fn equipment_version(&self, actor: ActorId) -> u64 {
        actor_equipment(actor).last_modified_at_turn
    }
}
```

Two correctness notes that only appear at the seam, both of which would be silent bugs:

- **`blocked_by_primary` slots must be filtered.** A two-handed weapon occupies `main_hand` +
  `off_hand` with the *same* `instance` (§4.2). Iterating slots naively would apply its modifiers
  **twice**. This is why `blocked_by_primary` exists as a field rather than being inferred.
- **`equipment_version` must change on every equip/unequip, including implicit unequips** (§8.3 step
  4). `last_modified_at_turn` satisfies this because the whole equip is one transaction — but a
  same-turn equip→unequip→equip sequence would not bump it. V1 is safe (one action per turn,
  COMB_001 §3 / TG-A3); if that ever changes, this needs a monotonic counter instead. Recorded as
  ITM-Q1.

**The ownership split, for the record:**

| | PL_007 | DF07 |
|---|---|---|
| `StatSlot` vocabulary | references | ✓ **defines** (closed, 10 V1) |
| `StatModifier` / `ModifierOp` / `ModifierSource` types | produces values | ✓ **defines** |
| Which item yields which modifiers | ✓ `EquipDecl.modifiers` | ✗ |
| *When* a contribution applies | ✓ **equipped only** (§6.5) | ✗ |
| Layer order, percent summing, clamping | ✗ | ✓ DF7-A3 / A5 / `resolve_stat_block` |
| Cache invalidation input | ✓ `equipment_version` | ✓ `StatEpoch` consumes it |

Because DF07 defines `StatSlot::StrikePower` and `StatSlot::Armor` explicitly as COMB_001 §4's two
law-chain inputs, the "which spelling?" question this doc originally reserved is **closed on arrival**
— there is no bridge to maintain.

### 6.4 `InstrumentTag` — the operand `instrument_match` never had (resolves PROG-D15)

Both PROG_001 and DF07 want to express *"+ swordsmanship, but only while wielding a sword"*:

- PROG_001 §training: `InstrumentMatch::Specific(ResourceKind)`
- DF07 §6.1 worked example: `StatTerm { kind_id: "swordsmanship", weight: 0.5, instrument_match: Some(Blade) }`

**Neither can be evaluated as written once ITM-A2 lands.** PROG_001 matches instruments by
`ResourceKind`, and ITM-A2 §12.2 withdraws `ResourceKind::Item` — so a wielded sword is an entity with
an `ItemDefId`, which no `ResourceKind` can name. DF07's `Blade` is finer-grained than any
`ItemClass`. The gap is invisible from either doc alone and shows up the moment all three exist.

PL_007 supplies the missing operand:

```rust
pub struct InstrumentTag(pub String);   // author-declared, English snake_case: "blade", "spear", "bow"

// ItemDefDecl gains:
pub instrument_tags: Vec<InstrumentTag>,

// PROG_001 InstrumentMatch gains two variants (additive per I14):
pub enum InstrumentMatch {
    Any,
    Specific(ResourceKind),             // retained for fungible tools; unused by items
    ItemDef(ItemDefId),                 // NEW — exact item
    ItemTag(InstrumentTag),             // NEW — category; this is PROG-D15's "InstrumentClass match"
}
```

**Resolution depends on the consumer — and this is the part the first draft got wrong.** It stated a
single rule ("the `main_hand`-equipped item"), which silently changed PROG_001's existing semantics.
PROG_001's training pseudocode evaluates `rule.instrument_match.matches(current_turn.instrument)` — the
**instrument of the turn being processed**, i.e. `InteractionPayloadBase.tools[0]`, not whatever happens
to be worn. The two consumers genuinely need two different resolutions:

| Consumer | Resolves against | Why |
|---|---|---|
| **PROG_001 training rules** (`Action { instrument_match }`) | the **turn's instrument** — `tools[0]` of the `Interaction` being processed (PROG_001's existing semantic, unchanged) | training is *what you just did with what you had in your hand*. A `Tool`-class item (lockpick, flint) is **never equippable** (§5.2), so an equipped-only rule would make *"train lockpicking while using a lockpick"* permanently unsatisfiable — a whole category of training rule silently dead. |
| **DF07 `StatTerm.instrument_match`** | the **`main_hand`-equipped** item (V1; `off_hand` V1+ per ITM-D19) | a stat term is a *standing* contribution resolved by `resolve_stat_block` outside any turn — there is no "current turn instrument" to read, and a passive bonus for briefly holding something would be incoherent. |

Both use the same `InstrumentMatch` enum and the same `instrument_tags` operand; only the *subject* they
match against differs, and each owner resolves its own. **PL_007 supplies the vocabulary and the tags;
it does not define one global resolution rule.** DF07's example becomes
`instrument_match: Some(InstrumentMatch::ItemTag(InstrumentTag("blade")))` with no change to DF07's law,
and PROG_001's training rules keep behaving exactly as specified.

Author-declared rather than a closed enum, for the same reason RES_001's kinds are: a wuxia reality's
weapon taxonomy is not a sci-fi reality's. Registered as ITM-C7 and as closure-pass extensions to
PROG_001 (§12.6) and DF07 (§12.5).

### 6.5 When modifiers apply

| Item state | Modifiers apply? | Why |
|---|:---:|---|
| Equipped (`actor_equipment` slot) | **yes** | the only V1 path to a stat contribution |
| Held but not equipped (`HeldBy`, no slot) | no | carrying a sword in a sack does not arm you |
| In a cell / container / on a corpse | no | not held |
| Equipped but `lifecycle_state ≠ Existing` | no — and the slot is cleared (§8.4) | destroyed gear cannot buff |

Consequence worth stating because it is a common bug class: **an actor's effective stats change on
`Item:Equip`/`Item:Unequip` and on the destroy-cascade, and at no other time.** Any consumer caching
effective stats subscribes to `actor_equipment` (§12.1).

---

## §7 Use effects

### 7.1 `UseEffectDecl` — closed enum, 7 V1 variants

> **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 (combat family / ABL-Q9) — `UseEffectDecl` retires into
> `EffectOp`, and the reason is a defect, not tidiness.**
>
> ```rust
> pub type UseEffectDecl = EffectOp;   // ABL_001 §4.1 owns the vocabulary (ABL-Q9/Q10)
> ```
>
> `ItemDef.use_effect: Option<UseEffectDecl>` is **unchanged in shape** — only the type it names moves.
> Two findings forced this, both caught by reading the two enums side by side one day after both were
> written:
>
> 1. **They had already diverged.** `StatusApply` here takes `{ flag, magnitude }`; ABL's takes
>    `{ flag, magnitude, duration_rounds }` (combat has rounds). `VitalDelta` here names its field `kind`,
>    ABL's names it `vital`. Neither doc was wrong alone — which is exactly how two closed enums over one
>    concept drift.
> 2. **`VitalDelta { amount: i32 }` was a damage-law-chain bypass, in both docs.** The field is *signed*,
>    so `UseItem { poison_vial, target } → VitalDelta { Hp, −30 }` writes damage that skips COMB_001 §4's
>    chain (**ignores `Armor`**, elem, resist, variance), takes **no hit roll**, accrues **no COMB_003
>    threat** (accrual reads `damage_applied` *from* the chain), ignores **COMB_001 Q4's disparity cap**,
>    and ignores **COMB_006's PvP eligibility predicate** — which guards `Strike` and `Damage`, not a raw
>    vital write. Net: **an unmissable, armour-ignoring PvP weapon usable inside a sanctuary**, silently
>    falsifying COMB_001's *"the 4-step chain is the sole damage authority"*.
>
> **Fix:** `VitalDelta` → **`VitalRestore { vital, amount: u32 }`** — harm becomes **unrepresentable by
> type**, and every path that reduces another actor's vitals is `Damage { power: PowerTerm }`, which
> passes the chain, the hit roll, the disparity cap and the PvP predicate. `ABL-V9` asserts it. This is
> the same *unrepresentable-not-merely-invalid* discipline as **ITM-A7** (equipment is a slot assignment)
> and THR-Q7.
>
> **What PL_007 gains, not loses:** `Unlock` moves into `EffectOp` as its 11th variant (nothing lost), and
> items become able to declare `Damage` — so an **explosive talisman (符)** is finally expressible, which
> the 7-variant enum could not do except via the bypass above. **ITM-A4 is strengthened:** the item still
> emits no number; a damaging talisman declares a `PowerTerm` (a multiplier on a stat slot) and the engine
> computes the damage. **PL_007's narrative-only `Unlock`/`Reveal` treatment below is preserved verbatim**
> and has been adopted by ABL for the same reason.
>
> Registered in [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md)
> §1.4a and the ownership matrix. Applied here as a dated note per the track's behavioural-closure
> pattern; the schema edit lands when this doc is next opened.

PL_007 adds no new effect substrate — it is a dispatch vocabulary, which is what keeps it bounded for
AGT-A2. **But the first draft's blanket claim that "every variant routes to an aggregate already owned
by another feature" was false for two of the seven, and the correction matters because it changes what
a player experiences.** Corrected at cold-start review 2026-07-26:

| Variant | V1 durable sink | Status |
|---|---|---|
| `VitalDelta` | RES_001 `vital_pool` | ✅ real |
| `StatusApply` / `StatusDispel` | PL_006 `actor_status` | ✅ real |
| `ResourceGrant` | RES_001 `resource_inventory` | ✅ real |
| `Inert` | — (none by design) | ✅ honest by construction |
| `Unlock` | **none** — §7.3: "validate the key, log the unlock, narrate it, **mutate nothing**"; blocked on the unwritten EnvObject body | ⚠️ **narrative-only V1** |
| `Reveal` | **none** — PL_005b §5.6 places `KnowledgeAccrual` at "V1+ when PCS_001 `knowledge_tags` ships"; the Oracle read is a query, not a write | ⚠️ **narrative-only V1** |

The risk this creates, stated plainly: `Unlock` and `Reveal` **pass ITM-V8** (`use_effect.is_some()`)
and return **success with no state change**, which from the player's side is indistinguishable from a
bug — and from a QA side is untestable, since there is nothing to assert. So V1 makes it explicit
rather than silent:

> **Narrative-only effects must be declared, not discovered.** `UseEffectDecl::Unlock` and `Reveal`
> resolve to an **accepted turn carrying the `item.use_effect_narrative_only` warning** (the same
> warning-on-accept shape as `item.inventory.cap_partial`), so the audit log records that a Use
> succeeded with no durable delta, and the narrator is told to describe an outcome rather than imply a
> persistent world change. An author who wants a *mechanical* lock should model it as
> `StatusApply`/`ResourceGrant` on the actor until the EnvObject body lands (ITM-D4).

Consequence for §5.2's class table, worth naming since it decides whether two classes are worth
shipping: **`Key` is narrative-only in V1** (its only sensible effect is `Unlock`), and `Document` is
narrative-only unless the author gives it a `ResourceGrant`/`StatusApply` instead of `Reveal`. Both
classes stay in V1 — they carry `display_name`, `description`, Examine text, Give/trade behaviour and
digest grouping, which is real content — but neither has a mechanical effect until ITM-D4.

```rust
pub enum UseEffectDecl {
    VitalDelta   { kind: VitalKind, amount: i32 },              // → RES_001 §7.5 VitalDelta
    StatusApply  { flag: StatusFlag, magnitude: u8 },           // → PL_006 actor_status
    StatusDispel { flag: StatusFlag },                          // → PL_006
    ResourceGrant{ kind: ResourceKind, amount: u64 },           // → RES_001 resource_inventory
    Unlock       { key_tag: String },                           // → EnvObject (V1 audit-only, §7.3)
    Reveal       { canon_ref: CanonRef },                       // → Oracle / knowledge-service
    Inert,                                                      // flavour only; narration, no delta
}
```

- `amount` / `magnitude` come from the **def** (author-declared), never from the payload (ITM-A4).
  `InteractionUsePayload.effect_magnitude` (PL_005b §6.1) is therefore **ignored for item-driven
  effects in V1** and reserved for the V1+ adjustable-dose case — flagged to PL_005 in §12.3.
- Multi-effect items ("elixir that heals *and* buffs") are ITM-D9: V1 is one effect per def. A single
  `UseEffectDecl` keeps the Lex evaluation (§12.7) and the severity estimate single-valued.

### 7.2 Examine

Examine needs no `use_effect`. It renders `def.description.render(locale)` plus, at
`ExamineDepth::Inspect` or deeper, the **mechanically visible** facts: class, equip slot, declared
modifiers, remaining charges. `Provenance` and `durability` are **not** surfaced at V1 depths
(ITM-D7). `ExamineTarget::Item` (PL_005b §5.3) currently takes a `GlossaryEntityId`; with instances
existing it should take an `EntityId` — flagged in §12.3.

### 7.3 Unlock stays audit-only in V1

`Unlock` matches `key_tag` against an EnvObject's declared lock tag. **There is no runtime EnvObject
state aggregate** (PL_005b §6.3 is explicit: "world-rule simulates state transitions in audit-log
only until V1+ Item substrate ships"). PL_007 shipping does *not* discharge that — the missing half is
the **EnvObject** body, which EF_001 §Defers-to assigns to a separate future feature. So V1 behaviour
is unchanged: validate the key, log the unlock, narrate it, mutate nothing. Recorded as ITM-D4 with
the honest blocker named.

---

## §8 Lifecycle & the four item-management actions

### 8.1 Lifecycle is EF_001's; PL_007 is a transition writer

PL_007 introduces **no new lifecycle states**. It writes EF_001 §6 transitions with these
`reason_kind`s (all already in EF_001's `LifecycleReasonKind` enum — no additive change):

| Transition | Trigger | `reason_kind` |
|---|---|---|
| ⊥ → `Existing` | canonical seed · `Forge:SpawnItem` · world placement · V1+ loot/craft | `CanonicalSeed` / `RuntimeSpawn` |
| `Existing` → `Destroyed` | charges exhausted with `consume_on_exhaust` · Strike-on-Item (V1+) · `Forge:DestroyItem` | `InteractionDestructive` |
| `Existing` → `Destroyed` | embedded child whose parent EnvObject died | `HolderCascade` |
| `Existing` → `Removed` | admin decanonize (WA_002/WA_003) | `AdminDecanonize` |
| any → `Existing` | admin restore | `AdminRestoreFromRemoved` |
| `Existing` → `Suspended` | **holder** suspends (NPC cold-decay) — cascade only, never independent | `HolderCascade` |
| `Suspended` → `Existing` | **holder** restores on cell-load — cascade only | `AutoRestoreOnCellLoad` |

**Suspension: cascade-only, never independent (corrected at cold-start review 2026-07-26).** The
earlier flat claim *"items never go `Suspended` in V1"* was **wrong**, and it contradicted this doc's
own ITM-C4 (§4.2), which requires an equipped item's lifecycle to move in **lockstep with its holder**.
Both statements cannot hold. EF_001 is the arbiter and says both halves precisely:

- **EF_001 §6 transitions table** — "V1 only NPCs go Suspended; Items + EnvObjects stay `Existing`
  even at distant cells V1" ⇒ an item has **no independent cold-decay path**. Nothing suspends an item
  *because of the item*.
- **EF_001 §6.1 cascade table** — `Existing → Suspended` on a holder transitions "all directly-held +
  contained + embedded entities" to `Suspended` ⇒ an item **does** suspend *because of its holder*.

So the correct rule is the conjunction, and the two cascade rows above are now in the table (they were
missing, which is what let the contradiction sit unnoticed): **an item never initiates a suspension and
never suspends alone; it follows its holder, and the `actor_equipment` slot survives untouched.**
ITM-D10 ("item cold-loading") is therefore specifically about giving items an *independent* suspension
path — not about the cascade, which is live in V1.

### 8.2 Four `EVT-T1 Submitted` sub-types (ITM-A7)

| Sub-type | Payload | Effect | LLM |
|---|---|---|---|
| `Item:PickUp` | `{ instance }` | `InCell(c) → HeldBy(agent)` | none |
| `Item:Drop` | `{ instance }` | `HeldBy(agent) → InCell(agent's cell)` | none |
| `Item:Equip` | `{ instance, slot? }` | `actor_equipment` slot write (+ implicit unequip, §8.3) | none |
| `Item:Unequip` | `{ slot }` | `actor_equipment` slot clear | none |

Payloads carry an instance/slot reference and nothing else — no counts, no coordinates, no numbers
(ITM-A4). They are `EVT-T1 Submitted` (not T3) because they are *actor-initiated proposals* subject to
the validator pipeline and to commit-service authority (DP-A6 / AGT-A6), exactly like any other turn.

**Why not new `InteractionKind`s:** PL_005's five-kind set is closed with a stated closed-set proof,
and these four have none of the interaction shape — no `direct_targets`, no bystanders, no narration
requirement, no Lex severity beyond the item's own tags. Folding them in would force four
degenerate 4-role payloads. See ITM-Q2 for the alternative that was rejected.

### 8.3 Equip semantics

1. Resolve `def.equip` — `None` ⇒ `item.not_equippable`.
2. Resolve target slot: explicit `slot` if given (must equal `equip.slot`), else `equip.slot`.
3. Compute the occupied set = `{equip.slot} ∪ equip.also_blocks`.
4. **Implicit unequip:** any item currently in the occupied set is unequipped first, in the same
   atomic write. Unequipped items stay `HeldBy` — they are not dropped.
5. Write the primary `SlotAssignment` + one `blocked_by_primary: true` assignment per blocked slot.
6. Emit `EVT-T3 Derived { aggregate_type: "actor_equipment" }` — this bumps `equipment_version`, which
   is what invalidates DF07's cached stat block (§6.3).

Steps 3–5 are one transaction. A two-handed equip that would block a slot it cannot free (V1: cannot
happen, since step 4 frees unconditionally) is reserved as `item.slot_occupied` for the V1+ cursed/
locked-gear case.

> **Capacity interaction — corrected at review 2026-07-26.** The first draft claimed step 4 was "safe
> at capacity because unequip doesn't change holding". That is **wrong under this feature's own
> accounting**: [PL_007b §4.1](PL_007b_inventory.md) counts *held-and-not-equipped* instances, so
> unequipping **increments** `slots_used`. Taken literally, an actor at capacity could neither unequip
> nor equip anything — a soft-lock reachable by ordinary play. Resolved in PL_007b §4.2 by the
> **over-encumbered** rule: unequip (explicit or implicit) is **exempt** from the cap and may push
> `slots_used` above it; being over the cap blocks *new acquisitions* until resolved. Rearranging what
> you already carry is never blocked.

### 8.4 Destroy & cascade — where the ends get tied

EF_001 §6.1 already specifies the holder-death cascade ("held items DROP TO GROUND: `HeldBy(holder) →
InCell(holder.last_cell_id)` AND lifecycle stays `Existing` — the items survive their owner").
PL_007 supplies the two pieces that cascade needed and did not have:

1. **A body to drop.** Ground items are `item_instance` + `entity_binding{InCell}`. Before PL_007
   there was nothing for the cascade to move.
2. **Equipment clearing.** The cascade MUST clear every `actor_equipment` slot of the dying actor in
   the *same* atomic batch, otherwise `actor_equipment` points at items now lying on the floor and
   ITM-C4 is violated. PL_007 registers a cascade hook for this (§12.1) — this is the concrete
   consumer that EF_001 §6.1's "future Item" placeholder anticipated.

Charge exhaustion: `charges: Some(0)` + `consume_on_exhaust: true` → `Existing → Destroyed` in the
same commit as the `Use` that spent the last charge, with `causal_ref` to that Use event.

**Item-side clearing (added at review 2026-07-26 — the mirror case the first draft missed).** §8.4
originally covered only the *holder* transitioning. The reverse is equally reachable: an **equipped
item** transitions to `Destroyed`/`Removed` on its own — a wand equipped in `main_hand` spends its last
charge, a `Forge:DestroyItem` on worn armour, a V1+ Strike-on-Item shattering a shield. In every such
case the item's slot(s) MUST be cleared in the **same transaction** as the lifecycle write, for exactly
the ITM-C4 reason: otherwise `actor_equipment` references a destroyed entity, and DF07's
`equipped_modifiers` would keep applying a destroyed item's bonuses until something else happened to
bump `equipment_version`. Stated as a rule so it is not left to the implementer:

> **Any transition of an item to `Destroyed` or `Removed` clears every `actor_equipment` slot holding
> it, in the same transaction, and bumps `equipment_version`.** Symmetric with the holder-side cascade
> above. Multi-slot items clear their primary *and* `blocked_by_primary` rows together (AC-ITM-14).

### 8.5 The loot seam (NOT the loot module)

> **Update 2026-07-26 (same day):** that module landed —
> [`COMB_004 Loot & Spoils`](../18_combat/COMB_004_loot_and_spoils.md) was written against this seam and
> confirms it needed **no PL_007 schema change and no new inventory surface** (its closure items 2 and 3).
> `ItemOrigin::Loot` is promoted to V1 active accordingly (§4.3). The paragraph below stands as the
> handover contract.

AUD-F9 names loot/drops as a separate missing module. PL_007 deliberately does **not** design it, and
instead states what it hands over: after a combatant dies, its former possessions are ordinary
`Existing` items with `location = InCell(death_cell)`, and its `actor_equipment` is empty. A loot
module therefore needs only an *interaction* (a `Loot` kind, or a corpse `Container` under ITM-D3) and
a *reward-generation* rule (`ItemOrigin::Loot` is already reserved). No PL_007 schema change.

### 8.6 Item actions vs combat state

COMB_001 §3 fixes the in-combat `allowed_tools` set to **Strike · Defend · Skill · UseItem · Flee**,
and COMB-V1 validates "intent-valid-in-`CombatActive`". The four `Item:*` sub-types are **not** in that
set, which leaves a question the first draft did not answer: can you swap weapons mid-fight?

> **V1 decision: no.** While the actor is in a `combat_session` with `state = Active`, `Item:PickUp` /
> `Item:Drop` / `Item:Equip` / `Item:Unequip` reject with COMB_001's `combat.action_invalid_in_state`
> (COMB's namespace, COMB's validator — PL_007 adds no rule_id for this and does not duplicate the
> check). **`UseItem` is the only item action inside combat**, exactly as COMB_001's action set says.
> You fight with what you are wearing.

Rationale, briefly: mid-combat swapping is a real RPG mechanic but it is an *action-economy* design
question (is a swap free? does it cost the turn's action? does it provoke?) and the action economy is
COMB_001/TG-A3's to own, not PL_007's. Shipping it unowned would mean each driver — Human UI, LlmDriver,
ScriptDriver — inventing its own answer. Reserved as **ITM-D22**, targeted at whichever COMB cycle
takes up the swap-cost decision. Out of combat, all four are ordinary turns.

### 8.7 Multiverse fork inheritance

Per the track convention every aggregate row states this: on a snapshot fork (MV4/MV6),
`item_instance` and `actor_equipment` rows are **copied bit-exactly**, alongside the `entity_binding`
rows they pair with (ITM-C3 holds across the fork because both sides copy together).
`provenance.created_at_turn` and `created_by` are preserved — a forked sword remembers being forged in
the parent, which is the correct fiction. `item_defs` live in the `RealityManifest`, so a
`Forge:EditItemDef` after the fork is **local to the reality that made it** (standard L3-scope
discipline); the child and parent may diverge on what "iron_sword" means, and instances in each resolve
against their own reality's def. No cross-reality item references (EF-D6).


---

## Continued in `PL_007c` — sections §9–§19

The contract and integration half of this feature lives in
[`PL_007c_integration.md`](PL_007c_integration.md), which **continues this file's section numbering**:

| § | Content |
|---|---|
| §9 | Validators (ITM-V1..V13) · `item.*` rule_id ledger · consistency rules ITM-C1..C11 |
| §10 | Event-model mapping (4 EVT-T1 · T4 · T3 · T8 · V1+30d T5) |
| §11 | `RealityManifest` extensions |
| §12 | Cross-feature integration + 13 closure-pass-extensions |
| §13 | Sequences |
| §14 | Acceptance criteria AC-ITM-1..23 |
| §15 | Deferrals ITM-D1..D23 |
| §16 | Open questions — all resolved |
| §17 | Cross-references |
| §18 | Readiness checklist |
| §19 | Review-pass findings ledger (2026-07-26) |

Inventory is [`PL_007b_inventory.md`](PL_007b_inventory.md) (ITM-A8/A9, AC-INV-1..13).
