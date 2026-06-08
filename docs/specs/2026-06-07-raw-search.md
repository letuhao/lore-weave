# Spec — Raw Chapter Search (full-text + semantic over raw text)

- **Date:** 2026-06-07
- **Branch:** **new workstream — recommend branching from `main`** (do NOT stack on `glossary/ai-pipeline-v2`). Mirrors the `[[lore-enrichment-branch]]` isolation rule.
- **Phase:** CLARIFY ✅ → **DESIGN** ✅ → **REVIEW (design)** ✅ (scenario-based eval, PART II) → confirm-at-BUILD all resolved (§10) → **DESIGN LOCKED 2026-06-07**. Ready for PLAN (Phase 1). No BUILD yet.
- **Related:** K18.3 `:Passage` layer (`services/knowledge-service/app/db/neo4j_repos/passages.py`), mui #4 semantic retrieval (`docs/specs/2026-06-07-glossary-semantic-retrieval.md`), Canon Model CM1/CM3 (`docs/specs/2026-06-03-canon-model.md`).
- **Size:** **L–XL** — `book-service` (Go) + `knowledge-service` (Py) + `api-gateway-bff` (TS) + `frontend`; 1 DB migration (`pg_trgm` + GIN); new internal + gateway endpoints; embedding call; cross-service ⇒ **live-smoke at VERIFY**. Built in **3 independently-shippable phases**; each phase re-classified at its own PLAN.

---

## 1. Problem

LoreWeave has three retrieval surfaces over a book — **glossary** (authored entity SSOT), **knowledge** (KG + semantic entity layer), **wiki** (generated articles). All three are **derived / lossy**: they summarise or extract *about* the text. None lets a user search the **raw chapter prose itself** — the verbatim sentences.

But raw-text search is the highest-frequency need for the two core jobs this product serves:

- **Authoring aid** — "where did I describe 姜子牙's appearance?", "find the scene where 哪吒 fights the dragon king", continuity/callback checks while writing.
- **Extraction / trích lục** — pull an exact verbatim quote with its precise source location to cite or excerpt.

Today neither is possible. `chapter_blocks.text_content` (book-service) holds the raw draft text but has **no search index**. The semantic *substrate* partly exists — knowledge-service's `:Passage` nodes already store **raw chapter chunks + per-dim embeddings + a Neo4j vector index** (`find_passages_by_vector`) — but it is consumed only internally by the context builder, is **gated on `chapter.published`** (no draft coverage), and is **not exposed to users**.

So this feature is **less greenfield than it looks**: the semantic half is ~80% built and must be *exposed + completed*; the lexical half must be *built*.

## 2. Decision (CLARIFY locked)

**Approach = build native, reuse the existing infra, depend on nothing external.** (PO-locked answers, 2026-06-07.)

- **Build it in-monorepo.** Reuse the `:Passage` semantic layer in knowledge-service (Neo4j vectors + BYOK embedding client + query-embedding cache). Do **not** adopt any external library as a runtime dependency.
- **Learn-and-reimplement the hybrid technique** from `free-context-hub` (it is the source of the ContextHub MCP) — but **re-implement in our stack**, not import it. We take the *techniques* (two-leg hybrid, rank fusion, MMR diversity, query token-expansion, graceful degradation, per-source capping); we reject its *infra* (pgvector, its own embedding models, its Node service, its English FTS tokenizer). See §8.
- **Coverage = both draft and canon, clearly distinguished.** Every result is labelled by **surface** (`draft` vs `canon`) so the feature serves both the authoring aid (drafts) and canon excerpting (published).
- **Fusion = RRF, not weighted blend.** Our two legs read from different stores on incomparable score scales (Neo4j cosine vs Postgres trigram/`ts_rank`); rank-based Reciprocal Rank Fusion is robust where free-context-hub's `sem + 0.30·fts` would not be. This is the one place we deliberately improve on the reference. See §3.4.

**Rejected** (detail in §8): integrating **mem0** (it is a *lossy LLM-extraction* memory layer — the exact "derivative product" problem we are escaping, plus it duplicates the vector infra); adopting **mempalace** wholesale (right *philosophy* — raw verbatim, not extraction — but wrong *infra*: local ChromaDB/SQLite, single-user, contradicts the cloud / multi-tenant / per-service-Postgres model).

## 3. Design

### 3.1 Two text surfaces per chapter (the core data model)

A chapter has two distinct raw-text surfaces, and they can diverge:

| Surface | Source of truth | Freshness | Granularity available |
|---|---|---|---|
| **draft** (working copy) | `chapter_blocks.text_content` (denormalized from `chapter_drafts.body` Tiptap JSONB) | always current | per-block (`block_index`, `heading_context`) |
| **canon** (published) | the **pinned** revision: `chapter_revisions.body` where `chapters.published_revision_id` matches; chapter has `editorial_status='published'` | frozen at publish | per-revision JSONB (not pre-segmented) |

For a chapter unedited since publish, the two coincide; for one edited after publish they differ. The feature treats them as **two labelled surfaces**, never silently conflating them. `editorial_status` (`draft|published`, CHECK-constrained) + `published_revision_id` are the discriminators.

