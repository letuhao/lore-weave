package api

// mui #1c — DB-integration tests for the entity merge/un-merge (destructive).
// Tests call the core methods (mergeOne / revertMergeCore) directly so they
// exercise the repoint+fold+soft-delete+journal logic without the JWT/book-
// owner HTTP layer. Require GLOSSARY_TEST_DB_URL; skip otherwise.

import (
	"context"
	"encoding/json"
	"slices"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

func runMergeMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	ctx := context.Background()
	for _, m := range []struct {
		name string
		fn   func(context.Context, *pgxpool.Pool) error
	}{
		{"Up", migrate.Up}, {"Seed", migrate.Seed}, {"UpSnapshot", migrate.UpSnapshot},
		{"UpSoftDelete", migrate.UpSoftDelete}, {"UpWiki", migrate.UpWiki},
		{"UpWikiSuggestions", migrate.UpWikiSuggestions}, {"UpExtraction", migrate.UpExtraction},
		{"UpOutbox", migrate.UpOutbox}, {"UpEntityEnrichments", migrate.UpEntityEnrichments},
		{"UpEntityMerge", migrate.UpEntityMerge}, {"UpMergeCandidates", migrate.UpMergeCandidates},
	} {
		if err := m.fn(ctx, pool); err != nil {
			t.Fatalf("migrate.%s: %v", m.name, err)
		}
	}
}

type mergeFixture struct {
	pool         *pgxpool.Pool
	ctx          context.Context
	srv          *Server
	bookID       uuid.UUID
	kindID       uuid.UUID
	nameAttr     uuid.UUID
	aliasAttr    uuid.UUID
	descAttr     uuid.UUID
}

func newMergeFixture(t *testing.T, bookSuffix string) *mergeFixture {
	pool := openTestDB(t)
	runMergeMigrations(t, pool)
	ctx := context.Background()
	f := &mergeFixture{pool: pool, ctx: ctx, bookID: uuid.MustParse("019e0000-0000-7000-bbbb-" + bookSuffix)}
	srv, _ := newEntitiesListServer(t)
	srv.pool = pool
	f.srv = srv
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&f.kindID)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, f.kindID).Scan(&f.nameAttr)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='aliases' LIMIT 1`, f.kindID).Scan(&f.aliasAttr)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='description' LIMIT 1`, f.kindID).Scan(&f.descAttr)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM merge_journal WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM merge_candidates WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, f.bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})
	return f
}

