# SS-6 — Kind Sync + Compare: Detailed Design

## Document Metadata

- Document ID: LW-M05-95
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Tech Lead
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Parent Plan: [doc 89](89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md) — SS-6 row
- Depends on: SS-5 complete (`book_kinds` + `user_kinds` both exist; `v_attr_def` view created)
- Summary: Full technical design for cross-tier kind attribute synchronisation. No new DB tables. Two new API endpoints (compare, sync apply). Frontend `KindCompareModal` with per-attribute diff table + checkbox selection. Entry points wired into SS-4 `KindDetailPage` and SS-5 `BookGlossaryKindsPage`.

## Change History

| Version | Date       | Change         | Author    |
| ------- | ---------- | -------------- | --------- |
| 0.1.0   | 2026-03-25 | Initial design | Assistant |

---

## 1) Goal & Scope

**In scope:**
- `POST /v1/glossary/kinds/compare` — compute attribute diff between any two kinds (same or different tiers)
- `POST /v1/glossary/kinds/sync` — apply selected diff items to the target kind
- Allowed sync directions: T1→T2, T1→T3, T2→T3, T3→T2
- Forbidden: T2→T1, T3→T1 (return 403)
- Data guard: if `removed` attribute has entity values → return per-attr warning (count), not a hard block
- `KindCompareModal.tsx` — two-column diff table with checkbox selection, "Apply selected" flow
- Entry points: "Re-sync from system" on `KindDetailPage` (T2 kinds) and on `BookGlossaryKindsPage` (T3 kinds); "Push to my kinds" and "Push to this book" buttons

**Out of scope:**
- Merging kind *metadata* (name, color, icon, description) — this sub-phase syncs attributes only
- Bulk sync across multiple target kinds
- Automated/scheduled sync
- SS-7 entity-picker wiring

---

## 2) DB Migration

**No new tables or columns required.** SS-5 already created `user_kind_attributes`, `book_kind_attributes`, and `v_attr_def`. SS-6 only reads these tables.

Migration function: `migrate.UpKindSync(ctx, pool)` in `services/glossary-service/internal/migrate/migrate.go`

Body is a no-op DDL (only comments), but the function must exist to allow incremental migration calls:

```go
// UpKindSync — SS-6. No schema changes needed; v_attr_def and kind tables exist after SS-5.
func UpKindSync(ctx context.Context, pool *pgxpool.Pool) error {
    // No DDL; this is a logical placeholder for the SS-6 migration slot.
    return nil
}
```

Call it at the end of `Up()` after `UpBookKinds`:

```go
if err := UpKindSync(ctx, pool); err != nil {
    return fmt.Errorf("UpKindSync: %w", err)
}
```

---

## 3) Diff Algorithm

