# Command Substrate — feature #2

> # ⛔ CLOSED 2026-08-06 — FOLDED INTO THE 2026-08-02 ROUND
>
> Every surviving item now has an **08-02 id** and the id is where the work continues:
> `CMD-11` the offer registry · `CMD-12` the keyed-MAC `offer_id` · `CMD-13` horizontal
> composition · `CMD-10` absorbed the N+1 test · `O-CI-23`/`O-CI-24`/`O-CI-25` carry the three
> questions the conflict-resolution proposal left open. See
> [`2026-08-05-reconciliation.md`](2026-08-05-reconciliation.md) §8b for the item-by-item mapping.
>
> **This folder is HISTORY. Do not build from it, do not cite it as current, and do not edit it to
> keep it alive** — an open question living only here is how it stops being asked.

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
> **RECONCILED 2026-08-05** — read [`2026-08-05-reconciliation.md`](2026-08-05-reconciliation.md)
> **FIRST.** It adjudicates every claim here against the prior rounds: most of this
> folder is duplicate, the 🔴 BLOCKER is WITHDRAWN, `CMD-D1`'s seal is VOID, and five
> items survive. The prior round's own run state records that the PO **declined to seal**
> `CMD-1`..`CMD-6` and **directed a round of prior art** — which is, accidentally, what
> this round performed, blind to the round that asked for it.
>
> **Nothing here is authoritative on its own.**
> Individual findings may survive; the framing ("feature #2", "nothing implements
> this", the blocker, the decision ids) does not.



**Round:** 2026-08-05 · **Status:** DESIGN, unreviewed · **nothing implements this**
**Feature #1 was** [the actor hub](../2026-08-02-actor-hub/_index.md) — built, sealed.

> **A command is not a method on an actor. It is a declared capability that some
> entity OFFERS, which some actor may SPEND its turn to invoke.**
> Provider, subject and definition are three different nouns, and the whole design
> is refusing to collapse them.

Where the actor hub answered *"what does an actor HAVE"* by making quantities
declared rather than named, this answers *"what can be DONE"* the same way: verbs
are declared by whatever provides them, and the engine never learns their names.

---

## The contracts

| file | owns |
|---|---|
| [`2026-08-05-command-substrate.md`](2026-08-05-command-substrate.md) | the model: Phase 0 refusals · the three layers · provider ≠ subject · the registry · parameter domains · the entitlement stage · offer-as-hint · declared preconditions · assumptions · what is not decided · §11 the research |
| [`2026-08-05-extensibility.md`](2026-08-05-extensibility.md) | the N+1 test · the five coupling points · **why `Domain::Payload` is the god class** · four candidates evaluated · **`CMD-D1` — the payload is DATA, sealed** · §8 three IDEAS taken from long-lived data-driven plugin formats (not a port), and **the composition hole they expose** |
| [`2026-08-05-resolutions.md`](2026-08-05-resolutions.md) | `CMD-D2`..`CMD-D7` — six open questions closed, each because a sealed decision forces the answer · and 🔴 **the BLOCKER found while closing them: `LinkExists` stands on nothing** |

---

## The three things a reviewer should attack first

1. **`offer_id` must be BOUND, not merely unguessable** (substrate §5). An offer id
   that is only hard to guess is a bearer token: if it leaks, it is authority. The
   design says it must be re-derived from `(offer_id, claimed subject, producer)`
   rather than looked up in a trusted table — that is the security claim of the
   whole feature and the easiest thing to get wrong in implementation.
2. **`CMD-D1` accepts a real cost and its mitigations are unbuilt** (extensibility
   §7.3). The payload is now data, so the compiler no longer catches an unhandled
   command and an interpreter has more divergence surface than a `match`. Two
   things must ship WITH the first command, not after: the declaration↔resolution
   gate in both directions, and a determinism re-proof against the interpreter.
3. **Nobody has measured offer minting** (substrate §8.6). Enumerating parameter
   domains for every actor every tick may not fit the tick budget. If it does not,
   offers go lazy — a change of delivery, not of model, but it should be measured
   before it is assumed.

## What was ALREADY WRONG and got corrected by research

Recorded because the corrections are more informative than the conclusions
(substrate §11):

- **Not every command is driver-invoked.** The first draft assumed every command
  appears in an offer set. WoW items carry up to five spell references with
  triggers — on-use, on-equip, periodic — and the latter two are never offered to
  anyone. Trigger kind belongs to the Definition.
- **The escape hatch was worse than Skyrim's.** The draft said a fifth precondition
  relation kind requires an engine change. Skyrim's answer is better: project the
  missing condition into a variable an effect writes, and test the variable. The
  closed alphabet gains one member instead of growing forever.
- **Confirmed, not invented:** offer-as-hint with the guarantee at step time is what
  Unreal's GAS does — client predicts, server re-runs the same activation, rejection
  rolls back every predicted side effect.

## SEALED this round

**`CMD-D1` — the payload is DATA.** *A compiled payload enum and a manifest-defined
skill are mutually exclusive; we already chose the manifest.* `Domain::Payload`
becomes `Invocation { command_id, bindings }`. The payload TYPE belongs to the
substrate; what a command's BINDINGS MEAN belongs to the feature that declared it.
`CombatPayload` is therefore **combat's** to keep, decode or delete — in combat's
own round. The substrate has no opinion and must not acquire one.

**`CMD-D2` — a collision is a BUILD ERROR; an amendment is ADDITIVE.** Two bundles
claiming one command id fails the ruleset build. A feature may ADD preconditions and
effects to a command it does not own; it may never redefine or weaken one. **We get
an answer nobody else gets because we pre-compose:** a system composing at launch
must produce something and so must pick a silent winner — a build can simply fail.

**`CMD-D3` — the registry runs in commit-service.** Forced: offers need live island
state, and `game-server` holds no authority (`CWC-A1`) while `world-service` holds
only derived reads. Computation and delivery stay separate; the lens stays a lens.

**`CMD-D4` — `offer_id` is a keyed MAC over `(ruleset_digest, reality, tick,
subject, provider, command, param-domains)`.** Entitlement recomputes and compares.
Stateless, expires for free, and names which field was tampered with.

**`CMD-D5` — no order queue in the substrate.** Offers expire per tick and a queued
command must be re-validated anyway, so queuing belongs to the driver.

**`CMD-D6` — parameter domains stay `Enumerated`-only**, admitting a new kind only
when a real command needs it AND the engine clamps it.

**`CMD-D7` — multi-subject commands stay out**, because a two-party act needs
CONSENT, and consent is a negotiation protocol rather than a command.

## 🔴 BLOCKER — ahead of any implementation

**`LinkExists` stands on nothing.** The contract's precondition alphabet includes
*"the subject holds the provider"*, and the design's own worked example — *consume
the teleport scroll you are holding* — is that relation and nothing else.

Measured 2026-08-05: **no holder graph exists anywhere.** No containment, no
inventory, no entity-to-entity holding relation in `crates/`, `services/`, or the
per-reality schema. The only `holder` in the codebase is the channel writer lease —
an unrelated concept sharing a word.

*"Who owns inventory"* was filed as a deferred side question. It is a
**prerequisite**: one of five precondition kinds is unimplementable, and the
substrate cannot express its own worked example until something owns that graph.
It cannot be the island — an item leaving an actor's hands is `External` by
`sim-core`'s own definition — so it lives outside, and today there is no outside.

## Deliberately NOT decided

**The wire shape of an offer**, and only that. Designing a wire format with zero
declared commands is the declared-general-with-one-instance trap this repo hit four
times in a single day. The first real command decides it.
