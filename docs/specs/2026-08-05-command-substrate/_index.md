# Command Substrate — feature #2

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

## Deliberately NOT decided

**OVERRIDE or CONTRIBUTION** when feature B touches feature A's command
(extensibility §8.4) — Skyrim's last-loaded-wins is whole-record replacement and
its cost is the compatibility-patch economy every modded install pays; the actor
hub's fold is additive and refuses that. A synthesis is offered and deliberately
NOT sealed: definition overrides, precondition/effect lists add.

The registry's host service · the wire shape of an offer · **who owns inventory**
— an item is `External` from the island's view, so something outside must own it,
and today nothing does · multi-subject commands · parameter domains beyond
`Enumerated` · an order queue.
