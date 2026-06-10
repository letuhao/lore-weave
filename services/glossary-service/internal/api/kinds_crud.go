package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/glossary-service/internal/domain"
)

// kindCreateParams is the create-spec for a new kind — shared by the manual /v1
// handler and the Tier-S confirm path (P4). Captured inside the confirm token so
// the confirm step creates exactly what was proposed.
type kindCreateParams struct {
	Code        string   `json:"code"`
	Name        string   `json:"name"`
	Description *string  `json:"description"`
	Icon        string   `json:"icon"`
	Color       string   `json:"color"`
	GenreTags   []string `json:"genre_tags"`
}

// createKindFromParams inserts a kind + its seed 'name' attribute in one tx and
// returns the created kind. A duplicate code surfaces as a unique-violation
// (isUniqueViolation) so callers can map it to 409. Shared core — the manual
// handler and the confirm endpoint both call it (one write path, one set of
// triggers).
func (s *Server) createKindFromParams(ctx context.Context, in kindCreateParams) (domain.EntityKind, error) {
	// SCHEMA-LOW1: defense-in-depth — both callers (manual handler + the Tier-S
	// confirm path) validate upstream, but the core must not create an unnamed
	// kind if a future caller forgets.
	if strings.TrimSpace(in.Code) == "" || strings.TrimSpace(in.Name) == "" {
		return domain.EntityKind{}, errors.New("code and name are required")
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

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.EntityKind{}, err
	}
	defer tx.Rollback(ctx)

	var kindID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO entity_kinds(code, name, description, icon, color, is_default, is_hidden, sort_order, genre_tags)
		VALUES ($1,$2,$3,$4,$5,false,false,
			COALESCE((SELECT MAX(sort_order)+1 FROM entity_kinds),1),
			$6)
		RETURNING kind_id`,
		in.Code, in.Name, in.Description, in.Icon, in.Color, in.GenreTags,
	).Scan(&kindID); err != nil {
		return domain.EntityKind{}, err
	}

	// Seed a system 'name' display attribute so the kind is name-capable from creation.
	// display_name resolves from a 'name'/'term' attribute (entity_handler.go); a kind
	// with neither — the prior behaviour for every API/UI-created kind — leaves its
	// entities with no display name, including entities reassigned here out of the
	// unknown bucket (their name would be dropped in the kind re-key).
	// Insert only base attribute_definitions columns (present since the initial
	// schema); is_active / genre_tags / auto_fill_prompt are added by later
	// migrations with defaults, so omitting them is migration-order-independent.
	nameAttr := domain.AttrDef{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, IsActive: true, SortOrder: 0, GenreTags: []string{}}
	if err := tx.QueryRow(ctx, `
		INSERT INTO attribute_definitions(kind_id, code, name, field_type, is_required, is_system, sort_order)
		VALUES ($1,'name','Name','text',true,true,0)
		RETURNING attr_def_id`,
		kindID,
	).Scan(&nameAttr.AttrDefID); err != nil {
		return domain.EntityKind{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.EntityKind{}, err
	}

	return domain.EntityKind{
		KindID:      kindID,
		Code:        in.Code,
		Name:        in.Name,
		Description: in.Description,
		Icon:        in.Icon,
		Color:       in.Color,
		IsDefault:   false,
		IsHidden:    false,
		GenreTags:   in.GenreTags,
		Attributes:  []domain.AttrDef{nameAttr},
	}, nil
}

// createKind handles POST /v1/glossary/kinds
func (s *Server) createKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var in kindCreateParams
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Code == "" || in.Name == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "code and name are required")
		return
	}
	k, err := s.createKindFromParams(r.Context(), in)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "kind code already exists")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create kind")
		return
	}
	writeJSON(w, http.StatusCreated, k)
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
	if v, ok := in["description"]; ok {
		sets += comma(sets) + "description=$" + itoa(i)
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
		SELECT kind_id, code, name, description, icon, color, is_default, is_hidden, sort_order, genre_tags,
			COALESCE((SELECT count(*) FROM glossary_entities ge WHERE ge.kind_id = ek.kind_id AND ge.deleted_at IS NULL), 0)
		FROM entity_kinds ek WHERE kind_id=$1`, kindID,
	).Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.IsDefault, &k.IsHidden, &k.SortOrder, &k.GenreTags, &k.EntityCount)
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

	// Check: must not have ACTIVE entities using this kind. Soft-deleted entities
	// (recycle bin) must NOT block — but the glossary_entities.kind_id FK has no
	// ON DELETE CASCADE, so leftover soft-deleted rows would otherwise FK-block the
	// kind delete with a confusing "has entities" 409 on a kind the UI shows as
	// empty (listKinds counts only deleted_at IS NULL). Purge them in the delete tx
	// (their attr values / evidences / enrichments cascade via ON DELETE CASCADE).
	var activeCount int
	if err := s.pool.QueryRow(r.Context(),
		`SELECT count(*) FROM glossary_entities WHERE kind_id=$1 AND deleted_at IS NULL`, kindID,
	).Scan(&activeCount); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity count failed")
		return
	}
	if activeCount > 0 {
		writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "kind has entities — delete or reassign them first")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context())

	// Bug-2 fix: wiki_articles is a product table; the entity FK is now RESTRICT
	// (no silent cascade). Explicitly delete the articles of the soft-deleted
	// entities being purged — emitting wiki.deleted per article (observable) and
	// surfacing a count — BEFORE deleting the entities (else RESTRICT FK-blocks).
	type delArt struct{ articleID, entityID, bookID uuid.UUID }
	var deletedArts []delArt
	artRows, err := tx.Query(r.Context(), `
		SELECT wa.article_id, wa.entity_id, wa.book_id
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		WHERE ge.kind_id=$1 AND ge.deleted_at IS NOT NULL`, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "gather wiki articles failed")
		return
	}
	for artRows.Next() {
		var a delArt
		if err := artRows.Scan(&a.articleID, &a.entityID, &a.bookID); err != nil {
			artRows.Close()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan wiki articles failed")
			return
		}
		deletedArts = append(deletedArts, a)
	}
	artRows.Close()
	if err := artRows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "gather wiki articles failed")
		return
	}
	exec := func(ctx context.Context, sql string, args ...any) error {
		_, e := tx.Exec(ctx, sql, args...)
		return e
	}
	for _, a := range deletedArts {
		// wiki_revisions + wiki_suggestions cascade off article_id (intended; wiki-internal).
		if _, err := tx.Exec(r.Context(), `DELETE FROM wiki_articles WHERE article_id=$1`, a.articleID); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete wiki article failed")
			return
		}
		if err := insertWikiDeletedOutboxEvent(r.Context(), exec, a.articleID, wikiDeletedPayload{
			BookID:    a.bookID.String(),
			ArticleID: a.articleID.String(),
			EntityID:  a.entityID.String(),
			Reason:    "kind_deleted",
			EmittedAt: time.Now().UTC().Format(time.RFC3339),
		}); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "emit wiki.deleted failed")
			return
		}
	}

	if _, err := tx.Exec(r.Context(),
		`DELETE FROM glossary_entities WHERE kind_id=$1 AND deleted_at IS NOT NULL`, kindID,
	); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "purge soft-deleted entities failed")
		return
	}
	// entity_kinds → attribute_definitions + entity_kind_aliases both cascade.
	if _, err := tx.Exec(r.Context(),
		`DELETE FROM entity_kinds WHERE kind_id=$1`, kindID,
	); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete kind failed")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx commit failed")
		return
	}
	// Bug-2: surface the count of destroyed articles (was 204 No Content — silent).
	writeJSON(w, http.StatusOK, map[string]any{"deleted_wiki_articles": len(deletedArts)})
}

