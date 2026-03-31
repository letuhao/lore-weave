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
D0-01  [DONE] Spin up postgres:18-alpine, test uuidv7() and JSON_TABLE availability
       Status: PASSED (2026-04-01)
       Results:
         - PostgreSQL 18.1 on x86_64-pc-linux-musl (Alpine)
         - uuidv7(): 019d4501-2158-7607-b141-cde5ff1b7f74 ← works, no extension
         - JSON_TABLE: 3 Tiptap blocks extracted correctly (type, _text, attrs)
         - Virtual generated column: block_count = 3 (zero storage)
         - pgcrypto NOT needed — confirmed safe to drop

D0-02  [DONE] Run ALL 9 service migrations against PG18
       Status: PASSED (2026-04-01)
       Results: all 9 services PASS — zero errors
         1. auth-service         → loreweave_auth              PASS
         2. book-service         → loreweave_book              PASS
         3. sharing-service      → loreweave_sharing           PASS
         4. catalog-service      → loreweave_catalog           PASS
         5. provider-registry    → loreweave_provider_registry PASS
         6. usage-billing        → loreweave_usage_billing     PASS
         7. glossary-service     → loreweave_glossary          PASS
         8. translation-service  → loreweave_translation       PASS
         9. chat-service         → loreweave_chat              PASS
       Notes: pgcrypto extension still works (backward compat), benign notices only

D0-03  [DONE] Test JSON_TABLE inside PL/pgSQL trigger function
       Status: PASSED (2026-04-01)
       File: infra/test-pg18-trigger.sql
       Results: all 7 test scenarios passed
         T1: INSERT 3 blocks — PASS (heading_context propagates)
         T2: UPSERT stability — PASS (id=SAME, hash/timestamp change only for modified)
         T3: Block shrink (3→2) — PASS (excess deleted)
         T4: Empty document — PASS (0 blocks)
         T5: HorizontalRule — PASS (empty text, type preserved)
         T6: Unicode — PASS (Vietnamese, Chinese, Japanese, emoji)
         T7: CASCADE delete — PASS (0 remaining)
       Key: UPSERT pattern confirmed — stable IDs, selective updated_at

D0-04  [DONE] Test pgx v5 JSONB scanning with json.RawMessage
       Status: PASSED (2026-04-01)
       File: infra/pg18test-go/main.go
       Results:
         T1: INSERT json.RawMessage → JSONB column — PASS
         T2: SELECT JSONB → scan as json.RawMessage — PASS (251 bytes)
         T3: json.Marshal(map{body: RawMessage}) → inline JSON — PASS (not base64!)
         T4: Round-trip data identical (key order differs — expected per JSON spec)
       Key: json.RawMessage is the correct Go type for JSONB columns
```

### D1-01: Postgres 18 + Redis in docker-compose

```
D1-01a  [DONE] Update docker-compose Postgres image + config
D1-01b  [DONE] Add Redis service to docker-compose
D1-01c  [DONE] Add loreweave_events database to db-ensure.sh
D1-01d  [DONE] Delete old Postgres volume (clean break)
        Status: PASSED (2026-04-01)
        Verified: PG 18.1 healthy, Redis 7.4.8 healthy, 10 databases created
```

### D1-02: Clean Schema — uuidv7 everywhere + JSONB body

```
D1-02a  [DONE] auth-service: 4 PKs → uuidv7(), pgcrypto removed
D1-02b  [DONE] book-service: 3 PKs → uuidv7(), pgcrypto removed, body→JSONB, body_format, block_count virtual
D1-02c  [DONE] sharing-service: pgcrypto removed
D1-02d  [DONE] provider-registry: 5 PKs → uuidv7(), pgcrypto removed
D1-02e  [DONE] usage-billing: 3 PKs → uuidv7(), pgcrypto removed
D1-02f  [DONE] glossary-service: 11 PKs → uuidv7(), pgcrypto removed
D1-02g  [DONE] translation-service: 4 PKs → uuidv7()
D1-02h  [DONE] chat-service: 3 PKs → uuidv7()
D1-02i  [DONE] All 9 migrations verified on fresh PG18 — PASS
        Status: PASSED (2026-04-01)
        Total: 30 uuidv7() replacements, 4 pgcrypto removals
        book-service: body=JSONB confirmed, block_count virtual confirmed
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

---

## Discovery Cycle 5: D1-07 + D1-08 — createChapter Import + Internal API + Downstream Consumers

### Chapter Creation Entry Points

Two paths into `createChapterRecord`:

| Entry | Source | Body Content |
|-------|--------|-------------|
| JSON body (L730-747) | Editor "create chapter" button, `createChapterEditor` API | Plain text string |
| Multipart file upload (L749-775) | Import dialog, `createChapterUpload` API | File content as string |

Both pass `body string` → `createChapterRecord` → stores in `chapter_drafts.body`.

**After migration:** `createChapterRecord` must convert plain text → Tiptap JSON with `_text` snapshots before storing as JSONB.

### Internal API Consumers — Complete Map

`getInternalBookChapter` (`/internal/books/{id}/chapters/{chapter_id}`) is consumed by:

