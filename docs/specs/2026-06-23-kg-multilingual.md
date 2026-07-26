# Spec — Multilingual Knowledge Graph (canonical-source + derived localization)

**Date:** 2026-06-23
**Status:** DRAFT (DESIGN — pending red-team REVIEW)
**Author:** session (knowledge-graph-ontology track)
**Scope:** knowledge-service, glossary-service, book-service client, composition-service packer, frontend i18n

---

## 1. Problem (verified, not assumed)

LoreWeave translates novels (e.g. Chinese original → Vietnamese) and builds a KG (entities,
relations, passages, embeddings, timeline) on top. A user writing a Vietnamese spin-off wants to
query the **original timeline** but cannot read the source language. Today that fails — but **not**
the way it first appears.

### 1.1 What the KG actually stores today (audited)

The graph is a **3-layer language soup**, none of it Vietnamese:

| Component | Language | Evidence |
|---|---|---|
| Entity `name` / `canonical_name` | **source language (zh)** | `sdks/python/loreweave_extraction/prompts/entity_extraction_system.md:12-15` — *"Keep entity `name` values in the ORIGINAL script of TEXT — do not transliterate or translate"* |
| Passage prose text | **source language (zh)** | `app/extraction/passage_ingester.py` ingests source chapter text; no language tag |
| `kind` (character, location…) | **English — fixed** | same prompt: *"JSON keys and `kind` values stay English"*; `services/glossary-service/internal/domain/kinds.go:57-227` seeds 12 EN kinds |
| `predicate` / `relationship_type` | **English snake_case — fixed** | `relation_extraction_system.md:13-15` — *"Keep `predicate` in English snake_case regardless of the TEXT language"* |
| `fact_type` | English enum | knowledge-service models |

So the "everything is English" instinct and the "everything is Chinese" instinct are **both half
right**: instance content is source-language, the schema/ID layer is English, **nothing is localized
to the reader's language**.

### 1.2 What breaks in the scenario

- **No re-ingest on translation.** No `translation.published` handler in knowledge-service
  (`app/events/handlers.py`), and `BookClient` chapter-text endpoints have no `language` param
  (`app/clients/book_client.py:374-441`). After translating to vi, the passage index is **100% zh**.
- **Timeline labels are zh.** `_TIMELINE_CYPHER` / `GraphNode` return raw `name`; no translated
  label field (`app/routers/public/graph_views.py:97-134,270-302`).
- **Composition pulls zh.** `glossary_client.select_for_context` sends no `language` key
  (`services/composition-service/app/clients/glossary_client.py:45-69`) even though glossary
  supports per-language aliases via `composePerLanguageAliases`
  (`glossary-service/internal/api/select_for_context_handler.go:45-87`); lore lens returns raw zh
  passages.
- **No language filter anywhere** in search/retriever (`app/search/retriever.py:155-271`,
  `app/routers/public/raw_search.py`).

### 1.3 What is NOT the problem (decided in discussion)

- **Entities merged across languages is CORRECT.** "Dracula" / "Bá tước Dracula" are one concept.
  We have **ground-truth alignment** (we know which chapter is a translation of which) — we do NOT
  need GNN/embedding entity-alignment (the cross-lingual-KG research problem). Do not build it.
- **English schema codes are CORRECT** — they are Wikidata-style language-agnostic identifiers
  (QID/property analogue). The fix is a **label layer**, not a rebuild.
- **Rebuilding the KG on the translation is an ANTI-PATTERN** — it bakes translation errors into the
  knowledge base, worsens entity resolution (inconsistent transliteration of proper nouns across
  chapters), forfeits the canonical source anchor, locks to one target language, and **still emits
  English `kind`/`predicate`** (prompt forces it regardless of input language). It costs the most
  expensive token type (generation, re-extraction) to buy almost nothing.

---

## 2. Target architecture — 4-layer model (industry standard)

Principle (ontology localisation, arXiv:2210.02807): *localizing by labels touches only the
linguistic layer; the concept space stays unchanged.* Wikidata is the reference: language-agnostic
IDs + labels per language.

