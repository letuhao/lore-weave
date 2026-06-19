package api

// G6-BE / D2 — per-entity genre override. The genre·kind·attribute model lets an
// ENTITY carry its own genre set, overriding the book's active genres (spec §3:
// "active genres = entity_genres override else book_active_genres"). The merged
// entity form (03-entity-form) reads this to decide which (kind × genre) attribute
// fields apply to a given entity. The `entity_genres` table was created in G1; this
// adds the read + replace HTTP surface that was missing (unblocks the FE entity form).
//
// `universal` is mandatory + always-active (O4) — it is auto-included on every set,
// and cannot be dropped from an entity's genre set.

import (
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

type entityGenresResp struct {
	GenreIDs        []string `json:"genre_ids"`
	UsesBookDefault bool     `json:"uses_book_default"` // true when no per-entity override is set
}

// GET /v1/glossary/books/{book_id}/entities/{entity_id}/genres
// Returns the entity's genre override (empty ⇒ the entity uses the book's active
// genres). View-gated (reading entity content).
func (s *Server) getEntityGenres(w http.ResponseWriter, r *http.Request) {
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
	if !s.entityInBook(w, r, entityID, bookID) {
		return
	}

	ctx := r.Context()
	rows, err := s.pool.Query(ctx,
		`SELECT eg.genre_id::text
		 FROM entity_genres eg JOIN book_genres bg ON bg.genre_id = eg.genre_id
		 WHERE eg.entity_id=$1 AND bg.deprecated_at IS NULL
		 ORDER BY bg.sort_order, bg.code`, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()
	ids := []string{}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}
	writeJSON(w, http.StatusOK, entityGenresResp{GenreIDs: ids, UsesBookDefault: len(ids) == 0})
}

// PUT /v1/glossary/books/{book_id}/entities/{entity_id}/genres
// Body { genre_ids: [...] } — replaces the entity's genre override set. Edit-gated
// (per-entity content). Every id must be a LIVE book genre of THIS book (else 422,
// tenant boundary). `universal` is always included (O4). An empty set (after the
// universal auto-include) is impossible — the entity always has at least universal.
func (s *Server) setEntityGenres(w http.ResponseWriter, r *http.Request) {
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
	if !s.entityInBook(w, r, entityID, bookID) {
		return
	}

	var in struct {
		GenreIDs []string `json:"genre_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	// Parse the requested ids (reject non-UUIDs early).
	want := make([]uuid.UUID, 0, len(in.GenreIDs))
	for _, s := range in.GenreIDs {
		id, err := uuid.Parse(s)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "genre_ids must be UUIDs")
			return
		}
		want = append(want, id)
	}

	ctx := r.Context()
	// Always include the book's universal genre (O4 — mandatory, never droppable).
	var universalID uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT genre_id FROM book_genres WHERE book_id=$1 AND code='universal' AND deprecated_at IS NULL`,
		bookID).Scan(&universalID); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "book has no universal genre (adopt it first)")
		return
	}
	want = append(want, universalID)

	// Validate every requested id is a LIVE book genre of THIS book (tenant boundary):
	// count the live book-genre matches and compare to the distinct requested set.
	var validCount int
	if err := s.pool.QueryRow(ctx,
		`SELECT count(DISTINCT genre_id) FROM book_genres
		 WHERE book_id=$1 AND deprecated_at IS NULL AND genre_id = ANY($2)`,
		bookID, want).Scan(&validCount); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "validate failed")
		return
	}
	if validCount != distinctCount(want) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"every genre_id must be a live genre of this book")
		return
	}

	// Replace the override set in one transaction.
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `DELETE FROM entity_genres WHERE entity_id=$1`, entityID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clear failed")
		return
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO entity_genres(entity_id, genre_id)
		 SELECT $1, g FROM unnest($2::uuid[]) AS g ON CONFLICT DO NOTHING`,
		entityID, want); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}

	ids := make([]string, len(want))
	for i, id := range want {
		ids[i] = id.String()
	}
	writeJSON(w, http.StatusOK, entityGenresResp{GenreIDs: dedupStrings(ids), UsesBookDefault: false})
}

// entityInBook writes 404 + returns false when the entity isn't part of the book
// (or doesn't exist) — the tenant guard for the per-entity routes.
func (s *Server) entityInBook(w http.ResponseWriter, r *http.Request, entityID, bookID uuid.UUID) bool {
	var exists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2)`,
		entityID, bookID).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return false
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found in this book")
		return false
	}
	return true
}

func distinctCount(ids []uuid.UUID) int {
	seen := map[uuid.UUID]struct{}{}
	for _, id := range ids {
		seen[id] = struct{}{}
	}
	return len(seen)
}