| Service | File | Line | Reads `body` as | Impact |
|---------|------|------|-----------------|--------|
| translation-service | `chapter_worker.py` | L94 | `chapter.get("body")` → string → LLM | **BREAKS** — gets JSON object instead of string |
| translation-service | `translation_runner.py` | L63 | `chapter.get("body")` → string → LLM | **BREAKS** — same |
| sharing-service | `server.go` | L319 | `map[string]any` proxy → public reader | **Transparent** — proxies JSON as-is |
| catalog-service | `server.go` | L131 | `map[string]any` proxy → catalog reader | **Transparent** — proxies JSON as-is |

**Fix for translation-service:** Both files change `chapter.get("body")` → `chapter.get("text_content")`.
This is a 1-line change per file, no other logic changes needed.

### Frontend Reader Consumers — NEWLY DISCOVERED

**ReaderPage** and **RevisionHistory** both use `ChapterReadView` which expects `body: string`:

| Component | File | Line | Problem |
|-----------|------|------|---------|
| ReaderPage | `pages/ReaderPage.tsx` | L29 | `setBody(d.body)` — d.body is now JSON object |
| RevisionHistory | `components/editor/RevisionHistory.tsx` | L37 | `setPreview({ body: data.body })` — data.body is now JSON object |
| ChapterReadView | `components/shared/ChapterReadView.tsx` | L12 | `body.split(/\n\n+/)` — crashes on JSON object |

**Fix options:**

| Option | Approach |
|--------|----------|
| A: getDraft returns `text_content` too | Backend adds text_content field to getDraft response (like internal API). Reader uses text_content. |
| B: Frontend renders Tiptap JSON read-only | Use a read-only TiptapEditor in ReaderPage. Richer rendering (headings, lists, callouts styled). |
| C: Frontend extracts text from JSON | Walk `_text` fields client-side. Simple but loses formatting. |

**Recommendation: Option B (read-only Tiptap) for ReaderPage, Option A for RevisionHistory.**

- ReaderPage SHOULD render rich content (headings, formatting, callouts) — that's the point of Tiptap migration
- RevisionHistory preview can use text_content for quick diff view — full formatting not needed there

This means:
- **getDraft** adds `text_content` field (aggregated from chapter_blocks) — for reader + revisions
- **getRevision** adds `text_content` field — for revision preview
- **ReaderPage** renders Tiptap JSON with read-only editor
- **RevisionHistory** uses `text_content` for preview
- **ChapterReadView** stays as text renderer (used by RevisionHistory)

### Sub-Tasks

```
D1-07a  createChapterRecord: convert plain text → Tiptap JSON with _text snapshots
        File: services/book-service/internal/api/server.go (L778-828)
        New function: plainTextToTiptapJSON(text string) ([]byte, error)
        Changes: store body as json.RawMessage, body_format='json'

D1-07b  createChapter JSON path: no change needed (already passes string body)
        File: server.go L730-747
        Note: the string body goes through createChapterRecord which converts it

D1-07c  createChapter multipart path: no change needed
        File: server.go L749-775
        Note: same — file content goes through createChapterRecord

D1-08a  getDraft: add text_content to response (from chapter_blocks)
        File: services/book-service/internal/api/server.go (getDraft handler)
        Change: add second query or subquery:
          SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
          FROM chapter_blocks WHERE chapter_id = $1
        Response: add "text_content": textContent

D1-08b  getRevision: add text_content to response
        File: server.go (getRevision handler)
        Problem: revisions don't have chapter_blocks — they're snapshots.
        Solution: extract _text from revision body JSONB inline:
          SELECT string_agg(t, E'\n\n' ORDER BY ordinality)
          FROM jsonb_path_query(rv.body, '$.content[*]._text') WITH ORDINALITY AS x(t, ordinality)
        Response: add "text_content": textContent

D1-08c  getInternalBookChapter: add text_content (already planned in Cycle 4)
        File: server.go L1449-1490
        Already covered in D1-06g, just confirming scope

D1-08d  translation-service: read text_content instead of body
        File: services/translation-service/app/workers/chapter_worker.py L94
        Change: chapter.get("body") → chapter.get("text_content")
        File: services/translation-service/app/services/translation_runner.py L63
        Change: chapter.get("body") → chapter.get("text_content")
        2 one-line changes, no other logic affected

D1-08e  translation-service tests: update mock response to include text_content
        File: services/translation-service/tests/test_jobs.py (if mock returns chapter body)
        Change: add text_content to mock response
```

### File Impact Summary (Cycle 5)

| File | Change | New? |
|------|--------|------|
| `services/book-service/internal/api/server.go` | createChapterRecord + getDraft + getRevision add text_content | No (modify) |
| `services/translation-service/app/workers/chapter_worker.py` | `chapter.get("body")` → `chapter.get("text_content")` | No (modify, 1 line) |
| `services/translation-service/app/services/translation_runner.py` | Same 1-line change | No (modify, 1 line) |
| `services/translation-service/tests/test_jobs.py` | Update mock if needed | No (modify) |

### Cross-Impact on Frontend (feeds into Cycle 7)

These frontend files need changes because of the JSONB body:

| File | Current | After Migration |
|------|---------|----------------|
| `pages/ReaderPage.tsx` | `setBody(d.body)` → string → ChapterReadView | Render Tiptap JSON with read-only editor |
| `components/editor/RevisionHistory.tsx` | `preview.body` → string → ChapterReadView | Use `text_content` from API response |
| `components/shared/ChapterReadView.tsx` | Expects `body: string` | Unchanged — used by RevisionHistory only |
| `features/books/api.ts` | `getDraft` returns `body: string` | Type changes: `body: any`, add `text_content: string` |

---

---

