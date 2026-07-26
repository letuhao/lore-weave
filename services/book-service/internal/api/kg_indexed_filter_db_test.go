package api

// WS-0.6 — the `kg_indexed` filter on GET /internal/books/{book_id}/chapters.
//
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.5 (red-team P0-2).
//
// This endpoint is the ONLY chapter-enumeration surface the knowledge-graph readers have
// (worker-ai's whole-book rebuild, the passage backfill/ingester, the extraction cost
// estimate, campaign chapter selection). Until now it could express exactly one canon
// question — `?editorial_status=published`. So a user who indexes 50 DRAFT chapters and
// then hits "Rebuild knowledge graph" gets ZERO of them enumerated: the job reports
// success having extracted nothing, and the cost estimate says "0 chapters". Their
// explicit act is silently undone by an unrelated button.
//
// The filter is ADDITIVE. editorial_status keeps meaning editorial status — it has
// legitimate non-KG users (translation word counts, lore-enrichment, the chapter browser,
// knowledge's draft lexical search). Re-defining it would break them.
//
// DB-gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// kgSeedChapter inserts a chapter with explicit KG/publish state and returns its id.
func kgSeedChapter(
	t *testing.T, ctx context.Context, pool *pgxpool.Pool, bookID uuid.UUID, sortOrder int,
	editorial string, published, kgIndexed *uuid.UUID, kgExclude bool,
) uuid.UUID {
	t.Helper()
	var chID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,
                     storage_key,lifecycle_state,editorial_status,
                     published_revision_id,kg_indexed_revision_id,kg_exclude)
VALUES($1,'c.txt','en','text/plain',$2,$3,'active',$4,$5,$6,$7) RETURNING id`,
		bookID, sortOrder, "k/"+uuid.NewString(), editorial, published, kgIndexed, kgExclude,
	).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	return chID
}

func kgSeedRevision(t *testing.T, ctx context.Context, pool *pgxpool.Pool, chID uuid.UUID) uuid.UUID {
	t.Helper()
	var rev uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO chapter_revisions(chapter_id, body, body_format) VALUES($1,$2::jsonb,'json') RETURNING id`,
		chID, `{"type":"doc","content":[]}`).Scan(&rev); err != nil {
		t.Fatalf("seed revision: %v", err)
	}
	return rev
}

// listInternalChapters drives the REAL route and returns (items, total).
func listInternalChapters(t *testing.T, s *Server, bookID uuid.UUID, query string) ([]map[string]any, int) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID.String()+"/chapters?limit=100"+query, nil)
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("list chapters%s = %d, body=%s", query, rr.Code, rr.Body.String())
	}
	var out struct {
		Items []map[string]any `json:"items"`
		Total int              `json:"total"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return out.Items, out.Total
}

func idSet(items []map[string]any) map[string]bool {
	s := map[string]bool{}
	for _, it := range items {
		if v, ok := it["chapter_id"].(string); ok {
			s[v] = true
		}
	}
	return s
}

// THE HEADLINE (P0-2): a rebuild must enumerate the DRAFT chapters the user indexed.
func TestInternalChapters_KGIndexedFilter_EnumeratesDraftIndexedChapters_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'ws06') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	// 1. a DRAFT chapter the user explicitly indexed  → MUST be enumerated
	draftIndexed := kgSeedChapter(t, ctx, pool, bookID, 1, "draft", nil, nil, false)
	rev1 := kgSeedRevision(t, ctx, pool, draftIndexed)
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_indexed_revision_id=$2 WHERE id=$1`, draftIndexed, rev1); err != nil {
		t.Fatalf("index draft: %v", err)
	}

	// 2. a published chapter (pointer seeded by the WS-0.2 backfill) → MUST be enumerated
	pub := kgSeedChapter(t, ctx, pool, bookID, 2, "published", nil, nil, false)
	rev2 := kgSeedRevision(t, ctx, pool, pub)
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET published_revision_id=$2, kg_indexed_revision_id=$2 WHERE id=$1`,
		pub, rev2); err != nil {
		t.Fatalf("publish: %v", err)
	}

	// 3. a plain draft, never indexed → must NOT be enumerated
	unindexed := kgSeedChapter(t, ctx, pool, bookID, 3, "draft", nil, nil, false)

	// 4. an INDEXED-then-EXCLUDED chapter → must NOT be enumerated (the user retracted it)
	excluded := kgSeedChapter(t, ctx, pool, bookID, 4, "draft", nil, nil, false)
	rev4 := kgSeedRevision(t, ctx, pool, excluded)
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_indexed_revision_id=$2, kg_exclude=true WHERE id=$1`,
		excluded, rev4); err != nil {
		t.Fatalf("exclude: %v", err)
	}

	items, total := listInternalChapters(t, s, bookID, "&kg_indexed=true")
	got := idSet(items)

	if !got[draftIndexed.String()] {
		t.Fatal("THE BUG (P0-2): a DRAFT chapter the user explicitly added to their knowledge " +
			"graph was NOT enumerated. A rebuild would report success having extracted " +
			"nothing, and the cost estimate would say '0 chapters'.")
	}
	if !got[pub.String()] {
		t.Fatal("a published chapter must still be enumerated (regression)")
	}
	if got[unindexed.String()] {
		t.Fatal("a chapter that was never indexed must NOT be enumerated — extracting it " +
			"would burn LLM spend on prose the user never added to their graph")
	}
	if got[excluded.String()] {
		t.Fatal("a kg_exclude'd chapter must NOT be enumerated — the user explicitly " +
			"retracted it from their knowledge graph")
	}

	// total must match the items, or the cost preview lies about what the job will do.
	if total != len(items) {
		t.Fatalf("total=%d but len(items)=%d — COUNT and LIST must apply the same filter, "+
			"else the cost estimate and the enumeration disagree", total, len(items))
	}
	if total != 2 {
		t.Fatalf("total=%d, want 2 (the draft-indexed + the published)", total)
	}
}

