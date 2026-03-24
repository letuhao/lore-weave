# SS-1: Snapshot Foundation — Detailed Design

## Document Metadata

- Document ID: LW-M05-90
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Tech Lead
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24`89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md` (SS-1)
- Summary: Full technical design for the entity_snapshot JSONB column, PL/pgSQL recalculation function, 5 database triggers, idempotent backfill, and export handler refactor. Ready for implementation.

---

## 1) Goal & Scope

Add a **self-contained JSON snapshot** to every `glossary_entities` row. The snapshot is kept up-to-date automatically by PG triggers whenever any sub-table (attribute values, translations, evidences, chapter links) changes. The `GET /export` handler is simplified to read from the snapshot rather than running 5 sequential queries.

**In scope:**
- DB migration: `entity_snapshot JSONB` column
- PL/pgSQL function `recalculate_entity_snapshot(UUID)`
- 5 trigger functions + 5 triggers
- Idempotent backfill
- Refactor `export_handler.go`
- Unit tests for snapshot content, trigger coverage, and export output parity

**Out of scope:**
- T2/T3 kind support in the snapshot (added in SS-7)
- Soft delete filtering (added in SS-2)
- Any new API endpoint

---

## 2) Current State (before SS-1)

| File | Relevant detail |
|---|---|
| `migrate.go` | Single `schemaSQL` const + `Up()` + `Seed()`. All DDL is `CREATE TABLE IF NOT EXISTS`. |
| `glossary_entities` | 7 columns: `entity_id`, `book_id`, `kind_id`, `status`, `tags`, `created_at`, `updated_at`. No snapshot column. |
| `export_handler.go` | 5 sequential `pool.Query` calls → in-memory assembly → `writeJSON`. ~370 lines. |

---

## 3) Migration Design

### 3.1 Column Addition

```sql
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS entity_snapshot JSONB;
```

`IF NOT EXISTS` makes this safe to re-run on every startup. Column starts as `NULL` for all existing rows; backfill (§6) fills them.

### 3.2 Snapshot JSON Schema

```jsonc
{
  "schema_version": "1.0",
  "entity_id":  "<uuid>",
  "book_id":    "<uuid>",
  "kind": {
    "source": "system",          // "user" | "book" added in SS-7
    "ref_id": "<uuid>",
    "code":   "character",
    "name":   "Character",
    "icon":   "user",
    "color":  "#6366f1"
  },
  "status": "draft",
  "tags":   ["tag-a"],
  "attributes": [
    {
      "attr_def_source":  "system",   // "user" | "book" added in SS-7
      "attr_def_ref_id":  "<uuid>",
      "attr_value_id":    "<uuid>",
      "code":             "name",
      "name":             "Name",
      "field_type":       "text",
      "sort_order":       0,
      "original_language":"zh",
      "original_value":   "李莫愁",
      "translations": [
        {
          "translation_id": "<uuid>",
          "language_code":  "en",
          "value":          "Li Mochou",
          "confidence":     "verified"
        }
      ],
      "evidences": [
        {
          "evidence_id":       "<uuid>",
          "evidence_type":     "quote",
          "original_language": "zh",
          "original_text":     "李莫愁冷笑一声",
          "chapter_id":        "<uuid-or-null>",
          "chapter_title":     "Chapter 3",
          "block_or_line":     "paragraph 12",
          "note":              null
        }
      ]
    }
  ],
  "chapter_links": [
    {
      "link_id":       "<uuid>",
      "chapter_id":    "<uuid>",
      "chapter_title": "Chapter 3",
      "chapter_index": 3,
      "relevance":     "major",
      "note":          null
    }
  ],
  "updated_at":  "2026-03-25T10:00:00Z",
  "snapshot_at": "2026-03-25T10:00:01Z"
}
```

