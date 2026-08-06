# Command Hub — the scope contract

**Status:** design contract — **SEALED by the PO 2026-08-06** · **Date:** 2026-08-06
**Companions:** [structure](2026-08-02-command-interaction-structure.md) ·
[dataflow](2026-08-02-command-interaction-dataflow.md) *(the derivation record — how each line was
reached)* · [RUN-STATE](../plans/2026-08-06-game-tier-build-RUN-STATE.md)

> This file states **what is in and what is out**, and nothing else.
>
> ⚠️ **One line of §4 is struck through pending the PO** — see `SEAM-1` there. The
> ordinal spaces this contract's rows address are counted in
> [ordinal-spaces](2026-08-06-ordinal-spaces.md), which is proposed, not sealed. Every argument that produced a
> line here lives in the two 08-02 documents. Written after the actor hub's contract, in the same
> shape, because that shape is what stopped that round from sprawling.

---

## 1. The architecture

> **Verbs are declared by FEATURES. The command substrate is the HUB that resolves them —
> and it knows nothing about what any of them MEAN.**

This is the actor hub's sentence one level up, and deliberately so. The hub folds quantity
contributions without knowing what a quantity means; the substrate resolves verb declarations
without knowing what a verb means. **If the two sentences stop being the same sentence, one of the
two designs has drifted.**

**Command substrate is feature #2 of roughly a thousand. Its job is to make feature #3 cheap — not
to pre-empt it.**

## 2. The scope test

> **THE DUMB DRIVER TEST.**
> **Strip away every chooser.** Leave a driver that picks uniformly at random, or a human clicking a
> button, with no model, no weights and no preferences anywhere.
> **What does the engine still need in order to resolve the action?**

| **still needed — the SUBSTRATE's** | **falls away — a FEATURE's** |
|---|---|
| which verb this is, and its ordinal | how *desirable* the verb is (`considerations`) |
| who fills which role | what it is *strong against* (`attack_class`, the effectiveness matrix) |
| whether it is legal (`requires`) | what a *coward* weighs differently from a hero |
| what it spends | how a planner *searches* over verbs |
| what it changes (`effects`) | the *words* shown for it |
| whether it succeeded (the roll) | which bundles a ruleset is *composed from* |
| the refusal, as a committed fact | what a verb *means* in the fiction |
| that something must be SHOWN (the cue ordinal) | |
| what may be done at all (the offer) | |

**Two things the test decides that the round kept re-opening:**

- **The chooser is a FEATURE, not a column.** `PO-5` asked for the decision layer — AI weights,
  cost/reward/penalty, rock-paper-scissors — and it is real. It is **not** the substrate's. The
  substrate owes it a **declared seam**, exactly as `D-9` owes the trigger mechanism one, and owes
  it nothing else. This is also what `A-7` was reporting from the other end: `/sleep` leaves four of
  six proposed columns inert, and a row whose normal state is mostly inert is the *"29 accreted
  fields are FOUR kinds"* signal.
- **The substrate RESOLVES actions; it does not BUILD rulesets.** Composition — match keys, merge
  strategies, `conflict_resolutions`, a build that fails on an unresolved collision (`CMD-13`) —
  happens **before** any action exists, to produce the table the substrate then reads. It belongs to
  the ruleset builder. That is why it kept feeling out of place: it is a different layer, not a
  hard part of this one.

**What the test does NOT settle:** a datum that is *mechanically* load-bearing and *feature-shaped*
in origin — an effectiveness multiplier changes what happened, so it cannot simply be evicted. The
answer is the hub's own: **it arrives as a contribution the substrate folds, and the substrate never
learns its name.** The declaring feature says what it means.

## 3. What the substrate holds — five things

```
1  VERB IDENTITY   a declared row with an ordinal — append-only, never reused   (CMD-1)
2  THE PIPELINE    engine-closed stages; what happens AT each stage is declared (CMD-2)
3  LEGALITY + COST what must hold, and what is taken — evaluated, never scored
4  EFFECT          rows from a closed primitive set: one primitive per BUILT DOOR (CMD-3)
5  THE OUTCOME     a committed fact either way — applied, or refused with a reason (CMD-5)
                   plus a cue ordinal, on a channel of its own                   (CMD-4)
```

**The closure rule on 4 is the load-bearing one, and it is currently the binding constraint:** a
primitive exists **iff the substrate already built the door it goes through**. Measured 2026-08-06,
**one door of seven is open** — `Delta`, built by the actor hub. `StatusPropose`, `EdgeMove`,
`LifecycleRequest`, `ClockAdvance`, `Materialise` and `Oracle` are prose. **The first verb is
therefore `Delta`-only, and that is a consequence of the rule rather than a compromise with it.**

