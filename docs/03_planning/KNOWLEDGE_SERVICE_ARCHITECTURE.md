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

### 4.1 Layer 1 — Project Context (loaded when session has project, ~200–400 tokens)

**Source:**
- Static: `knowledge_projects.instructions` (Postgres, user-editable)
- Dynamic: `knowledge_summaries WHERE scope_type='project' AND scope_id=$project_id`
- Optional: top 2–3 user writing samples (for style matching via few-shot learning)

**Content format (XML-tagged, see §4.4 for full structure):**

```xml
<project type="book" name="Winds of the Eastern Sea">
  <description>
    Fantasy, 45 chapters. Protagonist Kai (17, fire elemental) trained by
    Master Lin (deceased ch.12). Magic system: five elements, unlocked by
    emotional triggers. Current arc: Kai infiltrating Water Kingdom.
    Antagonist: Empress Yun. Unresolved: Lin's secret identity, the
    Sixth Element prophecy.
  </description>
  <instructions>
    Formal prose style. Avoid modern idioms. Third-person limited POV.
  </instructions>
  <style_examples>
    <example>The wind carried the scent of pine and distant fires, and Kai knew the hunt had begun.</example>
    <example>Master Lin spoke no words, yet his silence held a thousand unspoken lessons.</example>
  </style_examples>
</project>
```

**Few-shot style examples (Rec #2):**
Project summary alone tells the LLM *what* to write about, but not *how*. Two or
three short excerpts from the user's actual writing (extracted from recent
high-quality chapter content) show the model the prose rhythm, voice, and
vocabulary. Dramatically improves style matching vs. plain instructions.

**Content example — Translation project:**

```xml
<project type="translation" name="Vietnamese-English xianxia">
  <description>
    Source: Vietnamese xianxia web novels. Target: English cultivation-novel
    readers. 47 glossary terms established (dao, qi, jianghu, etc.).
  </description>
  <instructions>
    Preserve cultural terms, footnote first mentions. Never localize character
    names. Keep Chinese honorifics. Formal register.
  </instructions>
  <style_examples>
    <example>His qi surged through the meridians like a coiled dragon awakening from centuries of slumber.</example>
  </style_examples>
</project>
```

**When loaded:** When the chat session has `project_id` set. Style examples are
omitted if the project doesn't need them (coding, general chat).

### 4.2 Layer 2 — Relevant Facts (on-demand, ~300–500 tokens)

**Source:** Neo4j graph traversal filtered by entities detected in the user message,
filtered further by quality threshold (see §5.1 quarantine rules).

This is where **Neo4j's graph-native queries** shine. Main-character queries often
need 2-hop traversal, which Postgres handles poorly. See [`101 §3.7`](101_DATA_RE_ENGINEERING_PLAN.md)
for the hybrid graph + vector query pattern.

**Query logic:**

1. Extract entity names from user message (pattern-based, no LLM — see §5.1)
2. Cypher query: 1-hop direct facts + 2-hop contextual facts, filtered by
   `confidence >= 0.8` (excludes quarantined Pass 1 facts)
3. Rank facts by relevance (subject/object match + temporal proximity to current chapter)
4. Deduplicate against L1 project summary (see §4.4)
5. Group by temporal category (current / recent / background)
6. Format with XML structure

**Cypher example:**

```cypher
// 1-hop: direct facts about Kai (high-confidence only)
MATCH (kai:Entity {name: 'Kai'})-[r:RELATES_TO]->(target)
WHERE kai.user_id = $user_id
  AND (kai)-[:BELONGS_TO]->(:Project {id: $project_id})
  AND r.valid_until IS NULL
  AND r.confidence >= 0.8              // quarantined Pass 1 facts excluded
RETURN 'Kai' AS subject, r.type AS predicate, target.name AS object,
       r.valid_from AS established, r.source_chapter AS chapter, r.confidence

UNION

// 2-hop: Kai's allies' loyalties (contextual)
MATCH (kai:Entity {name: 'Kai'})-[:RELATES_TO {type: 'ally'}]->(ally)
      -[r2:RELATES_TO]->(target)
WHERE kai.user_id = $user_id
  AND r2.type IN ['loyal_to', 'enemy_of', 'member_of']
  AND r2.valid_until IS NULL
  AND r2.confidence >= 0.8
RETURN ally.name AS subject, r2.type AS predicate, target.name AS object,
       r2.valid_from AS established, r2.source_chapter AS chapter, r2.confidence
```

