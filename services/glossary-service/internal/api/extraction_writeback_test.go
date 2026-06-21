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
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// postExtractRaw drives POST /extract-entities and returns (status, decodedBody)
// WITHOUT failing the test — for concurrent callers where t.Fatalf (not goroutine
// safe) can't be used. Mirrors postExtract otherwise.
func postExtractRaw(srv *Server, token, bookID string, body map[string]any) (int, map[string]any) {
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/extract-entities", bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	var r map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &r)
	return w.Code, r
}

// liveEntityCount counts non-deleted entities for a book.
func liveEntityCount(t *testing.T, pool *pgxpool.Pool, ctx context.Context, bookID string) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM glossary_entities WHERE book_id=$1 AND deleted_at IS NULL`,
		bookID).Scan(&n); err != nil {
		t.Fatalf("count entities: %v", err)
	}
	return n
}

// cleanupExtractBook drops a test book's entities (EAV/evidence/links cascade) and
// its writeback-log rows.
func cleanupExtractBook(pool *pgxpool.Pool, bookID string) {
	ctx := context.Background()
	pool.Exec(ctx, `DELETE FROM extraction_writeback_log WHERE book_id=$1`, bookID)           //nolint:errcheck
	pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN
		(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bookID)                  //nolint:errcheck
	pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)                  //nolint:errcheck
}

// TestBulkExtract_UnadoptedBookReturns422 proves a book with no adopted ontology fails
// fast with a clear error instead of silently skipping every entity
// (D-GKA-EXTRACT-UNADOPTED-GUARD). An adopted book always has the 'unknown' kind, so an
// empty kind map ⇒ not scaffolded.
func TestBulkExtract_UnadoptedBookReturns422(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	bookID := uuid.NewString() // never adopted → no book_kinds rows
	raw, _ := json.Marshal(map[string]any{
		"source_language": "zh",
		"entities":        []map[string]any{{"kind_code": "character", "name": "哪吒"}},
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/books/"+bookID+"/extract-entities", bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("unadopted book extract: want 422, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "GLOSS_BOOK_NOT_SCAFFOLDED") {
		t.Fatalf("want GLOSS_BOOK_NOT_SCAFFOLDED, got %s", w.Body.String())
	}
}

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
	adoptTestBook(t, pool, uuid.MustParse(bookID))
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
		   JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
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
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")

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
	adoptTestBook(t, pool, uuid.MustParse(bookID))
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
		   JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		  WHERE ge.book_id=$1 AND ad.code='name' AND eav.original_value='杨戬'`,
		bookID).Scan(&tags)
	if len(tags) != 0 {
		t.Errorf("want empty tags for non-AI create, got %v", tags)
	}
}

// ── Extraction pipeline FND/M1 — two-ledger + concurrency ────────────────────

// TestBulkExtract_IdempotentReplay proves INV-C3: re-posting the SAME writeback_key
// is a no-op that echoes the original counts (idempotent_replay) and leaks no row.
func TestBulkExtract_IdempotentReplay(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1010"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	body := map[string]any{
		"source_language": "zh",
		"chapter_id":      chap,
		"writeback_key":   "wbk-replay-1",
		"content_hash":    "hash-abc",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "林动",
				"chapter_links": []map[string]any{{"chapter_id": chap, "chapter_index": 1}}},
		},
	}

	r1 := postExtract(t, srv, token, bookID, body)
	if r1["created"] != float64(1) {
		t.Fatalf("first apply: want created=1, got %v", r1)
	}

	// Replay: same key → early no-op before the loop even runs.
	st, r2 := postExtractRaw(srv, token, bookID, body)
	if st != http.StatusOK {
		t.Fatalf("replay status: want 200, got %d", st)
	}
	if r2["idempotent_replay"] != true {
		t.Errorf("want idempotent_replay=true, got %v", r2)
	}
	if r2["created"] != float64(1) {
		t.Errorf("replay must echo created=1 from the log, got %v", r2["created"])
	}

	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Errorf("idempotent replay leaked rows: want 1 entity, got %d", n)
	}
	var status string
	if err := pool.QueryRow(ctx,
		`SELECT status FROM extraction_writeback_log WHERE writeback_key='wbk-replay-1'`,
	).Scan(&status); err != nil {
		t.Fatalf("writeback-log row missing: %v", err)
	}
	if status != "committed" {
		t.Errorf("want committed log row, got %q", status)
	}
}

