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

### 3.5.1 Transactional Outbox Pattern (guaranteed delivery)

Events are written to an `outbox_events` table in the **same Postgres transaction** as the
data change. A background worker publishes pending events to Redis Stream. This guarantees
at-least-once delivery — no events are lost even if Redis is down.

```sql
CREATE TABLE outbox_events (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL,        -- 'chapter', 'book', 'entity'
  aggregate_id UUID NOT NULL,          -- chapter_id, book_id, etc.
  event_type TEXT NOT NULL,            -- 'chapter.saved', 'chapter.deleted'
  payload JSONB NOT NULL,              -- event data
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,           -- NULL = pending, set when published
  retry_count INT NOT NULL DEFAULT 0,
  last_error TEXT                      -- last publish failure reason
);

CREATE INDEX idx_outbox_unpublished ON outbox_events (created_at)
  WHERE published_at IS NULL;

-- Instant notification to worker on new event
CREATE OR REPLACE FUNCTION fn_outbox_notify()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('outbox_events', NEW.id::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_outbox_notify
  AFTER INSERT ON outbox_events
  FOR EACH ROW EXECUTE FUNCTION fn_outbox_notify();
```

**Write path** (inside patchDraft transaction):
```go
// SAME transaction as chapter save — atomic
_, _ = tx.Exec(ctx, `
  INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
  VALUES ('chapter', $1, 'chapter.saved', $2)
`, chID, payloadJSON)
// tx.Commit() — both data change AND event are guaranteed
```

**Outbox worker** (goroutine in book-service):
1. `LISTEN outbox_events` — gets instant `pg_notify` notification (<100ms)
2. On notification: read and publish all pending events to Redis Stream
3. Fallback: poll every 30s for any missed events (restart, network glitch)
4. On success: set `published_at = now()`
5. On failure: increment `retry_count`, set `last_error`, retry next cycle
6. Cleanup: daily job deletes events where `published_at < now() - 7 days`

**Consumer idempotency:** At-least-once delivery means consumers may see duplicates.
Each event has a unique `id` (uuidv7). Consumers track `last_processed_event_id`.
Neo4j `MERGE` with deterministic IDs is idempotent. Block extraction UPSERT is idempotent.
See §3.5.4 for the mandatory idempotency layer all consumers must implement.

**Consumer catch-up strategy (Redis + event_log hybrid):**

Redis Streams have `MAXLEN ~ 10000` retention (§3.5.5) to bound memory. But consumers
may be offline longer than 10K events. To prevent data loss, consumers use a two-source
catch-up pattern:

1. On startup, read `event_consumers.last_processed_event_id` from `loreweave_events`
2. Attempt `XREAD` from Redis Stream starting after `last_processed_event_id`
3. If Redis returns "ID too old" or the event is no longer in the stream:
   - Fall back to reading from `event_log` table (permanent history)
   - `SELECT * FROM event_log WHERE id > $last_processed ORDER BY id LIMIT 1000`
   - Process batch, update `last_processed_event_id`
   - Repeat until caught up
4. Once caught up to Redis-available events, switch to real-time `XREAD` with blocking
5. Update `last_processed_event_id` after each successfully processed event

This guarantees:
- Consumer can recover from any downtime duration (bounded only by `event_log` retention)
- Real-time latency when healthy (Redis XREAD is sub-millisecond)
- No silent event loss when Redis evicts old entries

**Outbox location:** Each microservice owns its own `outbox_events` table in its own
database (same-transaction atomicity). A centralized `loreweave_events` database stores
the permanent event log, consumer tracking, and dead letter queue — written by the relay
worker after publish. See §3.5.2 for the shared events schema.

### 3.5.2 Shared Events Database (`loreweave_events`)

Centralized event management — all services, all events, permanent history.

```sql
-- ── Permanent event log ────────────────────────────────────────
CREATE TABLE event_log (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  source_service TEXT NOT NULL,        -- 'book-service', 'glossary-service'
  source_outbox_id UUID NOT NULL,      -- original outbox event id (dedup key)
  event_type TEXT NOT NULL,            -- 'chapter.saved', 'entity.created'
  aggregate_type TEXT NOT NULL,        -- 'chapter', 'book', 'entity'
  aggregate_id UUID NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,     -- when the event originally occurred
  stored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(source_service, source_outbox_id)  -- idempotent relay
);

CREATE INDEX idx_event_log_type ON event_log (event_type, created_at DESC);
CREATE INDEX idx_event_log_aggregate ON event_log (aggregate_type, aggregate_id);
CREATE INDEX idx_event_log_service ON event_log (source_service, created_at DESC);

-- ── Consumer tracking ──────────────────────────────────────────
CREATE TABLE event_consumers (
  consumer_name TEXT NOT NULL,         -- 'knowledge-pipeline', 'embedding-pipeline'
  stream_name TEXT NOT NULL,           -- 'loreweave:events:chapter'
  last_processed_event_id UUID,
  last_processed_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active', -- 'active', 'paused', 'error'
  error_message TEXT,
  PRIMARY KEY (consumer_name, stream_name)
);

-- ── Dead letter queue ──────────────────────────────────────────
CREATE TABLE dead_letter_events (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  event_id UUID NOT NULL REFERENCES event_log(id),
  consumer_name TEXT NOT NULL,
  failure_reason TEXT NOT NULL,
  retry_count INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 5,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_dead_letter_unresolved ON dead_letter_events (created_at)
  WHERE resolved_at IS NULL;
```

### 3.5.3 Two-Worker Architecture

Background tasks split by language boundary and resource profile.

