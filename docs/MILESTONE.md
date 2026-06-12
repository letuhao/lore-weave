# LoreWeave — Project Milestone (SSOT)

> **Single Source of Truth** for project progress.
> CLAUDE.md and README.md derive from here — update this file first.
>
> Last updated: 2026-05-24 (session 67)

---

## Platform Core — All Done

| Module | Name | Backend | Frontend | Status |
|--------|------|---------|----------|--------|
| M01 | Identity & Auth | ✅ | ✅ | Closed (smoke) |
| M02 | Books & Sharing | ✅ | ✅ | Closed (smoke) |
| M03 | Provider Registry + Billing | ✅ | ✅ | Closed (smoke) |
| M04 | Raw Translation Pipeline | ✅ | ✅ | Closed (smoke) |
| M05 | Glossary & Lore Management | ✅ | ✅ | Closed (smoke) |

> "Closed (smoke)" = all code exists, smoke tests pass, formal acceptance evidence packs not produced (BLK-01).

---

## Phase 2 — Knowledge Services

| Component | Status | Notes |
|-----------|--------|-------|
| knowledge-service (Postgres SSOT + Neo4j derived graph) | ✅ Live | Entity relations, memory, narrative queries |
| Outbox → publisher → projection pipeline | ✅ Live | Event-driven graph sync |
| Entity extraction P1 — structural decomposer (loreweave_parse SDK) | ✅ Done | 4-level tree: book → part → chapter → scene |
| Entity extraction P2 — cache-wrap + per-op extractor versioning | ✅ Done | `v1-{op}-{8hex}` per-op cache keys |
| Entity extraction P3 — hierarchical reduce + per-level summaries | 🔄 In progress | pass2_orchestrator active, session 67 |
| Eval dataset + RAG quality baseline | 🔄 In progress | Target: P ≥ 0.85 R ≥ 0.70 on Sherlock baseline |
| Admin prune endpoint (orphan summary index) | ✅ Done | `POST /internal/admin/summary-indexes/prune` |
| Wiki (articles / revisions / suggestions) | ✅ Done | Hosted inside glossary-service, not separate |

---

## Services — Full List

19 services total. 3 are Living Worlds foundation (Phase 6+, Rust).

| Service | Language | Phase | Purpose |
|---------|----------|-------|---------|
| **api-gateway-bff** | TypeScript / NestJS | Core | Single entry point, auth forwarding |
| **auth-service** | Go / Chi | M01 | Identity, JWT, sessions, profiles |
| **book-service** | Go / Chi | M02 | Books, chapters, chunks, lifecycle |
| **sharing-service** | Go / Chi | M02 | Visibility policies, share links |
| **catalog-service** | Go / Chi | M02 | Public book discovery, search |
| **provider-registry-service** | Go / Chi | M03 | BYOK credentials, model registry, stream billing |
| **usage-billing-service** | Go / Chi | M03 | Token metering, quota enforcement, cost estimation |
| **glossary-service** | Go / Chi | M05 | Glossary entities, attributes, evidence linking, wiki |
| **statistics-service** | Go / Chi | Core | Analytics, usage metrics |
| **notification-service** | Go / Chi | Core | Notifications, email delivery |
| **worker-infra** | Go | Core | Outbox relay, import processing, Pandoc conversion |
| **translation-service** | Python / FastAPI | M04 | Translation API + job orchestration |
| **chat-service** | Python / FastAPI | Core | Streaming AI chat, multi-provider SSE, thinking mode |
| **knowledge-service** | Python / FastAPI | P2 | Knowledge graph, entity extraction, summaries |
| **video-gen-service** | Python / FastAPI | Phase 3.5 | Media generation BFF (ComfyUI in sibling repo) |
| **worker-ai** | Python | P2 | Async AI tasks: extraction, summary regen, embeddings |
| **tilemap-service** | Rust | Phase 6+ | Living Worlds — tile/spatial layer |
| **travel-service** | Rust | Phase 6+ | Living Worlds — movement/travel mechanics |
| **world-service** | Rust | Phase 6+ | Living Worlds — world state, reality model |

### Infrastructure (not counted in service total)

| Component | Purpose |
|-----------|---------|
| PostgreSQL 18 + pgvector | Per-service schemas, JSONB, vector embeddings (HNSW) |
| Neo4j | Derived entity graph (knowledge-service) |
| Redis 7 | Sessions, caching, rate limiting, outbox event streams |
| RabbitMQ 3.13 | Translation + heavy AI job distribution |
| MinIO | S3-compatible: media, exports, uploads |
| LanguageTool | Grammar + spell check |
| Pandoc Server | Format conversion (EPUB, DOCX, Markdown → HTML) |

---

## Current Active Work (session 67)

- **pass2_orchestrator P3** — hierarchical reduce + per-level summary generation
- **Eval dataset** — building golden-set fixtures for RAG quality measurement
- **RAG quality baseline** — target Sherlock: P ≥ 0.85 R ≥ 0.70

---

## Open Blockers

| ID | Blocker | Severity |
|----|---------|----------|
| BLK-01 | Formal acceptance evidence packs not produced for M01–M05 | Medium |

---

## Planned (not started)

| Item | Phase | Notes |
|------|-------|-------|
| Phase 3 — QA Extraction (grounded Q&A) | P3 | After RAG quality baseline validated |
| Phase 4 — Continuation & Canon Safety | P4 | Canon-aware AI drafting |
| Phase 5 — Hardening & Scale | P5 | Multi-tenancy, SRE, cloud readiness |
| Phase 6+ — Living Worlds | P6+ | LLM MMO RPG; design track locked, gated on novel platform maturity |

## Deferred (tracked)

| Item | Direction |
|------|-----------|
| SSE/WebSocket progress for translation jobs (currently polling) | Future polish cycle |
| Per-scene fanout in extraction (D-P2-PER-SCENE-FANOUT) | When 1MB+ novel perf becomes issue |
| FE toggle for `save_raw_extraction` (D-P2-FE-SAVE-RAW) | Polish cycle after P3 |
| 10MB end-to-end perf benchmark (D-P2-10MB-PERF-VALIDATION) | Post-P3 perf cycle |
| Structured zip import/export | Post-V1 |
| PDF import | Future MIME wave |
| Paid storage tiers / Stripe billing | Future monetization wave |
| Video generation real providers (Sora, Veo) | 10 tasks planned (VG-01..VG-10) |
| Physical GC for purge_pending objects | Background GC worker |
| Production rollout hardening (SRE, security sign-off) | Pre-release gate wave |
