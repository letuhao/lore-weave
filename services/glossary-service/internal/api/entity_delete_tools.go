package api

// glossary_entity_delete / glossary_entity_restore — real-usage feedback found no
// way to hard/soft-delete a garbage glossary_entities row (e.g. an AI-extraction
// draft with empty name, 0 attributes, 0 evidence — nothing to classify, so
// glossary_propose_reassign_kind is the wrong tool). The soft-delete/restore CORE
// LOGIC already existed (entity_handler.go's deleteEntity / recycle_bin_handler.go's
// restoreEntity — REST-only), and the frontend already carries these exact MCP
// tool names in its Undo allowlist (useActivityUndo.ts ALLOWED_UNDO_TOOLS) —
// this file is the missing MCP exposure.
//
// TIER SPLIT (mirrors glossary_ontology_delete's book-tier vs user-tier asymmetry,
// CAT-2 in mcp-tool-io.md): delete is destructive (an entity + its attribute
// values/evidence/chapter-links go dark) so it is Tier-W — propose+confirm,
// mint-only, NEVER mutates on the tool call itself. Restore is the safe direction
// (it only reverses a prior delete, never destroys anything new) so it is Tier-A —
// auto-executing, no confirm. This matches this service's OWN existing precedent:
// glossary_user_restore is Tier-A/direct, the reversal counterpart of
// glossary_user_delete (also Tier-A) and of glossary_ontology_delete's user-scope
// branch (direct, reversible). Checked book-service's mcp_actions.go/mcp_server.go
// before committing to this: book_delete/book_chapter_delete ARE registered
// (Tier-W), but book_restore/chapter_restore — named right alongside them in the
// SAME FE allowlist — are NOT registered as MCP tools anywhere in that service yet.
// So they set no usable tiering precedent either way; glossary's own user-tier
// restore is the only real, already-shipped restore precedent in this codebase,
// and it is Tier-A. That is the basis for tiering glossary_entity_restore Tier-A.
//
// BULK vs SINGLE (engineering judgment call per the task): glossary_ontology_delete
// batches (1-50 items) because an ontology row is cheap and structural — a batch of
// schema rows + their cascades is still a proportionate one-line confirm. An
// entity's blast radius is its own full attribute/evidence/chapter-link history,
// and the reported use case is a SMALL number of individually-reviewed garbage
// entities (3, in the field report) where a human wants to see each one (name,
// attribute count, chapter-link count) before confirming — not approve an N-count
// in one line. So glossary_entity_delete takes ONE entity_id. A batch variant is
// buildable later if the batch-curation use case actually materializes (it does
// NOT exist as a real need yet, so per the no-defer-drift gate it is not built
// speculatively here — batch status changes already have their own dedicated tool,
// glossary_propose_status_change, for the "triage many at once" case).

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterEntityDeleteTools adds glossary_entity_delete (Tier-W propose) and
// glossary_entity_restore (Tier-A direct) to the book MCP server.
func (s *Server) RegisterEntityDeleteTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_entity_delete",
		Description: "Propose DELETING one glossary entity (soft-delete — recoverable via " +
			"glossary_entity_restore until purged). Use this for a genuinely empty/garbage entity " +
			"(no name, no attributes, no evidence) — NOT for triaging an unknown-kind entity that just " +
			"needs re-classifying (use glossary_propose_reassign_kind for that). High-impact: returns a " +
			"confirm_token + a preview of what would be lost (name if any, attribute count, chapter-link " +
			"count) — a human must approve via glossary_confirm_action before anything is deleted. " +
			"Deleting an already-deleted entity is a no-op, not an error.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook,
			map[string]any{"tool": "glossary_entity_restore"},
			[]string{"delete entity", "remove entity", "trash entity", "delete garbage entity", "clean up duplicate entity"}),
	}, s.toolProposeEntityDelete)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_entity_restore",
		Description: "Restore a soft-deleted glossary entity from the recycle bin (undo a " +
			"glossary_entity_delete). Direct — no confirmation needed, since restoring only reverses a " +
			"prior delete. Restoring an entity that is not in the trash is a no-op, not an error.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil,
			[]string{"restore entity", "undelete entity", "recover entity", "undo entity delete"}),
	}, s.toolEntityRestore)
}

// ── glossary_entity_delete (Tier-W: mint-only propose) ────────────────────────

type entityDeleteToolIn struct {
	BookID   string `json:"book_id" jsonschema:"the book the entity belongs to (UUID)"`
	EntityID string `json:"entity_id" jsonschema:"the entity to delete (UUID)"`
}

