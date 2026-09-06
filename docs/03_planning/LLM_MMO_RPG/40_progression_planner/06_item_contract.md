# 40.6 — The item contract: what the item generator needs, derived from the substrate

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `ICT-`
> **Derived from** [`PL_007_item.md`](../features/04_play_loop/PL_007_item.md) (+ `PL_007b`, `PL_007c`,
> 2031 lines, `ITM-A1..A9`, all `ITM-Q1..Q8` resolved 2026-07-26) — **the substrate exists and is
> specified.** This document adds no item semantics. It reads `ItemDefDecl` field by field and asks
> one question of each: **who produces this?**
>
> ⚠ **2026-08-02 (`IR-30`) — THE METHOD SURVIVES; THE SUBJECT MOVED.** *"The substrate exists and is
> specified"* was true on 2026-07-31 and is no longer: the item round replaced `ITM-A2` (stackability is
> **earned**, not declared), deleted the `EquipmentStats` seam (a contribution is **DATA, never CODE**),
> and split **ownership from location**. Authority is now
> [`docs/specs/2026-08-02-item-data-structure.md`](../../../specs/2026-08-02-item-data-structure.md) and
> [`item-dataflow.md`](../../../specs/2026-08-02-item-dataflow.md) Part II (§14 is the declaration surface
> this document should be re-derived against).
>
> **The method — read the schema field by field and ask *who produces this* of every one — is right, and
> is the direct answer to doc 39's worst finding (*"23 schema positions had no producer at all"*).** It
> was applied to a schema that has since changed. **Re-run it; do not rewrite it.**
> **Applies** [`40.4`](04_enum_pool.md) `EPL-A2` · **retracts** one mechanism from
> [`40.3`](03_generator_boundary.md).

---

## 0 — Method, and why it starts by reading

Doc 39's worst finding was *"23 schema positions had no producer at all"* — a generator designed
against a schema nobody had read. The item substrate is **2031 lines of already-locked design**, so
this document does the opposite in order: read `ItemDefDecl`, classify every field, and let the
contract fall out.

**Two things it corrects immediately, from that reading:**

- `RES_001` §3.1 lists `Item(ItemKind)` as a reserved `ResourceKind`. **That was withdrawn** —
  `ITM-A2` §12.2 removes `ResourceKind::Item`, and an instanced item is an **Entity** with an
  `entity_binding` row, never a resource balance. An earlier note in this folder read `RES_001`
  without `PL_007` and got this backwards.
- `ITM-A2` is enforced, not asserted: an `ItemDefId` colliding with any `resource_kinds` `kind_id` is
  **rejected at canonical seed** (`ITM-V10`/`ITM-C2`).

---

## 1 — `ICT-A1` — items have THREE tiers, not two

> **`ICT-A1`.** For items the contract→generate split has a **third** level, and conflating any two of
> them produces either an unfillable human worklist or an unpinnable runtime.

| tier | what it is | how many | where it lives | who produces it |
|---|---|---|---|---|
| **1 · taxonomy** | the closed sets: grades, tags, slots, categories | **tens** | the **pool** (`EPL-A2`) | the contract loop — human + LLM |
| **2 · `ItemDef` table** | one `ItemDefDecl` per base type | **tens to hundreds** | the **pinned manifest** | item's **L2 generator**, from tier 1 |
| **3 · `item_instance`** | the sword a player is holding | unbounded | the **event log / runtime state** | runtime, `f(manifest, seed)` |

**Tier 2 is the one that is easy to misplace, in both directions.** Put it in the pool and a human is
asked to hand-author three hundred rows — the *"a human who must author every cell is a human who
will not finish"* failure doc 38 §4 already names. Put it at runtime and the manifest cannot say what
items a reality contains, so nothing is pinnable and `CPL-A12` breaks.

This is Diablo 2's shape exactly, and doc 38 `CPL-A10` already argued it: the **base table and affix
table are authored data** (tier 2), the **roll** is generated (tier 3). LoreWeave's one change is that
tier 2 is *derived from tier 1 by a generator* instead of typed in by a designer.

---

## 2 — Every field of `ItemDefDecl`, classified

