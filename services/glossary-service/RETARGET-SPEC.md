# G4 Phase-2 RETARGET-SPEC — test files: system tier → book tier

Status: Phase 1 (foundation) DONE. Build green. This spec is the **mechanical transform**
for Phase 2 — retarget every test that reads `system_kinds` / `system_kind_attributes`
(or `genre_groups`) so it uses the BOOK tier instead, because after the G4 cutover:

- `glossary_entities.kind_id` → `book_kinds(book_kind_id)` (was `system_kinds`)
- `entity_attribute_values.attr_def_id` → `book_attributes(attr_id)` (was `system_kind_attributes`)
- `recalculate_entity_snapshot` reads `book_kinds` / `book_attributes`.

A book MUST be adopted (its `book_kinds` / `book_attributes` populated) before any entity
can be inserted in it. Tests do this with the SQL-level helper `adoptTestBook`.

---

## 0. The helpers you call (already written, Phase 1)

File: `internal/api/g4_test_helpers_test.go`

```go
func adoptTestBook(t *testing.T, pool *pgxpool.Pool, bookID uuid.UUID)          // copy ALL system kinds+genres+attrs into book tier; idempotent
func bookKindID(t *testing.T, pool *pgxpool.Pool, bookID uuid.UUID, code string) uuid.UUID
func bookAttrID(t *testing.T, pool *pgxpool.Pool, bookID, bookKindID uuid.UUID, code string) uuid.UUID  // universal-genre row
```

- `adoptTestBook` adopts EVERY system kind+genre (not a picked subset) so any code a
  test references already exists. Call it ONCE per book id, right after migrations, before
  inserting entities. Idempotent — re-calling is safe (shared DB).
- `bookKindID` returns the `book_kind_id` for `(bookID, code)`. This is what now goes into
  `glossary_entities.kind_id`.
- `bookAttrID` returns the `book_attributes.attr_id` for `(bookID, bookKindID, code)`,
  preferring the universal-genre row. This is what now goes into
  `entity_attribute_values.attr_def_id`.

`bookID` MUST be a `uuid.UUID`. Where a test holds a string book id, parse it:
`bid := uuid.MustParse(bookID)`.

---

## 1. The core transform (per test / seed helper)

### BEFORE (system tier)
```go
var kindID, nameAttrID string
pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
pool.QueryRow(ctx,
    `SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`,
    kindID).Scan(&nameAttrID)

var eid string
pool.QueryRow(ctx,
    `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
    bookID, kindID).Scan(&eid)
pool.Exec(ctx,
    `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh',$3)`,
    eid, nameAttrID, name)
```

### AFTER (book tier)
```go
bid := uuid.MustParse(bookID)          // skip if bookID is already uuid.UUID
adoptTestBook(t, pool, bid)            // ← REQUIRED before any entity insert
kindID := bookKindID(t, pool, bid, "character")
nameAttrID := bookAttrID(t, pool, bid, kindID, "name")

var eid string
pool.QueryRow(ctx,
    `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
    bid, kindID).Scan(&eid)
pool.Exec(ctx,
    `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh',$3)`,
    eid, nameAttrID, name)
