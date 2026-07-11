package api

import (
	"context"
	"net/http/httptest"
	"slices"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/config"
)

// ── non-DB: tool wrapper validation + ownership (always run) ──────────────────

func ctxWithUser(u uuid.UUID) context.Context {
	return context.WithValue(context.Background(), ctxKeyUserID, u.String())
}

func TestToolPropose_MissingIdentity(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolProposeNewEntity(context.Background(), nil,
		proposeEntityToolIn{BookID: uuid.NewString(), Kind: "character", Name: "X"})
	if err == nil || err.Error() != "missing caller identity" {
		t.Fatalf("want missing-identity error, got %v", err)
	}
}

func TestToolPropose_RejectsBadInput(t *testing.T) {
	s := &Server{}
	u := uuid.New()
	cases := []struct {
		name string
		in   proposeEntityToolIn
	}{
		{"bad book_id", proposeEntityToolIn{BookID: "nope", Kind: "character", Name: "X"}},
		{"empty name", proposeEntityToolIn{BookID: uuid.NewString(), Kind: "character", Name: "   "}},
		{"empty kind", proposeEntityToolIn{BookID: uuid.NewString(), Kind: "", Name: "X"}},
	}
	for _, c := range cases {
		if _, _, err := s.toolProposeNewEntity(ctxWithUser(u), nil, c.in); err == nil {
			t.Errorf("%s: want validation error, got nil", c.name)
		}
	}
}

func TestToolPropose_OwnershipDenied(t *testing.T) {
	// book-service returns a projection owned by someone else → not accessible.
	ts := httptest.NewServer(projection(uuid.New(), uuid.New()))
	defer ts.Close()
	s := &Server{cfg: &config.Config{BookServiceURL: ts.URL, InternalServiceToken: "t"}, grantClient: buildGrantClient(ts.URL, "t")}
	_, _, err := s.toolProposeNewEntity(ctxWithUser(uuid.New()), nil,
		proposeEntityToolIn{BookID: uuid.NewString(), Kind: "character", Name: "X"})
	if err == nil || !strings.Contains(err.Error(), "not accessible") {
		t.Fatalf("non-owner must be denied with not-accessible, got %v", err)
	}
}

// ── DB-backed: proposeNewEntity core (skips without GLOSSARY_TEST_DB_URL) ─────

func TestProposeNewEntity_CreatesDraftThenDedups(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	s := &Server{pool: pool}

	// /review-impl HIGH fix (D-GLOSSARY-UNMATCHED-ATTR-FALLBACK, was "070"): a
	// supplied attribute code that doesn't exist on the kind is no longer dropped —
	// it's captured into the kind's "description" catch-all, so it's NOT reported
	// as skipped anymore (skipped is now reserved for a genuine drop: no
	// "description" attr_def on the kind, or INV-8 verified-clobber).
	id, status, skipped, err := s.proposeNewEntity(ctx, book, kindID, "Nezha", map[string]any{"no_such_attr": "x"}, "")
	if err != nil || status != "created" {
		t.Fatalf("want created, got status=%q err=%v", status, err)
	}
	if len(skipped) != 0 {
		t.Errorf("want no skipped attrs (captured into description instead), got %v", skipped)
	}
	var description string
	if err := pool.QueryRow(ctx, `
		SELECT eav.original_value FROM entity_attribute_values eav
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE eav.entity_id=$1 AND ba.code='description'`, id).Scan(&description); err != nil {
		t.Fatalf("query description: %v", err)
	}
	if !strings.Contains(description, "no_such_attr") || !strings.Contains(description, "x") {
		t.Errorf("want the unmatched attr captured into description, got %q", description)
	}
	var st string
	var tags []string
	if err := pool.QueryRow(ctx, `SELECT status, tags FROM glossary_entities WHERE entity_id=$1`, id).Scan(&st, &tags); err != nil {
		t.Fatalf("query created: %v", err)
	}
	if st != "draft" {
		t.Errorf("want status=draft, got %q", st)
	}
	if !slices.Contains(tags, "ai-suggested") || !slices.Contains(tags, "assistant") {
		t.Errorf("want tags [ai-suggested assistant], got %v", tags)
	}

	// H9 dedup: a second propose of the same name does not create a duplicate.
	id2, status2, _, err := s.proposeNewEntity(ctx, book, kindID, "Nezha", nil, "")
	if err != nil {
		t.Fatal(err)
	}
	if status2 != "skipped_exists" || id2 != id {
		t.Errorf("want skipped_exists with same id, got status=%q id=%v", status2, id2)
	}

	// The tool never mutates an existing entity, so re-proposing WITH attributes must
	// surface them as discarded (sorted) rather than silently dropping them — the
	// signal that tells a weak model to reapply via glossary_entity_set_attributes.
	_, status3, discarded, err := s.proposeNewEntity(ctx, book, kindID, "Nezha",
		map[string]any{"weapon": "Fire-tipped Spear", "title": "Third Prince"}, "")
	if err != nil {
		t.Fatal(err)
	}
	if status3 != "skipped_exists" {
		t.Errorf("want skipped_exists, got %q", status3)
	}
	if !slices.Equal(discarded, []string{"title", "weapon"}) {
		t.Errorf("want discarded attrs [title weapon] (sorted), got %v", discarded)
	}
}

