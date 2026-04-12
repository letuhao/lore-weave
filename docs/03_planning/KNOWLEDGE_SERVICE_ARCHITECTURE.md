# Knowledge Service Architecture

> **Status:** Design draft — extends the Data Re-Engineering Plan
> **Created:** 2026-04-12 (session 34) — originally as Memory Service, merged into Knowledge Service 2026-04-13
>
> **This document extends:**
> - [`101_DATA_RE_ENGINEERING_PLAN.md`](101_DATA_RE_ENGINEERING_PLAN.md) — the polyglot persistence architecture, event pipeline, Neo4j schema, and phased implementation plan that this document builds upon
> - [`102_DATA_RE_ENGINEERING_DETAILED_TASKS.md`](102_DATA_RE_ENGINEERING_DETAILED_TASKS.md) — the detailed task breakdown for Phase D1 (schema + events) that establishes the foundation we consume
>
> **Scope of this document:** chat memory features, L0-L3 context stack, memory UI,
> project-scoped memory model, pattern-based extraction. All infrastructure (Postgres 18,
> Neo4j v2026.01, outbox pattern, event pipeline, worker-infra) is defined in 101/102.

---

## Acknowledgments & Inspiration

This architecture draws from several open-source projects and industry research.
We give proper credit to the work that influenced our design.

### MemPalace

