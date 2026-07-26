package api

// WS-1.1 — books.kind: the privacy lock (spec 03, T29/T30).
//
// kind is NOT a UI hint. kind='diary' is what every egress guard keys on (sharing, wiki,
// public-MCP, notifications, catalog, export, collaborator grants). Two ways it could
// silently fail open, and a test for each:
//
//   1. Someone UPDATEs kind after creation  -> the lock is stripped.  (DB trigger)
//   2. A create path forgets to set kind    -> a diary is born a novel. (hygiene lock)
//
// DB-gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestBookKind_IsImmutable_DB(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()

	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'diary','diary') RETURNING id`,
		uuid.New()).Scan(&bookID); err != nil {
		t.Fatalf("seed diary: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	// THE LOCK. Flipping a diary to a novel would make private content shareable through
	// every egress path at once.
	_, err := pool.Exec(ctx, `UPDATE books SET kind='novel' WHERE id=$1`, bookID)
	if err == nil {
		t.Fatal("books.kind was CHANGED from diary to novel. kind is the privacy lock — " +
			"every egress guard keys on it, so a mutable kind means a private diary can be " +
			"silently turned into a publishable novel. It must be DB-enforced, not a convention.")
	}
	if !strings.Contains(err.Error(), "immutable") {
		t.Fatalf("expected the immutability trigger to fire, got: %v", err)
	}

	// And it really is still a diary.
	var kind string
	if err := pool.QueryRow(ctx, `SELECT kind FROM books WHERE id=$1`, bookID).Scan(&kind); err != nil {
		t.Fatalf("read kind: %v", err)
	}
	if kind != "diary" {
		t.Fatalf("kind = %q after the refused update, want diary", kind)
	}
}

func TestBookKind_OtherColumnsStillUpdatable_DB(t *testing.T) {
	// The trigger must not turn books into a read-only table — it guards ONE column.
	_, pool := dbTestServer(t)
	ctx := context.Background()

	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'t','novel') RETURNING id`,
		uuid.New()).Scan(&bookID); err != nil {
		t.Fatalf("seed: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	if _, err := pool.Exec(ctx,
		`UPDATE books SET title='renamed', description='d' WHERE id=$1`, bookID); err != nil {
		t.Fatalf("a normal update was refused by the kind trigger: %v", err)
	}
	// A no-op self-assignment of the SAME kind must also be allowed — otherwise every
	// dynamic UPDATE builder that happens to include kind would start failing.
	if _, err := pool.Exec(ctx,
		`UPDATE books SET kind='novel', title='again' WHERE id=$1`, bookID); err != nil {
		t.Fatalf("setting kind to its EXISTING value must be allowed: %v", err)
	}
}

func TestBookKind_ClosedSet_DB(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()

	_, err := pool.Exec(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'t','journal')`, uuid.New())
	if err == nil {
		t.Fatal("an unknown kind was accepted. The set is closed (novel|document|lore|diary) " +
			"because every egress guard switches on it — an unknown kind would fall through " +
			"whichever branch happens to be the default.")
	}
}

func TestBookKind_BackfilledBiblesAreLore_DB(t *testing.T) {
	// A DEFAULT does not revisit existing rows. Pre-existing world-bibles must have been
	// backfilled to 'lore' by the migration, in the SAME commit that teaches
	// createWorldCore to set kind='lore' — otherwise bibles created before and after the
	// deploy are different kinds forever.
	_, pool := dbTestServer(t)
	ctx := context.Background()

	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,is_bible,kind) VALUES($1,'wb',true,'lore') RETURNING id`,
		uuid.New()).Scan(&bookID); err != nil {
		t.Fatalf("seed bible: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	var kind string
	var isBible bool
	if err := pool.QueryRow(ctx,
		`SELECT kind, is_bible FROM books WHERE id=$1`, bookID).Scan(&kind, &isBible); err != nil {
		t.Fatalf("read: %v", err)
	}
	if kind != "lore" || !isBible {
		t.Fatalf("world bible = kind %q is_bible %v, want lore/true", kind, isBible)
	}
}

// ── the hygiene lock ──────────────────────────────────────────────────────────

var reInsertBooks = regexp.MustCompile(`(?is)INSERT\s+INTO\s+books\s*\(([^)]*)\)`)

// TestEveryBookCreatePathSetsKindExplicitly — the T30 drift lock.
//
// A create path that omits `kind` inherits the column default ('novel'). That is harmless
// for a novel and CATASTROPHIC for a diary: the book would be born without its privacy
// lock and every egress guard would wave it through. The failure is silent — the row looks
// perfectly normal.
//
// A code review cannot hold this invariant across future create paths. This test can.
func TestEveryBookCreatePathSetsKindExplicitly(t *testing.T) {
	found := 0
	err := filepath.Walk(".", func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || !strings.HasSuffix(path, ".go") ||
			strings.HasSuffix(path, "_test.go") {
			return err
		}
		src, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		for _, m := range reInsertBooks.FindAllStringSubmatch(string(src), -1) {
			cols := m[1]
			found++
			if !strings.Contains(strings.ToLower(cols), "kind") {
				t.Errorf(
					"%s: an INSERT INTO books does NOT set `kind` explicitly.\n"+
						"It will inherit the column default ('novel'). Harmless for a novel; "+
						"CATASTROPHIC for a diary — the book is born without its privacy lock, "+
						"and every egress guard (sharing, wiki, public-MCP, export, catalog) "+
						"waves it through. The row looks completely normal.\n"+
						"  columns: %s",
					path, strings.Join(strings.Fields(cols), " "),
				)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walk: %v", err)
	}

	// Guard against the test silently passing because the regex stopped matching.
	if found < 3 {
		t.Fatalf("expected at least 3 INSERT INTO books sites (REST createBook, MCP "+
			"book_create, createWorldCore), found %d — this hygiene lock is not actually "+
			"guarding anything", found)
	}
}
