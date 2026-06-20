package api

// Pipeline campaign — M2 write tools. Class W (direct, Edit-gated) for the ADDITIVE,
// low-risk curation writes — chapter-links (and, later, evidence) — so an agent can record
// where an entity appears without a confirm round-trip. The DESTRUCTIVE writes (merge,
// reassign-kind, batch status-change, restore-revision) are class C and go through the
// generalized confirm spine instead (see the M2 handoff). Each wraps the same core the
// HTTP handler uses.

import (
	"context"
	"errors"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterPipelineWriteTools adds the M2 direct (class-W) write tools to the /mcp server.
func (s *Server) RegisterPipelineWriteTools(srv *mcp.Server) {
	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_create_chapter_link",
		Description: "Link an entity to a chapter it appears in (additive, takes effect immediately; Edit). " +
			"book_id + entity_id + chapter_id (the chapter must belong to the book). relevance = " +
			"major | appears (default) | mentioned. Errors if the entity is already linked to that chapter.",
	}, s.toolCreateChapterLink)
}

type createChapterLinkToolIn struct {
	BookID    string `json:"book_id" jsonschema:"the book (UUID)"`
	EntityID  string `json:"entity_id" jsonschema:"the entity (UUID)"`
	ChapterID string `json:"chapter_id" jsonschema:"the chapter to link (UUID; must belong to the book)"`
	Relevance string `json:"relevance,omitempty" jsonschema:"major | appears (default) | mentioned"`
	Note      string `json:"note,omitempty"`
}

func (s *Server) toolCreateChapterLink(ctx context.Context, _ *mcp.CallToolRequest, in createChapterLinkToolIn) (*mcp.CallToolResult, chapterLinkResp, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantEdit)
	if err != nil {
		return nil, chapterLinkResp{}, err
	}
	entityID, ok, err := s.resolveEntityInBook(ctx, in.EntityID, bookID)
	if err != nil {
		return nil, chapterLinkResp{}, err
	}
	if !ok {
		return nil, chapterLinkResp{}, errors.New("entity not found in this book")
	}
	chapterID, err := uuid.Parse(strings.TrimSpace(in.ChapterID))
	if err != nil {
		return nil, chapterLinkResp{}, errors.New("chapter_id must be a UUID")
	}
	var note *string
	if n := strings.TrimSpace(in.Note); n != "" {
		note = &n
	}
	cl, err := s.createChapterLinkCore(ctx, bookID, entityID, chapterID, in.Relevance, note)
	if err != nil {
		// The core's sentinel errors are already LLM-readable — return them verbatim. Any
		// OTHER error is an unexpected DB/internal failure; wrap it so a raw pgx string never
		// reaches the model (the HTTP path does the same via writeChapterLinkErr's default).
		switch {
		case errors.Is(err, errChapterRelevance), errors.Is(err, errChapterNotInBook),
			errors.Is(err, errChapterUpstream), errors.Is(err, errChapterLinkDup):
			return nil, chapterLinkResp{}, err
		default:
			return nil, chapterLinkResp{}, errors.New("failed to create the chapter link")
		}
	}
	return nil, *cl, nil
}