**Design notes:**
- `schema_version` allows future migrations to detect stale snapshots.
- `kind.source` / `attr_def_source` are `"system"` for all existing data. SS-7 extends these values.
- `attributes` are ordered by `attr_def.sort_order`.
- `chapter_links` are ordered by `chapter_index NULLS LAST, added_at`.
- `translations` are ordered by `language_code` (deterministic).
- `evidences` are ordered by `created_at`.
- Null UUIDs (e.g. `evidence.chapter_id`) are serialised as JSON `null`.

---

## 4) PL/pgSQL Recalculation Function

### 4.1 Full Function

```sql
CREATE OR REPLACE FUNCTION recalculate_entity_snapshot(p_entity_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_snapshot JSONB;
BEGIN
  -- Build the complete snapshot in one aggregation query.
  -- Only handles T1 (system) kinds in SS-1; SS-7 extends for T2/T3.
  SELECT jsonb_build_object(
    'schema_version', '1.0',
    'entity_id',      e.entity_id::text,
    'book_id',        e.book_id::text,
    'kind', jsonb_build_object(
      'source', 'system',
      'ref_id', k.kind_id::text,
      'code',   k.code,
      'name',   k.name,
      'icon',   k.icon,
      'color',  k.color
    ),
    'status', e.status,
    'tags',   to_jsonb(e.tags),

    'attributes', COALESCE((
      SELECT jsonb_agg(
        jsonb_build_object(
          'attr_def_source',   'system',
          'attr_def_ref_id',   ad.attr_def_id::text,
          'attr_value_id',     av.attr_value_id::text,
          'code',              ad.code,
          'name',              ad.name,
          'field_type',        ad.field_type,
          'sort_order',        ad.sort_order,
          'original_language', av.original_language,
          'original_value',    COALESCE(av.original_value, ''),
          'translations', COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'translation_id', t.translation_id::text,
                'language_code',  t.language_code,
                'value',          t.value,
                'confidence',     t.confidence
              ) ORDER BY t.language_code
            )
            FROM attribute_translations t
            WHERE t.attr_value_id = av.attr_value_id
          ), '[]'::jsonb),
          'evidences', COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'evidence_id',       ev.evidence_id::text,
                'evidence_type',     ev.evidence_type,
                'original_language', ev.original_language,
                'original_text',     ev.original_text,
                'chapter_id',        ev.chapter_id::text,
                'chapter_title',     ev.chapter_title,
                'block_or_line',     ev.block_or_line,
                'note',              ev.note
              ) ORDER BY ev.created_at
            )
            FROM evidences ev
            WHERE ev.attr_value_id = av.attr_value_id
          ), '[]'::jsonb)
        ) ORDER BY ad.sort_order
      )
      FROM entity_attribute_values av
      JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
      WHERE av.entity_id = p_entity_id
    ), '[]'::jsonb),

    'chapter_links', COALESCE((
      SELECT jsonb_agg(
        jsonb_build_object(
          'link_id',       cl.link_id::text,
          'chapter_id',    cl.chapter_id::text,
          'chapter_title', cl.chapter_title,
          'chapter_index', cl.chapter_index,
          'relevance',     cl.relevance,
          'note',          cl.note
        ) ORDER BY cl.chapter_index NULLS LAST, cl.added_at
      )
      FROM chapter_entity_links cl
      WHERE cl.entity_id = p_entity_id
    ), '[]'::jsonb),

    'updated_at',  e.updated_at,
    'snapshot_at', now()
  )
  INTO v_snapshot
  FROM glossary_entities e
  JOIN entity_kinds k ON k.kind_id = e.kind_id
  WHERE e.entity_id = p_entity_id;

  -- Entity not found (concurrent delete): silently return.
  IF v_snapshot IS NULL THEN
    RETURN;
  END IF;

  -- Only write if the snapshot actually changed.
  -- This also prevents the trig_entity_self_snapshot trigger from
  -- entering an infinite loop (see §5.5).
  UPDATE glossary_entities
  SET entity_snapshot = v_snapshot
  WHERE entity_id = p_entity_id
    AND entity_snapshot IS DISTINCT FROM v_snapshot;
END;
$$;
```

