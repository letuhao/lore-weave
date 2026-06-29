# Spec — Incremental Temporal Knowledge Architecture (glossary + KG)

**Date:** 2026-06-29 · **Status:** DRAFT (review → implement next session) · **Scope:** BE + FE
**Pairs with:** `docs/analysis/2026-06-29-ontology-extraction-bloat.md` (clean extraction feeds this)

---

## 1. Problem

A novel can be **4,000+ chapters / 50 MB**. Accumulating an entity's knowledge (a character's
description, powers, relationships, the KG of facts/events) into a **monolithic field or a single
"rebuild-the-whole-graph" pass is impossible**:

- **Storage/IO** — one `description` grows to MBs; one KG-build re-reads the whole book.
- **Context bloat** — you can't feed 4,000 chapters (or even one entity's full history) to an LLM
  to "merge."
- **Loss of development** — a flat field can't represent that 张若尘 at ch.1 ≠ ch.4,000; overwrite
  erases growth, append explodes.
- **No arc structure** — semantic arc detection is fragile and **imported books have no arc format**.

**Goal:** an architecture where glossary AND KG knowledge accumulates **incrementally, append-only,
in O(1) context per chapter**, preserves the full history (time-travel), never rewrites old data,
and scales to an arbitrarily long book.

## 2. Research grounding (this is a proven pattern, not novel R&D)

| Source | What it validates |
|---|---|
| **Zep/Graphiti** (arXiv 2501.13956) — temporal KG agent memory | **Episodes** + **bi-temporal** facts (valid-time + transaction-time) + **invalidate-not-delete** + incremental entity resolution on ingest. The reference architecture. |
| **ATOM** (arXiv 2510.22590) | atomic temporal-KG **chunks** + **parallel merge**; "LLM-independent merge"; 93.8% faster than Graphiti. |
| **BooookScore** (arXiv 2310.00785) | book-length summarization: **incremental updating** (rolling refine) vs **hierarchical merge** (map-reduce); ground in **source citations** to kill hallucination. |
| **iText2KG** (2409.03284) / **SAGA** | incremental KG: chunk → extract → **resolve against existing nodes** → merge. |
| **ESAA event-sourcing** (2602.23193) | "source of truth = immutable append-only event log; current state is **projected**." |

**Our design = Graphiti's bi-temporal episodic graph + BooookScore's incremental-refine, evidence-grounded — applied uniformly to glossary entities AND the KG.**

## 3. Core model — three append-only layers

```
EPISODES (immutable events)  →  FACTS (bi-temporal, invalidate-not-delete)  →  CANONICAL (folded snapshots)
   = chapters / window-chunks       = entity attrs, KG relations/events            = bounded per-entity summary
```

### 3.1 Episode (the immutable ingest unit)
- An **episode** = a chapter, or a **context-window-sized chunk** of one (mechanical, NOT semantic
  arc — works on any imported book). Sealed once written, **never modified**.
- Metadata: `{episode_id, book_id, chapter_id, chapter_ordinal, char_range, token_count, ingested_at}`.
- Episodes are **embedded** → semantic retrieval ("episodes about 张若尘's powers") without full-scan.
- This is the user's "chunk by context window with metadata" = Graphiti's *episode* = a TimescaleDB
  hypertable chunk.

### 3.2 Bi-temporal fact (the atomic unit of knowledge)
Every piece of extracted knowledge — a glossary **attribute value**, a KG **relation/event/fact** —
is a **fact** with **two time axes** (Graphiti):

| Axis | Fields | Meaning |
|---|---|---|
| **Valid (story) time** | `valid_from_ordinal`, `valid_to_ordinal` | the chapter range over which it held true *in the story* |
| **Transaction (system) time** | `created_at`, `invalidated_at` | when we ingested it / when it was superseded |

- **Invalidate, never delete.** When ch.500 says "张若尘 reaches 黄极境", the old "境界 = 武者" fact is
  **invalidated** (`valid_to_ordinal = 500`, `invalidated_at = now`), the new one opened. Both rows
  stay → **time-travel** ("境界 as of ch.300") + **development view** for free.
- Each fact **cites its episode(s)** (`source_episode_id`) — evidence-grounded (anti-hallucination).
- Same shape for glossary EAV and KG triples → one mechanism, two surfaces.

### 3.3 Canonical snapshot (the bounded "who is this now")
- A per-entity, **bounded** (~300–500 word) synthesis — the thing the FE shows by default.
- **Fold-forward / incremental refine** (BooookScore incremental updating): when an episode-batch
  seals, `canonical_n = LLM(canonical_{n-1}[bounded] + new_facts_this_batch[bounded])`. **Never
  re-reads the book.** O(1) context regardless of chapter number.
- Snapshots are themselves **append-only + ordinal-stamped** → "canonical as of ch.N" time-travel.
- `canonical-dirty` flag (already exists) triggers the next fold; batched (not every chapter).

## 4. Write path (ingest one chapter)

