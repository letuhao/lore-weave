package api

// Tests for the widened GET /v1/glossary/books/{book_id}/entity-names surface
// (Slice C / F-H9 / PH26): keyset pagination + `truncated`/`next_cursor`, and a
// status filter widened to ALL non-deleted entities (draft/inactive/active),
// with soft-deleted rows excluded.
//
// Unit tests (no DB) run always. DB integration tests require GLOSSARY_TEST_DB_URL
// and skip otherwise (openTestDB), mirroring entities_list_test.go.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sort"
	"testing"
	"time"

	"github.com/google/uuid"
)

// entityNameOut / entityNamesPageOut mirror the handler's JSON page shape.
type entityNameOut struct {
	EntityID    string  `json:"entity_id"`
	DisplayName string  `json:"display_name"`
	KindCode    *string `json:"kind_code"`
}

type entityNamesPageOut struct {
	Items      []entityNameOut `json:"items"`
	Truncated  bool            `json:"truncated"`
	NextCursor *string         `json:"next_cursor"`
}

// ── unit tests (no DB) ──────────────────────────────────────────────

// TestEntityNames_RequireAuth — the route rejects a missing/invalid Bearer with
// 401 before any grant/DB work (mirrors listEntityNames' guard order).
func TestEntityNames_RequireAuth(t *testing.T) {
	srv := newExportServer(t, nil)
	book := "00000000-0000-0000-0000-000000000001"
	path := "/v1/glossary/books/" + book + "/entity-names"

	t.Run("no-token", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusUnauthorized {
			t.Errorf("no token: want 401, got %d", w.Code)
		}
	})
	t.Run("bad-token", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("Authorization", "Bearer not.a.valid.token")
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusUnauthorized {
			t.Errorf("bad token: want 401, got %d", w.Code)
		}
	})
}

// TestEntityNames_BadCursorReturns400 — a valid token + View grant but a malformed
// ?cursor= is a 400 (decoded before any DB query, so no pool needed). Mirrors the
// bad-cursor cases in entities_list_test.go.
func TestEntityNames_BadCursorReturns400(t *testing.T) {
	srv := newExportServer(t, nil)
	grantStub := stubViewAccess(t)
	srv.cfg.BookServiceURL = grantStub.URL
	srv.cfg.InternalServiceToken = "tkn"
	srv.grantClient = buildGrantClient(grantStub.URL, "tkn")

	book := uuid.NewString()
	token := makeExportToken(t, uuid.NewString())

	cases := []struct {
		name   string
		cursor string
	}{
		{"invalid base64", "!!!not-base64!!!"},
		{"empty json", "e30"},                                  // `{}` b64 → no entity_id
		{"invalid uuid", "eyJlbnRpdHlfaWQiOiJub3QtYS11dWlkIn0"}, // {"entity_id":"not-a-uuid"} b64
		{"not json", "Zm9v"},                                    // `foo` b64
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet,
				"/v1/glossary/books/"+book+"/entity-names?cursor="+tc.cursor, nil)
			req.Header.Set("Authorization", "Bearer "+token)
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusBadRequest {
				t.Errorf("%s: want 400, got %d body=%s", tc.name, w.Code, w.Body.String())
			}
		})
	}
}

// ── DB integration test ─────────────────────────────────────────────

