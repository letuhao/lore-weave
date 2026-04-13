package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// ── list entity evidences ────────────────────────────────────────────────────

type evidenceListItem struct {
	EvidenceID       string    `json:"evidence_id"`
	AttrValueID      string    `json:"attr_value_id"`
	AttributeName    string    `json:"attribute_name"`
	AttributeCode    string    `json:"attribute_code"`
	ChapterID        *string   `json:"chapter_id"`
	ChapterTitle     *string   `json:"chapter_title"`
	ChapterIndex     *int      `json:"chapter_index"`
	BlockOrLine      string    `json:"block_or_line"`
	EvidenceType     string    `json:"evidence_type"`
	OriginalLanguage string    `json:"original_language"`
	OriginalText     string    `json:"original_text"`
	DisplayText      string    `json:"display_text"`
	DisplayLanguage  string    `json:"display_language"`
	Note             *string   `json:"note"`
	CreatedAt        time.Time `json:"created_at"`
}

type evidenceFilterOption struct {
	AttrValueID string `json:"attr_value_id"`
	Name        string `json:"name"`
}

type evidenceChapterOption struct {
	ChapterID    string  `json:"chapter_id"`
	ChapterTitle *string `json:"chapter_title"`
	ChapterIndex *int    `json:"chapter_index"`
}

type evidenceListResp struct {
	Items               []evidenceListItem      `json:"items"`
	Total               int                     `json:"total"`
	Limit               int                     `json:"limit"`
	Offset              int                     `json:"offset"`
	AvailableAttributes []evidenceFilterOption   `json:"available_attributes"`
	AvailableChapters   []evidenceChapterOption  `json:"available_chapters"`
}

