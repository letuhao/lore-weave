package api

// Pipeline M2 — class-C PROPOSE MCP tools for the high-impact / destructive
// entity-curation actions. Each MINTS a generalized action confirm token (no write) +
// returns a confirm card the LLM hands to glossary_confirm_action; a human reviews +
// confirms via the token-gated /v1/glossary/actions/{confirm,preview} path. There is
// deliberately NO MCP tool that performs these writes directly — a buggy/compromised
// consumer routing through the gateway can mint but never mutate. All are Manage-gated
// (the confirm path requires Manage for grant authority), so the mint side checks Manage
// too to avoid minting a card the proposer could never redeem.

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterPipelineProposeTools adds the M2 class-C propose tools to the user/book MCP server.
// LEGACY (catalog-unification 2026-07-22 Part C): all four are superseded by
// glossary_propose_curation (op enum). They stay registered (visibility:legacy) for existing
// callers and share the SAME curation*Core funcs as the unified tool (no divergence).
func (s *Server) RegisterPipelineProposeTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_status_change",
		Description: "Propose a BATCH status change for entities (active | inactive | draft | rejected) — e.g. " +
			"approve drafts, retire stale entities, or reject a draft that shouldn't be kept. book_id + status + " +
			"entity_ids (UUIDs). Returns a confirm card; a human approves before anything changes. Reversible " +
			"(just set the status back). " +
			"NOTE: superseded by glossary_propose_curation (op=status_change) — kept for existing callers only.",
		InputSchema: closedSetSchemaFor[proposeStatusChangeToolIn](map[string][]any{
			"status": {"active", "inactive", "draft", "rejected"},
		}),
		// Mints a grant confirm_token (no direct write) ⇒ Tier W. LEGACY → glossary_propose_curation.
		Meta: lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil), lwmcp.VisibilityLegacy), "glossary_propose_curation"),
	}, s.toolProposeStatusChange)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_restore_revision",
		Description: "Propose restoring an entity to one of its prior revisions (see glossary_get_entity include=revisions). " +
			"book_id + entity_id + revision_id. DESTRUCTIVE: it prunes-then-restores the entity's attributes/" +
			"translations/evidence/chapter-links to that snapshot (current values not in the snapshot are removed). " +
			"Returns a confirm card; itself captured as a new revision, so it is reversible. " +
			"NOTE: superseded by glossary_propose_curation (op=restore_revision) — kept for existing callers only.",
		Meta: lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil), lwmcp.VisibilityLegacy), "glossary_propose_curation"),
	}, s.toolProposeRestoreRevision)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_reassign_kind",
		Description: "Propose moving an entity to a different kind (triage the unknown bucket — see " +
			"glossary_curation_list view=unknowns). book_id + entity_id + kind_code (the target kind's code). " +
			"DESTRUCTIVE: attribute values whose code has no counterpart in the new kind are DROPPED (the confirm " +
			"card previews exactly which). Recoverable via revision restore. Returns a confirm card. " +
			"NOTE: superseded by glossary_propose_curation (op=reassign_kind) — kept for existing callers only.",
		Meta: lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil), lwmcp.VisibilityLegacy), "glossary_propose_curation"),
	}, s.toolProposeReassignKind)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_merge",
		Description: "Propose merging duplicate entities (see glossary_curation_list view=merge_candidates). book_id + winner_id " +
			"(kept) + loser_ids (merged away). DESTRUCTIVE: each loser is soft-deleted and its non-conflicting child " +
			"rows + name/aliases fold into the winner. Losers must be the SAME kind as the winner. Returns a confirm " +
			"card; each merge is journaled and reversible via the merge-journal revert. " +
			"NOTE: superseded by glossary_propose_curation (op=merge) — kept for existing callers only.",
		Meta: lwmcp.WithSupersededBy(lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil), lwmcp.VisibilityLegacy), "glossary_propose_curation"),
	}, s.toolProposeMerge)
}

