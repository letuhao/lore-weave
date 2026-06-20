package api

// G2 — genre tier CRUD (genre·kind·attribute re-architecture, 2026-06-19).
// Spec docs/specs/2026-06-19-genre-kind-attribute-tiering.md.
//
// System genres are admin/seed-only (read merged via listGenres). User genres
// live in user_genres, scoped by owner_user_id (CLAUDE.md › User Boundaries &
// Tenancy): every query filters on the caller's user id, so user A can never
// read or mutate user B's genres. A user CLONES a System genre into their own
// tier (the clone keeps the same `code`), never edits the shared original.
//
// Mirrors the SS-4 user-kinds surface (user_kind_handler.go): owner-scoped CRUD
// + a soft-delete recycle bin (deleted_at / permanently_deleted_at).

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// ── response types ───────────────────────────────────────────────────────────

type genreResp struct {
	GenreID           string    `json:"genre_id"`
	Tier              string    `json:"tier"`
	OwnerUserID       *string   `json:"owner_user_id,omitempty"`
	Code              string    `json:"code"`
	Name              string    `json:"name"`
	Icon              string    `json:"icon"`
	Color             string    `json:"color"`
	SortOrder         int       `json:"sort_order"`
	ClonedFromGenreID *string   `json:"cloned_from_genre_id,omitempty"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
}

type userGenreListResp struct {
	Items  []genreResp `json:"items"`
	Total  int         `json:"total"`
	Limit  int         `json:"limit"`
	Offset int         `json:"offset"`
}

type genreTrashItem struct {
	GenreID   string    `json:"genre_id"`
	Code      string    `json:"code"`
	Name      string    `json:"name"`
	Icon      string    `json:"icon"`
	Color     string    `json:"color"`
	DeletedAt time.Time `json:"deleted_at"`
}

// ── merged read (System + caller's User tier) ─────────────────────────────────

func (s *Server) listStandardGenres(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	q := r.URL.Query()
	inclSystem := q.Get("include_system") != "false"
	inclUser := q.Get("include_user") != "false"

	ctx := r.Context()
	items := []genreResp{}

	if inclSystem {
		rows, err := s.pool.Query(ctx, `
			SELECT genre_id::text, code, name, icon, color, sort_order, created_at, updated_at
			FROM system_genres ORDER BY sort_order, code`)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "system genres query failed")
			return
		}
		defer rows.Close()
		for rows.Next() {
			var g genreResp
			g.Tier = "system"
			if err := rows.Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.CreatedAt, &g.UpdatedAt); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
				return
			}
			items = append(items, g)
		}
		if err := rows.Err(); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
			return
		}
	}

	if inclUser {
		rows, err := s.pool.Query(ctx, `
			SELECT genre_id::text, owner_user_id::text, code, name, icon, color, sort_order,
			       cloned_from_genre_id::text, created_at, updated_at
			FROM user_genres
			WHERE owner_user_id = $1 AND deleted_at IS NULL AND permanently_deleted_at IS NULL
			ORDER BY sort_order, code`, userID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "user genres query failed")
			return
		}
		defer rows.Close()
		for rows.Next() {
			var g genreResp
			g.Tier = "user"
			if err := rows.Scan(&g.GenreID, &g.OwnerUserID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder,
				&g.ClonedFromGenreID, &g.CreatedAt, &g.UpdatedAt); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
				return
			}
			items = append(items, g)
		}
		if err := rows.Err(); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
			return
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// ── helpers ──────────────────────────────────────────────────────────────────

// verifyUserGenreOwner confirms genre_id belongs to userID and is live (not
// trashed/purged). Writes 404/500 itself; returns true only when owned + live.
func (s *Server) verifyUserGenreOwner(w http.ResponseWriter, ctx context.Context, genreID, userID uuid.UUID) bool {
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM user_genres
		               WHERE genre_id=$1 AND owner_user_id=$2
		                 AND deleted_at IS NULL AND permanently_deleted_at IS NULL)`,
		genreID, userID,
	).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return false
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user genre not found")
		return false
	}
	return true
}

