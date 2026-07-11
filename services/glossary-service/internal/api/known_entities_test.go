package api

// Tests for GET /internal/books/{book_id}/known-entities.
// Unit tests (no DB) run always.
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// ── unit tests (no DB) ──────────────────────────────────────────────

// newKnownEntitiesServer reuses the export-test helpers but fixes an
// internal token so the /internal middleware lets us through.
func newKnownEntitiesServer(t *testing.T) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, nil)
	token := "known-entities-test-token"
	srv.cfg.InternalServiceToken = token
	return srv, token
}

func TestKnownEntities_RequiresInternalToken(t *testing.T) {
	srv, _ := newKnownEntitiesServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/known-entities", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestKnownEntities_WrongTokenReturns401(t *testing.T) {
	srv, _ := newKnownEntitiesServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/known-entities", nil)
	req.Header.Set("X-Internal-Token", "wrong")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("wrong token: want 401, got %d", w.Code)
	}
}

func TestKnownEntities_BadUUIDReturns400(t *testing.T) {
	srv, token := newKnownEntitiesServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/not-a-uuid/known-entities", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad uuid: want 400, got %d", w.Code)
	}
}

// ── integration (requires DB) ──────────────────────────────────────

// TestKnownEntities_ReturnsEntityID seeds 2 entities with enough
// chapter_entity_links to clear the min_frequency=2 default, then
// asserts that the response JSON includes the entity_id for each —
// K13.0's prerequisite change for anchor pre-loading.
func TestKnownEntities_ReturnsEntityID(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	// T2-polish-1: runMigrations stops at UpSnapshot, but the
	// known-entities handler filters on the `alive` column added by
	// UpExtraction (default true). Without that migration the handler
	// query raises SQLSTATE 42703 on the live test DB. Use the fuller
	// runK2aMigrations which chains Up → Seed → UpSnapshot →
	// UpSoftDelete → UpExtraction → UpEvidenceChapterIndex →
	// UpKnowledgeMemory.
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-000000000001"

	// G4: entities now reference the BOOK tier — adopt the book so its book_kinds /
	// book_attributes exist, then resolve the 'character' kind + name/aliases attrs.
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
	aliasesAttrID := bookAttrID(t, pool, bid, kindID, "aliases")

	// Seed two entities.
	seedEntity := func(name, aliasesJSON string) string {
		var eid string
		pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
			 VALUES($1,$2,'active','{}') RETURNING entity_id`,
			bid, kindID,
		).Scan(&eid)
		pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
			 VALUES($1,$2,'en',$3)`,
			eid, nameAttrID, name,
		)
		if aliasesJSON != "" {
			pool.Exec(ctx,
				`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
				 VALUES($1,$2,'en',$3)`,
				eid, aliasesAttrID, aliasesJSON,
			)
		}
		return eid
	}
	entA := seedEntity("Arthur", `["Art"]`)
	entB := seedEntity("Merlin", "")

	// 2 chapter links per entity clears min_frequency=2.
	// T2-polish-1: original SQL had 5 columns but only 4 values
	// (chapter_index was in the column list but not the VALUES
	// tuple), so every INSERT failed silently and the handler got 0
	// rows. Fixed by passing chapter_index as $2.
	link := func(eid string, chapterIdx int) {
		pool.Exec(ctx,
			`INSERT INTO chapter_entity_links(entity_id,chapter_id,chapter_title,chapter_index,relevance)
			 VALUES($1,gen_random_uuid(),'Ch',$2,'major')`,
			eid, chapterIdx,
		)
	}
	link(entA, 1)
	link(entA, 2)
	link(entB, 1)
	link(entB, 2)

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM chapter_entity_links WHERE entity_id IN ($1,$2)`, entA, entB)
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN ($1,$2)`, entA, entB)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newKnownEntitiesServer(t)
	srv.pool = pool

	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/known-entities", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp []struct {
		EntityID string   `json:"entity_id"`
		Name     string   `json:"name"`
		KindCode string   `json:"kind_code"`
		Aliases  []string `json:"aliases"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v — body=%s", err, w.Body.String())
	}

	if len(resp) != 2 {
		t.Fatalf("want 2 entities, got %d: %+v", len(resp), resp)
	}
	for _, e := range resp {
		if e.EntityID == "" {
			t.Errorf("entity_id must be non-empty — K13.0 anchor pre-loader depends on it; got %+v", e)
		}
	}

	// Ensure both seeded entities came back.
	seen := map[string]bool{}
	for _, e := range resp {
		seen[e.EntityID] = true
	}
	if !seen[entA] || !seen[entB] {
		t.Errorf("missing seeded entity_id(s): got %v (want %s and %s)", seen, entA, entB)
	}
}

// W11-M3 — a soft-deleted entity must NEVER appear in known-entities. Soft-delete
// is a pure `SET deleted_at` (status stays 'active', alive stays true, chapter links
// survive), so without the `deleted_at IS NULL` filter an author-DELETED canon entity
// would leak — and the public lore route serves this stream to anonymous readers.
func TestKnownEntities_ExcludesSoftDeleted(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-000000000002"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")

	var eid string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID).Scan(&eid)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'en','Villain')`,
		eid, nameAttrID)
	for _, idx := range []int{1, 2} {
		pool.Exec(ctx,
			`INSERT INTO chapter_entity_links(entity_id,chapter_id,chapter_title,chapter_index,relevance) VALUES($1,gen_random_uuid(),'Ch',$2,'major')`,
			eid, idx)
	}
	// Soft-delete: leaves status='active', alive=true, links intact — the exact
	// state that leaks without the deleted_at filter.
	pool.Exec(ctx, `UPDATE glossary_entities SET deleted_at=now() WHERE entity_id=$1`, eid)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM chapter_entity_links WHERE entity_id=$1`, eid)
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id=$1`, eid)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newKnownEntitiesServer(t)
	srv.pool = pool
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/known-entities?min_frequency=1&status=active", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var resp []map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v — body=%s", err, w.Body.String())
	}
	if len(resp) != 0 {
		t.Fatalf("soft-deleted active entity MUST be excluded (public canon leak), got %d: %+v", len(resp), resp)
	}
}

