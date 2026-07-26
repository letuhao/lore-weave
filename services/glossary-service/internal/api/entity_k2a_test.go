package api

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
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
	// pg_trgm + GIN trigram indexes + glossary_aliases_text — required for the
	// raw entity search (similarity()/% operators) and sort-by-name on cached_name.
	if err := migrate.UpGlossarySearch(ctx, pool); err != nil {
		t.Fatalf("migrate.UpGlossarySearch: %v", err)
	}
	// Denormalized appearance counters + triggers (sort-by-appearance).
	if err := migrate.UpEntityCounts(ctx, pool); err != nil {
		t.Fatalf("migrate.UpEntityCounts: %v", err)
	}
	// G4 genre·kind·attribute tiering: user_kinds → genre/kind/attr tier (creates
	// book_kinds + book_attributes, the cutover's FK targets) → seed system standards
	// → destructive cutover (repoints glossary_entities.kind_id → book_kinds and
	// entity_attribute_values.attr_def_id → book_attributes, rewrites the snapshot to
	// the book tier). Order matters: UpGenreKindAttr MUST precede the cutover. Because
	// the test DB is shared and this DDL persists, the cutover must be present in
	// whatever chain runs first — so it lives in this lowest-level shared helper.
	if err := migrate.UpUserKinds(ctx, pool); err != nil {
		t.Fatalf("migrate.UpUserKinds: %v", err)
	}
	if err := migrate.UpGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("migrate.UpGenreKindAttr: %v", err)
	}
	if err := migrate.SeedGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("migrate.SeedGenreKindAttr: %v", err)
	}
	if err := migrate.UpGlossaryCutoverG4(ctx, pool); err != nil {
		t.Fatalf("migrate.UpGlossaryCutoverG4: %v", err)
	}
	if err := migrate.UpGlossaryCutoverG4Cache(ctx, pool); err != nil {
		t.Fatalf("migrate.UpGlossaryCutoverG4Cache: %v", err)
	}
	// G4e: IRREVERSIBLE drop of the retired legacy objects (genre_groups,
	// system_kind_attributes, genre_tags columns). Runs LAST so the shared test DB
	// matches production after every consumer was retargeted off them (G4d).
	if err := migrate.UpGlossaryDropLegacyG4(ctx, pool); err != nil {
		t.Fatalf("migrate.UpGlossaryDropLegacyG4: %v", err)
	}
	// 0030 — backs the generalized class-C confirm machinery's single-use ledger.
	if err := migrate.UpConsumedTokens(ctx, pool); err != nil {
		t.Fatalf("migrate.UpConsumedTokens: %v", err)
	}
	// 0031 — System-tier soft-delete (G-C8): deprecated_at on system_genres/kinds/attributes.
	if err := migrate.UpSystemSoftDelete(ctx, pool); err != nil {
		t.Fatalf("migrate.UpSystemSoftDelete: %v", err)
	}
	// 0032 — extraction FND/M1: normalized_name + uq_entity_dedup, uq_evidence_dedup,
	// extraction_writeback_log. Runs after the G4 cutover-cache (adds cached_name, the
	// generated normalized_name's base).
	if err := migrate.UpExtractionConcurrency(ctx, pool); err != nil {
		t.Fatalf("migrate.UpExtractionConcurrency: %v", err)
	}
	// 0033 — extraction PROV/M3: evidence offset + provenance_status columns.
	if err := migrate.UpEvidenceProvenance(ctx, pool); err != nil {
		t.Fatalf("migrate.UpEvidenceProvenance: %v", err)
	}
	// 0034 — extraction MERGE/M5: EAV confidence marker + attribute merge_strategy.
	if err := migrate.UpMergePolicy(ctx, pool); err != nil {
		t.Fatalf("migrate.UpMergePolicy: %v", err)
	}
	// 0035 — D-GLOSSARY-MULTIROW-ATTR-VALUES: per-item child table + backfill.
	if err := migrate.UpMultirowAttrValues(ctx, pool); err != nil {
		t.Fatalf("migrate.UpMultirowAttrValues: %v", err)
	}
	// 0040 — D-GLOSSARY-ST-DEDUP: convert normalized_name GENERATED→app-maintained.
	// Required so the wired name-write paths' refreshEntityDedupKey UPDATE doesn't
	// hit "column can only be updated to DEFAULT" against a still-generated column.
	if err := migrate.UpStDedupAppMaintained(ctx, pool); err != nil {
		t.Fatalf("migrate.UpStDedupAppMaintained: %v", err)
	}
	// 0041 — M7: chapter_entity_links.mention_count (per-chapter mention frequency).
	if err := migrate.UpChapterLinkMentionCount(ctx, pool); err != nil {
		t.Fatalf("migrate.UpChapterLinkMentionCount: %v", err)
	}
	// 0043 — #26/#7: the summarize mode's canonical layer on the EAV
	// (canonical_value + canonical_dirty + canonical_synced_at).
	if err := migrate.UpCanonicalSummary(ctx, pool); err != nil {
		t.Fatalf("migrate.UpCanonicalSummary: %v", err)
	}
	// 0051 — D-GLOSSARY-ENTITY-SCOPE: scope_label column + widened uq_entity_dedup.
	// Safe to run here without 0044-0050 (bitemporal facts, unrelated K3-sensitive
	// trigger changes) — this step only touches glossary_entities.scope_label and
	// the uq_entity_dedup index already established by 0032 above. findEntityByNameOrAlias
	// (extraction_handler.go) now unconditionally selects ge.scope_label, so every test
	// reaching it through this shared helper needs the column present.
	if err := migrate.UpEntityScopeLabel(ctx, pool); err != nil {
		t.Fatalf("migrate.UpEntityScopeLabel: %v", err)
	}
	// 0054 (C4/SD-C4) — book_kinds/system_kinds/user_kinds.is_person. The wiki-gen + enrichment
	// PP-4 guards now filter `NOT ek.is_person` and the adopt clone selects sk/uk.is_person, so this
	// column MUST exist in the shared test DB or those paths error on a missing column.
	if err := migrate.UpKindIsPerson(ctx, pool); err != nil {
		t.Fatalf("migrate.UpKindIsPerson: %v", err)
	}
}