### 4.2 Why `IS DISTINCT FROM` on final UPDATE

When `recalculate_entity_snapshot` calls `UPDATE glossary_entities SET entity_snapshot = ...`, it fires `trig_entity_self_snapshot` (§5.5). That trigger guards against infinite recursion by checking whether `status / tags / kind_id` changed. Since only `entity_snapshot` is written, those columns are identical and the guard short-circuits — **no recursion occurs**.

However, as an additional safety measure, the `AND entity_snapshot IS DISTINCT FROM v_snapshot` condition means that if the snapshot content is already up-to-date (e.g. a no-op re-run after backfill), the `UPDATE` affects 0 rows and fires no trigger at all.

---

## 5) Trigger Design

Five triggers cover every table whose content appears in the snapshot.

### 5.1 entity_attribute_values

```sql
CREATE OR REPLACE FUNCTION trig_fn_eav_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM recalculate_entity_snapshot(
    CASE WHEN TG_OP = 'DELETE' THEN OLD.entity_id ELSE NEW.entity_id END
  );
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trig_eav_snapshot ON entity_attribute_values;
CREATE TRIGGER trig_eav_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON entity_attribute_values
  FOR EACH ROW EXECUTE FUNCTION trig_fn_eav_snapshot();
```

### 5.2 attribute_translations

`attribute_translations` has no direct `entity_id` — must traverse `entity_attribute_values`.

```sql
CREATE OR REPLACE FUNCTION trig_fn_trans_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_entity_id UUID;
BEGIN
  SELECT entity_id INTO v_entity_id
  FROM entity_attribute_values
  WHERE attr_value_id = CASE WHEN TG_OP = 'DELETE'
                             THEN OLD.attr_value_id
                             ELSE NEW.attr_value_id END;
  IF v_entity_id IS NOT NULL THEN
    PERFORM recalculate_entity_snapshot(v_entity_id);
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trig_trans_snapshot ON attribute_translations;
CREATE TRIGGER trig_trans_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON attribute_translations
  FOR EACH ROW EXECUTE FUNCTION trig_fn_trans_snapshot();
```

### 5.3 evidences

Same 2-hop pattern as attribute_translations.

```sql
CREATE OR REPLACE FUNCTION trig_fn_evid_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_entity_id UUID;
BEGIN
  SELECT entity_id INTO v_entity_id
  FROM entity_attribute_values
  WHERE attr_value_id = CASE WHEN TG_OP = 'DELETE'
                             THEN OLD.attr_value_id
                             ELSE NEW.attr_value_id END;
  IF v_entity_id IS NOT NULL THEN
    PERFORM recalculate_entity_snapshot(v_entity_id);
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trig_evid_snapshot ON evidences;
CREATE TRIGGER trig_evid_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON evidences
  FOR EACH ROW EXECUTE FUNCTION trig_fn_evid_snapshot();
```

### 5.4 chapter_entity_links

```sql
CREATE OR REPLACE FUNCTION trig_fn_cel_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM recalculate_entity_snapshot(
    CASE WHEN TG_OP = 'DELETE' THEN OLD.entity_id ELSE NEW.entity_id END
  );
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trig_cel_snapshot ON chapter_entity_links;
CREATE TRIGGER trig_cel_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON chapter_entity_links
  FOR EACH ROW EXECUTE FUNCTION trig_fn_cel_snapshot();
```

### 5.5 glossary_entities (self-trigger, infinite-loop analysis)

When the application calls `PATCH .../entities/:id` to update `status` or `tags`, the snapshot must be refreshed. However, `recalculate_entity_snapshot` itself calls `UPDATE glossary_entities SET entity_snapshot = ...`, which would fire this trigger again.

**Guard:** only recalculate when a *business* column changed, never when only `entity_snapshot` changed.

