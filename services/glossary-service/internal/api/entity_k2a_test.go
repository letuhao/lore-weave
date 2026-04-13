package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// runK2aMigrations applies the full migration chain through K2a.
// Mirrors runMigrations in export_handler_test.go but also wires up the
// knowledge-memory step under test.
func runK2aMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	ctx := context.Background()
	if err := migrate.Up(ctx, pool); err != nil {
		t.Fatalf("migrate.Up: %v", err)
	}
	if err := migrate.Seed(ctx, pool); err != nil {
		t.Fatalf("migrate.Seed: %v", err)
	}
	if err := migrate.UpSnapshot(ctx, pool); err != nil {
		t.Fatalf("migrate.UpSnapshot: %v", err)
	}
	if err := migrate.UpSoftDelete(ctx, pool); err != nil {
		t.Fatalf("migrate.UpSoftDelete: %v", err)
	}
	// UpExtraction adds the `alive` column that the snapshot triggers
	// reference. Skipping it leaves the recalculate function unable to
	// build a snapshot because it can't read e.alive.
	if err := migrate.UpExtraction(ctx, pool); err != nil {
		t.Fatalf("migrate.UpExtraction: %v", err)
	}
	if err := migrate.UpEvidenceChapterIndex(ctx, pool); err != nil {
		t.Fatalf("migrate.UpEvidenceChapterIndex: %v", err)
	}
	if err := migrate.UpKnowledgeMemory(ctx, pool); err != nil {
		t.Fatalf("migrate.UpKnowledgeMemory: %v", err)
	}
}

// ── schema shape tests ──────────────────────────────────────────────────────

func TestK2aColumnsExist(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)

	wantCols := map[string]bool{
		"short_description":      false,
		"is_pinned_for_context":  false,
		"cached_name":            false,
		"cached_aliases":         false,
		"search_vector":          false,
	}
	rows, err := pool.Query(context.Background(), `
		SELECT column_name FROM information_schema.columns
		WHERE table_name = 'glossary_entities'
		  AND column_name = ANY($1)`,
		[]string{"short_description", "is_pinned_for_context", "cached_name", "cached_aliases", "search_vector"})
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	defer rows.Close()
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatalf("scan: %v", err)
		}
		wantCols[name] = true
	}
	for name, found := range wantCols {
		if !found {
			t.Errorf("column %s missing", name)
		}
	}
}

func TestK2aIndexesExist(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)

	wantIdx := map[string]bool{
		"idx_ge_search_vector": false,
		"idx_ge_pinned_book":   false,
	}
	rows, err := pool.Query(context.Background(), `
		SELECT indexname FROM pg_indexes
		WHERE tablename = 'glossary_entities'
		  AND indexname = ANY($1)`,
		[]string{"idx_ge_search_vector", "idx_ge_pinned_book"})
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	defer rows.Close()
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatalf("scan: %v", err)
		}
		wantIdx[name] = true
	}
	for name, found := range wantIdx {
		if !found {
			t.Errorf("index %s missing", name)
		}
	}
}

// ── trigger behaviour tests ─────────────────────────────────────────────────

