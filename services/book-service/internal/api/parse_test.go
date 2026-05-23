package api

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/loreweave/book-service/internal/config"
)

// parse_test.go — P1 (H1 fix) book-service .txt sync path contract tests.
//
// Full end-to-end (with pgx + .txt -> parts/scenes -> DB) is validated at
// VERIFY phase live smoke. These tests cover the cross-service contract
// of parseClientCall (the HTTP shim around knowledge-service /internal/parse).

func TestParseClientCallSuccess(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Token") != "tok" {
			t.Errorf("missing X-Internal-Token: %q", r.Header.Get("X-Internal-Token"))
		}
		if r.URL.Path != "/internal/parse" {
			t.Errorf("wrong path: %q", r.URL.Path)
		}
		body, _ := io.ReadAll(r.Body)
		var req map[string]any
		_ = json.Unmarshal(body, &req)
		if req["source_format"] != "plain" {
			t.Errorf("expected source_format=plain, got %v", req["source_format"])
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
  "source_format":"plain","walker_path":"headings","detected_language":"en","book_title":null,
  "parts":[{"sort_order":1,"title":null,"path":"book/part-1","chapters":[
    {"sort_order":1,"title":"Chapter 1","path":"book/part-1/chapter-1","html":"","scenes":[
      {"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"x","content_hash":"abc"}
    ]}
  ]}]
}`))
	}))
	defer srv.Close()

	s := &Server{cfg: &config.Config{
		KnowledgeServiceURL:  srv.URL,
		InternalServiceToken: "tok",
	}}
	tree, err := s.parseClientCall(context.Background(), "plain", "Chapter 1\nbody.", "en", "novel.txt")
	if err != nil {
		t.Fatalf("parseClientCall error: %v", err)
	}
	if tree.SourceFormat != "plain" {
		t.Errorf("wrong source_format: %q", tree.SourceFormat)
	}
	if len(tree.Parts) != 1 || len(tree.Parts[0].Chapters) != 1 || len(tree.Parts[0].Chapters[0].Scenes) != 1 {
		t.Errorf("wrong tree shape: %+v", tree)
	}
	if tree.DetectedLanguage == nil || *tree.DetectedLanguage != "en" {
		t.Errorf("detected_language not propagated: %+v", tree.DetectedLanguage)
	}
}

func TestParseClientCallSendsInternalToken(t *testing.T) {
	t.Parallel()
	tokenReceived := ""
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tokenReceived = r.Header.Get("X-Internal-Token")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"source_format":"plain","walker_path":"headings","parts":[{"sort_order":1,"path":"book/part-1","chapters":[{"sort_order":1,"path":"book/part-1/chapter-1","html":"","scenes":[{"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"x","content_hash":"a"}]}]}]}`))
	}))
	defer srv.Close()
	s := &Server{cfg: &config.Config{
		KnowledgeServiceURL:  srv.URL,
		InternalServiceToken: "secret-token-42",
	}}
	_, _ = s.parseClientCall(context.Background(), "plain", "x", "", "")
	if tokenReceived != "secret-token-42" {
		t.Errorf("X-Internal-Token not sent, got: %q", tokenReceived)
	}
}

func TestParseClientCallReturnsErrorOnNon200(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail":"empty content"}`))
	}))
	defer srv.Close()
	s := &Server{cfg: &config.Config{
		KnowledgeServiceURL:  srv.URL,
		InternalServiceToken: "tok",
	}}
	_, err := s.parseClientCall(context.Background(), "plain", "", "", "")
	if err == nil {
		t.Fatal("expected error for non-200")
	}
	if !strings.Contains(err.Error(), "422") {
		t.Errorf("error should include 422: %v", err)
	}
}

func TestParseClientCallOmitsEmptyLanguageAndFilename(t *testing.T) {
	t.Parallel()
	var got map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &got)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"source_format":"plain","walker_path":"headings","parts":[{"sort_order":1,"path":"book/part-1","chapters":[{"sort_order":1,"path":"book/part-1/chapter-1","html":"","scenes":[{"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"x","content_hash":"a"}]}]}]}`))
	}))
	defer srv.Close()
	s := &Server{cfg: &config.Config{
		KnowledgeServiceURL:  srv.URL,
		InternalServiceToken: "tok",
	}}
	_, err := s.parseClientCall(context.Background(), "plain", "x", "", "")
	if err != nil {
		t.Fatalf("Call returned error: %v", err)
	}
	if _, present := got["language"]; present {
		t.Errorf("language should be omitted when empty: %+v", got)
	}
	if _, present := got["filename"]; present {
		t.Errorf("filename should be omitted when empty: %+v", got)
	}
}

func TestAllowedImportFormatsIncludesMD(t *testing.T) {
	t.Parallel()
	if _, ok := allowedImportFormats[".md"]; !ok {
		t.Fatal("P1: .md must be in allowedImportFormats")
	}
	if allowedImportFormats[".md"] != "markdown" {
		t.Errorf(".md should map to 'markdown', got %q", allowedImportFormats[".md"])
	}
	// Sanity — existing formats unchanged.
	if allowedImportFormats[".txt"] != "txt" {
		t.Error(".txt mapping regressed")
	}
	if allowedImportFormats[".epub"] != "epub" {
		t.Error(".epub mapping regressed")
	}
}

func TestSceneContentHashFromBytesMatchesSDK(t *testing.T) {
	t.Parallel()
	// Lock that the Go-side helper matches the SDK's sha256 hex pipeline.
	// The Python SDK does: hashlib.sha256(leaf_text.encode("utf-8")).hexdigest()
	// Go: sha256.Sum256([]byte(leaf_text)) -> hex.
	want := "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae" // sha256("foo")
	got := sceneContentHashFromBytes([]byte("foo"))
	if got != want {
		t.Errorf("hash mismatch: got %q, want %q", got, want)
	}
}
