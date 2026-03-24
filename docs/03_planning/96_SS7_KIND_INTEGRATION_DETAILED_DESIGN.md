# SS-7 — Kind Integration (Entity Picker + Filter Bar): Detailed Design

## Document Metadata

- Document ID: LW-M05-96
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Tech Lead
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Parent Plan: [doc 89](89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md) — SS-7 row
- Depends on: SS-6 complete; SS-1 complete (snapshot trigger exists)
- Summary: The final sub-phase. Applies ADR-S1 + ADR-S2 schema migrations to make `glossary_entities` and `entity_attribute_values` polymorphic. Extends `GET /v1/glossary/kinds`, `POST .../entities`, `GET .../entities`, and `GET .../entities/{id}` to handle all three tiers. Updates `CreateEntityModal`, `GlossaryFiltersBar`, and adds `KindBadge`. After this sub-phase, users can create entities with any T1/T2/T3 kind.

## Change History

| Version | Date       | Change         | Author    |
| ------- | ---------- | -------------- | --------- |
| 0.1.0   | 2026-03-25 | Initial design | Assistant |

---

## 1) Goal & Scope

**In scope:**
- ADR-S1: add `user_kind_id`, `book_kind_id` to `glossary_entities`; make `kind_id` nullable; add `CHECK exactly_one`
- ADR-S2: add `user_attr_def_id`, `book_attr_def_id` to `entity_attribute_values`; make `attr_def_id` nullable; replace UNIQUE constraint; add `CHECK exactly_one`
- `GET /v1/glossary/kinds?book_id=` — extended grouped response (T1 + T2 + T3)
- `POST .../entities` — accepts `kind_tier + kind_ref_id` for any tier
- `loadEntityDetail` — LEFT JOINs across all three tier tables; attr values via `v_attr_def`
- `listEntities` — LEFT JOINs; `kind_codes` filter resolves codes from all tiers
- Snapshot trigger update — resolve kind metadata from correct tier (added in SS-1, extended here)
- New `KindBadge.tsx` component
- Updated `CreateEntityModal` — three groups: System / My kinds / Book kinds
- Updated `GlossaryFiltersBar` — T2/T3 kind chips in separate rows with tier badges
- Updated `GlossaryPage` — use new API shape; `handleKindSelect` passes `kind_tier + kind_ref_id`
- Updated `useEntityKinds` hook — accepts `bookId`

**Out of scope:**
- Entity *re-kind* (changing kind after creation) — deferred
- Bulk kind assignment across entities — deferred
- Kind-level permissions (all kinds owned by the same user, already enforced by DB)

---

## 2) DB Migration

**New function:** `migrate.UpKindIntegration(ctx, pool)` in `services/glossary-service/internal/migrate/migrate.go`

Call in `Up()` after `UpKindSync`:

```go
if err := UpKindIntegration(ctx, pool); err != nil {
    return fmt.Errorf("UpKindIntegration: %w", err)
}
```

### 2.1 DDL

```sql
-- ─────────────────────────────────────────────────────────────────────────────
-- ADR-S1: Polymorphic kind reference on glossary_entities
-- ─────────────────────────────────────────────────────────────────────────────

-- Step 1: make kind_id nullable (was NOT NULL)
ALTER TABLE glossary_entities ALTER COLUMN kind_id DROP NOT NULL;

-- Step 2: add T2 and T3 FK columns
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS user_kind_id UUID
    REFERENCES user_kinds(user_kind_id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS book_kind_id UUID
    REFERENCES book_kinds(book_kind_id) ON DELETE SET NULL;

-- Step 3: add CHECK — exactly one kind FK must be non-null
--   (All existing rows already satisfy this: kind_id IS NOT NULL and the two new
--    columns are NULL → (1+0+0)=1 ✓)
ALTER TABLE glossary_entities
  ADD CONSTRAINT ck_entity_exactly_one_kind CHECK (
    (kind_id IS NOT NULL)::int +
    (user_kind_id IS NOT NULL)::int +
    (book_kind_id IS NOT NULL)::int = 1
  );

-- Step 4: partial indexes on new columns (avoids scanning NULLs)
CREATE INDEX IF NOT EXISTS idx_ge_book_user_kind
  ON glossary_entities(book_id, user_kind_id)
  WHERE user_kind_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ge_book_book_kind
  ON glossary_entities(book_id, book_kind_id)
  WHERE book_kind_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADR-S2: Polymorphic attr def reference on entity_attribute_values
-- ─────────────────────────────────────────────────────────────────────────────

-- Step 5: make attr_def_id nullable (was NOT NULL)
ALTER TABLE entity_attribute_values ALTER COLUMN attr_def_id DROP NOT NULL;

-- Step 6: add T2 and T3 FK columns
ALTER TABLE entity_attribute_values
  ADD COLUMN IF NOT EXISTS user_attr_def_id UUID
    REFERENCES user_kind_attributes(attr_id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS book_attr_def_id UUID
    REFERENCES book_kind_attributes(attr_id) ON DELETE SET NULL;

-- Step 7: drop original UNIQUE(entity_id, attr_def_id) — NULL != NULL in PG,
--   so it would allow duplicate (entity_id, NULL) rows for T2/T3 values.
ALTER TABLE entity_attribute_values
  DROP CONSTRAINT IF EXISTS entity_attribute_values_entity_id_attr_def_id_key;

-- Step 8: replace with three per-tier partial unique indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_eav_unique_system
  ON entity_attribute_values(entity_id, attr_def_id)
  WHERE attr_def_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_eav_unique_user
  ON entity_attribute_values(entity_id, user_attr_def_id)
  WHERE user_attr_def_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_eav_unique_book
  ON entity_attribute_values(entity_id, book_attr_def_id)
  WHERE book_attr_def_id IS NOT NULL;

-- Step 9: add CHECK — exactly one attr def FK must be non-null
ALTER TABLE entity_attribute_values
  ADD CONSTRAINT ck_attrval_exactly_one_def CHECK (
    (attr_def_id IS NOT NULL)::int +
    (user_attr_def_id IS NOT NULL)::int +
    (book_attr_def_id IS NOT NULL)::int = 1
  );

-- Step 10: covering indexes for new FK columns
CREATE INDEX IF NOT EXISTS idx_eav_user_attr
  ON entity_attribute_values(user_attr_def_id)
  WHERE user_attr_def_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_eav_book_attr
  ON entity_attribute_values(book_attr_def_id)
  WHERE book_attr_def_id IS NOT NULL;
```

