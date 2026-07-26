package api

// wiki-llm M8 (D-WIKI-M8-FEWSHOT) — gold-pairs endpoint tests. DB-integration via
// newMergeFixture (needs GLOSSARY_TEST_DB_URL, skips otherwise) + pure helper tests.

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func seedRev(t *testing.T, f *mergeFixture, articleID uuid.UUID, version int, authorType, text string) {
	t.Helper()
	body := fmt.Sprintf(
		`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":%q}]}]}`, text)
	if _, err := f.pool.Exec(f.ctx,
		`INSERT INTO wiki_revisions(article_id,version,body_json,author_id,author_type,summary)
		 VALUES($1,$2,$3,$4,$5,'')`,
		articleID, version, body, uuid.New(), authorType); err != nil {
		t.Fatalf("seed rev: %v", err)
	}
}

func getGoldPairs(t *testing.T, f *mergeFixture, limit string) []wikiGoldPair {
	t.Helper()
	url := "/internal/books/" + f.bookID.String() + "/wiki/gold-pairs"
	if limit != "" {
		url += "?limit=" + limit
	}
	req := httptest.NewRequest(http.MethodGet, url, nil)
	req.Header.Set("X-Internal-Token", f.srv.cfg.InternalServiceToken)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("gold-pairs: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		Pairs []wikiGoldPair `json:"pairs"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	return resp.Pairs
}

func TestGoldPairs_ReturnsAiOwnerPair(t *testing.T) {
	f := newMergeFixture(t, "00000000f0a1")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	seedRev(t, f, art, 1, "ai", "the ai draft body")
	seedRev(t, f, art, 2, "owner", "the human corrected body")

	pairs := getGoldPairs(t, f, "")
	if len(pairs) != 1 {
		t.Fatalf("want 1 gold pair, got %d", len(pairs))
	}
	p := pairs[0]
	if p.ArticleID != art.String() {
		t.Fatalf("article_id: got %s", p.ArticleID)
	}
	if !strings.Contains(p.AIText, "ai draft") {
		t.Fatalf("ai_text should be the v1 'ai' body, got %q", p.AIText)
	}
	if !strings.Contains(p.HumanText, "human corrected") {
		t.Fatalf("human_text should be the v2 'owner' body, got %q", p.HumanText)
	}
}

func TestGoldPairs_PicksLatestAiBeforeLatestOwner(t *testing.T) {
	// The subtle invariant: with a multi-revision history the pair must be the
	// LATEST 'ai' draft that PRECEDES the LATEST 'owner' edit. Here:
	//   v1 ai → v2 owner → v3 ai (regen, not yet corrected) → v4 owner
	// must yield (v3 ai, v4 owner) — NOT (v1, v2), and v3 must NOT be left
	// unpaired against v2. Guards the `version < h.version` + DISTINCT-ON logic
	// against a future `<`→`<=` or ordering regression. (/review-impl F2)
	f := newMergeFixture(t, "00000000f0a4")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Harker", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	seedRev(t, f, art, 1, "ai", "draft one stale")
	seedRev(t, f, art, 2, "owner", "human one stale")
	seedRev(t, f, art, 3, "ai", "draft three latest")
	seedRev(t, f, art, 4, "owner", "human four latest")

	pairs := getGoldPairs(t, f, "")
	if len(pairs) != 1 {
		t.Fatalf("want exactly 1 gold pair (one per article), got %d", len(pairs))
	}
	p := pairs[0]
	if !strings.Contains(p.AIText, "draft three latest") {
		t.Fatalf("ai_text must be the v3 draft preceding the v4 owner, got %q", p.AIText)
	}
	if strings.Contains(p.AIText, "stale") {
		t.Fatalf("ai_text must NOT be the stale v1 draft, got %q", p.AIText)
	}
	if !strings.Contains(p.HumanText, "human four latest") {
		t.Fatalf("human_text must be the v4 owner edit, got %q", p.HumanText)
	}
}

func TestGoldPairs_AiOnlyNotReturned(t *testing.T) {
	f := newMergeFixture(t, "00000000f0a2")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Lucy", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	seedRev(t, f, art, 1, "ai", "only an ai draft, no human edit")

	if got := getGoldPairs(t, f, ""); len(got) != 0 {
		t.Fatalf("an ai-only article is not a gold pair, got %d", len(got))
	}
}

func TestGoldPairs_OwnerBeforeAiNotPaired(t *testing.T) {
	// a human revision with NO preceding 'ai' draft (a hand-authored article) → not gold.
	f := newMergeFixture(t, "00000000f0a3")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Renfield", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	seedRev(t, f, art, 1, "owner", "hand-authored, never AI")

	if got := getGoldPairs(t, f, ""); len(got) != 0 {
		t.Fatalf("an owner-only article is not a gold pair, got %d", len(got))
	}
}

func TestTiptapPlaintextAndTruncate(t *testing.T) {
	doc := json.RawMessage(
		`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"Hello"},{"type":"text","text":"world"}]}]}`)
	got := tiptapPlaintext(doc)
	if !strings.Contains(got, "Hello") || !strings.Contains(got, "world") {
		t.Fatalf("plaintext: got %q", got)
	}
	if got := truncateRunes("abcdef", 3); got != "abc" {
		t.Fatalf("truncate: got %q", got) // db-safety-gate: ok — assertion message for truncateRunes() (Go rune helper), not SQL
	}
	if got := truncateRunes("ab", 5); got != "ab" {
		t.Fatalf("truncate no-op: got %q", got) // db-safety-gate: ok — assertion message for truncateRunes(), not SQL
	}
	if got := truncateRunes("封神演义", 2); got != "封神" {
		t.Fatalf("rune-safe truncate: got %q", got)
	}
}
