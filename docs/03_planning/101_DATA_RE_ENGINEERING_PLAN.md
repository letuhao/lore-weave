# Data Re-Engineering Plan

> **Goal:** Rebuild the data layer to support AI-driven features (knowledge graph, RAG, wiki, timeline, auto-suggest) with a polyglot persistence architecture and event-driven pipelines.
>
> **Prerequisite for:** Frontend V2 Phase 3 (Glossary, Wiki, Chat, Timeline features)
> **Blocks:** P3-05 to P3-08 (Glossary), P3-17 (Wiki), P3-18/19 (Chat RAG)
> **Does not block:** P3-01 to P3-04 (Translation), P3-20 to P3-22 (Sharing, Settings, Trash)
>
> **Created:** 2026-03-31 (session 12)
> **Updated:** 2026-03-31 (session 12 — technology research + PG18/Neo4j v2026.01 + data engineer review)

---

## 1. Technology Research Findings

> Research conducted 2026-03-31. These findings informed all architecture decisions below.

### PostgreSQL 18 (released September 2025)

| Feature | Impact for LoreWeave | Source |
|---------|---------------------|--------|
| **`JSON_TABLE`** | Query Tiptap JSONB blocks as relational rows directly in SQL. Eliminates need for Python block extractor — Postgres can extract blocks via trigger. | [Crunchy Data](https://www.crunchydata.com/blog/easily-convert-json-into-columns-and-rows-with-json_table) |
| **Virtual generated columns** | Extract fields from JSONB without storage cost: `block_count`, `word_count` as virtual columns. Zero-cost, always up-to-date. | [Neon](https://neon.com/postgresql/postgresql-18/virtual-generated-columns) |
| **`uuidv7()`** | Time-ordered UUIDs. Better insert performance (sequential B-tree writes), natural chronological ordering, no need for separate `created_at` sort. | [PG18 Release Notes](https://www.postgresql.org/docs/current/release-18.html) |
| **Async I/O** | 2-3x read performance improvement for large JSONB bodies. Worker-based I/O is the default. | [pganalyze](https://pganalyze.com/blog/postgres-18-async-io) |
| **SIMD JSON processing** | Faster parsing of JSON strings internally. | [Neon](https://neon.com/postgresql/postgresql-18-new-features) |
| **EXPLAIN ANALYZE improvements** | Buffer usage, WAL writes, CPU time shown automatically. Better debugging. | [PG18 Release Notes](https://www.postgresql.org/docs/current/release-18.html) |
| **Docker breaking change** | PGDATA path changed to `/var/lib/postgresql/18/docker`. Must update volume mounts. | [Aron Schueler](https://aronschueler.de/blog/2025/10/30/fixing-postgres-18-docker-compose-startup/) |

**Key insight:** `JSON_TABLE` + triggers replaces the need for a Python block extractor service. Postgres can extract Tiptap JSON blocks to `chapter_blocks` table natively in SQL, on every save, with zero latency and full ACID consistency.

**Caveat (from data engineer review):** Tiptap JSON has deeply nested text nodes (paragraphs with bold/italic = multiple text nodes, lists = 3 levels deep). A simple `JSON_TABLE` path like `$.content[0].text` only gets the first text node. **Solution:** Frontend pre-computes a `_text` field on each block containing the full concatenated text. The trigger reads `$._text` — trivial extraction, handles any nesting depth. See §3.2.1 for details.

### Neo4j v2026.01 (latest, March 2026)

| Feature | Impact for LoreWeave | Source |
|---------|---------------------|--------|
| **Native vector search with filters** | Filter vectors by metadata (book_id, language, entity type) AT INDEX TIME — no post-filtering needed. Eliminates need for separate Qdrant. | [Neo4j Blog](https://neo4j.com/blog/genai/vector-search-with-filters-in-neo4j-v2026-01-preview/) |
| **Cypher `SEARCH` clause** | Clean native syntax for vector queries, no procedure calls. | [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/) |
| **Multi-label vector indexes** | Index entities + events + chunks in one vector index, filter by label at query time. | [Neo4j Blog](https://neo4j.com/blog/genai/vector-search-with-filters-in-neo4j-v2026-01-preview/) |
| **HNSW algorithm** | Same algorithm as Qdrant, native implementation. | [Neo4j Docs](https://neo4j.com/developer/genai-ecosystem/vector-search/) |
| **Available in Community Edition** | Vector indexes work in free Community edition, not Enterprise-only. | [Neo4j Community](https://community.neo4j.com/t/new-blog-vector-search-with-filters-in-neo4j-v2026-01-preview/76472) |

**Key insight:** Neo4j v2026.01 eliminates the need for Qdrant. The knowledge graph DB now handles BOTH graph traversal AND vector search in unified Cypher queries. This reduces our DB count from 3 to 2.

### Qdrant (v1.17+, evaluated but NOT selected)

Qdrant remains an excellent dedicated vector DB with 4-bit quantization, built-in BM25, and native inference. However, Neo4j v2026.01's filtered vector search covers our needs. Qdrant would only be needed if we exceed Neo4j's vector performance limits (unlikely at LoreWeave's scale of <500K embeddings).

**Decision:** Do not include Qdrant. Revisit only if Neo4j vector search proves insufficient.

### GraphRAG Architecture (industry pattern)

| Finding | Source |
|---------|--------|
| Qdrant + Neo4j used together in production GraphRAG systems (Lettria achieved 20% accuracy gains) | [Qdrant Case Study](https://qdrant.tech/blog/case-study-lettria-v2/) |
| Neo4j officially recommends Qdrant integration for RAG pipelines | [Neo4j Blog](https://neo4j.com/blog/developer/qdrant-to-enhance-rag-pipeline/) |
| Best practice: use graph for structured knowledge + vectors for semantic similarity | [Qdrant Docs](https://qdrant.tech/documentation/examples/graphrag-qdrant-neo4j/) |

**Takeaway:** Our architecture (Postgres → Neo4j with vectors) follows the GraphRAG pattern but consolidated into fewer services. If we need to split vectors out later, the event-driven pipeline makes adding Qdrant a plug-in operation.

---

## 2. Architecture Overview

### Two-Layer Data Stack (revised from three-layer)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 1: SOURCE OF TRUTH (PostgreSQL 18)                           │
│  ├── App data: users, books, chapters, auth, billing                │
│  ├── Content: chapter_drafts (JSONB), chapter_revisions (JSONB)     │
│  ├── Block extraction: chapter_blocks (auto-populated via trigger   │
│  │   using JSON_TABLE — no external service needed)                 │
│  ├── Virtual columns: word_count, block_count (zero storage cost)   │
│  ├── UUIDs: uuidv7() for time-ordered primary keys                 │
│  └── User-curated: glossary entities (manual CRUD, evolves)         │
│                                                                      │
│  Every content mutation → event to Redis Stream                      │
└──────────────────────┬───────────────────────────────────────────────┘
                       │ event-driven (Redis Streams)
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 2: KNOWLEDGE GRAPH + VECTOR SEARCH (Neo4j v2026.01)          │
│  ├── Entities: characters, places, items, concepts, factions        │
│  ├── Events: plot events with temporal + causal ordering            │
│  ├── Relations: entity ↔ entity edges with types                    │
│  ├── Facts: atomic statements with source provenance                │
│  ├── Vector indexes: entity embeddings, chunk embeddings            │
│  │   (native filtered HNSW — no separate Qdrant needed)             │
│  └── Populated by AI extraction pipeline (Python knowledge-service) │
└──────────────────────────────────────────────────────────────────────┘
```

### Event Pipeline Architecture

```
Postgres 18 (write) → Redis Stream (events) → Consumer pipelines → Specialized stores

Pipeline 1: Block Extractor (Postgres trigger + JSON_TABLE)
  → Runs IN-DATABASE on every chapter save
  → Extracts Tiptap blocks → chapter_blocks table
  → Zero latency, full ACID, no external service

Pipeline 2: Knowledge Builder (Python knowledge-service, future)
  → Consumes chapter.saved events from Redis Stream
  → Reads chapter_blocks from Postgres
  → Runs LLM extraction (entities, events, relations, facts)
  → Writes to Neo4j knowledge graph
  → Triggers embedding generation on Neo4j nodes

Pipeline 3+: Extensible (future)
  → Search indexer (Elasticsearch/Meilisearch)
  → Analytics aggregator (materialized views)
  → Notification pipeline
  → Any new consumer just subscribes to the stream
```

### Technology Stack

| Component | Technology | Version | Justification |
|-----------|-----------|---------|---------------|
| Source of truth | PostgreSQL | **18** | JSON_TABLE, virtual columns, uuidv7, async I/O, SIMD JSON |
| Event bus | Redis Streams | existing | Already in stack for translation jobs, consumer groups |
| Knowledge graph | Neo4j | **v2026.01** | Graph-native Cypher, native vector search with filters |
| ~~Vector DB~~ | ~~Qdrant~~ | ~~removed~~ | ~~Neo4j v2026.01 covers vector search natively~~ |
| Knowledge service | Python / FastAPI | latest | Language rule: Python for AI/LLM services |
| Block extraction | **Postgres trigger** | PG18 | JSON_TABLE eliminates need for external Python consumer |

---

## 3. Schema Design

### 3.1 Postgres 18 Upgrade Notes

```yaml
# docker-compose.yml changes:
postgres:
  image: postgres:18-alpine          # was: postgres:16-alpine
  volumes:
    - postgres_data:/var/lib/postgresql  # PG18 uses versioned subdirectory internally
  environment:
    PGDATA: /var/lib/postgresql/18/docker  # NEW: PG18 requires this
```

**Migration:** Clean break. Drop all DBs and recreate. No production data.

### 3.2 Chapter Storage (clean break — JSONB)

```sql
-- ── chapter_drafts ──────────────────────────────────────────────────
-- Drop and recreate with JSONB body

CREATE TABLE chapter_drafts (
  chapter_id UUID PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
  body JSONB NOT NULL,                      -- Tiptap doc JSON (with _text snapshots per block)
  body_format TEXT NOT NULL DEFAULT 'json',  -- always 'json' (plain text converted at import)
  draft_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  draft_version BIGINT NOT NULL DEFAULT 1
);

-- Virtual generated columns (PG18 — zero storage cost)
ALTER TABLE chapter_drafts ADD COLUMN block_count INT
  GENERATED ALWAYS AS (jsonb_array_length(body -> 'content')) VIRTUAL;

-- ── chapter_revisions ───────────────────────────────────────────────

CREATE TABLE chapter_revisions (
  id UUID PRIMARY KEY DEFAULT uuidv7(),     -- PG18: time-ordered UUID
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  body JSONB NOT NULL,                      -- snapshot at save time
  body_format TEXT NOT NULL DEFAULT 'json',
  message TEXT,
  author_user_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chapter_revisions_chapter ON chapter_revisions(chapter_id, created_at DESC);
```

> **Note:** `chapter_raw_objects` (original uploaded text) stays as `TEXT`. It preserves the
> raw import and is never edited. No schema change needed.

### 3.2.1 Tiptap JSON `_text` Snapshot Convention (Option A)

The frontend adds a `_text` field to each top-level block on every save, containing the
full concatenated plain text of that block and all its children. This eliminates complex
server-side JSON tree walking.

```json
{
  "type": "doc",
  "content": [
    {
      "type": "paragraph",
      "_text": "Hello world and goodbye",
      "content": [
        { "type": "text", "text": "Hello " },
        { "type": "text", "marks": [{"type": "bold"}], "text": "world" },
        { "type": "text", "text": " and " },
        { "type": "text", "marks": [{"type": "italic"}], "text": "goodbye" }
      ]
    },
    {
      "type": "heading",
      "attrs": { "level": 2 },
      "_text": "Chapter One",
      "content": [{ "type": "text", "text": "Chapter One" }]
    },
    {
      "type": "bulletList",
      "_text": "Item 1\nItem 2",
      "content": [
        { "type": "listItem", "content": [{ "type": "paragraph", "content": [{ "type": "text", "text": "Item 1" }] }] },
        { "type": "listItem", "content": [{ "type": "paragraph", "content": [{ "type": "text", "text": "Item 2" }] }] }
      ]
    }
  ]
}
```

**Frontend implementation** (5 lines in TiptapEditor):
```typescript
function addTextSnapshots(doc: JSONContent): JSONContent {
  if (!doc.content) return doc;
  return {
    ...doc,
    content: doc.content.map(block => ({ ...block, _text: extractText(block) })),
  };
}
function extractText(node: any): string {
  if (node.type === 'text') return node.text || '';
  if (!node.content) return '';
  return node.content.map(extractText).join(node.type === 'listItem' ? '\n' : '');
}
```

**Benefits:**
- Trigger reads `$._text` — one simple JSON_TABLE path, no recursion
- Works for ANY nesting depth (lists, blockquotes, callouts, nested lists)
- Every downstream consumer (Neo4j, embeddings, search) reads `_text` directly
- ~10-15% more JSONB storage (acceptable: 50KB chapter → 57KB)

### 3.2.2 Plain Text Import → Tiptap JSON Conversion

Plain text is converted to Tiptap JSON **at import time** in `createChapterRecord`. The
`body_format` column is always `'json'` — no dual-mode branching in read paths.

```go
// Go: convert plain text to Tiptap JSON on chapter import
func plainTextToTiptapJSON(text string) ([]byte, error) {
    paragraphs := strings.Split(
        strings.ReplaceAll(strings.ReplaceAll(text, "\r\n", "\n"), "\r", "\n"),
        "\n\n",
    )
    content := make([]map[string]any, 0, len(paragraphs))
    for _, p := range paragraphs {
        p = strings.TrimSpace(p)
        if p == "" { continue }
        content = append(content, map[string]any{
            "type":    "paragraph",
            "_text":   p,
            "content": []map[string]any{{"type": "text", "text": p}},
        })
    }
    doc := map[string]any{"type": "doc", "content": content}
    return json.Marshal(doc)
}
```

**Result:** `body_format` is always `'json'`. No dual-mode. Trigger always fires.
Frontend always receives JSON. The `body_format` column exists for documentation and
future-proofing only.

### 3.3 Chapter Blocks (auto-populated via trigger)

```sql
CREATE TABLE chapter_blocks (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  block_index INT NOT NULL,                 -- position in Tiptap doc
  block_type TEXT NOT NULL,                 -- 'paragraph', 'heading', 'callout', 'blockquote'
  text_content TEXT NOT NULL,               -- plain text extracted from block
  content_hash TEXT NOT NULL,               -- SHA-256 for dirty detection / re-embedding
  heading_context TEXT,                     -- nearest preceding heading text
  attrs JSONB,                              -- block-specific attrs (heading level, callout type)
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE(chapter_id, block_index)
);

CREATE INDEX idx_chapter_blocks_chapter ON chapter_blocks(chapter_id);
CREATE INDEX idx_chapter_blocks_hash ON chapter_blocks(content_hash);
CREATE INDEX idx_chapter_blocks_type ON chapter_blocks(block_type);
```

### 3.4 Block Extraction Trigger (PG18 JSON_TABLE + UPSERT)

```sql
-- ── Trigger function: extract Tiptap blocks on every draft save ────
-- Uses UPSERT pattern to preserve block IDs when content is unchanged.
-- This gives stable IDs for downstream references (Neo4j provenance, embedding cache).
-- `updated_at` only changes when `content_hash` differs — embedding pipeline uses this.

CREATE OR REPLACE FUNCTION fn_extract_chapter_blocks()
RETURNS TRIGGER AS $$
DECLARE
  _max_idx INT;
BEGIN
  -- Extract blocks using JSON_TABLE, reading _text snapshot (pre-computed by frontend)
  INSERT INTO chapter_blocks (chapter_id, block_index, block_type, text_content, content_hash, attrs)
  SELECT
    NEW.chapter_id,
    (jt.block_index - 1),  -- 0-based index
    jt.block_type,
    COALESCE(jt.text_content, ''),
    encode(sha256(COALESCE(jt.text_content, '')::bytea), 'hex'),
    jt.block_attrs
  FROM JSON_TABLE(
    NEW.body, '$.content[*]'
    COLUMNS (
      block_index FOR ORDINALITY,
      block_type TEXT PATH '$.type',
      text_content TEXT PATH '$._text',        -- reads pre-computed _text snapshot
      block_attrs JSONB PATH '$.attrs'
    )
  ) AS jt
  WHERE jt.block_type IS NOT NULL
  ON CONFLICT (chapter_id, block_index)
  DO UPDATE SET
    block_type = EXCLUDED.block_type,
    text_content = EXCLUDED.text_content,
    content_hash = EXCLUDED.content_hash,
    attrs = EXCLUDED.attrs,
    updated_at = CASE
      WHEN chapter_blocks.content_hash = EXCLUDED.content_hash
      THEN chapter_blocks.updated_at    -- unchanged: keep old timestamp
      ELSE now()                        -- changed: update timestamp
    END;

  -- Delete blocks beyond the new block count (chapter shrank)
  SELECT count(*) INTO _max_idx
  FROM JSON_TABLE(NEW.body, '$.content[*]' COLUMNS (i FOR ORDINALITY)) AS jt;

  DELETE FROM chapter_blocks
  WHERE chapter_id = NEW.chapter_id AND block_index >= _max_idx;

  -- Fill heading_context using window function
  UPDATE chapter_blocks cb SET
    heading_context = sub.ctx
  FROM (
    SELECT
      id,
      MAX(CASE WHEN block_type = 'heading' THEN text_content END)
        OVER (PARTITION BY chapter_id ORDER BY block_index
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ctx
    FROM chapter_blocks
    WHERE chapter_id = NEW.chapter_id
  ) sub
  WHERE cb.id = sub.id AND cb.chapter_id = NEW.chapter_id;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_extract_blocks
  AFTER INSERT OR UPDATE OF body ON chapter_drafts
  FOR EACH ROW
  EXECUTE FUNCTION fn_extract_chapter_blocks();
```

**UPSERT benefits over DELETE+INSERT:**
- Block `id` (UUID) is stable across saves when content is unchanged
- `updated_at` only changes when `content_hash` differs — embedding pipeline uses `WHERE updated_at > last_processed`
- Neo4j provenance references (`block_id`) remain valid across saves
- No unnecessary churn in downstream pipelines

### 3.5 Event Schema (Redis Streams)

```
Stream: loreweave:events:chapter
Retention: MAXLEN ~ 10000 (auto-trim, oldest events evicted)

Event: chapter.saved
{
  "event_type": "chapter.saved",
  "book_id": "uuid",
  "chapter_id": "uuid",
  "draft_version": 42,
  "body_format": "json",
  "block_count": 15,
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

**Error handling:** Redis publish is best-effort. If Redis is down, the chapter save
still succeeds (Postgres commit is the priority). The publish failure is logged as a
warning. Downstream pipelines (knowledge-service) will have a "catch-up" / "full reprocess"
command that scans `chapter_drafts` directly for chapters not yet processed, independent
of the event stream.

**Go publish pattern:**
```go
// After successful Postgres commit — fire-and-forget with logging
if err := s.redis.XAdd(ctx, &redis.XAddArgs{
    Stream: "loreweave:events:chapter",
    MaxLen: 10000,
    Approx: true,
    Values: map[string]any{...},
}).Err(); err != nil {
    slog.Warn("failed to publish chapter.saved event", "chapter_id", chID, "err", err)
    // Do NOT fail the HTTP response — the save succeeded
}
```

### 3.6 Neo4j Knowledge Graph (designed now, built in Phase D3)

```cypher
// ── Nodes ──────────────────────────────────────────────

(:Entity {
  id: String,                  // uuidv7
  book_id: String,
  name: String,
  kind: String,                // character, place, item, concept, faction
  aliases: [String],           // "Elena", "the princess", "her majesty"
  description: String,         // AI-generated summary
  attributes: Map,             // kind-specific attrs (age, role, etc)
  source: String,              // 'ai_extracted' | 'user_created' | 'ai_suggested'
  confidence: Float,           // 0.0-1.0 for AI-extracted
  embedding: [Float],          // vector embedding (for vector index)
  created_at: DateTime
})

(:Event {
  id: String,
  book_id: String,
  description: String,
  chapter_id: String,
  block_index: Integer,
  narrative_order: Integer,    // position in story timeline
  chronological_order: Integer, // position in world timeline (if different)
  event_type: String,          // action, dialogue, revelation, transition
  significance: String,        // major, minor, background
  embedding: [Float],          // vector embedding
  created_at: DateTime
})

(:Chapter { id: String, book_id: String, title: String, sort_order: Integer })
(:Book    { id: String, title: String })

// ── Relationships ──────────────────────────────────────

(:Entity)-[:APPEARS_IN { first_mention_block: Integer }]->(:Chapter)
(:Entity)-[:BELONGS_TO]->(:Book)
(:Entity)-[:RELATES_TO {
  type: String,                // ally, enemy, parent, lover, owns, member_of
  description: String,
  confidence: Float,
  evidence_blocks: [Integer]
}]->(:Entity)
(:Entity)-[:PARTICIPATES_IN { role: String }]->(:Event)
(:Event)-[:OCCURS_IN]->(:Chapter)
(:Event)-[:CAUSES]->(:Event)
(:Event)-[:HAPPENS_BEFORE]->(:Event)

// ── Provenance ─────────────────────────────────────────

(:Entity)-[:EXTRACTED_FROM {
  block_id: String,
  chapter_id: String,
  confidence: Float,
  extracted_at: DateTime,
  model: String
}]->(:Chapter)

// ── Vector Indexes (Neo4j v2026.01) ────────────────────

CREATE VECTOR INDEX entity_embeddings FOR (e:Entity) ON (e.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX event_embeddings FOR (e:Event) ON (e.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};
```

### 3.7 Example: Hybrid Graph + Vector Query (Neo4j v2026.01)

```cypher
// "What is Elena's relationship with the jade amulet?"
// Step 1: Vector search for relevant entities
CALL db.index.vector.queryNodes('entity_embeddings', 5, $queryEmbedding)
YIELD node AS entity, score
WHERE entity.book_id = $bookId

// Step 2: Graph traversal for relationships
WITH entity, score
MATCH (entity)-[r:RELATES_TO]-(related:Entity)
WHERE related.name CONTAINS 'amulet' OR entity.name CONTAINS 'Elena'
RETURN entity.name, related.name, r.type, r.description, score
ORDER BY score DESC

// "Show Elena's character arc" (timeline)
MATCH (e:Entity {name: "Elena", book_id: $bookId})
      -[:PARTICIPATES_IN]->(ev:Event)-[:OCCURS_IN]->(ch:Chapter)
RETURN ev.description, ev.narrative_order, ch.title
ORDER BY ev.narrative_order

// "Find plot holes: entities referenced before introduction"
MATCH (ev:Event)-[:OCCURS_IN]->(ch:Chapter),
      (e:Entity)-[:PARTICIPATES_IN]->(ev),
      (e)-[:APPEARS_IN]->(first_ch:Chapter)
WHERE first_ch.sort_order > ch.sort_order
  AND e.book_id = $bookId
RETURN e.name, ch.title AS referenced_in, first_ch.title AS introduced_in
```

---

## 4. Implementation Phases

### Phase D1: Schema + Event Infrastructure (blocks everything)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D1-01 | Infra | Upgrade Postgres 16 → 18 in docker-compose (image, PGDATA, volume) | None | S |
| D1-02 | BE | Clean schema: drop + recreate chapter_drafts (JSONB), chapter_revisions (JSONB + uuidv7) | D1-01 | S |
| D1-03 | BE | Create chapter_blocks table + extraction trigger (JSON_TABLE) | D1-02 | M |
| D1-04 | BE | book-service: accept body_format in patchDraft, store JSONB body | D1-02 | S |
| D1-05 | BE | book-service: publish chapter.saved/deleted events to Redis Stream | D1-04 | S |
| D1-06 | BE | book-service: getDraft/listRevisions/restoreRevision include body_format | D1-04 | S |
| D1-07 | FE | Frontend: save Tiptap JSON (body_format: 'json'), load JSONB directly | D1-06 | M |
| D1-08 | BE+FE | Integration test: create chapter → save → verify chapter_blocks populated | D1-03, D1-07 | S |

**GATE:** After D1-08, chapter content saves as JSONB. Blocks auto-extracted via trigger. Events published to Redis Stream.

### Phase D2: Neo4j Infrastructure (can parallel with D1-05+)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D2-01 | Infra | Add Neo4j v2026.01 to docker-compose | None | S |
| D2-02 | BE | knowledge-service scaffold (Python/FastAPI, connects to Neo4j + Postgres + Redis) | D2-01 | M |
| D2-03 | BE | Neo4j schema init: create constraints, vector indexes | D2-01 | S |

### Phase D3: Knowledge Pipeline (future — after D1 + D2)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D3-01 | BE | Entity extraction: LLM NER + coreference → Neo4j entities | D2-02, D1-08 | L |
| D3-02 | BE | Event extraction: LLM → Neo4j events + temporal ordering | D3-01 | L |
| D3-03 | BE | Relation extraction: LLM → Neo4j relationship edges | D3-01 | M |
| D3-04 | BE | Fact extraction: atomic statements with provenance | D3-03 | M |
| D3-05 | BE | Embedding generation: embed entities + events → Neo4j vector indexes | D3-01, D2-03 | M |
| D3-06 | BE | Glossary-service evolution: read from Neo4j, user curates AI suggestions | D3-01 | L |

### Phase D4: RAG Integration (future — after D3)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D4-01 | BE | Chunk embedding pipeline: chapter_blocks text → Neo4j vector index | D2-03, D1-08 | M |
| D4-02 | BE | chat-service RAG: hybrid graph + vector query + LLM context | D3-05, D4-01 | L |
| D4-03 | BE | Wiki generation: entity pages from Neo4j knowledge graph | D3-04 | L |
| D4-04 | BE | Timeline generation: event ordering from Neo4j | D3-02 | M |

### Size Key: S = <1 session, M = 1-2 sessions, L = 2-4 sessions

---

## 5. Service Impact Map

| Service | Changes | When |
|---|---|---|
| **docker-compose** | Postgres 16→18, add Neo4j v2026.01, volume changes | Phase D1 + D2 |
| **book-service** (Go) | patchDraft accepts body_format, JSONB body, publishes Redis events | Phase D1 |
| **knowledge-service** (Python, NEW) | Consumes events, LLM extraction, writes Neo4j | Phase D3 |
| **glossary-service** (Go) | Evolves to read from Neo4j, keeps manual CRUD | Phase D3 |
| **chat-service** (Python) | Adds RAG: hybrid graph+vector query via Neo4j | Phase D4 |
| **frontend-v2** | Save/load Tiptap JSON directly (no plain text round-trip) | Phase D1 |

---

## 6. Migration Strategy

**Clean break.** Drop all databases and recreate. No production data exists.

Steps:
1. Stop all services
2. Remove old Postgres volumes (`docker volume rm ...`)
3. Update docker-compose: Postgres 18, PGDATA, Neo4j
4. `docker-compose up -d postgres` — creates fresh PG18 instance
5. Run migration (all services auto-migrate on startup)
6. Deploy updated book-service + frontend
7. Verify: create chapter → save → check `chapter_blocks` auto-populated
8. Verify: check Redis Stream for `chapter.saved` event

---

## 7. Decisions Log

| # | Decision | Reasoning | Date |
|---|---|---|---|
| 1 | **Postgres 18** (upgrade from 16) | JSON_TABLE, virtual generated columns, uuidv7, async I/O (2-3x reads), SIMD JSON | 2026-03-31 |
| 2 | **Neo4j v2026.01** for knowledge graph + vectors | Native filtered vector search eliminates need for Qdrant. Graph + vector in one DB. | 2026-03-31 |
| 3 | **No Qdrant** (removed from plan) | Neo4j v2026.01 covers vector search natively. Revisit only if >500K embeddings. | 2026-03-31 |
| 4 | **Block extraction via Postgres trigger** (not Python) | PG18 JSON_TABLE runs in-database: zero latency, ACID consistent, no extra service. | 2026-03-31 |
| 5 | **`uuidv7()`** for all new PKs | Time-ordered UUIDs: better insert perf, natural ordering, PG18 native. | 2026-03-31 |
| 6 | **Virtual generated columns** for computed fields | block_count: zero storage, always accurate, indexable. | 2026-03-31 |
| 7 | Postgres stays as source of truth | ACID, relational queries, existing stack, now with JSON_TABLE superpowers. | 2026-03-31 |
| 8 | Python for knowledge-service | Language rule: Python for AI/LLM services. Neo4j Python driver is mature. | 2026-03-31 |
| 9 | Event-driven via Redis Streams | Already in stack, consumer groups, extensible pipeline architecture. | 2026-03-31 |
| 10 | Clean schema break | No production data, simpler than migration. Drop all DBs. | 2026-03-31 |
| 11 | Frontend V2 Phase 3 paused | Glossary/Wiki/Chat depend on knowledge layer. Building GUI first = throwaway work. | 2026-03-31 |
| 12 | **`_text` snapshots per block** (Option A) | Frontend pre-computes text for each block. Trigger reads `$._text` — trivial, no recursive SQL. Handles any nesting depth. ~10-15% more JSONB storage (acceptable). | 2026-03-31 |
| 13 | **UPSERT trigger** (not DELETE+INSERT) | Preserves block IDs across saves. `updated_at` only changes when `content_hash` differs. Stable references for Neo4j provenance + embedding cache. | 2026-03-31 |
| 14 | **Plain text → Tiptap JSON at import** | All bodies are always JSON. No dual-mode branching. `body_format` is always `'json'`. Eliminates branching in every read path. | 2026-03-31 |
| 15 | **`json.RawMessage` for JSONB in Go** | pgx scans JSONB as `[]byte`. Using `json.RawMessage` prevents base64 encoding in API responses. Critical for correct JSON serialization. | 2026-03-31 |
| 16 | **Redis publish is best-effort** | Redis down = log warning, save still succeeds. Knowledge pipeline has catch-up/reprocess command. At-most-once delivery acceptable. | 2026-03-31 |
| 17 | **Redis Stream `MAXLEN ~ 10000`** | Auto-trim old events. Prevents unbounded growth. Older events re-derivable from database. | 2026-03-31 |
| 18 | **`chapter_raw_objects` unchanged** | Stays as `TEXT`. Preserves raw import, never edited. No schema change needed. | 2026-03-31 |

---

## 8. Data Engineer Review Notes

> Review conducted 2026-03-31. All findings incorporated into the plan above.

### Issues Found and Resolutions

| # | Issue | Severity | Resolution |
|---|-------|----------|------------|
| 1 | JSON_TABLE `$.content[0].text` misses formatted text (bold/italic = multiple text nodes) and nested blocks (lists, blockquotes) | **Critical** | Frontend adds `_text` snapshot per block (Decision #12). Trigger reads `$._text` — trivial path. |
| 2 | Go pgx scans JSONB as `[]byte` → `json.Marshal` base64-encodes it in API response | **High** | Use `json.RawMessage` for body field in all handlers (Decision #15). |
| 3 | DELETE+INSERT trigger loses block UUIDs on every save — breaks downstream references | **Medium** | Switch to UPSERT on `(chapter_id, block_index)` — stable IDs, `updated_at` tracks changes (Decision #13). |
| 4 | Redis publish failure = lost event, no retry | **Medium** | Best-effort publish with warning log. Knowledge pipeline has catch-up reprocess (Decision #16). |
| 5 | Plain text in JSONB column creates dual-mode complexity in every read path | **Medium** | Convert plain text to Tiptap JSON at import time. `body_format` always `'json'` (Decision #14). |
| 6 | No Redis Stream retention policy — unbounded growth | **Low** | `MAXLEN ~ 10000` on XADD (Decision #17). |
| 7 | `uuidv7()` not applied to existing tables (books, chapters) | **Low** | Apply to all tables in clean break. Consistent time-ordered IDs across system. |
| 8 | `chapter_raw_objects` not mentioned in plan | **Low** | Stays as TEXT, unchanged (Decision #18). |

---

## 8. Future Considerations

| Item | Trigger | Action |
|---|---|---|
| Add Qdrant as dedicated vector DB | Neo4j vector search latency >100ms at >500K embeddings | Add Qdrant container, new Pipeline 3, move embeddings |
| Add Elasticsearch/Meilisearch | Public catalog needs full-text search with facets | New Pipeline 4, consumer for Redis events |
| pgvector on Postgres | Need vector search on chapter_blocks without Neo4j round-trip | Add pgvector extension, hybrid search in SQL |
| Multi-book knowledge linking | Cross-book entity resolution (same character in series) | Neo4j cross-book relationship edges |
| Real-time collaboration | Multiple users editing same chapter | CRDT/OT layer, conflict resolution, WebSocket |
