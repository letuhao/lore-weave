# SS-4 — T2 User Kind CRUD: Detailed Design

## Document Metadata

- Document ID: LW-M05-93
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Tech Lead
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Parent Plan: [doc 89](89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md) — SS-4 row
- Summary: Full technical design for user-level (T2) glossary kind management. Covers `user_kinds` + `user_kind_attributes` tables, all 9 backend CRUD endpoints, recycle bin extension, `UserKindsPage`, `KindDetailPage`, `CreateKindModal`, and recycle bin UI additions. No entity creation with T2 kinds yet — that is wired in SS-7.

## Change History

| Version | Date       | Change         | Author    |
| ------- | ---------- | -------------- | --------- |
| 0.1.0   | 2026-03-25 | Initial design | Assistant |

---

## 1) Goal & Scope

**In scope:**
- `user_kinds` and `user_kind_attributes` DB tables with soft-delete
- Full CRUD API for T2 kinds and their attributes
- Clone from T1 (copy name/icon/color/genre_tags + all T1 attribute definitions)
- Soft delete with entity check guard (409 if entities exist)
- Attribute soft delete with force confirmation (409 with count if data exists)
- Recycle bin extension for kinds and attributes
- Frontend: `UserKindsPage` + `KindDetailPage` + modals in user settings
- Frontend: `RecycleBinPage` extended with "User Kinds" + "User Kind Attributes" tabs

**Out of scope (deferred to SS-7):**
- Wiring T2 kinds into the entity creation picker
- `v_attr_def` view (needs T3 too — will be defined in SS-5 when all tiers exist)
- `entity_attribute_values` polymorphic FK columns (SS-7)

---

## 2) DB Migration

**New function:** `migrate.UpUserKinds(ctx, pool)` in `services/glossary-service/internal/migrate/migrate.go`

### 2.1 DDL

```sql
-- user_kinds: T2 kinds owned by a user (cloned or created from scratch)
CREATE TABLE IF NOT EXISTS user_kinds (
  user_kind_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id       UUID        NOT NULL,
  code                TEXT        NOT NULL,
  name                TEXT        NOT NULL,
  description         TEXT,
  icon                TEXT        NOT NULL DEFAULT 'box',
  color               TEXT        NOT NULL DEFAULT '#6366f1',
  genre_tags          TEXT[]      NOT NULL DEFAULT '{}',
  is_active           BOOLEAN     NOT NULL DEFAULT true,
  cloned_from_kind_id UUID        REFERENCES entity_kinds(kind_id) ON DELETE SET NULL,
  deleted_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(owner_user_id, code)
);
CREATE INDEX IF NOT EXISTS idx_uk_owner
  ON user_kinds(owner_user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_uk_trash
  ON user_kinds(owner_user_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;

ALTER TABLE user_kinds
  ADD COLUMN IF NOT EXISTS permanently_deleted_at TIMESTAMPTZ;

-- user_kind_attributes: attribute definitions for T2 kinds
CREATE TABLE IF NOT EXISTS user_kind_attributes (
  attr_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_kind_id UUID        NOT NULL REFERENCES user_kinds(user_kind_id) ON DELETE CASCADE,
  code         TEXT        NOT NULL,
  name         TEXT        NOT NULL,
  description  TEXT,
  field_type   TEXT        NOT NULL DEFAULT 'text',
  is_required  BOOLEAN     NOT NULL DEFAULT false,
  sort_order   INT         NOT NULL DEFAULT 0,
  options      TEXT[],
  deleted_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_uka_kind
  ON user_kind_attributes(user_kind_id) WHERE deleted_at IS NULL;
```

**Schema notes:**
- `options TEXT[]` matches the existing T1 `attribute_definitions.options TEXT[]` so that the future `v_attr_def` UNION ALL view is type-compatible.
- `permanently_deleted_at` follows the same pattern as SS-2 glossary entities. The ALTER is separate from CREATE to be idempotent if run after the initial CREATE.
- `idx_uk_trash` enables efficient recycle bin queries without full-scan.

### 2.2 Migration function

