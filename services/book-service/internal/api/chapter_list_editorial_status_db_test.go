package api

// D-CHAPTER-LIST-STATUS-MISSING regression (Chapter Browser bug: a published
// book's chapters still read as "draft" in the list). Root cause: listChapters
// and listChaptersKeyset's SELECT + JSON response never included
// editorial_status/published_revision_id, so the FE's status badge (which
// treats a missing/undefined editorial_status as 'draft') silently rendered
// every chapter as draft regardless of its real DB state. DB-gated like the
// other *_db_test.go files: requires BOOK_TEST_DATABASE_URL, else skipped.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// TestListChapters_ReturnsEditorialStatus_DB proves the offset-paginated
// GET /v1/books/{book_id}/chapters response carries editorial_status +
// published_revision_id for both a still-draft chapter and one actually
// published via the real publish flow (publishViaConfirm) — not a hand-set
// column, so this also exercises the FK to chapter_revisions.
func TestListChapters_ReturnsEditorialStatus_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()

	draftBody := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"still a draft"}]}]}`)
	bookID, draftChID := seedChapterWithBody(t, ctx, pool, owner, draftBody)
	// seedChapterWithBody leaves title NULL (chapters.title is nullable); every
	// real ingestion path always sets one, so backfill it here to keep this test
	// on the same (title-populated) row shape production actually produces.
	if _, err := pool.Exec(ctx, `UPDATE chapters SET title='Draft Chapter' WHERE id=$1`, draftChID); err != nil {
		t.Fatalf("set draft title: %v", err)
	}

	// A second chapter in the SAME book, published before the /chapters call.
	var publishedChID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,'Published Chapter','c2.txt','en','text/plain',2,'k2','active','draft') RETURNING id`, bookID).Scan(&publishedChID); err != nil {
		t.Fatalf("seed second chapter: %v", err)
	}
	publishedBody := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"already published"}]}]}`)
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version) VALUES($1,$2,'json',1)`, publishedChID, publishedBody); err != nil {
		t.Fatalf("seed second draft: %v", err)
	}

	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	if code := publishViaConfirm(t, s, owner, bookID, publishedChID); code != http.StatusOK {
		t.Fatalf("publish = %d, want 200", code)
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/books/"+bookID.String()+"/chapters", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("list chapters = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v — %s", err, rr.Body.String())
	}

	byID := map[string]map[string]any{}
	for _, item := range out.Items {
		byID[item["chapter_id"].(string)] = item
	}

	draftItem, ok := byID[draftChID.String()]
	if !ok {
		t.Fatalf("draft chapter missing from response")
	}
	if draftItem["editorial_status"] != "draft" {
		t.Fatalf("draft chapter editorial_status = %v, want %q", draftItem["editorial_status"], "draft")
	}
	if draftItem["published_revision_id"] != nil {
		t.Fatalf("draft chapter published_revision_id = %v, want nil", draftItem["published_revision_id"])
	}

	publishedItem, ok := byID[publishedChID.String()]
	if !ok {
		t.Fatalf("published chapter missing from response")
	}
	if publishedItem["editorial_status"] != "published" {
		t.Fatalf("published chapter editorial_status = %v, want %q (this is the reported bug)", publishedItem["editorial_status"], "published")
	}
	if publishedItem["published_revision_id"] == nil {
		t.Fatalf("published chapter published_revision_id = nil, want a revision id")
	}
}

// TestListChaptersKeyset_ReturnsEditorialStatus_DB — same contract for the
// keyset-paginated GET /v1/books/{book_id}/chapters/page (manuscript
// navigator), which had the identical omission at a separate call site.
func TestListChaptersKeyset_ReturnsEditorialStatus_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()

	body := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"keyset published"}]}]}`)
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, body)
	// seedChapterWithBody leaves title NULL; backfill so the row shape matches
	// what every real ingestion path produces (see the sibling offset test).
	if _, err := pool.Exec(ctx, `UPDATE chapters SET title='Keyset Chapter' WHERE id=$1`, chID); err != nil {
		t.Fatalf("set title: %v", err)
	}

	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	if code := publishViaConfirm(t, s, owner, bookID, chID); code != http.StatusOK {
		t.Fatalf("publish = %d, want 200", code)
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/books/"+bookID.String()+"/chapters/page", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("list chapters (keyset) = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v — %s", err, rr.Body.String())
	}
	if len(out.Items) != 1 {
		t.Fatalf("items = %d, want 1", len(out.Items))
	}
	item := out.Items[0]
	if item["editorial_status"] != "published" {
		t.Fatalf("editorial_status = %v, want %q (this is the reported bug)", item["editorial_status"], "published")
	}
	if item["published_revision_id"] == nil {
		t.Fatalf("published_revision_id = nil, want a revision id")
	}
}
