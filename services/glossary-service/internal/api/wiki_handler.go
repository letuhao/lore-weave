package api

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// ── response types ───────────────────────────────────────────────────────────

type wikiArticleListItem struct {
	ArticleID     string      `json:"article_id"`
	EntityID      string      `json:"entity_id"`
	BookID        string      `json:"book_id"`
	DisplayName   string      `json:"display_name"`
	Kind          kindSummary `json:"kind"`
	Status        string      `json:"status"`
	TemplateCode  *string     `json:"template_code"`
	RevisionCount int         `json:"revision_count"`
	UpdatedAt     time.Time   `json:"updated_at"`
}

type wikiArticleListResp struct {
	Items  []wikiArticleListItem `json:"items"`
	Total  int                   `json:"total"`
	Limit  int                   `json:"limit"`
	Offset int                   `json:"offset"`
}

type wikiArticleDetail struct {
	wikiArticleListItem
	BodyJSON        json.RawMessage `json:"body_json"`
	SpoilerChapters []string        `json:"spoiler_chapters"`
	Infobox         []attrValueResp `json:"infobox"`
	CreatedAt       time.Time       `json:"created_at"`
}

type wikiRevisionListItem struct {
	RevisionID string    `json:"revision_id"`
	ArticleID  string    `json:"article_id"`
	Version    int       `json:"version"`
	AuthorID   string    `json:"author_id"`
	AuthorType string    `json:"author_type"`
	Summary    string    `json:"summary"`
	CreatedAt  time.Time `json:"created_at"`
}

type wikiRevisionListResp struct {
	Items  []wikiRevisionListItem `json:"items"`
	Total  int                    `json:"total"`
	Limit  int                    `json:"limit"`
	Offset int                    `json:"offset"`
}

type wikiRevisionDetail struct {
	wikiRevisionListItem
	BodyJSON json.RawMessage `json:"body_json"`
}

// ── verification helpers ─────────────────────────────────────────────────────

func (s *Server) verifyArticleInBook(w http.ResponseWriter, r *http.Request, articleID, bookID uuid.UUID) bool {
	var exists bool
	err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM wiki_articles WHERE article_id=$1 AND book_id=$2)`,
		articleID, bookID).Scan(&exists)
	if err != nil || !exists {
		writeError(w, http.StatusNotFound, "WIKI_NOT_FOUND", "wiki article not found")
		return false
	}
	return true
}

func (s *Server) verifyRevisionInArticle(w http.ResponseWriter, r *http.Request, revID, articleID uuid.UUID) bool {
	var exists bool
	err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM wiki_revisions WHERE revision_id=$1 AND article_id=$2)`,
		revID, articleID).Scan(&exists)
	if err != nil || !exists {
		writeError(w, http.StatusNotFound, "WIKI_REVISION_NOT_FOUND", "revision not found")
		return false
	}
	return true
}

// ── 1. listWikiArticles ──────────────────────────────────────────────────────