### 2.2 No data backfill needed

All existing `glossary_entities` rows have `kind_id IS NOT NULL` and the two new columns NULL → CHECK passes automatically. Same for `entity_attribute_values`.

---

## 3) Utility SQL Patterns

These patterns are used throughout the updated handlers. Define once, reference everywhere in this document.

### 3.1 Effective kind columns (SELECT clause fragment)

```sql
-- kind_ref_id: the actual UUID from whichever tier is set
CASE
  WHEN e.kind_id IS NOT NULL       THEN e.kind_id::text
  WHEN e.user_kind_id IS NOT NULL  THEN e.user_kind_id::text
  ELSE                                  e.book_kind_id::text
END AS kind_ref_id,

-- kind_tier
CASE
  WHEN e.kind_id IS NOT NULL       THEN 'system'
  WHEN e.user_kind_id IS NOT NULL  THEN 'user'
  ELSE                                  'book'
END AS kind_tier,

-- Kind display metadata (COALESCE across tier tables)
COALESCE(ek.kind_id::text,        uk.user_kind_id::text,        bk.book_kind_id::text)  AS kind_meta_id,
COALESCE(ek.code,                 uk.code,                      bk.code)                AS kind_code,
COALESCE(ek.name,                 uk.name,                      bk.name)                AS kind_name,
COALESCE(ek.icon,                 uk.icon,                      bk.icon)                AS kind_icon,
COALESCE(ek.color,                uk.color,                     bk.color)               AS kind_color
```

### 3.2 Kind LEFT JOINs (FROM clause fragment)

```sql
FROM glossary_entities e
LEFT JOIN entity_kinds ek ON ek.kind_id        = e.kind_id
LEFT JOIN user_kinds   uk ON uk.user_kind_id   = e.user_kind_id AND uk.deleted_at IS NULL
LEFT JOIN book_kinds   bk ON bk.book_kind_id   = e.book_kind_id AND bk.deleted_at IS NULL
```

### 3.3 Effective attr def ID (used in JOINs)

```sql
COALESCE(eav.attr_def_id, eav.user_attr_def_id, eav.book_attr_def_id)
```

Used to join `v_attr_def`:

```sql
JOIN v_attr_def vad ON vad.ref_id = COALESCE(eav.attr_def_id, eav.user_attr_def_id, eav.book_attr_def_id)
```

### 3.4 Display name subquery (entity-level, cross-tier)

```sql
COALESCE((
  SELECT eav2.original_value
  FROM entity_attribute_values eav2
  JOIN v_attr_def vad2
    ON vad2.ref_id = COALESCE(eav2.attr_def_id, eav2.user_attr_def_id, eav2.book_attr_def_id)
  WHERE eav2.entity_id = e.entity_id
    AND vad2.code IN ('name','term')
  ORDER BY vad2.sort_order
  LIMIT 1
), '') AS display_name
```

---

## 4) Backend Changes

### 4.1 `kinds_handler.go` — Extended `listKinds`

**No change to existing signature** when called without `?book_id=`.

When `?book_id=X` is present, return grouped format. Logic:

```go
func (s *Server) listKinds(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "...")
        return
    }
    ctx := r.Context()
    bookID := r.URL.Query().Get("book_id")

    if bookID == "" {
        // ── Backward-compat: flat T1 list (same as before) ──────────────────
        s.listKindsSystem(w, ctx)
        return
    }

    // ── Grouped: T1 + T2 (user's) + T3 (this book's) ───────────────────────
    bookUUID, err := uuid.Parse(bookID)
    if err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid book_id")
        return
    }
    if !s.verifyBookOwner(w, ctx, bookUUID, userID) {
        return
    }
    s.listKindsGrouped(w, ctx, userID, bookUUID)
}
```

**`listKindsSystem`**: existing logic extracted into helper (flat `EntityKind[]` with attrs, unchanged).

**`listKindsGrouped`**: new helper returning `AllKindsResponse`:

```go
type userKindSummary struct {
    UserKindID  string   `json:"user_kind_id"`
    Code        string   `json:"code"`
    Name        string   `json:"name"`
    Icon        string   `json:"icon"`
    Color       string   `json:"color"`
    GenreTags   []string `json:"genre_tags"`
    IsActive    bool     `json:"is_active"`
    AttrCount   int      `json:"attr_count"`
}

type bookKindSummary struct {
    BookKindID  string   `json:"book_kind_id"`
    Code        string   `json:"code"`
    Name        string   `json:"name"`
    Icon        string   `json:"icon"`
    Color       string   `json:"color"`
    GenreTags   []string `json:"genre_tags"`
    IsActive    bool     `json:"is_active"`
    AttrCount   int      `json:"attr_count"`
}

type allKindsResponse struct {
    System []domain.EntityKind  `json:"system"`
    User   []userKindSummary    `json:"user"`
    Book   []bookKindSummary    `json:"book"`
}
```

