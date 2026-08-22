# Item data structure — the substrate under ownership, inventory, equipment and transfer

**Status:** DESIGN, awaiting PO review · **Date:** 2026-08-02 · **Base:** `50bff49a4`
**Run state:** [`docs/plans/2026-08-02-item-substrate-RUN-STATE.md`](../plans/2026-08-02-item-substrate-RUN-STATE.md)
**Companion:** [`2026-08-02-item-dataflow.md`](2026-08-02-item-dataflow.md) — **PART I** the reasoning,
measured evidence and open register; **PART II (§14–§19)** the specification proper: the declaration
surface, the runtime shapes, the closed operation set, the validator ladder, the events, and the acceptance
criteria with their bite-tests. **Where the two disagree, the dataflow spec wins.**

**Inherits and does not re-open:** [`2026-08-02-actor-data-structure.md`](2026-08-02-actor-hub/analysis/2026-08-02-actor-data-structure.md)
and its run state (`D-1`..`D-109`). Decisions here are prefixed `ITD-`; open rows `IO-`; rot rows `IR-`.

> **Why this document exists, in one line.** The actor round named item by name — `D-101`/`O-121`:
> *"feature #2 (**items**) needs every one of these and needs no actor."* Item is the first feature to
> stand on the engine half, and it is the substrate under every ownership feature. It is also carrying
> ~3 155 lines of design written **before** the actor round, and much of that design is now wrong.

**Scope:** what an item IS, who may own it, how it moves, and how it reaches an actor's numbers.
Trade/economy is **out** (`D-22`) · crafting recipes are **out** · loot generation is **out** (`COMB_004`
owns the rules; this round owns the seam) · combat vocabulary is **out** (`D-14`) · splitting engine core
from the actor feature is **out** (`C-3`, its own round).

---

## 1. What this settles, and the one sentence that settles most of it

> **`ITD-1` — OWNERSHIP and LOCATION are two different questions, and one field is answering both.**

`EF_001` §3.1 gives an entity a single `location: EntityLocation`, whose `HeldBy { holder }` variant is
read everywhere as *"this actor owns this"*. It is not. It is *"this actor is carrying this"*. Every
interesting thing an ownership system must express lives in the **gap between the two**:

| the fiction | location | owner |
|---|---|---|
| a borrowed sword | `HeldBy(disciple)` | the master |
| a stolen sword | `HeldBy(thief)` | the victim — **and this is what makes it theft** |
| a sect treasury | `InContainer(vault)` | the sect |
| goods left with a merchant | `InContainer(shop)` | the consignor |
| an heirloom in the family hall | `InCell(hall)` | the family |
| a corpse's gear | `InCell(death_cell)` | nobody — **unowned is a state, not a missing value** |

Collapse the two and none of these is representable. **This is the `Suspended`-beside-`Destroyed` defect
one tier down** — the actor round's §5.3 found one field answering two unrelated questions and split the
axis; this is the same shape, in the feature the actor round handed the ownership edge to (`D-25`).

