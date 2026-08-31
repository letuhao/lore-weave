# PL_007b — Inventory & Capacity

> **Continued from:** [`PL_007_item.md`](PL_007_item.md). That file holds the item **substrate**
> (def/instance split, equipment slots, use effects, the four `Item:*` actions). This file holds the
> **inventory** half: how the two storage representations compose into one player-facing inventory,
> how capacity is accounted, how the LLM sees an inventory at flat token cost, and how ground items
> work. Read PL_007 first — this file assumes ITM-A2 (the representation rule).
>
> **Conversational name:** "Inventory" (INV). Same feature, same `ITM-*` namespace — PL_007b adds
> `ITM-V14..V17`, `ITM-D13..D18`, `ITM-Q6..Q8`, and the `item.inventory.*` rule_id sub-namespace.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** **DRAFT 2026-07-26** — closes the audit's *"Inventory — 🟡 partial"* row
> ([`12_module_coverage_audit.md`](../../12_module_coverage_audit.md) §2) and activates the two
> schema reservations that were left pointing at each other: EF_001 `entity_binding.inventory_cap`
> (Q6b) and RES_001 RES-D2.
> **Builds on:** PL_007 (all of it) · RES_001 §4.2/§6/§7.4/§8 (`resource_inventory`, production,
> harvest, trade) · EF_001 §3.1 (`inventory_cap`, `HeldBy`/`InCell`) · CSC_001 (placeable tiles) ·
> S9 prompt assembly (`AssemblePrompt`) · TG-A1 / COMB-A1 (the flat-token-cost family of axioms).

---

## §1 Why this exists

"Inventory" was marked partial rather than absent because **pieces of it exist in three places, and
no document says how they compose**:

| Piece | Where it lives | What was missing |
|---|---|---|
| Fungible balances (currency, food, materials) | RES_001 `resource_inventory.balances` | nothing — this half works |
| Held things with identity | EF_001 `entity_binding{HeldBy}` — and AC-EF-10 says the inventory *is* this read-view | no body behind `EntityId::Item` (PL_007 fixes) and no defined read-view |
| A capacity limit | EF_001 `inventory_cap: Option<CapacityProfile>` — "V1: ALWAYS None" | what a "slot" counts; what happens at the boundary |
| The promised V1 bloat mitigation | EF_001 §3.1: *"LLM context bloat mitigated V1 via AssemblePrompt summarization (top-N entries per kind)"* | one sentence, no contract, no bound |

So an implementer asking "what does the player's inventory panel read, and what does the LLM see?"
had no answer. Three concrete consequences that this file removes:

1. **Two candidate sources of truth.** RES_001 reserved `ResourceKind::Item` + `instance_id`, EF_001
   said the inventory is a binding read-view. PL_007 ITM-A2 picked the binding; §2 here states the
   authoring consequence and §12.1 the withdrawal.
2. **Unbounded LLM context.** An actor with 200 held items would put 200 lines into every
   `AssemblePrompt` call — the same cost failure mode COMB_001 §139 raised for grid narration and
   TG-A1 dissolved. §5 applies the identical fix: a **fixed-size** digest.
3. **No boundary behaviour.** With items now instanced, "inventory full" becomes reachable. §4
   defines the accounting and — the part that is usually wrong — what a *partial* transfer does.

---

## §2 The two representations in practice

> **⚠ ROT SWEEP 2026-08-02 (`IR-14`) — the premise of this section is replaced.** `ITM-A2` is superseded
> by [`ITD-2`](../../../../specs/2026-08-02-item-data-structure.md): **stackability is EARNED by the data,
> not declared by the author**. There is **one store with two shapes** — a **quantum**
> `(owner, location, def_id, count)` with no row per unit, and an **instance** with an id — and a thing
> moves between them by an *operation* (`assemble` / `repackage`), not by a declaration made once and
> forever.
>
> **This section is why.** It is the document that identified the hole, in its own words: a merchant's 50
> identical daggers are *"the awkward middle"*, deferred to ITM-Q3 / ITM-D1. **Both close as ANSWERED, not
> deferred** — packaged, they are one row with count 50; a buyer assembles one and it becomes theirs. The
> table below survives as an accurate description of the **two shapes**; what changes is **who decides,
> and when**. `ITM-V10` / `ITM-C2` are withdrawn with the boundary they policed (`IR-18`).

Per PL_007 ITM-A2 *(superseded — see above)*, every valuable thing in a reality is **either** a fungible
balance **or** an instanced entity, chosen by the author at declaration time and enforced at bootstrap
(ITM-V10).

| | Fungible — `resource_inventory` | Instanced — `entity_binding` + `item_instance` |
|---|---|---|
| Declared as | `resource_kinds: [ResourceKindDecl]` (RES_001 §3.4) | `item_defs: [ItemDefDecl]` (PL_007 §5) |
| Identity | none — 40 copper is a number | each has an `ItemInstanceId` |
| Stored as | one row per (owner, kind) with `amount: u64` | one entity row + one instance row each |
| Can be equipped | no | yes, if `def.equip.is_some()` |
| Can carry charges / durability / provenance | no | yes |
| Can be a `Use` tool | no (consumed by Generators + trade) | yes |
| Location model | owner `EntityRef` on the inventory row | `EntityLocation` (HeldBy / InCell / InContainer V1+30d) |
| Cost per unit at scale | **O(1)** — one row for any amount | **O(n)** — one entity per unit |

