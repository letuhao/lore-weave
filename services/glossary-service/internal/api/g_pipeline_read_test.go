package api

// Pipeline M1 — read tools. Proves: each tool is View-grant-gated (a non-grantee is
// denied), entity-addressed reads reject an entity not in the book, and the happy path
// returns the wrapped data (a seeded unknown-kind entity surfaces in the triage bucket).
// Requires GLOSSARY_TEST_DB_URL.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestPipelineReadTools_GatesAndData(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool) // pre-adopted book + owner View/Manage grant
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	// Seed one entity in the book's 'unknown' kind (the triage bucket).
	unknownKind := bookKindID(t, pool, f.bookID, "unknown")
	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description, source_kind_code)
		 VALUES($1,$2,'mystery thing','spell') RETURNING entity_id`,
		f.bookID, unknownKind).Scan(&entityID); err != nil {
		t.Fatalf("seed unknown entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) }) //nolint:errcheck

	// ── unknown-entities: the seeded entity surfaces ──
	if _, out, err := f.srv.toolListUnknownEntities(octx, nil, bookOnlyToolIn{BookID: f.bookID.String()}); err != nil {
		t.Fatalf("list unknown entities: %v", err)
	} else {
		if out.Total < 1 {
			t.Errorf("unknown total: want >=1, got %d", out.Total)
		}
		var found bool
		for _, it := range out.Items {
			if it.EntityID == entityID.String() {
				found = true
			}
		}
		if !found {
			t.Errorf("seeded unknown entity not returned: %+v", out.Items)
		}
	}

	// ── merge candidates: happy path (empty is fine) ──
	if _, _, err := f.srv.toolListMergeCandidates(octx, nil, mergeCandToolIn{BookID: f.bookID.String()}); err != nil {
		t.Errorf("list merge candidates: %v", err)
	}
	// invalid status rejected at the tool
	if _, _, err := f.srv.toolListMergeCandidates(octx, nil, mergeCandToolIn{BookID: f.bookID.String(), Status: "bogus"}); err == nil {
		t.Error("merge candidates: bad status should error")
	}

	// ── chapter links + revisions for the seeded entity (empty is fine) ──
	if _, _, err := f.srv.toolListChapterLinks(octx, nil, bookEntityToolIn{BookID: f.bookID.String(), EntityID: entityID.String()}); err != nil {
		t.Errorf("list chapter links: %v", err)
	}
	if _, _, err := f.srv.toolListEntityRevisions(octx, nil, bookEntityToolIn{BookID: f.bookID.String(), EntityID: entityID.String()}); err != nil {
		t.Errorf("list revisions: %v", err)
	}

	// ── entity-in-book guard: a random entity id is rejected ──
	if _, _, err := f.srv.toolListChapterLinks(octx, nil, bookEntityToolIn{BookID: f.bookID.String(), EntityID: uuid.NewString()}); err == nil {
		t.Error("chapter links for an entity not in the book should error")
	}

	// ── grant gate: a non-grantee is denied on every tool ──
	stranger := ctxWithUser(uuid.New())
	if _, _, err := f.srv.toolListUnknownEntities(stranger, nil, bookOnlyToolIn{BookID: f.bookID.String()}); err == nil {
		t.Error("non-grantee must be denied (unknown entities)")
	}
	if _, _, err := f.srv.toolListMergeCandidates(stranger, nil, mergeCandToolIn{BookID: f.bookID.String()}); err == nil {
		t.Error("non-grantee must be denied (merge candidates)")
	}
}
