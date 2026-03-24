# SS-2: Soft Delete + Recycle Bin — Detailed Design

## Document Metadata

- Document ID: LW-M05-91
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Parent: `89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md` (SS-2)
- Depends on: SS-1 complete (`entity_snapshot` column must exist before SS-2)
- Summary: Full technical design for replacing hard-delete with soft-delete on `glossary_entities`, extending the recycle bin API and UI with a Glossary Entities category. Includes exact SQL, precise Go handler diffs, and frontend component specs.

---

## 1) Goal & Scope

**In scope:**
- DB migration: `deleted_at`, `permanently_deleted_at` on `glossary_entities`
- Change `deleteEntity` handler from hard DELETE to soft delete
- Add `AND deleted_at IS NULL` guard to all live entity queries
- New recycle bin handler: list trash, restore, permanent-delete flag
- New routes in `server.go`
- Frontend: `RecycleBinPage` extended with Glossary tab; `GlossaryEntityCard` delete wording updated; trash link on `GlossaryPage`

**Out of scope:**
- Soft delete for kinds / attribute definitions (SS-4, SS-5)
- Background GC for physical deletion
- Chapter soft delete

---

## 2) Existing State (precise)

### Backend — what changes

| Location | Current code | Problem |
|---|---|---|
| `entity_handler.go:756` | `DELETE FROM glossary_entities WHERE entity_id=$1 AND book_id=$2` | Hard delete; no recycle bin |
| `chapter_link_handler.go:22` `verifyEntityInBook` | `SELECT EXISTS(... WHERE entity_id=$1 AND book_id=$2)` | Returns true for soft-deleted entities — must add `AND deleted_at IS NULL` |
| `entity_handler.go:175` `loadEntityDetail` | `WHERE e.entity_id=$1 AND e.book_id=$2` | Loads soft-deleted entities — must filter |
| `entity_handler.go:~440` `listEntities` | Dynamic WHERE builder, base: `WHERE e.book_id=$1` | Lists soft-deleted entities — must add base condition |
| `export_handler.go:106/126` | `WHERE e.book_id=$1 AND e.status='active'` | Would export soft-deleted entities — must add filter |

### Frontend — what changes

| Location | Current behavior | Required change |
|---|---|---|
| `GlossaryEntityCard.tsx` | "Delete" → hard delete API call | "Move to trash" → soft delete API call; different confirmation wording |
| `RecycleBinPage.tsx` | Shows books only | Add "Glossary Entities" category tab |
| `GlossaryPage.tsx` | No trash link | Add "Trash" link at bottom |

### Pattern reference: books

Books use `lifecycle_state TEXT` ('active' | 'trashed' | 'purge_pending'). Glossary entities use a separate `status` field ('draft' | 'active' | 'inactive') for business status. To avoid conflating lifecycle with business status, glossary entities use **two timestamp columns** instead of a state enum. This is consistent with ADR-S3 in doc 89.

---

## 3) DB Migration

### 3.1 DDL

```sql
-- SS-2 migration (add to UpSoftDelete() in migrate.go)

ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS deleted_at           TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS permanently_deleted_at TIMESTAMPTZ DEFAULT NULL;

-- Partial indexes for live (non-deleted) query paths
-- Replace the non-partial indexes that would now scan deleted rows.
-- Existing indexes remain; adding narrower partial indexes for hot paths.
CREATE INDEX IF NOT EXISTS idx_ge_live_book_kind
  ON glossary_entities(book_id, kind_id)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_status
  ON glossary_entities(book_id, status)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_updated
  ON glossary_entities(book_id, updated_at DESC)
  WHERE deleted_at IS NULL;

-- Index for recycle bin queries (deleted, not yet purged)
CREATE INDEX IF NOT EXISTS idx_ge_trash_book
  ON glossary_entities(book_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;
```

### 3.2 Column semantics

| Column | Meaning |
|---|---|
| `deleted_at IS NULL` | Entity is live; appears in all normal queries |
| `deleted_at IS NOT NULL, permanently_deleted_at IS NULL` | Soft-deleted; in recycle bin; restorable |
| `permanently_deleted_at IS NOT NULL` | Flagged for permanent deletion; hidden from recycle bin UI; awaits GC |

### 3.3 SS-1 snapshot trigger interaction

