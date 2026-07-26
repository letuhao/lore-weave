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
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

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
	// entity_enrichments manufactures confidence-scored AI "dimensions" about an entity. It is guarded at
	// the ENTITY level below (PP-4: a real person — colleague/self — is refused), which is DB-local (no
	// network hop on this internal hot path) and precise. The wiki PUBLISH of any enrichment is separately
	// diary-blocked (PP-2/PP-3), so a diary's own project/org supplement stays private + unpublishable.

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
	var isPerson bool
	if err := s.pool.QueryRow(ctx,
		`SELECT ek.is_person
		   FROM glossary_entities ge JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		  WHERE ge.entity_id=$1 AND ge.book_id=$2 AND ge.deleted_at IS NULL`,
		entityID, bookID).Scan(&isPerson); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity lookup failed")
		return
	}
	// PP-4 (spec 08 R6) — ENTITY-level guard: never manufacture AI "dimensions" about a REAL PERSON.
	// A diary colleague is a real third party who never consented. C4/SD-C4: gate on the STRUCTURAL
	// is_person flag (was the literal 'colleague' code), so a renamed/custom real-person kind is also
	// refused. DB-local (no network hop) + precise; defense-in-depth behind the book-level diary blocks
	// (PP-2/PP-3) for the cross-book/merged case. (The user's own is_self entity is their own data, not
	// a third party — and in a diary it is book-level blocked regardless.)
	if isPerson {
		writeError(w, http.StatusForbidden, "GLOSS_NO_ENRICH_PERSON",
			"a real person is not an enrichable entity")
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

// internalEnrichmentCoverage lists the book's entities with the per-dimension
// enrichment coverage the lore-enrichment gap engine (C7) needs to build
// EntityCoverage and detect under-described entities (D1 gap-auto-detect).
//
//	GET /internal/books/{book_id}/enrichment-coverage
//
// Per live entity: canonical name, kind code, mention_count (chapter links —
// the C6 ranking signal), and the DISTINCT PROMOTED enrichment dimensions
// (review_status='promoted', not soft-deleted) it already has. The lore side
// treats those as `present_dimensions`; the rest of the dimension table is the
// gap. Proposed (still-quarantined) enrichment is intentionally NOT counted as
// coverage — an un-promoted dimension is still a gap. Ordered by mention_count
// desc (most-referenced first) then entity_id for a stable page.
func (s *Server) internalEnrichmentCoverage(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	limit := 200
	if v := strings.TrimSpace(r.URL.Query().Get("limit")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 1000 {
			limit = n
		}
	}

	rows, err := s.pool.Query(r.Context(), `
		SELECT
			e.entity_id,
			k.code AS kind_code,
			COALESCE(name_av.original_value, '') AS name,
			(SELECT COUNT(*) FROM chapter_entity_links cel WHERE cel.entity_id = e.entity_id) AS mention_count,
			COALESCE(ARRAY(
				SELECT DISTINCT ee.dimension FROM entity_enrichments ee
				WHERE ee.entity_id = e.entity_id
				  AND ee.review_status = 'promoted' AND ee.deleted_at IS NULL
			), '{}') AS dimensions
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id
		LEFT JOIN entity_attribute_values name_av
			ON name_av.entity_id = e.entity_id
			AND name_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
				ORDER BY (g.code = 'universal') DESC, ba.sort_order LIMIT 1
			)
		-- C4/SD-C4 (cold-review LOW-MED-3) — defense-in-depth: never offer a REAL person as an
		-- enrichment TARGET (the write-back already refuses one, but don't ship its data to a picker
		-- that would send it to the LLM before the 403).
		WHERE e.book_id = $1 AND e.deleted_at IS NULL AND NOT k.is_person
		ORDER BY mention_count DESC, e.entity_id
		LIMIT $2`, bookID, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "coverage query failed")
		return
	}
	defer rows.Close()

	type coverageItem struct {
		EntityID      string   `json:"entity_id"`
		CanonicalName string   `json:"canonical_name"`
		Kind          string   `json:"kind"`
		MentionCount  int      `json:"mention_count"`
		Dimensions    []string `json:"dimensions"`
	}
	items := make([]coverageItem, 0)
	for rows.Next() {
		var it coverageItem
		var eid, kind, name string
		var mentions int
		var dims []string
		if err := rows.Scan(&eid, &kind, &name, &mentions, &dims); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "coverage scan failed")
			return
		}
		it.EntityID, it.Kind, it.CanonicalName, it.MentionCount = eid, kind, name, mentions
		it.Dimensions = dims
		if it.Dimensions == nil {
			it.Dimensions = []string{}
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "coverage rows failed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":  bookID.String(),
		"entities": items,
	})
}
