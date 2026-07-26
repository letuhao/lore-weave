package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// KG-ML M5 (C9) — POST /internal/books/{book_id}/entity-display-names resolves
// each entity's name/term value to the requested language (translation when
// present, else the canonical value with translated=false), internal-token gated,
// book-scoped + soft-absent for unknown ids.

func displayNamesReq(t *testing.T, f *versionFixture, body, token string) *httptest.ResponseRecorder {
	t.Helper()
	path := "/internal/books/" + f.bookID.String() + "/entity-display-names"
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
	if token != "" {
		req.Header.Set("X-Internal-Token", token)
	}
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestEntityDisplayNames_RequiresInternalToken(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	w := displayNamesReq(t, f, `{"language":"vi","entity_ids":[]}`, "")
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestEntityDisplayNames_RequiresLanguage(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	w := displayNamesReq(t, f, `{"entity_ids":["`+f.entityID.String()+`"]}`, "tok")
	if w.Code != http.StatusBadRequest {
		t.Errorf("missing language: want 400, got %d %s", w.Code, w.Body.String())
	}
}

func TestEntityDisplayNames_ResolvesTranslation(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()
	if _, err := pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id, language_code, value, confidence)
		 VALUES($1, 'vi', 'Na Tra', 'machine')`,
		f.nameAttrVal); err != nil {
		t.Fatalf("seed translation: %v", err)
	}

	w := displayNamesReq(t, f, `{"language":"vi","entity_ids":["`+f.entityID.String()+`"]}`, "tok")
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d %s", w.Code, w.Body.String())
	}
	var resp entityDisplayNamesResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("want 1 item, got %d", len(resp.Items))
	}
	it := resp.Items[0]
	if it.EntityID != f.entityID.String() {
		t.Errorf("entity_id: want %s, got %s", f.entityID, it.EntityID)
	}
	if it.DisplayName != "Na Tra" {
		t.Errorf("display_name: want Na Tra, got %q", it.DisplayName)
	}
	if !it.Translated {
		t.Errorf("translated: want true, got false")
	}
}

func TestEntityDisplayNames_FallsBackToCanonical(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	w := displayNamesReq(t, f, `{"language":"vi","entity_ids":["`+f.entityID.String()+`"]}`, "tok")
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d %s", w.Code, w.Body.String())
	}
	var resp entityDisplayNamesResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("want 1 item, got %d", len(resp.Items))
	}
	it := resp.Items[0]
	if it.DisplayName != "Nezha" {
		t.Errorf("display_name: want canonical Nezha, got %q", it.DisplayName)
	}
	if it.Translated {
		t.Errorf("translated: want false (source fallback), got true")
	}
}

func TestEntityDisplayNames_UnknownIDsDropped(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	// A well-formed but non-existent id + a malformed id are both soft-absent.
	body := `{"language":"vi","entity_ids":["` + uuid.NewString() + `","not-a-uuid","` + f.entityID.String() + `"]}`
	w := displayNamesReq(t, f, body, "tok")
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d %s", w.Code, w.Body.String())
	}
	var resp entityDisplayNamesResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("only the real entity should resolve, got %d items", len(resp.Items))
	}
	if resp.Items[0].EntityID != f.entityID.String() {
		t.Errorf("want the real entity, got %s", resp.Items[0].EntityID)
	}
}