// attrCreateParams is the create-spec for a new attribute definition — shared by
// the manual /v1 handler and the Tier-S confirm path (P4). KindID is resolved at
// propose time and carried inside the confirm token.
type attrCreateParams struct {
	KindID          string   `json:"kind_id"`
	Code            string   `json:"code"`
	Name            string   `json:"name"`
	Description     *string  `json:"description"`
	FieldType       string   `json:"field_type"`
	IsRequired      bool     `json:"is_required"`
	SortOrder       int      `json:"sort_order"`
	Options         []string `json:"options"`
	GenreTags       []string `json:"genre_tags"`
	AutoFillPrompt  *string  `json:"auto_fill_prompt"`
	TranslationHint *string  `json:"translation_hint"`
}

// createAttrDefFromParams inserts an attribute definition under in.KindID and
// returns it. A duplicate (kind, code) surfaces as a unique-violation. Shared
// core for the manual handler + the confirm endpoint.
func (s *Server) createAttrDefFromParams(ctx context.Context, in attrCreateParams) (domain.AttrDef, error) {
	// SCHEMA-LOW1: defense-in-depth code/name guard (see createKindFromParams).
	if strings.TrimSpace(in.Code) == "" || strings.TrimSpace(in.Name) == "" {
		return domain.AttrDef{}, errors.New("code and name are required")
	}
	if in.FieldType == "" {
		in.FieldType = "text"
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{}
	}
	var attrDefID string
	err := s.pool.QueryRow(ctx, `
		INSERT INTO attribute_definitions(kind_id, code, name, description, field_type, is_required, sort_order, options, genre_tags, auto_fill_prompt, translation_hint)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
		RETURNING attr_def_id`,
		in.KindID, in.Code, in.Name, in.Description, in.FieldType, in.IsRequired, in.SortOrder, in.Options, in.GenreTags, in.AutoFillPrompt, in.TranslationHint,
	).Scan(&attrDefID)
	if err != nil {
		return domain.AttrDef{}, err
	}
	return domain.AttrDef{
		AttrDefID:       attrDefID,
		Code:            in.Code,
		Name:            in.Name,
		Description:     in.Description,
		FieldType:       in.FieldType,
		IsRequired:      in.IsRequired,
		IsActive:        true,
		SortOrder:       in.SortOrder,
		Options:         in.Options,
		GenreTags:       in.GenreTags,
		AutoFillPrompt:  in.AutoFillPrompt,
		TranslationHint: in.TranslationHint,
	}, nil
}

