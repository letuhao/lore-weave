package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestBookIntegrityRequiresBearerToken(t *testing.T) {
	srv := newExportServer(t, nil)
	req := httptest.NewRequest(http.MethodGet, "/v1/glossary/books/00000000-0000-0000-0000-000000000001/integrity", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
}

func TestBookIntegrityRejectsBadBookIDBeforeGrantLookup(t *testing.T) {
	srv := newExportServer(t, nil)
	req := httptest.NewRequest(http.MethodGet, "/v1/glossary/books/not-a-uuid/integrity", nil)
	req.Header.Set("Authorization", "Bearer "+makeExportToken(t, "00000000-0000-0000-0000-000000000001"))
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d (%s)", w.Code, w.Body.String())
	}
}
