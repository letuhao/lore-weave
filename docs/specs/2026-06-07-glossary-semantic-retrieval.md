# Spec — Glossary Semantic Retrieval (mui #4)

- **Date:** 2026-06-07
- **Branch:** `glossary/ai-pipeline-v2`
- **Phase:** CLARIFY ✅ (PO locked decisions 2026-06-07) → DESIGN.
- **Parent architecture:** `docs/03_planning/GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md` (mui #4).
- **Size:** **L** — knowledge-service + glossary-service + composition-service; 2 new internal endpoints; embedding call; fallback paths. Cross-service ⇒ live-smoke at VERIFY.

---

## 1. Problem

`select-for-context` (called by chat context-build and composition's packer) ranks entities **lexically** (Postgres FTS `simple` + exact/pinned/recent tiers). For CJK especially, `simple` FTS has no segmentation → weak recall. knowledge-service already computes **entity embeddings** (Neo4j vector indexes, anchored to glossary via `glossary_entity_id`) but **nothing uses them to rank entities for context** — `find_entities_by_vector` exists yet is unused for this. Result: the AI ecosystem has the signal; the retrieval path ignores it.

## 2. Decision (CLARIFY locked)

- **Architecture = B:** semantic ranking lives in **knowledge** (where the embeddings are). knowledge embeds the query → `find_entities_by_vector` → glossary-anchored ids → fetches glossary details by id → returns ranked entities. **No knowledge→glossary→knowledge circular call.** glossary's FTS `select-for-context` stays as the **fallback**.
- **Scope v1 = chat + composition** both adopt the semantic path, each with FTS fallback.
- Rejected: A (vector tier inside glossary endpoint → coupling + circular call), C (glossary pgvector → duplicates embedding infra).

## 3. Design

### 3.1 New glossary endpoint — batch fetch by ids
`POST /internal/books/{book_id}/entities/by-ids` · body `{ "entity_ids": ["…"] }` → `{ "items": [GlossaryEntityForContext] }`.
- Returns the **same item shape** as `select-for-context` (`entity_id, cached_name, cached_aliases, short_description, kind_code`) for the requested ids that exist + are alive/active in this book. `tier`/`rank_score` omitted (caller owns ranking).
- Order is **not** significant (caller re-orders by its scores); missing ids silently dropped (soft-absent, like DI3).
- Internal-token gated. This is the only glossary change.

### 3.2 New knowledge internal endpoint — semantic glossary selection
`POST /internal/context/glossary-semantic` *(lives on the existing context router, K-1 done)* · body `{ user_id, project_id, query, max_entities, max_tokens }` → `{ items: [GlossaryEntityForContext-with-score] }`.
Flow:
1. Resolve project → `book_id`, `embedding_model`, `embedding_dimension` (knowledge_projects). If no embedding model / extraction never ran → return `{items: []}` (signals caller to fall back).
2. `EmbeddingClient.embed(query, model)` → query_vector (per-project model, via provider-registry). Embedding cache reused (existing L3 cache).
3. `find_entities_by_vector(query_vector, dim, user_id, project_id, limit=max_entities·k)` → hits with `glossary_entity_id` (+ cosine·anchor score). Drop hits with `glossary_entity_id IS NULL` (not in glossary SSOT).
4. Call glossary `entities/by-ids` with the ranked ids → enrich to GlossaryEntityForContext.
5. Re-attach scores, order by score, truncate to max_entities/max_tokens. Return.
- Best-effort: any failure (embed down, vector empty, glossary down) → `{items: []}` (never 500). The CALLER does the FTS fallback, so this endpoint stays simple.

### 3.3 Chat path (in-process, knowledge)
`select_glossary_for_context` (selectors/glossary.py): try the **semantic selection first** (same logic as 3.2, called in-process — no HTTP to self). If it returns ≥1 item, use it. Else fall back to the **existing** candidate-extraction + per-keyword FTS path (unchanged). Pinned entities: still want them — append glossary `select-for-context` tier-0 (pinned) results even on the semantic path (pinned is an authoring signal vectors can't represent). *(Design note: keep pinned via a cheap empty-query select-for-context call, merged ahead of semantic hits.)*

### 3.4 Composition path
Packer L1a (`gather_present` / glossary_client): call knowledge `glossary-semantic` endpoint first; on `{items: []}` or error → fall back to the **existing** glossary `select-for-context` call. Composition already calls knowledge for other lenses, so the dependency is not new. Cache the stable glossary `entity_id` (per LOOM rule), never knowledge `canonical_id`.

### 3.5 Fallback matrix (graceful degradation, INV-4)
| Condition | Result |
|---|---|
| project has no embedding model / extraction off | semantic returns [] → caller uses FTS |
| embed call fails | [] → FTS |
| vector search empty (no embedded entities yet) | [] → FTS |
| glossary by-ids fails | [] → FTS |
| all healthy | semantic ranking (vectors) |

## 4. Acceptance criteria

- AC1: a query semantically related to an entity (no lexical overlap, e.g. 「封神之人」→ 姜子牙) ranks it above pure-FTS for an embedded project.
- AC2: project with embeddings OFF → behaviour identical to today (FTS), no errors.
- AC3: pinned entities still appear on the chat semantic path.
- AC4: composition gets semantic ranking when available, FTS otherwise; response shape unchanged (no caller breakage).
- AC5: any single dependency down → no 500, degraded to FTS.
- AC6: only `glossary_entity_id`-anchored entities are returned (no orphan KG nodes leak into glossary context).

## 5. Phasing (verify each)

1. **G-1 (glossary):** `entities/by-ids` endpoint + handler + DB-integration tests (mirrors select-for-context item shape).
2. **K-1 (knowledge):** semantic selection function (embed → vector → by-ids) + `glossary-semantic` internal endpoint; unit tests with mocked embed/vector/glossary (fallback-to-[] on each failure).
3. **K-2 (chat path):** wire `select_glossary_for_context` to semantic-first + pinned-merge + FTS fallback; unit tests for the branch.
4. **C-1 (composition):** packer L1a calls knowledge semantic, FTS fallback; unit tests.
5. **VERIFY:** cross-service live smoke — embedded project, semantic query returns a non-lexical match; token `live smoke: semantic glossary ranking beats FTS on a non-lexical query`.

## 6. Risks (from architecture eval, scoped to #4)
- **TP1 coupling:** composition now depends on knowledge for ranking — mitigated by FTS fallback (AC4/AC5).
- **SP4 embedding model:** per-project model/dimension must route to the right vector index (find_entities_by_vector already dimension-routes).
- **Cost:** one embed per query — reuse the existing embedding cache; cheap vs the LLM calls already in the path.
- This mui also produces the **entity-similarity signal mui #1c (merge detection) needs** — `find_entities_by_vector` entity-to-entity becomes the blocking step there.

## review-impl findings (2026-06-07, all fixed)

- **MED-1 — FIXED:** `select_glossary_semantic` now takes `max_tokens` and trims results by an estimated token cost (parity with FTS select-for-context, which the semantic path was bypassing → glossary block could overrun budget). `_estimate_entity_tokens` (CJK-aware, over-estimate-safe).
- **MED-2 — FIXED:** the same message was embedded 2–3× per Mode-3 build (L3 + summary-blend + new glossary-semantic). Lifted passages.py's P-K18.3-01 query-embedding cache into shared `app/context/query_embedding.py::embed_query_cached`; all three selectors now share one TTL cache → one embed per (user, project, model, message) per window.
- **LOW-1 — FIXED:** added unit tests for the `/internal/context/glossary-semantic` endpoint (project resolution / book_id-None / no-embedding-model → []; happy path).
- Verified non-issues: by-ids has status parity with the FTS tier (both `deleted_at IS NULL` only); AC6 anchor-leak filtered + tested; dim-mismatch degrades.
- Tests: 58 unit green (semantic + endpoint + wiring + query-cache + passages + summary-blend + selector-budget regression).

## 7. Open confirm-at-BUILD
- Exact `VectorSearchHit` fields (confirm `glossary_entity_id` + score present).
- Exact `GlossaryEntityForContext` JSON shape parity between the new by-ids endpoint and select-for-context.
- Where composition's L1a glossary call lives (`packer/lenses.py gather_present`) + its client method.
