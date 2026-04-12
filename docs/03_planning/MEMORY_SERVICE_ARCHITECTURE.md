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

- **Server-side only** — all memory logic in backend services, frontend is a renderer
- **No new services** — memory tables live in chat-service's Postgres database
- **pgvector for embeddings** — no external vector DB (ChromaDB, Pinecone)
- **Pattern-based extraction** — no LLM calls for memory operations (zero incremental cost)
- **Multi-user, multi-book** — every memory scoped to `user_id`, optionally to `book_id`
- **Temporal validity** — triples have `valid_from`/`valid_until` for timeline queries
- **Existing integration** — plugs into `stream_service.py` context builder, exposed via tool calling

### System Context

```
┌─────────────────────────────────────────────────────────┐
│ chat-service (Python / FastAPI)                         │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ stream_      │  │ memory_      │  │ memory_       │  │
│  │ service.py   │──│ context.py   │  │ extractor.py  │  │
│  │ (LLM loop)  │  │ (L0-L3 load) │  │ (background)  │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                 │                   │          │
│  ┌──────▼─────────────────▼───────────────────▼───────┐  │
│  │ Postgres (chat-service DB)                         │  │
│  │  ├── chat_messages (existing)                      │  │
│  │  ├── memory_entities                               │  │
│  │  ├── memory_triples                                │  │
│  │  ├── memory_drawers (+ pgvector)                   │  │
│  │  └── memory_summaries                              │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Data Model

### 3.1 Palace Hierarchy → LoreWeave Domain Mapping

```
MemPalace           LoreWeave
─────────           ─────────
Wing          →     Book (or "global" for cross-book knowledge)
Room          →     Chapter / Character / Topic / Glossary entity
Hall          →     Memory type: fact, decision, event, preference, milestone
Tunnel        →     Cross-book entity (same character appears in multiple books)
Closet        →     memory_summaries (compressed context per scope)
Drawer        →     memory_drawers (verbatim text chunks with embeddings)
```

### 3.2 Postgres Schema

```sql
-- Extension required
CREATE EXTENSION IF NOT EXISTS vector;

-- ═══════════════════════════════════════════════════════════════
-- Entities: characters, places, concepts, projects
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_entities (
    entity_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    book_id         UUID REFERENCES books(book_id),  -- NULL = global
    name            TEXT NOT NULL,
    entity_type     TEXT NOT NULL,       -- person, place, concept, item, event
    aliases         TEXT[] DEFAULT '{}', -- alternative names / spellings
    properties      JSONB DEFAULT '{}',  -- flexible metadata
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, book_id, name, entity_type)
);

CREATE INDEX idx_memory_entities_user_book ON memory_entities(user_id, book_id);
CREATE INDEX idx_memory_entities_name ON memory_entities(user_id, name);

