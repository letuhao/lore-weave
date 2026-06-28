package api

// Tests for the #26/#7 summarize CANONICAL-layer internal endpoints:
//   GET  /internal/books/{book_id}/canonical-dirty
//   POST /internal/books/{book_id}/entities/{entity_id}/canonical
//
// Unit tests (no DB) run always. DB integration tests require GLOSSARY_TEST_DB_URL
// and skip otherwise (openTestDB).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func newCanonicalServer(t *testing.T) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, nil)
	token := "canonical-test-token"
	srv.cfg.InternalServiceToken = token
	return srv, token
}

const canonicalDirtyURL = "/internal/books/00000000-0000-0000-0000-000000000001/canonical-dirty"
const canonicalWriteURL = "/internal/books/00000000-0000-0000-0000-000000000001/entities/00000000-0000-0000-0000-000000000002/canonical"

// ── unit tests (no DB) ──────────────────────────────────────────────

func TestCanonicalDirty_RequiresInternalToken(t *testing.T) {
	srv, _ := newCanonicalServer(t)
	req := httptest.NewRequest(http.MethodGet, canonicalDirtyURL, nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestWriteCanonical_RequiresInternalToken(t *testing.T) {
	srv, _ := newCanonicalServer(t)
	req := httptest.NewRequest(http.MethodPost, canonicalWriteURL,
		strings.NewReader(`{"attr_code":"appearance","canonical_value":"x"}`))
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestCanonicalDirty_BadBookUUIDReturns400(t *testing.T) {
	srv, token := newCanonicalServer(t)
	req := httptest.NewRequest(http.MethodGet, "/internal/books/not-a-uuid/canonical-dirty", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad book uuid: want 400, got %d", w.Code)
	}
}

func TestWriteCanonical_MissingAttrCodeReturns422(t *testing.T) {
	srv, token := newCanonicalServer(t)
	req := httptest.NewRequest(http.MethodPost, canonicalWriteURL,
		strings.NewReader(`{"canonical_value":"x"}`))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnprocessableEntity {
		t.Errorf("missing attr_code: want 422, got %d", w.Code)
	}
}

// The canonical rune-cap is enforced BEFORE the DB write — runs without a DB.
func TestWriteCanonical_TooLongReturns422(t *testing.T) {
	srv, token := newCanonicalServer(t)
	long := strings.Repeat("仙", canonicalMaxRunes+1)
	body, _ := json.Marshal(map[string]string{"attr_code": "appearance", "canonical_value": long})
	req := httptest.NewRequest(http.MethodPost, canonicalWriteURL, strings.NewReader(string(body)))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnprocessableEntity {
		t.Errorf("over-cap canonical: want 422, got %d body=%s", w.Code, w.Body.String())
	}
}

// ── integration (requires DB) ──────────────────────────────────────

// seedSummarizeDirtyEntity sets the character/appearance attr to summarize, inserts an entity
// with a dirty appearance EAV (raw original_value), and returns its entity_id. Cleanup registered.
func seedSummarizeDirtyEntity(t *testing.T, pool *pgxpool.Pool, bookID, name, rawJSON string) string {
	t.Helper()
	ctx := context.Background()
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	setMergeStrategy(t, pool, bookID, "appearance", "summarize")
	kindID := bookKindID(t, pool, bid, "character")
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
	appearanceAttrID := bookAttrID(t, pool, bid, kindID, "appearance")

	var eid string
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
		 VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bid, kindID,
	).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	// Name EAV — the snapshot trigger maintains cached_name (the response's entity_name)
	// from it; the appearance EAV insert below recalcs the snapshot, so the name must exist.
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3)`,
		eid, nameAttrID, name,
	); err != nil {
		t.Fatalf("seed name EAV: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value,canonical_dirty)
		 VALUES($1,$2,'zh',$3,true)`,
		eid, appearanceAttrID, rawJSON,
	); err != nil {
		t.Fatalf("seed appearance EAV: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id=$1`, eid)
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id=$1`, eid)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})
	return eid
}

// TestCanonical_DirtyFetchThenWriteRoundtrip is the M2 core proof: a dirty summarize attr is
// listed (with parsed raw_values + fingerprint), the synthesized canonical lands, dirty clears,
// synced_at stamps, and a glossary.entity_updated event is emitted.
func TestCanonical_DirtyFetchThenWriteRoundtrip(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runCanonContentMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a2043"
	eid := seedSummarizeDirtyEntity(t, pool, bookID, "归纳者", `["tall","short"]`)

	srv, token := newCanonicalServer(t)
	srv.pool = pool

	// GET dirty → exactly one item, raw parsed, source language carried, fingerprint set.
	greq := httptest.NewRequest(http.MethodGet, "/internal/books/"+bookID+"/canonical-dirty", nil)
	greq.Header.Set("X-Internal-Token", token)
	gw := httptest.NewRecorder()
	srv.Router().ServeHTTP(gw, greq)
	if gw.Code != http.StatusOK {
		t.Fatalf("GET dirty: want 200, got %d body=%s", gw.Code, gw.Body.String())
	}
	var dirty struct {
		Items []canonicalDirtyItem `json:"items"`
		Count int                  `json:"count"`
	}
	if err := json.Unmarshal(gw.Body.Bytes(), &dirty); err != nil {
		t.Fatalf("decode dirty: %v", err)
	}
	if dirty.Count != 1 || len(dirty.Items) != 1 {
		t.Fatalf("want 1 dirty item, got %d (%+v)", dirty.Count, dirty.Items)
	}
	it := dirty.Items[0]
	if it.EntityID != eid || it.AttrCode != "appearance" || it.SourceLanguage != "zh" {
		t.Errorf("dirty item fields: got %+v", it)
	}
	if len(it.RawValues) != 2 || it.RawValues[0] != "tall" || it.RawValues[1] != "short" {
		t.Errorf("raw_values: want [tall short], got %v", it.RawValues)
	}
	if it.EntityName != "归纳者" {
		t.Errorf("entity_name: want 归纳者, got %q", it.EntityName)
	}
	if it.RawFingerprint == "" {
		t.Errorf("raw_fingerprint must be set")
	}

	// POST canonical with the fetched fingerprint → value stored, dirty cleared, synced stamped.
	body, _ := json.Marshal(map[string]string{
		"attr_code": "appearance", "canonical_value": "a tall, short warrior",
		"raw_fingerprint": it.RawFingerprint,
	})
	wreq := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/entities/"+eid+"/canonical", strings.NewReader(string(body)))
	wreq.Header.Set("X-Internal-Token", token)
	ww := httptest.NewRecorder()
	srv.Router().ServeHTTP(ww, wreq)
	if ww.Code != http.StatusOK {
		t.Fatalf("POST canonical: want 200, got %d body=%s", ww.Code, ww.Body.String())
	}

	var cv *string
	var dirtyFlag bool
	var synced *string
	pool.QueryRow(ctx, `
		SELECT canonical_value, canonical_dirty, canonical_synced_at::text
		  FROM entity_attribute_values eav
		  JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		 WHERE eav.entity_id=$1 AND ba.code='appearance'`, eid).Scan(&cv, &dirtyFlag, &synced)
	if cv == nil || *cv != "a tall, short warrior" {
		t.Errorf("canonical_value: want set, got %v", cv)
	}
	if dirtyFlag {
		t.Errorf("canonical_dirty must clear on a matching fingerprint")
	}
	if synced == nil {
		t.Errorf("canonical_synced_at must be stamped")
	}
	var nEvents int
	pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`, eid,
	).Scan(&nEvents)
	if nEvents < 1 {
		t.Errorf("want >=1 glossary.entity_updated event, got %d", nEvents)
	}
}

// TestCanonical_StaleFingerprintKeepsDirty proves compare-and-clear: if the raw set changed
// since the fetch (fingerprint mismatch), the canonical is still written but dirty STAYS true
// so the next pass re-synthesizes — no lost update from a concurrent extraction.
func TestCanonical_StaleFingerprintKeepsDirty(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runCanonContentMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a2044"
	eid := seedSummarizeDirtyEntity(t, pool, bookID, "残卷", `["tall","short","scarred"]`)

	srv, token := newCanonicalServer(t)
	srv.pool = pool

	body, _ := json.Marshal(map[string]string{
		"attr_code": "appearance", "canonical_value": "stale synthesis",
		"raw_fingerprint": "deadbeefdeadbeefdeadbeefdeadbeef", // never matches md5(original_value)
	})
	wreq := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/entities/"+eid+"/canonical", strings.NewReader(string(body)))
	wreq.Header.Set("X-Internal-Token", token)
	ww := httptest.NewRecorder()
	srv.Router().ServeHTTP(ww, wreq)
	if ww.Code != http.StatusOK {
		t.Fatalf("POST canonical: want 200, got %d body=%s", ww.Code, ww.Body.String())
	}

	var cv *string
	var dirtyFlag bool
	pool.QueryRow(ctx, `
		SELECT canonical_value, canonical_dirty
		  FROM entity_attribute_values eav
		  JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		 WHERE eav.entity_id=$1 AND ba.code='appearance'`, eid).Scan(&cv, &dirtyFlag)
	if cv == nil || *cv != "stale synthesis" {
		t.Errorf("canonical_value should still be written, got %v", cv)
	}
	if !dirtyFlag {
		t.Errorf("stale fingerprint must KEEP canonical_dirty true (re-synthesize next pass)")
	}
}

// TestWriteCanonical_NonSummarizeAttrReturns404 confirms a non-summarize attr (or stale entity)
// is a 404, not a silent write — the endpoint only serves the summarize tier.
func TestWriteCanonical_NonSummarizeAttrReturns404(t *testing.T) {
	pool := openTestDB(t)
	runCanonContentMigrations(t, pool)
	bookID := "00000000-0000-0000-0001-0000000a2045"
	// appearance is summarize here, but we target a DIFFERENT code that isn't summarize.
	eid := seedSummarizeDirtyEntity(t, pool, bookID, "杂项", `["x"]`)

	srv, token := newCanonicalServer(t)
	srv.pool = pool
	body, _ := json.Marshal(map[string]string{"attr_code": "personality", "canonical_value": "y"})
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/entities/"+eid+"/canonical", strings.NewReader(string(body)))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusNotFound {
		t.Errorf("non-summarize attr: want 404, got %d body=%s", w.Code, w.Body.String())
	}
}