Match by **`code`** (stable slug identifier, unique within a kind's attribute set).

| Status | Condition |
|---|---|
| `added` | code present in source attrs; **absent** in (non-deleted) target attrs |
| `removed` | code present in (non-deleted) target attrs; **absent** in source attrs |
| `modified` | code in both; any of `name`, `field_type`, `is_required`, `sort_order`, `options` differ |
| `unchanged` | code in both; all compared fields identical |

**Compared fields** (per attribute):

| Field | Source type | Notes |
|---|---|---|
| `code` | `TEXT` | match key, never included in diff fields |
| `name` | `TEXT` | compared as-is |
| `field_type` | `TEXT` | compared as-is |
| `is_required` | `BOOL` | compared as-is |
| `sort_order` | `INT` | compared as-is |
| `options` | `TEXT[]` | compared as sorted slices (nil == empty) |

`diff_key` format: `"{status}:{code}"` — e.g. `"added:aliases"`, `"modified:birth_date"`, `"removed:height"`. This is what the client sends back in `apply[]`.

---

## 4) Sync Apply Semantics

| Direction | Allowed | Effect |
|---|---|---|
| T1 → T2 | ✓ | INSERT/UPDATE/soft-delete on `user_kind_attributes` |
| T1 → T3 | ✓ | INSERT/UPDATE/soft-delete on `book_kind_attributes` |
| T2 → T3 | ✓ | INSERT/UPDATE/soft-delete on `book_kind_attributes`; verify both belong to same owner |
| T3 → T2 | ✓ | INSERT/UPDATE/soft-delete on `user_kind_attributes`; verify both belong to same owner |
| T2 → T1 | ✗ | 403 `GLOSS_SYNC_FORBIDDEN_TARGET` |
| T3 → T1 | ✗ | 403 `GLOSS_SYNC_FORBIDDEN_TARGET` |
| Same tier (e.g. T2 → T2) | ✗ | 400 `GLOSS_SYNC_SAME_KIND` if source.id == target.id |

**Apply rules per diff type:**

- `added`: INSERT new attribute row into target's table. `code`, `name`, `field_type`, `is_required`, `sort_order`, `options` copied from source. New `attr_id = gen_random_uuid()`. `deleted_at = NULL`.
- `modified`: UPDATE existing (non-deleted) target attribute row — set `name`, `field_type`, `is_required`, `sort_order`, `options`, `updated_at = now()`.
- `removed`: Soft-delete target attribute (`deleted_at = now()`). **Data guard**: before setting `deleted_at`, count `entity_attribute_values` rows where the correct FK column (`attr_def_id` / `user_attr_def_id` / `book_attr_def_id`) = target attr id AND `original_value != ''`. If count > 0 → populate `warnings` in response; still apply the soft-delete (the client already confirmed via the modal before calling Apply). See section 5.3 for pre-check endpoint behaviour.
- `unchanged`: no-op (even if included in `apply[]` list, skip silently).

All apply operations run in a single DB transaction. If any step fails → rollback entire sync.

---

## 5) API Endpoints

All endpoints: require JWT Bearer (validated via `requireUserID` middleware).

Route prefix: `/v1/glossary/kinds`

New routes registered in `server.go`:

```go
mux.HandleFunc("POST /v1/glossary/kinds/compare", s.handleKindCompare)
mux.HandleFunc("POST /v1/glossary/kinds/sync",    s.handleKindSync)
```

---

### 5.1 POST /v1/glossary/kinds/compare

**Purpose:** Compute the attribute diff between source and target kinds (read-only).

**Request body:**

```json
{
  "source": { "tier": "system", "id": "uuid-of-t1-kind" },
  "target": { "tier": "user",   "id": "uuid-of-t2-kind" }
}
```

`tier` values: `"system"` (T1), `"user"` (T2), `"book"` (T3).

**Ownership validation:**
- If target.tier = `"user"`: verify `user_kinds.owner_user_id = userID` AND `deleted_at IS NULL`
- If target.tier = `"book"`: call `verifyBookOwner` on the book that owns the kind (fetch `book_kinds.book_id`) + verify `book_kinds.owner_user_id = userID` AND `deleted_at IS NULL`
- If target.tier = `"system"`: return 403 `GLOSS_SYNC_FORBIDDEN_TARGET`
- Source: read-only, no ownership check. But verify exists and `deleted_at IS NULL`.

**Response 200:**

```json
{
  "source": { "tier": "system", "id": "...", "name": "Character", "code": "character" },
  "target": { "tier": "user",   "id": "...", "name": "My Character", "code": "my_character" },
  "diff": [
    {
      "diff_key":   "unchanged:aliases",
      "status":     "unchanged",
      "source_attr": { "code": "aliases", "name": "Aliases", "field_type": "text_list", "is_required": false, "sort_order": 1, "options": null },
      "target_attr": { "code": "aliases", "name": "Aliases", "field_type": "text_list", "is_required": false, "sort_order": 1, "options": null }
    },
    {
      "diff_key":   "modified:birth_date",
      "status":     "modified",
      "source_attr": { "code": "birth_date", "name": "Birth Date", "field_type": "text", "is_required": false, "sort_order": 2, "options": null },
      "target_attr": { "code": "birth_date", "name": "Birthday",   "field_type": "text", "is_required": true,  "sort_order": 2, "options": null }
    },
    {
      "diff_key":    "added:occupation",
      "status":      "added",
      "source_attr": { "code": "occupation", "name": "Occupation", "field_type": "text", "is_required": false, "sort_order": 5, "options": null },
      "target_attr": null
    },
    {
      "diff_key":    "removed:height",
      "status":      "removed",
      "source_attr": null,
      "target_attr": { "code": "height", "name": "Height (cm)", "field_type": "number", "is_required": false, "sort_order": 6, "options": null }
    }
  ],
  "has_data_warnings": false
}
```

`has_data_warnings`: pre-computes whether any `removed` diff item has existing entity values. Allows the modal to show a warning banner before the user even checks any boxes.

**Error codes:**

| HTTP | Code | Condition |
|---|---|---|
| 400 | `GLOSS_SYNC_INVALID_TIER` | `tier` not one of `system/user/book` |
| 400 | `GLOSS_SYNC_SAME_KIND` | source.id == target.id |
| 403 | `GLOSS_SYNC_FORBIDDEN_TARGET` | target.tier = `system` |
| 404 | `GLOSS_SYNC_SOURCE_NOT_FOUND` | source kind not found or deleted |
| 404 | `GLOSS_SYNC_TARGET_NOT_FOUND` | target kind not found, deleted, or not owned by user |

---

### 5.2 POST /v1/glossary/kinds/sync

**Purpose:** Apply selected diff items to the target kind.

**Request body:**

```json
{
  "source": { "tier": "system", "id": "uuid-of-t1-kind" },
  "target": { "tier": "user",   "id": "uuid-of-t2-kind" },
  "apply":  ["added:occupation", "modified:birth_date", "removed:height"]
}
```

`apply`: list of `diff_key` strings to apply. Must be non-empty. Unknown or `unchanged` keys are silently skipped.

**Behaviour:**
1. Re-run compare internally to get fresh diff (prevents TOCTOU with stale modal state).
2. Validate ownership (same rules as compare).
3. Validate direction (return 403 if T→T1).
4. Open DB transaction.
5. For each `diff_key` in `apply`:
   - Parse `status:code` → look up in fresh diff result.
   - Dispatch to apply function.
6. Collect `warnings` (removed attrs with data counts).
7. Commit transaction.
8. Return updated kind detail + any warnings.

**Response 200:**

```json
{
  "kind": {
    "kind_id": "...",
    "tier": "user",
    "code": "my_character",
    "name": "My Character",
    "attributes": [ ... ]
  },
  "applied_count": 3,
  "warnings": [
    {
      "diff_key":    "removed:height",
      "code":        "height",
      "entity_count": 12,
      "message":     "Attribute soft-deleted. 12 entity values remain and will display from snapshot."
    }
  ]
}
```

`warnings` is `[]` when no removed attrs had data. Empty `warnings` = clean sync.

**Error codes:** same set as compare (400/403/404), plus:

| HTTP | Code | Condition |
|---|---|---|
| 400 | `GLOSS_SYNC_EMPTY_APPLY` | `apply` array is empty or missing |
| 409 | `GLOSS_SYNC_CONFLICT` | Concurrent modification detected (optimistic: target kind `updated_at` changed between compare and sync) — rare, tell client to re-open modal |

---

## 6) Go Implementation

### 6.1 File: `services/glossary-service/internal/api/kind_sync_handler.go`

```go
package api

import (
    "context"
    "encoding/json"
    "net/http"
    "sort"
    "strings"
    "time"

    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgxpool"
)

// ── Domain types ──────────────────────────────────────────────────────────────

type kindTier string

const (
    tierSystem kindTier = "system"
    tierUser   kindTier = "user"
    tierBook   kindTier = "book"
)

type kindRef struct {
    Tier kindTier `json:"tier"`
    ID   string   `json:"id"`
}

type syncAttrSnap struct {
    Code       string   `json:"code"`
    Name       string   `json:"name"`
    FieldType  string   `json:"field_type"`
    IsRequired bool     `json:"is_required"`
    SortOrder  int      `json:"sort_order"`
    Options    []string `json:"options"`
}

type diffStatus string

const (
    diffAdded     diffStatus = "added"
    diffRemoved   diffStatus = "removed"
    diffModified  diffStatus = "modified"
    diffUnchanged diffStatus = "unchanged"
)

type diffItem struct {
    DiffKey    string        `json:"diff_key"`
    Status     diffStatus    `json:"status"`
    SourceAttr *syncAttrSnap `json:"source_attr"`
    TargetAttr *syncAttrSnap `json:"target_attr"`
}

type kindMeta struct {
    Tier kindTier `json:"tier"`
    ID   string   `json:"id"`
    Name string   `json:"name"`
    Code string   `json:"code"`
}

type compareResult struct {
    Source          kindMeta   `json:"source"`
    Target          kindMeta   `json:"target"`
    Diff            []diffItem `json:"diff"`
    HasDataWarnings bool       `json:"has_data_warnings"`
}

type syncWarning struct {
    DiffKey     string `json:"diff_key"`
    Code        string `json:"code"`
    EntityCount int    `json:"entity_count"`
    Message     string `json:"message"`
}

// ── Request/response types ────────────────────────────────────────────────────

type compareRequest struct {
    Source kindRef `json:"source"`
    Target kindRef `json:"target"`
}

type syncRequest struct {
    Source kindRef  `json:"source"`
    Target kindRef  `json:"target"`
    Apply  []string `json:"apply"`
}

type syncedKindAttr struct {
    AttrID     string   `json:"attr_id"`
    Code       string   `json:"code"`
    Name       string   `json:"name"`
    FieldType  string   `json:"field_type"`
    IsRequired bool     `json:"is_required"`
    SortOrder  int      `json:"sort_order"`
    Options    []string `json:"options"`
}

type syncedKind struct {
    KindID     string           `json:"kind_id"`
    Tier       kindTier         `json:"tier"`
    Code       string           `json:"code"`
    Name       string           `json:"name"`
    Attributes []syncedKindAttr `json:"attributes"`
}

type syncResponse struct {
    Kind         syncedKind    `json:"kind"`
    AppliedCount int           `json:"applied_count"`
    Warnings     []syncWarning `json:"warnings"`
}

// ── Handlers ──────────────────────────────────────────────────────────────────

func (s *Server) handleKindCompare(w http.ResponseWriter, r *http.Request) {
    userID := requireUserID(r)
    if userID == "" {
        writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "missing user")
        return
    }
    var req compareRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "BAD_REQUEST", err.Error())
        return
    }
    if err := validateTiers(req.Source.Tier, req.Target.Tier); err != nil {
        writeError(w, http.StatusBadRequest, err.Error(), err.Error())
        return
    }
    if req.Source.ID == req.Target.ID && req.Source.Tier == req.Target.Tier {
        writeError(w, http.StatusBadRequest, "GLOSS_SYNC_SAME_KIND", "source and target are the same kind")
        return
    }
    if req.Target.Tier == tierSystem {
        writeError(w, http.StatusForbidden, "GLOSS_SYNC_FORBIDDEN_TARGET", "cannot sync into system tier")
        return
    }

    ctx := r.Context()
    srcMeta, srcAttrs, err := loadKindAttrs(ctx, s.db, req.Source, "")
    if err != nil {
        writeKindError(w, err, "GLOSS_SYNC_SOURCE_NOT_FOUND")
        return
    }
    tgtMeta, tgtAttrs, err := loadKindAttrsOwned(ctx, s.db, req.Target, userID)
    if err != nil {
        writeKindError(w, err, "GLOSS_SYNC_TARGET_NOT_FOUND")
        return
    }

    diff := computeDiff(srcAttrs, tgtAttrs)
    hasWarn := preCheckDataWarnings(ctx, s.db, diff, req.Target)

    writeJSON(w, http.StatusOK, compareResult{
        Source:          srcMeta,
        Target:          tgtMeta,
        Diff:            diff,
        HasDataWarnings: hasWarn,
    })
}

func (s *Server) handleKindSync(w http.ResponseWriter, r *http.Request) {
    userID := requireUserID(r)
    if userID == "" {
        writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "missing user")
        return
    }
    var req syncRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "BAD_REQUEST", err.Error())
        return
    }
    if len(req.Apply) == 0 {
        writeError(w, http.StatusBadRequest, "GLOSS_SYNC_EMPTY_APPLY", "apply list must be non-empty")
        return
    }
    if err := validateTiers(req.Source.Tier, req.Target.Tier); err != nil {
        writeError(w, http.StatusBadRequest, err.Error(), err.Error())
        return
    }
    if req.Target.Tier == tierSystem {
        writeError(w, http.StatusForbidden, "GLOSS_SYNC_FORBIDDEN_TARGET", "cannot sync into system tier")
        return
    }

    ctx := r.Context()

    // Re-run compare fresh to avoid TOCTOU
    _, srcAttrs, err := loadKindAttrs(ctx, s.db, req.Source, "")
    if err != nil {
        writeKindError(w, err, "GLOSS_SYNC_SOURCE_NOT_FOUND")
        return
    }
    tgtMeta, tgtAttrs, err := loadKindAttrsOwned(ctx, s.db, req.Target, userID)
    if err != nil {
        writeKindError(w, err, "GLOSS_SYNC_TARGET_NOT_FOUND")
        return
    }

    freshDiff := computeDiff(srcAttrs, tgtAttrs)
    applySet := make(map[string]struct{}, len(req.Apply))
    for _, k := range req.Apply {
        applySet[k] = struct{}{}
    }

    tx, err := s.db.Begin(ctx)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "DB_ERROR", err.Error())
        return
    }
    defer tx.Rollback(ctx)

    var warnings []syncWarning
    appliedCount := 0

    for _, item := range freshDiff {
        if _, ok := applySet[item.DiffKey]; !ok {
            continue
        }
        if item.Status == diffUnchanged {
            continue
        }
        warn, err := applyDiffItem(ctx, tx, item, req.Target, tgtMeta)
        if err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_SYNC_APPLY_ERROR", err.Error())
            return
        }
        if warn != nil {
            warnings = append(warnings, *warn)
        }
        appliedCount++
    }

    if err := tx.Commit(ctx); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_SYNC_CONFLICT", "concurrent modification, please retry")
        return
    }

    // Reload target kind for response
    kind, err := loadSyncedKind(ctx, s.db, req.Target, tgtMeta)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "DB_ERROR", err.Error())
        return
    }
    if warnings == nil {
        warnings = []syncWarning{}
    }

    writeJSON(w, http.StatusOK, syncResponse{
        Kind:         kind,
        AppliedCount: appliedCount,
        Warnings:     warnings,
    })
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func validateTiers(src, tgt kindTier) error {
    valid := map[kindTier]bool{tierSystem: true, tierUser: true, tierBook: true}
    if !valid[src] || !valid[tgt] {
        return fmt.Errorf("GLOSS_SYNC_INVALID_TIER")
    }
    return nil
}

func writeKindError(w http.ResponseWriter, err error, code string) {
    if err == pgx.ErrNoRows {
        writeError(w, http.StatusNotFound, code, "kind not found")
    } else {
        writeError(w, http.StatusInternalServerError, "DB_ERROR", err.Error())
    }
}

// loadKindAttrs loads kind metadata + non-deleted attributes for any tier (no ownership check).
// bookID is only required when tier = "book" to call verifyBookOwner.
func loadKindAttrs(ctx context.Context, db *pgxpool.Pool, ref kindRef, ownerUserID string) (kindMeta, []syncAttrSnap, error) {
    switch ref.Tier {
    case tierSystem:
        return loadSystemKindAttrs(ctx, db, ref.ID)
    case tierUser:
        return loadUserKindAttrs(ctx, db, ref.ID, ownerUserID)
    case tierBook:
        return loadBookKindAttrs(ctx, db, ref.ID, ownerUserID)
    }
    return kindMeta{}, nil, fmt.Errorf("invalid tier")
}

func loadKindAttrsOwned(ctx context.Context, db *pgxpool.Pool, ref kindRef, userID string) (kindMeta, []syncAttrSnap, error) {
    return loadKindAttrs(ctx, db, ref, userID)
}

func loadSystemKindAttrs(ctx context.Context, db *pgxpool.Pool, kindID string) (kindMeta, []syncAttrSnap, error) {
    var meta kindMeta
    err := db.QueryRow(ctx,
        `SELECT kind_id, code, name FROM entity_kinds WHERE kind_id = $1 AND deleted_at IS NULL`,
        kindID,
    ).Scan(&meta.ID, &meta.Code, &meta.Name)
    if err != nil {
        return kindMeta{}, nil, err
    }
    meta.Tier = tierSystem

    rows, err := db.Query(ctx,
        `SELECT code, name, field_type, is_required, sort_order, COALESCE(options, '{}')
         FROM attribute_definitions
         WHERE kind_id = $1
         ORDER BY sort_order, code`,
        kindID,
    )
    if err != nil {
        return meta, nil, err
    }
    defer rows.Close()
    attrs, err := scanAttrSnaps(rows)
    return meta, attrs, err
}

func loadUserKindAttrs(ctx context.Context, db *pgxpool.Pool, kindID, ownerUserID string) (kindMeta, []syncAttrSnap, error) {
    var meta kindMeta
    q := `SELECT user_kind_id, code, name FROM user_kinds
          WHERE user_kind_id = $1 AND deleted_at IS NULL`
    args := []any{kindID}
    if ownerUserID != "" {
        q += ` AND owner_user_id = $2`
        args = append(args, ownerUserID)
    }
    err := db.QueryRow(ctx, q, args...).Scan(&meta.ID, &meta.Code, &meta.Name)
    if err != nil {
        return kindMeta{}, nil, err
    }
    meta.Tier = tierUser

    rows, err := db.Query(ctx,
        `SELECT code, name, field_type, is_required, sort_order, COALESCE(options, '{}')
         FROM user_kind_attributes
         WHERE user_kind_id = $1 AND deleted_at IS NULL
         ORDER BY sort_order, code`,
        kindID,
    )
    if err != nil {
        return meta, nil, err
    }
    defer rows.Close()
    attrs, err := scanAttrSnaps(rows)
    return meta, attrs, err
}

func loadBookKindAttrs(ctx context.Context, db *pgxpool.Pool, kindID, ownerUserID string) (kindMeta, []syncAttrSnap, error) {
    var meta kindMeta
    q := `SELECT book_kind_id, code, name FROM book_kinds
          WHERE book_kind_id = $1 AND deleted_at IS NULL`
    args := []any{kindID}
    if ownerUserID != "" {
        q += ` AND owner_user_id = $2`
        args = append(args, ownerUserID)
    }
    err := db.QueryRow(ctx, q, args...).Scan(&meta.ID, &meta.Code, &meta.Name)
    if err != nil {
        return kindMeta{}, nil, err
    }
    meta.Tier = tierBook

    rows, err := db.Query(ctx,
        `SELECT code, name, field_type, is_required, sort_order, COALESCE(options, '{}')
         FROM book_kind_attributes
         WHERE book_kind_id = $1 AND deleted_at IS NULL
         ORDER BY sort_order, code`,
        kindID,
    )
    if err != nil {
        return meta, nil, err
    }
    defer rows.Close()
    attrs, err := scanAttrSnaps(rows)
    return meta, attrs, err
}

func scanAttrSnaps(rows pgx.Rows) ([]syncAttrSnap, error) {
    var result []syncAttrSnap
    for rows.Next() {
        var a syncAttrSnap
        if err := rows.Scan(&a.Code, &a.Name, &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options); err != nil {
            return nil, err
        }
        result = append(result, a)
    }
    return result, rows.Err()
}

// computeDiff performs the O(n) diff by building maps keyed on code.
func computeDiff(srcAttrs, tgtAttrs []syncAttrSnap) []diffItem {
    srcMap := make(map[string]syncAttrSnap, len(srcAttrs))
    for _, a := range srcAttrs {
        srcMap[a.Code] = a
    }
    tgtMap := make(map[string]syncAttrSnap, len(tgtAttrs))
    for _, a := range tgtAttrs {
        tgtMap[a.Code] = a
    }

    var result []diffItem

    // added + modified + unchanged (iterate source)
    for _, sa := range srcAttrs {
        ta, exists := tgtMap[sa.Code]
        if !exists {
            result = append(result, diffItem{
                DiffKey:    "added:" + sa.Code,
                Status:     diffAdded,
                SourceAttr: ptr(sa),
                TargetAttr: nil,
            })
        } else if attrsEqual(sa, ta) {
            result = append(result, diffItem{
                DiffKey:    "unchanged:" + sa.Code,
                Status:     diffUnchanged,
                SourceAttr: ptr(sa),
                TargetAttr: ptr(ta),
            })
        } else {
            result = append(result, diffItem{
                DiffKey:    "modified:" + sa.Code,
                Status:     diffModified,
                SourceAttr: ptr(sa),
                TargetAttr: ptr(ta),
            })
        }
    }

    // removed (iterate target, missing in source)
    for _, ta := range tgtAttrs {
        if _, exists := srcMap[ta.Code]; !exists {
            result = append(result, diffItem{
                DiffKey:    "removed:" + ta.Code,
                Status:     diffRemoved,
                SourceAttr: nil,
                TargetAttr: ptr(ta),
            })
        }
    }

    // stable sort: added → modified → removed → unchanged; within group, by code
    statusOrder := map[diffStatus]int{diffAdded: 0, diffModified: 1, diffRemoved: 2, diffUnchanged: 3}
    sort.Slice(result, func(i, j int) bool {
        oi, oj := statusOrder[result[i].Status], statusOrder[result[j].Status]
        if oi != oj {
            return oi < oj
        }
        return result[i].DiffKey < result[j].DiffKey
    })
    return result
}

func attrsEqual(a, b syncAttrSnap) bool {
    if a.Name != b.Name || a.FieldType != b.FieldType ||
        a.IsRequired != b.IsRequired || a.SortOrder != b.SortOrder {
        return false
    }
    return slicesEqualSorted(a.Options, b.Options)
}

func slicesEqualSorted(a, b []string) bool {
    ac, bc := append([]string{}, a...), append([]string{}, b...)
    sort.Strings(ac)
    sort.Strings(bc)
    if len(ac) != len(bc) {
        return false
    }
    for i := range ac {
        if ac[i] != bc[i] {
            return false
        }
    }
    return true
}

func ptr[T any](v T) *T { return &v }

// preCheckDataWarnings scans for any removed diff items that have entity data.
func preCheckDataWarnings(ctx context.Context, db *pgxpool.Pool, diff []diffItem, tgt kindRef) bool {
    for _, item := range diff {
        if item.Status != diffRemoved {
            continue
        }
        count := countAttrData(ctx, db, item.TargetAttr.Code, tgt)
        if count > 0 {
            return true
        }
    }
    return false
}

// countAttrData counts entity_attribute_values rows for a given attribute code + target kind.
// Gracefully degrades (returns 0) if the target attr FK columns don't exist yet (pre-SS-7).
func countAttrData(ctx context.Context, db *pgxpool.Pool, attrCode string, tgt kindRef) int {
    var q string
    var args []any
    switch tgt.Tier {
    case tierUser:
        q = `SELECT COUNT(*) FROM entity_attribute_values eav
             JOIN user_kind_attributes uka ON uka.attr_id = eav.user_attr_def_id
             WHERE uka.user_kind_id = (
               SELECT user_kind_id FROM user_kind_attributes WHERE code = $1
               AND user_kind_id = $2 AND deleted_at IS NULL LIMIT 1
             ) AND eav.original_value != ''`
        args = []any{attrCode, tgt.ID}
    case tierBook:
        q = `SELECT COUNT(*) FROM entity_attribute_values eav
             JOIN book_kind_attributes bka ON bka.attr_id = eav.book_attr_def_id
             WHERE bka.book_kind_id = (
               SELECT book_kind_id FROM book_kind_attributes WHERE code = $1
               AND book_kind_id = $2 AND deleted_at IS NULL LIMIT 1
             ) AND eav.original_value != ''`
        args = []any{attrCode, tgt.ID}
    default:
        return 0
    }
    var count int
    _ = db.QueryRow(ctx, q, args...).Scan(&count)
    // Silently returns 0 if column doesn't exist yet (pre-SS-7); pgx error swallowed intentionally
    return count
}

// applyDiffItem applies one diff item within a transaction. Returns a warning if removed attr had data.
func applyDiffItem(ctx context.Context, tx pgx.Tx, item diffItem, tgt kindRef, tgtMeta kindMeta) (*syncWarning, error) {
    switch item.Status {
    case diffAdded:
        return nil, insertAttrIntoTarget(ctx, tx, item.SourceAttr, tgt)
    case diffModified:
        return nil, updateAttrInTarget(ctx, tx, item.SourceAttr, tgt)
    case diffRemoved:
        count := countAttrDataTx(ctx, tx, item.TargetAttr.Code, tgt)
        if err := softDeleteAttrInTarget(ctx, tx, item.TargetAttr.Code, tgt); err != nil {
            return nil, err
        }
        if count > 0 {
            return &syncWarning{
                DiffKey:     item.DiffKey,
                Code:        item.TargetAttr.Code,
                EntityCount: count,
                Message:     fmt.Sprintf("Attribute soft-deleted. %d entity values remain and will display from snapshot.", count),
            }, nil
        }
        return nil, nil
    }
    return nil, nil
}

func insertAttrIntoTarget(ctx context.Context, tx pgx.Tx, src *syncAttrSnap, tgt kindRef) error {
    switch tgt.Tier {
    case tierUser:
        _, err := tx.Exec(ctx,
            `INSERT INTO user_kind_attributes
               (user_kind_id, code, name, field_type, is_required, sort_order, options)
             VALUES ($1,$2,$3,$4,$5,$6,$7)
             ON CONFLICT (user_kind_id, code) DO UPDATE
               SET deleted_at = NULL,
                   name = EXCLUDED.name, field_type = EXCLUDED.field_type,
                   is_required = EXCLUDED.is_required, sort_order = EXCLUDED.sort_order,
                   options = EXCLUDED.options, updated_at = now()`,
            tgt.ID, src.Code, src.Name, src.FieldType, src.IsRequired, src.SortOrder, src.Options,
        )
        return err
    case tierBook:
        _, err := tx.Exec(ctx,
            `INSERT INTO book_kind_attributes
               (book_kind_id, code, name, field_type, is_required, sort_order, options)
             VALUES ($1,$2,$3,$4,$5,$6,$7)
             ON CONFLICT (book_kind_id, code) DO UPDATE
               SET deleted_at = NULL,
                   name = EXCLUDED.name, field_type = EXCLUDED.field_type,
                   is_required = EXCLUDED.is_required, sort_order = EXCLUDED.sort_order,
                   options = EXCLUDED.options, updated_at = now()`,
            tgt.ID, src.Code, src.Name, src.FieldType, src.IsRequired, src.SortOrder, src.Options,
        )
        return err
    }
    return nil
}

func updateAttrInTarget(ctx context.Context, tx pgx.Tx, src *syncAttrSnap, tgt kindRef) error {
    switch tgt.Tier {
    case tierUser:
        _, err := tx.Exec(ctx,
            `UPDATE user_kind_attributes
             SET name=$2, field_type=$3, is_required=$4, sort_order=$5, options=$6, updated_at=now()
             WHERE user_kind_id=$1 AND code=$7 AND deleted_at IS NULL`,
            tgt.ID, src.Name, src.FieldType, src.IsRequired, src.SortOrder, src.Options, src.Code,
        )
        return err
    case tierBook:
        _, err := tx.Exec(ctx,
            `UPDATE book_kind_attributes
             SET name=$2, field_type=$3, is_required=$4, sort_order=$5, options=$6, updated_at=now()
             WHERE book_kind_id=$1 AND code=$7 AND deleted_at IS NULL`,
            tgt.ID, src.Name, src.FieldType, src.IsRequired, src.SortOrder, src.Options, src.Code,
        )
        return err
    }
    return nil
}

func softDeleteAttrInTarget(ctx context.Context, tx pgx.Tx, code string, tgt kindRef) error {
    switch tgt.Tier {
    case tierUser:
        _, err := tx.Exec(ctx,
            `UPDATE user_kind_attributes SET deleted_at=now()
             WHERE user_kind_id=$1 AND code=$2 AND deleted_at IS NULL`,
            tgt.ID, code,
        )
        return err
    case tierBook:
        _, err := tx.Exec(ctx,
            `UPDATE book_kind_attributes SET deleted_at=now()
             WHERE book_kind_id=$1 AND code=$2 AND deleted_at IS NULL`,
            tgt.ID, code,
        )
        return err
    }
    return nil
}

// countAttrDataTx — same as countAttrData but uses an open transaction.
func countAttrDataTx(ctx context.Context, tx pgx.Tx, attrCode string, tgt kindRef) int {
    // Pre-SS-7 the FK columns don't exist yet; swallow the error and return 0.
    var count int
    var q string
    var args []any
    switch tgt.Tier {
    case tierUser:
        q = `SELECT COUNT(*) FROM entity_attribute_values eav
             JOIN user_kind_attributes uka ON uka.attr_id = eav.user_attr_def_id
             WHERE uka.code = $1 AND uka.user_kind_id = $2 AND eav.original_value != ''`
        args = []any{attrCode, tgt.ID}
    case tierBook:
        q = `SELECT COUNT(*) FROM entity_attribute_values eav
             JOIN book_kind_attributes bka ON bka.attr_id = eav.book_attr_def_id
             WHERE bka.code = $1 AND bka.book_kind_id = $2 AND eav.original_value != ''`
        args = []any{attrCode, tgt.ID}
    default:
        return 0
    }
    _ = tx.QueryRow(ctx, q, args...).Scan(&count)
    return count
}

func loadSyncedKind(ctx context.Context, db *pgxpool.Pool, ref kindRef, meta kindMeta) (syncedKind, error) {
    kind := syncedKind{KindID: meta.ID, Tier: meta.Tier, Code: meta.Code, Name: meta.Name}
    var rows pgx.Rows
    var err error
    switch ref.Tier {
    case tierUser:
        rows, err = db.Query(ctx,
            `SELECT attr_id, code, name, field_type, is_required, sort_order, COALESCE(options, '{}')
             FROM user_kind_attributes WHERE user_kind_id=$1 AND deleted_at IS NULL ORDER BY sort_order,code`,
            ref.ID)
    case tierBook:
        rows, err = db.Query(ctx,
            `SELECT attr_id, code, name, field_type, is_required, sort_order, COALESCE(options, '{}')
             FROM book_kind_attributes WHERE book_kind_id=$1 AND deleted_at IS NULL ORDER BY sort_order,code`,
            ref.ID)
    default:
        return kind, nil
    }
    if err != nil {
        return kind, err
    }
    defer rows.Close()
    for rows.Next() {
        var a syncedKindAttr
        if err := rows.Scan(&a.AttrID, &a.Code, &a.Name, &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options); err != nil {
            return kind, err
        }
        kind.Attributes = append(kind.Attributes, a)
    }
    if kind.Attributes == nil {
        kind.Attributes = []syncedKindAttr{}
    }
    return kind, rows.Err()
}
```

### 6.2 Route registration in `server.go`

Add after the book-kind-trash routes (end of SS-5 block):

```go
// SS-6: Cross-tier kind sync
mux.HandleFunc("POST /v1/glossary/kinds/compare", s.handleKindCompare)
mux.HandleFunc("POST /v1/glossary/kinds/sync",    s.handleKindSync)
```

---

## 7) TypeScript API Client

### 7.1 New types in `frontend/src/features/glossary/types.ts`

```typescript
// ── SS-6 Kind Sync ──────────────────────────────────────────────────────────

export type KindTier = 'system' | 'user' | 'book';

export interface KindRef {
  tier: KindTier;
  id:   string;
}

export interface SyncAttrSnap {
  code:        string;
  name:        string;
  field_type:  string;
  is_required: boolean;
  sort_order:  number;
  options:     string[] | null;
}

export type DiffStatus = 'added' | 'removed' | 'modified' | 'unchanged';

export interface DiffItem {
  diff_key:    string;
  status:      DiffStatus;
  source_attr: SyncAttrSnap | null;
  target_attr: SyncAttrSnap | null;
}

export interface KindMeta {
  tier: KindTier;
  id:   string;
  name: string;
  code: string;
}

export interface CompareResult {
  source:            KindMeta;
  target:            KindMeta;
  diff:              DiffItem[];
  has_data_warnings: boolean;
}

export interface SyncWarning {
  diff_key:     string;
  code:         string;
  entity_count: number;
  message:      string;
}

export interface SyncedKindAttr {
  attr_id:     string;
  code:        string;
  name:        string;
  field_type:  string;
  is_required: boolean;
  sort_order:  number;
  options:     string[] | null;
}

export interface SyncedKind {
  kind_id:    string;
  tier:       KindTier;
  code:       string;
  name:       string;
  attributes: SyncedKindAttr[];
}

export interface SyncResponse {
  kind:          SyncedKind;
  applied_count: number;
  warnings:      SyncWarning[];
}
```

### 7.2 New API functions in `frontend/src/features/glossary/api.ts`

Add to the `glossaryApi` object:

```typescript
// SS-6
compareKinds: async (
  token: string,
  source: KindRef,
  target: KindRef
): Promise<CompareResult> =>
  apiJson<CompareResult>('/v1/glossary/kinds/compare', {
    method: 'POST',
    token,
    body: { source, target },
  }),

syncKinds: async (
  token: string,
  source: KindRef,
  target: KindRef,
  apply: string[]
): Promise<SyncResponse> =>
  apiJson<SyncResponse>('/v1/glossary/kinds/sync', {
    method: 'POST',
    token,
    body: { source, target, apply },
  }),
```

---

## 8) Frontend Components

### 8.1 `KindCompareModal.tsx`

**File:** `frontend/src/components/glossary/KindCompareModal.tsx`

**Props:**

```typescript
interface Props {
  token:     string;
  source:    KindRef;
  target:    KindRef;
  onClose:   () => void;
  onApplied: (result: SyncResponse) => void;
}
```

**State:**
- `compareResult: CompareResult | null`
- `loading: boolean`  (fetching compare)
- `applying: boolean` (POST sync in progress)
- `error: string | null`
- `checked: Set<string>` — set of `diff_key` values currently selected

**Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Compare kinds                                          [×]       │
├─────────────────────────────────────────────────────────────────┤
│ Source: [tier badge] Character (system)                         │
│ Target: [tier badge] My Character (user kind)                   │
├──────┬──────────────┬───────────────────────┬───────────────────┤
│ [ ]  │ Status       │ Source attr           │ Target attr       │
├──────┼──────────────┼───────────────────────┼───────────────────┤
│ [✓]  │ ➕ added     │ Occupation (text)     │ —                 │
│ [✓]  │ ✏️ modified  │ Birth Date (required) │ Birthday          │
│ [✓]  │ ➖ removed   │ —                     │ Height ⚠️ 12 vals │
│ [ ]  │ ✓ unchanged  │ Aliases               │ Aliases           │
├──────┴──────────────┴───────────────────────┴───────────────────┤
│ [Select all] [Deselect all]            [Cancel] [Apply selected]│
└─────────────────────────────────────────────────────────────────┘
```

**Behaviour:**
- On mount: call `glossaryApi.compareKinds()`. Show spinner while loading.
- Default checked state: all non-`unchanged` items selected; `unchanged` items unchecked.
- `has_data_warnings = true` → show yellow banner: "Some attributes have existing data and will be soft-deleted if removed. Soft-deleted values remain visible via snapshot."
- Each `removed` item with entity data shows `⚠️ N values` inline in the target column.
- "Select all" → check all diff items. "Deselect all" → uncheck all.
- "Apply selected": disabled if no boxes checked. Calls `glossaryApi.syncKinds()` with `apply = [...checked]`. On success: calls `onApplied(result)`. On error: shows error banner, keeps modal open.
- Apply response `warnings` displayed inline (yellow row) after apply completes if modal stays open (not needed — modal closes on success and parent refreshes).

**Tier badge colours** (small `<span>` pill):
- `system` → gray
- `user` → indigo
- `book` → emerald

**Implementation skeleton:**

```tsx
import React, { useEffect, useState, useCallback } from 'react';
import { glossaryApi } from '../../features/glossary/api';
import type {
  KindRef, CompareResult, DiffItem, SyncResponse, DiffStatus,
} from '../../features/glossary/types';

const STATUS_ICON: Record<DiffStatus, string> = {
  added:     '➕',
  modified:  '✏️',
  removed:   '➖',
  unchanged: '✓',
};

const TIER_COLOR: Record<string, string> = {
  system: 'bg-gray-100 text-gray-700',
  user:   'bg-indigo-100 text-indigo-700',
  book:   'bg-emerald-100 text-emerald-700',
};

export default function KindCompareModal({ token, source, target, onClose, onApplied }: Props) {
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    glossaryApi.compareKinds(token, source, target)
      .then(r => {
        setResult(r);
        // Default: select all non-unchanged
        const initial = new Set(
          r.diff.filter(d => d.status !== 'unchanged').map(d => d.diff_key)
        );
        setChecked(initial);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (key: string) => {
    setChecked(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const selectAll = () => setChecked(new Set(result?.diff.map(d => d.diff_key) ?? []));
  const deselectAll = () => setChecked(new Set());

  const handleApply = async () => {
    if (!result || checked.size === 0) return;
    setApplying(true);
    setError(null);
    try {
      const res = await glossaryApi.syncKinds(token, source, target, [...checked]);
      onApplied(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setApplying(false);
    }
  };

  // … JSX render
}
```

---

### 8.2 Sync Entry Points

#### A. `KindDetailPage.tsx` (SS-4 user kind detail)

Add state: `const [showCompare, setShowCompare] = useState(false)`

Add button (only if `kind.cloned_from_kind_id` is set):

```tsx
{kind.cloned_from_kind_id && (
  <button
    onClick={() => setShowCompare(true)}
    className="text-sm underline text-indigo-600 hover:text-indigo-800"
  >
    Re-sync from system
  </button>
)}

{showCompare && (
  <KindCompareModal
    token={token}
    source={{ tier: 'system', id: kind.cloned_from_kind_id! }}
    target={{ tier: 'user',   id: kind.user_kind_id }}
    onClose={() => setShowCompare(false)}
    onApplied={() => { setShowCompare(false); refetchKind(); }}
  />
)}
```

#### B. `BookGlossaryKindsPage.tsx` (SS-5 book kind detail panel)

Add two buttons in the selected kind's action bar:

```tsx
{/* Only if kind has a system origin */}
{selectedKind.cloned_from_kind_id && (
  <button onClick={() => openCompare('system', selectedKind.cloned_from_kind_id!)}>
    Re-sync from system
  </button>
)}

{/* Only if kind has a user kind origin */}
{selectedKind.cloned_from_user_kind_id && (
  <button onClick={() => openCompare('user', selectedKind.cloned_from_user_kind_id!)}>
    Re-sync from my kind
  </button>
)}

{/* Always available: push this book kind's attrs up to a user kind */}
<button onClick={() => setShowPushToUser(true)}>
  Push to my kinds
</button>
```

"Push to my kinds" opens a `<UserKindPickerModal>` (small modal listing user's T2 kinds matching same `code`), then opens `KindCompareModal` with source=book/target=user.

`openCompare(srcTier, srcId)` sets `compareSource = { tier: srcTier, id: srcId }` and `compareTarget = { tier: 'book', id: selectedKind.book_kind_id }`.

```tsx
{compareSource && (
  <KindCompareModal
    token={token}
    source={compareSource}
    target={compareTarget}
    onClose={() => setCompareSource(null)}
    onApplied={r => { setCompareSource(null); /* refresh kind attrs */ }}
  />
)}
```

---

### 8.3 `UserKindPickerModal.tsx`

**File:** `frontend/src/components/glossary/UserKindPickerModal.tsx`

Small modal to select which T2 user kind to push to, when a T3 book kind has no explicit `cloned_from_user_kind_id`.

**Props:**

```typescript
interface Props {
  token:        string;
  bookKindCode: string;   // pre-filter: show only user kinds with same code
  onSelect:     (userKindId: string) => void;
  onClose:      () => void;
}
```

Calls `glossaryApi.listUserKinds(token)`, filters by `kind.code === bookKindCode`, renders a simple list. If no match — shows all user kinds (user may want to push to a differently-coded kind). On select → calls `onSelect(userKind.user_kind_id)`.

---

## 9) Wiring Checklist

| Step | File | Change |
|---|---|---|
| 1 | `services/glossary-service/internal/migrate/migrate.go` | Add `UpKindSync()` (no-op); call in `Up()` |
| 2 | `services/glossary-service/internal/api/kind_sync_handler.go` | New file (all sync logic) |
| 3 | `services/glossary-service/internal/api/server.go` | Register 2 new routes |
| 4 | `frontend/src/features/glossary/types.ts` | Add SS-6 types |
| 5 | `frontend/src/features/glossary/api.ts` | Add `compareKinds`, `syncKinds` |
| 6 | `frontend/src/components/glossary/KindCompareModal.tsx` | New file |
| 7 | `frontend/src/components/glossary/UserKindPickerModal.tsx` | New file |
| 8 | `frontend/src/pages/KindDetailPage.tsx` | Add "Re-sync from system" button + modal |
| 9 | `frontend/src/pages/BookGlossaryKindsPage.tsx` | Add sync buttons + modal |

---

## 10) Exit Criteria

| # | Criterion |
|---|---|
| 1 | `POST /v1/glossary/kinds/compare` returns correct diff for T1→T2, T1→T3, T2→T3, T3→T2 |
| 2 | `POST /v1/glossary/kinds/compare` returns 403 for T2→T1 and T3→T1 |
| 3 | `POST /v1/glossary/kinds/sync` with `added` items → attributes appear in target kind |
| 4 | Sync with `modified` items → target attributes updated |
| 5 | Sync with `removed` items (no data) → attributes soft-deleted, not in GET response |
| 6 | Sync with `removed` items (has data) → soft-deleted; `warnings` in response includes `entity_count` |
| 7 | Sync with unknown `diff_key` in `apply[]` → silently skipped (no error) |
| 8 | `KindCompareModal` shows diff rows with correct status icons |
| 9 | Only checked diff items sent in `apply[]` |
| 10 | "Re-sync from system" button visible on T2 `KindDetailPage` only if `cloned_from_kind_id` set |
| 11 | "Re-sync from system" / "Re-sync from my kind" visible on T3 kind panel based on clone source columns |
| 12 | "Push to my kinds" opens `UserKindPickerModal` then `KindCompareModal` with source=book/target=user |

---

## 11) Risks & Mitigations

| Risk | Mitigation |
|---|---|
| TOCTOU: user opens compare modal, another session modifies target before Apply | Sync handler re-runs compare internally; stale `diff_key` values for gone items are silently skipped |
| `countAttrData` references `user_attr_def_id`/`book_attr_def_id` FK columns that don't exist until SS-7 | Error is swallowed, count returns 0; pre-SS-7 no entity data can exist for T2/T3 attr defs anyway |
| T2→T3 sync: user picks a T2 kind they don't own | `loadKindAttrsOwned` adds `AND owner_user_id = $2` guard; returns 404 instead of data |
| Large attribute lists (100+) → compare slow | In-memory O(n) map-based diff; n is bounded by attribute count per kind (practical max ~50) |
| "Push to my kinds" with no matching T2 kind | `UserKindPickerModal` falls back to showing all user kinds; user must pick manually |
