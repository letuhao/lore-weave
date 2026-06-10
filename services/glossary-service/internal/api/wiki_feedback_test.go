package api

// wiki-llm M8 — feedback flywheel emit tests (DB-gated: need GLOSSARY_TEST_DB_URL,
// skip otherwise via newMergeFixture→openTestDB). These exercise the real handlers
// over Postgres: a human edit of an AI article emits wiki.corrected (but a human
// edit of a human article does NOT), and a suggestion review emits
// wiki.suggestion_reviewed.

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// feedbackToken mints a JWT for the fixture's server secret. (The shared
// makeToken helper lives in the external api_test package, invisible here.)
func feedbackToken(t *testing.T, f *mergeFixture, userID string) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   userID,
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(f.srv.cfg.JWTSecret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

func aiRevision(t *testing.T, f *mergeFixture, articleID, author uuid.UUID, authorType string) {
	t.Helper()
	if _, err := f.pool.Exec(f.ctx, `
		INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
		VALUES ($1, COALESCE((SELECT MAX(version) FROM wiki_revisions WHERE article_id=$1),0)+1, '{"type":"doc","content":[]}', $2, $3, '')`,
		articleID, author, authorType); err != nil {
		t.Fatalf("seed revision: %v", err)
	}
}

func countOutbox(t *testing.T, f *mergeFixture, eventType, articleID string) int {
	t.Helper()
	var n int
	f.pool.QueryRow(f.ctx,
		`SELECT count(*) FROM outbox_events WHERE event_type=$1 AND payload->>'article_id'=$2`,
		eventType, articleID).Scan(&n)
	return n
}

func patchBody(t *testing.T, f *mergeFixture, owner, bookID, articleID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"body_json": json.RawMessage(`{"type":"doc","content":[{"type":"paragraph"}]}`)})
	req := httptest.NewRequest(http.MethodPatch,
		"/v1/glossary/books/"+bookID.String()+"/wiki/"+articleID.String(), bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner.String()))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestPatch_EmitsWikiCorrected_OnAIArticle(t *testing.T) {
	f := newMergeFixture(t, "00000000c0d1")
	cleanupWikiArticles(t, f)
	ownerStr := mockBookOwner(t, f)
	owner := uuid.MustParse(ownerStr)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	// the article was AI-generated: its latest revision is 'ai', status needs_review
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET generation_status='needs_review' WHERE article_id=$1`, art)
	aiRevision(t, f, art, owner, "ai")

	if w := patchBody(t, f, owner, f.bookID, art); w.Code != http.StatusOK {
		t.Fatalf("patch: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if n := countOutbox(t, f, "wiki.corrected", art.String()); n != 1 {
		t.Fatalf("want 1 wiki.corrected event, got %d", n)
	}
	// the prior AI quality travels in the payload
	var prior string
	f.pool.QueryRow(f.ctx,
		`SELECT payload->>'prior_generation_status' FROM outbox_events WHERE event_type='wiki.corrected' AND payload->>'article_id'=$1`,
		art.String()).Scan(&prior)
	if prior != "needs_review" {
		t.Fatalf("prior_generation_status: want needs_review, got %q", prior)
	}
	// /review-impl F2 — the human now owns it: the AI markers are cleared so the
	// stale needs_review badge + flags panel don't persist.
	var genStatus *string
	f.pool.QueryRow(f.ctx, `SELECT generation_status FROM wiki_articles WHERE article_id=$1`, art).Scan(&genStatus)
	if genStatus != nil {
		t.Fatalf("generation_status should be cleared after a human correction, got %q", *genStatus)
	}
}

func TestPatch_NoCorrected_OnHumanArticle(t *testing.T) {
	f := newMergeFixture(t, "00000000c0d2")
	cleanupWikiArticles(t, f)
	ownerStr := mockBookOwner(t, f)
	owner := uuid.MustParse(ownerStr)
	entity := f.mkEntity(t, "Renfield", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	// a human-authored article: latest revision is 'owner' — editing it is NOT a
	// correction of AI output, so no wiki.corrected.
	aiRevision(t, f, art, owner, "owner")

	if w := patchBody(t, f, owner, f.bookID, art); w.Code != http.StatusOK {
		t.Fatalf("patch: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if n := countOutbox(t, f, "wiki.corrected", art.String()); n != 0 {
		t.Fatalf("want 0 wiki.corrected events (human article), got %d", n)
	}
}

func TestReview_EmitsSuggestionReviewed(t *testing.T) {
	f := newMergeFixture(t, "00000000c0d3")
	cleanupWikiArticles(t, f)
	ownerStr := mockBookOwner(t, f)
	owner := uuid.MustParse(ownerStr)
	entity := f.mkEntity(t, "Lucy", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET generation_status='generated' WHERE article_id=$1`, art)
	// a pending community suggestion from a non-owner
	var sug uuid.UUID
	if err := f.pool.QueryRow(f.ctx, `
		INSERT INTO wiki_suggestions (article_id, user_id, diff_json, reason, status)
		VALUES ($1, $2, '{"type":"doc","content":[]}', 'fix', 'pending') RETURNING suggestion_id`,
		art, uuid.New()).Scan(&sug); err != nil {
		t.Fatalf("seed suggestion: %v", err)
	}
	t.Cleanup(func() { f.pool.Exec(f.ctx, `DELETE FROM wiki_suggestions WHERE article_id=$1`, art) })

	body, _ := json.Marshal(map[string]any{"action": "reject"})
	req := httptest.NewRequest(http.MethodPatch,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/"+art.String()+"/suggestions/"+sug.String(), bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner.String()))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("review: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if n := countOutbox(t, f, "wiki.suggestion_reviewed", art.String()); n != 1 {
		t.Fatalf("want 1 wiki.suggestion_reviewed event, got %d", n)
	}
	var action string
	var wasAI bool
	f.pool.QueryRow(f.ctx,
		`SELECT payload->>'action', (payload->>'was_ai_generated')::bool FROM outbox_events
		 WHERE event_type='wiki.suggestion_reviewed' AND payload->>'article_id'=$1`,
		art.String()).Scan(&action, &wasAI)
	if action != "reject" || !wasAI {
		t.Fatalf("payload: want action=reject was_ai=true, got action=%q was_ai=%v", action, wasAI)
	}
}
