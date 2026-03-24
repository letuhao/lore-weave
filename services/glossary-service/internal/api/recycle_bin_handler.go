package api

import (
	"net/http"
	"strconv"
	"time"
)

// ── Types ─────────────────────────────────────────────────────────────────────

// entityTrashItem is the shape returned by the recycle bin list endpoint.
// Kind display fields are read from entity_snapshot to avoid extra joins.
type entityTrashItem struct {
	EntityID    string    `json:"entity_id"`
	BookID      string    `json:"book_id"`
	DeletedAt   time.Time `json:"deleted_at"`
	Status      string    `json:"status"`
	KindCode    string    `json:"kind_code"`
	KindName    string    `json:"kind_name"`
	KindIcon    string    `json:"kind_icon"`
	KindColor   string    `json:"kind_color"`
	DisplayName string    `json:"display_name"`
}

type entityTrashListResp struct {
	Items  []entityTrashItem `json:"items"`
	Total  int               `json:"total"`
	Limit  int               `json:"limit"`
	Offset int               `json:"offset"`
}

// ── helpers ───────────────────────────────────────────────────────────────────

func parseIntDefault(s string, def int) int {
	if s == "" {
		return def
	}
	v, err := strconv.Atoi(s)
	if err != nil || v < 0 {
		return def
	}
	return v
}

// ── GET /v1/glossary/books/{book_id}/recycle-bin ──────────────────────────────

func (s *Server) listEntityTrash(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
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
	limit := parseIntDefault(q.Get("limit"), 20)
	offset := parseIntDefault(q.Get("offset"), 0)
	if limit > 100 {
		limit = 100
	}

	ctx := r.Context()

	var total int
	if err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM glossary_entities
		 WHERE book_id = $1
		   AND deleted_at IS NOT NULL
		   AND permanently_deleted_at IS NULL`,
		bookID).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
		return
	}

	rows, err := s.pool.Query(ctx, `
		SELECT entity_id::text, book_id::text, deleted_at, status,
		       COALESCE(entity_snapshot->'kind'->>'code',  '') AS kind_code,
		       COALESCE(entity_snapshot->'kind'->>'name',  '') AS kind_name,
		       COALESCE(entity_snapshot->'kind'->>'icon',  '') AS kind_icon,
		       COALESCE(entity_snapshot->'kind'->>'color', '') AS kind_color,
		       COALESCE((
		           SELECT attr->>'original_value'
		           FROM jsonb_array_elements(entity_snapshot->'attributes') AS attr
		           WHERE attr->>'code' IN ('name', 'term')
		             AND attr->>'original_value' != ''
		           LIMIT 1
		       ), '') AS display_name
		FROM glossary_entities
		WHERE book_id = $1
		  AND deleted_at IS NOT NULL
		  AND permanently_deleted_at IS NULL
		ORDER BY deleted_at DESC
		LIMIT $2 OFFSET $3`,
		bookID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := []entityTrashItem{}
	for rows.Next() {
		var it entityTrashItem
		if err := rows.Scan(
			&it.EntityID, &it.BookID, &it.DeletedAt, &it.Status,
			&it.KindCode, &it.KindName, &it.KindIcon, &it.KindColor,
			&it.DisplayName,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	writeJSON(w, http.StatusOK, entityTrashListResp{
		Items:  items,
		Total:  total,
		Limit:  limit,
		Offset: offset,
	})
}

// ── POST /v1/glossary/books/{book_id}/recycle-bin/{entity_id}/restore ─────────

func (s *Server) restoreEntity(w http.ResponseWriter, r *http.Request) {
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

	ctx := r.Context()
	tag, err := s.pool.Exec(ctx,
		`UPDATE glossary_entities
		 SET deleted_at = NULL, updated_at = now()
		 WHERE entity_id = $1 AND book_id = $2
		   AND deleted_at IS NOT NULL
		   AND permanently_deleted_at IS NULL`,
		entityID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not in trash")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── DELETE /v1/glossary/books/{book_id}/recycle-bin/{entity_id} ───────────────

// purgeEntity flags the entity for permanent deletion.
// Does not physically delete the row; GC is handled separately.
func (s *Server) purgeEntity(w http.ResponseWriter, r *http.Request) {
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

	ctx := r.Context()
	tag, err := s.pool.Exec(ctx,
		`UPDATE glossary_entities
		 SET permanently_deleted_at = now()
		 WHERE entity_id = $1 AND book_id = $2
		   AND deleted_at IS NOT NULL
		   AND permanently_deleted_at IS NULL`,
		entityID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "purge failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not in trash")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