Queries:

```go
// T2: user's active, non-deleted kinds
rows, err := db.Query(ctx,
    `SELECT uk.user_kind_id, uk.code, uk.name, uk.icon, uk.color, uk.genre_tags,
            COUNT(uka.attr_id) AS attr_count
     FROM user_kinds uk
     LEFT JOIN user_kind_attributes uka
       ON uka.user_kind_id = uk.user_kind_id AND uka.deleted_at IS NULL
     WHERE uk.owner_user_id = $1 AND uk.is_active = true AND uk.deleted_at IS NULL
     GROUP BY uk.user_kind_id
     ORDER BY uk.name`, userID)
```

```go
// T3: book's active, non-deleted kinds
rows, err := db.Query(ctx,
    `SELECT bk.book_kind_id, bk.code, bk.name, bk.icon, bk.color, bk.genre_tags,
            COUNT(bka.attr_id) AS attr_count
     FROM book_kinds bk
     LEFT JOIN book_kind_attributes bka
       ON bka.book_kind_id = bk.book_kind_id AND bka.deleted_at IS NULL
     WHERE bk.book_id = $1 AND bk.is_active = true AND bk.deleted_at IS NULL
     GROUP BY bk.book_id
     ORDER BY bk.name`, bookUUID)
```

T1 system kinds: reuse existing `listKindsSystem` logic and embed the result in `system` field.

Response: `writeJSON(w, http.StatusOK, allKindsResponse{System: ..., User: ..., Book: ...})`

---

### 4.2 `entity_handler.go` — Updated `createEntity`

**Updated request body:**

```go
var in struct {
    // New format (preferred)
    KindTier  string `json:"kind_tier"`   // "system" | "user" | "book"
    KindRefID string `json:"kind_ref_id"` // UUID

    // Legacy format (backward compat: treated as tier=system)
    KindID string `json:"kind_id"` // UUID — deprecated, kept for old clients
}
```

**Normalization logic:**

```go
// Normalize legacy kind_id → new format
if in.KindRefID == "" && in.KindID != "" {
    in.KindTier  = "system"
    in.KindRefID = in.KindID
}
if in.KindRefID == "" {
    writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "kind_ref_id is required")
    return
}
if in.KindTier == "" {
    in.KindTier = "system"
}
```

**Kind validation per tier:**

```go
switch in.KindTier {
case "system":
    // Existing: verify entity_kinds row exists and is visible
    err = pool.QueryRow(ctx,
        `SELECT EXISTS(SELECT 1 FROM entity_kinds WHERE kind_id=$1 AND is_hidden=false)`,
        kindRefID).Scan(&exists)

case "user":
    // Verify user_kinds row belongs to this user and is active
    err = pool.QueryRow(ctx,
        `SELECT EXISTS(SELECT 1 FROM user_kinds WHERE user_kind_id=$1
          AND owner_user_id=$2 AND is_active=true AND deleted_at IS NULL)`,
        kindRefID, userID).Scan(&exists)

case "book":
    // Verify book_kinds row belongs to this book AND this user
    err = pool.QueryRow(ctx,
        `SELECT EXISTS(SELECT 1 FROM book_kinds WHERE book_kind_id=$1
          AND book_id=$2 AND owner_user_id=$3
          AND is_active=true AND deleted_at IS NULL)`,
        kindRefID, bookID, userID).Scan(&exists)
}
```

**Entity INSERT — polymorphic kind FK:**

```go
var entityIDStr string
switch in.KindTier {
case "system":
    err = tx.QueryRow(ctx,
        `INSERT INTO glossary_entities(book_id, kind_id, status, tags)
         VALUES($1,$2,'draft','{}') RETURNING entity_id`,
        bookID, kindRefID).Scan(&entityIDStr)
case "user":
    err = tx.QueryRow(ctx,
        `INSERT INTO glossary_entities(book_id, user_kind_id, status, tags)
         VALUES($1,$2,'draft','{}') RETURNING entity_id`,
        bookID, kindRefID).Scan(&entityIDStr)
case "book":
    err = tx.QueryRow(ctx,
        `INSERT INTO glossary_entities(book_id, book_kind_id, status, tags)
         VALUES($1,$2,'draft','{}') RETURNING entity_id`,
        bookID, kindRefID).Scan(&entityIDStr)
}
```

**Attr value INSERT — polymorphic attr def FK:**

```go
// Load attr defs from correct table
var attrQuery string
switch in.KindTier {
case "system":
    attrQuery = `SELECT attr_def_id, 'system' FROM attribute_definitions WHERE kind_id=$1 ORDER BY sort_order`
case "user":
    attrQuery = `SELECT attr_id, 'user' FROM user_kind_attributes WHERE user_kind_id=$1 AND deleted_at IS NULL ORDER BY sort_order`
case "book":
    attrQuery = `SELECT attr_id, 'book' FROM book_kind_attributes WHERE book_kind_id=$1 AND deleted_at IS NULL ORDER BY sort_order`
}
attrRows, err := tx.Query(ctx, attrQuery, kindRefID)
// ...
for attrRows.Next() {
    var attrID, attrTier string
    attrRows.Scan(&attrID, &attrTier)
    switch attrTier {
    case "system":
        tx.Exec(ctx,
            `INSERT INTO entity_attribute_values(entity_id, attr_def_id)
             VALUES($1,$2) ON CONFLICT DO NOTHING`,
            entityIDStr, attrID)
    case "user":
        tx.Exec(ctx,
            `INSERT INTO entity_attribute_values(entity_id, user_attr_def_id)
             VALUES($1,$2) ON CONFLICT DO NOTHING`,
            entityIDStr, attrID)
    case "book":
        tx.Exec(ctx,
            `INSERT INTO entity_attribute_values(entity_id, book_attr_def_id)
             VALUES($1,$2) ON CONFLICT DO NOTHING`,
            entityIDStr, attrID)
    }
}
```

