# SS-5 — T3 Book Kind CRUD: Detailed Design

## Document Metadata

- Document ID: LW-M05-94
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Tech Lead
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Parent Plan: [doc 89](89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md) — SS-5 row
- Depends on: SS-4 complete (`user_kinds` table must exist for clone-from-T2 FK)
- Summary: Full technical design for book-level (T3) glossary kind management. Mirrors SS-4 but scoped to a specific book. Additionally creates the `v_attr_def` unified view (all three tiers available after SS-5). Frontend adds `BookGlossaryKindsPage` within the book context, plus recycle bin extension.

## Change History

| Version | Date       | Change         | Author    |
| ------- | ---------- | -------------- | --------- |
| 0.1.0   | 2026-03-25 | Initial design | Assistant |

---

## 1) Goal & Scope

**In scope:**
- `book_kinds` and `book_kind_attributes` DB tables with soft-delete
- Full CRUD API scoped under `/v1/glossary/books/{book_id}/kinds`
- Clone from T1 system kind OR T2 user kind
- Soft delete with entity check guard (409 if live entities exist)
- Attribute soft delete with force confirmation (same as SS-4)
- `v_attr_def` unified view across T1+T2+T3 (created in this migration)
- Recycle bin extension: book-scoped kind trash at `/v1/glossary/books/{book_id}/kinds-trash`
- Frontend: `BookGlossaryKindsPage` at `/books/:bookId/glossary/kinds`
- Frontend: `RecycleBinPage` extended with "Book Kinds" category tab
- Navigation: "Kinds" link on GlossaryPage toolbar + BookDetailPage

**Out of scope (deferred to SS-7):**
- Wiring T3 kinds into the entity creation picker
- `entity_attribute_values` polymorphic FK columns for `book_attr_def_id`

**Difference from SS-4:**
- Two clone sources instead of one: T1 (`clone_from_kind_id`) **or** T2 (`clone_from_user_kind_id`)
- Scoped to a book: `verifyBookOwner` used for all handlers (calls book-service)
- Recycle bin is book-scoped (same endpoint pattern as entity trash)
- `v_attr_def` view is **created** in SS-5 (first time all three tiers are available)

---

## 2) DB Migration

**New function:** `migrate.UpBookKinds(ctx, pool)` in `services/glossary-service/internal/migrate/migrate.go`

### 2.1 DDL

```sql
-- book_kinds: T3 kinds scoped to a single book
CREATE TABLE IF NOT EXISTS book_kinds (
  book_kind_id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id                  UUID        NOT NULL,
  owner_user_id            UUID        NOT NULL,
  code                     TEXT        NOT NULL,
  name                     TEXT        NOT NULL,
  description              TEXT,
  icon                     TEXT        NOT NULL DEFAULT 'box',
  color                    TEXT        NOT NULL DEFAULT '#6366f1',
  genre_tags               TEXT[]      NOT NULL DEFAULT '{}',
  is_active                BOOLEAN     NOT NULL DEFAULT true,
  cloned_from_kind_id      UUID        REFERENCES entity_kinds(kind_id) ON DELETE SET NULL,
  cloned_from_user_kind_id UUID        REFERENCES user_kinds(user_kind_id) ON DELETE SET NULL,
  permanently_deleted_at   TIMESTAMPTZ,
  deleted_at               TIMESTAMPTZ,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_id, code),
  -- At most one clone source
  CONSTRAINT ck_bk_clone_source CHECK (
    (cloned_from_kind_id IS NOT NULL)::int +
    (cloned_from_user_kind_id IS NOT NULL)::int <= 1
  )
);
CREATE INDEX IF NOT EXISTS idx_bk_book
  ON book_kinds(book_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bk_trash
  ON book_kinds(book_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;

-- book_kind_attributes: attribute definitions for T3 kinds
CREATE TABLE IF NOT EXISTS book_kind_attributes (
  attr_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  book_kind_id UUID        NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  code         TEXT        NOT NULL,
  name         TEXT        NOT NULL,
  description  TEXT,
  field_type   TEXT        NOT NULL DEFAULT 'text',
  is_required  BOOLEAN     NOT NULL DEFAULT false,
  sort_order   INT         NOT NULL DEFAULT 0,
  options      TEXT[],
  deleted_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_bka_kind
  ON book_kind_attributes(book_kind_id) WHERE deleted_at IS NULL;

-- v_attr_def: unified view across T1 (system) + T2 (user) + T3 (book) attribute definitions.
-- Used by snapshot trigger, export refactor, and entity detail queries from SS-7 onward.
-- Created here because all three tiers now exist.
CREATE OR REPLACE VIEW v_attr_def AS
  SELECT
    attr_def_id  AS ref_id,
    'system'     AS source,
    kind_id      AS kind_ref_id,
    NULL::uuid   AS user_kind_id,
    NULL::uuid   AS book_kind_id,
    code, name, field_type, is_required, sort_order, options
  FROM attribute_definitions
UNION ALL
  SELECT
    attr_id,
    'user',
    NULL::uuid,
    user_kind_id,
    NULL::uuid,
    code, name, field_type, is_required, sort_order, options
  FROM user_kind_attributes
  WHERE deleted_at IS NULL
UNION ALL
  SELECT
    attr_id,
    'book',
    NULL::uuid,
    NULL::uuid,
    book_kind_id,
    code, name, field_type, is_required, sort_order, options
  FROM book_kind_attributes
  WHERE deleted_at IS NULL;
```

**Schema notes:**
- `options TEXT[]` — matches T1 + T2 for `v_attr_def` UNION ALL type compatibility.
- `CHECK ck_bk_clone_source` — ensures at most one clone source (not both T1 and T2). Zero is allowed (created from scratch).
- `v_attr_def` uses `NULL::uuid` casts so all three SELECT branches produce the same column types (`uuid`). PostgreSQL requires identical column count and compatible types in UNION ALL.
- The view excludes `attribute_definitions` deleted rows via the T1 fact that T1 has no `deleted_at` (system-managed).

### 2.2 Migration function

