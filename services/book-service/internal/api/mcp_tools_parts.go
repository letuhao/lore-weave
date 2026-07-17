package api

// S-02 (MCP-first / agent parity) — the manuscript-parts write tools. Each is a
// Tier-A (auto-write + Undo) tool scoped to a book, requiring the EDIT grant. They
// resolve identity from the envelope (SEC-1), verify the grant via mcpRequireGrant,
// and then call the SAME store methods the REST routes use (storeCreatePart, …) so
// the two surfaces can never drift. Every result carries _meta.undo_hint = {tool,
// args} naming the verified reverse op (C-ACTIVITY).
//
// Why these exist: without them the parts layer is human-operable through the GUI
// only. With them the Studio ASSISTANT can reorganise the manuscript — "make an act
// 'Rising Action' and move chapters 3-6 into it" — which is the feature's first
// genuinely-usable surface, independent of the drag-and-drop navigator.

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// mcpMapPartErr collapses the store sentinels to the MCP surface's uniform errors.
func mcpMapPartErr(err error) error {
	switch {
	case errors.Is(err, errPartNotFound), errors.Is(err, errChapterNotFound):
		return errBookNotAccessible // H13: no existence oracle — same uniform not-accessible
	case errors.Is(err, errPartNotInBook):
		return errPartNotInBook // a validation truth the agent should see verbatim
	case errors.Is(err, errReorderMismatch):
		return errReorderMismatch
	default:
		return errors.New("failed to write part")
	}
}

// ── book_part_create ─────────────────────────────────────────────────────────

type partCreateIn struct {
	BookID string `json:"book_id" jsonschema:"the book to add the act to (UUID)"`
	Title  string `json:"title,omitempty" jsonschema:"the act/volume title (optional; may be blank)"`
}
type partCreateOut struct {
	PartID    string `json:"part_id"`
	SortOrder int    `json:"sort_order"`
}

