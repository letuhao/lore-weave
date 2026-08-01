# 07 — The Lore Bible is an exhaustive sweep, not a search

> *We do not need to worry much about scale, because the problem was **find and load** from the start.
> And "find" is an **exhaustive sweep over a glossary list the book itself produced**. A lore bible
> cannot be built without that assistant. **Reading a chapter's raw data is wrong for this particular
> problem.*** — PO, 2026-08-01

**This document was rewritten.** Its first draft reached the right destination — build from the derived
layers, not the corpus — by the wrong road: it argued from **cost**, and framed corpus-reading as
something that stops working at three thousand chapters. That is not the reason. Corpus-reading is
wrong at **one hundred** chapters too, and the correction changes what gets built.

---

## 1. Why the chapter is the wrong unit

An entity's description is **scattered**. 乾坤圈 appears in chapter 12, again in 14, again in 34, and
what it *is* is the union of those appearances. A chapter is a **time slice**; it hands you fragments,
in narrative order, mixed with everything else happening in that scene.

The extraction pipeline already gathered those fragments — that is its whole job — and the result is
sitting in the glossary, alias-resolved, attributed and chapter-linked. Going back to raw chapters is
**redoing solved work, worse**, and the *"read the book"* framing hides that behind a cost argument.

> **`BTG-A18`** *(replaces the first draft's version).* **The chapter is the wrong unit; the entity is
> the unit.** The Lore Bible is built from the derived layers not because the corpus is *big* but
> because the corpus is *the wrong shape* — chronological, fragmented, and already processed into the
> right shape by a pipeline that exists. The corpus remains the **court of appeal**: touched to cite a
> claim, which is a pinpoint read.
>
> The hard prerequisite follows and is not negotiable: **a book with no glossary and no KG cannot have
> a bible built.** That assistant is not an accelerator, it is the subject matter.

## 2. "Find" is a SWEEP, and that is a different computation from a SEARCH

This is the correction that matters most, because the two have different completion semantics:

| | **search / RAG** | **exhaustive sweep** |
|---|---|---|
| input | a question | a **list** |
| output | passages that match | a decision **per element** |
| recall | unknown | **100% by construction** |
| "did we miss something?" | unanswerable | **countable** |
| failure mode | you never learn what you did not ask | you run out of budget, visibly |

The Lore Bible task, stated exactly:

```
for every entity the book produced:
      what is it, in the world's terms?      → lore
      and does the game need anything of it? → a demand on the design layer
```

> **`BTG-A21`.** **The bible's spine is an enumeration over a closed list, not a retrieval.** The list
> is the glossary — a list **the book itself produced**, which is why it is the right denominator and
> not an arbitrary one. Coverage becomes a fact rather than a hope: on the world currently on the
> stack, `5,431` entities · `5,412` with a description · `5,109` carrying attributes · `4,943`
> chapter-linked. Five thousand four hundred and thirty-one decisions, and a progress number that means
> something.

This is also the answer to a question left open one tier down. `evidence_n` — the denominator that
`m < n` needs and that retrieved spans could never supply — **is defined against the glossary.** It was
never a property of the corpus. It is the size of the list.

## 3. What this demotes: similarity search

The retrieval measured in [`12_operations_and_build.md` Part F](../LLM_MMO_RPG/40_progression_planner/12_operations_and_build.md)
— derived queries at the noise floor, model-written queries recovering ~0.09, encyclopaedic text
out-scoring narrative — is all still true, and all of it was measuring **the wrong instrument for this
job**. Those findings describe how well a *search* performs. The spine is not a search.

Retrieval keeps two real jobs, both supporting:

* **Citation.** A claim that matters must be traceable to a span — anchor → `locate()` → sentence,
  which structurally refuses a quote that is not there.
* **Contradiction hunting.** Foreclosures ([`04_fidelity.md`](04_fidelity.md) §2) are one sentence in
  one chapter and no sweep over entities will surface them; that genuinely is a search problem, and it
  is the one place `BTG-A8`'s signal has to come from.

> **`BTG-A22`.** Retrieval quality bounds the **evidence**, not the **coverage**. Confusing the two is
> how a pipeline ends up tuning a ranker to fix a completeness problem — which is what the first draft
> of this folder was set up to do, and what the Part F measurement was aimed at.

## 4. The other half: what the sweep cannot produce

A sweep covers everything the book *has*. A game needs things the book never mentioned — common item
families, mob archetypes, quest templates, the third of five realms nobody wrote down. The PO's
original phrase for the task was *find and load **plus brainstorming what is missing***, and the second
half is a different bounded problem:

```
  SWEEP      bounded by the GLOSSARY            → what this world HAS
  INVENTION  bounded by DOWNSTREAM DEMAND       → what this GAME needs
```

Both halves are **bounded and countable**, which is the real reason scale is not the problem. The
second bound is the gameplay design families and the slots they feed
([`03_two_jobs.md`](03_two_jobs.md) §4d) — a demand channel of exactly the shape `EPL-A8` already runs
one tier down, where an unanswerable question is a row, not a silence.

## 5. Which swept facts are LORE, and which are events

Sweeping produces 5,431 entity decisions; a bible has perhaps 200 sections. The reduction principle:

> **`BTG-A19`.** **A Lore Bible records the world's INVARIANTS; the book records its INSTANCES.**
> *"Cultivators break through realms"* is lore. *"In ch412 Zhang Wei broke through"* is an event — and
> it is **evidence for** the lore statement, not a competitor to it.

And it is computable, because the derived layer is **typed**: `kg_edge_types` declares 49 edge types
with `from_kinds`/`to_kinds`, directed, symmetric, cardinality — `MASTER_OF`, `DISCIPLE_OF`,
`DAO_COMPANION_OF`, `RIVAL_OF`.

| signal | reading |
|---|---|
| an edge type fires 812× over 40 subjects → 9 objects | a **system** |
| an edge fires once | an **event** |
| an attribute key appears on 300 entities of one kind | a **property of the kind** |
| an attribute appears on one entity | that entity's **detail** |

The sharpest form, and the reason this matters:

> If those 812 `BREAKS_THROUGH_TO` edges resolve to **9 distinct objects** inducing a consistent order
> across 40 subjects, **the realm ladder has been recovered from the edges — though no chapter ever
> lists the realms in order.**

That is exactly what the contract generator was asking a model to invent, sitting in data the platform
already produces, arriving with a count, an order and citations.

## 6. Describing the shape, so a model can name the systems

The model never sees 5,431 entities at once. It sees an aggregate — and the last row is worth as much
as the rest:

```
kinds        character 4,102 · location 611 · sect 88 · technique 1,340 · treasure 402
edge types   fired 41 of 49 declared
             MASTER_OF          2,904×   1,850 subj →   612 obj   hierarchy, depth ≤ 6
             BREAKS_THROUGH_TO    812×      40 subj →     9 obj   TOTAL ORDER over 9
             MEMBER_OF          3,180×   3,001 subj →    88 obj   partition, 12 orphans
unused       8 declared edge types NEVER fired  ← what this world does not have
```

An edge type the genre schema declares and this book never uses is a **statement about the world**. A
novel that never fires `RULES_OVER` has no sovereign politics, and a designer needs that before
inventing a court.

## 7. Contradiction is the human's decision, and the KG already holds it

A long serial contradicts itself: realm names drift, a character dies twice, currency inflates. A bible
must **decide** which version is canon, and no automated rule should.

The KG holds the contradictions already — a `multi_active` edge where cardinality says one, two values
on a single-valued key, an order violation among the breakthrough edges.

> **`BTG-A20`.** Contradiction surfacing is the **highest-value human-in-the-loop moment in the tier**
> and the cheapest to build, because the data is already there. It is also the one place automated
> resolution actively harms: silently taking the majority version writes a canon nobody agreed to and
> gives it the confidence of a fact.

## 8. Two mechanisms reused rather than invented

* **The bible is world-state at a CUTOFF.** Over a long book the world changes; a bible that flattens
  it describes a world that existed at no moment. `spoiler_window.resolve_before_order` and
  `before_chapter_id` already exist, fail-closed. A game set at chapter 1 needs a different bible than
  one set at chapter 2,900, and the cutoff is an early authoring decision.
* **Attention is ordered by blocking power** — the same computation the clingo register performs for
  open slots, one tier up. 5,431 decisions is not a queue anyone drains evenly; the order is the
  product.

## 9. When is it done?

Now there are two answers where there used to be none, and they are floor and ceiling:

* **Floor — the sweep is complete.** Every glossary entity has been decided or explicitly deferred.
  Countable, provable, and a real progress number.
* **Ceiling — downstream demand is satisfied.** Every question the gameplay design layer asks has an
  answer. Unanswerable questions are rows, the same shape as `EPL-A8`'s cross-module demand.

The floor is what makes the work tractable; the ceiling is what makes it sufficient. Neither alone is
*done*, and the first draft of this document had only the second.

## 10. What section 8 does not fix

1. **The bible inherits the glossary's errors.** Aliases, mis-splits, wrong kinds — the sweep visits
   exactly the list it is given, so a bad merge upstream produces a coherent, traceable, well-measured
   decision **about the wrong entity**.

   The first draft summarised this as *"coverage is provable; correctness is not"*, which was a category
   error: it used *correctness* to mean fidelity to a truth about the world, and for an **authored**
   world no such truth exists. What is provable is **traceability** — every fact reduces to a decision,
   every decision to a citation or a marked invention — and what varies is **fidelity**, which is a
   chosen position rather than an accuracy. See [`08_measuring_a_creative_result.md`](08_measuring_a_creative_result.md);
   the residue that survives is narrower and truer: **the profile measures the pipeline, not its
   inputs.**
2. **Frequency finds systems, not keystones.** A single `FOUNDED_BY` edge defines a sect. The aggregate
   in §6 would rank it as noise. Centrality is the obvious complement and is unmeasured.
3. **A sweep is only as bounded as its list is closed.** The glossary grows when new chapters are
   extracted, so the denominator moves. That is a versioning problem — the same one the cutoff in §8
   answers — and it means a "100% swept" claim is always *as of* a chapter and a glossary version.
