package api

// Tests for GET /internal/books/{book_id}/entities — C12c-a.
// Unit tests (no DB) run always.
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sort"
	"testing"
)

// ── unit tests (no DB) ──────────────────────────────────────────────

// newEntitiesListServer reuses the export-test helpers with a fixed
// internal token. Mirrors newKnownEntitiesServer.
func newEntitiesListServer(t *testing.T) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, nil)
	token := "entities-list-test-token"
	srv.cfg.InternalServiceToken = token
	return srv, token
}

func TestListEntities_RequiresInternalToken(t *testing.T) {
	srv, _ := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/entities", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestListEntities_WrongTokenReturns401(t *testing.T) {
	srv, _ := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/entities", nil)
	req.Header.Set("X-Internal-Token", "wrong")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("wrong token: want 401, got %d", w.Code)
	}
}

func TestListEntities_BadUUIDReturns400(t *testing.T) {
	srv, token := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/not-a-uuid/entities", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad uuid: want 400, got %d", w.Code)
	}
}

// Cursor validation is checked BEFORE the DB query, so this test runs
// without a DB. Covers: invalid base64, non-JSON payload, missing
// entity_id, invalid UUID.
func TestListEntities_BadCursorReturns400(t *testing.T) {
	srv, token := newEntitiesListServer(t)
	cases := []struct {
		name   string
		cursor string
	}{
		{"invalid base64", "!!!not-base64!!!"},
		{"empty json", "e30"},                                    // `{}` b64 → no entity_id
		{"invalid uuid", "eyJlbnRpdHlfaWQiOiJub3QtYS11dWlkIn0"},   // {"entity_id":"not-a-uuid"} b64
		{"not json", "Zm9v"},                                      // `foo` b64
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet,
				"/internal/books/00000000-0000-0000-0000-000000000001/entities?cursor="+tc.cursor, nil)
			req.Header.Set("X-Internal-Token", token)
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusBadRequest {
				t.Errorf("%s: want 400, got %d body=%s", tc.name, w.Code, w.Body.String())
			}
		})
	}
}

// ── integration (requires DB) ──────────────────────────────────────

// TestListEntities_CursorWalk seeds 5 entities with names + aliases +
// short_descriptions, pages through at limit=2, and asserts:
//   - exactly the 5 seeded entities appear
//   - pages are sized 2, 2, 1 (last page has no next_cursor)
//   - ordering is entity_id ASC (UUID total ordering)
//   - name, kind_code, aliases, short_description all round-trip
func TestListEntities_CursorWalk(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-000000000c12"

	// Look up 'character' kind + its name/aliases/short_description attrs.
	var kindID, nameAttrID, aliasesAttrID, shortAttrID string
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
	_ = pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='short_description' LIMIT 1`,
		kindID,
	).Scan(&shortAttrID)
	// short_description attr may not exist in the default seed; fall
	// back to a fresh definition so the test covers the full join.
	if shortAttrID == "" {
		pool.QueryRow(ctx,
			`INSERT INTO attribute_definitions(kind_id,code,label,ui_type,sort_order,max_values)
			 VALUES($1,'short_description','Short description','text',99,1)
			 RETURNING attr_def_id`,
			kindID,
		).Scan(&shortAttrID)
	}

	seedEntity := func(name, aliasesJSON, shortDesc string) string {
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
		if aliasesJSON != "" {
			pool.Exec(ctx,
				`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
				 VALUES($1,$2,'en',$3)`,
				eid, aliasesAttrID, aliasesJSON,
			)
		}
		if shortDesc != "" {
			pool.Exec(ctx,
				`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
				 VALUES($1,$2,'en',$3)`,
				eid, shortAttrID, shortDesc,
			)
		}
		return eid
	}
	seeded := []string{
		seedEntity("Arthur", `["Art","King"]`, "The once and future king"),
		seedEntity("Merlin", `["Wizard"]`, ""),
		seedEntity("Lancelot", "", "First knight of the Round Table"),
		seedEntity("Guinevere", `["Queen"]`, ""),
		seedEntity("Mordred", "", "The betrayer"),
	}

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id = ANY($1)`, seeded)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	type item struct {
		EntityID         string   `json:"entity_id"`
		Name             string   `json:"name"`
		KindCode         string   `json:"kind_code"`
		Aliases          []string `json:"aliases"`
		ShortDescription *string  `json:"short_description"`
	}
	type resp struct {
		Items      []item  `json:"items"`
		NextCursor *string `json:"next_cursor"`
	}

	fetchPage := func(cursor string) resp {
		url := "/internal/books/" + bookID + "/entities?limit=2"
		if cursor != "" {
			url += "&cursor=" + cursor
		}
		req := httptest.NewRequest(http.MethodGet, url, nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
		}
		var r resp
		if err := json.Unmarshal(w.Body.Bytes(), &r); err != nil {
			t.Fatalf("decode: %v", err)
		}
		return r
	}

	page1 := fetchPage("")
	if len(page1.Items) != 2 || page1.NextCursor == nil {
		t.Fatalf("page1 wrong shape: items=%d cursor=%v", len(page1.Items), page1.NextCursor)
	}
	page2 := fetchPage(*page1.NextCursor)
	if len(page2.Items) != 2 || page2.NextCursor == nil {
		t.Fatalf("page2 wrong shape: items=%d cursor=%v", len(page2.Items), page2.NextCursor)
	}
	page3 := fetchPage(*page2.NextCursor)
	if len(page3.Items) != 1 || page3.NextCursor != nil {
		t.Fatalf("page3 wrong shape: items=%d cursor=%v", len(page3.Items), page3.NextCursor)
	}

	allIDs := []string{}
	for _, p := range []resp{page1, page2, page3} {
		for _, it := range p.Items {
			allIDs = append(allIDs, it.EntityID)
		}
	}
	sortedSeeded := append([]string{}, seeded...)
	sort.Strings(sortedSeeded)
	// Walk order MUST match entity_id ASC (UUID total ordering).
	for i, id := range allIDs {
		if id != sortedSeeded[i] {
			t.Errorf("walk[%d]: want %s, got %s", i, sortedSeeded[i], id)
		}
	}

	// Spot-check field round-trip on Arthur's row (first in UUID order?
	// not deterministic — find by name).
	var arthur *item
	for _, p := range []resp{page1, page2, page3} {
		for i := range p.Items {
			if p.Items[i].Name == "Arthur" {
				arthur = &p.Items[i]
			}
		}
	}
	if arthur == nil {
		t.Fatal("Arthur not in walk")
	}
	if arthur.KindCode != "character" {
		t.Errorf("Arthur kind: want character, got %s", arthur.KindCode)
	}
	if len(arthur.Aliases) != 2 || arthur.Aliases[0] != "Art" {
		t.Errorf("Arthur aliases: want [Art King], got %v", arthur.Aliases)
	}
	if arthur.ShortDescription == nil || *arthur.ShortDescription != "The once and future king" {
		t.Errorf("Arthur short_desc: want 'The once and future king', got %v", arthur.ShortDescription)
	}

	// Merlin has no short_description → must be JSON null (pointer nil).
	var merlin *item
	for _, p := range []resp{page1, page2, page3} {
		for i := range p.Items {
			if p.Items[i].Name == "Merlin" {
				merlin = &p.Items[i]
			}
		}
	}
	if merlin == nil {
		t.Fatal("Merlin not in walk")
	}
	if merlin.ShortDescription != nil {
		t.Errorf("Merlin short_desc: want null, got %v", *merlin.ShortDescription)
	}
}

