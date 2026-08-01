# 40.4 — The enum pool: the contract layer is a POOL of closed sets, and one loop fills it

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `EPL-`
> **Sharpens** [`40.3`](03_generator_boundary.md) — `PPB-A1`/`A4`/`A5`/`A6` survive unchanged;
> `PPB-A2`'s three artifacts and `PPB-A3`'s vocabulary collapse into one mechanism.
> **Generalises** [`35_quantity_architecture.md`](../35_quantity_architecture.md) `QTY-A6`, which is
> this pattern already built — for quantities only.
> **Pipeline-wide, not progression-only.** Written here because this is where it surfaced; it belongs
> in [`38`](../38_content_pipeline_architecture.md) once reviewed.

---

## 0 — The proposal

> *"There is a way to solve this: the contract generator should be **facts**, and we build planners to
> produce the facts first. This is **creating enums for the game** — this reality has 5 grades of
> treasure, this world has 5 attribute types, the cultivation realm has 10 layers, and so on. Other
> generators **define the enum types they actually need — this can be done in code — and register them
> into the contract generator's pool.** Then the contract generator **loops over the pool**, running
> the planner + human-in-the-loop cycle to enrich those enums.
>
> This is how people make games: **game concept → realise it as a list → implement logic for that
> list** (game engine, game logic). What LoreWeave does is **define the deterministic functions** for
> the engine and the game logic, and **push the definition of that list outside, through the
> manifest**. And what we are doing is: **a human uses an LLM to produce that manifest, over several
> steps.**"* — PO, 2026-07-31

Three things fall out of this, in increasing order of importance: it **unifies** 40.3's three contract
artifacts into one, it **dissolves** 40.3's hardest open question, and it **states the thesis of the
entire track** in one sentence that can be turned into a lint.

---

## 1 — `EPL-A1` — the thesis, and it is enforceable

> **`EPL-A1`.** The **engine is a set of deterministic functions.** The **manifest is the set of lists
> those functions range over.** Generation is the process by which a human and an LLM author the
> lists. **No game-specific closed set may be hardcoded in engine code.**

The last sentence is the part that stops this being a slogan. It has the same shape as the repo's
`No hardcoded model names` rule — a class of literal that must live in data, checked mechanically,
with a real subject to bite.

**Why this is the correct decomposition and not merely a tidy one.** It is how data-driven game
development actually works, and doc 38 already argued it from the other end (`CPL-A10`'s Diablo 2
analysis): D2 ships fixed acts, a fixed item-base table, a fixed affix table — *authored data* — and
generates the **roll**. *"The tables are the expensive human work, paid once."* `EPL-A1` names what
the tables **are**: the closed sets the engine's functions range over. LoreWeave changes one thing —
the tables are authored by a human with an LLM from a book, instead of by a designer from imagination.

**And it explains the whole POC-1 failure in one line.** POC-1 tried to produce a *system*. A system
is functions **plus** lists, and the functions are already in Rust. All that was ever needed from the
book was **the lists** — and 4 of 11 questions got answered because 11 questions were the wrong shape
for filling a list.

### 1.1 The contract generator produces ONE kind of thing

> **`EPL-A3` — the contract generator produces the closed sets, and the structures built over them.
> Nothing else.** Its boundary IS `PGN-A5`'s permitted-authority boundary: a model may emit
> **CARDINALITY, ORDER and NAMES**, never **MAGNITUDE**. So the pool is not an arbitrary design choice
> — it is **derived** from where the model is already allowed to speak.

| in the pool | example | who authors |
|---|---|---|
| **① closed set** — the dominant kind | realm tiers · attribute kinds · treasure grades · trigger classes · place kinds · item roles | the loop (human + LLM) |
| **② structure over closed sets** | a breakthrough condition · a formula *shape* · a contribution point | the loop |

