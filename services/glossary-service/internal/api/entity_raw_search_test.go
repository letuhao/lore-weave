package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// DB integration tests for the glossary list overhaul backend (P2 sort + P3 raw
// search). Require GLOSSARY_TEST_DB_URL (openTestDB skips otherwise). They drive
// the PUBLIC list route (/v1/glossary/books/{id}/entities) end to end so the
// sort whitelist + the raw search SQL (trigram + cached_name/cached_aliases) are
// exercised against a real Postgres, not just the pure helpers.

func lookupCharacterAttrs(t *testing.T, f *versionFixture) (kindID, nameAttr, aliasesAttr string) {
	t.Helper()
	ctx := context.Background()
	f.srv.pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	f.srv.pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttr)
	_ = f.srv.pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='aliases' LIMIT 1`,
		kindID).Scan(&aliasesAttr)
	if aliasesAttr == "" {
		f.srv.pool.QueryRow(ctx,
			`INSERT INTO attribute_definitions(kind_id,code,name,field_type,is_required,is_system,sort_order)
			 VALUES($1,'aliases','Aliases','text',false,true,2) RETURNING attr_def_id`,
			kindID).Scan(&aliasesAttr)
	}
	return
}

// seed inserts an entity with name + optional aliases into f's book.
func seedNamed(t *testing.T, f *versionFixture, kindID, nameAttr, aliasesAttr, name, aliasesJSON string) string {
	t.Helper()
	ctx := context.Background()
	var eid string
	if err := f.srv.pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		f.bookID, kindID).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	if _, err := f.srv.pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'en',$3)`, eid, nameAttr, name); err != nil {
		t.Fatalf("seed name eav: %v", err)
	}
	if aliasesJSON != "" && aliasesAttr != "" {
		if _, err := f.srv.pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
			 VALUES($1,$2,'en',$3)`, eid, aliasesAttr, aliasesJSON); err != nil {
			t.Fatalf("seed aliases eav: %v", err)
		}
	}
	return eid
}

func (f *versionFixture) listEntities(t *testing.T, query string) entityListResp {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+f.bookID.String()+"/entities?"+query, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("list (%s): want 200, got %d %s", query, w.Code, w.Body.String())
	}
	var resp entityListResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return resp
}

func TestListEntities_SortByName(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool) // seeds one entity "Nezha"
	kindID, nameAttr, aliasesAttr := lookupCharacterAttrs(t, f)

	seedNamed(t, f, kindID, nameAttr, aliasesAttr, "Zorro", "")
	seedNamed(t, f, kindID, nameAttr, aliasesAttr, "Aaron", "")
	seedNamed(t, f, kindID, nameAttr, aliasesAttr, "Marlow", "")

	resp := f.listEntities(t, "sort=name")
	// Collect the latin display names in returned order; they must be ascending.
	var names []string
	for _, it := range resp.Items {
		names = append(names, it.DisplayName)
	}
	// Find the positions of our known names — they must be in ascending order.
	want := []string{"Aaron", "Marlow", "Nezha", "Zorro"}
	var seen []string
	for _, n := range names {
		for _, w := range want {
			if n == w {
				seen = append(seen, n)
			}
		}
	}
	if len(seen) != len(want) {
		t.Fatalf("sort=name: missing entities, got order %v", seen)
	}
	for i := range want {
		if seen[i] != want[i] {
			t.Errorf("sort=name order[%d]: want %s, got %s (full: %v)", i, want[i], seen[i], seen)
		}
	}

	// Descending reverses it.
	respDesc := f.listEntities(t, "sort=name_desc")
	var firstKnown string
	for _, it := range respDesc.Items {
		for _, w := range want {
			if it.DisplayName == w {
				firstKnown = it.DisplayName
				break
			}
		}
		if firstKnown != "" {
			break
		}
	}
	if firstKnown != "Zorro" {
		t.Errorf("sort=name_desc: first known should be Zorro, got %s", firstKnown)
	}
}

func TestListEntities_RawSearchCJKSubstring(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	kindID, nameAttr, aliasesAttr := lookupCharacterAttrs(t, f)

	seedNamed(t, f, kindID, nameAttr, aliasesAttr, "林黛玉", `["黛玉儿"]`)
	seedNamed(t, f, kindID, nameAttr, aliasesAttr, "孙悟空", `["美猴王"]`)

	// Substring "黛玉" hits the name 林黛玉 (and its alias) — exact-substring leg.
	resp := f.listEntities(t, "search_mode=raw&search=黛玉")
	if resp.Total != 1 || len(resp.Items) != 1 {
		t.Fatalf("raw CJK: want total=1, got total=%d items=%d", resp.Total, len(resp.Items))
	}
	it := resp.Items[0]
	if it.DisplayName != "林黛玉" {
		t.Errorf("raw CJK: want 林黛玉, got %s", it.DisplayName)
	}
	if it.Match == nil {
		t.Fatal("raw CJK: expected a match payload")
	}
	if it.Match.FieldCode != "name" {
		t.Errorf("raw CJK match field: want name, got %s", it.Match.FieldCode)
	}
	// "黛玉" is at rune offset [1,3] within "林黛玉".
	if len(it.Match.Highlights) != 1 || it.Match.Highlights[0][0] != 1 || it.Match.Highlights[0][1] != 3 {
		t.Errorf("raw CJK highlight: want [[1,3]], got %v", it.Match.Highlights)
	}
}

func TestListEntities_RawSearchAliasMatch(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	kindID, nameAttr, aliasesAttr := lookupCharacterAttrs(t, f)
	if aliasesAttr == "" {
		t.Skip("no aliases attr available")
	}

	seedNamed(t, f, kindID, nameAttr, aliasesAttr, "Sun Wukong", `["美猴王","齐天大圣"]`)

	// "美猴" only appears in the alias, not the name.
	resp := f.listEntities(t, "search_mode=raw&search=美猴")
	if resp.Total != 1 || len(resp.Items) != 1 {
		t.Fatalf("raw alias: want total=1, got total=%d items=%d", resp.Total, len(resp.Items))
	}
	it := resp.Items[0]
	if it.Match == nil || it.Match.FieldCode != "alias" {
		t.Errorf("raw alias: want field=alias, got %v", it.Match)
	}
}

func TestListEntities_SimpleModeHasNoMatchPayload(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	resp := f.listEntities(t, "search=Nezha")
	if len(resp.Items) != 1 {
		t.Fatalf("simple search: want 1, got %d", len(resp.Items))
	}
	if resp.Items[0].Match != nil {
		t.Errorf("simple mode must not emit a match payload, got %v", resp.Items[0].Match)
	}
}

func TestListEntities_RawSearchQueryTooLong(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	long := make([]rune, maxEntitySearchRunes+1)
	for i := range long {
		long[i] = 'a'
	}
	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+f.bookID.String()+"/entities?search_mode=raw&search="+string(long), nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("over-long query: want 400, got %d", w.Code)
	}
}
