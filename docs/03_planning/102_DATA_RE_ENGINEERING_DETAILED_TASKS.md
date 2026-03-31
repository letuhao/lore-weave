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

---

## Discovery Cycle 3: D1-04 + D1-05 — Outbox + Events Database

### Event Source Map (book-service mutations)

Every mutation handler in book-service, whether it needs an outbox event, and the transaction model:

| Handler | Mutation | Has TX? | Event Type | Needed in D1? |
|---------|----------|---------|------------|---------------|
| `patchDraft` (L1188) | UPDATE chapter_drafts, INSERT revision | **Yes** | `chapter.saved` | **Yes** |
| `createChapterRecord` (L821) | INSERT chapter + draft + revision | **Yes** | `chapter.created` | **Yes** |
| `restoreRevision` (L1342) | UPDATE draft, INSERT revision | **Yes** | `chapter.saved` | **Yes** |
| `transitionChapterLifecycle` (L1000) trash | UPDATE chapters | **No** ← needs refactor | `chapter.trashed` | **Yes** |
| `transitionChapterLifecycle` (L1014) purge | UPDATE chapters | **No** ← needs refactor | `chapter.deleted` | **Yes** |
| `transitionChapterLifecycle` (L1007) restore | UPDATE chapters | **No** ← needs refactor | `chapter.restored` | No (future) |
| `createBook` | INSERT books | No | `book.created` | No (future) |
| `patchBook` | UPDATE books | No | `book.updated` | No (future) |
| `transitionBookLifecycle` | UPDATE books + chapters | No | `book.trashed/deleted` | No (future) |
| `patchChapter` | UPDATE chapters (metadata) | No | — | No (metadata only) |
| `uploadCover` / `deleteCover` | cover assets | No | — | No |

**Key finding:** `transitionChapterLifecycle` uses direct `pool.Exec()` — no transaction.
Must refactor to use BEGIN/COMMIT to include outbox INSERT atomically.

### Outbox Event Types for D1

```
chapter.created   { book_id, chapter_id, body_format, user_id }
chapter.saved     { book_id, chapter_id, draft_version, body_format, block_count, user_id }
chapter.trashed   { book_id, chapter_id, user_id }
chapter.deleted   { book_id, chapter_id, user_id }
```

### Outbox Write Points (5 total)

| # | Handler | Line | Where to Insert Outbox |
|---|---------|------|----------------------|
| 1 | `patchDraft` | L1188-1191 | Inside existing tx, before COMMIT |
| 2 | `createChapterRecord` | L821-824 | Inside existing tx, before COMMIT |
| 3 | `restoreRevision` | L1342-1345 | Inside existing tx, before COMMIT |
| 4 | `transitionChapterLifecycle` (trash) | L1000 | **NEW tx needed** — wrap exec + outbox |
| 5 | `transitionChapterLifecycle` (purge) | L1014 | **NEW tx needed** — wrap exec + outbox |

### Events Database: Who Manages the Schema?

The `loreweave_events` database is **shared** — not owned by any single service.
The schema must be created before any worker reads from it.

**Options:**
1. **worker-infra runs the migration** — the relay worker creates tables on startup
2. **Standalone migration script** — run once during setup
3. **db-ensure.sh extended** — add SQL init for events DB

**Decision:** Option 1 — worker-infra owns the events DB schema. It runs migration on startup, same pattern as all other services.

### Server Struct Changes

```go
// Current:
type Server struct {
    pool   *pgxpool.Pool    // loreweave_book database
    cfg    *config.Config
    secret []byte
}

// No Redis needed! Outbox pattern means book-service only writes to Postgres.
// Redis is the worker-infra's concern.
```

**No Redis dependency in book-service.** The outbox INSERT is just a Postgres write.
The worker-infra reads the outbox and publishes to Redis. This is the whole point of the outbox pattern — the service doesn't know about Redis.

### Config Changes

```go
// No new config needed for book-service!
// The outbox table lives in the same database (loreweave_book).
// No new connection strings, no new environment variables.
```

### Helper Function Design

To avoid duplicating outbox INSERT logic in 5 handlers:

```go
// internal/api/outbox.go (new file)
func insertOutboxEvent(ctx context.Context, tx pgx.Tx, eventType string, aggregateID uuid.UUID, payload map[string]any) error {
    payloadJSON, err := json.Marshal(payload)
    if err != nil {
        return fmt.Errorf("outbox marshal: %w", err)
    }
    _, err = tx.Exec(ctx, `
        INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
        VALUES ('chapter', $1, $2, $3)
    `, aggregateID, eventType, payloadJSON)
    return err
}
```