**Authoring guidance (the decision an author actually faces).** Ask: *does any single one of these
need to differ from another?* Rice does not — 5 rice is 5 rice → fungible. A sword with 3 remaining
charges, a provenance, and an equip slot does → instanced. Merchant stock of 50 identical daggers is
the awkward middle: declare it fungible (`Valuable`/`Material` kind, sold as a number) unless
individual daggers must be equippable and traceable. This tradeoff is measured, not assumed —
ITM-Q3 / ITM-D1.

> **ITM-A8 — ⚠ AMENDED 2026-08-02 (`IR-15`): ONE store, two SHAPES — and the projection half survives.**
>
> **Withdrawn:** *"one inventory, two stores"*. The union projection existed **because the two stores had
> different identity models** — a `ResourceBalance` keyed by `(owner, kind)` and an entity keyed by an id.
> Under `ITD-2` they are two shapes of one row, so there is nothing to union across.
>
> **Survives, and is the durable half:** the player-facing inventory is a **projection, never an
> authoritative aggregate**; nothing may write *"the inventory"*. That is `P-F`/`D-39`'s rule for every
> derived copy — *rebuildable · carries the `(reality_id, seq)` it was taken at · discarded on divergence,
> never reconciled* — and it now applies with the `seq` requirement `D-53` adds.
>
> **Also survives, restated:** *"nothing may introduce a third store"*. Under `ITD-1` the **owner** is a
> second field on the same row, not a second store — and §3's read-view gains the query it could never
> express: *what am I carrying that is not mine?*

---

## §3 `actor_inventory_view` — the derived union

```rust
/// T1 / read-side projection. NOT an aggregate — never written directly, never a source of truth
/// (ITM-A8). Rebuildable at any time from the two stores; per DP-A19 ≤1s projection lag applies.
pub struct ActorInventoryView {
    pub owner: ActorId,
    pub resources: Vec<ResourceBalance>,        // RES_001: resource_inventory WHERE owner = Actor(a)
    pub items: Vec<HeldItem>,                   // entity_binding WHERE location = HeldBy(a)
                                                //                  AND lifecycle_state = Existing
    pub slots_used: u32,                        // §4.1 accounting
    pub cap: Option<CapacityProfile>,           // entity_binding.inventory_cap (EF_001)
    pub computed_at_turn: u64,
}

pub struct HeldItem {
    pub instance: ItemInstanceId,
    pub def_id: ItemDefId,
    pub class: ItemClass,
    pub charges: Option<u32>,
    pub equipped_slot: Option<EquipSlotId>,     // Some ⇒ also in actor_equipment (ITM-A5)
}
```

**Rules:**
- `lifecycle_state = Existing` is a **required** filter, not an optimisation: EF_001 §3.1 freezes the
  `location` of `Destroyed`/`Removed` entities for audit, so an unfiltered read-view would list a
  burned scroll forever. This is the same trap EF_001 §3.1 calls out for scene rosters.
- **Equipped items appear in `items` with `equipped_slot: Some(_)`** — they are not moved to a
  separate list. They are still `HeldBy` (ITM-A5); hiding them would make the panel disagree with the
  binding.
- Consumers **subscribe** rather than scan: `entity_binding` filtered on `HeldBy(a)` +
  `resource_inventory` on `owner = Actor(a)` + `actor_equipment` on `actor_ref = a` (three DP-K6
  subscriptions). DP-A8 forbids live `t2_scan` in the turn loop, so a scan-based inventory read is a
  defect, not a shortcut.

### 3.1 Deterministic ordering (required, not cosmetic)

Replay determinism (EVT-A9) and prompt stability both need a total order — an unordered digest would
make two replays produce different prompt bytes and therefore different LLM output.

```
items:     sort by (class as u8, def_id, instance_id)
resources: sort by (ResourceKind discriminant, kind_id)
```

Equipped-ness deliberately does **not** affect sort position; it is a flag, so equipping an item
never reshuffles the panel under the player's cursor.

---

## §4 Capacity

### 4.1 What a slot counts

Activating EF_001's `CapacityProfile { max_slots, max_weight }` requires saying what it counts —
which neither EF_001 nor RES_001 did:

```
slots_used = (count of DISTINCT resource kinds with amount > 0 in resource_inventory)
           + (count of held item_instances WHERE equipped_slot IS NONE)
```

> **⚠ RESTATED 2026-08-02 (`IR-16`) over the new shape — and the rule survives in substance.** Under
> `ITD-2` there is no `resource_inventory` to count separately; the accounting becomes:
>
> ```
> slots_used = count of ROWS at location = HeldBy(actor) WHERE equipped_slot IS NONE
> ```
>
> **A quantum stack is one row whatever its count**, so *"a resource kind costs one slot regardless of
> amount"* falls out of the storage shape instead of being a special case beside it — 1 copper and 10 000
> copper are still one row, and `Scheduled:CellProduction` still cannot fail on slot count. **The rule
> stopped needing to be a rule**, which is the same thing that happened to `ITM-C4` and to §8.4's item-side
> cascade in this sweep.

Two consequences, both deliberate:

- **A resource kind costs one slot regardless of amount.** 1 copper and 10,000 copper both cost one
  slot. Amount is limited by `max_weight` (V2) if at all — this is the standard bag-of-holding model
  and it keeps `Scheduled:CellProduction` (RES_001 §6.2) from ever failing on slot count.
- **Equipped items cost an equip slot, not an inventory slot.** Otherwise equipping to free space
  would be impossible at exactly the moment a player needs it, and PL_007 §8.3's implicit-unequip
  step could strand an actor. Weight (V2) still counts equipped items — you carry the armour either
  way.

### 4.1b The over-encumbered rule (corrected at review 2026-07-26)

