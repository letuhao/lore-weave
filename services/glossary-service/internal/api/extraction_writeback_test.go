package api

// Tests for the KG→glossary writeback contract (mui #1, BE-2):
//   - default_tags applied on CREATE (ai-suggested marks AI drafts)
//   - tombstone: an AI writeback skips names tagged ai-rejected
//   - backward-compat: no default_tags → no tags, no tombstone gate
//
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"slices"
	"testing"
)

// postExtract drives POST /internal/books/{book}/extract-entities and returns
// the decoded response. Fails the test on a non-200.
func postExtract(t *testing.T, srv *Server, token, bookID string, body map[string]any) map[string]any {
	t.Helper()
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/extract-entities",
		bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("extract-entities: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var r map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &r); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return r
}

// TestBulkExtract_DefaultTagsAppliedOnCreate proves an AI writeback batch
// lands a new entity as a reviewable draft tagged ai-suggested.
func TestBulkExtract_DefaultTagsAppliedOnCreate(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1001"
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN
			(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	resp := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"default_tags":    []string{"ai-suggested"},
		"entities": []map[string]any{
			{"kind_code": "character", "name": "哪吒"},
		},
	})
	if got := resp["created"]; got != float64(1) {
		t.Fatalf("want created=1, got %v (resp=%v)", got, resp)
	}

	var status string
	var tags []string
	err := pool.QueryRow(ctx,
		`SELECT ge.status, ge.tags
		   FROM glossary_entities ge
		   JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		   JOIN system_kind_attributes ad ON ad.attr_def_id = eav.attr_def_id
		  WHERE ge.book_id=$1 AND ad.code='name' AND eav.original_value='哪吒'`,
		bookID).Scan(&status, &tags)
	if err != nil {
		t.Fatalf("query created entity: %v", err)
	}
	if status != "draft" {
		t.Errorf("want status=draft, got %q", status)
	}
	if !slices.Contains(tags, "ai-suggested") {
		t.Errorf("want tags to contain ai-suggested, got %v", tags)
	}
}

// TestBulkExtract_TombstoneSkipsRejectedName proves a name the user rejected
// (tag ai-rejected) is not re-proposed by an AI writeback — skipped, untouched.
func TestBulkExtract_TombstoneSkipsRejectedName(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1002"
	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttrID)

	// Seed a previously-rejected entity named 李靖 (tombstoned).
	var rejectedID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
		 VALUES($1,$2,'inactive','{ai-suggested,ai-rejected}') RETURNING entity_id`,
		bookID, kindID).Scan(&rejectedID)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','李靖')`, rejectedID, nameAttrID)

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN
			(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	resp := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"default_tags":    []string{"ai-suggested"},
		"entities": []map[string]any{
			{"kind_code": "character", "name": "李靖"},
		},
	})
	if resp["created"] != float64(0) || resp["skipped"] != float64(1) {
		t.Fatalf("want created=0 skipped=1, got %v", resp)
	}
	ents := resp["entities"].([]any)
	first := ents[0].(map[string]any)
	if first["status"] != "skipped" || first["skip_reason"] != "tombstoned" {
		t.Errorf("want skipped/tombstoned, got %v", first)
	}

	// No new row created; exactly the one seeded entity remains.
	var count int
	pool.QueryRow(ctx, `SELECT COUNT(*) FROM glossary_entities WHERE book_id=$1`, bookID).Scan(&count)
	if count != 1 {
		t.Errorf("tombstone leaked a row: want 1 entity, got %d", count)
	}
}

// TestBulkExtract_NoDefaultTagsBackwardCompatible proves a normal (non-AI)
// batch still ignores the tombstone gate and creates with empty tags.
func TestBulkExtract_NoDefaultTagsBackwardCompatible(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1003"
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN
			(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	resp := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "杨戬"},
		},
	})
	if resp["created"] != float64(1) {
		t.Fatalf("want created=1, got %v", resp)
	}

	var tags []string
	pool.QueryRow(ctx,
		`SELECT ge.tags FROM glossary_entities ge
		   JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		   JOIN system_kind_attributes ad ON ad.attr_def_id = eav.attr_def_id
		  WHERE ge.book_id=$1 AND ad.code='name' AND eav.original_value='杨戬'`,
		bookID).Scan(&tags)
	if len(tags) != 0 {
		t.Errorf("want empty tags for non-AI create, got %v", tags)
	}
}
