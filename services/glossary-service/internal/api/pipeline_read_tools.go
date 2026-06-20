package api

// Pipeline campaign — M1 read tools. Make the agent-blind READ scenarios reachable:
// the LLM can now SEE merge candidates, an entity's chapter links + revision history, and
// the unknown-kind triage bucket — the inputs it needs before proposing curation actions
// (the M2 class-C write tools). All are class R: View-gated via bookToolAuth, scoped to
// the book (+ entity-in-book for entity-addressed reads), output-capped by their cores.
// They wrap the SAME core queries the HTTP handlers use (single source of truth).

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterPipelineReadTools adds the M1 read tools to the user/book MCP server.
func (s *Server) RegisterPipelineReadTools(srv *mcp.Server) {
	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_list_merge_candidates",
		Description: "List a book's proposed entity MERGE candidates (duplicate clusters the system " +
			"detected), ranked by score — each with its member entities, suggested winner, and rationale. " +
			"status defaults to 'proposed' (also: dismissed | merged). Read before proposing a merge.",
	}, s.toolListMergeCandidates)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_list_chapter_links",
		Description: "List the chapters an entity is linked to (where it appears / is relevant), with " +
			"relevance + notes. book_id + entity_id.",
	}, s.toolListChapterLinks)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_list_entity_revisions",
		Description: "List an entity's revision history (who changed what, when) newest-first. " +
			"book_id + entity_id. Use to find a revision to restore.",
	}, s.toolListEntityRevisions)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_list_unknown_entities",
		Description: "List a book's UNKNOWN-kind entities — the triage bucket of extracted entities whose " +
			"kind couldn't be determined — with the source kind code the extractor guessed. Read before " +
			"proposing a kind reassignment.",
	}, s.toolListUnknownEntities)
}

// ── shared cores (also called by the HTTP handlers — single source of truth) ──

// entityBelongsToBook reports whether a live entity belongs to the book (tenant guard for
// entity-addressed reads).
func (s *Server) entityBelongsToBook(ctx context.Context, entityID, bookID uuid.UUID) (bool, error) {
	var ok bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)`,
		entityID, bookID).Scan(&ok)
	return ok, err
}

// queryEntityRevisions is the auth-free core of listEntityRevisions.
func (s *Server) queryEntityRevisions(ctx context.Context, entityID uuid.UUID) ([]entityRevisionSummary, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT revision_id, revision_num, op, actor_type, actor_id, created_at::text
		FROM entity_revisions WHERE entity_id=$1
		ORDER BY revision_num DESC LIMIT $2`, entityID, entityRevisionsListCap)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]entityRevisionSummary, 0, 32)
	for rows.Next() {
		var it entityRevisionSummary
		var actorID *uuid.UUID
		if err := rows.Scan(&it.RevisionID, &it.RevisionNum, &it.Op, &it.ActorType, &actorID, &it.CreatedAt); err != nil {
			continue
		}
		if actorID != nil {
			a := actorID.String()
			it.ActorID = &a
		}
		items = append(items, it)
	}
	return items, rows.Err()
}