---

### 4.3 `entity_handler.go` — Updated response types

Add `kind_tier` to response types:

```go
type kindSummary struct {
    KindID   string `json:"kind_id"`   // ref_id from whichever tier
    KindTier string `json:"kind_tier"` // "system" | "user" | "book"  ← NEW
    Code     string `json:"code"`
    Name     string `json:"name"`
    Icon     string `json:"icon"`
    Color    string `json:"color"`
}
```

---

### 4.4 `entity_handler.go` — Updated `loadEntityDetail`

Replace Query 1 (entity + kind + counts):

```sql
SELECT
    e.entity_id, e.book_id,
    -- Effective kind ref
    CASE
      WHEN e.kind_id IS NOT NULL      THEN e.kind_id::text
      WHEN e.user_kind_id IS NOT NULL THEN e.user_kind_id::text
      ELSE                                 e.book_kind_id::text
    END AS kind_ref_id,
    CASE
      WHEN e.kind_id IS NOT NULL      THEN 'system'
      WHEN e.user_kind_id IS NOT NULL THEN 'user'
      ELSE                                 'book'
    END AS kind_tier,
    -- Kind display metadata
    COALESCE(ek.kind_id::text, uk.user_kind_id::text, bk.book_kind_id::text) AS kind_meta_id,
    COALESCE(ek.code,  uk.code,  bk.code)  AS kind_code,
    COALESCE(ek.name,  uk.name,  bk.name)  AS kind_name,
    COALESCE(ek.icon,  uk.icon,  bk.icon)  AS kind_icon,
    COALESCE(ek.color, uk.color, bk.color) AS kind_color,
    -- Entity fields
    e.status, e.tags, e.created_at, e.updated_at,
    -- Cross-tier display name
    COALESCE((
      SELECT eav2.original_value
      FROM entity_attribute_values eav2
      JOIN v_attr_def vad2
        ON vad2.ref_id = COALESCE(eav2.attr_def_id, eav2.user_attr_def_id, eav2.book_attr_def_id)
      WHERE eav2.entity_id = e.entity_id
        AND vad2.code IN ('name','term')
      ORDER BY vad2.sort_order LIMIT 1
    ), '') AS display_name,
    -- Counts
    (SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id = e.entity_id) AS chapter_link_count,
    (SELECT COUNT(*) FROM attribute_translations tr
        JOIN entity_attribute_values eav2 ON eav2.attr_value_id = tr.attr_value_id
        WHERE eav2.entity_id = e.entity_id) AS translation_count,
    (SELECT COUNT(*) FROM evidences ev
        JOIN entity_attribute_values eav3 ON eav3.attr_value_id = ev.attr_value_id
        WHERE eav3.entity_id = e.entity_id) AS evidence_count
FROM glossary_entities e
LEFT JOIN entity_kinds ek ON ek.kind_id       = e.kind_id
LEFT JOIN user_kinds   uk ON uk.user_kind_id  = e.user_kind_id AND uk.deleted_at IS NULL
LEFT JOIN book_kinds   bk ON bk.book_kind_id  = e.book_kind_id AND bk.deleted_at IS NULL
WHERE e.entity_id = $1 AND e.book_id = $2 AND e.deleted_at IS NULL
```

Scan changes: add `kindTier` and use `kind_ref_id` as `KindID` in `kindSummary`:

```go
err := s.pool.QueryRow(ctx, entityQ, entityID, bookID).Scan(
    &d.EntityID, &d.BookID,
    &d.KindID,            // kind_ref_id
    &d.Kind.KindTier,     // kind_tier  ← new
    &d.Kind.KindID,       // kind_meta_id (same UUID as kind_ref_id in practice)
    &d.Kind.Code, &d.Kind.Name, &d.Kind.Icon, &d.Kind.Color,
    &d.Status, &d.Tags, &d.CreatedAt, &d.UpdatedAt,
    &d.DisplayName,
    &d.ChapterLinkCount, &d.TranslationCount, &d.EvidenceCount,
)
```

Replace Query 3 (attribute values + attr defs):

```sql
SELECT
    eav.attr_value_id, eav.entity_id,
    COALESCE(eav.attr_def_id::text, eav.user_attr_def_id::text, eav.book_attr_def_id::text) AS attr_def_id,
    eav.original_language, eav.original_value,
    vad.ref_id::text, vad.code, vad.name, vad.field_type, vad.is_required, vad.sort_order
FROM entity_attribute_values eav
JOIN v_attr_def vad
  ON vad.ref_id = COALESCE(eav.attr_def_id, eav.user_attr_def_id, eav.book_attr_def_id)
WHERE eav.entity_id = $1
ORDER BY vad.sort_order
```

---

### 4.5 `entity_handler.go` — Updated `listEntities`

Replace `JOIN entity_kinds ek ON ek.kind_id = e.kind_id` with LEFT JOINs (pattern 3.2).

Update `kind_codes` WHERE clause fragment:

```go
// Old: fmt.Sprintf("ek.code = ANY($%d)", n)
// New:
where = append(where, fmt.Sprintf("COALESCE(ek.code, uk.code, bk.code) = ANY($%d)", n))
```

Update SELECT columns (use COALESCE patterns from 3.1 + 3.4).

Update `Scan` call to read `kind_ref_id`, `kind_tier`, and kind display fields:

