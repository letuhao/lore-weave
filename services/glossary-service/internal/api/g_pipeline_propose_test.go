package api

// Pipeline M2 — class-C propose tools + confirm effects. Validates the mint-side guards
// (identity, status/loser validation, ownership) and two full propose→confirm round-trips
// (status_change reversible; merge destructive+journaled), plus the reassign data-loss
// preview. Requires GLOSSARY_TEST_DB_URL.

import (
	"context"
	"encoding/json"
	stderrors "errors"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// ── mint-side validation (no DB) ──────────────────────────────────────────────

// validEntityStatus is the single source of truth reused by effectStatusChange,
// toolProposeStatusChange, and (post-consolidation) both entity_handler.go PATCH
// and bulk-status call sites. "rejected" is a 4th valid value added so the triage
// workflow (glossary_list_ai_suggestions' "not yet user-rejected" inbox language)
// has a real terminal status distinct from active/inactive/draft.
func TestValidEntityStatus(t *testing.T) {
	cases := map[string]bool{
		"active": true, "inactive": true, "draft": true, "rejected": true,
		"bogus": false, "": false, "Active": false, "REJECTED": false,
	}
	for s, want := range cases {
		if got := validEntityStatus(s); got != want {
			t.Errorf("validEntityStatus(%q) = %v, want %v", s, got, want)
		}
	}
}

func TestPipelinePropose_InputGuards(t *testing.T) {
	s := &Server{}
	book := uuid.NewString()

	// missing identity
	if _, _, err := s.toolProposeStatusChange(context.Background(), nil, struct {
		BookID    string   `json:"book_id" jsonschema:"the book (UUID)"`
		Status    string   `json:"status" jsonschema:"active | inactive | draft"`
		EntityIDs []string `json:"entity_ids" jsonschema:"the entities to change (UUIDs)"`
	}{BookID: book, Status: "active", EntityIDs: []string{uuid.NewString()}}); err == nil {
		t.Error("status_change: missing identity must error")
	}
	// bad status
	if _, _, err := s.toolProposeStatusChange(ctxWithUser(uuid.New()), nil, struct {
		BookID    string   `json:"book_id" jsonschema:"the book (UUID)"`
		Status    string   `json:"status" jsonschema:"active | inactive | draft"`
		EntityIDs []string `json:"entity_ids" jsonschema:"the entities to change (UUIDs)"`
	}{BookID: book, Status: "bogus", EntityIDs: []string{uuid.NewString()}}); err == nil {
		t.Error("status_change: bad status must error")
	}
	// merge: no losers distinct from winner
	w := uuid.NewString()
	if _, _, err := s.toolProposeMerge(ctxWithUser(uuid.New()), nil, struct {
		BookID   string   `json:"book_id" jsonschema:"the book (UUID)"`
		WinnerID string   `json:"winner_id" jsonschema:"the entity to KEEP (UUID)"`
		LoserIDs []string `json:"loser_ids" jsonschema:"the entities to merge away (UUIDs; same kind as the winner)"`
	}{BookID: book, WinnerID: w, LoserIDs: []string{w}}); err == nil {
		t.Error("merge: winner-only loser set must error")
	}
}

// ── tenancy: the extracted cores are book-scoped ──────────────────────────────
// The confirm effects re-bind opaque param entity-ids to claims.BookID, but the actual
// enforcement is the cores' WHERE book_id / entity-in-book filters. Guard them directly
// so a future refactor that drops the scoping is caught (the security-critical property
// the propose→confirm round-trips don't exercise — they stay within one book).
func TestPipelineCores_BookScoped(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")

	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, short_description)
		 VALUES($1,$2,'draft','scoped') RETURNING entity_id`, f.bookID, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) }) //nolint:errcheck

	otherBook := uuid.New() // a book the entity does NOT belong to

	// status_change: a wrong-book scope must update 0 and leave the entity untouched.
	n, err := f.srv.bulkSetEntityStatusCore(ctx, otherBook, "active", []uuid.UUID{entityID})
	if err != nil {
		t.Fatalf("bulkSetEntityStatusCore: %v", err)
	}
	if n != 0 {
		t.Errorf("cross-book status update touched %d rows (want 0)", n)
	}
	var status string
	pool.QueryRow(ctx, `SELECT status FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&status)
	if status != "draft" {
		t.Errorf("entity status mutated cross-book: %q", status)
	}

	// reassign_kind: an entity not in the addressed book is rejected (not silently moved).
	if err := f.srv.reassignEntityKindCore(ctx, otherBook, entityID, charKind); !errorsIs(err, errReassignKindNotFound, errReassignEntityNotFound) {
		t.Errorf("cross-book reassign: want a not-found sentinel, got %v", err)
	}

	// restore_revision core is entity-scoped (revision WHERE entity_id); a random entity
	// has no such revision → not-found (the effect adds the book binding on top).
	if _, err := f.srv.restoreEntityRevisionCore(ctx, f.bookID, uuid.New(), f.ownerID, uuid.New()); !errorsIs(err, errRevisionNotFound) {
		t.Errorf("restore of a foreign/absent revision: want errRevisionNotFound, got %v", err)
	}
}

