package api

// M1 (audit) — the resolver's §4.6 read-side lifecycle gate: getBookStructure MUST short-circuit a
// non-active book to an EMPTY skeleton + a book_lifecycle marker, and NEVER fetch composition (which,
// with a nil pool + no composition, would panic/hang). This is the automated regression guard the audit
// found missing — the gate was proven only by a live e2e. No DB: authBook resolves via the stubbed
// resolveBook, and the gate returns before any chapter/composition read.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

func TestGetBookStructure_NonActiveBook_GatesToEmptySkeleton(t *testing.T) {
	t.Parallel()
	for _, lifecycle := range []string{"trashed", "purge_pending"} {
		t.Run(lifecycle, func(t *testing.T) {
			s := mcpTestServer(GrantView)
			owner := uuid.New()
			// Force the resolver to see a NON-active book (the stub defaults to "active").
			s.resolveBook = func(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
				return GrantView, owner, lifecycle, nil
			}
			bookID := uuid.New()
			req := httptest.NewRequest(http.MethodGet, "/v1/books/"+bookID.String()+"/structure", nil)
			req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
			rctx := chi.NewRouteContext()
			rctx.URLParams.Add("book_id", bookID.String())
			req = req.WithContext(addChi(req, rctx))
			w := httptest.NewRecorder()

			s.getBookStructure(w, req)

			if w.Code != http.StatusOK {
				t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
			}
			var resp bookStructureResponse
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("decode: %v (body=%s)", err, w.Body.String())
			}
			if resp.BookLifecycle != lifecycle {
				t.Errorf("book_lifecycle = %q, want %q", resp.BookLifecycle, lifecycle)
			}
			if len(resp.Parts) != 0 {
				t.Errorf("a %s book MUST return NO live parts, got %d", lifecycle, len(resp.Parts))
			}
			if resp.KindsPresent.Parts || resp.KindsPresent.Outline {
				t.Errorf("a %s book must present no live structure kinds, got %+v", lifecycle, resp.KindsPresent)
			}
		})
	}
}
