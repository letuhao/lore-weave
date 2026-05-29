# Lore-Enrichment — CLARIFY Ground-Truth (bottom-up)

> **Status:** CLARIFY (bottom-up, code-verified) · **Date:** 2026-05-30 · **Branch:** `lore-enrichment/foundation`
> **Why this doc:** RAID only works on a plan built from real system knowledge. The earlier [SERVICE_DESIGN.md](SERVICE_DESIGN.md) was top-down and made unverified assumptions (notably "knowledge-service is planned"). This doc records what ACTUALLY exists (verified by reading code) and re-shapes the boundary before DESIGN/PLAN.

---

## 1. Major corrections vs the top-down draft

1. **knowledge-service is NOT "planned" — it is real and substantial** (Python/FastAPI). Its README says "K0 scaffold only" but that is **stale**; the code base implements a full extraction + KG pipeline. → the two-layer pattern is already partly built, not greenfield.
2. **main already hosts far more services** than CLAUDE.md lists: `game-server`, `world-service`, `tilemap-service`, `travel-service`, `statistics-service`, `notification-service`, `worker-ai`, `worker-infra`, etc. The platform substrate is larger than assumed.
3. **The glossary write-back API is real**: `POST /internal? /books/{book_id}/extract-entities` → `bulkExtractEntities` at [server.go:83](services/glossary-service/internal/api/server.go#L83). Wiki feature lives in [wiki_handler.go](services/glossary-service/internal/api/wiki_handler.go).

## 2. Verified integration surface

### glossary-service (Go) — authored SSOT
- Handlers: [entity_handler.go](services/glossary-service/internal/api/entity_handler.go), [wiki_handler.go](services/glossary-service/internal/api/wiki_handler.go), [extraction_handler.go](services/glossary-service/internal/api/extraction_handler.go), attribute/evidence/chapter-link/kinds/genres/select-for-context handlers.
- Bulk entity write: `POST /books/{book_id}/extract-entities` ([server.go:83](services/glossary-service/internal/api/server.go#L83)).
- Wiki tables (per CLAUDE.md): `wiki_articles`, `wiki_revisions`, `wiki_suggestions`.
- Entity key = the `glossary_entity_id` that knowledge-service anchors to.

### knowledge-service (Python/FastAPI) — fuzzy/semantic KG layer (REAL)
- **Extraction** [app/extraction/](services/knowledge-service/app/extraction/): `entity_detector`, `entity_resolver`, `glossary_sync`, `hierarchy_writer`, `pass2_orchestrator`, `pattern_extractor`, `triple_extractor`, `anchor_loader`, `passage_ingester`, `injection_defense`, `negation`, `tree_merge`.
- **Glossary anchoring** [glossary_sync.py](services/knowledge-service/app/extraction/glossary_sync.py): merges a glossary entity into Neo4j as a high-confidence `:Entity` node; MERGE key `(user_id, glossary_entity_id)`; glossary entities bypass quarantine (confidence=1.0, source_type='glossary'). Triggered by `glossary.entity_updated` events / internal sync / startup reconciler.
- **Neo4j graph** [app/neo4j/](services/knowledge-service/app/neo4j/), [app/db/neo4j_repos/](services/knowledge-service/app/db/neo4j_repos/) (canonical id helpers).
- **Events** [app/events/](services/knowledge-service/app/events/): consumer, dispatcher, gating, handlers.
- **Public routers** [app/routers/public/](services/knowledge-service/app/routers/public/): `entities`, `extraction`, `pending_facts`, `summaries`, `timeline`, `projects`, `drawers`, `costs`, `logs`, `user_data`.
- **Internal routers**: `context` (`/internal/context`), `extraction`, `parse`, `summarize`, `tools`, `admin`, `benchmark`.
- Ports: internal `8092`, host `8216`, gateway `/v1/knowledge/*`. DBs: `loreweave_knowledge` (+ read-only `GLOSSARY_DB_URL`), Neo4j, Redis.
- **Per-user / per-project scoped.**

### book-service (Go) — source canon input
- `chapters` / `chunks` / `parts` / `scenes` tables; internal read API `GET /internal/books/{book_id}/chapters/{chapter_id}/hierarchy` ([hierarchy.go](services/book-service/internal/api/hierarchy.go)) returns chapter + parts + scenes. Source text for enrichment ingest is reachable via internal APIs.

### chat-service (Python/FastAPI) — skeleton template for the new service
- Standard layout to mirror: `main.py`, `config.py` (fail-fast on missing secrets), `db/`, `deps.py`, `events/`, `middleware/`, `models.py`, `routers/`, **`client/`** (LLM provider adapter). knowledge-service uses `app/clients/`. → the **provider-adapter lives in per-service `client(s)/`**; copy that pattern (honours the no-direct-SDK + no-hardcoded-model invariants).

### Reusable infra to ADOPT (not reinvent)
- **Confidence / quarantine / pending_validation** model (knowledge-service extraction) → reuse for enrichment provenance/confidence.
- **pending_facts confirm/reject + injection-defense** review gate → mirror for the enrichment proposal review gate.
- **Extraction job state machine** (estimate/start/pause/resume/cancel/jobs) → mirror for enrichment jobs.
- **Per-project embedding-model** selection + Neo4j **graph-stats** → reuse for retrieval + gap-detection input.
- **CJK-aware text splitting** (`loreweave_extraction` lib) → reuse for Chinese source text.
- **Event pipeline** (Redis Streams; `glossary.entity_updated` etc.) → enrichment subscribes/emits here.

## 3. Re-shaped boundary (the key insight)

The enrichment service must **build on top of** the existing extraction/KG layer, not duplicate it:

```
book-service        →  raw canon text (chapters/chunks)
glossary-service    →  authored canonical entities + wiki  (SSOT)
knowledge-service   →  extraction + KG triples + Neo4j + glossary_sync + pending_facts + summaries + timeline
                       ── i.e. "UNDERSTAND existing canon" is DONE here
lore-enrichment ★   →  the NEW layer: GENERATE missing canon
                       gap-detect (over the KG) → 4 techniques → schema-governed gen
                       → canon-verify → provenance/confidence → human gate → write-back
```

What is genuinely NEW (not in knowledge-service): **gap detection over the KG, template scaffolding, external cultural retrieval, controlled fabrication, history/news re-cook, schema-governed game-ready output, per-fact provenance/confidence on GENERATED content, and the enrichment review/admission gate.**

## 4. Locked answers (CLARIFY checkpoint resolved — 2026-05-30)

1. **Review queue — own store, mirror the pattern.** Enrichment proposals are a different domain (generated lore entities/wiki) than `pending_facts` (chat memory facts), so enrichment keeps **its own proposal store** but **mirrors** knowledge-service's confirm/reject + injection-defense + confidence/quarantine pattern. No competing queue over the same data.
2. **Write-back path — author through glossary SSOT.** Approved canonical results write to **glossary** (`POST /books/{book_id}/extract-entities` + wiki); `glossary_sync` then propagates to Neo4j (single authoritative path, no drift). Enrichment does NOT write Neo4j directly for canonical content.
3. **✅ Scoping = per-user/per-project** (consistent with knowledge-service). Enriched data lives per-project, same as the KG it builds on. (Shared-canonical-world deferred — not now.)
4. **No generative overlap.** knowledge-service is **EXTRACTIVE** (Pass1 CJK pattern → Pass2 LLM → K18 validator; extracts from existing text). Its planned generation (D4-03 *wiki-from-KG*, summary regeneration) only *renders* known facts. → enrichment's "generate NEW off-page canon" is distinct and **feeds** that machinery (new grounded entities/facts → glossary/KG → existing wiki-generation renders them). Enrichment does not fork the plan.
5. **Game-entity schema — keep isolated from mmo-rpg.** "game-ready" output stays as enrichment's own schema-governed entity/wiki shape written to glossary; do NOT couple to `world-service`/`game-server` (the other agent's mmo-rpg work). Revisit only if/when a real game-engine contract is needed.
6. **Dependency & deploy order — acceptable.** Enrichment depends on knowledge-service (KG) + glossary (SSOT) + book-service (source) being up; local dev stacks them via `infra/docker-compose.yml`. Define a thin KG-read port so enrichment degrades gracefully if KG is unavailable.

## 5. Discovery — COMPLETE (2026-05-30)

- [x] `pending_facts` + `extraction` routers → review contract + job state machine (Q1).
- [x] `pass2_orchestrator` / `triple_extractor` → confirmed EXTRACTIVE, not generative (Q4).
- [x] book-service read API for source text (§2).
- [x] `KNOWLEDGE_SERVICE_ARCHITECTURE.md` enrichment/generation mentions → D4-03 wiki-from-KG, summaries (enrichment aligns, feeds it).
- [x] chat-service conventions + provider-adapter location (`client/`) for the new skeleton (§2).

> **CLARIFY COMPLETE.** All 6 questions locked (§4). Next: revise [SERVICE_DESIGN.md](SERVICE_DESIGN.md) to the corrected boundary — pipeline step [1] (ingest+seed-KG) is **delegated to knowledge-service**; enrichment consumes the KG and adds the generative layer. Then PLAN → RAID decomposition.
