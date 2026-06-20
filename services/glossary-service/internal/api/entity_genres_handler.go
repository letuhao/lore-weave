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
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

type entityGenresResp struct {
	GenreIDs        []string `json:"genre_ids"`
	UsesBookDefault bool     `json:"uses_book_default"` // true when no per-entity override is set
}

var (
	// errEntityGenreInvalid → 422: a requested genre is not a live book genre (tenancy).
	errEntityGenreInvalid = errors.New("a genre is not a live genre of this book")
	// errBookNoUniversal → 422: the book has no universal genre (not adopted yet).
	errBookNoUniversal = errors.New("book has no universal genre — adopt standards first")
)

// entityExistsInBook reports whether the entity belongs to the book (the tenant guard
// core shared by HTTP entityInBook and the MCP entity tools).
func (s *Server) entityExistsInBook(ctx context.Context, entityID, bookID uuid.UUID) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2)`,
		entityID, bookID).Scan(&exists)
	return exists, err
}

// getEntityGenreIDs returns the entity's live genre-override ids (empty ⇒ book default).
func (s *Server) getEntityGenreIDs(ctx context.Context, entityID uuid.UUID) ([]string, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT eg.genre_id::text
		 FROM entity_genres eg JOIN book_genres bg ON bg.genre_id = eg.genre_id
		 WHERE eg.entity_id=$1 AND bg.deprecated_at IS NULL
		 ORDER BY bg.sort_order, bg.code`, entityID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	ids := []string{}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// setEntityGenresCore replaces an entity's genre-override set. Empty want ⇒ clear back
// to the book default. Otherwise universal is force-included (O4) and every id must be a
// live book genre of THIS book (errEntityGenreInvalid). Shared by HTTP + MCP.
func (s *Server) setEntityGenresCore(ctx context.Context, bookID, entityID uuid.UUID, want []uuid.UUID) (*entityGenresResp, error) {
	if len(want) == 0 {
		if _, err := s.pool.Exec(ctx, `DELETE FROM entity_genres WHERE entity_id=$1`, entityID); err != nil {
			return nil, err
		}
		return &entityGenresResp{GenreIDs: []string{}, UsesBookDefault: true}, nil
	}
	var universalID uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT genre_id FROM book_genres WHERE book_id=$1 AND code='universal' AND deprecated_at IS NULL`,
		bookID).Scan(&universalID); err != nil {
		return nil, errBookNoUniversal
	}
	want = append(want, universalID)

	var validCount int
	if err := s.pool.QueryRow(ctx,
		`SELECT count(DISTINCT genre_id) FROM book_genres
		 WHERE book_id=$1 AND deprecated_at IS NULL AND genre_id = ANY($2)`,
		bookID, want).Scan(&validCount); err != nil {
		return nil, err
	}
	if validCount != distinctCount(want) {
		return nil, errEntityGenreInvalid
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `DELETE FROM entity_genres WHERE entity_id=$1`, entityID); err != nil {
		return nil, err
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO entity_genres(entity_id, genre_id)
		 SELECT $1, g FROM unnest($2::uuid[]) AS g ON CONFLICT DO NOTHING`,
		entityID, want); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	ids := make([]string, len(want))
	for i, id := range want {
		ids[i] = id.String()
	}
	return &entityGenresResp{GenreIDs: dedupStrings(ids), UsesBookDefault: false}, nil
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

	ids, err := s.getEntityGenreIDs(r.Context(), entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
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
	want := make([]uuid.UUID, 0, len(in.GenreIDs))
	for _, s := range in.GenreIDs {
		id, err := uuid.Parse(s)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "genre_ids must be UUIDs")
			return
		}
		want = append(want, id)
	}
	resp, err := s.setEntityGenresCore(r.Context(), bookID, entityID, want)
	if err != nil {
		writeEntityGenresErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, *resp)
}

// writeEntityGenresErr maps the set-core sentinels to HTTP responses.
func writeEntityGenresErr(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, errEntityGenreInvalid):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "every genre_id must be a live genre of this book")
	case errors.Is(err, errBookNoUniversal):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "book has no universal genre (adopt it first)")
	default:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "set genres failed")
	}
}

// entityInBook writes 404 + returns false when the entity isn't part of the book
// (or doesn't exist) — the tenant guard for the per-entity routes.
func (s *Server) entityInBook(w http.ResponseWriter, r *http.Request, entityID, bookID uuid.UUID) bool {
	exists, err := s.entityExistsInBook(r.Context(), entityID, bookID)
	if err != nil {
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