## Discovery Cycle 6: D1-09 + D1-10 — worker-infra Service

### Project Structure (new Go service)

Follows the same pattern as book-service:

```
services/worker-infra/
├── cmd/
│   └── worker-infra/
│       └── main.go                 # Entry point: load config, init connections, run registry
├── internal/
│   ├── config/
│   │   └── config.go               # Env vars: WORKER_TASKS, DB URLs, Redis URL
│   ├── migrate/
│   │   └── migrate.go              # loreweave_events schema (event_log, consumers, dead_letter)
│   ├── registry/
│   │   ├── registry.go             # TaskRegistry: register, runSelected, graceful shutdown
│   │   └── types.go                # Task interface, TaskType enum (Listen, Cron, Consumer)
│   └── tasks/
│       ├── outbox_relay.go         # ListenTask: pg_notify + poll, publish to Redis + event_log
│       └── outbox_cleanup.go       # CronTask: delete old published events
├── Dockerfile
├── go.mod
└── go.sum
```

### Go Dependencies

```
go.mod:
  github.com/jackc/pgx/v5          # Postgres (existing pattern)
  github.com/jackc/pgxlisten        # LISTEN/NOTIFY helper for pgx v5
  github.com/redis/go-redis/v9      # Redis Streams XADD
```

### Config Design

```go
// internal/config/config.go

type Config struct {
    WorkerTasks    []string          // from WORKER_TASKS env: "outbox-relay,outbox-cleanup"
    EventsDBURL    string            // EVENTS_DB_URL → loreweave_events
    RedisURL       string            // REDIS_URL → redis://redis:6379
    OutboxSources  []OutboxSource    // parsed from OUTBOX_SOURCES env
    CleanupRetainDays int            // OUTBOX_CLEANUP_RETAIN_DAYS, default 7
}

type OutboxSource struct {
    Name string                      // "book", "glossary"
    DBURL string                     // postgres://...loreweave_book
}

// Env var format:
// OUTBOX_SOURCES=book:postgres://loreweave:pw@postgres:5432/loreweave_book
// Multiple sources separated by comma:
// OUTBOX_SOURCES=book:postgres://...loreweave_book,glossary:postgres://...loreweave_glossary
```

### Task Registry Design

```go
// internal/registry/types.go

type Task interface {
    Name() string
    Run(ctx context.Context) error   // blocks until ctx cancelled
}

// internal/registry/registry.go

type Registry struct {
    tasks map[string]Task
}

func (r *Registry) Register(name string, task Task)
func (r *Registry) RunSelected(ctx context.Context, names []string) error
  // Starts each selected task in a goroutine
  // Waits for ctx.Done() (SIGINT/SIGTERM)
  // Calls task shutdown in reverse order
```

### Outbox Relay Task Design

```go
// internal/tasks/outbox_relay.go

type OutboxRelay struct {
    sources    []OutboxSource       // multiple DBs to read outbox from
    eventsPool *pgxpool.Pool        // loreweave_events DB
    redis      *redis.Client
}

func (t *OutboxRelay) Run(ctx context.Context) error {
    // For each source DB:
    //   1. Acquire dedicated connection
    //   2. LISTEN outbox_events
    //   3. Spawn goroutine: wait for notification → processSource()
    //   4. Spawn goroutine: poll every 30s → processSource() (fallback)
    // Wait for ctx.Done()
}

func (t *OutboxRelay) processSource(ctx context.Context, sourceName string, sourcePool *pgxpool.Pool) {
    // 1. SELECT pending events from outbox_events WHERE published_at IS NULL ORDER BY created_at LIMIT 100
    // 2. For each event:
    //    a. XADD to Redis Stream (loreweave:events:{aggregate_type})
    //    b. INSERT into event_log (loreweave_events DB) — idempotent via UNIQUE(source_service, source_outbox_id)
    //    c. UPDATE outbox_events SET published_at = now() WHERE id = $1
    //    On failure: UPDATE retry_count, last_error
}
```

### Outbox Cleanup Task Design

```go
// internal/tasks/outbox_cleanup.go

type OutboxCleanup struct {
    sources    []OutboxSource
    retainDays int
}

func (t *OutboxCleanup) Run(ctx context.Context) error {
    // Run once per day (ticker)
    // For each source DB:
    //   DELETE FROM outbox_events WHERE published_at < now() - $1 days
    //   Log: "cleaned N events from {source}"
}
```

### Docker Compose Entry

```yaml
worker-infra:
  build:
    context: ../services/worker-infra
    dockerfile: Dockerfile
  environment:
    WORKER_TASKS: "outbox-relay,outbox-cleanup"
    EVENTS_DB_URL: postgres://loreweave:loreweave_dev@postgres:5432/loreweave_events
    REDIS_URL: redis://redis:6379
    OUTBOX_SOURCES: "book:postgres://loreweave:loreweave_dev@postgres:5432/loreweave_book"
    OUTBOX_CLEANUP_RETAIN_DAYS: "7"
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  restart: unless-stopped
```

### Dockerfile

```dockerfile
FROM golang:1.22-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/worker-infra ./cmd/worker-infra

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /out/worker-infra /worker-infra
USER nobody
CMD ["/worker-infra"]
```

No HEALTHCHECK or EXPOSE — worker has no HTTP server. Docker restart policy handles crashes.

### main.go Design

