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

	"github.com/loreweave/glossary-service/internal/migrate"
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

// TestEvidenceProvenanceFields is the pure-unit defensive gate (INV-7 / T1): glossary
// trusts no raw model number. Only the closed enum is honored, offsets persist solely
// for exact/resolved AND only when sane, and a status claiming exact/resolved without
// valid offsets degrades to 'unverified' rather than landing half-trusted.
func TestEvidenceProvenanceFields(t *testing.T) {
	ip := func(v int) *int { return &v }
	cases := []struct {
		name      string
		ent       extractedEntity
		wantStat  string
		wantCS    *int
		wantCE    *int
		wantBlock string
	}{
		{"resolved with offsets",
			extractedEntity{EvidenceProvenanceStatus: "resolved", EvidenceCharStart: ip(5), EvidenceCharEnd: ip(12), EvidenceBlockOrLine: ip(1)},
			"resolved", ip(5), ip(12), "1"},
		{"exact with offsets",
			extractedEntity{EvidenceProvenanceStatus: "exact", EvidenceCharStart: ip(0), EvidenceCharEnd: ip(3), EvidenceBlockOrLine: ip(0)},
			"exact", ip(0), ip(3), "0"},
		{"ambiguous keeps status NULL offsets",
			extractedEntity{EvidenceProvenanceStatus: "ambiguous", EvidenceCharStart: ip(5), EvidenceCharEnd: ip(12)},
			"ambiguous", nil, nil, ""},
		{"unmatched keeps status NULL offsets",
			extractedEntity{EvidenceProvenanceStatus: "unmatched"},
			"unmatched", nil, nil, ""},
		{"resolved but missing offsets degrades",
			extractedEntity{EvidenceProvenanceStatus: "resolved"},
			"unverified", nil, nil, ""},
		{"resolved but inverted offsets degrades",
			extractedEntity{EvidenceProvenanceStatus: "resolved", EvidenceCharStart: ip(12), EvidenceCharEnd: ip(5)},
			"unverified", nil, nil, ""},
		{"resolved but negative offset degrades",
			extractedEntity{EvidenceProvenanceStatus: "resolved", EvidenceCharStart: ip(-1), EvidenceCharEnd: ip(5)},
			"unverified", nil, nil, ""},
		{"unknown status degrades to unverified",
			extractedEntity{EvidenceProvenanceStatus: "totally-made-up", EvidenceCharStart: ip(5), EvidenceCharEnd: ip(12)},
			"unverified", nil, nil, ""},
		{"omitted status (legacy caller) is unverified",
			extractedEntity{},
			"unverified", nil, nil, ""},
		{"resolved with valid offsets but negative block drops the block only",
			extractedEntity{EvidenceProvenanceStatus: "resolved", EvidenceCharStart: ip(5), EvidenceCharEnd: ip(12), EvidenceBlockOrLine: ip(-3)},
			"resolved", ip(5), ip(12), ""},
	}
	eqp := func(a, b *int) bool {
		if a == nil || b == nil {
			return a == b
		}
		return *a == *b
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			gotStat, gotCS, gotCE, gotBlock := evidenceProvenanceFields(c.ent)
			if gotStat != c.wantStat {
				t.Errorf("status: want %q got %q", c.wantStat, gotStat)
			}
			if !eqp(gotCS, c.wantCS) || !eqp(gotCE, c.wantCE) {
				t.Errorf("offsets: want (%v,%v) got (%v,%v)", c.wantCS, c.wantCE, gotCS, gotCE)
			}
			if gotBlock != c.wantBlock {
				t.Errorf("block_or_line: want %q got %q", c.wantBlock, gotBlock)
			}
		})
	}
}

// TestBulkExtract_EvidencePersistsValidatedOffsets proves the persist side of PROV/M3:
// a writeback carrying WORKER-VALIDATED offsets + a 'resolved' status lands them on the
// evidences row (replacing the chapter-only 'unverified' default), so a grounding
// consumer can trace the quote to exact source coordinates.
func TestBulkExtract_EvidencePersistsValidatedOffsets(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1019"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "证据者", "evidence": "他在第七章登场。",
				"evidence_provenance_status": "resolved",
				"evidence_char_start":        10,
				"evidence_char_end":          18,
				"evidence_block_or_line":     2,
				"chapter_links": []map[string]any{
					{"chapter_id": chap, "chapter_title": "第七章", "chapter_index": 7}}},
		},
	})

	var cs, ce int
	var block, status string
	if err := pool.QueryRow(ctx, `
		SELECT ev.char_start, ev.char_end, ev.block_or_line, ev.provenance_status
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		WHERE ge.book_id=$1 AND ev.evidence_type='extraction_quote'`, bookID).Scan(&cs, &ce, &block, &status); err != nil {
		t.Fatalf("query evidence offsets: %v", err)
	}
	if status != "resolved" {
		t.Errorf("want provenance_status=resolved, got %q", status)
	}
	if cs != 10 || ce != 18 {
		t.Errorf("want char_start=10 char_end=18, got %d,%d", cs, ce)
	}
	if block != "2" {
		t.Errorf("want block_or_line=\"2\", got %q", block)
	}
}

