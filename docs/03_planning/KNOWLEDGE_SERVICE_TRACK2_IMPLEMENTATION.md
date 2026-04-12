# Knowledge Service — Track 2 Implementation Plan

> **Status:** Implementation plan, ready to execute after Track 1 ships
> **Created:** 2026-04-13 (session 34)
> **Scope:** Track 2 (K10–K18 from [KNOWLEDGE_SERVICE_ARCHITECTURE.md §9](KNOWLEDGE_SERVICE_ARCHITECTURE.md))
> **Goal:** Opt-in Extraction Infrastructure — knowledge graph, L2/L3, BYOK LLM extraction
>
> **Prerequisite:** Track 1 complete and stable. See
> [KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md](KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md).

---

## 1. Executive Summary

### What Track 2 delivers

The full extraction infrastructure behind the `extraction_enabled` flag.
Users who opt in get:

- **Knowledge graph** in Neo4j per project
- **L2 context** — structured facts about detected entities with temporal grouping
- **L3 context** — semantic search over entities/events/drawers via vectors
- **Two-pass extraction** — fast pattern-based (Pass 1) + accurate LLM-based (Pass 2)
- **Per-project embedding model** — choose from curated 5-model list
- **Extraction Jobs** — user-triggered with cost estimate, pause/resume/cancel, budget caps
- **Incremental extraction** — new chapters auto-extracted, old ones re-extractable
- **Provenance tracking** — every fact traceable to its source via `EVIDENCED_BY` edges
- **Mode 3 chat context** — the full architecture promise

### What Track 2 explicitly does NOT include

| Out of scope | Where it lands |
|---|---|
| Full memory UI (timeline, entities table, raw drawers) | Track 3 (K19a-f) |
| Tool calling integration (memory tools for LLMs) | Track 3 (K21) |
| Summary regeneration (LLM-based L0/L1 refresh) | Track 3 (K20) |
| Honest privacy model docs page (in UI) | Track 3 (K22) |
| Inline fact correction UI | Track 3 |
| Draft glossary auto-population (Track 1 extension) | Already in Track 1 K4.3+ |
| Wiki generation (D4-03) | Post-Track 3 |
| Timeline generation (D4-04) | Post-Track 3 |
| Cross-project entity linking ("tunnel" entities) | Open question, not built |

### Prerequisites from 101 / D-phases

Must be done before starting K10:

- **D2-01** Add Neo4j v2026.01 to docker-compose
- **D2-03** Neo4j schema init (constraints, vector indexes, composite indexes)
- **D2-04** Self-hosted embedding model service (bge-m3)
- **D3-00** Idempotency layer (canonicalization + deterministic IDs + source_event_id)

Plus Track 1 must be complete:
- Gates 1–5 passed
- All integration tests T01–T10 green
- Real use for at least a few days (validate Track 1 is sound before building on top)

### What "done" looks like for Track 2

Ticking all boxes below means Track 2 is complete:

- [ ] Neo4j deployed, accessible from knowledge-service
- [ ] Self-hosted bge-m3 embedding service runs, serves `/embed` endpoint
- [ ] User can enable extraction on a project via API (explicit action)
- [ ] Cost estimation endpoint works (returns realistic range)
- [ ] Extraction Job can be started, paused, resumed, cancelled, cancelled mid-run keeps partial graph
- [ ] Pattern extractor runs synchronously on chat turns and chapter saves (when extraction enabled)
- [ ] LLM Pass 2 extractor runs asynchronously via worker-ai
- [ ] Pass 2 validates Pass 1 quarantine (confirms/contradicts)
- [ ] Facts with `confidence >= 0.8` appear in L2 context
- [ ] L3 semantic search returns relevant passages with hybrid scoring
- [ ] Chat header shows "Full memory" mode when extraction complete
- [ ] Mode 3 context block is correctly structured and under token budget
- [ ] Disabling extraction keeps partial graph and queues new events
- [ ] Re-enabling extraction processes queued events in order
- [ ] Budget cap enforcement is atomic (no TOCTOU race — T11 test passes)
- [ ] Monthly budget cap works across jobs (T12 test passes)
- [ ] Changing embedding model triggers rebuild warning and blocks until user confirms
- [ ] Deletion cascade works: delete chapter → related facts removed (T06 test)
- [ ] Partial re-extract works: old facts from chapter removed, new ones added (T07 test)
- [ ] Prompt injection detected and neutralized (T20 test)
- [ ] Cross-user isolation holds during concurrent extraction (T18 test)
- [ ] Extraction quality eval passes on golden set (precision ≥0.80, recall ≥0.70)
- [ ] Redis eviction fallback works (consumer catches up from event_log)
- [ ] Full rebuild from event_log reconstructs Neo4j correctly (§3.8.3)
- [ ] No f-string Cypher anywhere (CI lint passes)
- [ ] Backup script includes Neo4j dump
- [ ] All Track 2 integration tests T11–T20 pass

### Honest effort estimate

Track 2 is **significantly harder than Track 1**. It touches more services,
involves real money, has concurrency concerns, and requires careful quality
assurance. Be generous with time estimates.

| Phase | Effort | Why |
|---|---|---|
| K10 Postgres additions | 4–6 hours | Partitioning + cost columns + extraction_jobs |
| K11 Neo4j schema | 6–10 hours | Dimension indexes + provenance + constraints |
| K12 Embedding service | 8–12 hours | Containerize bge-m3, API, healthcheck, GPU support |
| K13 Chat turn event | 2–4 hours | chat-service outbox emit |
| K14 Event consumer + gating | 8–12 hours | Opt-in gating is subtle; pending queue + backfill |
| K15 Pattern extractor + quarantine | 15–25 hours | Multilingual, injection defense, two-pass entity detection |
| K16 Extraction Job engine | 20–30 hours | Scopes, progress, pause/resume/cancel, atomic cost enforcement, budget caps |
| K17 LLM extraction Pass 2 | 15–25 hours | Prompts, validation, reconciliation with Pass 1 |
| K18 Context builder Mode 3 | 12–18 hours | Cypher queries, hybrid scoring, temporal grouping, L2/L3 dedup |
| **Integration + QC** | 20–30 hours | End-to-end tests, chaos scenarios, quality eval |
| **Total realistic** | **110–170 hours** | 5–10 weeks of evenings |

**Do not rush this.** The most expensive bugs will be cost overruns (running
extraction infinite-loop on a 5000-chapter book) and data integrity issues
(bad extraction poisoning the graph). Both are catchable by careful QC
and the gates in this plan.

### Why Track 2 is a separate shipment

Track 1 delivers a working product. Track 2 adds premium features for users
who opt in. Users can run on Track 1 indefinitely without missing anything
critical. This staging lets you:

- Validate Track 1 in real use before committing to Track 2 complexity
- Spread the work over weeks/months without blocking users
- Discover Track 1 issues that change Track 2 design assumptions
- Give yourself a real milestone moment (Track 1 "done") before the bigger build

---

## 2. Architecture Recap (Track 2 additions)

```
┌─────────────────────────────────────────────────────────┐
│ Frontend                                                │
│   features/knowledge/*  +  Extraction Jobs UI (Track 3) │
└────────────┬────────────────────────────────────────────┘
             │ /v1/knowledge/* (now with extraction endpoints)
             ▼
┌─────────────────────────────────────────────────────────┐
│ api-gateway-bff                                         │
└────┬────────────────────────────────────┬───────────────┘
     │                                    │
     ▼                                    ▼
┌──────────────────┐              ┌──────────────────┐
│ chat-service     │──internal───▶│ knowledge-service│
│                  │  context     │                  │
│ + emits          │  /build      │ Context builder  │
│   chat.turn_     │              │ (Mode 1/2/3)     │
│   completed      │              │                  │
│   outbox event   │              │ Extraction Job   │
└──────┬───────────┘              │ engine (NEW)     │
       │                          │                  │
       │ event                    │ Pattern          │
       ▼                          │ extractor (NEW)  │
┌──────────────────┐              │                  │
│ worker-infra     │              │ LLM extractor    │
│ outbox relay     │              │ (via worker-ai)  │
│ → Redis Stream   │              └──────┬───────────┘
└──────┬───────────┘                     │
       │                                 │
       │ events                          │ read/write
       ▼                                 ▼
┌──────────────────┐              ┌──────────────────┐
│ worker-ai (NEW)  │              │ Neo4j (NEW)      │
│                  │◀─── Cypher ──┤ Entities, Events,│
│ - LLM extraction │              │ Facts, vectors,  │
│ - job processor  │              │ provenance edges │
│ - cost tracking  │              └──────────────────┘
└──────┬───────────┘                     ▲
       │                                 │
       │ BYOK API call                   │
       ▼                                 │
┌──────────────────┐              ┌──────────────────┐
│ provider-registry│              │ bge-m3 embedding │
│ (user's LLM)     │              │ service (NEW)    │
└──────────────────┘              │ self-hosted,     │
                                  │ local CPU/GPU    │
                                  └──────────────────┘
```

**Key Track 2 additions:**

1. **Neo4j** — the knowledge graph store
2. **bge-m3 embedding service** — self-hosted, free, multilingual
3. **worker-ai** — async task runner for LLM extraction
4. **Extraction Job engine** — user-triggered, cost-capped, resumable
5. **Pattern extractor** — pass 1 quarantine layer
6. **LLM extractor** — pass 2 validation + enrichment
7. **Mode 3 context builder** — reads L2/L3 from Neo4j
8. **chat.turn_completed event** — feeds the pipeline
9. **Opt-in gating** — every consumer checks `extraction_enabled`

---

## 3. Phase K10 — Postgres Schema Additions for Extraction

**Goal:** Add the new Postgres tables that support extraction lifecycle.

### Tasks

```
[ ] K10.1 Migration: extraction_pending table
    Files:
      - services/knowledge-service/migrations/20260501_010_extraction_pending.sql (NEW)
    Description:
      Per KSA §3.3. Stores events that arrive while extraction is disabled
      for their project, so they can be processed later.
      Include indexes:
        - idx_extraction_pending_unprocessed (project_id, created_at)
          WHERE processed_at IS NULL
      UNIQUE(project_id, event_id) for idempotent queueing.
    Acceptance criteria:
      - Migration applies cleanly
      - Cannot insert duplicate event_id for same project (unique constraint)
      - Query "next N pending events for project X" is fast
    Test:
      - Integration: insert duplicates, verify unique violation
    Dependencies: K1 complete (Track 1)
    Est: S
```