```go
func main() {
    cfg := config.Load()

    // Connect to events DB, run migration
    eventsPool := pgxpool.New(ctx, cfg.EventsDBURL)
    migrate.Up(ctx, eventsPool)

    // Connect to Redis
    rdb := redis.NewClient(redis.Options{Addr: cfg.RedisURL})

    // Connect to each outbox source DB
    sourcePools := map[string]*pgxpool.Pool{}
    for _, src := range cfg.OutboxSources {
        sourcePools[src.Name] = pgxpool.New(ctx, src.DBURL)
    }

    // Register tasks
    registry := registry.New()
    registry.Register("outbox-relay", &tasks.OutboxRelay{
        Sources: cfg.OutboxSources, SourcePools: sourcePools,
        EventsPool: eventsPool, Redis: rdb,
    })
    registry.Register("outbox-cleanup", &tasks.OutboxCleanup{
        Sources: cfg.OutboxSources, SourcePools: sourcePools,
        RetainDays: cfg.CleanupRetainDays,
    })

    // Run selected tasks until SIGINT/SIGTERM
    registry.RunSelected(ctx, cfg.WorkerTasks)
}
```

### Connection Count Analysis

| Connection | Target | Count | Pool Size |
|-----------|--------|-------|-----------|
| Events DB | `loreweave_events` | 1 pool | 5 connections |
| Redis | `redis:6379` | 1 client | 10 connections (default) |
| Book outbox | `loreweave_book` | 1 pool + 1 LISTEN conn | 3+1 connections |
| Future: glossary outbox | `loreweave_glossary` | 1 pool + 1 LISTEN conn | 3+1 |

**Total for D1:** ~20 connections. Well within Postgres limits.

### Sub-Tasks

```
D1-09a  Create worker-infra Go project scaffold
        Files: go.mod, cmd/worker-infra/main.go, Dockerfile
        Dependencies: pgx/v5, pgxlisten, go-redis/v9

D1-09b  Config loader: parse WORKER_TASKS, OUTBOX_SOURCES, EVENTS_DB_URL, REDIS_URL
        File: internal/config/config.go
        Note: OUTBOX_SOURCES format: "name:url,name:url"

D1-09c  Task registry: interface, Register, RunSelected, graceful shutdown
        Files: internal/registry/types.go, internal/registry/registry.go
        Pattern: each task runs in goroutine, ctx cancellation stops all

D1-09d  Events DB migration (loreweave_events schema)
        File: internal/migrate/migrate.go
        Tables: event_log, event_consumers, dead_letter_events
        Schema defined in 101_DATA_RE_ENGINEERING_PLAN.md §3.5.2

D1-10a  Outbox relay task implementation
        File: internal/tasks/outbox_relay.go
        Logic:
          - Connect to each source DB
          - LISTEN outbox_events via pgxlisten
          - Poll fallback every 30s
          - Read pending → XADD Redis (MAXLEN ~ 10000) → INSERT event_log → mark published
          - Retry on failure, increment retry_count
        Key library: github.com/jackc/pgxlisten

D1-10b  Outbox cleanup task implementation
        File: internal/tasks/outbox_cleanup.go
        Logic: daily ticker, DELETE published events older than N days from each source DB

D1-10c  Add worker-infra to docker-compose
        File: infra/docker-compose.yml
        Entry: worker-infra service with env vars, depends_on postgres + redis

D1-10d  Add worker-infra to gateway depends_on (optional — gateway doesn't need worker)
        Decision: NO — worker-infra is independent, doesn't block any other service
```

### File Impact Summary (Cycle 6)

| File | Change | New? |
|------|--------|------|
| `services/worker-infra/` (entire directory) | New Go service | **Yes** |
| `services/worker-infra/go.mod` | pgx, pgxlisten, go-redis | **Yes** |
| `services/worker-infra/Dockerfile` | Multi-stage Go build | **Yes** |
| `services/worker-infra/cmd/worker-infra/main.go` | Entry point | **Yes** |
| `services/worker-infra/internal/config/config.go` | Config loader | **Yes** |
| `services/worker-infra/internal/migrate/migrate.go` | Events DB schema | **Yes** |
| `services/worker-infra/internal/registry/types.go` | Task interface | **Yes** |
| `services/worker-infra/internal/registry/registry.go` | Registry implementation | **Yes** |
| `services/worker-infra/internal/tasks/outbox_relay.go` | Relay task | **Yes** |
| `services/worker-infra/internal/tasks/outbox_cleanup.go` | Cleanup task | **Yes** |
| `infra/docker-compose.yml` | Add worker-infra service entry | No (modify) |

**Total: 10 new files, 1 modified file.**

---

---

## Discovery Cycle 7: D1-11 — Frontend JSONB Save/Load

### Current Data Flow (BEFORE migration)

```
Save: editor → getHTML() → htmlToPlainText() → patchDraft({ body: plainText })
Load: getDraft() → { body: plainText } → plainTextToHtml() → editor.setContent(html)
Read: getDraft() → { body: plainText } → ChapterReadView splits by \n\n
```

### Target Data Flow (AFTER migration)

```
Save: editor → getJSON() → addTextSnapshots() → patchDraft({ body: jsonDoc, body_format: 'json' })
Load: getDraft() → { body: jsonDoc } → editor.setContent(jsonDoc)  ← direct, no conversion!
Read: getDraft() → { text_content: plainText } → ChapterReadView (unchanged)
```

### File-by-File Change Specification

#### 1. `features/books/api.ts` — API Client Types