**Everything else belongs to a SPECIFIC generator, and this document has no opinion about it.** Not
"routed elsewhere by the contract layer" — simply **not the contract generator's business**:

| not in the pool | example | who |
|---|---|---|
| **magnitudes** | how much a meditation tick yields · an item's damage · a region's size | **the owning generator**, each with its own numeric source. Progression's happens to be `PGN-A15`'s policy artifact; item's is item's, and there is no shared one |
| **instances** | *this* sword · *this* mountain · *this* NPC | **the owning generator**, at L2, from the frozen pool |

**The pool holds the LISTS, never the INSTANCES.** *"There are 5 grades of treasure"* is a pool entry.
*"The Verdant Frost Blade is grade 4, 87 damage"* is the item generator's output and none of the
contract generator's concern.

### 1.2 Two different "two layers" — do not confuse them

This design now contains two orthogonal two-layer splits, and conflating them is easy:

| | split | separated by | scope |
|---|---|---|---|
| **pipeline layers** (`PPB-A6`) | **CONTRACT → GENERATE** | a **freeze** | across all modules |
| **generator layers** (`CPL-A10`) | **LLM vocabulary → procedural spine** | nothing — they are two halves of one module | **inside each** specific generator |

> **`EPL-A6`.** Every specific generator is **internally** two-layered — an LLM half that supplies
> creative vocabulary and a procedural half that is the spine — per doc 38 `CPL-A10`: *"the procedural
> generator is the spine; the LLM is a plug-in that fills its vocabulary, never a replacement for it.
> Every element generator must be able to run with a hand-authored vocabulary and no model at all."*
> **The contract generator does not reach inside that split, and does not need to know it exists.**

```
CONTRACT GENERATOR                    ★FREEZE       SPECIFIC GENERATORS
one loop · human + LLM                              each internally 2-layer (CPL-A10)
produces the LISTS                     │            ┌── item ──────────────────┐
  ① closed sets                        │            │  LLM: names, flavour     │
  ② structures over them               ├──────────▶ │  proc: rolls, stats, qty │
                                       │            └──────────────────────────┘
                                       │            ┌── place ─────────────────┐
                                       ├──────────▶ │  LLM: naming, character  │
                                       │            │  proc: layout, geometry  │
                                       │            └──────────────────────────┘
                                       │            ┌── progression ───────────┐
                                       └──────────▶ │  LLM: (none needed)      │
                                                    │  proc: compile + policy  │
                                                    └──────────────────────────┘
```

**How large each half is, per generator, is NOT known yet and must not be guessed.** An earlier draft
of this section asserted that progression's generator *"barely has an LLM half at all"*. That was an
assumption, not a finding — it is only discoverable by specifying the module in detail. `CPL-A10`
fixes the *shape* (spine procedural, vocabulary pluggable, runnable with no model); it says nothing
about the ratio, and the ratio is per-module evidence.

---

## 2 — `EPL-A2` — shape is REGISTERED in code; members are AUTHORED per reality

> **`EPL-A2`.** Every element module **registers its slot shapes in code** — id, owner, arity bounds,
> ordering, required per-member fields, tenancy tier. The **members** are authored per reality by the
> pool loop and pinned by the manifest digest. A module never writes another module's members, and
> the pool never invents a slot nobody registered.

**This is `QTY-A6`, generalised.** Doc 35 already shipped exactly this shape — for quantities:

> **`QTY-A6`** — *"the ARRAY WIDTH is a compile-time constant. The IDENTITIES inside it are declared
> per reality and pinned by the digest."* A reality uses a prefix `0..n` of a fixed `N`; `n` is in the
> hashed bytes, `N` is in the binary.

`EPL-A2` says: that is not a quantity rule, it is **the** rule, and quantities were merely its first
instance. `QTY-A5`'s ordinal discipline (assigned never authored · monotonic · never reused · the
assignment table inside the hashed ruleset) carries over unchanged and for the same reasons.

