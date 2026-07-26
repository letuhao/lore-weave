package api

// import_pdf_test.go — docs/specs/2026-07-06-pdf-book-import.md.
//
// Covers pdfPeekClientCall (the pure HTTP-client piece) against a fake
// knowledge-service. The pdfPeek HTTP handler itself needs authBook's DB
// pool (no pgxmock harness exists for this file's other handlers either
// — startImport/listImportJobs/getImportJob are all untested today; this
// stays consistent with that, not a new gap introduced here).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/loreweave/book-service/internal/config"
)

func TestPdfPeekClientCall_HappyPath(t *testing.T) {
	var gotPath, gotToken string
	var gotBody struct {
		PdfBytesB64 string `json:"pdf_bytes_b64"`
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotToken = r.Header.Get("X-Internal-Token")
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"page_count": 12}`))
	}))
	defer srv.Close()

	s := &Server{cfg: &config.Config{KnowledgeServiceURL: srv.URL, InternalServiceToken: "tok-123"}}
	count, err := s.pdfPeekClientCall(context.Background(), []byte("fake pdf bytes"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if count != 12 {
		t.Errorf("page_count=%d, want 12", count)
	}
	if gotPath != "/internal/parse/pdf-peek" {
		t.Errorf("path=%s, want /internal/parse/pdf-peek", gotPath)
	}
	if gotToken != "tok-123" {
		t.Errorf("token=%q, want tok-123", gotToken)
	}
	if gotBody.PdfBytesB64 == "" {
		t.Error("expected non-empty pdf_bytes_b64 in request body")
	}
}

func TestPdfPeekClientCall_UnprocessableEntityMapsToPdfUpstreamError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail": "cannot open PDF: password-protected"}`))
	}))
	defer srv.Close()

	s := &Server{cfg: &config.Config{KnowledgeServiceURL: srv.URL, InternalServiceToken: "tok"}}
	_, err := s.pdfPeekClientCall(context.Background(), []byte("fake"))
	if err == nil {
		t.Fatal("expected error")
	}
	upstreamErr, ok := err.(*pdfUpstreamError)
	if !ok {
		t.Fatalf("err=%v (%T), want *pdfUpstreamError", err, err)
	}
	if upstreamErr.status != http.StatusUnprocessableEntity {
		t.Errorf("status=%d, want 422", upstreamErr.status)
	}
	if upstreamErr.detail != "cannot open PDF: password-protected" {
		t.Errorf("detail=%q", upstreamErr.detail)
	}
}

func TestPdfPeekClientCall_GenericUpstreamErrorNotTypedAsPdfError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`boom`))
	}))
	defer srv.Close()

	s := &Server{cfg: &config.Config{KnowledgeServiceURL: srv.URL, InternalServiceToken: "tok"}}
	_, err := s.pdfPeekClientCall(context.Background(), []byte("fake"))
	if err == nil {
		t.Fatal("expected error")
	}
	if _, ok := err.(*pdfUpstreamError); ok {
		t.Error("a generic 500 must NOT be typed as *pdfUpstreamError (that's reserved for 422)")
	}
}
