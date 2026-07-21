package api

// M0 (agent write auto-gate spec) — book_update_meta is now a Tier-W PROPOSE, not
// a Tier-A write. Calling the tool MUST NOT mutate the book; it returns a server-
// built DIFF CARD. The write happens only on confirm, guarded by optimistic
// concurrency (base_version = updated_at). Gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

func TestMCP_BookUpdateMeta_ProposesDiff_NoWrite_ThenConfirmApplies_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,description) VALUES($1,'Old Title','old desc') RETURNING id`,
		owner).Scan(&bookID); err != nil {
		t.Fatalf("seed: %v", err)
	}
	s.resolveBook = ownerResolver(owner)
	tctx := identityCtxForTest(t, owner)

	newDesc := "In a drowning port city, a glassmaker's daughter can save or shatter the harbor."
	_, card, err := s.toolBookUpdateMeta(tctx, nil, bookUpdateMetaIn{
		BookID: bookID.String(), Description: &newDesc,
	})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	// (1) it returns a book.meta DIFF card with a confirm token — not a write result.
	if card.ConfirmToken == "" || card.Descriptor != descBookMeta || card.Domain != "book" {
		t.Fatalf("want a book.meta diff card, got %+v", card)
	}
	if len(card.Changes) != 1 || card.Changes[0].Target != "description" ||
		card.Changes[0].OldValue != "old desc" || card.Changes[0].NewValue != newDesc {
		t.Fatalf("diff changes wrong: %+v", card.Changes)
	}
	// (2) NOTHING is written at propose time.
	var descNow string
	if err := pool.QueryRow(ctx, `SELECT description FROM books WHERE id=$1`, bookID).Scan(&descNow); err != nil {
		t.Fatalf("read-back: %v", err)
	}
	if descNow != "old desc" {
		t.Fatalf("propose must NOT write; description already = %q", descNow)
	}
	// (3) confirm → the edit is applied.
	rr := confirmReq(t, s, owner, card.ConfirmToken)
	if rr.Code != http.StatusOK {
		t.Fatalf("confirm = %d; body=%s", rr.Code, rr.Body.String())
	}
	if err := pool.QueryRow(ctx, `SELECT description FROM books WHERE id=$1`, bookID).Scan(&descNow); err != nil {
		t.Fatalf("read-back 2: %v", err)
	}
	if descNow != newDesc {
		t.Fatalf("confirm must apply the edit; description = %q", descNow)
	}
}

// OCC (I7): a diff proposed against one version must NOT clobber a book edited since.
func TestMCP_BookUpdateMeta_StaleVersion_Conflicts_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,description) VALUES($1,'T','v1 desc') RETURNING id`,
		owner).Scan(&bookID); err != nil {
		t.Fatalf("seed: %v", err)
	}
	s.resolveBook = ownerResolver(owner)
	tctx := identityCtxForTest(t, owner)

	d := "proposed against v1"
	_, card, err := s.toolBookUpdateMeta(tctx, nil, bookUpdateMetaIn{BookID: bookID.String(), Description: &d})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	// A concurrent edit bumps updated_at AFTER the diff was proposed.
	if _, err := pool.Exec(ctx, `UPDATE books SET description='v2 concurrent', updated_at=now() WHERE id=$1`, bookID); err != nil {
		t.Fatalf("concurrent edit: %v", err)
	}
	rr := confirmReq(t, s, owner, card.ConfirmToken)
	if rr.Code == http.StatusOK {
		t.Fatalf("stale confirm must NOT succeed (would clobber the concurrent edit)")
	}
	var descNow string
	_ = pool.QueryRow(ctx, `SELECT description FROM books WHERE id=$1`, bookID).Scan(&descNow)
	if descNow != "v2 concurrent" {
		t.Fatalf("the concurrent edit must survive; description = %q", descNow)
	}
}