// ── schema shape tests ──────────────────────────────────────────────────────

func TestK2aColumnsExist(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)

	wantCols := map[string]bool{
		"short_description":     false,
		"is_pinned_for_context": false,
		"cached_name":           false,
		"cached_aliases":        false,
		"search_vector":         false,
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
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
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
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	aliasesAttrID := bookAttrID(t, pool, bid, kindID, "aliases")

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
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	aliasesAttrID := bookAttrID(t, pool, bid, kindID, "aliases")

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
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
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
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
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
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
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

// ── T2-close-7 / P-K2a-02: trigger perf — updated_at NO LONGER triggers recalc

// TestTriggerSkipsRecalcOnUpdatedAtOnly proves the self-trigger watch list
// dropped updated_at. A bare UPDATE that bumps nothing but updated_at must
// leave entity_snapshot untouched.
func TestTriggerSkipsRecalcOnUpdatedAtOnly(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-00000000bbbb"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	// Name the entity so recalculate_entity_snapshot produces a non-empty
	// cached_name when we manually trigger it once below.
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'en','Alice')`, entityID, nameAttrID)

	// Capture the snapshot's snapshot_at timestamp — the only source of
	// truth for "did recalc run". We deliberately read it BEFORE and AFTER
	// the updated_at bump.
	var before, after string
	pool.QueryRow(ctx,
		`SELECT entity_snapshot->>'snapshot_at' FROM glossary_entities WHERE entity_id=$1`,
		entityID).Scan(&before)

	// Bump updated_at alone — this is the kind of write the API used to
	// issue for pin toggles. With updated_at dropped from the trigger
	// watch list, the recalc must NOT fire.
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET updated_at = now() + interval '1 second' WHERE entity_id=$1`,
		entityID); err != nil {
		t.Fatalf("updated_at bump: %v", err)
	}

	pool.QueryRow(ctx,
		`SELECT entity_snapshot->>'snapshot_at' FROM glossary_entities WHERE entity_id=$1`,
		entityID).Scan(&after)

	if before != after {
		t.Errorf("updated_at bump should NOT re-run recalc (snapshot_at changed: %s -> %s)", before, after)
	}
}

