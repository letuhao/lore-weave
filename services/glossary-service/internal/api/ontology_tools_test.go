package api

import (
	"context"
	"strings"
	"testing"
)

func sptr(v string) *string { return &v }

// ── upsert (create) ───────────────────────────────────────────────────────────

func TestOntologyUpsert_CreateAllLevels_BookScope(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool) // pre-adopted
	octx := ctxWithUser(f.ownerID)

	_, out, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyUpsertItemIn{
			{Level: "genre", Code: "t2_faction", Name: sptr("Faction")},
			{Level: "kind", Code: "t2_sect", Name: sptr("Sect")},
			{Level: "attribute", Code: "t2_bloodline", Name: sptr("Bloodline"), KindCode: "character", GenreCode: "universal"},
		},
	})
	if err != nil {
		t.Fatalf("upsert create: %v", err)
	}
	if out.Summary.Created != 3 || out.Summary.Updated != 0 || out.Summary.Failed != 0 {
		t.Fatalf("want 3 created, got %+v", out.Summary)
	}
	for _, r := range out.Results {
		if r.Status != "created" || r.Version == "" {
			t.Errorf("bad result: %+v", r)
		}
	}
}

func TestOntologyUpsert_MixedBatch_CreateAndUpdate(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	// seed a kind to update
	_, seeded, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{
		BookID: f.bookID.String(), Level: "kind", Name: "Realm", Code: "t2_realm",
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}

	_, out, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyUpsertItemIn{
			{Level: "kind", Code: "t2_new_kind", Name: sptr("Brand New")},                                     // create
			{Level: "kind", Code: "t2_realm", BaseVersion: seeded.Version, Name: sptr("Realm Renamed")}, // update
		},
	})
	if err != nil {
		t.Fatalf("mixed upsert: %v", err)
	}
	if out.Summary.Created != 1 || out.Summary.Updated != 1 || out.Summary.Failed != 0 {
		t.Fatalf("want 1 created + 1 updated, got %+v", out.Summary)
	}
	var got string
	pool.QueryRow(context.Background(), `SELECT name FROM book_kinds WHERE book_id=$1 AND code='t2_realm'`, f.bookID).Scan(&got)
	if got != "Realm Renamed" {
		t.Errorf("update did not apply: name=%q", got)
	}
}

func TestOntologyUpsert_DuplicateCodeInBatch_Rejected(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	_, _, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyUpsertItemIn{
			{Level: "kind", Code: "t2_dup", Name: sptr("First")},
			{Level: "kind", Code: "t2_dup", Name: sptr("Second")},
		},
	})
	if err == nil || !strings.Contains(err.Error(), "duplicate") {
		t.Fatalf("want duplicate-in-batch rejection, got %v", err)
	}
}

func TestOntologyUpsert_UpdateWhenMissing_And_CreateWhenExists(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	// base_version present but no such row → per-item error, not a batch failure.
	_, out, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyUpsertItemIn{
			{Level: "kind", Code: "t2_ghost", BaseVersion: "2020-01-01T00:00:00Z", Name: sptr("Ghost")},
		},
	})
	if err != nil {
		t.Fatalf("call should succeed with a per-item error: %v", err)
	}
	if out.Summary.Failed != 1 || out.Results[0].Status != "error" {
		t.Fatalf("want a per-item error result, got %+v", out.Results)
	}

	// create when the code already exists → per-item error naming the conflict.
	_, _, err = f.srv.toolBookCreate(octx, nil, bookCreateToolIn{BookID: f.bookID.String(), Level: "kind", Name: "X", Code: "t2_exists"})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	_, out2, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyUpsertItemIn{{Level: "kind", Code: "t2_exists", Name: sptr("Y")}},
	})
	if err != nil {
		t.Fatalf("call should succeed with a per-item error: %v", err)
	}
	if out2.Summary.Failed != 1 || !strings.Contains(out2.Results[0].Error, "already exists") {
		t.Fatalf("want already-exists per-item error, got %+v", out2.Results)
	}
}

func TestOntologyUpsert_UserScope_CreateAndUpdate(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	_, out, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "user",
		Items: []ontologyUpsertItemIn{{Level: "genre", Code: "t2_u_genre", Name: sptr("My Genre")}},
	})
	if err != nil || out.Summary.Created != 1 {
		t.Fatalf("user create: %v %+v", err, out)
	}
	version := out.Results[0].Version

	_, out2, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "user",
		Items: []ontologyUpsertItemIn{{Level: "genre", Code: "t2_u_genre", BaseVersion: version, Name: sptr("Renamed")}},
	})
	if err != nil || out2.Summary.Updated != 1 {
		t.Fatalf("user update: %v %+v", err, out2)
	}
}

