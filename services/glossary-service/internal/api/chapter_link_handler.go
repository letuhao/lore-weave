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
	"github.com/loreweave/grantclient"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// verifyEntityInBook checks that entity_id belongs to book_id. Writes 404 and
// returns false if not found or on DB error.
func (s *Server) verifyEntityInBook(w http.ResponseWriter, ctx context.Context, entityID, bookID uuid.UUID) bool {
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)`,
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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
	cl, err := s.createChapterLinkCore(r.Context(), bookID, entityID, chapterID, in.Relevance, in.Note)
	if err != nil {
		writeChapterLinkErr(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, cl)
}

// chapter-link create sentinels (shared by the HTTP handler + the MCP write tool).
var (
	errChapterRelevance = errors.New("relevance must be major, appears, or mentioned") // → 422
	errChapterNotInBook = errors.New("chapter does not belong to this book")           // → 422
	errChapterUpstream  = errors.New("book service unavailable")                       // → 503
	errChapterLinkDup   = errors.New("entity is already linked to this chapter")       // → 409
)

// createChapterLinkCore validates the relevance + that the chapter belongs to the book
// (via book-service) and inserts the link. The single source of truth for the HTTP
// createChapterLink handler and the glossary_create_chapter_link MCP tool. Entity-in-book
// + grant are checked by the CALLER.
func (s *Server) createChapterLinkCore(ctx context.Context, bookID, entityID, chapterID uuid.UUID, relevance string, note *string) (*chapterLinkResp, error) {
	switch relevance {
	case "major", "appears", "mentioned":
	case "":
		relevance = "appears"
	default:
		return nil, errChapterRelevance
	}
	chapters, status := s.fetchBookChapters(ctx, bookID)
	if status != http.StatusOK {
		return nil, errChapterUpstream
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
		return nil, errChapterNotInBook
	}
	var cl chapterLinkResp
	err := s.pool.QueryRow(ctx, `
		INSERT INTO chapter_entity_links(entity_id, chapter_id, chapter_title, chapter_index, relevance, note)
		VALUES($1,$2,$3,$4,$5,$6)
		RETURNING link_id, entity_id, chapter_id, chapter_title, chapter_index, relevance, note, added_at`,
		entityID, chapterID, chapterTitle, chapterIndex, relevance, note,
	).Scan(
		&cl.LinkID, &cl.EntityID, &cl.ChapterID,
		&cl.ChapterTitle, &cl.ChapterIndex, &cl.Relevance, &cl.Note, &cl.AddedAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return nil, errChapterLinkDup
		}
		return nil, err
	}
	return &cl, nil
}

// writeChapterLinkErr maps the core sentinels to HTTP for the createChapterLink handler.
func writeChapterLinkErr(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, errChapterRelevance):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", err.Error())
	case errors.Is(err, errChapterNotInBook):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_CHAPTER_NOT_IN_BOOK", err.Error())
	case errors.Is(err, errChapterUpstream):
		writeError(w, http.StatusServiceUnavailable, "GLOSS_UPSTREAM_UNAVAILABLE", err.Error())
	case errors.Is(err, errChapterLinkDup):
		writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CHAPTER_LINK", err.Error())
	default:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
	}
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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