// loadUserGenre fetches one live user genre, owner-scoped. pgx.ErrNoRows if absent.
func (s *Server) loadUserGenre(ctx context.Context, genreID, userID uuid.UUID) (*genreResp, error) {
	var g genreResp
	g.Tier = "user"
	err := s.pool.QueryRow(ctx, `
		SELECT genre_id::text, owner_user_id::text, code, name, icon, color, sort_order,
		       cloned_from_genre_id::text, created_at, updated_at
		FROM user_genres
		WHERE genre_id=$1 AND owner_user_id=$2
		  AND deleted_at IS NULL AND permanently_deleted_at IS NULL`,
		genreID, userID,
	).Scan(&g.GenreID, &g.OwnerUserID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder,
		&g.ClonedFromGenreID, &g.CreatedAt, &g.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &g, nil
}

// ── genre CRUD ────────────────────────────────────────────────────────────────

func (s *Server) listUserGenres(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	q := r.URL.Query()
	limit := parseIntDefault(q.Get("limit"), 20)
	offset := parseIntDefault(q.Get("offset"), 0)
	if limit > 100 {
		limit = 100
	}
	if limit < 1 {
		limit = 1
	}
	if offset < 0 {
		offset = 0
	}
	orderClause := "created_at DESC"
	if q.Get("sort") == "name" {
		orderClause = "name ASC"
	}

	ctx := r.Context()
	var total int
	if err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM user_genres
		 WHERE owner_user_id=$1 AND deleted_at IS NULL AND permanently_deleted_at IS NULL`,
		userID).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
		return
	}

	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
		SELECT genre_id::text, owner_user_id::text, code, name, icon, color, sort_order,
		       cloned_from_genre_id::text, created_at, updated_at
		FROM user_genres
		WHERE owner_user_id=$1 AND deleted_at IS NULL AND permanently_deleted_at IS NULL
		ORDER BY %s
		LIMIT $2 OFFSET $3`, orderClause), userID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := []genreResp{}
	for rows.Next() {
		var g genreResp
		g.Tier = "user"
		if err := rows.Scan(&g.GenreID, &g.OwnerUserID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder,
			&g.ClonedFromGenreID, &g.CreatedAt, &g.UpdatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		items = append(items, g)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}
	writeJSON(w, http.StatusOK, userGenreListResp{Items: items, Total: total, Limit: limit, Offset: offset})
}

func (s *Server) createUserGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var in struct {
		Code             string  `json:"code"`
		Name             string  `json:"name"`
		Icon             string  `json:"icon"`
		Color            string  `json:"color"`
		SortOrder        int     `json:"sort_order"`
		CloneFromGenreID *string `json:"clone_from_genre_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if strings.TrimSpace(in.Name) == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "name is required")
		return
	}
	in.Name = strings.TrimSpace(in.Name) // normalize identically to the MCP tool path
	if in.Icon == "" {
		in.Icon = ""
	}
	if in.Color == "" {
		in.Color = "#6366f1"
	}
	if strings.TrimSpace(in.Code) == "" {
		in.Code = slugify(in.Name)
	}
	if in.Code == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "code could not be derived from name")
		return
	}

	var cloneFrom *uuid.UUID
	if in.CloneFromGenreID != nil && *in.CloneFromGenreID != "" {
		id, err := uuid.Parse(*in.CloneFromGenreID)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid clone_from_genre_id")
			return
		}
		cloneFrom = &id
	}

	var genreID uuid.UUID
	// content_hash = md5(code|name) — the SAME format the seed uses for system_genres
	// (migrate.go SeedGenreKindAttr) so the hash is comparable across tiers. This is
	// the baseline G5 Sync captures into book_genres.source_hash at adopt; without it
	// a user-sourced genre adopts as '' and Sync can never detect an edit (D-GKA-HASH-REFRESH).
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO user_genres (owner_user_id, code, name, icon, color, sort_order, cloned_from_genre_id, content_hash)
		VALUES ($1,$2,$3,$4,$5,$6,$7, md5($2||'|'||$3))
		RETURNING genre_id`,
		userID, in.Code, in.Name, in.Icon, in.Color, in.SortOrder, cloneFrom,
	).Scan(&genreID)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE", "a user genre with this code already exists")
			return
		}
		// clone_from_genre_id that isn't a real system genre trips the FK (23503).
		if isForeignKeyViolation(err) {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "clone_from_genre_id is not a system genre")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}

	detail, err := s.loadUserGenre(r.Context(), genreID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusCreated, detail)
}