// GET /v1/glossary/books/{book_id}/entities/{entity_id}/evidences
func (s *Server) listEntityEvidences(w http.ResponseWriter, r *http.Request) {
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}

	q := r.URL.Query()
	ctx := r.Context()

	// Parse filters
	evidenceType := q.Get("evidence_type")
	attrValueFilter := q.Get("attr_value_id")
	chapterFilter := q.Get("chapter_id")
	language := q.Get("language")

	// Parse sort
	sortBy := q.Get("sort_by")
	sortDir := q.Get("sort_dir")
	allowedSorts := map[string]string{
		"created_at":     "ev.created_at",
		"chapter_index":  "ev.chapter_index",
		"block_or_line":  "ev.block_or_line",
		"attribute_name": "ad.name",
	}
	sortCol, ok2 := allowedSorts[sortBy]
	if !ok2 {
		sortCol = "ev.created_at"
	}
	if sortDir != "asc" {
		sortDir = "desc"
	}

	// Parse pagination
	limit := 20
	offset := 0
	if v, err := strconv.Atoi(q.Get("limit")); err == nil && v > 0 && v <= 100 {
		limit = v
	}
	if v, err := strconv.Atoi(q.Get("offset")); err == nil && v >= 0 {
		offset = v
	}

	// Build WHERE clauses
	whereClauses := []string{"eav.entity_id = $1"}
	args := []any{entityID}
	n := 1

	if evidenceType != "" {
		switch evidenceType {
		case "quote", "summary", "reference":
			n++
			whereClauses = append(whereClauses, fmt.Sprintf("ev.evidence_type = $%d", n))
			args = append(args, evidenceType)
		default:
			writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "evidence_type must be quote, summary, or reference")
			return
		}
	}

	if attrValueFilter != "" {
		if _, err := uuid.Parse(attrValueFilter); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "invalid attr_value_id")
			return
		}
		n++
		whereClauses = append(whereClauses, fmt.Sprintf("ev.attr_value_id = $%d", n))
		args = append(args, attrValueFilter)
	}

	if chapterFilter != "" {
		if _, err := uuid.Parse(chapterFilter); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "invalid chapter_id")
			return
		}
		n++
		whereClauses = append(whereClauses, fmt.Sprintf("ev.chapter_id = $%d", n))
		args = append(args, chapterFilter)
	}

	whereSQL := "WHERE " + strings.Join(whereClauses, " AND ")

	// Count
	countSQL := fmt.Sprintf(`
		SELECT COUNT(*)
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		%s`, whereSQL)

	var total int
	if err := s.pool.QueryRow(ctx, countSQL, args...).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count query failed")
		return
	}

	// Main query with language fallback
	n++
	limitArg := n
	n++
	offsetArg := n
	args = append(args, limit, offset)

	// If language is provided, try to find evidence_translation for that language.
	// Fallback to original_text if no translation exists.
	var displayTextExpr, displayLangExpr string
	if language != "" {
		n++
		langArg := n
		args = append(args, language)
		displayTextExpr = fmt.Sprintf(`COALESCE(
			(SELECT et.value FROM evidence_translations et
			 WHERE et.evidence_id = ev.evidence_id AND et.language_code = $%d AND et.value != ''),
			ev.original_text
		)`, langArg)
		displayLangExpr = fmt.Sprintf(`CASE
			WHEN EXISTS(SELECT 1 FROM evidence_translations et
			            WHERE et.evidence_id = ev.evidence_id AND et.language_code = $%d AND et.value != '')
			THEN $%d::text
			ELSE ev.original_language
		END`, langArg, langArg)
	} else {
		displayTextExpr = "ev.original_text"
		displayLangExpr = "ev.original_language"
	}

	orderSQL := fmt.Sprintf("ORDER BY %s %s NULLS LAST", sortCol, sortDir)

	mainSQL := fmt.Sprintf(`
		SELECT
			ev.evidence_id, ev.attr_value_id,
			ad.name, ad.code,
			ev.chapter_id, ev.chapter_title, ev.chapter_index,
			ev.block_or_line, ev.evidence_type,
			ev.original_language, ev.original_text,
			%s AS display_text,
			%s AS display_language,
			ev.note, ev.created_at
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
		%s
		%s
		LIMIT $%d OFFSET $%d`,
		displayTextExpr, displayLangExpr,
		whereSQL, orderSQL, limitArg, offsetArg)

	rows, err := s.pool.Query(ctx, mainSQL, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "list query failed")
		return
	}
	defer rows.Close()

	items := []evidenceListItem{}
	for rows.Next() {
		var item evidenceListItem
		if err := rows.Scan(
			&item.EvidenceID, &item.AttrValueID,
			&item.AttributeName, &item.AttributeCode,
			&item.ChapterID, &item.ChapterTitle, &item.ChapterIndex,
			&item.BlockOrLine, &item.EvidenceType,
			&item.OriginalLanguage, &item.OriginalText,
			&item.DisplayText, &item.DisplayLanguage,
			&item.Note, &item.CreatedAt,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	// Available attributes (for filter dropdown)
	attrRows, err := s.pool.Query(ctx, `
		SELECT DISTINCT eav.attr_value_id, ad.name
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
		WHERE eav.entity_id = $1
		ORDER BY ad.name`, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attrs query failed")
		return
	}
	defer attrRows.Close()

	availAttrs := []evidenceFilterOption{}
	for attrRows.Next() {
		var opt evidenceFilterOption
		if err := attrRows.Scan(&opt.AttrValueID, &opt.Name); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		availAttrs = append(availAttrs, opt)
	}
	if err := attrRows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	// Available chapters (for filter dropdown)
	chRows, err := s.pool.Query(ctx, `
		SELECT DISTINCT ev.chapter_id, ev.chapter_title, ev.chapter_index
		FROM evidences ev
		JOIN entity_attribute_values eav ON eav.attr_value_id = ev.attr_value_id
		WHERE eav.entity_id = $1 AND ev.chapter_id IS NOT NULL
		ORDER BY ev.chapter_index NULLS LAST, ev.chapter_title`, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "chapters query failed")
		return
	}
	defer chRows.Close()

	availChapters := []evidenceChapterOption{}
	for chRows.Next() {
		var opt evidenceChapterOption
		if err := chRows.Scan(&opt.ChapterID, &opt.ChapterTitle, &opt.ChapterIndex); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		availChapters = append(availChapters, opt)
	}
	if err := chRows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	writeJSON(w, http.StatusOK, evidenceListResp{
		Items:               items,
		Total:               total,
		Limit:               limit,
		Offset:              offset,
		AvailableAttributes: availAttrs,
		AvailableChapters:   availChapters,
	})
}