-- ═══════════════════════════════════════════════════════════════
-- Triples: subject → predicate → object (temporal knowledge graph)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_triples (
    triple_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    book_id         UUID REFERENCES books(book_id),
    subject         TEXT NOT NULL,       -- entity name or free text
    predicate       TEXT NOT NULL,       -- relationship verb: "is", "lives_in", "killed", "decided_to"
    object          TEXT NOT NULL,       -- entity name or free text
    confidence      REAL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    valid_from      TIMESTAMPTZ DEFAULT now(),
    valid_until     TIMESTAMPTZ,         -- NULL = still valid
    source_type     TEXT DEFAULT 'chat', -- chat, mining, manual, glossary_sync
    source_message_id UUID,              -- link to chat_messages
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memory_triples_user_book ON memory_triples(user_id, book_id);
CREATE INDEX idx_memory_triples_subject ON memory_triples(user_id, subject);
CREATE INDEX idx_memory_triples_object ON memory_triples(user_id, object);
CREATE INDEX idx_memory_triples_temporal ON memory_triples(user_id, valid_from, valid_until);

-- ═══════════════════════════════════════════════════════════════
-- Drawers: verbatim text chunks with vector embeddings
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_drawers (
    drawer_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    book_id         UUID REFERENCES books(book_id),    -- wing
    room            TEXT NOT NULL,                      -- chapter/character/topic
    hall            TEXT DEFAULT 'facts',               -- facts, decisions, events, preferences, milestones
    content         TEXT NOT NULL,
    embedding       vector(1536),                      -- pgvector (dimension depends on embedding model)
    source_type     TEXT DEFAULT 'chat',                -- chat, book_content, glossary, manual
    source_id       UUID,                              -- message_id, chapter_id, etc.
    token_count     INT,
    filed_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memory_drawers_user_book ON memory_drawers(user_id, book_id);
CREATE INDEX idx_memory_drawers_room ON memory_drawers(user_id, book_id, room);
CREATE INDEX idx_memory_drawers_embedding ON memory_drawers
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ═══════════════════════════════════════════════════════════════
-- Summaries: compressed context per scope (L0 and L1 layers)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memory_summaries (
    summary_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    book_id         UUID REFERENCES books(book_id),
    scope_type      TEXT NOT NULL,       -- identity, book, character, chapter, session
    scope_id        UUID,                -- book_id, character entity_id, chapter_id, session_id
    content         TEXT NOT NULL,
    token_count     INT,
    version         INT DEFAULT 1,       -- incremented on regeneration
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, scope_type, scope_id)
);
```

### 3.3 Glossary Integration

LoreWeave already has a glossary system with entities, kinds, and descriptions. Memory should sync with it:

| Glossary concept | Memory equivalent |
|---|---|
| Glossary entity | `memory_entities` row (sync on create/update) |
| Entity description | `memory_drawers` row (room = entity name, hall = 'facts') |
| Entity relationships | `memory_triples` rows |
| Entity kind | `memory_entities.entity_type` |

When a glossary entity is created/updated, a background job syncs to `memory_entities` and `memory_drawers`. This means the AI automatically knows about characters, places, and concepts from the glossary without the user needing to attach context manually.

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

### 4.1 Layer 1 — Book Context (loaded when book attached, ~200 tokens)

**Source:** `memory_summaries WHERE scope_type = 'book' AND scope_id = active_book_id`

**Content example:**
```
"Winds of the Eastern Sea" — fantasy novel, 45 chapters. Protagonist Kai (17, fire elemental)
trained by Master Lin (deceased ch.12). Magic system: five elements, unlocked by emotional triggers.
Current arc: Kai infiltrating the Water Kingdom. Antagonist: Empress Yun (ice elemental, political).
Key unresolved: Lin's secret identity, the Sixth Element prophecy.
```

**When loaded:** When the user has a book attached to the chat session or sends a message referencing book content.

**How populated:** Background job after every N conversation turns about the book. Uses pattern extraction + periodic LLM summarization (cheap, infrequent).

### 4.2 Layer 2 — Relevant Facts (on-demand, ~300 tokens)

**Source:** `memory_triples` filtered by entities detected in user message.

**Query logic:**
1. Extract entity names from user message (pattern-based, no LLM)
2. `SELECT * FROM memory_triples WHERE user_id = $1 AND subject IN (entities) AND valid_until IS NULL`
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

**Source:** `memory_drawers` via pgvector cosine similarity search.

**Query logic:**
1. Embed user message (via embedding model from provider-registry)
2. `SELECT content, 1 - (embedding <=> $query_embedding) AS similarity FROM memory_drawers WHERE user_id = $1 ORDER BY similarity DESC LIMIT 5`
3. Optionally filter by `book_id`, `room`, `hall`

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

## 6. Integration with Chat Service

### 6.1 Context Builder (before LLM call)

Added to `stream_service.py` — builds memory context and prepends to system prompt.

```python
async def build_memory_context(
    user_id: str,
    session_id: str,
    user_message: str,
    book_id: str | None,
    pool: asyncpg.Pool,
) -> str:
    """Build layered memory context for the LLM system prompt."""
    parts = []

    # L0: Identity (always)
    identity = await get_summary(pool, user_id, 'identity')
    if identity:
        parts.append(f"[About the user]\n{identity.content}")

    # L1: Book context (if book attached or detected)
    if book_id:
        book_ctx = await get_summary(pool, user_id, 'book', book_id)
        if book_ctx:
            parts.append(f"[Current book context]\n{book_ctx.content}")

    # L2: Relevant triples (entity-based)
    entities = extract_entities_from_text(user_message)
    if entities:
        triples = await search_active_triples(pool, user_id, book_id, entities, limit=20)
        if triples:
            formatted = "\n".join(f"- {t.subject} {t.predicate} {t.object}" for t in triples)
            parts.append(f"[Known facts]\n{formatted}")

    # L3: Semantic search (if L2 thin)
    if len(parts) < 3:
        drawers = await vector_search_drawers(pool, user_id, book_id, user_message, limit=5)
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
    book_id: str | None,
    user_message: str,
    assistant_message: str,
    message_id: str,
    pool: asyncpg.Pool,
):
    """Background task: extract memories from conversation turn."""
    combined = f"User: {user_message}\nAssistant: {assistant_message}"

    # Pattern-based memory extraction (no LLM)
    memories = extract_memories(combined)
    for mem in memories:
        await upsert_drawer(pool, user_id, book_id, mem.room, mem.hall, mem.content, message_id)

    # Entity + triple extraction (no LLM)
    triples = extract_triples(combined)
    for triple in triples:
        await upsert_triple(pool, user_id, book_id, triple, message_id)
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