**And the corpus already discovered it — for exactly one entity type.** `entity_binding` carries
[`cell_owner: Option<EntityRef>`](../03_planning/LLM_MMO_RPG/features/00_entity/EF_001_entity_foundation.md#L144)
**beside** `location`, and `EntityRef` enumerates
[`Actor | Cell | Item | Faction`](../03_planning/LLM_MMO_RPG/features/00_entity/EF_001_entity_foundation.md#L162).
`WSA-F4` reads that field as *evidence*: the economy work needed an owner reference and **reached past the
closed `EntityId` to get one**. It got the axis right, and then applied it to cells only. Items — the
things ownership is actually about — were left with `HeldBy` doing both jobs.

**Independent arrival, from outside.** Bethesda's Creation Engine separates them and states the
consequence in one line: *the owner of the object overrides ownership by the container or actor; ownership
notes whether the item is owned by an NPC **or a faction**; if you are not at the correct rank in the
faction, taking it is considered **theft**.* Two engines, two directions, one conclusion — and one of them
is this repo.

**And the sandbox survey is close to unanimous — six of seven** (dataflow §10.0). Wurm links every item to
*"the player who last dropped it"* and then computes protection from the **gap** between owner and
position. Space Engineers puts an owner **and** a share setting on every powered block, independent of
where it is. ARK makes each structure tribe-owned or personally-owned and keeps that through the owner
leaving the tribe. Dual Universe ships a whole access-control engine. Eco puts **law** above ownership.
Ultima Online expresses it as access tiers on a container.

**The seventh is the one that decides it.** Rust has **no owner field at all** — a tool cupboard holds an
authorization list, and *"any player may remove locks applied and left unlocked."* Possession plus physical
access is the entire model, and it is correct **for Rust**, where taking your neighbour's things is the
intended loop rather than a transgression. ⇒ **`ITD-1` is the field that makes *theft* a concept instead of
an event.** A fiction with sects, inheritance, debts and betrayal sits at the opposite end of that axis.

## 2. What an item IS — and stackability is EARNED, not declared

> **`ITD-2`.** A thing with **no per-instance state** is a **QUANTUM**: `(owner, location, def_id, count)`,
> with **no row per unit**. A thing that acquires per-instance state becomes an **INSTANCE** with an id.
> **The transition is an operation, not a declaration.**

`ITM-A2` (PL_007:94-99) says the author picks *entity* or *resource row* **at declaration time**, forever.
That asks an author to predict which of their items will ever need identity, and `PL_007b` §2 records the
resulting hole itself, calling the merchant's 50 identical daggers *"the awkward middle"* and deferring it
to `ITM-Q3`/`ITM-D1`. **It is not awkward. It is the wrong question.**

EVE Online answers it correctly and has run the answer at scale for two decades: **packaged** items *"only
have 3 attributes: location, item type and quantity — there is not a database record for each unit in a
stack"*; an **assembled** ship gets hit points, a cargo hold and fitting slots, and *"can no longer be
stacked, because it is no longer identical to every other ship of that type."* The market rule falls out
of the same fact rather than being bolted on: you may only sell a **packaged** item, *"as it needs to be
identical to every other item of the type so the buyer knows what they are getting."*

| | quantum | instance |
|---|---|---|
| storage | one row per `(owner, location, def_id)` with a `count` | one row per thing |
| identity | none — 50 arrows is a number | an `ItemId`, never reused |
| may carry | nothing per-unit | charges · durability · provenance · custom name · bindings · a container interior |
| becomes the other by | **acquiring** per-instance state (`assemble`) | **shedding** it (`repackage`) — destructive, fiction-visible |
| cost at scale | **O(1)** in the count | O(n) |

**This passes `D-98`'s discriminator, which `ITM-A2` does not.** The engine's arithmetic genuinely
differs per member: a quantum **folds by addition** and a merge of two quanta of the same def is a legal,
information-preserving operation; two instances never merge. `ItemClass`'s eight closed variants do **not**
pass it — the engine treats all eight uniformly and only the item feature knows their names, so
`ItemClass` is the item feature's vocabulary and must be **declared, not an engine enum** (`IR-4`;
`06_item_contract.md:64` currently states the opposite — *"engine-fixed, 8 variants. A reality cannot add a
9th"*).

**And Minecraft ships the rule as a load-time validator.** It has always had the behaviour emergently —
*"any differences in NBT data will prevent items from stacking"*, so damage, enchantments, a custom name or
lore each break a stack, and there has never been a `stackable: bool`. In 1.20.5 unstructured NBT became
*"structured **components**, parsed and **validated when the item is loaded**"*, and one of the validations
is: **`max_stack_size` greater than 1 cannot be combined with `max_damage`.** That is `ITD-2` as a schema
rule in a shipping engine — a thing that can carry per-instance state may not declare itself stackable —
and it gives our L2 validator ladder a **named check to implement** rather than a principle to uphold.

**What this replaces.** `ITM-A2`'s cross-check `ITM-V10`/`ITM-C2` — *"an `ItemDefId` colliding with any
`resource_kinds.kind_id` is rejected at canonical seed"* — exists to police a boundary that `ITD-2`
removes. A quantum is `(def_id, count)`; it is **not** a `ResourceBalance` and needs no `ResourceKind`.
Currency, ore and rice are quanta of item defs. **One store, two shapes** — replacing `ITM-A8`'s *"one
inventory, two stores"*, which needed a union projection precisely because the two stores had different
identity models.

## 3. Who may HOLD — and this closes `O-118b`

> **`ITD-3`.** `Owner ∈ { Actor · Place · Item · Group · None }` and `Location ∈ { Cell · HeldBy(actor) ·
> InContainer(item) · Embedded(parent) }`. **They are separate fields with separate vocabularies.**
> `None` is a value, not a null: **unowned** is a real state (a corpse's gear, wilderness ore, a dropped
> coin) and it is what makes *claiming* a legal operation.

The owner vocabulary is **not new** — it is `EF_001`'s existing `EntityRef { Actor | Cell | Item |
Faction }` (EF_001:162-167), which already enumerates exactly the four holders and already reserves
`Faction` (marked *V3*). This round promotes it from *"the discriminator RES_001 needed for cell
ownership"* to **the owner axis for everything**, and renames `Cell → Place` per `WSA-R19`.

**`D-93` left this open and named the residue precisely** (`O-118b`): *"a sect **treasury** IS held by the
group as such, and a faction is neither a place nor a person — one question for the social system, with a
stated shape to answer against."* Here is the shape, and the answer is that **it does not need
`ActorKind::Group`**. A group is not an actor — it never takes a turn, never holds a quantity, never has a
lifecycle of its own in this substrate. It is only ever the **subject of an owner edge**. So the cost of
group ownership is **one variant on the owner enum**, not a fifth `ActorKind` and not a new entity class.

> **The line, stated so the social feature knows what it is inheriting.** Item core owns **who owns it**.
> It does **not** own **who may act on behalf of a group owner** — that is a permission relation, `ITD-9`.

## 4. Equipment is ROWS — the trait comes out

> **`ITD-4`.** `PL_007` §6.3's `impl EquipmentStats for World { fn equipped_modifiers(&self, actor) -> Vec<StatModifier> }`
> is **deleted**. Equipping writes `actor_equipment` **and** its `ModifierRow`s in **one**
> `commit_with_modifiers` call (`D-50`). Nothing is derived at read time, so there is nothing to
> invalidate.

PL_007:435-455 is feature code **the engine calls during resolution**. That is precisely the trap the
actor round's dataflow §13.1 names and closes: *"read that sentence as an implementation and it means —
during the tick, feature code runs. Which requires the engine to call into features, which requires the
engine to hold a list of features, which is `D-2` violated at the worst possible layer."* `D-27`
generalised `CPL-A17` to close it: **a contribution is DATA, never CODE.**

Three defects PL_007 documents dissolve rather than get fixed, and that is the test that the change is
structural rather than stylistic:

| PL_007's defect | what happens to it |
|---|---|
| **the `blocked_by_primary` double-count** (§6.3) — a two-handed weapon occupies two slots with the same instance, so naive iteration applies its modifiers **twice**, which is *"why `blocked_by_primary` exists as a field rather than being inferred"* | **gone.** The equip writes its modifier rows **once**, at commit. There is no iteration to double-count. The field survives only for its real job — making unequip a single-key operation |
| **`equipment_version` monotonicity** (§6.3, `ITM-Q1`) — *"a same-turn equip→unequip→equip sequence would not bump it… V1 is safe because one action per turn"* — a correctness argument resting on a turn-economy accident | **gone.** No cache, no version, no `StatEpoch` input. `D-28`: staleness is **impossible**, not detectable |
| **the item-side destroy cascade** (§8.4, review finding 3 — *"`actor_equipment` would reference a destroyed entity and DF07 would keep applying its modifiers"*) | **gone.** Destroying the item removes its rows in the same commit, by signature |

**And `ITM-A3` cannot survive as written** (PL_007:101-105): *"`Vec<StatModifier>` against the closed
DF07-owned `StatSlot` enum (10 V1 slots)."* `D-10` opened the slot set, `D-100` measured it to be
**combat's** vocabulary, and `D-105` split it into two concepts being dismantled by `C-2a`/`C-2b`/`C-2c`.
**An item design that names `StatSlot` is building on a condemned structure.** The replacement is
`D-27`'s row, unchanged, with `target: QuantityOrdinal` naming a quantity the *reality* declared.

**One distinction the rewrite must not lose.** `EquipDecl.requirements` (PL_007:387-393) and a modifier's
`condition` (`D-29`) look alike and are not: a **requirement** is checked **once, at commit**, and refuses
the equip; a **condition** is a declared threshold ordinal evaluated **every tick**. Requirements stay a
validator. Conditions are one bit test in `threshold_active`.

## 5. Transfer — and the single-place rule IS the anti-duplication mechanism

> **`ITD-5`.** An instance transfer is **one write to one edge**. `EF_001` §3.1's *"an entity is in
> EXACTLY one place at a time"* is not housekeeping — **it is the mechanism that makes item duplication
> unrepresentable rather than merely invalid.** Label it as such, and never weaken it for a cache.

The prior art is unambiguous about both the failure and the fix. OpenMU, rebuilding a game whose economy
was destroyed by duping: *"each item has its own row which is identifiable by a GUID as primary key.
Therefore, there can only be one item with the same Id and only assigned to one account."* The general
prescription: *"design ALL item movements (spawn, loot, trade, shops, etc.) to use atomic, durable
transactions."* And the root cause, stated by the same source: *"every item duplication trick which I know
depends on the **timing of saving** item data"* — a memory-versus-database desync, with *"no optimistic or
pessimistic lock strategies which could detect if there was data saved for the same account before from
another session."*

**Two things this architecture already buys, and they should be stated rather than assumed:**

1. **There is no save step to mis-time.** `D-36` makes the event log the SSOT and `D-23` makes a
   materialised row a fold over it. The desync class that produces most dupes needs two writable copies of
   the truth; there is one. *(This is a claim about the design, not a measurement of an implementation —
   see `IO-3`.)*
2. **A transfer needs no two-phase protocol, and `D-22` is why.** The event-sourcing literature is clear
   that a transfer spanning two aggregates in different consistency boundaries needs a reservation
   pattern — measured at *18 of 50 transfers succeeding at 1.24 req/s* for naive two-aggregate locking
   versus *all 50 at 48 req/s* for reservation. **`D-22` puts both parties in one island by
   construction** (*"a transfer is face to face; co-located actors are in one island"*), so both edges are
   inside one consistency boundary and the primitive is a single atomic write. **This gives `D-22` a
   second, independent justification it did not have** — it was argued from feature scope, and it is also
   the reason the transfer needs no reservation machinery. A cross-island transfer is refused by name, and
   *that refusal is what keeps the primitive simple.*

> **`ITD-6` — a quantum transfer is a TWO-DELTA; an instance transfer is a ONE-EDGE MOVE.** Different
> arithmetic, one commit primitive. Conservation is **checkable** for quanta (the `sources`/`sinks`
> declaration the actor round's dataflow §2.6.7 already designed) and **structural** for instances — an
> instance cannot fail to conserve, because there is only one row and it moved.

## 6. Item lifecycle — the four axes, and one of them is empty

> **`ITD-7`.** An item has **existence** (declared vocabulary), **tier** (engine) and **residency**
> (engine, fiction-invisible). It has **no control axis** — nothing drives an item.

`PL_007` §8.1 is written against `EF_001`'s single closed enum and spends fourteen lines resolving a
contradiction that **does not exist once the axes are split**. Its `ITM-C4` requires an equipped item's
lifecycle to move *"in lockstep with its holder"*, and §8.1 corrects an earlier draft that said items never
suspend. Both halves are about `Suspended` — which is **residency, not existence** (`D-12` / actor §5.3
axis 3), and residency is engine-owned and **invisible in the fiction**.

⇒ **`ITM-C4` is not a fiction rule at all.** *Of course* a passivated actor's gear passivates with it —
that is the residency cascade doing its job, and by the invisibility law it must change **no**
fiction-visible byte. The paragraph that fixed the contradiction can be deleted along with the
contradiction.

The empty fourth axis is worth stating rather than passing over: the actor round derived four axes from
the actor. **Item has three, and the missing one is missing for a reason a reader can check.** Axes that
can be individually absent are orthogonal; a bundle would have travelled together. *(A container's
interior is `SPG-A1`'s space-holder question, not a control edge — see `IO-6`.)*

> **`ITD-8` — an item's disposal is `D-51`'s, unchanged: cache eviction, not deletion.** A tier-2 item row
> is a fold over the ledger; freeing it frees a slot. **`EntityId` is never reused; the slot is.** This is
> also why `ITD-5` is safe under eviction — the single-place invariant lives in the ledger, not in the row.

## 7. Permissions are a RELATION, and they are NOT item core's

> **`ITD-9`.** *Who may deposit into, or withdraw from, a thing owned by a group* is a **pair-keyed
> relation** — `D-74`'s declaration kind ② — owned by the **social / faction** feature. Item core owns the
> owner edge and stops.

The prior art converges on one shape and one warning. EVE: up to **seven** hangar divisions per office,
each with **roles** — and the split that matters, *"**Query** access allows viewing contents but requires a
**Take** role to remove items."* WoW guild banks: *"per tab, per guild rank"*, deposit/withdraw separately
grantable, **withdrawal limits**, and an **access log** of the latest deposits/withdrawals per tab.

Two things fall out. First, the rights vocabulary is **at least** `view | deposit | withdraw`, with a
**rate limit** on withdraw — a lesson learned the expensive way in both games. Second, the shape is
`(group, container, rank) → rights`, which is a relation and not a field on anything.

**It leaves item core by `D-24`'s own test — *the game is playable without it*.** Remove permissions and
you have a game where a group's chest is open to its members. Remove *ownership* and there is no game.
**A thing you can remove and still ship is not substrate.**

## 7.4 `ITD-15` — STACK MANAGEMENT is first-class, and taking it seriously deletes three operations

> **PO requirement:** *we must have stack management — some items have only **one** stack, some are **n**
> stacks.*

Accepted, and it is `max_stack: u32` on the def (§14.3): **`1` = never stacks · `n` = stacks to n.** Making
it first-class rather than incidental produces three consequences, and the first is a defect in this
round's own output.

### 🔴 The defect it exposes — in the rot sweep, applied an hour earlier

`IR-16` restated `PL_007b` §4.1's slot accounting over the new shape and concluded:

> *"A quantum stack is **one row whatever its count**, so *a resource kind costs one slot regardless of
> amount* falls out of the storage shape instead of being a special case beside it."*

**That is storage-true and slot-WRONG.** It silently kept `PL_007b`'s deliberate *bag-of-holding* model —
*"1 copper and 10 000 copper both cost one slot"* — which is exactly the model a `max_stack` **replaces**.
With `max_stack = 99` and 250 arrows, the player has **three stacks**, and any UI, capacity rule or prompt
digest that says *one slot* is lying to them.

> **Correction: STORAGE and SLOTS are different questions.** One row per key with an unbounded `count`;
> **slots consumed = `ceil(count / max_stack)`**, and an instance consumes 1. `max_stack` is a
> **capacity-accounting** rule, not a storage rule.

**Recorded rather than quietly fixed** because it is the round's own shape: *one field answering two
questions*, this time `count`.

### The two operations that stop being operations

**`merge` is what the KEY does.** §15.1 makes a quantum's key `(owner, location, def)` and **unique** — so
two quanta with the same key **cannot coexist**. Dropping 30 arrows where 20 of yours already lie is not a
merge operation; it is a write to a row that exists. Different owners in one cell keep different keys and
stay separate, which is correct.

**`split` is `move` with a count.** Under a unique key, *"split a stack"* only means *take n out and put
them somewhere else* — which is a partial move. So **`move`, `give` and `lend` each carry a `count`**
defaulting to the whole row, and the separate split disappears.

### The operation set, recounted

| | |
|---|---|
| §16 as written | **12** |
| − `repackage` (`ITD-13`, one-way) | 11 |
| − `merge` (structural — the key enforces it) | 10 |
| − `split` (`move` with a count) | **9** |

**`birth · move · give · lend · claim · release · assemble · mutate-state · destroy`.** The conservation
law (`ITD-11`) is unchanged: every one of the nine conserves `Σ count` per def except `birth` and
`destroy`, which remain the only declared source and sink.

> **Three operations removed by taking a requirement seriously rather than by simplifying.** That is the
> fourth time this round a rule stopped needing to be a rule — after `ITM-C4`, §8.4's item-side cascade,
> and `ITM-Q1`. **The pattern is worth naming: when a mechanism dissolves under a requirement instead of
> surviving it, the mechanism was compensating for a missing distinction** — here, storage versus slots.

## 7.5 The operation set is CLOSED, and it is where the conservation law lives

> **`ITD-11`.** Item core has **twelve** operations — `birth · move · give · lend · claim · release · merge
> · split · assemble · repackage · mutate-state · destroy` — and **every one of them either CONSERVES or is
> a declared SOURCE/SINK**. `birth` and `destroy` are the only two that are not conservative, and each is a
> declared, ledgered event.

Full table with preconditions, writes and fiction-visibility: dataflow §16. Two things the closure buys:

- **`Σ count` per def is an invariant with a property test that can red** (dataflow §16.1). **Duplication
  is exactly a violation of it**, so the test's subject is the failure mode `ITD-5` is about — and unlike
  most invariants in this pair of documents, it needs no infrastructure that does not exist.
- **Six operations a designer reaches for are compositions, not primitives** — *trade* is two `give`s,
  *loot* is `COMB_004` choosing which `birth`s to make, *craft* is `destroy`×n + `birth`, *repair* is
  `mutate-state` on a `Durability` slot, *rename* is `mutate-state` plus a permission, and *cross-island
  transfer* is refused by name (`D-22`). **A closed set whose near-misses all decompose is closed in the
  right place** — the test `PL_005`'s five interaction kinds passed with their closed-set proof.

**Equip and unequip are deliberately NOT operations on an item.** They write `actor_equipment` and
`modifier_rows` through `commit_with_modifiers` and touch no item field — `ITD-4` restated as an absence
from a list.

> **`ITD-10` — a def reference inside a runtime ROW is an interned index, and that index is a CACHE.**
> `D-76` addresses content by opaque id and §1 of the dataflow commits that item creates **zero** new
> ordinal spaces; a 4-byte index in the hot row appears to break both. It does not, under one written rule:
> **the ledger and the hashed bytes carry the opaque `def_id`; the index is rebuilt from the loaded content
> manifest, never written to the ledger, and not stable across loads.** `P-F` applied to a field, the same
> shape `D-49` gave `control` and `status_active`. **The tell that it is a cache: it may be renumbered on
> any load, and nothing may compare two of them across a load boundary.** Written down because an
> unwritten one gets persisted.

## 8. What item does NOT need — recorded because absence is the evidence

| | |
|---|---|
| **a new ordinal space** | An item def is **content**, addressed by an **opaque id** (`D-76`). `T0-4`'s never-reuse generalisation *"stops at the ruleset boundary and does not follow content into the manifest"* — so item creates **zero** new ordinal registries to guard. **This is the first independent confirmation that `D-76` drew the seam in the right place**, and it was available only from a second feature |
| **a field in `ActorQuantities`** | `D-30`'s acceptance test: adding item touches **zero files** in actor core. Equipment writes `ModifierRow`s; inventory is the item's own edge (`D-25`). ✅ |
| **an engine that knows what an item is** | the engine folds rows. `D-27` |
| **`ResourceKind::Item`** | already withdrawn by `PL_007c` §12.2 — and `ITD-2` withdraws the *other* half too, the `resource_kinds`-versus-`item_defs` boundary itself |

## 9. Rot ledger — `U` = update, `D` = delete, `K` = keep and label

Line numbers against the files at `50bff49a4`. The **cost** column is what the removal touches: `∅` = doc
only · `S1` = authoring/manifest surface · `⛓` = would move a digest **if any reality were pinned**, and
none is (`D-11`).

### 9.1 `PL_007_item.md` — the substrate half

| id | site | action | cost |
|---|---|---|---|
| `IR-1` | :94-99 `ITM-A2` — the representation rule, author-picks-at-declaration | **U** → `ITD-2`. Stackability is earned by absence of per-instance state; the transition is an operation | S1 |
| `IR-2` | :101-105 `ITM-A3` — *"against the closed DF07-owned `StatSlot` enum (10 V1 slots)"* | **U** → `ModifierRow.target: QuantityOrdinal`. `D-10`/`D-100`/`D-105` | S1 |
| `IR-3` | :113-118 `ITM-A5` — equipment is a slot assignment, not a location | **K** — survives intact, and is now the *model*: it is the same *unrepresentable-not-merely-invalid* discipline as `ITD-5` | ∅ |
| `IR-4` | :266-285 `ItemClass` — closed 8-variant engine enum | **U** — fails `D-98`'s discriminator; the engine treats all eight uniformly. Declared vocabulary | S1 |
| `IR-5` | :120-123 `ITM-A6` — V1 inventory flat, `InContainer` reserved | **U** — a container is an item with an interior (`SPG-A1`); the depth-≤1 claim and *"`cyclic_holder_graph` is structurally unreachable"* both lapse. **`SPG-A4` supplies the guarantee**: containment is a strict acyclic tree | S1 |
| `IR-6` | :196-208 `ITM-C4` — lifecycle lockstep with the holder | **D** — the contradiction it resolves does not exist once residency leaves the existence axis (`ITD-7`) | ∅ |
| `IR-7` | :215-238 §4.3 `Provenance` on the row | **U** — under `D-23` the ledger holds the history. The row is a **derived copy** and must carry `(reality_id, seq)` per `D-53`, or be deleted (`D-39`). ⚠ **Amended by the sandbox survey:** Wurm's creator **signature** is lossy *in proportion to the item's own quality* — *"unclear signatures have some letters of the name replaced by a dot."* **A derived view may be deliberately lossy, and the lossiness may itself be content** — good enough to recognise a master's work, not good enough to be proof | ∅ |
| `IR-8` | :379-399 `EquipDecl.modifiers: Vec<StatModifier>` | **U** → `Vec<ModifierRow>` minus `actor`/`source`, which the commit supplies | S1 |
| `IR-9` | :415-481 §6.3 the whole `EquipmentStats` seam, incl. :437-455 the impl and :451-454 `equipment_version` | **D** → `ITD-4`. This is the largest single deletion in the sweep | ∅ |
| `IR-10` | :459-466 the `blocked_by_primary` double-count and the `equipment_version` monotonicity note | **U** — both dissolve; keep `blocked_by_primary` for single-key unequip only | ∅ |
| `IR-11` | :622-654 §8.1 lifecycle table + the suspension correction | **U** → four axes. The two `HolderCascade` suspend/restore rows become **residency**, not transitions | ∅ |
| `IR-12` | :70 `ItemDef` in `RealityManifest.item_defs` | **K + label** — classify as `D-74` kind ① **ROSTER**. The structure is ours, the members are the author's (`D-75`) | ∅ |
| `IR-13` | :741-757 §8.6 — no weapon swap in combat | **K** — correctly deferred to the action economy (`ITM-D22`), and `D-14` keeps it out of this round | ∅ |

### 9.2 `PL_007b_inventory.md` · `PL_007c_integration.md`

| id | site | action | cost |
|---|---|---|---|
| `IR-14` | `PL_007b`:51-70 §2 — the two representations table + *"the awkward middle"* | **U** → `ITD-2`. `ITM-Q3`/`ITM-D1` close as **answered**, not deferred | S1 |
| `IR-15` | `PL_007b`:72-75 `ITM-A8` — *"one inventory, two stores, no third"* | **U** — one store, two shapes. The union projection was needed because the two stores had different identity models | S1 |
| `IR-16` | `PL_007b`:137-140 §4.1 `slots_used` — *"a resource kind costs one slot regardless of amount"* | **U** — under `ITD-2` a quantum stack is one row, so the rule survives in substance and must be restated over the new shape | S1 |
| `IR-17` | `PL_007b`:194-200 §4.3 — `CarryCapacity` as a reserved `StatSlot`, pointed at `inventory_cap` by `DF7-D3` | **U** — `C-2a` makes a ceiling a **declared derived quantity**, not a slot. The *intent* (capacity is a resolved stat, not a manifest constant) is correct and gets a better home | S1 |
| `IR-18` | `PL_007c`:71 `ITM-V10` · :140 `ITM-C2` — `item_defs` ∩ `resource_kinds` = ∅ | **D** — polices a boundary `ITD-2` removes | S1 |
| `IR-19` | `PL_007c`:288 — *"equipment_version bumps → DF07 StatEpoch invalidates the cached block"* | **D** — `IR-9` | ∅ |
| `IR-20` | `PL_007c`:556 readiness checklist — *"DF07 seam implemented, not merely described… the `blocked_by_primary` double-count and the `equipment_version` monotonicity limit are both called out rather than left latent"* | **U** — ✅ on a design being deleted. **Keep the sentence's history**: calling a latent defect out is what made it cheap to find now | ∅ |
| `IR-21` | `PL_007c`:503 `ITM-D7` — *"a transfer ledger is an event-log query, not a field"* | **K** — correct, and `D-23` is now the reason. Promote from deferral to **decided** | ∅ |

### 9.3 `EF_001_entity_foundation.md` · `40_progression_planner/06_item_contract.md`

| id | site | action | cost |
|---|---|---|---|
| `IR-22` | `EF_001`:169-174 `EntityLocation` | **U** — add the **owner** field beside it; document that `HeldBy` answered two questions (`ITD-1`) | S1 |
| `IR-23` | `EF_001`:160-167 `EntityRef` | **U** — promote to the **owner vocabulary** for all entities; `Cell → Place` per `WSA-R19`; `Faction` leaves *V3* and becomes V1 (`ITD-3`). ⚠ **Name collision, measured:** `crates/dp-kernel/src/entity_status.rs:126` already defines a *different* `EntityRef { entity_id, aggregate_type, reality_id }` — a platform status-lookup ref. One name, two tiers, unrelated meanings (`IO-1`) | S1 |
| `IR-24` | `EF_001`:120-144 `cell_owner` | **U** — generalise. It is the owner axis, discovered for one entity type and marked *"reached past the closed enum"* by `WSA-F4`. Once `ITD-1` lands it is **one instance of a general field**, not a special case | S1 |
| `IR-25` | `EF_001`:180 — *"an entity is in EXACTLY one place at a time"* | **K + label** — this is `ITD-5`, the anti-duplication mechanism. Today it reads as a housekeeping rule and is therefore weakenable by anyone optimising a read path | ∅ |
| `IR-26` | `EF_001`:73 `LifecycleState` | **already swept** — carries `D-12` and the declared-ordinal wording. Recorded so the next sweep does not redo it | ∅ |
| `IR-27` | `EF_001`:146-158 `inventory_cap: CapacityProfile` | **U** — `max_slots`/`max_weight` become declared derived quantities per `IR-17`; the field is a manifest constant today | S1 |
| `IR-28` | `06_item_contract.md`:64 — `class: ItemClass` — *"**engine-fixed, 8 variants.** A reality cannot add a 9th"* | **U** → `IR-4` | S1 |
| `IR-29` | `06_item_contract.md`:68 — `equip.modifiers` — *"`StatSlot` is **DF07-owned, 10 V1 slots**"* | **U** → `IR-2` | S1 |
| `IR-30` | `06_item_contract.md`:22-27 §0 — *"the substrate exists and is specified… 2031 lines of already-locked design"* | **U** — the premise of the whole document. Its *method* (read the schema field by field, ask who produces each) is good and survives; its **subject moved** | ∅ |

**Nothing in this sweep is `⛓`.** Zero realities are pinned (`D-11`), so every entry costs a re-authoring
pass at most — and `D-84`'s rule applies with force: **a reversal is cheap now and expensive once content
exists.**

## 9.5 `ITD-12` — no ownership defaulting, and it removes a hole rather than guarding one

> **`ITD-12`.** The owner edge is **explicit on every row**. Inserting into a container never changes it,
> and ownership is **never resolved transitively**. Putting something into the sect vault does not make it
> the sect's; **transferring** it does.

Derived while adjudicating the register (dataflow §20.3), where `IO-2` (who guards an ownership cycle) and
`IO-11` (does a container's owner propagate) turned out to be **one** question: a cycle only hurts if
something walks the graph, and the only reason to walk it is defaulting.

- **The laundering hole closes by construction.** `IO-11`'s own warning — *"silence here is how goods get
  laundered by being put in a box"* — cannot arise, because insertion is not a transfer.
- **`IO-2` drops from 🔴 to minor.** Nothing walks the graph, so a cycle is nonsense fiction rather than an
  unbounded loop; `V2-4` stays as a cheap bounded check and stops being load-bearing.
- **`owner = None` inside a group's vault stays findable** — unclaimed goods in a shared store are a real
  state with a real query, which defaulting would silently consume.
- **It is the complaint EVE's players actually make**: *"who owns the contents — the pilot or the
  corporation — has been noted as a design complexity issue."* The complexity **is** the defaulting.
  Bethesda defaults, which is why *"the owner of the object **overrides** ownership by the container"* has
  to exist as a second rule on top of the first.

**Cost, stated:** an author who wants *"everything in the sect vault belongs to the sect"* writes a rule
that transfers on insert. That is the **social feature's** rule, expressed as an operation — not a silent
property of the substrate.

## 10. The questions for the PO — **four became one** (dataflow §20)

> **Adjudicated 2026-08-02.** Two of the four dissolve into rules this project already sealed, one is
> reframed by a measurement, and one absorbs the fourth. **The table below is kept in full** — a question
> that closes is more useful with its closure attached than deleted.

| # | status |
|---|---|
| **`IPO-1`** · ship or reserve the ownership axis | ✅ **CLOSED by `D-84`** — *"a reversal is cheap now and expensive once content exists… take the reversal's decision now even if its code lands later."* The split is a **reversal**, not new work, and `D-11` supplies the window. ⚠ **One obligation ships with it:** a field stored and never read is a defect (the *write-only behaviour* bug class), so the minimum consumer must land with the field — `V2-3`, operations `give`/`claim`/`release`, and the *what am I carrying that is not mine* query |
| **`IPO-4`** · take the `Group` owner variant now | ✅ **CLOSED with `IPO-1`** — one line, already reserved as `EF_001`'s `EntityRef::Faction`, and `ITD-3` established a group is only ever the **subject** of an owner edge, so no `ActorKind` change |
| **`IPO-3`** · does an item get a `size_of`-gated hot block | 🔁 **REFRAMED, and the measurement damaged the number I was going to borrow.** `TierCapacityCaps` = **0 occurrences in `crates/`**, its real shape is `max_major_tracked: 20` / `max_minor_tracked: 100` / **`Untracked unlimited`**, and it caps **AI attention**, not state. ⇒ **`D-94`'s *"hard stateful population cap is 120"* is a cap over a different ladder** — exactly the conflation `D-21` retired the word *tier* to prevent. Recorded, **not re-opened**. What survives is better than the question: adopt the **mechanism** (author-declared cap, engine defaults, overflow **defers rather than drops** — `DL-D6`), and `D-94`'s own revisit trigger (*a stateful cap above ~10 000*) becomes the **decision rule** for the layout instead of a coin toss |
| **`IPO-2`** · is `repackage` allowed / lossy | ⬆️ **ABSORBED INTO THE ONE REMAINING QUESTION** — see below |

### 10.0 ✅ RESOLVED 2026-08-02 — **`ITD-13`: DYNAMIC, ONE-WAY.** The PO's criterion split a question I had framed as binary

> **PO criterion, and it is the standing one for this project:** *we are not building one game, we are
> building a **simulator of worlds** — so the answer usually depends on **the limit it places on
> extension**.*

**Applied, it reverses §20.2's recommendation and then dissolves the trade-off that produced it.**

**First, the reversal.** I recommended STATIC because it carries less surface. **Less surface is not more
extensible.** Under STATIC an author must decide at **declaration time** whether a thing may ever become
individual: wanting *"arrows stack, but a legendary arrow can be named"* forces `CustomName` capacity onto
the def, so **no arrow ever stacks again**. The author must choose **cheap bulk XOR the possibility of
individuality**, per def, before knowing which things the fiction will make special.

**That is `ITM-A2`'s failure one level up** — the author predicting which things will need identity — and
this document exists to remove it. For one game it is a decision made once. For **N realities and multiple
authors** it is a ceiling, and it is exactly the class of ceiling a world simulator hits and a single game
does not. The wish corpus speaks in the language of **becoming**: a natal treasure *becomes* bonded, a
blade *becomes* chipped, a keycard *is issued* with a date.

**Second, the dissolution — and both of my options missed it.** I presented the transition as one thing.
**It is two directions, and they separate cleanly:**

| direction | what it buys | what it costs |
|---|---|---|
| **`assemble`** quantum → instance (*becoming special*) | **all of the extensibility value** | **+1 row**, bounded by construction |
| **`repackage`** instance → quantum (*becoming anonymous*) | **only market packaging** | deliberate loss · a laundering vector (`IPO-2`) · collapses n rows into 1, so the delta is **unbounded** (`IO-4`, `IA-1`) |

**Every one of the four open rows I charged to "the dynamic rule" belongs to `repackage`, not to
`assemble`.** And `repackage` exists to serve a **market** — which `D-22` sealed as trade + economy's.

> **`ITD-13` — DYNAMIC, ONE-WAY. `assemble` is in; `repackage` is OUT**, deferred with a named trigger:
> *the first time trade + economy needs bulk-identical storage.* The operation set is **eleven**, not ten
> and not twelve.

**What this closes:** `IPO-2` (no lossy operation exists to rule on) · `IO-4` and `IA-1` (a single
`assemble` is +1 row; bulk assemble is capped per call, which the collapse direction could not be) ·
`IO-5` (a quantum has no per-instance state to merge away — nothing is written until it assembles).

**Verified against the blind wish corpus (§21):** *"a blade that chips and can be **reforged once**"* does
**not** need `repackage` — reforging is `mutate state` on the `Durability` slot, and the blade keeps its id
and its signature. **None of the 18 item wishes needs the reverse direction.**

**The residual cost, stated:** a used dagger can never rejoin the stack of new ones. That is honest — it
*is* different — and it is the same *unrepresentable-rather-than-invalid* discipline as `ITM-A5` and
`ITD-5`.

### 10.0b The PO's second correction — **my worked example was genre-wrong**, and the fix produces `ITD-14`

> **PO, immediately after:** *look at how Diablo and games of that genre store it — **you cannot store 50
> swords as one row**.*

**Correct, and it removes the justification I had been leaning on.** In the ARPG family a sword is **born
rolled**: it never joins a stack because it was never identical to another. So *"a merchant's 50 identical
daggers"* — the example I carried from `PL_007b` §2 through `ITD-2` and into §20.2's cost table — **is not
a case that arises in that genre at all**, and the compression benefit I priced at 2.8 KB was priced
against a population that does not exist there.

**Measured, and the genre says something more useful than the example did:**

| evidence | what it establishes |
|---|---|
| **Diablo II's save format** — an item is a variable-length bitfield; a **"simple item"** is the base record, and a **non-simple** one carries rarity, prefix, suffix, runeword, personalisation, set membership **plus a mod list of 9-bit key/value pairs terminated by `0x1ff`** ([d2s format](https://squeek502.github.io/d2itemreader/formats/d2s.html)) | **The simple/complex split is PER ROW, not per def.** A plain white sword costs the base record; a rare one pays for its mods. That is our `instance.state: StateRef = None` for a plain instance — **so a born-plain-but-unstackable thing is already cheap** |
| **Path of Exile** — the Currency stash tab has **designated slots per currency kind, 5 000 each**, while unstackable items get *"at least 50"* ordinary slots ([stash tabs](https://maxroll.gg/poe/getting-started/stash-tabs-explained)) | the two storage shapes are **architecturally separate** in a shipping ARPG — `(kind, count)` with no per-unit row, beside per-row items. `ITD-2`'s core is unchallenged |
| **The practitioner's rule** — *"charged objects like wands or potions may have a 'uses' count, and these **can't be stacked as a single object with a count, as the individual charges would be lost**"*; *"equipment doesn't stack because each piece is typically unique… with its own properties"* ([GameDev.net](https://gamedev.net/forums/topic/583905-item-stacking-in-rpgs/)) | **`ITD-2`'s dynamic rule, stated independently by someone shipping it** — merging is illegal exactly when it would destroy per-item state |

**Does this overturn `ITD-13`? No — and the reason is the PO's own criterion.** Diablo is served by
**either** rule: its equipment declares state capacity, its births always roll, so under STATIC it never
stacks and under DYNAMIC it is born an instance. **The rules differ on exactly one case, and it is the one
an ARPG does not have and a world simulator does:**

> **A def whose births are usually PLAIN and occasionally SPECIAL.** A sect mass-producing 500 identical
> talismans, an armoury of standard-issue sabres, a batch of 100 identical pills — then *one* gets
> inscribed, bonded or named. **STATIC forces the author to give up bulk storage for the entire class to
> keep that possibility open.** DYNAMIC costs one row when it happens.

⇒ `ITD-13` **stands, with its justification replaced**: not *"compressing 50 identical swords"* (which the
genre says is not a real population) but *"a class that is ordinary in bulk and occasionally becomes
individual"* — which is a **world-simulation** shape, not an ARPG one.

> **`ITD-14` — BIRTH declares the shape, and `instance_state` declares only the CAPACITY.** The two are
> different and §16's operation 1 conflated them by saying only *"one row"*. A def's `instance_state` says
> what a thing **may** carry; the **birth** says whether *this* thing arrives as a **quantum** or as an
> **instance**. Diablo's sword: capacity yes, **born instance, always** (the generator rolls at birth).
> The sect's talisman: capacity yes, **born quantum**, assembled later if ever. Arrows: **no capacity**,
> always quantum. **Three genres, three behaviours, one mechanism** — and without this the design could
> not express *born rolled*, which is how most of the ARPG family actually works.

<details><summary>The question as it was put to the PO, kept because the framing error is the lesson</summary>

### The original binary: static or dynamic stacking

§14.4 of the dataflow named two rules for `ITD-2` and took EVE's **dynamic** rule. Adjudicating the
register showed that choice was carrying **four open rows by itself** (`IPO-2` · `IO-4` · `IO-5` · `IA-1`),
and all four vanish under Minecraft's **static** rule.

| | **STATIC** — `instance_state` non-empty ⇒ never stacks | **DYNAMIC** — stacks while every slot is at default |
|---|---|---|
| operations | **10** | 12 (`assemble` + `repackage`) |
| open rows it carries | **0** | `IPO-2` · `IO-4` · `IO-5` · `IA-1` |
| costs | 50 durability-bearing daggers are **50 rows** (2.8 KB; 10 000 = 560 KB, materialised only when touched under `D-23`) | those 50 are one row until sold |

**The benefit the dynamic rule buys belongs to a feature we handed away.** EVE requires packaging *"to be
sold on the market… it needs to be identical to every other item of the type so the buyer knows what they
are getting"* — the transition exists **to serve a market**, and `D-22` sealed markets as trade + economy's.

> **Recommendation: take the STATIC rule.** It deletes two operations, closes three register rows and one
> attack-surface row, and makes `V1-4` the whole rule instead of half of one. **If trade + economy later
> needs bulk-identical storage it can ask for `repackage` then** — with a real requirement and a cost model
> it owns.
>
> It stays the PO's because it trades authoring convenience against architectural surface, and that is a
> value call. ⚠ **It reverses my own §14.4**, on the strength of nothing but counting the rows that choice
> was carrying — **four open rows traceable to one optional decision is what a wrong default looks like
> from the outside.**

#### The four questions as originally escalated — **all superseded by §10 above**

⚠ Kept as history only. `IPO-3`'s premise in particular is now known to be a **mis-citation**:
`TierCapacityCaps` caps **AI attention**, not state, so *"items are not capped by it"* was true of a
different ladder than the one the sentence implies.

| # | Question (superseded) |
|---|---|
| **`IPO-1`** | **Does the ownership axis ship now, or is it reserved?** Shipping it costs one field, one enum promotion and a validator. Reserving it makes theft, lending, consignment, inheritance and every group holding inexpressible until a schema change. **Recommendation: ship it** — it is a `C-1`/`C-2`-class reversal, and those are *"cheap now, expensive after any reality is pinned."* |
| **`IPO-2`** | **Is the quantum→instance transition reversible?** EVE's repackage **destroys** per-instance state, which is honest and lossy. Ours would destroy provenance, charges and bindings. Reversible-and-lossy, irreversible, or author-declared per def? This is a fiction-visible destructive operation and the answer is a game-design call, not an engineering one. |
| **`IPO-3`** | **🔴 Does an item get a fixed-width `size_of`-gated hot block like `ActorQuantities`?** `D-94` closed the columnar-vs-`size_of` question **because the stateful actor cap is 120** — *"at 120 the columnar benefit is unmeasurable."* **Items are not capped by `TierCapacityCaps`, and there is no item ceiling anywhere in the corpus.** So the measurement that dissolved the question for actors **does not transfer**, and inheriting the actor's answer would be `D-101`'s failure mode arriving with evidence. This needs a number nobody has — `O-54`'s absence, one tier down. |
| **`IPO-4`** | **Does item core take the `Group` owner variant now**, with permissions handed to the social feature (`ITD-9`)? Recommendation: **yes** — the variant is one line and already half-present as `EntityRef::Faction`; the permission relation is genuinely someone else's and fails `D-24`'s playability test. |

</details>

### 10.1 Where this design is most likely to be wrong

Written for the red team, by the author, before they arrive.

⚠ **`IA-1` and `IA-5` are struck by `ITD-13`** (no `repackage` ⇒ no unbounded row-count delta, and a
quantum has no per-instance state to merge away). The rest stand.

| # | The attack surface |
|---|---|
| **`IA-1`** | **`ITD-2`'s transition has no cost model.** A merchant repackaging 50 daggers collapses 50 rows into one; a player assembling them explodes one row into 50. **A single authored operation whose row-count delta is unbounded is a denial-of-service seam**, and nothing here bounds it. `D-56` said the same thing about `modifier_rows` and I have reproduced the defect one feature later. |
| **`IA-2`** | **`ITD-1` doubles the state space and I have not enumerated it.** Four owners × four locations = sixteen combinations, and I have justified six of them with fiction (§1). What is `owner=Item, location=HeldBy`? What is `owner=None, location=InContainer`? Some of these are probably illegal and nothing here says which. |
| **`IA-3`** | **`ITD-5` is asserted about a design, not measured against an implementation.** *"There is no save step to mis-time"* is true of `D-36`'s model. Nothing in `crates/` implements item movement at all, so the claim cannot currently be falsified — which per `non-vacuity` is exactly the shape of a claim that will be believed and never checked. |
| **`IA-4`** | **`ITD-7`'s empty control axis may be an artefact of scope.** A cursed sword that acts, a spirit bound into a blade, `TVL_003`'s mounts, an autonomous construct — every one of those is an item a reality might want to have a controller. I concluded *"nothing drives an item"* from the absence of a current requirement, which is the weakest form of evidence this project recognises. |
| **`IA-5`** | **The quantum's key is `(owner, location, def_id)` and I have not checked that it is unique enough.** Two quanta with the same key and different provenance must merge — losing which one came from where. That may be correct (it is what *fungible* means) or it may quietly destroy a fact some feature needs. |
| **`IA-6`** | **`ITD-9` hands permissions away on `D-24`'s test, and the test may not apply.** `D-24` moved *opinion* out — a feature with no invariant to violate. Permissions guard an invariant (*this member may not empty the treasury*), and a substrate that cannot express a constraint its owner feature depends on is a different case from one that merely lacks flavour. |

---

## 11. What must not be lost when this is applied

The item corpus was written carefully and its **method** was right even where its conclusions are now
wrong. Recorded so the sweep does not throw it away with the rot:

- **`PL_007c`:556 called its own two latent defects out** rather than leaving them to be discovered.
  That is why `IR-10` costs a paragraph instead of a debugging session.
- **`PL_007b` §4.1b found a reachable soft-lock** — an actor at capacity who can neither equip nor
  unequip — by taking its own accounting rule literally. The **over-encumbered** rule that resolves it
  (*rearranging what you already carry is never blocked*) is a genuine game-design finding that survives
  every change in this document.
- **`PL_007` §6.4's `InstrumentTag`** closed a three-way break invisible from any one document. The
  mechanism moves (it must not name `ResourceKind`), but *the finding* — that two features declared an
  operand neither could evaluate — is the kind only a third document can make.
- **`06_item_contract.md`'s method** — read the schema field by field and ask *who produces this* of each
  one — is the right method. It was applied to a schema that is about to change.
