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

// TestFoldLoop verifies the F2-app canonical fold loop on the glossary side: a fact write
// marks the entity dirty; GET fold-dirty serves it with its bounded facts + fingerprint;
// POST fold-snapshot writes the canonical + compare-and-clears dirty; GET canonical returns
// the fresh snapshot; a NEW fact makes the snapshot stale → GET canonical degrades to
// canon-content and re-flags dirty.
func TestFoldLoop(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrate.RunChain(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	bookID := "00000000-0000-0000-0001-0000000a1f02"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	chapterID := uuid.New()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM canonical_snapshot WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bid) //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM canonical_fold_state WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bid) //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM entity_facts WHERE book_id=$1`, bid)             //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM episodes WHERE book_id=$1`, bid)                 //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM extraction_writeback_log WHERE book_id=$1`, bid) //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bid) //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bid) //nolint:errcheck
	})
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh", "chapter_id": chapterID.String(),
		"content_hash": "h1f02", "writeback_key": "wbk-1f02", "chapter_ordinal": 5,
		"entities": []map[string]any{
			{"kind_code": "character", "name": "李四", "attributes": map[string]any{"境界": "金丹"}},
		},
	})
	var entityID string
	pool.QueryRow(ctx, `
		SELECT ge.entity_id FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id=ge.entity_id
		JOIN book_attributes ba ON ba.attr_id=eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='name' AND eav.original_value='李四'`, bid).Scan(&entityID) //nolint:errcheck

	doGET := func(path string) map[string]any {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("GET %s: %d %s", path, w.Code, w.Body.String())
		}
		var r map[string]any
		json.Unmarshal(w.Body.Bytes(), &r) //nolint:errcheck
		return r
	}
	doPOST := func(path string, body map[string]any) int {
		raw, _ := json.Marshal(body)
		req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(raw))
		req.Header.Set("X-Internal-Token", token)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		return w.Code
	}

	// the writeback flagged this entity dirty
	if n := srv.foldDirtyCount(ctx, bid); n < 1 {
		t.Fatalf("expected >=1 dirty entity after writeback, got %d", n)
	}

	// fetch the fold work item + its fingerprint
	dirty := doGET("/internal/books/" + bookID + "/fold-dirty")
	items, _ := dirty["items"].([]any)
	if len(items) < 1 {
		t.Fatalf("fold-dirty returned %d items, want >=1", len(items))
	}
	item := items[0].(map[string]any)
	fingerprint, _ := item["fold_fingerprint"].(string)
	headOrdinal := item["head_ordinal"]
	if fingerprint == "" {
		t.Fatalf("fold item has no fingerprint: %v", item)
	}

	// write the folded canonical (simulating the LLM worker)
	if code := doPOST("/internal/books/"+bookID+"/entities/"+entityID+"/fold-snapshot", map[string]any{
		"content": "李四，金丹期修士。", "as_of_ordinal": headOrdinal,
		"fold_algo_version": 1, "fold_fingerprint": fingerprint,
	}); code != http.StatusOK {
		t.Fatalf("fold-snapshot write: %d", code)
	}

	// dirty cleared (compare-and-clear, no new fact since)
	if n := srv.foldDirtyCount(ctx, bid); n != 0 {
		t.Fatalf("dirty should be cleared after fold, got %d", n)
	}

	// GET canonical returns the fresh snapshot
	canon := doGET("/internal/books/" + bookID + "/entities/" + entityID + "/canonical-snapshot")
	if canon["content"] != "李四，金丹期修士。" || canon["source"] != "snapshot" || canon["canonical_status"] != "current" {
		t.Fatalf("canonical = %v, want the folded snapshot (source=snapshot, current)", canon)
	}

	// a NEW fact makes the snapshot STALE → GET canonical degrades + re-flags dirty
	if code := doPOST("/internal/books/"+bookID+"/facts/append", map[string]any{
		"entity_id": entityID, "fact_kind": "attribute", "attr_or_predicate": "境界",
		"value": "元婴", "valid_from_ordinal": 900,
	}); code != http.StatusOK {
		t.Fatalf("append new fact: %d", code)
	}
	canon2 := doGET("/internal/books/" + bookID + "/entities/" + entityID + "/canonical-snapshot")
	if canon2["source"] != "canon-content" || canon2["canonical_status"] != "stale" {
		t.Fatalf("after a newer fact, canonical = %v, want degrade (source=canon-content, stale)", canon2)
	}
	if n := srv.foldDirtyCount(ctx, bid); n < 1 {
		t.Fatalf("stale read should re-flag dirty, got %d", n)
	}
}