// TestBulkExtract_EvidenceOffsetRefreshesOnReExtract proves the latest-validated-wins
// refresh: a second writeback (DISTINCT writeback_key, same quote, NEW validated offsets
// — the chapter-edited-but-quote-byte-identical case) updates the stored offset/status in
// place rather than leaving the first writer's now-stale coordinates. Still ONE row.
func TestBulkExtract_EvidenceOffsetRefreshesOnReExtract(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1020"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	mk := func(key string, cs, ce, blk int) map[string]any {
		return map[string]any{
			"source_language": "zh", "chapter_id": chap, "writeback_key": key,
			"entities": []map[string]any{
				{"kind_code": "character", "name": "漂移者", "evidence": "他在此登场。",
					"evidence_provenance_status": "resolved",
					"evidence_char_start":        cs,
					"evidence_char_end":          ce,
					"evidence_block_or_line":     blk,
					"chapter_links": []map[string]any{
						{"chapter_id": chap, "chapter_title": "章", "chapter_index": 1}}},
			},
		}
	}
	postExtract(t, srv, token, bookID, mk("drift-key-1", 5, 11, 0))   // first: offset 5..11
	postExtract(t, srv, token, bookID, mk("drift-key-2", 40, 46, 3)) // re-extract: quote moved to 40..46

	var cs, ce int
	var block string
	var n int
	if err := pool.QueryRow(ctx, `
		SELECT count(*), max(ev.char_start), max(ev.char_end), max(ev.block_or_line)
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		WHERE ge.book_id=$1 AND ev.evidence_type='extraction_quote'`, bookID).Scan(&n, &cs, &ce, &block); err != nil {
		t.Fatalf("query refreshed evidence: %v", err)
	}
	if n != 1 {
		t.Fatalf("re-extract duplicated evidence: want 1 row, got %d", n)
	}
	if cs != 40 || ce != 46 || block != "3" {
		t.Errorf("offset not refreshed to latest: got start=%d end=%d block=%q (want 40,46,\"3\")", cs, ce, block)
	}
}

// skipReasonFor digs an entity's per-attribute skip reason out of the bulk response.
func skipReasonFor(resp map[string]any, name, code string) string {
	ents, _ := resp["entities"].([]any)
	for _, e := range ents {
		em, _ := e.(map[string]any)
		if em == nil || em["name"] != name {
			continue
		}
		reasons, _ := em["attributes_skipped_reasons"].([]any)
		for _, r := range reasons {
			rm, _ := r.(map[string]any)
			if rm != nil && rm["code"] == code {
				s, _ := rm["reason"].(string)
				return s
			}
		}
	}
	return ""
}

// TestBulkExtract_VerifiedClobberGuard proves INV-8 (T2): a human-'verified' SOURCE value
// is NEVER overwritten by a machine re-extraction, even with action=overwrite — it is
// skipped with reason 'verified', and the stored value is unchanged.
func TestBulkExtract_VerifiedClobberGuard(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1021"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	chap := uuid.NewString()

	mk := func(appearance, action string) map[string]any {
		return map[string]any{
			"source_language":   "zh",
			"attribute_actions": map[string]any{"character": map[string]any{"appearance": action}},
			"entities": []map[string]any{
				{"kind_code": "character", "name": "守护者",
					"attributes":    map[string]any{"appearance": appearance},
					"chapter_links": []map[string]any{{"chapter_id": chap, "chapter_index": 1}}},
			},
		}
	}

	// 1. First extraction creates the entity + writes appearance='tall' (DEFAULT machine).
	postExtract(t, srv, token, bookID, mk("tall", "overwrite"))

	var avid uuid.UUID
	var val, conf string
	if err := pool.QueryRow(ctx, `
		SELECT eav.attr_value_id, eav.original_value, eav.confidence
		FROM entity_attribute_values eav
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='appearance'`, bookID).Scan(&avid, &val, &conf); err != nil {
		t.Fatalf("query appearance: %v", err)
	}
	if val != "tall" || conf != "machine" {
		t.Fatalf("setup: want tall/machine, got %q/%q", val, conf)
	}

	// 2. A human verifies the value (the editor / apply-edit producer marks it 'verified').
	if _, err := pool.Exec(ctx,
		`UPDATE entity_attribute_values SET confidence='verified' WHERE attr_value_id=$1`, avid); err != nil {
		t.Fatalf("mark verified: %v", err)
	}

	// 3. Re-extract a DIFFERENT value with overwrite → the guard must refuse.
	resp := postExtract(t, srv, token, bookID, mk("short", "overwrite"))

	var val2 string
	if err := pool.QueryRow(ctx,
		`SELECT original_value FROM entity_attribute_values WHERE attr_value_id=$1`, avid).Scan(&val2); err != nil {
		t.Fatalf("re-query appearance: %v", err)
	}
	if val2 != "tall" {
		t.Errorf("verified-clobber guard FAILED: value overwritten to %q (want unchanged 'tall')", val2)
	}
	if r := skipReasonFor(resp, "守护者", "appearance"); r != "verified" {
		t.Errorf("want skip reason 'verified', got %q", r)
	}
}

