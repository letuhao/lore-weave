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
	WorldID string `json:"world_id" jsonschema:"the world to fetch (UUID)"`
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
		return nil, worldGetOut{}, errors.New("world not found") // owner-scoped: no existence oracle
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
}

func (s *Server) toolWorldList(ctx context.Context, _ *mcp.CallToolRequest, in worldListIn) (*mcp.CallToolResult, worldListOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldListOut{}, errMissingIdentity
	}
	limit := in.Limit
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	offset := in.Offset
	if offset < 0 {
		offset = 0
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
		if err == nil {
			worlds = append(worlds, d)
		}
	}
	return nil, worldListOut{Worlds: worlds}, nil
}

type worldMoveBookIn struct {
	WorldID string `json:"world_id" jsonschema:"the world to move the book INTO (UUID; you must own it)"`
	BookID  string `json:"book_id" jsonschema:"the book to move (UUID; you must own it)"`
}
type worldMoveBookOut struct {
	Moved bool `json:"moved"`
}

func (s *Server) toolWorldMoveBook(ctx context.Context, _ *mcp.CallToolRequest, in worldMoveBookIn) (*mcp.CallToolResult, worldMoveBookOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldMoveBookOut{}, errMissingIdentity
	}
	worldID, err := uuid.Parse(in.WorldID)
	if err != nil {
		return nil, worldMoveBookOut{}, errors.New("world_id must be a UUID")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, worldMoveBookOut{}, errors.New("book_id must be a UUID")
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
		return nil, worldMoveBookOut{}, errors.New("world not found")
	}
	// Move only a real (non-bible) book the caller owns; a hidden bible book can
	// never be re-homed (guards the single-bible invariant).
	tag, err := s.pool.Exec(ctx, `
-- WS-1.2 · EGRESS (review-impl): the agent-callable world_move_book must also refuse a
-- diary — a world is shareable, so moving a diary into one is a back-door share.
UPDATE books SET world_id=$1, updated_at=now()
WHERE id=$2 AND owner_user_id=$3 AND is_bible=false AND kind<>'diary' AND lifecycle_state!='purge_pending'`,
		worldID, bookID, ownerID)
	if err != nil {
		return nil, worldMoveBookOut{}, errors.New("failed to move book")
	}
	if tag.RowsAffected() == 0 {
		return nil, worldMoveBookOut{}, errors.New("book not found or not movable")
	}
	return nil, worldMoveBookOut{Moved: true}, nil
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
		"Move a book you own INTO a world you own (groups it under that world). Reversible. "+
			"A hidden bible book cannot be moved.",
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
