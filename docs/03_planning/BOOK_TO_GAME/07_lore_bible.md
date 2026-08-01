# 07 — Building a Lore Bible from a book nobody can read

The PO's question, and it is a scale question and a design question at once:

> *The book has thousands of chapters, tens of thousands of glossary entries, and an enormous KG. How
> can we build a Lore Bible?*

A 3,000-chapter web novel is 10–15M characters. Nothing reads it. Not a person, not a context window,
not affordably and not twice. Every approach that starts with *"first, read the book"* is dead before
it is costed.

But that is the wrong starting point, and the reason is in the numbers already on the stack.

---

## 1. The derived layers are not an obstacle. They are the asset.

| layer | what it holds | what it already did |
|---|---|---|
| `glossary_entities` (+ `entity_alias_map`) | the entities, **named, typed, deduplicated, alias-resolved** | the extraction |
| `entity_attribute_values` / `_value_items`, `entity_facts` | attributes per entity | the attribution |
| `chapter_entity_links` | entity ↔ chapter | **frequency, first appearance, co-occurrence** — for free |
| `kg_edge_types` | **49 declared edge types**, each with `from_kinds`/`to_kinds`, directed, symmetric, cardinality — `MASTER_OF`, `DISCIPLE_OF`, `DAO_COMPANION_OF`, `RIVAL_OF` | the relation **vocabulary**, and it is genre-aware |
| the graph itself (Neo4j) | the instantiated edges | the relations |

> **`BTG-A18`.** **The Lore Bible is built from the DERIVED layers, never from the corpus.** The book is
> the **court of appeal** — touched only to cite a claim, which is a pinpoint read — not the source.
> At a hundred chapters this is an optimisation; at three thousand it is the only thing that works, and
> designing as if the corpus were the input produces a system that runs exactly once, on a fixture.

This also means the bible has an honest **hard dependency**: a book with no glossary and no KG cannot
have one built. That is a prerequisite to state, not a limitation to route around — and it is why the
platform's existing extraction pipeline is upstream of this tier rather than replaced by it.

## 2. The operation is a TRANSPOSITION, not a summary

The book is ordered by **time**. The bible is ordered by **topic**. Summarising 3,000 chapters yields a
shorter story — still time-ordered, still about events — which is not a world description and cannot be
made into one by compressing harder.

```
  BOOK            ch.1 → ch.412 → ch.2900          ordered by WHEN
  KG              entity —edge→ entity             ordered by WHAT RELATES TO WHAT
  LORE BIBLE      cultivation · geography · …      ordered by TOPIC
```

The KG is the halfway house: it has already left chronology behind. Going from the KG to the bible is
the second half of a transposition whose first half the platform already performs.

## 3. The selection principle: invariants, not instances

A bible of 200 sections out of 30,000 entities is a ~150:1 compression, and compression needs a
principle. The one that works:

> **`BTG-A19`.** **A Lore Bible records the world's INVARIANTS; the book records its INSTANCES.**
> *"Cultivators break through realms, and a breakthrough requires a bottleneck to be broken"* is lore.
> *"In chapter 412, Zhang Wei broke through to Golden Core"* is an **event** — and it is *evidence for*
> the lore statement, not a competitor to it.

The value of that formulation is that it is **computable over the KG**, because an invariant is a
pattern with many instances:

| signal | reading |
|---|---|
| edge type `BREAKS_THROUGH_TO` fires 812 times over 40 distinct subjects | a **system** |
| edge `(Zhang Wei, KILLS, Li Si)` fires once | an **event** |
| an attribute key appears on 300 entities of one kind | a **property of that kind** |
| an attribute appears on one entity | that entity's **detail** |

And the strongest case, which is why this section matters most:

> If the 812 `BREAKS_THROUGH_TO` edges resolve to **9 distinct objects**, and those 9 induce a
> consistent partial order across 40 different subjects, then **the realm ladder has been recovered
> from the edges — even though no chapter ever lists the realms in order.**

That is precisely the thing the contract generator was asking a model to invent, sitting in data the
platform already produces. It arrives with a count, an order, and citations, which is exactly the shape
`evidence_n` was missing.

## 4. The cost strategy: describe the SHAPE, not the content

The model must never see 30,000 entities. It sees an **aggregate** — a few thousand tokens describing
15M characters:

```
kinds        character 4,102 · location 611 · sect 88 · technique 1,340 · treasure 402
edge types   fired 41 of 49 declared
             MASTER_OF          2,904×   1,850 subj →   612 obj    hierarchy, depth ≤ 6
             BREAKS_THROUGH_TO    812×      40 subj →     9 obj    TOTAL ORDER over 9
             MEMBER_OF          3,180×   3,001 subj →    88 obj    partition, 12 orphans
             LOVER_OF              47×                              sparse — incidental
unused       8 declared edge types never fired  ← what this world does NOT have
```

