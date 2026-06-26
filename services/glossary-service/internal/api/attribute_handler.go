package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/glossary-service/internal/shortdesc"
	"github.com/loreweave/grantclient"
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
		       ad.attr_id, ad.code, ad.name, ad.field_type, ad.is_required, ad.sort_order
		FROM entity_attribute_values eav
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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

	// H5 optimistic concurrency (opt-in): an attribute edit bumps the parent
	// entity's `updated_at`, so the entity version is the single token covering
	// both entity-level and attribute edits. When the assistant-edit Apply sends
	// If-Match, gate on it (412 on drift). Absent ⇒ unchanged behavior.
	ifMatch := strings.TrimSpace(r.Header.Get("If-Match"))

	setClauses := []string{}
	args := []any{}
	argN := 1
	// D-GLOSSARY-MULTIROW slice 2 — the new SOURCE value when original_value is patched,
	// so the per-item child rows can be synced (verified) after the UPDATE. nil ⇒ value
	// not touched by this PATCH.
	var newSourceValue *string

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
		// MERGE/M5 (INV-8) — a human authoring a SOURCE value marks it 'verified', so a
		// later machine re-extraction's verified-clobber guard refuses to overwrite it.
		// Literal (no placeholder) so it rides both the If-Match guard-CTE and plain paths.
		setClauses = append(setClauses, "confidence = 'verified'")
		v := val
		newSourceValue = &v
	}

	ctx := r.Context()

	if len(setClauses) > 0 {
		// Transactional (parity with patchEntity): the attr UPDATE, the K3.3b
		// short_description regen, and the glossary.entity_updated event commit
		// atomically — and the before/after snapshot is captured consistently
		// with the write (no TOCTOU). Without this event, a manual attribute edit
		// (the UI's primary edit path) never reaches the staleness consumer,
		// glossary_sync→Neo4j, or learning-service (D-WIKI-W2-ATTR-EMIT).
		tx, err := s.pool.Begin(ctx)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "begin tx failed")
			return
		}
		defer tx.Rollback(ctx)

		// BEFORE snapshot (pre-edit; the subsequent UPDATE locks the row).
		beforeName, beforeKind, beforeAliases, beforeShortDesc, beforeOK :=
			loadEntityEventFields(ctx, tx, entityID)

		args = append(args, attrValueID, entityID)
		if ifMatch != "" {
			// H5: gate both writes on the entity version in-SQL (no TOCTOU). The
			// attr UPDATE and the entity bump only fire when updated_at still
			// equals the read version; otherwise 0 rows ⇒ 412 (existence already
			// confirmed by verifyAttrValueInEntity above, so it can only be drift).
			args = append(args, ifMatch)
			updateSQL := fmt.Sprintf(`
				WITH guard AS (
					SELECT updated_at FROM glossary_entities WHERE entity_id = $%d
				),
				_upd AS (
					UPDATE entity_attribute_values SET %s
					WHERE attr_value_id = $%d AND (SELECT updated_at FROM guard) = $%d::timestamptz
				)
				UPDATE glossary_entities SET updated_at = now()
				WHERE entity_id = $%d AND updated_at = $%d::timestamptz`,
				argN+1, strings.Join(setClauses, ", "), argN, argN+2, argN+1, argN+2)
			tag, err := tx.Exec(ctx, updateSQL, args...)
			if err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
				return
			}
			if tag.RowsAffected() == 0 {
				writeError(w, http.StatusPreconditionFailed, "GLOSS_VERSION_CONFLICT",
					"entity changed since it was read; re-open and try again")
				return
			}
		} else {
			// Single CTE keeps both writes atomic — no partial-update window.
			updateSQL := fmt.Sprintf(`
				WITH _upd AS (
					UPDATE entity_attribute_values SET %s WHERE attr_value_id = $%d
				)
				UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $%d`,
				strings.Join(setClauses, ", "), argN, argN+1)
			if _, err := tx.Exec(ctx, updateSQL, args...); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
				return
			}
		}

		// D-GLOSSARY-MULTIROW slice 2 — sync the per-item child rows for a LIST value
		// (scalar ⇒ no-op), stamped 'verified' (a human edit). Keeps items in step with
		// the editor's original_value so per-item verify/tombstone and a later append see
		// the curated list. In-tx → atomic with the edit.
		if newSourceValue != nil {
			if err := syncListItemsByID(ctx, tx, attrValueID, *newSourceValue, "verified", nil); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "item sync failed")
				return
			}
		}

		// K3.3b auto-regen IN-TX: when the description attribute is the one being
		// patched AND short_description is still auto-generated, rebuild it from
		// the new text — so the AFTER snapshot + the event reflect it. Best-effort:
		// a regen failure is logged, never rolls back the edit.
		var attrCode string
		if err := tx.QueryRow(ctx, `
			SELECT ad.code FROM entity_attribute_values eav
			JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
			WHERE eav.attr_value_id = $1`, attrValueID).Scan(&attrCode); err != nil {
			slog.Warn("patch-attr: attr code lookup failed (non-fatal)",
				"attr_value_id", attrValueID.String(), "error", err.Error())
		}
		if attrCode == "description" {
			if err := s.regenerateAutoShortDescription(ctx, tx, entityID); err != nil {
				slog.Warn("regenerate short_description failed",
					"entity_id", entityID.String(), "error", err.Error())
			}
		}
		// D-GLOSSARY-ST-DEDUP M3a: a name/term edit must move the app-maintained
		// dedup key with it (cached_name was just recomputed by the EAV trigger).
		if attrCode == "name" || attrCode == "term" {
			if err := refreshEntityDedupKey(ctx, tx, entityID); err != nil {
				if errors.Is(err, errDuplicateName) {
					writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_NAME",
						"an entity with this name already exists in this book")
					return
				}
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "dedup key refresh failed")
				return
			}
		}

		// AFTER snapshot + ONE transactional user-correction event (parity with
		// patchEntity). A book-owner PATCH is a user correction by construction
		// (verifyBookOwner above → actor = owner).
		afterName, afterKind, afterAliases, afterShortDesc, _ :=
			loadEntityEventFields(ctx, tx, entityID)
		var before *EntitySnapshot
		if beforeOK {
			before = &EntitySnapshot{
				Name:             beforeName,
				Kind:             beforeKind,
				Aliases:          beforeAliases,
				ShortDescription: beforeShortDesc,
			}
		}
		payload := buildEntityEventPayload(
			bookID.String(), entityID.String(),
			afterName, afterKind, afterAliases, afterShortDesc, "updated",
			"user", userID.String(), before,
		)
		if err := emitEntityUpdatedTx(ctx, tx, entityID, payload); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "outbox emit failed")
			return
		}
		if err := tx.Commit(ctx); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
			return
		}
	}

	av, err := s.scanAttrValueBasic(ctx, attrValueID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}

	writeJSON(w, http.StatusOK, av)
}