```
┌─ worker-infra (Go) ──────────────────────────────────────────┐
│  Config: WORKER_TASKS env var selects active tasks            │
│                                                               │
│  Task Registry:                                               │
│  ├── outbox-relay     LISTEN + poll → Redis Stream + event_log│
│  ├── outbox-cleanup   cron daily: delete old published events │
│  ├── event-archive    cron weekly: partition old event_log    │
│  ├── search-indexer   future: Redis consumer → search engine │
│  └── notifier         future: Redis consumer → push/email    │
│                                                               │
│  Profile: lightweight, always-on, <100ms latency, 50MB RAM   │
│  Reads: all service outbox tables (book, glossary, auth, etc)│
│  Writes: loreweave_events.event_log + Redis Streams          │
└───────────────────────────────────────────────────────────────┘

┌─ worker-ai (Python) ──────────────────────────────────────────┐
│  Config: WORKER_TASKS env var selects active tasks            │
│                                                               │
│  Task Registry:                                               │
│  ├── translation-worker   RabbitMQ consumer → LLM → DB       │
│  ├── knowledge-extractor  Redis consumer → LLM → Neo4j       │
│  ├── embedding-generator  Redis consumer → embed → Neo4j     │
│  └── future AI tasks                                          │
│                                                               │
│  Profile: heavy, bursty, 2GB+ RAM, GPU optional              │
│  Absorbs existing translation-worker container                │
└───────────────────────────────────────────────────────────────┘
```

**Task types in the registry:**
- **ListenTask** — triggered by pg_notify + poll fallback (outbox relay)
- **CronTask** — runs on schedule (cleanup, archival)
- **ConsumerTask** — reads from Redis Stream consumer group (indexing, notify)
- **QueueTask** — reads from RabbitMQ queue (translation, legacy)

**Scaling pattern:** Same binary, different `WORKER_TASKS`. No code change to scale.
```
Dev:    worker-infra  WORKER_TASKS=outbox-relay,outbox-cleanup
Prod:   worker-relay  WORKER_TASKS=outbox-relay          (high priority, dedicated)
        worker-cron   WORKER_TASKS=outbox-cleanup,event-archive
        worker-ai-1   WORKER_TASKS=knowledge-extractor   (GPU instance)
        worker-ai-2   WORKER_TASKS=embedding-generator   (GPU instance)
        worker-ai-3   WORKER_TASKS=translation-worker    (scale horizontally)
```

### 3.5.4 Consumer Idempotency Layer (mandatory for all AI consumers)

At-least-once delivery + non-deterministic LLM output = duplicate / conflicting writes
unless consumers implement explicit idempotency. This section defines the mandatory
pattern for all Redis/event_log consumers that write to Neo4j.

**Problem:** Running the same LLM extraction twice on the same input may produce:
- Different entity names (LLM temperature > 0)
- Different relation wording ("killed" vs "slew")
- Different coreference resolutions ("the princess" → Elena vs Melena)

Without a canonicalization + idempotency layer, duplicate processing creates
garbage buildup in Neo4j — multiple nodes for the same entity, conflicting facts.

**Rule 1: Deterministic node IDs.** Every Neo4j node gets an ID derived from
canonical form, not from the LLM output:

```python
def entity_canonical_id(user_id: str, project_id: str, name: str, kind: str) -> str:
    """Deterministic ID for an entity — same name + kind = same node."""
    normalized = name.lower().strip()
    # Strip common honorifics/titles for matching (kept as alias)
    for prefix in ("master ", "lord ", "lady ", "sir ", "dame ", "mr. ", "mrs. ", "dr. "):
        normalized = normalized.removeprefix(prefix)
    key = f"{user_id}:{project_id or 'global'}:{kind}:{normalized}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]
```

Cypher write uses this ID with `MERGE`:
```cypher
MERGE (e:Entity {id: $canonical_id})
ON CREATE SET
  e.name = $display_name,
  e.kind = $kind,
  e.user_id = $user_id,
  e.project_id = $project_id,
  e.aliases = [$display_name],
  e.created_at = datetime()
ON MATCH SET
  e.aliases = CASE
    WHEN $display_name IN e.aliases THEN e.aliases
    ELSE e.aliases + $display_name
  END,
  e.updated_at = datetime()
RETURN e
```

Running the same extraction twice = no duplicate nodes. Different spellings of the
same name accumulate into `aliases`.

**Rule 2: Event-level idempotency key.** Every fact/relation write records the source
event ID. If a consumer retries the same event, writes are no-ops:

```cypher
MERGE (e1:Entity {id: $subject_id})
MERGE (e2:Entity {id: $object_id})
MERGE (e1)-[r:RELATES_TO {
  type: $relation_type,
  source_event_id: $event_id   // idempotency key — unique per (subject, object, type, event)
}]->(e2)
ON CREATE SET
  r.confidence = $confidence,
  r.valid_from = $valid_from,
  r.created_at = datetime()
```

The `source_event_id` in the relationship match means rerunning the same event
creates zero new edges.

**Rule 3: Consumer state tracking.** Each consumer maintains its position in
`event_consumers`:

```sql
INSERT INTO event_consumers (consumer_name, stream_name, last_processed_event_id, last_processed_at)
VALUES ('knowledge-extractor', 'loreweave:events:chapter', $event_id, now())
ON CONFLICT (consumer_name, stream_name) DO UPDATE
  SET last_processed_event_id = EXCLUDED.last_processed_event_id,
      last_processed_at = EXCLUDED.last_processed_at;
```

This is updated **after** the Neo4j write succeeds, in the same logical operation.
If the consumer crashes between Neo4j write and state update, the next run will
re-process the event — and idempotency rules 1 and 2 ensure no duplicate data.

**Rule 4: Canonicalization is versioned.** If the canonicalization function changes
(e.g., new honorific added), existing entity IDs become stale. Record the canonicalization
version on each entity:

```cypher
(:Entity { ..., canonical_version: 1 })
```

A migration task can rebuild affected entity IDs when the version bumps. Start at
version 1; bump only when rules change materially.

### 3.5.5 Redis Stream Retention & Catch-Up

Redis Streams use `MAXLEN ~ 10000` per stream (approximate trim). This bounds memory
but means consumers offline for >10K events miss data if they only read from Redis.

**Retention target:** ~7 days at expected throughput.
- Chapter saves: ~50/day × 7 = 350 events
- Chat turns: ~5000/day × 7 = 35000 events (CHAT STREAM needs higher MAXLEN: ~50000)
- Other: ~1000/day × 7 = 7000 events

**Streams and their MAXLEN:**
```
loreweave:events:chapter    MAXLEN ~ 10000    (conservative, low throughput)
loreweave:events:chat       MAXLEN ~ 50000    (high throughput chat turns)
loreweave:events:glossary   MAXLEN ~ 10000
loreweave:events:generic    MAXLEN ~ 10000
```

