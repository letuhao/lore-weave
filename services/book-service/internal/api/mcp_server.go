package api

// S-BOOK (MCP fan-out) — book-service's /mcp server. Exposes book/chapter
// capabilities as MCP tools so a chat agent can do everything the book UI can.
// Built on the shared Go kit (sdks/go/loreweave_mcp): identity middleware
// (X-Internal-Token gate + envelope→ctx), the C-TOOL `_meta` validator
// (tier+scope required on every tool), and the Tier-W confirm-token spine.
//
// Tiers (C-TOOL): R = read (auto), A = auto-write + Undo (undo_hint in result),
// W = confirm via token (the propose tool MINTS; the only write path is the
// token-gated /v1/book/actions/confirm route).
//
// PREFIX DECISION (C-GW): book-service's gateway provider prefix is `book_`. The
// gateway DROPS any tool whose name does not start with `book_`. The §4 catalog
// lists chapter tools as `chapter_*`; to pass prefix enforcement they are
// registered here as `book_chapter_*` (and book tools as `book_*`). The §4
// "descriptor" values (book.publish / book.delete) are unchanged — descriptors
// are not gateway-prefixed.

import (
	"context"
	"errors"
	"net/http"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// uniform caller-visible errors (H13 — no existence oracle). Shared by the guard
// and every tool handler.
var (
	errMissingIdentity      = errors.New("missing caller identity")
	errBookNotAccessible    = errors.New("book not accessible")
	errBookCheckUnavailable = errors.New("book ownership check unavailable, try again")
)

// mcpUserID lifts the caller's user id from the kit identity context (set by
// lwmcp.IdentityMiddleware from X-User-Id). ok=false → the handler MUST refuse
// (never proceed with uuid.Nil). Identity NEVER comes from a tool arg (SEC-1).
func mcpUserID(ctx context.Context) (uuid.UUID, bool) {
	return lwmcp.UserIDFromCtx(ctx)
}

// addTool registers a tool, attaching its C-TOOL `_meta` (tier+scope, plus
// optional undo_hint/synonyms) and validating it at boot — a tool missing/with
// an invalid tier or scope panics here (programming error, fail at start).
func addTool[In, Out any](
	srv *mcp.Server,
	name, description string,
	meta mcp.Meta,
	handler func(context.Context, *mcp.CallToolRequest, In) (*mcp.CallToolResult, Out, error),
) {
	tool := &mcp.Tool{Name: name, Description: description, Meta: meta}
	lwmcp.MustValidateToolMeta(tool)
	mcp.AddTool(srv, tool, handler)
}

// newMCPServer builds the book-service MCP server and registers the S-BOOK
// catalog (§4). Exposed for tests (which assert tier metadata on every tool).
func (s *Server) newMCPServer() *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{Name: "book", Version: "0.1.0"}, nil)

	// ── Tier R (reads, auto; scope=book; View grant) ──────────────────────────
	addTool(srv, "book_list",
		"List the caller's books (owned + shared). Returns id, title, language, "+
			"chapter count, and lifecycle. Use to find a book before acting on it.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"books", "my library", "novels"}),
		s.toolBookList)

	addTool(srv, "book_get",
		"Fetch one book's full detail (title, description, language, summary, "+
			"genre tags, chapter count, lifecycle) by id.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"book detail", "open book", "show book"}),
		s.toolBookGet)

	addTool(srv, "book_list_chapters",
		"List a book's chapters (title, sort order, language, editorial status, "+
			"draft revision count, lifecycle). Use to see a book's structure.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"chapters", "table of contents", "toc"}),
		s.toolBookListChapters)

	addTool(srv, "book_get_chapter",
		"Fetch one chapter by book_id + chapter_id: metadata (title, language, sort "+
			"order, editorial status, published revision) always, plus the chapter's "+
			"full plain-text prose in `body` when include_body=true (use that to READ a "+
			"chapter after story_search locates it; the body can be large).",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"chapter detail", "open chapter", "read chapter text"}),
		s.toolBookGetChapter)

	addTool(srv, "book_list_revisions",
		"List a chapter's saved draft revisions (id, created_at, author, message, "+
			"body size), newest first. Use before restoring a revision.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"revisions", "history", "versions"}),
		s.toolBookListRevisions)

	// ── Tier A (auto-write + Undo; scope=book; Edit grant) ────────────────────
	// Every Tier-A result carries _meta.undo_hint = {tool, args} naming the
	// verified reverse op (book uses trash/restore; draft ops → restore_revision).
	addTool(srv, "book_create",
		"Create a new (empty) book owned by the caller. Returns the new book_id. "+
			"Reverse: book_delete (trash).",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"new book", "add book", "start a novel"}),
		s.toolBookCreate)

	addTool(srv, "book_update_meta",
		"Update a book's metadata (title, description, original_language, summary, "+
			"genre_tags). Only provided fields change. Reverse: book_update_meta with "+
			"the prior values.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"rename book", "edit book", "set genre"}),
		s.toolBookUpdateMeta)

	addTool(srv, "book_chapter_create",
		"Create a new chapter in a book from plain text (or empty). Returns the "+
			"new chapter_id. Reverse: book_chapter_delete (trash).",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"new chapter", "add chapter"}),
		s.toolChapterCreate)

	addTool(srv, "book_chapter_bulk_create",
		"Create many plain-text chapters in one call (folder/large import). "+
			"Idempotent on original_filename. Returns created/skipped counts + new ids.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"bulk chapters", "import chapters", "add many chapters"}),
		s.toolChapterBulkCreate)

	addTool(srv, "book_chapter_update_meta",
		"Update a chapter's metadata (title, sort_order, original_language). Only "+
			"provided fields change. Reverse: book_chapter_update_meta with prior values.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"rename chapter", "reorder chapter"}),
		s.toolChapterUpdateMeta)

	addTool(srv, "book_chapter_restore_revision",
		"Restore a chapter's draft to a prior saved revision (a new revision "+
			"snapshots the current draft first, so it is reversible). Reverse: "+
			"book_chapter_restore_revision to the snapshot it created.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"restore revision", "revert chapter", "undo edit"}),
		s.toolChapterRestoreRevision)

	addTool(srv, "book_chapter_save_draft",
		"Save a chapter draft body (Tiptap JSON). REQUIRES base_version (the "+
			"draft_version you read); a version mismatch returns a conflict and "+
			"stops — no overwrite. Reverse: book_chapter_restore_revision.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"save draft", "edit chapter text", "write chapter"}),
		s.toolChapterSaveDraft)

	// ── Tier W (confirm via token; scope=book; the propose tool MINTS only) ────
	// The propose tools below MINT a confirm token (no write) + return a confirm
	// card. The ONLY write path is /v1/book/actions/confirm (token-gated). See
	// mcp_actions.go.
	s.registerActionProposeTools(srv)

	return srv
}

// mcpHandler builds the book-service MCP server wrapped in the kit identity
// middleware (X-Internal-Token gate + X-User-Id/Session/Trace → ctx, SEC-1) and
// the stateless StreamableHTTP transport (INV-4). Mounted at /mcp by Router().
//
// When cfg is nil (a bare &Server{} in some unit tests that only exercise other
// routes) the handler degrades to a 503 stub rather than panicking — production
// always has a non-empty InternalServiceToken (config.Load enforces it), so the
// identity gate is never actually disabled in a real deployment.
func (s *Server) mcpHandler() http.Handler {
	if s.cfg == nil {
		return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			http.Error(w, "mcp not configured", http.StatusServiceUnavailable)
		})
	}
	return lwmcp.NewStatelessHandler(s.newMCPServer(), s.cfg.InternalServiceToken)
}
