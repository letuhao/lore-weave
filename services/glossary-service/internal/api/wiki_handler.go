package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
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
	// wiki-llm M7b — AI-generation badge driver. NULL (human-authored / never
	// AI-generated) | 'generated' | 'needs_review' | 'blocked'. omitempty so a
	// plain article carries no badge field.
	GenerationStatus *string `json:"generation_status,omitempty"`
	// wiki-llm Phase-2 — a knowledge source the article was built from changed; the
	// FE shows an "Outdated" badge. Cleared on regenerate (§5.3).
	IsKnowledgeStale bool `json:"is_knowledge_stale"`
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
	// RedirectedFrom is set (to the requested article_id) when the requested
	// article was archived by a merge (superseded) and this detail is the winner's
	// article served in its place (Bug-1 redirect). Omitted on a normal fetch.
	RedirectedFrom string `json:"redirected_from,omitempty"`
	// SupersededBy is the winner entity of a merge that archived this article
	// (Bug-1). Internal — drives the getWikiArticle redirect; not serialized.
	SupersededBy *uuid.UUID `json:"-"`
	// wiki-llm M7b — AI-generation provenance for the reader trust layer.
	// GenerationProvenance carries the C7 build_inputs fingerprint + citations +
	// verify_flags (the needs_review/blocked driver); GeneratedAt the timestamp.
	// omitempty so a human-authored article exposes none of these.
	GenerationProvenance json.RawMessage `json:"generation_provenance,omitempty"`
	GeneratedAt          *time.Time      `json:"generated_at,omitempty"`
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
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
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_id FROM book_attributes ad
				JOIN book_genres g ON g.genre_id = ad.genre_id
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1
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
			ek.book_kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.status, wa.template_code,
			(SELECT COUNT(*) FROM wiki_revisions wr WHERE wr.article_id = wa.article_id) AS revision_count,
			wa.updated_at, wa.generation_status, wa.is_knowledge_stale
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_id FROM book_attributes ad
				JOIN book_genres g ON g.genre_id = ad.genre_id
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1
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
			&it.UpdatedAt, &it.GenerationStatus, &it.IsKnowledgeStale,
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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

	const maxBodySize = 2 * 1024 * 1024 // 2 MB
	bodyJSON := json.RawMessage("{}")
	if req.BodyJSON != nil && len(req.BodyJSON) > 0 {
		if len(req.BodyJSON) > maxBodySize {
			writeError(w, http.StatusRequestEntityTooLarge, "WIKI_BODY_TOO_LARGE", "body_json exceeds 2 MB limit")
			return
		}
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
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

	// Bug-1 redirect: if this article was archived by a merge (superseded_by set),
	// serve the winner's article instead so links to a merged-away entity resolve.
	// superseded_by comes from the same detail query — no extra round-trip on the
	// common (non-superseded) path.
	if detail.SupersededBy != nil {
		var winnerArticleID uuid.UUID
		if e := s.pool.QueryRow(r.Context(),
			`SELECT article_id FROM wiki_articles WHERE entity_id=$1 AND book_id=$2 AND superseded_by_entity_id IS NULL`,
			*detail.SupersededBy, bookID,
		).Scan(&winnerArticleID); e == nil {
			winner, werr := s.loadWikiArticleDetail(r, bookID, winnerArticleID)
			if werr != nil {
				slog.Error("getWikiArticle redirect", "error", werr)
				writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
				return
			}
			winner.RedirectedFrom = articleID.String()
			writeJSON(w, http.StatusOK, winner)
			return
		}
		// winner article missing → fall through and serve the archived article as-is.
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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

	// Validate body size
	const maxBodySize = 2 * 1024 * 1024 // 2 MB
	if req.BodyJSON != nil && len(req.BodyJSON) > maxBodySize {
		writeError(w, http.StatusRequestEntityTooLarge, "WIKI_BODY_TOO_LARGE", "body_json exceeds 2 MB limit")
		return
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
		// wiki-llm M8 — feedback flywheel: if this owner edit lands on an
		// AI-authored article (its latest revision BEFORE this edit is 'ai'), the
		// pair (ai draft → owner edit) is correction gold. Capture the prior state
		// now, emit wiki.corrected after the new revision lands (all in-tx).
		var emitCorrected bool
		var corrEntityID uuid.UUID
		var corrGenStatus *string
		var priorAuthor *string
		if err := tx.QueryRow(r.Context(), `
			SELECT wa.entity_id, wa.generation_status,
			       (SELECT wr.author_type FROM wiki_revisions wr
			        WHERE wr.article_id = wa.article_id ORDER BY wr.version DESC LIMIT 1)
			FROM wiki_articles wa WHERE wa.article_id=$1`,
			articleID,
		).Scan(&corrEntityID, &corrGenStatus, &priorAuthor); err != nil {
			slog.Error("patchWikiArticle prior-rev lookup", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		emitCorrected = priorAuthor != nil && *priorAuthor == "ai"

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

		if emitCorrected {
			exec := func(ctx context.Context, sql string, args ...any) error {
				_, e := tx.Exec(ctx, sql, args...)
				return e
			}
			prior := ""
			if corrGenStatus != nil {
				prior = *corrGenStatus
			}
			if err := insertWikiCorrectedOutboxEvent(r.Context(), exec, articleID, wikiCorrectedPayload{
				BookID:                bookID.String(),
				ArticleID:             articleID.String(),
				EntityID:              corrEntityID.String(),
				UserID:                userID.String(),
				PriorGenerationStatus: prior,
				EmittedAt:             time.Now().UTC().Format(time.RFC3339),
			}); err != nil {
				slog.Error("patchWikiArticle emit wiki.corrected", "error", err)
				writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
				return
			}
			// /review-impl F2 — the human now owns this article: clear the AI
			// markers so a stale needs_review/blocked badge + verify-flags panel
			// don't persist on a human-corrected article. The prior status is
			// already captured in the event above; the AI-origin audit lives in
			// the revision history + the wiki.corrected event.
			if _, err := tx.Exec(r.Context(),
				`UPDATE wiki_articles SET generation_status=NULL, generation_provenance=NULL WHERE article_id=$1`,
				articleID,
			); err != nil {
				slog.Error("patchWikiArticle clear gen markers", "error", err)
				writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
				return
			}
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		slog.Error("deleteWikiArticle tx", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	var delEntityID uuid.UUID
	if err := tx.QueryRow(r.Context(),
		`DELETE FROM wiki_articles WHERE article_id=$1 RETURNING entity_id`, articleID).Scan(&delEntityID); err != nil {
		slog.Error("deleteWikiArticle", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	// Bug-2: emit wiki.deleted in the SAME tx (transactional outbox) so delete + event
	// are atomic — consistent with the kind-delete path; observable destruction.
	exec := func(ctx context.Context, sql string, args ...any) error {
		_, e := tx.Exec(ctx, sql, args...)
		return e
	}
	if err := insertWikiDeletedOutboxEvent(r.Context(), exec, articleID, wikiDeletedPayload{
		BookID:    bookID.String(),
		ArticleID: articleID.String(),
		EntityID:  delEntityID.String(),
		Reason:    "user_deleted",
		EmittedAt: time.Now().UTC().Format(time.RFC3339),
	}); err != nil {
		slog.Error("deleteWikiArticle emit wiki.deleted", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("deleteWikiArticle commit", "error", err)
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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

// injectGenSelectionCounts adds `total_matched` and `selected` to a wiki-gen
// delegate's JSON-object response body (D-WIKI-M7B-GEN-LIMIT). `selected` is
// the number of entities actually enqueued (== job item count); `total_matched`
// is how many matched before the genLimit cap. The FE compares them to warn
// "generating N of M". A body that isn't a JSON object (or fails to round-trip)
// is returned unchanged — surfacing the counts is best-effort, never fatal.
func injectGenSelectionCounts(body []byte, totalMatched, selected int) []byte {
	var obj map[string]any
	if err := json.Unmarshal(body, &obj); err != nil || obj == nil {
		return body
	}
	obj["total_matched"] = totalMatched
	obj["selected"] = selected
	merged, err := json.Marshal(obj)
	if err != nil {
		return body
	}
	return merged
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	// PP-3 (spec 08 R5) — a diary has NO wiki. generateWikiStubs AUTO-WRITES prose about an entity
	// ("Auto-generated from KG") REGARDLESS of visibility, so the visibility chokepoint (PP-2) is not
	// enough here — the article must never be MANUFACTURED for a diary colleague in the first place.
	if s.refuseDiaryWikiSurface(w, r, bookID) {
		return
	}

	var req struct {
		KindCodes []string `json:"kind_codes"`
		Limit     *int     `json:"limit"`
		// wiki-llm M6 — when ModelRef is set the request is DELEGATED to
		// knowledge-service's LLM batch generator instead of the deterministic
		// stub render. ModelSource defaults to "user_model".
		ModelRef    string   `json:"model_ref"`
		ModelSource string   `json:"model_source"`
		MaxSpendUSD *float64 `json:"max_spend_usd"`
		// wiki-llm M7b-2b — explicit entity ids for single-article REGENERATE.
		// When present (delegate path only), these are generated directly instead
		// of resolving by kind — so a "Regenerate" button re-runs exactly one
		// entity (the clobber-guard still protects any human-edited article).
		EntityIDs []string `json:"entity_ids"`
		// wiki-llm W5 — optional override model for the corrective revise re-gen
		// (null/empty ⇒ knowledge reuses the prose model). Forwarded as a pair.
		ReviseModelRef    string `json:"revise_model_ref"`
		ReviseModelSource string `json:"revise_model_source"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}

	genLimit := 50
	if req.Limit != nil && *req.Limit > 0 && *req.Limit <= 200 {
		genLimit = *req.Limit
	}

	// wiki-llm M6 — LLM delegate. Resolve the candidate entities + hand off to
	// knowledge-service; propagate its 202/409/404. The deterministic stub path
	// below is unchanged (the fallback when no model_ref is supplied).
	if req.ModelRef != "" {
		entityIDs, totalMatched, err := s.resolveDelegateEntityIDs(r.Context(), bookID, req.EntityIDs, req.KindCodes, genLimit)
		if err != nil {
			if verr, ok := err.(*badEntityIDError); ok {
				writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", verr.Error())
				return
			}
			slog.Error("generateWikiStubs resolve entities (delegate)", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		if len(entityIDs) == 0 {
			writeJSON(w, http.StatusOK, map[string]any{"action": "none", "entities": 0, "total_matched": totalMatched})
			return
		}
		modelSource := req.ModelSource
		if modelSource == "" {
			modelSource = "user_model"
		}
		// W5 — pair the revise source with its ref (default 'user_model' when a
		// revise ref is given without an explicit source); empty ref = no override.
		reviseSource := req.ReviseModelSource
		if req.ReviseModelRef != "" && reviseSource == "" {
			reviseSource = "user_model"
		}
		status, body, err := s.triggerWikiGeneration(
			r.Context(), bookID, userID, modelSource, req.ModelRef, entityIDs, req.MaxSpendUSD,
			reviseSource, req.ReviseModelRef)
		if err != nil {
			slog.Error("generateWikiStubs delegate", "error", err)
			writeError(w, http.StatusBadGateway, "WIKI_DELEGATE", "generation service unavailable")
			return
		}
		// D-WIKI-M7B-GEN-LIMIT — additively surface the selection counts on a
		// successful 202 so the FE can warn when the genLimit silently dropped
		// candidates (total_matched > selected). Best-effort: a body that isn't a
		// JSON object is forwarded unchanged.
		if status == http.StatusAccepted {
			body = injectGenSelectionCounts(body, totalMatched, len(entityIDs))
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write(body)
		return
	}

	// Find entities without wiki articles.
	// C5 (D4-03): also pull display_name + kind name so the renderer can
	// build a real body. The display_name subselect mirrors the
	// loadWikiArticleDetail pattern (first name/term attribute by
	// sort_order).
	querySQL := `
		SELECT ge.entity_id, ek.code, ek.name,
			COALESCE((
				SELECT eav.original_value FROM entity_attribute_values eav
				JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
				WHERE eav.entity_id = ge.entity_id AND ad.code IN ('name','term')
				ORDER BY ad.sort_order LIMIT 1
			), '') AS display_name
		FROM glossary_entities ge
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		WHERE ge.book_id = $1
		  AND ge.deleted_at IS NULL
		  AND ge.status = 'active'
		  AND NOT EXISTS (SELECT 1 FROM wiki_articles wa WHERE wa.entity_id = ge.entity_id)
		  -- PP-4 (spec 08 R6) — ENTITY-level guard: never manufacture a wiki page for a REAL PERSON.
		  -- The book-level PP-3 guard blocks a diary; this closes the cross-book/merged case (an entity
		  -- of the seeded work-person kind 'colleague' must not get an AI biography even if it ended up
		  -- in a wiki-eligible book). Scoped to 'colleague' (not all work kinds) so a legitimately-public
		  -- 'org' page is not over-blocked.
		  AND ek.code <> 'colleague'`

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
		EntityID    uuid.UUID
		KindCode    string
		KindName    string
		DisplayName string
	}
	var stubs []entityStub
	for rows.Next() {
		var s entityStub
		if err := rows.Scan(&s.EntityID, &s.KindCode, &s.KindName, &s.DisplayName); err != nil {
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

	// C5 (D4-03): render a real body per entity BEFORE opening the tx.
	// The KG-neighborhood read is a network call to knowledge-service —
	// we must not hold a DB transaction open across it. Each body is
	// assembled from the entity's glossary attributes (canon) + its
	// 1-hop KG neighborhood (relations, source_type-tagged). The KG read
	// degrades to nil (minimal body) when knowledge-service is
	// unavailable — wiki generation never hard-fails on a down KG (Q6).
	type renderedStub struct {
		entity entityStub
		body   json.RawMessage
	}
	rendered := make([]renderedStub, 0, len(stubs))
	for _, stub := range stubs {
		attrs, aerr := s.loadEntityWikiAttrs(r.Context(), stub.EntityID)
		if aerr != nil {
			// Attribute load failure is non-fatal — fall back to no
			// attributes; the body is still generated from name/kind/KG.
			slog.Warn("generateWikiStubs load attrs", "entity_id", stub.EntityID, "error", aerr)
			attrs = nil
		}
		neighborhood, _ := s.fetchWikiNeighborhood(r.Context(), userID, stub.EntityID)
		// T7 (B1 / F-C13-2): surface the enrichment supplement as a labeled
		// `dị bản` section. Non-fatal: a load failure falls back to no
		// supplement (the canon body still renders).
		enrichments, eerr := s.loadEntityEnrichments(r.Context(), stub.EntityID)
		if eerr != nil {
			slog.Warn("generateWikiStubs load enrichments", "entity_id", stub.EntityID, "error", eerr)
			enrichments = nil
		}
		body := renderWikiBody(wikiRenderInput{
			DisplayName:  stub.DisplayName,
			KindName:     stub.KindName,
			Attributes:   attrs,
			Neighborhood: neighborhood,
			Enrichments:  enrichments,
		})
		rendered = append(rendered, renderedStub{entity: stub, body: body})
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
	for _, rs := range rendered {
		var aid uuid.UUID
		err := tx.QueryRow(r.Context(), `
			INSERT INTO wiki_articles (entity_id, book_id, body_json, status, template_code)
			VALUES ($1, $2, $3, 'draft', $4)
			RETURNING article_id`,
			rs.entity.EntityID, bookID, rs.body, rs.entity.KindCode,
		).Scan(&aid)
		if err != nil {
			slog.Error("generateWikiStubs insert article", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		articleIDs = append(articleIDs, aid)

		if _, err := tx.Exec(r.Context(), `
			INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
			VALUES ($1, 1, $2, $3, 'system', 'Auto-generated from KG')`,
			aid, rs.body, userID,
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
			ek.book_kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.status, wa.template_code, 1 AS revision_count, wa.updated_at
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_id FROM book_attributes ad
				JOIN book_genres g ON g.genre_id = ad.genre_id
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1
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

// ── loadEntityWikiAttrs (C5 D4-03) ───────────────────────────────────────────
//
// Loads an entity's glossary attribute values for the wiki renderer.
// These are authored-canon attributes (source_type='glossary'). The
// display-name attribute (code name/term) is excluded — it becomes the
// article title, not a body row. Ordered by sort_order for stable,
// reproducible bodies.
func (s *Server) loadEntityWikiAttrs(ctx context.Context, entityID uuid.UUID) ([]wikiRenderAttr, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT ad.name, eav.original_value
		FROM entity_attribute_values eav
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		WHERE eav.entity_id = $1
		  AND ad.code NOT IN ('name','term')
		  AND eav.original_value <> ''
		ORDER BY ad.sort_order, ad.code`, entityID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var attrs []wikiRenderAttr
	for rows.Next() {
		var a wikiRenderAttr
		if err := rows.Scan(&a.Label, &a.Value); err != nil {
			return nil, err
		}
		attrs = append(attrs, a)
	}
	return attrs, rows.Err()
}

// loadEntityEnrichments reads the LIVE, PROMOTED enrichment-supplement rows for
// an entity (entity_enrichments, deleted_at IS NULL, review_status='promoted')
// so the wiki renderer can surface them as a distinguished `dị bản` section
// (B1 / F-C13-2 T7). Ordered deterministically.
//
// H0/quarantine (review-impl MED-1): ONLY 'promoted' (author-approved) supplements
// reach the wiki — 'proposed' rows are still quarantined makeup not yet approved
// by the author, and the wiki body is servable on the PUBLIC endpoints, so
// surfacing un-promoted content (even labeled) would leak quarantine to readers.
func (s *Server) loadEntityEnrichments(ctx context.Context, entityID uuid.UUID) ([]wikiRenderEnrichment, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT dimension, content, review_status, technique
		FROM entity_enrichments
		WHERE entity_id = $1 AND deleted_at IS NULL AND review_status = 'promoted'
		ORDER BY dimension, created_at`, entityID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []wikiRenderEnrichment
	for rows.Next() {
		var e wikiRenderEnrichment
		if err := rows.Scan(&e.Dimension, &e.Content, &e.ReviewStatus, &e.Technique); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

// ── loadWikiArticleDetail ────────────────────────────────────────────────────

func (s *Server) loadWikiArticleDetail(r *http.Request, bookID, articleID uuid.UUID) (*wikiArticleDetail, error) {
	var d wikiArticleDetail
	var spoilerChapters []uuid.UUID

	err := s.pool.QueryRow(r.Context(), `
		SELECT
			wa.article_id, wa.entity_id, wa.book_id,
			COALESCE(dn.original_value, '') AS display_name,
			ek.book_kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.status, wa.template_code,
			(SELECT COUNT(*) FROM wiki_revisions wr WHERE wr.article_id = wa.article_id) AS revision_count,
			wa.updated_at, wa.body_json, wa.spoiler_chapters, wa.created_at, wa.superseded_by_entity_id,
			wa.generation_status, wa.generation_provenance, wa.generated_at, wa.is_knowledge_stale
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_id FROM book_attributes ad
				JOIN book_genres g ON g.genre_id = ad.genre_id
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1
			)
		WHERE wa.article_id = $1 AND wa.book_id = $2`,
		articleID, bookID,
	).Scan(
		&d.ArticleID, &d.EntityID, &d.BookID,
		&d.DisplayName,
		&d.Kind.KindID, &d.Kind.Code, &d.Kind.Name, &d.Kind.Icon, &d.Kind.Color,
		&d.Status, &d.TemplateCode,
		&d.RevisionCount,
		&d.UpdatedAt, &d.BodyJSON, &spoilerChapters, &d.CreatedAt, &d.SupersededBy,
		&d.GenerationStatus, &d.GenerationProvenance, &d.GeneratedAt, &d.IsKnowledgeStale,
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
			ad.attr_id, ad.code, ad.name, ad.field_type, ad.is_required, false, ad.sort_order,
			eav.original_language, eav.original_value
		FROM entity_attribute_values eav
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
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
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_id FROM book_attributes ad
				JOIN book_genres g ON g.genre_id = ad.genre_id
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1
			)
		WHERE %s AND ge.deleted_at IS NULL`, whereClause)
	if err := s.pool.QueryRow(r.Context(), countSQL, args...).Scan(&total); err != nil {
		slog.Error("publicListWikiArticles count", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	fetchSQL := fmt.Sprintf(`
		SELECT
			wa.article_id, wa.entity_id,
			COALESCE(dn.original_value, '') AS display_name,
			ek.book_kind_id, ek.code, ek.name, ek.icon, ek.color,
			wa.template_code,
			wa.updated_at
		FROM wiki_articles wa
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_id FROM book_attributes ad
				JOIN book_genres g ON g.genre_id = ad.genre_id
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1
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
		if err := rows.Scan(
			&it.ArticleID, &it.EntityID,
			&it.DisplayName,
			&it.Kind.KindID, &it.Kind.Code, &it.Kind.Name, &it.Kind.Icon, &it.Kind.Color,
			&it.TemplateCode,
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

	// Check spoiler: if article spoils chapters beyond reader's progress, redact body.
	// Fail-closed: if we can't resolve chapter indices, assume spoiler to protect readers.
	spoilerWarning := false
	if maxChapterIndex >= 0 && len(detail.SpoilerChapters) > 0 {
		chapters, chStatus := s.fetchBookChapters(r.Context(), bookID)
		if chStatus != http.StatusOK {
			// Can't resolve chapter indices — fail-closed, assume spoiler
			spoilerWarning = true
		} else {
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

// ── Community Suggestions ────────────────────────────────────────────────────

type wikiSuggestionResp struct {
	SuggestionID       string          `json:"suggestion_id"`
	ArticleID          string          `json:"article_id"`
	UserID             string          `json:"user_id"`
	DiffJSON           json.RawMessage `json:"diff_json"`
	Reason             string          `json:"reason"`
	Status             string          `json:"status"`
	ReviewerNote       *string         `json:"reviewer_note"`
	CreatedAt          time.Time       `json:"created_at"`
	ReviewedAt         *time.Time      `json:"reviewed_at"`
	ArticleDisplayName string          `json:"article_display_name,omitempty"`
}

// ── 1. submitWikiSuggestion ──────────────────────────────────────────────────

func (s *Server) submitWikiSuggestion(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}

	// Check book exists and get wiki_settings + owner
	proj, status := s.fetchBookProjection(r.Context(), bookID)
	if status == http.StatusNotFound {
		writeError(w, http.StatusNotFound, "WIKI_BOOK_NOT_FOUND", "book not found")
		return
	}
	if status != http.StatusOK {
		writeError(w, http.StatusServiceUnavailable, "WIKI_UPSTREAM_UNAVAILABLE", "book service unavailable")
		return
	}

	// Owner cannot submit suggestions (they can edit directly)
	if proj.OwnerUserID == userID {
		writeError(w, http.StatusForbidden, "WIKI_OWNER_CANNOT_SUGGEST", "book owner should edit directly")
		return
	}

	// Check community_mode allows suggestions
	if proj.WikiSettings == nil || (proj.WikiSettings.CommunityMode != "suggest" && proj.WikiSettings.CommunityMode != "open") {
		writeError(w, http.StatusForbidden, "WIKI_SUGGESTIONS_DISABLED", "community suggestions are not enabled")
		return
	}

	// Verify article exists, belongs to book, and is published
	var exists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM wiki_articles WHERE article_id=$1 AND book_id=$2 AND status='published')`,
		articleID, bookID).Scan(&exists); err != nil || !exists {
		writeError(w, http.StatusNotFound, "WIKI_NOT_FOUND", "wiki article not found")
		return
	}

	var req struct {
		DiffJSON json.RawMessage `json:"diff_json"`
		Reason   string          `json:"reason"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}
	if req.DiffJSON == nil || len(req.DiffJSON) == 0 {
		writeError(w, http.StatusUnprocessableEntity, "WIKI_MISSING_DIFF", "diff_json is required")
		return
	}
	const maxDiffSize = 2 * 1024 * 1024 // 2 MB
	if len(req.DiffJSON) > maxDiffSize {
		writeError(w, http.StatusRequestEntityTooLarge, "WIKI_BODY_TOO_LARGE", "diff_json exceeds 2 MB limit")
		return
	}

	var sug wikiSuggestionResp
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO wiki_suggestions (article_id, user_id, diff_json, reason)
		VALUES ($1, $2, $3, $4)
		RETURNING suggestion_id, article_id, user_id, diff_json, reason, status, reviewer_note, created_at, reviewed_at`,
		articleID, userID, req.DiffJSON, req.Reason,
	).Scan(
		&sug.SuggestionID, &sug.ArticleID, &sug.UserID,
		&sug.DiffJSON, &sug.Reason, &sug.Status, &sug.ReviewerNote,
		&sug.CreatedAt, &sug.ReviewedAt,
	)
	if err != nil {
		slog.Error("submitWikiSuggestion insert", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusCreated, sug)
}

// ── 2. listWikiSuggestions (book-level) ──────────────────────────────────────

func (s *Server) listWikiSuggestions(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
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

	// Optional status filter
	where := []string{"wa.book_id = $1"}
	args := []any{bookID}
	argN := 2

	if statusFilter := q.Get("status"); statusFilter != "" {
		where = append(where, fmt.Sprintf("ws.status = $%d", argN))
		args = append(args, statusFilter)
		argN++
	}

	whereClause := strings.Join(where, " AND ")

	var total int
	countSQL := fmt.Sprintf(`
		SELECT COUNT(*)
		FROM wiki_suggestions ws
		JOIN wiki_articles wa ON wa.article_id = ws.article_id
		WHERE %s`, whereClause)
	if err := s.pool.QueryRow(r.Context(), countSQL, args...).Scan(&total); err != nil {
		slog.Error("listWikiSuggestions count", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	fetchSQL := fmt.Sprintf(`
		SELECT
			ws.suggestion_id, ws.article_id, ws.user_id,
			ws.diff_json, ws.reason, ws.status, ws.reviewer_note,
			ws.created_at, ws.reviewed_at,
			COALESCE(dn.original_value, '') AS display_name
		FROM wiki_suggestions ws
		JOIN wiki_articles wa ON wa.article_id = ws.article_id
		JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
			AND dn.attr_def_id = (
				SELECT ad.attr_id FROM book_attributes ad
				JOIN book_genres g ON g.genre_id = ad.genre_id
				WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
				ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1
			)
		WHERE %s
		ORDER BY ws.created_at DESC
		LIMIT $%d OFFSET $%d`, whereClause, argN, argN+1)
	args = append(args, limit, offset)

	rows, err := s.pool.Query(r.Context(), fetchSQL, args...)
	if err != nil {
		slog.Error("listWikiSuggestions fetch", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	items := []wikiSuggestionResp{}
	for rows.Next() {
		var it wikiSuggestionResp
		if err := rows.Scan(
			&it.SuggestionID, &it.ArticleID, &it.UserID,
			&it.DiffJSON, &it.Reason, &it.Status, &it.ReviewerNote,
			&it.CreatedAt, &it.ReviewedAt,
			&it.ArticleDisplayName,
		); err != nil {
			slog.Error("listWikiSuggestions scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		slog.Error("listWikiSuggestions rows", "error", err)
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

// ── 3. reviewWikiSuggestion (accept/reject) ──────────────────────────────────

func (s *Server) reviewWikiSuggestion(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	articleID, ok := parsePathUUID(w, r, "article_id")
	if !ok {
		return
	}
	if !s.verifyArticleInBook(w, r, articleID, bookID) {
		return
	}
	sugID, ok := parsePathUUID(w, r, "sug_id")
	if !ok {
		return
	}

	// Verify suggestion exists and belongs to this article
	var sugStatus string
	var diffJSON json.RawMessage
	var sugUserID uuid.UUID
	err := s.pool.QueryRow(r.Context(),
		`SELECT status, diff_json, user_id FROM wiki_suggestions WHERE suggestion_id=$1 AND article_id=$2`,
		sugID, articleID).Scan(&sugStatus, &diffJSON, &sugUserID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "WIKI_SUGGESTION_NOT_FOUND", "suggestion not found")
		return
	}
	if err != nil {
		slog.Error("reviewWikiSuggestion fetch", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	if sugStatus != "pending" {
		writeError(w, http.StatusConflict, "WIKI_SUGGESTION_ALREADY_REVIEWED", "suggestion already reviewed")
		return
	}

	var req struct {
		Action       string  `json:"action"`
		ReviewerNote *string `json:"reviewer_note"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}
	if req.Action != "accept" && req.Action != "reject" {
		writeError(w, http.StatusUnprocessableEntity, "WIKI_INVALID_ACTION", "action must be accept or reject")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		slog.Error("reviewWikiSuggestion tx begin", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	newStatus := req.Action + "ed" // "accepted" or "rejected"

	// Update suggestion status
	if _, err := tx.Exec(r.Context(), `
		UPDATE wiki_suggestions SET status=$1, reviewer_note=$2, reviewed_at=now()
		WHERE suggestion_id=$3`,
		newStatus, req.ReviewerNote, sugID,
	); err != nil {
		slog.Error("reviewWikiSuggestion update", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	if req.Action == "accept" {
		// An AI regeneration that the clobber-guard filed as a suggestion (because the
		// article had human edits) stores an ENVELOPE in diff_json —
		// {body_json, generation_status, generation_provenance} — NOT a raw body. A
		// human community suggestion stores the TipTap doc directly. Discriminate on
		// the envelope's two server-set keys (body_json + a validated generation_status)
		// — a TipTap doc, {"type":"doc",...}, carries neither, so a client-crafted diff
		// can't masquerade as a regen. For an AI regen we unwrap the real body and
		// restore the generation metadata, so the accepted article reflects the new AI
		// generation (badges/provenance correct) and is logged as an 'ai' revision —
		// future regens then overwrite it freely instead of re-filing suggestions.
		var env struct {
			BodyJSON             json.RawMessage `json:"body_json"`
			GenerationStatus     *string         `json:"generation_status"`
			GenerationProvenance json.RawMessage `json:"generation_provenance"`
		}
		_ = json.Unmarshal(diffJSON, &env)
		isAIRegen := env.BodyJSON != nil && env.GenerationStatus != nil

		applyBody := diffJSON
		authorType := "community"
		summary := "Community suggestion accepted"
		if isAIRegen {
			applyBody = env.BodyJSON
			authorType = "ai"
			summary = "AI regeneration accepted"
		}

		// Lock article for revision version safety
		if _, err := tx.Exec(r.Context(),
			`SELECT 1 FROM wiki_articles WHERE article_id=$1 FOR UPDATE`, articleID); err != nil {
			slog.Error("reviewWikiSuggestion lock", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}

		// Apply the accepted body. An AI regen also restores its generation metadata.
		if isAIRegen {
			if _, err := tx.Exec(r.Context(), `
				UPDATE wiki_articles
				   SET body_json=$1, generation_status=$2, generation_provenance=$3,
				       generated_at=now(), updated_at=now()
				 WHERE article_id=$4`,
				applyBody, env.GenerationStatus, env.GenerationProvenance, articleID,
			); err != nil {
				slog.Error("reviewWikiSuggestion apply", "error", err)
				writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
				return
			}
		} else if _, err := tx.Exec(r.Context(),
			`UPDATE wiki_articles SET body_json=$1, updated_at=now() WHERE article_id=$2`,
			applyBody, articleID,
		); err != nil {
			slog.Error("reviewWikiSuggestion apply", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}

		// Create the revision: 'community' for a human suggestion, 'ai' for a regen.
		if _, err := tx.Exec(r.Context(), `
			INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
			VALUES ($1, COALESCE((SELECT MAX(version) FROM wiki_revisions WHERE article_id=$1), 0) + 1, $2, $3, $4, $5)`,
			articleID, applyBody, sugUserID, authorType, summary,
		); err != nil {
			slog.Error("reviewWikiSuggestion revision", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}

		// wiki-llm Phase-2b (D-WIKI-P2B-SUGGESTION-RESOLVE) — accepting a suggestion
		// brings the article up to date, so resolve its pending staleness ledger rows
		// and clear the denormalized "Outdated" flag (symmetric with the direct-write
		// resolve in wiki_writeback.go). A REJECT intentionally leaves the staleness
		// pending — the changed source is still unaddressed.
		if _, err := tx.Exec(r.Context(),
			`UPDATE wiki_staleness SET status='regenerated' WHERE article_id=$1 AND status='pending'`,
			articleID,
		); err != nil {
			slog.Error("reviewWikiSuggestion resolve staleness", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		if _, err := tx.Exec(r.Context(),
			`UPDATE wiki_articles SET is_knowledge_stale=false WHERE article_id=$1`,
			articleID,
		); err != nil {
			slog.Error("reviewWikiSuggestion clear stale flag", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	}

	// wiki-llm M8 — emit the review signal for the feedback flywheel (in-tx).
	// `was_ai_generated` lets the consumer weight a correction of an AI article
	// differently from a human-authored one.
	var revGenStatus *string
	if err := tx.QueryRow(r.Context(),
		`SELECT generation_status FROM wiki_articles WHERE article_id=$1`, articleID,
	).Scan(&revGenStatus); err != nil {
		slog.Error("reviewWikiSuggestion gen-status lookup", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	exec := func(ctx context.Context, sql string, args ...any) error {
		_, e := tx.Exec(ctx, sql, args...)
		return e
	}
	if err := insertWikiSuggestionReviewedOutboxEvent(r.Context(), exec, articleID, wikiSuggestionReviewedPayload{
		BookID:         bookID.String(),
		ArticleID:      articleID.String(),
		SuggestionID:   sugID.String(),
		UserID:         userID.String(),
		Action:         req.Action,
		WasAIGenerated: revGenStatus != nil,
		EmittedAt:      time.Now().UTC().Format(time.RFC3339),
	}); err != nil {
		slog.Error("reviewWikiSuggestion emit wiki.suggestion_reviewed", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("reviewWikiSuggestion commit", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// Return updated suggestion
	var sug wikiSuggestionResp
	if err := s.pool.QueryRow(r.Context(), `
		SELECT suggestion_id, article_id, user_id, diff_json, reason, status, reviewer_note, created_at, reviewed_at
		FROM wiki_suggestions WHERE suggestion_id=$1`, sugID,
	).Scan(
		&sug.SuggestionID, &sug.ArticleID, &sug.UserID,
		&sug.DiffJSON, &sug.Reason, &sug.Status, &sug.ReviewerNote,
		&sug.CreatedAt, &sug.ReviewedAt,
	); err != nil {
		slog.Error("reviewWikiSuggestion reload", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, sug)
}
