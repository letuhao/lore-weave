package api

// W10-M1 — world-container MCP tools (agent-native worldbuilding).
//
// A "world" groups books + holds the hidden bible book/chapter that anchors
// prose-less lore (the G1 substrate). These tools let an agent CREATE a world and
// discover it, so glossary/KG authoring can then target the world's bible. Worlds
// are OWNER-scoped only (no E0 sharing), so every tool authenticates via the
// envelope identity (mcpUserID) and filters `owner_user_id` — scope=none, no book
// grant. Create/move are Tier-A (direct, reversible: delete the world / move the
// book back) — the analog of knowledge's kg_project_create, NOT a Tier-W
// destructive write, so they don't go through the confirm-token spine.

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// The world/map family is UUID-only: every tool here takes an id and none accepts a name.
// The only suppliers are world_list (world_id) and world_map_list (map_id), and batch 29 of the
// tool deep-dive measured what happens when a refusal does not say so: across 25 live runs the
// model was asked about a world BY NAME, passed the name (or a token out of it) as the id, was
// refused with a bare "world not found", and stopped. It never chained to the supplier once,
// and it never invented a UUID either — it simply had nowhere to go.
//
// So these name the supplier, the way this service's best refusal already does:
// book_chapter_update_meta answers "check the chapter_id (call book_list kind=chapters for
// valid ids)". They stay owner-scoped and identical for "not yours" and "no such row", so
// neither becomes an existence oracle. The leading "not found" is retained deliberately:
// six existing tests assert that exact vocabulary as the uniform-refusal contract, and
// naming the supplier is an ADDITION to that contract rather than a replacement for it.
var (
	errNoSuchWorld = errors.New("world not found — check the world_id (call world_list for valid ids)")
	errNoSuchMap   = errors.New("map not found — check the map_id (call world_map_list for valid ids)")
)

// createWorldCore inserts the world + its hidden bible book + the sort_order-0
// bible chapter inside an open tx, returning the three ids. Shared by the HTTP
// createWorld handler and the world_create MCP tool so the substrate is provisioned
// identically on both paths.
func (s *Server) createWorldCore(ctx context.Context, tx pgx.Tx, ownerID uuid.UUID, name string, description *string) (worldID, bibleBookID, bibleChapterID uuid.UUID, err error) {
	// Normalize once so the HTTP + MCP create paths store description identically:
	// trimmed, and empty/whitespace → NULL (not '').
	var desc *string
	if description != nil {
		if t := strings.TrimSpace(*description); t != "" {
			desc = &t
		}
	}
	if err = tx.QueryRow(ctx, `
INSERT INTO worlds(owner_user_id, name, description)
VALUES($1,$2,$3)
RETURNING id
`, ownerID, name, nullableDescription(desc)).Scan(&worldID); err != nil {
		return
	}
	if err = tx.QueryRow(ctx, `
-- WS-1.1: kind='lore' EXPLICITLY. Without it a world-bible would default to 'novel',
-- while the migration backfilled every PRE-EXISTING bible to 'lore' — so bibles created
-- before and after the deploy would be indistinguishable kinds forever after. The two
-- must land in the same commit.
INSERT INTO books(owner_user_id, title, description, world_id, is_bible, kind)
VALUES($1,$2,$3,$4,true,'lore')
RETURNING id
`, ownerID, name+" — World Bible", "Auto-created world bible (hidden).", worldID).Scan(&bibleBookID); err != nil {
		return
	}
	bibleChapterID, err = provisionBibleChapter(ctx, tx, bibleBookID, ownerID)
	return
}

// ── MCP: world tools ─────────────────────────────────────────────────────────

type worldToolDetail struct {
	WorldID        string  `json:"world_id"`
	Name           string  `json:"name"`
	Description    *string `json:"description"`
	BookCount      int     `json:"book_count"`
	BibleBookID    *string `json:"bible_book_id"`
	BibleChapterID *string `json:"bible_chapter_id"`
}

