package api

import (
	"net/http"
	"testing"

	"github.com/google/uuid"
)

// resolveListBookScope: a list request with ?book_id but no grant authority (s.grants
// nil in the test server) → 404 anti-oracle (a book the caller can't verify a grant on
// is indistinguishable from absent). Rejected BEFORE any list query, so the mock needs
// no expectations. Covers all 5 list endpoints via the shared helper.
func TestListBookScope_NoGrant404(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", "user")
	book := uuid.NewString()

	for _, path := range []string{
		"/v1/agent-registry/subagents?book_id=" + book,
		"/v1/agent-registry/commands?book_id=" + book,
		"/v1/agent-registry/hooks?book_id=" + book,
		"/v1/agent-registry/skills?book_id=" + book,
		"/v1/agent-registry/mcp-servers?book_id=" + book,
	} {
		rec := doJSON(s, http.MethodGet, path, tok, "")
		if rec.Code != http.StatusNotFound {
			t.Errorf("%s (no grant authority) → want 404, got %d", path, rec.Code)
		}
	}
	// a malformed book_id → 400 (also before any DB op)
	rec := doJSON(s, http.MethodGet, "/v1/agent-registry/subagents?book_id=not-a-uuid", tok, "")
	if rec.Code != http.StatusBadRequest {
		t.Errorf("malformed book_id → want 400, got %d", rec.Code)
	}
}