```rust
// registered by the module that OWNS the concept — compile-time, checkable, one place
declare_pool_slot! {
    id:      "treasure_grade",
    owner:   ELEMENT_ITEM,
    arity:   2..=16,            // N — the compile-time width (QTY-A6)
    ordered: true,              // grades compare; attribute kinds would not
    tier:    Reality,           // tenancy: System | Reality | Book
    member:  { name: I18nKey, rank: Ordinal },   // fields every member must carry
}
```

Two properties this buys that prose could not:

- **A module cannot over-specify another module's content**, because it has no syntax for it. 40.3's
  `PPB-A3` needed a closed `REQUIREMENT_VOCABULARY` to stop the progression planner writing item
  design; under `EPL-A2` progression simply has no slot to write it into. **The vocabulary dissolves
  into the registry.**
- **The registry is the L0 layer `PPB-A6` needed**, and it is code rather than a document — so it is
  compiled, versioned with the engine, and cannot drift from what the engine actually reads.

---

## 3 — `EPL-A4` — ONE register over the whole pool, not one per module

> **`EPL-A4`.** The abductive open-decision register (`PPL-A8`) ranges over the **entire pool**, across
> every module's slots at once. There is one loop, one worklist, and one human.

This is the PO's *"the contract generator loops over the pool"*, and it is what makes the whole design
affordable. 40.3 left an unstated cost: if every element module runs its own planner, there are seven
loops, seven UIs and seven human workflows. There is one.

**And cross-module gaps become ordinary register rows.** Walk the case 40.3 struggled with:

```
progression declares   breakthrough(inner_power → foundation_establishment)
                       requires item_role::?            ← a reference into ITEM's slot
item's slot            item_role  has no such member
                       ─────────────────────────────────────────────────────
register (abduced)     OPEN: item_role needs a member; referenced by decision D-142;
                       blocks 1 gate; provenance available: ③ CITED (chunk 7, span 12..38)
```

No `RoleRequirement` type, no demand register, no cross-module message. **A dangling reference between
two pool entries, found by the same abduction that finds everything else.** 40.3's ① and ② were two
special cases of it, and its ③ (`StateExposure`) is not an artifact at all — it is a *projection* of a
declaration, since a Stage-typed kind has a tier by construction.

> **`EPL-A5` — owning a slot's SHAPE is not authoring its MEMBERS.** Item owns `item_role`'s shape.
> Progression's breakthrough *references* a member. Neither writes it: **the loop writes it, with the
> human**, and the register records which decision demanded it. Ownership governs the schema;
> authorship goes through one gate.

That is what keeps `PPB-A1` (*a declarer never sources*) true while still letting progression's need
for a catalyst reach the item taxonomy.

---

## 3A — `EPL-A7` — a slot is SHARED or PRIVATE, and the test is "does another module reference it?"

The criterion, from the PO:

> *"I think it is grade and type, because those affect other modules."*

That is the right test, and it is sharper than what `EPL-A2` said. Registering a slot and **publishing**
it are different acts:

> **`EPL-A7`.** Every registered slot declares a **visibility**. A slot is **SHARED** if any other
> module's declarations reference its members, and **PRIVATE** otherwise. Both are filled by the same
> loop; only a SHARED slot can produce a **cross-module** dangling reference, and a reference from
> module X into a PRIVATE slot of module Y is a violation, not a coupling.

| | shared | private |
|---|---|---|
| filled by the one loop (`EPL-A4`) | yes | yes |
| referenceable by another module | **yes** | no |
| can raise a cross-module register row | yes | no |
| changing its member set is | a **contract change** | the owner's own business |

**Why this is worth a rule and not a naming convention.** It is the only thing that keeps the pool
from becoming a global namespace where every module's internal taxonomy is everyone's business.
`item_affix` is a real closed set a human authors — and no other module has any reason to name an
affix. Publishing it would let a future progression rule bind to *"the Sharp affix"*, which is the
`PPB-A1` violation this whole track exists to prevent, arriving through the back door.

