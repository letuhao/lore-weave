package api

import (
	"errors"
	"fmt"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// hierarchy.go — P3 D-P3-EXTRACTION-CALLER-WIRE-UP book-service side.
//
// One NEW internal HTTP endpoint consumed by worker-ai before calling
// knowledge-service's /persist-pass2 with P3 fields:
//
//   GET /internal/books/{book_id}/chapters/{chapter_id}/hierarchy
//       -> book / part / chapter / scenes / book_parts info needed to
//          construct the HierarchyPathsPayload the persist-pass2
//          handler expects.
//
// Undecomposed chapters (NULL part_id / NULL structural_path from pre-P1
// imports) get a DETERMINISTIC synthesized single implicit part
// ("book/part-1") + a synthesized chapter path, so the P3
// Book→Part→Chapter summary pipeline runs for legacy/flat books instead
// of silently opting out (D-KG-SUMMARIES-TARGET-NOOP — the majority of
// imported novels had NO part tier, so their chapter summaries never
// generated and "where is X at chapter N" recall punted). MERGE-on-path
// is idempotent + deterministic, so a later real decomposition reuses
// the same node (no graph drift). scenes stay []; :MENTIONED_IN then
// targets :Chapter directly (D6 fallback).

type hierarchyBook struct {
	ID    string  `json:"id"`
	Path  string  `json:"path"`
	Title *string `json:"title"`
}

type hierarchyPart struct {
	ID    string  `json:"id"`
	Path  string  `json:"path"`
	Index int     `json:"index"`
	Title *string `json:"title"`
}

type hierarchyChapter struct {
	ID        string  `json:"id"`
	Path      *string `json:"path"`
	Index     int     `json:"index"`
	Title     *string `json:"title"`
	SortOrder int     `json:"sort_order"`
}

type hierarchyScene struct {
	ID    string `json:"id"`
	Path  string `json:"path"`
	Index int    `json:"index"`
}

// getInternalChapterHierarchy handles
// GET /internal/books/{book_id}/chapters/{chapter_id}/hierarchy.
//
// Returns the hierarchy info worker-ai needs to construct a P3
// HierarchyPathsPayload + book_parts list:
//
//   - book:   id + synthesized path "book" + title (NULL if untitled)
//   - part:   id/path/index/title — null for legacy chapters (no part_id)
//   - chapter: id/path/index/title/sort_order — path may be null
//             for legacy chapters
//   - scenes: ordered list of scene id/path/index for this chapter
//   - book_parts: ordered list of ALL parts in the book (for the
//                 is_last_chapter_of_book book-summary enqueue path)
//
// Legacy chapters (NULL part_id, NULL structural_path) get part=null
// + chapter.path=null + scenes=[] — worker-ai treats that as opt-out
// of P3 summary enqueue.
func (s *Server) getInternalChapterHierarchy(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}

	// Book row: title only. Book "path" is always "book" per P1
	// structural decomposer convention (book_path string field on
	// HierarchyPaths in knowledge-service).
	var bookTitle *string
	err := s.pool.QueryRow(r.Context(), `
SELECT title FROM books WHERE id=$1 AND lifecycle_state='active'
`, bookID).Scan(&bookTitle)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "book lookup failed")
		return
	}

	// Chapter row + optional part join. LEFT JOIN so legacy chapters
	// (NULL part_id) still return — worker-ai checks part-null and
	// skips P3 enqueue for those.
	// C-merge C4 — parts moved to composition; book-service no longer joins a parts table. Chapters
	// resolve part-less here, so worker-ai/KG uses the synthetic single-part fallback (the same path
	// legacy/flat books always took). The part tier for a grouped book is a composition concern.
	var (
		chapterPath, chapterTitle *string
		chapterSortOrder          int
		partID                    *uuid.UUID
		partPath, partTitle       *string
		partSortOrder             *int
	)
	err = s.pool.QueryRow(r.Context(), `
SELECT c.structural_path, c.title, c.sort_order
FROM chapters c
WHERE c.id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'
`, chapterID, bookID).Scan(
		&chapterPath, &chapterTitle, &chapterSortOrder,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found in book")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "chapter lookup failed")
		return
	}

	// Scenes for this chapter — ordered by sort_order. Legacy chapters
	// return an empty list.
	scenes := []hierarchyScene{}
	rows, err := s.pool.Query(r.Context(), `
SELECT id, path, sort_order
FROM scenes
WHERE chapter_id=$1 AND lifecycle_state='active'
ORDER BY sort_order
`, chapterID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "scenes query failed")
		return
	}
	for rows.Next() {
		var id uuid.UUID
		var path string
		var sortOrder int
		if err := rows.Scan(&id, &path, &sortOrder); err == nil {
			scenes = append(scenes, hierarchyScene{
				ID: id.String(), Path: path, Index: sortOrder,
			})
		}
	}
	rows.Close()

	// C-merge C4 — no book-service parts table; the synthetic-part fallback (resolveHierarchyPart)
	// supplies the single implicit part for the summary pipeline. Empty here.
	bookParts := []hierarchyPart{}

	// Assemble response.
	book := hierarchyBook{
		ID: bookID.String(), Path: "book", Title: bookTitle,
	}
	chapter := hierarchyChapter{
		ID: chapterID.String(), Path: chapterPath, Title: chapterTitle,
		Index: chapterSortOrder, SortOrder: chapterSortOrder,
	}
	var part *hierarchyPart
	part, bookParts, chapter.Path = resolveHierarchyPart(
		bookID,
		partID, partPath, partSortOrder, partTitle,
		chapter.Path, chapterSortOrder, bookParts,
	)

	writeJSON(w, http.StatusOK, map[string]any{
		"book":       book,
		"part":       part,
		"chapter":    chapter,
		"scenes":     scenes,
		"book_parts": bookParts,
	})
}

