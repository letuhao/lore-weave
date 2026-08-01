# 40.3 — The generator boundary: what the progression planner owns, and what it only CONTRACTS for

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `PPB-`
> **Corrects** [`40.1`](01_planner_architecture.md) `PPL-A1`/`PPL-A2`/`PPL-A7` and
> [`40.2`](02_outcome_contract.md) `PPO-A1` — all three were written broad enough to reach into other
> element modules' scope.
> **Governed by** [`38_content_pipeline_architecture.md`](../38_content_pipeline_architecture.md)
> `CPL-A3` (one module per element) and [`35_quantity_architecture.md`](../35_quantity_architecture.md)
> `QTY-A13` (a source contributes, never declares).

---

> ### ▶ Sharpened by [`40.4 — the enum pool`](04_enum_pool.md), 2026-07-31 — not corrected
> `PPB-A1` (declare vs contribute), `PPB-A4` (a gate belongs to whoever refuses), `PPB-A5` (closure
> splits) and `PPB-A6` (two layers + freeze) all **stand**. What collapses is the *machinery*:
> `PPB-A2`'s three artifacts become dangling references between pool entries, and `PPB-A3`'s
> `REQUIREMENT_VOCABULARY` dissolves into a code-level slot registry — a module cannot over-specify
> another's content because it has no syntax for it. Open questions §10.1 and §10.4 are closed there.

---

## 0 — The finding

> *"The current definition is too broad — it now reaches into the scope of other generators like the
> item generator. So we need to make clear which part the progression system generator does, and which
> part is a **contract** to feed into the other generators."*

Correct, and doc 38 had already forbidden it in writing:

> **`CPL-A3`** — *"there is no universal generator. There is one MODULE per element, and one CONTRACT
> they all implement."* Quoting the PO's own earlier constraint: *"we only focus for each element, not
> make a perfect generator that can make anything — nothing like that exists in the real world."*

Doc 38's element roster already names the coupling and flags it: **Progression system · depends on
rules, place, item ⚠**. Docs 40 and 41 then drifted across exactly that line, in three places:

| where | what it said | why that is a scope violation |
|---|---|---|
| `PPL-A7` | the planner emits a `Demand{shape: "a consumable that permits a Stage advance"}` | *shape* is item design. The item module's job becomes obedience, not design. |
| `PPO-A1` §2 | *"the planner declares `alchemist_grade` and **demands the mechanism**"* | the mechanism is the crafting system. This makes the progression planner the author of crafting. |
| `PPL-A1` | Gates are one of the four parts the planner produces | most gates are authored by **whoever refuses** — combat, place, crafting. The planner does not write them. |

The ontology in `PPL-A1` is not wrong — a progression *system* really does have four parts. What was
wrong is the unstated slide from *"the system has gates"* to *"the planner writes gates"*. This
document fixes the ownership, not the ontology.

---

## 1 — `PPB-A1` — the planner DECLARES; every other generator CONTRIBUTES

Doc 35 already carries half of this rule:

> **`QTY-A13`** — a source **CONTRIBUTES**; it never **DECLARES**.

Its dual was never written down, and its absence is the whole bug:

> **`PPB-A1`.** A declarer never sources. **The progression planner declares quantities, their shape,
> and the transition rules of its own state machine. It authors no item, no place, no recipe, no
> encounter, and no external gate.** Everything it needs from another module crosses the boundary as
> a **typed contract**, never as a design.

Stated as a one-liner that settles arguments:

> **The planner owns the SOCKET and the SLOT. It never owns the PLUG or the FILLER.**

---

## 2 — `PPB-A2` — the boundary is exactly three typed artifacts

The planner's output is not *"declarations + a demand manifest"* (docs 40/41's pair). It is
**declarations + three contract artifacts**, and each crosses the boundary in a different direction.

