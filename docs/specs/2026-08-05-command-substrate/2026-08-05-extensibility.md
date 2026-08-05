# Extensibility — where a feature's command actually lives

**Status:** DESIGN, unreviewed.
**Question:** we will have N features. How does feature N+1 land without collapsing
the command layer? Does the feature implement its commands while the command layer
owns only the interface? A decorator? Something else?

---

## §1 · The test, before the answer

Every candidate below is judged by one criterion, because it is the criterion the
failures in this repo all failed:

> **THE N+1 TEST — can feature N+1 land without editing any file that the other N
> features share?**

`CombatPayload` fails it four times over: a new action edits the enum,
`Vocabulary::validate`'s `match`, `actor_of()`, and the domain law. That is the
definition of a god class — not that it is large, but that **everyone must touch it.**

`0006_projections` failed it too, in the other direction: ten tables were added
*without* anyone asking whether they had producers, because nothing in the shape of
the work forced the question.

The test is deliberately mechanical. A design that passes it in prose but not in
`git diff --stat` has not passed it.

---

## §2 · The four coupling points, and which are safe

A command system can only re-form a god class in five places. Four of them are
already safe **by decisions already sealed**; one is not.

| # | central thing | who edits it when feature N+1 lands | verdict |
|---|---|---|---|
| 1 | the set of **command names** | nobody — declarations are data, keyed by manifest id | **safe** |
| 2 | the set of **parameter domain kinds** (`Enumerated`, …) | engine only, rarely | **safe, bounded** |
| 3 | the set of **precondition relation kinds** (`ResourceAtLeast`, `LinkExists`, `TagPresent`, `Adjacent`, `ValueAtLeast`) | engine only, and §11.2's variable escape means almost never | **safe, bounded** |
| 4 | the **resolution function registry** | every feature registers into it | **safe only if DISCOVERED, never enumerated** |
| 5 | **`Domain::Payload`** — the type an invocation becomes before the island sees it | **every feature, today** | 🔴 **THIS IS THE GOD CLASS** |

Points 2 and 3 are bounded on purpose: the engine owns the alphabet, the manifest
owns the sentences. Growing the alphabet is an engine change and that is the price
of the manifest never shipping code (contract §7).

Point 4 has a known answer in this repo. `scripts/gate-self-tests.py` exists because
a hand-maintained list of gates silently dropped one; its rule is *"Discovered,
never enumerated. A gate added tomorrow is covered on its first commit, with nobody
to remember."* The resolution registry gets the same rule: a feature crate declares
its resolutions; the host **discovers** them. No central list to forget to edit.

Point 5 is the real problem, and the rest of this document is about it.

---

## §3 · The god class is `Domain::Payload`, and no amount of plugin discipline hides it

`sim_core::Domain` requires an associated `type Payload`. `Island<D>` is generic over
exactly one `D`. So every command that reaches an island must become a value of that
island's single payload type.

Today that type is `CombatPayload`, a Rust enum. Which means:

- a feature adding a command **must add a variant** — an edit to a shared file
- the domain's `check`/`apply` must **match** the new variant — another edit
- `actor_of()` must know the new variant spends a turn — another edit

**So it does not matter how beautifully the declaration layer is designed.** If an
invocation must become a variant of a shared enum to be executed, the enum is the
god class and every feature edits it. The N+1 test fails at the last step.

This is the single most important finding in this document, and it was invisible
until the question was asked in the form *"how does feature N+1 land?"*

---

## §4 · The candidates

### 4.1 Feature implements, command layer owns the interface *(the GAS shape)*

The command layer owns: Definition schema, offer minting, entitlement, invocation
validation, cost accounting. A feature owns: its declarations (data) + its
resolution code, registered as a plugin.

This is what Unreal's Gameplay Ability System does — `UGameplayAbility` is the base,
`AbilitySystemComponent` is the substrate, and a game's features supply abilities.

**Verdict: correct, and necessary — but it does not by itself pass the N+1 test.**
GAS gets away with it because a `GameplayAbility` is a *subclass*: polymorphism is
the payload, so there is no central enum. Our island has a single concrete
`Payload` type, so the same split leaves point 5 untouched.

### 4.2 Decorator

Wrap an entity in command-providing decorators; compose at runtime.

**Verdict: already present, under a different name — and not the answer.** A
*provider* (contract §2) is a decorator in effect: attach a scroll, gain its offers.
The composition question is solved. Decoration says nothing about how the invocation
executes, which is where the god class is.

### 4.3 ECS — command as component, feature as system

A feature adds a component; its system enumerates entities carrying it.

**Verdict: strong for the registry, silent on the payload.** It is a good answer to
*"which entities offer what"* and would scale to dense entity counts. It does not
answer how an invocation crosses into `Island<D>`, because ECS assumes the systems
*are* the executors — and here the island is the executor and the authority.

### 4.4 Erase the payload — an invocation IS data

`Payload` stops being an enum of verbs and becomes one shape:

```
Invocation { command_id, bindings }
```