## 7. Embedding Strategy

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

## 8. Summary Regeneration

L0 and L1 summaries become stale as conversations accumulate. Regeneration strategy:

| Scope | Trigger | Method |
|---|---|---|
| Identity (L0) | Every 50 conversation turns | LLM summarization (cheap, infrequent) |
| Book (L1) | Every 20 turns about the book | LLM summarization from latest triples + drawers |
| Character | On glossary update or every 30 mentions | Compile from triples |
| Session | On session archive | Compile from drawers for that session |

Regeneration is a background job — never blocks the chat flow.

---

## 9. Implementation Phases

| Phase | Scope | Effort | Dependencies |
|---|---|---|---|
| **P1** | Postgres schema + migrations | Small | pgvector extension |
| **P2** | Pattern-based extractor (triples + drawers from chat) | Medium | P1 |
| **P3** | Context builder (L0-L3 injection into LLM calls) | Medium | P1, P2 |
| **P4** | Glossary sync (auto-populate from existing data) | Small | P1 |
| **P5** | Book content mining (chapter text → drawers) | Medium | P1 |
| **P6** | Embedding pipeline (pgvector semantic search for L3) | Medium | P1, embedding model |
| **P7** | Summary regeneration (L0/L1 periodic refresh) | Medium | P3, P6 |
| **P8** | Tool calling integration (memory tools for LLM) | Medium | P3 |
| **P9** | Memory UI (view/edit/delete memories, timeline) | Large | P1-P3 |

**MVP (P1-P3):** Pattern-based extraction + L0-L2 context loading. No embeddings needed. The AI gets structured memory without any LLM cost for extraction.

**Full system (P1-P8):** Adds semantic search (L3), book mining, glossary sync, summary regeneration, and LLM tool access to memory.

---

## 10. Cost Analysis

| Approach | Tokens per turn | Annual cost (100 turns/day) |
|---|---|---|
| Current (50 messages replay) | ~5,000 | Baseline |
| Memory L0+L1 only | ~250 | **95% reduction** |
| Memory L0+L1+L2 | ~550 | **89% reduction** |
| Memory L0+L1+L2+L3 | ~1,050 | **79% reduction** |

Extraction cost: **$0** (pattern-based, no LLM calls).
Summary regeneration: ~$0.50/month (infrequent LLM calls for L0/L1 refresh).

---

## 11. Open Questions

1. **Embedding dimension:** Should we standardize on 1536 (OpenAI compatible) or support variable dimensions per user model?
2. **Conflict resolution:** When a new triple contradicts an old one, auto-invalidate the old one? Or flag for user review?
3. **Cross-book entities:** How to handle a character that appears in multiple books (tunnel concept)?
4. **Privacy scope:** Should memory be per-user only, or support shared memories for collaborative projects?
5. **Memory retention:** Should memories have a TTL, or persist indefinitely until invalidated?
6. **Chat history cutoff:** Once memory is active, reduce the message replay from 50 to 10-20? (Memory provides the deep context, recent messages provide the conversation flow.)

---

*Created: 2026-04-12 — LoreWeave session 34*