```

Key points:
- `kindID` / `nameAttrID` change type `string` → `uuid.UUID` (the helpers return `uuid.UUID`).
  If the surrounding code needs a string, call `.String()`. Adjust insert binds accordingly
  (pgx accepts `uuid.UUID` directly).
- The two `QueryRow ... system_*` lookups collapse to `bookKindID` / `bookAttrID`.
- Add exactly ONE `adoptTestBook(t, pool, bid)` per distinct book id, before the first entity
  insert into that book.
- Multiple attrs: one `bookAttrID(... 'name')`, `bookAttrID(... 'aliases')`,
  `bookAttrID(... 'description')`, etc. — same `kindID`.

### Aliases-attr / description-attr variants
```go
// BEFORE
pool.QueryRow(ctx, `SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='aliases' LIMIT 1`, kindID).Scan(&aliasAttr)
// AFTER
aliasAttr := bookAttrID(t, pool, bid, kindID, "aliases")
```

### "Seed the kind if missing" fallbacks (merge_handler_test.go pattern)
The `mergeFixture` block that INSERTs into `system_kinds` / `system_kind_attributes` when
`character` is absent is now UNNECESSARY: `adoptTestBook` always copies every system kind
(the seed guarantees `character` exists system-side). Replace the whole
`if f.kindID == uuid.Nil { … INSERT system_kinds … }` block with:
```go
adoptTestBook(t, f.pool, f.bookID)
f.kindID    = bookKindID(t, f.pool, f.bookID, "character")
f.nameAttr  = bookAttrID(t, f.pool, f.bookID, f.kindID, "name")
f.aliasAttr = bookAttrID(t, f.pool, f.bookID, f.kindID, "aliases")
f.descAttr  = bookAttrID(t, f.pool, f.bookID, f.kindID, "description")
```
(`f.kindID` / `f.nameAttr` etc. are already `uuid.UUID` in `mergeFixture` — no type change.)

---

## 2. Migration chain — ALREADY DONE in Phase 1 (do not redo)

The G4 tier + cutover is wired into the LOWEST-level shared helper so every test runs on it:
- `runK2aMigrations` (entity_k2a_test.go) — canonical chain; now ends with
  `UpUserKinds → UpGenreKindAttr → SeedGenreKindAttr → UpGlossaryCutoverG4`.
- `runMigrations` (export_handler_test.go) — now delegates to `runK2aMigrations`.
- `runMergeMigrations` (merge_handler_test.go) — inline chain; cutover appended.
- `setupRevisionsDB` (entity_revisions_handler_test.go) — inline chain; `UpExtraction` +
  cutover appended.
- All other helpers (`runCanonContentMigrations`, `runEnrichmentMigrations`, `runK3Migrations`,
  `runKindAliasMigrations`, `runGenreMigrations`, `runUserKindMigrations`) delegate to
  `runK2aMigrations`, so they inherit the cutover automatically — no change needed.

Phase 2 does NOT touch migration helpers further.

---

## 3. The 26 test files referencing system tier (from grep of
`system_kind_attributes` / `FROM system_kinds` / `genre_groups` in `*_test.go`)

Already handled in Phase 1 (migration-chain only — may still contain inline entity-seed SQL
that Phase 2 must retarget if present):
- `g4_test_helpers_test.go`   — the NEW helper file (no change).
- `entity_k2a_test.go`        — chain done. Body has many `system_*` schema-shape asserts +
  entity inserts → retarget the entity-insert / EAV-insert sites; schema-shape asserts that
  literally test the `system_kinds` table CAN STAY (those tables still exist).
- `merge_handler_test.go`     — chain done. Retarget `mergeFixture` per §1.
- `export_handler_test.go`    — chain done (delegates). Retarget any inline entity seeds.
- `entity_revisions_handler_test.go` — chain done. Retarget the `system_kinds`/`system_kind_attributes`
  lookups in `TestReconcileEntityFromSnapshot_*` (they SELECT kind_id + name attr_def_id).

Entity-seed / EAV-insert retarget (the bulk of Phase 2 work) — apply §1 to each:
- `bulk_status_test.go`            — `seedBulkEntity` (SELECT system_kinds character).
- `canon_content_test.go`          — `seedIdentityOnlyEntity` (location→character fallback + name attr).
- `entities_by_ids_test.go`
- `entities_list_test.go`
- `entity_raw_search_test.go`
- `entity_stats_test.go`
- `entity_version_test.go`
- `extraction_translation_test.go` — `seedEntityWithTranslation`.
- `extraction_writeback_test.go`
- `g2c_handler_test.go`
- `glossary_translate_handler_test.go`
- `k3_shortdesc_test.go`
- `known_entities_test.go`
- `kind_aliases_test.go`           — alias resolution now maps alias_code → book_kind by code;
  asserts on `loadKindMap` output expect `book_kind_id` values, not system kind_id.
- `merge_candidates_test.go`
- `propose_entity_test.go`
- `schema_confirm_test.go`         — see §4 (handler still mints into system tier — phase 4).
- `select_for_context_test.go`     — `seedContextBook` (+ seedEntity rows).
- `translation_glossary_test.go`   — `seedTranslationEntity`, `seedNameOnlyEntity`.
- `wiki_gen_limit_test.go`
- `wiki_writeback_test.go`
- `extraction_translation_test.go` (listed once).

### Shared seed helpers to retarget (callers then need no further change)
- `seedIdentityOnlyEntity(t, pool, bookID string, name)` — canon_content_test.go:252.
- `seedBulkEntity(t, pool, bookID uuid.UUID, status)` — bulk_status_test.go:62.
- `seedEntityWithTranslation(t, pool, bookID string, name, lang, value, confidence)` — extraction_translation_test.go:38.
- `seedContextBook(t, pool, bookID string, entities)` — select_for_context_test.go:24.
- `seedTranslationEntity(t, pool, bookID string, name, targetLang, value, confidence)` — translation_glossary_test.go:41.
- `seedNameOnlyEntity(t, pool, bookID string, name)` — translation_glossary_test.go:75.

Each: add `bid := uuid.MustParse(bookID)` + `adoptTestBook(t,pool,bid)`, swap the two
`system_*` SELECTs for `bookKindID` / `bookAttrID`, bind `bid` (not the string) into the
`glossary_entities` insert. Because many books are minted ad hoc per test, calling
`adoptTestBook` inside the seed helper (idempotent) is the cheapest place to guarantee it.

---

## 4. Handlers DEFERRED to Phase 4 (DO NOT retarget in Phase 2; tests for these stay
asserting system tier OR are skipped/xfail until Phase 4)

Phase 1 retargeted ONLY the extraction/entity-detail/translation read path. These still
read/write the SYSTEM tier and are Phase 4:
- `kinds_handler.listKinds`, `kinds_crud`, `genres_crud`/`genres_handler`,
  `schema_confirm_handler` (`createKindFromParams` / `createAttrDefFromParams` still mint into
  `system_kinds` / `system_kind_attributes`).
- `entity_handler.go` `createEntity` (validates kind against `system_kinds`) and `listEntities`
  (the `JOIN system_kinds ek ON ek.kind_id = e.kind_id` + name subqueries at ~lines 540-696)
  — these were NOT in the Phase-1 scope. **They are runtime-broken post-cutover** (book_kind_id
  won't match system_kinds), so any Phase-2 test that goes through `POST …/entities` or
  `GET …/entities` will fail until these are retargeted. See "Notes" — recommend pulling
  `createEntity` + `listEntities` retarget FORWARD into Phase 2 if those suites must go green.
- `system_kind_attributes`, `genre_groups`, `genre_tags` columns STILL EXIST (not dropped) —
  schema-shape tests on them remain valid.

---

## 5. Quick checklist for each Phase-2 file
1. Does it INSERT `glossary_entities`? → needs `adoptTestBook` + `bookKindID` for `kind_id`.
2. Does it INSERT `entity_attribute_values`? → needs `bookAttrID` for `attr_def_id`.
3. Does it SELECT from `system_kinds` / `system_kind_attributes` to get an id for the above?
   → replace with the helpers.
4. Pure schema-shape assertions on `system_*` tables → leave alone (tables still exist).
5. Goes through `POST/GET …/entities` HTTP? → blocked on Phase-4 `createEntity`/`listEntities`
   (flag, don't fight it).