func (s *Server) getUserGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	detail, err := s.loadUserGenre(r.Context(), genreID, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user genre not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (s *Server) patchUserGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	if !s.verifyUserGenreOwner(w, r.Context(), genreID, userID) {
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
	nameArgN := 0 // >0 once name is in the SET list — drives content_hash recompute below

	if raw, ok := in["name"]; ok {
		var v string
		if err := json.Unmarshal(raw, &v); err != nil || strings.TrimSpace(v) == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid name")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("name = $%d", argN))
		args = append(args, strings.TrimSpace(v)) // normalize identically to the MCP tool path
		nameArgN = argN
		argN++
	}
	for _, f := range []string{"icon", "color"} {
		if raw, ok := in[f]; ok {
			var v string
			if err := json.Unmarshal(raw, &v); err != nil {
				writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid "+f)
				return
			}
			setClauses = append(setClauses, fmt.Sprintf("%s = $%d", f, argN))
			args = append(args, v)
			argN++
		}
	}
	if raw, ok := in["sort_order"]; ok {
		var v int
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid sort_order")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("sort_order = $%d", argN))
		args = append(args, v)
		argN++
	}

	if len(setClauses) > 0 {
		// When name changes, recompute content_hash = md5(code|name) so G5 Sync sees the
		// edit. code is immutable here, so reference the live column + the new-name param.
		if nameArgN > 0 {
			setClauses = append(setClauses, fmt.Sprintf("content_hash = md5(code||'|'||$%d)", nameArgN))
		}
		setClauses = append(setClauses, "updated_at = now()")
		args = append(args, genreID, userID)
		updateSQL := fmt.Sprintf(
			"UPDATE user_genres SET %s WHERE genre_id = $%d AND owner_user_id = $%d",
			strings.Join(setClauses, ", "), argN, argN+1)
		if _, err := s.pool.Exec(r.Context(), updateSQL, args...); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
	}

	detail, err := s.loadUserGenre(r.Context(), genreID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (s *Server) deleteUserGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	if !s.verifyUserGenreOwner(w, r.Context(), genreID, userID) {
		return
	}

	// Guard: a genre still linked to a live user-kind (user_kind_genres) or carrying
	// user attributes can't be trashed — unlink/remove first. FK ON DELETE CASCADE
	// would silently drop links, so we 409 instead.
	var refCount int
	if err := s.pool.QueryRow(r.Context(),
		`SELECT (SELECT COUNT(*) FROM user_kind_genres WHERE genre_id=$1)
		      + (SELECT COUNT(*) FROM user_attributes WHERE genre_id=$1 AND deleted_at IS NULL)`,
		genreID,
	).Scan(&refCount); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "ref count failed")
		return
	}
	if refCount > 0 {
		writeError(w, http.StatusConflict, "GLOSS_GENRE_IN_USE",
			fmt.Sprintf("%d kind-links/attributes reference this genre; remove them first", refCount))
		return
	}

	tag, err := s.pool.Exec(r.Context(), `
		UPDATE user_genres SET deleted_at = now(), updated_at = now()
		WHERE genre_id = $1 AND owner_user_id = $2 AND deleted_at IS NULL`,
		genreID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user genre not found or already deleted")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── recycle bin ──────────────────────────────────────────────────────────────

func (s *Server) listUserGenreTrash(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	q := r.URL.Query()
	limit := parseIntDefault(q.Get("limit"), 20)
	offset := parseIntDefault(q.Get("offset"), 0)
	if limit > 100 {
		limit = 100
	}
	if limit < 1 {
		limit = 1
	}
	if offset < 0 {
		offset = 0
	}

	ctx := r.Context()
	var total int
	if err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM user_genres
		WHERE owner_user_id=$1 AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
		userID).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
		return
	}

	rows, err := s.pool.Query(ctx, `
		SELECT genre_id::text, code, name, icon, color, deleted_at
		FROM user_genres
		WHERE owner_user_id=$1 AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL
		ORDER BY deleted_at DESC
		LIMIT $2 OFFSET $3`, userID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := []genreTrashItem{}
	for rows.Next() {
		var it genreTrashItem
		if err := rows.Scan(&it.GenreID, &it.Code, &it.Name, &it.Icon, &it.Color, &it.DeletedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) restoreUserGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
		UPDATE user_genres SET deleted_at = NULL, updated_at = now()
		WHERE genre_id = $1 AND owner_user_id = $2
		  AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
		genreID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user genre not in trash")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) purgeUserGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
		UPDATE user_genres SET permanently_deleted_at = now()
		WHERE genre_id = $1 AND owner_user_id = $2
		  AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
		genreID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "purge failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user genre not in trash")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
