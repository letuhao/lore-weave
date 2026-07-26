package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/loreweave/auth-service/internal/config"
)

// parseProfilePatch enforces the same validation as the public PATCH: bio ≤1000,
// languages ≤20 items / ≤50 chars each, and only the prose fields are mutable.
func TestParseProfilePatch_Validation(t *testing.T) {
	t.Parallel()

	// Happy path: only the provided fields produce non-nil pointers.
	dn, loc, av, bi, langs, verr := parseProfilePatch(map[string]any{
		"display_name": "Alice",
		"languages":    []any{"en", "vi"},
	})
	if verr != "" {
		t.Fatalf("unexpected error: %s", verr)
	}
	if dn == nil || *dn != "Alice" {
		t.Fatalf("display_name not parsed: %v", dn)
	}
	if loc != nil || av != nil || bi != nil {
		t.Fatal("absent fields must stay nil (COALESCE leaves them unchanged)")
	}
	if len(langs) != 2 {
		t.Fatalf("languages: got %v", langs)
	}

	// bio over 1000 chars → error.
	big := make([]byte, 1001)
	for i := range big {
		big[i] = 'x'
	}
	if _, _, _, _, _, verr := parseProfilePatch(map[string]any{"bio": string(big)}); verr == "" {
		t.Fatal("bio > 1000 chars must be rejected")
	}

	// >20 languages → error.
	many := make([]any, 21)
	for i := range many {
		many[i] = "x"
	}
	if _, _, _, _, _, verr := parseProfilePatch(map[string]any{"languages": many}); verr == "" {
		t.Fatal("languages > 20 must be rejected")
	}

	// avatar_url scheme allowlist (stored-XSS guard): http(s) and empty/clear pass;
	// javascript:/data: (and other schemes) are rejected.
	for _, ok := range []string{"http://x/a.png", "https://x/a.png", "HTTPS://X/a.png", ""} {
		if _, _, av, _, _, verr := parseProfilePatch(map[string]any{"avatar_url": ok}); verr != "" {
			t.Fatalf("avatar_url %q must be accepted, got error %q", ok, verr)
		} else if av == nil {
			t.Fatalf("avatar_url %q must produce a non-nil patch value", ok)
		}
	}
	for _, bad := range []string{"javascript:alert(1)", "data:text/html,<script>", "ftp://x/a", "/relative/a.png", "vbscript:msgbox"} {
		if _, _, _, _, _, verr := parseProfilePatch(map[string]any{"avatar_url": bad}); verr == "" {
			t.Fatalf("avatar_url %q (non-http scheme) must be rejected", bad)
		}
	}
}

// The internal full-profile routes must reject a missing/wrong X-Internal-Token
// (defense in depth — a profile WRITE reachable cross-service is token-gated).
func TestInternalProfile_RequiresInternalToken(t *testing.T) {
	t.Parallel()
	s := &Server{cfg: &config.Config{InternalServiceToken: "right-internal-token-32-characters!"}}

	handler := s.requireInternalServiceToken(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	// Missing token → 401.
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/internal/users/x/full-profile", nil))
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("missing token: expected 401, got %d", rec.Code)
	}

	// Wrong token → 401.
	rec = httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/internal/users/x/full-profile", nil)
	req.Header.Set("X-Internal-Token", "wrong")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("wrong token: expected 401, got %d", rec.Code)
	}

	// Correct token → passes through (200).
	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/internal/users/x/full-profile", nil)
	req.Header.Set("X-Internal-Token", "right-internal-token-32-characters!")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("correct token: expected 200, got %d", rec.Code)
	}
}