// TestBulkExtract_SkipReasonTaxonomy proves the skip-reason taxonomy ends the silent-skip
// gap: fill on an occupied (machine) value → 'fill_occupied'; an attribute with no action
// → 'no_action'. (Verified is covered above.)
func TestBulkExtract_SkipReasonTaxonomy(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-0000000a1022"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	chap := uuid.NewString()
	links := []map[string]any{{"chapter_id": chap, "chapter_index": 1}}

	// Create the entity with a machine appearance value.
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "记录者",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})

	// Re-extract: fill on the occupied appearance (→ fill_occupied) + personality with an
	// EXPLICIT 'skip' action (→ no_action). (An ABSENT action now falls to the authored
	// merge_strategy default — covered by TestMergeStrategy_FromOntology — so 'no_action'
	// is reserved for an explicit profile skip.)
	resp := postExtract(t, srv, token, bookID, map[string]any{
		"source_language":   "zh",
		"attribute_actions": map[string]any{"character": map[string]any{"appearance": "fill", "personality": "skip"}},
		"entities": []map[string]any{
			{"kind_code": "character", "name": "记录者",
				"attributes":    map[string]any{"appearance": "new", "personality": "brave"},
				"chapter_links": links},
		},
	})

	if r := skipReasonFor(resp, "记录者", "appearance"); r != "fill_occupied" {
		t.Errorf("want appearance skip reason 'fill_occupied', got %q", r)
	}
	if r := skipReasonFor(resp, "记录者", "personality"); r != "no_action" {
		t.Errorf("want personality skip reason 'no_action', got %q", r)
	}

	// The occupied value was NOT overwritten by fill.
	var val string
	if err := pool.QueryRow(ctx, `
		SELECT eav.original_value FROM entity_attribute_values eav
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='appearance'`, bookID).Scan(&val); err != nil {
		t.Fatalf("query appearance: %v", err)
	}
	if val != "tall" {
		t.Errorf("fill clobbered an occupied value: got %q (want 'tall')", val)
	}
}

// TestDedupNormalized is the pure-unit proof of the per-item append dedup
// (D-GLOSSARY-MULTIROW-ATTR-VALUES slice 1): drop empties, dedup by normalized
// value (NFC + case/space-insensitive), preserve first-seen order. This is the
// up-front "anything to add?" gate; UNIQUE(attr_value_id, item_norm) is the
// DB-level backstop.
func TestDedupNormalized(t *testing.T) {
	cases := []struct {
		name string
		in   []string
		want []string
	}{
		{"plain", []string{"tall", "short"}, []string{"tall", "short"}},
		{"dups dropped", []string{"a", "b", "a"}, []string{"a", "b"}},
		{"case/space-insensitive", []string{"Yan Mo", "yan  mo", "New"}, []string{"Yan Mo", "New"}},
		{"empties dropped", []string{"", "  ", "x"}, []string{"x"}},
		{"all dup → empty", []string{"a", "A", " a "}, []string{"a"}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := dedupNormalized(c.in)
			if len(got) != len(c.want) {
				t.Fatalf("len: want %v got %v", c.want, got)
			}
			for i := range got {
				if got[i] != c.want[i] {
					t.Errorf("idx %d: want %q got %q", i, c.want[i], got[i])
				}
			}
		})
	}
}