**Formatted output with temporal grouping and negative facts (fixes Issue #2):**

LLMs have a recency bias — facts at the end of a list get more attention weight.
We group facts by temporal category so the model foregrounds what's currently
true, not what the sort order happens to surface.

```xml
<facts>
  <!-- What's true right now — highest attention weight -->
  <current>
    <fact source="ch.38">Kai is infiltrating Water Kingdom</fact>
    <fact source="ch.38">Kai's cover identity: merchant's apprentice</fact>
    <fact source="ch.1" type="trait">Kai is a fire elemental</fact>
    <fact source="ch.1" type="trait">Empress Yun rules Water Kingdom (ice elemental)</fact>
    <fact source="ch.5" type="location">Water Kingdom capital: Hailong City</fact>
  </current>

  <!-- Recent events — for conversational continuity -->
  <recent>
    <fact source="ch.35">Kai killed Commander Zhao</fact>
    <fact source="ch.37">Kai learned Lin was loyal to the Sixth Element order</fact>
  </recent>

  <!-- Background — only when directly needed -->
  <background>
    <fact source="ch.12">Master Lin died</fact>
    <fact source="ch.8">Kai first manifested fire elemental powers</fact>
  </background>

  <!-- What characters DON'T know — critical for consistency (Rec #4) -->
  <negative>
    <fact source="ch.35">Water Kingdom does NOT know Kai killed Commander Zhao</fact>
    <fact source="ch.37">Kai does NOT know why Lin kept the Sixth Element secret</fact>
    <fact source="ch.1">Empress Yun does NOT know Kai is a fire elemental</fact>
  </negative>
</facts>

<instructions>
Before answering, silently note which facts are relevant to the user's question.
Characters can only know what their POV has witnessed. If a character is about to
reveal information listed in &lt;negative&gt;, flag the inconsistency.
</instructions>
```

**Why temporal grouping matters:**
- `<current>` facts are what the model should foreground when writing new content
- `<recent>` provides conversational continuity ("yesterday we discussed...")
- `<background>` is retrieved but deprioritized (last attention weight)
- `<negative>` prevents the LLM from having characters reveal things they shouldn't know

**CoT anchoring (Rec #3):**
The `<instructions>` block forces the model to engage with facts before answering,
not treat them as passive background. Measurable improvement in fact retention.

**Compression rollover (Rec #5) — when L2 has too many facts:**

Main characters can have 50+ established facts. Dumping all of them blows the
token budget and gives the LLM too much to process. Instead:

```python
def format_l2_with_rollover(facts: list, max_inline: int = 15) -> str:
    # Rank facts by relevance to the current message
    ranked = rank_facts(facts, query=user_message, recency_weight=0.4)

    if len(ranked) <= max_inline:
        return format_all(ranked)

    # Top N inline, rest as a compressed summary
    inline = ranked[:max_inline]
    tail = ranked[max_inline:]

    summary = compress_tail(tail)  # "40+ additional facts including relationships with..."
    return f"{format_all(inline)}\n<more>{summary}</more>"
```

Example:

```xml
<facts>
  <current>...</current>
  <recent>...</recent>
  <background>...</background>
  <more>
    Kai has 38 additional established relationships including: ties to 4 other
    factions (Twilight Guild, Mountain Sect, Silver Merchants, Sparrow Riders),
    5 training milestones, 12 secondary characters, and 8 plot events not
    directly relevant to the current query. Ask about any to retrieve details.
  </more>
</facts>
```

**Cross-layer deduplication (fixes Issue #4):**

If L1 already contains "Kai is 17, fire elemental, trained by Lin," the L2 loader
filters those facts out to avoid redundancy. See §4.4 for the dedup algorithm.

**When loaded:** When the user message contains recognized entity names.

### 4.3 Layer 3 — Deep Semantic Search (on-demand, ~500 tokens)

**Source:** Neo4j native vector search over `entity_embeddings` and `event_embeddings`
indexes (defined in [`101 §3.6`](101_DATA_RE_ENGINEERING_PLAN.md)), plus drawer
chunks from chat/book content.

#### Hybrid Scoring: Relevance + Recency (fixes Issue #8)

Pure cosine similarity over-weights old content. When a user asks "what did Kai do
recently?" the highest-similarity passages may be from chapter 3 simply because
they share vocabulary. We combine similarity with recency decay:

```python
def hybrid_score(similarity: float, age_days: int, query_type: str) -> float:
    """
    query_type:
      - "recent" (user said "yesterday", "last chapter", "recently") → recency_weight=0.6
      - "historical" (user said "originally", "first", "backstory") → recency_weight=0.1
      - "general" (default) → recency_weight=0.3
    """
    recency_weight = {
        "recent": 0.6,
        "historical": 0.1,
        "general": 0.3,
    }[query_type]

    # Exponential decay with 14-day half-life
    recency_score = 0.5 ** (age_days / 14)

    return (1 - recency_weight) * similarity + recency_weight * recency_score
```

**Query type detection:** simple keyword matching on the user message. No LLM
needed. Examples:
- "what did Kai do yesterday" → `recent`
- "how did Kai originally meet Lin" → `historical`
- "tell me about the jade amulet" → `general`

If the user mentions a specific chapter number ("in chapter 12..."), apply a
hard temporal filter before vector search.

#### Cypher with Hybrid Scoring

```cypher
CALL db.index.vector.queryNodes('entity_embeddings', 20, $query_embedding)
YIELD node, score AS similarity
WHERE node.user_id = $user_id
  AND (node)-[:BELONGS_TO]->(:Project {id: $project_id})
  AND similarity > 0.65                          // noise floor

WITH node, similarity,
     duration.between(node.last_seen, datetime()).days AS age_days

// Hybrid score applied in client code or via Cypher UDF
WITH node, similarity, age_days,
     (1 - $recency_weight) * similarity +
     $recency_weight * exp(-age_days * 0.0495) AS hybrid

WHERE hybrid > 0.5
RETURN node.name, node.description, node.source_chapter AS chapter,
       similarity, age_days, hybrid
ORDER BY hybrid DESC
LIMIT 5
```

#### Structured Passage Format (fixes Issue #3)

L3 returns text chunks that need attribution. Dumping raw prose into the prompt
causes hallucination amplification and quote confusion. Use XML-tagged passages
with metadata so the LLM can cite sources and distinguish content types:

```xml
<related_passages>
  <passage
    source="Winds of the Eastern Sea, ch.12"
    type="chapter_content"
    relevance="0.91"
    age_days="8"
  >
    The jade amulet was ancient, carved with runes that predated the Sixth Element
    itself. Master Lin had kept it locked away, never speaking of its origin, yet
    Kai had sensed its presence long before he had seen it.
  </passage>

  <passage
    source="chat 2026-04-08"
    type="conversation"
    relevance="0.85"
    age_days="5"
  >
    <user>Kai held the amulet up to the light...</user>
    <assistant>The runes seemed to resonate when exposed to flame, as though responding to Kai's elemental nature. You noted this was the first time anyone had seen it react.</assistant>
  </passage>

  <passage
    source="glossary: jade amulet"
    type="user_curated"
    relevance="1.00"
    age_days="30"
  >
    Ancient artifact. Activates in response to elemental energy. Linked to the Sixth Element prophecy (hypothesized). Kai possesses it as of ch.12.
  </passage>
</related_passages>
```

**Passage types and their meaning to the LLM:**

| type | What it means | LLM should... |
|---|---|---|
| `chapter_content` | Text from a saved chapter | Cite as canon, may quote |
| `conversation` | Previous chat with this user | Reference context, don't quote as if user said now |
| `user_curated` | Glossary entry or manual memory | Treat as authoritative |
| `draft_note` | Author's notes or outline | Use as guidance, not narrative |

**When loaded:** When L2 returns fewer than 3 relevant facts, or when the user
asks a broad "tell me about X" question, or when query type is `historical`.

### Token Budget Summary

| Layer | Tokens | Trigger | Source |
|---|---|---|---|
| L0 | ~50 | Always | Postgres `knowledge_summaries` (global) |
| L1 | ~200–400 | Session has project | Postgres projects + style examples |
| L2 | ~300–500 | Entities detected | Neo4j graph traversal (1-hop + 2-hop) |
| L3 | ~500 | L2 insufficient | Neo4j vector search + drawer chunks |
| **Total** | **~200–1450** | | vs ~5000 for 50-message replay |

---

## 4.4 Prompt Structure — How Memory Is Injected into the LLM Call

Where and how memory is placed in the prompt matters enormously for LLM behavior.
This section defines the mandatory prompt structure used by all memory consumers.

### 4.4.1 Memory Block Placement (fixes Issue #1)

**Rule:** memory is injected as an **XML-tagged block at the start of the system
prompt**, before the user's session system prompt. Both Claude and GPT-4 strongly
respect XML structure, and stable-content-at-the-start enables prompt caching
(see §7.5).

**Mandatory prompt layout:**

```
system:
<memory>
  {L0 global identity}
  {L1 project context + instructions + style examples}
  {L2 facts, grouped by temporal category, with CoT anchor}
  {L3 related passages, attributed with type/source/relevance}
  {Absence markers — see §4.5}
</memory>

<session_instructions>
{user's session system prompt, if any}
</session_instructions>

user: {current user message}
assistant: {recent messages, last N pairs}
... (conversation continues)
user: {current turn}
```

**Why XML tags, not free text:**
Claude 3 and GPT-4 are trained to respect XML structure and use it as semantic
boundaries. Facts inside `<facts>` are treated as known facts; instructions
inside `<instructions>` are treated as rules; passages inside `<passage>` are
treated as quotable references. Free text gets mixed semantics.

**Why at the start of the system prompt, not prepended as a separate message:**
- Survives system-prompt priority weighting across most models
- Enables prompt caching (stable prefix, cached across turns within a session)
- Doesn't confuse role-based models (no orphan message without a role)
- Claude explicitly recommends "put stable context at the beginning" in their
  prompt engineering guide

### 4.4.2 Full Memory Block Example

```xml
<memory>
  <!-- L0: Global identity (~50 tokens, always) -->
  <user>
    Vietnamese novelist. Writes fantasy and sci-fi. Prefers formal prose.
    Working on "The Three Kingdoms" series. Timezone UTC+7.
  </user>

  <!-- L1: Project context (~200-400 tokens, when session has project) -->
  <project type="book" name="Winds of the Eastern Sea">
    <description>
      Fantasy, 45 chapters. Protagonist Kai (17, fire elemental) trained by
      Master Lin (deceased ch.12). Magic system: five elements, unlocked by
      emotional triggers. Current arc: Water Kingdom infiltration.
    </description>
    <instructions>Formal prose. Third-person limited POV. No modern idioms.</instructions>
    <style_examples>
      <example>The wind carried the scent of pine and distant fires, and Kai knew the hunt had begun.</example>
      <example>Master Lin spoke no words, yet his silence held a thousand unspoken lessons.</example>
    </style_examples>
  </project>

  <!-- L2: Relevant facts (~300-500 tokens, when entities detected) -->
  <facts>
    <current>
      <fact source="ch.38">Kai is infiltrating Water Kingdom</fact>
      <fact source="ch.1" type="trait">Kai is a fire elemental</fact>
    </current>
    <recent>
      <fact source="ch.35">Kai killed Commander Zhao</fact>
    </recent>
    <background>
      <fact source="ch.12">Master Lin died</fact>
    </background>
    <negative>
      <fact source="ch.35">Water Kingdom does NOT know Kai killed Commander Zhao</fact>
    </negative>
  </facts>

  <!-- L3: Related passages (~500 tokens, when needed) -->
  <related_passages>
    <passage source="Eastern Sea, ch.12" type="chapter_content" relevance="0.91">
      Master Lin had kept the jade amulet locked away, never speaking of its origin...
    </passage>
  </related_passages>

  <!-- Absence markers — see §4.5 -->
  <no_memory_for>jade amulet activation sequence, Sixth Element prophecy text</no_memory_for>

  <instructions>
    Before answering, silently note which facts are relevant to the user's question.
    Characters can only know what their POV has witnessed — check &lt;negative&gt; before
    revealing information. Cite sources from &lt;related_passages&gt; when quoting.
    If a topic appears in &lt;no_memory_for&gt;, ask the user instead of inventing.
  </instructions>
</memory>

<session_instructions>
You are assisting with chapter 12 rewrite. Focus on pacing and emotional beats.
</session_instructions>
```

### 4.4.3 Cross-Layer Deduplication (fixes Issue #4)

L1 project summary and L2 facts often overlap. Before injecting L2, filter out
facts already covered by L1.

**Dedup algorithm:**

```python
def deduplicate_l2_against_l1(l1_text: str, l2_facts: list[Fact]) -> list[Fact]:
    """Filter L2 facts that are already expressed in L1 summary."""
    l1_lower = l1_text.lower()
    filtered = []

    for fact in l2_facts:
        # Build a minimal phrase from the fact
        phrase = f"{fact.subject} {fact.predicate} {fact.object}".lower()

        # Check if all significant words from the fact appear in L1
        keywords = [
            w for w in phrase.split()
            if len(w) > 3 and w not in STOPWORDS
        ]
        if keywords and all(kw in l1_lower for kw in keywords):
            metrics.inc("l2_fact_deduplicated")
            continue  # Already in L1, skip

        filtered.append(fact)

    return filtered
```

This is approximate but cheap. Perfect dedup would require semantic matching,
but keyword overlap catches 80-90% of duplicates at near-zero cost.

**Alternative (cleaner):** make L1 and L2 roles **explicitly disjoint**:
- L1 = stable narrative backbone (doesn't include recent events)
- L2 = dynamic facts not yet promoted to L1

Requires the L1 regeneration job (K11) to know which facts belong in L2, and
exclude them. Higher quality but more complex. Defer as a future optimization.

### 4.4.4 Total Prompt Budget (fixes Issue #6)

Memory is not the only thing in the prompt. We must budget the whole thing:

```python
PROMPT_BUDGET = {
    # Model context window → usable fraction
    "claude-opus-4-6":      int(200_000 * 0.8),   # 160K usable
    "claude-sonnet-4-6":    int(200_000 * 0.8),   # 160K usable
    "gpt-4o":                int(128_000 * 0.8),   # 102K usable
    "gemma-3-27b":           int(8_192 * 0.75),    # 6K usable
    "llama-3-70b":           int(128_000 * 0.8),
}

ALLOCATION = {
    "system_base":      0.10,  # Session system prompt + base instructions
    "memory_l0_l1":     0.15,  # Stable memory layers (~15%)
    "memory_l2_l3":     0.15,  # Dynamic memory layers (~15%)
    "recent_messages":  0.40,  # Last 20 messages (~40%)
    "current_message":  0.05,  # User's current turn (~5%)
    "response_buffer":  0.15,  # Space for LLM response (~15%)
}
```

**Allocation strategy:**
1. Start with ideal allocations for the active model
2. Build context in priority order: system_base → memory L0 → memory L1 → current_message → last 10 messages → memory L2 → memory L3 → older messages
3. If allocation exceeds budget, drop in reverse priority order
4. Never drop: system_base, current_message, last 10 messages, response_buffer

**Why this order:**
- System prompt and current message are non-negotiable
- Last 10 messages preserve conversational flow (the user's immediate context)
- L0/L1 are cheap and always useful (cache-friendly)
- L2/L3 are variable cost — drop first when budget is tight
- Older messages are the most sacrificeable

**Small-model degradation:**
When the model is small (e.g., 8K context), drop L2/L3 entirely and only use
L0+L1+recent_messages. This keeps memory working even on constrained deployments.

---

## 4.5 Absence Signaling — "I Don't Know What I Don't Know"

**Fixes Issue #10.** When memory returns nothing for a topic the user is asking
about, the LLM will hallucinate a plausible answer unless we explicitly signal
absence.

### 4.5.1 Detecting Absence

The context builder extracts entity candidates from the user message (same logic
as L2 entity detection). For each candidate:

1. Query L2 (Neo4j) for matching entities
2. Query L3 (vector search) for matching passages
3. If both return empty for a specific candidate → the candidate is an "absence"

```python
async def detect_absences(message: str, l2_entities: set, l3_hits: list) -> list[str]:
    """Find entities in user message that have zero memory coverage."""
    candidates = extract_entity_candidates(message)  # pattern-based, no LLM
    l3_hit_names = {hit.entity_name for hit in l3_hits if hit.relevance > 0.7}
    covered = l2_entities | l3_hit_names
    return [c for c in candidates if c.lower() not in {x.lower() for x in covered}]
```

### 4.5.2 Signaling Absence in the Prompt

Inject a `<no_memory_for>` element listing topics the user is asking about but
which have zero coverage:

```xml
<memory>
  <user>...</user>
  <project>...</project>
  <facts>
    <current>
      <fact source="ch.38">Kai is infiltrating Water Kingdom</fact>
    </current>
  </facts>
  <no_memory_for>jade amulet, the Sixth Element prophecy</no_memory_for>
  <instructions>
    If a topic appears in &lt;no_memory_for&gt;, do NOT invent details.
    Say "I don't have that in memory — can you remind me?" instead.
  </instructions>
</memory>
```

### 4.5.3 Behavioral Impact

Without absence signaling, models tend to:
- Invent plausible-sounding details
- Mix the user's question into an answer that wasn't in memory
- Hallucinate with high confidence

With explicit absence signaling + instruction, models:
- Ask clarifying questions when memory is empty
- Say "I don't know" when appropriate
- Reduce hallucination rate significantly (measurable in evals)

**Cost:** ~30-50 tokens for the absence block. Well worth it for correctness.

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
| Pattern (Pass 1, quarantined) vs LLM (Pass 2) | **LLM wins absolutely.** Pattern extraction never overrides LLM. Pass 2 confirms or contradicts quarantined Pass 1 facts (§5.1 quarantine). |
| Pattern (Pass 1) vs Pattern (Pass 1) | **Both quarantined until Pass 2.** Neither reaches L2 context. |
| Temporal facts (age over time) | **Both preserved** with `valid_from`/`valid_until` windows. |
| User manual edit vs any extraction | **User manual edit always wins.** Pause auto-extraction for that entity property for 7 days after manual edit. |

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

### 5.1 Pattern-Based Extractor (Pass 1) — with Quarantine

**Inspired by MemPalace's `general_extractor.py`.** Runs synchronously in the
knowledge-service event consumer. Zero LLM cost.

**Critical warning:** pattern extraction is dumb. Regex cannot distinguish intent
from fact, hypothetical from reality, reported speech from direct observation:

| Sentence | Regex match | Reality |
|---|---|---|
| `Kai killed Zhao` | ✓ | Correct — use it |
| `Kai said he killed Zhao` | ✓ | **Wrong** — reported speech, not fact |
| `What if Kai killed Zhao?` | ✓ | **Wrong** — hypothetical |
| `Kai would have killed Zhao` | ✓ | **Wrong** — counterfactual |
| `Kai killed Zhao in the dream` | ✓ | **Wrong** — non-canon |
| `Kai wanted to kill Zhao` | ✓ | **Wrong** — intent, not action |

Without protection, these false extractions pollute L2 and the LLM hallucinates
based on memory the user never created.

#### Quarantine Mode (fixes Issue #5)

Pass 1 facts are written to Neo4j with **low confidence** (`confidence=0.5`) and a
`pending_validation: true` flag. They are NOT loaded into L2 until Pass 2 validates
them (see §5.2).

**Quarantine rules:**

1. Pattern extractor writes facts with `confidence=0.5`, `pending_validation=true`
2. L2 context loader filters `WHERE confidence >= 0.8 AND NOT pending_validation`
3. Pass 2 LLM extraction runs within seconds (async via worker-ai)
4. Pass 2 either confirms the fact (promote to `confidence=0.9+`, clear pending)
   or contradicts it (write a new fact with higher confidence; old fact stays
   in quarantine for user review)
5. Facts stuck in quarantine for >24h with no Pass 2 verdict → auto-invalidated

**Why quarantine instead of rejection:**
- Pattern extraction is still useful for entity discovery (Kai is mentioned → track as candidate)
- Memory UI can show quarantined facts for power users to review
- Analytics: track Pass 1 → Pass 2 agreement rate to tune patterns

**Visibility:**

```cypher
// L2 loader (excludes quarantine)
MATCH (e:Entity)-[r:RELATES_TO]->(target)
WHERE e.user_id = $user_id
  AND r.confidence >= 0.8
  AND r.pending_validation IS NOT TRUE
RETURN ...

// Memory UI "Quarantine" tab (shows pending)
MATCH (e:Entity)-[r:RELATES_TO]->(target)
WHERE e.user_id = $user_id
  AND r.pending_validation = true
RETURN ...
```

#### Pattern Types

**Memory types detected by regex patterns (Pass 1, quarantined):**

| Type | Markers (examples) | Neo4j target |
|---|---|---|
| Decision | "let's use", "we decided", "instead of", "trade-off" | `(:Fact {type:'decision'})` |
| Preference | "I prefer", "always use", "never use", "my rule is" | `(:Fact {type:'preference'})` |
| Milestone | "it works", "fixed", "breakthrough", "finished chapter N" | `(:Fact {type:'milestone'})` |
| Entity | Capitalized proper nouns, quoted names, glossary matches | `(:Entity)` (also pending) |
| Relation | SVO patterns (excluding hypothetical markers) | `(:Entity)-[:RELATES_TO]->(:Entity)` |
| Event | "in chapter N", "after the battle", "when X happened" | `(:Event)` |
| **Negation** (Rec #4) | "does not know", "is unaware", "never told", "has no idea" | `(:Fact {type:'negation'})` |

**Negation patterns matter for novel consistency.** When the extractor finds
"Water Kingdom does not know that Kai killed Commander Zhao," it creates a
negative fact. These are loaded into L2's `<negative>` block (§4.2) so the
LLM doesn't have characters reveal things they shouldn't know.

**Hypothetical/counterfactual filters (skip extraction):**

Before extracting any SVO, the pattern extractor checks the sentence for:

```python
SKIP_MARKERS = [
    # Hypothetical
    r"\bif\b", r"\bwhat if\b", r"\bsuppose\b", r"\bhypothetically\b",
    # Counterfactual
    r"\bwould have\b", r"\bcould have\b", r"\bmight have\b",
    # Reported speech (unreliable for direct extraction)
    r"\bsaid\b", r"\bclaimed\b", r"\bthought\b", r"\bbelieved\b",
    # Non-canon markers
    r"\bin the dream\b", r"\bin a vision\b", r"\bdraft\b", r"\bdeleted scene\b",
    # Intent, not action
    r"\bwanted to\b", r"\bplanned to\b", r"\btried to\b", r"\babout to\b",
]

def should_extract(sentence: str) -> bool:
    lower = sentence.lower()
    return not any(re.search(pattern, lower) for pattern in SKIP_MARKERS)
```

This is approximate but catches 80% of false positives. The remaining 20% are
filtered by the quarantine mechanism.

**Entity extraction:** Two-pass system (MemPalace pattern):

1. **Candidate extraction** — capitalized words, quoted names, known glossary entities, repeated noun phrases
2. **Signal scoring** — frequency, position in sentence, co-occurrence with verbs, matches existing entities

**Triple extraction examples (quarantined until Pass 2 confirms):**
- `Kai killed Commander Zhao` → `(Kai)-[:killed {confidence:0.5, pending:true}]->(Commander Zhao)`
- `The capital is Hailong City` → `(Water Kingdom)-[:has_capital {confidence:0.5, pending:true}]->(Hailong City)`
- `We decided to use fire magic` → `(:Fact {type:'decision', confidence:0.5, pending:true})`
- `Water Kingdom does not know Kai killed Zhao` → `(:Fact {type:'negation', content:'Water Kingdom unaware of Zhao killing', confidence:0.6, pending:true})`

### 5.2 LLM-Based Extractor (Pass 2) — Validates Quarantine

**Defined in [`101 Phase D3`](101_DATA_RE_ENGINEERING_PLAN.md) (D3-01 to D3-04).**

Runs asynchronously via worker-ai. Extracts nuanced relationships, resolves
coreferences, merges entity variants, and — critically — **validates Pass 1
quarantine**.

**Validation flow:**

1. worker-ai consumes `chat.turn_completed` event (low priority queue)
2. Reads the full conversation turn from Postgres
3. Runs LLM extraction with context awareness (understands reported speech, negation, hypotheticals)
4. For each Pass 1 quarantined fact from this turn:
   - If LLM confirms → update: `confidence=0.95`, `pending_validation=false`
   - If LLM contradicts → create new fact with higher confidence, leave quarantined fact for user review
   - If LLM has no opinion (fact is ambiguous) → keep quarantined, eventually auto-invalidated at 24h
5. Writes new facts (beyond what Pass 1 saw) with `confidence=0.9`, not quarantined

**Agreement tracking:**

```python
metrics.inc("pass1_confirmed")    # Pass 2 agreed
metrics.inc("pass1_contradicted") # Pass 2 disagreed
metrics.inc("pass1_ambiguous")    # Pass 2 couldn't tell
```

Low agreement rate → tune Pass 1 patterns. High ambiguous rate → tune Pass 2 prompt.

The two passes complement each other:
- Pass 1 gives **discovery** (fast entity/relation detection for UI and eventual validation)
- Pass 2 gives **authority** (high-confidence facts that flow into L2)
- User never sees Pass 1 output in chat; they see Pass 2 (or a mix if Pass 1 > 24h old and uncontested)

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

### 5.4 Multilingual Extraction (fixes Issue #7)

LoreWeave is explicitly multilingual (Vietnamese, English, Chinese, Japanese,
Korean, and more — see `frontend/public/locales/`). Memory extraction must
handle non-English content correctly.

#### Language Detection

Every extraction call detects the dominant language of the input text before
selecting patterns and canonicalization rules:

```python
# Use fast-text or langdetect — no LLM call needed
from langdetect import detect_langs

def detect_primary_language(text: str) -> str:
    """Return ISO 639-1 code for the dominant language, or 'mixed' if ambiguous."""
    try:
        langs = detect_langs(text)
        if len(langs) > 1 and langs[0].prob < 0.7:
            return "mixed"
        return langs[0].lang
    except Exception:
        return "en"  # fallback
```

For mixed-language content (e.g., a Vietnamese novelist chatting in English about
Chinese character names), each sentence is detected separately and extracted
using its own language pattern set.

#### Per-Language Pattern Sets

The pattern extractor loads different regex sets per language. Each set is a
Python module under `knowledge_service/extractors/patterns/`:

```
patterns/
├── en.py      (decision, preference, milestone, negation, SKIP markers)
├── vi.py      ("chúng ta quyết định", "tôi thích", "không biết", ...)
├── zh.py      ("我们决定", "我喜欢", "不知道", ...)
├── ja.py      ("決めた", "好き", "知らない", ...)
├── ko.py      ("결정했어", "좋아해", "모르다", ...)
└── base.py    (shared: chapter numbers, quoted text, dates)
```

Each language pattern module exports the same interface:

```python
# en.py
DECISION_MARKERS = [r"\blet's use\b", r"\bwe decided\b", r"\binstead of\b", ...]
PREFERENCE_MARKERS = [r"\bI prefer\b", r"\balways use\b", ...]
NEGATION_MARKERS = [r"\bdoes not know\b", r"\bis unaware\b", ...]
SKIP_MARKERS = [r"\bif\b", r"\bwould have\b", r"\bsaid\b", ...]

# vi.py
DECISION_MARKERS = [r"\bchúng ta quyết định\b", r"\bchúng tôi sẽ\b", r"\bthay vì\b", ...]
PREFERENCE_MARKERS = [r"\btôi thích\b", r"\bluôn dùng\b", ...]
NEGATION_MARKERS = [r"\bkhông biết\b", r"\bchưa nghe\b", ...]
SKIP_MARKERS = [r"\bnếu\b", r"\bcó thể\b", r"\bnói rằng\b", ...]
```

#### CJK Canonicalization

The canonicalization function in §5.0 uses `.lower()` which is meaningless for
Chinese, Japanese, and Korean. Add per-script rules:

```python
import unicodedata

CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0xAC00, 0xD7AF),   # Hangul Syllables
]

def is_cjk(text: str) -> bool:
    return any(
        any(start <= ord(c) <= end for start, end in CJK_RANGES)
        for c in text
    )

def canonicalize_entity_name(name: str) -> str:
    """Normalize an entity name across scripts."""
    normalized = unicodedata.normalize("NFKC", name).strip()

    if is_cjk(normalized):
        # CJK: strip whitespace and honorifics, keep characters as-is
        for honorific in ["先生", "様", "さん", "君", "ちゃん", "씨", "선생", "大人"]:
            normalized = normalized.replace(honorific, "")
        return normalized.strip()

    # Latin/Cyrillic: lowercase + strip honorifics
    normalized = normalized.lower()
    for h in HONORIFICS_LATIN:
        normalized = normalized.removeprefix(h)
        normalized = normalized.removesuffix(h)

    # Collapse whitespace, strip punctuation
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^\w\s']", "", normalized)
    return normalized.strip()
```

#### Multilingual Embedding Model

Decision [#27](101_DATA_RE_ENGINEERING_PLAN.md) already specifies `BAAI/bge-m3`
or `intfloat/multilingual-e5-large`. Both support 100+ languages with shared
semantic space — a Vietnamese query can retrieve English chunks and vice versa.

**bge-m3 is preferred** because:
- Explicit multilingual training (100+ languages)
- 1024-dim (matches Neo4j index target)
- Strong CJK performance
- Dense + sparse hybrid retrieval support

#### Summary Language Preference

User's L0/L1 summaries are regenerated in their preferred language, not mixed:

```sql
-- New column on knowledge_summaries
ALTER TABLE knowledge_summaries ADD COLUMN language TEXT DEFAULT 'en';
```

The regeneration job reads `users.preferred_locale` or falls back to auto-detect
over recent messages. When a user switches locale, summaries are regenerated on
next trigger (not retroactively).

#### Context Builder Language Alignment

When building the memory block (§4.4), the context builder formats metadata
labels (`<facts>`, `<current>`, etc.) as XML — language-neutral. But the free-text
content inside each element is in whatever language the source used.

For the `<instructions>` CoT anchor and the `<no_memory_for>` absence signal,
the language matches the user's preferred locale so the LLM follows the
instructions correctly.

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

### 7.5 Prompt Caching Strategy (Rec #1)

Both Anthropic and OpenAI support prompt caching — the provider hashes the prefix
of your prompt and caches the attention state, charging ~10% cost for cache hits.
Memory context is a prime candidate because L0/L1 are stable across many turns.

**Cache structure:**

```
[CACHEABLE — stable, TTL ~5 minutes]
  <memory>
    <user>...</user>                        ← L0, changes rarely
    <project>...</project>                  ← L1, changes rarely
  </memory>
  <session_instructions>...</session_instructions>

[BREAKPOINT — cache cut here]

[VOLATILE — changes every turn]
  <memory>
    <facts>...</facts>                      ← L2, depends on user message
    <related_passages>...</related_passages> ← L3, depends on user message
    <no_memory_for>...</no_memory_for>      ← depends on user message
    <instructions>...</instructions>         ← dynamic CoT anchor
  </memory>

[CONVERSATION HISTORY — partially cached]
  user: ...
  assistant: ...
  (recent messages)
```

**Provider-specific cache hints:**

```python
# Anthropic Claude
messages = [
    {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": stable_memory_prefix,  # L0 + L1 + instructions
                "cache_control": {"type": "ephemeral"}  # ← cache this
            },
            {
                "type": "text",
                "text": volatile_memory + recent_messages_rendered,
                # No cache — changes every turn
            }
        ]
    },
    {"role": "user", "content": current_message}
]

# OpenAI GPT-4 (automatic prompt caching — just put stable content first)
# No explicit markers needed, but ordering matters: stable prefix → volatile suffix
```

**Expected savings:**
- L0 + L1 + style examples = ~500 tokens, constant across ~10-30 turns per session
- With caching: 10% × 500 = 50 tokens effective cost per turn instead of 500
- **~80-90% reduction in memory-layer cost** for active sessions

**Cache invalidation:**
- Session-level cache implicit (provider cache TTL is usually 5 min)
- L0/L1 edits in memory UI → emit `knowledge.summary_invalidated` event → chat-service evicts in-process cache → next call rebuilds stable prefix
- Project switch or session end → cache expires naturally

**Measurement:**
- Prometheus metric `llm_prompt_cache_hit_ratio` per consumer service
- Target: >70% hit rate for chat-service after first few turns in a session

### 7.6 Summary Regeneration — Drift Prevention (fixes Issue #9)

L0/L1 summaries are regenerated periodically to incorporate new knowledge. Without
guardrails, this becomes an echo chamber: "User prefers formal prose" gets
reinforced every regeneration, drowning out any experiment the user tries.

**Problem scenario:**
1. Initial L0: "User writes fantasy"
2. User writes formally for 20 sessions → L0: "User prefers formal fantasy prose"
3. User tries modern prose in session 21 → extraction sees mixed signals
4. Next regen ignores the 1 modern session → L0: "User exclusively writes formal fantasy"
5. LLM now aggressively avoids modern style, pushing user back to formal
6. User can't escape their own frozen identity

**Fix: regeneration uses raw source messages, not extracted facts:**

```python
async def regenerate_l1_project_summary(user_id: str, project_id: str):
    # 1. Fetch the raw content that inspired the summary
    chapters = await fetch_recent_chapters(project_id, limit=10)
    chat_turns = await fetch_recent_chat_turns(user_id, project_id, limit=50)
    user_edits = await fetch_summary_edits(user_id, project_id)

    # 2. Check for user override — respect it
    if user_edits and user_edits.latest.created_at > 30.days.ago:
        return  # Skip regen — user recently edited, don't fight them

    # 3. Build LLM prompt from raw content (not from current summary)
    llm_prompt = f"""
    Summarize this project for use as AI context. Focus on what's established,
    active, and unresolved. Do not infer user preferences — only describe the
    project itself.

    Recent chapters:
    {format_chapters(chapters)}

    Recent conversation:
    {format_chat_turns(chat_turns)}
    """

    new_summary = await llm.generate(llm_prompt, max_tokens=400)

    # 4. Diversity check — if the new summary is >95% similar to the old one,
    # no point writing a new version
    old_summary = await get_current_summary(user_id, project_id)
    if old_summary and similarity(new_summary, old_summary.content) > 0.95:
        metrics.inc("summary_regen_no_op")
        return

    # 5. Write new version (old versions preserved for audit)
    await write_summary(user_id, project_id, new_summary, version=old_summary.version + 1)
```

**Drift prevention rules:**

1. **Regeneration reads raw source**, not the current summary. This prevents
   recursive amplification.
2. **User edit wins for 30 days.** If the user manually edits a summary, the
   auto-regeneration job skips that scope until 30 days pass.
3. **Diversity check.** Skip regen if the new output is near-identical to the
   existing one — no churn, no drift.
4. **Preference extraction is conservative.** The LLM prompt explicitly says
   "do not infer preferences unless stated 3+ times." A single message
   doesn't flip an identity.
5. **Global L0 explicitly separated from project L1.** User identity
   ("Vietnamese, formal prose") lives in L0. Project characteristics
   ("Winds of the Eastern Sea is formal") live in L1. Editing one doesn't
   affect the other.
6. **Undo via version history.** `knowledge_summaries.version` increments on
   every regen. UI lets users roll back to a previous version if the new one
   is worse.

**Observability:**
- `summary_regen_count{scope_type}` — how often regen runs
- `summary_regen_no_op{scope_type}` — how often diversity check skips
- `summary_user_override_respected{scope_type}` — user edits protected from regen

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