The accounting above has a consequence the first draft got **wrong**. PL_007 §8.3 claimed that
unequipping at capacity "is still safe because unequip doesn't change holding" — but under §4.1,
`slots_used` counts held-and-**not-equipped** instances, so unequipping **increments** it. Taken
literally, an actor at exactly `max_slots` with a full bag could neither unequip (would exceed the cap)
nor equip (implicit-unequip of the displaced item would exceed it) — a **soft-lock reachable by ordinary
play**, with no in-game action available to escape it.

> **Rule: rearranging what you already carry is never blocked.** `Item:Unequip` — and the implicit
> unequip inside `Item:Equip` (PL_007 §8.3 step 4) — are **exempt** from the capacity check and may push
> `slots_used` above `max_slots`. An actor in that state is **over-encumbered**: acquisitions
> (`Item:PickUp`, `Give`-receive, trade-receive, bulk fill) reject or partial-fill until
> `slots_used ≤ max_slots` again, but equip/unequip/drop always work.

Three reasons this is the right shape rather than "unequip rejects at cap": the actor can always
self-resolve (drop or re-equip); no state becomes unreachable; and it matches how the genre has settled
the question — encumbrance gates *acquisition*, not *manipulation*. Bites at **AC-ITM-17** /
**AC-INV-11**, both of which fail against the original wording.

### 4.2 V1 posture: reserved, unenforced — and *why that is now a live risk*

EF_001 Q6 and RES_001 RES-D2 both lock V1 to `inventory_cap = None` (unbounded). **PL_007b keeps that
posture** — reversing a locked decision is not this file's job — but records honestly what changed:
before items were instanced, an unbounded inventory was at worst a long list of numbers. Now it is an
unbounded set of entity rows. The two guards that make "unbounded" tolerable in V1 are therefore
**mandatory, not optional**:

1. **§5 bounded digest** — makes LLM cost flat regardless of size. This is the promise EF_001 §3.1
   made and this file discharges.
2. **§6 cell item soft cap** — stops a cell becoming an unrenderable junk heap.

If the first authored reality shows inventory bloat, activation is a *config* change
(`inventory_defaults.default_cap = Some(..)`), not a schema change — the field already exists.
Tracked as ITM-Q6.

### 4.3 Weight (V2) and the `CarryCapacity` slot

`CapacityProfile.max_weight` sums `ItemDef.weight` over held instances (equipped included) plus a
per-resource-kind unit weight that RES_001 does not yet carry. Activating weight therefore needs a
`ResourceKindDecl.unit_weight` field — an additive RES_001 change, recorded as ITM-D14 so it is not
discovered at implementation time.

**The stat-side of this already exists as a reservation.** DF07_001 §3 reserves a V1+ `StatSlot`
`CarryCapacity` and DF7-D3 explicitly points it at EF_001's `inventory_cap`. So the intended end state
is that `max_slots`/`max_weight` become **resolved stats** (base + progression + equipment + status)
rather than manifest constants — a strong actor, or one wearing a bag-of-holding, carries more. That
composes cleanly with §4.1 as written: the accounting rule does not change, only where the limit comes
from.

> **⚠ 2026-08-02 (`IR-17`): the INTENT is right and gets a better home; the mechanism is condemned.**
> `StatSlot` is two concepts sharing one array (`D-105`) and is being dismantled — and the measurement
> that found it is directly about this case: **`MaxHp`/`MaxStamina` were never combat's**, they are the
> slots a declared resource binds its **ceiling** to. `C-2a` replaces `CeilingBinding::Slot(StatSlot)` with
> `Derived(quantity_ordinal)`, so a capacity becomes **a declared derived quantity of the reality**, not a
> reserved engine slot.
>
> ⇒ `max_slots` / `max_weight` become exactly that, and the intent this paragraph states — *a limit that
> is resolved, not a manifest constant* — is preserved **and stops being blocked on a V1+ reservation**.
> It also means a granary's capacity gets a name that is not `max_stamina`, which is the wall all four
> author agents hit (`D-82`). Two coordination points recorded so activation is not a redesign:
`inventory_defaults.default_cap` becomes the **fallback** when the capacity quantity is unresolved, and a
capacity change must be visible to any cached `slots_used` comparison.

> ⚠ **2026-08-02 (`IR-17`): the second coordination point DISSOLVES.** It read *"… the same way
> `equipment_version` invalidates `StatEpoch` (PL_007 §6.3)"* — a cache-invalidation analogy pointing at a
> cache that no longer exists (`IR-9`). A capacity is a **derived quantity** now: it is recomputed at
> **phase 0** with every other derived field (`D-49`), so there is no staleness window to coordinate
> across. **The coordination point was an artefact of the cache, not a requirement of the feature.**

### 4.4 Boundary behaviour — single vs bulk (the part usually got wrong)

When a cap is active (V1+30d), two different transfer shapes need two different answers:

| Transfer shape | Examples | At capacity | Why |
|---|---|---|---|
| **Single, atomic** | `Item:PickUp` · `Give` of one item · buying one item | **hard reject** `item.inventory.cap_exceeded` | the actor asked for one specific thing; a silent no-op reads as a bug, and a partial of one is meaningless |
| **Bulk drain** | RES_001 §7.4 PC harvest (drains the whole cell stockpile) · V1+ loot-all | **partial fill**, remainder stays at source, emit `item.inventory.cap_partial` as a *warning* on an accepted turn | destroying the remainder is unrecoverable; failing the whole drain wastes the action; leaving it in the cell is the only reversible option |
| **Rearrangement** *(added at review)* | `Item:Unequip` · the implicit unequip inside `Item:Equip` · `Item:Drop` | **exempt** — proceeds and may exceed the cap (over-encumbered, §4.1b) | blocking it soft-locks an actor with no in-game escape; encumbrance gates acquisition, not manipulation |
| **Cascade** *(added at review)* | holder-death drop (EF_001 §6.1) · equipment clearing (PL_007 §8.4) | **exempt** — never fails | a cascade is a *consequence*, not a proposal; there is no actor to reject and no alternative outcome |