```
[ ] K10.2 Migration: extraction_jobs table
    Files:
      - services/knowledge-service/migrations/20260501_011_extraction_jobs.sql (NEW)
    Description:
      Per KSA §3.3. Tracks user-triggered extraction jobs with progress,
      cost, scope, status. Include CHECK constraints on status and scope enums.
      Indexes:
        - idx_extraction_jobs_project (project_id, created_at DESC)
        - idx_extraction_jobs_active (status) WHERE status IN ('pending', 'running', 'paused')
    Acceptance criteria:
      - Migration applies
      - Status and scope enums enforced
      - JSONB current_cursor accepts any structure
    Test:
      - Integration
    Dependencies: K10.1
    Est: S
```

```
[ ] K10.3 Migration: extraction fields on knowledge_projects
    Files:
      - services/knowledge-service/migrations/20260501_012_projects_extraction_fields.sql (NEW)
    Description:
      ALTER TABLE knowledge_projects ADD COLUMN for all the extraction-related
      fields from KSA §3.3 that weren't in Track 1:
        - embedding_model TEXT (nullable)
        - extraction_config JSONB DEFAULT '{}'
        - last_extracted_at TIMESTAMPTZ
        - estimated_cost_usd NUMERIC(10,4) DEFAULT 0
        - actual_cost_usd NUMERIC(10,4) DEFAULT 0
        - monthly_budget_usd NUMERIC(10,4) (nullable)
        - current_month_spent_usd NUMERIC(10,4) DEFAULT 0
        - current_month_key TEXT (nullable)
        - stat_entity_count INT DEFAULT 0
        - stat_fact_count INT DEFAULT 0
        - stat_event_count INT DEFAULT 0
        - stat_glossary_count INT DEFAULT 0
        - stat_updated_at TIMESTAMPTZ
    Acceptance criteria:
      - Existing projects have sensible defaults for new columns
      - Cost columns use NUMERIC not FLOAT (no rounding errors)
      - Stat columns indexable
    Test:
      - Integration + verify existing Track 1 projects work unchanged
    Dependencies: K1.2 (Track 1)
    Est: S
    Notes:
      Note: K1.2 already created the table. K10.3 is a forward-compatible
      ALTER that adds columns Track 1 didn't need.
```

```
[ ] K10.4 Repository: extraction_jobs
    Files:
      - services/knowledge-service/app/db/repositories/extraction_jobs.py (NEW)
    Description:
      Pydantic models + queries:
        - create_job(project_id, user_id, scope, llm_model, embedding_model, max_spend_usd)
        - get_job(job_id, user_id)
        - list_jobs_for_project(project_id, user_id)
        - list_active_jobs(user_id)
        - update_status(job_id, new_status, ...)
        - atomic_try_spend(job_id, estimated_cost) → atomic SQL per KSA §5.5
        - advance_cursor(job_id, cursor_data)
        - complete_job(job_id)
        - cancel_job(job_id)
    Acceptance criteria:
      - atomic_try_spend uses the single-statement UPDATE pattern (no TOCTOU)
      - All queries user_id scoped
      - Returns Pydantic models
    Test:
      - Integration: cost race test — spawn 10 concurrent try_spend calls,
        verify total spent never exceeds max_spend_usd
    Dependencies: K10.2, K10.3
    Est: M
    Notes:
      **Security/money critical.** The atomic UPDATE is the whole point.
      Unit test this specifically — don't trust eyeballing.
```

```
[ ] K10.5 Repository: extraction_pending
    Files:
      - services/knowledge-service/app/db/repositories/extraction_pending.py (NEW)
    Description:
      - queue_event(project_id, event_id, event_type, aggregate_type, aggregate_id)
      - count_pending(project_id)
      - fetch_pending(project_id, limit)
      - mark_processed(pending_id)
      - clear_pending(project_id)  # called when user cancels/disables
    Acceptance criteria:
      - Queue is idempotent (duplicate event_id → no-op)
      - Fetch returns in created_at order
      - User_id scoped via JOIN on knowledge_projects
    Test:
      - Integration
    Dependencies: K10.1
    Est: S
```

### Gate 6 — Extraction Schema Ready

- [ ] All migrations apply to fresh DB cleanly
- [ ] Existing Track 1 projects unchanged (no column default mismatches)
- [ ] Atomic spend test passes 1000 concurrent iterations without exceeding cap
- [ ] Cross-user isolation still works (no regression)
- [ ] Pending queue handles 100K rows without index slowdown

---

## 4. Phase K11 — Neo4j Schema

**Goal:** Deploy Neo4j, create the schema per KSA §3.4, verify multi-tenant
queries work with composite indexes.

**This phase requires Neo4j to be deployed** (D2-01 from 101). If not done,
do it as part of K11.

### Tasks

```
[ ] K11.1 Deploy Neo4j v2026.01 in docker-compose
    Files:
      - infra/docker-compose.yml (MODIFY — add neo4j service)
      - infra/.env.example (MODIFY — add NEO4J_* vars)
    Description:
      Add Neo4j service:
        - image: neo4j:2026.01-community
        - volumes: data, logs, conf, import, plugins
        - environment: NEO4J_AUTH (neo4j/<strong password>), NEO4J_PLUGINS='["apoc"]'
        - ports: 7474 (http), 7687 (bolt)
        - healthcheck: wget /health (retries 10, start_period 60s)
        - deploy.resources.limits.memory: 4G
        - profiles: [full, neo4j, extraction]
    Acceptance criteria:
      - `docker compose --profile neo4j up -d neo4j` starts successfully
      - http://localhost:7474 shows Neo4j browser
      - bolt://localhost:7687 accessible
      - Healthy after ~60s startup
    Test:
      - Manual: access Neo4j browser, run MATCH (n) RETURN count(n) (should be 0)
    Dependencies: none
    Est: M
    Notes:
      Community edition is free but limited. Enterprise features we don't need.
      Use APOC plugin for utility functions (not required for Track 2 core
      but useful for debugging).
```

```
[ ] K11.2 Neo4j driver setup in knowledge-service
    Files:
      - services/knowledge-service/pyproject.toml (MODIFY — add neo4j driver)
      - services/knowledge-service/app/db/neo4j.py (NEW)
    Description:
      Add `neo4j` Python driver. Create async session pool with config from env.
      NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD env vars.
    Acceptance criteria:
      - Driver connects at startup
      - Startup fails if Neo4j unreachable
      - Session pool properly closed on shutdown
    Test:
      - Integration: verify connection + simple MATCH query
    Dependencies: K11.1
    Est: S
```

```
[ ] K11.3 Cypher schema init script
    Files:
      - services/knowledge-service/app/db/neo4j_schema.cypher (NEW)
      - services/knowledge-service/app/db/neo4j_schema.py (NEW — runs the script)
    Description:
      Cypher script that creates per KSA §3.4:
        - Node labels: Project, Session, Entity, Event, Fact, ExtractionSource
        - Unique constraints on entity_id, event_id, fact_id, source_id
        - Composite indexes: entity_user_canonical, entity_user_name, entity_user_project,
          entity_project_model, event_user_order, event_user_chapter
        - Vector indexes: entity_embeddings_384, _1024, _1536, _3072
        - Vector indexes: event_embeddings_1024 (default)
        - Evidence count indexes: entity_zero_evidence, event_zero_evidence, fact_zero_evidence
        - ExtractionSource constraint + indexes
    Acceptance criteria:
      - All constraints/indexes created
      - Idempotent (re-running doesn't error)
      - Fails with clear error if Neo4j version doesn't support vector indexes
    Test:
      - Integration: run script, SHOW INDEXES, verify all present
    Dependencies: K11.2
    Est: M
    Notes:
      IF NOT EXISTS clauses throughout. Vector indexes require Neo4j 2026.01+.
```

```
[ ] K11.4 Multi-tenant query helpers
    Files:
      - services/knowledge-service/app/db/neo4j_helpers.py (NEW)
    Description:
      Wrapper functions that enforce user_id filter on every query:
        - run_read(cypher, user_id, **params) — asserts cypher contains user_id filter
        - run_write(cypher, user_id, **params) — same
      Raises AssertionError if cypher doesn't reference $user_id parameter.
      All knowledge-service Cypher goes through these helpers.
    Acceptance criteria:
      - Cypher without user_id filter raises AssertionError
      - Cypher with user_id filter runs normally
      - Parameters passed through correctly
    Test:
      - Unit: test each path
    Dependencies: K11.2
    Est: S
    Notes:
      This is a safety net for the "every Cypher must filter by user_id" rule
      from 101 §3.6. Cheap runtime check that catches developer mistakes.
```

```
[ ] K11.5 Repository: entities (Neo4j)
    Files:
      - services/knowledge-service/app/db/neo4j_repos/entities.py (NEW)
    Description:
      CRUD + query functions over :Entity nodes:
        - merge_entity(canonical_id, user_id, project_id, display_name, kind, ...)
          using deterministic canonical_id from §5.0
        - get_entity(canonical_id, user_id)
        - find_entities_by_name(user_id, project_id, name_or_alias)
        - find_entities_by_vector(user_id, project_id, embedding, dim, limit)
        - delete_entities_with_zero_evidence(user_id, project_id) — uses cached evidence_count
    Acceptance criteria:
      - merge_entity is idempotent (re-running creates no duplicates)
      - Name lookup uses composite index
      - Vector query uses dimension-routed index
      - Cleanup query uses evidence_count index (not full scan)
    Test:
      - Integration: insert 10k entities, measure query latency
    Dependencies: K11.3, K11.4
    Est: L
    Notes:
      **Use parameterized Cypher throughout.** No f-strings. Reviewers will
      reject. Reference: 101 §3.6 Cypher injection rule.
```

```
[ ] K11.6 Repository: relations (RELATES_TO edges)
    Files:
      - services/knowledge-service/app/db/neo4j_repos/relations.py (NEW)
    Description:
      Functions over (:Entity)-[:RELATES_TO]->(:Entity) edges:
        - create_relation(subject_id, predicate, object_id, user_id, ..., source_event_id)
        - find_relations_for_entity(entity_id, user_id, min_confidence=0.8)
        - find_relations_2hop(entity_id, user_id, hop_types, min_confidence)
        - invalidate_relation(relation_id) — sets valid_until
    Acceptance criteria:
      - create_relation uses source_event_id for idempotency (same event → no-op)
      - 2-hop queries complete in <200ms at 10k entity scale
      - Temporal filter (valid_until IS NULL) applied
    Test:
      - Integration: 2-hop traversal with fixture data
    Dependencies: K11.5
    Est: M
```