```
1. Episode:   write the immutable episode row (+ embed).                         [append]
2. Extract:   clean per-chapter extraction (the just-shipped precision pipeline) → candidate facts.
3. Resolve:   resolve entities against existing nodes — the write-time resolver + cross-kind
              merge (#43, ALREADY BUILT + validated: re-extract → 0 dups).        [no rewrite]
4. Reconcile: for each attribute/relation, OPEN a new fact; if it supersedes a prior value,
              INVALIDATE the prior (set valid_to/invalidated_at) — never delete.  [append]
5. Fold:      mark affected entities canonical-dirty; a batched job folds new facts into the
              bounded canonical snapshot (incremental refine).                    [append]
```

Steps 1–5 are all **append / mark** — **old data is never mutated** (except a fact's
`valid_to/invalidated_at` stamp, which is a close, not a rewrite). This is what makes it scale
forever and stay safe under concurrency/re-runs.

## 5. Read paths

| Query | How |
|---|---|
| **Current state** | facts where `invalidated_at IS NULL` + latest canonical snapshot. O(1). |
| **As-of chapter N** (time-travel) | facts where `valid_from ≤ N < valid_to`; canonical snapshot with `ordinal ≤ N`. Powers **spoiler-free translation** + period-correct views. |
| **Development / timeline** | the ordered fact-versions + snapshot series → "show 张若尘's growth." |
| **Deep dive ("his powers")** | **semantic retrieval over episodes/segments** (embeddings) → top-K relevant, not full-scan. |
| **Full export** | stream facts ordered by `valid_from` — bounded per page. |

## 6. Applies to BOTH glossary and KG (the unifying point)

- **Glossary**: an entity's attribute values become bi-temporal facts; `description` is a folded
  canonical snapshot (not a flat field). The cross-kind merge (#43) is the entity-resolution step.
- **KG**: you **cannot** build a 4,000-chapter KG in one pass — it's episodic by necessity (Graphiti).
  Relations/events/facts are bi-temporal edges with `valid_from/to` + invalidation. The
  knowledge-service already has Neo4j + a `summarize_level` notion + community summaries → wire them
  to this model (relations get validity intervals; community/canonical summaries are folded snapshots).
- One ingest pipeline, two projections (glossary EAV view + Neo4j graph view).

## 7. FE impact

The FE must stop assuming "one entity = one current value." New surfaces:

1. **Canonical card** — the bounded synthesis (default view); never a 50 MB textarea.
2. **Time/version slider** — "view this entity **as of chapter N**"; scrubbing re-projects facts.
3. **Change timeline** — a per-entity feed of fact-opens/invalidations ("境界: 武者 → 黄极境 @ ch.500"),
   each with its **source episode citation** (click → the chapter quote).
4. **Diff view** — snapshot@N vs snapshot@M → the development delta.
5. **Retrieval, not scroll** — "ask about X" pulls relevant episodes, not the whole history.
6. **Translation** — translate per-episode + per-snapshot (bounded units), keyed by validity so a
   ch.300 translation never leaks ch.4,000 facts.

## 8. Builds on what already exists

| Have | Role here |
|---|---|
| write-time resolver + cross-kind merge (`#43`) | entity resolution on ingest (step 3) — **done + validated** |
| canonical layer + `canonical-dirty` (`#26/#7`) | the folded snapshot + its refresh trigger |
| `summarize_level` extraction + KG community summaries | the hierarchical-merge option (§ for coherent roll-ups) |
| per-entity `evidence` quotes + chapter links | the episode citations (anti-hallucination) |
| the just-shipped precision extraction | clean facts in → clean knowledge accumulates |

The new build is mostly: **episode store** (immutable + embedded), **bi-temporal columns +
invalidation** on facts/EAV/edges, the **fold-forward** batched job, and the **FE temporal surfaces**.

## 9. Open questions (resolve in CLARIFY before BUILD)

1. **Episode granularity** — chapter, or sub-chapter token-window? (Start: per-chapter; window only
   when a chapter exceeds the model context.)
2. **Fold cadence** — every chapter, every K chapters, or every sealed segment? (Batch by token
   budget to bound LLM cost.)
3. **`valid_from` source** — chapter ordinal (cheap, robust) vs detected in-story time
   (`event_date_iso`, advanced). Start with **chapter ordinal**.
4. **Storage** — Postgres bi-temporal tables for glossary; Neo4j edge properties for KG. Do we add a
   dedicated `episodes` table + an append-only `entity_facts` table, or extend EAV with temporal cols?
5. **Migration** — existing flat entities → seed as a single open fact (`valid_from = first seen`);
   no backfill of history required (append-only tolerates a cold start).
6. **Invalidation policy** — when is a new value a *supersession* (invalidate prior) vs a *coexisting*
   alias/multi-value? Needs per-attribute semantics (single-valued like `境界` vs multi like `aliases`).

## 10. Why this is the right call

- **Append-only / immutable** → never rewrite old data → safe under re-runs (validated: re-extract →
  0 dups) and concurrency; scales linearly forever.
- **Bounded context everywhere** → O(1) LLM cost per chapter; a 4,000-chapter book is just 4,000
  cheap folds, never one impossible merge.
- **Bi-temporal** → time-travel, development view, spoiler-free translation — features a flat model
  *cannot* offer.
- **Proven** → it's Graphiti + BooookScore, not speculation.
- **Composes** with the clean-extraction work we just shipped and the merge we already built.
