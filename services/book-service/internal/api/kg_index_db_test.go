package api

// WS-0.4 — the "add to knowledge" (index) action, against real Postgres.
//
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.3.
// Acceptance §5: (1) draft never published -> indexed; (2) autosave does NOT extract;
// (3) published flow unchanged; (8) kg_exclude retracts; (10) re-index unchanged -> no spend.
//
// DB-gated on BOOK_TEST_DATABASE_URL like the other *_db_test.go files here.
//
// These assert the PRODUCER half (book-service): the pointer moves, the right event is
// emitted, and — the load-bearing negative — `chapter.saved` (autosave) emits NO index
// event. The CONSUMER half (knowledge actually extracting) is WS-0.8's live smoke.

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func kgBody(text string) json.RawMessage {
	b, _ := json.Marshal(map[string]any{
		"type": "doc",
		"content": []any{
			map[string]any{
				"type":    "paragraph",
				"content": []any{map[string]any{"type": "text", "text": text}},
			},
		},
	})
	return b
}

// outboxEventsFor returns the event_types emitted for a chapter, in order.
func outboxEventsFor(t *testing.T, ctx context.Context, pool *pgxpool.Pool, chID uuid.UUID) []string {
	t.Helper()
	rows, err := pool.Query(ctx,
		`SELECT event_type FROM outbox_events WHERE aggregate_id=$1 ORDER BY created_at, id`, chID)
	if err != nil {
		t.Fatalf("read outbox: %v", err)
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var et string
		if err := rows.Scan(&et); err != nil {
			t.Fatalf("scan outbox: %v", err)
		}
		out = append(out, et)
	}
	return out
}

func countEvent(events []string, want string) int {
	n := 0
	for _, e := range events {
		if e == want {
			n++
		}
	}
	return n
}

func kgChapterState(t *testing.T, ctx context.Context, pool *pgxpool.Pool, chID uuid.UUID) (
	editorial string, publishedRev, kgRev *uuid.UUID, kgExclude bool,
) {
	t.Helper()
	if err := pool.QueryRow(ctx, `
SELECT editorial_status, published_revision_id, kg_indexed_revision_id, kg_exclude
FROM chapters WHERE id=$1`, chID).Scan(&editorial, &publishedRev, &kgRev, &kgExclude); err != nil {
		t.Fatalf("read chapter state: %v", err)
	}
	return
}

// ── (1) THE POINT: a draft that is NEVER published gets into the knowledge graph ──

func TestIndex_DraftNeverPublished_IsIndexed_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("Alice met Bob at the docks."))

	res, err := s.indexChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("indexChapter: %v", err)
	}

	editorial, publishedRev, kgRev, _ := kgChapterState(t, ctx, pool, chID)

	// The whole point of the change: indexed WITHOUT being published.
	if editorial != "draft" {
		t.Fatalf("editorial_status = %q, want draft — indexing must NOT publish", editorial)
	}
	if publishedRev != nil {
		t.Fatalf("published_revision_id = %v, want NULL — indexing must NOT publish", *publishedRev)
	}
	if kgRev == nil {
		t.Fatal("kg_indexed_revision_id is NULL — the draft was not indexed (the whole feature)")
	}
	if *kgRev != res.RevisionID {
		t.Fatalf("kg pointer %v != returned revision %v", *kgRev, res.RevisionID)
	}

	// The NEW event, and NOT chapter.published.
	events := outboxEventsFor(t, ctx, pool, chID)
	if countEvent(events, "chapter.kg_indexed") != 1 {
		t.Fatalf("want exactly 1 chapter.kg_indexed, got events=%v", events)
	}
	if countEvent(events, "chapter.published") != 0 {
		t.Fatalf("indexing must NOT emit chapter.published, got events=%v", events)
	}
}

// ── (2) AUTOSAVE MUST NOT INDEX — the CM3b/CM3c guarantee ──
//
// This is the negative that protects the user's LLM budget and the "unreviewed draft
// prose never canonizes" invariant. Saving a draft must emit chapter.saved and NOTHING
// else; it must not move the KG pointer.