// createAttrDef handles POST /v1/glossary/kinds/{kind_id}/attributes
func (s *Server) createAttrDef(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var in attrCreateParams
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Code == "" || in.Name == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "code and name are required")
		return
	}
	in.KindID = chi.URLParam(r, "kind_id")
	a, err := s.createAttrDefFromParams(r.Context(), in)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "attribute code already exists for this kind")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create attribute")
		return
	}
	writeJSON(w, http.StatusCreated, a)
}

// isUniqueViolation reports whether err is a Postgres unique-constraint violation
// (SQLSTATE 23505) — used to map a duplicate kind/attribute code to 409.
func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}

// isForeignKeyViolation reports whether err is a Postgres FK violation (23503) —
// e.g. confirming a new attribute whose kind was deleted between propose and
// confirm — so the caller can return a clean 422 instead of a 500.
func isForeignKeyViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23503"
}

// validFieldTypes is the allowed attribute field_type set (mirrors patchAttrDef).
var validFieldTypes = map[string]bool{
	"text": true, "textarea": true, "select": true, "number": true,
	"date": true, "tags": true, "url": true, "boolean": true,
}

func isValidFieldType(ft string) bool { return validFieldTypes[ft] }

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

	// Validation
	if v, ok := in["name"]; ok {
		s, _ := v.(string)
		if s == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "name must not be empty")
			return
		}
	}
	if v, ok := in["field_type"]; ok {
		s, _ := v.(string)
		switch s {
		case "text", "textarea", "select", "number", "date", "tags", "url", "boolean":
			// valid
		default:
			writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "invalid field_type: "+s)
			return
		}
	}

	sets := ""
	args := []any{attrDefID, kindID}
	i := 3
	if v, ok := in["name"]; ok {
		sets += comma(sets) + "name=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["description"]; ok {
		sets += comma(sets) + "description=$" + itoa(i)
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
	if v, ok := in["is_active"]; ok {
		sets += comma(sets) + "is_active=$" + itoa(i)
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
	if v, ok := in["genre_tags"]; ok {
		tags, _ := toStringSlice(v)
		if tags == nil {
			tags = []string{}
		}
		sets += comma(sets) + "genre_tags=$" + itoa(i)
		args = append(args, tags)
		i++
	}
	if v, ok := in["auto_fill_prompt"]; ok {
		sets += comma(sets) + "auto_fill_prompt=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["translation_hint"]; ok {
		sets += comma(sets) + "translation_hint=$" + itoa(i)
		args = append(args, v)
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
	err = s.pool.QueryRow(r.Context(), `
		SELECT attr_def_id, code, name, description, field_type, is_required, is_system, is_active, sort_order, options, genre_tags, auto_fill_prompt, translation_hint
		FROM attribute_definitions WHERE attr_def_id=$1 AND kind_id=$2`, attrDefID, kindID,
	).Scan(&a.AttrDefID, &a.Code, &a.Name, &a.Description, &a.FieldType, &a.IsRequired, &a.IsSystem, &a.IsActive, &a.SortOrder, &a.Options, &a.GenreTags, &a.AutoFillPrompt, &a.TranslationHint)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to re-fetch attribute")
		return
	}

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

	// Check if system attribute
	var isSystem bool
	if err := s.pool.QueryRow(r.Context(), `SELECT is_system FROM attribute_definitions WHERE attr_def_id=$1 AND kind_id=$2`, attrDefID, kindID).Scan(&isSystem); err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
		return
	}
	if isSystem {
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "cannot delete system attributes")
		return
	}

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
		SELECT attr_def_id, code, name, description, field_type, is_required, is_system, is_active, sort_order, options, genre_tags, auto_fill_prompt, translation_hint
		FROM attribute_definitions WHERE kind_id=$1 ORDER BY sort_order`, kindID)
	if err != nil {
		return []domain.AttrDef{}
	}
	defer rows.Close()
	attrs := make([]domain.AttrDef, 0)
	for rows.Next() {
		var a domain.AttrDef
		rows.Scan(&a.AttrDefID, &a.Code, &a.Name, &a.Description, &a.FieldType, &a.IsRequired, &a.IsSystem, &a.IsActive, &a.SortOrder, &a.Options, &a.GenreTags, &a.AutoFillPrompt, &a.TranslationHint)
		attrs = append(attrs, a)
	}
	return attrs
}

// reorderKinds handles PATCH /v1/glossary/kinds/reorder
func (s *Server) reorderKinds(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var in struct {
		KindIDs []string `json:"kind_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || len(in.KindIDs) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "kind_ids array is required")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to begin transaction")
		return
	}
	defer tx.Rollback(r.Context())

	for i, id := range in.KindIDs {
		tx.Exec(r.Context(), `UPDATE entity_kinds SET sort_order=$1 WHERE kind_id=$2`, i, id)
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to commit reorder")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"reordered": len(in.KindIDs)})
}

// reorderAttrDefs handles PATCH /v1/glossary/kinds/{kind_id}/attributes/reorder
func (s *Server) reorderAttrDefs(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID := chi.URLParam(r, "kind_id")

	var in struct {
		AttrDefIDs []string `json:"attr_def_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || len(in.AttrDefIDs) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "attr_def_ids array is required")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to begin transaction")
		return
	}
	defer tx.Rollback(r.Context())

	for i, id := range in.AttrDefIDs {
		tx.Exec(r.Context(), `UPDATE attribute_definitions SET sort_order=$1 WHERE attr_def_id=$2 AND kind_id=$3`, i, id, kindID)
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to commit reorder")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"reordered": len(in.AttrDefIDs)})
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
