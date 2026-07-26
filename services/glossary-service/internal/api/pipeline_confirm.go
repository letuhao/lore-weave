package api

// Pipeline M2 — class-C confirm effects + previews for the high-impact / destructive
// entity-curation actions (status_change, restore_revision, reassign_kind, merge). Each
// effect re-validates against CURRENT state at confirm time (§13.5) and wraps the SAME
// core the HTTP handler uses; each preview re-renders the human-facing card from current
// state (never consuming the token). Authority is grant (Manage, re-checked in
// authorizeAction); the propose/mint side lives in pipeline_propose_tools.go.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

// ── status_change ─────────────────────────────────────────────────────────────

type statusChangeParams struct {
	Status    string   `json:"status"`
	EntityIDs []string `json:"entity_ids"`
}

// parseEntityIDs drops malformed ids (a bad id never matches the book-scoped WHERE).
func parseEntityIDs(raw []string) []uuid.UUID {
	ids := make([]uuid.UUID, 0, len(raw))
	for _, r := range raw {
		if id, err := uuid.Parse(strings.TrimSpace(r)); err == nil {
			ids = append(ids, id)
		}
	}
	return ids
}

func validEntityStatus(s string) bool {
	switch s {
	case "active", "inactive", "draft", "rejected":
		return true
	default:
		return false
	}
}

func (s *Server) effectStatusChange(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p statusChangeParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	if !validEntityStatus(p.Status) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "invalid status — propose again")
		return
	}
	updated, err := s.bulkSetEntityStatusCore(ctx, claims.BookID, p.Status, parseEntityIDs(p.EntityIDs))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "status update failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"updated": updated, "status": p.Status})
}

func (s *Server) previewStatusChange(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p statusChangeParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	ids := parseEntityIDs(p.EntityIDs)
	live, err := s.countLiveEntitiesInBook(ctx, claims.BookID, ids)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor: descStatusChange, Title: fmt.Sprintf("Set %d entities to %q", live, p.Status), Destructive: false,
		PreviewRows: []previewRow{
			{Label: "new status", Value: p.Status},
			{Label: "entities updated", Value: fmt.Sprint(live)},
			{Label: "not found / already removed", Value: fmt.Sprint(len(ids) - live), Note: "skipped"},
		},
	})
}

// ── restore_revision ──────────────────────────────────────────────────────────

type restoreRevisionParams struct {
	EntityID   string `json:"entity_id"`
	RevisionID string `json:"revision_id"`
}

func (s *Server) effectRestoreRevision(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p restoreRevisionParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	entityID, err := uuid.Parse(p.EntityID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "invalid entity — propose again")
		return
	}
	revID, err := uuid.Parse(p.RevisionID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "invalid revision — propose again")
		return
	}
	// Re-confirm entity-in-book at confirm time (the token's book scopes authority, but
	// the entity id is opaque params — bind it to the book here so it can't target another).
	inBook, err := s.entityBelongsToBook(ctx, entityID, claims.BookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed")
		return
	}
	if !inBook {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the entity no longer exists — propose again")
		return
	}
	revNum, err := s.restoreEntityRevisionCore(ctx, claims.BookID, entityID, claims.UserID, revID)
	switch {
	case errors.Is(err, errRevisionNotFound):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the revision no longer exists — propose again")
		return
	case errors.Is(err, errRevisionIncomplete):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INCOMPLETE_REVISION", "revision snapshot is incomplete — cannot restore")
		return
	case err != nil:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"restored": true, "entity_id": entityID.String(), "from_revision_num": revNum})
}

