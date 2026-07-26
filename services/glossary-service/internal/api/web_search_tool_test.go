package api

// glossary_web_search — general free-form research tool (D-KG-LF-WEBSEARCH-MCP).
// No DB: the tool is user-scoped and the outward call is stubbed (a fake
// provider-registry /internal/web-search), so this covers identity, validation,
// INV-6 neutralization, non-http(s) URL dropping, and the not-configured path.

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func newWebSearchServer(t *testing.T, providerURL string) *Server {
	t.Helper()
	srv := newExportServer(t, nil) // no pool — web_search touches no glossary table
	srv.cfg.ProviderRegistryURL = providerURL
	srv.cfg.InternalServiceToken = "tok"
	return srv
}

func TestWebSearchTool_NeutralizesAndDropsUnsafeURLs(t *testing.T) {
	// A normal result (whitespace to collapse), a javascript: URL (must be dropped),
	// and a second valid one. answer carries a control char + newline.
	stub := stubProviderRegistry(t, `{"answer":"Dracula is an 1897\ngothic novel.","results":[
		{"title":"Dracula","url":"https://ex.com/dracula","content":"Count   Dracula    of Transylvania","score":0.9},
		{"title":"Evil","url":"javascript:alert(1)","content":"do not return me","score":0.5},
		{"title":"Stoker","url":"https://ex.com/stoker","content":"Bram Stoker, author.","score":0.8}
	]}`)
	srv := newWebSearchServer(t, stub.URL)

	_, out, err := srv.toolWebSearch(ctxWithUser(uuid.New()), nil,
		webSearchToolIn{Query: "dracula novel background", MaxResults: 5})
	if err != nil {
		t.Fatalf("web search: %v", err)
	}
	if len(out.Sources) != 2 {
		t.Fatalf("want 2 safe sources (js: dropped), got %d: %+v", len(out.Sources), out.Sources)
	}
	if out.Sources[0].URL != "https://ex.com/dracula" {
		t.Errorf("source[0] url = %q", out.Sources[0].URL)
	}
	if out.Sources[0].Snippet != "Count Dracula of Transylvania" {
		t.Errorf("snippet not neutralized: %q", out.Sources[0].Snippet)
	}
	for _, s := range out.Sources {
		if s.URL == "javascript:alert(1)" {
			t.Fatal("a javascript: URL leaked to the agent")
		}
	}
	if out.Answer != "Dracula is an 1897 gothic novel." {
		t.Errorf("answer not neutralized: %q", out.Answer)
	}
}

func TestWebSearchTool_RequiresIdentity(t *testing.T) {
	srv := newWebSearchServer(t, "http://unused")
	if _, _, err := srv.toolWebSearch(context.Background(), nil,
		webSearchToolIn{Query: "x"}); err == nil {
		t.Error("missing caller identity must be rejected")
	}
}

func TestWebSearchTool_EmptyQueryRejected(t *testing.T) {
	srv := newWebSearchServer(t, "http://unused")
	if _, _, err := srv.toolWebSearch(ctxWithUser(uuid.New()), nil,
		webSearchToolIn{Query: "   "}); err == nil {
		t.Error("empty query must be rejected")
	}
}

func TestWebSearchTool_NotConfigured(t *testing.T) {
	// No PROVIDER_REGISTRY_URL → a clear "not configured" message, not a 500.
	srv := newWebSearchServer(t, "")
	_, _, err := srv.toolWebSearch(ctxWithUser(uuid.New()), nil,
		webSearchToolIn{Query: "dracula"})
	if err == nil {
		t.Fatal("expected a not-configured error")
	}
	if !strings.Contains(err.Error(), "not configured") {
		t.Errorf("want a not-configured message, got %q", err.Error())
	}
}
