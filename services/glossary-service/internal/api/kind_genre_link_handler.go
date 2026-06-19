package api

// G2 — kind↔genre association links (genre·kind·attribute re-architecture).
// Manages user_kind_genres: which user-genres a user-kind carries. Owner-scoped
// on BOTH sides — the kind must be the caller's, and every linked genre must be
// the caller's user-tier genre (no linking another tenant's or a System genre id
// directly; clone System into your tier first, §2.6).

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
)

// loadUserKindLinkedGenres returns the user-genres linked to a user-kind, ordered.
func (s *Server) loadUserKindLinkedGenres(ctx context.Context, userKindID uuid.UUID) ([]genreResp, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT g.genre_id::text, g.owner_user_id::text, g.code, g.name, g.icon, g.color, g.sort_order,
		       g.cloned_from_genre_id::text, g.created_at, g.updated_at
		FROM user_kind_genres kg
		JOIN user_genres g ON g.genre_id = kg.genre_id
		WHERE kg.kind_id = $1 AND g.deleted_at IS NULL AND g.permanently_deleted_at IS NULL
		ORDER BY g.sort_order, g.code`, userKindID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []genreResp{}
	for rows.Next() {
		var g genreResp
		g.Tier = "user"
		if err := rows.Scan(&g.GenreID, &g.OwnerUserID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder,
			&g.ClonedFromGenreID, &g.CreatedAt, &g.UpdatedAt); err != nil {
			return nil, err
		}
		items = append(items, g)
	}
	return items, rows.Err()
}

func (s *Server) listUserKindGenres(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}
	items, err := s.loadUserKindLinkedGenres(r.Context(), userKindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// putUserKindGenres replaces the full link set for a user-kind.
func (s *Server) putUserKindGenres(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}

	var in struct {
		GenreIDs []string `json:"genre_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	// Validate + de-dup the target set: every id must be the caller's live user-genre.
	seen := map[uuid.UUID]struct{}{}
	genreIDs := make([]uuid.UUID, 0, len(in.GenreIDs))
	for _, raw := range in.GenreIDs {
		gid, err := uuid.Parse(raw)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid genre id: "+raw)
			return
		}
		if _, dup := seen[gid]; dup {
			continue
		}
		if owned, err := s.ownsUserGenre(r.Context(), gid, userID); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "ownership check failed")
			return
		} else if !owned {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
				"genre "+raw+" is not your user-tier genre (clone the system genre first)")
			return
		}
		seen[gid] = struct{}{}
		genreIDs = append(genreIDs, gid)
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	if _, err := tx.Exec(ctx, `DELETE FROM user_kind_genres WHERE kind_id = $1`, userKindID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clear links failed")
		return
	}
	for _, gid := range genreIDs {
		if _, err := tx.Exec(ctx,
			`INSERT INTO user_kind_genres (kind_id, genre_id) VALUES ($1,$2) ON CONFLICT DO NOTHING`,
			userKindID, gid); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "link failed")
			return
		}
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}

	items, err := s.loadUserKindLinkedGenres(ctx, userKindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reload failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// addUserKindGenre links a single genre (idempotent).
func (s *Server) addUserKindGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}
	if owned, err := s.ownsUserGenre(r.Context(), genreID, userID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "ownership check failed")
		return
	} else if !owned {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user genre not found")
		return
	}
	if _, err := s.pool.Exec(r.Context(),
		`INSERT INTO user_kind_genres (kind_id, genre_id) VALUES ($1,$2) ON CONFLICT DO NOTHING`,
		userKindID, genreID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "link failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// deleteUserKindGenre removes a single link.
func (s *Server) deleteUserKindGenre(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}
	tag, err := s.pool.Exec(r.Context(),
		`DELETE FROM user_kind_genres WHERE kind_id = $1 AND genre_id = $2`, userKindID, genreID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "unlink failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "link not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
