package api

// Internal enrichment-supplement endpoints (lore-enrichment F-C13-1 + F-C13-2).
//
//	POST   /internal/books/{book_id}/entities/{entity_id}/enrichments
//	DELETE /internal/books/{book_id}/entities/{entity_id}/enrichments?proposal_id=
//
// Service-to-service only (X-Internal-Token via the /internal route group).
//
// Why this exists (PO ruling B1, 2026-05-31):
//   The lore-enrichment promote flow previously wrote enriched lore onto the
//   canonical entity's short_description COLUMN (canon-content / DEFERRED-053).
//   The QC review found that CONFLATES makeup with the original authored canon:
//   once enrichment resolves onto the real canonical entity, short_description
//   could no longer be told apart from author-written canon (F-C13-2), and
//   retract had no clean per-supplement undo — it tried to recycle the WHOLE
//   entity via a user JWT a service-to-service call never carries (F-C13-1).
//
//   These endpoints write the enrichment to its OWN table (entity_enrichments,
//   FK→canonical entity) as a distinguished supplement / `dị bản`, and retract
//   it via a soft-delete on an internal token — no user JWT, the canonical
//   entity + its original canon are never touched.
//
// H0 note: the supplement is born quarantined. The POST sets origin='enrichment'
//   unconditionally (the client cannot supply origin), confidence stays <1.0
//   (DB CHECK), and review_status is constrained to {proposed,promoted}. A
//   supplement row can never masquerade as canon. Promote moves a proposal's
//   rows to review_status='promoted' (markers attached) — it is still a
//   distinguished supplement, never merged into short_description.

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/sanitize"
)

// enrichmentFact is one per-dimension supplement row in an upsert request.
type enrichmentFact struct {
	Dimension  string  `json:"dimension"`
	Content    string  `json:"content"`
	Confidence float64 `json:"confidence"`
}

// upsertEnrichmentRequest is the POST body. A proposal_id keys a variant set;
// every fact in the request belongs to that one proposal.
type upsertEnrichmentRequest struct {
	ProposalID   string           `json:"proposal_id"`
	Technique    string           `json:"technique"`
	ReviewStatus string           `json:"review_status"`
	PromotedBy   *string          `json:"promoted_by"`
	PromotedAt   *string          `json:"promoted_at"`
	Facts        []enrichmentFact `json:"facts"`
}

