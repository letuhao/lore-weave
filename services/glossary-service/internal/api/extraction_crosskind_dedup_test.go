package api

// #38/#39 — cross-kind entity dedup at extraction write time. The same name
// extracted under a DIFFERENT kind (an LLM mis-tag, or a re-run with a changed
// kind set whose writeback_key bypasses chapter idempotency) must REUSE the
// existing entity instead of spawning a per-kind duplicate.
//
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func entityKindCode(t *testing.T, pool *pgxpool.Pool, bookID string) string {
	t.Helper()
	var code string
	if err := pool.QueryRow(context.Background(), `
		SELECT bk.code FROM glossary_entities ge
		JOIN book_kinds bk ON bk.book_kind_id = ge.kind_id
		WHERE ge.book_id=$1 AND ge.deleted_at IS NULL
		ORDER BY ge.created_at LIMIT 1`, bookID).Scan(&code); err != nil {
		t.Fatalf("read entity kind: %v", err)
	}
	return code
}

func TestCrossKindDedup_SameNameDifferentKind_ReusesEntity(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	bookID := uuid.NewString()
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	// First run: "Li Yun" under character.
	r1 := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "character", "name": "Li Yun"}},
	})
	if r1["created"] != float64(1) {
		t.Fatalf("first extract: want created=1, got %v", r1)
	}
	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Fatalf("after first extract: want 1 entity, got %d", n)
	}

	// Second run: the SAME name under a DIFFERENT kind, carrying a description.
	// Pre-fix this created a second entity; now it must dedup into the existing
	// one AND merge the attribute against the matched entity's (character) kind —
	// proving the cross-kind path goes through the real merge, not just the lookup.
	r2 := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"attribute_actions": map[string]any{
			"location": map[string]any{"description": "overwrite"},
		},
		"entities": []map[string]any{
			{"kind_code": "location", "name": "Li Yun", "attributes": map[string]any{
				"description": "A young cultivator",
			}},
		},
	})
	if r2["created"] != float64(0) {
		t.Errorf("cross-kind: want created=0, got %v (resp=%v)", r2["created"], r2)
	}
	if r2["updated"] != float64(1) {
		t.Errorf("cross-kind: want updated=1 (merged into the existing entity), got %v", r2["updated"])
	}
	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Errorf("after cross-kind extract: want STILL 1 entity, got %d", n)
	}
	// Oldest wins → the entity keeps its original (character) kind.
	if code := entityKindCode(t, pool, bookID); code != "character" {
		t.Errorf("entity kind: want character (oldest wins), got %q", code)
	}
	// The description merged onto the character entity via its OWN kind's attr def.
	var desc string
	if err := pool.QueryRow(ctx, `
		SELECT eav.original_value FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ge.deleted_at IS NULL AND ad.code='description'`,
		bookID).Scan(&desc); err != nil {
		t.Fatalf("read merged description: %v", err)
	}
	if desc != "A young cultivator" {
		t.Errorf("cross-kind merge: want description merged onto the entity, got %q", desc)
	}
}

func TestCrossKindDedup_DistinctNameCreates(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	bookID := uuid.NewString()
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "character", "name": "Li Yun"}},
	})
	// A genuinely different name under another kind must still CREATE — cross-kind
	// dedup must not over-merge distinct entities.
	r2 := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "location", "name": "Cloud Peak"}},
	})
	if r2["created"] != float64(1) {
		t.Errorf("distinct name: want created=1, got %v (resp=%v)", r2["created"], r2)
	}
	if n := liveEntityCount(t, pool, ctx, bookID); n != 2 {
		t.Errorf("distinct name: want 2 entities, got %d", n)
	}
}

func TestCrossKindDedup_FoldedNameVariant_ReusesEntity(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	bookID := uuid.NewString()
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	// Traditional-script name under character.
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities":        []map[string]any{{"kind_code": "character", "name": "張若塵"}},
	})
	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Fatalf("after first extract: want 1 entity, got %d", n)
	}
	// The SIMPLIFIED variant under a different kind folds to the same
	// normalized_name (textnorm.Normalize) → cross-kind dedup, no duplicate.
	r2 := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities":        []map[string]any{{"kind_code": "location", "name": "张若尘"}},
	})
	if r2["created"] != float64(0) {
		t.Errorf("folded variant: want created=0, got %v (resp=%v)", r2["created"], r2)
	}
	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Errorf("folded variant: want STILL 1 entity, got %d", n)
	}
}

// D-GLOSSARY-ENTITY-SCOPE — cross-kind dedup must NOT merge an unscoped extraction
// onto an entity a human already disambiguated with a scope_label. The bulk
// pipeline has no scope concept of its own (always passes ""), so it should
// create a fresh (unscoped) entity rather than silently attaching new attributes
// to whichever world's entity happens to be oldest.
func TestCrossKindDedup_ScopedEntityNotReusedByUnscopedExtraction(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	bookID := uuid.NewString()
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "character", "name": "Lam Gia"}},
	})
	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Fatalf("after first extract: want 1 entity, got %d", n)
	}
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET scope_label='World A' WHERE book_id=$1`, bookID,
	); err != nil {
		t.Fatalf("set scope_label: %v", err)
	}

	// Same name, different kind, but the FIRST entity is now scoped — the unscoped
	// extraction must NOT reuse it.
	r2 := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "location", "name": "Lam Gia"}},
	})
	if r2["created"] != float64(1) {
		t.Errorf("scoped entity must not be reused by an unscoped extraction: want created=1, got %v (resp=%v)", r2["created"], r2)
	}
	if n := liveEntityCount(t, pool, ctx, bookID); n != 2 {
		t.Errorf("want 2 entities (scoped original + fresh unscoped draft), got %d", n)
	}
}