// ── helpers ───────────────────────────────────────────────────────────────────

// verifyEvidenceInAttrValue checks that evidence_id belongs to attr_value_id.
func (s *Server) verifyEvidenceInAttrValue(w http.ResponseWriter, ctx context.Context, evidenceID, attrValueID uuid.UUID) bool {
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM evidences WHERE evidence_id=$1 AND attr_value_id=$2)`,
		evidenceID, attrValueID,
	).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return false
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "evidence not found")
		return false
	}
	return true
}

// scanEvidence fetches a single evidence row (without translations).
func (s *Server) scanEvidence(ctx context.Context, evidenceID, attrValueID uuid.UUID) (*evidenceResp, error) {
	var ev evidenceResp
	err := s.pool.QueryRow(ctx, `
		SELECT evidence_id, attr_value_id, chapter_id, chapter_title,
		       block_or_line, evidence_type, original_language, original_text, note, created_at
		FROM evidences
		WHERE evidence_id=$1 AND attr_value_id=$2`,
		evidenceID, attrValueID,
	).Scan(
		&ev.EvidenceID, &ev.AttrValueID, &ev.ChapterID, &ev.ChapterTitle,
		&ev.BlockOrLine, &ev.EvidenceType, &ev.OriginalLanguage,
		&ev.OriginalText, &ev.Note, &ev.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	ev.Translations = []evidenceTranslationResp{}
	return &ev, nil
}

// ── POST /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/evidences

func (s *Server) createEvidence(w http.ResponseWriter, r *http.Request) {
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
		EvidenceType     string  `json:"evidence_type"`
		OriginalText     string  `json:"original_text"`
		OriginalLanguage string  `json:"original_language"`
		ChapterID        *string `json:"chapter_id"`
		ChapterTitle     *string `json:"chapter_title"`
		ChapterIndex     *int    `json:"chapter_index"`
		BlockOrLine      string  `json:"block_or_line"`
		Note             *string `json:"note"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	switch in.EvidenceType {
	case "quote", "summary", "reference":
	case "":
		in.EvidenceType = "quote"
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"evidence_type must be quote, summary, or reference")
		return
	}
	if in.OriginalLanguage == "" {
		in.OriginalLanguage = "zh"
	}

	// Validate chapter_id UUID if provided
	var chapterUUID *uuid.UUID
	if in.ChapterID != nil && *in.ChapterID != "" {
		id, err := uuid.Parse(*in.ChapterID)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid chapter_id")
			return
		}
		chapterUUID = &id
	}

	var ev evidenceResp
	ev.Translations = []evidenceTranslationResp{}
	// CTE inserts the evidence and bumps the entity's updated_at in one round-trip.
	err := s.pool.QueryRow(r.Context(), `
		WITH _ins AS (
			INSERT INTO evidences(attr_value_id, chapter_id, chapter_title, chapter_index, block_or_line,
			                      evidence_type, original_language, original_text, note)
			VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
			RETURNING evidence_id, attr_value_id, chapter_id, chapter_title,
			          block_or_line, evidence_type, original_language, original_text, note, created_at
		),
		_bump AS (
			UPDATE glossary_entities SET updated_at = now()
			WHERE entity_id = (
				SELECT entity_id FROM entity_attribute_values WHERE attr_value_id = $1
			)
		)
		SELECT evidence_id, attr_value_id, chapter_id, chapter_title,
		       block_or_line, evidence_type, original_language, original_text, note, created_at
		FROM _ins`,
		attrValueID, chapterUUID, in.ChapterTitle, in.ChapterIndex, in.BlockOrLine,
		in.EvidenceType, in.OriginalLanguage, in.OriginalText, in.Note,
	).Scan(
		&ev.EvidenceID, &ev.AttrValueID, &ev.ChapterID, &ev.ChapterTitle,
		&ev.BlockOrLine, &ev.EvidenceType, &ev.OriginalLanguage,
		&ev.OriginalText, &ev.Note, &ev.CreatedAt,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}
	writeJSON(w, http.StatusCreated, ev)
}

