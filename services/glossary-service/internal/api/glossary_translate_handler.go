package api

// Batch glossary attribute translation — internal read/write for translation-service worker.
// Upsert semantics mirror extraction_handler.go M4d-2b (never overwrite verified).

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

type translationCandidateAttr struct {
	AttrValueID      string  `json:"attr_value_id"`
	Code             string  `json:"code"`
	FieldType        string  `json:"field_type"`
	OriginalLanguage string  `json:"original_language"`
	OriginalValue    string  `json:"original_value"`
	ExistingValue    *string `json:"existing_value,omitempty"`
	ExistingConf     *string `json:"existing_confidence,omitempty"`
}

type translationCandidateEntity struct {
	EntityID    string                     `json:"entity_id"`
	DisplayName string                     `json:"display_name"`
	KindCode    string                     `json:"kind_code"`
	Status      string                     `json:"status"`
	Attributes  []translationCandidateAttr `json:"attributes"`
}

type translationCandidatesResp struct {
	BookID         string                       `json:"book_id"`
	TargetLanguage string                       `json:"target_language"`
	Total          int                          `json:"total"`
	Limit          int                          `json:"limit"`
	Offset         int                          `json:"offset"`
	Items          []translationCandidateEntity `json:"items"`
}

// GET /internal/books/{book_id}/translation-candidates
func (s *Server) internalTranslationCandidates(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	targetLang := strings.TrimSpace(r.URL.Query().Get("target_language"))
	if targetLang == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_QUERY", "target_language is required")
		return
	}
	overwriteMode := strings.TrimSpace(r.URL.Query().Get("overwrite_mode"))
	if overwriteMode == "" {
		overwriteMode = "missing_only"
	}
	if overwriteMode != "missing_only" && overwriteMode != "refresh_machine" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_QUERY",
			"overwrite_mode must be missing_only or refresh_machine")
		return
	}

	limit := 50
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 && n <= 200 {
			limit = n
		}
	}
	offset := 0
	if raw := r.URL.Query().Get("offset"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n >= 0 {
			offset = n
		}
	}

	entityFilter := parseOptionalUUIDList(r.URL.Query().Get("entity_ids"))

	ctx := r.Context()

	// Count distinct entities matching the filter.
	countSQL := `
		SELECT COUNT(DISTINCT e.entity_id)
		FROM glossary_entities e
		JOIN entity_attribute_values eav ON eav.entity_id = e.entity_id
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		LEFT JOIN attribute_translations tr
		  ON tr.attr_value_id = eav.attr_value_id AND tr.language_code = $2
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		  AND btrim(eav.original_value) <> ''
		  AND (` + translationCandidateWhere(overwriteMode) + `)`
	countArgs := []any{bookID, targetLang}
	if len(entityFilter) > 0 {
		countSQL += ` AND e.entity_id = ANY($3)`
		countArgs = append(countArgs, entityFilter)
	}
	var total int
	if err := s.pool.QueryRow(ctx, countSQL, countArgs...).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
		return
	}

	// Page entity ids.
	entitySQL := `
		SELECT DISTINCT e.entity_id
		FROM glossary_entities e
		JOIN entity_attribute_values eav ON eav.entity_id = e.entity_id
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		LEFT JOIN attribute_translations tr
		  ON tr.attr_value_id = eav.attr_value_id AND tr.language_code = $2
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		  AND btrim(eav.original_value) <> ''
		  AND (` + translationCandidateWhere(overwriteMode) + `)`
	entityArgs := []any{bookID, targetLang}
	limitArg := 3
	if len(entityFilter) > 0 {
		entitySQL += ` AND e.entity_id = ANY($3)`
		entityArgs = append(entityArgs, entityFilter)
		limitArg = 4
	}
	entitySQL += ` ORDER BY e.entity_id LIMIT $` + strconv.Itoa(limitArg) +
		` OFFSET $` + strconv.Itoa(limitArg+1)
	entityArgs = append(entityArgs, limit, offset)

	rows, err := s.pool.Query(ctx, entitySQL, entityArgs...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	var entityIDs []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		entityIDs = append(entityIDs, id)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}

	items := make([]translationCandidateEntity, 0, len(entityIDs))
	for _, eid := range entityIDs {
		ent, err := s.loadTranslationCandidateEntity(ctx, bookID, eid, targetLang, overwriteMode)
		if err != nil {
			if err == pgx.ErrNoRows {
				continue
			}
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed: "+err.Error())
			return
		}
		if len(ent.Attributes) > 0 {
			items = append(items, *ent)
		}
	}

	writeJSON(w, http.StatusOK, translationCandidatesResp{
		BookID:         bookID.String(),
		TargetLanguage: targetLang,
		Total:          total,
		Limit:          limit,
		Offset:         offset,
		Items:          items,
	})
}

