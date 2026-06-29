# Spec — Incremental Temporal Knowledge Architecture (glossary + KG)

**Date:** 2026-06-29 (hardened 2026-06-30) · **Status:** DESIGN COMPLETE — architecture validated;
edge-case review (§11, 5 adversarial agents) surfaced ~14 HIGH gaps / 4 root causes; **§12 closes all of
them** with implementable design + re-locks the 6 reopened decisions. **BUILD-ready** (next session,
separate branch) · **Scope:** BE + FE
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

## 6D. Knowledge Access Layer (KAL) — the single read/write boundary (FUTURE-PROOFING)

**The most important structural decision.** The agent sweeps showed the glossary/KG read/write surface
is **scattered**: stable service clients in some places, but also bespoke per-service endpoints, MCP
tools, **and direct DB reads** (wiki reads `entity_attribute_values` directly; enrichment pulls the
full-book glossary; composition/chat/enrichment each hit different endpoints). That scattering is the
real reason a model change (this temporal one — or any future one) threatens an **N-consumer refactor**.

**Fix: every read/write of entity/lore/KG knowledge goes through ONE versioned contract — the KAL.**
The flat→bi-temporal change (and every future change) lands **entirely behind it**; consumers never move.

### The contract (bounded BY CONSTRUCTION — no "give me everything" call exists)

**Reads** (every one returns a bounded result; this is what makes context bloat structurally impossible):
- `get_canonical(entity, as_of?)` — the bounded canonical snapshot (current, or as-of chapter N)
- `get_facts(entity, as_of?, attrs?)` — latest-valid (or valid-at-N) facts, per-attribute bounded
- `timeline(entity, before_order, after_order, cursor)` — windowed change history (newest-first page)
- `retrieve(scope, query, k)` — semantic top-K over episodes/segments
- `search(query, k)` · `neighborhood(entity, hops=1, cap)` — entity search · KG 1-hop
- *(no `list_all` / unbounded dump — bounding is enforced by the API surface itself)*

**Writes** (the only mutators; encode the two write paths + retract from §4):
- `ingest_episode(chapter, content_hash)` → immutable episode (mints a new revision on hash change)
- `resolve_entity(name, kind)` → the cross-kind resolver (`#43`)
- `append_fact(entity, attr|relation, value, valid_from, source_episode)` · `close_fact(... valid_to)`
- `retract(episode_revision, dropped_facts)` → transaction-time close (Path B; reuse KG's
  `remove_evidence_*`, build the glossary equivalent)
- `fold_canonical(entity)` → trigger the bounded snapshot fold (the `canonical_dirty` mechanism)

### The invariant (this is what prevents the next refactor)

> **INV-KAL — no service reads or writes the glossary EAV or the KG (Neo4j) except through the KAL.**
> No direct `entity_attribute_values` / Neo4j queries outside the owning services; no new bespoke
> per-consumer read endpoint. Enforce it like the gateway/provider invariants — a `scripts/` lint that
> fails on a direct glossary/KG table read from a consumer service. Migrate the current outliers (wiki
> direct-EAV read, enrichment full-book read) onto the KAL as part of this work.

### Why this future-proofs (the user's ask)

