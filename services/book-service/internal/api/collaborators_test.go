package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/book-service/internal/config"
)

// --- Pure grant-logic (security-critical; no DB) ---

func TestGrantLevelString(t *testing.T) {
	t.Parallel()
	cases := map[GrantLevel]string{
		GrantNone: "none", GrantView: "view", GrantEdit: "edit", GrantManage: "manage", GrantOwner: "owner",
	}
	for lvl, want := range cases {
		if got := lvl.String(); got != want {
			t.Errorf("GrantLevel(%d).String()=%q want %q", lvl, got, want)
		}
	}
}

func TestGrantLevelOrdering(t *testing.T) {
	t.Parallel()
	// This ordering gates EVERY permission decision (resolve >= need). If it
	// regresses, an editor could pass a manage check, etc.
	if !(GrantNone < GrantView && GrantView < GrantEdit && GrantEdit < GrantManage && GrantManage < GrantOwner) {
		t.Fatal("grant-level ordering invariant broken: none<view<edit<manage<owner")
	}
}

func TestRoleToLevel(t *testing.T) {
	t.Parallel()
	cases := map[string]GrantLevel{
		"view": GrantView, "edit": GrantEdit, "manage": GrantManage,
		// Unknown/empty/owner/cased must default-deny — never silently grant.
		"": GrantNone, "owner": GrantNone, "admin": GrantNone, "VIEW": GrantNone,
	}
	for role, want := range cases {
		if got := roleToLevel(role); got != want {
			t.Errorf("roleToLevel(%q)=%v want %v (unknown must default-deny)", role, got, want)
		}
	}
}

func TestValidCollaboratorRole(t *testing.T) {
	t.Parallel()
	for _, r := range []string{"view", "edit", "manage"} {
		if !validCollaboratorRole(r) {
			t.Errorf("role %q should be grantable", r)
		}
	}
	// owner is implicit (from owner_user_id), NOT a grantable role.
	for _, r := range []string{"owner", "", "admin", "Edit", "MANAGE"} {
		if validCollaboratorRole(r) {
			t.Errorf("role %q must NOT be grantable", r)
		}
	}
}

// --- Handler guards (DB-free paths: token gate, owner-only auth, input validation) ---

func testServer() *Server {
	return NewServer(nil, &config.Config{
		JWTSecret:            "test-secret-at-least-32-characters-long!",
		InternalServiceToken: "itok",
	})
}

func TestGetBookAccess_RequiresInternalToken(t *testing.T) {
	t.Parallel()
	s := testServer()
	req := httptest.NewRequest(http.MethodGet, "/internal/books/"+uuid.NewString()+"/access?user_id="+uuid.NewString(), nil)
	// no X-Internal-Token
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("missing internal token: got %d want 401", rr.Code)
	}
}

func TestGetBookAccess_BadIDs(t *testing.T) {
	t.Parallel()
	s := testServer()
	// Bad book id → 400 before any DB access.
	req := httptest.NewRequest(http.MethodGet, "/internal/books/not-a-uuid/access?user_id="+uuid.NewString(), nil)
	req.Header.Set("X-Internal-Token", "itok")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("bad book id: got %d want 400", rr.Code)
	}
	// Missing/invalid user_id → 400.
	req = httptest.NewRequest(http.MethodGet, "/internal/books/"+uuid.NewString()+"/access", nil)
	req.Header.Set("X-Internal-Token", "itok")
	rr = httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("missing user_id: got %d want 400", rr.Code)
	}
}

func TestCollaboratorMgmt_RequiresJWT(t *testing.T) {
	t.Parallel()
	s := testServer()
	book := uuid.NewString()
	target := uuid.NewString()
	// All owner-only endpoints must 401 without a Bearer token (before DB).
	reqs := []*http.Request{
		httptest.NewRequest(http.MethodGet, "/v1/books/"+book+"/collaborators", nil),
		httptest.NewRequest(http.MethodPut, "/v1/books/"+book+"/collaborators/"+target, nil),
		httptest.NewRequest(http.MethodDelete, "/v1/books/"+book+"/collaborators/"+target, nil),
	}
	for _, req := range reqs {
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusUnauthorized {
			t.Errorf("%s %s without JWT: got %d want 401", req.Method, req.URL.Path, rr.Code)
		}
	}
}
