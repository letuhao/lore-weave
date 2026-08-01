# 03 — Two jobs, and why one agent cannot hold both

> *You cannot tell one agent to write literature and to store deterministic structured data at the
> same time.* — PO, 2026-08-01

This document is a correction. The first draft of this folder put **authoring** and **structuring** in
the same place and then asked which one the seam belonged to. That was the wrong question, and the
evidence that it was wrong had already been collected without being read.

---

## 1. The measured evidence, read again

Across the contract-generator probes, one model turn was asked to do all of this at once: invent the
categories, name them in the setting's register, judge which observed objects each covers, assign a
provenance, cite evidence, respect an arity range, and emit an envelope with no undeclared fields.

The failures, taken from live runs:

| failure | what the model was doing |
|---|---|
| `no_undeclared_body_fields` — added `aspect` to a slot declaring `member: {}` | **thinking about the content** and writing the thought down |
| `no_undeclared_body_fields` — added `nature` to `progression_kind` | the same, on a different slot |
| `every_category_covers` — put `covers` inside `body.instrument_match` | reading the consumer list as a schema hint |
| `codes_unique`, `no_generic_tier` | naming while also formatting |

Each was treated at the time as a prompt or an envelope defect, and each fix helped a little. The
pattern across them was not seen.

> **`BTG-A12`.** These are not formatting errors. They are the signature of a model **holding an
> intention while filling in a form**. Invention wants to add a field; a deterministic emitter must
> not. A single turn asked for both gets one at the cost of the other, and which one it sacrifices
> varies per run — which is exactly the instability the heal loop was papering over.

## 2. The two jobs

| | **AUTHORING** | **STRUCTURING** |
|---|---|---|
| produces | the game concept — prose, entities, decisions with reasons | manifests — closed sets, codes, typed references, a digest |
| is | creative. It **invents** what the source does not have. | deterministic. It **invents nothing**. |
| succeeds when | the world is playable and coherent | the structure is closed, resolvable and stable |
| fails by | being thin, generic, or unfaithful in a way nobody chose | being wrong, or silently accepting a value it should refuse |
| the human is | the author — deciding, disagreeing, revising | the reviewer — approving a gate, not writing content |
| output shape | **unstructured** | **strictly structured** |
| lives in | this tier | the game tier's generators |

> **`BTG-A13`.** The game concept is **not directly consumable by the game**. It is unstructured by
> nature, and trying to make it structured is trying to make an author into a compiler. The generators
> exist precisely to turn authored material into something a deterministic engine can read — that is
> their whole job, and it is a *different* job, not a later phase of the same one.

## 3. What each side may and may not do

**The authoring side may:**
* invent anything the game needs and the source lacks — this is the normal case, not the exception
* depart from canon, knowingly, and say why
* leave questions open and ask the human
* write prose, because prose is how a human reads, edits and disagrees

**The authoring side may not:**
* emit codes, ordinals, digests, or anything a machine will key on
* decide the shape of a data structure
* be trusted to be complete — completeness is checked downstream, not asserted upstream

**The structuring side may:**
* refuse — loudly, by name, with the reason
* enumerate, assign codes and ordinals, resolve references, close sets, freeze
* report what the concept did not decide

**The structuring side may not:**
* invent a member the concept does not contain
* soften a refusal into a default
* be asked for judgement about the world — if it needs one, the concept is incomplete and that is a
  finding to send back to the author, not a decision to make

> **`BTG-A14`.** *"The concept did not decide this"* is a **first-class output of structuring**, and it
> is the return path of the whole tier. Today the contract generator has nowhere to send such a
> finding, so it either invents or stalls. With an authored concept upstream, an unresolvable structure
> becomes a **question for the author** — which is the human-in-the-loop this project has been trying
> to build since the redesign began.

## 4. What this fixes about the current build

Re-reading the game tier's stuck points under this separation:

| stuck point | under the separation |
|---|---|
| the model kept inventing fields while filling the envelope | it is no longer asked to invent at that moment; the inventing already happened, in prose |
| `evidence_n` undefined | the concept states how many; structuring counts what is stated |
| `probe()` returns identifiers | structuring reads the concept, which is written in the concept's own vocabulary; retrieval over raw narrative stops being the critical path |
| `approve = lambda: True` | approval belongs to authoring, where a human is already sitting |
| heal rounds were unstable | a deterministic emitter reading decided content has much less to be unstable about |

None of that is a promise; it is the prediction this design makes, and
§[`06`](06_poc_plan.md) is how it gets checked.

## 4b. Four layers, not two — and one of them is already built

The two-job split is right and too coarse. Professional game production does not go from prose to data
in one step; it stacks documents, and the stack maps onto what this repo already has:

| layer | industry name | here | state |
|---|---|---|---|
| 1 | **Lore Bible / World Bible** | Lore Design — what the world IS | not built |
| 2 | **Narrative + Game Design (GDD)** | Gameplay Design — what the GAME does | not built |
| 3 | **Technical Design / Data Spec** | **`contracts/pool/registry.json`** — slots, arity, references, visibility | **BUILT** |
| 4 | compiled data | `app/pool` + `app/generators` → manifests | **BUILT** |

