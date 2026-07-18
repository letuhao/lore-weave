package api

// glossary_entity_delete / glossary_entity_restore — Tier-W propose→confirm soft-
// delete of a single glossary entity + its Tier-A direct restore counterpart.
// Added for the real-usage feedback finding: no MCP way to remove a genuinely
// empty/garbage extraction-draft entity (glossary_propose_reassign_kind is the
// wrong tool — there's nothing to classify). Requires GLOSSARY_TEST_DB_URL for
// the DB-backed round-trips; the mint-side guard tests run with no DB.

import (
	"context"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ── mint-side validation (no DB) ──────────────────────────────────────────────

func TestToolProposeEntityDelete_MissingIdentity(t *testing.T) {
	s := &Server{}
	if _, _, err := s.toolProposeEntityDelete(context.Background(), nil,
		entityDeleteToolIn{BookID: uuid.NewString(), EntityID: uuid.NewString()}); err == nil {
		t.Fatal("want missing-identity error")
	}
}

func TestToolEntityRestore_MissingIdentity(t *testing.T) {
	s := &Server{}
	if _, _, err := s.toolEntityRestore(context.Background(), nil,
		entityRestoreToolIn{BookID: uuid.NewString(), EntityID: uuid.NewString()}); err == nil {
		t.Fatal("want missing-identity error")
	}
}

func TestToolProposeEntityDelete_BadIDsRejected(t *testing.T) {
	s := &Server{}
	if _, _, err := s.toolProposeEntityDelete(ctxWithUser(uuid.New()), nil,
		entityDeleteToolIn{BookID: "not-a-uuid", EntityID: uuid.NewString()}); err == nil {
		t.Fatal("want book_id UUID error")
	}
	if _, _, err := s.toolProposeEntityDelete(ctxWithUser(uuid.New()), nil,
		entityDeleteToolIn{BookID: uuid.NewString(), EntityID: "not-a-uuid"}); err == nil {
		t.Fatal("want entity_id UUID error")
	}
}

func TestToolEntityRestore_BadIDsRejected(t *testing.T) {
	s := &Server{}
	if _, _, err := s.toolEntityRestore(ctxWithUser(uuid.New()), nil,
		entityRestoreToolIn{BookID: "not-a-uuid", EntityID: uuid.NewString()}); err == nil {
		t.Fatal("want book_id UUID error")
	}
	if _, _, err := s.toolEntityRestore(ctxWithUser(uuid.New()), nil,
		entityRestoreToolIn{BookID: uuid.NewString(), EntityID: "not-a-uuid"}); err == nil {
		t.Fatal("want entity_id UUID error")
	}
}

// ── DB-backed round-trips ──────────────────────────────────────────────────────

func seedGarbageEntity(t *testing.T, pool *pgxpool.Pool, bookID, kindID uuid.UUID) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	// short_description carries a placeholder (non-empty is DB-enforced) — the
	// "garbage" property under test is no NAME attribute value, no attributes, no
	// chapter links, which is what glossary_entity_delete's preview actually reads.
	if err := pool.QueryRow(context.Background(),
		`INSERT INTO glossary_entities(book_id, kind_id, status, short_description)
		 VALUES($1,$2,'draft','(unclassified draft)') RETURNING entity_id`, bookID, kindID).Scan(&id); err != nil {
		t.Fatalf("seed: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, id) }) //nolint:errcheck
	return id
}

// happy path: propose → preview → confirm actually soft-deletes; a replay is
// rejected as single-use.
func TestEntityDelete_RoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")
	entityID := seedGarbageEntity(t, pool, f.bookID, charKind)

	_, card, err := f.srv.toolProposeEntityDelete(ctxWithUser(f.ownerID), nil,
		entityDeleteToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	if card.ConfirmToken == "" || card.Descriptor != descEntityDelete || !card.Destructive {
		t.Fatalf("bad card: %+v", card)
	}
	if card.Warning != "" {
		t.Errorf("a live entity's delete proposal must not carry the no-op warning, got %q", card.Warning)
	}
	if w := f.preview(t, card.ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("preview: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var deleted bool
	pool.QueryRow(ctx, `SELECT deleted_at IS NOT NULL FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&deleted)
	if !deleted {
		t.Error("entity was not soft-deleted")
	}
	// replay → single-use → 422
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay: want 422, got %d", w.Code)
	}
}

// no-op-on-already-deleted: proposing to delete an entity that is ALREADY
// deleted must still mint (not error) and carry a no-op warning — mirrors the
// glossary_ontology_delete / status_change / reassign_kind audit #11 precedent.
// Confirming it is a clean idempotent 200, not an error.
func TestEntityDelete_NoOpWhenAlreadyDeleted(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")
	entityID := seedGarbageEntity(t, pool, f.bookID, charKind)

	if _, err := pool.Exec(ctx, `UPDATE glossary_entities SET deleted_at=now() WHERE entity_id=$1`, entityID); err != nil {
		t.Fatalf("pre-delete: %v", err)
	}

	_, card, err := f.srv.toolProposeEntityDelete(ctxWithUser(f.ownerID), nil,
		entityDeleteToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("propose on an already-deleted entity must still mint (idempotent), got err: %v", err)
	}
	if card.ConfirmToken == "" {
		t.Fatal("a no-op delete proposal must still mint a valid confirm_token (it is not an error)")
	}
	if card.Warning == "" {
		t.Fatalf("proposing to delete an already-deleted entity must carry a no-op warning, got card=%+v", card)
	}
	if !strings.Contains(card.Warning, "already deleted") {
		t.Errorf("warning should state the entity is already deleted, got %q", card.Warning)
	}
	// confirming is still a clean 200 (idempotent no-op), not an error.
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm of an already-deleted entity: want 200 (idempotent), got %d (%s)", w.Code, w.Body.String())
	}
}

// propose on a nonexistent / wrong-book entity_id is rejected up front (mint-time
// guard, §11 #8) rather than minting a doomed card.
func TestEntityDelete_UnknownEntityRejectedAtPropose(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)

	_, _, err := f.srv.toolProposeEntityDelete(ctxWithUser(f.ownerID), nil,
		entityDeleteToolIn{BookID: f.bookID.String(), EntityID: uuid.NewString()})
	if err == nil {
		t.Fatal("propose on a nonexistent entity must error, not mint a card")
	}
}

// restore round-trip: delete → confirm (real soft-delete) → glossary_entity_restore
// un-deletes it, carries an undo_hint back to glossary_entity_delete, and restoring
// again (already live) is an idempotent no-op.
func TestEntityRestore_RoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")
	entityID := seedGarbageEntity(t, pool, f.bookID, charKind)

	_, card, err := f.srv.toolProposeEntityDelete(ctxWithUser(f.ownerID), nil,
		entityDeleteToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("propose delete: %v", err)
	}
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm delete: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var deleted bool
	pool.QueryRow(ctx, `SELECT deleted_at IS NOT NULL FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&deleted)
	if !deleted {
		t.Fatal("setup: entity was not soft-deleted")
	}

	res, out, err := f.srv.toolEntityRestore(ctxWithUser(f.ownerID), nil,
		entityRestoreToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("restore: %v", err)
	}
	if !out.Restored {
		t.Errorf("restore of a trashed entity must report restored=true, got %+v", out)
	}
	if res == nil || res.Meta == nil {
		t.Fatal("restore result must carry _meta.undo_hint")
	}
	undo, ok := res.Meta["undo_hint"].(map[string]any)
	if !ok || undo["tool"] != "glossary_entity_delete" {
		t.Errorf("undo_hint.tool = %v, want glossary_entity_delete", res.Meta["undo_hint"])
	}
	pool.QueryRow(ctx, `SELECT deleted_at IS NOT NULL FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&deleted)
	if deleted {
		t.Error("entity was not restored (still soft-deleted)")
	}

	// restoring again (already live) is an idempotent no-op, not an error.
	_, out2, err := f.srv.toolEntityRestore(ctxWithUser(f.ownerID), nil,
		entityRestoreToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("re-restore: %v", err)
	}
	if out2.Restored {
		t.Errorf("restoring an already-live entity must report restored=false (no-op), got %+v", out2)
	}
}

// restoring an entity that was never deleted is also an idempotent no-op.
func TestEntityRestore_NoOpWhenNeverDeleted(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	charKind := bookKindID(t, pool, f.bookID, "character")
	entityID := seedGarbageEntity(t, pool, f.bookID, charKind)

	_, out, err := f.srv.toolEntityRestore(ctxWithUser(f.ownerID), nil,
		entityRestoreToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("restore of a never-deleted entity should not error: %v", err)
	}
	if out.Restored {
		t.Errorf("restoring a live entity must report restored=false (no-op), got %+v", out)
	}
}

// the confirm card's preview surfaces the entity's name + a real attribute/
// chapter-link count — the "would be lost" evidence a human reviews before
// confirming a delete of a supposedly-empty entity.
func TestEntityDelete_PreviewShowsCounts(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	charKind := bookKindID(t, pool, f.bookID, "character")
	entityID := seedGarbageEntity(t, pool, f.bookID, charKind)

	nameAttr := bookAttrID(t, pool, f.bookID, charKind, "name")
	if _, err := pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id, attr_def_id, original_language, original_value)
		 VALUES($1,$2,'en','Test Name')`, entityID, nameAttr); err != nil {
		t.Fatalf("seed attr: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO chapter_entity_links(entity_id, chapter_id, chapter_title, relevance)
		 VALUES($1,$2,'Test Chapter','appears')`, entityID, uuid.New()); err != nil {
		t.Fatalf("seed chapter link: %v", err)
	}

	_, card, err := f.srv.toolProposeEntityDelete(ctxWithUser(f.ownerID), nil,
		entityDeleteToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	var foundName, foundAttrs, foundLinks bool
	for _, row := range card.PreviewRows {
		switch {
		case row.Label == "name" && row.Value == "Test Name":
			foundName = true
		case row.Label == "attributes" && row.Value == "1":
			foundAttrs = true
		case row.Label == "chapter links" && row.Value == "1":
			foundLinks = true
		}
	}
	if !foundName {
		t.Errorf("preview must show the entity's name, got %+v", card.PreviewRows)
	}
	if !foundAttrs {
		t.Errorf("preview must show the attribute count, got %+v", card.PreviewRows)
	}
	if !foundLinks {
		t.Errorf("preview must show the chapter-link count, got %+v", card.PreviewRows)
	}
}

// an unnamed, attribute-less, link-less entity — the exact "garbage draft" use
// case from the field report — previews as empty, not blank/missing rows.
func TestEntityDelete_PreviewOfGenuinelyEmptyEntity(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	charKind := bookKindID(t, pool, f.bookID, "character")
	entityID := seedGarbageEntity(t, pool, f.bookID, charKind)

	_, card, err := f.srv.toolProposeEntityDelete(ctxWithUser(f.ownerID), nil,
		entityDeleteToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	var foundUnnamed, foundZeroAttrs, foundZeroLinks bool
	for _, row := range card.PreviewRows {
		switch {
		case row.Label == "name" && row.Value == "(none)":
			foundUnnamed = true
		case row.Label == "attributes" && row.Value == "0":
			foundZeroAttrs = true
		case row.Label == "chapter links" && row.Value == "0":
			foundZeroLinks = true
		}
	}
	if !foundUnnamed || !foundZeroAttrs || !foundZeroLinks {
		t.Errorf("empty-entity preview should show (none)/0/0, got %+v", card.PreviewRows)
	}
}