```
[ ] K11.7 Repository: events + facts
    Files:
      - services/knowledge-service/app/db/neo4j_repos/events.py (NEW)
      - services/knowledge-service/app/db/neo4j_repos/facts.py (NEW)
    Description:
      Similar pattern as entities + relations. :Event has temporal ordering
      (narrative_order, chronological_order). :Fact has type (decision,
      preference, milestone, negation).
    Acceptance criteria:
      - Merge is idempotent
      - Temporal queries work
      - Fact type filter efficient
    Test:
      - Integration
    Dependencies: K11.5
    Est: M
```

```
[ ] K11.8 Repository: provenance (EVIDENCED_BY + ExtractionSource)
    Files:
      - services/knowledge-service/app/db/neo4j_repos/provenance.py (NEW)
    Description:
      Functions per KSA §3.4.C:
        - upsert_extraction_source(source_type, source_id, project_id, user_id) → id
        - add_evidence(node_id, source_id, extraction_model, confidence, job_id)
          CRITICAL: increments node.evidence_count atomically
        - remove_evidence_for_source(source_id) — for partial re-extract/delete
          CRITICAL: decrements node.evidence_count atomically
        - delete_source_cascade(source_id) — deletes the ExtractionSource
        - cleanup_zero_evidence_nodes(user_id, project_id)
          Uses evidence_count index for O(log n) speed
    Acceptance criteria:
      - evidence_count stays in sync with actual edge count (K11.9 reconciler)
      - Partial re-extract cascade works: delete source → affected nodes drop → orphans cleaned
      - Parameterized Cypher only
    Test:
      - Integration: full partial-operation scenario per KSA §3.8.5
    Dependencies: K11.5, K11.6, K11.7
    Est: L
    Notes:
      **Critical correctness area.** Drop a chapter, verify only its
      exclusive facts are removed; shared entities stay.
```

```
[ ] K11.9 Evidence count reconciler (weekly job)
    Files:
      - services/knowledge-service/app/jobs/reconcile_evidence_count.py (NEW)
    Description:
      Periodic job that verifies cached `evidence_count` matches actual
      EVIDENCED_BY edge count and fixes drift. Per 101 §3.6.
      Runs daily at low traffic (2am).
    Acceptance criteria:
      - Drift in test data gets corrected
      - Normal run fixes zero nodes
      - Metric `evidence_count_drift_fixed` for observability
    Test:
      - Integration: inject artificial drift, run job, verify fix
    Dependencies: K11.8
    Est: S
```

### Gate 7 — Neo4j Schema Functional

- [ ] Neo4j running and accessible from knowledge-service
- [ ] All constraints + indexes present (`SHOW INDEXES` lists them)
- [ ] Vector indexes functional (queryNodes returns results with test data)
- [ ] Multi-tenant helper rejects Cypher missing user_id filter
- [ ] evidence_count stays in sync through 1000 entity create/delete cycles
- [ ] Cross-user: User A writes entity, User B can't read it (verified)
- [ ] 2-hop traversal <200ms with 10k entity fixture

---

## 5. Phase K12 — Self-Hosted Embedding Service (bge-m3)

**Goal:** A separate container serving embedding requests for bge-m3.
Zero external calls, multilingual support, free.

### Tasks

```
[ ] K12.1 Embedding service scaffold
    Files:
      - services/embedding-service/ (NEW)
      - services/embedding-service/app/main.py (NEW)
      - services/embedding-service/pyproject.toml (NEW)
      - services/embedding-service/Dockerfile (NEW)
    Description:
      FastAPI service exposing POST /embed. Uses sentence-transformers library
      with bge-m3 model. Model downloaded once on first start, cached in volume.
      No external dependencies (no OpenAI, no cloud).
    Acceptance criteria:
      - Service starts with model loaded in memory
      - Model download on first start (~1 GB)
      - Subsequent starts use cached model (fast)
    Test:
      - Manual: docker compose up, curl /embed with test text
    Dependencies: K11.1 (docker-compose setup)
    Est: M
    Notes:
      Use Hugging Face Hub for model hosting. bge-m3 is BAAI/bge-m3.
      Alternative: intfloat/multilingual-e5-large if bge-m3 doesn't work.
```

```
[ ] K12.2 POST /embed endpoint
    Files:
      - services/embedding-service/app/api.py (NEW)
    Description:
      POST /embed body: {texts: [string], normalize: bool = true}
      Returns: {embeddings: [[float]], dimension: int, model: "bge-m3"}
      Batch support (up to 32 texts per call).
    Acceptance criteria:
      - Single text embedding works
      - Batch of 32 texts returns 32 embeddings
      - Dimensions are 1024 (bge-m3)
      - Normalized vectors (L2 norm = 1)
    Test:
      - Integration: verify dimensions, verify normalization
    Dependencies: K12.1
    Est: S
```

```
[ ] K12.3 Healthcheck + metrics
    Files:
      - services/embedding-service/app/health.py (NEW)
    Description:
      GET /health returns {status, model_loaded, memory_usage}
      GET /metrics prometheus format: embedding_requests_total, duration_histogram
    Acceptance criteria:
      - /health returns 200 when ready, 503 during model load
      - Metrics present
    Test:
      - Manual + curl
    Dependencies: K12.2
    Est: S
```

```
[ ] K12.4 Internal auth
    Files:
      - services/embedding-service/app/auth.py (NEW)
    Description:
      X-Internal-Token auth on /embed. Same pattern as knowledge-service K0.6.
    Acceptance criteria:
      - Missing/wrong token → 401
    Test:
      - Integration
    Dependencies: K12.2
    Est: S
```

```
[ ] K12.5 Docker compose wiring
    Files:
      - infra/docker-compose.yml (MODIFY — add embedding-service)
    Description:
      - build: services/embedding-service
      - healthcheck: /health
      - start_period: 120s (model load is slow)
      - volumes: ./models:/models (cached model)
      - profiles: [full, extraction]
      - deploy.resources.limits.memory: 3G (model + overhead)
    Acceptance criteria:
      - Starts with `docker compose --profile extraction up -d`
      - Healthy after ~90s
    Test:
      - Manual
    Dependencies: K12.3
    Est: S
```

```
[ ] K12.6 Embedding client in knowledge-service
    Files:
      - services/knowledge-service/app/clients/embedding_client.py (NEW)
    Description:
      httpx.AsyncClient wrapper for calling embedding-service /embed.
      Timeout: 10s (embedding can be slow for long text).
      Retries: 2 with exponential backoff.
    Acceptance criteria:
      - Returns np arrays or lists of floats (decide based on usage)
      - Handles service down → raises specific exception
    Test:
      - Integration with mock embedding-service
    Dependencies: K12.4
    Est: S
```

```
[ ] K12.7 GPU support (optional)
    Files:
      - services/embedding-service/Dockerfile (MODIFY — add CUDA base)
      - infra/docker-compose.yml (MODIFY — add GPU runtime)
    Description:
      If user has NVIDIA GPU, use CUDA-enabled PyTorch for ~10x speedup.
      Fall back to CPU if GPU not available.
    Acceptance criteria:
      - Detects GPU automatically
      - Logs which device is used
      - CPU mode works without GPU
    Test:
      - Manual on machine with/without GPU
    Dependencies: K12.1
    Est: M
    Notes:
      Optional — CPU is fine for hobby scale (minutes-to-hours for a 5000-ch backfill).
```

### Gate 8 — Embedding Service Works

- [ ] embedding-service starts, loads model, healthy
- [ ] curl /embed returns 1024-dim normalized vector
- [ ] knowledge-service can call it via internal client
- [ ] Batch of 100 texts processed in reasonable time (< 30s on CPU)
- [ ] Service handles being stopped and restarted (cache persistent)

---

## 6. Phase K13 — Chat Turn Event Emission

**Goal:** chat-service emits `chat.turn_completed` outbox events after LLM
stream finishes. These feed the pattern extractor.

### Tasks

```
[ ] K13.1 chat-service outbox table (if not already from D1)
    Files:
      - services/chat-service/app/migrations/NNN_outbox.py (NEW or verify)
    Description:
      Ensure outbox_events table exists in chat-service DB per 101 §3.5.1.
      Schema already defined in D1 phase; this just verifies it's present.
    Acceptance criteria:
      - Table exists
      - pg_notify trigger present
    Test:
      - Integration
    Dependencies: D1 outbox (from 101)
    Est: S
    Notes:
      Track 1 didn't need this. Track 2 uses it for chat.turn_completed events.
```

```
[ ] K13.2 Emit chat.turn_completed event in stream_service
    Files:
      - services/chat-service/app/services/stream_service.py (MODIFY)
    Description:
      After the assistant message is inserted (in the same transaction):
        INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
        VALUES ('chat.turn_completed', 'chat_message', $message_id, $json)
      Payload: {user_id, project_id, session_id, message_id, user_message_id, user_content_len, assistant_content_len}
    Acceptance criteria:
      - Every successful chat turn emits exactly one event
      - Event is in the same transaction as the message insert
      - No event on errors (rolled back with the transaction)
    Test:
      - Integration: send chat, verify outbox row appears
    Dependencies: K13.1
    Est: S
```

```
[ ] K13.3 Verify worker-infra relays to Redis
    Files:
      - services/worker-infra/internal/tasks/outbox_relay.go (VERIFY — should already work)
    Description:
      worker-infra's outbox-relay task already handles all event types from
      all services (D1-10 did this). Just add loreweave_chat as an OUTBOX_SOURCES entry.
    Acceptance criteria:
      - worker-infra picks up chat.turn_completed events
      - Events appear in Redis Stream loreweave:events:chat
      - event_log in loreweave_events gets the row
    Test:
      - Integration: XRANGE Redis, SELECT event_log
    Dependencies: K13.2
    Est: S
```

---

## 7. Phase K14 — Event Consumer with Opt-In Gating

**Goal:** knowledge-service consumes outbox events. For each event, checks
whether extraction is enabled for the relevant project. If yes → process.
If no → queue in extraction_pending.

### Tasks

```
[ ] K14.1 Redis Streams consumer setup
    Files:
      - services/knowledge-service/app/events/consumer.py (NEW)
    Description:
      Main consumer loop using redis-py asyncio client. Creates consumer
      group "knowledge-extractor" on streams:
        - loreweave:events:chapter
        - loreweave:events:chat
        - loreweave:events:glossary
      Uses XREADGROUP with blocking. Ack on successful processing.
    Acceptance criteria:
      - Consumer joins group on startup
      - Can read events from all 3 streams
      - Graceful shutdown on SIGTERM (acks pending, stops loop)
    Test:
      - Integration: publish events, verify consumer receives
    Dependencies: K10.4, K13.3
    Est: M
```