func TestProposeNewEntity_SkipsTombstoned(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	nameAttrID := bookAttrID(t, pool, book, kindID, "name")

	// Seed a previously-rejected (tombstoned) entity named "Rejected".
	var rejectedID uuid.UUID
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'inactive','{ai-suggested,ai-rejected}') RETURNING entity_id`,
		book, kindID).Scan(&rejectedID)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Rejected')`,
		rejectedID, nameAttrID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	s := &Server{pool: pool}

	id, status, _, err := s.proposeNewEntity(ctx, book, kindID, "Rejected", nil, "")
	if err != nil {
		t.Fatal(err)
	}
	if status != "skipped_tombstoned" || id != rejectedID {
		t.Errorf("want skipped_tombstoned with the rejected id, got status=%q id=%v (rejected=%v)", status, id, rejectedID)
	}
}

// D-GLOSSARY-ENTITY-SCOPE — /review-impl HIGH fix (2026-07-09): entity creation +
// the scope_label set now share ONE transaction, so a uq_entity_dedup collision on
// the scope_label UPDATE rolls back the whole creation instead of leaving a
// wrongly-empty-scoped orphan.
//
// D-GLOSSARY-PROPOSE-LOCK (cleared 2026-07-09): the dedup check now runs under the
// SAME per-book advisory lock the bulk extraction pipeline uses (INV-C1), on the
// SAME tx connection as everything else in proposeNewEntity — so this test now
// asserts the FULL guarantee: exactly one "Race Entity" survives 8 truly
// concurrent identical proposals, and it carries the correct scope. (Two earlier
// attempts at this deadlocked under concurrent test load because they mixed
// tx-bound calls with a call hitting s.pool directly for a second connection
// while the tx's own connection was still held open — fixed by giving
// loadAttrDefMap a querier param instead of hardcoding s.pool, so the whole
// function now runs on exactly one connection.)
func TestProposeNewEntity_ConcurrentRaceSerializedByBookLock(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	book := uuid.New()
	adoptTestBook(t, pool, book)
	kindID := bookKindID(t, pool, book, "character")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	s := &Server{pool: pool}

	const n = 8
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			_, _, _, _ = s.proposeNewEntity(ctx, book, kindID, "Race Entity", nil, "World A")
		}()
	}
	wg.Wait()

	rows, err := pool.Query(ctx, `
		SELECT ge.scope_label
		FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE ge.book_id=$1 AND ge.kind_id=$2 AND ba.code='name' AND eav.original_value='Race Entity'
		  AND ge.deleted_at IS NULL`,
		book, kindID)
	if err != nil {
		t.Fatalf("query result: %v", err)
	}
	defer rows.Close()
	found := 0
	for rows.Next() {
		found++
		var scope string
		if err := rows.Scan(&scope); err != nil {
			t.Fatalf("scan: %v", err)
		}
		if scope != "World A" {
			t.Errorf("row %d: want scope_label=World A, got %q (an empty/wrong-scoped orphan survived the race)", found, scope)
		}
	}
	if found != 1 {
		t.Errorf("want exactly 1 surviving entity after the race (the advisory lock serializes the dedup check), got %d", found)
	}
}