```typescript
// CURRENT:
getDraft → returns { body: string; draft_format: string; ... }
patchDraft → payload: { body: string; ... }
getRevision → returns { body: string; ... }

// AFTER:
getDraft → returns { body: any; draft_format: string; text_content: string; ... }
patchDraft → payload: { body: any; body_format?: string; ... }
getRevision → returns { body: any; body_format: string; text_content: string; ... }
```

Changes:
- `getDraft` return type: `body: string` → `body: any`, add `text_content: string`
- `patchDraft` payload: `body: string` → `body: any`, add `body_format?: string`
- `getRevision` return type: `body: string` → `body: any`, add `body_format: string`, `text_content: string`

#### 2. `components/editor/TiptapEditor.tsx` — Major Refactor

```
REMOVE:
  - plainTextToHtml() function          ← no longer needed (body is JSON)
  - htmlToPlainText() function          ← no longer needed
  - escapeHtml() function              ← no longer needed
  - HTML-based content conversion      ← replaced by direct JSON

CHANGE:
  - content prop: string → any (accepts Tiptap JSON object)
  - onUpdate callback: (html: string) → (json: any) (returns getJSON() not getHTML())
  - initialContent: plainTextToHtml(content) → content directly
  - setContent: plainTextToHtml(newContent) → newContent directly

ADD:
  - addTextSnapshots(json) → adds _text to each top-level block
  - extractText(node) → recursive text extraction
  - onUpdate calls: addTextSnapshots(editor.getJSON()) before passing to parent

NEW interface:
  TiptapEditorHandle {
    setContent: (json: any) => void        // was __setContentFromPlainText
    setGrammarEnabled: (enabled: boolean) => void
  }

  TiptapEditorProps {
    content: any                            // was string
    onUpdate: (json: any) => void           // was (html: string)
    editable?: boolean
    grammarEnabled?: boolean
    editorMode?: EditorMode
    className?: string
  }
```

#### 3. `pages/ChapterEditorPage.tsx` — Save/Load Flow

```
CURRENT STATE VARIABLES:
  savedBody: string       ← plain text
  initialBody: string     ← plain text for TiptapEditor content prop
  tiptapHtml: string      ← HTML from onUpdate

AFTER:
  savedBody: any          ← Tiptap JSON doc from server
  tiptapJson: any | null  ← JSON from onUpdate (null = unchanged since load)
  textContent: string     ← plain text from getDraft().text_content (for word count)

SAVE FLOW (CURRENT):
  const bodyToSave = tiptapHtml ? htmlToPlainText(tiptapHtml) : savedBody;
  patchDraft({ body: bodyToSave })

SAVE FLOW (AFTER):
  const bodyToSave = tiptapJson ?? savedBody;
  patchDraft({ body: bodyToSave, body_format: 'json' })

LOAD FLOW (CURRENT):
  setSavedBody(draft.body);       ← string
  setInitialBody(draft.body);     ← string → plainTextToHtml in TiptapEditor

LOAD FLOW (AFTER):
  setSavedBody(draft.body);       ← JSON object
  setTextContent(draft.text_content);  ← for word count
  // TiptapEditor receives JSON directly via content prop

DIRTY CHECK (CURRENT):
  const bodyChanged = tiptapHtml ? htmlToPlainText(tiptapHtml) !== savedBody : false;

DIRTY CHECK (AFTER):
  const bodyChanged = tiptapJson
    ? JSON.stringify(tiptapJson) !== JSON.stringify(savedBody)
    : false;

DISCARD (CURRENT):
  tiptapEditorRef.current?.__setContentFromPlainText(savedBody);

DISCARD (AFTER):
  tiptapEditorRef.current?.setContent(savedBody);

WORD COUNT (CURRENT):
  const currentBody = tiptapHtml ? htmlToPlainText(tiptapHtml) : savedBody;
  wordCount(currentBody)

WORD COUNT (AFTER):
  // Use text_content from API (updated on save), or extract from tiptapJson
  // Simpler: just use textContent state variable, update on load
  wordCount(textContent)
```

#### 4. `pages/ReaderPage.tsx` — Read-Only Tiptap Rendering

```
CURRENT:
  setBody(d.body);                        ← string
  <ChapterReadView body={body} ... />     ← splits by \n\n

AFTER (Option B from Cycle 5: read-only Tiptap):
  setBody(d.body);                        ← JSON object
  <TiptapEditor
    content={body}
    onUpdate={() => {}}
    editable={false}
    className="..."
  />

  Remove ChapterReadView from ReaderPage — replaced by read-only TiptapEditor.
  The reader now shows rich content: headings, formatting, callouts, lists.
  Reader theme styling applied via CSS (tiptap-content class).
```

#### 5. `components/editor/RevisionHistory.tsx` — Preview Uses text_content

```
CURRENT:
  const data = await booksApi.getRevision(...)
  setPreview({ revision: rev, body: data.body });     ← string
  <ChapterReadView body={preview.body} />
  wordCount(preview.body)

AFTER:
  const data = await booksApi.getRevision(...)
  setPreview({ revision: rev, textContent: data.text_content });  ← plain text
  <ChapterReadView body={preview.textContent} />
  wordCount(preview.textContent)

  RevisionHistory keeps using ChapterReadView with plain text.
  Type changes: PreviewState { body: string } → { textContent: string }
```

#### 6. `components/shared/ChapterReadView.tsx` — NO CHANGES