When `deleteEntity` sets `deleted_at = now(), updated_at = now()`, the existing `trig_entity_self_snapshot` fires (because `updated_at` changed). The snapshot is recalculated to include the current data. This is **correct** — the recycle bin reads from the snapshot for display, so it needs an up-to-date snapshot at the moment of deletion.

No changes needed to the trigger function.

---

## 4) Backend Changes

### 4.1 New `UpSoftDelete()` in `migrate.go`

```go
const softDeleteSQL = `
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS deleted_at            TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS permanently_deleted_at TIMESTAMPTZ DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_kind
  ON glossary_entities(book_id, kind_id)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_status
  ON glossary_entities(book_id, status)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_updated
  ON glossary_entities(book_id, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_trash_book
  ON glossary_entities(book_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;
`

func UpSoftDelete(ctx context.Context, pool *pgxpool.Pool) error {
    if _, err := pool.Exec(ctx, softDeleteSQL); err != nil {
        return fmt.Errorf("migrate soft-delete: %w", err)
    }
    return nil
}
```

### 4.2 `main.go` call sequence (cumulative after SS-1 + SS-2)

```go
if err := migrate.Up(ctx, pool); err != nil { ... }
if err := migrate.Seed(ctx, pool); err != nil { ... }
if err := migrate.UpSnapshot(ctx, pool); err != nil { ... }      // SS-1
if err := migrate.BackfillSnapshots(ctx, pool); err != nil { ... } // SS-1
if err := migrate.UpSoftDelete(ctx, pool); err != nil { ... }    // SS-2
```

### 4.3 `verifyEntityInBook` — add `deleted_at IS NULL`

**File:** `chapter_link_handler.go:22`

```go
// Before:
`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2)`

// After:
`SELECT EXISTS(SELECT 1 FROM glossary_entities
               WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)`
```

This single change cascades to all 8 call sites across `chapter_link_handler.go`, `attribute_handler.go`, and `evidence_handler.go` that call `verifyEntityInBook`. No other files need changes for those handlers.

### 4.4 `loadEntityDetail` — add `deleted_at IS NULL`

**File:** `entity_handler.go:175`

```go
// Before:
`WHERE e.entity_id = $1 AND e.book_id = $2`

// After:
`WHERE e.entity_id = $1 AND e.book_id = $2 AND e.deleted_at IS NULL`
```

### 4.5 `listEntities` — add base condition

**File:** `entity_handler.go:~440` (dynamic WHERE builder)

The list handler builds a `where []string` slice and joins with `AND`. The first condition is always `e.book_id = $1`. Add `e.deleted_at IS NULL` as a second invariant base condition:

```go
// Current:
where := []string{"e.book_id = $1"}

// After:
where := []string{"e.book_id = $1", "e.deleted_at IS NULL"}
```

One-line change; argument numbering unchanged since no new parameter is added.

### 4.6 `deleteEntity` — soft delete

**File:** `entity_handler.go:754-766`

```go
// Before:
tag, err := s.pool.Exec(ctx,
    `DELETE FROM glossary_entities WHERE entity_id=$1 AND book_id=$2`,
    entityID, bookID)

// After:
tag, err := s.pool.Exec(ctx,
    `UPDATE glossary_entities
     SET deleted_at = now(), updated_at = now()
     WHERE entity_id = $1 AND book_id = $2
       AND deleted_at IS NULL`,
    entityID, bookID)
```

`RowsAffected() == 0` check remains: covers both "entity not found" and "entity already deleted" cases, both return 404. The trigger fires (updated_at changed) and refreshes the snapshot before the row is hidden.

### 4.7 `exportGlossary` — add `deleted_at IS NULL` (SS-1 + SS-2 combined)

**File:** `export_handler.go` (the refactored snapshot-based query from SS-1)

```go
// Append to the base query after SS-1 refactor:
`WHERE book_id = $1
   AND status = 'active'
   AND entity_snapshot IS NOT NULL
   AND deleted_at IS NULL`   -- added in SS-2
```

### 4.8 New file: `recycle_bin_handler.go`

#### Response type

```go
// entityTrashItem is the shape returned by the recycle bin list endpoint.
type entityTrashItem struct {
    EntityID    string          `json:"entity_id"`
    BookID      string          `json:"book_id"`
    DeletedAt   time.Time       `json:"deleted_at"`
    // Kind and display name are read from entity_snapshot to avoid joins.
    // Clients display these without requiring a separate lookup.
    KindCode    string          `json:"kind_code"`
    KindName    string          `json:"kind_name"`
    KindIcon    string          `json:"kind_icon"`
    KindColor   string          `json:"kind_color"`
    DisplayName string          `json:"display_name"`
    Status      string          `json:"status"`   // business status before deletion
}

type entityTrashListResp struct {
    Items  []entityTrashItem `json:"items"`
    Total  int               `json:"total"`
    Limit  int               `json:"limit"`
    Offset int               `json:"offset"`
}
```

#### `GET /v1/glossary/books/{book_id}/recycle-bin`

```go
func (s *Server) listEntityTrash(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok { writeError(w, 401, ...); return }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    q := r.URL.Query()
    limit  := parseIntDefault(q.Get("limit"),  20)
    offset := parseIntDefault(q.Get("offset"),  0)
    if limit > 100 { limit = 100 }

    ctx := r.Context()

    var total int
    if err := s.pool.QueryRow(ctx,
        `SELECT COUNT(*) FROM glossary_entities
         WHERE book_id=$1 AND deleted_at IS NOT NULL
           AND permanently_deleted_at IS NULL`,
        bookID).Scan(&total); err != nil {
        writeError(w, 500, "GLOSS_INTERNAL", "count failed"); return
    }

    rows, err := s.pool.Query(ctx, `
        SELECT entity_id::text, book_id::text, deleted_at, status,
               entity_snapshot->'kind'->>'code'  AS kind_code,
               entity_snapshot->'kind'->>'name'  AS kind_name,
               entity_snapshot->'kind'->>'icon'  AS kind_icon,
               entity_snapshot->'kind'->>'color' AS kind_color,
               COALESCE((
                   SELECT attr->>'original_value'
                   FROM jsonb_array_elements(entity_snapshot->'attributes') AS attr
                   WHERE attr->>'code' IN ('name','term')
                     AND attr->>'original_value' != ''
                   LIMIT 1
               ), '') AS display_name
        FROM glossary_entities
        WHERE book_id=$1 AND deleted_at IS NOT NULL
          AND permanently_deleted_at IS NULL
        ORDER BY deleted_at DESC
        LIMIT $2 OFFSET $3`,
        bookID, limit, offset)
    if err != nil {
        writeError(w, 500, "GLOSS_INTERNAL", "query failed"); return
    }
    defer rows.Close()

    items := []entityTrashItem{}
    for rows.Next() {
        var it entityTrashItem
        if err := rows.Scan(
            &it.EntityID, &it.BookID, &it.DeletedAt, &it.Status,
            &it.KindCode, &it.KindName, &it.KindIcon, &it.KindColor,
            &it.DisplayName,
        ); err != nil {
            writeError(w, 500, "GLOSS_INTERNAL", "scan failed"); return
        }
        items = append(items, it)
    }
    if err := rows.Err(); err != nil {
        writeError(w, 500, "GLOSS_INTERNAL", "rows error"); return
    }

    writeJSON(w, 200, entityTrashListResp{
        Items:  items,
        Total:  total,
        Limit:  limit,
        Offset: offset,
    })
}
```

**Note on snapshot JSON query:** `entity_snapshot->'kind'->>'code'` is a JSONB path expression supported by PostgreSQL. No GIN index needed here since we are selecting by `book_id` (B-tree indexed) and reading JSON fields from the result rows.

#### `POST /v1/glossary/books/{book_id}/recycle-bin/{entity_id}/restore`

```go
func (s *Server) restoreEntity(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok { writeError(w, 401, ...); return }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    entityID, ok := parsePathUUID(w, r, "entity_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    ctx := r.Context()
    tag, err := s.pool.Exec(ctx,
        `UPDATE glossary_entities
         SET deleted_at = NULL, updated_at = now()
         WHERE entity_id = $1 AND book_id = $2
           AND deleted_at IS NOT NULL
           AND permanently_deleted_at IS NULL`,
        entityID, bookID)
    if err != nil {
        writeError(w, 500, "GLOSS_INTERNAL", "restore failed"); return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, 404, "GLOSS_NOT_FOUND", "entity not in trash"); return
    }
    w.WriteHeader(http.StatusNoContent)
}
```

After restore, `updated_at = now()` triggers the snapshot recalculation. The entity is immediately visible in the live list again.

#### `DELETE /v1/glossary/books/{book_id}/recycle-bin/{entity_id}`

Flags the entity for permanent deletion. Does **not** DELETE the row (GC is out of scope).

```go
func (s *Server) purgeEntity(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok { writeError(w, 401, ...); return }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    entityID, ok := parsePathUUID(w, r, "entity_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    ctx := r.Context()
    tag, err := s.pool.Exec(ctx,
        `UPDATE glossary_entities
         SET permanently_deleted_at = now()
         WHERE entity_id = $1 AND book_id = $2
           AND deleted_at IS NOT NULL
           AND permanently_deleted_at IS NULL`,
        entityID, bookID)
    if err != nil {
        writeError(w, 500, "GLOSS_INTERNAL", "purge failed"); return
    }
    if tag.RowsAffected() == 0 {
        writeError(w, 404, "GLOSS_NOT_FOUND", "entity not in trash"); return
    }
    w.WriteHeader(http.StatusNoContent)
}
```

### 4.9 New routes in `server.go`

```go
// Inside the books/{book_id} router block, alongside the existing /export route:
r.Route("/recycle-bin", func(r chi.Router) {
    r.Get("/", s.listEntityTrash)
    r.Post("/{entity_id}/restore", s.restoreEntity)
    r.Delete("/{entity_id}", s.purgeEntity)
})
```

---

## 5) Frontend Changes

### 5.1 `glossaryApi.ts` — new recycle bin functions

```typescript
// Add to existing glossaryApi object:

listEntityTrash(
  bookId: string,
  token: string,
  params: { limit?: number; offset?: number } = {},
): Promise<{ items: EntityTrashItem[]; total: number; limit: number; offset: number }> {
  const qs = new URLSearchParams();
  if (params.limit)  qs.set('limit',  String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  const q = qs.toString();
  return apiJson(
    `${BASE}/books/${bookId}/recycle-bin${q ? '?' + q : ''}`,
    { token },
  );
},

restoreEntity(bookId: string, entityId: string, token: string): Promise<void> {
  return apiJson<void>(
    `${BASE}/books/${bookId}/recycle-bin/${entityId}/restore`,
    { method: 'POST', token },
  );
},

purgeEntity(bookId: string, entityId: string, token: string): Promise<void> {
  return apiJson<void>(
    `${BASE}/books/${bookId}/recycle-bin/${entityId}`,
    { method: 'DELETE', token },
  );
},
```

New type in `types.ts`:

```typescript
export type EntityTrashItem = {
  entity_id: string;
  book_id: string;
  deleted_at: string;      // ISO timestamp
  kind_code: string;
  kind_name: string;
  kind_icon: string;
  kind_color: string;
  display_name: string;
  status: string;
};
```

### 5.2 `GlossaryEntityCard.tsx` — wording change + API call

Two changes:
1. Confirmation text: "Delete" → "Move to trash"
2. No behavior change — still calls `onDelete(entityId)` which the parent maps to `glossaryApi.deleteEntity(...)`. The API call is unchanged (same endpoint, now soft-deletes on the backend). **No frontend code change needed for the delete call itself.**

Only the confirmation dialog wording changes:

```tsx
// Before (confirmation state):
<button onClick={() => onDelete(entity.entity_id)}>Delete</button>

// After:
<button onClick={() => onDelete(entity.entity_id)}>Move to trash</button>
```

Also update the tooltip/label on the delete trigger button from "Delete" to "Move to trash".

### 5.3 `GlossaryPage.tsx` — trash link

Add a small link at the bottom of the page, below the entity list:

```tsx
// Below the entity list section, before closing the main div:
<div className="mt-4 flex justify-end">
  <Link
    to={`/books/${bookId}/glossary/trash`}
    className="text-xs text-muted-foreground underline hover:text-foreground"
  >
    View trash
  </Link>
</div>
```

Route `/books/:bookId/glossary/trash` → `GlossaryTrashPage` (§5.5).

### 5.4 `RecycleBinPage.tsx` — extend with Glossary tab

The current page shows books only. Extend with a two-tab layout: **Books** (existing) and **Glossary Entities** (new).

The Glossary tab loads from all of the user's books via a fan-out. This avoids adding cross-book endpoints to the glossary-service.

```tsx
// RecycleBinPage.tsx — restructured (full component)
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { glossaryApi, type EntityTrashItem } from '@/features/glossary/api';

type Tab = 'books' | 'glossary';

export function RecycleBinPage() {
  const { accessToken } = useAuth();
  const [tab, setTab]   = useState<Tab>('books');

  // ── Books tab state ────────────────────────────────────────────
  const [bookItems, setBookItems]   = useState<Book[]>([]);
  const [bookError, setBookError]   = useState('');

  const loadBooks = async () => {
    if (!accessToken) return;
    try {
      const res = await booksApi.listTrash(accessToken);
      setBookItems(res.items);
      setBookError('');
    } catch (e) { setBookError((e as Error).message); }
  };

  // ── Glossary tab state ─────────────────────────────────────────
  const [glossaryItems, setGlossaryItems] = useState<EntityTrashItem[]>([]);
  const [glossaryError, setGlossaryError] = useState('');
  const [glossaryLoading, setGlossaryLoading] = useState(false);

  const loadGlossary = async () => {
    if (!accessToken) return;
    setGlossaryLoading(true);
    setGlossaryError('');
    try {
      // Fan-out: load all user's books, then fetch trash per book
      const booksRes = await booksApi.listBooks(accessToken);
      const results = await Promise.all(
        booksRes.items.map((b) =>
          glossaryApi
            .listEntityTrash(b.book_id, accessToken, { limit: 100 })
            .then((r) => r.items)
            .catch(() => [] as EntityTrashItem[]),
        ),
      );
      setGlossaryItems(results.flat().sort(
        (a, b) => new Date(b.deleted_at).getTime() - new Date(a.deleted_at).getTime(),
      ));
    } catch (e) { setGlossaryError((e as Error).message); }
    finally { setGlossaryLoading(false); }
  };

  useEffect(() => { void loadBooks(); }, [accessToken]);

  useEffect(() => {
    if (tab === 'glossary') void loadGlossary();
  }, [tab, accessToken]);

  // ── Restore / Purge ────────────────────────────────────────────
  const restoreBook  = async (bookId: string) => {
    if (!accessToken) return;
    await booksApi.restoreBook(accessToken, bookId);
    void loadBooks();
  };
  const purgeBook    = async (bookId: string) => {
    if (!accessToken) return;
    await booksApi.purgeBook(accessToken, bookId);
    void loadBooks();
  };
  const restoreEntity = async (item: EntityTrashItem) => {
    if (!accessToken) return;
    await glossaryApi.restoreEntity(item.book_id, item.entity_id, accessToken);
    void loadGlossary();
  };
  const purgeEntity  = async (item: EntityTrashItem) => {
    if (!accessToken) return;
    await glossaryApi.purgeEntity(item.book_id, item.entity_id, accessToken);
    void loadGlossary();
  };

  const tabClass = (t: Tab) =>
    `px-3 py-1.5 text-sm font-medium rounded-t border-b-2 transition-colors ${
      tab === t
        ? 'border-foreground text-foreground'
        : 'border-transparent text-muted-foreground hover:text-foreground'
    }`;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Recycle bin</h1>
        <Link to="/books" className="text-sm underline">Back to books</Link>
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 border-b">
        <button className={tabClass('books')}    onClick={() => setTab('books')}>
          Books
        </button>
        <button className={tabClass('glossary')} onClick={() => setTab('glossary')}>
          Glossary Entities
        </button>
      </div>

      {/* Books tab */}
      {tab === 'books' && (
        <>
          {bookError && <p className="text-sm text-destructive">{bookError}</p>}
          <ul className="space-y-2">
            {bookItems.map((b) => (
              <li key={b.book_id} className="rounded border p-3 text-sm">
                <p className="font-medium">{b.title}</p>
                <div className="mt-2 flex gap-3">
                  <button className="underline" onClick={() => void restoreBook(b.book_id)}>Restore</button>
                  <button className="underline text-destructive" onClick={() => void purgeBook(b.book_id)}>
                    Delete permanently
                  </button>
                </div>
              </li>
            ))}
            {bookItems.length === 0 && (
              <p className="text-sm text-muted-foreground">No books in trash.</p>
            )}
          </ul>
        </>
      )}

      {/* Glossary tab */}
      {tab === 'glossary' && (
        <>
          {glossaryError && <p className="text-sm text-destructive">{glossaryError}</p>}
          {glossaryLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          <ul className="space-y-2">
            {glossaryItems.map((it) => (
              <li key={it.entity_id} className="rounded border p-3 text-sm">
                <div className="flex items-center gap-2">
                  {/* Kind color dot */}
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: it.kind_color }}
                  />
                  <p className="font-medium">{it.display_name || '(unnamed)'}</p>
                  <span className="ml-1 text-xs text-muted-foreground">{it.kind_name}</span>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Deleted {new Date(it.deleted_at).toLocaleDateString()}
                </p>
                <div className="mt-2 flex gap-3">
                  <button className="underline text-sm" onClick={() => void restoreEntity(it)}>
                    Restore
                  </button>
                  <button className="underline text-sm text-destructive" onClick={() => void purgeEntity(it)}>
                    Delete permanently
                  </button>
                </div>
              </li>
            ))}
            {!glossaryLoading && glossaryItems.length === 0 && (
              <p className="text-sm text-muted-foreground">No glossary entities in trash.</p>
            )}
          </ul>
        </>
      )}
    </div>
  );
}
```

### 5.5 New page: `GlossaryTrashPage.tsx`

Route: `/books/:bookId/glossary/trash`. Provides book-scoped trash view accessible directly from `GlossaryPage`.

```tsx
// frontend/src/pages/GlossaryTrashPage.tsx
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { glossaryApi, type EntityTrashItem } from '@/features/glossary/api';
import { KindBadge } from '@/features/glossary/components/KindBadge';

export function GlossaryTrashPage() {
  const { bookId } = useParams<{ bookId: string }>();
  const { accessToken } = useAuth();
  const [items, setItems]   = useState<EntityTrashItem[]>([]);
  const [error, setError]   = useState('');

  const load = async () => {
    if (!accessToken || !bookId) return;
    try {
      const res = await glossaryApi.listEntityTrash(bookId, accessToken);
      setItems(res.items);
      setError('');
    } catch (e) { setError((e as Error).message); }
  };

  useEffect(() => { void load(); }, [accessToken, bookId]);

  const restore = async (item: EntityTrashItem) => {
    if (!accessToken || !bookId) return;
    await glossaryApi.restoreEntity(bookId, item.entity_id, accessToken);
    void load();
  };

  const purge = async (item: EntityTrashItem) => {
    if (!accessToken || !bookId) return;
    await glossaryApi.purgeEntity(bookId, item.entity_id, accessToken);
    void load();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Glossary trash</h1>
        <Link to={`/books/${bookId}/glossary`} className="text-sm underline">
          Back to glossary
        </Link>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.entity_id} className="rounded border p-3 text-sm">
            <div className="flex items-center gap-2">
              <KindBadge code={it.kind_code} name={it.kind_name}
                         icon={it.kind_icon} color={it.kind_color} />
              <span className="font-medium">{it.display_name || '(unnamed)'}</span>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Deleted {new Date(it.deleted_at).toLocaleDateString()}
            </p>
            <div className="mt-2 flex gap-3">
              <button className="underline" onClick={() => void restore(it)}>Restore</button>
              <button className="underline text-destructive" onClick={() => void purge(it)}>
                Delete permanently
              </button>
            </div>
          </li>
        ))}
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">Trash is empty.</p>
        )}
      </ul>
    </div>
  );
}
```

### 5.6 `App.tsx` — new route

```tsx
import { GlossaryTrashPage } from './pages/GlossaryTrashPage';

// Add to route tree (inside RequireAuth):
<Route path="/books/:bookId/glossary/trash"
       element={<RequireAuth><GlossaryTrashPage /></RequireAuth>} />
```

---

## 6) Query Diff Summary (all files)

| File | Line(s) | Change |
|---|---|---|
| `migrate.go` | new | Add `UpSoftDelete()` |
| `main.go` | after SS-1 calls | Add `migrate.UpSoftDelete(ctx, pool)` |
| `chapter_link_handler.go` | 22 | `verifyEntityInBook`: add `AND deleted_at IS NULL` |
| `entity_handler.go` | 175 | `loadEntityDetail`: add `AND e.deleted_at IS NULL` |
| `entity_handler.go` | ~442 | `listEntities` WHERE base: add `"e.deleted_at IS NULL"` |
| `entity_handler.go` | 756 | `deleteEntity`: `DELETE` → `UPDATE SET deleted_at = now(), updated_at = now()` |
| `export_handler.go` | baseSQL | Add `AND deleted_at IS NULL` (also combines with SS-1 snapshot query) |
| `recycle_bin_handler.go` | new file | `listEntityTrash`, `restoreEntity`, `purgeEntity` |
| `server.go` | new routes | Add `/recycle-bin` route block |
| `frontend/src/features/glossary/api.ts` | new functions | `listEntityTrash`, `restoreEntity`, `purgeEntity` |
| `frontend/src/features/glossary/types.ts` | new type | `EntityTrashItem` |
| `frontend/src/features/glossary/components/GlossaryEntityCard.tsx` | confirm label | "Delete" → "Move to trash" |
| `frontend/src/pages/GlossaryPage.tsx` | bottom | Add "View trash" link |
| `frontend/src/pages/RecycleBinPage.tsx` | full rewrite | Add category tabs; Books + Glossary Entities |
| `frontend/src/pages/GlossaryTrashPage.tsx` | new file | Book-scoped trash page |
| `frontend/src/App.tsx` | new route | `/books/:bookId/glossary/trash` |

---

## 7) Test Plan

### Backend tests

| Test | What to assert |
|---|---|
| `TestSoftDeleteHidesEntity` | After delete, `GET .../entities/{id}` returns 404; `GET .../entities` list doesn't include the entity. |
| `TestSoftDeletePreservesSubResources` | After delete, `attribute_translations` and `evidences` rows still exist in DB (no cascade). |
| `TestVerifyEntityInBookRejectsSoftDeleted` | After delete, any sub-resource handler (e.g. `POST .../evidences`) for that entity returns 404 (via `verifyEntityInBook`). |
| `TestListTrashContainsDeletedEntity` | After delete, `GET .../recycle-bin` returns the entity with correct `kind_code`, `display_name`, `deleted_at`. |
| `TestListTrashExcludesPermanentlyDeleted` | After purge, entity absent from `GET .../recycle-bin`. |
| `TestRestoreEntityMakesLive` | After restore, entity appears in `GET .../entities` list again; `GET .../entities/{id}` returns 200. |
| `TestRestoreNonTrashedReturns404` | Restore a live entity → 404. |
| `TestPurgeNonTrashedReturns404` | Purge a live entity → 404. |
| `TestDeleteAlreadyDeletedReturns404` | Second soft delete on same entity → 404 (because first set `deleted_at IS NOT NULL`, second `WHERE deleted_at IS NULL` matches 0 rows). |
| `TestExportExcludesSoftDeleted` | After delete, entity absent from `GET /export`. |
| `TestSnapshotUpdatedOnDelete` | After soft delete, `entity_snapshot` is recalculated (trigger fired on `updated_at` change). `entity_snapshot->>'snapshot_at'` > `entity_snapshot->>'updated_at'` of the row before deletion. |
| `TestTrashListPagination` | Create 5 entities, delete all, `GET .../recycle-bin?limit=2&offset=0` returns 2 items with `total=5`. |

### Frontend tests

| Test | What to assert |
|---|---|
| `RecycleBinPage` tabs render | Both "Books" and "Glossary Entities" tabs visible. |
| Glossary tab loads entities | Mock `glossaryApi.listEntityTrash` returns 1 item → item visible in Glossary tab. |
| Restore calls correct API | Click Restore → `glossaryApi.restoreEntity` called with correct `book_id` + `entity_id`. |
| Purge calls correct API | Click "Delete permanently" → `glossaryApi.purgeEntity` called. |
| `GlossaryEntityCard` wording | Confirmation button text is "Move to trash" not "Delete". |

---

## 8) Edge Cases & Risks

| Scenario | Handling |
|---|---|
| User deletes entity then immediately tries to access a sub-resource (race condition) | `verifyEntityInBook` adds `AND deleted_at IS NULL` → returns 404. Sub-resources are unaffected in DB but inaccessible via API. |
| Fan-out in RecycleBinPage with many books (>20) | `Promise.all` fires all in parallel; server handles concurrent requests normally. For very large numbers, add a cap or lazy-load per book (future UX polish). |
| `entity_snapshot IS NULL` in trash list query | Existing entities created before SS-1 may have no snapshot until backfill runs. The JSON path expressions return NULL. `COALESCE(... '', '')` handles gracefully — display_name shows '(unnamed)', kind fields show empty string. Backfill in SS-1 ensures this is rare in practice. |
| Restore after kind soft-deleted (SS-4/SS-5 scenario) | Entity is restored but its kind is in trash. Entity detail falls back to snapshot for kind display (SS-1 design). No error on restore. |
| Concurrent restore + purge | Both set different columns (`deleted_at = NULL` vs `permanently_deleted_at = now()`). PG row-level locking prevents split-brain. One will update 0 rows (returns 404). |

---

## 9) Files to Create / Modify

### Create

| File | Purpose |
|---|---|
| `services/glossary-service/internal/api/recycle_bin_handler.go` | `listEntityTrash`, `restoreEntity`, `purgeEntity` handlers |
| `frontend/src/pages/GlossaryTrashPage.tsx` | Book-scoped trash page |

### Modify

| File | Change summary |
|---|---|
| `services/glossary-service/internal/migrate/migrate.go` | Add `softDeleteSQL` const + `UpSoftDelete()` |
| `services/glossary-service/cmd/server/main.go` | Call `migrate.UpSoftDelete` |
| `services/glossary-service/internal/api/chapter_link_handler.go` | 1-line fix: `verifyEntityInBook` |
| `services/glossary-service/internal/api/entity_handler.go` | 3 query changes + delete handler |
| `services/glossary-service/internal/api/export_handler.go` | Add `AND deleted_at IS NULL` |
| `services/glossary-service/internal/api/server.go` | Add recycle bin routes |
| `frontend/src/features/glossary/api.ts` | Add 3 recycle bin functions |
| `frontend/src/features/glossary/types.ts` | Add `EntityTrashItem` |
| `frontend/src/features/glossary/components/GlossaryEntityCard.tsx` | Wording change |
| `frontend/src/pages/GlossaryPage.tsx` | Add trash link |
| `frontend/src/pages/RecycleBinPage.tsx` | Full rewrite with tabs |
| `frontend/src/App.tsx` | Add trash route |

---

## 10) Exit Criteria

- [ ] `UpSoftDelete()` runs without error on fresh DB and on existing DB with entities.
- [ ] Deleting entity returns 204; entity absent from list/detail; sub-resources inaccessible.
- [ ] Deleted entity rows still exist in DB with `deleted_at IS NOT NULL`.
- [ ] `GET .../recycle-bin` returns deleted entities with correct snapshot fields.
- [ ] Restore: entity reappears in live list; `deleted_at` is NULL again.
- [ ] Purge: entity absent from recycle bin; row has `permanently_deleted_at IS NOT NULL`.
- [ ] All 12 backend tests pass (`go test ./...`).
- [ ] RecycleBinPage renders two category tabs; Glossary tab shows deleted entities.
- [ ] GlossaryTrashPage loads and shows correct entities; restore/purge work.
- [ ] `npx tsc --noEmit` passes.
- [ ] All existing SP-1–SP-5 tests still pass.

---

## 11) References

- `docs/03_planning/89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md` — SS-2 overview, ADR-S3
- `docs/03_planning/90_SS1_SNAPSHOT_FOUNDATION_DETAILED_DESIGN.md` — SS-1 (snapshot dependency)
- `services/glossary-service/internal/api/chapter_link_handler.go:17-24` — `verifyEntityInBook`
- `services/glossary-service/internal/api/entity_handler.go:736-766` — current hard-delete handler
- `frontend/src/pages/RecycleBinPage.tsx` — existing recycle bin (books only)
- `frontend/src/features/books/api.ts` — `listTrash`, `restoreBook`, `purgeBook` pattern