// errorsIs reports whether err matches any of the targets.
func errorsIs(err error, targets ...error) bool {
	for _, t := range targets {
		if stderrors.Is(err, t) {
			return true
		}
	}
	return false
}

// ── status_change round-trip (reversible) ─────────────────────────────────────

func TestPipelinePropose_StatusChangeRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")

	seed := func() uuid.UUID {
		var id uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id, kind_id, status, short_description)
			 VALUES($1,$2,'draft','sc') RETURNING entity_id`, f.bookID, charKind).Scan(&id); err != nil {
			t.Fatalf("seed: %v", err)
		}
		t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, id) }) //nolint:errcheck
		return id
	}
	e1, e2 := seed(), seed()

	_, card, err := f.srv.toolProposeStatusChange(ctxWithUser(f.ownerID), nil, struct {
		BookID    string   `json:"book_id" jsonschema:"the book (UUID)"`
		Status    string   `json:"status" jsonschema:"active | inactive | draft"`
		EntityIDs []string `json:"entity_ids" jsonschema:"the entities to change (UUIDs)"`
	}{BookID: f.bookID.String(), Status: "active", EntityIDs: []string{e1.String(), e2.String()}})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	if asCard(card).ConfirmToken == "" || asCard(card).Descriptor != descStatusChange {
		t.Fatalf("bad card: %+v", card)
	}
	// preview is non-consuming
	if w := f.preview(t, asCard(card).ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("preview: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if w := f.confirm(t, asCard(card).ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var active int
	pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE entity_id = ANY($1::uuid[]) AND status='active'`,
		[]uuid.UUID{e1, e2}).Scan(&active)
	if active != 2 {
		t.Errorf("status not applied: %d/2 active", active)
	}
	// replay → single-use → 422
	if w := f.confirm(t, asCard(card).ConfirmToken); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay: want 422, got %d", w.Code)
	}
}

