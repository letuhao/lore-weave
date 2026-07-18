package api

// Pipeline campaign — M1/M2 read tools. Make the agent-blind READ scenarios reachable:
// the LLM can now SEE merge candidates, an entity's chapter links + revision history,
// the unknown-kind triage bucket, an entity's evidence, and the AI-suggestion review
// inbox — the inputs it needs before proposing curation actions (the M2 write tools).
// All are class R: View-gated via bookToolAuth, scoped to
// the book (+ entity-in-book for entity-addressed reads). They wrap the SAME core queries
// the HTTP handlers use (single source of truth). Output is bounded for the LLM: revisions
// (200) and unknowns (500) cap in their cores; merge-candidates + chapter-links have no
// core LIMIT (HTTP keeps them unbounded), so the TOOLS cap at pipelineReadCap with an
// explicit `truncated` flag (no silent cap) to protect the model's token budget.

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterPipelineReadTools adds the M1 read tools to the user/book MCP server.
func (s *Server) RegisterPipelineReadTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_list_merge_candidates",
		Description: "List a book's proposed entity MERGE candidates (duplicate clusters the system " +
			"detected), ranked by score — each with its member entities, suggested winner, and rationale. " +
			"status defaults to 'proposed' (also: dismissed | merged). Read before proposing a merge.",
		InputSchema: closedSetSchemaFor[mergeCandToolIn](map[string][]any{
			"status": {"proposed", "dismissed", "merged"},
		}),
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolListMergeCandidates)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_list_chapter_links",
		Description: "List the chapters an entity is linked to (where it appears / is relevant), with " +
			"relevance + notes. book_id + entity_id.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolListChapterLinks)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_list_entity_revisions",
		Description: "List an entity's revision history (who changed what, when) newest-first. " +
			"book_id + entity_id. Use to find a revision to restore.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolListEntityRevisions)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_list_unknown_entities",
		Description: "List a book's UNKNOWN-kind entities — the triage bucket of extracted entities whose " +
			"kind couldn't be determined — with the source kind code the extractor guessed. Read before " +
			"proposing a kind reassignment. status defaults to 'draft' (pending, not yet actioned) so the " +
			"inbox actually drains as you triage; pass 'all' to see every status regardless of triage state.",
		InputSchema: closedSetSchemaFor[bookOnlyToolIn](map[string][]any{
			"status": {"draft", "active", "inactive", "rejected", "all"},
		}),
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolListUnknownEntities)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_get_entity_evidence",
		Description: "Get the evidence excerpts (quotes / summaries / references) attached to an entity's " +
			"attributes — what supports each value. book_id + entity_id. Read before judging or editing an " +
			"attribute, or before adding evidence with glossary_create_evidence.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolGetEntityEvidence)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_list_ai_suggestions",
		Description: "List a book's AI-SUGGESTED entities awaiting review — drafts the extractor proposed " +
			"(tagged 'ai-suggested', not yet user-rejected). The triage inbox. Read before proposing a status " +
			"change (approve/reject) or a merge. Returns each entity's name, status, and tags. status defaults " +
			"to 'draft' (pending) so already-actioned (active/inactive/rejected) entities drop out of the " +
			"inbox once triaged; pass 'all' to see every status regardless of triage state.",
		InputSchema: closedSetSchemaFor[bookOnlyToolIn](map[string][]any{
			"status": {"draft", "active", "inactive", "rejected", "all"},
		}),
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolListAISuggestions)
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

// resolveInboxStatusFilter normalizes a bookOnlyToolIn.Status argument shared by
// glossary_list_unknown_entities / glossary_list_ai_suggestions: blank defaults to
// "draft" (pending), "all" is passed through as the explicit no-filter sentinel, and
// any other value must be a real entity status (validEntityStatus, pipeline_confirm.go
// — the single source of truth, so this list can never drift from what
// glossary_propose_status_change itself accepts).
func resolveInboxStatusFilter(raw string) (string, error) {
	status := strings.TrimSpace(raw)
	if status == "" {
		return "draft", nil
	}
	if status == "all" || validEntityStatus(status) {
		return status, nil
	}
	return "", errors.New("status must be draft, active, inactive, rejected, or all")
}