```go
const bookKindsSQL = `
CREATE TABLE IF NOT EXISTS book_kinds (
  book_kind_id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id                  UUID        NOT NULL,
  owner_user_id            UUID        NOT NULL,
  code                     TEXT        NOT NULL,
  name                     TEXT        NOT NULL,
  description              TEXT,
  icon                     TEXT        NOT NULL DEFAULT 'box',
  color                    TEXT        NOT NULL DEFAULT '#6366f1',
  genre_tags               TEXT[]      NOT NULL DEFAULT '{}',
  is_active                BOOLEAN     NOT NULL DEFAULT true,
  cloned_from_kind_id      UUID        REFERENCES entity_kinds(kind_id) ON DELETE SET NULL,
  cloned_from_user_kind_id UUID        REFERENCES user_kinds(user_kind_id) ON DELETE SET NULL,
  permanently_deleted_at   TIMESTAMPTZ,
  deleted_at               TIMESTAMPTZ,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_id, code),
  CONSTRAINT ck_bk_clone_source CHECK (
    (cloned_from_kind_id IS NOT NULL)::int +
    (cloned_from_user_kind_id IS NOT NULL)::int <= 1
  )
);
CREATE INDEX IF NOT EXISTS idx_bk_book
  ON book_kinds(book_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bk_trash
  ON book_kinds(book_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS book_kind_attributes (
  attr_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  book_kind_id UUID        NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  code         TEXT        NOT NULL,
  name         TEXT        NOT NULL,
  description  TEXT,
  field_type   TEXT        NOT NULL DEFAULT 'text',
  is_required  BOOLEAN     NOT NULL DEFAULT false,
  sort_order   INT         NOT NULL DEFAULT 0,
  options      TEXT[],
  deleted_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_bka_kind
  ON book_kind_attributes(book_kind_id) WHERE deleted_at IS NULL;

CREATE OR REPLACE VIEW v_attr_def AS
  SELECT
    attr_def_id  AS ref_id,
    'system'     AS source,
    kind_id      AS kind_ref_id,
    NULL::uuid   AS user_kind_id,
    NULL::uuid   AS book_kind_id,
    code, name, field_type, is_required, sort_order, options
  FROM attribute_definitions
UNION ALL
  SELECT
    attr_id,
    'user',
    NULL::uuid,
    user_kind_id,
    NULL::uuid,
    code, name, field_type, is_required, sort_order, options
  FROM user_kind_attributes
  WHERE deleted_at IS NULL
UNION ALL
  SELECT
    attr_id,
    'book',
    NULL::uuid,
    NULL::uuid,
    book_kind_id,
    code, name, field_type, is_required, sort_order, options
  FROM book_kind_attributes
  WHERE deleted_at IS NULL;
`

func UpBookKinds(ctx context.Context, pool *pgxpool.Pool) error {
    if _, err := pool.Exec(ctx, bookKindsSQL); err != nil {
        return fmt.Errorf("migrate book_kinds: %w", err)
    }
    return nil
}
```

### 2.3 Updated `main.go` call sequence (cumulative)

```go
if err := migrate.Up(ctx, pool);                  err != nil { log.Fatal(err) }
if err := migrate.Seed(ctx, pool);                err != nil { log.Fatal(err) }
if err := migrate.UpSnapshot(ctx, pool);          err != nil { log.Fatal(err) } // SS-1
if err := migrate.BackfillSnapshots(ctx, pool);   err != nil { log.Fatal(err) } // SS-1
if err := migrate.UpSoftDelete(ctx, pool);        err != nil { log.Fatal(err) } // SS-2
if err := migrate.UpGlossaryPrefs(ctx, pool);     err != nil { log.Fatal(err) } // SS-3
if err := migrate.UpUserKinds(ctx, pool);         err != nil { log.Fatal(err) } // SS-4
if err := migrate.UpBookKinds(ctx, pool);         err != nil { log.Fatal(err) } // SS-5
```

---

## 3) Backend — Response Types

**New file:** `services/glossary-service/internal/api/book_kind_handler.go`

### 3.1 Response structs

Mirrors SS-4 with `BookKindID` / `BookID` field names:

```go
package api

import "time"

type bookKindAttrResp struct {
    AttrID      string    `json:"attr_id"`
    BookKindID  string    `json:"book_kind_id"`
    Code        string    `json:"code"`
    Name        string    `json:"name"`
    Description *string   `json:"description,omitempty"`
    FieldType   string    `json:"field_type"`
    IsRequired  bool      `json:"is_required"`
    SortOrder   int       `json:"sort_order"`
    Options     []string  `json:"options,omitempty"`
    CreatedAt   time.Time `json:"created_at"`
}

type bookKindSummaryResp struct {
    BookKindID              string    `json:"book_kind_id"`
    BookID                  string    `json:"book_id"`
    OwnerUserID             string    `json:"owner_user_id"`
    Code                    string    `json:"code"`
    Name                    string    `json:"name"`
    Description             *string   `json:"description,omitempty"`
    Icon                    string    `json:"icon"`
    Color                   string    `json:"color"`
    GenreTags               []string  `json:"genre_tags"`
    IsActive                bool      `json:"is_active"`
    ClonedFromKindID        *string   `json:"cloned_from_kind_id,omitempty"`
    ClonedFromUserKindID    *string   `json:"cloned_from_user_kind_id,omitempty"`
    AttributeCount          int       `json:"attribute_count"`
    CreatedAt               time.Time `json:"created_at"`
    UpdatedAt               time.Time `json:"updated_at"`
}

type bookKindDetailResp struct {
    bookKindSummaryResp
    Attributes []bookKindAttrResp `json:"attributes"`
}

type bookKindListResp struct {
    Items  []bookKindSummaryResp `json:"items"`
    Total  int                   `json:"total"`
    Limit  int                   `json:"limit"`
    Offset int                   `json:"offset"`
}

type bookKindTrashItem struct {
    BookKindID string    `json:"book_kind_id"`
    BookID     string    `json:"book_id"`
    Code       string    `json:"code"`
    Name       string    `json:"name"`
    Icon       string    `json:"icon"`
    Color      string    `json:"color"`
    DeletedAt  time.Time `json:"deleted_at"`
}
```

### 3.2 Helper: `verifyBookKindOwner`

Unlike SS-4's user-only check, T3 kinds require book ownership verification via the book-service:

```go
// verifyBookKindOwner checks:
// 1. The book exists and is owned by userID (via book-service projection)
// 2. The book_kind_id belongs to that book and is not permanently deleted
func (s *Server) verifyBookKindOwner(
    w http.ResponseWriter, ctx context.Context,
    bookKindID, bookID, userID uuid.UUID,
) bool {
    // Step 1: book ownership (reuses existing verifyBookOwner helper)
    if !s.verifyBookOwner(w, ctx, bookID, userID) {
        return false
    }
    // Step 2: kind belongs to book
    var exists bool
    if err := s.pool.QueryRow(ctx,
        `SELECT EXISTS(SELECT 1 FROM book_kinds
                       WHERE book_kind_id=$1 AND book_id=$2
                         AND permanently_deleted_at IS NULL)`,
        bookKindID, bookID,
    ).Scan(&exists); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
        return false
    }
    if !exists {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "book kind not found")
        return false
    }
    return true
}
```

### 3.3 `loadBookKindDetail` helper

```go
func (s *Server) loadBookKindDetail(ctx context.Context, bookKindID, bookID uuid.UUID) (*bookKindDetailResp, error) {
    var d bookKindDetailResp
    err := s.pool.QueryRow(ctx, `
        SELECT bk.book_kind_id, bk.book_id, bk.owner_user_id, bk.code, bk.name, bk.description,
               bk.icon, bk.color, bk.genre_tags, bk.is_active,
               bk.cloned_from_kind_id, bk.cloned_from_user_kind_id,
               bk.created_at, bk.updated_at,
               COUNT(bka.attr_id) AS attribute_count
        FROM book_kinds bk
        LEFT JOIN book_kind_attributes bka
          ON bka.book_kind_id = bk.book_kind_id AND bka.deleted_at IS NULL
        WHERE bk.book_kind_id = $1
          AND bk.book_id = $2
          AND bk.permanently_deleted_at IS NULL
        GROUP BY bk.book_kind_id`,
        bookKindID, bookID,
    ).Scan(
        &d.BookKindID, &d.BookID, &d.OwnerUserID, &d.Code, &d.Name, &d.Description,
        &d.Icon, &d.Color, &d.GenreTags, &d.IsActive,
        &d.ClonedFromKindID, &d.ClonedFromUserKindID,
        &d.CreatedAt, &d.UpdatedAt, &d.AttributeCount,
    )
    if err != nil {
        return nil, err
    }
    if d.GenreTags == nil { d.GenreTags = []string{} }

    rows, err := s.pool.Query(ctx, `
        SELECT attr_id, book_kind_id, code, name, description,
               field_type, is_required, sort_order, options, created_at
        FROM book_kind_attributes
        WHERE book_kind_id = $1 AND deleted_at IS NULL
        ORDER BY sort_order ASC, created_at ASC`,
        bookKindID)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    d.Attributes = []bookKindAttrResp{}
    for rows.Next() {
        var a bookKindAttrResp
        if err := rows.Scan(
            &a.AttrID, &a.BookKindID, &a.Code, &a.Name, &a.Description,
            &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.CreatedAt,
        ); err != nil {
            return nil, err
        }
        if a.Options == nil { a.Options = []string{} }
        d.Attributes = append(d.Attributes, a)
    }
    return &d, rows.Err()
}
```

---

## 4) Backend — Kind CRUD Handlers

### 4.1 GET /v1/glossary/books/{book_id}/kinds

```go
func (s *Server) listBookKinds(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    q := r.URL.Query()
    limit  := parseIntDefault(q.Get("limit"),  20)
    offset := parseIntDefault(q.Get("offset"),  0)
    if limit > 100 { limit = 100 }

    filterActive := q.Get("is_active")
    sortBy       := q.Get("sort") // "name" | default "created_at"

    where := []string{
        "bk.book_id = $1",
        "bk.deleted_at IS NULL",
        "bk.permanently_deleted_at IS NULL",
    }
    args := []any{bookID}
    argN := 2

    if filterActive == "true" {
        where = append(where, fmt.Sprintf("bk.is_active = $%d", argN))
        args = append(args, true); argN++
    } else if filterActive == "false" {
        where = append(where, fmt.Sprintf("bk.is_active = $%d", argN))
        args = append(args, false); argN++
    }

    orderClause := "bk.created_at DESC"
    if sortBy == "name" { orderClause = "bk.name ASC" }

    ctx := r.Context()

    var total int
    countSQL := fmt.Sprintf(
        "SELECT COUNT(*) FROM book_kinds bk WHERE %s",
        strings.Join(where, " AND "))
    if err := s.pool.QueryRow(ctx, countSQL, args...).Scan(&total); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
        return
    }

    args = append(args, limit, offset)
    listSQL := fmt.Sprintf(`
        SELECT bk.book_kind_id, bk.book_id, bk.owner_user_id, bk.code, bk.name, bk.description,
               bk.icon, bk.color, bk.genre_tags, bk.is_active,
               bk.cloned_from_kind_id, bk.cloned_from_user_kind_id,
               bk.created_at, bk.updated_at,
               COUNT(bka.attr_id) AS attribute_count
        FROM book_kinds bk
        LEFT JOIN book_kind_attributes bka
          ON bka.book_kind_id = bk.book_kind_id AND bka.deleted_at IS NULL
        WHERE %s
        GROUP BY bk.book_kind_id
        ORDER BY %s
        LIMIT $%d OFFSET $%d`,
        strings.Join(where, " AND "), orderClause, argN, argN+1)

    rows, err := s.pool.Query(ctx, listSQL, args...)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
        return
    }
    defer rows.Close()

    items := []bookKindSummaryResp{}
    for rows.Next() {
        var bk bookKindSummaryResp
        if err := rows.Scan(
            &bk.BookKindID, &bk.BookID, &bk.OwnerUserID, &bk.Code, &bk.Name, &bk.Description,
            &bk.Icon, &bk.Color, &bk.GenreTags, &bk.IsActive,
            &bk.ClonedFromKindID, &bk.ClonedFromUserKindID,
            &bk.CreatedAt, &bk.UpdatedAt, &bk.AttributeCount,
        ); err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
            return
        }
        if bk.GenreTags == nil { bk.GenreTags = []string{} }
        items = append(items, bk)
    }
    if err := rows.Err(); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
        return
    }

    writeJSON(w, http.StatusOK, bookKindListResp{
        Items: items, Total: total, Limit: limit, Offset: offset,
    })
}
```

### 4.2 POST /v1/glossary/books/{book_id}/kinds

Two clone sources (T1 or T2) plus from-scratch:

```go
func (s *Server) createBookKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    var in struct {
        Code                string   `json:"code"`
        Name                string   `json:"name"`
        Description         *string  `json:"description"`
        Icon                string   `json:"icon"`
        Color               string   `json:"color"`
        GenreTags           []string `json:"genre_tags"`
        CloneFromKindID     *string  `json:"clone_from_kind_id"`      // T1
        CloneFromUserKindID *string  `json:"clone_from_user_kind_id"` // T2
    }
    if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
        return
    }
    if strings.TrimSpace(in.Name) == "" {
        writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "name is required")
        return
    }
    if in.CloneFromKindID != nil && in.CloneFromUserKindID != nil {
        writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
            "provide at most one of clone_from_kind_id or clone_from_user_kind_id")
        return
    }
    if in.Icon == "" { in.Icon = "box" }
    if in.Color == "" { in.Color = "#6366f1" }
    if in.GenreTags == nil { in.GenreTags = []string{} }
    if strings.TrimSpace(in.Code) == "" { in.Code = slugify(in.Name) }

    var cloneFromKindID     *uuid.UUID
    var cloneFromUserKindID *uuid.UUID
    if in.CloneFromKindID != nil && *in.CloneFromKindID != "" {
        id, err := uuid.Parse(*in.CloneFromKindID)
        if err != nil {
            writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid clone_from_kind_id")
            return
        }
        cloneFromKindID = &id
    }
    if in.CloneFromUserKindID != nil && *in.CloneFromUserKindID != "" {
        id, err := uuid.Parse(*in.CloneFromUserKindID)
        if err != nil {
            writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid clone_from_user_kind_id")
            return
        }
        cloneFromUserKindID = &id
    }

    ctx := r.Context()
    tx, err := s.pool.Begin(ctx)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
        return
    }
    defer tx.Rollback(ctx)

    var bkID uuid.UUID
    err = tx.QueryRow(ctx, `
        INSERT INTO book_kinds
          (book_id, owner_user_id, code, name, description, icon, color, genre_tags,
           cloned_from_kind_id, cloned_from_user_kind_id)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING book_kind_id`,
        bookID, userID, in.Code, in.Name, in.Description,
        in.Icon, in.Color, in.GenreTags,
        cloneFromKindID, cloneFromUserKindID,
    ).Scan(&bkID)
    if err != nil {
        if isUniqueViolation(err) {
            writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE",
                "a book kind with this code already exists in this book")
            return
        }
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
        return
    }

    // Clone attributes from T1 system kind
    if cloneFromKindID != nil {
        if _, err = tx.Exec(ctx, `
            INSERT INTO book_kind_attributes
              (book_kind_id, code, name, description, field_type, is_required, sort_order, options)
            SELECT $1, code, name, description, field_type, is_required, sort_order, options
            FROM attribute_definitions
            WHERE kind_id = $2
            ORDER BY sort_order`,
            bkID, cloneFromKindID,
        ); err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clone T1 attrs failed")
            return
        }
    }

    // Clone attributes from T2 user kind
    if cloneFromUserKindID != nil {
        // Verify the T2 kind belongs to this user
        var ukOwner uuid.UUID
        if err := tx.QueryRow(ctx,
            `SELECT owner_user_id FROM user_kinds
             WHERE user_kind_id=$1 AND deleted_at IS NULL AND permanently_deleted_at IS NULL`,
            cloneFromUserKindID,
        ).Scan(&ukOwner); err != nil || ukOwner != userID {
            writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN",
                "you do not own the specified user kind")
            return
        }

        if _, err = tx.Exec(ctx, `
            INSERT INTO book_kind_attributes
              (book_kind_id, code, name, description, field_type, is_required, sort_order, options)
            SELECT $1, code, name, description, field_type, is_required, sort_order, options
            FROM user_kind_attributes
            WHERE user_kind_id = $2 AND deleted_at IS NULL
            ORDER BY sort_order`,
            bkID, cloneFromUserKindID,
        ); err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clone T2 attrs failed")
            return
        }
    }

    if err := tx.Commit(ctx); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
        return
    }

    detail, err := s.loadBookKindDetail(ctx, bkID, bookID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
        return
    }
    writeJSON(w, http.StatusCreated, detail)
}
```

### 4.3 GET /v1/glossary/books/{book_id}/kinds/{book_kind_id}

```go
func (s *Server) getBookKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    bookKindID, ok := parsePathUUID(w, r, "book_kind_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    detail, err := s.loadBookKindDetail(r.Context(), bookKindID, bookID)
    if err == pgx.ErrNoRows {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "book kind not found")
        return
    }
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
        return
    }
    writeJSON(w, http.StatusOK, detail)
}
```

### 4.4 PATCH /v1/glossary/books/{book_id}/kinds/{book_kind_id}

Identical logic to SS-4 `patchUserKind` — same allowed fields, same partial-update pattern. Only difference: uses `verifyBookKindOwner` and updates `book_kinds`:

```go
func (s *Server) patchBookKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    bookKindID, ok := parsePathUUID(w, r, "book_kind_id")
    if !ok { return }
    if !s.verifyBookKindOwner(w, r.Context(), bookKindID, bookID, userID) { return }

    var in map[string]json.RawMessage
    if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
        return
    }

    setClauses := []string{}
    args := []any{}
    argN := 1

    // Same field handling as patchUserKind: name, description, icon, color, genre_tags, is_active
    // (code is immutable)
    for _, field := range []string{"name", "description", "icon", "color", "genre_tags", "is_active"} {
        raw, ok := in[field]
        if !ok { continue }
        switch field {
        case "name":
            var v string
            if err := json.Unmarshal(raw, &v); err != nil || strings.TrimSpace(v) == "" {
                writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid name"); return
            }
            setClauses = append(setClauses, fmt.Sprintf("name = $%d", argN)); args = append(args, v); argN++
        case "description":
            var v *string
            if err := json.Unmarshal(raw, &v); err != nil {
                writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid description"); return
            }
            setClauses = append(setClauses, fmt.Sprintf("description = $%d", argN)); args = append(args, v); argN++
        case "icon":
            var v string
            if err := json.Unmarshal(raw, &v); err != nil {
                writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid icon"); return
            }
            setClauses = append(setClauses, fmt.Sprintf("icon = $%d", argN)); args = append(args, v); argN++
        case "color":
            var v string
            if err := json.Unmarshal(raw, &v); err != nil {
                writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid color"); return
            }
            setClauses = append(setClauses, fmt.Sprintf("color = $%d", argN)); args = append(args, v); argN++
        case "genre_tags":
            var v []string
            if err := json.Unmarshal(raw, &v); err != nil {
                writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid genre_tags"); return
            }
            if v == nil { v = []string{} }
            setClauses = append(setClauses, fmt.Sprintf("genre_tags = $%d", argN)); args = append(args, v); argN++
        case "is_active":
            var v bool
            if err := json.Unmarshal(raw, &v); err != nil {
                writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid is_active"); return
            }
            setClauses = append(setClauses, fmt.Sprintf("is_active = $%d", argN)); args = append(args, v); argN++
        }
    }

    if len(setClauses) > 0 {
        setClauses = append(setClauses, "updated_at = now()")
        args = append(args, bookKindID, bookID)
        updateSQL := fmt.Sprintf(
            "UPDATE book_kinds SET %s WHERE book_kind_id = $%d AND book_id = $%d",
            strings.Join(setClauses, ", "), argN, argN+1)
        if _, err := s.pool.Exec(r.Context(), updateSQL, args...); err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
            return
        }
    }

    detail, err := s.loadBookKindDetail(r.Context(), bookKindID, bookID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
        return
    }
    writeJSON(w, http.StatusOK, detail)
}
```

### 4.5 DELETE /v1/glossary/books/{book_id}/kinds/{book_kind_id}

```go
func (s *Server) deleteBookKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    bookKindID, ok := parsePathUUID(w, r, "book_kind_id")
    if !ok { return }
    if !s.verifyBookKindOwner(w, r.Context(), bookKindID, bookID, userID) { return }

    ctx := r.Context()

    // Guard: reject if live entities use this kind (pre-SS-7 graceful degradation)
    var entityCount int
    err := s.pool.QueryRow(ctx, `
        SELECT COUNT(*) FROM glossary_entities
        WHERE book_kind_id = $1
          AND deleted_at IS NULL
          AND permanently_deleted_at IS NULL`,
        bookKindID,
    ).Scan(&entityCount)
    if err != nil {
        var pgErr *pgconn.PgError
        if errors.As(err, &pgErr) && pgErr.Code == "42703" {
            entityCount = 0 // column not yet added (pre-SS-7)
        } else {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
            return
        }
    }
    if entityCount > 0 {
        writeError(w, http.StatusConflict, "GLOSS_KIND_HAS_ENTITIES",
            fmt.Sprintf("%d entities use this kind; reassign or delete them first", entityCount))
        return
    }

    tag, err := s.pool.Exec(ctx, `
        UPDATE book_kinds
        SET deleted_at = now(), updated_at = now()
        WHERE book_kind_id = $1 AND book_id = $2 AND deleted_at IS NULL`,
        bookKindID, bookID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
        return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "book kind not found or already deleted")
        return
    }
    w.WriteHeader(http.StatusNoContent)
}
```

---

## 5) Backend — Attribute CRUD Handlers

**File:** `book_kind_handler.go` (continued)

All three attribute handlers (`createBookKindAttr`, `patchBookKindAttr`, `deleteBookKindAttr`) mirror SS-4's implementations with the following substitutions:

| SS-4 | SS-5 |
|---|---|
| `verifyUserKindOwner(w, ctx, userKindID, userID)` | `verifyBookKindOwner(w, ctx, bookKindID, bookID, userID)` + `parsePathUUID(w, r, "book_id")` |
| `user_kind_attributes` table | `book_kind_attributes` table |
| `user_kind_id` FK column | `book_kind_id` FK column |
| `entity_attribute_values.user_attr_def_id` | `entity_attribute_values.book_attr_def_id` |
| `UPDATE user_kinds SET updated_at = now()` | `UPDATE book_kinds SET updated_at = now()` |

**`deleteBookKindAttr` data guard** — checks `entity_attribute_values.book_attr_def_id` (degrades gracefully before SS-7 with error code `42703`). Exact same `?force=true` pattern as SS-4.

---

## 6) Backend — Recycle Bin Extension (Book Kinds)

Book kind trash is **book-scoped** — endpoints under `/v1/glossary/books/{book_id}/kinds-trash`.

### 6.1 `listBookKindTrash`

```go
func (s *Server) listBookKindTrash(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    q := r.URL.Query()
    limit  := parseIntDefault(q.Get("limit"),  20)
    offset := parseIntDefault(q.Get("offset"),  0)
    if limit > 100 { limit = 100 }

    ctx := r.Context()

    var total int
    if err := s.pool.QueryRow(ctx, `
        SELECT COUNT(*) FROM book_kinds
        WHERE book_id=$1
          AND deleted_at IS NOT NULL
          AND permanently_deleted_at IS NULL`,
        bookID).Scan(&total); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
        return
    }

    rows, err := s.pool.Query(ctx, `
        SELECT book_kind_id::text, book_id::text, code, name, icon, color, deleted_at
        FROM book_kinds
        WHERE book_id=$1
          AND deleted_at IS NOT NULL
          AND permanently_deleted_at IS NULL
        ORDER BY deleted_at DESC
        LIMIT $2 OFFSET $3`,
        bookID, limit, offset)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
        return
    }
    defer rows.Close()

    items := []bookKindTrashItem{}
    for rows.Next() {
        var it bookKindTrashItem
        if err := rows.Scan(&it.BookKindID, &it.BookID, &it.Code, &it.Name, &it.Icon, &it.Color, &it.DeletedAt); err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
            return
        }
        items = append(items, it)
    }

    writeJSON(w, http.StatusOK, map[string]any{
        "items": items, "total": total, "limit": limit, "offset": offset,
    })
}
```

### 6.2 `restoreBookKind` and `purgeBookKind`

Mirror SS-4's `restoreUserKind`/`purgeUserKind` with `book_kinds` table and `bookID` scoping. Both require `verifyBookOwner` before the UPDATE.

```go
func (s *Server) restoreBookKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r); if !ok { writeError(w, 401, "GLOSS_UNAUTHORIZED", "..."); return }
    bookID, ok := parsePathUUID(w, r, "book_id"); if !ok { return }
    bookKindID, ok := parsePathUUID(w, r, "book_kind_id"); if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    tag, err := s.pool.Exec(r.Context(), `
        UPDATE book_kinds SET deleted_at = NULL, updated_at = now()
        WHERE book_kind_id=$1 AND book_id=$2
          AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
        bookKindID, bookID)
    if err != nil { writeError(w, 500, "GLOSS_INTERNAL", "restore failed"); return }
    if tag.RowsAffected() == 0 { writeError(w, 404, "GLOSS_NOT_FOUND", "book kind not in trash"); return }
    w.WriteHeader(http.StatusNoContent)
}

func (s *Server) purgeBookKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r); if !ok { writeError(w, 401, "GLOSS_UNAUTHORIZED", "..."); return }
    bookID, ok := parsePathUUID(w, r, "book_id"); if !ok { return }
    bookKindID, ok := parsePathUUID(w, r, "book_kind_id"); if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    tag, err := s.pool.Exec(r.Context(), `
        UPDATE book_kinds SET permanently_deleted_at = now()
        WHERE book_kind_id=$1 AND book_id=$2
          AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
        bookKindID, bookID)
    if err != nil { writeError(w, 500, "GLOSS_INTERNAL", "purge failed"); return }
    if tag.RowsAffected() == 0 { writeError(w, 404, "GLOSS_NOT_FOUND", "book kind not in trash"); return }
    w.WriteHeader(http.StatusNoContent)
}
```

---

## 7) Route Registration

**File:** `services/glossary-service/internal/api/server.go`

Inside the `r.Route("/books/{book_id}", ...)` block, alongside the existing `/export` and `/recycle-bin` routes:

```go
// ── T3 Book Kind CRUD (SS-5) ──────────────────────────────────────────────────
r.Route("/kinds", func(r chi.Router) {
    r.Get("/", s.listBookKinds)
    r.Post("/", s.createBookKind)
    r.Route("/{book_kind_id}", func(r chi.Router) {
        r.Get("/", s.getBookKind)
        r.Patch("/", s.patchBookKind)
        r.Delete("/", s.deleteBookKind)
        r.Route("/attributes", func(r chi.Router) {
            r.Post("/", s.createBookKindAttr)
            r.Route("/{attr_id}", func(r chi.Router) {
                r.Patch("/", s.patchBookKindAttr)
                r.Delete("/", s.deleteBookKindAttr)
            })
        })
    })
})

// ── Book Kind Recycle Bin (SS-5) ─────────────────────────────────────────────
r.Route("/kinds-trash", func(r chi.Router) {
    r.Get("/", s.listBookKindTrash)
    r.Post("/{book_kind_id}/restore", s.restoreBookKind)
    r.Delete("/{book_kind_id}", s.purgeBookKind)
})
```

**Updated complete `r.Route("/books/{book_id}", ...)` block structure:**

```go
r.Route("/books/{book_id}", func(r chi.Router) {
    r.Get("/export", s.exportGlossary)
    r.Route("/entities", ...)       // existing
    r.Route("/recycle-bin", ...)    // SS-2: entity trash
    r.Route("/kinds", ...)          // SS-5: T3 kind CRUD  ← NEW
    r.Route("/kinds-trash", ...)    // SS-5: T3 kind trash ← NEW
})
```

---

## 8) Frontend — Types and API Client

### 8.1 New types in `frontend/src/features/glossary/types.ts`

```typescript
// ── T3 Book Kinds ─────────────────────────────────────────────────────────────

export type BookKindAttr = {
  attr_id: string;
  book_kind_id: string;
  code: string;
  name: string;
  description?: string;
  field_type: FieldType;
  is_required: boolean;
  sort_order: number;
  options?: string[];
  created_at: string;
};

export type BookKind = {
  book_kind_id: string;
  book_id: string;
  owner_user_id: string;
  code: string;
  name: string;
  description?: string;
  icon: string;
  color: string;
  genre_tags: string[];
  is_active: boolean;
  cloned_from_kind_id?: string | null;
  cloned_from_user_kind_id?: string | null;
  attribute_count: number;
  created_at: string;
  updated_at: string;
  attributes?: BookKindAttr[];
};

export type BookKindListResponse = {
  items: BookKind[];
  total: number;
  limit: number;
  offset: number;
};

export type BookKindTrashItem = {
  book_kind_id: string;
  book_id: string;
  code: string;
  name: string;
  icon: string;
  color: string;
  deleted_at: string;
};
```

### 8.2 API client additions in `frontend/src/features/glossary/api.ts`

```typescript
// ── T3 Book Kinds (SS-5) ─────────────────────────────────────────────────────

listBookKinds(
  token: string,
  bookId: string,
  params: { is_active?: boolean; sort?: 'name' | 'created_at'; limit?: number; offset?: number } = {},
): Promise<BookKindListResponse> {
  const qs = new URLSearchParams();
  if (params.is_active !== undefined) qs.set('is_active', String(params.is_active));
  if (params.sort)   qs.set('sort', params.sort);
  if (params.limit)  qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  const q = qs.toString();
  return apiJson<BookKindListResponse>(`${BASE}/books/${bookId}/kinds${q ? '?' + q : ''}`, { token });
},

createBookKind(
  token: string,
  bookId: string,
  body: {
    name: string;
    code?: string;
    description?: string;
    icon?: string;
    color?: string;
    genre_tags?: string[];
    clone_from_kind_id?: string;
    clone_from_user_kind_id?: string;
  },
): Promise<BookKind> {
  return apiJson<BookKind>(`${BASE}/books/${bookId}/kinds`, {
    method: 'POST',
    body: JSON.stringify(body),
    token,
  });
},

getBookKind(token: string, bookId: string, bookKindId: string): Promise<BookKind> {
  return apiJson<BookKind>(`${BASE}/books/${bookId}/kinds/${bookKindId}`, { token });
},

patchBookKind(
  token: string,
  bookId: string,
  bookKindId: string,
  changes: Partial<Pick<BookKind, 'name' | 'description' | 'icon' | 'color' | 'genre_tags' | 'is_active'>>,
): Promise<BookKind> {
  return apiJson<BookKind>(`${BASE}/books/${bookId}/kinds/${bookKindId}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
    token,
  });
},

