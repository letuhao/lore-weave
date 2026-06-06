package api

// Tests for GET /internal/books/{book_id}/translation-glossary.
// D-TRANSL-M1D: the response carries the target translation's `confidence` tier
// (verified|machine|draft) so the translation V3 verifier can hard-enforce only
// canon. DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

// callTranslationGlossary issues a GET against the internal endpoint and decodes
// the JSON array body. Internal-token header is set when token != "".
func callTranslationGlossary(t *testing.T, srv *Server, bookID, targetLang, token string) (*httptest.ResponseRecorder, []map[string]any) {
	t.Helper()
	url := "/internal/books/" + bookID + "/translation-glossary?target_language=" + targetLang
	req := httptest.NewRequest(http.MethodGet, url, nil)
	if token != "" {
		req.Header.Set("X-Internal-Token", token)
	}
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		return w, nil
	}
	var items []map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &items); err != nil {
		t.Fatalf("decode response: %v; body=%s", err, w.Body.String())
	}
	return w, items
}

// seedTranslationEntity inserts one active entity with a zh name attribute and a
// target-language translation at the given confidence, returning the entity_id.
func seedTranslationEntity(t *testing.T, pool *pgxpool.Pool, bookID, name, targetLang, value, confidence string) string {
	t.Helper()
	ctx := context.Background()
	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID,
	).Scan(&nameAttrID)

	var eid string
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}')
		 RETURNING entity_id`, bookID, kindID,
	).Scan(&eid); err != nil {
		t.Fatalf("insert entity: %v", err)
	}
	var attrValueID string
	if err := pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3) RETURNING attr_value_id`, eid, nameAttrID, name,
	).Scan(&attrValueID); err != nil {
		t.Fatalf("insert name attr: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id,language_code,value,confidence)
		 VALUES($1,$2,$3,$4)`, attrValueID, targetLang, value, confidence,
	); err != nil {
		t.Fatalf("insert translation: %v", err)
	}
	return eid
}

// seedNameOnlyEntity inserts an active entity with a zh name but NO target
// translation (exercises the nameTarget=="" path).
func seedNameOnlyEntity(t *testing.T, pool *pgxpool.Pool, bookID, name string) string {
	t.Helper()
	ctx := context.Background()
	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID,
	).Scan(&nameAttrID)

	var eid string
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}')
		 RETURNING entity_id`, bookID, kindID,
	).Scan(&eid); err != nil {
		t.Fatalf("insert entity: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3)`, eid, nameAttrID, name,
	); err != nil {
		t.Fatalf("insert name attr: %v", err)
	}
	return eid
}

// ── auth (no DB) ─────────────────────────────────────────────────────────────

func TestTranslationGlossary_RequiresInternalToken(t *testing.T) {
	srv, _ := newContextTestServer(t, nil)
	w, _ := callTranslationGlossary(t, srv, "00000000-0000-0000-0000-000000000001", "vi", "")
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestTranslationGlossary_MissingTargetLangReturns400(t *testing.T) {
	srv, token := newContextTestServer(t, nil)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/translation-glossary", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("missing target_language: want 400, got %d", w.Code)
	}
}

// ── confidence exposure (real DB) ───────────────────────────────────────────

func TestTranslationGlossary_ExposesConfidenceTier(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000d4001"
	seedTranslationEntity(t, pool, bookID, "提拉米", "vi", "Tirami", "verified")
	seedTranslationEntity(t, pool, bookID, "阿尔德里克", "vi", "Aldric", "machine")
	// An active entity with NO target translation must still be returned, with
	// no confidence key (guards the nameTarget=="" scan/emit path).
	seedNameOnlyEntity(t, pool, bookID, "无译名")
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	w, items := callTranslationGlossary(t, srv, bookID, "vi", token)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}

	// Index by zh name → (confidence, hasConfidenceKey).
	type entry struct {
		conf   string
		hasKey bool
	}
	got := map[string]entry{}
	for _, it := range items {
		zh, _ := it["zh"].([]any)
		if len(zh) == 0 {
			continue
		}
		name, _ := zh[0].(string)
		conf, hasKey := it["confidence"].(string)
		got[name] = entry{conf, hasKey}
	}
	if got["提拉米"].conf != "verified" {
		t.Errorf("提拉米: want confidence=verified, got %q (items=%+v)", got["提拉米"].conf, items)
	}
	if got["阿尔德里克"].conf != "machine" {
		t.Errorf("阿尔德里克: want confidence=machine, got %q (items=%+v)", got["阿尔德里克"].conf, items)
	}
	if _, ok := got["无译名"]; !ok {
		t.Errorf("name-only entity dropped from result (items=%+v)", items)
	}
	if got["无译名"].hasKey {
		t.Errorf("name-only entity should carry NO confidence key, got %q", got["无译名"].conf)
	}
}
