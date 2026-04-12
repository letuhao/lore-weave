# Knowledge Service — Track 1 Implementation Plan

> **Status:** Implementation plan, ready to execute
> **Created:** 2026-04-13 (session 34)
> **Scope:** Track 1 only (K0–K9 from [KNOWLEDGE_SERVICE_ARCHITECTURE.md §9](KNOWLEDGE_SERVICE_ARCHITECTURE.md))
> **Goal:** Ship Static Memory — zero AI cost, no Neo4j, usable baseline

> **This doc replaces discussion with action.** Each task has concrete files,
> acceptance criteria, and a test. Dependencies are explicit. QC gates enforce
> pause-and-verify between risky transitions. Tick each checkbox as you finish.

---

## 1. Executive Summary

### What Track 1 delivers

A working `knowledge-service` that provides **Static Memory** to chat-service
without any LLM extraction or Neo4j. Users get:

- **Project-scoped chat** with persistent instructions (like ChatGPT Projects)
- **Automatic glossary context** injected per chat turn (from existing curated
  glossary; zero AI cost)
- **User bio** (global identity) always in the prompt
- **Style examples** per project to match user's writing voice
- **Three memory modes** (`no_project`, `static`, `full`) — Track 1 implements the first two
- **Frontend UI** to create projects, edit instructions, manage global bio
- **Chat header indicator** showing which memory mode is active

### What Track 1 explicitly does NOT include

