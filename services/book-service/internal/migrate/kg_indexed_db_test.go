package migrate

// WS-0.2 — publish-independent KG indexing: columns + backfill.
//
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.1 + §6.
//
// migrate_test.go locks the schema STRINGS; it never executes a statement. The two
// hazards here are both RUNTIME ones and neither is observable without a database:
//
//  1. SET-EQUIVALENCE (§6): the backfill must seed exactly the set the OLD
//     published-gated sweeper predicate selected — no more (a re-parse storm on
//     first sweep), no fewer (a chapter silently drops out of the graph forever).
//
//  2. MARKER GATING: the backfill must run EXACTLY ONCE. If it re-ran on boot it
//     would RE-SET kg_indexed_revision_id on a chapter the user had explicitly
//     excluded from their knowledge graph (kg_exclude retraction clears the pointer
//     but leaves the chapter published) — a privacy decision silently undone by a
//     restart. That is the test this file exists for.
//
// Gated on BOOK_TEST_DATABASE_URL, a THROWAWAY database.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// kgSeed inserts a book + chapter + revision, returning (chapterID, revisionID).
func kgSeed(t *testing.T, pool *pgxpool.Pool, status string, withRevision bool) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()

	bookID := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO books (id, owner_user_id, title) VALUES ($1, $2, $3)`,
		bookID, uuid.New(), "ws02-"+bookID.String()[:8],
	); err != nil {
		t.Fatalf("seed book: %v", err)
	}

	chapterID := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO chapters
		   (id, book_id, original_filename, original_language, content_type,
		    sort_order, storage_key)
		 VALUES ($1, $2, 'ch.txt', 'en', 'text/plain', 1, $3)`,
		chapterID, bookID, "k/"+chapterID.String(),
	); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}

	var revID uuid.UUID
	if withRevision {
		revID = uuid.New()
		if _, err := pool.Exec(ctx,
			`INSERT INTO chapter_revisions (id, chapter_id, body) VALUES ($1, $2, $3::jsonb)`,
			revID, chapterID, `{"type":"doc","content":[]}`,
		); err != nil {
			t.Fatalf("seed revision: %v", err)
		}
		if _, err := pool.Exec(ctx,
			`UPDATE chapters SET editorial_status=$2, published_revision_id=$3 WHERE id=$1`,
			chapterID, status, revID,
		); err != nil {
			t.Fatalf("pin revision: %v", err)
		}
	} else {
		if _, err := pool.Exec(ctx,
			`UPDATE chapters SET editorial_status=$2 WHERE id=$1`, chapterID, status,
		); err != nil {
			t.Fatalf("set status: %v", err)
		}
	}
	return chapterID, revID
}

func kgPointer(t *testing.T, pool *pgxpool.Pool, chapterID uuid.UUID) *uuid.UUID {
	t.Helper()
	var ptr *uuid.UUID
	if err := pool.QueryRow(context.Background(),
		`SELECT kg_indexed_revision_id FROM chapters WHERE id=$1`, chapterID,
	).Scan(&ptr); err != nil {
		t.Fatalf("read kg_indexed_revision_id: %v", err)
	}
	return ptr
}

// clearKGMarker lets a test re-run the backfill as if this were a fresh deploy.
func clearKGMarker(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	if _, err := pool.Exec(context.Background(),
		`DELETE FROM canon_model_migration WHERE id = 'kg_indexed_backfill_v1'`,
	); err != nil {
		t.Fatalf("clear marker: %v", err)
	}
}

// TestKGIndexedBackfillSetEquivalence — spec §6.
//
// The backfill must select EXACTLY the old predicate's set:
//   - published + has a pinned revision  -> pointer seeded  (was swept before, still is)
//   - draft                              -> pointer NULL    (was not swept, still isn't)
//   - published but no pinned revision   -> pointer NULL    (excluded by BOTH predicates)
//
// Under-seeding = a chapter drops out of the graph forever. Over-seeding = a re-parse
// storm on first sweep.
func TestKGIndexedBackfillSetEquivalence(t *testing.T) {
	pool := scenesTestPool(t) // runs Up(); skips when BOOK_TEST_DATABASE_URL is unset
	defer pool.Close()

	// Seed BEFORE re-running the backfill, then clear the marker so it fires over
	// these rows (Up() in the fixture already consumed the marker on an empty DB).
	pubCh, pubRev := kgSeed(t, pool, "published", true)
	draftCh, _ := kgSeed(t, pool, "draft", true)
	pubNoRevCh, _ := kgSeed(t, pool, "published", false)

	clearKGMarker(t, pool)
	if err := Up(context.Background(), pool); err != nil {
		t.Fatalf("Up (backfill re-run): %v", err)
	}

	if got := kgPointer(t, pool, pubCh); got == nil || *got != pubRev {
		t.Fatalf("published chapter must be seeded with its published revision: got %v want %v", got, pubRev)
	}
	if got := kgPointer(t, pool, draftCh); got != nil {
		t.Fatalf("a DRAFT chapter must NOT be seeded (it was never swept before): got %v", *got)
	}
	if got := kgPointer(t, pool, pubNoRevCh); got != nil {
		t.Fatalf("published-but-unpinned chapter must NOT be seeded (excluded by both predicates): got %v", *got)
	}
}

