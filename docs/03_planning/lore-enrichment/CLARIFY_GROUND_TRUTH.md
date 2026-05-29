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
- (to map in next discovery pass) books/chapters/chunks + chapter/chunk read API = the raw text enrichment ingests.

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

## 4. Sharpened open questions (for CLARIFY checkpoint → must lock before PLAN)

1. **Reuse vs rebuild the review queue.** knowledge-service already has `pending_facts` (a fact review queue). Should enrichment proposals flow through knowledge-service's `pending_facts`/extraction pipeline, or maintain their own proposal store? (Avoid two competing review queues.)
2. **Write-back path.** Do enriched canonical results write to glossary via `extract-entities` (then `glossary_sync` propagates to Neo4j), or write to knowledge-service as facts, or both? What's the authoritative path so we don't create drift?
3. **Scoping model.** knowledge-service is per-user/per-project. Is the Fengshen enrichment a **shared canonical world** (book-level, authored once) or **per-user/per-project**? This determines where enriched data lives and how it's shared.
4. **Overlap with knowledge-service generation.** Does knowledge-service already do any *generation* (vs extraction)? Its `summaries`/`pass2` — are they generative? Need to confirm enrichment isn't re-treading.
5. **Does the demo need its own game-entity schema** (the "game-ready" target), and where is that defined — is it tied to `world-service`/`game-server` (the mmo-rpg work) which we must stay isolated from?
6. **Dependency direction & deployment order** — enrichment depends on knowledge-service being up; confirm that's acceptable and how local dev stacks it.

## 5. Next discovery (still needed before DESIGN can finalize)

- [ ] Read `pending_facts` + `extraction` public routers to learn the existing proposal/review contract (Q1).
- [ ] Read knowledge-service's `pass2_orchestrator` / `summaries` to confirm generative-vs-extractive boundary (Q4).
- [ ] Map book-service read API for source text (§2 book-service).
- [ ] Read `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` + `101_DATA_RE_ENGINEERING_PLAN.md` for the intended contract + roadmap (so enrichment aligns with, not forks, the plan).
- [ ] Confirm chat-service (Python/FastAPI) conventions + provider-adapter location for the new service skeleton.

> **DESIGN cannot be finalized until §4 questions are locked.** SERVICE_DESIGN.md must then be revised: its pipeline step [1] (ingest+seed-KG) is largely **delegated to knowledge-service**, not re-implemented.
