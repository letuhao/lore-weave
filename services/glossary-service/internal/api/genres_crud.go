package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/loreweave/glossary-service/internal/domain"
)

// createGenre creates a new genre group for a book.
func (s *Server) createGenre(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	bookID := chi.URLParam(r, "book_id")

	var in struct {
		Name        string `json:"name"`
		Color       string `json:"color"`
		Description string `json:"description"`
		SortOrder   *int   `json:"sort_order"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "invalid JSON body")
		return
	}

	in.Name = strings.TrimSpace(in.Name)
	if in.Name == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "name is required")
		return
	}
	if in.Color == "" {
		in.Color = "#8b5cf6"
	}
	sortOrder := 0
	if in.SortOrder != nil {
		sortOrder = *in.SortOrder
	}

	var g domain.GenreGroup
	var createdAt time.Time
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO genre_groups (book_id, name, color, description, sort_order)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, book_id, name, color, description, sort_order, created_at`,
		bookID, in.Name, in.Color, in.Description, sortOrder,
	).Scan(&g.ID, &g.BookID, &g.Name, &g.Color, &g.Description, &g.SortOrder, &createdAt)
	if err != nil {
		if strings.Contains(err.Error(), "unique") || strings.Contains(err.Error(), "duplicate") {
			writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "a genre with this name already exists for this book")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create genre")
		return
	}
	g.CreatedAt = createdAt.Format(time.RFC3339)

	writeJSON(w, http.StatusCreated, g)
}

// patchGenre updates a genre group's fields.
func (s *Server) patchGenre(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	bookID := chi.URLParam(r, "book_id")
	genreID := chi.URLParam(r, "genre_id")

	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "invalid JSON body")
		return
	}

	sets := ""
	args := []any{genreID, bookID} // $1 = genre_id, $2 = book_id
	i := 3

	if v, ok := in["name"]; ok {
		name, _ := v.(string)
		name = strings.TrimSpace(name)
		if name == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "name cannot be empty")
			return
		}
		sets += comma(sets) + "name=$" + itoa(i)
		args = append(args, name)
		i++
	}
	if v, ok := in["color"]; ok {
		sets += comma(sets) + "color=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["description"]; ok {
		sets += comma(sets) + "description=$" + itoa(i)
		args = append(args, v)
		i++
	}
	if v, ok := in["sort_order"]; ok {
		sets += comma(sets) + "sort_order=$" + itoa(i)
		args = append(args, v)
		i++
	}

	if sets == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "no fields to update")
		return
	}

	tag, err := s.pool.Exec(r.Context(),
		"UPDATE genre_groups SET "+sets+" WHERE id=$1 AND book_id=$2", args...)
	if err != nil {
		if strings.Contains(err.Error(), "unique") || strings.Contains(err.Error(), "duplicate") {
			writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "a genre with this name already exists for this book")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to update genre")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "genre not found")
		return
	}

	// Re-fetch and return the updated row.
	var g domain.GenreGroup
	var createdAt time.Time
	err = s.pool.QueryRow(r.Context(), `
		SELECT id, book_id, name, color, description, sort_order, created_at
		FROM genre_groups WHERE id=$1`, genreID,
	).Scan(&g.ID, &g.BookID, &g.Name, &g.Color, &g.Description, &g.SortOrder, &createdAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to re-fetch genre")
		return
	}
	g.CreatedAt = createdAt.Format(time.RFC3339)

	writeJSON(w, http.StatusOK, g)
}

// deleteGenre removes a genre group.
func (s *Server) deleteGenre(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	bookID := chi.URLParam(r, "book_id")
	genreID := chi.URLParam(r, "genre_id")

	tag, err := s.pool.Exec(r.Context(),
		"DELETE FROM genre_groups WHERE id=$1 AND book_id=$2", genreID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to delete genre")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "genre not found")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}
