package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

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
			INSERT INTO evidences(attr_value_id, chapter_id, chapter_title, block_or_line,
			                      evidence_type, original_language, original_text, note)
			VALUES($1,$2,$3,$4,$5,$6,$7,$8)
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
		attrValueID, chapterUUID, in.ChapterTitle, in.BlockOrLine,
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