```
                    ┌──────────────────────────────────────────┐
                    │        PROGRESSION PLANNER               │
                    │  DECLARE: kinds · curves · caps · tiers  │
                    │           breakthrough structure         │
                    │           couplings AMONG progression    │
                    └───┬───────────────┬──────────────┬───────┘
       ① REQUIRE (out)  │               │ ② EXPOSE (in)│ ③ READABLE (in)
       a role slot      │               │ a socket     │ a state contract
                        ▼               ▲              ▲
              ┌─────────────────┐  ┌────┴────────┐  ┌──┴──────────────┐
              │ item · place ·  │  │ crafting ·  │  │ combat · place  │
              │ status · actor  │  │ quest ·     │  │ access · recipe │
              │   generators    │  │ event mods  │  │   gate authors  │
              │  → BIND         │  │ → CONTRIBUTE│  │  → author gates │
              └─────────────────┘  └─────────────┘  └─────────────────┘
```

### ① `RoleRequirement` — outbound, and deliberately UNDER-specified

```
RoleRequirement {
  role_id:      "breakthrough_catalyst"       # the planner's own name for the slot
  element_kind: item | place | status | actor # WHICH module must fill it
  predicate:    [ <terms from a CLOSED vocabulary — §3> ]
  raised_by:    decision_id                   # traceability: which decision opened it
  evidence:     the provenance that raised it (PPL-A5)
  state:        open | bound(ref) | refused(reason, owner)
}
```

The planner says *"I need a thing that plays this role."* It does **not** say what the thing is. The
item module designs the item — its name, recipe, rarity, price, drop table, art direction — and
answers with a `BIND`.

### ② `ContributionPoint` — inbound, and this is the inversion that stops the god-planner

```
ContributionPoint {
  target_kind:   inner_power
  trigger_class: meditation_tick | craft_success | combat_victory | …   # closed set
  magnitude:     a BAND, not a value  (bounded by the numeric policy, PGN-A15)
  cap_semantics: how it interacts with the kind's CapRule (QTY-A8)
}
```

**The planner publishes a socket; other modules plug into it.** Crafting is not *told* to raise
`alchemist_grade` — crafting *decides* that a successful refine contributes, and plugs in. The
planner never reaches into crafting, which is precisely what `PPO-A1`'s *"demands the mechanism"*
had it doing.

This is `QTY-A13` operating as designed: crafting is a **source**, and a source contributes.

### ③ `StateExposure` — inbound, the read contract that makes external gates writable

```
StateExposure {
  path:        inner_power.tier
  semantics:   ordinal, totally ordered, 24 values, comparable across actors
  stability:   pinned in the manifest digest; ordinals never reused (QTY-A5)
}
```

Combat authors the realm-gap curve *by reading this*. Place authors *"you may not enter below
Foundation Establishment"* by reading this. **The planner makes its state legible and stops there.**
It does not know what a ravine is and must not be asked to.

---

## 3 — `PPB-A3` — a requirement that over-specifies is a scope violation, and the check is an enum

The hard part of ① is knowing when a predicate has said too much. *"a consumable"* is a contract.
*"a consumable crafted from three herbs, costing 500 spirit stones, dropped by tier-3 beasts"* is item
design wearing a contract's clothes — and the item module's remaining job is obedience.

> **`PPB-A3`.** A `RoleRequirement`'s predicate may only use terms from a **closed vocabulary of
> progression-relevant properties**. A term outside it is a scope violation, refused at authoring
> time — not a style note.

```
REQUIREMENT_VOCABULARY  (closed set; adding a term is an architecture decision, not a convenience)
  consumable: bool                     # is it used up? (affects repeatability of the gate)
  obtainable_before: <tier ref>         # reachability — without this the gate is a wall (PPL-A2)
  enterable: bool                       # place: can an actor be there at all
  has_property: <property enum ref>      # e.g. high_ambient_energy — a PROPERTY, not a place
  persists_for: <duration class>         # status: does the condition survive the attempt
  count: <cardinality>                   # how many, never which
```