Both paths are deterministic: bulk fill consumes source entries in the §3.1 order until the cap is
reached, so a replay fills the same slots. The `cap_partial` warning is carried on the accepted
event, not as a reject — RES_001 §13.2 reserved `resource.balance.cap_exceeded` for its own side;
`item.inventory.*` is the inventory-side namespace and the two are reported together.

---

## §5 The bounded LLM digest

> **ITM-A9 — Inventory context is fixed-size (extends TG-A1 / COMB-A1 flat-cost family).** What
> `AssemblePrompt` injects for an actor's inventory is an `InventoryDigest` whose **serialized size is
> bounded by configuration, not by inventory size**. An actor with 5 items and an actor with 500
> produce digests within a constant factor of each other. The LLM never receives a full item list,
> and never needs one: it selects from a bounded tool vocabulary (AGT-A2), and the engine — not the
> LLM — resolves whether a chosen instance is valid (PL_007 ITM-V2/V7/V8).

```rust
pub struct InventoryDigest {
    /// Every equipped item, in full — always ≤ slot-profile size (6 V1). This is what the LLM
    /// most needs for narration coherence ("he raises the greatsword").
    pub equipped: Vec<DigestEntry>,

    /// Per-ItemClass counts. ≤ 8 lines V1 (one per ItemClass).
    pub by_class: Vec<(ItemClass, u32)>,

    /// Notable unequipped items, top-N by the §5.1 ranking. N = inventory_defaults.digest_top_n
    /// (default 8).
    pub notable: Vec<DigestEntry>,

    /// Fungible balances, top-M by amount×price with currencies always included. M default 6.
    pub resources: Vec<(ResourceKind, u64)>,

    /// Truthful elision marker — the LLM is TOLD it is not seeing everything, so it does not
    /// narrate "he has nothing else."
    pub elided: Option<ElidedSummary>,          // { item_count, resource_kind_count }
}

pub struct DigestEntry {
    pub instance: ItemInstanceId,
    pub display_name: String,                   // def.display_name.render(locale) (RES_001 §2.2)
    pub class: ItemClass,
    pub charges: Option<u32>,
    pub equipped_slot: Option<EquipSlotId>,
}
```

**The bound is a formula, not a constant (corrected at review 2026-07-26).** The first draft asserted a
flat "≤ 29 lines", derived from the 6-slot engine default. But the slot profile is **author-declared**
(PL_007 §6.1) and `equipped` renders in full, so a reality declaring 20 slots would emit 20 equipped
lines and blow a 29-line assertion — ITM-V17 would then fire on a **legitimate author config** instead of
on a defect, which is worse than not asserting at all (an assertion that cries wolf gets disabled). Two
coordinated fixes: PL_007 §6.1 now caps the profile at **12 slots**, and the bound is stated as:

```
digest_max_lines = |slot_profile|            // ≤ 12, capped at PL_007 §6.1
                 + |ItemClass|               // 8 V1 (closed enum)
                 + digest_top_n              // default 8
                 + digest_resource_top_m     // default 6
                 + 1                         // elision line
// engine defaults (6-slot profile):  6 + 8 + 8 + 6 + 1 = 29
// worst legal case (12-slot profile): 12 + 8 + 8 + 6 + 1 = 35
```

**ITM-V17 asserts against the computed value, never a literal.** The guarantee ITM-A9 actually makes is
therefore the one that matters: *the digest is bounded by configuration, and independent of inventory
size* — 5 items and 500 items both land inside the same bound. Compare CSC_001's demonstrated win — the
v3 LLM-as-grid draft cost 31K tokens against v4 LLM-as-zone at 2.5K — the same shape of fix.

### 5.1 `notable` ranking (deterministic)

```
sort unequipped items by:
  1. is_usable_now DESC        // charges.map_or(true, |c| c > 0) && def.use_effect.is_some()
                               // NOT `charges.is_some()` — see the note below
  2. def.price DESC            (None sorts last)
  3. class as u8 ASC
  4. instance_id ASC           (total-order tiebreak — replay determinism)
take digest_top_n
```

No RNG, no recency clock, no LLM involvement in the selection. Recency was deliberately excluded: it
would make two replays with different wall-clock ordering diverge.

> **Corrected at cold-start review 2026-07-26.** Key 1 was written as `has_charges DESC` over a
> `charges: Option<u32>`, which is ambiguous in the worst direction: read as `is_some()` it ranks an
> **exhausted husk** (`Some(0)` — a spent wand kept because `consume_on_exhaust: false`) *above* a
> perfectly usable charge-less item (`None` — a sword, a rope). The prompt would then spend its scarce
> `notable` lines advertising items the actor cannot use, while omitting ones it can. The predicate is
> now spelled out, and it also folds in `use_effect.is_some()` so that an item with no effect at all
> does not outrank one that has a usable effect.

### 5.2 Elision must be visible

`elided` is populated whenever anything was dropped from `notable` or `resources`. A digest that
silently truncates invites the exact failure A6 canon-drift exists to catch — the narrator asserting
"he carried nothing else" as fact. With `elided: Some { item_count: 47, .. }` the prompt can state
"and 47 other items" and stay truthful. **AC-INV-6 tests this.**

