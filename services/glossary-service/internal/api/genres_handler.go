package api

import (
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/loreweave/glossary-service/internal/domain"
)

// listGenres returns all genre groups for a book, sorted by sort_order.
func (s *Server) listGenres(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	bookID := chi.URLParam(r, "book_id")
	ctx := r.Context()

	rows, err := s.pool.Query(ctx, `
		SELECT id, book_id, name, color, description, sort_order, created_at
		FROM genre_groups
		WHERE book_id = $1
		ORDER BY sort_order, name`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query genres")
		return
	}
	defer rows.Close()

	out := make([]domain.GenreGroup, 0)
	for rows.Next() {
		var g domain.GenreGroup
		var createdAt time.Time
		if err := rows.Scan(&g.ID, &g.BookID, &g.Name, &g.Color, &g.Description, &g.SortOrder, &createdAt); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan genre")
			return
		}
		g.CreatedAt = createdAt.Format(time.RFC3339)
		out = append(out, g)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to iterate genres")
		return
	}

	writeJSON(w, http.StatusOK, out)
}
