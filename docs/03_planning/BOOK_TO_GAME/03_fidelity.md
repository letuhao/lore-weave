# 03 — Fidelity: how close to the source, and how a human decides

> *A game is created from an original story, but how closely it can follow that story is a question
> that has to be answered — and the human should be the one to answer it. How can they?*

This is the tier's reason to exist. Everything else is machinery for making this decision **informed**
and then **enforceable**.

---

## 1. Fidelity is not a number, and it is not one decision

"How faithful is this adaptation" has no single answer, because the same game is routinely faithful in
one respect and free in another. A retelling where you play Nezha needs the canonical cast to be a
**closed** set and cares little about geography. A sandbox in the same setting needs generative
rosters and a coherent map, and would be ruined by a fixed timeline.

> **`BTG-A6`.** Fidelity is **per-axis**, and a single slider is worse than none: it forces the human
> to average away exactly the distinctions the adaptation lives on, and it produces a number nobody can
> act on.

**The axes are not invented for this document.** They are the pool's slots, grouped by what they
constrain — which keeps the list grounded and keeps it growing with the contract instead of drifting
beside it:

| axis | slots it groups (today) | the question it answers |
|---|---|---|
| **cast** | `actor_*`, factions | who exists |
| **artifacts** | `item_archetype`, `instrument_tag`, `equip_slot` | what things are and what they do |
| **power** | `progression_kind`, `progression_stage` | how strength works and what gates it |
| **geography** | place slots (unregistered) | where, and what connects |
| **chronology** | — | when, and in what order |
| **outcome** | — | what is allowed to end differently |
| **register** | cross-cutting | how it is named and worded |

Two of those have no slots yet. **That is information, not an omission**: an axis with no slots is an
axis the game does not yet condition on, and inviting a fidelity decision about it would be asking the
human to rule on something with no consequence.

## 2. The distinction everything turns on: SILENT is not FORECLOSED

The corpus stands in one of three relations to any question:

| | canon | inventing an answer |
|---|---|---|
| **STATES** it | has an answer | **contradicts** canon |
| **SILENT** on it | has no answer | leaves canon untouched |
| **FORECLOSES** it | says *there is no answer* | **contradicts** canon |

The third is easy to miss and is the one that matters most. 封神演義 does not merely fail to rank its
treasures — it says out loud that they were never ranked: **寶各有用，未嘗較其次第** (*each treasure has
its use; their order was never compared*). The reference wiki repeats it: **書中未嘗分品第**.

A pipeline that treats *"the book doesn't say"* as a licence to invent will happily bolt a nine-grade
ladder onto a world that explicitly refused one — and it will report high confidence, because it found
no contradiction to a statement it never looked for.

> **`BTG-A7`.** **A stated foreclosure is canon.** High fidelity plus a foreclosure does not mean
> *invent carefully*; it means **the game may not have that mechanism at all** and must find another
> way to do the job. This is the sharpest tooth in the existing fixture (`fixture_teeth.json`, `I2`),
> and it was designed before this tier was conceived — which is a reason to trust it and a reason it
> should move here.

Detecting foreclosure is a real retrieval task with a real failure mode: the evidence for *"the book
says there is no ranking"* is a **single sentence in one chapter**, and a similarity search for
"grade" or "rank" returns the thousand places ranks are *not* discussed. It has to be looked for
deliberately.

## 3. What a fidelity setting actually is

Given the three relations above, a fidelity position on an axis is a **policy over provenance** — and
the vocabulary already exists in the game tier (`MEM-A5`'s six provenances, `ENR-A4`'s six-rung
enrichment ladder). Nothing new is invented here; the charter just says which rungs are legal where.

| position | STATES | SILENT | FORECLOSES |
|---|---|---|---|
| **canon-bound** | must use it | leave the gap; the game does without | the mechanism is **refused** |
| **canon-anchored** | must use it | `DERIVED` only — extend by rule, from what is stated | refused |
| **canon-inspired** | may depart, must record what it departed from | `PROPOSED` allowed | may invent, but the contradiction is **recorded and shown** |
| **setting-only** | free | free | free |

