package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/grantclient"

	"github.com/loreweave/glossary-service/internal/config"
)

// ownershipTestServer builds a Server whose grant client points at a fake
// book-service (the given handler). grantClient is wired explicitly because the
// test constructs Server directly (not via NewServer).
func ownershipTestServer(t *testing.T, h http.HandlerFunc) *Server {
	t.Helper()
	ts := httptest.NewServer(h)
	t.Cleanup(ts.Close)
	return &Server{
		cfg:         &config.Config{BookServiceURL: ts.URL, InternalServiceToken: "tok"},
		grantClient: buildGrantClient(ts.URL, "tok"),
	}
}

// projection is the shared fake book-service. It multiplexes the two internal
// endpoints glossary depends on: /access (the E0-1 grant authority — owner→owner,
// everyone else→none, book active) and /projection (owner + wiki_settings).
func projection(book, owner uuid.UUID) http.HandlerFunc {
	return projectionLifecycle(book, owner, "active")
}

// projectionLifecycle is projection with an explicit book lifecycle_state on the
// /access leg (for lifecycle-gate tests).
func projectionLifecycle(book, owner uuid.UUID, lifecycle string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasSuffix(r.URL.Path, "/access") {
			lvl := "none"
			if r.URL.Query().Get("user_id") == owner.String() {
				lvl = "owner"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"grant_level": lvl, "lifecycle_state": lifecycle})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id": book.String(), "owner_user_id": owner.String(),
		})
	}
}

func TestCheckGrant_OwnerSatisfiesAllTiers(t *testing.T) {
	owner, book := uuid.New(), uuid.New()
	s := ownershipTestServer(t, projection(book, owner))
	for _, need := range []grantclient.GrantLevel{grantclient.GrantView, grantclient.GrantEdit, grantclient.GrantManage} {
		if err := s.checkGrant(context.Background(), book, owner, need); err != nil {
			t.Fatalf("owner should satisfy %v, got %v", need, err)
		}
	}
}

func TestCheckGrant_NonGranteeIsNotAccessible(t *testing.T) {
	s := ownershipTestServer(t, projection(uuid.New(), uuid.New()))
	err := s.checkGrant(context.Background(), uuid.New(), uuid.New(), grantclient.GrantView)
	if !errors.Is(err, ErrNotAccessible) {
		t.Fatalf("non-grantee must be ErrNotAccessible, got %v", err)
	}
}

func TestCheckGrant_MissingBookIsNotAccessible(t *testing.T) {
	// R4/H13: missing book → grant `none` → SAME ErrNotAccessible as not-a-grantee
	// (no enumeration oracle).
	s := ownershipTestServer(t, func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"grant_level": "none", "lifecycle_state": ""})
	})
	if err := s.checkGrant(context.Background(), uuid.New(), uuid.New(), grantclient.GrantView); !errors.Is(err, ErrNotAccessible) {
		t.Fatalf("missing book must be ErrNotAccessible, got %v", err)
	}
}

func TestCheckGrant_BookServiceDownFailsClosed(t *testing.T) {
	s := ownershipTestServer(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	})
	if err := s.checkGrant(context.Background(), uuid.New(), uuid.New(), grantclient.GrantView); !errors.Is(err, ErrBookUnavailable) {
		t.Fatalf("book-service down must be ErrBookUnavailable (fail-closed), got %v", err)
	}
}

func TestCheckGrant_NilClientFailsClosed(t *testing.T) {
	// A Server with no grant client (misconfig) must deny, never allow.
	s := &Server{cfg: &config.Config{}}
	if err := s.checkGrant(context.Background(), uuid.New(), uuid.New(), grantclient.GrantView); !errors.Is(err, ErrBookUnavailable) {
		t.Fatalf("nil grant client must fail closed, got %v", err)
	}
}

func TestCheckGrant_LifecycleGate(t *testing.T) {
	// A trashed book: reads (view) still pass; edit/manage are blocked with
	// ErrBookInactive (the lifecycle gate, D-E0-LIFECYCLE-NEEDMAP).
	owner, book := uuid.New(), uuid.New()
	s := ownershipTestServer(t, projectionLifecycle(book, owner, "trashed"))
	if err := s.checkGrant(context.Background(), book, owner, grantclient.GrantView); err != nil {
		t.Fatalf("view must be allowed on a trashed book, got %v", err)
	}
	for _, need := range []grantclient.GrantLevel{grantclient.GrantEdit, grantclient.GrantManage} {
		if err := s.checkGrant(context.Background(), book, owner, need); !errors.Is(err, ErrBookInactive) {
			t.Fatalf("%v on a trashed book must be ErrBookInactive, got %v", need, err)
		}
	}
}

func TestRequireGrant_HTTPStatusMapping(t *testing.T) {
	owner, book := uuid.New(), uuid.New()

	// owner on an active book → pass (no error written).
	s := ownershipTestServer(t, projection(book, owner))
	rr := httptest.NewRecorder()
	if !s.requireGrant(rr, context.Background(), book, owner, grantclient.GrantManage) {
		t.Fatalf("owner manage should pass, got %d", rr.Code)
	}

	// under-grant (non-grantee) → 403.
	rr = httptest.NewRecorder()
	if s.requireGrant(rr, context.Background(), book, uuid.New(), grantclient.GrantEdit) || rr.Code != http.StatusForbidden {
		t.Fatalf("under-grant want 403, got %d", rr.Code)
	}

	// edit on a trashed book → 409 (lifecycle gate).
	s2 := ownershipTestServer(t, projectionLifecycle(book, owner, "trashed"))
	rr = httptest.NewRecorder()
	if s2.requireGrant(rr, context.Background(), book, owner, grantclient.GrantEdit) || rr.Code != http.StatusConflict {
		t.Fatalf("edit on trashed want 409, got %d", rr.Code)
	}

	// book-service down → 503 (fail-closed).
	s3 := ownershipTestServer(t, func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusServiceUnavailable) })
	rr = httptest.NewRecorder()
	if s3.requireGrant(rr, context.Background(), book, owner, grantclient.GrantView) || rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("book-service down want 503, got %d", rr.Code)
	}
}

func TestCheckGrant_CachesPositiveOnly(t *testing.T) {
	owner, book := uuid.New(), uuid.New()
	hits := 0
	s := ownershipTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/access") {
			hits++
		}
		projection(book, owner)(w, r)
	})
	_ = s.checkGrant(context.Background(), book, owner, grantclient.GrantView)
	_ = s.checkGrant(context.Background(), book, owner, grantclient.GrantView)
	if hits != 1 {
		t.Fatalf("a positive grant must be cached (want 1 upstream hit, got %d)", hits)
	}
}

func TestCheckGrant_DoesNotCacheFailure(t *testing.T) {
	owner, book := uuid.New(), uuid.New()
	hits := 0
	s := ownershipTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		hits++
		if hits == 1 {
			w.WriteHeader(http.StatusServiceUnavailable) // first: down → fail-closed, NOT cached
			return
		}
		projection(book, owner)(w, r) // second: recovered → owner
	})
	if err := s.checkGrant(context.Background(), book, owner, grantclient.GrantView); !errors.Is(err, ErrBookUnavailable) {
		t.Fatalf("first call should fail-closed, got %v", err)
	}
	if err := s.checkGrant(context.Background(), book, owner, grantclient.GrantView); err != nil {
		t.Fatalf("second call should re-check and pass (failure not cached), got %v", err)
	}
	if hits != 2 {
		t.Fatalf("failure must not be cached (want 2 hits, got %d)", hits)
	}
}