// proposeStatusChangeToolIn is named (not inline) so the registration can build
// its closed-set schema from the same type the handler decodes (W0 #2).
type proposeStatusChangeToolIn struct {
	BookID    string   `json:"book_id,omitempty" jsonschema:"the book (UUID)"`
	Status    string   `json:"status" jsonschema:"active | inactive | draft"`
	EntityIDs []string `json:"entity_ids" jsonschema:"the entities to change (UUIDs)"`
}

// toolProposeStatusChange is the LEGACY thin wrapper (catalog-unification 2026-07-22 Part C):
// glossary_propose_curation op=status_change is the unified entry. Both share curationStatusChangeCore.
func (s *Server) toolProposeStatusChange(ctx context.Context, req *mcp.CallToolRequest, in proposeStatusChangeToolIn) (*mcp.CallToolResult, any, error) {
	userID, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, confirmCardOut{}, err
	}
	return s.curationStatusChangeCore(ctx, req, userID, bookID, in.Status, in.EntityIDs)
}

// curationStatusChangeCore — shared post-auth core for the status-change curation op (used by
// glossary_propose_curation op=status_change AND the legacy glossary_propose_status_change).
// The caller has already resolved userID + bookID and enforced the Manage grant.
func (s *Server) curationStatusChangeCore(ctx context.Context, req *mcp.CallToolRequest, userID, bookID uuid.UUID, statusRaw string, entityIDsRaw []string) (*mcp.CallToolResult, any, error) {
	status := strings.TrimSpace(statusRaw)
	if !validEntityStatus(status) {
		return nil, confirmCardOut{}, errors.New("status must be active, inactive, draft, or rejected")
	}
	ids := parseEntityIDs(entityIDsRaw)
	if len(ids) == 0 {
		return nil, confirmCardOut{}, errors.New("at least one valid entity_id is required")
	}
	if len(ids) > 1000 {
		return nil, confirmCardOut{}, errors.New("entity_ids must be at most 1000")
	}
	live, err := s.countLiveEntitiesInBook(ctx, bookID, ids)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve entities")
	}
	if live == 0 {
		return nil, confirmCardOut{}, errors.New("none of the given entities are live in this book")
	}
	params := statusChangeParams{Status: status, EntityIDs: entityIDsRaw}
	rows := []previewRow{
		{Label: "new status", Value: status},
		{Label: "entities updated", Value: fmt.Sprint(live)},
	}
	title := fmt.Sprintf("Set %d entities to %q", live, status)
	_, card, cardErr := s.mintGrantActionCard(userID, bookID, descStatusChange, title, params, rows, false)
	// External MCP discoverability audit #11 — effectStatusChange's UPDATE has no
	// `status <> target` guard, so it reports every live id as "updated" even when they
	// ALL already have the target status. Warn up front instead of letting the caller
	// confirm a token that changes nothing meaningful.
	if cardErr == nil {
		if changing, cerr := s.countEntitiesNeedingStatusChange(ctx, bookID, ids, status); cerr == nil && changing == 0 {
			card.Warning = fmt.Sprintf("all %d matched entities already have status %q — this will change nothing", live, status)
		}
	}
	return s.gateOrCard(ctx, req, descStatusChange, bookID, userID, params, card, cardErr)
}

// toolProposeRestoreRevision is the LEGACY thin wrapper — glossary_propose_curation
// op=restore_revision is the unified entry; both share curationRestoreRevisionCore.
func (s *Server) toolProposeRestoreRevision(ctx context.Context, req *mcp.CallToolRequest, in struct {
	BookID     string `json:"book_id,omitempty" jsonschema:"the book (UUID)"`
	EntityID   string `json:"entity_id" jsonschema:"the entity (UUID)"`
	RevisionID string `json:"revision_id" jsonschema:"the revision to restore to (UUID; see glossary_get_entity include=revisions)"`
}) (*mcp.CallToolResult, any, error) {
	userID, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, confirmCardOut{}, err
	}
	return s.curationRestoreRevisionCore(ctx, req, userID, bookID, in.EntityID, in.RevisionID)
}

