package api

// #287 — the mechanism behind the clock-independent order: `chapter_revisions.seq`
// comes from the per-chapter counter `chapters.revision_seq` (row-locked UPDATE in
// the inserting transaction), so it is strictly increasing per chapter regardless of
// the wall clock, and the MCP save_draft double-insert (snapshot + new body in ONE
// transaction) lands at n+1 / n+2 in write order. Branch-only file: it names the seq
// column, which only exists after this branch's migration.
import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestRevisionSeqIsMonotonicPerChapter_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	// REST patchDraft (one insert)…
	revisionClockTestServerCalls(t, s, bookID, chID, owner, "save one")
	// …then the MCP tool's double-insert (snapshot + new body, one tx).
	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), Body: draftProse,
	}); err != nil {
		t.Fatalf("save_draft: %v", err)
	}

	rows, err := pool.Query(ctx, `
SELECT COALESCE(message,''), seq FROM chapter_revisions WHERE chapter_id=$1 ORDER BY seq ASC`, chID)
	if err != nil {
		t.Fatalf("query seqs: %v", err)
	}
	defer rows.Close()
	type revRow struct {
		message string
		seq     int64
	}
	var got []revRow
	for rows.Next() {
		var r revRow
		if err := rows.Scan(&r.message, &r.seq); err != nil {
			t.Fatalf("scan: %v", err)
		}
		got = append(got, r)
	}
	if len(got) < 3 {
		t.Fatalf("expected 3 revisions (patch + snapshot + body), got %d", len(got))
	}
	for i := 1; i < len(got); i++ {
		if got[i].seq != got[i-1].seq+1 {
			t.Fatalf("seq not gap-free increasing per chapter: %+v", got)
		}
	}
	var counter int64
	if err := pool.QueryRow(ctx, `SELECT revision_seq FROM chapters WHERE id=$1`, chID).Scan(&counter); err != nil {
		t.Fatalf("read chapters.revision_seq: %v", err)
	}
	if counter != int64(len(got)) {
		t.Fatalf("chapters.revision_seq = %d, want %d (the insert counter must sit at the tail)", counter, len(got))
	}
	if got[len(got)-2].message != "before assistant save" || got[len(got)-1].message != "" {
		t.Fatalf("MCP double-insert order wrong: %+v (want snapshot then the new body, in write order)", got)
	}
}
