// 24 PH20 Row-3 — the manuscript reading-order reorder.
//
// Why this endpoint exists at all: `sort_order` was already writable via the generic
// PATCH /chapters/{id}, but a REORDER is impossible through it. `idx_chapters_unique_slot_lang_active`
// is a partial UNIQUE on (book_id, sort_order, original_language) WHERE active, so moving chapter 5
// into slot 2 collides with the chapter already holding slot 2 → 409. A reorder is inherently a
// multi-row permutation and has to be ONE transaction.
//
// Dodging the unique index: a permutation cannot be written in a single UPDATE, because Postgres
// checks a non-deferrable unique index per ROW, so an intermediate state would collide. So we write
// it in TWO statements whose target value-sets are disjoint from their source sets:
//   1. negate every affected slot   (positive → negative: no negative row exists yet ⇒ no collision)
//   2. write the final dense slots  (negative → positive: no positive row remains ⇒ no collision)
//
// Concurrency: the load takes FOR UPDATE on the book's active chapters in that language, which
// serializes two racing reorders. That is why no `version`/If-Match column is needed here — the
// operation is a whole-sequence rewrite, not a field edit, so "last writer wins on a serialized
// sequence" is the correct semantic (a stale client just re-reads the new order).
//
// Language scope: the unique slot includes `original_language`, i.e. parallel language tracks share
// slot numbers. So a reorder renumbers ONLY the moved chapter's language track, leaving any other
// track's slots untouched (a single-language book — the normal case — is the whole book).
package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

type reorderChaptersRequest struct {
	ChapterID uuid.UUID `json:"chapter_id"`
	// Place the chapter directly AFTER this one. null/absent ⇒ make it the FIRST chapter.
	AfterChapterID *uuid.UUID `json:"after_chapter_id"`
}

type reorderedChapter struct {
	ChapterID uuid.UUID `json:"chapter_id"`
	SortOrder int       `json:"sort_order"`
}

// reorderChapters — POST /v1/books/{book_id}/chapters/reorder
func (s *Server) reorderChapters(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	var in reorderChaptersRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	if in.ChapterID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "chapter_id is required")
		return
	}
	if in.AfterChapterID != nil && *in.AfterChapterID == in.ChapterID {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
			"after_chapter_id must not be the chapter being moved")
		return
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reorder chapters")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit

	// The moved chapter fixes the language TRACK being renumbered. Book + chapter must both be
	// active — reordering into a trashed book, or moving a trashed chapter into the live sequence,
	// is not a reorder.
	var lang string
	err = tx.QueryRow(ctx, `
SELECT c.original_language
FROM chapters c JOIN books b ON b.id = c.book_id
WHERE c.id = $1 AND c.book_id = $2
  AND c.lifecycle_state = 'active' AND b.lifecycle_state = 'active'
`, in.ChapterID, bookID).Scan(&lang)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reorder chapters")
		return
	}

	// FOR UPDATE serializes concurrent reorders of the same track (see the file header).
	order, err := lockActiveChapterTrack(ctx, tx, bookID, lang)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reorder chapters")
		return
	}

	next, ok := moveWithin(order, in.ChapterID, in.AfterChapterID)
	if !ok {
		// after_chapter_id is not a live chapter of this book+language track.
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
			"after_chapter_id is not an active chapter of this book")
		return
	}

	out, err := writeChapterTrackOrder(ctx, tx, bookID, lang, next)
	if err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to reorder chapters")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to reorder chapters")
		return
	}

	// The whole new sequence — the caller's mirror (composition's story_order) must be rebuilt from
	// it, so returning only the moved chapter would force an extra read.
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":           bookID,
		"original_language": lang,
		"chapters":          out,
	})
}

// lockActiveChapterTrack loads the book's active chapter ids in `lang`, in reading order,
// taking FOR UPDATE so concurrent reorders of the same track serialize (file header). Shared
// by the REST reorder handler and the S-07 book_chapter_reorder MCP tool so the collision-
// dodging load lives once.
func lockActiveChapterTrack(ctx context.Context, tx pgx.Tx, bookID uuid.UUID, lang string) ([]uuid.UUID, error) {
	rows, err := tx.Query(ctx, `
SELECT id FROM chapters
WHERE book_id = $1 AND original_language = $2 AND lifecycle_state = 'active'
ORDER BY sort_order, id
FOR UPDATE
`, bookID, lang)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var order []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		order = append(order, id)
	}
	return order, rows.Err()
}

// writeChapterTrackOrder applies `next` — the COMPLETE desired order of the book's active
// chapters in `lang` — via the two-phase negate/rewrite that dodges the partial UNIQUE
// (book_id, sort_order, original_language). The caller must hold `tx` (having locked the
// track via lockActiveChapterTrack) and pass every active chapter of the track exactly once;
// a partial/foreign list would strand slots. Returns the dense 1..N slots. See the file
// header for why a permutation cannot be written in one UPDATE. Shared by REST + MCP.
func writeChapterTrackOrder(ctx context.Context, tx pgx.Tx, bookID uuid.UUID, lang string, next []uuid.UUID) ([]reorderedChapter, error) {
	// Phase 1: park every slot in the negative space (source positives → target negatives; the
	// two sets are disjoint, so the per-row unique check never trips).
	if _, err := tx.Exec(ctx, `
UPDATE chapters SET sort_order = -sort_order - 1
WHERE book_id = $1 AND original_language = $2 AND lifecycle_state = 'active'
`, bookID, lang); err != nil {
		return nil, err
	}
	// Phase 2: write the dense 1..N sequence (negatives → positives; disjoint again).
	out := make([]reorderedChapter, 0, len(next))
	for i, id := range next {
		slot := i + 1
		if _, err := tx.Exec(ctx, `
UPDATE chapters SET sort_order = $3, updated_at = now()
WHERE id = $1 AND book_id = $2
`, id, bookID, slot); err != nil {
			return nil, err
		}
		out = append(out, reorderedChapter{ChapterID: id, SortOrder: slot})
	}
	return out, nil
}

// moveWithin returns `order` with `id` lifted out and re-inserted directly AFTER `afterID`
// (nil ⇒ at the front). ok=false when afterID is given but absent from the sequence — the caller
// turns that into a 400 rather than silently placing the chapter somewhere the user didn't ask for.
// Pure, so the permutation itself is unit-testable without a database.
func moveWithin(order []uuid.UUID, id uuid.UUID, afterID *uuid.UUID) ([]uuid.UUID, bool) {
	rest := make([]uuid.UUID, 0, len(order))
	found := false
	for _, x := range order {
		if x == id {
			found = true
			continue
		}
		rest = append(rest, x)
	}
	if !found {
		return nil, false
	}
	if afterID == nil {
		return append([]uuid.UUID{id}, rest...), true
	}
	at := -1
	for i, x := range rest {
		if x == *afterID {
			at = i
			break
		}
	}
	if at < 0 {
		return nil, false
	}
	next := make([]uuid.UUID, 0, len(order))
	next = append(next, rest[:at+1]...)
	next = append(next, id)
	next = append(next, rest[at+1:]...)
	return next, true
}