### 5.3 NPC inventories

Identical digest, same bounds, for `LlmDriver` NPCs (AGT-A3) — with one difference: a **hostile**
actor's digest is subject to COMB_001 Q6 stat-hiding, so a PC-facing prompt gets the *observable*
subset (equipped + visible class counts), never `notable`/`resources`. What an enemy is *carrying* is
not visible; what it is *wielding* is.

---

## §6 Ground inventory (cell-held items)

Items with `location = InCell(c)` are the third place inventory shows up: dropped gear, corpse
spill (PL_007 §8.4), world-placed treasure (TMP_006), and the loot module's future subject.

```rust
/// T1 read-side projection, per cell. Same non-authoritative status as §3 (ITM-A8).
pub struct CellItemView {
    pub cell: ChannelId,
    pub items: Vec<HeldItem>,                   // entity_binding WHERE InCell(c) AND Existing
    pub soft_cap: u32,                          // inventory_defaults.cell_item_soft_cap (default 100)
}
```

- **Soft cap, not hard.** A cascade drop (PL_007 §8.4) MUST NOT fail — an actor dying with 30 items
  in a cell already holding 95 cannot be rejected, because the cascade is a consequence, not a
  proposal. So the cap governs *proposals* (`Item:Drop` rejects with
  `item.inventory.cell_cap_exceeded`) and only *warns* on cascades. This asymmetry is the whole point
  of calling it soft.
- **Rendering seam:** CSC_001 places cell items on placeable tiles and already owns
  `csc.item_on_non_placeable`. Beyond the placeable-tile count, surplus items are rendered as a
  single "pile" affordance — CSC's Layer-3 assignment decides, not PL_007b (ITM-D16).
- **Decay:** ground items persist indefinitely in V1. A `Scheduled:ItemDecay` Generator
  (PL_007 §10, V1+30d reserved per RES-D18) is the pressure valve, and it is the honest answer to
  "won't cells fill up over months" — recorded as ITM-D15 rather than hand-waved.

---

## §7 Transfer flows

Each row shows which store moves and which validator gates it. **No flow writes "the inventory"** —
they write one of the two stores (ITM-A8).

| Flow | Store touched | Gate | Capacity path (§4.4) |
|---|---|---|---|
| `Item:PickUp` | `entity_binding` HeldBy | ITM-V9 (in cell) | single → hard reject |
| `Item:Drop` | `entity_binding` InCell | ITM-V12 (not equipped) + §6 soft cap | cell soft cap → reject proposal |
| `Give` (PL_005) — instanced | `entity_binding` HeldBy transfer | ITM-V2 + ITM-V12 + EF_001 `BeGiven`/`BeReceived` | single → hard reject |
| `Give` (PL_005) — fungible | `resource_inventory` decrement/increment | RES-V1 `ResourceBalanceCheck` | single → hard reject |
| Trade (RES_001 §8) | `resource_inventory` both sides | RES-V3 `TradePricingValidator` | single → hard reject |
| Trade of an **instanced** item | `entity_binding` + `resource_inventory` (payment) | RES-V3 + ITM-V2/V12 | single → hard reject |
| Harvest (RES_001 §7.4) | `resource_inventory` bulk drain from cell | RES-V1 | **bulk → partial fill** |
| Production / auto-collect (RES_001 §6) | `resource_inventory` (cell → NPC) | RES-V4 | bulk → partial fill; `stockpile_cap` already clamps upstream |
| Holder death cascade | `entity_binding` HeldBy → InCell + `actor_equipment` clear | none — consequence, not proposal | soft cap **warns only** (§6) |
| Loot (V1+, AUD-F9) | `entity_binding` InCell/corpse → HeldBy | that module's | bulk → partial fill |

**One gap made explicit:** RES_001 §8.5's `InteractionTradePayload` carries
`Vec<ResourceBalance>` on both sides — it can express "5 copper for 3 rice" but **not** "5 copper for
*that specific sword*". Trading an instanced item therefore needs an additive
`instances: Vec<ItemInstanceId>` on the payload. Recorded as ITM-D13 with the RES_001/PL_005 closure
pass as its target — V1 workaround is Give-reciprocal (RES-Q3 already allows it).

> **And the consequence of that gap, stated plainly (review 2026-07-26): V1 has no *priced* sale of an
> instanced item.** Because RES-V3's `TradePricingValidator` reads `ResourceBalance` amounts, it cannot
> see an item instance at all — so the Give-reciprocal workaround is **consensual but unpriced**. Nothing
> checks that the coins offered match `ItemDefDecl.price`. That field therefore does *no* enforcement
> work in V1; it feeds digest ranking (§5.1) and V1+ vendor flows only. Worth naming because a `price`
> field invites the reasonable assumption that trade honours it, and a reader auditing for an
> economy exploit should find this stated rather than have to derive it. What *does* constrain the trade
> is NPC willingness (PL_005b §4.7 opinion threshold) — social, not arithmetic. Tracked as **ITM-D20**
> alongside ITM-D13, since one payload change fixes both.

---

## §8 Validators & rule_ids

### 8.1 New validators (extend PL_007 §9, same Stage 3.5.e)