**Catch-up procedure (applies to all AI consumers):**

```python
async def catch_up_and_stream(consumer_name: str, stream_name: str):
    # 1. Load last processed position from Postgres
    last_id = await get_last_processed(consumer_name, stream_name)

    # 2. Try to resume from Redis
    try:
        events = await redis.xread({stream_name: last_id}, block=0, count=100)
        if events:
            return events  # Redis has them, stream live
    except RedisStreamTruncated:
        pass  # Fall through to event_log catch-up

    # 3. Fall back: replay from event_log table
    while True:
        rows = await pool.fetch(
            """
            SELECT id, event_type, aggregate_type, aggregate_id, payload, created_at
            FROM event_log
            WHERE id > $1 AND event_type IN (SELECT event_type FROM stream_filter WHERE stream = $2)
            ORDER BY id
            LIMIT 1000
            """,
            last_id, stream_name,
        )
        if not rows:
            break  # Caught up from table

        for row in rows:
            await process_event(row)
            last_id = row["id"]
            await update_last_processed(consumer_name, stream_name, last_id)

    # 4. Switch to real-time Redis reads
    while True:
        events = await redis.xread({stream_name: last_id}, block=5000)
        for event in events:
            await process_event(event)
            last_id = event["id"]
            await update_last_processed(consumer_name, stream_name, last_id)
```

This guarantees:
- Real-time latency when healthy (sub-ms Redis)
- Recovery from any downtime (bounded by event_log retention, ~1 year)
- No silent event loss from Redis eviction

### 3.5.6 Outbox Table Partitioning

High-throughput outbox tables need partitioning to manage cleanup and autovacuum.

**Problem at scale:**
- 100 users × 50 chat turns/day = 5K chat events/day
- 1000 users = 50K/day
- 7-day retention before cleanup = 350K rows in `chat_outbox_events`
- Heavy DELETE churn causes bloat in the partial index on `published_at IS NULL`

**Fix: monthly partitioning by `created_at`.**

```sql
-- Parent table (no data)
CREATE TABLE outbox_events (
  id UUID NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  retry_count INT NOT NULL DEFAULT 0,
  last_error TEXT,
  PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Auto-create monthly partitions via pg_partman or manual cron
CREATE TABLE outbox_events_2026_04 PARTITION OF outbox_events
  FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

-- Partial index on current partition (where churn happens)
CREATE INDEX idx_outbox_2026_04_unpublished
  ON outbox_events_2026_04 (created_at)
  WHERE published_at IS NULL;
```

**Cleanup:** `DROP TABLE outbox_events_2026_03` when partition is older than retention.
No DELETE churn, no vacuum pressure, O(1) cleanup.

**Autovacuum tuning for the active partition:**
```sql
ALTER TABLE outbox_events_2026_04 SET (
  autovacuum_vacuum_scale_factor = 0.01,   -- vacuum after 1% dead tuples
  autovacuum_vacuum_cost_delay = 0,        -- no throttling (latency critical)
  autovacuum_analyze_scale_factor = 0.02
);
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

// ── Multi-Tenancy Note ────────────────────────────────
// ALL nodes include user_id for tenant isolation. Every query must filter by user_id.
// Entities also have project_id (new — for KSA project scoping) in addition to book_id.
// See KNOWLEDGE_SERVICE_ARCHITECTURE §3.4 for project/session scoping amendments.

(:Entity { ...,
  user_id: String,
  project_id: String,
  embedding_model: String,       // which curated model produced this entity's embedding
  // Dimension-indexed embedding properties (only ONE is populated per entity)
  embedding_384: [Float],        // populated if embedding_model is 384-dim
  embedding_1024: [Float],       // populated if embedding_model is 1024-dim (default: bge-m3)
  embedding_1536: [Float],       // populated if embedding_model is 1536-dim (OpenAI small)
  embedding_3072: [Float]        // populated if embedding_model is 3072-dim (OpenAI large)
})
(:Event { ..., user_id: String })

// ── Vector Indexes (Neo4j v2026.01) ────────────────────
// Four indexes, one per supported dimension. See KSA §4.3 for supported model list.
// Model change = delete project graph + rebuild (§3.8.3).

CREATE VECTOR INDEX entity_embeddings_384 FOR (e:Entity) ON (e.embedding_384)
OPTIONS { indexConfig: {
  `vector.dimensions`: 384,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX entity_embeddings_1024 FOR (e:Entity) ON (e.embedding_1024)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX entity_embeddings_1536 FOR (e:Entity) ON (e.embedding_1536)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX entity_embeddings_3072 FOR (e:Entity) ON (e.embedding_3072)
OPTIONS { indexConfig: {
  `vector.dimensions`: 3072,
  `vector.similarity_function`: 'cosine'
}};

// Same pattern for events (populated when event_embeddings are enabled)
CREATE VECTOR INDEX event_embeddings_1024 FOR (e:Event) ON (e.embedding_1024)
OPTIONS { indexConfig: { `vector.dimensions`: 1024, `vector.similarity_function`: 'cosine' }};

// ── Composite Indexes for Multi-Tenant Queries (mandatory) ──────

// Entity primary lookup (user_id is always the prefix filter)
CREATE INDEX entity_user_canonical FOR (e:Entity) ON (e.user_id, e.id);
CREATE INDEX entity_user_name FOR (e:Entity) ON (e.user_id, e.name);
CREATE INDEX entity_user_project FOR (e:Entity) ON (e.user_id, e.project_id);
CREATE INDEX entity_project_model FOR (e:Entity) ON (e.project_id, e.embedding_model);

// Event primary lookup
CREATE INDEX event_user_order FOR (e:Event) ON (e.user_id, e.narrative_order);
CREATE INDEX event_user_chapter FOR (e:Event) ON (e.user_id, e.chapter_id);

// Unique constraints (Neo4j enforces uniqueness)
CREATE CONSTRAINT entity_id_unique FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT event_id_unique  FOR (e:Event)  REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT chapter_id_unique FOR (c:Chapter) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT book_id_unique    FOR (b:Book)    REQUIRE b.id IS UNIQUE;

// ── Provenance (EVIDENCED_BY edges) for partial operations ───────
// See KSA §3.4.C and §3.8.5 below for the cascade rules.

(:ExtractionSource {
  id: String,                    // uuidv7
  source_type: String,           // 'chapter' | 'chat_message' | 'glossary_entity' | 'manual'
  source_id: String,             // chapter_id, message_id, etc.
  project_id: String,
  user_id: String
})

(:Entity)-[:EVIDENCED_BY {
  extracted_at: DateTime,
  extraction_model: String,      // which LLM produced this extraction
  confidence: Float,
  job_id: String                 // extraction job that created this edge
}]->(:ExtractionSource)

(:Event)-[:EVIDENCED_BY { ... }]->(:ExtractionSource)
(:Fact)-[:EVIDENCED_BY { ... }]->(:ExtractionSource)

CREATE CONSTRAINT extraction_source_id_unique
    FOR (s:ExtractionSource) REQUIRE s.id IS UNIQUE;
CREATE INDEX extraction_source_by_source_id
    FOR (s:ExtractionSource) ON (s.source_type, s.source_id);
CREATE INDEX extraction_source_project
    FOR (s:ExtractionSource) ON (s.project_id, s.source_type);
```

