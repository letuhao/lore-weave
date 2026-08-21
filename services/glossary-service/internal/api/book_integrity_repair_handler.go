package api

import (
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

type bookIntegrityRepairResponse struct {
	BookID     uuid.UUID `json:"book_id"`
	FixedCodes []string  `json:"fixed_codes"`
	FixedCount int       `json:"fixed_count"`
	CheckedAt  time.Time `json:"checked_at"`
}

func (s *Server) repairBookIntegrity(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	if s.pool == nil {
		writeError(w, http.StatusServiceUnavailable, "GLOSS_NOT_READY", "database unavailable")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "GLOSS_REPAIR_UNAVAILABLE", "could not start integrity repair")
		return
	}
	defer tx.Rollback(r.Context())

	repairs := []struct{ code, query string }{
		{"active_genres", "DELETE FROM book_active_genres ag WHERE ag.book_id = $1 AND NOT EXISTS (SELECT 1 FROM book_genres g WHERE g.book_id = ag.book_id AND g.genre_id = ag.genre_id)"},
		{"kind_genres", "DELETE FROM book_kind_genres kg USING book_kinds k WHERE k.book_kind_id = kg.kind_id AND k.book_id = $1 AND NOT EXISTS (SELECT 1 FROM book_genres g WHERE g.book_id = k.book_id AND g.genre_id = kg.genre_id)"},
		{"entity_attributes", "DELETE FROM entity_attribute_values v USING glossary_entities e WHERE e.entity_id = v.entity_id AND e.book_id = $1 AND e.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM book_attributes a WHERE a.attr_id = v.attr_def_id AND a.book_id = e.book_id AND a.kind_id = e.kind_id)"},
		{"kind_facets", "UPDATE glossary_entities e SET kind_labels = ARRAY(SELECT facet_id FROM unnest(COALESCE(e.kind_labels, '{}'::uuid[])) facet_id JOIN book_kinds k ON k.book_kind_id = facet_id AND k.book_id = e.book_id) WHERE e.book_id = $1 AND e.deleted_at IS NULL AND EXISTS (SELECT 1 FROM unnest(COALESCE(e.kind_labels, '{}'::uuid[])) facet_id LEFT JOIN book_kinds k ON k.book_kind_id = facet_id AND k.book_id = e.book_id WHERE k.book_kind_id IS NULL)"},
	}
	fixed := make([]string, 0, len(repairs))
	for _, repair := range repairs {
		tag, err := tx.Exec(r.Context(), repair.query, bookID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_REPAIR_FAILED", "integrity repair failed for "+repair.code)
			return
		}
		if tag.RowsAffected() > 0 {
			fixed = append(fixed, repair.code)
		}
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_REPAIR_FAILED", "could not commit integrity repair")
		return
	}
	writeJSON(w, http.StatusOK, bookIntegrityRepairResponse{BookID: bookID, FixedCodes: fixed, FixedCount: len(fixed), CheckedAt: time.Now().UTC()})
}
