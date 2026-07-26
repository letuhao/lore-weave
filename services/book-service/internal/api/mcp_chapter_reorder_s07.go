package api

// S-07 §3 — book_chapter_reorder MCP tool. Reorder was REST-only, so an agent driving the
// manuscript could create/delete/save chapters but not REORDER them. This wraps the same
// two-phase engine the REST route uses (lockActiveChapterTrack + writeChapterTrackOrder),
// which dodges the partial UNIQUE(book_id, sort_order, original_language) — see
// chapter_reorder.go. Together with book_chapter_set_part (S-02) it gives the agent full
// manuscript-structure parity with the human.
//
// Shape (spec §3): the body is the COMPLETE ordered chapter-id list for ONE language track.
// We resolve the track from the first listed chapter, lock it, and require the list to be an
// exact permutation of that track (every active chapter, once) — a partial or foreign list
// would strand slots, so it's a validation error, not a silent partial reorder.

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type chapterReorderIn struct {
	BookID     string   `json:"book_id" jsonschema:"the book whose chapters to reorder (UUID; you need edit access)"`
	ChapterIDs []string `json:"chapter_ids" jsonschema:"the book's active chapters in the NEW reading order — the COMPLETE set for one language track, each chapter exactly once (a partial or foreign list is rejected)"`
}
type chapterReorderOut struct {
	BookID           string             `json:"book_id"`
	OriginalLanguage string             `json:"original_language"`
	Chapters         []reorderedChapter `json:"chapters"`
}

func (s *Server) toolChapterReorder(ctx context.Context, _ *mcp.CallToolRequest, in chapterReorderIn) (*mcp.CallToolResult, chapterReorderOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, chapterReorderOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, chapterReorderOut{}, errors.New("book_id must be a UUID")
	}
	if len(in.ChapterIDs) == 0 {
		return nil, chapterReorderOut{}, errors.New("chapter_ids is required (the full new order)")
	}
	// Parse + reject duplicates up front (a repeated id would drop a chapter from the order).
	next := make([]uuid.UUID, 0, len(in.ChapterIDs))
	seen := make(map[uuid.UUID]bool, len(in.ChapterIDs))
	for _, raw := range in.ChapterIDs {
		id, perr := uuid.Parse(raw)
		if perr != nil {
			return nil, chapterReorderOut{}, errors.New("every chapter_id must be a UUID")
		}
		if seen[id] {
			return nil, chapterReorderOut{}, errors.New("chapter_ids must not repeat a chapter")
		}
		seen[id] = true
		next = append(next, id)
	}

	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, chapterReorderOut{}, mcpOwnershipError(err)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, chapterReorderOut{}, errors.New("failed to reorder chapters")
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit

	// The FIRST listed chapter fixes the language track being renumbered (like the REST route's
	// moved chapter). Both the chapter and the book must be active — you can't reorder into a
	// trashed book or seed the track from a trashed chapter.
	var lang string
	err = tx.QueryRow(ctx, `
SELECT c.original_language
FROM chapters c JOIN books b ON b.id = c.book_id
WHERE c.id = $1 AND c.book_id = $2 AND c.lifecycle_state = 'active' AND b.lifecycle_state = 'active'
`, next[0], bookID).Scan(&lang)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, chapterReorderOut{}, errors.New("the first chapter_id is not an active chapter of this book")
	}
	if err != nil {
		return nil, chapterReorderOut{}, errors.New("failed to reorder chapters")
	}

	order, err := lockActiveChapterTrack(ctx, tx, bookID, lang)
	if err != nil {
		return nil, chapterReorderOut{}, errors.New("failed to reorder chapters")
	}

	// The list MUST be an exact permutation of the locked track: same length + every id belongs.
	// (Same length + all-belong + no-dupes ⇒ it's a permutation.) A missing chapter would strand
	// a slot; a foreign/other-track chapter isn't ours to move here.
	if len(next) != len(order) {
		return nil, chapterReorderOut{}, errors.New(
			"chapter_ids must list every active chapter of this language track exactly once")
	}
	inTrack := make(map[uuid.UUID]bool, len(order))
	for _, id := range order {
		inTrack[id] = true
	}
	for _, id := range next {
		if !inTrack[id] {
			return nil, chapterReorderOut{}, errors.New(
				"a chapter_id is not an active chapter of this book's language track")
		}
	}

	out, err := writeChapterTrackOrder(ctx, tx, bookID, lang, next)
	if err != nil {
		return nil, chapterReorderOut{}, errors.New("failed to reorder chapters")
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, chapterReorderOut{}, errors.New("failed to reorder chapters")
	}
	return nil, chapterReorderOut{
		BookID:           bookID.String(),
		OriginalLanguage: lang,
		Chapters:         out,
	}, nil
}