**Query pattern rule:** Every Cypher query that touches `:Entity`, `:Event`, or
user data MUST include `user_id` as the first filter predicate. Reviewers must
reject any PR that issues a cross-tenant query.

```cypher
-- GOOD (uses entity_user_name index)
MATCH (e:Entity) WHERE e.user_id = $user_id AND e.name = $name RETURN e

-- BAD (full scan across all users)
MATCH (e:Entity {name: $name}) RETURN e
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

## 3.8 Consistency Model & Recovery

Postgres is the source of truth; Neo4j is a derived view. This section documents
the consistency contract and rebuild procedures.

### 3.8.1 Consistency Model

**Postgres writes are strongly consistent:**
- `chapter_drafts`, `chat_messages`, `glossary_entities`, `knowledge_projects`, etc.
- Transactional outbox writes are atomic with the data change.
- Read-after-write: immediate.

**Neo4j writes are eventually consistent:**
- Relay worker publishes events → knowledge-service consumes → writes Neo4j.
- Target lag: p50 < 1s, p95 < 5s, p99 < 30s.
- Read-after-write: **not guaranteed via the event path**. Users may query Neo4j
  and not see changes they just made via Postgres.

**Two write paths to Neo4j:**

| Path | When used | Consistency |
|---|---|---|
| **Async (event pipeline)** | Background mining, chat turn extraction, chapter re-extraction | Eventual (p95 < 5s) |
| **Sync (knowledge-service direct)** | User manually edits an entity in memory UI, user manually adds a fact via "remember this" | Strong — returns after Neo4j write completes |

For user-facing actions that require read-after-write (e.g., "I just told the AI to
remember X, now I ask about X"), chat-service calls knowledge-service synchronously
with a 500ms timeout. For background extraction, async is fine.

### 3.8.2 Consistency SLA

| Operation | Path | SLA |
|---|---|---|
| User manually adds a fact via memory UI | Sync | 200ms p95 |
| User asks about fact in next chat turn | Async after auto-extract | 5s p95 |
| Chapter save → character appears in L2 context | Async | 10s p95 |
| Glossary edit → reflected in Neo4j | Async | 5s p95 |
| Consumer catch-up after 1-hour downtime | Event log replay | Full catch-up within 5 minutes |

**Enforcement:** OpenTelemetry traces span the full path from Postgres write to
Neo4j write. Prometheus metric `knowledge_consumer_lag_seconds{consumer="..."}`
alerts when lag exceeds SLA.

### 3.8.3 Neo4j Rebuild from Event Log

Neo4j must be rebuildable from scratch using only `loreweave_events.event_log`. This
is the disaster recovery story and the "re-embed with new model" story.

**Procedure:**

```python
async def rebuild_neo4j_from_events(
    from_event_id: str = None,
    consumer_name: str = "knowledge-extractor-rebuild",
    batch_size: int = 1000,
):
    """Replay all events from the log to rebuild Neo4j.

    Safe to run on live system — uses a separate consumer name so it doesn't
    conflict with the production consumer. After completion, atomically swap
    the rebuild into place or switch the primary consumer's state.
    """
    # 1. Start from event_id or beginning
    last_id = from_event_id or "00000000-0000-0000-0000-000000000000"

    # 2. Fetch events in uuidv7 order (time-ordered)
    while True:
        rows = await pool.fetch(
            """
            SELECT id, event_type, aggregate_type, aggregate_id, payload, created_at
            FROM event_log
            WHERE id > $1
              AND event_type IN ('chapter.saved', 'chapter.deleted',
                                 'chat.turn_completed', 'glossary.entity_updated',
                                 'knowledge.fact_added')
            ORDER BY id
            LIMIT $2
            """,
            last_id, batch_size,
        )
        if not rows:
            break

        # 3. Process through the same knowledge pipeline (idempotent by design)
        for row in rows:
            await process_event(row)  # uses §3.5.4 idempotency — safe to replay
            last_id = row["id"]

        # 4. Progress tracking
        await update_last_processed(consumer_name, last_id)
        print(f"Rebuilt through {last_id}")
```

**Why this works safely on a running system:**
- §3.5.4 idempotency: re-processing the same event is a no-op in Neo4j
- Deterministic entity IDs: rebuilt entities get the same `id`, so `MERGE` finds them
- `source_event_id` on relationships: duplicate relation writes are no-ops

**When to rebuild:**
1. Neo4j database corruption or restore from older backup
2. Embedding model change (see §7 decision #27)
3. Canonicalization rule change (bump `canonical_version`)
4. Schema migration that can't be done in-place
5. Extraction algorithm improvement (Pass 2 LLM model change)

**Partial rebuild (specific book or project):**
```sql
-- Rebuild only a specific book's entities
UPDATE event_consumers
  SET last_processed_event_id = NULL
  WHERE consumer_name = 'knowledge-extractor-rebuild';

SELECT * FROM event_log
  WHERE payload->>'book_id' = $target_book_id
  ORDER BY id;