// TestBulkExtract_ConcurrentNoDuplicate proves INV-C1/C2: two concurrent writebacks
// of the SAME entity on the same book land exactly ONE row. The per-book advisory
// lock serializes them so the second's resolver sees the first and merges — the
// TOCTOU duplicate the old lock-free path produced is gone.
func TestBulkExtract_ConcurrentNoDuplicate(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1011"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	// No writeback_key → BOTH run the full create/merge path (the idempotency
	// short-circuit is deliberately NOT exercised here; we want the lock+resolver
	// to be what prevents the duplicate).
	body := map[string]any{
		"source_language": "zh",
		"entities":        []map[string]any{{"kind_code": "character", "name": "重复者"}},
	}

	var wg sync.WaitGroup
	codes := make([]int, 4)
	for i := range codes {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			codes[i], _ = postExtractRaw(srv, token, bookID, body)
		}(i)
	}
	wg.Wait()
	for i, c := range codes {
		if c != http.StatusOK {
			t.Fatalf("goroutine %d: status %d", i, c)
		}
	}

	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Errorf("concurrent writeback duplicated the entity: want 1, got %d", n)
	}
}

// TestBulkExtract_EvidenceIdempotent proves INV-C5: the same quote written twice
// (two DIFFERENT writeback keys so both apply, bypassing the idempotency
// short-circuit) yields ONE evidence row, via uq_evidence_dedup + ON CONFLICT.
func TestBulkExtract_EvidenceIdempotent(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1012"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	mk := func(key string) map[string]any {
		return map[string]any{
			"source_language": "zh", "chapter_id": chap, "writeback_key": key,
			"entities": []map[string]any{
				{"kind_code": "character", "name": "引用者", "evidence": "他在第一章出现。",
					"chapter_links": []map[string]any{{"chapter_id": chap, "chapter_index": 1}}},
			},
		}
	}
	postExtract(t, srv, token, bookID, mk("ev-key-1"))
	postExtract(t, srv, token, bookID, mk("ev-key-2")) // different key → re-applies; same quote

	var n int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		WHERE ge.book_id=$1 AND ev.evidence_type='extraction_quote'`, bookID).Scan(&n); err != nil {
		t.Fatalf("count evidence: %v", err)
	}
	if n != 1 {
		t.Errorf("evidence not idempotent: want 1 row, got %d", n)
	}
}

// TestBulkExtract_EvidenceCarriesChapterProvenance proves PROV/M3: an extracted
// evidence quote now records its chapter (index + title) and a provenance_status
// (DEFAULT 'unverified' until offsets are validated), not just chapter_id + text.
func TestBulkExtract_EvidenceCarriesChapterProvenance(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1014"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "证据者", "evidence": "他在第七章登场。",
				"chapter_links": []map[string]any{
					{"chapter_id": chap, "chapter_title": "第七章", "chapter_index": 7}}},
		},
	})

	var idx int
	var title, status string
	if err := pool.QueryRow(ctx, `
		SELECT ev.chapter_index, ev.chapter_title, ev.provenance_status
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		WHERE ge.book_id=$1 AND ev.evidence_type='extraction_quote'`, bookID).Scan(&idx, &title, &status); err != nil {
		t.Fatalf("query evidence provenance: %v", err)
	}
	if idx != 7 || title != "第七章" {
		t.Errorf("chapter provenance not populated: idx=%d title=%q", idx, title)
	}
	if status != "unverified" {
		t.Errorf("want provenance_status=unverified (offsets not validated yet), got %q", status)
	}
}

// TestEntityDedup_UniqueIndexBackstop proves the constraint backstop (INV-C2): two
// LIVE entities of the same book+kind cannot share a normalized name. Driven through
// the real EAV name-write path (the trig_eav_snapshot trigger maintains cached_name,
// from which normalized_name is generated and the unique index is checked).
func TestEntityDedup_UniqueIndexBackstop(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1013"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	kindID := bookKindID(t, pool, bid, "character")
	nameAttr := bookAttrID(t, pool, bid, kindID, "name")

	// Entity 1 named 独一 — lands fine.
	var e1, e2 uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status) VALUES($1,$2,'draft') RETURNING entity_id`,
		bid, kindID).Scan(&e1); err != nil {
		t.Fatalf("insert e1: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','独一')`, e1, nameAttr); err != nil {
		t.Fatalf("name e1: %v", err)
	}

	// Entity 2 with the SAME normalized name — its name write must violate uq_entity_dedup.
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status) VALUES($1,$2,'draft') RETURNING entity_id`,
		bid, kindID).Scan(&e2); err != nil {
		t.Fatalf("insert e2: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','独一')`, e2, nameAttr); err == nil {
		t.Errorf("uq_entity_dedup did not reject a second live entity with the same normalized name")
	}
}