> **Labeling rule (eval TP1/R3 — §14):** a hit's `surface` is derived from **which text source produced it**, never from `chapters.editorial_status`. Text from `chapter_blocks` ⇒ **always** `surface=draft`; text from the pinned revision ⇒ **always** `surface=canon`. Rationale: a chapter edited after publish stays `editorial_status='published'` while its `chapter_blocks` holds uncommitted draft text — labeling by status would present draft prose as canon (a provenance/fidelity violation, QA1).

> **Open scope decision (see §10):** the lexical leg over the **canon** surface requires block-segmenting the published revision JSONB (it is not in `chapter_blocks`, which tracks the *draft*). Phase 2 chooses between (a) projecting published-revision text into a `chapter_revision_blocks`-style table at publish time (full "both" lexical), or (b) shipping **draft-lexical + canon-semantic** first and deferring canon-lexical. Recommendation: (b) for Phase 1–2, (a) as a Phase-2 add if canon exact-match proves needed.

### 3.2 Lexical leg — `book-service` (Go), always-fresh, zero embedding cost

Owns the raw text, so the keyword/exact leg lives here. This is the **high-frequency authoring path** (exact proper nouns, artifact names, specific phrases) and it covers **drafts instantly** — no publish, no embedding required.

> **Freshness — confirmed transactional (2026-06-07).** `chapter_blocks` is maintained by the trigger `trg_extract_chapter_blocks AFTER INSERT OR UPDATE OF body ON chapter_drafts` (`migrate.go` §`triggerSQL`), which JSON_TABLE-extracts each block's `_text` + fills `heading_context` in the **same transaction as the draft save**. So the lexical index is as fresh as the last committed keystroke-save — no async lag — and it reads `chapter_drafts.body`, never revisions ⇒ `chapter_blocks` is **strictly the draft surface** (reinforces the §3.1 labeling rule).