// External MCP discoverability audit #11 — effectStatusChange's UPDATE has no
// `status <> target` guard, so it always reports every live id as "updated" even when
// they ALL already have the target status. A status_change proposing the status an
// entity already has must still mint (not an error) but must carry a warning.
func TestPipelinePropose_StatusChangeNoOpWarnsWhenAlreadyAtTarget(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")

	var id uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, short_description)
		 VALUES($1,$2,'active','sc-noop') RETURNING entity_id`, f.bookID, charKind).Scan(&id); err != nil {
		t.Fatalf("seed: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, id) }) //nolint:errcheck

	_, card, err := f.srv.toolProposeStatusChange(ctxWithUser(f.ownerID), nil, struct {
		BookID    string   `json:"book_id" jsonschema:"the book (UUID)"`
		Status    string   `json:"status" jsonschema:"active | inactive | draft"`
		EntityIDs []string `json:"entity_ids" jsonschema:"the entities to change (UUIDs)"`
	}{BookID: f.bookID.String(), Status: "active", EntityIDs: []string{id.String()}})
	if err != nil {
		t.Fatalf("propose status_change to the entity's current status: %v", err)
	}
	if asCard(card).ConfirmToken == "" {
		t.Fatal("a no-op status_change must still mint a valid confirm_token (it is not an error)")
	}
	if asCard(card).Warning == "" {
		t.Fatalf("a status_change to the CURRENT status must carry a no-op warning, got card=%+v", card)
	}
	if !strings.Contains(asCard(card).Warning, "already have status") {
		t.Errorf("warning should state entities already have that status, got %q", asCard(card).Warning)
	}
}

// A status_change that actually flips entities to a NEW status must not carry the
// no-op warning (regression guard on TestPipelinePropose_StatusChangeRoundTrip's
// happy path).
func TestPipelinePropose_StatusChangeRealChangeCarriesNoWarning(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")

	var id uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, short_description)
		 VALUES($1,$2,'draft','sc-real') RETURNING entity_id`, f.bookID, charKind).Scan(&id); err != nil {
		t.Fatalf("seed: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, id) }) //nolint:errcheck

	_, card, err := f.srv.toolProposeStatusChange(ctxWithUser(f.ownerID), nil, struct {
		BookID    string   `json:"book_id" jsonschema:"the book (UUID)"`
		Status    string   `json:"status" jsonschema:"active | inactive | draft"`
		EntityIDs []string `json:"entity_ids" jsonschema:"the entities to change (UUIDs)"`
	}{BookID: f.bookID.String(), Status: "active", EntityIDs: []string{id.String()}})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	if asCard(card).Warning != "" {
		t.Errorf("a real status change must not carry the no-op warning, got %q", asCard(card).Warning)
	}
}

// ── merge round-trip (destructive, journaled) ─────────────────────────────────

func TestPipelinePropose_MergeRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")

	seed := func(desc string) uuid.UUID {
		var id uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id, kind_id, short_description)
			 VALUES($1,$2,$3) RETURNING entity_id`, f.bookID, charKind, desc).Scan(&id); err != nil {
			t.Fatalf("seed: %v", err)
		}
		t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, id) }) //nolint:errcheck
		return id
	}
	winner, loser := seed("winner"), seed("loser")
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM merge_journal WHERE winner_entity_id=$1`, winner) }) //nolint:errcheck

	_, card, err := f.srv.toolProposeMerge(ctxWithUser(f.ownerID), nil, struct {
		BookID   string   `json:"book_id" jsonschema:"the book (UUID)"`
		WinnerID string   `json:"winner_id" jsonschema:"the entity to KEEP (UUID)"`
		LoserIDs []string `json:"loser_ids" jsonschema:"the entities to merge away (UUIDs; same kind as the winner)"`
	}{BookID: f.bookID.String(), WinnerID: winner.String(), LoserIDs: []string{loser.String()}})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	if asCard(card).Descriptor != descMerge || !asCard(card).Destructive {
		t.Fatalf("bad card: %+v", card)
	}
	if w := f.confirm(t, asCard(card).ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var loserDeleted bool
	pool.QueryRow(ctx, `SELECT deleted_at IS NOT NULL FROM glossary_entities WHERE entity_id=$1`, loser).Scan(&loserDeleted)
	if !loserDeleted {
		t.Error("loser was not soft-deleted by the merge")
	}
	// a journal row (the revert handle) was written
	var journals int
	pool.QueryRow(ctx, `SELECT count(*) FROM merge_journal WHERE winner_entity_id=$1 AND loser_entity_id=$2 AND status='merged'`,
		winner, loser).Scan(&journals)
	if journals != 1 {
		t.Errorf("merge journal not written: %d", journals)
	}
	// replay → 422
	if w := f.confirm(t, asCard(card).ConfirmToken); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay: want 422, got %d", w.Code)
	}
}

// ── reassign_kind preview surfaces dropped attributes (data loss) ─────────────

