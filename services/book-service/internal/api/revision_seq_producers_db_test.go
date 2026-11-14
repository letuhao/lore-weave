package api

// Codex review on PR #325 (P1): the #287 change made `seq DESC` the primary
// sort key for chapter revisions, but only 6 of the 18 revision INSERTs in
// this package assigned `seq` — every other producer (MCP publish, diary
// amend, kg index, MCP/REST restore snapshots, the three import writers, the
// two assistant-seed creates) left rows at the DEFAULT 0, so a freshly
// written revision sorted BEHIND older positive-sequence rows and Revision
// Compare picked a stale pair as its "newest two".
//
// This test drives every producer through its real handler and asserts the
// counter invariant the #287 design promises: every revision carries a
// strictly increasing seq starting at 1 with no gaps, and
// chapters.revision_seq sits at the tail. It FAILS on the pre-fix code
// (seq=0 rows from the unconverted producers) and passes once every INSERT
// allocates from the counter.
//
// The three import writers (parse.go / import.go / epub_import_finalize.go)
// create brand-new chapters, so they are covered by the static guard in
// revision_write_guards_test.go (which scans every production INSERT) plus
// the MCP create/bulk-create paths below, which share their SQL shape.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// assertRevisionSeqs pins the #287 counter invariant for one chapter: the
// revision seqs are exactly 1..want in write order (no 0s, no gaps), and the
// chapters.revision_seq counter sits at the tail.
func assertRevisionSeqs(t *testing.T, pool *pgxpool.Pool, chID uuid.UUID, want int) {
	t.Helper()
	ctx := context.Background()
	rows, err := pool.Query(ctx,
		`SELECT seq FROM chapter_revisions WHERE chapter_id=$1 ORDER BY seq ASC`, chID)
	if err != nil {
		t.Fatalf("query seqs: %v", err)
	}
	defer rows.Close()
	var seqs []int64
	for rows.Next() {
		var s int64
		if err := rows.Scan(&s); err != nil {
			t.Fatalf("scan seq: %v", err)
		}
		seqs = append(seqs, s)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows: %v", err)
	}
	if len(seqs) != want {
		t.Fatalf("chapter %s: got %d revisions (seqs %v), want %d", chID, len(seqs), seqs, want)
	}
	for i, s := range seqs {
		if s != int64(i+1) {
			t.Fatalf("chapter %s: seqs %v — want gap-free 1..%d (a 0 here is an unconverted producer)", chID, seqs, want)
		}
	}
	var counter int64
	if err := pool.QueryRow(ctx, `SELECT revision_seq FROM chapters WHERE id=$1`, chID).Scan(&counter); err != nil {
		t.Fatalf("read chapters.revision_seq: %v", err)
	}
	if counter != int64(want) {
		t.Fatalf("chapter %s: chapters.revision_seq = %d, want %d (counter must sit at the tail)", chID, counter, want)
	}
}

