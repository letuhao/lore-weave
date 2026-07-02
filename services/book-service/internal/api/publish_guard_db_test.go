package api

// Empty-prose publish-guard regression (Track 4 eval standup finding). The guard
// used to extract prose ONLY from the editor's `_text` projection
// ($.content[*]._text), so a chapter whose draft body is STANDARD tiptap (nested
// {"type":"text","text":…} leaves, no `_text` — e.g. the compose POC import path)
// was false-rejected with CHAPTER_EMPTY_PUBLISH / errActionBadState, blocking
// canon + KG extraction for the whole book. The fix unions both extractions
// ($.content[*]._text  ∪  $.**.text). DB-gated like mcp_actions_db_test.go:
// requires BOOK_TEST_DATABASE_URL (real PG — jsonb_path_query), else skipped.

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// seedChapterWithBody mirrors seedChapter but with a caller-supplied draft body.
func seedChapterWithBody(t *testing.T, ctx context.Context, pool *pgxpool.Pool, ownerID uuid.UUID, body json.RawMessage) (bookID, chID uuid.UUID) {
	t.Helper()
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'t') RETURNING id`, ownerID).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,'c.txt','en','text/plain',1,'k','active','draft') RETURNING id`, bookID).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version) VALUES($1,$2,'json',1)`, chID, body); err != nil {
		t.Fatalf("seed draft: %v", err)
	}
	return bookID, chID
}

func publishViaConfirm(t *testing.T, s *Server, owner, bookID, chID uuid.UUID) int {
	t.Helper()
	tok, err := lwmcp.MintConfirmToken(mcpConfirmSecret, owner, bookID, descBookPublish,
		actionPayload{Op: "publish", ChapterID: chID.String()}, actionTokenTTL)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	return confirmReq(t, s, owner, tok).Code
}

// A standard tiptap body (nested text leaves, NO `_text` projection) must publish.
// Pre-fix this was refused as "empty" — the false-reject this test pins down.
func TestPublishGuard_StandardTiptap_NoTextProjection_Publishes_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	body := json.RawMessage(`{"type":"doc","content":[
	  {"type":"heading","attrs":{"level":3},"content":[{"type":"text","text":"Sự Phản Bội"}]},
	  {"type":"paragraph","content":[{"type":"text","text":"Ánh trăng lạnh lẽo hắt qua khung cửa sổ."}]}
	]}`)
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, body)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	if code := publishViaConfirm(t, s, owner, bookID, chID); code != http.StatusOK {
		t.Fatalf("standard-tiptap publish = %d, want 200 (guard false-rejected nested text)", code)
	}
	var status string
	if err := pool.QueryRow(ctx, `SELECT editorial_status FROM chapters WHERE id=$1`, chID).Scan(&status); err != nil {
		t.Fatalf("read status: %v", err)
	}
	if status != "published" {
		t.Fatalf("editorial_status = %q, want published", status)
	}
}

// The legacy editor `_text`-projection shape must STILL publish (back-compat).
func TestPublishGuard_TextProjectionShape_StillPublishes_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	body := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","_text":"hello world"}]}`)
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, body)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	if code := publishViaConfirm(t, s, owner, bookID, chID); code != http.StatusOK {
		t.Fatalf("_text-projection publish = %d, want 200 (back-compat regressed)", code)
	}
}

// A truly empty doc must still be refused — the guard is fixed, not removed.
func TestPublishGuard_TrulyEmptyBody_StillRefused_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	body := json.RawMessage(`{"type":"doc","content":[]}`)
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, body)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	if code := publishViaConfirm(t, s, owner, bookID, chID); code == http.StatusOK {
		t.Fatalf("empty-body publish = 200, want refusal (empty-prose guard lost)")
	}
	var status string
	if err := pool.QueryRow(ctx, `SELECT editorial_status FROM chapters WHERE id=$1`, chID).Scan(&status); err != nil {
		t.Fatalf("read status: %v", err)
	}
	if status != "draft" {
		t.Fatalf("editorial_status = %q, want draft (must not have published)", status)
	}
}