```

### 3.8.4 Deletion Cascade

Raw data in Postgres is the source of truth. Derived data in Neo4j must reflect
deletions. Cascade rules:

| Postgres delete | Event | Neo4j effect |
|---|---|---|
| `chapter_drafts` row removed | `chapter.deleted` | Invalidate `(:Event)` nodes tied to chapter; invalidate `(:Fact)` with only-this-chapter provenance |
| `chat_messages` row removed | `chat.message_deleted` (new) | Invalidate facts/entities sourced from this message only |
| `knowledge_projects` row removed | `project.deleted` | Delete project-scoped entities (not global); keep entities referenced by other projects |
| `users` row removed (GDPR) | `user.deleted` | Delete all user-scoped entities, events, facts, embeddings (hard delete) |

**Invariant:** A fact/entity derived solely from deleted source data must be deleted
from Neo4j within 5 minutes of the Postgres deletion. Enforced by consumer watchdog.

**GDPR requirement:** `user.deleted` event must trigger complete user data removal
from Neo4j within 30 days. A daily cleanup job scans for orphaned user data as a
safety net.

### 3.8.5 Provenance Cascade Rules (for partial operations)

LoreWeave supports **partial extraction operations** per KSA §5.5 — users can
re-extract a chapter range, delete a subplot, append new chapters, or pause
and resume extraction. These operations require explicit provenance tracking
via `EVIDENCED_BY` edges (see §3.6).

**Core invariant:** An entity/event/fact is deleted if and only if its
`EVIDENCED_BY` edge count reaches zero. All partial operations reduce to
this single rule.

#### Partial Operation Cascade Table

| Operation | Step 1 | Step 2 | Step 3 |
|---|---|---|---|
| **Append (new chapter saved)** | Create new `:ExtractionSource` | Run extraction → creates new entities (via MERGE) and EVIDENCED_BY edges | (no cleanup needed) |
| **Partial re-extract (ch.123)** | Delete EVIDENCED_BY edges from ch.123's ExtractionSource | Delete entities/events/facts with zero remaining EVIDENCED_BY edges | Re-run extraction on ch.123 current content |
| **Partial delete (ch.400-450)** | Cascade delete ExtractionSource nodes for the range | EVIDENCED_BY edges cascade-delete | Delete entities/events/facts with zero remaining evidence |
| **Stop mid-extraction** | Save cursor position to `extraction_jobs.current_cursor` | Leave all existing EVIDENCED_BY edges untouched | Next run resumes from cursor |
| **Cancel extraction** | Save job status = 'cancelled' | Keep partial graph (all edges intact) | User can resume or rebuild later |
| **Full rebuild** | Delete all ExtractionSource nodes for the project | All provenance edges cascade | Re-run full extraction |
| **Disable extraction (keep graph)** | Set `extraction_enabled = false` | Stop consumer processing | Existing graph stays queryable |
| **Change embedding model** | Warning dialog | Delete all ExtractionSource + entities for the project | User must trigger new extraction with new model |

#### Example Cypher: Partial Re-Extract

```cypher
// Step 1: Remove evidence from chapter 123's source
MATCH (src:ExtractionSource {source_id: 'ch123', project_id: $project_id})
      <-[e:EVIDENCED_BY]-(n)
DELETE e

// Step 2: Delete entities with zero remaining evidence
MATCH (n:Entity)
WHERE n.project_id = $project_id AND NOT (n)-[:EVIDENCED_BY]->()
DETACH DELETE n

// Same for Events and Facts
MATCH (e:Event) WHERE e.user_id = $user_id AND NOT (e)-[:EVIDENCED_BY]->() DETACH DELETE e
MATCH (f:Fact)  WHERE f.user_id = $user_id AND NOT (f)-[:EVIDENCED_BY]->() DETACH DELETE f

// Step 3: Remove the ExtractionSource itself
MATCH (src:ExtractionSource {source_id: 'ch123', project_id: $project_id}) DETACH DELETE src

// Step 4: (application code) trigger new extraction job on ch.123
```

#### Example Cypher: Append (no cleanup)

```cypher
// Chapter 46 saved → extraction runs → MERGE creates new nodes if needed,
// or adds EVIDENCED_BY edges to existing canonical entities.
// No deletion, just additive writes.

MERGE (src:ExtractionSource {id: $source_uuid})
  SET src.source_type = 'chapter',
      src.source_id = 'ch46',
      src.project_id = $project_id,
      src.user_id = $user_id

// For each entity extracted from ch.46
MERGE (e:Entity {id: $canonical_id})
  ON CREATE SET e.name = $display_name, e.project_id = $project_id, ...
MERGE (e)-[r:EVIDENCED_BY]->(src)
  ON CREATE SET r.extracted_at = datetime(),
                r.extraction_model = $model,
                r.confidence = $confidence,
                r.job_id = $job_id