**Project:** [MemPalace](https://github.com/MemPalace/mempalace) by the MemPalace team
**License:** MIT
**Version studied:** 3.1.0 (April 2026)

MemPalace is an open-source, local-first AI memory system that achieved 96.6% on the
LongMemEval benchmark. Several concepts in this document are directly inspired by
MemPalace's design:

| Concept borrowed | MemPalace origin | Our adaptation |
|---|---|---|
| Palace hierarchy (wings/rooms/halls) | Hierarchical memory organization | Project=Wing, Topic/Character=Room, Fact type=Hall |
| Verbatim storage over summarization | Raw drawers in ChromaDB | Raw drawers in Postgres + Neo4j vectors |
| L0-L3 lazy-loaded memory stack | 4-layer token-budgeted retrieval | Same concept, adapted for Postgres SSOT + Neo4j derived |
| Pattern-based extraction (no LLM) | `general_extractor.py` regex patterns | Fast first-pass extraction, runs alongside LLM extraction |
| Two-pass entity detection | `entity_detector.py` candidate → scoring | Same approach for entity detection |
| Temporal knowledge graph | SQLite triples with valid_from/valid_to | Neo4j edges with temporal properties |
| Exchange-pair chunking | `convo_miner.py` Q+A units | Same chunking strategy for chat mining |

We chose to **reimplement from scratch** rather than fork because:
- MemPalace is SQLite + ChromaDB (local, single-user)
- LoreWeave is Postgres + Neo4j (cloud, multi-user)
- Only ~18% of MemPalace code is portable; the rest is storage-layer specific
- Multi-tenant `user_id` scoping touches every query

We deeply respect the MemPalace team's work.

### Other influences

- **Mem0** ([mem0.ai](https://github.com/mem0ai/mem0)) — memory scoping model (user/session/agent), conflict resolution strategy. Research paper [arXiv:2504.19413](https://arxiv.org/abs/2504.19413).
- **Claude's 3-layer memory** (Anthropic) — distinction between persistent instructions vs persistent memory, project-scoped isolation.
- **ChatGPT Memory** (OpenAI) — editable memory dashboard where users view/edit/delete what the AI remembers.
- **OpenAI Agents SDK** — session trimming, memory distillation, consolidation patterns.

---

## 1. Problem Statement

LoreWeave's current chat-service is a **stateless replay buffer** — it sends the last
50 messages to the LLM on every turn. This has fundamental limitations that affect
all AI-driven features, not just chat:

| Problem | Impact |
|---|---|
| Context window limit | After 50 messages, older context silently dropped |
| No semantic memory | Important decisions buried in noise |
| Linear cost scaling | Every turn re-sends entire history as prompt tokens |
| No cross-session memory | New session = AI knows nothing about user/project |
| No cross-book knowledge reuse | Writing assistant for book B doesn't benefit from book A's lore |
| Model switching loses context | Model B doesn't understand Model A's reasoning |

**The Data Re-Engineering Plan (101)** addresses the infrastructure side:
polyglot Postgres + Neo4j, event-driven extraction, knowledge-service as
the consumer. This document extends that plan with:

1. **Chat memory specifics** — how chat conversations feed into the knowledge graph
2. **L0-L3 context stack** — how knowledge is loaded for each LLM call
3. **Project-scoped memory model** — how chat sessions attach to projects
4. **Memory UI** — how users review/edit/delete their knowledge
5. **Pattern-based extraction** — zero-cost first pass alongside LLM extraction

---

## 2. Relationship to the Data Re-Engineering Plan

### What 101/102 Already Defines

Per [`101_DATA_RE_ENGINEERING_PLAN.md`](101_DATA_RE_ENGINEERING_PLAN.md):

- **Source of truth:** PostgreSQL 18 (app data, content, glossary, outbox)
- **Knowledge layer:** Neo4j v2026.01 (entities, events, relations, vectors)
- **Event bus:** Redis Streams (outbox → consumers)
- **Transactional Outbox pattern:** atomic writes with guaranteed event delivery
- **Two-worker architecture:** `worker-infra` (Go, outbox relay) + `worker-ai` (Python, extraction)
- **knowledge-service** (Python): consumes events, runs extraction, writes to Neo4j
- **Neo4j schema:** `(:Entity)`, `(:Event)`, `(:Chapter)`, `(:Book)` nodes; `:APPEARS_IN`, `:RELATES_TO`, `:PARTICIPATES_IN`, `:CAUSES`, `:HAPPENS_BEFORE` edges
- **Vector indexes:** `entity_embeddings`, `event_embeddings` (1536-dim, cosine)

Phase D3 (Knowledge Pipeline):
- D3-01: Entity extraction (LLM NER + coreference)
- D3-02: Event extraction with temporal ordering
- D3-03: Relation extraction
- D3-04: Fact extraction with provenance
- D3-05: Embedding generation
- D3-06: Glossary-service evolution (reads from Neo4j)

Phase D4 (RAG Integration):
- D4-01: Chunk embedding pipeline
- D4-02: chat-service RAG (hybrid graph + vector query)
- D4-03: Wiki generation from knowledge graph
- D4-04: Timeline generation from events

### What This Document Adds

This document does **not** redefine the infrastructure. It adds chat-memory concerns
that extend the D3/D4 phases:

| New concern | Relates to existing phase |
|---|---|
| Chat turn mining (extract from user/AI conversations) | New: extends D3-01..04 |
| Project-scoped memory (vs book-scoped) | Schema amendment to D2 (Neo4j) and Phase D1 (Postgres) |
| L0-L3 context stack (layered retrieval) | Concretizes D4-02 (chat-service RAG) |
| Pattern-based extractor (cheap first pass) | Complements D3-01..04 (runs in parallel) |
| Memory UI (projects, timeline, entity editor) | New frontend work |
| GDPR erasure + memory toggle | New user-facing controls |

---

## 3. Scope Model — Projects, Sessions, Turns

LoreWeave serves multiple purposes (novel writing, translation, coding, general AI
chat). Memory must be scoped to reflect this — not locked to books.

### 3.1 Four-Level Scope Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ Global Memory (user-wide, cross-project)                    │
│  "User is Vietnamese novelist", "prefers formal prose"      │
│                                                             │
│  ┌───────────────────┐  ┌───────────────────┐              │
│  │ Project A          │  │ Project B          │  ...        │
│  │ "Eastern Sea" book │  │ "Translation Work" │             │
│  │ linked to book_id  │  │ (no book link)     │             │
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

| Scope | Lifetime | What it stores | Example |
|---|---|---|---|
| **Global** | Permanent, cross-project | User identity, preferences, habits | "User is Vietnamese novelist, UTC+7" |
| **Project** | Lives with the project | Domain knowledge, rules, entities | "5 kingdoms, fire magic, Kai is 17" |
| **Session** | Lives with the chat session | Conversation-specific decisions | "Rewriting ch.12, trying approach B" |
| **Turn** | Discarded after response | Recent messages (last 10-20) | Current replay buffer |

Projects are **explicit user-created containers**, matching ChatGPT's Projects pattern.
A project can link to an existing book (`book_id` foreign key) or be standalone.

### 3.2 Project Types

| Type | Example | Glossary sync? | Book content mining? |
|---|---|---|---|
| `book` | "Winds of the Eastern Sea" | Yes (from linked book) | Yes (chapter events) |
| `translation` | "Vietnamese-English xianxia" | Per source glossary | No |
| `code` | "LoreWeave dev" | No | No |
| `general` | "Personal notes" | No | No |

### 3.3 Postgres Additions

These schema additions extend the SSOT layer defined in [`101_DATA_RE_ENGINEERING_PLAN.md` §3](101_DATA_RE_ENGINEERING_PLAN.md). Entities and relations go to Neo4j (per the
original plan); projects and session linkage stay in Postgres for transactional safety.

```sql
-- ═══════════════════════════════════════════════════════════════
-- Projects: explicit containers for scoping knowledge
-- Lives in Postgres (SSOT), not Neo4j
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE knowledge_projects (
    project_id      UUID PRIMARY KEY DEFAULT uuidv7(),   -- PG18 time-ordered UUID
    user_id         UUID NOT NULL REFERENCES users(user_id),
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    project_type    TEXT NOT NULL CHECK (project_type IN ('book', 'translation', 'code', 'general')),
    book_id         UUID REFERENCES books(book_id),      -- optional book link
    instructions    TEXT DEFAULT '',                      -- persistent project instructions (like ChatGPT)
    is_archived     BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_projects_user ON knowledge_projects(user_id) WHERE NOT is_archived;

-- ═══════════════════════════════════════════════════════════════
-- Summaries: compressed context per scope (L0 and L1 layers)
-- Lives in Postgres because it's user-editable and needs transactional updates
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE knowledge_summaries (
    summary_id      UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    scope_type      TEXT NOT NULL CHECK (scope_type IN ('global', 'project', 'session', 'entity')),
    scope_id        UUID,                                 -- project_id, session_id, entity_id, NULL for global
    content         TEXT NOT NULL,
    token_count     INT,
    version         INT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, scope_type, scope_id)
);

-- ═══════════════════════════════════════════════════════════════
-- Session → Project link (column addition to existing chat_sessions)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE chat_sessions ADD COLUMN project_id UUID
    REFERENCES knowledge_projects(project_id) ON DELETE SET NULL;

CREATE INDEX idx_chat_sessions_project ON chat_sessions(project_id) WHERE project_id IS NOT NULL;
```

### 3.4 Neo4j Amendments (project scoping)

Per [`101_DATA_RE_ENGINEERING_PLAN.md` §3.6](101_DATA_RE_ENGINEERING_PLAN.md), entities
are book-scoped (`book_id: String` on every `:Entity`). To support multi-purpose
projects, we amend the schema:

```cypher
// Project node — mirrors Postgres knowledge_projects
(:Project {
  id: String,           // uuidv7 from Postgres
  user_id: String,
  name: String,
  project_type: String, // book, translation, code, general
  book_id: String       // optional, links to (:Book) node
})

// Entity → Project relationship
(:Entity)-[:BELONGS_TO]->(:Project)

// Existing :BELONGS_TO Book relationship kept for book-type projects
(:Entity)-[:BELONGS_TO]->(:Book)  // still valid, project also links to book

// Session node — for session-scoped facts
(:Session {
  id: String,           // chat_sessions.session_id
  user_id: String,
  project_id: String    // optional
})

// Entities can be session-scoped
(:Entity)-[:BELONGS_TO]->(:Session)  // for session-only facts
```

**Query pattern for L2 context loading (triples):**

```cypher
MATCH (e:Entity)-[r:RELATES_TO]->(target)
WHERE e.user_id = $user_id
  AND (
    (e)-[:BELONGS_TO]->(:Project {id: $project_id})
    OR (e.user_id = $user_id AND NOT (e)-[:BELONGS_TO]->(:Project))  // global entities
  )
  AND e.name IN $detected_entities
  AND r.valid_until IS NULL
RETURN e, r, target
```

---

## 4. Memory Stack (L0–L3)

Inspired by MemPalace's lazy-loaded layer system. Each layer has a token budget and
trigger condition. All read paths go through the knowledge-service context builder.

### 4.0 Layer 0 — Global Identity (always loaded, ~50 tokens)

**Source:** `knowledge_summaries WHERE user_id=$1 AND scope_type='global'` (Postgres)

**Content example:**
```
Vietnamese novelist. Writes fantasy and sci-fi. Prefers formal prose style.
Working on "The Three Kingdoms" series. Timezone UTC+7.
```

**When loaded:** Every LLM call through any AI service.

**Populated by:** Background consolidation job or manual edit via memory UI.

### 4.1 Layer 1 — Project Context (loaded when session has project, ~200 tokens)

**Source:**
- Static: `knowledge_projects.instructions` (Postgres, user-editable)
- Dynamic: `knowledge_summaries WHERE scope_type='project' AND scope_id=$project_id`

**Content examples:**

```
[Book project]
Project: "Winds of the Eastern Sea" (fantasy, 45 chapters).
Protagonist Kai (17, fire elemental) trained by Master Lin (deceased ch.12).
Magic system: five elements, unlocked by emotional triggers.
Current arc: Kai infiltrating Water Kingdom. Antagonist Empress Yun.
Instructions: Formal prose style. Avoid modern idioms.
```

```
[Translation project]
Project: Vietnamese→English xianxia translation.
Preserve cultural terms (dao, qi, jianghu), footnote first mentions.
Never localize character names. Keep Chinese honorifics.
```

**When loaded:** When the chat session has `project_id` set.

### 4.2 Layer 2 — Relevant Facts (on-demand, ~300 tokens)

**Source:** Neo4j graph traversal filtered by entities detected in the user message.

This is where **Neo4j's graph-native queries** shine. Main-character queries often
need 2-hop traversal (Kai's enemies' allies, relationships of related entities),
which Postgres handles poorly. See [`101_DATA_RE_ENGINEERING_PLAN.md` §3.7](101_DATA_RE_ENGINEERING_PLAN.md)
for the hybrid graph + vector query pattern.

**Query logic:**

1. Extract entity names from user message (pattern-based, no LLM — see §5.1)
2. Cypher query: 1-hop direct facts + 2-hop contextual facts
3. Format as compact fact list with temporal markers

**Cypher example:**

```cypher
// 1-hop: direct facts about Kai
MATCH (kai:Entity {name: 'Kai'})-[r:RELATES_TO]->(target)
WHERE kai.user_id = $user_id
  AND (kai)-[:BELONGS_TO]->(:Project {id: $project_id})
  AND r.valid_until IS NULL
RETURN 'Kai' AS subject, r.type AS predicate, target.name AS object, r.valid_from

UNION

// 2-hop: Kai's allies' loyalties (context)
MATCH (kai:Entity {name: 'Kai'})-[:RELATES_TO {type: 'ally'}]->(ally)
      -[r2:RELATES_TO]->(target)
WHERE kai.user_id = $user_id
  AND r2.type IN ['loyal_to', 'enemy_of', 'member_of']
  AND r2.valid_until IS NULL
RETURN ally.name AS subject, r2.type AS predicate, target.name AS object, r2.valid_from
```

**Content example (user mentions "Kai" and "Water Kingdom"):**
```
Known facts:
- Kai is a fire elemental (since ch.1)
- Kai is infiltrating Water Kingdom (since ch.38)
- Kai's cover identity: merchant's apprentice (since ch.38)
- Water Kingdom capital: Hailong City
- Empress Yun rules Water Kingdom
- Kai killed Commander Zhao in ch.35 (Water Kingdom unaware)
- [2-hop] Kai's ally Lin was secretly loyal to the Sixth Element order
```

**When loaded:** When the user message contains recognized entity names.

### 4.3 Layer 3 — Deep Semantic Search (on-demand, ~500 tokens)

**Source:** Neo4j native vector search over `entity_embeddings` and `event_embeddings`
indexes (defined in [`101_DATA_RE_ENGINEERING_PLAN.md` §3.6](101_DATA_RE_ENGINEERING_PLAN.md)),
plus drawer chunks from chat/book content.

**Cypher example (hybrid filtered vector search):**

```cypher
CALL db.index.vector.queryNodes('entity_embeddings', 10, $query_embedding)
YIELD node, score
WHERE node.user_id = $user_id
  AND (node)-[:BELONGS_TO]->(:Project {id: $project_id})
  AND score > 0.7
RETURN node.name, node.description, score
ORDER BY score DESC LIMIT 5
```

**When loaded:** When L2 returns fewer than 3 relevant facts, or when the user asks a
broad question ("what happened in the early chapters?").

### Token Budget Summary

| Layer | Tokens | Trigger | Source |
|---|---|---|---|
| L0 | ~50 | Always | Postgres `knowledge_summaries` (global) |
| L1 | ~200 | Session has project | Postgres `knowledge_projects` + `knowledge_summaries` (project) |
| L2 | ~300 | Entities detected | Neo4j graph traversal (1-hop + 2-hop) |
| L3 | ~500 | L2 insufficient | Neo4j vector search + drawer chunks |
| **Total** | **~200–1050** | | vs ~5000 for 50-message replay |

---

## 5. Extraction Pipeline

The knowledge-service extraction pipeline runs **two passes** for best cost/quality
tradeoff:

1. **Pass 1 — Pattern-based (fast, free)** — catches obvious facts immediately
2. **Pass 2 — LLM-based (slower, accurate)** — runs async in background, corrects and supplements

Both passes go through the **entity resolution layer** (§5.0) before writing to Neo4j.
Both passes must follow the **idempotency rules** defined in [`101 §3.5.4`](101_DATA_RE_ENGINEERING_PLAN.md).

### 5.0 Entity Resolution (Canonicalization + Alias Handling)

The same entity can be extracted from multiple sources with different surface forms:
- **Glossary-service:** user manually creates "Kai" with description
- **Book mining (D3-01):** LLM extracts "Master Kai" from chapter text
- **Chat mining (K5):** pattern extractor finds "kai" in a chat turn
- **Pass 2 LLM:** refines "the protagonist" → "Kai"

All four refer to the **same entity**. Without explicit resolution, Neo4j ends up
with duplicate nodes and fragmented relationships.

#### Canonicalization Function

```python
import hashlib
import re

HONORIFICS = {
    "master ", "lord ", "lady ", "sir ", "dame ", "mr. ", "mrs. ", "ms. ",
    "dr. ", "prof. ", "captain ", "commander ", "general ", "shifu ", "sensei ",
    "-shifu", "-sensei", "-sama", "-san", "-kun",
}

def canonicalize_entity_name(name: str) -> str:
    """Normalize an entity name for deduplication matching.

    The canonical form is used to generate deterministic IDs. The original
    name is preserved as the primary display name, and any other spellings
    seen later are added to the `aliases` list.
    """
    normalized = name.strip().lower()

    # Strip honorifics (prefix and suffix)
    for h in HONORIFICS:
        if normalized.startswith(h):
            normalized = normalized[len(h):]
        if normalized.endswith(h):
            normalized = normalized[: -len(h)]

    # Collapse whitespace, strip punctuation (except apostrophes in names like O'Neill)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^\w\s']", "", normalized)

    return normalized.strip()


def entity_canonical_id(
    user_id: str,
    project_id: str | None,
    name: str,
    kind: str,
    canonical_version: int = 1,
) -> str:
    """Deterministic ID for an entity — same canonical name + kind = same node.

    Scoped by user_id + project_id for multi-tenant isolation. Version suffix
    lets us migrate entity IDs when canonicalization rules change.
    """
    canonical = canonicalize_entity_name(name)
    key = f"v{canonical_version}:{user_id}:{project_id or 'global'}:{kind}:{canonical}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]
```

**Example:**

| Input name | Canonical | ID (sha256, truncated) |
|---|---|---|
| "Kai" | `kai` | `a3f2...` |
| "Master Kai" | `kai` | `a3f2...` (same!) |
| "kai-shifu" | `kai` | `a3f2...` (same!) |
| "KAI" | `kai` | `a3f2...` (same!) |
| "Kai the Flame" | `kai the flame` | `b891...` (different — sub-identity) |

#### Upsert Pattern (Cypher)

Every entity write goes through this pattern:

```cypher
MERGE (e:Entity {id: $canonical_id})
ON CREATE SET
  e.user_id = $user_id,
  e.project_id = $project_id,
  e.name = $display_name,              // original, preserving case
  e.kind = $kind,
  e.aliases = [$display_name],
  e.canonical_version = 1,
  e.source_types = [$source_type],     // book_content, chat, glossary, manual
  e.confidence = $confidence,
  e.created_at = datetime()
ON MATCH SET
  // Add new spelling to aliases if unseen
  e.aliases = CASE
    WHEN $display_name IN e.aliases THEN e.aliases
    ELSE e.aliases + $display_name
  END,
  // Track which sources have mentioned this entity
  e.source_types = CASE
    WHEN $source_type IN e.source_types THEN e.source_types
    ELSE e.source_types + $source_type
  END,
  // Confidence uses a max across sources
  e.confidence = CASE WHEN $confidence > e.confidence THEN $confidence ELSE e.confidence END,
  e.updated_at = datetime()
RETURN e
```

#### Conflict Resolution (properties disagree across sources)

When multiple sources set different values for the same property (e.g., age):

| Scenario | Resolution |
|---|---|
| Glossary (user-curated) vs LLM extraction | **User-curated wins.** Store LLM suggestion in `disputed_properties` for user review. |
| Two LLM extractions disagree | **Higher-confidence wins.** If tied, most recent wins. |
| Pattern extraction (Pass 1) vs LLM (Pass 2) | **LLM wins.** Pattern extraction is a placeholder until Pass 2 catches up. |
| Temporal facts (age over time) | **Both preserved** with `valid_from`/`valid_until` windows. |

#### Provenance Preservation

Even after merging, every fact tracks its source. When a user asks "where did you
learn this?", we can answer:

```cypher
MATCH (e:Entity {id: $entity_id})-[r:EXTRACTED_FROM]->(source)
RETURN source, r.extracted_at, r.model, r.confidence
ORDER BY r.extracted_at DESC
```

Sources include `(:Chapter)`, `(:ChatMessage)`, `(:GlossaryEntry)`, `(:ManualEntry)`.

#### When Canonicalization Rules Change

The `canonical_version` field lets us migrate entity IDs safely:

1. Bump `CANONICAL_VERSION` constant in knowledge-service
2. Run the §3.8.3 rebuild procedure with the new version
3. Old entities with `canonical_version: 1` get recomputed IDs under `canonical_version: 2`
4. `MERGE` behavior: new ID matches nothing → creates new node with merged data
5. Delete old `canonical_version: 1` entities after rebuild completes

This is a rare operation but critical for long-term evolution (new honorifics,
language support, etc.).

---

### 5.1 Pattern-Based Extractor (Pass 1)

**Inspired by MemPalace's `general_extractor.py`.** Runs synchronously in the
knowledge-service event consumer. Zero LLM cost.

**Memory types detected by regex patterns:**

| Type | Markers (examples) | Neo4j label / property |
|---|---|---|
| Decision | "let's use", "we decided", "instead of", "trade-off" | `(:Fact {type:'decision'})` |
| Preference | "I prefer", "always use", "never use", "my rule is" | `(:Fact {type:'preference'})` |
| Milestone | "it works", "fixed", "breakthrough", "finished chapter N" | `(:Fact {type:'milestone'})` |
| Entity | Capitalized proper nouns, quoted names, glossary matches | `(:Entity)` |
| Relation | SVO patterns: "Kai killed Zhao", "Lin trained Kai" | `(:Entity)-[:RELATES_TO]->(:Entity)` |
| Event | "in chapter N", "after the battle", "when X happened" | `(:Event)` |

**Entity extraction:** Two-pass system (MemPalace pattern):

1. **Candidate extraction** — capitalized words, quoted names, known glossary entities, repeated noun phrases
2. **Signal scoring** — frequency, position in sentence, co-occurrence with verbs, matches existing entities

**Triple extraction:** Pattern matching on SVO sentences:
- `Kai killed Commander Zhao` → `(Kai)-[:killed]->(Commander Zhao)`
- `The capital is Hailong City` → `(Water Kingdom)-[:has_capital]->(Hailong City)`
- `We decided to use fire magic` → `(:Fact {type:'decision', content:'use fire magic'})`

### 5.2 LLM-Based Extractor (Pass 2)

**Defined in [`101_DATA_RE_ENGINEERING_PLAN.md` Phase D3](101_DATA_RE_ENGINEERING_PLAN.md) (D3-01 to D3-04).**

Runs asynchronously via worker-ai. Takes longer but extracts nuanced relationships,
resolves coreferences, merges entity variants, and produces higher-confidence facts.

The two passes complement each other:
- Pass 1 gives **immediate** context (the user sees results in the next chat turn)
- Pass 2 **corrects and enriches** Pass 1 within seconds (background)
- Facts from Pass 2 can override or merge with Pass 1 facts (`confidence` field disambiguates)

### 5.3 Event Consumers

The knowledge-service subscribes to multiple outbox event streams:

| Event | Source | What it triggers |
|---|---|---|
| `chapter.saved` | book-service | Pattern + LLM extraction over chapter text (Phase D3-01..05, already planned) |
| `chapter.deleted` | book-service | Invalidate entities tied only to this chapter |
| `chat.turn_completed` | chat-service (new event) | Pattern extraction over user+assistant message pair |
| `glossary.entity_updated` | glossary-service | Sync user-curated entities to Neo4j |
| `knowledge.summary_stale` | scheduled job | Regenerate L0/L1 summaries (~every 20 turns) |

**Chat turn mining (new, extends D3 phase):**

1. chat-service streams response to user
2. On stream completion, chat-service writes an outbox event `chat.turn_completed`
3. worker-infra relays event to Redis Stream
4. knowledge-service consumes event, reads full turn from Postgres
5. Runs pattern extractor → emits facts to Neo4j immediately
6. Schedules LLM extraction (worker-ai, lower priority)

---

## 6. Knowledge-Service API

### 6.1 Internal API (service-to-service, `X-Internal-Token` auth)

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
  "token_count": 487
}
```

#### `POST /internal/extract/chat-turn`

Extract knowledge from a completed chat turn. Triggered by `chat.turn_completed`
event, also exposed as an API for ad-hoc reprocessing.

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

**Response:** `202 Accepted` (extraction runs asynchronously)

#### Other internal endpoints

Existing from the original plan:
- `POST /internal/extract/chapter` (D3-01, chapter mining)
- `POST /internal/embed` (D3-05, proxy to provider-registry)
- `POST /internal/summarize` (L0/L1 regeneration)

### 6.2 Public API (user-facing, JWT auth via api-gateway-bff)

Exposed at `/v1/knowledge/*` through the gateway.

#### Projects

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/knowledge/projects` | List user's projects |
| `POST` | `/v1/knowledge/projects` | Create a project |
| `GET` | `/v1/knowledge/projects/{id}` | Get project details |
| `PATCH` | `/v1/knowledge/projects/{id}` | Update name, description, instructions |
| `DELETE` | `/v1/knowledge/projects/{id}` | Delete project (cascade) |
| `POST` | `/v1/knowledge/projects/{id}/archive` | Archive a project |

#### Knowledge (read/write)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/knowledge/summaries` | L0 (global) and L1 (per project) summaries |
| `GET` | `/v1/knowledge/entities?project_id=...` | List entities scoped to project |
| `GET` | `/v1/knowledge/entities/{id}` | Entity detail with all relations |
| `GET` | `/v1/knowledge/relations?subject=...&project_id=...` | Query relations by subject/object |
| `GET` | `/v1/knowledge/timeline?project_id=...&from=...&to=...` | Events in chronological order |
| `POST` | `/v1/knowledge/remember` | Manual knowledge entry |
| `DELETE` | `/v1/knowledge/entities/{id}` | Forget an entity |
| `POST` | `/v1/knowledge/relations/{id}/invalidate` | Mark a relation as no longer valid |
| `DELETE` | `/v1/knowledge/user-data` | GDPR erasure |

---

## 7. Integration with chat-service

### 7.1 Context Builder Call (before LLM)

```python
# In chat-service stream_service.py — add before LLM call
async def build_system_prompt(session, user_message):
    base_prompt = session.system_prompt or ""

    try:
        resp = await knowledge_client.post("/internal/context/build", json={
            "user_id": session.owner_user_id,
            "project_id": session.project_id,
            "session_id": session.session_id,
            "message": user_message,
            "layers": ["L0", "L1", "L2", "L3"],
            "token_budget": 1050,
        })
        context = resp.json()["context"]
        return f"{base_prompt}\n\n{context}" if context else base_prompt
    except (httpx.RequestError, httpx.HTTPStatusError):
        # Graceful degradation — knowledge-service down, fall back to plain prompt
        logger.warning("knowledge-service unavailable, skipping memory context")
        return base_prompt
```

### 7.2 Chat Turn Event (after LLM)

After the assistant message is persisted, chat-service writes an outbox event:

```python
# In chat-service stream_service.py — after assistant message insert
await conn.execute(
    """
    INSERT INTO outbox_events (event_type, aggregate_id, payload)
    VALUES ('chat.turn_completed', $1, $2::jsonb)
    """,
    message_id,
    json.dumps({
        "user_id": user_id,
        "project_id": session.project_id,
        "session_id": session_id,
        "message_id": message_id,
        "user_message_id": user_msg_id,
    }),
)
```

worker-infra relays this to Redis Streams → knowledge-service consumes → runs
pattern extraction → schedules LLM extraction. Chat-service never waits on this.

### 7.3 Graceful Degradation with Timeouts & Circuit Breaker

chat-service **must not crash or stall** if knowledge-service is slow or unavailable.
Three protection layers:

**Layer 1: Layer-level timeouts (best-effort return)**

Context building asks knowledge-service for L0-L3 with individual budgets:

```python
LAYER_TIMEOUTS = {
    "L0": 0.1,   # 100ms — Postgres read
    "L1": 0.1,   # 100ms — Postgres read
    "L2": 0.2,   # 200ms — Neo4j graph traversal (1-hop + 2-hop)
    "L3": 0.2,   # 200ms — Neo4j filtered vector search
}
TOTAL_BUDGET = 0.5  # 500ms total ceiling

async def build_context_with_timeouts(user_id, project_id, session_id, message):
    parts = []
    deadline = time.monotonic() + TOTAL_BUDGET

    for layer in ["L0", "L1", "L2", "L3"]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break  # Budget exhausted — skip remaining layers
        try:
            result = await asyncio.wait_for(
                fetch_layer(layer, user_id, project_id, session_id, message),
                timeout=min(LAYER_TIMEOUTS[layer], remaining),
            )
            if result:
                parts.append(result)
        except asyncio.TimeoutError:
            metrics.inc("knowledge_layer_timeout", layer=layer)
            continue  # Don't block — skip this layer, try the next

    return "\n\n".join(parts)
```

**Layer 2: Cache for hot data**

L0 (global identity) and L1 (project context) change rarely — cache them in
chat-service memory with short TTL:

```python
# In-process LRU cache, 60s TTL
_l0_cache: TTLCache = TTLCache(maxsize=1000, ttl=60)
_l1_cache: TTLCache = TTLCache(maxsize=1000, ttl=60)

async def get_l0(user_id):
    if user_id in _l0_cache:
        return _l0_cache[user_id]
    value = await knowledge_client.get_global_summary(user_id)
    _l0_cache[user_id] = value
    return value
```

Cache invalidation: when the user edits their identity via memory UI, emit a
`knowledge.summary_invalidated` event. chat-service subscribes and evicts the cache.

**Layer 3: Circuit breaker for total outages**

If knowledge-service fails 3 consecutive calls, open the circuit for 60 seconds.
During open state, chat-service skips memory context entirely and returns a normal
LLM response. After 60s, a single probe call determines whether to close the circuit.

```python
from purgatory import CircuitBreaker  # or any Python circuit breaker library

knowledge_cb = CircuitBreaker(
    fail_max=3,
    timeout_duration=60,
    expected_exception=(httpx.RequestError, httpx.HTTPStatusError, asyncio.TimeoutError),
)

async def build_system_prompt(session, user_message):
    base_prompt = session.system_prompt or ""
    try:
        async with knowledge_cb:
            context = await build_context_with_timeouts(
                session.owner_user_id,
                session.project_id,
                session.session_id,
                user_message,
            )
            return f"{base_prompt}\n\n{context}" if context else base_prompt
    except CircuitBreakerError:
        metrics.inc("knowledge_circuit_open")
        return base_prompt  # Circuit open — degrade gracefully
    except Exception as e:
        logger.warning(f"knowledge-service error: {e}, falling back")
        return base_prompt
```

**Observability:** every degradation path increments a metric. Prometheus alerts
fire when `knowledge_circuit_open` / `knowledge_layer_timeout` exceed a threshold,
indicating an operational issue.

### 7.4 Raw Messages vs Derived Knowledge — Invariants

A critical invariant for trust and GDPR compliance:

> **Raw `chat_messages` and `chapter_drafts` are the source of truth.
> Neo4j knowledge is always a derived view, never primary data.**

**Rules:**

1. **Raw data is preserved unchanged.** Memory extraction never modifies or deletes
   raw messages/chapters. Users always have a complete record of what they said.
2. **Memory is derivative.** Every `(:Fact)`, `(:Entity)`, `(:Event)` in Neo4j has
   a provenance edge back to its source (`message_id`, `chapter_id`, `glossary_entity_id`).
3. **Deletion cascades:** when raw data is deleted, derived memory is invalidated.
   See [`101 §3.8.4`](101_DATA_RE_ENGINEERING_PLAN.md) for the cascade matrix.
4. **No silent paraphrasing.** Knowledge-service never rewrites user content into
   facts that differ from what the user actually said. Extraction adds metadata
   ("Kai killed Zhao"), it does not replace source content.
5. **User visibility:** the memory UI shows provenance for every fact. Clicking
   a fact shows the source message/chapter it came from. Users can audit what
   the AI "knows" and why.
6. **GDPR erasure:** deleting a user (via `DELETE /v1/knowledge/user-data`) removes
   both raw and derived data atomically. Events flow: Postgres delete → outbox
   event → Neo4j cascade. Completion verified by a consistency check job.

**Practical consequence for chat history cutoff:** even when memory provides
L0-L3 context, we **keep the last 20 raw messages** in the LLM prompt. Memory
provides depth; recent messages provide conversational flow. Users never see
"the AI forgot what I just said 5 seconds ago."

---

## 8. Memory UI (Power-User Feature)

Memory UI is a **power-user feature**. Most users just want memory to work without
touching it. Only power users care about inspecting/editing the knowledge store.

### 8.1 Design Principles

1. **Hidden by default** — no top-level nav item. Accessed via Settings → Advanced → Memory.
2. **Minimal cognitive load** — power users can dive in; regular users never see it.
3. **Read-first, edit-second** — viewing should be easy, editing deliberate.
4. **No surprises for normal users** — if they never touch the UI, memory still works.

### 8.2 For Normal Users (99%)

**Settings → Privacy → "AI Memory" section:**

```
[ ] Enable AI Memory
    When enabled, your AI assistants remember things across conversations.
    Your data stays private — view or delete anytime.
    [View my memory]  [Delete all memory]
```

One toggle, two buttons. The toggle maps to a `user_preferences.memory_enabled` flag
checked by knowledge-service.

### 8.3 For Power Users (1%)

Accessed via Settings → Advanced → Memory, or the "View my memory" button.

**Tabs:**

| Tab | Purpose |
|---|---|
| **Global** | Edit L0 identity summary, list global preferences, "Regenerate" / "Reset" actions |
| **Projects** | Sidebar of projects, main panel shows project instructions (editable), summary, token budget, archive/delete |
| **Timeline** | Temporal view of facts/events, filter by project/entity/date, invalidate/edit/delete per row |
| **Entities** | Table of entities (characters, places, concepts), drill down to relations + drawers, edit aliases/properties |
| **Raw** | Drawer list with search (vector), delete individual memories |

### 8.4 Chat Page Integration

A subtle indicator in the chat header shows when memory is active. Clicking opens a
popover with the session's project, fact count, and a link to the memory UI for that
project.

### 8.5 Frontend Structure

```
frontend/src/features/knowledge/
  ├── pages/
  │   └── KnowledgePage.tsx            ← routed at /knowledge (power-user only)
  ├── components/
  │   ├── KnowledgeTabs.tsx
  │   ├── GlobalTab.tsx
  │   ├── ProjectsTab.tsx
  │   ├── TimelineView.tsx
  │   ├── EntitiesTable.tsx
  │   ├── DrawersViewer.tsx
  │   ├── MemoryToggle.tsx             ← simple toggle for Settings → Privacy
  │   └── SessionMemoryIndicator.tsx   ← chat header brain icon + popover
  ├── api.ts                           ← /v1/knowledge/* client
  └── types.ts
```

---

## 9. Implementation Phases

These phases extend [`101_DATA_RE_ENGINEERING_PLAN.md` §4](101_DATA_RE_ENGINEERING_PLAN.md)
with chat-memory specific work. Dependencies on D1/D2/D3 are called out explicitly.

| Phase | Scope | Effort | Dependencies |
|---|---|---|---|
| **K0** | knowledge-service scaffold: FastAPI app, Dockerfile, docker-compose, internal-token auth, health check | S | D1 (Postgres 18, Redis) |
| **K1** | Postgres additions: `knowledge_projects`, `knowledge_summaries`, `chat_sessions.project_id` column | S | K0 |
| **K2** | Neo4j schema amendments: `(:Project)` and `(:Session)` nodes, `BELONGS_TO` edges, indexes | S | D2 (Neo4j live) |
| **K3** | Pattern-based extractor: port MemPalace patterns, entity detector, triple extractor | M | K0 |
| **K4** | Chat turn event: chat-service writes `chat.turn_completed` outbox event | S | D1 outbox |
| **K5** | Event consumer: knowledge-service subscribes to `chat.turn_completed`, runs K3 extractor | M | K3, K4 |
| **K6** | Context builder API: `/internal/context/build`, L0-L3 assembly, token budget enforcement | M | K2, K5 |
| **K7** | chat-service integration: call `build_context` before LLM, graceful degradation on failure | S | K6 |
| **K8** | Public API: `/v1/knowledge/projects` CRUD, gateway proxy routes | M | K1 |
| **K9** | Memory toggle in Settings → Privacy (frontend) | S | K8 |
| **K10** | Full memory UI: projects tab, timeline, entities, drawers (power-user) | L | K8 |
| **K11** | Summary regeneration: scheduled job, LLM-assisted L0/L1 refresh | M | K6, D3-05 (embeddings) |
| **K12** | LLM extraction integration: Pass 2 runs alongside Pass 1 (reuses D3-01..04) | M | K5, D3-01..04 |
| **K13** | Tool calling integration: expose knowledge tools to LLMs via chat-service tool loop | M | K6 |

**Prerequisites from 101/102 that must be done first:**
- D0: Pre-flight validation (PG18 + JSON_TABLE + pgx)
- D1: Postgres 18 + outbox + events DB + worker-infra *(partially done)*
- D2: Neo4j deployment *(not started)*
- D3-01..05: Base LLM extraction for chapters *(not started)*

**MVP chat memory (K0-K7):** Pattern-based extraction + L0-L2 context loading. No LLM
extraction needed yet (Pass 1 only). Users get structured memory with minimal cost.

**Full chat memory (K0-K13):** Adds UI, L3 semantic search, summary regen, LLM extraction,
and tool calling.

### Order of Operations

```
Prerequisites (from 101/102):
  D0 → D1 → D2
              ↓
Chat memory (this doc):
  K0 → K1 → K2 → K3 → K4 → K5 → K6 → K7  (MVP)
                                       ↓
                                      K8 → K9 → K10  (UI)
                                      K11             (regeneration)
                                      K12             (LLM extraction pass 2)
                                      K13             (tool calling)
```

---

## 10. Cost Analysis

| Approach | Tokens per turn | Annual cost (100 turns/day) |
|---|---|---|
| Current (50 messages replay) | ~5,000 | Baseline |
| Memory L0+L1 only | ~250 | **95% reduction** |
| Memory L0+L1+L2 | ~550 | **89% reduction** |
| Memory L0+L1+L2+L3 | ~1,050 | **79% reduction** |

**Extraction cost:**
- Pattern-based (Pass 1): **$0** per turn
- LLM-based (Pass 2): ~$0.001 per turn for small model (runs async, non-blocking)
- Summary regeneration: ~$0.50/month per active user (infrequent)

---

## 11. Open Questions

**Answered by data engineer review (2026-04-13):**

- ~~**Embedding dimension / BYOK:**~~ Resolved by [`101 decision #27`](101_DATA_RE_ENGINEERING_PLAN.md).
  Server-chosen embedding model (`BAAI/bge-m3` or `intfloat/multilingual-e5-large`,
  1024-dim, self-hosted). No BYOK for embeddings. LLMs stay BYOK.

- ~~**Pass 1 vs Pass 2 conflict resolution:**~~ Resolved in §5.0 conflict resolution
  table. LLM (Pass 2) wins over pattern (Pass 1); glossary (user-curated) wins over LLM.

- ~~**Chat history cutoff when memory is active:**~~ Resolved in §7.4 invariants.
  Keep last 20 raw messages in the prompt; memory adds depth on top.

**Still open:**

1. **Cross-project entities:** A character appearing in multiple books (shared
   universe). Current answer: duplicate per project (entity ID includes `project_id`).
   Alternative: "global" entity linked via `ALSO_KNOWN_AS` edges to per-project nodes.
   Revisit when we have a real user with multi-book series.

2. **Session-to-project promotion:** Unassigned sessions accumulate session-level
   knowledge. Should the system auto-suggest creating a project after N turns? Or
   auto-promote high-confidence facts to global memory?

3. **Default "Personal" project:** Should every user have a default catch-all project,
   or allow truly unscoped sessions (session-level memory only)?

4. **Memory retention:** Should session-level drawers have a TTL (e.g., expire
   after 30 days of inactivity)? Project-level drawers should persist indefinitely.

5. **Memory toggle scope:** When a user disables memory, do we stop writing new
   knowledge, stop reading existing knowledge, or both? Soft-delete or just hide?
   Data engineer recommendation: **stop writing + stop reading + keep existing data**.
   Re-enabling resumes both paths. Data is only deleted via explicit GDPR erasure.

6. **Pattern extraction quality threshold:** Pass 1 will write noisy facts. Should
   we set a minimum confidence threshold (e.g., 0.5) to avoid polluting Neo4j with
   low-quality extractions? Or let Pass 2 clean them up asynchronously?

---

## 12. Related Documents

- [`101_DATA_RE_ENGINEERING_PLAN.md`](101_DATA_RE_ENGINEERING_PLAN.md) — Parent plan: polyglot persistence, Neo4j schema, event pipeline, Phase D1-D4 roadmap
- [`102_DATA_RE_ENGINEERING_DETAILED_TASKS.md`](102_DATA_RE_ENGINEERING_DETAILED_TASKS.md) — Detailed sub-tasks for Phase D1
- [`98_CHAT_SERVICE_DESIGN.md`](98_CHAT_SERVICE_DESIGN.md) — chat-service architecture that this document integrates with
- [`75_PHASE3_MODULE05_GLOSSARY_LORE_EXECUTION_PACK.md`](75_PHASE3_MODULE05_GLOSSARY_LORE_EXECUTION_PACK.md) — Glossary module that this extends for project-scoped knowledge

---

*Created: 2026-04-12 (session 34) as MEMORY_SERVICE_ARCHITECTURE*
*Renamed and restructured: 2026-04-13 (session 34) as KNOWLEDGE_SERVICE_ARCHITECTURE (extension of 101/102)*
