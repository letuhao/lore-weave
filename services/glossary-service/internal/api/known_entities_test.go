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

	// Look up the 'character' kind + its name/aliases attribute defs.
	var kindID, nameAttrID, aliasesAttrID string
	pool.QueryRow(ctx,
		`SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`,
	).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID,
	).Scan(&nameAttrID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='aliases' LIMIT 1`,
		kindID,
	).Scan(&aliasesAttrID)

	// Seed two entities.
	seedEntity := func(name, aliasesJSON string) string {
		var eid string
		pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
			 VALUES($1,$2,'active','{}') RETURNING entity_id`,
			bookID, kindID,
		).Scan(&eid)
		pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
			 VALUES($1,$2,'en',$3)`,
			eid, nameAttrID, name,
		)
		if aliasesAttrID != "" && aliasesJSON != "" {
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