// scanWorldDetail scans a worldSelectSQL row into a worldToolDetail.
func scanWorldDetail(row pgx.Row) (worldToolDetail, error) {
	var id, owner uuid.UUID
	var name string
	var desc *string
	var createdAt, updatedAt any
	var bookCount int
	var bibleBookID, bibleChapterID *uuid.UUID
	if err := row.Scan(&id, &owner, &name, &desc, &createdAt, &updatedAt, &bookCount, &bibleBookID, &bibleChapterID); err != nil {
		return worldToolDetail{}, err
	}
	d := worldToolDetail{WorldID: id.String(), Name: name, Description: desc, BookCount: bookCount}
	if bibleBookID != nil {
		s := bibleBookID.String()
		d.BibleBookID = &s
	}
	if bibleChapterID != nil {
		s := bibleChapterID.String()
		d.BibleChapterID = &s
	}
	return d, nil
}

type worldCreateIn struct {
	Name        string `json:"name" jsonschema:"the world's name"`
	Description string `json:"description,omitempty" jsonschema:"optional one-line description"`
}
type worldCreateOut struct {
	World worldToolDetail `json:"world"`
}

func (s *Server) toolWorldCreate(ctx context.Context, _ *mcp.CallToolRequest, in worldCreateIn) (*mcp.CallToolResult, worldCreateOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldCreateOut{}, errMissingIdentity
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		return nil, worldCreateOut{}, errors.New("name is required")
	}
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil {
		return nil, worldCreateOut{}, errors.New("failed to initialize quota")
	}
	// K13 (2026-07-23) — idempotency guard, mirroring the N6 chapter guard
	// (mcp_tools_write.go). LIVE-PROBED: two byte-identical `world_create` calls produced
	// TWO worlds, and the agent loop was measured re-issuing an identical Tier-A write
	// across iterations despite an explicit success result. Tier-A auto-commits are
	// bounded only by TIER_A_SAME_OP_CAP (5/turn), so one intent could mint five worlds.
	// Sequential tool execution makes a pre-insert lookup sufficient; a DB unique on
	// (owner,name) is deliberately avoided since a legitimate same-name world is possible.
	{
		var existing uuid.UUID
		if err := s.pool.QueryRow(ctx,
			`SELECT id FROM worlds WHERE owner_user_id=$1 AND lower(name)=lower($2)
			   ORDER BY created_at LIMIT 1`, ownerID, name).Scan(&existing); err == nil {
			if d, derr := scanWorldDetail(s.pool.QueryRow(ctx, worldSelectSQL+`
WHERE w.id=$1 AND w.owner_user_id=$2`, existing, ownerID)); derr == nil {
				return nil, worldCreateOut{World: d}, nil
			}
		}
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, worldCreateOut{}, errors.New("failed to create world")
	}
	defer tx.Rollback(ctx)
	// createWorldCore normalizes (trim + empty→NULL), so pass the raw value through.
	worldID, _, _, err := s.createWorldCore(ctx, tx, ownerID, name, &in.Description)
	if err != nil {
		return nil, worldCreateOut{}, errors.New("failed to create world")
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, worldCreateOut{}, errors.New("failed to commit world")
	}
	d, err := scanWorldDetail(s.pool.QueryRow(ctx, worldSelectSQL+`
WHERE w.id=$1 AND w.owner_user_id=$2`, worldID, ownerID))
	if err != nil {
		return nil, worldCreateOut{}, errors.New("failed to load created world")
	}
	return nil, worldCreateOut{World: d}, nil
}

type worldGetIn struct {
	WorldID string `json:"world_id" jsonschema:"the world to fetch (UUID). NOT a name — if you have the world's NAME, call world_list first and match it to get the id"`
}
type worldGetOut struct {
	World worldToolDetail `json:"world"`
}