```go
if err := rows.Scan(
    &item.EntityID, &item.BookID,
    &item.KindID,       // kind_ref_id
    &item.Kind.KindTier, // kind_tier  ← new
    &item.Kind.KindID,  // kind_meta_id
    &item.Kind.Code, &item.Kind.Name, &item.Kind.Icon, &item.Kind.Color,
    &item.DisplayName,
    &item.ChapterLinkCount, &item.TranslationCount, &item.EvidenceCount,
    &item.Status, &item.Tags, &item.CreatedAt, &item.UpdatedAt,
); err != nil { ... }
```

---

### 4.6 Snapshot trigger update (`recalculate_entity_snapshot`)

The snapshot PL/pgSQL function was created in SS-1. In SS-7 it must resolve kind metadata from the correct tier. The function body `recalculate_entity_snapshot(entity_id UUID)` changes its kind metadata lookup:

```sql
-- SS-7 update: replace the kind SELECT block with:
kind_row := (
  SELECT
    CASE WHEN e.kind_id IS NOT NULL THEN 'system'
         WHEN e.user_kind_id IS NOT NULL THEN 'user'
         ELSE 'book' END AS source,
    COALESCE(ek.kind_id, uk.user_kind_id, bk.book_kind_id) AS ref_id,
    COALESCE(ek.code,  uk.code,  bk.code)  AS code,
    COALESCE(ek.name,  uk.name,  bk.name)  AS name,
    COALESCE(ek.icon,  uk.icon,  bk.icon)  AS icon,
    COALESCE(ek.color, uk.color, bk.color) AS color
  FROM glossary_entities e
  LEFT JOIN entity_kinds ek ON ek.kind_id       = e.kind_id
  LEFT JOIN user_kinds   uk ON uk.user_kind_id  = e.user_kind_id
  LEFT JOIN book_kinds   bk ON bk.book_kind_id  = e.book_kind_id
  WHERE e.entity_id = p_entity_id
);
```

Also update the attribute values collection in the trigger to use `v_attr_def`:

```sql
-- SS-7 update: replace attribute_definitions JOIN with v_attr_def:
FOR attr_rec IN
  SELECT
    vad.source         AS attr_def_source,
    vad.ref_id::text   AS attr_def_ref_id,
    vad.name,
    vad.field_type,
    vad.sort_order,
    eav.attr_value_id::text,
    eav.original_language,
    eav.original_value
  FROM entity_attribute_values eav
  JOIN v_attr_def vad
    ON vad.ref_id = COALESCE(eav.attr_def_id, eav.user_attr_def_id, eav.book_attr_def_id)
  WHERE eav.entity_id = p_entity_id
  ORDER BY vad.sort_order
```

The trigger DDL update is done via `CREATE OR REPLACE FUNCTION recalculate_entity_snapshot(...)` in `UpKindIntegration`.

---

### 4.7 Route changes in `server.go`

No new routes. The existing routes are unchanged:

```
GET  /v1/glossary/kinds                         → listKinds (extended with ?book_id)
POST /v1/glossary/books/{book_id}/entities      → createEntity (extended)
GET  /v1/glossary/books/{book_id}/entities      → listEntities (extended)
GET  /v1/glossary/books/{book_id}/entities/{id} → getEntityDetail (extended)
```

---

## 5) TypeScript API Changes

### 5.1 Updates to `frontend/src/features/glossary/types.ts`

Add new types and extend existing ones:

```typescript
// ── SS-7 Kind Integration ────────────────────────────────────────────────────

// KindTier is shared with SS-6 types (already defined there; import or co-locate)
export type KindTier = 'system' | 'user' | 'book';

// Lightweight T2 kind as returned by GET /kinds?book_id=
export type UserKindSummary = {
  user_kind_id: string;
  code:         string;
  name:         string;
  icon:         string;
  color:        string;
  genre_tags:   string[];
  is_active:    boolean;
  attr_count:   number;
};

// Lightweight T3 kind as returned by GET /kinds?book_id=
export type BookKindSummary = {
  book_kind_id: string;
  code:         string;
  name:         string;
  icon:         string;
  color:        string;
  genre_tags:   string[];
  is_active:    boolean;
  attr_count:   number;
};

// Grouped response from GET /v1/glossary/kinds?book_id=X
export type AllKindsResponse = {
  system: EntityKind[];
  user:   UserKindSummary[];
  book:   BookKindSummary[];
};

// Unified kind entry used internally in the picker
export type AnyKindEntry = {
  tier:   KindTier;
  ref_id: string;    // kind_id | user_kind_id | book_kind_id
  code:   string;
  name:   string;
  icon:   string;
  color:  string;
  genre_tags: string[];
};
```

Extend existing types:

```typescript
// KindSummary: add kind_tier
export type KindSummary = {
  kind_id:   string;   // the ref UUID from whichever tier
  kind_tier: KindTier; // ← NEW
  code:      string;
  name:      string;
  icon:      string;
  color:     string;
};

// GlossaryEntitySummary: kind_id is now the tier-specific ref_id
// No change to shape, but semantic: kind_id may be user_kind_id or book_kind_id
// kind.kind_tier tells you which table it came from.
```

---

### 5.2 Updates to `frontend/src/features/glossary/api.ts`

