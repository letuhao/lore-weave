package api

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/google/uuid"
)

type entitiesByIDsRequest struct {
	EntityIDs []string `json:"entity_ids"`
}

type entitiesByIDsResponse struct {
	Items []glossaryEntityForContext `json:"items"`
}

// internalEntitiesByIDs batch-fetches glossary entities by id in the SAME item
// shape as select-for-context (mui #4 — semantic retrieval, architecture B).
// The knowledge-service semantic selector resolves vector hits →
// glossary_entity_ids → this endpoint to enrich them with canon detail
// (cached_name/aliases/short_description/kind_code). Order is NOT significant —
// the caller re-ranks by its vector scores; tier/rank_score are left zero.
// Missing or soft-deleted ids are silently dropped (soft-absent, DI3).
//
//	POST /internal/books/{book_id}/entities/by-ids
//	body: { "entity_ids": ["…", …] }  →  { "items": [glossaryEntityForContext] }
func (s *Server) internalEntitiesByIDs(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}

	var req entitiesByIDsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}

	// Parse + drop malformed ids (soft-absent). Empty → empty result, not error.
	ids := make([]uuid.UUID, 0, len(req.EntityIDs))
	for _, raw := range req.EntityIDs {
		if id, err := uuid.Parse(raw); err == nil {
			ids = append(ids, id)
		}
	}
	if len(ids) == 0 {
		writeJSON(w, http.StatusOK, entitiesByIDsResponse{Items: []glossaryEntityForContext{}})
		return
	}

	query := fmt.Sprintf(`
		SELECT %s
		FROM glossary_entities e
		JOIN system_kinds ek ON ek.kind_id = e.kind_id
		WHERE e.book_id = $1
		  AND e.deleted_at IS NULL
		  AND e.entity_id = ANY($2::uuid[])`, selectCols)
	rows, err := s.pool.Query(r.Context(), query, bookID, ids)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "by-ids query failed")
		return
	}
	defer rows.Close()

	items := []glossaryEntityForContext{}
	for rows.Next() {
		row, err := s.scanContextRow(rows, nil)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "by-ids scan failed")
			return
		}
		items = append(items, row)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "by-ids rows error")
		return
	}

	writeJSON(w, http.StatusOK, entitiesByIDsResponse{Items: items})
}