Stays as-is. Still receives `body: string` (plain text). Used only by RevisionHistory now.
ReaderPage switches to read-only TiptapEditor instead.

### Code to Delete (cleanup)

| File | What to Remove |
|------|---------------|
| `TiptapEditor.tsx` | `plainTextToHtml()`, `htmlToPlainText()`, `escapeHtml()` functions |
| `ChapterEditorPage.tsx` | `import { htmlToPlainText }` — no longer exported/used |
| `ChapterEditorPage.tsx` | `tiptapHtml` state → replaced by `tiptapJson` |

### _text Snapshot Implementation

```typescript
// Added to TiptapEditor.tsx (or a new utility file)

import type { JSONContent } from '@tiptap/react';

/** Add _text snapshot to each top-level block */
function addTextSnapshots(doc: JSONContent): JSONContent {
  if (!doc.content) return doc;
  return {
    ...doc,
    content: doc.content.map(block => ({
      ...block,
      _text: extractText(block),
    })),
  };
}

/** Recursively extract plain text from a Tiptap node */
function extractText(node: JSONContent): string {
  if (node.type === 'text') return node.text || '';
  if (node.type === 'hardBreak') return '\n';
  if (!node.content) return '';
  return node.content
    .map(child => extractText(child))
    .join(node.type === 'listItem' ? '\n' : '');
}
```

### Sub-Tasks

```
D1-11a  API client type updates
        File: frontend-v2/src/features/books/api.ts
        Changes: getDraft, patchDraft, getRevision return/param types
        3 type definition changes

D1-11b  TiptapEditor refactor: content as JSON, onUpdate returns JSON with _text
        File: frontend-v2/src/components/editor/TiptapEditor.tsx
        Changes:
          - Remove plainTextToHtml, htmlToPlainText, escapeHtml
          - content prop: string → any
          - onUpdate: calls addTextSnapshots(editor.getJSON())
          - setContent handle: accepts JSON directly
          - Add addTextSnapshots + extractText functions
        This is the core change — all other files depend on this

D1-11c  ChapterEditorPage: JSONB save/load flow
        File: frontend-v2/src/pages/ChapterEditorPage.tsx
        Changes:
          - State: tiptapHtml → tiptapJson, add textContent
          - Save: send JSON + body_format
          - Load: pass JSON to editor directly, store text_content
          - Dirty check: JSON.stringify comparison
          - Discard: setContent(savedBody) not __setContentFromPlainText
          - Word count: use textContent state

D1-11d  ReaderPage: read-only TiptapEditor replaces ChapterReadView
        File: frontend-v2/src/pages/ReaderPage.tsx
        Changes:
          - Import TiptapEditor instead of ChapterReadView
          - setBody receives JSON object
          - Render: <TiptapEditor content={body} editable={false} />
          - Reader theme CSS applied via tiptap-content class

D1-11e  RevisionHistory: use text_content from API
        File: frontend-v2/src/components/editor/RevisionHistory.tsx
        Changes:
          - PreviewState type: body → textContent
          - data.body → data.text_content
          - wordCount uses textContent
          - ChapterReadView stays (receives plain text)

D1-11f  Unit test: extractText function
        File: frontend-v2/src/components/editor/__tests__/extractText.test.ts (new)
        Test cases:
          - Simple paragraph → "Hello world"
          - Paragraph with bold/italic → "Hello bold italic"
          - Heading → "Chapter One"
          - BulletList → "Item 1\nItem 2"
          - Blockquote → "To be or not to be"
          - HorizontalRule → ""
          - Callout → "This is a note"
          - Empty paragraph → ""
          - Nested list → correct newline joining
```

### File Impact Summary (Cycle 7)

| File | Change | New? |
|------|--------|------|
| `features/books/api.ts` | 3 type changes (getDraft, patchDraft, getRevision) | No |
| `components/editor/TiptapEditor.tsx` | Major refactor: remove HTML functions, JSON content, _text snapshots | No |
| `pages/ChapterEditorPage.tsx` | Save/load flow rewrite, state variables changed | No |
| `pages/ReaderPage.tsx` | ChapterReadView → read-only TiptapEditor | No |
| `components/editor/RevisionHistory.tsx` | body → textContent, type change | No |
| `components/editor/__tests__/extractText.test.ts` | Unit test for extractText | **Yes** |

**Total: 5 modified files, 1 new test file.**

---

---

## Discovery Cycle 8: D1-12 — Integration Test

### Pre-Test Setup

```bash
# 1. Stop everything, clean volumes
docker compose down -v

# 2. Rebuild all changed services
docker compose build book-service worker-infra frontend

# 3. Start infrastructure first
docker compose up -d postgres redis
# Wait for healthy

# 4. Start all services
docker compose up -d
# Wait for all healthchecks to pass
```

### Test Tools

| Tool | Command | Purpose |
|------|---------|---------|
| psql | `docker compose exec postgres psql -U loreweave -d loreweave_book` | Verify DB state |
| redis-cli | `docker compose exec redis redis-cli` | Verify Redis events |
| curl | `curl -s localhost:3123/v1/...` | Test API via gateway |
| browser | `http://localhost:5174` | Test frontend |

### Test Scenarios

#### T01: Postgres 18 Startup + All Migrations

```
Action:   docker compose up -d postgres → wait for healthy → check all services start
Verify:
  □ All 10 databases created (db-ensure.sh includes loreweave_events)
  □ All services pass healthcheck
  □ psql: SELECT uuidv7(); returns UUID
  □ psql: no 'pgcrypto' extension in any DB
  □ All tables use uuidv7() defaults (spot check: books, chapters, chapter_drafts)
```

