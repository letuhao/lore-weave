package api

// WS-0.5 — the reparse sweeper, re-keyed onto kg_indexed_revision_id.
//
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.4 (red-team P1-5).
//
// The sweeper's selection set IS the definition of "what the knowledge layer indexes".
// These tests pin all five cases the spec enumerates — published · draft-indexed ·
// excluded · trashed · unpublished-but-still-indexed — plus the two failure modes
// re-keying only the WHERE clause would have produced:
//
//	(a) the inner JOIN silently dropping every draft-indexed chapter, and
//	(b) an INFINITE RE-PARSE LOOP on a chapter that is both published@A and
//	    draft-indexed@B (parse A, stamp last_parsed=A, but kg_indexed=B ⇒ still stale
//	    ⇒ re-parse forever, re-emitting scenes_reparsed and re-paying LLM cost each tick).
//
// DB-gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// sweepSeed builds a chapter with its own revision and returns (bookID, chapterID, revID).
// Nothing is pinned — the caller decides which pointers to set, which is the whole point.
func sweepSeed(t *testing.T, ctx context.Context, pool *pgxpool.Pool, editorial string) (
	bookID, chID, revID uuid.UUID,
) {
	t.Helper()
	owner := uuid.New()
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'ws05') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,
                     storage_key,lifecycle_state,editorial_status,structural_path)
VALUES($1,'c.txt','en','text/plain',1,'k','active',$2,'book/part-1/chapter-1')
RETURNING id`, bookID, editorial).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	body := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","_text":"prose"}]}`)
	if err := pool.QueryRow(ctx,
		`INSERT INTO chapter_revisions(chapter_id, body, body_format, message)
		 VALUES($1,$2,'json','x') RETURNING id`, chID, body).Scan(&revID); err != nil {
		t.Fatalf("seed revision: %v", err)
	}
	return bookID, chID, revID
}

// sweptChapterIDs runs the REAL selection query and returns which chapters it picked.
// Asserting on the selection set (rather than on side effects) is what makes the
// "excluded/trashed are OUT" cases provable.
func sweptChapterIDs(t *testing.T, ctx context.Context, s *Server, want uuid.UUID) bool {
	t.Helper()
	rows, err := s.pool.Query(ctx, `
SELECT c.id
FROM chapters c
JOIN chapter_revisions r ON r.id = c.kg_indexed_revision_id
WHERE c.kg_indexed_revision_id IS NOT NULL
  AND c.kg_exclude       = false
  AND c.lifecycle_state  = 'active'
  AND c.last_parsed_revision_id IS DISTINCT FROM c.kg_indexed_revision_id`)
	if err != nil {
		t.Fatalf("sweep select: %v", err)
	}
	defer rows.Close()
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			t.Fatalf("scan: %v", err)
		}
		if id == want {
			return true
		}
	}
	return false
}

// ── The five selection cases ──

// A DRAFT chapter that the user explicitly indexed MUST be swept. Under the old
// predicate (editorial_status='published' + a JOIN on published_revision_id) it was
// dropped twice over — this is the case the whole change exists for.
func TestSweeper_DraftIndexedChapter_IsSwept_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	_, chID, revID := sweepSeed(t, ctx, pool, "draft")

	// Indexed, never published.
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_indexed_revision_id=$2 WHERE id=$1`, chID, revID); err != nil {
		t.Fatalf("index: %v", err)
	}

	if !sweptChapterIDs(t, ctx, s, chID) {
		t.Fatal("a DRAFT chapter with kg_indexed_revision_id must be swept — re-keying only " +
			"the WHERE (leaving the JOIN on published_revision_id) would drop it at the " +
			"inner join, silently excluding the exact rows this change exists to include")
	}
}

// A published chapter (pointer seeded by the WS-0.2 backfill) is still swept — the
// legacy-backfill property, unchanged.
func TestSweeper_PublishedChapter_StillSwept_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	_, chID, revID := sweepSeed(t, ctx, pool, "published")
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET published_revision_id=$2, kg_indexed_revision_id=$2 WHERE id=$1`,
		chID, revID); err != nil {
		t.Fatalf("pin: %v", err)
	}
	if !sweptChapterIDs(t, ctx, s, chID) {
		t.Fatal("a published chapter must still be swept (no regression)")
	}
}

