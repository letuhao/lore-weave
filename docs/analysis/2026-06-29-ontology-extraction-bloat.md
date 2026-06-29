# Ontology as a Root Cause of Extraction Bloat & Slowness

**Date:** 2026-06-29
**Author:** investigation (Claude) at user request
**Scope:** glossary + KG extraction quality, driven by the per-book **ontology** (kinds, kind
descriptions, attributes). Two real books profiled on the live `loreweave_glossary` DB.

> **TL;DR** — The ontology is a *primary* driver of over-extraction, and over-extraction is a
> *primary* driver of slow extraction (LLM decode time ∝ output volume). The two structural
> ontology defects are **(1) empty/vague kind descriptions** (no extraction boundary) and
> **(2) too many abstract/thematic kinds** (no "is this a discrete named entity?" test). Two
> secondary defects: **category-error kinds** (`relationship`/`event` extracted as flat entities
> instead of KG edges/temporal nodes) and **bloated, redundant attribute schemas** (`character`
> = 57 attributes). Better *dedup* barely helps; the lever is **ontology hygiene + upstream
> extraction constraint**.

---

## 1. The two books

| | **Book 1** — erotic fantasy | **Book 2** — 万古神帝 (long web novel) |
|---|---|---|
| Book ID | `019f0820-5e79-7916-9a62-91ad7a5ee65d` | `019efae6-3797-79a2-bb4e-ade28cd6fe60` |
| Chapters extracted | 10 | 707 (of 4234) |
| Live glossary entities | **3,187** | **15,947** |
| **Entities / extracted chapter** | **318.7** 🔴 | **22.6** |
| Kinds defined / used | 30 / 30 | 11 / 9 |
| After cross-kind exact dedup | 1,854 (−42%) | 14,242 (−11%) |
| Single-mention (≤1 evidence) | 86% | 69% |
| Possessive `的` "names" | 22% (712) | 31% (4,901) |
| ≥2 mentions **+ deduped** (realistic size) | **~227** | ~4,190 |

**Book 1 produces 14× more entities per chapter than Book 2.** The dominant difference is its
ontology: **30 kinds, ~20 of them abstract/thematic**, vs Book 2's 9 mostly-concrete kinds.

---

## 2. Ontology defect #1 — empty / vague kind descriptions

The `#33` fix put the kind description into the extraction prompt so the model knows what each kind
captures. **But the descriptions are mostly empty or abstract**, so that guard is inert.

- **Book 2: 8 of 9 used kinds have ZERO description** (only `combat_encounter` has one). `relationship`
  (4,789 entities), `event` (5,498), `item`, `concept`, `character` — all `desc_len = 0`.
