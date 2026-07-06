package api

import (
	"context"
	"encoding/json"
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

func TestGetBookAccess_ReturnsOwnerToGranteeOnly(t *testing.T) {
	t.Parallel()
	s := testServer()
	owner := uuid.New()

	// A grantee (edit) receives owner_user_id so it can resolve a cross-tenant
	// read of the owner's per-(user,book) rows (the book-tier model settings).
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantEdit, owner, "active", nil
	}
	req := httptest.NewRequest(http.MethodGet, "/internal/books/"+uuid.NewString()+"/access?user_id="+uuid.NewString(), nil)
	req.Header.Set("X-Internal-Token", "itok")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("grantee access: got %d want 200 (%s)", rr.Code, rr.Body.String())
	}
	var body map[string]string
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if body["owner_user_id"] != owner.String() {
		t.Fatalf("owner_user_id: got %q want %q", body["owner_user_id"], owner.String())
	}

	// A non-grantee (none) must NOT get owner_user_id — no owner/existence oracle.
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantNone, owner, "active", nil
	}
	req2 := httptest.NewRequest(http.MethodGet, "/internal/books/"+uuid.NewString()+"/access?user_id="+uuid.NewString(), nil)
	req2.Header.Set("X-Internal-Token", "itok")
	rr2 := httptest.NewRecorder()
	s.Router().ServeHTTP(rr2, req2)
	var body2 map[string]string
	_ = json.Unmarshal(rr2.Body.Bytes(), &body2)
	if _, ok := body2["owner_user_id"]; ok {
		t.Fatalf("owner_user_id leaked to a non-grantee: %v", body2)
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
		httptest.NewRequest(http.MethodPost, "/v1/books/"+book+"/collaborators", nil), // E0-5 invite
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

// --- E0-5 auth-service resolution helpers (HTTP, no DB) ---

func authStubServer(t *testing.T, status int, body string) *Server {
	t.Helper()
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(ts.Close)
	return NewServer(nil, &config.Config{
		JWTSecret:              "test-secret-at-least-32-characters-long!",
		InternalServiceToken:   "itok",
		AuthServiceInternalURL: ts.URL,
	})
}

func TestAuthResolveByEmail_Found(t *testing.T) {
	t.Parallel()
	id := uuid.New()
	s := authStubServer(t, http.StatusOK,
		`{"user_id":"`+id.String()+`","email":"a@b.co","display_name":"Ada"}`)
	got, name, found, err := s.authResolveByEmail(context.Background(), "a@b.co")
	if err != nil || !found {
		t.Fatalf("want found, no err; got found=%v err=%v", found, err)
	}
	if got != id || name != "Ada" {
		t.Errorf("got (%s,%q) want (%s,Ada)", got, name, id)
	}
}

func TestAuthResolveByEmail_NotFound(t *testing.T) {
	t.Parallel()
	// 404 → found=false, NO error (the invite surfaces a clean "no such user").
	s := authStubServer(t, http.StatusNotFound, `{"error":{"code":"AUTH_USER_NOT_FOUND"}}`)
	_, _, found, err := s.authResolveByEmail(context.Background(), "nobody@x.co")
	if err != nil || found {
		t.Fatalf("404 must be found=false,err=nil; got found=%v err=%v", found, err)
	}
}

func TestAuthResolveByEmail_ServerErrorIsError(t *testing.T) {
	t.Parallel()
	// A 5xx is an ERROR (the invite fails 503), never a silent "not found".
	s := authStubServer(t, http.StatusInternalServerError, ``)
	if _, _, _, err := s.authResolveByEmail(context.Background(), "x@y.co"); err == nil {
		t.Fatal("5xx from auth must return an error, not a silent not-found")
	}
}

func TestAuthDisplayName_BestEffort(t *testing.T) {
	t.Parallel()
	// Happy path returns the name; a non-200 degrades to "" (never errors the list).
	ok := authStubServer(t, http.StatusOK, `{"display_name":"Bo"}`)
	if got := ok.authDisplayName(context.Background(), uuid.New()); got != "Bo" {
		t.Errorf("display_name=%q want Bo", got)
	}
	down := authStubServer(t, http.StatusServiceUnavailable, ``)
	if got := down.authDisplayName(context.Background(), uuid.New()); got != "" {
		t.Errorf("auth down: display_name=%q want empty (best-effort)", got)
	}
}