```
[ ] K14.2 Hybrid catch-up (Redis + event_log fallback)
    Files:
      - services/knowledge-service/app/events/consumer.py (MODIFY)
    Description:
      Per 101 §3.5.5: on startup, check last_processed_event_id in
      event_consumers table. Try XREAD from there; if Redis returns stale
      error (events evicted), fall back to event_log SELECT until caught up,
      then switch to real-time XREAD.
    Acceptance criteria:
      - Fresh consumer starts from beginning (event_log)
      - Caught-up consumer uses Redis
      - If consumer lags > MAXLEN (10K events), automatically falls back to event_log
      - No events lost or double-processed
    Test:
      - Integration: simulate long downtime, verify catch-up
    Dependencies: K14.1
    Est: M
    Notes:
      Critical for production robustness. Test thoroughly.
```

```
[ ] K14.3 Event dispatcher (routes to handlers)
    Files:
      - services/knowledge-service/app/events/handlers.py (NEW)
    Description:
      Dispatcher that maps event_type to handler function:
        - chat.turn_completed → handle_chat_turn
        - chapter.saved → handle_chapter_saved
        - chapter.deleted → handle_chapter_deleted
        - glossary.entity_updated → handle_glossary_update
      Unknown events are logged and acked (no retry).
    Acceptance criteria:
      - Each event type routes correctly
      - Unknown events don't crash consumer
      - Handler exceptions are caught; event goes to DLQ
    Test:
      - Unit + integration
    Dependencies: K14.1
    Est: M
```

```
[ ] K14.4 Opt-in gating logic
    Files:
      - services/knowledge-service/app/events/gating.py (NEW)
    Description:
      Helper function:
        async def should_extract(project_id, user_id) -> bool
      Returns True if project.extraction_enabled AND extraction_status in ('ready', 'building').
      Caches the result for 10s (avoid hammering Postgres per event).
    Acceptance criteria:
      - Returns False for disabled projects (default state)
      - Returns True for enabled projects
      - Cache invalidated when project.extraction_enabled changes
    Test:
      - Unit
    Dependencies: K10.4 (new fields)
    Est: S
```

```
[ ] K14.5 Queue handler: chat.turn_completed
    Files:
      - services/knowledge-service/app/events/handlers.py (MODIFY — add handler)
    Description:
      handle_chat_turn(event):
        if should_extract(project_id, user_id):
          run pattern extraction (K15)
          schedule Pass 2 (K17) via worker-ai queue
        else:
          queue_event in extraction_pending (K10.5)
    Acceptance criteria:
      - Disabled project → event queued, not processed
      - Enabled project → pattern extraction runs
      - Idempotent (duplicate events don't produce duplicate writes)
    Test:
      - Integration: both paths
    Dependencies: K14.3, K14.4, K10.5, K15 (pattern extractor)
    Est: M
```

```
[ ] K14.6 Queue handler: chapter.saved
    Files:
      - services/knowledge-service/app/events/handlers.py (MODIFY)
    Description:
      Same pattern as K14.5 but for chapter events.
      Pattern extraction reads the chapter text_content via book-service
      internal API (D1-08 from 101).
    Acceptance criteria:
      - Queues when disabled, processes when enabled
      - Correctly reads chapter content from book-service
    Test:
      - Integration
    Dependencies: K14.3, K14.4
    Est: M
```

```
[ ] K14.7 Queue handler: chapter.deleted
    Files:
      - services/knowledge-service/app/events/handlers.py (MODIFY)
    Description:
      Cascades deletion per KSA §3.8.4:
        1. Find ExtractionSource for this chapter
        2. Remove provenance edges (K11.8 remove_evidence_for_source)
        3. Cleanup zero-evidence nodes
        4. Also clear any matching rows in extraction_pending
    Acceptance criteria:
      - Facts sourced only from deleted chapter are removed
      - Facts with other evidence remain
      - extraction_pending cleared
    Test:
      - Integration: full cascade test
    Dependencies: K11.8
    Est: M
```

```
[ ] K14.8 DLQ handling
    Files:
      - services/knowledge-service/app/events/consumer.py (MODIFY)
    Description:
      On handler exception:
        1. Log with trace_id + event payload
        2. Increment retry_count in event_log
        3. If retry_count < max_retries → redeliver (don't ack)
        4. Else → insert into dead_letter_events, ack
      Per 101 §3.5.2.
    Acceptance criteria:
      - Transient errors retry
      - Permanent errors go to DLQ after N retries
      - DLQ visible in loreweave_events.dead_letter_events
    Test:
      - Integration: inject bad handler, verify DLQ
    Dependencies: K14.1
    Est: M
```

### Gate 9 — Event Pipeline Working

- [ ] chat.turn_completed events flow through the full pipeline
- [ ] Disabled project queues events
- [ ] Enabled project processes events
- [ ] DLQ catches persistent failures
- [ ] Consumer recovers from Redis downtime via event_log fallback

---

## 8. Phase K15 — Pattern Extractor + Quarantine + Multilingual

**Goal:** Fast, free, pattern-based extraction that runs synchronously on
events. Quarantined (not loaded into L2 until Pass 2 confirms).

### Tasks

```
[ ] K15.1 Canonicalization function (§5.0)
    Files:
      - services/knowledge-service/app/extraction/canonicalize.py (NEW)
    Description:
      Per KSA §5.0:
        - canonicalize_entity_name(name) → normalized form
        - entity_canonical_id(user_id, project_id, name, kind) → deterministic sha256 ID
      Handles honorifics, CJK, whitespace, case.
    Acceptance criteria:
      - Same name variants produce same ID
      - Different names produce different IDs
      - CJK preserved
      - 15+ test cases cover edge cases
    Test:
      - Unit: comprehensive test table
    Dependencies: K14.5
    Est: M
    Notes:
      Shared with K17 (LLM extractor). This is the foundation of idempotency.
      Also used in 101 D3-00. Reference: 101 §3.5.4 + KSA §5.0.
```

```
[ ] K15.2 Entity candidate extractor (two-pass)
    Files:
      - services/knowledge-service/app/extraction/entity_detector.py (NEW)
    Description:
      Port from Track 1 K4.3 but extend:
        1. Candidate extraction: capitalized words, quoted names, glossary matches, repeated nouns
        2. Signal scoring: frequency, position, verb co-occurrence, glossary match
        3. Returns list of (name, confidence, kind_hint) tuples
    Acceptance criteria:
      - Extracts 90%+ of explicit names in test corpus
      - Ignores common nouns ("the character")
      - Scoring ranks glossary matches highest
    Test:
      - Unit with fixture text
    Dependencies: K15.1
    Est: L
```

```
[ ] K15.3 Per-language pattern sets (§5.4)
    Files:
      - services/knowledge-service/app/extraction/patterns/__init__.py (NEW)
      - services/knowledge-service/app/extraction/patterns/en.py (NEW)
      - services/knowledge-service/app/extraction/patterns/vi.py (NEW)
      - services/knowledge-service/app/extraction/patterns/zh.py (NEW)
      - services/knowledge-service/app/extraction/patterns/ja.py (NEW)
      - services/knowledge-service/app/extraction/patterns/ko.py (NEW)
    Description:
      Per KSA §5.4. Each module exports:
        - DECISION_MARKERS
        - PREFERENCE_MARKERS
        - MILESTONE_MARKERS
        - NEGATION_MARKERS
        - SKIP_MARKERS (hypothetical, reported speech, counterfactual)
      Plus a language_detect() function (langdetect library).
    Acceptance criteria:
      - Language auto-detected from input
      - Correct pattern set used
      - Mixed-language content detects per sentence
    Test:
      - Unit with multilingual test cases
    Dependencies: none
    Est: L
    Notes:
      Don't perfection the patterns. 80% coverage is fine; LLM extractor
      catches the rest in Pass 2.
```

```
[ ] K15.4 Triple extractor (SVO patterns)
    Files:
      - services/knowledge-service/app/extraction/triple_extractor.py (NEW)
    Description:
      Pattern-based SVO extraction on sentences:
        - "Kai killed Commander Zhao" → (Kai, killed, Commander Zhao)
        - Skip if matches SKIP_MARKERS (hypothetical etc.)
        - Quarantine all extracted triples (confidence=0.5, pending_validation=true)
    Acceptance criteria:
      - Extracts clean SVO sentences
      - Skips hypothetical/reported speech
      - 80%+ precision on fixture text
    Test:
      - Unit with 30+ sentences including traps
    Dependencies: K15.3
    Est: L
```

```
[ ] K15.5 Negation fact extractor
    Files:
      - services/knowledge-service/app/extraction/negation.py (NEW)
    Description:
      Detects "does not know", "is unaware", "never told", etc. per KSA §4.2
      negative facts. Creates :Fact {type:'negation'} nodes.
    Acceptance criteria:
      - Catches common negation patterns (English + multilingual via K15.3)
      - Outputs negative facts with appropriate structure
    Test:
      - Unit
    Dependencies: K15.3
    Est: M
```

```
[ ] K15.6 Prompt injection neutralizer (§5.1.5 Defense 2)
    Files:
      - services/knowledge-service/app/extraction/injection_defense.py (NEW)
    Description:
      Per KSA §5.1.5:
        neutralize_injection(text) → text with dangerous phrases tagged [FICTIONAL]
      Also emits `knowledge_injection_pattern_matched` metric with project_id.
    Acceptance criteria:
      - All patterns from KSA §5.1.5 detected (multilingual)
      - Text with no injections unchanged
      - Metric incremented on detection
    Test:
      - Unit: 20+ injection attempts including multilingual
    Dependencies: none
    Est: M
    Notes:
      Defense in depth. Called both at extraction time AND at context-build time.
```

