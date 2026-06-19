package api

// G5 — book Sync diff/apply. Requires GLOSSARY_TEST_DB_URL.
// Proves: (1) a fresh adopt reports no pending updates; (2) editing a System source
// surfaces it as update_available with the new values in `theirs`; (3) take_theirs
// overwrites the book row + clears the prompt; keep_mine silences it without changing
// the book row; (4) a retired source reads as source_retired and is left untouched;
// (5) the View/Manage grant gates; (6) the user-tier edit paths refresh content_hash
// so a real PATCH surfaces through Sync (D-GKA-HASH-REFRESH, the milestone VERIFY).

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func syncAvailable(t *testing.T, srv *Server, book, user uuid.UUID) syncAvailableResp {
	t.Helper()
	w := ukReq(t, srv, http.MethodGet, "/v1/glossary/books/"+book.String()+"/sync/available", user.String(), "")
	if w.Code != http.StatusOK {
		t.Fatalf("sync/available: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var out syncAvailableResp
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode available: %v", err)
	}
	return out
}

func findUpdate(ups []syncUpdateItem, entity, code string) (syncUpdateItem, bool) {
	for _, u := range ups {
		if u.Entity == entity && u.Code == code {
			return u, true
		}
	}
	return syncUpdateItem{}, false
}

func TestBookSync_DiffApplyAllChoices(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	ctx := context.Background()
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()

	// Throwaway System standards with codes UNIQUE to this run, so editing them never
	// touches the seeded vocabulary (shared test DB — mutating 'fantasy'/'character'
	// would poison every other adopt test and make this one non-idempotent). Covers the
	// system-tier branch of the diff/apply SQL; the user-tier branch is covered by the
	// other G5 tests. Cleaned up at the end.
	gc := "syncg_" + book.String()[:8]
	kc := "synck_" + book.String()[:8]
	var sgID, skID uuid.UUID
	mustExec := func(q string, args ...any) {
		if _, err := pool.Exec(ctx, q, args...); err != nil {
			t.Fatalf("seed/edit system standard: %v", err)
		}
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_genres (code,name,content_hash) VALUES ($1,'SyncG','g0') RETURNING genre_id`,
		gc).Scan(&sgID); err != nil {
		t.Fatalf("seed system genre: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_kinds (code,name,description) VALUES ($1,'SyncK','kind desc 0') RETURNING kind_id`,
		kc).Scan(&skID); err != nil {
		t.Fatalf("seed system kind: %v", err)
	}
	mustExec(`INSERT INTO system_kind_genres (kind_id,genre_id) VALUES ($1,$2)`, skID, sgID)
	// Rich attribute so take_theirs has a full surface (name+desc+field_type+is_required+options) to overwrite.
	mustExec(`INSERT INTO system_attributes (kind_id,genre_id,code,name,description,field_type,is_required,options,content_hash)
	          VALUES ($1,$2,'attr1','SyncA','attr desc 0','text',false,NULL,'h0')`, skID, sgID)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gc) //nolint:errcheck
		pool.Exec(context.Background(), `DELETE FROM system_kinds  WHERE code=$1`, kc) //nolint:errcheck
	})

	// Adopt the throwaway standards → system-sourced book rows.
	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["`+gc+`"],"kinds":["`+kc+`"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	// A fresh adopt is fully in sync.
	if up := syncAvailable(t, srv, book, owner); len(up.Updates) != 0 {
		t.Fatalf("fresh adopt: want 0 updates, got %d (%+v)", len(up.Updates), up.Updates)
	}

	bAttrID := bookAttrID(t, pool, book, bookKindID(t, pool, book, kc), "attr1").String()

	// Edit all three System standards across the FULL semantic surface (kind hash is
	// recomputed live from name|description; genre/attr carry content_hash columns).
	mustExec(`UPDATE system_genres SET name='SyncG EDITED', content_hash='g1' WHERE code=$1`, gc)
	mustExec(`UPDATE system_kinds  SET name='SyncK EDITED', description='kind desc 1' WHERE code=$1`, kc)
	mustExec(`UPDATE system_attributes SET name='SyncA EDITED', description='attr desc 1', field_type='select',
	          is_required=true, options=ARRAY['x','y'], content_hash='h1' WHERE kind_id=$1 AND code='attr1'`, skID)

	// All three surface as update_available; `theirs` previews the new values (incl. the
	// attribute's full surface, locking the diff projection).
	up := syncAvailable(t, srv, book, owner)
	gUp, ok := findUpdate(up.Updates, "genre", gc)
	if !ok || gUp.Status != syncStatusUpdate || gUp.Theirs == nil || gUp.Theirs.Name != "SyncG EDITED" {
		t.Fatalf("genre update: got %+v (theirs=%+v)", gUp, gUp.Theirs)
	}
	kUp, ok := findUpdate(up.Updates, "kind", kc)
	if !ok || kUp.Status != syncStatusUpdate || kUp.Theirs == nil ||
		kUp.Theirs.Name != "SyncK EDITED" || derefStr(kUp.Theirs.Description) != "kind desc 1" {
		t.Fatalf("kind update: got %+v (theirs=%+v)", kUp, kUp.Theirs)
	}
	aUp, ok := findUpdate(up.Updates, "attribute", "attr1")
	if !ok || aUp.Status != syncStatusUpdate || aUp.Theirs == nil ||
		aUp.Theirs.Name != "SyncA EDITED" || derefStr(aUp.Theirs.FieldType) != "select" ||
		aUp.Theirs.IsRequired == nil || !*aUp.Theirs.IsRequired ||
		len(aUp.Theirs.Options) != 2 || aUp.Theirs.Options[0] != "x" || aUp.Theirs.Options[1] != "y" {
		t.Fatalf("attr update: got %+v (theirs=%+v)", aUp, aUp.Theirs)
	}

	// Apply: take_theirs for kind + attribute (overwrite the full surface), keep_mine for
	// genre (bump hash only, leave the book value).
	applyBody := `{"items":[
		{"entity":"genre","id":"` + gUp.ID + `","choice":"keep_mine"},
		{"entity":"kind","id":"` + kUp.ID + `","choice":"take_theirs"},
		{"entity":"attribute","id":"` + bAttrID + `","choice":"take_theirs"}
	]}`
	aw := ukReq(t, srv, http.MethodPost, base+"/sync/apply", owner.String(), applyBody)
	if aw.Code != http.StatusOK {
		t.Fatalf("sync/apply: want 200, got %d (%s)", aw.Code, aw.Body.String())
	}
	var ar syncApplyResp
	if err := json.Unmarshal(aw.Body.Bytes(), &ar); err != nil {
		t.Fatalf("decode apply: %v", err)
	}
	if ar.Applied != 3 {
		t.Fatalf("apply: want 3 applied, got %d (%+v)", ar.Applied, ar.Results)
	}

	// keep_mine left the genre name untouched.
	var gName string
	if err := pool.QueryRow(ctx, `SELECT name FROM book_genres WHERE genre_id=$1`, gUp.ID).Scan(&gName); err != nil {
		t.Fatalf("read book genre: %v", err)
	}
	if gName != "SyncG" {
		t.Fatalf("genre keep_mine should NOT overwrite name, got %q", gName)
	}
	// take_theirs pulled the kind's name + description.
	var kName, kDesc string
	if err := pool.QueryRow(ctx, `SELECT name, description FROM book_kinds WHERE book_kind_id=$1`, kUp.ID).Scan(&kName, &kDesc); err != nil {
		t.Fatalf("read book kind: %v", err)
	}
	if kName != "SyncK EDITED" || kDesc != "kind desc 1" {
		t.Fatalf("kind take_theirs: want name='SyncK EDITED' desc='kind desc 1', got %q / %q", kName, kDesc)
	}
	// take_theirs pulled the attribute's FULL surface (not just name).
	var aName, aDesc, aFtype string
	var aReq bool
	var aOpts []string
	if err := pool.QueryRow(ctx,
		`SELECT name, description, field_type, is_required, options FROM book_attributes WHERE attr_id=$1`,
		bAttrID).Scan(&aName, &aDesc, &aFtype, &aReq, &aOpts); err != nil {
		t.Fatalf("read book attr: %v", err)
	}
	if aName != "SyncA EDITED" || aDesc != "attr desc 1" || aFtype != "select" || !aReq ||
		len(aOpts) != 2 || aOpts[0] != "x" || aOpts[1] != "y" {
		t.Fatalf("attr take_theirs full surface: got name=%q desc=%q ftype=%q req=%v opts=%v",
			aName, aDesc, aFtype, aReq, aOpts)
	}

	// Everything is now reconciled — no pending updates remain (keep_mine bumped the
	// genre's source_hash to the upstream hash, silencing it).
	if up := syncAvailable(t, srv, book, owner); len(up.Updates) != 0 {
		t.Fatalf("post-apply: want 0 updates, got %d (%+v)", len(up.Updates), up.Updates)
	}
}

