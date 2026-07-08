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

	// ── entity evidence (empty is fine) + entity-in-book guard ──
	if _, _, err := f.srv.toolGetEntityEvidence(octx, nil, bookEntityToolIn{BookID: f.bookID.String(), EntityID: entityID.String()}); err != nil {
		t.Errorf("get entity evidence: %v", err)
	}
	if _, _, err := f.srv.toolGetEntityEvidence(octx, nil, bookEntityToolIn{BookID: f.bookID.String(), EntityID: uuid.NewString()}); err == nil {
		t.Error("entity evidence for an entity not in the book should error")
	}

	// ── AI suggestions: a seeded ai-suggested entity surfaces; an ai-rejected one does not ──
	var suggestID, rejectedID uuid.UUID
	charKind := bookKindID(t, pool, f.bookID, "character")
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, tags, short_description)
		 VALUES($1,$2,'draft','{ai-suggested}','pending') RETURNING entity_id`,
		f.bookID, charKind).Scan(&suggestID); err != nil {
		t.Fatalf("seed ai-suggested: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, tags, short_description)
		 VALUES($1,$2,'inactive','{ai-suggested,ai-rejected}','tombstoned') RETURNING entity_id`,
		f.bookID, charKind).Scan(&rejectedID); err != nil {
		t.Fatalf("seed ai-rejected: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id = ANY($1::uuid[])`, []uuid.UUID{suggestID, rejectedID}) //nolint:errcheck
	})
	if _, out, err := f.srv.toolListAISuggestions(octx, nil, bookOnlyToolIn{BookID: f.bookID.String()}); err != nil {
		t.Fatalf("list ai suggestions: %v", err)
	} else {
		seen := map[string]bool{}
		for _, it := range out.Items {
			seen[it.EntityID] = true
		}
		if !seen[suggestID.String()] {
			t.Error("ai-suggested entity must surface in the inbox")
		}
		if seen[rejectedID.String()] {
			t.Error("ai-rejected (tombstoned) entity must NOT surface")
		}
	}

	// ── grant gate: a non-grantee is denied on every tool ──
	stranger := ctxWithUser(uuid.New())
	if _, _, err := f.srv.toolListUnknownEntities(stranger, nil, bookOnlyToolIn{BookID: f.bookID.String()}); err == nil {
		t.Error("non-grantee must be denied (unknown entities)")
	}
	if _, _, err := f.srv.toolListMergeCandidates(stranger, nil, mergeCandToolIn{BookID: f.bookID.String()}); err == nil {
		t.Error("non-grantee must be denied (merge candidates)")
	}
	if _, _, err := f.srv.toolListAISuggestions(stranger, nil, bookOnlyToolIn{BookID: f.bookID.String()}); err == nil {
		t.Error("non-grantee must be denied (ai suggestions)")
	}
	if _, _, err := f.srv.toolGetEntityEvidence(stranger, nil, bookEntityToolIn{BookID: f.bookID.String(), EntityID: entityID.String()}); err == nil {
		t.Error("non-grantee must be denied (entity evidence)")
	}
}