| ID | Check | rule_id | Active |
|---|---|---|---|
| **ITM-V14** | single-transfer target has a free slot when `cap` is `Some` | `item.inventory.cap_exceeded` | V1+30d (V1 cap always None) |
| **ITM-V15** | bulk drain computes a partial fill and emits the warning rather than rejecting | `item.inventory.cap_partial` (warning) | V1+30d |
| **ITM-V16** | `Item:Drop` target cell is below `cell_item_soft_cap` | `item.inventory.cell_cap_exceeded` | **V1** |
| **ITM-V17** | digest assembly asserts `lines ≤ digest_max_lines` **computed per §5's formula** — never against a literal | `item.inventory.digest_bound_violated` | **V1** |
| **ITM-V18** *(added at review)* | acquisition-vs-rearrangement classification: a transfer classified as *rearrangement* or *cascade* must **not** consult the cap (§4.1b / §4.4) | (no reject — a structural assertion; a cap check on an exempt path is a defect) | **V1** |

ITM-V16 and ITM-V17 are the two that are **live in V1**. ITM-V14/V15 exist because the cap field
exists; they are dormant-by-configuration, not dormant-by-omission — and AC-INV-4 exercises them
with a cap forced on in test config so they are not untested code paths at activation time.

ITM-V17 deserves a note on non-vacuity: it is a self-assertion, and a self-assertion that cannot fail
is worthless. It **can** fail — a mis-tuned `digest_top_n`, a locale whose `display_name` renders long,
or a future 9th `ItemClass` all push the line count past the bound. It fails loudly at assembly time
rather than silently inflating every prompt.

### 8.2 `item.inventory.*` sub-namespace — 4 rules

| rule_id | Trigger | `user_message` (I18nBundle default / vi) |
|---|---|---|
| `item.inventory.cap_exceeded` | single transfer, no free slot | "Your inventory is full." / "Túi của bạn đã đầy." |
| `item.inventory.cap_partial` | bulk drain partially filled (**warning on an accepted turn**) | "You could only carry some of it." / "Bạn chỉ mang được một phần." |
| `item.inventory.cell_cap_exceeded` | `Item:Drop` into a cell at soft cap | "There is no room to put that down here." / "Không còn chỗ để đặt xuống ở đây." |
| `item.inventory.digest_bound_violated` | ITM-A9 assertion failure (internal) | "System error assembling inventory context." / "Lỗi hệ thống khi dựng ngữ cảnh túi đồ." |

Registered under PL_007's existing `item.*` prefix — one namespace, one owner, no second registration.

---

## §9 `RealityManifest` extension

```rust
RealityManifest {
    // ── PL_007b extension (added 2026-07-26) ──
    /// OPTIONAL V1 — engine defaults below.
    pub inventory_defaults: InventoryDefaults,
}

pub struct InventoryDefaults {
    /// Applied to entity_binding.inventory_cap at EntityBorn for actors.
    /// V1 default None (unbounded — EF_001 Q6 / RES-D2 posture, §4.2).
    pub default_cap: Option<CapacityProfile>,
    pub digest_top_n: u32,              // default 8   (§5)
    pub digest_resource_top_m: u32,     // default 6   (§5)
    pub cell_item_soft_cap: u32,        // default 100 (§6)
}
```

---

## §10 Cross-feature notes

| # | Target | Change | Load-bearing |
|---|---|---|---|
| **10.1** | **RES_001** | `resource_inventory` stays the fungible store, unchanged. **RES-D2 (weight cap)** now has an accounting definition (§4.1/§4.3) and a named prerequisite (`ResourceKindDecl.unit_weight`, ITM-D14). Harvest gains partial-fill semantics under a cap (§4.4). `InteractionTradePayload` needs `instances` for instanced trade (ITM-D13). | **yes** |
| **10.2** | **EF_001** | `inventory_cap` (Q6b) gains its accounting rule (§4.1) — the reservation is no longer undefined. `ActorInventoryView`/`CellItemView` are the read-views AC-EF-10 asserted but did not specify. | **yes** |
| **10.3** | **S9 prompt assembly** | `AssemblePrompt` gains the `InventoryDigest` block with a hard size bound (ITM-A9) | **yes** |
| **10.4** | **CSC_001** | cell items render on placeable tiles; surplus becomes a pile affordance (ITM-D16) | no |
| **10.5** | **COMB_001** | digest for hostile actors respects Q6 stat-hiding (§5.3): wielded visible, carried not | yes |
| **10.6** | **NPC_002 / AIT_001** | NPC prompts use the same bounded digest — inventory size never affects per-NPC token cost, which matters at AIT_001's ≤20 Major / ≤100 Minor caps | no |
| **10.7** | **future Loot module** (AUD-F9) | inherits `CellItemView` + bulk partial-fill + `ItemOrigin::Loot`; needs no new inventory surface | no |

---

## §11 Acceptance criteria

10 V1-testable scenarios.

1. **AC-INV-1 — the union is a union.** An actor holding 3 instanced items and 4 resource kinds
   produces a view with `items.len() == 3` and `resources.len() == 4`; deleting the
   `resource_inventory` row leaves the 3 items intact and vice versa. *(§3 / ITM-A8)*
2. **AC-INV-2 — destroyed items leave the view immediately.** Burning a held scroll
   (`Existing → Destroyed`) removes it from `ActorInventoryView` on the next read **while**
   `entity_binding.location` still reports the frozen audit location. *(§3 — the EF_001 §3.1 trap)*
3. **AC-INV-3 — equipped items stay in the list, flagged.** After `Item:Equip`, the item is still in
   `items` with `equipped_slot: Some(main_hand)`, and `slots_used` **decreases by 1**. *(§3 / §4.1)*
