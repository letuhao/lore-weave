package api

import (
	"context"
	"net/http"
	"testing"
)

// F3b — glossary_propose_new_kind carries the kind's defining attributes, created
// ATOMICALLY with the kind on one confirm. Collapses the fragile
// propose-kind→approve→propose-each-attr→approve chain into one approval.

func TestCreateKind_WithAttributes_Atomic(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	desc := "The vampire's specific vulnerabilities."
	k, err := f.srv.createKindFromParams(ctx, f.bookID, kindCreateParams{
		Code: "qa_vampire", Name: "Vampire",
		Attributes: []kindAttrSpec{
			{Code: "weaknesses", Name: "Weaknesses", FieldType: "textarea", Description: &desc},
			{Code: "bloodline", Name: "Bloodline", FieldType: "text"},
			{Code: "name", Name: "Dup"}, // auto-seeded → skipped
		},
	})
	if err != nil {
		t.Fatalf("create kind+attrs: %v", err)
	}
	// returned set = name (seeded) + weaknesses + bloodline; the 'name' dup is skipped.
	if len(k.Attributes) != 3 {
		t.Fatalf("returned attrs = %d, want 3 (name + 2)", len(k.Attributes))
	}
	var n int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM book_attributes a JOIN book_kinds bk ON bk.book_kind_id=a.kind_id
		 WHERE bk.book_id=$1 AND bk.code='qa_vampire'`, f.bookID).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 3 {
		t.Fatalf("DB attr count = %d, want 3", n)
	}
	// The description persisted (this is the whole point — extraction reads it).
	var got *string
	if err := pool.QueryRow(ctx,
		`SELECT a.description FROM book_attributes a JOIN book_kinds bk ON bk.book_kind_id=a.kind_id
		 WHERE bk.book_id=$1 AND bk.code='qa_vampire' AND a.code='weaknesses'`, f.bookID).Scan(&got); err != nil {
		t.Fatalf("read desc: %v", err)
	}
	if got == nil || *got != desc {
		t.Fatalf("weaknesses description = %v, want %q", got, desc)
	}
}

func TestProposeKindWithAttributes_RoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	_, card, err := f.srv.toolProposeNewKind(ctxWithUser(f.ownerID), nil, proposeKindToolIn{
		BookID: f.bookID.String(), Code: "qa_were", Name: "Werewolf",
		Attributes: []proposeKindAttrIn{
			{Code: "triggers", Name: "Transformation Triggers", FieldType: "textarea",
				Description: "What causes the werewolf to transform (full moon, rage, …)."},
		},
	})
	if err != nil {
		t.Fatalf("propose kind+attrs: %v", err)
	}
	if asCard(card).ConfirmToken == "" || asCard(card).Descriptor != descSchemaCreateKind {
		t.Fatalf("bad card: %+v", card)
	}
	// The confirm-card preview enumerates the attribute (so the human sees it).
	foundAttr := false
	for _, r := range asCard(card).PreviewRows {
		if r.Value == "triggers" {
			foundAttr = true
		}
	}
	if !foundAttr {
		t.Fatalf("attribute not surfaced in preview rows: %+v", asCard(card).PreviewRows)
	}
	// Confirm → kind + attribute created in one shot.
	if w := f.confirm(t, asCard(card).ConfirmToken); w.Code != http.StatusCreated {
		t.Fatalf("confirm kind+attrs: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM book_attributes a JOIN book_kinds bk ON bk.book_kind_id=a.kind_id
		 WHERE bk.book_id=$1 AND bk.code='qa_were' AND a.code='triggers'`, f.bookID).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 1 {
		t.Fatalf("triggers attr not created via the confirm round-trip, count=%d", n)
	}
}
