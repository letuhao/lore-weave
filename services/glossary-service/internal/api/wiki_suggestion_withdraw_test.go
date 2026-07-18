package api

// S-09 W5 — the submitter side of the wiki-suggestion lifecycle:
//   • DELETE .../suggestions/{id}  → the ORIGINAL submitter withdraws their own PENDING
//     suggestion (no book grant needed; a non-submitter gets an anti-oracle 404; a
//     reviewed suggestion is immutable → 409).
//   • GET  .../suggestions/mine    → the submitter reads THEIR OWN suggestions WITH the
//     accept/reject status, so the outcome isn't write-only (they don't hold a grant, so
//     the owner-facing listWikiSuggestions is closed to them).
// DB-integration via newMergeFixture (needs GLOSSARY_TEST_DB_URL, skips otherwise).

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// seedSuggestionAs inserts a suggestion with a KNOWN submitter + status (the shared
// seedSuggestion helper uses a random user_id, which can't be matched to a token).
func seedSuggestionAs(t *testing.T, f *mergeFixture, articleID, submitter uuid.UUID, status string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := f.pool.QueryRow(f.ctx, `
		INSERT INTO wiki_suggestions (article_id, user_id, diff_json, reason, status)
		VALUES ($1, $2, '{"type":"doc","content":[]}', 'fix', $3) RETURNING suggestion_id`,
		articleID, submitter, status).Scan(&id); err != nil {
		t.Fatalf("seed suggestion: %v", err)
	}
	t.Cleanup(func() { f.pool.Exec(f.ctx, `DELETE FROM wiki_suggestions WHERE article_id=$1`, articleID) })
	return id
}

func withdrawSuggestion(t *testing.T, f *mergeFixture, caller string, articleID, sugID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/"+articleID.String()+"/suggestions/"+sugID.String(), nil)
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, caller))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func suggestionCount(t *testing.T, f *mergeFixture, sugID uuid.UUID) int {
	t.Helper()
	var n int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM wiki_suggestions WHERE suggestion_id=$1`, sugID).Scan(&n)
	return n
}

// The submitter withdraws their own pending suggestion → 204 and the row is gone.
func TestWithdrawSuggestion_SubmitterDeletesPending(t *testing.T) {
	f := newMergeFixture(t, "00000000e0f1")
	cleanupWikiArticles(t, f)
	mockBookOwner(t, f)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	submitter := uuid.New()
	sug := seedSuggestionAs(t, f, art, submitter, "pending")

	if w := withdrawSuggestion(t, f, submitter.String(), art, sug); w.Code != http.StatusNoContent {
		t.Fatalf("withdraw: want 204, got %d (%s)", w.Code, w.Body.String())
	}
	if n := suggestionCount(t, f, sug); n != 0 {
		t.Fatalf("suggestion should be deleted, still present (%d)", n)
	}
}

// A non-submitter (even the book owner) is told the suggestion does not exist (404,
// not 403) and the row is left intact — an ID can't be probed for existence.
func TestWithdrawSuggestion_NonSubmitterGets404(t *testing.T) {
	f := newMergeFixture(t, "00000000e0f2")
	cleanupWikiArticles(t, f)
	ownerStr := mockBookOwner(t, f)
	entity := f.mkEntity(t, "Lucy", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	submitter := uuid.New()
	sug := seedSuggestionAs(t, f, art, submitter, "pending")

	if w := withdrawSuggestion(t, f, ownerStr, art, sug); w.Code != http.StatusNotFound {
		t.Fatalf("non-submitter withdraw: want 404, got %d (%s)", w.Code, w.Body.String())
	}
	if n := suggestionCount(t, f, sug); n != 1 {
		t.Fatalf("a non-submitter must not delete the row, count=%d", n)
	}
}

// A reviewed (accepted/rejected) suggestion is immutable history — even the submitter
// cannot withdraw it → 409, row intact.
func TestWithdrawSuggestion_AlreadyReviewedGives409(t *testing.T) {
	f := newMergeFixture(t, "00000000e0f3")
	cleanupWikiArticles(t, f)
	mockBookOwner(t, f)
	entity := f.mkEntity(t, "Renfield", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	submitter := uuid.New()
	sug := seedSuggestionAs(t, f, art, submitter, "rejected")

	if w := withdrawSuggestion(t, f, submitter.String(), art, sug); w.Code != http.StatusConflict {
		t.Fatalf("withdraw reviewed: want 409, got %d (%s)", w.Code, w.Body.String())
	}
	if n := suggestionCount(t, f, sug); n != 1 {
		t.Fatalf("a reviewed suggestion must not be deleted, count=%d", n)
	}
}

// The submitter reads their OWN suggestions with status; another user's suggestion in
// the same book is not included (the WHERE ws.user_id = caller is the scope).
func TestListMySuggestions_ReturnsOwnWithStatus(t *testing.T) {
	f := newMergeFixture(t, "00000000e0f4")
	cleanupWikiArticles(t, f)
	mockBookOwner(t, f)
	entity := f.mkEntity(t, "Quincey", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	me := uuid.New()
	other := uuid.New()
	mine := seedSuggestionAs(t, f, art, me, "accepted")
	seedSuggestionAs(t, f, art, other, "pending")

	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/suggestions/mine", nil)
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, me.String()))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("mine: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	var resp struct {
		Items []struct {
			SuggestionID uuid.UUID `json:"suggestion_id"`
			Status       string    `json:"status"`
		} `json:"items"`
		Total int `json:"total"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Total != 1 || len(resp.Items) != 1 {
		t.Fatalf("want exactly my 1 suggestion, got total=%d items=%d", resp.Total, len(resp.Items))
	}
	if resp.Items[0].SuggestionID != mine {
		t.Fatalf("want my suggestion %s, got %s", mine, resp.Items[0].SuggestionID)
	}
	if resp.Items[0].Status != "accepted" {
		t.Fatalf("submitter read must carry the accept/reject status, got %q", resp.Items[0].Status)
	}
}
