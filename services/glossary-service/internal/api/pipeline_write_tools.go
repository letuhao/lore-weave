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
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterPipelineWriteTools adds the M2 direct (class-W) write tools to the /mcp server.
func (s *Server) RegisterPipelineWriteTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_create_chapter_link",
		Description: "Link an entity to a chapter it appears in (additive, takes effect immediately; Edit). " +
			"book_id + entity_id + chapter_id (the chapter must belong to the book). relevance = " +
			"major | appears (default) | mentioned. Errors if the entity is already linked to that chapter.",
		InputSchema: closedSetSchemaFor[createChapterLinkToolIn](map[string][]any{
			"relevance": {"major", "appears", "mentioned"},
		}),
		// Direct, additive, reversible write (no confirm_token) ⇒ lwmcp Tier A. (The file's
		// "class W" is internal jargon for a direct Edit-gated write, NOT lwmcp's TierW,
		// which means confirm_action — those are the "class C" propose tools.)
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, nil),
	}, s.toolCreateChapterLink)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_create_evidence",
		Description: "Attach an evidence excerpt (a quote / summary / reference supporting an attribute value) " +
			"to an entity's attribute (additive, takes effect immediately; Edit). book_id + entity_id + " +
			"attr_value_id (the attribute value to support — get it from the entity's attributes). " +
			"evidence_type = quote (default) | summary | reference. original_text is the excerpt; " +
			"original_language defaults to 'zh'. Optionally cite chapter_id (UUID) + chapter_title + " +
			"chapter_index + block_or_line.",
		InputSchema: closedSetSchemaFor[createEvidenceToolIn](map[string][]any{
			"evidence_type": {"quote", "summary", "reference"},
		}),
		// Direct, additive, reversible write (no confirm_token) ⇒ lwmcp Tier A.
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, nil),
	}, s.toolCreateEvidence)
}

type createEvidenceToolIn struct {
	BookID           string  `json:"book_id" jsonschema:"the book (UUID)"`
	EntityID         string  `json:"entity_id" jsonschema:"the entity (UUID)"`
	AttrValueID      string  `json:"attr_value_id" jsonschema:"the attribute value the evidence supports (UUID; must belong to the entity)"`
	EvidenceType     string  `json:"evidence_type,omitempty" jsonschema:"quote (default) | summary | reference"`
	OriginalText     string  `json:"original_text" jsonschema:"the excerpt / evidence text"`
	OriginalLanguage string  `json:"original_language,omitempty" jsonschema:"BCP-47 language of original_text (default zh)"`
	ChapterID        string  `json:"chapter_id,omitempty" jsonschema:"the chapter this evidence comes from (UUID)"`
	ChapterTitle     *string `json:"chapter_title,omitempty"`
	ChapterIndex     *int    `json:"chapter_index,omitempty"`
	BlockOrLine      string  `json:"block_or_line,omitempty" jsonschema:"a block/line locator within the chapter"`
	Note             string  `json:"note,omitempty"`
}

func (s *Server) toolCreateEvidence(ctx context.Context, _ *mcp.CallToolRequest, in createEvidenceToolIn) (*mcp.CallToolResult, evidenceResp, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantEdit)
	if err != nil {
		return nil, evidenceResp{}, err
	}
	entityID, ok, err := s.resolveEntityInBook(ctx, in.EntityID, bookID)
	if err != nil {
		return nil, evidenceResp{}, err
	}
	if !ok {
		return nil, evidenceResp{}, errors.New("entity not found in this book")
	}
	attrValueID, err := uuid.Parse(strings.TrimSpace(in.AttrValueID))
	if err != nil {
		return nil, evidenceResp{}, errors.New("attr_value_id must be a UUID")
	}
	inEntity, err := s.attrValueInEntity(ctx, attrValueID, entityID)
	if err != nil {
		return nil, evidenceResp{}, errors.New("failed to verify the attribute value")
	}
	if !inEntity {
		return nil, evidenceResp{}, errors.New("attr_value_id does not belong to this entity")
	}
	var note *string
	if n := strings.TrimSpace(in.Note); n != "" {
		note = &n
	}
	ev, err := s.createEvidenceCore(ctx, attrValueID, in.EvidenceType, in.OriginalText,
		in.OriginalLanguage, in.ChapterID, in.ChapterTitle, in.ChapterIndex, in.BlockOrLine, note)
	if err != nil {
		// Sentinels are LLM-readable; wrap anything else (raw pgx) like the chapter-link tool.
		switch {
		case errors.Is(err, errEvidenceType), errors.Is(err, errEvidenceChapter):
			return nil, evidenceResp{}, err
		default:
			return nil, evidenceResp{}, errors.New("failed to create the evidence")
		}
	}
	return nil, *ev, nil
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