```sql
CREATE OR REPLACE FUNCTION trig_fn_entity_self_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- Only recalculate when a business-field changed.
  -- Prevents infinite loop when recalculate_entity_snapshot
  -- writes back to entity_snapshot (which changes only that column).
  IF NEW.status     IS DISTINCT FROM OLD.status
  OR NEW.tags       IS DISTINCT FROM OLD.tags
  OR NEW.kind_id    IS DISTINCT FROM OLD.kind_id
  OR NEW.updated_at IS DISTINCT FROM OLD.updated_at
  THEN
    PERFORM recalculate_entity_snapshot(NEW.entity_id);
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trig_entity_self_snapshot ON glossary_entities;
CREATE TRIGGER trig_entity_self_snapshot
  AFTER UPDATE ON glossary_entities
  FOR EACH ROW EXECUTE FUNCTION trig_fn_entity_self_snapshot();
```

**Call chain analysis (no recursion):**

```
App: UPDATE glossary_entities SET status='active' WHERE entity_id=X
  → trig_entity_self_snapshot fires (NEW.status ≠ OLD.status)
    → recalculate_entity_snapshot(X)
      → UPDATE glossary_entities SET entity_snapshot=... WHERE entity_id=X
        → trig_entity_self_snapshot fires again
          → NEW.status == OLD.status, NEW.tags == OLD.tags, NEW.kind_id == OLD.kind_id
          → NEW.updated_at == OLD.updated_at (snapshot update doesn't touch updated_at)
          → Guard fails → RETURN NULL immediately  ✓  (no recursion)
```

---

## 6) Backfill Strategy

### 6.1 Go function in migrate package

```go
// BackfillSnapshots populates entity_snapshot for any entity where it is NULL.
// Safe to call repeatedly (idempotent); skips entities that already have a snapshot.
func BackfillSnapshots(ctx context.Context, pool *pgxpool.Pool) error {
    rows, err := pool.Query(ctx,
        `SELECT entity_id FROM glossary_entities WHERE entity_snapshot IS NULL`)
    if err != nil {
        return fmt.Errorf("backfill list: %w", err)
    }
    defer rows.Close()

    var ids []uuid.UUID
    for rows.Next() {
        var id uuid.UUID
        if err := rows.Scan(&id); err != nil {
            return fmt.Errorf("backfill scan: %w", err)
        }
        ids = append(ids, id)
    }
    if err := rows.Err(); err != nil {
        return err
    }

    for _, id := range ids {
        if _, err := pool.Exec(ctx,
            `SELECT recalculate_entity_snapshot($1)`, id); err != nil {
            return fmt.Errorf("backfill entity %s: %w", id, err)
        }
    }
    return nil
}
```

### 6.2 main.go call sequence

```go
// existing:
if err := migrate.Up(ctx, pool); err != nil { ... }
if err := migrate.Seed(ctx, pool); err != nil { ... }

// new (SS-1):
if err := migrate.UpSnapshot(ctx, pool); err != nil { ... }
if err := migrate.BackfillSnapshots(ctx, pool); err != nil { ... }
```

### 6.3 `UpSnapshot` in migrate package

```go
const snapshotSQL = `
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS entity_snapshot JSONB;

CREATE OR REPLACE FUNCTION recalculate_entity_snapshot(p_entity_id UUID)
RETURNS void LANGUAGE plpgsql AS $fn$
  -- (full function body from §4.1)
$fn$;

CREATE OR REPLACE FUNCTION trig_fn_eav_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $fn$
  -- (body from §5.1)
$fn$;

-- (repeat for trig_fn_trans_snapshot, trig_fn_evid_snapshot,
--  trig_fn_cel_snapshot, trig_fn_entity_self_snapshot)

DROP TRIGGER IF EXISTS trig_eav_snapshot    ON entity_attribute_values;
DROP TRIGGER IF EXISTS trig_trans_snapshot  ON attribute_translations;
DROP TRIGGER IF EXISTS trig_evid_snapshot   ON evidences;
DROP TRIGGER IF EXISTS trig_cel_snapshot    ON chapter_entity_links;
DROP TRIGGER IF EXISTS trig_entity_self_snapshot ON glossary_entities;

