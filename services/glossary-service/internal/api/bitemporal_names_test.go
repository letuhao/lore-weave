package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// TestBitemporalNames verifies F1g (§12.4.3): the writeback emits the name as a
// first-class `name` fact and aliases as `alias` multi facts; a later name supersedes;
// and an AS-OF read returns the name valid at that chapter (spoiler-free naming, §6B).
func TestBitemporalNames(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrate.RunChain(ctx, pool); err != nil { // incl. 0048 conversion
		t.Fatalf("migrate: %v", err)
	}
	bookID := "00000000-0000-0000-0001-0000000a1f19"
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

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh", "chapter_id": chapterID.String(),
		"content_hash": "h1f19", "writeback_key": "wbk-1f19", "chapter_ordinal": 1,
		"entities": []map[string]any{
			{"kind_code": "character", "name": "张三",
				"attributes": map[string]any{"aliases": []string{"张兄", "三公子"}}},
		},
	})
	var entityID uuid.UUID
	if err := pool.QueryRow(ctx, `
		SELECT ge.entity_id FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id=ge.entity_id
		JOIN book_attributes ba ON ba.attr_id=eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='name' AND eav.original_value='张三'`, bid).Scan(&entityID); err != nil {
		t.Fatalf("find entity: %v", err)
	}

	// name is a `name` fact; aliases are `alias` multi facts; NO `attribute` name/aliases facts.
	var nameKind string
	if err := pool.QueryRow(ctx, `
		SELECT fact_kind FROM entity_facts
		WHERE entity_id=$1 AND attr_or_predicate='name' AND invalidated_at IS NULL`, entityID).Scan(&nameKind); err != nil {
		t.Fatalf("name fact: %v", err)
	}
	if nameKind != "name" {
		t.Fatalf("name fact_kind = %q, want name", nameKind)
	}
	var aliasCount, badAttr int
	pool.QueryRow(ctx, `SELECT count(*) FROM entity_facts WHERE entity_id=$1 AND fact_kind='alias' AND invalidated_at IS NULL`, entityID).Scan(&aliasCount) //nolint:errcheck
	pool.QueryRow(ctx, `SELECT count(*) FROM entity_facts WHERE entity_id=$1 AND fact_kind='attribute' AND attr_or_predicate IN ('name','aliases') AND invalidated_at IS NULL`, entityID).Scan(&badAttr) //nolint:errcheck
	if aliasCount != 2 {
		t.Fatalf("alias facts = %d, want 2 (张兄, 三公子)", aliasCount)
	}
	if badAttr != 0 {
		t.Fatalf("found %d leftover attribute name/aliases facts (F1g reconcile broken)", badAttr)
	}

	// A later chapter renames 张三 → 张老 (append a name fact @500).
	raw, _ := json.Marshal(map[string]any{
		"entity_id": entityID.String(), "fact_kind": "name", "attr_or_predicate": "name",
		"value": "张老", "valid_from_ordinal": 500,
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/books/"+bookID+"/facts/append", bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("append name@500: %d %s", w.Code, w.Body.String())
	}

	// AS-OF name (spoiler-free): @300 → 张三 ; @600 → 张老.
	nameAsOf := func(n int) string {
		req := httptest.NewRequest(http.MethodGet,
			"/internal/books/"+bookID+"/entities/"+entityID.String()+"/facts?as_of="+strconv.Itoa(n), nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		var r struct {
			Items []map[string]any `json:"items"`
		}
		json.Unmarshal(w.Body.Bytes(), &r) //nolint:errcheck
		for _, f := range r.Items {
			if f["attr_or_predicate"] == "name" {
				return f["value"].(string)
			}
		}
		return ""
	}
	if got := nameAsOf(300); got != "张三" {
		t.Fatalf("name as-of 300 = %q, want 张三 (pre-rename)", got)
	}
	if got := nameAsOf(600); got != "张老" {
		t.Fatalf("name as-of 600 = %q, want 张老 (post-rename)", got)
	}
}