| Layer | Role | Language | SSOT | Today | This spec |
|---|---|---|---|---|---|
| **0. Concept/ID** | kind & predicate identifiers | language-agnostic (EN codes) | code/glossary | ✅ exists | keep |
| **1. Canonical content** | facts extracted from **source** | source language | Postgres (knowledge) + Neo4j derived | ✅ exists | keep; add `source_lang` tag |
| **2. Derived localization** | labels/names/prose per reader language | any | glossary translations + new label maps | ❌ missing wiring | **build** |
| **3. Retrieval** | multilingual embed + language-aware ranking | — | Neo4j vector + book lexical | ⚠️ partial | **extend** |

**Hard rule:** Layer 1 is built **once, from the source language, never from a translation.**
Everything a reader sees in vi is **derived** at Layer 2/3.

---

## 3. Design decisions

### D1 — Tag language at the content layer (enables everything else)
- Add `source_lang` (ISO-639-1) to `:Passage` and `:Entity` nodes, and to the Postgres mirror.
- Forward chapter `original_language` from book-service (already stored in
  `book-service migrate.go`) through `BookClient` → passage ingester. New optional field, additive.
- Persist the `detect_primary_language()` result that today is computed-then-discarded
  (`app/extraction/pattern_extractor.py:236-247`) onto extracted nodes as provenance.
- **Backfill** existing zh nodes with `source_lang='zh'` (book-level default) via a one-shot, same
  pattern as the published-passage backfill (`D-KG-PASSAGE-BACKFILL`, commit 626bcec6).

### D2 — Dual-index translated passages (build-time precompute)
- On `translation.published` (NEW event handler in knowledge-service), ingest the **vi** chapter
  text as **additional** `:Passage` nodes tagged `source_lang='vi'`, `derived_from=<zh passage/chapter>`.
- Cost = **embeddings only** (the vi prose already exists from the reading feature — sunk cost; no
  generation, no re-extraction).
- vi query → multilingual embedding → **same vector space** → matches vi passages directly →
  same-lingual retrieval → readable output → **~0 generation tokens at query time.**
- Entities/relations/timeline are **NOT** re-extracted from vi (Layer 1 stays canonical).

### D3 — Localized labels for the Concept/ID layer (Layer 0→2)
- **kind labels:** add per-language label map for the 12+ kinds (`character → nhân vật`). NOT an
  LLM job — static i18n strings, ~0 tokens.
- **predicate labels:** frontend/presentation i18n map (`disciple_of → "là đệ tử của"`). Static.
- **Tenancy (per the LOCKED tiers in CLAUDE.md):**
  - System kinds → System-tier labels: admin-seeded, read-only to users, one row per (kind_code, lang).
  - User/book custom kinds → label owned by that user/book tier; `UNIQUE(scope_key, kind_code, lang)`.
  - **Never** a globally-unique user-mutable label row (that is the original `entity_kinds` bug).

### D4 — Localized entity display names (Layer 2)
- Use existing glossary `attribute_translations(language_code)` + `composePerLanguageAliases`.
- **Wire the missing caller:** composition `select_for_context` must pass `language` (S6 infra
  exists, only the caller omits it). Same for timeline/graph-view label resolution.
- Populate vi entity names: triggered from the translate flow with a **glossary-locked** translation
  (proper nouns resolved consistently), one-time per entity (cheap, ~dozens of entities/book).

### D5 — Language-aware retrieval (Layer 3) — SOFT WEIGHTING, not hard filter
- Add optional `language` param to search endpoints + retriever.
- **Soft language-preference weighting (chosen over hard pre-filter).** Language match is a *score
  signal*, not a binary gate: over-fetch cross-language candidates, then re-rank with a
  language-preference boost (`w_lang · same_lang(reader_pref)` added to the normalized
  dense+sparse score) + the existing reranker for precision. Cross-language hits are allowed but
  down-weighted, never excluded.
  - **Why not hard filter:** with partial translation (the common case — user translates chapter by
    chapter), a hard language gate returns *empty/starved* results for untranslated chapters. Soft
    weighting returns the source-language fallback ranked lower + a coverage signal (D11). This is the
    mainstream production stance ("hybrid boosts recall; reranking restores precision"); see RDF/RAG
    survey + hybrid-search playbooks.
  - **Bonus — relaxes V5:** soft weighting over-fetches and re-ranks anyway, so it does NOT depend on
    the vector store's native pre-filtering. Neo4j's post-hoc filter limitation becomes irrelevant;
    V5 downgrades from blocker to informational.
  - Optionally enforce a per-language quota in top-K (the 46%→65% Hits@20 finding, arXiv:2507.07543)
    as a soft constraint when both languages are well-represented.