// resolveHierarchyPart returns the part a chapter attaches to, the (possibly
// extended) book_parts list, and the (possibly synthesized) chapter path.
//
// A decomposed chapter (real part_id) passes through unchanged. An UNDECOMPOSED
// chapter (NULL part_id / structural_path — the common legacy/flat-book case)
// gets a DETERMINISTIC single implicit part "book/part-1"
// (part_id = uuidv5(book_id,"book/part-1")) + a synthesized chapter path, so
// the P3 Book→Part→Chapter summary pipeline runs instead of silently opting out
// (D-KG-SUMMARIES-TARGET-NOOP). MERGE-on-path is idempotent + deterministic, so
// a later real decomposition reuses the node — no graph drift. Pure (no DB) so
// the synthesis decision is unit-testable without a pool mock.
func resolveHierarchyPart(
	bookID uuid.UUID,
	partID *uuid.UUID, partPath *string, partSortOrder *int, partTitle *string,
	chapterPath *string, chapterSortOrder int,
	bookParts []hierarchyPart,
) (*hierarchyPart, []hierarchyPart, *string) {
	if partID != nil && partPath != nil && partSortOrder != nil {
		return &hierarchyPart{
			ID: partID.String(), Path: *partPath,
			Index: *partSortOrder, Title: partTitle,
		}, bookParts, chapterPath
	}
	const synthPartPath = "book/part-1"
	synthPartID := uuid.NewSHA1(bookID, []byte(synthPartPath))
	part := &hierarchyPart{
		ID: synthPartID.String(), Path: synthPartPath, Index: 1, Title: nil,
	}
	// The is_last_chapter_of_book tail enqueues one summary.part per book_parts
	// entry — a flat book's parts query is empty, so include the synthetic part
	// for the book-summary roll-up. If real parts exist (mixed book) leave them.
	if len(bookParts) == 0 {
		bookParts = append(bookParts, *part)
	}
	// Synthesize the chapter's structural path when it was never decomposed
	// (NULL structural_path) so :Chapter MERGEs under the implicit part.
	// chapter_index (knowledge payload ge=1) is the ≥1 sort_order.
	if chapterPath == nil {
		cp := fmt.Sprintf("%s/chapter-%d", synthPartPath, chapterSortOrder)
		chapterPath = &cp
	}
	return part, bookParts, chapterPath
}