CREATE TRIGGER trig_eav_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON entity_attribute_values
  FOR EACH ROW EXECUTE FUNCTION trig_fn_eav_snapshot();

-- (repeat for remaining 4 triggers)
`

func UpSnapshot(ctx context.Context, pool *pgxpool.Pool) error {
    if _, err := pool.Exec(ctx, snapshotSQL); err != nil {
        return fmt.Errorf("migrate snapshot: %w", err)
    }
    return nil
}
```

**Note on `DROP TRIGGER IF EXISTS`:** This runs on every startup, but is safe because `CREATE OR REPLACE FUNCTION` and `DROP/CREATE TRIGGER` are fast metadata operations. Alternatives (check-before-create) are more complex without meaningful gain.

---

## 7) Export Handler Refactor

### 7.1 New query approach

The refactored handler uses **one query** to read snapshots. The `chapter_id` filter still uses the `chapter_entity_links` table via `EXISTS` (indexed), avoiding JSON path queries.

```go
// snapshotToRAGEntity maps the stored snapshot JSON to the ragEntityExport shape
// used by the existing export response contract.
func snapshotToRAGEntity(raw []byte) (ragEntityExport, error) {
    // Intermediate struct matching snapshot schema
    var snap struct {
        EntityID string `json:"entity_id"`
        Kind     struct {
            Code string `json:"code"`
        } `json:"kind"`
        Status string   `json:"status"`
        Tags   []string `json:"tags"`
        Attributes []struct {
            Code             string `json:"code"`
            Name             string `json:"name"`
            OriginalLanguage string `json:"original_language"`
            OriginalValue    string `json:"original_value"`
            Translations []struct {
                LanguageCode string `json:"language_code"`
                Value        string `json:"value"`
                Confidence   string `json:"confidence"`
            } `json:"translations"`
            Evidences []struct {
                EvidenceType     string  `json:"evidence_type"`
                OriginalLanguage string  `json:"original_language"`
                OriginalText     string  `json:"original_text"`
                ChapterTitle     *string `json:"chapter_title"`
                BlockOrLine      string  `json:"block_or_line"`
                Note             *string `json:"note"`
            } `json:"evidences"`
        } `json:"attributes"`
        ChapterLinks []struct {
            ChapterTitle *string `json:"chapter_title"`
            Relevance    string  `json:"relevance"`
            Note         *string `json:"note"`
        } `json:"chapter_links"`
    }

    if err := json.Unmarshal(raw, &snap); err != nil {
        return ragEntityExport{}, err
    }

    // Build display_name: first non-empty value from 'name' or 'term' attribute
    displayName := ""
    for _, a := range snap.Attributes {
        if (a.Code == "name" || a.Code == "term") && a.OriginalValue != "" {
            displayName = a.OriginalValue
            break
        }
    }

    // Map attributes (skip empty, same rule as current handler)
    attrs := []ragAttrExport{}
    for _, a := range snap.Attributes {
        if a.OriginalValue == "" && len(a.Translations) == 0 && len(a.Evidences) == 0 {
            continue
        }
        trans := make([]ragTransExport, len(a.Translations))
        for i, t := range a.Translations {
            trans[i] = ragTransExport{
                Language:   t.LanguageCode,
                Value:      t.Value,
                Confidence: t.Confidence,
            }
        }
        evids := make([]ragEvidExport, len(a.Evidences))
        for i, ev := range a.Evidences {
            evids[i] = ragEvidExport{
                Type:         ev.EvidenceType,
                OriginalLang: ev.OriginalLanguage,
                Text:         ev.OriginalText,
                Chapter:      ev.ChapterTitle,
                Location:     ev.BlockOrLine,
                Note:         ev.Note,
            }
        }
        attrs = append(attrs, ragAttrExport{
            Code:             a.Code,
            Name:             a.Name,
            OriginalLanguage: a.OriginalLanguage,
            OriginalValue:    a.OriginalValue,
            Translations:     trans,
            Evidences:        evids,
        })
    }

    // Map chapter links
    links := make([]ragLinkExport, len(snap.ChapterLinks))
    for i, cl := range snap.ChapterLinks {
        links[i] = ragLinkExport{
            ChapterTitle: cl.ChapterTitle,
            Relevance:    cl.Relevance,
            Note:         cl.Note,
        }
    }

    return ragEntityExport{
        EntityID:     snap.EntityID,
        Kind:         snap.Kind.Code,
        DisplayName:  displayName,
        Status:       snap.Status,
        Tags:         snap.Tags,
        ChapterLinks: links,
        Attributes:   attrs,
    }, nil
}
```

