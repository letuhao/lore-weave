# Seams and triggers — what feature #1 measured and did NOT decide

**Status:** register · **Date:** 2026-08-02
**Replaces:** `2026-08-02-handoffs-to-features.md`, which was itself a scope violation — it made
**proposals** about other features' mechanics.

---

## Why this file is a list and not a design

Actor hub is **feature #1 of roughly a thousand**, across dozens of categories. **A plugin exists so that
adding feature N+1 does not touch feature #1 — not so that feature #1 can specify feature N+1.**

The prior version of this file carried worked proposals for combat, progression and ownership: a damage
model, a threshold rule, a tier-fall enum, a currency representation. **None of that was ours to write.**
Writing it costs the owning feature its design freedom and costs this round its finish line.

> **The rule for every row below: a MEASURED FACT about shipped code, the SEAM it touches, and the TRIGGER
> that makes it someone's problem. No mechanics. No proposals. No numbers we chose.**

Everything deleted from the previous version survives in
[`2026-08-02-actor-dataflow.md`](analysis/2026-08-02-actor-dataflow.md) (the derivation record) and in the
[RUN-STATE](../../plans/2026-08-02-actor-substrate-RUN-STATE.md). **Nothing is lost; it is de-scoped.**

---

## The register

| # | measured fact | seam | trigger — whose, and when |
|---|---|---|---|
| **S-1** | `attack.rs:135` and `:185` both floor at `.max(1)`, so a landed hit always deals ≥1; `:109-111` returns 0 on a miss | a far weaker attacker can defeat a far stronger one by attrition | **combat**, when it designs damage |
| **S-2** | `StatSlot` is used by name inside the shared fold (`resolve.rs:131`) and the shared stat block (`block.rs:76`, `:89`) | the slot table cannot become combat-private until those two uses move | **combat**, before `C-2` |
| **S-3** | `melee_archetype` and `slot_defaults` are `[i32; SLOT_COUNT]` over ten combat slots; `StatBlock::from_defaults` exists because *"playable with zero declaration is a hard requirement"* | the only source of a playable actor today is combat-shaped | **combat or a future archetype feature**, when either is designed |
| **S-4** | `block.rs:89` `self.set(StatSlot::MoveRange, …)` overwrites a value six modifier layers just resolved | an Equipment `Flat(+2)` on `MoveRange` is accepted and silently discarded | **combat**, when it owns the derivation |
| **S-5** | `ruleset-core/src/progression/validate.rs:212-219` refuses a ladder whose `tier_max` does not rise; the message states a genre claim aloud | a reality wanting a rank to be revocable cannot say so | **progression**, when it designs tiers |
| **S-6** | `progression/mod.rs` declares caps as `u64`; `decode_cap` reads `r.u64()?` unbounded | a width decision at the hub tier narrows what progression can declare | **progression**, when a cap is authored |
| **S-7** | `ResourceDecl.min` is signed *"because a pool may model debt"* and is an **absolute** value | any fractional representation of `current` needs a conversion | **resource**, when pools are designed |
| **S-8** | `docs/specs/2026-08-02-item-data-structure.md` exists and inherits `D-1`..`D-109`; this round continued to `D-291` | the item round is building on a superseded snapshot | **item/ownership**, at its next checkpoint |
| **S-9** | `EntityId(u64)` is *"identity within a reality"*; `GoneState` is keyed by `EntityRef { uuid, aggregate_type, reality_id }`; **zero conversion sites exist** | the hub cannot key a platform-tier lifecycle operation | **platform**, when the hub first meets it |
| **S-10** | `crates/ruleset-loader/src/layer.rs:22` ships `enum Layer` with an ascending fold order | a second unqualified "layer" would be one name for two concepts | **already handled** — this round uses `fold_layer` |

## Added by the BUILD — measured against `crates/actor-hub`, 2026-08-02

The rule is unchanged: **a measured fact about shipped code, the seam it touches, and the trigger.** Each
row below is something the implementation ran into and deliberately did not answer.