// curationRestoreRevisionCore — shared post-auth core (caller resolved userID + bookID + Manage grant).
func (s *Server) curationRestoreRevisionCore(ctx context.Context, req *mcp.CallToolRequest, userID, bookID uuid.UUID, entityIDRaw, revisionIDRaw string) (*mcp.CallToolResult, any, error) {
	entityID, err := uuid.Parse(strings.TrimSpace(entityIDRaw))
	if err != nil {
		return nil, confirmCardOut{}, errors.New("entity_id must be a UUID")
	}
	revID, err := uuid.Parse(strings.TrimSpace(revisionIDRaw))
	if err != nil {
		return nil, confirmCardOut{}, errors.New("revision_id must be a UUID")
	}
	inBook, err := s.entityBelongsToBook(ctx, entityID, bookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve the entity")
	}
	if !inBook {
		return nil, confirmCardOut{}, errors.New("entity not found in this book")
	}
	// Mint-time validation: the revision must exist for this entity AND be restorable.
	var revNum int
	var snapshot []byte
	if err := s.pool.QueryRow(ctx,
		`SELECT revision_num, snapshot FROM entity_revisions WHERE revision_id=$1 AND entity_id=$2`,
		revID, entityID).Scan(&revNum, &snapshot); err != nil {
		return nil, confirmCardOut{}, errors.New("revision not found for this entity")
	}
	if !snapshotRestorable(snapshot) {
		return nil, confirmCardOut{}, errors.New("that revision's snapshot is incomplete — it cannot be restored")
	}
	params := restoreRevisionParams{EntityID: entityID.String(), RevisionID: revID.String()}
	rows := []previewRow{
		{Label: "restore to", Value: fmt.Sprintf("revision #%d", revNum),
			Note: "prunes-then-restores attributes/translations/evidence/links to that snapshot"},
	}
	title := fmt.Sprintf("Restore entity to revision #%d", revNum)
	_, card, cerr := s.mintGrantActionCard(userID, bookID, descRestoreRevision, title, params, rows, true)
	return s.gateOrCard(ctx, req, descRestoreRevision, bookID, userID, params, card, cerr)
}

// toolProposeReassignKind is the LEGACY thin wrapper — glossary_propose_curation
// op=reassign_kind is the unified entry; both share curationReassignKindCore.
func (s *Server) toolProposeReassignKind(ctx context.Context, req *mcp.CallToolRequest, in struct {
	BookID   string `json:"book_id,omitempty" jsonschema:"the book (UUID)"`
	EntityID string `json:"entity_id" jsonschema:"the entity to move (UUID)"`
	KindCode string `json:"kind_code" jsonschema:"the target kind's code (see glossary_book_ontology_read)"`
}) (*mcp.CallToolResult, any, error) {
	userID, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, confirmCardOut{}, err
	}
	return s.curationReassignKindCore(ctx, req, userID, bookID, in.EntityID, in.KindCode)
}

// curationReassignKindCore — shared post-auth core (caller resolved userID + bookID + Manage grant).
func (s *Server) curationReassignKindCore(ctx context.Context, req *mcp.CallToolRequest, userID, bookID uuid.UUID, entityIDRaw, kindCodeRaw string) (*mcp.CallToolResult, any, error) {
	entityID, err := uuid.Parse(strings.TrimSpace(entityIDRaw))
	if err != nil {
		return nil, confirmCardOut{}, errors.New("entity_id must be a UUID")
	}
	kindCode := strings.TrimSpace(kindCodeRaw)
	if kindCode == "" {
		return nil, confirmCardOut{}, errors.New("kind_code is required")
	}
	inBook, err := s.entityBelongsToBook(ctx, entityID, bookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve the entity")
	}
	if !inBook {
		return nil, confirmCardOut{}, errors.New("entity not found in this book")
	}
	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve kinds")
	}
	kindID, ok := kindMap[kindCode]
	if !ok {
		return nil, confirmCardOut{}, errors.New("unknown kind: " + kindCode)
	}
	// External MCP discoverability audit #11 — if the entity is ALREADY on the target
	// kind, rekeyEntityToKind's re-key/drop UPDATEs all filter `od.kind_id <> newKindID`
	// and match zero rows; only a timestamp bumps. Mint-time this is a clean, cheap check
	// (one extra column off the row we already fetched via entityBelongsToBook's query).
	var currentKindID uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT kind_id FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&currentKindID); err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve the entity's current kind")
	}
	dropped, err := s.reassignKindDroppedCodes(ctx, entityID, kindID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to preview the reassignment")
	}
	params := reassignKindParams{EntityID: entityID.String(), KindID: kindID.String(), KindCode: kindCode}
	rows := []previewRow{{Label: "new kind", Value: kindCode}}
	if len(dropped) == 0 {
		rows = append(rows, previewRow{Label: "attributes dropped", Value: "0", Note: "all attribute values carry over"})
	} else {
		rows = append(rows, previewRow{Label: "attributes dropped (DATA LOSS)", Value: fmt.Sprint(len(dropped)),
			Note: "codes with no counterpart: " + strings.Join(dropped, ", ") + " — recoverable via revision restore"})
	}
	title := fmt.Sprintf("Reassign entity to kind %q", kindCode)
	_, card, cerr := s.mintGrantActionCard(userID, bookID, descReassignKind, title, params, rows, true)
	if cerr == nil && currentKindID == kindID {
		card.Warning = fmt.Sprintf("the entity is already kind %q — this will change nothing", kindCode)
	}
	return s.gateOrCard(ctx, req, descReassignKind, bookID, userID, params, card, cerr)
}

