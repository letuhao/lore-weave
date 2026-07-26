package api

// C-merge C4 — the surviving manuscript-parts MCP tool. Part CRUD moved to composition
// (structure_node kind='part'); book-service keeps only book_chapter_set_part, which (re)homes a
// chapter into a manuscript part by writing chapters.structure_node_id (or NULL to un-home). Tier-A
// (auto-write + Undo), EDIT-gated, identity from the envelope.

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
	case errors.Is(err, errChapterNotFound):
		return errBookNotAccessible // H13: no existence oracle — same uniform not-accessible
	default:
		return errors.New("failed to move chapter")
	}
}

// ── book_chapter_set_part ────────────────────────────────────────────────────

type chapterSetPartIn struct {
	BookID    string  `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string  `json:"chapter_id" jsonschema:"the chapter to (re)home (UUID)"`
	PartID    *string `json:"part_id" jsonschema:"the target part (a structure_node UUID), or null to un-home into the flat manuscript"`
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
	// §4.5 (agent half of the no-silent-seam fix, H2) — a non-null target must be a LIVE kind='part' of
	// THIS book. The HTTP path validates via the bearer-forwarded /parts; the MCP ctx has a user_id but
	// no user bearer, so we validate via composition's INTERNAL parts route (X-Internal-Token + user_id).
	// Without this an agent could home a chapter onto an arc id / foreign-book part and it would silently
	// read as Unassigned — the exact "no check, silent error, for agents too" this closes. Un-home (null)
	// skips the check.
	if target != nil {
		valid, reachable := s.validatePartTargetInternal(ctx, bookID, userID, *target)
		if !reachable {
			return nil, chapterSetPartOut{}, errors.New("could not verify the target part — composition is unavailable; try again shortly")
		}
		if !valid {
			return nil, chapterSetPartOut{}, errors.New("target part is not a live part of this book")
		}
	}
	// Capture the prior grouping for the undo hint (before the move).
	var priorPart *uuid.UUID
	_ = s.pool.QueryRow(ctx, `SELECT structure_node_id FROM chapters WHERE id=$1 AND book_id=$2`, chID, bookID).Scan(&priorPart)

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