func (s *Server) previewRestoreRevision(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p restoreRevisionParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	out := actionPreview{Descriptor: descRestoreRevision, Destructive: true, Title: "Restore entity to a prior revision"}
	entityID, err := uuid.Parse(p.EntityID)
	if err != nil {
		out.PreviewRows = []previewRow{{Label: "status", Value: "invalid", Note: "propose again"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	revID, err := uuid.Parse(p.RevisionID)
	if err != nil {
		out.PreviewRows = []previewRow{{Label: "status", Value: "invalid", Note: "propose again"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	var revNum int
	var snapshot json.RawMessage
	if err := s.pool.QueryRow(ctx,
		`SELECT revision_num, snapshot FROM entity_revisions WHERE revision_id=$1 AND entity_id=$2`,
		revID, entityID).Scan(&revNum, &snapshot); err != nil {
		out.PreviewRows = []previewRow{{Label: "status", Value: "not found", Note: "the revision no longer exists — propose again"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	rows := []previewRow{
		{Label: "restore to", Value: fmt.Sprintf("revision #%d", revNum),
			Note: "prunes-then-restores attributes/translations/evidence/links to that snapshot"},
	}
	if !snapshotRestorable(snapshot) {
		rows = append(rows, previewRow{Label: "warning", Value: "incomplete snapshot", Note: "not restorable"})
	}
	out.PreviewRows = rows
	writeJSON(w, http.StatusOK, out)
}

// ── reassign_kind ─────────────────────────────────────────────────────────────

type reassignKindParams struct {
	EntityID string `json:"entity_id"`
	KindID   string `json:"kind_id"` // book_kind_id (resolved from kind_code at mint)
	KindCode string `json:"kind_code"`
}

func (s *Server) effectReassignKind(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p reassignKindParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	entityID, err := uuid.Parse(p.EntityID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "invalid entity — propose again")
		return
	}
	kindID, err := uuid.Parse(p.KindID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "invalid kind — propose again")
		return
	}
	err = s.reassignEntityKindCore(ctx, claims.BookID, entityID, kindID)
	switch {
	case errors.Is(err, errReassignKindNotFound):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the target kind no longer exists — propose again")
		return
	case errors.Is(err, errReassignEntityNotFound):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the entity no longer exists — propose again")
		return
	case err != nil:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reassign failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"entity_id": entityID.String(), "kind_id": kindID.String()})
}

func (s *Server) previewReassignKind(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p reassignKindParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	out := actionPreview{Descriptor: descReassignKind, Destructive: true,
		Title: fmt.Sprintf("Reassign entity to kind %q", p.KindCode)}
	entityID, err1 := uuid.Parse(p.EntityID)
	kindID, err2 := uuid.Parse(p.KindID)
	if err1 != nil || err2 != nil {
		out.PreviewRows = []previewRow{{Label: "status", Value: "invalid", Note: "propose again"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	dropped, err := s.reassignKindDroppedCodes(ctx, entityID, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
		return
	}
	rows := []previewRow{{Label: "new kind", Value: p.KindCode}}
	if len(dropped) == 0 {
		rows = append(rows, previewRow{Label: "attributes dropped", Value: "0", Note: "all attribute values carry over"})
	} else {
		rows = append(rows, previewRow{Label: "attributes dropped (DATA LOSS)", Value: fmt.Sprint(len(dropped)),
			Note: "codes with no counterpart in the new kind: " + strings.Join(dropped, ", ") + " — recoverable via revision restore"})
	}
	out.PreviewRows = rows
	writeJSON(w, http.StatusOK, out)
}

// ── merge ─────────────────────────────────────────────────────────────────────

type mergeParams struct {
	WinnerID string   `json:"winner_id"`
	LoserIDs []string `json:"loser_ids"`
}

func (s *Server) effectMerge(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p mergeParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	winnerID, err := uuid.Parse(p.WinnerID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "invalid winner — propose again")
		return
	}
	if len(p.LoserIDs) == 0 {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "no losers — propose again")
		return
	}
	results, err := s.mergeEntitiesCore(ctx, claims.BookID, winnerID, p.LoserIDs, claims.UserID, false)
	if errors.Is(err, errMergeBadWinner) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the winner is no longer a live entity — propose again")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "merge failed")
		return
	}
	// Each merged result carries journal_id — the revert handle (POST merge-journal/{id}/revert).
	writeJSON(w, http.StatusOK, map[string]any{"winner_id": winnerID.String(), "results": results})
}

func (s *Server) previewMerge(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p mergeParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	out := actionPreview{Descriptor: descMerge, Destructive: true, Title: "Merge entities"}
	winnerID, err := uuid.Parse(p.WinnerID)
	if err != nil {
		out.PreviewRows = []previewRow{{Label: "status", Value: "invalid winner", Note: "propose again"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	winnerName, _ := entityNameAndAliases(ctx, s.pool, winnerID)
	if winnerName == "" {
		winnerName = winnerID.String()
	}
	rows := []previewRow{{Label: "winner (kept)", Value: winnerName}}
	for _, raw := range p.LoserIDs {
		lid, err := uuid.Parse(raw)
		if err != nil {
			rows = append(rows, previewRow{Label: "loser (merged away)", Value: raw, Note: "invalid uuid — will be skipped"})
			continue
		}
		name, _ := entityNameAndAliases(ctx, s.pool, lid)
		if name == "" {
			name = lid.String()
		}
		rows = append(rows, previewRow{Label: "loser (merged away)", Value: name, Note: "soft-deleted; name folded into winner's aliases"})
	}
	rows = append(rows, previewRow{Label: "reversible", Value: "yes", Note: "each merge is journaled — revert via merge-journal/{id}/revert"})
	out.PreviewRows = rows
	writeJSON(w, http.StatusOK, out)
}
