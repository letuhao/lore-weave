package api

// C13 — tests for GET /internal/books/{book_id}/entities/stats (auto-pin
// suggestion data). The pure helpers always run; the GROUP-BY shape test
// requires GLOSSARY_TEST_DB_URL and skips otherwise (openTestDB).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func intp(v int) *int { return &v }

// ── pure helpers (no DB) ────────────────────────────────────────────

func TestComputeEntityStats_CoveragePct(t *testing.T) {
	rows := []statRow{
		{EntityID: "e1", Name: "PanGu", Kind: "deity", MentionCount: 4,
			DistinctChapters: 2, FirstChapterIndex: intp(1), LastChapterIndex: intp(50)},
		{EntityID: "e2", Name: "Kai", Kind: "character", MentionCount: 30,
			DistinctChapters: 20, FirstChapterIndex: intp(1), LastChapterIndex: intp(20)},
	}
	out := computeEntityStats(rows, 100)
	if len(out) != 2 {
		t.Fatalf("want 2, got %d", len(out))
	}
	// PanGu: 2/100 = 0.02 (sparse) with span 1..50 (long-reaching) → an auto-pin
	// candidate (coverage ≤ 0.15 AND span ≥ 0.5×100).
	if out[0].CoveragePct != 0.02 {
		t.Errorf("PanGu coverage: want 0.02, got %v", out[0].CoveragePct)
	}
	if *out[0].FirstChapterIndex != 1 || *out[0].LastChapterIndex != 50 {
		t.Errorf("PanGu span: want 1..50, got %v..%v",
			*out[0].FirstChapterIndex, *out[0].LastChapterIndex)
	}
	if out[0].MentionCount != 4 {
		t.Errorf("PanGu mention_count: want 4, got %d", out[0].MentionCount)
	}
	// Kai: 20/100 = 0.20 (NOT sparse) → not a candidate.
	if out[1].CoveragePct != 0.20 {
		t.Errorf("Kai coverage: want 0.20, got %v", out[1].CoveragePct)
	}
}

func TestComputeEntityStats_ZeroChapterCountNoDivByZero(t *testing.T) {
	rows := []statRow{{EntityID: "e1", Name: "X", Kind: "k", MentionCount: 1, DistinctChapters: 1}}
	out := computeEntityStats(rows, 0)
	if out[0].CoveragePct != 0 {
		t.Errorf("zero chapter_count → coverage must be 0, got %v", out[0].CoveragePct)
	}
}

func TestMaxChapterDenominator(t *testing.T) {
	// highest last_chapter_index + 1 (0-based).
	rows := []statRow{
		{LastChapterIndex: intp(4)},
		{LastChapterIndex: intp(49)},
		{LastChapterIndex: nil},
	}
	if got := maxChapterDenominator(rows); got != 50 {
		t.Errorf("want 50, got %d", got)
	}
	// no indexed links → 0.
	if got := maxChapterDenominator([]statRow{{LastChapterIndex: nil}}); got != 0 {
		t.Errorf("want 0, got %d", got)
	}
}

// ── route guards (no DB) ────────────────────────────────────────────

func TestEntityStats_BadUUIDReturns400(t *testing.T) {
	srv, token := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/not-a-uuid/entities/stats", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad uuid: want 400, got %d", w.Code)
	}
}

func TestEntityStats_RequiresInternalToken(t *testing.T) {
	srv, _ := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/entities/stats", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

// ── GROUP-BY shape on a fixture book (needs DB) ─────────────────────

func TestEntityStats_GroupByOnFixtureBook(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bookID := "00000000-0000-0000-0002-0000000c1301"
	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttrID)

	seed := func(name string) string {
		var eid string
		pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
			 VALUES($1,$2,'active','{}') RETURNING entity_id`,
			bookID, kindID).Scan(&eid)
		pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
			 VALUES($1,$2,'zh',$3)`, eid, nameAttrID, name)
		return eid
	}
	link := func(eid string, idx int) {
		pool.Exec(ctx,
			`INSERT INTO chapter_entity_links(entity_id,chapter_id,chapter_title,chapter_index,relevance)
			 VALUES($1,$2,'Ch',$3,'appears')`, eid, uuid.New(), idx)
	}

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM chapter_entity_links WHERE entity_id IN
			(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bookID)
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN
			(SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	// PanGu: sparse-but-long-reaching — 2 links at ch1 & ch50.
	panguID := seed("盘古")
	link(panguID, 1)
	link(panguID, 50)
	// Kai: dense — 3 links in ch1..ch3.
	kaiID := seed("凯")
	link(kaiID, 1)
	link(kaiID, 2)
	link(kaiID, 3)

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID+"/entities/stats", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp entityStatsResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}

	byID := map[string]entityStat{}
	for _, it := range resp.Items {
		byID[it.EntityID] = it
	}
	pg, ok := byID[panguID]
	if !ok {
		t.Fatalf("PanGu missing from stats; items=%d", len(resp.Items))
	}
	if pg.MentionCount != 2 {
		t.Errorf("PanGu mention_count: want 2, got %d", pg.MentionCount)
	}
	if pg.FirstChapterIndex == nil || *pg.FirstChapterIndex != 1 {
		t.Errorf("PanGu first_chapter_index: want 1, got %v", pg.FirstChapterIndex)
	}
	if pg.LastChapterIndex == nil || *pg.LastChapterIndex != 50 {
		t.Errorf("PanGu last_chapter_index: want 50, got %v", pg.LastChapterIndex)
	}
	if pg.Name != "盘古" {
		t.Errorf("PanGu name: want 盘古, got %q", pg.Name)
	}
	if pg.Kind != "character" {
		t.Errorf("PanGu kind: want character, got %q", pg.Kind)
	}

	kai := byID[kaiID]
	if kai.MentionCount != 3 {
		t.Errorf("Kai mention_count: want 3, got %d", kai.MentionCount)
	}
	if kai.LastChapterIndex == nil || *kai.LastChapterIndex != 3 {
		t.Errorf("Kai last_chapter_index: want 3, got %v", kai.LastChapterIndex)
	}

	// book-service unavailable in tests → denominator falls back to
	// max(last_chapter_index)+1 = 51. PanGu coverage = 2/51; Kai = 3/51.
	if resp.ChapterCount != 51 {
		t.Errorf("chapter_count fallback: want 51, got %d", resp.ChapterCount)
	}
	if pg.CoveragePct >= 0.15 {
		t.Errorf("PanGu should read sparse (≤0.15), got %v", pg.CoveragePct)
	}
}
