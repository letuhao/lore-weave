package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/config"
)

func ownershipTestServer(t *testing.T, h http.HandlerFunc) *Server {
	t.Helper()
	ts := httptest.NewServer(h)
	t.Cleanup(ts.Close)
	return &Server{cfg: &config.Config{BookServiceURL: ts.URL, InternalServiceToken: "tok"}}
}

func projection(book, owner uuid.UUID) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id": book.String(), "owner_user_id": owner.String(),
		})
	}
}

func TestCheckBookOwnership_OwnedPasses(t *testing.T) {
	owner, book := uuid.New(), uuid.New()
	s := ownershipTestServer(t, projection(book, owner))
	if err := s.checkBookOwnership(context.Background(), book, owner); err != nil {
		t.Fatalf("owner should pass, got %v", err)
	}
}

func TestCheckBookOwnership_NonOwnerIsNotAccessible(t *testing.T) {
	s := ownershipTestServer(t, projection(uuid.New(), uuid.New()))
	err := s.checkBookOwnership(context.Background(), uuid.New(), uuid.New())
	if !errors.Is(err, ErrNotAccessible) {
		t.Fatalf("non-owner must be ErrNotAccessible, got %v", err)
	}
}

func TestCheckBookOwnership_NotFoundIsNotAccessible(t *testing.T) {
	// H13: not-found and not-owner collapse to the SAME error (no enumeration oracle).
	s := ownershipTestServer(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	})
	if err := s.checkBookOwnership(context.Background(), uuid.New(), uuid.New()); !errors.Is(err, ErrNotAccessible) {
		t.Fatalf("not-found must be ErrNotAccessible, got %v", err)
	}
}

func TestCheckBookOwnership_BookServiceDownFailsClosed(t *testing.T) {
	s := ownershipTestServer(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	})
	if err := s.checkBookOwnership(context.Background(), uuid.New(), uuid.New()); !errors.Is(err, ErrBookUnavailable) {
		t.Fatalf("book-service down must be ErrBookUnavailable (fail-closed), got %v", err)
	}
}

func TestCheckBookOwnership_CachesPositiveOnly(t *testing.T) {
	owner, book := uuid.New(), uuid.New()
	hits := 0
	s := ownershipTestServer(t, func(w http.ResponseWriter, _ *http.Request) {
		hits++
		projection(book, owner)(w, nil)
	})
	_ = s.checkBookOwnership(context.Background(), book, owner)
	_ = s.checkBookOwnership(context.Background(), book, owner)
	if hits != 1 {
		t.Fatalf("a positive ownership result must be cached (want 1 upstream hit, got %d)", hits)
	}
}

func TestCheckBookOwnership_DoesNotCacheFailure(t *testing.T) {
	owner, book := uuid.New(), uuid.New()
	hits := 0
	s := ownershipTestServer(t, func(w http.ResponseWriter, _ *http.Request) {
		hits++
		if hits == 1 {
			w.WriteHeader(http.StatusServiceUnavailable) // first: down → fail-closed, NOT cached
			return
		}
		projection(book, owner)(w, nil) // second: recovered → owned
	})
	if err := s.checkBookOwnership(context.Background(), book, owner); !errors.Is(err, ErrBookUnavailable) {
		t.Fatalf("first call should fail-closed, got %v", err)
	}
	if err := s.checkBookOwnership(context.Background(), book, owner); err != nil {
		t.Fatalf("second call should re-check and pass (failure not cached), got %v", err)
	}
	if hits != 2 {
		t.Fatalf("failure must not be cached (want 2 hits, got %d)", hits)
	}
}
