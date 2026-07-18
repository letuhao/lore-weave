package api

// S-BOOK — 28 AN-7 lexical-search MCP tool. The manuscript's literal (grep)
// search engine (search.go's runLexicalSearch) is REST-only; the agent's only
// prose search is story_search (semantic). book_search closes that hole — the
// exact-match class of question every rename / canon check / consistency pass
// starts with ("which chapters literally contain 'Thần Hồn'").
//
// It is a ~thin MCP ADAPTER over the SAME engine, gates, enums, and pagination
// the REST route uses (search.go) — reusing runLexicalSearch, validateSearchQuery
// (maxSearchQueryRunes), validateSurface, validateGranularity, and clampLimit —
// so the two front doors can never drift (PH20 discipline applied to a read).
// Tier R, ScopeBook (VIEW), identity from the envelope (SEC-1).

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type searchToolIn struct {
	BookID      string `json:"book_id" jsonschema:"the book to search (UUID)"`
	Q           string `json:"q" jsonschema:"the literal text to find (1..256 chars; LIKE metacharacters are escaped so it matches verbatim)"`
	Surface     string `json:"surface,omitempty" jsonschema:"which text to search: draft (live editor text) | canon (published revisions) | all (default draft)"`
	Granularity string `json:"granularity,omitempty" jsonschema:"result grain: chapter (best block per chapter, the navigate default) | block (every matching block) (default chapter)"`
	Limit       int    `json:"limit,omitempty" jsonschema:"max results (default 20, max 100)"`
	Offset      int    `json:"offset,omitempty" jsonschema:"pagination offset (default 0)"`
}

// searchToolOut returns the route's result rows VERBATIM (buildLexicalHit shape:
// chapterId, chapterTitle, sortOrder, surface, snippet, highlights, location,
// score, …) so the MCP and REST front doors stay identical. has_more is the
// standard page-boundary heuristic (a full page ⇒ there may be more).
type searchToolOut struct {
	Query   string           `json:"query"`
	Mode    string           `json:"mode"`
	Results []map[string]any `json:"results"`
	HasMore bool             `json:"has_more"`
}

func (s *Server) toolBookSearch(ctx context.Context, _ *mcp.CallToolRequest, in searchToolIn) (*mcp.CallToolResult, searchToolOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, searchToolOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, searchToolOut{}, errors.New("book_id must be a UUID")
	}
	q, errMsg := validateSearchQuery(in.Q)
	if errMsg != "" {
		return nil, searchToolOut{}, errors.New(errMsg)
	}
	surface, errMsg := validateSurface(in.Surface)
	if errMsg != "" {
		return nil, searchToolOut{}, errors.New(errMsg)
	}
	granularity, errMsg := validateGranularity(in.Granularity)
	if errMsg != "" {
		return nil, searchToolOut{}, errors.New(errMsg)
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, searchToolOut{}, mcpOwnershipError(err)
	}
	limit := clampLimit(in.Limit) // default 20, max 100 — mirrors parseLimitOffset
	offset := in.Offset
	if offset < 0 {
		offset = 0
	}
	results, err := s.runLexicalSearch(ctx, bookID, q, limit, offset, granularity, surface)
	if err != nil {
		return nil, searchToolOut{}, errors.New("search failed")
	}
	return nil, searchToolOut{
		Query:   q,
		Mode:    "lexical",
		Results: results,
		HasMore: len(results) >= limit,
	}, nil
}