```

#### Why This Works Safely

- **Idempotent:** re-running the same extraction on the same source produces zero new nodes (§3.5.4)
- **Concurrent-safe:** partial delete operations only touch entities with matching provenance, not unrelated ones
- **Recoverable:** at any point the system can rebuild from event_log (§3.8.3)
- **Transparent:** every fact can be traced back to its source via EVIDENCED_BY

---

## 4. Implementation Phases

### Phase D0: Pre-Flight Validation (before any code changes)

> Verify assumptions before committing to the migration. Real tests, not unit tests.

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D0-01 | Infra | Spin up postgres:18-alpine, run ALL 9 service migrations, verify they pass | None | S |
| D0-02 | Infra | Test JSON_TABLE inside PL/pgSQL trigger on PG18 (write test SQL script, run it) | D0-01 | S |
| D0-03 | BE | Test pgx JSONB scanning with json.RawMessage (small Go test program) | D0-01 | S |
| D0-04 | BE | Identify ALL breaking changes in PG16→18 upgrade for our SQL patterns | D0-01 | S |

**GATE:** All 4 pass → proceed to D1. Any failure → fix the approach before building.

If D0-01 reveals migration failures in other services, add refactor tasks to D1.
If D0-02 reveals JSON_TABLE doesn't work in triggers, switch to application-level extraction.
If D0-04 reveals breaking SQL patterns, document each and add refactor tasks.

### Phase D1: Schema + Event Infrastructure (blocks everything)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D1-01 | Infra | Upgrade Postgres 16 → 18, add Redis, add `loreweave_events` DB to db-ensure.sh | D0 gate | S |
| D1-02 | BE | Clean schema: all tables use uuidv7 (books, chapters, revisions, etc), chapter_drafts (JSONB), chapter_revisions (JSONB + format). Refactor any PG18-incompatible SQL found in D0. | D1-01 | M |
| D1-03 | BE | Create chapter_blocks table + UPSERT extraction trigger (JSON_TABLE + `_text`) | D1-02 | M |
| D1-04 | BE | Create outbox_events table (in loreweave_book) + pg_notify trigger | D1-02 | S |
| D1-05 | BE | Create loreweave_events schema (event_log, event_consumers, dead_letter_events) | D1-01 | S |
| D1-06 | BE | book-service: refactor ALL 8 body-touching handlers to use json.RawMessage for JSONB. Full handler list: patchDraft, getDraft, getRevision, restoreRevision, exportChapter, getChapterContent, getInternalBookChapter, listRevisions. Rewrite broken unit tests. | D1-02, D1-04 | L |
| D1-07 | BE | book-service: createChapter converts plain text → Tiptap JSON at import (with `_text` snapshots) | D1-06 | S |
| D1-08 | BE | book-service: getInternalBookChapter adds `text_content` field (aggregated from chapter_blocks). Translation worker unchanged — reads `text_content` instead of `body`. | D1-03, D1-06 | S |
| D1-09 | BE | worker-infra service scaffold: Go project, task registry (ListenTask, CronTask, ConsumerTask), Dockerfile, service discovery config for outbox source DBs | D1-04, D1-05 | M |
| D1-10 | BE | worker-infra: outbox-relay task (LISTEN + poll, publish to Redis Stream + event_log) + outbox-cleanup task (cron daily) | D1-09 | M |
| D1-11 | FE | Frontend: save Tiptap JSON with `_text` snapshots, load JSONB directly, remove plainTextToHtml/htmlToPlainText legacy code | D1-06 | M |
| D1-12 | BE+FE | Integration test: create → save → verify blocks + event_log + Redis event + getInternalBookChapter text_content | D1-03, D1-08, D1-10, D1-11 | S |

**GATE:** After D1-12, chapter content saves as JSONB with `_text` snapshots. Blocks auto-extracted via UPSERT trigger. Events guaranteed via outbox → worker-infra relay → Redis Stream + event_log. Internal API returns `text_content` for downstream services.

**Notes:**
- D1-06 is the largest task (L) — 8 handlers to refactor + test rewrites. May split into sub-tasks.
- D1-09 includes service discovery config: `OUTBOX_SOURCES` env var lists DB connection strings.
  Future: replace with proper service registry if scaling to many services.
- Existing translation-worker is NOT changed in D1. It reads `text_content` from the updated internal API (D1-08).

### Phase D2: Neo4j Infrastructure (can parallel with D1-05+)

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D2-01 | Infra | Add Neo4j v2026.01 to docker-compose | None | S |
| D2-02 | BE | knowledge-service scaffold (Python/FastAPI, connects to Neo4j + Postgres + Redis) | D2-01 | M |
| D2-03 | BE | Neo4j schema init: constraints (§3.6), vector indexes (§3.6 + §7 #27 dimension), composite indexes on `(user_id, ...)`. Mandatory per §3.6 query rule. | D2-01 | S |
| D2-04 | BE | Self-hosted embedding model service (BAAI/bge-m3 or multilingual-e5-large) as a task in worker-ai or standalone container. See §7 decision #27. | D2-01 | M |

### Phase D3: Knowledge Pipeline (future — after D1 + D2, gated by per-project opt-in)

**Important:** Per decision #34, extraction is opt-in per project. D3 tasks build
the **infrastructure** for extraction, but the infrastructure only runs on projects
where the user has explicitly enabled extraction via KSA §5.5 Extraction Jobs.

All D3 consumers must check `knowledge_projects.extraction_enabled` before
processing events. Events for disabled projects go to `extraction_pending` queue
(KSA §3.3) for later backfill.

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| D3-00 | BE | **Idempotency layer (blocker for all other D3 tasks).** Canonicalization function (§3.5.4 Rule 1), deterministic entity ID generator, `source_event_id` pattern on relation writes. Unit tests for canonicalization edge cases. | D2-02 | M |
| D3-01 | BE | Entity extraction: LLM NER + coreference → Neo4j entities (uses D3-00 canonicalization). **Gated by `extraction_enabled`.** | D3-00, D1-08 | L |
| D3-02 | BE | Event extraction: LLM → Neo4j events + temporal ordering. **Gated.** | D3-01 | L |
| D3-03 | BE | Relation extraction: LLM → Neo4j relationship edges (uses D3-00 idempotency keys). **Gated.** | D3-01 | M |
| D3-04 | BE | Fact extraction: atomic statements with provenance via EVIDENCED_BY edges (§3.8.5). **Gated.** | D3-03 | M |
| D3-05 | BE | Embedding generation: embed entities + events → Neo4j vector indexes. **Uses D2-04 embedding service, routes to dimension-indexed property based on project's chosen model (KSA §4.3).** | D3-01, D2-04 | M |
| D3-06 | BE | Glossary-service evolution: read from Neo4j, user curates AI suggestions. Also maintains `short_description` field for chat fallback (KSA §4.2.5). | D3-01 | L |
| D3-07 | BE | **Backfill for chapters + pending queue:** process historical `chapter_drafts` AND drain `extraction_pending` table for the project. Progress tracking with cost cap (KSA §5.5). | D3-01, D3-05 | M |
| D3-08 | BE | Neo4j rebuild tool: CLI/API that replays `event_log` to reconstruct Neo4j from scratch (§3.8.3). Supports project-scoped rebuild (not full system-wide). Used for disaster recovery and embedding model migration. | D3-01, D3-05 | M |
| D3-09 | BE | **Extraction Job engine:** scope handling (`chapters` / `chat` / `glossary_sync` / `all`), cursor-based resume, pause/cancel, `max_spend_usd` enforcement, progress updates via event_log. KSA §5.5. | D3-01..04, D3-07 | L |

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
| **docker-compose** | Postgres 16→18, add Redis, add Neo4j v2026.01, add worker containers | Phase D1 + D2 |
| **book-service** (Go) | JSONB body, outbox pattern, json.RawMessage, plain→JSON import | Phase D1 |
| **worker-infra** (Go, NEW) | Task registry, outbox-relay, outbox-cleanup, future tasks | Phase D1 |
| **worker-ai** (Python, NEW) | Absorbs translation-worker, adds knowledge + embedding tasks | Phase D2-D3 |
| **knowledge-service** (Python, NEW) | Consumes Redis events, LLM extraction, writes Neo4j → becomes tasks in worker-ai | Phase D3 |
| **glossary-service** (Go) | Evolves to read from Neo4j, keeps manual CRUD | Phase D3 |
| **chat-service** (Python) | Adds RAG: hybrid graph+vector query via Neo4j | Phase D4 |
| **frontend-v2** | Save Tiptap JSON with `_text` snapshots, load JSONB directly | Phase D1 |

---

## 6. Migration Strategy

**Clean break.** Drop all databases and recreate. No production data exists.

Steps:
1. Stop all services
2. Remove old Postgres volumes (`docker volume rm ...`)
3. Update docker-compose: Postgres 18 (PGDATA), add Redis
4. `docker-compose up -d postgres redis` — creates fresh PG18 + Redis
5. Run migration (all services auto-migrate on startup, all tables use uuidv7)
6. Deploy updated book-service (outbox worker starts automatically)
7. Deploy updated frontend (sends Tiptap JSON with `_text` snapshots)
8. Verify: create chapter → save → check `chapter_blocks` rows (UPSERT)
9. Verify: check `outbox_events` has row with `published_at` set
10. Verify: `redis-cli XRANGE loreweave:events:chapter - +` shows event

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
| 16 | **Transactional Outbox pattern** (replaces best-effort) | Event written in same Postgres tx as data. Worker publishes to Redis. At-least-once delivery guaranteed. No data loss in event pipeline. Each service owns its own outbox table. | 2026-03-31 |
| 17 | **Redis Stream `MAXLEN ~ 10000`** | Auto-trim old events. Prevents unbounded growth. Older events re-derivable from database. | 2026-03-31 |
| 18 | **`chapter_raw_objects` unchanged** | Stays as `TEXT`. Preserves raw import, never edited. No schema change needed. | 2026-03-31 |
| 19 | **Shared `loreweave_events` database** | Centralized event store with permanent log, consumer tracking, dead letter queue. Each service keeps local outbox (same-tx atomicity), relay worker writes to shared events DB after publish. | 2026-03-31 |
| 20 | **Two-worker architecture** (worker-infra + worker-ai) | Split by language (Go/Python) and resource profile (lightweight I/O vs heavy GPU). Configurable via `WORKER_TASKS` env var. Same binary scales by adding containers with different task selection. | 2026-03-31 |
| 21 | **worker-ai absorbs translation-worker** | Existing `translation-worker` container becomes a task in worker-ai. One less Dockerfile, unified task registry. | 2026-03-31 |
| 22 | **Phase D0 pre-flight validation** | Test PG18 compat, JSON_TABLE in triggers, pgx JSONB scanning BEFORE building. Real tests, not assumptions. Prevents days of debugging. | 2026-04-01 |
| 23 | **Accept full refactor of book-service** | All 8 body-touching handlers refactored for JSONB. Broken tests removed and rewritten. Big change accepted. | 2026-04-01 |
| 24 | **Internal API adds `text_content` field** (Option C) | `getInternalBookChapter` returns both JSONB `body` + plain `text_content` (from chapter_blocks). Downstream services pick what they need. Translation worker reads `text_content`, unchanged. | 2026-04-01 |
| 25 | **Trust frontend `_text` snapshots** | No server-side validation. Frontend is authority on editor content. Add unit test on `extractText` to prevent regressions. | 2026-04-01 |
| 26 | **Service discovery for worker-infra** | `OUTBOX_SOURCES` env var: `book:postgres://...loreweave_book,glossary:postgres://...loreweave_glossary`. Future: proper service registry when scaling beyond docker-compose. | 2026-04-01 |
| 27 | **Server-chosen embedding model** (not BYOK) | Vector spaces are model-specific — mixing models breaks similarity queries. Self-host one embedding model (`BAAI/bge-m3` or `intfloat/multilingual-e5-large`, 1024-dim, multilingual, free). BYOK for LLMs stays intact; embedding is a platform capability. Neo4j vector index dimension is fixed at deployment; model changes require §3.8.3 rebuild. | 2026-04-13 |
| 28 | **Consumer idempotency is mandatory** (§3.5.4) | At-least-once delivery + non-deterministic LLM output requires explicit idempotency. Rules: deterministic node IDs from canonicalized names, `source_event_id` on relation writes, `canonical_version` for migration. D3-00 is a blocker for all other D3 tasks. | 2026-04-13 |
| 29 | **Hybrid consumer catch-up** (§3.5.5) | Redis Streams have bounded retention; consumers fall back to `event_log` table when Redis has evicted events. Prevents silent data loss during extended consumer downtime. Implemented once in a shared helper, reused by all AI consumers. | 2026-04-13 |
| 30 | **Outbox table partitioning by month** (§3.5.6) | High-throughput outbox tables (chat at 50K events/day) need partitioning to avoid DELETE churn and vacuum pressure. `DROP PARTITION` replaces `DELETE WHERE old`. Monthly granularity. Autovacuum tuned per-partition for the active month. | 2026-04-13 |
| 31 | **Neo4j multi-tenant query rule** (§3.6) | Every Cypher query on `:Entity`/`:Event` must filter by `user_id` as the first predicate. Enforced via composite indexes `entity_user_*`. PR review rejects any cross-tenant query. Alternative (database-per-user) requires Enterprise license — not justified at current scale. | 2026-04-13 |
| 32 | **Postgres SSOT deletion cascades to Neo4j** (§3.8.4) | Raw data is authoritative; derived data in Neo4j must reflect deletions within SLA. `chapter.deleted`, `chat.message_deleted`, `project.deleted`, `user.deleted` events drive Neo4j cleanup. Daily orphan-scan watchdog as safety net. | 2026-04-13 |
| 33 | **Rebuild-from-event-log is a first-class feature** (§3.8.3) | Neo4j must be reconstructible from `event_log`. Enables disaster recovery, embedding model migration, canonicalization rule changes, and algorithm improvements without data loss. D3-08 delivers the rebuild tool. | 2026-04-13 |
| 34 | **Opt-in extraction (not automatic)** | Knowledge graph extraction is disabled by default per project (`knowledge_projects.extraction_enabled = false`). No LLM calls happen for a project until the user explicitly triggers an Extraction Job (KSA §5.5). Prevents surprise AI bills. | 2026-04-13 |
| 35 | **Events queued when extraction disabled** (KSA §5.3) | When extraction is off for a project, knowledge-service still receives events but queues them in `extraction_pending` table instead of processing. When user enables extraction later, backfill processes the queue. Enables "opt-in with full history" flow. | 2026-04-13 |
| 36 | **Glossary fallback for static memory** (KSA §4.2.5) | When extraction is disabled, chat uses Postgres FTS to select top-20 relevant glossary entities per query, plus `short_description` field for compact injection. Provides free "dumb but useful" memory using already-curated user data. | 2026-04-13 |
| 37 | **Curated embedding model list (not open BYOK)** (KSA §4.3) | Users select from a vetted list of 5 embedding models (bge-m3, text-embedding-3-small/large, voyage-3, embed-english-v3). Supports 4 dimensions (384, 1024, 1536, 3072) with one Neo4j vector index per dimension. Extending the list adds a model config entry, not a schema change. | 2026-04-13 |
| 38 | **Per-project embedding model** (KSA §4.3) | Each project picks its own embedding model. Different dimensions stored in dimension-indexed Neo4j properties (`embedding_384`, `embedding_1024`, etc.). Changing model = delete project graph + rebuild (with warning). No cross-model semantic search. | 2026-04-13 |
| 39 | **Provenance edges (EVIDENCED_BY) for partial operations** (§3.8.5, KSA §3.4.C) | Every extracted entity/event/fact has EVIDENCED_BY edges to its sources. Partial re-extraction, append, and delete operations are reduced to a single invariant: "delete if evidence count reaches zero." Enables safe incremental extraction for live novels. | 2026-04-13 |
| 40 | **L0 and L1 are plain text (no embeddings)** (KSA §4.0-4.1) | Global identity and project context are always-loaded short summaries stored as plain text in Postgres `knowledge_summaries`. No embedding model needed. Works identically regardless of per-project embedding choices. Only L2/L3 use embeddings. | 2026-04-13 |
| 41 | **Honest "Trust Me" privacy model** (KSA §7.7) | Hobby project acknowledges no SOC 2, no HIPAA BAA, no enterprise audit. Relies on BYOK (user's AI provider account), self-hosting, local-first defaults, and open source code for trust. Documented honestly rather than marketed. Enterprise escape hatch requires separate engineering effort. | 2026-04-13 |

---

## 8. Review Notes

> Review 1 (schema design): 2026-03-31
> Review 2 (pre-flight concerns): 2026-04-01
> All findings incorporated into the plan above.

### Review 1: Schema Design Issues

| # | Issue | Severity | Resolution |
|---|-------|----------|------------|
| 1 | JSON_TABLE `$.content[0].text` misses formatted text | **Critical** | Frontend adds `_text` snapshot per block (Decision #12). |
| 2 | Go pgx JSONB → base64 in API response | **High** | `json.RawMessage` for body field (Decision #15). |
| 3 | DELETE+INSERT trigger loses block IDs | **Medium** | UPSERT on `(chapter_id, block_index)` (Decision #13). |
| 4 | Redis publish failure = lost event | **Medium** | Transactional Outbox pattern (Decision #16). |
| 5 | Plain text dual-mode in JSONB | **Medium** | Convert to Tiptap JSON at import (Decision #14). |
| 6 | No Redis Stream retention | **Low** | `MAXLEN ~ 10000` (Decision #17). |
| 7 | uuidv7 not applied everywhere | **Low** | Apply to ALL tables in clean break (Decision #5). |
| 8 | chapter_raw_objects not mentioned | **Low** | Stays TEXT, unchanged (Decision #18). |

### Review 2: Pre-Flight Concerns

| # | Concern | Severity | Resolution |
|---|---------|----------|------------|
| C1 | PG18 compat with all 9 services | **Blocker** | Phase D0: test all migrations. Accept full refactor (Decision #22, #23). |
| C2 | JSON_TABLE in PL/pgSQL trigger untested | **High** | D0-02: write + run test SQL on PG18 before D1-03 (Decision #22). |
| C3 | 8 handlers touch `body` — all need refactoring | **High** | D1-06 expanded to L-size. Full handler list documented (Decision #23). |
| C4 | exportChapter + getChapterContent need plain text | **High** | Extract from chapter_blocks. Added to D1-06 scope. |
| C5 | getInternalBookChapter — translation expects string | **High** | Add `text_content` field to response (Decision #24). D1-08. |
| C6 | `_text` snapshot integrity | **Low** | Trust frontend. Unit test extractText (Decision #25). |
| C7 | Worker-infra multi-DB connections | **Low** | Service discovery via `OUTBOX_SOURCES` env var (Decision #26). |
| C8 | Existing unit tests will break | **Medium** | Remove and rewrite. Scoped into D1-06. |

---

## 9. Future Considerations

| Item | Trigger | Action |
|---|---|---|
| Add Qdrant as dedicated vector DB | Neo4j vector search latency >100ms at >500K embeddings | Add Qdrant container, new Pipeline 3, move embeddings |
| Add Elasticsearch/Meilisearch | Public catalog needs full-text search with facets | New Pipeline 4, consumer for Redis events |
| pgvector on Postgres | Need vector search on chapter_blocks without Neo4j round-trip | Add pgvector extension, hybrid search in SQL |
| Multi-book knowledge linking | Cross-book entity resolution (same character in series) | Neo4j cross-book relationship edges |
| Real-time collaboration | Multiple users editing same chapter | CRDT/OT layer, conflict resolution, WebSocket |