func TestPipelinePropose_ReassignPreviewsDroppedAttrs(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()

	// Seed an entity under 'character' carrying a character-only attribute that has no
	// counterpart under the target kind 'location' → reassign would drop it.
	charKind := bookKindID(t, pool, f.bookID, "character")
	locKind := bookKindID(t, pool, f.bookID, "location")

	var charOnlyAttr string
	// pick any character attr whose code is absent from 'location'
	err := pool.QueryRow(ctx, `
		SELECT ba.code FROM book_attributes ba
		WHERE ba.book_id=$1 AND ba.kind_id=$2 AND ba.code NOT IN ('name','term')
		  AND NOT EXISTS (SELECT 1 FROM book_attributes x WHERE x.book_id=$1 AND x.kind_id=$3 AND x.code = ba.code)
		LIMIT 1`, f.bookID, charKind, locKind).Scan(&charOnlyAttr)
	if err != nil {
		t.Skipf("no character-only attribute to exercise drop preview: %v", err)
	}
	attrID := bookAttrID(t, pool, f.bookID, charKind, charOnlyAttr)

	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'re') RETURNING entity_id`,
		f.bookID, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) }) //nolint:errcheck
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id, attr_def_id, original_language, original_value)
		 VALUES($1,$2,'zh','val')`, entityID, attrID); err != nil {
		t.Fatalf("seed attr value: %v", err)
	}

	_, card, err := f.srv.toolProposeReassignKind(ctxWithUser(f.ownerID), nil, struct {
		BookID   string `json:"book_id" jsonschema:"the book (UUID)"`
		EntityID string `json:"entity_id" jsonschema:"the entity to move (UUID)"`
		KindCode string `json:"kind_code" jsonschema:"the target kind's code (see glossary_book_ontology_read)"`
	}{BookID: f.bookID.String(), EntityID: entityID.String(), KindCode: "location"})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	if asCard(card).Descriptor != descReassignKind || !asCard(card).Destructive {
		t.Fatalf("bad card: %+v", card)
	}
	// the at-mint card must call out the dropped-attr data loss
	found := false
	for _, row := range asCard(card).PreviewRows {
		if row.Label == "attributes dropped (DATA LOSS)" && row.Value != "0" {
			found = true
		}
	}
	if !found {
		b, _ := json.Marshal(asCard(card).PreviewRows)
		t.Errorf("reassign card must surface dropped attrs: %s", b)
	}
	// regression guard: a real kind change must NOT carry the same-kind no-op warning.
	if asCard(card).Warning != "" {
		t.Errorf("a real reassign to a DIFFERENT kind must not carry the no-op warning, got %q", asCard(card).Warning)
	}
}

// External MCP discoverability audit #11 — reassigning an entity to the kind it is
// ALREADY on is a genuine no-op (rekeyEntityToKind's re-key/drop UPDATEs all filter
// `kind_id <> target`, so none of them touch a row). Must still mint (not an error)
// but must carry a warning.
func TestPipelinePropose_ReassignSameKindWarnsOnNoOp(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")

	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'same-kind') RETURNING entity_id`,
		f.bookID, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) }) //nolint:errcheck

	_, card, err := f.srv.toolProposeReassignKind(ctxWithUser(f.ownerID), nil, struct {
		BookID   string `json:"book_id" jsonschema:"the book (UUID)"`
		EntityID string `json:"entity_id" jsonschema:"the entity to move (UUID)"`
		KindCode string `json:"kind_code" jsonschema:"the target kind's code (see glossary_book_ontology_read)"`
	}{BookID: f.bookID.String(), EntityID: entityID.String(), KindCode: "character"}) // same kind it's already on
	if err != nil {
		t.Fatalf("propose reassign to the entity's current kind: %v", err)
	}
	if asCard(card).ConfirmToken == "" {
		t.Fatal("a same-kind reassign must still mint a valid confirm_token (it is not an error)")
	}
	if asCard(card).Warning == "" {
		t.Fatalf("a reassign to the entity's CURRENT kind must carry a no-op warning, got card=%+v", card)
	}
	if !strings.Contains(asCard(card).Warning, "already kind") {
		t.Errorf("warning should state the entity is already that kind, got %q", asCard(card).Warning)
	}
}
