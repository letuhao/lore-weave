package api

// Codex review on PR #325 (P1): MCP save_draft locked the chapters row first
// (snapshot CTE) while REST patchDraft/publish locked the draft row first, so
// overlapping saves deadlocked (40P01). The fix makes every two-row write
// take the draft lock FIRST — the static guard in
// revision_write_guards_test.go pins that order in the real source.
//
// This test proves the order serializes at the Postgres level: a second
// save that starts while a first save holds the draft lock must WAIT for it
// (then proceed), never deadlock. The interleaving below drives the two
// transactions' exact statements (patchDraft's draft UPDATE + counter CTE,
// save_draft's post-fix draft UPDATE + counter CTE); the pre-fix order
// (chapters CTE first) aborted the REST side with 40P01 on this same
// interleaving — reproduced on the pre-fix code before the fix landed.

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestRevisionSaveLockOrderSerializes_DB(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	_, chID := seedChapter(t, ctx, pool, owner)

	conn1, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire 1: %v", err)
	}
	defer conn1.Release()
	conn2, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire 2: %v", err)
	}
	defer conn2.Release()

	body := `{"type":"doc","content":[{"type":"paragraph","_text":"concurrent save"}]}`
	draftUpdate := `UPDATE chapter_drafts SET body=$2,draft_format=$3,draft_updated_at=now(),draft_version=draft_version+1 WHERE chapter_id=$1`
	seqInsert := `
WITH s AS (UPDATE chapters SET revision_seq=revision_seq+1 WHERE id=$1 RETURNING revision_seq)
INSERT INTO chapter_revisions(chapter_id, seq, body, body_format, message, author_user_id)
SELECT $1, s.revision_seq, $2, $3, $4, $5 FROM s`

	// Tx1 (REST order): draft UPDATE first — takes the draft lock (and the
	// chapters lock via the word-count trigger), then the counter CTE.
	if _, err := conn1.Exec(ctx, `BEGIN`); err != nil {
		t.Fatalf("tx1 begin: %v", err)
	}
	if _, err := conn1.Exec(ctx, `SET LOCAL lock_timeout = '10s'`); err != nil {
		t.Fatalf("tx1 timeout: %v", err)
	}
	if _, err := conn1.Exec(ctx, draftUpdate, chID, body, "json"); err != nil {
		t.Fatalf("tx1 draft update: %v", err)
	}

	// Tx2 (MCP post-fix order): draft UPDATE first as well — it must BLOCK
	// on the draft row (not deadlock), then proceed once tx1 commits.
	tx2done := make(chan error, 1)
	go func() {
		defer conn2.Exec(ctx, `ROLLBACK`)
		if _, err := conn2.Exec(ctx, `BEGIN`); err != nil {
			tx2done <- err
			return
		}
		if _, err := conn2.Exec(ctx, `SET LOCAL lock_timeout = '10s'`); err != nil {
			tx2done <- err
			return
		}
		if _, err := conn2.Exec(ctx, draftUpdate, chID, body, "json"); err != nil {
			tx2done <- err
			return
		}
		if _, err := conn2.Exec(ctx, seqInsert, chID, body, "json", "concurrent save", owner); err != nil {
			tx2done <- err
			return
		}
		if _, err := conn2.Exec(ctx, `COMMIT`); err != nil {
			tx2done <- err
			return
		}
		tx2done <- nil
	}()
	time.Sleep(500 * time.Millisecond) // let tx2 block on the draft row

	if _, err := conn1.Exec(ctx, seqInsert, chID, body, "json", "concurrent save", owner); err != nil {
		t.Fatalf("tx1 seq insert: %v", err)
	}
	if _, err := conn1.Exec(ctx, `COMMIT`); err != nil {
		t.Fatalf("tx1 commit: %v", err)
	}

	select {
	case err := <-tx2done:
		if err != nil {
			if strings.Contains(err.Error(), "40P01") {
				t.Fatalf("tx2 deadlocked (40P01) — the two save paths still take the row locks in opposite orders: %v", err)
			}
			t.Fatalf("tx2: %v", err)
		}
	case <-time.After(15 * time.Second):
		t.Fatal("tx2 did not finish after tx1 committed — it is stuck, not serialized")
	}

	// Both saves landed, seqs 1 then 2 in write order, counter at the tail.
	assertRevisionSeqs(t, pool, chID, 2)
}
