package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// GLOSS-DISPLAY-LANG — list entities resolves display_name from translations
// when display_language query param is set.

func TestListEntities_DisplayLanguageResolvesName(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id, language_code, value, confidence)
		 VALUES($1, 'vi', 'Hỏa Ma', 'machine')`,
		f.nameAttrVal)

	path := "/v1/glossary/books/" + f.bookID.String() + "/entities?display_language=vi"
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("list: want 200, got %d %s", w.Code, w.Body.String())
	}

	var resp entityListResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("want 1 item, got %d", len(resp.Items))
	}
	item := resp.Items[0]
	if item.DisplayName != "Hỏa Ma" {
		t.Errorf("display_name: want Hỏa Ma, got %q", item.DisplayName)
	}
	if item.DisplayNameTranslation == nil || *item.DisplayNameTranslation != "Hỏa Ma" {
		t.Errorf("display_name_translation: want Hỏa Ma, got %v", item.DisplayNameTranslation)
	}
}

func TestListEntities_DisplayLanguageFallsBackToOriginal(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	path := "/v1/glossary/books/" + f.bookID.String() + "/entities?display_language=vi"
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("list: want 200, got %d %s", w.Code, w.Body.String())
	}

	var resp entityListResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("want 1 item, got %d", len(resp.Items))
	}
	if resp.Items[0].DisplayName != "Nezha" {
		t.Errorf("display_name fallback: want Nezha, got %q", resp.Items[0].DisplayName)
	}
	if resp.Items[0].DisplayNameTranslation != nil {
		t.Errorf("display_name_translation should be null on fallback, got %v", resp.Items[0].DisplayNameTranslation)
	}
}

func TestListEntities_SearchMatchesTranslatedName(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id, language_code, value, confidence)
		 VALUES($1, 'vi', 'Hỏa Ma', 'machine')`,
		f.nameAttrVal)

	path := "/v1/glossary/books/" + f.bookID.String() + "/entities?display_language=vi&search=Hỏa"
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("search: want 200, got %d %s", w.Code, w.Body.String())
	}

	var resp entityListResp
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if resp.Total != 1 {
		t.Errorf("search translated name: want total=1, got %d", resp.Total)
	}
}