### Sub-Tasks

```
D1-04a  Create outbox_events table DDL in book-service migration
        File: services/book-service/internal/migrate/migrate.go
        Schema: id (uuidv7), aggregate_type, aggregate_id, event_type,
                payload (JSONB), created_at, published_at, retry_count, last_error
        Index: partial index on unpublished (WHERE published_at IS NULL)

D1-04b  Create pg_notify trigger on outbox_events
        File: services/book-service/internal/migrate/migrate.go
        Trigger: AFTER INSERT → pg_notify('outbox_events', NEW.id::text)

D1-04c  Create insertOutboxEvent helper function
        File: services/book-service/internal/api/outbox.go (new)
        Signature: func insertOutboxEvent(ctx, tx, eventType, aggregateID, payload) error

D1-04d  Refactor transitionChapterLifecycle to use transaction
        File: services/book-service/internal/api/server.go (lines 967-1017)
        Change: wrap trash/purge cases in BEGIN/COMMIT to include outbox atomically
        Note: restore case (line 1007) stays non-event for now

D1-05a  Create loreweave_events database migration file
        File: services/worker-infra/internal/migrate/migrate.go (new — part of worker-infra scaffold)
        Schema:
          - event_log (id, source_service, source_outbox_id, event_type, aggregate_type,
            aggregate_id, payload, created_at, stored_at, UNIQUE on source+outbox_id)
          - event_consumers (consumer_name, stream_name, last_processed_event_id, status)
          - dead_letter_events (id, event_id FK, consumer_name, failure_reason, retry_count)

D1-05b  Add loreweave_events to db-ensure.sh
        File: infra/db-ensure.sh
        Change: add loreweave_events to DATABASES list
```

### File Impact Summary (Cycle 3)

| File | Change | New? |
|------|--------|------|
| `services/book-service/internal/migrate/migrate.go` | Add outbox_events DDL + pg_notify trigger | No (modify) |
| `services/book-service/internal/api/outbox.go` | Helper function for outbox INSERT | **Yes** |
| `services/book-service/internal/api/server.go` | Refactor transitionChapterLifecycle to use tx | No (modify) |
| `services/worker-infra/internal/migrate/migrate.go` | Events DB schema (event_log, consumers, dead_letter) | **Yes** (part of D1-09) |
| `infra/db-ensure.sh` | Add loreweave_events | No (modify) |

### Cross-Reference: Who Inserts Outbox Events?

These handlers will call `insertOutboxEvent` (done in D1-06 when we refactor handlers):

| Handler | Event | Existing TX? | Notes |
|---------|-------|-------------|-------|
| `patchDraft` | `chapter.saved` | Yes | Add 1 line before commit |
| `createChapterRecord` | `chapter.created` | Yes | Add 1 line before commit |
| `restoreRevision` | `chapter.saved` | Yes | Add 1 line before commit |
| `transitionChapterLifecycle` (trash) | `chapter.trashed` | **Refactored** | New tx wraps both |
| `transitionChapterLifecycle` (purge) | `chapter.deleted` | **Refactored** | New tx wraps both |

---

---

## Discovery Cycle 4: D1-06 — book-service JSONB Refactor

### Handler-by-Handler Change Specification

All 8 handlers in `services/book-service/internal/api/server.go` that touch the `body` column.

#### Handler 1: `getDraft` (L1097-1137) — READ

```
Current:  var body, format string          ← scans body as string
          .Scan(&chapterID, &body, &format, &updated, &version)
          writeJSON(w, 200, map[string]any{"body": body, ...})

Problem:  JSONB column → pgx returns []byte → json.Marshal base64-encodes it

Fix:      var body json.RawMessage          ← scans JSONB as raw JSON
          .Scan(&chapterID, &body, &format, &updated, &version)
          writeJSON(w, 200, map[string]any{"body": body, ...})
          // json.RawMessage implements json.Marshaler → inlines correctly

Import:   Add "encoding/json" (already imported in file)
Lines:    L1112: change type declaration
```

#### Handler 2: `patchDraft` (L1139-1196) — WRITE

