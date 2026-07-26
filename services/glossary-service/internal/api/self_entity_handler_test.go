package api

// WS-1.6 (spec 05 §Q5) — the self-entity seed get-or-create (seedSelfEntityCore).
//
// The user's OWN identity entity must be created ACTIVE + is_self (not a review draft — the
// user IS themselves), exactly once per diary, and a re-provision (including concurrent) must
// converge on the SAME entity. Then capture dedups the user's name onto it + the detectors
// exclude it. DB-gated on GLOSSARY_TEST_DB_URL (via openTestDB).

import (
	"context"
	"sync"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// selfEntityTestBook sets up a diary-like book with the 'colleague' work kind adopted, plus
// the WS-1.5a work-kind seed + WS-1.6c is_self column (idempotent; not in the K2a subset).
func selfEntityTestBook(t *testing.T) (*Server, uuid.UUID) {
	t.Helper()
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrate.SeedWorkKinds(ctx, pool); err != nil {
		t.Fatalf("SeedWorkKinds: %v", err)
	}
	if err := migrate.UpEntityIsSelf(ctx, pool); err != nil {
		t.Fatalf("UpEntityIsSelf: %v", err)
	}
	book := uuid.New()
	user := uuid.New()
	adoptTestBook(t, pool, book)
	s := &Server{pool: pool}
	// Clone the 'colleague' work kind into the book tier (WS-1.5b does this in production).
	if err := s.adoptBookOntologyCore(ctx, book, user, nil, []string{"colleague"}); err != nil {
		t.Fatalf("adopt colleague: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	return s, book
}

func TestSeedSelfEntity_CreatesActiveIsSelf_ThenIdempotent(t *testing.T) {
	s, book := selfEntityTestBook(t)
	ctx := context.Background()

	id1, created1, err := s.seedSelfEntityCore(ctx, book, "Alex Kim")
	if err != nil {
		t.Fatalf("first seed: %v", err)
	}
	if !created1 {
		t.Fatal("first seed must report created")
	}

	// The identity entity is ACTIVE + is_self (not a review draft — the user IS themselves).
	var isSelf bool
	var status string
	if err := s.pool.QueryRow(ctx,
		`SELECT is_self, status FROM glossary_entities WHERE entity_id=$1`, id1).Scan(&isSelf, &status); err != nil {
		t.Fatalf("read entity: %v", err)
	}
	if !isSelf || status != "active" {
		t.Fatalf("self-entity is_self=%v status=%q, want true/active", isSelf, status)
	}

	// Idempotent: a second seed returns the SAME entity, never a second "me".
	id2, created2, err := s.seedSelfEntityCore(ctx, book, "Alex Kim")
	if err != nil {
		t.Fatalf("second seed: %v", err)
	}
	if created2 || id2 != id1 {
		t.Fatalf("second seed created=%v id=%s (want false, %s) — must be idempotent", created2, id2, id1)
	}

	var n int
	if err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM glossary_entities WHERE book_id=$1 AND is_self AND deleted_at IS NULL`,
		book).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 1 {
		t.Fatalf("self-entity count=%d, want exactly 1", n)
	}
}

func TestSeedSelfEntity_RaceSafe(t *testing.T) {
	// Two devices open /assistant at once → two concurrent seeds must converge on ONE
	// self-entity (proposeNewEntity dedups the name under a per-book advisory lock).
	s, book := selfEntityTestBook(t)
	ctx := context.Background()

	const n = 6
	var wg sync.WaitGroup
	ids := make([]string, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			if id, _, err := s.seedSelfEntityCore(ctx, book, "Alex Kim"); err == nil {
				ids[i] = id
			}
		}(i)
	}
	wg.Wait()

	first := ids[0]
	for i, id := range ids {
		if id == "" || id != first {
			t.Fatalf("concurrent seed produced DIFFERENT self-entities (caller %d: %q vs %q)", i, id, first)
		}
	}
	var rows int
	if err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM glossary_entities WHERE book_id=$1 AND is_self AND deleted_at IS NULL`,
		book).Scan(&rows); err != nil {
		t.Fatalf("count: %v", err)
	}
	if rows != 1 {
		t.Fatalf("self-entity rows=%d, want exactly 1", rows)
	}
}