```go
const userKindsSQL = `
CREATE TABLE IF NOT EXISTS user_kinds (
  user_kind_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id       UUID        NOT NULL,
  code                TEXT        NOT NULL,
  name                TEXT        NOT NULL,
  description         TEXT,
  icon                TEXT        NOT NULL DEFAULT 'box',
  color               TEXT        NOT NULL DEFAULT '#6366f1',
  genre_tags          TEXT[]      NOT NULL DEFAULT '{}',
  is_active           BOOLEAN     NOT NULL DEFAULT true,
  cloned_from_kind_id UUID        REFERENCES entity_kinds(kind_id) ON DELETE SET NULL,
  permanently_deleted_at TIMESTAMPTZ,
  deleted_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(owner_user_id, code)
);
CREATE INDEX IF NOT EXISTS idx_uk_owner
  ON user_kinds(owner_user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_uk_trash
  ON user_kinds(owner_user_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS user_kind_attributes (
  attr_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_kind_id UUID        NOT NULL REFERENCES user_kinds(user_kind_id) ON DELETE CASCADE,
  code         TEXT        NOT NULL,
  name         TEXT        NOT NULL,
  description  TEXT,
  field_type   TEXT        NOT NULL DEFAULT 'text',
  is_required  BOOLEAN     NOT NULL DEFAULT false,
  sort_order   INT         NOT NULL DEFAULT 0,
  options      TEXT[],
  deleted_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_uka_kind
  ON user_kind_attributes(user_kind_id) WHERE deleted_at IS NULL;
`

func UpUserKinds(ctx context.Context, pool *pgxpool.Pool) error {
    if _, err := pool.Exec(ctx, userKindsSQL); err != nil {
        return fmt.Errorf("migrate user_kinds: %w", err)
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
```

---

## 3) Backend — Response Types

**New file:** `services/glossary-service/internal/api/user_kind_handler.go`

### 3.1 Response structs

```go
package api

import "time"

// ── user_kinds response types ─────────────────────────────────────────────────

type userKindAttrResp struct {
    AttrID      string   `json:"attr_id"`
    UserKindID  string   `json:"user_kind_id"`
    Code        string   `json:"code"`
    Name        string   `json:"name"`
    Description *string  `json:"description,omitempty"`
    FieldType   string   `json:"field_type"`
    IsRequired  bool     `json:"is_required"`
    SortOrder   int      `json:"sort_order"`
    Options     []string `json:"options,omitempty"`
    CreatedAt   time.Time `json:"created_at"`
}

type userKindSummaryResp struct {
    UserKindID        string    `json:"user_kind_id"`
    OwnerUserID       string    `json:"owner_user_id"`
    Code              string    `json:"code"`
    Name              string    `json:"name"`
    Description       *string   `json:"description,omitempty"`
    Icon              string    `json:"icon"`
    Color             string    `json:"color"`
    GenreTags         []string  `json:"genre_tags"`
    IsActive          bool      `json:"is_active"`
    ClonedFromKindID  *string   `json:"cloned_from_kind_id,omitempty"`
    AttributeCount    int       `json:"attribute_count"`
    CreatedAt         time.Time `json:"created_at"`
    UpdatedAt         time.Time `json:"updated_at"`
}

type userKindDetailResp struct {
    userKindSummaryResp
    Attributes []userKindAttrResp `json:"attributes"`
}

type userKindListResp struct {
    Items  []userKindSummaryResp `json:"items"`
    Total  int                   `json:"total"`
    Limit  int                   `json:"limit"`
    Offset int                   `json:"offset"`
}

// ── trash types (extend SS-2 pattern) ────────────────────────────────────────

type userKindTrashItem struct {
    UserKindID string    `json:"user_kind_id"`
    Code       string    `json:"code"`
    Name       string    `json:"name"`
    Icon       string    `json:"icon"`
    Color      string    `json:"color"`
    DeletedAt  time.Time `json:"deleted_at"`
}
```

### 3.2 Helper: `verifyUserKindOwner`

```go
// verifyUserKindOwner checks that user_kind_id belongs to userID and is not
// permanently deleted. Returns the UUID of the kind on success.
func (s *Server) verifyUserKindOwner(
    w http.ResponseWriter, ctx context.Context,
    userKindID, userID uuid.UUID,
) bool {
    var exists bool
    if err := s.pool.QueryRow(ctx,
        `SELECT EXISTS(SELECT 1 FROM user_kinds
                       WHERE user_kind_id=$1 AND owner_user_id=$2
                         AND permanently_deleted_at IS NULL)`,
        userKindID, userID,
    ).Scan(&exists); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
        return false
    }
    if !exists {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not found")
        return false
    }
    return true
}
```

---

## 4) Backend — Kind CRUD Handlers

### 4.1 GET /v1/glossary/user-kinds

```go
func (s *Server) listUserKinds(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }

    q := r.URL.Query()
    limit  := parseIntDefault(q.Get("limit"),  20)
    offset := parseIntDefault(q.Get("offset"),  0)
    if limit > 100 { limit = 100 }

    // Optional filters
    filterActive  := q.Get("is_active")  // "true" | "false" | ""
    filterCloned  := q.Get("cloned_from") // "system" | "scratch" | ""
    sortBy        := q.Get("sort")       // "name" | "created_at" (default created_at DESC)

    where := []string{
        "owner_user_id = $1",
        "deleted_at IS NULL",
        "permanently_deleted_at IS NULL",
    }
    args := []any{userID}
    argN := 2

    if filterActive == "true" {
        where = append(where, fmt.Sprintf("is_active = $%d", argN))
        args = append(args, true); argN++
    } else if filterActive == "false" {
        where = append(where, fmt.Sprintf("is_active = $%d", argN))
        args = append(args, false); argN++
    }

    if filterCloned == "system" {
        where = append(where, "cloned_from_kind_id IS NOT NULL")
    } else if filterCloned == "scratch" {
        where = append(where, "cloned_from_kind_id IS NULL")
    }

    orderClause := "created_at DESC"
    if sortBy == "name" {
        orderClause = "name ASC"
    }

    ctx := r.Context()

    var total int
    countSQL := fmt.Sprintf(
        "SELECT COUNT(*) FROM user_kinds WHERE %s",
        strings.Join(where, " AND "))
    if err := s.pool.QueryRow(ctx, countSQL, args...).Scan(&total); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
        return
    }

    args = append(args, limit, offset)
    listSQL := fmt.Sprintf(`
        SELECT uk.user_kind_id, uk.owner_user_id, uk.code, uk.name, uk.description,
               uk.icon, uk.color, uk.genre_tags, uk.is_active,
               uk.cloned_from_kind_id, uk.created_at, uk.updated_at,
               COUNT(uka.attr_id) AS attribute_count
        FROM user_kinds uk
        LEFT JOIN user_kind_attributes uka
          ON uka.user_kind_id = uk.user_kind_id AND uka.deleted_at IS NULL
        WHERE %s
        GROUP BY uk.user_kind_id
        ORDER BY uk.%s
        LIMIT $%d OFFSET $%d`,
        strings.Join(where, " AND "), orderClause, argN, argN+1)

    rows, err := s.pool.Query(ctx, listSQL, args...)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
        return
    }
    defer rows.Close()

    items := []userKindSummaryResp{}
    for rows.Next() {
        var uk userKindSummaryResp
        if err := rows.Scan(
            &uk.UserKindID, &uk.OwnerUserID, &uk.Code, &uk.Name, &uk.Description,
            &uk.Icon, &uk.Color, &uk.GenreTags, &uk.IsActive,
            &uk.ClonedFromKindID, &uk.CreatedAt, &uk.UpdatedAt,
            &uk.AttributeCount,
        ); err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
            return
        }
        if uk.GenreTags == nil { uk.GenreTags = []string{} }
        items = append(items, uk)
    }
    if err := rows.Err(); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
        return
    }

    writeJSON(w, http.StatusOK, userKindListResp{
        Items: items, Total: total, Limit: limit, Offset: offset,
    })
}
```

### 4.2 POST /v1/glossary/user-kinds

Two modes: create from scratch OR clone from T1 kind.

```go
func (s *Server) createUserKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }

    var in struct {
        Code              string   `json:"code"`
        Name              string   `json:"name"`
        Description       *string  `json:"description"`
        Icon              string   `json:"icon"`
        Color             string   `json:"color"`
        GenreTags         []string `json:"genre_tags"`
        CloneFromKindID   *string  `json:"clone_from_kind_id"` // T1 kind_id to clone
    }
    if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
        return
    }

    // Validate required fields
    if strings.TrimSpace(in.Name) == "" {
        writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "name is required")
        return
    }
    if in.Icon == "" { in.Icon = "box" }
    if in.Color == "" { in.Color = "#6366f1" }
    if in.GenreTags == nil { in.GenreTags = []string{} }

    // If cloning, derive code + metadata from T1 kind if not provided
    var cloneFromKindID *uuid.UUID
    if in.CloneFromKindID != nil && *in.CloneFromKindID != "" {
        id, err := uuid.Parse(*in.CloneFromKindID)
        if err != nil {
            writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid clone_from_kind_id")
            return
        }
        cloneFromKindID = &id
    }

    // Generate code from name if not provided
    if strings.TrimSpace(in.Code) == "" {
        in.Code = slugify(in.Name) // see helper below
    }

    ctx := r.Context()

    tx, err := s.pool.Begin(ctx)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
        return
    }
    defer tx.Rollback(ctx)

    // Insert user_kind
    var ukID uuid.UUID
    err = tx.QueryRow(ctx, `
        INSERT INTO user_kinds
          (owner_user_id, code, name, description, icon, color, genre_tags, cloned_from_kind_id)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING user_kind_id`,
        userID, in.Code, in.Name, in.Description,
        in.Icon, in.Color, in.GenreTags, cloneFromKindID,
    ).Scan(&ukID)
    if err != nil {
        // unique constraint violation: (owner_user_id, code) already exists
        if isUniqueViolation(err) {
            writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE",
                "a user kind with this code already exists")
            return
        }
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
        return
    }

    // If cloning: copy T1 attribute definitions into user_kind_attributes
    if cloneFromKindID != nil {
        _, err = tx.Exec(ctx, `
            INSERT INTO user_kind_attributes
              (user_kind_id, code, name, description, field_type, is_required, sort_order, options)
            SELECT $1, code, name, description, field_type, is_required, sort_order, options
            FROM attribute_definitions
            WHERE kind_id = $2
            ORDER BY sort_order`,
            ukID, cloneFromKindID,
        )
        if err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clone attrs failed")
            return
        }
    }

    if err := tx.Commit(ctx); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
        return
    }

    detail, err := s.loadUserKindDetail(ctx, ukID, userID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
        return
    }
    writeJSON(w, http.StatusCreated, detail)
}

// slugify converts a display name to a lowercase underscore code.
// "My Character" → "my_character"
func slugify(name string) string {
    s := strings.ToLower(strings.TrimSpace(name))
    s = strings.Map(func(r rune) rune {
        if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
            return r
        }
        return '_'
    }, s)
    // collapse multiple underscores
    for strings.Contains(s, "__") {
        s = strings.ReplaceAll(s, "__", "_")
    }
    return strings.Trim(s, "_")
}

// isUniqueViolation returns true for pgconn error code 23505.
func isUniqueViolation(err error) bool {
    var pgErr *pgconn.PgError
    return errors.As(err, &pgErr) && pgErr.Code == "23505"
}
```

### 4.3 GET /v1/glossary/user-kinds/{user_kind_id}

```go
func (s *Server) getUserKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }

    detail, err := s.loadUserKindDetail(r.Context(), userKindID, userID)
    if err == pgx.ErrNoRows {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not found")
        return
    }
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
        return
    }
    writeJSON(w, http.StatusOK, detail)
}

// loadUserKindDetail fetches kind metadata + all non-deleted attributes.
// Returns pgx.ErrNoRows if kind not found or not owned by userID.
func (s *Server) loadUserKindDetail(ctx context.Context, userKindID, userID uuid.UUID) (*userKindDetailResp, error) {
    var d userKindDetailResp
    err := s.pool.QueryRow(ctx, `
        SELECT uk.user_kind_id, uk.owner_user_id, uk.code, uk.name, uk.description,
               uk.icon, uk.color, uk.genre_tags, uk.is_active,
               uk.cloned_from_kind_id, uk.created_at, uk.updated_at,
               COUNT(uka.attr_id) AS attribute_count
        FROM user_kinds uk
        LEFT JOIN user_kind_attributes uka
          ON uka.user_kind_id = uk.user_kind_id AND uka.deleted_at IS NULL
        WHERE uk.user_kind_id = $1
          AND uk.owner_user_id = $2
          AND uk.permanently_deleted_at IS NULL
        GROUP BY uk.user_kind_id`,
        userKindID, userID,
    ).Scan(
        &d.UserKindID, &d.OwnerUserID, &d.Code, &d.Name, &d.Description,
        &d.Icon, &d.Color, &d.GenreTags, &d.IsActive,
        &d.ClonedFromKindID, &d.CreatedAt, &d.UpdatedAt,
        &d.AttributeCount,
    )
    if err != nil {
        return nil, err
    }
    if d.GenreTags == nil { d.GenreTags = []string{} }

    // Load attributes
    rows, err := s.pool.Query(ctx, `
        SELECT attr_id, user_kind_id, code, name, description,
               field_type, is_required, sort_order, options, created_at
        FROM user_kind_attributes
        WHERE user_kind_id = $1 AND deleted_at IS NULL
        ORDER BY sort_order ASC, created_at ASC`,
        userKindID)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    d.Attributes = []userKindAttrResp{}
    for rows.Next() {
        var a userKindAttrResp
        if err := rows.Scan(
            &a.AttrID, &a.UserKindID, &a.Code, &a.Name, &a.Description,
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

### 4.4 PATCH /v1/glossary/user-kinds/{user_kind_id}

Partial update — only provided fields are changed. `code` is immutable after creation.

```go
func (s *Server) patchUserKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }
    if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) { return }

    var in map[string]json.RawMessage
    if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
        return
    }

    setClauses := []string{}
    args := []any{}
    argN := 1

    // Permitted fields: name, description, icon, color, genre_tags, is_active
    if raw, ok := in["name"]; ok {
        var v string
        if err := json.Unmarshal(raw, &v); err != nil || strings.TrimSpace(v) == "" {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid name")
            return
        }
        setClauses = append(setClauses, fmt.Sprintf("name = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["description"]; ok {
        var v *string
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid description")
            return
        }
        setClauses = append(setClauses, fmt.Sprintf("description = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["icon"]; ok {
        var v string
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid icon")
            return
        }
        setClauses = append(setClauses, fmt.Sprintf("icon = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["color"]; ok {
        var v string
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid color")
            return
        }
        setClauses = append(setClauses, fmt.Sprintf("color = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["genre_tags"]; ok {
        var v []string
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid genre_tags")
            return
        }
        if v == nil { v = []string{} }
        setClauses = append(setClauses, fmt.Sprintf("genre_tags = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["is_active"]; ok {
        var v bool
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid is_active")
            return
        }
        setClauses = append(setClauses, fmt.Sprintf("is_active = $%d", argN))
        args = append(args, v); argN++
    }

    if len(setClauses) == 0 {
        // Nothing to update — return current state
        detail, err := s.loadUserKindDetail(r.Context(), userKindID, userID)
        if err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
            return
        }
        writeJSON(w, http.StatusOK, detail)
        return
    }

    setClauses = append(setClauses, "updated_at = now()")
    args = append(args, userKindID, userID)
    updateSQL := fmt.Sprintf(
        "UPDATE user_kinds SET %s WHERE user_kind_id = $%d AND owner_user_id = $%d",
        strings.Join(setClauses, ", "), argN, argN+1)

    if _, err := s.pool.Exec(r.Context(), updateSQL, args...); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
        return
    }

    detail, err := s.loadUserKindDetail(r.Context(), userKindID, userID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
        return
    }
    writeJSON(w, http.StatusOK, detail)
}
```

### 4.5 DELETE /v1/glossary/user-kinds/{user_kind_id}

Soft delete. Rejects with 409 if live (non-deleted, non-purged) entities still use this kind.

```go
func (s *Server) deleteUserKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }
    if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) { return }

    ctx := r.Context()

    // Guard: reject if live entities exist using this kind
    var entityCount int
    if err := s.pool.QueryRow(ctx, `
        SELECT COUNT(*) FROM glossary_entities
        WHERE user_kind_id = $1
          AND deleted_at IS NULL
          AND permanently_deleted_at IS NULL`,
        userKindID,
    ).Scan(&entityCount); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
        return
    }
    if entityCount > 0 {
        writeError(w, http.StatusConflict, "GLOSS_KIND_HAS_ENTITIES",
            fmt.Sprintf("%d entities use this kind; move them to another kind or delete them first", entityCount))
        return
    }

    tag, err := s.pool.Exec(ctx, `
        UPDATE user_kinds
        SET deleted_at = now(), updated_at = now()
        WHERE user_kind_id = $1 AND owner_user_id = $2
          AND deleted_at IS NULL`,
        userKindID, userID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
        return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not found or already deleted")
        return
    }
    w.WriteHeader(http.StatusNoContent)
}
```

**Note:** The guard queries `glossary_entities.user_kind_id`. This column does not exist until SS-7 migration. Until SS-7, the query will return 0 (no rows) because the column doesn't exist — which would cause a runtime SQL error. **Mitigation:** The guard uses a safe fallback:

```go
// Safe query that degrades gracefully before SS-7 adds user_kind_id column.
// Use column existence check or simply skip the guard if column is missing.
// Option A (simplest): Check if column exists before querying.
// Option B: Catch error and treat as "no entities".
// Chosen: Option B — catch specific column-does-not-exist error (code 42703).
var pgErr *pgconn.PgError
if errors.As(err, &pgErr) && pgErr.Code == "42703" {
    entityCount = 0 // column not yet added — safe to proceed
}
```

This is the only handler that touches the future `user_kind_id` column before SS-7. The guard is added now for correctness; it becomes fully functional after SS-7.

---

## 5) Backend — Attribute CRUD Handlers

**File:** `services/glossary-service/internal/api/user_kind_handler.go` (continued)

### 5.1 POST /v1/glossary/user-kinds/{user_kind_id}/attributes

```go
func (s *Server) createUserKindAttr(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }
    if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) { return }

    var in struct {
        Code        string   `json:"code"`
        Name        string   `json:"name"`
        Description *string  `json:"description"`
        FieldType   string   `json:"field_type"`
        IsRequired  bool     `json:"is_required"`
        SortOrder   int      `json:"sort_order"`
        Options     []string `json:"options"`
    }
    if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
        return
    }
    if strings.TrimSpace(in.Name) == "" {
        writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "name is required")
        return
    }
    if in.Code == "" { in.Code = slugify(in.Name) }
    if in.FieldType == "" { in.FieldType = "text" }

    validFieldTypes := map[string]bool{
        "text": true, "textarea": true, "select": true,
        "number": true, "date": true, "tags": true, "url": true, "boolean": true,
    }
    if !validFieldTypes[in.FieldType] {
        writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
            "field_type must be text, textarea, select, number, date, tags, url, or boolean")
        return
    }

    var a userKindAttrResp
    err := s.pool.QueryRow(r.Context(), `
        INSERT INTO user_kind_attributes
          (user_kind_id, code, name, description, field_type, is_required, sort_order, options)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING attr_id, user_kind_id, code, name, description,
                  field_type, is_required, sort_order, options, created_at`,
        userKindID, in.Code, in.Name, in.Description,
        in.FieldType, in.IsRequired, in.SortOrder, in.Options,
    ).Scan(
        &a.AttrID, &a.UserKindID, &a.Code, &a.Name, &a.Description,
        &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.CreatedAt,
    )
    if err != nil {
        if isUniqueViolation(err) {
            writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE",
                "an attribute with this code already exists for this kind")
            return
        }
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
        return
    }
    if a.Options == nil { a.Options = []string{} }

    // Bump kind updated_at
    _, _ = s.pool.Exec(r.Context(),
        `UPDATE user_kinds SET updated_at = now() WHERE user_kind_id = $1`, userKindID)

    writeJSON(w, http.StatusCreated, a)
}
```

### 5.2 PATCH /v1/glossary/user-kinds/{user_kind_id}/attributes/{attr_id}

```go
func (s *Server) patchUserKindAttr(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }
    attrID, ok := parsePathUUID(w, r, "attr_id")
    if !ok { return }
    if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) { return }

    var in map[string]json.RawMessage
    if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
        return
    }

    setClauses := []string{}
    args := []any{}
    argN := 1

    if raw, ok := in["name"]; ok {
        var v string
        if err := json.Unmarshal(raw, &v); err != nil || strings.TrimSpace(v) == "" {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid name"); return
        }
        setClauses = append(setClauses, fmt.Sprintf("name = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["description"]; ok {
        var v *string
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid description"); return
        }
        setClauses = append(setClauses, fmt.Sprintf("description = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["field_type"]; ok {
        var v string
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid field_type"); return
        }
        setClauses = append(setClauses, fmt.Sprintf("field_type = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["is_required"]; ok {
        var v bool
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid is_required"); return
        }
        setClauses = append(setClauses, fmt.Sprintf("is_required = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["sort_order"]; ok {
        var v int
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid sort_order"); return
        }
        setClauses = append(setClauses, fmt.Sprintf("sort_order = $%d", argN))
        args = append(args, v); argN++
    }
    if raw, ok := in["options"]; ok {
        var v []string
        if err := json.Unmarshal(raw, &v); err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid options"); return
        }
        setClauses = append(setClauses, fmt.Sprintf("options = $%d", argN))
        args = append(args, v); argN++
    }

    if len(setClauses) == 0 {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "no fields to update")
        return
    }

    args = append(args, attrID, userKindID)
    updateSQL := fmt.Sprintf(
        "UPDATE user_kind_attributes SET %s WHERE attr_id = $%d AND user_kind_id = $%d AND deleted_at IS NULL",
        strings.Join(setClauses, ", "), argN, argN+1)

    tag, err := s.pool.Exec(r.Context(), updateSQL, args...)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
        return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
        return
    }

    // Bump kind updated_at
    _, _ = s.pool.Exec(r.Context(),
        `UPDATE user_kinds SET updated_at = now() WHERE user_kind_id = $1`, userKindID)

    // Return updated attribute
    var a userKindAttrResp
    if err := s.pool.QueryRow(r.Context(), `
        SELECT attr_id, user_kind_id, code, name, description,
               field_type, is_required, sort_order, options, created_at
        FROM user_kind_attributes
        WHERE attr_id = $1`, attrID,
    ).Scan(
        &a.AttrID, &a.UserKindID, &a.Code, &a.Name, &a.Description,
        &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.CreatedAt,
    ); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reload failed")
        return
    }
    if a.Options == nil { a.Options = []string{} }
    writeJSON(w, http.StatusOK, a)
}
```

### 5.3 DELETE /v1/glossary/user-kinds/{user_kind_id}/attributes/{attr_id}

Soft delete with data guard. If any `entity_attribute_values` row has a non-empty `original_value` for this attr, return 409 with count. Client re-sends with `?force=true` to bypass.

```go
func (s *Server) deleteUserKindAttr(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }
    attrID, ok := parsePathUUID(w, r, "attr_id")
    if !ok { return }
    if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) { return }

    force := r.URL.Query().Get("force") == "true"
    ctx := r.Context()

    // Check if any entity_attribute_values have data for this attr
    // Note: uses user_attr_def_id column added in SS-7. Before SS-7 this returns 0 (safe).
    var dataCount int
    err := s.pool.QueryRow(ctx, `
        SELECT COUNT(*) FROM entity_attribute_values
        WHERE user_attr_def_id = $1
          AND original_value != ''`,
        attrID,
    ).Scan(&dataCount)
    if err != nil {
        // If column doesn't exist yet (before SS-7), treat as 0
        var pgErr *pgconn.PgError
        if errors.As(err, &pgErr) && pgErr.Code == "42703" {
            dataCount = 0
        } else {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
            return
        }
    }

    if dataCount > 0 && !force {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusConflict)
        _ = json.NewEncoder(w).Encode(map[string]any{
            "code":        "GLOSS_ATTR_HAS_DATA",
            "message":     fmt.Sprintf("%d entities have data for this attribute", dataCount),
            "entity_count": dataCount,
        })
        return
    }

    tag, err := s.pool.Exec(ctx, `
        UPDATE user_kind_attributes
        SET deleted_at = now()
        WHERE attr_id = $1 AND user_kind_id = $2 AND deleted_at IS NULL`,
        attrID, userKindID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
        return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
        return
    }

    // Bump kind updated_at
    _, _ = s.pool.Exec(ctx,
        `UPDATE user_kinds SET updated_at = now() WHERE user_kind_id = $1`, userKindID)

    w.WriteHeader(http.StatusNoContent)
}
```

---

## 6) Backend — Recycle Bin Extension (User Kinds)

### 6.1 List user-kind trash

Add handler `listUserKindTrash` in `user_kind_handler.go`:

```go
func (s *Server) listUserKindTrash(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }

    q := r.URL.Query()
    limit  := parseIntDefault(q.Get("limit"),  20)
    offset := parseIntDefault(q.Get("offset"),  0)
    if limit > 100 { limit = 100 }

    ctx := r.Context()

    var total int
    if err := s.pool.QueryRow(ctx, `
        SELECT COUNT(*) FROM user_kinds
        WHERE owner_user_id=$1
          AND deleted_at IS NOT NULL
          AND permanently_deleted_at IS NULL`,
        userID).Scan(&total); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
        return
    }

    rows, err := s.pool.Query(ctx, `
        SELECT user_kind_id::text, code, name, icon, color, deleted_at
        FROM user_kinds
        WHERE owner_user_id=$1
          AND deleted_at IS NOT NULL
          AND permanently_deleted_at IS NULL
        ORDER BY deleted_at DESC
        LIMIT $2 OFFSET $3`,
        userID, limit, offset)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
        return
    }
    defer rows.Close()

    items := []userKindTrashItem{}
    for rows.Next() {
        var it userKindTrashItem
        if err := rows.Scan(&it.UserKindID, &it.Code, &it.Name, &it.Icon, &it.Color, &it.DeletedAt); err != nil {
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

### 6.2 Restore user kind

```go
func (s *Server) restoreUserKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }

    tag, err := s.pool.Exec(r.Context(), `
        UPDATE user_kinds
        SET deleted_at = NULL, updated_at = now()
        WHERE user_kind_id = $1 AND owner_user_id = $2
          AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
        userKindID, userID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed")
        return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not in trash")
        return
    }
    w.WriteHeader(http.StatusNoContent)
}
```

### 6.3 Purge user kind

```go
func (s *Server) purgeUserKind(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }
    userKindID, ok := parsePathUUID(w, r, "user_kind_id")
    if !ok { return }

    tag, err := s.pool.Exec(r.Context(), `
        UPDATE user_kinds
        SET permanently_deleted_at = now()
        WHERE user_kind_id = $1 AND owner_user_id = $2
          AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
        userKindID, userID)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "purge failed")
        return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not in trash")
        return
    }
    w.WriteHeader(http.StatusNoContent)
}
```

---

## 7) Route Registration

**File:** `services/glossary-service/internal/api/server.go`

Add inside the `r.Route("/v1/glossary", ...)` block, after the preferences routes:

```go
// ── T2 User Kind CRUD (SS-4) ─────────────────────────────────────────────────
r.Route("/user-kinds", func(r chi.Router) {
    r.Get("/", s.listUserKinds)
    r.Post("/", s.createUserKind)

    r.Route("/{user_kind_id}", func(r chi.Router) {
        r.Get("/", s.getUserKind)
        r.Patch("/", s.patchUserKind)
        r.Delete("/", s.deleteUserKind)

        r.Route("/attributes", func(r chi.Router) {
            r.Post("/", s.createUserKindAttr)
            r.Route("/{attr_id}", func(r chi.Router) {
                r.Patch("/", s.patchUserKindAttr)
                r.Delete("/", s.deleteUserKindAttr)
            })
        })
    })
})

// ── User Kind Recycle Bin (SS-4) ─────────────────────────────────────────────
r.Route("/user-kinds-trash", func(r chi.Router) {
    r.Get("/", s.listUserKindTrash)
    r.Post("/{user_kind_id}/restore", s.restoreUserKind)
    r.Delete("/{user_kind_id}", s.purgeUserKind)
})
```

---

## 8) Frontend — Types and API Client

### 8.1 New types in `frontend/src/features/glossary/types.ts`

```typescript
// ── T2 User Kinds ─────────────────────────────────────────────────────────────

export type UserKindAttr = {
  attr_id: string;
  user_kind_id: string;
  code: string;
  name: string;
  description?: string;
  field_type: FieldType;
  is_required: boolean;
  sort_order: number;
  options?: string[];
  created_at: string;
};

export type UserKind = {
  user_kind_id: string;
  owner_user_id: string;
  code: string;
  name: string;
  description?: string;
  icon: string;
  color: string;
  genre_tags: string[];
  is_active: boolean;
  cloned_from_kind_id?: string | null;
  attribute_count: number;
  created_at: string;
  updated_at: string;
  // Only present in detail (GET /user-kinds/{id}) response:
  attributes?: UserKindAttr[];
};

export type UserKindListResponse = {
  items: UserKind[];
  total: number;
  limit: number;
  offset: number;
};

export type UserKindTrashItem = {
  user_kind_id: string;
  code: string;
  name: string;
  icon: string;
  color: string;
  deleted_at: string;
};
```

### 8.2 API client additions in `frontend/src/features/glossary/api.ts`

```typescript
// ── T2 User Kinds (SS-4) ─────────────────────────────────────────────────────

listUserKinds(
  token: string,
  params: {
    is_active?: boolean;
    cloned_from?: 'system' | 'scratch';
    sort?: 'name' | 'created_at';
    limit?: number;
    offset?: number;
  } = {},
): Promise<UserKindListResponse> {
  const qs = new URLSearchParams();
  if (params.is_active !== undefined) qs.set('is_active', String(params.is_active));
  if (params.cloned_from)            qs.set('cloned_from', params.cloned_from);
  if (params.sort)                   qs.set('sort', params.sort);
  if (params.limit)                  qs.set('limit', String(params.limit));
  if (params.offset)                 qs.set('offset', String(params.offset));
  const q = qs.toString();
  return apiJson<UserKindListResponse>(`${BASE}/user-kinds${q ? '?' + q : ''}`, { token });
},

createUserKind(
  token: string,
  body: {
    name: string;
    code?: string;
    description?: string;
    icon?: string;
    color?: string;
    genre_tags?: string[];
    clone_from_kind_id?: string;
  },
): Promise<UserKind> {
  return apiJson<UserKind>(`${BASE}/user-kinds`, {
    method: 'POST',
    body: JSON.stringify(body),
    token,
  });
},

getUserKind(token: string, userKindId: string): Promise<UserKind> {
  return apiJson<UserKind>(`${BASE}/user-kinds/${userKindId}`, { token });
},

patchUserKind(
  token: string,
  userKindId: string,
  changes: Partial<Pick<UserKind, 'name' | 'description' | 'icon' | 'color' | 'genre_tags' | 'is_active'>>,
): Promise<UserKind> {
  return apiJson<UserKind>(`${BASE}/user-kinds/${userKindId}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
    token,
  });
},

