# Command — the control substrate

> # 🔴 QUARANTINED — DO NOT BUILD FROM THIS
>
> **This round's Phase 0 is FALSE.** Its §0 states *"In code: nothing… In design: two
> things, and both are refused."* A cold-start review found **4 017 lines of directly
> relevant prior design**, three days older, in this same `docs/specs/` tree, which
> this round never opened:
>
> | | lines | what it already contains |
> |---|---|---|
> | `../2026-08-02-command-interaction-structure.md` | 415 | **`from: Offered \| Any // THR-A4`** — the offer concept this round presents as its central invention, already a declared field · The Sims smart objects, already sourced to `D-2` · deterministic lockstep, already concluding *"a command is data by necessity, not by taste"* |
> | `../2026-08-02-command-interaction-dataflow.md` | 877 | the specification proper |
> | `../../plans/2026-08-02-command-interaction-RUN-STATE.md` | 796 | decisions **`CMD-1`..`CMD-9`** — which this round's `CMD-D1`..`CMD-D7` collide with, one letter apart, same subject |
> | `../2026-08-02-item-data-structure.md` | 611 | *"the substrate under **ownership, inventory, equipment and transfer**"* — the holder graph this round declares a 🔴 BLOCKER with *"today there is no outside"* |
> | `../2026-08-02-item-dataflow.md` | 1 318 | its specification |
>
> **How it happened, precisely:** every absence claim in this round was a `grep` over
> `crates/` and `services/`, reported as a repo-scoped conclusion. **`docs/specs/` was
> never searched.** That is the exact defect Phase 0 exists to prevent, performed by a
> section that claims to BE Phase 0 — and it is the same shape as the actor-hub round
> that designed feature #1 without auditing what already modelled an actor.
>
> **Nothing here is authoritative until it is reconciled with the 2026-08-02 rounds.**
> Individual findings may survive; the framing ("feature #2", "nothing implements
> this", the blocker, the decision ids) does not.



**Status:** DESIGN, unreviewed. Nothing implements this.
**Feature:** #2. Actor hub was #1.
**Date:** 2026-08-05

> **A command is not a method on an actor. It is a declared capability that some
> entity OFFERS, which some actor may SPEND its turn to invoke.**
> Those are three different nouns and the whole design is refusing to collapse them.

---

## §0 · Phase 0 — what already claimed to model this, and why it is refused

**In code: nothing.** No command, no registry, no affordance. (`world-gen`'s
`enum Command` is CLI argument parsing; `agent-registry-service`'s "commands" are
user-authored slash commands for the agent tier. Different concepts, same word.)

**In design: two things, and both are refused.**

### 0.1 `EF_001` affordances — REFUSED, one idea kept

The old entity foundation declares:

```rust
fn type_default_affordances(&self) -> AffordanceSet;   // "PCS_001 / NPC_001 / Item / EnvObject MUST declare"
affordance_overrides: Option<AffordanceSet>            // per-instance override
```

with flags like `be_received`, `be_contained_in`, and a validator stage
`3.5.a entity_affordance` that checks lifecycle plus those flags.

Two reasons it cannot be adopted:

1. **It is keyed on a closed entity-TYPE set** — `Pc / Npc / Item / EnvObject`.
   That is the archetype enum, and it is the same shape `0017`/`0018` removed and
   `D-2` forbids: *the engine closes on MECHANISM, the manifest closes on
   VOCABULARY.* There is no `Pc` and no `Npc`; there is only an actor.
2. **It models the wrong direction.** An affordance flag answers *"may X be done
   TO me"* — a permission bit on the target. A command answers *"what can be done,
   BY whom, with which arguments, at what cost"*. `be_received` cannot express
   *"consume this scroll, destination ∈ {hangzhou, suzhou}"*: there is no
   parameter, no cost, and no provider.

**Kept:** the layering — a **type-level default** narrowed by a **per-instance
override**. That cascade is right and it recurs across this repo (System →
per-user → per-book). It is reused in §3 without the type enum.

### 0.2 `CombatPayload` — out of scope here, and a constraint

The PO has scoped combat's own Phase 0 out of this round. It still constrains this
design in one way: `CombatPayload` is a **god enum** — adding an action edits the
enum, `Vocabulary::validate`'s `match`, `actor_of()`, and the domain law. **This
design exists so that the second action never costs four edits.** Whatever lands
here must make `CombatPayload` shrinkable, not join it.

---

## §1 · Three layers, and the collapse each one prevents

| layer | what it is | when it exists | who authors it |
|---|---|---|---|
| **Definition** | *"a `consume` command exists; it takes a `destination`; it costs a turn slot; it requires the invoker to hold the provider"* | authored once, in the ruleset/manifest | content |
| **Offer** | *"scroll instance `#7`, held by actor `A`, can be consumed right now, and `destination` admits `[hangzhou, suzhou]`"* | minted per (subject, tick) by the engine | engine |
| **Invocation** | *"offer `o_91f3`, destination = `hangzhou`"* | produced by a driver | driver |

**Definition without Offer** is `consume(item_id, location)` — a free-parameter
function call. The caller must then know the item exists, that it is held, and that
the destination is reachable. All three are engine facts, so the engine's authority
has moved into the driver. This is what `THR-A4` already forbids for combat targets:
*"the model cannot name anyone the engine did not offer."*

**Offer without Definition** is a hardcoded list of verbs — `CombatPayload` again.

**Invocation carrying anything but an offer id + chosen arguments** re-opens the
same hole: any field a driver fills freely is a field the engine must re-derive.

---

## §2 · Why a command cannot hang off the actor

Because the thing that **offers** a command is usually not the actor.

```
  scroll #7        ── offers ──▶  consume(destination)
  actor A          ── spends ──▶  turn slot, and is the SUBJECT
  the map node     ── offers ──▶  travel_to(node)
  a learned skill  ── offers ──▶  activate(target)
  actor A itself   ── offers ──▶  speak(text)          ← the actor CAN be a provider
```

So every offer carries **two entity references, and they are different roles**:

- **provider** — the entity whose declaration produced this offer. Consuming an
  item destroys the *provider*. Losing a skill removes its offers.
- **subject** — the actor whose resources are spent and whose turn it must be.
  The subject is what a driver is entitled to (§5), never the provider.

`consume(item_id, destination)` collapses provider into a parameter and drops the
subject entirely. That is why the signature reads wrong: it is not that the
arguments are missing, it is that the *roles* are missing.

**Corollary — this is why the actor needs no archetype.** An actor does not have a
`kind` that determines what it can do. It has *attached providers*, and offers are
whatever those providers declare. Exactly the hub's rule for quantities: *"a
quantity is present because a plugin that declares it is attached."*

---

## §3 · The registry — what "control hub" means

The control hub is a **registry + a projection**, not a dispatcher. It answers one
question:

```
offers_for(subject, as_of_tick) -> [Offer]
```

It never executes anything. It composes:

1. every provider currently attached to / reachable by `subject`
2. each provider's **command definitions** — type default, narrowed by per-instance
   override (the one idea kept from `EF_001`)
3. each definition's **parameter domains**, computed against live state
4. dropping any offer whose preconditions already fail

Point 4 is a **convenience, not a guarantee** — see §6.

This is the same shape as the actor hub: the hub holds no vocabulary, plugins
declare, the hub folds. Here the hub holds no verbs, providers declare, the hub
enumerates. **A new command is a new declaration; the engine never learns its name.**

---

## §4 · Parameters are DOMAINS, not values

An offer does not say *"takes a destination"*. It says *"takes a destination, and
these are the destinations"*:

```
Offer {
  offer_id,                        // minted, per (subject, tick, provider, command)
  provider, subject, command,
  params: [ Param { name: "destination",
                    domain: Enumerated([hangzhou, suzhou]) } ],
  cost:   [ Resource(turn_slot, 1) ],
}
```

`Enumerated` is the only domain kind this design commits to. Ranges, free text and
open references are **deliberately not decided** (§8) — every one of them is a hole
through which an unvalidated value could reach the engine, and none is needed by any
command that exists.

A driver's invocation names an `offer_id` and picks **inside** the declared domains.
Anything else is rejected at admission, by comparing against the offer the engine
itself minted.

---

## §5 · The entitlement stage this supplies

Today admission runs `schema · producer-identity · idempotency ·
decision-vocabulary`. `producer-identity` proves **which service** sent a proposal.
**Nothing checks which actor that producer may act for.** It does not bite yet
because the host wires each driver to a specific actor — the entitlement is implicit
in the wiring. The day a human at a GUI becomes a producer, that implicit wiring
becomes a security boundary.

Offers close it without a new subsystem:

- an offer is minted **for a (session, subject) pair**. `CMD-D4` gives the
  mechanism: `offer_id` is a keyed MAC over the offer's own inputs, so binding
  is recomputation rather than a trusted lookup table
- a new admission stage **`offer-entitlement`** re-derives the offer from
  `(offer_id, claimed subject, producer)` and rejects a mismatch
- so a driver cannot invoke an offer it was not given, and cannot act for an actor
  it was not bound to

**This is the design's main security claim, and it is the one that most needs an
adversarial review.** An `offer_id` that is merely unguessable is a bearer token; if
it leaks it is authority. It must be *bound*, not merely secret — re-derived, not
looked up in a trusted table.

---

## §6 · An offer is a HINT; the guarantee is at step time

The registry computes offers from state at tick `T`. The island resolves at step
time, which is later. In between, the actor may have been stunned, the scroll may
have been stolen, the destination may have burned down.

The existing code already states this for initiative:

> *"Evaluated at STEP time against live state, which is the only moment the answer
> is definite: an actor that was next when the proposal was made may have been
> stunned, hasted or killed since."*

So: **every precondition an offer filtered on MUST be re-checked at step time.**
The offer's filtering exists to keep drivers from proposing obviously-dead actions;
it is a UX and token-cost optimisation, never an authorisation. If the two ever
disagree, step time wins and the invocation fails as a rule violation — which is
also exactly how two drivers racing for one turn slot resolves.

**A design that treats the offer as a promise has moved authority to tick `T`.**

---

## §7 · Preconditions are DECLARED; resolution is CODE

This is the assumption the PO flagged, stated with its trade-off.

The hub sealed: *"A condition is a declared threshold, never a predicate grammar —
a grammar is code wearing a data costume."*

Applied here:

- **Preconditions are declared**, over a **closed, engine-owned set of relation
  kinds**: `ResourceAtLeast`, `LinkExists` (holder/containment), `TagPresent`,
  `Adjacent` (map graph). A manifest may combine them; it may not invent one.
- **Effects are declared**, and may only name mechanisms the engine already has:
  spend a resource, destroy the provider, hand a `Portable` to another island, emit
  an `External`.
- **Computation is not a command's business.** A damage formula is not a
  precondition — it is *resolution*, which already lives in `Domain::step`. A
  command declares *"invoke resolution `R` with these bindings"*; `R` is code,
  registered like a plugin.

**Why this is not the grammar the hub refused:** the refused thing was an *open*
predicate language where a manifest could express arbitrary logic. A closed set of
four relation kinds is the same closure discipline as ordinals — the engine owns the
alphabet, the manifest owns the sentences.

**The escape valve — taken from Skyrim, not invented here (§11.2).** The first draft
of this section said a fifth relation kind requires an engine change, full stop.
That is wrong, and a shipped game shows why: when a Creation Kit condition has no
scripting equivalent, the documented workaround is *not* to add a condition function
— modders cannot — but to **project the missing condition into a value the closed
set can already read**: a constant effect writes a global variable, and the
condition tests the global.

So the closed set gains one member and the problem dissolves:

- **`ValueAtLeast(declared_variable, n)`** — a declared, engine-readable value that
  a declared *effect* may write.

Arbitrary derived state now reaches preconditions **without the precondition
language growing**. The manifest still ships no code; the computation lives where
computation already lives (resolution), and its result is deposited in a variable
the closed alphabet can read.

**The trade-off, restated honestly:** this is powerful enough to be abused. A
content author can encode a whole rules engine as a web of variables written by
effects. That is a *review* problem, not an architecture hole — the engine still
owns every verb that can execute.

---

## §8 · Assumptions — stated so they can be attacked

1. **Every entity that participates in the map can be a provider.** Doors, nodes,
   items, skills, actors. Nothing is special-cased.
2. **Every invocation has exactly one subject.** Multi-subject commands are out
   of scope, and `CMD-D7` settled WHY: a two-party act needs CONSENT from the
   second subject's driver, and consent is a negotiation protocol with its own
   states — not a command.
3. **One offer set per (subject, tick).** Offers do not survive a tick. This is what
   makes them safe to treat as hints.
4. **`Enumerated` is the only parameter domain.** `CMD-D6` gives the admission
   test for a second kind: a real command must need it AND **the engine must
   clamp it**. An unclamped `Range` is a free parameter wearing a type.
5. **Turn slot stays the arbitration primitive**, and it is a per-domain resource,
   not a command-layer concept. The command layer *declares a cost*; the domain
   owns whether the cost can be paid.
6. **Offer computation is not free.** Enumerating destinations for every actor every
   tick has a cost nobody has measured. If it does not fit the tick budget, offers
   become lazy/pull rather than eager/push — a change of delivery, not of model.
7. **Tags are hierarchical** (§11.1). `TagPresent` matches on a hierarchy
   (`status.stunned` is matched by a requirement on `status`), not on string
   equality. Same closure cost, much more expressive, and it is what the most
   widely deployed ability framework chose.
8. **Not every command is driver-invoked** (§11.4). A provider may declare commands
   that fire on a trigger — on-equip, on-hit, periodic — which no driver ever sees
   in an offer set. **The first draft assumed every command was a driver choice and
   that assumption was wrong.** Trigger kinds are therefore part of a Definition,
   and only the `on_invoke` kind produces offers.

---

## §9 · What this design does NOT decide

**Six items that stood here have been decided** — see
[`2026-08-05-resolutions.md`](2026-08-05-resolutions.md). Kept as a pointer rather
than deleted, because a list of open questions that quietly loses entries is how a
resolved decision gets re-litigated:

| was open here | now |
|---|---|
| where the registry runs | `CMD-D3` — commit-service, forced by live island state |
| an order queue | `CMD-D5` — no queue in the substrate; it is the driver's |
| multi-subject commands | `CMD-D7` — out, because they need consent |
| parameter domains beyond `Enumerated` | `CMD-D6` — closed, with a clamp test for admitting a kind |
| whether `CombatPayload` is replaced | `CMD-D1` — it is COMBAT's to keep, decode or delete |
| override vs contribution across features | `CMD-D2` — collision fails the build; amendment is additive |

**Inventory ownership is no longer a deferred item — it is a 🔴 BLOCKER.** An item is
`External` from the island's view, so something outside must own the holder graph,
and measurement found that nothing does. That makes `LinkExists` — one of §7's five
precondition kinds — unimplementable, and it is the relation this document's own
worked example rests on. See the resolutions doc.

**Still genuinely open, and only this:**

- **the wire shape of an offer.** This document names roles, not JSON. Designing a
  wire format with zero declared commands is the declared-general-with-one-instance
  trap; the first real command decides it.
- **how offers are delivered to a GUI vs. an LLM** is *not* open in substance — both
  consume the same offer set and neither gets a privileged path (§10). What is open
  is only the rendering, which is each driver's business.

---

## §10 · How it lands on what already runs

```
  registry.offers_for(subject, tick)          ← engine mints offers
        │
        ├── LLM driver: offers → tool schemas → one LLM call → pick
        └── human driver: offers → GUI affordances → click
        │
        ▼
  Invocation { offer_id, args }               ← a REQUEST, never a write
        │
        ▼
  admission:  schema · producer-identity · offer-entitlement (NEW)
              · idempotency · parameter-domain
        │
        ▼
  Admitted<D>                                 ← only admission mints it; bypass does not compile
        │
        ▼
  Island::submit → step time: preconditions RE-CHECKED, turn slot spent
        │
        ├── External  → commit-service authorisation (inventory, progression)
        └── Portable  → depart / arrive (cross-island travel)
```

Nothing on this path is new except `offer-entitlement` and the registry. The
proposal→admission→island spine, the `Admitted<D>` token, the step-time precondition
check, `External` and `Portable` all exist and are exercised today.

**Both drivers do the same thing.** That is the property to protect: the moment the
human path can pass a value the LLM path cannot, the human path is more privileged,
and the entitlement boundary in §5 has a hole in it.

---

## §11 · What long-lived games already settled — and where this design was wrong

Researched 2026-08-05 because several sections above were assumptions. Games with
dense entity counts and decade-long expansion cannot carry a bad control
architecture — if these questions had cheap wrong answers, those games would have
collapsed years ago. Three of the open questions are now settled by precedent, and
**two of this design's claims were wrong.**

### 11.1 Unreal's Gameplay Ability System — the closest existing thing, and it validates the riskiest claim

GAS is the most widely deployed version of this architecture, and it lines up
almost item for item:

| this design | GAS |
|---|---|
| registry per entity (§3) | `AbilitySystemComponent` — any Actor that participates must have one |
| Definition, with declared cost (§1) | `GameplayAbility` — *"defines what an ability does, what it costs, and when it can activate"* |
| Offer filter (§3.4) | `CanActivateAbility()` — tag requirements met, cost affordable, not on cooldown, no other instance running |
| `TagPresent` precondition (§7) | `GameplayTag`, with **Activation Required** and **Activation Blocked** tag sets |
| provider ≠ subject (§2) | abilities are *granted* to an ASC by items and effects; the ASC is the subject |

**And it confirms §6, the claim most likely to be wrong.** GAS predicts on the
client, then *the server runs the same activation again* and may reject it:
`TryActivateAbility` → `ServerTryActivateAbility` → `ClientActivateAbility(Failed/
Succeed)`, with every predicted side effect tagged by an `FPredictionKey` and
**rolled back on rejection**. The client's `CanActivateAbility` is a hint. The
server's is the guarantee. That is exactly *"an offer is a HINT; the guarantee is at
step time"* — arrived at independently, and it is the industry answer.

**One correction taken:** GAS tags are **hierarchical**, not flat strings. Same
closure cost, far more expressive. Adopted as assumption §8.7.

**One direction confirmed:** since UE 5.3 `GameplayEffect` moved to a **component**
architecture — *"each component defines a specific behavior — granting abilities,
blocking tags, applying additional effects, or checking requirements."* They
refactored *toward* the plugin shape this repo's actor hub already uses. That is
evidence about the direction of travel, not just the destination.

### 11.2 Skyrim — conditions are a CLOSED engine-owned set, and the escape is a variable

This settles §7's assumption directly. Creation Kit conditions are **data** on
perks, spells and dialogue, evaluated by the engine. Modders cannot add condition
functions: *"native functions ... do not contain Papyrus code ... modders cannot
simply add new condition functions themselves — they can only work with what the
engine provides."*

**But the escape hatch is the part worth stealing.** When a needed condition has no
scripting equivalent, the documented workaround is to make a constant-effect magic
effect that writes a global variable, condition the ability on that variable, and
let script read it. Arbitrary derived state reaches a closed condition language
**without the language growing**.

§7 originally said a fifth relation kind requires an engine change. That was wrong,
and §7 now carries `ValueAtLeast(declared_variable, n)` instead.

### 11.3 RTS lockstep — a command is an OBJECT, not a function call

Deterministic-lockstep RTS (StarCraft, Age of Empires, Warcraft III, Total War)
synchronises **inputs, not state** — *"a million units costs the same bandwidth as
one"* — with checksums to detect divergence. Orders are high-level (*"group 1 attack
position x"*), not resolved effects.

The load-bearing sentence: *"Commands should be implemented as **objects with state
machines, not one-off function calls**, which makes **queuing, undo, and replays**
possible."*

That is independent confirmation that `consume(item_id, destination)` is the wrong
shape and Invocation-as-object (§1) is right — and it names three payoffs. The event
ledger already gives replay. **Queuing has no home in this design**, which is now
recorded in §9 rather than left as a silent gap.

### 11.4 World of Warcraft — a provider REFERENCES declared commands, and not all are invoked

Items carry up to five spell-ID columns, and a trigger determines when each fires —
on use, on equip, periodic. An item does not *implement* an action; it *references*
a declared spell.

That is §2's provider/definition split, shipped and load-bearing for two decades.

**And it falsifies an assumption this design made silently:** it assumed every
command is a driver choice that appears in an offer set. On-equip and periodic
commands are never offered to anyone. Trigger kind is therefore part of a
Definition, and only `on_invoke` produces offers — recorded as assumption §8.8.

---

**Sources:**
[Understanding the Unreal Engine Gameplay Ability System](https://dev.epicgames.com/documentation/unreal-engine/understanding-the-unreal-engine-gameplay-ability-system?lang=en-US) ·
[Gameplay Ability System Reference — Unreal Directive](https://unrealdirective.com/resources/cpp-reference/gas/) ·
[GAS networking notes — Gamedev Guide](https://ikrima.dev/ue4guide/gameplay-programming/gameplay-ability-system/gas-networking/) ·
[FPredictionKey — Unreal Engine documentation](https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/GameplayAbilities/FPredictionKey) ·
[Condition Functions — CreationKit Wiki](https://ck.uesp.net/wiki/Condition_Functions) ·
[Arcane University: Scripting Best Practices — Beyond Skyrim](https://wiki.beyondskyrim.org/wiki/Arcane_University:Scripting_Best_Practices) ·
[Perk — CreationKit Wiki](https://ck.uesp.net/wiki/Perk) ·
[Lockstep as the RTS Gold Standard](https://www.socratopia.app/library/math-for-game-devs-en/chapter-30) ·
[Real-time strategy games — what makes them tick?](https://medium.com/adequatesource/real-time-strategy-games-what-makes-them-tick-4ac36bd3de95) ·
[Adding spell effects to custom or existing items (MaNGOS)](https://www.ownedcore.com/forums/world-of-warcraft/world-of-warcraft-emulator-servers/wow-emu-guides-tutorials/161503-mangos-adding-spell-effects-custom-existing-items.html)