// ── PATCH /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/evidences/{evidence_id}

func (s *Server) updateEvidence(w http.ResponseWriter, r *http.Request) {
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
	evidenceID, ok := parsePathUUID(w, r, "evidence_id")
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
	if !s.verifyEvidenceInAttrValue(w, r.Context(), evidenceID, attrValueID) {
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

	if raw, ok := in["original_text"]; ok {
		var val string
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid original_text")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("original_text = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["original_language"]; ok {
		var val string
		if err := json.Unmarshal(raw, &val); err != nil || val == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid original_language")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("original_language = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["block_or_line"]; ok {
		var val string
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid block_or_line")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("block_or_line = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["evidence_type"]; ok {
		var val string
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid evidence_type")
			return
		}
		switch val {
		case "quote", "summary", "reference":
		default:
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "evidence_type must be quote, summary, or reference")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("evidence_type = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["chapter_id"]; ok {
		var val *string
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid chapter_id")
			return
		}
		if val != nil && *val != "" {
			if _, err := uuid.Parse(*val); err != nil {
				writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid chapter_id UUID")
				return
			}
		}
		setClauses = append(setClauses, fmt.Sprintf("chapter_id = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["chapter_title"]; ok {
		var val *string
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid chapter_title")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("chapter_title = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["chapter_index"]; ok {
		var val *int
		if err := json.Unmarshal(raw, &val); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid chapter_index")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("chapter_index = $%d", argN))
		args = append(args, val)
		argN++
	}

	if raw, ok := in["note"]; ok {
		var note *string
		if err := json.Unmarshal(raw, &note); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid note")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("note = $%d", argN))
		args = append(args, note)
		argN++
	}

	ctx := r.Context()
	if len(setClauses) > 0 {
		args = append(args, evidenceID, attrValueID)
		updateSQL := fmt.Sprintf(
			"UPDATE evidences SET %s WHERE evidence_id = $%d AND attr_value_id = $%d",
			strings.Join(setClauses, ", "), argN, argN+1)
		if _, err := s.pool.Exec(ctx, updateSQL, args...); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
		if _, err := s.pool.Exec(ctx,
			`UPDATE glossary_entities SET updated_at = now()
			 WHERE entity_id = (SELECT entity_id FROM entity_attribute_values WHERE attr_value_id = $1)`,
			attrValueID); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
	}

	ev, err := s.scanEvidence(ctx, evidenceID, attrValueID)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "evidence not found")
		} else {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		}
		return
	}
	writeJSON(w, http.StatusOK, ev)
}

// ── DELETE /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/evidences/{evidence_id}

func (s *Server) deleteEvidence(w http.ResponseWriter, r *http.Request) {
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
	evidenceID, ok := parsePathUUID(w, r, "evidence_id")
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

	// CTE deletes the evidence and — only if a row was deleted — bumps the entity.
	tag, err := s.pool.Exec(r.Context(), `
		WITH _del AS (
			DELETE FROM evidences WHERE evidence_id=$1 AND attr_value_id=$2
			RETURNING attr_value_id
		)
		UPDATE glossary_entities SET updated_at = now()
		WHERE entity_id = (
			SELECT entity_id FROM entity_attribute_values
			WHERE attr_value_id = (SELECT attr_value_id FROM _del)
		)`,
		evidenceID, attrValueID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "evidence not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
