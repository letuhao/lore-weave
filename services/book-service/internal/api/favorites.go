package api

import (
	"context"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// canViewOrPublic reports whether userID may favorite/list bookID: either they
// hold a ≥view grant (owner/collaborator) OR the book is public/unlisted
// (catalog). Fail-closed — a missing book or a sharing-service failure (where
// fetchSharingVisibility defaults to "private") yields false. This is the gate
// that stops favoriting being a metadata oracle on private books
// (D-FAVORITES-METADATA-LEAK).
func (s *Server) canViewOrPublic(ctx context.Context, bookID, userID uuid.UUID) bool {
	if lvl, err := s.resolveGrant(ctx, bookID, userID); err == nil && lvl.AtLeast(GrantView) {
		return true
	}
	switch s.fetchSharingVisibility(ctx, bookID) {
	case "public", "unlisted":
		return true
	default:
		return false
	}
}

func (s *Server) addFavorite(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_AUTH_ERROR", "authentication required")
		return
	}
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book_id")
		return
	}
	// Only favorite books the caller can actually see (a grant or a public book).
	// Missing/private/inaccessible → 404 (uniform, no existence oracle).
	if !s.canViewOrPublic(r.Context(), bookID, userID) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	_, _ = s.pool.Exec(r.Context(), `
		INSERT INTO user_favorites (user_id, book_id) VALUES ($1, $2)
		ON CONFLICT DO NOTHING`, userID, bookID)
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) removeFavorite(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_AUTH_ERROR", "authentication required")
		return
	}
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book_id")
		return
	}
	_, _ = s.pool.Exec(r.Context(), `DELETE FROM user_favorites WHERE user_id=$1 AND book_id=$2`, userID, bookID)
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) checkFavorite(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_AUTH_ERROR", "authentication required")
		return
	}
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book_id")
		return
	}
	var exists bool
	_ = s.pool.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM user_favorites WHERE user_id=$1 AND book_id=$2)`, userID, bookID).Scan(&exists)
	writeJSON(w, http.StatusOK, map[string]any{"is_favorited": exists})
}

func (s *Server) listFavorites(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_AUTH_ERROR", "authentication required")
		return
	}
	limit := 20
	offset := 0
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 100 {
			limit = n
		}
	}
	if v := r.URL.Query().Get("offset"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			offset = n
		}
	}

	// access_level computed locally; a row the caller has no grant on is only
	// returned if the book is public/unlisted — else its metadata would leak
	// (D-FAVORITES-METADATA-LEAK). access_level='none' rows fall to a per-row
	// visibility RPC, bounded by the page limit.
	rows, err := s.pool.Query(r.Context(), `
		SELECT b.id, b.title, b.description, b.original_language, b.genre_tags, b.created_at, f.created_at,
		  CASE WHEN b.owner_user_id=$1 THEN 'owner'
		       ELSE COALESCE((SELECT role FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1),'none') END AS access_level
		FROM user_favorites f
		JOIN books b ON b.id = f.book_id
		WHERE f.user_id = $1 AND b.lifecycle_state = 'active'
		ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_INTERNAL_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	for rows.Next() {
		var bookID uuid.UUID
		var title, accessLevel string
		var description, language *string
		var genreTags []string
		var createdAt, favoritedAt any
		if err := rows.Scan(&bookID, &title, &description, &language, &genreTags, &createdAt, &favoritedAt, &accessLevel); err != nil {
			continue
		}
		// No grant → only surface metadata if the book is public/unlisted.
		if accessLevel == "none" {
			switch s.fetchSharingVisibility(r.Context(), bookID) {
			case "public", "unlisted":
			default:
				continue
			}
		}
		if genreTags == nil {
			genreTags = []string{}
		}
		items = append(items, map[string]any{
			"book_id":           bookID,
			"title":             title,
			"description":       description,
			"original_language": language,
			"genre_tags":        genreTags,
			"access_level":      accessLevel,
			"created_at":        createdAt,
			"favorited_at":      favoritedAt,
		})
	}

	// total = all active favorites. addFavorite gates accessibility at the source,
	// so this drifts from the filtered page only for the rare favorite-then-lost-
	// access case (a slight over-count, never a metadata leak).
	var total int64
	_ = s.pool.QueryRow(r.Context(), `
		SELECT COUNT(*) FROM user_favorites f JOIN books b ON b.id = f.book_id
		WHERE f.user_id = $1 AND b.lifecycle_state = 'active'`, userID).Scan(&total)

	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}
