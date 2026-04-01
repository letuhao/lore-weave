package api

import (
	"net/http"

	"github.com/loreweave/glossary-service/internal/domain"
)

// kindRow is the DB-joined shape returned from listKinds.
type kindRow struct {
	KindID    string
	Code      string
	Name      string
	Icon      string
	Color     string
	IsDefault bool
	IsHidden  bool
	SortOrder int
	GenreTags []string
}

type attrRow struct {
	AttrDefID  string
	Code       string
	Name       string
	FieldType  string
	IsRequired bool
	IsSystem   bool
	SortOrder  int
}

// listKinds handles GET /v1/glossary/kinds.
// Requires Bearer JWT (401 if absent or invalid).
func (s *Server) listKinds(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	ctx := r.Context()

	// Fetch all visible kinds ordered by sort_order
	kindRows, err := s.pool.Query(ctx, `
		SELECT kind_id, code, name, icon, color, is_default, is_hidden, sort_order, genre_tags
		FROM entity_kinds
		WHERE is_hidden = false
		ORDER BY sort_order`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query kinds")
		return
	}
	defer kindRows.Close()

	var kinds []kindRow
	for kindRows.Next() {
		var k kindRow
		if err := kindRows.Scan(&k.KindID, &k.Code, &k.Name, &k.Icon, &k.Color,
			&k.IsDefault, &k.IsHidden, &k.SortOrder, &k.GenreTags); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan error")
			return
		}
		kinds = append(kinds, k)
	}
	if err := kindRows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	// Fetch all attribute definitions in one query
	attrRowsQ, err := s.pool.Query(ctx, `
		SELECT ad.attr_def_id, ad.kind_id, ad.code, ad.name, ad.field_type, ad.is_required, ad.is_system, ad.sort_order
		FROM attribute_definitions ad
		ORDER BY ad.kind_id, ad.sort_order`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query attrs")
		return
	}
	defer attrRowsQ.Close()

	// Group attr rows by kind_id
	attrsByKind := make(map[string][]attrRow)
	for attrRowsQ.Next() {
		var kindID string
		var a attrRow
		if err := attrRowsQ.Scan(&a.AttrDefID, &kindID, &a.Code, &a.Name,
			&a.FieldType, &a.IsRequired, &a.IsSystem, &a.SortOrder); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan attr error")
			return
		}
		attrsByKind[kindID] = append(attrsByKind[kindID], a)
	}
	if err := attrRowsQ.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr rows error")
		return
	}

	// Assemble response
	out := make([]domain.EntityKind, 0, len(kinds))
	for _, k := range kinds {
		attrs := make([]domain.AttrDef, 0, len(attrsByKind[k.KindID]))
		for _, a := range attrsByKind[k.KindID] {
			attrs = append(attrs, domain.AttrDef{
				AttrDefID:  a.AttrDefID,
				Code:       a.Code,
				Name:       a.Name,
				FieldType:  a.FieldType,
				IsRequired: a.IsRequired,
				IsSystem:   a.IsSystem,
				SortOrder:  a.SortOrder,
			})
		}
		out = append(out, domain.EntityKind{
			KindID:     k.KindID,
			Code:       k.Code,
			Name:       k.Name,
			Icon:       k.Icon,
			Color:      k.Color,
			IsDefault:  k.IsDefault,
			IsHidden:   k.IsHidden,
			SortOrder:  k.SortOrder,
			GenreTags:  k.GenreTags,
			Attributes: attrs,
		})
	}

	writeJSON(w, http.StatusOK, out)
}