deleteBookKind(token: string, bookId: string, bookKindId: string): Promise<void> {
  return apiJson<void>(`${BASE}/books/${bookId}/kinds/${bookKindId}`, {
    method: 'DELETE', token,
  });
},

createBookKindAttr(
  token: string,
  bookId: string,
  bookKindId: string,
  body: { name: string; code?: string; description?: string; field_type?: string; is_required?: boolean; sort_order?: number; options?: string[] },
): Promise<BookKindAttr> {
  return apiJson<BookKindAttr>(`${BASE}/books/${bookId}/kinds/${bookKindId}/attributes`, {
    method: 'POST', body: JSON.stringify(body), token,
  });
},

patchBookKindAttr(
  token: string, bookId: string, bookKindId: string, attrId: string,
  changes: Partial<Pick<BookKindAttr, 'name' | 'description' | 'field_type' | 'is_required' | 'sort_order' | 'options'>>,
): Promise<BookKindAttr> {
  return apiJson<BookKindAttr>(`${BASE}/books/${bookId}/kinds/${bookKindId}/attributes/${attrId}`, {
    method: 'PATCH', body: JSON.stringify(changes), token,
  });
},

deleteBookKindAttr(
  token: string, bookId: string, bookKindId: string, attrId: string, force = false,
): Promise<void> {
  const qs = force ? '?force=true' : '';
  return apiJson<void>(`${BASE}/books/${bookId}/kinds/${bookKindId}/attributes/${attrId}${qs}`, {
    method: 'DELETE', token,
  });
},