### 7.2 Refactored exportGlossary handler (skeleton)

```go
func (s *Server) exportGlossary(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok { writeError(...); return }
    bookID, ok := parsePathUUID(w, r, "book_id")
    if !ok { return }
    if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }

    ctx := r.Context()
    q := r.URL.Query()

    var chapterFilter *uuid.UUID
    if cid := q.Get("chapter_id"); cid != "" {
        id, err := uuid.Parse(cid)
        if err != nil {
            writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid chapter_id")
            return
        }
        chapterFilter = &id
    }

    // Single query — no 5-query fan-out
    baseSQL := `
        SELECT entity_id::text, entity_snapshot
        FROM glossary_entities
        WHERE book_id = $1
          AND status = 'active'
          AND entity_snapshot IS NOT NULL`

    var rows pgx.Rows
    var err error
    if chapterFilter != nil {
        rows, err = s.pool.Query(ctx, baseSQL+`
          AND EXISTS (
              SELECT 1 FROM chapter_entity_links
              WHERE entity_id = glossary_entities.entity_id
                AND chapter_id = $2
          )
          ORDER BY entity_snapshot->'kind'->>'code',
                   updated_at DESC`,
            bookID, *chapterFilter)
    } else {
        rows, err = s.pool.Query(ctx, baseSQL+`
          ORDER BY entity_snapshot->'kind'->>'code',
                   updated_at DESC`,
            bookID)
    }
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
        return
    }
    defer rows.Close()

    result := []ragEntityExport{}
    for rows.Next() {
        var entityIDStr string
        var snapshotBytes []byte
        if err := rows.Scan(&entityIDStr, &snapshotBytes); err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
            return
        }
        ent, err := snapshotToRAGEntity(snapshotBytes)
        if err != nil {
            writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "snapshot parse failed")
            return
        }
        result = append(result, ent)
    }
    if err := rows.Err(); err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
        return
    }

    var chapIDStr *string
    if chapterFilter != nil {
        s := chapterFilter.String()
        chapIDStr = &s
    }
    writeJSON(w, http.StatusOK, ragExportResp{
        BookID:      bookID.String(),
        ExportedAt:  time.Now().UTC(),
        ChapterID:   chapIDStr,
        EntityCount: len(result),
        Entities:    result,
    })
}
```

---

## 8) Test Plan

### 8.1 DB-level unit tests (Go, using `pgx` against a real test DB)