func postJSONViaRouter(t *testing.T, s *Server, owner uuid.UUID, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader("{}"))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestRevisionSeqEveryProducerAllocates_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	// The test server's cfg carries QuotaBytesDefault=0; seed headroom so the
	// create paths reach the revision INSERT instead of tripping the quota gate.
	if _, err := pool.Exec(ctx, `
INSERT INTO user_storage_quota(owner_user_id, used_bytes, quota_bytes) VALUES($1, 0, $2)
ON CONFLICT(owner_user_id) DO UPDATE SET quota_bytes = EXCLUDED.quota_bytes`,
		owner, int64(1<<30)); err != nil {
		t.Fatalf("seed quota: %v", err)
	}
	tctx := identityCtxForTest(t, owner)

	// 1. REST patchDraft — already converted by #287 (control).
	revisionClockTestServerCalls(t, s, bookID, chID, owner, "save one")
	// 2. MCP save_draft — snapshot + new body in one tx (already converted).
	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), Body: draftProse,
	}); err != nil {
		t.Fatalf("mcp save_draft: %v", err)
	}
	// 3. MCP publish — Codex-named producer (mcp_actions.go).
	if _, _, err := s.mcpPublishChapter(ctx, owner, bookID, chID); err != nil {
		t.Fatalf("mcp publish: %v", err)
	}
	// 4. REST publish — publishChapter (already converted).
	rr := postJSONViaRouter(t, s, owner,
		"/v1/books/"+bookID.String()+"/chapters/"+chID.String()+"/publish")
	if rr.Code != http.StatusOK {
		t.Fatalf("REST publish: want 200, got %d body=%s", rr.Code, rr.Body.String())
	}
	// 5. KG index on a CHANGED draft — Codex-named producer (kg_index.go).
	// The draft body must differ, or indexChapter reuses the existing revision.
	if _, err := pool.Exec(ctx,
		`UPDATE chapter_drafts SET body=$2, draft_version=draft_version+1 WHERE chapter_id=$1`,
		chID, kgBody("version two — materially different")); err != nil {
		t.Fatalf("edit draft: %v", err)
	}
	if _, err := s.indexChapter(ctx, owner, bookID, chID); err != nil {
		t.Fatalf("kg index: %v", err)
	}
	// 6. MCP restore — snapshot the current draft, then restore the first revision.
	var firstRev uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT id FROM chapter_revisions WHERE chapter_id=$1 ORDER BY created_at ASC, id ASC LIMIT 1`,
		chID).Scan(&firstRev); err != nil {
		t.Fatalf("first revision: %v", err)
	}
	if _, _, err := s.mcpRestoreRevision(ctx, owner, bookID, chID, firstRev); err != nil {
		t.Fatalf("mcp restore: %v", err)
	}
	// 7. REST restore — snapshot again, restore the (now) first revision.
	var restRev uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT id FROM chapter_revisions WHERE chapter_id=$1 ORDER BY created_at ASC, id ASC LIMIT 1`,
		chID).Scan(&restRev); err != nil {
		t.Fatalf("restore target: %v", err)
	}
	rr = postJSONViaRouter(t, s, owner,
		"/v1/books/"+bookID.String()+"/chapters/"+chID.String()+
			"/revisions/"+restRev.String()+"/restore")
	if rr.Code != http.StatusOK {
		t.Fatalf("REST restore: want 200, got %d body=%s", rr.Code, rr.Body.String())
	}

	// 1 + 2 + 1 + 1 + 1 + 1 + 1 = 8 revisions, seqs 1..8.
	assertRevisionSeqs(t, pool, chID, 8)

	// 8. Diary amend — Codex-named producer (diary_entry_handler.go).
	// A diary entry is its own chapter: create, keep, amend.
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	rr = postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "Minh froze the Q3 budget.",
	}, true)
	dch := uuid.MustParse(entryChapterID(t, rr))
	keepDiaryEntry(t, s, diary, dch, owner)
	ar := amendDiaryEntry(t, s, diary, dch, owner, "Alice froze the Q3 budget.")
	if ar.Code != http.StatusOK {
		t.Fatalf("diary amend: want 200, got %d body=%s", ar.Code, ar.Body.String())
	}
	// Create (seq 1) + amend (seq 2).
	assertRevisionSeqs(t, pool, dch, 2)
}

func TestRevisionSeqCreatePathsAllocate_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	// Quota headroom — see the main test (create paths trip the quota gate first).
	if _, err := pool.Exec(ctx, `
INSERT INTO user_storage_quota(owner_user_id, used_bytes, quota_bytes) VALUES($1, 0, $2)
ON CONFLICT(owner_user_id) DO UPDATE SET quota_bytes = EXCLUDED.quota_bytes`,
		owner, int64(1<<30)); err != nil {
		t.Fatalf("seed quota: %v", err)
	}
	tctx := identityCtxForTest(t, owner)

	// MCP book_chapter_create ("seed from assistant") — first revision must be seq 1.
	_, out, err := s.toolChapterCreate(tctx, nil, chapterCreateIn{
		BookID: bookID.String(), Title: "created one",
		OriginalLanguage: "en", Body: draftProse,
	})
	if err != nil {
		t.Fatalf("mcp create: %v", err)
	}
	assertRevisionSeqs(t, pool, uuid.MustParse(out.ChapterID), 1)

	// MCP bulk create ("bulk seed from assistant") — each chapter's first revision is seq 1.
	_, bout, err := s.toolChapterBulkCreate(tctx, nil, chapterBulkCreateIn{
		BookID: bookID.String(), OriginalLanguage: "en",
		Chapters: []chapterBulkItem{
			{Title: "bulk one", Content: draftProse},
			{Title: "bulk two", Content: draftProse},
		},
	})
	if err != nil {
		t.Fatalf("mcp bulk create: %v", err)
	}
	if len(bout.ChapterIDs) != 2 {
		t.Fatalf("bulk create: got %d chapters, want 2", len(bout.ChapterIDs))
	}
	for _, id := range bout.ChapterIDs {
		assertRevisionSeqs(t, pool, uuid.MustParse(id), 1)
	}
}
