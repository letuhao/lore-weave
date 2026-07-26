package api

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// book_get_chapter's opt-in include_body returns the chapter's plain-text prose
// (from the extracted, searchable chapter_blocks) so an agent can READ a chapter
// after story_search locates it. Default omits it (the body can be large).
func TestMCP_GetChapter_IncludeBody_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner) // draft_version = 1
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	// Write a draft whose prose carries a distinctive phrase; the chapter_blocks
	// extraction trigger makes it both searchable (story_search) and readable (here).
	// The tool takes PROSE (see saveDraftIn) and normalizes it to a Tiptap doc server-side.
	body := "He works for the firm of Mr. Peter Hawkins of Exeter."
	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), BaseVersion: 1, Body: body,
	}); err != nil {
		t.Fatalf("save draft: %v", err)
	}

	// Default (include_body omitted) → metadata only, no body.
	_, out, err := s.toolBookGetChapter(tctx, nil, getChapterIn{
		BookID: bookID.String(), ChapterID: chID.String(),
	})
	if err != nil {
		t.Fatalf("get chapter (no body): %v", err)
	}
	if out.Body != nil {
		t.Fatalf("body returned without include_body: %q", *out.Body)
	}

	// include_body=true → the prose contains the phrase.
	_, out, err = s.toolBookGetChapter(tctx, nil, getChapterIn{
		BookID: bookID.String(), ChapterID: chID.String(), IncludeBody: true,
	})
	if err != nil {
		t.Fatalf("get chapter (body): %v", err)
	}
	if out.Body == nil {
		t.Fatalf("include_body=true but body is nil")
	}
	if !strings.Contains(*out.Body, "Peter Hawkins of Exeter") {
		t.Fatalf("body missing the seeded phrase; got: %q", *out.Body)
	}
}