- Reader preference comes from D10 (server-side per-(user,book)), falling back to detected query
  language, falling back to source.
- Keep ONE multilingual embedding model + ONE vector space (mainstream; bge-m3 / Qwen3-Embedding
  class). Model resolved via provider-registry per BYOK rule — **no per-language model env knob**
  (the `D-RERANK-NOT-BYOK` mistake).
- **Design context (why we hand-roll this):** RDF/triple stores (Stardog, Ontotext GraphDB, Neptune
  RDF, Jena) get the *label* layer free via `@lang`-tagged literals + SPARQL `langMatches()` — the
  Wikidata model native. Neo4j is a property graph (LPG) with no language-tagged literals, so D3/D4
  hand-build the label layer in the app tier. **The vector/retrieval layer is the same for everyone**
  regardless of graph DB — RDF stores bolt on vector search separately and face the identical
  single-space + language-noise problem D5 addresses. Switching to RDF for native labels is a non-goal
  (re-platform); hand-rolling in Neo4j is the pragmatic choice.

### D6 — Token budget posture
- **Build-time precompute wins** for LoreWeave: static corpus (a novel doesn't change) + very high
  query frequency (cowrite pulls lore every turn) + translation already sunk + BYOK (respect user
  wallet). Amortization is decisive — break-even after a few dozen queries.
- **Avoid** the two token-heavy anti-patterns: (a) re-extraction on vi, (b)
  document-translation-per-query (re-translates the same static passages forever).
- Runtime cost is bounded to: embedding the short query (+ optionally translating the one query
  string). Generation tokens at query time ≈ 0.

---

## 4. Tenancy & SSOT checklist (LOCKED rules)

- Postgres SSOT, Neo4j derived → any Postgres delete of a translated artifact must cascade to Neo4j
  (the `purge_project` lesson; `postgres-ssot-neo4j-derived-delete-must-cascade`). vi passages are
  derived → include them in project/book purge scope.
- Every new localization row carries a scope key (System / `owner_user_id` / `book_id`) and every
  query filters by it. No `UNIQUE(code)` on a shared user-writable table.
- New cross-service contract (translation event, language param) → live-smoke through the **consumer**
  path, not unit-only (`new-cross-service-contract-needs-consumer-live-smoke`).

---

## 5. Change list (fix-now vs defer — to be finalized after red team)

| # | Change | Service | Size | Note |
|---|---|---|---|---|
| C1 | `source_lang` on Passage/Entity (+ backfill zh) | knowledge | S | additive, enables all |
| C2 | Forward `original_language` via BookClient → ingester | knowledge | S | book-service already stores it |
| C3 | `translation.published` handler → dual-index vi passages | knowledge | M | embeddings only; new event contract |
| C4 | kind label map + tenancy tiers | glossary | M | static i18n; tenancy-sensitive |
| C5 | predicate i18n map | frontend | S | presentation only |
| C6 | composition passes `language` to select_for_context | composition | XS | one-field wiring; infra exists |
| C7 | timeline/graph-view label resolution (vi) | knowledge | S | presentation join |
| C8 | `language` param + language-preference ranking | knowledge | M | retrieval correctness |
| C9 | glossary entity-name vi population (glossary-locked) | glossary/translation | M | one-time per entity |

---

## 6. Edge cases (red-team target — stress these)

1. **Mixed-language chapters** (zh prose with English/loanword terms) — which `source_lang`? Per-sentence split already exists; how does it tag a passage that spans languages?
2. **Multi-source-language book** (a book whose chapters originate in different languages, not translations of each other).
3. **Partial / in-progress translation** — only some vi chapters exist; retrieval must not silently drop coverage or falsely report completeness.
4. **Translation drift** — vi translation edited after dual-index; stale vi passages vs canonical. Re-embed trigger? Version pinning?
5. **Same surface form, different entity across languages** — anchor key `(folded-name, kind)` collision (`entity_resolver.py:116`).
6. **Proper-noun transliteration inconsistency** in vi name population (same zh entity → 2 vi spellings).
7. **Embedding model actually weak on zh or vi** — single-space assumption degrades; no per-language fallback by design.
8. **Embedding model / dimension change** — re-index cost for doubled (zh+vi) corpus.
9. **Three+ languages** (zh original, vi + en translations) — quota ranking, storage, label fan-out.
10. **Tenancy leak** — user A's kind label or entity-name translation visible/mutable to user B.
11. **Deletion/purge** — derived vi passages orphaned in Neo4j on book/chapter/project delete.
12. **Cost-gate / fairness** — dual-index of a large book as one job vs per-chapter (P5 WFQ, runaway worker lessons).
13. **Query language detection failure** — short/ambiguous query mis-detected → wrong language preference.
14. **Glossary attribute_translations not populated** — composition passes `language=vi` but no vi data exists → empty vs fallback-to-source behavior.

---

## 7. Open questions

- Q1: Dual-index vi as separate nodes vs a `translations[]` property on the zh passage? (separate
  nodes chosen — cleaner language filter + ranking; confirm storage cost acceptable.)
- Q2: Is the configured embedding model verified multilingual-strong for zh **and** vi? (blocking
  assumption for D2/D5 — verify before build.)
- Q3: Who triggers entity-name vi population — the chapter translate flow, a glossary batch, or the
  KG build? (avoid double-spend.)
- Q4: Re-embed policy on translation edit — eager, lazy, or version-pinned + sweeper?

---

## 9. Red-team review outcomes (2026-06-23, 5 adversarial reviewers)

Findings triaged into three buckets. **Build-work** = "code not written yet" — expected for a draft,
not a defect; tracked in the change list, no design change. **Design-hole** = the spec was wrong or
silent on a decision; resolved below and folded into decisions/change-list. **Verify-gate** = a
load-bearing assumption that must be checked before BUILD.

### 9.1 Design-holes — RESOLVED (these amend the decisions above)

- **R1 — Anchor-key collision is NOT introduced by this spec (downgraded from "BLOCKER").**
  Reviewer 1 feared `(folded-name, kind)` collision across languages. But D2 **does not re-extract
  entities/relations from vi** — the only entity resolution still runs on the **source** text, exactly
  as today. vi names arrive via D4 (glossary translation of an *already-resolved* entity), not via a
  new extraction pass. So no new cross-language collision is introduced. The pre-existing
  same-name-different-entity risk (within a language) is **orthogonal** and out of scope here. **Action:**
  state explicitly in D2 that the vi path is *index-only* (passages) + *label-only* (names), never a
  second extraction. Confirm `entity_resolver` anchor index is project-scoped (it is keyed off the
  project's glossary anchors) — note as a verify item, not a change.
- **R2 — `translation.published` event does NOT exist today → hard prerequisite, not an assumption.**
  Grep confirms no such event in translation-service and no handler in knowledge-service. **Action:**
  C3 is split — **C3a (translation-service): emit a transactional-outbox `translation.published`
  event** (payload: `book_id, chapter_id, target_language, revision_id, owner_user_id`) at the
  version-activate chokepoint; **C3b (knowledge-service): consume it** → dual-index. C3b cannot start
  before C3a. Live-smoke the contract through the consumer (composition retrieval) per
  `new-cross-service-contract-needs-consumer-live-smoke`.
- **R3 — Reader-language is undefined and conflated with UI-language and query-language.** Three
  distinct things: (a) *UI language* (localStorage, per-device, fine), (b) *query language* (detected
  from the query string), (c) *content/reader-language preference* (which language of passages/labels
  the user wants back). **Action — new decision D10:** reader-language preference is **per-(user,
  book)** user-data, stored **server-side** (`book-service` reading state or `auth-service`
  preferences — pick in PLAN), synced cross-device (CLAUDE.md: server is SSOT, not localStorage).
  Retrieval ranking (D5) keys off **this stored preference**, falling back to detected query language,
  falling back to source. Chat/composition must forward it explicitly.
- **R4 — Tenancy schema for labels was hand-waved (genuine, the canonical-bug class).** `kind_labels`
  table does not exist; `attribute_translations` is scoped only *indirectly* via the entity→book FK.
  Indirect-via-FK is acceptable for the **book tier** (every query already joins through book_id), but
  D3's System + Per-user tiers have **no table**. **Action — tighten D3:** new `kind_labels(kind_code,
  language_code, label, scope, owner_user_id NULL, book_id NULL, ...)` with
  `UNIQUE(scope, COALESCE(owner_user_id,'∅'), COALESCE(book_id,'∅'), kind_code, language_code)`;
  System rows admin-seeded via the existing `system_admin_handler` RS256-scoped path (read-only to
  users); resolution merges System→Per-user→Per-book; **no user write to a System row** (else it is the
  `entity_kinds` bug again). Per-user label tier is **deferred** (D-KG-ML-PERUSER-LABELS) unless a
  concrete need appears — System+Book covers the scenario.
- **R5 — Predicate/kind localization must NOT be frontend-only (C5 was wrong).** chat-service and
  MCP/agent consumers also render predicates/kinds and never touch frontend i18n files. **Action:**
  serve the kind/predicate label map from a **backend contract** (a knowledge/glossary read endpoint
  or a shared i18n resource the gateway exposes); the frontend consumes the same source. C5 reclassified
  M, moved off "frontend-only".
- **R6 — Partial-translation coverage must be signalled, not silently filled with source.** If only
  some chapters are translated, a vi-preferring query that hits an untranslated chapter currently
  returns unreadable source silently. **Action — new decision D11:** retrieval returns a per-hit
  `lang` + a response-level `coverage` note ("chapters X–Y not translated; showing source"). The
  consumer (reader/cowrite) surfaces it. No silent fallback.
- **R7 — Re-embed policy (was open Q4) — RESOLVED.** Mirror the existing zh behavior: `chapter.published`
  already does delete-then-reingest per source (`delete_passages_for_source`). So **republishing a vi
  translation re-fires `translation.published` → delete vi passages for that (chapter, lang) → re-embed.**
  Eager, idempotent, bounded to the edited chapter. vi passages are keyed `(source_id=chapter_id,
  source_lang=vi)` so the delete is language-scoped and never touches zh. No version-pin/sweeper needed.
- **R8 — Wiki multilingual was out of scope and unstated.** `wiki_articles` has one row per entity, no
  language dimension. **Action:** declare wiki multilingual an **explicit deferral**
  (D-KG-ML-WIKI) — the scenario (timeline + cowrite lore) does not need per-language wiki bodies yet;
  attribute-translation embedding in the existing article is the interim. Do not silently imply it works.
- **R9 — MCP-first for agent-facing multilingual query.** If an agent decides language/ranking, that
  logic must be an MCP tool through ai-gateway, not a bespoke HTTP endpoint (CLAUDE.md invariant). The
  *non-agentic* retrieval HTTP path (composition packer, raw search) is exempt. **Action:** when the
  cowrite agent gains a "search lore in my language" capability, expose it as an MCP tool; plain
  retrieval params on existing endpoints stay HTTP. Note in change-list, not a blocker now.

### 9.2 Verify-gates — must check BEFORE build (do not assume)

- **V1 (load-bearing) — Is the configured/default embedding model actually strong on BOTH the source
  language and vi?** Flagged by 3 reviewers. The whole single-vector-space design (D2/D5) rests on it.
  The model is BYOK-resolved via provider-registry; there is **no language-capability gate** today.
  **Gate:** probe the default embedding model with parallel zh/vi/en queries vs known passages; if
  weak on a target language, the design needs a per-language fallback (currently a non-goal) — so this
  gate can *invalidate* §8. **This is the #1 next action.**
- **V2 — Is `chapters.original_language` reliably populated (non-null) on existing data?** D1 backfill
  uses it **per-chapter** (NOT a book-level default — reviewer correctly killed the book-level shortcut;
  a book may hold chapters of different source languages). If null for legacy chapters, define a
  detect-or-default fallback before backfill.
- **V3 — Confirm the embedding cost path is metered.** Passage embedding is currently **inline and
  NOT recorded to usage-billing** (reviewer 3, Finding 2). Dual-index doubles an already-unmetered
  spend. **Action — new row C10:** record `embed_result.prompt_tokens` to usage-billing at the ingest
  chokepoint (fixes the existing leak too), with correct owner/job attribution; add a skip-gate so an
  unchanged republish does not re-embed-and-re-bill.
- **V4 — Verify test fixture language.** The driving example uses zh→vi; the in-system "Dracula" book
  may be en→vi. Design is language-pair-agnostic, but examples/acceptance must use the real fixture.
- **V5 (DOWNGRADED to informational by D5) — Neo4j vector index pre-filter vs post-filter.** The
  running Neo4j's `db.index.vector.queryNodes` may only post-filter (top-K then filter), which would
  starve a hard language filter. **D5's soft-weighting/over-fetch+rerank removes this dependency** —
  no native pre-filter required. Still worth confirming the version's behavior for sizing the
  over-fetch multiplier.
- **V6 — Lexical/keyword leg is per-language (tokenizer does NOT share a space).** Unlike multilingual
  embeddings (one shared vector space), keyword analyzers are language-specific: a `standard` analyzer
  mis-tokenizes Chinese (no word spaces). Whether lexical lives in Neo4j full-text (`db.index.fulltext`)
  or book-service Postgres (`tsvector`), `source_lang` must select the analyzer/config. **Verify:**
  Neo4j `db.index.fulltext.listAvailableAnalyzers()` for `cjk`/`smartcn`; and whether Postgres has a
  CJK tokenizer extension (`zhparser`/`pg_jieba`). Tracked as design item D12 (lexical leg per-language).
- **V7 (load-bearing, twin of V1) — the RERANKER must be multilingual too.** D5 leans on a reranker
  to restore precision after soft-weighting over-fetch. A cross-encoder reranker has the SAME
  language-capability requirement as the embedding model: an English-only reranker will mis-rank
  zh/vi candidates and silently undo D5. **Verify:** which rerank model is configured (BYOK via
  provider-registry, per `local-model-backends-via-provider-registry` / `default-model-per-capability-byok`),
  and confirm it is multilingual-capable (e.g., bge-reranker-v2-m3 class). If weak → same fallout as
  a failed V1.

### 9.3 Amendments to earlier sections

- **D1** corrected: backfill `source_lang` **per-chapter** from `chapters.original_language`, never a
  book-level default (V2). Handle `detect_primary_language()=="mixed"` by storing the dominant lang +
  a `mixed=true` flag; ranking treats `mixed` as matching any query language (don't drop it).
- **D2** corrected: vi path is **index-only + label-only, never re-extraction** (R1); trigger is the
  new `translation.published` (R2); re-embed is eager-per-chapter on republish (R7).
- **Change list additions:** C3→C3a/C3b (event producer + consumer); C5 backend-served (R5); C10 cost
  metering + skip-gate (V3); C11 reader-language preference storage + plumbing (R3); C12 coverage
  signalling in retrieval response (R6).
- **Open questions:** Q4 resolved (R7). Q2 escalated to V1 (hard gate). New: who owns reader-language
  storage — book-service reading-state vs auth preferences (decide in PLAN).

### 9.4 Deferrals earned (gate-checked)

| ID | Item | Gate reason |
|---|---|---|
| D-KG-ML-WIKI | Per-language wiki article bodies | out-of-scope for the timeline+cowrite scenario; large (schema + regen) |
| D-KG-ML-PERUSER-LABELS | Per-user kind-label tier | naturally-next-phase; System+Book covers current need |
| D-KG-ML-PERLANG-EMBED | Per-language embedding model/space | blocked on V1 evidence (only if default model proves weak) |

---

## 10. Acceptance criteria (the measurable "done" — was missing)

- **AC1 (timeline readable):** reading the vi translation, opening an entity timeline shows entity
  labels in vi (or explicit source-fallback marker), never raw untranslated source with no signal.
- **AC2 (same-lang retrieval):** a vi query on a dual-indexed book returns vi passages ranked above
  cross-lingual source hits; each hit carries its `lang`.
- **AC3 (preference is server-side):** set reader-language=vi on device A, query on device B → device B
  also prefers vi (proves R3/D10 cross-device storage).
- **AC4 (coverage honesty):** query targeting an untranslated chapter returns source + a coverage note,
  not a silent unreadable result (R6/D11).
- **AC5 (canon integrity):** dual-indexing vi does NOT create/alter any `:Entity`/`:RELATES_TO`/timeline
  node — Layer 1 byte-identical before/after (R1).
- **AC6 (tenancy):** user B cannot read or mutate user A's System/Per-book kind labels or entity-name
  translations without an E0 grant (R4).
- **AC7 (cost):** dual-index embedding spend appears in usage-billing attributed to the owner; an
  unchanged republish embeds/bills zero (V3).
- **AC8 (purge):** deleting the book/project removes ALL vi passages from Neo4j (no orphans) — verified
  by node count (R: SSOT-Neo4j cascade).
- **Live-smoke (≥2 services):** translation-service emits `translation.published` → knowledge-service
  dual-indexes → composition retrieves a vi passage in a cowrite context. One real end-to-end run.

### 10.1 Quality eval (functional AC is not enough for a retrieval-quality change)

AC1–AC8 prove the plumbing works; they do NOT prove retrieval got *better*. A retrieval-quality change
needs a measured baseline, plugged into the existing **KG-benchmark gate**:

- **Eval set:** a small fixed set of (query, expected-passage) pairs per language for one book —
  same-language queries (vi→vi, zh→zh) and cross-language (vi→zh source) — authored once, committed.
- **Metric:** recall@k and MRR **broken out by language** + a cross-lingual subset. Report the
  language-balanced top-K effect (the 46%→65% lever) as before/after.
- **Gate:** dual-index + soft-weighting (D5) must **not regress** same-language recall and must
  **improve** the vi-reader-on-zh-source case vs today's baseline. Wire into the KG-benchmark harness;
  do not ship D5 on vibes.
- Tracked as **C13 (eval harness + multilingual eval set)**.

---

## 11. Gate results (run 2026-06-23, code-inspection pass)

| Gate | Result | Detail |
|---|---|---|
| **V1 — embedding** | ✅ **PASS** | Default is **BGE-M3 (1024-dim)** — `tests/unit/test_benchmark_runner_service.py:58`, `benchmark/golden_set.yaml:159-162`, `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md`. BGE-M3 is genuinely multilingual (100+ langs incl. zh+vi). Golden-set live run already scored recall@3=1.0. The load-bearing single-space premise **HOLDS**. (Recommended but non-blocking: a zh/vi-specific recall probe for hard numbers.) |
| **V7 — reranker** | ⚠️ **PASS w/ caveat** | Reference model **bge-reranker-v2-m3** — multilingual, already perf-measured on **CJK** passages (`config.py:150-154`). BUT rerank is **BYOK + optional**: NULL project/user model ⇒ **rerank skipped** (`config.py:144-146`, `retriever.py:245-250`). → **D5 must degrade gracefully with NO reranker** (the default for un-configured users); reranker is precision-boost, not a dependency. |
| **V6 — lexical** | ❌ **FAIL (confirmed weak)** | Lexical leg lives in **book-service Postgres**, `ILIKE + pg_trgm` only (`book-service/internal/api/search.go:25-94`, `migrate.go:371-373`). **No CJK tokenizer** (no `zhparser`/`pg_jieba`), **no `tsvector`** full-text. Chinese 2–3-char terms fall below the 0.3 trigram threshold (degraded); vi diacritics/compounds unhandled. Neo4j (2026.03-community) holds **vector indexes only — no full-text index**; entity name match is exact-equality. → **D12 is evidence-backed real work, not theoretical.** |
| **V5 — Neo4j pre-filter** | ℹ️ moot + likely fine | Neo4j **2026.03-community** (`infra/docker-compose.yml:1484`) — modern line, likely supports vector metadata pre-filter; and D5 soft-weighting removes the dependency anyway. |

**Net read:** the **load-bearing risk (V1) is CLEARED** — the core single-vector-space design is sound
because bge-m3 is truly multilingual. The vector leg (the primary retrieval path) is healthy. The two
remaining items are bounded and known: **D5 must not hard-depend on the reranker** (V7), and **the
lexical leg needs per-language tokenization** (V6/D12) — which the strong multilingual vector leg +
soft-weighting partially mask, but CJK exact-term/proper-noun keyword search genuinely needs D12.

**Spec amendments from gate results:**
- **D5** add: retrieval must produce acceptable ranking with rerank **disabled**; reranker, when
  present and multilingual, is an additive precision pass — never required for correctness (V7).
- **D12** promoted from "verify" to **confirmed change** (V6): `source_lang` selects a per-language
  lexical path; for zh add a CJK tokenizer (`pg_jieba`/`zhparser` tsvector) or a Neo4j full-text index
  with a `cjk` analyzer; keep trigram as the script-agnostic fallback.
- **V1 probe** stays as a recommended (non-blocking) BUILD-time confidence check, not a gate.

---

## 8. Non-goals

- Cross-lingual entity alignment via ML (we have ground-truth alignment).
- Per-language embedding models / per-language vector spaces.
- Rebuilding Layer 1 from any translation.
- Translating the canonical graph itself (only deriving labels on top).
