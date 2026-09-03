package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// T2 — book Sync MCP tools. Requires GLOSSARY_TEST_DB_URL.
// Drives the C-class apply round-trip (propose tool → preview → confirm endpoint →
// effect) and proves: the available diff round-trips through the tool; sync_apply is
// destructive + single-use; mint-time validation rejects malformed items; a non-Manage
// caller is denied. Uses throwaway System standards with run-unique codes so editing
// them never poisons the shared seeded vocabulary (the g5_sync_test discipline).

func TestSyncTool_AvailableApplyRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool) // pre-adopted book + confirm routes
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	gc := "synct_g_" + f.bookID.String()[:8]
	kc := "synct_k_" + f.bookID.String()[:8]
	var sgID, skID uuid.UUID
	mustExec := func(q string, args ...any) {
		if _, err := pool.Exec(ctx, q, args...); err != nil {
			t.Fatalf("seed/edit system standard: %v", err)
		}
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_genres (code,name,content_hash) VALUES ($1,'SyncTG','g0') RETURNING genre_id`,
		gc).Scan(&sgID); err != nil {
		t.Fatalf("seed system genre: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_kinds (code,name,description) VALUES ($1,'SyncTK','desc 0') RETURNING kind_id`,
		kc).Scan(&skID); err != nil {
		t.Fatalf("seed system kind: %v", err)
	}
	mustExec(`INSERT INTO system_kind_genres (kind_id,genre_id) VALUES ($1,$2)`, skID, sgID)
	mustExec(`INSERT INTO system_attributes (kind_id,genre_id,code,name,description,field_type,is_required,options,content_hash)
	          VALUES ($1,$2,'attr1','SyncTA','a 0','text',false,NULL,'h0')`, skID, sgID)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gc) //nolint:errcheck
		pool.Exec(context.Background(), `DELETE FROM system_kinds  WHERE code=$1`, kc) //nolint:errcheck
	})

	// Adopt the throwaway standards via the shared core (no HTTP) → system-sourced rows.
	if err := f.srv.adoptBookOntologyCore(ctx, f.bookID, f.ownerID, []string{gc}, []string{kc}); err != nil {
		t.Fatalf("adopt drifted standards: %v", err)
	}
	// Fresh adopt → nothing pending.
	if _, up, err := f.srv.toolBookSyncAvailable(octx, nil, syncAvailableToolIn{BookID: f.bookID.String()}); err != nil || len(up.Updates) != 0 {
		t.Fatalf("fresh adopt: want 0 updates, got %d (%v)", len(up.Updates), err)
	}

	// Drift all three sources.
	mustExec(`UPDATE system_genres SET name='SyncTG E', content_hash='g1' WHERE code=$1`, gc)
	mustExec(`UPDATE system_kinds  SET name='SyncTK E', description='desc 1' WHERE code=$1`, kc)
	mustExec(`UPDATE system_attributes SET name='SyncTA E', content_hash='h1' WHERE kind_id=$1 AND code='attr1'`, skID)

	_, up, err := f.srv.toolBookSyncAvailable(octx, nil, syncAvailableToolIn{BookID: f.bookID.String()})
	if err != nil {
		t.Fatalf("sync_available: %v", err)
	}
	gUp, ok1 := findUpdate(up.Updates, "genre", gc)
	kUp, ok2 := findUpdate(up.Updates, "kind", kc)
	aUp, ok3 := findUpdate(up.Updates, "attribute", "attr1")
	if !ok1 || !ok2 || !ok3 {
		t.Fatalf("expected genre+kind+attr updates, got %+v", up.Updates)
	}

	// Propose the apply: take_theirs for kind+attr, keep_mine for genre.
	items := []syncApplyItemToolIn{
		{Entity: "genre", ID: gUp.ID, Choice: "keep_mine"},
		{Entity: "kind", ID: kUp.ID, Choice: "take_theirs"},
		{Entity: "attribute", ID: aUp.ID, Choice: "take_theirs"},
	}
	_, card, err := f.srv.toolBookSyncApply(octx, nil, syncApplyToolIn{BookID: f.bookID.String(), Items: items})
	if err != nil {
		t.Fatalf("propose sync_apply: %v", err)
	}
	if asCard(card).Descriptor != descSyncApply || !asCard(card).Destructive || asCard(card).ConfirmToken == "" {
		t.Fatalf("bad sync_apply card: %+v", card)
	}

	// preview (non-consuming) re-renders counts from current state.
	if w := f.preview(t, asCard(card).ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("preview: want 200, got %d (%s)", w.Code, w.Body.String())
	} else {
		var pv actionPreview
		json.Unmarshal(w.Body.Bytes(), &pv)
		if pv.Descriptor != descSyncApply || len(pv.PreviewRows) == 0 {
			t.Errorf("sync preview should enumerate counts: %+v", pv)
		}
	}

	// confirm → applies the set.
	if w := f.confirm(t, asCard(card).ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm sync_apply: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	// take_theirs on the kind overwrote its name in the book.
	var kn string
	pool.QueryRow(ctx, `SELECT name FROM book_kinds WHERE book_id=$1 AND code=$2`, f.bookID, kc).Scan(&kn)
	if kn != "SyncTK E" {
		t.Errorf("kind take_theirs did not overwrite: name=%q", kn)
	}
	// replay → single-use 422.
	if w := f.confirm(t, asCard(card).ConfirmToken); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay sync_apply: want 422 single-use, got %d", w.Code)
	}
}

