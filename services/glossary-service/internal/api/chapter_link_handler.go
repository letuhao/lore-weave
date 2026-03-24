package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// verifyEntityInBook checks that entity_id belongs to book_id. Writes 404 and
// returns false if not found or on DB error.
func (s *Server) verifyEntityInBook(w http.ResponseWriter, ctx context.Context, entityID, bookID uuid.UUID) bool {
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2)`,
		entityID, bookID,
	).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return false
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return false
	}
	return true
}

// queryChapterLinks fetches all chapter links for an entity ordered by
// chapter_index NULLS LAST, then added_at.
func (s *Server) queryChapterLinks(ctx context.Context, entityID uuid.UUID) ([]chapterLinkResp, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT link_id, entity_id, chapter_id, chapter_title, chapter_index, relevance, note, added_at
		FROM chapter_entity_links
		WHERE entity_id = $1
		ORDER BY chapter_index NULLS LAST, added_at`, entityID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	links := []chapterLinkResp{}
	for rows.Next() {
		var cl chapterLinkResp
		if err := rows.Scan(
			&cl.LinkID, &cl.EntityID, &cl.ChapterID,
			&cl.ChapterTitle, &cl.ChapterIndex, &cl.Relevance, &cl.Note, &cl.AddedAt,
		); err != nil {
			return nil, err
		}
		links = append(links, cl)
	}
	return links, rows.Err()
}

// scanChapterLink fetches a single chapter link row by link_id + entity_id.
func (s *Server) scanChapterLink(ctx context.Context, linkID, entityID uuid.UUID) (*chapterLinkResp, error) {
	var cl chapterLinkResp
	err := s.pool.QueryRow(ctx, `
		SELECT link_id, entity_id, chapter_id, chapter_title, chapter_index, relevance, note, added_at
		FROM chapter_entity_links
		WHERE link_id = $1 AND entity_id = $2`,
		linkID, entityID,
	).Scan(
		&cl.LinkID, &cl.EntityID, &cl.ChapterID,
		&cl.ChapterTitle, &cl.ChapterIndex, &cl.Relevance, &cl.Note, &cl.AddedAt,
	)
	if err != nil {
		return nil, err
	}
	return &cl, nil
}

// ── GET /v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links ───────

func (s *Server) listChapterLinks(w http.ResponseWriter, r *http.Request) {
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

	links, err := s.queryChapterLinks(r.Context(), entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	writeJSON(w, http.StatusOK, links)
}

// ── POST /v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links ──────

func (s *Server) createChapterLink(w http.ResponseWriter, r *http.Request) {
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

	var in struct {
		ChapterID string  `json:"chapter_id"`
		Relevance string  `json:"relevance"`
		Note      *string `json:"note"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.ChapterID == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "chapter_id is required")
		return
	}
	chapterID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "chapter_id must be a UUID")
		return
	}
	switch in.Relevance {
	case "major", "appears", "mentioned":
	case "":
		in.Relevance = "appears"
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"relevance must be major, appears, or mentioned")
		return
	}

	// Validate chapter belongs to book via book-service
	chapters, status := s.fetchBookChapters(r.Context(), bookID)
	if status != http.StatusOK {
		writeError(w, http.StatusServiceUnavailable, "GLOSS_UPSTREAM_UNAVAILABLE", "book service unavailable")
		return
	}
	var chapterTitle *string
	var chapterIndex *int
	found := false
	for _, ch := range chapters {
		if ch.ChapterID == chapterID {
			chapterTitle = ch.Title
			idx := ch.SortOrder
			chapterIndex = &idx
			found = true
			break
		}
	}
	if !found {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_CHAPTER_NOT_IN_BOOK",
			"chapter does not belong to this book")
		return
	}

	// Insert
	ctx := r.Context()
	var cl chapterLinkResp
	err = s.pool.QueryRow(ctx, `
		INSERT INTO chapter_entity_links(entity_id, chapter_id, chapter_title, chapter_index, relevance, note)
		VALUES($1,$2,$3,$4,$5,$6)
		RETURNING link_id, entity_id, chapter_id, chapter_title, chapter_index, relevance, note, added_at`,
		entityID, chapterID, chapterTitle, chapterIndex, in.Relevance, in.Note,
	).Scan(
		&cl.LinkID, &cl.EntityID, &cl.ChapterID,
		&cl.ChapterTitle, &cl.ChapterIndex, &cl.Relevance, &cl.Note, &cl.AddedAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CHAPTER_LINK",
				"entity is already linked to this chapter")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}
	writeJSON(w, http.StatusCreated, cl)
}

// ── PATCH /v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links/{link_id}

func (s *Server) updateChapterLink(w http.ResponseWriter, r *http.Request) {
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
	linkID, ok := parsePathUUID(w, r, "link_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
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

	if raw, ok := in["relevance"]; ok {
		var rel string
		if err := json.Unmarshal(raw, &rel); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid relevance")
			return
		}
		switch rel {
		case "major", "appears", "mentioned":
		default:
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
				"relevance must be major, appears, or mentioned")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("relevance = $%d", argN))
		args = append(args, rel)
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
		args = append(args, linkID, entityID)
		updateSQL := fmt.Sprintf(
			"UPDATE chapter_entity_links SET %s WHERE link_id = $%d AND entity_id = $%d",
			strings.Join(setClauses, ", "), argN, argN+1)
		tag, err := s.pool.Exec(ctx, updateSQL, args...)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
		if tag.RowsAffected() == 0 {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "chapter link not found")
			return
		}
	}

	cl, err := s.scanChapterLink(ctx, linkID, entityID)
	if err != nil {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "chapter link not found")
		return
	}
	writeJSON(w, http.StatusOK, cl)
}

// ── DELETE /v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links/{link_id}

func (s *Server) deleteChapterLink(w http.ResponseWriter, r *http.Request) {
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
	linkID, ok := parsePathUUID(w, r, "link_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}

	tag, err := s.pool.Exec(r.Context(),
		`DELETE FROM chapter_entity_links WHERE link_id=$1 AND entity_id=$2`, linkID, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "chapter link not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