// setMergeStrategy sets the authored merge_strategy for (character, code) on a book.
func setMergeStrategy(t *testing.T, pool *pgxpool.Pool, bookID, code, strategy string) {
	t.Helper()
	if _, err := pool.Exec(context.Background(), `
		UPDATE book_attributes SET merge_strategy=$1
		WHERE attr_id IN (
			SELECT ba.attr_id FROM book_attributes ba
			JOIN book_kinds bk ON bk.book_kind_id = ba.kind_id
			WHERE bk.book_id=$2 AND bk.code='character' AND ba.code=$3)`,
		strategy, bookID, code); err != nil {
		t.Fatalf("setMergeStrategy: %v", err)
	}
}

func appearanceValue(t *testing.T, pool *pgxpool.Pool, bookID string) string {
	t.Helper()
	var v string
	if err := pool.QueryRow(context.Background(), `
		SELECT eav.original_value FROM entity_attribute_values eav
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='appearance'`, bookID).Scan(&v); err != nil {
		t.Fatalf("query appearance: %v", err)
	}
	return v
}

// TestBulkExtract_AppendAction proves the append action dedup-merges a list value and is
// idempotent (a re-append of the same item is skipped 'unchanged').
func TestBulkExtract_AppendAction(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a1023"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	links := []map[string]any{{"chapter_id": uuid.NewString(), "chapter_index": 1}}

	mk := func(val string) map[string]any {
		return map[string]any{
			"source_language":   "zh",
			"attribute_actions": map[string]any{"character": map[string]any{"appearance": "append"}},
			"entities": []map[string]any{
				{"kind_code": "character", "name": "拼接者",
					"attributes": map[string]any{"appearance": val}, "chapter_links": links},
			},
		}
	}
	// Create the entity (createExtractedEntity writes appearance='tall').
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "拼接者",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})
	// Append 'short' → ["tall","short"].
	postExtract(t, srv, token, bookID, mk("short"))
	if v := appearanceValue(t, pool, bookID); v != `["tall","short"]` {
		t.Errorf("append: want [\"tall\",\"short\"], got %q", v)
	}
	// Re-append 'short' → unchanged (idempotent).
	resp := postExtract(t, srv, token, bookID, mk("short"))
	if v := appearanceValue(t, pool, bookID); v != `["tall","short"]` {
		t.Errorf("idempotent append changed the value: got %q", v)
	}
	if r := skipReasonFor(resp, "拼接者", "appearance"); r != "unchanged" {
		t.Errorf("want re-append skip reason 'unchanged', got %q", r)
	}
}

// TestBulkExtract_AppendCreatesItems proves the slice-1 per-item model
// (D-GLOSSARY-MULTIROW-ATTR-VALUES): an append materializes the prior scalar + the new
// element as ACTIVE child rows (the appended one carrying source-chapter provenance),
// keeps original_value as the write-synced cache, and is idempotent (UNIQUE item_norm).
func TestBulkExtract_AppendCreatesItems(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a1099"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	chapterID := uuid.NewString()
	links := []map[string]any{{"chapter_id": chapterID, "chapter_index": 1}}

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "缝合怪",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language":   "zh",
		"attribute_actions": map[string]any{"character": map[string]any{"appearance": "append"}},
		"entities": []map[string]any{
			{"kind_code": "character", "name": "缝合怪",
				"attributes": map[string]any{"appearance": "short"}, "chapter_links": links},
		},
	})

	// Child items: 2 active rows, ordered; the seeded 'tall' has NULL provenance, the
	// appended 'short' carries the chapter id; both default confidence 'machine'.
	type item struct {
		val, norm, conf, status string
		src                     *string
	}
	rows, err := pool.Query(context.Background(), `
		SELECT i.item_value, i.item_norm, i.confidence, i.status, i.source_chapter_id::text
		FROM entity_attribute_value_items i
		JOIN entity_attribute_values eav ON eav.attr_value_id = i.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='appearance'
		ORDER BY i.sort_order, i.item_norm`, bookID)
	if err != nil {
		t.Fatalf("query items: %v", err)
	}
	var items []item
	for rows.Next() {
		var it item
		if err := rows.Scan(&it.val, &it.norm, &it.conf, &it.status, &it.src); err != nil {
			rows.Close()
			t.Fatalf("scan item: %v", err)
		}
		items = append(items, it)
	}
	rows.Close()
	if len(items) != 2 {
		t.Fatalf("want 2 child items, got %d (%+v)", len(items), items)
	}
	if items[0].val != "tall" || items[0].src != nil {
		t.Errorf("seeded item: want tall/NULL-src, got %q/%v", items[0].val, items[0].src)
	}
	if items[1].val != "short" || items[1].src == nil || *items[1].src != chapterID {
		t.Errorf("appended item: want short/src=%s, got %q/%v", chapterID, items[1].val, items[1].src)
	}
	for _, it := range items {
		if it.conf != "machine" || it.status != "active" {
			t.Errorf("item %q: want machine/active, got %s/%s", it.val, it.conf, it.status)
		}
		if it.norm == "" {
			t.Errorf("item %q: empty item_norm", it.val)
		}
	}
	// Cache parity (INV-MR1) + idempotency: re-append 'short' adds no new row.
	if v := appearanceValue(t, pool, bookID); v != `["tall","short"]` {
		t.Errorf("cache parity: want [\"tall\",\"short\"], got %q", v)
	}
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language":   "zh",
		"attribute_actions": map[string]any{"character": map[string]any{"appearance": "append"}},
		"entities": []map[string]any{
			{"kind_code": "character", "name": "缝合怪",
				"attributes": map[string]any{"appearance": "short"}, "chapter_links": links},
		},
	})
	var n int
	if err := pool.QueryRow(context.Background(), `
		SELECT count(*) FROM entity_attribute_value_items i
		JOIN entity_attribute_values eav ON eav.attr_value_id = i.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='appearance'`, bookID).Scan(&n); err != nil {
		t.Fatalf("recount: %v", err)
	}
	if n != 2 {
		t.Errorf("idempotent re-append created a row: want 2 items, got %d", n)
	}
}

