package loreweave_mcp

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// NewStatelessHandler must wrap the MCP server in the identity middleware, so a
// request with no/invalid internal token is rejected before reaching the MCP
// transport.
func TestNewStatelessHandler_EnforcesIdentity(t *testing.T) {
	srv := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	h := NewStatelessHandler(srv, testToken)

	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	// no X-Internal-Token → must be 401 from the middleware
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401 (identity gate)", rr.Code)
	}
}