- **Book 1: the `character` kind has ZERO description** (yet 57 attributes and is the single most
  important kind). The descriptions that *do* exist are abstract and invite phrase extraction:

  | kind | description | entities |
  |---|---|---|
  | `concept` | "An abstract idea, philosophical principle, or metaphysical construct within the world." | 190 |
  | `erotic_arc` | "A narrative progression focused on sexual development or corruption." | 248 |
  | `military_strategy` | "The doctrines, forces, and tactical philosophies of organized combat." | 152 |
  | `social_hierarchy` | "Layer 2: The structures of power, class, and governance within the world." | 125 |
  | `race_species` | "Races/species with their traits." (32 chars) | 404 |

  None of these contains a **discreteness test** ("extract a NAMED instance; do NOT extract themes,
  descriptions, or relationships"). "An abstract idea … within the world" literally tells the model
  to extract every abstract idea.

**Effect:** with no boundary, the model extracts every noun phrase that loosely fits the theme →
over-extraction + mis-kinding.

---

## 3. Ontology defect #2 — too many abstract / thematic kinds (Book 1)

Of Book 1's 30 active kinds, ~20 are **abstract categories / systems / themes**, not discrete
entity types:

`event, erotic_arc, concept, kink, military_strategy, erotic_drama_type, social_hierarchy,
magic_system, physicality_biology, political_structure, cosmology_system, cosmology_history,
sex_scene, sexual_dynamics, bonds_contracts, sexual_tool, sexual_profile, fundamental_law,
economy_governance, era`

These are the over-extracted ones (`erotic_arc` 248, `concept` 190, `kink` 166, `military_strategy`
152, `social_hierarchy` 125 …) and overwhelmingly single-mention. A "kind" like `erotic_arc` or
`military_strategy` has no natural discrete instance — so the model invents one per scene/paragraph.

The concrete kinds behave far better: `character` 98, `artifact` 64, `region` 12 — bounded counts.

**The mechanism is multiplicative:** each abstract kind is an independent invitation to scan the
chapter and emit instances. 20 abstract kinds × 10 chapters ⇒ the 319-entities/chapter blow-up.
All 30 kinds are attached to the **`universal` genre** (no curated genre pack), i.e. an
undifferentiated bag.

---

## 4. Ontology defect #3 — category-error kinds (`relationship`, `event`)

Book 2's `relationship` kind holds **4,789 "entities", 88% of them possessive `A與B的X關係`
phrases**:

```
西院院主與張若塵的師生關係   (the teacher–student relationship between West Court Master and Zhang Ruochen)
林昀姍與黑虎堂的敵對關係     (the hostile relationship between Lin Yunshan and the Black Tiger Hall)
張若塵與雲芝的關係           (the relationship between Zhang Ruochen and Yunzhi)
```

A relationship is a **KG edge** (`A —[rel]→ B`), not a flat glossary entity. knowledge-service
already extracts relations as edges; making `relationship` a glossary *kind* makes the entity pass
generate thousands of phrase-rows that (a) are not entities, (b) can never dedup (every pair is
unique), and (c) cost a full extra LLM pass of decode. `event` (5,498) is similar — events are
temporal nodes, and most are single-mention phrases.

---

## 5. Ontology defect #4 — bloated, redundant attribute schemas

Book 1 `character` has **57 attributes** (Book 2 `character`: 10). The list is redundant and
polluted:

- duplicates: `alias` **and** `aliases`; `gender` + `current_gender` + `original_gender` +
  `original_gender_vs_current`; `corruption_level` + `corruption_stage` + `corruption_training_status`.
- a literal junk attribute: **`new_attribute`**.
- ~30 niche fields (`scent_musk`, `previous_self_contrast`, `body_adaptation`, `fluids`, …).

**Effect on speed & quality:** every extracted character asks the model to consider/emit up to 57
fields → huge per-entity output (slow decode) that is mostly null/sparse, and the schema sprawl
encourages the model to "find" content to fill fields. Attribute schemas should be small and
curated; 57 is a smell that the schema was AI-generated and never pruned.

---

## 6. How the ontology causes *slow* extraction (not just messy data)

`pass2_orchestrator` runs **4–5 LLM passes per chapter** (entities → relations → events → facts →
summary). LLM latency is dominated by **decode** (autoregressive output generation), so cost ∝
**how much each pass emits**:

- An entity pass told (by 20 abstract kinds + empty descriptions + a 57-field schema) to emit
  **319 entities/chapter** spends most of its time decoding that output.
- A `relationship` pass emitting **4,789 phrase-edges** is a whole pass of bloated decode producing
  non-entities.

So the ontology inflates the **output token volume** of every pass → directly slower.

**Critical nuance for fixing speed:** *where* you cut matters.
- **Post-process filters** (drop `的`-phrases / singletons *after* generation) clean the data but the
  model already paid the decode cost → small speedup.
- **Upstream ontology constraint** (fewer/curated kinds, a discreteness test in every description,
  drop the `relationship` pass, cap attributes) makes the model **generate less** → large speedup.

---

## 7. Recommendations (ontology-first, ordered by impact-to-effort)

| # | Action | Fixes | Effort |
|---|---|---|---|
| **O1** | **Mandate a discreteness test in every kind description** ("Extract NAMED instances of X. Do NOT extract themes, descriptions, relationships, or one-off mentions.") and **block extraction on empty descriptions** (or fall back to a safe generic with the test). | over-extraction + mis-kinding | **S** |
| **O2** | **Curate the kind set**: flag abstract/thematic kinds (`concept`, `erotic_arc`, `military_strategy`, `social_hierarchy`, `cosmology_*`, …) as **non-extractable "lenses"** or merge them into a few concrete kinds. Cap the active extractable kind count (e.g. warn > 15). | the Book-1 14× blow-up | **M** |
| **O3** | **Stop extracting `relationship` (and reconsider `event`) as glossary kinds** — route them to KG edges / temporal nodes (the two-layer glossary↔KG pattern). | 4.8k phrase-rows + a whole bloated pass | **M–L** |
| **O4** | **Attribute-schema linter**: cap attributes/kind (e.g. ≤ ~15), de-dupe redundant attrs, strip junk (`new_attribute`). Smaller schema → less decode, less sparsity. | per-entity output size (speed) | **S–M** |
| **O5** | **Confidence floor**: don't auto-canonicalize single-mention entities — quarantine as "needs review" or require ≥2 mentions. (Book 1 → ~227, Book 2 → ~4,190.) | the singleton flood | **M** |
| **O6** | **Ontology-quality "linter" surfaced in the Schema GUI** (#28/#22): flag empty descriptions, missing discreteness test, > N attributes, abstract-category kinds, `relationship`/`event` as glossary kinds. Authoring-time prevention. | recurrence | **M** |
| — | Cross-kind exact dedup remediation (`#43`, shipped) | existing same-name/diff-kind dups | done |
| — | Smarter *name* dedup (separator/alias) | **negligible yield (−6 / +70 unsafe)** — not worth it | skip |

**Suggested first cut:** **O1 + O4** (both **S**, deterministic, immediately reduce decode *and*
data noise) → then **O2/O3** (the structural wins) → **O5** for the long tail.

---

## 8. How the field actually does extraction (research) — and where we diverge

Web research on LLM extraction practice (general documents + novel-specific) strongly corroborates
this analysis: **the established norm is a SMALL set of CONCRETE entity types with explicit
definitions + examples, precision-constrained prompting, and conservative coreference** — the
opposite of our 30 abstract, description-less kinds.

### 8a. General-document / knowledge-graph extraction (GraphRAG, structured prompting)

- **Tiny, concrete type sets.** Microsoft **GraphRAG ships ~4 default entity types** —
  *person, organization, geo/location, event* — customizable per domain, with 15 entity + 12
  relationship few-shot examples. Industry default is **~4–6 concrete types**, not 30 themes.
- **Type definitions + EXAMPLES in the prompt.** "LLMs often misclassify due to **overgeneralization**;
  including clear definitions and examples for each type helps the model distinguish similar types."
  (We inject a kind *description* — when present — but no examples and no counter-examples.)
- **Sequential / staged extraction.** Extract entity types *in order*, and **relations only after
  all entities** — "reduces attention competition, improves precision." (Our `pass2` does separate
  entity→relation passes, which is correct; we could sequence *within* the entity pass.)
- **Explicit in-prompt filtering rules** beat post-processing — e.g. legal pipelines add a rule to
  drop court/jury entities *in the prompt*, removing noise at the source.
- **Binary, decomposed relations** as triples — never relation *phrases*.
- **Gleaning is for RECALL.** GraphRAG runs multiple passes to extract *more*. **Our problem is the
  opposite** (over-extraction) — so we should explicitly **not glean**, and instead add a precision/
  salience constraint. Worth stating so nobody "fixes" sparsity we don't have.
- **A description per entity** is standard (GraphRAG schema = name, type, description).

### 8b. Novel / literary-specific extraction (BookNLP, schema-guided literary KG)

- **Schema-guided ≫ open-domain for fiction.** "Schema-guided extraction **dramatically
  outperforms** open-domain extraction for literary texts… ensures the LLM extracts entities
  meaningful for each work's genre/themes." → *Having a schema is right; the schema just has to be
  concrete.* Our bug is a **bad** schema, not the existence of one.
- **Coreference / character-name CLUSTERING at extraction time.** **BookNLP** (the canonical
  book-length pipeline: POS, NER, **name clustering**, pronoun coref, quote attribution) clusters
  `Tom / Tom Sawyer / Mr. Sawyer` into **one** character *before* graphing. This is exactly our
  `伊斯坦莎` vs `伊斯坦莎.薩納丹` fragmentation — solved upstream by name-clustering, not post-hoc.
- **…but conservative coref — over-merging is the bigger danger.** "Attempting **full** coreference
  (any named/common/pronoun corefer) tends to **erroneously conflate distinct entities**." → This
  **validates our caution**: aggressive head-token/substring aliasing (the `露露 → 露露的打氣`
  false-positive) is the known failure mode; cluster names conservatively, at separator boundaries.
- **Salience filtering.** Literary pipelines rank mentions by **salience** (how much a mention
  stands out) and drop one-off background mentions — the principled version of our "≥2 evidence" floor.
- **Relations from dialogue / co-occurrence as EDGES**, decomposed to binary pairs — never as
  `A與B的關係` entity rows.

### 8c. Scorecard — established practice vs LoreWeave today

| Practice (field norm) | LoreWeave today | Gap → action |
|---|---|---|
| ~4–6 **concrete** entity types | Book 1: **30** kinds (~20 abstract) | **O2** — curate; abstract → lenses/tags |
| Type **definition + examples** in prompt | description only, **often empty** | **O1** — mandate description **+ examples + discreteness test** |
| **Salience / frequency** filter | none (auto-promote singletons) | **O5** — ≥2-mention floor / quarantine |
| **Coreference name-clustering** at extraction | partial (write-time resolver, exact-fold) | **O7 (new)** — conservative name-cluster pre-pass (boundary-anchored) |
| **Conservative** coref (avoid over-merge) | ✓ (we already declined head-token aliasing) | keep — don't ship aggressive substring merge |
| Relations as **binary edges** | `relationship`/`event` as glossary **kinds** | **O3** — route to KG edges/nodes |
| Schema-guided (concrete schema) | schema-guided but **schema is bad** | O1+O2 fix the schema, keep the approach |
| Gleaning = boost recall | n/a | **don't add gleaning** — we're over-, not under-extracting |
| Description per entity | attributes (57!) but no concise entity description | **O4** — small attr set + a short entity description |

**Net:** our pipeline architecture is sound and aligned with the field (schema-guided, multi-pass,
write-time resolver). The divergence is entirely in **ontology quality** (too many/abstract kinds,
empty descriptions, no examples, no salience gate) — i.e. the **agent's ontology-authoring skill**
and the **adopted standards**, exactly the upstream levers identified in §7.

### 8d. New recommendation surfaced by the research

| # | Action | Source of practice |
|---|---|---|
| **O7** | **Conservative coreference / name-clustering pre-pass** (boundary-anchored: `given ⊂ given·surname`), to fold `伊斯坦莎`→`伊斯坦莎.薩納丹` at extraction — NOT aggressive substring (which over-conflates). | BookNLP name clustering |
| **O8** | In `glossary_skill.py`, require **2–3 examples + a counter-example** per kind (not just a description) — "extract X like {a,b}; do NOT extract {theme/relationship}". | GraphRAG defs+examples |
| **O9** | Explicitly **do not enable gleaning / recall-boosting**; add a precision+salience instruction to the entity pass instead. | GraphRAG gleaning (inverse) |

**Sources:** [NVIDIA — Insights & Evaluation for LLM-Driven KGs](https://developer.nvidia.com/blog/insights-techniques-and-evaluation-for-llm-driven-knowledge-graphs/) ·
[CORE-KG: Structured Prompting + Coreference (arXiv 2510.26512)](https://arxiv.org/pdf/2510.26512) ·
[GraphRAG implementation guide — entity extraction & gleaning (PremAI, 2026)](https://blog.premai.io/graphrag-implementation-guide-entity-extraction-query-routing-when-it-beats-vector-rag-2026/) ·
[Microsoft GraphRAG auto-tuning](https://www.microsoft.com/en-us/research/blog/graphrag-auto-tuning-provides-rapid-adaptation-to-new-domains/) ·
[BookNLP pipeline (name clustering + coref)](https://github.com/booknlp/booknlp) ·
[Evaluating NER for social networks from novels (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7924459/) ·
[Dialogue-Based Multi-Dimensional Relationship Extraction from Novels (arXiv 2507.04852)](https://arxiv.org/html/2507.04852) ·
[LLMs Fall Short: Complex Relationships in Detective Narratives (arXiv 2402.11051)](https://arxiv.org/pdf/2402.11051) ·
[iText2KG: Incremental KG Construction (arXiv 2409.03284)](https://arxiv.org/pdf/2409.03284)

---

## 9. POC — measured on gemma-4-26b-a4b-qat (lm_studio)

Two experiments on `google/gemma-4-26b-a4b-qat` to test the two hypotheses empirically. Harness:
`scratchpad/poc/run_poc.py` (crafted chapter, known ground truth) + `run_poc_real.py` (real
万古神帝 chapters). The model has a 200K context, so **nothing truncated** — any degradation is
pure attention dilution, not budget starvation.

### 9a. Crafted chapter (known ground truth → objective recall + precision)

A 631-char xianxia scene with **11 ground-truth scene entities** and **6 background distractors**
(a dead mentor in memory, a missing disciple, geographic asides, two distant non-scene characters)
that a precise extractor must OMIT.

| Method | sys-prompt tok | entities | recall | **background leak** | latency |
|---|---|---|---|---|---|
| **A_WARM** — real prompt + **1000 known_entities** | 6,130 | 17 | 11/11 | **6 / 6** 🔴 | 8.3s |
| **B_RAW** — real prompt + **0 known_entities** | 2,133 | 12 | 10/11 | **2 / 6** | 6.1s |
| **C_BLOATED_ONT** — book 1's **30 abstract kinds** | 1,337 | 18 | 11/11 | **6 / 6** 🔴 | 4.5s |
| **D_LEAN_ONT** — **6 concrete kinds + discreteness test** | **952** | 13 | **11/11** | **2 / 6** ✅ | **4.0s** |

**Both the known-entities flood AND the abstract ontology collapse precision the same way** —
each leaked **all 6** background entities (3× the false positives) while recall barely moved.
**Precision, not recall, is what dies.** `D_LEAN` (raw + concrete ontology) wins every axis:
best recall, best precision, smallest prompt, fastest.

### 9b. Real chapters (万古神帝 ch. 0050/0100/0200, avg; no ground truth → over-extraction proxy)

Warm method injects the book's **real top-1000 entity names** (faithful re-extraction).

| Method | avg entities | `的`-phrase % | sys-prompt tok | latency |
|---|---|---|---|---|
| **A_WARM** (1000 real known) | **16** | 0% | **~10,300** | **9.0s** |
| **B_RAW** (0 known) | 13 | 0% | ~4,300 | 7.1s |
| C_BLOATED (book 2's 10 kinds) | 12 | 0% | ~3,100 | 4.7s |
| **D_LEAN** (6 concrete) | 15 | 0% | ~3,100 | 5.3s |

**Findings:**
1. **Warm re-extraction over-extracts ~23% (16 vs 13), costs 2.5× the prompt tokens, +27% latency
   — for worse quality.** The known-entities injection is a net negative: it dilutes attention and
   burns tokens. **Validates the "raw extract → merge" architecture** (extract stateless per
   chapter, resolve with the cross-kind merge afterwards).
2. **`的`-phrase pollution is 0% from the KG entity prompt.** So the book's 4,789 relationship
   phrases come from the **glossary `relationship` kind**, NOT entity extraction — sharpening O3
   (remove `relationship` as a glossary kind; it's not an entity-prompt issue).
3. **Abstractness, not kind-count, drives the blow-up.** Book 2's 10 *concrete* kinds didn't
   over-extract (C mild); book 1's 30 *abstract* kinds did (crafted C: leak 6 vs 2). → O2 should
   target *abstract* kinds specifically, not just count.

### 9c. POC conclusions → confirmed direction

- **Adopt raw/stateless extraction** (drop the `known_entities` injection from re-runs) + rely on
  the **write-time resolver + cross-kind merge** (`#43`) for dedup. Faster, cheaper, more precise.
- **The base KG entity prompt is already good** (scene-relevance + omission bias work) — the wins
  are (a) not flooding it with known-entities, (b) a concrete ontology, (c) removing `relationship`
  from the *glossary* path.
- **Next POC ideas** (not yet run): a tiny **salience re-prompt** ("keep only entities mentioned ≥2×
  or central to the scene") as a cheap precision pass; a **two-stage extract-then-judge** (the
  existing `precision_filter`); and measuring the glossary-extraction prompt directly (where the
  `的`-phrases and 30-abstract-kinds actually originate).

### 9d. The GLOSSARY extraction path — where the bloat & slowness are actually born

§9a/9b POC'd the *KG* entity prompt (clean: scene-relevance + omission). The bloat the user sees
lives in the **glossary** path: `services/translation-service/app/workers/extraction_prompt.py`.
Running the same matrix through the **real** glossary prompt builder (gemma, 万古神帝 ch.
0050/0100/0200, avg):

| Method | entities | `的`-phrase% | latency/call | calls/chapter | ~total/chapter |
|---|---|---|---|---|---|
| GLOSS_WARM (book 2's 10 kinds, 1000 known) | 13 | 0% | **20.6s** | 4 | **~82s** |
| GLOSS_RAW (10 kinds, 0 known) | 13 | 5% | 17.8s | 4 | ~71s |
| **GLOSS_LEAN** (5 concrete kinds) | 16 | 0% | **11.3s** | 2 | **~23s** |
| **GLOSS_IMPROVED** (lean kinds + scene-relevance template) | 14 | 0% | 10.7s | 2 | ~21s |

**Why the glossary path is "slow as hell" (structural, confirmed):**
1. **Weak precision prompt.** `SYSTEM_TEMPLATE` says *"identify ALL named entities matching the
   types"* with **no scene-relevance / omission filter** (the KG prompt's key precision control is
   absent) and `max_entities_per_kind = 30`.
2. **~20s per call** (vs KG's ~7s) — the per-kind **attribute schemas** (book 1 `character` = 57
   attrs!) bloat both the input schema and the output (every entity × every attr).
3. **`MAX_KINDS_PER_BATCH = 3`** → 10 kinds = **4 LLM calls/chapter**; book 1's 30 kinds = **10
   calls/chapter**. So per chapter ≈ `calls × ~20s` → **~80s for book 2, ~200s for book 1**.

**The lean lever compounds on speed:** a 5-concrete-kind ontology is **~2× faster per call AND
halves the batch count → ~3.6× faster overall** (~23s vs ~82s/chapter) while extracting *more*
cleanly. Dropping `known_entities` (warm→raw) saves 3× prompt tokens for no quality loss.

### 9d-bis. POC-4 — reproducing the `relationship` phrase flood (gap closed)

The §9d run put all 10 kinds in ONE call, which DILUTED `relationship` (24% phrase). Production
batches kinds 3-at-a-time, so `relationship` gets its **own** batch. Re-running it that way (gemma,
**6** chapters: 0050/0100/0200/0500/1000/1500):

| Method (avg over 6 ch) | entities | **`的/与` phrase rate** |
|---|---|---|
| **REL_OWN_BATCH** (relationship alone, as production) | 2.5 | **100%** (every chapter) 🔴 |
| CHAR_ONLY (control, concrete kind) | 4.5 | **4%** |
| REL+CHAR (2-kind batch) | 6.2 | 24% |

**Every `relationship` "entity" is an `A與B的關係` phrase** — real samples: `张若尘与端木星灵`,
`张若尘与风知林`, `张若尘与树祖`, `黑木树人一族与人族军士`. This **reproduces the production
data experimentally** (book 2's 4,789 relationship rows, 88% possessive) and **directly validates
fix #4**: `relationship` as a glossary kind is 100% phrase-noise; concrete kinds are 4%. The
dilution in the 10-kind batch is itself the evidence that `relationship` over-produces when given
a dedicated call. → **Drop `relationship` as a glossary kind; relationships are KG edges.**

**Cross-model confirmation:** re-running REL_OWN_BATCH on **qwen3.6-27b** (a different model) gave
the **same 100% phrase rate** (3/3 chapters; samples even more elaborate —
`张若尘与端木星灵的陪练指导关系`, `张若尘与风知林的生死台对决关系`), CHAR_ONLY 0%. So the
`relationship`-kind defect is **model-INDEPENDENT** (structural ontology issue), unlike the abstract-
kind over-extraction which was model-sensitive (clear on gemma, muted on qwen).

### 9e. Validated remediation (what the whole POC supports)

1. **Raw / stateless extraction** — stop injecting `known_entities`; rely on the write-time
   resolver + cross-kind merge (`#43`). Faster, 3× cheaper, no quality loss.
2. **Lean CONCRETE ontology** (≤ ~6–8 kinds, real discreteness-test descriptions, ≤ ~10 attrs/kind)
   — the biggest single speed + precision lever (~3.6× faster on the glossary path).
3. **Add the KG prompt's scene-relevance / omission filter to the glossary `SYSTEM_TEMPLATE`** and
   drop *"ALL"* → *"salient, discrete, named"*.
4. **Drop `relationship` (and reconsider `event`) as glossary kinds** → KG edges/nodes (kills the
   `的`-phrase flood + a whole bloated batch).
5. **Author-time enforcement in `glossary_skill.py`** (O1/O8) so new ontologies are born lean +
   concrete with examples — prevents recurrence.

---

## Appendix — full kind tables

### Book 1 (`019f0820…`, 10 ch, 3,187 entities, 30 kinds, all `universal` genre)
`race_species` 404 (desc 32, 4 attrs) · `event` 268 · `place` 260 · `erotic_arc` 248 · `concept`
190 · `kink` 166 · `military_strategy` 152 · `erotic_drama_type` 146 · `social_hierarchy` 125 ·
**`character` 98 (desc 0, 57 attrs)** · `plane_dimension` 94 · `magic_system` 94 ·
`physicality_biology` 93 · `political_structure` 85 · `military_unit` 79 · `cosmology_system` 79 ·
`faction` 75 · `cosmology_history` 74 · `sex_scene` 64 · `artifact` 64 · `sexual_dynamics` 51 ·
`magic_school` 50 · `bonds_contracts` 48 · `sexual_tool` 46 · `sexual_profile` 42 ·
`fundamental_law` 31 · `economy_governance` 24 · `world` 16 · `region` 12 · `era` 9 · `unknown` 0.

### Book 2 (`019efae6…`, 707 ch, 15,947 entities, 9 used kinds — ALL desc_len 0 except `combat_encounter`)
`event` 5,498 · `relationship` 4,789 (88% `的`-phrases) · `item` 1,596 · `concept` 1,216 ·
`location` 851 · `character` 836 (10 attrs) · `technique` 732 · `organization` 338 ·
`combat_encounter` 91 · `romantic_scene` 0 · `unknown` 0.

*Queries: progressive-fold counts, per-kind entity/singleton/possessive counts, attribute lists,
and genre membership — all run read-only against `loreweave_glossary` on `infra-postgres-1:5555`.*