func (f *mergeFixture) mkEntity(t *testing.T, name string, aliases []string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := f.pool.QueryRow(f.ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		f.bookID, f.kindID).Scan(&id); err != nil {
		t.Fatalf("mkEntity: %v", err)
	}
	f.pool.Exec(f.ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh',$3)`, id, f.nameAttr, name)
	if aliases != nil {
		j, _ := json.Marshal(aliases)
		f.pool.Exec(f.ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh',$3)`, id, f.aliasAttr, string(j))
	}
	return id
}

func (f *mergeFixture) aliasesOf(t *testing.T, id uuid.UUID) []string {
	t.Helper()
	var raw string
	err := f.pool.QueryRow(f.ctx, `SELECT original_value FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, id, f.aliasAttr).Scan(&raw)
	if err != nil {
		return nil
	}
	var out []string
	json.Unmarshal([]byte(raw), &out)
	return out
}

func (f *mergeFixture) isSoftDeleted(t *testing.T, id uuid.UUID) (deleted bool, mergedInto *uuid.UUID) {
	t.Helper()
	var del *string
	f.pool.QueryRow(f.ctx, `SELECT deleted_at::text, merged_into_entity_id FROM glossary_entities WHERE entity_id=$1`, id).Scan(&del, &mergedInto)
	return del != nil, mergedInto
}

func TestMergeOne_HappyPath_RepointsAndFolds(t *testing.T) {
	f := newMergeFixture(t, "000000000001")
	winner := f.mkEntity(t, "姜子牙", nil)
	loser := f.mkEntity(t, "太公望", []string{"子牙"})
	// loser-only child rows that should repoint to winner:
	chap := uuid.New()
	f.pool.Exec(f.ctx, `INSERT INTO chapter_entity_links(entity_id,chapter_id,relevance) VALUES($1,$2,'appears')`, loser, chap)
	f.pool.Exec(f.ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','原為崑崙弟子')`, loser, f.descAttr) // winner lacks description

	jid, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New())
	if err != nil || reason != "" {
		t.Fatalf("mergeOne failed: reason=%q err=%v", reason, err)
	}
	if jid == uuid.Nil {
		t.Fatal("no journal id")
	}

	// loser soft-deleted + merged_into=winner
	del, into := f.isSoftDeleted(t, loser)
	if !del || into == nil || *into != winner {
		t.Errorf("loser not soft-deleted/merged: del=%v into=%v", del, into)
	}
	// chapter link repointed to winner
	var nLink int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`, winner, chap).Scan(&nLink)
	if nLink != 1 {
		t.Errorf("chapter link not repointed: winner has %d", nLink)
	}
	// description attr repointed to winner
	var nDesc int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, winner, f.descAttr).Scan(&nDesc)
	if nDesc != 1 {
		t.Errorf("description not repointed: winner has %d", nDesc)
	}
	// aliases folded: winner now carries loser's name + loser's aliases
	al := f.aliasesOf(t, winner)
	if !slices.Contains(al, "太公望") || !slices.Contains(al, "子牙") {
		t.Errorf("aliases not folded: %v", al)
	}
	if slices.Contains(al, "姜子牙") {
		t.Errorf("winner aliased to its own name: %v", al)
	}
}

func TestMergeOne_ConflictsStayWithLoser(t *testing.T) {
	f := newMergeFixture(t, "000000000002")
	winner := f.mkEntity(t, "李靖A", nil)
	loser := f.mkEntity(t, "李靖B", nil)
	shared := uuid.New()
	// BOTH linked to the same chapter → the loser's link must NOT move (UNIQUE).
	f.pool.Exec(f.ctx, `INSERT INTO chapter_entity_links(entity_id,chapter_id,relevance) VALUES($1,$2,'appears')`, winner, shared)
	f.pool.Exec(f.ctx, `INSERT INTO chapter_entity_links(entity_id,chapter_id,relevance) VALUES($1,$2,'appears')`, loser, shared)

	_, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New())
	if err != nil || reason != "" {
		t.Fatalf("mergeOne: reason=%q err=%v", reason, err)
	}
	// winner still has exactly one link to the shared chapter
	var nW int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`, winner, shared).Scan(&nW)
	if nW != 1 {
		t.Errorf("winner shared-chapter link count = %d, want 1", nW)
	}
	// loser's conflicting link stayed with loser
	var nL int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`, loser, shared).Scan(&nL)
	if nL != 1 {
		t.Errorf("loser conflicting link count = %d, want 1 (stays with hidden loser)", nL)
	}
	// loser's name attr stayed with loser (winner already had a name)
	var nLoserName int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`, loser, f.nameAttr).Scan(&nLoserName)
	if nLoserName != 1 {
		t.Errorf("loser name attr count = %d, want 1 (conflict stays)", nLoserName)
	}
}

func TestMergeOne_Validation(t *testing.T) {
	f := newMergeFixture(t, "000000000003")
	winner := f.mkEntity(t, "甲", nil)

	// same entity
	if _, reason, _ := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, winner, uuid.New()); reason != "same entity" {
		t.Errorf("same-entity: reason=%q", reason)
	}
	// loser not found
	if _, reason, _ := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, uuid.New(), uuid.New()); reason != "loser not found" {
		t.Errorf("not-found: reason=%q", reason)
	}
	// different kind: make a loser under a different kind
	var otherKind uuid.UUID
	f.pool.QueryRow(f.ctx, `SELECT kind_id FROM entity_kinds WHERE code<>'character' AND is_hidden=false LIMIT 1`).Scan(&otherKind)
	if otherKind != uuid.Nil {
		var lid uuid.UUID
		f.pool.QueryRow(f.ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, f.bookID, otherKind).Scan(&lid)
		if _, reason, _ := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, lid, uuid.New()); reason != "different kind" {
			t.Errorf("different-kind: reason=%q", reason)
		}
	}
}