// 2026-07-08 real-usage feedback ("the inboxes never drain") — glossary_list_unknown_entities
// used to return every entity regardless of status, so triaging (setting an entity to
// active/inactive) never removed it from the NEXT call's results. Confirms: default (no
// status arg) surfaces only 'draft' rows; an explicit status narrows to exactly that;
// 'all' restores the old status-blind behavior; a bogus value is rejected.
func TestListUnknownEntities_StatusFilterDrainsOnceTriaged(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)
	unknownKind := bookKindID(t, pool, f.bookID, "unknown")

	var draftID, activeID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, short_description, source_kind_code)
		 VALUES($1,$2,'draft','still pending','spell') RETURNING entity_id`,
		f.bookID, unknownKind).Scan(&draftID); err != nil {
		t.Fatalf("seed draft unknown entity: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, short_description, source_kind_code)
		 VALUES($1,$2,'active','already triaged','spell') RETURNING entity_id`,
		f.bookID, unknownKind).Scan(&activeID); err != nil {
		t.Fatalf("seed already-active unknown entity: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id = ANY($1::uuid[])`, []uuid.UUID{draftID, activeID}) //nolint:errcheck
	})

	// Default: only the still-pending draft surfaces — the already-triaged one has drained.
	_, out, err := f.srv.toolListUnknownEntities(octx, nil, bookOnlyToolIn{BookID: f.bookID.String()})
	if err != nil {
		t.Fatalf("default list: %v", err)
	}
	seen := map[string]bool{}
	for _, it := range out.Items {
		seen[it.EntityID] = true
	}
	if !seen[draftID.String()] {
		t.Error("default (draft) view must surface the still-pending entity")
	}
	if seen[activeID.String()] {
		t.Error("default (draft) view must NOT surface the already-triaged entity")
	}

	// status="all" restores the old status-blind behavior — both surface.
	_, outAll, err := f.srv.toolListUnknownEntities(octx, nil, bookOnlyToolIn{BookID: f.bookID.String(), Status: "all"})
	if err != nil {
		t.Fatalf("status=all list: %v", err)
	}
	seenAll := map[string]bool{}
	for _, it := range outAll.Items {
		seenAll[it.EntityID] = true
	}
	if !seenAll[draftID.String()] || !seenAll[activeID.String()] {
		t.Errorf("status=all must surface both entities, got %+v", outAll.Items)
	}

	// An explicit status narrows to exactly that bucket.
	_, outActive, err := f.srv.toolListUnknownEntities(octx, nil, bookOnlyToolIn{BookID: f.bookID.String(), Status: "active"})
	if err != nil {
		t.Fatalf("status=active list: %v", err)
	}
	for _, it := range outActive.Items {
		if it.EntityID == draftID.String() {
			t.Error("status=active must NOT surface the draft entity")
		}
	}

	// A bogus status is rejected, not silently ignored.
	if _, _, err := f.srv.toolListUnknownEntities(octx, nil, bookOnlyToolIn{BookID: f.bookID.String(), Status: "bogus"}); err == nil {
		t.Error("unknown entities: bad status should error")
	}
}

// Mirrors the above for glossary_list_ai_suggestions — the OTHER inbox the feedback named,
// and the one whose bug had a DIFFERENT root cause (tag-based filtering, never status-based,
// so "approving" via glossary_propose_status_change never set the tombstone tag and the
// entity lingered forever). The status-default fix works here even though the underlying
// tag logic is untouched.
func TestListAISuggestions_StatusFilterDrainsOnceApproved(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)
	charKind := bookKindID(t, pool, f.bookID, "character")

	var pendingID, approvedID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, tags, short_description)
		 VALUES($1,$2,'draft','{ai-suggested}','still pending') RETURNING entity_id`,
		f.bookID, charKind).Scan(&pendingID); err != nil {
		t.Fatalf("seed pending ai-suggested: %v", err)
	}
	// Simulates the REAL bug: approved via glossary_propose_status_change (status -> active),
	// which never touches the 'ai-rejected' tombstone tag — the tag-only filter alone would
	// keep surfacing this row forever.
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, status, tags, short_description)
		 VALUES($1,$2,'active','{ai-suggested}','already approved') RETURNING entity_id`,
		f.bookID, charKind).Scan(&approvedID); err != nil {
		t.Fatalf("seed already-approved ai-suggested: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id = ANY($1::uuid[])`, []uuid.UUID{pendingID, approvedID}) //nolint:errcheck
	})

	_, out, err := f.srv.toolListAISuggestions(octx, nil, bookOnlyToolIn{BookID: f.bookID.String()})
	if err != nil {
		t.Fatalf("default list: %v", err)
	}
	seen := map[string]bool{}
	for _, it := range out.Items {
		seen[it.EntityID] = true
	}
	if !seen[pendingID.String()] {
		t.Error("default (draft) view must surface the still-pending suggestion")
	}
	if seen[approvedID.String()] {
		t.Error("default (draft) view must NOT surface the already-approved suggestion (the reported bug)")
	}

	_, outAll, err := f.srv.toolListAISuggestions(octx, nil, bookOnlyToolIn{BookID: f.bookID.String(), Status: "all"})
	if err != nil {
		t.Fatalf("status=all list: %v", err)
	}
	seenAll := map[string]bool{}
	for _, it := range outAll.Items {
		seenAll[it.EntityID] = true
	}
	if !seenAll[pendingID.String()] || !seenAll[approvedID.String()] {
		t.Errorf("status=all must surface both suggestions, got %+v", outAll.Items)
	}
}