```
Current:  var in struct { Body string ... }
          UPDATE chapter_drafts SET body=$2 WHERE chapter_id=$1

Fix:      var in struct {
              Body       json.RawMessage `json:"body"`      ← accept raw JSON
              BodyFormat string          `json:"body_format"`← new field
              ...
          }
          Validation: if in.BodyFormat == "" { in.BodyFormat = "json" }
                      if !json.Valid(in.Body) { return 400 }
          SQL:        UPDATE chapter_drafts SET body=$2, draft_format=$3, ... WHERE chapter_id=$1
          Outbox:     INSERT INTO outbox_events(...) ← add before COMMIT (Cycle 3)
          Revision:   INSERT INTO chapter_revisions(..., body, body_format, ...) ← include format

Lines:    L1153-1157: change struct, L1158: validation, L1188-1189: SQL params
```

#### Handler 3: `getRevision` (L1249-1295) — READ

```
Current:  var body string
          .Scan(&rid, &cid, &at, &uid, &msg, &body)
          writeJSON(w, 200, map[string]any{"body": body, ...})

Fix:      var body json.RawMessage
          var bodyFormat string
          SQL: add d.body_format to SELECT
          .Scan(&rid, &cid, &at, &uid, &msg, &body, &bodyFormat)
          writeJSON(w, 200, map[string]any{"body": body, "body_format": bodyFormat, ...})

Lines:    L1271: type, L1273: SQL add column, L1278: scan, L1287-1294: response add field
```

#### Handler 4: `restoreRevision` (L1297-1350) — READ + WRITE

```
Current:  var currentBody string  ← reads current draft
          var body string          ← reads revision body
          UPDATE chapter_drafts SET body=$2 WHERE chapter_id=$1
          INSERT INTO chapter_revisions(... body ...) ← saves "before restore"

Fix:      var currentBody json.RawMessage
          var currentFormat string
          SELECT d.body, d.draft_format FROM chapter_drafts ...
          var body json.RawMessage
          var bodyFormat string
          SELECT rv.body, rv.body_format FROM chapter_revisions ...
          INSERT INTO chapter_revisions(... body, body_format ...) ← save current with its format
          UPDATE chapter_drafts SET body=$2, draft_format=$3 ... ← set revision's format
          Outbox: INSERT outbox_events (chapter.saved) ← before COMMIT

Lines:    L1321-1326: scan types + add format, L1327-1333: scan + add format,
          L1342-1343: SQL params
```

#### Handler 5: `listRevisions` (L1198-1247) — READ (metadata only)

```
Current:  SELECT ... length(rv.body) ...
          .Scan(&rid, &cid, &at, &uid, &msg, &n)

Fix:      SELECT ... octet_length(rv.body::text) ...  ← JSONB length
          No body_format needed in list (it's metadata only)

Lines:    L1214: SQL change length() → octet_length(rv.body::text)
Note:     Minimal change — list doesn't return body content
```

#### Handler 6: `exportChapter` (L1054-1095) — READ (plain text output)

```
Current:  var body string
          SELECT d.body FROM chapter_drafts d ...
          w.Write([]byte(body))  ← returns raw body as text/plain

Fix:      REPLACE SQL to read from chapter_blocks instead:
          SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
          FROM chapter_blocks WHERE chapter_id = $1

          OR: scan body as json.RawMessage, extract _text fields in Go

Decision: Use chapter_blocks approach — simpler, text already extracted.
          Fallback: if no blocks exist (legacy), read body and extract in Go.

Lines:    L1068-1076: replace SQL query entirely, L1033: change scan type
```

#### Handler 7: `getChapterContent` (L1019-1052) — READ (plain text output)

```
Current:  SELECT ro.body_text FROM chapter_raw_objects ...
          w.Write([]byte(body))  ← returns raw object as text/plain

Fix:      This reads from chapter_raw_objects, NOT chapter_drafts!
          It returns the ORIGINAL uploaded text, not the edited draft.
          → NO CHANGE NEEDED. chapter_raw_objects stays TEXT.

Lines:    No changes!
Note:     This handler is NOT affected by the JSONB migration.
```

**Important discovery:** `getChapterContent` reads from `chapter_raw_objects` (original import), not from `chapter_drafts`. It's unaffected. Only 7 handlers need changes, not 8.

#### Handler 8: `getInternalBookChapter` (L1449-1490) — READ (internal API)