The whole derivation. `P` = pool (tier 1) · `E` = engine-fixed closed set (in the binary, not
per-reality) · `M` = magnitude (item's own numeric source) · `R` = reference into another module's
pool · `V` = LLM vocabulary · `D` = derived structurally at tier 2.

| field | class | who produces it |
|---|---|---|
| `def_id: ItemDefId` | **D** | tier-2 generator; the identity of a base |
| `display_name: I18nBundle` | **V** | LLM half of item's generator |
| `description: I18nBundle` | **V** | LLM half — also the `Examine` text (`§7.2`) |
| `class: ItemClass` | ~~**E**~~ → **P** | ⚠ **CORRECTED 2026-08-02 (`IR-28` / `IR-4`).** Was *"engine-fixed, 8 variants. A reality cannot add a 9th."* `D-98`: the engine's arithmetic does **not** differ per class — **it never reads the class at all** — so this is the item feature's vocabulary in costume. It becomes a declared **ROSTER** (`item_classes`) with the 8 as engine **defaults**. **This row is where an author would actually hit the wall**: a reality of `talisman` / `pill` / `spirit-stone` / `manual` had to spell them `Trinket` / `Consumable` / `Valuable` / `Document` |
| `affordance_overrides` | **E** | `AffordanceSet` is EF_001's closed set |
| `equip.slot: EquipSlotId` | **P** | `equip_slot_profile` — author-declared, **capped at 12** (`§6.1`) |
| `equip.also_blocks` | **D** | follows from `two_handed`; consistency-checked by `ITM-C5` |
| `equip.modifiers: Vec<ModifierTemplate>` | **R** target + **M** value | ⚠ **CORRECTED 2026-08-02 (`IR-29` / `IR-2`).** Was *"`StatSlot` is **DF07-owned, 10 V1 slots**."* `D-10` opened the set, `D-100` measured it to be **combat's**, `D-105` found it is **two concepts sharing one array**, and `C-2a`/`b`/`c` are dismantling it. The target is now a **`QuantityOrdinal` the reality declared** — so it is a **reference into another module's pool (`R`)**, not an engine-fixed set, which also means the generator resolves it the same way it resolves `equip.requirements.kind_id`. The magnitude half is unchanged |
| `equip.requirements` | **R** + **M** | `EquipRequirement::MinProgression{kind_id, min_raw_value}` — `kind_id` is **progression's** pool member; the threshold is a magnitude |
| `equip.combat.reach` | **M** | |
| `equip.combat.two_handed` | **D** | |
| `equip.combat.strike_kinds` | **E** | `StrikeKind` is PL_005b's closed set |
| `use_effect: UseEffectDecl` | **E** op + **M** value | *"the item-legal subset of ABL's `EffectOp`"* — ability module owns the ops |
| `max_charges` | **M** | |
| `consume_on_exhaust` | **D** | a flag implied by the archetype, not a set |
| `price: PriceDecl` | **M** + **R** | the number is a magnitude; the currency is **RES_001's** `CurrencyKindId` |
| `weight` | **M** | V1 informational |
| `lex_tags: Vec<LexTag>` | **R** | **WA_001** owns the lex vocabulary (`§12.7`) |
| `instrument_tags: Vec<InstrumentTag>` | **P** | `instrument_tag` — *"author-declared, English snake_case"* (`§6.4`) |
| `destructible` | **D** | |

**Read the `class` column and the contract is already visible.** Of twenty positions, **two** are
pool slots. Everything else is engine-fixed, a magnitude, a reference, vocabulary, or derived.

> **`ICT-A2` — the item module's pool footprint is SMALL, and that is the finding.** The item
> generator looks like the biggest module in the pipeline and contributes about five decisions to the
> shared pool. Its bulk is tier 2, which it produces itself.

---

## 3 — The contract: what item registers into the pool

Five slots. `equip_slot_profile` and `instrument_tag` come straight from §2; the other three are the
tier-1 taxonomy that tier 2 needs and `ItemDefDecl` does not name because it is *below* it.

```rust
// ── straight out of ItemDefDecl ──────────────────────────────────────────────
declare_pool_slot!{ id:"equip_slot", owner:ELEMENT_ITEM, arity:1..=12, ordered:false,
                    tier:Reality, member:{ slot_id, display_name: I18nBundle } }
                    // cap of 12 is NOT ours — PL_007 §6.1 set it, because InventoryDigest
                    // renders every equipped item and 30 slots blow ITM-A9's ≤29-line bound

declare_pool_slot!{ id:"instrument_tag", owner:ELEMENT_ITEM, arity:0..=32, ordered:false,
                    tier:Reality, member:{ tag: SnakeCase } }
                    // "blade", "spear", "bow" — a wuxia taxonomy is not a sci-fi one

// ── the tier-1 taxonomy tier 2 generates FROM ────────────────────────────────
declare_pool_slot!{ id:"item_grade", owner:ELEMENT_ITEM, arity:2..=16, ordered:TRUE,
                    tier:Reality, member:{ name: I18nBundle, rank: Ordinal } }
                    // the PO's own example: "this reality has 5 grades of treasure"

declare_pool_slot!{ id:"item_archetype", owner:ELEMENT_ITEM, arity:1..=64, ordered:false,
                    tier:Reality, member:{ name: I18nBundle, class: ItemClass,
                                           instrument_tags: [instrument_tag],
                                           equip_slot: equip_slot? } }
                    // "sword", "spear", "saber", "healing pill", "talisman"
                    // NOT an ItemDef — an ItemDef is (archetype x grade x affixes), tier 2

declare_pool_slot!{ id:"item_affix", owner:ELEMENT_ITEM, arity:0..=64, ordered:false,
                    tier:Reality, member:{ name: I18nBundle, stat_slot: StatSlot,
                                           applies_to: [item_archetype | ItemClass] } }
                    // the D2 affix table's vocabulary; the ROLL RANGE is a magnitude, not here
```

**Why `item_archetype` and not `item_def`.** `item_def` is tier 2. `item_archetype` is the assertion a
human can actually make and approve — *"the weapons of this reality are sword, spear, saber, whip,
fan"* — and it is `PGN-A11`'s approval unit: **the assertion class, not the row.** Six archetypes ×
five grades is thirty `ItemDef`s from one human decision, expanded by provenance ⑤ DERIVED
(`PPL-A5`) at zero marginal cost.

### 3.1 Which of the five are SHARED — the PO's criterion, applied

> *"I think it is grade and type, because those affect other modules. Is anything else needed?"*

Right criterion (now `EPL-A7`), and it separates the five cleanly. The test is literal: **grep the
other modules' declarations for a reference to this slot's members.**

| slot | visibility | who outside item references it |
|---|:---:|---|
| `item_grade` | **SHARED** | economy (price tiering) · loot tables · place generator · crafting output grade |
| `item_archetype` | **SHARED** | crafting recipes · loot tables · quest rewards |
| `instrument_tag` | **SHARED** | **PROG_001** training + breakthrough conditions · **DF07** `StatTerm` |
| `equip_slot` | **SHARED** | **DF07** stat resolution · `PL_007b` inventory digest |
| `item_affix` | **PRIVATE** | **nobody.** No other module has a reason to name an affix |

So the PO's two are correct and there are **two more that also cross the boundary** — and both were
found by reading `PL_007`, not by reasoning: `instrument_tag` (§6.4, the `PROG-D15` seam) and
`equip_slot` (§6.1, which DF07 reads to resolve stats).

**And one drops out.** `item_affix` stays a real authored list — a human still writes it — but it is
**item's own business**. Publishing it would let a future progression rule bind to *"the Sharp
affix"*, which is `PPB-A1`'s violation arriving through the back door.

**Anything else needed?** From the field-by-field pass in §2 and the reference table in §4: **no.**
Every other cross-module thing an item touches is either **engine-fixed** (`ItemClass`, `StatSlot`,
`StrikeKind`, `EffectOp`, `AffordanceSet` — referenced, never filled, cannot dangle) or **owned
elsewhere and referenced by item** (`ProgressionKindId`, `CurrencyKindId`, `LexTag`). Item publishes
four things and consumes three.

### 3.2 What `EPL-A8` means here: progression will GROW this contract

The PO's second observation lands directly on `item_archetype` and `instrument_tag`:

> *"The progression generator crosses the boundary — when we run it, it adds a type into the item type
> enum."*

Correct, and it is the normal mode, not an exception (`EPL-A8`). A breakthrough condition resolved in
the progression half of the loop leaves a reference to an item-side member that does not exist, and
the register abduces it as an open row **on item's slot**. Item's taxonomy is therefore never "done"
until the whole pool converges.

**What makes it affordable is `ICT-A3`.** Because the seam is `InstrumentMatch::ItemTag`, progression
demands **one `instrument_tag` member** — not a set of archetypes. Item's own generator then decides
which archetypes wear the tag. One cheap cross-module decision instead of N expensive ones, and the
under-specification that keeps the modules decoupled is the same under-specification that keeps the
demand small.

**Rough size of the human's actual job for items:** ~6 equip slots · ~10 instrument tags · ~5 grades ·
~15 archetypes · ~20 affixes ≈ **56 decisions**, most of them cheap and most of them citable from a
book. That is a job someone finishes in an afternoon. Three hundred hand-authored `ItemDef`s is not.

---

## 4 — What item REFERENCES from other modules

Dangling references the pool must resolve (`EPL-A4`) — item does not own any of these:

| reference | owner | used for |
|---|---|---|
| `ProgressionKindId` | **PROG_001** | `EquipRequirement::MinProgression` / `MinProgressionTier` |
| `CurrencyKindId` | **RES_001** | `PriceDecl` |
| `LexTag` | **WA_001** | `lex_tags` — the Stage-4 gate `PL_005b` §8.2 declared and never had an input for |
| `StatSlot` | **DF07** | `StatModifier` — engine-fixed, referenced not filled |
| `EffectOp` (item-legal subset) | **ABL** | `use_effect` |
| `StrikeKind` | **PL_005b** | `CombatItemProfile.strike_kinds` |
| `FactionId` · `RaceId` · `TitleId` | FAC / IDF / titles | `EquipRequirement` **V1+ reserved** |

Only the first three are *open-member* — i.e. only three can produce a dangling pool reference. The
rest are engine-fixed sets, which cannot dangle by construction.

---

## 5 — What item EXPOSES

| exposure | who reads it |
|---|---|
| `item_archetype` + `instrument_tag` | **PROG_001** training/breakthrough conditions, **DF07** `StatTerm` |
| `item_grade` (ordered) | economy, loot tables, place generator |
| `ItemDefId` (tier 2, post-freeze) | crafting recipes, loot tables, quest rewards |
| `equip_slot` profile | DF07 stat resolution, inventory digest |

---

## 6 — `ICT-A3` — `RoleRequirement` is retracted; the seam already exists and it is `InstrumentTag`

[`40.3` `PPB-A2`①](03_generator_boundary.md) proposed a `RoleRequirement` so progression could say
*"I need an item that plays this role"* without designing the item, and [`40.3` `PPB-A3`](03_generator_boundary.md)
proposed a closed `REQUIREMENT_VOCABULARY` to stop it over-specifying.

**Both are reinventing `PL_007` §6.4, which shipped as the resolution of `PROG-D15`.** The repo already
solved progression→item reference, and solved it the same way, for the same stated reason:

```rust
pub enum InstrumentMatch {
    Any,
    Specific(ResourceKind),   // fungible tools
    ItemDef(ItemDefId),       // exact item
    ItemTag(InstrumentTag),   // NEW — category; PROG-D15's "InstrumentClass match"
}
```

`ItemTag` **is** the under-specified reference: progression names a *tag*, item decides what wears it.
No new type, no new vocabulary, no new register.

Three details worth carrying into the pool design, because they were learned the hard way there:

- **`PL_007` deliberately does NOT define one global resolution rule.** Its first draft did, and it
  *"would have changed PROG_001's training semantics by side effect"* — `ItemClass::Tool` is never
  equippable, so an equipped-only rule kills every *train-X-while-using-tool-Y* rule. Each consumer
  resolves its own subject: PROG_001 → the turn's instrument; DF07 → the `main_hand` item. **The pool
  must not add a global rule either.**
- **Tags are author-declared rather than a closed enum**, *"for the same reason RES_001's kinds are"* —
  which is `EPL-A2`, arrived at independently, twice.
- **`ITM-C7` warns at bootstrap on an unreferenced tag.** That is already the assembly-closure check
  `PPB-A5` describes, for this one slot.

> **`ICT-A3`.** Retract `PPB-A2`① and `PPB-A3`. Cross-module item reference is **tag matching on an
> author-declared `instrument_tag`**, and the consumer resolves the subject. The design was right; it
> was already built.

### 6.1 `EPL-A2` needs a distinction it does not currently make

§2's `E` column is not in `EPL-A2`'s model. There are **two kinds of closed set**, and only one of
them is a pool slot:

| | members fixed by | example | pool slot? |
|---|---|---|---|
| **fixed-member** | the **engine binary** — every reality gets the same list | `ItemClass` (8) · `StatSlot` (10) · `StrikeKind` · `AffordanceSet` · `VitalKind` | **no** |
| **open-member** | the **reality**, authored per-manifest | `instrument_tag` · `item_archetype` · `equip_slot` · `progression_kind` · `MaterialKindId` | **yes** |

`RES_001` already names both — §3.2 *"Engine-fixed enums (closed sets)"* vs §3.3 *"Author-declared
kinds (open per-reality)"* — and `PL_007` practises the same split without naming it. **Fold this into
`EPL-A2`:** a module registers *both*, but only open-member slots enter the pool; fixed-member sets are
referenced, never filled, and cannot produce a dangling reference.

### 6.2 One ambiguity this reading exposes, unresolved

`ITM-A4` **LLM-zero-item-math** reads: *"The LLM … never emits a heal amount, a damage number, a
durability value, a price, or **any `ItemDef` field**."*

In context that governs the **runtime agent** — the sentence is about `Item:*` and `UseItem` payloads.
But taken literally it also forbids the **build-time generation pipeline** from producing
`display_name`, which is the one field the LLM is *supposed* to author (`CPL-A10`: the LLM is the
creative vocabulary). Two different models at two different times, one axiom.

**Not resolved here.** Flagged because it must be settled in `PL_007`'s own words before the item
generator is built, and because the same ambiguity likely exists in every `LLM-zero-*` axiom the repo
has (`COMB-A1`, `TG-A1`).

---

## 7 — What item's L2 generator actually does

Per `EPL-A6`, internally two-layered. Reading §2's classification, the halves are now concrete rather
than assumed:

| half | produces | inputs |
|---|---|---|
| **procedural spine** | the tier-2 `ItemDef` table: archetype × grade × affix expansion · `StatModifier` values · `price` · `max_charges` · `reach` · `weight` · `also_blocks`/`two_handed` consistency | frozen pool + item's magnitude policy + seed |
| **LLM vocabulary** | `display_name` and `description` per generated def; affix wordlists | the frozen pool + the corpus |

**And it must run with the LLM half empty** (`CPL-A10`): a hand-authored name list produces a complete,
valid `ItemDef` table. That is the falsifiable property to test first — not the model output.

---

## 8 — Open

1. **`ITM-A4`'s scope** — §6.2. Blocks building the LLM half.
2. **Where do item magnitudes come from?** Progression has `PGN-A15`'s numeric policy artifact.
   Item has none. Same shape, separate artifact (`EPL-A3`: every generator owns its numbers) — but it
   has to be designed, and *"damage of a grade-3 sword"* is a balance question, not a lookup.
3. **Do crafting recipes reference tier 2 or tier 1?** `RecipeId` is `RES_001`-reserved and
   `14_crafting/` is a V2 reservation, so nothing binds yet. If recipes reference `ItemDefId` (tier 2)
   they are **post-freeze**, which makes crafting an L2 module reading item's L2 output — and
   `PPB-A6` forbids that. If they reference `item_archetype` + `item_grade` (tier 1) they are clean.
   **This is the first real test of `PPB-A6` and it should be run before adopting it pipeline-wide.**
4. **`item_archetype` arity.** Set at 64 by analogy with the other slots, on no evidence. The real
   bound comes from one reality's actual taxonomy — measure before fixing it, the way `PL_007` §6.1
   fixed the 12-slot cap from a *derived* constraint rather than a guess.
5. **Affix roll ranges.** `item_affix`'s pool member carries the affix's *identity*; its magnitude
   range is item's numeric policy (#2). The split is stated but not designed.