4. **AC-INV-4 — capacity paths work when switched on.** With test config
   `default_cap = Some { max_slots: 5 }`: (a) `Item:PickUp` at 5/5 rejects
   `item.inventory.cap_exceeded`; (b) a 10-kind harvest into 3 free slots fills exactly 3 in §3.1
   order, leaves 7 kinds in the cell, accepts the turn, and reports `item.inventory.cap_partial`;
   (c) equipping an item frees a slot and the pickup then succeeds. *(§4.4 / ITM-V14 / ITM-V15)*
5. **AC-INV-5 — digest is size-bounded.** Actors with 5, 50, and 500 held items produce digests whose
   line counts are all ≤ 29 and differ by ≤ 2 lines from each other. *(§5 / ITM-A9)*
6. **AC-INV-6 — elision is truthful.** The 500-item actor's digest has
   `elided: Some { item_count: n }` with `n` equal to actual-minus-shown, and the assembled prompt
   contains the "and n other items" clause. Removing the elision field makes the test fail. *(§5.2)*
7. **AC-INV-7 — digest is replay-stable.** The same actor state assembled twice, and once again after
   an unrelated turn elsewhere in the reality, produces **byte-identical** digests. Ordering ties are
   broken by `instance_id`. *(§3.1 / §5.1 — EVT-A9)*
8. **AC-INV-8 — hostile digest hides the bag, not the blade.** A PC-facing prompt for a hostile NPC
   contains its `equipped` entries and class counts, and contains **no** `notable` or `resources`
   entries. *(§5.3 / COMB_001 Q6)*
9. **AC-INV-9 — cell soft cap rejects proposals and passes cascades.** With a cell at
   `cell_item_soft_cap`: `Item:Drop` rejects `item.inventory.cell_cap_exceeded`; a holder-death
   cascade dropping 30 items into the same cell **succeeds**, warns, and leaves all 30 `InCell`.
   *(§6 / ITM-V16)*
10. **AC-INV-10 — no live scan in the turn loop.** *(reworded at review — the original said a `t2_scan`
    "fails the DP-A8 assertion", but DP-A8 is a **policy**, not a runtime guard, so that test had
    nothing to hook onto and could not have been written.)* Testable form: assert the inventory read
    path issues **only** DP-K6 subscribe reads and keyed point-reads — no `t2_scan` call site exists in
    the turn path. Mechanised as a call-graph/grep assertion in CI over the inventory projection module,
    the same way the provider-gate script asserts "no direct SDK import". *(§3 / DP-A8)*
11. **AC-INV-11 — over-encumbered state is reachable and escapable.** With
    `default_cap = Some { max_slots: 5 }`, an actor at 5/5 plus one equipped item: `Item:Unequip`
    **succeeds** → `slots_used = 6`; `Item:PickUp` rejects `item.inventory.cap_exceeded`; `Item:Drop`
    **succeeds** → back to 5; pickup then succeeds. **Fails against the pre-review wording**, where
    unequip was cap-checked and the actor had no legal escape. *(§4.1b)*