- **Index:** `CREATE EXTENSION IF NOT EXISTS pg_trgm;` then a GIN trigram index on the draft surface:
  `CREATE INDEX idx_chapter_blocks_trgm ON chapter_blocks USING gin (text_content gin_trgm_ops);`
  (`pg_trgm` ships in `postgres:18-alpine`'s contrib — just needs the `CREATE EXTENSION`.)
- **Why trigram, not `to_tsvector`:** the demo corpus is **封神演义 (Classical Chinese)**. `to_tsvector('english'|'simple', …)` has no CJK word segmentation → near-useless recall. **Character trigrams** match CJK substrings/exact terms (e.g. `乾坤圈`) and accelerate `ILIKE '%term%'` + `similarity()` ranking. See §3.7.
- **Dual-mounted handler** (same SQL, two routes — §3.5):
  - external `GET /v1/books/{book_id}/search?q=&surface=&limit=&mode=lexical` — JWT + `ensureOwnerBook` (book-service's existing ownership check; this is the resilient, always-available path the FE hits directly);
  - internal `GET /internal/books/{book_id}/lexical-search?q=&surface=&limit=` — `X-Internal-Token` only, **caller-trusted** (book-service `/internal/*` does not re-check ownership — confirmed pattern; the knowledge orchestrator already established ownership via project-resolve before calling).
  - response: `{ hits: [ { chapter_id, sort_order, surface, block_index, heading_context, snippet, char_start, char_end, score } ] }`.
  - `score` = `similarity(text_content, $1)` (trigram) plus an exact-substring boost; query is parameterized (`$1`) and length-capped (SP5).
  - `snippet` = the matched block's `text_content` (or a windowed excerpt around the match) — **verbatim**, with `char_start/char_end` for highlight + jump-to-source.
  - **v1 surface:** lexical hits are `surface=draft` only (chapter_blocks is the draft surface). `surface=canon` for the lexical leg needs the canon projection (§3.1 open #2 — deferred). `surface` param still accepted for forward-compat; `canon`/`all` simply yield draft hits in v1.

### 3.3 Semantic leg — `knowledge-service` (Py), reuse the `:Passage` layer as-is

For conceptual recall ("the scene where X happens") where keywords fail. **Reuse, do not rebuild.**

- `find_passages_by_vector(session, user_id=…, project_id=…, query_vector=…, dim=…, embedding_model=…, source_type="chapter", limit=…)` already exists and is dim-routed, tenant-scoped, with hub-penalty + MMR in the selector layer (P-K18.3-02). Filter `source_type="chapter"` to scope to chapter prose (excludes `chat`/`glossary` passages).
- **Coverage = canon** by default (passages ingest on `chapter.published`). This aligns: lexical→draft, semantic→canon, both legs cover the published overlap.
- **Embedding** via the existing BYOK `EmbeddingClient` + the shared **query-embedding cache** (`app/context/query_embedding.py::embed_query_cached`) — one embed per `(user, project, model, query)` window, same as mui #4.
- **Optional Phase 3:** widen passage ingestion to **drafts** (debounced or on-demand "index this draft") to get semantic-on-draft. Deferred because draft churn × re-embedding is a real cost; debounce/lazy is the mitigation.

### 3.4 Orchestration + fusion + dedup — `knowledge-service` (external endpoint)

The hybrid/semantic orchestrator owns query embedding, both legs, and fusion (knowledge-service already has the embedding + vector machinery; book-service has neither). **Confirmed wiring (2026-06-07):** the gateway is a pure path-proxy and cannot branch on `?mode=`, so this is a **JWT-gated external** knowledge endpoint (the gateway already proxies `/v1/knowledge/*`), not an internal one.

`GET /v1/knowledge/books/{book_id}/search?q=&mode=hybrid|semantic&surface=&limit=` → `{ results: [SearchHit], degraded: {…} }`

Flow:
1. **Resolve + authorize in one step.** Look up the caller's project for this book — `knowledge_projects WHERE user_id = <jwt sub> AND book_id = {book_id}` (resolver exists, `projects.py`). The row **is** the ownership gate *and* the source of `embedding_model` / `embedding_dimension`. **No project ⇒ `404 not_indexed`**: the book has no semantic index anyway, so the FE falls back to the lexical endpoint (§3.5), which enforces ownership itself.
2. Run the requested legs **in parallel**:
   - lexical → `BookClient` HTTP to book-service `/internal/books/{book_id}/lexical-search` (§3.2) — the existing client already carries `X-Internal-Token`;
   - semantic → embed query (cached) → `find_passages_by_vector(source_type="chapter")` (§3.3).
3. **Fuse with RRF.** For each leg's ranked list, `rrf(d) = Σ_legs 1/(k + rank_leg(d))`, `k = 60`. Rank-based ⇒ immune to the cosine-vs-trigram scale mismatch.
4. **Dedup + diversity.** v1 dedup key = `(chapter_id, surface)` with a **per-chapter cap** (≤ 2–3 hits/chapter, free-context-hub's per-file-cap idea) so one chapter can't flood top-k; a hit found by both legs → `match_type="both"` (keeps the higher RRF contribution). Reuse the selector's MMR for intra-semantic-leg redundancy.
   - **Phase 3:** finer char-offset overlap dedup (merge a lexical block hit with the semantic chunk covering it) — needs passages to store char offsets at ingest; deferred.
5. Truncate to `limit`, attach labels, return.

### 3.5 API surface & resilience — two endpoints, FE picks by mode

The gateway proxies by **path only** (`/v1/books/*` → book-service, `/v1/knowledge/*` → knowledge-service) and injects no internal token. So instead of one gateway-routed endpoint, the design uses **two first-class external endpoints, each owning its own auth**, both already reachable through the existing proxy — no new gateway logic:

| Mode | Endpoint | Service | Auth | Always-available? |
|---|---|---|---|---|
| `lexical` | `GET /v1/books/{id}/search` | book-service | JWT + `ensureOwnerBook` | **Yes** — no embeddings, no Neo4j, draft-fresh |
| `hybrid` / `semantic` | `GET /v1/knowledge/books/{id}/search` | knowledge-service | JWT + project-resolve (§3.4) | only when a project exists + semantic stack up |

Common params: `q` (required), `surface` (`draft\|canon\|all`, default `all`), `limit` (default 20, max 100). → `200 { query, mode, results: [SearchHit], degraded?: {…} }`.

The book-service lexical handler is **dual-mounted**: external `/v1/books/{id}/search` (ownership-checked) **and** internal `/internal/books/{id}/lexical-search` (token-gated, caller-trusted) — same query, two callers (FE direct vs the knowledge orchestrator).

**Resilience (degradation, not error), needs no gateway logic:** the FE calls the knowledge endpoint for `hybrid`; on `404 not_indexed` (no project) or `503` (the gateway already emits a structured 503 when knowledge-service is down) it **falls back to `GET /v1/books/{id}/search`** (lexical-only). A total semantic-stack outage still leaves raw search working via book-service. Inside the knowledge endpoint, a failed semantic leg degrades to lexical-only + a `degraded` note; never a 500.

### 3.6 Result shape (built for excerpting)

```jsonc
SearchHit {
  chapterId, chapterTitle, sortOrder,
  surface,        // "draft" | "canon"
  matchType,      // "lexical" | "semantic" | "both"
  score,          // fused RRF score (display/debug only)
  snippet,        // VERBATIM excerpt — the raw sentences
  highlights,     // [[start,end]…] char offsets within snippet (the matched span)
  location: { blockIndex?, chunkIndex?, charStart, charEnd },
  revisionId?     // present only when surface === "canon"
}
```

The verbatim `snippet` + `location` + `revisionId` are what make this usable for 創作/trích lục: copy the exact quote, or jump to the precise spot in the editor/reader.

### 3.7 CJK strategy (project-specific — corpus is 封神演义)

- **Lexical leg:** `pg_trgm` character trigrams (§3.2). Caveat: trigram padding weakens recall on 1–2-char terms; serviceable for v1 exact/substring hunting. **Noted alternatives for a future phase** if linguistic tokenization is needed: a CJK FTS parser (`zhparser` / `pg_jieba`) — extra extension, not in the base image; or a Neo4j Lucene full-text index with `SmartChineseAnalyzer` co-located with passages.
- **Semantic leg:** handled natively **iff** the project's BYOK embedding model is multilingual. **Confirm-at-BUILD:** verify the registered model (e.g. bge-m3 / qwen3-embedding / multilingual-e5 all handle Chinese well).

### 3.8 Multi-tenant + graceful degradation matrix

Every leg is tenant-scoped: passages filter `user_id` (built-in); book-service verifies book ownership at the gateway. A user can only ever search their own book.

| Condition | Result |
|---|---|
| all healthy, `mode=hybrid` | lexical + semantic, RRF-fused |
| project has no embedding model / extraction never ran | semantic empty → **lexical-only results** (not a fallback-of-last-resort here — lexical is a first-class leg) |
| embed call / Neo4j down | lexical-only + `degraded.semantic` |
| book-service lexical down | semantic-only + `degraded.lexical` |
| knowledge-service entirely down | gateway routes `mode=lexical` direct to book-service (resilience path, §3.5) |
| both legs down | `200 { results: [], degraded: {…} }` — never 500 |

## 4. Acceptance criteria

- **AC1 (draft lexical, no publish):** an exact CJK term (e.g. `乾坤圈`) typed into a **draft** chapter is found via the lexical leg with `surface="draft"`, with no publish and no embedding.
- **AC2 (canon semantic):** a semantically-related query with **no lexical overlap** returns the right **published** passage via the semantic leg.
- **AC3 (hybrid fuse):** `mode=hybrid` returns both, RRF-fused, deduped, each labelled `surface` + `matchType`; a region hit by both legs shows `matchType="both"`.
- **AC4 (surface filter):** `surface=draft|canon|all` scopes correctly.
- **AC5 (resilience):** with knowledge-service/Neo4j down, `mode=lexical` still returns results via book-service; hybrid degrades to lexical-only without 500.
- **AC6 (excerpting):** every hit carries a verbatim `snippet` + precise `location` (and `revisionId` for canon) sufficient for copy-quote and jump-to-source.
- **AC7 (tenant isolation):** user A cannot retrieve any hit from user B's book.
- **AC8 (CJK):** search works on the Chinese corpus (trigram lexical + multilingual semantic), not only English.

## 5. Phasing (each independently shippable; re-classify size at its own PLAN)

| Phase | Scope | Value |
|---|---|---|
| **1 — Lexical MVP** | book-service: `pg_trgm` migration + `idx_chapter_blocks_trgm` + the **external** `GET /v1/books/{id}/search` handler (JWT + `ensureOwnerBook`, draft surface, custom CJK highlight); minimal FE result list + jump-to-source. No gateway change (gateway already proxies `/v1/books/*`). | Ships the #1 authoring need — **exact-term hunt on live drafts** — at **zero embedding cost**, fully self-contained in book-service + FE. |
| **2 — Hybrid** | knowledge orchestrator `GET /v1/knowledge/books/{id}/search` (project-resolve auth) + RRF fusion + dedup; book-service **internal** mount `/internal/books/{id}/lexical-search` + `BookClient.lexical_search`; FE match-type chips + degraded banner + lexical fallback on 404/503. Decide canon-lexical projection here (§3.1 open #2). | Adds conceptual recall over canon; the full hybrid. |
| **3 — Polish** | char-offset cross-leg dedup; semantic-on-draft (debounced/on-demand ingest); optional LLM rerank (free-context-hub pattern); snippet highlight for CJK; copy-excerpt UX. | Quality + completeness. |

**VERIFY (cross-service ⇒ live-smoke required, CLAUDE.md):** Phase 2+ touches ≥2 services → evidence token e.g. `live smoke: hybrid raw-search returns a CJK draft lexical hit + a canon semantic hit, RRF-fused, on a stacked-up book`.

## 6. Frontend (Phase 1 minimal, grows in 2–3)

Per the React-MVC rules (`features/raw-search/` with `hooks/` controllers, `context/` shared state, `components/` render-only, `api.ts`, `types.ts`):

- A search surface (modal or side panel) usable from the editor and the reader.
- Result list: verbatim snippet with highlighted match, **status badge** (`draft` / `published`), **match-type chip** (`lexical` / `semantic` / `both`), jump-to-source, copy-excerpt.
- Mode toggle (lexical / hybrid) + surface filter; a `degraded` banner when a leg is unavailable.
- No localStorage for results; only per-device UI prefs (panel width) may be local, per the data-persistence rules.

## 7. Risks

- **R1 — pg_trgm CJK quality.** Trigram padding weakens short-term recall. *Mitigation:* acceptable for v1 exact/substring; `zhparser`/Lucene-CJK noted as a phase-X upgrade (§3.7).
- **R2 — draft↔canon text drift.** Edited-after-publish chapters diverge. *Mitigation:* the two-surface model (§3.1) labels every hit; never conflated.
- **R3 — semantic coverage gaps.** Passages exist only where extraction ran; non-extracted books have no semantic leg. *Mitigation:* degrade to lexical (AC5); lexical needs no extraction.
- **R4 — draft-semantic cost.** Re-embedding on every save is expensive. *Mitigation:* draft-semantic is Phase 3 with debounce/on-demand only.
- **R5 — score-scale heterogeneity.** *Mitigation:* RRF (rank-based), not weighted blend (§3.4).
- **R6 — cost.** One embed per hybrid query. *Mitigation:* reuse the shared query-embedding cache; trivial next to the LLM calls already in authoring paths.

## 8. Alternatives considered (the three options weighed at CLARIFY)

| Option | What it is | Verdict |
|---|---|---|
| **mem0** | LLM **extracts** salient "memories" from text and stores the processed facts; retrieval returns the *extracted* memories, not the source. | **Rejected — wrong category.** It is itself a *lossy derivative* layer — precisely the problem we're escaping — and would add a 4th such layer. Also duplicates the Neo4j vector infra and adds an external dependency contrary to the no-lock-in / per-service model. |
| **mempalace** | Raw-verbatim memory tool; "store everything, make it findable" (explicitly *not* extraction). ChromaDB + local SQLite, single-user, zero-API embeddings. | **Philosophy adopted, infra rejected.** The raw-verbatim stance is exactly right and validates our approach. But ChromaDB / local SQLite / single-user contradicts the cloud-hosted, multi-tenant, per-service-Postgres + Neo4j model (CLAUDE.md). Borrow the *idea*, not the code. |
| **free-context-hub** | Hybrid **pgvector (semantic) + Postgres FTS (lexical) + RRF/weighted blend + MMR + optional LLM rerank** over raw content; the source of the ContextHub MCP. | **Techniques adopted, re-implemented in our stack; not a dependency.** Take: two-leg hybrid, MMR diversity, query token-expansion, graceful degradation, per-source capping. Reject its infra: pgvector (→ our Neo4j), its embedding models (→ BYOK provider-registry), its Node service (→ Python in knowledge-service), its English FTS tokenizer (→ `pg_trgm` for CJK). **Improve on it:** RRF instead of weighted blend, justified by heterogeneous backends (§3.4). |

## 9. Non-goals

- Not replacing glossary / knowledge / wiki — they remain the derived layers; this adds the missing **raw** layer beneath them.
- Not a new vector store — reuse Neo4j.
- Not an LLM extraction / memory layer — this is deliberately the **opposite**: lossless raw retrieval.
- Not external search infra (Elasticsearch / Qdrant / etc.) — Postgres + Neo4j only, per the no-lock-in rule.

## 10. Confirm-at-BUILD — RESOLVED (2026-06-07, design locked)

All seven cleared by code investigation. The design above already reflects these.

1. **`chapter_blocks` freshness** — ✅ **DB trigger**, transactional. `trg_extract_chapter_blocks AFTER INSERT OR UPDATE OF body ON chapter_drafts` re-extracts blocks in the same Tx as the draft save (`migrate.go` §`triggerSQL`). Freshness = last committed save, no lag. `chapter_blocks` is strictly the **draft** surface (§3.2). ⇒ lexical leg is draft-fresh for free.
2. **Canon-lexical projection** — ✅ **Locked: defer.** Ship **draft-lexical + canon-semantic** (Phases 1–2); the published-revision block projection (full "both" lexical) is a Phase-2/3 add only if canon exact-match proves needed. `chapter_blocks` cannot serve canon (it tracks `chapter_drafts.body`); canon-lexical would require extracting `chapter_revisions.body` at publish. Reversible decision.
3. **`knowledge_projects` fields** — ✅ Confirmed columns `book_id`, `embedding_model`, `embedding_dimension` on `knowledge_projects` (`projects.py`), with a by-`book_id` resolver. `embedding_model` is a provider-registry model ref; routes to `passage_embeddings_{embedding_dimension}`. Same resolver as mui #4.
4. **Authz flow** — ✅ Confirmed. book-service `/internal/*` = `X-Internal-Token` (`INTERNAL_SERVICE_TOKEN`), **caller-trusted, no ownership re-check**; `/v1/*` = JWT (`sub`) + `ensureOwnerBook`. Gateway = pure path-proxy, forwards JWT, no token injection. ⇒ external lexical endpoint self-checks ownership; knowledge orchestrator establishes ownership via project-resolve *before* calling the internal lexical route (§3.4–3.5).
5. **`mode=lexical` route** — ✅ **Resolved better than asked.** The gateway *can't* branch on `?mode=` (path-proxy only), so lexical is its **own first-class book-service external endpoint** `/v1/books/{id}/search` (already proxied) and the FE falls back to it on knowledge `404 not_indexed` / `503`. No gateway logic; resilience is structural (§3.5). Clears eval **R6**.
6. **CJK snippet highlight** — ✅ **Locked: custom offset highlight.** `ts_headline` is FTS/`tsvector`-oriented and weak for trigram/CJK; the lexical handler computes match `char_start/char_end` itself (exact substring locate — needs no tokenization for CJK) and returns ranges; FE renders. (§3.2, SP—not a knob, just a method.)
7. **Embedding model multilinguality** — ✅ **Runtime/BYOK, handled by degradation.** No hardcoded default (per the no-hardcoded-model rule); the design degrades cleanly if the model is non-multilingual or absent (semantic→empty→lexical). **Onboarding recommendation:** a multilingual model for CJK projects — `bge-m3` already appears in provider-registry tests (known-good in this stack); `qwen3-embedding` / `multilingual-e5` also fit. Billing already has CJK-aware token divisors. *Track as a setup recommendation, not a code gate.*

---

# PART II — SCENARIO-BASED EVALUATION (ATAM-lite)

Method (house style, mirrors `GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md` §7-10): derive prioritized quality attributes → write concrete scenarios (`stimulus → architectural response → measure`) → walk each through the design in PART I → extract **Sensitivity points / Tradeoff points / Risks / Non-risks** → verdict. Scope = the raw-search design (lexical leg + semantic-leg reuse + RRF orchestration), Phases 1–3.

## 11. Design invariants (what the evaluation holds the design to)

- **INV-1 — Verbatim.** A returned snippet is byte-equal to its source text; search never normalizes/paraphrases stored prose. (raw, lossless — the whole point.)
- **INV-2 — Provenance.** Every hit carries a `surface` (`draft|canon`) derived from its text source (§3.1 labeling rule); draft text is never presented as canon.
- **INV-3 — Degrade, never 500.** Any leg / infra down → return available results + a `degraded` note. (mirrors glossary INV-4.)
- **INV-4 — Tenant-scoped.** All retrieval filters `user_id` + verified book ownership. No cross-tenant hit. (mirrors glossary INV-5.)
- **INV-5 — Additive, no new lossy layer, no new datastore.** Lexical reuses Postgres; semantic reuses the existing Neo4j `:Passage` layer. Raw search sits *beneath* glossary/knowledge/wiki, never becomes another derivative.
- **INV-6 — Config/registry-resolved.** Embedding model, CJK parser choice, RRF params, timeouts — never hardcoded. (mirrors glossary INV-6.)

## 12. Quality attributes (prioritized)

| # | Attribute | Why it dominates here |
|---|---|---|
| QA1 | **Verbatim fidelity & provenance** | The product use is *quoting/excerpting* — a paraphrased snippet or a draft-labeled-canon hit is the worst outcome. |
| QA2 | **Retrieval quality (recall + precision)** | If it doesn't surface the passage, the feature is dead weight; both legs must pull their weight. |
| QA3 | **Latency (interactive)** | An authoring aid used mid-sentence must feel instant or it goes unused. |
| QA4 | **Freshness (draft immediacy)** | The authoring loop searches text typed seconds ago; a stale index gives wrong answers. |
| QA5 | **Availability / graceful degradation** | Multi-service; embedding provider / Neo4j / knowledge-service may each be down. |
| QA6 | **CJK / multilingual correctness** | Corpus is Classical Chinese (封神演义); naive English tokenization is useless. Project-defining. |
| QA7 | **Cost** | Embedding $ per query + re-embedding churn if drafts are vectorized. |
| QA8 | **Architectural integrity (lossless, decoupled, SoC)** | The user's explicit design goal: stay raw, don't duplicate infra, don't couple to the derivative pipeline. |
| QA9 | **Modifiability / extensibility** | Swap embedding model, add CJK parser, add rerank, add canon-lexical, scale to many books. |
| QA10 | **Security / multi-tenancy** | Per-user/book isolation; lexical leg takes a raw user query (injection surface). |

## 13. Scenarios & walkthroughs

**S1 — Exact CJK term hunt in a draft (QA1, QA4, QA6). [use]**
*Stimulus:* author types `乾坤圈` into the search box while editing an unpublished chapter. *Response:* lexical leg, `pg_trgm` over `chapter_blocks` (live draft), no publish/embed. *Measure:* term found, `surface=draft`, latency < ~300ms. → **Satisfied**; recall on short CJK terms rests on trigram quality (**SP1**, **R1**). The #1 authoring path, fully decoupled from the AI pipeline (**NR2**).

**S2 — Semantic recall over canon, no lexical overlap (QA2, QA6). [use]**
*Stimulus:* "the scene where 哪吒 defies his father" (none of those exact words in the prose). *Response:* semantic leg embeds query → `find_passages_by_vector(source_type="chapter")` over published passages. *Measure:* the right passage in top-k. → **Feasible iff** the BYOK model is multilingual (**SP3**) *and* passages were ingested (**R-coverage/S10**). Reuses proven infra (**NR4**).

**S3 — Hybrid query fuses both legs (QA2). [use]**
*Stimulus:* a query that is part proper-noun, part concept. *Response:* both legs run; RRF merge; per-chapter cap; `match_type` labeling. *Measure:* both surfaces represented, `both` where they overlap, no single chapter flooding top-k. → **Satisfied**; ranking quality is sensitive to RRF `k` + per-chapter cap (**SP2**) and to the lexical/semantic balance (**TP-leg-balance folded into SP2**).

**S4 — Copy-exact for extraction (QA1). [stress]**
*Stimulus:* user copies a returned snippet to quote verbatim. *Response:* lexical snippet = `chapter_blocks.text_content` span with exact `char_start/end`; semantic snippet = `passage.text` (chunk-bounded, ~1500c, overlapped). *Measure:* copied text == source span. → **Satisfied for the lexical leg** (exact spans). **RISK for the semantic leg** (**R2**): chunk-bounded hits are not match-bounded and lack exact char offsets until Phase 3 → semantic hits should *jump-to-source*, not promise copy-exact-span. Sharpest fidelity tension (**TP2**).

**S5 — Chapter edited after publish (QA1 provenance). [stress]**
*Stimulus:* a published chapter is edited (new draft text), not re-published; user searches a term in the new text. *Response:* it lives in `chapter_blocks` but `editorial_status` is still `published`. *Measure:* is the hit labeled draft or canon? → **RISK if labeled by status** (**R3**): would present uncommitted draft as canon. **Mitigated** by the §3.1 labeling rule (surface = text-source, not status) (**TP1**). Must be tested explicitly.

**S6 — Swap embedding model / dimension (QA9, QA5). [growth]**
*Stimulus:* user changes the project's embedding model (1024→1536). *Response:* query routes to `passage_embeddings_{dim}`; passages must be rebuilt (model change ⇒ delete+rebuild, inherited mui#4 constraint). *Measure:* correct semantic hits post-reindex. → **Satisfied for routing** (dim-routed); semantic leg is **down until reindex** (**SP3**) — but lexical leg is model-independent, so search stays useful throughout (**NR2**, integrity payoff).

**S7 — Large corpus (QA3, QA2). [growth]**
*Stimulus:* a 5,000-chapter book; lexical + semantic search. *Response:* `pg_trgm` GIN for substring/similarity; Neo4j ANN for vectors. *Measure:* latency at scale. → semantic ANN is sublinear (fine); **lexical RISK** (**R4**): low-selectivity CJK trigrams (common characters) over a huge table can be slow. *Mitigation:* GIN + `limit` + per-chapter cap; monitor; optional chapter-range scope.

**S8 — Embedding provider slow/down (QA5, QA3). [stress]**
*Stimulus:* `/internal/embed` stalls (the ingestion path allows 30s). *Response:* hybrid should degrade to lexical-only + `degraded.semantic`. *Measure:* response still 200 within lexical latency. → **Satisfied** (INV-3) **but** the 30s ingestion timeout is wrong for interactive search (**SP4**, **R7**): needs a tight interactive embed timeout that fails fast to lexical, or hybrid feels broken before it degrades.

**S9 — knowledge-service / Neo4j entirely down (QA5, QA8). [stress]**
*Stimulus:* the whole semantic stack is offline. *Response:* lexical is its own book-service external endpoint `/v1/books/{id}/search` (separately proxied); the FE falls back to it on the knowledge endpoint's `503`. *Measure:* lexical search still works. → **Satisfied — structurally** (resolved, §3.5): resilience is two independent endpoints in two services, not a conditional gateway route. **R6 cleared.**

**S10 — Project never ran extraction (QA8, QA5). [exploratory]**
*Stimulus:* a book imported with no KG/extraction/embeddings. *Response:* semantic leg returns empty → lexical-only. *Measure:* search still useful. → **Satisfied** — lexical needs no extraction, no embedding, no publish. This is the core integrity result: **raw search's primary leg is independent of the entire derivative pipeline** (**NR1/NR2**, QA8).

**S11 — Cross-tenant isolation (QA10). [stress]**
*Stimulus:* user A's query — could it return user B's book? *Response:* semantic filters `user_id`+`project_id` (built-in); lexical scoped by `book_id` with a gateway ownership check before the internal call. *Measure:* zero cross-tenant hits. → **Satisfied iff** book-service ownership is verified at the gateway (**R5**) — the internal token is a service gate, not the authz boundary (mirrors glossary R7).

**S12 — Injection / pathological query (QA10, QA7). [stress]**
*Stimulus:* query contains SQL/Cypher metacharacters or a 10k-char paste. *Response:* lexical uses parameterized `$1` + `similarity()`/`ILIKE` (no string-built SQL); query length-capped; semantic just embeds the text. *Measure:* no injection; bounded cost. → **Satisfied** with a query-length cap (**SP5**); `passages.py` already uses closed-set dim substitution (injection-safe) (**NR5**).

**S13 — Add LLM rerank later (QA9, QA2). [growth]**
*Stimulus:* Phase 3 adds a rerank pass on fused top-k (free-context-hub pattern). *Response:* additive stage after fusion; optional, cached, degradable. *Measure:* localized effort, budgeted latency. → **Satisfied** (additive); **TP5**: quality uplift ↔ interactive latency+cost. Default off.

*(Out of scope, noted: cross-book "search all my books" (QA9) is per-book today; it's a fan-out + merged-ranking add, feasible without redesign — future.)*

## 14. Findings

### Sensitivity points (single knobs that swing a quality attribute)
- **SP1 — CJK lexical tokenization (`pg_trgm`).** Swings QA6/QA2. Trigram is the *only* lexical signal; short-term CJK recall rests on it. Keep a config upgrade path (`zhparser`/`pg_jieba`/Lucene-CJK).
- **SP2 — RRF params (`k` + per-chapter cap).** Swings QA2. The single ranking knob: leg balance and anti-flooding. Must be config.
- **SP3 — per-project embedding model/dimension** (inherits mui#4 SP4). Swings QA2/QA6 and semantic-leg availability during reindex.
- **SP4 — interactive embed timeout.** Swings QA3 vs QA2-semantic-recall. The 30s ingestion value is wrong here; needs a separate short interactive budget.
- **SP5 — query length cap.** Swings QA7/QA10 vs usability.

### Tradeoff points (one decision pulls two attributes opposite ways)
- **TP1 — surface label source.** Provenance correctness (QA1) ↔ implementation simplicity. *Resolved:* §3.1 rule — surface = text-source, never `editorial_status`.
- **TP2 — semantic-snippet fidelity vs chunk granularity.** Copy-exact extraction (QA1) ↔ chunk-bounded passages. Lexical is the fidelity leg; semantic char-offsets are a Phase-3 gate (R2).
- **TP3 — lexical-leg placement (book-service).** Resilience + freshness + decoupling (QA4/QA5/QA8: always-fresh, draft-covering, survives AI outage) ↔ one cross-service HTTP hop per hybrid query (QA3). *Accepted:* the integrity/resilience win dominates a single local call.
- **TP4 — surface×leg coupling in v1.** Cost/simplicity (ship draft-lexical + canon-semantic) ↔ completeness (no canon-exact-match, no draft-semantic until Phase 3). The two dimensions are *aliased* in v1 — FE/UX must not promise canon exact-match yet.
- **TP5 — rerank (Phase 3).** QA2 uplift ↔ QA3/QA7. Default off.

### Risks
- **R1 — CJK trigram recall** on short terms (S1, S7). *Mitigation:* acceptable v1; measure recall on 封神演义 at Phase-1 VERIFY; parser upgrade path held open (SP1).
- **R2 — semantic snippets not copy-exact** (S4, TP2). *Mitigation:* semantic hits jump-to-source, not copy-span, until passage char-offsets land (Phase 3).
- **R3 — surface mislabeling** (S5, TP1). *Mitigation:* §3.1 source-derived rule; explicit post-publish-edit test.
- **R4 — trigram perf at scale** (S7). *Mitigation:* GIN + limit + per-chapter cap; monitor; chapter-range scope option.
- **R5 — lexical-leg authz** (S11). *Mitigation:* gateway ownership check before book-service `lexical-search`; cross-tenant test.
- **R6 — resilience routing** (S9). ✅ **Cleared at design-lock:** lexical is a first-class book-service external endpoint (`/v1/books/{id}/search`), separately proxied; FE falls back to it on knowledge `404/503`. No gateway logic, no special route to "not build" — resilience is structural.
- **R7 — interactive latency from 30s embed timeout** (S8). *Mitigation:* separate short interactive timeout; fail-fast to lexical.

### Non-risks (explicitly cleared)
- **NR1 — no new datastore / no new lossy layer** (S10, INV-5): lexical = existing Postgres, semantic = existing Neo4j passages. Purely additive.
- **NR2 — lexical decoupled from the AI pipeline** (S6, S10): the primary leg needs no extraction/embedding/publish. The core integrity goal (QA8) is architecturally native, not bolted on.
- **NR3 — graceful degradation** (S8, S9): established house pattern; reused (INV-3).
- **NR4 — semantic infra reuse** (S2): `find_passages_by_vector` + dim routing + shared query-embedding cache are battle-shaped from mui#4.
- **NR5 — injection** (S12): parameterized lexical query + closed-set dim substitution already safe.

## 15. Verdict

The design is **sound and strongly additive.** It adds the missing **raw** layer with no new datastore, no new lossy layer, and — decisively — its primary leg (lexical) **fully decoupled from the derivative AI pipeline** (S10/NR2). The two dominant goals, verbatim fidelity (QA1) and architectural integrity (QA8, "stay raw, don't add another derivative"), are protected natively, not patched in.

Unlike glossary mui#1c, **risk is *not* concentrated in the reused semantic machinery** (proven) — it sits in three smaller, addressable places:
1. **Provenance labeling** (TP1/R3) — resolved by the §3.1 source-derived rule; needs a test.
2. **Semantic-snippet fidelity for extraction** (TP2/R2) — lexical is the fidelity leg; semantic = jump-to-source until Phase-3 char-offsets.
3. **CJK lexical quality** (SP1/R1) — trigram is serviceable but unproven on Classical Chinese; measure early.

**Phase 1 (lexical MVP) is the correct first slice:** lowest-risk, highest-frequency value, decoupled from every fragile dependency, and it exercises the CJK question (R1) exactly where course-correction is cheapest.

**Recommendations**
- Lock **SP1–SP5** as config (CJK parser, RRF `k`/cap, interactive embed timeout, query cap), per INV-6.
- Build the **resilience direct-route** (R6) inside Phase 1 — it is cheap and it is the integrity payoff.
- Add a **CJK recall measurement on 封神演义** to Phase-1 VERIFY (R1).
- Gate "copy-exact from semantic hits" on **Phase-3 passage char-offsets** (R2); ship jump-to-source first.
- This feature does **not** warrant `/amaw`: additive, non-destructive, reversible, no schema-destruction (contrast glossary #1c). A standard 2-stage REVIEW at Phase 2 (cross-service ⇒ live-smoke) is sufficient.
- **Proceed to PLAN for Phase 1** once the §10 confirm-at-BUILD items #1, #3, #4, #5 are answered.
