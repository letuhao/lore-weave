package loreweave_mcp

import (
	"net/http"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// NewStatelessHandler wraps an MCP server in the proven stateless StreamableHTTP
// transport (Stateless:true, JSONResponse:true — INV-4: a per-call stateless
// downstream connection, never shared across users) and the kit identity
// middleware (SEC-1). Mount the result at /mcp.
//
// Stateless mode means each request carries its own envelope (validated by
// IdentityMiddleware) and no session is retained — the right shape for a server
// the federation gateway connects to per call on behalf of many users.
func NewStatelessHandler(srv *mcp.Server, internalToken string) http.Handler {
	streamable := mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true},
	)
	return IdentityMiddleware(internalToken, streamable)
}