func TestMerge_RevertRoundTrip(t *testing.T) {
	f := newMergeFixture(t, "000000000004")
	winner := f.mkEntity(t, "楊戩", []string{"二郎神"})
	loser := f.mkEntity(t, "二郎真君", nil)
	chap := uuid.New()
	f.pool.Exec(f.ctx, `INSERT INTO chapter_entity_links(entity_id,chapter_id,relevance) VALUES($1,$2,'appears')`, loser, chap)
	aliasesBefore := f.aliasesOf(t, winner)

	jid, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New())
	if err != nil || reason != "" {
		t.Fatalf("merge: %q %v", reason, err)
	}
	// revert
	if r, err := f.srv.revertMergeCore(f.ctx, f.bookID, jid); err != nil || r != "" {
		t.Fatalf("revert: reason=%q err=%v", r, err)
	}
	// loser live again
	if del, _ := f.isSoftDeleted(t, loser); del {
		t.Error("loser still soft-deleted after revert")
	}
	// chapter link back on loser, not winner
	var onLoser, onWinner int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`, loser, chap).Scan(&onLoser)
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`, winner, chap).Scan(&onWinner)
	if onLoser != 1 || onWinner != 0 {
		t.Errorf("link not reverted: loser=%d winner=%d", onLoser, onWinner)
	}
	// winner aliases restored to before
	if got := f.aliasesOf(t, winner); len(got) != len(aliasesBefore) || (len(got) > 0 && got[0] != aliasesBefore[0]) {
		t.Errorf("aliases not restored: got=%v want=%v", got, aliasesBefore)
	}
	// double revert → already_reverted
	if r, _ := f.srv.revertMergeCore(f.ctx, f.bookID, jid); r != "already_reverted" {
		t.Errorf("double revert: reason=%q", r)
	}
}

// MED-1: winner lacks aliases, loser has them → the loser's aliases row must
// NOT be repointed (only folded), so revert restores the loser's ORIGINAL
// aliases instead of the folded/polluted form.
func TestMerge_RevertRestoresLoserAliases_WhenWinnerLackedAliases(t *testing.T) {
	f := newMergeFixture(t, "000000000005")
	winner := f.mkEntity(t, "W", nil)                  // no aliases
	loser := f.mkEntity(t, "L", []string{"别名一"}) // has aliases

	jid, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New())
	if err != nil || reason != "" {
		t.Fatalf("merge: %q %v", reason, err)
	}
	// winner gained folded aliases; loser keeps its own aliases row (not moved).
	if al := f.aliasesOf(t, winner); !slices.Contains(al, "别名一") || !slices.Contains(al, "L") {
		t.Errorf("winner fold wrong: %v", al)
	}
	if al := f.aliasesOf(t, loser); len(al) != 1 || al[0] != "别名一" {
		t.Errorf("loser aliases moved/changed during merge: %v", al)
	}

	if r, err := f.srv.revertMergeCore(f.ctx, f.bookID, jid); err != nil || r != "" {
		t.Fatalf("revert: %q %v", r, err)
	}
	// loser's ORIGINAL aliases intact; winner's inserted aliases row deleted.
	if al := f.aliasesOf(t, loser); len(al) != 1 || al[0] != "别名一" {
		t.Errorf("loser aliases corrupted by revert: %v", al)
	}
	if al := f.aliasesOf(t, winner); len(al) != 0 {
		t.Errorf("winner aliases not cleaned on revert: %v", al)
	}
}

// MED-3a: reverting out of order (the winner has since been merged away) is
// rejected — the later merge must be reverted first.
func TestRevert_ChainGuardRejectsOutOfOrder(t *testing.T) {
	f := newMergeFixture(t, "000000000006")
	a := f.mkEntity(t, "甲", nil)
	b := f.mkEntity(t, "乙", nil)
	c := f.mkEntity(t, "丙", nil)
	jidAB, reason, err := f.srv.mergeOne(f.ctx, f.bookID, b, f.kindID, a, uuid.New()) // A→B
	if err != nil || reason != "" {
		t.Fatalf("merge A→B: %q %v", reason, err)
	}
	if _, reason, err := f.srv.mergeOne(f.ctx, f.bookID, c, f.kindID, b, uuid.New()); err != nil || reason != "" { // B→C
		t.Fatalf("merge B→C: %q %v", reason, err)
	}
	// B is now merged into C → reverting A→B must be rejected.
	if r, err := f.srv.revertMergeCore(f.ctx, f.bookID, jidAB); err != nil || r != "winner_since_merged" {
		t.Errorf("chain guard: reason=%q err=%v (want winner_since_merged)", r, err)
	}
}