// queryUnknownEntities is the auth-free core of listUnknownEntities. Returns the capped
// item list + the TRUE total (the list is LIMIT-capped, so len(items) under-reports).
func (s *Server) queryUnknownEntities(ctx context.Context, bookID uuid.UUID) ([]unknownEntityOut, int, error) {
	var total int
	if err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id AND k.code = 'unknown'
		WHERE e.book_id = $1 AND e.deleted_at IS NULL`, bookID).Scan(&total); err != nil {
		return nil, 0, err
	}
	rows, err := s.pool.Query(ctx, `
		SELECT e.entity_id, COALESCE(nv.original_value, ''), e.source_kind_code, e.status, e.created_at
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id AND k.code = 'unknown'
		LEFT JOIN entity_attribute_values nv
			ON nv.entity_id = e.entity_id
			AND nv.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
				ORDER BY (g.code = 'universal') DESC, ba.sort_order LIMIT 1
			)
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		ORDER BY e.created_at DESC
		LIMIT 500`, bookID)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	out := make([]unknownEntityOut, 0)
	for rows.Next() {
		var e unknownEntityOut
		var ts time.Time
		if err := rows.Scan(&e.EntityID, &e.Name, &e.SourceKindCode, &e.Status, &ts); err != nil {
			return nil, 0, err
		}
		e.CreatedAt = ts.Format(time.RFC3339)
		out = append(out, e)
	}
	return out, total, rows.Err()
}

// ── tools ─────────────────────────────────────────────────────────────────────

type mergeCandToolIn struct {
	BookID string `json:"book_id" jsonschema:"the book (UUID)"`
	Status string `json:"status,omitempty" jsonschema:"proposed (default) | dismissed | merged"`
}
type mergeCandidatesOut struct {
	Candidates []mergeCandidateView `json:"candidates"`
}

func (s *Server) toolListMergeCandidates(ctx context.Context, _ *mcp.CallToolRequest, in mergeCandToolIn) (*mcp.CallToolResult, mergeCandidatesOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, mergeCandidatesOut{}, err
	}
	status := strings.TrimSpace(in.Status)
	if status == "" {
		status = "proposed"
	}
	if status != "proposed" && status != "dismissed" && status != "merged" {
		return nil, mergeCandidatesOut{}, errors.New("status must be proposed, dismissed, or merged")
	}
	cands, err := s.loadMergeCandidates(ctx, bookID, status)
	if err != nil {
		return nil, mergeCandidatesOut{}, errors.New("failed to load merge candidates")
	}
	return nil, mergeCandidatesOut{Candidates: cands}, nil
}

type bookEntityToolIn struct {
	BookID   string `json:"book_id" jsonschema:"the book (UUID)"`
	EntityID string `json:"entity_id" jsonschema:"the entity (UUID)"`
}
type chapterLinksOut struct {
	Links []chapterLinkResp `json:"links"`
}

func (s *Server) toolListChapterLinks(ctx context.Context, _ *mcp.CallToolRequest, in bookEntityToolIn) (*mcp.CallToolResult, chapterLinksOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, chapterLinksOut{}, err
	}
	entityID, ok, err := s.resolveEntityInBook(ctx, in.EntityID, bookID)
	if err != nil {
		return nil, chapterLinksOut{}, err
	}
	if !ok {
		return nil, chapterLinksOut{}, errors.New("entity not found in this book")
	}
	links, err := s.queryChapterLinks(ctx, entityID)
	if err != nil {
		return nil, chapterLinksOut{}, errors.New("failed to load chapter links")
	}
	return nil, chapterLinksOut{Links: links}, nil
}

type entityRevisionsOut struct {
	Revisions []entityRevisionSummary `json:"revisions"`
}

func (s *Server) toolListEntityRevisions(ctx context.Context, _ *mcp.CallToolRequest, in bookEntityToolIn) (*mcp.CallToolResult, entityRevisionsOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, entityRevisionsOut{}, err
	}
	entityID, ok, err := s.resolveEntityInBook(ctx, in.EntityID, bookID)
	if err != nil {
		return nil, entityRevisionsOut{}, err
	}
	if !ok {
		return nil, entityRevisionsOut{}, errors.New("entity not found in this book")
	}
	revs, err := s.queryEntityRevisions(ctx, entityID)
	if err != nil {
		return nil, entityRevisionsOut{}, errors.New("failed to load revisions")
	}
	return nil, entityRevisionsOut{Revisions: revs}, nil
}

type bookOnlyToolIn struct {
	BookID string `json:"book_id" jsonschema:"the book (UUID)"`
}
type unknownEntitiesOut struct {
	Items []unknownEntityOut `json:"items"`
	Total int                `json:"total"`
}

func (s *Server) toolListUnknownEntities(ctx context.Context, _ *mcp.CallToolRequest, in bookOnlyToolIn) (*mcp.CallToolResult, unknownEntitiesOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, unknownEntitiesOut{}, err
	}
	items, total, err := s.queryUnknownEntities(ctx, bookID)
	if err != nil {
		return nil, unknownEntitiesOut{}, errors.New("failed to load unknown entities")
	}
	return nil, unknownEntitiesOut{Items: items, Total: total}, nil
}

// resolveEntityInBook parses an entity-id string and confirms it belongs to the book.
func (s *Server) resolveEntityInBook(ctx context.Context, entityIDStr string, bookID uuid.UUID) (uuid.UUID, bool, error) {
	entityID, perr := uuid.Parse(strings.TrimSpace(entityIDStr))
	if perr != nil {
		return uuid.Nil, false, errors.New("entity_id must be a UUID")
	}
	ok, err := s.entityBelongsToBook(ctx, entityID, bookID)
	if err != nil {
		return uuid.Nil, false, errors.New("failed to verify the entity")
	}
	return entityID, ok, nil
}
