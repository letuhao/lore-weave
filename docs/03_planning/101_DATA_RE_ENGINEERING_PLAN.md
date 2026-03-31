# Data Re-Engineering Plan

> **Goal:** Rebuild the data layer to support AI-driven features (knowledge graph, RAG, wiki, timeline, auto-suggest) with a polyglot persistence architecture and event-driven pipelines.
>
> **Prerequisite for:** Frontend V2 Phase 3 (Glossary, Wiki, Chat, Timeline features)
> **Blocks:** P3-05 to P3-08 (Glossary), P3-17 (Wiki), P3-18/19 (Chat RAG)
> **Does not block:** P3-01 to P3-04 (Translation), P3-20 to P3-22 (Sharing, Settings, Trash)

---

## 1. Architecture Overview

### Three-Layer Data Stack

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: SOURCE OF TRUTH (Postgres)                            │
│  ├── App data: users, books, chapters, auth, billing            │
│  ├── Content: chapter_drafts (JSONB), chapter_revisions (JSONB) │
│  ├── RAG prep: chapter_blocks (denormalized text + hash)        │
│  └── User-curated: glossary entities (manual CRUD, evolves)     │
│                                                                  │
│  Every content mutation → event to Redis Stream                  │
└──────────────────────┬───────────────────────────────────────────┘
                       │ event-driven
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2: KNOWLEDGE GRAPH (Neo4j)                               │
│  ├── Entities: characters, places, items, concepts, factions    │
│  ├── Events: plot events with temporal + causal ordering        │
│  ├── Relations: entity ↔ entity edges with types                │
│  ├── Facts: atomic statements with source provenance            │
│  └── Populated by AI extraction pipeline (Python)               │
└──────────────────────┬───────────────────────────────────────────┘
                       │ async embedding
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3: RETRIEVAL (Qdrant Vector DB)                          │
│  ├── Chunk embeddings (chapter text blocks)                     │
│  ├── Entity embeddings (knowledge graph descriptions)           │
│  └── Read-only projection, rebuilt from Layer 1+2 any time      │
└──────────────────────────────────────────────────────────────────┘
```

### Event Pipeline Architecture

```
Postgres (write) → Redis Stream (events) → Consumer pipelines → Specialized stores
                                          ├── P1: Block extractor → chapter_blocks (Postgres)
                                          ├── P2: Knowledge builder → Neo4j (future)
                                          ├── P3: Embedder → Qdrant (future)
                                          └── P4+: Extensible (search, analytics, etc.)
```

### Technology Choices

| Component | Technology | Justification |
|-----------|-----------|---------------|
| Source of truth | Postgres 16 + JSONB | Already in stack, ACID, relational + document hybrid |
| Event bus | Redis Streams | Already in stack for translation jobs, consumer groups built-in |
| Knowledge graph | Neo4j 5 Community | Graph-native queries (Cypher), natural fit for entities/relations |
| Vector DB | Qdrant (self-hosted) | Open-source, Docker-friendly, filtering + payload, gRPC |
| Knowledge service | Python / FastAPI | Language rule: Python for AI/LLM services |
| Block extractor | Python consumer | Same language as knowledge service, JSON tree walking |

---

## 2. Schema Design

### 2.1 Chapter Storage (Postgres — clean break)

```sql
-- Drop and recreate: chapter_drafts, chapter_revisions
-- Existing data is draft-only, safe to drop