```
[ ] K15.7 Write extracted facts to Neo4j (quarantined)
    Files:
      - services/knowledge-service/app/extraction/pattern_writer.py (NEW)
    Description:
      Takes extraction output and writes to Neo4j:
        1. Create/upsert :Entity nodes (via K11.5)
        2. Create/upsert :ExtractionSource node
        3. Create EVIDENCED_BY edges (K11.8 — increments evidence_count)
        4. Create :RELATES_TO edges (K11.6) with confidence=0.5, pending_validation=true
        5. Create :Fact nodes for decisions/preferences/milestones/negations
    Acceptance criteria:
      - All writes use parameterized Cypher
      - Idempotent: re-running same input produces no duplicates
      - Metric `pass1_facts_written` incremented
    Test:
      - Integration with real Neo4j
    Dependencies: K15.1, K15.2, K15.4, K15.5, K11.5, K11.6, K11.8
    Est: L
```

```
[ ] K15.8 Orchestrator: extract_from_chat_turn
    Files:
      - services/knowledge-service/app/extraction/pattern_extractor.py (NEW)
    Description:
      Top-level function called by K14.5 handler:
        async def extract_from_chat_turn(user_message, assistant_message, ...):
          1. Run language detection
          2. Sanitize: neutralize_injection
          3. Extract entity candidates
          4. Extract triples
          5. Extract negations
          6. Write all to Neo4j (quarantined)
          7. Return extraction summary (for logging)
    Acceptance criteria:
      - Completes in <2s for a normal chat turn
      - Handles empty/short input without error
      - Emits metrics for each step
    Test:
      - Integration: end-to-end test with a chat fixture
    Dependencies: K15.3-K15.7
    Est: M
```

```
[ ] K15.9 Orchestrator: extract_from_chapter
    Files:
      - services/knowledge-service/app/extraction/pattern_extractor.py (MODIFY)
    Description:
      Similar to K15.8 but takes chapter text (potentially large).
      Chunks text into paragraphs and runs extraction per chunk.
    Acceptance criteria:
      - Handles 10K-token chapter without OOM
      - Splits into chunks appropriately
    Test:
      - Integration with 5000-word chapter
    Dependencies: K15.8
    Est: M
```

```
[ ] K15.10 Quarantine cleanup job
    Files:
      - services/knowledge-service/app/jobs/quarantine_cleanup.py (NEW)
    Description:
      Per KSA §5.1: facts stuck in quarantine (pending_validation=true) for >24h
      without Pass 2 verdict → auto-invalidate.
      Runs hourly.
    Acceptance criteria:
      - Old quarantined facts get invalidated
      - Recent ones untouched
      - Metric `quarantine_auto_invalidated` incremented
    Test:
      - Integration: inject old quarantined fact, run job, verify gone
    Dependencies: K15.7
    Est: S
```

```
[ ] K15.11 Glossary sync handler
    Files:
      - services/knowledge-service/app/events/handlers.py (MODIFY)
    Description:
      Handle glossary.entity_updated events:
        1. Read updated entity from glossary-service
        2. Merge into Neo4j as :Entity with confidence=1.0, source_type='glossary'
        3. Glossary entities don't go through quarantine (user-curated)
    Acceptance criteria:
      - Glossary entities appear in Neo4j immediately on update
      - User-curated data has higher confidence than extracted data
    Test:
      - Integration
    Dependencies: K15.7
    Est: M
```

```
[ ] K15.12 Metrics + logging
    Files:
      - services/knowledge-service/app/extraction/metrics.py (NEW)
    Description:
      All Pass 1 metrics from KSA §9.6:
        - pass1_entities_extracted
        - pass1_triples_extracted
        - pass1_facts_extracted
        - pass1_injections_detected
        - pass1_duration_seconds
    Acceptance criteria:
      - All metrics exposed via /metrics
    Test:
      - Manual: run extraction, check /metrics
    Dependencies: K15.8
    Est: S
```

### Gate 10 — Pattern Extractor Works

- [ ] Chat turn → pattern extraction → Neo4j entities (quarantined)
- [ ] Chapter save → extraction → Neo4j entities (quarantined)
- [ ] Pattern extractor handles English + Vietnamese + Chinese text
- [ ] Injection patterns detected and neutralized
- [ ] Idempotent: same input twice = no duplicates
- [ ] Performance: chat turn extraction < 2s, chapter extraction < 30s per chapter
- [ ] No unparameterized Cypher (CI lint passes)

---

## 9. Phase K16 — Extraction Job Engine

**Goal:** User-triggered extraction jobs with progress tracking, pause/resume/
cancel, atomic cost enforcement, budget caps. This is the user-facing control
plane for Track 2.

### Tasks

```
[ ] K16.1 Extraction Job state machine
    Files:
      - services/knowledge-service/app/jobs/state_machine.py (NEW)
    Description:
      Per KSA §8.4 state machine. Transition function that validates
      state changes and persists to DB:
        - pending → running
        - running → paused_user / paused_budget / paused_error / complete / cancelled
        - paused_* → running (resume)
        - cancelled → terminal
        - complete → terminal (job ends)
    Acceptance criteria:
      - Invalid transitions raise StateTransitionError
      - Atomic DB update (single query)
      - Logs every transition with trace_id
    Test:
      - Unit: test all valid + invalid transitions
    Dependencies: K10.4
    Est: M
```

```
[ ] K16.2 Cost estimation endpoint
    Files:
      - services/knowledge-service/app/api/public/extraction.py (NEW)
    Description:
      POST /v1/knowledge/projects/{id}/extraction/estimate
      Body: {scope, scope_range, llm_model}
      Returns: {items_total, estimated_cost_low, estimated_cost_high, duration_seconds}

      Estimation logic per KSA §5.5:
        - Count chapters (via book-service)
        - Count pending chat turns (via extraction_pending)
        - Count glossary entities (via glossary-service)
        - Apply token estimates per item
        - Multiply by model pricing
    Acceptance criteria:
      - Returns cost range (not a point estimate)
      - Range is realistic (low is 70% of high)
      - Respects scope_range filter
    Test:
      - Integration
    Dependencies: K10.4, K7.1 (jwt auth from Track 1)
    Est: M
```

```
[ ] K16.3 Start extraction job endpoint
    Files:
      - services/knowledge-service/app/api/public/extraction.py (MODIFY)
    Description:
      POST /v1/knowledge/projects/{id}/extraction/start
      Body: {scope, scope_range, llm_model, embedding_model, max_spend_usd}

      Steps:
        1. Verify project belongs to user
        2. Run can_start_job check (monthly cap) per KSA §5.5
        3. Atomically: create extraction_jobs row, set project.extraction_enabled = true,
           project.extraction_status = 'building', project.embedding_model = chosen
        4. Notify worker-ai (Redis task queue)
        5. Return job_id
    Acceptance criteria:
      - Atomic: either all fields update or none
      - Monthly budget check blocks over-budget starts
      - Returns 409 if another job already running for this project
    Test:
      - Integration
    Dependencies: K16.1, K16.2
    Est: M
```

```
[ ] K16.4 Pause/resume/cancel endpoints
    Files:
      - services/knowledge-service/app/api/public/extraction.py (MODIFY)
    Description:
      - POST /v1/knowledge/projects/{id}/extraction/pause
      - POST /v1/knowledge/projects/{id}/extraction/resume
      - POST /v1/knowledge/projects/{id}/extraction/cancel
    Acceptance criteria:
      - State transitions correct (via K16.1)
      - Cancel preserves partial graph
      - Cancel transitions project.extraction_status = 'disabled'
    Test:
      - Integration: start → pause → resume → cancel
    Dependencies: K16.1
    Est: M
```

```
[ ] K16.5 Job status endpoint (for frontend polling)
    Files:
      - services/knowledge-service/app/api/public/extraction.py (MODIFY)
    Description:
      GET /v1/knowledge/extraction/jobs/{job_id}
      Returns full job state with progress per KSA §6.3.
      Supports If-None-Match for etag-based conditional GET.
    Acceptance criteria:
      - Returns job or 404
      - Cross-user: 404
      - etag changes on progress update
    Test:
      - Integration
    Dependencies: K16.3
    Est: S
```

```
[ ] K16.6 worker-ai: task runner
    Files:
      - services/worker-ai/app/tasks/extraction_job_runner.py (NEW)
    Description:
      Per KSA §5.5 + 101 D3-09. worker-ai picks up tasks from Redis queue:
        1. Load extraction_job from DB
        2. Enumerate items per scope (chapters/chat/glossary/all)
        3. For each item:
           a. Check job.status (pause/cancel?)
           b. atomic_try_spend estimated cost
           c. Run LLM extraction (K17)
           d. advance_cursor
           e. Reconcile actual cost
        4. On all done → complete_job
    Acceptance criteria:
      - Respects pause/cancel within <5s of state change
      - Atomic cost tracking (never exceeds max_spend_usd)
      - Cursor-based resume works after restart
      - Progress metric updates regularly
    Test:
      - Integration: start job, pause mid-run, restart worker-ai, resume, verify continues
    Dependencies: K16.1, K10.4, K15.8, K17 (Pass 2 extractor)
    Est: L
    Notes:
      **Critical runtime.** Test carefully for cost correctness.
```

```
[ ] K16.7 worker-ai: backfill handler
    Files:
      - services/worker-ai/app/tasks/backfill.py (NEW)
    Description:
      Per KSA §5.5 + 101 D3-07. On extraction-enable:
        1. Enumerate historical chapters via book-service
        2. Emit synthetic chapter.saved events (via book-service outbox)
        3. Drain extraction_pending queue for the project
        4. All go through the normal extraction pipeline
    Acceptance criteria:
      - All historical chapters processed
      - Pending chat events drained
      - Progress visible in UI
    Test:
      - Integration: create 20 chapters before enable, enable, verify all extracted
    Dependencies: K16.6
    Est: M
```

```
[ ] K16.8 Delete graph endpoint (keep raw data)
    Files:
      - services/knowledge-service/app/api/public/extraction.py (MODIFY)
    Description:
      DELETE /v1/knowledge/projects/{id}/extraction/graph
      Deletes all Neo4j data for this project:
        - :Entity, :Event, :Fact nodes
        - :ExtractionSource nodes
        - EVIDENCED_BY edges (cascade)
      Sets project.extraction_status = 'disabled' but keeps project row.
    Acceptance criteria:
      - All Neo4j project-scoped data gone
      - Postgres project row remains
      - Can be restarted with new extraction job
    Test:
      - Integration: extract, delete graph, verify no Neo4j data for this project
    Dependencies: K11.8
    Est: M
```

```
[ ] K16.9 Rebuild endpoint (delete + start)
    Files:
      - services/knowledge-service/app/api/public/extraction.py (MODIFY)
    Description:
      POST /v1/knowledge/projects/{id}/extraction/rebuild
      Combines K16.8 + K16.3 in one call. Deletes existing graph, then
      starts a new extraction job with scope=all.
    Acceptance criteria:
      - Atomic: if start fails, no partial delete
      - Returns new job_id
    Test:
      - Integration
    Dependencies: K16.3, K16.8
    Est: S
```