deleteUserKind(token: string, userKindId: string): Promise<void> {
  return apiJson<void>(`${BASE}/user-kinds/${userKindId}`, {
    method: 'DELETE',
    token,
  });
},

createUserKindAttr(
  token: string,
  userKindId: string,
  body: {
    name: string;
    code?: string;
    description?: string;
    field_type?: string;
    is_required?: boolean;
    sort_order?: number;
    options?: string[];
  },
): Promise<UserKindAttr> {
  return apiJson<UserKindAttr>(`${BASE}/user-kinds/${userKindId}/attributes`, {
    method: 'POST',
    body: JSON.stringify(body),
    token,
  });
},

patchUserKindAttr(
  token: string,
  userKindId: string,
  attrId: string,
  changes: Partial<Pick<UserKindAttr, 'name' | 'description' | 'field_type' | 'is_required' | 'sort_order' | 'options'>>,
): Promise<UserKindAttr> {
  return apiJson<UserKindAttr>(`${BASE}/user-kinds/${userKindId}/attributes/${attrId}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
    token,
  });
},

deleteUserKindAttr(
  token: string,
  userKindId: string,
  attrId: string,
  force = false,
): Promise<void> {
  const qs = force ? '?force=true' : '';
  return apiJson<void>(`${BASE}/user-kinds/${userKindId}/attributes/${attrId}${qs}`, {
    method: 'DELETE',
    token,
  });
},

// ── User Kind Recycle Bin (SS-4) ─────────────────────────────────────────────

listUserKindTrash(
  token: string,
  params: { limit?: number; offset?: number } = {},
): Promise<{ items: UserKindTrashItem[]; total: number; limit: number; offset: number }> {
  const qs = new URLSearchParams();
  if (params.limit)  qs.set('limit',  String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  const q = qs.toString();
  return apiJson(`${BASE}/user-kinds-trash${q ? '?' + q : ''}`, { token });
},

restoreUserKind(token: string, userKindId: string): Promise<void> {
  return apiJson<void>(`${BASE}/user-kinds-trash/${userKindId}/restore`, {
    method: 'POST',
    token,
  });
},

purgeUserKind(token: string, userKindId: string): Promise<void> {
  return apiJson<void>(`${BASE}/user-kinds-trash/${userKindId}`, {
    method: 'DELETE',
    token,
  });
},
```

---

## 9) Frontend — Pages and Components

### 9.1 UserKindsPage.tsx

**Route:** `/settings/glossary/kinds` (new route — see section 9.5)

**File:** `frontend/src/pages/UserKindsPage.tsx`

```tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { glossaryApi } from '@/features/glossary/api';
import type { UserKind } from '@/features/glossary/types';
import { CreateKindModal } from '@/components/glossary/CreateKindModal';

export function UserKindsPage() {
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [kinds, setKinds] = useState<UserKind[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [filterActive, setFilterActive] = useState<'all' | 'active' | 'inactive'>('all');

  const LIMIT = 20;
  const [offset, setOffset] = useState(0);

  async function load(newOffset = offset) {
    setLoading(true);
    setError('');
    try {
      const params: Parameters<typeof glossaryApi.listUserKinds>[1] = {
        limit: LIMIT,
        offset: newOffset,
      };
      if (filterActive === 'active')   params.is_active = true;
      if (filterActive === 'inactive') params.is_active = false;

      const resp = await glossaryApi.listUserKinds(token, params);
      setKinds(resp.items);
      setTotal(resp.total);
      setOffset(newOffset);
    } catch (e: unknown) {
      setError((e as Error).message || 'Failed to load kinds');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(0); }, [filterActive]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleDelete(kind: UserKind) {
    if (!confirm(`Move "${kind.name}" to trash?`)) return;
    try {
      await glossaryApi.deleteUserKind(token, kind.user_kind_id);
      load();
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message || '';
      if (msg.includes('GLOSS_KIND_HAS_ENTITIES')) {
        alert(msg);
      } else {
        alert('Delete failed: ' + msg);
      }
    }
  }

  async function handleToggleActive(kind: UserKind) {
    try {
      await glossaryApi.patchUserKind(token, kind.user_kind_id, { is_active: !kind.is_active });
      load();
    } catch (e: unknown) {
      alert('Update failed: ' + (e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">My glossary kinds</h2>
          <p className="text-sm text-muted-foreground">
            Custom entity categories for your glossary. Clone from system kinds or build from scratch.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>+ New kind</Button>
      </div>

      {/* Filter bar */}
      <div className="flex gap-2">
        {(['all', 'active', 'inactive'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilterActive(f)}
            className={`rounded px-3 py-1 text-sm capitalize ${
              filterActive === f
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/70'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Kind list */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : kinds.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No kinds yet.{' '}
          <button className="underline" onClick={() => setShowCreate(true)}>
            Create one
          </button>{' '}
          or clone from a system kind.
        </p>
      ) : (
        <div className="space-y-2">
          {kinds.map((kind) => (
            <div
              key={kind.user_kind_id}
              className="flex items-center gap-3 rounded border p-3"
            >
              {/* Color swatch + icon */}
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-sm"
                style={{ backgroundColor: kind.color + '22', color: kind.color }}
              >
                {kind.icon}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{kind.name}</span>
                  <span className="text-xs text-muted-foreground">({kind.code})</span>
                  {!kind.is_active && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                      inactive
                    </span>
                  )}
                  {kind.cloned_from_kind_id && (
                    <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                      cloned
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {kind.attribute_count} attribute{kind.attribute_count !== 1 ? 's' : ''}
                  {kind.description ? ` · ${kind.description}` : ''}
                </p>
              </div>

              <div className="flex shrink-0 gap-1">
                <Link
                  to={`/settings/glossary/kinds/${kind.user_kind_id}`}
                  className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                >
                  Edit
                </Link>
                <button
                  onClick={() => handleToggleActive(kind)}
                  className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                >
                  {kind.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <button
                  onClick={() => handleDelete(kind)}
                  className="rounded px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > LIMIT && (
        <div className="flex gap-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => load(Math.max(0, offset - LIMIT))}
          >
            Previous
          </Button>
          <span className="self-center text-muted-foreground">
            {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={offset + LIMIT >= total}
            onClick={() => load(offset + LIMIT)}
          >
            Next
          </Button>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <CreateKindModal
          token={token}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(0); }}
        />
      )}
    </div>
  );
}
```

### 9.2 CreateKindModal.tsx

**File:** `frontend/src/components/glossary/CreateKindModal.tsx`

Two modes: "From scratch" and "Clone from system kind". Modal follows the existing pattern in the codebase (fixed overlay + dialog box).

```tsx
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { glossaryApi } from '@/features/glossary/api';
import type { EntityKind } from '@/features/glossary/types';

type Mode = 'scratch' | 'clone';

type Props = {
  token: string;
  onClose: () => void;
  onCreated: () => void;
};

export function CreateKindModal({ token, onClose, onCreated }: Props) {
  const [mode, setMode] = useState<Mode>('scratch');

  // Scratch form
  const [name, setName]       = useState('');
  const [icon, setIcon]       = useState('📦');
  const [color, setColor]     = useState('#6366f1');
  const [description, setDesc] = useState('');

  // Clone form
  const [systemKinds, setSystemKinds] = useState<EntityKind[]>([]);
  const [selectedKindId, setSelectedKindId] = useState('');
  const [kindSearch, setKindSearch] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Load system kinds for clone mode
  useEffect(() => {
    if (mode === 'clone' && systemKinds.length === 0) {
      glossaryApi.getKinds(token).then(setSystemKinds).catch(() => {});
    }
  }, [mode, token, systemKinds.length]);

  const filteredKinds = systemKinds.filter((k) =>
    k.name.toLowerCase().includes(kindSearch.toLowerCase()) ||
    k.code.toLowerCase().includes(kindSearch.toLowerCase()),
  );

  async function handleSubmit() {
    setError('');
    if (mode === 'scratch' && !name.trim()) {
      setError('Name is required'); return;
    }
    if (mode === 'clone' && !selectedKindId) {
      setError('Select a system kind to clone'); return;
    }

    setSubmitting(true);
    try {
      if (mode === 'scratch') {
        await glossaryApi.createUserKind(token, {
          name: name.trim(),
          icon,
          color,
          description: description.trim() || undefined,
        });
      } else {
        const sourceKind = systemKinds.find((k) => k.kind_id === selectedKindId)!;
        await glossaryApi.createUserKind(token, {
          name: sourceKind.name,
          icon: sourceKind.icon,
          color: sourceKind.color,
          clone_from_kind_id: selectedKindId,
        });
      }
      onCreated();
    } catch (e: unknown) {
      setError((e as Error).message || 'Create failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Create kind</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>

        {/* Mode selector */}
        <div className="mb-4 flex gap-1 rounded border p-1">
          {(['scratch', 'clone'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`flex-1 rounded py-1 text-sm font-medium transition-colors ${
                mode === m
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {m === 'scratch' ? 'From scratch' : 'Clone from system'}
            </button>
          ))}
        </div>

        {mode === 'scratch' && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Name *</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Magic System"
                className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-sm font-medium">Icon</label>
                <input
                  value={icon}
                  onChange={(e) => setIcon(e.target.value)}
                  placeholder="📦"
                  className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Color</label>
                <input
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="h-9 w-16 cursor-pointer rounded border"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Description (optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDesc(e.target.value)}
                rows={2}
                className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          </div>
        )}

        {mode === 'clone' && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Search system kinds</label>
              <input
                value={kindSearch}
                onChange={(e) => setKindSearch(e.target.value)}
                placeholder="character, location, …"
                className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <div className="max-h-48 overflow-y-auto rounded border">
              {filteredKinds.length === 0 && (
                <p className="p-3 text-sm text-muted-foreground">No matches</p>
              )}
              {filteredKinds.map((k) => (
                <button
                  key={k.kind_id}
                  onClick={() => setSelectedKindId(k.kind_id)}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted ${
                    selectedKindId === k.kind_id ? 'bg-muted font-medium' : ''
                  }`}
                >
                  <span style={{ color: k.color }}>{k.icon}</span>
                  <span>{k.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {k.default_attributes.length} attrs
                  </span>
                </button>
              ))}
            </div>
            {selectedKindId && (
              <p className="text-xs text-muted-foreground">
                Will copy all {systemKinds.find((k) => k.kind_id === selectedKindId)?.default_attributes.length ?? 0} attribute definitions.
                You can customize them after creating.
              </p>
            )}
          </div>
        )}

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Creating…' : 'Create'}
          </Button>
        </div>
      </div>
    </>
  );
}
```

### 9.3 KindDetailPage.tsx

**Route:** `/settings/glossary/kinds/:userKindId`

**File:** `frontend/src/pages/KindDetailPage.tsx`

```tsx
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { glossaryApi } from '@/features/glossary/api';
import type { UserKind, UserKindAttr } from '@/features/glossary/types';
import { AttributeDeleteConfirmModal } from '@/components/glossary/AttributeDeleteConfirmModal';

const FIELD_TYPES = [
  'text', 'textarea', 'select', 'number', 'date', 'tags', 'url', 'boolean',
] as const;

export function KindDetailPage() {
  const { userKindId } = useParams<{ userKindId: string }>();
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [kind, setKind] = useState<UserKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Metadata edit form
  const [form, setForm] = useState({ name: '', icon: '', color: '', description: '' });
  const [formDirty, setFormDirty] = useState(false);

  // New attribute form
  const [newAttr, setNewAttr] = useState({
    name: '', field_type: 'text', is_required: false, sort_order: 0,
  });
  const [addingAttr, setAddingAttr] = useState(false);
  const [attrError, setAttrError] = useState('');

  // Delete confirmation modal state
  const [deleteTarget, setDeleteTarget] = useState<{ attr: UserKindAttr; count: number } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const k = await glossaryApi.getUserKind(token, userKindId!);
      setKind(k);
      setForm({
        name: k.name, icon: k.icon, color: k.color,
        description: k.description ?? '',
      });
      setFormDirty(false);
    } catch {
      setError('Failed to load kind');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSaveMeta() {
    setSaving(true);
    setError('');
    setSuccessMsg('');
    try {
      await glossaryApi.patchUserKind(token, userKindId!, {
        name: form.name,
        icon: form.icon,
        color: form.color,
        description: form.description || undefined,
      });
      setSuccessMsg('Saved');
      setFormDirty(false);
      load();
    } catch (e: unknown) {
      setError((e as Error).message || 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  async function handleAddAttr() {
    if (!newAttr.name.trim()) { setAttrError('Name is required'); return; }
    setAddingAttr(true);
    setAttrError('');
    try {
      await glossaryApi.createUserKindAttr(token, userKindId!, {
        name: newAttr.name.trim(),
        field_type: newAttr.field_type,
        is_required: newAttr.is_required,
        sort_order: newAttr.sort_order,
      });
      setNewAttr({ name: '', field_type: 'text', is_required: false, sort_order: 0 });
      load();
    } catch (e: unknown) {
      setAttrError((e as Error).message || 'Add failed');
    } finally {
      setAddingAttr(false);
    }
  }

  async function handleDeleteAttr(attr: UserKindAttr, force = false) {
    try {
      await glossaryApi.deleteUserKindAttr(token, userKindId!, attr.attr_id, force);
      setDeleteTarget(null);
      load();
    } catch (e: unknown) {
      const msg = (e as Error).message || '';
      // Backend returns 409 with entity_count in body for data guard
      try {
        const body = JSON.parse(msg);
        if (body.code === 'GLOSS_ATTR_HAS_DATA') {
          setDeleteTarget({ attr, count: body.entity_count });
          return;
        }
      } catch { /* not a JSON error */ }
      alert('Delete failed: ' + msg);
    }
  }

  if (loading) return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );

  if (!kind) return <p className="text-sm text-destructive">{error || 'Kind not found'}</p>;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/settings/glossary" className="hover:underline">Settings</Link>
        <span>›</span>
        <Link to="/settings/glossary/kinds" className="hover:underline">Kinds</Link>
        <span>›</span>
        <span className="text-foreground">{kind.name}</span>
      </div>

      {/* Metadata form */}
      <section className="space-y-4 rounded border p-4">
        <h3 className="font-medium">Kind details</h3>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">Name</label>
            <input
              value={form.name}
              onChange={(e) => { setForm({ ...form, name: e.target.value }); setFormDirty(true); }}
              className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium">Icon</label>
              <input
                value={form.icon}
                onChange={(e) => { setForm({ ...form, icon: e.target.value }); setFormDirty(true); }}
                className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Color</label>
              <input
                type="color"
                value={form.color}
                onChange={(e) => { setForm({ ...form, color: e.target.value }); setFormDirty(true); }}
                className="h-9 w-16 cursor-pointer rounded border"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => { setForm({ ...form, description: e.target.value }); setFormDirty(true); }}
              rows={2}
              className="w-full rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>

        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        {successMsg && <p className="text-sm text-green-600">{successMsg}</p>}

        <Button onClick={handleSaveMeta} disabled={saving || !formDirty}>
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
      </section>

      {/* Attribute definitions */}
      <section className="space-y-3 rounded border p-4">
        <h3 className="font-medium">
          Attributes ({kind.attributes?.length ?? 0})
        </h3>

        {(kind.attributes ?? []).length === 0 && (
          <p className="text-sm text-muted-foreground">No attributes yet.</p>
        )}

        <div className="space-y-1">
          {(kind.attributes ?? []).map((attr) => (
            <div
              key={attr.attr_id}
              className="flex items-center gap-2 rounded border px-3 py-2 text-sm"
            >
              <span className="w-32 shrink-0 font-medium">{attr.name}</span>
              <span className="w-20 shrink-0 text-xs text-muted-foreground">{attr.field_type}</span>
              {attr.is_required && (
                <span className="text-xs text-destructive">required</span>
              )}
              <span className="flex-1 text-xs text-muted-foreground">
                ({attr.code})
              </span>
              <button
                onClick={() => handleDeleteAttr(attr)}
                className="text-xs text-destructive hover:underline"
              >
                Remove
              </button>
            </div>
          ))}
        </div>

        {/* Add attribute inline form */}
        <div className="rounded border border-dashed p-3">
          <p className="mb-2 text-xs font-medium text-muted-foreground">Add attribute</p>
          <div className="flex flex-wrap gap-2">
            <input
              value={newAttr.name}
              onChange={(e) => setNewAttr({ ...newAttr, name: e.target.value })}
              placeholder="Attribute name"
              className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <select
              value={newAttr.field_type}
              onChange={(e) => setNewAttr({ ...newAttr, field_type: e.target.value })}
              className="rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {FIELD_TYPES.map((ft) => (
                <option key={ft} value={ft}>{ft}</option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={newAttr.is_required}
                onChange={(e) => setNewAttr({ ...newAttr, is_required: e.target.checked })}
              />
              Required
            </label>
            <Button size="sm" onClick={handleAddAttr} disabled={addingAttr}>
              {addingAttr ? 'Adding…' : 'Add'}
            </Button>
          </div>
          {attrError && <p className="mt-1 text-xs text-destructive">{attrError}</p>}
        </div>
      </section>

      {/* Delete confirmation modal */}
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

### 9.4 AttributeDeleteConfirmModal.tsx

**File:** `frontend/src/components/glossary/AttributeDeleteConfirmModal.tsx`

```tsx
import { Button } from '@/components/ui/button';

type Props = {
  attrName: string;
  entityCount: number;
  onConfirm: () => void;
  onCancel: () => void;
};

export function AttributeDeleteConfirmModal({ attrName, entityCount, onConfirm, onCancel }: Props) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onCancel} aria-hidden="true" />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-xl">
        <h3 className="mb-3 font-semibold">Remove attribute?</h3>
        <p className="mb-4 text-sm text-muted-foreground">
          <strong>{entityCount}</strong>{' '}
          {entityCount === 1 ? 'entity has' : 'entities have'} data for{' '}
          <strong>{attrName}</strong>. Removing this attribute will hide it from
          their detail view, but the data is preserved and will reappear if the
          attribute is restored.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm}>Remove anyway</Button>
        </div>
      </div>
    </>
  );
}
```

### 9.5 Route and Settings Changes

#### App.tsx additions

Add two new routes (after the glossary route):

```tsx
import { UserKindsPage } from './pages/UserKindsPage';
import { KindDetailPage } from './pages/KindDetailPage';

// In AppRoutes():
<Route
  path="/settings/glossary/kinds"
  element={
    <RequireAuth>
      <UserKindsPage />
    </RequireAuth>
  }
/>
<Route
  path="/settings/glossary/kinds/:userKindId"
  element={
    <RequireAuth>
      <KindDetailPage />
    </RequireAuth>
  }
/>
```

#### UserSettingsPage.tsx — add Glossary sub-navigation

The Glossary tab (added in SS-3) currently shows `GlossarySection`. In SS-4 we add a link to kind management.

**File:** `frontend/src/components/settings/GlossarySection.tsx`

Add at the bottom of the section, after the preferences form:

```tsx
<section className="rounded border p-4">
  <div className="flex items-center justify-between">
    <div>
      <h3 className="font-medium">Kind management</h3>
      <p className="text-sm text-muted-foreground">
        Create and manage custom glossary kinds for your entities.
      </p>
    </div>
    <Link
      to="/settings/glossary/kinds"
      className="rounded border px-3 py-1.5 text-sm hover:bg-muted"
    >
      Manage kinds →
    </Link>
  </div>
</section>
```

### 9.6 RecycleBinPage Extensions

**File:** `frontend/src/pages/RecycleBinPage.tsx`

The SS-2 design rewrote this file to have a Books/Glossary Entities tab structure. SS-4 adds a third tab: "Kinds".

Key additions:
1. Add `'kinds'` to the `Category` type.
2. Add a tab button for "Kinds".
3. When `category === 'kinds'`, render a `UserKindTrashTab` sub-component.

**`UserKindTrashTab` component** (can be inline or in a separate file):

```tsx
function UserKindTrashTab({ token }: { token: string }) {
  const [items, setItems] = useState<UserKindTrashItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const LIMIT = 20;

  async function load(newOffset = 0) {
    setLoading(true);
    try {
      const resp = await glossaryApi.listUserKindTrash(token, { limit: LIMIT, offset: newOffset });
      setItems(resp.items);
      setTotal(resp.total);
      setOffset(newOffset);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRestore(item: UserKindTrashItem) {
    await glossaryApi.restoreUserKind(token, item.user_kind_id);
    load();
  }

  async function handlePurge(item: UserKindTrashItem) {
    if (!confirm(`Permanently delete "${item.name}"? This cannot be undone.`)) return;
    await glossaryApi.purgeUserKind(token, item.user_kind_id);
    load();
  }

  if (loading) return <Skeleton className="h-24 w-full" />;
  if (items.length === 0) return <p className="text-sm text-muted-foreground">No deleted kinds.</p>;

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.user_kind_id} className="flex items-center gap-3 rounded border p-3">
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
              onClick={() => handleRestore(item)}
              className="rounded px-2 py-1 text-xs text-primary hover:bg-muted"
            >
              Restore
            </button>
            <button
              onClick={() => handlePurge(item)}
              className="rounded px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
            >
              Delete permanently
            </button>
          </div>
        </div>
      ))}
      {/* Pagination omitted for brevity — same pattern as UserKindsPage */}
    </div>
  );
}
```

---

## 10) Files to Create/Modify

### New Files

| File | Purpose |
|---|---|
| `services/glossary-service/internal/api/user_kind_handler.go` | All kind + attr CRUD + trash handlers |
| `frontend/src/pages/UserKindsPage.tsx` | Kind list page at `/settings/glossary/kinds` |
| `frontend/src/pages/KindDetailPage.tsx` | Kind edit + attribute management |
| `frontend/src/components/glossary/CreateKindModal.tsx` | Create/clone modal |
| `frontend/src/components/glossary/AttributeDeleteConfirmModal.tsx` | Force-delete warning modal |

### Modified Files

| File | Change |
|---|---|
| `services/glossary-service/internal/migrate/migrate.go` | Add `userKindsSQL` + `UpUserKinds()` |
| `services/glossary-service/internal/api/server.go` | Register 10 new routes |
| `frontend/src/features/glossary/types.ts` | Add `UserKindAttr`, `UserKind`, `UserKindListResponse`, `UserKindTrashItem` |
| `frontend/src/features/glossary/api.ts` | Add 12 new API functions |
| `frontend/src/pages/RecycleBinPage.tsx` | Add "Kinds" category tab + `UserKindTrashTab` |
| `frontend/src/components/settings/GlossarySection.tsx` | Add "Kind management" card with link |
| `frontend/src/App.tsx` | Add 2 new routes |

---

## 11) Test Coverage

### Backend (append to `server_test.go`)

| # | Scenario | Expected |
|---|---|---|
| T1 | `GET /v1/glossary/user-kinds` — empty | 200, `{items: [], total: 0}` |
| T2 | `POST /v1/glossary/user-kinds` from scratch | 201, kind returned with empty attributes |
| T3 | `POST /v1/glossary/user-kinds` clone from T1 | 201, attributes copied from T1 |
| T4 | Clone from non-existent T1 kind | 422 or 500 depending on DB FK check |
| T5 | `POST` duplicate code | 409 `GLOSS_DUPLICATE_CODE` |
| T6 | `GET /v1/glossary/user-kinds/{id}` — owned | 200 with attributes |
| T7 | `GET /v1/glossary/user-kinds/{id}` — not owned | 404 |
| T8 | `PATCH /v1/glossary/user-kinds/{id}` name change | 200, updated name |
| T9 | `PATCH` read-only field `code` — ignored | 200, code unchanged |
| T10 | `DELETE /v1/glossary/user-kinds/{id}` — no entities | 204 |
| T11 | `DELETE` kind with live entities | 409 `GLOSS_KIND_HAS_ENTITIES` |
| T12 | `GET /v1/glossary/user-kinds?is_active=false` | 200, only inactive kinds |
| T13 | `POST .../attributes` — valid | 201, attr returned |
| T14 | `POST .../attributes` duplicate code | 409 `GLOSS_DUPLICATE_CODE` |
| T15 | `PATCH .../attributes/{id}` | 200, updated attr |
| T16 | `DELETE .../attributes/{id}` — no data | 204 |
| T17 | `DELETE .../attributes/{id}` — has data, no force | 409 `GLOSS_ATTR_HAS_DATA` with count |
| T18 | `DELETE .../attributes/{id}?force=true` — has data | 204 |
| T19 | `DELETE` kind → appears in `GET /user-kinds-trash` | 200, kind in list |
| T20 | `POST /user-kinds-trash/{id}/restore` | 204; kind disappears from trash |
| T21 | `DELETE /user-kinds-trash/{id}` (purge) | 204; kind gone from trash, permanently_deleted_at set |
| T22 | `GET /v1/glossary/user-kinds?cloned_from=system` | only cloned kinds |
| T23 | `GET /v1/glossary/user-kinds?sort=name` | alphabetical order |

### Frontend Tests

| # | Scenario | Expected |
|---|---|---|
| F1 | `UserKindsPage` — load with kinds | Cards rendered |
| F2 | `UserKindsPage` — "Deactivate" → PATCH | `is_active: false` sent |
| F3 | `UserKindsPage` — "Delete" → 409 → alert shown | `GLOSS_KIND_HAS_ENTITIES` message displayed |
| F4 | `CreateKindModal` — from scratch submit | `createUserKind` called without `clone_from_kind_id` |
| F5 | `CreateKindModal` — clone mode select + submit | `createUserKind` called with `clone_from_kind_id` |
| F6 | `KindDetailPage` — save metadata | `patchUserKind` called |
| F7 | `KindDetailPage` — add attribute | `createUserKindAttr` called |
| F8 | `KindDetailPage` — delete attribute (no data) | `deleteUserKindAttr(false)` → success |
| F9 | `KindDetailPage` — delete attr → 409 → modal shown → confirm | `deleteUserKindAttr(true)` called |
| F10 | `RecycleBinPage` Kinds tab — restore | `restoreUserKind` called; item removed |

---

## 12) Exit Criteria

- [ ] `UpUserKinds()` migration runs successfully; `user_kinds` + `user_kind_attributes` tables created.
- [ ] User can create kind from scratch: name/icon/color set correctly.
- [ ] User can clone from T1 kind: all T1 attributes copied into `user_kind_attributes`.
- [ ] Duplicate code returns 409; invalid field_type returns 422.
- [ ] `DELETE /user-kinds/{id}` with live entities returns 409 with count message.
- [ ] Attribute delete without data: soft delete succeeds.
- [ ] Attribute delete with data, no force: 409 with entity count.
- [ ] Attribute delete with force=true: soft delete succeeds.
- [ ] Deleted kind appears in `/user-kinds-trash`; restore returns it to list; purge removes it.
- [ ] `UserKindsPage` at `/settings/glossary/kinds` renders kind list with pagination.
- [ ] `KindDetailPage` shows kind + attributes; inline add works; remove opens confirmation if needed.
- [ ] `RecycleBinPage` "Kinds" tab shows deleted user kinds with restore/purge actions.
- [ ] `GlossarySection` settings shows "Kind management" link.
- [ ] `go test ./...` passes.
- [ ] `npx tsc --noEmit` passes.
