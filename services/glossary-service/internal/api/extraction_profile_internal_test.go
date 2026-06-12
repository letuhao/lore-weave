package api

// Regression: internal extraction-profile must work with X-Internal-Token only
// (translation-service worker/router). Delegating to JWT-gated getExtractionProfile
// caused kinds_metadata=[] → 0 LLM batches → instant 0-entity jobs.

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestInternalExtractionProfile_RequiresInternalToken(t *testing.T) {
	srv, _ := newEntitiesListServer(t)
	bookID := "00000000-0000-0000-0000-000000000001"
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/extraction-profile", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestInternalExtractionProfile_ReturnsKindsWithoutJWT(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-000b-0000000b1001"

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/extraction-profile", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}
	if strings.Contains(w.Body.String(), "Bearer token") {
		t.Fatalf("internal route must not require JWT, body=%s", w.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	kinds, ok := body["kinds"].([]any)
	if !ok || len(kinds) == 0 {
		t.Fatalf("want non-empty kinds, got %v", body["kinds"])
	}
}
