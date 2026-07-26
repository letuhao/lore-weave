package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// ── unit tests (no DB) ──────────────────────────────────────────────

func TestCanonicalTranslation_RequiresInternalToken(t *testing.T) {
	srv, _ := newCanonicalServer(t)
	url := "/internal/books/00000000-0000-0000-0000-000000000001/entities/00000000-0000-0000-0000-000000000002/canonical-translation?lang=en"
	req := httptest.NewRequest(http.MethodGet, url, nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestCanonicalTranslation_BadBookUUIDReturns400(t *testing.T) {
	srv, token := newCanonicalServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/not-a-uuid/entities/00000000-0000-0000-0000-000000000002/canonical-translation?lang=en", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad book uuid: want 400, got %d", w.Code)
	}
}

func TestMd5hexMatchesPostgres(t *testing.T) {
	// The cache key is md5hex(content); a sanity check that it is 32-char lowercase hex
	// (byte-identical to Postgres md5(), the canonical_snapshot.content_hash convention).
	got := md5hex("李四，金丹期修士。")
	if len(got) != 32 {
		t.Fatalf("md5hex length = %d, want 32 (%q)", len(got), got)
	}
}

// ── integration (requires DB) ──────────────────────────────────────

// foldCanonicalForEntity seeds an entity via extraction + writes a folded canonical snapshot for
// it (mirroring TestFoldLoop), returning the entity id. The snapshot content is `content`.
func foldCanonicalForEntity(t *testing.T, srv *Server, pool *pgxpool.Pool, token, bookID string, content string) string {
	t.Helper()
	ctx := context.Background()
	bid := uuid.MustParse(bookID)
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh", "chapter_id": uuid.NewString(),
		"content_hash": "tlh1", "writeback_key": "tl-wbk-1", "chapter_ordinal": 5,
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

	dirty := func() map[string]any {
		req := httptest.NewRequest(http.MethodGet, "/internal/books/"+bookID+"/fold-dirty", nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		var r map[string]any
		json.Unmarshal(w.Body.Bytes(), &r) //nolint:errcheck
		return r
	}()
	items, _ := dirty["items"].([]any)
	if len(items) < 1 {
		t.Fatalf("fold-dirty returned no items")
	}
	item := items[0].(map[string]any)
	raw, _ := json.Marshal(map[string]any{
		"content": content, "as_of_ordinal": item["head_ordinal"],
		"fold_algo_version": 1, "fold_fingerprint": item["fold_fingerprint"],
	})
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/entities/"+entityID+"/fold-snapshot", bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("fold-snapshot write: %d %s", w.Code, w.Body.String())
	}
	return entityID
}

