# Data Re-Engineering — Detailed Task Breakdown

> **Parent plan:** `101_DATA_RE_ENGINEERING_PLAN.md`
> **Created:** 2026-04-01
> **Method:** Impact-first discovery cycles. Each cycle picks a task, traces all affected files, creates sub-tasks.

---

## Discovery Cycle 1: Postgres 18 Upgrade + uuidv7 Migration

### Impact Map

**9 migration files** need `gen_random_uuid()` → `uuidv7()`:

| Service | File | Tables | pgcrypto Used For |
|---------|------|--------|-------------------|
| auth-service | `internal/migrate/migrate.go` | 4 tables | only `gen_random_uuid()` |
| book-service | `internal/migrate/migrate.go` | 3 tables | only `gen_random_uuid()` |
| sharing-service | `internal/migrate/migrate.go` | 0 (FKs only) | only extension line |
| catalog-service | `internal/migrate/migrate.go` | 0 (TEXT PK) | not used |
| provider-registry | `internal/migrate/migrate.go` | 5 tables | only `gen_random_uuid()` |
| usage-billing | `internal/migrate/migrate.go` | 3 tables | only `gen_random_uuid()` |
| glossary-service | `internal/migrate/migrate.go` | 8 tables | only `gen_random_uuid()` |
| translation-service | `app/migrate.py` | 3 tables | not used |
| chat-service | `app/db/migrate.py` | 3 tables | not used |

**Total: 29 tables across 9 services. pgcrypto only used for `gen_random_uuid()` — safe to replace with `uuidv7()`.**

**Note:** Encryption in auth-service, provider-registry, usage-billing uses Go `crypto/*` packages (application-level), NOT Postgres `pgcrypto`. No impact from removing the extension.

### Infrastructure Impact

| File | Change |
|------|--------|
| `infra/docker-compose.yml` | `postgres:16-alpine` → `postgres:18-alpine`, add `PGDATA` env, add Redis service |
| `infra/db-ensure.sh` | Add `loreweave_events` database |
| Docker volumes | Delete `loreweave_pg` volume (clean break, PG18 data format incompatible) |

---

## Detailed Sub-Tasks

### D0: Pre-Flight Validation

```
D0-01  Spin up postgres:18-alpine, test uuidv7() and JSON_TABLE availability
       Files: none (manual psql test)
       Test: SELECT uuidv7();
             SELECT * FROM JSON_TABLE('{"a":1}'::jsonb, '$' COLUMNS (a INT PATH '$.a')) AS jt;
       Pass/fail gate: both must return results

D0-02  Run ALL 9 service migrations against PG18
       Method: start PG18, create all DBs, run each service with migration-only mode
       or manually execute migration SQL from each migrate.go/migrate.py
       Files to read: all 9 migration files listed above
       Pass/fail: all CREATE TABLE statements succeed

D0-03  Test JSON_TABLE inside PL/pgSQL trigger function
       File: create test SQL script (new file: infra/test-pg18-features.sql)
       Test: CREATE TABLE + trigger using JSON_TABLE + INSERT + verify extracted data
       Pass/fail: trigger fires, data extracted correctly

D0-04  Test pgx v5 JSONB scanning with json.RawMessage
       File: create test Go program (new file: services/book-service/cmd/pg18test/main.go)
       Test: INSERT JSONB → SELECT → scan as json.RawMessage → json.Marshal → verify inline JSON
       Pass/fail: response contains inline JSON object, not base64 string
```

### D1-01: Postgres 18 + Redis in docker-compose

```
D1-01a  Update docker-compose Postgres image + config
        File: infra/docker-compose.yml
        Changes:
          - image: postgres:16-alpine → postgres:18-alpine
          - Add: PGDATA: /var/lib/postgresql/18/docker
          - Volume stays: loreweave_pg:/var/lib/postgresql

D1-01b  Add Redis service to docker-compose
        File: infra/docker-compose.yml
        Add:
          redis:
            image: redis:7-alpine
            ports: ["6399:6379"]
            volumes: [loreweave_redis:/data]
            healthcheck: redis-cli ping
        Add volume: loreweave_redis

D1-01c  Add loreweave_events database to db-ensure.sh
        File: infra/db-ensure.sh
        Add: loreweave_events to DATABASES list

D1-01d  Delete old Postgres volume (documented step, not code)
        Command: docker volume rm infra_loreweave_pg
        Note: This is a manual step during migration execution
```

### D1-02: Clean Schema — uuidv7 everywhere + JSONB body

