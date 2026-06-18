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

// loadKinds returns the global kind catalog + attribute definitions (visible
// kinds only). Non-HTTP core shared by the listKinds HTTP endpoint and the
// glossary_list_kinds MCP tool. Kinds are GLOBAL (not book-scoped).
func (s *Server) loadKinds(ctx context.Context) ([]domain.EntityKind, error) {
	kindRows, err := s.pool.Query(ctx, `
		SELECT kind_id, code, name, description, icon, color, is_default, is_hidden, sort_order, genre_tags,
			COALESCE((SELECT count(*) FROM glossary_entities ge WHERE ge.kind_id = ek.kind_id AND ge.deleted_at IS NULL), 0) AS entity_count
		FROM system_kinds ek
		WHERE is_hidden = false
		ORDER BY sort_order`)
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

	attrRowsQ, err := s.pool.Query(ctx, `
		SELECT ad.attr_def_id, ad.kind_id, ad.code, ad.name, ad.description, ad.field_type, ad.is_required, ad.is_system, ad.is_active, ad.sort_order, ad.genre_tags, ad.auto_fill_prompt, ad.translation_hint
		FROM system_kind_attributes ad
		JOIN system_kinds ek ON ek.kind_id = ad.kind_id AND ek.is_hidden = false
		ORDER BY ad.kind_id, ad.sort_order`)
	if err != nil {
		return nil, fmt.Errorf("query attrs: %w", err)
	}
	defer attrRowsQ.Close()

	attrsByKind := make(map[string][]attrRow)
	for attrRowsQ.Next() {
		var kindID string
		var a attrRow
		if err := attrRowsQ.Scan(&a.AttrDefID, &kindID, &a.Code, &a.Name, &a.Description,
			&a.FieldType, &a.IsRequired, &a.IsSystem, &a.IsActive, &a.SortOrder, &a.GenreTags,
			&a.AutoFillPrompt, &a.TranslationHint); err != nil {
			return nil, fmt.Errorf("scan attr: %w", err)
		}
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
