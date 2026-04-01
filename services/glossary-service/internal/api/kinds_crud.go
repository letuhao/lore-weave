package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/glossary-service/internal/domain"
)

// createKind handles POST /v1/glossary/kinds
func (s *Server) createKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var in struct {
		Code      string   `json:"code"`
		Name      string   `json:"name"`
		Icon      string   `json:"icon"`
		Color     string   `json:"color"`
		GenreTags []string `json:"genre_tags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Code == "" || in.Name == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "code and name are required")
		return
	}
	if in.Icon == "" {
		in.Icon = "📝"
	}
	if in.Color == "" {
		in.Color = "#6366f1"
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{"universal"}
	}

	var kindID string
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO entity_kinds(code, name, icon, color, is_default, is_hidden, sort_order, genre_tags)
		VALUES ($1,$2,$3,$4,false,false,
			COALESCE((SELECT MAX(sort_order)+1 FROM entity_kinds),1),
			$5)
		RETURNING kind_id`,
		in.Code, in.Name, in.Icon, in.Color, in.GenreTags,
	).Scan(&kindID)
	if err != nil {
		writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "kind code already exists")
		return
	}

	writeJSON(w, http.StatusCreated, domain.EntityKind{
		KindID:     kindID,
		Code:       in.Code,
		Name:       in.Name,
		Icon:       in.Icon,
		Color:      in.Color,
		IsDefault:  false,
		IsHidden:   false,
		GenreTags:  in.GenreTags,
		Attributes: []domain.AttrDef{},
	})
}

// patchKind handles PATCH /v1/glossary/kinds/{kind_id}
func (s *Server) patchKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID := chi.URLParam(r, "kind_id")

	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "invalid payload")
		return
	}

	// Build dynamic SET clause
	sets := ""
	args := []any{kindID}
	i := 2
	if v, ok := in["name"]; ok {
		sets += comma(sets) + "name=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["icon"]; ok {
		sets += comma(sets) + "icon=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["color"]; ok {
		sets += comma(sets) + "color=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["is_hidden"]; ok {
		sets += comma(sets) + "is_hidden=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["genre_tags"]; ok {
		tags, _ := toStringSlice(v)
		sets += comma(sets) + "genre_tags=$" + itoa(i)
		args = append(args, tags)
		i++
	}

	if sets == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "no fields to update")
		return
	}

	tag, err := s.pool.Exec(r.Context(), "UPDATE entity_kinds SET "+sets+" WHERE kind_id=$1", args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to update kind")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "kind not found")
		return
	}

	// Return updated kind
	var k domain.EntityKind
	err = s.pool.QueryRow(r.Context(), `
		SELECT kind_id, code, name, icon, color, is_default, is_hidden, sort_order, genre_tags
		FROM entity_kinds WHERE kind_id=$1`, kindID,
	).Scan(&k.KindID, &k.Code, &k.Name, &k.Icon, &k.Color, &k.IsDefault, &k.IsHidden, &k.SortOrder, &k.GenreTags)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to read kind")
		return
	}
	k.Attributes = s.loadAttrDefs(r.Context(), kindID)
	writeJSON(w, http.StatusOK, k)
}

// deleteKind handles DELETE /v1/glossary/kinds/{kind_id}
func (s *Server) deleteKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID := chi.URLParam(r, "kind_id")

	// Check: must not be a system (default) kind
	var isDefault bool
	err := s.pool.QueryRow(r.Context(), `SELECT is_default FROM entity_kinds WHERE kind_id=$1`, kindID).Scan(&isDefault)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "kind not found")
		return
	}
	if isDefault {
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "cannot delete system kinds")
		return
	}

	// Check: must not have entities using this kind
	var entityCount int
	s.pool.QueryRow(r.Context(), `SELECT count(*) FROM glossary_entities WHERE kind_id=$1`, kindID).Scan(&entityCount)
	if entityCount > 0 {
		writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "kind has entities — delete or reassign them first")
		return
	}

	s.pool.Exec(r.Context(), `DELETE FROM entity_kinds WHERE kind_id=$1`, kindID)
	w.WriteHeader(http.StatusNoContent)
}

