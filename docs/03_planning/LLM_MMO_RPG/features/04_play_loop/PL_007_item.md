# PL_007 — Item Foundation

> **⚠ ROT SWEEP APPLIED 2026-08-02 — this file predates the actor round and the item round, and parts of it
> are now wrong rather than merely dated.** Authority moves to
> [`docs/specs/2026-08-02-item-data-structure.md`](../../../../specs/2026-08-02-item-data-structure.md)
> (decisions `ITD-1..ITD-11`, rot ledger `IR-1..IR-30`) and
> [`docs/specs/2026-08-02-item-dataflow.md`](../../../../specs/2026-08-02-item-dataflow.md) (Part II is the
> specification: declaration surface, runtime shapes, the closed 12-operation set, the validator ladder).
> **Where this file and those disagree, they win.**
>
> **What changed, in one line each — each is marked in place below:**
> - **`ITM-A2` is replaced** (`IR-1`): stackability is **earned by the data**, not declared by the author.
> - **`ITM-A3` names a condemned type** (`IR-2`): `StatSlot` is being dismantled (`D-10`/`D-100`/`D-105`).
> - **§6.3's `EquipmentStats` impl is deleted** (`IR-9`): a contribution is **DATA, never CODE** (`D-27`).
> - **`ITM-C4` is deleted** (`IR-6`): the contradiction it resolves does not exist once residency leaves
>   the existence axis.
> - **A second axis arrives**: ownership is separate from location (`ITD-1`), so `HeldBy` stops meaning
>   *"owns"*.
>
> **What SURVIVES, and is now cited as a model rather than merely kept:** `ITM-A5` (equipment is a slot
> assignment, not a location) · §8.6 (no weapon swap in combat) · §6.4's finding that two features declared
> an operand neither could evaluate · §8.5's loot **seam** · the review discipline of §12 (`PL_007c`:556
> called out its own two latent defects, which is why they cost a paragraph rather than a debugging
> session).

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
> 2026-07-26, same day, in parallel) — ⚠ **this dependency is WITHDRAWN 2026-08-02** (`IR-2`, `IR-9`):
> DF07's closed `StatSlot` set is being dismantled (`D-100`/`D-105`/`C-2a`), and the `EquipmentStats` body
> §6.3 shipped is deleted in favour of modifier **rows** (`D-27`). What remains of the relationship is the
> **fold**, which the engine owns and neither feature implements.
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
| **ItemDef** | Author-declared template in `RealityManifest.item_defs` — **a `D-74` kind ① ROSTER** (`IR-12`) | System-tier, read-only at runtime, admin-editable via Forge. The blueprint: class, affordances, equip decl, use effect, price, lex tags. **The structure is ours, the members are the author's** (`D-75`): a new feature declares a *member*, never adds a *field*. Addressed by **opaque id, never an ordinal** (`D-76`) — which is why item creates **zero** new ordinal spaces. |
| **ItemDefId** | `pub struct ItemDefId(pub String)` | English `snake_case` stable ID per RES_001 §2 i18n contract (e.g. `iron_sword`, `minor_heal_elixir`). |
| **item_instance** | T2/Reality aggregate (§4.1) | The runtime thing: which def, how many charges left, where it came from. **Location is NOT here** — it lives in `entity_binding` (EF_001 owns). |
| **ItemInstanceId** | `pub type ItemInstanceId = ItemId;` | **Alias, not a new type.** Resolves the EF_001/RES_001 spelling drift — see ITM-C1 (§9.4). `EntityId::Item(ItemId)` stays the canonical spelling. |
| **ItemClass** | Closed enum — 8 V1 (§5.2) | `Weapon \| Armor \| Trinket \| Consumable \| Tool \| Key \| Document \| Valuable`. Drives default affordances + the digest grouping (PL_007b §5). |
| **actor_equipment** | T2/Reality sparse aggregate (§4.2) | Per-actor slot → instance map. **Not** a location: an equipped item is still `HeldBy(actor)` (ITM-A5). |
| **EquipSlotId** | `pub struct EquipSlotId(pub String)` | Author-declarable with a 6-slot engine default (§6.1). |
| **StatModifier** | **DF07-owned type** — `{ slot: StatSlot, op: ModifierOp, value: i32, source: ModifierSource }` | What an item *contributes*. PL_007 **produces** these with `source = ModifierSource::Equipment(entity_id)`; it does not define the type and does not resolve it (§6.3). |
| **InstrumentTag** | `pub struct InstrumentTag(pub String)` | Author-declared weapon/tool category (`"blade"`, `"spear"`, `"bow"`). The operand that makes PROG_001 `instrument_match` and DF07 `StatTerm.instrument_match` evaluable against a wielded item — and **resolves PROG-D15** (§6.4 / ITM-C7). |
| **UseEffectDecl** | `= EffectOp` — **ABL_001-owned** closed enum (ABL-Q9/Q10); PL_007 declares the item-legal subset (§7.1) | The bounded vocabulary of what `Use` can do. PL_007 invents no effect substrate and, post-merge, does not own the vocabulary either. |
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

