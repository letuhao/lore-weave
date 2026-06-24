package api

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Shared helpers for the tiered MCP tools (F2): code→id resolvers (so tools take
// human-stable codes, not transposition-prone UUIDs — §6.8/§11 #9), and a
// base-version concurrency check (the H5 lesson — patch tools 409 on drift).

// errVersionConflict is returned by compareBaseVersion when the caller's base
// version no longer matches the live row (optimistic-concurrency drift → 409).
var errVersionConflict = errors.New("base version conflict")

// compareBaseVersion implements the optimistic-concurrency check for patch tools
// (§12.6). `base` is the version the caller read before editing (content_hash for
// genres/attrs, updated_at for kinds); `current` is the live row's version now.
// An empty base means the caller opted out of the check (explicit last-write-wins),
// so it passes. A non-empty base that differs from current → errVersionConflict.
func compareBaseVersion(current, base string) error {
	if base == "" {
		return nil
	}
	if current != base {
		return errVersionConflict
	}
	return nil
}

// resolveBookGenreID maps a book-local genre code to its id (live rows only).
// pgx.ErrNoRows when no such live genre — callers map that to a clean "not found".
func (s *Server) resolveBookGenreID(ctx context.Context, bookID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT genre_id FROM book_genres
		   WHERE book_id = $1 AND code = $2 AND deprecated_at IS NULL`, bookID, code).Scan(&id)
	return id, err
}

// resolveBookKindID maps a book-local kind code to its book_kind_id (live rows only).
func (s *Server) resolveBookKindID(ctx context.Context, bookID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT book_kind_id FROM book_kinds
		   WHERE book_id = $1 AND code = $2 AND deprecated_at IS NULL`, bookID, code).Scan(&id)
	return id, err
}

// resolveBookAttrID maps a (kind_code, genre_code, attr_code) triple to a book
// attribute id — attributes are keyed by (kind × genre × code), so the code alone
// is not unique (§ tiering model). Live rows only.
func (s *Server) resolveBookAttrID(ctx context.Context, bookID uuid.UUID, kindCode, genreCode, attrCode string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `
		SELECT a.attr_id
		  FROM book_attributes a
		  JOIN book_kinds  k ON k.book_kind_id = a.kind_id  AND k.deprecated_at IS NULL
		  JOIN book_genres g ON g.genre_id     = a.genre_id AND g.deprecated_at IS NULL
		 WHERE a.book_id = $1 AND k.code = $2 AND g.code = $3 AND a.code = $4
		   AND a.deprecated_at IS NULL`,
		bookID, kindCode, genreCode, attrCode).Scan(&id)
	return id, err
}

// isNoRows is a small predicate so resolver callers read cleanly.
func isNoRows(err error) bool { return errors.Is(err, pgx.ErrNoRows) }