// TestEntityNames_PaginatesAndWidensStatus seeds named entities across statuses
// (active, draft, inactive) plus one soft-deleted "ghost" and one term-keyed
// terminology entity, pages at limit=2, and asserts:
//   - the walk terminates: the final page has truncated=false + nil next_cursor
//   - EVERY non-deleted named entity appears exactly once (draft + inactive
//     included — the widened status filter), regardless of status
//   - a term-keyed entity (identity under the 'term' attribute, not 'name') appears
//     — the regression guard for the 'name'-only resolver drop bug
//   - the soft-deleted entity NEVER appears (deleted_at IS NULL still holds)
func TestEntityNames_PaginatesAndWidensStatus(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0003-0000000e0a11"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)

	kindID := bookKindID(t, pool, bid, "character")
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
	// A term-keyed kind (terminology) labels its identity under the 'term' attribute, NOT 'name'.
	// The name map MUST resolve those too — the regression guard for the 'name'-only drop bug
	// (the resolver mirrors loadEntityDetail's `code IN ('name','term')`).
	termKindID := bookKindID(t, pool, bid, "terminology")
	termAttrID := bookAttrID(t, pool, bid, termKindID, "term")

	// seedAs inserts an entity under (kindID, attrID) with the given status + optional soft-delete
	// tombstone, and (when name != "") an EAV value under attrID the handler resolves as display_name.
	seedAs := func(kindID, attrID uuid.UUID, name, status string, deleted bool) string {
		var deletedAt any = nil
		if deleted {
			deletedAt = time.Now()
		}
		var eid string
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags,deleted_at)
			 VALUES($1,$2,$3,'{}',$4) RETURNING entity_id`,
			bid, kindID, status, deletedAt,
		).Scan(&eid); err != nil {
			t.Fatalf("seed %q: %v", name, err)
		}
		if name != "" {
			if _, err := pool.Exec(ctx,
				`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
				 VALUES($1,$2,'en',$3)`, eid, attrID, name); err != nil {
				t.Fatalf("seed name %q: %v", name, err)
			}
		}
		return eid
	}
	seed := func(name, status string, deleted bool) string {
		return seedAs(kindID, nameAttrID, name, status, deleted)
	}

	seeded := []string{
		seed("Active1", "active", false),
		seed("DraftE", "draft", false),      // non-active, non-deleted → MUST appear
		seed("InactiveE", "inactive", false), // non-active, non-deleted → MUST appear
		seed("Active2", "active", false),
		seed("Ghost", "active", true), // soft-deleted → MUST NOT appear
		// A terminology entity whose identity lives ONLY in the 'term' EAV (no 'name'): with a
		// 'name'-only resolver this row resolved to blank and was dropped. MUST appear now.
		seedAs(termKindID, termAttrID, "QiTerm", "active", false),
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id = ANY($1)`, seeded)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv := newExportServer(t, nil)
	srv.pool = pool
	grantStub := stubViewAccess(t)
	srv.cfg.BookServiceURL = grantStub.URL
	srv.cfg.InternalServiceToken = "ptk"
	srv.grantClient = buildGrantClient(grantStub.URL, "ptk")
	token := makeExportToken(t, uuid.NewString())

	fetch := func(cursor string) entityNamesPageOut {
		url := "/v1/glossary/books/" + bookID + "/entity-names?limit=2"
		if cursor != "" {
			url += "&cursor=" + cursor
		}
		req := httptest.NewRequest(http.MethodGet, url, nil)
		req.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("entity-names: want 200, got %d body=%s", w.Code, w.Body.String())
		}
		var p entityNamesPageOut
		if err := json.Unmarshal(w.Body.Bytes(), &p); err != nil {
			t.Fatalf("decode: %v", err)
		}
		return p
	}

	// Walk every page following next_cursor until truncated=false.
	collected := []string{}
	pages := 0
	cursor := ""
	for {
		p := fetch(cursor)
		pages++
		for _, it := range p.Items {
			collected = append(collected, it.DisplayName)
		}
		if !p.Truncated {
			if p.NextCursor != nil {
				t.Errorf("final page: truncated=false but next_cursor=%v (want nil)", *p.NextCursor)
			}
			break
		}
		if p.NextCursor == nil {
			t.Fatal("truncated=true but next_cursor is nil — pagination cannot advance")
		}
		cursor = *p.NextCursor
		if pages > 20 {
			t.Fatal("pagination did not terminate")
		}
	}

	// 5 non-deleted named entities (incl. the term-keyed one), paged 2 at a time → ≥3 pages.
	if pages < 2 {
		t.Errorf("want ≥2 pages for 5 items at limit=2, got %d", pages)
	}

	sort.Strings(collected)
	want := []string{"Active1", "Active2", "DraftE", "InactiveE", "QiTerm"}
	if len(collected) != len(want) {
		t.Fatalf("collected names: want %v, got %v", want, collected)
	}
	for i := range want {
		if collected[i] != want[i] {
			t.Errorf("collected[%d]: want %s, got %s", i, want[i], collected[i])
		}
	}
	// Explicit soft-delete exclusion assertion (belt-and-suspenders over the count).
	for _, n := range collected {
		if n == "Ghost" {
			t.Error("soft-deleted 'Ghost' leaked into entity-names")
		}
	}
}