- **The temporal change is absorbed behind the KAL.** v1 of the contract == the **"current projection"**
  (today's bounded latest-state reads — already what consumers do). Temporal is an **additive** `as_of`
  parameter + the new write verbs. Consumers opt in; nobody is forced to refactor.
- **Every FUTURE model change** (new attribute semantics, new storage engine, new summary strategy)
  lands inside the KAL implementation, behind the stable contract. **No coordinated N-service refactor
  ever again** — the blast radius is permanently reduced to one layer.
- **Bounding is structural, not a convention** — because the API has no unbounded read, no consumer can
  reintroduce context bloat.

### Home: a NEW typed knowledge-gateway service (DECIDED 2026-06-29)
- The KAL is **a dedicated, typed knowledge-gateway service** federating glossary-svc (SSOT projection)
  + knowledge-svc (KG) behind **one versioned, typed contract** — built for **all** consumers and
  transports, **not only MCP**. The existing federated MCP tools (`glossary_search`,
  `kg_graph_query(as_of_chapter)`, `kg_entity_edge_timeline`) become **one client of the KAL**, not the
  contract itself — so non-agent paths (composition, enrichment, wiki, translation, FE) get the same
  typed contract with stronger typing/versioning than ad-hoc MCP tool schemas.
- The existing **`glossary_client` / `knowledge_client`** become thin adapters that call the KAL;
  ownership of the data stays with the SSOT services, the KAL owns the *contract*.
- Promoted from an open question (Q9) to a **load-bearing pillar**: build the KAL FIRST (contract +
  current-projection), migrate the direct-DB outliers (wiki EAV, enrichment full-book) onto it, then
  evolve the bi-temporal substrate behind the frozen contract.

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

## 8B. Codebase reality — VERIFIED (glossary ≠ KG; §8 corrected)

Three read-only agent sweeps verified the "builds-on" claims against code. **Headline correction: §8
over-claimed and wrongly treated glossary + KG as symmetric. They are in completely different states**
— the KG (Neo4j) is **~half-built** toward this design; the glossary (Postgres EAV) is a **flat
overwrite store with none of it.** Net-new scope must be split per side.

### Per-element reality

| Spec element | **KG (knowledge-svc, Neo4j)** | **Glossary (glossary-svc, EAV)** |
|---|---|---|
| **bi-temporal fact** | ✅ has `valid_from/valid_until` + a separate read-axis `from_order/chronological_order` — but the validity is **wall-clock transaction-time**, NOT a chapter-ordinal valid-time, and the two axes are **not unified on one fact** (`facts.py:104-112`, `relations.py:99-104`) | ❌ **none.** EAV is `UNIQUE(entity_id, attr_def_id)`, **in-place OVERWRITE**, zero `valid_*` columns (grep: 0 hits). History only out-of-band (`extraction_audit_log`, `entity_revisions`) — not a queryable fact store |
| **invalidate-not-delete** | ✅ **built + proven** — `invalidate_fact`/`invalidate_relation` keep rows, default reads filter `valid_until IS NULL`, L7 `single_active` does atomic close-prior-then-open-new (`relations.py:190-201`) — but only wired for L7/user, **not driven from extraction** | ❌ none (only enrichment soft-delete, a different mechanism) |
| **RETRACT (Path B)** | ✅ **already exists** — `remove_evidence_for_natural_key`/`remove_evidence_for_source` + zero-evidence cleanup (`provenance.py:63-66`, `facts.py:469`, `events.py:828`). The #42 "can't retract" is **false for KG** → REUSE it | ❌ **confirmed absent** — writeback only CREATE/MERGE (fill/overwrite/append/summarize); a dropped attribute is never closed. The #42 gap is **glossary-only**; build retract here |
| **folded canonical** | hierarchical `chapter→part→book` summaries, content-hash-cached (`level_summaries.py`, `summary_processor.py`) = BooookScore's *hierarchical-merge* leg ✅ — but **book-structural (needs a "part" format imported books lack), overwrite per (level,model), not per-entity, not ordinal-stamped** | `#26/#7` `summarize` canonical: bounded (≤2000 runes) LLM resynthesis from a **bounded** raw-item subset (✅ no bloat) + `canonical_dirty` fold-trigger ✅ — but **per-(entity,attribute), single-column OVERWRITE, no snapshot/ordinal/history** |
| **episode store** (immutable, sealed, revisioned, embedded) | closest = `:Passage` — embedded + content-hashed, but **MERGE-in-place (mutable), no revision chain, no sealed `char_range/token_count/ingested_at`** (`passages.py`) | ❌ none |
| **evidence/quote citation** | chapter pointer only (`source_chapter`, `EVIDENCED_BY→ExtractionSource`) — **no exact quote stored** | ✅ `evidences` table has the **quote + chapter** (`original_text`, `chapter_id`, char offsets) |
| **as-of read** | ✅ ~70% — event/fact spoiler-window via `before_order`/`from_order`, paginated timeline + filters (#12/#15) | ❌ no temporal projection possible (flat current value) |
| **entity `version`** | optimistic-concurrency / ETag counter, **overwrites in place, keeps NO prior state** (`entities.py:136,297`) — NOT a transaction-time version | n/a |
| **resolve-on-ingest** | ✅ idempotent `merge_entity` + alias/provenance accumulation | ✅ `findEntityByNameOrAlias` + cross-kind merge `#43` (validated: re-extract → 0 dups) |

### Net-new scope, split by side

- **KG side = mostly WIRING + one schema change** (a head start): (a) add a **chapter-ordinal valid-time**
  axis and **unify** it with the existing `from_order` so a fact carries *story* `valid_from/to_ordinal`
  **and** *system* `created/invalidated` (today's `valid_*` is the latter); (b) **drive the existing
  invalidate + retract primitives FROM the extraction path** (Path A close-prior, Path B
  `remove_evidence_*`), not just L7/user; (c) store the **quote** on KG citations; (d) add the
  **per-entity ordinal-stamped canonical snapshot** (the summary tree is structural, not per-entity).
- **Glossary side = MOSTLY NET-NEW substrate** (the heavy lift): the **entire bi-temporal fact store**
  (episodes + `valid_from/to_ordinal` + `created/invalidated_at`, append not overwrite), the **retract
  write path** (absent today), and a **per-entity append-versioned canonical** (the #26/#7 bounded
  resynthesis + dirty-fold is a good *foundation* but is overwrite/per-attribute). The `evidences`
  quote table + the cross-kind resolver are the parts already in place.

### Migration is the EASY part — the read side is essentially ready (all 4 consumers verified)
Every consumer reads glossary/KG through **stable, bounded endpoints whose latest-state result IS the
"current projection."** And the read-side temporal axis **largely already exists**:

| Consumer | Bounded? | As-of already? | Migration |
|---|---|---|---|
| **composition** (biggest reader) | ✅ top-K (present 20, timeline 50, lore 40, refs 6); only `_cast_roster` reads ~full glossary (id+name, `limit=100`) | ✅ **already** — `timeline before_order/after_order`, `fact_for_check at_order`, entity detail `valid_until IS NULL` | **LOW** — stable HTTP, already temporal-parameterized |
| **chat** | ✅ MCP `glossary_search`/`get_entity`/bounded `build_context` | ✅ **KG side already** — `kg_graph_query(as_of_chapter)`, `kg_entity_edge_timeline`; glossary tools latest-only | **LOW** |
| **wiki** | ✅ per-entity attrs + 1-hop KG ≤200 + ≤8 passages (entity batch ≤50) | ❌ latest-only (spoiler handled downstream) | **LOW** — current snapshot = natural projection |
| **lore-enrichment** | ⚠️ MIXED — KG passages top-5 + output top-K, but the **glossary canon read pulls the full book** (`list_entities`, cached, filtered by name in-process) | ❌ latest-only | **LOW–MED** — the full-book read is served by the current-projection default; as-of is additive |

**Conclusion (all 4 verified):** the "current-projection + opt-in temporal API" migration needs **no
bespoke per-consumer rework** — the consumers that need an as-of axis (composition, chat-KG) **already
expose it**, and the lone full-ish read (composition/enrichment `list_entities`) is trivially served by
the current-projection default. **The work is the write-side substrate (§ above), not the readers.**

> **Spec correction:** §8 ("the new build is mostly episode store + columns + FE") **understated the
> glossary lift** and **double-counted retract** (already on KG). Treat §3.2/§3.3 as **net-new for
> glossary, build-on for KG.** §6's "one mechanism, two surfaces" → **two mechanisms converging on one
> contract** (the §6C API), built on very different substrates.

## 9. Decisions — CLARIFY RESOLVED (2026-06-29)

> ⚠→🔒 **Reopened by §11, RE-LOCKED by §12.** The §11 edge-case review showed decisions **2, 4, 6, 7,
> 8, 9** were under-specified / rested on an unsafe "reuse the existing primitive" assumption. **§12.6
> re-locks all six** against designed mechanisms (ordinal-aware interval-split, in-tx projection, fact
> natural key, chain re-stitch, per-substrate `as_of` gating, fact-chain merge + `split_entity`).
> Decisions 1, 3, 5 stand unchanged. **Read §9 → §11 → §12 as one arc**; §12 is the BUILD-ready design.

1. **Episode granularity** → **per-chapter** episode; sub-chapter token-window only when a chapter
   exceeds the model context (reuse the existing `context_budget` windowing). 🔒
2. **Fold cadence** → **debounced batch**: mark `canonical_dirty` on each fact change; fold at job-end
   / every K chapters (NOT per-chapter — too costly). Plus the §9B **periodic re-ground**: every M
   folds (or on a drift signal), rebuild the canonical *from facts* (bounded retrieval) instead of
   refine-from-prior — kills accumulation drift. 🔒
3. **`valid_from` source** → **chapter ordinal**, reusing the KG's existing `from_order`/`event_order`
   reading axis. Detected in-story time (`event_date_iso`) is a later advanced follow-up. 🔒
4. **Storage** → **a dedicated append-only `entity_facts` table is the SSOT** (cols: `entity_id`,
   `attr|relation`, `value`, `valid_from_ordinal`, `valid_to_ordinal`, `created_at`, `invalidated_at`,
   `source_episode_id`, `cardinality`); **the existing EAV becomes a materialized "current" projection**
   (latest-valid) so existing reads + the KAL current-projection keep working unchanged. A new
   `episodes` table holds the immutable, content-hash-revisioned, embedded units. **KG side:** add a
   **story-ordinal valid axis** to the existing edge props (today's `valid_from/until` is wall-clock
   transaction-time; unify with `from_order`). *(decided 2026-06-29)* 🔒
5. **Migration** → **cold-start seed**: existing flat entities become one open fact
   (`valid_from = first-seen`); **no history backfill** (append-only tolerates it; optional later
   reconstruction from `entity_revisions`/`extraction_audit_log`). 🔒
6. **Invalidation policy** → **per-attribute `cardinality`; DEFAULT single-valued (supersede)** — a new
   value CLOSES the prior in valid-time (`境界: 武者 → 黄极境 @ch.500`); multi-valued attrs (`aliases`,
   tags) are flagged explicitly to coexist. **Reuse the KG `single_active` (L7) precedent**, which
   already does atomic close-prior-then-open-new. *(decided 2026-06-29)* 🔒
7. **Retract trigger** → **content-hash-gated**: a text edit mints a new episode revision → **diff +
   RETRACT** (transaction-time close the facts the new revision dropped); a same-text re-run (better
   model/prompt) is **update-only, no retract** (avoid LLM-nondeterminism churn). **Reuse KG's
   `remove_evidence_*` + zero-evidence cleanup**; build the glossary EAV/`entity_facts` equivalent
   (net-new there). 🔒
8. **Translation** → **as-of-chapter injection** (translate ch.N against state `valid_from ≤ N`,
   spoiler-free) **+ immutable-once caching** (translate each immutable canonical/segment summary once,
   re-translate only on a new revision). Bound the one full-book read (composition/enrichment
   `cast_roster` `list_entities`) via the KAL. 🔒
9. **KAL home** → **a NEW typed knowledge-gateway service** federating glossary-svc (SSOT projection) +
   knowledge-svc (KG) behind one versioned, typed contract that serves **all** consumers — **MCP is one
   client of it, not the whole contract** (we build for more than MCP). Add the `scripts/` lint that
   enforces **INV-KAL** (no direct glossary-EAV/Neo4j read outside the owning services). **Build order:**
   freeze the KAL contract → build KAL + current-projection → migrate the direct-DB outliers first (wiki
   EAV read, enrichment full-book read) → then composition opts into `as_of`. The bi-temporal substrate
   evolves *behind* this frozen contract. *(decided 2026-06-29)* 🔒

## 9B. Production risks & mitigations (research-grounded)

Incremental/temporal systems have well-documented failure modes. The spec must design against them.

| Risk (from literature) | Why it bites us | Mitigation (baked into this design) |
|---|---|---|
| **Error accumulation in fold-forward summaries** — "as the stream lengthens, errors compound"; drift stages: accurate → misbinding → fabrication (long-doc summarization papers) | a naive `canonical_n = LLM(canonical_{n-1}+new)` over **thousands** of folds drifts/hallucinates | **(a) Facts are the SSOT; the canonical is a REGENERABLE CACHE** (atomic, evidence-cited facts → the canonical can always be rebuilt from them). **(b) Periodic RE-GROUND**: every K folds (or on drift), rebuild the canonical via **bounded retrieval of top facts** (map-reduce), not from the prior summary — resets drift. **(c)** canonical claims **cite facts**; a validator can check. |
| **Entity-resolution degrades at scale** — prompting the LLM with all prior entities is impractical & drifts (semantic drift: "Apple" co/fruit) | this is *exactly* our extraction bloat finding, now a general law | our resolver is **DETERMINISTIC** (normalized-name fold + cross-kind merge `#43`), **not** LLM-prompt-all-entities → sidesteps the degradation entirely. Known-entities injection stays **bounded** (≤50, by frequency). |
| **Temporal ambiguity → indexing errors** — time-varying facts merged under one node *without* temporal separation | a character's 境界/relationships change → collapsing them corrupts the entity | **mandatory valid-time axis** — a changing value OPENS a new fact + closes the prior in valid-time; never a single overwritten value. |
| **Stochastic LLM → non-stable / non-exhaustive KG** — re-runs differ | a routine re-extract could churn/retract facts the model just didn't re-mention | **content-hash-gated retract** (Q7: same-text re-run = update-only, no retract) + **idempotent MERGE** → re-runs CONVERGE (validated: run #2 → 0 dups). |
| **Temporal conflict/redundancy in retrieval** (T-GRAG) | old + new facts both retrieved → confused answer | **as-of queries** (§5/§5B) project a single consistent slice; default = latest-valid. |

> **The keystone property:** **atomic evidence-cited FACTS are the source of truth; episodes,
> segments, and the canonical snapshot are all DERIVED + REGENERABLE.** This is what makes the whole
> design robust — any drift in a derived layer is *recoverable by rebuilding from facts*, which a flat
> `description` field can never offer. Design every derived layer as a rebuildable projection, never
> as a place where truth lives.

## 10. Why this is the right call

- **Append-only / immutable** → never rewrite old data → safe under re-runs (validated: re-extract →
  0 dups) and concurrency; scales linearly forever.
- **Bounded context everywhere** → O(1) LLM cost per chapter; a 4,000-chapter book is just 4,000
  cheap folds, never one impossible merge.
- **Bi-temporal** → time-travel, development view, spoiler-free translation — features a flat model
  *cannot* offer.
- **Proven** → it's Graphiti + BooookScore, not speculation.
- **Composes** with the clean-extraction work we just shipped and the merge we already built.

## 11. Edge-case review — gaps to close before BUILD (2026-06-29)

Five independent adversarial agents probed this spec against the **actual code** it claims to build
on (`merge_handler.go`, `relations.py`/`facts.py`/`provenance.py`, `canonical_summary_handler.go`,
`resummarize.py`, `plan.py`, the glossary/enrichment clients). The architecture **holds** — append-only
bi-temporal facts as SSOT with derived/regenerable projections is the right call. But the review found
**~14 HIGH gaps that collapse to FOUR root causes**, and showed several §9 decisions marked `🔒` are
**not actually resolved**. **Status downgraded from "DESIGN COMPLETE" → these must be designed first.**
Convergence (a gap found independently by ≥2 agents) is flagged — it is the strongest signal.

### Root cause A — "REUSE the existing primitive" is unsafe (the spec's most repeated, most load-bearing error)
The existing KG/merge primitives were built for a **wall-clock transaction-time, flat-overwrite,
monotonic-user-edit** world. The new model is **chapter-ordinal valid-time, append-only, out-of-order**.
"Reuse `single_active` / `remove_evidence_*` / `#43` / content-hash identity" is wrong without redesign.

| # | Gap | Sev | Conv. | Resolution to bake in |
|---|---|---|---|---|
| A1 | **Merge can't combine two fact HISTORIES.** `#43`'s EAV repoint is a `UNIQUE`-collision dodge (`merge_handler.go:321-330` `NOT IN (SELECT attr_def_id…)`) — on a fact store it orphans the loser's whole interval chain. "`#43` is the entity-resolution step, done+validated" (§4/§6/§8) is **false** for the new substrate. | **HIGH** | ×2 (merge, concurrency) | Define a **fact-chain merge**: repoint ALL loser facts (no collision dodge), re-sort the per-attr chain by `valid_from`, re-derive `valid_to` = next fact's `valid_from`, invalidate-not-delete on overlap with a deterministic tiebreak, journal the moved **fact** ids, then rebuild the projection. Merge is **net-new**, not "done via #43." |
| A2 | **Out-of-order ingestion inverts intervals.** KG `single_active` close (`relations.py:190-201`) closes *any* open instance by wall-clock `datetime()`, **zero ordinal awareness** → back-filled ch.300 closes the still-correct ch.500 fact. Q5 backfill + §2 ATOM parallel-merge *guarantee* out-of-order arrival. | **HIGH** | ×2 (bi-temporal, fold) | The close must be an **ordinal-aware interval-split**, a NEW primitive: opening F@v sets the containing fact's `valid_to=v` and F's `valid_to` = next fact's `valid_from` (open only if none later). Same fix needed on the KG side the moment extraction drives it. |
| A3 | **Retract orphans the valid-time close it caused.** `remove_evidence_*` deletes F_new but never reopens F_old that F_new superseded — and the extraction path is *deliberately* coded never to resurrect (`relations.py` comment). → as-of read returns nothing. §9B keystone does **not** save this (the fact layer itself is corrupt). | **HIGH** | bi-temporal | Add **Path-B step B.3.5 — re-stitch the chain around every retracted fact** (reopen predecessor to F_new's `valid_to`). Better: model `valid_to` as *derived* (= next surviving fact's `valid_from` via view/trigger) so retract auto-restitches. |
| A4 | **Oscillating single-valued attrs collide.** Content-hash fact identity (`facts.py:89`) MERGEs ch.100 `宗门` and ch.300 `宗门` into one node; the intervening `[200,300)=秘境` is orphaned. Q6's cited "re-assert = no-op" (`relations.py:181`) is **exactly wrong** for recurring values. | **MED** | bi-temporal | Fact identity for `entity_facts` must include **interval origin** — key on `(entity_id, attr, value, valid_from_ordinal)` or `(…, source_episode_id)`, not `canonical_content`. "Idempotent re-run = no-op" re-scoped to "same value *from the same episode*." |
| A5 | **Dual-substrate `as_of` returns incomparable data.** KG `valid_until` is wall-clock; `get_facts(as_of=N)` returns story-time-correct glossary rows + transaction-time-contaminated KG edges behind ONE contract. `from_order` is NULL on legacy/chat facts → silently non-exhaustive (`facts.py:108-112,363-374`). Build order (§9.9) never sequences the KG ordinal-unify **before** exposing `as_of`. | **HIGH** | KAL | Version-gate `as_of` **per substrate capability**: until KG carries a unified story-ordinal valid-time, KAL refuses/marks KG `as_of` as `temporal_unsupported` (degrade-safe). Add to build order: unify KG valid-time **before** `as_of` on the KG branch. |

### Root cause B — the canonical's identity is unresolved: immutable series **vs** regenerable cache
§3.3 says snapshots are "append-only + ordinal-stamped" (immutable series); §9B's keystone says the
canonical is a "REGENERABLE CACHE." **These are mutually exclusive.** The design *needs* the cache model
to be correct (out-of-order facts, re-ground, algorithm evolution); §3.3/§9-dec-5/§10 forbid the rewrites
it implies. **Resolve this ONE contradiction first** and B1–B4 below become tractable.

| # | Gap | Sev | Conv. | Resolution |
|---|---|---|---|---|
| B0 | **The root contradiction itself** — immutable snapshot series vs regenerable cache. | **HIGH** | ×2 (fold, KAL) | Commit to **lazy, versioned, regenerable cache**: snapshots are recomputable performance rows keyed by `(entity, ordinal, fold_algo_version, fact_coverage_txid)`, **never truth**. Delete/qualify "append-only + ordinal-stamped" in §3.3. As-of below the fold head **always** projects from facts. |
| B1 | **"Bounded retrieval of top facts" is undefined** — top-K drops the long tail (the "loss of development" we exist to prevent); all-facts = the monolith. Worse: the shipped #26/#7 fold already feeds the **entire** active raw-item set with **no input cap** (`resummarize.py` + `extraction_handler.go:1601`) → §8B's "bounded raw-item subset (✅ no bloat)" is **already false** (only the *output* is bounded). | **HIGH** | fold | Re-ground = **hierarchical ordinal-bucketed tree over facts** (per-arc/per-N-chapter buckets, each a bounded folded sub-summary, then map-reduce the sub-summaries — the `summary_processor.py` tree, made per-entity + ordinal not book-structural). State the bucket key, per-bucket bound, reduce step. |
| B2 | **"Drift signal" is a TODO disguised as a 🔒 decision** — appears once, never defined; detecting drift needs the very rebuild it gates (circular). | **HIGH** | fold | Either drop the branch and commit to deterministic **every-K-folds** re-ground, or define a *cheap* proxy (invalidation-count / new-fact-count since last re-ground), never the full rebuild. |
| B3 | **Out-of-order facts silently corrupt the as-of snapshot SERIES.** Path-B "re-fold snapshots that CITED episode N" misses a *new* ch.300 fact — by definition it has no citation in the pre-existing snapshots@≥300. | **HIGH** | fold | Falls out of B0: snapshots below the fold head are stale-on-newer-fact → rebuild-on-read from facts. Drop "snapshot series time-travel" or make it lazy. |
| B4 | **Poison fact wedges an entity forever.** `canonical_dirty` is a bare boolean (`canonical_summary.go:30`); a fold failure never clears it → re-fails every job-end, no backoff/quarantine. The proposed `LLM(canonical_{n-1}+batch)` is *worse* (poison persists into the next input). | **MED** | fold | Add `fold_attempts`/`fold_failed_at` + backoff (reuse the KG `RETRY_BUDGET=3`); after N fails, quarantine + surface "canonical unbuildable" in FE. Keystone holds only if one fact can't permanently block regeneration. |

### Root cause C — flat-store concurrency/idempotency machinery does NOT transfer (assumed, not specified)
The flat store is safe via three concrete mechanisms the spec never carries forward: per-book
`pg_advisory_xact_lock` (`extraction_handler.go:611`), `writeback_key`+`extraction_writeback_log`
idempotency (`:623,:1002`), fingerprint compare-and-clear on `canonical_dirty`
(`canonical_summary_handler.go:178-192`). §10's "safe under re-runs and concurrency" is an **inherited
claim that doesn't survive the storage change** — and in two places (C2, C3) the new model *removes* a
guard the current code has.

| # | Gap | Sev | Conv. | Resolution |
|---|---|---|---|---|
| C1 | **Materialized "current projection" has no defined refresh mechanism.** The WHOLE migration story rests on it. Async → every backward-compat reader sees stale current state; a real Postgres matview can't refresh per-row + `REFRESH CONCURRENTLY` is a full rebuild (catastrophic per-chapter). | **HIGH** | ×2 (concurrency, KAL) | Specify: **app-maintained "current" row upserted in the SAME tx as the fact append** (extend the existing per-chapter writeback tx). Invariant: "no fact commits without its projection upsert in-tx." Rebuild-from-facts repair job as backstop. |
| C2 | **Append-only breaks idempotency.** `entity_facts` has no natural key → re-running Path A appends **duplicate** facts into the SSOT. The "validated 0-dups" (§9B) was on the flat `UNIQUE(entity_id,attr_def_id)` store; the spec itself admits Run #2 was a cache replay. | **HIGH** | concurrency | `UNIQUE(entity_id, attr|relation, value_hash, valid_from_ordinal, source_episode_id)` + `ON CONFLICT DO NOTHING`; carry `writeback_key` forward to gate the Path-A append. Re-run the "identical re-extract → 0 *fact* rows" test (does not transfer). |
| C3 | **Append-racing-the-fold lost-wakeup — spec REGRESSES an existing guard.** New `fold_canonical` is a bare "mark dirty → fold"; the shipped #26/#7 already solved this with fingerprint compare-and-clear. | **HIGH** | concurrency | Mandate the **existing compare-and-clear**: capture a fact-set fingerprint at read, clear dirty only if unchanged at write (direct reuse of `internalWriteCanonical`'s `md5(...)` clause). |
| C4 | **Merge must move append-only fact history under the existing locks** (the concurrency face of A1) — `mergeOne` repoints a fixed child-table list that won't include `entity_facts`/`episodes`; a fact-append racing a merge orphans the fact on the soft-deleted loser; un-journaled fact moves break the reversible-merge invariant. | **HIGH** | ×2 (merge, concurrency) | Extend `mergeOne` + `merge_journal` to repoint/journal `entity_facts`+`episodes`; post-merge valid-time reconciliation; **mandate ALL KAL fact writes take the same per-book advisory lock** as `mergeExtractedEntity`. |
| C5 | **Concurrent Path-B re-extract** — no `UNIQUE(chapter,content_hash)`, no revision allocation, unspecified lock → double-mint revisions / double-retract. | **MED** | concurrency | `UNIQUE(chapter_id, content_hash)` + `ON CONFLICT DO NOTHING`; Path B takes the same per-book lock; diff+retract runs inside it. |
| C6 | **Crash mid-pipeline strands a sealed empty episode.** §4-A is 5 steps crossing a non-transactional LLM call; crash after step 1 leaves an immutable episode with no facts (and re-run may re-mint it). | **MED** | concurrency | Episode-seal + `writeback_key` reservation in tx-1 with a `pending→reconciled` status; reconcile in tx-2 keyed by the same `writeback_key`; `UNIQUE(chapter,content_hash)` makes re-run resume not re-mint. |

### Root cause D — the KAL contract has unbudgeted shape gaps
| # | Gap | Sev | Conv. | Resolution |
|---|---|---|---|---|
| D1 | **Half-open interval semantics undefined — 3 conflicting conventions.** §5 `valid_from ≤ N < valid_to`, §6B `valid_from ≤ N`, KG code inclusive-lower/no-upper (`facts.py:374`). `valid_to` sentinel for an open fact is undefined → `N < NULL` **excludes the current value from every as-of query**. Directly defeats spoiler-free translation. | **HIGH** | bi-temporal | LOCK one convention: half-open `[valid_from, valid_to)`; open fact `valid_to=NULL`=+∞; predicate `valid_from ≤ N AND (valid_to IS NULL OR N < valid_to)`; supersede sets `old.valid_to = new.valid_from`. Add a `valid_to_eff = coalesce(valid_to, INT_MAX)` indexable column (reuse KG's `INT64_MAX` null-sink). Fix §6B-2. |
| D2 | **No `split_entity` / un-merge verb.** Append-only makes a wrong CJK-name merge **permanent**; `revertMerge` is LIFO journal-replay that can't unwind interleaved history. §6D writes-list has none. | **HIGH** | merge | Add `split_entity(winner, facts→new, by source_episode provenance)` — re-attribute by `source_episode_id` as a new transaction-time event (invalidate-not-delete preserved). Design now; it's the inverse of the load-bearing merge. |
| D3 | **Name/aliases are flat EAV, not bi-temporal** (`entityNameAndAliases` reads `code IN ('name','aliases')` as flat rows). → rename-at-ch.4000 spawns a spurious entity every time AND **as-of name (§6B's own anti-spoiler example) is literally impossible.** | **HIGH** | merge | Model name+aliases as **multi-valued bi-temporal facts** (`valid_from_ordinal`); resolver matches the full across-time alias set (ch.4000 mention resolves to the ch.1 entity, no merge); as-of read returns the canonical name valid-at-N. |
| D4 | **"No unbounded read" forbids the composition planner's legitimate full-cast need.** The planner injects the **entire roster** into the L2 prompt + uses it as the resolver index (`plan.py:160-174,286-290`); a top-K drops characters from both. AND `_cast_roster` already **silently truncates at 100** (`glossary_client.py:80`, ignores `next_cursor`). | **HIGH** | KAL | Add a **bounded-but-complete** primitive: `roster(book, fields=[id,name], cursor)` — cursor-paginated to completion, projection-restricted (never full attributes). Carve into INV-KAL as allowed. **Fix the existing truncation** (`_cast_roster` must drain the cursor) regardless of the KAL. |
| D5 | **Cold-start seed may be lossy.** Q5 "one open fact valid_from=first-seen" never says **what value** it carries. If first-seen-*value* → the projection regresses to ch.1 state, not today's overwritten current value → "consumers keep working unchanged" is **false on day one**. | **MED** | KAL | Seed the open fact with the entity's **current flat EAV value**, `valid_from=first-seen` as the *bound* only. Migration test: `projection(entity) == flat_eav(entity)` for all entities. |
| D6 | **INV-KAL lint only half-enforceable.** A grep catches direct table reads but **not** the bespoke-HTTP-endpoint outliers §6D itself lists (consumers calling `/internal/.../entities` is an ordinary HTTP call, indistinguishable from a KAL call). | **MED** | KAL | Two mechanisms: (i) grep lint for direct table/Cypher reads (owning-svc + KAL allowlisted); (ii) **HTTP-surface check** — lint that no consumer client targets the owning services' `/internal/*` knowledge endpoints. Until both, document as "table-read-enforced, HTTP-surface tracked" + a DEFERRED row. |
| D7 | **Content-hash-gated retract can't self-heal a same-text hallucination** (a model upgrade can't drop a prior hallucinated fact without editing source). Deliberate, but the spec doesn't flag it's **permanent**. | **MED** | bi-temporal | Keep no-auto-retract-on-same-text default; add an explicit `allow_retract_on_remodel` force path keyed on model/prompt-version change (off by default). Document the force-revision escape valve. |
| D8 | **Translation immutable-once cache goes stale against re-ground.** §6B "translate each immutable snapshot once" vs §9B "rebuild the canonical every K folds" → re-ground rewrites the canonical with no chapter edit → cached translation stale, no "new revision" fired. | **MED** | KAL | Key the translation cache on the **bounded unit's own content-hash** (not "chapter revision"); re-ground that changes content → cache miss; identical content → hit. Falls out of B0 (snapshot = versioned cache identity). |
| D9 | **Multi-valued attr truncation in the prose canonical.** 200 aliases > `canonicalMaxRunes=2000` → 422-reject (→ wedges via B4) or silent alias drop in the default "who is this now" card. | **MED** | fold | Multi-valued attrs are **structured, not summarized** — keep aliases/tags/appears_in as paginated `entity_facts`, queried directly; the prose fold covers only single-valued/narrative attrs and *references* the list ("known by 200 aliases — see list"). |

### Cross-cutting analysis-integrity corrections (fix the prose, not just add findings)
- **§4/§6/§8 "the cross-kind merge `#43` is the entity-resolution step — done + validated"** → **FALSE for the new substrate.** `#43` is validated for the flat overwrite store; merge over append-only fact history is **net-new** (A1/C4/D2). Re-scope it.
- **§8B "summarize reads a bounded raw-item subset (✅ no bloat)"** → **already false** — only the output is bounded; the input set is uncapped (B1). Fix the claim and cap the input.
- **§9B "deterministic resolver sidesteps entity-resolution drift entirely"** → **overclaims.** It sidesteps *prompt-context* drift only; CJK aliases/honorifics that don't normalize-equal still need a **merge** (→ A1/D2/D3). Rewrite the row.
- **§10 "safe under re-runs and concurrency"** → **inherited, not designed** (root cause C). Replace with a pointer to the new **§9C concurrency contract**.
- **Things the review confirmed GENUINELY SOUND (do not touch):** facts-as-SSOT/derived-regenerable keystone; KG retract reuse scoped to glossary-net-new (Q7 correctly identifies #42 is false for KG); content-hash-gated retract vs churn (the *default* is right); cross-item fold isolation (`asyncio.gather(return_exceptions=True)`); the compare-and-clear dirty guard (C3 is about *not dropping* it); idempotent no-op re-fold on unchanged raw set; composition/chat KG side already as-of-parameterized.

### What this means for status
The spec is **architecturally validated but not implementation-ready.** Before BUILD:
1. **Resolve B0 first** (immutable series vs regenerable cache) — it unblocks B1/B3/D8.
2. **Add a §9C "Concurrency & idempotency contract"** (root cause C: in-tx projection upsert, fact natural key, advisory-lock-all-writes, compare-and-clear fold, episode `pending→reconciled`).
3. **Re-scope merge as net-new** (A1/C4/D2/D3) — fact-chain merge + `split_entity` + bi-temporal name/aliases; the "#43 = done" claim is the single most load-bearing error.
4. **Lock the interval convention (D1)** and make the close **ordinal-aware** (A2) + **retract chain-restitching** (A3).
5. **Gate `as_of` per-substrate** (A5) and add the **bounded-complete roster** primitive (D4, + fix the live truncation).
6. Downgrade the affected §9 `🔒` decisions (2, 4, 6, 7, 8, 9) to ⚠ pending these resolutions.

> **§12 closes all of the above.** Each §11 gap now has a concrete, implementable resolution below; the
> §9 decisions are **re-locked** against §12.

## 12. Hardened resolutions — the implementable design (2026-06-30)

This section turns the §11 gap-list into **buildable design**: schemas, predicates, algorithms, and
invariants precise enough that BUILD does not re-derive them. Organized by the four root causes. Every
§11 ID is closed here (the `→` tag maps each resolution back to its gap).

### 12.0 The single foundational invariant (read first)

> **INV-FACTS — atomic, evidence-cited FACTS in `entity_facts` are the ONE source of truth. Every other
> layer — the EAV "current" projection, the canonical snapshot, episode/segment summaries, translations,
> the KG edge view — is a DERIVED, REBUILDABLE cache.** No truth lives outside `entity_facts`. Any
> derived layer may be dropped and recomputed from facts without data loss. This is what makes the design
> robust under drift, re-runs, and out-of-order ingestion — and it is the lens that resolves B0, A3, C1.

Corollary: **a derived layer must never be the place a write lands.** Writes append/close/retract *facts*;
derived layers are *reactions*. Two reactions are **synchronous-in-tx** (the EAV projection, §12.2.1) and
the rest are **debounced + rebuildable** (canonical, translations).

### 12.1 Canonical = lazy, versioned, regenerable cache  → closes B0, B1, B2, B3, B4, D8, D9, F6

**B0 decision (LOCKED): the canonical is NOT an immutable append-only series. It is a versioned cache.**
Delete "append-only + ordinal-stamped" framing from §3.3. A canonical snapshot is a recomputable row:

```
canonical_snapshot(
  entity_id, attr_scope,           -- 'narrative' (folded prose) — multi-valued attrs are NOT here (D9)
  as_of_ordinal,                   -- the chapter this snapshot projects (the head, or any pinned N)
  content, content_hash,           -- the bounded prose (≤ canonicalMaxRunes)
  fold_algo_version,               -- bumped when prompt/model/strategy changes (F6)
  fact_coverage_txid,              -- max(created_at txid) of facts folded in (staleness key, B3)
  built_at
)
PRIMARY KEY (entity_id, attr_scope, as_of_ordinal, fold_algo_version)
```

- **Read (B3, F6):** a snapshot is **valid** iff `fold_algo_version == current` AND no fact with
  `valid_from ≤ as_of_ordinal` has a `created_at` txid newer than `fact_coverage_txid`. Invalid →
  **rebuild-on-read from facts** (it's a cache miss, not corruption). As-of reads **below the fold head
  always project from facts** (§5 predicate, §12.3.1); the snapshot is purely a perf cache for the
  hot "current head" and any explicitly-pinned ordinals. This makes out-of-order/back-filled facts
  (B3) self-healing: the late ch.300 fact bumps the coverage check, every snapshot@≥300 goes stale,
  next read rebuilds. No eager re-fold of old snapshots needed; §4 Path-B step 5 is **deleted** (it
  was keyed on citations the new fact lacks).
- **Diff view (F6):** the FE diff (§7-4) **recomputes both endpoints at the current `fold_algo_version`**
  before diffing, so a delta is story-development, never an algorithm artifact. Never diff across versions.

**B1 — the fold/re-ground is hierarchical, bounded by construction, not "top-K":**
- **Incremental fold (the hot path, every batch):** `canonical_head = LLM(prior_head[bounded] +
  new_facts_this_batch[bounded])`. Bounded because a *batch* of facts is bounded. Cheap, O(1)/chapter.
- **Re-ground (the drift-reset, periodic):** do **NOT** retrieve "top-K facts" (drops the long tail) and
  do **NOT** load all facts (the monolith). Build an **ordinal-bucketed summary tree**: partition the
  entity's facts into fixed **ordinal windows** (e.g. every 200 chapters — mechanical, no arc format
  needed, works on imported books); fold each window into a bounded sub-summary; map-reduce the
  **sub-summaries** (not the facts) into the canonical. This is `summary_processor.py`'s
  `chapter→part→book` tree made **per-entity + ordinal-keyed** (not book-structural). Every level is
  bounded; the long tail survives as window summaries. **Fix §8B's false "bounded raw-item subset"
  claim and cap the #26/#7 fold input** to one window's facts.
- **B2 — drift trigger is deterministic, no circular "drift signal":** re-ground when
  `(folds_since_reground ≥ K)` **OR** `(fact_invalidations_since_reground ≥ J)` — invalidations are
  where incremental-refine most likely drops a superseded value, so they are the cheap proxy. Both are
  counters; neither needs the rebuild they gate. **Drop the undefined "drift signal" wording.**

**B4 — fold failure has explicit state (no infinite re-fail):** add `fold_attempts INT`,
`fold_failed_at` to the dirty mechanism (mirror the KG `RETRY_BUDGET=3` + backoff). After N failures →
**quarantine** the item (stop re-folding) and surface `canonical_status='unbuildable'` in the FE
(degrade-safe — show the structured facts instead of a broken prose card). INV-FACTS guarantees the data
is still readable from `entity_facts`; only the prose convenience is degraded.

**D9 — multi-valued attrs are STRUCTURED, never folded into prose:** aliases / tags / `appears_in` live
as paginated `entity_facts` rows queried directly (§12.5.3). The prose canonical covers only
single-valued/narrative attrs and *references* the list ("known by 200 aliases — see list"). This
removes the 2000-rune-overflow → 422 → wedge path entirely.

**D8 — translation cache keys on the bounded unit's `content_hash`,** not "chapter revision." A re-ground
that changes the canonical changes its hash → cache miss → re-translate; identical content → hit (free).
Re-ground producing a new `(as_of_ordinal, fold_algo_version)` row is the invalidation event. §6B point 1
reworded: snapshots are *immutable per `(ordinal, algo_version)` identity*; a re-ground mints a new
identity — that IS the revision.

### 12.2 §9C — Concurrency & idempotency contract  → closes C1, C2, C3, C4, C5, C6

The flat store's safety came from machinery the new substrate must **inherit explicitly**: per-book
`pg_advisory_xact_lock`, `writeback_key`/`extraction_writeback_log`, fingerprint compare-and-clear. §9C
carries each forward and adds the append-only-specific keys.

**12.2.1 The EAV "current" projection is synchronous-in-tx (C1).** It is **NOT** a Postgres MATERIALIZED
VIEW. It is an app-maintained `entity_attribute_values`-shaped table, **upserted in the SAME transaction
as the `entity_facts` append/close**. Invariant: *no fact commits without its projection upsert in the
same tx* → the projection is always read-consistent with the SSOT, so every legacy/KAL "current" read is
correct with zero skew. A standalone **rebuild-projection-from-facts** repair job exists as the INV-FACTS
backstop (used after merge/split/migration), never on the hot path.

**12.2.2 Fact append is idempotent by a content-addressed natural key (C2).**
```
UNIQUE (entity_id, fact_kind, attr_or_predicate, value_hash, valid_from_ordinal, source_episode_id)
```
`INSERT … ON CONFLICT DO NOTHING`. Re-running Path A for the same chapter appends **zero** new fact rows.
The whole Path-A append is additionally gated by the existing `writeback_key`/`extraction_writeback_log`
short-circuit (reused, not reinvented). **Re-run the validation against the NEW store** — the cited
"run #2 → 0 dups" was on the flat `UNIQUE(entity_id,attr_def_id)` store and does not transfer.
*(Note: `valid_from_ordinal` in the key is what makes oscillation A4 work — a recurring value at a new
chapter is a distinct row, not a content-hash collision.)*

**12.2.3 Fact writes are lock-serialized at their TOCTOU granularity (C3, C4, C5).**
> ⚠ **SUPERSEDED by §12.7.1** — the original "ALL writes take one **per-book** advisory lock" over-locked
> (foreclosing within-book parallelism) and was factually wrong that merge "already uses" that lock. The
> correct model is **per-`(entity, attr)` chain** locks for appends (disjoint entities run in parallel),
> `UNIQUE(book, normalized_name, kind)` for resolver-create, and the existing entity-pair `FOR UPDATE` for
> merge/split. Read §12.7.1.

Still serializes the things that need it — append-vs-merge (no orphaned fact on a soft-deleted loser, C4),
the two-Path-B race (no double-mint/double-retract, C5), append-vs-fold ordering — but at chain/entity-pair
granularity, not book-global, because the idempotent natural key (§12.2.2) + ordinal-aware `maintain_chain`
(§12.3.3) already make disjoint appends safe.

**12.2.4 The fold keeps the existing compare-and-clear (C3).** `fold_canonical` captures a fact-set
fingerprint (`max(created_at)` over the entity's contributing facts) at read; clears `canonical_dirty`
**only if** the fingerprint is unchanged at write (direct reuse of `internalWriteCanonical`'s `md5(...)`
guard). A fact appended between read and write keeps the row dirty → next batch re-folds. **Do not ship
the bare "mark dirty → fold"** — it regresses a guard that already exists.

**12.2.5 Episodes are revisioned + crash-safe (C5, C6).**
```
UNIQUE (chapter_id, content_hash)         -- a re-run with same text resumes, never re-mints (C6)
episode.status ∈ {pending, reconciled}    -- seal+writeback_key reserved in tx-1 as 'pending';
                                          -- facts written + flip to 'reconciled' in tx-2 (same writeback_key)
```
A crash after tx-1 leaves a resumable `pending` episode (not a phantom sealed-empty one polluting
retrieval); re-run finds it by `(chapter_id, content_hash)` and resumes step 4. The LLM call (step 2)
sits *between* the two txs — never inside a DB transaction.

### 12.3 Bi-temporal correctness  → closes A2, A3, A4, D1, D7

**12.3.1 The interval convention is LOCKED (D1):** **half-open `[valid_from_ordinal, valid_to_ordinal)`.**
An open fact stores `valid_to_ordinal = NULL` meaning **+∞**. The canonical as-of-N predicate, everywhere
(fix §5 and §6B to match):
```sql
valid_from_ordinal <= N AND (valid_to_ordinal IS NULL OR N < valid_to_ordinal)
```
A supersede sets `old.valid_to_ordinal = new.valid_from_ordinal` (contiguous: no gap, no overlap).
`valid_to_ordinal` is a **stored column** (maintained by the single chain-maintenance routine of §12.3.3,
NOT computed by a subquery). Add a generated indexable column
`valid_to_eff = coalesce(valid_to_ordinal, INT_MAX)` (`GENERATED ALWAYS AS … STORED` — legal because it
references only the same row's stored `valid_to_ordinal`; reuse the KG `INT64_MAX` null-sink
`_NULL_ORDER_SENTINEL`/`coalesce(event_order, 9223372036854775807)` in `db/neo4j_repos/events.py` — **NOT**
`spoiler_window.py`, which is a fail-closed `-1` ceiling, the opposite sentinel) so the range query is
index-served on `(entity_id, attr, valid_from_ordinal, valid_to_eff)`.

**12.3.2 The close is an ordinal-aware interval-split, a NEW primitive (A2).** This is the single most
important "do NOT reuse the KG `single_active`" point — that primitive closes *any* open instance by
wall-clock `datetime()` and inverts intervals under out-of-order arrival. The correct insert of fact F
with `valid_from = v` on chain `(entity, attr)`:
1. Find `F_prev` whose interval **contains** v (`valid_from ≤ v < valid_to_eff`) → set `F_prev.valid_to = v`.
2. Find `F_next` = smallest `valid_from > v` → set `F.valid_to = F_next.valid_from` (do **not** leave F
   open if a later fact exists).
3. Open (`valid_to = NULL`) **only if** no later fact exists.
This is a proper interval-tree insert; it is correct for backfill, parallel/ATOM merge, and re-import.
**The KG side needs the same fix** the moment extraction drives its invalidation (today's `single_active`
is correct only for monotonic L7/user edits).

**12.3.3 Retract re-stitches the chain (A3) — via ONE chain-maintenance routine.** Path B gains **step
B.3.5**: when fact `F_new` is retracted (transaction-time close via `remove_evidence_*` / the glossary
equivalent), **repair the valid-time interval it occupied** — extend its predecessor
`F_prev.valid_to ← F_new.valid_to` (or to NULL if F_new was the open one), re-close against F_new's
successor if any.

> **LOCKED — stored `valid_to`, single maintainer (resolves the §12.3.1↔§12.3.3 ambiguity).** `valid_to`
> is a **stored** column written by **exactly one** *chain-maintenance routine* `maintain_chain(entity,
> attr)` that, for a given `(entity, attr)` chain, sorts surviving facts by `valid_from_ordinal` and sets
> each `valid_to = next survivor's valid_from` (open the last). This **single routine is the only writer
> of `valid_to`** — the §12.3.2 ordinal-aware close, the §12.4.1 merge reconcile, and this B.3.5 retract
> are **the same routine invoked at three entry points**, not three algorithms. The "trigger" option is
> merely this routine wired as an `AFTER` trigger — never a *second* writer competing with the
> application code (that was the trap). So retract auto-restitches by re-running `maintain_chain` over the
> survivors.

**Retract must never leave a dangling close** — add a test that closes-then-retracts and asserts the
predecessor is current again. INV-FACTS does not save this; the fact layer itself must be correct.

**12.3.4 Oscillation works because identity includes the interval origin (A4).** Resolved by 12.2.2 —
fact identity is `(…, value_hash, valid_from_ordinal, source_episode_id)`, so ch.100 `宗门` and ch.300
`宗门` are **two rows / two intervals**, with `[200,300)=秘境` intact between them. Re-scope Q6's
"re-assert = no-op" to "same value **from the same episode** = no-op." The KG content-hash identity
(`facts.py:89`) is fine for *its* dedup purpose but **must not** be the identity for bi-temporal interval
rows.

**12.3.5 Same-text retract has an explicit escape valve (D7).** Default stays content-hash-gated
(same-text re-run = update-only, no retract — kills churn). Add an opt-in **`allow_retract_on_remodel`**
force path keyed on `extraction_model`/`prompt_version` change (off by default; on for a deliberate
"re-ground this book with model B" job) so a model upgrade *can* clean a prior hallucination. Document the
force-revision workaround. State plainly in Q7 that without this flag, a same-text hallucination is
**permanent** by policy.

### 12.4 Merge & identity over append-only — NET-NEW, not "#43 done"  → closes A1, C4, D2, D3

**Correct the load-bearing false claim:** `#43` is validated for the **flat overwrite store**. Over
append-only fact history, merge is **net-new**. §4/§6/§8 reworded accordingly.

**12.4.1 Fact-chain merge (A1, C4).** `merge_entities(loser, winner)` — **heavy work staged OUTSIDE the
lock; lock held only for the swap (§12.7.2)**:
1. Acquire the **entity-pair** lock (loser+winner `FOR UPDATE`) + the affected per-attr chain locks — NOT
   a book-global lock (§12.7.1). Stage steps 2–4 as a prepared batch outside the lock; take the lock only
   for the final swap + journal (step 5). Chunk large repoints with release/reacquire.
2. Repoint **ALL** loser facts → winner (`UPDATE entity_facts SET entity_id=winner WHERE entity_id=loser`)
   — **no `NOT IN` collision dodge** (facts coexist by design). `source_episode_id` + `valid_*` untouched
   (provenance + intervals preserved).
3. **Per-attribute chain reconciliation:** re-sort the combined chain by `valid_from_ordinal`, re-derive
   each `valid_to` = next fact's `valid_from` (12.3.2). On **overlapping intervals from the two sources**,
   deterministic tiebreak (newest `created_at`, or source-episode priority) → invalidate-not-delete the
   loser fact (transaction-time close), never delete.
4. Rebuild the EAV projection for the winner from the merged latest-valid facts (12.2.1).
5. **Journal the moved FACT ids + every close/invalidation** into `merge_journal` (new columns) so revert
   stays exact.
Extend `mergeOne` to also repoint `entity_facts` + `episodes` (today's fixed child-table list omits them).

**12.4.2 `split_entity` — the inverse, designed now not deferred (D2).** Append-only makes a wrong CJK
merge otherwise **permanent**. `split_entity(source, facts_predicate → new_entity)` re-attributes facts
**by provenance**: facts whose `source_episode_id` resolves to the extracted identity move to a fresh
entity; the move is a **new transaction-time event** (originals get `invalidated_at` + a `split` reason,
new facts opened on the new entity — invalidate-not-delete preserved, audit intact). Satisfies append-only
AND corrigibility. Add `split_entity` to the §6D KAL write verbs.

**12.4.3 Name + aliases are multi-valued bi-temporal facts (D3).** Today `name`/`aliases` are flat EAV
rows the resolver reads timelessly — so rename-at-ch.4000 spawns a spurious entity *and* as-of name
(§6B's own anti-spoiler example) is impossible. Fix: model name + aliases as **multi-valued bi-temporal
facts** (`cardinality=multi`, `valid_from_ordinal`). Then:
- The resolver matches the **full across-all-time alias set** → a ch.4000 mention resolves to the ch.1
  entity, **no merge needed** (this also *shrinks* the merge load that 12.4.1 must handle).
- As-of name read returns the canonical name `valid_at ≤ N` → spoiler-free names fall out for free.
- The alias-fold in `mergeOne` appends alias facts with provenance + valid-from, instead of flattening to
  one JSON string. CJK honorific/tokenizer normalization (the known lessons) is the resolver's test plan
  so residual merges are minimized.

### 12.5 KAL contract hardening  → closes A5, D4, D5, D6

**12.5.1 `as_of` is gated per-substrate capability (A5).** Until the KG carries a unified story-ordinal
valid-time (§8B net-new), the KAL **must not** silently serve transaction-time-contaminated KG `as_of`.
The contract returns a typed `temporal_capability` per source; a KG branch without the ordinal axis either
**refuses `as_of`** (returns `temporal_unsupported`, degrade-safe) or restricts to `from_order`-only with
a documented caveat. **Build-order amendment (§9.9):** unify the KG story-ordinal valid-time **before**
`as_of` is exposed on the KG branch. `as_of` is *not* uniformly "purely additive" across a substrate that
cannot honor it.

**12.5.2 A bounded-but-COMPLETE roster primitive (D4).** The "no unbounded read" invariant must not forbid
the composition planner's legitimate need for the **whole cast** (it injects the full roster into the L2
prompt *and* uses it as the resolver index). Add `roster(book, fields=[id,name], cursor)` —
**cursor-paginated to completion** (caller drains pages) + **projection-restricted** (id+name only, never
full attributes / never the monolith). Carve it into INV-KAL as an allowed shape (bounded *per page* and
*per field*, complete *in aggregate*). **Independently fix the live bug:** `_cast_roster` ignores
`next_cursor` and truncates at 100 today — it must drain the cursor regardless of the KAL.

**12.5.3 Multi-valued structured reads** (pairs with D9): the KAL exposes `list_attr_values(entity, attr,
cursor)` for multi-valued attrs (aliases/tags/appears_in) — paginated structured facts, never folded
prose. Bounded per page, complete in aggregate, same shape as the roster.

**12.5.4 Cold-start seed carries the CURRENT value (D5).** The migration open fact carries the entity's
**current flat EAV value** (and current canonical), with `valid_from_ordinal = first-seen-ordinal` as the
**lower bound only** (not a value selector). So the projection is byte-identical to the pre-migration flat
store for every existing entity → "consumers keep working unchanged" is true on day one. **Migration test:
`projection(entity) == flat_eav(entity)` for all entities post-seed.**

**12.5.5 INV-KAL is enforced by TWO mechanisms (D6).** A grep lint catches only direct table reads, not
the bespoke-HTTP outliers §6D exists to kill. Split enforcement: (i) **grep lint** for direct
table/Cypher reads outside owning-service + KAL paths (allowlist-based); (ii) **HTTP-surface check** —
lint that **no consumer-service client targets the owning services' `/internal/*` knowledge endpoints**
(greppable on the base-URL/path constant in consumer clients). Until both exist, document INV-KAL as
"table-read-enforced, HTTP-surface tracked-for-migration" + a DEFERRED row for the bespoke-HTTP consumers
(composition/enrichment `list_entities`) — **do not claim gateway-grade enforcement it doesn't have yet.**

### 12.6 Re-locked decisions (supersedes the §9 ⚠ downgrades)

With §12 the six reopened decisions are **re-locked**, now resting on designed mechanisms not on "reuse
the existing primitive":

| §9 | Re-locked as | Backed by |
|---|---|---|
| 2 (fold cadence) | debounced incremental fold + **deterministic K-folds-or-J-invalidations re-ground** via an **ordinal-bucketed tree**; compare-and-clear retained | §12.1 (B1/B2/B4), §12.2.4 (C3) |
| 4 (storage) | append-only `entity_facts` SSOT + **synchronous-in-tx** EAV projection + **content-addressed fact natural key** + `episodes(status, UNIQUE(chapter,hash))` | §12.0, §12.2.1/.2/.5 (C1/C2/C6) |
| 6 (invalidation) | per-attr cardinality, default supersede via the **ordinal-aware interval-split** (NOT KG `single_active`); identity includes interval origin (oscillation) | §12.3.2/.4 (A2/A4) |
| 7 (retract) | content-hash-gated + **chain re-stitch (B.3.5)** + opt-in `allow_retract_on_remodel` | §12.3.3/.5 (A3/D7) |
| 8 (translation) | as-of injection + immutable-once keyed on **bounded-unit content-hash** (re-ground-safe) | §12.1 (D8), §12.5.1 (A5) |
| 9 (KAL) | new typed gateway + **per-substrate `as_of` gating** + **bounded-complete roster** + **two-mechanism INV-KAL** + corrected build order + `split_entity` verb | §12.4.2 (D2), §12.5 (A5/D4/D6) |

Decisions **1, 3, 5 stand unchanged.** The architecture (append-only bi-temporal facts as the sole SSOT,
everything else a rebuildable cache — INV-FACTS) is unchanged and reaffirmed; §12 hardens the *mechanisms*
that realize it. **This is the BUILD-ready design** (see §12.7 for the verification-round tightenings).

### 12.7 Verification-round tightenings (2026-06-30)

Two adversarial agents verified §12 against the code and against itself. They confirmed the substance
holds (B0/B1/B3/B4, C2/C3, A1/C4/D2/D3, D1/D4/D8 close, with code citations; the merge↔canonical-staleness
interaction, oscillation-fold, and Path-B compositional trace are all consistent). They found **two HIGH
self-inflicted serialization bugs**, plus citation/ambiguity defects (fixed inline above: §12.3.1
`spoiler_window.py`→`events.py`; §12.3.3 stored-`valid_to` single-routine). The locking model is the
load-bearing fix:

**12.7.1 LOCKING MODEL — scope the lock to its actual TOCTOU surface (closes the two HIGH: over-locking +
unbounded merge critical section).**
> ⚠ **The lock TABLE below is REFINED by §12.7.8** — a round-2 verification showed dropping the per-book
> lock *entirely* lost resolver-create + chapter-write-once protection. §12.7.8 is the authoritative,
> *decomposed* model (this row's direction is right; its coverage was incomplete). Read §12.7.8. §12.2.3's "ALL fact writes take ONE per-book advisory lock" was
**wrong twice**: (i) it **over-locks** — a book-global lock serializes *all* extraction for a book to one
writer, foreclosing the within-book parallelism `project_extraction_parallelism_gap` + the analysis doc
want; and (ii) §12.4.1 ran the whole merge (repoint-all + reconcile + projection rebuild) *inside* that
lock — an **unbounded critical section** that stalls the book, contradicting §12.2.1's own "rebuild never
on the hot path." Also: the parenthetical "the lock `mergeExtractedEntity` already uses" is **inaccurate**
— bulk-extract writeback uses `pg_advisory_xact_lock(extractionWritebackLockNS, hashtext(book))`
(`extraction_handler.go:611`), but the standalone cross-kind **merge uses row-level `FOR UPDATE`**
(`merge_handler.go:262-265`), a *different* lock; the adopt/sync paths use yet another single-int
namespace. **Replace §12.2.3 with a scoped model** — §12's own correctness mechanisms (the idempotent
natural key §12.2.2 + the ordinal-aware `maintain_chain` §12.3.3) already make disjoint appends safe
*without* a book-global lock, so:

| Operation | Lock | Why it's sufficient |
|---|---|---|
| **Append a fact** (Path A/B chain write + in-tx projection upsert) | **per-`(entity_id, attr)` chain** (advisory or row), acquired in **sorted entity-id order** within a chapter to avoid deadlock | the natural key makes exact-dup appends idempotent; `maintain_chain` under the per-chain lock makes the interval-split correct. Disjoint entities/chapters run **in parallel** → restores the parallelism goal. |
| **Resolver create** (new entity for an unmatched name) | `UNIQUE(book_id, normalized_name, kind)` + `ON CONFLICT DO NOTHING` (no lock) | constraint resolves the create-TOCTOU without serializing. |
| **Merge / split** | per-**entity-pair** (the existing `FOR UPDATE` on loser+winner) + the per-chain locks for the affected attrs only | touches two entities' chains, not the book. |

**Name the one canonical fact-write lock key** so Path A/B don't take non-conflicting locks and serialize
nothing: per-chain = `pg_advisory_xact_lock(FACT_CHAIN_NS, hashtext(entity_id||':'||attr))`. This is an
explicit, recorded **decision to drop the per-book serialization in favour of per-chain** — realizing
`project_extraction_parallelism_gap`, not deferring it.

**12.7.2 Bound the merge critical section (HIGH-1).** Stage the heavy work **outside** the lock: repoint +
`maintain_chain` reconcile + projection rebuild run as a prepared batch; take the per-entity-pair +
affected-chain locks for the swap. For a huge merge, chunk the repoint and release/reacquire between
chunks. Merges are rare/admin-gated — state that explicitly so the trade-off is conscious. The winner
projection rebuild is **winner-scoped**, never the §12.2.1 full repair job.
> ⚠ **CORRECTED by §12.7.8 (Probe-2):** "lock only for the swap" reintroduced a lost-update — a loser
> append between the staging read and the swap is dropped. §12.7.8 requires the affected **chain locks be
> held from the staging-read through commit** (or a fingerprint re-validate under the swap lock). The
> *outside-the-lock staging* of the heavy rebuild still stands; only the lock *coverage window* changes.

**12.7.3 Roster drain is a stable keyset snapshot (MED-1).** §12.5.2's "drain to completion" needs a
**keyset cursor** (on a monotonic `id`/`created_at`) so concurrent inserts append *past* the cursor rather
than shift it, plus a stated contract: *the roster is a snapshot as-of drain-start; entities created
mid-drain may be omitted — tolerated by the planner's commit-time `BAD_ENTITY`/unresolved-name check*.
Without this the "complete in aggregate" claim only holds under no concurrent writes.

**12.7.4 Resolver bootstrap on first ingest (LOW, D3).** §12.4.3 describes only steady-state name
resolution. Add the cold path: **no alias-fact match → create the entity + seed its name/alias facts at
the current ordinal** (`valid_from = N`), so a brand-new entity with zero name facts doesn't loop the
resolver.

**12.7.5 Re-ground bucketing key (LOW, B1).** Bucket facts by **`valid_from_ordinal`** — a fact belongs to
exactly **one** window (its origin); the map-reduce **carries forward open intervals** across window
boundaries so a fact spanning two windows (`[150,450)`) isn't double-counted.

**12.7.6 Path-B unchanged-value re-points, not re-opens (LOW).** In Path B step 3, a fact value **still
present** across the edit must **re-point to / no-op against the existing interval** (the prior revision's
row), not open a parallel interval from the new episode id. `maintain_chain` over survivors collapses any
transient overlap, but state the intent so a builder doesn't mint a duplicate interval per re-extract.

**12.7.7 Cross-links + deferrals (LOW).** (a) §12.2.5 — add the clause "the §12.2.1 projection upsert
happens in **tx-2** alongside the fact append, not tx-1." (b) D6 is closed **as a plan, not as
enforcement** (the HTTP-surface lint doesn't exist yet) — land the **DEFERRED row** (HTTP-surface lint +
the bespoke `/internal/* list_entities` consumers) in `SESSION_HANDOFF`. (c) The prescribed edits to
upstream §3.3 / §5 / §6B / §4-Path-B-step-5 are **applied in BUILD**; until then those sections are
**superseded by §12** where they conflict (a top-to-bottom reader should treat §12 as authoritative).

**12.7.8 Locking model — CORRECTED (round-2 verification).** A third agent verified §12.7.1/.7.2 against
the code and found the fix **over-corrected**: dropping the per-book lock entirely lost **two** guarantees
that fine-grained chain locks don't cover — and §12.7.2's "lock only for the swap" reintroduced a merge
lost-update. The per-book lock was load-bearing for resolver-create-TOCTOU (the migration comment is
explicit: *"the advisory lock makes the resolver race-free; this index is the backstop"* —
`extraction_concurrency.go:21-25`) and chapter write-once. The right model is **NOT "book lock" vs "no
lock"** — it is to **decompose** the book lock into the minimal scoped locks, each held only over its real
critical section, so parallelism survives *and* every guarantee is preserved. **This supersedes the lock
rows of §12.7.1 and §12.7.2.**

| Critical section | Lock (all finer than per-book) | Parallelism / why it closes the gap |
|---|---|---|
| **Resolver-create** (new entity for an unmatched name) | per-**`(book, normalized_name, kind)`** advisory lock around the whole resolve→create→**stamp** sequence; **OR** stamp `normalized_name` **in the INSERT** (app-side, not the deferred `refreshEntityDedupKey`) + real `ON CONFLICT (book_id, kind_id, normalized_name) DO NOTHING RETURNING` + **re-read the winner's `entity_id` on conflict**. | name-scoped → different names run parallel. **Closes Probe-3 HIGH:** today's create inserts with empty `cached_name` (`normalized_name=''`) → *outside* the partial `uq_entity_dedup` index (`WHERE … normalized_name<>''`) → two creates both pass, UNIQUE only bites at the later stamp. The partial index is a **backstop, not the primary guard** — §12.7.1 wrongly promoted it. |
| **Chapter write-once** | `UNIQUE(chapter_id, content_hash)` (§12.2.5) as the chapter idempotency gate + `writeback_key` replay short-circuit | chapter-scoped → different chapters run parallel. **Closes Probe-5 MED:** the book lock incidentally serialized per-chapter writeback; without it, two different `writeback_key`s for the *same* chapter could both proceed — the `(chapter,content_hash)` UNIQUE restores chapter-level write-once. |
| **Fact append / interval maintenance** | per-**`(entity, attr)`** chain advisory lock `hashtext(entity_id‖':'‖attr)`, acquired in sorted **full-composite-key** order | chain-scoped → disjoint chains parallel. **Closes Probe-1 MED:** sort by the composite chain key, NOT entity-id (an entity has multiple attrs → two chapters writing `{a,b}` of E deadlock under entity-id sort). |
| **Merge / split** | entity-pair `FOR UPDATE` (sorted by `entity_id`) **+ the affected per-chain locks, held from the staging-READ through COMMIT** (not "only for the swap") | entity-pair-scoped. **Closes Probe-2 HIGH:** holding the loser/winner chain locks across the staging read prevents a loser-chain append from interleaving between stage and swap (which would be dropped or left with a stale `valid_to`). The heavy projection rebuild may still be staged outside, but **chain-lock coverage must span read→commit**; alternatively re-validate the §12.2.4 `max(created_at)` fingerprint under the swap lock and re-stage on mismatch. |

**Global lock order (deadlock-free, spans both lock domains).** Every path acquires in this exact order:
**(1)** the create lock (if creating) → **(2)** entity rows `FOR UPDATE` sorted by `entity_id` → **(3)**
chain advisory locks sorted by full composite key `(entity_id, attr)`. Append and merge both nest under
this single order, so the two lock *types* (row-level `FOR UPDATE` + advisory) can't form a cycle.

**Probe-4 (LOW, confirmed safe — state it):** the EAV projection is keyed **per-`(entity, attr)` row**
(`ON CONFLICT (entity_id, attr_def_id)`), so two chapters appending *different* attrs of the same entity
hit *different* projection rows → no lost update; same-`(entity,attr)` upserts serialize on the Postgres
row lock. §12.2.1 should say "per-`(entity,attr)` projection row" to make this self-evident.

> **Net of round-2:** the per-chain *direction* is right and restores the parallelism goal, but the lock
> had to be **decomposed, not deleted**. The corrected tiered model above preserves all four guarantees
> the coarse book lock gave (resolver-create, chapter write-once, chain-interval correctness, merge
> atomicity) while keeping disjoint chapters/entities/names concurrent. **This is the load-bearing
> correctness contract for BUILD.**

**Verified consistent (not defects):** the A5↔decision-8 ordering (translation as-of reads the *glossary*
substrate §12 builds, not the KG `as_of` §12.5.1 defers); the §12.2.1↔§12.2.5 tx-timing; the
merge→canonical staleness (the merge's re-derived `valid_to` bumps `fact_coverage_txid` → canonical
rebuilds); and (round-2) the append-vs-fold compare-and-clear + episode-revision minting both hold
independent of the dropped book lock. **The architecture is unchanged across all three review rounds;
these are tightenings, not redesign.**