```
D1-02a  auth-service migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/auth-service/internal/migrate/migrate.go
        Changes: 4 table PKs, remove CREATE EXTENSION pgcrypto line

D1-02b  book-service migration: gen_random_uuid() → uuidv7(), JSONB body, drop pgcrypto
        File: services/book-service/internal/migrate/migrate.go
        Changes:
          - 3 table PKs → uuidv7()
          - chapter_drafts.body: TEXT → JSONB
          - chapter_drafts.draft_format: DEFAULT 'plain' → DEFAULT 'json'
          - chapter_revisions: add body_format column, id → uuidv7()
          - chapter_revisions.body: TEXT → JSONB
          - Add virtual column: block_count
          - Remove pgcrypto

D1-02c  sharing-service migration: drop pgcrypto
        File: services/sharing-service/internal/migrate/migrate.go
        Changes: remove CREATE EXTENSION pgcrypto (no tables use UUID gen)

D1-02d  provider-registry migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/provider-registry-service/internal/migrate/migrate.go
        Changes: 5 table PKs, remove pgcrypto

D1-02e  usage-billing migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/usage-billing-service/internal/migrate/migrate.go
        Changes: 3 table PKs, remove pgcrypto

D1-02f  glossary-service migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/glossary-service/internal/migrate/migrate.go
        Changes: 8 table PKs, remove pgcrypto

D1-02g  translation-service migration: gen_random_uuid() → uuidv7()
        File: services/translation-service/app/migrate.py
        Changes: 3 table PKs (no pgcrypto to remove)

D1-02h  chat-service migration: gen_random_uuid() → uuidv7()
        File: services/chat-service/app/db/migrate.py
        Changes: 3 table PKs (no pgcrypto to remove)

D1-02i  Verify: start all services, migrations run, all healthchecks pass
```

---

## Cycle 1 Summary

| Phase | Sub-tasks | New files | Modified files |
|-------|-----------|-----------|---------------|
| D0 | 4 | 2 (test scripts) | 0 |
| D1-01 | 4 | 0 | 2 (docker-compose, db-ensure.sh) |
| D1-02 | 9 | 0 | 9 (all migration files) |
| **Total** | **17** | **2** | **11** |

---

---

## Discovery Cycle 2: D1-03 — chapter_blocks + UPSERT Trigger

### Tiptap Block Type Catalog

All block types our editor can produce (StarterKit + CalloutExtension):

```
Block Type      │ Content Model       │ Attrs             │ _text Source
────────────────┼─────────────────────┼───────────────────┼─────────────────────
paragraph       │ inline*             │ none              │ concatenate text nodes
heading         │ inline*             │ { level: 1|2|3 }  │ concatenate text nodes
bulletList      │ listItem+           │ none              │ recursive: listItem → paragraph → text
orderedList     │ listItem+           │ none              │ recursive: listItem → paragraph → text
blockquote      │ block+              │ none              │ recursive: paragraph → text
horizontalRule  │ (empty)             │ none              │ "" (empty string)
callout         │ inline*             │ { type: note|... }│ concatenate text nodes
hardBreak       │ (inline, not block) │ none              │ "\n" (inside paragraph)
```

### JSON Examples for Each Block Type

```json
// paragraph (simple)
{ "type": "paragraph", "_text": "Hello world", "content": [
    { "type": "text", "text": "Hello world" }
]}

// paragraph (with marks)
{ "type": "paragraph", "_text": "Hello bold italic", "content": [
    { "type": "text", "text": "Hello " },
    { "type": "text", "marks": [{"type": "bold"}], "text": "bold" },
    { "type": "text", "text": " " },
    { "type": "text", "marks": [{"type": "italic"}], "text": "italic" }
]}

// heading
{ "type": "heading", "attrs": { "level": 2 }, "_text": "Chapter One", "content": [
    { "type": "text", "text": "Chapter One" }
]}

// bulletList (nested)
{ "type": "bulletList", "_text": "Item 1\nItem 2\nItem 3", "content": [
    { "type": "listItem", "content": [
        { "type": "paragraph", "content": [{ "type": "text", "text": "Item 1" }] }
    ]},
    { "type": "listItem", "content": [
        { "type": "paragraph", "content": [{ "type": "text", "text": "Item 2" }] }
    ]},
    { "type": "listItem", "content": [
        { "type": "paragraph", "content": [{ "type": "text", "text": "Item 3" }] }
    ]}
]}

// blockquote (nested)
{ "type": "blockquote", "_text": "To be or not to be", "content": [
    { "type": "paragraph", "content": [
        { "type": "text", "text": "To be or not to be" }
    ]}
]}

// horizontalRule (no content)
{ "type": "horizontalRule", "_text": "" }

// callout (custom)
{ "type": "callout", "attrs": { "type": "warning" }, "_text": "This is a note", "content": [
    { "type": "text", "text": "This is a note" }
]}
```

### Trigger Edge Cases

| Edge Case | Input | Expected `text_content` | Handling |
|-----------|-------|------------------------|----------|
| Empty paragraph | `{ "type": "paragraph" }` | `""` | COALESCE(_text, '') |
| Paragraph with only hardBreak | `{ "type": "paragraph", "content": [{"type": "hardBreak"}] }` | `""` | _text won't include hardBreak text |
| horizontalRule | `{ "type": "horizontalRule" }` | `""` | No `_text` field, COALESCE to '' |
| Empty document | `{ "type": "doc", "content": [] }` | No rows | JSON_TABLE returns 0 rows |
| Missing `_text` field | `{ "type": "paragraph", "content": [...] }` | `""` | COALESCE(PATH '$._text', '') — NULL handling |
| Very long paragraph (50KB) | Large text block | Full text stored | TEXT has no length limit |
| Unicode (CJK, emoji) | `{ "_text": "你好世界 🌍" }` | `"你好世界 🌍"` | PG TEXT handles UTF-8 natively |
| Block count = 0 | Empty `content: []` | No blocks, cleanup deletes old | DELETE WHERE block_index >= 0 (deletes all) |
| Block count shrinks (edit removes paragraphs) | Was 10 blocks, now 5 | 5 rows remain | DELETE WHERE block_index >= new_count |