func (s *Server) listWikiArticles(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	offset, _ := strconv.Atoi(q.Get("offset"))
	if offset < 0 {
		offset = 0
	}

	// Build WHERE clauses
	where := []string{"wa.book_id = $1"}
	args := []any{bookID}
	argN := 2

	if status := q.Get("status"); status != "" {
		where = append(where, fmt.Sprintf("wa.status = $%d", argN))
		args = append(args, status)
		argN++
	}
	if kindCode := q.Get("kind_code"); kindCode != "" {
		where = append(where, fmt.Sprintf("ek.code = $%d", argN))
		args = append(args, kindCode)
		argN++
	}
	if search := q.Get("search"); search != "" {
		where = append(where, fmt.Sprintf(`(
			dn.original_value ILIKE '%%' || $%d || '%%'
		)`, argN))
		args = append(args, search)
		argN++
	}

	whereClause := strings.Join(where, " AND ")

	// Count
	var total int
	countSQL := fmt.Sprintf(`
		SELECT COUNT(*)
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_def_id FROM attribute_definitions ad
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)
		WHERE %s AND ge.deleted_at IS NULL`, whereClause)
	if err := s.pool.QueryRow(r.Context(), countSQL, args...).Scan(&total); err != nil {
		slog.Error("listWikiArticles count", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Fetch
	fetchSQL := fmt.Sprintf(`
		SELECT
			wa.article_id, wa.entity_id, wa.book_id,
			COALESCE(dn.original_value, '') AS display_name,
			ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.status, wa.template_code,
			(SELECT COUNT(*) FROM wiki_revisions wr WHERE wr.article_id = wa.article_id) AS revision_count,
			wa.updated_at
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_def_id FROM attribute_definitions ad
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)
		WHERE %s AND ge.deleted_at IS NULL
		ORDER BY wa.updated_at DESC
		LIMIT $%d OFFSET $%d`, whereClause, argN, argN+1)
	args = append(args, limit, offset)

	rows, err := s.pool.Query(r.Context(), fetchSQL, args...)
	if err != nil {
		slog.Error("listWikiArticles fetch", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	items := []wikiArticleListItem{}
	for rows.Next() {
		var it wikiArticleListItem
		if err := rows.Scan(
			&it.ArticleID, &it.EntityID, &it.BookID,
			&it.DisplayName,
			&it.Kind.KindID, &it.Kind.Code, &it.Kind.Name, &it.Kind.Icon, &it.Kind.Color,
			&it.Status, &it.TemplateCode,
			&it.RevisionCount,
			&it.UpdatedAt,
		); err != nil {
			slog.Error("listWikiArticles scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		slog.Error("listWikiArticles rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, wikiArticleListResp{
		Items:  items,
		Total:  total,
		Limit:  limit,
		Offset: offset,
	})
}

// ── 2. createWikiArticle ─────────────────────────────────────────────────────

func (s *Server) createWikiArticle(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	var req struct {
		EntityID     string          `json:"entity_id"`
		TemplateCode *string         `json:"template_code"`
		BodyJSON     json.RawMessage `json:"body_json"`
		Status       *string         `json:"status"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}

	entityID, err := uuid.Parse(req.EntityID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_INVALID_ENTITY", "invalid entity_id")
		return
	}

	// Verify entity belongs to this book and is not deleted
	var entityBookID uuid.UUID
	err = s.pool.QueryRow(r.Context(),
		`SELECT book_id FROM glossary_entities WHERE entity_id=$1 AND deleted_at IS NULL`,
		entityID).Scan(&entityBookID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "WIKI_ENTITY_NOT_FOUND", "entity not found")
		return
	}
	if err != nil {
		slog.Error("createWikiArticle entity check", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	if entityBookID != bookID {
		writeError(w, http.StatusForbidden, "WIKI_FORBIDDEN", "entity does not belong to this book")
		return
	}

	// Check no existing article for this entity
	var exists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM wiki_articles WHERE entity_id=$1)`,
		entityID).Scan(&exists); err != nil {
		slog.Error("createWikiArticle dup check", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	if exists {
		writeError(w, http.StatusConflict, "WIKI_ALREADY_EXISTS", "wiki article already exists for this entity")
		return
	}

	status := "draft"
	if req.Status != nil && (*req.Status == "draft" || *req.Status == "published") {
		status = *req.Status
	}

	bodyJSON := json.RawMessage("{}")
	if req.BodyJSON != nil && len(req.BodyJSON) > 0 {
		bodyJSON = req.BodyJSON
	}

	// Insert article + initial revision in a transaction
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		slog.Error("createWikiArticle tx begin", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	var articleID uuid.UUID
	var createdAt, updatedAt time.Time
	err = tx.QueryRow(r.Context(), `
		INSERT INTO wiki_articles (entity_id, book_id, body_json, status, template_code)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING article_id, created_at, updated_at`,
		entityID, bookID, bodyJSON, status, req.TemplateCode,
	).Scan(&articleID, &createdAt, &updatedAt)
	if err != nil {
		slog.Error("createWikiArticle insert", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Create initial revision (version 1)
	if _, err := tx.Exec(r.Context(), `
		INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
		VALUES ($1, 1, $2, $3, 'owner', 'Initial version')`,
		articleID, bodyJSON, userID,
	); err != nil {
		slog.Error("createWikiArticle revision", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("createWikiArticle commit", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Build response by loading the full article detail
	detail, err := s.loadWikiArticleDetail(r, bookID, articleID)
	if err != nil {
		slog.Error("createWikiArticle load", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusCreated, detail)
}

// ── 3. getWikiArticle ────────────────────────────────────────────────────────

func (s *Server) getWikiArticle(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}

	detail, err := s.loadWikiArticleDetail(r, bookID, articleID)
	if err != nil {
		slog.Error("getWikiArticle", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, detail)
}

// ── 4. patchWikiArticle ──────────────────────────────────────────────────────

func (s *Server) patchWikiArticle(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}

	var req struct {
		BodyJSON        json.RawMessage `json:"body_json"`
		Status          *string         `json:"status"`
		TemplateCode    *string         `json:"template_code"`
		SpoilerChapters *[]string       `json:"spoiler_chapters"`
		Summary         *string         `json:"summary"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}

	// Validate status if provided
	if req.Status != nil && *req.Status != "draft" && *req.Status != "published" {
		writeError(w, http.StatusUnprocessableEntity, "WIKI_INVALID_STATUS", "status must be draft or published")
		return
	}

	// Validate spoiler_chapters UUIDs if provided
	var spoilerUUIDs []uuid.UUID
	if req.SpoilerChapters != nil {
		spoilerUUIDs = make([]uuid.UUID, 0, len(*req.SpoilerChapters))
		for _, s := range *req.SpoilerChapters {
			id, err := uuid.Parse(s)
			if err != nil {
				writeError(w, http.StatusBadRequest, "WIKI_INVALID_SPOILER", "invalid UUID in spoiler_chapters")
				return
			}
			spoilerUUIDs = append(spoilerUUIDs, id)
		}
	}

	// Build dynamic UPDATE
	sets := []string{"updated_at = now()"}
	args := []any{articleID}
	argN := 2
	bodyChanged := req.BodyJSON != nil && len(req.BodyJSON) > 0

	if bodyChanged {
		sets = append(sets, fmt.Sprintf("body_json = $%d", argN))
		args = append(args, req.BodyJSON)
		argN++
	}
	if req.Status != nil {
		sets = append(sets, fmt.Sprintf("status = $%d", argN))
		args = append(args, *req.Status)
		argN++
	}
	if req.TemplateCode != nil {
		sets = append(sets, fmt.Sprintf("template_code = $%d", argN))
		args = append(args, *req.TemplateCode)
		argN++
	}
	if req.SpoilerChapters != nil {
		sets = append(sets, fmt.Sprintf("spoiler_chapters = $%d", argN))
		args = append(args, spoilerUUIDs)
		argN++
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		slog.Error("patchWikiArticle tx begin", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	// Lock the article row to prevent concurrent revision version conflicts
	if _, err := tx.Exec(r.Context(),
		`SELECT 1 FROM wiki_articles WHERE article_id=$1 FOR UPDATE`, articleID); err != nil {
		slog.Error("patchWikiArticle lock", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	updateSQL := fmt.Sprintf("UPDATE wiki_articles SET %s WHERE article_id = $1", strings.Join(sets, ", "))
	if _, err := tx.Exec(r.Context(), updateSQL, args...); err != nil {
		slog.Error("patchWikiArticle update", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Create revision if body changed
	if bodyChanged {
		summary := ""
		if req.Summary != nil {
			summary = *req.Summary
		}
		if _, err := tx.Exec(r.Context(), `
			INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
			VALUES ($1, COALESCE((SELECT MAX(version) FROM wiki_revisions WHERE article_id=$1), 0) + 1, $2, $3, 'owner', $4)`,
			articleID, req.BodyJSON, userID, summary,
		); err != nil {
			slog.Error("patchWikiArticle revision", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	}

	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("patchWikiArticle commit", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	detail, err := s.loadWikiArticleDetail(r, bookID, articleID)
	if err != nil {
		slog.Error("patchWikiArticle load", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// ── 5. deleteWikiArticle ─────────────────────────────────────────────────────

func (s *Server) deleteWikiArticle(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}

	if _, err := s.pool.Exec(r.Context(),
		`DELETE FROM wiki_articles WHERE article_id=$1`, articleID); err != nil {
		slog.Error("deleteWikiArticle", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// ── 6. listWikiRevisions ─────────────────────────────────────────────────────

func (s *Server) listWikiRevisions(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}

	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	offset, _ := strconv.Atoi(q.Get("offset"))
	if offset < 0 {
		offset = 0
	}

	var total int
	if err := s.pool.QueryRow(r.Context(),
		`SELECT COUNT(*) FROM wiki_revisions WHERE article_id=$1`, articleID,
	).Scan(&total); err != nil {
		slog.Error("listWikiRevisions count", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	rows, err := s.pool.Query(r.Context(), `
		SELECT revision_id, article_id, version, author_id, author_type, summary, created_at
		FROM wiki_revisions
		WHERE article_id=$1
		ORDER BY version DESC
		LIMIT $2 OFFSET $3`, articleID, limit, offset)
	if err != nil {
		slog.Error("listWikiRevisions fetch", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	items := []wikiRevisionListItem{}
	for rows.Next() {
		var it wikiRevisionListItem
		if err := rows.Scan(
			&it.RevisionID, &it.ArticleID, &it.Version,
			&it.AuthorID, &it.AuthorType, &it.Summary, &it.CreatedAt,
		); err != nil {
			slog.Error("listWikiRevisions scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		slog.Error("listWikiRevisions rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, wikiRevisionListResp{
		Items:  items,
		Total:  total,
		Limit:  limit,
		Offset: offset,
	})
}

// ── 7. getWikiRevision ───────────────────────────────────────────────────────

func (s *Server) getWikiRevision(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}
	revID, ok := parsePathUUID(w, r, "rev_id")
	if !ok {
		return
	}
	if !s.verifyRevisionInArticle(w, r, revID, articleID) {
		return
	}

	var rev wikiRevisionDetail
	err := s.pool.QueryRow(r.Context(), `
		SELECT revision_id, article_id, version, body_json, author_id, author_type, summary, created_at
		FROM wiki_revisions
		WHERE revision_id=$1`, revID,
	).Scan(
		&rev.RevisionID, &rev.ArticleID, &rev.Version,
		&rev.BodyJSON, &rev.AuthorID, &rev.AuthorType, &rev.Summary, &rev.CreatedAt,
	)
	if err != nil {
		slog.Error("getWikiRevision", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, rev)
}

// ── 8. restoreWikiRevision ───────────────────────────────────────────────────

func (s *Server) restoreWikiRevision(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}
	revID, ok := parsePathUUID(w, r, "rev_id")
	if !ok {
		return
	}
	if !s.verifyRevisionInArticle(w, r, revID, articleID) {
		return
	}

	// Fetch revision body + version
	var revBody json.RawMessage
	var revVersion int
	if err := s.pool.QueryRow(r.Context(),
		`SELECT body_json, version FROM wiki_revisions WHERE revision_id=$1`, revID,
	).Scan(&revBody, &revVersion); err != nil {
		slog.Error("restoreWikiRevision fetch", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		slog.Error("restoreWikiRevision tx begin", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	// Lock the article row to prevent concurrent revision version conflicts
	if _, err := tx.Exec(r.Context(),
		`SELECT 1 FROM wiki_articles WHERE article_id=$1 FOR UPDATE`, articleID); err != nil {
		slog.Error("restoreWikiRevision lock", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Update article body
	if _, err := tx.Exec(r.Context(),
		`UPDATE wiki_articles SET body_json=$1, updated_at=now() WHERE article_id=$2`,
		revBody, articleID,
	); err != nil {
		slog.Error("restoreWikiRevision update", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Create new revision
	summary := fmt.Sprintf("Restored from version %d", revVersion)
	if _, err := tx.Exec(r.Context(), `
		INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
		VALUES ($1, COALESCE((SELECT MAX(version) FROM wiki_revisions WHERE article_id=$1), 0) + 1, $2, $3, 'owner', $4)`,
		articleID, revBody, userID, summary,
	); err != nil {
		slog.Error("restoreWikiRevision revision", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("restoreWikiRevision commit", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	detail, err := s.loadWikiArticleDetail(r, bookID, articleID)
	if err != nil {
		slog.Error("restoreWikiRevision load", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

// ── 9. generateWikiStubs ─────────────────────────────────────────────────────

func (s *Server) generateWikiStubs(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	var req struct {
		KindCodes []string `json:"kind_codes"`
		Limit     *int     `json:"limit"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}

	genLimit := 50
	if req.Limit != nil && *req.Limit > 0 && *req.Limit <= 200 {
		genLimit = *req.Limit
	}

	// Find entities without wiki articles
	querySQL := `
		SELECT ge.entity_id, ek.code
		FROM glossary_entities ge
		JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		WHERE ge.book_id = $1
		  AND ge.deleted_at IS NULL
		  AND ge.status = 'active'
		  AND NOT EXISTS (SELECT 1 FROM wiki_articles wa WHERE wa.entity_id = ge.entity_id)`

	args := []any{bookID}
	argN := 2

	if len(req.KindCodes) > 0 {
		placeholders := make([]string, len(req.KindCodes))
		for i, code := range req.KindCodes {
			placeholders[i] = fmt.Sprintf("$%d", argN)
			args = append(args, code)
			argN++
		}
		querySQL += fmt.Sprintf(" AND ek.code IN (%s)", strings.Join(placeholders, ","))
	}

	querySQL += fmt.Sprintf(" ORDER BY ge.created_at LIMIT $%d", argN)
	args = append(args, genLimit)

	rows, err := s.pool.Query(r.Context(), querySQL, args...)
	if err != nil {
		slog.Error("generateWikiStubs query", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	type entityStub struct {
		EntityID uuid.UUID
		KindCode string
	}
	var stubs []entityStub
	for rows.Next() {
		var s entityStub
		if err := rows.Scan(&s.EntityID, &s.KindCode); err != nil {
			slog.Error("generateWikiStubs scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		stubs = append(stubs, s)
	}
	if err := rows.Err(); err != nil {
		slog.Error("generateWikiStubs rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	if len(stubs) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{
			"created":  0,
			"articles": []wikiArticleListItem{},
		})
		return
	}

	// Batch insert articles + revisions
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		slog.Error("generateWikiStubs tx begin", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	var articleIDs []uuid.UUID
	emptyBody := json.RawMessage("{}")
	for _, stub := range stubs {
		var aid uuid.UUID
		err := tx.QueryRow(r.Context(), `
			INSERT INTO wiki_articles (entity_id, book_id, body_json, status, template_code)
			VALUES ($1, $2, $3, 'draft', $4)
			RETURNING article_id`,
			stub.EntityID, bookID, emptyBody, stub.KindCode,
		).Scan(&aid)
		if err != nil {
			slog.Error("generateWikiStubs insert article", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		articleIDs = append(articleIDs, aid)

		if _, err := tx.Exec(r.Context(), `
			INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
			VALUES ($1, 1, $2, $3, 'owner', 'Auto-generated stub')`,
			aid, emptyBody, userID,
		); err != nil {
			slog.Error("generateWikiStubs insert revision", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	}

	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("generateWikiStubs commit", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Fetch created articles for response
	placeholders := make([]string, len(articleIDs))
	fetchArgs := make([]any, len(articleIDs))
	for i, id := range articleIDs {
		placeholders[i] = fmt.Sprintf("$%d", i+1)
		fetchArgs[i] = id
	}

	fetchRows, err := s.pool.Query(r.Context(), fmt.Sprintf(`
		SELECT
			wa.article_id, wa.entity_id, wa.book_id,
			COALESCE(dn.original_value, '') AS display_name,
			ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.status, wa.template_code, 1 AS revision_count, wa.updated_at
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_def_id FROM attribute_definitions ad
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)
		WHERE wa.article_id IN (%s)
		ORDER BY wa.created_at`, strings.Join(placeholders, ",")), fetchArgs...)
	if err != nil {
		slog.Error("generateWikiStubs fetch", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer fetchRows.Close()

	items := []wikiArticleListItem{}
	for fetchRows.Next() {
		var it wikiArticleListItem
		if err := fetchRows.Scan(
			&it.ArticleID, &it.EntityID, &it.BookID,
			&it.DisplayName,
			&it.Kind.KindID, &it.Kind.Code, &it.Kind.Name, &it.Kind.Icon, &it.Kind.Color,
			&it.Status, &it.TemplateCode, &it.RevisionCount, &it.UpdatedAt,
		); err != nil {
			slog.Error("generateWikiStubs scan result", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		items = append(items, it)
	}
	if err := fetchRows.Err(); err != nil {
		slog.Error("generateWikiStubs fetch rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"created":  len(items),
		"articles": items,
	})
}

// ── loadWikiArticleDetail ────────────────────────────────────────────────────

func (s *Server) loadWikiArticleDetail(r *http.Request, bookID, articleID uuid.UUID) (*wikiArticleDetail, error) {
	var d wikiArticleDetail
	var spoilerChapters []uuid.UUID

	err := s.pool.QueryRow(r.Context(), `
		SELECT
			wa.article_id, wa.entity_id, wa.book_id,
			COALESCE(dn.original_value, '') AS display_name,
			ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.status, wa.template_code,
			(SELECT COUNT(*) FROM wiki_revisions wr WHERE wr.article_id = wa.article_id) AS revision_count,
			wa.updated_at, wa.body_json, wa.spoiler_chapters, wa.created_at
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_def_id FROM attribute_definitions ad
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)
		WHERE wa.article_id = $1 AND wa.book_id = $2`,
		articleID, bookID,
	).Scan(
		&d.ArticleID, &d.EntityID, &d.BookID,
		&d.DisplayName,
		&d.Kind.KindID, &d.Kind.Code, &d.Kind.Name, &d.Kind.Icon, &d.Kind.Color,
		&d.Status, &d.TemplateCode,
		&d.RevisionCount,
		&d.UpdatedAt, &d.BodyJSON, &spoilerChapters, &d.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("loadWikiArticleDetail main: %w", err)
	}

	// Convert spoiler_chapters UUIDs to strings
	d.SpoilerChapters = make([]string, len(spoilerChapters))
	for i, id := range spoilerChapters {
		d.SpoilerChapters[i] = id.String()
	}

	// Load infobox: attribute values with translations (same pattern as entity detail)
	entityID, _ := uuid.Parse(d.EntityID)
	avRows, err := s.pool.Query(r.Context(), `
		SELECT
			eav.attr_value_id, eav.entity_id, eav.attr_def_id,
			ad.attr_def_id, ad.code, ad.name, ad.field_type, ad.is_required, ad.is_system, ad.sort_order,
			eav.original_language, eav.original_value
		FROM entity_attribute_values eav
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
		WHERE eav.entity_id = $1
		ORDER BY ad.sort_order`, entityID)
	if err != nil {
		return nil, fmt.Errorf("loadWikiArticleDetail attrs: %w", err)
	}
	defer avRows.Close()

	d.Infobox = []attrValueResp{}
	var attrValueIDs []uuid.UUID
	for avRows.Next() {
		var av attrValueResp
		if err := avRows.Scan(
			&av.AttrValueID, &av.EntityID, &av.AttrDefID,
			&av.AttributeDef.AttrDefID, &av.AttributeDef.Code, &av.AttributeDef.Name,
			&av.AttributeDef.FieldType, &av.AttributeDef.IsRequired, &av.AttributeDef.IsSystem,
			&av.AttributeDef.SortOrder,
			&av.OriginalLanguage, &av.OriginalValue,
		); err != nil {
			return nil, fmt.Errorf("loadWikiArticleDetail attr scan: %w", err)
		}
		av.Translations = []translationResp{}
		av.Evidences = []evidenceResp{}
		avID, _ := uuid.Parse(av.AttrValueID)
		attrValueIDs = append(attrValueIDs, avID)
		d.Infobox = append(d.Infobox, av)
	}
	if err := avRows.Err(); err != nil {
		return nil, fmt.Errorf("loadWikiArticleDetail attr rows: %w", err)
	}

	// Batch load translations for all attribute values
	if len(attrValueIDs) > 0 {
		avIDMap := make(map[string]int)
		for i, av := range d.Infobox {
			avIDMap[av.AttrValueID] = i
		}

		placeholders := make([]string, len(attrValueIDs))
		trArgs := make([]any, len(attrValueIDs))
		for i, id := range attrValueIDs {
			placeholders[i] = fmt.Sprintf("$%d", i+1)
			trArgs[i] = id
		}

		trRows, err := s.pool.Query(r.Context(), fmt.Sprintf(`
			SELECT translation_id, attr_value_id, language_code, value, confidence, translator, updated_at
			FROM attribute_translations
			WHERE attr_value_id IN (%s)
			ORDER BY language_code`, strings.Join(placeholders, ",")), trArgs...)
		if err != nil {
			return nil, fmt.Errorf("loadWikiArticleDetail translations: %w", err)
		}
		defer trRows.Close()

		for trRows.Next() {
			var tr translationResp
			if err := trRows.Scan(
				&tr.TranslationID, &tr.AttrValueID, &tr.LanguageCode,
				&tr.Value, &tr.Confidence, &tr.Translator, &tr.UpdatedAt,
			); err != nil {
				return nil, fmt.Errorf("loadWikiArticleDetail translation scan: %w", err)
			}
			if idx, ok := avIDMap[tr.AttrValueID]; ok {
				d.Infobox[idx].Translations = append(d.Infobox[idx].Translations, tr)
			}
		}
	}

	return &d, nil
}

// ── Public endpoints (no JWT) ────────────────────────────────────────────────

// checkWikiPublic verifies the book has wiki visibility=public via book-service projection.
// Returns the projection on success, nil + error written on failure.
func (s *Server) checkWikiPublic(w http.ResponseWriter, r *http.Request, bookID uuid.UUID) *bookProjection {
	proj, status := s.fetchBookProjection(r.Context(), bookID)
	if status == http.StatusNotFound {
		writeError(w, http.StatusNotFound, "WIKI_BOOK_NOT_FOUND", "book not found")
		return nil
	}
	if status != http.StatusOK {
		writeError(w, http.StatusServiceUnavailable, "WIKI_UPSTREAM_UNAVAILABLE", "book service unavailable")
		return nil
	}
	if proj.WikiSettings == nil || proj.WikiSettings.Visibility != "public" {
		writeError(w, http.StatusNotFound, "WIKI_NOT_PUBLIC", "wiki is not public")
		return nil
	}
	return proj
}

// ── publicListWikiArticles ───────────────────────────────────────────────────

func (s *Server) publicListWikiArticles(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if s.checkWikiPublic(w, r, bookID) == nil {
		return
	}

	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	offset, _ := strconv.Atoi(q.Get("offset"))
	if offset < 0 {
		offset = 0
	}

	// Build WHERE — only published articles, non-deleted entities
	where := []string{"wa.book_id = $1", "wa.status = 'published'"}
	args := []any{bookID}
	argN := 2

	if kindCode := q.Get("kind_code"); kindCode != "" {
		where = append(where, fmt.Sprintf("ek.code = $%d", argN))
		args = append(args, kindCode)
		argN++
	}
	if search := q.Get("search"); search != "" {
		where = append(where, fmt.Sprintf("dn.original_value ILIKE '%%' || $%d || '%%'", argN))
		args = append(args, search)
		argN++
	}

	whereClause := strings.Join(where, " AND ")

	var total int
	countSQL := fmt.Sprintf(`
		SELECT COUNT(*)
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_def_id FROM attribute_definitions ad
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)
		WHERE %s AND ge.deleted_at IS NULL`, whereClause)
	if err := s.pool.QueryRow(r.Context(), countSQL, args...).Scan(&total); err != nil {
		slog.Error("publicListWikiArticles count", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	fetchSQL := fmt.Sprintf(`
		SELECT
			wa.article_id, wa.entity_id, wa.book_id,
			COALESCE(dn.original_value, '') AS display_name,
			ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.status, wa.template_code,
			wa.updated_at
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_def_id FROM attribute_definitions ad
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			)
		WHERE %s AND ge.deleted_at IS NULL
		ORDER BY wa.updated_at DESC
		LIMIT $%d OFFSET $%d`, whereClause, argN, argN+1)
	args = append(args, limit, offset)

	rows, err := s.pool.Query(r.Context(), fetchSQL, args...)
	if err != nil {
		slog.Error("publicListWikiArticles fetch", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	type publicListItem struct {
		ArticleID    string      `json:"article_id"`
		EntityID     string      `json:"entity_id"`
		DisplayName  string      `json:"display_name"`
		Kind         kindSummary `json:"kind"`
		TemplateCode *string     `json:"template_code"`
		UpdatedAt    time.Time   `json:"updated_at"`
	}
	items := []publicListItem{}
	for rows.Next() {
		var it publicListItem
		var status string
		var bookIDScan string
		if err := rows.Scan(
			&it.ArticleID, &it.EntityID, &bookIDScan,
			&it.DisplayName,
			&it.Kind.KindID, &it.Kind.Code, &it.Kind.Name, &it.Kind.Icon, &it.Kind.Color,
			&status, &it.TemplateCode,
			&it.UpdatedAt,
		); err != nil {
			slog.Error("publicListWikiArticles scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		slog.Error("publicListWikiArticles rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

// ── publicGetWikiArticle ─────────────────────────────────────────────────────

func (s *Server) publicGetWikiArticle(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if s.checkWikiPublic(w, r, bookID) == nil {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}

	// Verify article exists, belongs to book, AND is published
	var exists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM wiki_articles WHERE article_id=$1 AND book_id=$2 AND status='published')`,
		articleID, bookID).Scan(&exists); err != nil || !exists {
		writeError(w, http.StatusNotFound, "WIKI_NOT_FOUND", "wiki article not found")
		return
	}

	// Parse max_chapter_index for spoiler filtering
	maxChapterIndex := -1
	if mci := r.URL.Query().Get("max_chapter_index"); mci != "" {
		if v, err := strconv.Atoi(mci); err == nil && v >= 0 {
			maxChapterIndex = v
		}
	}

	// Load full article detail (reuse existing loader)
	detail, err := s.loadWikiArticleDetail(r, bookID, articleID)
	if err != nil {
		slog.Error("publicGetWikiArticle load", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Check spoiler: if article spoils chapters beyond reader's progress, redact body
	spoilerWarning := false
	if maxChapterIndex >= 0 && len(detail.SpoilerChapters) > 0 {
		// We need to check if any spoiler chapter has an index > maxChapterIndex.
		// spoiler_chapters are UUIDs — we need to resolve their indices.
		// For simplicity, fetch chapter indices from book-service.
		chapters, chStatus := s.fetchBookChapters(r.Context(), bookID)
		if chStatus == http.StatusOK {
			chapterIndexMap := make(map[string]int)
			for _, ch := range chapters {
				chapterIndexMap[ch.ChapterID.String()] = ch.SortOrder
			}
			for _, spoilerChID := range detail.SpoilerChapters {
				if idx, ok := chapterIndexMap[spoilerChID]; ok && idx > maxChapterIndex {
					spoilerWarning = true
					break
				}
			}
		}
	}

	// Build public response (strip revision_count, add spoiler_warning)
	resp := map[string]any{
		"article_id":       detail.ArticleID,
		"entity_id":        detail.EntityID,
		"display_name":     detail.DisplayName,
		"kind":             detail.Kind,
		"template_code":    detail.TemplateCode,
		"spoiler_chapters": detail.SpoilerChapters,
		"spoiler_warning":  spoilerWarning,
		"infobox":          detail.Infobox,
		"updated_at":       detail.UpdatedAt,
		"created_at":       detail.CreatedAt,
	}

	if spoilerWarning {
		// Redact body — return empty doc instead
		resp["body_json"] = json.RawMessage(`{"type":"doc","content":[]}`)
	} else {
		resp["body_json"] = detail.BodyJSON
	}

	writeJSON(w, http.StatusOK, resp)
}