// TestTriggerStillFiresOnWatchedFields guards against the inverse regression:
// dropping updated_at must not have accidentally broken the specific watches
// for ANY of the fields the snapshot depends on. Table-driven over all seven
// watched fields so a future rewrite that drops one is caught.
func TestTriggerStillFiresOnWatchedFields(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	cases := []struct {
		name        string
		setClause   string
		usesKindLoc bool // true if the case changes kind_id to the book's 'location' kind
		needsCharOK bool // true if the case needs a name seeded for snapshot to exist
	}{
		{"status", "status = 'inactive'", false, true},
		{"alive", "alive = false", false, true},
		{"tags", "tags = ARRAY['revised']", false, true},
		{"kind_id", "kind_id = $2", true, true},
		{"short_description", "short_description = 'a brief'", false, true},
		{"deleted_at", "deleted_at = now()", false, true},
		{"permanently_deleted_at", "permanently_deleted_at = now()", false, true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			bookID := "00000000-0000-0000-0000-0000" + fmt.Sprintf("%08x", len(tc.name)+0xbbcc)
			bid := uuid.MustParse(bookID)
			adoptTestBook(t, pool, bid)
			// book-tier kind ids for THIS book (FK target is now book_kinds).
			kindCharID := bookKindID(t, pool, bid, "character")

			var entityID string
			pool.QueryRow(ctx,
				`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
				bid, kindCharID).Scan(&entityID)
			t.Cleanup(func() {
				pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
			})

			// The kind_id case needs a distinct book-local kind to switch to.
			var args []any
			if tc.usesKindLoc {
				args = []any{bookKindID(t, pool, bid, "location")}
			}

			if tc.needsCharOK {
				nameAttrID := bookAttrID(t, pool, bid, kindCharID, "name")
				pool.Exec(ctx,
					`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
					 VALUES($1,$2,'en','Bob')`, entityID, nameAttrID)
			}

			var before string
			pool.QueryRow(ctx,
				`SELECT entity_snapshot->>'snapshot_at' FROM glossary_entities WHERE entity_id=$1`,
				entityID).Scan(&before)

			execArgs := append([]any{entityID}, args...)
			q := fmt.Sprintf(`UPDATE glossary_entities SET %s WHERE entity_id=$1`, tc.setClause)
			if _, err := pool.Exec(ctx, q, execArgs...); err != nil {
				t.Fatalf("%s update: %v", tc.name, err)
			}

			var after string
			pool.QueryRow(ctx,
				`SELECT entity_snapshot->>'snapshot_at' FROM glossary_entities WHERE entity_id=$1`,
				entityID).Scan(&after)

			if before == after {
				t.Errorf("%s change: recalc did not fire (snapshot_at unchanged = %s)", tc.name, before)
			}
		})
	}
}

// TestPinSQLDoesNotBumpUpdatedAt simulates exactly what the pin handler
// now writes — a single-column UPDATE with no `updated_at = now()` —
// and asserts both updated_at and snapshot_at stay frozen. Verifies
// the combined fix at the SQL layer without needing a book-service
// mock for verifyBookOwner.
func TestPinSQLDoesNotBumpUpdatedAt(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-00000000bbdd"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	var entityID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&entityID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	// Seed a name so recalc runs once and we have a baseline snapshot_at.
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'en','Cara')`, entityID, nameAttrID)

	var entityUpdatedBefore, snapshotAtBefore string
	pool.QueryRow(ctx,
		`SELECT updated_at::text, entity_snapshot->>'snapshot_at'
		 FROM glossary_entities WHERE entity_id=$1`,
		entityID).Scan(&entityUpdatedBefore, &snapshotAtBefore)

	// Emulate the NEW pin handler SQL verbatim — no updated_at bump.
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities
		 SET is_pinned_for_context = true
		 WHERE entity_id = $1 AND book_id = $2 AND deleted_at IS NULL`,
		entityID, bookID); err != nil {
		t.Fatalf("pin SQL: %v", err)
	}

	var isPinned bool
	var entityUpdatedAfter, snapshotAtAfter string
	pool.QueryRow(ctx,
		`SELECT is_pinned_for_context, updated_at::text, entity_snapshot->>'snapshot_at'
		 FROM glossary_entities WHERE entity_id=$1`,
		entityID).Scan(&isPinned, &entityUpdatedAfter, &snapshotAtAfter)

	if !isPinned {
		t.Error("pin: is_pinned_for_context was not set")
	}
	if entityUpdatedBefore != entityUpdatedAfter {
		t.Errorf("pin: updated_at changed (%s -> %s); pin must be a timestamp-inert write",
			entityUpdatedBefore, entityUpdatedAfter)
	}
	if snapshotAtBefore != snapshotAtAfter {
		t.Errorf("pin: snapshot_at changed (%s -> %s); recalc must NOT fire for a pin toggle",
			snapshotAtBefore, snapshotAtAfter)
	}
}
