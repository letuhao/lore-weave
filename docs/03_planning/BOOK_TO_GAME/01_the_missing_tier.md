# 01 — The missing tier, and the measurement that found it

**Prefix:** `BTG-*` (this folder only; not registered in the game track's id catalog, which governs
`docs/03_planning/LLM_MMO_RPG/` and does not scan here).

---

## 1. What the game tier has been doing instead

The contract generator ([`40_progression_planner`](../LLM_MMO_RPG/40_progression_planner/_index.md))
fills closed sets — instrument tags, item archetypes, progression kinds and their ladders — from
evidence. On 2026-08-01 it was measured against the real corpus for the first time, and the result is
the reason this folder exists.

**Every quality number the track had produced rested on evidence written by hand.** Eleven bullet
lines, extracted by the author from the novel, one object per line:

```
[ch12] a gold ring-shaped implement, resizable, thrown
```

That sentence is not in 封神演義. The novel has 乾坤圈 inside a battle scene. The line is an
*analysis*: an object, its affordances, stripped of narrative and normalised into something a game
rule could condition on. **The planners performed well because they were fed cooked material, and
that material was cooked by a human who was not counted as part of the pipeline.**

## 2. What happened when the raw source was substituted

Measured with production components — `chunk_text`, `top_k`, BYOK embeddings — over the real world:
100 source chapters and 16 lore pages, 675,860 chars, 2329 chunks.

| what was searched | result |
|---|---|
| the **novel** (narrative) | queries derived from slot ids scored at the noise floor; top hits were a lesson on playing the zither, deer conservation in Beijing |
| model-written queries in the work's own register (法寶 · 境界) | ~+0.09 and, far more importantly, the right material |
| the **scraped wiki** (encyclopaedic) | *out-scored* the novel while being *less* useful — a 《狐狸缘全传》 crossover reference beat the actual campaign passage |

> **`BTG-A1`.** Neither artifact in the world is the right source. A **novel** is written for a reader
> and *uses* its objects inside scenes about something else. An **encyclopaedia** is written about a
> subject and covers everything the word has ever meant — the page for 麒麟 carries Hong Kong lion
> dances and a light-novel species. A game needs a third thing that **nobody has written**: a document
> about this world, stated as game facts, written with the game's questions already in mind.

## 3. Two documents, and they are not versions of each other

| | a book | a game concept |
|---|---|---|
| written for | a reader | a rule system |
| 乾坤圈 is | a gold ring Taiyi Zhenren gave Nezha, used against Ao Bing | implement · thrown · returns · single target · held, not equipped · gated on realm |
| completeness means | it reads well | the sets are **closed** — nothing of that kind is missing |
| being wrong means | it is a weaker book | the game breaks |
| most of its content | comes from the source | **is not in the source** and must be authored |

That last row is the one that decides the architecture. A summariser cannot produce this document,
because most of what a game needs was never written down: how many realms, what a grade means, what a
tier costs. The source **constrains** the answer; it does not contain it.

## 4. Why `lore-enrichment-service` cannot close this alone

`lore-enrichment-service` is a **retrieval and verification** engine, and a good one: sealed corpora,
anchor-derived citations (a quote that is not in the chunk cannot be given a span at all), a
provenance census, a refusal channel. Every one of those is needed here.

What it structurally lacks:

1. **It answers questions; it does not decide which questions exist.** Its interrogation stage takes a
   brief's questions and finds answers. POC-1 failed for exactly this reason — the brief's eleven
   questions covered only the cultivation ladder, and `TrainingRuleDecl`, `strike_formula` and
   `derives_from` had **zero** producers. A closed questionnaire cannot discover what it did not ask.
2. **It has no notion of a target artifact.** It enriches *a corpus*. It does not author *a document*
   with a table of contents, an editor, a revision history and a human who disagrees with it.
3. **It has no notion of fidelity.** Nothing in it can express *"this game follows canon on the cast
   and invents freely on geography"*, and that is the decision the whole tier exists to serve.
4. **It is single-book.** A world holds several books plus a glossary and a KG; exploiting that
   mixture is a world-level operation (§ [`02`](02_world_as_corpus.md)).

> **`BTG-A2`.** The missing piece is not a stage in a pipeline — it is an **artifact under authorship**.
> Everything this session tried to build as an in-pipeline "cook" step was ephemeral: computed, used,
> dropped. A human cannot read, edit, disagree with or return tomorrow to an intermediate value. Three
> problems the game tier is currently stuck on dissolve the moment the cooked material is a **document**
> instead of a value:
>
> | stuck on | why it dissolves |
> |---|---|
> | `approve` has been `lambda: True` all session | a batch pipeline has no place for a human to stand; a document being written does |
> | `evidence_n` is undefined against a real corpus | you cannot count entities in 2329 narrative chunks; you can count them in a document with a table of contents |
> | `probe()` returns identifiers, not queries | schema words fail against classical Chinese; they do not fail against a document written in the contract's own vocabulary |
>
> Three symptoms, one cause.

## 5. What this tier owes the game tier

The game tier's contract generator already declares what it needs: a registry of slots, each wanting
members with provenance and evidence. This tier's output must be **retrievable**, **countable**, and
**provenance-carrying**, because those are the three properties the contract generator's criteria
already depend on (`MEM-A5`, `ENR-A4`, `BLD-A1`).

It also owes something the game tier cannot check for itself: **a stated fidelity position**, so that a
`PROPOSED` member is legitimate in one game and a defect in another.
