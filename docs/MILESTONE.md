# LoreWeave — Project Milestone (SSOT)

> **Single Source of Truth** for project progress.
> CLAUDE.md and README.md derive from here — update this file first.
>
> Last updated: 2026-08-08 — game-tier build index added (§ Phase 6+)

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
| Phase 6+ — Living Worlds | P6+ | **IN BUILD** — see the build index below. The old note ("design track locked, gated on novel platform maturity") was true until ~2026-06 and is no longer: the engine is ~60k lines. |

---

## Phase 6+ — Living Worlds: the BOOK → REALITY build index

> **Added 2026-08-08. This table is the build index for the game tier** — what state each part is
> in and what blocks what. It is deliberately an INDEX, not a design: detail lives in the track
> docs, and the live working state is
> [`docs/plans/2026-08-06-game-tier-build-RUN-STATE.md`](plans/2026-08-06-game-tier-build-RUN-STATE.md).
>
> The chain: **`book → lore bible → pre-manifest stub → manifest → reality`**
> Full stage-by-stage measurement:
> [`docs/specs/2026-08-08-book-to-reality-pipeline-index.md`](specs/2026-08-08-book-to-reality-pipeline-index.md)

**The shape of it: the two ends are built and the middle is not.**

| # | stage | track | state | note |
|---|---|---|---|---|
| S1 | Book — source text | LoreWeave | ✅ built | `loreweave_book` 584 MB / 394 books |
| S2 | Glossary / KG — authored lore SSOT | LoreWeave | ✅ built | `loreweave_glossary` 1847 MB, largest DB in the stack |
| S3 | **Lore bible** — the authored game concept | [BOOK_TO_GAME](03_planning/BOOK_TO_GAME/_index.md) | 🟡 design only | 17 docs, **zero code** |
| S4 | **Pre-manifest stub** — unstructured concept → structured input | — | 🔴 **undefined** | not a named artifact anywhere in the repo |
| S5 | Manifest / ruleset — what the engine ingests | [LLM_MMO_RPG](03_planning/LLM_MMO_RPG/00_VISION.md) | 🟢 substantially built | `ruleset-core` 5.2k + `ruleset-loader` 3.9k lines; `load_reality()`; shipped `engine_default.toml`. **`G-S5a` discharged 2026-08-11** — the authorable surface is now stated and machine-checked: [`contracts/ruleset/authorable-surface.v1.yaml`](../contracts/ruleset/authorable-surface.v1.yaml), 8 patch types / 72 keys / 6 refusals / 20 classified rows, checked against the source AND against the real loader ([run-state](plans/2026-08-14-authorable-surface-RUN-STATE.md)) |
| S6 | Engine — deterministic runtime | LLM_MMO_RPG | 🟢 substantially built | `dp-kernel` 15.1k · `world-gen` 30.8k · `sim-core` 2.5k · `actor-hub` 2.0k |
| S7 | **Reality data** — the per-reality database | LLM_MMO_RPG | 🟢 **CREATED BY AN HTTP REQUEST 2026-08-11** | First provisioned 2026-08-08 (registry row `active`, DB on `pg-shard-0.internal`, 12 tables, 15 in the migration ledger, `channels` live and `REC-106` holding). **The "still a drill" caveat is now discharged**: `world-service` serves `POST /internal/v1/realities` and a real process created `lw_reality_58663ea66315` over a socket — 201, then `pg_database` confirming it. Idempotent on re-entry (`already_provisioned` / `resumed`, both proven live). Internal-only per `I1`; the gateway route is the next build. [run-state](plans/2026-08-13-world-service-server-RUN-STATE.md) · [contract](../contracts/api/world/provisioning.v1.yaml) |
| S8 | Reality request — the user-facing function | — | 🅿 parked — **but no longer by its own gates** | [spec](specs/2026-08-08-user-created-realities.md); a CREATE DATABASE feature, needs layered security. **All three stated wake-up conditions are now met** (`G-S5a` ✅ · `G-S7b` ✅ · `G-S8b` ✅, 2026-08-11), so what parks it is the PO's build-order call — *"you cannot give a user a manifest builder if you do not know what the game engine can support"* — plus `S3`/`S4` still being undesigned. **A product decision now, not an engineering blocker.** See the ⚠ note in [the pipeline index](specs/2026-08-08-book-to-reality-pipeline-index.md) §5 |

**Build order (PO, 2026-08-08): engine first.** You cannot give a user a manifest builder without
knowing what the engine supports — every field a builder offers is a promise the engine must keep
(`AUTHOR-1`, `LIM-1`). `engine_default.toml` is the engine's own declaration of that surface.

**Open gaps:** `G-S3` lore bible has no schema/producer · `G-S4` pre-manifest stub undefined ·
`G-S5a` engine's authorable surface not enumerated for authors · `G-S7a` zero realities ever ·
`G-S7b` **the meta database does not exist** and `migrations/meta/` is a second migration tree with
no manifest or gate · `G-S8a` `reality_registry` has no owner · `G-S8b` `loreweave` is the sole
Postgres login role and is superuser.

---

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
