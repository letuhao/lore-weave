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

## 4. Two write paths — APPEND (new chapter) vs UPDATE (re-extract)

These are **different operations** and must not be conflated. "Don't touch old data" governs path A
**globally** (no chapter's data is ever rewritten); path B revises **only the re-extracted episode's
own contribution**, as a new transaction-time version (history retained, never deleted).

### Path A — ingest a NEW chapter (append-only; "development")
First time chapter N is seen.

```
1. Episode:   write the immutable episode row (+ embed).                          [append]
2. Extract:   clean per-chapter extraction (just-shipped precision pipeline) → candidate facts.
3. Resolve:   resolve entities vs existing nodes — write-time resolver + cross-kind merge
              (#43, BUILT + validated: re-extract identical text → 0 dups).        [no rewrite]
4. Reconcile: OPEN each new fact. If it supersedes a prior value IN STORY TIME (ch.500's 境界 >
              ch.300's), set the prior's `valid_to_ordinal` — a VALID-TIME close, normal growth.   [append]
5. Fold:      mark affected entities canonical-dirty → batched fold into the bounded snapshot.  [append]
```
**Which time axis moves: VALID (story) time forward.** No other chapter's data is touched.

### Path B — RE-EXTRACT an existing chapter (update/correction; "different concept")
Triggered when the **chapter text was edited** OR we re-run with a better model/prompt. Scoped to
**that one episode**; it is a TRANSACTION-TIME correction, and it **must reconcile (incl. RETRACT)**,
not blindly append:

```
1. Episode:   the chapter content hash changed (or forced) → write a NEW episode REVISION.   [append version]
2. Extract:   re-extract chapter N → new_facts.
3. DIFF vs what episode N's PRIOR revision contributed:
      • still present  → keep / update the value
      • GONE (edited out / corrected) → RETRACT: transaction-time close (`invalidated_at`) —
        we no longer believe this chapter asserts it.  ← pure append/merge CANNOT do this (#42).
      • NEW            → open
4. Resolve+Reconcile as in A for the kept/new facts.
5. Re-fold ONLY the snapshots that CITED episode N (bounded — not the book).
```
**Which time axis moves: TRANSACTION time (a new belief about the SAME chapter).** Valid-time/chapter
is unchanged. The prior episode-revision + its facts are transaction-time-closed (kept for
audit/time-travel), never deleted. **Run #2 did NOT exercise this** — it re-extracted identical text
(cache replay), so it validated A's "no over-extraction," not B's retract path.

> **Retraction is the load-bearing new capability.** The platform's `MERGE`/resolver adds + updates
> but cannot remove a fact a re-extraction dropped (#42, #43). Path B needs an **episode-scoped
> fact-diff + retract** (`remove_evidence_for_natural_key`-style) — design it explicitly.

## 5. Read paths

| Query | How |
|---|---|
| **Current state** | facts where `invalidated_at IS NULL` + latest canonical snapshot. O(1). |
| **As-of chapter N** (time-travel) | facts where `valid_from ≤ N < valid_to`; canonical snapshot with `ordinal ≤ N`. Powers **spoiler-free translation** + period-correct views. |
| **Development / timeline** | the ordered fact-versions + snapshot series → "show 张若尘's growth." |
| **Deep dive ("his powers")** | **semantic retrieval over episodes/segments** (embeddings) → top-K relevant, not full-scan. |
| **Full export** | stream facts ordered by `valid_from` — bounded per page. |

### 5B. Researching a LARGE entity (the read UX — you never load it all)

An entity with thousands of facts across 4,000 chapters is **never loaded whole**. Three bounded modes:

1. **Default (no range) → the newest bounded state.** Opening the entity loads only: the **latest
   canonical snapshot** (~500 words, one row), the **current facts** (latest-valid value *per
   attribute*, not all history), and a short **recent-changes tail**. O(1) regardless of book length.
   → *"without selecting a range, you get the most recent / current state."*
2. **Range select → time-travel (optional).** A chapter slider / arc picker loads the **as-of-N**
   view: facts where `valid_from ≤ N < valid_to` + the snapshot with `ordinal ≤ N`. Only when you
   want a *period* (development view, "around ch.500"), not the current state.
3. **Topic / question → semantic retrieval.** A question ("his powers?", "bond with 苏挽月?") does
   **RAG over the entity's embedded segments** → top-K relevant chunks → synthesize. Never a scroll.

**Chunk-load technique:** the full timeline is **cursor-paginated by chapter ordinal, newest-first**
(scroll back for older windows); topic reads are **vector top-K**; period reads are **indexed range
queries** on `(entity_id, valid_from)`. All bounded — no query ever returns the whole history.

| Intent | Loads | Cost |
|---|---|---|
| who-is-this-now (default) | latest canonical + current facts | O(1) |
| at chapter N / this arc | facts valid-in-range + as-of snapshot | indexed range |
| tell me about X | top-K retrieved segments | vector top-K |
| scroll whole history | windowed pages, newest-first | cursor page |

(Partly exists: the KG timeline already has pagination + chapter/date filters — #12/#15 — reuse it.)
An LLM agent "researching" the entity uses the **same** path: canonical as the entry, retrieval for
detail, optional as-of range — it is never handed the monolith either.

## 6. Applies to BOTH glossary and KG (the unifying point)

- **Glossary**: an entity's attribute values become bi-temporal facts; `description` is a folded
  canonical snapshot (not a flat field). The cross-kind merge (#43) is the entity-resolution step.
- **KG**: you **cannot** build a 4,000-chapter KG in one pass — it's episodic by necessity (Graphiti).
  Relations/events/facts are bi-temporal edges with `valid_from/to` + invalidation. The
  knowledge-service already has Neo4j + a `summarize_level` notion + community summaries → wire them
  to this model (relations get validity intervals; community/canonical summaries are folded snapshots).
- One ingest pipeline, two projections (glossary EAV view + Neo4j graph view).

## 6B. Translation — same bounded principle (input side)

Translation **consumes** this knowledge to stay consistent (names, terminology, relationships), so it
has the **same context-bloat risk** on the *input* side: injecting accumulated glossary/KG data that
is "so huge." The temporal model bounds it the same way it bounds extraction.

**What already exists (keep + build on):**
- Chapter translation fetches glossary **scoped to the chapter** (`fetch_translation_glossary(chapter_id)`)
  and `build_glossary_context` **scores entities by occurrence in the chapter text** — it injects only
  terms that actually appear, not all 15,947. ✅
- A **rolling summary** across batches (`session_translator`) — already the incremental-summary pattern. ✅
- `chapter_translation_glossary_usage` records which entities a chapter used (targeted re-translate). ✅

**Where it still bloats / must change under this design:**
1. **Translate BOUNDED units, never the accumulated blob.** A glossary entity's `description` under
   the flat-field model can be the 50 MB monolith → translating it bloats. Translate the **bounded
   canonical snapshot** + each **immutable episode/segment summary** instead. Because segments/snapshots
   are **immutable**, each is translated **exactly once** and cached (re-translate only on a new
   revision) — translation cost scales with *distinct bounded units*, not accumulated size.
2. **Inject AS-OF-CHAPTER state (spoiler-free + bounded).** When translating chapter N, inject the
   relevant entities' canonical/facts **valid as of N** (`valid_from ≤ N`), not their final ch.4,000
   state. Time-travel (§5) makes this a cheap projection and **prevents spoilers + anachronistic terms**
   (a ch.300 translation must not use a name/title the character only earns at ch.4,000).
3. **Bound the KG context too.** If/when translation uses KG relationships for disambiguation, inject
   only the **relevant edges as-of-N** (retrieved by the chapter's entities), never the whole graph.
4. **Verify the fetch is truly chapter-bounded** end-to-end (the scoring is client-side; confirm the
   endpoint doesn't pull the full book glossary before filtering — if it does, push the occurrence/
   as-of filter server-side).

**Net:** translation reuses the *same three append-only layers* — it reads bounded canonical snapshots
+ relevant as-of facts + (already) a rolling summary, and translates **immutable units once**. No path
ever feeds it an accumulated monolith.

## 6C. Consumers & blast radius (this is a foundational layer change)

The glossary/KG layer is read/written by **most of the platform**, so this design touches them all.
That is the *point* (one consistent, bounded, time-traveled knowledge layer for everyone) **and** the
main risk (broad blast radius). Manage it with a **backward-compat projection** (below), not a big-bang.

| Consumer (verified in code) | Role | Affected by this design |
|---|---|---|
| **extraction** (translation-svc) | producer | emits bi-temporal facts cited to episodes (the just-shipped clean pipeline feeds this) |
| **lore-enrichment-service** (`grounding`, `compose_task`, `book_profile`) | reader **+** producer | grounding reads **bounded, as-of** context (no 50 MB blob); enrichments become **cited bi-temporal facts** (not flat overwrites that erase history) |
| **composition-service** (co-writer: `plan.py`, `knowledge_client`, `glossary_client`, `style_voice`) | reader **+** producer | **the biggest reader** — must inject canon/KG **as-of the draft's chapter** (spoiler-free, period-correct, bounded) instead of the whole accumulated state; the canon flywheel writes facts valid-from that chapter |
| **wiki** (glossary-svc `wiki_*`) | reader **+** producer | generate articles from the **bounded canonical + as-of**, not a monolith |
| **chat / roleplay** (`frontend_tools`, `stream_service`) | reader | Q&A / character voice via **retrieval + as-of** (roleplay a character *as they were at ch.N*) |
| **search / catalog** | reader | semantic search over **episode/segment embeddings** |
| **translation** (§6B) | reader | bounded, as-of, immutable-once |

**Per-consumer win (why it's worth the blast radius):** every feature gets **consistency** (one
canon), **bounding** (no context bloat), and **time-travel** (as-of) *for free* — spoiler-free
composition, period-correct translation, accurate wiki, grounded enrichment.

### Migration strategy — projection, not big-bang
The old flat reads (`entity.description`, current EAV, the current KG) become a **stable "current"
projection** of the new facts (latest-valid facts where `invalidated_at IS NULL`). So:
- **Existing consumers keep working unchanged** against the projection during the transition.
- **New / upgraded consumers** opt into the temporal API (`as-of`, `timeline`, `retrieval`).
- Migration is **per-consumer and incremental** — no service must change on day one. This is what
  makes a layer-wide change tractable.

> **Open question (add to §9):** define the **knowledge-layer read/write API** (the projection +
> the temporal endpoints) as the stable contract before any consumer migrates — so the blast radius
> is mediated by one versioned interface, not N ad-hoc reads.

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
7. **Episode revisioning + retract reconciler (Path B)** — key the episode by **content hash** so an
   edited chapter mints a new revision automatically. The **fact-diff + RETRACT** (close facts the new
   revision dropped) is a NEW capability the current resolver lacks (#42) — build it as an
   episode-scoped reconciler. Decide: does an editorial re-run (better model, same text) also retract,
   or only TEXT edits? (Proposal: text-edit → full diff+retract; same-text re-run → update-only, no
   retract, to avoid churn.)
8. **Translation as-of-chapter + immutable-once (§6B)** — confirm: translate chapter N against the
   entity state **valid as of N** (spoiler-free), and translate immutable canonical/segment summaries
   **once** (cache, re-translate only on a new revision). Audit whether `fetch_translation_glossary`
   pulls the full book glossary before client-side filtering — if so, move the occurrence/as-of filter
   server-side. (The chapter-occurrence filter + rolling summary already exist; this adds the as-of
   bound + the bounded-canonical/immutable-unit translation.)
9. **Knowledge-layer API contract (§6C blast-radius gate)** — define the stable read/write interface
   FIRST: (a) the backward-compat **"current" projection** the old flat reads keep using; (b) the new
   **temporal endpoints** (`as_of=N`, `timeline`, `retrieve(entity, query)`, `append_fact`,
   `retract_fact`). Versioned, owned by glossary-svc (SSOT) + knowledge-svc (KG). Every consumer
   (enrichment, composition, wiki, chat, translation) migrates against THIS, not ad-hoc reads — so the
   blast radius is mediated by one contract. Sequence: ship the layer + projection → migrate consumers
   one at a time (composition first, biggest win).

## 10. Why this is the right call

- **Append-only / immutable** → never rewrite old data → safe under re-runs (validated: re-extract →
  0 dups) and concurrency; scales linearly forever.
- **Bounded context everywhere** → O(1) LLM cost per chapter; a 4,000-chapter book is just 4,000
  cheap folds, never one impossible merge.
- **Bi-temporal** → time-travel, development view, spoiler-free translation — features a flat model
  *cannot* offer.
- **Proven** → it's Graphiti + BooookScore, not speculation.
- **Composes** with the clean-extraction work we just shipped and the merge we already built.