func (s *Server) toolWorldGet(ctx context.Context, _ *mcp.CallToolRequest, in worldGetIn) (*mcp.CallToolResult, worldGetOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldGetOut{}, errMissingIdentity
	}
	worldID, err := uuid.Parse(in.WorldID)
	if err != nil {
		return nil, worldGetOut{}, errors.New("world_id must be a UUID")
	}
	d, err := scanWorldDetail(s.pool.QueryRow(ctx, worldSelectSQL+`
WHERE w.id=$1 AND w.owner_user_id=$2`, worldID, ownerID))
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, worldGetOut{}, errNoSuchWorld // owner-scoped: no existence oracle
	}
	if err != nil {
		return nil, worldGetOut{}, errors.New("failed to get world")
	}
	return nil, worldGetOut{World: d}, nil
}

type worldListIn struct {
	Limit  int `json:"limit,omitempty" jsonschema:"max worlds (default 20, max 100)"`
	Offset int `json:"offset,omitempty" jsonschema:"pagination offset"`
}
type worldListOut struct {
	Worlds []worldToolDetail `json:"worlds"`
	// K25 (2026-07-24) — OUT-5: `world_list` capped at `limit` (default 20) but returned
	// ONLY the slice, no total/has_more/is_complete. A caller with 27 worlds asking
	// `limit=20` read the result as "you have 20 worlds" — a silent truncation, the exact
	// shape OUT-5 forbids ("reads to the agent as 'this is everything' when it isn't").
	// Mirror the book_list paging envelope + prose stop-signal via the shared listPage.
	Total    int          `json:"total"`
	Page     pageEnvelope `json:"page"`
	Guidance string       `json:"guidance"`
}

func (s *Server) toolWorldList(ctx context.Context, _ *mcp.CallToolRequest, in worldListIn) (*mcp.CallToolResult, worldListOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldListOut{}, errMissingIdentity
	}
	// Was an inline clamp duplicating clampLimit()'s constants — and it did not
	// agree with it. `limit <= 0 || limit > 100 → 20` silently hands back a
	// SMALLER page than asked for when a client over-asks, while clampLimit caps
	// at mcpMaxLimit. So `world_list` answered limit=500 with 20 rows and
	// `book_list` answered the same request with 100, on the same MCP surface,
	// in the same package. One concept, one name (mcp-tool-io IN-*).
	limit := clampLimit(in.Limit)
	offset := in.Offset
	if offset < 0 {
		offset = 0
	}
	// Owner-scoped total for the paging envelope (OUT-5). One extra cheap COUNT rather than
	// `count(*) OVER()` on worldSelectSQL, whose 9-column scanner is shared by 6 call sites
	// and must not grow a column here.
	var total int
	if err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM worlds WHERE owner_user_id=$1`, ownerID).Scan(&total); err != nil {
		return nil, worldListOut{}, errors.New("failed to list worlds")
	}
	rows, err := s.pool.Query(ctx, worldSelectSQL+`
