package api

// G-U1 — revert a Book override back to its parent tier. Proves: an edited adopted row
// reverts to the System parent's CURRENT value (HTTP + the MCP propose→confirm path,
// single-use); a book-native row is NOT revertable (404 / mint error); a row whose parent
// was soft-deleted (G-C8) is not revertable; a non-Manage caller is denied. Requires
// GLOSSARY_TEST_DB_URL.

import (
	"context"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

func TestBookRevert_RoundTripAndGuards(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	ctx := context.Background()
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	octx := ctxWithUser(owner)
	base := "/v1/glossary/books/" + book.String()

	// Throwaway System standards with run-unique codes (shared test DB hygiene).
	gc := "revg_" + book.String()[:8]
	kc := "revk_" + book.String()[:8]
	var sgID, skID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_genres (code,name,content_hash) VALUES ($1,'RevG','g0') RETURNING genre_id`, gc).Scan(&sgID); err != nil {
		t.Fatalf("seed system genre: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO system_kinds (code,name,description) VALUES ($1,'RevK','desc') RETURNING kind_id`, kc).Scan(&skID); err != nil {
		t.Fatalf("seed system kind: %v", err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO system_kind_genres (kind_id,genre_id) VALUES ($1,$2)`, skID, sgID); err != nil {
		t.Fatalf("seed link: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO system_attributes (kind_id,genre_id,code,name,description,field_type,is_required,options,content_hash)
		 VALUES ($1,$2,'attr1','SysName','d','text',false,NULL,'h0')`, skID, sgID); err != nil {
		t.Fatalf("seed system attr: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gc) //nolint:errcheck
		pool.Exec(context.Background(), `DELETE FROM system_kinds  WHERE code=$1`, kc) //nolint:errcheck
	})

	// Adopt → system-sourced book rows.
	if err := srv.adoptBookOntologyCore(ctx, book, owner, []string{gc}, []string{kc}); err != nil {
		t.Fatalf("adopt: %v", err)
	}
	bKindID := bookKindID(t, pool, book, kc)
	bAttrID := bookAttrID(t, pool, book, bKindID, "attr1")

	revertURL := func(id uuid.UUID) string {
		return base + "/ontology/attributes/" + id.String() + "/revert"
	}
	nameOf := func(id uuid.UUID) string {
		var n string
		pool.QueryRow(ctx, `SELECT name FROM book_attributes WHERE attr_id=$1`, id).Scan(&n) //nolint:errcheck
		return n
	}

	// ── HTTP revert round-trip: local edit → revert → parent value restored ──
	if _, err := pool.Exec(ctx, `UPDATE book_attributes SET name='LocalEdit' WHERE attr_id=$1`, bAttrID); err != nil {
		t.Fatalf("diverge: %v", err)
	}
	if rw := ukReq(t, srv, http.MethodPost, revertURL(bAttrID), owner.String(), ""); rw.Code != http.StatusOK {
		t.Fatalf("revert: want 200, got %d (%s)", rw.Code, rw.Body.String())
	}
	if got := nameOf(bAttrID); got != "SysName" {
		t.Fatalf("revert must restore the parent value, got %q", got)
	}

	// ── book-native row is NOT revertable (404) ──
	var nativeID uuid.UUID
	if err := pool.QueryRow(ctx, `
		INSERT INTO book_attributes (book_id, kind_id, genre_id, code, name, field_type)
		SELECT $1, $2, (SELECT genre_id FROM book_genres WHERE book_id=$1 AND code=$3), 'native1', 'Native', 'text'
		RETURNING attr_id`, book, bKindID, gc).Scan(&nativeID); err != nil {
		t.Fatalf("insert book-native attr: %v", err)
	}
	if nrw := ukReq(t, srv, http.MethodPost, revertURL(nativeID), owner.String(), ""); nrw.Code != http.StatusNotFound {
		t.Errorf("revert book-native: want 404 NOT_REVERTABLE, got %d (%s)", nrw.Code, nrw.Body.String())
	}

	// ── Manage gate: a stranger is denied ──
	if srw := ukReq(t, srv, http.MethodPost, revertURL(bAttrID), uuid.NewString(), ""); srw.Code == http.StatusOK {
		t.Errorf("stranger revert must be denied, got 200")
	}

	// ── MCP propose → confirm round-trip + single-use ──
	if _, err := pool.Exec(ctx, `UPDATE book_attributes SET name='LocalEdit2' WHERE attr_id=$1`, bAttrID); err != nil {
		t.Fatalf("diverge2: %v", err)
	}
	_, card, err := srv.toolBookRevert(octx, nil, bookRevertToolIn{
		BookID: book.String(), Level: "attribute", Code: "attr1", KindCode: kc, GenreCode: gc})
	if err != nil {
		t.Fatalf("propose revert: %v", err)
	}
	if asCard(card).Descriptor != descBookRevert || asCard(card).Destructive || asCard(card).ConfirmToken == "" {
		t.Fatalf("bad revert card: %+v", card)
	}
	body := `{"confirm_token":"` + asCard(card).ConfirmToken + `"}`
	if pv := ukReq(t, srv, http.MethodPost, "/v1/glossary/actions/preview", owner.String(), body); pv.Code != http.StatusOK {
		t.Fatalf("preview revert: want 200, got %d (%s)", pv.Code, pv.Body.String())
	}
	if cw := ukReq(t, srv, http.MethodPost, "/v1/glossary/actions/confirm", owner.String(), body); cw.Code != http.StatusOK {
		t.Fatalf("confirm revert: want 200, got %d (%s)", cw.Code, cw.Body.String())
	}
	if got := nameOf(bAttrID); got != "SysName" {
		t.Errorf("confirm revert should restore the parent value, got %q", got)
	}
	if rp := ukReq(t, srv, http.MethodPost, "/v1/glossary/actions/confirm", owner.String(), body); rp.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay revert: want 422 single-use, got %d", rp.Code)
	}

	// ── MCP rejects a book-native revert at mint ──
	if _, _, nerr := srv.toolBookRevert(octx, nil, bookRevertToolIn{
		BookID: book.String(), Level: "attribute", Code: "native1", KindCode: kc, GenreCode: gc}); nerr == nil {
		t.Error("propose revert of a book-native attr should error at mint")
	}

	// ── parent soft-deleted (G-C8) → not revertable ──
	if _, err := pool.Exec(ctx, `UPDATE system_attributes SET deprecated_at=now() WHERE kind_id=$1 AND code='attr1'`, skID); err != nil {
		t.Fatalf("soft-delete parent: %v", err)
	}
	if _, err := pool.Exec(ctx, `UPDATE book_attributes SET name='LocalEdit3' WHERE attr_id=$1`, bAttrID); err != nil {
		t.Fatalf("diverge3: %v", err)
	}
	if gw := ukReq(t, srv, http.MethodPost, revertURL(bAttrID), owner.String(), ""); gw.Code != http.StatusNotFound {
		t.Errorf("revert with a deprecated parent: want 404, got %d (%s)", gw.Code, gw.Body.String())
	}
}