// entityDeleteParams is the captured intent for a glossary_entity_delete
// proposal. book_id rides in the token's claims.BookID (mintGrantActionCard binds
// it), so only the target entity needs capturing — mirrors restoreRevisionParams/
// reassignKindParams's shape (pipeline_confirm.go).
type entityDeleteParams struct {
	EntityID string `json:"entity_id"`
}

func (s *Server) toolProposeEntityDelete(ctx context.Context, _ *mcp.CallToolRequest, in entityDeleteToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(strings.TrimSpace(in.BookID))
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	entityID, err := uuid.Parse(strings.TrimSpace(in.EntityID))
	if err != nil {
		return nil, confirmCardOut{}, errors.New("entity_id must be a UUID")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, confirmCardOut{}, uniformOwnershipError(err)
	}
	exists, deleted, err := s.entityDeleteState(ctx, bookID, entityID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve the entity")
	}
	if !exists {
		return nil, confirmCardOut{}, errors.New("entity not found in this book")
	}
	info, err := s.entityDeletePreview(ctx, entityID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to preview the delete")
	}
	rows := entityDeletePreviewRows(info, deleted)
	title := "Delete unnamed entity"
	if info.Name != "" {
		title = fmt.Sprintf("Delete entity %q", info.Name)
	}
	res, out, err := s.mintGrantActionCard(userID, bookID, descEntityDelete, title,
		entityDeleteParams{EntityID: entityID.String()}, rows, true)
	// External MCP discoverability audit #11 precedent (same pattern as
	// glossary_ontology_delete / glossary_propose_status_change / glossary_propose_reassign_kind):
	// a token minted against an already-deleted entity is still confirmable but will
	// change nothing — warn up front instead of letting the caller confirm blind.
	if err == nil && deleted {
		out.Warning = "this entity is already deleted — confirming will change nothing"
	}
	return res, out, err
}