#### T02: Chapter Create (plain text → Tiptap JSON conversion)

```
Action:   Register user → create book → create chapter with plain text body
          curl -X POST localhost:3123/v1/books/{id}/chapters \
            -H "Authorization: Bearer {token}" \
            -H "Content-Type: application/json" \
            -d '{"title":"Test","original_language":"en","body":"First paragraph\n\nSecond paragraph"}'

Verify:
  □ Response: chapter created with 201
  □ psql loreweave_book: SELECT body, draft_format FROM chapter_drafts WHERE chapter_id = '...'
    - body is JSONB: {"type":"doc","content":[{"type":"paragraph","_text":"First paragraph",...},{"type":"paragraph","_text":"Second paragraph",...}]}
    - draft_format = 'json'
  □ psql: SELECT count(*) FROM chapter_blocks WHERE chapter_id = '...'
    - Returns 2 (two paragraphs)
  □ psql: SELECT block_type, text_content, heading_context FROM chapter_blocks ORDER BY block_index
    - Row 0: paragraph, "First paragraph", NULL
    - Row 1: paragraph, "Second paragraph", NULL
  □ psql loreweave_book: SELECT event_type FROM outbox_events WHERE aggregate_id = '...'
    - 1 row: chapter.created
  □ psql loreweave_events: SELECT event_type FROM event_log WHERE aggregate_id = '...'
    - 1 row: chapter.created (relayed by worker-infra)
  □ redis-cli: XRANGE loreweave:events:chapter - +
    - Contains chapter.created event
```

#### T03: Chapter Save (Tiptap JSON with _text snapshots)

```
Action:   From frontend editor, type content with heading + paragraph + callout.
          Save (Ctrl+S or button).
          Expected patchDraft payload:
          {
            "body": {
              "type": "doc",
              "content": [
                {"type":"heading","attrs":{"level":2},"_text":"Chapter Title","content":[...]},
                {"type":"paragraph","_text":"Some text here","content":[...]},
                {"type":"callout","attrs":{"type":"note"},"_text":"Author note","content":[...]}
              ]
            },
            "body_format": "json",
            "expected_draft_version": 1
          }

Verify:
  □ Save succeeds, toast "Chapter saved"
  □ psql: chapter_drafts.body contains JSONB with _text fields
  □ psql: chapter_blocks has 3 rows:
    - block 0: heading, "Chapter Title", heading_context = "Chapter Title"
    - block 1: paragraph, "Some text here", heading_context = "Chapter Title"
    - block 2: callout, "Author note", heading_context = "Chapter Title"
  □ psql: content_hash is SHA-256 of text_content for each block
  □ outbox_events: chapter.saved event with draft_version = 2
  □ event_log: chapter.saved relayed
  □ redis: chapter.saved event in stream
```

#### T04: Chapter Save — UPSERT Block Stability

```
Action:   Edit only paragraph text (block 1), don't touch heading or callout. Save again.

Verify:
  □ psql: chapter_blocks still has 3 rows
  □ Block 0 (heading): SAME id, SAME updated_at (content unchanged)
  □ Block 1 (paragraph): SAME id, NEW updated_at (content changed), NEW content_hash
  □ Block 2 (callout): SAME id, SAME updated_at (content unchanged)
  □ This proves UPSERT preserves stable IDs for unchanged blocks
```

#### T05: Chapter Save — Block Count Shrinks

```
Action:   Delete the callout block in editor. Save.

Verify:
  □ chapter_blocks now has 2 rows (block 2 deleted by trigger)
  □ Remaining blocks have correct block_index (0, 1)
```

#### T06: getDraft Returns JSON + text_content

```
Action:   curl GET /v1/books/{id}/chapters/{id}/draft

Verify:
  □ Response body.body is JSON object (not string, not base64)
  □ Response body.draft_format = "json"
  □ Response body.text_content = "Chapter Title\n\nSome text here" (aggregated from blocks)
  □ Response body.draft_version = 3 (after 3 saves)
```

#### T07: getRevision Returns JSON + text_content

```
Action:   curl GET /v1/books/{id}/chapters/{id}/revisions/{rev_id}

Verify:
  □ Response body.body is JSON object
  □ Response body.body_format = "json"
  □ Response body.text_content extracted from body JSONB _text fields
```

#### T08: Restore Revision

```
Action:   Restore revision 1 (the original plain-text-converted chapter)

Verify:
  □ chapter_drafts.body restored to revision 1's JSONB content
  □ New revision created (snapshot of "before restore")
  □ chapter_blocks re-extracted (trigger fires on UPDATE)
  □ outbox_events: chapter.saved event
  □ Frontend editor shows restored content correctly
```

#### T09: Export Chapter (plain text from blocks)

```
Action:   curl GET /v1/books/{id}/chapters/{id}/export

Verify:
  □ Response Content-Type: text/plain
  □ Response body is plain text (not JSON), paragraphs joined by \n\n
  □ Content-Disposition header has correct filename
```

#### T10: Internal API + Translation Worker

```
Action:   curl GET /internal/books/{id}/chapters/{id} (direct to book-service:8082)

Verify:
  □ Response has "body": { JSON object }
  □ Response has "text_content": "plain text string"
  □ Translation worker would read text_content (verify with mock if possible)
```

