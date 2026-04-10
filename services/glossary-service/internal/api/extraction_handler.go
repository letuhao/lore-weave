package api

import (
	"net/http"
)

// getExtractionProfile auto-resolves entity kinds + attributes for extraction
// based on the book's genre groups. Returns the full kinds metadata so the
// frontend can render the extraction profile dialog.
//
// Two routes share this handler:
//   - Public:   GET /v1/glossary/books/{book_id}/extraction-profile  (JWT auth)
//   - Internal: GET /internal/books/{book_id}/extraction-profile     (service token)
func (s *Server) getExtractionProfile(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	ctx := r.Context()

	// 1. Fetch the book's genre names from genre_groups table
	rows, err := s.pool.Query(ctx, `SELECT name FROM genre_groups WHERE book_id=$1 ORDER BY sort_order`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch genres")
		return
	}
	var bookGenres []string
	for rows.Next() {
		var g string
		if err := rows.Scan(&g); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan genre")
			return
		}
		bookGenres = append(bookGenres, g)
	}
	rows.Close()

	// 2. Fetch all entity kinds with their attributes, apply genre filtering
	//
	// Resolution rules from design doc §4.2:
	//   - Include system kinds where genre_tags overlap with book's genres
	//   - Always include system kinds with genre_tags containing 'universal'
	//   - Always include user-created kinds (is_default = false)
	//   - Exclude kinds where is_hidden = true
	kindRows, err := s.pool.Query(ctx, `
		SELECT kind_id, code, name, icon, is_default, genre_tags
		FROM entity_kinds
		WHERE is_hidden = false
		ORDER BY sort_order, name
	`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch kinds")
		return
	}
	defer kindRows.Close()

	type attrOut struct {
		Code           string  `json:"code"`
		Name           string  `json:"name"`
		FieldType      string  `json:"field_type"`
		Description    *string `json:"description"`
		AutoFillPrompt *string `json:"auto_fill_prompt"`
		IsRequired     bool    `json:"is_required"`
		AutoSelected   bool    `json:"auto_selected"`
	}
	type kindOut struct {
		KindID       string    `json:"kind_id"`
		Code         string    `json:"code"`
		Name         string    `json:"name"`
		Icon         string    `json:"icon"`
		AutoSelected bool      `json:"auto_selected"`
		Attributes   []attrOut `json:"attributes"`
	}

	var kinds []kindOut
	for kindRows.Next() {
		var kindID, code, name, icon string
		var isDefault bool
		var kindGenreTags []string
		if err := kindRows.Scan(&kindID, &code, &name, &icon, &isDefault, &kindGenreTags); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan kind")
			return
		}

		// Determine if this kind is auto-selected
		autoSelected := false
		if !isDefault {
			// User-created kinds are always included
			autoSelected = true
		} else {
			// System kind: check genre overlap or universal
			autoSelected = tagsOverlap(kindGenreTags, bookGenres) || containsTag(kindGenreTags, "universal")
		}

		// Fetch attributes for this kind
		attrRows, err := s.pool.Query(ctx, `
			SELECT code, name, field_type, description, auto_fill_prompt,
			       is_required, is_active, genre_tags
			FROM attribute_definitions
			WHERE kind_id = $1
			ORDER BY sort_order, name
		`, kindID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch attributes")
			return
		}

		var attrs []attrOut
		for attrRows.Next() {
			var a attrOut
			var isActive bool
			var attrGenreTags []string
			if err := attrRows.Scan(&a.Code, &a.Name, &a.FieldType, &a.Description,
				&a.AutoFillPrompt, &a.IsRequired, &isActive, &attrGenreTags); err != nil {
				attrRows.Close()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan attribute")
				return
			}

			// Determine auto_selected for this attribute:
			//   - is_required → always selected
			//   - !is_active → never selected
			//   - user-created kind → all active attrs selected (no genre filtering)
			//   - system kind → genre_tags empty OR overlaps with book's genres
			if !isActive {
				a.AutoSelected = false
			} else if a.IsRequired {
				a.AutoSelected = true
			} else if !isDefault {
				// User-created kind: all active attrs are auto-selected
				a.AutoSelected = true
			} else {
				a.AutoSelected = len(attrGenreTags) == 0 || tagsOverlap(attrGenreTags, bookGenres)
			}
			attrs = append(attrs, a)
		}
		attrRows.Close()

		if attrs == nil {
			attrs = []attrOut{}
		}
		kinds = append(kinds, kindOut{
			KindID:       kindID,
			Code:         code,
			Name:         name,
			Icon:         icon,
			AutoSelected: autoSelected,
			Attributes:   attrs,
		})
	}

	if kinds == nil {
		kinds = []kindOut{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"kinds":         kinds,
		"saved_profile": nil, // saved_profile lives on books table (book-service); frontend has it from GET /books/{id}
	})
}

// internalExtractionProfile is an alias for the same handler, used on the internal route.
func (s *Server) internalExtractionProfile(w http.ResponseWriter, r *http.Request) {
	s.getExtractionProfile(w, r)
}

// ── helpers ─────────────────────────────────────────────────────────────────

// tagsOverlap returns true if any element in a appears in b (case-sensitive).
func tagsOverlap(a, b []string) bool {
	set := make(map[string]struct{}, len(b))
	for _, v := range b {
		set[v] = struct{}{}
	}
	for _, v := range a {
		if _, ok := set[v]; ok {
			return true
		}
	}
	return false
}

// containsTag returns true if tags contains the given tag.
func containsTag(tags []string, tag string) bool {
	for _, t := range tags {
		if t == tag {
			return true
		}
	}
	return false
}