**Registration carries it:**

```rust
declare_pool_slot!{ id:"item_grade",  owner:ELEMENT_ITEM, visibility:SHARED,  … }
declare_pool_slot!{ id:"item_affix",  owner:ELEMENT_ITEM, visibility:PRIVATE, … }
```

---

## 3B — `EPL-A8` — a module's decision routinely opens a decision in ANOTHER module. That is the normal mode.

The PO's second observation, and it is the strongest argument for `EPL-A4` yet:

> *"Something interesting here: the progression generator crosses the boundary — when we run it, it
> adds a type into the item type enum."*

Exactly so. Resolving *"breakthrough requires a catalyst"* does not fill a progression slot. It leaves
progression's declaration referencing an item-side member **that does not exist yet**, and the
register abduces it (`PPL-A8`) as an open row on **item's** slot.

> **`EPL-A8`.** Cross-module member creation is **not an exception path**. The pool is one
> interconnected fact set in which a decision in module X routinely opens a decision in module Y, and
> the loop is the only writer for both (`EPL-A5`). Any design that fills the pool **module by module**
> is wrong by construction.

Four consequences, and none of them is optional:

| | |
|---|---|
| **no per-module ordering** | you cannot "finish item, then do progression" — running progression *grows* item's taxonomy. The loop is ordered by **blocking power** (`PPL-A6.1`), across the whole pool |
| **slots reopen** | `item_archetype` can be complete, then open again when a later progression decision demands a tag. "Done" is a property of the **pool**, never of a slot |
| **one freeze, at the end** | `PPB-A6`'s freeze is when the **whole** pool converges. A per-module freeze would pin item's taxonomy before progression had finished demanding from it |
| **`PPO-A1` was measuring this** | *"~50% of a cultivation system is a demand on another module"* — `EPL-A8` is that number showing up as a mechanism rather than a survey result |

### 3B.1 Why this does not explode — and where it still might

The obvious fear: progression demands an item type, whose recipe demands a material, which demands a
place that grows it, and the loop never terminates.

**Two things bound it, one real and one to watch.**

**Real: the demand is usually a TAG, not a member of the expensive slot.** Per
[`40.6` `ICT-A3`](06_item_contract.md), the progression→item seam is
`InstrumentMatch::ItemTag(InstrumentTag)`. Progression demands **one tag**; item's own generator then
decides which archetypes wear it. One cheap cross-module decision, not N expensive ones — and the
under-specification that makes it cheap is the same under-specification `PPB-A1` requires. **The
mechanism that keeps modules decoupled is also the mechanism that keeps the loop finite.**

**To watch: nothing yet proves termination.** The referencing structures are finite (a breakthrough
has finitely many condition leaves), and the human can always answer *not-stated* — which `PGN-A4`
already makes a **complete** answer rather than a gap. But that is an argument, not a bound. The
spike should **log demand-chain depth per round** and report it, rather than assume it stays at one.


---

## 4 — What the pipeline looks like now

`PPB-A6`'s two layers survive; L0 and L1 get their real shape.

```
L0 · REGISTRY        in CODE, compiled with the engine
                     every module declares its slot SHAPES  (EPL-A2)
                     ⇒ the pool's schema. No reality-specific content.
                              │
                              ▼
L1 · POOL FILL       ONE loop. ONE register. ONE human.        (EPL-A4)
                     abduce open members → resolve by provenance (PPL-A5)
                       ① DECLARED  ② CANON  ⑤ DERIVED  ③ CITED  ④ PROPOSED
                     until the register is empty for the declared profile
                              │
                              ▼  ★ FREEZE — content-addressed, ordinals assigned (QTY-A5)
L2 · GENERATE        every SPECIFIC generator in PARALLEL, reading only the frozen pool
                     each internally 2-layer — LLM vocabulary + procedural spine (EPL-A6)
                     item rolls items · place lays out places · progression compiles rows
                     magnitudes and instances are decided HERE, per generator, never in the pool
                     ✗ no module reads another module's L2 output
                              │
                              ▼
                     MANIFEST — pinned, digested, loaded by a reality
```