// internalUpsertEnrichments upserts the supplement rows for one proposal.
//
//	POST /internal/books/{book_id}/entities/{entity_id}/enrichments
//
// ON CONFLICT (entity_id, dimension, proposal_id) the row is updated in place
// and un-soft-deleted (deleted_at=NULL) so a re-write of an earlier-retracted
// proposal restores it. Emits glossary.entity_updated so the C4 glossary_sync
// pipeline runs.
func (s *Server) internalUpsertEnrichments(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}

	var req upsertEnrichmentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}

	proposalID, err := uuid.Parse(strings.TrimSpace(req.ProposalID))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid proposal_id")
		return
	}
	technique := strings.TrimSpace(req.Technique)
	if technique == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "technique is required")
		return
	}
	reviewStatus := strings.TrimSpace(req.ReviewStatus)
	if reviewStatus == "" {
		reviewStatus = "proposed"
	}
	if reviewStatus != "proposed" && reviewStatus != "promoted" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY",
			"review_status must be 'proposed' or 'promoted'")
		return
	}
	if len(req.Facts) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "facts must be non-empty")
		return
	}

	var promotedBy *uuid.UUID
	if req.PromotedBy != nil && strings.TrimSpace(*req.PromotedBy) != "" {
		pb, perr := uuid.Parse(strings.TrimSpace(*req.PromotedBy))
		if perr != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid promoted_by")
			return
		}
		promotedBy = &pb
	}

	// promoted_at: validate as RFC3339 if present (review-impl LOW-4) — a raw
	// garbage string would otherwise reach the TIMESTAMPTZ column as a 500.
	var promotedAt *time.Time
	if req.PromotedAt != nil && strings.TrimSpace(*req.PromotedAt) != "" {
		ts, terr := time.Parse(time.RFC3339, strings.TrimSpace(*req.PromotedAt))
		if terr != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY",
				"promoted_at must be an RFC3339 timestamp")
			return
		}
		promotedAt = &ts
	}

	// Provenance invariant (review-impl LOW-6): a 'promoted' supplement MUST carry
	// the promoter marker — a promoted row without promoted_by is an untraceable
	// canon-adjacent write. (The DB CHECK is the backstop; this is the clean 400.)
	if reviewStatus == "promoted" && promotedBy == nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY",
			"promoted_by is required when review_status='promoted'")
		return
	}

	ctx := r.Context()

	// The entity must exist + belong to this book (not soft-deleted) — a stale
	// or cross-book entity_id is a 404, never a silent FK error or wrong-row
	// write. (The FK guarantees referential integrity but not book scoping.)
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM glossary_entities
		    WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)`,
		entityID, bookID).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity lookup failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}

	// Validate every fact BEFORE any write so a bad fact yields a clean 4xx and
	// no partial state (review-impl LOW-5: the writes then run in ONE tx).
	type vfact struct {
		dimension  string
		content    string
		confidence float64
	}
	vfacts := make([]vfact, 0, len(req.Facts))
	for _, f := range req.Facts {
		// Untrusted LLM text → neutralize structural injection (chat-template /
		// role-spoof tokens, zero-width smuggling) at the canon boundary,
		// independent of the caller, exactly as canon-content does. NFC-safe.
		// BOTH the dimension label and the content are neutralized — the
		// dimension reaches the wiki render as 【增补·<dimension>】, so it is a
		// stored-injection surface too (review-impl LOW-3).
		dimension := strings.TrimSpace(sanitize.NeutralizeCanonText(f.Dimension))
		if dimension == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "fact dimension is required")
			return
		}
		content := strings.TrimSpace(sanitize.NeutralizeCanonText(f.Content))
		if content == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "fact content is required")
			return
		}
		if utf8.RuneCountInString(content) > 4000 {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_CONTENT",
				"fact content must be at most 4000 characters")
			return
		}
		// confidence must stay strictly sub-canon (H0). The DB CHECK also
		// enforces this; validate here for a clean 422 instead of a 500.
		if f.Confidence <= 0 || f.Confidence >= 1.0 {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_CONFIDENCE",
				"confidence must be in (0, 1.0)")
			return
		}
		vfacts = append(vfacts, vfact{dimension, content, f.Confidence})
	}

	// All facts for the proposal upsert in ONE transaction — a mid-loop failure
	// can no longer leave a partial supplement (review-impl LOW-5).
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(ctx)

	written := 0
	for _, f := range vfacts {
		// origin is NOT taken from the client — it is always 'enrichment'
		// (the column DEFAULT). This makes it structurally impossible for a
		// caller to write a 'glossary'-origin (canon) supplement row.
		tag, err := tx.Exec(ctx,
			`INSERT INTO entity_enrichments
			   (entity_id, book_id, dimension, content, technique, confidence,
			    proposal_id, review_status, promoted_by, promoted_at, deleted_at, updated_at)
			 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10, NULL, now())
			 ON CONFLICT (entity_id, dimension, proposal_id) DO UPDATE SET
			   content       = EXCLUDED.content,
			   technique     = EXCLUDED.technique,
			   confidence    = EXCLUDED.confidence,
			   review_status = EXCLUDED.review_status,
			   promoted_by   = EXCLUDED.promoted_by,
			   promoted_at   = EXCLUDED.promoted_at,
			   deleted_at    = NULL,
			   updated_at    = now()`,
			entityID, bookID, f.dimension, f.content, technique, f.confidence,
			proposalID, reviewStatus, promotedBy, promotedAt)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "enrichment upsert failed")
			return
		}
		written += int(tag.RowsAffected())
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx commit failed")
		return
	}

	// The supplement changed → re-run glossary_sync (C4/K14) best-effort.
	// Already committed; fire-and-forget so a broker hiccup can't fail a
	// successful write.
	s.emitEntityUpdated(ctx, entityID, "updated")

	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id":   entityID.String(),
		"book_id":     bookID.String(),
		"proposal_id": proposalID.String(),
		"written":     written,
	})
}

// internalDeleteEnrichments soft-deletes a proposal's supplement rows (retract).
//
//	DELETE /internal/books/{book_id}/entities/{entity_id}/enrichments?proposal_id=
//
// This is the F-C13-1 fix: retract un-canonizes the enrichment via the internal
// token, exactly the way promote canonized it — NO user JWT, and the canonical
// entity + its original canon are never touched (only the supplement rows get
// deleted_at). Idempotent: a missing/already-retracted proposal returns 200 with
// soft_deleted=0.
func (s *Server) internalDeleteEnrichments(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	proposalID, err := uuid.Parse(strings.TrimSpace(r.URL.Query().Get("proposal_id")))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid or missing proposal_id")
		return
	}

	ctx := r.Context()
	tag, err := s.pool.Exec(ctx,
		`UPDATE entity_enrichments
		    SET deleted_at = now(), updated_at = now()
		  WHERE entity_id = $1 AND book_id = $2 AND proposal_id = $3
		    AND deleted_at IS NULL`,
		entityID, bookID, proposalID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "enrichment soft-delete failed")
		return
	}
	softDeleted := int(tag.RowsAffected())

	// Only re-sync if something actually changed (retract of a no-op proposal
	// shouldn't spam the pipeline).
	if softDeleted > 0 {
		s.emitEntityUpdated(ctx, entityID, "updated")
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id":    entityID.String(),
		"book_id":      bookID.String(),
		"proposal_id":  proposalID.String(),
		"soft_deleted": softDeleted,
	})
}
