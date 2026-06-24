package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/book-service/internal/config"
)

// E0-2 router-level grant-mapping deny test — the executable guard on the
// owner→grant adoption. book-service resolves grants LOCALLY, so we inject a
// stub `resolveBook` that returns a fixed grant level; this exercises the
// route→need mapping (the authBook chokepoint) WITHOUT a DB. It asserts the
// DENY side only: a grantee one tier below a route's need gets 403, and a
// non-grantee gets 404 on reads — both short-circuit in authBook BEFORE any
// pool access (the nil pool never panics on these paths). The ALLOW side (a
// sufficient grantee proceeds to the query) is covered by real-PG/live-smoke.
//
// This is the check that owner-run DB tests CANNOT provide: an owner satisfies
// every tier, so a need-mapping regression (e.g. a destructive route silently
// mapped to edit) stays invisible until a real collaborator hits it. (E0-1's
// /review-impl caught exactly this class of bug; the guard is now executable.)

// denyServer returns a Server whose grant resolver always reports `level` on an
// active book, so route handlers see a caller holding exactly that grant.
func denyServer(level GrantLevel) *Server {
	s := NewServer(nil, &config.Config{
		JWTSecret:            grantMapSecret,
		InternalServiceToken: "itok",
	})
	s.resolveBook = func(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		// owner = a random id != caller, so the caller is a pure collaborator at
		// `level` (never implicitly owner). lifecycle active.
		return level, uuid.New(), "active", nil
	}
	return s
}

const grantMapSecret = "test-secret-at-least-32-characters-long!"