**Note what moved.** In 40.3, L1 was N parallel per-module contract authorings. It is now **one
sequential enrichment loop over a pool whose schema came from code**. That is a smaller, more honest
machine: the parallelism that mattered was always L2 (generation), not L1 (deciding).

**And the human's job becomes legible.** Not *"review 121 rows"* and not *"answer 11 questions"*, but:
*"here are the lists this reality needs; here is which ones are still empty; here is what the book says
about each."* That is a job a person can actually finish.

---

## 5 — Worked example, end to end

**L0 — registered in code, once, by three different modules:**

```
item        declare_pool_slot!{ id:"treasure_grade", arity:2..=16, ordered:true,  member:{name,rank} }
item        declare_pool_slot!{ id:"item_role",      arity:0..=32, ordered:false, member:{name} }
progression declare_pool_slot!{ id:"progression_kind", arity:1..=8, ordered:false,
                                member:{name, kind_type, curve, cap} }
progression declare_pool_slot!{ id:"realm_tier",     arity:2..=64, ordered:true,  member:{name, index} }
rules       declare_pool_slot!{ id:"trigger_class",  arity:1..=32, ordered:false, member:{name} }
place       declare_pool_slot!{ id:"place_property", arity:0..=32, ordered:false, member:{name} }
```

**L1 — one loop fills them.** A slice of the register, ranked by blocking power (`PPL-A6.1`):

| open | blocks | cheapest provenance |
|---|---|---|
| `progression_kind` — **how many, and which?** | 11 | **① DECLARED** — the human, ten seconds (`PPL-A4`) |
| `realm_tier` members | 6 | ③ CITED, then ⑤ DERIVED for the sub-level pattern |
| `item_role` needs a member (referenced by D-142) | 1 gate | ③ CITED — the book names the pill |
| `place_property` needs `high_ambient_energy` (referenced by D-143) | 1 gate | ③ CITED |
| `trigger_class` — which actions feed progression? | 4 | ② CANON from the wiki, else ④ PROPOSED |

**Freeze.** Ordinals assigned, digest computed.

**L2 — in parallel, nobody blocking anybody:**

```
item        reads item_role + treasure_grade   → designs the pill, its recipe, its rarity → BIND
place       reads place_property               → lays out a pool that HAS the property     → BIND
combat      reads realm_tier (ordered)         → authors the realm-gap curve
progression reads its own members              → compiles ProgressionKindDecl rows
```

**Assembly** verifies every reference resolves. Then the manifest pins.

Note what progression never touched: the pill's name, recipe, rarity, drop; the pool's coordinates or
biome; the combat curve. And note what it never had to *wait* for: any of them.

---

## 6 — Trust properties

| id | property | mechanism | can it fail? |
|---|---|---|---|
| `EPL-T1` | no game-specific closed set is hardcoded in the engine | a lint over `crates/`: a closed enum whose variants are *reality-specific vocabulary* rather than *engine roles* is a finding. Sibling of `closed-set-gate.py`, which already walks every closed set in the tree | yes — a `enum RealmTier { QiCondensation, … }` in Rust reds it |
| `EPL-T2` | the pool never invents a slot | every pool entry joins to a registered slot id; an orphan entry is refused at freeze | yes |
| `EPL-T3` | members respect their registered shape | arity bounds, ordering, required member fields checked at freeze against L0 | yes — a 17th `treasure_grade` under `arity:2..=16` reds it |
| `EPL-T4` | a module cannot author another's members | authorship is only through the loop, and the loop records the deciding provenance + the referencing decision (`EPL-A5`) | yes — a member with no register row reds it |
| `EPL-T5` | no magnitude enters the pool | `EPL-A3`/`PGN-A5`: a member field typed as a magnitude is refused at registration | yes — `member:{ rate: u32 }` on a pool slot is refused; a rate belongs to whichever generator owns it |
| `EPL-T6` | L2 cannot read L2 | `PPB-A6`; generation is `f(frozen pool, seed)` and the pool digest is an input | yes |

