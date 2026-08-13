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

	"github.com/google/jsonschema-go/jsonschema"
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
	addToolWithSchema(srv, name, description, meta, nil, handler)
}

// addToolWithSchema is addTool plus an explicit InputSchema — the seam a CLOSED-SET arg needs.
//
// T12-D1: `sort` accepts exactly recent|alpha|chapters|popular, and that set lived only in the
// description prose. W0 #2's rule is that a finite, code-known set MUST be a real JSON-schema
// `enum`, because prose is invisible to a weak model. Worse here than the usual case: an
// unrecognised value does not fail, it falls through `queryPublicBooks`'s `switch` to the
// `default` arm and silently sorts by RECENT — the caller asked for one ordering and got
// another with no signal at all. Measured 2026-08-13: `sort:"bogus"` returned a normal,
// successful, recency-ordered result.
//
// `lwmcp.ClosedSetSchema` is the shared kit helper glossary-service's copy already delegates to,
// with a comment saying that keeping it glossary-only "is precisely how book-service shipped
// four enum-less closed-set args". catalog-service is the next service that never inherited it.
func addToolWithSchema[In, Out any](
	srv *mcp.Server,
	name, description string,
	meta mcp.Meta,
	inputSchema *jsonschema.Schema,
	handler func(context.Context, *mcp.CallToolRequest, In) (*mcp.CallToolResult, Out, error),
) {
	tool := &mcp.Tool{Name: name, Description: description, Meta: meta}
	if inputSchema != nil {
		tool.InputSchema = inputSchema
	}
	lwmcp.MustValidateToolMeta(tool)
	lwmcp.RegisterTool(srv, tool, handler)
}

// catalogSortValues — the ONE place the sort set is written as data. `queryPublicBooks`'s switch
// must stay in lockstep; TestCatalogSortEnumMatchesTheHandler asserts exactly that.
var catalogSortValues = []any{"recent", "alpha", "chapters", "popular"}

// newMCPServer builds the catalog-service MCP server (P5 OD-7 read tools).
func (s *Server) newMCPServer() *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{Name: "catalog", Version: "0.1.0"}, nil)

	// ── Tier R (reads, auto; scope=none — public discovery, no owner guard) ──────
	addToolWithSchema(srv, "catalog_list_public_books",
		"List PUBLIC books in the catalog (anyone's public works). Supports free-text "+
			"query, language/genre/author filters, and sort (recent|alpha|chapters|popular). "+
			"Returns id, title, language, summary, genre tags, chapter & view counts. Public "+
			"content — not scoped to the caller.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, []string{"catalog", "public books", "browse", "discover novels"}),
		lwmcp.ClosedSetSchema[catalogListIn](map[string][]any{"sort": catalogSortValues}),
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