// TestKGIndexedBackfillIsMarkerGatedAndCannotResurrectAnExcludedChapter — THE test.
//
// The scenario the marker exists to defend:
//
//	1. deploy         -> backfill seeds kg_indexed_revision_id from published_revision_id
//	2. user excludes  -> kg_exclude=true, kg_indexed_revision_id=NULL (the §3.8 retraction).
//	                     The chapter is STILL editorial_status='published' with a pinned
//	                     published_revision_id — nothing about publish changed.
//	3. restart        -> Up() runs again.
//
// An ungated backfill re-runs at step 3, sees "published AND published_revision_id IS
// NOT NULL", and RE-SETS the pointer — silently pulling a chapter the user removed from
// their knowledge graph back INTO it. A privacy decision undone by a reboot.
func TestKGIndexedBackfillIsMarkerGatedAndCannotResurrectAnExcludedChapter(t *testing.T) {
	pool := scenesTestPool(t)
	defer pool.Close()
	ctx := context.Background()

	// 1. A published, indexed chapter.
	ch, rev := kgSeed(t, pool, "published", true)
	clearKGMarker(t, pool)
	if err := Up(ctx, pool); err != nil {
		t.Fatalf("Up (initial backfill): %v", err)
	}
	if got := kgPointer(t, pool, ch); got == nil || *got != rev {
		t.Fatalf("precondition: chapter should be seeded, got %v", got)
	}

	// 2. The user excludes it from their KG (§3.8 retraction clears the pointer).
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_exclude=true, kg_indexed_revision_id=NULL WHERE id=$1`, ch,
	); err != nil {
		t.Fatalf("exclude: %v", err)
	}

	// 3. Restart. The backfill must NOT run again.
	if err := Up(ctx, pool); err != nil {
		t.Fatalf("Up (restart): %v", err)
	}

	if got := kgPointer(t, pool, ch); got != nil {
		t.Fatalf("REGRESSION: a restart resurrected the KG pointer (%v) on a chapter the "+
			"user excluded. The backfill must be marker-gated so it cannot undo a "+
			"privacy decision on reboot.", *got)
	}
}

// TestKGIndexedBackfillGuardsAgainstExcludedChaptersEvenOnAFreshRun — belt-and-braces.
//
// Even if the marker were somehow cleared (a hand-run migration, a restored DB), the
// backfill's own `kg_exclude = false` guard must still refuse to seed an excluded
// chapter. Defense in depth for the same privacy property.
func TestKGIndexedBackfillGuardsAgainstExcludedChaptersEvenOnAFreshRun(t *testing.T) {
	pool := scenesTestPool(t)
	defer pool.Close()
	ctx := context.Background()

	ch, _ := kgSeed(t, pool, "published", true)
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET kg_exclude=true, kg_indexed_revision_id=NULL WHERE id=$1`, ch,
	); err != nil {
		t.Fatalf("exclude: %v", err)
	}

	clearKGMarker(t, pool) // simulate the marker being lost
	if err := Up(ctx, pool); err != nil {
		t.Fatalf("Up: %v", err)
	}

	if got := kgPointer(t, pool, ch); got != nil {
		t.Fatalf("the backfill's kg_exclude=false guard must refuse to seed an excluded "+
			"chapter even on a fresh run: got %v", *got)
	}
}

// TestKGExcludeDefaultsFalseSoExistingChaptersAreUnaffected — the column default.
//
// kg_exclude must default false: adding the column must not silently remove every
// existing chapter from the knowledge graph.
func TestKGExcludeDefaultsFalse(t *testing.T) {
	pool := scenesTestPool(t)
	defer pool.Close()

	ch, _ := kgSeed(t, pool, "draft", false)

	var excluded bool
	if err := pool.QueryRow(context.Background(),
		`SELECT kg_exclude FROM chapters WHERE id=$1`, ch,
	).Scan(&excluded); err != nil {
		t.Fatalf("read kg_exclude: %v", err)
	}
	if excluded {
		t.Fatal("kg_exclude must default to false — a true default would silently drop " +
			"every existing chapter out of the knowledge graph")
	}
}
