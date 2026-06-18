package api

// Tests for POST /internal/books/{book_id}/entities/by-ids (mui #4 G-1).
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEntitiesByIDs_FetchesShapeAndDropsAbsent(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0002-0000000b4001"
	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttrID)

	seed := func(name, shortDesc, status string, deleted bool) string {
		var eid string
		pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags,short_description,deleted_at)
			 VALUES($1,$2,$3,'{}',$4, CASE WHEN $5 THEN now() ELSE NULL END) RETURNING entity_id`,
			bookID, kindID, status, nullIfEmpty(shortDesc), deleted,
		).Scan(&eid)
		// name attr → K2a trigger populates cached_name
		pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
			 VALUES($1,$2,'zh',$3)`, eid, nameAttrID, name)
		return eid
	}

	id1 := seed("姜子牙", "founding strategist", "active", false)
	id2 := seed("哪吒", "", "active", false)
	idDeleted := seed("废弃", "x", "active", true)

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN
			(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	body, _ := json.Marshal(map[string]any{
		"entity_ids": []string{id1, id2, idDeleted, "00000000-0000-0000-0000-0000deadbeef", "not-a-uuid"},
	})
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/entities/by-ids", bytes.NewReader(body))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp struct {
		Items []glossaryEntityForContext `json:"items"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}

	// id1+id2 present; deleted + absent + malformed dropped.
	got := map[string]glossaryEntityForContext{}
	for _, it := range resp.Items {
		got[it.EntityID] = it
	}
	if len(resp.Items) != 2 {
		t.Fatalf("want 2 items, got %d: %+v", len(resp.Items), resp.Items)
	}
	if _, ok := got[idDeleted]; ok {
		t.Error("soft-deleted entity leaked into by-ids result")
	}
	e1, ok := got[id1]
	if !ok {
		t.Fatal("id1 missing")
	}
	if e1.CachedName == nil || *e1.CachedName != "姜子牙" {
		t.Errorf("cached_name not populated: %+v", e1.CachedName)
	}
	if e1.ShortDescription == nil || *e1.ShortDescription != "founding strategist" {
		t.Errorf("short_description not returned: %+v", e1.ShortDescription)
	}
	if e1.KindCode != "character" {
		t.Errorf("want kind_code=character, got %q", e1.KindCode)
	}
}

func TestEntitiesByIDs_EmptyBodyReturnsEmpty(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	body, _ := json.Marshal(map[string]any{"entity_ids": []string{}})
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/00000000-0000-0000-0002-0000000b4002/entities/by-ids", bytes.NewReader(body))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d", w.Code)
	}
	var resp struct {
		Items []glossaryEntityForContext `json:"items"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if len(resp.Items) != 0 {
		t.Errorf("want empty items, got %d", len(resp.Items))
	}
}
