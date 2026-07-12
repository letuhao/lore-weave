package api

// prose_state.go — GET /internal/books/{book_id}/prose-state.
//
// chat-service calls this ONCE PER CHAT TURN to answer "does this book actually
// have prose in it yet?", so it must be a single cheap round-trip: one query, no
// pagination, no N+1.
//
// Why this is NOT just the existing GET /internal/books/{book_id}/chapters:
//   - that route clamps `limit` to 100 (parseLimitOffset), so a >100-chapter book
//     would need the caller to page just to count;
//   - its `word_count_estimate` only looks at chapter_drafts, so an IMPORTED book
//     whose prose lives in chapter_raw_objects.body_text reports 0 words for every
//     chapter — an imported novel would look empty.
//
// The "has prose" predicate is deliberately NOT `EXISTS (SELECT 1 FROM chapter_drafts)`.
// Every chapter-creation path unconditionally inserts a chapter_drafts row (server.go
// createChapter, import.go, parse.go, mcp_tools_write.go), and plainTextToTiptapJSON("")
// still yields a structurally valid doc — {"type":"doc","content":[{"type":"paragraph",
// "_text":""}]}. A bare EXISTS would therefore report a book of blank chapters as fully
// prose-bearing (the inverse of the bug this endpoint exists to fix). Instead we reuse
// the service's OWN authoritative prose predicate — the publish-time empty-prose guard
// (mcp_actions.go publishChapterTx, server.go publishChapter): the union of the editor's
// `_text` projection ($.content[*]._text) AND standard tiptap nested text leaves
// ($.**.text), trimmed. Lax jsonpath (not strict) exactly as those call sites use it;
// `**` can double-visit a single-text-node block, but duplication cannot change an
// emptiness test.

import (
	"context"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// proseStateQuerier is the minimal DB surface queryBookProseState needs — satisfied
// by *pgxpool.Pool and by pgxmock, so the SQL is unit-testable without a real DB.
// Mirrors the auditQuerier pattern in tenant_audit.go.
type proseStateQuerier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// proseStateSQL counts a book's active chapters and, in the same pass, how many of
// them actually carry prose (draft text OR imported raw body). One statement, one
// round-trip; the two EXISTS are correlated semi-joins, not per-chapter queries.
//
// Draft prose is read from chapter_blocks.text_content — the trigger-maintained
// (fn_extract_chapter_blocks) PLAIN-TEXT projection of the Tiptap draft body, with an
// index on chapter_id. The first cut jsonb_path_query'd the raw draft JSONB per chapter,
// which detoasts and walks every body: a review measured 2.28s on a 10k-chapter book,
// OVER the probe's own 2s timeout, so the source would fail on a large manuscript exactly
// when it matters. The projection exists precisely to avoid that scan; using it is an
// indexed semi-join. (Trade-off accepted: a legacy chapter whose blocks were never
// backfilled would under-count as "no prose" — a small, degrading error, far better than
// a hard timeout that returns UNKNOWN for the whole source.)
//
// Both counts are count(*) aggregates, which return 0 (never NULL) over an empty input,
// so a zero-chapter book scans cleanly into plain ints — no NULL-into-non-pointer hazard.
//
// Emptiness is tested with ~ '[^[:space:]]' ("contains a non-whitespace character"), NOT
// btrim(x) <> '' — single-arg btrim trims only spaces, so a "\n"-only body would count as
// prose (caught by prose_state_db_test.go against real PG; a mock cannot see it).
const proseStateSQL = `
SELECT
  count(*) AS total,
  count(*) FILTER (
    WHERE EXISTS (
            SELECT 1 FROM chapter_blocks b
            WHERE b.chapter_id = c.id
              AND b.text_content ~ '[^[:space:]]'
          )
       OR EXISTS (
            SELECT 1 FROM chapter_raw_objects r
            WHERE r.chapter_id = c.id
              AND r.body_text ~ '[^[:space:]]'
          )
  ) AS with_prose
FROM chapters c
WHERE c.book_id = $1 AND c.lifecycle_state = 'active'`

// queryBookProseState runs the single counting query. Pool-agnostic (takes the
// querier) so a pgxmock test can pin the statement + args without a live DB.
// The scan error is RETURNED, never discarded — a swallowed scan here would
// report every book as empty (chapters=0), and the caller would silently treat a
// full novel as an empty one.
func queryBookProseState(ctx context.Context, q proseStateQuerier, bookID uuid.UUID) (total, withProse int, err error) {
	if err = q.QueryRow(ctx, proseStateSQL, bookID).Scan(&total, &withProse); err != nil {
		return 0, 0, err
	}
	return total, withProse, nil
}

// getInternalBookProseState handles GET /internal/books/{book_id}/prose-state.
//
// A book with no chapters (or a book_id that does not exist) is a 200 with zeros,
// NOT a 404: the caller asks this every turn and only wants the counts, so "no
// chapters" and "no book" collapse to the same cheap, honest answer — and keeping
// it to one query is the whole point. Existence/authorization is the internal
// token's job (this route sits inside the requireInternalToken group).
func (s *Server) getInternalBookProseState(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book id")
		return
	}
	total, withProse, err := queryBookProseState(r.Context(), s.pool, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read prose state")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":    bookID,
		"chapters":   total,
		"with_prose": withProse,
	})
}