// /review-impl MED#1 regression — the peek-ahead cursor logic must
// survive rows being dropped by the empty-name filter. Seeds 4
// entities where the 2nd is nameless; at limit=2 the DB returns 3
// rows (limit+1), one is filtered, so items has only 1 valid row in
// page1. Handler must STILL emit a cursor so page2 fetches the
// remainder (without this fix, pagination silently terminated early,
// dropping entities 3 & 4).
func TestListEntities_NameFilterDoesNotBreakPagination(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-000000c12c"

	var kindID, nameAttrID string
	pool.QueryRow(ctx,
		`SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`,
	).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID,
	).Scan(&nameAttrID)

	seed := func(name string) string {
		var eid string
		pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
			 VALUES($1,$2,'active','{}') RETURNING entity_id`,
			bookID, kindID,
		).Scan(&eid)
		if name != "" {
			pool.Exec(ctx,
				`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
				 VALUES($1,$2,'en',$3)`,
				eid, nameAttrID, name,
			)
		}
		return eid
	}
	seeded := []string{
		seed("Alpha"),
		seed(""), // nameless — filter skips
		seed("Charlie"),
		seed("Delta"),
	}

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id = ANY($1)`, seeded)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	type item struct {
		EntityID string `json:"entity_id"`
		Name     string `json:"name"`
	}
	type resp struct {
		Items      []item  `json:"items"`
		NextCursor *string `json:"next_cursor"`
	}

	fetch := func(cursor string) resp {
		url := "/internal/books/" + bookID + "/entities?limit=2"
		if cursor != "" {
			url += "&cursor=" + cursor
		}
		req := httptest.NewRequest(http.MethodGet, url, nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
		}
		var r resp
		json.Unmarshal(w.Body.Bytes(), &r)
		return r
	}

	// Page 1: DB returns 3 rows (limit=2 peek-ahead=3). Row 2 is
	// nameless → filtered → items has Alpha (if ordered first).
	// The 3rd row triggers rowsScanned>limit → cursor emitted.
	page1 := fetch("")
	if page1.NextCursor == nil {
		t.Fatal("page1 cursor: want non-nil (more data exists), got nil")
	}

	// Walk: all non-empty names must appear across pages.
	collected := []string{}
	for _, it := range page1.Items {
		collected = append(collected, it.Name)
	}
	cursor := *page1.NextCursor
	for cursor != "" {
		p := fetch(cursor)
		for _, it := range p.Items {
			collected = append(collected, it.Name)
		}
		if p.NextCursor == nil {
			break
		}
		cursor = *p.NextCursor
	}

	sort.Strings(collected)
	want := []string{"Alpha", "Charlie", "Delta"}
	if len(collected) != len(want) {
		t.Fatalf("walk missed entities: want %v, got %v", want, collected)
	}
	for i := range want {
		if collected[i] != want[i] {
			t.Errorf("walk[%d]: want %s, got %s", i, want[i], collected[i])
		}
	}
}