// createAttrDef handles POST /v1/glossary/kinds/{kind_id}/attributes
func (s *Server) createAttrDef(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID := chi.URLParam(r, "kind_id")

	var in struct {
		Code       string   `json:"code"`
		Name       string   `json:"name"`
		FieldType  string   `json:"field_type"`
		IsRequired bool     `json:"is_required"`
		SortOrder  int      `json:"sort_order"`
		Options    []string `json:"options"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Code == "" || in.Name == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "code and name are required")
		return
	}
	if in.FieldType == "" {
		in.FieldType = "text"
	}

	var attrDefID string
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO attribute_definitions(kind_id, code, name, field_type, is_required, sort_order, options)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		RETURNING attr_def_id`,
		kindID, in.Code, in.Name, in.FieldType, in.IsRequired, in.SortOrder, in.Options,
	).Scan(&attrDefID)
	if err != nil {
		writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "attribute code already exists for this kind")
		return
	}

	writeJSON(w, http.StatusCreated, domain.AttrDef{
		AttrDefID:  attrDefID,
		Code:       in.Code,
		Name:       in.Name,
		FieldType:  in.FieldType,
		IsRequired: in.IsRequired,
		SortOrder:  in.SortOrder,
		Options:    in.Options,
	})
}

// patchAttrDef handles PATCH /v1/glossary/kinds/{kind_id}/attributes/{attr_def_id}
func (s *Server) patchAttrDef(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID := chi.URLParam(r, "kind_id")
	attrDefID := chi.URLParam(r, "attr_def_id")

	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "invalid payload")
		return
	}

	sets := ""
	args := []any{attrDefID, kindID}
	i := 3
	if v, ok := in["name"]; ok {
		sets += comma(sets) + "name=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["field_type"]; ok {
		sets += comma(sets) + "field_type=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["is_required"]; ok {
		sets += comma(sets) + "is_required=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["sort_order"]; ok {
		sets += comma(sets) + "sort_order=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["options"]; ok {
		opts, _ := toStringSlice(v)
		sets += comma(sets) + "options=$" + itoa(i)
		args = append(args, opts)
		i++
	}

	if sets == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "no fields to update")
		return
	}

	tag, err := s.pool.Exec(r.Context(), "UPDATE attribute_definitions SET "+sets+" WHERE attr_def_id=$1 AND kind_id=$2", args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to update attribute")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
		return
	}

	var a domain.AttrDef
	s.pool.QueryRow(r.Context(), `
		SELECT attr_def_id, code, name, field_type, is_required, sort_order, options
		FROM attribute_definitions WHERE attr_def_id=$1`, attrDefID,
	).Scan(&a.AttrDefID, &a.Code, &a.Name, &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options)

	writeJSON(w, http.StatusOK, a)
}

// deleteAttrDef handles DELETE /v1/glossary/kinds/{kind_id}/attributes/{attr_def_id}
func (s *Server) deleteAttrDef(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID := chi.URLParam(r, "kind_id")
	attrDefID := chi.URLParam(r, "attr_def_id")

	tag, err := s.pool.Exec(r.Context(), `DELETE FROM attribute_definitions WHERE attr_def_id=$1 AND kind_id=$2`, attrDefID, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to delete attribute")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// loadAttrDefs fetches attribute definitions for a kind.
func (s *Server) loadAttrDefs(ctx context.Context, kindID string) []domain.AttrDef {
	rows, err := s.pool.Query(ctx, `
		SELECT attr_def_id, code, name, field_type, is_required, sort_order, options
		FROM attribute_definitions WHERE kind_id=$1 ORDER BY sort_order`, kindID)
	if err != nil {
		return []domain.AttrDef{}
	}
	defer rows.Close()
	attrs := make([]domain.AttrDef, 0)
	for rows.Next() {
		var a domain.AttrDef
		rows.Scan(&a.AttrDefID, &a.Code, &a.Name, &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options)
		attrs = append(attrs, a)
	}
	return attrs
}

// helpers

func comma(s string) string {
	if s == "" {
		return ""
	}
	return ","
}

func itoa(i int) string {
	return fmt.Sprintf("%d", i)
}

func toStringSlice(v any) ([]string, bool) {
	arr, ok := v.([]any)
	if !ok {
		return nil, false
	}
	out := make([]string, 0, len(arr))
	for _, item := range arr {
		s, ok := item.(string)
		if ok {
			out = append(out, s)
		}
	}
	return out, true
}