```typescript
// ── Updated getKinds ──────────────────────────────────────────────────────────

/** GET /v1/glossary/kinds — flat T1 list (backward compat) */
getKindsSystem(token: string): Promise<EntityKind[]> {
  return apiJson<EntityKind[]>(`${BASE}/kinds`, { token });
},

/** GET /v1/glossary/kinds?book_id=X — grouped T1+T2+T3 */
getAllKinds(token: string, bookId: string): Promise<AllKindsResponse> {
  return apiJson<AllKindsResponse>(`${BASE}/kinds?book_id=${bookId}`, { token });
},

// ── Updated createEntity ──────────────────────────────────────────────────────

/** POST /v1/glossary/books/{bookId}/entities */
createEntity(
  bookId: string,
  kind: { kind_tier: KindTier; kind_ref_id: string },
  token: string,
): Promise<GlossaryEntity> {
  return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities`, {
    method: 'POST',
    body: JSON.stringify({ kind_tier: kind.kind_tier, kind_ref_id: kind.kind_ref_id }),
    token,
  });
},
```

Old `createEntity(bookId, kindId, token)` signature is removed and replaced. All callers must update.

---

## 6) Frontend Component Changes

### 6.1 New component: `frontend/src/features/glossary/components/KindBadge.tsx`

Small pill badge showing kind name + tier indicator icon.

```tsx
import type { KindTier } from '../types';

interface Props {
  name:  string;
  icon:  string;
  color: string;
  tier:  KindTier;
}

const TIER_ICON: Record<KindTier, string> = {
  system: '',       // no indicator for system (default)
  user:   ' 👤',   // person icon
  book:   ' 📖',   // book icon
};