// queryUnknownEntities is the auth-free core of listUnknownEntities. Returns the capped
// item list + the TRUE total (the list is LIMIT-capped, so len(items) under-reports).
// status == "" or "all" applies no status filter (the pre-fix, status-blind behavior);
// any other value (validated by the caller via validEntityStatus) restricts to exactly
// that status, so an actioned entity drops out of the default ("draft") view.
func (s *Server) queryUnknownEntities(ctx context.Context, bookID uuid.UUID, status string) ([]unknownEntityOut, int, error) {
	args := []any{bookID}
	statusFilter := ""
	if status != "" && status != "all" {
		statusFilter = " AND e.status = $2"
		args = append(args, status)
	}
	var total int
	if err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id AND k.code = 'unknown'
		WHERE e.book_id = $1 AND e.deleted_at IS NULL`+statusFilter, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	rows, err := s.pool.Query(ctx, `
		SELECT e.entity_id, COALESCE(nv.original_value, ''), e.source_kind_code, e.status, e.created_at, e.scope_label
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
		WHERE e.book_id = $1 AND e.deleted_at IS NULL`+statusFilter+`
		ORDER BY e.created_at DESC
		LIMIT 500`, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	out := make([]unknownEntityOut, 0)
	for rows.Next() {
		var e unknownEntityOut
		var ts time.Time
		if err := rows.Scan(&e.EntityID, &e.Name, &e.SourceKindCode, &e.Status, &ts, &e.ScopeLabel); err != nil {
			return nil, 0, err
		}
		e.CreatedAt = ts.Format(time.RFC3339)
		out = append(out, e)
	}
	return out, total, rows.Err()
}

// ── tools ─────────────────────────────────────────────────────────────────────

// pipelineReadCap bounds the LLM-facing payload of the tools whose cores have no LIMIT
// (merge-candidates, chapter-links). Truncation is signalled, never silent.
const pipelineReadCap = 200

type mergeCandToolIn struct {
	BookID string `json:"book_id" jsonschema:"the book (UUID)"`
	Status string `json:"status,omitempty" jsonschema:"proposed (default) | dismissed | merged — omit this argument for the default; do not send an empty string"`
}
type mergeCandidatesOut struct {
	Candidates []mergeCandidateView `json:"candidates"`
	Truncated  bool                 `json:"truncated,omitempty"`
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
	cands, err := s.loadMergeCandidates(ctx, bookID, status, 0) // tool: full set (truncates after, signals it)
	if err != nil {
		return nil, mergeCandidatesOut{}, errors.New("failed to load merge candidates")
	}
	truncated := false
	if len(cands) > pipelineReadCap {
		cands = cands[:pipelineReadCap]
		truncated = true
	}
	return nil, mergeCandidatesOut{Candidates: cands, Truncated: truncated}, nil
}

type bookEntityToolIn struct {
	BookID   string `json:"book_id" jsonschema:"the book (UUID)"`
	EntityID string `json:"entity_id" jsonschema:"the entity (UUID)"`
}
type chapterLinksOut struct {
	Links     []chapterLinkResp `json:"links"`
	Truncated bool              `json:"truncated,omitempty"`
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
	truncated := false
	if len(links) > pipelineReadCap {
		links = links[:pipelineReadCap]
		truncated = true
	}
	return nil, chapterLinksOut{Links: links, Truncated: truncated}, nil
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
	// External MCP feedback (2026-07-08, "the inboxes never drain") — both list tools
	// sharing this type used to return every entity regardless of status, so
	// approving/rejecting a triage item never removed it from the NEXT call's
	// results — there was no way to tell "what still needs my attention" from "I
	// already handled this." Defaults to "draft" (the pending state extraction
	// writes) so the inbox actually drains as items are actioned; "all" restores
	// the old status-blind behavior for a caller that explicitly wants everything.
	Status string `json:"status,omitempty" jsonschema:"draft (default, pending) | active | inactive | rejected | all — omit for the default; do not send an empty string"`
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
	status, err := resolveInboxStatusFilter(in.Status)
	if err != nil {
		return nil, unknownEntitiesOut{}, err
	}
	items, total, err := s.queryUnknownEntities(ctx, bookID, status)
	if err != nil {
		return nil, unknownEntitiesOut{}, errors.New("failed to load unknown entities")
	}
	return nil, unknownEntitiesOut{Items: items, Total: total}, nil
}

type entityEvidenceOut struct {
	Evidence  []entityEvidenceItem `json:"evidence"`
	Truncated bool                 `json:"truncated,omitempty"`
}

func (s *Server) toolGetEntityEvidence(ctx context.Context, _ *mcp.CallToolRequest, in bookEntityToolIn) (*mcp.CallToolResult, entityEvidenceOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, entityEvidenceOut{}, err
	}
	entityID, ok, err := s.resolveEntityInBook(ctx, in.EntityID, bookID)
	if err != nil {
		return nil, entityEvidenceOut{}, err
	}
	if !ok {
		return nil, entityEvidenceOut{}, errors.New("entity not found in this book")
	}
	// Query one past the cap to detect truncation without a second COUNT round-trip.
	items, err := s.queryEntityEvidences(ctx, entityID, pipelineReadCap+1)
	if err != nil {
		return nil, entityEvidenceOut{}, errors.New("failed to load evidence")
	}
	truncated := false
	if len(items) > pipelineReadCap {
		items = items[:pipelineReadCap]
		truncated = true
	}
	return nil, entityEvidenceOut{Evidence: items, Truncated: truncated}, nil
}

type aiSuggestionItem struct {
	EntityID  string   `json:"entity_id"`
	Name      string   `json:"name"`
	KindCode  string   `json:"kind_code"`
	Status    string   `json:"status"`
	Tags      []string `json:"tags"`
	CreatedAt string   `json:"created_at"`
	// ScopeLabel (D-GLOSSARY-ENTITY-SCOPE) surfaces an existing disambiguator so a
	// triaging agent/human can tell two same-named suggestions apart before
	// approving/merging/rejecting.
	ScopeLabel string `json:"scope_label,omitempty"`
}
type aiSuggestionsOut struct {
	Items []aiSuggestionItem `json:"items"`
	Total int                `json:"total"`
}

// queryAISuggestions lists a book's pending AI-suggested entities (tagged 'ai-suggested',
// NOT the 'ai-rejected' tombstone, live), newest-first, capped. Returns the capped list +
// the TRUE total. Auth-free core; grant is the CALLER's concern. status == "" or "all"
// applies no status filter (the pre-fix behavior — the tag check alone let an already
// approved/rejected entity linger forever, since nothing in this codebase ever sets the
// 'ai-rejected' tag); any other value restricts to exactly that status on top of the tag
// filter (additive, not a replacement — an entity could theoretically be re-tagged
// 'ai-rejected' by a future feature and this keeps honoring that too).
func (s *Server) queryAISuggestions(ctx context.Context, bookID uuid.UUID, status string) ([]aiSuggestionItem, int, error) {
	args := []any{bookID}
	statusFilter := ""
	if status != "" && status != "all" {
		statusFilter = " AND e.status = $2"
		args = append(args, status)
	}
	var total int
	if err := s.pool.QueryRow(ctx, `
		SELECT count(*) FROM glossary_entities e
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		  AND e.tags @> ARRAY['ai-suggested']::text[]
		  AND NOT (e.tags @> ARRAY['ai-rejected']::text[])`+statusFilter, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	limitArgs := append(append([]any{}, args...), pipelineReadCap)
	rows, err := s.pool.Query(ctx, `
		SELECT e.entity_id, COALESCE(nv.original_value, ''), k.code, e.status, e.tags, e.created_at::text, e.scope_label
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id
		LEFT JOIN entity_attribute_values nv
			ON nv.entity_id = e.entity_id
			AND nv.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code IN ('name','term')
				ORDER BY CASE ba.code WHEN 'name' THEN 0 ELSE 1 END, (g.code = 'universal') DESC, ba.sort_order
				LIMIT 1
			)
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		  AND e.tags @> ARRAY['ai-suggested']::text[]
		  AND NOT (e.tags @> ARRAY['ai-rejected']::text[])`+statusFilter+`
		ORDER BY e.created_at DESC
		LIMIT `+fmt.Sprintf("$%d", len(limitArgs)), limitArgs...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	items := []aiSuggestionItem{}
	for rows.Next() {
		var it aiSuggestionItem
		if err := rows.Scan(&it.EntityID, &it.Name, &it.KindCode, &it.Status, &it.Tags, &it.CreatedAt, &it.ScopeLabel); err != nil {
			return nil, 0, err
		}
		items = append(items, it)
	}
	return items, total, rows.Err()
}

func (s *Server) toolListAISuggestions(ctx context.Context, _ *mcp.CallToolRequest, in bookOnlyToolIn) (*mcp.CallToolResult, aiSuggestionsOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, aiSuggestionsOut{}, err
	}
	status, err := resolveInboxStatusFilter(in.Status)
	if err != nil {
		return nil, aiSuggestionsOut{}, err
	}
	items, total, err := s.queryAISuggestions(ctx, bookID, status)
	if err != nil {
		return nil, aiSuggestionsOut{}, errors.New("failed to load AI suggestions")
	}
	return nil, aiSuggestionsOut{Items: items, Total: total}, nil
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
