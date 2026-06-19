package api

import (
	"context"
	"fmt"
	"net/http"

	"github.com/loreweave/glossary-service/internal/domain"
)

// kindRow is the DB-joined shape returned from listKinds.
type kindRow struct {
	KindID      string
	Code        string
	Name        string
	Description *string
	Icon        string
	Color       string
	IsDefault   bool
	IsHidden    bool
	SortOrder   int
	GenreTags   []string
	EntityCount int
}

type attrRow struct {
	AttrDefID       string
	Code            string
	Name            string
	Description     *string
	FieldType       string
	IsRequired      bool
	IsSystem        bool
	IsActive        bool
	SortOrder       int
	GenreTags       []string
	AutoFillPrompt  *string
	TranslationHint *string
}

// listKinds handles GET /v1/glossary/kinds.
// Requires Bearer JWT (401 if absent or invalid).
func (s *Server) listKinds(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	out, err := s.loadKinds(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to load kinds")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

// loadKinds returns the global SYSTEM kind catalog + attribute definitions
// (visible kinds only). Non-HTTP core shared by the listKinds HTTP endpoint and the
// glossary_list_kinds MCP tool. System kinds are GLOBAL (not book-scoped).
//
// G4: genre_tags / system_kind_attributes are gone — genre membership now comes from
// the system_kind_genres link table (→ system_genres.code) and attributes from the
// per-(kind,genre) system_attributes table (the universal-genre rows are the kind's
// base attrs). entity_count counts entities for the SAME-code book kind across all
// books (the entity layer is now book-local), so a system kind still reflects usage.
func (s *Server) loadKinds(ctx context.Context) ([]domain.EntityKind, error) {
	kindRows, err := s.pool.Query(ctx, `
		SELECT ek.kind_id, ek.code, ek.name, ek.description, ek.icon, ek.color, ek.is_default, ek.is_hidden, ek.sort_order,
			COALESCE((
				SELECT array_agg(g.code ORDER BY g.sort_order)
				FROM system_kind_genres kg JOIN system_genres g ON g.genre_id = kg.genre_id
				WHERE kg.kind_id = ek.kind_id
			), '{}') AS genre_tags,
			COALESCE((
				SELECT count(*) FROM glossary_entities ge
				JOIN book_kinds bk ON bk.book_kind_id = ge.kind_id
				WHERE bk.code = ek.code AND ge.deleted_at IS NULL
			), 0) AS entity_count
		FROM system_kinds ek
		WHERE ek.is_hidden = false
		ORDER BY ek.sort_order`)
	if err != nil {
		return nil, fmt.Errorf("query kinds: %w", err)
	}
	defer kindRows.Close()

	var kinds []kindRow
	for kindRows.Next() {
		var k kindRow
		if err := kindRows.Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color,
			&k.IsDefault, &k.IsHidden, &k.SortOrder, &k.GenreTags, &k.EntityCount); err != nil {
			return nil, fmt.Errorf("scan kind: %w", err)
		}
		kinds = append(kinds, k)
	}
	if err := kindRows.Err(); err != nil {
		return nil, fmt.Errorf("kind rows: %w", err)
	}

	// Attributes from system_attributes; the genre's code rides along as the attr's
	// genre_tags so a UI can still group/badge by genre. is_system/is_active are
	// synthesised (system standards are always system + active).
	attrRowsQ, err := s.pool.Query(ctx, `
		SELECT ad.attr_id, ad.kind_id, ad.code, ad.name, ad.description, ad.field_type, ad.is_required, ad.sort_order,
			g.code AS genre_code, ad.auto_fill_prompt, ad.translation_hint
		FROM system_attributes ad
		JOIN system_kinds  ek ON ek.kind_id  = ad.kind_id AND ek.is_hidden = false
		JOIN system_genres g  ON g.genre_id   = ad.genre_id
		ORDER BY ad.kind_id, ad.sort_order`)
	if err != nil {
		return nil, fmt.Errorf("query attrs: %w", err)
	}
	defer attrRowsQ.Close()

	attrsByKind := make(map[string][]attrRow)
	for attrRowsQ.Next() {
		var kindID, genreCode string
		var a attrRow
		if err := attrRowsQ.Scan(&a.AttrDefID, &kindID, &a.Code, &a.Name, &a.Description,
			&a.FieldType, &a.IsRequired, &a.SortOrder, &genreCode,
			&a.AutoFillPrompt, &a.TranslationHint); err != nil {
			return nil, fmt.Errorf("scan attr: %w", err)
		}
		// System standards are always system-owned + active; the per-(kind,genre)
		// attribute's genre code rides along as its single-element genre_tags.
		a.IsSystem = true
		a.IsActive = true
		a.GenreTags = []string{genreCode}
		attrsByKind[kindID] = append(attrsByKind[kindID], a)
	}
	if err := attrRowsQ.Err(); err != nil {
		return nil, fmt.Errorf("attr rows: %w", err)
	}

	out := make([]domain.EntityKind, 0, len(kinds))
	for _, k := range kinds {
		attrs := make([]domain.AttrDef, 0, len(attrsByKind[k.KindID]))
		for _, a := range attrsByKind[k.KindID] {
			attrs = append(attrs, domain.AttrDef{
				AttrDefID:       a.AttrDefID,
				Code:            a.Code,
				Name:            a.Name,
				Description:     a.Description,
				FieldType:       a.FieldType,
				IsRequired:      a.IsRequired,
				IsSystem:        a.IsSystem,
				IsActive:        a.IsActive,
				SortOrder:       a.SortOrder,
				GenreTags:       a.GenreTags,
				AutoFillPrompt:  a.AutoFillPrompt,
				TranslationHint: a.TranslationHint,
			})
		}
		out = append(out, domain.EntityKind{
			KindID:      k.KindID,
			Code:        k.Code,
			Name:        k.Name,
			Description: k.Description,
			Icon:        k.Icon,
			Color:       k.Color,
			IsDefault:   k.IsDefault,
			IsHidden:    k.IsHidden,
			SortOrder:   k.SortOrder,
			GenreTags:   k.GenreTags,
			EntityCount: k.EntityCount,
			Attributes:  attrs,
		})
	}
	return out, nil
}
