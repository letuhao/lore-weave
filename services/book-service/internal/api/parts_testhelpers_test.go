package api

// Shared test helpers that used to live in parts_db_test.go (removed with the C4 parts-CRUD
// retirement). Still used by mcp_chapter_idempotency_db_test.go and any future book-scoped DB test.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedPartsBook inserts an active book owned by ownerID.
func seedPartsBook(t *testing.T, ctx context.Context, pool *pgxpool.Pool, ownerID uuid.UUID) uuid.UUID {
	t.Helper()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'parts') RETURNING id`, ownerID).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	return bookID
}

// ownerResolver makes s.resolveBook treat `owner` as the book's owner for any book id.
func ownerResolver(owner uuid.UUID) func(context.Context, uuid.UUID, uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
	return func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
}
