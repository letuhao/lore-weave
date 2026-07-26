package api

// KG-ML M5 (C9 / DD4) — internal batch read of localized entity display names.
//
// The knowledge-service KG graph-view / edge-timeline carries `glossary_entity_id`
// on each node but only the canonical (source-language) name. For a reader whose
// language differs from the source, the KG must show the entity's name in the
// reader's language. The entity name IS the `name`/`term` attribute value; its
// per-language translation already lives in `attribute_translations` (populated by
// the existing translate pipeline, idempotent on `(attr_value_id, language_code)`,
// never overwriting `verified`). This endpoint is the READ knowledge joins on:
// given a set of entity ids + a language, return each entity's display name
// resolved to that language (translation when present, else the canonical value).
//
// Glossary-locked: glossary owns entity names (the two-layer SSOT pattern), so the
// localized name resolves HERE, not by knowledge re-deriving it. Internal-token
// gated; book-scoped (an id not in this book is silently dropped — soft-absent,
// no cross-book existence oracle).

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

type entityDisplayNamesRequest struct {
	Language  string   `json:"language"`
	EntityIDs []string `json:"entity_ids"`
}

type entityDisplayNameItem struct {
	EntityID    string `json:"entity_id"`
	DisplayName string `json:"display_name"`
	// Translated is true when a non-empty translation existed in the requested
	// language; false means DisplayName fell back to the canonical value (the
	// FE can render an explicit source-fallback marker — AC1).
	Translated bool `json:"translated"`
}

type entityDisplayNamesResponse struct {
	Language string                  `json:"language"`
	Items    []entityDisplayNameItem `json:"items"`
}

// internalEntityDisplayNames — POST /internal/books/{book_id}/entity-display-names
//
//	body: { "language": "vi", "entity_ids": ["…", …] }
//	→     { "language": "vi", "items": [{entity_id, display_name, translated}] }
func (s *Server) internalEntityDisplayNames(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}

	var req entityDisplayNamesRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}
	lang := strings.TrimSpace(req.Language)
	if lang == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "language is required")
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
		writeJSON(w, http.StatusOK, entityDisplayNamesResponse{Language: lang, Items: []entityDisplayNameItem{}})
		return
	}

	// One round-trip: resolve each entity's name/term value to `lang`. The
	// correlated subquery mirrors listEntities' display-language resolution
	// (COALESCE(translation, original)); `translated` reports whether a non-empty
	// translation actually existed so the caller can mark a source-fallback.
	const q = `
		SELECT e.entity_id,
			COALESCE((
				SELECT COALESCE(NULLIF(at.value, ''), eav.original_value)
				FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
					AND at.language_code = $2
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '') AS display_name,
			(
				SELECT NULLIF(at.value, '')
				FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
					AND at.language_code = $2
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			) IS NOT NULL AS translated
		FROM glossary_entities e
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		  AND e.entity_id = ANY($3::uuid[])`

	rows, err := s.pool.Query(r.Context(), q, bookID, lang, ids)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "display-names query failed")
		return
	}
	defer rows.Close()

	items := []entityDisplayNameItem{}
	for rows.Next() {
		var it entityDisplayNameItem
		if err := rows.Scan(&it.EntityID, &it.DisplayName, &it.Translated); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "display-names scan failed")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "display-names rows error")
		return
	}

	writeJSON(w, http.StatusOK, entityDisplayNamesResponse{Language: lang, Items: items})
}