func TestK2aCachedNamePopulatedFromEAV(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-0000000ca100"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	var nameAttrID string
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttrID)
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','李雲')`,
		entityID, nameAttrID); err != nil {
		t.Fatalf("insert name attr: %v", err)
	}

	var cached *string
	pool.QueryRow(ctx, `SELECT cached_name FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&cached)
	if cached == nil || *cached != "李雲" {
		t.Errorf("cached_name: want 李雲, got %v", cached)
	}
}

func TestK2aCachedAliasesParsedFromJSONString(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-0000000ca101"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	var aliasesAttrID string
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='aliases' LIMIT 1`,
		kindID).Scan(&aliasesAttrID)
	if aliasesAttrID == "" {
		t.Skip("character kind has no 'aliases' attribute definition")
	}

	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','["小李","李子"]')`,
		entityID, aliasesAttrID); err != nil {
		t.Fatalf("insert aliases: %v", err)
	}

	var cached []string
	pool.QueryRow(ctx, `SELECT cached_aliases FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&cached)
	if len(cached) != 2 || cached[0] != "小李" || cached[1] != "李子" {
		t.Errorf("cached_aliases: want [小李 李子], got %v", cached)
	}
}

func TestK2aMalformedAliasesJSONFallsBackToEmpty(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-0000000ca102"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	var aliasesAttrID string
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='aliases' LIMIT 1`,
		kindID).Scan(&aliasesAttrID)
	if aliasesAttrID == "" {
		t.Skip("character kind has no 'aliases' attribute definition")
	}

	// Garbage value — must NOT crash the trigger.
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','this is not json')`,
		entityID, aliasesAttrID); err != nil {
		t.Fatalf("insert garbage aliases: %v", err)
	}

	var cached []string
	pool.QueryRow(ctx, `SELECT cached_aliases FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&cached)
	if len(cached) != 0 {
		t.Errorf("malformed aliases: want empty, got %v", cached)
	}
}

func TestK2aSearchVectorRefreshesOnDirectShortDescriptionWrite(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-0000000ca103"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	// Direct write — does NOT bump updated_at, exercises the
	// extended self-trigger watch list.
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET short_description='unique_marker_zenith' WHERE entity_id=$1`,
		entityID); err != nil {
		t.Fatalf("update short_description: %v", err)
	}

	var foundID string
	err := pool.QueryRow(ctx,
		`SELECT entity_id FROM glossary_entities
		 WHERE search_vector @@ plainto_tsquery('simple','unique_marker_zenith')
		   AND book_id=$1`, bookID).Scan(&foundID)
	if err != nil {
		t.Fatalf("FTS query failed (expected to find entity): %v", err)
	}
	if foundID != entityID {
		t.Errorf("FTS returned wrong entity: want %s, got %s", entityID, foundID)
	}
}

func TestK2aSearchVectorRefreshesOnEAVChange(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-0000000ca104"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	var nameAttrID string
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttrID)
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','sigil_alpha')`,
		entityID, nameAttrID); err != nil {
		t.Fatalf("insert name: %v", err)
	}

	var foundID string
	if err := pool.QueryRow(ctx,
		`SELECT entity_id FROM glossary_entities
		 WHERE search_vector @@ plainto_tsquery('simple','sigil_alpha')
		   AND book_id=$1`, bookID).Scan(&foundID); err != nil {
		t.Fatalf("FTS after name insert: %v", err)
	}
	if foundID != entityID {
		t.Errorf("FTS wrong entity: want %s, got %s", entityID, foundID)
	}
}

// ── pin/unpin SQL semantics ────────────────────────────────────────────────

func TestK2aPinTogglePartialIndex(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-0000000ca105"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	// Pin
	pool.Exec(ctx, `UPDATE glossary_entities SET is_pinned_for_context=true, updated_at=now() WHERE entity_id=$1`, entityID)
	var pinnedCount int
	pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE is_pinned_for_context AND deleted_at IS NULL AND book_id=$1`, bookID).Scan(&pinnedCount)
	if pinnedCount != 1 {
		t.Errorf("after pin: want 1, got %d", pinnedCount)
	}

	// Unpin
	pool.Exec(ctx, `UPDATE glossary_entities SET is_pinned_for_context=false, updated_at=now() WHERE entity_id=$1`, entityID)
	pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE is_pinned_for_context AND book_id=$1`, bookID).Scan(&pinnedCount)
	if pinnedCount != 0 {
		t.Errorf("after unpin: want 0, got %d", pinnedCount)
	}
}

// ── HTTP-level auth tests (no DB required) ─────────────────────────────────

func TestK2aPinEndpoint_RequiresAuth(t *testing.T) {
	srv := newExportServer(t, nil)
	for _, method := range []string{http.MethodPost, http.MethodDelete} {
		req := httptest.NewRequest(method,
			"/v1/glossary/books/00000000-0000-0000-0000-000000000001/entities/00000000-0000-0000-0000-000000000002/pin",
			nil)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusUnauthorized {
			t.Errorf("%s /pin without auth: want 401, got %d", method, w.Code)
		}
	}
}

func TestK2aPinEndpoint_BadBookUUIDReturns400(t *testing.T) {
	srv := newExportServer(t, nil)
	token := makeExportToken(t, "11111111-1111-1111-1111-111111111111")
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/not-a-uuid/entities/00000000-0000-0000-0000-000000000002/pin",
		nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad book_id: want 400, got %d", w.Code)
	}
}

// ── backfill idempotency ────────────────────────────────────────────────────

func TestK2aBackfillIdempotent(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	if err := migrate.BackfillKnowledgeMemory(ctx, pool); err != nil {
		t.Fatalf("first backfill: %v", err)
	}
	if err := migrate.BackfillKnowledgeMemory(ctx, pool); err != nil {
		t.Fatalf("second backfill: %v", err)
	}
}