#### T11: Outbox Relay + Event Log

```
Action:   After several saves, check the full event pipeline

Verify:
  □ psql loreweave_book: SELECT count(*) FROM outbox_events WHERE published_at IS NOT NULL
    - All events published (no pending)
  □ psql loreweave_events: SELECT count(*) FROM event_log
    - Same count as published outbox events
  □ psql loreweave_events: SELECT * FROM event_log ORDER BY stored_at
    - Events in chronological order, correct source_service, event_type
  □ redis-cli: XLEN loreweave:events:chapter
    - Matches event count
  □ psql loreweave_events: SELECT * FROM dead_letter_events
    - Empty (no failures)
```

#### T12: Frontend Reader (rich content)

```
Action:   Navigate to /books/{id}/chapters/{id}/read in browser

Verify:
  □ Headings render as styled headings (not plain text "## Title")
  □ Callouts render with colored sidebar
  □ Bold/italic formatting preserved
  □ Lists render with bullets/numbers
  □ No "[object Object]" or broken rendering
```

#### T13: Frontend Revision Preview

```
Action:   Open History panel → click "View" on a revision

Verify:
  □ Preview shows plain text (text_content), not JSON
  □ Word count is correct
  □ Restore button works, editor updates
```

#### T14: Chapter Delete — Cascade + Event

```
Action:   Trash → purge a chapter

Verify:
  □ chapter_blocks rows CASCADE deleted
  □ outbox_events: chapter.trashed + chapter.deleted events
  □ event_log: both events relayed
```

#### T15: File Upload Import

```
Action:   Upload a .txt file via import dialog

Verify:
  □ Chapter created with body_format = 'json'
  □ Body is Tiptap JSON (converted from plain text)
  □ chapter_blocks populated correctly
  □ Reader shows correct content
```

#### T16: uuidv7 Ordering

```
Action:   Create 3 chapters rapidly, then list revisions

Verify:
  □ All IDs are uuidv7 format (time-ordered, start with similar prefix)
  □ chapter_revisions.id ordering matches created_at ordering
  □ No need for explicit ORDER BY created_at — uuidv7 natural order works
```

### Sub-Tasks

```
D1-12a  Write integration test script (bash or Go test)
        File: infra/test-integration-d1.sh (new)
        Covers: T01 through T16
        Method: curl + psql + redis-cli assertions
        Requires: all services running via docker compose

D1-12b  Manual browser verification checklist
        Covers: T03 (save), T06 (load), T12 (reader), T13 (revisions), T15 (import)
        Method: open browser, follow steps, check results
        No automation — visual verification
```

### File Impact Summary (Cycle 8)

| File | Change | New? |
|------|--------|------|
| `infra/test-integration-d1.sh` | Integration test script | **Yes** |

### Test Dependency Map

```
T01 (infra) → T02 (create) → T03 (save) → T04 (UPSERT stability)
                                          → T05 (shrink)
                                          → T06 (getDraft)
                                          → T07 (getRevision)
                                          → T08 (restore)
                                          → T09 (export)
                                          → T10 (internal API)
                                          → T11 (outbox relay)
                                          → T12 (reader UI)
                                          → T13 (revisions UI)
                             → T14 (delete cascade)
                             → T15 (file upload)
              T16 (uuidv7) — independent, can run after T02
```

---

## All Cycles Complete — Summary

### Total Sub-Tasks by Phase

| Phase | Cycle | Sub-tasks | New Files | Modified Files |
|-------|-------|-----------|-----------|---------------|
| D0 | 1 | 4 | 2 | 0 |
| D1-01 | 1 | 4 | 0 | 2 |
| D1-02 | 1 | 9 | 0 | 9 |
| D1-03 | 2 | 4 | 1 | 1 |
| D1-04 | 3 | 4 | 1 | 1 |
| D1-05 | 3 | 2 | 1* | 1 |
| D1-06 | 4 | 8 | 0 | 1 |
| D1-07 | 5 | 3 | 0 | 1 |
| D1-08 | 5 | 5 | 0 | 3 |
| D1-09 | 6 | 4 | 10 | 0 |
| D1-10 | 6 | 3 | 0 | 1 |
| D1-11 | 7 | 6 | 1 | 5 |
| D1-12 | 8 | 2 | 1 | 0 |
| **Total** | | **58** | **17** | **25** |

*D1-05 migration file is part of worker-infra (D1-09), counted once.

### Execution Order (respecting dependencies)

```
Phase D0 (pre-flight):
  D0-01 → D0-02 → D0-03 → D0-04                    GATE

Phase D1 (build):
  D1-01a,b,c,d (infra)                               parallel
  ├── D1-02a through D1-02i (schema)                  sequential per service
  │   ├── D1-03a,b,c,d (trigger)                      sequential
  │   ├── D1-04a,b,c (outbox table)                   sequential
  │   │   ├── D1-06a through D1-06h (JSONB refactor)  sequential per handler
  │   │   │   ├── D1-07a (createChapter import)
  │   │   │   ├── D1-08a,b,c,d,e (text_content)
  │   │   │   └── D1-11a through D1-11f (frontend)
  │   │   └── D1-04d (lifecycle refactor)
  │   └── D1-05a,b (events schema)
  │       └── D1-09a through D1-09d (worker scaffold)
  │           └── D1-10a,b,c (relay tasks)
  └── D1-12a,b (integration test)                     GATE
```