> **ITM-A2 — ⚠ REPLACED 2026-08-02 by `ITD-2` (`IR-1`). Stackability is EARNED, not declared.**
>
> **The rule now:** a thing with **no per-instance state** is a **QUANTUM** — one row
> `(owner, location, def_id, count)`, **no row per unit**. A thing that **acquires** per-instance state
> becomes an **INSTANCE** with an id. **The transition is an operation** (`assemble` / `repackage`),
> **not a declaration.** One store, two shapes.
>
> **Why the original was wrong, recorded rather than overwritten.** It read: *"exactly one representation
> per thing, chosen by the author at declaration time; never both"*, with fungible value staying in RES_001
> `resource_inventory`. That asks an author to predict which of their items will ever need identity — and
> **this feature already recorded the resulting hole itself**, calling a merchant's 50 identical daggers
> *"the awkward middle"* (PL_007b §2) and deferring it to ITM-Q3 / ITM-D1. It is not awkward; it is the
> wrong question. EVE Online has run the correct answer for two decades: a **packaged** item has *"only 3
> attributes: location, item type and quantity"*, while an assembled one *"can no longer be stacked,
> because it is no longer identical to every other."*
>
> **The tell was in this feature's own enforcement.** ITM-V10 / ITM-C2 exist **only** to police the
> `item_defs` ∩ `resource_kinds` boundary that ITM-A2 invented. **A validator whose entire job is to police
> a boundary you created is evidence the boundary should not exist** — the same argument `D-27` used to
> delete the plugin registry and `D-29` used to delete the predicate grammar. Both checks are withdrawn
> (`IR-18`).
>
> **The static half is a load-time check, and Minecraft ships it:** `max_stack_size > 1` may not combine
> with `max_damage`. Ours: `instance_state` non-empty ⇒ `max_stack == 1`. See item-dataflow §14.4.

> **ITM-A3 — Items carry modifiers, never stats.** ⚠ **AMENDED 2026-08-02 (`IR-2`, `IR-8`) — the
> principle survives; both of its nouns are condemned.**
>
> **Surviving:** an `ItemDef` never stores a stat value; it declares what it **contributes**, and the
> engine owns the fold. That half was right and is now `D-27`'s general law.
>
> **Withdrawn — the closed `StatSlot` target.** The original read *"`Vec<StatModifier>` against the closed
> DF07-owned `StatSlot` enum (10 V1 slots)"*. `D-10` opened the slot set; `D-100` measured it to be
> **combat's** vocabulary living in the engine core; `D-105` found it is **two concepts sharing one array**
> (slots 0-1 are pool ceilings, 2-7 are combat law inputs) and `C-2a`/`C-2b`/`C-2c` are dismantling it.
> **An item design that names `StatSlot` is building on a condemned structure.**
>
> **Withdrawn — the trait.** *"PL_007 implements DF07's `EquipmentStats` trait and nothing more"* is
> deleted by `IR-9`; see §6.3.
>
> **Replacement:** an item declares `Vec<ModifierTemplate>` whose `target` is a **`QuantityOrdinal` the
> reality declared**, and equipping writes `ModifierRow`s through `commit_with_modifiers` (`D-50`). Shape
> in item-dataflow §14.5.

