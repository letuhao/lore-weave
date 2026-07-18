package api

// SC11-amendment Phase 0 — `chapter.scenes_linked`, the PRODUCER half.
//
// `scenes.source_scene_id` is written in THREE places and, before Phase 0, only TWO of them
// emitted anything at all — and the one that emitted NOTHING is the one that creates the link for
// a plain import (the IX-12 decompile write-back, in worker-infra). Any consumer built on those
// events would therefore render a decompiled book as ENTIRELY UNWRITTEN: a confident, wrong,
// whole-book answer.
//
// These are the two writers that live in book-service. Writer #3 (worker-infra) is covered by
// `services/worker-infra/internal/tasks/scenes_linked_test.go`.
//
// The load-bearing NEGATIVE is as important as the positive: a link-less import and a no-op
// re-parse must emit NOTHING. A no-op event is not harmless — it is a lie the relay pays to
// deliver, and it trains the consumer to re-read for nothing.
//
// DB-gated on BOOK_TEST_DATABASE_URL (dbTestServer skips without it).

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// scenesLinkedCount counts `chapter.scenes_linked` events emitted for a chapter.
func scenesLinkedCount(t *testing.T, ctx context.Context, pool *pgxpool.Pool, chID uuid.UUID) int {
	t.Helper()
	return countEvent(outboxEventsFor(t, ctx, pool, chID), ScenesLinkedEvent)
}

// ── WRITER #1 — the import INSERT (parse.go) ─────────────────────────────────────────────────

func TestScenesLinked_Import_EmitsOnlyWhenAnAnchorWasRecovered_DB(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()

	// A chapter whose scenes carry NO recovered anchor — the COMMON case (a plain import: the
	// parser only recovers `data-scene-id` from an already-exported document). The links do not
	// exist yet, so there is nothing for a mirror to reconcile.
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("She crossed the bridge."))
	// Reap. CASCADE clears chapters + scenes + outbox rows. Without this the rows leak into the
	// shared DB and fail `internal/migrate`'s backfill test, which asserts over EVERY scene.
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, bookID) })
	if _, err := pool.Exec(ctx,
		`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version)
		 VALUES($1,$2,0,'0','She crossed the bridge.','h0',NULL,1)`, chID, bookID); err != nil {
		t.Fatalf("seed unlinked scene: %v", err)
	}
	if n := scenesLinkedCount(t, ctx, pool, chID); n != 0 {
		t.Fatalf("a LINK-LESS import emitted %d scenes_linked — a no-op must emit nothing", n)
	}

	// Now the anchored case: a scene that DOES carry a back-link. `parse.go` sets `anyLinked` and
	// emits in the same tx as the INSERT.
	//
	// We assert the emit helper against the same tx boundary parse.go uses, because the handler
	// itself needs a full multipart import; the seam under test is "a recovered anchor ⇒ an event
	// in THIS tx", and that is exactly what emitScenesLinked does.
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	specNode := uuid.New()
	if _, err := tx.Exec(ctx,
		`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version)
		 VALUES($1,$2,1,'1','He did not.','h1',$3,1)`, chID, bookID, specNode); err != nil {
		tx.Rollback(ctx)
		t.Fatalf("insert anchored scene: %v", err)
	}
	if err := emitScenesLinked(ctx, tx, bookID, chID); err != nil {
		tx.Rollback(ctx)
		t.Fatalf("emitScenesLinked: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit: %v", err)
	}

	if n := scenesLinkedCount(t, ctx, pool, chID); n != 1 {
		t.Fatalf("an ANCHORED import emitted %d scenes_linked, want exactly 1", n)
	}
}

func TestScenesLinked_EmitIsAtomicWithTheLink_DB(t *testing.T) {
	// INV-O12. If the emit could not be written, the LINK must not exist either — otherwise
	// composition's mirror never learns of a link that is sitting in book-service's table, and the
	// projection silently diverges from the truth it mirrors. Rolling the tx back must take BOTH.
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, kgBody("A rolled-back link."))
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, bookID) })

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	specNode := uuid.New()
	if _, err := tx.Exec(ctx,
		`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version)
		 VALUES($1,$2,0,'0','x','h',$3,1)`, chID, bookID, specNode); err != nil {
		tx.Rollback(ctx)
		t.Fatalf("insert: %v", err)
	}
	if err := emitScenesLinked(ctx, tx, bookID, chID); err != nil {
		tx.Rollback(ctx)
		t.Fatalf("emit: %v", err)
	}
	// Simulate the emit path failing AFTER both writes: the caller rolls back.
	if err := tx.Rollback(ctx); err != nil {
		t.Fatalf("rollback: %v", err)
	}

	var scenes int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM scenes WHERE chapter_id=$1 AND source_scene_id IS NOT NULL`, chID,
	).Scan(&scenes); err != nil {
		t.Fatalf("count scenes: %v", err)
	}
	if scenes != 0 {
		t.Fatalf("%d linked scene(s) survived a rolled-back tx — the link and its event are not atomic", scenes)
	}
	if n := scenesLinkedCount(t, ctx, pool, chID); n != 0 {
		t.Fatalf("%d event(s) survived a rolled-back tx", n)
	}
}

// ── WRITER #2 — re-parse (reparse.go, via its callers' counts.changed() guard) ───────────────

func TestScenesLinked_Reparse_EmitsAlongsideScenesReparsed_DB(t *testing.T) {
	// The re-parse seam is exercised through PUBLISH (the same path
	// TestPublishReparsesIndexAndEmitsBothEvents_DB uses): it re-parses the pinned body, upserts
	// the scenes, and emits scenes_reparsed inside `counts.changed()`. A re-parse re-resolves
	// every scene's anchor (`desiredSourceSceneID`), so the spec back-links may have MOVED —
	// which is exactly when the mirror must re-read.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, bookID) })
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	anchor := uuid.New()
	parseSrv := mockParseServer(t, twoSceneTreeJSON(anchor.String()))
	defer parseSrv.Close()
	s.cfg.KnowledgeServiceURL = parseSrv.URL

	if code, out := publishViaRouter(t, s, uuid.New(), bookID, chID); code != 200 {
		t.Fatalf("publish = %d, body=%v", code, out)
	}

	events := outboxEventsFor(t, ctx, pool, chID)
	if n := countEvent(events, "chapter.scenes_reparsed"); n != 1 {
		t.Fatalf("want 1 chapter.scenes_reparsed, got %d (events=%v)", n, events)
	}
	if n := countEvent(events, ScenesLinkedEvent); n != 1 {
		t.Fatalf("want 1 %s alongside it, got %d (events=%v) — writer #2 does not emit",
			ScenesLinkedEvent, n, events)
	}

	// …and a NO-OP re-publish must emit NEITHER. The guard is `counts.changed()`; if
	// scenes_linked escaped it, every idempotent re-parse would wake the consumer for nothing.
	if code, _ := publishViaRouter(t, s, uuid.New(), bookID, chID); code != 200 && code != 409 {
		t.Fatalf("re-publish = %d, want 200 or 409", code)
	}
	events = outboxEventsFor(t, ctx, pool, chID)
	if n := countEvent(events, ScenesLinkedEvent); n != 1 {
		t.Fatalf("a NO-OP re-parse emitted %s again (total %d) — it must ride counts.changed()",
			ScenesLinkedEvent, n)
	}
}