CREATE TABLE chapter_drafts (
  chapter_id UUID PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
  body JSONB NOT NULL,                    -- Tiptap doc JSON
  body_format TEXT NOT NULL DEFAULT 'json', -- 'json' (new) | 'plain' (legacy compat)
  draft_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  draft_version BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE chapter_revisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  body JSONB NOT NULL,                    -- snapshot at save time
  body_format TEXT NOT NULL DEFAULT 'json',
  message TEXT,
  author_user_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 2.2 Chapter Blocks (Postgres — RAG-ready denormalized table)

```sql
CREATE TABLE chapter_blocks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  block_index INT NOT NULL,               -- position in Tiptap doc
  block_type TEXT NOT NULL,               -- 'paragraph', 'heading', 'callout', 'blockquote'
  text_content TEXT NOT NULL,             -- plain text extracted from block
  content_hash TEXT NOT NULL,             -- SHA-256 for dirty detection
  heading_context TEXT,                   -- nearest preceding heading text
  attrs JSONB,                            -- block-specific attrs (heading level, callout type)
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE(chapter_id, block_index)
);

CREATE INDEX idx_chapter_blocks_chapter ON chapter_blocks(chapter_id);
CREATE INDEX idx_chapter_blocks_hash ON chapter_blocks(content_hash);
```

### 2.3 Event Schema (Redis Streams)

```
Stream: loreweave:events:chapter

Event: chapter.saved
{
  "event_type": "chapter.saved",
  "book_id": "uuid",
  "chapter_id": "uuid",
  "draft_version": 42,
  "body_format": "json",
  "body_hash": "sha256-of-body",
  "user_id": "uuid",
  "timestamp": "2026-03-31T12:00:00Z"
}

Event: chapter.deleted
{
  "event_type": "chapter.deleted",
  "book_id": "uuid",
  "chapter_id": "uuid",
  "timestamp": "..."
}
```

### 2.4 Neo4j Knowledge Graph (future — designed now, built later)

```cypher
// Nodes
(:Entity { id, book_id, name, kind, aliases, description, attributes,
           source, confidence, created_at })
(:Event  { id, book_id, description, chapter_id, block_index,
           narrative_order, chronological_order, event_type, significance })
(:Chapter { id, book_id, title, sort_order })
(:Book    { id, title })

// Relationships
(:Entity)-[:APPEARS_IN { first_mention_block }]->(:Chapter)
(:Entity)-[:BELONGS_TO]->(:Book)
(:Entity)-[:RELATES_TO { type, description, confidence, evidence_blocks }]->(:Entity)
(:Entity)-[:PARTICIPATES_IN { role }]->(:Event)
(:Event)-[:OCCURS_IN]->(:Chapter)
(:Event)-[:CAUSES]->(:Event)
(:Event)-[:HAPPENS_BEFORE]->(:Event)
(:Entity)-[:EXTRACTED_FROM { block_id, confidence, model }]->(:Chapter)
```

---

## 3. Implementation Phases

### Phase D1: Schema + Event Infrastructure (blocks everything)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D1-01 | BE | Clean schema: drop + recreate chapter_drafts (JSONB), chapter_revisions (JSONB + format) | None | S |
| D1-02 | BE | Create chapter_blocks table | D1-01 | S |
| D1-03 | BE | book-service: accept body_format in patchDraft, store JSONB body | D1-01 | S |
| D1-04 | BE | book-service: publish chapter.saved event to Redis Stream on save | D1-03 | S |
| D1-05 | BE | book-service: include body_format in getDraft, listRevisions, restoreRevision | D1-03 | S |
| D1-06 | FE | Frontend: save Tiptap JSON (body_format: 'json'), load JSONB directly | D1-05 | M |
| D1-07 | BE | Block extractor: Python consumer reads chapter.saved, extracts blocks → chapter_blocks | D1-02, D1-04 | M |
| D1-08 | BE | book-service: on chapter delete, publish chapter.deleted event | D1-04 | S |

**GATE:** After D1-08, the event pipeline is live. Chapter content saves as JSONB. Blocks are extracted.

### Phase D2: Infrastructure Prep (not blocking, can be parallel)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D2-01 | Infra | Add Neo4j 5 Community to docker-compose | None | S |
| D2-02 | Infra | Add Qdrant to docker-compose | None | S |
| D2-03 | BE | knowledge-service scaffold (Python/FastAPI, connects to Neo4j + Postgres + Redis) | D2-01 | M |

### Phase D3: Knowledge Pipeline (future — after D1 + D2)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D3-01 | BE | Entity extraction: LLM NER + coreference → Neo4j entities | D2-03, D1-07 | L |
| D3-02 | BE | Event extraction: LLM → Neo4j events + temporal ordering | D3-01 | L |
| D3-03 | BE | Relation extraction: LLM → Neo4j relationship edges | D3-01 | M |
| D3-04 | BE | Fact extraction: atomic statements with provenance | D3-03 | M |
| D3-05 | BE | Glossary-service evolution: read from Neo4j, user curates AI suggestions | D3-01 | L |

### Phase D4: Embedding + RAG (future — after D3)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D4-01 | BE | Embedding pipeline: chapter_blocks text → Qdrant vectors | D2-02, D1-07 | M |
| D4-02 | BE | Entity embedding: Neo4j entity descriptions → Qdrant | D3-01, D2-02 | M |
| D4-03 | BE | chat-service RAG: vector search + Neo4j context + LLM | D4-01, D4-02 | L |

### Size Key: S = <1 session, M = 1-2 sessions, L = 2-4 sessions

---

## 4. Service Impact Map

| Service | Changes | When |
|---|---|---|
| book-service (Go) | patchDraft accepts body_format, publishes Redis events | Phase D1 |
| block-extractor (Python, NEW) | Consumes chapter.saved, writes chapter_blocks | Phase D1 |
| knowledge-service (Python, NEW) | Consumes events, LLM extraction, writes Neo4j | Phase D3 |
| glossary-service (Go) | Evolves to read from Neo4j, keeps manual CRUD | Phase D3 |
| chat-service (Python) | Adds RAG query (Qdrant + Neo4j context) | Phase D4 |
| frontend-v2 | Save/load Tiptap JSON | Phase D1 |

---

## 5. Migration Strategy

**Clean break.** Drop `chapter_drafts` and `chapter_revisions` tables and recreate with JSONB schema. Existing data is development-only (no production users).

Steps:
1. Stop all services
2. Run migration SQL (drop + create)
3. Deploy updated book-service
4. Deploy frontend with JSONB save/load
5. Start block-extractor consumer
6. Verify: create chapter → save → check chapter_blocks populated

---

## 6. Decisions Log

| Decision | Reasoning |
|---|---|
| Postgres stays as source of truth | ACID, relational queries, existing stack |
| Neo4j for knowledge graph | Graph-native Cypher queries, natural for entities/relations/events |
| Qdrant for vector search | Self-hosted, Docker-friendly, better than pgvector at scale |
| Python for new AI services | Language rule: Python for AI/LLM services |
| Event-driven via Redis Streams | Already in stack, consumer groups, extensible pipeline architecture |
| Clean schema break | No production data, simpler than migration |
| Block extraction in Python (not Go) | JSON tree walking + future LLM calls = Python strength |
| Frontend V2 Phase 3 paused | Glossary/Wiki/Chat depend on knowledge layer, building GUI first = throwaway work |
