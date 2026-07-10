package api

// S-BOOK Tier-R (read) MCP tools for the SCENE index (22-A4 / SC9).
//
// `scenes` is a derived index (SC1) and authoring writes composition (SC5), so
// the MCP surface is READ-only — there is no book_scene_create/update/delete (they
// dropped out of SC9 with the API amendment; writes go to composition's
// outline_node tools). Each tool resolves the caller from the envelope (never a
// tool arg, SEC-1), VIEW-gates via mcpRequireGrant, and returns structured output.
//
// book_scene_list carries a `source_scene_id` filter (28 AN-5b): the agent's
// go-to-prose step resolves a spec scene (outline_node.id) → the index row that
// back-links to it (scenes.source_scene_id = that id), giving it the chapter +
// scene identity to open the prose. 28-AN-C1 reds without this arg.

import (
	"context"
	"errors"
	"fmt"
	"strconv"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// ── book_scene_list ───────────────────────────────────────────────────────────

type sceneListIn struct {
	BookID        string `json:"book_id" jsonschema:"the book whose scenes to list (UUID)"`
	ChapterID     string `json:"chapter_id,omitempty" jsonschema:"filter to one chapter (UUID)"`
	SourceSceneID string `json:"source_scene_id,omitempty" jsonschema:"filter to the index row that back-links to this composition spec scene id (outline_node.id, UUID) — the go-to-prose join key"`
	Q             string `json:"q,omitempty" jsonschema:"case-insensitive substring over the scene heading + prose"`
	Limit         int    `json:"limit,omitempty" jsonschema:"max scenes to return (default 20, max 100)"`
	Offset        int    `json:"offset,omitempty" jsonschema:"pagination offset"`
}
type sceneSummary struct {
	SceneID        string  `json:"scene_id"`
	BookID         *string `json:"book_id"`
	ChapterID      string  `json:"chapter_id"`
	SortOrder      int     `json:"sort_order"`
	Title          string  `json:"title"`
	Path           string  `json:"path"`
	SourceSceneID  *string `json:"source_scene_id"`
	ContentHash    string  `json:"content_hash"`
	ParseVersion   int     `json:"parse_version"`
	LifecycleState string  `json:"lifecycle_state"`
}
type sceneListOut struct {
	Scenes []sceneSummary `json:"scenes"`
	Total  int            `json:"total"`
}

func (s *Server) toolBookSceneList(ctx context.Context, _ *mcp.CallToolRequest, in sceneListIn) (*mcp.CallToolResult, sceneListOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, sceneListOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, sceneListOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, sceneListOut{}, mcpOwnershipError(err)
	}

	args := []any{bookID}
	where := `book_id=$1 AND lifecycle_state='active'`
	if in.ChapterID != "" {
		cid, err := uuid.Parse(in.ChapterID)
		if err != nil {
			return nil, sceneListOut{}, errors.New("chapter_id must be a UUID")
		}
		args = append(args, cid)
		where += " AND chapter_id=$2"
	}
	if in.SourceSceneID != "" {
		sid, err := uuid.Parse(in.SourceSceneID)
		if err != nil {
			return nil, sceneListOut{}, errors.New("source_scene_id must be a UUID")
		}
		args = append(args, sid)
		where += fmt.Sprintf(" AND source_scene_id=$%d", len(args))
	}
	if in.Q != "" {
		if len([]rune(in.Q)) > maxSearchQueryRunes {
			return nil, sceneListOut{}, errors.New("query too long")
		}
		args = append(args, escapeLikePattern(in.Q))
		where += fmt.Sprintf(" AND (title ILIKE $%d OR leaf_text ILIKE $%d)", len(args), len(args))
	}

	limit := clampLimit(in.Limit)
	offset := in.Offset
	if offset < 0 {
		offset = 0
	}
	countArgs := append([]any{}, args...)
	args = append(args, limit, offset)
	rows, err := s.pool.Query(ctx,
		`SELECT id, book_id, chapter_id, sort_order, title, path, source_scene_id, content_hash, parse_version, lifecycle_state
FROM scenes WHERE `+where+` ORDER BY chapter_id, sort_order LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		return nil, sceneListOut{}, errors.New("failed to list scenes")
	}
	defer rows.Close()
	out := sceneListOut{Scenes: []sceneSummary{}}
	for rows.Next() {
		var sc sceneSummary
		var id, chID uuid.UUID
		var bookIDScan, sourceSceneID *uuid.UUID
		if err := rows.Scan(&id, &bookIDScan, &chID, &sc.SortOrder, &sc.Title, &sc.Path, &sourceSceneID, &sc.ContentHash, &sc.ParseVersion, &sc.LifecycleState); err == nil {
			sc.SceneID = id.String()
			sc.ChapterID = chID.String()
			sc.BookID = uuidPtrToStr(bookIDScan)
			sc.SourceSceneID = uuidPtrToStr(sourceSceneID)
			out.Scenes = append(out.Scenes, sc)
		}
	}
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM scenes WHERE `+where, countArgs...).Scan(&out.Total)
	return nil, out, nil
}

// ── book_scene_get ────────────────────────────────────────────────────────────

type sceneGetIn struct {
	BookID  string `json:"book_id" jsonschema:"the book the scene belongs to (UUID)"`
	SceneID string `json:"scene_id" jsonschema:"the scene index row to fetch (UUID)"`
}
type sceneDetail struct {
	SceneID        string  `json:"scene_id"`
	BookID         *string `json:"book_id"`
	ChapterID      string  `json:"chapter_id"`
	SortOrder      int     `json:"sort_order"`
	Title          string  `json:"title"`
	Path           string  `json:"path"`
	LeafText       string  `json:"leaf_text"`
	SourceSceneID  *string `json:"source_scene_id"`
	ContentHash    string  `json:"content_hash"`
	ParseVersion   int     `json:"parse_version"`
	LifecycleState string  `json:"lifecycle_state"`
}
type sceneGetOut struct {
	Scene sceneDetail `json:"scene"`
}

func (s *Server) toolBookSceneGet(ctx context.Context, _ *mcp.CallToolRequest, in sceneGetIn) (*mcp.CallToolResult, sceneGetOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, sceneGetOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, sceneGetOut{}, errors.New("book_id must be a UUID")
	}
	sceneID, err := uuid.Parse(in.SceneID)
	if err != nil {
		return nil, sceneGetOut{}, errors.New("scene_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, sceneGetOut{}, mcpOwnershipError(err)
	}
	var d sceneDetail
	var id, chID uuid.UUID
	var bookIDScan, sourceSceneID *uuid.UUID
	err = s.pool.QueryRow(ctx,
		`SELECT id, book_id, chapter_id, sort_order, title, path, leaf_text, source_scene_id, content_hash, parse_version, lifecycle_state
FROM scenes WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`, sceneID, bookID).
		Scan(&id, &bookIDScan, &chID, &d.SortOrder, &d.Title, &d.Path, &d.LeafText, &sourceSceneID, &d.ContentHash, &d.ParseVersion, &d.LifecycleState)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, sceneGetOut{}, errBookNotAccessible
	}
	if err != nil {
		return nil, sceneGetOut{}, errors.New("failed to get scene")
	}
	d.SceneID = id.String()
	d.ChapterID = chID.String()
	d.BookID = uuidPtrToStr(bookIDScan)
	d.SourceSceneID = uuidPtrToStr(sourceSceneID)
	return nil, sceneGetOut{Scene: d}, nil
}
