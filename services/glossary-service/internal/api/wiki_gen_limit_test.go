package api

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/google/uuid"
)

// D-WIKI-M7B-GEN-LIMIT — the delegate's 202 body is augmented with selection
// counts so the FE can warn when the genLimit silently dropped candidates.
func TestInjectGenSelectionCounts(t *testing.T) {
	t.Run("adds counts to a JSON object body", func(t *testing.T) {
		in := []byte(`{"job_id":"j1","status":"pending"}`)
		out := injectGenSelectionCounts(in, 87, 50)
		var obj map[string]any
		if err := json.Unmarshal(out, &obj); err != nil {
			t.Fatalf("output not valid JSON: %v", err)
		}
		if obj["job_id"] != "j1" || obj["status"] != "pending" {
			t.Fatalf("original fields lost: %v", obj)
		}
		// JSON numbers decode as float64.
		if obj["total_matched"].(float64) != 87 || obj["selected"].(float64) != 50 {
			t.Fatalf("counts not injected: %v", obj)
		}
	})

	t.Run("no truncation: total_matched == selected", func(t *testing.T) {
		out := injectGenSelectionCounts([]byte(`{"job_id":"j2"}`), 12, 12)
		var obj map[string]any
		_ = json.Unmarshal(out, &obj)
		if obj["total_matched"].(float64) != 12 || obj["selected"].(float64) != 12 {
			t.Fatalf("counts wrong: %v", obj)
		}
	})

	t.Run("non-object body is returned unchanged", func(t *testing.T) {
		for _, raw := range []string{`[1,2,3]`, `"hello"`, `not json`, ``} {
			out := injectGenSelectionCounts([]byte(raw), 5, 1)
			if string(out) != raw {
				t.Fatalf("non-object body %q mutated to %q", raw, string(out))
			}
		}
	})
}

// D-WIKI-M7B-GEN-LIMIT (real-PG) — resolveWikiGenEntities must return the
// limited id slice AND the UNLIMITED total-matched count, so the handler can
// detect the silent-truncation case (the core of the honest-banner fix).
// Skips when GLOSSARY_TEST_DB_URL is unset.
func TestResolveWikiGenEntities_TotalMatchedVsLimit(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	srv, _ := newEntitiesListServer(t)
	srv.pool = pool

	bookID := uuid.MustParse("00000000-0000-0000-0002-0000000b7b01")
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)

	seed := func(status string, deleted bool) {
		pool.Exec(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags,deleted_at)
			 VALUES($1,$2,$3,'{}', CASE WHEN $4 THEN now() ELSE NULL END)`,
			bookID, kindID, status, deleted)
	}
	// 5 eligible (active, not deleted) + 2 ineligible (deleted / inactive).
	for i := 0; i < 5; i++ {
		seed("active", false)
	}
	seed("active", true)   // soft-deleted — must NOT count
	seed("inactive", false) // non-active — must NOT count

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	// Limit below the eligible count → truncation: 3 ids, total 5.
	ids, total, err := srv.resolveWikiGenEntities(ctx, bookID, []string{"character"}, 3)
	if err != nil {
		t.Fatalf("resolveWikiGenEntities: %v", err)
	}
	if len(ids) != 3 {
		t.Errorf("want 3 limited ids, got %d", len(ids))
	}
	if total != 5 {
		t.Errorf("want total_matched=5 (eligible only, deleted/inactive excluded), got %d", total)
	}

	// Limit at/above the eligible count → no truncation: 5 ids, total 5.
	ids2, total2, err := srv.resolveWikiGenEntities(ctx, bookID, []string{"character"}, 50)
	if err != nil {
		t.Fatalf("resolveWikiGenEntities (no-trunc): %v", err)
	}
	if len(ids2) != 5 || total2 != 5 {
		t.Errorf("no-truncation: want 5 ids + total 5, got %d ids / total %d", len(ids2), total2)
	}
}
