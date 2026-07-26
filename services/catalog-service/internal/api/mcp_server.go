package api

// S-CATALOG (MCP fan-out, P5 OD-7) — catalog-service's /mcp server. Exposes the
// PUBLIC catalog as read-only MCP tools so an external agent (via the public edge →
// ai-gateway) can discover public books on-behalf-of a user. Built on the shared Go
// kit (sdks/go/loreweave_mcp): identity middleware (X-Internal-Token gate) + the
// C-TOOL `_meta` validator.
//
// OD-7 distinction: catalog content is PUBLIC (the sharing-service public gate), so
// these tools are owner-AGNOSTIC — they return the same public catalog regardless of
// caller. There is no private data here, so NO OD-8 owner gate applies. `_meta.scope`
// is `none` (no kit guard runs); the EDGE classifies catalog_* as read/domain:catalog.
//
// PREFIX (C-GW): catalog-service's gateway provider prefix is `catalog_`.

import (
	"context"
	"net/http"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// addTool registers a tool with its C-TOOL `_meta` (validated at boot — a missing/
// invalid tier or scope panics, a programming error caught at start).
func addTool[In, Out any](
	srv *mcp.Server,
	name, description string,
	meta mcp.Meta,
	handler func(context.Context, *mcp.CallToolRequest, In) (*mcp.CallToolResult, Out, error),
) {
	tool := &mcp.Tool{Name: name, Description: description, Meta: meta}
	lwmcp.MustValidateToolMeta(tool)
	lwmcp.RegisterTool(srv, tool, handler)
}

// newMCPServer builds the catalog-service MCP server (P5 OD-7 read tools).
func (s *Server) newMCPServer() *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{Name: "catalog", Version: "0.1.0"}, nil)

	// ── Tier R (reads, auto; scope=none — public discovery, no owner guard) ──────
	addTool(srv, "catalog_list_public_books",
		"List PUBLIC books in the catalog (anyone's public works). Supports free-text "+
			"query, language/genre/author filters, and sort (recent|alpha|chapters|popular). "+
			"Returns id, title, language, summary, genre tags, chapter & view counts. Public "+
			"content — not scoped to the caller.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, []string{"catalog", "public books", "browse", "discover novels"}),
		s.toolCatalogListPublicBooks)

	addTool(srv, "catalog_get_book",
		"Fetch one PUBLIC book's detail (title, description, language, summary, genre "+
			"tags, chapter count, available translation languages) by id. Returns not-found "+
			"for a non-public or unknown book.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, []string{"public book detail", "open public book"}),
		s.toolCatalogGetBook)

	return srv
}

// mcpHandler wraps the catalog MCP server in the kit identity middleware (X-Internal-
// Token gate) + the stateless StreamableHTTP transport. Mounted at /mcp by Router().
// Degrades to 503 when cfg is nil (bare &Server{} in some unit tests).
func (s *Server) mcpHandler() http.Handler {
	if s.cfg == nil {
		return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			http.Error(w, "mcp not configured", http.StatusServiceUnavailable)
		})
	}
	return lwmcp.NewStatelessHandler(s.newMCPServer(), s.cfg.InternalServiceToken)
}