> **`BTG-A8`.** A fidelity charter is machine-checkable, because every fact in the game concept already
> has to carry a provenance for other reasons. *"canon-bound on cast"* becomes: **no member of a cast
> slot may have provenance `PROPOSED`** — a criterion of exactly the shape the contract generator's
> per-operation criteria already are (`BLD-A1`), evaluated by the same machinery. The charter is not a
> preference recorded in prose; it is a set of checks that can fail.

## 4. How the human decides — the part the question was really asking

A human cannot answer *"how canon-bound should the power system be?"* in the abstract, and asking them
to is how a settings screen becomes a source of regret. They can answer it when shown **what each
position costs, on this corpus**.

So the tier owes them, per axis, four computed things:

**① Coverage — what canon actually supplies.** Of the slots on this axis, how many can be filled from
`CITED` evidence alone? This is the provenance census (`app/gamegen/census.py`) projected per axis, and
it already computes exactly this shape: *chosen vs defaulted*, *book-grounded vs model-proposed*.

**② Foreclosures — where canon says no.** Named, with the sentence, with its citation. This is the
single highest-value thing the tier can show, and today nothing looks for it.

**③ The cost of each position — stated as work and as loss.**

> *`power`, **canon-bound**: 2 of 5 slots fillable from the text. The book names no realm count and
> **forecloses treasure ranking** (ch65). You get a progression system with 2 gates and no item tier —
> playable, thin. **canon-anchored**: 4 of 5, by deriving stage boundaries from the breakthrough scenes
> in ch12/ch47. **canon-inspired**: 5 of 5, and you will be contradicting ch65 in one place, shown
> below.*

**④ What the reference game would do.** The comparison a human actually reasons with — *"a game of this
kind usually has 9 tiers; this book supports 2"* — is what makes the gap legible. It arrives as
`PROJECTED`, never as fact (`BTG-A5`), and it is a **suggestion the human accepts or refuses**, which
is the point: the decision stays theirs and now has something to be a decision *about*.

> **`BTG-A9`.** The decision is not elicited by a question; it is elicited by a **consequence**. The
> tier's job is to compute the consequence before the question is asked. This is the same finding the
> game tier reached from the other direction (`ASK-A2`: never ask for a number, ask for the structure
> that determines it, then compute the number and show the derivation).

## 5. The decision is revisable, and revision must cost something visible

A fidelity charter will be changed — after playtesting, after the human sees what canon-bound actually
produces. That must not silently leave a pool full of members authored under the old policy.

The mechanism already exists one tier down: the game concept is **content-addressed**, everything
derived from it **pins the digest**, and changing the charter changes the digest. Every downstream
artifact then declares itself stale by comparison rather than by anyone remembering. The game tier's
freeze does this for the pool; this tier needs the same discipline for the concept, and it is the same
code.

## 6. Open questions this document does not settle

1. **Who owns the axis list?** §1 derives it from the pool's slots, which makes it grow with the
   contract. But two axes (chronology, outcome) have no slots and may never — they may be constraints
   on *play*, not on the contract, in which case they belong to a different document and the tier
   should say so rather than carry them.
2. **Is foreclosure detectable at acceptable cost?** §2 says a foreclosure is one sentence in one
   chapter and that similarity search will not find it. An explicit *"does the corpus deny this?"* pass
   over every open question is a real expense and it is unmeasured. §[`05`](05_poc_plan.md) makes it
   the first thing measured, because if it cannot be found reliably, `BTG-A7` is unenforceable and the
   whole charter degrades to *silent = invent*.
3. **Does a fidelity position belong to the world, the game, or the run?** Two games from one novel is
   the obvious case, and it implies the charter is not world-level. Left open deliberately.