| Test | What to assert |
|---|---|
| `TestSnapshotColumnExists` | After `UpSnapshot`, `entity_snapshot` column exists with type `jsonb`. |
| `TestRecalculateBuildsCorrectSnapshot` | Create entity with 2 attrs, 1 translation, 1 evidence, 1 chapter link → call `SELECT recalculate_entity_snapshot(id)` → parse snapshot JSON → assert all fields present and values correct. |
| `TestSnapshotKindFields` | Snapshot `kind.code`, `kind.name`, `kind.icon`, `kind.color` match the entity's kind row. |
| `TestSnapshotAttributeOrder` | Snapshot attributes are ordered by `sort_order`. |
| `TestSnapshotChapterLinkOrder` | chapter_links ordered by `chapter_index` then `added_at`. |
| `TestSnapshotEmptyArrays` | Entity with no translations/evidences/chapter_links → snapshot has `[]` (not `null`) for all array fields. |
| `TestTriggerFiresOnAttrValueUpdate` | Update `entity_attribute_values.original_value` → snapshot refreshes with new value. |
| `TestTriggerFiresOnTranslationInsert` | Insert `attribute_translations` row → snapshot reflects new translation. |
| `TestTriggerFiresOnEvidenceDelete` | Delete `evidences` row → snapshot no longer contains that evidence. |
| `TestTriggerFiresOnChapterLinkChange` | Insert `chapter_entity_links` → snapshot `chapter_links` updated. |
| `TestTriggerFiresOnEntityStatusUpdate` | `UPDATE glossary_entities SET status='active'` → snapshot `status` field updated. |
| `TestNoInfiniteLoop` | Run `UPDATE glossary_entities SET status='active'` → no stack overflow / no infinite trigger chain (assert only 1 snapshot recalculation occurs by counting calls or checking `snapshot_at` timestamp changes once). |
| `TestBackfillIdempotent` | Run `BackfillSnapshots` twice → second run is a no-op (no rows updated the second time, verified by checking `snapshot_at` unchanged). |
| `TestBackfillSkipsAlreadyPopulated` | Create entity, manually set `entity_snapshot = '{"schema_version":"1.0"}'`, run backfill → that entity's snapshot is NOT overwritten (since `WHERE entity_snapshot IS NULL` skips it). Actually backfill only fills NULLs so this passes trivially — assert 0 updates for already-populated entities. |

### 8.2 Export parity test

| Test | What to assert |
|---|---|
| `TestExportOutputUnchangedAfterRefactor` | Create character entity with 2 attrs, 1 translation, 1 evidence, 1 chapter link → call both old export logic (kept as `exportGlossaryLegacy` in test) and new handler → compare output JSON. Field-by-field equality. |
| `TestExportChapterFilter` | Two entities, one linked to chapter A, one not → export with `?chapter_id=A` → only linked entity in result. |
| `TestExportEmptyResult` | Book with no active entities → `entity_count: 0`, `entities: []`. |
| `TestExportSkipsEmptyAttributes` | Entity with all empty original_value + no translations + no evidences → those attributes absent from export. |
| `TestExportSnapshotIsNull` | Entity whose `entity_snapshot IS NULL` (pre-backfill) → excluded from export (handled by `AND entity_snapshot IS NOT NULL` in query). |

### 8.3 Auth tests (unchanged — carried forward from SP-1 to SP-5)

No new auth tests needed; existing `TestExportEndpointRequiresAuth` and `TestExportEndpointRejectsBadToken` still cover the refactored handler.

---

## 9) Performance Considerations

### 9.1 Trigger overhead per write

Each mutation now triggers one extra `recalculate_entity_snapshot` call, which runs a correlated subquery with ~4 sub-selects. For a typical write (e.g. `PATCH attribute value`):

| Operation | Extra trigger cost (estimated) |
|---|---|
| Update 1 attribute value | 1 snapshot recalculation ≈ 3–5 ms on entity with 13 attrs, 5 translations |
| Add 1 evidence | 1 recalculation (via `trig_evid_snapshot`) |
| Add 1 translation | 1 recalculation (via `trig_trans_snapshot`) |

This is acceptable for interactive (user-driven) mutations. The API never does bulk writes in the current SP-1–SP-5 scope.

### 9.2 Benchmark gate before proceeding to SS-2

Before merging SS-1, run a benchmark:
- Create 1 book with 100 entities, each with 13 attrs, 5 translations, 3 evidences, 2 chapter links.
- Run `BackfillSnapshots` → measure wall time.
- Run 50 concurrent `PATCH attribute value` requests → measure P95 latency.

**Acceptable thresholds:**
- Backfill 100 entities: < 2 seconds.
- P95 patch latency with trigger: < 200 ms (vs < 50 ms without trigger).