// The projection must carry the pointer, or a re-keyed reader can filter but cannot PIN
// the revision — and worker-ai falls back to LIVE DRAFT text when it has no revision_id.
func TestInternalChapters_ProjectionCarriesKGPointerAndExclude_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'ws06p') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	ch := kgSeedChapter(t, ctx, pool, bookID, 1, "draft", nil, nil, false)
	rev := kgSeedRevision(t, ctx, pool, ch)
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_indexed_revision_id=$2 WHERE id=$1`, ch, rev); err != nil {
		t.Fatalf("index: %v", err)
	}

	items, _ := listInternalChapters(t, s, bookID, "&kg_indexed=true")
	if len(items) != 1 {
		t.Fatalf("want 1 item, got %d", len(items))
	}
	it := items[0]

	got, ok := it["kg_indexed_revision_id"].(string)
	if !ok || got != rev.String() {
		t.Fatalf("kg_indexed_revision_id = %v, want %s. Without it a reader can filter on "+
			"the KG gate but cannot PIN the revision, and worker-ai's extractor falls back "+
			"to the LIVE DRAFT text — silently extracting unreviewed prose.", it["kg_indexed_revision_id"], rev)
	}
	if _, ok := it["kg_exclude"]; !ok {
		t.Fatal("kg_exclude must be in the projection so enumerators can see the opt-out")
	}
}

// ADDITIVE: editorial_status must keep its old meaning (translation word counts,
// lore-enrichment, the chapter browser, knowledge's draft lexical search all rely on it).
func TestInternalChapters_EditorialStatusFilterUnchanged_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'ws06e') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	// A draft chapter that IS indexed — visible to kg_indexed=true, but still a DRAFT.
	draftIndexed := kgSeedChapter(t, ctx, pool, bookID, 1, "draft", nil, nil, false)
	rev := kgSeedRevision(t, ctx, pool, draftIndexed)
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_indexed_revision_id=$2 WHERE id=$1`, draftIndexed, rev); err != nil {
		t.Fatalf("index: %v", err)
	}

	pubItems, _ := listInternalChapters(t, s, bookID, "&editorial_status=published")
	if idSet(pubItems)[draftIndexed.String()] {
		t.Fatal("indexing a draft must NOT make it show up under editorial_status=published — " +
			"the kg_indexed filter is ADDITIVE; publish semantics are unchanged")
	}

	draftItems, _ := listInternalChapters(t, s, bookID, "&editorial_status=draft")
	if !idSet(draftItems)[draftIndexed.String()] {
		t.Fatal("an indexed draft is still a draft under editorial_status=draft")
	}
}

// A typo'd value must 400, never silently fall through to "all chapters" — that would
// over-extract kg_exclude'd prose the user asked us to forget.
func TestInternalChapters_InvalidKGIndexedParamIs400_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'ws06v') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+bookID.String()+"/chapters?kg_indexed=yes", nil)
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("kg_indexed=yes should 400 (closed set), got %d — silently ignoring it "+
			"would enumerate ALL chapters including kg_exclude'd ones", rr.Code)
	}
}