// Mint-time validation (§11 #8): malformed items reject before a card is shown.
func TestSyncTool_ApplyMintValidation(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	if _, _, err := f.srv.toolBookSyncApply(octx, nil, syncApplyToolIn{BookID: f.bookID.String()}); err == nil {
		t.Error("empty items must be rejected")
	}
	bad := []syncApplyToolIn{
		{BookID: f.bookID.String(), Items: []syncApplyItemToolIn{{Entity: "bogus", ID: uuid.NewString(), Choice: "keep_mine"}}},
		{BookID: f.bookID.String(), Items: []syncApplyItemToolIn{{Entity: "kind", ID: uuid.NewString(), Choice: "nope"}}},
		{BookID: f.bookID.String(), Items: []syncApplyItemToolIn{{Entity: "kind", ID: "not-a-uuid", Choice: "take_theirs"}}},
	}
	for i, in := range bad {
		if _, _, err := f.srv.toolBookSyncApply(octx, nil, in); err == nil {
			t.Errorf("bad items[%d] must be rejected at mint", i)
		}
	}
}

// External MCP discoverability audit #11 — applySyncRow only affects a row whose
// recorded source is STILL LIVE; a retired source matches nothing regardless of
// take_theirs/keep_mine. If EVERY proposed item's source has retired, sync_apply
// must still mint (it's not an error) but must carry a warning.
func TestSyncTool_ApplyAllRetiredWarnsOnNoOp(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	gc := "synct_ret_g_" + f.bookID.String()[:8]
	var sgID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_genres (code,name,content_hash) VALUES ($1,'SyncRetG','g0') RETURNING genre_id`,
		gc).Scan(&sgID); err != nil {
		t.Fatalf("seed system genre: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gc) }) //nolint:errcheck

	if err := f.srv.adoptBookOntologyCore(ctx, f.bookID, f.ownerID, []string{gc}, nil); err != nil {
		t.Fatalf("adopt: %v", err)
	}
	// Retire the source AFTER adopt — the book row stays frozen, source now resolves gone.
	if _, err := pool.Exec(ctx, `UPDATE system_genres SET deprecated_at=now() WHERE code=$1`, gc); err != nil {
		t.Fatalf("retire source: %v", err)
	}

	var bookGenreID string
	if err := pool.QueryRow(ctx, `SELECT genre_id::text FROM book_genres WHERE book_id=$1 AND code=$2`, f.bookID, gc).Scan(&bookGenreID); err != nil {
		t.Fatalf("resolve book genre row: %v", err)
	}

	_, card, err := f.srv.toolBookSyncApply(octx, nil, syncApplyToolIn{
		BookID: f.bookID.String(),
		Items:  []syncApplyItemToolIn{{Entity: "genre", ID: bookGenreID, Choice: "keep_mine"}},
	})
	if err != nil {
		t.Fatalf("propose sync_apply on a retired source: %v", err)
	}
	if asCard(card).ConfirmToken == "" {
		t.Fatal("an all-retired sync_apply must still mint a valid confirm_token (it is not an error)")
	}
	if asCard(card).Warning == "" {
		t.Fatalf("an all-retired sync_apply must carry a no-op warning, got card=%+v", card)
	}
	if !strings.Contains(asCard(card).Warning, "live source") {
		t.Errorf("warning should mention the missing live source, got %q", asCard(card).Warning)
	}
}

// A sync_apply whose item still has a LIVE source must NOT carry the no-op warning,
// even for a keep_mine choice (keep_mine still bumps source_hash — a real effect).
func TestSyncTool_ApplyWithLiveSourceCarriesNoWarning(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	gc := "synct_live_g_" + f.bookID.String()[:8]
	var sgID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_genres (code,name,content_hash) VALUES ($1,'SyncLiveG','g0') RETURNING genre_id`,
		gc).Scan(&sgID); err != nil {
		t.Fatalf("seed system genre: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gc) }) //nolint:errcheck

	if err := f.srv.adoptBookOntologyCore(ctx, f.bookID, f.ownerID, []string{gc}, nil); err != nil {
		t.Fatalf("adopt: %v", err)
	}
	pool.Exec(ctx, `UPDATE system_genres SET name='SyncLiveG E', content_hash='g1' WHERE code=$1`, gc) //nolint:errcheck

	var bookGenreID string
	if err := pool.QueryRow(ctx, `SELECT genre_id::text FROM book_genres WHERE book_id=$1 AND code=$2`, f.bookID, gc).Scan(&bookGenreID); err != nil {
		t.Fatalf("resolve book genre row: %v", err)
	}

	_, card, err := f.srv.toolBookSyncApply(octx, nil, syncApplyToolIn{
		BookID: f.bookID.String(),
		Items:  []syncApplyItemToolIn{{Entity: "genre", ID: bookGenreID, Choice: "keep_mine"}},
	})
	if err != nil {
		t.Fatalf("propose sync_apply: %v", err)
	}
	if asCard(card).Warning != "" {
		t.Errorf("a sync_apply with a live source must not carry the no-op warning, got %q", asCard(card).Warning)
	}
}

// A non-Manage caller can neither read the diff nor propose an apply.
func TestSyncTool_NonGranteeDenied(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	stranger := ctxWithUser(uuid.New())

	if _, _, err := f.srv.toolBookSyncAvailable(stranger, nil, syncAvailableToolIn{BookID: f.bookID.String()}); err == nil {
		t.Error("non-grantee sync_available must be denied")
	}
	if _, _, err := f.srv.toolBookSyncApply(stranger, nil, syncApplyToolIn{
		BookID: f.bookID.String(),
		Items:  []syncApplyItemToolIn{{Entity: "kind", ID: uuid.NewString(), Choice: "take_theirs"}},
	}); err == nil {
		t.Error("non-grantee sync_apply must be denied")
	}
}

// 🔴 MINT-TIME VALIDATION STOPPED AT THE SHAPE OF AN ID, so a Tier-W card could be minted for
// rows that are not available updates at all. Measured 2026-08-24 over MCP against the deployed
// tool: an id that exists nowhere, a book with ZERO available updates, and book A's row applied
// against book B ALL minted a card. Each row on that card decides whether the author's own value
// is overwritten, so this is approve-then-fail on a destructive write.
//
// The control arm matters as much as the three refusals: a row that IS available must still mint,
// or the check has simply broken the tool.
func TestSyncTool_ApplyRejectsRowsThatAreNotAvailableUpdates(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	a := newActionFixture(t, pool)
	b := newActionFixture(t, pool)
	octxA := ctxWithUser(a.ownerID)
	octxB := ctxWithUser(b.ownerID)

	// A divergence, scoped to book A's OWN adopted rows: source_hash is the book's record of
	// what it adopted, so staling it makes the upstream row differ without touching any shared
	// standard. This is the same per-book seed the toolloop fixture uses.
	stale := func(bookID uuid.UUID) {
		t.Helper()
		if _, err := pool.Exec(ctx,
			`UPDATE book_kinds SET source_hash='STALE-TEST-HASH'
			   WHERE book_id=$1 AND source_ref IS NOT NULL`, bookID); err != nil {
			t.Fatalf("seed divergence: %v", err)
		}
	}
	stale(a.bookID)

	avail, err := a.srv.syncKindsAvailable(ctx, a.bookID, a.ownerID)
	if err != nil {
		t.Fatalf("available: %v", err)
	}
	if len(avail) == 0 {
		t.Fatal("the fixture has no available update, so this test would prove nothing")
	}
	realRow := avail[0].ID

	item := func(id string) []syncApplyItemToolIn {
		return []syncApplyItemToolIn{{Entity: "kind", ID: id, Choice: "take_theirs"}}
	}

	// 🔴 ASSERT THE REASON, NOT MERELY THAT IT FAILED. With the check disabled this assertion
	// still passed — something else in the mint path refuses an unknown id on a book that HAS
	// updates — so "err != nil" would have credited this check with a refusal it did not make.
	// The message is what distinguishes them.
	_, _, err = a.srv.toolBookSyncApply(octxA, nil,
		syncApplyToolIn{BookID: a.bookID.String(), Items: item(uuid.NewString())})
	if err == nil {
		t.Error("an id that is not an available update must be rejected at mint")
	} else if !strings.Contains(err.Error(), "not an available update") {
		t.Errorf("rejected for the wrong reason (this check did not fire): %v", err)
	}

	// Book B is UP TO DATE — nothing is available, so nothing may be proposed for it.
	if _, _, err := b.srv.toolBookSyncApply(octxB, nil,
		syncApplyToolIn{BookID: b.bookID.String(), Items: item(uuid.NewString())}); err == nil {
		t.Error("a book with zero available updates must be rejected at mint, not carded")
	}

	// Book A's REAL row, offered against book B: well-formed, live, and not book B's business.
	if _, _, err := b.srv.toolBookSyncApply(octxB, nil,
		syncApplyToolIn{BookID: b.bookID.String(), Items: item(realRow)}); err == nil {
		t.Error("another book's sync row must be rejected at mint")
	}

	// 🔴 THE CONTROL RUNS LAST, AND THE ORDER IS LOAD-BEARING. sync_apply is single-use, so a
	// card minted for the control changes what a LATER mint on the same book does — with the
	// control first and the guard disabled, the unknown-id assertion passed because the second
	// mint failed for an unrelated reason, crediting this check with a refusal it never made.
	// Refusals first, against untouched state; the control after them.
	if _, _, err := a.srv.toolBookSyncApply(octxA, nil,
		syncApplyToolIn{BookID: a.bookID.String(), Items: item(realRow)}); err != nil {
		t.Fatalf("a genuinely available row must still mint a card: %v", err)
	}
}