func TestAutosave_DoesNotIndex_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("first draft"))
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	// Drive the REAL autosave path through the router: PATCH /draft is what the editor
	// calls on every keystroke-debounce. (Not the MCP save tool — THIS is the one that
	// fires hundreds of times a day and would bankrupt the user if it indexed.)
	payload, _ := json.Marshal(map[string]any{"body": kgBody("second draft — still unreviewed")})
	req := httptest.NewRequest(http.MethodPatch,
		"/v1/books/"+bookID.String()+"/chapters/"+chID.String()+"/draft",
		bytes.NewReader(payload))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("autosave (PATCH /draft) = %d, body=%s", rr.Code, rr.Body.String())
	}

	_, _, kgRev, _ := kgChapterState(t, ctx, pool, chID)
	if kgRev != nil {
		t.Fatalf("autosave moved kg_indexed_revision_id to %v — autosave must NEVER index "+
			"(unreviewed draft prose must not canonize, and every save would re-pay LLM "+
			"extraction cost)", *kgRev)
	}

	events := outboxEventsFor(t, ctx, pool, chID)
	if countEvent(events, "chapter.kg_indexed") != 0 {
		t.Fatalf("autosave emitted chapter.kg_indexed — it must not. events=%v", events)
	}
	if countEvent(events, "chapter.saved") == 0 {
		t.Fatalf("autosave should still emit chapter.saved (unconsumed by knowledge). events=%v", events)
	}
}

// ── (10) Re-indexing an UNCHANGED draft reuses the revision and costs nothing ──