> **`BTG-A15`.** The contract-generator track built layers **3 and 4** and then, finding layers 1 and 2
> absent, reached past them to the novel. That is the whole diagnosis, and it explains a measurement
> that otherwise looks like a retrieval problem: slot-id queries scored at the noise floor because a
> **Data Spec** was being used as a **search query against a story**. Nothing in layer 3 was ever meant
> to be legible to a novel.
>
> The compiler analogy holds and is worth keeping: **nobody compiles source text straight to machine
> code.** Book is source; the design documents are the IR; the registry is the target's type system.

**Where the analogy breaks, and it matters.** A compiler's IR has a formal grammar. A game design
document is natural language *with structure* — semi-structured. So layer 3→4 is **not a parse**; it is
still a model reading prose, just prose in which the decisions have already been made. **The
determinism comes from the decisions being upstream, not from the format being formal.** Treating the
GDD as a formal IR would mean writing a parser and being surprised: a `Weapon / Material / Durability`
block is nearly YAML, while quest branching and NPC behaviour are not. How parseable a family is turns
out to be a **per-family property**, and one worth measuring rather than assuming.

## 4c. Lore Design vs Gameplay Design — the boundary is not the topic

The obvious split — *world stuff over here, game stuff over there* — does not survive contact. `Currency`
is lore; `Economy` is gameplay; spirit stones are both. `Realm` is lore; the gate that stops you
entering a zone is gameplay.

The boundary that does work is **what makes the statement true**:

> **`BTG-A16`.** A statement belongs to **Lore Design** if it is true because the world says so — it
> would still be true if no game were ever made. It belongs to **Gameplay Design** if it is true because
> the game needs it — it means nothing outside the game.

Same location, two documents:

```
LORE DESIGN                          GAMEPLAY DESIGN
Thanh Vân Thành                      Thanh Vân Thành
  population 550,000                   purpose: STARTER HUB
    cultivator 120,000                 first-hour flow: arrive → guild → first quest
  districts: inner · market ·          services: trainer, vendor, storage
    academy · slum · dock              level band: 1–10
  economy: spirit stone,               spawn budget: 0 hostile inside the barrier
    weapon craft, alchemy              quest anchors: 3 main, 6 side
  power: city lord · 12 elders ·       fast-travel: unlocked on arrival
    merchant council
```

Everything in the right-hand column is **invented**. None of it is in any novel. That column is why the
tier exists, and it is the column a Kind Generator can actually compile.

## 4d. Gameplay Design is MANY documents — one per element family

Lore Design is one document set, world-scoped. Gameplay Design is not: quests, items, enemies,
dungeons, skills, economy, crafting, spawn rules each need a **different design method, different
questions, and a different notion of "complete"**. A quest document asks about branching, inputs and
outcomes; an item document asks what exists uniquely in the book *and* what common families must be
invented so there is anything to loot.

> **`BTG-A17`.** **The gameplay design families and the pool's slots are the same taxonomy at two levels
> of formality.** A `quest` design document feeds `quest_*` slots; an `item` document feeds
> `item_archetype`, `instrument_tag`, `equip_slot`. This is falsifiable in both directions: a family
> with no slots produces documents nothing compiles, and a slot with no family is a data spec nobody
> designs for. Either is a defect, and both are checkable from the registry.

**Is this too much?** [`05_gameplay_inventory.md`](../LLM_MMO_RPG/40_progression_planner/05_gameplay_inventory.md)
counts **178 entries in 18 families**. Eighteen document types is a great deal of work — but the
*structure* costs nothing to adopt, and only the building is expensive. The discipline is the one this
project already used on the planner kinds: **build ONE family end to end, measure it, and only then
claim the pattern.** `BLD-A5` made exactly that claim falsifiable and it survived a fifth slot being
added without a fifth planner file. The same falsifiable claim governs here — *adding an element family
must not add an authoring engine* — and if it fails, the design is wrong and better to know at family
two than at family eighteen.

## 5. The handoff between them

The concept is unstructured, so the handoff cannot be a schema. What it can be:

* **addressable** — every claim the structuring side uses must be pointed at (a section, an entity, a
  sentence), because a manifest that cannot say where a value came from cannot be revised when the
  concept changes
* **content-addressed** — the concept has a digest; every manifest pins it. A concept edit makes every
  downstream artifact declare itself stale by comparison rather than by anyone remembering
* **one-directional** — the structuring side never writes back into the concept. It emits *findings*,
  and a human folds them in. Otherwise the authored document stops being authored.

This is the same shape the game tier already uses at its own freeze (`PPB-A6`), one tier up.

## 6. Where this leaves the seam question

The first draft asked: *is deriving the pool from the concept mechanical or judgemental?* — and treated
"mechanical" as a result that would delete a subsystem.

Under this separation, **mechanical is the design goal, not a discovery.** The generators are supposed
to be deterministic. The real question is different and sharper:

> **Does the authored concept decide enough that structuring it requires no judgement?**

An honest failure mode exists on both sides: the concept can under-decide (structuring stalls or is
forced to invent — a `BTG-A14` finding), or the structuring side can be under-specified (it asks for a
value the concept had no reason to state). The measurement is of *how often* and *of which kind*, and
that is what §[`06`](06_poc_plan.md) POC-C is for — reframed accordingly.
