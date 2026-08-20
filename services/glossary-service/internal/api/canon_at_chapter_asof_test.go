package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// `known-entities` answers AS OF the requested chapter (plan T52).
//
// THE DESIGN'S OWN WORKED EXAMPLE
// ------------------------------
// `GET /v1/glossary/books/{book_id}/known-entities` is a LIVE public route feeding the
// composition canon-at-chapter panel, and its entire purpose is *"what does canon know as of
// chapter N"*. It bounded `chapter_entity_links` by chapter — and then joined the CURRENT
// name, aliases and kind, and filtered the TIMELESS `e.alive`. So the set of entities was
// timed and everything rendered about them was not.
//
// The sealed design cites this exact handler as its worked example, and T5 added a *new*
// as-of endpoint without touching it — which is how a defect survives a refactor that claims
// to have fixed it.
//
// The acceptance case is the plan's own: an entity renamed at ch.30 must render under its
// **ch.10 name** when queried at ch.10.

func TestKnownEntities_RendersTheNameFromTheRequestedChapter(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	// The rename: "Ash" from the start, "Ashborn" from chapter 30. Two facts, one chain.
	if _, err := pool.Exec(ctx, `
		INSERT INTO entity_facts
		    (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, valid_to_ordinal)
		VALUES ($1, $2, 'name', 'name', 'Ash', 1, 30),
		       ($1, $2, 'name', 'name', 'Ashborn', 30, NULL)`,
		f.bookID, f.entityID); err != nil {
		t.Fatalf("seed name facts: %v", err)
	}
	// The entity must be LINKED to early chapters or the aggregate excludes it entirely.
	for _, idx := range []int{1, 2} {
		if _, err := pool.Exec(ctx, `
			INSERT INTO chapter_entity_links (entity_id, chapter_id, chapter_index, relevance)
			VALUES ($1, gen_random_uuid(), $2, 'primary')`,
			f.entityID, idx); err != nil {
			t.Fatalf("seed chapter link: %v", err)
		}
	}

	get := func(q string) []map[string]any {
		t.Helper()
		req := httptest.NewRequest(http.MethodGet,
			"/v1/glossary/books/"+f.bookID.String()+"/known-entities?min_frequency=1&"+q, nil)
		req.Header.Set("Authorization", "Bearer "+f.token)
		w := httptest.NewRecorder()
		f.srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("known-entities %s: want 200, got %d (%s)", q, w.Code, w.Body.String())
		}
		var out []map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
			t.Fatalf("decode: %v (%s)", err, w.Body.String())
		}
		return out
	}

	nameFor := func(rows []map[string]any) string {
		for _, r := range rows {
			if r["entity_id"] == f.entityID.String() {
				n, _ := r["name"].(string)
				return n
			}
		}
		return ""
	}

	// ── the acceptance case ──────────────────────────────────────────────────────
	at10 := nameFor(get("before_chapter_index=10"))
	if at10 != "Ash" {
		t.Fatalf("queried at chapter 10 the entity must render under its ch.10 name %q, got %q.\n"+
			"  A canon-at-chapter panel showing the ch.30 name at ch.10 is a SPOILER that looks "+
			"like data — it is well-formed, plausible and wrong.", "Ash", at10)
	}

	// ── and the control: the same read after the rename sees the new name ────────
	// Without this, "Ash" could be right for the wrong reason — a handler that always
	// returned the earliest name would pass the assertion above and be just as broken.
	at40 := nameFor(get("before_chapter_index=40"))
	if at40 != "Ashborn" {
		t.Fatalf("queried at chapter 40 the entity must render under its ch.30 name %q, got %q.\n"+
			"  Without this control the test above passes for a handler that simply always "+
			"returns the oldest name.", "Ashborn", at40)
	}
}

