package tasks

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// parse_client_test.go — P1 cross-service contract tests for ParseClient.
// Full processImport flow (with mocked pgx + minio) is validated at
// VERIFY phase live smoke per memory `feedback_mock_only_coverage_hides_crossservice_bugs`.

func TestParseClientCallSuccess(t *testing.T) {
	t.Parallel()

	expected := StructuralTree{
		SourceFormat: "html",
		WalkerPath:   "headings",
		Parts: []Part{
			{
				SortOrder: 1,
				Path:      "book/part-1",
				Chapters: []ParsedChapter{
					{
						SortOrder: 1,
						Path:      "book/part-1/chapter-1",
						HTML:      "<p>x</p>",
						Scenes: []Scene{
							{SortOrder: 1, Path: "book/part-1/chapter-1/scene-1", LeafText: "x", ContentHash: "abc"},
						},
					},
				},
			},
		},
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Token") != "tok" {
			t.Errorf("missing or wrong X-Internal-Token: %q", r.Header.Get("X-Internal-Token"))
		}
		if r.URL.Path != "/internal/parse" {
			t.Errorf("wrong path: %q", r.URL.Path)
		}
		body, _ := io.ReadAll(r.Body)
		var req map[string]any
		_ = json.Unmarshal(body, &req)
		if req["source_format"] != "html" {
			t.Errorf("expected source_format=html, got %v", req["source_format"])
		}
		if req["content"] != "<h2>Ch 1</h2>" {
			t.Errorf("content not propagated, got %v", req["content"])
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(expected)
	}))
	defer srv.Close()

	client := NewParseClient(srv.URL, "tok")
	tree, err := client.Call(context.Background(), "html", "<h2>Ch 1</h2>", "en", "alice.epub")
	if err != nil {
		t.Fatalf("Call returned error: %v", err)
	}
	if tree.SourceFormat != "html" {
		t.Errorf("wrong source_format: %q", tree.SourceFormat)
	}
	if len(tree.Parts) != 1 || len(tree.Parts[0].Chapters) != 1 || len(tree.Parts[0].Chapters[0].Scenes) != 1 {
		t.Errorf("wrong tree shape: %+v", tree)
	}
	if tree.Parts[0].Chapters[0].Scenes[0].ContentHash != "abc" {
		t.Errorf("content_hash not unmarshalled: %+v", tree.Parts[0].Chapters[0].Scenes[0])
	}
}

func TestParseClientCallPropagatesLanguageAndFilename(t *testing.T) {
	t.Parallel()

	var got map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &got)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"source_format":"plain","walker_path":"headings","parts":[{"sort_order":1,"path":"book/part-1","chapters":[{"sort_order":1,"path":"book/part-1/chapter-1","html":"","scenes":[{"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"x","content_hash":"a"}]}]}]}`))
	}))
	defer srv.Close()

	client := NewParseClient(srv.URL, "tok")
	_, err := client.Call(context.Background(), "plain", "x", "vi", "novel.txt")
	if err != nil {
		t.Fatalf("Call returned error: %v", err)
	}
	if got["language"] != "vi" {
		t.Errorf("language not in request: %+v", got)
	}
	if got["filename"] != "novel.txt" {
		t.Errorf("filename not in request: %+v", got)
	}
}

func TestParseClientCallOmitsEmptyLanguageAndFilename(t *testing.T) {
	t.Parallel()

	var got map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &got)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"source_format":"html","walker_path":"headings","parts":[{"sort_order":1,"path":"book/part-1","chapters":[{"sort_order":1,"path":"book/part-1/chapter-1","html":"","scenes":[{"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"x","content_hash":"a"}]}]}]}`))
	}))
	defer srv.Close()

	client := NewParseClient(srv.URL, "tok")
	_, err := client.Call(context.Background(), "html", "x", "", "")
	if err != nil {
		t.Fatalf("Call returned error: %v", err)
	}
	if _, present := got["language"]; present {
		t.Errorf("language should be omitted when empty, got: %+v", got)
	}
	if _, present := got["filename"]; present {
		t.Errorf("filename should be omitted when empty, got: %+v", got)
	}
}

func TestParseClientCallReturnsErrorOnNon200(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail":"empty content"}`))
	}))
	defer srv.Close()

	client := NewParseClient(srv.URL, "tok")
	_, err := client.Call(context.Background(), "html", "", "", "")
	if err == nil {
		t.Fatal("expected error for non-200 status")
	}
	if !strings.Contains(err.Error(), "422") {
		t.Errorf("error should include status code: %v", err)
	}
}

func TestParseClientCallReturnsErrorOnMalformedResponse(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`not valid json {{{`))
	}))
	defer srv.Close()

	client := NewParseClient(srv.URL, "tok")
	_, err := client.Call(context.Background(), "html", "x", "", "")
	if err == nil {
		t.Fatal("expected error for malformed response")
	}
	if !strings.Contains(err.Error(), "unmarshal") {
		t.Errorf("error should mention unmarshal: %v", err)
	}
}

func TestParseClientCallSendsInternalToken(t *testing.T) {
	t.Parallel()
	// Regression-lock — chat-service D-CHAT-BILLING-01 hit exactly this pattern:
	// a client that didn't send X-Internal-Token got 401'd silently. Mirror the
	// header assertion explicitly.
	tokenReceived := ""
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tokenReceived = r.Header.Get("X-Internal-Token")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"source_format":"html","walker_path":"headings","parts":[{"sort_order":1,"path":"book/part-1","chapters":[{"sort_order":1,"path":"book/part-1/chapter-1","html":"","scenes":[{"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"x","content_hash":"a"}]}]}]}`))
	}))
	defer srv.Close()
	client := NewParseClient(srv.URL, "secret-token")
	_, _ = client.Call(context.Background(), "html", "x", "", "")
	if tokenReceived != "secret-token" {
		t.Errorf("X-Internal-Token not sent, got: %q", tokenReceived)
	}
}