## 4. The seam — the whole feature contract

A feature adds a verb by writing **rows**, never code (`D-27`). It declares:

- a **key** and the roles it needs
- **requirements** — from the closed relation set, over state the substrate can already read
- **spend** and **effects** — from the closed primitive set
- a **cue** ordinal
- ~~a **submitter class**~~ ✅ **STRUCK by the PO, 2026-08-06 — see `SEAM-1` below.**

> ✅ **`SEAM-1` · RESOLVED 2026-08-06. This line is struck; `CMD-10` governs.**
>
> **The reason the PO gave is stronger than seniority between two decisions, and
> it is now `AUTHOR-1`:** *the manifest author is not a developer, and usually
> produces the manifest with an LLM — so if it gets too complex they cannot do
> it.* Striking this field does not merely follow the later decision; it
> **removes a field the author would have had to get right, whose wrong value is
> an authorisation defect.**
>
> The original finding, kept because how it survived a seal is the useful part: §2's DUMB DRIVER table does not list a submitter class among the
> nine things the engine still needs, and `CMD-10`'s V4 table — cited by this
> same document — scores `submitter_class` + `may_submit_engine_verbs` **❌**
> with the reason *"the author supplies the verdict of the authorisation rule."*
>
> **The build followed `CMD-10`, not this line.**
> [`FORBIDDEN_VERB_KEYS`](../../crates/ruleset-core/src/classification/forbidden.rs)
> refuses both keys **by name, with the reason**, on the permissive parse — and
> that refusal IS `CMD-10`'s owed bite, discharged in `M2`.
>
> So a SEALED contract asks for a field the code refuses. It is struck through
> rather than deleted because **sealing is the PO's and so is unsealing**; this
> marker is the ask. The correct reading, if the PO agrees: a declared verb is
> submittable by any actor-driver, and engine-only payloads (`EndTurn`) are not
> declared verbs at all.
>
> **How it survived a seal:** the line was written before `CMD-10` existed, and
> `CMD-10` was folded in without re-reading the seam it changed. Same shape as
> `M1-D2`, sealed and then reversed by its own build — the fourth stale-claim
> catch of this run, and the first one inside a document carrying a seal.

**The substrate never branches on the verb's name.** Binding a declared name to an engine operation
is table-driven, not a `match` arm (`CMD-6`) — which is what `vocabulary.rs` gets wrong today, and
the narrowest high-leverage fix in the round.

## 5. Cost

Resolving a declared verb walks a table where the shipped code jumps to a compiled arm. **This is a
real cost and it buys the acceptance test in §6.**

> **A declared verb is not a slower `match`. It is a `match` an author can extend without a
> release.** Where that trade is *not* worth taking — an operation on the step path, per actor, per
> tick — it should not be a verb at all.

The compiler no longer catches an unhandled command, so two things ship **with** the first verb, not
after: the declaration↔resolution gate **in both directions**, and a determinism re-proof against
the interpreter.

## 6. The acceptance test

> **Adding a verb must touch ZERO files in command core.**

The same test the actor hub takes, and checkable for the same reason: a feature that cannot add a
field has nothing to touch.

**The honest bound: it holds UP TO THE DECLARED WIDTHS**, and the widths are not yet priced — the
verb ordinal space is `C-3`, and `AF-8` found `RefKindMask` unpriced and outside the six ordinal
spaces. Exceeding one is a **version bump, visible and costed**, not a silent failure.

## 7. Open — and deliberately not decided here

| | |
|---|---|
| how a chooser scores a legal verb | **a decision-layer feature**, through the seam §2 names |
| what any verb is strong against | **combat**, in combat's own round |
| what a verb is *called* in any language | **presentation**, off the cue ordinal |
| how a ruleset is composed from bundles | **the ruleset builder** (`CMD-13`, `O-CI-23`..`O-CI-25`) |
| the six doors that are prose | **the features that own them** — buildable, not blocked |
| the wire shape of an offer | **the first real command**, and not before it |

**And one that is open because it is genuinely undecided, not delegated:** `O-CI-16` counted **six**
types named across the 08-02 documents and never defined. §2's eviction takes **one** of them —
`InputKind` is `ConsiderationRow`'s input field, so it leaves with the chooser. **Five remain, and
all five are the substrate's own:** `ChanceSpec` (the roll), arity's home, a pair's `subject`, the
two-role `EffectRow`, and `RefKindMask`. Every `success` row in a real manifest rests on an invented
shape. **Nothing can be built against a name.**

> A boundary that shrinks a problem by one and reports it as five is doing its job. A boundary that
> shrinks it by one and still reports six has been drawn and then not applied — which is how this
> project's registers went stale four times this week.