func TestIndex_UnchangedDraft_ReusesRevision_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("unchanging prose"))

	first, err := s.indexChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("first index: %v", err)
	}
	if first.Reused {
		t.Fatal("the FIRST index must create a revision, not reuse one")
	}

	second, err := s.indexChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("second index: %v", err)
	}
	if !second.Reused {
		t.Fatal("re-indexing an UNCHANGED draft must reuse the existing revision — else " +
			"every click spams chapter_revisions and churns the KG pointer, forcing a " +
			"pointless re-parse + re-extract (acceptance #10: no LLM spend)")
	}
	if second.RevisionID != first.RevisionID {
		t.Fatalf("reused revision %v != original %v", second.RevisionID, first.RevisionID)
	}

	var revCount int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM chapter_revisions WHERE chapter_id=$1`, chID).Scan(&revCount); err != nil {
		t.Fatalf("count revisions: %v", err)
	}
	if revCount != 1 {
		t.Fatalf("chapter_revisions = %d, want 1 — a re-index of identical prose must not "+
			"snapshot a duplicate revision", revCount)
	}
}

// A CHANGED draft, by contrast, must pin a NEW revision and advance the pointer.
func TestIndex_ChangedDraft_PinsNewRevision_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("version one"))

	first, err := s.indexChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("first index: %v", err)
	}

	if _, err := pool.Exec(ctx,
		`UPDATE chapter_drafts SET body=$2, draft_version=draft_version+1 WHERE chapter_id=$1`,
		chID, kgBody("version two — materially different")); err != nil {
		t.Fatalf("edit draft: %v", err)
	}

	second, err := s.indexChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("second index: %v", err)
	}
	if second.Reused {
		t.Fatal("a CHANGED draft must pin a NEW revision, not reuse the stale one")
	}
	if second.RevisionID == first.RevisionID {
		t.Fatal("revision id did not advance for changed prose")
	}

	_, _, kgRev, _ := kgChapterState(t, ctx, pool, chID)
	if kgRev == nil || *kgRev != second.RevisionID {
		t.Fatalf("kg pointer = %v, want the new revision %v", kgRev, second.RevisionID)
	}
}

// ── kg_exclude — the producer-side authoritative refusal (§3.7) ──

func TestIndex_KGExcludedChapter_IsRefusedLoudly_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("private thoughts"))

	if _, err := pool.Exec(ctx, `UPDATE chapters SET kg_exclude=true WHERE id=$1`, chID); err != nil {
		t.Fatalf("set kg_exclude: %v", err)
	}

	_, err := s.indexChapter(ctx, owner, bookID, chID)
	if err == nil {
		t.Fatal("indexing a kg_exclude'd chapter must FAIL loudly — a silent success that " +
			"indexed nothing is the bug class this repo keeps re-shipping")
	}
	if !errors.Is(err, errActionKGExcluded) {
		t.Fatalf("want errActionKGExcluded (so the caller can say WHY), got %v", err)
	}

	_, _, kgRev, _ := kgChapterState(t, ctx, pool, chID)
	if kgRev != nil {
		t.Fatalf("an excluded chapter must NOT get a KG pointer, got %v", *kgRev)
	}
	if n := countEvent(outboxEventsFor(t, ctx, pool, chID), "chapter.kg_indexed"); n != 0 {
		t.Fatalf("an excluded chapter must emit NO chapter.kg_indexed, got %d", n)
	}
}

// Setting kg_exclude AFTER indexing must RETRACT: clear the pointer and emit the
// retraction event so knowledge-service removes the facts it already extracted.
// Without this the toggle is a lie (spec §3.8 / P1-7).
func TestSetKGExclude_AfterIndexing_RetractsAndEmits_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("remembered, then forgotten"))

	if _, err := s.indexChapter(ctx, owner, bookID, chID); err != nil {
		t.Fatalf("index: %v", err)
	}
	if _, _, kgRev, _ := kgChapterState(t, ctx, pool, chID); kgRev == nil {
		t.Fatal("precondition: chapter should be indexed")
	}

	if err := s.setChapterKGExclude(ctx, bookID, chID, true); err != nil {
		t.Fatalf("setChapterKGExclude: %v", err)
	}

	_, _, kgRev, excl := kgChapterState(t, ctx, pool, chID)
	if !excl {
		t.Fatal("kg_exclude was not set")
	}
	if kgRev != nil {
		t.Fatalf("kg_exclude=true must CLEAR the pointer, got %v — otherwise the chapter "+
			"stays in the sweeper's set and keeps re-entering the graph", *kgRev)
	}
	events := outboxEventsFor(t, ctx, pool, chID)
	if countEvent(events, "chapter.kg_excluded") != 1 {
		t.Fatalf("kg_exclude=true must emit chapter.kg_excluded so knowledge RETRACTS the "+
			"already-extracted facts; without it the toggle is a lie. events=%v", events)
	}
}

// Clearing kg_exclude re-opens the chapter to indexing but must NOT silently re-index —
// re-entering the knowledge graph has to be an explicit act.
func TestSetKGExclude_False_DoesNotSilentlyReindex_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("in, out, in again"))

	if _, err := s.indexChapter(ctx, owner, bookID, chID); err != nil {
		t.Fatalf("index: %v", err)
	}
	if err := s.setChapterKGExclude(ctx, bookID, chID, true); err != nil {
		t.Fatalf("exclude: %v", err)
	}
	if err := s.setChapterKGExclude(ctx, bookID, chID, false); err != nil {
		t.Fatalf("un-exclude: %v", err)
	}

	_, _, kgRev, excl := kgChapterState(t, ctx, pool, chID)
	if excl {
		t.Fatal("kg_exclude should be false")
	}
	if kgRev != nil {
		t.Fatalf("clearing kg_exclude must NOT silently re-index (got pointer %v) — a toggle "+
			"that silently re-ingests the user's prose is a privacy surprise; they must "+
			"click 'add to knowledge' again", *kgRev)
	}
}

// ── Empty prose is refused (same guard publish uses) ──

func TestIndex_EmptyProse_IsRefused_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner,
		json.RawMessage(`{"type":"doc","content":[{"type":"paragraph"}]}`))

	if _, err := s.indexChapter(ctx, owner, bookID, chID); err == nil {
		t.Fatal("indexing empty prose must be refused — it would enqueue an LLM extraction " +
			"over nothing")
	}
	if _, _, kgRev, _ := kgChapterState(t, ctx, pool, chID); kgRev != nil {
		t.Fatalf("empty chapter must not be indexed, got %v", *kgRev)
	}
}

// ── (3) The published flow is unchanged: publish still indexes (regression) ──

func TestPublish_StillSetsKGPointer_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("canonical prose"))

	revID, _, err := s.mcpPublishChapter(ctx, owner, bookID, chID)
	if err != nil {
		t.Fatalf("publish: %v", err)
	}
	editorial, publishedRev, kgRev, _ := kgChapterState(t, ctx, pool, chID)
	if editorial != "published" || publishedRev == nil || *publishedRev != revID {
		t.Fatalf("publish regression: status=%q publishedRev=%v want published/%v",
			editorial, publishedRev, revID)
	}
	if kgRev == nil || *kgRev != revID {
		t.Fatalf("publish must ALSO advance the KG pointer (WS-0.3), got %v want %v", kgRev, revID)
	}
}

// Publishing a kg_exclude'd chapter must NOT drag it back into the knowledge graph.
func TestPublish_DoesNotIndexExcludedChapter_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("published but private"))

	if _, err := pool.Exec(ctx, `UPDATE chapters SET kg_exclude=true WHERE id=$1`, chID); err != nil {
		t.Fatalf("set kg_exclude: %v", err)
	}
	if _, _, err := s.mcpPublishChapter(ctx, owner, bookID, chID); err != nil {
		t.Fatalf("publish: %v", err)
	}

	editorial, _, kgRev, _ := kgChapterState(t, ctx, pool, chID)
	if editorial != "published" {
		t.Fatalf("publish should still work on an excluded chapter, status=%q", editorial)
	}
	if kgRev != nil {
		t.Fatalf("publishing a kg_exclude'd chapter must NOT index it (got %v) — kg_exclude "+
			"is the user's explicit 'keep this out of my knowledge graph'", *kgRev)
	}
}
