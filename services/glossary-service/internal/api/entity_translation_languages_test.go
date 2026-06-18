package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestListBookTranslationLanguages_ReturnsDistinctCodes(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id, language_code, value, confidence)
		 VALUES($1, 'vi', 'Hỏa Ma', 'machine')`,
		f.nameAttrVal)

	path := "/v1/glossary/books/" + f.bookID.String() + "/translation-languages"
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d %s", w.Code, w.Body.String())
	}

	var resp bookTranslationLanguagesResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if len(resp.Languages) != 1 || resp.Languages[0] != "vi" {
		t.Errorf("want [vi], got %v", resp.Languages)
	}
}

func TestListBookTranslationLanguages_EmptyWhenNoTranslations(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	path := "/v1/glossary/books/" + f.bookID.String() + "/translation-languages"
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d %s", w.Code, w.Body.String())
	}

	var resp bookTranslationLanguagesResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if len(resp.Languages) != 0 {
		t.Errorf("want empty languages, got %v", resp.Languages)
	}
}