WHERE w.owner_user_id=$1
ORDER BY w.created_at DESC
LIMIT $2 OFFSET $3`, ownerID, limit, offset)
	if err != nil {
		return nil, worldListOut{}, errors.New("failed to list worlds")
	}
	defer rows.Close()
	worlds := make([]worldToolDetail, 0)
	for rows.Next() {
		d, err := scanWorldDetail(rows)
		if err != nil {
			// #312: skipping the row was worse here than anywhere else -- the pagination
			// envelope below is built from len(worlds), so a dropped row misreports `returned`
			// against a `total` that came from a separate COUNT, and a caller paging on
			// next_offset would step straight over the missing record.
			return nil, worldListOut{}, errors.New("failed to list worlds")
		}
		worlds = append(worlds, d)
	}
	if err := rows.Err(); err != nil {
		return nil, worldListOut{}, errors.New("failed to list worlds")
	}
	env, g := listPage("worlds", len(worlds), total, offset, "world_list")
	return nil, worldListOut{Worlds: worlds, Total: total, Page: env, Guidance: g}, nil
}

type worldMoveBookIn struct {
	// #318: world_id is no longer REQUIRED, because there was no way to undo this tool. It called
	// itself "Reversible" while the reverse operation did not exist on the MCP surface: world_id
	// had to parse as a UUID, so null, omitted and "" were all rejected, and a book moved into a
	// world could never be returned to standalone. REST has had the capability all along
	// (removeBookFromWorld sets world_id=NULL); only the agent surface lacked it. `clear_world`
	// mirrors the `clear_entity` idiom the map tools already use for the same absent-vs-null need.
	WorldID    string `json:"world_id,omitempty" jsonschema:"the world to move the book INTO (UUID; you must own it). Omit and set clear_world=true to remove the book from its world instead."`
	BookID     string `json:"book_id" jsonschema:"the book to move (UUID; you must own it)"`
	ClearWorld bool   `json:"clear_world,omitempty" jsonschema:"true = remove the book from whatever world it is in, making it standalone again (the reverse of a move)"`
}
type worldMoveBookOut struct {
	Moved bool `json:"moved"`
}

func (s *Server) toolWorldMoveBook(ctx context.Context, _ *mcp.CallToolRequest, in worldMoveBookIn) (*mcp.CallToolResult, worldMoveBookOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldMoveBookOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, worldMoveBookOut{}, errors.New("book_id must be a UUID")
	}
	if in.WorldID == "" && !in.ClearWorld {
		return nil, worldMoveBookOut{}, errors.New(
			"provide world_id to move the book into a world, or clear_world=true to remove it from its world")
	}
	if in.WorldID != "" && in.ClearWorld {
		return nil, worldMoveBookOut{}, errors.New(
			"pass either world_id or clear_world=true, not both — they ask for opposite things")
	}
	// target is the new world_id: a real world when moving in, NULL when clearing.
	var target any
	if !in.ClearWorld {
		worldID, perr := uuid.Parse(in.WorldID)
		if perr != nil {
			return nil, worldMoveBookOut{}, errors.New("world_id must be a UUID")
		}
		// The caller must OWN the target world (no existence oracle otherwise). Capture
		// the query error and distinguish it from not-owned: a transient DB failure must
		// surface as a retryable error, not masquerade as "world not found" (which would
		// tell the agent the world is gone → duplicate-create). Mirrors requireWorldOwner.
		var exists bool
		if err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM worlds WHERE id=$1 AND owner_user_id=$2)`, worldID, ownerID).Scan(&exists); err != nil {
			return nil, worldMoveBookOut{}, errors.New("failed to resolve world")
		}
		if !exists {
			return nil, worldMoveBookOut{}, errNoSuchWorld
		}
		target = worldID
	}
	// Move only a real (non-bible) book the caller owns; a hidden bible book can
	// never be re-homed (guards the single-bible invariant).
	//
	// The self-join to `old` returns the book's PREVIOUS world_id from the same statement, which
	// is what the undo hint below replays — no second read, so the value reported as "prior"
	// cannot already be someone else's move. `b.world_id` and `old.world_id` are both qualified:
	// books is joined twice here, and an unqualified reference makes Postgres reject the whole
	// statement, which no Go test can see (the #315 lesson).
	var priorWorld *uuid.UUID
	err = s.pool.QueryRow(ctx, `
-- WS-1.2 · EGRESS (review-impl): the agent-callable world_move_book must also refuse a
-- diary — a world is shareable, so moving a diary into one is a back-door share.
UPDATE books b SET world_id=$1, updated_at=now()
FROM books old
WHERE b.id=old.id AND b.id=$2 AND b.owner_user_id=$3
  AND b.is_bible=false AND b.kind<>'diary' AND b.lifecycle_state!='purge_pending'
RETURNING old.world_id`,
		target, bookID, ownerID).Scan(&priorWorld)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, worldMoveBookOut{}, errors.New("book not found or not movable")
	}
	if err != nil {
		return nil, worldMoveBookOut{}, errors.New("failed to move book")
	}
	// Undo hint (#318): the reverse of a move is a move BACK — or a clear, when the book was
	// standalone before. That second case is why clear_world had to exist at all: replaying
	// world_id alone can never express "it belonged to no world", and omitting it would leave the
	// book in the world this call just put it in.
	undoArgs := map[string]any{"book_id": bookID.String()}
	if priorWorld != nil {
		undoArgs["world_id"] = priorWorld.String()
	} else {
		undoArgs["clear_world"] = true
	}
	return undoResult("world_move_book", undoArgs), worldMoveBookOut{Moved: true}, nil
}