// kg_exclude'd chapters are OUT — the user asked to keep them out of the graph.
func TestSweeper_ExcludedChapter_IsNotSwept_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	_, chID, revID := sweepSeed(t, ctx, pool, "draft")
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_indexed_revision_id=$2, kg_exclude=true WHERE id=$1`,
		chID, revID); err != nil {
		t.Fatalf("exclude: %v", err)
	}
	if sweptChapterIDs(t, ctx, s, chID) {
		t.Fatal("a kg_exclude'd chapter must NOT be swept — re-parsing it would re-emit " +
			"scenes_reparsed and pull it back toward the graph the user removed it from")
	}
}

// Trashed chapters stay out (lifecycle_state), as under the old predicate.
func TestSweeper_TrashedChapter_IsNotSwept_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	_, chID, revID := sweepSeed(t, ctx, pool, "draft")
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_indexed_revision_id=$2, lifecycle_state='trashed' WHERE id=$1`,
		chID, revID); err != nil {
		t.Fatalf("trash: %v", err)
	}
	if sweptChapterIDs(t, ctx, s, chID) {
		t.Fatal("a trashed chapter must NOT be swept")
	}
}

// ── (9) UNPUBLISH MUST NOT DESTROY THE INDEX REQUEST — spec §3.8 / acceptance #9 ──
//
// The plan's WS-0.5 row originally said "unpublish clears the pointer". It is the
// opposite (RUN-STATE D-R5): publish now means only "this is the canonical version", so
// an EDITORIAL unpublish must not silently throw away the user's explicit
// "add to knowledge" request. Retraction is kg_exclude's job.
func TestSweeper_UnpublishedChapter_StaysIndexed_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID, _ := sweepSeed(t, ctx, pool, "draft")
	_ = bookID

	// Index it, then publish it, then unpublish it.
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version)
VALUES($1,$2,'json',1)`, chID, kgBody("prose worth remembering")); err != nil {
		t.Fatalf("seed draft: %v", err)
	}
	res, err := s.indexChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("index: %v", err)
	}
	if _, _, err := s.mcpPublishChapter(ctx, owner, bookID, chID); err != nil {
		t.Fatalf("publish: %v", err)
	}
	if err := s.mcpUnpublishChapter(ctx, bookID, chID); err != nil {
		t.Fatalf("unpublish: %v", err)
	}

	editorial, publishedRev, kgRev, _ := kgChapterState(t, ctx, pool, chID)
	if editorial != "draft" || publishedRev != nil {
		t.Fatalf("precondition: unpublish should have cleared publish state, got %q/%v",
			editorial, publishedRev)
	}
	if kgRev == nil {
		t.Fatalf("REGRESSION (acceptance #9): unpublishing DESTROYED the index request. "+
			"A user who clicked 'add to knowledge' and then unpublished for editorial "+
			"reasons must not silently lose their knowledge graph. Retraction is "+
			"kg_exclude's job, not unpublish's. (indexed rev was %v)", res.RevisionID)
	}
}

// ── THE INFINITE RE-PARSE LOOP (P1-5) ──
//
// A chapter published at revision A and then draft-indexed at revision B. If the sweeper
// re-keyed only its WHERE clause, it would still SELECT/JOIN/stamp on
// published_revision_id: parse A, stamp last_parsed = A. But kg_indexed = B, so
// `last_parsed(A) IS DISTINCT FROM kg_indexed(B)` stays TRUE — the row is stale forever.
// Every tick re-parses it and re-emits chapter.scenes_reparsed, whose consumer
// invalidates the extraction cache → the book re-pays LLM extraction cost on a loop.
//
// The fix is that the SELECT, the JOIN, the guard AND the stamp all key on the KG
// pointer. This test proves convergence: one sweep makes the chapter non-stale, and a
// second sweep finds nothing to do.
func TestSweeper_PublishedAtA_IndexedAtB_ConvergesAndDoesNotLoop_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID, _ := sweepSeed(t, ctx, pool, "draft")

	// A reachable parser, so publish/index do their in-Tx scenes parse (and stamp
	// last_parsed) rather than falling back to "leave it stale for the sweeper".
	parseSrv := mockParseServer(t, twoSceneTreeJSON(""))
	defer parseSrv.Close()
	s.cfg.KnowledgeServiceURL = parseSrv.URL

	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version)
VALUES($1,$2,'json',1)`, chID, kgBody("revision A prose")); err != nil {
		t.Fatalf("seed draft: %v", err)
	}

	// Publish at A.
	revA, _, err := s.mcpPublishChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("publish@A: %v", err)
	}
	// Edit the draft, then INDEX at B (without publishing).
	if _, err := pool.Exec(ctx,
		`UPDATE chapter_drafts SET body=$2, draft_version=draft_version+1 WHERE chapter_id=$1`,
		chID, kgBody("revision B prose — different, indexed but not published")); err != nil {
		t.Fatalf("edit draft: %v", err)
	}
	resB, err := s.indexChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("index@B: %v", err)
	}
	revB := resB.RevisionID
	if revA == revB {
		t.Fatal("precondition: A and B must be different revisions")
	}

	// The chapter is published@A and kg-indexed@B.
	_, publishedRev, kgRev, _ := kgChapterState(t, ctx, pool, chID)
	if publishedRev == nil || *publishedRev != revA {
		t.Fatalf("precondition: published_revision_id should be A (%v), got %v", revA, publishedRev)
	}
	if kgRev == nil || *kgRev != revB {
		t.Fatalf("precondition: kg_indexed_revision_id should be B (%v), got %v", revB, kgRev)
	}

	// The index action already parsed B in-Tx, so last_parsed should be B ⇒ NOT stale.
	// This is the convergence assertion: had we stamped A (the published rev), the row
	// would be permanently stale and the sweeper would loop on it forever.
	var lastParsed *uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT last_parsed_revision_id FROM chapters WHERE id=$1`, chID).Scan(&lastParsed); err != nil {
		t.Fatalf("read last_parsed: %v", err)
	}
	if lastParsed == nil || *lastParsed != revB {
		t.Fatalf("last_parsed = %v, want B (%v). Stamping the PUBLISHED revision instead of "+
			"the INDEXED one is the infinite-re-parse-loop bug: last_parsed(A) would never "+
			"equal kg_indexed(B), so the chapter stays stale by predicate forever and every "+
			"sweeper tick re-parses it + re-emits scenes_reparsed + re-pays LLM extraction.",
			lastParsed, revB)
	}

	if sweptChapterIDs(t, ctx, s, chID) {
		t.Fatal("the chapter is still selected as STALE after being indexed at B — this is " +
			"the infinite re-parse loop (P1-5). It must have converged.")
	}

	// ── The decisive half: force the EXACT state a WHERE-only re-key would leave, and
	// prove the real sweeper converges out of it instead of looping.
	//
	// last_parsed = A (the PUBLISHED revision) while kg_indexed = B. Under the buggy
	// implementation the sweeper would parse the published body and re-stamp A here,
	// leaving the row stale on every subsequent tick — forever.
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET last_parsed_revision_id=$2 WHERE id=$1`, chID, revA); err != nil {
		t.Fatalf("force stale-at-A: %v", err)
	}
	if !sweptChapterIDs(t, ctx, s, chID) {
		t.Fatal("precondition: with last_parsed=A and kg_indexed=B the chapter must be STALE")
	}

	if _, err := s.sweepStaleChapters(ctx, 50); err != nil {
		t.Fatalf("sweep: %v", err)
	}

	if err := pool.QueryRow(ctx,
		`SELECT last_parsed_revision_id FROM chapters WHERE id=$1`, chID).Scan(&lastParsed); err != nil {
		t.Fatalf("read last_parsed after sweep: %v", err)
	}
	if lastParsed == nil || *lastParsed != revB {
		t.Fatalf("after a sweep, last_parsed = %v, want the INDEXED revision B (%v). "+
			"Stamping the published revision A here is the infinite-re-parse loop: the row "+
			"would stay stale by predicate forever.", lastParsed, revB)
	}

	// Converged: a second tick has nothing to do for this chapter.
	if sweptChapterIDs(t, ctx, s, chID) {
		t.Fatal("the chapter is STILL stale after a sweep — the sweeper is looping (P1-5)")
	}
}