// TestBulkExtract_AppendScalarReappendCanonicalizes locks the INV-MR1 fix: appending a
// scalar list value with its OWN value adds no new element (skip 'unchanged') but still
// materializes the legacy scalar into a child item and canonicalizes original_value to the
// active-item JSON array — the cache never diverges from the items.
func TestBulkExtract_AppendScalarReappendCanonicalizes(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a1101"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	links := []map[string]any{{"chapter_id": uuid.NewString(), "chapter_index": 1}}

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "钟表匠",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})
	// Pre-state: scalar cache, zero items.
	if v := appearanceValue(t, pool, bookID); v != "tall" {
		t.Fatalf("precondition: want scalar 'tall', got %q", v)
	}
	resp := postExtract(t, srv, token, bookID, map[string]any{
		"source_language":   "zh",
		"attribute_actions": map[string]any{"character": map[string]any{"appearance": "append"}},
		"entities": []map[string]any{
			{"kind_code": "character", "name": "钟表匠",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})
	if r := skipReasonFor(resp, "钟表匠", "appearance"); r != "unchanged" {
		t.Errorf("want skip 'unchanged' (no new element), got %q", r)
	}
	// INV-MR1: cache canonicalized to the active-item array, parity with the one item.
	if v := appearanceValue(t, pool, bookID); v != `["tall"]` {
		t.Errorf("cache not canonicalized: want [\"tall\"], got %q", v)
	}
}

// TestBulkExtract_OverwriteThenAppendNoResurrection locks the slice-2 divergence closure:
// an extraction overwrite of a list attr replaces the item set, so a SUBSEQUENT append builds
// on the overwritten list — the pre-overwrite items are NOT resurrected by the cache rebuild
// (the slice-1 boundary, now closed).
func TestBulkExtract_OverwriteThenAppendNoResurrection(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a1102"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	links := []map[string]any{{"chapter_id": uuid.NewString(), "chapter_index": 1}}
	mk := func(action string, val any) map[string]any {
		return map[string]any{
			"source_language":   "zh",
			"attribute_actions": map[string]any{"character": map[string]any{"appearance": action}},
			"entities": []map[string]any{
				{"kind_code": "character", "name": "镜匠",
					"attributes": map[string]any{"appearance": val}, "chapter_links": links},
			},
		}
	}
	// create → append two → items [tall, short]
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "镜匠",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})
	postExtract(t, srv, token, bookID, mk("append", "short"))
	if v := appearanceValue(t, pool, bookID); v != `["tall","short"]` {
		t.Fatalf("setup append: want [\"tall\",\"short\"], got %q", v)
	}
	// overwrite with a fresh LIST → item set replaced (tall/short gone)
	postExtract(t, srv, token, bookID, mk("overwrite", []any{"fresh"}))
	if v := appearanceValue(t, pool, bookID); v != `["fresh"]` {
		t.Fatalf("overwrite: want [\"fresh\"], got %q", v)
	}
	// append builds on the overwritten list — NO resurrection of tall/short
	postExtract(t, srv, token, bookID, mk("append", "more"))
	if v := appearanceValue(t, pool, bookID); v != `["fresh","more"]` {
		t.Errorf("post-overwrite append resurrected stale items: want [\"fresh\",\"more\"], got %q", v)
	}
	var n int
	if err := pool.QueryRow(context.Background(), `
		SELECT count(*) FROM entity_attribute_value_items i
		JOIN entity_attribute_values eav ON eav.attr_value_id = i.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='appearance' AND i.status='active'`, bookID).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 2 {
		t.Errorf("want 2 active items after overwrite+append, got %d", n)
	}
}