The domain does not `match` on a verb. It **looks up the declaration** for
`command_id` — preconditions, costs, effects — and interprets it, dispatching to a
discovered resolution only where the declaration says computation is needed.

**Verdict: this is the only candidate that passes the N+1 test at point 5.**
Feature N+1 adds a declaration (data) and possibly a resolution (its own crate). It
edits no shared file. `CombatPayload` shrinks to nothing rather than growing.

---

## §5 · What 4.4 costs, stated plainly

It is not free, and the cost is real:

- **Exhaustive matching is gone.** A Rust enum makes "did you handle every action?"
  a compile error. A `command_id` string makes it a runtime lookup. The compiler
  stops being the thing that catches an unhandled command.
- **The declaration becomes load-bearing at runtime.** A malformed or missing
  declaration is a runtime failure where it used to be a build failure.
- **Determinism gets harder to hold.** Lockstep RTS demands bitwise-identical
  simulation; an interpreter over declarations has more surface for divergence than
  a `match` over a closed enum. `sim-core` already requires a seeded `DetRng` and
  deterministic iteration order — the interpreter must not introduce a map iteration
  anywhere on the resolution path.

**The mitigation is the same one this repo has used all day: replace the compiler
with a check that can go red.** A ruleset digest already pins the declaration set
(`RLS-A13` content address). What is missing is a gate asserting that **every
declared command resolves** — the exact mirror of `orphan-model-gate`, which asks
whether every handled event has a producer. Here: does every declared command have a
resolution, and does every registered resolution have a declaration? Both
directions, or the registry only grows.

That gate does not exist and is not built. It is named here so the trade-off in 4.4
is not accepted on a promise.

---

## §6 · Recommendation

**4.4 (erase the payload) + 4.1 (feature owns implementation, substrate owns the
interface) + point 4's discovery rule.** They are three answers to three different
questions and none substitutes for another:

- **4.1** answers *who writes what* — substrate owns the interface, feature owns the
  declaration and the resolution
- **discovery** answers *how the substrate finds it* — never a hand-maintained list
- **4.4** answers *how it executes without a shared enum* — the payload is data

Decorator is already covered by provider attachment. ECS is worth revisiting for the
registry's performance question (contract §8.6) but is not an answer here.

---

## §7 · `CMD-D1` — the payload is DATA. SEALED by the PO, 2026-08-05.

> **A compiled payload enum and a manifest-defined skill are mutually exclusive.
> You cannot have both. We have already chosen the manifest.**

That is the PO's argument and it is not a preference — it is an implication, and it
settles §3 without needing any of §4's comparisons.

**The reasoning, stated so it cannot be re-litigated from memory:** this project
already pushes definitions out to the manifest — a skill is *defined there*. If a
skill's action must become a variant of a compiled Rust enum before it can execute,
then a manifest cannot define a skill. It can only *select* among skills the engine
was compiled to know. That is not "content defines skills"; it is "content picks
from a menu the engine wrote". The manifest decision was made long before this
document, so the payload question was already answered — it just had not been asked
out loud.

### 7.1 What this actually means — the boundary

`Domain::Payload` becomes one data shape for every feature:

```
Invocation { command_id, bindings }
```

and the boundary falls exactly here:

| | owner |
|---|---|
| the payload **TYPE** — one shape, opaque bindings | the **command substrate** |
| what a `command_id`'s **bindings MEAN**, and the resolution that consumes them | the **feature that declared the command** |

So **`CombatPayload` is not "replaced by the command layer."** It becomes combat's
own internal representation, decoded from bindings *inside* the combat feature, if
combat still wants one. Whether it keeps a typed enum behind its own door is
**combat's decision, in combat's own round** — the substrate has no opinion and
must not acquire one. The PO's phrasing: *payload is now the feature's business,
not the command's.*

### 7.2 What does NOT change

**The engine keeps its own privileged payloads.** `EndTurn` is host-submitted
precisely so *"no driver (player, LLM or script) can mint itself another action by
asking for one"*. Making driver invocations data does not hand drivers the host's
verbs — `sim-core`'s ingress already separates ordinary domain work from a kernel
control item, and that separation is what carries this.

### 7.3 What this makes MANDATORY, not optional

Sealing `CMD-D1` accepts §5's costs, so §5's mitigation stops being a suggestion:

1. **The declaration↔resolution gate ships with the FIRST declared command, not
   after.** Both directions — every declared command resolves, every registered
   resolution is declared. Without it, "the compiler no longer catches an unhandled
   command" is a hole rather than a trade.
2. **Determinism must be re-proved against an interpreter.** `sim-core`'s existing
   determinism tests were written against a `match`. An interpreter has more
   divergence surface; a map iteration anywhere on the resolution path breaks
   lockstep, and nothing currently forbids one there.
3. **A manifest-only feature must be a first-class case.** Discovery implies
   compiled-in plugins. If a feature that declares a command but ships no resolution
   cannot work, then "content can add a command" quietly means "content can add a
   command that does nothing new" — and `CMD-D1`'s whole argument evaporates.

Items 1 and 2 are the price of the decision. They are not follow-ups.