```
Current:  var title, lang, body string
          SELECT c.title, ..., d.body FROM chapters c JOIN chapter_drafts d ...
          writeJSON(w, 200, map[string]any{"body": body, ...})

Fix:      var body json.RawMessage
          Scan body as json.RawMessage
          Add text_content from chapter_blocks:
            SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
            FROM chapter_blocks WHERE chapter_id = $1
          Response: add "body": body, "text_content": textContent, "body_format": "json"

Lines:    L1465: type, L1473: scan, L1482-1489: response add fields
Note:     Translation worker reads text_content (D1-08 concern resolved here)
```

### Existing Tests Impact

```
File: services/book-service/internal/api/server_test.go

Tests in this file:
  TestParseLimitOffset          ← utility, NOT affected
  TestHelpers                   ← utility, NOT affected
  TestRequireUserID             ← auth, NOT affected
  TestParseUUIDParam            ← utility, NOT affected
  TestFetchSharingVisibility    ← sharing, NOT affected
  TestFetchSharingVisibilityFallsBackToPrivate ← sharing, NOT affected

Result: ALL existing tests pass without changes.
No handler-level tests exist (handlers tested via manual/integration only).
```

### New Test Cases Needed

```
D1-06-test-01  Test patchDraft accepts json.RawMessage body
D1-06-test-02  Test getDraft returns inline JSON (not base64)
D1-06-test-03  Test getRevision returns body + body_format
D1-06-test-04  Test restoreRevision copies body_format correctly
D1-06-test-05  Test exportChapter returns plain text from chapter_blocks
D1-06-test-06  Test getInternalBookChapter returns body + text_content
D1-06-test-07  Test patchDraft rejects invalid JSON body
```

These are integration tests (need DB). Can be deferred to D1-12 or written as part of D1-06.

### Sub-Tasks

```
D1-06a  getDraft: body → json.RawMessage scan + inline response
        File: server.go L1097-1137
        Changes: 2 lines (type declaration, already returns draft_format)

D1-06b  patchDraft: accept json.RawMessage body + body_format, validate JSON, add outbox
        File: server.go L1139-1196
        Changes: struct fields, validation, SQL params (body + format), outbox INSERT
        Depends on: D1-04c (outbox helper)

D1-06c  getRevision: body → json.RawMessage, add body_format to response
        File: server.go L1249-1295
        Changes: type, SQL column, scan, response field

D1-06d  restoreRevision: json.RawMessage both directions, copy body_format, add outbox
        File: server.go L1297-1350
        Changes: types, SQL columns, scan, outbox INSERT
        Depends on: D1-04c (outbox helper)

D1-06e  listRevisions: length(body) → octet_length(body::text)
        File: server.go L1198-1247
        Changes: 1 SQL line

D1-06f  exportChapter: read plain text from chapter_blocks instead of draft body
        File: server.go L1054-1095
        Changes: replace SQL query, change scan to single string result
        Depends on: D1-03 (chapter_blocks table exists)

D1-06g  getInternalBookChapter: body → json.RawMessage, add text_content from blocks
        File: server.go L1449-1490
        Changes: type, add second query for text_content, response fields
        Depends on: D1-03 (chapter_blocks table exists)

D1-06h  createChapterRecord: outbox event for chapter.created
        File: server.go L778-828
        Changes: add outbox INSERT before tx.Commit
        Depends on: D1-04c (outbox helper)
        Note: body format changes handled in D1-07 (plain text → JSON import)
```

### File Impact Summary (Cycle 4)

| File | Change | New? |
|------|--------|------|
| `services/book-service/internal/api/server.go` | 7 handlers refactored (getDraft, patchDraft, getRevision, restoreRevision, listRevisions, exportChapter, getInternalBookChapter) + createChapterRecord outbox | No (modify) |
| `services/book-service/internal/api/server_test.go` | Existing tests unchanged. New integration tests added (optional, can defer to D1-12) | No (modify or defer) |

### Correction from Cycle 3

Originally counted 8 handlers. `getChapterContent` reads from `chapter_raw_objects` (TEXT, unchanged) — **only 7 handlers need JSONB refactoring** + 1 handler gets outbox event (createChapterRecord).

---

## Remaining Cycles

| Cycle | Focus | Tasks |
|-------|-------|-------|
| 5 | D1-07 + D1-08: createChapter import + internal API text_content | Plain text → Tiptap JSON, text_content aggregation |
| 6 | D1-09 + D1-10: worker-infra service | Go project scaffold, task registry, relay |
| 7 | D1-11: Frontend JSONB save/load | _text snapshots, TiptapEditor changes |
| 8 | D1-12: Integration test | End-to-end verification |
