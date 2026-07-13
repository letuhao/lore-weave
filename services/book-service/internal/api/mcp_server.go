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
	lwmcp.RegisterTool(srv, tool, handler)
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
		"[Saved book] Fetch one chapter by book_id + chapter_id: metadata (title, language, sort "+
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

	addTool(srv, "book_scene_list",
		"List a book's parsed SCENES (the prose index): scene_id, chapter_id, sort "+
			"order, heading, and source_scene_id (the spec back-link). Filter by "+
			"chapter_id, source_scene_id (resolve a spec scene → its prose index row for "+
			"go-to-prose), or q (heading/prose substring). Read-only: authoring writes go "+
			"to the composition outline, not here.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"scenes", "scene index", "go to prose"}),
		s.toolBookSceneList)

	addTool(srv, "book_scene_get",
		"Fetch one scene index row by book_id + scene_id: heading, path, prose "+
			"(leaf_text), content hash, and source_scene_id (the composition spec "+
			"back-link). Read-only.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"scene detail", "open scene", "read scene"}),
		s.toolBookSceneGet)

	addTool(srv, "book_steering_list",
		"List this book's steering rules — the per-book story-bible / .cursorrules "+
			"that are injected into every matching chat turn: id, name, body, "+
			"inclusion_mode, match_pattern, enabled, updated_at. Read these before "+
			"authoring so you don't clobber an existing rule (max 20 per book).",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"rules", "style guide", "story bible", "steering", "writing rules"}),
		s.toolBookSteeringList)

	addTool(srv, "book_search",
		"Literal, exact-substring search over the book's manuscript (grep). Args: q "+
			"(the verbatim text; LIKE metacharacters are escaped), surface "+
			"(draft|canon|all, default draft), granularity (chapter|block, default "+
			"chapter), limit/offset. Returns matching chapters/blocks with highlighted "+
			"snippets + has_more. For meaning-alike / semantic passages use story_search "+
			"instead — this one only finds the exact characters you pass.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"grep", "find text", "exact phrase", "literal search", "where in the book does it say"}),
		s.toolBookSearch)

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
		"[Saved book] Save a chapter's PROSE as its draft. Put the chapter text itself in `body` as "+
			"plain prose (blank line between paragraphs) — do NOT hand-write editor/Tiptap JSON. "+
			"REQUIRES base_version (the draft_version you read); a version mismatch returns a conflict "+
			"and stops — no overwrite. Reverse: book_chapter_restore_revision.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"save draft", "edit chapter text", "write chapter"}),
		s.toolChapterSaveDraft)

	// WS-0.4 — publish-independent KG indexing. Indexing is NOT publishing: a chapter
	// can be added to the knowledge graph while remaining a draft forever (and
	// kind='diary' books never publish at all). Never fires on autosave.
	addTool(srv, "book_index_chapter",
		"[Saved book] Add a chapter to the knowledge graph ('index it' / 'remember this "+
			"chapter'). Works on a DRAFT chapter — it does NOT publish, and publishing is "+
			"not required. Pins the current draft as the revision the knowledge layer "+
			"reflects, re-parses its scenes, and enqueues extraction. Re-indexing an "+
			"unchanged draft is a NO-OP and costs nothing (reused_revision=true). Refuses "+
			"if the chapter is kg_exclude'd. COSTS MONEY: this enqueues an LLM extraction "+
			"on the user's own model. The graph is NOT updated when this call returns — a "+
			"background job does the work. There is NO cheap undo (removing the chapter "+
			"again via book_chapter_set_kg_exclude also destroys anything a previous "+
			"publish contributed), so do not index speculatively.",
		// review-impl P2: WithPaid + WithAsync. The tool enqueues a real Pass-2 LLM
		// extraction on the user's BYOK model (paid), and the graph is only updated by a
		// background drain (async). Without these the workflow step-runner treats it as a
		// free, synchronous write and an agent will happily call it in a loop.
		lwmcp.WithAsync(lwmcp.WithPaid(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{
			"index chapter", "add to knowledge", "add chapter to knowledge graph",
			"remember this chapter", "extract knowledge from this chapter",
		}))),
		s.toolBookIndexChapter)

	addTool(srv, "book_chapter_set_kg_exclude",
		"[Saved book] Include or exclude a chapter from the knowledge graph. "+
			"kg_exclude=true KEEPS IT OUT and RETRACTS anything already extracted from it "+
			"(facts and passages are removed) — use for 'forget this chapter' / 'don't "+
			"remember this'. kg_exclude=false merely re-allows indexing; it does NOT "+
			"re-index by itself (call book_index_chapter for that).",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{
			"exclude from knowledge graph", "forget this chapter", "don't remember this chapter",
			"remove chapter from knowledge", "un-index chapter",
		}),
		s.toolBookSetKGExclude)

	addTool(srv, "book_steering_set",
		"Author or replace a book steering rule (the .cursorrules / story-bible the "+
			"agent obeys). Upsert keyed on name: a new name CREATES, an existing name "+
			"FULLY replaces the rule (PUT semantics). The body is injected into every "+
			"matching turn — keep it tight (max 8000 chars, max 20 rules per book). "+
			"inclusion_mode: always|scene_match|manual|auto. Use this for 'write that "+
			"down / always / never' instructions so they survive compaction + sessions. "+
			"Returns the prior row when one was replaced; reverse is in the result's "+
			"undo_hint.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"add rule", "remember this steering rule", "always do", "never do", "write that down"}),
		s.toolBookSteeringSet)

	addTool(srv, "book_steering_delete",
		"Delete a book steering rule by name (or id). Returns the deleted row; the "+
			"result's undo_hint restores it. An unknown name/id is an error, never a "+
			"silent no-op.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"remove rule", "forget rule", "delete steering"}),
		s.toolBookSteeringDelete)

	// ── Tier W (confirm via token; scope=book; the propose tool MINTS only) ────
	// The propose tools below MINT a confirm token (no write) + return a confirm
	// card. The ONLY write path is /v1/book/actions/confirm (token-gated). See
	// mcp_actions.go.
	s.registerActionProposeTools(srv)

	// ── W10-M1 world-container tools (Tier-R reads + Tier-A create/move) ──
	s.registerWorldTools(srv)

	// ── W10-M2 world-map tools (Tier-R reads + Tier-A create/marker/region) ──
	s.registerMapTools(srv)

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
