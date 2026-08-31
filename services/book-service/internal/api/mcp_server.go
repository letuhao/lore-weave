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
	// errChapterNotInBook is the EXPLICIT error for "the book is accessible, but chapter_id
	// names no active chapter of it" — returned ONLY after the book grant has already passed.
	// It is safe to be specific here (no H13 oracle leak): a caller who cleared the book grant
	// can already enumerate the book's chapters via book_list, so naming a bad chapter_id reveals
	// nothing new — and a uniform "book not accessible" here actively MISLEADS the caller/agent
	// into thinking they lost book access (the observed failure: a mistranscribed chapter_id read
	// as "no book access", so the agent gave up instead of fixing the id).
	errChapterNotInBook = errors.New("no active chapter with that chapter_id in this book — check the chapter_id (call book_list kind=chapters for valid ids)")
	// errSceneNotInBook is the same reasoning one level down (TOOLV2 LOOP #132). The scene read
	// returned errBookNotAccessible for a missing scene_id, on a book the same call had just
	// proven readable — the sixth site of this class found in this loop. A VIEW-granted caller
	// can already enumerate scenes via book_scene_list, so naming a bad scene_id leaks no
	// existence oracle either.
	errSceneNotInBook = errors.New("no active scene with that scene_id in this book — check the scene_id (call book_scene_list for valid ids)")
	// errStructureTargetNotInBook is the same reasoning for the STRUCTURE ops, where the missing
	// thing may be a part or a chapter and the shared mapper cannot tell which (TOOLV2 LOOP
	// #138). It is still not the book: every one of these paths runs after an EDIT grant has
	// passed, so "book not accessible" was false on all of them.
	errStructureTargetNotInBook = errors.New("no active part or chapter with that id in this book — check the id (call book_structure_read for the current structure)")
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

// addToolClosedSet is addTool for a tool with CLOSED-SET args. `enums` maps a dotted
// property path to its legal values, which are attached to the inferred schema as a real
// JSON-Schema `enum`.
//
// Use it whenever a description would otherwise enumerate the values in prose. The set the
// model is validated against must be the set the author wrote down — writing it only in the
// description puts it somewhere the validator can never read (the `panel_id` silent no-op).
// TestEveryEnumeratedClosedSetHasAnEnum reds if a new tool takes the prose route.
func addToolClosedSet[In, Out any](
	srv *mcp.Server,
	name, description string,
	meta mcp.Meta,
	enums map[string][]any,
	handler func(context.Context, *mcp.CallToolRequest, In) (*mcp.CallToolResult, Out, error),
) {
	tool := &mcp.Tool{
		Name: name, Description: description, Meta: meta,
		InputSchema: lwmcp.ClosedSetSchema[In](enums),
	}
	lwmcp.MustValidateToolMeta(tool)
	lwmcp.RegisterTool(srv, tool, handler)
}