`EPL-T1` is the one worth building first: it is the only check that would notice the whole thesis
being violated, and `closed-set-gate.py` already proves the tree-walk is cheap.

---

## 7 — What this changes

| target | change |
|---|---|
| `PPB-A2` (three artifacts) | **collapses.** ① and ② become dangling references between pool entries; ③ is a projection, not an artifact (`EPL-A4`) |
| `PPB-A3` (`REQUIREMENT_VOCABULARY`) | **dissolves** into the L0 registry — a module has no syntax for another's content (`EPL-A2`) |
| `PPB-A1` · `A4` · `A5` · `A6` | **survive unchanged.** Declare-vs-contribute, gates belong to refusers, closure splits, two layers + freeze |
| `PPB` §10.1 · §10.4 | **closed** — L0 is code; `has_property` is `place_property`, an ordinary slot |
| `PPL-A8` (abduction) | **scope widens** from the progression plan to the whole pool (`EPL-A4`). Same mechanism, one instance |
| `PPL-A10` (fact set) | confirmed and generalised: the SSOT is a flat fact set. `Decision` rows now carry a `(slot_id, member)` address |
| `PPO-A4` (profiles) | simplifies — a profile is largely **which slots must be non-empty** for this product, plus its CQ set |
| `PPO-A7` (capability vocabulary) | it is a **pool slot** (`capability`, per tier), not a special output. Registered by the agent tier, filled by the loop |
| `QTY-A5` · `A6` | **promoted** from quantity rules to the general pattern; quantities become the first registered slot family |
| doc 38 | `EPL-A1` is the thesis its `CPL-A10` argued from the other end. **`CPL-A10` is also `EPL-A6`** — it governs the *inside* of a specific generator, which the contract generator never reaches into (§1.2). `EPL-*` belongs in 38 once reviewed |
| doc 39 | S4's numeric policy is **the progression generator's own** magnitude source, outside the pool, unchanged. It is not a shared facility — every specific generator owns its numbers (`EPL-A3`) |

---

## 8 — Open

1. **Is `EPL-T1` decidable?** *"Reality-specific vocabulary vs engine role"* is a judgement in the
   general case. A tractable proxy: an enum is a finding if a **manifest-loaded slot with the same
   concept exists**, or if its variants carry genre nouns. Needs a real pass over `crates/` to see
   whether the false-positive rate is livable — the lesson `count-drift` learned the hard way.
2. **Ordered slots and insertion.** `realm_tier` is ordered and `QTY-A5` forbids ordinal reuse. What
   happens when the loop learns, late, that a tier sits **between** two existing ones? Probably: the
   member ordinal and the *display order* are different fields. Confirm before building.
3. **Where does the registry live?** It must be readable by the Python planner and the Rust engine
   without a mirror. Candidate: declared in Rust, **exported** to `contracts/` by a build step, the way
   the doc 39 schema fingerprint already is — one source, one generated artifact, a drift test.
4. **Does every element module fit?** Carried forward from `PPB` §10.6 and now sharper: world/geography
   is bulk geometry (④ instances), so its L1 contribution may be nearly empty. A module with no pool
   slots at all is fine; a module needing to read another's L2 is not. Walk all seven.
5. **How does a slot get retired?** `QTY-A5` says ordinals are never reused, but nothing yet says how a
   *slot* leaves L0 when a genre stops needing it. Doc 35 §6.3.1 records that removal was the third
   kind of change and the first build order committed it — same trap here.