// ── Book Kind Recycle Bin (SS-5) ─────────────────────────────────────────────

listBookKindTrash(
  token: string,
  bookId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<{ items: BookKindTrashItem[]; total: number; limit: number; offset: number }> {
  const qs = new URLSearchParams();
  if (params.limit)  qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  const q = qs.toString();
  return apiJson(`${BASE}/books/${bookId}/kinds-trash${q ? '?' + q : ''}`, { token });
},

restoreBookKind(token: string, bookId: string, bookKindId: string): Promise<void> {
  return apiJson<void>(`${BASE}/books/${bookId}/kinds-trash/${bookKindId}/restore`, {
    method: 'POST', token,
  });
},

purgeBookKind(token: string, bookId: string, bookKindId: string): Promise<void> {
  return apiJson<void>(`${BASE}/books/${bookId}/kinds-trash/${bookKindId}`, {
    method: 'DELETE', token,
  });
},
```

---

## 9) Frontend — Pages and Components

### 9.1 BookGlossaryKindsPage.tsx

**Route:** `/books/:bookId/glossary/kinds`

This page serves as both the kind list and a per-kind management surface — mirrors `KindDetailPage` (SS-4) but lives within the book context.

**File:** `frontend/src/pages/BookGlossaryKindsPage.tsx`

Layout (two-panel or tabbed):
- Left / top: kind list (`BookKind[]`) with "New kind" button
- Right / below (on kind row click): inline kind detail showing attributes + add/remove form

```tsx
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { glossaryApi } from '@/features/glossary/api';
import type { BookKind, BookKindAttr } from '@/features/glossary/types';
import { CreateBookKindModal } from '@/components/glossary/CreateBookKindModal';
import { AttributeDeleteConfirmModal } from '@/components/glossary/AttributeDeleteConfirmModal';

export function BookGlossaryKindsPage() {
  const { bookId = '' } = useParams();
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [kinds, setKinds] = useState<BookKind[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedKind, setSelectedKind] = useState<BookKind | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ attr: BookKindAttr; count: number } | null>(null);
  const [newAttr, setNewAttr] = useState({ name: '', field_type: 'text', is_required: false });
  const [addingAttr, setAddingAttr] = useState(false);
  const [attrError, setAttrError] = useState('');

  const FIELD_TYPES = ['text','textarea','select','number','date','tags','url','boolean'] as const;

  async function loadKinds() {
    setLoading(true);
    try {
      const resp = await glossaryApi.listBookKinds(token, bookId, { limit: 50 });
      setKinds(resp.items);
    } finally {
      setLoading(false);
    }
  }

  async function loadSelected(bookKindId: string) {
    const detail = await glossaryApi.getBookKind(token, bookId, bookKindId);
    setSelectedKind(detail);
  }

  useEffect(() => { loadKinds(); }, []); // eslint-disable-line

  async function handleDelete(kind: BookKind) {
    if (!confirm(`Move "${kind.name}" to trash?`)) return;
    try {
      await glossaryApi.deleteBookKind(token, bookId, kind.book_kind_id);
      if (selectedKind?.book_kind_id === kind.book_kind_id) setSelectedKind(null);
      loadKinds();
    } catch (e: unknown) {
      alert((e as Error).message);
    }
  }

  async function handleToggleActive(kind: BookKind) {
    await glossaryApi.patchBookKind(token, bookId, kind.book_kind_id, { is_active: !kind.is_active });
    loadKinds();
    if (selectedKind?.book_kind_id === kind.book_kind_id) loadSelected(kind.book_kind_id);
  }

  async function handleAddAttr() {
    if (!selectedKind || !newAttr.name.trim()) { setAttrError('Name is required'); return; }
    setAddingAttr(true); setAttrError('');
    try {
      await glossaryApi.createBookKindAttr(token, bookId, selectedKind.book_kind_id, {
        name: newAttr.name.trim(), field_type: newAttr.field_type, is_required: newAttr.is_required,
      });
      setNewAttr({ name: '', field_type: 'text', is_required: false });
      loadSelected(selectedKind.book_kind_id);
    } catch (e: unknown) { setAttrError((e as Error).message); }
    finally { setAddingAttr(false); }
  }

  async function handleDeleteAttr(attr: BookKindAttr, force = false) {
    if (!selectedKind) return;
    try {
      await glossaryApi.deleteBookKindAttr(token, bookId, selectedKind.book_kind_id, attr.attr_id, force);
      setDeleteTarget(null);
      loadSelected(selectedKind.book_kind_id);
    } catch (e: unknown) {
      const msg = (e as Error).message || '';
      try {
        const body = JSON.parse(msg);
        if (body.code === 'GLOSS_ATTR_HAS_DATA') { setDeleteTarget({ attr, count: body.entity_count }); return; }
      } catch { /* not JSON */ }
      alert('Delete failed: ' + msg);
    }
  }

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to={`/books/${bookId}`} className="hover:underline">Book</Link>
        <span>›</span>
        <Link to={`/books/${bookId}/glossary`} className="hover:underline">Glossary</Link>
        <span>›</span>
        <span className="text-foreground">Kinds</span>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Book kinds</h1>
        <Button onClick={() => setShowCreate(true)}>+ New kind</Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-[260px_1fr]">
        {/* Kind list (left) */}
        <div className="space-y-1">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)
          ) : kinds.length === 0 ? (
            <p className="text-sm text-muted-foreground">No book kinds yet.</p>
          ) : (
            kinds.map((kind) => (
              <div
                key={kind.book_kind_id}
                onClick={() => loadSelected(kind.book_kind_id)}
                className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm hover:bg-muted ${
                  selectedKind?.book_kind_id === kind.book_kind_id ? 'bg-muted' : ''
                }`}
              >
                <span style={{ color: kind.color }}>{kind.icon}</span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">{kind.name}</p>
                  <p className="text-xs text-muted-foreground">{kind.attribute_count} attrs</p>
                </div>
                <div className="flex shrink-0 gap-1" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => handleToggleActive(kind)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                    title={kind.is_active ? 'Deactivate' : 'Activate'}
                  >
                    {kind.is_active ? '●' : '○'}
                  </button>
                  <button
                    onClick={() => handleDelete(kind)}
                    className="text-xs text-destructive hover:underline"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Kind detail (right) */}
        <div>
          {!selectedKind ? (
            <p className="text-sm text-muted-foreground">Select a kind to manage its attributes.</p>
          ) : (
            <div className="space-y-4 rounded border p-4">
              <div className="flex items-center gap-2">
                <span style={{ color: selectedKind.color }} className="text-xl">{selectedKind.icon}</span>
                <h2 className="font-semibold">{selectedKind.name}</h2>
                {!selectedKind.is_active && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">inactive</span>
                )}
              </div>

              {/* Attributes */}
              <div className="space-y-1">
                {(selectedKind.attributes ?? []).map((attr) => (
                  <div key={attr.attr_id} className="flex items-center gap-2 rounded border px-3 py-2 text-sm">
                    <span className="w-32 shrink-0 font-medium">{attr.name}</span>
                    <span className="w-20 shrink-0 text-xs text-muted-foreground">{attr.field_type}</span>
                    {attr.is_required && <span className="text-xs text-destructive">required</span>}
                    <span className="flex-1 text-xs text-muted-foreground">({attr.code})</span>
                    <button
                      onClick={() => handleDeleteAttr(attr)}
                      className="text-xs text-destructive hover:underline"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {(selectedKind.attributes ?? []).length === 0 && (
                  <p className="text-sm text-muted-foreground">No attributes.</p>
                )}
              </div>

              {/* Add attribute */}
              <div className="rounded border border-dashed p-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">Add attribute</p>
                <div className="flex flex-wrap gap-2">
                  <input
                    value={newAttr.name}
                    onChange={(e) => setNewAttr({ ...newAttr, name: e.target.value })}
                    placeholder="Name"
                    className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                  <select
                    value={newAttr.field_type}
                    onChange={(e) => setNewAttr({ ...newAttr, field_type: e.target.value })}
                    className="rounded border bg-background px-2 py-1 text-sm"
                  >
                    {FIELD_TYPES.map((ft) => <option key={ft} value={ft}>{ft}</option>)}
                  </select>
                  <label className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={newAttr.is_required} onChange={(e) => setNewAttr({ ...newAttr, is_required: e.target.checked })} />
                    Required
                  </label>
                  <Button size="sm" onClick={handleAddAttr} disabled={addingAttr}>
                    {addingAttr ? 'Adding…' : 'Add'}
                  </Button>
                </div>
                {attrError && <p className="mt-1 text-xs text-destructive">{attrError}</p>}
              </div>
            </div>
          )}
        </div>
      </div>

      {showCreate && (
        <CreateBookKindModal
          token={token}
          bookId={bookId}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadKinds(); }}
        />
      )}
      {deleteTarget && (
        <AttributeDeleteConfirmModal
          attrName={deleteTarget.attr.name}
          entityCount={deleteTarget.count}
          onConfirm={() => handleDeleteAttr(deleteTarget.attr, true)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
```

### 9.2 CreateBookKindModal.tsx

**File:** `frontend/src/components/glossary/CreateBookKindModal.tsx`

Extends `CreateKindModal` (SS-4) with a third mode: "Clone from my kinds" (T2 user kinds). Three-mode toggle: scratch / system / user.

```tsx
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { glossaryApi } from '@/features/glossary/api';
import type { EntityKind, UserKind } from '@/features/glossary/types';

type Mode = 'scratch' | 'system' | 'user';

type Props = { token: string; bookId: string; onClose: () => void; onCreated: () => void };

export function CreateBookKindModal({ token, bookId, onClose, onCreated }: Props) {
  const [mode, setMode] = useState<Mode>('scratch');

  const [name, setName]   = useState('');
  const [icon, setIcon]   = useState('📦');
  const [color, setColor] = useState('#6366f1');

  const [systemKinds, setSystemKinds] = useState<EntityKind[]>([]);
  const [userKinds, setUserKinds]     = useState<UserKind[]>([]);
  const [selectedKindId, setSelectedKindId]     = useState('');
  const [selectedUserKindId, setSelectedUserKindId] = useState('');
  const [search, setSearch] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError]           = useState('');

  useEffect(() => {
    if (mode === 'system' && systemKinds.length === 0) {
      glossaryApi.getKinds(token).then(setSystemKinds).catch(() => {});
    }
    if (mode === 'user' && userKinds.length === 0) {
      glossaryApi.listUserKinds(token, { is_active: true, limit: 100 })
        .then((r) => setUserKinds(r.items))
        .catch(() => {});
    }
  }, [mode, token, systemKinds.length, userKinds.length]);

  const filteredSystem = systemKinds.filter((k) =>
    k.name.toLowerCase().includes(search.toLowerCase()));
  const filteredUser = userKinds.filter((k) =>
    k.name.toLowerCase().includes(search.toLowerCase()));

  async function handleSubmit() {
    setError('');
    if (mode === 'scratch' && !name.trim()) { setError('Name is required'); return; }
    if (mode === 'system' && !selectedKindId) { setError('Select a system kind'); return; }
    if (mode === 'user' && !selectedUserKindId) { setError('Select one of your kinds'); return; }

    setSubmitting(true);
    try {
      if (mode === 'scratch') {
        await glossaryApi.createBookKind(token, bookId, { name: name.trim(), icon, color });
      } else if (mode === 'system') {
        const src = systemKinds.find((k) => k.kind_id === selectedKindId)!;
        await glossaryApi.createBookKind(token, bookId, {
          name: src.name, icon: src.icon, color: src.color,
          clone_from_kind_id: selectedKindId,
        });
      } else {
        const src = userKinds.find((k) => k.user_kind_id === selectedUserKindId)!;
        await glossaryApi.createBookKind(token, bookId, {
          name: src.name, icon: src.icon, color: src.color,
          clone_from_user_kind_id: selectedUserKindId,
        });
      }
      onCreated();
    } catch (e: unknown) { setError((e as Error).message || 'Create failed'); }
    finally { setSubmitting(false); }
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Create book kind</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>

        {/* Three-way mode selector */}
        <div className="mb-4 flex gap-1 rounded border p-1">
          {(['scratch', 'system', 'user'] as Mode[]).map((m) => (
            <button key={m} onClick={() => { setMode(m); setSearch(''); }}
              className={`flex-1 rounded py-1 text-xs font-medium transition-colors ${
                mode === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {m === 'scratch' ? 'From scratch' : m === 'system' ? 'System kind' : 'My kinds'}
            </button>
          ))}
        </div>

        {mode === 'scratch' && (
          <div className="space-y-3">
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Kind name *"
              className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring" />
            <div className="flex gap-3">
              <input value={icon} onChange={(e) => setIcon(e.target.value)}
                placeholder="Icon" className="flex-1 rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring" />
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)}
                className="h-9 w-16 cursor-pointer rounded border" />
            </div>
          </div>
        )}

        {(mode === 'system' || mode === 'user') && (
          <div className="space-y-3">
            <input value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder={mode === 'system' ? 'Search system kinds…' : 'Search your kinds…'}
              className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring" />
            <div className="max-h-48 overflow-y-auto rounded border">
              {mode === 'system' && filteredSystem.map((k) => (
                <button key={k.kind_id} onClick={() => setSelectedKindId(k.kind_id)}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted ${selectedKindId === k.kind_id ? 'bg-muted font-medium' : ''}`}
                >
                  <span style={{ color: k.color }}>{k.icon}</span>
                  <span>{k.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{k.default_attributes.length} attrs</span>
                </button>
              ))}
              {mode === 'user' && filteredUser.map((k) => (
                <button key={k.user_kind_id} onClick={() => setSelectedUserKindId(k.user_kind_id)}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted ${selectedUserKindId === k.user_kind_id ? 'bg-muted font-medium' : ''}`}
                >
                  <span style={{ color: k.color }}>{k.icon}</span>
                  <span>{k.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{k.attribute_count} attrs</span>
                </button>
              ))}
              {mode === 'user' && filteredUser.length === 0 && (
                <p className="p-3 text-sm text-muted-foreground">No active user kinds found.</p>
              )}
            </div>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Creating…' : 'Create'}</Button>
        </div>
      </div>
    </>
  );
}
```

### 9.3 Navigation Changes

#### GlossaryPage.tsx — "Manage kinds" link

Add a "Kinds" link to the toolbar alongside "+ New Entity":

**File:** `frontend/src/pages/GlossaryPage.tsx`

```tsx
// In the toolbar div, after "New Entity" button:
<Link
  to={`/books/${bookId}/glossary/kinds`}
  className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
