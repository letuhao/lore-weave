package api

// mui #1c G-cand — DB-integration tests for the merge-candidate surface.
// Exercise the auth-free cores (proposeOneCandidate / loadMergeCandidates /
// dismissMergeCandidateCore / markCandidatesMerged) so the propose→review→
// dismiss/merge lifecycle is covered without the JWT/book-owner HTTP layer.
// Require GLOSSARY_TEST_DB_URL; skip otherwise (via openTestDB).

import (
	"slices"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func (f *mergeFixture) candidateStatus(t *testing.T, id uuid.UUID) string {
	t.Helper()
	var st string
	f.pool.QueryRow(f.ctx, `SELECT status FROM merge_candidates WHERE candidate_id=$1`, id).Scan(&st)
	return st
}

func (f *mergeFixture) countCandidates(t *testing.T) int {
	t.Helper()
	var n int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM merge_candidates WHERE book_id=$1`, f.bookID).Scan(&n)
	return n
}

func TestProposeCandidate_CreatesRowWithMemberDetail(t *testing.T) {
	f := newMergeFixture(t, "00000000c001")
	a := f.mkEntity(t, "姜子牙", []string{"子牙"})
	b := f.mkEntity(t, "太公望", nil)
	// give a chapter link so the member detail's chapter count is non-zero
	f.pool.Exec(f.ctx, `INSERT INTO chapter_entity_links(entity_id,chapter_id,relevance) VALUES($1,$2,'appears')`, a, uuid.New())

	res := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs:         []string{a.String(), b.String()},
		SuggestedWinnerEntityID: a.String(),
		Score:                   0.82,
		Evidence:                []any{map[string]any{"kind": "shared_chapter"}},
		Rationale:               "co-occur in封神台 scenes",
	})
	if res.Status != "proposed" || res.CandidateID == "" {
		t.Fatalf("propose: status=%q id=%q reason=%q", res.Status, res.CandidateID, res.Reason)
	}

	views, err := f.srv.loadMergeCandidates(f.ctx, f.bookID, "proposed", 0)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(views) != 1 {
		t.Fatalf("want 1 candidate, got %d", len(views))
	}
	v := views[0]
	if v.SuggestedWinner != a.String() || v.Score != 0.82 || v.KindCode != "character" {
		t.Errorf("view fields wrong: winner=%q score=%v kind=%q", v.SuggestedWinner, v.Score, v.KindCode)
	}
	// evidence survives propose→store→list round-trip (JSONB)
	if !strings.Contains(string(v.Evidence), "shared_chapter") {
		t.Errorf("evidence lost in round-trip: %s", string(v.Evidence))
	}
	if v.Rationale != "co-occur in封神台 scenes" {
		t.Errorf("rationale lost: %q", v.Rationale)
	}
	if len(v.Members) != 2 {
		t.Fatalf("want 2 members, got %d", len(v.Members))
	}
	// member detail carries names + aliases + chapter counts
	byID := map[string]mergeCandidateMember{}
	for _, m := range v.Members {
		byID[m.EntityID] = m
	}
	if byID[a.String()].Name != "姜子牙" || !slices.Contains(byID[a.String()].Aliases, "子牙") {
		t.Errorf("member a detail wrong: %+v", byID[a.String()])
	}
	if byID[a.String()].ChapterLinks != 1 {
		t.Errorf("member a chapter count = %d, want 1", byID[a.String()].ChapterLinks)
	}
	if byID[b.String()].Name != "太公望" {
		t.Errorf("member b name wrong: %+v", byID[b.String()])
	}
}

func TestProposeCandidate_IdempotentBySetKey(t *testing.T) {
	f := newMergeFixture(t, "00000000c002")
	a := f.mkEntity(t, "甲", nil)
	b := f.mkEntity(t, "乙", nil)

	// member order reversed on the second call — same set key, same row.
	r1 := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{a.String(), b.String()}, Score: 0.5,
	})
	r2 := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{b.String(), a.String()}, Score: 0.9, Rationale: "stronger",
	})
	if r1.Status != "proposed" || r2.Status != "proposed" {
		t.Fatalf("statuses: %q %q", r1.Status, r2.Status)
	}
	if r1.CandidateID != r2.CandidateID {
		t.Errorf("re-propose made a new row: %q vs %q", r1.CandidateID, r2.CandidateID)
	}
	if n := f.countCandidates(t); n != 1 {
		t.Errorf("want 1 row, got %d", n)
	}
	// the update took effect (score/rationale refreshed on the proposed row)
	views, _ := f.srv.loadMergeCandidates(f.ctx, f.bookID, "proposed", 0)
	if len(views) != 1 || views[0].Score != 0.9 || views[0].Rationale != "stronger" {
		t.Errorf("upsert did not refresh: %+v", views)
	}
}

func TestProposeCandidate_DismissedNotResurrected(t *testing.T) {
	f := newMergeFixture(t, "00000000c003")
	a := f.mkEntity(t, "甲", nil)
	b := f.mkEntity(t, "乙", nil)

	r1 := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{a.String(), b.String()},
	})
	cid := uuid.MustParse(r1.CandidateID)
	if reason, err := f.srv.dismissMergeCandidateCore(f.ctx, f.bookID, cid); err != nil || reason != "" {
		t.Fatalf("dismiss: reason=%q err=%v", reason, err)
	}
	if st := f.candidateStatus(t, cid); st != "dismissed" {
		t.Fatalf("status after dismiss = %q", st)
	}

	// re-propose the same set → suppressed, status stays dismissed, no new row
	r2 := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{a.String(), b.String()}, Score: 0.99,
	})
	if r2.Status != "suppressed" {
		t.Errorf("re-propose of dismissed: status=%q (want suppressed)", r2.Status)
	}
	if st := f.candidateStatus(t, cid); st != "dismissed" {
		t.Errorf("dismissed cluster resurrected: status=%q", st)
	}
	if n := f.countCandidates(t); n != 1 {
		t.Errorf("want 1 row, got %d", n)
	}
}

func TestProposeCandidate_Validation(t *testing.T) {
	f := newMergeFixture(t, "00000000c004")
	a := f.mkEntity(t, "甲", nil)

	// < 2 distinct members (duplicate collapses to 1)
	if r := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{a.String(), a.String()},
	}); r.Status != "skipped" {
		t.Errorf("dup-member: status=%q (want skipped)", r.Status)
	}
	// missing member id
	if r := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{a.String(), uuid.New().String()},
	}); r.Status != "skipped" {
		t.Errorf("missing-member: status=%q (want skipped)", r.Status)
	}
	// cross-kind cluster (book-tier kind)
	var otherKind uuid.UUID
	f.pool.QueryRow(f.ctx, `SELECT book_kind_id FROM book_kinds WHERE book_id=$1 AND code<>'character' AND is_hidden=false LIMIT 1`, f.bookID).Scan(&otherKind)
	if otherKind != uuid.Nil {
		var other uuid.UUID
		f.pool.QueryRow(f.ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, f.bookID, otherKind).Scan(&other)
		if r := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
			MemberEntityIDs: []string{a.String(), other.String()},
		}); r.Status != "skipped" {
			t.Errorf("cross-kind: status=%q (want skipped)", r.Status)
		}
	}
	if n := f.countCandidates(t); n != 0 {
		t.Errorf("invalid candidates created rows: %d", n)
	}
}

func TestDismissCandidate_NotFoundAndAlreadyMerged(t *testing.T) {
	f := newMergeFixture(t, "00000000c005")
	a := f.mkEntity(t, "甲", nil)
	b := f.mkEntity(t, "乙", nil)

	// not found
	if reason, _ := f.srv.dismissMergeCandidateCore(f.ctx, f.bookID, uuid.New()); reason != "not_found" {
		t.Errorf("missing candidate: reason=%q (want not_found)", reason)
	}
	// merged → cannot dismiss
	r := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{a.String(), b.String()},
	})
	cid := uuid.MustParse(r.CandidateID)
	f.pool.Exec(f.ctx, `UPDATE merge_candidates SET status='merged' WHERE candidate_id=$1`, cid)
	if reason, _ := f.srv.dismissMergeCandidateCore(f.ctx, f.bookID, cid); reason != "already_merged" {
		t.Errorf("merged candidate: reason=%q (want already_merged)", reason)
	}
}

func TestMarkCandidatesMerged_ClosesInbox(t *testing.T) {
	f := newMergeFixture(t, "00000000c006")
	winner := f.mkEntity(t, "姜子牙", nil)
	loser := f.mkEntity(t, "太公望", nil)
	other := f.mkEntity(t, "妲己", nil)

	rWin := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{winner.String(), loser.String()}, SuggestedWinnerEntityID: winner.String(),
	})
	rNoWinner := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{loser.String(), other.String()},
	})
	// MED-1: a superset cluster (winner+loser+other) must NOT close on a merge of
	// just {winner,loser} — `other` is still unresolved.
	rSuperset := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{winner.String(), loser.String(), other.String()},
	})
	// a dismissed cluster must stay dismissed even if this merge fully covers it.
	dWinner := f.mkEntity(t, "雷震子", nil)
	dLoser := f.mkEntity(t, "辛環", nil)
	rDismissed := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
		MemberEntityIDs: []string{dWinner.String(), dLoser.String()},
	})
	f.srv.dismissMergeCandidateCore(f.ctx, f.bookID, uuid.MustParse(rDismissed.CandidateID))

	f.srv.markCandidatesMerged(f.ctx, f.bookID, winner, []uuid.UUID{loser})
	f.srv.markCandidatesMerged(f.ctx, f.bookID, dWinner, []uuid.UUID{dLoser})

	if st := f.candidateStatus(t, uuid.MustParse(rWin.CandidateID)); st != "merged" {
		t.Errorf("exactly-resolved candidate status = %q (want merged)", st)
	}
	// no winner among members → not flipped
	if st := f.candidateStatus(t, uuid.MustParse(rNoWinner.CandidateID)); st != "proposed" {
		t.Errorf("no-winner candidate flipped: status=%q (want proposed)", st)
	}
	// superset with an unresolved member → stays proposed (MED-1)
	if st := f.candidateStatus(t, uuid.MustParse(rSuperset.CandidateID)); st != "proposed" {
		t.Errorf("superset candidate prematurely closed: status=%q (want proposed)", st)
	}
	// dismissed stays dismissed
	if st := f.candidateStatus(t, uuid.MustParse(rDismissed.CandidateID)); st != "dismissed" {
		t.Errorf("dismissed candidate flipped: status=%q (want dismissed)", st)
	}
}

// TestLoadMergeCandidates_LimitCapsLoad proves the `limit` arg caps the SQL load
// (D-PLAN-MERGE-CONTEXT-COST): with 3 proposed clusters, limit=2 returns the 2
// highest-score ones (so the planner's per-call context is bounded regardless of
// backlog size) while limit=0 returns all 3 (the FE inbox path is unchanged).
func TestLoadMergeCandidates_LimitCapsLoad(t *testing.T) {
	f := newMergeFixture(t, "00000000c007")
	// 3 distinct 2-member clusters with distinct scores (so the score-ordering is testable).
	mk := func(n1, n2 string, score float64) {
		a := f.mkEntity(t, n1, nil)
		b := f.mkEntity(t, n2, nil)
		if r := f.srv.proposeOneCandidate(f.ctx, f.bookID, proposeCandidateInput{
			MemberEntityIDs: []string{a.String(), b.String()}, Score: score,
		}); r.Status != "proposed" {
			t.Fatalf("seed candidate (%s/%s): status=%q", n1, n2, r.Status)
		}
	}
	mk("甲", "乙", 0.9)
	mk("丙", "丁", 0.8)
	mk("戊", "己", 0.7)

	// limit=0 → all 3 (FE inbox behaviour).
	if all, err := f.srv.loadMergeCandidates(f.ctx, f.bookID, "proposed", 0); err != nil || len(all) != 3 {
		t.Fatalf("limit=0: want 3 candidates, got %d (err=%v)", len(all), err)
	}
	// limit=2 → exactly the 2 highest-score clusters (0.9, 0.8), score-descending.
	capped, err := f.srv.loadMergeCandidates(f.ctx, f.bookID, "proposed", 2)
	if err != nil {
		t.Fatalf("limit=2: %v", err)
	}
	if len(capped) != 2 {
		t.Fatalf("limit=2: want 2 candidates, got %d", len(capped))
	}
	if capped[0].Score != 0.9 || capped[1].Score != 0.8 {
		t.Errorf("limit=2: want the top-2 by score (0.9, 0.8), got %.2f, %.2f", capped[0].Score, capped[1].Score)
	}
}
