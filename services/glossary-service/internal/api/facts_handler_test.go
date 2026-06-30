package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// TestFactsHTTP exercises the F4-live glossary fact surface the KAL reads/writes through:
// facts emitted by the writeback are READ back via GET .../facts; a direct POST .../facts/append
// opens a new fact; GET reflects it; POST .../facts/retract closes it. End-to-end over the router.
func TestFactsHTTP(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrate.RunChain(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	bookID := "00000000-0000-0000-0001-0000000a14f4"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	chapterID := uuid.New()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_facts WHERE book_id=$1`, bid)             //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM episodes WHERE book_id=$1`, bid)                 //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM extraction_writeback_log WHERE book_id=$1`, bid) //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN
			(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bid) //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bid) //nolint:errcheck
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	// seed facts via the writeback (Path A)
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh", "chapter_id": chapterID.String(),
		"content_hash": "h14f4", "writeback_key": "wbk-14f4", "chapter_ordinal": 3,
		"entities": []map[string]any{
			{"kind_code": "character", "name": "苏寒", "attributes": map[string]any{"境界": "练气"}},
		},
	})
	var entityID string
	if err := pool.QueryRow(ctx, `
		SELECT ge.entity_id FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id=ge.entity_id
		JOIN book_attributes ba ON ba.attr_id=eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='name' AND eav.original_value='苏寒'`, bid).Scan(&entityID); err != nil {
		t.Fatalf("find entity: %v", err)
	}

	get := func(path string) []map[string]any {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("GET %s: %d body=%s", path, w.Code, w.Body.String())
		}
		var r struct {
			Items []map[string]any `json:"items"`
		}
		json.Unmarshal(w.Body.Bytes(), &r) //nolint:errcheck
		return r.Items
	}
	post := func(path string, body map[string]any) (int, map[string]any) {
		raw, _ := json.Marshal(body)
		req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(raw))
		req.Header.Set("X-Internal-Token", token)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		var r map[string]any
		json.Unmarshal(w.Body.Bytes(), &r) //nolint:errcheck
		return w.Code, r
	}

	// READ: the writeback's facts come back (name + 境界, valid_from 3, open)
	facts := get("/internal/books/" + bookID + "/entities/" + entityID + "/facts")
	byAttr := map[string]map[string]any{}
	for _, f := range facts {
		byAttr[f["attr_or_predicate"].(string)] = f
	}
	if byAttr["name"]["value"] != "苏寒" || byAttr["境界"]["value"] != "练气" {
		t.Fatalf("GET facts = %v, want name=苏寒 & 境界=练气", facts)
	}
	if byAttr["境界"]["valid_from_ordinal"].(float64) != 3 {
		t.Fatalf("境界 valid_from = %v, want 3", byAttr["境界"]["valid_from_ordinal"])
	}

	// WRITE: append a superseding 境界 at chapter 9 → GET reflects 突破境 as current
	code, ar := post("/internal/books/"+bookID+"/facts/append", map[string]any{
		"entity_id": entityID, "fact_kind": "attribute", "attr_or_predicate": "境界",
		"value": "突破境", "valid_from_ordinal": 9,
	})
	if code != http.StatusOK || ar["inserted"] != true {
		t.Fatalf("append: code=%d resp=%v", code, ar)
	}
	facts = get("/internal/books/" + bookID + "/entities/" + entityID + "/facts")
	cur := ""
	for _, f := range facts {
		if f["attr_or_predicate"] == "境界" {
			cur = f["value"].(string)
		}
	}
	if cur != "突破境" {
		t.Fatalf("after append, current 境界 = %q, want 突破境", cur)
	}

	// timeline shows both 境界 versions (the change feed)
	tl := get("/internal/books/" + bookID + "/entities/" + entityID + "/timeline?limit=50")
	jingCount := 0
	for _, f := range tl {
		if f["attr_or_predicate"] == "境界" {
			jingCount++
		}
	}
	if jingCount < 2 {
		t.Fatalf("timeline 境界 versions = %d, want >=2 (development history)", jingCount)
	}

	// RETRACT the appended fact → current reverts to 练气
	var appendedID string
	pool.QueryRow(ctx, `SELECT fact_id FROM entity_facts WHERE entity_id=$1 AND value='突破境'`, uuid.MustParse(entityID)).Scan(&appendedID) //nolint:errcheck
	code, rr := post("/internal/books/"+bookID+"/facts/retract", map[string]any{
		"fact_ids": []string{appendedID}, "reason": "retract",
	})
	if code != http.StatusOK {
		t.Fatalf("retract: code=%d resp=%v", code, rr)
	}
	facts = get("/internal/books/" + bookID + "/entities/" + entityID + "/facts")
	for _, f := range facts {
		if f["attr_or_predicate"] == "境界" && f["value"] != "练气" {
			t.Fatalf("after retract, 境界 = %v, want 练气 (chain re-stitched)", f["value"])
		}
	}

	// RESOLVE: a known name resolves to the existing entity (no create); a new name creates.
	code, rsv := post("/internal/books/"+bookID+"/facts/resolve-entity", map[string]any{"name": "苏寒", "kind": "character"})
	if code != http.StatusOK || rsv["created"] != false || rsv["entity_id"] != entityID {
		t.Fatalf("resolve known: code=%d resp=%v (want existing %s, created=false)", code, rsv, entityID)
	}
	code, rsv2 := post("/internal/books/"+bookID+"/facts/resolve-entity", map[string]any{"name": "未见之人", "kind": "character"})
	if code != http.StatusOK || rsv2["created"] != true || rsv2["entity_id"] == "" {
		t.Fatalf("resolve new: code=%d resp=%v (want created=true)", code, rsv2)
	}
	// resolving the just-created name again returns the same id (idempotent resolve)
	code, rsv3 := post("/internal/books/"+bookID+"/facts/resolve-entity", map[string]any{"name": "未见之人", "kind": "character"})
	if code != http.StatusOK || rsv3["created"] != false || rsv3["entity_id"] != rsv2["entity_id"] {
		t.Fatalf("re-resolve new: code=%d resp=%v (want same id, created=false)", code, rsv3)
	}
}
