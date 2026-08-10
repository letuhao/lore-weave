package api

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

// Chapter revisions invalidate the facts they replaced (plan T32 / decision Q6).
//
// RED BEFORE GREEN, BY CONSTRUCTION
// ---------------------------------
// When Q6 was sealed the corpus was measured at **99 episodes, 99 chapters, 0 revisions** —
// every episode is its chapter's first and only one, so this path has never fired in
// production and no existing test could have covered it. These tests have to CREATE the
// revision the corpus has never contained; that is the whole reason they exist rather than
// an assertion about data that was already there.
//
// The axis matters. A rewrite does not change WHEN something happened in the story, it
// changes what the system is entitled to believe about it — so the facts are invalidated on
// the belief axis (`invalidated_at` / `invalidated_reason`) and their story intervals are left
// exactly as they were.

func TestEpisodeSupersede_RevisionInvalidatesPriorFacts(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	chapterID := uuid.New()
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	ep1, minted1, err := ingestEpisode(ctx, tx, f.bookID, chapterID, 7, "hash-original", "")
	if err != nil || !minted1 {
		t.Fatalf("seed episode: err=%v minted=%v", err, minted1)
	}
	var factID uuid.UUID
	if err := tx.QueryRow(ctx, `
		INSERT INTO entity_facts
		    (book_id, entity_id, fact_kind, attr_or_predicate, value,
		     valid_from_ordinal, source_episode_id)
		VALUES ($1, $2, 'attribute', 'rank', 'inner disciple', 7, $3)
		RETURNING fact_id`,
		f.bookID, f.entityID, ep1).Scan(&factID); err != nil {
		t.Fatalf("seed fact: %v", err)
	}

	// The revision: same chapter, different text ⇒ a new content hash ⇒ a new episode.
	ep2, minted2, err := ingestEpisode(ctx, tx, f.bookID, chapterID, 7, "hash-rewritten", "")
	if err != nil || !minted2 {
		t.Fatalf("revision episode: err=%v minted=%v", err, minted2)
	}
	if ep2 == ep1 {
		t.Fatal("precondition: a changed content hash must mint a NEW episode, not resume the old one")
	}

	n, err := supersedePriorEpisodeFacts(ctx, tx, chapterID, ep2)
	if err != nil {
		t.Fatalf("supersede: %v", err)
	}
	if n != 1 {
		t.Fatalf("the revision must invalidate the 1 fact from the superseded episode, got %d", n)
	}

	var reason string
	var validFrom int64
	if err := tx.QueryRow(ctx,
		`SELECT coalesce(invalidated_reason,''), valid_from_ordinal
		   FROM entity_facts WHERE fact_id = $1`, factID).Scan(&reason, &validFrom); err != nil {
		t.Fatalf("read fact: %v", err)
	}
	if reason != "episode_superseded" {
		t.Fatalf("want invalidated_reason=episode_superseded, got %q", reason)
	}
	// Q6 is explicit that story-time is untouched: only the system's BELIEF changed.
	if validFrom != 7 {
		t.Fatalf("the story interval moved (valid_from_ordinal=%d, want 7) — a rewrite must not "+
			"relocate when something happened in the narrative", validFrom)
	}
}

func TestEpisodeSupersede_ReRunWithIdenticalTextSupersedesNothing(t *testing.T) {
	// The control, and the one that stops this becoming a data-loss bug. `ingestEpisode`
	// RESUMES on an identical content hash (C6), so a re-run of the same extraction must
	// invalidate nothing. Without this, every idempotent re-ingest would quietly retire the
	// facts it had just confirmed.
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	chapterID := uuid.New()
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	ep1, _, err := ingestEpisode(ctx, tx, f.bookID, chapterID, 9, "hash-same", "")
	if err != nil {
		t.Fatalf("seed episode: %v", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO entity_facts
		    (book_id, entity_id, fact_kind, attr_or_predicate, value,
		     valid_from_ordinal, source_episode_id)
		VALUES ($1, $2, 'attribute', 'rank', 'core disciple', 9, $3)`,
		f.bookID, f.entityID, ep1); err != nil {
		t.Fatalf("seed fact: %v", err)
	}

	ep2, minted, err := ingestEpisode(ctx, tx, f.bookID, chapterID, 9, "hash-same", "")
	if err != nil {
		t.Fatalf("re-ingest: %v", err)
	}
	if minted || ep2 != ep1 {
		t.Fatalf("precondition: identical text must RESUME the same episode (minted=%v, same=%v)",
			minted, ep2 == ep1)
	}

	n, err := supersedePriorEpisodeFacts(ctx, tx, chapterID, ep2)
	if err != nil {
		t.Fatalf("supersede: %v", err)
	}
	if n != 0 {
		t.Fatalf("an idempotent re-ingest invalidated %d fact(s) — a re-run must confirm facts, "+
			"not retire them", n)
	}
}

func TestEpisodeSupersede_LeavesOtherChaptersAlone(t *testing.T) {
	// Scoping, asserted rather than assumed: the UPDATE selects episodes by chapter_id, and a
	// missing predicate there would invalidate the whole book's facts on any single edit —
	// silently, because every one of them would still look like a well-formed retired fact.
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	otherChapter := uuid.New()
	epOther, _, err := ingestEpisode(ctx, tx, f.bookID, otherChapter, 3, "hash-other", "")
	if err != nil {
		t.Fatalf("seed other episode: %v", err)
	}
	var otherFact uuid.UUID
	if err := tx.QueryRow(ctx, `
		INSERT INTO entity_facts
		    (book_id, entity_id, fact_kind, attr_or_predicate, value,
		     valid_from_ordinal, source_episode_id)
		VALUES ($1, $2, 'attribute', 'sect', 'Cloud Gate', 3, $3)
		RETURNING fact_id`,
		f.bookID, f.entityID, epOther).Scan(&otherFact); err != nil {
		t.Fatalf("seed other fact: %v", err)
	}

	revised := uuid.New()
	if _, _, err := ingestEpisode(ctx, tx, f.bookID, revised, 4, "hash-v1", ""); err != nil {
		t.Fatalf("seed revised ch v1: %v", err)
	}
	ep2, _, err := ingestEpisode(ctx, tx, f.bookID, revised, 4, "hash-v2", "")
	if err != nil {
		t.Fatalf("seed revised ch v2: %v", err)
	}
	if _, err := supersedePriorEpisodeFacts(ctx, tx, revised, ep2); err != nil {
		t.Fatalf("supersede: %v", err)
	}

	var reason string
	if err := tx.QueryRow(ctx,
		`SELECT coalesce(invalidated_reason,'') FROM entity_facts WHERE fact_id = $1`,
		otherFact).Scan(&reason); err != nil {
		t.Fatalf("read other fact: %v", err)
	}
	if reason != "" {
		t.Fatalf("revising one chapter invalidated another chapter's fact (reason=%q) — the "+
			"chapter predicate is not holding", reason)
	}
}