| # | measured fact | seam | trigger — whose, and when |
|---|---|---|---|
| **S-11** | `QuantityOrdinal` (`actor-hub/src/ordinal.rs`) carries a `u16` and **no digest**; its derived `PartialEq`/`Ord`/`Hash` compare reality A's ordinal 3 equal to reality B's | `QTY-A14` requires *"any datum that leaves the island carrying an ordinal MUST carry the digest that gives it meaning"*, and no such carrier exists | **whichever feature first moves a quantity across a reality boundary** — the same crossing `S-9` names for identity |
| **S-12** | plugin ordinals are assigned once and never reused **by convention only**; `ruleset-core/src/never_reuse.rs` mechanises the quantity space and nothing mechanises the plugin space | a renumbering silently redefines every stored attachment | **`M-8`, when plugin #2 is declared** — an ordinal space with one member cannot be renumbered, so a check built today has no failing input |
| **S-13** | the fold resolves derivations in **one pass** against modifier-only values (`actor-hub/src/fold.rs`), which is the shipped shape — `resolve_block` runs its modifier loop and *then* derives `MoveRange` from the finalised `Speed` | a derivation **of a derivation** is not expressible, and adding one needs a dependency order the hub does not have | **the first feature that declares a chained derivation** |
| **S-14** | the only clamp in the fold is the **representation's** — the `i64` accumulator saturating into one `i32` slot, reported as `Capped` | `U-2`: the shipped clamp channel is a two-pass ordered parameter pair with intersect semantics and a floor-wins contradiction rule, and a `u8` fold-layer ordinal cannot express *"and also a clamp channel"* | **the first feature that declares a bounded quantity** (`U-4` — the ceiling MODEL is that feature's) |
| **S-15** | after `Actor::attach` initialises a quantity from its declaration, **nothing in the hub writes it again** — there is no damage, no regeneration, no expenditure, no progression verb | whatever changes a stored quantity also decides what event records the change (substrate §2: *"canon is what is written to the ledger"*) | **the declaring feature**, when it defines how its own quantity moves |
| **S-16** | the fold produces a **derived copy** (`FoldReport`) and it carries **no `(reality_id, seq)`**, because a pure crate has access to neither — the hub takes an actor, a registry and two row slices, and none of the three carries a reality | substrate §2 requires *"every derived copy carries `(reality_id, seq)`"*, so the stamp is the CALLER's and nothing enforces that it happens | **whichever host first persists or transmits a fold result** — the same host that owns the ledger write |
| **S-18** | `ruleset-core` already ships a **per-quantity-ordinal bound** — `ResourceDecl { quantity, min, base, ceiling: CeilingBinding, … }` held by `ResourceTable` over the same ordinal space, carried by every `Ruleset`, and validated (`ResourceError::BadBounds`) — and **the hub does not consult it**: `HubRegistry` takes the initial value from the attaching plugin's `QuantityDecl`, and the fold clamps with nothing but the `i32` emit | a reality can declare `ceiling: Fixed(1000)` for a quantity and the fold will resolve it to 10 500 with no `Capped` record; `QuantityDecl.initial` and `ResourceDecl.base` are two declarations of one fact with nothing reconciling them | **resource**, when pools are designed — reconciling the two decides **what a pool is**, and answering that from feature #1's chair is the encroachment this round exists to stop |
| **S-17** | `Actor` holds a bare `EntityId` and **no `Gen`**; substrate §8 measures that `EntityId` is a bare `u64` (`sim-core/src/types.rs`) whose generation lives beside it in `entities: BTreeMap<EntityId, Gen>` | *"a bare `EntityId` is a dangling handle"* — staleness is detectable only when a caller carries the `Gen` and threads it through a `Precondition`, and the hub does not | **the substrate**, as `M-15`/`U-8`'s threading — unchanged by this build, and the hub deliberately did not invent a second generation |

---

## What feature #1 deliberately did NOT decide

Damage · thresholds and bands · tier ladders and falls · currency and denominations · pools and regeneration
· the log domain and power scale · ceilings beyond the one the fold needs · archetypes · spawn · maps and
places.

**Each is a category with its own feature. Feature #1 measured where it touches them and stopped.**