func (s *Server) toolPartCreate(ctx context.Context, _ *mcp.CallToolRequest, in partCreateIn) (*mcp.CallToolResult, partCreateOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, partCreateOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, partCreateOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, partCreateOut{}, mcpOwnershipError(err)
	}
	// Mirror REST createPart + the sibling create tools (toolChapterCreate): you cannot
	// add an act to a trashed book. Keeps the two surfaces in lockstep.
	var lifecycle string
	if err := s.pool.QueryRow(ctx, `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); err != nil {
		return nil, partCreateOut{}, errBookNotAccessible
	}
	if lifecycle != "active" {
		return nil, partCreateOut{}, errors.New("book is not in an editable state")
	}
	p, err := s.storeCreatePart(ctx, bookID, in.Title)
	if err != nil {
		return nil, partCreateOut{}, mcpMapPartErr(err)
	}
	res := undoResult("book_part_archive", map[string]any{"book_id": bookID.String(), "part_id": p.PartID.String()})
	return res, partCreateOut{PartID: p.PartID.String(), SortOrder: p.SortOrder}, nil
}

// ── book_part_rename ─────────────────────────────────────────────────────────

type partRenameIn struct {
	BookID string `json:"book_id" jsonschema:"the book the act belongs to (UUID)"`
	PartID string `json:"part_id" jsonschema:"the act to rename (UUID)"`
	Title  string `json:"title" jsonschema:"the new title (may be blank to clear it)"`
}
type partRenameOut struct {
	PartID string `json:"part_id"`
}

func (s *Server) toolPartRename(ctx context.Context, _ *mcp.CallToolRequest, in partRenameIn) (*mcp.CallToolResult, partRenameOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, partRenameOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, partRenameOut{}, errors.New("book_id must be a UUID")
	}
	partID, err := uuid.Parse(in.PartID)
	if err != nil {
		return nil, partRenameOut{}, errors.New("part_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, partRenameOut{}, mcpOwnershipError(err)
	}
	// Capture the prior title for the undo hint (before the update).
	var priorTitle *string
	_ = s.pool.QueryRow(ctx,
		`SELECT title FROM parts WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`, partID, bookID).Scan(&priorTitle)

	p, err := s.storeRenamePart(ctx, bookID, partID, in.Title)
	if err != nil {
		return nil, partRenameOut{}, mcpMapPartErr(err)
	}
	res := undoResult("book_part_rename", map[string]any{
		"book_id": bookID.String(), "part_id": p.PartID.String(), "title": derefStr(priorTitle),
	})
	return res, partRenameOut{PartID: p.PartID.String()}, nil
}

// ── book_part_reorder ────────────────────────────────────────────────────────

type partReorderIn struct {
	BookID     string   `json:"book_id" jsonschema:"the book whose acts to reorder (UUID)"`
	OrderedIDs []string `json:"ordered_ids" jsonschema:"every active act id of the book, in the new order (a permutation of the current set)"`
}
type partReorderOut struct {
	PartIDs []string `json:"part_ids"`
}

func (s *Server) toolPartReorder(ctx context.Context, _ *mcp.CallToolRequest, in partReorderIn) (*mcp.CallToolResult, partReorderOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, partReorderOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, partReorderOut{}, errors.New("book_id must be a UUID")
	}
	ids := make([]uuid.UUID, 0, len(in.OrderedIDs))
	for _, s := range in.OrderedIDs {
		id, err := uuid.Parse(s)
		if err != nil {
			return nil, partReorderOut{}, errors.New("ordered_ids must all be UUIDs")
		}
		ids = append(ids, id)
	}
	if msg := validateOrderedIDs(ids); msg != "" {
		return nil, partReorderOut{}, errors.New(msg)
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, partReorderOut{}, mcpOwnershipError(err)
	}
	// Capture the prior order for the undo hint (before the rewrite).
	prior := s.activePartOrder(ctx, bookID)

	out, err := s.storeReorderParts(ctx, bookID, ids)
	if err != nil {
		return nil, partReorderOut{}, mcpMapPartErr(err)
	}
	partIDs := make([]string, len(out))
	for i, p := range out {
		partIDs[i] = p.PartID.String()
	}
	res := undoResult("book_part_reorder", map[string]any{"book_id": bookID.String(), "ordered_ids": prior})
	return res, partReorderOut{PartIDs: partIDs}, nil
}

// activePartOrder returns the book's active part ids in current sort order (for the
// reorder undo hint). Best-effort — an empty slice on error just yields a weaker hint.
func (s *Server) activePartOrder(ctx context.Context, bookID uuid.UUID) []string {
	rows, err := s.pool.Query(ctx,
		`SELECT id FROM parts WHERE book_id=$1 AND lifecycle_state='active' ORDER BY sort_order, id`, bookID)
	if err != nil {
		return []string{}
	}
	defer rows.Close()
	out := []string{}
	for rows.Next() {
		var id uuid.UUID
		if rows.Scan(&id) == nil {
			out = append(out, id.String())
		}
	}
	return out
}

// ── book_part_archive ────────────────────────────────────────────────────────

type partArchiveIn struct {
	BookID string `json:"book_id" jsonschema:"the book the act belongs to (UUID)"`
	PartID string `json:"part_id" jsonschema:"the act to trash (UUID)"`
}
type partArchiveOut struct {
	PartID string `json:"part_id"`
}

func (s *Server) toolPartArchive(ctx context.Context, _ *mcp.CallToolRequest, in partArchiveIn) (*mcp.CallToolResult, partArchiveOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, partArchiveOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, partArchiveOut{}, errors.New("book_id must be a UUID")
	}
	partID, err := uuid.Parse(in.PartID)
	if err != nil {
		return nil, partArchiveOut{}, errors.New("part_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, partArchiveOut{}, mcpOwnershipError(err)
	}
	if err := s.storeArchivePart(ctx, bookID, partID); err != nil {
		return nil, partArchiveOut{}, mcpMapPartErr(err)
	}
	// Reverse: restore. NOTE the chapters this un-homed are NOT re-homed by restore
	// (sealed) — the reverse restores the ACT, not the memberships.
	res := undoResult("book_part_restore", map[string]any{"book_id": bookID.String(), "part_id": partID.String()})
	return res, partArchiveOut{PartID: partID.String()}, nil
}

// ── book_part_restore ────────────────────────────────────────────────────────

type partRestoreIn struct {
	BookID string `json:"book_id" jsonschema:"the book the act belongs to (UUID)"`
	PartID string `json:"part_id" jsonschema:"the trashed act to restore (UUID)"`
}
type partRestoreOut struct {
	PartID string `json:"part_id"`
}

func (s *Server) toolPartRestore(ctx context.Context, _ *mcp.CallToolRequest, in partRestoreIn) (*mcp.CallToolResult, partRestoreOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, partRestoreOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, partRestoreOut{}, errors.New("book_id must be a UUID")
	}
	partID, err := uuid.Parse(in.PartID)
	if err != nil {
		return nil, partRestoreOut{}, errors.New("part_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, partRestoreOut{}, mcpOwnershipError(err)
	}
	if _, err := s.storeRestorePart(ctx, bookID, partID); err != nil {
		return nil, partRestoreOut{}, mcpMapPartErr(err)
	}
	res := undoResult("book_part_archive", map[string]any{"book_id": bookID.String(), "part_id": partID.String()})
	return res, partRestoreOut{PartID: partID.String()}, nil
}

// ── book_chapter_set_part ────────────────────────────────────────────────────

type chapterSetPartIn struct {
	BookID    string  `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string  `json:"chapter_id" jsonschema:"the chapter to (re)home (UUID)"`
	PartID    *string `json:"part_id" jsonschema:"the target act (UUID), or null to un-home into the flat manuscript"`
}
type chapterSetPartOut struct {
	ChapterID string  `json:"chapter_id"`
	PartID    *string `json:"part_id"`
}

func (s *Server) toolChapterSetPart(ctx context.Context, _ *mcp.CallToolRequest, in chapterSetPartIn) (*mcp.CallToolResult, chapterSetPartOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, chapterSetPartOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, chapterSetPartOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, chapterSetPartOut{}, errors.New("chapter_id must be a UUID")
	}
	var target *uuid.UUID
	if in.PartID != nil {
		id, err := uuid.Parse(*in.PartID)
		if err != nil {
			return nil, chapterSetPartOut{}, errors.New("part_id must be a UUID or null")
		}
		target = &id
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, chapterSetPartOut{}, mcpOwnershipError(err)
	}
	// Capture the prior part_id for the undo hint (before the move).
	var priorPart *uuid.UUID
	_ = s.pool.QueryRow(ctx, `SELECT part_id FROM chapters WHERE id=$1 AND book_id=$2`, chID, bookID).Scan(&priorPart)

	if err := s.moveChapterToPart(ctx, bookID, chID, target); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, chapterSetPartOut{}, errBookNotAccessible
		}
		return nil, chapterSetPartOut{}, mcpMapPartErr(err)
	}
	var priorArg any
	if priorPart != nil {
		priorArg = priorPart.String()
	} else {
		priorArg = nil // reverse un-homes
	}
	res := undoResult("book_chapter_set_part", map[string]any{
		"book_id": bookID.String(), "chapter_id": chID.String(), "part_id": priorArg,
	})
	var outPart *string
	if target != nil {
		v := target.String()
		outPart = &v
	}
	return res, chapterSetPartOut{ChapterID: chID.String(), PartID: outPart}, nil
}