func translationCandidateWhere(overwriteMode string) string {
	if overwriteMode == "refresh_machine" {
		return `tr.translation_id IS NULL OR tr.confidence IN ('draft', 'machine')`
	}
	return `tr.translation_id IS NULL`
}

func (s *Server) loadTranslationCandidateEntity(
	ctx context.Context, bookID, entityID uuid.UUID, targetLang, overwriteMode string,
) (*translationCandidateEntity, error) {
	var ent translationCandidateEntity
	ent.EntityID = entityID.String()
	err := s.pool.QueryRow(ctx, `
		SELECT e.status, ek.code,
			COALESCE((
				SELECT eav.original_value FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '') AS display_name
		FROM glossary_entities e
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
		WHERE e.entity_id = $1 AND e.book_id = $2 AND e.deleted_at IS NULL`,
		entityID, bookID,
	).Scan(&ent.Status, &ent.KindCode, &ent.DisplayName)
	if err != nil {
		return nil, err
	}

	attrRows, err := s.pool.Query(ctx, `
		SELECT eav.attr_value_id, ad.code, ad.field_type,
		       eav.original_language, eav.original_value,
		       tr.value, tr.confidence
		FROM entity_attribute_values eav
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		LEFT JOIN attribute_translations tr
		  ON tr.attr_value_id = eav.attr_value_id AND tr.language_code = $2
		WHERE eav.entity_id = $1 AND btrim(eav.original_value) <> ''
		  AND (`+translationCandidateWhere(overwriteMode)+`)
		ORDER BY ad.sort_order`,
		entityID, targetLang,
	)
	if err != nil {
		return nil, err
	}
	defer attrRows.Close()

	for attrRows.Next() {
		var a translationCandidateAttr
		var existingVal, existingConf *string
		if err := attrRows.Scan(
			&a.AttrValueID, &a.Code, &a.FieldType,
			&a.OriginalLanguage, &a.OriginalValue,
			&existingVal, &existingConf,
		); err != nil {
			return nil, err
		}
		a.ExistingValue = existingVal
		a.ExistingConf = existingConf
		ent.Attributes = append(ent.Attributes, a)
	}
	if err := attrRows.Err(); err != nil {
		return nil, err
	}
	return &ent, nil
}

type applyTranslationItem struct {
	EntityID    string `json:"entity_id"`
	AttrValueID string `json:"attr_value_id"`
	Value       string `json:"value"`
}

type applyTranslationsReq struct {
	TargetLanguage string                 `json:"target_language"`
	Items          []applyTranslationItem `json:"items"`
}

type applyTranslationsResp struct {
	Translated      int      `json:"translated"`
	SkippedVerified int      `json:"skipped_verified"`
	SkippedEmpty    int      `json:"skipped_empty"`
	Failed          []string `json:"failed"`
}

