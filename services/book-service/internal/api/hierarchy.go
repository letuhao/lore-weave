package api

import (
	"errors"
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
// Legacy chapters (NULL part_id from pre-P1 imports) return part=null
// + scenes=[]; worker-ai treats that as "skip P3 enqueue" so the
// summarize_processor doesn't churn re-enqueue cycles on chapters that
// can't be summarized yet.

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
	var (
		chapterPath, chapterTitle     *string
		chapterSortOrder              int
		partID                        *uuid.UUID
		partPath, partTitle           *string
		partSortOrder                 *int
	)
	err = s.pool.QueryRow(r.Context(), `
SELECT c.structural_path, c.title, c.sort_order,
       p.id, p.path, p.title, p.sort_order
FROM chapters c
LEFT JOIN parts p ON p.id = c.part_id
WHERE c.id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'
`, chapterID, bookID).Scan(
		&chapterPath, &chapterTitle, &chapterSortOrder,
		&partID, &partPath, &partTitle, &partSortOrder,
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

	// All parts in the book — for the is_last_chapter_of_book →
	// summary.part × N enqueue tail. Empty for legacy books.
	bookParts := []hierarchyPart{}
	rows, err = s.pool.Query(r.Context(), `
SELECT id, path, sort_order, title
FROM parts
WHERE book_id=$1 AND lifecycle_state='active'
ORDER BY sort_order
`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "parts query failed")
		return
	}
	for rows.Next() {
		var id uuid.UUID
		var path string
		var sortOrder int
		var title *string
		if err := rows.Scan(&id, &path, &sortOrder, &title); err == nil {
			bookParts = append(bookParts, hierarchyPart{
				ID: id.String(), Path: path, Index: sortOrder, Title: title,
			})
		}
	}
	rows.Close()

	// Assemble response.
	book := hierarchyBook{
		ID: bookID.String(), Path: "book", Title: bookTitle,
	}
	chapter := hierarchyChapter{
		ID: chapterID.String(), Path: chapterPath, Title: chapterTitle,
		Index: chapterSortOrder, SortOrder: chapterSortOrder,
	}
	var part *hierarchyPart
	if partID != nil && partPath != nil && partSortOrder != nil {
		part = &hierarchyPart{
			ID: partID.String(), Path: *partPath,
			Index: *partSortOrder, Title: partTitle,
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"book":       book,
		"part":       part,
		"chapter":    chapter,
		"scenes":     scenes,
		"book_parts": bookParts,
	})
}