```
[ ] K16.10 Change embedding model endpoint
    Files:
      - services/knowledge-service/app/api/public/extraction.py (MODIFY)
    Description:
      PUT /v1/knowledge/projects/{id}/embedding-model
      Body: {embedding_model: "text-embedding-3-small"}
      Warns user (via response) that change requires rebuild.
      If user confirms (via ?confirm=true query), deletes graph
      and sets project.embedding_model to new value.
    Acceptance criteria:
      - Without confirm → returns warning + delta
      - With confirm → deletes graph + updates model
      - Doesn't start new job automatically (user must explicitly trigger)
    Test:
      - Integration
    Dependencies: K16.8
    Est: M
```

```
[ ] K16.11 Monthly budget enforcement
    Files:
      - services/knowledge-service/app/jobs/budget.py (NEW)
    Description:
      Per KSA §5.5. Helper functions:
        - can_start_job(project_id, estimated_cost) → (bool, reason)
        - record_spending(project_id, cost) → updates monthly + all-time counters
          Handles month rollover (current_month_key)
        - check_user_monthly_budget(user_id, cost)
    Acceptance criteria:
      - Monthly rollover resets counter
      - Per-project cap blocks over-budget jobs
      - Per-user aggregate cap blocks over-budget jobs across projects
      - Warning at 80% of budget
    Test:
      - Integration with fake clock
    Dependencies: K10.4
    Est: M
```

```
[ ] K16.12 Cost tracking API
    Files:
      - services/knowledge-service/app/api/public/costs.py (NEW)
    Description:
      - GET /v1/knowledge/costs → user's total spending (all-time, current month)
      - GET /v1/knowledge/projects/{id}/costs → per-project breakdown by job
      - PUT /v1/knowledge/projects/{id}/budget → set monthly cap
      - PUT /v1/knowledge/me/budget → set user-wide monthly cap
    Acceptance criteria:
      - Accurate figures (matches extraction_jobs.cost_spent_usd sum)
      - User-scoped
    Test:
      - Integration
    Dependencies: K16.11
    Est: M
```

```
[ ] K16.13 Extraction control routes in gateway
    Files:
      - services/api-gateway-bff/src/gateway-setup.ts (MODIFY)
    Description:
      Add all /v1/knowledge/projects/{id}/extraction/* routes to proxy config.
      Forward Authorization header.
    Acceptance criteria:
      - All endpoints reachable via gateway
    Test:
      - Integration
    Dependencies: K16.3-K16.10
    Est: S
```

```
[ ] K16.14 Project stats cache updater
    Files:
      - services/knowledge-service/app/jobs/stats_updater.py (NEW)
    Description:
      Maintains stat_entity_count, stat_fact_count, stat_event_count,
      stat_glossary_count on knowledge_projects. Updated:
        - On extraction batch complete (incremental)
        - Daily reconcile job (full recount from Neo4j)
    Acceptance criteria:
      - Counts match reality within 1 minute of data change
      - Daily reconciler fixes any drift
    Test:
      - Integration
    Dependencies: K11.5
    Est: M
```

```
[ ] K16.15 Extraction lifecycle integration test
    Files:
      - services/knowledge-service/tests/integration/test_extraction_lifecycle.py (NEW)
    Description:
      End-to-end test covering:
        1. Create project, enable extraction
        2. Get cost estimate
        3. Start job
        4. Poll progress
        5. Pause mid-run
        6. Resume
        7. Cancel another run
        8. Verify partial graph kept
        9. Delete graph
        10. Rebuild
    Acceptance criteria:
      - All state transitions work
      - Cost tracking accurate
      - No orphaned data
    Test:
      - This IS the test
    Dependencies: K16.1-K16.14
    Est: L
```

### Gate 11 — Extraction Jobs Work

- [ ] Full lifecycle: start → progress → complete
- [ ] Pause/resume/cancel all work correctly
- [ ] Cost enforced atomically (T11 from KSA §9.8)
- [ ] Monthly budget blocks over-budget jobs (T12)
- [ ] Embedding model change triggers rebuild (T13)
- [ ] Rebuild from scratch works (T14)
- [ ] Partial graph preserved on cancel
- [ ] Backfill processes historical chapters + pending events (T16)

---

## 10. Phase K17 — LLM Extraction (Pass 2)

**Goal:** Async LLM-based extraction that validates Pass 1 quarantine,
adds high-confidence facts, and runs via worker-ai with user's BYOK.

### Tasks

```
[ ] K17.1 LLM extraction prompts
    Files:
      - services/knowledge-service/app/extraction/llm_prompts/__init__.py (NEW)
      - services/knowledge-service/app/extraction/llm_prompts/entity_extraction.md (NEW)
      - services/knowledge-service/app/extraction/llm_prompts/relation_extraction.md (NEW)
      - services/knowledge-service/app/extraction/llm_prompts/event_extraction.md (NEW)
      - services/knowledge-service/app/extraction/llm_prompts/fact_extraction.md (NEW)
    Description:
      Carefully written prompts for each extraction type. Use structured
      output (JSON) for reliable parsing. Prompts include:
        - Clear task description
        - Input format
        - Output JSON schema
        - Examples (few-shot)
        - Disambiguation rules (reported speech, hypothetical, etc.)
    Acceptance criteria:
      - Prompts produce parseable JSON 95%+ of the time
      - Follow entity canonicalization rules from K15.1
    Test:
      - Run prompts against golden set (K17.10)
    Dependencies: none
    Est: L
    Notes:
      Spend time here. Prompts are the quality bottleneck. Iterate against
      the golden set (K17.10).
```

```
[ ] K17.2 provider-registry client for BYOK LLM calls
    Files:
      - services/knowledge-service/app/clients/provider_client.py (NEW)
    Description:
      Calls provider-registry internal proxy to invoke user's BYOK LLM model.
      Passes model_source, model_ref, user_id. Returns LLM response.
    Acceptance criteria:
      - Returns model response
      - Handles 4xx/5xx errors from provider
      - Timeout: 60s per call (LLMs can be slow)
    Test:
      - Integration with mock provider
    Dependencies: none (provider-registry is existing)
    Est: M
```

```
[ ] K17.3 JSON extraction with retry on parse failure
    Files:
      - services/knowledge-service/app/extraction/llm_json_parser.py (NEW)
    Description:
      LLMs sometimes return malformed JSON. Helper that:
        1. Calls LLM
        2. Attempts to parse response as JSON
        3. On parse failure: ask LLM to fix it (1 retry)
        4. Validates against expected Pydantic schema
    Acceptance criteria:
      - 95%+ success rate on golden set
      - Retry on malformed JSON
      - Raises ExtractionError if both attempts fail
    Test:
      - Unit with mock LLM
    Dependencies: K17.2
    Est: M
```

```
[ ] K17.4 Entity LLM extractor
    Files:
      - services/knowledge-service/app/extraction/llm_entity_extractor.py (NEW)
    Description:
      Extracts entities from text using prompt K17.1. Returns list of
      (canonical_name, kind, confidence, aliases) tuples.
      Uses K15.1 canonicalization for IDs.
    Acceptance criteria:
      - Handles chapter-sized inputs
      - Returns valid entity records
      - Uses deterministic IDs (idempotent re-run)
    Test:
      - Integration + golden set
    Dependencies: K17.1, K17.3, K15.1
    Est: M
```

```
[ ] K17.5 Relation LLM extractor
    Files:
      - services/knowledge-service/app/extraction/llm_relation_extractor.py (NEW)
    Description:
      Extracts relations between entities. Same pattern as K17.4.
      Includes temporal hints (valid_from if determinable).
    Acceptance criteria:
      - Relations link to existing entity IDs
      - Confidence >= 0.8 for produced relations
    Test:
      - Integration
    Dependencies: K17.4
    Est: M
```

```
[ ] K17.6 Event LLM extractor
    Files:
      - services/knowledge-service/app/extraction/llm_event_extractor.py (NEW)
    Description:
      Extracts plot events with temporal ordering. Events have:
        - description, chapter_id, block_index
        - narrative_order (position in text)
        - participating entities
    Acceptance criteria:
      - Events linked to chapter
      - Entities resolved to canonical IDs
    Test:
      - Integration
    Dependencies: K17.4
    Est: M
```

```
[ ] K17.7 Fact LLM extractor
    Files:
      - services/knowledge-service/app/extraction/llm_fact_extractor.py (NEW)
    Description:
      Atomic statements with provenance. Covers:
        - Decisions, preferences, milestones (from chat content)
        - State facts (from chapter content)
        - Negations ("Kai doesn't know X")
    Acceptance criteria:
      - Facts classified by type
      - Provenance preserved (source message_id / chapter_id)
    Test:
      - Integration
    Dependencies: K17.4
    Est: M
```

```
[ ] K17.8 Pass 2 orchestrator (validates Pass 1 quarantine)
    Files:
      - services/knowledge-service/app/extraction/pass2.py (NEW)
    Description:
      Per KSA §5.2:
        1. Read chat turn or chapter content
        2. Run K17.4 entity extractor
        3. Run K17.5-K17.7 extractors
        4. For each Pass 1 quarantined fact from this source:
           a. Check if Pass 2 confirms (same relation, similar confidence)
           b. If yes: promote to confidence=0.95, clear pending_validation
           c. If no: create new fact with higher confidence, leave old for review
        5. Write new Pass 2 facts (not quarantined, confidence=0.9+)
        6. Update metrics (pass1_confirmed, pass1_contradicted, pass1_ambiguous)
    Acceptance criteria:
      - Pass 1 facts correctly promoted/contradicted
      - New Pass 2 facts written
      - Metrics accurate
    Test:
      - Integration: seed Pass 1 facts, run Pass 2, verify outcomes
    Dependencies: K17.4-K17.7
    Est: L
```

```
[ ] K17.9 Injection defense at extraction time
    Files:
      - services/knowledge-service/app/extraction/pass2.py (MODIFY)
    Description:
      Apply K15.6 neutralize_injection to all LLM-extracted facts before
      writing to Neo4j. Defense in depth beyond the context-build-time defense.
    Acceptance criteria:
      - Facts containing injection patterns get [FICTIONAL] prefix
      - Metric incremented
    Test:
      - Unit with injection-containing fixture
    Dependencies: K15.6, K17.8
    Est: S
```