// POST /internal/books/{book_id}/apply-translations
func (s *Server) internalApplyTranslations(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var req applyTranslationsReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	req.TargetLanguage = strings.TrimSpace(req.TargetLanguage)
	if req.TargetLanguage == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "target_language is required")
		return
	}

	ctx := r.Context()
	var resp applyTranslationsResp
	resp.Failed = []string{}
	touchedEntities := map[uuid.UUID]struct{}{}

	for _, item := range req.Items {
		value := strings.TrimSpace(item.Value)
		if value == "" {
			resp.SkippedEmpty++
			continue
		}
		attrID, err := uuid.Parse(item.AttrValueID)
		if err != nil {
			resp.Failed = append(resp.Failed, item.AttrValueID+": invalid attr_value_id")
			continue
		}
		entityID, err := uuid.Parse(item.EntityID)
		if err != nil {
			resp.Failed = append(resp.Failed, item.EntityID+": invalid entity_id")
			continue
		}
		var attrOK, entOK bool
		if err := s.pool.QueryRow(ctx,
			`SELECT EXISTS(SELECT 1 FROM entity_attribute_values WHERE attr_value_id=$1 AND entity_id=$2)`,
			attrID, entityID,
		).Scan(&attrOK); err != nil || !attrOK {
			resp.Failed = append(resp.Failed, item.AttrValueID+": attr not in entity")
			continue
		}
		if err := s.pool.QueryRow(ctx,
			`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)`,
			entityID, bookID,
		).Scan(&entOK); err != nil || !entOK {
			resp.Failed = append(resp.Failed, item.EntityID+": entity not in book")
			continue
		}

		ct, err := s.pool.Exec(ctx, `
			INSERT INTO attribute_translations (attr_value_id, language_code, value, confidence, translator)
			VALUES ($1, $2, $3, 'machine', 'glossary-translate')
			ON CONFLICT (attr_value_id, language_code) DO UPDATE
			  SET value = EXCLUDED.value, confidence = 'machine',
			      translator = EXCLUDED.translator, updated_at = now()
			  WHERE attribute_translations.confidence <> 'verified'
		`, attrID, req.TargetLanguage, value)
		if err != nil {
			resp.Failed = append(resp.Failed, item.AttrValueID+": insert failed")
			continue
		}
		if ct.RowsAffected() == 0 {
			resp.SkippedVerified++
			continue
		}
		resp.Translated++
		touchedEntities[entityID] = struct{}{}
	}

	for entityID := range touchedEntities {
		s.emitTranslationChanged(ctx, bookID, entityID, req.TargetLanguage)
	}

	writeJSON(w, http.StatusOK, resp)
}

// ── Public batch-translate surface (S4) ───────────────────────────────────────
// The internal candidates/apply handlers above are X-Internal-Token-gated (the
// translation worker). These two thin wrappers expose the SAME logic to the FE batch
// dialog on the JWT-authed /v1 path, adding the tenancy gate the internal callers don't
// need: the user must hold a grant on the book (View to list, Edit to write). After the
// grant check they DELEGATE to the internal handler (no body read yet), so there is one
// source of truth for the query + the never-overwrite-verified upsert.

// GET /v1/glossary/books/{book_id}/translation-candidates
func (s *Server) bookTranslationCandidates(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "authentication required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if err := s.checkGrant(r.Context(), bookID, userID, grantclient.GrantView); err != nil {
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "you do not have access to this book")
		return
	}
	s.internalTranslationCandidates(w, r)
}

// POST /v1/glossary/books/{book_id}/apply-translations
func (s *Server) bookApplyTranslations(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "authentication required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if err := s.checkGrant(r.Context(), bookID, userID, grantclient.GrantEdit); err != nil {
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "you need edit access to this book")
		return
	}
	s.internalApplyTranslations(w, r)
}

func parseOptionalUUIDList(csv string) []uuid.UUID {
	if strings.TrimSpace(csv) == "" {
		return nil
	}
	parts := strings.Split(csv, ",")
	out := make([]uuid.UUID, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		if id, err := uuid.Parse(p); err == nil {
			out = append(out, id)
		}
	}
	return out
}