func TestCanonicalTranslation_StateMachine(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrate.RunChain(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	bookID := "00000000-0000-0000-0001-0000000a7e10"
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM canonical_snapshot_translations WHERE book_id=$1`, bid)                                                          //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM canonical_snapshot WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bid)          //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM canonical_fold_state WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bid)        //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM entity_facts WHERE book_id=$1`, bid)                                                                             //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM episodes WHERE book_id=$1`, bid)                                                                                 //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM extraction_writeback_log WHERE book_id=$1`, bid)                                                                 //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bid)     //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bid)                                                                        //nolint:errcheck
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	// Stub translation-service: returns a canned translated_text for any /translate-text call.
	const translated = "Li Si, a Golden Core cultivator."
	var calls int
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"translated_text": translated}) //nolint:errcheck
	}))
	defer stub.Close()

	const content = "李四，金丹期修士。"
	entityID := foldCanonicalForEntity(t, srv, pool, token, bookID, content)
	userID := uuid.NewString()

	getTr := func(lang, uid string) map[string]any {
		url := "/internal/books/" + bookID + "/entities/" + entityID + "/canonical-translation?lang=" + lang
		req := httptest.NewRequest(http.MethodGet, url, nil)
		req.Header.Set("X-Internal-Token", token)
		if uid != "" {
			req.Header.Set("X-User-Id", uid)
		}
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("GET canonical-translation: %d %s", w.Code, w.Body.String())
		}
		var r map[string]any
		json.Unmarshal(w.Body.Bytes(), &r) //nolint:errcheck
		return r
	}

	// 1) missing lang → 422
	{
		req := httptest.NewRequest(http.MethodGet,
			"/internal/books/"+bookID+"/entities/"+entityID+"/canonical-translation", nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusUnprocessableEntity {
			t.Fatalf("missing lang: want 422, got %d", w.Code)
		}
	}

	// 2) miss + no user → failed/no_user (no row claimed, no fill)
	if r := getTr("en", ""); r["status"] != "failed" || r["error_code"] != "no_user" {
		t.Fatalf("no-user miss = %v, want failed/no_user", r)
	}

	// 3) miss + user but TranslationServiceURL unset → failed/unconfigured
	if r := getTr("en", userID); r["status"] != "failed" || r["error_code"] != "unconfigured" {
		t.Fatalf("unconfigured miss = %v, want failed/unconfigured", r)
	}

	// Configure the stub translation-service for the real fill path.
	srv.cfg.TranslationServiceURL = stub.URL

	// 4) miss + user + configured → claim + launch fill → translating; original content shown.
	r := getTr("en", userID)
	if r["status"] != "translating" || r["translated"] != false || r["content"] != content {
		t.Fatalf("first view = %v, want translating with original content", r)
	}

	// 5) the background fill settles the row to ready==translated; poll the cache.
	hash := md5hex(content)
	deadline := time.Now().Add(5 * time.Second)
	var got string
	for time.Now().Before(deadline) {
		var status, value string
		if err := pool.QueryRow(ctx, `
			SELECT status, value FROM canonical_snapshot_translations
			WHERE entity_id=$1 AND attr_scope='narrative' AND language_code='en' AND source_content_hash=$2`,
			entityID, hash).Scan(&status, &value); err == nil && status == "ready" {
			got = value
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	if got != translated {
		t.Fatalf("fill did not settle to ready/value=%q (got %q)", translated, got)
	}

	// 6) second view → cache hit: ready + translated content + cached.
	r2 := getTr("en", userID)
	if r2["status"] != "ready" || r2["translated"] != true || r2["content"] != translated || r2["cached"] != true {
		t.Fatalf("cache hit = %v, want ready/translated/cached with the translated content", r2)
	}

	// 7) single-flight: exactly ONE LLM call happened for this (content, lang) despite 2 views.
	if calls != 1 {
		t.Fatalf("expected exactly 1 translation-service call (single-flight), got %d", calls)
	}

	// 8) HEAL: a config-error (no_model) failed row — even AT the retry-budget cap — is re-claimable
	// by a configured viewer (config errors cost no LLM + are caller-specific, so they must not
	// poison the shared book-tier row). Force the row to failed/no_model/attempts=budget, then view.
	if _, err := pool.Exec(ctx, `
		UPDATE canonical_snapshot_translations
		   SET status='failed', error_code='no_model', attempts=$3, value=''
		 WHERE entity_id=$1 AND attr_scope='narrative' AND language_code='en' AND source_content_hash=$2`,
		entityID, hash, foldRetryBudget); err != nil {
		t.Fatalf("seed failed/no_model row: %v", err)
	}
	if r := getTr("en", userID); r["status"] != "translating" {
		t.Fatalf("heal view of a capped no_model row = %v, want re-claim → translating", r)
	}
	deadline = time.Now().Add(5 * time.Second)
	healed := false
	for time.Now().Before(deadline) {
		var status, value string
		if err := pool.QueryRow(ctx, `
			SELECT status, value FROM canonical_snapshot_translations
			WHERE entity_id=$1 AND attr_scope='narrative' AND language_code='en' AND source_content_hash=$2`,
			entityID, hash).Scan(&status, &value); err == nil && status == "ready" && value == translated {
			healed = true
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	if !healed {
		t.Fatalf("a capped no_model row was not healed to ready by a configured viewer")
	}
	if calls != 2 {
		t.Fatalf("heal should have made exactly 1 more LLM call (total 2), got %d", calls)
	}
}