// toolProposeMerge is the LEGACY thin wrapper — glossary_propose_curation op=merge is the
// unified entry; both share curationMergeCore.
func (s *Server) toolProposeMerge(ctx context.Context, req *mcp.CallToolRequest, in struct {
	BookID   string   `json:"book_id,omitempty" jsonschema:"the book (UUID)"`
	WinnerID string   `json:"winner_id" jsonschema:"the entity to KEEP (UUID)"`
	LoserIDs []string `json:"loser_ids" jsonschema:"the entities to merge away (UUIDs; same kind as the winner)"`
}) (*mcp.CallToolResult, any, error) {
	userID, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, confirmCardOut{}, err
	}
	return s.curationMergeCore(ctx, req, userID, bookID, in.WinnerID, in.LoserIDs)
}

// curationMergeCore — shared post-auth core (caller resolved userID + bookID + Manage grant).
func (s *Server) curationMergeCore(ctx context.Context, req *mcp.CallToolRequest, userID, bookID uuid.UUID, winnerIDRaw string, loserIDsRaw []string) (*mcp.CallToolResult, any, error) {
	winnerID, err := uuid.Parse(strings.TrimSpace(winnerIDRaw))
	if err != nil {
		return nil, confirmCardOut{}, errors.New("winner_id must be a UUID")
	}
	losers := make([]string, 0, len(loserIDsRaw))
	for _, raw := range loserIDsRaw {
		if id, perr := uuid.Parse(strings.TrimSpace(raw)); perr == nil && id != winnerID {
			losers = append(losers, id.String())
		}
	}
	if len(losers) == 0 {
		return nil, confirmCardOut{}, errors.New("at least one loser_id (distinct from the winner) is required")
	}
	// Mint-time validation: the winner must be a live entity in this book.
	winnerInBook, err := s.entityBelongsToBook(ctx, winnerID, bookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve the winner")
	}
	if !winnerInBook {
		return nil, confirmCardOut{}, errors.New("winner is not a live entity in this book")
	}
	winnerName, _ := entityNameAndAliases(ctx, s.pool, winnerID)
	if winnerName == "" {
		winnerName = winnerID.String()
	}
	rows := []previewRow{{Label: "winner (kept)", Value: winnerName}}
	for _, raw := range losers {
		lid := uuid.MustParse(raw)
		name, _ := entityNameAndAliases(ctx, s.pool, lid)
		if name == "" {
			name = raw
		}
		rows = append(rows, previewRow{Label: "loser (merged away)", Value: name, Note: "soft-deleted; reversible"})
	}
	params := mergeParams{WinnerID: winnerID.String(), LoserIDs: losers}
	title := fmt.Sprintf("Merge %d entities into %q", len(losers), winnerName)
	_, card, cerr := s.mintGrantActionCard(userID, bookID, descMerge, title, params, rows, true)
	return s.gateOrCard(ctx, req, descMerge, bookID, userID, params, card, cerr)
}
