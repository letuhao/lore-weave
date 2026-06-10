package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/loreweave/glossary-service/internal/config"
)

// The MCP identity middleware (SO-1) must reject any /mcp request without the
// service token BEFORE the MCP handler runs — a regression removing the gate
// would expose the read tools to unauthenticated callers.
func postMCP(t *testing.T, url, token string) int {
	t.Helper()
	req, _ := http.NewRequest(http.MethodPost, url,
		strings.NewReader(`{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}`))
	if token != "" {
		req.Header.Set("X-Internal-Token", token)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()
	return resp.StatusCode
}

func mcpTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	s := &Server{cfg: &config.Config{InternalServiceToken: "right-token"}}
	ts := httptest.NewServer(s.mcpHandler())
	t.Cleanup(ts.Close)
	return ts
}

func TestMCPHandler_RejectsMissingToken(t *testing.T) {
	if code := postMCP(t, mcpTestServer(t).URL, ""); code != http.StatusUnauthorized {
		t.Fatalf("missing token must be 401, got %d", code)
	}
}

func TestMCPHandler_RejectsWrongToken(t *testing.T) {
	if code := postMCP(t, mcpTestServer(t).URL, "wrong-token"); code != http.StatusUnauthorized {
		t.Fatalf("wrong token must be 401, got %d", code)
	}
}