```
[ ] K17.10 Golden set + quality eval (§9.9)
    Files:
      - tests/fixtures/golden_chapters/ (NEW)
      - services/knowledge-service/tests/quality/test_extraction_eval.py (NEW)
    Description:
      Per KSA §9.9. 10 chapters from public-domain works with annotated
      expected entities/relations/events. Run extraction, compute
      precision/recall/FP-rate.

      Quality gates:
        - Precision >= 0.80
        - Recall >= 0.70
        - FP rate on traps <= 0.15

      Run before any extraction prompt or model change.
    Acceptance criteria:
      - Eval runs end-to-end
      - Thresholds met with default model
      - Regression gates catch prompt degradation
    Test:
      - Run the eval in CI (non-blocking but logged)
    Dependencies: K17.4-K17.8
    Est: L
    Notes:
      Start with 5 chapters, expand to 10 later. Fiction from Project
      Gutenberg is public domain and good source material.
```

```
[ ] K17.11 Run Pass 2 via worker-ai from extraction job
    Files:
      - services/worker-ai/app/tasks/extraction_job_runner.py (MODIFY)
    Description:
      In K16.6 job runner, call K17.8 Pass 2 orchestrator for each item.
      Pass the user's BYOK model from job config.
    Acceptance criteria:
      - Pass 2 runs per item
      - Cost tracked atomically
      - Errors caught per item (don't fail whole job)
    Test:
      - Integration
    Dependencies: K16.6, K17.8
    Est: M
```

```
[ ] K17.12 Rate limiting for LLM calls
    Files:
      - services/knowledge-service/app/clients/provider_client.py (MODIFY)
    Description:
      Respect per-user rate limits on LLM calls to avoid provider 429s.
      Simple token bucket: max 10 calls per second per user.
      On 429 from provider: exponential backoff.
    Acceptance criteria:
      - Never exceeds 10 calls/sec/user
      - 429 backoff works
    Test:
      - Unit with fake provider
    Dependencies: K17.2
    Est: M
```

### Gate 12 — LLM Extraction Pipeline Works

- [ ] Pass 2 runs successfully on a test project
- [ ] Pass 1 quarantine correctly validated
- [ ] Metrics show pass1_confirmed/contradicted/ambiguous distribution
- [ ] Quality eval passes thresholds (P≥0.80, R≥0.70, FP≤0.15)
- [ ] Rate limiting prevents 429 storms
- [ ] Cost tracking matches actual provider billing (spot-check)
- [ ] Injection defense applies at extraction time

---

## 11. Phase K18 — Context Builder Mode 3

**Goal:** Wire L2 and L3 into the context builder for projects with
extraction enabled. Completes the user-facing memory experience.

### Tasks

```
[ ] K18.1 Mode 3 builder scaffold
    Files:
      - services/knowledge-service/app/context/modes/full.py (NEW)
    Description:
      Top-level Mode 3 builder that assembles all layers:
        - L0 (from Track 1 K4.5)
        - L1 (from Track 1 K4.6)
        - Glossary (reduced — L2 provides richer data)
        - L2 facts
        - L3 passages
        - Absence markers
        - CoT instructions
      Returns ContextResponse with mode="full", recent_message_count=20.
    Acceptance criteria:
      - Dispatcher from K4.10 now routes extraction_enabled projects here
      - Returns valid XML memory block
    Test:
      - Integration
    Dependencies: K4 (Track 1)
    Est: M
```

```
[ ] K18.2 L2 fact selector with temporal grouping
    Files:
      - services/knowledge-service/app/context/selectors/facts.py (NEW)
    Description:
      Per KSA §4.2:
        1. Extract entity names from user message (K4.3 pattern extractor)
        2. Query Neo4j for 1-hop facts (confidence >= 0.8)
        3. Query Neo4j for 2-hop contextual facts
        4. Rank by relevance + temporal recency
        5. Group into <current>, <recent>, <background>, <negative>
        6. Apply compression rollover (top 15 + summary tail)
        7. Return formatted XML block
    Acceptance criteria:
      - 1+2 hop queries use parameterized Cypher with user_id filter
      - Temporal grouping based on chapter order
      - Negative facts surface in <negative> block
      - Compression rollover used when facts > 15
    Test:
      - Integration with fixture data
    Dependencies: K11.6, K11.7
    Est: L
```

```
[ ] K18.3 L3 semantic search selector
    Files:
      - services/knowledge-service/app/context/selectors/passages.py (NEW)
    Description:
      Per KSA §4.3:
        1. Detect query type (recent/historical/general) — keyword-based
        2. Embed user message via embedding-service (K12.6)
        3. Route to correct dimension index based on project.embedding_model
        4. Run hybrid scoring (similarity + recency decay)
        5. Format as <passage> XML with source/type/relevance attributes
    Acceptance criteria:
      - Dimension routing correct per embedding_model
      - Hybrid scoring applied
      - Recent-type queries weight recency heavily
      - Parameterized Cypher
    Test:
      - Integration with fixture Neo4j data
    Dependencies: K12.6, K11.5
    Est: L
```

```
[ ] K18.4 Cross-layer dedup (L1 vs L2)
    Files:
      - services/knowledge-service/app/context/formatters/dedup.py (MODIFY from K4.12)
    Description:
      Enhanced dedup that also filters L2 facts already expressed in L1 summary.
      Per KSA §4.4.3.
    Acceptance criteria:
      - Facts already in L1 are dropped from L2
      - Metric `l2_fact_deduplicated` incremented
    Test:
      - Unit
    Dependencies: K4.12 (Track 1)
    Est: S
```

```
[ ] K18.5 Absence detection (§4.5)
    Files:
      - services/knowledge-service/app/context/selectors/absence.py (NEW)
    Description:
      Per KSA §4.5. Detects entities mentioned in user message that have
      zero L2/L3 coverage. Returns list for <no_memory_for> block.
    Acceptance criteria:
      - Entity mentioned + no L2 hit → in absence list
      - Entity covered by L2 OR L3 → not in absence list
    Test:
      - Unit
    Dependencies: K18.2, K18.3
    Est: M
```

```
[ ] K18.6 CoT instructions block
    Files:
      - services/knowledge-service/app/context/formatters/instructions.py (NEW)
    Description:
      Per KSA §4.2 + §4.5. Generates the <instructions> block telling the
      LLM to engage with facts, respect negations, ask about absences.
      Language-aware (matches user's preferred_locale).
    Acceptance criteria:
      - Instructions always present in Mode 3
      - Language matches user locale
    Test:
      - Unit
    Dependencies: K18.2, K18.5
    Est: S
```

```
[ ] K18.7 Mode 3 full integration
    Files:
      - services/knowledge-service/app/context/modes/full.py (MODIFY)
    Description:
      Assembles all pieces from K18.2-K18.6 into the final Mode 3 memory block.
      Enforces token budget with priority-based drops (KSA §4.4.4).
    Acceptance criteria:
      - Full Mode 3 block under token budget
      - All layers present when data exists
      - XML valid
    Test:
      - Integration: full context build for a project with extracted data
    Dependencies: K18.1-K18.6
    Est: M
```

```
[ ] K18.8 Dispatcher update (Mode 3 enabled)
    Files:
      - services/knowledge-service/app/context/builder.py (MODIFY)
    Description:
      Update K4.10 dispatcher to route extraction_enabled=true projects to
      Mode 3 builder (K18.7). No longer raises NotImplementedError.
    Acceptance criteria:
      - Extraction-enabled project → Mode 3
      - Extraction-disabled project → Mode 2 (unchanged)
      - No project → Mode 1 (unchanged)
    Test:
      - Integration: all three mode paths
    Dependencies: K18.7
    Est: S
```

```
[ ] K18.9 Prompt caching hints (Rec #1 from context review)
    Files:
      - services/knowledge-service/app/context/formatters/memory_block.py (MODIFY)
    Description:
      Per KSA §7.5. Add cache-breakpoint markers in the memory block so
      chat-service can set Anthropic cache_control: ephemeral on the stable
      prefix (L0+L1) separately from the volatile suffix (L2+L3).
    Acceptance criteria:
      - Context builder returns both stable and volatile segments
      - chat-service can opt into caching
    Test:
      - Unit
    Dependencies: K18.7
    Est: M
    Notes:
      Optional but high-value — 80-90% cost reduction on memory for active chats.
```

```
[ ] K18.10 chat-service integration for Mode 3
    Files:
      - services/chat-service/app/services/stream_service.py (MODIFY)
    Description:
      Update K5.3 to handle the new Mode 3 response. Specifically:
        - Respect recent_message_count=20 when in Mode 3
        - Use prompt caching hints if K18.9 done
        - Log mode for observability
    Acceptance criteria:
      - Mode 3 sessions use 20 messages, not 50
      - Full memory block in system prompt
      - Cache hit ratio improves after first turn
    Test:
      - Integration
    Dependencies: K18.8, K5.3 (Track 1)
    Est: S
```

### Gate 13 — Mode 3 End-to-End

**FINAL GATE.** This is the full Track 2 verification.

- [ ] Enable extraction on a project, run full extraction job
- [ ] Send chat message in that project
- [ ] Verify Mode 3 context block in system prompt (L2 facts present)
- [ ] Verify L3 passages appear for queries with semantic matches
- [ ] Verify 20-message history (not 50)
- [ ] Verify negative facts prevent inconsistency ("character reveals secret" test)
- [ ] Disable extraction → Mode 2 works again (partial graph preserved)
- [ ] Re-enable extraction → Mode 3 works, picks up pending events
- [ ] Cross-user isolation: User A's extraction can't see User B's data (T18)
- [ ] Chaos: stop Neo4j mid-chat, verify Mode 2 fallback works
- [ ] Cost tracking: run a small extraction, verify billing matches actual usage
- [ ] Quality eval: golden set passes thresholds

---

## 12. Integration Test Scenarios (T11–T20)

Track 2-specific tests from KSA §9.8.

```
T11: Atomic cost cap — concurrent try_spend calls never exceed max_spend_usd
    [ ] Pass

T12: Monthly budget blocks over-budget jobs
    [ ] Pass

T13: Embedding model change triggers rebuild
    [ ] Pass

T14: Full rebuild from scratch
    [ ] Pass

T15: Chat turn while extraction disabled → queued in extraction_pending
    [ ] Pass

T16: Enable extraction → backfill drains pending queue
    [ ] Pass

T17: Glossary entity created → appears in Mode 3 context within 5s
    [ ] Pass

T18: Cross-user isolation with concurrent extraction
    [ ] Pass

T19: Delete user account → all Neo4j data gone within SLA
    [ ] Pass

T20: Prompt injection in chapter → neutralized in L2/L3 context
    [ ] Pass
```

