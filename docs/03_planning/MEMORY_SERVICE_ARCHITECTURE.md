# Memory Service Architecture

> **Status:** Design draft — for discussion
> **Date:** 2026-04-12 (session 34)
> **Adapted for:** LoreWeave multi-user cloud (Postgres + pgvector, no SQLite/ChromaDB)

---

## Acknowledgments & Inspiration

This architecture draws significant inspiration from several open-source projects and
industry research. We believe in giving proper credit to the work that influenced our design.

### MemPalace

**Project:** [MemPalace](https://github.com/MemPalace/mempalace) by the MemPalace team
**License:** MIT
**Version studied:** 3.1.0 (April 2026)

MemPalace is an open-source, local-first AI memory system that achieved 96.6% on the
LongMemEval benchmark. Several core concepts in this architecture are directly inspired
by MemPalace's design:

| Concept borrowed | MemPalace origin | Our adaptation |
|---|---|---|
| Palace hierarchy (wings/rooms/halls) | Hierarchical memory organization | Mapped to book/chapter/fact-type |
| Verbatim storage over summarization | Raw drawers in ChromaDB | Raw drawers in Postgres + pgvector |
| L0-L3 lazy-loaded memory stack | 4-layer token-budgeted retrieval | Same concept, Postgres-backed |
| Pattern-based extraction (no LLM) | `general_extractor.py` regex patterns | Ported pattern lists for decisions/preferences/milestones |
| Two-pass entity detection | `entity_detector.py` candidate → scoring | Same approach for character/place extraction |
| Temporal knowledge graph | SQLite triples with valid_from/valid_to | Postgres triples with same temporal model |
| Exchange-pair chunking | `convo_miner.py` Q+A units | Same chunking strategy for chat mining |

We chose to **reimplement from scratch** rather than fork because:
- MemPalace is built on SQLite + ChromaDB (local, single-user)
- LoreWeave requires Postgres + pgvector (cloud, multi-user)
- Only ~18% of MemPalace code is portable; the rest is storage-layer specific
- Multi-tenant `user_id` scoping touches every query and table

We deeply respect the MemPalace team's work and encourage anyone interested in
local-first AI memory to check out their project.

### Other influences

- **Mem0** ([mem0.ai](https://github.com/mem0ai/mem0)) — memory scoping model (user/session/agent),
  conflict resolution strategy, graph memory concept. Mem0's research paper
  ([arXiv:2504.19413](https://arxiv.org/abs/2504.19413)) informed our extraction pipeline design.
- **Claude's 3-layer memory** (Anthropic) — the distinction between persistent instructions
  vs persistent memory, and project-scoped isolation.
- **ChatGPT Memory** (OpenAI) — the concept of an editable memory dashboard where users
  can view, edit, and delete what the AI remembers.
- **OpenAI Agents SDK** — session-based memory with trimming, distillation, and consolidation
  patterns for short-term → long-term memory promotion.

---

## 1. Problem Statement

LoreWeave's current chat is a **stateless replay buffer** — it sends the last 50 messages to the LLM on every turn. This has fundamental limitations:

| Problem | Impact |
|---------|--------|
| Context window limit | After 50 messages, older context silently dropped |
| No semantic memory | Important decisions buried in noise |
| Linear cost scaling | Every turn re-sends entire history as prompt tokens |
| No cross-session memory | New session = AI knows nothing about user/book |
| Model switching loses context | Model B doesn't understand Model A's assumptions |
| No book-aware context | AI doesn't auto-know character names, plot decisions, glossary |

### What competitors do

| Product | Approach |
|---------|----------|
| ChatGPT | Memory dashboard (extracted facts) + Projects (scoped instructions) |
| Claude | 3-layer: chat memory + project memory + API memory tool |
| Mem0 | LLM-based extraction → vector store + knowledge graph |
| MemPalace | Verbatim storage + palace hierarchy + temporal KG + L0-L3 stack |

### Why MemPalace's approach fits LoreWeave

1. **Verbatim storage** — novel writing needs exact character descriptions, dialogue style, world-building details. Summarization loses nuance.
2. **Structured hierarchy** — maps naturally to LoreWeave's domain: Book = Wing, Chapter/Character = Room, Fact type = Hall.
3. **Temporal knowledge graph** — "What did we decide about this character in January?" is a core novel-writing query.
4. **Pattern-based extraction** — no LLM needed for memory extraction, keeps cost near zero.
5. **Token-budgeted layers** — ~200-1050 tokens per turn vs 5000+ for raw history replay.

---

## 2. Architecture Overview

### Design Principles

- **Dedicated microservice** — `memory-service` (Python/FastAPI) owns all memory logic and data
- **Shared infrastructure layer** — consumed by chat-service, writing-assistant, translation-service, and any future AI pipeline
- **Per-service DB** — memory-service owns `memory_db` (follows LoreWeave's per-service DB rule)
- **Server-side only** — all memory logic in backend, frontend is a renderer
- **pgvector for embeddings** — no external vector DB (ChromaDB, Pinecone)
- **Pattern-based extraction** — no LLM calls for memory ops (zero incremental cost)
- **Multi-user, multi-project** — every memory scoped to `user_id`, optionally to `project_id`/`session_id`
- **Temporal validity** — triples have `valid_from`/`valid_until` for timeline queries
- **Provider-registry for embeddings** — BYOK model via existing proxy pattern
- **Gateway invariant preserved** — all external traffic through api-gateway-bff

### Why a Separate Service (not in chat-service)

LoreWeave has multiple AI pipelines that need memory:

| Service | Needs memory for |
|---|---|
| chat-service | Context injection + extraction per chat turn |
| writing-assistant-service (future) | Book context, character consistency, writing style |
| translation-service | Term consistency, previous translation choices |
| glossary-service | Auto-populate entity descriptions from chat |
| video-gen-service (future) | Scene + character appearance consistency |

Putting memory inside chat-service would force every other AI service to call into
chat-service for memory operations — wrong coupling (they're peers, not dependents)
and it violates the per-service DB rule. Memory must be a **shared infrastructure
service** owned by nobody and used by everybody.

### Why Python (not Go)

Per `CLAUDE.md`: "Go for domain services, Python for AI/LLM services." Memory sits in
the middle, but the Python choice is clear because:

1. **Pattern-based extraction** is the core value-add — regex + text processing is
   Python-native. We're porting patterns from MemPalace which is Python.
2. **Embedding pipeline** uses provider-registry the same way chat-service does —
   same async HTTP patterns, same credential resolution.
3. **LLM-assisted summarization** (L0/L1 regeneration) needs the same provider
   infrastructure as chat-service.
4. **Pydantic + FastAPI + asyncpg + pgvector** are all first-class in Python.
5. **Consistency with chat-service** — same language, same async patterns, easy
   knowledge transfer.

### System Context

```
┌─────────────────────────────────────────────────────────────────┐
│ api-gateway-bff (NestJS — external entry point)                 │
└───┬─────────────────────────────┬───────────────────────────────┘
    │                             │
    │ /v1/memory/*                │ /v1/chat/*
    │ (user-facing CRUD)          │
    │                             │
┌───▼──────────────┐  ┌───────────▼────────────┐  ┌──────────────┐
│ memory-service   │◄─┤ chat-service           │  │ writing-     │
│ (Python/FastAPI) │  │ (Python/FastAPI)       │  │ assistant    │
│                  │  │                        │  │ (future)     │
│ • Extraction     │  │ • Chat sessions        │  │              │
│ • Context build  │  │ • Voice pipeline       │  │              │
│ • CRUD + search  │  │ • Calls memory-service │  │              │
│ • Embedding      │  │                        │  │              │
└───┬──────────────┘  └────────────────────────┘  └──────┬───────┘
    │                                                      │
    │◄─────────────────────────────────────────────────────┘
    │           (internal API — X-Internal-Token)
    │
┌───▼──────────────┐      ┌─────────────────────────────┐
│ memory_db        │      │ provider-registry-service   │
│ Postgres +       │      │ (embedding proxy for        │
│ pgvector         │      │  BYOK models)               │
└──────────────────┘      └─────────────────────────────┘
```

### Service Responsibilities

**memory-service owns:**
- 5 Postgres tables: `memory_projects`, `memory_entities`, `memory_triples`, `memory_drawers`, `memory_summaries`
- Extraction pipeline (pattern-based, no LLM)
- Context builder (L0-L3 assembly with token budgets)
- Embedding generation (proxies through provider-registry)
- Summary regeneration (periodic, uses LLM sparingly)
- Memory CRUD API (projects, entities, timeline, manual entries)
- GDPR erasure

**chat-service consumes memory-service:**
- Calls `POST /internal/context/build` before LLM call → gets assembled context string
- Calls `POST /internal/extract` after LLM response → fires-and-forgets extraction
- No memory logic or tables in chat-service

**Future services** (writing-assistant, translation, etc.) consume the same internal API.

---

## 3. Data Model

### 3.1 Scope Model

LoreWeave serves multiple purposes (novel writing, translation, worldbuilding, coding,
general AI chat). Memory must be scoped to reflect this — not locked to books.

```
┌─────────────────────────────────────────────────────────────┐
│ Global Memory (user-wide)                                   │
│  "User is Vietnamese", "prefers formal English"             │
│                                                             │
│  ┌───────────────────┐  ┌───────────────────┐              │
│  │ Project:           │  │ Project:           │  ...        │
│  │ "Eastern Sea" book │  │ "Translation Work" │             │
│  │                    │  │                    │             │
│  │ ┌──────┐ ┌──────┐ │  │ ┌──────┐ ┌──────┐ │             │
│  │ │Sess 1│ │Sess 2│ │  │ │Sess 3│ │Sess 4│ │             │
│  │ └──────┘ └──────┘ │  │ └──────┘ └──────┘ │             │
│  └───────────────────┘  └───────────────────┘              │
│                                                             │
│  ┌──────┐ ┌──────┐  (unassigned sessions — no project)     │
│  │Sess 5│ │Sess 6│                                          │
│  └──────┘ └──────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

**Four memory scopes:**

| Scope | Lifetime | What it stores | Example |
|---|---|---|---|
| **Global** | Permanent, cross-project | User identity, preferences, habits | "User is Vietnamese novelist, UTC+7" |
| **Project** | Lives with the project | Domain knowledge, rules, entities | "5 kingdoms, fire magic, Kai is 17" |
| **Session** | Lives with the chat session | Conversation-specific decisions | "Rewriting ch.12, trying approach B" |
| **Turn** | Discarded after response | Recent messages (last 10-20) | Current replay buffer |

**Projects are explicit containers** — a user creates them like ChatGPT Projects.
A project can link to a book (`book_id`), a codebase, a translation job, or nothing
(general-purpose). Sessions can optionally belong to a project.

### 3.2 Palace Hierarchy → LoreWeave Mapping

```
MemPalace           LoreWeave
─────────           ─────────
Wing          →     Project (book, translation job, codebase, general)
Room          →     Topic / Chapter / Character / Module
Hall          →     Memory type: fact, decision, event, preference, milestone
Tunnel        →     Cross-project entity (same character in multiple books)
Closet        →     memory_summaries (compressed context per scope)
Drawer        →     memory_drawers (verbatim text chunks with embeddings)
```

### 3.3 Postgres Schema

```sql
-- Extension required
CREATE EXTENSION IF NOT EXISTS vector;

-- ═══════════════════════════════════════════════════════════════
-- Projects: explicit containers for scoping memory
-- (like ChatGPT Projects — a book, a codebase, a translation job, or general)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_projects (
    project_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    project_type    TEXT DEFAULT 'general', -- book, translation, code, general
    book_id         UUID,                   -- optional link to existing book
    instructions    TEXT DEFAULT '',         -- persistent project instructions (like ChatGPT custom instructions)
    is_archived     BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memory_projects_user ON memory_projects(user_id);

-- ═══════════════════════════════════════════════════════════════
-- Link sessions to projects (optional — sessions can be unassigned)
-- ═══════════════════════════════════════════════════════════════
-- This is a column addition to existing chat_sessions table:
-- ALTER TABLE chat_sessions ADD COLUMN project_id UUID REFERENCES memory_projects(project_id);

-- ═══════════════════════════════════════════════════════════════
-- Entities: characters, places, concepts, terms
-- Scoped to project (or global if project_id is NULL)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_entities (
    entity_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    project_id      UUID REFERENCES memory_projects(project_id),  -- NULL = global
    name            TEXT NOT NULL,
    entity_type     TEXT NOT NULL,       -- person, place, concept, item, event
    aliases         TEXT[] DEFAULT '{}', -- alternative names / spellings
    properties      JSONB DEFAULT '{}',  -- flexible metadata
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, project_id, name, entity_type)
);

CREATE INDEX idx_memory_entities_user ON memory_entities(user_id, project_id);
CREATE INDEX idx_memory_entities_name ON memory_entities(user_id, name);

-- ═══════════════════════════════════════════════════════════════
-- Triples: subject → predicate → object (temporal knowledge graph)
-- Scoped to project + optionally session
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_triples (
    triple_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    project_id      UUID REFERENCES memory_projects(project_id),  -- NULL = global
    session_id      UUID,               -- NULL = project-level, set = session-level
    subject         TEXT NOT NULL,       -- entity name or free text
    predicate       TEXT NOT NULL,       -- "is", "lives_in", "killed", "decided_to", "prefers"
    object          TEXT NOT NULL,       -- entity name or free text
    confidence      REAL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    valid_from      TIMESTAMPTZ DEFAULT now(),
    valid_until     TIMESTAMPTZ,         -- NULL = still valid
    source_type     TEXT DEFAULT 'chat', -- chat, mining, manual, glossary_sync
    source_message_id UUID,              -- link to chat_messages
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memory_triples_user_project ON memory_triples(user_id, project_id);
CREATE INDEX idx_memory_triples_session ON memory_triples(user_id, session_id);
CREATE INDEX idx_memory_triples_subject ON memory_triples(user_id, subject);
CREATE INDEX idx_memory_triples_object ON memory_triples(user_id, object);
CREATE INDEX idx_memory_triples_temporal ON memory_triples(user_id, valid_from, valid_until);

-- ═══════════════════════════════════════════════════════════════
-- Drawers: verbatim text chunks with vector embeddings
-- Scoped to project + optionally session
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_drawers (
    drawer_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    project_id      UUID REFERENCES memory_projects(project_id),  -- wing
    session_id      UUID,               -- NULL = project-level, set = session-level
    room            TEXT NOT NULL,       -- topic / chapter / character / module
    hall            TEXT DEFAULT 'facts',-- facts, decisions, events, preferences, milestones
    content         TEXT NOT NULL,
    embedding       vector(1536),        -- pgvector (dimension depends on embedding model)
    source_type     TEXT DEFAULT 'chat', -- chat, book_content, glossary, manual
    source_id       UUID,                -- message_id, chapter_id, etc.
    token_count     INT,
    filed_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memory_drawers_user_project ON memory_drawers(user_id, project_id);
CREATE INDEX idx_memory_drawers_session ON memory_drawers(user_id, session_id);
CREATE INDEX idx_memory_drawers_room ON memory_drawers(user_id, project_id, room);
CREATE INDEX idx_memory_drawers_embedding ON memory_drawers
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ═══════════════════════════════════════════════════════════════
-- Summaries: compressed context per scope (L0 and L1 layers)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_summaries (
    summary_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    scope_type      TEXT NOT NULL,       -- global, project, session, entity
    scope_id        UUID,                -- project_id, session_id, entity_id (NULL for global)
    content         TEXT NOT NULL,
    token_count     INT,
    version         INT DEFAULT 1,       -- incremented on regeneration
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, scope_type, scope_id)
);
```

### 3.4 Scope Resolution at Query Time

When building memory context for a chat turn, the system queries multiple scopes
and merges results by priority:

```
Session S belongs to Project P, owned by User U.

L0 (identity):
  memory_summaries WHERE user_id=U AND scope_type='global'

L1 (project context):
  memory_summaries WHERE user_id=U AND scope_type='project' AND scope_id=P

L2 (relevant facts):
  memory_triples WHERE user_id=U AND (project_id=P OR project_id IS NULL)
                   AND valid_until IS NULL
                   AND subject IN (detected_entities)

L3 (semantic search):
  memory_drawers WHERE user_id=U AND (project_id=P OR project_id IS NULL)
                  ORDER BY embedding <=> query_embedding
                  LIMIT 5

Turn context:
  chat_messages WHERE session_id=S ORDER BY sequence_num DESC LIMIT 20
```

**Note:** Queries always include `project_id IS NULL` (global memories) alongside
project-scoped memories. Global memories apply everywhere. Project memories
only apply within that project. Session-level memories are included when
querying within that session.

### 3.5 Glossary Integration

LoreWeave already has a glossary system tied to books. When a project is linked to a
book (`memory_projects.book_id`), the glossary auto-syncs to project memory:

| Glossary concept | Memory equivalent |
|---|---|
| Glossary entity | `memory_entities` row (sync on create/update, scoped to project) |
| Entity description | `memory_drawers` row (room = entity name, hall = 'facts') |
| Entity relationships | `memory_triples` rows |
| Entity kind | `memory_entities.entity_type` |

When a glossary entity is created/updated, a background job syncs to `memory_entities`
and `memory_drawers` under the project that links to that book. This means the AI
automatically knows about characters, places, and concepts from the glossary without
the user needing to attach context manually.

Projects without a linked book (translation jobs, general chat) don't use glossary sync.

---

## 4. Memory Stack (L0-L3)

Inspired by MemPalace's lazy-loaded layer system. Each layer has a token budget and trigger condition.

### 4.0 Layer 0 — Identity (always loaded, ~50 tokens)

**Source:** `memory_summaries WHERE scope_type = 'identity'`

**Content example:**
```
Vietnamese novelist. Writes fantasy and sci-fi. Prefers formal prose style.
Working on "The Three Kingdoms" series. Uses LoreWeave for translation and worldbuilding.
```

**When loaded:** Every LLM call.

**How populated:** Extracted from early conversations, editable by user in settings.

### 4.1 Layer 1 — Project Context (loaded when session is in a project, ~200 tokens)

**Source:** `memory_summaries WHERE scope_type = 'project' AND scope_id = active_project_id`

Plus project instructions from `memory_projects.instructions` (user-editable, like ChatGPT custom instructions).

**Content example — Book project:**
```
Project: "Winds of the Eastern Sea" (book, 45 chapters). Protagonist Kai (17, fire elemental)
trained by Master Lin (deceased ch.12). Magic system: five elements, unlocked by emotional triggers.
Current arc: Kai infiltrating the Water Kingdom. Antagonist: Empress Yun (ice elemental, political).
Key unresolved: Lin's secret identity, the Sixth Element prophecy.
Instructions: Respond in formal prose style. Avoid modern idioms.
```

**Content example — Translation project:**
```
Project: "Vietnamese-English translation work". Source genre: xianxia web novels.
Target audience: English-speaking cultivation novel readers. Style: preserve cultural terms
(dao, qi, jianghu), use footnotes for first mentions. Previous glossary includes 47 terms.
Instructions: Never localize character names. Keep Chinese honorifics.
```

**Content example — General project (or no project):**
```
(L1 is empty or skipped when session has no project)
```

**When loaded:** When the session is linked to a project (`chat_sessions.project_id IS NOT NULL`).

**How populated:** Background job after every N conversation turns in the project. Uses pattern extraction + periodic LLM summarization (cheap, infrequent). User can also edit `memory_projects.instructions` directly for the static portion.

### 4.2 Layer 2 — Relevant Facts (on-demand, ~300 tokens)

**Source:** `memory_triples` filtered by entities detected in user message, scoped to current project + global.

**Query logic:**
1. Extract entity names from user message (pattern-based, no LLM)
2. `SELECT * FROM memory_triples WHERE user_id = $1 AND (project_id = $2 OR project_id IS NULL) AND subject IN (entities) AND valid_until IS NULL`
3. Also reverse: `WHERE object IN (entities)`
4. Format as compact fact list

**Content example (user mentions "Kai" and "Water Kingdom"):**
```
Known facts:
- Kai is a fire elemental (since ch.1)
- Kai is infiltrating Water Kingdom (since ch.38)
- Kai's cover identity is "merchant's apprentice" (since ch.38)
- Water Kingdom capital is Hailong City
- Empress Yun rules Water Kingdom
- Kai killed Commander Zhao in ch.35 (Water Kingdom doesn't know)
```

**When loaded:** When the user message contains recognized entity names.

### 4.3 Layer 3 — Deep Search (on-demand, ~500 tokens)

**Source:** `memory_drawers` via pgvector cosine similarity search, scoped to project + global.

**Query logic:**
1. Embed user message (via embedding model from provider-registry)
2. `SELECT content, 1 - (embedding <=> $query_embedding) AS similarity FROM memory_drawers WHERE user_id = $1 AND (project_id = $2 OR project_id IS NULL) ORDER BY similarity DESC LIMIT 5`
3. Optionally filter by `room`, `hall`

**When loaded:** When L2 returns fewer than 3 relevant facts, or when the user asks a broad question ("what happened in the early chapters?").

**Content:** Verbatim text passages from past conversations or book content.

### Token Budget Summary

| Layer | Tokens | Trigger | Source |
|---|---|---|---|
| L0 | ~50 | Always | `memory_summaries` (identity) |
| L1 | ~200 | Book attached | `memory_summaries` (book) |
| L2 | ~300 | Entities detected | `memory_triples` (filtered) |
| L3 | ~500 | L2 insufficient | `memory_drawers` (pgvector) |
| **Total** | **~200-1050** | | vs ~5000 for 50-message replay |

---

## 5. Memory Extraction Pipeline

### 5.1 Pattern-Based Extractor (zero LLM cost)

Runs after each conversation turn as a background task. Inspired by MemPalace's `general_extractor.py`.

**Memory types detected by regex patterns:**

| Type | Markers (examples) | Hall |
|---|---|---|
| Decision | "let's use", "we decided", "instead of", "trade-off" | decisions |
| Preference | "I prefer", "always use", "never use", "my rule is" | preferences |
| Milestone | "it works", "fixed", "breakthrough", "finished chapter" | milestones |
| Fact | "X is Y", "X lives in Y", names + descriptions | facts |
| Event | "in chapter N", "when X happened", "after the battle" | events |

**Entity extraction:** Two-pass system (like MemPalace):
1. Candidate extraction: capitalized words, quoted names, known glossary entities
2. Signal scoring: frequency, position in sentence, co-occurrence with verbs

**Triple extraction:** Pattern matching on SVO (subject-verb-object) sentences:
- "Kai killed Commander Zhao" → `(Kai, killed, Commander Zhao)`
- "The capital is Hailong City" → `(capital, is, Hailong City)`
- "We decided to use fire magic" → `(story, decided, use fire magic)` + hall=decisions

### 5.2 Conversation Mining (on session end or periodically)

Processes the full conversation history for a session:
1. Group messages into exchange pairs (user + assistant)
2. Run pattern extractor on each pair
3. Detect room (chapter/character/topic) by keyword scoring
4. Store extracted memories as drawers + triples

### 5.3 Book Content Mining (on import or chapter save)

When a user imports a book or saves a chapter:
1. Chunk chapter text (800 chars, 100 overlap — like MemPalace)
2. Extract entities and triples
3. Store as drawers with `source_type = 'book_content'`
4. Cross-reference with glossary entities

### 5.4 Glossary Sync (on glossary change)

When glossary entities are created/updated/deleted:
1. Upsert corresponding `memory_entities` row
2. Upsert `memory_drawers` with entity description
3. Upsert `memory_triples` for entity relationships

---

## 6. Memory-Service API

### 6.0 Internal API (service-to-service, `X-Internal-Token` auth)

These endpoints are called by chat-service, writing-assistant-service, and other
AI pipelines. Not exposed through api-gateway-bff.

#### `POST /internal/context/build`

Build assembled memory context for an LLM call.

**Request:**
```json
{
  "user_id": "uuid",
  "project_id": "uuid | null",
  "session_id": "uuid",
  "message": "user message text",
  "layers": ["L0", "L1", "L2", "L3"],
  "token_budget": 1050
}
```

**Response:**
```json
{
  "context": "=== Memory Context ===\n[About the user]...",
  "layers_loaded": ["L0", "L1", "L2"],
  "token_count": 487,
  "cache_key": "optional — for request deduplication"
}
```

#### `POST /internal/extract`

Extract and store memories from a conversation turn. Fire-and-forget — returns 202.

**Request:**
```json
{
  "user_id": "uuid",
  "project_id": "uuid | null",
  "session_id": "uuid",
  "user_message": "...",
  "assistant_message": "...",
  "message_id": "uuid"
}
```

**Response:** `202 Accepted` (extraction runs in background)

#### `POST /internal/embed`

Generate embedding for text via user's BYOK embedding model.

**Request:**
```json
{
  "user_id": "uuid",
  "text": "text to embed",
  "model_source": "user_model",
  "model_ref": "uuid"
}
```

**Response:**
```json
{
  "embedding": [0.123, 0.456, ...],
  "dimension": 1536,
  "model_name": "text-embedding-3-small"
}
```

#### `POST /internal/summarize`

Regenerate a summary (L0/L1) using LLM. Called by scheduled background job,
not on the chat hot path.

**Request:**
```json
{
  "user_id": "uuid",
  "scope_type": "global | project",
  "scope_id": "uuid | null",
  "model_source": "user_model",
  "model_ref": "uuid"
}
```

**Response:**
```json
{
  "summary_id": "uuid",
  "content": "...",
  "token_count": 180,
  "version": 3
}
```

---

### 6.1 Public API (user-facing, JWT auth via api-gateway-bff)

Exposed at `/v1/memory/*` through the gateway.

#### Projects

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/memory/projects` | List user's projects |
| `POST` | `/v1/memory/projects` | Create a project |
| `GET` | `/v1/memory/projects/{id}` | Get project details |
| `PATCH` | `/v1/memory/projects/{id}` | Update project (name, description, instructions) |
| `DELETE` | `/v1/memory/projects/{id}` | Delete project (cascade deletes scoped memories) |
| `POST` | `/v1/memory/projects/{id}/archive` | Archive a project |

#### Memories

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/memory/summaries` | Get L0 (global) and L1 (per project) summaries |
| `GET` | `/v1/memory/entities?project_id=...` | List entities scoped to project (or global) |
| `GET` | `/v1/memory/triples?subject=...&project_id=...` | Query triples by subject/object |
| `GET` | `/v1/memory/drawers?project_id=...&room=...` | List drawers in a project/room |
| `GET` | `/v1/memory/timeline?project_id=...&from=...&to=...` | Temporal query — events in chronological order |
| `POST` | `/v1/memory/remember` | Manual memory entry (user tells AI "remember this") |
| `DELETE` | `/v1/memory/drawers/{id}` | Forget a specific memory |
| `POST` | `/v1/memory/triples/{id}/invalidate` | Mark a triple as no longer true (sets valid_until) |
| `DELETE` | `/v1/memory/user-data` | GDPR erasure (delete all memory for user) |

#### Project instructions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/memory/projects/{id}/instructions` | Get custom instructions for a project |
| `PUT` | `/v1/memory/projects/{id}/instructions` | Set custom instructions (markdown text) |

---

## 7. Integration with Chat Service

### 6.1 Context Builder (before LLM call)

Added to `stream_service.py` — builds memory context and prepends to system prompt.

```python
async def build_memory_context(
    user_id: str,
    session_id: str,
    user_message: str,
    project_id: str | None,
    pool: asyncpg.Pool,
) -> str:
    """Build layered memory context for the LLM system prompt."""
    parts = []

    # L0: Global identity (always)
    identity = await get_summary(pool, user_id, 'global', None)
    if identity:
        parts.append(f"[About the user]\n{identity.content}")

    # L1: Project context (if session is in a project)
    if project_id:
        project = await get_project(pool, user_id, project_id)
        if project and project.instructions:
            parts.append(f"[Project instructions]\n{project.instructions}")

        project_ctx = await get_summary(pool, user_id, 'project', project_id)
        if project_ctx:
            parts.append(f"[Project context]\n{project_ctx.content}")

    # L2: Relevant triples (entity-based, project + global scope)
    entities = extract_entities_from_text(user_message)
    if entities:
        triples = await search_active_triples(pool, user_id, project_id, entities, limit=20)
        if triples:
            formatted = "\n".join(f"- {t.subject} {t.predicate} {t.object}" for t in triples)
            parts.append(f"[Known facts]\n{formatted}")

    # L3: Semantic search (project + global scope)
    if len(parts) < 3:
        drawers = await vector_search_drawers(pool, user_id, project_id, user_message, limit=5)
        if drawers:
            formatted = "\n".join(f"- {d.content[:200]}" for d in drawers)
            parts.append(f"[Related memories]\n{formatted}")

    if not parts:
        return ""
    return "=== Memory Context ===\n" + "\n\n".join(parts) + "\n=== End Memory Context ==="
```

### 6.2 Background Extractor (after LLM response)

```python
async def extract_and_store_memories(
    user_id: str,
    project_id: str | None,
    session_id: str,
    user_message: str,
    assistant_message: str,
    message_id: str,
    pool: asyncpg.Pool,
):
    """Background task: extract memories from conversation turn.

    Memories are scoped:
    - Project-level if session belongs to a project (persistent across sessions)
    - Session-level otherwise (lives with this specific conversation)
    - Global preferences/identity can be promoted from session → global via consolidation
    """
    combined = f"User: {user_message}\nAssistant: {assistant_message}"

    # Pattern-based memory extraction (no LLM)
    memories = extract_memories(combined)
    for mem in memories:
        await upsert_drawer(
            pool, user_id, project_id, session_id,
            mem.room, mem.hall, mem.content, message_id,
        )

    # Entity + triple extraction (no LLM)
    triples = extract_triples(combined)
    for triple in triples:
        await upsert_triple(pool, user_id, project_id, session_id, triple, message_id)
```

### 6.3 Tool Calling Integration (future)

Memory tools exposed to the LLM via function calling:

| Tool | Purpose |
|---|---|
| `memory_search` | Search memories by query (semantic) |
| `memory_recall_entity` | Get all known facts about an entity |
| `memory_timeline` | Get events in chronological order |
| `memory_remember` | Explicitly store a fact/decision |
| `memory_forget` | Invalidate a triple (set valid_until) |

This allows the AI to proactively search its memory when needed, rather than relying solely on the automatic context builder.

---

## 8. Embedding Strategy

### 7.1 Embedding Model

Use the user's configured embedding model via provider-registry proxy (same BYOK pattern as STT/TTS). Fallback to a lightweight model for users without one configured.

**Options:**
- User's BYOK embedding model (via provider-registry)
- Self-hosted: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, fast, free)
- Fallback: `text-embedding-3-small` (1536 dimensions, cheap)

**pgvector dimension:** Configurable per user model. Default column `vector(1536)`, but can create separate columns or use `halfvec` for smaller models.

### 7.2 When to Embed

- **Chat turns:** Background task after each turn (embed user+assistant pair)
- **Book content:** On chapter save/import (embed chunks)
- **Glossary sync:** On entity create/update (embed description)
- **Manual entries:** When user explicitly adds a memory

---

## 9. Summary Regeneration

L0 and L1 summaries become stale as conversations accumulate. Regeneration strategy:

| Scope | Trigger | Method |
|---|---|---|
| Identity (L0) | Every 50 conversation turns | LLM summarization (cheap, infrequent) |
| Book (L1) | Every 20 turns about the book | LLM summarization from latest triples + drawers |
| Character | On glossary update or every 30 mentions | Compile from triples |
| Session | On session archive | Compile from drawers for that session |

Regeneration is a background job — never blocks the chat flow.

---

## 10. Implementation Phases

| Phase | Scope | Effort | Dependencies |
|---|---|---|---|
| **P0** | Service scaffolding: new `memory-service` FastAPI app, Dockerfile, docker-compose entry, `memory_db` Postgres + pgvector extension, health check, internal token auth | Small | — |
| **P1** | Database schema + migrations: 5 tables (projects, entities, triples, drawers, summaries) + indexes | Small | P0 |
| **P2** | Internal API: `/internal/context/build` + `/internal/extract` + `/internal/embed` endpoints (stubs OK initially) | Small | P1 |
| **P3** | Pattern-based extractor: port MemPalace regex patterns for decisions/preferences/milestones, entity detector, triple extractor | Medium | P2 |
| **P4** | Context builder: L0-L3 assembly with token budgets, scope resolution (project + global) | Medium | P2, P3 |
| **P5** | chat-service integration: add memory client, call `build_context` before LLM and `extract` after (background) | Small | P4 |
| **P6** | Public API: projects CRUD, memory CRUD, `/v1/memory/*` routes, gateway proxy setup | Medium | P1 |
| **P7** | Glossary sync: listen to glossary-service events, auto-populate entities/drawers for book-linked projects | Small | P1 |
| **P8** | Embedding pipeline: provider-registry proxy for embeddings, populate `memory_drawers.embedding`, pgvector semantic search (L3) | Medium | P4 |
| **P9** | Book content mining: chapter text → chunks → drawers | Medium | P8 |
| **P10** | Summary regeneration: scheduled job, LLM-assisted L0/L1 refresh | Medium | P4, P8 |
| **P11** | Tool calling integration: expose memory tools to LLMs via chat-service tool loop | Medium | P5 |
| **P12** | Memory UI in frontend: projects list, memory viewer, timeline, manual edit/delete | Large | P6 |
| **P13** | Writing-assistant-service integration (when that service is built) | Small | P2 |

**MVP (P0-P5):** New service running, pattern extraction working, chat-service uses it.
No embeddings yet — L0-L2 context loading only, which covers 80% of the value.

**Full system (P0-P12):** Adds semantic search (L3), book mining, glossary sync,
summary regeneration, LLM tool access, and UI.

### Incremental Path for Chat-Service Migration

P5 is critical: chat-service must gracefully handle memory-service being unavailable
(degraded mode — fall back to current 50-message replay). This is the "no bricks in
production" guarantee:

```python
try:
    context = await memory_client.build_context(...)
except (httpx.RequestError, httpx.HTTPStatusError):
    logger.warning("memory-service unavailable, falling back to message replay")
    context = ""  # proceed without memory context
```

---

## 11. Cost Analysis

| Approach | Tokens per turn | Annual cost (100 turns/day) |
|---|---|---|
| Current (50 messages replay) | ~5,000 | Baseline |
| Memory L0+L1 only | ~250 | **95% reduction** |
| Memory L0+L1+L2 | ~550 | **89% reduction** |
| Memory L0+L1+L2+L3 | ~1,050 | **79% reduction** |

Extraction cost: **$0** (pattern-based, no LLM calls).
Summary regeneration: ~$0.50/month (infrequent LLM calls for L0/L1 refresh).

---

## 12. Open Questions

1. **Embedding dimension:** Should we standardize on 1536 (OpenAI compatible) or support variable dimensions per user model?
2. **Conflict resolution:** When a new triple contradicts an old one, auto-invalidate the old one? Or flag for user review?
3. **Cross-project entities:** How to handle a character that appears in multiple projects (tunnel concept)?
4. **Privacy scope:** Should memory be per-user only, or support shared memories for collaborative projects?
5. **Session-to-project promotion:** When a session isn't assigned to a project, should we auto-suggest creating a project after N turns? Or keep sessions unassigned indefinitely?
6. **Global memory extraction:** How do facts get promoted from session → project → global? Auto-consolidation on threshold, or manual "remember this" command?
7. **Default "Personal" project:** Should every user have a default project, or allow truly unscoped sessions?
5. **Memory retention:** Should memories have a TTL, or persist indefinitely until invalidated?
6. **Chat history cutoff:** Once memory is active, reduce the message replay from 50 to 10-20? (Memory provides the deep context, recent messages provide the conversation flow.)

---

*Created: 2026-04-12 — LoreWeave session 34*