// grantMapJWT mints a valid HS256 access token for a random caller.
func grantMapJWT(t *testing.T) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   uuid.NewString(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(grantMapSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return signed
}

// grantRoute is one in-scope route plus the grant tier it must require.
type grantRoute struct {
	method string
	path   string // {b}/{c} placeholders substituted with real uuids
	need   GrantLevel
	body   string // optional JSON body (authBook fires first, but avoid pre-parse 400s)
}

// mutatingRoutes — every book-service route that must require >view. The `need`
// is the PO-locked tier (CLARIFY 2026-06-11). A grantee at need-1 must 403.
func mutatingRoutes() []grantRoute {
	return []grantRoute{
		// edit-tier
		{http.MethodPatch, "/v1/books/{b}", GrantEdit, `{}`},
		{http.MethodPost, "/v1/books/{b}/cover", GrantEdit, ``},
		{http.MethodDelete, "/v1/books/{b}/cover", GrantEdit, ``},
		{http.MethodPost, "/v1/books/{b}/chapters", GrantEdit, `{}`},
		{http.MethodPatch, "/v1/books/{b}/chapters/{c}", GrantEdit, `{}`},
		{http.MethodPatch, "/v1/books/{b}/chapters/{c}/draft", GrantEdit, `{"body":{}}`},
		{http.MethodDelete, "/v1/books/{b}/chapters/{c}", GrantEdit, ``}, // trash (reversible)
		{http.MethodPost, "/v1/books/{b}/chapters/{c}/restore", GrantEdit, ``},
		{http.MethodPost, "/v1/books/{b}/chapters/{c}/publish", GrantEdit, `{}`},
		{http.MethodPost, "/v1/books/{b}/chapters/{c}/unpublish", GrantEdit, ``},
		{http.MethodPost, "/v1/books/{b}/chapters/{c}/revisions/" + uuid.NewString() + "/restore", GrantEdit, ``},
		{http.MethodPost, "/v1/books/{b}/chapters/{c}/media-generate", GrantEdit, `{}`},
		{http.MethodPost, "/v1/books/{b}/chapters/{c}/media-versions", GrantEdit, `{}`},
		{http.MethodPost, "/v1/books/{b}/chapters/{c}/audio/generate", GrantEdit, `{}`},
		{http.MethodPost, "/v1/books/{b}/import", GrantEdit, ``},
		// manage-tier
		{http.MethodDelete, "/v1/books/{b}/chapters/{c}/purge", GrantManage, ``},
		{http.MethodDelete, "/v1/books/{b}/chapters/{c}/media-versions/" + uuid.NewString(), GrantManage, ``},
		{http.MethodDelete, "/v1/books/{b}/chapters/{c}/audio", GrantManage, ``},
		// owner-only (book-destructive + collaborator mgmt)
		{http.MethodDelete, "/v1/books/{b}", GrantOwner, ``},   // trash book
		{http.MethodPost, "/v1/books/{b}/restore", GrantOwner, ``},
		{http.MethodDelete, "/v1/books/{b}/purge", GrantOwner, ``},
		{http.MethodPut, "/v1/books/{b}/collaborators/" + uuid.NewString(), GrantOwner, `{"role":"view"}`},
		{http.MethodDelete, "/v1/books/{b}/collaborators/" + uuid.NewString(), GrantOwner, ``},
	}
}

// readRoutes — routes a non-grantee must NOT reach (404, no existence oracle).
func readRoutes() []grantRoute {
	return []grantRoute{
		{http.MethodGet, "/v1/books/{b}", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/search?q=x", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/cover", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/stats", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/content", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/export", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/draft", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/revisions", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/revisions/" + uuid.NewString(), GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/revisions/compare?left=" + uuid.NewString() + "&right=" + uuid.NewString(), GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/media-versions", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/chapters/{c}/audio", GrantView, ``},
		{http.MethodGet, "/v1/books/{b}/imports", GrantView, ``},
		// KG-ML M3 — reader-language read is view-gated (canViewOrPublic): a
		// non-grantee on a private book gets 404 (no existence oracle).
		{http.MethodGet, "/v1/books/{b}/reader-language", GrantView, ``},
	}
}

func subst(path string) string {
	path = strings.Replace(path, "{b}", uuid.NewString(), 1)
	path = strings.Replace(path, "{c}", uuid.NewString(), 1)
	return path
}

// TestGrantMapping_MutatingRoutesDenyUnderTier asserts a grantee one tier below
// each route's `need` is rejected (403) — never reaching the DB.
func TestGrantMapping_MutatingRoutesDenyUnderTier(t *testing.T) {
	t.Parallel()
	for _, rt := range mutatingRoutes() {
		// A grantee exactly one tier below the requirement.
		under := rt.need - 1
		s := denyServer(under)
		token := grantMapJWT(t)
		var bodyReader *strings.Reader
		if rt.body != "" {
			bodyReader = strings.NewReader(rt.body)
		} else {
			bodyReader = strings.NewReader("")
		}
		req := httptest.NewRequest(rt.method, subst(rt.path), bodyReader)
		req.Header.Set("Authorization", "Bearer "+token)
		if rt.body != "" {
			req.Header.Set("Content-Type", "application/json")
		}
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusForbidden {
			t.Errorf("%s %s as %v (need %v): got %d want 403\n%s",
				rt.method, rt.path, under, rt.need, rr.Code, rr.Body.String())
		}
	}
}

// TestFavorites_AddDeniesNonGranteePrivateBook closes D-FAVORITES-METADATA-LEAK
// at the entry: a non-grantee cannot favorite a book they can't see. denyServer
// has no grant and no SharingInternalURL (→ fetchSharingVisibility = "private"),
// so canViewOrPublic is false → 404 before any INSERT (nil pool never reached).
func TestFavorites_AddDeniesNonGranteePrivateBook(t *testing.T) {
	t.Parallel()
	s := denyServer(GrantNone)
	req := httptest.NewRequest(http.MethodPost, "/v1/books/"+uuid.NewString()+"/favorite", nil)
	req.Header.Set("Authorization", "Bearer "+grantMapJWT(t))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Errorf("non-grantee favoriting a private book: got %d want 404\n%s", rr.Code, rr.Body.String())
	}
}

// TestGrantMapping_ReadRoutesDenyNonGrantee asserts a non-grantee (none) gets
// 404 on every read route — uniform with a missing book (no existence oracle).
func TestGrantMapping_ReadRoutesDenyNonGrantee(t *testing.T) {
	t.Parallel()
	s := denyServer(GrantNone)
	for _, rt := range readRoutes() {
		token := grantMapJWT(t)
		req := httptest.NewRequest(rt.method, subst(rt.path), nil)
		req.Header.Set("Authorization", "Bearer "+token)
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusNotFound {
			t.Errorf("%s %s as non-grantee: got %d want 404\n%s",
				rt.method, rt.path, rr.Code, rr.Body.String())
		}
	}
}

// TestGrantMapping_MutatingRoutesDenyNonGrantee asserts a non-grantee gets 404
// on mutating routes too (authBook collapses none→404 before the need check).
func TestGrantMapping_MutatingRoutesDenyNonGrantee(t *testing.T) {
	t.Parallel()
	s := denyServer(GrantNone)
	for _, rt := range mutatingRoutes() {
		token := grantMapJWT(t)
		var body *strings.Reader
		if rt.body != "" {
			body = strings.NewReader(rt.body)
		} else {
			body = strings.NewReader("")
		}
		req := httptest.NewRequest(rt.method, subst(rt.path), body)
		req.Header.Set("Authorization", "Bearer "+token)
		if rt.body != "" {
			req.Header.Set("Content-Type", "application/json")
		}
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		// Collaborator-mgmt (requireBookOwner) uniformly 403s a non-owner; the
		// authBook routes 404 a non-grantee. Both are valid denials.
		if rr.Code != http.StatusNotFound && rr.Code != http.StatusForbidden {
			t.Errorf("%s %s as non-grantee: got %d want 404/403\n%s",
				rt.method, rt.path, rr.Code, rr.Body.String())
		}
	}
}