// ── internal: world → bible resolution (for world-native lore authoring) ──────

// getInternalWorldBible resolves a world to its hidden bible book + chapter so
// glossary/knowledge authoring tools can target world-native lore without the
// caller juggling the bible handle. Internal-token gated; owner-scoped by the
// ?user_id param (the trusted caller passes the authoring user). A world not owned
// by that user → 404 (no cross-owner resolution).
func (s *Server) getInternalWorldBible(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	userID, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "user_id query param required")
		return
	}
	var bibleBookID, bibleChapterID *uuid.UUID
	err = s.pool.QueryRow(r.Context(), `
SELECT
  (SELECT bb.id FROM books bb WHERE bb.world_id=$1 AND bb.is_bible=true ORDER BY bb.created_at ASC LIMIT 1),
  (SELECT c.id FROM chapters c
     WHERE c.book_id=(SELECT bb.id FROM books bb WHERE bb.world_id=$1 AND bb.is_bible=true ORDER BY bb.created_at ASC LIMIT 1)
       AND c.sort_order=0 AND c.is_bible=true AND c.lifecycle_state='active'
     ORDER BY c.created_at ASC LIMIT 1)
FROM worlds w WHERE w.id=$1 AND w.owner_user_id=$2`, worldID, userID).Scan(&bibleBookID, &bibleChapterID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "WORLD_NOT_FOUND", "world not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to resolve world bible")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"world_id":         worldID,
		"bible_book_id":    bibleBookID,
		"bible_chapter_id": bibleChapterID,
	})
}

// registerWorldTools registers the W10-M1 world MCP tools on the book MCP server.
func (s *Server) registerWorldTools(srv *mcp.Server) {
	addTool(srv, "world_list",
		"List the worlds you own (worldbuilding containers). Each has a book_count and "+
			"a hidden bible (bible_book_id / bible_chapter_id) that anchors prose-less lore. "+
			"Use to find a world before authoring in it.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, []string{"worlds", "my worlds", "worldbuilding"}),
		s.toolWorldList)

	addTool(srv, "world_get",
		"Fetch one world you own by id: name, description, book_count, and its bible "+
			"handle (bible_book_id / bible_chapter_id) for authoring lore into it.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, []string{"world detail", "open world", "show world"}),
		s.toolWorldGet)

	addTool(srv, "world_create",
		"Create a new WORLD (a prose-less worldbuilding container) with an auto-provisioned "+
			"hidden bible. Direct + reversible (delete it to undo). Returns the world_id + its "+
			"bible_book_id / bible_chapter_id — author characters, places and lore into that "+
			"bible via the glossary/KG tools.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"new world", "create world", "start a world"}),
		s.toolWorldCreate)

	addTool(srv, "world_move_book",
		"Move a book you own INTO a world you own (groups it under that world), or pass "+
			"clear_world=true instead of world_id to take it back OUT and make it standalone. "+
			"Reversible either way — the result's undo_hint replays the book's previous world, or "+
			"clears it if it had none. A hidden bible book cannot be moved.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"move book into world", "group book", "add book to world"}),
		s.toolWorldMoveBook)

	// S-07 §2 — the missing edit/cleanup verbs (REST had them; MCP did not).
	addTool(srv, "world_update",
		"Rename a world you own or change its one-line description. Owner-scoped. "+
			"Reverse: world_update back to the prior name / description.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"rename world", "edit world", "update world description"}),
		s.toolWorldUpdate)

	addTool(srv, "world_delete",
		"Delete a world you own (hard delete — NOT reversible). REFUSED while the world still "+
			"contains member books; move them out (world_move_book to another world) or delete them "+
			"first, so the delete can't silently orphan them. Use to clean up a world you mis-created.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"delete world", "remove world", "clean up world"}),
		s.toolWorldDelete)
}