// TestMultirowBackfill proves migration 0035's Go backfill re-materializes per-item child
// rows from a list-valued original_value that has none (the pre-0035 state). Simulated by
// appending (which creates items) then deleting the items while keeping the list cache, then
// re-running UpMultirowAttrValues (idempotent): the backfill scans LIKE '[%' rows and rebuilds
// the items via the SHARED textnorm normalize (parity with the runtime append path).
func TestMultirowBackfill(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a1100"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	links := []map[string]any{{"chapter_id": uuid.NewString(), "chapter_index": 1}}

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "古董商",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language":   "zh",
		"attribute_actions": map[string]any{"character": map[string]any{"appearance": "append"}},
		"entities": []map[string]any{
			{"kind_code": "character", "name": "古董商",
				"attributes": map[string]any{"appearance": "Yan  Mo"}, "chapter_links": links},
		},
	})
	// Simulate a pre-0035 row: the list cache exists, but the child items don't.
	if _, err := pool.Exec(context.Background(), `
		DELETE FROM entity_attribute_value_items i
		USING entity_attribute_values eav, glossary_entities ge, book_attributes ba
		WHERE i.attr_value_id = eav.attr_value_id AND eav.entity_id = ge.entity_id
		  AND ba.attr_id = eav.attr_def_id AND ge.book_id=$1 AND ba.code='appearance'`, bookID); err != nil {
		t.Fatalf("delete items: %v", err)
	}
	// Backfill re-runs (idempotent) and rebuilds the items from the cache.
	if err := migrate.UpMultirowAttrValues(context.Background(), pool); err != nil {
		t.Fatalf("UpMultirowAttrValues: %v", err)
	}
	rows, err := pool.Query(context.Background(), `
		SELECT i.item_value, i.item_norm FROM entity_attribute_value_items i
		JOIN entity_attribute_values eav ON eav.attr_value_id = i.attr_value_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ba.code='appearance' AND i.status='active'
		ORDER BY i.sort_order`, bookID)
	if err != nil {
		t.Fatalf("query items: %v", err)
	}
	var vals, norms []string
	for rows.Next() {
		var v, n string
		if err := rows.Scan(&v, &n); err != nil {
			rows.Close()
			t.Fatalf("scan: %v", err)
		}
		vals = append(vals, v)
		norms = append(norms, n)
	}
	rows.Close()
	if len(vals) != 2 || vals[0] != "tall" || vals[1] != "Yan  Mo" {
		t.Fatalf("backfill items: want [tall, Yan  Mo], got %v", vals)
	}
	// Normalize parity: item_norm uses the SHARED textnorm (NFC+collapse+lower).
	if norms[1] != "yan mo" {
		t.Errorf("backfill normalize: want 'yan mo', got %q", norms[1])
	}
}

// TestMergeStrategy_FromOntology proves the authored merge_strategy is the DEFAULT when the
// profile gives no action: 'manual' → skipped 'manual' (queue for review, no write);
// 'append' → appends. (The profile, when present, still overrides — covered elsewhere.)
func TestMergeStrategy_FromOntology(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a1024"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	links := []map[string]any{{"chapter_id": uuid.NewString(), "chapter_index": 1}}

	// Create with appearance='tall'.
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "策略者",
				"attributes": map[string]any{"appearance": "tall"}, "chapter_links": links},
		},
	})

	// merge_strategy='manual' + NO profile action → skip 'manual', value unchanged.
	setMergeStrategy(t, pool, bookID, "appearance", "manual")
	resp := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh", // no attribute_actions → authored strategy governs
		"entities": []map[string]any{
			{"kind_code": "character", "name": "策略者",
				"attributes": map[string]any{"appearance": "short"}, "chapter_links": links},
		},
	})
	if r := skipReasonFor(resp, "策略者", "appearance"); r != "manual" {
		t.Errorf("want manual-strategy skip reason 'manual', got %q", r)
	}
	if v := appearanceValue(t, pool, bookID); v != "tall" {
		t.Errorf("manual strategy must not write: got %q", v)
	}

	// merge_strategy='append' + NO profile action → appends.
	setMergeStrategy(t, pool, bookID, "appearance", "append")
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "策略者",
				"attributes": map[string]any{"appearance": "short"}, "chapter_links": links},
		},
	})
	if v := appearanceValue(t, pool, bookID); v != `["tall","short"]` {
		t.Errorf("append strategy: want [\"tall\",\"short\"], got %q", v)
	}
}