>
  Kinds
</Link>
```

#### BookDetailPage.tsx — "Glossary Kinds" link

Add after the existing "Glossary" link (line ~139):

**File:** `frontend/src/pages/BookDetailPage.tsx`

```tsx
<Link to={`/books/${bookId}/glossary/kinds`} className="underline">
  Glossary kinds
</Link>
```

### 9.4 App.tsx — New Route

```tsx
import { BookGlossaryKindsPage } from './pages/BookGlossaryKindsPage';

// Add in AppRoutes(), after the glossary route:
<Route
  path="/books/:bookId/glossary/kinds"
  element={
    <RequireAuth>
      <BookGlossaryKindsPage />
    </RequireAuth>
  }
/>
```

### 9.5 RecycleBinPage.tsx — "Book Kinds" Tab

Extend the SS-2 tab structure (Books / Glossary Entities) with a third tab: "Book Kinds".

The book kinds trash is book-scoped, so the global recycle bin fans out across all user's books (same pattern as the Glossary Entities tab):

```tsx
// Add 'book-kinds' to the Tab type and tabs array
type Tab = 'books' | 'glossary' | 'book-kinds';

// Add tab:
{ id: 'book-kinds', label: 'Book Kinds' }

// Add state and load function:
const [bookKindItems, setBookKindItems] = useState<BookKindTrashItem[]>([]);
const [bookKindLoading, setBookKindLoading] = useState(false);
const [bookKindError, setBookKindError] = useState('');