// pgxExecQuerier is the read+write interface shared by *pgxpool.Pool and
// pgx.Tx, so a helper can run either standalone (post-commit, on the pool) or
// enlisted in an open transaction (so its writes commit atomically with the
// caller's edit).
type pgxExecQuerier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
}

// regenerateAutoShortDescription recomputes short_description from the
// current name/description/kind and writes it back — but only if the
// entity's short_description_auto flag is still true. Used by the
// patchAttributeValue hook so editing a description keeps the auto
// summary in sync. `q` is the pool (post-commit callers) or the open tx
// (patchAttributeValue, so the regenerated summary lands in the SAME tx as the
// edit and is captured by the entity_updated before/after snapshot).
func (s *Server) regenerateAutoShortDescription(ctx context.Context, q pgxExecQuerier, entityID uuid.UUID) error {
	var (
		name     string
		desc     string
		kindName string
		auto     bool
	)
	err := q.QueryRow(ctx, `
		SELECT
		  COALESCE(e.cached_name, ''),
		  COALESCE((
		    SELECT av.original_value
		    FROM entity_attribute_values av
		    JOIN book_attributes ad ON ad.attr_id = av.attr_def_id
		    WHERE av.entity_id = e.entity_id AND ad.code = 'description'
		    LIMIT 1
		  ), ''),
		  ek.name,
		  e.short_description_auto
		FROM glossary_entities e
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
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
	// clobber a just-set manual value. T2-close-7 / P-K2a-02 also adds
	// `short_description IS DISTINCT FROM $1` — when the regenerated
	// summary equals the one already persisted (e.g. whitespace-only
	// description edit, no name change), the UPDATE affects zero rows
	// and the self-trigger does not fire a second recalculate_entity_snapshot
	// on top of the eav-trigger's one. Reduces the common description-PATCH
	// path from 3 recalcs down to 1 (when short_description is unchanged)
	// or 2 (when it legitimately changed).
	_, err = q.Exec(ctx, `
		UPDATE glossary_entities
		SET short_description = $1
		WHERE entity_id = $2
		  AND short_description_auto = true
		  AND short_description IS DISTINCT FROM $1`,
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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
	// M6b: propagate target-language-specific staleness to translation-service.
	s.emitTranslationChanged(r.Context(), bookID, entityID, tr.LanguageCode)
	// M7c-3: a user-verified name is a human-canonical rendering → learning gold.
	if tr.Confidence == "verified" {
		s.emitNameConfirmed(r.Context(), bookID, entityID, tr.LanguageCode, tr.Value, userID.String())
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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
	// M6b: propagate target-language-specific staleness to translation-service.
	s.emitTranslationChanged(ctx, bookID, entityID, tr.LanguageCode)
	// M7c-3: capture the verify ACTION (confidence set to 'verified' in this patch)
	// as a human-canonical name confirmation → learning gold.
	if _, hadConf := in["confidence"]; hadConf && tr.Confidence == "verified" {
		s.emitNameConfirmed(ctx, bookID, entityID, tr.LanguageCode, tr.Value, userID.String())
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}
	if !s.verifyAttrValueInEntity(w, r.Context(), attrValueID, entityID) {
		return
	}

	// RETURNING language_code so M6b can emit a per-language staleness event
	// AFTER the row is gone (ErrNoRows ⇒ nothing deleted ⇒ 404, no emit).
	var deletedLang string
	err := s.pool.QueryRow(r.Context(),
		`DELETE FROM attribute_translations WHERE translation_id=$1 AND attr_value_id=$2
		 RETURNING language_code`,
		translationID, attrValueID).Scan(&deletedLang)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "translation not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	// M6b: propagate target-language-specific staleness to translation-service.
	s.emitTranslationChanged(r.Context(), bookID, entityID, deletedLang)
	w.WriteHeader(http.StatusNoContent)
}