If P95 exceeds threshold, consider:
- Option A: Statement-level trigger (batch recalculation per statement, not per row). Reduces overhead for bulk imports but adds complexity.
- Option B: Deferred trigger (`CONSTRAINT TRIGGER ... DEFERRED`). Runs once at end of transaction.
- Option C: Async queue (Go goroutine pool). Adds eventual-consistency risk.

For SS-1 scope, **Option B (deferred trigger)** is the preferred fallback if benchmark fails:

```sql
-- Deferred variant example for evidences:
CREATE CONSTRAINT TRIGGER trig_evid_snapshot_deferred
  AFTER INSERT OR UPDATE OR DELETE ON evidences
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION trig_fn_evid_snapshot();
```

Deferred triggers fire at transaction commit time — one snapshot recalculation per entity per transaction regardless of how many sub-rows changed. The snapshot is never stale within the same transaction (reads within the same TX would still see the pre-commit state).

### 9.3 Export performance improvement

Old export: 5 sequential queries → N round-trips (N = number of `ANY($1)` batches).
New export: 1 query reading pre-assembled JSONB. Expected 5–10× improvement for books with >50 entities.

---

## 10) Files to Create / Modify

### Modify

| File | Change |
|---|---|
| `services/glossary-service/internal/migrate/migrate.go` | Add `snapshotSQL` const, `UpSnapshot()` function, `BackfillSnapshots()` function |
| `services/glossary-service/cmd/server/main.go` | Call `migrate.UpSnapshot(ctx, pool)` and `migrate.BackfillSnapshots(ctx, pool)` after existing `migrate.Up` and `migrate.Seed` |
| `services/glossary-service/internal/api/export_handler.go` | Replace 5-query logic with snapshot-based query; add `snapshotToRAGEntity()` helper function |

### Create

| File | Purpose |
|---|---|
| `services/glossary-service/internal/api/export_handler_test.go` (new tests added to existing file if it exists) | Export parity tests, chapter filter test, empty result test |

---

## 11) Exit Criteria

All of the following must be true before SS-1 is considered done:

- [ ] `UpSnapshot()` and `BackfillSnapshots()` run without error on a fresh DB and on a DB that already has entities.
- [ ] `entity_snapshot` column exists and is populated for all existing entities after startup.
- [ ] All 13 trigger tests pass (`go test ./...`).
- [ ] Export parity test passes: old and new handler produce identical JSON for the same data.
- [ ] Benchmark: backfill 100 entities < 2 s; P95 patch latency < 200 ms with trigger active.
- [ ] No infinite trigger loop detectable under any test scenario.
- [ ] `npx tsc --noEmit` passes (no frontend changes in SS-1).
- [ ] `go vet ./...` passes.

---

## 12) SS-7 Forward-Compatibility Notes

The `recalculate_entity_snapshot` function is written to handle only `kind_source = 'system'` in SS-1. When SS-7 adds `user_kind_id` and `book_kind_id` columns to `glossary_entities`, the function will be updated with a `CASE` branch:

```sql
-- SS-7 addition (not in SS-1):
'kind', CASE
  WHEN e.kind_id IS NOT NULL THEN
    jsonb_build_object('source','system', 'ref_id', k.kind_id::text, ...)
  WHEN e.user_kind_id IS NOT NULL THEN
    jsonb_build_object('source','user',   'ref_id', uk.user_kind_id::text, ...)
  WHEN e.book_kind_id IS NOT NULL THEN
    jsonb_build_object('source','book',   'ref_id', bk.book_kind_id::text, ...)
END,
```

The `schema_version: "1.0"` field will remain unchanged since the shape does not break — it only adds possible values to the `source` enum. No migration of existing snapshots needed when SS-7 ships.

---

## 13) References

- `docs/03_planning/89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md` — SS-1 overview
- `docs/03_planning/88_MODULE05_SUPPLEMENT_REQUIREMENTS.md` — Feature D requirements
- `services/glossary-service/internal/migrate/migrate.go` — current schema (9 tables)
- `services/glossary-service/internal/api/export_handler.go` — current 5-query export (371 lines)