// newMCPServer builds the book-service MCP server and registers the S-BOOK
// catalog (§4). Exposed for tests (which assert tier metadata on every tool).
func (s *Server) newMCPServer() *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{Name: "book", Version: "0.1.0"}, nil)

	// ── Tier R (reads, auto; scope=book; View grant) ──────────────────────────
	// book_list — the unified "ls": list REFERENCES only (never bodies), paged, self-terminating
	// (docs/specs/2026-07-22-book-tools-redesign.md Part C/D). `kind` selects the set; default
	// "books" keeps the prior behavior backward-compatible (.books + .total still present).
	// Supersedes book_list_chapters / book_list_revisions / book_scene_list (now legacy).
	//
	// CP-4 brick 2, 2026-08-09: that sentence used to be the ONLY record of the edge. Measured
	// across the frozen 315-tool baseline, 54 tools carry _meta.superseded_by and every one of them
	// is composition_* -> composition_*; not one book_* tool carried a pointer, so book_list -- the
	// declaration this whole effort was founded on -- superseded three tools that named it nowhere a
	// consumer could read. WithSupersededBy has existed in the kit the entire time. The three call
	// sites below now carry it, and mcp_supersession_test.go asserts the edge from THIS registry so
	// a fourth folded-in read cannot be documented in a comment alone.
	addToolClosedSet(srv, "book_list",
		"List REFERENCES only (the 'ls') — never bodies. `kind` selects what: books (default; the "+
			"caller's library), chapters (needs book_id), revisions (needs book_id + chapter_id), or "+
			"scenes (needs book_id). Paged via limit/offset; every result carries page.is_complete + a "+
			"`guidance` line telling you when to STOP paging. To read one item's content use book_read "+
			"(cat); to find one by text use book_search (grep) — don't page a whole list to reach one item.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{
			"books", "my library", "novels", "list chapters", "table of contents", "toc",
			"list revisions", "list scenes", "ls"}),
		// The set selector — same discriminator rule as book_structure_edit.op.
		map[string][]any{"kind": {"books", "chapters", "revisions", "scenes"}},
		s.toolBookListUnified)

	addTool(srv, "book_get",
		"Fetch one book's full detail (title, description, language, summary, "+
			"genre tags, chapter count, lifecycle) by id. "+
			"DEPRECATED: use book_read with book_id alone — the one 'cat' tool for book/chapter/scene.",
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"book detail", "open book", "show book"}), lwmcp.VisibilityLegacy), "book_read"),
		s.toolBookGet)

	addTool(srv, "book_list_chapters",
		"List a book's chapters (title, sort order, language, editorial status, "+
			"draft revision count, lifecycle). Use to see a book's structure. "+
			"DEPRECATED: use book_list with kind=chapters — the one 'ls' tool, paged + self-terminating.",
		// CP-4 brick 2 — the supersession edge is DATA, not the prose above. See book_list.
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"chapters", "table of contents", "toc"}), lwmcp.VisibilityLegacy), "book_list"),
		s.toolBookListChapters)

	addTool(srv, "book_get_chapter",
		"[Saved book] Fetch one chapter by book_id + chapter_id: metadata (title, language, sort "+
			"order, editorial status, published revision) always, plus the chapter's "+
			"full plain-text prose in `body` when include_body=true (use that to READ a "+
			"chapter after story_search locates it; the body can be large). "+
			"DEPRECATED: use book_read with book_id + chapter_id — the one 'cat' tool, same block-paging.",
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"chapter detail", "open chapter", "read chapter text"}), lwmcp.VisibilityLegacy), "book_read"),
		s.toolBookGetChapter)

	addTool(srv, "book_list_revisions",
		"List a chapter's saved draft revisions (id, created_at, author, message, "+
			"body size), newest first. Use before restoring a revision. "+
			"DEPRECATED: use book_list with kind=revisions.",
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"revisions", "history", "versions"}), lwmcp.VisibilityLegacy), "book_list"),
		s.toolBookListRevisions)

	addTool(srv, "book_scene_list",
		"List a book's parsed SCENES (the prose index): scene_id, chapter_id, sort "+
			"order, heading, and source_scene_id (the spec back-link). Filter by "+
			"chapter_id, source_scene_id (resolve a spec scene → its prose index row for "+
			"go-to-prose), or q (heading/prose substring). Read-only: authoring writes go "+
			"to the composition outline, not here. "+
			"DEPRECATED: use book_list with kind=scenes.",
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"scenes", "scene index", "go to prose"}), lwmcp.VisibilityLegacy), "book_list"),
		s.toolBookSceneList)

	addTool(srv, "book_scene_get",
		"Fetch one scene index row by book_id + scene_id: heading, path, prose "+
			"(leaf_text), content hash, and source_scene_id (the composition spec "+
			"back-link). Read-only. "+
			"DEPRECATED: use book_read with book_id + scene_id.",
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"scene detail", "open scene", "read scene"}), lwmcp.VisibilityLegacy), "book_read"),
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
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"grep", "find exact text", "exact phrase", "literal search", "where in the book does it say"}),
		s.toolBookSearch)

	// book_read — the unified "cat": read the full content of ONE addressed item
	// (docs/specs/2026-07-22-book-tools-redesign.md Part C/D). Supersedes book_get +
	// book_get_chapter + book_scene_get (now legacy). Deepest id wins (scene > chapter > book).
	addTool(srv, "book_read",
		"Read the full content of ONE item — the 'cat'. Pass book_id alone for the book's own "+
			"detail; add chapter_id for that chapter's metadata + prose (large bodies are block-paged "+
			"via offset/limit); add scene_id for one scene's prose. The DEEPEST id present wins. To "+
			"FIND an item first, use book_search (grep); to LIST items, use book_list (ls) — don't page "+
			"a whole list to reach one item. Every result carries page.is_complete + a `guidance` line "+
			"telling you exactly when to stop.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{
			"read", "open", "cat", "read chapter", "open chapter", "read the chapter text",
			"open scene", "read scene", "show the book", "read the book"}),
		s.toolBookRead)

	// ── Tier A (auto-write + Undo; scope=book; Edit grant) ────────────────────
	// Every Tier-A result carries _meta.undo_hint = {tool, args} naming the
	// verified reverse op (book uses trash/restore; draft ops → restore_revision).
	// DEPRECATED 2026-07-22 (docs/specs/2026-07-22-book-tools-redesign.md): creating a book is a
	// MANUAL user action (UI "New Book") — the agent works WITHIN an already-opened book. Tagged
	// legacy (CAT-4): endpoint + UI keep working, agent can't discover.
	addTool(srv, "book_create",
		"Create a new (empty) book owned by the caller. Returns the new book_id. "+
			"DEPRECATED: creating a book is a MANUAL UI action — the agent works within an opened book.",
		lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"new book", "add book", "start a novel"}), lwmcp.VisibilityLegacy),
		s.toolBookCreate)

	addTool(srv, "book_update_details",
		"Change a book's own DETAILS — its title, description/blurb/synopsis, summary, "+
			"original_language, genre_tags. This is the ONLY home for a book's description, blurb "+
			"or summary: to change what the book is ABOUT, edit these fields here — NEVER create or "+
			"save a chapter for it (a chapter is story prose, not the book's details). Returns a DIFF "+
			"CARD the human reviews and applies — it does NOT write immediately. Pass ONLY the new "+
			"values you want; you do not need to read the book or supply a version first. Only "+
			"provided fields change.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{
			"rename book", "edit book", "edit book details", "update book details", "book blurb",
			"set genre", "set description", "update description", "change the description",
			"update the book description", "set summary", "update summary", "set blurb",
			"set synopsis", "write the book description"}),
		s.toolBookUpdateMeta)

	addTool(srv, "book_chapter_create",
		"Create a new chapter — a unit of manuscript PROSE (the story text itself) — from plain text "+
			"(or empty). Returns the new chapter_id. For the book's own description / summary / blurb "+
			"(the book's own details, not chapter prose), use book_update_details instead — do NOT create a chapter for it. "+
			"Reverse: trashing a chapter is a manual UI action — tell the user, do not look for a tool.",
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

	// S-02 — manuscript parts (acts / volumes). These let the assistant reorganise
	// the manuscript hierarchy the same way the navigator will: create/rename/reorder/
	// trash an act and move a chapter between acts. All Tier-A, scope=book, EDIT grant.
	// C-merge C4 — part CRUD tools (book_part_*) moved to composition (structure_node kind='part').
	// Only the chapter→part ASSIGNMENT stays here (it writes chapters.structure_node_id).
	// ── Unified manuscript-structure tools (docs/specs/2026-07-22-manuscript-structure-tool.md) ──
	// book_structure_read = the manuscript GRAPH (parts → chapters → unassigned), reference-first + paged.
	// book_structure_edit = ONE write over create/rename/reorder parts + home/reorder chapters. These
	// SUPERSEDE the two standalones below (set_part / reorder → now visibility:legacy, folded into the
	// edit op set) AND close the gap that no MCP tool could create a manuscript part (part CRUD was
	// bearer-only HTTP in composition; the edit tool orchestrates it over the new internal routes).
	addTool(srv, "book_structure_read",
		"Read the manuscript STRUCTURE (its part/chapter graph). With book_id alone: the overview — every "+
			"part with its chapter_count, plus unassigned_count (the whole tree in one call). With "+
			"part_id=<id> (or part_id=\"unassigned\"): that group's chapters, paged — every result carries "+
			"page.is_complete + a `guidance` line telling you when to STOP. Use this to see where chapters "+
			"live before reorganizing with book_structure_edit.",
		lwmcp.WithAmbientBook(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"manuscript structure", "parts overview", "where do chapters live", "book outline"})),
		s.toolBookStructureRead)

	addToolClosedSet(srv, "book_structure_edit",
		"Reorganize the manuscript STRUCTURE. `op` selects the operation: create_part (title) · rename_part "+
			"(part_id, title) · reorder_parts (ordered_part_ids — the full active set, each once) · "+
			"home_chapter (chapter_id + part_id, or part_id=\"unassigned\" to un-home) · reorder_chapters "+
			"(chapter_ids — the complete new order for one language track). Every op is reversible (Undo). "+
			"To DELETE a part, call the SEPARATE tool book_structure_part_archive (soft-delete to "+
			"trash, restorable — its chapters keep their text and fall to Unassigned). This tool "+
			"has no archive op.",
		lwmcp.WithAmbientBook(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{
			"create part", "add act", "add volume", "rename part", "reorder parts",
			"move chapter to act", "put chapter in volume", "home chapter", "reorder chapters", "change reading order",
		})),
		// The dispatch discriminator. A miss here is the whole failure mode, so the legal
		// ops are declared where the VALIDATOR reads them, not only in the prose above.
		map[string][]any{"op": {
			"create_part", "rename_part", "reorder_parts", "home_chapter", "reorder_chapters",
		}},
		s.toolBookStructureEdit)

	// The destructive part-archive is a SEPARATE legacy/lifecycle tool (CAT-2 split — human owns
	// destructive; the auto-write surface above is reversible-only). Soft-delete (trash), restorable.
	addTool(srv, "book_structure_part_archive",
		"Archive (trash) a manuscript part. Its chapters keep their text and fall to Unassigned; restore "+
			"from the trash if needed. Lifecycle op — normally a human action.",
		lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"delete part", "archive part", "trash act", "remove volume"}), lwmcp.VisibilityLegacy),
		s.toolBookStructurePartArchive)

	// C-merge C4 — the chapter→part ASSIGNMENT + reorder engines. FOLDED into book_structure_edit
	// (home_chapter / reorder_chapters ops); kept registered so the Undo hints + any pinned callers
	// still resolve, but visibility:legacy hides them from discovery (one name per concept).
	addTool(srv, "book_chapter_set_part",
		"DEPRECATED: use book_structure_edit op=home_chapter. Move a chapter into / out of / between "+
			"manuscript parts. part_id = the target part, or null to un-home it into the flat manuscript. "+
			"Reverse: book_chapter_set_part with the chapter's prior part_id.",
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"move chapter to act", "put chapter in volume", "home chapter", "un-home chapter"}), lwmcp.VisibilityLegacy), "book_structure_edit"),
		s.toolChapterSetPart)

	// S-07 §3 — reorder was REST-only; this gives the agent reading-order parity with the human.
	addTool(srv, "book_chapter_reorder",
		"DEPRECATED: use book_structure_edit op=reorder_chapters. Set the reading order of a book's "+
			"chapters. Pass chapter_ids as the COMPLETE list of the book's active chapters (one language "+
			"track) in the new order — each exactly once. Reverse: book_chapter_reorder with the prior order.",
		lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"reorder chapters", "reorder manuscript", "change reading order", "move chapter"}), lwmcp.VisibilityLegacy), "book_structure_edit"),
		s.toolChapterReorder)

	addTool(srv, "book_chapter_restore_revision",
		"Restore a chapter's draft to a prior saved revision (a new revision "+
			"snapshots the current draft first, so it is reversible). Reverse: "+
			"book_chapter_restore_revision to the snapshot it created.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"restore revision", "revert chapter", "undo edit"}),
		s.toolChapterRestoreRevision)

	addToolClosedSet(srv, "book_chapter_save_draft",
		"[Saved book] WRITE a chapter's story PROSE (its draft). THE tool for writing/replacing the "+
			"text of a chapter — \"write chapter 1\", \"draft this scene\", \"put down the opening\". Put the "+
			"prose in `body` as plain text (blank line between paragraphs) — do NOT hand-write editor/Tiptap "+
			"JSON. The backend RESOLVES THE CHAPTER'S STATE FOR YOU: you do NOT read the chapter first "+
			"and you do NOT pass a version. Pick the chapter with `chapter` (its NUMBER like \"1\", or its "+
			"TITLE), or omit it when the book has one chapter — NEVER guess a chapter id and NEVER reuse the "+
			"book id or project id as a chapter id. It returns the chapter's new state (id, title, number, "+
			"new version, word_count) so you know exactly what landed. This is NOT for the book's own "+
			"description / summary / blurb (those are the book's DETAILS — use book_update_details; never write "+
			"prose there). Reverse: book_chapter_restore_revision.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"save draft", "edit chapter text", "write chapter prose", "save the chapter draft", "save the scene draft"}),
		map[string][]any{"body_format": {"plain", "markdown", "json"}},
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

	addToolClosedSet(srv, "book_steering_set",
		"Author or replace a book steering rule (the .cursorrules / story-bible the "+
			"agent obeys). Upsert keyed on name: a new name CREATES, an existing name "+
			"FULLY replaces the rule (PUT semantics). The body is injected into every "+
			"matching turn — keep it tight (max 8000 chars, max 20 rules per book). "+
			"inclusion_mode: always|scene_match|manual|auto. Use this for 'write that "+
			"down / always / never' instructions so they survive compaction + sessions. "+
			"Returns the prior row when one was replaced; reverse is in the result's "+
			"undo_hint.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{"add rule", "remember this steering rule", "always do", "never do", "write that down"}),
		map[string][]any{"inclusion_mode": {"always", "scene_match", "manual", "auto"}},
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
