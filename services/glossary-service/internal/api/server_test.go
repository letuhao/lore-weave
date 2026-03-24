package api_test

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/api"
	"github.com/loreweave/glossary-service/internal/config"
	"github.com/loreweave/glossary-service/internal/domain"
)

const testSecret = "test_jwt_secret_at_least_32_characters_long"

func newTestServer(t *testing.T, pool *pgxpool.Pool) *api.Server {
	t.Helper()
	cfg := &config.Config{
		HTTPAddr:  ":0",
		JWTSecret: testSecret,
	}
	return api.NewServer(pool, cfg)
}

func makeToken(t *testing.T, userID string) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   userID,
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(testSecret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

// ── unit tests (no DB required) ──────────────────────────────────────────────

// TestHealthEndpoint verifies GET /health returns 200 without auth.
func TestHealthEndpoint(t *testing.T) {
	srv := newTestServer(t, nil)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
}

// TestListKindsUnauthorized verifies GET /v1/glossary/kinds returns 401 without a token.
func TestListKindsUnauthorized(t *testing.T) {
	srv := newTestServer(t, nil)
	req := httptest.NewRequest(http.MethodGet, "/v1/glossary/kinds", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", w.Code)
	}
}

// TestListKindsBadToken verifies an invalid token returns 401.
func TestListKindsBadToken(t *testing.T) {
	srv := newTestServer(t, nil)
	req := httptest.NewRequest(http.MethodGet, "/v1/glossary/kinds", nil)
	req.Header.Set("Authorization", "Bearer not.a.valid.token")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", w.Code)
	}
}

// ── seed data unit tests (no DB) ─────────────────────────────────────────────

// TestDefaultKindsCount verifies exactly 12 kinds are declared.
func TestDefaultKindsCount(t *testing.T) {
	if got := len(domain.DefaultKinds); got != 12 {
		t.Fatalf("expected 12 default kinds, got %d", got)
	}
}

// TestCharacterAttrCount verifies character has 13 attribute definitions.
func TestCharacterAttrCount(t *testing.T) {
	var char *domain.SeedKind
	for i := range domain.DefaultKinds {
		if domain.DefaultKinds[i].Code == "character" {
			char = &domain.DefaultKinds[i]
			break
		}
	}
	if char == nil {
		t.Fatal("character kind not found")
	}
	if got := len(char.Attrs); got != 13 {
		t.Fatalf("expected 13 character attrs, got %d", got)
	}
}

// TestTerminologyAttrCount verifies terminology has 4 attribute definitions.
func TestTerminologyAttrCount(t *testing.T) {
	var term *domain.SeedKind
	for i := range domain.DefaultKinds {
		if domain.DefaultKinds[i].Code == "terminology" {
			term = &domain.DefaultKinds[i]
			break
		}
	}
	if term == nil {
		t.Fatal("terminology kind not found")
	}
	if got := len(term.Attrs); got != 4 {
		t.Fatalf("expected 4 terminology attrs, got %d", got)
	}
}

// TestRequiredAttrsHaveIsRequired verifies that required fields are marked correctly.
func TestRequiredAttrsHaveIsRequired(t *testing.T) {
	requiredCodes := map[string][]string{
		"character":  {"name"},
		"location":   {"name"},
		"item":       {"name"},
		"event":      {"name"},
		"terminology": {"term", "definition"},
		"trope":      {"name", "definition"},
	}
	kindsByCode := make(map[string]*domain.SeedKind)
	for i := range domain.DefaultKinds {
		kindsByCode[domain.DefaultKinds[i].Code] = &domain.DefaultKinds[i]
	}
	for kindCode, reqCodes := range requiredCodes {
		k, ok := kindsByCode[kindCode]
		if !ok {
			t.Errorf("kind %s not found", kindCode)
			continue
		}
		attrByCode := make(map[string]*domain.SeedAttr)
		for i := range k.Attrs {
			attrByCode[k.Attrs[i].Code] = &k.Attrs[i]
		}
		for _, code := range reqCodes {
			a, ok := attrByCode[code]
			if !ok {
				t.Errorf("%s.%s not found", kindCode, code)
				continue
			}
			if !a.IsRequired {
				t.Errorf("%s.%s should be required", kindCode, code)
			}
		}
	}
}

