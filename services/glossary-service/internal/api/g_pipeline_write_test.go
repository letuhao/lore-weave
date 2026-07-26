package api

// Pipeline M2 — direct (class-W) write tool guards. glossary_create_chapter_link is
// Edit-gated, entity-in-book guarded, and validates relevance + chapter_id before any
// write. (The happy-path insert shares createChapterLinkCore with the HTTP handler.)
// Requires GLOSSARY_TEST_DB_URL.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestPipelineWriteTool_ChapterLinkGuards(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'cl entity') RETURNING entity_id`,
		f.bookID, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) }) //nolint:errcheck

	book := f.bookID.String()

	// grant gate — a non-grantee is denied
	if _, _, err := f.srv.toolCreateChapterLink(ctxWithUser(uuid.New()), nil,
		createChapterLinkToolIn{BookID: book, EntityID: entityID.String(), ChapterID: uuid.NewString()}); err == nil {
		t.Error("non-grantee must be denied")
	}
	// entity-in-book guard
	if _, _, err := f.srv.toolCreateChapterLink(octx, nil,
		createChapterLinkToolIn{BookID: book, EntityID: uuid.NewString(), ChapterID: uuid.NewString()}); err == nil {
		t.Error("entity not in book must error")
	}
	// invalid chapter_id uuid (rejected before the core)
	if _, _, err := f.srv.toolCreateChapterLink(octx, nil,
		createChapterLinkToolIn{BookID: book, EntityID: entityID.String(), ChapterID: "not-a-uuid"}); err == nil {
		t.Error("invalid chapter_id must error")
	}
	// bad relevance (rejected by the core before any upstream/insert)
	if _, _, err := f.srv.toolCreateChapterLink(octx, nil,
		createChapterLinkToolIn{BookID: book, EntityID: entityID.String(), ChapterID: uuid.NewString(), Relevance: "bogus"}); err == nil {
		t.Error("bad relevance must error")
	}
}

func TestPipelineWriteTool_CreateEvidenceGuards(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	nameAttr := bookAttrID(t, pool, f.bookID, charKind, "name")

	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'ev entity') RETURNING entity_id`,
		f.bookID, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) }) //nolint:errcheck

	var attrValueID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id, attr_def_id, original_language, original_value)
		 VALUES($1,$2,'zh','姜子牙') RETURNING attr_value_id`,
		entityID, nameAttr).Scan(&attrValueID); err != nil {
		t.Fatalf("seed attr value: %v", err)
	}

	book := f.bookID.String()

	// grant gate — a non-grantee is denied
	if _, _, err := f.srv.toolCreateEvidence(ctxWithUser(uuid.New()), nil,
		createEvidenceToolIn{BookID: book, EntityID: entityID.String(), AttrValueID: attrValueID.String(), OriginalText: "x"}); err == nil {
		t.Error("non-grantee must be denied")
	}
	// entity-in-book guard
	if _, _, err := f.srv.toolCreateEvidence(octx, nil,
		createEvidenceToolIn{BookID: book, EntityID: uuid.NewString(), AttrValueID: attrValueID.String(), OriginalText: "x"}); err == nil {
		t.Error("entity not in book must error")
	}
	// attr-value-in-entity guard (random attr value not on this entity)
	if _, _, err := f.srv.toolCreateEvidence(octx, nil,
		createEvidenceToolIn{BookID: book, EntityID: entityID.String(), AttrValueID: uuid.NewString(), OriginalText: "x"}); err == nil {
		t.Error("attr value not on entity must error")
	}
	// bad evidence_type (rejected by the core)
	if _, _, err := f.srv.toolCreateEvidence(octx, nil,
		createEvidenceToolIn{BookID: book, EntityID: entityID.String(), AttrValueID: attrValueID.String(), OriginalText: "x", EvidenceType: "bogus"}); err == nil {
		t.Error("bad evidence_type must error")
	}
	// bad chapter_id uuid (rejected by the core)
	if _, _, err := f.srv.toolCreateEvidence(octx, nil,
		createEvidenceToolIn{BookID: book, EntityID: entityID.String(), AttrValueID: attrValueID.String(), OriginalText: "x", ChapterID: "not-a-uuid"}); err == nil {
		t.Error("bad chapter_id must error")
	}
	// happy path — additive insert succeeds, defaults applied
	_, ev, err := f.srv.toolCreateEvidence(octx, nil,
		createEvidenceToolIn{BookID: book, EntityID: entityID.String(), AttrValueID: attrValueID.String(),
			OriginalText: "他姓姜，名尚", Note: "from ch.1"})
	if err != nil {
		t.Fatalf("happy path: %v", err)
	}
	if ev.EvidenceType != "quote" || ev.OriginalLanguage != "zh" {
		t.Errorf("defaults not applied: type=%q lang=%q", ev.EvidenceType, ev.OriginalLanguage)
	}
	if ev.AttrValueID != attrValueID.String() {
		t.Errorf("attr_value_id mismatch: %s", ev.AttrValueID)
	}
}
