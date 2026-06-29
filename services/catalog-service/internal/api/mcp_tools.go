package api

// S-CATALOG Tier-R (read) MCP tool handlers. Each delegates to the shared query core
// (queryPublicBooks / queryPublicBook in server.go) so the MCP surface and the HTTP
// catalog stay byte-identical. PUBLIC content (OD-7) — no identity/owner gate.

import (
	"context"
	"errors"
	"net/http"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// ── catalog_list_public_books ────────────────────────────────────────────────

type catalogListIn struct {
	Limit    int    `json:"limit,omitempty" jsonschema:"max books to return (default 20, max 100)"`
	Offset   int    `json:"offset,omitempty" jsonschema:"pagination offset"`
	Query    string `json:"query,omitempty" jsonschema:"free-text title search"`
	Language string `json:"language,omitempty" jsonschema:"filter by original language code (e.g. en, zh)"`
	Genre    string `json:"genre,omitempty" jsonschema:"filter by genre tag(s); comma-separated = OR"`
	Sort     string `json:"sort,omitempty" jsonschema:"recent (default) | alpha | chapters | popular"`
	Author   string `json:"author,omitempty" jsonschema:"filter by author user id (UUID)"`
}

type catalogListOut struct {
	Items []map[string]any `json:"items"`
	Total int              `json:"total"`
}

func (s *Server) toolCatalogListPublicBooks(ctx context.Context, _ *mcp.CallToolRequest, in catalogListIn) (*mcp.CallToolResult, catalogListOut, error) {
	items, total, status, _, msg := s.queryPublicBooks(in.Limit, in.Offset, in.Query, in.Language, in.Genre, in.Sort, in.Author)
	if status != http.StatusOK {
		if status == http.StatusBadRequest { // a caller-fixable bad arg (e.g. author uuid)
			return nil, catalogListOut{}, errors.New(msg)
		}
		return nil, catalogListOut{}, errors.New("failed to list public books")
	}
	if items == nil {
		items = []map[string]any{}
	}
	return nil, catalogListOut{Items: items, Total: total}, nil
}

// ── catalog_get_book ─────────────────────────────────────────────────────────

type catalogGetIn struct {
	BookID string `json:"book_id" jsonschema:"the public book to fetch (UUID)"`
}

type catalogGetOut struct {
	Book map[string]any `json:"book"`
}

func (s *Server) toolCatalogGetBook(ctx context.Context, _ *mcp.CallToolRequest, in catalogGetIn) (*mcp.CallToolResult, catalogGetOut, error) {
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, catalogGetOut{}, errors.New("invalid book id")
	}
	data, status := s.queryPublicBook(bookID)
	if status != http.StatusOK {
		return nil, catalogGetOut{}, errors.New("book not found")
	}
	return nil, catalogGetOut{Book: data}, nil
}
