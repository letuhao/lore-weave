package tasks

// import_processor_pdf_test.go — docs/specs/2026-07-06-pdf-book-import.md.
//
// Covers the pure helpers (plainTextToHTML, pdfImageExtToContentType) and
// the new parse_client_pdf.go HTTP methods (PdfPeek, CallPdfChunk) against
// a fake knowledge-service. processPdfImport itself needs a real Postgres
// pool + MinIO client (no mock harness exists for import_processor.go's
// sibling processImport either — this stays consistent with that gap,
// not a new one introduced here; covered instead by the cross-service
// live smoke in Phase 7).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ── plainTextToHTML ──────────────────────────────────────────────────────

func TestPlainTextToHTML_WrapsParagraphs(t *testing.T) {
	got := plainTextToHTML("First para.\n\nSecond para.")
	want := "<p>First para.</p><p>Second para.</p>"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestPlainTextToHTML_EscapesHTML(t *testing.T) {
	got := plainTextToHTML("Revenue < 100 & rising")
	if strings.Contains(got, "< 100 &") {
		t.Errorf("expected HTML-escaping, got unescaped content: %q", got)
	}
	if !strings.Contains(got, "&lt;") || !strings.Contains(got, "&amp;") {
		t.Errorf("expected &lt;/&amp; escapes, got %q", got)
	}
}

func TestPlainTextToHTML_EmptyReturnsSinglePTag(t *testing.T) {
	if got := plainTextToHTML(""); got != "<p></p>" {
		t.Errorf("got %q, want <p></p>", got)
	}
}

func TestPlainTextToHTML_BlankParagraphsSkipped(t *testing.T) {
	got := plainTextToHTML("Only para.\n\n\n\n")
	if got != "<p>Only para.</p>" {
		t.Errorf("got %q", got)
	}
}

// ── pdfImageExtToContentType ─────────────────────────────────────────────

func TestPdfImageExtToContentType(t *testing.T) {
	cases := map[string]string{
		"png": "image/png", "PNG": "image/png",
		"jpg": "image/jpeg", "jpeg": "image/jpeg",
		"webp": "image/webp", "gif": "image/gif",
		"bmp": "application/octet-stream", "": "application/octet-stream",
	}
	for ext, want := range cases {
		if got := pdfImageExtToContentType(ext); got != want {
			t.Errorf("ext=%q: got %q, want %q", ext, got, want)
		}
	}
}

// ── ParseClient.PdfPeek ───────────────────────────────────────────────────

func TestParseClient_PdfPeek_HappyPath(t *testing.T) {
	var gotPath, gotToken string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotToken = r.Header.Get("X-Internal-Token")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"page_count": 42}`))
	}))
	defer srv.Close()

	c := NewParseClient(srv.URL, "tok-abc")
	count, err := c.PdfPeek(context.Background(), []byte("fake pdf"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if count != 42 {
		t.Errorf("count=%d, want 42", count)
	}
	if gotPath != "/internal/parse/pdf-peek" {
		t.Errorf("path=%s", gotPath)
	}
	if gotToken != "tok-abc" {
		t.Errorf("token=%q", gotToken)
	}
}

func TestParseClient_PdfPeek_UpstreamErrorPropagates(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail": "cannot open PDF: password-protected"}`))
	}))
	defer srv.Close()

	c := NewParseClient(srv.URL, "tok")
	_, err := c.PdfPeek(context.Background(), []byte("fake"))
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "password-protected") {
		t.Errorf("expected upstream detail in error, got %v", err)
	}
}

// ── ParseClient.CallPdfChunk ──────────────────────────────────────────────

func TestParseClient_CallPdfChunk_HappyPath(t *testing.T) {
	var gotBody pdfChunkRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/parse/pdf-chunk" {
			t.Errorf("path=%s", r.URL.Path)
		}
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"chapter": {
				"sort_order": 1, "title": "Pages 1-5", "path": "chunk-0", "html": "",
				"scenes": [{"sort_order": 1, "path": "chunk-0/scene-1", "leaf_text": "hello", "content_hash": "abc"}]
			},
			"images": [
				{"page_number": 2, "image_bytes_b64": "aW1n", "ext": "png", "caption": "A chart.", "model_ref": "m1"}
			]
		}`))
	}))
	defer srv.Close()

	c := NewParseClient(srv.URL, "tok")
	result, err := c.CallPdfChunk(context.Background(), PdfChunkParams{
		BookID: "book-1", PdfBytes: []byte("fake"), PageStart: 1, PageEnd: 5,
		ChunkIndex: 0, CaptionImages: true, Language: "en",
		UserID: "user-1", ModelSource: "user_model", ModelRef: "model-1",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Chapter.Path != "chunk-0" || len(result.Chapter.Scenes) != 1 {
		t.Errorf("chapter=%+v", result.Chapter)
	}
	if len(result.Images) != 1 || *result.Images[0].Caption != "A chart." {
		t.Errorf("images=%+v", result.Images)
	}
	if gotBody.PageStart != 1 || gotBody.PageEnd != 5 || gotBody.ChunkIndex != 0 {
		t.Errorf("request body=%+v", gotBody)
	}
	if !gotBody.CaptionImages || gotBody.ModelRef != "model-1" {
		t.Errorf("expected caption_images=true + model_ref forwarded, got %+v", gotBody)
	}
}

func TestParseClient_CallPdfChunk_UpstreamErrorPropagates(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`boom`))
	}))
	defer srv.Close()

	c := NewParseClient(srv.URL, "tok")
	_, err := c.CallPdfChunk(context.Background(), PdfChunkParams{BookID: "b", PdfBytes: []byte("x"), PageStart: 1, PageEnd: 1})
	if err == nil {
		t.Fatal("expected error")
	}
}