That last row is worth as much as the rest: **an edge type the genre schema declares and this book
never uses is a statement about the world.** A wuxia novel that never fires `RULES_OVER` has no
sovereign politics, and a designer needs to know that before inventing a court.

The model's job on that aggregate is to *name the systems and write the prose*, which is a job sized
for a context window. The counts, orders and citations come from SQL and the graph.

## 5. Contradiction is the human's decision, and the KG already holds it

A 3,000-chapter serial contradicts itself. Realm names drift, a character dies twice, currency
inflates, an author forgets. A bible must **decide** which version is canon, and no automated rule
should: that is authorship.

What the tier owes is the **surfacing**, ranked. The KG has the contradictions already — a
`multi_active` edge where cardinality says one, two attribute values on a single-valued key, an order
violation among the 812 breakthrough edges. Each becomes a decision presented with both sides and their
chapters.

> **`BTG-A20`.** Contradiction surfacing is the **highest-value human-in-the-loop moment in the tier**,
> and the cheapest to build, because the data is already there. It is also the one place where an
> automated resolution would be actively harmful: silently choosing the majority version writes a
> canon nobody agreed to and gives it the same confidence as a fact.

## 6. The bible describes the world AT A CUTOFF

Over 3,000 chapters the world changes: a sect is founded, a city falls, a currency is replaced. A bible
that flattens all of it describes a world that never existed at any moment.

A game set at chapter 1 needs a different bible than a game set at chapter 2,900 — and this is not a
new mechanism to build. `spoiler_window.resolve_before_order` and `before_chapter_id` already exist,
fail-closed, and are used by the reader product. The bible is a **world-state at a chapter cutoff**,
and the cutoff is a design decision the author makes early because it changes everything downstream.

## 7. Ordering the human's attention

200 sections is more review than anyone will do evenly, so the order matters more than the total. Rank
by **how much depends on the decision** — the same computation the contract generator's clingo register
performs for open slots, one tier up:

* a decision many other sections reference ranks first
* a contradiction blocking a systemic claim outranks one blocking a detail
* a section with no downstream demand can wait, and should say so rather than sit unread

## 8. What the section list is, and why it is a `CONFIRM`

Not derived from nothing, and not fixed forever. A **genre template** proposes the checklist —
cosmology · power system · geography · polities · economy · history · peoples · crafting · religion ·
language — and the aggregate confirms, prunes or extends it.

That is exactly the `CONFIRM` operation the game tier already built and measured: *a declared default,
kept or overridden with evidence.* Its virtue here is the same one it had there — **it makes absence
visible.** A power-system section that the aggregate cannot populate is not a missing section; it is
the finding that this world has no power system, which is the single most important thing a game
designer can learn early ([`04_fidelity.md`](04_fidelity.md) §1).

## 9. When is it done?

Not "when the world is fully described" — that has no end. The bible is sufficient when the **gameplay
design layer's questions can be answered**, which makes completeness *downstream-defined* and
measurable: an unanswerable question is a demand row against the bible, the same shape as `EPL-A8`'s
cross-module demand, one tier up.

## 10. What is honestly hard about this

1. **The bible inherits the KG's errors.** The KG is the *derived, fuzzy* layer by design
   (`CLAUDE.md` → two-layer pattern). A pattern over noisy edges is a confident-looking wrong
   invariant. Mitigation: **patterns propose, citations verify** — a systemic claim that matters must
   be traceable to spans, using the anchor→`locate()`→sentence machinery that already refuses a quote
   it cannot find.
2. **Entity resolution bounds everything.** 30,000 entities include aliases, translations and
   mis-splits. `entity_alias_map` exists; the bible's quality is capped by how well it was populated,
   and no amount of good design downstream repairs a bad merge upstream.
3. **The aggregate can mislead by omission.** An edge type that fires rarely may still be load-bearing —
   a single `FOUNDED_BY` edge defines a sect. Frequency finds *systems*; it does not find *keystones*,
   and something else has to (centrality is the obvious candidate and is unmeasured).
4. **This has never been run at scale.** Every number in this document is a shape, not a measurement.
   The largest book on the stack today is **100 chapters** and the glossary holds **5,431 entities** —
   one to two orders of magnitude below the case being designed for. **Anything here that survives
   contact with a real 3,000-chapter book will do so by luck until it is measured**, and the POC ladder
   should say so rather than quietly assume it scales.