// TestAdoptClone_PropagatesMergeStrategy — D-EXTRACT-ATTR-MERGE-DEFAULTS review-impl HIGH fix.
// The migration (0039) is a ONE-TIME re-seed; the book_attributes column DEFAULT is still
// fill_if_empty, so a book adopted/cloned LATER must inherit the (healed) source's merge_strategy
// or it re-freezes. This proves the adoption clone COPIES merge_strategy from the System source.
func TestAdoptClone_PropagatesMergeStrategy(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()
	// Heal a System attribute to a non-default strategy (what 0039 does in prod). system_attributes
	// is SHARED across tests on this DB, so capture the original + RESTORE in cleanup — otherwise the
	// (now strategy-copying) adopt helper would leak this value into other tests' cloned books.
	const where = `code='appearance' AND kind_id IN (SELECT kind_id FROM system_kinds WHERE code='character')`
	var orig string
	if err := pool.QueryRow(ctx, `SELECT merge_strategy FROM system_attributes WHERE `+where).Scan(&orig); err != nil {
		t.Fatalf("read original system strategy: %v", err)
	}
	if _, err := pool.Exec(ctx, `UPDATE system_attributes SET merge_strategy='append' WHERE `+where); err != nil {
		t.Fatalf("seed system strategy: %v", err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `UPDATE system_attributes SET merge_strategy=$1 WHERE `+where, orig)
	})
	bookID := uuid.MustParse("00000000-0000-0000-0001-0000000a1026")
	adoptTestBook(t, pool, bookID)
	t.Cleanup(func() { cleanupExtractBook(pool, bookID.String()) })

	kindID := bookKindID(t, pool, bookID, "character")
	attrID := bookAttrID(t, pool, bookID, kindID, "appearance")
	var strat string
	if err := pool.QueryRow(ctx,
		`SELECT merge_strategy FROM book_attributes WHERE attr_id=$1`, attrID).Scan(&strat); err != nil {
		t.Fatalf("read cloned strategy: %v", err)
	}
	if strat != "append" {
		t.Errorf("adoption clone must inherit the System source's merge_strategy; got %q want append "+
			"(a new book would re-freeze on fill_if_empty)", strat)
	}
}

// TestEvidenceChapterFor — D-EVIDENCE-PROVENANCE-OVERHAUL M2. The evidence's chapter must be the
// chapter the writeback PROCESSED (req.ChapterID, where the quote came from), not the entity's
// first appearance — the firstChapterID bug mislabeled a chapter-50 quote as chapter 1.
func TestEvidenceChapterFor(t *testing.T) {
	c1, c50 := uuid.NewString(), uuid.NewString()
	links := []chapterLinkIn{
		{ChapterID: c1, ChapterTitle: "Ch1", ChapterIndex: 1},
		{ChapterID: c50, ChapterTitle: "Ch50", ChapterIndex: 50},
	}
	// Writeback for chapter 50 → evidence stamped with c50 + its title/index (NOT c1).
	id, title, idx := evidenceChapterFor(c50, links)
	if id == nil || id.String() != c50 || title != "Ch50" || idx == nil || *idx != 50 {
		t.Fatalf("scope=c50 → got id=%v title=%q idx=%v want c50/Ch50/50", id, title, idx)
	}
	// Scope chapter present but no matching link → correct id, empty title (backfilled later).
	other := uuid.NewString()
	id2, title2, idx2 := evidenceChapterFor(other, links)
	if id2 == nil || id2.String() != other || title2 != "" || idx2 != nil {
		t.Fatalf("scope=other → got id=%v title=%q idx=%v want other/empty/nil", id2, title2, idx2)
	}
	// Legacy (no scope) → first link, preserving old behavior.
	id3, title3, idx3 := evidenceChapterFor("", links)
	if id3 == nil || id3.String() != c1 || title3 != "Ch1" || idx3 == nil || *idx3 != 1 {
		t.Fatalf("legacy → got id=%v title=%q idx=%v want c1/Ch1/1", id3, title3, idx3)
	}
	// Nothing → nil.
	if id4, _, _ := evidenceChapterFor("", nil); id4 != nil {
		t.Fatalf("empty → want nil id, got %v", id4)
	}
}