func TestKnownEntities_WholeBookReadUsesCurrentValues(t *testing.T) {
	// `before_chapter_index` omitted means "the whole book", which has NO single story
	// position — asking for a name "as of the whole book" is not a question. The current
	// value is then the CORRECT read rather than a degradation, and this pins that so a
	// future change cannot quietly make the untimed read answer at position 0 (which would
	// render every entity under its earliest name across the whole panel).
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	if _, err := pool.Exec(ctx, `
		INSERT INTO entity_facts
		    (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, valid_to_ordinal)
		VALUES ($1, $2, 'name', 'name', 'Ash', 1, 30)`,
		f.bookID, f.entityID); err != nil {
		t.Fatalf("seed name fact: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO chapter_entity_links (entity_id, chapter_id, chapter_index, relevance)
		VALUES ($1, gen_random_uuid(), 5, 'primary')`,
		f.entityID); err != nil {
		t.Fatalf("seed chapter link: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+f.bookID.String()+"/known-entities?min_frequency=1", nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var out []map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, r := range out {
		if r["entity_id"] == f.entityID.String() {
			if n, _ := r["name"].(string); n == "Ash" {
				t.Fatalf("the untimed whole-book read answered from a story-time fact (%q). "+
					"A whole-book read has no position; it must use the current value.", n)
			}
		}
	}
}

// TestKnownEntities_AnEntityKilledInTheStoryLeavesTheCanonPanelAfterItsDeath is T32's
// reader migration, and the case D-T32-ALIVE-NO-FACTS said could not be validated.
//
// That deferral posed a dichotomy — a migrated reader must fail CLOSED (every entity reads
// not-alive: a total outage) or fail OPEN (identical to alive=true: proves nothing) — and both
// arms assume the reader REPLACES the column. Conjoining is the third path: `alive` still
// gates the author's explicit hide, and a `life_status='gone'` fact covering the requested
// position removes the entity on top of it. Strictly narrowing, so it cannot regress.
//
// Both directions are asserted. The before-death read is not a nicety: a handler that dropped
// the entity everywhere would satisfy the after-death half and be far worse than the bug.
func TestKnownEntities_AnEntityKilledInTheStoryLeavesTheCanonPanelAfterItsDeath(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	// Killed at ordinal 20. Open interval: once gone, gone.
	seedFact(t, pool, f.bookID, f.entityID, "status", "life_status", "gone", 20, nil)
	for _, idx := range []int{1, 2} {
		if _, err := pool.Exec(ctx, `
			INSERT INTO chapter_entity_links (entity_id, chapter_id, chapter_index, relevance)
			VALUES ($1, gen_random_uuid(), $2, 'primary')`,
			f.entityID, idx); err != nil {
			t.Fatalf("seed chapter link: %v", err)
		}
	}

	present := func(q string) bool {
		t.Helper()
		req := httptest.NewRequest(http.MethodGet,
			"/v1/glossary/books/"+f.bookID.String()+"/known-entities?min_frequency=1&"+q, nil)
		req.Header.Set("Authorization", "Bearer "+f.token)
		w := httptest.NewRecorder()
		f.srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("known-entities %s: want 200, got %d (%s)", q, w.Code, w.Body.String())
		}
		var out []map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
			t.Fatalf("decode: %v (%s)", err, w.Body.String())
		}
		for _, r := range out {
			if r["entity_id"] == f.entityID.String() {
				return true
			}
		}
		return false
	}

	if present("before_chapter_index=40") {
		t.Fatalf("read at chapter 40 still lists an entity the story killed at 20.\n" +
			"  A canon panel dated after a character's death that still shows them alive is " +
			"the same spoiler class as showing their later name early — well-formed, " +
			"plausible, and wrong.")
	}
	if !present("before_chapter_index=10") {
		t.Fatalf("read at chapter 10 — BEFORE the death at 20 — dropped the entity.\n" +
			"  This is the control. Without it a handler that hides the entity at every " +
			"position passes the assertion above while destroying the panel.")
	}
	// And the UNTIMED read: no position means the liveness question is unanswerable, so the
	// filter must be inert rather than guessing. An editor view that silently lost every dead
	// character would be a regression wearing a spoiler fix's clothes.
	if !present("") {
		t.Fatalf("the untimed (editor) read dropped a dead entity.\n" +
			"  With no position there is nothing to evaluate `gone at P` against; the filter " +
			"must not fire at all.")
	}
}
