package api

import (
	"context"
	"net/http"
	"sort"
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

// lexicalSearchChapterSQL — E5 "chapter" granularity (navigate): one BEST block
// per chapter, so `LIMIT $4` bounds distinct CHAPTERS, not blocks. The flat
// block SQL spent its limit on blocks that cluster into few chapters, capping
// recall for wide terms (P3-EVAL: lexical oracle-recall 0.63). A window function
// keeps the top-ranked block per chapter (exact-first, then similarity), then the
// outer query ranks chapters. Same 7 projected columns as lexicalSearchSQL.
//
//	$1 = book_id   $2 = raw query   $3 = escaped ILIKE pattern   $4 = limit
const lexicalSearchChapterSQL = `
SELECT t.chapter_id, t.title, t.sort_order, t.block_index, t.heading_context,
       t.text_content, t.sim
FROM (
  SELECT cb.chapter_id, c.title, c.sort_order, cb.block_index, cb.heading_context,
         cb.text_content, similarity(cb.text_content, $2) AS sim,
         (cb.text_content ILIKE $3) AS exact,
         ROW_NUMBER() OVER (
           PARTITION BY cb.chapter_id
           ORDER BY (cb.text_content ILIKE $3) DESC, similarity(cb.text_content, $2) DESC,
                    cb.block_index
         ) AS rn
  FROM chapter_blocks cb
  JOIN chapters c ON c.id = cb.chapter_id
  WHERE c.book_id = $1
    AND c.lifecycle_state = 'active'
    AND (cb.text_content ILIKE $3 OR cb.text_content % $2)
) t
WHERE t.rn = 1
ORDER BY t.exact DESC, t.sim DESC, t.sort_order
LIMIT $4`

// lexicalSearchCanonSQL — P3-B canon surface. Searches the PUBLISHED revision
// text per chapter (chapter_revisions.body JSONB `_text` elements) rather than
// the live draft chapter_blocks. block_index = JSONB content-array ordinal,
// which matches the reader's data-block-id for a published chapter (P3-C scroll).
// No trigram GIN on the JSONB text → a seq scan; acceptable until a canon corpus
// exists (then denormalize to a canon_blocks table). Same 7 projected columns as
// the draft SQLs so buildLexicalHit/runLexicalSQL are shared.
//
//	$1 = book_id   $2 = raw query   $3 = escaped ILIKE pattern   $4 = limit
const lexicalSearchCanonSQL = `
SELECT c.id, c.title, c.sort_order, (x.ord - 1)::int AS block_index,
       NULL::text AS heading_context, (x.elem ->> '_text') AS text_content,
       similarity(x.elem ->> '_text', $2) AS sim
FROM chapters c
JOIN chapter_revisions rv ON rv.id = c.published_revision_id
CROSS JOIN LATERAL jsonb_array_elements(rv.body -> 'content') WITH ORDINALITY AS x(elem, ord)
WHERE c.book_id = $1
  AND c.lifecycle_state = 'active'
  AND (x.elem ->> '_text') IS NOT NULL
  AND ((x.elem ->> '_text') ILIKE $3 OR (x.elem ->> '_text') % $2)
ORDER BY ((x.elem ->> '_text') ILIKE $3) DESC, sim DESC, c.sort_order, x.ord
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

// validateSurface normalises ?surface= (P3-B). "" defaults to "draft" (live
// chapter_blocks); "canon" searches the published-revision text; "all" merges
// both. An unrecognised value is a 400 so client typos don't fall through.
func validateSurface(raw string) (surface, errMsg string) {
	switch raw {
	case "", "draft":
		return "draft", ""
	case "canon":
		return "canon", ""
	case "all":
		return "all", ""
	default:
		return "", "invalid surface"
	}
}

// validateGranularity normalises ?granularity= (E5). "" defaults to "chapter"
// (best-block-per-chapter — the navigate default, strictly better chapter recall
// than the flat block list). "block" returns every matching block (exhaustive
// mining). An unrecognised value is a 400 so client typos don't silently fall
// through to the default.
func validateGranularity(raw string) (granularity, errMsg string) {
	switch raw {
	case "", "chapter":
		return "chapter", ""
	case "block":
		return "block", ""
	default:
		return "", "invalid granularity"
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
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	q, errMsg := validateSearchQuery(r.URL.Query().Get("q"))
	if errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	surface, errMsg := validateSurface(r.URL.Query().Get("surface"))
	if errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	granularity, errMsg := validateGranularity(r.URL.Query().Get("granularity"))
	if errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	// Grant IS the tenant gate (INV-4) — internal-token callers don't reach this
	// external route; here the JWT subject must hold ≥view on the book (E0-2).
	_, _, lifecycle, ok := s.authBook(w, r, bookID, GrantView)
	if !ok {
		return
	}
	if lifecycle == "purge_pending" { // mirror getBookByID — don't search a book being purged (LOW-2)
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	limit, _ := parseLimitOffset(r) // default 20, max 100; v1 has no pagination (offset ignored, LOW-3)
	results, err := s.runLexicalSearch(r.Context(), bookID, q, limit, granularity, surface)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "search failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"query":   q,
		"mode":    "lexical",
		"results": results,
	})
}

// searchChapterTextInternal — GET /internal/books/{book_id}/lexical-search?q=&limit=.
// Internal-token gated (caller-trusted: no ownership re-check, matching the other
// /internal endpoints). The Phase-2 knowledge orchestrator calls this for the
// lexical leg after it has already resolved the user's project for the book.
func (s *Server) searchChapterTextInternal(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	q, errMsg := validateSearchQuery(r.URL.Query().Get("q"))
	if errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	granularity, errMsg := validateGranularity(r.URL.Query().Get("granularity"))
	if errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	surface, errMsg := validateSurface(r.URL.Query().Get("surface"))
	if errMsg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errMsg)
		return
	}
	limit, _ := parseLimitOffset(r)
	results, err := s.runLexicalSearch(r.Context(), bookID, q, limit, granularity, surface)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "search failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"results": results})
}

// buildLexicalHit maps one scanned chapter_blocks row → the raw-search hit map.
// Pure (no DB) so the highlight/score/relevance/offset logic is unit-testable
// without a live Postgres (D-RAWSEARCH-HANDLER-COVERAGE). `sim` is the trigram
// similarity from the SQL; an exact substring (computeHighlight matched) boosts
// score to 1+sim and pins relevance to 1.0.
//
// NOTE (review-impl MED-2): charStart/charEnd + highlights are Unicode
// CODE-POINT (rune) offsets, NOT UTF-16 units — clients index by code point.
func buildLexicalHit(chapterID uuid.UUID, title, headingCtx *string, sortOrder, blockIndex int, textContent string, sim float64, q, surface string) map[string]any {
	hl := computeHighlight(textContent, q, searchSnippetWindow)
	score := sim
	relevance := sim // E5: calibrated 0–1 relevance (exact match ⇒ 1.0)
	highlights := make([][]int, 0, 1)
	if hl.Matched {
		score = 1 + sim // exact-substring boost (mirrors the ILIKE-first ORDER BY)
		relevance = 1.0
		highlights = append(highlights, []int{hl.HLStart, hl.HLEnd})
	}
	return map[string]any{
		"chapterId":    chapterID,
		"chapterTitle": title,
		"sortOrder":    sortOrder,
		"surface":      surface, // P3-B: "draft" (chapter_blocks) or "canon" (published rev)
		"matchType":    "lexical",
		"score":        score,
		"relevance":    relevance,
		"snippet":      hl.Snippet,
		"highlights":   highlights,
		"location": map[string]any{
			"blockIndex":     blockIndex,
			"headingContext": headingCtx,
			"charStart":      hl.BlockStart,
			"charEnd":        hl.BlockEnd,
		},
	}
}

// runLexicalSearch is the shared lexical-search core (no auth/ownership — the
// callers gate that). `surface` (P3-B) selects the text searched: "draft" (live
// chapter_blocks, default), "canon" (published-revision text), or "all" (both,
// merged by score). `granularity` applies to the draft leg (chapter-best vs
// every-block). matchType="lexical" by construction.
func (s *Server) runLexicalSearch(ctx context.Context, bookID uuid.UUID, q string, limit int, granularity, surface string) ([]map[string]any, error) {
	draftSQL := lexicalSearchSQL // "block": every matching block (exhaustive mining)
	if granularity == "chapter" {
		draftSQL = lexicalSearchChapterSQL // best block per chapter (navigate)
	}
	switch surface {
	case "canon":
		return s.runLexicalSQL(ctx, lexicalSearchCanonSQL, bookID, q, limit, "canon")
	case "all":
		draft, err := s.runLexicalSQL(ctx, draftSQL, bookID, q, limit, "draft")
		if err != nil {
			return nil, err
		}
		canon, err := s.runLexicalSQL(ctx, lexicalSearchCanonSQL, bookID, q, limit, "canon")
		if err != nil {
			return nil, err
		}
		merged := append(draft, canon...)
		sort.SliceStable(merged, func(i, j int) bool {
			return merged[i]["score"].(float64) > merged[j]["score"].(float64)
		})
		if len(merged) > limit {
			merged = merged[:limit]
		}
		return merged, nil
	default: // "draft"
		return s.runLexicalSQL(ctx, draftSQL, bookID, q, limit, "draft")
	}
}

// runLexicalSQL runs one lexical SQL ($1 book_id, $2 raw q, $3 escaped pattern,
// $4 limit) and maps each row → a hit with the given surface label.
func (s *Server) runLexicalSQL(ctx context.Context, sql string, bookID uuid.UUID, q string, limit int, surface string) ([]map[string]any, error) {
	rows, err := s.pool.Query(ctx, sql, bookID, q, escapeLikePattern(q), limit)
	if err != nil {
		return nil, err
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
		results = append(results, buildLexicalHit(chapterID, title, headingCtx, sortOrder, blockIndex, textContent, sim, q, surface))
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return results, nil
}