**Why this is the right shape and not a heuristic.** It is the repo's existing *closed-set ⇒ enum*
discipline (the Frontend-Tool Contract's rule, and doc 38's `CPL-A3` #1 *"closed sets as enums"*)
applied to a cross-generator contract. It is machine-checkable, it fails loudly, and widening it
requires someone to argue that progression legitimately needs a new property — which is exactly the
conversation that should happen before the boundary moves.

**The intuition it encodes:** *a requirement must be satisfiable by more than one design.* If exactly
one possible item can satisfy the predicate, the planner designed the item.

---

## 4 — `PPB-A4` — a gate belongs to whoever REFUSES

`PPL-A1` listed Gates as one of the four parts. Ownership, corrected:

| gate | who authors it | what the planner supplies |
|---|---|---|
| **breakthrough condition** — the transition rule of the ladder itself | **the planner** — it is its own state machine | the whole thing; its *leaves* are `RoleRequirement`s |
| **combat effectiveness** (realm-gap curve, `strike_formula`) | combat module | ③ `StateExposure` |
| **place access** (*"not below Foundation Establishment"*) | place / access module | ③ |
| **recipe attempt** (*"may attempt grade-N"*) | crafting module | ③ |
| **skill check** at interaction | `PL_005` | ③ |

**The planner authors exactly one class of gate, and it is internal.** Everything else it makes
*legible* and steps back from. That is the sentence docs 40/41 were missing.

---

## 5 — `PPB-A5` — closure splits in two, and the planner can finish before the world does

`PPL-A2` said: every variable needs an inflow and a gate. Under `PPB-A1` the planner **cannot author
either** for most variables — so as written, `PPL-A2` was a check the planner could never pass without
committing the scope violation this document forbids. It splits:

| | **internal closure** — the planner's own gate | **assembly closure** — the world's gate |
|---|---|---|
| checks | every declared variable has ≥1 `ContributionPoint` **and** ≥1 `StateExposure`; every `RoleRequirement` is well-formed and vocabulary-legal | every `RoleRequirement` is `bound`; every `ContributionPoint` has ≥1 real `CONTRIBUTE`; every `StateExposure` has ≥1 real reader |
| when | the planner's own loop (`PPL-A6`) | **manifest assembly**, across all element modules |
| failure means | *the planner is not done* | *the world is not closed* — a dangling variable or an unreachable gate |
| who fixes it | the human in the planner loop | whichever module owns the missing side |

> **`PPB-A5`.** The progression planner is **DONE** when it is internally closed. It does not block on
> the item generator, and it does not get to call the world playable.

This resolves [`40.2` §10.2](02_outcome_contract.md) (*"do planners compose over the demand graph?"*)
without a composition engine: they do not compose, they **publish and bind**. And it fixes a real
deadlock the old framing had — under `PPO-A1`, progression could not finish until crafting existed,
while crafting's contribution target could not exist until progression declared it.

**The `PPL-A2` failure modes move house**, and that is the correct home for them:

| | old (planner-only) | now |
|---|---|---|
| **Dangling variable** — nothing reads it | planner finding | **assembly** finding: a `StateExposure` with no reader |
| **Unreachable gate** — nothing raises it | planner finding | **assembly** finding: a `ContributionPoint` with no contributor, or a `RoleRequirement` never bound |

The planner literally cannot see either. Reporting them at the planner was the check pretending to a
scope it does not have.

---

## 5A — `PPB-A6` — TWO LAYERS: contracts first, generation second, and the ⚠ dependency is retracted

Doc 38's element roster carries this row:

> **Progression system** · depends on **rules, place, item** ⚠

> **That dependency is wrong, and the ⚠ was the tell.** — PO, 2026-07-31:
> *"We have to decouple. Build progression's part and create the contract; then item comes and feeds
> our contract into itself. I think we should do a **two-layer generator** to decouple the generators.
> Step 1: create the contract. Step 2: the generators take the already-created contract and generate,
> without depending on each other."*

`PPB-A1`..`A5` say what may cross the boundary. This says **when**, and it is what makes the rest
mechanically achievable rather than aspirational.

```
L0 · VOCABULARY  ── authored once, versioned, cross-module ────────────────────
     element kinds · REQUIREMENT_VOCABULARY · property enums · trigger classes
     the closed sets every contract is written IN
                                   │
                                   ▼  (frozen)
L1 · CONTRACT  ── every module, IN PARALLEL, reading only L0 ──────────────────
     progression:  DECLARE kinds/curves/tiers · REQUIRE roles · EXPOSE sockets + state
     item:         DECLARE item schema/classes · REQUIRE  … · EXPOSE …
     place:        …            character: …            crafting: …
     ✗ no module reads another module's L1 while L1 is being written
                                   │
                                   ▼  ★ FREEZE — the contract set is content-addressed
L2 · GENERATE  ── every module, IN PARALLEL, reading only the FROZEN L1 set ───
     item:         reads REQUIRE role(breakthrough_catalyst) → designs an item → BIND
     place:        reads REQUIRE role(sealed_place)          → designs a place → BIND
     combat:       reads EXPOSE readable(inner_power.tier)   → authors the realm-gap curve
     progression:  compiles its declarations → RealityManifest rows
     ✗ no module reads another module's L2 output. Ever.
                                   │
                                   ▼
ASSEMBLE  ── assembly closure (PPB-A5): every REQUIRE bound · every socket plugged ·
             every exposure read. Refuse on `open`.
```

> **`PPB-A6`.** Generation is **two layers separated by a freeze**. In L1 a module may read only the
> shared vocabulary; in L2 it may read only the **frozen L1 contract set**. **No module ever reads
> another module's L2 output.** Dependency between modules is therefore a dependency on a *contract*,
> not on a *run* — so every module in a layer can run in any order, or all at once.

### 5A.1 What this fixes, concretely

| the old ⚠ dependency implied | under `PPB-A6` |
|---|---|
| progression must run **after** place and item | progression's L1 is complete with **no item and no place in existence** — it emits role slots |
| item must know which progression tier gates it | item's L2 reads progression's **L1 contract**, where the tiers are already declared |
| a cycle: progression needs items, item needs tiers | **there is no cycle** — both needs are satisfied at L1, which neither module's L1 depends on |
| generation order is a DAG that must be scheduled | one **barrier**, not an N-way DAG. `CPL-A9`'s ordering claim survives as a claim about *contracts* |

The cycle is worth dwelling on because it is the reason the ⚠ existed at all. `CPL-A9` said
*"a progression kind's terms must reference quantity ordinals that exist before the kind"* and read
that as *module* ordering. It is **contract** ordering: L0 owns the ordinal space, L1 references it,
and nothing has to run first.

### 5A.2 L0 is not a formality — it is what makes L1 independent

If progression's requirement says `has_property = high_ambient_energy`, that property name belongs to
place's ontology. Written at L1, that is a cross-module read and the decoupling is already broken.
**So the shared vocabulary must precede both**, and every term a contract may use — element kinds,
requirement predicates, property enums, trigger classes — lives in L0, closed and versioned.

This closes two of this document's own open questions: `REQUIREMENT_VOCABULARY` has a home (L0, in
`contracts/`, with a lint — the shape the frontend-tools contract already uses), and `has_property` is
not a back door but an L0 term like any other.