// ── delete ─────────────────────────────────────────────────────────────────

func TestOntologyDelete_UserScope_DirectAndIdempotent(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	_, _, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "user", Items: []ontologyUpsertItemIn{{Level: "genre", Code: "t2_u_del", Name: sptr("ToDelete")}},
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}

	_, out, err := f.srv.toolOntologyDelete(octx, nil, ontologyDeleteToolIn{
		Scope: "user", Items: []ontologyDeleteItemIn{{Level: "genre", Code: "t2_u_del"}},
	})
	if err != nil || out.Summary == nil || out.Summary.Trashed != 1 {
		t.Fatalf("direct delete: %v %+v", err, out)
	}
	if out.ConfirmToken != "" {
		t.Errorf("user-scope delete must NOT mint a confirm token: %+v", out)
	}

	// idempotent — deleting again is a no-op, not an error.
	_, out2, err := f.srv.toolOntologyDelete(octx, nil, ontologyDeleteToolIn{
		Scope: "user", Items: []ontologyDeleteItemIn{{Level: "genre", Code: "t2_u_del"}},
	})
	if err != nil || out2.Results[0].Status != "already_trashed" {
		t.Fatalf("re-delete should be idempotent, got %v %+v", err, out2.Results)
	}
}

func TestOntologyDelete_BookScope_MintsOneTokenForBatch(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	_, _, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyUpsertItemIn{
			{Level: "kind", Code: "t2_del_a", Name: sptr("A")},
			{Level: "kind", Code: "t2_del_b", Name: sptr("B")},
		},
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}

	_, out, err := f.srv.toolOntologyDelete(octx, nil, ontologyDeleteToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyDeleteItemIn{{Level: "kind", Code: "t2_del_a"}, {Level: "kind", Code: "t2_del_b"}},
	})
	if err != nil {
		t.Fatalf("book delete propose: %v", err)
	}
	if out.ConfirmToken == "" {
		t.Fatalf("book-scope delete must mint a confirm token: %+v", out)
	}
	if out.Results != nil {
		t.Errorf("book-scope delete must NOT execute directly: %+v", out)
	}
	if len(out.Preview) == 0 {
		t.Errorf("want a non-empty cascade preview")
	}

	// confirm the SINGLE token executes BOTH deletes.
	w := f.confirm(t, out.ConfirmToken)
	if w.Code != 200 {
		t.Fatalf("confirm: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var nA, nB int
	pool.QueryRow(context.Background(), `SELECT count(*) FROM book_kinds WHERE book_id=$1 AND code='t2_del_a' AND deprecated_at IS NULL`, f.bookID).Scan(&nA)
	pool.QueryRow(context.Background(), `SELECT count(*) FROM book_kinds WHERE book_id=$1 AND code='t2_del_b' AND deprecated_at IS NULL`, f.bookID).Scan(&nB)
	if nA != 0 || nB != 0 {
		t.Errorf("both kinds should be soft-deleted: a_live=%d b_live=%d", nA, nB)
	}

	// replay → single-use 422.
	if w := f.confirm(t, out.ConfirmToken); w.Code != 422 {
		t.Errorf("replay: want 422 single-use, got %d", w.Code)
	}
}

func TestOntologyDelete_BookScope_BatchIsIdempotentOnPartialReplay(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	_, _, err := f.srv.toolOntologyUpsert(octx, nil, ontologyUpsertToolIn{
		Scope: "book", BookID: f.bookID.String(),
		Items: []ontologyUpsertItemIn{{Level: "kind", Code: "t2_del_c", Name: sptr("C")}},
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}

	_, out, err := f.srv.toolOntologyDelete(octx, nil, ontologyDeleteToolIn{
		Scope: "book", BookID: f.bookID.String(),
		// one real target + one already-nonexistent code — must not fail the whole mint.
		Items: []ontologyDeleteItemIn{{Level: "kind", Code: "t2_del_c"}, {Level: "kind", Code: "t2_never_existed"}},
	})
	if err != nil {
		t.Fatalf("propose with one missing target: %v", err)
	}
	if out.ConfirmToken == "" {
		t.Fatalf("must still mint a token for the valid item: %+v", out)
	}

	w := f.confirm(t, out.ConfirmToken)
	if w.Code != 200 {
		t.Fatalf("confirm: want 200 (partial batch), got %d (%s)", w.Code, w.Body.String())
	}
	var nC int
	pool.QueryRow(context.Background(), `SELECT count(*) FROM book_kinds WHERE book_id=$1 AND code='t2_del_c' AND deprecated_at IS NULL`, f.bookID).Scan(&nC)
	if nC != 0 {
		t.Errorf("t2_del_c should be deleted despite the sibling missing target: live=%d", nC)
	}
}