> **ITM-A4 — LLM-zero-item-math** (extends COMB-A1 LLM-zero-math and TG-A1 LLM-zero-space). The LLM
> selects *which* item from the bounded held set (AGT-A2) and *what* to point it at. It never emits a
> heal amount, a damage number, a durability value, a price, or any `ItemDef` field. `Item:*` and
> `UseItem` payloads carry an `ItemInstanceId` + an optional target and nothing numeric. A payload
> carrying an out-of-set instance or an engine-owned number is rejected, not clamped.

> **ITM-A5 — Equipment is a slot assignment, not a location.** ✅ **SURVIVES INTACT 2026-08-02 (`IR-3`),
> and is now cited as the model.** An equipped item's `entity_binding.location` stays `HeldBy(actor)`;
> "equipped" is a row in `actor_equipment`. This preserves EF_001 §3.1's "an entity is in EXACTLY one
> place at a time" and adds **no fifth `LocationKind`** — the enum stays closed (EF_001 §5 "closed V1").
> Consequence: unequipping is a pure `actor_equipment` write with no binding delta, and a dropped item must
> be unequipped first (ITM-V12).
>
> **Why it is a model:** it makes a second location **unrepresentable** rather than merely invalid. That is
> the identical discipline `ITD-5` now applies to duplication — *"an entity is in EXACTLY one place at a
> time"* is not housekeeping, **it is the anti-duplication mechanism** (EF_001 §3.1 is relabelled
> accordingly, `IR-25`), and it converges exactly with OpenMU's post-mortem fix after MU Online's economy
> was destroyed by duping: *"there can only be one item with the same Id and only assigned to one
> account."*

