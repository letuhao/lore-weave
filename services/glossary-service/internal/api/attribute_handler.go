package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/glossary-service/internal/shortdesc"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// verifyAttrValueInEntity checks that attr_value_id belongs to entity_id.
func (s *Server) verifyAttrValueInEntity(w http.ResponseWriter, ctx context.Context, attrValueID, entityID uuid.UUID) bool {
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM entity_attribute_values WHERE attr_value_id=$1 AND entity_id=$2)`,
		attrValueID, entityID,
	).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return false
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute value not found")
		return false
	}
	return true
}

// scanAttrValueBasic fetches one attribute value row with its attr_def, but without
// translations or evidences (callers use onRefresh to reload the full entity).
func (s *Server) scanAttrValueBasic(ctx context.Context, attrValueID uuid.UUID) (*attrValueResp, error) {
	var av attrValueResp
	err := s.pool.QueryRow(ctx, `
		SELECT eav.attr_value_id, eav.entity_id, eav.attr_def_id,
		       eav.original_language, eav.original_value,
		       ad.attr_def_id, ad.code, ad.name, ad.field_type, ad.is_required, ad.sort_order
		FROM entity_attribute_values eav
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
		WHERE eav.attr_value_id = $1`,
		attrValueID,
	).Scan(
		&av.AttrValueID, &av.EntityID, &av.AttrDefID,
		&av.OriginalLanguage, &av.OriginalValue,
		&av.AttributeDef.AttrDefID, &av.AttributeDef.Code, &av.AttributeDef.Name,
		&av.AttributeDef.FieldType, &av.AttributeDef.IsRequired, &av.AttributeDef.SortOrder,
	)
	if err != nil {
		return nil, err
	}
	av.Translations = []translationResp{}
	av.Evidences = []evidenceResp{}
	return &av, nil
}

// scanTranslation fetches a single translation row by translation_id + attr_value_id.
func (s *Server) scanTranslation(ctx context.Context, translationID, attrValueID uuid.UUID) (*translationResp, error) {
	var tr translationResp
	err := s.pool.QueryRow(ctx, `
		SELECT translation_id, attr_value_id, language_code, value, confidence, translator, updated_at
		FROM attribute_translations
		WHERE translation_id=$1 AND attr_value_id=$2`,
		translationID, attrValueID,
	).Scan(
		&tr.TranslationID, &tr.AttrValueID, &tr.LanguageCode,
		&tr.Value, &tr.Confidence, &tr.Translator, &tr.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &tr, nil
}

// ── PATCH /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}

func (s *Server) patchAttributeValue(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	attrValueID, ok := parsePathUUID(w, r, "attr_value_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}
	if !s.verifyAttrValueInEntity(w, r.Context(), attrValueID, entityID) {
		return
	}

	var in map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	setClauses := []string{}
	args := []any{}
	argN := 1

	if raw, ok := in["original_language"]; ok {
		var lang string
		if err := json.Unmarshal(raw, &lang); err != nil || lang == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid original_language")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("original_language = $%d", argN))
		args = append(args, lang)
		argN++
	}

	if raw, ok := in["original_value"]; ok {
		var val string
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid original_value")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("original_value = $%d", argN))
		args = append(args, val)
		argN++
	}

	ctx := r.Context()

	if len(setClauses) > 0 {
		args = append(args, attrValueID, entityID)
		// Single CTE keeps both writes atomic — no partial-update window.
		updateSQL := fmt.Sprintf(`
			WITH _upd AS (
				UPDATE entity_attribute_values SET %s WHERE attr_value_id = $%d
			)
			UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $%d`,
			strings.Join(setClauses, ", "), argN, argN+1)
		if _, err := s.pool.Exec(ctx, updateSQL, args...); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
	}

	av, err := s.scanAttrValueBasic(ctx, attrValueID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}

	// K3.3b auto-regen: when the description attribute is the one being
	// patched AND the entity's short_description is still auto-generated
	// (not user-overridden), rebuild short_description from the new text.
	// Failures are logged but don't fail the PATCH — regeneration is
	// best-effort.
	if av.AttributeDef.Code == "description" {
		_ = s.regenerateAutoShortDescription(ctx, entityID)
	}

	writeJSON(w, http.StatusOK, av)
}

// regenerateAutoShortDescription recomputes short_description from the
// current name/description/kind and writes it back — but only if the
// entity's short_description_auto flag is still true. Used by the
// patchAttributeValue hook so editing a description keeps the auto
// summary in sync.
func (s *Server) regenerateAutoShortDescription(ctx context.Context, entityID uuid.UUID) error {
	var (
		name     string
		desc     string
		kindName string
		auto     bool
	)
	err := s.pool.QueryRow(ctx, `
		SELECT
		  COALESCE(e.cached_name, ''),
		  COALESCE((
		    SELECT av.original_value
		    FROM entity_attribute_values av
		    JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
		    WHERE av.entity_id = e.entity_id AND ad.code = 'description'
		    LIMIT 1
		  ), ''),
		  ek.name,
		  e.short_description_auto
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		WHERE e.entity_id = $1`, entityID,
	).Scan(&name, &desc, &kindName, &auto)
	if err != nil {
		return err
	}
	if !auto {
		return nil
	}
	sd := shortdesc.Generate(name, desc, kindName, shortdesc.DefaultMaxChars)
	if sd == "" {
		return nil
	}
	// Guard with short_description_auto so a race with a user PATCH can't
	// clobber a just-set manual value.
	_, err = s.pool.Exec(ctx, `
		UPDATE glossary_entities
		SET short_description = $1
		WHERE entity_id = $2 AND short_description_auto = true`,
		sd, entityID)
	return err
}

// ── POST /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/translations

func (s *Server) createTranslation(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	attrValueID, ok := parsePathUUID(w, r, "attr_value_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}
	if !s.verifyAttrValueInEntity(w, r.Context(), attrValueID, entityID) {
		return
	}

	var in struct {
		LanguageCode string  `json:"language_code"`
		Value        string  `json:"value"`
		Confidence   string  `json:"confidence"`
		Translator   *string `json:"translator"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.LanguageCode == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "language_code is required")
		return
	}
	switch in.Confidence {
	case "verified", "draft", "machine":
	case "":
		in.Confidence = "draft"
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"confidence must be verified, draft, or machine")
		return
	}

	var tr translationResp
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO attribute_translations(attr_value_id, language_code, value, confidence, translator)
		VALUES($1,$2,$3,$4,$5)
		RETURNING translation_id, attr_value_id, language_code, value, confidence, translator, updated_at`,
		attrValueID, in.LanguageCode, in.Value, in.Confidence, in.Translator,
	).Scan(
		&tr.TranslationID, &tr.AttrValueID, &tr.LanguageCode,
		&tr.Value, &tr.Confidence, &tr.Translator, &tr.UpdatedAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_TRANSLATION_LANGUAGE",
				"a translation for this language already exists")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}
	writeJSON(w, http.StatusCreated, tr)
}

// ── PATCH /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/translations/{translation_id}

func (s *Server) updateTranslation(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	attrValueID, ok := parsePathUUID(w, r, "attr_value_id")
	if !ok {
		return
	}
	translationID, ok := parsePathUUID(w, r, "translation_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}
	if !s.verifyAttrValueInEntity(w, r.Context(), attrValueID, entityID) {
		return
	}

	var in map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	// Always bump updated_at; append field changes if present
	setClauses := []string{"updated_at = now()"}
	args := []any{}
	argN := 1

	if raw, ok := in["value"]; ok {
		var val string
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid value")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("value = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["confidence"]; ok {
		var conf string
		if err := json.Unmarshal(raw, &conf); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid confidence")
			return
		}
		switch conf {
		case "verified", "draft", "machine":
		default:
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
				"confidence must be verified, draft, or machine")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("confidence = $%d", argN))
		args = append(args, conf)
		argN++
	}

	if raw, ok := in["translator"]; ok {
		var translator *string
		if err := json.Unmarshal(raw, &translator); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid translator")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("translator = $%d", argN))
		args = append(args, translator)
		argN++
	}

	ctx := r.Context()
	args = append(args, translationID, attrValueID)
	updateSQL := fmt.Sprintf(
		"UPDATE attribute_translations SET %s WHERE translation_id = $%d AND attr_value_id = $%d",
		strings.Join(setClauses, ", "), argN, argN+1)
	tag, err := s.pool.Exec(ctx, updateSQL, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "translation not found")
		return
	}

	tr, err := s.scanTranslation(ctx, translationID, attrValueID)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "translation not found")
		} else {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		}
		return
	}
	writeJSON(w, http.StatusOK, tr)
}

// ── DELETE /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/translations/{translation_id}

func (s *Server) deleteTranslation(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	attrValueID, ok := parsePathUUID(w, r, "attr_value_id")
	if !ok {
		return
	}
	translationID, ok := parsePathUUID(w, r, "translation_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}
	if !s.verifyAttrValueInEntity(w, r.Context(), attrValueID, entityID) {
		return
	}

	tag, err := s.pool.Exec(r.Context(),
		`DELETE FROM attribute_translations WHERE translation_id=$1 AND attr_value_id=$2`,
		translationID, attrValueID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "translation not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
