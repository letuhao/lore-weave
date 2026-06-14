package api

import (
	"context"
	"net/http"

	"github.com/google/uuid"
)

// C13 — glossary pinning auto-suggestion data. The build wizard's Step-2
// auto-pin banner needs, per entity, how widely + how sparsely it appears so it
// can suggest pinning the "sparse-but-long-reaching" ones (a god in ch1 & ch5000
// that the LLM would otherwise drop in every chapter between). The mention span
// + coverage live in chapter_entity_links; list_entities does NOT expose them.
//
//	GET /internal/books/{book_id}/entities/stats
//	→ { "items": [entityStat], "chapter_count": <int> }
type entityStat struct {
	EntityID          string `json:"entity_id"`
	Name              string `json:"name"`
	Kind              string `json:"kind"`
	MentionCount      int    `json:"mention_count"`
	FirstChapterIndex *int   `json:"first_chapter_index"`
	LastChapterIndex  *int   `json:"last_chapter_index"`
	// CoveragePct = distinct linked chapters / total book chapters, in [0,1].
	// 0 when the book has no chapters (avoids a divide-by-zero).
	CoveragePct float64 `json:"coverage_pct"`
}

type entityStatsResponse struct {
	Items        []entityStat `json:"items"`
	ChapterCount int          `json:"chapter_count"`
}

// statRow is the raw per-entity aggregate straight off the GROUP-BY, before the
// coverage_pct (which needs the book's total chapter count) is computed. Split
// out so computeEntityStats can be unit-tested without a DB or book-service.
type statRow struct {
	EntityID          string
	Name              string
	Kind              string
	MentionCount      int
	DistinctChapters  int
	FirstChapterIndex *int
	LastChapterIndex  *int
}

// computeEntityStats folds the raw GROUP-BY rows + the book's total chapter
// count into the response shape, computing coverage_pct = distinct linked
// chapters / chapter_count (0 when chapter_count <= 0). Pure — no DB, no I/O.
func computeEntityStats(rows []statRow, chapterCount int) []entityStat {
	out := make([]entityStat, 0, len(rows))
	for _, r := range rows {
		cov := 0.0
		if chapterCount > 0 {
			cov = float64(r.DistinctChapters) / float64(chapterCount)
		}
		out = append(out, entityStat{
			EntityID:          r.EntityID,
			Name:              r.Name,
			Kind:              r.Kind,
			MentionCount:      r.MentionCount,
			FirstChapterIndex: r.FirstChapterIndex,
			LastChapterIndex:  r.LastChapterIndex,
			CoveragePct:       cov,
		})
	}
	return out
}

// queryEntityStats runs the bounded GROUP-BY over chapter_entity_links joined to
// the (alive) glossary entities + their kind. One row per entity that has at
// least one chapter link. mention_count = total links; distinct_chapters =
// distinct chapter ids; first/last_chapter_index = MIN/MAX chapter_index (NULL
// when no link carries an index). Book-scoped (WHERE e.book_id) so the scan is
// bounded to one book.
func (s *Server) queryEntityStats(ctx context.Context, bookID uuid.UUID) ([]statRow, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT e.entity_id,
		       COALESCE(e.cached_name, '')              AS name,
		       ek.code                                  AS kind,
		       COUNT(cel.link_id)                       AS mention_count,
		       COUNT(DISTINCT cel.chapter_id)           AS distinct_chapters,
		       MIN(cel.chapter_index)                   AS first_chapter_index,
		       MAX(cel.chapter_index)                   AS last_chapter_index
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id
		WHERE e.book_id = $1
		  AND e.deleted_at IS NULL
		GROUP BY e.entity_id, e.cached_name, ek.code
		ORDER BY mention_count DESC, e.entity_id`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := []statRow{}
	for rows.Next() {
		var r statRow
		if err := rows.Scan(
			&r.EntityID, &r.Name, &r.Kind, &r.MentionCount,
			&r.DistinctChapters, &r.FirstChapterIndex, &r.LastChapterIndex,
		); err != nil {
			return nil, err
		}
		result = append(result, r)
	}
	return result, rows.Err()
}

// internalEntityStats serves the per-entity mention-span + coverage aggregate
// for a book, used by the C13 build-wizard auto-pin suggestion banner. The
// total chapter count (the coverage_pct denominator) comes from book-service;
// if book-service is unavailable, we fall back to `max(last_chapter_index)+1`
// derived from the links themselves. That under-estimates the denominator, which
// OVER-estimates coverage_pct — and since the auto-pin heuristic only suggests
// LOW-coverage (sparse) entities, over-stating coverage makes it strictly MORE
// conservative (suggests fewer) on the degraded path — never a spurious pin.
// Bounded, book-scoped GROUP-BY.
//
//	GET /internal/books/{book_id}/entities/stats
func (s *Server) internalEntityStats(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}

	rows, err := s.queryEntityStats(r.Context(), bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "stats query failed")
		return
	}

	// Total chapter count for coverage_pct. Prefer book-service (authoritative);
	// degrade to a link-derived denominator on outage so the endpoint never 503s
	// just for a coverage number.
	chapterCount := 0
	if chapters, status := s.fetchBookChapters(r.Context(), bookID); status == http.StatusOK {
		chapterCount = len(chapters)
	} else {
		chapterCount = maxChapterDenominator(rows)
	}

	writeJSON(w, http.StatusOK, entityStatsResponse{
		Items:        computeEntityStats(rows, chapterCount),
		ChapterCount: chapterCount,
	})
}

// maxChapterDenominator derives a coverage denominator from the links alone —
// the highest last_chapter_index seen + 1 (0-based indices). Used only when
// book-service is unreachable. Returns 0 when no link carries an index.
func maxChapterDenominator(rows []statRow) int {
	maxIdx := -1
	for _, r := range rows {
		if r.LastChapterIndex != nil && *r.LastChapterIndex > maxIdx {
			maxIdx = *r.LastChapterIndex
		}
	}
	if maxIdx < 0 {
		return 0
	}
	return maxIdx + 1
}