**L0 is small and it is expensive to change.** Adding a term is a cross-module architecture decision.
That friction is correct: L0 is the only place where modules are genuinely coupled, so it should be
the hardest thing to move.

### 5A.3 Binding: who does it, and what happens when nobody does

**The module that FILLS a role declares the bind**, at L2, because only it knows which of its outputs
was made for that purpose. Assembly verifies; it does not match-make — a matcher would be a fourth
authority guessing at intent.

| case | verdict |
|---|---|
| exactly one module binds a role | ✅ |
| **two modules bind the same role** | **REFUSE.** Ambiguity is a human decision, not a first-wins race |
| **nobody binds a role** | assembly fails with the role, its `raised_by` decision and its evidence — the human either drops the gate or accepts a different one (open #2) |
| a module binds a role that was never required | REFUSE — an orphan bind means someone read a stale contract set |

### 5A.4 The freeze is what makes L2 reproducible

The L1 set is **content-addressed** and its digest is an input to every L2 run. Two consequences,
both already load-bearing elsewhere in this repo:

- **L2 is `f(frozen contracts, seed)`** — the same shape as `CPL-A12`'s pinned manifest. Re-running
  item generation against the same contract digest yields the same items.
- **A contract change invalidates L2, visibly.** Without the freeze, editing progression's tier list
  mid-run would silently produce items binding a tier that no longer exists. With it, the digest
  moves and every L2 output built on the old one is stale by construction rather than by inspection.

### 5A.5 What this costs, stated rather than hidden

**A module cannot react to what another module actually produced.** If the item generator invents a
genuinely wonderful artifact that *should* gate a new progression tier, progression cannot see it —
it is L2 output, and L2 is not readable. The only path is a **second round**: amend L1, re-freeze,
re-run. That is the price of decoupling and it is the right price, but it is a real constraint and it
means round count is a design parameter, not an accident.

`CPL-A15`'s runtime-authored tier already lives outside this pipeline, so the cost lands on build-time
authoring only.

---

## 6 — The straddling class dissolves

[`40.2` §2](02_outcome_contract.md) called five of eighteen loops *"straddling"* — a progression kind
whose inflow and gate both live elsewhere — and treated it as an awkward special case. Under this
boundary it is not special; it is **the normal case**, and it now has a clean encoding:

```
alchemist_grade
  DECLARE   kind(alchemist_grade, Skill, curve=Log, cap=HardCap(9))     ← planner owns, fully
  EXPOSE ②  contribution_point(alchemist_grade, trigger=craft_success,
                               magnitude ∈ policy band)                  ← planner publishes the socket
  EXPOSE ③  readable(alchemist_grade) : ordinal, 9 values                ← planner makes it legible
  ────────────────────────────────────────────────────────────────────
  crafting  CONTRIBUTE alchemist_grade on craft_success   (crafting decides the rate)
  crafting  GATE recipe_attempt requires alchemist_grade ≥ N  (crafting authors its own refusal)
```

**The planner writes three lines and owns all three.** Crafting writes two and owns both. Nobody
reaches across. What looked like a straddle was just the missing vocabulary for a socket.

The same rewrite applies to artifact refining, the four minor professions, sect rank and heart-demon —
all five. `PPO-A1`'s *count* stands (4 pure / 5 straddling / 9 demand); its *conclusion* — that the
planner must specify the mechanism — does not.

---

## 7 — Worked example: *"Foundation Establishment requires a foundation pill and a sealed cold place"*

**What the planner emits** — and this is the whole of it:

```
DECLARE  kind(inner_power, Stage, tiers=[…, foundation_establishment, …], cap=TierBased)
DECLARE  breakthrough(inner_power → foundation_establishment,
                      requires = [ role(breakthrough_catalyst), role(sealed_place) ])
REQUIRE① role(breakthrough_catalyst): item,  consumable=true,
                                       obtainable_before=qi_condensation_9
         raised_by = D-142   evidence = CITED (chunk 7, span 12..38)
REQUIRE① role(sealed_place):          place, enterable=true,
                                       has_property=high_ambient_energy
         raised_by = D-143   evidence = CITED (chunk 7, span 44..71)
EXPOSE②  contribution_point(inner_power, trigger=meditation_tick, magnitude ∈ band)
EXPOSE③  readable(inner_power.tier): ordinal, totally ordered
```

**What the planner must NOT emit**, each with the module that owns it:

| forbidden | owner |
|---|---|
| the pill's name, recipe, price, rarity, drop source | item |
| that the pill is *crafted* at all (it could be found, gifted, inherited) | item |
| the pool's coordinates, biome, region, guardians | place / world |
| how much a meditation tick actually yields | numeric policy (`PGN-A15`) |
| that failing the breakthrough costs 10 years of lifespan | *another progression declaration* — legal, but a separate decision with its own provenance, not a rider on this one |

**What comes back:**

```
item      BIND role(breakthrough_catalyst) → item:foundation_pill
place     BIND role(sealed_place)          → place:cold_pool_of_the_northern_ridge
crafting  CONTRIBUTE alchemist_grade …     (unrelated to this gate; plugged into ②)
combat    reads ③, authors the realm-gap curve
```

**Assembly closure** then verifies both `REQUIRE`s are bound, `②` has a contributor, `③` has a
reader — and only then is the world closed.

---

## 8 — Trust properties

| id | property | mechanism | can it fail? |
|---|---|---|---|
| `PPB-T1` | the planner authors no other module's element | the compiler emits only `DECLARE`/`REQUIRE`/`EXPOSE`; there is no output channel for an item, place or recipe | yes — a schema with an `item_name` field on a requirement reds it |
| `PPB-T2` | a requirement does not over-specify | `PPB-A3`: predicate terms enum-validated against `REQUIREMENT_VOCABULARY` | yes — *"costing 500 spirit stones"* has no legal term and is refused |
| `PPB-T3` | the planner finishes without the world | internal closure (`PPB-A5`) does not read any other module's output | yes — an internal check that queries a `BIND` reds it |
| `PPB-T4` | nothing silently vanishes at the seam | every `REQUIRE` is `open`, `bound` or `refused(reason, owner)`; assembly refuses on `open` | yes — a dropped requirement leaves the world un-closed and named |
| `PPB-T5` | a socket with no plug is caught | assembly closure: `ContributionPoint` with zero contributors | yes — POC-1's output is the first failing subject (every kind, zero contributors) |

`PPB-T5` shares POC-1's fact set with `PPL-T8`, which is the point: the same failing artifact bites
two checks at two different layers, and neither can be satisfied by the other's evidence.

---

## 9 — What this changes in 40.1 and 40.2

| doc | change |
|---|---|
| `PPL-A1` | ontology **unchanged** (four parts); **ownership corrected** — the planner authors Variables, Couplings-among-progression, and exactly one gate class (`PPB-A4`) |
| `PPL-A2` | **splits** into internal + assembly closure (`PPB-A5`); the two failure modes move to assembly |
| `PPL-A7` | `Demand{shape}` → **`RoleRequirement`** with a closed predicate vocabulary (`PPB-A2`①, `PPB-A3`). The word *shape* was the leak. |
| `PPL-A10` | the fact set gains two more relations: `ContributionPoint` and `StateExposure`. `OUTCOME` is **declarations + three contract artifacts**, not a pair. |
| `PPL-T2` | splits into `PPB`-layer internal/assembly checks |
| `PPO-A1` | count stands; *"demands the mechanism"* is **retracted** — §6 |
| `PPO-A6` | a CQ answerable only from another module's output is an **assembly** CQ, not a planner CQ. §5's nineteen must be split accordingly before the spike. |
| `PPO` §10.2 | **closed** — planners do not compose; they publish and bind (`PPB-A5`) |
| doc 38 | **two amendments, PROPOSED.** (a) `CPL-A3` is applied, not changed. (b) **`CPL-A9` is corrected**: the roster's *"Progression system · depends on rules, place, item ⚠"* is **retracted** — under `PPB-A6` there is no module→module dependency at all, only module→contract. The ordering claim survives as a statement about **L0 → L1 → L2**, which is one barrier rather than an N-way schedule. |
| `PPB-A6` scope | this is a **pipeline-wide** architecture, not a progression rule. It is written here because progression is where the violation surfaced, but it governs every element module and belongs in doc 38 once reviewed. |

---

## 10 — Open

1. ~~Who owns `REQUIREMENT_VOCABULARY`?~~ **CLOSED by `PPB-A6`** — it is L0, in `contracts/`, with a
   lint. Same shape as the frontend-tools contract.
2. **What binds a role when no module wants it?** Assembly fails with the role, its `raised_by`
   decision and its evidence (§5A.3). Open: where that refusal *surfaces* in the planner loop, and
   whether it re-opens L1 automatically or waits for a human.
3. **Can two roles bind to the same instance?** *The* cold pool satisfying both a breakthrough gate and
   a training-location condition is normal and probably fine — but it makes the two gates correlated,
   which matters for pacing (`CQ-A1`). Note it; do not solve it yet. (Distinct from §5A.3's *two
   modules binding one role*, which is refused.)
4. ~~Is `has_property` a back door?~~ **CLOSED by `PPB-A6` §5A.2** — the property enum is an L0 term
   like any other, and L0 precedes every L1.
5. **How many rounds?** §5A.5 makes round count a design parameter: L1 → freeze → L2 → *(amend L1,
   re-freeze, re-run)*. One round is clean and blind; two lets progression react to what item actually
   built. **What triggers a second round, and who decides it is worth the re-run?**
6. **Does every element module fit the L1/L2 split?** Progression is nearly pure-L1 (its L2 is just a
   compile). Item is nearly pure-L2. World/geography may be neither. A module that needs to read
   another's L2 would break `PPB-A6` — before adopting this pipeline-wide, walk all seven roster
   entries and find out whether one does.