func TestBookSync_SourceRetired(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	ctx := context.Background()
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()

	// A user-tier genre the caller customized, sharing the 'fantasy' code so adopt
	// resolves the book's fantasy genre to the user row (source_ref 'user:<id>').
	var ugID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO user_genres (owner_user_id, code, name, content_hash) VALUES ($1,'fantasy','My Fantasy', md5('fantasy|My Fantasy')) RETURNING genre_id`,
		owner).Scan(&ugID); err != nil {
		t.Fatalf("seed user genre: %v", err)
	}
	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["fantasy"],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var srcRef, bookGenreID string
	if err := pool.QueryRow(ctx,
		`SELECT genre_id::text, source_ref FROM book_genres WHERE book_id=$1 AND code='fantasy'`,
		book).Scan(&bookGenreID, &srcRef); err != nil {
		t.Fatalf("read book fantasy genre: %v", err)
	}
	if !strings.HasPrefix(srcRef, "user:") {
		t.Fatalf("fantasy genre should be user-sourced, got %q", srcRef)
	}

	// Retire the source: soft-delete the user genre. Sync must report source_retired
	// (the book copy stays frozen), with no `theirs`.
	if _, err := pool.Exec(ctx, `UPDATE user_genres SET deleted_at=now() WHERE genre_id=$1`, ugID); err != nil {
		t.Fatalf("soft-delete user genre: %v", err)
	}
	up := syncAvailable(t, srv, book, owner)
	gUp, ok := findUpdate(up.Updates, "genre", "fantasy")
	if !ok || gUp.Status != syncStatusRetired || gUp.Theirs != nil {
		t.Fatalf("retired source: want source_retired + nil theirs, got %+v", gUp)
	}

	// take_theirs on a retired source is a no-op: result source_retired, row unchanged.
	aw := ukReq(t, srv, http.MethodPost, base+"/sync/apply", owner.String(),
		`{"items":[{"entity":"genre","id":"`+bookGenreID+`","choice":"take_theirs"}]}`)
	if aw.Code != http.StatusOK {
		t.Fatalf("apply: want 200, got %d (%s)", aw.Code, aw.Body.String())
	}
	var ar syncApplyResp
	if err := json.Unmarshal(aw.Body.Bytes(), &ar); err != nil {
		t.Fatalf("decode apply: %v", err)
	}
	if ar.Applied != 0 || len(ar.Results) != 1 || ar.Results[0].Result != syncStatusRetired {
		t.Fatalf("retired apply: want 0 applied + source_retired, got %+v", ar)
	}
	var name string
	if err := pool.QueryRow(ctx, `SELECT name FROM book_genres WHERE genre_id=$1`, bookGenreID).Scan(&name); err != nil {
		t.Fatalf("read book genre: %v", err)
	}
	if name != "My Fantasy" {
		t.Fatalf("retired source should leave the book row frozen, got name %q", name)
	}
}

// TestBookSync_UserEditRefreshesHash is the milestone VERIFY: editing a user-tier
// standard through the REAL handler bumps content_hash, so a book that adopted it sees
// update_available (without the D-GKA-HASH-REFRESH fix the hash never moves).
func TestBookSync_UserEditRefreshesHash(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()

	// Caller's user-tier genre (created via the real handler → content_hash set).
	cw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-genres", owner.String(),
		`{"code":"fantasy","name":"My Fantasy"}`)
	if cw.Code != http.StatusCreated {
		t.Fatalf("create user genre: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var created genreResp
	if err := json.Unmarshal(cw.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode created genre: %v", err)
	}

	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["fantasy"],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if up := syncAvailable(t, srv, book, owner); len(up.Updates) != 0 {
		t.Fatalf("fresh adopt of user genre: want 0 updates, got %d (%+v)", len(up.Updates), up.Updates)
	}

	// Edit the user genre name via the real PATCH handler. This MUST recompute
	// content_hash; otherwise Sync stays blind to the edit.
	pw := ukReq(t, srv, http.MethodPatch, "/v1/glossary/user-genres/"+created.GenreID, owner.String(),
		`{"name":"My Fantasy v2"}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("patch user genre: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}
	up := syncAvailable(t, srv, book, owner)
	gUp, ok := findUpdate(up.Updates, "genre", "fantasy")
	if !ok || gUp.Status != syncStatusUpdate || gUp.Theirs == nil || gUp.Theirs.Name != "My Fantasy v2" {
		t.Fatalf("user edit not surfaced by sync (D-GKA-HASH-REFRESH): got %+v (theirs=%+v)", gUp, gUp.Theirs)
	}
}

// TestPatchUserAttribute_RefreshesContentHash locks the attribute-tier half of
// D-GKA-HASH-REFRESH directly: a PATCH must recompute content_hash to the
// attrContentHash of the post-update fields (else Sync stays blind to user-attr edits).
func TestPatchUserAttribute_RefreshesContentHash(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	ctx := context.Background()
	owner := uuid.New()
	srv := newAdoptServer(t, pool, uuid.New(), owner) // book unused; user-attr routes are not book-scoped

	var ukID, ugID, aID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO user_kinds (owner_user_id,code,name) VALUES ($1,'hrk','HRK') RETURNING user_kind_id`, owner).Scan(&ukID); err != nil {
		t.Fatalf("seed user kind: %v", err)
	}
	if err := pool.QueryRow(ctx, `INSERT INTO user_genres (owner_user_id,code,name,content_hash) VALUES ($1,'hrg','HRG',md5('hrg|HRG')) RETURNING genre_id`, owner).Scan(&ugID); err != nil {
		t.Fatalf("seed user genre: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO user_attributes (owner_user_id,kind_id,genre_id,code,name,content_hash) VALUES ($1,$2,$3,'attr','Attr','stale-hash') RETURNING attr_id`,
		owner, ukID, ugID).Scan(&aID); err != nil {
		t.Fatalf("seed user attr: %v", err)
	}

	pw := ukReq(t, srv, http.MethodPatch, "/v1/glossary/user-attributes/"+aID.String(), owner.String(), `{"name":"Attr v2"}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("patch user attr: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}

	var got string
	if err := pool.QueryRow(ctx, `SELECT content_hash FROM user_attributes WHERE attr_id=$1`, aID).Scan(&got); err != nil {
		t.Fatalf("read content_hash: %v", err)
	}
	want := attrContentHash("attr", "Attr v2", nil, "text", false, []string{})
	if got != want {
		t.Fatalf("content_hash not refreshed on patch: got %q want %q (stale-hash means the refresh did not run)", got, want)
	}
}

// TestBookSync_GrantGates — available needs View, apply needs Manage; a stranger
// (no grant in the mock projection) is denied on both.
func TestBookSync_GrantGates(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()
	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["fantasy"],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	stranger := uuid.New()
	if w := ukReq(t, srv, http.MethodGet, base+"/sync/available", stranger.String(), ""); w.Code != http.StatusForbidden {
		t.Fatalf("stranger available: want 403, got %d", w.Code)
	}
	if w := ukReq(t, srv, http.MethodPost, base+"/sync/apply", stranger.String(),
		`{"items":[{"entity":"genre","id":"`+uuid.NewString()+`","choice":"keep_mine"}]}`); w.Code != http.StatusForbidden {
		t.Fatalf("stranger apply: want 403, got %d", w.Code)
	}
}