12. **AC-INV-12 — the digest bound tracks the profile, not a constant.** With a 12-slot author profile
    and 12 items equipped, the digest assembles cleanly and ITM-V17 does **not** fire (bound = 35, per
    §5's formula); with the assertion hard-coded to 29 the same input trips it. Then the size-independence
    half: 5-item and 500-item actors on the same profile stay within the same computed bound.
    *(§5 / ITM-V17)*
13. **AC-INV-13 — declaring a 13-slot profile is rejected at bootstrap.** `item.slot_profile_too_large`,
    so the digest bound can never be exceeded by configuration. *(PL_007 §6.1)*

---

## §12 Deferrals & open questions

| ID | What | Why | Target |
|---|---|---|---|
| **ITM-D13** | `InteractionTradePayload.instances: Vec<ItemInstanceId>` — trading a *specific* item | RES_001 §8.5 is balance-only (§7); V1 workaround = Give-reciprocal per RES-Q3 | RES_001 + PL_005 closure pass |
| **ITM-D14** | `ResourceKindDecl.unit_weight` — prerequisite for the V2 weight cap | additive RES_001 field; naming it now stops discovery-at-implementation | V2 (with RES-D2) |
| **ITM-D15** | `Scheduled:ItemDecay` — ground-item cleanup | reserved in PL_007 §10; pairs with RES-D18 spoilage | V1+30d |
| **ITM-D16** | Surplus ground items as a single "pile" affordance | CSC_001 Layer-3 owns the rendering decision | CSC_001 next pass |
| **ITM-D17** | Inventory sort/filter/search UI + per-device layout persistence | client-build track; per CLAUDE.md per-device UI state may use localStorage, the inventory data may not | client track |
| **ITM-D18** | Bank / storage chest (off-actor persistent storage) | needs ITM-D3 containers + an ownership model beyond HeldBy | V2 |

**All three RESOLVED at the review pass 2026-07-26** — one decision, two measurements with a defined
method and a named trigger. See [PL_007 §16](PL_007_item.md) for ITM-Q1..Q5.

| ID | Question | **Resolution** |
|---|---|---|
| **ITM-Q6** | Does V1 actually survive uncapped inventories, or should `default_cap` ship set? | **DECIDED: ship V1 uncapped (`default_cap = None`), and the decision is now *safe* rather than merely inherited.** At draft time this was a risk carried on trust from the EF_001-Q6 / RES-D2 lock. It is now defensible on mechanism: (a) ITM-A9's bounded digest means an unbounded inventory has **no LLM cost consequence** at all — the failure mode that would have hurt most is structurally absent; (b) **ITM-C10** removes the multiplying source of instances (Untracked actors hold none); (c) the remaining cost is DB rows for Tracked actors, which is bounded by what a human bothers to pick up. **Trigger for reversal:** a Tracked actor exceeding ~200 held instances in playtest, or `actor_inventory_view` assembly appearing in a slow-query log. Activation stays config-only — `inventory_defaults.default_cap`, no schema change, and §4.1b/§4.4 already specify every boundary behaviour, so flipping it on cannot surprise anyone. |
| **ITM-Q7** | Is `digest_top_n = 8` the right bound for narration quality vs cost? | **MEASURE, with the method fixed rather than left to taste.** Reuse CSC_001's own methodology, which is the reason this project trusts the bounded-digest approach at all: CSC_001 measured v3 LLM-as-grid at 31K tokens against v4 LLM-as-zone at 2.5K and chose on numbers. The A/B here is `digest_top_n ∈ {4, 8, 16}` against two graded outcomes — narration coherence (does the narrator reference items the actor actually holds?) and A6 canon-drift rate (does it invent items?). **Owner:** the first authored reality's prompt-tuning pass. **Default holds at 8 until measured**; the formula in §5 makes any value safe to try, since the assertion adapts. |
| **ITM-Q8** | Should `slots_used` count *distinct kinds* or introduce per-kind stack sizes (classic "99 per stack")? | **DECIDED: distinct kinds; stack sizes are rejected for V1, not merely deferred.** A per-kind stack size would re-introduce exactly the numeric ceiling RES_001's `StackPolicy::Sum` deliberately omits, and it would collide with `Scheduled:CellProduction` (RES_001 §6.2), which already clamps at `stockpile_cap` and has no notion of splitting a balance across stacks. Two ceilings on the same quantity, owned by two features, is a drift generator. If "99 per stack" is ever wanted as a *fiction* device, the honest implementation is a `max_stack` on `ResourceKindDecl` — **RES_001's field, RES_001's decision**, not an inventory-side reinterpretation of the same number. |

---

## §13 Cross-references

- Item substrate — [`PL_007_item.md`](PL_007_item.md) (ITM-A1..A7, aggregates, `Item:*` actions, §9 validators)
- Fungible store + harvest/trade/production — [`RES_001`](../00_resource/RES_001_resource_foundation.md) §4.2, §6, §7.4, §8
- Binding, `inventory_cap`, the AC-EF-10 read-view claim — [`EF_001`](../00_entity/EF_001_entity_foundation.md) §3.1, §14
- Cell rendering — [`CSC_001`](../00_cell_scene/CSC_001_cell_scene_composition.md) (Layer 3, `csc.item_on_non_placeable`)
- Flat-token-cost precedent + the 31K→2.5K measurement — [`COMB_002`](../18_combat/COMB_002_tactical_grid.md) §1 · CSC_001 `_ui_drafts/CELL_SCENE_v3..v4`
- Stat hiding — [`COMB_001`](../18_combat/COMB_001_combat_foundation.md) §6 Q6
- Prompt assembly — `02_storage/S09_prompt_assembly.md`
- Audit rows closed — [`12_module_coverage_audit.md`](../../12_module_coverage_audit.md) (Inventory 🟡 → designed; AUD-F5 with PL_007)

---

## §14 Readiness checklist

- [x] ITM-A8 (one inventory, two stores) + ITM-A9 (fixed-size context) stated as axioms with failure modes
- [x] `actor_inventory_view` + `CellItemView` specified as **projections**, never aggregates
- [x] `lifecycle_state = Existing` filter justified against EF_001 §3.1's frozen-location rule
- [x] Deterministic total ordering for both stores (§3.1) — replay + prompt stability
- [x] Slot accounting **defined** (§4.1), activating EF_001 Q6b / RES-D2 reservations
- [x] V1 uncapped posture preserved, with the new risk named and both mandatory guards specified (§4.2)
- [x] Single-vs-bulk boundary behaviour decided with reasons (§4.4) — not left to implementation
- [x] Digest with a hard line bound (≤29) + deterministic ranking + **truthful elision** (§5)
- [x] Hostile-actor digest respects COMB_001 Q6 stat hiding (§5.3)
- [x] Ground inventory + soft-cap asymmetry (proposals reject, cascades warn) (§6)
- [x] 11 transfer flows mapped to store + gate + capacity path (§7); the RES_001 trade-payload gap named (ITM-D13)
- [x] 4 new validators (ITM-V14..V17), 2 live in V1, 2 dormant-by-config but test-covered (AC-INV-4)
- [x] 4 `item.inventory.*` rule_ids under the existing `item.*` prefix — one registration
- [x] 1 RealityManifest extension, OPTIONAL with engine defaults
- [x] 7 cross-feature notes, 4 load-bearing (§10)
- [x] 13 V1-testable acceptance criteria (AC-INV-1..13); AC-INV-11..13 added at the review pass
- [x] 6 deferrals (ITM-D13..D18) + ITM-D20/D23 raised here
- [x] **All 3 open questions RESOLVED** (§12) — ITM-Q6 decided *on mechanism* rather than inherited on trust, ITM-Q8 decided against stack sizes with the RES_001 collision named, ITM-Q7 given a measurement method and an owner
- [x] **Review pass fixes landed here:** the unequip soft-lock (§4.1b over-encumbered rule) · the digest bound as a formula rather than a constant (§5) · rearrangement + cascade rows in the capacity table (§4.4) · the unpriced-instanced-sale limitation named (§7 / ITM-D20) · AC-INV-10 made mechanically testable
- [ ] `/review-impl` cold-start adversarial pass — **still recommended** (see PL_007 §19 on author blindness)
- [ ] CANDIDATE-LOCK closure pass — pending PL_007 (shared cycle)