### heading_context Window Function Analysis

The trigger fills `heading_context` with the nearest preceding heading text:

```
block_index │ block_type  │ text_content      │ heading_context
────────────┼─────────────┼───────────────────┼─────────────────
0           │ heading     │ "Chapter One"     │ "Chapter One"
1           │ paragraph   │ "First para..."   │ "Chapter One"
2           │ paragraph   │ "Second para..."  │ "Chapter One"
3           │ heading     │ "Part Two"        │ "Part Two"
4           │ paragraph   │ "Third para..."   │ "Part Two"
5           │ callout     │ "Author note"     │ "Part Two"
6           │ horizontalRule │ ""              │ "Part Two"
```

Edge case: no heading exists → `heading_context` is NULL for all blocks. This is correct.

### Downstream Consumers of chapter_blocks

| Consumer | How it reads | What it needs |
|----------|-------------|---------------|
| D1-08: getInternalBookChapter | `SELECT string_agg(text_content, E'\n\n' ORDER BY block_index) FROM chapter_blocks` | `text_content` concatenated |
| D1-06: exportChapter | Same as above | Plain text export |
| D1-06: getChapterContent | Same as above | Reader view |
| D3: Knowledge extraction | `SELECT text_content, block_type, heading_context FROM chapter_blocks WHERE chapter_id = $1` | Per-block text + metadata |
| D4: Embedding pipeline | `SELECT id, text_content, content_hash FROM chapter_blocks WHERE updated_at > $1` | Changed blocks only |
| Future: search indexer | `SELECT text_content FROM chapter_blocks WHERE chapter_id = $1` | Full text |

### Sub-Tasks

```
D1-03a  Create chapter_blocks table DDL
        File: services/book-service/internal/migrate/migrate.go
        Schema: id (uuidv7), chapter_id (FK CASCADE), block_index, block_type,
                text_content, content_hash, heading_context, attrs (JSONB), updated_at
        Indexes: (chapter_id), (content_hash), (block_type), UNIQUE(chapter_id, block_index)

D1-03b  Create fn_extract_chapter_blocks() trigger function
        File: services/book-service/internal/migrate/migrate.go (appended to schemaSQL)
        Logic:
          1. INSERT ... FROM JSON_TABLE(NEW.body, '$.content[*]') reading _text
             ON CONFLICT (chapter_id, block_index) DO UPDATE (UPSERT)
             - updated_at changes only when content_hash differs
          2. DELETE blocks where block_index >= extracted count
          3. UPDATE heading_context via window function
        Edge cases handled:
          - Missing _text → COALESCE to ''
          - Empty doc → no inserts, all old blocks deleted
          - horizontalRule → empty text, type preserved

D1-03c  Create trg_extract_blocks trigger
        File: same migration file
        Trigger: AFTER INSERT OR UPDATE OF body ON chapter_drafts FOR EACH ROW

D1-03d  Write PG18 test script for the trigger
        File: infra/test-pg18-trigger.sql (new, also covers D0-03)
        Test cases:
          1. Insert draft with 3 paragraphs → verify 3 rows in chapter_blocks
          2. Update draft (change paragraph 2) → verify only block 1 has new updated_at
          3. Update draft (remove paragraph 3) → verify only 2 rows remain
          4. Insert draft with heading + paragraphs → verify heading_context filled
          5. Insert draft with empty content → verify 0 rows
          6. Insert draft with bulletList → verify _text captured correctly
          7. Insert draft with horizontalRule → verify empty text, type preserved
          8. Insert draft with Unicode → verify text preserved
```

### File Impact Summary (Cycle 2)

| File | Change | New? |
|------|--------|------|
| `services/book-service/internal/migrate/migrate.go` | Add chapter_blocks DDL + trigger function + trigger | No (modify) |
| `infra/test-pg18-trigger.sql` | Test script for trigger validation | Yes |

---

## Remaining Cycles

| Cycle | Focus | Tasks |
|-------|-------|-------|
| 3 | D1-04 + D1-05: outbox + events schema | outbox table, events DB schema, pg_notify |
| 4 | D1-06: book-service JSONB refactor | All 8 handlers line by line, test rewrites |
| 5 | D1-07 + D1-08: createChapter + internal API | Plain text import, text_content field |
| 6 | D1-09 + D1-10: worker-infra service | Go project scaffold, task registry, relay |
| 7 | D1-11: Frontend JSONB save/load | _text snapshots, TiptapEditor changes |
| 8 | D1-12: Integration test | End-to-end verification |