Plus chaos scenarios from KSA §9.10:

```
[ ] C01: Stop Neo4j mid-chat → Mode 2 fallback
[ ] C02: Stop knowledge-service → chat works without memory
[ ] C03: LLM provider 429 → job backs off and pauses
[ ] C04: Embedding service OOM → job pauses with error
[ ] C05: Redis loses events → consumer catches up from event_log
[ ] C06: Manually corrupt Neo4j data → rebuild from event_log succeeds
[ ] C07: User deletes project mid-extraction → clean cancel
[ ] C08: Bulk delete 1000 chapters → cascade rate-limited, no overload
```

---

## 13. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cost overrun due to runaway loop | Medium | **Critical** | Atomic cost cap (K10.4) + monthly budget (K16.11) + rate limiting (K17.12) |
| Neo4j performance degrades at 5000-ch scale | Medium | High | Composite indexes, evidence_count cache, HNSW tuning |
| LLM extraction quality too low | Medium | High | Golden set eval (K17.10); iterate prompts before ship |
| Cypher injection | Low | **Critical** | Mandatory parameterized queries, CI lint, K11.4 helper |
| Cross-user data leak | Low | **Critical** | user_id filter on every query, K11.4 helper, T18 test |
| Embedding dimension mismatch → missing results | Medium | Medium | Dimension-routed queries (K18.3), project-scoped model |
| Pass 1 quarantine pollutes L2 before Pass 2 runs | Medium | Medium | L2 query filters confidence>=0.8 AND not pending_validation |
| Prompt injection poisons context | Medium | High | Injection defense at both extraction (K15.6) and context build (K18.7) |
| worker-ai OOM during large backfill | Medium | Medium | Chunk processing, memory limits, rate limiting |
| Concurrent extraction on same project | Low | Medium | Only one active job per project (K16.3 409) |
| User changes embedding model → orphaned vectors | Low | Low | Rebuild required (K16.10 warning) |
| Redis stream eviction breaks consumer | Low | Medium | Hybrid catch-up via event_log (K14.2) |
| Backup takes too long at scale | Low | Medium | Incremental backups, tier retention |
| Reconcile job interferes with live extraction | Low | Low | Run at low-traffic hours, use read-only queries |
| Provider API changes break extraction | Low | Medium | Tested via mocked provider; update prompts when upstream changes |

---

## 14. Phase Dependencies and Parallelism

```
Prerequisites:
  Track 1 complete  ──────────────────────┐
  D2-01 (Neo4j deployed) ─────────────────┤
  D2-04 (embedding service) ──────────────┤
  D3-00 (idempotency layer) ──────────────┤
                                          ▼

K10 (postgres) ───────────────────────────┐
                                          │
K11 (Neo4j schema) ───────────────────────┤
                                          │
K12 (embedding service) ──────────────────┤
                                          │
K13 (chat turn event) ────────────────────┤
                                          │
                                          ▼
                            K14 (event consumer)
                                          │
                                          ▼
                          K15 (pattern extractor + quarantine)
                                          │
                                          ▼
                                K16 (job engine)
                                          │
                                          ▼
                                K17 (LLM extraction)
                                          │
                                          ▼
                         K18 (Mode 3 context builder)
                                          │
                                          ▼
                                   Gate 13 — Ship Track 2
```

**Parallel work opportunities:**
- K10 + K11 + K12 can run in parallel (independent data layers)
- K13 is trivial and unblocks nothing complex
- K14 needs K10 + K13
- K15 can start planning while K14 is in progress
- K16 + K17 can be developed in parallel once K15 is done
- K18 is the final integration step

---

## 15. Getting Started Checklist (Day 1 of Track 2)

Before writing any code:

- [ ] Confirm Track 1 is fully shipped and stable
- [ ] Re-read KSA §3.4 (Neo4j amendments), §3.8.5 (provenance cascade), §5 (extraction), §7.5 (prompt caching)
- [ ] Re-read 101 §3.6 (Neo4j schema), §3.5.4 (idempotency), §3.5.5 (consumer catch-up)
- [ ] Verify D2 prerequisites complete (Neo4j deployed, bge-m3 service available)
- [ ] Create a new branch: `git checkout -b feature/knowledge-service-track2`
- [ ] Update SESSION_PATCH.md with "Starting Track 2 implementation"
- [ ] Run Track 1 smoke tests (ensure nothing broken before starting)
- [ ] Start with K10.1 (extraction_pending table migration)

---

## 16. Progress Tracking

```
K10 Postgres              [ / 5  tasks]  Gate 6:  [ ]
K11 Neo4j schema          [ / 9  tasks]  Gate 7:  [ ]
K12 Embedding service     [ / 7  tasks]  Gate 8:  [ ]
K13 Chat turn event       [ / 3  tasks]
K14 Event consumer        [ / 8  tasks]  Gate 9:  [ ]
K15 Pattern extractor     [ / 12 tasks]  Gate 10: [ ]
K16 Job engine            [ / 15 tasks]  Gate 11: [ ]
K17 LLM extraction        [ / 12 tasks]  Gate 12: [ ]
K18 Mode 3 builder        [ / 10 tasks]  Gate 13: [ ]

Integration tests         [ / 10 tests]  (T11-T20)
Chaos scenarios           [ / 8  tests]  (C01-C08)

Total Track 2 tasks: 81
```

---

## 17. After Track 2 Ships

When all gates pass and tests are green:

1. **Commit final state:** "feat(knowledge): Track 2 complete — opt-in extraction infrastructure"
2. **Write retrospective:** `docs/sessions/TRACK2_RETRO.md`
   - Time per phase (actual vs estimate)
   - Hardest task
   - Most valuable test caught
   - Things to refactor in Track 3
   - Whether you'd do it again
3. **Use Track 2 in real writing.** Run extraction on one of your actual books.
   Let it sit for a week or two. See what breaks or annoys you.
4. **Decide on Track 3.** Evaluate if the power-user memory UI, tool calling,
   and regeneration are worth building. Many users may stop at Track 2 and
   never need Track 3.

Track 2 is the **hardest** shipment. Celebrate when it's done.

---

## 18. Out of Scope — Track 2 Non-Goals

Explicit list of things you'll be tempted to build:

- **Memory UI power-user tabs** (Timeline, Entities table, Raw drawers) → Track 3
- **Tool calling** (memory tools for LLMs) → Track 3
- **Summary regeneration** (LLM-based L0/L1 refresh) → Track 3
- **Extraction Jobs UI in memory page** → Track 3 K19b (the API endpoints exist in K16, but the UI comes in Track 3)
- **Inline fact correction UI** → Track 3
- **Write advanced Cypher reports** ("plot hole detection", "character arc visualization") → Future enhancements
- **Cross-project entity linking** ("tunnel" entities) → Open question, not yet decided
- **Share extraction across users** (collaborative projects) → Never, per hobby scope
- **Real-time collaborative editing of memory** → Never, per hobby scope
- **Fine-tuning your own extraction model** → Never (BYOK covers this)
- **SOC 2 / HIPAA compliance infrastructure** → Never, per KSA §7.7

If you find yourself building any of these, STOP. Note for Track 3 or skip entirely.

---

## 19. Critical Success Factors

These are the things that MUST go right for Track 2 to be trustworthy:

### 1. Cost correctness
Users pay real money. The atomic spend pattern in K10.4 is the single most
important piece of code. Test it with concurrent workers. Audit every place
that updates `actual_cost_usd` or `current_month_spent_usd`.

### 2. Cross-user isolation
One leaked query = destroyed user trust. Every Cypher has user_id filter.
Every Postgres query has user_id filter. T18 test is security-critical.
Code review EVERY PR for isolation.

### 3. Idempotency
Events may be delivered twice. LLMs may return different extractions. The
idempotency layer (K15.1, K11.5-K11.8, 101 §3.5.4) is the reason this works.
Test re-running the same event produces no new data.

### 4. Graceful degradation
Mode 3 cannot crash chat. If Neo4j is down, fall back to Mode 2. If Pass 2
fails, leave Pass 1 quarantine. If embedding service is slow, timeout and
skip L3. Users should never see an error from memory — only degraded context.

### 5. Quality gates
Extraction quality is subjective but measurable. The golden set eval
(K17.10) is not optional. Run it before shipping Track 2 and after every
prompt/model change. If P<0.80 or R<0.70, the extraction is too bad to
trust in production.

### 6. Cleanup correctness
Partial operations (append, re-extract, delete) must be precise. Deleting
a chapter must NOT remove entities that still have evidence from other
chapters. K11.8 provenance cascade + T06/T07 tests verify this.

---

## 20. When You Hit a Dead End

Track 2 is significantly harder than Track 1. You will hit dead ends. Some
common ones and resolutions:

**"My Cypher is slow."**
- Check indexes used: `EXPLAIN` the query
- Ensure composite indexes (user_id first) per 101 §3.6
- Check evidence_count is populated (not NULL on existing nodes)

**"Pass 1 and Pass 2 keep disagreeing."**
- Look at specific disagreements — is it a pattern issue or LLM issue?
- Tune Pass 1 patterns (K15.3) to match Pass 2 output style
- Accept some disagreement — that's what quarantine is for

**"Extraction job hangs forever."**
- Check worker-ai logs for errors
- Check LLM rate limit (K17.12)
- Check max_spend_usd — job may be auto-paused silently

**"Neo4j memory keeps growing."**
- Check for dangling edges (run K11.9 reconcile)
- Increase JVM heap (NEO4J_server_memory_heap_max__size)
- Check evidence_count cleanup is actually running

**"Context builder sometimes returns wrong mode."**
- Check caching (K6.2 — may be stale)
- Verify extraction_enabled is up-to-date in DB
- Add more logging at mode dispatch (K4.10 → K18.8)

**"Tests pass locally but fail in CI."**
- Neo4j startup timing — increase start_period in healthcheck
- Consumer group state — reset between test runs
- Random port conflicts — use test containers

---

*Created: 2026-04-13 (session 34) — PM implementation plan for KSA Track 2*
*Total tasks: 81 + 10 integration tests + 8 chaos scenarios*
*Target: complete Track 2 as the opt-in premium memory experience*
*Prerequisite: Track 1 complete and stable*