const loadBookKindTrash = async () => {
  if (!accessToken) return;
  setBookKindLoading(true);
  setBookKindError('');
  try {
    const booksRes = await booksApi.listBooks(accessToken);
    const results = await Promise.all(
      booksRes.items.map((b) =>
        glossaryApi.listBookKindTrash(accessToken, b.book_id, { limit: 100 })
          .then((r) => r.items)
          .catch(() => [] as BookKindTrashItem[]),
      ),
    );
    setBookKindItems(
      results.flat().sort((a, b) =>
        new Date(b.deleted_at).getTime() - new Date(a.deleted_at).getTime(),
      ),
    );
  } catch (e) { setBookKindError((e as Error).message); }
  finally { setBookKindLoading(false); }
};

useEffect(() => {
  if (tab === 'book-kinds') void loadBookKindTrash();
}, [tab, accessToken]);

// In the render for tab === 'book-kinds':
{tab === 'book-kinds' && (
  <div className="space-y-2">
    {bookKindLoading ? (
      <Skeleton className="h-24 w-full" />
    ) : bookKindError ? (
      <p className="text-sm text-destructive">{bookKindError}</p>
    ) : bookKindItems.length === 0 ? (
      <p className="text-sm text-muted-foreground">No deleted book kinds.</p>
    ) : (
      bookKindItems.map((item) => (
        <div key={item.book_kind_id} className="flex items-center gap-3 rounded border p-3">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-sm"
            style={{ backgroundColor: item.color + '22', color: item.color }}
          >
            {item.icon}
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-medium">{item.name}</p>
            <p className="text-xs text-muted-foreground">
              Deleted {new Date(item.deleted_at).toLocaleDateString()}
            </p>
          </div>
          <div className="flex gap-1">
            <button
              onClick={async () => {
                await glossaryApi.restoreBookKind(accessToken!, item.book_id, item.book_kind_id);
                loadBookKindTrash();
              }}
              className="rounded px-2 py-1 text-xs text-primary hover:bg-muted"
            >
              Restore
            </button>
            <button
              onClick={async () => {
                if (!confirm('Permanently delete this kind?')) return;
                await glossaryApi.purgeBookKind(accessToken!, item.book_id, item.book_kind_id);
                loadBookKindTrash();
              }}
              className="rounded px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
            >
              Delete permanently
            </button>
          </div>
        </div>
      ))
    )}
  </div>
)}
```

---

## 10) Files to Create/Modify

### New Files

| File | Purpose |
|---|---|
| `services/glossary-service/internal/api/book_kind_handler.go` | All T3 kind + attr CRUD + trash handlers |
| `frontend/src/pages/BookGlossaryKindsPage.tsx` | Book kind management at `/books/:bookId/glossary/kinds` |
| `frontend/src/components/glossary/CreateBookKindModal.tsx` | 3-mode create modal (scratch / system / user) |

### Modified Files

| File | Change |
|---|---|
| `services/glossary-service/internal/migrate/migrate.go` | Add `bookKindsSQL` + `UpBookKinds()` (includes `v_attr_def` view) |
| `services/glossary-service/internal/api/server.go` | Register 10 new routes under `/books/{book_id}/kinds` + `/kinds-trash` |
| `frontend/src/features/glossary/types.ts` | Add `BookKindAttr`, `BookKind`, `BookKindListResponse`, `BookKindTrashItem` |
| `frontend/src/features/glossary/api.ts` | Add 12 new API functions |
| `frontend/src/pages/GlossaryPage.tsx` | Add "Kinds" link to toolbar |
| `frontend/src/pages/BookDetailPage.tsx` | Add "Glossary kinds" link |
| `frontend/src/pages/RecycleBinPage.tsx` | Add "Book Kinds" tab + fan-out load |
| `frontend/src/App.tsx` | Add `/books/:bookId/glossary/kinds` route |

---

## 11) Test Coverage

### Backend

| # | Scenario | Expected |
|---|---|---|
| T1 | `GET /books/{id}/kinds` — empty book | 200, `{items: []}` |
| T2 | `POST` from scratch | 201, kind with empty attributes |
| T3 | `POST` clone from T1 | 201, T1 attribute definitions copied |
| T4 | `POST` clone from T2 (owned by user) | 201, T2 attribute definitions copied |
| T5 | `POST` clone from T2 (owned by another user) | 403 `GLOSS_FORBIDDEN` |
| T6 | `POST` both clone_from_kind_id and clone_from_user_kind_id | 422 `GLOSS_INVALID_BODY` |
| T7 | `POST` duplicate code within same book | 409 `GLOSS_DUPLICATE_CODE` |
| T8 | Same code in different book — allowed | 201 |
| T9 | `GET /books/{id}/kinds/{kind_id}` | 200 with attributes |
| T10 | `GET` kind of different book | 404 |
| T11 | `PATCH` name, icon, color | 200, fields updated |
| T12 | `DELETE` — no entities | 204 |
| T13 | `DELETE` — live entities exist | 409 `GLOSS_KIND_HAS_ENTITIES` |
| T14 | Attr CRUD mirrors SS-4 tests T13–T18 | Same expectations |
| T15 | `GET /books/{id}/kinds-trash` after delete | 200, kind in list |
| T16 | Restore → kind back in list, gone from trash | 204 |
| T17 | Purge → permanently_deleted_at set | 204 |
| T18 | `v_attr_def` view selects from all 3 tiers | SELECT returns rows from T1, T2, T3 |

### Frontend

| # | Scenario | Expected |
|---|---|---|
| F1 | `BookGlossaryKindsPage` — load empty | "No book kinds" message |
| F2 | Click kind in list → detail shown | `getBookKind` called |
| F3 | Add attribute → `createBookKindAttr` called | New attr in detail list |
| F4 | Remove attr → confirm → `deleteBookKindAttr(false)` | Success |
| F5 | Remove attr → 409 data warning → confirm → `force=true` | `deleteBookKindAttr(true)` called |
| F6 | `CreateBookKindModal` — system mode → clone | `createBookKind` with `clone_from_kind_id` |
| F7 | `CreateBookKindModal` — user mode → clone | `createBookKind` with `clone_from_user_kind_id` |
| F8 | `RecycleBinPage` Book Kinds tab — fan-out | `listBookKindTrash` called per book |
| F9 | Restore from recycle bin | `restoreBookKind` called; item removed |

---

## 12) Exit Criteria

- [ ] `UpBookKinds()` runs; `book_kinds` + `book_kind_attributes` + `v_attr_def` view created.
- [ ] `v_attr_def` SELECT returns rows from all three tiers (T1/T2/T3).
- [ ] Book owner can create T3 kind from scratch, clone from T1, and clone from own T2 kind.
- [ ] Clone from another user's T2 kind returns 403.
- [ ] Providing both clone sources returns 422.
- [ ] Duplicate code within same book returns 409; same code in different book succeeds.
- [ ] Attribute soft-delete with data guard works (409 without force, 204 with force).
- [ ] Deleted book kind appears in `/books/{id}/kinds-trash`; restore and purge work.
- [ ] `BookGlossaryKindsPage` loads at `/books/:bookId/glossary/kinds`.
- [ ] `CreateBookKindModal` three-way mode selector works.
- [ ] "Kinds" link in `GlossaryPage` toolbar navigates correctly.
- [ ] "Glossary kinds" link in `BookDetailPage` navigates correctly.
- [ ] `RecycleBinPage` "Book Kinds" tab shows fan-out results.
- [ ] `go test ./...` passes.
- [ ] `npx tsc --noEmit` passes.