export function KindBadge({ name, icon, color, tier }: Props) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{ borderColor: color + '60', color }}
    >
      {icon} {name}{TIER_ICON[tier]}
    </span>
  );
}
```

---

### 6.2 Updated `CreateEntityModal.tsx`

**New props:**

```typescript
interface Props {
  allKinds:    AllKindsResponse;      // replaces kinds: EntityKind[]
  onSelect:    (entry: AnyKindEntry) => void;
  onClose:     () => void;
  isCreating?: boolean;
  createError?: string;
}
```

**Group layout change:**

Old: 3 system groups (Universal / Fantasy / Romance+Drama)

New: same 3 system groups (T1) + 2 optional extra groups:

```
┌─────────────────────────────────────────────────┐
│ Choose entity type                        [×]    │
├─────────────────────────────────────────────────┤
│ UNIVERSAL                                        │
│ [👤 Character] [📍 Location] [🎁 Item]          │
│                                                  │
│ FANTASY                                          │
│ [✨ Power System] [🏛 Organization] ...          │
│                                                  │
│ ROMANCE / DRAMA                                  │
│ [💕 Relationship] [📈 Plot Arc] ...             │
├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤
│ MY KINDS  👤                                     │  ← only shown if allKinds.user.length > 0
│ [🗡 My Knight] [🏯 My Castle] ...              │
├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤
│ BOOK KINDS  📖                                   │  ← only shown if allKinds.book.length > 0
│ [⚔ Battle Scene] ...                            │
└─────────────────────────────────────────────────┘
```

**`onSelect` callback now receives `AnyKindEntry`** (includes `tier` and `ref_id`).

T1 kinds: `tier='system', ref_id=kind.kind_id`
T2 kinds: `tier='user', ref_id=kind.user_kind_id`
T3 kinds: `tier='book', ref_id=kind.book_kind_id`

**Group collapsed by default if empty.** T2/T3 groups hidden if `allKinds.user.length === 0` / `allKinds.book.length === 0`.

**Implementation sketch:**

```tsx
export function CreateEntityModal({ allKinds, onSelect, onClose, isCreating, createError }: Props) {
  // T1 groups (existing logic, unchanged)
  const universal = allKinds.system.filter(k => k.genre_tags.includes('universal'));
  const fantasy   = allKinds.system.filter(k => k.genre_tags.includes('fantasy') && !k.genre_tags.includes('universal'));
  const romance   = allKinds.system.filter(k =>
    (k.genre_tags.includes('romance') || k.genre_tags.includes('drama')) &&
    !k.genre_tags.includes('universal') && !k.genre_tags.includes('fantasy'));

  function toEntry(k: EntityKind): AnyKindEntry {
    return { tier: 'system', ref_id: k.kind_id, code: k.code, name: k.name, icon: k.icon, color: k.color, genre_tags: k.genre_tags };
  }
  function toUserEntry(k: UserKindSummary): AnyKindEntry {
    return { tier: 'user', ref_id: k.user_kind_id, code: k.code, name: k.name, icon: k.icon, color: k.color, genre_tags: k.genre_tags };
  }
  function toBookEntry(k: BookKindSummary): AnyKindEntry {
    return { tier: 'book', ref_id: k.book_kind_id, code: k.code, name: k.name, icon: k.icon, color: k.color, genre_tags: k.genre_tags };
  }

  const systemGroups = [
    { label: 'Universal',        kinds: universal.map(toEntry) },
    { label: 'Fantasy',          kinds: fantasy.map(toEntry) },
    { label: 'Romance / Drama',  kinds: romance.map(toEntry) },
  ].filter(g => g.kinds.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-xl overflow-y-auto max-h-[90vh]">
        {/* header, error, spinner — unchanged */}

        <div className="space-y-4">
          {/* System kinds */}
          {systemGroups.map(group => (
            <div key={group.label}>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {group.label}
              </p>
              <div className="grid grid-cols-3 gap-2">
                {group.kinds.map(entry => (
                  <button key={entry.ref_id} disabled={isCreating}
                    onClick={() => onSelect(entry)}
                    className="flex flex-col items-center gap-1 rounded border p-3 text-center transition hover:bg-muted disabled:opacity-50"
                    style={{ borderColor: entry.color + '40' }}>
                    <span className="text-2xl">{entry.icon}</span>
                    <span className="text-xs font-medium leading-tight" style={{ color: entry.color }}>
                      {entry.name}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}

          {/* T2: My kinds */}
          {allKinds.user.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                My Kinds 👤
              </p>
              <div className="grid grid-cols-3 gap-2">
                {allKinds.user.map(k => {
                  const entry = toUserEntry(k);
                  return (
                    <button key={k.user_kind_id} disabled={isCreating}
                      onClick={() => onSelect(entry)}
                      className="flex flex-col items-center gap-1 rounded border p-3 text-center transition hover:bg-muted disabled:opacity-50"
                      style={{ borderColor: k.color + '40' }}>
                      <span className="text-2xl">{k.icon}</span>
                      <span className="text-xs font-medium leading-tight" style={{ color: k.color }}>
                        {k.name}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{k.attr_count} attrs</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* T3: Book kinds */}
          {allKinds.book.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Book Kinds 📖
              </p>
              <div className="grid grid-cols-3 gap-2">
                {allKinds.book.map(k => {
                  const entry = toBookEntry(k);
                  return (
                    <button key={k.book_kind_id} disabled={isCreating}
                      onClick={() => onSelect(entry)}
                      className="flex flex-col items-center gap-1 rounded border p-3 text-center transition hover:bg-muted disabled:opacity-50"
                      style={{ borderColor: k.color + '40' }}>
                      <span className="text-2xl">{k.icon}</span>
                      <span className="text-xs font-medium leading-tight" style={{ color: k.color }}>
                        {k.name}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{k.attr_count} attrs</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

---

### 6.3 Updated `GlossaryFiltersBar.tsx`

**New props:**

```typescript
interface Props {
  filters:  FilterState;
  allKinds: AllKindsResponse;   // replaces kinds: EntityKind[]
  onChange: (partial: Partial<FilterState>) => void;
}
```

**Kind chips row changes:**

Old: one flat row of kind chips.

New: three rows (system / user / book), each only shown if non-empty:

```tsx
{/* Row 2: System kind chips */}
{allKinds.system.length > 0 && (
  <div className="flex flex-wrap gap-1.5">
    {allKinds.system.map(k => (
      <button key={k.kind_id} onClick={() => toggleKind(k.code)}
        className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition"
        style={...}>
        {k.icon} {k.name}
      </button>
    ))}
  </div>
)}

{/* Row 3: User kind chips (hidden if empty) */}
{allKinds.user.length > 0 && (
  <div className="flex flex-wrap gap-1.5 items-center">
    <span className="text-[10px] text-muted-foreground">My kinds:</span>
    {allKinds.user.map(k => (
      <button key={k.user_kind_id} onClick={() => toggleKind(k.code)}
        className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition"
        style={...}>
        {k.icon} {k.name} 👤
      </button>
    ))}
  </div>
)}

{/* Row 4: Book kind chips (hidden if empty) */}
{allKinds.book.length > 0 && (
  <div className="flex flex-wrap gap-1.5 items-center">
    <span className="text-[10px] text-muted-foreground">Book kinds:</span>
    {allKinds.book.map(k => (
      <button key={k.book_kind_id} onClick={() => toggleKind(k.code)}
        className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition"
        style={...}>
        {k.icon} {k.name} 📖
      </button>
    ))}
  </div>
)}
```

`toggleKind(code)` is unchanged — still operates on `filters.kindCodes` as `string[]`.

---

### 6.4 Updated `useEntityKinds` hook

**File:** `frontend/src/features/glossary/hooks/useEntityKinds.ts`

Old: `getKinds(token)` → `EntityKind[]`

New: when `bookId` is provided, calls `getAllKinds(token, bookId)` → `AllKindsResponse`.

```typescript
export function useEntityKinds(bookId?: string) {
  const { accessToken } = useAuth();
  const [allKinds, setAllKinds] = useState<AllKindsResponse>({
    system: [], user: [], book: [],
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    setIsLoading(true);
    const fn = bookId
      ? () => glossaryApi.getAllKinds(accessToken, bookId)
      : () => glossaryApi.getKindsSystem(accessToken).then(system => ({ system, user: [], book: [] }));
    fn()
      .then(setAllKinds)
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, [accessToken, bookId]);

  // Backward compat: flat T1 list for components that haven't migrated yet
  const kinds = allKinds.system;

  return { allKinds, kinds, isLoading };
}
```

---

### 6.5 Updated `GlossaryPage.tsx`

Key changes:

```tsx
// OLD: const { kinds, isLoading: kindsLoading } = useEntityKinds();
const { allKinds, isLoading: kindsLoading } = useEntityKinds(bookId);

// OLD: async function handleKindSelect(kind: EntityKind) {
//   const created = await glossaryApi.createEntity(bookId, kind.kind_id, accessToken);
// NEW:
async function handleKindSelect(entry: AnyKindEntry) {
  if (!accessToken) return;
  setIsCreating(true);
  setCreateError('');
  try {
    const created = await glossaryApi.createEntity(
      bookId,
      { kind_tier: entry.tier, kind_ref_id: entry.ref_id },
      accessToken,
    );
    setIsCreateOpen(false);
    refresh();
    setSelectedEntityId(created.entity_id);
  } catch (e: unknown) {
    setCreateError((e as Error).message || 'Failed to create entity');
  } finally {
    setIsCreating(false);
  }
}

// Pass allKinds to updated modal and filters bar:
<CreateEntityModal
  allKinds={allKinds}   // replaces kinds={kinds}
  onSelect={handleKindSelect}
  ...
/>

<GlossaryFiltersBar
  filters={filters}
  allKinds={allKinds}   // replaces kinds={kinds}
  onChange={setFilters}
/>
```

---

### 6.6 Use `KindBadge` in entity cards

`GlossaryEntityCard.tsx` (or equivalent): replace inline kind display with `<KindBadge>`:

```tsx
// OLD: <span style={{ color: entity.kind.color }}>{entity.kind.icon} {entity.kind.name}</span>
// NEW:
<KindBadge
  name={entity.kind.name}
  icon={entity.kind.icon}
  color={entity.kind.color}
  tier={entity.kind.kind_tier}
/>
```

---

## 7) Wiring Checklist

| Step | File | Change |
|---|---|---|
| 1 | `services/glossary-service/internal/migrate/migrate.go` | Add `UpKindIntegration()` with full ADR-S1+S2 DDL; call in `Up()` |
| 2 | `services/glossary-service/internal/migrate/migrate.go` | Update `recalculate_entity_snapshot` PL/pgSQL function (SS-1's function) via `CREATE OR REPLACE FUNCTION` |
| 3 | `services/glossary-service/internal/api/kinds_handler.go` | Extract `listKindsSystem()` helper; add `listKindsGrouped()`; update `listKinds()` to branch on `?book_id` |
| 4 | `services/glossary-service/internal/api/entity_handler.go` | Update `kindSummary` struct (add `KindTier`); update `createEntity`; update `loadEntityDetail` (Q1 + Q3); update `listEntities` |
| 5 | `frontend/src/features/glossary/types.ts` | Add `UserKindSummary`, `BookKindSummary`, `AllKindsResponse`, `AnyKindEntry`; extend `KindSummary` with `kind_tier` |
| 6 | `frontend/src/features/glossary/api.ts` | Add `getKindsSystem`, `getAllKinds`; update `createEntity` signature |
| 7 | `frontend/src/features/glossary/hooks/useEntityKinds.ts` | Accept optional `bookId`; use `getAllKinds` when provided |
| 8 | `frontend/src/features/glossary/components/KindBadge.tsx` | New file |
| 9 | `frontend/src/features/glossary/components/CreateEntityModal.tsx` | New props; add T2/T3 groups |
| 10 | `frontend/src/features/glossary/components/GlossaryFiltersBar.tsx` | New props; add T2/T3 kind chip rows |
| 11 | `frontend/src/pages/GlossaryPage.tsx` | Use `useEntityKinds(bookId)`; update `handleKindSelect`; pass `allKinds` to modal+filter |
| 12 | `frontend/src/features/glossary/components/GlossaryEntityCard.tsx` | Use `KindBadge` |

---

## 8) Exit Criteria

| # | Criterion |
|---|---|
| 1 | `GET /v1/glossary/kinds?book_id=X` returns `{ system: [...], user: [...], book: [...] }` |
| 2 | `GET /v1/glossary/kinds` (no `book_id`) still returns flat T1 `EntityKind[]` (backward compat) |
| 3 | `POST .../entities` with `{ kind_tier: "user", kind_ref_id: uuid }` → entity created with `user_kind_id` set, `kind_id = NULL` |
| 4 | `POST .../entities` with `{ kind_tier: "book", kind_ref_id: uuid }` → entity created with `book_kind_id` set |
| 5 | `POST .../entities` with legacy `{ kind_id: uuid }` still works as before (backward compat) |
| 6 | `GET .../entities/{id}` for T2 entity → `kind.kind_tier = "user"`, `kind.name` from `user_kinds` |
| 7 | `GET .../entities/{id}` for T3 entity → `kind.kind_tier = "book"`, `kind.name` from `book_kinds` |
| 8 | `GET .../entities?kind_codes=my_knight_code` filters correctly for T2 kind code |
| 9 | `entity_snapshot` for T2 entity has `kind.source = "user"` and correct kind metadata |
| 10 | `entity_snapshot` for T3 entity has `kind.source = "book"` and correct kind metadata |
| 11 | Existing T1 entities unaffected — all existing tests pass |
| 12 | `CreateEntityModal` shows T2 / T3 groups (My kinds / Book kinds) when non-empty |
| 13 | `GlossaryFiltersBar` shows T2/T3 kind chips when non-empty |
| 14 | `KindBadge` shows tier indicator (👤 for user, 📖 for book, none for system) |
| 15 | CHECK constraint `ck_entity_exactly_one_kind` rejects entity with 0 or 2+ kind FKs |
| 16 | CHECK constraint `ck_attrval_exactly_one_def` rejects attr value row with 0 or 2+ def FKs |

---

## 9) Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `ALTER COLUMN kind_id DROP NOT NULL` on `glossary_entities` fails if old rows somehow violate the forthcoming CHECK | Run migration in transaction; validate row count `WHERE kind_id IS NULL` = 0 before adding CHECK |
| `DROP CONSTRAINT entity_attribute_values_entity_id_attr_def_id_key` may have a different auto-generated name in a specific PG version | Use `IF EXISTS` in the ALTER; also add a fallback that drops any constraint with `pg_constraint` lookup if needed |
| `v_attr_def` JOIN in display_name subquery + listEntities is slower than direct T1 JOIN | Add `EXPLAIN ANALYZE` in dev; the view has covering indexes from SS-5 — acceptable for expected dataset sizes |
| `listEntities` query with LEFT JOINs across 3 kind tables + dynamic WHERE is harder to read | Keep the existing query-builder pattern; add comments marking the new LEFT JOINs |
| Snapshot trigger update changes output format — existing consumers parse `kind.source` | SS-1 design already includes `kind.source` in snapshot schema; SS-7 populates it for T2/T3 |
| `GlossaryFiltersBar` receives `AllKindsResponse` but some call sites still pass `EntityKind[]` | Check all usages; only `GlossaryPage` uses it — one update needed |
| Frontend `createEntity` callers outside `GlossaryPage` still call old signature | `glossaryApi.createEntity` old overload is removed — TypeScript compile error will catch all callers |
