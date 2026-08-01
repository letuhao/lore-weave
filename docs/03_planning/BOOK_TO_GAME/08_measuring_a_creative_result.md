# 08 — Measuring a result that has no right answer

> *Correctness IS proven — by the deterministic data built from the lore bible, and the bible is built
> from glossary / KG / wiki. This is a problem with no absolute correctness; it is a **creative**
> problem. How correct depends on how closely we want to stay to the original lore. And it needs a
> **qualitative measurement function**.* — PO, 2026-08-01

This document exists because [`07_lore_bible.md`](07_lore_bible.md) §10 got it wrong. It said
*"coverage is provable; correctness is not"* — which used "correctness" to mean **fidelity to a truth
about the world**. For an authored world there is no such truth. There is no correct number of realms
for a world that never named one; the answer is *decided*, and a decision cannot be wrong in the way a
measurement can.

Three different things were being run together. Separating them is the whole document.

---

## 1. What IS proven, and it is not truth

```
glossary / KG / wiki   →   LORE BIBLE   →   deterministic data
     evidence               authored           compiled
```

The second arrow is **deterministic by construction** ([`03_two_jobs.md`](03_two_jobs.md)): the
compiler invents nothing, the manifest pins the bible's digest, and every value in it came from a
decision recorded upstream. That arrow's correctness is provable, and it is worth naming precisely
because it is easy to over- and under-claim.

> **`BTG-A23`.** **Determinism does not make the content right. It makes the content ATTRIBUTABLE.**
> Every game fact reduces to a bible decision; every bible decision reduces to a cited entity or a
> **marked invention**. So there is always an answer to *"why is it like this?"*, and the answer is a
> human decision someone can go and change — never a model's whim, and never an unexplainable artefact
> of a pipeline.
>
> The property this buys is **localisation of disagreement**: if the game is wrong, the bible is wrong,
> and the bible says who decided what and on what basis. That is the only kind of correctness a
> creative pipeline can have, and it is worth more than a truth claim would be.

The one part of this that is genuinely binary, and therefore a **HARD** check: *can every fact name its
origin?* A fact with no provenance, no citation and no invention marker is a defect of **form**, not of
content, and form is checkable.

## 2. What is NOT correctness at all: fidelity

*"How closely does this follow the source"* is a **chosen position**, not an accuracy
([`04_fidelity.md`](04_fidelity.md)). A game that invents 80% of its power system is not 80% wrong; it
is *inspired* rather than a retelling, and that was somebody's decision.

Which means the single most consequential thing in this whole document:

> **`BTG-A25`.** **No measure here has a fixed threshold. Every threshold comes from the declared
> position.** 30% groundedness is excellent for *inspired* and a failure for *retelling*. A rubric with
> absolute cut-offs would be measuring adherence to a standard nobody chose — and would penalise the
> case the tier exists for, a source with no system at all, where near-total invention is the correct
> outcome.

So the useful question is never *how good is this*. It is **how far is this from what you said you
wanted** — and that is checkable, because the human wrote the target down.

## 3. What the qualitative measure actually is: a profile, not a score

The project already argued this, in code, before this document existed. From
`app/gamegen/census.py`:

> *It is deliberately **not** a quality score. There is no single number for "is this a good cultivation
> system", and inventing one would be the shape this pipeline refuses everywhere else: a figure that
> looks like evidence and answers a question nobody asked.*

> **`BTG-A24`.** A creative result gets a **census, not a score**: several numbers, each answering a
> *different* question, none of them averageable. Averaging them would reproduce a defect this project
> has already recorded — `MEM-A7`, where seven categorical criteria and one failure scored 0.857
> against a copied 0.85 threshold, producing a gate that could not fail.

The profile, with its source:

| measure | the question it answers | where it comes from | kind |
|---|---|---|---|
| **traceability** | can every fact name its origin? | provenance + evidence present | **HARD** — the only binary one |
| **sweep coverage** | did we visit everything the book produced? | decided ÷ glossary entities (`07` §2) | ratio · **floor** |
| **groundedness** | of what we decided, how much does the source support? | `CITED ÷ (CITED + PROPOSED)` — `census.py` computes exactly this | ratio · **target set by charter** |
| **declaration conformance** | does the result match the fidelity we declared? | measured provenance mix vs charter position, per axis | ratio · **the load-bearing one** |
| **internal consistency** | does the bible contradict itself? | closed sets referenced consistently; ladders are orders; cardinalities respected | count of violations |
| **register conformance** | does the invented content belong to *this* world? | the `MEM-A6` check — vocabulary from another tradition | count of violations |
| **downstream sufficiency** | can the design layer answer its questions? | unanswered demand rows | count · **ceiling** |

One HARD binary and six soft numbers is the same split the contract generator's criteria already use
(`MEM-A7`), and for the same reason: the things that are about **form** can fail outright, and the
things that are about **content** can only be reported.

## 4. Why `declaration conformance` is the load-bearing one

Every other measure describes the result. This one compares the result **to the human's own standard**,
which makes it the only one that can fail *without anyone arguing about taste*:

> *You declared `power: retelling`. Measured: 2 of 11 power facts are `CITED`, 9 are `PROPOSED`, and 4
> of those 9 name no departure. Either the position is wrong or the work is — and both are yours to
> change.*

That is a real failure with no aesthetic judgement in it. It is also the thing that catches the drift
this tier is most prone to: a charter written optimistically at the start, and an authoring process
that quietly invents its way past it because inventing is easier than citing.

**And it must not become a gate that forbids invention** — the mistake
[`04_fidelity.md`](04_fidelity.md) was corrected for. It reports a distance. The human closes it by
authoring more citations *or* by moving the position; both are legitimate, and the tool must not have
an opinion about which.

## 5. What this does NOT measure, and cannot

Stated plainly so nobody looks for it later:

1. **Whether the game is good.** No number here touches fun, pacing, or whether a player would care.
   That is playtesting, and no static analysis substitutes for it.
2. **Whether an invention is a *good* invention.** Register conformance catches western rarity tiers in
   a Ming setting; it cannot tell a dull realm ladder from an inspired one. That judgement is the
   author's and stays the author's.
3. **Whether the glossary was right.** The sweep visits the list it is given. A bad merge upstream
   produces a coherent, traceable, well-measured decision **about the wrong entity** — every number in
   §3 stays green. This is the honest residue of `07` §10, restated correctly: it is not that
   correctness is unprovable, it is that **the profile measures the pipeline, not its inputs.**

## 6. Where the numbers come from, and what is missing

Most of the profile is already computable from things that exist:

* `census.py` — completeness and groundedness, already built, already tested, already argued
* the criteria machinery — internal consistency, the HARD/SCORED split
* `MEM-A6`'s check — register conformance
* the sweep — coverage, once the sweep exists
* the demand channel — sufficiency, the `EPL-A8` shape one tier up

**Missing, and it is the one genuinely new piece:** *declaration conformance* has nothing today,
because the charter has nothing today. It needs the charter to be machine-readable, which is
[`06_poc_plan.md`](06_poc_plan.md) POC-D — and POC-D's design should be read again with this document
in hand, because §4 sharpens what it must report: not *pass/fail*, but **a distance and both ways to
close it**.