| Out of scope | When it ships |
|---|---|
| Neo4j deployment | Track 2 (K10–K18) |
| LLM-based extraction (Pass 2) | Track 2 |
| Pattern-based extraction (Pass 1) | Track 2 |
| L2 facts from knowledge graph | Track 2 |
| L3 semantic search via vectors | Track 2 |
| Extraction Jobs system | Track 2 |
| Embedding service (bge-m3) | Track 2 |
| `extraction_pending` queue | Track 2 |
| `chat.turn_completed` outbox event | Track 2 (chat-service still writes it, but there's no consumer yet) |
| Full memory UI (timeline, entities, raw drawers) | Track 3 (K19) |
| Tool calling integration | Track 3 (K21) |
| Summary regeneration | Track 3 (K20) |
| Provenance edges (`EVIDENCED_BY`) | Track 2 (Neo4j) |
| Per-project embedding model choice | Track 2 |
| Prompt injection defense for facts | Track 2 (but still applies L0/L1 safe rendering) |

### What "done" looks like for Track 1

Ticking all boxes below means Track 1 is complete:

- [ ] `knowledge-service` runs cleanly via `docker compose up -d`
- [ ] `/health` endpoint returns 200 with DB connection check
- [ ] User can create a project via the frontend
- [ ] User can edit their global bio (L0) via Settings → Memory
- [ ] User can set project instructions and style examples (L1)
- [ ] Assigning a chat session to a project changes the chat's memory mode
- [ ] Chat header shows correct memory mode (No memory / Static memory)
- [ ] chat-service `build_system_prompt` calls `knowledge-service` before every LLM turn
- [ ] Context block is injected into system prompt with correct XML structure
- [ ] Glossary entities are selected by FTS and included when project has a linked book
- [ ] When `knowledge-service` is down, chat-service falls back gracefully (last 50 messages only)
- [ ] Layer-level timeouts enforced (<300ms total for context build)
- [ ] Cross-user isolation verified by test T18-lite (no Neo4j variant)
- [ ] All integration tests T01–T07 (Track 1 subset) pass
- [ ] Security lint: no f-string SQL, no f-string XML
- [ ] Backup script includes `loreweave_knowledge` database
- [ ] Docs updated: `SESSION_PATCH.md`, `CLAUDE.md` service list

### Honest effort estimate

This is NOT a 1-week project. With focused work (you + AI assistant, solo pace):

| Phase | Effort | Why |
|---|---|---|
| K0 scaffold | 4–6 hours | New service, docker wiring, auth, logging |
| K1 schema | 2–4 hours | Migrations + repositories |
| K2 glossary schema | 3–5 hours | Cross-service change (Go code) |
| K3 short description | 2–3 hours | Template + backfill job |
| K4 context builder | 8–12 hours | Most complex part; many edge cases |
| K5 chat-service integration | 3–5 hours | HTTP client + Python Pydantic models |
| K6 degradation | 4–6 hours | Circuit breaker + cache + timeouts |
| K7 public API | 6–10 hours | Many endpoints + authz + tests |
| K8 frontend projects UI | 8–12 hours | React components + i18n + error handling |
| K9 chat indicator | 3–5 hours | Popover + session dropdown + stats fetch |
| **Integration + QC** | 6–10 hours | End-to-end tests, fixing bugs |
| **Total realistic** | **50–80 hours** | 2–4 weeks of evenings |

Accept this. Track 1 is the **smallest shippable increment**, and it's still
nontrivial. Don't try to compress it.

---

## 2. Architecture Recap (30-Second Version)

Track 1 components and their interactions:

```
┌─────────────────────────────────────────────────────────┐
│ Frontend (Vite + React)                                 │
│   features/knowledge/*  (Projects UI, Global bio)       │
└────────────┬────────────────────────────────────────────┘
             │ /v1/knowledge/* + /v1/chat/*
             ▼
┌─────────────────────────────────────────────────────────┐
│ api-gateway-bff (existing)                              │
│   Proxies /v1/knowledge/* to knowledge-service          │
└────┬────────────────────────────────────┬───────────────┘
     │                                    │
     ▼                                    ▼
┌──────────────────┐              ┌──────────────────┐
│ chat-service     │──internal───▶│ knowledge-service│
│ (existing)       │  X-Token     │ (NEW)            │
│                  │              │                  │
│ stream_service   │  /internal/  │ Context builder  │
│ calls context    │  context/    │ (Mode 1 / 2)     │
│ before LLM       │  build       │                  │
└──────┬───────────┘              └──────┬───────────┘
       │                                 │
       │                                 │ read
       │                                 ▼
       │                       ┌──────────────────┐
       │                       │ loreweave_       │
       │                       │ knowledge        │
       │                       │ (NEW PG DB)      │
       │                       │ - projects       │
       │                       │ - summaries      │
       │                       └──────────────────┘
       │
       │ read
       ▼
┌──────────────────┐         ┌──────────────────┐
│ loreweave_chat   │         │ loreweave_       │
│ (existing)       │         │ glossary         │
│ - chat_sessions  │         │ (existing +      │
│   (+ project_id) │         │  new columns)    │
│                  │         │ - short_desc     │
│                  │         │ - search_vector  │
│                  │         │ - is_pinned      │
└──────────────────┘         └──────────────────┘
                             Queried via FTS by
                             knowledge-service
```

**Key invariants to remember while building:**

1. **knowledge-service is stateless** w.r.t. chat sessions — all data reads come from its own DB or cross-service queries.
2. **chat-service is ignorant of mode logic** — it calls `/internal/context/build` and gets back a ready-to-inject context block plus a `recent_message_count`.
3. **Graceful degradation is mandatory** — if knowledge-service is down, chat-service must continue working without memory.
4. **No extraction in Track 1** — no LLM calls happen from knowledge-service. Zero incremental AI cost.
5. **Glossary is queried read-only** via Postgres FTS in its own DB; knowledge-service uses a separate read connection pool to `loreweave_glossary`.

---

## 3. Task Template (how to read each task)

Each task below follows this template:

```
[ ] K{phase}.{num} Title
    Files:
      - services/knowledge-service/app/foo.py (NEW)
      - services/chat-service/app/bar.py (MODIFY)
    Description:
      One-paragraph what and why.
    Acceptance criteria:
      - Specific testable condition #1
      - Specific testable condition #2
    Test:
      - Unit: tests/unit/test_foo.py::test_something
      - OR Integration: tests/integration/test_bar.sh scenario X
    Dependencies:
      - K{previous tasks}
    Est:
      S (<1h) | M (1-3h) | L (3-8h)
    Notes:
      Gotchas, things to be careful about.
```

---

## 4. Phase K0 — Knowledge-Service Scaffold

**Goal:** A FastAPI app that starts in Docker, exposes `/health`, authenticates
internal requests, logs structured JSON, and connects to its Postgres database.

**Gate:** [Gate 1](#gate-1--scaffold-clean) at the end of this phase.

### Tasks

```
[ ] K0.1 Create service directory structure
    Files:
      - services/knowledge-service/ (NEW)
      - services/knowledge-service/app/ (NEW)
      - services/knowledge-service/app/__init__.py (NEW)
      - services/knowledge-service/app/main.py (NEW)
      - services/knowledge-service/app/config.py (NEW)
      - services/knowledge-service/pyproject.toml (NEW)
      - services/knowledge-service/README.md (NEW, ~20 lines)
    Description:
      Create the folder tree matching the implementation skeleton from
      KSA §4.6. Include the modules we'll actually use in Track 1
      (context/, db/, api/internal/, api/public/). Stub modules with
      docstrings but no implementation yet.
    Acceptance criteria:
      - Directory structure exists
      - `pyproject.toml` has FastAPI, uvicorn, asyncpg, httpx, pydantic, purgatory
      - `README.md` mentions this is Track 1 scope
    Test:
      - File existence check in Gate 1 smoke script
    Dependencies: none
    Est: S
    Notes:
      Do NOT create placeholder files for Track 2/3 phases (Neo4j driver,
      extraction pipeline, embedding client). Add those in their own phase.
```

```
[ ] K0.2 Dockerfile
    Files:
      - services/knowledge-service/Dockerfile (NEW)
    Description:
      Multi-stage Dockerfile based on python:3.13-slim. Install uv, copy
      pyproject + lock, install deps, copy app, run uvicorn.
    Acceptance criteria:
      - `docker build services/knowledge-service` succeeds
      - Image size < 300 MB
      - Non-root user inside container
    Test:
      - `./scripts/build-knowledge-service.sh` (new) succeeds
    Dependencies: K0.1
    Est: S
    Notes:
      Match the style used by chat-service's Dockerfile for consistency.
```

```
[ ] K0.3 Config loader
    Files:
      - services/knowledge-service/app/config.py
    Description:
      Pydantic BaseSettings with fields:
        - KNOWLEDGE_DB_URL (postgres DSN)
        - GLOSSARY_DB_URL (read-only pool to loreweave_glossary)
        - REDIS_URL (for future event consumer)
        - INTERNAL_SERVICE_TOKEN (shared secret)
        - LOG_LEVEL (default INFO)
        - HOST, PORT (defaults 0.0.0.0:8000)
    Acceptance criteria:
      - Missing required env var = service fails to start with clear error
      - Sensible defaults for non-critical fields
    Test:
      - Unit: tests/unit/test_config.py::test_missing_required_raises
    Dependencies: K0.1
    Est: S
    Notes:
      Follow CLAUDE.md rule: "services fail to start if required secrets missing".
```

```
[ ] K0.4 Logging setup with JSON + trace_id + secret redaction
    Files:
      - services/knowledge-service/app/logging_config.py (NEW)
    Description:
      Structured JSON logging via python-json-logger. All log records
      include trace_id (from incoming X-Trace-Id header or generated
      uuid4). Install a RedactFilter per §7.7a that strips API key patterns.
    Acceptance criteria:
      - Logs are valid JSON on stdout
      - Every record has timestamp, level, service, trace_id
      - API key patterns in messages are redacted as ***REDACTED***
    Test:
      - Unit: tests/unit/test_logging.py::test_redact_filter
    Dependencies: K0.1
    Est: S
    Notes:
      Use contextvars for trace_id propagation. Don't rely on thread-locals
      — asyncio code breaks those.
```

```
[ ] K0.5 Database connection pools (asyncpg)
    Files:
      - services/knowledge-service/app/db/__init__.py (NEW)
      - services/knowledge-service/app/db/postgres.py (NEW)
    Description:
      Create two connection pools:
        - knowledge_pool: read/write to loreweave_knowledge
        - glossary_pool: read-only to loreweave_glossary (for FTS queries)
      Pool size: min 2, max 10. Connection timeout: 5s.
    Acceptance criteria:
      - Pools initialize on app startup
      - Pools close cleanly on app shutdown
      - Failed DB connection at startup = service refuses to start
    Test:
      - Integration: tests/integration/test_db_pools.py
    Dependencies: K0.3
    Est: S
    Notes:
      Per CLAUDE.md: cloud readiness requires DB pool tuning. Use the
      same values as chat-service for consistency.
```

```
[ ] K0.6 Internal auth middleware
    Files:
      - services/knowledge-service/app/api/middleware/internal_auth.py (NEW)
      - services/knowledge-service/app/api/middleware/__init__.py (NEW)
    Description:
      FastAPI dependency that verifies the X-Internal-Token header matches
      INTERNAL_SERVICE_TOKEN for /internal/* routes. Public routes (/v1/*)
      use JWT auth via the gateway (handled later).
    Acceptance criteria:
      - /internal/* without header returns 401
      - /internal/* with wrong token returns 401
      - /internal/* with correct token returns 200 (on a stub endpoint)
    Test:
      - Integration: tests/integration/test_internal_auth.py
    Dependencies: K0.3
    Est: S
    Notes:
      Constant-time comparison for the token (secrets.compare_digest) —
      prevents timing attacks even in hobby scope.
```

```
[ ] K0.7 /health endpoint
    Files:
      - services/knowledge-service/app/api/health.py (NEW)
      - services/knowledge-service/app/main.py (UPDATE — mount router)
    Description:
      GET /health returns {status: "ok", db: "ok"|"error", glossary_db: "ok"|"error"}
      with HTTP 200 if DB is reachable, 503 otherwise.
    Acceptance criteria:
      - Returns 200 + JSON when DBs reachable
      - Returns 503 when knowledge_pool is down
      - Responds within 100ms under normal conditions
    Test:
      - Integration: tests/integration/test_health.py
    Dependencies: K0.5
    Est: S
    Notes:
      Healthcheck in docker-compose.yml depends on this.
```

```
[ ] K0.8 Wire into docker-compose.yml
    Files:
      - infra/docker-compose.yml (MODIFY)
      - infra/db-ensure.sh (MODIFY — add loreweave_knowledge DB)
    Description:
      Add knowledge-service entry with:
        - build: services/knowledge-service
        - depends_on: postgres (healthy), redis (started)
        - environment: all required vars from .env
        - healthcheck: curl /health
        - restart: unless-stopped
        - logging: json-file max-size 50m max-file 5
      Update db-ensure.sh to create loreweave_knowledge database on startup.
    Acceptance criteria:
      - `docker compose up -d knowledge-service` starts successfully
      - `docker compose logs knowledge-service` shows JSON logs
      - `curl http://localhost:<port>/health` returns 200 (if port exposed)
    Test:
      - Manual: docker compose up, verify container is healthy
    Dependencies: K0.7
    Est: M
    Notes:
      Use a profile flag ("knowledge") so users can start minimal stack
      without knowledge-service if desired. Reference: KSA §9.5.
```

```
[ ] K0.9 Proxy route in api-gateway-bff
    Files:
      - services/api-gateway-bff/src/gateway-setup.ts (MODIFY)
    Description:
      Add proxy route: /v1/knowledge/* → http://knowledge-service:8000/v1/knowledge/*
      Use the existing proxy pattern (createProxyMiddleware). JWT forwarded
      as Authorization header. Not exposed: /internal/* (service-to-service only).
    Acceptance criteria:
      - `curl /v1/knowledge/health-public` (new public endpoint for testing)
        routes through gateway
      - /internal/* is NOT exposed through gateway
    Test:
      - Integration: curl through gateway succeeds
    Dependencies: K0.8
    Est: S
    Notes:
      Add a tiny public health endpoint (GET /v1/knowledge/ping) for this
      test. Will be removed in K7 when real endpoints are added.
```

### Gate 1 — Scaffold Clean

**STOP.** Before moving to K1, verify:

- [ ] `docker compose --profile knowledge up -d` starts knowledge-service within 30s
- [ ] `docker compose ps knowledge-service` shows healthy
- [ ] `curl http://localhost:3000/v1/knowledge/ping` returns 200 via gateway
- [ ] `curl http://localhost:8000/health` returns 200 directly (if port exposed)
- [ ] `docker compose logs knowledge-service` shows JSON logs with trace_id
- [ ] `curl http://localhost:8000/internal/something -H "X-Internal-Token: wrong"` returns 401
- [ ] `docker compose down` stops cleanly (no orphaned connections)

If any fail, fix before proceeding. No point writing business logic on a broken scaffold.

---

## 5. Phase K1 — Postgres Schema

**Goal:** Create the knowledge-service database tables and a tiny repository
layer for reads/writes.

### Tasks

```
[ ] K1.1 Pick migration tool
    Files:
      - services/knowledge-service/pyproject.toml (UPDATE — add yoyo-migrations or alembic)
    Description:
      Use yoyo-migrations (simple SQL files) OR alembic (auto-generated).
      Recommendation: yoyo-migrations — hobby projects don't need alembic's
      complexity, and plain SQL is inspectable.
    Acceptance criteria:
      - Dependency added
      - Decision documented in README
    Test:
      - n/a
    Dependencies: K0.1
    Est: S
    Notes:
      If yoyo: create migrations/ folder with YYYYMMDD_NNN_description.sql naming.
```

```
[ ] K1.2 Migration 001: knowledge_projects table
    Files:
      - services/knowledge-service/migrations/20260413_001_projects.sql (NEW)
    Description:
      Create table per KSA §3.3 schema. Include all extraction fields even
      though Track 1 doesn't use them (extraction_enabled default false).
      Include indexes from §3.3.
    Acceptance criteria:
      - Migration applies cleanly to fresh DB
      - Migration is idempotent (re-running succeeds)
      - Table schema matches KSA §3.3 exactly
    Test:
      - Integration: tests/integration/test_migrations.py
    Dependencies: K1.1
    Est: S
    Notes:
      Include the CHECK constraints for project_type and extraction_status.
      Use uuidv7() for project_id default. Reference: KSA §3.3.
```

```
[ ] K1.3 Migration 002: knowledge_summaries table
    Files:
      - services/knowledge-service/migrations/20260413_002_summaries.sql (NEW)
    Description:
      Create knowledge_summaries per KSA §3.3. UNIQUE(user_id, scope_type, scope_id).
    Acceptance criteria:
      - Migration applies cleanly
      - Unique constraint enforced
    Test:
      - Integration: test inserts, verify uniqueness violation on duplicate
    Dependencies: K1.2
    Est: S
    Notes:
      No extraction_pending or extraction_jobs in Track 1 migrations — those
      come in K10/Track 2.
```

```
[ ] K1.4 Migration in chat-service: add chat_sessions.project_id
    Files:
      - services/chat-service/app/migrations/NNN_session_project_id.py (NEW)
    Description:
      ALTER TABLE chat_sessions ADD COLUMN project_id UUID. NO foreign key
      constraint (cross-service reference — enforced in application code).
      Add index on (project_id) WHERE project_id IS NOT NULL.
    Acceptance criteria:
      - Migration applies to loreweave_chat
      - Existing sessions have NULL project_id
      - New sessions can set project_id via API (K7.x later)
    Test:
      - Integration: tests/integration/test_session_project_migration.py
    Dependencies: none (runs in chat-service repo)
    Est: S
    Notes:
      **Cross-service change.** This migration is owned by chat-service.
      Update chat-service's session model, repository, and API to handle
      the new field. Reference: KSA §3.3.
      **IMPORTANT:** No FK constraint means chat-service cannot validate
      project existence. knowledge-service validates it when receiving
      context build requests.
```

```
[ ] K1.5 Repository layer: projects
    Files:
      - services/knowledge-service/app/db/repositories/__init__.py (NEW)
      - services/knowledge-service/app/db/repositories/projects.py (NEW)
      - services/knowledge-service/app/db/models.py (NEW)
    Description:
      Pydantic models + asyncpg queries for:
        - create_project(user_id, name, description, project_type, book_id=None, instructions="")
        - list_projects(user_id, include_archived=False)
        - get_project(project_id, user_id)  # user_id filter for security
        - update_project(project_id, user_id, **updates)
        - archive_project(project_id, user_id)
        - delete_project(project_id, user_id)
    Acceptance criteria:
      - All queries parameterized ($1, $2) — no string interpolation
      - user_id is ALWAYS included in WHERE clause
      - Returns Pydantic models, not raw rows
    Test:
      - Integration: tests/integration/test_projects_repo.py (CRUD scenarios)
    Dependencies: K1.2
    Est: M
    Notes:
      Security: this is the security-critical layer. Every query MUST filter
      by user_id. Reviewers (even if that's future-you) must reject any
      query that doesn't.
```

```
[ ] K1.6 Repository layer: summaries
    Files:
      - services/knowledge-service/app/db/repositories/summaries.py (NEW)
    Description:
      Pydantic models + queries for:
        - get_summary(user_id, scope_type, scope_id=None)
        - upsert_summary(user_id, scope_type, scope_id, content)
        - delete_summary(user_id, scope_type, scope_id)
    Acceptance criteria:
      - Upsert uses ON CONFLICT DO UPDATE
      - Content update increments version automatically
      - token_count computed on write (len(content)//4 heuristic)
    Test:
      - Integration: tests/integration/test_summaries_repo.py
    Dependencies: K1.3
    Est: M
    Notes:
      Track 1 only supports manual summary edits. Auto-regeneration is
      Track 3 (K20).
```

### Gate 2 — Schema & Repository

- [ ] Fresh DB migrations run without errors (`./scripts/reset-db.sh && docker compose up`)
- [ ] Unit tests for repositories pass (`pytest tests/integration/test_projects_repo.py`)
- [ ] Can create, list, update, delete projects via Python repl
- [ ] chat-service migration applied, existing tests still pass in chat-service
- [ ] No cross-tenant data leak: create 2 users, verify user A can't access user B's projects at repository level

If any fail, fix before K2.

---

## 6. Phase K2 — Glossary Schema Additions

**Goal:** Add `short_description`, `is_pinned_for_context`, and `search_vector`
columns to `glossary_entities` in the glossary-service database. Update
glossary-service (Go) to handle the new fields.

### Tasks

```
[ ] K2.1 Migration: glossary_entities schema additions
    Files:
      - services/glossary-service/internal/migrate/migrations/NNN_glossary_memory.sql (NEW)
    Description:
      Add columns:
        - short_description TEXT DEFAULT NULL
        - is_pinned_for_context BOOLEAN DEFAULT false
        - search_vector tsvector GENERATED ALWAYS AS (...) STORED
      Create GIN index on search_vector. Reference: KSA §3.3.
    Acceptance criteria:
      - Migration applies cleanly to existing glossary DB
      - Existing rows have NULL short_description, false is_pinned, computed search_vector
      - GIN index exists
    Test:
      - Integration: Go test for glossary-service migration
    Dependencies: K1.2 (can run in parallel with K1)
    Est: S
    Notes:
      Generated column is populated automatically from name + aliases +
      short_description + description. Uses 'simple' text config for
      maximum language coverage (works for CJK too via tokenization).
```

```
[ ] K2.2 Update glossary-service Go models and queries
    Files:
      - services/glossary-service/internal/models/entity.go (MODIFY)
      - services/glossary-service/internal/repo/entities.go (MODIFY)
    Description:
      Add new fields to GlossaryEntity struct, update SELECT/INSERT/UPDATE
      queries. Default short_description to nil in inserts (backfilled by K3).
    Acceptance criteria:
      - Existing glossary-service tests still pass
      - GET /v1/glossary/entities/{id} includes new fields in response
      - PATCH /v1/glossary/entities/{id} accepts short_description update
    Test:
      - Integration: existing glossary-service tests + new assertion on new fields
    Dependencies: K2.1
    Est: M
    Notes:
      Don't break existing API shape. New fields are additive.
```

```
[ ] K2.3 API: pin/unpin endpoints
    Files:
      - services/glossary-service/internal/api/entities.go (MODIFY)
    Description:
      - POST /v1/glossary/entities/{id}/pin → sets is_pinned_for_context = true
      - DELETE /v1/glossary/entities/{id}/pin → sets is_pinned_for_context = false
      Both require auth (user must own the entity via book ownership).
    Acceptance criteria:
      - Pin works, unpin works, both idempotent
      - Cross-user access returns 403
    Test:
      - Integration: curl test + cross-user isolation check
    Dependencies: K2.2
    Est: S
    Notes:
      No hard cap on pinned count at the DB level — just the UI cap of 10
      (KSA §4.2.5). Users can technically pin more via API but the
      glossary fallback selector only picks the top max_pinned.
```

```
[ ] K2.4 API: FTS search endpoint (internal)
    Files:
      - services/glossary-service/internal/api/entities.go (MODIFY)
    Description:
      POST /internal/glossary/select-for-context
      Body: {user_id, book_id, query, max_entities, max_tokens, exclude_ids}
      Returns: sorted list of GlossaryEntityForContext structs (with
      short_description, name, kind, is_pinned, rank_score).

      Implements the tiered selection from KSA §4.2.5:
        Tier 0: pinned (max 10)
        Tier 1: name/alias exact match
        Tier 2: tsvector FTS with ts_rank
        Tier 3 fallback: top-mentioned entities (future; Track 1 returns empty)
        Tier 4 fallback: most-recently-edited
    Acceptance criteria:
      - All tiers work
      - Returns empty list if book has no glossary entries
      - Respects exclude_ids (dedupe across tiers)
    Test:
      - Integration: Go table-driven test with fixture glossary data
    Dependencies: K2.2
    Est: L
    Notes:
      **Critical path.** Reviewer check: every query includes
      `WHERE owner_user_id = $1 AND book_id = $2` to prevent cross-tenant
      leaks. Use parameterized queries.
```

```
[ ] K2.5 Internal token auth for new endpoint
    Files:
      - services/glossary-service/internal/api/middleware.go (MODIFY)
    Description:
      /internal/glossary/* routes require X-Internal-Token header.
      knowledge-service calls this endpoint with the shared secret.
    Acceptance criteria:
      - Without token: 401
      - With wrong token: 401
      - With correct token: 200
    Test:
      - Integration: curl tests
    Dependencies: K2.4
    Est: S
    Notes:
      Same pattern as K0.6 but in Go.
```

---

## 7. Phase K3 — Short Description Auto-Generator

**Goal:** Ensure every glossary entity has a useful `short_description` for
compact chat context injection, without requiring users to write one manually.

### Tasks

```
[ ] K3.1 Template-based short description generator
    Files:
      - services/glossary-service/internal/shortdesc/generator.go (NEW)
    Description:
      Pure function: given a GlossaryEntity, produce a ~150-char summary.
      Strategy:
        1. If short_description already set → return it
        2. If description is empty → return "{kind}: {name}" (e.g., "character: Kai")
        3. If description has a first sentence <= 150 chars → use it
        4. Otherwise: truncate at last word boundary before 150 chars + "..."
    Acceptance criteria:
      - Always returns a non-empty string for non-empty input
      - Output is <= 150 characters
      - Output ends on a word boundary when truncated
      - Handles CJK (counts characters, not bytes)
    Test:
      - Unit: 10+ cases including short, long, multilingual, empty
    Dependencies: K2.2
    Est: S
    Notes:
      No LLM. No network calls. Pure function, easy to test.
```

```
[ ] K3.2 Backfill job on service startup
    Files:
      - services/glossary-service/internal/backfill/shortdesc.go (NEW)
      - services/glossary-service/cmd/glossary-service/main.go (MODIFY — call backfill once)
    Description:
      On service startup, run a SELECT of entities with NULL short_description
      (batch 100 at a time), generate via K3.1, UPDATE.
      Idempotent: re-running skips already-backfilled entities.
    Acceptance criteria:
      - First run processes all existing entities
      - Subsequent runs are no-ops
      - Doesn't block service startup for more than 10s (run in background goroutine if slow)
    Test:
      - Integration: create 100 entities with NULL short_description,
        verify all have non-NULL after startup
    Dependencies: K3.1
    Est: M
    Notes:
      Background goroutine — service becomes healthy immediately, backfill
      runs in parallel. Log progress every 100 entities.
```

```
[ ] K3.3 Event listener: auto-update on entity updates
    Files:
      - services/glossary-service/internal/repo/entities.go (MODIFY)
    Description:
      When an entity's description is updated AND short_description was
      auto-generated (not user-edited), regenerate short_description via K3.1.
    Acceptance criteria:
      - Editing description regenerates short_description
      - User-edited short_description (via PATCH) is preserved (never regenerated)
    Test:
      - Integration: PATCH description, verify short_description updates;
        PATCH short_description directly, verify it persists
    Dependencies: K3.1, K2.2
    Est: S
    Notes:
      Need a flag `short_description_auto` to distinguish manual vs generated.
      Add this column in K2.1 migration (oversight — add if missing).
```

### Mini-Gate (no full gate needed — small phase)

- [ ] All existing glossary entities have non-NULL short_description after service restart
- [ ] Editing a description regenerates short_description
- [ ] K3.1 unit tests pass for edge cases (CJK, empty, very long)

---

## 8. Phase K4 — Context Builder (Modes 1 & 2)

**Goal:** The core of the service. Given a user message and session,
produce an XML memory block for chat-service to inject into the system prompt.

**This is the most complex phase.** Allocate the most time here.

### Tasks

```
[ ] K4.1 XML escape utility (MANDATORY helper — used everywhere)
    Files:
      - services/knowledge-service/app/context/formatters/xml_escape.py (NEW)
    Description:
      Implement sanitize_for_xml() and xml_escape() per KSA §4.4.3b.
      Handle control characters, entity escaping, CJK safely.
    Acceptance criteria:
      - html.escape applied with quote=True
      - Control chars (\x00-\x1F except \t, \n, \r) stripped
      - All edge cases from KSA §4.4.3b test table pass
    Test:
      - Unit: tests/unit/test_xml_escape.py
        Cases: `<`, `>`, `&`, `"`, control chars, CJK, `]]>`, empty, None
    Dependencies: K0.1
    Est: S
    Notes:
      **USE THIS EVERYWHERE.** Any XML construction elsewhere must go
      through these functions. No exceptions. Mark module with __all__
      to enforce import discipline.
```

```
[ ] K4.2 Token counter
    Files:
      - services/knowledge-service/app/context/formatters/token_counter.py (NEW)
    Description:
      Simple function: estimate_tokens(text) -> int
      Use the `len(text) // 4` heuristic for Track 1 — no need for tiktoken
      (which would be a heavy dependency for unclear benefit).
      If tiktoken is available, use it for better accuracy.
    Acceptance criteria:
      - Returns int for any string input
      - Empty string → 0
      - Handles None → 0 without exception
    Test:
      - Unit: basic cases
    Dependencies: K0.1
    Est: S
    Notes:
      In Track 2, we'll switch to accurate counting. For now, 4:1 ratio
      is good enough for budget enforcement.
```

```
[ ] K4.3 Entity candidate extractor (pattern-based)
    Files:
      - services/knowledge-service/app/context/selectors/entity_candidates.py (NEW)
    Description:
      Given a user message, extract capitalized proper nouns and quoted names
      that might be glossary entities. NO LLM. Pure regex/string work.
      Also returns the raw tokens for FTS fallback.
    Acceptance criteria:
      - "Tell me about Kai" → ["Kai"]
      - "What does Master Lin think?" → ["Master Lin", "Lin"]
      - "The princess is dead" → [] (no capitalized word)
      - Handles empty input
      - Handles CJK: "告诉我关于凯的事" → ["凯"] (single-char CJK names work)
    Test:
      - Unit: 15+ cases covering English, CJK, quoted names, edge cases
    Dependencies: K0.1
    Est: M
    Notes:
      This is the simplest entity detection — Track 2 will add LLM-based
      extraction. For Track 1 glossary FTS, this is plenty.
```

```
[ ] K4.4 Glossary client (HTTP call to glossary-service)
    Files:
      - services/knowledge-service/app/clients/glossary_client.py (NEW)
    Description:
      httpx.AsyncClient wrapper that calls POST /internal/glossary/select-for-context
      with the user_id/book_id/query/limits. Timeout: 200ms. Retries: 1.
      Returns list of GlossaryEntityForContext Pydantic models.
    Acceptance criteria:
      - Handles timeout → returns empty list (don't raise)
      - Handles 404/500 → returns empty list + logs warning
      - Handles connection error → returns empty list + logs warning
      - Returns parsed Pydantic models on success
    Test:
      - Integration: mock glossary-service with respx, verify each path
    Dependencies: K2.4
    Est: M
    Notes:
      Graceful degradation is mandatory. If glossary-service is down,
      chat should still work (just with less context).
```

```
[ ] K4.5 L0 loader (plain text, Postgres read)
    Files:
      - services/knowledge-service/app/context/selectors/summaries.py (NEW)
    Description:
      load_global_summary(user_id) → SummaryContent | None
      Reads knowledge_summaries WHERE user_id AND scope_type='global'.
      Returns None if not set.
    Acceptance criteria:
      - Returns None for users who haven't set a bio
      - Returns content for users who have
      - Query uses parameterized $1
    Test:
      - Integration: insert, read, verify
    Dependencies: K1.6
    Est: S
    Notes:
      This is load_l0 in KSA §4.0.
```

```
[ ] K4.6 L1 loader (project context, plain text)
    Files:
      - services/knowledge-service/app/context/selectors/summaries.py (MODIFY — add load_project_summary)
    Description:
      load_project_summary(user_id, project_id) → tuple[Project, Summary | None]
      Reads knowledge_projects for instructions + style examples,
      AND knowledge_summaries (scope=project) for auto-generated summary.
      Returns both so the formatter can combine them.
    Acceptance criteria:
      - Returns project even if no summary exists
      - Returns None project if project doesn't exist or user doesn't own it
      - User_id filter enforced
    Test:
      - Integration: cross-user access returns None
    Dependencies: K1.5, K1.6
    Est: S
    Notes:
      Combine instructions (required) + summary (optional) at the formatter level.
```

```
[ ] K4.7 Mode 1 builder (no project)
    Files:
      - services/knowledge-service/app/context/modes/no_project.py (NEW)
    Description:
      Builds a memory block containing only L0 (global identity).
      Returns ContextResponse with mode="no_project", recent_message_count=50.

      XML structure:
        <memory mode="no_project">
          <user>...</user>
          <instructions>...</instructions>
        </memory>
    Acceptance criteria:
      - User with no global summary → empty memory block, mode="no_project"
      - User with global summary → formatted block including it
      - All user content XML-escaped via K4.1
      - Token count respected (L0 should never exceed ~200 tokens)
    Test:
      - Unit: mock repository, call builder, assert output structure
    Dependencies: K4.1, K4.5
    Est: M
    Notes:
      Simplest mode. Good first build target — use it to shake out the
      formatter plumbing before tackling Mode 2.
```

```
[ ] K4.8 Glossary fallback selector (Level 1: FTS only)
    Files:
      - services/knowledge-service/app/context/selectors/glossary.py (NEW)
    Description:
      Calls K4.4 glossary_client with:
        - book_id from the project (if linked)
        - query text from user message
        - max_entities=20, max_tokens=800
      Returns structured list. Handles case where project has no book.
    Acceptance criteria:
      - Project with no book_id → returns empty list
      - Project with book_id → calls glossary-service, returns results
      - glossary-service down → returns empty list (graceful)
    Test:
      - Integration with mock glossary-service
    Dependencies: K4.4, K4.6
    Est: M
    Notes:
      The glossary_client handles all error paths. This function just
      orchestrates.
```

```
[ ] K4.9 Mode 2 builder (static)
    Files:
      - services/knowledge-service/app/context/modes/static.py (NEW)
    Description:
      Builds memory block for project with extraction_enabled=false.
      Contents:
        - L0 via K4.5
        - L1 via K4.6 (instructions + summary + style_examples)
        - glossary via K4.8
        - instructions block telling LLM this is static mode

      XML structure per KSA §4.4.2b Mode 2 example.
    Acceptance criteria:
      - Empty glossary → block still renders, just without <glossary>
      - Missing L0 → block still renders without <user>
      - Missing L1 summary → shows instructions only
      - Token count within budget (<~1500 tokens memory portion)
    Test:
      - Unit with mock repositories; cover each missing-piece scenario
    Dependencies: K4.5, K4.6, K4.8, K4.1
    Est: L
    Notes:
      **Most important build target.** Spend the time here; most users
      will see Mode 2 output.
```

```
[ ] K4.10 Mode dispatcher
    Files:
      - services/knowledge-service/app/context/builder.py (NEW)
    Description:
      Top-level function build_context(request) that:
        1. If project_id is None → Mode 1 (K4.7)
        2. Else fetches project; if extraction_enabled=false → Mode 2 (K4.9)
        3. Else → raises NotImplementedError (Mode 3 is Track 2)
    Acceptance criteria:
      - Dispatches correctly based on project state
      - Mode 3 path raises clear error (NotImplementedError with message)
      - Returns ContextResponse with mode, context, recent_message_count
    Test:
      - Unit: each dispatch path
    Dependencies: K4.7, K4.9
    Est: S
    Notes:
      This is the public API entry. Keep it small — logic lives in
      the mode builders.
```

```
[ ] K4.11 Internal endpoint: POST /internal/context/build
    Files:
      - services/knowledge-service/app/api/internal/context.py (NEW)
    Description:
      FastAPI route that:
        1. Validates internal token
        2. Parses request (Pydantic model with user_id, project_id, session_id, message)
        3. Calls K4.10 builder
        4. Returns ContextResponse as JSON
    Acceptance criteria:
      - Returns 200 + JSON on success
      - Returns 401 on missing/wrong token
      - Returns 400 on malformed request
      - Returns 500 on internal error (with error logged, no stack trace in response)
    Test:
      - Integration: end-to-end HTTP test with real DB
    Dependencies: K4.10, K0.6
    Est: M
    Notes:
      Add OpenAPI tag "Internal" so docs clearly separate from public API.
```

```
[ ] K4.12 Cross-layer deduplication (L1 vs glossary)
    Files:
      - services/knowledge-service/app/context/formatters/dedup.py (NEW)
    Description:
      If L1 summary mentions an entity that's also in the glossary selection,
      drop the glossary entry (L1 takes precedence). Uses keyword overlap,
      not semantic similarity. Reference: KSA §4.4.3.
    Acceptance criteria:
      - Glossary entry "Kai: 17yo fire elemental" AND L1 says "protagonist Kai (fire elemental)"
        → glossary entry dropped
      - Keywords >3 chars, case-insensitive match
      - Metric incremented on each dedup
    Test:
      - Unit with specific L1 text + glossary list
    Dependencies: K4.9
    Est: S
    Notes:
      Small optimization. Skip if time is tight — can add after Gate 3.
```

### Gate 3 — Context Builder Works Standalone

**STOP.** Don't touch chat-service until this gate passes.

- [ ] `curl -X POST /internal/context/build` with a real user returns correct mode
- [ ] Mode 1 (no project) returns block with just L0
- [ ] Mode 2 (static) returns block with L0 + L1 + glossary (when applicable)
- [ ] Missing global summary handled (no error, just no `<user>` element)
- [ ] Missing project handled (returns 400 with clear error)
- [ ] Cross-user test: user A requesting build_context for user B's project → 403 or 404
- [ ] XML is valid (parse it with an XML library in the test)
- [ ] Token count within budget for a realistic input
- [ ] glossary-service down → fallback returns context without glossary, doesn't crash
- [ ] Latency: single call < 300ms (with warm DB pools) under normal conditions

If any fail, fix before K5.

---

## 9. Phase K5 — chat-service Integration

**Goal:** chat-service calls knowledge-service before every LLM request,
injects the returned memory block into the system prompt, and gracefully
degrades if knowledge-service is unavailable.

### Tasks

```
[ ] K5.1 HTTP client in chat-service
    Files:
      - services/chat-service/app/clients/knowledge_client.py (NEW)
    Description:
      httpx.AsyncClient wrapper for calling knowledge-service /internal/context/build.
      Timeout: 500ms total. Includes X-Internal-Token from config.
    Acceptance criteria:
      - Sends X-Internal-Token correctly
      - Timeout enforced
      - Exceptions wrapped in a domain-specific KnowledgeServiceError
    Test:
      - Unit with respx mock
    Dependencies: K4.11
    Est: S
    Notes:
      Match pattern of existing chat-service provider clients for consistency.
```

```
[ ] K5.2 Config: knowledge-service URL + shared secret
    Files:
      - services/chat-service/app/config.py (MODIFY)
    Description:
      Add KNOWLEDGE_SERVICE_URL and INTERNAL_SERVICE_TOKEN env vars.
    Acceptance criteria:
      - Missing vars → clear error at startup
      - Values visible in /health (truncated secret)
    Test:
      - Unit: test_config
    Dependencies: K5.1
    Est: S
```

```
[ ] K5.3 Call build_context in stream_service.py
    Files:
      - services/chat-service/app/services/stream_service.py (MODIFY)
    Description:
      Before the LLM call:
        1. Build the knowledge context request with user_id, project_id (from session),
           session_id, and the user's current message
        2. Call knowledge_client.build_context
        3. Prepend returned context to system prompt
        4. Use returned recent_message_count to trim history (50 or 20)
    Acceptance criteria:
      - Context is actually injected (visible in logs at DEBUG level)
      - System prompt order: memory block → user's session system prompt → user message
      - recent_message_count respected (loads exactly that many history messages)
    Test:
      - Integration: full chat turn with stubbed knowledge-service, verify prompt construction
    Dependencies: K5.1, K5.2
    Est: M
    Notes:
      Be careful with prompt ordering. Memory must come BEFORE the session
      system prompt so it doesn't get squashed by session-specific instructions.
```

```
[ ] K5.4 Graceful degradation (K6 earlier or here)
    Files:
      - services/chat-service/app/services/stream_service.py (MODIFY)
    Description:
      Wrap the knowledge-service call in try/except. On failure:
        - Log the exception with trace_id
        - Proceed without memory block (system prompt = session prompt only)
        - Use default recent_message_count = 50
        - Emit metric `knowledge_fallback_used` with reason label
    Acceptance criteria:
      - Stop knowledge-service container → chat still works
      - Response is correct (just without memory)
      - Metric recorded
    Test:
      - Chaos scenario: docker compose stop knowledge-service, verify chat works
    Dependencies: K5.3
    Est: S
    Notes:
      Non-negotiable. Chat never blocks on memory.
```

```
[ ] K5.5 Pass project_id through chat session create/update API
    Files:
      - services/chat-service/app/api/sessions.py (MODIFY)
      - contracts/api/chat-service.openapi.yaml (MODIFY)
    Description:
      Accept optional project_id in POST /v1/chat/sessions body and
      PATCH /v1/chat/sessions/{id} body. Validate it's a UUID (no FK check
      — trust knowledge-service to reject invalid IDs at build time).
    Acceptance criteria:
      - Can create session with project_id
      - Can update session to add/remove project_id
      - Invalid UUID → 400
      - Valid UUID → accepted (even if project doesn't exist; loose coupling)
    Test:
      - Integration: Python test covering create, update, get
    Dependencies: K1.4
    Est: S
    Notes:
      Loose coupling means chat-service doesn't know about projects. It
      just stores the UUID. knowledge-service validates existence on context build.
```

---

## 10. Phase K6 — Graceful Degradation (Timeouts + Cache + Circuit Breaker)

**Goal:** Make knowledge-service robust under failure and fast for hot reads.

### Tasks

```
[ ] K6.1 Layer-level timeouts inside context builder
    Files:
      - services/knowledge-service/app/context/builder.py (MODIFY)
    Description:
      Each layer (L0, L1, glossary) wrapped in asyncio.wait_for with:
        - L0: 100ms
        - L1: 100ms
        - glossary: 200ms
      Total ceiling: 400ms. If budget exhausted, skip remaining layers.
      Metrics: `knowledge_layer_timeout{layer}` counter.
    Acceptance criteria:
      - Artificially slow Postgres → partial context returned, no error
      - Metrics incremented on timeout
      - Total build time <= 400ms even under slow deps
    Test:
      - Unit: mock selectors to sleep > timeout, verify graceful skip
    Dependencies: K4.10
    Est: M
```

```
[ ] K6.2 TTL cache for L0 and L1
    Files:
      - services/knowledge-service/app/context/cache.py (NEW)
    Description:
      In-process TTLCache (from cachetools) keyed by (user_id) for L0 and
      (user_id, project_id) for L1. TTL: 60 seconds. Max size: 10,000 entries.
    Acceptance criteria:
      - First call hits DB
      - Second call within 60s uses cache
      - Cache metric `knowledge_cache_hit` incremented on hit
      - Cache size bounded (LRU eviction above max_size)
    Test:
      - Unit: populate cache, verify hit, wait > TTL, verify miss
    Dependencies: K4.5, K4.6
    Est: M
    Notes:
      This cache is per-process. Multiple knowledge-service instances
      (if scaled out) each have their own. Cache staleness is acceptable
      at 60s — users editing their bio won't notice a 1-minute delay.
```

```
[ ] K6.3 Cache invalidation on writes
    Files:
      - services/knowledge-service/app/db/repositories/summaries.py (MODIFY)
      - services/knowledge-service/app/db/repositories/projects.py (MODIFY)
    Description:
      When a summary or project is updated, invalidate the matching cache
      key immediately (same process only — eventual consistency across
      processes). Reference: KSA §7.3 cache invalidation.
    Acceptance criteria:
      - Update global bio → next build_context call sees new bio
      - Update project instructions → same
      - Uncached keys → no-op, no error
    Test:
      - Unit: update → verify cache miss on next lookup
    Dependencies: K6.2
    Est: S
    Notes:
      Cross-process invalidation is a Track 2 concern (Redis pub/sub or
      event bus). For Track 1, 60s staleness is fine.
```

```
[ ] K6.4 Circuit breaker for glossary-service calls
    Files:
      - services/knowledge-service/app/clients/glossary_client.py (MODIFY)
    Description:
      Use `purgatory` library. Open circuit after 3 consecutive failures,
      stay open for 60s, then try one probe. On open circuit, glossary
      selection returns [] immediately without HTTP call.
    Acceptance criteria:
      - 3 failures → circuit opens
      - Open circuit → immediate empty return (no HTTP call)
      - After 60s → probe attempt
      - Probe success → circuit closes
    Test:
      - Unit: simulate failures, verify state transitions
    Dependencies: K4.4
    Est: M
```

```
[ ] K6.5 Metrics endpoint (Prometheus format)
    Files:
      - services/knowledge-service/app/api/metrics.py (NEW)
    Description:
      GET /metrics exposes Prometheus-format metrics via prometheus-client library.
      Include all metrics from KSA §9.6 that apply to Track 1:
        - knowledge_layer_timeout (counter, labels: layer)
        - knowledge_cache_hit (counter, labels: layer)
        - knowledge_circuit_open (gauge, labels: service)
        - knowledge_context_build_duration_seconds (histogram, labels: mode)
        - knowledge_api_request_duration_seconds (histogram, labels: endpoint, status)
    Acceptance criteria:
      - /metrics returns Prometheus format
      - All Track 1 metrics present
      - No auth required (internal port only, not exposed via gateway)
    Test:
      - Integration: curl /metrics, verify format
    Dependencies: K6.1, K6.2, K6.4
    Est: M
    Notes:
      Most metrics populate in later tasks. This just sets up the endpoint
      and registry.
```

---

## 11. Phase K7 — Public API (CRUD + Export/Delete)

**Goal:** Expose REST endpoints for managing projects, summaries, and user data.

### Tasks

```
[ ] K7.1 JWT auth middleware
    Files:
      - services/knowledge-service/app/api/middleware/jwt_auth.py (NEW)
    Description:
      Parse JWT from Authorization: Bearer header. Extract user_id (sub claim).
      Use same JWT secret as auth-service (shared from env).
      All /v1/knowledge/* routes use this dependency.
    Acceptance criteria:
      - Missing header → 401
      - Invalid signature → 401
      - Expired token → 401
      - Valid token → user_id available in request context
      - user_id NEVER accepted from query/body
    Test:
      - Integration: test each failure mode
    Dependencies: K0.3
    Est: M
    Notes:
      **Security-critical.** Never accept user_id from the client as a
      parameter — always derive from JWT. This is the fundamental cross-user
      isolation boundary.
```

```
[ ] K7.2 Projects CRUD endpoints
    Files:
      - services/knowledge-service/app/api/public/projects.py (NEW)
    Description:
      - GET /v1/knowledge/projects
      - POST /v1/knowledge/projects
      - GET /v1/knowledge/projects/{id}
      - PATCH /v1/knowledge/projects/{id}
      - DELETE /v1/knowledge/projects/{id}
      - POST /v1/knowledge/projects/{id}/archive
    Acceptance criteria:
      - All endpoints require JWT
      - All queries filter by user_id from JWT
      - Cross-user access returns 404 (not 403 — don't leak existence)
      - PATCH is partial update (only provided fields)
      - DELETE cascade deletes related summaries
    Test:
      - Integration: full CRUD test + cross-user isolation
    Dependencies: K1.5, K7.1
    Est: L
    Notes:
      Return 404 (not 403) for cross-user access to avoid leaking "this ID exists."
```

```
[ ] K7.3 Summary endpoints
    Files:
      - services/knowledge-service/app/api/public/summaries.py (NEW)
    Description:
      - GET /v1/knowledge/summaries (list user's summaries by scope)
      - PATCH /v1/knowledge/summaries/global (update global L0)
      - PATCH /v1/knowledge/projects/{id}/summary (update project L1)
      Body: {content: string}
    Acceptance criteria:
      - Returns user's own summaries
      - Updates are user_id-scoped
      - Content can be empty string (delete without deleting the row)
    Test:
      - Integration
    Dependencies: K1.6, K7.1
    Est: M
```

```
[ ] K7.4 Glossary pin passthrough endpoints
    Files:
      - services/knowledge-service/app/api/public/glossary.py (NEW)
    Description:
      Thin wrappers that call glossary-service:
        - POST /v1/knowledge/glossary-entities/{id}/pin
        - DELETE /v1/knowledge/glossary-entities/{id}/pin
    Acceptance criteria:
      - Delegates to glossary-service internal API
      - JWT is forwarded or re-validated
    Test:
      - Integration with real glossary-service
    Dependencies: K2.3, K7.1
    Est: S
    Notes:
      Alternative: just expose these directly on glossary-service as public
      endpoints. The wrapper is only useful if you want a unified
      /v1/knowledge/* namespace for the frontend. Decide based on taste.
```

```
[ ] K7.5 User data export
    Files:
      - services/knowledge-service/app/api/public/user_data.py (NEW)
    Description:
      GET /v1/knowledge/user-data/export
      Returns JSON bundle: all projects, summaries for the authenticated user.
      Streams response to handle large datasets.
    Acceptance criteria:
      - Returns only the authenticated user's data
      - JSON is well-formed
      - Content-Disposition header suggests filename
    Test:
      - Integration: export + parse + verify structure
    Dependencies: K1.5, K1.6, K7.1
    Est: M
    Notes:
      Track 1 only exports knowledge-service-owned data. Full cross-service
      export (chapters, chat, glossary) is Track 3.
```

```
[ ] K7.6 User data delete (GDPR erasure)
    Files:
      - services/knowledge-service/app/api/public/user_data.py (MODIFY)
    Description:
      DELETE /v1/knowledge/user-data
      Deletes all of the authenticated user's projects and summaries.
      CASCADE handles related tables.
    Acceptance criteria:
      - All user's data deleted
      - Other users' data untouched (verified in T18 test)
      - Returns 200 with counts of deleted rows
    Test:
      - Integration: T18 cross-user isolation + deletion verify
    Dependencies: K1.5, K1.6, K7.1
    Est: S
    Notes:
      Just Track 1 scope. Full GDPR cascade across services is Track 3.
```

```
[ ] K7.7 Gateway proxy routes for /v1/knowledge/*
    Files:
      - services/api-gateway-bff/src/gateway-setup.ts (MODIFY)
    Description:
      Proxy ALL /v1/knowledge/* to knowledge-service. Forward Authorization header.
    Acceptance criteria:
      - All K7.2-K7.6 endpoints accessible via gateway
      - /internal/* NOT exposed via gateway
    Test:
      - Integration: curl through gateway
    Dependencies: K7.2-K7.6, K0.9
    Est: S
    Notes:
      Remove the temporary /v1/knowledge/ping route from K0.9.
```

### Gate 4 — End-to-End API Works

**STOP.** Verify a complete user journey via API.

- [ ] Create a user via auth-service
- [ ] POST /v1/knowledge/projects → create project, get ID
- [ ] PATCH /v1/knowledge/projects/{id} → set instructions
- [ ] PATCH /v1/knowledge/summaries/global → set global bio
- [ ] Create chat session with project_id via chat-service API
- [ ] Send a chat message → response uses memory (check logs for knowledge-service call)
- [ ] Verify prompt contains user bio and project instructions
- [ ] Create second user, try to access first user's project → 404
- [ ] Delete first user's data → second user still has access to their own data
- [ ] Stop knowledge-service → send chat message → chat still works (no memory)
- [ ] Restart knowledge-service → chat uses memory again

If any fail, fix before K8.

---

## 12. Phase K8 — Frontend Projects UI

**Goal:** User-facing UI for managing projects and the global bio.

### Tasks

```
[ ] K8.1 Feature folder structure
    Files:
      - frontend/src/features/knowledge/ (NEW)
      - frontend/src/features/knowledge/api.ts (NEW)
      - frontend/src/features/knowledge/types.ts (NEW)
      - frontend/src/features/knowledge/hooks/ (NEW)
      - frontend/src/features/knowledge/components/ (NEW)
      - frontend/src/features/knowledge/pages/ (NEW)
    Description:
      Match existing feature folder conventions (features/chat, features/books).
      Export via index.ts files.
    Acceptance criteria:
      - Folder structure matches KSA §8.10 spec
      - TypeScript compiles with `npm run build`
    Test:
      - Build passes
    Dependencies: none
    Est: S
```

```
[ ] K8.2 API client
    Files:
      - frontend/src/features/knowledge/api.ts
    Description:
      Fetch wrapper functions for all K7 endpoints:
        - listProjects, createProject, getProject, patchProject, deleteProject, archiveProject
        - getSummary, patchGlobalSummary, patchProjectSummary
        - pinGlossaryEntity, unpinGlossaryEntity
        - exportUserData, deleteUserData
    Acceptance criteria:
      - All methods typed via types.ts
      - Uses shared http client (with auth token)
      - Errors surfaced with message + status
    Test:
      - Type check only (no integration yet)
    Dependencies: K7
    Est: M
    Notes:
      Match the patterns in features/chat/api.ts.
```

```
[ ] K8.3 React Query hooks
    Files:
      - frontend/src/features/knowledge/hooks/useProjects.ts (NEW)
      - frontend/src/features/knowledge/hooks/useProjectMutations.ts (NEW)
      - frontend/src/features/knowledge/hooks/useGlobalBio.ts (NEW)
    Description:
      useQuery / useMutation wrappers with sensible cache keys and
      invalidation on mutations.
    Acceptance criteria:
      - Query keys stable
      - Invalidation after mutations updates the list automatically
      - Loading/error states exposed
    Test:
      - Manual in UI
    Dependencies: K8.2
    Est: M
```

```
[ ] K8.4 Projects list page
    Files:
      - frontend/src/features/knowledge/pages/ProjectsPage.tsx (NEW)
      - frontend/src/features/knowledge/components/ProjectCard.tsx (NEW)
      - frontend/src/features/knowledge/components/CreateProjectDialog.tsx (NEW)
    Description:
      List page showing user's projects as cards. Each card shows:
        - Name, type badge, book link (if any)
        - "Static memory" badge (Track 1 all projects are in this state)
        - Edit button, Archive button, Delete button
      "+ New Project" button opens CreateProjectDialog.
    Acceptance criteria:
      - Loads projects, shows empty state if none
      - Create dialog validates name
      - Actions work
    Test:
      - Manual smoke test
    Dependencies: K8.3
    Est: L
```

```
[ ] K8.5 Project detail / edit panel
    Files:
      - frontend/src/features/knowledge/components/ProjectEditor.tsx (NEW)
    Description:
      Edit name, description, type, book link, instructions (textarea),
      style examples (repeatable text inputs).
      Save button calls patchProject.
    Acceptance criteria:
      - All fields editable
      - Validation on name (required)
      - Save shows loading, success toast, error toast
      - Dirty state detection (disable save if no changes)
    Test:
      - Manual
    Dependencies: K8.4
    Est: M
```

```
[ ] K8.6 Global bio editor (Settings → Memory → Global)
    Files:
      - frontend/src/features/knowledge/components/GlobalBioEditor.tsx (NEW)
      - frontend/src/features/settings/pages/PrivacySettingsPage.tsx (MODIFY — add Memory section)
    Description:
      Multi-line textarea for the global bio (L0). Character count with limit hint
      (~200 tokens ≈ 800 chars). Save button writes to knowledge-service.
    Acceptance criteria:
      - Loads current bio
      - Save works, updates cache
      - Character limit enforced
    Test:
      - Manual
    Dependencies: K8.3
    Est: M
```

```
[ ] K8.7 Settings → Privacy → Memory toggle
    Files:
      - frontend/src/features/settings/pages/PrivacySettingsPage.tsx (MODIFY)
    Description:
      Add a section with:
        - Description of what memory does (plain language)
        - "View my memory" button → links to projects page
        - "Delete all memory" button → confirm dialog → calls deleteUserData
      NO "enable/disable memory" toggle in Track 1 (memory is always on at
      the L0/L1/glossary level; extraction toggle is Track 2).
    Acceptance criteria:
      - Links work
      - Delete confirmation uses double-confirm (type the word "delete")
    Test:
      - Manual
    Dependencies: K8.6
    Est: M
```

```
[ ] K8.8 i18n strings
    Files:
      - frontend/public/locales/en/knowledge.json (NEW)
      - frontend/public/locales/vi/knowledge.json (NEW)
      - frontend/public/locales/ja/knowledge.json (NEW)
      - frontend/public/locales/zh-TW/knowledge.json (NEW)
    Description:
      Translate all knowledge UI strings into 4 languages.
    Acceptance criteria:
      - No hardcoded strings in K8.4-K8.7 components
      - All 4 languages have complete translations
    Test:
      - Manual switch via language picker
    Dependencies: K8.4-K8.7
    Est: M
    Notes:
      Use machine translation as a starting point for vi/ja/zh-TW, then
      manually review for novel-writing context terms.
```

---

## 13. Phase K9 — Chat Header Memory Indicator

**Goal:** Show the user which memory mode their current chat is in, and let
them assign the session to a project.

### Tasks

```
[ ] K9.1 Session project picker dropdown
    Files:
      - frontend/src/features/chat/components/SessionSettingsPanel.tsx (MODIFY)
    Description:
      Add a "Project" dropdown in the session settings panel. Options:
        - "No project"
        - List of user's active projects
      On change, PATCH the chat session with project_id.
    Acceptance criteria:
      - Loads user's projects
      - Selecting a project updates the session
      - Setting to "No project" sets project_id = null
    Test:
      - Manual
    Dependencies: K5.5, K8.3
    Est: M
```

```
[ ] K9.2 Memory state detection hook
    Files:
      - frontend/src/features/knowledge/hooks/useSessionMemoryState.ts (NEW)
    Description:
      Hook that given a session_id returns memory state:
        - "no_project" (project_id is null)
        - "static" (project exists, extraction_enabled=false — always in Track 1)
        - "full" (Track 2, not possible in Track 1)
      Fetches project if session has project_id.
    Acceptance criteria:
      - Returns correct state for each case
      - Cached via React Query
    Test:
      - Manual
    Dependencies: K8.3, K9.1
    Est: S
```

```
[ ] K9.3 Chat header indicator component
    Files:
      - frontend/src/features/knowledge/components/SessionMemoryIndicator.tsx (NEW)
      - frontend/src/features/chat/components/ChatHeader.tsx (MODIFY — add indicator)
    Description:
      Small icon + label in the chat header:
        - "📖 No memory" (gray)
        - "📖 Static memory" (yellow)
      Click opens a popover with plain-language explanation per KSA §8.7.
      Popover shows: current mode, what context includes, link to build
      knowledge graph (disabled in Track 1 with "Coming in Track 2" tooltip).
    Acceptance criteria:
      - Icon/label matches state
      - Popover shows correct plain-language explanation per mode
      - Link to /knowledge/projects works
    Test:
      - Manual
    Dependencies: K9.2
    Est: M
```

```
[ ] K9.4 i18n for chat indicator
    Files:
      - frontend/public/locales/*/knowledge.json (MODIFY)
    Description:
      Add strings for mode labels and popover content.
    Acceptance criteria:
      - All 4 languages updated
    Test:
      - Manual
    Dependencies: K9.3
    Est: S
```

### Gate 5 — Full UX Works

**STOP.** Verify the complete user journey via the browser.

- [ ] Open LoreWeave in browser, log in with test account
- [ ] Go to Settings → Memory → Global, edit bio, save, refresh, verify persisted
- [ ] Go to Knowledge page, create a new project
- [ ] Edit project: set instructions and style examples, save, refresh, verify persisted
- [ ] Open Chat, create a new session, assign it to the project via dropdown
- [ ] Send a message, verify response "knows" about the project (use a
      project-specific fact in instructions to test)
- [ ] Check chat header: shows "📖 Static memory"
- [ ] Click header icon, verify popover shows mode explanation
- [ ] Open another session without a project, verify it shows "📖 No memory"
- [ ] Stop knowledge-service → send message in project session → should still
      work (no memory), header indicator should fall back gracefully
- [ ] Restart knowledge-service → message uses memory again

If any fail, fix before declaring Track 1 done.

---

## 14. Integration Test Scenarios (from KSA §9.8)

The Track 1 subset. These must all pass before declaring Track 1 done.

```
T01: Create project, verify extraction_enabled = false
     Tools: pytest + asyncpg
     Steps:
       1. POST /v1/knowledge/projects → capture project_id
       2. SELECT * FROM knowledge_projects WHERE project_id=...
       3. Assert extraction_enabled = false, extraction_status = 'disabled'
     [ ] Pass

T02: Chat in project without extraction has Mode 2 context
     Tools: pytest + httpx
     Steps:
       1. Create project with instructions "Write in formal prose"
       2. Create chat session with project_id
       3. Send a chat message; intercept the LLM request
       4. Verify system prompt contains:
          - <memory mode="static">
          - <user> (if global bio set)
          - <project> with instructions
          - <glossary> if book linked
          - Does NOT contain <facts> or <related_passages>
     [ ] Pass

T03: Chat without a project has Mode 1 context
     Steps:
       1. Create chat session without project_id
       2. Send message
       3. Verify system prompt contains <memory mode="no_project">
          with only <user> element (or empty if no bio)
     [ ] Pass

T04: Cross-user isolation at API level
     Steps:
       1. User A creates project A
       2. User B tries GET /v1/knowledge/projects/{project_A_id}
       3. Assert 404
       4. User B tries PATCH /v1/knowledge/projects/{project_A_id}
       5. Assert 404
     [ ] Pass

T05: knowledge-service down = chat still works
     Steps:
       1. docker compose stop knowledge-service
       2. Send chat message
       3. Assert response received within reasonable time
       4. Assert log shows fallback triggered
       5. docker compose start knowledge-service
     [ ] Pass

T06: Glossary fallback returns entries
     Steps:
       1. Create a book with 50 glossary entities (some pinned, varied descriptions)
       2. Create project linked to the book
       3. Chat with a message mentioning a pinned entity + a non-pinned one
       4. Assert glossary element in memory block contains both
       5. Assert pinned comes first
     [ ] Pass

T07: User deletes data, other users unaffected
     Steps:
       1. User A creates project + summary
       2. User B creates project + summary
       3. User A calls DELETE /v1/knowledge/user-data
       4. Assert user A's data gone (list projects returns empty)
       5. Assert user B's data intact (list projects still has their project)
     [ ] Pass

T08: Timeout enforced
     Steps:
       1. Artificially slow glossary-service (add sleep in test mode)
       2. Call /internal/context/build
       3. Assert response within 500ms
       4. Assert glossary block missing or empty
       5. Assert `knowledge_layer_timeout{layer="glossary"}` metric incremented
     [ ] Pass

T09: Migration rollback safety
     Steps:
       1. Apply migration
       2. Rollback migration (if yoyo supports it) or restore from pre-migration backup
       3. Verify chat-service and knowledge-service still function
     [ ] Pass
     Notes: Optional but recommended. Skip if time is tight.

T10: XML injection in project instructions
     Steps:
       1. Create project with instructions containing < > & " ]]> characters
       2. Build context
       3. Parse returned XML with strict parser (lxml)
       4. Assert parser accepts it (no errors)
       5. Assert original content recoverable after unescape
     [ ] Pass
```

**Additional smoke tests (manual):**

```
S01: Full user journey (test account)
  1. Log in with claude-test@loreweave.dev
  2. Create a new project "Test Book" of type "book"
  3. Attach it to an existing book with glossary
  4. Edit instructions: "You are a helpful writing assistant."
  5. Go to Settings → Memory → Global, set bio
  6. Start a new chat, assign to "Test Book"
  7. Ask: "What glossary entities do you know about?"
  8. Verify the response references actual glossary entries
  9. Check Docker logs: knowledge-service received the request and returned Mode 2
  [ ] Pass

S02: i18n smoke test
  1. Switch to Vietnamese
  2. Verify all knowledge UI strings translated
  3. Switch to Chinese, Japanese — same
  [ ] Pass

S03: Mobile responsive smoke test
  1. Open on phone or Chrome DevTools mobile view
  2. Navigate to Knowledge page
  3. Create a project
  4. Open chat, verify header indicator renders
  [ ] Pass
```

---

## 15. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cross-service chat_sessions migration deadlock | Low | High | Run chat-service migration before starting knowledge-service |
| FTS ts_vector performance at 1650+ entities | Low | Medium | GIN index added in K2.1; benchmark in T06 |
| XML escaping bugs with CJK | Medium | Medium | Dedicated unit tests in K4.1; integration test T10 |
| Cache staleness annoys users editing bio | Medium | Low | 60s TTL + invalidation on write (K6.3) |
| chat-service circular dependency | Low | High | knowledge-service never calls chat-service; verified in code review |
| Deployment coordination (services must be compatible) | Medium | High | Compatibility version header in /internal API; deploy in order |
| Glossary-service breaks when we add columns | Low | High | Additive schema only; existing queries compatible |
| User sees stale project_id after deleting project | Medium | Low | Frontend re-validates on action; backend returns 404 |
| Rate-limit on gateway proxy | Low | Medium | Existing gateway has rate limiting; knowledge-service inherits |
| Memory cache OOM on server | Low | Medium | max_size=10000 entries, ~100 MB cap |
| User writes malicious XML in project instructions | Medium | Low | K4.1 escape helper handles it; T10 verifies |
| Cross-user data leak via missed WHERE clause | Low | Critical | Lint rule + PR review + T04/T07 tests |

---

## 16. Getting Started Checklist (Day 1)

Before writing any code, spend 30 minutes:

- [ ] Read KNOWLEDGE_SERVICE_ARCHITECTURE.md §3, §4, §7 (relevant sections only)
- [ ] Read this doc start to finish
- [ ] Open `docker-compose.yml` and familiarize with how existing services are wired
- [ ] Open `services/chat-service/` and look at its structure (our template for knowledge-service)
- [ ] Create a new branch: `git checkout -b feature/knowledge-service-track1`
- [ ] Update SESSION_PATCH.md with "Starting Track 1 implementation"
- [ ] Confirm `docker compose up -d postgres redis minio` starts cleanly
- [ ] Run existing tests to confirm baseline: `cd services/chat-service && pytest`

Now start K0.1.

---

## 17. Progress Tracking

Keep the following running count as you work through the plan:

```
K0 Scaffold        [ / 9  tasks]   Gate 1: [ ]
K1 Schema          [ / 6  tasks]   Gate 2: [ ]
K2 Glossary schema [ / 5  tasks]
K3 Short desc      [ / 3  tasks]
K4 Context builder [ / 12 tasks]   Gate 3: [ ]
K5 chat integration[ / 5  tasks]
K6 Degradation     [ / 5  tasks]
K7 Public API      [ / 7  tasks]   Gate 4: [ ]
K8 Frontend        [ / 8  tasks]
K9 Chat indicator  [ / 4  tasks]   Gate 5: [ ]

Integration tests  [ / 10 tests]
Smoke tests        [ / 3  tests]

Total Track 1 tasks: 64
```

Update this in the doc (or in a separate tracking file) as you tick off tasks.
Commit after each task or small group.

---

## 18. Out of Scope — Do Not Build in Track 1

Explicit reminders of things that look tempting but belong to Track 2+:

- **No Neo4j.** Not even a container. Track 2.
- **No LLM extraction.** No Pass 1, no Pass 2. Track 2.
- **No embedding service.** Track 2.
- **No extraction_pending queue table.** Track 2.
- **No provenance edges.** Track 2.
- **No chat.turn_completed outbox event.** Track 2 (chat-service doesn't need to emit it yet).
- **No L2 or L3 context layers.** Track 2.
- **No memory timeline, entities table, raw drawers UI.** Track 3.
- **No tool calling integration.** Track 3.
- **No summary regeneration (LLM-based).** Track 3.
- **No per-project embedding model selection UI.** Track 2.
- **No Extraction Jobs UI.** Track 2.
- **No build knowledge graph dialog.** Track 2 (the button exists in K9.3 but is disabled with "Coming soon" tooltip).

If you find yourself building any of these, STOP. Note it for Track 2 and
continue with Track 1 tasks.

---

## 19. When You Hit a Dead End

Track 1 is ambitious but bounded. If you get stuck:

1. **Read the relevant KSA section again.** The architecture doc has the answer for 90% of design questions.
2. **Check the acceptance criteria.** Are you over-engineering? The criteria define "done."
3. **Ask for help from the AI assistant** — specifically reference the task ID (e.g., "stuck on K4.9, need help with Mode 2 XML structure").
4. **Write a test first.** If you don't know how to implement, writing the test often clarifies the design.
5. **Skip and come back.** If a task is blocked on another service issue, note it and continue with parallel tasks. Don't let one task block all progress.

Tasks that can be done in parallel:
- K2 (glossary schema) can run alongside K1 (knowledge schema)
- K3 (short description) can run alongside K4 (context builder)
- K6 (degradation) can be done after K4 but before or alongside K5
- K8 (frontend) can start once K7 APIs are stable enough to call (may be partial)
- K9 (chat indicator) runs after K8

---

## 20. After Track 1 Ships

When Track 1 is done (all gates pass, all tests green):

1. **Commit the final state** with message "feat(knowledge): Track 1 complete — static memory baseline"
2. **Update SESSION_PATCH.md** with what was shipped and what's next
3. **Write a retrospective** (short, 10-15 bullets) in `docs/sessions/TRACK1_RETRO.md`:
   - What went well
   - What was harder than expected
   - Bugs caught by each gate
   - Time per phase (actual vs estimate)
   - Things to change in Track 2 based on what you learned
4. **Decide on Track 2.** You might want to:
   - Use Track 1 for a week in your actual writing workflow before committing to Track 2
   - Fix any friction points before adding complexity
   - Scope Track 2 more carefully based on what Track 1 taught you

Track 1 is not just an intermediate step — it's a **real product**. Many
users might stop here and never need Track 2. That's fine.

---

*Created: 2026-04-13 (session 34) — PM implementation plan for KSA Track 1*
*Total tasks: 64 + 10 integration tests + 3 smoke tests*
*Target: complete Track 1 as a real shippable milestone*