// TestGenreTagsAssignment verifies genre tags on a sample of kinds.
func TestGenreTagsAssignment(t *testing.T) {
	cases := map[string]string{
		"character":    "universal",
		"power_system": "fantasy",
		"relationship": "romance",
		"plot_arc":     "drama",
	}
	for kindCode, expectedTag := range cases {
		var found *domain.SeedKind
		for i := range domain.DefaultKinds {
			if domain.DefaultKinds[i].Code == kindCode {
				found = &domain.DefaultKinds[i]
				break
			}
		}
		if found == nil {
			t.Errorf("kind %s not found", kindCode)
			continue
		}
		hasTag := false
		for _, tag := range found.GenreTags {
			if tag == expectedTag {
				hasTag = true
				break
			}
		}
		if !hasTag {
			t.Errorf("kind %s should have genre_tag %q, got %v", kindCode, expectedTag, found.GenreTags)
		}
	}
}

// TestSortOrderUnique verifies no two kinds share the same sort_order.
func TestSortOrderUnique(t *testing.T) {
	seen := make(map[int]string)
	for _, k := range domain.DefaultKinds {
		if prev, exists := seen[k.SortOrder]; exists {
			t.Errorf("duplicate sort_order %d between %s and %s", k.SortOrder, prev, k.Code)
		}
		seen[k.SortOrder] = k.Code
	}
}

// ── entity endpoint auth tests (no DB required) ───────────────────────────────

// TestChapterLinkEndpointsRequireAuth verifies all 4 chapter-link endpoints return 401 without a token.
func TestChapterLinkEndpointsRequireAuth(t *testing.T) {
	srv := newTestServer(t, nil)
	fakeBook := "00000000-0000-0000-0000-000000000001"
	fakeEntity := "00000000-0000-0000-0000-000000000002"
	fakeLink := "00000000-0000-0000-0000-000000000003"
	base := "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity + "/chapter-links"

	cases := []struct {
		method string
		path   string
	}{
		{http.MethodGet, base},
		{http.MethodPost, base},
		{http.MethodPatch, base + "/" + fakeLink},
		{http.MethodDelete, base + "/" + fakeLink},
	}

	for _, tc := range cases {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, nil)
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Errorf("expected 401, got %d", w.Code)
			}
		})
	}
}

// TestChapterLinkEndpointsRejectBadToken verifies all 4 chapter-link endpoints return 401 for an invalid token.
func TestChapterLinkEndpointsRejectBadToken(t *testing.T) {
	srv := newTestServer(t, nil)
	fakeBook := "00000000-0000-0000-0000-000000000001"
	fakeEntity := "00000000-0000-0000-0000-000000000002"
	fakeLink := "00000000-0000-0000-0000-000000000003"
	base := "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity + "/chapter-links"

	cases := []struct {
		method string
		path   string
	}{
		{http.MethodGet, base},
		{http.MethodPost, base},
		{http.MethodPatch, base + "/" + fakeLink},
		{http.MethodDelete, base + "/" + fakeLink},
	}

	for _, tc := range cases {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, nil)
			req.Header.Set("Authorization", "Bearer not.a.valid.token")
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Errorf("expected 401, got %d", w.Code)
			}
		})
	}
}

// TestEntityEndpointsRequireAuth verifies all 5 entity endpoints return 401 without a token.
func TestEntityEndpointsRequireAuth(t *testing.T) {
	srv := newTestServer(t, nil)
	fakeBook := "00000000-0000-0000-0000-000000000001"
	fakeEntity := "00000000-0000-0000-0000-000000000002"

	cases := []struct {
		method string
		path   string
	}{
		{http.MethodPost, "/v1/glossary/books/" + fakeBook + "/entities"},
		{http.MethodGet, "/v1/glossary/books/" + fakeBook + "/entities"},
		{http.MethodGet, "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity},
		{http.MethodPatch, "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity},
		{http.MethodDelete, "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity},
	}

	for _, tc := range cases {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, nil)
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Errorf("expected 401, got %d", w.Code)
			}
		})
	}
}

// TestEntityEndpointsRejectBadToken verifies all 5 entity endpoints return 401 for an invalid token.
func TestEntityEndpointsRejectBadToken(t *testing.T) {
	srv := newTestServer(t, nil)
	fakeBook := "00000000-0000-0000-0000-000000000001"
	fakeEntity := "00000000-0000-0000-0000-000000000002"

	cases := []struct {
		method string
		path   string
	}{
		{http.MethodPost, "/v1/glossary/books/" + fakeBook + "/entities"},
		{http.MethodGet, "/v1/glossary/books/" + fakeBook + "/entities"},
		{http.MethodGet, "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity},
		{http.MethodPatch, "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity},
		{http.MethodDelete, "/v1/glossary/books/" + fakeBook + "/entities/" + fakeEntity},
	}

	for _, tc := range cases {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, nil)
			req.Header.Set("Authorization", "Bearer not.a.valid.token")
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Errorf("expected 401, got %d", w.Code)
			}
		})
	}
}