// TestSeedMergeStrategy — D-EXTRACT-ATTR-MERGE-DEFAULTS review fix. The runtime heuristic for
// a NEWLY-created ontology attribute (book adoption clone of a fresh source, custom kind/attr,
// user-tier attr) MUST match migration 0039's CASE so new books/attrs don't re-freeze on the
// column's fill_if_empty default. This locks the mapping (the migration itself has no Go test).
func TestSeedMergeStrategy(t *testing.T) {
	cases := []struct {
		code, fieldType string
		required        bool
		want            string
	}{
		{"name", "text", true, "fill_if_empty"},   // identity key
		{"term", "text", false, "fill_if_empty"},  // identity key (glossary term)
		{"slug", "text", true, "fill_if_empty"},   // any required text key
		{"aliases", "tags", false, "append"},      // list → accumulate
		{"abilities", "tags", true, "append"},     // required tags still append
		{"location", "text", false, "overwrite"},  // non-required state text → advance
		{"biography", "textarea", false, "overwrite"},
		{"power_level", "number", false, "overwrite"},
		{"affiliation", "select", false, "overwrite"},
	}
	for _, c := range cases {
		if got := seedMergeStrategy(c.code, c.fieldType, c.required); got != c.want {
			t.Errorf("seedMergeStrategy(%q,%q,%v)=%q want %q", c.code, c.fieldType, c.required, got, c.want)
		}
	}
}

// TestMergeStrategy_DefaultSentinel — D-EXTRACT-ATTR-MERGE-DEFAULTS M2. The worker/FE now
// send an explicit "default" action (instead of forcing "fill", which froze every
// already-filled attribute on re-extraction) so the attribute's authored merge_strategy
// governs. This proves the "default" sentinel routes to the authored strategy identically to
// an omitted action — for BOTH append (accumulate) and overwrite (advance state).
func TestMergeStrategy_DefaultSentinel(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a1025"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	links := []map[string]any{{"chapter_id": uuid.NewString(), "chapter_index": 1}}
	// Every post sends the explicit "default" sentinel for appearance.
	defaultAction := map[string]any{"character": map[string]any{"appearance": "default"}}

	post := func(val string) {
		postExtract(t, srv, token, bookID, map[string]any{
			"source_language":   "zh",
			"attribute_actions": defaultAction,
			"entities": []map[string]any{
				{"kind_code": "character", "name": "默認者",
					"attributes": map[string]any{"appearance": val}, "chapter_links": links},
			},
		})
	}

	// Seed a clean scalar baseline under fill_if_empty.
	setMergeStrategy(t, pool, bookID, "appearance", "fill_if_empty")
	post("tall")
	if v := appearanceValue(t, pool, bookID); v != "tall" {
		t.Fatalf("baseline (default→fill on empty): want \"tall\", got %q", v)
	}

	// strategy=append + action="default" → ACCUMULATE (the core fix).
	setMergeStrategy(t, pool, bookID, "appearance", "append")
	post("short")
	if v := appearanceValue(t, pool, bookID); v != `["tall","short"]` {
		t.Errorf("default→append: want [\"tall\",\"short\"], got %q", v)
	}

	// strategy=overwrite + action="default" → ADVANCE to the latest value, REPLACING the
	// accumulated list (not appending). The attr is in multi-row mode after the append step,
	// so the replaced single value serializes as a one-element list — the point is that
	// "tall"/"short" are gone and only "medium" remains.
	setMergeStrategy(t, pool, bookID, "appearance", "overwrite")
	post("medium")
	if v := appearanceValue(t, pool, bookID); v != `["medium"]` {
		t.Errorf("default→overwrite: want [\"medium\"] (replaced, not appended), got %q", v)
	}
}

// TestEntityDedup_UniqueIndexBackstop proves the constraint backstop (INV-C2): two
// LIVE entities of the same book+kind cannot share a normalized name. Post
// D-GLOSSARY-ST-DEDUP M3a, normalized_name is APP-MAINTAINED (no longer a GENERATED
// expression), so the backstop is keyed when the app stamps the dedup key via
// refreshEntityDedupKey — NOT on a raw EAV insert that bypasses the app. This test
// drives that app path: the second entity's key stamp must violate uq_entity_dedup.
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

	// Entity 1 named 独一 — name lands, app stamps the dedup key: fine.
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
	if err := refreshEntityDedupKey(ctx, pool, e1); err != nil {
		t.Fatalf("stamp dedup key e1: %v", err)
	}

	// Entity 2 with the SAME normalized name — the raw name insert succeeds (plain
	// column), but the app's key stamp must violate uq_entity_dedup.
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status) VALUES($1,$2,'draft') RETURNING entity_id`,
		bid, kindID).Scan(&e2); err != nil {
		t.Fatalf("insert e2: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','独一')`, e2, nameAttr); err != nil {
		t.Fatalf("name e2: %v", err)
	}
	if err := refreshEntityDedupKey(ctx, pool, e2); err == nil {
		t.Errorf("uq_entity_dedup did not reject a second live entity with the same normalized name")
	}
}
