package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGlossaryTranslate_RequiresInternalToken(t *testing.T) {
	srv, _ := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/translation-candidates?target_language=vi", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestGlossaryTranslate_CandidatesMissingLang(t *testing.T) {
	srv, token := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/translation-candidates", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestGlossaryTranslate_ApplyWritesMachineMultiAttr(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e3001"
	ctx := context.Background()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	var kindID, nameAttrID, descAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttrID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='description' LIMIT 1`, kindID).Scan(&descAttrID)

	var eid, nameAVID, descAVID string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&eid)
	pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3) RETURNING attr_value_id`, eid, nameAttrID, "焰魔").Scan(&nameAVID)
	pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3) RETURNING attr_value_id`, eid, descAttrID, "火焰恶魔").Scan(&descAVID)

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	body := map[string]any{
		"target_language": "vi",
		"items": []map[string]any{
			{"entity_id": eid, "attr_value_id": nameAVID, "value": "Diễm Ma"},
			{"entity_id": eid, "attr_value_id": descAVID, "value": "Ác ma lửa"},
		},
	}
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/apply-translations", bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("apply: want 200, got %d %s", w.Code, w.Body.String())
	}
	var resp applyTranslationsResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if resp.Translated != 2 {
		t.Errorf("want translated=2, got %+v", resp)
	}

	var nameVal, nameConf string
	pool.QueryRow(ctx, `
		SELECT at.value, at.confidence FROM attribute_translations at
		WHERE at.attr_value_id=$1 AND at.language_code='vi'`, nameAVID).Scan(&nameVal, &nameConf)
	if nameVal != "Diễm Ma" || nameConf != "machine" {
		t.Errorf("name: got %q/%q", nameConf, nameVal)
	}
}

func TestGlossaryTranslate_CandidatesMissingOnlyReturnsItems(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e3004"
	ctx := context.Background()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttrID)

	var eid string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&eid)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3)`, eid, nameAttrID, "测试名")

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/translation-candidates?target_language=vi&overwrite_mode=missing_only", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("candidates: %d %s", w.Code, w.Body.String())
	}
	var resp translationCandidatesResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if resp.Total < 1 || len(resp.Items) < 1 || len(resp.Items[0].Attributes) < 1 {
		t.Errorf("want candidates with attrs, got %+v", resp)
	}
}

func TestGlossaryTranslate_CandidatesRefreshMachineIncludesMachine(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e3003"
	ctx := context.Background()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	seedEntityWithTranslation(t, pool, bookID, "机器名", "vi", "Machine", "machine")

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/translation-candidates?target_language=vi&overwrite_mode=refresh_machine", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("candidates: %d %s", w.Code, w.Body.String())
	}
	var resp translationCandidatesResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if resp.Total < 1 || len(resp.Items) < 1 {
		t.Errorf("refresh_machine should include machine-confidence attrs, got %+v", resp)
	}
}

func TestGlossaryTranslate_DoesNotOverwriteVerified(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e3002"
	ctx := context.Background()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	seedEntityWithTranslation(t, pool, bookID, "阿尔德里克", "vi", "Aldric", "verified")
	var avid string
	pool.QueryRow(ctx, `
		SELECT eav.attr_value_id FROM entity_attribute_values eav
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN system_kind_attributes ad ON ad.attr_def_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ad.code='name' AND eav.original_value=$2`, bookID, "阿尔德里克").Scan(&avid)
	var eid string
	pool.QueryRow(ctx, `SELECT entity_id FROM glossary_entities WHERE book_id=$1 LIMIT 1`, bookID).Scan(&eid)

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	body := map[string]any{
		"target_language": "vi",
		"items": []map[string]any{
			{"entity_id": eid, "attr_value_id": avid, "value": "Overwrite"},
		},
	}
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/apply-translations", bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("apply: %d %s", w.Code, w.Body.String())
	}
	var resp applyTranslationsResp
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.SkippedVerified != 1 {
		t.Errorf("want skipped_verified=1, got %+v", resp)
	}
	val, conf, _ := nameTranslation(t, pool, bookID, "阿尔德里克", "vi")
	if val != "Aldric" || conf != "verified" {
		t.Errorf("verified clobbered: %q/%q", conf, val)
	}
}