// effectEntityDelete re-validates against CURRENT state (§13.5 #4) and soft-
// deletes the entity via the SAME core the REST DELETE route uses
// (entity_handler.go::softDeleteEntityCore). Idempotent: an entity already
// deleted since propose is reported as a clean success, not an error — the
// caller's desired end state (entity gone) already holds (mirrors
// glossary_ontology_delete's "already removed — nothing to delete" precedent).
func (s *Server) effectEntityDelete(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p entityDeleteParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	entityID, err := uuid.Parse(p.EntityID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "bad entity ref")
		return
	}
	exists, _, err := s.entityDeleteState(ctx, claims.BookID, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if !exists {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the entity no longer exists — propose again")
		return
	}
	if _, err := s.softDeleteEntityCore(ctx, claims.BookID, entityID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	// softDeleteEntityCore's found=false here just means it was already deleted
	// since propose — idempotent, not an error (the entity is deleted either way,
	// which is the caller's goal).
	writeJSON(w, http.StatusOK, map[string]any{"entity_id": entityID, "deleted": true})
}

// previewEntityDelete re-renders the delete confirm card from CURRENT state
// (§5.1 #5) — mirrors previewBookDelete/previewMerge.
func (s *Server) previewEntityDelete(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p entityDeleteParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	entityID, err := uuid.Parse(p.EntityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	out := actionPreview{Descriptor: descEntityDelete, Destructive: true, Title: "Delete entity"}
	exists, deleted, err := s.entityDeleteState(ctx, claims.BookID, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	if !exists {
		out.PreviewRows = []previewRow{{Label: "status", Value: "already removed", Note: "this entity no longer exists"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	info, err := s.entityDeletePreview(ctx, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	out.Title = "Delete unnamed entity"
	if info.Name != "" {
		out.Title = fmt.Sprintf("Delete entity %q", info.Name)
	}
	out.PreviewRows = entityDeletePreviewRows(info, deleted)
	writeJSON(w, http.StatusOK, out)
}

// ── glossary_entity_restore (Tier-A: direct, auto-executing) ──────────────────

type entityRestoreToolIn struct {
	BookID   string `json:"book_id" jsonschema:"the book the entity belongs to (UUID)"`
	EntityID string `json:"entity_id" jsonschema:"the entity to restore (UUID)"`
}

type entityRestoreOut struct {
	EntityID string `json:"entity_id"`
	Restored bool   `json:"restored"` // false = idempotent no-op (already live, purged, or nonexistent)
}

// toolEntityRestore is Tier-A: auto-executing, no confirm — restoring only
// reverses a prior delete, the safe direction (see the file header for the
// tiering rationale). Edit-gated, matching the REST restoreEntity route's own
// grant level (recycle_bin_handler.go) — restore is deliberately LESS gated than
// delete (which requires Manage), matching the CAT-2 safety asymmetry.
func (s *Server) toolEntityRestore(ctx context.Context, _ *mcp.CallToolRequest, in entityRestoreToolIn) (*mcp.CallToolResult, entityRestoreOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, entityRestoreOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(strings.TrimSpace(in.BookID))
	if err != nil {
		return nil, entityRestoreOut{}, errors.New("book_id must be a UUID")
	}
	entityID, err := uuid.Parse(strings.TrimSpace(in.EntityID))
	if err != nil {
		return nil, entityRestoreOut{}, errors.New("entity_id must be a UUID")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantEdit); err != nil {
		return nil, entityRestoreOut{}, uniformOwnershipError(err)
	}
	found, err := s.restoreEntityCore(ctx, bookID, entityID)
	if err != nil {
		return nil, entityRestoreOut{}, errors.New("restore failed")
	}
	// found=false: idempotent no-op (not in the trash — already live, purged, or
	// nonexistent). Not an error — the caller's desired end state (entity live) may
	// already hold.
	res := &mcp.CallToolResult{Meta: mcp.Meta{
		lwmcp.MetaKeyUndoHint: map[string]any{
			"tool": "glossary_entity_delete",
			"args": map[string]any{"book_id": bookID.String(), "entity_id": entityID.String()},
		},
	}}
	return res, entityRestoreOut{EntityID: entityID.String(), Restored: found}, nil
}

// ── shared preview/state helpers ───────────────────────────────────────────────

// entityDeleteState resolves an entity's book membership + soft-delete state for
// the mint-time / preview-time / confirm-time re-validation. exists=false means no
// such entity_id in this book at all (never existed, a different book, or already
// permanently purged — a purged entity is treated as gone, matching the recycle-
// bin list's own exclusion of purged rows). deleted=true means it is currently in
// the recycle bin (deleted_at set, not yet purged).
func (s *Server) entityDeleteState(ctx context.Context, bookID, entityID uuid.UUID) (exists, deleted bool, err error) {
	err = s.pool.QueryRow(ctx,
		`SELECT true, deleted_at IS NOT NULL FROM glossary_entities
		 WHERE entity_id=$1 AND book_id=$2 AND permanently_deleted_at IS NULL`,
		entityID, bookID).Scan(&exists, &deleted)
	if isNoRows(err) {
		return false, false, nil
	}
	return exists, deleted, err
}

// entityDeletePreviewInfo is the "what would be lost" snapshot shown on the
// glossary_entity_delete confirm card, so a human can see the entity is genuinely
// empty/garbage (no name, no attributes, no evidence) before confirming.
type entityDeletePreviewInfo struct {
	Name           string
	AttributeCount int
	ChapterLinks   int
}

// entityDeletePreview reads the name (via the shared entityNameAndAliases helper,
// merge_handler.go — the same one glossary_propose_merge's preview uses) plus
// live counts of the entity's attribute values and chapter links.
func (s *Server) entityDeletePreview(ctx context.Context, entityID uuid.UUID) (entityDeletePreviewInfo, error) {
	name, _ := entityNameAndAliases(ctx, s.pool, entityID)
	var attrs, links int
	if err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM entity_attribute_values WHERE entity_id=$1`, entityID).Scan(&attrs); err != nil {
		return entityDeletePreviewInfo{}, err
	}
	if err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM chapter_entity_links WHERE entity_id=$1`, entityID).Scan(&links); err != nil {
		return entityDeletePreviewInfo{}, err
	}
	return entityDeletePreviewInfo{Name: name, AttributeCount: attrs, ChapterLinks: links}, nil
}

// entityDeletePreviewRows renders the shared preview-row shape used by both the
// mint-time card (toolProposeEntityDelete) and the current-state re-render
// (previewEntityDelete) — kept in one place so the two never drift.
func entityDeletePreviewRows(info entityDeletePreviewInfo, alreadyDeleted bool) []previewRow {
	rows := make([]previewRow, 0, 4)
	if info.Name != "" {
		rows = append(rows, previewRow{Label: "name", Value: info.Name})
	} else {
		rows = append(rows, previewRow{Label: "name", Value: "(none)", Note: "unnamed — likely a stub/garbage draft"})
	}
	rows = append(rows,
		previewRow{Label: "attributes", Value: fmt.Sprint(info.AttributeCount)},
		previewRow{Label: "chapter links", Value: fmt.Sprint(info.ChapterLinks)},
	)
	if alreadyDeleted {
		rows = append(rows, previewRow{Label: "status", Value: "already deleted", Note: "already in the recycle bin — nothing to delete"})
	}
	return rows
}