> **ITM-A6 — ⚠ AMENDED 2026-08-02 (`IR-5`) — the posture survives as a NUMBER, not as a restriction.**
>
> The original made V1 holder graphs depth ≤ 1, *"which is why EF_001's `entity.cyclic_holder_graph` is
> **structurally unreachable** in V1 rather than merely untested."* **That sentence is the `NV-2` shape —
> *the scope never reaches it*.** A guard that cannot fire because nothing in scope can reach it is not a
> guard; it is coverage reported by a check that cannot fail.
>
> **Replacement:** a container is an item carrying an `Interior` slot (`SPG-A1` — *"a chest, a house, a
> ship, a planet and a cultivator at 神境 are then one construct, not five special cases"*), and depth is
> `ContainerDecl.max_depth`, an **authored number**. Setting it to 1 reproduces V1's posture exactly, and
> the guard becomes reachable the moment an author sets 2. Containment acyclicity is already guaranteed by
> `SPG-A4` via `DP-Ch1`'s parent-relation guard.
>
> ⚠ **This does NOT cover ownership.** `ITD-1` adds an owner edge, which is a **reference** edge, and
> `SPG-A5b` already records that *"a reference edge is not a parent edge and escapes that guard entirely."*
> **A owns B owns A is representable today with nothing to detect it** — tracked as `IO-2`, and its check
> is `V2-4`, which exists nowhere.

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
- **ITM-C4 — ⚠ DELETED 2026-08-02 (`IR-6`). The contradiction it resolves does not exist.**

  The rule said an equipped instance must satisfy `location == HeldBy(actor_ref)` **and**
  `instance.lifecycle_state == holder.lifecycle_state` — *"lockstep with the holder, not always
  `Existing`"* — and it was written carefully, at a review, to reconcile two halves of
  [EF_001 §6.1](../00_entity/EF_001_entity_foundation.md#61-cascade-rules) that appeared to disagree about
  whether items suspend.

  **Both halves were about `Suspended`, and `Suspended` is RESIDENCY, not existence** (`D-12`, actor
  dataflow §5.3 axis 3). Residency is engine-owned and governed by one law: **a movement on that axis must
  be INVISIBLE IN THE FICTION.** So *of course* a passivated actor's gear passivates with it, and *of
  course* the slot survives untouched — that is the residency cascade doing its job, and it must change no
  fiction-visible byte. There is nothing left to reconcile.

  **The location half survives** and moves into the equip validator (`V2-9`): an equip requires the item to
  be `HeldBy` the actor.

  > **This is the third time this project has hit the same shape**, and it is worth naming here because
  > this paragraph is a good example of it: a document spends its most careful reasoning reconciling two
  > rules that contradict each other, and the contradiction is **one field answering two questions**.
  > `LifecycleState` did it for actors (`Suspended` beside `Destroyed`); `HeldBy` does it for ownership
  > (`ITD-1`); `StatSlot` does it for stats (`D-105`). **The tell is identical every time — a correction
  > that is right, careful, and load-bearing for a distinction that should not have existed.**
- The slot is cleared only on the transitions that actually sever holding: holder `→ Destroyed` or
  `→ Removed` (§8.4), the item itself `→ Destroyed`/`Removed` (§8.4), and any location change away
  from `HeldBy(actor_ref)`.
- Sparse: an actor with nothing equipped has **no row** (mirrors ACT_001 `actor_chorus_metadata`).
  ⚠ The original second half — *"`equipment_version` for an absent row is 0, so DF07's `StatEpoch` has a
  defined input"* — is **withdrawn** (`IR-9`). There is no version and no cache to feed: an actor with no
  equipment simply has **no modifier rows**, and **absence is free** (`D-27`) — no null row, no sentinel,
  no registration. That is the same property that lets a feature contributing nothing need no opt-out.
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

> **⚠ AMENDED 2026-08-02 (`IR-7`) — these three fields are a DERIVED COPY, and one of them may be a
> deliberately lossy one.**
>
> Under `D-23` **canon is what is written to the ledger**, and the ledger already holds an item's entire
> history — `ItemBorn` carries the origin, `ItemOwnerChanged` carries every hand it passed through. So this
> struct is not a source; it is a **cache of the first ledger entry**, and `D-39`/`D-53` bind every derived
> copy to one rule: **rebuildable · carries the `(reality_id, seq)` it was taken at · discarded on
> divergence, never reconciled.** Add the `seq` or delete the fields. ITM-D7's own wording already had this
> right — *"a transfer ledger is an event-log query, not a field"* (`IR-21`) — so it is **promoted from a
> deferral to a decision.**
>
> **The one thing the row genuinely owes that the ledger does not.** Wurm Online burns the maker's name
> into an item as a **signature**, and the signature is **lossy in proportion to the item's own quality**:
> *"higher QL has a tendency toward giving a clearer signature, while unclear signatures have some letters
> of the name replaced by a dot."* That is not a cache — it is a **fiction-visible, deliberately degraded
> view** whose fidelity is itself a mechanic: good enough to recognise a master's work, not good enough to
> be proof. **A derived view may be intentionally lossy, and the lossiness may be content.** It becomes the
> `Signature` per-instance state slot (item-dataflow §14.4).

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

### 5.2 `ItemClass` — ⚠ NO LONGER A CLOSED ENGINE ENUM (`IR-4`, 2026-08-02)

> **The eight variants below become a declared ROSTER (`item_classes`), not an engine type.**
>
> `D-98` supplies the discriminator that decides this, and it is measurable rather than stylistic: **a
> closed set is MECHANISM if the engine's arithmetic DIFFERS PER MEMBER; it is A FEATURE'S VOCABULARY IN
> COSTUME if the engine treats members uniformly and only one feature knows their names.** The engine's
> arithmetic does not differ per `ItemClass` — **the engine never reads the class at all.** Only this
> feature does, for affordance defaults and digest grouping.
>
> **The cost of leaving it closed is the wall all four author agents hit one tier up** (`D-82`): a reality
> whose things are `talisman`, `pill`, `spirit-stone` and `manual` must spell them `Trinket`, `Consumable`,
> `Valuable`, `Document`. And `06_item_contract.md`:64 states the closure as a rule to the generator —
> *"engine-fixed, 8 variants. A reality cannot add a 9th"* — which is where an author would actually hit
> it (`IR-28`).
>
> **The table below survives as the ENGINE-DEFAULT roster** — the same shape RES_001 §3.5 uses for default
> kinds, and PL_007 §6.1 for the 6-slot equip profile: shipped members an author may extend or replace,
> not a type they cannot move.
>
> ⚠ **Counter-evidence, kept in view so this is not read as *"open is better"*:** `D-109` measured chaos's
> `dimensions.yaml` — one flat global list of ~60 stat names, feature-grouped **in comments only**, with
> **zero readers**. *"Opening a god-list does not decouple it — it removes the compiler's ability to notice."*
> **The coupling is fixed by OWNERSHIP (whose part declares the row), not by openness.** `item_classes`
> belongs to the item feature's part; it is not a free-for-all global.

#### The 8 V1 default members

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

> **⚠ `modifiers` RETYPED 2026-08-02 (`IR-8`).** `Vec<StatModifier>` becomes `Vec<ModifierTemplate>` —
> `{ target: QuantityOrdinal, op, magnitude (fixed-point 1e-4, `D-52`), layer, condition:
> Option<ThresholdOrdinal> }`. The `actor` and `source` fields are **not authored**; the commit supplies
> them (`D-50`), which is what makes removal mechanical (`DELETE WHERE source = …`) and *"why is my attack
> 47"* answerable. Full shape: item-dataflow §14.5.
>
> **`requirements` survives unchanged, and the distinction is worth stating because the two look alike:**
> an **equip requirement** is checked **once, at the commit**, and refuses the equip. A modifier's
> **`condition`** is a **declared threshold ordinal** evaluated **every tick** — one bit test in
> `threshold_active` (`D-29`). Collapsing them would either make requirements a per-tick cost or make
> conditions a scripting language, and `D-29` refused the second explicitly.

```rust
pub struct EquipDecl {
    pub slot: EquipSlotId,                      // primary slot
    pub also_blocks: Vec<EquipSlotId>,          // two-handed sword: [off_hand]
    pub modifiers: Vec<ModifierTemplate>,       // IR-8 — NOT StatModifier. Applies WHILE EQUIPPED (§6.5)
    pub requirements: Vec<EquipRequirement>,    // V1: progression-gated only. Checked ONCE, at commit
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

### 6.3 The DF07 seam — ⚠ **DELETED 2026-08-02 (`IR-9`, `IR-10`). Equipment is ROWS, not a trait.**

> **What was here.** ~65 lines implementing `EquipmentStats for World` — `equipped_modifiers(actor) ->
> Vec<StatModifier>` and `equipment_version(actor) -> u64` — presented as *"the one thing PL_007
> implements"*, discharging DF7-D1 with zero DF07 change.

**Why it is deleted rather than retyped.** Read that impl as an implementation and it means: **during the
tick, feature code runs.** Which requires the engine to call into features, which requires the engine to
hold a list of features — `D-2` violated at the worst possible layer, because *the engine is an
environment; it fixes the operations, never the nouns.* `D-27` generalises `CPL-A17` to close it:

> **A contribution is DATA, never CODE. A feature does not run during the tick; it leaves ROWS, and the
> engine folds rows.**

**The replacement, end to end:**

```
EQUIP jian_001 into main_hand -- ONE commit, via commit_with_modifiers (D-50):
  actor_equipment[LM01].main_hand = jian_001         <- this feature's own table
  actor_equipment[LM01].off_hand  = jian_001 (blocked_by_primary)
  modifier_rows += { LM01, ord(attack), Flat,   +10, layer=Equipment,
                     condition=None, source=(ITM, equip#4471), expiry=None }
  modifier_rows += { LM01, ord(speed),  Percent, +5, layer=Equipment,
                     condition=None, source=(ITM, equip#4471), expiry=None }

NEXT TICK, phase 0: the engine folds LM01's rows into values[].
                    It has not learned that swords exist.

UNEQUIP / DESTROY / HOLDER DIES -- ONE commit:
  <the feature-table change>
  DELETE modifier_rows WHERE source = (ITM, equip#4471)
```

**Three defects this section documented DISSOLVE rather than get fixed** — and that is the test showing the
change is structural, not stylistic:

| the defect, as this file recorded it | what happens to it |
|---|---|
| **the `blocked_by_primary` double-count** — a two-handed weapon occupies two slots with the *same* instance, so naive iteration applies its modifiers **twice**; *"this is why `blocked_by_primary` exists as a field rather than being inferred"* | **gone.** The rows are written **once**, at commit. There is no iteration to double-count. The field survives for its honest job: making unequip a single-key operation |
| **`equipment_version` monotonicity (ITM-Q1)** — *"a same-turn equip→unequip→equip sequence would not bump `last_modified_at_turn`… V1 is safe because one action per turn"* | **gone.** A correctness argument resting on a turn-economy accident. Nothing is derived at read time, so nothing needs invalidating — and the question stops existing rather than being answered |
| **the item-side destroy cascade** (§8.4, review finding 3) — *"`actor_equipment` would reference a destroyed entity and DF07 would keep applying its modifiers"* | **gone.** Destroying the item removes its rows in the same commit, **by signature** (`D-50`), not by a rule an implementer must remember |

**Staleness becomes impossible, not detectable** (`D-28`): the modifier row is written and removed in the
**same commit** as the feature row that justifies it. There is no sync step to forget because there is no
second step. **This feature had already found the shape by hand once** — `PL_007c` §8.4's equipment
clearing runs *"**inside** the `EF_001` HolderCascade atomic batch, **not after it**"* — and
`commit_with_modifiers` makes it the only expressible form.

**What this does to the ownership split table that was here:** it collapses. DF07 no longer owns a slot
vocabulary this feature references (`D-100`/`D-105`), and this feature no longer implements anything DF07
calls. The engine validates a row's **shape** — target is granted, op is in the closed set, layer is
declared, condition names a declared threshold — **and never asks what the source means.**

**Acceptance test, and it passes:** adding this feature touches **zero files** in actor core (`D-30`) — no
struct field, no reserved ordinal, no registry entry, no projector edit, and `size_of::<ActorQuantities>()`
does not move.

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

**Resolution depends on the consumer, and PL_007 does NOT define one global rule** — the first draft did,
which would have changed PROG_001's training semantics by side effect (`ItemClass::Tool` is never
equippable, so an equipped-only rule kills every "train X while using tool Y" rule). PL_007 supplies the
vocabulary and the tags; each consumer resolves its own subject:

- **PROG_001 training rules** → the **turn's instrument** (`tools[0]`), its existing semantic, unchanged.
- **DF07 `StatTerm`** → the **`main_hand`-equipped** item (`off_hand` V1+ per ITM-D19).

The authoritative per-consumer table now lives in **[PROG_001 §training's closure-pass note](../00_progression/PROG_001_progression_foundation.md)**
(where a future PROG editor will see it) and in [DF07_001 §6.1](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md),
which reached the same conclusion independently with a stronger reason: it keeps the instrument inside
`StatEpoch.equipment_version` rather than being a hidden per-action input the snapshot cannot see.

> ⚠ **2026-08-02: the conclusion survives, its reason does not** (`IR-9`). `StatEpoch.equipment_version`
> is gone with the cache it invalidated. The **finding** this section makes is the durable part and is
> independent of it: two features declared an operand — PROG_001's `InstrumentMatch::Specific(ResourceKind)`
> and DF07's `Some(Blade)` — that **neither could evaluate**, and it was invisible from either document
> alone. That kind of finding is one only a third document can make. The mechanism must be respelled (it
> may not name `ResourceKind`, withdrawn by `PL_007c` §12.2, nor a closed `StatSlot`); `instrument_tags`
> survives as a field on the def (item-dataflow §14.3), and the per-consumer resolution table stays where
> it is.

Tags are author-declared rather than a closed enum, for the same reason RES_001's kinds are: a wuxia
reality's weapon taxonomy is not a sci-fi reality's. ITM-C7 warns at bootstrap on an unreferenced tag.

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

### 7.1 Use effects — the item-legal subset of ABL's `EffectOp`

> **⚠ CLOSURE-PASS-EXTENSION 2026-07-26 (combat family / ABL-Q9) — `UseEffectDecl` retires into
> `EffectOp`:** `pub type UseEffectDecl = EffectOp;`. `ItemDef.use_effect` keeps its shape; only the type
> it names moves, and **ABL_001 §4.1 owns the vocabulary** (ABL-Q10). Forced by a **defect, not tidiness**:
> the two enums had already diverged in one day, and `VitalDelta { amount: i32 }` was *signed* — a
> damage-law-chain bypass that ignored `Armor`, the hit roll, COMB_003 threat, COMB_001 Q4's disparity cap
> and COMB_006's PvP predicate. **Full note, verbatim, with the fix and what PL_007 gains:**
> [`PL_007c §12.14`](PL_007c_integration.md). Relocated there because the §12 table is where this track
> keeps closure-pass extensions — and because PL_007 was over its 800-line cap.

PL_007 adds no new effect substrate — it is a dispatch vocabulary, which is what keeps it bounded for
AGT-A2. **But the first draft's blanket claim that "every variant routes to an aggregate already owned
by another feature" was false for two of the seven, and the correction matters because it changes what
a player experiences.** Corrected at cold-start review 2026-07-26:

| Variant | V1 durable sink | Status |
|---|---|---|
| `VitalRestore` (was `VitalDelta`) | RES_001 `vital_pool` | ✅ real |
| `Damage` | RES_001 `vital_pool` **via COMB_001 §4's chain** | ✅ real (post-merge capability) |
| `StatusApply` / `StatusDispel` | PL_006 `actor_status` | ✅ real |
| `ResourceGrant` | RES_001 `resource_inventory` | ✅ real |
| `Inert` | — (none by design) | ✅ honest by construction |
| `Unlock` | **none** — §7.3: "validate the key, log the unlock, narrate it, **mutate nothing**"; blocked on the unwritten EnvObject body | ⚠️ **narrative-only V1** |
| `Reveal` | **none** — PL_005b §5.6 places `KnowledgeAccrual` at "V1+ when PCS_001 `knowledge_tags` ships"; the Oracle read is a query, not a write | ⚠️ **narrative-only V1** |

Both **pass ITM-V8** and return **success with no state change** — indistinguishable from a bug to a
player, unassertable to QA. So V1 declares it rather than leaving it to be discovered:

> **Narrative-only effects must be declared, not discovered.** `Unlock` and `Reveal` resolve to an
> **accepted turn carrying the `item.use_effect_narrative_only` warning** (same warning-on-accept shape as
> `item.inventory.cap_partial`), so the audit log records a Use that succeeded with no durable delta and
> the narrator describes an outcome rather than implying a persistent world change. An author wanting a
> *mechanical* lock models it as `StatusApply`/`ResourceGrant` until the EnvObject body lands (ITM-D4).

Consequence for §5.2's class table: **`Key` is narrative-only in V1** (its only sensible effect is
`Unlock`), and `Document` is too unless given `ResourceGrant`/`StatusApply` instead of `Reveal`. Both
classes still ship — display name, description, Examine text, Give/trade, digest grouping are real
content — but neither has a mechanical effect until ITM-D4.

**The variant list itself is no longer declared here** — it is `EffectOp`, owned by
[ABL_001 §4.1](../19_ability/ABL_001_ability_foundation.md) (ABL-Q9/Q10, per the closure-pass note above).
PL_007 declares only *which* ops an item may carry and the discipline around them:

- **Item-legal subset.** `VitalRestore` · `StatusApply` · `StatusDispel` · `ResourceGrant` · `Unlock` ·
  `Reveal` · `Inert` · **`Damage`** (new capability — the explosive talisman the 7-variant enum could not
  express except through the bypass). ABL-only ops (`ModifyThreat`, `ForceMove`, `SeverBinding`) are not
  item-declarable in V1.
- **`VitalRestore.amount` is `u32`** — harm is unrepresentable by type on this path. Any item that
  *reduces* another actor's vitals declares `Damage { power: PowerTerm }` and goes through COMB_001 §4's
  chain. This is what closes the bypass, and it is the same *unrepresentable-not-merely-invalid*
  discipline as ITM-A5 (equipment is a slot assignment, so it cannot be a second location).
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

`Unlock` matches `key_tag` against an EnvObject's declared lock tag, and **there is no runtime EnvObject
state aggregate** — PL_005b §6.3 is explicit that state transitions are simulated in the audit log "until
V1+ Item substrate ships". **PL_007 shipping does not discharge that**: the missing half is the
**EnvObject body**, which EF_001 §Defers-to assigns to a separate future feature, not to this one. V1
behaviour is therefore unchanged — validate the key, log it, narrate it, mutate nothing (ITM-D4, blocker
named).

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

> **⚠ THE TABLE ABOVE IS ONE AXIS DOING THREE JOBS — corrected 2026-08-02 (`IR-11`).**
>
> `D-12` and actor dataflow §5.3 split lifecycle into **four orthogonal axes**, and an item uses three:
>
> | axis | closed by | for an item |
> |---|---|---|
> | **1 · Tier** | engine | `Untracked · Declared · Stateful · Irreversible` — a generic coin in a crowd's pocket is `Untracked` until someone looks (`ONT-D1`'s attention-promotes) |
> | **2 · Existence** | **the author** | the declared vocabulary — `intact`, `broken`, `consumed`, `destroyed`, `lost`. `Existing`/`Destroyed`/`Removed` below are **one reality's members**, not the engine's type |
> | **3 · Residency** | engine, **fiction-INVISIBLE** | `Active · Passivated · Evicted`. **`Suspended` belongs HERE**, and that is what deletes `ITM-C4` (§4.2) |
> | **4 · Control** | — | **EMPTY. Nothing drives an item.** Recorded as evidence the axes are orthogonal rather than a bundle: four were derived from the actor, and the second subject needs three |
>
> **So the two `HolderCascade` rows below — `Existing → Suspended` and `Suspended → Existing` — are not
> transitions at all.** They are the **residency cascade**, engine-owned, and by the invisibility law they
> must change **no fiction-visible byte**. The rest of the table survives as this reality's axis-2
> vocabulary and its transition triggers.
>
> **The control axis is safe to leave empty rather than reserved** because control is a **relation**
> (`D-77` — `control_binding`, a pair table, not a field), so an item that later gains a controller — a
> cursed blade, a bound spirit, `TVL_003`'s mounts — adds **rows**, not a schema change.

**Suspension: cascade-only, never independent (corrected at cold-start review 2026-07-26).** ⚠ **The
correction below is right and its subject moved** (`IR-11`): both halves are about `Suspended`, which is
**residency**, so there was never a contradiction to resolve — see the axis table above. Kept because the
reasoning is a clean worked example of the failure mode, and because EF_001's two halves still say what
they say. The earlier flat claim *"items never go `Suspended` in V1"* was **wrong**, and it contradicted
this doc's own ITM-C4 (§4.2), which requires an equipped item's lifecycle to move in **lockstep with its
holder**. Both statements cannot hold. EF_001 is the arbiter and says both halves precisely:

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
6. ⚠ **REWRITTEN 2026-08-02 (`IR-9`).** Write the `ModifierRow`s for every modifier the equipped def
   declares — **in the same commit as steps 4-5**, via `commit_with_modifiers(feature_row, modifiers)`
   (`D-50`). There is no version to bump and no cache to invalidate. Emit `EVT-T3 Derived
   { aggregate_type: "actor_equipment" }` as before, for subscribers.

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
bump `equipment_version`.

> ⚠ **2026-08-02 (`IR-9`): this defect DISSOLVES, and the rule that fixed it is no longer needed as a
> rule.** It was: *"any transition of an item to `Destroyed` or `Removed` clears every `actor_equipment`
> slot holding it, in the same transaction, and bumps `equipment_version`"* — correct, and it had to be
> **stated so an implementer would not forget it.** Under `D-50` the destroy passes its modifier deletions
> through the same `commit_with_modifiers` call, so **there is no second step to forget because the API
> offers none**: atomicity becomes a *signature* rather than a rule.
>
> **This finding is why the deletion is cheap.** It was caught at a 2026-07-26 review (`PL_007c` finding 3)
> rather than in production, which is the whole argument for the review discipline this feature ran. What
> survives is the **shape** — multi-slot items clear their primary *and* `blocked_by_primary` rows together
> (AC-ITM-14) — restated as a precondition of the commit rather than as an obligation on a human.

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
