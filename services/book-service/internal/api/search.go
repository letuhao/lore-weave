package api

import (
	"net/http"
	"strings"
	"unicode"

	"github.com/google/uuid"
)

// Raw search — Phase 1 (lexical leg). docs/specs/2026-06-07-raw-search.md §3.2,
// docs/plans/2026-06-07-raw-search.md (BE-2). Searches the DRAFT surface
// (chapter_blocks, kept fresh by trg_extract_chapter_blocks) of one book.
// Every hit is surface="draft" / matchType="lexical" by construction (the
// canon surface + semantic leg are Phase 2). Returns verbatim snippets with
// rune offsets for highlight + jump-to-source.

const (
	maxSearchQueryRunes = 256 // SP5 — query length cap (cost/injection guard)
	searchSnippetWindow = 160 // total context runes around a match
)

// lexicalSearchSQL — exact-substring (ILIKE, $3 = escaped pattern) is the
// PRIMARY matcher: it catches short CJK terms the trigram `%` operator misses
// at the default similarity_threshold; similarity() only ranks. The
// idx_chapter_blocks_trgm GIN index accelerates both legs of the OR.
//
//	$1 = book_id   $2 = raw query (similarity + trigram)
//	$3 = escaped ILIKE pattern   $4 = limit
const lexicalSearchSQL = `
SELECT cb.chapter_id, c.title, c.sort_order, cb.block_index, cb.heading_context,
       cb.text_content, similarity(cb.text_content, $2) AS sim
FROM chapter_blocks cb
JOIN chapters c ON c.id = cb.chapter_id
WHERE c.book_id = $1
  AND c.lifecycle_state = 'active'
  AND (cb.text_content ILIKE $3 OR cb.text_content % $2)
ORDER BY (cb.text_content ILIKE $3) DESC, sim DESC, c.sort_order, cb.block_index
LIMIT $4`

// validateSearchQuery trims ?q= and enforces presence + the length cap (SP5).
// errMsg non-empty ⇒ the handler returns 400.
func validateSearchQuery(raw string) (q, errMsg string) {
	q = strings.TrimSpace(raw)
	if q == "" {
		return "", "query is required"
	}
	if len([]rune(q)) > maxSearchQueryRunes {
		return "", "query too long"
	}
	return q, ""
}

// validateSurface accepts "", "draft", "canon", or "all" (ADJ-3). v1 always
// returns draft hits — a recognised value is accepted for forward-compat; an
// unrecognised one is a 400 so client typos don't silently fall through to draft.
func validateSurface(raw string) string {
	switch raw {
	case "", "draft", "canon", "all":
		return ""
	default:
		return "invalid surface"
	}
}

// escapeLikePattern wraps q in %…% for an ILIKE substring match, escaping the
// LIKE metacharacters (\ % _) so a literal "100%" or "a_b" matches literally.
// Default ILIKE ESCAPE is backslash.
func escapeLikePattern(q string) string {
	r := strings.NewReplacer(`\`, `\\`, `%`, `\%`, `_`, `\_`)
	return "%" + r.Replace(q) + "%"
}

type highlightResult struct {
	Snippet    string // windowed verbatim excerpt
	HLStart    int    // rune offset of the match within Snippet
	HLEnd      int
	BlockStart int // rune offset of the match within the full block text
	BlockEnd   int
	Matched    bool
}

// indexRunesFold returns the rune index of the first case-insensitive
// occurrence of q in t, or -1. Pure rune comparison — no byte/ToLower length
// subtleties — so CJK offsets are exact (ADJ-4).
func indexRunesFold(t, q []rune) int {
	if len(q) == 0 || len(q) > len(t) {
		return -1
	}
	for i := 0; i+len(q) <= len(t); i++ {
		match := true
		for j := 0; j < len(q); j++ {
			if unicode.ToLower(t[i+j]) != unicode.ToLower(q[j]) {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}

// computeHighlight locates query in text and returns a windowed verbatim
// snippet plus rune offsets — within the snippet (for rendering) and within the
// full block (for jump-to-source). On a trigram-only hit (no exact substring)
// it returns a leading window with Matched=false (no highlight span).
func computeHighlight(text, query string, window int) highlightResult {
	tr := []rune(text)
	mi := indexRunesFold(tr, []rune(query))
	if mi < 0 {
		end := len(tr)
		if end > window {
			end = window
		}
		return highlightResult{Snippet: string(tr[:end])}
	}
	matchEnd := mi + len([]rune(query))
	ctx := window / 2
	winStart := mi - ctx
	if winStart < 0 {
		winStart = 0
	}
	winEnd := matchEnd + ctx
	if winEnd > len(tr) {
		winEnd = len(tr)
	}
	return highlightResult{
		Snippet:    string(tr[winStart:winEnd]),
		HLStart:    mi - winStart,
		HLEnd:      matchEnd - winStart,
		BlockStart: mi,
		BlockEnd:   matchEnd,
		Matched:    true,
	}
}

// searchChapterText — GET /v1/books/{book_id}/search?q=&limit= (mode=lexical).
func (s *Server) searchChapterText(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	q, errMsg := validateSearchQuery(r.URL.Query().Get("q"))
	if errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	if errMsg := validateSurface(r.URL.Query().Get("surface")); errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	// Ownership IS the tenant gate (INV-4) — internal-token callers don't reach
	// this external route; here the JWT subject must own the book.
	lifecycle, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		if status == http.StatusNotFound {
			writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		} else {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to load book")
		}
		return
	}
	if lifecycle == "purge_pending" { // mirror getBookByID — don't search a book being purged (LOW-2)
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	limit, _ := parseLimitOffset(r) // default 20, max 100; v1 has no pagination (offset ignored, LOW-3)

	rows, err := s.pool.Query(r.Context(), lexicalSearchSQL, bookID, q, escapeLikePattern(q), limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "search failed")
		return
	}
	defer rows.Close()

	results := make([]map[string]any, 0)
	for rows.Next() {
		var chapterID uuid.UUID
		var title, headingCtx *string // nullable
		var sortOrder, blockIndex int
		var textContent string
		var sim float64
		if err := rows.Scan(&chapterID, &title, &sortOrder, &blockIndex, &headingCtx, &textContent, &sim); err != nil {
			continue
		}
		hl := computeHighlight(textContent, q, searchSnippetWindow)
		score := sim
		highlights := make([][]int, 0, 1)
		if hl.Matched {
			score = 1 + sim // exact-substring boost (mirrors the ILIKE-first ORDER BY)
			highlights = append(highlights, []int{hl.HLStart, hl.HLEnd})
		}
		// NOTE (review-impl MED-2): charStart/charEnd + highlights are Unicode
		// CODE-POINT (rune) offsets, NOT UTF-16 units — FE-1 must index by code
		// point (e.g. [...str]) so supplementary-plane chars don't misalign.
		results = append(results, map[string]any{
			"chapterId":    chapterID,
			"chapterTitle": title,
			"sortOrder":    sortOrder,
			"surface":      "draft",
			"matchType":    "lexical",
			"score":        score,
			"snippet":      hl.Snippet,
			"highlights":   highlights,
			"location": map[string]any{
				"blockIndex":     blockIndex,
				"headingContext": headingCtx,
				"charStart":      hl.BlockStart,
				"charEnd":        hl.BlockEnd,
			},
		})
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "search failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"query":   q,
		"mode":    "lexical",
		"results": results,
	})
}