// ── D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM + D-ANCHOR-PRELOAD-50-CAP ────────

// TestKnownEntities_InvalidStatusReturns400 — `status` used to be accepted and
// silently ignored (a write-only param). It is now honored, and a value outside
// the closed set is rejected rather than quietly matching nothing.
func TestKnownEntities_InvalidStatusReturns400(t *testing.T) {
	srv, token := newKnownEntitiesServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/known-entities?status=bogus", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad status: want 400, got %d body=%s", w.Code, w.Body.String())
	}
}

// knownEntitiesGet issues an authed GET with the given query string and decodes.
func knownEntitiesGet(t *testing.T, srv *Server, token, bookID, query string) []struct {
	EntityID string `json:"entity_id"`
	Name     string `json:"name"`
} {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/known-entities"+query, nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("query %q: want 200, got %d body=%s", query, w.Code, w.Body.String())
	}
	var resp []struct {
		EntityID string `json:"entity_id"`
		Name     string `json:"name"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v — body=%s", err, w.Body.String())
	}
	return resp
}

// TestKnownEntities_ProseLessStatusAndPaging is the DB regression for the three
// bugs /review-impl found in the WS-4B graph projection's glossary read:
//  1. min_frequency default 2 hid every entity of a PROSE-LESS book (0 chapter
//     links) — the exact scenario the projection exists for. min_frequency=0 must
//     return them (even 1 would not: the chapter join is a LEFT JOIN, COUNT=0).
//  2. `status` was never read → every caller's status=active was a silent no-op.
//  3. `limit` defaulted to 50 with no `offset`, so a bigger glossary was silently
//     truncated. offset must page deterministically (stable ORDER BY tiebreak).
func TestKnownEntities_ProseLessStatusAndPaging(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-000000000042"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")

	// Seed 3 entities with ZERO chapter links (a prose-less book).
	seed := func(name, status string) string {
		var eid string
		pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
			 VALUES($1,$2,$3,'{}') RETURNING entity_id`,
			bid, kindID, status,
		).Scan(&eid)
		pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
			 VALUES($1,$2,'en',$3)`, eid, nameAttrID, name)
		return eid
	}
	d1 := seed("DraftOne", "draft")
	d2 := seed("DraftTwo", "draft")
	a1 := seed("ActiveOne", "active")

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN ($1,$2,$3)`, d1, d2, a1)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bid)
	})

	srv, token := newKnownEntitiesServer(t)
	srv.pool = pool

	// (1) default min_frequency=2 hides all of them (this WAS the bug).
	if got := knownEntitiesGet(t, srv, token, bookID, ""); len(got) != 0 {
		t.Fatalf("default min_frequency should hide prose-less entities, got %d", len(got))
	}
	// min_frequency=0 returns all 3 — the fix the projection relies on.
	all := knownEntitiesGet(t, srv, token, bookID, "?min_frequency=0")
	if len(all) != 3 {
		t.Fatalf("min_frequency=0: want 3 prose-less entities, got %d: %+v", len(all), all)
	}

	// (2) status filter actually filters now.
	drafts := knownEntitiesGet(t, srv, token, bookID, "?min_frequency=0&status=draft")
	if len(drafts) != 2 {
		t.Errorf("status=draft: want 2, got %d: %+v", len(drafts), drafts)
	}
	actives := knownEntitiesGet(t, srv, token, bookID, "?min_frequency=0&status=active")
	if len(actives) != 1 || actives[0].EntityID != a1 {
		t.Errorf("status=active: want just %s, got %+v", a1, actives)
	}

	// (3) offset pages deterministically and covers the whole set exactly once.
	p1 := knownEntitiesGet(t, srv, token, bookID, "?min_frequency=0&limit=2&offset=0")
	p2 := knownEntitiesGet(t, srv, token, bookID, "?min_frequency=0&limit=2&offset=2")
	if len(p1) != 2 || len(p2) != 1 {
		t.Fatalf("paging: want 2+1, got %d+%d", len(p1), len(p2))
	}
	seen := map[string]bool{}
	for _, e := range append(p1, p2...) {
		if seen[e.EntityID] {
			t.Errorf("paging returned %s twice (unstable ORDER BY?)", e.EntityID)
		}
		seen[e.EntityID] = true
	}
	if len(seen) != 3 {
		t.Errorf("paging covered %d entities, want 3", len(seen))
	}
}
