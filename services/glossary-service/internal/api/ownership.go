package api

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/google/uuid"
)

// Ownership sentinels for the MCP read tools (INV-8).
var (
	// ErrNotAccessible — the book doesn't exist OR isn't owned by the caller.
	// Deliberately UNIFORM for both cases (H13) so a tool can't be used as an
	// existence oracle to probe other users' book ids.
	ErrNotAccessible = errors.New("book not accessible")
	// ErrBookUnavailable — book-service couldn't be reached, so ownership is
	// UNKNOWN → fail closed (deny), never assume owned.
	ErrBookUnavailable = errors.New("book ownership unavailable")
)

const ownershipCacheTTL = 60 * time.Second

type ownerCacheEntry struct {
	owned bool
	exp   time.Time
}

// checkBookOwnership verifies userID owns bookID (INV-8). Backed by a short-TTL
// cache that stores ONLY positive results — a not-owner / not-found / unavailable
// is never cached, so a revoked grant or a transient book-service outage re-checks
// on the next call. book-service down → ErrBookUnavailable (fail-closed).
func (s *Server) checkBookOwnership(ctx context.Context, bookID, userID uuid.UUID) error {
	key := userID.String() + ":" + bookID.String()
	if v, ok := s.ownerCache.Load(key); ok {
		if e := v.(ownerCacheEntry); e.owned && time.Now().Before(e.exp) {
			return nil
		}
	}

	proj, status := s.fetchBookProjection(ctx, bookID)
	switch {
	case status == http.StatusNotFound:
		return ErrNotAccessible
	case status != http.StatusOK:
		return ErrBookUnavailable
	case proj.OwnerUserID != userID:
		return ErrNotAccessible
	}

	s.ownerCache.Store(key, ownerCacheEntry{owned: true, exp: time.Now().Add(ownershipCacheTTL)})
	return nil
}
